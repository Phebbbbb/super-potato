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
from app.services.auth import get_current_user, require_modify, require_not_client, check_client_access, check_optimistic_lock
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
    _=Depends(get_current_user),
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

    from app.services.audit_service import log_action
    log_action(db, "filing", filing.id, "created", operator=user.display_name or user.username or "",
               detail={"tax_type": tax_type, "period": period, "client_id": data.client_id})

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

    from app.services.audit_service import log_action
    log_action(db, "filing", filing_id, "updated", operator=user.display_name or user.username or "",
               detail={"tax_type": f.tax_type, "period": f.period, "client_id": f.client_id, "status": f.status})

    db.commit()
    return {"message": "申报状态已更新", "filing_id": filing_id, "status": f.status}


@router.delete("/{filing_id}")
def delete_filing(filing_id: str, db: Session = Depends(get_db), user=Depends(require_modify)):
    """删除纳税申报记录"""
    f = db.query(TaxFiling).filter(TaxFiling.id == filing_id).first()
    if not f:
        raise HTTPException(status_code=404, detail="申报记录不存在")
    if f.client_id and not check_client_access(f.client_id, user, db):
        raise HTTPException(status_code=403, detail="无权访问该客户数据")

    from app.services.audit_service import log_action
    log_action(db, "filing", filing_id, "deleted", operator=user.display_name or user.username or "",
               detail={"tax_type": f.tax_type, "period": f.period, "client_id": f.client_id})

    commit(db, "tax_filing", filing_id, "deleted", user.display_name or "",
           before={"tax_type": f.tax_type, "period": f.period, "status": f.status})

    # 清理关联的 RPA 任务
    if f.rpa_task_id:
        task = db.query(RPATask).filter(RPATask.id == f.rpa_task_id).first()
        if task:
            db.delete(task)

    db.delete(f)
    db.commit()
    return {"message": "申报记录已删除", "filing_id": filing_id}


@router.post("/preview")
def preview_filing_data(data: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """预览申报数据 — 从已确认凭证自动计算，不保存"""
    tax_type = data.get("tax_type", "vat")
    period = data.get("period", "")
    taxpayer_type = data.get("taxpayer_type", "small")
    if not period:
        raise HTTPException(status_code=400, detail="请提供申报所属期")
    return preview_filing(db, tax_type, period, taxpayer_type)


@router.get("/missing-filings")
def scan_missing_filings(
    period: str = Query(...),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """漏报扫描 — 遍历所有客户，检测指定期间哪些税种尚未申报"""
    from app.models.client import Client

    TAX_TYPE_NAMES = {
        "vat": "增值税", "consumption_tax": "消费税", "corporate_income": "企业所得税",
        "individual_income": "个人所得税", "surtax": "附加税", "stamp_duty": "印花税",
        "property_tax": "房产税", "land_use_tax": "城镇土地使用税",
        "land_appreciation_tax": "土地增值税", "deed_tax": "契税",
        "vehicle_vessel_tax": "车船税", "vehicle_purchase_tax": "车辆购置税",
        "resource_tax": "资源税", "environmental_tax": "环境保护税",
        "farmland_occupation_tax": "耕地占用税", "tobacco_tax": "烟叶税", "customs_duty": "关税",
    }

    y, m = map(int, period.split("-"))

    # 确定本期应报税种
    monthly_types = ["vat", "surtax", "stamp_duty", "individual_income"]
    is_quarter = m in (1, 4, 7, 10)
    quarterly_types = ["corporate_income", "property_tax", "land_use_tax"] if is_quarter else []

    clients = db.query(Client).all()
    missing = []

    for client in clients:
        required = list(monthly_types)
        if is_quarter:
            required.extend(quarterly_types)
        # 小规模纳税人增值税/附加税按季
        if client.taxpayer_type == "small" and not is_quarter:
            required = [t for t in required if t not in ("vat", "surtax")]

        for tax_type in required:
            existing = db.query(TaxFiling).filter(
                TaxFiling.client_id == client.id,
                TaxFiling.period == period,
                TaxFiling.tax_type == tax_type,
            ).first()
            if not existing:
                missing.append({
                    "client_id": client.id,
                    "client_name": client.name,
                    "taxpayer_type": client.taxpayer_type or "small",
                    "tax_type": tax_type,
                    "tax_name": TAX_TYPE_NAMES.get(tax_type, tax_type),
                    "period": period,
                })

    return {
        "period": period,
        "total_clients": len(clients),
        "missing_count": len(missing),
        "items": missing,
    }
