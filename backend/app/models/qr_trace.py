import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class QRTrace(Base):
    __tablename__ = "qr_traces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    target_type: Mapped[str] = mapped_column(String(20), nullable=False)  # document/voucher/tax_filing/report
    target_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    stage: Mapped[str] = mapped_column(String(20), nullable=False)  # ingest/ai_voucher/confirm/file_tax/report
    qr_code_path: Mapped[str] = mapped_column(String(500), nullable=True)
    scan_url: Mapped[str] = mapped_column(String(500), nullable=True)
    parent_qr_id: Mapped[str] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
