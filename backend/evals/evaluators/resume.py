"""Resume parsing accuracy.

Tracked per change: the heuristic parser must keep recovering the fields it
already recovers, and the parser must never invent a value it cannot see. This
runs with no model available, which is also the rules-only mode users get when no
API key is configured.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.resume.parse import heuristic_parse
from evals.evaluators.base import CaseResult, EvalReport

DATASET_DIR = Path(__file__).resolve().parents[1] / "datasets"
MANIFEST = DATASET_DIR / "resumes.json"

MIN_FIELD_ACCURACY = 0.95


def _check(parsed, expected: dict) -> list[str]:
    problems: list[str] = []

    if "full_name" in expected and parsed.full_name != expected["full_name"]:
        problems.append(f"full_name: expected {expected['full_name']!r}, got {parsed.full_name!r}")

    if "email" in expected and (parsed.email or "").lower() != expected["email"]:
        problems.append(f"email: expected {expected['email']!r}, got {parsed.email!r}")

    if "years_of_experience" in expected:
        want = expected["years_of_experience"]
        got = parsed.years_of_experience
        if want is None:
            if got is not None:
                problems.append(f"years: expected none, got {got}")
        elif got is None or abs(float(got) - float(want)) > 0.51:
            problems.append(f"years: expected {want}, got {got}")

    if "location_contains" in expected:
        needle = expected["location_contains"].lower()
        if needle not in (parsed.location or "").lower():
            problems.append(f"location: expected to contain {needle!r}, got {parsed.location!r}")

    if "skills_include" in expected:
        have = {skill.lower() for skill in parsed.skills}
        missing = [skill for skill in expected["skills_include"] if skill not in have]
        if missing:
            problems.append(f"skills missing: {missing}")

    if expected.get("linkedin") is True and not parsed.linkedin_url:
        problems.append("linkedin: expected a URL, got none")
    if expected.get("linkedin") is False and parsed.linkedin_url:
        problems.append(f"linkedin: expected none, got {parsed.linkedin_url!r}")

    return problems


def evaluate() -> EvalReport:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    report = EvalReport(
        name="resume_parsing",
        description="Deterministic resume parsing, tracked per change.",
        thresholds={"field_accuracy": MIN_FIELD_ACCURACY},
    )

    fields_checked = fields_ok = 0

    for item in manifest["items"]:
        path = DATASET_DIR / "resumes" / item["file"]
        parsed = heuristic_parse(path.read_text(encoding="utf-8"))
        expected = item["expected"]

        problems = _check(parsed, expected)
        fields_checked += len(expected)
        fields_ok += len(expected) - len(problems)

        report.cases.append(
            CaseResult(
                item["file"],
                not problems,
                "; ".join(problems) or f"name={parsed.full_name!r} years={parsed.years_of_experience}",
            )
        )

    report.metrics["field_accuracy"] = fields_ok / fields_checked if fields_checked else 0.0
    report.metrics["resumes"] = float(len(manifest["items"]))
    return report
