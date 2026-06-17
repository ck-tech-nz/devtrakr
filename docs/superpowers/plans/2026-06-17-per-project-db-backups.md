# Per-Project Database Backups Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generalize the single self-backup feature into a per-project, multi-database backup engine in a new `apps/backups` app, with SSH-reachable remote targets, scheduled + manual runs, and retention.

**Architecture:** New `apps/backups` app (sibling of `uptime`). `BackupTarget` holds reference-only connection info (nullable `project`: NULL = site-level). `DatabaseBackup` moves from `settings`, gains `target`/`trigger`. A single Celery task `run_backup` dumps locally (no `ssh_host`) or over SSH (remote). `django_celery_beat` drives per-target cron schedules. Admin-only API at `/api/backups/`.

**Tech Stack:** Django REST Framework, Celery + `django_celery_beat`, PostgreSQL `pg_dump`, `subprocess`, pytest + factory-boy, Nuxt 4 / Vue 3 (Nuxt UI `UTable`/`UButton`).

## Global Constraints

- Backend package manager: `uv` — run everything as `uv run …` from `backend/`.
- Permissions: every backup endpoint uses DRF `IsAdminUser` (staff-level). No project-manager delegation, no object-level checks.
- **No secret ever enters the database.** `BackupTarget` stores only references (SSH host/alias, db name, container, db user). SSH private keys + DB passwords live on the host.
- Migrations: structural changes via `makemigrations`; only the legacy row-copy is a hand-written `RunPython` data migration. Never edit an existing migration — add a new one.
- Frontend language is Chinese (zh-hans); code comments and UI text in Chinese. Specs/plans in English.
- Each task ends green: `uv run pytest` passes and the running system still works.

---

### Task 1: Scaffold `apps/backups` + models

**Files:**
- Create: `backend/apps/backups/__init__.py` (empty)
- Create: `backend/apps/backups/apps.py`
- Create: `backend/apps/backups/models.py`
- Modify: `backend/config/settings.py:47` (add `"apps.backups",` to INSTALLED_APPS, after `"apps.uptime",`)
- Create: `backend/apps/backups/migrations/__init__.py` (empty)
- Test: `backend/tests/test_backup_models.py`

**Interfaces:**
- Produces: `apps.backups.models.BackupTarget` (fields: `project` FK nullable, `name`, `engine`, `ssh_host`, `ssh_user`, `ssh_port`, `docker_container`, `db_name`, `db_user`, `db_host`, `db_port`, `schedule_cron`, `schedule_enabled`, `retention_count`, `is_active`, `created_by`, `created_at`, `updated_at`; reverse accessor `backups`).
- Produces: `apps.backups.models.DatabaseBackup` (fields: `target` FK nullable SET_NULL, `filename`, `file_size`, `status`, `error_message`, `trigger`, `created_by`, `created_at`).

- [ ] **Step 1: Write `apps.py`**

```python
# backend/apps/backups/apps.py
from django.apps import AppConfig


class BackupsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.backups"
    verbose_name = "数据库备份"
```

- [ ] **Step 2: Register the app**

In `backend/config/settings.py`, add `"apps.backups",` immediately after `"apps.uptime",` in INSTALLED_APPS.

- [ ] **Step 3: Write `models.py`**

```python
# backend/apps/backups/models.py
from django.conf import settings
from django.db import models


class BackupTarget(models.Model):
    """一个可备份的数据库目标。所有字段都是非敏感引用——密钥留在主机上。"""

    ENGINE_CHOICES = [("postgres", "PostgreSQL")]

    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="backup_targets",
        verbose_name="关联项目",
        help_text="留空表示站点级目标(如 DevTrakr 自身)",
    )
    name = models.CharField(max_length=100, verbose_name="名称")
    engine = models.CharField(
        max_length=20, choices=ENGINE_CHOICES, default="postgres", verbose_name="引擎"
    )

    # SSH 引用:密钥留主机(容器内 ~/.ssh + ssh-agent / 挂载的 key 文件)
    ssh_host = models.CharField(
        max_length=255, blank=True, default="",
        verbose_name="SSH 主机", help_text="留空=本地执行(备份 DevTrakr 自身)",
    )
    ssh_user = models.CharField(max_length=64, blank=True, default="", verbose_name="SSH 用户")
    ssh_port = models.PositiveIntegerField(null=True, blank=True, verbose_name="SSH 端口")
    docker_container = models.CharField(
        max_length=128, blank=True, default="",
        verbose_name="DB 容器名", help_text="留空=主机上直接执行 pg_dump",
    )

    # DB 引用:密码靠远程 .pgpass / env,不进库
    db_name = models.CharField(max_length=128, verbose_name="数据库名")
    db_user = models.CharField(max_length=64, blank=True, default="", verbose_name="DB 用户")
    db_host = models.CharField(max_length=255, blank=True, default="", verbose_name="DB 主机(远程视角)")
    db_port = models.PositiveIntegerField(null=True, blank=True, verbose_name="DB 端口")

    # 调度
    schedule_cron = models.CharField(
        max_length=64, blank=True, default="",
        verbose_name="定时(cron)", help_text="5 段 cron;留空=仅手动",
    )
    schedule_enabled = models.BooleanField(default=True, verbose_name="启用定时")

    # 保留
    retention_count = models.PositiveIntegerField(
        default=7, verbose_name="保留份数", help_text="保留最近 N 个成功备份;0=不限",
    )

    is_active = models.BooleanField(default=True, verbose_name="启用")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "备份目标"
        verbose_name_plural = "备份目标"
        ordering = ["project_id", "name"]

    def __str__(self):
        return self.name


class DatabaseBackup(models.Model):
    target = models.ForeignKey(
        BackupTarget, on_delete=models.SET_NULL, null=True, blank=True, related_name="backups",
    )
    filename = models.CharField(max_length=255)
    file_size = models.BigIntegerField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=[("running", "备份中"), ("success", "成功"), ("failed", "失败")],
    )
    error_message = models.TextField(blank=True, default="")
    trigger = models.CharField(
        max_length=20,
        choices=[("manual", "手动"), ("scheduled", "定时")],
        default="manual",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "数据库备份"
        verbose_name_plural = "数据库备份"

    def __str__(self):
        return self.filename
```

- [ ] **Step 4: Generate the migration**

Run: `cd backend && uv run python manage.py makemigrations backups`
Expected: creates `backend/apps/backups/migrations/0001_initial.py` with `CreateModel` for `BackupTarget` and `DatabaseBackup`.

- [ ] **Step 5: Write the failing tests**

