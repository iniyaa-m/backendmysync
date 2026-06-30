import asyncio
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.main import app
from app.database.base import Base, get_db

# Use in-memory SQLite for tests
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


async def override_get_db():
    async with TestSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_database():
    """Create all tables before tests and drop after."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed badges
    from app.services.gamification_service import seed_badges
    async with TestSessionLocal() as db:
        await seed_badges(db)

    yield

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def db_session():
    async with TestSessionLocal() as session:
        yield session


# ─── Helper fixtures ──────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def student_token(client: AsyncClient) -> str:
    """Register and login a student, return access token."""
    await client.post("/api/v1/auth/register", json={
        "name": "Test Student",
        "email": "student@test.com",
        "password": "test1234",
        "role": "student",
    })
    resp = await client.post("/api/v1/auth/login", json={
        "email": "student@test.com",
        "password": "test1234",
    })
    return resp.json()["access_token"]


@pytest_asyncio.fixture
async def teacher_token(client: AsyncClient) -> str:
    """Register and login a teacher, return access token."""
    await client.post("/api/v1/auth/register", json={
        "name": "Test Teacher",
        "email": "teacher@test.com",
        "password": "test1234",
        "role": "teacher",
    })
    resp = await client.post("/api/v1/auth/login", json={
        "email": "teacher@test.com",
        "password": "test1234",
    })
    return resp.json()["access_token"]
