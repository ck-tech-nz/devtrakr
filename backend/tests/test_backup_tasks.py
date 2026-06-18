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
def test_filename_namespaced_by_target(mock_dump, tmp_path, settings):
    # 两个目标备份同名库(如 test/prod 各自的 outcall_db)不能生成相同文件名相互覆盖
    settings.BACKUP_DIR = str(tmp_path)
    mock_dump.return_value = (True, 10, "")
    t1 = BackupTarget.objects.create(name="A", db_name="outcall_db")
    t2 = BackupTarget.objects.create(name="B", db_name="outcall_db")
    b1 = DatabaseBackup.objects.get(id=tasks.run_backup(t1.id))
    b2 = DatabaseBackup.objects.get(id=tasks.run_backup(t2.id))
    assert b1.filename != b2.filename
    assert f"t{t1.id}" in b1.filename and f"t{t2.id}" in b2.filename


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
