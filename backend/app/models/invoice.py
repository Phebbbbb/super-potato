"""数电票/全电发票 开票模型"""
import uuid
from datetime import datetime, UTC
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base
from app.db import Base


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    client_id = Column(String(64), ForeignKey("clients.id"), nullable=False, index=True)

    # 购方信息
    buyer_name = Column(String(200), nullable=False)
    buyer_tax_no = Column(String(50), nullable=False)
    buyer_address = Column(String(300))
    buyer_phone = Column(String(30))
    buyer_bank = Column(String(200))
    buyer_account = Column(String(50))

    version = Column(Integer, default=1)
    idempotency_key = Column(String(64), unique=True)

    # 发票类型
    invoice_type = Column(String(20), default="electronic_normal")  # electronic_normal / electronic_special

    # 商品明细 JSON: [{name, spec, unit, quantity, price, amount, tax_rate, tax_amount}]
    items = Column(Text, nullable=False)

    # 金额汇总
    total_amount = Column(String(20))      # 不含税合计
    total_tax = Column(String(20))          # 税额合计
    grand_total = Column(String(20))        # 价税合计

    # 备注
    remark = Column(String(500))

    # 状态
    status = Column(String(20), default="draft")  # draft / issuing / issued / failed
    issued_at = Column(DateTime)

    # 电子税务局返回
    invoice_code = Column(String(50))
    invoice_no = Column(String(50))
    invoice_url = Column(String(500))
    screenshot_path = Column(String(500))

    # 审计
    created_by = Column(String(100))
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
