#!/usr/bin/env bash
# DevTrack worktree bootstrap. Idempotent. Run inside a freshly created worktree.
# Usage:  ./.worktree-init.sh [local|skip]
#   local  (default) — restore DB from latest dump in main checkout's .backups/
#   skip            — don't touch the database (use when iterating on frontend only)
#
# To pull a fresh prod dump first, run `/db-backup prod` from the main checkout, then re-run this.

set -euo pipefail

MODE="${1:-local}"

# ── Locate main checkout (we're inside a worktree) ─────────────────────────
MAIN_REPO=$(git rev-parse --path-format=absolute --git-common-dir | xargs dirname)
BRANCH=$(git branch --show-current)
[ -z "$BRANCH" ] && { echo "❌ HEAD is detached — create a branch first"; exit 1; }

# ── Derive deterministic identifiers from branch name ──────────────────────
# Port ranges deliberately above main checkout's 8100 (Django) and 3004 (Nuxt).
SLUG=$(echo "$BRANCH" | tr '/' '-' | tr -cd 'a-zA-Z0-9-' | tr '[:upper:]' '[:lower:]')
OFFSET=$(echo -n "$SLUG" | cksum | awk '{print $1 % 100}')
DB_NAME="devtrack_wt_${SLUG}"
BACKEND_PORT=$((8201 + OFFSET))      # 8201-8300
FRONTEND_PORT=$((3101 + OFFSET))     # 3101-3200

echo "🌲 Worktree bootstrap"
echo "   branch:        $BRANCH"
echo "   main repo:     $MAIN_REPO"
echo "   db name:       $DB_NAME"
echo "   backend port:  $BACKEND_PORT"
echo "   frontend port: $FRONTEND_PORT"
echo ""

# ── 1. Backend env: copy from main, override worktree-specific fields ──────
SRC_BACKEND_ENV="$MAIN_REPO/backend/.env"
if [ ! -f "$SRC_BACKEND_ENV" ]; then
  echo "❌ $SRC_BACKEND_ENV not found in main checkout. Set it up there first."
  exit 1
fi
cp "$SRC_BACKEND_ENV" backend/.env

# Override DB_NAME (in-place, portable across macOS/Linux)
python3 - <<PY
import re, pathlib
p = pathlib.Path("backend/.env")
text = p.read_text()

def upsert(text, key, value):
    pattern = re.compile(rf'(?m)^{re.escape(key)}=.*$')
    if pattern.search(text):
        return pattern.sub(f'{key}={value}', text, count=1)
    return text.rstrip() + f'\n{key}={value}\n'

text = upsert(text, "DB_NAME", "${DB_NAME}")
text = upsert(text, "BACKEND_PORT", "${BACKEND_PORT}")

# Append CSRF for the worktree's frontend port (if not already there)
csrf_origin = "http://localhost:${FRONTEND_PORT}"
m = re.search(r'(?m)^DJANGO_CSRF_TRUSTED_ORIGINS=(.*)$', text)
if m and csrf_origin not in m.group(1):
    text = text.replace(m.group(0), m.group(0) + "," + csrf_origin)
elif not m:
    text += f"\nDJANGO_CSRF_TRUSTED_ORIGINS={csrf_origin}\n"

pathlib.Path("backend/.env").write_text(text)
PY
echo "✅ backend/.env written (DB_NAME=$DB_NAME, BACKEND_PORT=$BACKEND_PORT, CSRF appended)"

# ── 2. Frontend env: copy from main, override API base and port ────────────
SRC_FRONTEND_ENV="$MAIN_REPO/frontend/.env"
if [ -f "$SRC_FRONTEND_ENV" ]; then
  cp "$SRC_FRONTEND_ENV" frontend/.env
else
  : > frontend/.env
fi
python3 - <<PY
import re, pathlib
p = pathlib.Path("frontend/.env")
text = p.read_text() if p.exists() else ""

def upsert(text, key, value):
    pattern = re.compile(rf'(?m)^{re.escape(key)}=.*$')
    if pattern.search(text):
        return pattern.sub(f'{key}={value}', text)
    return text.rstrip() + f'\n{key}={value}\n'

