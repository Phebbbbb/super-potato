"""合同管理模型"""
from datetime import datetime, date
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Float, Date, DateTime, Text, func
from app.db import Base


class Contract(Base):
    __tablename__ = "contracts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    client_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    contract_no: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, comment="合同编号")
    contract_name: Mapped[str] = mapped_column(String(200), nullable=False, comment="合同名称")
    contract_type: Mapped[str] = mapped_column(String(30), nullable=False, default="service", comment="service/sales/purchase/lease/other")
    counterparty: Mapped[str] = mapped_column(String(100), nullable=False, comment="对方单位")
    amount: Mapped[float] = mapped_column(nullable=False, default=0, comment="合同金额")
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", comment="active/expired/terminated/completed")
    payment_terms: Mapped[str] = mapped_column(Text, nullable=True, comment="付款条款")
    revenue_period: Mapped[str] = mapped_column(String(20), nullable=True, comment="收入确认期间 monthly/quarterly/once")
    monthly_revenue: Mapped[float] = mapped_column(default=0, comment="月均确认收入")
    remark: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
