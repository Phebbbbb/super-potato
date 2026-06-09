"""合同管理 API — CRUD + 到期提醒 + 收入确认关联"""
import uuid
from datetime import date as dt_date, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.db import get_db
from app.models.contract import Contract
from app.services.auth import require_modify, get_current_user, check_client_access
from app.services.version_control import commit
from app.services.notification_service import create_notification

router = APIRouter()


@router.get("/")
def list_contracts(
    client_id: str = Query(None),
    status: str = Query(None),
    contract_type: str = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Contract)
    if client_id:
        q = q.filter(Contract.client_id == client_id)
    if status:
        q = q.filter(Contract.status == status)
    if contract_type:
        q = q.filter(Contract.contract_type == contract_type)
    items = q.order_by(Contract.end_date.asc()).all()

    today = dt_date.today()
    soon = today + timedelta(days=30)
    expiring_ids = {c.id for c in items if c.status == "active" and c.end_date and c.end_date <= soon}

    return {
        "items": [{
            "id": c.id, "client_id": c.client_id, "contract_no": c.contract_no,
            "contract_name": c.contract_name, "contract_type": c.contract_type,
            "counterparty": c.counterparty, "amount": c.amount,
            "start_date": c.start_date.isoformat() if c.start_date else None,
            "end_date": c.end_date.isoformat() if c.end_date else None,
            "status": c.status, "payment_terms": c.payment_terms,
            "revenue_period": c.revenue_period, "monthly_revenue": c.monthly_revenue,
            "remark": c.remark,
            "expiring_soon": c.id in expiring_ids,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        } for c in items],
        "expiring_count": len(expiring_ids),
    }


@router.post("/")
def create_contract(
    data: dict,
    db: Session = Depends(get_db),
    user=Depends(require_modify),
):
    c = Contract(
        id=str(uuid.uuid4()),
        client_id=data.get("client_id", ""),
        contract_no=data.get("contract_no", f"CT-{uuid.uuid4().hex[:8].upper()}"),
        contract_name=data["contract_name"],
        contract_type=data.get("contract_type", "service"),
        counterparty=data.get("counterparty", ""),
        amount=float(data.get("amount", 0)),
        start_date=dt_date.fromisoformat(data["start_date"]) if data.get("start_date") else dt_date.today(),
        end_date=dt_date.fromisoformat(data["end_date"]) if data.get("end_date") else dt_date.today(),
        status=data.get("status", "active"),
        payment_terms=data.get("payment_terms", ""),
        revenue_period=data.get("revenue_period", "monthly"),
        monthly_revenue=float(data.get("monthly_revenue", 0)),
        remark=data.get("remark", ""),
    )
    db.add(c)
    db.flush()

    # 即将到期提醒
    today = dt_date.today()
    if c.end_date and c.end_date <= today + timedelta(days=30):
        create_notification(db, "deadline",
                            title=f"合同即将到期：{c.contract_name}",
                            message=f"合同 {c.contract_no} 将于 {c.end_date.isoformat()} 到期，对方单位：{c.counterparty}",
                            link="/contracts")

    commit(db, "contract", c.id, "created", user.display_name or "",
           after={"contract_name": c.contract_name, "amount": c.amount})
    db.commit()
    return {"id": c.id, "message": f"合同 {c.contract_name} 已创建"}


@router.patch("/{contract_id}")
def update_contract(contract_id: str, data: dict, db: Session = Depends(get_db), user=Depends(require_modify)):
    c = db.query(Contract).filter(Contract.id == contract_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="合同不存在")
    if c.client_id and not check_client_access(c.client_id, user, db):
        raise HTTPException(status_code=403, detail="无权操作")
    before = {"contract_name": c.contract_name, "amount": c.amount, "status": c.status}
    for f in ["contract_name", "contract_type", "counterparty", "status", "contract_no", "payment_terms", "revenue_period", "remark"]:
        if f in data and data[f] is not None:
            setattr(c, f, data[f])
    if "amount" in data:
        c.amount = float(data["amount"])
    if "monthly_revenue" in data:
        c.monthly_revenue = float(data["monthly_revenue"])
    if "start_date" in data and data["start_date"]:
        c.start_date = dt_date.fromisoformat(data["start_date"])
    if "end_date" in data and data["end_date"]:
        c.end_date = dt_date.fromisoformat(data["end_date"])
    commit(db, "contract", contract_id, "updated", user.display_name or "", before=before,
           after={"contract_name": c.contract_name, "status": c.status})
    db.commit()
    return {"message": f"合同 {c.contract_name} 已更新"}


@router.delete("/{contract_id}")
def delete_contract(contract_id: str, db: Session = Depends(get_db), user=Depends(require_modify)):
    c = db.query(Contract).filter(Contract.id == contract_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="合同不存在")
    if c.client_id and not check_client_access(c.client_id, user, db):
        raise HTTPException(status_code=403, detail="无权操作")
    commit(db, "contract", contract_id, "deleted", user.display_name or "", before={"contract_name": c.contract_name})
    db.delete(c)
    db.commit()
    return {"message": f"合同 {c.contract_name} 已删除"}
