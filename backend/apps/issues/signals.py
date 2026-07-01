from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Issue
from .services_danmaku import broadcast_issue_event, build_payload


@receiver(post_save, sender=Issue)
def trigger_ai_analysis(sender, instance, created, update_fields, **kwargs):
    if created:
        _maybe_analyze(instance, triggered_by="auto")
    elif update_fields and "description" in update_fields:
        _maybe_analyze(instance, triggered_by="auto")


@receiver(post_save, sender=Issue)
def broadcast_danmaku(sender, instance, created, **kwargs):
    # 新建 → created;首次进入终态(save override 置的标志)→ completed;其余不推。
    # on_commit:事务回滚时不发幽灵事件。
    if created:
        payload = build_payload(instance, "created")
    elif getattr(instance, "_danmaku_completed", False):
        payload = build_payload(instance, "completed")
    else:
        return
    transaction.on_commit(lambda: broadcast_issue_event(payload))


def _maybe_analyze(issue, triggered_by):
    if not issue.repo_id:
        return
    from apps.repos.models import Repo
    try:
        repo = Repo.objects.get(pk=issue.repo_id)
    except Repo.DoesNotExist:
        return
    if repo.clone_status != "cloned":
        return

    from apps.ai.services import IssueAnalysisService
    svc = IssueAnalysisService()
    if svc.get_running_analysis(issue):
        return
    svc.analyze_async(issue, triggered_by=triggered_by)
