# backend/tests/test_backup_models.py
import pytest
from apps.backups.models import BackupTarget, DatabaseBackup
from apps.projects.models import Project

pytestmark = pytest.mark.django_db


class TestBackupTarget:
    def test_site_level_target_has_null_project(self):
        t = BackupTarget.objects.create(name="DevTrakr 自身", db_name="devtrack")
        assert t.project is None
        assert t.ssh_host == ""
        assert t.retention_count == 7
        assert t.is_active is True

    def test_project_scoped_target(self):
        p = Project.objects.create(name="P", status="进行中")
        t = BackupTarget.objects.create(name="P 生产库", db_name="p_prod", project=p)
        assert t.project_id == p.id
        assert list(p.backup_targets.all()) == [t]


class TestDatabaseBackup:
    def test_backup_links_to_target(self):
        t = BackupTarget.objects.create(name="T", db_name="d")
        b = DatabaseBackup.objects.create(target=t, filename="d_1.dump", status="running")
        assert b.trigger == "manual"
        assert list(t.backups.all()) == [b]

    def test_deleting_target_keeps_backup_history(self):
        t = BackupTarget.objects.create(name="T", db_name="d")
        b = DatabaseBackup.objects.create(target=t, filename="d_1.dump", status="success")
        t.delete()
        b.refresh_from_db()
        assert b.target_id is None
        assert DatabaseBackup.objects.filter(id=b.id).exists()

    def test_ordering_newest_first(self):
        b1 = DatabaseBackup.objects.create(filename="a.dump", status="success")
        b2 = DatabaseBackup.objects.create(filename="b.dump", status="success")
        assert list(DatabaseBackup.objects.values_list("id", flat=True)) == [b2.id, b1.id]
