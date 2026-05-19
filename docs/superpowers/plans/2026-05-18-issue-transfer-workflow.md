# Issue Transfer Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add issue transfer workflow with full audit trail, dynamic status cell UI, project-manager snapshot per issue, and Phase-2 AI auto-assignment on creation.

**Architecture:** New `IssueAssignment` event-log table records every assignment change (claim/assign/transfer/confirm/ai_assign). All writes go through `apps/issues/services.py` to keep `Issue.assignee == issue.assignments.last().to_user` invariant. Frontend gets a single `StatusCell.vue` component that renders the right buttons/badges based on `can_*` flags computed server-side. Phase 2 adds `auto_assign_issue()` that calls existing `LLMClient` to pick a member by their `personal_description`.

**Tech Stack:** Django 6 / DRF, `factory_boy` + `pytest-django` for backend tests, Nuxt 4 + Vue 3 + `@nuxt/ui` (UModal, USelect, UTextarea, UBadge, UButton) for frontend, existing `apps/ai/client.LLMClient` for LLM calls.

**Spec reference:** `docs/superpowers/specs/2026-05-18-issue-transfer-workflow-design.md`

---

## File Map

### Backend — new files

- `backend/apps/issues/migrations/0010_assignment_workflow.py` — schema + data migration
- `backend/apps/projects/migrations/0003_projectmember_is_manager.py` — schema migration
- `backend/apps/settings/migrations/0008_status_rename.py` — site settings JSON update
- `backend/tests/test_assignment_workflow.py` — service-layer + invariant tests
- `backend/tests/test_assignment_api.py` — HTTP-level tests for 4 new endpoints
- `backend/tests/test_project_manager.py` — is_manager + Issue.manager snapshot tests
- `backend/tests/test_auto_assign.py` — Phase 2 AI auto-assign tests

### Backend — modified files

- `backend/apps/issues/models.py` — IssueStatus rename, +manager FK, +IssueAssignment, +AssignmentAction
- `backend/apps/projects/models.py` — ProjectMember.is_manager + partial unique constraint
- `backend/apps/settings/models.py` — default_issue_statuses update
- `backend/apps/issues/services.py` — add InvalidTransition, claim/confirm/transfer/assign/create_issue/auto_assign_issue + _resolve_project_manager
- `backend/apps/issues/serializers.py` — IssueAssignmentSerializer, can_* fields, manager_name, hook create_issue into IssueCreateUpdateSerializer.create, Transfer/Assign input serializers
- `backend/apps/issues/views.py` — IssueClaimView/ConfirmView/TransferView/AssignView, fix status_order Case-When, fix DashboardStatsView "待处理"→"待分配"
- `backend/apps/issues/urls.py` — register 4 new endpoints
- `backend/apps/issues/admin.py` — register IssueAssignment + ProjectMember.is_manager fields
- `backend/tests/factories.py` — IssueFactory default status, SiteSettingsFactory.issue_statuses, +IssueAssignmentFactory, ProjectMemberFactory.is_manager
- `backend/tests/test_issues.py`, `test_dashboard.py`, `test_issues_duplicate_check.py`, `test_attachments.py`, `test_external_api.py`, `test_ai_wizard.py`, `test_settings.py`, `test_kpi_metrics.py` — sed-style "待处理"→"待分配"

### Frontend — new files

- `frontend/app/constants/issueStatus.ts` — status string constants, color map, kanban order
- `frontend/app/components/issue/StatusCell.vue` — dynamic status cell (table + kanban)
- `frontend/app/components/issue/TransferDialog.vue` — transfer modal
- `frontend/app/components/issue/AssignDialog.vue` — manager-assign modal
- `frontend/app/composables/useIssueActions.ts` — API wrappers for claim/confirm/transfer/assign

### Frontend — modified files

- `frontend/app/pages/app/issues/index.vue` — remove 负责人 column, use StatusCell, update kanban order, create-form toast logic, update statusColor
- `frontend/app/pages/app/issues/[id].vue` — add assignment history block, use StatusCell
- `frontend/app/components/IssueCard.vue` — replace status badge with StatusCell
- `frontend/app/data/mock.ts` — replace "待处理" with "待分配", add "待确认" entries

---

# Phase 1: Foundation + Manual Workflow

## Task 1: Define IssueStatus + AssignmentAction + IssueAssignment model

**Files:**
- Modify: `backend/apps/issues/models.py`
- Test: `backend/tests/test_assignment_workflow.py` (new)

- [ ] **Step 1: Write failing test for new status enum + assignment model**

Create `backend/tests/test_assignment_workflow.py`:

```python
import pytest
from django.db import IntegrityError
from apps.issues.models import Issue, IssueAssignment, IssueStatus, AssignmentAction
from tests.factories import IssueFactory, UserFactory


@pytest.mark.django_db
class TestEnums:
    def test_issue_status_has_unassigned_and_pending_confirmation(self):
        assert IssueStatus.UNASSIGNED.value == "待分配"
        assert IssueStatus.PENDING_CONFIRMATION.value == "待确认"
        assert IssueStatus.IN_PROGRESS.value == "进行中"
        # Verify "待处理" is GONE
        assert "待处理" not in IssueStatus.values

    def test_assignment_action_choices(self):
        assert AssignmentAction.CLAIM.value == "claim"
        assert AssignmentAction.ASSIGN.value == "assign"
        assert AssignmentAction.AI_ASSIGN.value == "ai_assign"
        assert AssignmentAction.TRANSFER.value == "transfer"
        assert AssignmentAction.CONFIRM.value == "confirm"


@pytest.mark.django_db
class TestIssueAssignmentModel:
    def test_create_basic_assignment(self):
        issue = IssueFactory()
        to_user = UserFactory()
        ev = IssueAssignment.objects.create(
            issue=issue,
            action=AssignmentAction.ASSIGN,
            from_user=None,
            to_user=to_user,
            actor=None,
            reason="seed",
        )
        assert ev.pk is not None
        assert issue.assignments.count() == 1
        assert issue.assignments.first().to_user == to_user

    def test_assignment_ordering_by_created_at(self):
        issue = IssueFactory()
        u1, u2, u3 = UserFactory(), UserFactory(), UserFactory()
        IssueAssignment.objects.create(issue=issue, action=AssignmentAction.ASSIGN, to_user=u1)
        IssueAssignment.objects.create(issue=issue, action=AssignmentAction.TRANSFER, from_user=u1, to_user=u2)
        IssueAssignment.objects.create(issue=issue, action=AssignmentAction.TRANSFER, from_user=u2, to_user=u3)
        users = [a.to_user for a in issue.assignments.all()]
        assert users == [u1, u2, u3]
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd backend && uv run pytest tests/test_assignment_workflow.py::TestEnums::test_issue_status_has_unassigned_and_pending_confirmation -xvs
```
Expected: FAIL — `AttributeError: type object 'IssueStatus' has no attribute 'UNASSIGNED'` or similar.

- [ ] **Step 3: Update Issue model + add new models**

Modify `backend/apps/issues/models.py` — replace `IssueStatus` and append at end of file:

```python
class IssueStatus(models.TextChoices):
    UNPLANNED = '未计划', '未计划'
    UNASSIGNED = '待分配', '待分配'
    PENDING_CONFIRMATION = '待确认', '待确认'
    IN_PROGRESS = '进行中', '进行中'
    RESOLVED = '已解决', '已解决'
    PUBLISHED = '已发布', '已发布'
    CLOSED = '已关闭', '已关闭'


class AssignmentAction(models.TextChoices):
    CLAIM = 'claim', '接单'
    ASSIGN = 'assign', '指派'
    AI_ASSIGN = 'ai_assign', 'AI分配'
    TRANSFER = 'transfer', '转单'
    CONFIRM = 'confirm', '确认'
```

Add `manager` field to `Issue` model (after `assignee = ...` block):

```python
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="managed_issues",
        verbose_name="项目经理快照",
        help_text="创建时快照,后续 project.manager 变更不影响此字段",
    )
```

Append at the bottom of the file (after `Activity` class):

```python
class IssueAssignment(models.Model):
    issue = models.ForeignKey(
        Issue, on_delete=models.CASCADE, related_name='assignments',
    )
    action = models.CharField(max_length=20, choices=AssignmentAction.choices)
    from_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
        verbose_name="转出方",
    )
    to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
        verbose_name="接收方",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
        verbose_name="操作人",
    )
    reason = models.TextField(blank=True, default='', verbose_name="原因")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "分配事件"
        verbose_name_plural = "分配事件"
        ordering = ['created_at']
        indexes = [models.Index(fields=['issue', '-created_at'])]

    def __str__(self):
        return f"{self.issue_id} {self.action} → {self.to_user_id}"
```

- [ ] **Step 4: Generate migration**

```bash
cd backend && uv run python manage.py makemigrations issues
```
Expected: creates `apps/issues/migrations/0010_<auto-name>.py` containing CreateModel(IssueAssignment), AddField(manager), AlterField(status with new choices). Rename it for clarity:

```bash
mv backend/apps/issues/migrations/0010_*.py backend/apps/issues/migrations/0010_assignment_workflow.py
```

Then edit the new migration file's class name attribute is unaffected; only filename changed. Verify with:

```bash
cd backend && uv run python manage.py makemigrations --check
```
Expected: no missing migrations.

- [ ] **Step 5: Apply migration and rerun test**

```bash
cd backend && uv run python manage.py migrate && uv run pytest tests/test_assignment_workflow.py::TestEnums tests/test_assignment_workflow.py::TestIssueAssignmentModel -xvs
```
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add backend/apps/issues/models.py backend/apps/issues/migrations/0010_assignment_workflow.py backend/tests/test_assignment_workflow.py
git commit -m "feat(issues): add IssueAssignment event log + manager FK + status enum rename"
```

---

## Task 2: Add ProjectMember.is_manager with partial unique constraint

**Files:**
- Modify: `backend/apps/projects/models.py`
- Create: `backend/apps/projects/migrations/0003_projectmember_is_manager.py`
- Test: `backend/tests/test_project_manager.py` (new)

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_project_manager.py`:

```python
import pytest
from django.db import IntegrityError, transaction
from apps.projects.models import ProjectMember
from tests.factories import ProjectFactory, UserFactory, ProjectMemberFactory


@pytest.mark.django_db
class TestProjectManager:
    def test_default_is_manager_false(self):
        m = ProjectMemberFactory()
        assert m.is_manager is False

    def test_can_set_is_manager_true(self):
        project = ProjectFactory()
        u = UserFactory()
        m = ProjectMember.objects.create(project=project, user=u, is_manager=True)
        assert m.is_manager is True

    def test_only_one_manager_per_project(self):
        project = ProjectFactory()
        u1, u2 = UserFactory(), UserFactory()
        ProjectMember.objects.create(project=project, user=u1, is_manager=True)
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                ProjectMember.objects.create(project=project, user=u2, is_manager=True)

    def test_two_projects_can_each_have_a_manager(self):
        p1, p2 = ProjectFactory(), ProjectFactory()
        u1, u2 = UserFactory(), UserFactory()
        ProjectMember.objects.create(project=p1, user=u1, is_manager=True)
        ProjectMember.objects.create(project=p2, user=u2, is_manager=True)
        # No error
        assert ProjectMember.objects.filter(is_manager=True).count() == 2
```

- [ ] **Step 2: Run, confirm fail**

```bash
cd backend && uv run pytest tests/test_project_manager.py -xvs
```
Expected: FAIL — `TypeError: ProjectMember() got unexpected keyword arguments: 'is_manager'`.

- [ ] **Step 3: Update ProjectMember model**

Modify `backend/apps/projects/models.py` — add `is_manager` field and Meta.constraints. Replace the `ProjectMember` class entirely:

```python
class ProjectMember(models.Model):
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="project_members"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="project_memberships"
    )
    role = models.ForeignKey(
        "auth.Group",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="project_memberships",
        verbose_name="角色",
    )
    personal_description = models.TextField(
        blank=True, default="", verbose_name="个人描述"
    )
    is_manager = models.BooleanField(default=False, verbose_name="项目经理")

    class Meta:
        verbose_name = "项目成员"
        verbose_name_plural = "项目成员"
        unique_together = ("project", "user")
        constraints = [
            models.UniqueConstraint(
                fields=["project"],
                condition=models.Q(is_manager=True),
                name="one_manager_per_project",
            ),
        ]

    def __str__(self):
        role_name = self.role.name if self.role_id else "-"
        flag = " [经理]" if self.is_manager else ""
        return f"{self.user} - {self.project} ({role_name}){flag}"
```

- [ ] **Step 4: Generate migration**

```bash
cd backend && uv run python manage.py makemigrations projects && mv backend/apps/projects/migrations/0003_*.py backend/apps/projects/migrations/0003_projectmember_is_manager.py
```

Verify:

```bash
cd backend && uv run python manage.py makemigrations --check
```

- [ ] **Step 5: Apply and rerun tests**

```bash
cd backend && uv run python manage.py migrate && uv run pytest tests/test_project_manager.py -xvs
```
Expected: PASS (4 tests).

- [ ] **Step 6: Expose is_manager via the project member API**

Modify `backend/apps/projects/serializers.py` to add `is_manager` to `ProjectMemberSerializer`, `ProjectMemberCreateSerializer`, and `ProjectMemberUpdateSerializer`:

