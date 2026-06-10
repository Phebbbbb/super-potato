"""合同管理 API — CRUD + 到期提醒 + 收入确认关联"""
import uuid
import hashlib
import secrets
from datetime import date as dt_date, datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.db import get_db
from app.models.contract import Contract
from app.models.client import Client
from app.services.auth import require_modify, get_current_user, check_client_access
from app.services.version_control import commit
from app.services.notification_service import create_notification
from app.services.interaction_service import send_message_to_client

router = APIRouter()


def _contract_to_dict(c: Contract, expiring_ids: set) -> dict:
    return {
        "id": c.id, "client_id": c.client_id, "contract_no": c.contract_no,
        "contract_name": c.contract_name, "contract_type": c.contract_type,
        "counterparty": c.counterparty, "amount": c.amount,
        "start_date": c.start_date.isoformat() if c.start_date else None,
        "end_date": c.end_date.isoformat() if c.end_date else None,
        "status": c.status, "payment_terms": c.payment_terms,
        "revenue_period": c.revenue_period, "monthly_revenue": c.monthly_revenue,
        "remark": c.remark, "is_template": c.is_template, "template_id": c.template_id,
        "expiring_soon": c.id in expiring_ids,
        "e_sign_status": c.e_sign_status, "e_sign_platform": c.e_sign_platform,
        "e_sign_sent_at": c.e_sign_sent_at.isoformat() if c.e_sign_sent_at else None,
        "e_sign_signer_name": c.e_sign_signer_name, "e_sign_signer_phone": c.e_sign_signer_phone,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


@router.get("/")
def list_contracts(
    client_id: str = Query(None),
    status: str = Query(None),
    contract_type: str = Query(None),
    is_template: bool = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Contract)
    if client_id:
        q = q.filter(Contract.client_id == client_id)
    if status:
        q = q.filter(Contract.status == status)
    if contract_type:
        q = q.filter(Contract.contract_type == contract_type)
    if is_template is not None:
        q = q.filter(Contract.is_template == is_template)
    else:
        q = q.filter(Contract.is_template == False)  # 默认只返回已签合同
    items = q.order_by(Contract.end_date.asc()).all()

    today = dt_date.today()
    soon = today + timedelta(days=30)
    expiring_ids = {c.id for c in items if c.status == "active" and c.end_date and c.end_date <= soon}

    return {
        "items": [_contract_to_dict(c, expiring_ids) for c in items],
        "expiring_count": len(expiring_ids),
    }


@router.get("/templates")
def list_templates(db: Session = Depends(get_db)):
    """获取所有合同模板"""
    items = db.query(Contract).filter(Contract.is_template == True).order_by(Contract.created_at.desc()).all()
    return {
        "items": [_contract_to_dict(c, set()) for c in items],
    }


@router.post("/")
def create_contract(
    data: dict,
    db: Session = Depends(get_db),
    user=Depends(require_modify),
):
    is_template = data.get("is_template", False)
    c = Contract(
        id=str(uuid.uuid4()),
        client_id="" if is_template else data.get("client_id", ""),
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
        is_template=is_template,
        template_id=data.get("template_id"),
    )
    db.add(c)
    db.flush()

    if not is_template:
        today = dt_date.today()
        if c.end_date and c.end_date <= today + timedelta(days=30):
            create_notification(db, "deadline",
                                title=f"合同即将到期：{c.contract_name}",
                                message=f"合同 {c.contract_no} 将于 {c.end_date.isoformat()} 到期，对方单位：{c.counterparty}",
                                link="/contracts")

    commit(db, "contract", c.id, "created", user.display_name or "",
           after={"contract_name": c.contract_name, "amount": c.amount, "is_template": is_template})
    db.commit()
    label = "模板" if is_template else "合同"
    return {"id": c.id, "message": f"{label}「{c.contract_name}」已创建"}


@router.post("/from-template/{template_id}")
def create_from_template(
    template_id: str,
    data: dict,
    db: Session = Depends(get_db),
    user=Depends(require_modify),
):
    """从模板创建已签合同"""
    tpl = db.query(Contract).filter(Contract.id == template_id, Contract.is_template == True).first()
    if not tpl:
        raise HTTPException(status_code=404, detail="模板不存在")

    c = Contract(
        id=str(uuid.uuid4()),
        client_id=data.get("client_id", ""),
        contract_no=data.get("contract_no", f"CT-{uuid.uuid4().hex[:8].upper()}"),
        contract_name=data.get("contract_name", tpl.contract_name),
        contract_type=data.get("contract_type", tpl.contract_type),
        counterparty=data.get("counterparty", ""),
        amount=float(data.get("amount", tpl.amount)),
        start_date=dt_date.fromisoformat(data["start_date"]) if data.get("start_date") else dt_date.today(),
        end_date=dt_date.fromisoformat(data["end_date"]) if data.get("end_date") else dt_date.today(),
        status="active",
        payment_terms=data.get("payment_terms", tpl.payment_terms or ""),
        revenue_period=data.get("revenue_period", tpl.revenue_period or "monthly"),
        monthly_revenue=float(data.get("monthly_revenue", tpl.monthly_revenue or 0)),
        remark=data.get("remark", tpl.remark or ""),
        is_template=False,
        template_id=template_id,
    )
    db.add(c)
    db.flush()
    commit(db, "contract", c.id, "created_from_template", user.display_name or "",
           after={"contract_name": c.contract_name, "template": tpl.contract_name})
    db.commit()
    return {"id": c.id, "message": f"已从模板「{tpl.contract_name}」创建合同「{c.contract_name}」"}


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


ESIGN_PLATFORMS = {
    "fadada": "法大大",
    "bestsign": "上上签",
    "qiyuesuo": "契约锁",
    "esign": "e签宝",
}


@router.post("/{contract_id}/esign")
def send_esign(
    contract_id: str,
    data: dict,
    db: Session = Depends(get_db),
    user=Depends(require_modify),
):
    """发送合同至电子签平台，生成签署链接发送给客户"""
    c = db.query(Contract).filter(Contract.id == contract_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="合同不存在")
    if c.client_id and not check_client_access(c.client_id, user, db):
        raise HTTPException(status_code=403, detail="无权操作")
    if c.e_sign_status == "signed":
        raise HTTPException(status_code=400, detail="该合同已签署完成")

    platform = data.get("platform", "").strip()
    if platform not in ESIGN_PLATFORMS:
        raise HTTPException(status_code=400, detail=f"不支持的电子签平台，可选: {', '.join(ESIGN_PLATFORMS.keys())}")

    signer_name = data.get("signer_name", "").strip()
    signer_phone = data.get("signer_phone", "").strip()
    if not signer_name or not signer_phone:
        raise HTTPException(status_code=400, detail="签署人姓名和手机号不能为空")

    # 生成唯一签署令牌
    token = secrets.token_urlsafe(24)
    sign_link = f"/contracts/sign/{contract_id}?token={token}"

    c.e_sign_platform = platform
    c.e_sign_status = "sent"
    c.e_sign_sent_at = datetime.now()
    c.e_sign_signer_name = signer_name
    c.e_sign_signer_phone = signer_phone

    commit(db, "contract", contract_id, "esign_sent", user.display_name or "",
           after={"platform": ESIGN_PLATFORMS[platform], "signer": signer_name, "phone": signer_phone, "sign_link": sign_link})

    # 发送签署链接给客户（通过消息通知）
    try:
        send_message_to_client(db, c.client_id,
                               title=f"待签署合同：{c.contract_name}",
                               message=f"合同 {c.contract_no}（金额 ¥{c.amount:,.2f}）已通过{ESIGN_PLATFORMS[platform]}发起电子签，请尽快签署",
                               link=sign_link)
    except Exception:
        pass  # 消息发送失败不影响主流程

    create_notification(db, "deadline",
                        title=f"电子签已发送：{c.contract_name}",
                        message=f"合同 {c.contract_no} 已通过{ESIGN_PLATFORMS[platform]}发送给 {signer_name}（{signer_phone}）签署，签署链接：{sign_link}",
                        link="/contracts")

    db.commit()
    return {
        "message": f"合同已通过{ESIGN_PLATFORMS[platform]}发送至 {signer_name} 签署",
        "esign_status": "sent",
        "platform": platform,
        "platform_name": ESIGN_PLATFORMS[platform],
        "sign_link": sign_link,
        "signer_name": signer_name,
        "signer_phone": signer_phone,
    }


@router.patch("/{contract_id}/esign-status")
def update_esign_status(
    contract_id: str,
    data: dict,
    db: Session = Depends(get_db),
    user=Depends(require_modify),
):
    """更新电子签状态（模拟回调/手动更新）"""
    c = db.query(Contract).filter(Contract.id == contract_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="合同不存在")
    if c.client_id and not check_client_access(c.client_id, user, db):
        raise HTTPException(status_code=403, detail="无权操作")

    new_status = data.get("e_sign_status", "").strip()
    if new_status not in ("sent", "signed", "expired", "rejected"):
        raise HTTPException(status_code=400, detail="状态值无效，可选: sent/signed/expired/rejected")

    old_status = c.e_sign_status
    c.e_sign_status = new_status

    commit(db, "contract", contract_id, "esign_status_updated", user.display_name or "",
           before={"e_sign_status": old_status}, after={"e_sign_status": new_status})

    status_labels = {"signed": "已签署", "expired": "已过期", "rejected": "已拒签", "sent": "已发送"}
    create_notification(db, "rpa",
                        title=f"电子签状态更新：{c.contract_name}",
                        message=f"合同 {c.contract_no} 电子签状态变更为：{status_labels.get(new_status, new_status)}",
                        link="/contracts")

    db.commit()
    return {
        "message": f"电子签状态已更新为：{status_labels.get(new_status, new_status)}",
        "e_sign_status": new_status,
    }


@router.get("/{contract_id}/esign-log")
def get_esign_log(
    contract_id: str,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """查询电子签操作记录"""
    from app.models.audit_log import AuditLog
    logs = db.query(AuditLog).filter(
        AuditLog.target_type == "contract",
        AuditLog.target_id == contract_id,
        AuditLog.action.like("esign%"),
    ).order_by(AuditLog.created_at.desc()).limit(20).all()

    return {
        "items": [
            {
                "action": l.action,
                "operator": l.operator,
                "detail": l.detail,
                "created_at": l.created_at.isoformat() if l.created_at else None,
            }
            for l in logs
        ],
    }
