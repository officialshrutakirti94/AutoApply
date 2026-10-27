"""End-to-end: the journey a real user and their extension take."""

from __future__ import annotations

from urllib.parse import urlparse

from tests.helpers import (
    agent_step,
    button,
    extension_headers,
    observation,
    start_run,
    text_field,
)


async def test_platform_status_flips_the_dashboard_chip(onboarded, extension_token):
    response = await onboarded.post(
        "/api/platform/status",
        json={"platform": "linkedin", "signed_in": True},
        headers=extension_headers(extension_token),
    )
    assert response.status_code == 204

    me = (await onboarded.get("/api/auth/me")).json()
    linkedin = next(chip for chip in me["platforms"] if chip["platform"] == "linkedin")
    assert linkedin["signed_in"] is True

    naukri = next(chip for chip in me["platforms"] if chip["platform"] == "naukri")
    assert naukri["signed_in"] is False


async def test_full_application_journey(onboarded, extension_token):
    run = await start_run(onboarded, extension_token, dry_run=False)

    # 1. search results -> open the matching card
    step = await agent_step(
        onboarded,
        extension_token,
        observation(
            run_id=run["id"],
            page_type="search_results",
            elements=[
                button("b1", "Marketing Manager at Foo"),
                button("b2", "Backend Engineer at Acme Systems"),
            ],
        ),
    )
    assert step["status"] == "continue"
    assert step["actions"][0] == {"type": "click", "ref": "b2"}

    # 2. job detail -> Easy Apply
    step = await agent_step(
        onboarded,
        extension_token,
        observation(
            run_id=run["id"],
            page_type="job_detail",
            elements=[button("b1", "Easy Apply")],
        ),
    )
    assert step["actions"][0]["ref"] == "b1"

    # 3. first form step -> fill, then Next
    step = await agent_step(
        onboarded,
        extension_token,
        observation(
            run_id=run["id"],
            page_type="apply_form",
            elements=[
                text_field("f1", "Full name"),
                text_field("f2", "Email address"),
                button("b9", "Next"),
            ],
        ),
    )
    assert [action["type"] for action in step["actions"]] == [
        "fill_text",
        "fill_text",
        "click",
    ]

    # 4. final form step -> submit
    step = await agent_step(
        onboarded,
        extension_token,
        observation(
            run_id=run["id"],
            page_type="apply_form",
            elements=[
                text_field("f5", "Notice period"),
                button("b9", "Submit application"),
            ],
        ),
    )
    assert step["actions"][-1] == {"type": "submit"}
    assert step["meta"]["job_status"] == "applied"

    # 5. confirmation -> done
    step = await agent_step(
        onboarded,
        extension_token,
        observation(run_id=run["id"], page_type="confirmation"),
    )
    assert step["status"] == "done"

    ledger = (await onboarded.get("/api/applications")).json()
    assert len(ledger["items"]) == 1
    assert ledger["items"][0]["status"] == "applied"
    assert ledger["items"][0]["job_url"].startswith("https://www.linkedin.com/")
    assert ledger["total_unresolved"] == 0

    active = (await onboarded.get("/api/runs/active")).json()
    assert active["run"] is not None
    assert active["run"]["applied_count"] == 1
    assert active["today"]["applied"] == 1

    stop = await onboarded.post(
        f"/api/runs/{run['id']}/stop", json={}, headers=extension_headers(extension_token)
    )
    assert stop.status_code == 200
    assert stop.json()["status"] == "stopped"

    assert (await onboarded.get("/api/runs/active")).json()["run"] is None