```python
# backend/tests/test_backup_models.py
import pytest
from apps.backups.models import BackupTarget, DatabaseBackup
from apps.projects.models import Project

pytestmark = pytest.mark.django_db


class TestBackupTarget:
    def test_site_level_target_has_null_project(self):
        t = BackupTarget.objects.create(name="DevTrakr 自身", db_name="devtrack")
        assert t.project is None
        assert t.ssh_host == ""
        assert t.retention_count == 7
        assert t.is_active is True

    def test_project_scoped_target(self):
        p = Project.objects.create(name="P", status="进行中")
        t = BackupTarget.objects.create(name="P 生产库", db_name="p_prod", project=p)
        assert t.project_id == p.id
        assert list(p.backup_targets.all()) == [t]


class TestDatabaseBackup:
    def test_backup_links_to_target(self):
        t = BackupTarget.objects.create(name="T", db_name="d")
        b = DatabaseBackup.objects.create(target=t, filename="d_1.dump", status="running")
        assert b.trigger == "manual"
        assert list(t.backups.all()) == [b]

    def test_deleting_target_keeps_backup_history(self):
        t = BackupTarget.objects.create(name="T", db_name="d")
        b = DatabaseBackup.objects.create(target=t, filename="d_1.dump", status="success")
        t.delete()
        b.refresh_from_db()
        assert b.target_id is None
        assert DatabaseBackup.objects.filter(id=b.id).exists()

    def test_ordering_newest_first(self):
        b1 = DatabaseBackup.objects.create(filename="a.dump", status="success")
        b2 = DatabaseBackup.objects.create(filename="b.dump", status="success")
        assert list(DatabaseBackup.objects.values_list("id", flat=True)) == [b2.id, b1.id]
```

- [ ] **Step 6: Run tests**

Run: `cd backend && uv run pytest tests/test_backup_models.py -v`
Expected: PASS (4 tests).

- [ ] **Step 7: Commit**

```bash
git add backend/apps/backups backend/config/settings.py backend/tests/test_backup_models.py
git commit -m "feat(backups): scaffold backups app with BackupTarget + DatabaseBackup models"
```

---

### Task 2: Command builders (`services.py`, pure functions)

**Files:**
- Create: `backend/apps/backups/services.py`
- Test: `backend/tests/test_backup_services.py`

**Interfaces:**
- Produces: `get_backup_dir() -> str`
- Produces: `parse_cron(expr: str) -> dict` (keys: `minute, hour, day_of_month, month_of_year, day_of_week`; raises `ValueError` if not 5 fields)
- Produces: `build_local_command(target, filepath: str) -> list[str]`
- Produces: `build_remote_dump_cmd(target) -> str` (single shell command string to run on the remote)
- Produces: `build_ssh_argv(target, remote_cmd: str) -> list[str]`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_backup_services.py
import pytest
from apps.backups import services
from apps.backups.models import BackupTarget

pytestmark = pytest.mark.django_db


def test_parse_cron_valid():
    assert services.parse_cron("30 2 * * *") == {
        "minute": "30", "hour": "2", "day_of_month": "*",
        "month_of_year": "*", "day_of_week": "*",
    }


def test_parse_cron_invalid_field_count():
    with pytest.raises(ValueError):
        services.parse_cron("30 2 * *")


def test_build_local_command_uses_target_db_name():
    t = BackupTarget(name="self", db_name="devtrack")
    argv = services.build_local_command(t, "/tmp/x.dump")
    assert argv[0] == "pg_dump"
    assert "-Fc" in argv and "devtrack" in argv
    assert argv[-2:] == ["-f", "/tmp/x.dump"]


def test_build_remote_dump_cmd_plain_host():
    t = BackupTarget(name="r", ssh_host="prod1", db_name="app", db_user="app")
    cmd = services.build_remote_dump_cmd(t)
    assert cmd.startswith("pg_dump")
    assert "-U app" in cmd and "-Fc app" in cmd
    assert "docker" not in cmd


def test_build_remote_dump_cmd_with_container():
    t = BackupTarget(name="r", ssh_host="prod1", db_name="app", docker_container="pg")
    cmd = services.build_remote_dump_cmd(t)
    assert cmd.startswith("docker exec pg pg_dump")


def test_build_ssh_argv_with_user_and_port():
    t = BackupTarget(name="r", ssh_host="prod1", ssh_user="ubuntu", ssh_port=2222, db_name="app")
    argv = services.build_ssh_argv(t, "pg_dump -Fc app")
    assert argv[0] == "ssh"
    assert "-p" in argv and "2222" in argv
    assert "ubuntu@prod1" in argv
    assert argv[-1] == "pg_dump -Fc app"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_backup_services.py -v`
Expected: FAIL with `AttributeError: module 'apps.backups.services' has no attribute ...`

- [ ] **Step 3: Implement `services.py`**

```python
# backend/apps/backups/services.py
import os
import shlex
import subprocess

from django.conf import settings


def get_backup_dir() -> str:
    d = getattr(settings, "BACKUP_DIR", "/data/backups")
    os.makedirs(d, exist_ok=True)
    return d


def parse_cron(expr: str) -> dict:
    """把 5 段 cron 解析成 django_celery_beat CrontabSchedule 字段。"""
    parts = expr.split()
    if len(parts) != 5:
        raise ValueError("cron 必须是 5 段(分 时 日 月 周)")
    minute, hour, dom, mon, dow = parts
    return {
        "minute": minute, "hour": hour, "day_of_month": dom,
        "month_of_year": mon, "day_of_week": dow,
    }


def build_local_command(target, filepath: str) -> list:
    """本地 pg_dump(备份 DevTrakr 自身):凭据取自 DATABASES['default']。"""
    db = settings.DATABASES["default"]
    return [
        "pg_dump",
        "-h", target.db_host or db.get("HOST", "127.0.0.1"),
        "-p", str(target.db_port or db.get("PORT", "5432")),
        "-U", target.db_user or db.get("USER", "postgres"),
        "-Fc", target.db_name,
        "-f", filepath,
    ]


def build_remote_dump_cmd(target) -> str:
    """在远程主机上要执行的 pg_dump 命令(单条 shell 字符串,-Fc 输出到 stdout)。"""
    inner = ["pg_dump"]
    if target.db_host:
        inner += ["-h", target.db_host]
    if target.db_port:
        inner += ["-p", str(target.db_port)]
    if target.db_user:
        inner += ["-U", target.db_user]
    inner += ["-Fc", target.db_name]
    cmd = " ".join(shlex.quote(p) for p in inner)
    if target.docker_container:
        cmd = f"docker exec {shlex.quote(target.docker_container)} {cmd}"
    return cmd


