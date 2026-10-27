"""Shared types for the eval suites."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class CaseResult:
    case_id: str
    passed: bool
    detail: str = ""


@dataclass(slots=True)
class EvalReport:
    name: str
    description: str
    cases: list[CaseResult] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)
    thresholds: dict[str, float] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return len(self.cases)

    @property
    def passed(self) -> int:
        return sum(1 for case in self.cases if case.passed)

    @property
    def failures(self) -> list[CaseResult]:
        return [case for case in self.cases if not case.passed]

    @property
    def metrics_ok(self) -> bool:
        return all(self.metrics.get(key, 0.0) >= value for key, value in self.thresholds.items())

    @property
    def ok(self) -> bool:
        return not self.failures and self.metrics_ok

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "total": self.total,
            "passed": self.passed,
            "ok": self.ok,
            "metrics": self.metrics,
            "thresholds": self.thresholds,
            "failures": [
                {"id": case.case_id, "detail": case.detail} for case in self.failures
            ],
        }