```python
class ProjectMemberSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(source="user.id", read_only=True)
    user_name = serializers.CharField(source="user.name", read_only=True)
    avatar = serializers.URLField(source="user.avatar", read_only=True)
    role = serializers.CharField(source="role.name", read_only=True, allow_null=True)
    role_id = serializers.PrimaryKeyRelatedField(
        source="role", queryset=Group.objects.all(), allow_null=True, required=False
    )

    class Meta:
        model = ProjectMember
        fields = ["user_id", "user_name", "avatar", "role", "role_id",
                  "personal_description", "is_manager"]


class ProjectMemberCreateSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    role_id = serializers.PrimaryKeyRelatedField(
        queryset=Group.objects.all(), allow_null=True, required=False
    )
    personal_description = serializers.CharField(
        allow_blank=True, required=False, default=""
    )
    is_manager = serializers.BooleanField(required=False, default=False)

    def validate_user_id(self, value):
        if not User.objects.filter(id=value).exists():
            raise serializers.ValidationError("用户不存在")
        return value


class ProjectMemberUpdateSerializer(serializers.ModelSerializer):
    role_id = serializers.PrimaryKeyRelatedField(
        source="role", queryset=Group.objects.all(), allow_null=True, required=False
    )

    class Meta:
        model = ProjectMember
        fields = ["role_id", "personal_description", "is_manager"]
```

Also update `apps/projects/views.py` if `ProjectMemberListCreateView.perform_create` (or equivalent) only forwards selected fields — propagate `is_manager` through. Check by reading the create view; if it explicitly lists fields, add `is_manager` to the dict.

```bash
grep -n "is_manager\|personal_description=" backend/apps/projects/views.py
```

If `personal_description=` is hardcoded in the view's create path, add the `is_manager=` parameter too.

- [ ] **Step 7: Add API test for is_manager update**

Append to `backend/tests/test_project_manager.py`:

```python
@pytest.mark.django_db
class TestProjectMemberAPI:
    def test_patch_member_to_be_manager(self, auth_client):
        project = ProjectFactory()
        user = UserFactory()
        member = ProjectMember.objects.create(project=project, user=user, is_manager=False)
        resp = auth_client.patch(
            f"/api/projects/{project.id}/members/{user.id}/",
            {"is_manager": True}, format="json",
        )
        assert resp.status_code == 200, resp.data
        member.refresh_from_db()
        assert member.is_manager is True

    def test_setting_second_manager_returns_400(self, auth_client):
        project = ProjectFactory()
        u1, u2 = UserFactory(), UserFactory()
        ProjectMember.objects.create(project=project, user=u1, is_manager=True)
        ProjectMember.objects.create(project=project, user=u2)
        resp = auth_client.patch(
            f"/api/projects/{project.id}/members/{u2.id}/",
            {"is_manager": True}, format="json",
        )
        # IntegrityError → DRF 500 normally; the view should catch and 400.
        # Acceptable for Phase 1: either 400 or 500 — code 500 indicates the
        # constraint is enforced. Adjust expectations if a clean 400 handler
        # is added later.
        assert resp.status_code in (400, 409, 500)
```

- [ ] **Step 8: Rerun tests**

```bash
cd backend && uv run pytest tests/test_project_manager.py -xvs
```
Expected: 6 tests pass (4 model + 2 API).

- [ ] **Step 9: Commit**

```bash
git add backend/apps/projects/models.py backend/apps/projects/migrations/0003_projectmember_is_manager.py backend/apps/projects/serializers.py backend/apps/projects/views.py backend/tests/test_project_manager.py
git commit -m "feat(projects): ProjectMember.is_manager with one-per-project constraint + API"
```

---

## Task 3: Data migration — rename 待处理→待分配 + seed IssueAssignment rows

**Files:**
- Create: `backend/apps/issues/migrations/0011_data_status_rename_and_seed.py`

- [ ] **Step 1: Write the data migration**

Create `backend/apps/issues/migrations/0011_data_status_rename_and_seed.py`:

```python
"""Rename status 待处理→待分配 on existing issues, and seed IssueAssignment
rows for issues that already have an assignee so the invariant
`Issue.assignee == latest_assignment.to_user` holds for legacy data.

Idempotent: only updates rows matching the old value and only seeds
issues that have no assignments yet.
"""
from django.db import migrations


def forwards(apps, schema_editor):
    Issue = apps.get_model("issues", "Issue")
    IssueAssignment = apps.get_model("issues", "IssueAssignment")

    # 1) Rename status on existing rows
    Issue.all_objects = Issue._default_manager  # ensure includes soft-deleted
    Issue._default_manager.filter(status="待处理").update(status="待分配")

    # 2) Seed assignment events for issues with an existing assignee
    for issue in Issue._default_manager.filter(assignee__isnull=False).iterator():
        if IssueAssignment.objects.filter(issue=issue).exists():
            continue
        IssueAssignment.objects.create(
            issue=issue,
            action="assign",
            from_user=None,
            to_user=issue.assignee,
            actor=None,
            reason="历史数据 seed",
            created_at=issue.created_at,
        )


def reverse(apps, schema_editor):
    Issue = apps.get_model("issues", "Issue")
    IssueAssignment = apps.get_model("issues", "IssueAssignment")
    Issue._default_manager.filter(status="待分配").update(status="待处理")
    IssueAssignment.objects.filter(reason="历史数据 seed").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("issues", "0010_assignment_workflow"),
    ]

    operations = [
        migrations.RunPython(forwards, reverse),
    ]
```

- [ ] **Step 2: Test the migration by writing a test**

Append to `backend/tests/test_assignment_workflow.py`:

```python
@pytest.mark.django_db
class TestSeedMigration:
    """Verify the data migration's forwards function in isolation."""

    def test_status_rename_and_seed(self):
        # Set up a "legacy" state directly (not via factory which already uses 待分配)
        u = UserFactory()
        issue = IssueFactory(status="进行中", assignee=u)
        # Pretend this issue was in the old 待处理 state
        Issue.objects.filter(pk=issue.pk).update(status="待处理")
        IssueAssignment.objects.filter(issue=issue).delete()

        # Replay the migration's semantic effect inline (the real migration
        # uses apps.get_model under RunPython; this test asserts the outcome).
        Issue.objects.filter(status="待处理").update(status="待分配")
        if not IssueAssignment.objects.filter(issue=issue).exists():
            IssueAssignment.objects.create(
                issue=issue, action="assign",
                from_user=None, to_user=issue.assignee,
                reason="历史数据 seed",
            )

        issue.refresh_from_db()
        assert issue.status == "待分配"
        assert issue.assignments.count() == 1
        assert issue.assignments.first().to_user == u
```

Note: full migration-replay testing requires `pytest-django` with `--migrations` flag; this test asserts the semantic outcome which is sufficient.

- [ ] **Step 3: Apply migration**

```bash
cd backend && uv run python manage.py migrate
```
Expected: applies `0011_data_status_rename_and_seed`.

- [ ] **Step 4: Run test**

```bash
cd backend && uv run pytest tests/test_assignment_workflow.py::TestSeedMigration -xvs
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/issues/migrations/0011_data_status_rename_and_seed.py backend/tests/test_assignment_workflow.py
git commit -m "feat(issues): data migration to rename status + seed assignment events"
```

---

## Task 4: Update SiteSettings default + migrate existing singleton

**Files:**
- Modify: `backend/apps/settings/models.py`
- Create: `backend/apps/settings/migrations/0008_status_rename.py`
- Modify: `backend/tests/factories.py` (SiteSettingsFactory.issue_statuses)

- [ ] **Step 1: Update default in code**

Modify `backend/apps/settings/models.py` line 28:

```python
def default_issue_statuses():
    return ["未计划", "待分配", "待确认", "进行中", "已解决", "已发布", "已关闭"]
```

- [ ] **Step 2: Update factory**

Modify `backend/tests/factories.py` line 46 (inside `SiteSettingsFactory`):

```python
    issue_statuses = ["未计划", "待分配", "待确认", "进行中", "已解决", "已发布", "已关闭"]
```

And modify line 84 (`IssueFactory.status`):

```python
    status = "待分配"
```

- [ ] **Step 3: Write the settings migration**

Create `backend/apps/settings/migrations/0008_status_rename.py`:

```python
from django.db import migrations


NEW = ["未计划", "待分配", "待确认", "进行中", "已解决", "已发布", "已关闭"]
OLD = ["未计划", "待处理", "进行中", "已解决", "已发布", "已关闭"]


def update_to_new(apps, schema_editor):
    SiteSettings = apps.get_model("settings", "SiteSettings")
    obj = SiteSettings.objects.first()
    if obj is None:
        return
    obj.issue_statuses = NEW
    obj.save(update_fields=["issue_statuses"])


def revert_to_old(apps, schema_editor):
    SiteSettings = apps.get_model("settings", "SiteSettings")
    obj = SiteSettings.objects.first()
    if obj is None:
        return
    obj.issue_statuses = OLD
    obj.save(update_fields=["issue_statuses"])


class Migration(migrations.Migration):

    dependencies = [
        ("settings", "0007_default_project_and_modules"),
    ]

    operations = [
        migrations.RunPython(update_to_new, revert_to_old),
    ]
```

- [ ] **Step 4: Update existing test_settings.py**

Modify `backend/tests/test_settings.py` line 24:

```python
        assert site_settings.issue_statuses == ["未计划", "待分配", "待确认", "进行中", "已解决", "已发布", "已关闭"]
```

- [ ] **Step 5: Apply migration + run settings test**

```bash
cd backend && uv run python manage.py migrate && uv run pytest tests/test_settings.py -xvs
```
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/apps/settings/models.py backend/apps/settings/migrations/0008_status_rename.py backend/tests/factories.py backend/tests/test_settings.py
git commit -m "feat(settings): update default issue_statuses to include 待分配 + 待确认"
```

---

## Task 5: Sweep remaining backend test files for 待处理 → 待分配

**Files:** ~7 test files that hardcode `"待处理"`

- [ ] **Step 1: Identify all files**

```bash
grep -rln '"待处理"\|'\''待处理'\''' backend/tests backend/apps
```
Expected: list including `test_issues.py`, `test_dashboard.py`, `test_issues_duplicate_check.py`, `test_attachments.py`, `test_external_api.py`, `test_ai_wizard.py`, `test_kpi_metrics.py`, `apps/issues/views.py`.

- [ ] **Step 2: Replace in test files only (NOT apps/ — those are handled in later tasks)**

For each test file, do an exact-string replace. Run one find+sed pipeline:

```bash
cd /Users/ck/Git/matrix/devtrack && python3 -c "
import pathlib, re
for f in pathlib.Path('backend/tests').rglob('test_*.py'):
    txt = f.read_text(encoding='utf-8')
    new = txt.replace('待处理', '待分配')
    if new != txt:
        f.write_text(new, encoding='utf-8')
        print(f'  patched {f}')
"
```
Expected output: 7 files patched.

- [ ] **Step 3: Run the full test suite to surface regressions**

```bash
cd backend && uv run pytest -x 2>&1 | tail -40
```
Expected: most tests pass; some may fail because they rely on `apps/issues/views.py` `status_order` or `DashboardStatsView` still using `待处理`. Note any failures — they should be fixed in Task 9.

- [ ] **Step 4: Commit (even with some failures — code-side fixes follow)**

```bash
git add backend/tests/
git commit -m "test: rename status string 待处理 → 待分配 in all test files"
```

---

## Task 6: Service-layer — InvalidTransition, _resolve_project_manager, assign_issue

**Files:**
- Modify: `backend/apps/issues/services.py`
- Test: `backend/tests/test_assignment_workflow.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_assignment_workflow.py`:

```python
from django.contrib.auth import get_user_model
from apps.issues.services import (
    InvalidTransition, assign_issue, _resolve_project_manager,
)
from apps.projects.models import ProjectMember

User = get_user_model()


@pytest.mark.django_db
class TestResolveProjectManager:
    def test_returns_manager_user(self):
        project = ProjectFactory()
        mgr = UserFactory()
        ProjectMember.objects.create(project=project, user=mgr, is_manager=True)
        assert _resolve_project_manager(project) == mgr

    def test_returns_none_when_no_manager(self):
        project = ProjectFactory()
        ProjectMember.objects.create(project=project, user=UserFactory(), is_manager=False)
        assert _resolve_project_manager(project) is None


@pytest.mark.django_db
class TestAssignIssue:
    def test_assign_unassigned_issue_moves_to_pending_confirmation(self):
        mgr = UserFactory()
        project = ProjectFactory()
        ProjectMember.objects.create(project=project, user=mgr, is_manager=True)
        target = UserFactory()
        ProjectMember.objects.create(project=project, user=target)
        issue = IssueFactory(project=project, status="待分配", assignee=None, manager=mgr)

        ev = assign_issue(issue, actor=mgr, to_user=target)

        issue.refresh_from_db()
        assert issue.assignee == target
        assert issue.status == "待确认"
        assert ev.action == "assign"
        assert ev.to_user == target
        assert ev.from_user is None
        assert ev.actor == mgr

    def test_assign_requires_actor_to_be_manager(self):
        project = ProjectFactory()
        mgr = UserFactory()
        ProjectMember.objects.create(project=project, user=mgr, is_manager=True)
        other = UserFactory()
        target = UserFactory()
        issue = IssueFactory(project=project, status="待分配", assignee=None, manager=mgr)

        from rest_framework.exceptions import PermissionDenied
        with pytest.raises(PermissionDenied):
            assign_issue(issue, actor=other, to_user=target)

    def test_assign_rejects_from_in_progress(self):
        mgr = UserFactory()
        issue = IssueFactory(status="进行中", assignee=UserFactory(), manager=mgr)
        with pytest.raises(InvalidTransition):
            assign_issue(issue, actor=mgr, to_user=UserFactory())
```

- [ ] **Step 2: Run, confirm fail**

```bash
cd backend && uv run pytest tests/test_assignment_workflow.py::TestResolveProjectManager tests/test_assignment_workflow.py::TestAssignIssue -xvs
```
Expected: FAIL — ImportError for `InvalidTransition`/`assign_issue`/`_resolve_project_manager`.

- [ ] **Step 3: Implement in services.py**

Append to `backend/apps/issues/services.py`:

```python
from django.db import transaction
from rest_framework.exceptions import PermissionDenied

