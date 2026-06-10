"""微信用户绑定模型"""
from datetime import datetime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, DateTime, func
from app.db import Base


class WeChatBinding(Base):
    __tablename__ = "wechat_bindings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: __import__("uuid").uuid4().hex)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    openid: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    unionid: Mapped[str | None] = mapped_column(String(128), nullable=True)
    nickname: Mapped[str | None] = mapped_column(String(100), nullable=True)
    avatar: Mapped[str | None] = mapped_column(String(500), nullable=True)
    bound_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
