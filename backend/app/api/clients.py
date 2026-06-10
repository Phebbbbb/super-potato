"""客户管理 API"""
import json
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.db import get_db
from app.models.client import Client
from app.models.user import User
from app.services.auth import get_current_user, require_admin, require_modify
from app.services.version_control import commit
from app.services.cache import cache_get, cache_set, cache_invalidate
from app.schemas.core import ClientCreate, ClientUpdate

router = APIRouter()


@router.get("/")
def list_clients(
    search: str = Query(None),
    is_active: bool = Query(None),
    page: int = Query(1), page_size: int = Query(50),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    cache_key = f"clients:list:{search}:{is_active}:{page}:{page_size}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    q = db.query(Client)
    if search:
        q = q.filter(Client.name.contains(search) | Client.tax_no.contains(search) | Client.contact_person.contains(search))
    if is_active is not None:
        q = q.filter(Client.is_active == is_active)
    total = q.count()
    items = q.order_by(Client.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    # 批量查询 staff 名称
    staff_ids = [c.assigned_staff_id for c in items if c.assigned_staff_id]
    staff_map = {}
    if staff_ids:
        staffs = db.query(User).filter(User.id.in_(staff_ids)).all()
        staff_map = {s.id: s.display_name for s in staffs}

    result = []
    for c in items:
        result.append({"id": c.id, "name": c.name, "tax_no": c.tax_no, "taxpayer_type": c.taxpayer_type,
                        "industry": c.industry, "contact_person": c.contact_person, "contact_phone": c.contact_phone,
                        "assigned_staff_id": c.assigned_staff_id,
                        "assigned_staff_name": staff_map.get(c.assigned_staff_id, "") if c.assigned_staff_id else "",
                        "service_start": str(c.service_start) if c.service_start else None,
                        "service_end": str(c.service_end) if c.service_end else None,
                        "remark": c.remark, "is_active": c.is_active, "created_at": str(c.created_at)})
    result = {"items": result, "total": total, "page": page, "page_size": page_size}
    cache_set(cache_key, result, ttl=120)
    return result


@router.get("/{client_id}")
def get_client(client_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    c = db.query(Client).filter(Client.id == client_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="客户不存在")
    staff_name = ""
    if c.assigned_staff_id:
        s = db.query(User).filter(User.id == c.assigned_staff_id).first()
        staff_name = s.display_name if s else ""
    return {"id": c.id, "name": c.name, "tax_no": c.tax_no, "taxpayer_type": c.taxpayer_type,
            "industry": c.industry, "address": c.address, "contact_person": c.contact_person,
            "contact_phone": c.contact_phone,
            "assigned_staff_id": c.assigned_staff_id, "assigned_staff_name": staff_name,
            "service_start": str(c.service_start) if c.service_start else None,
            "service_end": str(c.service_end) if c.service_end else None,
            "remark": c.remark, "is_active": c.is_active, "created_at": str(c.created_at)}


@router.post("/")
def create_client(data: ClientCreate, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    """创建客户 — Pydantic 校验"""
    if data.tax_no:
        existing = db.query(Client).filter(Client.tax_no == data.tax_no).first()
        if existing:
            raise HTTPException(status_code=400, detail="该税号已存在")
    c = Client(
        id=uuid.uuid4().hex,
        name=data.name,
        tax_no=data.tax_no,
        taxpayer_type=data.taxpayer_type,
        industry=data.industry,
        contact_person=data.contact_name,
        contact_phone=data.contact_phone,
    )
    db.add(c)
    commit(db, "client", c.id, "created", user.display_name or "admin",
           after={"name": c.name, "tax_no": c.tax_no})
    from app.services.audit_service import log_action
    log_action(db, "client", c.id, "created", operator=user.display_name or user.username or "",
               detail={"name": c.name, "tax_no": c.tax_no, "taxpayer_type": c.taxpayer_type})
    db.commit()
    cache_invalidate("clients:*")
    return {"id": c.id, "message": "客户创建成功"}


@router.patch("/{client_id}")
def update_client(client_id: str, data: dict, db: Session = Depends(get_db), user: User = Depends(require_modify)):
    c = db.query(Client).filter(Client.id == client_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="客户不存在")

    # 专属人员分配：不允许两个不同服务人员服务同一客户
    if "assigned_staff_id" in data and data["assigned_staff_id"]:
        new_staff = data["assigned_staff_id"]
        if c.assigned_staff_id and c.assigned_staff_id != new_staff:
            old_staff = db.query(User).filter(User.id == c.assigned_staff_id).first()
            old_name = old_staff.display_name if old_staff else "未知"
            raise HTTPException(
                status_code=409,
                detail=f"该客户已由「{old_name}」专属服务，不可换人。如需变更请先由原负责人取消分配"
            )
        # 验证 staff 存在且非 client 角色
        staff = db.query(User).filter(User.id == new_staff, User.role != "client").first()
        if not staff:
            raise HTTPException(status_code=400, detail="指定服务人员不存在")
        c.assigned_staff_id = new_staff
    elif "assigned_staff_id" in data and not data["assigned_staff_id"]:
        c.assigned_staff_id = None

    before = {"name": c.name, "taxpayer_type": c.taxpayer_type, "industry": c.industry, "is_active": c.is_active}
    for field in ["name", "taxpayer_type", "industry", "address", "contact_person", "contact_phone", "remark", "is_active"]:
        if field in data:
            setattr(c, field, data[field])
    if "tax_no" in data:
        c.tax_no = data["tax_no"]
    commit(db, "client", client_id, "updated", user.display_name or "admin",
           before=before, after={"name": c.name, "taxpayer_type": c.taxpayer_type, "industry": c.industry, "is_active": c.is_active})
    from app.services.audit_service import log_action
    log_action(db, "client", client_id, "updated", operator=user.display_name or user.username or "",
               detail={"name": c.name, "taxpayer_type": c.taxpayer_type, "is_active": c.is_active})
    db.commit()
    cache_invalidate("clients:*")
    return {"message": "客户信息已更新"}


@router.get("/staff/available")
def available_staff(db: Session = Depends(get_db), _=Depends(get_current_user)):
    """可分配的服务端人员列表"""
    staffs = db.query(User).filter(User.role != "client", User.is_active == True).all()
    # 统计每人已服务的客户数
    from sqlalchemy import func as sqla_func
    assigned_counts = dict(
        db.query(Client.assigned_staff_id, sqla_func.count(Client.id))
        .filter(Client.assigned_staff_id != None)
        .group_by(Client.assigned_staff_id)
        .all()
    )
    return [
        {
            "id": s.id,
            "display_name": s.display_name,
            "username": s.username,
            "role": s.role,
            "assigned_count": assigned_counts.get(s.id, 0),
        }
        for s in staffs
    ]


@router.delete("/{client_id}")
def delete_client(client_id: str, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    c = db.query(Client).filter(Client.id == client_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="客户不存在")
    from app.services.audit_service import log_action
    log_action(db, "client", client_id, "deleted", operator=user.display_name or user.username or "",
               detail={"name": c.name, "tax_no": c.tax_no})
    commit(db, "client", client_id, "deleted", user.display_name or "admin",
           before={"name": c.name, "tax_no": c.tax_no, "is_active": c.is_active})
    db.delete(c)
    db.commit()
    cache_invalidate("clients:*")
    return {"message": "客户已删除"}
