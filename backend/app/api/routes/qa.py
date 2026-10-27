"""Saved screening answers.

Editing is in v1 on purpose: a read-only answer list is the difference between a
product you can live with and one that makes you re-do onboarding.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Response, status

from app.api.schemas import QaCreate, QaOut, QaUpdate
from app.core.deps import CurrentUser, DbSession
from app.services import qa_bank

router = APIRouter(prefix="/qa", tags=["qa"])


@router.get("", response_model=list[QaOut])
async def list_answers(user: CurrentUser, db: DbSession) -> list[QaOut]:
    entries = await qa_bank.list_entries(db, user_id=user.id)
    return [QaOut.model_validate(entry) for entry in entries]


@router.post("", response_model=QaOut, status_code=status.HTTP_201_CREATED)
async def create_answer(payload: QaCreate, user: CurrentUser, db: DbSession) -> QaOut:
    entry = await qa_bank.create_entry(
        db,
        user_id=user.id,
        question=payload.question,
        answer=payload.answer,
        sensitive=payload.sensitive,
    )
    return QaOut.model_validate(entry)


@router.patch("/{entry_id}", response_model=QaOut)
async def update_answer(
    entry_id: uuid.UUID, payload: QaUpdate, user: CurrentUser, db: DbSession
) -> QaOut:
    entry = await qa_bank.update_entry(
        db,
        user_id=user.id,
        entry_id=entry_id,
        answer=payload.answer,
        approved=payload.approved,
        sensitive=payload.sensitive,
    )
    return QaOut.model_validate(entry)


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_answer(entry_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Response:
    await qa_bank.delete_entry(db, user_id=user.id, entry_id=entry_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