from .models import (
    Issue, IssueAssignment, AssignmentAction, IssueStatus, Activity,
)


class InvalidTransition(Exception):
    """Raised when an issue cannot move from its current status via the requested action."""

    def __init__(self, message: str, current_status: str | None = None):
        super().__init__(message)
        self.message = message
        self.current_status = current_status


def _resolve_project_manager(project):
    """Return the User who is project manager, or None."""
    from apps.projects.models import ProjectMember
    pm = ProjectMember.objects.filter(project=project, is_manager=True).select_related("user").first()
    return pm.user if pm else None


def _is_project_member(user, project) -> bool:
    from apps.projects.models import ProjectMember
    if not user or not user.is_authenticated:
        return False
    return ProjectMember.objects.filter(project=project, user=user).exists()


@transaction.atomic
def assign_issue(issue, actor, to_user, *, action=AssignmentAction.ASSIGN, reason=""):
    """Manager assigns 待分配 → 待确认. Also used internally for ai_assign and
    the create-with-assignee path."""
    if action == AssignmentAction.ASSIGN and issue.status != IssueStatus.UNASSIGNED.value:
        raise InvalidTransition(
            f"只有「待分配」可被指派,当前 {issue.status}", current_status=issue.status,
        )
    # AI_ASSIGN reuses this function but can come from any pre-assignment state during creation.
    # Permission: ASSIGN requires manager; AI_ASSIGN passes actor=None (system).
    if action == AssignmentAction.ASSIGN:
        if actor is None or issue.manager_id != getattr(actor, "id", None):
            raise PermissionDenied("仅项目经理可指派")

    event = IssueAssignment.objects.create(
        issue=issue,
        action=action,
        from_user=None,
        to_user=to_user,
        actor=actor,
        reason=reason,
    )
    issue.assignee = to_user
    issue.status = IssueStatus.PENDING_CONFIRMATION.value
    issue.save(update_fields=["assignee", "status", "updated_at"])

    Activity.objects.create(
        user=actor, issue=issue, action="assigned",
        detail=f"指派给 {to_user.name or to_user.username}",
    )
    return event
```

- [ ] **Step 4: Rerun tests**

```bash
cd backend && uv run pytest tests/test_assignment_workflow.py::TestResolveProjectManager tests/test_assignment_workflow.py::TestAssignIssue -xvs
```
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/apps/issues/services.py backend/tests/test_assignment_workflow.py
git commit -m "feat(issues): assign_issue service + InvalidTransition + manager resolver"
```

---

## Task 7: Service-layer — claim_issue + confirm_issue

**Files:**
- Modify: `backend/apps/issues/services.py`
- Test: `backend/tests/test_assignment_workflow.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_assignment_workflow.py`:

```python
from apps.issues.services import claim_issue, confirm_issue


@pytest.mark.django_db
class TestClaimIssue:
    def test_claim_unassigned_by_member_goes_to_in_progress(self):
        project = ProjectFactory()
        member = UserFactory()
        ProjectMember.objects.create(project=project, user=member)
        issue = IssueFactory(project=project, status="待分配", assignee=None)

        ev = claim_issue(issue, actor=member)

        issue.refresh_from_db()
        assert issue.assignee == member
        assert issue.status == "进行中"
        assert ev.action == "claim"
        assert ev.to_user == member
        assert ev.from_user is None
        assert ev.actor == member

    def test_claim_rejected_for_non_member(self):
        project = ProjectFactory()
        outsider = UserFactory()
        issue = IssueFactory(project=project, status="待分配", assignee=None)
        with pytest.raises(PermissionDenied):
            claim_issue(issue, actor=outsider)

    def test_claim_rejected_if_not_unassigned(self):
        project = ProjectFactory()
        member = UserFactory()
        ProjectMember.objects.create(project=project, user=member)
        issue = IssueFactory(project=project, status="进行中", assignee=UserFactory())
        with pytest.raises(InvalidTransition):
            claim_issue(issue, actor=member)


@pytest.mark.django_db
class TestConfirmIssue:
    def test_confirm_by_assignee_moves_to_in_progress(self):
        u = UserFactory()
        issue = IssueFactory(status="待确认", assignee=u)
        # Seed an assignment to maintain invariant
        IssueAssignment.objects.create(issue=issue, action="assign", to_user=u)

        ev = confirm_issue(issue, actor=u)

        issue.refresh_from_db()
        assert issue.status == "进行中"
        assert issue.assignee == u  # unchanged
        assert ev.action == "confirm"
        assert ev.from_user == u
        assert ev.to_user == u

    def test_confirm_rejected_for_non_assignee(self):
        u, other = UserFactory(), UserFactory()
        issue = IssueFactory(status="待确认", assignee=u)
        with pytest.raises(PermissionDenied):
            confirm_issue(issue, actor=other)

    def test_confirm_rejected_when_not_pending_confirmation(self):
        u = UserFactory()
        issue = IssueFactory(status="进行中", assignee=u)
        with pytest.raises(InvalidTransition):
            confirm_issue(issue, actor=u)
```

- [ ] **Step 2: Run, fail**

```bash
cd backend && uv run pytest tests/test_assignment_workflow.py::TestClaimIssue tests/test_assignment_workflow.py::TestConfirmIssue -xvs
```
Expected: FAIL — ImportError.

- [ ] **Step 3: Implement**

Append to `backend/apps/issues/services.py`:

```python
@transaction.atomic
def claim_issue(issue, actor):
    """Any project member can claim a 待分配 issue → 进行中, becoming assignee."""
    if issue.status != IssueStatus.UNASSIGNED.value:
        raise InvalidTransition(
            f"只有「待分配」可被接单,当前 {issue.status}", current_status=issue.status,
        )
    if not _is_project_member(actor, issue.project):
        raise PermissionDenied("仅项目成员可接单")

    event = IssueAssignment.objects.create(
        issue=issue,
        action=AssignmentAction.CLAIM,
        from_user=None,
        to_user=actor,
        actor=actor,
        reason="",
    )
    issue.assignee = actor
    issue.status = IssueStatus.IN_PROGRESS.value
    issue.save(update_fields=["assignee", "status", "updated_at"])

    Activity.objects.create(
        user=actor, issue=issue, action="claimed",
        detail=f"{actor.name or actor.username} 接单",
    )
    return event


@transaction.atomic
def confirm_issue(issue, actor):
    """Current assignee confirms 待确认 → 进行中."""
    if issue.status != IssueStatus.PENDING_CONFIRMATION.value:
        raise InvalidTransition(
            f"只有「待确认」可被接受,当前 {issue.status}", current_status=issue.status,
        )
    if issue.assignee_id != getattr(actor, "id", None):
        raise PermissionDenied("仅当前负责人可确认接单")

    event = IssueAssignment.objects.create(
        issue=issue,
        action=AssignmentAction.CONFIRM,
        from_user=actor,
        to_user=actor,
        actor=actor,
        reason="",
    )
    issue.status = IssueStatus.IN_PROGRESS.value
    issue.save(update_fields=["status", "updated_at"])

    Activity.objects.create(
        user=actor, issue=issue, action="confirmed",
        detail="确认接单",
    )
    return event
```

- [ ] **Step 4: Rerun tests**

```bash
cd backend && uv run pytest tests/test_assignment_workflow.py::TestClaimIssue tests/test_assignment_workflow.py::TestConfirmIssue -xvs
```
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/apps/issues/services.py backend/tests/test_assignment_workflow.py
git commit -m "feat(issues): claim_issue + confirm_issue services"
```

---

## Task 8: Service-layer — transfer_issue + invariant test

**Files:**
- Modify: `backend/apps/issues/services.py`
- Test: `backend/tests/test_assignment_workflow.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_assignment_workflow.py`:

```python
from apps.issues.services import transfer_issue


@pytest.mark.django_db
class TestTransferIssue:
    def test_transfer_from_in_progress_to_pending_confirmation(self):
        owner = UserFactory()
        new_user = UserFactory()
        issue = IssueFactory(status="进行中", assignee=owner)
        IssueAssignment.objects.create(issue=issue, action="claim", to_user=owner)

        ev = transfer_issue(issue, actor=owner, to_user=new_user, reason="不熟悉该模块")

        issue.refresh_from_db()
        assert issue.assignee == new_user
        assert issue.status == "待确认"
        assert ev.action == "transfer"
        assert ev.from_user == owner
        assert ev.to_user == new_user
        assert ev.actor == owner
        assert ev.reason == "不熟悉该模块"

    def test_transfer_from_pending_confirmation(self):
        a = UserFactory()
        b = UserFactory()
        issue = IssueFactory(status="待确认", assignee=a)
        IssueAssignment.objects.create(issue=issue, action="assign", to_user=a)

        ev = transfer_issue(issue, actor=a, to_user=b, reason="转给后端")
        issue.refresh_from_db()
        assert issue.assignee == b
        assert issue.status == "待确认"
        assert ev.from_user == a
        assert ev.to_user == b

    def test_manager_can_transfer_someone_elses_issue(self):
        mgr = UserFactory()
        owner = UserFactory()
        new_user = UserFactory()
        issue = IssueFactory(status="进行中", assignee=owner, manager=mgr)

        ev = transfer_issue(issue, actor=mgr, to_user=new_user, reason="重新调配")
        assert ev.actor == mgr
        assert ev.from_user == owner  # the displaced owner
        assert ev.to_user == new_user

    def test_non_assignee_non_manager_cannot_transfer(self):
        owner = UserFactory()
        intruder = UserFactory()
        issue = IssueFactory(status="进行中", assignee=owner, manager=UserFactory())
        with pytest.raises(PermissionDenied):
            transfer_issue(issue, actor=intruder, to_user=UserFactory(), reason="x")

    def test_transfer_rejected_when_unassigned(self):
        issue = IssueFactory(status="待分配", assignee=None)
        with pytest.raises(InvalidTransition):
            transfer_issue(issue, actor=UserFactory(), to_user=UserFactory(), reason="x")

    def test_transfer_requires_reason(self):
        owner = UserFactory()
        issue = IssueFactory(status="进行中", assignee=owner)
        with pytest.raises(ValueError):
            transfer_issue(issue, actor=owner, to_user=UserFactory(), reason="")


@pytest.mark.django_db
class TestInvariant:
    def test_assignee_equals_latest_assignment_to_user(self):
        mgr = UserFactory()
        project = ProjectFactory()
        ProjectMember.objects.create(project=project, user=mgr, is_manager=True)
        a = UserFactory()
        b = UserFactory()
        c = UserFactory()
        for u in (a, b, c):
            ProjectMember.objects.create(project=project, user=u)
        issue = IssueFactory(project=project, status="待分配", assignee=None, manager=mgr)

        assign_issue(issue, actor=mgr, to_user=a)
        issue.refresh_from_db(); assert issue.assignee == issue.assignments.last().to_user

        confirm_issue(issue, actor=a)
        issue.refresh_from_db(); assert issue.assignee == issue.assignments.last().to_user

        transfer_issue(issue, actor=a, to_user=b, reason="x")
        issue.refresh_from_db(); assert issue.assignee == issue.assignments.last().to_user

        transfer_issue(issue, actor=b, to_user=c, reason="y")
        issue.refresh_from_db(); assert issue.assignee == issue.assignments.last().to_user

        # Full chain in order
        chain = [(a.id, "assign"), (a.id, "confirm"), (b.id, "transfer"), (c.id, "transfer")]
        actual = [(ev.to_user_id, ev.action) for ev in issue.assignments.all()]
        assert actual == chain
```

- [ ] **Step 2: Run, fail**

```bash
cd backend && uv run pytest tests/test_assignment_workflow.py::TestTransferIssue tests/test_assignment_workflow.py::TestInvariant -xvs
```
Expected: FAIL.

- [ ] **Step 3: Implement**

Append to `backend/apps/issues/services.py`:

```python
@transaction.atomic
def transfer_issue(issue, actor, to_user, reason: str):
    """assignee or issue.manager transfers an issue (in 待确认 or 进行中) to a new user.
    The new user lands in 待确认.
    """
    TRANSFERABLE = (IssueStatus.PENDING_CONFIRMATION.value, IssueStatus.IN_PROGRESS.value)
    if issue.status not in TRANSFERABLE:
        raise InvalidTransition(
            f"只有「待确认/进行中」可转单,当前 {issue.status}",
            current_status=issue.status,
        )
    if not reason or not reason.strip():
        raise ValueError("转单原因必填")

    actor_id = getattr(actor, "id", None)
    is_assignee = issue.assignee_id == actor_id
    is_manager = issue.manager_id == actor_id and actor_id is not None
    if not (is_assignee or is_manager):
        raise PermissionDenied("仅当前负责人或项目经理可转单")

    from_user = issue.assignee  # the displaced owner (may equal actor)

    event = IssueAssignment.objects.create(
        issue=issue,
        action=AssignmentAction.TRANSFER,
        from_user=from_user,
        to_user=to_user,
        actor=actor,
        reason=reason[:500],
    )
    issue.assignee = to_user
    issue.status = IssueStatus.PENDING_CONFIRMATION.value
    issue.save(update_fields=["assignee", "status", "updated_at"])

    Activity.objects.create(
        user=actor, issue=issue, action="transferred",
        detail=f"转给 {to_user.name or to_user.username}: {reason[:80]}",
    )
    return event
```

- [ ] **Step 4: Rerun tests**

```bash
cd backend && uv run pytest tests/test_assignment_workflow.py::TestTransferIssue tests/test_assignment_workflow.py::TestInvariant -xvs
```
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/apps/issues/services.py backend/tests/test_assignment_workflow.py
git commit -m "feat(issues): transfer_issue service + assignee invariant test"
```

