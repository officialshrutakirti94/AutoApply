"""Users, dashboard sessions, extension tokens and pairing.

Two credentials exist and they are deliberately not interchangeable:

* ``aa_session`` (httpOnly cookie) — minted after Google sign-in, dashboard scope.
* ``aa_ext_...`` (bearer)         — minted by redeeming a pairing code, extension scope.

Both are stored as SHA-256 digests. Neither can read anything outside its scope:
the extension token cannot touch profile or preferences, and a cookie request is
never treated as an extension request.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from app.core.config import settings
from app.core.errors import InvalidCredentials
from app.core.security import (
    EXTENSION_TOKEN_PREFIX,
    hash_pairing_code,
    hash_secret,
    new_extension_token,
    new_pairing_code,
    new_session_token,
)
from app.core.timeutils import ensure_utc, utcnow
from app.db.models import ExtensionPairingCode, ExtensionToken, User, UserSession

SESSION_COOKIE = "aa_session"
CSRF_HEADER = "x-requested-with"
CSRF_VALUE = "XMLHttpRequest"
PAIRING_TTL_MINUTES = 10
_TOUCH_INTERVAL = timedelta(seconds=60)


@dataclass(frozen=True, slots=True)
class ExtensionPrincipal:
    user_id: uuid.UUID
    token_id: uuid.UUID
    scope: str
    install_id: str | None


# --------------------------------------------------------------------------- users


async def upsert_user(
    db: AsyncSession,
    *,
    google_sub: str,
    email: str,
    email_verified: bool,
    name: str | None,
    avatar_url: str | None,
) -> User:
    """Find or create the user for a verified Google identity.

    Matched on ``google_sub`` first, then on email so an account created before a
    Google subject claim existed still resolves to the same person.
    """
    now = utcnow()
    user = (
        await db.execute(select(User).where(User.google_sub == google_sub))
    ).scalar_one_or_none()

    if user is None:
        user = (
            await db.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if user is not None:
            user.google_sub = google_sub

    if user is None:
        user = User(
            google_sub=google_sub,
            email=email,
            email_verified=email_verified,
            name=name,
            avatar_url=avatar_url,
            last_login_at=now,
        )
        db.add(user)
    else:
        user.email = email
        user.email_verified = email_verified
        user.name = name or user.name
        user.avatar_url = avatar_url or user.avatar_url
        user.last_login_at = now

    await db.commit()
    await db.refresh(user)
    return user


async def get_user(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await db.get(User, user_id)


# ------------------------------------------------------------------------ sessions


async def create_session(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    user_agent: str | None,
    ip: str | None,
) -> str:
    raw = new_session_token()
    now = utcnow()
    db.add(
        UserSession(
            user_id=user_id,
            token_hash=hash_secret(raw),
            user_agent=(user_agent or "")[:400] or None,
            ip_hash=hash_secret(ip) if ip else None,
            last_seen_at=now,
            expires_at=now + timedelta(days=settings.session_ttl_days),
        )
    )
    await db.commit()
    return raw


async def user_for_session(db: AsyncSession, raw_token: str | None) -> User | None:
    if not raw_token:
        return None

    session = (
        await db.execute(select(UserSession).where(UserSession.token_hash == hash_secret(raw_token)))
    ).scalar_one_or_none()

    if session is None or session.revoked_at is not None:
        return None
    if ensure_utc(session.expires_at) <= utcnow():
        return None

    now = utcnow()
    if ensure_utc(session.last_seen_at) < now - _TOUCH_INTERVAL:
        session.last_seen_at = now
        await db.commit()

    return await db.get(User, session.user_id)


async def revoke_session(db: AsyncSession, raw_token: str | None) -> None:
    if not raw_token:
        return
    await db.execute(
        update(UserSession)
        .where(UserSession.token_hash == hash_secret(raw_token), UserSession.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    await db.commit()


def set_session_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=raw_token,
        max_age=settings.session_ttl_days * 24 * 3600,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE,
        path="/",
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
    )


# --------------------------------------------------------------- extension tokens


async def issue_pairing_code(db: AsyncSession, *, user_id: uuid.UUID) -> tuple[str, datetime]:
    now = utcnow()
    # Only the newest code should be usable; older unused ones are burned.
    await db.execute(
        update(ExtensionPairingCode)
        .where(
            ExtensionPairingCode.user_id == user_id,
            ExtensionPairingCode.used_at.is_(None),
        )
        .values(used_at=now)
    )

    expires_at = now + timedelta(minutes=PAIRING_TTL_MINUTES)
    for _ in range(5):
        raw = new_pairing_code()
        db.add(
            ExtensionPairingCode(
                user_id=user_id, code_hash=hash_pairing_code(raw), expires_at=expires_at
            )
        )
        try:
            await db.commit()
            return raw, expires_at
        except IntegrityError:
            await db.rollback()
            continue

    raise RuntimeError("Could not allocate a unique pairing code")


async def redeem_pairing_code(
    db: AsyncSession,
    *,
    code: str,
    install_id: str | None,
    label: str | None,
) -> tuple[User, str]:
    record = (
        await db.execute(
            select(ExtensionPairingCode).where(
                ExtensionPairingCode.code_hash == hash_pairing_code(code)
            )
        )
    ).scalar_one_or_none()

    invalid = InvalidCredentials("That pairing code is wrong or has expired. Generate a new one.")
    if record is None or record.used_at is not None:
        raise invalid
    if ensure_utc(record.expires_at) <= utcnow():
        raise invalid

    user = await db.get(User, record.user_id)
    if user is None:
        raise invalid

    record.used_at = utcnow()

    # Re-pairing the same install should replace its token, not stack a second one.
    if install_id:
        await db.execute(
            update(ExtensionToken)
            .where(
                ExtensionToken.user_id == user.id,
                ExtensionToken.install_id == install_id,
                ExtensionToken.revoked_at.is_(None),
            )
            .values(revoked_at=utcnow())
        )

    raw = new_extension_token()
    db.add(
        ExtensionToken(
            user_id=user.id,
            token_hash=hash_secret(raw),
            scope="extension",
            install_id=install_id,
            label=(label or "")[:120] or None,
        )
    )
    await db.commit()
    return user, raw


async def principal_for_extension_token(
    db: AsyncSession, raw_token: str | None
) -> ExtensionPrincipal | None:
    if not raw_token or not raw_token.startswith(EXTENSION_TOKEN_PREFIX):
        return None

    token = (
        await db.execute(select(ExtensionToken).where(ExtensionToken.token_hash == hash_secret(raw_token)))
    ).scalar_one_or_none()

    if token is None or token.revoked_at is not None or token.scope != "extension":
        return None

    now = utcnow()
    if ensure_utc(token.last_used_at) is None or ensure_utc(token.last_used_at) < now - _TOUCH_INTERVAL:
        token.last_used_at = now
        await db.commit()

    return ExtensionPrincipal(
        user_id=token.user_id,
        token_id=token.id,
        scope=token.scope,
        install_id=token.install_id,
    )


async def list_extension_tokens(db: AsyncSession, *, user_id: uuid.UUID) -> list[ExtensionToken]:
    rows = await db.execute(
        select(ExtensionToken)
        .where(ExtensionToken.user_id == user_id)
        .order_by(ExtensionToken.created_at.desc())
    )
    return list(rows.scalars())


async def revoke_extension_token(
    db: AsyncSession, *, user_id: uuid.UUID, token_id: uuid.UUID
) -> bool:
    token = (
        await db.execute(
            select(ExtensionToken).where(
                ExtensionToken.id == token_id, ExtensionToken.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if token is None:
        return False
    if token.revoked_at is None:
        token.revoked_at = utcnow()
        await db.commit()
    return True
