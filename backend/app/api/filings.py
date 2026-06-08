import json
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.db import get_db
from app.models.filing import TaxFiling
from app.models.rpa_task import RPATask
from app.models.user import User
from app.services.qr_service import create_trace
from app.services.tax_service import preview_filing
from app.services.auth import get_current_user, require_modify, check_client_access, check_optimistic_lock
from app.services.version_control import commit
from app.schemas.core import FilingCreate, FilingUpdate

router = APIRouter()


@router.get("/")
def list_filings(
    page: int = 1,
    page_size: int = 20,
    tax_type: str = None,
    status: str = None,
    client_id: str = Query(None),
    db: Session = Depends(get_db),
):
    """纳税申报记录列表"""
    q = db.query(TaxFiling)
    if tax_type:
        q = q.filter(TaxFiling.tax_type == tax_type)
    if status:
        q = q.filter(TaxFiling.status == status)
    if client_id:
        q = q.filter(TaxFiling.client_id == client_id)

    total = q.count()
    items = (
        q.order_by(desc(TaxFiling.period), desc(TaxFiling.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {
        "items": [
            {
                "id": f.id,
                "tax_type": f.tax_type,
                "period": f.period,
                "rpa_task_id": f.rpa_task_id,
                "filing_result": json.loads(f.filing_result) if f.filing_result else None,
                "status": f.status,
                "reviewer": f.reviewer,
                "review_comment": f.review_comment,
                "qr_code_path": f.qr_code_path,
                "filed_at": f.filed_at.isoformat() if f.filed_at else None,
                "created_at": f.created_at.isoformat() if f.created_at else None,
            }
            for f in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{filing_id}")
def get_filing(filing_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """纳税申报记录详情"""
    f = db.query(TaxFiling).filter(TaxFiling.id == filing_id).first()
    if not f:
        raise HTTPException(status_code=404, detail="申报记录不存在")
    if f.client_id and not check_client_access(f.client_id, user, db):
        raise HTTPException(status_code=403, detail="无权访问该客户数据")

    from app.services.qr_service import get_trace_chain
    trace = get_trace_chain(db, "tax_filing", f.id)

    return {
        "id": f.id,
        "tax_type": f.tax_type,
        "period": f.period,
        "rpa_task_id": f.rpa_task_id,
        "filing_result": json.loads(f.filing_result) if f.filing_result else None,
        "status": f.status,
        "reviewer": f.reviewer,
        "review_comment": f.review_comment,
        "qr_code_path": f.qr_code_path,
        "trace_chain": trace,
        "filed_at": f.filed_at.isoformat() if f.filed_at else None,
        "created_at": f.created_at.isoformat() if f.created_at else None,
    }


@router.post("/")
def create_filing(data: FilingCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user), _=Depends(require_modify)):
    """创建纳税申报任务 — 自动生成关联 RPA 任务"""
    if data.idempotency_key:
        existing = db.query(TaxFiling).filter(TaxFiling.idempotency_key == data.idempotency_key).first()
        if existing:
            return {
                "id": existing.id,
                "tax_type": existing.tax_type,
                "period": existing.period,
                "rpa_task_id": existing.rpa_task_id,
                "status": existing.status,
                "qr_code_path": existing.qr_code_path,
                "message": "申报任务已存在（幂等）",
            }

    tax_type = data.tax_type
    period = data.period

    # 创建 RPA 任务
    rpa_task = RPATask(
        id=str(uuid.uuid4()),
        task_type="file_tax",
        status="pending",
        payload=json.dumps({
            "tax_type": tax_type,
            "period": period,
            "company_name": data.company_name,
            "tax_no": data.tax_no,
            "summary": data.summary,
        }, ensure_ascii=False),
    )
    db.add(rpa_task)
    db.flush()

    # 创建申报记录
    filing = TaxFiling(
        id=str(uuid.uuid4()),
        tax_type=tax_type,
        period=period,
        rpa_task_id=rpa_task.id,
        client_id=data.client_id,
        status="pending",
        idempotency_key=data.idempotency_key or None,
    )
    db.add(filing)
    db.flush()

    # 自动计算申报数据（从已确认凭证汇总）
    try:
        tax_data = preview_filing(db, tax_type, period, data.taxpayer_type)
        filing.filing_result = json.dumps(tax_data, ensure_ascii=False)
    except Exception:
        pass

    # 生成 QR 码
    trace = create_trace(db, "tax_filing", filing.id, "file_tax")
    filing.qr_code_path = trace.qr_code_path

    commit(db, "tax_filing", filing.id, "created", user.display_name or "",
           after={"tax_type": tax_type, "period": period, "client_id": data.client_id})

    db.commit()

    return {
        "id": filing.id,
        "tax_type": filing.tax_type,
        "period": filing.period,
        "rpa_task_id": rpa_task.id,
        "status": "pending",
        "qr_code_path": filing.qr_code_path,
        "message": "申报任务已创建，RPA 将自动执行申报",
    }


@router.patch("/{filing_id}")
def update_filing(filing_id: str, data: FilingUpdate, db: Session = Depends(get_db), user=Depends(require_modify)):
    """更新申报状态（由 RPA 回写）"""
    f = db.query(TaxFiling).filter(TaxFiling.id == filing_id).first()
    if not f:
        raise HTTPException(status_code=404, detail="申报记录不存在")
    if f.client_id and not check_client_access(f.client_id, user, db):
        raise HTTPException(status_code=403, detail="无权访问该客户数据")

    check_optimistic_lock(f, data.model_dump())

    old_status = f.status
    if data.status is not None:
        f.status = data.status
    if data.filing_result is not None:
        f.filing_result = json.dumps(data.filing_result, ensure_ascii=False)
    if data.status == "success":
        f.filed_at = datetime.now()

    if f.rpa_task_id:
        task = db.query(RPATask).filter(RPATask.id == f.rpa_task_id).first()
        if task:
            if data.status is not None:
                task.status = data.status
            if data.filing_result is not None:
                task.result = json.dumps(data.filing_result, ensure_ascii=False)

    if old_status != f.status:
        commit(db, "tax_filing", filing_id, "status_change", user.display_name or "",
               before={"status": old_status}, after={"status": f.status})

    db.commit()
    return {"message": "申报状态已更新", "filing_id": filing_id, "status": f.status}


@router.post("/preview")
def preview_filing_data(data: dict, db: Session = Depends(get_db)):
    """预览申报数据 — 从已确认凭证自动计算，不保存"""
    tax_type = data.get("tax_type", "vat")
    period = data.get("period", "")
    taxpayer_type = data.get("taxpayer_type", "small")
    if not period:
        raise HTTPException(status_code=400, detail="请提供申报所属期")
    return preview_filing(db, tax_type, period, taxpayer_type)
