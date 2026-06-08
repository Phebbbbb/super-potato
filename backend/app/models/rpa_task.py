import uuid
from datetime import datetime
from sqlalchemy import String, Text, Enum, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class RPATask(Base):
    __tablename__ = "rpa_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_type: Mapped[str] = mapped_column(String(30), nullable=False)  # scan_invoice / file_tax / fetch_bank
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")  # pending/assigned/processing/done/failed
    payload: Mapped[str] = mapped_column(Text, nullable=True)  # JSON string
    result: Mapped[str] = mapped_column(Text, nullable=True)  # JSON string
    assigned_rpa: Mapped[str] = mapped_column(String(100), nullable=True)
    client_id: Mapped[str] = mapped_column(String(36), nullable=True, index=True)
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