text = upsert(text, "NUXT_API_BASE", "http://localhost:${BACKEND_PORT}")
text = upsert(text, "NUXT_PORT",     "${FRONTEND_PORT}")
p.write_text(text)
PY
echo "✅ frontend/.env written (NUXT_API_BASE=:$BACKEND_PORT, NUXT_PORT=$FRONTEND_PORT)"

# ── 3. VSCode launch.json: copy fresh from main, substitute backend port ──
# Worktree gets its own .vscode/launch.json with the worktree's port baked
# in. Main repo's launch.json stays untouched. Idempotent (re-copies each run).
# We mark it skip-worktree so the local mod never accidentally gets committed
# back into the repo.
if [ -f "$MAIN_REPO/.vscode/launch.json" ]; then
  mkdir -p .vscode
  # If previously skip-worktree'd, we must clear it before cp can write a fresh
  # copy without git getting confused by the next index check.
  git update-index --no-skip-worktree .vscode/launch.json 2>/dev/null || true
  cp "$MAIN_REPO/.vscode/launch.json" .vscode/launch.json
  python3 - <<PY
import re, pathlib
p = pathlib.Path(".vscode/launch.json")
text = p.read_text()
text = re.sub(r'(0\.0\.0\.0:)\d+', r'\g<1>${BACKEND_PORT}', text)
p.write_text(text)
PY
  git update-index --skip-worktree .vscode/launch.json
  echo "✅ .vscode/launch.json patched to port $BACKEND_PORT (skip-worktree, won't be committed)"
fi

# ── 4. Database: restore from latest dump in main checkout ─────────────────
if [ "$MODE" = "skip" ]; then
  echo "⏭  database skipped (MODE=skip)"
else
  LATEST=$(ls -t "$MAIN_REPO/.backups/devtrakr_prod_dump_"*.dump 2>/dev/null | head -1 || true)
  if [ -z "$LATEST" ]; then
    echo "⚠️  No prod dump found in $MAIN_REPO/.backups/"
    echo "    Run /db-backup prod from the main checkout, then re-run this script."
    exit 1
  fi
  AGE_DAYS=$(( ($(date +%s) - $(stat -f %m "$LATEST" 2>/dev/null || stat -c %Y "$LATEST")) / 86400 ))
  echo "📦 Restoring from $(basename "$LATEST") (${AGE_DAYS} days old)"

  export PGPASSWORD=postgres
  PSQL="psql -h 127.0.0.1 -p 25432 -U postgres -v ON_ERROR_STOP=1"
  $PSQL -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='$DB_NAME' AND pid<>pg_backend_pid();" >/dev/null 2>&1 || true
  $PSQL -c "DROP DATABASE IF EXISTS \"$DB_NAME\";"
  $PSQL -c "CREATE DATABASE \"$DB_NAME\";"
  pg_restore -h 127.0.0.1 -p 25432 -U postgres -d "$DB_NAME" --no-owner --no-acl "$LATEST" 2>&1 \
    | grep -vE '^pg_restore: (warning|error: could not execute query: ERROR:  role .* does not exist)' || true
  echo "✅ database $DB_NAME ready"
fi

# ── 5. Dependencies ────────────────────────────────────────────────────────
echo "📥 Installing backend deps (uv sync)"
(cd backend && uv sync --quiet)

echo "📥 Installing frontend deps (npm install)"
(cd frontend && npm install --no-audit --no-fund --silent)

# ── 6. Migrations (catches any post-dump schema changes) ────────────────────
if [ "$MODE" != "skip" ]; then
  echo "🔧 Running migrations"
  (cd backend && uv run python manage.py migrate)
fi

# ── 7. Report ──────────────────────────────────────────────────────────────
cat <<EOF

✅ Worktree ready

  Backend:  cd backend && uv run python manage.py runserver 0.0.0.0:$BACKEND_PORT
  Frontend: cd frontend && npm run dev    # reads NUXT_PORT from .env

  Database: $DB_NAME
  URLs:     http://localhost:$FRONTEND_PORT  (frontend)
            http://localhost:$BACKEND_PORT   (backend API)

EOF
