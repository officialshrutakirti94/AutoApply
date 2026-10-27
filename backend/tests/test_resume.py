"""Resume parsing: the deterministic parser, the upload path, and the fallback."""

from __future__ import annotations

import pytest

from app.core.errors import UnsupportedMedia
from app.resume.extract import DocumentKind, detect_kind
from app.resume.parse import heuristic_parse
from tests.helpers import EMPTY_PDF, SAMPLE_RESUME, make_docx

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def test_heuristic_parser_reads_the_basics():
    parsed = heuristic_parse(SAMPLE_RESUME)

    assert parsed.full_name == "Priya Sharma"
    assert parsed.email == "priya.sharma@example.com"
    assert "98765" in (parsed.phone or "")
    assert parsed.years_of_experience == 5.0
    assert parsed.location is not None and "pune" in parsed.location.lower()
    assert parsed.linkedin_url is not None and parsed.linkedin_url.startswith("https://linkedin.com/in/")
    assert parsed.github_url is not None
    assert any("python" in skill.lower() for skill in parsed.skills)
    assert parsed.confidence["email"] == "high"
    assert parsed.suggested_roles


def test_heuristic_parser_survives_a_thin_resume():
    parsed = heuristic_parse("Some Person\nsome.person@example.com")
    assert parsed.email == "some.person@example.com"
    assert parsed.years_of_experience is None
    assert parsed.confidence["years_of_experience"] == "low"


def test_detect_kind_rejects_plain_text():
    with pytest.raises(UnsupportedMedia):
        detect_kind("cv.txt", "text/plain", b"just some text")


def test_detect_kind_rejects_a_zip_that_is_not_docx():
    with pytest.raises(UnsupportedMedia):
        detect_kind("archive.docx", DOCX_MIME, b"PK\x03\x04" + b"nope" * 20)


def test_detect_kind_trusts_the_bytes_over_the_header():
    assert detect_kind("cv.docx", DOCX_MIME, b"%PDF-1.7\n...") is DocumentKind.PDF


def test_detect_kind_accepts_a_real_docx():
    data = make_docx(["Priya Sharma", "priya@example.com"])
    assert detect_kind("cv.docx", DOCX_MIME, data) is DocumentKind.DOCX


async def test_scanned_pdf_returns_the_friendly_fallback(signed_in):
    response = await signed_in.post(
        "/api/resume", files={"file": ("cv.pdf", EMPTY_PDF, "application/pdf")}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["parse_status"] == "failed"
    assert "couldn't read this file" in body["message"]


async def test_docx_upload_prefills_the_profile(signed_in):
    data = make_docx(SAMPLE_RESUME.splitlines())
    response = await signed_in.post(
        "/api/resume", files={"file": ("cv.docx", data, DOCX_MIME)}
    )
    assert response.status_code == 200, response.text

    body = response.json()
    assert body["parse_status"] == "parsed"
    assert body["profile"]["full_name"] == "Priya Sharma"
    assert body["profile"]["has_resume"] is True
    assert body["profile"]["onboarding_step"] >= 2
    assert body["confidence"]["email"] == "high"

    draft = (await signed_in.get("/api/resume/draft")).json()
    assert draft["draft"]["email"] == "priya.sharma@example.com"


async def test_manual_entry_is_always_available(signed_in):
    response = await signed_in.post("/api/resume/manual")
    assert response.status_code == 200
    assert response.json()["parse_status"] == "manual"


async def test_upload_rejects_oversized_files(signed_in):
    big = b"%PDF-1.7\n" + b"0" * (6 * 1024 * 1024)
    response = await signed_in.post(
        "/api/resume", files={"file": ("big.pdf", big, "application/pdf")}
    )
    assert response.status_code == 413


async def test_upload_rejects_wrong_type(signed_in):
    response = await signed_in.post(
        "/api/resume", files={"file": ("cv.txt", b"hello there", "text/plain")}
    )
    assert response.status_code == 415


async def test_upload_requires_a_session(client):
    response = await client.post(
        "/api/resume", files={"file": ("cv.pdf", EMPTY_PDF, "application/pdf")}
    )
    assert response.status_code == 401


async def test_draft_is_404_before_any_upload(signed_in):
    response = await signed_in.get("/api/resume/draft")
    assert response.status_code == 404
