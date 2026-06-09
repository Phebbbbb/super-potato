"""工商年报模型 — 企业年度报告公示（市场监督管理局）"""
import uuid
from datetime import datetime, UTC
from sqlalchemy import Column, String, Text, DateTime, Integer, ForeignKey
from app.db import Base


class AnnualReport(Base):
    __tablename__ = "annual_reports"

    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    client_id = Column(String(64), ForeignKey("clients.id"), nullable=False, index=True)

    # 报告年度
    report_year = Column(Integer, nullable=False)  # 如 2025

    # ===== 企业基本信息 =====
    company_name = Column(String(200), nullable=False)
    unified_social_credit_code = Column(String(50), nullable=False)
    legal_representative = Column(String(100))
    contact_phone = Column(String(30))
    contact_email = Column(String(100))
    business_address = Column(String(300))
    postal_code = Column(String(10))
    website_url = Column(String(200))
    business_scope = Column(Text)
    employee_count = Column(Integer)
    is_listed = Column(String(10), default="否")  # 是/否

    # ===== 股东及出资信息 =====
    shareholders = Column(Text)  # JSON: [{name, contribution_type, subscribed_amount, subscribed_date, paid_amount, paid_date}]

    # ===== 资产状况信息 (万元) =====
    total_assets = Column(String(20))         # 资产总额
    total_liabilities = Column(String(20))    # 负债总额
    net_assets = Column(String(20))           # 净资产
    annual_revenue = Column(String(20))       # 营业收入
    annual_profit = Column(String(20))        # 利润总额
    annual_net_profit = Column(String(20))    # 净利润
    annual_tax_paid = Column(String(20))      # 纳税总额

    # ===== 对外担保信息 =====
    external_guarantees = Column(Text)  # JSON: [{creditor, debtor, guarantee_type, amount, period, due_date}]

    # ===== 党建信息 =====
    party_members_count = Column(Integer)
    has_party_org = Column(String(10), default="否")

    # ===== 社保信息 =====
    social_insurance_participants = Column(Integer)       # 参保人数
    social_insurance_base = Column(String(20))            # 单位缴费基数（万元）
    social_insurance_paid = Column(String(20))            # 实际缴费金额（万元）
    social_insurance_arrears = Column(String(20))         # 欠缴金额（万元）

    # ===== 状态 =====
    status = Column(String(20), default="draft")  # draft / submitted / published
    submitted_at = Column(DateTime)
    published_at = Column(DateTime)
    samr_receipt_no = Column(String(100))  # 市场监管局回执号

    # 审计
    created_by = Column(String(100))
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
