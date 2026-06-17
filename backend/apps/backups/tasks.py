# backend/apps/backups/tasks.py
import logging
import os

from celery import shared_task
from django.db import transaction
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
        .order_by("-created_at")
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
    # 原子锁:select_for_update 防止两个并发任务同时通过 running 检查
    with transaction.atomic():
        target = BackupTarget.objects.select_for_update().filter(id=target_id, is_active=True).first()
        if target is None:
            return None
        # 同一 target 一次只跑一个
        if DatabaseBackup.objects.filter(target=target, status="running").exists():
            logger.warning("backup target %s already running, skip", target_id)
            return None

        timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{target.db_name}_{timestamp}.dump"
        backup = DatabaseBackup.objects.create(
            target=target, filename=filename, status="running",
            trigger=trigger, created_by_id=created_by_id,
        )

    # filepath 和实际 dump 在锁外执行,不持有行锁
    filepath = os.path.join(get_backup_dir(), filename)

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
