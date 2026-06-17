import pytest
from unittest.mock import patch
from apps.backups.models import BackupTarget, DatabaseBackup

pytestmark = pytest.mark.django_db


class TestTargetAPI:
    def test_create_site_level_target(self, superuser_client):
        resp = superuser_client.post("/api/backups/targets/", {
            "name": "DevTrakr 自身", "db_name": "devtrack", "engine": "postgres",
        }, format="json")
        assert resp.status_code == 201
        assert resp.data["project"] is None

    def test_create_rejects_invalid_cron(self, superuser_client):
        resp = superuser_client.post("/api/backups/targets/", {
            "name": "T", "db_name": "d", "schedule_cron": "bad cron",
        }, format="json")
        assert resp.status_code == 400

    def test_list_forbidden_for_regular_user(self, regular_client):
        resp = regular_client.get("/api/backups/targets/")
        assert resp.status_code == 403

    def test_list_unauthenticated(self, api_client):
        resp = api_client.get("/api/backups/targets/")
        assert resp.status_code == 401


class TestRunAPI:
    @patch("apps.backups.views.run_backup.delay")
    def test_manual_run_enqueues_task(self, mock_delay, superuser_client):
        t = BackupTarget.objects.create(name="T", db_name="d")
        resp = superuser_client.post(f"/api/backups/targets/{t.id}/run/")
        assert resp.status_code == 202
        mock_delay.assert_called_once()

    @patch("apps.backups.views.run_backup.delay")
    def test_manual_run_conflict_when_running(self, mock_delay, superuser_client):
        t = BackupTarget.objects.create(name="T", db_name="d")
        DatabaseBackup.objects.create(target=t, filename="x.dump", status="running")
        resp = superuser_client.post(f"/api/backups/targets/{t.id}/run/")
        assert resp.status_code == 409
        mock_delay.assert_not_called()


class TestBackupRecordsAPI:
    def test_list_filter_by_target(self, superuser_client):
        t1 = BackupTarget.objects.create(name="A", db_name="a")
        t2 = BackupTarget.objects.create(name="B", db_name="b")
        DatabaseBackup.objects.create(target=t1, filename="a.dump", status="success")
        DatabaseBackup.objects.create(target=t2, filename="b.dump", status="success")
        resp = superuser_client.get(f"/api/backups/backups/?target={t1.id}")
        assert resp.status_code == 200 and resp.data["count"] == 1

    def test_download_and_delete(self, superuser_client, tmp_path, settings):
        settings.BACKUP_DIR = str(tmp_path)
        (tmp_path / "d.dump").write_bytes(b"dump")
        b = DatabaseBackup.objects.create(filename="d.dump", file_size=4, status="success")
        dl = superuser_client.get(f"/api/backups/backups/{b.id}/download/")
        assert dl.status_code == 200 and b"dump" in b"".join(dl.streaming_content)
        rm = superuser_client.delete(f"/api/backups/backups/{b.id}/")
        assert rm.status_code == 204 and not (tmp_path / "d.dump").exists()
