"""测试 fixtures — 内存 SQLite + TestClient"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.db import Base, get_db
from app.models.user import User, UserClientAssignment  # noqa: F401
from app.models.client import Client  # noqa: F401
from app.models.document import OriginalDocument  # noqa: F401
from app.models.voucher import AccountingVoucher  # noqa: F401
from app.models.filing import TaxFiling  # noqa: F401
from app.models.account import ChartOfAccount  # noqa: F401
from app.models.system_config import SystemConfig  # noqa: F401
from app.models.rpa_task import RPATask  # noqa: F401
from app.models.audit_log import AuditLog  # noqa: F401
from app.models.qr_trace import QRTrace  # noqa: F401
from app.models.payroll import Employee, PayrollBatch, PayrollDetail  # noqa: F401
from app.models.bank import BankAccount, BankStatementLine, ImportBatch  # noqa: F401
from app.models.field_task import FieldTask  # noqa: F401
from app.models.invoice import Invoice  # noqa: F401
from app.services.auth import hash_password, create_access_token
from sqlalchemy.pool import StaticPool

TEST_DB_URL = "sqlite:///:memory:"
_engine = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    echo=False,
    poolclass=StaticPool,  # 确保单连接，避免 :memory: 跨连接丢失
)
_TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


@pytest.fixture(scope="function")
def db_session():
    """每个测试独立的数据库会话"""
    Base.metadata.create_all(bind=_engine)
    db = _TestingSessionLocal()
    yield db
    db.close()
    Base.metadata.drop_all(bind=_engine)


@pytest.fixture(scope="function")
def client(db_session: Session):
    """FastAPI TestClient，注入测试数据库"""

    def override_get_db():
        yield db_session

    from app.main import app
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _ensure_test_user(db: Session) -> str:
    """确保存在测试用户，返回 token"""
    from app.models.user import User
    user = db.query(User).filter(User.username == "testuser").first()
    if not user:
        user = User(
            id="test-user-001",
            username="testuser",
            display_name="测试用户",
            password_hash=hash_password("Test1234!"),
            role="admin",
            is_active=True,
        )
        db.add(user)
        db.commit()
    return create_access_token(user)


@pytest.fixture
def auth_headers(client, db_session):
    """创建测试用户并返回带 token 的 headers"""
    token = _ensure_test_user(db_session)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def sample_client(client, auth_headers, db_session):
    """创建一个测试客户"""
    resp = client.post("/api/clients/", json={
        "name": "测试科技有限公司",
        "tax_no": "91110108MA01TEST",
        "taxpayer_type": "small",
        "contact_name": "张三",
        "contact_phone": "13800138000",
    }, headers=auth_headers)
    assert resp.status_code == 200, f"创建客户失败: status={resp.status_code} body={resp.text}"
    return resp.json()
