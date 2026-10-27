"""Private file storage.

Resumes and stuck-step screenshots live in a private bucket and are only ever
reachable through a short-lived signed URL. Local disk is the development
implementation; in production we use an S3-compatible bucket (Supabase Storage in
v1, since it needs no credit card unlike Cloudflare R2). Both satisfy the same
protocol, so callers never branch on the backend.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import sign_payload
from app.core.timeutils import utcnow

log = get_logger("storage")


class StorageError(RuntimeError):
    pass


class Storage(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> None: ...
    async def delete(self, key: str) -> None: ...
    async def read(self, key: str) -> bytes: ...
    async def signed_url(self, key: str, ttl_seconds: int | None = None) -> str: ...


def _safe_relative(key: str) -> Path:
    candidate = Path(key.replace("\\", "/"))
    if candidate.is_absolute() or ".." in candidate.parts:
        raise StorageError("Invalid storage key")
    return candidate


class LocalStorage:
    """Files under ``STORAGE_LOCAL_DIR``, served through this API on a signed URL."""

    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.root / _safe_relative(key)).resolve()
        if not str(path).startswith(str(self.root)):
            raise StorageError("Invalid storage key")
        return path

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)

    async def delete(self, key: str) -> None:
        path = self._path(key)
        await asyncio.to_thread(path.unlink, True)

    async def read(self, key: str) -> bytes:
        path = self._path(key)
        if not await asyncio.to_thread(path.exists):
            raise StorageError("Not found")
        return await asyncio.to_thread(path.read_bytes)

    async def signed_url(self, key: str, ttl_seconds: int | None = None) -> str:
        ttl = ttl_seconds or settings.signed_url_ttl_seconds
        expires = int(utcnow().timestamp()) + ttl
        signature = sign_payload(f"{key}:{expires}")
        base = f"{settings.backend_base_url}{settings.api_prefix}/files/{quote(key, safe='/')}"
        return f"{base}?exp={expires}&sig={signature}"


def _error_code(exc: Exception) -> str:
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        return str(response.get("Error", {}).get("Code") or "")
    return ""


def _describe(operation: str, exc: Exception) -> str:
    """StorageError messages end up in logs, so name the operation and the cause."""
    if isinstance(exc, StorageError):
        return str(exc)
    return f"{operation} failed ({_error_code(exc) or type(exc).__name__})"


class S3Storage:
    """Any S3-compatible bucket. v1 targets Supabase Storage.

    Supabase's S3 endpoint needs three things that boto3 does not do by default,
    and getting any of them wrong produces a signature error with a message that
    does not say what is actually wrong:

    * ``signature_version="s3v4"`` - Supabase rejects older signing.
    * **path-style** addressing (``/storage/v1/s3/<bucket>/<key>``). Virtual-hosted
      style would try ``<bucket>.<project>.supabase.co`` and fail DNS.
    * the project's real region (for example ``ap-south-1``), not ``auto``.
      ``auto`` is a Cloudflare R2 convention that Supabase does not accept.
    """

    def __init__(self) -> None:
        self._client = None

    def _s3(self):
        if self._client is None:
            try:
                import boto3
                from botocore.config import Config
            except ImportError as exc:  # pragma: no cover - configuration error
                raise StorageError(
                    "S3 storage needs the storage extra: pip install '.[storage]'"
                ) from exc

            self._client = boto3.client(
                "s3",
                endpoint_url=settings.s3_endpoint_url or None,
                aws_access_key_id=settings.s3_access_key_id,
                aws_secret_access_key=settings.s3_secret_access_key,
                region_name=settings.s3_region or None,
                config=Config(
                    signature_version="s3v4",
                    s3={"addressing_style": "path"},
                    retries={"max_attempts": 3, "mode": "standard"},
                    connect_timeout=5,
                    read_timeout=30,
                ),
            )
        return self._client

    def _bucket(self) -> str:
        if not settings.s3_bucket:
            raise StorageError("S3_BUCKET is not set")
        return settings.s3_bucket

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        bucket = self._bucket()
        try:
            await asyncio.to_thread(
                self._s3().put_object,
                Bucket=bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
        except Exception as exc:
            raise StorageError(_describe("Upload", exc)) from exc

    async def delete(self, key: str) -> None:
        bucket = self._bucket()
        try:
            await asyncio.to_thread(self._s3().delete_object, Bucket=bucket, Key=key)
        except Exception as exc:
            raise StorageError(_describe("Delete", exc)) from exc

    async def read(self, key: str) -> bytes:
        bucket = self._bucket()
        try:
            response = await asyncio.to_thread(self._s3().get_object, Bucket=bucket, Key=key)
        except Exception as exc:
            code = _error_code(exc)
            if code in {"NoSuchKey", "404", "NotFound"}:
                raise StorageError("Not found") from exc
            raise StorageError(_describe("Read", exc)) from exc

        return await asyncio.to_thread(response["Body"].read)

    async def signed_url(self, key: str, ttl_seconds: int | None = None) -> str:
        bucket = self._bucket()
        ttl = ttl_seconds or settings.signed_url_ttl_seconds
        try:
            return await asyncio.to_thread(
                self._s3().generate_presigned_url,
                "get_object",
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=ttl,
            )
        except Exception as exc:
            raise StorageError(_describe("Sign", exc)) from exc


class SupabaseStorage:
    """Supabase Storage over its REST API.

    This is the default production backend because the project's own API keys are
    enough: ``SUPABASE_URL`` plus the **secret** key (``sb_secret_...``). The S3
    protocol needs a *separate* S3 access key pair generated in the dashboard, and
    an ``sb_secret_`` key will not work there - it is an API key, not a SigV4
    credential.

    The bucket stays private. Files are read through the authenticated endpoint or
    through a short-lived signed URL; neither exposes the bucket publicly.

    ``SUPABASE_SECRET_KEY`` bypasses row-level security, so it must never leave the
    backend. The publishable key is the browser-safe one and is not used here.
    """

    def __init__(self) -> None:
        self._bucket_ready = False
        self._bucket_lock = asyncio.Lock()

    # -- plumbing ------------------------------------------------------------
    def _require_config(self) -> tuple[str, str, str]:
        url = (settings.supabase_url or "").rstrip("/")
        key = settings.supabase_secret_key or ""
        bucket = settings.supabase_bucket or ""
        if not url or not key:
            raise StorageError("SUPABASE_URL and SUPABASE_SECRET_KEY are required")
        if not bucket:
            raise StorageError("SUPABASE_BUCKET is not set")
        return url, key, bucket

    def _headers(self, key: str, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {key}", "apikey": key}
        if extra:
            headers.update(extra)
        return headers

    @staticmethod
    def _message(response: "httpx.Response") -> str:
        try:
            payload = response.json()
        except ValueError:
            return response.text[:200]
        if isinstance(payload, dict):
            for field in ("message", "error", "error_description"):
                if payload.get(field):
                    return str(payload[field])
        return response.text[:200]

    def _fail(self, operation: str, response: "httpx.Response") -> StorageError:
        code = response.status_code
        message = self._message(response)
        if code in {401, 403}:
            return StorageError(
                f"{operation} failed: Supabase rejected the key (HTTP {code}). "
                f"Check SUPABASE_SECRET_KEY. {message}"
            )
        return StorageError(f"{operation} failed (HTTP {code}): {message}")

    async def _ensure_bucket(self) -> None:
        """Create the bucket on first use when auto-create is enabled."""
        if self._bucket_ready:
            return

        url, key, bucket = self._require_config()
        async with self._bucket_lock:
            if self._bucket_ready:
                return

            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
                existing = await client.get(
                    f"{url}/storage/v1/bucket/{quote(bucket, safe='')}",
                    headers=self._headers(key),
                )
                if existing.status_code == 200:
                    self._bucket_ready = True
                    return

                if existing.status_code not in {400, 404}:
                    raise self._fail("Bucket lookup", existing)

                if not settings.supabase_auto_create_bucket:
                    raise StorageError(
                        f"Bucket '{bucket}' does not exist. Create it in Supabase "
                        f"(Storage -> New bucket, keep it private) or set "
                        f"SUPABASE_AUTO_CREATE_BUCKET=true."
                    )

                created = await client.post(
                    f"{url}/storage/v1/bucket",
                    headers=self._headers(key, {"Content-Type": "application/json"}),
                    json={"id": bucket, "name": bucket, "public": False},
                )
                if created.status_code not in {200, 201}:
                    # Another worker may have created it a moment ago.
                    check = await client.get(
                        f"{url}/storage/v1/bucket/{quote(bucket, safe='')}",
                        headers=self._headers(key),
                    )
                    if check.status_code != 200:
                        raise self._fail("Bucket creation", created)

                log.info("supabase_bucket_ready", bucket=bucket)
                self._bucket_ready = True

    # -- storage protocol ----------------------------------------------------
    async def put(self, key: str, data: bytes, content_type: str) -> None:
        await self._ensure_bucket()
        url, api_key, bucket = self._require_config()
        target = f"{url}/storage/v1/object/{quote(bucket, safe='')}/{quote(key, safe='/-_.~')}"

        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
            response = await client.post(
                target,
                headers=self._headers(
                    api_key,
                    {
                        "Content-Type": content_type,
                        "Cache-Control": "private, max-age=0",
                        "x-upsert": "true",
                    },
                ),
                content=data,
            )

        if response.status_code not in {200, 201}:
            raise self._fail("Upload", response)

    async def delete(self, key: str) -> None:
        url, api_key, bucket = self._require_config()
        target = f"{url}/storage/v1/object/{quote(bucket, safe='')}/{quote(key, safe='/-_.~')}"

        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
            response = await client.request(
                "DELETE", target, headers=self._headers(api_key)
            )

        if response.status_code not in {200, 204}:
            # Deleting something that is already gone is not an error for callers.
            if response.status_code == 404:
                return
            raise self._fail("Delete", response)

    async def read(self, key: str) -> bytes:
        url, api_key, bucket = self._require_config()
        target = (
            f"{url}/storage/v1/object/authenticated/{quote(bucket, safe='')}"
            f"/{quote(key, safe='/-_.~')}"
        )

        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
            response = await client.get(target, headers=self._headers(api_key))

        if response.status_code == 404:
            raise StorageError("Not found")
        if response.status_code != 200:
            raise self._fail("Read", response)
        return response.content

    async def signed_url(self, key: str, ttl_seconds: int | None = None) -> str:
        url, api_key, bucket = self._require_config()
        ttl = ttl_seconds or settings.signed_url_ttl_seconds
        target = f"{url}/storage/v1/object/sign/{quote(bucket, safe='')}/{quote(key, safe='/-_.~')}"

        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
            response = await client.post(
                target,
                headers=self._headers(api_key, {"Content-Type": "application/json"}),
                json={"expiresIn": ttl},
            )

        if response.status_code != 200:
            raise self._fail("Sign", response)

        payload = response.json()
        # The REST API returns camelCase; accept the variants rather than break.
        signed = (
            payload.get("signedURL")
            or payload.get("signedUrl")
            or payload.get("signed_url")
            or ""
        )
        if not signed:
            raise StorageError("Sign failed: no signed URL in the response")

        if signed.startswith("http"):
            return signed
        if signed.startswith("/storage/v1"):
            return f"{url}{signed}"
        return f"{url}/storage/v1{signed}"


_storage: Storage | None = None


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        if settings.storage_backend == "supabase":
            _storage = SupabaseStorage()
        elif settings.storage_backend == "s3":
            _storage = S3Storage()
        else:
            _storage = LocalStorage(settings.storage_local_dir)
    return _storage


def reset_storage() -> None:
    """Test hook: forget the cached backend after settings change."""
    global _storage
    _storage = None


def verify_signed_url(key: str, exp: int, sig: str) -> bool:
    from app.core.security import signatures_match

    if exp < int(utcnow().timestamp()):
        return False
    return signatures_match(sign_payload(f"{key}:{exp}"), sig)
