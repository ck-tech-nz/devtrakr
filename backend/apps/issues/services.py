"""Issue-level services (kept separate from views and serializers).

The current entry point is `check_duplicates`, used by the create-issue
modal to surface near-duplicate open issues before submission.
"""
import json
import logging
import time

from apps.ai.client import LLMClient
from apps.ai.models import Prompt
from .models import Issue, IssueAssignment, AssignmentAction, IssueStatus, Activity


logger = logging.getLogger(__name__)

CLOSED_STATUSES = ("已关闭", "已发布")
MIN_TITLE_LENGTH = 3
MAX_CANDIDATES = 100
MAX_MATCHES = 5
DESCRIPTION_TRUNCATE = 300
LLM_TIMEOUT_SECONDS = 15
DUPLICATE_PROMPT_SLUG = "issue_duplicate_check"


def check_duplicates(project_id, title, description):
    """Return up to MAX_MATCHES AI-flagged near-duplicate open issues in the project.

    Returns [] (silently) when any precondition is unmet: missing project,
    short title, no candidates, no prompt, no LLM config, malformed JSON,
    or any exception raised by the LLM call.
    """
    if not project_id:
        return []
    title = (title or "").strip()
    if len(title) < MIN_TITLE_LENGTH:
        return []

    candidates = list(
        Issue.objects.filter(project_id=project_id)
        .exclude(status__in=CLOSED_STATUSES)
        .order_by("-id")
        .values("id", "title", "description", "status")[:MAX_CANDIDATES]
    )
    if not candidates:
        return []

    prompt = Prompt.objects.filter(slug=DUPLICATE_PROMPT_SLUG, is_active=True).first()
    if not prompt:
        return []

    llm_config = prompt.llm_config

    truncated = [
        {
            "id": c["id"],
            "title": c["title"],
            "description": (c["description"] or "")[:DESCRIPTION_TRUNCATE],
            "status": c["status"],
        }
        for c in candidates
    ]
    by_id = {c["id"]: c for c in candidates}

    started = time.monotonic()
    try:
        user_prompt = prompt.user_prompt_template.format(
            candidates_json=json.dumps(truncated, ensure_ascii=False),
            new_title=title,
            new_description=description or "",
        )
        raw = LLMClient(llm_config).complete(
            model=prompt.llm_model,
            system_prompt=prompt.system_prompt,
            user_prompt=user_prompt,
            temperature=prompt.temperature,
            timeout=LLM_TIMEOUT_SECONDS,
        )
        parsed = json.loads(raw)
        duplicates = parsed.get("duplicates") or []
    except (json.JSONDecodeError, KeyError, ValueError):
        logger.warning("duplicate_check: bad LLM response shape", exc_info=True)
        return []
    except Exception:
        logger.warning("duplicate_check: LLM call failed", exc_info=True)
        return []

    out = []
    for entry in duplicates:
        cid = entry.get("id") if isinstance(entry, dict) else None
        if cid in by_id:
            cand = by_id[cid]
            out.append({
                "id": cand["id"],
                "title": cand["title"],
                "status": cand["status"],
                "reason": (entry.get("reason") or "")[:200],
            })
        if len(out) >= MAX_MATCHES:
            break

    elapsed_ms = int((time.monotonic() - started) * 1000)
    logger.info(
        "duplicate_check project=%s candidates=%d matches=%d elapsed_ms=%d",
        project_id, len(candidates), len(out), elapsed_ms,
    )
    return out


# ---------------------------------------------------------------------------
# Assignment service layer
# ---------------------------------------------------------------------------

from django.db import transaction
from rest_framework.exceptions import PermissionDenied


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
def _do_assign(issue, *, actor, to_user, action, reason):
    """Internal helper: write the assignment event + flip assignee/status.

    Used by create_issue (which enforces its own permission boundary) and
    assign_issue (which enforces manager-only). Callers are responsible for
    all permission and status guards before calling this.
    """
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


@transaction.atomic
def claim_issue(issue, actor):
    """任何项目成员可接单「待分配」→「进行中」,自动成为负责人。"""
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
    """当前负责人确认「待确认」→「进行中」。"""
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


@transaction.atomic
def transfer_issue(issue, actor, to_user, reason: str):
    """负责人或项目经理将「待确认/进行中」的工单转给新负责人,新负责人落入「待确认」。"""
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

    from_user = issue.assignee  # capture the displaced owner BEFORE updating

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


AUTO_ASSIGN_PROMPT_SLUG = "issue_auto_assign"


def _build_members_block(members, workload_by_user_id) -> str:
    """Format project members for the LLM prompt.

    Each line: - id=<user_id>, 姓名=<name>, 角色=<role>, 活跃工单=<n>, 描述="<desc>"
    `活跃工单` is the count of 待确认+进行中 issues currently assigned to the
    member inside the same project — fed to the LLM so it can balance load.
    personal_description is sanitized: newlines → space, quotes → ', truncated to 500 chars.
    """
    lines = []
    for m in members:
        role = m.role.name if m.role_id else "未设置"
        desc = (m.personal_description or "").replace("\n", " ").replace('"', "'")[:500]
        name = m.user.name or m.user.username
        active = workload_by_user_id.get(m.user_id, 0)
        lines.append(
            f'- id={m.user_id}, 姓名={name}, 角色={role}, 活跃工单={active}, 描述="{desc}"'
        )
    return "\n".join(lines)


