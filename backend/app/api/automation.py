"""自动化采集 API — 热文件夹 + 邮件轮询 + ZIP导入 + 扫描仪 + 微信/钉钉 Webhook"""
import os
import uuid
import zipfile
import tempfile
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, Request
from sqlalchemy.orm import Session
from app.db import get_db
from app.models.document import OriginalDocument
from app.services.auth import require_modify, require_not_client, get_current_user
from app.services.qr_service import create_trace
from app.services.version_control import commit
from app.services import file_watcher, email_collector, webhook_collector

router = APIRouter()


# ============================================================
# 热文件夹 + 扫描仪监控
# ============================================================

@router.get("/hot-folders")
def list_hot_folders(_=Depends(get_current_user)):
    return file_watcher.get_status()


@router.post("/hot-folders")
def add_hot_folder(
    data: dict,
    user=Depends(require_modify),
):
    """添加热文件夹监控"""
    path = data.get("path", "").strip()
    client_id = data.get("client_id", "").strip()
    label = data.get("label", "").strip()
    source = data.get("source", "hot_folder")  # hot_folder 或 scanner

    if not path or not os.path.isdir(path):
        raise HTTPException(status_code=400, detail="目录路径无效或不存在")
    if not client_id:
        raise HTTPException(status_code=400, detail="客户 ID 不能为空")

    item = file_watcher.add_watch(path, client_id, label, source)
    return {"message": f"已添加监控: {label or path}", "item": item}


@router.delete("/hot-folders/{watch_id}")
def remove_hot_folder(watch_id: str, user=Depends(require_modify)):
    file_watcher.remove_watch(watch_id)
    return {"message": "已移除监控"}


@router.patch("/hot-folders/{watch_id}/toggle")
def toggle_hot_folder(watch_id: str, data: dict, user=Depends(require_not_client)):
    file_watcher.toggle_watch(watch_id, data.get("enabled", True))
    return {"message": "状态已更新"}


# ============================================================
# 邮件轮询采集
# ============================================================

@router.get("/email-collectors")
def list_email_collectors(_=Depends(get_current_user)):
    return email_collector.get_status()


@router.post("/email-collectors")
def add_email_collector(
    data: dict,
    user=Depends(require_modify),
):
    """添加邮件采集器"""
    client_id = data.get("client_id", "").strip()
    imap_host = data.get("imap_host", "").strip()
    imap_user = data.get("imap_user", "").strip()
    imap_pass = data.get("imap_pass", "").strip()
    folder = data.get("folder", "INBOX").strip()
    interval = int(data.get("interval_minutes", 5))

    if not all([client_id, imap_host, imap_user, imap_pass]):
        raise HTTPException(status_code=400, detail="参数不完整")

    item = email_collector.add_collector(client_id, imap_host, imap_user, imap_pass, folder, interval)
    return {"message": f"已添加邮件采集器: {imap_user}", "item": item}


@router.delete("/email-collectors/{collector_id}")
def remove_email_collector(collector_id: str, user=Depends(require_modify)):
    email_collector.remove_collector(collector_id)
    return {"message": "已移除邮件采集器"}


@router.patch("/email-collectors/{collector_id}/toggle")
def toggle_email_collector(collector_id: str, data: dict, user=Depends(require_not_client)):
    email_collector.toggle_collector(collector_id, data.get("enabled", True))
    return {"message": "状态已更新"}


@router.post("/email-collectors/{collector_id}/test")
def test_email_collector(collector_id: str, user=Depends(require_modify)):
    """手动触发一次邮件采集"""
    configs = email_collector.get_configs()
    for c in configs:
        if c["id"] == collector_id:
            collected = email_collector._simulate_email_fetch(c)
            return {"message": f"测试采集完成，收到 {len(collected)} 封邮件", "collected": collected}
    raise HTTPException(status_code=404, detail="采集器不存在")


# ============================================================
# ZIP 批量导入
# ============================================================

ALLOWED_IN_ZIP = {".jpg", ".jpeg", ".png", ".pdf", ".ofd"}
MAX_ZIP_SIZE = 100 * 1024 * 1024  # 100MB


