"""Probe the configured object store end to end.

Run this once after filling in the storage settings, and again after any credential
rotation or deploy:

    python scripts/storage_check.py

It performs exactly what the app performs — upload, read back, sign a URL, fetch
that URL over HTTP, delete — and prints a hint for each common failure. Exit code is
non-zero on failure, so it works in a deploy pipeline.

Works with all three backends: ``local``, ``supabase`` (REST API) and ``s3``.
Nothing sensitive is printed: keys are masked and secrets never appear.
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# Allow running from any directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.services.storage import (  # noqa: E402
    get_storage,
    reset_storage,
    verify_signed_url,
)

PAYLOAD = b"autoapply storage check\n"

HINTS: dict[str, list[str]] = {
    "Invalid JWT": [
        "SUPABASE_SECRET_KEY is not valid for this project. It must be the secret key",
        "(sb_secret_...), not the publishable one.",
        "Rotate it in Supabase: Project Settings -> API keys.",
    ],
    "SUPABASE_SECRET_KEY": [
        "The key was rejected. Regenerate the secret key in Supabase and update .env.",
    ],
    "Bucket not found": [
        "The bucket does not exist and auto-create is off.",
        "Either set SUPABASE_AUTO_CREATE_BUCKET=true or create it in the dashboard",
        "(Storage -> New bucket) and keep it private.",
    ],
    "SignatureDoesNotMatch": [
        "S3_SECRET_ACCESS_KEY is wrong, or S3_REGION does not match the project region.",
        "Supabase requires the real region (e.g. ap-south-1); 'auto' is an R2 value.",
    ],
    "InvalidAccessKeyId": [
        "S3_ACCESS_KEY_ID does not exist. Create an S3 access key in the Supabase",
        "dashboard (Storage -> S3 access keys) — an sb_secret_ key is not an S3 key.",
    ],
    "404": [
        "Endpoint path is wrong. For S3 it must be "
        "https://<project-ref>.supabase.co/storage/v1/s3",
    ],
}


def mask(value: str) -> str:
    if not value:
        return "(not set)"
    if len(value) <= 8:
        return value[0] + "***"
    return f"{value[:4]}...{value[-4:]}"


def show_config() -> list[str]:
    """Print the effective config and return a list of missing settings."""
    print("Object storage check")
    print("--------------------")
    print(f"backend        {settings.storage_backend}")

    missing: list[str] = []

    if settings.storage_backend == "local":
        print(f"local dir      {settings.storage_local_dir}")
        print()
        print("Local mode: no bucket involved. Set STORAGE_BACKEND=supabase to check")
        print("the real project.")
        print()
        return missing

    if settings.storage_backend == "supabase":
        print(f"project url    {settings.supabase_url or '(not set)'}")
        print(f"bucket         {settings.supabase_bucket or '(not set)'}")
        print(f"secret key     {mask(settings.supabase_secret_key)}")
        print(f"auto create    {settings.supabase_auto_create_bucket}")
        missing = [
            name
            for name, value in {
                "SUPABASE_URL": settings.supabase_url,
                "SUPABASE_SECRET_KEY": settings.supabase_secret_key,
                "SUPABASE_BUCKET": settings.supabase_bucket,
            }.items()
            if not value
        ]
    else:
        print(f"endpoint       {settings.s3_endpoint_url or '(not set)'}")
        print(f"region         {settings.s3_region or '(not set)'}")
        print(f"bucket         {settings.s3_bucket or '(not set)'}")
        print(f"access key     {mask(settings.s3_access_key_id)}")
        print(f"secret key     {'(set)' if settings.s3_secret_access_key else '(not set)'}")
        if settings.s3_region.lower() == "auto":
            print("hint           region 'auto' is an R2 convention; use the real region")
        missing = [
            name
            for name, value in {
                "S3_ENDPOINT_URL": settings.s3_endpoint_url,
                "S3_REGION": settings.s3_region,
                "S3_ACCESS_KEY_ID": settings.s3_access_key_id,
                "S3_SECRET_ACCESS_KEY": settings.s3_secret_access_key,
                "S3_BUCKET": settings.s3_bucket,
            }.items()
            if not value
        ]

    print(f"signed url ttl {settings.signed_url_ttl_seconds}s")
    print()
    return missing


async def run() -> int:
    reset_storage()
    store = get_storage()
    key = f"healthcheck/{uuid.uuid4().hex}.txt"
    remote = settings.storage_backend in {"supabase", "s3"}

    try:
        await store.put(key, PAYLOAD, "text/plain")
        print("ok    upload")
    except Exception as exc:
        print(f"FAIL  upload: {exc}")
        for hint in HINTS.get(next((h for h in HINTS if h in str(exc)), ""), []):
            print(f"      {hint}")
        return 1

    try:
        content = await store.read(key)
    except Exception as exc:
        print(f"FAIL  read: {exc}")
        return 1
    if content != PAYLOAD:
        print("FAIL  read: the bytes that came back are not the bytes we uploaded")
        return 1
    print("ok    read (bytes match)")

    try:
        url = await store.signed_url(key, 60)
    except Exception as exc:
        print(f"FAIL  sign: {exc}")
        return 1
    print(f"ok    sign: {url[:96]}...")

    if remote:
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as http:
                response = await http.get(url)
        except Exception as exc:
            print(f"FAIL  fetch signed url: {exc}")
            return 1

        if response.status_code != 200:
            print(f"FAIL  fetch signed url: HTTP {response.status_code}")
            print(f"      {response.text[:300]}")
            return 1
        if response.content != PAYLOAD:
            print("FAIL  fetch signed url: HTTP 200 but the bytes are wrong")
            return 1
        print("ok    fetch signed url (HTTP 200, bytes match)")
    else:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        try:
            exp = int(query["exp"][0])
            sig = query["sig"][0]
        except (KeyError, ValueError, IndexError):
            print("FAIL  sign: the local URL is missing exp or sig")
            return 1
        if not verify_signed_url(key, exp, sig):
            print("FAIL  sign: the local signature does not verify")
            return 1
        print("ok    verify signature (local HMAC)")

    try:
        await store.delete(key)
        print("ok    delete")
    except Exception as exc:
        print(f"FAIL  delete: {exc}")
        return 1

    print()
    if remote:
        print("Storage is working. Resume uploads, screenshots and signed URLs will work.")
    else:
        print("Local storage is working. Set STORAGE_BACKEND=supabase to check the project.")
    return 0


def main() -> int:
    missing = show_config()
    if missing:
        print("Missing settings: " + ", ".join(missing))
        print("Fill them in .env (see .env.example) and run this again.")
        return 2

    if settings.storage_backend == "s3":
        try:
            import boto3  # noqa: F401
        except ImportError:
            print("boto3 is not installed. Install the storage extra:  pip install '.[storage]'")
            return 2

    return asyncio.run(run())


if __name__ == "__main__":
    raise SystemExit(main())
