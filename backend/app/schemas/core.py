"""Pydantic 请求校验模型 — 核心业务"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import date


class InvoiceItem(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    spec: str = Field(default="", max_length=50)
    unit: str = Field(default="", max_length=20)
    quantity: float = Field(default=1, ge=0)
    price: float = Field(default=0, ge=0)
    amount: float = Field(default=0, ge=0)
    tax_amount: float = Field(default=0, ge=0)
    tax_rate: float = Field(default=0, ge=0, le=1)


class InvoiceCreate(BaseModel):
    client_id: str = Field(..., min_length=1)
    buyer_name: str = Field(..., min_length=1, max_length=200)
    buyer_tax_no: str = Field(..., min_length=1, max_length=30)
    buyer_address: str = Field(default="", max_length=500)
    buyer_phone: str = Field(default="", max_length=30)
    buyer_bank: str = Field(default="", max_length=200)
    buyer_account: str = Field(default="", max_length=50)
    invoice_type: str = Field(default="electronic_normal")
    items: list[InvoiceItem] = Field(default_factory=list)
    remark: str = Field(default="", max_length=500)
    idempotency_key: str = Field(default="", max_length=64)

    @field_validator("items")
    @classmethod
    def at_least_one_item(cls, v):
        if not v:
            raise ValueError("至少需要一个商品行")
        return v


class VoucherEntry(BaseModel):
    account_code: str = Field(..., min_length=1, max_length=20)
    account_name: str = Field(..., min_length=1, max_length=100)
    debit: float = Field(default=0, ge=0)
    credit: float = Field(default=0, ge=0)
    summary: str = Field(default="", max_length=200)


class VoucherCreate(BaseModel):
    client_id: str = Field(..., min_length=1)
    voucher_date: date
    summary: str = Field(default="", max_length=500)
    entries: list[VoucherEntry] = Field(default_factory=list)

    @field_validator("entries")
    @classmethod
    def check_balance(cls, v):
        if len(v) < 2:
            raise ValueError("至少需要两条分录")
        total_debit = sum(e.debit for e in v)
        total_credit = sum(e.credit for e in v)
        if abs(total_debit - total_credit) > 0.01:
            raise ValueError(f"借贷不平衡：借方{total_debit}，贷方{total_credit}")
        return v


class ClientCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    tax_no: str = Field(default="", max_length=30)
    taxpayer_type: str = Field(default="small")
    industry: str = Field(default="")
    contact_name: str = Field(default="", max_length=100)
    contact_phone: str = Field(default="", max_length=30)
    status: str = Field(default="active")


class ClientUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=200)
    tax_no: Optional[str] = Field(default=None, max_length=30)
    taxpayer_type: Optional[str] = None
    industry: Optional[str] = None
    contact_name: Optional[str] = Field(default=None, max_length=100)
    contact_phone: Optional[str] = Field(default=None, max_length=30)
    status: Optional[str] = None


class FilingCreate(BaseModel):
    client_id: str = Field(..., min_length=1)
    tax_type: str = Field(..., min_length=1)
    period: str = Field(..., min_length=6, max_length=7)
    taxpayer_type: str = Field(default="small")
    company_name: str = Field(default="", max_length=200)
    tax_no: str = Field(default="", max_length=30)
    summary: dict = Field(default_factory=dict)
    remark: str = Field(default="", max_length=500)
    idempotency_key: str = Field(default="", max_length=64)


class EmployeeCreate(BaseModel):
    client_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1, max_length=50)
    position: str = Field(default="", max_length=100)
    department: str = Field(default="", max_length=100)
    base_salary: float = Field(default=0, ge=0)
    social_insurance_base: float = Field(default=0, ge=0)
    housing_fund_base: float = Field(default=0, ge=0)
    phone: str = Field(default="", max_length=30)
    id_card: str = Field(default="", max_length=20)
    bank_account: str = Field(default="", max_length=50)
    bank_name: str = Field(default="", max_length=100)
    hire_date: Optional[date] = None


class BankAccountCreate(BaseModel):
    client_id: str = Field(..., min_length=1)
    bank_name: str = Field(..., min_length=1, max_length=100)
    account_no: str = Field(..., min_length=1, max_length=50)
    account_name: str = Field(default="", max_length=200)


class FieldTaskCreate(BaseModel):
    client_id: str = Field(..., min_length=1)
    task_type: str = Field(..., min_length=1)
    title: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=1000)
    priority: str = Field(default="normal")
    assigned_to: str = Field(default="")
    deadline: Optional[date] = None


class AccountCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=20)
    name: str = Field(..., min_length=1, max_length=100)
    category: str = Field(default="asset")
    parent_code: Optional[str] = Field(default=None, max_length=20)
    direction: str = Field(default="debit")
    is_active: bool = Field(default=True)


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1, max_length=100)


class FilingUpdate(BaseModel):
    status: Optional[str] = Field(default=None, max_length=20)
    filing_result: Optional[dict] = None
    version: Optional[int] = Field(default=None, ge=1)


class VoucherConfirm(BaseModel):
    reviewer: str = Field(default="审核员", max_length=50)
    comment: str = Field(default="", max_length=500)
    version: Optional[int] = Field(default=None, ge=1)


class VoucherUpdate(BaseModel):
    summary: Optional[str] = Field(default=None, max_length=500)
    entries: Optional[list[VoucherEntry]] = None
    version: Optional[int] = Field(default=None, ge=1)


class AgentChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    context: str = Field(default="", max_length=2000)
