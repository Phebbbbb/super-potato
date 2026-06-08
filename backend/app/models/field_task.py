"""外勤任务模型 — 线下跑腿也留痕"""
from datetime import datetime, date
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Text, DateTime, Date, func
from app.db import Base


class FieldTask(Base):
    __tablename__ = "field_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: __import__("uuid").uuid4().hex)
    client_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    task_type: Mapped[str] = mapped_column(String(30), nullable=False, comment="tax_bureau/business_reg/bank/client_visit/document_delivery/other")
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", comment="pending/assigned/in_progress/completed/failed")
    assigned_to: Mapped[str] = mapped_column(String(36), nullable=True, comment="FK users.id")
    priority: Mapped[str] = mapped_column(String(10), default="normal", comment="low/normal/high/urgent")
    deadline: Mapped[date] = mapped_column(Date, nullable=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    attachments: Mapped[str] = mapped_column(Text, nullable=True, comment="JSON: [{name,url}] 现场照片等")
    notes: Mapped[str] = mapped_column(Text, nullable=True, comment="执行记录")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
