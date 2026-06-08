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
