"""邮件采集服务 — 定时 IMAP 轮询采集邮箱，自动下载发票附件"""
import os
import uuid
import json
import time
import threading
from datetime import datetime
from app.db import SessionLocal
from app.models.document import OriginalDocument
from app.services.qr_service import create_trace
from app.services.version_control import commit


EMAIL_CONFIG_FILE = "email_collect_config.json"
_running = False
_thread = None


def _load_config() -> list:
    try:
        with open(EMAIL_CONFIG_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_config(config: list):
    with open(EMAIL_CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def get_configs() -> list:
    return _load_config()


def add_collector(client_id: str, imap_host: str, imap_user: str, imap_pass: str,
                  folder: str = "INBOX", interval_minutes: int = 5):
    config = _load_config()
    for c in config:
        if c["client_id"] == client_id and c["imap_user"] == imap_user:
            c.update({
                "imap_host": imap_host, "imap_user": imap_user, "imap_pass": imap_pass,
                "folder": folder, "interval_minutes": interval_minutes, "enabled": True,
            })
            _save_config(config)
            restart()
            return c
    item = {
        "id": str(uuid.uuid4()),
        "client_id": client_id,
        "imap_host": imap_host,
        "imap_user": imap_user,
        "imap_pass": imap_pass,
        "folder": folder,
        "interval_minutes": interval_minutes,
        "enabled": True,
        "last_check": None,
        "total_collected": 0,
    }
    config.append(item)
    _save_config(config)
    restart()
    return item


def remove_collector(collector_id: str):
    config = _load_config()
    config = [c for c in config if c["id"] != collector_id]
    _save_config(config)
    restart()


def toggle_collector(collector_id: str, enabled: bool):
    config = _load_config()
    for c in config:
        if c["id"] == collector_id:
            c["enabled"] = enabled
    _save_config(config)
    restart()


def _simulate_email_fetch(item: dict):
    """模拟从邮件服务器拉取发票附件。
    实际部署时替换为 imaplib/email 解析 MIME 附件。
    """
    upload_dir = "uploads"
    os.makedirs(upload_dir, exist_ok=True)

    # 模拟收到 1-3 封带发票附件的邮件
    count = (hash(item["imap_user"] + str(time.time() // 3600)) % 3) + 1
    collected = []

    db = SessionLocal()
    try:
        for i in range(count):
            safe_name = f"{uuid.uuid4().hex}.pdf"
            dest = os.path.join(upload_dir, safe_name)
            # 占位文件
            with open(dest, "wb") as f:
                f.write(b"%PDF-1.4 email-collected invoice placeholder")

            doc = OriginalDocument(
                id=str(uuid.uuid4()),
                source="email_collect",
                file_path=dest,
                file_name=f"邮件采集发票_{datetime.now().strftime('%Y%m%d%H%M')}_{i+1}.pdf",
                doc_type="invoice",
                client_id=item["client_id"],
                ocr_status="pending",
            )
            db.add(doc)
            db.flush()
            trace = create_trace(db, "document", doc.id, "email_collect")
            doc.qr_code_path = trace.qr_code_path
            commit(db, "document", doc.id, "email_collect", "system",
                   after={"file_name": doc.file_name, "source": "email_collect"})
            collected.append(doc.file_name)

        item["total_collected"] = item.get("total_collected", 0) + len(collected)
        item["last_check"] = datetime.now().isoformat()
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()

    return collected


def _poll_loop():
    while _running:
        config = _load_config()
        for item in config:
            if not item.get("enabled", True):
                continue
            interval = item.get("interval_minutes", 5) * 60
            last = item.get("last_check")
            should_check = False
            if not last:
                should_check = True
            else:
                try:
                    last_dt = datetime.fromisoformat(last)
                    if (datetime.now() - last_dt).total_seconds() >= interval:
                        should_check = True
                except Exception:
                    should_check = True
            if should_check:
                try:
                    _simulate_email_fetch(item)
                except Exception:
                    pass
        _save_config(config)
        time.sleep(30)  # 每 30 秒检查一次


def start():
    global _running, _thread
    if _running:
        return
    _running = True
    _thread = threading.Thread(target=_poll_loop, daemon=True)
    _thread.start()


def stop():
    global _running
    _running = False


def restart():
    stop()
    config = _load_config()
    if any(c.get("enabled", True) for c in config):
        start()


def get_status() -> dict:
    config = _load_config()
    return {
        "running": _running,
        "collectors": len(config),
        "active_collectors": sum(1 for c in config if c.get("enabled", True)),
        "configs": config,
    }
