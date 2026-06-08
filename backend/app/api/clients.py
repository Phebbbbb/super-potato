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
    result = []
    for c in items:
        result.append({"id": c.id, "name": c.name, "tax_no": c.tax_no, "taxpayer_type": c.taxpayer_type,
                        "industry": c.industry, "contact_person": c.contact_person, "contact_phone": c.contact_phone,
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
    return {"id": c.id, "name": c.name, "tax_no": c.tax_no, "taxpayer_type": c.taxpayer_type,
            "industry": c.industry, "address": c.address, "contact_person": c.contact_person,
            "contact_phone": c.contact_phone, "service_start": str(c.service_start) if c.service_start else None,
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
    db.commit()
    cache_invalidate("clients:*")
    return {"id": c.id, "message": "客户创建成功"}


@router.patch("/{client_id}")
def update_client(client_id: str, data: dict, db: Session = Depends(get_db), user: User = Depends(require_modify)):
    c = db.query(Client).filter(Client.id == client_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="客户不存在")
    for field in ["name", "taxpayer_type", "industry", "address", "contact_person", "contact_phone", "remark", "is_active"]:
        if field in data:
            setattr(c, field, data[field])
    if "tax_no" in data:
        c.tax_no = data["tax_no"]
    db.commit()
    cache_invalidate("clients:*")
    return {"message": "客户信息已更新"}


@router.delete("/{client_id}")
def delete_client(client_id: str, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    c = db.query(Client).filter(Client.id == client_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="客户不存在")
    db.delete(c)
    db.commit()
    cache_invalidate("clients:*")
    return {"message": "客户已删除"}
