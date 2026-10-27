"""The ledger the dashboard reads, and the stuck-step evidence the extension uploads."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, File, Request, UploadFile

from app.api.presenters import application_out
from app.api.schemas import (
    ApplicationListOut,
    ApplicationOut,
    ApplicationResolveRequest,
    ScreenshotUrlOut,
)
from app.api.utils import parse_datetime_param
from app.core.config import settings
from app.core.deps import CurrentUser, DbSession, ExtensionAuth
from app.core.errors import NotFound, Unprocessable
from app.core.ratelimit import check_rate_limit
from app.db.enums import ApplicationStatus
from app.services import applications as applications_service
from app.services.screenshots import MAX_SCREENSHOT_BYTES, store_screenshot
from app.services.storage import get_storage

router = APIRouter(prefix="/applications", tags=["applications"])

_VALID_STATUSES = {status.value for status in ApplicationStatus}


@router.get("", response_model=ApplicationListOut)
async def list_applications(
    user: CurrentUser,
    db: DbSession,
    since: str | None = None,
    status: str | None = None,
    platform: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> ApplicationListOut:
    if status and status not in _VALID_STATUSES:
        raise Unprocessable("Unknown status filter.")
    if platform and platform not in {"linkedin", "naukri"}:
        raise Unprocessable("Unknown platform filter.")

    items = await applications_service.list_for_user(
        db,
        user_id=user.id,
        since=parse_datetime_param(since),
        status=status,
        platform=platform,
        limit=limit,
        offset=offset,
    )
    unresolved = await applications_service.unresolved_count(db, user_id=user.id)
    return ApplicationListOut(
        items=[application_out(item) for item in items], total_unresolved=unresolved
    )


@router.patch("/{application_id}", response_model=ApplicationOut)
async def resolve_application(
    application_id: uuid.UUID,
    payload: ApplicationResolveRequest,
    user: CurrentUser,
    db: DbSession,
) -> ApplicationOut:
    application = await applications_service.resolve(
        db,
        user_id=user.id,
        application_id=application_id,
        status=payload.status,
        reason=payload.reason,
    )
    return application_out(application)


@router.get("/{application_id}/screenshot-url", response_model=ScreenshotUrlOut)
async def screenshot_url(
    application_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> ScreenshotUrlOut:
    application = await applications_service.get(
        db, user_id=user.id, application_id=application_id
    )
    if not application.screenshot_key:
        raise NotFound("No screenshot for this item.")

    url = await get_storage().signed_url(
        application.screenshot_key, settings.signed_url_ttl_seconds
    )
    return ScreenshotUrlOut(url=url, expires_in=settings.signed_url_ttl_seconds)


@router.post("/{application_id}/screenshot", status_code=204)
async def upload_screenshot(
    application_id: uuid.UUID,
    request: Request,
    principal: ExtensionAuth,
    db: DbSession,
    file: UploadFile = File(...),
) -> None:
    await check_rate_limit(request, bucket="screenshot", window_seconds=60, limit=30)

    # Scope the lookup by the token's user before touching bytes.
    application = await applications_service.get(
        db, user_id=principal.user_id, application_id=application_id
    )
    content = await file.read(MAX_SCREENSHOT_BYTES + 1)
    key = await store_screenshot(
        user_id=principal.user_id,
        application_id=application.id,
        content=content,
        content_type=file.content_type,
    )

    previous = application.screenshot_key
    await applications_service.attach_screenshot(
        db, user_id=principal.user_id, application_id=application.id, key=key
    )
    if previous and previous != key:
        try:
            await get_storage().delete(previous)
        except Exception:
            pass
