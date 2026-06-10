from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.exc import DisconnectionError
from app.config import settings

# 根据数据库类型自动适配连接参数
_is_sqlite = settings.database_url.startswith("sqlite")
_connect_args = {"check_same_thread": False} if _is_sqlite else {}

# PostgreSQL 连接池配置 — 基于 fastapi-full-stack-template 生产模式
_pool_args = {} if _is_sqlite else {
    "pool_size": 10,
    "max_overflow": 20,
    "pool_pre_ping": True,       # 使用前验证连接有效性
    "pool_recycle": 3600,        # 每小时回收连接，避免超过服务端超时
    "pool_timeout": 10,          # 获取连接超时，快速失败
}

engine = create_engine(
    settings.database_url,
    echo=False,
    connect_args=_connect_args,
    **_pool_args,
)


# 连接池事件监听 — 检测连接泄漏
@event.listens_for(engine, "checkout")
def _on_checkout(dbapi_conn, connection_record, connection_proxy):
    pool = engine.pool
    if hasattr(pool, "size"):
        checked_out = getattr(pool, "_checked_out_count", None)
        if checked_out is not None and checked_out > pool.size() * 0.8:
            import logging
            logging.getLogger("sqlalchemy.pool").warning(
                f"连接池使用率 >80%: checked_out={checked_out}, pool_size={pool.size()}"
            )


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI 依赖 — 确保 session 在请求结束后关闭并归还连接"""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db():
    from app.models.account import ChartOfAccount
    from app.models.document import OriginalDocument
    from app.models.voucher import AccountingVoucher
    from app.models.filing import TaxFiling
    from app.models.qr_trace import QRTrace
    from app.models.rpa_task import RPATask
    from app.models.audit_log import AuditLog
    from app.models.system_config import SystemConfig
    from app.models.client import Client
    from app.models.user import User, UserClientAssignment
    from app.models.payroll import Employee, PayrollBatch, PayrollDetail
    from app.models.bank import BankAccount, BankStatementLine, ImportBatch
    from app.models.field_task import FieldTask
    from app.models.invoice import Invoice
    from app.models.tax_announcement import TaxAnnouncement
    from app.models.notification import Notification
    from app.models.fixed_asset import FixedAsset
    from app.models.contract import Contract
    from app.models.annual_report import AnnualReport
    from app.models.correction_learning import CorrectionRecord, LearnedPattern
    from app.models.subscription import ClientSubscription, LoginHistory
    from app.models.wechat_binding import WeChatBinding

    Base.metadata.create_all(bind=engine)