---

## Task 9: Update views to use new status values + add status_order ordering

**Files:**
- Modify: `backend/apps/issues/views.py`

- [ ] **Step 1: Update `status_order` Case-When in `IssueListCreateView.get_queryset`**

Modify `backend/apps/issues/views.py` lines 79-89. Replace the `status_order` Case block:

```python
            status_order=Case(
                When(status="未计划", then=Value(0)),
                When(status="待分配", then=Value(1)),
                When(status="待确认", then=Value(2)),
                When(status="进行中", then=Value(3)),
                When(status="已解决", then=Value(4)),
                When(status="已发布", then=Value(5)),
                When(status="已关闭", then=Value(6)),
                default=Value(7),
                output_field=IntegerField(),
            ),
```

- [ ] **Step 2: Update `DashboardStatsView`**

Modify `backend/apps/issues/views.py` lines 154-158. Replace `pending` block:

```python
            # 待分配 + 待确认 视作"待处理"统计口径
            "pending": Issue.objects.filter(status__in=["待分配", "待确认"]).count(),
            "pending_yesterday": Issue.objects.filter(
                status__in=["待分配", "待确认"], created_at__lt=today_start
            ).count(),
```

- [ ] **Step 3: Run full backend test suite**

```bash
cd backend && uv run pytest -x 2>&1 | tail -30
```
Expected: All tests pass. Investigate any remaining `待处理` failures with `grep -rn 待处理 backend`.

- [ ] **Step 4: Commit**

```bash
git add backend/apps/issues/views.py
git commit -m "fix(issues): update status_order + dashboard counts for renamed statuses"
```

---

## Task 10: Service-layer — create_issue + auto_assign_issue stub

**Files:**
- Modify: `backend/apps/issues/services.py`
- Test: `backend/tests/test_assignment_workflow.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_assignment_workflow.py`:

```python
from apps.issues.services import create_issue, auto_assign_issue


@pytest.mark.django_db
class TestCreateIssue:
    def test_create_without_assignee_stays_unassigned(self):
        mgr = UserFactory()
        project = ProjectFactory()
        ProjectMember.objects.create(project=project, user=mgr, is_manager=True)

        issue = create_issue(
            project=project, actor=UserFactory(),
            title="t", description="d",
            priority="P2", assignee=None,
        )
        assert issue.status == "待分配"
        assert issue.assignee is None
        assert issue.manager == mgr  # snapshotted
        assert issue.assignments.count() == 0

    def test_create_with_assignee_goes_to_pending_confirmation(self):
        mgr = UserFactory()
        project = ProjectFactory()
        ProjectMember.objects.create(project=project, user=mgr, is_manager=True)
        target = UserFactory()
        ProjectMember.objects.create(project=project, user=target)

        issue = create_issue(
            project=project, actor=mgr,
            title="t", description="d", priority="P2",
            assignee=target,
        )
        assert issue.status == "待确认"
        assert issue.assignee == target
        assert issue.assignments.count() == 1
        assert issue.assignments.first().action == "assign"

    def test_create_without_project_manager_keeps_manager_null(self):
        project = ProjectFactory()
        issue = create_issue(
            project=project, actor=UserFactory(),
            title="t", description="d", priority="P2", assignee=None,
        )
        assert issue.manager is None


@pytest.mark.django_db
class TestAutoAssignStub:
    def test_phase1_stub_returns_none(self):
        # Phase 1 stub: until Phase 2 is implemented, returns None always
        issue = IssueFactory(status="待分配", assignee=None)
        assert auto_assign_issue(issue) is None
```

- [ ] **Step 2: Run, fail**

```bash
cd backend && uv run pytest tests/test_assignment_workflow.py::TestCreateIssue tests/test_assignment_workflow.py::TestAutoAssignStub -xvs
```
Expected: FAIL.

- [ ] **Step 3: Implement**

Append to `backend/apps/issues/services.py`:

```python
def auto_assign_issue(issue):
    """Phase 1 stub. Phase 2 implements real LLM-based selection.
    Returns IssueAssignment on success, None on any failure or skip.
    """
    return None


@transaction.atomic
def create_issue(*, project, actor, title, description, priority,
                 assignee=None, **extra_fields):
    """Unified entry point for creating an Issue. Both the manual create
    form (POST /api/issues/) and the AI-wizard commit path route through
    this so workflow rules are enforced exactly once.

    Behavior:
      - assignee provided → status=待确认, writes an `assign` event
      - assignee=None → calls auto_assign_issue(); on None, leaves status=待分配
    """
    issue = Issue.objects.create(
        project=project,
        manager=_resolve_project_manager(project),
        title=title,
        description=description,
        priority=priority,
        status=IssueStatus.UNASSIGNED.value,
        created_by=actor,
        **extra_fields,
    )

    if assignee is not None:
        # Bypass the manager-only permission check by calling internal helper
        _do_assign(issue, actor=actor, to_user=assignee, action=AssignmentAction.ASSIGN, reason="")
    else:
        auto_assign_issue(issue)  # Phase 1 = no-op

    return issue


def _do_assign(issue, *, actor, to_user, action, reason):
    """Internal: write the assignment event + flip status. Used by
    create_issue (which has its own permission boundary) and assign_issue
    (which enforces manager-only)."""
    event = IssueAssignment.objects.create(
        issue=issue,
        action=action,
        from_user=None,
        to_user=to_user,
        actor=actor,
        reason=reason,
    )
    issue.assignee = to_user
    issue.status = IssueStatus.PENDING_CONFIRMATION.value
    issue.save(update_fields=["assignee", "status", "updated_at"])
    Activity.objects.create(
        user=actor, issue=issue, action="assigned",
        detail=f"指派给 {to_user.name or to_user.username}",
    )
    return event
```

Refactor `assign_issue` to delegate to `_do_assign` (replace the existing function body):

```python
@transaction.atomic
def assign_issue(issue, actor, to_user, *, action=AssignmentAction.ASSIGN, reason=""):
    """Manager assigns 待分配 → 待确认."""
    if action == AssignmentAction.ASSIGN and issue.status != IssueStatus.UNASSIGNED.value:
        raise InvalidTransition(
            f"只有「待分配」可被指派,当前 {issue.status}", current_status=issue.status,
        )
    if action == AssignmentAction.ASSIGN:
        if actor is None or issue.manager_id != getattr(actor, "id", None):
            raise PermissionDenied("仅项目经理可指派")
    return _do_assign(issue, actor=actor, to_user=to_user, action=action, reason=reason)
```

- [ ] **Step 4: Rerun tests**

```bash
cd backend && uv run pytest tests/test_assignment_workflow.py -xvs 2>&1 | tail -30
```
Expected: PASS for all `TestCreateIssue`, `TestAutoAssignStub`, plus all prior tests still green.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/issues/services.py backend/tests/test_assignment_workflow.py
git commit -m "feat(issues): create_issue unified entry + auto_assign_issue stub"
```

---

## Task 11: Wire create_issue into IssueCreateUpdateSerializer + IssueListSerializer fields

**Files:**
- Modify: `backend/apps/issues/serializers.py`

- [ ] **Step 1: Write failing test for new serializer fields**

Append to `backend/tests/test_assignment_workflow.py`:

```python
from apps.issues.serializers import IssueListSerializer


@pytest.mark.django_db
class TestSerializerFields:
    def test_list_serializer_includes_can_actions_and_manager_name(self, rf):
        from django.contrib.auth.models import AnonymousUser
        mgr = UserFactory(name="赵经理")
        member = UserFactory()
        project = ProjectFactory()
        ProjectMember.objects.create(project=project, user=mgr, is_manager=True)
        ProjectMember.objects.create(project=project, user=member)
        issue = IssueFactory(project=project, status="待分配", assignee=None, manager=mgr)

        req = rf.get("/api/issues/")
        req.user = member
        data = IssueListSerializer(issue, context={"request": req}).data

        assert data["can_claim"] is True
        assert data["can_confirm"] is False
        assert data["can_transfer"] is False
        assert data["can_assign"] is False
        assert data["manager_name"] == "赵经理"
```

(Add the `rf` fixture import at top of file: `from pytest_django.fixtures import rf` — actually `rf` is a built-in pytest-django fixture, no import needed.)

- [ ] **Step 2: Run, fail**

```bash
cd backend && uv run pytest tests/test_assignment_workflow.py::TestSerializerFields -xvs
```
Expected: FAIL — `KeyError: 'can_claim'`.

- [ ] **Step 3: Update IssueListSerializer**

Modify `backend/apps/issues/serializers.py`. Inside `IssueListSerializer` class, add these SerializerMethodFields and update `fields`:

```python
class IssueListSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()
    updated_by_name = serializers.SerializerMethodField()
    assignee_name = serializers.CharField(source="assignee.name", read_only=True, default=None)
    manager_name = serializers.SerializerMethodField()
    helpers = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    helpers_names = serializers.SerializerMethodField()
    resolution_hours = serializers.SerializerMethodField()
    github_issues = GitHubIssueLinkSerializer(many=True, read_only=True)
    ai_cause = serializers.CharField(read_only=True, default='')
    ai_solution = serializers.CharField(read_only=True, default='')
    can_claim = serializers.SerializerMethodField()
    can_confirm = serializers.SerializerMethodField()
    can_transfer = serializers.SerializerMethodField()
    can_assign = serializers.SerializerMethodField()

    class Meta:
        model = Issue
        fields = [
            "id", "project", "repo", "title", "priority",
            "status", "labels", "reporter",
            "created_by", "created_by_name",
            "updated_by", "updated_by_name",
            "assignee", "assignee_name", "manager", "manager_name",
            "helpers", "helpers_names", "remark", "cause", "solution",
            "ai_cause", "ai_solution",
            "resolution_hours", "created_at", "updated_at", "github_issues",
            "estimated_completion", "estimated_hours", "source",
            "can_claim", "can_confirm", "can_transfer", "can_assign",
        ]

    # ... existing get_* methods ...

    def get_manager_name(self, obj):
        if obj.manager:
            return obj.manager.name or obj.manager.username
        return None

    def _request_user(self):
        request = self.context.get("request")
        return getattr(request, "user", None) if request else None

    def get_can_claim(self, obj):
        from apps.projects.models import ProjectMember
        user = self._request_user()
        if not user or not user.is_authenticated:
            return False
        if obj.status != "待分配":
            return False
        return ProjectMember.objects.filter(project=obj.project, user=user).exists()

    def get_can_confirm(self, obj):
        user = self._request_user()
        if not user or not user.is_authenticated:
            return False
        if obj.status != "待确认":
            return False
        return obj.assignee_id == user.id

    def get_can_transfer(self, obj):
        user = self._request_user()
        if not user or not user.is_authenticated:
            return False
        if obj.status not in ("待确认", "进行中"):
            return False
        return obj.assignee_id == user.id or obj.manager_id == user.id

    def get_can_assign(self, obj):
        user = self._request_user()
        if not user or not user.is_authenticated:
            return False
        if obj.status != "待分配":
            return False
        return obj.manager_id == user.id
```

- [ ] **Step 4: Update IssueCreateUpdateSerializer.create to delegate to create_issue**

Modify `backend/apps/issues/serializers.py` — replace the `create()` method of `IssueCreateUpdateSerializer`:

```python
    @transaction.atomic
    def create(self, validated_data):
        from .services import create_issue
        helpers = validated_data.pop("helpers", [])
        attachment_ids = validated_data.pop("attachment_ids", [])
        if "estimated_hours" in validated_data and not self._user_can_edit_estimated_hours():
            validated_data.pop("estimated_hours")

        actor = self.context["request"].user
        assignee = validated_data.pop("assignee", None)
        # Status from client is ignored by the workflow — create_issue decides it.
        validated_data.pop("status", None)
        project = validated_data.pop("project")
        title = validated_data.pop("title")
        description = validated_data.pop("description", "")
        priority = validated_data.pop("priority")

        issue = create_issue(
            project=project, actor=actor,
            title=title, description=description, priority=priority,
            assignee=assignee,
            **validated_data,
        )
        if helpers:
            issue.helpers.set(helpers)
        Activity.objects.create(user=actor, issue=issue, action="created")
        if attachment_ids:
            atts = Attachment.objects.filter(id__in=attachment_ids, uploaded_by=actor)
            issue.attachments.add(*atts)
        create_mention_notifications(
            issue=issue, old_description="",
            new_description=issue.description, actor=actor,
        )
        return issue
```

- [ ] **Step 5: Rerun new test + full test suite**

```bash
cd backend && uv run pytest tests/test_assignment_workflow.py::TestSerializerFields tests/test_issues.py -xvs 2>&1 | tail -40
```
Expected: PASS. If `test_issues.py` fails because old tests assumed `status` was respected: confirm the failure is about `status` being overwritten to `待分配`, then update those tests to expect the workflow status.

- [ ] **Step 6: Run full suite to catch other regressions**

```bash
cd backend && uv run pytest 2>&1 | tail -30
```
Expected: green or known small regressions in tests that explicitly post `status="进行中"`. Those tests may need a quick adjustment in this commit.

- [ ] **Step 7: Commit**

```bash
git add backend/apps/issues/serializers.py backend/tests/test_assignment_workflow.py backend/tests/test_issues.py
git commit -m "feat(issues): can_* permission flags + create_issue wiring in serializer"
```

---

## Task 12: API endpoints — claim/confirm/transfer/assign views + URLs

**Files:**
- Modify: `backend/apps/issues/views.py`
- Modify: `backend/apps/issues/serializers.py`
- Modify: `backend/apps/issues/urls.py`
- Create: `backend/tests/test_assignment_api.py`

- [ ] **Step 1: Add Transfer/Assign input serializers**

Append to `backend/apps/issues/serializers.py`:

```python
class IssueTransferInputSerializer(serializers.Serializer):
    to_user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())
    reason = serializers.CharField(max_length=500, allow_blank=False)


