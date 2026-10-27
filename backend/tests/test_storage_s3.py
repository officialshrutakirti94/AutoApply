"""Storage backend tests against a real S3-speaking server.

The local backend is covered indirectly by every upload test. This file covers the
S3 path, because that is the one that only runs in production and therefore the one
most likely to be broken when it matters.

`moto` runs an actual S3-over-HTTP server on localhost, so these tests exercise the
real boto3 client, the real SigV4 signing and real HTTP — including fetching a
presigned URL and receiving the bytes. What they cannot prove is that Supabase's
server agrees, so `scripts/storage_check.py` does that against the live bucket.
"""

from __future__ import annotations

import socket

import pytest

from app.core.config import settings
from app.services import storage as storage_module
from app.services.storage import S3Storage, StorageError

REGION = "ap-south-1"
BUCKET = "autoapply-private"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.fixture(scope="module")
def s3_server():
    """A moto S3 server for the whole module; starting one is slow."""
    from moto.server import ThreadedMotoServer

    port = _free_port()
    server = ThreadedMotoServer(ip_address="127.0.0.1", port=port, verbose=False)
    server.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.stop()


@pytest.fixture
def s3_config(monkeypatch, s3_server):
    """Point the app at the fake bucket and forget the cached backend."""
    monkeypatch.setattr(settings, "storage_backend", "s3")
    monkeypatch.setattr(settings, "s3_endpoint_url", s3_server)
    monkeypatch.setattr(settings, "s3_region", REGION)
    monkeypatch.setattr(settings, "s3_access_key_id", "test-key-id")
    monkeypatch.setattr(settings, "s3_secret_access_key", "test-secret")
    monkeypatch.setattr(settings, "s3_bucket", BUCKET)
    storage_module.reset_storage()
    yield settings
    storage_module.reset_storage()


@pytest.fixture
def fake_bucket(s3_config, s3_server):
    """Create the bucket and hand back a client for assertions."""
    import boto3
    from botocore.config import Config

    client = boto3.client(
        "s3",
        endpoint_url=s3_server,
        region_name=REGION,
        aws_access_key_id="test-key-id",
        aws_secret_access_key="test-secret",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )
    # The moto server lives for the whole module, so the bucket may already exist.
    try:
        client.head_bucket(Bucket=BUCKET)
    except Exception:
        client.create_bucket(
            Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": REGION}
        )
    yield client
    for item in client.list_objects_v2(Bucket=BUCKET).get("Contents", []):
        client.delete_object(Bucket=BUCKET, Key=item["Key"])


def test_get_storage_selects_s3(s3_config):
    assert isinstance(storage_module.get_storage(), S3Storage)


async def test_put_read_delete_round_trip(fake_bucket):
    store = storage_module.get_storage()
    key = "resume/user-1/abc.pdf"

    await store.put(key, b"%PDF-1.4 hello", "application/pdf")

    head = fake_bucket.head_object(Bucket=BUCKET, Key=key)
    assert head["ContentType"] == "application/pdf"
    assert head["ContentLength"] == len(b"%PDF-1.4 hello")

    assert await store.read(key) == b"%PDF-1.4 hello"

    await store.delete(key)
    with pytest.raises(StorageError):
        await store.read(key)


async def test_reading_a_missing_object_is_a_storage_error(fake_bucket):
    store = storage_module.get_storage()
    with pytest.raises(StorageError, match="Not found"):
        await store.read("resume/nobody/missing.pdf")


async def test_signed_url_is_path_style_and_v4(fake_bucket):
    """These are the settings that silently break Supabase if they are wrong."""
    store = storage_module.get_storage()
    key = "screenshots/user-1/app-1/shot.png"
    await store.put(key, b"\x89PNG\r\n\x1a\n", "image/png")

    url = await store.signed_url(key, 60)

    # Path style: bucket in the path, not in the host name.
    assert f"{settings.s3_endpoint_url}/{BUCKET}/{key}" in url
    assert f"{BUCKET}." not in url.replace(f"{BUCKET}/", "")

    # SigV4, which Supabase requires.
    assert "X-Amz-Algorithm=AWS4-HMAC-SHA256" in url
    assert "X-Amz-Signature=" in url
    assert "X-Amz-Expires=60" in url
    assert REGION in url


