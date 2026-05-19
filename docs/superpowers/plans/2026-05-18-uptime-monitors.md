# Uptime Monitors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-project URL uptime monitoring to DevTrack — inline section on the project detail page, Celery-driven HTTP health checks, automatic Issue creation on outage and auto-close on recovery.

**Architecture:** New Django app `apps/uptime` owns models, tasks, serializers, views. Celery Beat tick task runs every 60s, queries due monitors and dispatches per-monitor check tasks. State machine fires Issue creation / closure side effects through `apps/issues` and `apps/notifications`. Frontend gets four new components mounted into `pages/app/projects/[id].vue` and a `formatUptime` helper. Periodic tasks are seeded via Django data migration (matches existing `apps/ai` / `apps/kpi` pattern — DB-backed `django_celery_beat` scheduler is already in use).

**Tech Stack:** Django + DRF, `requests` (HTTP), `celery` + `django-celery-beat`, `pytest-django` + `factory-boy` + `unittest.mock` (mocking — no `responses` library, not a dep), Nuxt 4 + Nuxt UI (`UModal`, `UAlertDialog`, `UInput`, `USelect`, `UButton`).

**Spec:** `docs/superpowers/specs/2026-05-18-uptime-monitors-design.md`

**Reconciliation with spec:** The spec mentioned static `CELERY_BEAT_SCHEDULE` in settings. The project actually uses `DatabaseScheduler` (see `config/settings.py:158`) and seeds periodic tasks via data migrations (see `apps/ai/migrations/0002_seed_celery_periodic_tasks.py`). This plan follows the existing convention — periodic tasks are created in a data migration, not in `CELERY_BEAT_SCHEDULE`. Settings constants for tick interval / failure threshold / retention days remain in `config/settings.py` and are referenced from task code.

**Comments-on-Issue:** The codebase has no `Comment` model on Issue. The closest equivalent is `Activity` (see `apps/issues/models.py:111`). The recovery flow creates an `Activity(action="resolved", detail="...")` instead of a comment. This is consistent with how `apps/issues/serializers.py` records status transitions.

---

## File Structure

### Backend (new files)

- `backend/apps/uptime/__init__.py` — app marker
- `backend/apps/uptime/apps.py` — `UptimeConfig`
- `backend/apps/uptime/models.py` — `UptimeMonitor`, `UptimeCheck`
- `backend/apps/uptime/admin.py` — Django Unfold admin for both models
- `backend/apps/uptime/permissions.py` — `IsSuperUserOrReadOnly`
- `backend/apps/uptime/services.py` — pure state-machine + side-effect helpers (failure / recovery actions)
- `backend/apps/uptime/http_check.py` — `perform_check(monitor)` HTTP execution
- `backend/apps/uptime/tasks.py` — `tick_uptime_monitors`, `check_monitor`, `prune_old_checks`
- `backend/apps/uptime/serializers.py` — `UptimeMonitorSerializer`, `UptimeCheckSerializer`
- `backend/apps/uptime/views.py` — list/create/retrieve/update/delete + checks endpoint
- `backend/apps/uptime/urls.py` — flat routes (`/api/uptime/...`)
- `backend/apps/uptime/migrations/0001_initial.py` — generated
- `backend/apps/uptime/migrations/0002_seed_periodic_tasks.py` — data migration
- `backend/tests/test_uptime.py` — all backend tests
- `backend/tests/factories.py` — add `UptimeMonitorFactory`, `UptimeCheckFactory` (modify existing file)

### Backend (modified files)

- `backend/config/settings.py` — add `apps.uptime` to `INSTALLED_APPS`, add uptime constants
- `backend/apps/urls.py` — mount `apps.uptime.urls` at `uptime/`
- `backend/apps/projects/urls.py` — add nested `<int:project_pk>/monitors/` route
- `backend/apps/projects/views.py` — add `ProjectMonitorsView` (list/create nested under project)

### Frontend (new files)

- `frontend/app/utils/formatUptime.ts` — pure helper, returns Chinese strings
- `frontend/app/components/projects/UptimeMonitorTimeline.vue` — timeline strip (presentational)
- `frontend/app/components/projects/UptimeMonitorRow.vue` — single row with hover actions
- `frontend/app/components/projects/UptimeMonitorFormModal.vue` — create/edit modal
- `frontend/app/components/projects/UptimeMonitorsSection.vue` — section container, data fetch + polling

### Frontend (modified files)

- `frontend/app/pages/app/projects/[id].vue` — insert `<ProjectsUptimeMonitorsSection :project-id="..." />`

---

## Task 1: Create app skeleton + register in settings

**Files:**
- Create: `backend/apps/uptime/__init__.py`
- Create: `backend/apps/uptime/apps.py`
- Create: `backend/apps/uptime/migrations/__init__.py`
- Modify: `backend/config/settings.py` (INSTALLED_APPS list, add settings constants near `# Celery` block at line 150)

- [ ] **Step 1: Create empty `__init__.py` files**

```bash
mkdir -p backend/apps/uptime/migrations
touch backend/apps/uptime/__init__.py
touch backend/apps/uptime/migrations/__init__.py
```

- [ ] **Step 2: Create `apps.py`**

`backend/apps/uptime/apps.py`:
```python
from django.apps import AppConfig


class UptimeConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.uptime"
    verbose_name = "系统监控"
```

- [ ] **Step 3: Register in INSTALLED_APPS**

In `backend/config/settings.py`, find the line `"apps.kpi",` and add `"apps.uptime",` directly after it.

- [ ] **Step 4: Add uptime settings constants**

In `backend/config/settings.py`, find the Celery block (around line 150-158, just after `CELERY_BEAT_SCHEDULER = ...`) and append:

```python

# Uptime monitoring
UPTIME_TICK_SECONDS = 60
UPTIME_FAILURE_THRESHOLD = 3
UPTIME_CHECK_RETENTION_DAYS = 30
UPTIME_DEFAULT_TIMEOUT_SECS = 20
UPTIME_SYSTEM_BOT_USERNAME = "bot"
```

- [ ] **Step 5: Verify Django still loads**

Run from `backend/`:
```bash
uv run python manage.py check
```
Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 6: Commit**

```bash
git add backend/apps/uptime/__init__.py backend/apps/uptime/apps.py backend/apps/uptime/migrations/__init__.py backend/config/settings.py
git commit -m "feat(uptime): register apps.uptime app + settings constants"
```

---

## Task 2: Models + initial migration

**Files:**
- Create: `backend/apps/uptime/models.py`

- [ ] **Step 1: Write models**

`backend/apps/uptime/models.py`:
```python
from django.db import models


class UptimeMonitor(models.Model):
    STATUS_UP = "up"
    STATUS_DOWN = "down"
    STATUS_UNKNOWN = "unknown"
    STATUS_CHOICES = [
        (STATUS_UP, "正常"),
        (STATUS_DOWN, "宕机"),
        (STATUS_UNKNOWN, "未知"),
    ]

    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="uptime_monitors",
    )
    name = models.CharField(max_length=100, verbose_name="名称")
    url = models.URLField(max_length=500, verbose_name="URL")
    method = models.CharField(max_length=10, default="GET", verbose_name="方法")
    expected_status = models.CharField(max_length=50, default="200", verbose_name="期望状态码")
    expected_body = models.CharField(max_length=200, blank=True, verbose_name="期望响应体关键字")
    interval_minutes = models.PositiveIntegerField(default=1, verbose_name="检查间隔(分钟)")
    timeout_secs = models.PositiveIntegerField(default=20, verbose_name="超时(秒)")
    is_enabled = models.BooleanField(default=True, verbose_name="启用")

    next_check_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_check_at = models.DateTimeField(null=True, blank=True)
    last_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_UNKNOWN)
    last_up_at = models.DateTimeField(null=True, blank=True)
    outage_started_at = models.DateTimeField(null=True, blank=True)
    consecutive_failures = models.PositiveIntegerField(default=0)
    active_incident_issue = models.ForeignKey(
        "issues.Issue", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "系统监控"
        verbose_name_plural = "系统监控"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.url})"


class UptimeCheck(models.Model):
    monitor = models.ForeignKey(
        UptimeMonitor, on_delete=models.CASCADE, related_name="checks",
    )
    checked_at = models.DateTimeField(db_index=True)
    is_up = models.BooleanField()
    status_code = models.PositiveIntegerField(null=True, blank=True)
    response_ms = models.PositiveIntegerField(null=True, blank=True)
    error = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name = "监控检查记录"
        verbose_name_plural = "监控检查记录"
        indexes = [
            models.Index(fields=["monitor", "-checked_at"]),
        ]
        ordering = ["-checked_at"]

    def __str__(self):
        return f"{self.monitor.name} @ {self.checked_at} {'up' if self.is_up else 'down'}"
```

- [ ] **Step 2: Generate migration**

```bash
cd backend && uv run python manage.py makemigrations uptime
```
Expected: `Migrations for 'uptime': uptime/migrations/0001_initial.py - Create model UptimeMonitor - Create model UptimeCheck`

- [ ] **Step 3: Apply migration**

```bash
cd backend && uv run python manage.py migrate uptime
```
Expected: `Applying uptime.0001_initial... OK`

- [ ] **Step 4: Commit**

```bash
git add backend/apps/uptime/models.py backend/apps/uptime/migrations/0001_initial.py
git commit -m "feat(uptime): add UptimeMonitor + UptimeCheck models"
```

---

## Task 3: Factories for tests

**Files:**
- Modify: `backend/tests/factories.py`

- [ ] **Step 1: Add factory imports**

In `backend/tests/factories.py`, locate the existing import block and add:
```python
from apps.uptime.models import UptimeMonitor, UptimeCheck
```

- [ ] **Step 2: Append factories at end of file**