@router.post("/zip-import")
async def import_zip(
    file: UploadFile = File(...),
    client_id: str = Form(...),
    db: Session = Depends(get_db),
    user=Depends(require_modify),
):
    """上传 ZIP 文件，自动解压并逐张入库"""
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="仅支持 ZIP 格式")

    content = await file.read()
    if len(content) > MAX_ZIP_SIZE:
        raise HTTPException(status_code=400, detail=f"ZIP 文件过大，最大 100MB")
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="文件为空")

    # 写入临时文件
    tmpdir = tempfile.mkdtemp(prefix="zip_import_")
    zip_path = os.path.join(tmpdir, file.filename)
    with open(zip_path, "wb") as f:
        f.write(content)

    # 解压
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            # 安全检查：防止 zip 炸弹
            total_size = sum(info.file_size for info in zf.infolist())
            if total_size > MAX_ZIP_SIZE * 3:
                raise HTTPException(status_code=400, detail="ZIP 解压后文件过大")
            zf.extractall(tmpdir)
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="ZIP 文件已损坏")

    upload_dir = "uploads"
    os.makedirs(upload_dir, exist_ok=True)

    imported = []
    skipped = []
    for root, dirs, files in os.walk(tmpdir):
        for fname in files:
            if fname == file.filename:
                continue  # 跳过 ZIP 本身
            ext = os.path.splitext(fname)[1].lower()
            if ext not in ALLOWED_IN_ZIP:
                skipped.append(fname)
                continue

            src = os.path.join(root, fname)
            safe_name = f"{uuid.uuid4().hex}{ext}"
            dest = os.path.join(upload_dir, safe_name)

            with open(src, "rb") as sf:
                with open(dest, "wb") as df:
                    df.write(sf.read())

            # 自动识别类型
            doc_type = "other"
            fn_lower = fname.lower()
            if "发票" in fn_lower or "invoice" in fn_lower:
                doc_type = "invoice"
            elif "回单" in fn_lower or "receipt" in fn_lower:
                doc_type = "bank_receipt"
            elif "合同" in fn_lower or "contract" in fn_lower:
                doc_type = "contract"
            elif "完税" in fn_lower:
                doc_type = "tax_cert"

            doc = OriginalDocument(
                id=str(uuid.uuid4()),
                source="zip_import",
                file_path=dest,
                file_name=fname,
                doc_type=doc_type,
                client_id=client_id,
                ocr_status="pending",
            )
            db.add(doc)
            db.flush()

            trace = create_trace(db, "document", doc.id, "zip_import")
            doc.qr_code_path = trace.qr_code_path

            commit(db, "document", doc.id, "zip_import", user.display_name or "",
                   after={"file_name": doc.file_name, "doc_type": doc_type})
            imported.append({"id": doc.id, "file_name": fname, "doc_type": doc_type})

    db.commit()

    # 清理临时目录
    try:
        import shutil
        shutil.rmtree(tmpdir)
    except Exception:
        pass

    return {
        "message": f"ZIP 导入完成：{len(imported)} 成功" + (f"，{len(skipped)} 跳过" if skipped else ""),
        "imported": len(imported),
        "skipped": len(skipped),
        "skipped_files": skipped[:20],
        "items": imported,
    }


# ============================================================
# 微信 / 钉钉 Webhook
# ============================================================

@router.get("/webhooks")
def list_webhooks(_=Depends(get_current_user)):
    configs = webhook_collector.get_configs()
    return {"items": configs}


@router.post("/webhooks")
def add_webhook(
    data: dict,
    user=Depends(require_modify),
):
    platform = data.get("platform", "").strip()
    client_id = data.get("client_id", "").strip()
    name = data.get("name", "").strip()

    if platform not in ("wechat", "dingtalk"):
        raise HTTPException(status_code=400, detail="平台仅支持 wechat 或 dingtalk")

    item = webhook_collector.add_webhook(platform, client_id, name)
    full_url = f"/api/webhook/{platform}?token={item['token']}"
    return {
        "message": f"{platform} webhook 已创建",
        "item": item,
        "full_webhook_url": full_url,
    }


