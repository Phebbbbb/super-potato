from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from app.config import settings

# 根据数据库类型自动适配连接参数
_is_sqlite = settings.database_url.startswith("sqlite")
_connect_args = {"check_same_thread": False} if _is_sqlite else {}
_pool_args = {} if _is_sqlite else {"pool_size": 10, "max_overflow": 20, "pool_pre_ping": True}

engine = create_engine(settings.database_url, echo=False, connect_args=_connect_args, **_pool_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
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

    Base.metadata.create_all(bind=engine)
