"""数据库备份服务 — 定时全量备份，保留近7天"""
import os
import shutil
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from app.config import settings


def backup_database() -> dict:
    """执行数据库备份，返回备份结果"""
    backup_dir = Path(settings.backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    try:
        if settings.database_url.startswith("sqlite"):
            # SQLite: 直接复制文件
            db_path = settings.database_url.replace("sqlite:///", "")
            if not os.path.isabs(db_path):
                db_path = str(Path(db_path).absolute())
            backup_file = backup_dir / f"smart_tax_{ts}.db"
            shutil.copy2(db_path, str(backup_file))
            size_mb = backup_file.stat().st_size / (1024 * 1024)
        else:
            # PostgreSQL: pg_dump
            backup_file = backup_dir / f"smart_tax_{ts}.sql"
            db_url = settings.database_url
            # 解析 postgresql://user:pass@host/db
            url_part = db_url.replace("postgresql://", "")
            user_pass, host_db = url_part.split("@")
            user, pwd = user_pass.split(":") if ":" in user_pass else (user_pass, "")
            host_port, db_name = host_db.split("/")
            host = host_port.split(":")[0]

            env = os.environ.copy()
            if pwd:
                env["PGPASSWORD"] = pwd
            cmd = [
                "pg_dump", "-h", host, "-U", user, "-d", db_name,
                "-f", str(backup_file), "--no-owner", "--no-acl",
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=120)
            if result.returncode != 0:
                return {"success": False, "error": result.stderr[:200]}
            size_mb = backup_file.stat().st_size / (1024 * 1024)

        # 清理7天前的备份
        cutoff = datetime.now() - timedelta(days=7)
        for f in backup_dir.iterdir():
            if f.is_file() and f.stat().st_mtime < cutoff.timestamp():
                f.unlink()

        return {
            "success": True,
            "file": str(backup_file.name),
            "size_mb": round(size_mb, 2),
            "timestamp": ts,
        }
    except Exception as e:
        return {"success": False, "error": str(e)[:200]}


def restore_database(backup_file: str) -> dict:
    """从备份文件恢复数据库"""
    backup_path = Path(settings.backup_dir) / backup_file
    if not backup_path.exists():
        return {"success": False, "error": f"备份文件不存在: {backup_file}"}

    try:
        if backup_file.endswith(".db"):
            db_path = settings.database_url.replace("sqlite:///", "")
            if not os.path.isabs(db_path):
                db_path = str(Path(db_path).absolute())
            shutil.copy2(str(backup_path), db_path)
        else:
            db_url = settings.database_url
            url_part = db_url.replace("postgresql://", "")
            user_pass, host_db = url_part.split("@")
            user, pwd = user_pass.split(":") if ":" in user_pass else (user_pass, "")
            host_port, db_name = host_db.split("/")
            host = host_port.split(":")[0]
            env = os.environ.copy()
            if pwd:
                env["PGPASSWORD"] = pwd
            cmd = ["psql", "-h", host, "-U", user, "-d", db_name, "-f", str(backup_path)]
            result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=120)
            if result.returncode != 0:
                return {"success": False, "error": result.stderr[:200]}

        return {"success": True, "message": f"已从 {backup_file} 恢复"}
    except Exception as e:
        return {"success": False, "error": str(e)[:200]}