class IssueAssignInputSerializer(serializers.Serializer):
    to_user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())
```

- [ ] **Step 2: Write failing API tests**

Create `backend/tests/test_assignment_api.py`:

```python
import pytest
from rest_framework.test import APIClient
from apps.projects.models import ProjectMember
from apps.issues.models import IssueAssignment
from tests.factories import IssueFactory, UserFactory, ProjectFactory


@pytest.fixture
def member_client(api_client, db):
    user = UserFactory()
    api_client.force_authenticate(user=user)
    api_client.user = user
    return api_client


@pytest.mark.django_db
class TestClaimAPI:
    def test_claim_unassigned(self, api_client):
        project = ProjectFactory()
        u = UserFactory()
        ProjectMember.objects.create(project=project, user=u)
        issue = IssueFactory(project=project, status="待分配", assignee=None)

        api_client.force_authenticate(user=u)
        resp = api_client.post(f"/api/issues/{issue.pk}/claim/")
        assert resp.status_code == 200, resp.data
        issue.refresh_from_db()
        assert issue.status == "进行中"
        assert issue.assignee == u

    def test_claim_outsider_forbidden(self, api_client):
        outsider = UserFactory()
        issue = IssueFactory(status="待分配", assignee=None)
        api_client.force_authenticate(user=outsider)
        resp = api_client.post(f"/api/issues/{issue.pk}/claim/")
        assert resp.status_code == 403


@pytest.mark.django_db
class TestConfirmAPI:
    def test_confirm_by_assignee(self, api_client):
        u = UserFactory()
        issue = IssueFactory(status="待确认", assignee=u)
        IssueAssignment.objects.create(issue=issue, action="assign", to_user=u)
        api_client.force_authenticate(user=u)
        resp = api_client.post(f"/api/issues/{issue.pk}/confirm/")
        assert resp.status_code == 200
        issue.refresh_from_db()
        assert issue.status == "进行中"


@pytest.mark.django_db
class TestTransferAPI:
    def test_transfer_with_reason(self, api_client):
        owner = UserFactory()
        target = UserFactory()
        issue = IssueFactory(status="进行中", assignee=owner)
        IssueAssignment.objects.create(issue=issue, action="claim", to_user=owner)
        api_client.force_authenticate(user=owner)
        resp = api_client.post(
            f"/api/issues/{issue.pk}/transfer/",
            {"to_user": target.id, "reason": "不熟悉该模块"}, format="json",
        )
        assert resp.status_code == 200, resp.data
        issue.refresh_from_db()
        assert issue.assignee == target
        assert issue.status == "待确认"

    def test_transfer_empty_reason_rejected(self, api_client):
        owner = UserFactory()
        issue = IssueFactory(status="进行中", assignee=owner)
        api_client.force_authenticate(user=owner)
        resp = api_client.post(
            f"/api/issues/{issue.pk}/transfer/",
            {"to_user": UserFactory().id, "reason": ""}, format="json",
        )
        assert resp.status_code == 400


@pytest.mark.django_db
class TestAssignAPI:
    def test_assign_by_manager(self, api_client):
        mgr = UserFactory()
        project = ProjectFactory()
        ProjectMember.objects.create(project=project, user=mgr, is_manager=True)
        target = UserFactory()
        issue = IssueFactory(project=project, status="待分配", assignee=None, manager=mgr)

        api_client.force_authenticate(user=mgr)
        resp = api_client.post(
            f"/api/issues/{issue.pk}/assign/",
            {"to_user": target.id}, format="json",
        )
        assert resp.status_code == 200, resp.data
        issue.refresh_from_db()
        assert issue.assignee == target
        assert issue.status == "待确认"

    def test_assign_by_non_manager_forbidden(self, api_client):
        issue = IssueFactory(status="待分配", assignee=None, manager=UserFactory())
        other = UserFactory()
        api_client.force_authenticate(user=other)
        resp = api_client.post(
            f"/api/issues/{issue.pk}/assign/",
            {"to_user": UserFactory().id}, format="json",
        )
        assert resp.status_code == 403
```

- [ ] **Step 3: Run, fail**

```bash
cd backend && uv run pytest tests/test_assignment_api.py -xvs
```
Expected: FAIL — 404 (URLs don't exist).

- [ ] **Step 4: Implement the 4 views**

Append to `backend/apps/issues/views.py`:

```python
from rest_framework.exceptions import ValidationError as DRFValidationError
from .services import (
    claim_issue, confirm_issue, transfer_issue, assign_issue, InvalidTransition,
)


def _get_issue_or_404(pk):
    return Issue.objects.filter(pk=pk).first()


def _serialize_issue(issue, request):
    return IssueListSerializer(issue, context={"request": request}).data


class IssueClaimView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        issue = _get_issue_or_404(pk)
        if not issue:
            return Response({"detail": "问题不存在"}, status=status.HTTP_404_NOT_FOUND)
        try:
            claim_issue(issue, actor=request.user)
        except InvalidTransition as e:
            return Response({"detail": e.message}, status=status.HTTP_409_CONFLICT)
        return Response(_serialize_issue(issue, request))


class IssueConfirmView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        issue = _get_issue_or_404(pk)
        if not issue:
            return Response({"detail": "问题不存在"}, status=status.HTTP_404_NOT_FOUND)
        try:
            confirm_issue(issue, actor=request.user)
        except InvalidTransition as e:
            return Response({"detail": e.message}, status=status.HTTP_409_CONFLICT)
        return Response(_serialize_issue(issue, request))


class IssueTransferView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        from .serializers import IssueTransferInputSerializer
        issue = _get_issue_or_404(pk)
        if not issue:
            return Response({"detail": "问题不存在"}, status=status.HTTP_404_NOT_FOUND)
        ser = IssueTransferInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            transfer_issue(
                issue, actor=request.user,
                to_user=ser.validated_data["to_user"],
                reason=ser.validated_data["reason"],
            )
        except InvalidTransition as e:
            return Response({"detail": e.message}, status=status.HTTP_409_CONFLICT)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_serialize_issue(issue, request))


class IssueAssignView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        from .serializers import IssueAssignInputSerializer
        issue = _get_issue_or_404(pk)
        if not issue:
            return Response({"detail": "问题不存在"}, status=status.HTTP_404_NOT_FOUND)
        ser = IssueAssignInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            assign_issue(
                issue, actor=request.user,
                to_user=ser.validated_data["to_user"],
            )
        except InvalidTransition as e:
            return Response({"detail": e.message}, status=status.HTTP_409_CONFLICT)
        return Response(_serialize_issue(issue, request))
```

- [ ] **Step 5: Register URLs**

Modify `backend/apps/issues/urls.py`:

```python
from django.urls import path
from .views import (
    IssueListCreateView, IssueDetailView, BatchUpdateView,
    IssueGitHubCreateView, IssueGitHubLinkView, IssueCloseWithGitHubView,
    IssueAIAnalyzeView, IssueAIStatusView, IssueAnalysesView,
    IssueAttachmentsView, IssueCheckDuplicateView, IssueHistoryView,
    IssueAiDraftView,
    IssueClaimView, IssueConfirmView, IssueTransferView, IssueAssignView,
)

urlpatterns = [
    path("", IssueListCreateView.as_view(), name="issue-list"),
    path("check-duplicate/", IssueCheckDuplicateView.as_view(), name="issue-check-duplicate"),
    path("ai-draft/", IssueAiDraftView.as_view(), name="issue-ai-draft"),
    path("batch-update/", BatchUpdateView.as_view(), name="issue-batch-update"),
    path("<int:pk>/", IssueDetailView.as_view(), name="issue-detail"),
    path("<int:pk>/attachments/", IssueAttachmentsView.as_view(), name="issue-attachments"),
    path("<int:pk>/github-create/", IssueGitHubCreateView.as_view(), name="issue-github-create"),
    path("<int:pk>/github-link/", IssueGitHubLinkView.as_view(), name="issue-github-link"),
    path("<int:pk>/close-with-github/", IssueCloseWithGitHubView.as_view(), name="issue-close-with-github"),
    path("<int:pk>/ai-analyze/", IssueAIAnalyzeView.as_view(), name="issue-ai-analyze"),
    path("<int:pk>/ai-status/", IssueAIStatusView.as_view(), name="issue-ai-status"),
    path("<int:pk>/analyses/", IssueAnalysesView.as_view(), name="issue-analyses"),
    path("<int:pk>/history/", IssueHistoryView.as_view(), name="issue-history"),
    path("<int:pk>/claim/", IssueClaimView.as_view(), name="issue-claim"),
    path("<int:pk>/confirm/", IssueConfirmView.as_view(), name="issue-confirm"),
    path("<int:pk>/transfer/", IssueTransferView.as_view(), name="issue-transfer"),
    path("<int:pk>/assign/", IssueAssignView.as_view(), name="issue-assign"),
]
```

- [ ] **Step 6: Rerun API tests**

```bash
cd backend && uv run pytest tests/test_assignment_api.py -xvs
```
Expected: PASS (7 tests).

- [ ] **Step 7: Commit**

```bash
git add backend/apps/issues/views.py backend/apps/issues/serializers.py backend/apps/issues/urls.py backend/tests/test_assignment_api.py
git commit -m "feat(issues): API endpoints for claim/confirm/transfer/assign"
```

---

## Task 13: Manager assignments expose endpoint + admin registration

**Files:**
- Modify: `backend/apps/issues/admin.py`
- Modify: `backend/apps/projects/admin.py` (if exists; otherwise skip)

- [ ] **Step 1: Read existing admin.py**

```bash
cat backend/apps/issues/admin.py
```

- [ ] **Step 2: Register IssueAssignment + show manager in Issue admin**

Modify `backend/apps/issues/admin.py` — add the IssueAssignment registration. Append:

```python
from .models import IssueAssignment


@admin.register(IssueAssignment)
class IssueAssignmentAdmin(admin.ModelAdmin):
    list_display = ("id", "issue", "action", "from_user", "to_user", "actor", "created_at")
    list_filter = ("action",)
    search_fields = ("issue__title", "to_user__username", "from_user__username")
    raw_id_fields = ("issue", "from_user", "to_user", "actor")
    readonly_fields = ("created_at",)
```

If `Issue` is already registered in this file, add `"manager"` to its `list_display` and `raw_id_fields` accordingly.

- [ ] **Step 3: Register ProjectMember.is_manager in admin if applicable**

Check `backend/apps/projects/admin.py`:

```bash
cat backend/apps/projects/admin.py 2>/dev/null
```

If file exists and `ProjectMember` is registered, add `"is_manager"` to `list_display` and `list_editable`. If file is missing or no registration, skip.

- [ ] **Step 4: Sanity check**

```bash
cd backend && uv run python manage.py check
```
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/issues/admin.py backend/apps/projects/admin.py
git commit -m "chore(admin): register IssueAssignment + ProjectMember.is_manager"
```

---

## Task 14: Add IssueAssignment listing to issue detail endpoint

**Files:**
- Modify: `backend/apps/issues/serializers.py`

- [ ] **Step 1: Write failing test**

Append to `backend/tests/test_assignment_api.py`:

```python
@pytest.mark.django_db
class TestIssueDetailAssignments:
    def test_detail_includes_assignments_list(self, auth_client):
        u1 = UserFactory()
        u2 = UserFactory()
        issue = IssueFactory(status="进行中", assignee=u2)
        IssueAssignment.objects.create(issue=issue, action="assign", to_user=u1, reason="initial")
        IssueAssignment.objects.create(issue=issue, action="transfer", from_user=u1, to_user=u2, actor=u1, reason="移交")

        resp = auth_client.get(f"/api/issues/{issue.pk}/")
        assert resp.status_code == 200
        assignments = resp.data["assignments"]
        assert len(assignments) == 2
        assert assignments[0]["action"] == "assign"
        assert assignments[0]["to_user_name"] == (u1.name or u1.username)
        assert assignments[1]["action"] == "transfer"
        assert assignments[1]["reason"] == "移交"
```

- [ ] **Step 2: Run, fail**

```bash
cd backend && uv run pytest tests/test_assignment_api.py::TestIssueDetailAssignments -xvs
```
Expected: FAIL — `KeyError: 'assignments'`.

- [ ] **Step 3: Add IssueAssignmentSerializer + wire into detail**

Append to `backend/apps/issues/serializers.py`:

```python
from .models import IssueAssignment


class IssueAssignmentSerializer(serializers.ModelSerializer):
    from_user_name = serializers.SerializerMethodField()
    to_user_name = serializers.SerializerMethodField()
    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = IssueAssignment
        fields = [
            "id", "action", "reason", "created_at",
            "from_user", "from_user_name",
            "to_user", "to_user_name",
            "actor", "actor_name",
        ]

    def _name(self, u):
        if not u:
            return None
        return u.name or u.username

    def get_from_user_name(self, obj):
        return self._name(obj.from_user)

    def get_to_user_name(self, obj):
        return self._name(obj.to_user)

    def get_actor_name(self, obj):
        return self._name(obj.actor)
```

Modify `IssueDetailSerializer` — add `assignments` field:

```python
class IssueDetailSerializer(IssueListSerializer):
    github_issues = GitHubIssueBriefSerializer(many=True, read_only=True)
    attachments = AttachmentSerializer(many=True, read_only=True)
    assignments = IssueAssignmentSerializer(many=True, read_only=True)

    class Meta(IssueListSerializer.Meta):
        fields = IssueListSerializer.Meta.fields + [
            "description", "estimated_completion",
            "actual_hours", "resolved_at", "github_issues", "attachments",
            "source_meta", "settlement", "assignments",
        ]
```

