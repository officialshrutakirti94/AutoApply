"""Eval registry and runner.

    python -m evals.run                # every suite, human readable
    python -m evals.run sensitive      # one suite
    python -m evals.run --json         # machine readable, for CI
    python -m evals.run --list

Exits non-zero when any suite fails, so it can gate a merge.

None of these call a model: they are deterministic, free and fast. That is
deliberate. Model quality is compared separately (Groq vs Nemotron) by running the
same datasets through ``LLM_ENABLED=true`` with a key present.
"""

from __future__ import annotations

import argparse
import json
import sys

from evals.evaluators import groundedness, injection, resume, sensitive
from evals.evaluators.base import EvalReport

SUITES = {
    "sensitive": sensitive.evaluate,
    "injection": injection.evaluate,
    "groundedness": groundedness.evaluate,
    "resume": resume.evaluate,
}

ORDER = ["sensitive", "injection", "groundedness", "resume"]


def run_suites(names: list[str] | None = None) -> list[EvalReport]:
    selected = names or ORDER
    unknown = [name for name in selected if name not in SUITES]
    if unknown:
        raise SystemExit(f"Unknown suite(s): {', '.join(unknown)}. Try --list.")

    reports: list[EvalReport] = []
    for name in selected:
        reports.append(SUITES[name]())
    return reports


def _print_human(reports: list[EvalReport]) -> None:
    for report in reports:
        status = "PASS" if report.ok else "FAIL"
        print(f"\n{status}  {report.name}  ({report.passed}/{report.total} cases)")
        print(f"      {report.description}")
        for key, value in report.metrics.items():
            threshold = report.thresholds.get(key)
            if threshold is None:
                print(f"      {key} = {value}")
                continue
            mark = "ok" if value >= threshold else "BELOW"
            print(f"      {key} = {value:.3f}  (min {threshold:.2f}) {mark}")
        for failure in report.failures:
            print(f"      x {failure.case_id}: {failure.detail}")

    total = sum(report.total for report in reports)
    passed = sum(report.passed for report in reports)
    overall = "PASS" if all(report.ok for report in reports) else "FAIL"
    print(f"\n{overall}  {passed}/{total} cases across {len(reports)} suites")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the AutoApply eval suites.")
    parser.add_argument("suites", nargs="*", help="subset of suites to run")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--list", action="store_true", help="list available suites")
    args = parser.parse_args(argv)

    if args.list:
        for name in ORDER:
            print(name)
        return 0

    reports = run_suites(args.suites or None)

    if args.json:
        print(json.dumps([report.as_dict() for report in reports], indent=2))
    else:
        _print_human(reports)

    return 0 if all(report.ok for report in reports) else 1


if __name__ == "__main__":
    sys.exit(main())