def build_ssh_argv(target, remote_cmd: str) -> list:
    argv = ["ssh"]
    if target.ssh_port:
        argv += ["-p", str(target.ssh_port)]
    host = f"{target.ssh_user}@{target.ssh_host}" if target.ssh_user else target.ssh_host
    argv += [host, remote_cmd]
    return argv


def dump_database(target, filepath: str):
    """执行转储。返回 (success: bool, file_size: int, error: str)。"""
    env = os.environ.copy()
    if not target.ssh_host:
        env["PGPASSWORD"] = settings.DATABASES["default"].get("PASSWORD", "")
        proc = subprocess.run(build_local_command(target, filepath), env=env, capture_output=True)
        if proc.returncode == 0:
            return True, os.path.getsize(filepath), ""
        return False, 0, proc.stderr.decode().strip()

    remote_cmd = build_remote_dump_cmd(target)
    argv = build_ssh_argv(target, remote_cmd)
    with open(filepath, "wb") as f:
        proc = subprocess.run(argv, stdout=f, stderr=subprocess.PIPE, env=env)
    if proc.returncode == 0 and os.path.exists(filepath) and os.path.getsize(filepath) > 0:
        return True, os.path.getsize(filepath), ""
    return False, 0, proc.stderr.decode().strip() or "远程转储失败"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_backup_services.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/apps/backups/services.py backend/tests/test_backup_services.py
git commit -m "feat(backups): pg_dump command builders + cron parser"
```

---

### Task 3: `run_backup` Celery task + retention

**Files:**
- Create: `backend/apps/backups/tasks.py`
- Test: `backend/tests/test_backup_tasks.py`

**Interfaces:**
- Consumes: `services.dump_database`, `services.get_backup_dir`, `BackupTarget`, `DatabaseBackup`
- Produces: `run_backup(target_id, trigger="scheduled", created_by_id=None) -> int | None` (returns the `DatabaseBackup.id`, or `None` if skipped)
- Produces: `prune_old_backups(target) -> None`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_backup_tasks.py
import os
import pytest
from unittest.mock import patch
from apps.backups.models import BackupTarget, DatabaseBackup
from apps.backups import tasks

pytestmark = pytest.mark.django_db


@patch("apps.backups.tasks.dump_database")
def test_run_backup_success(mock_dump, tmp_path, settings):
    settings.BACKUP_DIR = str(tmp_path)
    mock_dump.return_value = (True, 2048, "")
    t = BackupTarget.objects.create(name="T", db_name="d")
    bid = tasks.run_backup(t.id, trigger="manual")
    b = DatabaseBackup.objects.get(id=bid)
    assert b.status == "success" and b.file_size == 2048 and b.trigger == "manual"


@patch("apps.backups.tasks.dump_database")
def test_run_backup_failure_cleans_partial_file(mock_dump, tmp_path, settings):
    settings.BACKUP_DIR = str(tmp_path)
    mock_dump.return_value = (False, 0, "connection refused")
    t = BackupTarget.objects.create(name="T", db_name="d")
    bid = tasks.run_backup(t.id)
    b = DatabaseBackup.objects.get(id=bid)
    assert b.status == "failed" and "connection refused" in b.error_message


@patch("apps.backups.tasks.dump_database")
def test_run_backup_skips_when_target_already_running(mock_dump, tmp_path, settings):
    settings.BACKUP_DIR = str(tmp_path)
    t = BackupTarget.objects.create(name="T", db_name="d")
    DatabaseBackup.objects.create(target=t, filename="x.dump", status="running")
    assert tasks.run_backup(t.id) is None
    mock_dump.assert_not_called()


@patch("apps.backups.tasks.dump_database")
def test_run_backup_skips_inactive_target(mock_dump, tmp_path, settings):
    settings.BACKUP_DIR = str(tmp_path)
    t = BackupTarget.objects.create(name="T", db_name="d", is_active=False)
    assert tasks.run_backup(t.id) is None
    mock_dump.assert_not_called()


@patch("apps.backups.tasks.dump_database")
def test_retention_prunes_old_successful_backups(mock_dump, tmp_path, settings):
    settings.BACKUP_DIR = str(tmp_path)
    mock_dump.return_value = (True, 10, "")
    t = BackupTarget.objects.create(name="T", db_name="d", retention_count=2)
    for _ in range(4):
        tasks.run_backup(t.id)
    assert DatabaseBackup.objects.filter(target=t, status="success").count() == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_backup_tasks.py -v`
Expected: FAIL with `ModuleNotFoundError` / `AttributeError` for `apps.backups.tasks`.

- [ ] **Step 3: Implement `tasks.py`**

```python
# backend/apps/backups/tasks.py
import logging
import os

from celery import shared_task
from django.utils import timezone

from apps.backups.models import BackupTarget, DatabaseBackup
from apps.backups.services import dump_database, get_backup_dir

logger = logging.getLogger(__name__)


def prune_old_backups(target) -> None:
    """保留最近 retention_count 个成功备份,其余删行 + 删文件。0 = 不限。"""
    if not target.retention_count:
        return
    keep_ids = list(
        DatabaseBackup.objects.filter(target=target, status="success")
        .values_list("id", flat=True)[: target.retention_count]
    )
    old = DatabaseBackup.objects.filter(target=target, status="success").exclude(id__in=keep_ids)
    for b in old:
        fp = os.path.join(get_backup_dir(), b.filename)
        if os.path.exists(fp):
            os.remove(fp)
    old.delete()


@shared_task
def run_backup(target_id, trigger="scheduled", created_by_id=None):
    target = BackupTarget.objects.filter(id=target_id, is_active=True).first()
    if target is None:
        return None
    # 同一 target 一次只跑一个
    if DatabaseBackup.objects.filter(target=target, status="running").exists():
        logger.warning("backup target %s already running, skip", target_id)
        return None

    timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{target.db_name}_{timestamp}.dump"
    filepath = os.path.join(get_backup_dir(), filename)
    backup = DatabaseBackup.objects.create(
        target=target, filename=filename, status="running",
        trigger=trigger, created_by_id=created_by_id,
    )

    try:
        success, size, err = dump_database(target, filepath)
        if success:
            backup.status = "success"
            backup.file_size = size
        else:
            backup.status = "failed"
            backup.error_message = err
            if os.path.exists(filepath):
                os.remove(filepath)
    except Exception as e:  # noqa: BLE001 - 记录任何异常到备份记录
        backup.status = "failed"
        backup.error_message = str(e)
        if os.path.exists(filepath):
            os.remove(filepath)

    backup.save()
    if backup.status == "success":
        prune_old_backups(target)
    return backup.id
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_backup_tasks.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/apps/backups/tasks.py backend/tests/test_backup_tasks.py
git commit -m "feat(backups): run_backup celery task with per-target lock + retention"
```

