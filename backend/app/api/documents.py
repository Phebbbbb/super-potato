import json
import os
import uuid
import aiofiles
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Form, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.db import get_db
from app.models.document import OriginalDocument
from app.services.auth import get_current_user, require_modify, check_client_access
from app.schemas.document import DocumentQuery
from app.services.qr_service import create_trace
from app.services.version_control import commit
from app.config import settings

router = APIRouter()

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf"}
MAX_UPLOAD_SIZE = 20 * 1024 * 1024  # 20MB


@router.get("/")
def list_documents(
    page: int = 1,
    page_size: int = 20,
    doc_type: str = None,
    source: str = None,
    client_id: str = Query(None),
    db: Session = Depends(get_db),
):
    """原始凭证列表（支持分页和筛选）"""
    q = db.query(OriginalDocument)
    if doc_type:
        q = q.filter(OriginalDocument.doc_type == doc_type)
    if source:
        q = q.filter(OriginalDocument.source == source)
    if client_id:
        q = q.filter(OriginalDocument.client_id == client_id)

    total = q.count()
    items = (
        q.order_by(desc(OriginalDocument.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {
        "items": [
            {
                "id": d.id,
                "source": d.source,
                "file_name": d.file_name,
                "doc_type": d.doc_type,
                "ocr_status": d.ocr_status,
                "ocr_structured": json.loads(d.ocr_structured) if d.ocr_structured else None,
                "qr_code_path": d.qr_code_path,
                "rpa_task_id": d.rpa_task_id,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{doc_id}")
def get_document(doc_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """原始凭证详情"""
    doc = db.query(OriginalDocument).filter(OriginalDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="凭证不存在")
    if doc.client_id and not check_client_access(doc.client_id, user, db):
        raise HTTPException(status_code=403, detail="无权访问该客户数据")
    return {
        "id": doc.id,
        "source": doc.source,
        "file_name": doc.file_name,
        "file_path": doc.file_path,
        "doc_type": doc.doc_type,
        "ocr_status": doc.ocr_status,
        "ocr_structured": json.loads(doc.ocr_structured) if doc.ocr_structured else None,
        "qr_code_path": doc.qr_code_path,
        "rpa_task_id": doc.rpa_task_id,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
    }


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    doc_type: str = Form("other"),
    client_id: str = Form(None),
    db: Session = Depends(get_db),
    user=Depends(require_modify),
):
    """手动上传原始凭证（RPA 覆盖不到的场景）"""
    if client_id and not check_client_access(client_id, user, db):
        raise HTTPException(status_code=403, detail="无权访问该客户数据")

    ext = os.path.splitext(file.filename or ".jpg")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {ext}")

    # 文件大小限制
    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail=f"文件过大，最大支持 20MB")
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="文件为空")

    safe_name = f"{uuid.uuid4().hex}{ext}"
    upload_path = os.path.join(settings.upload_dir, safe_name)
    abs_path = os.path.join(os.getcwd(), upload_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)

    async with aiofiles.open(abs_path, "wb") as f:
        await f.write(content)

    doc = OriginalDocument(
        id=str(uuid.uuid4()),
        source="manual_upload",
        file_path=upload_path,
        file_name=file.filename,
        doc_type=doc_type,
        client_id=client_id,
        ocr_status="pending",
    )
    db.add(doc)
    db.flush()

    trace = create_trace(db, "document", doc.id, "ingest")
    doc.qr_code_path = trace.qr_code_path

    commit(db, "document", doc.id, "ingest", user.display_name or "",
           after={"file_name": doc.file_name, "doc_type": doc.doc_type, "client_id": client_id})

    db.commit()

    return {
        "id": doc.id,
        "file_name": doc.file_name,
        "doc_type": doc.doc_type,
        "qr_code_path": doc.qr_code_path,
        "message": "上传成功",
    }


@router.post("/{doc_id}/re-ocr")
def re_ocr_document(doc_id: str, db: Session = Depends(get_db), user=Depends(require_modify)):
    """重新 OCR 识别 — 将文档重置为待识别状态"""
    doc = db.query(OriginalDocument).filter(OriginalDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="凭证不存在")
    if doc.client_id and not check_client_access(doc.client_id, user, db):
        raise HTTPException(status_code=403, detail="无权访问该客户数据")

    doc.ocr_status = "pending"
    doc.ocr_structured = None
    commit(db, "document", doc_id, "re-ocr", user.display_name or "",
           before={"ocr_status": "done"}, after={"ocr_status": "pending"})
    db.commit()
    return {"id": doc_id, "message": "已重新提交 OCR 识别"}


@router.delete("/{doc_id}")
def delete_document(doc_id: str, db: Session = Depends(get_db), user=Depends(require_modify)):
    """删除原始凭证"""
    doc = db.query(OriginalDocument).filter(OriginalDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="凭证不存在")
    if doc.client_id and not check_client_access(doc.client_id, user, db):
        raise HTTPException(status_code=403, detail="无权访问该客户数据")

    commit(db, "document", doc_id, "deleted", user.display_name or "",
           before={"file_name": doc.file_name, "doc_type": doc.doc_type})

    # 删除文件（防路径穿越）
    if doc.file_path:
        base_dir = os.path.realpath(os.path.join(os.getcwd(), settings.upload_dir))
        abs_path = os.path.realpath(os.path.join(os.getcwd(), doc.file_path))
        if abs_path.startswith(base_dir) and os.path.exists(abs_path):
            os.remove(abs_path)

    db.delete(doc)
    db.commit()
    return {"message": "删除成功", "id": doc_id}


# ===== 多渠道采集 =====

@router.get("/collection-channels")
def get_collection_channels(
    client_id: str = Query(None),
    db: Session = Depends(get_db),
):
    """获取可用采集渠道及配置"""
    return {
        "channels": [
            {
                "key": "manual",
                "name": "手动上传",
                "icon": "upload",
                "desc": "拖拽或点击上传 JPG/PNG/PDF 文件",
                "enabled": True,
            },
            {
                "key": "email",
                "name": "邮件采集",
                "icon": "mail",
                "desc": "将发票邮件转发至专属采集邮箱，系统自动解析入库",
                "enabled": True,
                "config": {
                    "email": f"collect+{client_id or 'default'}@zhangyaoyao.com",
                    "status": "active",
                },
            },
            {
                "key": "tax_pull",
                "name": "电子税务局拉取",
                "icon": "cloud-download",
                "desc": "通过 Playwright 自动登录电子税务局，拉取进项发票数据",
                "enabled": True,
            },
            {
                "key": "qr_scan",
                "name": "扫码采集",
                "icon": "qrcode",
                "desc": "生成采集二维码，手机扫码拍照上传票据",
                "enabled": True,
            },
            {
                "key": "webhook",
                "name": "微信/钉钉机器人",
                "icon": "robot",
                "desc": "配置企业微信或钉钉机器人，自动接收群聊中的票据文件",
                "enabled": True,
            },
        ],
    }


@router.post("/email-collect")
def trigger_email_collect(
    client_id: str = Query(...),
    db: Session = Depends(get_db),
    user=Depends(require_modify),
):
    """模拟邮件采集：扫描采集邮箱，导入新发票"""
    import uuid as _uuid
    from datetime import date as _date, datetime as _dt

    # 模拟从邮件服务器拉取的发票
    mock_files = [
        {"file_name": f"增值税发票_{_dt.now().strftime('%Y%m%d')}_{i}.pdf", "doc_type": "invoice"}
        for i in range(1, 4)
    ]

    created = []
    for mf in mock_files:
        safe_name = f"{_uuid.uuid4().hex}.pdf"
        upload_path = os.path.join(settings.upload_dir, safe_name)
        abs_path = os.path.join(os.getcwd(), upload_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        # 创建占位文件
        with open(abs_path, "wb") as f:
            f.write(b"%PDF-1.4 email collected placeholder")

        doc = OriginalDocument(
            id=str(_uuid.uuid4()),
            source="email_collect",
            file_path=upload_path,
            file_name=mf["file_name"],
            doc_type=mf["doc_type"],
            client_id=client_id,
            ocr_status="pending",
        )
        db.add(doc)
        db.flush()

        trace = create_trace(db, "document", doc.id, "email_collect")
        doc.qr_code_path = trace.qr_code_path

        commit(db, "document", doc.id, "email_collect", user.display_name or "",
               after={"file_name": doc.file_name, "source": "email_collect"})
        created.append({"id": doc.id, "file_name": doc.file_name})

    db.commit()
    return {
        "message": f"邮件采集完成，共导入 {len(created)} 张发票",
        "collected": len(created),
        "items": created,
    }


@router.post("/tax-pull")
def trigger_tax_pull(
    client_id: str = Query(...),
    start_date: str = Query(None),
    end_date: str = Query(None),
    db: Session = Depends(get_db),
    user=Depends(require_modify),
):
    """模拟从电子税务局拉取进项发票数据"""
    import uuid as _uuid
    from datetime import date as _date, datetime as _dt

    today = _date.today()
    start = _date.fromisoformat(start_date) if start_date else today.replace(day=1)
    end = _date.fromisoformat(end_date) if end_date else today

    # 模拟从电子税务局拉取的发票
    mock_invoices = [
        {"file_name": f"进项发票_{start.isoformat()}_{i}.pdf", "doc_type": "invoice"}
        for i in range(1, 6)
    ]

    created = []
    for mi in mock_invoices:
        safe_name = f"{_uuid.uuid4().hex}.pdf"
        upload_path = os.path.join(settings.upload_dir, safe_name)
        abs_path = os.path.join(os.getcwd(), upload_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "wb") as f:
            f.write(b"%PDF-1.4 tax-bureau pulled placeholder")

        doc = OriginalDocument(
            id=str(_uuid.uuid4()),
            source="tax_pull",
            file_path=upload_path,
            file_name=mi["file_name"],
            doc_type=mi["doc_type"],
            client_id=client_id,
            ocr_status="pending",
        )
        db.add(doc)
        db.flush()

        trace = create_trace(db, "document", doc.id, "tax_pull")
        doc.qr_code_path = trace.qr_code_path

        commit(db, "document", doc.id, "tax_pull", user.display_name or "",
               after={"file_name": doc.file_name, "source": "tax_pull"})
        created.append({"id": doc.id, "file_name": doc.file_name})

    db.commit()
    return {
        "message": f"电子税务局拉取完成，期间 {start}~{end}，共拉取 {len(created)} 张进项发票",
        "collected": len(created),
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "items": created,
    }


@router.get("/collection-qr")
def get_collection_qr(
    client_id: str = Query(None),
):
    """获取扫码采集二维码"""
    base_url = f"/upload?client_id={client_id}" if client_id else "/upload"
    return {
        "url": base_url,
        "tip": "手机扫描二维码，拍照上传发票、收据等原始凭证",
        "expires_in": "24小时",
    }


# ===== 文档解析引擎 (Kreuzberg) =====

@router.post("/parse")
async def parse_document_endpoint(
    file: UploadFile = File(...),
    extract_tables: bool = Form(True),
):
    """通用文档解析 → Markdown/JSON（50+格式支持）"""
    from app.services.document_parser import parse_document

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="文件为空")

    tmp_path = os.path.join(settings.upload_dir, f"_parse_{uuid.uuid4().hex}{os.path.splitext(file.filename or '.bin')[1]}")
    os.makedirs(os.path.dirname(os.path.join(os.getcwd(), tmp_path)), exist_ok=True)
    with open(os.path.join(os.getcwd(), tmp_path), "wb") as f:
        f.write(content)

    try:
        result = parse_document(os.path.join(os.getcwd(), tmp_path), extract_tables=extract_tables)
        result["file_name"] = file.filename
        result["file_size"] = len(content)
        return result
    finally:
        if os.path.exists(os.path.join(os.getcwd(), tmp_path)):
            os.remove(os.path.join(os.getcwd(), tmp_path))


@router.post("/parse-invoice")
async def parse_invoice_endpoint(
    file: UploadFile = File(...),
):
    """发票专用解析 → 结构化字段提取"""
    from app.services.document_parser import parse_invoice

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="文件为空")

    tmp_path = os.path.join(settings.upload_dir, f"_parse_inv_{uuid.uuid4().hex}{os.path.splitext(file.filename or '.pdf')[1]}")
    os.makedirs(os.path.dirname(os.path.join(os.getcwd(), tmp_path)), exist_ok=True)
    with open(os.path.join(os.getcwd(), tmp_path), "wb") as f:
        f.write(content)

    try:
        result = parse_invoice(os.path.join(os.getcwd(), tmp_path))
        result["file_name"] = file.filename
        return result
    finally:
        if os.path.exists(os.path.join(os.getcwd(), tmp_path)):
            os.remove(os.path.join(os.getcwd(), tmp_path))


@router.post("/parse-receipt")
async def parse_receipt_endpoint(
    file: UploadFile = File(...),
):
    """收据/小票解析"""
    from app.services.document_parser import parse_receipt

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="文件为空")

    tmp_path = os.path.join(settings.upload_dir, f"_parse_rcpt_{uuid.uuid4().hex}{os.path.splitext(file.filename or '.jpg')[1]}")
    os.makedirs(os.path.dirname(os.path.join(os.getcwd(), tmp_path)), exist_ok=True)
    with open(os.path.join(os.getcwd(), tmp_path), "wb") as f:
        f.write(content)

    try:
        result = parse_receipt(os.path.join(os.getcwd(), tmp_path))
        result["file_name"] = file.filename
        return result
    finally:
        if os.path.exists(os.path.join(os.getcwd(), tmp_path)):
            os.remove(os.path.join(os.getcwd(), tmp_path))


@router.post("/parse-bank-statement")
async def parse_bank_statement_endpoint(
    file: UploadFile = File(...),
):
    """银行流水解析 → 结构化交易列表"""
    from app.services.document_parser import parse_bank_statement

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="文件为空")

    tmp_path = os.path.join(settings.upload_dir, f"_parse_bank_{uuid.uuid4().hex}{os.path.splitext(file.filename or '.csv')[1]}")
    os.makedirs(os.path.dirname(os.path.join(os.getcwd(), tmp_path)), exist_ok=True)
    with open(os.path.join(os.getcwd(), tmp_path), "wb") as f:
        f.write(content)

    try:
        result = parse_bank_statement(os.path.join(os.getcwd(), tmp_path))
        result["file_name"] = file.filename
        return result
    finally:
        if os.path.exists(os.path.join(os.getcwd(), tmp_path)):
            os.remove(os.path.join(os.getcwd(), tmp_path))
