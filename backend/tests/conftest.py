"""Test harness.

Runs the real app against an in-memory SQLite database. Production is Postgres,
but no query in the codebase uses Postgres-only operators (see ``app/db/types.py``),
so the ORM paths under test are the same ones that run in production.

Environment is set before importing anything from ``app`` because settings are
resolved at import time.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

os.environ["APP_ENV"] = "test"
os.environ["SECRET_KEY"] = "test-secret-key-long-enough-to-be-realistic-123456"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite://"
os.environ["AUTH_DEV_BYPASS"] = "true"
os.environ["LLM_ENABLED"] = "false"
os.environ["STORAGE_BACKEND"] = "local"
os.environ["STORAGE_LOCAL_DIR"] = tempfile.mkdtemp(prefix="autoapply-test-")
os.environ["SAFETY_REST_DAY"] = "7"  # 7 is never a weekday, so rest day never triggers
os.environ["SAFETY_WARMUP_DAYS"] = "0"
os.environ["CRON_SECRET"] = "test-cron-secret"
os.environ["LOG_LEVEL"] = "WARNING"

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import event  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402

CSRF_HEADERS = {"X-Requested-With": "XMLHttpRequest"}


@pytest_asyncio.fixture(autouse=True)
async def _reset_rate_limiter():
    """The limiter is process-wide by design; tests must not share its counters."""
    from app.core.ratelimit import limiter

    await limiter.reset()
    yield
    await limiter.reset()


@pytest_asyncio.fixture
async def engine():
    test_engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(test_engine.sync_engine, "connect")
    def _foreign_keys_on(dbapi_connection, _record):  # pragma: no cover
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    yield test_engine
    await test_engine.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    return async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


@pytest_asyncio.fixture
async def db(session_factory) -> AsyncSession:
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client_factory(session_factory):
    """Create independent HTTP clients (separate cookie jars) sharing one database."""
    created: list[AsyncClient] = []

    async def _override_db():
        async with session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_db

    def make(headers: dict[str, str] | None = None) -> AsyncClient:
        http_client = AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
            headers={**CSRF_HEADERS, **(headers or {})},
        )
        created.append(http_client)
        return http_client

    yield make

    for http_client in created:
        await http_client.aclose()
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(client_factory) -> AsyncClient:
    return client_factory()


@pytest_asyncio.fixture
async def signed_in(client) -> AsyncClient:
    response = await client.post("/api/auth/dev-login", json={})
    assert response.status_code == 200, response.text
    return client


@pytest_asyncio.fixture
async def onboarded(signed_in) -> AsyncClient:
    from tests.helpers import complete_onboarding

    await complete_onboarding(signed_in)
    return signed_in


@pytest_asyncio.fixture
async def extension_token(onboarded) -> str:
    from tests.helpers import connect_extension

    return await connect_extension(onboarded)


@pytest.fixture
def storage_dir() -> Path:
    return Path(os.environ["STORAGE_LOCAL_DIR"])