Append to `backend/tests/factories.py`:
```python


class UptimeMonitorFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = UptimeMonitor

    project = factory.SubFactory(ProjectFactory)
    name = factory.Sequence(lambda n: f"monitor-{n}")
    url = factory.Sequence(lambda n: f"https://example{n}.com/health")
    method = "GET"
    expected_status = "200"
    interval_minutes = 1
    timeout_secs = 20
    is_enabled = True


class UptimeCheckFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = UptimeCheck

    monitor = factory.SubFactory(UptimeMonitorFactory)
    checked_at = factory.LazyFunction(tz.now)
    is_up = True
    status_code = 200
    response_ms = 100
```

- [ ] **Step 3: Smoke-check factory loads**

```bash
cd backend && uv run python -c "from tests.factories import UptimeMonitorFactory; print('OK')"
```
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/tests/factories.py
git commit -m "test(uptime): add UptimeMonitor + UptimeCheck factories"
```

---

## Task 4: State machine — pure logic (TDD)

**Files:**
- Create: `backend/apps/uptime/services.py`
- Create: `backend/tests/test_uptime.py`

The state machine has two halves: (a) pure transition logic that decides what action to take (fire failure / fire recovery / nothing), and (b) side-effect handlers that create Issues, Activities, Notifications. This task implements only (a) — a pure function. Side effects come in later tasks.

- [ ] **Step 1: Write failing test for state machine transitions**

`backend/tests/test_uptime.py`:
```python
import pytest
from datetime import timedelta
from unittest.mock import patch
from django.utils import timezone
from tests.factories import UptimeMonitorFactory, UptimeCheckFactory
from apps.uptime.services import decide_transition, TransitionAction

pytestmark = pytest.mark.django_db


class TestDecideTransition:
    def test_up_to_up_no_action(self):
        monitor = UptimeMonitorFactory(last_status="up", consecutive_failures=0)
        action = decide_transition(monitor, is_up=True)
        assert action == TransitionAction.NONE

    def test_unknown_to_up_no_action(self):
        monitor = UptimeMonitorFactory(last_status="unknown", consecutive_failures=0)
        action = decide_transition(monitor, is_up=True)
        assert action == TransitionAction.NONE

    def test_up_to_down_first_failure_no_action(self):
        monitor = UptimeMonitorFactory(last_status="up", consecutive_failures=0)
        action = decide_transition(monitor, is_up=False)
        assert action == TransitionAction.NONE

    def test_up_to_down_second_failure_no_action(self):
        monitor = UptimeMonitorFactory(last_status="up", consecutive_failures=1)
        action = decide_transition(monitor, is_up=False)
        assert action == TransitionAction.NONE

    def test_up_to_down_third_failure_fires_failure(self):
        monitor = UptimeMonitorFactory(last_status="up", consecutive_failures=2)
        action = decide_transition(monitor, is_up=False)
        assert action == TransitionAction.FIRE_FAILURE

    def test_down_to_down_no_action(self):
        monitor = UptimeMonitorFactory(last_status="down", consecutive_failures=10)
        action = decide_transition(monitor, is_up=False)
        assert action == TransitionAction.NONE

    def test_down_to_up_fires_recovery(self):
        monitor = UptimeMonitorFactory(last_status="down", consecutive_failures=5)
        action = decide_transition(monitor, is_up=True)
        assert action == TransitionAction.FIRE_RECOVERY
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && uv run pytest tests/test_uptime.py::TestDecideTransition -v
```
Expected: All FAIL with `ImportError: cannot import name 'decide_transition' from 'apps.uptime.services'`

- [ ] **Step 3: Write `services.py` with `decide_transition`**

`backend/apps/uptime/services.py`:
```python
from enum import Enum
from django.conf import settings


class TransitionAction(Enum):
    NONE = "none"
    FIRE_FAILURE = "fire_failure"
    FIRE_RECOVERY = "fire_recovery"


def decide_transition(monitor, *, is_up: bool) -> TransitionAction:
    """Decide what side effect to fire given the current monitor state and the latest check result.

    Pure function — does not mutate the monitor. The caller applies state updates
    (last_status, consecutive_failures, etc.) and dispatches the corresponding action.
    """
    threshold = settings.UPTIME_FAILURE_THRESHOLD

    if is_up:
        if monitor.last_status == "down":
            return TransitionAction.FIRE_RECOVERY
        return TransitionAction.NONE

    # is_up = False
    if monitor.last_status == "down":
        return TransitionAction.NONE
    # last_status is up or unknown
    if monitor.consecutive_failures + 1 >= threshold:
        return TransitionAction.FIRE_FAILURE
    return TransitionAction.NONE
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && uv run pytest tests/test_uptime.py::TestDecideTransition -v
```
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/uptime/services.py backend/tests/test_uptime.py
git commit -m "feat(uptime): add pure state-machine decision function with tests"
```

---

## Task 5: Failure action — create Issue + notify

**Files:**
- Modify: `backend/apps/uptime/services.py`
- Modify: `backend/tests/test_uptime.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_uptime.py`:
```python
from apps.uptime.services import fire_failure
from apps.issues.models import Issue
from apps.notifications.models import Notification, NotificationRecipient
from apps.projects.models import ProjectMember
from tests.factories import ProjectFactory, UserFactory


class TestFireFailure:
    def _setup(self):
        bot = UserFactory(username="bot")
        project = ProjectFactory()
        member = UserFactory()
        ProjectMember.objects.create(project=project, user=member, role="开发者")
        monitor = UptimeMonitorFactory(
            project=project, name="api-prod",
            url="https://api.example.com/health",
            last_status="up", consecutive_failures=2,
        )
        return bot, project, member, monitor

    def test_creates_issue_in_project(self, site_settings):
        bot, project, member, monitor = self._setup()
        fire_failure(monitor, latest_error="timeout")
        issue = Issue.objects.get(project=project)
        assert "api-prod" in issue.title
        assert "不可达" in issue.title
        assert issue.priority == "P1"
        assert issue.status == "待处理"
        assert issue.created_by == bot
        assert "timeout" in issue.description

    def test_sets_active_incident_issue(self, site_settings):
        bot, project, member, monitor = self._setup()
        fire_failure(monitor, latest_error="timeout")
        monitor.refresh_from_db()
        assert monitor.active_incident_issue is not None
        assert monitor.last_status == "down"
        assert monitor.outage_started_at is not None

    def test_sends_notifications_to_project_members(self, site_settings):
        bot, project, member, monitor = self._setup()
        fire_failure(monitor, latest_error="timeout")
        notification = Notification.objects.get()
        assert "api-prod" in notification.title
        recipients = list(notification.recipients.values_list("user_id", flat=True))
        assert member.id in recipients

    def test_no_bot_user_raises(self, site_settings):
        project = ProjectFactory()
        monitor = UptimeMonitorFactory(
            project=project, last_status="up", consecutive_failures=2,
        )
        with pytest.raises(Exception):
            fire_failure(monitor, latest_error="timeout")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_uptime.py::TestFireFailure -v
```
Expected: All FAIL with `ImportError: cannot import name 'fire_failure'`.

- [ ] **Step 3: Implement `fire_failure`**

Append to `backend/apps/uptime/services.py`:
```python
import logging
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

logger = logging.getLogger(__name__)
User = get_user_model()


def _get_bot_user():
    return User.objects.get(username=settings.UPTIME_SYSTEM_BOT_USERNAME)


def _build_failure_description(monitor, latest_error: str) -> str:
    return (
        f"**监控**: {monitor.name}\n\n"
        f"**URL**: {monitor.url}\n\n"
        f"**首次失败时间**: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"**连续失败次数**: {settings.UPTIME_FAILURE_THRESHOLD}\n\n"
        f"**最近一次错误**: {latest_error}\n"
    )


def fire_failure(monitor, *, latest_error: str):
    """Create an Issue for this monitor going down, link it, and notify project members."""
    from apps.issues.models import Issue
    from apps.notifications.models import Notification, NotificationRecipient
    from apps.projects.models import ProjectMember

    bot = _get_bot_user()
    now = timezone.now()

    issue = Issue.objects.create(
        project=monitor.project,
        title=f"[监控告警] {monitor.name} 不可达",
        description=_build_failure_description(monitor, latest_error),
        priority="P1",
        status="待处理",
        created_by=bot,
        reporter="",
    )

    monitor.active_incident_issue = issue
    monitor.last_status = "down"
    monitor.outage_started_at = now
    monitor.save(update_fields=["active_incident_issue", "last_status", "outage_started_at", "updated_at"])

    notification = Notification.objects.create(
        notification_type=Notification.Type.SYSTEM,
        title=f"监控 {monitor.name} 不可达",
        content=f"已创建 Issue #{issue.pk}",
        source_user=bot,
        source_issue=issue,
        target_type=Notification.TargetType.USER,
    )
    member_ids = list(
        ProjectMember.objects.filter(project=monitor.project).values_list("user_id", flat=True)
    )
    for user_id in member_ids:
        NotificationRecipient.objects.create(notification=notification, user_id=user_id)

    logger.info("Uptime monitor %s went down. Issue #%s created.", monitor.pk, issue.pk)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_uptime.py::TestFireFailure -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/uptime/services.py backend/tests/test_uptime.py
git commit -m "feat(uptime): fire_failure creates Issue and notifies project members"
```

---

## Task 6: Recovery action — close Issue + add Activity

