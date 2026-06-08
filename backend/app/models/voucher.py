import uuid
from datetime import datetime, date
from sqlalchemy import String, Text, Date, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class AccountingVoucher(Base):
    __tablename__ = "accounting_vouchers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    voucher_no: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    voucher_date: Mapped[date] = mapped_column(Date, nullable=False)
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    source_doc_ids: Mapped[str] = mapped_column(Text, nullable=True)  # JSON array of document IDs
    entries: Mapped[str] = mapped_column(Text, nullable=False)  # JSON array of {account_code, account_name, debit, credit, summary}
    total_debit: Mapped[float] = mapped_column(nullable=False, default=0)
    total_credit: Mapped[float] = mapped_column(nullable=False, default=0)
    qr_code_path: Mapped[str] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")  # draft / pending_review / confirmed / rejected / cancelled
    client_id: Mapped[str] = mapped_column(String(36), nullable=True, index=True)
    version: Mapped[int] = mapped_column(default=1)
    created_by: Mapped[str] = mapped_column(String(20), nullable=False, default="ai")  # ai / manual
    reviewer: Mapped[str] = mapped_column(String(50), nullable=True)  # 审核人
    reviewed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)  # 审核时间
    review_comment: Mapped[str] = mapped_column(Text, nullable=True)  # 审核意见
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
