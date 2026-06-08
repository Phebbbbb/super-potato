import uuid
from datetime import datetime
from sqlalchemy import String, Text, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class OriginalDocument(Base):
    __tablename__ = "original_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="manual_upload")  # manual_upload / rpa_scan / rpa_bank
    file_path: Mapped[str] = mapped_column(String(500), nullable=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=True)
    doc_type: Mapped[str] = mapped_column(String(20), nullable=False, default="other")  # invoice/receipt/bank_receipt/contract/tax_cert/other
    rpa_task_id: Mapped[str] = mapped_column(String(36), nullable=True)
    client_id: Mapped[str] = mapped_column(String(36), nullable=True, index=True)
    ocr_structured: Mapped[str] = mapped_column(Text, nullable=True)  # JSON string
    qr_code_path: Mapped[str] = mapped_column(String(500), nullable=True)
    ocr_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")  # pending / done
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