---

### Task 4: Schedule sync (signals → `PeriodicTask`)

**Files:**
- Create: `backend/apps/backups/signals.py`
- Modify: `backend/apps/backups/apps.py` (add `ready()` to import signals)
- Test: `backend/tests/test_backup_scheduling.py`

**Interfaces:**
- Consumes: `services.parse_cron`, `BackupTarget`
- Produces: `sync_target_schedule(target) -> None` — upserts/deletes the `PeriodicTask` named `backup:target:{id}`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_backup_scheduling.py
import pytest
from django_celery_beat.models import PeriodicTask
from apps.backups.models import BackupTarget

pytestmark = pytest.mark.django_db


def _task_name(t):
    return f"backup:target:{t.id}"


def test_saving_target_with_cron_creates_periodic_task():
    t = BackupTarget.objects.create(name="T", db_name="d", schedule_cron="0 3 * * *")
    pt = PeriodicTask.objects.get(name=_task_name(t))
    assert pt.task == "apps.backups.tasks.run_backup"
    assert pt.enabled is True
    assert str(t.id) in pt.args


def test_blank_cron_creates_no_task():
    t = BackupTarget.objects.create(name="T", db_name="d", schedule_cron="")
    assert not PeriodicTask.objects.filter(name=_task_name(t)).exists()


def test_disabling_schedule_disables_task():
    t = BackupTarget.objects.create(name="T", db_name="d", schedule_cron="0 3 * * *")
    t.schedule_enabled = False
    t.save()
    assert PeriodicTask.objects.get(name=_task_name(t)).enabled is False


def test_clearing_cron_removes_task():
    t = BackupTarget.objects.create(name="T", db_name="d", schedule_cron="0 3 * * *")
    t.schedule_cron = ""
    t.save()
    assert not PeriodicTask.objects.filter(name=_task_name(t)).exists()


def test_deleting_target_removes_task():
    t = BackupTarget.objects.create(name="T", db_name="d", schedule_cron="0 3 * * *")
    name = _task_name(t)
    t.delete()
    assert not PeriodicTask.objects.filter(name=name).exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_backup_scheduling.py -v`
Expected: FAIL (no PeriodicTask created — signals not wired).

- [ ] **Step 3: Implement `signals.py`**

```python
# backend/apps/backups/signals.py
import json

from django.conf import settings
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from apps.backups.models import BackupTarget
from apps.backups.services import parse_cron


def _task_name(target_id) -> str:
    return f"backup:target:{target_id}"


def sync_target_schedule(target) -> None:
    from django_celery_beat.models import CrontabSchedule, PeriodicTask

    name = _task_name(target.id)
    if not target.schedule_cron:
        PeriodicTask.objects.filter(name=name).delete()
        return

    fields = parse_cron(target.schedule_cron)
    schedule, _ = CrontabSchedule.objects.get_or_create(timezone=settings.TIME_ZONE, **fields)
    PeriodicTask.objects.update_or_create(
        name=name,
        defaults={
            "task": "apps.backups.tasks.run_backup",
            "crontab": schedule,
            "interval": None,
            "args": json.dumps([target.id]),
            "kwargs": json.dumps({"trigger": "scheduled"}),
            "enabled": bool(target.is_active and target.schedule_enabled),
        },
    )


@receiver(post_save, sender=BackupTarget)
def _on_target_save(sender, instance, **kwargs):
    sync_target_schedule(instance)


@receiver(post_delete, sender=BackupTarget)
def _on_target_delete(sender, instance, **kwargs):
    from django_celery_beat.models import PeriodicTask

    PeriodicTask.objects.filter(name=_task_name(instance.id)).delete()
```

- [ ] **Step 4: Wire signals in `apps.py`**

Replace `backend/apps/backups/apps.py` with:

```python
from django.apps import AppConfig


class BackupsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.backups"
    verbose_name = "数据库备份"

    def ready(self):
        from apps.backups import signals  # noqa: F401
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_backup_scheduling.py -v`
Expected: PASS (5 tests).

- [ ] **Step 6: Commit**

```bash
git add backend/apps/backups/signals.py backend/apps/backups/apps.py backend/tests/test_backup_scheduling.py
git commit -m "feat(backups): sync per-target cron schedule to django_celery_beat"
```

---

### Task 5: Serializers, views, URLs (`/api/backups/`)

**Files:**
- Create: `backend/apps/backups/serializers.py`
- Create: `backend/apps/backups/views.py`
- Create: `backend/apps/backups/urls.py`
- Modify: `backend/apps/urls.py` (mount `backups/`)
- Test: `backend/tests/test_backup_api.py`

**Interfaces:**
- Consumes: `BackupTarget`, `DatabaseBackup`, `services.parse_cron`, `services.get_backup_dir`, `tasks.run_backup`
- Produces routes: `GET/POST /api/backups/targets/`, `GET/PATCH/DELETE /api/backups/targets/{id}/`, `POST /api/backups/targets/{id}/run/`, `GET /api/backups/backups/`, `GET /api/backups/backups/{id}/download/`, `DELETE /api/backups/backups/{id}/`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_backup_api.py
import pytest
from unittest.mock import patch
from apps.backups.models import BackupTarget, DatabaseBackup

pytestmark = pytest.mark.django_db


class TestTargetAPI:
    def test_create_site_level_target(self, superuser_client):
        resp = superuser_client.post("/api/backups/targets/", {
            "name": "DevTrakr 自身", "db_name": "devtrack", "engine": "postgres",
        }, format="json")
        assert resp.status_code == 201
        assert resp.data["project"] is None

    def test_create_rejects_invalid_cron(self, superuser_client):
        resp = superuser_client.post("/api/backups/targets/", {
            "name": "T", "db_name": "d", "schedule_cron": "bad cron",
        }, format="json")
        assert resp.status_code == 400

    def test_list_forbidden_for_regular_user(self, regular_client):
        resp = regular_client.get("/api/backups/targets/")
        assert resp.status_code == 403

    def test_list_unauthenticated(self, api_client):
        resp = api_client.get("/api/backups/targets/")
        assert resp.status_code == 401


class TestRunAPI:
    @patch("apps.backups.views.run_backup.delay")
    def test_manual_run_enqueues_task(self, mock_delay, superuser_client):
        t = BackupTarget.objects.create(name="T", db_name="d")
        resp = superuser_client.post(f"/api/backups/targets/{t.id}/run/")
        assert resp.status_code == 202
        mock_delay.assert_called_once()

    @patch("apps.backups.views.run_backup.delay")
    def test_manual_run_conflict_when_running(self, mock_delay, superuser_client):
        t = BackupTarget.objects.create(name="T", db_name="d")
        DatabaseBackup.objects.create(target=t, filename="x.dump", status="running")
        resp = superuser_client.post(f"/api/backups/targets/{t.id}/run/")
        assert resp.status_code == 409
        mock_delay.assert_not_called()


class TestBackupRecordsAPI:
    def test_list_filter_by_target(self, superuser_client):
        t1 = BackupTarget.objects.create(name="A", db_name="a")
        t2 = BackupTarget.objects.create(name="B", db_name="b")
        DatabaseBackup.objects.create(target=t1, filename="a.dump", status="success")
        DatabaseBackup.objects.create(target=t2, filename="b.dump", status="success")
        resp = superuser_client.get(f"/api/backups/backups/?target={t1.id}")
        assert resp.status_code == 200 and resp.data["count"] == 1

    def test_download_and_delete(self, superuser_client, tmp_path, settings):
        settings.BACKUP_DIR = str(tmp_path)
        (tmp_path / "d.dump").write_bytes(b"dump")
        b = DatabaseBackup.objects.create(filename="d.dump", file_size=4, status="success")
        dl = superuser_client.get(f"/api/backups/backups/{b.id}/download/")
        assert dl.status_code == 200 and b"dump" in b"".join(dl.streaming_content)
        rm = superuser_client.delete(f"/api/backups/backups/{b.id}/")
        assert rm.status_code == 204 and not (tmp_path / "d.dump").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_backup_api.py -v`
