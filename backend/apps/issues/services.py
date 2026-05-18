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
