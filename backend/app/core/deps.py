"""Request dependencies: the only place a caller becomes a user.

Dashboard routes depend on :data:`CurrentUser` (cookie session + CSRF header).
Extension routes depend on :data:`ExtensionAuth` (bearer token, extension scope).
Nothing accepts a user id from the request body, which is what makes the
authorization tests meaningful.

Two things are declared as real OpenAPI parameters on purpose:

* ``X-Requested-With`` on dashboard routes, so the required CSRF header is visible
  in Swagger UI instead of producing an unexplained 403.
* the ``HTTPBearer`` scheme on extension routes, so Swagger shows an **Authorize**
  button and can call the extension API with a real token.

Both are documentation and enforcement of the same checks; behaviour is unchanged.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthRequired, Forbidden
from app.db.models import User
from app.db.session import get_db
from app.services.auth import (
    CSRF_HEADER,
    CSRF_VALUE,
    SESSION_COOKIE,
    ExtensionPrincipal,
    principal_for_extension_token,
    user_for_session,
)

DbSession = Annotated[AsyncSession, Depends(get_db)]

_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

bearer_scheme = HTTPBearer(
    scheme_name="ExtensionToken",
    description=(
        "Extension bearer token (`aa_ext_...`), minted by POST /api/extension/connect. "
        "Paste the raw token, without the word Bearer."
    ),
    auto_error=False,
)


def bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer":
        return None
    return token.strip() or None


async def optional_user(request: Request, db: DbSession) -> User | None:
    return await user_for_session(db, request.cookies.get(SESSION_COOKIE))


async def current_user(request: Request, db: DbSession) -> User:
    user = await user_for_session(db, request.cookies.get(SESSION_COOKIE))
    if user is None:
        raise AuthRequired()
    return user


async def dashboard_user(
    request: Request,
    user: Annotated[User, Depends(current_user)],
    x_requested_with: Annotated[
        str | None,
        Header(
            alias=CSRF_HEADER,
            include_in_schema=True,
            description=(
                "Required on POST/PUT/PATCH/DELETE. Send the literal value XMLHttpRequest. "
                "A cross-site form cannot set this header, which is the point."
            ),
        ),
    ] = None,
) -> User:
    """Session user plus a cheap CSRF gate.

    The session cookie is ``SameSite=Lax``, which already blocks cross-site POSTs.
    Requiring a custom header on unsafe methods closes the same-site-subdomain and
    form-post edge: a cross-origin HTML form cannot set ``X-Requested-With``.
    """
    if request.method in _UNSAFE_METHODS and x_requested_with != CSRF_VALUE:
        raise Forbidden("Missing request header.")
    return user


async def extension_principal(
    request: Request,
    db: DbSession,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ] = None,
) -> ExtensionPrincipal:
    raw = credentials.credentials if credentials else bearer_token(request)
    principal = await principal_for_extension_token(db, raw)
    if principal is None:
        raise AuthRequired("Reconnect the extension from Settings to continue.")
    return principal


CurrentUser = Annotated[User, Depends(dashboard_user)]
ExtensionAuth = Annotated[ExtensionPrincipal, Depends(extension_principal)]
