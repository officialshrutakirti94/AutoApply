"""Google-only authentication.

There is no register, no password and no reset flow. One credential in, one
session cookie out.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from app.api.presenters import build_me
from app.api.schemas import DevSignInRequest, GoogleSignInRequest, MeOut
from app.api.utils import client_ip
from app.core.config import settings
from app.core.deps import CurrentUser, DbSession
from app.core.errors import NotFound
from app.core.ratelimit import check_rate_limit
from app.services.auth import (
    SESSION_COOKIE,
    clear_session_cookie,
    create_session,
    revoke_session,
    set_session_cookie,
    upsert_user,
)
from app.services.google import verify_google_id_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/google", response_model=MeOut)
async def sign_in_with_google(
    payload: GoogleSignInRequest,
    request: Request,
    response: Response,
    db: DbSession,
) -> MeOut:
    await check_rate_limit(request, bucket="auth", limit=20, window_seconds=60)

    identity = await verify_google_id_token(payload.credential)
    user = await upsert_user(
        db,
        google_sub=identity.subject,
        email=identity.email,
        email_verified=identity.email_verified,
        name=identity.name,
        avatar_url=identity.picture,
    )

    raw_token = await create_session(
        db,
        user_id=user.id,
        user_agent=request.headers.get("user-agent"),
        ip=client_ip(request),
    )
    set_session_cookie(response, raw_token)
    return await build_me(db, user)


@router.post("/dev-login", response_model=MeOut)
async def dev_login(
    payload: DevSignInRequest,
    request: Request,
    response: Response,
    db: DbSession,
) -> MeOut:
    """Local development only. Hidden and disabled outside development."""
    if settings.is_production or not settings.auth_dev_bypass:
        raise NotFound("Not found.")

    await check_rate_limit(request, bucket="dev-auth", limit=30, window_seconds=60)

    email = (payload.email or settings.auth_dev_bypass_email).strip().lower()
    user = await upsert_user(
        db,
        google_sub=f"dev:{email}",
        email=email,
        email_verified=True,
        name=email.split("@")[0].replace(".", " ").title(),
        avatar_url=None,
    )
    raw_token = await create_session(
        db,
        user_id=user.id,
        user_agent=request.headers.get("user-agent"),
        ip=client_ip(request),
    )
    set_session_cookie(response, raw_token)
    return await build_me(db, user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response, db: DbSession) -> Response:
    await revoke_session(db, request.cookies.get(SESSION_COOKIE))
    clear_session_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=MeOut)
async def me(user: CurrentUser, db: DbSession) -> MeOut:
    return await build_me(db, user)
