import uuid
from datetime import datetime
from sqlalchemy import String, Enum, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class ChartOfAccount(Base):
    __tablename__ = "chart_of_accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False)  # 资产/负债/权益/收入/费用
    parent_code: Mapped[str] = mapped_column(String(20), nullable=True, default=None)
    direction: Mapped[str] = mapped_column(String(10), nullable=False, default="debit")  # debit=借方增加 / credit=贷方增加
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
