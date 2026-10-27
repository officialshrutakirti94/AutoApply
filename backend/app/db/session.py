"""Async engine and session factory.

One engine per process, created lazily so importing the app never opens sockets
(which keeps tests and Alembic imports cheap).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.db.base import Base

# Importing the package registers every model on Base.metadata.
from app.db import models as _models  # noqa: F401

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _build_engine() -> AsyncEngine:
    url = settings.effective_database_url
    options: dict = {"echo": settings.db_echo, "pool_pre_ping": True}
    is_sqlite = url.startswith("sqlite")

    if is_sqlite:
        if ":memory:" not in url:
            raw_path = url.split("///", 1)[-1]
            if raw_path:
                Path(raw_path).parent.mkdir(parents=True, exist_ok=True)
        options["connect_args"] = {"timeout": 30}
    else:
        options["pool_size"] = settings.db_pool_size
        options["max_overflow"] = settings.db_pool_size
        # Neon closes idle connections; recycle before that happens.
        options["pool_recycle"] = 1800

    engine = create_async_engine(url, **options)

    if is_sqlite:
        # ON DELETE CASCADE is off by default in SQLite; production Postgres has it
        # always on, and the account-deletion path relies on it.
        @event.listens_for(engine.sync_engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection, _record):  # pragma: no cover
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = _build_engine()
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(), expire_on_commit=False, autoflush=False
        )
    return _session_factory


async def get_db() -> AsyncIterator[AsyncSession]:
    async with get_session_factory()() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def init_models() -> None:
    """Create tables from metadata. Development and tests only."""
    async with get_engine().begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def dispose_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
