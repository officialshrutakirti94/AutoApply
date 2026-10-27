"""The answer bank.

A screening question is answered once, then reused. Questions are normalised
before storage so "What is your notice period?" and "what is your notice period"
are the same row, which is what keeps the runtime LLM bill near zero.
"""

from __future__ import annotations

import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict, NotFound, Unprocessable
from app.db.enums import QaSource
from app.db.models import QaBankEntry

_PUNCTUATION = re.compile(r"[^a-z0-9\s]")
_WHITESPACE = re.compile(r"\s+")

_PREFIXES = (
    "what is your ",
    "what are your ",
    "whats your ",
    "what s your ",
    "please enter your ",
    "please provide your ",
    "enter your ",
    "do you have a ",
    "do you have an ",
)

FUZZY_MATCH_THRESHOLD = 0.8


def normalize_question(raw: str) -> str:
    text = (raw or "").strip().lower()
    text = _PUNCTUATION.sub(" ", text)
    text = _WHITESPACE.sub(" ", text).strip()
    for prefix in _PREFIXES:
        if text.startswith(prefix):
            text = text[len(prefix) :]
            break
    return text[:500]


def _tokens(text: str) -> set[str]:
    return {token for token in text.split() if len(token) > 2}


def _similarity(left: str, right: str) -> float:
    left_tokens, right_tokens = _tokens(left), _tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


async def list_entries(db: AsyncSession, *, user_id: uuid.UUID) -> list[QaBankEntry]:
    rows = await db.execute(
        select(QaBankEntry)
        .where(QaBankEntry.user_id == user_id)
        .order_by(QaBankEntry.question_pattern)
    )
    return list(rows.scalars())


async def find_entry(db: AsyncSession, *, user_id: uuid.UUID, question: str) -> QaBankEntry | None:
    """Exact normalised match first, then a conservative fuzzy match."""
    normalised = normalize_question(question)
    if not normalised:
        return None

    exact = (
        await db.execute(
            select(QaBankEntry).where(
                QaBankEntry.user_id == user_id,
                QaBankEntry.question_pattern == normalised,
            )
        )
    ).scalar_one_or_none()
    if exact is not None:
        return exact

    approved = list(
        (
            await db.execute(
                select(QaBankEntry).where(
                    QaBankEntry.user_id == user_id, QaBankEntry.approved.is_(True)
                )
            )
        ).scalars()
    )
    best, best_score = None, 0.0
    for entry in approved:
        score = _similarity(normalised, entry.question_pattern)
        if score > best_score:
            best, best_score = entry, score
    if best is not None and best_score >= FUZZY_MATCH_THRESHOLD:
        return best
    return None


async def create_entry(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    question: str,
    answer: str,
    sensitive: bool = False,
    approved: bool = True,
    source: str = QaSource.USER,
) -> QaBankEntry:
    pattern = normalize_question(question)
    if not pattern:
        raise Unprocessable("That question needs at least a couple of words.")

    existing = (
        await db.execute(
            select(QaBankEntry).where(
                QaBankEntry.user_id == user_id, QaBankEntry.question_pattern == pattern
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise Conflict("You already saved an answer for that question.")

    entry = QaBankEntry(
        user_id=user_id,
        question_pattern=pattern,
        answer=answer.strip(),
        source=source,
        approved=approved,
        sensitive=sensitive,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


async def upsert_ai_answer(
    db: AsyncSession, *, user_id: uuid.UUID, question: str, answer: str
) -> QaBankEntry:
    """An AI answer is stored unapproved: it is reused only after the user accepts it."""
    pattern = normalize_question(question)
    entry = (
        await db.execute(
            select(QaBankEntry).where(
                QaBankEntry.user_id == user_id, QaBankEntry.question_pattern == pattern
            )
        )
    ).scalar_one_or_none()

    if entry is None:
        entry = QaBankEntry(
            user_id=user_id,
            question_pattern=pattern,
            answer=answer.strip(),
            source=QaSource.AI,
            approved=False,
            sensitive=False,
        )
        db.add(entry)
    else:
        entry.answer = answer.strip()
        entry.source = QaSource.AI

    await db.commit()
    await db.refresh(entry)
    return entry


async def update_entry(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    entry_id: uuid.UUID,
    answer: str | None = None,
    approved: bool | None = None,
    sensitive: bool | None = None,
) -> QaBankEntry:
    entry = (
        await db.execute(
            select(QaBankEntry).where(QaBankEntry.id == entry_id, QaBankEntry.user_id == user_id)
        )
    ).scalar_one_or_none()
    if entry is None:
        raise NotFound("That answer no longer exists.")

    if answer is not None:
        entry.answer = answer.strip()
        # A human touched it, so it is now their answer, not the agent's guess.
        entry.source = QaSource.USER
    if approved is not None:
        entry.approved = approved
    if sensitive is not None:
        entry.sensitive = sensitive

    await db.commit()
    await db.refresh(entry)
    return entry


async def mark_used(db: AsyncSession, entry: QaBankEntry) -> None:
    entry.times_used += 1
    await db.commit()


async def delete_entry(db: AsyncSession, *, user_id: uuid.UUID, entry_id: uuid.UUID) -> None:
    entry = (
        await db.execute(
            select(QaBankEntry).where(QaBankEntry.id == entry_id, QaBankEntry.user_id == user_id)
        )
    ).scalar_one_or_none()
    if entry is None:
        raise NotFound("That answer no longer exists.")
    await db.delete(entry)
    await db.commit()
