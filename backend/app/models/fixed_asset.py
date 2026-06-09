"""固定资产模型"""
from datetime import datetime, date
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Float, Date, DateTime, Text, func
from app.db import Base


class FixedAsset(Base):
    __tablename__ = "fixed_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    client_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    asset_code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, comment="资产编码")
    asset_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="资产名称")
    category: Mapped[str] = mapped_column(String(30), nullable=False, default="office", comment="房屋/电子设备/运输工具/办公家具/其他")
    purchase_date: Mapped[date] = mapped_column(Date, nullable=False, comment="购置日期")
    original_value: Mapped[float] = mapped_column(nullable=False, default=0, comment="原值")
    residual_rate: Mapped[float] = mapped_column(default=5.0, comment="残值率%")
    useful_life: Mapped[int] = mapped_column(default=36, comment="使用年限(月)")
    monthly_depreciation: Mapped[float] = mapped_column(default=0, comment="月折旧额")
    accumulated_depreciation: Mapped[float] = mapped_column(default=0, comment="累计折旧")
    net_value: Mapped[float] = mapped_column(default=0, comment="净值")
    status: Mapped[str] = mapped_column(String(20), default="in_use", comment="in_use/idle/disposed")
    location: Mapped[str] = mapped_column(String(100), nullable=True, comment="存放地点")
    remark: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
