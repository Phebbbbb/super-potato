"""
自学习纠错模型 — 系统越用越聪明

核心思路：
  每次人工修正 → 记录 (原文, 修正后, 上下文特征)
  → 定期归纳为模式 → 新数据自动匹配模式 → 自动纠错
"""
from sqlalchemy import Column, String, Float, Integer, DateTime, Text, Index
from app.db import Base
from datetime import datetime


class CorrectionRecord(Base):
    """人工修正记录 — 学习的原始素材"""
    __tablename__ = "correction_records"

    id = Column(String(36), primary_key=True)
    target_type = Column(String(32), nullable=False, index=True)  # ocr / voucher_entries / account_mapping
    target_id = Column(String(36), nullable=False, index=True)  # document_id / voucher_id
    field_path = Column(String(128), nullable=False)  # e.g. "invoice.amount" / "entries[0].account_code"
    original_value = Column(Text, default="")
    corrected_value = Column(Text, default="")
    context_json = Column(Text, default="{}")  # 上下文特征: vendor_name, amount_range, field_position, etc.
    operator = Column(String(64), default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_cr_target", "target_type", "target_id"),
        Index("ix_cr_type_field", "target_type", "field_path"),
    )


class LearnedPattern(Base):
    """学习到的模式 — 可用于自动纠错"""
    __tablename__ = "learned_patterns"

    id = Column(String(36), primary_key=True)
    pattern_type = Column(String(32), nullable=False, index=True)  # ocr_fix / vendor_template / account_mapping / field_rule
    name = Column(String(128), default="")  # 人类可读的模式名
    conditions_json = Column(Text, default="{}")  # 匹配条件
    action_json = Column(Text, default="{}")  # 匹配后执行的动作
    confidence = Column(Float, default=0.5)  # 置信度 0-1
    match_count = Column(Integer, default=0)  # 此模式被匹配次数
    success_count = Column(Integer, default=0)  # 自动纠错被采纳次数
    last_applied_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_lp_type_conf", "pattern_type", "confidence"),
    )
