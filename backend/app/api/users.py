"""用户管理 API"""
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.db import get_db
from app.models.user import User, UserClientAssignment
from app.services.auth import hash_password, get_current_user, require_admin, validate_password_strength
from app.services.version_control import commit

router = APIRouter()


@router.get("/")
def list_users(page: int = Query(1), page_size: int = Query(50),
               db: Session = Depends(get_db), _: User = Depends(require_admin)):
    q = db.query(User).filter(User.is_active == True)
    total = q.count()
    items = q.offset((page - 1) * page_size).limit(page_size).all()
    result = [{"id": u.id, "username": u.username, "display_name": u.display_name,
                "role": u.role, "phone": u.phone, "created_at": str(u.created_at)} for u in items]
    return {"items": result, "total": total, "page": page, "page_size": page_size}


@router.post("/")
def create_user(data: dict, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    if db.query(User).filter(User.username == data.get("username", "")).first():
        raise HTTPException(status_code=400, detail="用户名已存在")
    password = data.get("password", "")
    if not password:
        raise HTTPException(status_code=400, detail="请输入密码")
    err = validate_password_strength(password)
    if err:
        raise HTTPException(status_code=400, detail=err)
    u = User(
        id=uuid.uuid4().hex,
        username=data["username"],
        password_hash=hash_password(password),
        display_name=data.get("display_name", data["username"]),
        role=data.get("role", "accountant"),
        phone=data.get("phone", ""),
    )
    db.add(u)
    commit(db, "user", u.id, "created", data.get("display_name", data["username"]),
           after={"username": u.username, "role": u.role})
    db.commit()
    return {"id": u.id, "message": "用户创建成功"}


@router.patch("/{user_id}")
def update_user(user_id: str, data: dict, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="用户不存在")
    before = {"display_name": u.display_name, "role": u.role, "is_active": u.is_active}
    for field in ["display_name", "role", "phone", "is_active"]:
        if field in data:
            setattr(u, field, data[field])
    if "password" in data:
        err = validate_password_strength(data["password"])
        if err:
            raise HTTPException(status_code=400, detail=err)
        u.password_hash = hash_password(data["password"])
    commit(db, "user", user_id, "updated", u.display_name,
           before=before, after={"display_name": u.display_name, "role": u.role, "is_active": u.is_active})
    db.commit()
    return {"message": "用户已更新"}


@router.post("/{user_id}/assign")
def assign_client(user_id: str, data: dict, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    client_id = data.get("client_id", "")
    if not client_id:
        raise HTTPException(status_code=400, detail="请指定客户")
    existing = db.query(UserClientAssignment).filter(
        UserClientAssignment.user_id == user_id,
        UserClientAssignment.client_id == client_id,
    ).first()
    if not existing:
        db.add(UserClientAssignment(id=uuid.uuid4().hex, user_id=user_id, client_id=client_id,
                                     role=data.get("role", "primary")))
        db.commit()
    return {"message": "已分配客户"}


@router.delete("/{user_id}/assign/{client_id}")
def unassign_client(user_id: str, client_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    db.query(UserClientAssignment).filter(
        UserClientAssignment.user_id == user_id,
        UserClientAssignment.client_id == client_id,
    ).delete()
    db.commit()
    return {"message": "已移除分配"}
