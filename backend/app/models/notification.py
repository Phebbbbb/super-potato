"""系统通知模型"""
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, Text
from app.db import Base


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(String(50), primary_key=True)
    user_id = Column(String(50), nullable=True, index=True, comment="接收用户ID，NULL=全站通知")
    type = Column(String(30), nullable=False, index=True, comment="通知类型: deadline/risk/announcement/rpa/system")
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=True)
    is_read = Column(Boolean, default=False, index=True)
    link = Column(String(500), nullable=True, comment="点击跳转路径")
    created_at = Column(DateTime, default=datetime.now)

    def __repr__(self):
        return f"<Notification {self.type}:{self.title}>"