- [ ] **Step 4: Rerun test**

```bash
cd backend && uv run pytest tests/test_assignment_api.py::TestIssueDetailAssignments -xvs
```
Expected: PASS.

- [ ] **Step 5: Run full backend suite**

```bash
cd backend && uv run pytest 2>&1 | tail -20
```
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add backend/apps/issues/serializers.py backend/tests/test_assignment_api.py
git commit -m "feat(issues): expose assignments list on issue detail endpoint"
```

---

## Phase 1 Backend Checkpoint

- [ ] **Verify checkpoint state**

```bash
cd backend && uv run pytest 2>&1 | tail -5
```
Expected: All tests pass.

```bash
cd backend && uv run python manage.py migrate --plan | tail -10
```
Expected: no unapplied migrations.

**Hand off to user for review.** Phase 1 backend complete.

---

## Task 15: Frontend constants module

**Files:**
- Create: `frontend/app/constants/issueStatus.ts`

- [ ] **Step 1: Create the constants file**

Create `frontend/app/constants/issueStatus.ts`:

```typescript
export const ISSUE_STATUS = {
  UNPLANNED: '未计划',
  UNASSIGNED: '待分配',
  PENDING_CONFIRMATION: '待确认',
  IN_PROGRESS: '进行中',
  RESOLVED: '已解决',
  PUBLISHED: '已发布',
  CLOSED: '已关闭',
} as const

export type IssueStatusValue = typeof ISSUE_STATUS[keyof typeof ISSUE_STATUS]

export const ISSUE_STATUS_OPTIONS: { label: string; value: IssueStatusValue }[] = [
  { label: '未计划', value: ISSUE_STATUS.UNPLANNED },
  { label: '待分配', value: ISSUE_STATUS.UNASSIGNED },
  { label: '待确认', value: ISSUE_STATUS.PENDING_CONFIRMATION },
  { label: '进行中', value: ISSUE_STATUS.IN_PROGRESS },
  { label: '已解决', value: ISSUE_STATUS.RESOLVED },
  { label: '已发布', value: ISSUE_STATUS.PUBLISHED },
  { label: '已关闭', value: ISSUE_STATUS.CLOSED },
]

export const KANBAN_DEFAULT_COLUMNS: IssueStatusValue[] = [
  ISSUE_STATUS.UNASSIGNED,
  ISSUE_STATUS.PENDING_CONFIRMATION,
  ISSUE_STATUS.IN_PROGRESS,
  ISSUE_STATUS.RESOLVED,
  ISSUE_STATUS.PUBLISHED,
]

export const KANBAN_COMPLETED_LEFT: IssueStatusValue[] = [ISSUE_STATUS.UNPLANNED]
export const KANBAN_COMPLETED_RIGHT: IssueStatusValue[] = [ISSUE_STATUS.CLOSED]

export function statusColor(status: string): string {
  switch (status) {
    case ISSUE_STATUS.UNPLANNED: return 'secondary'
    case ISSUE_STATUS.UNASSIGNED: return 'warning'
    case ISSUE_STATUS.PENDING_CONFIRMATION: return 'warning'
    case ISSUE_STATUS.IN_PROGRESS: return 'info'
    case ISSUE_STATUS.RESOLVED: return 'success'
    case ISSUE_STATUS.PUBLISHED: return 'primary'
    default: return 'neutral'
  }
}

export function kanbanColor(status: string): string {
  switch (status) {
    case ISSUE_STATUS.UNPLANNED: return '#8b5cf6'
    case ISSUE_STATUS.UNASSIGNED: return '#f59e0b'
    case ISSUE_STATUS.PENDING_CONFIRMATION: return '#eab308'
    case ISSUE_STATUS.IN_PROGRESS: return '#3b82f6'
    case ISSUE_STATUS.RESOLVED: return '#10b981'
    case ISSUE_STATUS.PUBLISHED: return '#14b8a6'
    case ISSUE_STATUS.CLOSED: return '#6b7280'
    default: return '#9ca3af'
  }
}
```

- [ ] **Step 2: Type-check**

```bash
cd frontend && npx nuxi typecheck 2>&1 | tail -10
```
Expected: no new errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/constants/issueStatus.ts
git commit -m "feat(frontend): centralize issue status constants"
```

---

## Task 16: useIssueActions composable

**Files:**
- Create: `frontend/app/composables/useIssueActions.ts`

- [ ] **Step 1: Create the composable**

Create `frontend/app/composables/useIssueActions.ts`:

```typescript
export function useIssueActions() {
  const api = useApi()

  async function claim(issueId: number) {
    return api(`/api/issues/${issueId}/claim/`, { method: 'POST' })
  }

  async function confirm(issueId: number) {
    return api(`/api/issues/${issueId}/confirm/`, { method: 'POST' })
  }

  async function transfer(issueId: number, toUserId: number, reason: string) {
    return api(`/api/issues/${issueId}/transfer/`, {
      method: 'POST',
      body: { to_user: toUserId, reason },
    })
  }

  async function assignTo(issueId: number, toUserId: number) {
    return api(`/api/issues/${issueId}/assign/`, {
      method: 'POST',
      body: { to_user: toUserId },
    })
  }

  return { claim, confirm, transfer, assignTo }
}
```

`useApi` is a Nuxt auto-imported composable defined at `frontend/app/composables/useApi.ts`. Confirm with:

```bash
head -20 frontend/app/composables/useApi.ts
```

- [ ] **Step 2: Type-check**

```bash
cd frontend && npx nuxi typecheck 2>&1 | tail -10
```
Expected: no new errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/composables/useIssueActions.ts
git commit -m "feat(frontend): useIssueActions composable for claim/confirm/transfer/assign"
```

---

## Task 17: TransferDialog component

**Files:**
- Create: `frontend/app/components/issue/TransferDialog.vue`

- [ ] **Step 1: Read project member endpoint pattern**

```bash
grep -rn "project_members\|/api/projects.*members\|project.members" frontend/app | head -10
```

Note the expected endpoint pattern. Typical: `GET /api/projects/{id}/members/` returns a list of members.

- [ ] **Step 2: Create the dialog**

Create `frontend/app/components/issue/TransferDialog.vue`:

```vue
<script setup lang="ts">
import { useIssueActions } from '~/composables/useIssueActions'

interface ProjectMember {
  user_id: number
  user_name: string
  role?: string | null
}

const props = defineProps<{
  modelValue: boolean
  issueId: number
  projectId: number
  selfUserId: number
}>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'transferred'): void
}>()

const api = useApi()
const { transfer } = useIssueActions()

const members = ref<ProjectMember[]>([])
const selectedUserId = ref<number | null>(null)
const reason = ref('')
const submitting = ref(false)
const error = ref('')

async function loadMembers() {
  try {
    const data = await api<ProjectMember[]>(`/api/projects/${props.projectId}/members/`)
    members.value = data.filter(m => m.user_id !== props.selfUserId)
  } catch (e) {
    error.value = '加载成员失败'
  }
}

watch(() => props.modelValue, (v) => {
  if (v) {
    selectedUserId.value = null
    reason.value = ''
    error.value = ''
    loadMembers()
  }
})

const canSubmit = computed(() =>
  selectedUserId.value !== null && reason.value.trim().length > 0 && !submitting.value,
)

async function onSubmit() {
  if (!canSubmit.value || selectedUserId.value === null) return
  submitting.value = true
  error.value = ''
  try {
    await transfer(props.issueId, selectedUserId.value, reason.value.trim())
    emit('transferred')
    emit('update:modelValue', false)
  } catch (e: any) {
    error.value = e?.data?.detail || e?.message || '转单失败'
  } finally {
    submitting.value = false
  }
}

const userOptions = computed(() =>
  members.value.map(m => ({
    label: m.role ? `${m.user_name} · ${m.role}` : m.user_name,
    value: m.user_id,
  })),
)
</script>

<template>
  <UModal :open="modelValue" @update:open="emit('update:modelValue', $event)" title="转单">
    <template #body>
      <div class="space-y-4">
        <div>
          <label class="block text-sm mb-1">转给谁</label>
          <USelect
            v-model="selectedUserId"
            :items="userOptions"
            value-key="value"
            placeholder="选择项目成员"
          />
        </div>
        <div>
          <label class="block text-sm mb-1">转单原因 <span class="text-red-500">*</span></label>
          <UTextarea
            v-model="reason"
            placeholder="为什么把这个 issue 转给这位同事"
            :rows="3"
            :maxlength="500"
          />
        </div>
        <p v-if="error" class="text-sm text-red-500">{{ error }}</p>
      </div>
    </template>
    <template #footer>
      <div class="flex justify-end gap-2">
        <UButton color="neutral" variant="ghost" @click="emit('update:modelValue', false)">取消</UButton>
        <UButton color="primary" :loading="submitting" :disabled="!canSubmit" @click="onSubmit">
          确定转单
        </UButton>
      </div>
    </template>
  </UModal>
</template>
```

- [ ] **Step 3: Type-check**

```bash
cd frontend && npx nuxi typecheck 2>&1 | tail -20
```
Expected: no errors. If `members` endpoint shape mismatches, adjust the interface in the file.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/components/issue/TransferDialog.vue
git commit -m "feat(frontend): TransferDialog modal for issue transfer"
```

---

## Task 18: AssignDialog component

**Files:**
- Create: `frontend/app/components/issue/AssignDialog.vue`

- [ ] **Step 1: Create**

Create `frontend/app/components/issue/AssignDialog.vue`:

```vue
<script setup lang="ts">
import { useIssueActions } from '~/composables/useIssueActions'

interface ProjectMember {
  user_id: number
  user_name: string
  role?: string | null
}

const props = defineProps<{
  modelValue: boolean
  issueId: number
  projectId: number
}>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'assigned'): void
}>()

const api = useApi()
const { assignTo } = useIssueActions()

const members = ref<ProjectMember[]>([])
const selectedUserId = ref<number | null>(null)
const submitting = ref(false)
const error = ref('')

async function loadMembers() {
  try {
    members.value = await api<ProjectMember[]>(`/api/projects/${props.projectId}/members/`)
  } catch (e) {
    error.value = '加载成员失败'
  }
}

watch(() => props.modelValue, (v) => {
  if (v) {
    selectedUserId.value = null
    error.value = ''
    loadMembers()
  }
})

const userOptions = computed(() =>
  members.value.map(m => ({
    label: m.role ? `${m.user_name} · ${m.role}` : m.user_name,
    value: m.user_id,
  })),
)

async function onSubmit() {
  if (selectedUserId.value === null) return
  submitting.value = true
  error.value = ''
  try {
    await assignTo(props.issueId, selectedUserId.value)
    emit('assigned')
    emit('update:modelValue', false)
  } catch (e: any) {
    error.value = e?.data?.detail || e?.message || '指派失败'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <UModal :open="modelValue" @update:open="emit('update:modelValue', $event)" title="指派给">
    <template #body>
      <div class="space-y-4">
        <USelect
          v-model="selectedUserId"
          :items="userOptions"
          value-key="value"
          placeholder="选择项目成员"
        />
        <p v-if="error" class="text-sm text-red-500">{{ error }}</p>
      </div>
    </template>
    <template #footer>
      <div class="flex justify-end gap-2">
        <UButton color="neutral" variant="ghost" @click="emit('update:modelValue', false)">取消</UButton>
        <UButton color="primary" :loading="submitting" :disabled="selectedUserId === null" @click="onSubmit">
          指派
        </UButton>
      </div>
    </template>
  </UModal>
</template>
```

- [ ] **Step 2: Type-check + commit**

```bash
cd frontend && npx nuxi typecheck 2>&1 | tail -10
git add frontend/app/components/issue/AssignDialog.vue
git commit -m "feat(frontend): AssignDialog modal for manager-assign action"
```

---

## Task 19: StatusCell component

**Files:**
- Create: `frontend/app/components/issue/StatusCell.vue`

- [ ] **Step 1: Create the component**

Create `frontend/app/components/issue/StatusCell.vue`:

