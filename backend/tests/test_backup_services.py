# backend/tests/test_backup_services.py
import pytest
from apps.backups import services
from apps.backups.models import BackupTarget

pytestmark = pytest.mark.django_db


def test_parse_cron_valid():
    assert services.parse_cron("30 2 * * *") == {
        "minute": "30", "hour": "2", "day_of_month": "*",
        "month_of_year": "*", "day_of_week": "*",
    }


def test_parse_cron_invalid_field_count():
    with pytest.raises(ValueError):
        services.parse_cron("30 2 * *")


def test_build_local_command_uses_target_db_name():
    t = BackupTarget(name="self", db_name="devtrack")
    argv = services.build_local_command(t, "/tmp/x.dump")
    assert argv[0] == "pg_dump"
    assert "-Fc" in argv and "devtrack" in argv
    assert argv[-2:] == ["-f", "/tmp/x.dump"]


def test_build_remote_dump_cmd_plain_host():
    t = BackupTarget(name="r", ssh_host="prod1", db_name="app", db_user="app")
    cmd = services.build_remote_dump_cmd(t)
    assert cmd.startswith("pg_dump")
    assert "-U app" in cmd and "-Fc app" in cmd
    assert "docker" not in cmd


def test_build_remote_dump_cmd_with_container():
    t = BackupTarget(name="r", ssh_host="prod1", db_name="app", docker_container="pg")
    cmd = services.build_remote_dump_cmd(t)
    assert cmd.startswith("docker exec pg pg_dump")


def test_build_ssh_argv_with_user_and_port():
    t = BackupTarget(name="r", ssh_host="prod1", ssh_user="ubuntu", ssh_port=2222, db_name="app")
    argv = services.build_ssh_argv(t, "pg_dump -Fc app")
    assert argv[0] == "ssh"
    assert "-p" in argv and "2222" in argv
    assert "ubuntu@prod1" in argv
    assert argv[-1] == "pg_dump -Fc app"
    assert "BatchMode=yes" in argv
