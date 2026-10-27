"""End-to-end smoke test against a running backend.

This is the fastest way to see the whole product working over real HTTP, with real
cookies, real storage and a real database. It walks the same journey the dashboard
and the extension will walk, asserts on every step, and prints one line per step.

    # 1. start the API (in another terminal)
    uvicorn app.main:app --port 8000

    # 2. run this
    python scripts/smoke_test.py
    python scripts/smoke_test.py --base-url https://your-api.onrender.com

It needs the dev sign-in, so:
    APP_ENV=development
    AUTH_DEV_BYPASS=true

The script creates one throwaway user and deletes it at the end, which also removes
its rows and its resume object. Pass ``--keep-account`` to inspect the result in the
dashboard afterwards.

Exit code is 0 when every step passes.
"""

from __future__ import annotations

import argparse
import io
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

CSRF = {"X-Requested-With": "XMLHttpRequest"}
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@dataclass
class Run:
    base_url: str
    client: httpx.Client
    passed: int = 0
    failed: int = 0
    failures: list[str] = field(default_factory=list)
    started: float = field(default_factory=time.perf_counter)

    def step(self, label: str, ok: bool, detail: str = "") -> bool:
        if ok:
            self.passed += 1
            print(f"  PASS  {label}" + (f"  [{detail}]" if detail else ""))
        else:
            self.failed += 1
            self.failures.append(label)
            print(f"  FAIL  {label}" + (f"  [{detail}]" if detail else ""))
        return ok

    def info(self, label: str, value: object) -> None:
        print(f"        {label}: {value}")


def make_docx() -> bytes:
    import docx

    document = docx.Document()
    for line in (
        "Priya Sharma",
        "Pune, India | +91 98765 43210 | priya.sharma@example.com",
        "linkedin.com/in/priyasharma",
        "SUMMARY",
        "Backend engineer with 5 years of experience building payment systems.",
        "SKILLS",
        "Python, FastAPI, PostgreSQL, Docker",
        "EDUCATION",
        "B.Tech in Computer Science, Pune Institute of Technology, 2019",
    ):
        document.add_paragraph(line)

    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def observation(run_id: str, *, page_type: str, job_id: str, **extra) -> dict:
    payload = {
        "run_id": run_id,
        "platform": "linkedin",
        "page_type": page_type,
        "job": {
            "id": job_id,
            "title": "Backend Engineer",
            "company": "Acme Systems",
            "location": "Pune, IN",
            "job_url": f"https://www.linkedin.com/jobs/view/{job_id}",
            "already_applied": False,
            "external": False,
        },
        "elements": [],
        "signals": [],
    }
    payload.update(extra)
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="End-to-end smoke test.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--keep-account", action="store_true", help="skip account deletion")
    parser.add_argument("--email", default=f"smoke-{uuid.uuid4().hex[:8]}@example.com")
    args = parser.parse_args(argv)

    base = args.base_url.rstrip("/")
    print(f"\nAutoApply smoke test against {base}\n")

    with httpx.Client(base_url=base, timeout=90, follow_redirects=True) as client:
        run = Run(base_url=base, client=client)
        identity = _run_steps(run, args)

        elapsed = time.perf_counter() - run.started
        print()
        print(f"{'PASSED' if not run.failed else 'FAILED'}  {run.passed} checks, "
              f"{run.failed} failed, {elapsed:.1f}s")
        if run.failed:
            print("Failed: " + ", ".join(run.failures))
        if args.keep_account and identity:
            print(f"\nAccount kept: {identity} — sign in with dev-login to inspect it.")
        return 0 if run.failed == 0 else 1


