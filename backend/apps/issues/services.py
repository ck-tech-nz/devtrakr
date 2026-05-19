"""Issue-level services (kept separate from views and serializers).

The current entry point is `check_duplicates`, used by the create-issue
modal to surface near-duplicate open issues before submission.
"""
import json
import logging
import time

from apps.ai.client import LLMClient
from apps.ai.models import LLMConfig, Prompt
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

    llm_config = prompt.llm_config or LLMConfig.objects.filter(is_default=True, is_active=True).first()
    if not llm_config:
        return []

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


def _build_members_block(members) -> str:
    """Format project members for the LLM prompt.

    Each line: - id=<user_id>, 姓名=<name>, 角色=<role>, 描述="<desc>"
    personal_description is sanitized: newlines → space, quotes → ', truncated to 500 chars.
    """
    lines = []
    for m in members:
        role = m.role.name if m.role_id else "未设置"
        desc = (m.personal_description or "").replace("\n", " ").replace('"', "'")[:500]
        name = m.user.name or m.user.username
        lines.append(f'- id={m.user_id}, 姓名={name}, 角色={role}, 描述="{desc}"')
    return "\n".join(lines)


def auto_assign_issue(issue):
    """Phase 2: use LLM to pick the best assignee from members with personal_description.

    Returns IssueAssignment on success, None on any failure or skip (never raises).
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
        labels = issue.labels if isinstance(issue.labels, list) else []
        user_prompt = prompt.user_prompt_template.format(
            title=issue.title,
            description=(issue.description or "")[:1000],
            labels=", ".join(labels),
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
        logger.info("auto_assign: LLM picked id=%s not in project members %s", target_id, valid_member_ids)
        return None

    target_user = next(m.user for m in members if m.user_id == target_id)
    return _do_assign(
        issue, actor=None, to_user=target_user,
        action=AssignmentAction.AI_ASSIGN, reason=reason,
    )


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
        _do_assign(issue, actor=actor, to_user=assignee,
                   action=AssignmentAction.ASSIGN, reason="")
    else:
        auto_assign_issue(issue)

    return issue
