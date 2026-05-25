"""DocCheck 测试共享配置与 fixtures"""

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool

# ── 测试数据库 ──────────────────────────────────────────────
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop():
    """Session-scoped event loop for async tests."""
    import asyncio
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db_session():
    """Create a fresh in-memory SQLite DB for each test."""
    from database import Base, get_db

    engine = create_async_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    # patch the DB dependency
    import main as app_main
    app_main.get_db = override_get_db

    async with session_factory() as session:
        yield session


@pytest.fixture
def client(db_session):
    """FastAPI TestClient with overridden DB session."""
    from main import app
    with TestClient(app) as c:
        yield c


@pytest_asyncio.fixture
async def seed_users(db_session):
    """Insert default test users."""
    from models import User
    from passlib.hash import bcrypt
    users = [
        User(username="admin", password_hash=bcrypt.hash("admin123"),
             display_name="系统管理员", role="admin", is_active=True),
        User(username="reviewer", password_hash=bcrypt.hash("review123"),
             display_name="审核员张三", role="reviewer", is_active=True),
        User(username="writer", password_hash=bcrypt.hash("writer123"),
             display_name="编写者李四", role="writer", is_active=True),
        User(username="ruleadmin", password_hash=bcrypt.hash("rule123"),
             display_name="规则管理员王五", role="rule_admin", is_active=True),
        User(username="multi", password_hash=bcrypt.hash("multi123"),
             display_name="多角色赵六", role="writer,reviewer", is_active=True),
        User(username="disabled_user", password_hash=bcrypt.hash("disabled123"),
             display_name="已禁用用户", role="writer", is_active=False),
    ]
    for u in users:
        db_session.add(u)
    await db_session.commit()
    return users


@pytest_asyncio.fixture
async def seed_doc_types(db_session):
    """Insert test document types."""
    from models import DocType
    types = [
        DocType(name="立项报告", sort_order=1),
        DocType(name="技术规格说明书", sort_order=2),
        DocType(name="需求文档", sort_order=3),
    ]
    for t in types:
        db_session.add(t)
    await db_session.commit()
    return types


@pytest_asyncio.fixture
async def seed_rules(db_session, seed_doc_types):
    """Insert test rules."""
    from models import Rule
    rules = [
        Rule(doc_type_id=1, name="必须包含投资估算章节",
             description="立项报告应当包含投资估算相关内容，列出项目总预算、资金来源、分项费用",
             severity="must_fix", stage="all", sort_order=1, is_active=True),
        Rule(doc_type_id=1, name="封面信息完整",
             description="报告封面应包含项目名称、编制单位、日期",
             severity="suggest", stage="all", sort_order=2, is_active=True),
        Rule(doc_type_id=2, name="性能指标明确",
             description="技术规格说明书应对每个功能模块给出明确性能指标，不能只写'满足要求'",
             severity="must_fix", stage="all", sort_order=1, is_active=True),
        Rule(doc_type_id=2, name="技术方案对比分析",
             description="应至少提供2种技术方案的对比分析（优劣势、成本、风险）",
             severity="suggest", stage="final", sort_order=2, is_active=True),
        Rule(doc_type_id=1, name="禁用测试规则",
             description="这条规则已被禁用",
             severity="must_fix", stage="all", sort_order=99, is_active=False),
    ]
    for r in rules:
        db_session.add(r)
    await db_session.commit()
    return rules


@pytest_asyncio.fixture
async def login_admin(client, seed_users):
    """Log in as admin and return session cookies."""
    resp = client.post("/api/auth/login", data={
        "username": "admin",
        "password": "admin123",
    })
    assert resp.status_code == 200
    return client.cookies.get("session")


@pytest_asyncio.fixture
async def login_writer(client, seed_users):
    """Log in as writer."""
    resp = client.post("/api/auth/login", data={
        "username": "writer",
        "password": "writer123",
    })
    assert resp.status_code == 200


@pytest_asyncio.fixture
async def login_reviewer(client, seed_users):
    """Log in as reviewer."""
    resp = client.post("/api/auth/login", data={
        "username": "reviewer",
        "password": "review123",
    })
    assert resp.status_code == 200


@pytest_asyncio.fixture
async def login_rule_admin(client, seed_users):
    """Log in as rule admin."""
    resp = client.post("/api/auth/login", data={
        "username": "ruleadmin",
        "password": "rule123",
    })
    assert resp.status_code == 200
