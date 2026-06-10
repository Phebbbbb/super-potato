"""认证 API — JWT 登录 / 令牌刷新 / 客户端手机验证码登录 / 注册 / 忘记密码"""
import random
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.db import get_db
from app.models.user import User, UserClientAssignment
from app.services.auth import (
    verify_password, create_access_token, get_current_user, hash_password,
    MAX_FAILED_ATTEMPTS, LOCKOUT_MINUTES,
)
from app.services.version_control import commit
from app.services.subscription_service import check_subscription_valid, record_login
from app.schemas.core import LoginRequest

router = APIRouter()

# 模拟短信验证码存储（生产环境替换为 Redis + 真实 SMS SDK）
_phone_codes: dict[str, tuple[str, datetime]] = {}


def _verify_sms_code(phone: str, code: str) -> bool:
    """校验短信验证码，成功则消费"""
    cached = _phone_codes.get(phone)
    if not cached:
        return False
    saved_code, expires = cached
    if datetime.now(timezone.utc) > expires:
        del _phone_codes[phone]
        return False
    if saved_code != code:
        return False
    del _phone_codes[phone]
    return True


class PhoneLoginRequest(BaseModel):
    phone: str = Field(..., min_length=11, max_length=11)
    code: str = Field(..., min_length=4, max_length=6)
    tax_no: str = Field(..., min_length=15, max_length=18, description="统一社会信用代码/税号")


class SendCodeRequest(BaseModel):
    phone: str = Field(..., min_length=11, max_length=11)


class ForgotPasswordRequest(BaseModel):
    phone: str = Field(..., min_length=11, max_length=11)
    code: str = Field(..., min_length=4, max_length=6)
    new_password: str = Field(..., min_length=6, max_length=100)


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)
    password: str = Field(..., min_length=6, max_length=100)
    display_name: str = Field(..., min_length=2, max_length=50)
    phone: str = Field(..., min_length=11, max_length=11)
    code: str = Field(..., min_length=4, max_length=6)


class BindPhoneRequest(BaseModel):
    phone: str = Field(..., min_length=11, max_length=11)
    code: str = Field(..., min_length=4, max_length=6)


class RememberMeLoginRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)
    password: str = Field(..., min_length=1, max_length=100)
    remember: bool = False


def _gen_code() -> str:
    return f"{random.randint(100000, 999999)}"


@router.post("/login")
def login(data: RememberMeLoginRequest, request: Request, db: Session = Depends(get_db)):
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

    # 记录登录历史（服务端人员）
    ip = request.client.host if request.client else ""
    ua = request.headers.get("user-agent", "")
    record_login(db, user, ip=ip, ua=ua, login_type="password")

    assignments = db.query(UserClientAssignment).filter(UserClientAssignment.user_id == user.id).all()
    client_ids = [a.client_id for a in assignments]

    # 记住密码：延长 token 有效期至 30 天
    token = create_access_token(user, expires_minutes=43200 if data.remember else None)
    commit(db, "user", user.id, "login", user.display_name or user.username,
           after={"username": user.username, "role": user.role})
    from app.services.audit_service import log_action
    log_action(db, "user", user.id, "login", operator=user.display_name or user.username,
               detail={"ip": ip, "role": user.role})
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


# ========================
# 短信验证码（共用）
# ========================

@router.post("/send-code")
def send_verification_code(data: SendCodeRequest):
    """发送手机验证码（开发模式：固定 123456；生产环境接入阿里云/腾讯云 SMS）"""
    import os
    code = "123456" if os.getenv("SMS_ENV", "dev") == "dev" else _gen_code()
    _phone_codes[data.phone] = (code, datetime.now(timezone.utc) + timedelta(minutes=5))
    print(f"[SMS] 手机号 {data.phone} 验证码: {code}")  # 生产环境删除此行
    return {"message": "验证码已发送", "expires_in": 300}


# ========================
# 注册（服务端人员）
# ========================

@router.post("/register")
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    """注册服务端账号：手机号 + 验证码 + 基本信息"""
    # 校验验证码
    if not _verify_sms_code(data.phone, data.code):
        raise HTTPException(status_code=401, detail="验证码无效或已过期")

    # 检查用户名是否已存在
    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(status_code=409, detail="用户名已被占用")

    # 检查手机号是否已被服务端账号绑定
    existing = db.query(User).filter(User.phone == data.phone, User.role != "client").first()
    if existing:
        raise HTTPException(status_code=409, detail="该手机号已被其他服务端账号绑定")

    user = User(
        username=data.username,
        password_hash=hash_password(data.password),
        display_name=data.display_name,
        role="viewer",  # 新注册默认最低权限，需管理员提升
        phone=data.phone,
        is_active=True,
    )
    db.add(user)
    db.flush()

    commit(db, "user", user.id, "register", user.display_name,
           after={"username": user.username, "role": user.role, "phone": user.phone})
    db.commit()

    token = create_access_token(user)
    return {
        "token": token,
        "user": {
            "id": user.id, "username": user.username,
            "display_name": user.display_name,
            "role": user.role, "phone": user.phone,
        },
        "client_ids": [],
    }