async def test_presigned_url_actually_downloads_the_object(fake_bucket):
    """A signed URL that does not work is worse than no URL at all."""
    import httpx

    store = storage_module.get_storage()
    key = "resume/user-1/private.pdf"
    payload = b"%PDF-1.4 confidential"
    await store.put(key, payload, "application/pdf")

    url = await store.signed_url(key, 60)
    async with httpx.AsyncClient() as http:
        response = await http.get(url)

    assert response.status_code == 200
    assert response.content == payload


async def test_unsigned_object_url_is_denied(fake_bucket):
    import httpx

    store = storage_module.get_storage()
    key = "resume/user-1/private.pdf"
    await store.put(key, b"%PDF-1.4 confidential", "application/pdf")

    # The bucket is private: the bare path must not serve the file.
    async with httpx.AsyncClient() as http:
        response = await http.get(f"{settings.s3_endpoint_url}/{BUCKET}/{key}")
    assert response.status_code in {401, 403}


async def test_resume_upload_writes_to_the_bucket(client, fake_bucket, session_factory):
    """The app path, not just the storage class: upload -> object in the bucket."""
    from sqlalchemy import select

    from app.db.models import Profile
    from tests.helpers import make_docx

    login = await client.post("/api/auth/dev-login", json={"email": "s3@example.com"})
    assert login.status_code == 200

    body = make_docx(["Priya Sharma", "priya.sharma@example.com", "5 years of experience"])
    response = await client.post("/api/resume", files={"file": ("cv.docx", body, DOCX_MIME)})
    assert response.status_code == 200, response.text
    assert response.json()["parse_status"] == "parsed"

    # Same engine the request used (the dependency override), not the app default.
    async with session_factory() as session:
        profile = (
            await session.execute(select(Profile).where(Profile.email == "s3@example.com"))
        ).scalar_one()

    keys = fake_bucket.list_objects_v2(Bucket=BUCKET).get("Contents", [])
    assert len(keys) == 1
    assert keys[0]["Key"].startswith("resume/")
    assert keys[0]["Key"] == profile.resume_file_key

    # And the user can get their own resume back out through a signed URL.
    import httpx

    signed = (await client.get("/api/resume/file-url")).json()
    async with httpx.AsyncClient() as http:
        fetched = await http.get(signed["url"])
    assert fetched.status_code == 200
    assert fetched.content == body


async def test_screenshot_upload_and_signed_url_use_s3(client, fake_bucket):
    import httpx

    from tests.helpers import (
        agent_step,
        complete_onboarding,
        connect_extension,
        extension_headers,
        observation,
        start_run,
    )

    await client.post("/api/auth/dev-login", json={"email": "s3-shot@example.com"})
    await complete_onboarding(client)
    token = await connect_extension(client, install_id="s3-shot")

    run = await start_run(client, token, dry_run=False)
    await agent_step(client, token, observation(run_id=run["id"], page_type="confirmation"))

    item = (await client.get("/api/applications")).json()["items"][0]
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64

    upload = await client.post(
        f"/api/applications/{item['id']}/screenshot",
        files={"file": ("stuck.png", png, "image/png")},
        headers=extension_headers(token),
    )
    assert upload.status_code == 204, upload.text

    objects = fake_bucket.list_objects_v2(Bucket=BUCKET, Prefix="screenshots/")
    assert objects["KeyCount"] == 1

    signed = (await client.get(f"/api/applications/{item['id']}/screenshot-url")).json()
    assert signed["url"].startswith(f"{settings.s3_endpoint_url}/{BUCKET}/screenshots/")

    async with httpx.AsyncClient() as http:
        fetched = await http.get(signed["url"])
    assert fetched.status_code == 200
    assert fetched.content == png


async def test_delete_account_removes_bucket_objects(client, fake_bucket):
    """Delete-my-data has to reach the bucket, or resumes outlive the account."""
    from tests.helpers import make_docx

    await client.post("/api/auth/dev-login", json={"email": "purge@example.com"})
    body = make_docx(["Purge Me", "purge@example.com", "3 years of experience"])
    await client.post("/api/resume", files={"file": ("cv.docx", body, DOCX_MIME)})

    assert fake_bucket.list_objects_v2(Bucket=BUCKET)["KeyCount"] == 1

    assert (await client.delete("/api/account")).status_code == 204

    assert fake_bucket.list_objects_v2(Bucket=BUCKET)["KeyCount"] == 0


async def test_missing_bucket_name_is_a_clear_error(monkeypatch):
    monkeypatch.setattr(settings, "s3_bucket", "")
    store = S3Storage()

    with pytest.raises(StorageError, match="S3_BUCKET"):
        await store.put("k", b"v", "text/plain")
