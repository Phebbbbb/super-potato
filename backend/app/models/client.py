"""客户档案模型"""
from datetime import datetime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Boolean, DateTime, Text, func
from app.db import Base


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: __import__("uuid").uuid4().hex)
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="公司名称")
    tax_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, comment="统一社会信用代码")
    taxpayer_type: Mapped[str] = mapped_column(String(20), default="small", comment="general/small")
    industry: Mapped[str] = mapped_column(String(30), nullable=True, comment="行业分类")
    address: Mapped[str] = mapped_column(String(255), nullable=True)
    contact_person: Mapped[str] = mapped_column(String(50), nullable=True, comment="联系人")
    contact_phone: Mapped[str] = mapped_column(String(20), nullable=True)
    service_start: Mapped[datetime] = mapped_column(DateTime, nullable=True, comment="服务起始日")
    service_end: Mapped[datetime] = mapped_column(DateTime, nullable=True, comment="合同到期日")
    remark: Mapped[str] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
