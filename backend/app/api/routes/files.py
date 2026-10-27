"""Signed file delivery for the local storage backend.

In production with S3 (Supabase Storage) this route is unused: the client gets a
presigned S3 URL instead. It exists so development is a complete, working flow
rather than a thing you have to mock.
"""

from __future__ import annotations

from fastapi import APIRouter, Response

from app.core.config import settings
from app.core.errors import Forbidden, NotFound
from app.services.storage import StorageError, get_storage, verify_signed_url

router = APIRouter(tags=["files"])

_MEDIA_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
}


@router.get("/files/{key:path}")
async def read_file(key: str, exp: int, sig: str) -> Response:
    if not verify_signed_url(key, exp, sig):
        raise Forbidden("That link has expired.")

    try:
        content = await get_storage().read(key)
    except StorageError as exc:
        raise NotFound("That file is no longer available.") from exc

    extension = key.rsplit(".", 1)[-1].lower()
    return Response(
        content=content,
        media_type=_MEDIA_TYPES.get(extension, "application/octet-stream"),
        headers={
            "Cache-Control": f"private, max-age={settings.signed_url_ttl_seconds}",
            "Content-Disposition": "inline",
        },
    )
