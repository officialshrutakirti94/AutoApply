"""Extension pairing, token management and platform state.

Two audiences share this prefix:

* dashboard routes (cookie + CSRF) mint pairing codes and revoke installs
* extension routes (bearer token) report platform state and fetch the resume file
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request, Response, status

from app.api.schemas import (
    ExtensionConnectOut,
    ExtensionConnectRequest,
    ExtensionTokenOut,
    PairCodeOut,
    PlatformStatusRequest,
    ResumeFileOut,
)
from app.api.presenters import token_out
from app.core.config import settings
from app.core.deps import CurrentUser, DbSession, ExtensionAuth
from app.core.errors import NotFound
from app.core.ratelimit import check_rate_limit
from app.core.timeutils import ensure_utc, utcnow
from app.db.models import PlatformConnection, Profile
from app.services import runs as runs_service
from app.services.auth import (
    PAIRING_TTL_MINUTES,
    issue_pairing_code,
    list_extension_tokens,
    redeem_pairing_code,
    revoke_extension_token,
)
from app.services.storage import get_storage

router = APIRouter(tags=["extension"])


@router.post("/extension/pair", response_model=PairCodeOut)
async def create_pairing_code(request: Request, user: CurrentUser, db: DbSession) -> PairCodeOut:
    await check_rate_limit(request, bucket="pair", window_seconds=60, limit=10)
    code, expires_at = await issue_pairing_code(db, user_id=user.id)
    return PairCodeOut(
        code=code,
        expires_at=expires_at,
        instructions=(
            f"Open the extension, paste this code and press Connect. "
            f"It works once and expires in {PAIRING_TTL_MINUTES} minutes."
        ),
    )


@router.post("/extension/connect", response_model=ExtensionConnectOut)
async def connect_extension(
    payload: ExtensionConnectRequest, request: Request, db: DbSession
) -> ExtensionConnectOut:
    """Public endpoint: the pairing code *is* the credential."""
    await check_rate_limit(request, bucket="extension-connect", window_seconds=300, limit=10)

    user, token = await redeem_pairing_code(
        db, code=payload.code, install_id=payload.install_id, label=payload.label
    )
    return ExtensionConnectOut(token=token, user_email=user.email, user_name=user.name)


@router.get("/extension/tokens", response_model=list[ExtensionTokenOut])
async def list_tokens(user: CurrentUser, db: DbSession) -> list[ExtensionTokenOut]:
    tokens = await list_extension_tokens(db, user_id=user.id)
    return [token_out(token) for token in tokens]


@router.delete("/extension/tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_extension(
    token_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> Response:
    revoked = await revoke_extension_token(db, user_id=user.id, token_id=token_id)
    if not revoked:
        raise NotFound("That extension is no longer connected.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/platform/status", status_code=status.HTTP_204_NO_CONTENT)
async def report_platform_status(
    payload: PlatformStatusRequest, principal: ExtensionAuth, db: DbSession
) -> Response:
    connection = await db.get(PlatformConnection, (principal.user_id, payload.platform))
    now = utcnow()
    if connection is None:
        connection = PlatformConnection(
            user_id=principal.user_id,
            platform=payload.platform,
            signed_in=payload.signed_in,
            last_seen_at=now,
        )
        db.add(connection)
    else:
        connection.signed_in = payload.signed_in
        connection.last_seen_at = now
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/extension/resume-file", response_model=ResumeFileOut)
async def resume_file_for_extension(principal: ExtensionAuth, db: DbSession) -> ResumeFileOut:
    """Only works during an active run: that is the one time the token touches the resume."""
    run = await runs_service.active_run(db, user_id=principal.user_id)
    if run is None:
        raise NotFound("No active run.")

    heartbeat = ensure_utc(run.last_heartbeat_at)
    if heartbeat is None or (utcnow() - heartbeat).total_seconds() > settings.safety_heartbeat_timeout_seconds:
        raise NotFound("No active run.")

    profile = await db.get(Profile, principal.user_id)
    if profile is None or not profile.resume_file_key:
        raise NotFound("No resume on file.")

    url = await get_storage().signed_url(
        profile.resume_file_key, settings.signed_url_ttl_seconds
    )
    return ResumeFileOut(url=url, expires_in=settings.signed_url_ttl_seconds)
