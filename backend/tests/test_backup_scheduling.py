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
