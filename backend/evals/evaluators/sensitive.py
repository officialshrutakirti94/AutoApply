"""Sensitive-question routing.

Two numbers matter and they pull in opposite directions:

* recall on sensitive questions - a missed one means the agent answers something it
  should have asked a human about;
* false-positive rate on standard ones - over-blocking means CTC and notice-period
  questions, the most common Naukri chat questions, all land in "Needs you".

The plan asks for recall near 100% and a low false-positive rate, so both are
thresholds, not just the first.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.services.answers import detect_sensitive
from evals.evaluators.base import CaseResult, EvalReport

DATASET = Path(__file__).resolve().parents[1] / "datasets" / "sensitive_questions.json"

MIN_RECALL = 0.95
MAX_FALSE_POSITIVE_RATE = 0.10

# These must never be blocked: they are the standard Naukri chat questions.
MUST_NOT_BLOCK = {"n01", "n02", "n05", "n06", "n08", "n15", "n16"}


def load() -> list[dict]:
    return json.loads(DATASET.read_text(encoding="utf-8"))["items"]


def evaluate() -> EvalReport:
    report = EvalReport(
        name="sensitive_routing",
        description="Deterministic sensitive-question routing before any model call.",
        thresholds={
            "sensitive_recall": MIN_RECALL,
            "standard_specificity": 1 - MAX_FALSE_POSITIVE_RATE,
        },
    )

    sensitive_total = sensitive_hit = standard_total = standard_ok = 0

    for item in load():
        flagged_as = detect_sensitive(item["question"])
        predicted_sensitive = flagged_as is not None

        if item["label"] == "sensitive":
            sensitive_total += 1
            if predicted_sensitive:
                sensitive_hit += 1
                report.cases.append(CaseResult(item["id"], True))
            else:
                report.cases.append(
                    CaseResult(
                        item["id"],
                        False,
                        f"missed sensitive ({item['category']}): {item['question']!r}",
                    )
                )
        else:
            standard_total += 1
            if predicted_sensitive:
                must = item["id"] in MUST_NOT_BLOCK
                report.cases.append(
                    CaseResult(
                        item["id"],
                        not must,
                        f"false positive as {flagged_as!r}: {item['question']!r}"
                        + (" (must never be blocked)" if must else ""),
                    )
                )
            else:
                standard_ok += 1
                report.cases.append(CaseResult(item["id"], True))

    report.metrics["sensitive_recall"] = (
        sensitive_hit / sensitive_total if sensitive_total else 0.0
    )
    report.metrics["standard_specificity"] = (
        standard_ok / standard_total if standard_total else 0.0
    )
    return report
