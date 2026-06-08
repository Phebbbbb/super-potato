"""操作审计日志 — 记录所有人工修改和系统操作，完整可追溯"""
import uuid
from datetime import datetime
from sqlalchemy import String, Text, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    target_type: Mapped[str] = mapped_column(String(30), nullable=False)  # document/voucher/filing/report
    target_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(30), nullable=False)  # created/updated/confirmed/rejected/corrected
    operator: Mapped[str] = mapped_column(String(50), nullable=False, default="system")  # system/ai/用户名
    detail: Mapped[str] = mapped_column(Text, nullable=True)  # 变更详情（修改前/修改后）
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
