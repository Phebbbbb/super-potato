"""国家税务总局公告"""
import uuid
from datetime import datetime, UTC
from sqlalchemy import Column, String, Text, DateTime
from app.db import Base


class TaxAnnouncement(Base):
    __tablename__ = "tax_announcements"

    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(500), nullable=False)
    url = Column(String(500), nullable=False)
    source = Column(String(100), default="国家税务总局")
    pub_date = Column(String(20))          # 发布日期原文
    pub_date_parsed = Column(DateTime)      # 解析后的日期，用于排序
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
