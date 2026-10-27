"""Stuck-step screenshots.

Captured by the extension only when a job needs a human, cropped to the apply
dialog where possible, then auto-deleted after ``SCREENSHOT_RETENTION_DAYS`` by the
sweeper. Validation happens here so the endpoint stays thin.
"""

from __future__ import annotations

import uuid

from app.core.errors import PayloadTooLarge, UnsupportedMedia
from app.services.storage import get_storage

MAX_SCREENSHOT_BYTES = 2 * 1024 * 1024

_MAGIC = {
    "image/png": b"\x89PNG\r\n\x1a\n",
    "image/jpeg": b"\xff\xd8\xff",
    "image/webp": b"RIFF",
}


def validate_screenshot(content: bytes, content_type: str | None) -> str:
    normalised = (content_type or "").split(";")[0].strip().lower()
    if normalised not in _MAGIC:
        raise UnsupportedMedia("Screenshots must be PNG, JPEG or WebP.")
    if len(content) == 0:
        raise UnsupportedMedia("That screenshot was empty.")
    if len(content) > MAX_SCREENSHOT_BYTES:
        raise PayloadTooLarge("That screenshot is too large (2 MB limit).")
    if not content.startswith(_MAGIC[normalised]):
        raise UnsupportedMedia("That file does not look like an image.")
    return normalised


def screenshot_key(*, user_id: uuid.UUID, application_id: uuid.UUID, extension: str) -> str:
    return f"screenshots/{user_id}/{application_id}/{uuid.uuid4().hex}.{extension}"


async def store_screenshot(
    *,
    user_id: uuid.UUID,
    application_id: uuid.UUID,
    content: bytes,
    content_type: str | None,
) -> str:
    normalised = validate_screenshot(content, content_type)
    extension = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}[normalised]
    key = screenshot_key(user_id=user_id, application_id=application_id, extension=extension)
    await get_storage().put(key, content, normalised)
    return key
