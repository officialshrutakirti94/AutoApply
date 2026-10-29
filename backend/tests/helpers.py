"""Helpers shared by tests: onboarding, extension pairing, fixture builders."""

from __future__ import annotations

import io

from httpx import AsyncClient

WIDE_HOURS = {"start": "00:00", "end": "23:59", "timezone": "UTC"}


async def complete_onboarding(client: AsyncClient) -> None:
    profile = await client.put(
        "/api/profile",
        json={
            "full_name": "Priya Sharma",
            "phone": "+91 98765 43210",
            "location": "Pune, India",
            "linkedin_url": "https://linkedin.com/in/priyasharma",
            "current_title": "Backend Engineer",
            "current_company": "Acme Systems",
            "years_of_experience": 5,
            "notice_period_days": 60,
            "current_ctc_lpa": 18,
            "expected_ctc_lpa": 24,
            "work_authorization": "Indian citizen, no sponsorship needed",
            "skills": ["Python", "FastAPI", "PostgreSQL", "Docker"],
        },
    )
    assert profile.status_code == 200, profile.text

    preferences = await client.put(
        "/api/preferences",
        json={
            "target_roles": ["Backend Engineer", "Python Developer"],
            "domains": ["Software"],
            "locations": ["Pune", "Remote"],
            "work_mode": ["remote", "hybrid"],
            "experience_level": "mid",
            "platforms": ["linkedin", "naukri"],
            "active_hours": WIDE_HOURS,
            "daily_cap": 10,
        },
    )
    assert preferences.status_code == 200, preferences.text

    done = await client.post("/api/onboarding/complete", json={"risk_accepted": True})
    assert done.status_code == 200, done.text


async def connect_extension(client: AsyncClient, install_id: str = "test-install") -> str:
    pair = await client.post("/api/extension/pair")
    assert pair.status_code == 200, pair.text
    code = pair.json()["code"]

    connect = await client.post(
        "/api/extension/connect", json={"code": code, "install_id": install_id, "label": "Test"}
    )
    assert connect.status_code == 200, connect.text
    return connect.json()["token"]


def extension_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def observation(
    *,
    run_id: str,
    page_type: str = "job_detail",
    job: dict | None = None,
    elements: list[dict] | None = None,
    chat: dict | None = None,
    signals: list[str] | None = None,
    page_text_digest: str | None = None,
    platform: str = "linkedin",
) -> dict:
    payload = {
        "run_id": run_id,
        "platform": platform,
        "page_type": page_type,
        "job": job
        or {
            "id": "4012345",
            "title": "Backend Engineer",
            "company": "Acme Systems",
            "location": "Pune",
            "job_url": "https://www.linkedin.com/jobs/view/4012345",
            "already_applied": False,
            "external": False,
        },
        "elements": elements or [],
        "signals": signals or [],
    }
    if chat is not None:
        payload["chat"] = chat
    if page_text_digest is not None:
        payload["page_text_digest"] = page_text_digest
    return payload


def button(ref: str, label: str) -> dict:
    return {"ref": ref, "kind": "button", "label": label}


def text_field(ref: str, label: str, *, required: bool = True, value: str | None = None) -> dict:
    return {"ref": ref, "kind": "text", "label": label, "required": required, "value": value}


def make_docx(paragraphs: list[str]) -> bytes:
    import docx

    document = docx.Document()
    for line in paragraphs:
        document.add_paragraph(line)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


# A structurally valid PDF with no text content, i.e. what a scanned resume looks like.
EMPTY_PDF = b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj
trailer<</Root 1 0 R>>
%%EOF
"""

SAMPLE_RESUME = """Priya Sharma
Pune, India | +91 98765 43210 | priya.sharma@example.com
linkedin.com/in/priyasharma | github.com/priyasharma

SUMMARY
Backend engineer with 5 years of experience building payment and logistics systems.

EXPERIENCE
Senior Backend Engineer at Acme Systems | 2021 - Present
- Built FastAPI services handling 2M requests per day.

SKILLS
Python, FastAPI, PostgreSQL, Docker, AWS, Kubernetes

EDUCATION
B.Tech in Computer Science, Pune Institute of Technology, 2019
"""

# ------------------------------------------------------------------ run helpers


async def start_run(
    client: AsyncClient, token: str, *, platform: str = "linkedin", dry_run: bool = False
) -> dict:
    response = await client.post(
        "/api/runs/start",
        json={"platform": platform, "dry_run": dry_run},
        headers=extension_headers(token),
    )
    assert response.status_code == 200, response.text
    return response.json()["run"]


async def agent_step(client: AsyncClient, token: str, payload: dict) -> dict:
    response = await client.post(
        "/api/agent/step", json=payload, headers=extension_headers(token)
    )
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------- db builders


async def make_user(db, email: str = "unit@example.com", **overrides):
    from app.db.models import User

    user = User(google_sub=f"dev:{email}", email=email, email_verified=True, **overrides)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def make_profile(db, user_id, **overrides):
    from app.db.models import Profile

    profile = Profile(user_id=user_id, **overrides)
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


async def make_preferences(db, user_id, **overrides):
    from app.db.models import Preference

    payload = {"active_hours": WIDE_HOURS, "daily_cap": 10}
    payload.update(overrides)
    preference = Preference(user_id=user_id, **payload)
    db.add(preference)
    await db.commit()
    await db.refresh(preference)
    return preference
