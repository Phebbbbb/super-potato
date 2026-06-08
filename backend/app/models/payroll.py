"""薪酬管理模型"""
from datetime import datetime, date
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Float, Boolean, DateTime, Date, Text, func
from app.db import Base


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: __import__("uuid").uuid4().hex)
    client_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    id_card: Mapped[str] = mapped_column(String(18), nullable=True)
    phone: Mapped[str] = mapped_column(String(20), nullable=True)
    position: Mapped[str] = mapped_column(String(50), nullable=True)
    department: Mapped[str] = mapped_column(String(50), nullable=True)
    hire_date: Mapped[date] = mapped_column(Date, nullable=True)
    base_salary: Mapped[float] = mapped_column(Float, default=0)
    social_insurance_base: Mapped[float] = mapped_column(Float, default=0)
    housing_fund_base: Mapped[float] = mapped_column(Float, default=0)
    bank_account: Mapped[str] = mapped_column(String(50), nullable=True)
    bank_name: Mapped[str] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active/resigned
    resigned_at: Mapped[date] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class PayrollBatch(Base):
    __tablename__ = "payroll_batches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: __import__("uuid").uuid4().hex)
    client_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    period: Mapped[str] = mapped_column(String(7), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft/confirmed/paid
    total_gross: Mapped[float] = mapped_column(Float, default=0)
    total_social_insurance: Mapped[float] = mapped_column(Float, default=0)
    total_housing_fund: Mapped[float] = mapped_column(Float, default=0)
    total_special_deduction: Mapped[float] = mapped_column(Float, default=0)
    total_taxable: Mapped[float] = mapped_column(Float, default=0)
    total_iit: Mapped[float] = mapped_column(Float, default=0)
    total_net_pay: Mapped[float] = mapped_column(Float, default=0)
    confirmed_by: Mapped[str] = mapped_column(String(50), nullable=True)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class PayrollDetail(Base):
    __tablename__ = "payroll_details"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: __import__("uuid").uuid4().hex)
    batch_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    employee_id: Mapped[str] = mapped_column(String(36), nullable=False)
    employee_name: Mapped[str] = mapped_column(String(50), nullable=False)
    base_salary: Mapped[float] = mapped_column(Float, default=0)
    overtime_pay: Mapped[float] = mapped_column(Float, default=0)
    bonus: Mapped[float] = mapped_column(Float, default=0)
    allowance: Mapped[float] = mapped_column(Float, default=0)
    deduction: Mapped[float] = mapped_column(Float, default=0)
    gross_pay: Mapped[float] = mapped_column(Float, default=0)
    social_insurance_personal: Mapped[float] = mapped_column(Float, default=0)
    housing_fund_personal: Mapped[float] = mapped_column(Float, default=0)
    special_deduction: Mapped[float] = mapped_column(Float, default=0)
    taxable_income: Mapped[float] = mapped_column(Float, default=0)
    iit: Mapped[float] = mapped_column(Float, default=0)
    net_pay: Mapped[float] = mapped_column(Float, default=0)
    remark: Mapped[str] = mapped_column(Text, nullable=True)