def _active_workload_by_user(project, member_ids):
    """Count of 待确认+进行中 issues per member inside the given project.

    Members with zero active issues are absent from the dict; the block
    builder treats missing keys as 0.
    """
    from django.db.models import Count
    active_statuses = (IssueStatus.PENDING_CONFIRMATION.value, IssueStatus.IN_PROGRESS.value)
    rows = (
        Issue.objects
        .filter(project=project, assignee_id__in=list(member_ids), status__in=active_statuses)
        .values("assignee_id")
        .annotate(n=Count("id"))
    )
    return {r["assignee_id"]: r["n"] for r in rows}


def pick_assignee_for_draft(*, project, title, description, labels, priority):
    """LLM-pick the best assignee from project developers — pure (no DB writes).

    Returns (User, reason) on success, None on any skip/failure. Shared by:
      - auto_assign_issue (post-create fallback when no assignee provided)
      - AiWizardService._stream_draft_v2 (pre-create, parallel with oneshot/dedup)

    Splitting the picker from auto_assign_issue lets the wizard run this LLM
    call in parallel with the draft+dedup calls so the create-issue POST is
    instant. Errors are swallowed (logged); caller decides the fallback.
    """
    from apps.projects.models import ProjectMember

    # 仅在"开发者"角色成员中挑选 — 产品经理 / 测试 / 只读成员不参与自动分派
    members = list(
        ProjectMember.objects.filter(project=project, role__name="开发者")
        .exclude(personal_description="")
        .select_related("user", "role")
    )
    if not members:
        logger.info("auto_assign: no developer members with descriptions for project %s", project.pk)
        return None

    prompt = Prompt.objects.filter(slug=AUTO_ASSIGN_PROMPT_SLUG, is_active=True).first()
    if not prompt:
        logger.warning("auto_assign: prompt '%s' not configured", AUTO_ASSIGN_PROMPT_SLUG)
        return None

    llm_config = prompt.llm_config

    try:
        labels_list = labels if isinstance(labels, list) else []
        workload = _active_workload_by_user(project, [m.user_id for m in members])
        user_prompt = prompt.user_prompt_template.format(
            title=title or "",
            description=(description or "")[:1000],
            labels=", ".join(labels_list),
            priority=priority or "P2",
            members_block=_build_members_block(members, workload),
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
        logger.info("auto_assign: LLM picked id=%s not in project members %s", target_id, valid_member_ids)
        return None

    target_user = next(m.user for m in members if m.user_id == target_id)
    return target_user, reason


def auto_assign_issue(issue):
    """Phase 2 fallback: LLM-pick + write the assignment for an existing Issue.

    Returns IssueAssignment on success, None on any failure or skip (never raises).
    The wizard pre-picks an assignee in parallel during draft analysis so this
    fallback is only hit when an Issue is created outside the wizard with no
    assignee provided.
    """
    pick = pick_assignee_for_draft(
        project=issue.project,
        title=issue.title,
        description=issue.description,
        labels=issue.labels,
        priority=issue.priority,
    )
    if pick is None:
        return None
    target_user, reason = pick
    return _do_assign(
        issue, actor=None, to_user=target_user,
        action=AssignmentAction.AI_ASSIGN, reason=reason,
    )


def create_issue(*, project, actor, title, description, priority,
                 assignee=None, **extra_fields):
    """Unified entry point for creating an Issue.

    Behavior:
      - assignee provided → status=待确认, writes an `assign` event synchronously
      - assignee=None → leaves status=待分配 and queues a Celery task to LLM-pick
        a developer. The submitter only cares the AI draft matches their intent;
        the assignment decision runs off the critical path.
    """
    # 未指定 repo 且项目仅关联一个仓库时自动绑定。
    # 普通创建表单本就有"单仓库自动选中"UX, AI 向导没有仓库选择器,
    # 在服务层兜底,避免 AI 创建的 issue 永远没关联仓库 (顺带让 post_save
    # 触发的 AI 代码分析也能跑起来——signals 依赖 issue.repo_id)
    if not extra_fields.get("repo") and not extra_fields.get("repo_id"):
        project_repo_ids = list(project.repos.values_list("id", flat=True)[:2])
        if len(project_repo_ids) == 1:
            extra_fields["repo_id"] = project_repo_ids[0]

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
        _do_assign(issue, actor=actor, to_user=assignee,
                   action=AssignmentAction.ASSIGN, reason="")
    else:
        # Defer until the surrounding serializer transaction commits, otherwise
        # the worker can fire before the Issue row is visible
        from django.db import transaction as _transaction
        from apps.issues.tasks import auto_assign_issue_task
        _transaction.on_commit(lambda: auto_assign_issue_task.delay(issue.id))

    return issue