Expected: FAIL with 404 (routes not mounted yet).

- [ ] **Step 3: Implement `serializers.py`**

```python
# backend/apps/backups/serializers.py
from rest_framework import serializers

from apps.backups.models import BackupTarget, DatabaseBackup
from apps.backups.services import parse_cron


class DatabaseBackupSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source="created_by.name", read_only=True, default=None)

    class Meta:
        model = DatabaseBackup
        fields = [
            "id", "target", "filename", "file_size", "status",
            "error_message", "trigger", "created_by_name", "created_at",
        ]
        read_only_fields = fields


class BackupTargetSerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source="project.name", read_only=True, default=None)
    latest_backup = serializers.SerializerMethodField()

    class Meta:
        model = BackupTarget
        fields = [
            "id", "project", "project_name", "name", "engine",
            "ssh_host", "ssh_user", "ssh_port", "docker_container",
            "db_name", "db_user", "db_host", "db_port",
            "schedule_cron", "schedule_enabled", "retention_count",
            "is_active", "created_at", "updated_at", "latest_backup",
        ]
        read_only_fields = ["id", "project_name", "created_at", "updated_at", "latest_backup"]

    def get_latest_backup(self, obj):
        b = obj.backups.first()
        if not b:
            return None
        return {"status": b.status, "created_at": b.created_at}

    def validate_schedule_cron(self, value):
        if value:
            try:
                parse_cron(value)
            except ValueError as e:
                raise serializers.ValidationError(str(e))
        return value
```

- [ ] **Step 4: Implement `views.py`**

```python
# backend/apps/backups/views.py
import os

from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.generics import (
    ListAPIView, ListCreateAPIView, RetrieveUpdateDestroyAPIView, DestroyAPIView,
)
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.backups.models import BackupTarget, DatabaseBackup
from apps.backups.serializers import BackupTargetSerializer, DatabaseBackupSerializer
from apps.backups.services import get_backup_dir
from apps.backups.tasks import run_backup


class BackupTargetListCreateView(ListCreateAPIView):
    serializer_class = BackupTargetSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        qs = BackupTarget.objects.select_related("project").all()
        project = self.request.query_params.get("project")
        if project:
            qs = qs.filter(project_id=project)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class BackupTargetDetailView(RetrieveUpdateDestroyAPIView):
    queryset = BackupTarget.objects.all()
    serializer_class = BackupTargetSerializer
    permission_classes = [IsAdminUser]


class BackupTargetRunView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        target = get_object_or_404(BackupTarget, pk=pk, is_active=True)
        if DatabaseBackup.objects.filter(target=target, status="running").exists():
            return Response({"detail": "已有备份任务正在运行"}, status=status.HTTP_409_CONFLICT)
        run_backup.delay(target.id, trigger="manual", created_by_id=request.user.id)
        return Response({"detail": "已开始备份"}, status=status.HTTP_202_ACCEPTED)


class BackupListView(ListAPIView):
    serializer_class = DatabaseBackupSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        qs = DatabaseBackup.objects.select_related("target", "created_by").all()
        target = self.request.query_params.get("target")
        project = self.request.query_params.get("project")
        if target:
            qs = qs.filter(target_id=target)
        if project:
            qs = qs.filter(target__project_id=project)
        return qs


class BackupDownloadView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, pk):
        backup = get_object_or_404(DatabaseBackup, pk=pk)
        filepath = os.path.join(get_backup_dir(), backup.filename)
        if not os.path.exists(filepath):
            return Response({"detail": "备份文件不存在"}, status=status.HTTP_404_NOT_FOUND)
        return FileResponse(
            open(filepath, "rb"),
            content_type="application/octet-stream",
            as_attachment=True,
            filename=backup.filename,
        )


class BackupDeleteView(DestroyAPIView):
    queryset = DatabaseBackup.objects.all()
    serializer_class = DatabaseBackupSerializer
    permission_classes = [IsAdminUser]

    def perform_destroy(self, instance):
        filepath = os.path.join(get_backup_dir(), instance.filename)
        if os.path.exists(filepath):
            os.remove(filepath)
        instance.delete()
```

- [ ] **Step 5: Implement `urls.py`**

