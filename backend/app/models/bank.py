"""银行对账模型"""
from datetime import datetime, date
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Float, DateTime, Date, Text, func
from app.db import Base


class BankAccount(Base):
    __tablename__ = "bank_accounts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: __import__("uuid").uuid4().hex)
    client_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    account_no: Mapped[str] = mapped_column(String(30), nullable=False)
    bank_name: Mapped[str] = mapped_column(String(100), nullable=False)
    account_name: Mapped[str] = mapped_column(String(100), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="CNY")
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class BankStatementLine(Base):
    __tablename__ = "bank_statement_lines"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: __import__("uuid").uuid4().hex)
    bank_account_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    client_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str] = mapped_column(String(300), nullable=True)
    debit: Mapped[float] = mapped_column(Float, default=0)
    credit: Mapped[float] = mapped_column(Float, default=0)
    balance: Mapped[float] = mapped_column(Float, default=0)
    counterparty: Mapped[str] = mapped_column(String(100), nullable=True)
    match_status: Mapped[str] = mapped_column(String(20), default="unmatched")  # unmatched/auto_matched/manual_matched/ignored
    matched_voucher_id: Mapped[str] = mapped_column(String(36), nullable=True)
    match_confidence: Mapped[float] = mapped_column(Float, default=0)
    import_batch_id: Mapped[str] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ImportBatch(Base):
    __tablename__ = "import_batches"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: __import__("uuid").uuid4().hex)
    bank_account_id: Mapped[str] = mapped_column(String(36), nullable=False)
    client_id: Mapped[str] = mapped_column(String(36), nullable=False)
    file_name: Mapped[str] = mapped_column(String(200), nullable=True)
    period_start: Mapped[date] = mapped_column(Date, nullable=True)
    period_end: Mapped[date] = mapped_column(Date, nullable=True)
    total_debit: Mapped[float] = mapped_column(Float, default=0)
    total_credit: Mapped[float] = mapped_column(Float, default=0)
    line_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
