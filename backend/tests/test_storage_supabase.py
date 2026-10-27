"""Supabase Storage tests against a fake Storage API server.

Supabase's REST API is the default production backend, because the project's own
URL and secret key are enough. These tests run a real HTTP server that implements
the four Storage endpoints we use, so the code path under test is the same one that
talks to supabase.co: real httpx calls, real status codes, real signed URLs that
are actually fetched back.

`scripts/storage_check.py` does the same thing against the live project.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

import pytest

from app.core.config import settings
from app.services import storage as storage_module
from app.services.storage import StorageError, SupabaseStorage

SECRET = "test-secret-key"
BUCKET = "autoapply-private"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class _State:
    def __init__(self) -> None:
        self.buckets: dict[str, dict[str, tuple[bytes, str]]] = {}
        self.calls: list[str] = []


class _Handler(BaseHTTPRequestHandler):
    state: _State
    # HTTP/1.1 keeps the connection open between calls, which removes the
    # accept/close race that made this fake server flaky under load. Every
    # response below sets Content-Length, which HTTP/1.1 requires.
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # silence the test output
        pass

    # -- dispatch ----------------------------------------------------------
    def do_GET(self):
        self._dispatch(self._on_get)

    def do_POST(self):
        self._dispatch(self._on_post)

    def do_DELETE(self):
        self._dispatch(self._on_delete)

    def _dispatch(self, handler):
        try:
            handler()
        except (BrokenPipeError, ConnectionResetError):
            # The client hung up mid-response; nothing to report.
            self.close_connection = True
        except Exception:
            try:
                self._json(500, {"message": "fake server error"})
            except Exception:
                self.close_connection = True

    # -- helpers -----------------------------------------------------------
    def _send(self, code: int, body: bytes = b"", content_type: str = "application/json"):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _json(self, code: int, payload: dict):
        self._send(code, json.dumps(payload).encode())

    def _authorised(self) -> bool:
        return self.headers.get("Authorization") == f"Bearer {SECRET}"

    def _body(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length else b""

    def _route(self):
        parts = urlsplit(self.path)
        segments = [unquote(segment) for segment in parts.path.split("/") if segment]
        return parts, segments

    def _serve_object(self, bucket: str, key: str):
        items = self.state.buckets.get(bucket)
        if items is None:
            return self._json(404, {"message": "Bucket not found"})
        if key not in items:
            return self._json(404, {"message": "Object not found"})
        data, content_type = items[key]
        return self._send(200, data, content_type)

    # -- verbs -------------------------------------------------------------
    def _on_get(self):
        parts, segments = self._route()
        self.state.calls.append(f"GET {parts.path}")

        # A signed URL is meant to work without a bearer token, but only with one.
        if len(segments) > 3 and segments[2] == "object" and segments[3] == "sign":
            if "token=" not in parts.query:
                return self._json(401, {"message": "Missing token"})
            bucket, key = segments[4], "/".join(segments[5:])
            return self._serve_object(bucket, key)

        if not self._authorised():
            return self._json(401, {"message": "Invalid JWT"})
        if segments[:3] == ["storage", "v1", "bucket"] and len(segments) == 4:
            name = segments[3]
            if name in self.state.buckets:
                return self._json(200, {"id": name, "name": name, "public": False})
            return self._json(404, {"message": "Bucket not found"})
        if segments[:4] == ["storage", "v1", "object", "authenticated"]:
            return self._serve_object(segments[4], "/".join(segments[5:]))
        return self._json(404, {"message": "not found"})

    def _on_post(self):
        parts, segments = self._route()
        self.state.calls.append(f"POST {parts.path}")

        if not self._authorised():
            return self._json(401, {"message": "Invalid JWT"})

        if segments == ["storage", "v1", "bucket"]:
            payload = json.loads(self._body() or b"{}")
            name = payload.get("id") or payload.get("name")
            self.state.buckets.setdefault(name, {})
            return self._json(200, {"name": name})

        if segments[:4] == ["storage", "v1", "object", "sign"] and len(segments) >= 6:
            bucket, key = segments[4], "/".join(segments[5:])
            if key not in self.state.buckets.get(bucket, {}):
                return self._json(404, {"message": "Object not found"})
            return self._json(
                200, {"signedURL": f"/object/sign/{bucket}/{key}?token=sig-{key}"}
            )

        if segments[:3] == ["storage", "v1", "object"] and len(segments) >= 5:
            bucket, key = segments[3], "/".join(segments[4:])
            if bucket not in self.state.buckets:
                return self._json(400, {"message": "Bucket not found"})
            data = self._body()
            content_type = self.headers.get("Content-Type") or "application/octet-stream"
            self.state.buckets[bucket][key] = (data, content_type)
            return self._json(200, {"Key": f"{bucket}/{key}"})

        return self._json(404, {"message": "not found"})

    def _on_delete(self):
        parts, segments = self._route()
        self.state.calls.append(f"DELETE {parts.path}")

        if not self._authorised():
            return self._json(401, {"message": "Invalid JWT"})
        if segments[:3] == ["storage", "v1", "object"] and len(segments) >= 5:
            bucket, key = segments[3], "/".join(segments[4:])
            items = self.state.buckets.get(bucket, {})
            if key not in items:
                return self._json(404, {"message": "Object not found"})
            del items[key]
            return self._json(200, {"message": "Successfully deleted"})
        return self._json(404, {"message": "not found"})


@pytest.fixture(scope="module")
def supabase_server():
    state = _State()
    handler = type("Handler", (_Handler,), {"state": state})

    class _Server(ThreadingHTTPServer):
        daemon_threads = True
        allow_reuse_address = True
        request_queue_size = 64

    server = _Server(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}", state
    server.shutdown()
    server.server_close()


@pytest.fixture
def supabase_config(monkeypatch, supabase_server):
    url, state = supabase_server
    state.buckets.clear()
    state.calls.clear()

    monkeypatch.setattr(settings, "storage_backend", "supabase")
    monkeypatch.setattr(settings, "supabase_url", url)
    monkeypatch.setattr(settings, "supabase_secret_key", SECRET)
    monkeypatch.setattr(settings, "supabase_bucket", BUCKET)
    monkeypatch.setattr(settings, "supabase_auto_create_bucket", True)
    storage_module.reset_storage()
    yield state
    storage_module.reset_storage()


def test_get_storage_selects_supabase(supabase_config):
    assert isinstance(storage_module.get_storage(), SupabaseStorage)


async def test_bucket_is_created_on_first_upload(supabase_config):
    store = storage_module.get_storage()
    assert BUCKET not in supabase_config.buckets

    await store.put("resume/u1/a.txt", b"hello", "text/plain")

    assert BUCKET in supabase_config.buckets
    assert supabase_config.buckets[BUCKET]["resume/u1/a.txt"][0] == b"hello"
    assert any(call == "POST /storage/v1/bucket" for call in supabase_config.calls)


async def test_bucket_is_created_only_once(supabase_config):
    store = storage_module.get_storage()
    await store.put("a.txt", b"1", "text/plain")
    await store.put("b.txt", b"2", "text/plain")

    creates = [c for c in supabase_config.calls if c == "POST /storage/v1/bucket"]
    assert len(creates) == 1


async def test_round_trip(supabase_config):
    store = storage_module.get_storage()
    key = "resume/user-1/cv.pdf"
    payload = b"%PDF-1.4 hello"

    await store.put(key, payload, "application/pdf")
    assert await store.read(key) == payload

    await store.delete(key)
    with pytest.raises(StorageError, match="Not found"):
        await store.read(key)


async def test_upload_sets_content_type_and_upsert(supabase_config):
    store = storage_module.get_storage()
    await store.put("resume/u1/cv.docx", b"PK\x03\x04data", DOCX_MIME)

    _data, content_type = supabase_config.buckets[BUCKET]["resume/u1/cv.docx"]
    assert content_type == DOCX_MIME


async def test_signed_url_goes_through_the_storage_api(supabase_config):
    store = storage_module.get_storage()
    key = "screenshots/u1/a1/shot.png"
    payload = b"\x89PNG\r\n\x1a\nbinary"
    await store.put(key, payload, "image/png")

    url = await store.signed_url(key, 120)

    assert "/storage/v1/object/sign/" in url
    assert f"/{BUCKET}/{key}" in url
    assert "token=" in url


async def test_signed_url_actually_downloads(supabase_config):
    """The whole point of a signed URL: it works without our credentials."""
    import httpx

    store = storage_module.get_storage()
    key = "resume/u1/private.pdf"
    payload = b"%PDF-1.4 confidential"
    await store.put(key, payload, "application/pdf")

    url = await store.signed_url(key, 60)
    async with httpx.AsyncClient() as http:
        response = await http.get(url)

    assert response.status_code == 200
    assert response.content == payload


async def test_revoked_or_wrong_key_is_a_clear_error(supabase_config, monkeypatch):
    monkeypatch.setattr(settings, "supabase_secret_key", "sb_secret_wrong")
    storage_module.reset_storage()

    store = storage_module.get_storage()
    with pytest.raises(StorageError, match="SUPABASE_SECRET_KEY"):
        await store.put("x.txt", b"x", "text/plain")


async def test_missing_bucket_without_auto_create_is_actionable(monkeypatch, supabase_server):
    url, state = supabase_server
    state.buckets.clear()

    monkeypatch.setattr(settings, "storage_backend", "supabase")
    monkeypatch.setattr(settings, "supabase_url", url)
    monkeypatch.setattr(settings, "supabase_secret_key", SECRET)
    monkeypatch.setattr(settings, "supabase_bucket", "never-created")
    monkeypatch.setattr(settings, "supabase_auto_create_bucket", False)
    storage_module.reset_storage()

    store = storage_module.get_storage()
    with pytest.raises(StorageError, match="does not exist"):
        await store.put("x.txt", b"x", "text/plain")
    storage_module.reset_storage()


async def test_missing_config_is_a_clear_error(monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", "")
    store = SupabaseStorage()
    with pytest.raises(StorageError, match="SUPABASE_URL"):
        await store.put("x.txt", b"x", "text/plain")


# --------------------------------------------------------------- app level


async def test_resume_upload_lands_in_supabase(client, supabase_config, session_factory):
    from sqlalchemy import select

    from app.db.models import Profile
    from tests.helpers import make_docx

    await client.post("/api/auth/dev-login", json={"email": "supabase@example.com"})
    body = make_docx(["Priya Sharma", "priya.sharma@example.com", "5 years of experience"])

    response = await client.post("/api/resume", files={"file": ("cv.docx", body, DOCX_MIME)})
    assert response.status_code == 200, response.text
    assert response.json()["parse_status"] == "parsed"

    async with session_factory() as session:
        profile = (
            await session.execute(select(Profile).where(Profile.email == "supabase@example.com"))
        ).scalar_one()

    stored = supabase_config.buckets[BUCKET]
    assert list(stored) == [profile.resume_file_key]
    assert stored[profile.resume_file_key][0] == body

    import httpx

    signed = (await client.get("/api/resume/file-url")).json()
    async with httpx.AsyncClient() as http:
        fetched = await http.get(signed["url"])
    assert fetched.status_code == 200
    assert fetched.content == body


async def test_delete_account_purges_the_bucket(client, supabase_config):
    from tests.helpers import make_docx

    await client.post("/api/auth/dev-login", json={"email": "purge-sb@example.com"})
    body = make_docx(["Purge Me", "purge@example.com", "3 years of experience"])
    await client.post("/api/resume", files={"file": ("cv.docx", body, DOCX_MIME)})
    assert supabase_config.buckets[BUCKET]

    assert (await client.delete("/api/account")).status_code == 204
    assert supabase_config.buckets[BUCKET] == {}


async def test_screenshot_upload_and_signed_url(client, supabase_config):
    import httpx

    from tests.helpers import (
        agent_step,
        complete_onboarding,
        connect_extension,
        extension_headers,
        observation,
        start_run,
    )

    await client.post("/api/auth/dev-login", json={"email": "shot-sb@example.com"})
    await complete_onboarding(client)
    token = await connect_extension(client, install_id="shot-sb")

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

    stored = supabase_config.buckets[BUCKET]
    assert any(key.startswith("screenshots/") for key in stored)

    signed = (await client.get(f"/api/applications/{item['id']}/screenshot-url")).json()
    async with httpx.AsyncClient() as http:
        fetched = await http.get(signed["url"])
    assert fetched.status_code == 200
    assert fetched.content == png