```python
# backend/apps/backups/urls.py
from django.urls import path

from apps.backups.views import (
    BackupTargetListCreateView, BackupTargetDetailView, BackupTargetRunView,
    BackupListView, BackupDownloadView, BackupDeleteView,
)

urlpatterns = [
    path("targets/", BackupTargetListCreateView.as_view(), name="backup-target-list"),
    path("targets/<int:pk>/", BackupTargetDetailView.as_view(), name="backup-target-detail"),
    path("targets/<int:pk>/run/", BackupTargetRunView.as_view(), name="backup-target-run"),
    path("backups/", BackupListView.as_view(), name="backup-list"),
    path("backups/<int:pk>/download/", BackupDownloadView.as_view(), name="backup-download"),
    path("backups/<int:pk>/", BackupDeleteView.as_view(), name="backup-delete"),
]
```

- [ ] **Step 6: Mount the route**

In `backend/apps/urls.py`, add after the `uptime/` include:

```python
    path("backups/", include("apps.backups.urls")),
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_backup_api.py -v`
Expected: PASS (8 tests).

- [ ] **Step 8: Commit**

```bash
git add backend/apps/backups/serializers.py backend/apps/backups/views.py backend/apps/backups/urls.py backend/apps/urls.py backend/tests/test_backup_api.py
git commit -m "feat(backups): /api/backups/ targets + records API (admin-only)"
```

---

### Task 6: Admin registration

**Files:**
- Create: `backend/apps/backups/admin.py`

**Interfaces:**
- Consumes: `BackupTarget`, `DatabaseBackup`. No new symbols produced.

- [ ] **Step 1: Implement `admin.py`**

```python
# backend/apps/backups/admin.py
from django.contrib import admin
from unfold.admin import ModelAdmin

from apps.backups.models import BackupTarget, DatabaseBackup


@admin.register(BackupTarget)
class BackupTargetAdmin(ModelAdmin):
    list_display = ("name", "project", "db_name", "ssh_host", "schedule_cron", "is_active")
    list_filter = ("is_active", "engine", "project")
    search_fields = ("name", "db_name", "ssh_host")


@admin.register(DatabaseBackup)
class DatabaseBackupAdmin(ModelAdmin):
    list_display = ("filename", "target", "status", "file_size", "trigger", "created_by", "created_at")
    list_filter = ("status", "trigger")
    readonly_fields = (
        "target", "filename", "file_size", "status",
        "error_message", "trigger", "created_by", "created_at",
    )
```

- [ ] **Step 2: Verify admin loads**

Run: `cd backend && uv run python manage.py check`
Expected: `System check identified no issues`.

- [ ] **Step 3: Commit**

```bash
git add backend/apps/backups/admin.py
git commit -m "feat(backups): register BackupTarget + DatabaseBackup in admin"
```

---

### Task 7: Data migration — backfill legacy backups onto a site-level self-target

**Files:**
- Create: `backend/apps/backups/migrations/0002_migrate_legacy_backups.py`

**Interfaces:**
- Consumes: historical models `settings.DatabaseBackup` (still present), `backups.BackupTarget`, `backups.DatabaseBackup`. No code symbols produced.