@router.delete("/webhooks/{webhook_id}")
def remove_webhook(webhook_id: str, user=Depends(require_modify)):
    webhook_collector.remove_webhook(webhook_id)
    return {"message": "已移除 webhook"}


@router.patch("/webhooks/{webhook_id}/toggle")
def toggle_webhook(webhook_id: str, data: dict, user=Depends(require_not_client)):
    webhook_collector.toggle_webhook(webhook_id, data.get("enabled", True))
    return {"message": "状态已更新"}


# ============================================================
# Webhook 接收端点（外部可访问）
# ============================================================

@router.post("/webhook/wechat")
async def wechat_webhook(
    request: Request,
    token: str = Query(...),
    db: Session = Depends(get_db),
):
    """接收企业微信机器人消息"""
    config = webhook_collector.validate_token("wechat", token)
    if not config:
        raise HTTPException(status_code=403, detail="invalid token")

    try:
        body = await request.json()
    except Exception:
        body = {}

    # 微信机器人消息格式: {"msgtype": "image", "image": {"media_id": "..."}}
    file_urls = []
    file_names = []

    if body.get("msgtype") == "image":
        media_id = body.get("image", {}).get("media_id", "")
        if media_id:
            file_urls.append(f"https://qyapi.weixin.qq.com/cgi-bin/media/get?media_id={media_id}")
            file_names.append(f"wechat_{media_id}.jpg")
    elif body.get("msgtype") == "file":
        media_id = body.get("file", {}).get("media_id", "")
        fname = body.get("file", {}).get("file_name", f"wechat_{media_id}.pdf")
        if media_id:
            file_urls.append(f"https://qyapi.weixin.qq.com/cgi-bin/media/get?media_id={media_id}")
            file_names.append(fname)

    if file_urls:
        collected = webhook_collector.process_webhook_message(config, file_urls, file_names)
        return {"errcode": 0, "errmsg": "ok", "collected": len(collected)}

    return {"errcode": 0, "errmsg": "no file to process"}


@router.post("/webhook/dingtalk")
async def dingtalk_webhook(
    request: Request,
    token: str = Query(...),
    db: Session = Depends(get_db),
):
    """接收钉钉机器人消息"""
    config = webhook_collector.validate_token("dingtalk", token)
    if not config:
        raise HTTPException(status_code=403, detail="invalid token")

    try:
        body = await request.json()
    except Exception:
        body = {}

    file_urls = []
    file_names = []

    # 钉钉机器人消息格式
    if body.get("msgtype") == "image":
        pic_url = body.get("image", {}).get("picUrl", "")
        if pic_url:
            file_urls.append(pic_url)
            file_names.append(f"dingtalk_{uuid.uuid4().hex[:8]}.jpg")
    elif body.get("msgtype") == "file":
        download_url = body.get("file", {}).get("downloadUrl", "")
        fname = body.get("file", {}).get("fileName", f"dingtalk_file.pdf")
        if download_url:
            file_urls.append(download_url)
            file_names.append(fname)

    if file_urls:
        collected = webhook_collector.process_webhook_message(config, file_urls, file_names)
        return {"errcode": 0, "errmsg": "ok", "collected": len(collected)}

    return {"errcode": 0, "errmsg": "no file to process"}


# ============================================================
# 综合状态
# ============================================================

@router.get("/status")
def automation_overview(_=Depends(get_current_user)):
    """所有自动化通道状态概览"""
    fw = file_watcher.get_status()
    ec = email_collector.get_status()
    wh = webhook_collector.get_configs()
    return {
        "hot_folders": {"running": fw["running"], "count": fw["active_watchers"], "total": fw["watchers"]},
        "email_collectors": {"running": ec["running"], "count": ec["active_collectors"], "total": ec["collectors"]},
        "webhooks": {"total": len(wh), "active": sum(1 for w in wh if w.get("enabled", True))},
        "zip_import": {"enabled": True},
    }