**Files:**
- Modify: `backend/apps/uptime/services.py`
- Modify: `backend/tests/test_uptime.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_uptime.py`:
```python
from apps.uptime.services import fire_recovery
from apps.issues.models import Activity


class TestFireRecovery:
    def _setup_in_outage(self):
        bot = UserFactory(username="bot")
        project = ProjectFactory()
        member = UserFactory()
        ProjectMember.objects.create(project=project, user=member, role="开发者")
        existing_issue = Issue.objects.create(
            project=project, title="[监控告警] api-prod 不可达",
            description="...", priority="P1", status="待处理",
            created_by=bot, reporter="",
        )
        monitor = UptimeMonitorFactory(
            project=project, name="api-prod",
            last_status="down", consecutive_failures=5,
            outage_started_at=timezone.now() - timedelta(minutes=15),
            active_incident_issue=existing_issue,
        )
        return bot, project, member, monitor, existing_issue

    def test_closes_issue_with_resolved_status(self, site_settings):
        bot, project, member, monitor, issue = self._setup_in_outage()
        fire_recovery(monitor)
        issue.refresh_from_db()
        assert issue.status == "已解决"
        assert issue.resolved_at is not None

    def test_adds_activity_comment_with_duration(self, site_settings):
        bot, project, member, monitor, issue = self._setup_in_outage()
        fire_recovery(monitor)
        activity = Activity.objects.get(issue=issue, action="resolved", user=bot)
        assert "恢复" in activity.detail
        assert "15" in activity.detail  # 15 minute outage

    def test_clears_monitor_outage_state(self, site_settings):
        bot, project, member, monitor, issue = self._setup_in_outage()
        fire_recovery(monitor)
        monitor.refresh_from_db()
        assert monitor.active_incident_issue is None
        assert monitor.outage_started_at is None
        assert monitor.last_status == "up"
        assert monitor.last_up_at is not None
        assert monitor.consecutive_failures == 0

    def test_sends_recovery_notification(self, site_settings):
        bot, project, member, monitor, issue = self._setup_in_outage()
        fire_recovery(monitor)
        notification = Notification.objects.get()
        assert "恢复" in notification.title
        recipients = list(notification.recipients.values_list("user_id", flat=True))
        assert member.id in recipients

    def test_active_issue_already_closed_still_sends_notification(self, site_settings):
        bot, project, member, monitor, issue = self._setup_in_outage()
        issue.status = "已关闭"
        issue.save()
        fire_recovery(monitor)
        notification = Notification.objects.get()
        assert "恢复" in notification.title
        monitor.refresh_from_db()
        assert monitor.active_incident_issue is None
        assert monitor.last_status == "up"

    def test_no_active_issue_still_clears_state(self, site_settings):
        bot = UserFactory(username="bot")
        project = ProjectFactory()
        monitor = UptimeMonitorFactory(
            project=project, last_status="down", consecutive_failures=3,
            outage_started_at=timezone.now() - timedelta(minutes=5),
            active_incident_issue=None,
        )
        fire_recovery(monitor)
        monitor.refresh_from_db()
        assert monitor.last_status == "up"
        assert monitor.last_up_at is not None
        assert monitor.outage_started_at is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_uptime.py::TestFireRecovery -v
```
Expected: All FAIL with import error.

- [ ] **Step 3: Implement `fire_recovery`**

Append to `backend/apps/uptime/services.py`:
```python
def _format_duration_zh(delta) -> str:
    total_seconds = int(delta.total_seconds())
    if total_seconds < 60:
        return f"{total_seconds} 秒"
    minutes = total_seconds // 60
    if minutes < 60:
        return f"{minutes} 分钟"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} 小时 {minutes % 60} 分钟"
    days = hours // 24
    return f"{days} 天 {hours % 24} 小时"


def fire_recovery(monitor):
    """Close the active incident Issue (if any), add an Activity row, notify project members."""
    from apps.issues.models import Issue, Activity
    from apps.notifications.models import Notification, NotificationRecipient
    from apps.projects.models import ProjectMember

    bot = _get_bot_user()
    now = timezone.now()
    duration = now - monitor.outage_started_at if monitor.outage_started_at else timedelta()
    duration_human = _format_duration_zh(duration)

    issue = monitor.active_incident_issue
    if issue is not None and issue.status not in ("已解决", "已关闭"):
        issue.status = "已解决"
        issue.resolved_at = now
        issue.save(update_fields=["status", "resolved_at", "updated_at"])
        Activity.objects.create(
            user=bot, issue=issue, action="resolved",
            detail=f"监控已恢复,故障持续 {duration_human}",
        )

    monitor.active_incident_issue = None
    monitor.outage_started_at = None
    monitor.last_status = "up"
    monitor.last_up_at = now
    monitor.consecutive_failures = 0
    monitor.save(update_fields=[
        "active_incident_issue", "outage_started_at", "last_status",
        "last_up_at", "consecutive_failures", "updated_at",
    ])

    notification = Notification.objects.create(
        notification_type=Notification.Type.SYSTEM,
        title=f"监控 {monitor.name} 已恢复",
        content=f"故障持续 {duration_human}",
        source_user=bot,
        source_issue=issue,
        target_type=Notification.TargetType.USER,
    )
    member_ids = list(
        ProjectMember.objects.filter(project=monitor.project).values_list("user_id", flat=True)
    )
    for user_id in member_ids:
        NotificationRecipient.objects.create(notification=notification, user_id=user_id)

    logger.info("Uptime monitor %s recovered after %s.", monitor.pk, duration_human)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_uptime.py::TestFireRecovery -v
```
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/uptime/services.py backend/tests/test_uptime.py
git commit -m "feat(uptime): fire_recovery closes Issue and notifies project members"
```

---

## Task 7: HTTP check function

**Files:**
- Create: `backend/apps/uptime/http_check.py`
- Modify: `backend/tests/test_uptime.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_uptime.py`:
```python
from unittest.mock import patch, MagicMock
import requests as req_lib
from apps.uptime.http_check import perform_check


def _mock_response(status_code: int, text: str = "OK"):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    return resp


class TestPerformCheck:
    def test_200_with_default_expected(self):
        monitor = UptimeMonitorFactory(expected_status="200")
        with patch("apps.uptime.http_check.requests.get", return_value=_mock_response(200)):
            result = perform_check(monitor)
        assert result.is_up is True
        assert result.status_code == 200
        assert result.error == ""

    def test_204_when_expected_200(self):
        monitor = UptimeMonitorFactory(expected_status="200")
        with patch("apps.uptime.http_check.requests.get", return_value=_mock_response(204)):
            result = perform_check(monitor)
        assert result.is_up is False
        assert result.status_code == 204
        assert "status 204" in result.error

    def test_204_when_expected_200_or_204(self):
        monitor = UptimeMonitorFactory(expected_status="200,204")
        with patch("apps.uptime.http_check.requests.get", return_value=_mock_response(204)):
            result = perform_check(monitor)
        assert result.is_up is True

    def test_body_match_passes(self):
        monitor = UptimeMonitorFactory(expected_status="200", expected_body="healthy")
        with patch("apps.uptime.http_check.requests.get",
                   return_value=_mock_response(200, '{"status":"healthy"}')):
            result = perform_check(monitor)
        assert result.is_up is True

    def test_body_match_fails(self):
        monitor = UptimeMonitorFactory(expected_status="200", expected_body="healthy")
        with patch("apps.uptime.http_check.requests.get",
                   return_value=_mock_response(200, '{"status":"degraded"}')):
            result = perform_check(monitor)
        assert result.is_up is False
        assert "body mismatch" in result.error

    def test_timeout(self):
        monitor = UptimeMonitorFactory()
        with patch("apps.uptime.http_check.requests.get",
                   side_effect=req_lib.exceptions.Timeout()):
            result = perform_check(monitor)
        assert result.is_up is False
        assert result.status_code is None
        assert result.error == "timeout"

    def test_connection_error(self):
        monitor = UptimeMonitorFactory()
        with patch("apps.uptime.http_check.requests.get",
                   side_effect=req_lib.exceptions.ConnectionError()):
            result = perform_check(monitor)
        assert result.is_up is False
        assert result.status_code is None
        assert "connection" in result.error.lower()

    def test_response_time_captured(self):
        monitor = UptimeMonitorFactory()
        with patch("apps.uptime.http_check.requests.get", return_value=_mock_response(200)):
            result = perform_check(monitor)
        assert result.response_ms is not None
        assert result.response_ms >= 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_uptime.py::TestPerformCheck -v
```
Expected: All FAIL with import error.

- [ ] **Step 3: Implement HTTP check**

`backend/apps/uptime/http_check.py`:
```python
import time
from dataclasses import dataclass
from typing import Optional
import requests


@dataclass
class CheckResult:
    is_up: bool
    status_code: Optional[int]
    response_ms: Optional[int]
    error: str


def _parse_expected_status(expected: str) -> list[int]:
    return [int(s.strip()) for s in expected.split(",") if s.strip()]


