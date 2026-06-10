"""客户订阅与权限模型"""
from datetime import datetime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Boolean, DateTime, func
from app.db import Base


class ClientSubscription(Base):
    """客户订阅 — 绑定手机号 + 企业，分试用/VIP"""
    __tablename__ = "client_subscriptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: __import__("uuid").uuid4().hex)
    client_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True, comment="关联客户")
    phone: Mapped[str] = mapped_column(String(20), nullable=False, index=True, comment="绑定手机号")
    tier: Mapped[str] = mapped_column(String(20), default="trial", comment="trial=半年试用 / vip=年费会员")
    status: Mapped[str] = mapped_column(String(20), default="active", comment="active/expired/cancelled")
    start_date: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="起始日")
    end_date: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="到期日")
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class LoginHistory(Base):
    """登录历史 — 服务端人员使用状态追踪"""
    __tablename__ = "login_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: __import__("uuid").uuid4().hex)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(50), nullable=False)
    display_name: Mapped[str] = mapped_column(String(50), nullable=True)
    role: Mapped[str] = mapped_column(String(20), nullable=True)
    login_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    ip_address: Mapped[str] = mapped_column(String(50), nullable=True)
    user_agent: Mapped[str] = mapped_column(String(255), nullable=True)
    login_type: Mapped[str] = mapped_column(String(20), default="password", comment="password=服务端 / sms=客户端")
