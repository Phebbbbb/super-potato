import uuid
from datetime import datetime
from sqlalchemy import String, Text, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class TaxFiling(Base):
    __tablename__ = "tax_filings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tax_type: Mapped[str] = mapped_column(String(30), nullable=False)  # 支持全部 18 个税种
    period: Mapped[str] = mapped_column(String(10), nullable=False)  # 2026-05
    rpa_task_id: Mapped[str] = mapped_column(String(36), nullable=True)
    version: Mapped[int] = mapped_column(default=1)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=True, unique=True)
    client_id: Mapped[str] = mapped_column(String(36), nullable=True, index=True)
    filing_result: Mapped[str] = mapped_column(Text, nullable=True)  # JSON string
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")  # pending/pending_review/submitted/success/failed
    reviewer: Mapped[str] = mapped_column(String(50), nullable=True)  # 审核人
    reviewed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)  # 审核时间
    review_comment: Mapped[str] = mapped_column(Text, nullable=True)  # 审核意见
    qr_code_path: Mapped[str] = mapped_column(String(500), nullable=True)
    filed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
