# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

DevTrack is a project management and issue tracking platform. Django REST Framework backend with a Nuxt 4 SPA frontend, connected via JWT authentication.

## Development Commands

### Backend (run from `backend/`)

```bash
uv run python manage.py runserver          # Start dev server on :8000
uv run python manage.py migrate            # Apply migrations
uv run python manage.py makemigrations     # Generate migrations
uv run python manage.py sync_page_perms    # Sync page routes + permission groups from PAGE_PERMS config
uv run python manage.py createsuperuser    # Create admin user
uv sync                                    # Install dependencies
uv sync --dev                              # Install with dev dependencies
```

### Backend Tests (run from `backend/`)

```bash
uv run pytest                              # Run all tests
uv run pytest tests/test_issues.py         # Run a single test file
uv run pytest tests/test_issues.py::TestIssueAPI::test_create_issue -v  # Run a single test
uv run pytest -x                           # Stop on first failure
```

Tests use `pytest-django` with `factory-boy`. Fixtures in `tests/conftest.py`: `api_client` (unauthenticated), `auth_client` (admin-authenticated), `site_settings`. Factories in `tests/factories.py`.

### Frontend (run from `frontend/`)

```bash
npm run dev                                # Start dev server on :3004
npm run build                              # Production build
npx nuxi typecheck                         # Type check
```

### Docker

```bash
docker compose up --build                  # Start full stack (backend :8000, frontend :3000)
```

## Architecture

### Backend

- **`backend/config/`** — Django settings, root URL conf
- **`backend/apps/`** — All Django apps, plus shared `urls.py` and `permissions.py`
- **`backend/tests/`** — All tests in one directory, not per-app

Django apps: `users`, `projects`, `issues`, `repos`, `settings`

API is mounted at `/api/` with sub-routes: `auth/`, `users/`, `projects/`, `issues/`, `dashboard/`, `repos/`, `settings/`.

### Frontend

- **Nuxt 4 SPA** (SSR disabled), proxies `/api/**` to backend
- **`frontend/app/composables/`** — Core logic:
  - `useApi.ts` — JWT token management, auto-refresh on 401
  - `useAuth.ts` — User state, `can(permission)`, `hasGroup(group)`
  - `useNavigation.ts` — Nav items with permission-based filtering

### Permission System

Django model permissions flow to the frontend via `/api/auth/me/` (returns `permissions: string[]` in `app_label.codename` format). Two enforcement points:

1. **Sidebar visibility** — `useNavigation.ts` `filteredNavItems` hides nav items where `can(permission)` is false
2. **Route guard** — `middleware/auth.global.ts` `routePermissions` map blocks navigation and redirects to `/app/forbidden`

When adding a new page backed by a Django model, add the permission to both `navItems` in `useNavigation.ts` and `routePermissions` in `auth.global.ts`. See `.claude/skills/page-permissions.md` for the full checklist.

### Database

PostgreSQL. Default local connection: `127.0.0.1:25432`, database `devtrack`. Configurable via env vars `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`.

## Deployment

Push to `env/test` or `env/prod` branch triggers CI (`.github/workflows/build-push.yml`) which builds and pushes both backend and frontend Docker images.

`env/test` and `env/prod` are release branches — they only track what is currently deployed. Divergence from `main` is expected and can be ignored; always force-push from `main`.

```bash
git push -f origin main:env/test     # Deploy to test (builds both frontend + backend)
git push -f origin main:env/prod     # Deploy to production
```

## Key Conventions

- Backend uses `uv` as package manager (not pip)
- Issue numbers are auto-incremented integers, displayed as `ISS-001`
- `SiteSettings` is a singleton (django-solo) for labels, priorities, and issue statuses
- `FullDjangoModelPermissions` in `apps/permissions.py` enforces `view_*` on GET (unlike default DRF which allows unauthenticated reads)
- User groups are defined in `sync_page_perms` management command — run after migrations
- Frontend language is Chinese (zh-hans)
- create skills in ENGLISH, but code comments and UI text in CHINESE
- For runtime/deprecation warnings, only resolve via dependency upgrades or upstream fixes; do not silence warnings (for example via `NODE_OPTIONS --disable-warning`) and do not downgrade only to hide warnings. If it cannot be solved safely, report it explicitly.

## gstack

Use the `/browse` skill from gstack for all web browsing. Never use `mcp__claude-in-chrome__*` tools.

Available skills: `/office-hours`, `/plan-ceo-review`, `/plan-eng-review`, `/plan-design-review`, `/design-consultation`, `/design-shotgun`, `/design-html`, `/review`, `/ship`, `/land-and-deploy`, `/canary`, `/benchmark`, `/browse`, `/connect-chrome`, `/qa`, `/qa-only`, `/design-review`, `/setup-browser-cookies`, `/setup-deploy`, `/retro`, `/investigate`, `/document-release`, `/codex`, `/cso`, `/autoplan`, `/careful`, `/freeze`, `/guard`, `/unfreeze`, `/gstack-upgrade`, `/learn`.
