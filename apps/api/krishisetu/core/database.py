"""Async SQLAlchemy database engine and session factory.

Configuration:
- Async engine with asyncpg driver
- Connection pool tuned for production (configurable via env vars)
- Session-per-request via FastAPI dependency injection
- Read replica routing (Phase 2)
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from krishisetu.core.config import settings


class Base(DeclarativeBase):
    """Declarative base for all SQLAlchemy models."""

    pass


def _create_engine() -> AsyncEngine:
    """Create the async SQLAlchemy engine with pool tuning."""
    return create_async_engine(
        str(settings().DATABASE_URL),
        pool_size=settings().DB_POOL_SIZE,
        max_overflow=settings().DB_MAX_OVERFLOW,
        pool_timeout=settings().DB_POOL_TIMEOUT,
        pool_recycle=settings().DB_POOL_RECYCLE,
        pool_pre_ping=True,  # Verify connection is alive before checkout
        echo=settings().DEBUG,  # Log SQL in dev
    )


engine: AsyncEngine = _create_engine()

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async database session.

    Commits on successful handler completion, rolls back on exception.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def check_db_connection() -> bool:
    """Health check: verify database is reachable."""
    try:
        from sqlalchemy import text

        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            return result.scalar() == 1
    except Exception:
        return False
