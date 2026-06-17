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
