"""A throwaway database for evals that need one.

Deliberately independent of ``app.db.session``: the eval runner must not touch the
developer's ``.env`` database, and evals are read-only against their own fixtures.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base

# Import registers every model on Base.metadata.
import app.db.models  # noqa: F401


@asynccontextmanager
async def scratch_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    try:
        async with factory() as session:
            yield session
    finally:
        await engine.dispose()


def ensure_no_llm() -> None:
    """Evals must be deterministic and free: never call a provider."""
    os.environ["LLM_ENABLED"] = "false"
