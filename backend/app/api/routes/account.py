"""Account deletion.

Deletes the user row, which cascades to profile, preferences, answers, tokens,
runs, applications and safety events. Storage objects have to be removed
explicitly because no database constraint knows about the bucket.
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status
from sqlalchemy import select

from app.core.deps import CurrentUser, DbSession
from app.core.logging import get_logger
from app.db.models import Application, Profile
from app.services.auth import clear_session_cookie
from app.services.storage import get_storage

log = get_logger("account")

router = APIRouter(tags=["account"])


@router.delete("/account", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(user: CurrentUser, db: DbSession) -> Response:
    keys: list[str] = []

    profile = await db.get(Profile, user.id)
    if profile is not None and profile.resume_file_key:
        keys.append(profile.resume_file_key)

    rows = await db.execute(
        select(Application.screenshot_key).where(
            Application.user_id == user.id, Application.screenshot_key.is_not(None)
        )
    )
    keys.extend([key for key in rows.scalars() if key])

    storage = get_storage()
    for key in keys:
        try:
            await storage.delete(key)
        except Exception:
            # A missing object must not block deletion of the account.
            log.warning("storage_delete_failed", key=key)

    await db.delete(user)
    await db.commit()

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_session_cookie(response)
    return response
