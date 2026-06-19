"""Async SQLAlchemy engine, session factory, and declarative base.

Import the items you need::

    from backend.db.connection import engine, AsyncSessionLocal, Base, get_db

``get_db`` is a FastAPI dependency that yields an ``AsyncSession`` and handles
commit / rollback automatically.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from backend.core.config import settings

engine = create_async_engine(
    settings.database_url,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    echo=False,
)

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models in the backend."""


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yield a managed async database session.

    Commits automatically on success and rolls back on any exception.

    Yields:
        An open ``AsyncSession`` bound to the shared connection pool.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