def _run_steps(run: Run, args) -> str | None:
    c = run.client
    base = run.base_url
    email = args.email
    print("1. Health")

    health = c.get("/health")
    ok = health.status_code == 200 and health.json().get("database") == "ok"
    run.step("GET /health", ok, f"{health.status_code} db={health.json().get('database')}")
    if not ok:
        print("      Is the server running?  uvicorn app.main:app --port 8000")
        return None
    run.info("llm", "enabled" if health.json().get("llm", {}).get("enabled") else "disabled (rules only)")

    print("\n2. Sign in (dev bypass, no Google needed)")
    me = c.post("/api/auth/dev-login", json={"email": email})
    if me.status_code == 404:
        run.step("POST /api/auth/dev-login", False, "404 — needs APP_ENV=development + AUTH_DEV_BYPASS=true")
        return None
    run.step("POST /api/auth/dev-login", me.status_code == 200, f"{me.status_code} {email}")
    run.step("session cookie set", "aa_session" in c.cookies)
    run.step("GET /api/auth/me", c.get("/api/auth/me").status_code == 200)

    print("\n3. Profile and preferences")
    profile = c.put(
        "/api/profile",
        json={
            "full_name": "Priya Sharma",
            "phone": "+91 98765 43210",
            "location": "Pune, India",
            "current_title": "Backend Engineer",
            "current_company": "Acme Systems",
            "years_of_experience": 5,
            "notice_period_days": 60,
            "current_ctc_lpa": 18,
            "expected_ctc_lpa": 24,
            "skills": ["Python", "FastAPI", "PostgreSQL"],
        },
        headers=CSRF,
    )
    run.step("PUT /api/profile", profile.status_code == 200, str(profile.status_code))
    run.step(
        "CSRF header is enforced",
        c.put("/api/profile", json={"full_name": "x"}, headers={"X-Requested-With": ""}).status_code == 403,
    )

    preferences = c.put(
        "/api/preferences",
        json={
            "target_roles": ["Backend Engineer", "Python Developer"],
            "platforms": ["linkedin", "naukri"],
            "locations": ["Pune", "Remote"],
            "work_mode": ["remote", "hybrid"],
            "active_hours": {"start": "00:00", "end": "23:59", "timezone": "Asia/Kolkata"},
            "daily_cap": 10,
        },
        headers=CSRF,
    )
    run.step("PUT /api/preferences", preferences.status_code == 200, str(preferences.status_code))

    onboarding = c.post("/api/onboarding/complete", json={"risk_accepted": True}, headers=CSRF)
    run.step(
        "POST /api/onboarding/complete",
        onboarding.status_code == 200 and onboarding.json()["onboarding"]["done"] is True,
    )

    print("\n4. Resume upload, parsing and signed download")
    body = make_docx()
    upload = c.post("/api/resume", files={"file": ("cv.docx", body, DOCX_MIME)}, headers=CSRF)
    parsed = upload.status_code == 200 and upload.json().get("parse_status") == "parsed"
    run.step("POST /api/resume", parsed, f"{upload.status_code} {upload.json().get('parse_status')}")
    if parsed:
        fields = upload.json()["profile"]
        run.info("parsed name", fields.get("full_name"))
        run.info("parsed years", fields.get("years_of_experience"))
        run.info("confidence", upload.json().get("confidence"))

    file_url = c.get("/api/resume/file-url")
    run.step("GET /api/resume/file-url", file_url.status_code == 200)
    if file_url.status_code == 200:
        url = file_url.json()["url"]
        # Local storage builds an absolute URL from BACKEND_BASE_URL. If the server
        # is not running on that exact origin (common when testing on another port),
        # fetch from the origin we are actually talking to.
        parsed = urlsplit(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin != base:
            print(f"        note: BACKEND_BASE_URL is {origin}; fetching from {base} instead")
            url = f"{base}{parsed.path}" + (f"?{parsed.query}" if parsed.query else "")

        fetched = httpx.get(url, timeout=60, follow_redirects=True)
        run.step(
            "signed URL downloads the file",
            fetched.status_code == 200 and fetched.content == body,
            f"{fetched.status_code}, {len(fetched.content)} bytes",
        )

    print("\n5. Safety and quota")
    safety = c.get("/api/safety/status")
    usage = safety.json().get("usage", {}) if safety.status_code == 200 else {}
    run.step("GET /api/safety/status", safety.status_code == 200)
    run.info("daily cap", usage.get("effective_daily_cap"))
    run.info("warm-up cap", usage.get("warmup_cap"))
    run.info("hourly cap", usage.get("effective_hourly_cap"))
    run.info("reset hour", f"{usage.get('day_reset_hour')}:00 {usage.get('active_timezone')}")
    run.info("quota resets at", usage.get("quota_resets_at"))

    print("\n6. Extension pairing")
    pair = c.post("/api/extension/pair", headers=CSRF)
    run.step("POST /api/extension/pair", pair.status_code == 200)
    code = pair.json()["code"] if pair.status_code == 200 else ""
    run.info("pairing code", code)

    connect = c.post("/api/extension/connect", json={"code": code, "install_id": "smoke-test"})
    run.step("POST /api/extension/connect", connect.status_code == 200)
    token = connect.json().get("token", "") if connect.status_code == 200 else ""
    ext = {"Authorization": f"Bearer {token}"}
    if token:
        run.info("bearer token", token[:14] + "...")

    if token:
        # A second client with no cookies: exactly what a leaked extension token
        # gives an attacker. The signed-in client above would legitimately pass on
        # its session cookie, so this check needs a clean jar.
        with httpx.Client(base_url=base, timeout=30) as anonymous:
            status = anonymous.get("/api/profile", headers=ext).status_code
        run.step("extension token alone cannot read /profile", status == 401, str(status))
    run.step(
        "POST /api/platform/status",
        c.post("/api/platform/status", json={"platform": "linkedin", "signed_in": True}, headers=ext).status_code == 204,
    )

    print("\n7. Start a dry run")
    start = c.post("/api/runs/start", json={"platform": "linkedin", "dry_run": True}, headers=ext)
    if start.status_code == 403:
        reason = start.json()["error"]["message"]
        run.step("POST /api/runs/start", False, reason)
        print("      If this says 'rest day', run with SAFETY_REST_DAY=7 locally.")
        return email
    run.step("POST /api/runs/start", start.status_code == 200)
    if start.status_code != 200:
        return email

    run_id = start.json()["run"]["id"]
    run.info("run id", run_id)
    run.info("max applications this run", start.json()["run"]["max_applications"])
    run.info("heartbeat every", f"{start.json()['heartbeat_seconds']}s")
    run.info("pacing", start.json()["pacing"])

    print("\n8. Agent decisions")
    detail = c.post(
        "/api/agent/step",
        json=observation(
            run_id,
            page_type="job_detail",
            job_id="smoke-1",
            elements=[
                {"ref": "b1", "kind": "button", "label": "Share"},
                {"ref": "b2", "kind": "button", "label": "Easy Apply"},
            ],
        ),
        headers=ext,
    )
    step = detail.json() if detail.status_code == 200 else {}
    run.step(
        "job detail -> click Easy Apply",
        step.get("actions") == [{"type": "click", "ref": "b2"}],
        str(step.get("actions")),
    )

    form = c.post(
        "/api/agent/step",
        json=observation(
            run_id,
            page_type="apply_form",
            job_id="smoke-1",
            elements=[
                {"ref": "f1", "kind": "text", "label": "Full name", "required": True},
                {"ref": "f2", "kind": "text", "label": "Mobile number", "required": True},
                {"ref": "f3", "kind": "text", "label": "Current CTC", "required": True},
                {"ref": "b9", "kind": "button", "label": "Submit application"},
            ],
        ),
        headers=ext,
    )
    form_body = form.json() if form.status_code == 200 else {}
    actions = form_body.get("actions", [])
    values = {a.get("ref"): a.get("value") for a in actions}
    run.step("answers come from the profile", values.get("f1") == "Priya Sharma" and values.get("f3") == "18 LPA", str(values))
    run.step("dry run never submits", all(a["type"] != "submit" for a in actions) and form_body.get("reason") == "dry_run_complete")
    run.step("zero model calls", form_body.get("meta", {}).get("llm_calls") == 0)

    sensitive = c.post(
        "/api/agent/step",
        json=observation(
            run_id,
            page_type="chat_question",
            job_id="smoke-2",
            elements=[{"ref": "b9", "kind": "button", "label": "Next"}],
            chat={"question": "Do you have any disability we should know about?", "input_ref": "c1"},
        ),
        headers=ext,
    )
    sensitive_body = sensitive.json() if sensitive.status_code == 200 else {}
    run.step(
        "sensitive question -> needs a human",
        sensitive_body.get("status") == "hitl" and sensitive_body.get("reason") == "sensitive_question",
        str(sensitive_body.get("reason")),
    )
    run.step("no actions were emitted for the human's form", sensitive_body.get("actions") == [])

    print("\n9. Heartbeat")
    beat = c.post(f"/api/runs/{run_id}/heartbeat", headers=ext)
    run.step("POST /runs/{id}/heartbeat", beat.status_code == 200 and beat.json()["allowed"] is True)

    print("\n10. Ledger")
    ledger = c.get("/api/applications")
    items = ledger.json().get("items", []) if ledger.status_code == 200 else []
    statuses = {item["status"] for item in items}
    run.step("GET /api/applications", ledger.status_code == 200, f"{len(items)} rows")
    run.step("dry run recorded", "dry_run" in statuses, str(sorted(statuses)))
    run.step("stuck job recorded", "needs_attention" in statuses)
    stuck = next((i for i in items if i["status"] == "needs_attention"), None)
    if stuck:
        run.info("stuck reason", stuck.get("reason_label"))
        resolved = c.patch(f"/api/applications/{stuck['id']}", json={"status": "resolved"}, headers=CSRF)
        run.step("PATCH /applications/{id} resolves it", resolved.status_code == 200 and resolved.json()["status"] == "resolved")

    print("\n11. CAPTCHA hard stop and cooldown")
    captcha = c.post(
        "/api/agent/step",
        json=observation(run_id, page_type="job_detail", job_id="smoke-3", signals=["captcha"]),
        headers=ext,
    )
    captcha_body = captcha.json() if captcha.status_code == 200 else {}
    run.step("captcha -> stop", captcha_body.get("status") == "stop", str(captcha_body.get("reason")))

    active = c.get("/api/runs/active").json()
    run.step("run is no longer active", active.get("run") is None)

    blocked = c.post("/api/runs/start", json={"platform": "linkedin", "dry_run": True}, headers=ext)
    run.step(
        "starting again is blocked by the cooldown",
        blocked.status_code == 403 and blocked.json()["error"]["code"] == "policy_blocked",
        blocked.json()["error"]["message"] if blocked.status_code == 403 else str(blocked.status_code),
    )

    print("\n12. Cleanup")
    if args.keep_account:
        run.step("DELETE /api/account", True, "skipped (--keep-account)")
        return email

    deleted = c.delete("/api/account", headers=CSRF)
    run.step("DELETE /api/account", deleted.status_code == 204)
    run.step("session is gone", c.get("/api/auth/me").status_code == 401)
    return None


if __name__ == "__main__":
    raise SystemExit(main())
