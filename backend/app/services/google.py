"""Google Identity Services token verification.

The dashboard signs the user in with Google's button and receives an ID token. We
verify it here against Google's published keys. No client secret and no redirect
URI are involved, which is why the dashboard needs only a Web client ID.

One client ID is enough for the whole product: the **extension never talks to
Google**. It authenticates with an 8-character pairing code traded for a bearer
token, so adding a second OAuth client is not required. If one is ever added, put
its ID in ``GOOGLE_EXTRA_CLIENT_IDS`` and it will be accepted too.

A "Sign in with Google" ID token is a bearer assertion: it is verified against the
expected audience (our client IDs) and Google's certificates, so a token minted for
another app is rejected.
"""

from __future__ import annotations

from dataclasses import dataclass

from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.errors import InvalidCredentials
from app.core.logging import get_logger

log = get_logger("google_auth")


@dataclass(frozen=True, slots=True)
class GoogleIdentity:
    subject: str
    email: str
    email_verified: bool
    name: str | None
    picture: str | None


def _verify_sync(credential: str, audiences: list[str]) -> dict:
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token as google_id_token

    return google_id_token.verify_oauth2_token(
        credential,
        google_requests.Request(),
        # google-auth accepts a list and checks `aud` against any of them.
        audience=audiences,
    )


async def verify_google_id_token(credential: str) -> GoogleIdentity:
    audiences = settings.google_client_id_list
    if not audiences:
        raise InvalidCredentials("Google sign-in is not configured on this server.")

    try:
        claims = await run_in_threadpool(_verify_sync, credential, audiences)
    except Exception as exc:  # google-auth raises several unrelated types
        # Log the reason, not the token. The message is what tells you the audience
        # was wrong, the token expired, or the client ID does not match. Client IDs
        # are public (they ship in the dashboard bundle), so this leaks nothing.
        log.warning(
            "google_token_rejected",
            error_type=type(exc).__name__,
            error=str(exc)[:240],
            accepted_audiences=len(audiences),
        )
        raise InvalidCredentials("That Google sign-in could not be verified. Try again.") from exc

    subject = claims.get("sub")
    email = (claims.get("email") or "").strip().lower()
    if not subject or not email:
        raise InvalidCredentials("That Google account did not share an email address.")

    return GoogleIdentity(
        subject=str(subject),
        email=email,
        email_verified=bool(claims.get("email_verified", False)),
        name=(claims.get("name") or None),
        picture=(claims.get("picture") or None),
    )
