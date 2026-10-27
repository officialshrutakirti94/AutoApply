"""Optional LangSmith tracing.

Tracing is free on the developer tier and always worth having in development. It
is off unless both ``LANGSMITH_TRACING=true`` and a key are present, and the app
behaves identically without it.
"""

from __future__ import annotations

from typing import Any, Callable

from app.core.config import settings


def traceable(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        if not (settings.langsmith_tracing and settings.langsmith_api_key):
            return func
        try:
            from langsmith import traceable as langsmith_traceable
        except ImportError:  # optional dependency
            return func
        return langsmith_traceable(run_type="chain", name=name)(func)

    return decorator
