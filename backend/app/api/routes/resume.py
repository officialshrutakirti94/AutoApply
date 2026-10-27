"""Resume upload, parsing and the draft the review step reads."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, File, Request, UploadFile

from app.api.presenters import profile_out
from app.api.routes.profile import get_or_create_profile
from app.api.schemas import ResumeFileOut, ResumeOut
from app.core.config import settings
from app.core.deps import CurrentUser, DbSession
from app.core.errors import NotFound
from app.core.ratelimit import check_rate_limit
from app.db.models import Profile
from app.resume.extract import (
    NO_TEXT_MESSAGE,
    DocumentKind,
    NoTextFound,
    detect_kind,
    extract_text,
)
from app.resume.parse import ParsedResume, parse_resume
from app.services.storage import get_storage

router = APIRouter(tags=["resume"])

_CONTENT_TYPES = {
    DocumentKind.PDF: "application/pdf",
    DocumentKind.DOCX: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _apply_parsed(profile: Profile, parsed: ParsedResume) -> None:
    """Prefill from the parse, never wiping a field the parser could not read."""
    scalar_fields = (
        "full_name",
        "phone",
        "email",
        "location",
        "linkedin_url",
        "github_url",
        "portfolio_url",
        "summary",
        "current_title",
        "current_company",
    )
    for field in scalar_fields:
        value = getattr(parsed, field)
        if field == "email":
            continue  # the account email is authoritative
        if value:
            setattr(profile, field, value)

    if parsed.years_of_experience is not None:
        profile.years_of_experience = parsed.years_of_experience
    if parsed.skills:
        profile.skills = parsed.skills
    if parsed.education:
        profile.education = [item.model_dump() for item in parsed.education]


@router.post("/resume", response_model=ResumeOut)
async def upload_resume(
    request: Request,
    user: CurrentUser,
    db: DbSession,
    file: UploadFile = File(...),
) -> ResumeOut:
    await check_rate_limit(request, bucket="resume", window_seconds=60, limit=6)

    profile = await get_or_create_profile(db, user_id=user.id, email=user.email)
    raw = await file.read(settings.upload_max_mb * 1024 * 1024 + 1)
    kind = detect_kind(file.filename, file.content_type, raw)

    try:
        text = await extract_text(raw, kind)
    except NoTextFound:
        # A valid file we simply cannot read. Not an error dialog: the UI offers
        # manual entry with the exact copy from the plan.
        profile.parse_status = "failed"
        await db.commit()
        await db.refresh(profile)
        return ResumeOut(
            parse_status="failed",
            message=NO_TEXT_MESSAGE,
            profile=profile_out(profile),
        )

    parsed = await parse_resume(text)

    storage = get_storage()
    key = f"resume/{user.id}/{uuid.uuid4().hex}.{kind.value}"
    await storage.put(key, raw, _CONTENT_TYPES[kind])

    previous_key = profile.resume_file_key
    if previous_key and previous_key != key:
        try:
            await storage.delete(previous_key)
        except Exception:  # already gone is fine
            pass

    _apply_parsed(profile, parsed)
    profile.resume_file_key = key
    profile.resume_parsed = parsed.model_dump(mode="json")
    profile.parse_status = "parsed"
    profile.onboarding_step = max(profile.onboarding_step, 2)

    await db.commit()
    await db.refresh(profile)

    return ResumeOut(
        parse_status=profile.parse_status,
        draft=profile.resume_parsed,
        confidence=dict((profile.resume_parsed or {}).get("confidence") or {}),
        profile=profile_out(profile),
    )


@router.get("/resume/file-url", response_model=ResumeFileOut)
async def resume_file_url(user: CurrentUser, db: DbSession) -> ResumeFileOut:
    """A short-lived link to the user's own resume, for the Settings/Review screen.

    Dashboard scope, unlike `/extension/resume-file`, which is extension scope and
    only valid during an active run.
    """
    profile = await get_or_create_profile(db, user_id=user.id, email=user.email)
    if not profile.resume_file_key:
        raise NotFound("No resume has been uploaded yet.")

    url = await get_storage().signed_url(
        profile.resume_file_key, settings.signed_url_ttl_seconds
    )
    return ResumeFileOut(url=url, expires_in=settings.signed_url_ttl_seconds)


@router.get("/resume/draft", response_model=ResumeOut)
async def read_draft(user: CurrentUser, db: DbSession) -> ResumeOut:
    profile = await get_or_create_profile(db, user_id=user.id, email=user.email)
    if not profile.resume_parsed:
        raise NotFound("No resume has been parsed yet.")

    return ResumeOut(
        parse_status=profile.parse_status,
        draft=profile.resume_parsed,
        confidence=dict((profile.resume_parsed or {}).get("confidence") or {}),
        profile=profile_out(profile),
    )


@router.post("/resume/manual", response_model=ResumeOut)
async def use_manual_entry(user: CurrentUser, db: DbSession) -> ResumeOut:
    """Let the user skip parsing and type their details instead."""
    profile = await get_or_create_profile(db, user_id=user.id, email=user.email)
    if profile.parse_status in {"none", "failed"}:
        profile.parse_status = "manual"
        await db.commit()
        await db.refresh(profile)
    return ResumeOut(
        parse_status=profile.parse_status,
        draft=profile.resume_parsed,
        confidence=dict((profile.resume_parsed or {}).get("confidence") or {}),
        profile=profile_out(profile),
    )