async def test_stuck_application_reaches_the_needs_you_inbox(onboarded, extension_token):
    run = await start_run(onboarded, extension_token, dry_run=False)

    await agent_step(
        onboarded,
        extension_token,
        observation(
            run_id=run["id"],
            page_type="chat_question",
            elements=[button("b9", "Next")],
            chat={"question": "What is your caste?", "input_ref": "c1"},
        ),
    )

    ledger = (await onboarded.get("/api/applications")).json()
    item = ledger["items"][0]
    assert item["status"] == "needs_attention"
    assert item["reason"] == "sensitive_question"
    assert item["reason_label"]
    assert ledger["total_unresolved"] == 1

    resolved = await onboarded.patch(
        f"/api/applications/{item['id']}", json={"status": "resolved"}
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"

    assert (await onboarded.get("/api/applications")).json()["total_unresolved"] == 0


async def test_screenshot_upload_and_signed_url(onboarded, extension_token):
    run = await start_run(onboarded, extension_token, dry_run=False)
    await agent_step(
        onboarded, extension_token, observation(run_id=run["id"], page_type="confirmation")
    )
    item = (await onboarded.get("/api/applications")).json()["items"][0]
    assert item["has_screenshot"] is False

    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 128
    upload = await onboarded.post(
        f"/api/applications/{item['id']}/screenshot",
        files={"file": ("stuck.png", png, "image/png")},
        headers=extension_headers(extension_token),
    )
    assert upload.status_code == 204

    updated = (await onboarded.get("/api/applications")).json()["items"][0]
    assert updated["has_screenshot"] is True

    signed = (await onboarded.get(f"/api/applications/{item['id']}/screenshot-url")).json()
    parsed = urlparse(signed["url"])

    fetched = await onboarded.get(f"{parsed.path}?{parsed.query}")
    assert fetched.status_code == 200
    assert fetched.content == png

    tampered = await onboarded.get(f"{parsed.path}?exp=99999999999&sig=deadbeef")
    assert tampered.status_code == 403


async def test_screenshot_type_is_validated(onboarded, extension_token):
    run = await start_run(onboarded, extension_token, dry_run=False)
    await agent_step(
        onboarded, extension_token, observation(run_id=run["id"], page_type="confirmation")
    )
    item = (await onboarded.get("/api/applications")).json()["items"][0]

    response = await onboarded.post(
        f"/api/applications/{item['id']}/screenshot",
        files={"file": ("not-an-image.png", b"just text", "image/png")},
        headers=extension_headers(extension_token),
    )
    assert response.status_code == 415


async def test_resume_file_requires_an_active_run(onboarded, extension_token):
    response = await onboarded.get(
        "/api/extension/resume-file", headers=extension_headers(extension_token)
    )
    assert response.status_code == 404


async def test_ledger_filters(onboarded, extension_token):
    run = await start_run(onboarded, extension_token, dry_run=False)

    await agent_step(
        onboarded,
        extension_token,
        observation(run_id=run["id"], page_type="confirmation"),
    )
    await agent_step(
        onboarded,
        extension_token,
        observation(
            run_id=run["id"],
            job={"id": "ext-2", "title": "Backend Engineer", "external": True},
            page_type="external",
        ),
    )

    applied = (await onboarded.get("/api/applications?status=applied")).json()["items"]
    skipped = (await onboarded.get("/api/applications?status=skipped")).json()["items"]
    assert len(applied) == 1
    assert len(skipped) == 1

    bad = await onboarded.get("/api/applications?status=not_a_status")
    assert bad.status_code == 422

    by_platform = (await onboarded.get("/api/applications?platform=naukri")).json()["items"]
    assert by_platform == []


async def test_answers_can_be_created_edited_and_deleted(onboarded):
    created = await onboarded.post(
        "/api/qa",
        json={"question": "Why do you want this role?", "answer": "The problem is interesting."},
    )
    assert created.status_code == 201
    entry = created.json()
    assert entry["source"] == "user"

    duplicate = await onboarded.post(
        "/api/qa",
        json={"question": "Why do you want this role?", "answer": "Because."},
    )
    assert duplicate.status_code == 409

    edited = await onboarded.patch(
        f"/api/qa/{entry['id']}", json={"answer": "The team ships fast."}
    )
    assert edited.json()["answer"] == "The team ships fast."

    listed = (await onboarded.get("/api/qa")).json()
    assert len(listed) == 1

    removed = await onboarded.delete(f"/api/qa/{entry['id']}")
    assert removed.status_code == 204
    assert (await onboarded.get("/api/qa")).json() == []


async def test_internal_sweep_requires_the_cron_secret(client):
    response = await client.post("/api/internal/sweep")
    assert response.status_code == 403

    response = await client.post(
        "/api/internal/sweep", headers={"X-Cron-Secret": "test-cron-secret"}
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True

async def test_start_run_returns_the_search_plan(onboarded, extension_token):
    """The extension cannot read /preferences, so the run carries the query."""
    body = (
        await onboarded.post(
            "/api/runs/start",
            json={"platform": "linkedin", "dry_run": True},
            headers=extension_headers(extension_token),
        )
    ).json()

    search = body["search"]
    assert search["roles"] == ["Backend Engineer", "Python Developer"]
    assert "Pune" in search["locations"]
    assert search["work_mode"] == ["remote", "hybrid"]
    assert search["remote_first"] is True


async def test_search_plan_is_empty_when_preferences_are(onboarded, extension_token):
    await onboarded.put(
        "/api/preferences",
        json={"target_roles": [], "locations": [], "work_mode": []},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    body = (
        await onboarded.post(
            "/api/runs/start",
            json={"platform": "linkedin", "dry_run": True},
            headers=extension_headers(extension_token),
        )
    ).json()

    assert body["search"] == {
        "roles": [],
        "locations": [],
        "work_mode": [],
        "remote_first": False,
    }

async def test_a_stale_run_is_reclaimed_instead_of_blocking_forever(
    onboarded, extension_token, db
):
    """A dead tab must not lock the user out of starting a new run."""
    from datetime import timedelta

    from sqlalchemy import select

    from app.core.timeutils import utcnow
    from app.db.models import AgentRun, User

    first = await onboarded.post(
        "/api/runs/start",
        json={"platform": "linkedin", "dry_run": True},
        headers=extension_headers(extension_token),
    )
    assert first.status_code == 200

    user = (
        await db.execute(select(User).where(User.email == "dev@example.com"))
    ).scalar_one()
    run = (
        await db.execute(
            select(AgentRun).where(AgentRun.user_id == user.id, AgentRun.status == "running")
        )
    ).scalar_one()
    run.last_heartbeat_at = utcnow() - timedelta(minutes=10)
    await db.commit()

    second = await onboarded.post(
        "/api/runs/start",
        json={"platform": "linkedin", "dry_run": True},
        headers=extension_headers(extension_token),
    )
    assert second.status_code == 200, second.text
    assert second.json()["run"]["id"] != first.json()["run"]["id"]
