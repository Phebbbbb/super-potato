"""认证 API — JWT 登录 / 令牌刷新 / 账户锁定"""
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db import get_db
from app.models.user import User, UserClientAssignment
from app.services.auth import (
    verify_password, create_access_token, get_current_user,
    MAX_FAILED_ATTEMPTS, LOCKOUT_MINUTES,
)
from app.services.version_control import commit
from app.schemas.core import LoginRequest

router = APIRouter()


@router.post("/login")
def login(data: LoginRequest, db: Session = Depends(get_db)):
    username = data.username
    password = data.password

    user = db.query(User).filter(User.username == username, User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    # 检查账户是否被锁定
    now = datetime.now(timezone.utc)
    if user.locked_until and user.locked_until > now:
        remaining = int((user.locked_until - now).total_seconds() / 60) + 1
        raise HTTPException(status_code=423, detail=f"账户已被锁定，{remaining} 分钟后重试")

    if not verify_password(password, user.password_hash):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
            user.locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
            user.failed_login_attempts = 0
        db.commit()
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    # 登录成功，清除失败计数
    user.failed_login_attempts = 0
    user.locked_until = None

    assignments = db.query(UserClientAssignment).filter(UserClientAssignment.user_id == user.id).all()
    client_ids = [a.client_id for a in assignments]

    token = create_access_token(user)
    commit(db, "user", user.id, "login", user.display_name or user.username,
           after={"username": user.username, "role": user.role})
    db.commit()

    return {
        "token": token,
        "user": {
            "id": user.id, "username": user.username,
            "display_name": user.display_name,
            "role": user.role, "phone": user.phone,
        },
        "client_ids": client_ids,
    }


@router.post("/refresh")
def refresh_token(user: User = Depends(get_current_user)):
    token = create_access_token(user)
    return {"token": token, "user": {"id": user.id, "username": user.username, "display_name": user.display_name, "role": user.role}}


@router.get("/me")
def get_me(user: User = Depends(get_current_user)):
    return {
        "id": user.id, "username": user.username,
        "display_name": user.display_name,
        "role": user.role, "phone": user.phone,
    }
