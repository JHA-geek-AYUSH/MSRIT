from __future__ import annotations

from typing import AsyncGenerator, Optional
from contextvars import ContextVar

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import text

from app.core.config import get_settings

# Context variable to store current user ID for RLS
current_user_id: ContextVar[Optional[str]] = ContextVar('current_user_id', default=None)


def _normalize_url(url: str) -> str:
    """
    Normalise the DB URL to use asyncpg driver.
    asyncpg works on Windows with both Proactor and Selector event loops.
    """
    # Already asyncpg
    if "asyncpg" in url:
        return url
    # psycopg async variants → asyncpg
    for prefix in ("postgresql+psycopg://", "postgresql+asyncpg://"):
        if url.startswith(prefix):
            return url.replace(prefix, "postgresql+asyncpg://", 1)
    # bare postgresql://
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


_settings = get_settings()

# Use local SQLite for development if DATABASE_URL is not set or is unreachable
if not _settings.DATABASE_URL or _settings.DATABASE_URL.startswith("sqlite"):
    ASYNC_DATABASE_URL = "sqlite+aiosqlite:///./gemmaFin.db"
else:
    ASYNC_DATABASE_URL = _normalize_url(_settings.DATABASE_URL)

engine = create_async_engine(
    ASYNC_DATABASE_URL, 
    pool_pre_ping=True, 
    echo=False,
    connect_args={"timeout": 15} if "sqlite" in ASYNC_DATABASE_URL else {}
)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        # Set user context for RLS if available (PostgreSQL only, silently ignored on SQLite)
        user_id = current_user_id.get()
        if user_id:
            try:
                # Only attempt RLS for PostgreSQL
                if "postgresql" in ASYNC_DATABASE_URL or "asyncpg" in ASYNC_DATABASE_URL:
                    await session.execute(
                        text("SELECT set_config('app.current_user_id', :user_id, true)"), 
                        {"user_id": user_id}
                    )
            except Exception:
                pass
        yield session


def set_current_user(user_id: str) -> None:
    """Set current user ID for RLS context"""
    current_user_id.set(user_id)


def get_current_user() -> Optional[str]:
    """Get current user ID from context"""
    return current_user_id.get()


async def get_db_with_user(user_id: str) -> AsyncGenerator[AsyncSession, None]:
    """Get database session with specific user context for RLS (PostgreSQL only)"""
    async with SessionLocal() as session:
        try:
            if "postgresql" in ASYNC_DATABASE_URL or "asyncpg" in ASYNC_DATABASE_URL:
                await session.execute(
                    text("SELECT set_config('app.current_user_id', :user_id, true)"), 
                    {"user_id": user_id}
                )
        except Exception:
            pass
        yield session


