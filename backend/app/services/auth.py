"""权限校验 — bcrypt 密码哈希 + JWT 令牌 + 角色鉴权 + 多租户隔离"""
import re
from datetime import datetime, timedelta, timezone
from passlib.context import CryptContext
from jose import jwt, JWTError
from fastapi import Depends, HTTPException, Header, Query
from sqlalchemy.orm import Session
from app.db import get_db
from app.config import settings
from app.models.user import User, UserClientAssignment

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15
MIN_PASSWORD_LENGTH = 8


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def validate_password_strength(password: str) -> str | None:
    """校验密码强度，返回 None 表示通过，否则返回错误描述"""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"密码至少 {MIN_PASSWORD_LENGTH} 位"
    if not re.search(r"[A-Za-z]", password):
        return "密码需包含字母"
    if not re.search(r"\d", password):
        return "密码需包含数字"
    return None


def create_access_token(user: User, expires_minutes: int | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes or settings.jwt_expire_minutes)
    payload = {
        "sub": user.id,
        "username": user.username,
        "role": user.role,
        "display_name": user.display_name,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        raise HTTPException(status_code=401, detail="会话已过期，请重新登录")


def get_current_user(
    authorization: str = Header(None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization:
        raise HTTPException(status_code=401, detail="未登录")
    token = authorization.replace("Bearer ", "")
    payload = decode_access_token(token)
    user = db.query(User).filter(User.id == payload["sub"], User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在或已禁用")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role not in ("admin", "super_admin"):
        raise HTTPException(status_code=403, detail="仅管理员可执行此操作")
    return user


def require_modify(user: User = Depends(get_current_user)) -> User:
    if user.role not in ("admin", "super_admin", "reviewer"):
        raise HTTPException(status_code=403, detail="无修改权限，需管理员或审核员角色")
    return user


def require_not_client(user: User = Depends(get_current_user)) -> User:
    """阻止 client 角色执行写操作"""
    if user.role == "client":
        raise HTTPException(status_code=403, detail="客户端用户仅可访问票据管理和AI顾问")
    return user


def get_user_client_ids(user: User, db: Session) -> set[str]:
    """获取用户被分配的客户 ID 集合"""
    assignments = db.query(UserClientAssignment).filter(UserClientAssignment.user_id == user.id).all()
    return {a.client_id for a in assignments}


def check_client_access(client_id: str, user: User, db: Session) -> bool:
    """检查用户是否有权限访问指定客户"""
    if user.role in ("admin", "super_admin"):
        return True
    return client_id in get_user_client_ids(user, db)


def check_optimistic_lock(obj, data: dict):
    """乐观锁校验 — 版本号不匹配抛 409；不传或传 None 则跳过校验"""
    expected = data.get("version") if isinstance(data, dict) else obj.version
    if expected is None:
        expected = obj.version
    if obj.version != expected:
        from fastapi import HTTPException
        raise HTTPException(status_code=409, detail="数据已被他人修改，请刷新后重试")
    obj.version += 1


def require_client_access(
    client_id: str = Query(..., description="客户ID"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> str:
    """依赖注入：校验当前用户有权访问指定客户，返回 client_id"""
    if user.role in ("admin", "super_admin"):
        return client_id
    assignments = db.query(UserClientAssignment).filter(
        UserClientAssignment.user_id == user.id,
        UserClientAssignment.client_id == client_id,
    ).first()
    if not assignments:
        raise HTTPException(status_code=403, detail="无权访问该客户数据")
    return client_id
