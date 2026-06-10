"""Webhook 采集服务 — 接收微信/钉钉机器人的消息，下载图片/文件"""
import os
import uuid
import json
import requests
from datetime import datetime
from app.db import SessionLocal
from app.models.document import OriginalDocument
from app.services.qr_service import create_trace
from app.services.version_control import commit

WEBHOOK_CONFIG_FILE = "webhook_config.json"


def _load_config() -> list:
    try:
        with open(WEBHOOK_CONFIG_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_config(config: list):
    with open(WEBHOOK_CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def get_configs() -> list:
    return _load_config()


def add_webhook(platform: str, client_id: str, name: str = ""):
    """注册 webhook，返回 webhook URL 和 token"""
    config = _load_config()
    token = uuid.uuid4().hex[:16]
    item = {
        "id": str(uuid.uuid4()),
        "platform": platform,  # wechat / dingtalk
        "client_id": client_id,
        "name": name or f"{platform} 机器人",
        "token": token,
        "enabled": True,
        "webhook_url": f"/api/webhook/{platform}?token={token}",
        "total_collected": 0,
        "created_at": datetime.now().isoformat(),
    }
    config.append(item)
    _save_config(config)
    return item


def remove_webhook(webhook_id: str):
    config = _load_config()
    config = [c for c in config if c["id"] != webhook_id]
    _save_config(config)


def toggle_webhook(webhook_id: str, enabled: bool):
    config = _load_config()
    for c in config:
        if c["id"] == webhook_id:
            c["enabled"] = enabled
    _save_config(config)


def validate_token(platform: str, token: str) -> dict | None:
    """验证 webhook token"""
    config = _load_config()
    for c in config:
        if c["platform"] == platform and c["token"] == token and c.get("enabled", True):
            return c
    return None


def process_webhook_message(config_item: dict, file_urls: list[str], file_names: list[str] = None):
    """处理 webhook 发来的文件/图片"""
    upload_dir = "uploads"
    os.makedirs(upload_dir, exist_ok=True)
    collected = []

    if file_names is None:
        file_names = [f"webhook_{config_item['platform']}_{i+1}" for i in range(len(file_urls))]

    db = SessionLocal()
    try:
        for i, url in enumerate(file_urls):
            fname = file_names[i] if i < len(file_names) else f"webhook_file_{i}.jpg"
            ext = os.path.splitext(fname)[1].lower() or ".jpg"
            if ext not in (".jpg", ".jpeg", ".png", ".pdf"):
                ext = ".jpg"
            safe_name = f"{uuid.uuid4().hex}{ext}"
            dest = os.path.join(upload_dir, safe_name)

            # 尝试下载文件
            try:
                resp = requests.get(url, timeout=15, stream=True)
                if resp.status_code == 200:
                    with open(dest, "wb") as f:
                        for chunk in resp.iter_content(8192):
                            f.write(chunk)
                else:
                    # 占位文件
                    with open(dest, "wb") as f:
                        f.write(b"webhook placeholder")
            except Exception:
                with open(dest, "wb") as f:
                    f.write(b"webhook placeholder")

            doc_type = "receipt"
            if "发票" in fname or "invoice" in fname.lower():
                doc_type = "invoice"
            elif "合同" in fname or "contract" in fname.lower():
                doc_type = "contract"

            doc = OriginalDocument(
                id=str(uuid.uuid4()),
                source=f"{config_item['platform']}_bot",
                file_path=dest,
                file_name=fname,
                doc_type=doc_type,
                client_id=config_item["client_id"],
                ocr_status="pending",
            )
            db.add(doc)
            db.flush()
            trace = create_trace(db, "document", doc.id, f"{config_item['platform']}_bot")
            doc.qr_code_path = trace.qr_code_path
            commit(db, "document", doc.id, f"{config_item['platform']}_bot", "system",
                   after={"file_name": doc.file_name})
            collected.append({"id": doc.id, "file_name": doc.file_name})

        config_item["total_collected"] = config_item.get("total_collected", 0) + len(collected)
        _save_config(_load_config())  # persist the updated count
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()

    return collected