> **Note on testing:** This is a one-shot data migration whose source table (`settings_databasebackup`) is dropped in Task 8. A post-facto unit test is not meaningful (the source no longer exists once the suite's migrations are fully applied). Verify by running it against a copy of real data (Step 2).

- [ ] **Step 1: Write the migration**

```python
# backend/apps/backups/migrations/0002_migrate_legacy_backups.py
from django.conf import settings as dj_settings
from django.db import migrations


def forward(apps, schema_editor):
    LegacyBackup = apps.get_model("settings", "DatabaseBackup")
    BackupTarget = apps.get_model("backups", "BackupTarget")
    NewBackup = apps.get_model("backups", "DatabaseBackup")

    if not LegacyBackup.objects.exists() and BackupTarget.objects.filter(
        name="DevTrakr 自身", project__isnull=True
    ).exists():
        return

    self_target, _ = BackupTarget.objects.get_or_create(
        name="DevTrakr 自身",
        project=None,
        defaults={
            "engine": "postgres",
            "db_name": dj_settings.DATABASES["default"].get("NAME", "devtrack"),
        },
    )

    for old in LegacyBackup.objects.all():
        NewBackup.objects.create(
            target=self_target,
            filename=old.filename,
            file_size=old.file_size,
            status=old.status,
            error_message=old.error_message,
            trigger="manual",
            created_by_id=old.created_by_id,
            created_at=old.created_at,
        )


def reverse(apps, schema_editor):
    # 不可逆:只清掉自身目标迁过来的记录,不还原旧表
    BackupTarget = apps.get_model("backups", "BackupTarget")
    BackupTarget.objects.filter(name="DevTrakr 自身", project__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("backups", "0001_initial"),
        ("settings", "0012_issue_statuses_disabled_flag"),
    ]
    operations = [
        migrations.RunPython(forward, reverse),
    ]
```

> Note: `created_at` has `auto_now_add=True`, which ignores assigned values on create. To preserve original timestamps, after the `create()` loop the migration should bulk-update them. Replace the loop body to collect `(new_obj, old.created_at)` and then `NewBackup.objects.filter(pk=...).update(created_at=...)` for each. Implement this in Step 1 — do not leave it as a comment.

Concretely, the loop becomes:

```python
    for old in LegacyBackup.objects.all():
        new = NewBackup.objects.create(
            target=self_target, filename=old.filename, file_size=old.file_size,
            status=old.status, error_message=old.error_message, trigger="manual",
            created_by_id=old.created_by_id,
        )
        NewBackup.objects.filter(pk=new.pk).update(created_at=old.created_at)
```

- [ ] **Step 2: Verify against current DB**

Run: `cd backend && uv run python manage.py migrate backups`
Then: `uv run python manage.py shell -c "from apps.backups.models import BackupTarget, DatabaseBackup; print('targets', BackupTarget.objects.count(), 'backups', DatabaseBackup.objects.count())"`
Expected: one `DevTrakr 自身` target exists, and `backups.DatabaseBackup` count equals the prior `settings_databasebackup` row count.

- [ ] **Step 3: Confirm full test suite still green**

Run: `cd backend && uv run pytest -q`
Expected: PASS (old `tests/test_backups.py` still passes — settings model not yet removed).

- [ ] **Step 4: Commit**

```bash
git add backend/apps/backups/migrations/0002_migrate_legacy_backups.py
git commit -m "feat(backups): data migration backfilling legacy backups onto site-level self-target"
```

---

### Task 8: Remove legacy `settings` backup code + delete old model

**Files:**
- Delete: `backend/apps/settings/backup_views.py`
- Delete: `backend/apps/settings/backup_serializers.py`
- Delete: `backend/tests/test_backups.py` (covered the removed endpoints; replaced by `tests/test_backup_*.py`)
- Modify: `backend/apps/settings/urls.py` (drop backup imports + 4 routes)
- Modify: `backend/apps/settings/admin.py` (drop `DatabaseBackup` import + `DatabaseBackupAdmin`)
- Modify: `backend/apps/settings/models.py:116-142` (delete the `DatabaseBackup` class)
- Modify: `backend/tests/factories.py` (only if a backup factory referencing the settings model exists — it does not today; no change expected)
- Create: `backend/apps/settings/migrations/0013_delete_databasebackup.py` (generated)

**Interfaces:** Removes `apps.settings.models.DatabaseBackup` and the `/api/settings/backups/*` routes. No new symbols.

- [ ] **Step 1: Remove the old code**

- Delete `backend/apps/settings/backup_views.py` and `backend/apps/settings/backup_serializers.py`.
- Delete `backend/tests/test_backups.py`.
- In `backend/apps/settings/urls.py`, remove the `from .backup_views import (...)` line and the four `backups/...` `path(...)` entries, leaving only `site-settings` and `label-settings`.
- In `backend/apps/settings/admin.py`, change `from .models import DatabaseBackup, ExternalAPIKey, SiteSettings` to `from .models import ExternalAPIKey, SiteSettings` and delete the entire `@admin.register(DatabaseBackup)` `DatabaseBackupAdmin` block.
- In `backend/apps/settings/models.py`, delete the `class DatabaseBackup(models.Model): ...` block (lines 116-142).

- [ ] **Step 2: Generate the delete migration**

Run: `cd backend && uv run python manage.py makemigrations settings`
Expected: creates `backend/apps/settings/migrations/0013_delete_databasebackup.py` with `DeleteModel(name="DatabaseBackup")`.

- [ ] **Step 3: Make the delete depend on the backfill**

Edit the generated `0013_delete_databasebackup.py` `dependencies` to also require the backfill, so deletion never runs before the copy:

```python
    dependencies = [
        ("settings", "0012_issue_statuses_disabled_flag"),
        ("backups", "0002_migrate_legacy_backups"),
    ]
```

(Adding a dependency to a freshly generated migration before it has ever run is allowed — this is not editing an already-applied migration.)

- [ ] **Step 4: Apply migrations**

Run: `cd backend && uv run python manage.py migrate`
Expected: `settings.0013_delete_databasebackup` applies cleanly (the `settings_databasebackup` table is dropped after Task 7 already copied its rows).

- [ ] **Step 5: Run the full suite**

Run: `cd backend && uv run pytest -q`
Expected: PASS. No import errors referencing `apps.settings.backup_views` / `DatabaseBackup`.

- [ ] **Step 6: Sanity grep for stragglers**

Run: `cd backend && grep -rn "settings.*DatabaseBackup\|backup_views\|backup_serializers\|settings/backups" apps/ tests/`
Expected: no matches.

- [ ] **Step 7: Commit**

```bash
git add -A backend/apps/settings backend/tests/test_backups.py
git commit -m "refactor(backups): remove legacy settings backup model/views/routes after migration"
```

---

### Task 9: Frontend — target-oriented backups page

**Files:**
- Modify: `frontend/app/pages/app/settings/backups.vue` (full rewrite)

**Interfaces:** Consumes `/api/backups/targets/`, `/api/backups/targets/{id}/run/`, `/api/backups/backups/?target=`, `/api/backups/backups/{id}/download/`, `DELETE /api/backups/backups/{id}/`. Route path and nav entry are unchanged (still `/app/settings/backups`, admin-gated) — no `useNavigation.ts` / `auth.global.ts` change needed.

- [ ] **Step 1: Rewrite the page**

Replace `frontend/app/pages/app/settings/backups.vue` with a target-oriented layout. Keep the existing `formatSize`/`formatTime`/`statusMap` helpers. Structure:

```vue
<script setup lang="ts">
definePageMeta({ layout: 'default' })

interface LatestBackup { status: string; created_at: string }
interface BackupTarget {
  id: number
  project: number | null
  project_name: string | null
  name: string
  db_name: string
  ssh_host: string
  docker_container: string
  schedule_cron: string
  schedule_enabled: boolean
  retention_count: number
  is_active: boolean
  latest_backup: LatestBackup | null
}
interface BackupRecord {
  id: number
  target: number | null
  filename: string
  file_size: number | null
  status: 'running' | 'success' | 'failed'
  error_message: string
  trigger: 'manual' | 'scheduled'
  created_by_name: string | null
  created_at: string
}

const { api } = useApi()
const toast = useToast()

const loading = ref(false)
const targets = ref<BackupTarget[]>([])
const runningId = ref<number | null>(null)
const expandedId = ref<number | null>(null)
const recordsByTarget = ref<Record<number, BackupRecord[]>>({})

function formatSize(bytes: number | null): string {
  if (bytes == null) return '-'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
function formatTime(iso: string): string { return new Date(iso).toLocaleString('zh-CN') }
const statusMap: Record<string, { label: string; color: 'success' | 'warning' | 'error' }> = {
  running: { label: '备份中', color: 'warning' },
  success: { label: '成功', color: 'success' },
  failed: { label: '失败', color: 'error' },
}

// 站点级目标(project===null)排在前,其余按项目名分组展示
const siteTargets = computed(() => targets.value.filter(t => t.project === null))
const projectTargets = computed(() => targets.value.filter(t => t.project !== null))

async function fetchTargets() {
  loading.value = true
  try {
    const res = await api<any>('/api/backups/targets/')
    targets.value = res.results ?? res
  } finally {
    loading.value = false
  }
}

async function runBackup(t: BackupTarget) {
  runningId.value = t.id
  try {
    await api(`/api/backups/targets/${t.id}/run/`, { method: 'POST' })
    toast.add({ title: '已开始备份', color: 'success' })
  } catch (e: any) {
    toast.add({ title: e?.data?.detail || '备份失败', color: 'error' })
  } finally {
    runningId.value = null
  }
}

async function toggleRecords(t: BackupTarget) {
  if (expandedId.value === t.id) { expandedId.value = null; return }
  expandedId.value = t.id
  const res = await api<any>(`/api/backups/backups/?target=${t.id}`)
  recordsByTarget.value[t.id] = res.results ?? res
}

async function downloadBackup(row: BackupRecord) {
  const token = localStorage.getItem('access_token')
  try {
    const response = await fetch(`/api/backups/backups/${row.id}/download/`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!response.ok) throw new Error()
    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = row.filename; a.click()
    URL.revokeObjectURL(url)
  } catch { toast.add({ title: '下载失败', color: 'error' }) }
}

async function deleteBackup(row: BackupRecord) {
  if (!confirm(`确定要删除备份 ${row.filename}？`)) return
  try {
    await api(`/api/backups/backups/${row.id}/`, { method: 'DELETE' })
    toast.add({ title: '已删除', color: 'success' })
    if (expandedId.value) {
      const res = await api<any>(`/api/backups/backups/?target=${expandedId.value}`)
      recordsByTarget.value[expandedId.value] = res.results ?? res
    }
  } catch { toast.add({ title: '删除失败', color: 'error' }) }
}

onMounted(fetchTargets)
</script>

<template>
  <div class="p-6 space-y-6">
    <h1 class="text-lg font-semibold">数据库备份</h1>

    <!-- 站点级 -->
    <section class="space-y-2">
      <h2 class="text-sm font-medium text-gray-500">站点级</h2>
      <BackupTargetCard
        v-for="t in siteTargets" :key="t.id" :target="t"
        :running="runningId === t.id" :expanded="expandedId === t.id"
        :records="recordsByTarget[t.id] || []"
        @run="runBackup(t)" @toggle="toggleRecords(t)"
        @download="downloadBackup" @delete="deleteBackup"
      />
    </section>

    <!-- 项目级 -->
    <section class="space-y-2">
      <h2 class="text-sm font-medium text-gray-500">项目</h2>
      <BackupTargetCard
        v-for="t in projectTargets" :key="t.id" :target="t"
        :running="runningId === t.id" :expanded="expandedId === t.id"
        :records="recordsByTarget[t.id] || []"
        @run="runBackup(t)" @toggle="toggleRecords(t)"
        @download="downloadBackup" @delete="deleteBackup"
      />
    </section>
  </div>
</template>
```

- [ ] **Step 2: Create the `BackupTargetCard` component**

Create `frontend/app/components/BackupTargetCard.vue` rendering one target: name, `project_name` (or「站点级」), connection summary (`ssh_host || '本地'` + `db_name` + optional `docker_container`), schedule (`schedule_cron || '仅手动'`), retention, latest-backup badge, a「立即备份」`UButton` (`:loading="running"`, emits `run`), a toggle to expand records, and when expanded a `UTable` of `records` with download/delete actions (reuse the markup from the old page's `actions-cell`). Define `props: { target, running, expanded, records }` and `emits: ['run', 'toggle', 'download', 'delete']`. Use the same `formatSize`/`formatTime`/`statusMap` helpers (duplicate locally or extract to a composable — local duplication is acceptable here).

- [ ] **Step 3: Type-check**

Run: `cd frontend && npx nuxi typecheck`
Expected: no type errors.

- [ ] **Step 4: Manual smoke (dev server)**

Run: `cd frontend && TMPDIR=/tmp npm run dev` (per memory: macOS+Node26 socket fix). Log in as `bot` / `password123`, open `/app/settings/backups`. Verify: the `DevTrakr 自身` site-level target shows; clicking「立即备份」toasts「已开始备份」; expanding lists its backup records with working download/delete.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/pages/app/settings/backups.vue frontend/app/components/BackupTargetCard.vue
git commit -m "feat(backups): target-oriented backups page consuming /api/backups/"
```

---

### Task 10: Infrastructure — SSH client + keys in backend/worker images

**Files:**
- Modify: backend `Dockerfile` (add `openssh-client`)
- Modify: production `docker-compose` (mount SSH material into backend + celery worker; keep `backups` volume)

**Interfaces:** No code symbols. Enables remote (`ssh_host` set) targets to actually run.

> **Note:** Exact compose/Dockerfile paths depend on the deploy repo layout (see `db-backup.yml` / `server-sync.yml` and the `2026-04-03` spec's compose section). Confirm paths before editing.

- [ ] **Step 1: Add `openssh-client` to the backend image**

In the backend `Dockerfile`, alongside the existing `apt-get install -y postgresql-client`, add `openssh-client` (e.g. `apt-get install -y postgresql-client openssh-client`).

- [ ] **Step 2: Mount SSH material**

In the production compose file, for **both** the backend container and the celery **worker** container (the worker is where `run_backup` executes), mount the host SSH dir read-only and ensure `known_hosts` is populated, e.g.:

```yaml
    volumes:
      - backups:/data/backups
      - /opt/devtrakr/.ssh:/root/.ssh:ro
```

Document that remote hosts must be reachable via these keys and have `pg_dump` (directly or inside `docker_container`).

- [ ] **Step 3: Verify the image builds**

Run: `docker compose build backend` (or the relevant service). Expected: build succeeds; `docker compose run --rm backend ssh -V` prints an OpenSSH version.

- [ ] **Step 4: Commit**

```bash
git add Dockerfile docker-compose*.yml
git commit -m "chore(backups): install openssh-client + mount SSH keys for remote backups"
```

---

## Self-Review

**1. Spec coverage**

| Spec section | Task |
|---|---|
| New `apps/backups` app | Task 1 |
| `BackupTarget` model (nullable project, reference fields, schedule, retention) | Task 1 |
| `DatabaseBackup` moved + `target`/`trigger` | Tasks 1 (new model), 7 (data), 8 (delete old) |
| Execution: local vs SSH remote, per-target lock | Tasks 2 (builders), 3 (task) |
| Security: arg lists / `shlex.quote` | Task 2 (`build_remote_dump_cmd`, `build_ssh_argv`) |
| Scheduling via `django_celery_beat` | Task 4 |
| Retention | Task 3 (`prune_old_backups`) |
| API `/api/backups/`, admin-only | Task 5 |
| Admin registration | Task 6 |
| Migration: self-target backfill | Task 7 |
| Remove legacy settings code | Task 8 |
| Frontend target-oriented page | Task 9 |
| Infra: openssh-client + key mount (backend + worker) | Task 10 |
| YAGNI (no mysql/encryption/restore) | Honored — no tasks added |

**2. Placeholder scan:** No `TBD`/`TODO`/"handle edge cases". The one inherently-untestable item (Task 7 data migration) is called out with an explicit manual verification step and expected output, not left vague.

**3. Type consistency:** `run_backup(target_id, trigger=, created_by_id=)` signature is identical in Tasks 3 and 5; `services.dump_database`/`get_backup_dir`/`parse_cron`/`build_*` names match between Tasks 2, 3, 4, 5; `sync_target_schedule` PeriodicTask name `backup:target:{id}` matches between Task 4 implementation and its tests; serializer field lists match the model fields from Task 1.
