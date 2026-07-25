"""Test configuration and shared fixtures.

Fixtures:
- `db_session` — async SQLAlchemy session with rollback (test isolation)
- `client` — async httpx client wired to the FastAPI app
- `redis_mock` — in-memory Redis mock
- `settings_test` — settings override for testing
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Configure test environment BEFORE importing app code
os.environ.setdefault("ENV", "development")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://krishisetu:krishisetu_test@localhost:5432/krishisetu_test",
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")  # Use DB 15 for tests
os.environ.setdefault(
    "JWT_SECRET",
    "test-secret-must-be-at-least-32-characters-long-for-validation",
)
os.environ.setdefault("S3_ENDPOINT", "http://localhost:9000")
os.environ.setdefault("S3_ACCESS_KEY", "test")
os.environ.setdefault("S3_SECRET_KEY", "test")
os.environ.setdefault("CORS_ORIGINS", '["http://localhost:3000"]')

# Phase F: security settings for tests
os.environ.setdefault(
    "ENCRYPTION_KEY",
    "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",  # base64(32 bytes)
)
os.environ.setdefault(
    "CSRF_SECRET",
    "test-csrf-secret-must-be-at-least-32-characters-long",
)
os.environ.setdefault("DPDP_GRIEVANCE_OFFICER_EMAIL", "test-grievance@krishisetu.in")

from krishisetu.core.database import Base, get_db  # noqa: E402
from krishisetu.core.redis import get_redis  # noqa: E402
from krishisetu.main import app  # noqa: E402

# Use the same database URL as the app
TEST_DATABASE_URL = os.environ["DATABASE_URL"]

# Create a separate engine for tests with NullPool for isolation
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(
    bind=test_engine, class_=AsyncSession, expire_on_commit=False
)


# ---------------------------------------------------------------------------
# Event loop
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def event_loop():
    """Create a single event loop for the entire test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async DB session with rollback isolation.

    Each test gets its own transaction, which is rolled back at the end.
    This ensures tests don't pollute each other's state.
    """
    async with test_engine.connect() as conn:
        await conn.begin()
        # Bind session to the connection's transaction
        session = AsyncSession(bind=conn, expire_on_commit=False)

        # Override the get_db dependency to use this session
        async def override_get_db():
            try:
                yield session
            finally:
                await session.close()

        app.dependency_overrides[get_db] = override_get_db

        try:
            yield session
        finally:
            await session.close()
            await conn.rollback()
            app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# HTTP client fixture
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client wired to the FastAPI app via ASGI transport."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Redis mock fixture
# ---------------------------------------------------------------------------


class RedisMock:
    """In-memory async Redis mock for unit tests.

    Implements only the subset of Redis commands used by the auth service:
    get, set (with ex), delete, exists, incr, expire, ttl, pipeline.
    """

    def __init__(self) -> None:
        self._store: dict[str, tuple[str, float | None]] = {}
        self._pipelined: list[tuple[str, tuple[Any, ...]]] = []

    async def get(self, key: str) -> str | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expiry = entry
        if expiry is not None and asyncio.get_event_loop().time() > expiry:
            del self._store[key]
            return None
        return value

    async def set(self, key: str, value: str, ex: int | None = None) -> str:
        expiry = (
            asyncio.get_event_loop().time() + ex if ex is not None else None
        )
        self._store[key] = (value, expiry)
        return "OK"

    async def delete(self, *keys: str) -> int:
        count = 0
        for key in keys:
            if key in self._store:
                del self._store[key]
                count += 1
        return count

    async def exists(self, key: str) -> bool:
        val = await self.get(key)
        return val is not None

    async def incr(self, key: str) -> int:
        val = await self.get(key)
        new_val = int(val) + 1 if val else 1
        self._store[key] = (str(new_val), self._store.get(key, (None, None))[1])
        return new_val

    async def expire(self, key: str, ttl: int) -> bool:
        if key not in self._store:
            return False
        value, _ = self._store[key]
        self._store[key] = (value, asyncio.get_event_loop().time() + ttl)
        return True

    async def ttl(self, key: str) -> int:
        entry = self._store.get(key)
        if entry is None:
            return -2
        _, expiry = entry
        if expiry is None:
            return -1
        remaining = int(expiry - asyncio.get_event_loop().time())
        return max(0, remaining)

    def pipeline(self):
        return self

    def execute(self):
        # Simplistic: execute commands sequentially
        return asyncio.gather(*[
            self._execute_one(cmd, args) for cmd, args in self._pipelined
        ])

    async def _execute_one(self, cmd: str, args: tuple) -> Any:
        method = getattr(self, cmd)
        return await method(*args)

    # Pipeline-specific methods that queue commands
    def set(self, key, value, ex=None):  # type: ignore[no-redef]
        # When called in pipeline context, return self for chaining
        # (This is a simplification — real pipeline queues commands)
        self._store[key] = (value, asyncio.get_event_loop().time() + ex if ex else None)
        return self

    def incr(self, key):  # type: ignore[no-redef]
        val = self._store.get(key)
        new_val = int(val[0]) + 1 if val else 1
        self._store[key] = (str(new_val), val[1] if val else None)
        return self

    def expire(self, key, ttl):  # type: ignore[no-redef]
        if key in self._store:
            value, _ = self._store[key]
            self._store[key] = (value, asyncio.get_event_loop().time() + ttl)
        return self

    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        pass


@pytest_asyncio.fixture
async def redis_mock(monkeypatch):
    """Replace the Redis client with an in-memory mock."""
    mock = RedisMock()

    async def override_get_redis():
        return mock

    # Patch the get_redis function used throughout the app
    import krishisetu.core.redis as redis_module

    monkeypatch.setattr(redis_module, "get_redis", override_get_redis)
    # Also patch the import in services
    import krishisetu.domains.identity.services as services_module

    monkeypatch.setattr(services_module, "get_redis", override_get_redis)

    app.dependency_overrides[get_redis] = override_get_redis

    yield mock

    app.dependency_overrides.pop(get_redis, None)


# ---------------------------------------------------------------------------
# SMS mock fixture
# ---------------------------------------------------------------------------


class SMSMock:
    """Mock SMS backend that captures OTPs without sending."""

    def __init__(self) -> None:
        self.sent_otps: list[tuple[str, str, str]] = []  # (phone, otp, purpose)

    async def send_otp(self, phone: str, otp: str, purpose: str = "login") -> bool:
        self.sent_otps.append((phone, otp, purpose))
        return True

    async def send_sms(self, phone: str, message: str) -> bool:
        return True

    def last_otp(self, phone: str, purpose: str | None = None) -> str | None:
        """Get the most recent OTP sent to a phone (optionally for a purpose)."""
        for p, otp, pur in reversed(self.sent_otps):
            if p == phone and (purpose is None or pur == purpose):
                return otp
        return None


@pytest_asyncio.fixture
async def sms_mock(monkeypatch):
    """Replace the SMS backend with a mock that captures OTPs."""
    mock = SMSMock()

    def override_get_sms_backend():
        return mock

    import krishisetu.core.sms as sms_module
    import krishisetu.domains.identity.services as services_module

    monkeypatch.setattr(sms_module, "get_sms_backend", override_get_sms_backend)
    monkeypatch.setattr(services_module, "get_sms_backend", override_get_sms_backend)

    return mock


# ---------------------------------------------------------------------------
# Helper: create a test user directly in the database
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession):
    """Create a test user in the database and return the user object."""
    from krishisetu.domains.identity import repository as repo
    from krishisetu.domains.identity.models import UserRole

    user = await repo.create_user(
        db_session,
        phone="9876543210",
        full_name="Test Farmer",
        role=UserRole.FARMER,
        preferred_language="en",
    )
    await db_session.flush()
    return user


# ---------------------------------------------------------------------------
# Helper: get auth token for a test user
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def auth_headers(test_user) -> dict[str, str]:
    """Return Authorization headers with a valid JWT for the test user."""
    from krishisetu.core.security import create_access_token

    token = create_access_token(
        user_id=test_user.id,
        role=test_user.role.value,
        extra_claims={"name": test_user.full_name},
    )
    return {"Authorization": f"Bearer {token}"}