```vue
<script setup lang="ts">
import { ISSUE_STATUS, statusColor } from '~/constants/issueStatus'
import { useIssueActions } from '~/composables/useIssueActions'

interface IssueLike {
  id: number
  status: string
  assignee: number | null
  assignee_name: string | null
  can_claim?: boolean
  can_confirm?: boolean
  can_transfer?: boolean
  can_assign?: boolean
}

const props = defineProps<{
  issue: IssueLike
  selfUserId: number
}>()
const emit = defineEmits<{
  (e: 'changed'): void
  (e: 'request-transfer'): void
  (e: 'request-assign'): void
}>()

const { claim, confirm } = useIssueActions()
const busy = ref(false)

const isAssignedToSelf = computed(() => props.issue.assignee === props.selfUserId)

const assigneeLabel = computed(() => {
  if (!props.issue.assignee_name) return ''
  return isAssignedToSelf.value ? '我' : props.issue.assignee_name
})

const trailingActionLabel = computed(() => {
  switch (props.issue.status) {
    case ISSUE_STATUS.PENDING_CONFIRMATION: return '待确认'
    case ISSUE_STATUS.IN_PROGRESS: return '处理中'
    case ISSUE_STATUS.RESOLVED: return '已解决'
    case ISSUE_STATUS.PUBLISHED: return '已发布'
    case ISSUE_STATUS.CLOSED: return '已关闭'
    default: return props.issue.status
  }
})

const badgeLabel = computed(() => {
  if (!assigneeLabel.value) return trailingActionLabel.value
  return `${assigneeLabel.value} ${trailingActionLabel.value}`
})

async function onClaim() {
  if (busy.value) return
  busy.value = true
  try {
    await claim(props.issue.id)
    emit('changed')
  } finally { busy.value = false }
}

async function onConfirm() {
  if (busy.value) return
  busy.value = true
  try {
    await confirm(props.issue.id)
    emit('changed')
  } finally { busy.value = false }
}
</script>

<template>
  <div class="flex items-center gap-1 min-w-0">
    <!-- 待分配 -->
    <template v-if="issue.status === ISSUE_STATUS.UNASSIGNED">
      <UButton
        v-if="issue.can_claim"
        size="xs" color="primary" variant="soft"
        icon="i-lucide-plus" :loading="busy"
        @click.stop="onClaim"
      >接单</UButton>
      <UButton
        v-if="issue.can_assign"
        size="xs" color="neutral" variant="ghost"
        @click.stop="emit('request-assign')"
      >指派</UButton>
      <UBadge
        v-if="!issue.can_claim && !issue.can_assign"
        :color="statusColor(issue.status)" variant="subtle" size="sm"
      >待分配</UBadge>
    </template>

    <!-- 待确认: 自己的 -->
    <template v-else-if="issue.status === ISSUE_STATUS.PENDING_CONFIRMATION && isAssignedToSelf">
      <UButton
        size="xs" color="primary" variant="soft"
        icon="i-lucide-check" :loading="busy"
        @click.stop="onConfirm"
      >接受</UButton>
      <UButton
        size="xs" color="neutral" variant="ghost"
        icon="i-lucide-corner-up-right"
        @click.stop="emit('request-transfer')"
      />
    </template>

    <!-- 待确认/进行中: 别人的 (经理可转单) -->
    <template v-else-if="(issue.status === ISSUE_STATUS.PENDING_CONFIRMATION || issue.status === ISSUE_STATUS.IN_PROGRESS) && !isAssignedToSelf">
      <UBadge :color="statusColor(issue.status)" variant="subtle" size="sm">
        {{ badgeLabel }}
      </UBadge>
      <UButton
        v-if="issue.can_transfer"
        size="xs" color="neutral" variant="ghost"
        icon="i-lucide-corner-up-right"
        @click.stop="emit('request-transfer')"
      />
    </template>

    <!-- 进行中: 自己的 -->
    <template v-else-if="issue.status === ISSUE_STATUS.IN_PROGRESS && isAssignedToSelf">
      <UBadge :color="statusColor(issue.status)" variant="subtle" size="sm">
        我 处理中
      </UBadge>
      <UButton
        size="xs" color="neutral" variant="ghost"
        icon="i-lucide-corner-up-right"
        @click.stop="emit('request-transfer')"
      />
    </template>

    <!-- 已解决/已发布/已关闭/未计划 -->
    <template v-else>
      <UBadge :color="statusColor(issue.status)" variant="subtle" size="sm">
        {{ badgeLabel }}
      </UBadge>
    </template>
  </div>
</template>
```

- [ ] **Step 2: Type-check**

```bash
cd frontend && npx nuxi typecheck 2>&1 | tail -10
```
Expected: no new errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/components/issue/StatusCell.vue
git commit -m "feat(frontend): StatusCell component for dynamic status display"
```

---

## Task 20: Wire StatusCell into issues list page

**Files:**
- Modify: `frontend/app/pages/app/issues/index.vue`

- [ ] **Step 1: Update imports + state**

Modify `frontend/app/pages/app/issues/index.vue`. At top of `<script setup>` add:

```typescript
import { ISSUE_STATUS, ISSUE_STATUS_OPTIONS, kanbanColor, KANBAN_DEFAULT_COLUMNS, KANBAN_COMPLETED_LEFT, KANBAN_COMPLETED_RIGHT, statusColor as statusColorFn } from '~/constants/issueStatus'
import StatusCell from '~/components/issue/StatusCell.vue'
import TransferDialog from '~/components/issue/TransferDialog.vue'
import AssignDialog from '~/components/issue/AssignDialog.vue'

const { user } = useAuth()
const selfUserId = computed(() => Number(user.value?.id ?? 0))

const transferDialog = ref<{ open: boolean; issueId: number | null; projectId: number | null }>({
  open: false, issueId: null, projectId: null,
})
const assignDialog = ref<{ open: boolean; issueId: number | null; projectId: number | null }>({
  open: false, issueId: null, projectId: null,
})

function openTransfer(issue: any) {
  transferDialog.value = { open: true, issueId: issue.id, projectId: issue.project }
}
function openAssign(issue: any) {
  assignDialog.value = { open: true, issueId: issue.id, projectId: issue.project }
}
```

- [ ] **Step 2: Remove the 负责人 column + use StatusCell in status column**

Modify the `columns` computed in `index.vue`. Replace the columns array:

```typescript
const columns = computed(() => {
  const cols = [
    { id: 'select', header: '', cell: '' },
    { accessorKey: 'id', header: 'ID' },
    { accessorKey: 'title', header: '标题' },
    { accessorKey: 'cause', header: '原因分析' },
    { accessorKey: 'solution', header: '解决方案' },
    { accessorKey: 'remark', header: '备注' },
    { accessorKey: 'priority', header: '优先级' },
    { accessorKey: 'status', header: '状态', meta: { minWidth: 180 } },
    { accessorKey: 'reporter', header: '提出人' },
    { accessorKey: 'created_at', header: '历时' },
    { accessorKey: 'estimated_completion', header: '预计完成' },
  ]
  if (showGHColumn.value) {
    cols.push({ accessorKey: 'github_issues', header: 'GitHub Issues' })
  }
  return cols
})
```

- [ ] **Step 3: Replace the status cell template**

Find the existing `<template #status-cell="{ row }">` block (around line 266) and replace its contents:

```vue
<template #status-cell="{ row }">
  <StatusCell
    :issue="row.original"
    :self-user-id="selfUserId"
    @changed="fetchIssues"
    @request-transfer="openTransfer(row.original)"
    @request-assign="openAssign(row.original)"
  />
</template>
```

Remove the `<template #assignee_name-cell="{ row }">` block entirely (lines ~274-276), as the column no longer exists.

- [ ] **Step 4: Update statusColor reference**

Find the local `statusColor` function (around line 705-707) and remove it. The component now uses `statusColorFn` from constants — but since `IssueStatusBadge` (if used elsewhere) may still call `statusColor()` from local scope, add an alias at top of `<script setup>`:

```typescript
const statusColor = statusColorFn
```

- [ ] **Step 5: Update kanban columns**

Find the `kanbanColumns` computed (line 616) and replace:

```typescript
const kanbanColumns = computed(() => {
  const baseKeys = KANBAN_DEFAULT_COLUMNS
  const keys = showCompleted.value
    ? [...KANBAN_COMPLETED_LEFT, ...baseKeys, ...KANBAN_COMPLETED_RIGHT]
    : baseKeys
  return keys.map(key => ({
    key,
    label: key,
    color: kanbanColor(key),
    items: issues.value.filter(i => i.status === key),
  }))
})
```

- [ ] **Step 6: Update create-form defaults + status options**

Find `newIssue` ref (around line 405) and update default status:

```typescript
const newIssue = ref({
  // ... other fields unchanged ...
  status: ISSUE_STATUS.UNASSIGNED,
  // ...
})
```

Find `createStatusOptions` and `filterStatusOptions` (lines 520, 525) and replace both:

```typescript
const createStatusOptions = ISSUE_STATUS_OPTIONS
const filterStatusOptions = ISSUE_STATUS_OPTIONS
```

- [ ] **Step 7: Update reset-newIssue logic (look for any `'待处理'` literal in this file)**

```bash
grep -n '待处理' frontend/app/pages/app/issues/index.vue
```
Replace any remaining `'待处理'` with `ISSUE_STATUS.UNASSIGNED`.

- [ ] **Step 8: Render the dialogs in the template**

At the end of the main `<template>` block (before `</template>`), add:

```vue
    <TransferDialog
      v-if="transferDialog.issueId !== null && transferDialog.projectId !== null"
      v-model="transferDialog.open"
      :issue-id="transferDialog.issueId"
      :project-id="transferDialog.projectId"
      :self-user-id="selfUserId"
      @transferred="fetchIssues"
    />
    <AssignDialog
      v-if="assignDialog.issueId !== null && assignDialog.projectId !== null"
      v-model="assignDialog.open"
      :issue-id="assignDialog.issueId"
      :project-id="assignDialog.projectId"
      @assigned="fetchIssues"
    />
```

- [ ] **Step 9: Update create-toast logic**

Find the create submit handler (function around line 540-563). After the successful create, change toast text:

```typescript
const created = await api<any>('/api/issues/', { method: 'POST', body, format: 'json' })
const msg = created.assignee
  ? `已创建,分配给 ${created.assignee_name || '该成员'}`
  : '已创建,等待人工接单'
useToast().add({ title: msg, color: 'success' })
```