def perform_check(monitor) -> CheckResult:
    expected_codes = _parse_expected_status(monitor.expected_status)
    start = time.monotonic()
    try:
        resp = requests.get(monitor.url, timeout=monitor.timeout_secs)
    except requests.exceptions.Timeout:
        return CheckResult(is_up=False, status_code=None, response_ms=None, error="timeout")
    except requests.exceptions.ConnectionError:
        return CheckResult(is_up=False, status_code=None, response_ms=None, error="connection error")
    except requests.exceptions.RequestException as exc:
        return CheckResult(is_up=False, status_code=None, response_ms=None, error=str(exc)[:200])

    elapsed_ms = int((time.monotonic() - start) * 1000)

    if resp.status_code not in expected_codes:
        return CheckResult(
            is_up=False, status_code=resp.status_code,
            response_ms=elapsed_ms, error=f"status {resp.status_code}",
        )

    if monitor.expected_body and monitor.expected_body not in (resp.text or ""):
        return CheckResult(
            is_up=False, status_code=resp.status_code,
            response_ms=elapsed_ms, error="body mismatch",
        )

    return CheckResult(
        is_up=True, status_code=resp.status_code,
        response_ms=elapsed_ms, error="",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_uptime.py::TestPerformCheck -v
```
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/uptime/http_check.py backend/tests/test_uptime.py
git commit -m "feat(uptime): HTTP check implementation with timeout and body validation"
```

---

## Task 8: `check_monitor` task — orchestration

**Files:**
- Create: `backend/apps/uptime/tasks.py`
- Modify: `backend/tests/test_uptime.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_uptime.py`:
```python
from apps.uptime.tasks import check_monitor
from apps.uptime.http_check import CheckResult
from apps.uptime.models import UptimeMonitor, UptimeCheck


class TestCheckMonitorTask:
    def test_writes_check_record(self, site_settings):
        UserFactory(username="bot")
        monitor = UptimeMonitorFactory(last_status="up", consecutive_failures=0)
        with patch("apps.uptime.tasks.perform_check",
                   return_value=CheckResult(is_up=True, status_code=200, response_ms=80, error="")):
            check_monitor(monitor.pk)
        assert UptimeCheck.objects.filter(monitor=monitor).count() == 1
        check = UptimeCheck.objects.get(monitor=monitor)
        assert check.is_up is True
        assert check.status_code == 200
        assert check.response_ms == 80

    def test_advances_next_check_at(self, site_settings):
        UserFactory(username="bot")
        monitor = UptimeMonitorFactory(interval_minutes=5, next_check_at=None)
        with patch("apps.uptime.tasks.perform_check",
                   return_value=CheckResult(is_up=True, status_code=200, response_ms=50, error="")):
            check_monitor(monitor.pk)
        monitor.refresh_from_db()
        assert monitor.next_check_at is not None
        delta = monitor.next_check_at - timezone.now()
        assert timedelta(minutes=4, seconds=50) < delta < timedelta(minutes=5, seconds=10)

    def test_third_consecutive_failure_fires_failure(self, site_settings):
        UserFactory(username="bot")
        project = ProjectFactory()
        monitor = UptimeMonitorFactory(
            project=project, last_status="up", consecutive_failures=2,
        )
        with patch("apps.uptime.tasks.perform_check",
                   return_value=CheckResult(is_up=False, status_code=500, response_ms=10, error="status 500")):
            check_monitor(monitor.pk)
        monitor.refresh_from_db()
        assert monitor.last_status == "down"
        assert monitor.active_incident_issue is not None
        assert monitor.consecutive_failures == 3

    def test_recovery_from_down_to_up(self, site_settings):
        bot = UserFactory(username="bot")
        project = ProjectFactory()
        issue = Issue.objects.create(
            project=project, title="x", description="x", priority="P1",
            status="待处理", created_by=bot, reporter="",
        )
        monitor = UptimeMonitorFactory(
            project=project, last_status="down", consecutive_failures=5,
            outage_started_at=timezone.now() - timedelta(minutes=10),
            active_incident_issue=issue,
        )
        with patch("apps.uptime.tasks.perform_check",
                   return_value=CheckResult(is_up=True, status_code=200, response_ms=70, error="")):
            check_monitor(monitor.pk)
        monitor.refresh_from_db()
        assert monitor.last_status == "up"
        assert monitor.consecutive_failures == 0
        assert monitor.active_incident_issue is None

    def test_disabled_monitor_skipped_silently(self, site_settings):
        monitor = UptimeMonitorFactory(is_enabled=False)
        with patch("apps.uptime.tasks.perform_check") as mocked:
            check_monitor(monitor.pk)
        mocked.assert_not_called()
        assert UptimeCheck.objects.filter(monitor=monitor).count() == 0

    def test_first_failure_does_not_fire(self, site_settings):
        UserFactory(username="bot")
        monitor = UptimeMonitorFactory(last_status="up", consecutive_failures=0)
        with patch("apps.uptime.tasks.perform_check",
                   return_value=CheckResult(is_up=False, status_code=500, response_ms=10, error="status 500")):
            check_monitor(monitor.pk)
        monitor.refresh_from_db()
        assert monitor.consecutive_failures == 1
        assert monitor.last_status == "up"
        assert monitor.active_incident_issue is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_uptime.py::TestCheckMonitorTask -v
```
Expected: All FAIL with import error.

- [ ] **Step 3: Implement `check_monitor`**

`backend/apps/uptime/tasks.py`:
```python
import logging
from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from apps.uptime.http_check import perform_check
from apps.uptime.models import UptimeMonitor, UptimeCheck
from apps.uptime.services import decide_transition, fire_failure, fire_recovery, TransitionAction

logger = logging.getLogger(__name__)


@shared_task
def check_monitor(monitor_id: int):
    """Execute one health check for the given monitor and apply state transitions."""
    with transaction.atomic():
        monitor = (
            UptimeMonitor.objects
            .select_for_update(skip_locked=True)
            .filter(pk=monitor_id)
            .first()
        )
        if monitor is None or not monitor.is_enabled:
            return

        now = timezone.now()
        monitor.next_check_at = now + timedelta(minutes=monitor.interval_minutes)
        monitor.last_check_at = now
        monitor.save(update_fields=["next_check_at", "last_check_at", "updated_at"])

    # HTTP call outside the txn so we don't hold a row lock during a slow request.
    result = perform_check(monitor)

    UptimeCheck.objects.create(
        monitor=monitor,
        checked_at=timezone.now(),
        is_up=result.is_up,
        status_code=result.status_code,
        response_ms=result.response_ms,
        error=result.error,
    )

    action = decide_transition(monitor, is_up=result.is_up)

    if result.is_up:
        monitor.consecutive_failures = 0
    else:
        monitor.consecutive_failures += 1
    monitor.save(update_fields=["consecutive_failures", "updated_at"])

    if action == TransitionAction.FIRE_FAILURE:
        fire_failure(monitor, latest_error=result.error or "unknown")
    elif action == TransitionAction.FIRE_RECOVERY:
        fire_recovery(monitor)
    else:
        logger.debug("Monitor %s check: is_up=%s, no action", monitor.pk, result.is_up)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_uptime.py::TestCheckMonitorTask -v
```
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/uptime/tasks.py backend/tests/test_uptime.py
git commit -m "feat(uptime): check_monitor task wires HTTP check to state machine"
```

---

## Task 9: `tick_uptime_monitors` and `prune_old_checks` tasks

**Files:**
- Modify: `backend/apps/uptime/tasks.py`
- Modify: `backend/tests/test_uptime.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_uptime.py`:
```python
from apps.uptime.tasks import tick_uptime_monitors, prune_old_checks


class TestTickTask:
    def test_dispatches_due_monitors(self, site_settings):
        now = timezone.now()
        due_no_schedule = UptimeMonitorFactory(next_check_at=None)
        due_overdue = UptimeMonitorFactory(next_check_at=now - timedelta(minutes=1))
        not_due = UptimeMonitorFactory(next_check_at=now + timedelta(minutes=5))
        disabled = UptimeMonitorFactory(is_enabled=False, next_check_at=None)

        with patch("apps.uptime.tasks.check_monitor.delay") as mocked:
            tick_uptime_monitors()

        called_ids = sorted([c.args[0] for c in mocked.call_args_list])
        assert called_ids == sorted([due_no_schedule.pk, due_overdue.pk])

    def test_no_due_monitors_dispatches_nothing(self, site_settings):
        UptimeMonitorFactory(next_check_at=timezone.now() + timedelta(minutes=10))
        with patch("apps.uptime.tasks.check_monitor.delay") as mocked:
            tick_uptime_monitors()
        mocked.assert_not_called()


class TestPruneTask:
    def test_deletes_old_checks(self, site_settings):
        monitor = UptimeMonitorFactory()
        cutoff = timezone.now() - timedelta(days=30)
        old = UptimeCheckFactory(monitor=monitor, checked_at=cutoff - timedelta(hours=1))
        recent = UptimeCheckFactory(monitor=monitor, checked_at=cutoff + timedelta(hours=1))

        prune_old_checks()

        assert not UptimeCheck.objects.filter(pk=old.pk).exists()
        assert UptimeCheck.objects.filter(pk=recent.pk).exists()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_uptime.py::TestTickTask tests/test_uptime.py::TestPruneTask -v
```
Expected: All FAIL with import error.

- [ ] **Step 3: Add tick + prune tasks**

Append to `backend/apps/uptime/tasks.py`:
```python
from django.conf import settings
from django.db.models import Q


@shared_task
def tick_uptime_monitors():
    """Find all monitors due for a check and dispatch per-monitor check tasks."""
    now = timezone.now()
    due_ids = list(
        UptimeMonitor.objects
        .filter(is_enabled=True)
        .filter(Q(next_check_at__isnull=True) | Q(next_check_at__lte=now))
        .values_list("pk", flat=True)
    )
    for monitor_id in due_ids:
        check_monitor.delay(monitor_id)
    logger.info("Uptime tick dispatched %d checks", len(due_ids))


@shared_task
def prune_old_checks():
    """Hard-delete UptimeCheck rows older than UPTIME_CHECK_RETENTION_DAYS."""
    cutoff = timezone.now() - timedelta(days=settings.UPTIME_CHECK_RETENTION_DAYS)
    deleted, _ = UptimeCheck.objects.filter(checked_at__lt=cutoff).delete()
    logger.info("Pruned %d old uptime checks (cutoff=%s)", deleted, cutoff)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_uptime.py::TestTickTask tests/test_uptime.py::TestPruneTask -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/uptime/tasks.py backend/tests/test_uptime.py
git commit -m "feat(uptime): tick task + retention pruning task"
```

---

## Task 10: Seed periodic tasks via data migration

**Files:**
- Create: `backend/apps/uptime/migrations/0002_seed_periodic_tasks.py`

- [ ] **Step 1: Write the data migration**

`backend/apps/uptime/migrations/0002_seed_periodic_tasks.py`:
```python
from django.db import migrations


def seed_periodic_tasks(apps, schema_editor):
    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    every_minute, _ = IntervalSchedule.objects.get_or_create(
        every=60, period="seconds",
    )
    PeriodicTask.objects.get_or_create(
        name="系统监控节拍（每分钟）",
        defaults={
            "task": "apps.uptime.tasks.tick_uptime_monitors",
            "interval": every_minute,
            "enabled": True,
        },
    )

    daily_3am, _ = CrontabSchedule.objects.get_or_create(
        minute="0", hour="3", day_of_month="*",
        month_of_year="*", day_of_week="*",
    )
    PeriodicTask.objects.get_or_create(
        name="清理过期监控记录（每日 3 点）",
        defaults={
            "task": "apps.uptime.tasks.prune_old_checks",
            "crontab": daily_3am,
            "enabled": True,
        },
    )


def remove_periodic_tasks(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(
        task__in=[
            "apps.uptime.tasks.tick_uptime_monitors",
            "apps.uptime.tasks.prune_old_checks",
        ]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("uptime", "0001_initial"),
        ("django_celery_beat", "__latest__"),
    ]

    operations = [
        migrations.RunPython(seed_periodic_tasks, remove_periodic_tasks),
    ]
```

- [ ] **Step 2: Apply the migration**

```bash
cd backend && uv run python manage.py migrate uptime
```
Expected: `Applying uptime.0002_seed_periodic_tasks... OK`

- [ ] **Step 3: Verify rows created**

```bash
cd backend && uv run python manage.py shell -c "from django_celery_beat.models import PeriodicTask; print([t.task for t in PeriodicTask.objects.filter(task__startswith='apps.uptime')])"
```
Expected: `['apps.uptime.tasks.tick_uptime_monitors', 'apps.uptime.tasks.prune_old_checks']` (order may vary)

- [ ] **Step 4: Commit**

```bash
git add backend/apps/uptime/migrations/0002_seed_periodic_tasks.py
git commit -m "feat(uptime): seed Celery Beat periodic tasks via data migration"
```

---

## Task 11: Permission class

**Files:**
- Create: `backend/apps/uptime/permissions.py`

- [ ] **Step 1: Write the permission class**

`backend/apps/uptime/permissions.py`:
```python
from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsSuperUserOrReadOnly(BasePermission):
    """Authenticated users may read; only superusers may create/update/delete."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return True
        return bool(request.user.is_superuser)
```

- [ ] **Step 2: Commit**

```bash
git add backend/apps/uptime/permissions.py
git commit -m "feat(uptime): IsSuperUserOrReadOnly permission class"
```

---

## Task 12: Serializers

**Files:**
- Create: `backend/apps/uptime/serializers.py`
- Modify: `backend/tests/test_uptime.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_uptime.py`:
```python
from apps.uptime.serializers import UptimeMonitorSerializer


class TestUptimeMonitorSerializer:
    def _factory_data(self, **overrides):
        data = {
            "name": "test-monitor",
            "url": "https://example.com/health",
            "method": "GET",
            "expected_status": "200",
            "expected_body": "",
            "interval_minutes": 5,
            "timeout_secs": 20,
            "is_enabled": True,
        }
        data.update(overrides)
        return data

    def test_valid_data(self):
        serializer = UptimeMonitorSerializer(data=self._factory_data())
        assert serializer.is_valid(), serializer.errors

    def test_url_must_have_protocol(self):
        serializer = UptimeMonitorSerializer(data=self._factory_data(url="example.com"))
        assert not serializer.is_valid()
        assert "url" in serializer.errors

    def test_method_post_rejected_in_v1(self):
        serializer = UptimeMonitorSerializer(data=self._factory_data(method="POST"))
        assert not serializer.is_valid()
        assert "method" in serializer.errors

    def test_expected_status_must_be_digits(self):
        serializer = UptimeMonitorSerializer(data=self._factory_data(expected_status="2xx"))
        assert not serializer.is_valid()
        assert "expected_status" in serializer.errors

    def test_expected_status_comma_separated_ok(self):
        serializer = UptimeMonitorSerializer(data=self._factory_data(expected_status="200,204"))
        assert serializer.is_valid(), serializer.errors

    def test_interval_min_1(self):
        serializer = UptimeMonitorSerializer(data=self._factory_data(interval_minutes=0))
        assert not serializer.is_valid()

    def test_interval_max_1440(self):
        serializer = UptimeMonitorSerializer(data=self._factory_data(interval_minutes=1441))
        assert not serializer.is_valid()

    def test_timeout_min_1(self):
        serializer = UptimeMonitorSerializer(data=self._factory_data(timeout_secs=0))
        assert not serializer.is_valid()

    def test_timeout_max_60(self):
        serializer = UptimeMonitorSerializer(data=self._factory_data(timeout_secs=61))
        assert not serializer.is_valid()

    def test_serialized_fields_include_read_only(self):
        monitor = UptimeMonitorFactory(
            last_status="up", last_check_at=timezone.now(), last_up_at=timezone.now(),
        )
        data = UptimeMonitorSerializer(monitor).data
        assert "last_status" in data
        assert "last_check_at" in data
        assert "last_up_at" in data
        assert "outage_started_at" in data
        assert "active_incident_issue_id" in data
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_uptime.py::TestUptimeMonitorSerializer -v
```
Expected: All FAIL with import error.

- [ ] **Step 3: Implement serializers**

`backend/apps/uptime/serializers.py`:
```python
import re
from rest_framework import serializers
from apps.uptime.models import UptimeMonitor, UptimeCheck

EXPECTED_STATUS_RE = re.compile(r"^\d{3}(,\d{3})*$")


class UptimeMonitorSerializer(serializers.ModelSerializer):
    interval_minutes = serializers.IntegerField(min_value=1, max_value=1440)
    timeout_secs = serializers.IntegerField(min_value=1, max_value=60)
    active_incident_issue_id = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = UptimeMonitor
        fields = [
            "id",
            "name", "url", "method", "expected_status", "expected_body",
            "interval_minutes", "timeout_secs", "is_enabled",
            "last_status", "last_check_at", "last_up_at",
            "outage_started_at", "active_incident_issue_id",
        ]
        read_only_fields = [
            "id", "last_status", "last_check_at", "last_up_at",
            "outage_started_at", "active_incident_issue_id",
        ]

    def validate_method(self, value):
        if value != "GET":
            raise serializers.ValidationError("v1 仅支持 GET")
        return value

    def validate_expected_status(self, value):
        if not EXPECTED_STATUS_RE.match(value):
            raise serializers.ValidationError("格式必须是单个状态码或逗号分隔(例如 '200' 或 '200,204')")
        return value

    def validate_url(self, value):
        if not (value.startswith("http://") or value.startswith("https://")):
            raise serializers.ValidationError("URL 必须以 http:// 或 https:// 开头")
        return value


class UptimeCheckSerializer(serializers.ModelSerializer):
    class Meta:
        model = UptimeCheck
        fields = ["checked_at", "is_up", "status_code", "response_ms", "error"]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_uptime.py::TestUptimeMonitorSerializer -v
```
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/uptime/serializers.py backend/tests/test_uptime.py
git commit -m "feat(uptime): serializers with validation"
```

---

## Task 13: Views — flat detail + checks endpoint

**Files:**
- Create: `backend/apps/uptime/views.py`
- Create: `backend/apps/uptime/urls.py`
- Modify: `backend/apps/urls.py`
- Modify: `backend/tests/test_uptime.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_uptime.py`:
```python
class TestUptimeMonitorDetailAPI:
    def test_retrieve_authenticated(self, regular_client):
        monitor = UptimeMonitorFactory()
        response = regular_client.get(f"/api/uptime/monitors/{monitor.pk}/")
        assert response.status_code == 200
        assert response.data["name"] == monitor.name

    def test_retrieve_unauthenticated_forbidden(self, api_client):
        monitor = UptimeMonitorFactory()
        response = api_client.get(f"/api/uptime/monitors/{monitor.pk}/")
        assert response.status_code in (401, 403)

    def test_update_non_superuser_forbidden(self, regular_client):
        monitor = UptimeMonitorFactory()
        response = regular_client.patch(f"/api/uptime/monitors/{monitor.pk}/", {"name": "x"})
        assert response.status_code == 403

    def test_update_superuser_ok(self, superuser_client):
        monitor = UptimeMonitorFactory()
        response = superuser_client.patch(
            f"/api/uptime/monitors/{monitor.pk}/", {"name": "renamed"}, format="json",
        )
        assert response.status_code == 200
        monitor.refresh_from_db()
        assert monitor.name == "renamed"

    def test_delete_non_superuser_forbidden(self, regular_client):
        monitor = UptimeMonitorFactory()
        response = regular_client.delete(f"/api/uptime/monitors/{monitor.pk}/")
        assert response.status_code == 403

    def test_delete_superuser_ok(self, superuser_client):
        monitor = UptimeMonitorFactory()
        response = superuser_client.delete(f"/api/uptime/monitors/{monitor.pk}/")
        assert response.status_code == 204
        assert not UptimeMonitor.objects.filter(pk=monitor.pk).exists()


class TestUptimeChecksAPI:
    def test_returns_recent_checks_newest_first(self, regular_client):
        monitor = UptimeMonitorFactory()
        now = timezone.now()
        UptimeCheckFactory(monitor=monitor, checked_at=now - timedelta(minutes=2), is_up=True)
        UptimeCheckFactory(monitor=monitor, checked_at=now - timedelta(minutes=1), is_up=False)
        UptimeCheckFactory(monitor=monitor, checked_at=now, is_up=True)

        response = regular_client.get(f"/api/uptime/monitors/{monitor.pk}/checks/")
        assert response.status_code == 200
        results = response.data
        assert len(results) == 3
        assert results[0]["is_up"] is True  # newest

    def test_limit_param(self, regular_client):
        monitor = UptimeMonitorFactory()
        for i in range(10):
            UptimeCheckFactory(monitor=monitor, checked_at=timezone.now() - timedelta(minutes=i))
        response = regular_client.get(f"/api/uptime/monitors/{monitor.pk}/checks/?limit=5")
        assert len(response.data) == 5
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_uptime.py::TestUptimeMonitorDetailAPI tests/test_uptime.py::TestUptimeChecksAPI -v
```
Expected: All FAIL with 404 (routes don't exist yet).

- [ ] **Step 3: Implement views**

`backend/apps/uptime/views.py`:
```python
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.uptime.models import UptimeMonitor, UptimeCheck
from apps.uptime.permissions import IsSuperUserOrReadOnly
from apps.uptime.serializers import UptimeMonitorSerializer, UptimeCheckSerializer


class UptimeMonitorDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = UptimeMonitor.objects.all()
    serializer_class = UptimeMonitorSerializer
    permission_classes = [IsAuthenticated, IsSuperUserOrReadOnly]


class UptimeMonitorChecksView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            limit = int(request.query_params.get("limit", 60))
        except ValueError:
            limit = 60
        limit = max(1, min(limit, 500))
        checks = (
            UptimeCheck.objects
            .filter(monitor_id=pk)
            .order_by("-checked_at")[:limit]
        )
        return Response(UptimeCheckSerializer(checks, many=True).data)
```

- [ ] **Step 4: Create URL conf**

`backend/apps/uptime/urls.py`:
```python
from django.urls import path
from .views import UptimeMonitorDetailView, UptimeMonitorChecksView

urlpatterns = [
    path("monitors/<int:pk>/", UptimeMonitorDetailView.as_view(), name="uptime-monitor-detail"),
    path("monitors/<int:pk>/checks/", UptimeMonitorChecksView.as_view(), name="uptime-monitor-checks"),
]
```

- [ ] **Step 5: Mount routes**

In `backend/apps/urls.py`, add the import-style include at the end of the `urlpatterns` list (alongside other `path(...)` entries):
```python
    path("uptime/", include("apps.uptime.urls")),
```

(Find the line containing `path("notifications/", include("apps.notifications.urls"))` and place the new line right after it.)

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_uptime.py::TestUptimeMonitorDetailAPI tests/test_uptime.py::TestUptimeChecksAPI -v
```
Expected: 8 passed.

- [ ] **Step 7: Commit**

```bash
git add backend/apps/uptime/views.py backend/apps/uptime/urls.py backend/apps/urls.py backend/tests/test_uptime.py
git commit -m "feat(uptime): flat monitor detail + checks history endpoints"
```

---

## Task 14: Nested project monitors endpoint (list + create)

**Files:**
- Modify: `backend/apps/projects/views.py`
- Modify: `backend/apps/projects/urls.py`
- Modify: `backend/tests/test_uptime.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_uptime.py`:
```python
class TestProjectMonitorsAPI:
    def test_list_for_project(self, regular_client):
        project = ProjectFactory()
        UptimeMonitorFactory(project=project)
        UptimeMonitorFactory(project=project)
        UptimeMonitorFactory()  # other project
        response = regular_client.get(f"/api/projects/{project.pk}/monitors/")
        assert response.status_code == 200
        assert len(response.data) == 2

    def test_create_non_superuser_forbidden(self, regular_client):
        project = ProjectFactory()
        response = regular_client.post(
            f"/api/projects/{project.pk}/monitors/",
            {"name": "m1", "url": "https://example.com/", "expected_status": "200",
             "interval_minutes": 1, "timeout_secs": 20, "method": "GET"},
            format="json",
        )
        assert response.status_code == 403

    def test_create_superuser_ok(self, superuser_client):
        project = ProjectFactory()
        response = superuser_client.post(
            f"/api/projects/{project.pk}/monitors/",
            {"name": "m1", "url": "https://example.com/health", "expected_status": "200",
             "interval_minutes": 1, "timeout_secs": 20, "method": "GET", "is_enabled": True,
             "expected_body": ""},
            format="json",
        )
        assert response.status_code == 201
        monitor = UptimeMonitor.objects.get(name="m1")
        assert monitor.project_id == project.pk

    def test_create_invalid_url(self, superuser_client):
        project = ProjectFactory()
        response = superuser_client.post(
            f"/api/projects/{project.pk}/monitors/",
            {"name": "m1", "url": "example.com", "expected_status": "200",
             "interval_minutes": 1, "timeout_secs": 20, "method": "GET", "expected_body": ""},
            format="json",
        )
        assert response.status_code == 400

    def test_create_invalid_expected_status(self, superuser_client):
        project = ProjectFactory()
        response = superuser_client.post(
            f"/api/projects/{project.pk}/monitors/",
            {"name": "m1", "url": "https://example.com/", "expected_status": "2xx",
             "interval_minutes": 1, "timeout_secs": 20, "method": "GET", "expected_body": ""},
            format="json",
        )
        assert response.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_uptime.py::TestProjectMonitorsAPI -v
```
Expected: All FAIL with 404.

- [ ] **Step 3: Add `ProjectMonitorsView`**

Append to `backend/apps/projects/views.py`:
```python


class ProjectMonitorsView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_permissions(self):
        from apps.uptime.permissions import IsSuperUserOrReadOnly
        return [IsAuthenticated(), IsSuperUserOrReadOnly()]

    def get_serializer_class(self):
        from apps.uptime.serializers import UptimeMonitorSerializer
        return UptimeMonitorSerializer

    def get_queryset(self):
        from apps.uptime.models import UptimeMonitor
        return UptimeMonitor.objects.filter(project_id=self.kwargs["project_pk"])

    def perform_create(self, serializer):
        from apps.projects.models import Project
        project = get_object_or_404(Project, pk=self.kwargs["project_pk"])
        serializer.save(project=project)
```

- [ ] **Step 4: Wire the URL**

Modify `backend/apps/projects/urls.py`:
```python
from django.urls import path
from .views import (
    ProjectListCreateView,
    ProjectDetailView,
    ProjectMemberListCreateView,
    ProjectMemberDeleteView,
    ProjectIssuesView,
    ProjectMonitorsView,
)

urlpatterns = [
    path("", ProjectListCreateView.as_view(), name="project-list"),
    path("<int:pk>/", ProjectDetailView.as_view(), name="project-detail"),
    path("<int:project_pk>/members/", ProjectMemberListCreateView.as_view(), name="project-members"),
    path("<int:project_pk>/members/<int:user_pk>/", ProjectMemberDeleteView.as_view(), name="project-member-delete"),
    path("<int:project_pk>/issues/", ProjectIssuesView.as_view(), name="project-issues"),
    path("<int:project_pk>/monitors/", ProjectMonitorsView.as_view(), name="project-monitors"),
]
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_uptime.py::TestProjectMonitorsAPI -v
```
Expected: 5 passed.

- [ ] **Step 6: Run the full uptime test suite**

```bash
cd backend && uv run pytest tests/test_uptime.py -v
```
Expected: all uptime tests pass (50+ tests).

- [ ] **Step 7: Commit**

```bash
git add backend/apps/projects/views.py backend/apps/projects/urls.py backend/tests/test_uptime.py
git commit -m "feat(uptime): nested project monitors list+create endpoint"
```

---

## Task 15: Django admin registration

**Files:**
- Create: `backend/apps/uptime/admin.py`

- [ ] **Step 1: Register both models**

`backend/apps/uptime/admin.py`:
```python
from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import UptimeMonitor, UptimeCheck


@admin.register(UptimeMonitor)
class UptimeMonitorAdmin(ModelAdmin):
    list_display = ("id", "name", "project", "url", "last_status", "is_enabled", "last_check_at")
    list_filter = ("last_status", "is_enabled", "project")
    search_fields = ("name", "url")
    readonly_fields = (
        "next_check_at", "last_check_at", "last_status", "last_up_at",
        "outage_started_at", "consecutive_failures", "active_incident_issue",
        "created_at", "updated_at",
    )


@admin.register(UptimeCheck)
class UptimeCheckAdmin(ModelAdmin):
    list_display = ("monitor", "checked_at", "is_up", "status_code", "response_ms", "error")
    list_filter = ("is_up",)
    search_fields = ("monitor__name", "error")
    date_hierarchy = "checked_at"
```

- [ ] **Step 2: Verify Django still loads**

```bash
cd backend && uv run python manage.py check
```
Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 3: Commit**

```bash
git add backend/apps/uptime/admin.py
git commit -m "feat(uptime): Django admin for monitors and checks"
```

---

## Task 16: Frontend — `formatUptime` helper

**Files:**
- Create: `frontend/app/utils/formatUptime.ts`

- [ ] **Step 1: Write the helper**

`frontend/app/utils/formatUptime.ts`:
```ts
export function formatUptime(
  lastUpAt: string | null,
  outageStartedAt: string | null,
  lastStatus: string,
): string {
  if (lastStatus === 'unknown') return '等待首次检查'

  const anchor = lastStatus === 'down' ? outageStartedAt : lastUpAt
  if (!anchor) return '等待首次检查'

  const now = Date.now()
  const then = new Date(anchor).getTime()
  const diffMs = Math.max(0, now - then)
  const minutes = Math.floor(diffMs / 60000)

  const prefix = lastStatus === 'down' ? '已宕机' : '已稳定运行'

  if (minutes < 60) return `${prefix} ${minutes} 分钟`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${prefix} ${hours} 小时`
  const days = Math.floor(hours / 24)
  return `${prefix} ${days} 天`
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/app/utils/formatUptime.ts
git commit -m "feat(uptime): formatUptime helper for Chinese duration display"
```

---

## Task 17: Frontend — Timeline component

**Files:**
- Create: `frontend/app/components/projects/UptimeMonitorTimeline.vue`

- [ ] **Step 1: Build the component**

`frontend/app/components/projects/UptimeMonitorTimeline.vue`:
```vue
<template>
  <div class="flex items-center gap-[1px]">
    <UTooltip
      v-for="(check, idx) in displayChecks"
      :key="`${check.checked_at}-${idx}`"
      :text="tooltipFor(check)"
    >
      <div
        class="w-[4px] h-5 rounded-[1px]"
        :class="check.is_up ? 'bg-green-500' : 'bg-red-500'"
      />
    </UTooltip>
    <div
      v-for="n in placeholderCount"
      :key="`p-${n}`"
      class="w-[4px] h-5 rounded-[1px] bg-gray-200 dark:bg-gray-700"
    />
  </div>
</template>

<script setup lang="ts">
interface Check {
  checked_at: string
  is_up: boolean
  status_code: number | null
  response_ms: number | null
  error: string
}

const props = defineProps<{
  checks: Check[]
  maxBars?: number
}>()

const maxBars = computed(() => props.maxBars ?? 60)

const displayChecks = computed(() => {
  // Caller sends newest first; reverse so oldest is on the left.
  return [...props.checks].reverse().slice(-maxBars.value)
})

const placeholderCount = computed(() => Math.max(0, maxBars.value - displayChecks.value.length))

function tooltipFor(check: Check): string {
  const ts = new Date(check.checked_at).toLocaleString('zh-CN', { hour12: false })
  if (check.is_up) return `已恢复 - ${ts}`
  const err = check.error ? ` (${check.error})` : ''
  return `宕机 - ${ts}${err}`
}
</script>
```

- [ ] **Step 2: Typecheck**

```bash
cd frontend && npx nuxi typecheck 2>&1 | tail -10
```
Expected: 0 errors related to `UptimeMonitorTimeline.vue` (existing project errors unrelated are acceptable; check that no new errors appear in the file).

- [ ] **Step 3: Commit**

```bash
git add frontend/app/components/projects/UptimeMonitorTimeline.vue
git commit -m "feat(uptime): timeline strip component"
```

---

## Task 18: Frontend — Form modal component

**Files:**
- Create: `frontend/app/components/projects/UptimeMonitorFormModal.vue`

- [ ] **Step 1: Build the component**

`frontend/app/components/projects/UptimeMonitorFormModal.vue`:
```vue
<template>
  <UModal v-model:open="isOpen" :title="title">
    <template #body>
      <div class="space-y-4">
        <UFormField label="监控名称" required>
          <UInput v-model="form.name" placeholder="例如：api-prod" />
        </UFormField>
        <UFormField label="URL" required>
          <UInput v-model="form.url" placeholder="https://example.com/health" />
        </UFormField>
        <UFormField label="期望状态码" hint="单个或逗号分隔,例如 200 或 200,204">
          <UInput v-model="form.expected_status" placeholder="200" />
        </UFormField>
        <UFormField label="期望响应体关键字" hint="留空表示不校验响应体">
          <UInput v-model="form.expected_body" placeholder="healthy" />
        </UFormField>
        <UFormField label="检查间隔">
          <USelect v-model="form.interval_minutes" :items="intervalOptions" value-key="value" />
        </UFormField>
        <UFormField label="超时(秒)">
          <UInput v-model.number="form.timeout_secs" type="number" :min="1" :max="60" />
        </UFormField>
        <p v-if="error" class="text-sm text-red-500">{{ error }}</p>
      </div>
    </template>
    <template #footer>
      <div class="flex justify-end gap-2">
        <UButton color="neutral" variant="ghost" @click="isOpen = false">取消</UButton>
        <UButton :loading="submitting" @click="submit">{{ isEdit ? '保存' : '创建' }}</UButton>
      </div>
    </template>
  </UModal>
</template>

<script setup lang="ts">
interface MonitorPayload {
  id?: number
  name: string
  url: string
  method: string
  expected_status: string
  expected_body: string
  interval_minutes: number
  timeout_secs: number
  is_enabled: boolean
}

const props = defineProps<{
  open: boolean
  projectId: number
  initial?: MonitorPayload | null
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  saved: []
}>()

const { api } = useApi()

const isOpen = computed({
  get: () => props.open,
  set: (v: boolean) => emit('update:open', v),
})

const isEdit = computed(() => Boolean(props.initial?.id))
const title = computed(() => isEdit.value ? '编辑监控' : '添加监控')

const intervalOptions = [
  { label: '每 1 分钟', value: 1 },
  { label: '每 5 分钟', value: 5 },
  { label: '每 10 分钟', value: 10 },
  { label: '每 30 分钟', value: 30 },
  { label: '每 60 分钟', value: 60 },
]

const form = reactive<MonitorPayload>({
  name: '',
  url: '',
  method: 'GET',
  expected_status: '200',
  expected_body: '',
  interval_minutes: 1,
  timeout_secs: 20,
  is_enabled: true,
})

const submitting = ref(false)
const error = ref('')

watch(() => props.open, (open) => {
  if (open) {
    error.value = ''
    if (props.initial) {
      Object.assign(form, props.initial)
    } else {
      Object.assign(form, {
        name: '', url: '', method: 'GET', expected_status: '200',
        expected_body: '', interval_minutes: 1, timeout_secs: 20, is_enabled: true,
      })
    }
  }
})

async function submit() {
  error.value = ''
  submitting.value = true
  try {
    if (isEdit.value) {
      await api(`/api/uptime/monitors/${props.initial!.id}/`, { method: 'PATCH', body: form })
    } else {
      await api(`/api/projects/${props.projectId}/monitors/`, { method: 'POST', body: form })
    }
    emit('saved')
    isOpen.value = false
  } catch (e: any) {
    error.value = e?.data ? JSON.stringify(e.data) : (e?.message ?? '保存失败')
  } finally {
    submitting.value = false
  }
}
</script>
```

- [ ] **Step 2: Typecheck**

```bash
cd frontend && npx nuxi typecheck 2>&1 | tail -10
```
Expected: no new errors in `UptimeMonitorFormModal.vue`.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/components/projects/UptimeMonitorFormModal.vue
git commit -m "feat(uptime): create/edit monitor modal"
```

---

## Task 19: Frontend — Row component

**Files:**
- Create: `frontend/app/components/projects/UptimeMonitorRow.vue`

- [ ] **Step 1: Build the component**

`frontend/app/components/projects/UptimeMonitorRow.vue`:
```vue
<template>
  <div class="group flex items-center gap-4 py-3 px-3 hover:bg-gray-50 dark:hover:bg-gray-800 rounded-lg">
    <div
      class="w-2 h-2 rounded-full shrink-0"
      :class="statusDotClass"
    />
    <div class="min-w-0 flex-shrink-0 w-56">
      <div class="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">{{ monitor.name }}</div>
      <a
        :href="monitor.url" target="_blank" rel="noopener"
        class="text-xs text-gray-500 dark:text-gray-400 hover:text-crystal-500 truncate block"
      >{{ monitor.url }}</a>
    </div>
    <div class="flex-1 min-w-0 overflow-hidden">
      <ProjectsUptimeMonitorTimeline :checks="checks" />
    </div>
    <div class="shrink-0 text-xs w-32 text-right" :class="statusTextClass">
      {{ statusText }}
    </div>
    <div v-if="canManage" class="shrink-0 opacity-0 group-hover:opacity-100 transition-opacity flex gap-1">
      <UButton icon="i-heroicons-pencil-square" size="xs" color="neutral" variant="ghost" @click="emit('edit')" />
      <UButton icon="i-heroicons-trash" size="xs" color="error" variant="ghost" @click="emit('delete')" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { formatUptime } from '~/utils/formatUptime'

interface Monitor {
  id: number
  name: string
  url: string
  last_status: string
  last_up_at: string | null
  outage_started_at: string | null
}

interface Check {
  checked_at: string
  is_up: boolean
  status_code: number | null
  response_ms: number | null
  error: string
}

const props = defineProps<{
  monitor: Monitor
  checks: Check[]
  canManage: boolean
}>()

const emit = defineEmits<{ edit: []; delete: [] }>()

const statusDotClass = computed(() => {
  switch (props.monitor.last_status) {
    case 'up': return 'bg-green-500'
    case 'down': return 'bg-red-500'
    default: return 'bg-gray-300 dark:bg-gray-600'
  }
})

const statusText = computed(() => formatUptime(
  props.monitor.last_up_at, props.monitor.outage_started_at, props.monitor.last_status,
))

const statusTextClass = computed(() => {
  switch (props.monitor.last_status) {
    case 'up': return 'text-green-600 dark:text-green-400'
    case 'down': return 'text-red-600 dark:text-red-400'
    default: return 'text-gray-400 dark:text-gray-500'
  }
})
</script>
```

- [ ] **Step 2: Typecheck**

```bash
cd frontend && npx nuxi typecheck 2>&1 | tail -10
```
Expected: no new errors in `UptimeMonitorRow.vue`.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/components/projects/UptimeMonitorRow.vue
git commit -m "feat(uptime): row component with status dot, timeline, and hover actions"
```

---

## Task 20: Frontend — Section container with polling

**Files:**
- Create: `frontend/app/components/projects/UptimeMonitorsSection.vue`

- [ ] **Step 1: Build the component**

`frontend/app/components/projects/UptimeMonitorsSection.vue`:
```vue
<template>
  <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5">
    <div class="flex items-center justify-between mb-3">
      <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100">
        系统监控 ({{ monitors.length }})
      </h3>
      <UButton
        v-if="canManage"
        size="xs" icon="i-heroicons-plus"
        @click="openCreate"
      >添加监控</UButton>
    </div>

    <div v-if="loading" class="text-sm text-gray-400 dark:text-gray-500 py-2">加载中...</div>

    <div v-else-if="monitors.length === 0" class="text-sm text-gray-400 dark:text-gray-500 py-2">
      暂无监控
    </div>

    <div v-else class="divide-y divide-gray-100 dark:divide-gray-800">
      <ProjectsUptimeMonitorRow
        v-for="m in monitors" :key="m.id"
        :monitor="m"
        :checks="checksMap[m.id] ?? []"
        :can-manage="canManage"
        @edit="openEdit(m)"
        @delete="confirmDelete(m)"
      />
    </div>

    <ProjectsUptimeMonitorFormModal
      v-model:open="modalOpen"
      :project-id="projectId"
      :initial="editing"
      @saved="onSaved"
    />

    <UModal v-model:open="deleteDialogOpen" title="删除监控">
      <template #body>
        <p class="text-sm">确定要删除监控 "{{ pendingDelete?.name }}" 吗?此操作不可撤销。</p>
      </template>
      <template #footer>
        <div class="flex justify-end gap-2">
          <UButton color="neutral" variant="ghost" @click="deleteDialogOpen = false">取消</UButton>
          <UButton color="error" :loading="deleting" @click="doDelete">删除</UButton>
        </div>
      </template>
    </UModal>
  </div>
</template>

<script setup lang="ts">
interface Monitor {
  id: number
  name: string
  url: string
  method: string
  expected_status: string
  expected_body: string
  interval_minutes: number
  timeout_secs: number
  is_enabled: boolean
  last_status: string
  last_check_at: string | null
  last_up_at: string | null
  outage_started_at: string | null
  active_incident_issue_id: number | null
}

interface Check {
  checked_at: string
  is_up: boolean
  status_code: number | null
  response_ms: number | null
  error: string
}

const props = defineProps<{
  projectId: number
}>()

const { api } = useApi()
const { user } = useAuth()

const canManage = computed(() => Boolean(user.value?.is_superuser))

const monitors = ref<Monitor[]>([])
const checksMap = ref<Record<number, Check[]>>({})
const loading = ref(true)

const modalOpen = ref(false)
const editing = ref<Monitor | null>(null)

const deleteDialogOpen = ref(false)
const pendingDelete = ref<Monitor | null>(null)
const deleting = ref(false)

let pollTimer: ReturnType<typeof setInterval> | null = null

async function fetchMonitors() {
  const data = await api<Monitor[]>(`/api/projects/${props.projectId}/monitors/`)
  monitors.value = data ?? []
}

async function fetchAllChecks() {
  const results = await Promise.all(
    monitors.value.map(async (m) => {
      try {
        const checks = await api<Check[]>(`/api/uptime/monitors/${m.id}/checks/?limit=60`)
        return [m.id, checks] as const
      } catch {
        return [m.id, []] as const
      }
    }),
  )
  checksMap.value = Object.fromEntries(results)
}

function patchStatusFields(fresh: Monitor[]) {
  // In-place update existing rows; add new ones; drop removed ones.
  const byId = new Map(fresh.map(m => [m.id, m]))
  monitors.value = monitors.value
    .filter(m => byId.has(m.id))
    .map((m) => {
      const f = byId.get(m.id)!
      return {
        ...m,
        last_status: f.last_status,
        last_check_at: f.last_check_at,
        last_up_at: f.last_up_at,
        outage_started_at: f.outage_started_at,
        active_incident_issue_id: f.active_incident_issue_id,
      }
    })
  // Append monitors that weren't there before
  const existingIds = new Set(monitors.value.map(m => m.id))
  for (const m of fresh) {
    if (!existingIds.has(m.id)) monitors.value.push(m)
  }
}

async function pollStatus() {
  try {
    const fresh = await api<Monitor[]>(`/api/projects/${props.projectId}/monitors/`)
    patchStatusFields(fresh ?? [])
  } catch (e) {
    console.warn('Failed to poll uptime monitors', e)
  }
}

function openCreate() {
  editing.value = null
  modalOpen.value = true
}

function openEdit(m: Monitor) {
  editing.value = { ...m }
  modalOpen.value = true
}

async function onSaved() {
  await fetchMonitors()
  await fetchAllChecks()
}

function confirmDelete(m: Monitor) {
  pendingDelete.value = m
  deleteDialogOpen.value = true
}

async function doDelete() {
  if (!pendingDelete.value) return
  deleting.value = true
  try {
    await api(`/api/uptime/monitors/${pendingDelete.value.id}/`, { method: 'DELETE' })
    await fetchMonitors()
    await fetchAllChecks()
    deleteDialogOpen.value = false
  } catch (e) {
    console.error('Delete failed', e)
  } finally {
    deleting.value = false
  }
}

onMounted(async () => {
  try {
    await fetchMonitors()
    await fetchAllChecks()
  } finally {
    loading.value = false
  }
  pollTimer = setInterval(pollStatus, 60_000)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>
```

- [ ] **Step 2: Typecheck**

```bash
cd frontend && npx nuxi typecheck 2>&1 | tail -10
```
Expected: no new errors in `UptimeMonitorsSection.vue`.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/components/projects/UptimeMonitorsSection.vue
git commit -m "feat(uptime): section container with polling + create/edit/delete"
```

---

## Task 21: Wire section into project detail page

**Files:**
- Modify: `frontend/app/pages/app/projects/[id].vue`

- [ ] **Step 1: Insert the section between "项目成员" and "Issues"**

In `frontend/app/pages/app/projects/[id].vue`, find the closing `</div>` of the Members block (around line 56, right after `</div>` that closes the `<!-- Members -->` section). Insert the new section just before the `<!-- Issues View -->` comment:

Find this:
```vue
      <div v-else class="text-sm text-gray-400 dark:text-gray-500">暂无成员</div>
    </div>

    <!-- Issues View -->
```

Replace with:
```vue
      <div v-else class="text-sm text-gray-400 dark:text-gray-500">暂无成员</div>
    </div>

    <!-- Uptime Monitors -->
    <ProjectsUptimeMonitorsSection :project-id="Number(route.params.id)" />

    <!-- Issues View -->
```

- [ ] **Step 2: Typecheck**

```bash
cd frontend && npx nuxi typecheck 2>&1 | tail -10
```
Expected: no new errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/pages/app/projects/[id].vue
git commit -m "feat(uptime): show monitors section on project detail page"
```

---

## Task 22: End-to-end smoke test

This task verifies the whole feature on the running stack. **Do not commit anything in this task** — it's manual validation.

- [ ] **Step 1: Start backend, worker, beat, frontend**

In four terminals from the repo root:
```bash
cd backend && uv run python manage.py runserver
cd backend && uv run celery -A config worker -l info
cd backend && uv run celery -A config beat -l info
cd frontend && npm run dev
```

- [ ] **Step 2: Verify the `bot` user exists**

```bash
cd backend && uv run python manage.py shell -c "from django.contrib.auth import get_user_model; print(get_user_model().objects.filter(username='bot').exists())"
```
Expected: `True`. If `False`, create one:
```bash
cd backend && uv run python manage.py shell -c "from django.contrib.auth import get_user_model; User=get_user_model(); User.objects.create_user(username='bot', email='bot@local', password='x'); print('created')"
```

- [ ] **Step 3: Open browser to a project detail page**

Navigate to `http://localhost:3000/app/projects/1`. Verify the **系统监控 (0)** section appears between project members and Issues, with a **+ 添加监控** button (only if logged in as superuser).

- [ ] **Step 4: Add a healthy monitor**

Click **+ 添加监控**, fill in:
- 监控名称: `test-healthy`
- URL: `https://www.example.com/`
- (leave defaults)

Click 创建. The row appears with a gray dot ("等待首次检查"). Within ~60s, watch the green timeline bars appear and the status turn green.

- [ ] **Step 5: Add a broken monitor and verify failure + Issue creation**

Click **+ 添加监控**, fill in:
- 监控名称: `test-broken`
- URL: `http://127.0.0.1:1/` (port that nothing listens on → connection error)
- 检查间隔: 1 分钟

Click 创建. Watch the timeline turn red. After 3 minutes (3 failed checks), check:
- The row turns to red dot, text "已宕机 N 分钟"
- A new Issue appears at `/app/issues` titled `[监控告警] test-broken 不可达`
- A notification appears in the bell

- [ ] **Step 6: Fix the broken monitor and verify recovery**

Edit `test-broken` → change URL to `https://www.example.com/` → save.

Within 1 minute, the next check succeeds. Verify:
- The row's dot turns green, text shows "已稳定运行 N 分钟"
- The Issue created in Step 5 is now marked 已解决
- An Activity entry on that Issue says "监控已恢复,故障持续 X 分钟"
- A new "已恢复" notification arrives

- [ ] **Step 7: Verify non-superuser sees no manage controls**

Log in as a non-superuser. Visit the same project page. Verify:
- The section is visible with monitor rows
- No **+ 添加监控** button
- Hovering on a row does not show edit/delete icons

If any step fails, fix in a new task and verify again before continuing.

---

## Task 23: Final verification + ship

- [ ] **Step 1: Run full backend test suite**

```bash
cd backend && uv run pytest -v
```
Expected: all tests pass (including the new uptime suite).

- [ ] **Step 2: Run frontend typecheck**

```bash
cd frontend && npx nuxi typecheck
```
Expected: 0 type errors.

- [ ] **Step 3: Push to test branch**

```bash
git push -f origin HEAD:env/test
```

This triggers CI to build images. Wait for green build, then smoke-test the deployed instance.

- [ ] **Step 4: Production deploy — REQUIRES USER APPROVAL**

Per `MEMORY.md` constitutional rule: never push to `env/prod` without explicit user consent. Stop and confirm with the user before running:

```bash
git push -f origin HEAD:env/prod
```

---

## Open follow-ups (not in v1, intentionally deferred)

- Monitor detail page with response-time chart (currently Django admin only)
- Email / webhook alerting channels
- Maintenance windows (suppress alerts during planned downtime)
- Pause / mute a monitor's notifications without disabling its checks
- Per-monitor priority (currently always P1)
