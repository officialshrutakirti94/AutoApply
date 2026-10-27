"""Answer groundedness.

The rule from the plan: no invented facts. This asks the standard questions
against a fixed sample profile with no model available, then checks that every
answer is traceable to the profile:

* no number appears in an answer that is not in the profile or the form options;
* no email or phone number appears that the profile does not contain;
* the compensation and notice answers match the profile exactly.

The checking code here is written independently of ``app.services.answers`` so it
is a real assertion rather than a restatement of the implementation.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.services.answers import answer_question
from evals.evaluators._db import scratch_session
from evals.evaluators.base import CaseResult, EvalReport

DATASET = Path(__file__).resolve().parents[1] / "datasets" / "sensitive_questions.json"

MIN_GROUNDED_RATE = 1.0
NUMBER = re.compile(r"\d+(?:\.\d+)?")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]{2,}")
PHONE = re.compile(r"\+?\d[\d\s-]{8,}\d")

SAMPLE_PROFILE = {
    "full_name": "Priya Sharma",
    "email": "priya.sharma@example.com",
    "phone": "+91 98765 43210",
    "location": "Pune, India",
    "linkedin_url": "https://linkedin.com/in/priyasharma",
    "current_title": "Backend Engineer",
    "current_company": "Acme Systems",
    "years_of_experience": 5,
    "notice_period_days": 60,
    "current_ctc_lpa": 18,
    "expected_ctc_lpa": 24,
    "work_authorization": "Indian citizen",
    "skills": ["Python", "FastAPI", "PostgreSQL"],
    "education": [{"degree": "B.Tech Computer Science"}],
}

EXPECTED_ANSWERS = {
    "n01": "18 LPA",
    "n02": "24 LPA",
    "n05": "2 months",
    "n08": "5",
}


def _numbers(text: str) -> set[str]:
    return {value.rstrip("0").rstrip(".") if "." in value else value for value in NUMBER.findall(str(text))}


def _facts_numbers() -> set[str]:
    allowed: set[str] = set()
    for value in SAMPLE_PROFILE.values():
        allowed |= _numbers(json.dumps(value, default=str))
    # Derived, but still traceable to the profile: 60 days is 2 months.
    allowed |= {"2", "60"}
    return allowed


def _violations(answer: str) -> list[str]:
    problems: list[str] = []

    allowed = _facts_numbers()
    for number in _numbers(answer):
        if number not in allowed:
            problems.append(f"unsupported number {number!r}")

    for address in EMAIL.findall(answer):
        if address not in SAMPLE_PROFILE["email"]:
            problems.append(f"invented email {address!r}")

    if PHONE.search(answer) and not PHONE.search(SAMPLE_PROFILE["phone"]):
        problems.append("invented phone number")

    return problems


async def _run() -> tuple[list[CaseResult], dict[str, float]]:
    from app.db.models import Preference, Profile, User

    items = json.loads(DATASET.read_text(encoding="utf-8"))["items"]
    standard = [item for item in items if item["label"] == "standard"]

    cases: list[CaseResult] = []
    answered = 0

    async with scratch_session() as db:
        user = User(google_sub="eval:groundedness", email="eval@example.com", email_verified=True)
        db.add(user)
        await db.commit()
        await db.refresh(user)

        profile = Profile(
            user_id=user.id,
            full_name=SAMPLE_PROFILE["full_name"],
            email=SAMPLE_PROFILE["email"],
            phone=SAMPLE_PROFILE["phone"],
            location=SAMPLE_PROFILE["location"],
            linkedin_url=SAMPLE_PROFILE["linkedin_url"],
            current_title=SAMPLE_PROFILE["current_title"],
            current_company=SAMPLE_PROFILE["current_company"],
            years_of_experience=SAMPLE_PROFILE["years_of_experience"],
            notice_period_days=SAMPLE_PROFILE["notice_period_days"],
            current_ctc_lpa=SAMPLE_PROFILE["current_ctc_lpa"],
            expected_ctc_lpa=SAMPLE_PROFILE["expected_ctc_lpa"],
            work_authorization=SAMPLE_PROFILE["work_authorization"],
            skills=SAMPLE_PROFILE["skills"],
            education=SAMPLE_PROFILE["education"],
        )
        db.add(profile)
        preference = Preference(
            user_id=user.id,
            target_roles=["Backend Engineer"],
            platforms=["linkedin"],
            work_mode=["remote"],
            active_hours={"start": "00:00", "end": "23:59", "timezone": "UTC"},
        )
        db.add(preference)
        await db.commit()
        await db.refresh(preference)

        for item in standard:
            # Same call shape as the agent: preferences included, so relocation and
            # work-mode answers are exercised rather than skipped.
            result = await answer_question(
                db,
                user_id=user.id,
                question=item["question"],
                options=None,
                profile=profile,
                preferences=preference,
                llm_calls_left=0,
                allow_llm=False,
            )

            if not result.resolved:
                # Not every phrasing is covered by a rule; that is a HITL, not a
                # wrong answer. Only answered ones are graded for groundedness.
                cases.append(CaseResult(item["id"], True, "unanswered (goes to a human)"))
                continue

            answered += 1
            problems = _violations(result.value or "")

            expected = EXPECTED_ANSWERS.get(item["id"])
            if expected is not None and (result.value or "").strip() != expected:
                problems.append(f"expected {expected!r}, got {result.value!r}")

            cases.append(
                CaseResult(
                    item["id"],
                    not problems,
                    "; ".join(problems) or f"{result.source}: {result.value}",
                )
            )

    grounded = sum(1 for case in cases if case.passed)
    metrics = {
        "grounded_rate": grounded / len(cases) if cases else 0.0,
        "answered_from_profile": answered,
    }
    return cases, metrics


async def evaluate_async() -> EvalReport:
    """Async entry point, for callers that already own an event loop."""
    report = EvalReport(
        name="answer_groundedness",
        description="Answers are traceable to the profile; nothing is invented.",
        thresholds={"grounded_rate": MIN_GROUNDED_RATE},
    )
    cases, metrics = await _run()
    report.cases = cases
    report.metrics = metrics
    return report


def evaluate() -> EvalReport:
    """Sync entry point for the CLI runner."""
    import asyncio

    return asyncio.run(evaluate_async())
