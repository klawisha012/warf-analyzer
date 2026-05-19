"""SQLAlchemy 2.0 async engine + session factory + FastAPI dependency."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    future=True,
)

async_session: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding an async session per request."""
    async with async_session() as session:
        yield session
