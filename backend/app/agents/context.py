"""Everything a graph node is allowed to touch, injected per step.

Nodes are pure-ish functions over this context plus the graph state, which makes
each one testable without a running server.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentRun, Preference, Profile


@dataclass(slots=True)
class StepContext:
    db: AsyncSession
    user_id: uuid.UUID
    run: AgentRun
    profile: Profile | None
    preferences: Preference | None
    llm_calls_left: int
    dry_run: bool

    @property
    def target_roles(self) -> list[str]:
        return list(self.preferences.target_roles) if self.preferences else []

    @property
    def blacklist_companies(self) -> list[str]:
        return list(self.preferences.blacklist_companies) if self.preferences else []

    @property
    def blacklist_keywords(self) -> list[str]:
        return list(self.preferences.blacklist_keywords) if self.preferences else []
