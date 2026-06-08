"""系统配置持久化模型"""
from datetime import datetime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Text, DateTime, func
from app.db import Base


class SystemConfig(Base):
    __tablename__ = "system_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: __import__("uuid").uuid4().hex)
    config_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    config_value: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
