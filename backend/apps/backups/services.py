# backend/apps/backups/services.py
import os
import shlex
import subprocess

from django.conf import settings


def get_backup_dir() -> str:
    d = getattr(settings, "BACKUP_DIR", "/data/backups")
    os.makedirs(d, exist_ok=True)
    return d


def parse_cron(expr: str) -> dict:
    """把 5 段 cron 解析成 django_celery_beat CrontabSchedule 字段。"""
    parts = expr.split()
    if len(parts) != 5:
        raise ValueError("cron 必须是 5 段(分 时 日 月 周)")
    minute, hour, dom, mon, dow = parts
    return {
        "minute": minute, "hour": hour, "day_of_month": dom,
        "month_of_year": mon, "day_of_week": dow,
    }


def build_local_command(target, filepath: str) -> list:
    """本地 pg_dump(备份 DevTrakr 自身):凭据取自 DATABASES['default']。"""
    db = settings.DATABASES["default"]
    return [
        "pg_dump",
        "-h", target.db_host or db.get("HOST", "127.0.0.1"),
        "-p", str(target.db_port or db.get("PORT", "5432")),
        "-U", target.db_user or db.get("USER", "postgres"),
        "-Fc", target.db_name,
        "-f", filepath,
    ]


def build_remote_dump_cmd(target) -> str:
    """在远程主机上要执行的 pg_dump 命令(单条 shell 字符串,-Fc 输出到 stdout)。"""
    inner = ["pg_dump"]
    if target.db_host:
        inner += ["-h", target.db_host]
    if target.db_port:
        inner += ["-p", str(target.db_port)]
    if target.db_user:
        inner += ["-U", target.db_user]
    inner += ["-Fc", target.db_name]
    cmd = " ".join(shlex.quote(p) for p in inner)
    if target.docker_container:
        cmd = f"docker exec {shlex.quote(target.docker_container)} {cmd}"
    return cmd


def build_ssh_argv(target, remote_cmd: str) -> list:
    argv = ["ssh"]
    if target.ssh_port:
        argv += ["-p", str(target.ssh_port)]
    host = f"{target.ssh_user}@{target.ssh_host}" if target.ssh_user else target.ssh_host
    argv += [host, remote_cmd]
    return argv


def dump_database(target, filepath: str):
    """执行转储。返回 (success: bool, file_size: int, error: str)。"""
    env = os.environ.copy()
    if not target.ssh_host:
        env["PGPASSWORD"] = settings.DATABASES["default"].get("PASSWORD", "")
        proc = subprocess.run(build_local_command(target, filepath), env=env, capture_output=True)
        if proc.returncode == 0:
            return True, os.path.getsize(filepath), ""
        return False, 0, proc.stderr.decode().strip()

    remote_cmd = build_remote_dump_cmd(target)
    argv = build_ssh_argv(target, remote_cmd)
    with open(filepath, "wb") as f:
        proc = subprocess.run(argv, stdout=f, stderr=subprocess.PIPE, env=env)
    if proc.returncode == 0 and os.path.exists(filepath) and os.path.getsize(filepath) > 0:
        return True, os.path.getsize(filepath), ""
    return False, 0, proc.stderr.decode().strip() or "远程转储失败"