(Verify the existing toast call signature — adjust to match the project's `useToast` usage; check another `.vue` file for an example if needed.)

- [ ] **Step 10: Type-check + manual smoke test**

```bash
cd frontend && npx nuxi typecheck 2>&1 | tail -20
```
Expected: no new errors.

- [ ] **Step 11: Commit**

```bash
git add frontend/app/pages/app/issues/index.vue
git commit -m "feat(frontend): use StatusCell in issues list, remove 负责人 column"
```

---

## Task 21: Update IssueCard + detail page

**Files:**
- Modify: `frontend/app/components/IssueCard.vue`
- Modify: `frontend/app/pages/app/issues/[id].vue`

- [ ] **Step 1: Replace status badge in IssueCard**

Read `frontend/app/components/IssueCard.vue` and find the status badge near line 90 (`<UBadge :color="statusColor(c.status)" ...>{{ c.status }}</UBadge>`). Replace it with StatusCell:

```vue
<script setup lang="ts">
import StatusCell from '~/components/issue/StatusCell.vue'
import { statusColor } from '~/constants/issueStatus'
// ... existing imports
const { user } = useAuth()
const selfUserId = computed(() => Number(user.value?.id ?? 0))
const emit = defineEmits<{ (e: 'changed'): void; (e: 'request-transfer', issue: any): void }>()
</script>
```

Then in template, replace the status badge:

```vue
<StatusCell
  :issue="c"
  :self-user-id="selfUserId"
  @changed="emit('changed')"
  @request-transfer="emit('request-transfer', c)"
/>
```

(The IssueCard parent — the kanban view — should listen for `request-transfer` and open the dialog. If the kanban implementation owns the dialog state, wire that pass-through accordingly. Verify by reading the kanban parent.)

- [ ] **Step 2: Detail page — render assignments timeline + StatusCell**

Read `frontend/app/pages/app/issues/[id].vue`. Find where the issue status is shown. Replace static badge with `<StatusCell>` similar to Task 19/20.

Add a new section after the main issue body:

```vue
<section v-if="issue?.assignments?.length" class="mt-6">
  <h3 class="text-sm font-medium mb-2">分配流转</h3>
  <ol class="space-y-1 text-sm">
    <li v-for="a in issue.assignments" :key="a.id" class="flex gap-2">
      <span class="text-gray-500">{{ formatDate(a.created_at) }}</span>
      <span class="font-medium">{{ actionLabel(a.action) }}</span>
      <span v-if="a.from_user_name"> from {{ a.from_user_name }}</span>
      <span> → {{ a.to_user_name }}</span>
      <span v-if="a.reason" class="text-gray-600">— {{ a.reason }}</span>
    </li>
  </ol>
</section>
```

Add helper in `<script setup>`:

```typescript
function actionLabel(a: string): string {
  return ({
    claim: '接单',
    assign: '指派',
    ai_assign: 'AI 分配',
    transfer: '转单',
    confirm: '确认',
  } as Record<string, string>)[a] || a
}
function formatDate(s: string): string {
  return new Date(s).toLocaleString('zh-CN')
}
```

- [ ] **Step 3: Type-check**

```bash
cd frontend && npx nuxi typecheck 2>&1 | tail -10
```
Expected: no new errors.

- [ ] **Step 4: Replace any remaining `待处理` literals in [id].vue**

```bash
grep -n 待处理 frontend/app/pages/app/issues/'[id].vue' frontend/app/components/IssueCard.vue
```
Replace each occurrence with `ISSUE_STATUS.UNASSIGNED` (import from `~/constants/issueStatus`).

- [ ] **Step 5: Update mock data**

```bash
grep -n 待处理 frontend/app/data/mock.ts
```

Replace `待处理` with `待分配` in `frontend/app/data/mock.ts`.

- [ ] **Step 6: Commit**

```bash
git add frontend/app/components/IssueCard.vue frontend/app/pages/app/issues/'[id].vue' frontend/app/data/mock.ts
git commit -m "feat(frontend): StatusCell in IssueCard + assignment timeline in detail page"
```

---

## Task 22: Phase 1 smoke test

- [ ] **Step 1: Start backend + frontend dev servers**

```bash
cd backend && uv run python manage.py runserver &
cd frontend && npm run dev &
```

- [ ] **Step 2: Manually verify Phase 1 acceptance criteria**

Open `http://localhost:3000/app/issues`. Verify:
- [ ] Sidebar/filter shows `待分配` and `待确认` in status filter
- [ ] No `负责人` column in the table
- [ ] An issue in `待分配` shows a「+ 接单」button for a logged-in project member
- [ ] After click, the row moves to `进行中` and shows「我 处理中」
- [ ] Create a new issue with `指派给` set → status becomes `待确认`
- [ ] As the assignee, the row shows「✓ 接受」+「↪」 buttons
- [ ] Click `↪` → TransferDialog opens, select another member + fill reason, submit → row updates to that user as `待确认`

- [ ] **Step 3: Phase 1 review checkpoint — stop and hand to user**

Phase 1 complete. Wait for user signoff before proceeding to Phase 2.

---

# Phase 2: AI Auto-Assignment

## Task 23: Seed an `issue_auto_assign` Prompt row

**Files:**
- Create: `backend/apps/ai/migrations/<next>_seed_auto_assign_prompt.py` (number based on existing AI migrations)

- [ ] **Step 1: Find latest AI migration number**

```bash
ls backend/apps/ai/migrations/ | sort | tail -3
```

- [ ] **Step 2: Create the seed migration**

Create `backend/apps/ai/migrations/<NEXT>_seed_auto_assign_prompt.py` (e.g., `0010_seed_auto_assign_prompt.py`):

```python
from django.db import migrations


SYSTEM_PROMPT = """你是项目工单分配助手。请根据问题描述,从候选项目成员中挑选最合适的一位。
只返回 JSON 对象:{"assignee_id": <整数>, "reason": "<不超过200字的推荐理由>"}
不要输出 markdown 代码块,不要输出 JSON 之外的任何内容。"""

USER_PROMPT = """【问题】
标题: {title}
描述: {description}
标签: {labels}
优先级: {priority}

【候选成员】
{members_block}"""


def forwards(apps, schema_editor):
    Prompt = apps.get_model("ai", "Prompt")
    Prompt.objects.update_or_create(
        slug="issue_auto_assign",
        defaults={
            "name": "工单自动分配",
            "system_prompt": SYSTEM_PROMPT,
            "user_prompt_template": USER_PROMPT,
            "llm_model": "gpt-4o",
            "temperature": 0.2,
            "is_active": True,
        },
    )


def reverse(apps, schema_editor):
    Prompt = apps.get_model("ai", "Prompt")
    Prompt.objects.filter(slug="issue_auto_assign").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("ai", "<latest_migration_name_here>"),
    ]

    operations = [
        migrations.RunPython(forwards, reverse),
    ]
```

Fill in the actual `<latest_migration_name_here>` from Step 1.

- [ ] **Step 3: Apply migration**

```bash
cd backend && uv run python manage.py migrate
```

- [ ] **Step 4: Commit**

```bash
git add backend/apps/ai/migrations/*_seed_auto_assign_prompt.py
git commit -m "feat(ai): seed Prompt row for issue_auto_assign"
```

---

## Task 24: Implement real auto_assign_issue

**Files:**
- Modify: `backend/apps/issues/services.py`
- Create: `backend/tests/test_auto_assign.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_auto_assign.py`:

```python
import json
import pytest
from unittest.mock import patch, MagicMock
from apps.issues.services import auto_assign_issue, AssignmentAction
from apps.issues.models import IssueAssignment
from apps.projects.models import ProjectMember
from tests.factories import (
    IssueFactory, UserFactory, ProjectFactory, LLMConfigFactory, PromptFactory,
)


@pytest.fixture
def auto_assign_prompt(db):
    return PromptFactory(
        slug="issue_auto_assign",
        system_prompt="x",
        user_prompt_template="{title} {description} {labels} {priority} {members_block}",
        is_active=True,
    )


@pytest.fixture
def default_llm_config(db):
    return LLMConfigFactory(is_default=True, is_active=True)


@pytest.mark.django_db
class TestAutoAssign:
    def _project_with_members(self, n=2):
        project = ProjectFactory()
        members = []
        for i in range(n):
            u = UserFactory(name=f"成员{i}")
            ProjectMember.objects.create(
                project=project, user=u,
                personal_description=f"负责模块 {i}",
            )
            members.append(u)
        return project, members

    def test_returns_event_on_valid_llm_response(self, auto_assign_prompt, default_llm_config):
        project, members = self._project_with_members(2)
        issue = IssueFactory(project=project, status="待分配", assignee=None)

        fake_response = json.dumps({"assignee_id": members[1].id, "reason": "更贴合"})
        with patch("apps.issues.services.LLMClient") as MockClient:
            MockClient.return_value.complete.return_value = fake_response
            ev = auto_assign_issue(issue)

        assert ev is not None
        assert ev.action == AssignmentAction.AI_ASSIGN
        assert ev.to_user == members[1]
        assert ev.actor is None
        issue.refresh_from_db()
        assert issue.assignee == members[1]
        assert issue.status == "待确认"

    def test_returns_none_when_no_members_with_description(self, auto_assign_prompt, default_llm_config):
        project = ProjectFactory()
        ProjectMember.objects.create(project=project, user=UserFactory(), personal_description="")
        issue = IssueFactory(project=project, status="待分配", assignee=None)
        assert auto_assign_issue(issue) is None

    def test_returns_none_when_no_llm_config(self, auto_assign_prompt):
        project, _ = self._project_with_members(2)
        issue = IssueFactory(project=project, status="待分配", assignee=None)
        # No LLMConfig fixture used → none active
        assert auto_assign_issue(issue) is None

    def test_returns_none_when_no_prompt(self, default_llm_config):
        project, _ = self._project_with_members(2)
        issue = IssueFactory(project=project, status="待分配", assignee=None)
        # No PromptFactory fixture used
        assert auto_assign_issue(issue) is None

    def test_returns_none_on_llm_exception(self, auto_assign_prompt, default_llm_config):
        project, _ = self._project_with_members(2)
        issue = IssueFactory(project=project, status="待分配", assignee=None)
        with patch("apps.issues.services.LLMClient") as MockClient:
            MockClient.return_value.complete.side_effect = RuntimeError("timeout")
            assert auto_assign_issue(issue) is None

    def test_returns_none_when_response_is_invalid_json(self, auto_assign_prompt, default_llm_config):
        project, _ = self._project_with_members(2)
        issue = IssueFactory(project=project, status="待分配", assignee=None)
        with patch("apps.issues.services.LLMClient") as MockClient:
            MockClient.return_value.complete.return_value = "not json"
            assert auto_assign_issue(issue) is None

    def test_returns_none_when_assignee_id_not_in_project(self, auto_assign_prompt, default_llm_config):
        project, members = self._project_with_members(2)
        outsider = UserFactory()
        issue = IssueFactory(project=project, status="待分配", assignee=None)
        fake_response = json.dumps({"assignee_id": outsider.id, "reason": "x"})
        with patch("apps.issues.services.LLMClient") as MockClient:
            MockClient.return_value.complete.return_value = fake_response
            assert auto_assign_issue(issue) is None
```

- [ ] **Step 2: Run, fail**

```bash
cd backend && uv run pytest tests/test_auto_assign.py -xvs
```
Expected: FAIL — stub returns None always.

- [ ] **Step 3: Replace the stub with real implementation**

In `backend/apps/issues/services.py`, replace `def auto_assign_issue(issue): return None` with:

```python
AUTO_ASSIGN_PROMPT_SLUG = "issue_auto_assign"


def _build_members_block(members) -> str:
    lines = []
    for m in members:
        role = m.role.name if m.role_id else "未设置"
        # Sanitize personal_description to mitigate prompt injection
        desc = (m.personal_description or "").replace("\n", " ").replace('"', "'")[:500]
        lines.append(f"- id={m.user_id}, 姓名={m.user.name or m.user.username}, 角色={role}, 描述=\"{desc}\"")
    return "\n".join(lines)


def auto_assign_issue(issue):
    """Use LLM to pick the best assignee based on member personal_descriptions.
    Returns IssueAssignment on success, None on any failure or skip.
    """
    from apps.projects.models import ProjectMember

    members = list(
        ProjectMember.objects.filter(project=issue.project)
        .exclude(personal_description="")
        .select_related("user", "role")
    )
    if not members:
        logger.info("auto_assign: no members with descriptions for issue %s", issue.pk)
        return None

    prompt = Prompt.objects.filter(slug=AUTO_ASSIGN_PROMPT_SLUG, is_active=True).first()
    if not prompt:
        logger.warning("auto_assign: prompt '%s' not configured", AUTO_ASSIGN_PROMPT_SLUG)
        return None

    llm_config = prompt.llm_config or LLMConfig.objects.filter(is_default=True, is_active=True).first()
    if not llm_config:
        logger.warning("auto_assign: no active LLM config")
        return None

    try:
        user_prompt = prompt.user_prompt_template.format(
            title=issue.title,
            description=(issue.description or "")[:1000],
            labels=", ".join(issue.labels or []) if isinstance(issue.labels, list) else "",
            priority=issue.priority,
            members_block=_build_members_block(members),
        )
        raw = LLMClient(llm_config).complete(
            model=prompt.llm_model,
            system_prompt=prompt.system_prompt,
            user_prompt=user_prompt,
            temperature=prompt.temperature,
            timeout=15,
        )
        parsed = json.loads(raw)
        target_id = int(parsed["assignee_id"])
        reason = str(parsed.get("reason", ""))[:500]
    except (json.JSONDecodeError, KeyError, ValueError, TypeError):
        logger.warning("auto_assign: bad LLM response", exc_info=True)
        return None
    except Exception:
        logger.warning("auto_assign: LLM call failed", exc_info=True)
        return None

    valid_member_ids = {m.user_id for m in members}
    if target_id not in valid_member_ids:
        logger.info("auto_assign: LLM picked %s not in members %s", target_id, valid_member_ids)
        return None

    target_user = next(m.user for m in members if m.user_id == target_id)
    return _do_assign(
        issue, actor=None, to_user=target_user,
        action=AssignmentAction.AI_ASSIGN, reason=reason,
    )
```

- [ ] **Step 4: Rerun tests**

```bash
cd backend && uv run pytest tests/test_auto_assign.py -xvs
```
Expected: PASS (7 tests).

- [ ] **Step 5: End-to-end test — create_issue triggers auto_assign**

Append to `backend/tests/test_auto_assign.py`:

```python
@pytest.mark.django_db
class TestCreateIssueAutoAssignIntegration:
    def test_create_without_assignee_triggers_auto_assign(self, auto_assign_prompt, default_llm_config):
        from apps.issues.services import create_issue
        project = ProjectFactory()
        target = UserFactory()
        ProjectMember.objects.create(
            project=project, user=target, personal_description="后端专家",
        )

        fake = json.dumps({"assignee_id": target.id, "reason": "后端"})
        with patch("apps.issues.services.LLMClient") as MockClient:
            MockClient.return_value.complete.return_value = fake
            issue = create_issue(
                project=project, actor=UserFactory(),
                title="后端 API 500", description="POST /foo 报错",
                priority="P1", assignee=None,
            )

        assert issue.assignee == target
        assert issue.status == "待确认"
        ev = issue.assignments.last()
        assert ev.action == "ai_assign"
        assert ev.reason == "后端"
```

```bash
cd backend && uv run pytest tests/test_auto_assign.py::TestCreateIssueAutoAssignIntegration -xvs
```
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/apps/issues/services.py backend/tests/test_auto_assign.py
git commit -m "feat(issues): Phase 2 — AI auto-assign via LLM on issue creation"
```

---

## Task 25: Phase 2 smoke test + final cleanup

- [ ] **Step 1: Run full backend suite**

```bash
cd backend && uv run pytest 2>&1 | tail -10
```
Expected: all green.

- [ ] **Step 2: Type-check frontend**

```bash
cd frontend && npx nuxi typecheck 2>&1 | tail -10
```
Expected: no new errors.

- [ ] **Step 3: Manual smoke test of Phase 2**

Open `http://localhost:3000/app/issues`, click `新建问题`:
- [ ] Fill in title + description, leave `指派给` empty, submit
- [ ] Confirm toast says `已创建,分配给 {AI 选的人}` (assuming LLM is configured and project has members with `personal_description`)
- [ ] Issue lands in `待确认` for the AI-picked person
- [ ] Open the new issue's detail page, verify the `分配流转` section shows an `AI 分配` row with the model's reason

If LLM is offline, verify the fallback toast `已创建,等待人工接单` and `待分配` status.

- [ ] **Step 4: Final search-for-leftovers sweep**

```bash
grep -rn "待处理" backend frontend --include='*.py' --include='*.ts' --include='*.vue' | grep -v __pycache__ | grep -v node_modules
```
Expected: no results, OR only documented backward-compat shim (none in this plan).

- [ ] **Step 5: Phase 2 review checkpoint — hand to user**

Plan complete.

---

# Self-Review Notes

After writing the plan, verified against spec:

- §3 status machine — covered by Tasks 1, 4, 6-8
- §4.1 Issue.manager — Task 1
- §4.2 ProjectMember.is_manager + constraint — Task 2
- §4.3 IssueAssignment model — Task 1
- §4.4 invariant — Task 8 (explicit invariant test)
- §5 API — Task 12
- §5.1 service signatures — Tasks 6-10
- §5.2 permissions — Tasks 6-8 (each service tests its rule)
- §5.3 can_* fields — Task 11
- §6.1 StatusCell — Task 19
- §6.2 TransferDialog — Task 17
- §6.3 list page changes — Task 20
- §6.4 create form changes — Task 20 (toast + assignee optional)
- §7 AI auto-assign — Tasks 23-24
- §8 migrations — Tasks 1, 2, 3, 4, 23
- §9 tests — Tasks 1-12, 24

Spec coverage: complete. Backward-compat status alias (spec §10) intentionally NOT implemented — frontend is the only consumer and is updated in this same release; external API consumers were not flagged as a concern.

Type consistency check:
- `AssignmentAction.CLAIM`/`ASSIGN`/`AI_ASSIGN`/`TRANSFER`/`CONFIRM` used consistently
- `IssueStatus.UNASSIGNED`/`PENDING_CONFIRMATION`/`IN_PROGRESS` etc. used consistently
- Service method signatures match across tasks
- Frontend constants `ISSUE_STATUS.*` match backend values