# ========================
# 忘记密码
# ========================

@router.post("/forgot-password")
def forgot_password(data: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """忘记密码：手机号 + 验证码 → 重置密码"""
    if not _verify_sms_code(data.phone, data.code):
        raise HTTPException(status_code=401, detail="验证码无效或已过期")

    # 查找绑定该手机号的服务端用户
    user = db.query(User).filter(User.phone == data.phone, User.role != "client").first()
    if not user:
        raise HTTPException(status_code=404, detail="该手机号未绑定任何服务端账号")

    user.password_hash = hash_password(data.new_password)
    user.failed_login_attempts = 0
    user.locked_until = None

    commit(db, "user", user.id, "password_reset", user.display_name,
           after={"message": "通过手机验证码重置密码"})
    db.commit()
    return {"message": "密码重置成功，请使用新密码登录"}


# ========================
# 绑定手机号（服务端人员）
# ========================

@router.post("/client-login")
def client_login(data: PhoneLoginRequest, request: Request, db: Session = Depends(get_db)):
    """客户端手机验证码登录 — 企业客户通过税号+手机号+验证码登录"""
    from app.models.client import Client
    from app.models.subscription import ClientSubscription
    from app.services.subscription_service import get_client_subscription

    if not _verify_sms_code(data.phone, data.code):
        raise HTTPException(status_code=401, detail="验证码无效或已过期")

    # 通过统一社会信用代码查找客户
    client = db.query(Client).filter(Client.tax_no == data.tax_no, Client.is_active == True).first()
    if not client:
        raise HTTPException(status_code=404, detail="未找到该税号对应的企业信息，请联系服务商开通")

    # 查找或创建客户端用户
    client_username = f"client_{client.id[:12]}"
    user = db.query(User).filter(User.username == client_username).first()
    if not user:
        user = User(
            username=client_username,
            password_hash=hash_password(data.phone),  # 用手机号做初始密码
            display_name=client.contact_person or client.name,
            role="client",
            phone=data.phone,
            is_active=True,
        )
        db.add(user)
        db.flush()
    else:
        # 更新手机号
        if user.phone != data.phone:
            user.phone = data.phone

    # 分配客户关系
    from app.models.user import UserClientAssignment
    assignment = db.query(UserClientAssignment).filter(
        UserClientAssignment.user_id == user.id,
        UserClientAssignment.client_id == client.id,
    ).first()
    if not assignment:
        db.add(UserClientAssignment(user_id=user.id, client_id=client.id, role="primary"))

    # 检查订阅状态
    sub = get_client_subscription(db, client.id)

    # 首次登录自动开通半年试用
    if not sub or sub.get("tier") == "none":
        from datetime import timedelta as _td
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        new_sub = ClientSubscription(
            client_id=client.id,
            phone=data.phone,
            tier="trial",
            status="active",
            start_date=now,
            end_date=now + _td(days=182),
            auto_renew=False,
            created_by="auto_trial",
        )
        db.add(new_sub)
        db.flush()
        sub = get_client_subscription(db, client.id)

    # 记录登录
    ip = request.client.host if request.client else ""
    ua = request.headers.get("user-agent", "")
    record_login(db, user, ip=ip, ua=ua, login_type="sms_code")

    from app.services.audit_service import log_action
    log_action(db, "user", user.id, "client_login", operator=user.display_name or client.name,
               detail={"client_id": client.id, "tax_no": data.tax_no, "ip": ip})

    # 生成 token
    token = create_access_token(user)

    db.commit()

    return {
        "token": token,
        "user": {
            "id": user.id, "username": user.username,
            "display_name": user.display_name,
            "role": user.role, "phone": user.phone,
        },
        "client_ids": [client.id],
        "subscription": sub,
    }


@router.post("/bind-phone")
def bind_phone(
    data: BindPhoneRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """服务端人员绑定/更换手机号"""
    if not _verify_sms_code(data.phone, data.code):
        raise HTTPException(status_code=401, detail="验证码无效或已过期")

    # 检查手机号是否已被其他服务端账号绑定
    existing = db.query(User).filter(
        User.phone == data.phone,
        User.role != "client",
        User.id != current_user.id,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="该手机号已被其他账号绑定")

    current_user.phone = data.phone
    commit(db, "user", current_user.id, "phone_bind", current_user.display_name,
           after={"phone": data.phone})
    db.commit()
    return {"message": "手机号绑定成功", "phone": data.phone}
