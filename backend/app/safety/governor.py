"""Human-like pacing.

Randomised delays are what keep a run from looking mechanical. Every value is
clamped by a floor so no configuration can turn the loop into a spammer, and the
extension applies the same floor locally before it acts.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from app.core.config import settings

MIN_ACTION_DELAY_MS = 250
MAX_CONSECUTIVE_ERRORS = 3


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(value, high))


def action_delay_ms() -> int:
    """Delay before a single interaction (typing, click, scroll)."""
    low = max(settings.safety_action_delay_min_ms, MIN_ACTION_DELAY_MS)
    high = max(settings.safety_action_delay_max_ms, low)
    delay = random.randint(low, high)
    # Occasional hesitation, the way a person pauses when reading a form.
    if random.random() < 0.15:
        delay += random.randint(600, 2400)
    return delay


def apply_pause_s() -> int:
    """Pause between two applications."""
    low = max(settings.safety_apply_pause_min_s, 30)
    high = max(settings.safety_apply_pause_max_s, low)
    return random.randint(low, high)


def long_break_s(applications_this_run: int) -> int | None:
    """Every N applications the run takes a real break."""
    every = max(settings.safety_long_break_every_n, 1)
    if applications_this_run <= 0 or applications_this_run % every != 0:
        return None
    low = max(settings.safety_long_break_min_s, 60)
    high = max(settings.safety_long_break_max_s, low)
    return random.randint(low, high)


def enforce_floor(delay_ms: int) -> int:
    """Used by the extension: never act faster than the floor, whatever it is told."""
    return _clamp(delay_ms, MIN_ACTION_DELAY_MS, 30_000)


def reached_error_limit(consecutive_errors: int) -> bool:
    return consecutive_errors >= MAX_CONSECUTIVE_ERRORS


@dataclass(frozen=True, slots=True)
class PacingPlan:
    action_delay_ms: int
    apply_pause_s: int | None
    long_break_s: int | None

    def as_dict(self) -> dict:
        return {
            "action_delay_ms": self.action_delay_ms,
            "apply_pause_s": self.apply_pause_s,
            "long_break_s": self.long_break_s,
        }


def next_pause(applications_this_run: int) -> PacingPlan:
    return PacingPlan(
        action_delay_ms=action_delay_ms(),
        apply_pause_s=apply_pause_s(),
        long_break_s=long_break_s(applications_this_run),
    )
