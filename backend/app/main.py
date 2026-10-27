"""Application factory and process lifecycle."""

from __future__ import annotations

import asyncio
import os
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app import __version__
from app.agents.llm import provider_status
from app.api.routes import (
    account,
    agent,
    applications,
    auth,
    extension,
    files,
    internal,
    plan,
    profile,
    qa,
    resume,
    runs,
    safety,
)
from app.api.schemas import HealthOut
from app.core.config import settings
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging, get_logger
from app.db.session import dispose_engine, get_session_factory, init_models
from app.safety.sweeper import maintenance_loop

log = get_logger("app")


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging(settings.log_level, json_output=settings.is_production)

    if settings.langsmith_tracing and settings.langsmith_api_key:
        os.environ.setdefault("LANGSMITH_TRACING", "true")
        os.environ.setdefault("LANGSMITH_API_KEY", settings.langsmith_api_key)
        os.environ.setdefault("LANGSMITH_PROJECT", settings.langsmith_project)

    if settings.auto_create_schema:
        await init_models()
        log.info("schema_ready", mode="create_all", env=settings.app_env)
    else:
        log.info("schema_ready", mode="alembic", env=settings.app_env)

    maintenance = asyncio.create_task(maintenance_loop())
    log.info("startup", version=__version__, env=settings.app_env, llm=provider_status()["enabled"])

    try:
        yield
    finally:
        maintenance.cancel()
        await asyncio.gather(maintenance, return_exceptions=True)
        await dispose_engine()
        log.info("shutdown")


def create_app() -> FastAPI:
    configure_logging(settings.log_level, json_output=settings.is_production)

    app = FastAPI(
        title=f"{settings.app_name} API",
        description="Resume-first job application agent. Decisions only: the extension owns the page.",
        version=__version__,
        lifespan=lifespan,
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/openapi.json",
    )

    install_error_handlers(app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        # Chrome extension ids use the letters a-p.
        allow_origin_regex=r"^chrome-extension://[a-p]{32}$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Retry-After", "X-Request-ID"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    prefix = settings.api_prefix
    for module in (
        auth,
        profile,
        resume,
        qa,
        extension,
        runs,
        agent,
        applications,
        safety,
        account,
        internal,
        plan,
        files,
    ):
        app.include_router(module.router, prefix=prefix)

    @app.get("/health", response_model=HealthOut, tags=["meta"])
    async def health() -> HealthOut:
        database = "ok"
        try:
            async with get_session_factory()() as session:
                await session.execute(text("SELECT 1"))
        except Exception:
            database = "error"

        return HealthOut(
            status="ok" if database == "ok" else "degraded",
            database=database,
            version=__version__,
            env=settings.app_env,
            llm=provider_status(),
        )

    @app.get("/", include_in_schema=False)
    async def root() -> dict:
        return {"name": settings.app_name, "version": __version__, "api": prefix}

    return app


app = create_app()
