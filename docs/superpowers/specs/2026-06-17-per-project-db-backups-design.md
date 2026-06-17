# Per-Project Database Backups Design

**Date:** 2026-06-17
**Status:** Draft — pending review
**Supersedes / extends:** [2026-04-03-database-backup-design.md](2026-04-03-database-backup-design.md)

## Overview

Today DevTrack can back up only its **own** database: a single, synchronous, admin-triggered
`pg_dump` of `DATABASES['default']`, recorded by `DatabaseBackup` in the `settings` app.

This design generalizes that into a **per-project, multi-database backup engine**:

- An admin registers one or more **backup targets**, each pointing at a database.
- Targets can be **site-level** (e.g. DevTrack's own DB) or **scoped to a tracked Project**.
- Remote/external production databases are reached over **SSH** (DevTrack can SSH to every host).
- Each target supports **scheduled** (Celery Beat) and **manual** backups.
- Old backups are pruned per a **retention policy**.

The existing one-click self-backup becomes the degenerate case of a single site-level target with
no SSH host (local `pg_dump`).

## Locked Decisions

These were settled during brainstorming and drive the design:

1. **Database nature** — Remote/external production databases, **all reachable from DevTrack over SSH**.
   The execution path is SSH → run `pg_dump` on the remote → stream the dump back. No direct
   PostgreSQL network connection to remote hosts is assumed.
2. **Credentials** — Store **references only**. Non-secret connection info (SSH host alias, db name,
   container name, db user) lives in the DB. **Secrets never enter the DB**: SSH private keys live on
   the host (container `~/.ssh` + ssh-agent / mounted key files); DB passwords rely on the remote's
   `.pgpass` or environment. This matches the project's "config that varies by deployment belongs
   outside the database" principle.
3. **Scheduling** — Both **scheduled and manual**. Each target may carry a cron schedule (driven by
   `django_celery_beat`) and always exposes a manual "Backup now" action.
4. **Permissions** — **Admin only** (`IsAdminUser` / staff-level, which includes the 系统管理员 group
   and superusers). NOT delegated to project managers; no object-level permission checks.
5. **Home** — A new dedicated app **`apps/backups`**, a sibling of `uptime`/`kpi`/`notifications`.
   Not `tools` (a user-facing attachment service), not folded into `settings` (a django-solo
   singleton config app), not merged with `uptime` (a shipped, cohesive subsystem).

## Architecture

### Why a dedicated app

The codebase organizes by **subsystem-per-app**: `repos`, `uptime`, `kpi`, `notifications`,
`external`, each with its own `models/services/tasks/views/urls` and an `/api/<name>/` route. With
targets + scheduling + SSH execution, the backup feature acquires the exact file shape of `uptime`
(`models.py`, `services.py`, `tasks.py`, `serializers.py`, `views.py`, `urls.py`). Treating like with
like, it gets its own app and its own `/api/backups/` route.

```text
[Frontend /app/settings/backups]
        |  POST /api/backups/targets/{id}/run/   (manual)
        v
[Django view: IsAdminUser]  --enqueue-->  Celery: apps.backups.tasks.run_backup(target_id, ...)
                                              |
   django_celery_beat PeriodicTask  --------->|   (scheduled, same task)
                                              v
                                   BackupTarget.ssh_host empty?
                                    /                        \
                              yes (local)                no (remote)
                                  |                          |
                       pg_dump -Fc <db> -f file   ssh <host> "[docker exec <c>] pg_dump -Fc <db>" > file
                                  \                          /
                                   v                        v
                              write to BACKUP_DIR/<filename>
                                              |
                              update DatabaseBackup record (status/size/error)
                                              |
                              prune old backups per target.retention_count
```

## Data Model (`apps/backups/models.py`)

### `BackupTarget` (new)

A registered database that can be backed up. All fields are non-secret references.

| Field | Type | Notes |
|---|---|---|
| `project` | FK → `projects.Project`, `null=True, blank=True` | `NULL` = site-level (e.g. DevTrack itself). Mirrors `ExternalAPIKey`'s nullable-project convention. `on_delete=CASCADE` — deleting a project removes its targets. |
| `name` | `CharField(100)` | Display name. |
| `engine` | `CharField`, choices `[("postgres","PostgreSQL")]`, default `postgres` | Only PostgreSQL implemented; enum reserved for future engines. |
| `ssh_host` | `CharField(255)`, blank | SSH host **or alias** resolved via the container's `~/.ssh/config`. **Blank = local execution** (the DevTrack-self case). |
| `ssh_user` | `CharField(64)`, blank | Optional; alias config may already specify it. |
| `ssh_port` | `PositiveIntegerField`, null | Optional. |
| `docker_container` | `CharField(128)`, blank | If set, `pg_dump` runs via `docker exec <container>` on the remote. Blank = run directly on the host. |
| `db_name` | `CharField(128)` | Database to dump. |
| `db_user` | `CharField(64)`, blank | DB role; blank falls back to remote default. |
| `db_host` | `CharField(255)`, blank | From the remote's perspective; blank = `localhost` on the remote. |
| `db_port` | `PositiveIntegerField`, null | Blank = default 5432. |
| `schedule_cron` | `CharField(64)`, blank | 5-field cron. **Blank = manual only.** |
| `schedule_enabled` | `BooleanField(default=True)` | Pause scheduling without deleting the cron. |
| `retention_count` | `PositiveIntegerField(default=7)` | Keep the newest N **successful** backups; older ones (and their files) are pruned. `0` = keep all. |
| `is_active` | `BooleanField(default=True)` | Inactive targets neither schedule nor accept manual runs. |
| `created_by` | FK → user, `SET_NULL`, null | |
| `created_at` / `updated_at` | timestamps | |

### `DatabaseBackup` (moved from `settings`, extended)

A single backup run record. Existing fields are preserved; two are added.

| Field | Change | Notes |
|---|---|---|
| `target` | **new** FK → `BackupTarget`, `on_delete=SET_NULL, null=True, blank=True` | Deleting a target keeps its history; the row simply loses its target link. |
| `trigger` | **new** `CharField`, choices `[("manual","手动"),("scheduled","定时")]`, default `manual` | Distinguishes Beat runs from button clicks. |
| `filename` | unchanged | `<db_name>_<timestamp>.dump`. |
| `file_size` | unchanged | bytes, null until success. |
| `status` | unchanged | `running` / `success` / `failed`. |
| `error_message` | unchanged | |
| `created_by` | unchanged | `NULL` for scheduled (system) runs. |
| `created_at` | unchanged | |

## Execution (`apps/backups/tasks.py` + `services.py`)

A single Celery task, two modes:

```python
@shared_task
def run_backup(target_id, trigger="scheduled", created_by_id=None): ...
```

1. Load the target; abort if inactive.
2. **Per-target concurrency lock**: if a `DatabaseBackup` with `status="running"` already exists for
   this target, skip (return 409-equivalent). (Replaces today's global single-run lock — different
   targets may run concurrently.)
3. Create the `DatabaseBackup` row (`status="running"`, `trigger`, `created_by_id`, `filename`).
4. Build and run the dump (in `services.py`):
   - **Local** (`ssh_host` blank): `pg_dump -h <db_host> -p <db_port> -U <db_user> -Fc <db_name> -f <path>`,
     `PGPASSWORD` from `DATABASES['default']` — i.e. today's behavior.
   - **Remote** (`ssh_host` set): run `pg_dump -Fc <db_name>` (optionally wrapped in
     `docker exec <container>`) **on the remote via SSH**, streaming stdout (`-Fc`) into the local
     `BACKUP_DIR/<filename>`. DB auth handled remotely (`.pgpass`/env); SSH auth via host keys.
5. On success: `status="success"`, `file_size`. On failure: `status="failed"`, `error_message`,
   delete the partial file.
6. **Retention**: after a successful run, delete successful backups beyond `retention_count`
   (rows + files) for this target.

### Security note — command construction

Target fields (`ssh_host`, `db_name`, `docker_container`, …) are admin-entered but still flow into a
shell/SSH command. Use `subprocess` **argument lists** (no `shell=True`) for the local case. For the
remote case the remote command string must be assembled with strict quoting/escaping (e.g.
`shlex.quote`) — the SSH invocation itself uses an arg list, and the single remote command string is
escaped. Admin-only access lowers but does not eliminate the injection surface.

## Scheduling (`django_celery_beat`)

Already installed (`CELERY_BEAT_SCHEDULER = django_celery_beat.schedulers:DatabaseScheduler`), with
seed-migration precedent in `kpi`/`ai`.

On `BackupTarget` save (signal or serializer hook), synchronize one `PeriodicTask`:

- name: `backup:target:{id}`
- task: `apps.backups.tasks.run_backup`, args `[target.id]`, kwargs `{"trigger": "scheduled"}`
- schedule: a `CrontabSchedule` parsed from `schedule_cron`
- `enabled = is_active and schedule_enabled and bool(schedule_cron)`

On target delete, remove the `PeriodicTask`. Blank `schedule_cron` → no task (manual-only target).

## API (`/api/backups/`, mounted in `apps/urls.py`)

All endpoints `IsAdminUser`.

| Method | Path | Description |
|---|---|---|
| GET | `/api/backups/targets/` | List targets (filterable by `project`). |
| POST | `/api/backups/targets/` | Create a target. |
| GET/PATCH/DELETE | `/api/backups/targets/{id}/` | Retrieve / update / delete a target. |
| POST | `/api/backups/targets/{id}/run/` | Enqueue a manual backup → `202 Accepted`. Replaces the old global "立即备份". |
| GET | `/api/backups/backups/` | List backup records (filterable by `target`, `project`). |
| GET | `/api/backups/backups/{id}/download/` | Stream the dump file (`FileResponse`). |
| DELETE | `/api/backups/backups/{id}/` | Delete record + file. |

Serializers expose only non-secret fields. The target serializer surfaces a derived connection
summary and the latest backup status for list display.

## Migration Strategy

The one piece of real migration work — moving `DatabaseBackup` from `settings` to `backups` while
preserving production rows and files.

1. **`backups/0001`** — `makemigrations`-generated `CreateModel` for `BackupTarget` and
   `DatabaseBackup` (new app).
2. **`backups/0002` data migration (`RunPython`)** —
   a. Create one site-level target **"DevTrakr 自身"** (`project=NULL`, `ssh_host=""`,
      `db_name` from `DATABASES['default']['NAME']`).
   b. Copy every row from `settings_databasebackup` into `backups_databasebackup`, pointing `target`
      at the self-target, preserving `filename/file_size/status/error_message/created_by/created_at`,
      `trigger="manual"`.
3. **`settings/00xx`** — `makemigrations`-generated `DeleteModel(DatabaseBackup)`; remove
   `backup_views.py`, `backup_serializers.py`, backup routes from `settings/urls.py`, and the admin
   registration.
4. Files in `BACKUP_DIR` are keyed by `filename` and are **not touched** — downloads keep working
   against the new rows.

This follows the repo convention: structural changes via Django-generated migrations; the row copy is
a hand-written data migration (the kind Django cannot generate).

## Infrastructure Changes

Building on the 2026-04-03 baseline (ASGI/uvicorn, `postgresql-client` in the backend image,
`BACKUP_DIR` volume):

- **SSH client + key access in the backend container** — install `openssh-client`; mount/provide
  `~/.ssh` (config + private keys) and known_hosts, or run an ssh-agent. Keys are deployment material
  on the host, per Decision 2.
- **Celery worker** must run the backup task (it already runs `kpi`/`ai`/`repos` tasks); ensure the
  worker container has the SSH client + keys too, since that is where `run_backup` executes.
- Remote hosts must have `pg_dump` available (directly or inside `docker_container`).

## Frontend (`/app/settings/backups`, route + nav unchanged)

The page evolves from "one global list + one Backup-now button" into a **target-oriented** view:

- Sections: **Site-level** targets, then per-Project groups.
- Each target row: name, connection summary, schedule (cron / manual), retention, latest backup
  status, and a **"立即备份"** action.
- Expanding a target (or a detail view) lists that target's `DatabaseBackup` records with
  **下载 / 删除**.
- Target **create/edit form** (admin): project (or site-level), SSH fields, DB fields, cron,
  retention. The form must make clear that secrets are NOT entered here — only references.
- Permission integration unchanged: admin-only via `useNavigation.ts` + `auth.global.ts`. The API
  base moves from `/api/settings/backups/` to `/api/backups/...`.

## Out of Scope (YAGNI)

- Non-PostgreSQL engines (the `engine` field reserves the seam only).
- Delegating backup management to project managers (admin-only for now).
- Encryption-at-rest of dumps, off-host upload (S3/remote), or cross-region replication.
- Restore-from-backup UI (download + manual restore remains the workflow).
- Storing any secret in the database.

## Testing

`pytest` with the existing fixtures/factories:

- Model: `BackupTarget` validation; nullable `project` (site vs project); `DatabaseBackup.target`
  `SET_NULL` on target delete.
- Scheduling: saving a target with `schedule_cron` creates/updates the `PeriodicTask`; clearing it or
  setting `is_active=False`/`schedule_enabled=False` disables it; deleting the target removes it.
- Execution (mock the subprocess/SSH layer): local vs remote command construction; success/failure
  status transitions; partial-file cleanup on failure; per-target running lock; retention pruning.
- API: `IsAdminUser` enforcement on every endpoint; manual run returns `202`; list filtering by
  project/target; download streams the file; delete removes row + file.
- Migration: data migration copies legacy rows onto the site-level self-target.
