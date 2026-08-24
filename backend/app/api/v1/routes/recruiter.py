"""Recruiter routes — the human-review queue (design spec §7).

Recruiter-only (role-gated). Recruiters browse sessions, pull the queue of
answers whose two scoring passes diverged (`needs_review`), and override a
score — which is recorded with the reviewer's id and note for audit.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, require_role
from app.models import Answer, Evaluation, InterviewSession, Question
from app.models.session import SessionState
from app.models.user import UserRole
from app.schemas.interview import (
    EvaluationReviewRead,
    OverrideRequest,
    OverrideResult,
    RecruiterSessionRead,
)

router = APIRouter(
    prefix="/recruiter",
    tags=["recruiter"],
    dependencies=[Depends(require_role(UserRole.recruiter))],
)


@router.get("/sessions", response_model=list[RecruiterSessionRead])
async def list_sessions(
    db: DbSession,
    state: SessionState | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[RecruiterSessionRead]:
    query = select(InterviewSession).order_by(InterviewSession.created_at.desc())
    if state is not None:
        query = query.where(InterviewSession.state == state)
    rows = await db.scalars(query.limit(limit).offset(offset))
    return [RecruiterSessionRead.model_validate(s) for s in rows]


@router.get("/evaluations", response_model=list[EvaluationReviewRead])
async def review_queue(
    db: DbSession,
    needs_review: bool = True,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[EvaluationReviewRead]:
    query = (
        select(Evaluation, Question, Answer)
        .join(Answer, Evaluation.answer_id == Answer.id)
        .join(Question, Answer.question_id == Question.id)
        .order_by(Evaluation.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if needs_review:
        query = query.where(Evaluation.needs_review.is_(True))
    result = await db.execute(query)
    return [
        EvaluationReviewRead(
            id=ev.id,
            answer_id=ev.answer_id,
            topic=q.topic,
            question_text=q.text,
            answer_text=a.text,
            final_score=ev.final_score,
            deterministic_score=ev.deterministic_score,
            confidence=ev.confidence,
            needs_review=ev.needs_review,
            run_count=ev.run_count,
        )
        for ev, q, a in result.all()
    ]


@router.post("/evaluations/{evaluation_id}/override", response_model=OverrideResult)
async def override_evaluation(
    evaluation_id: uuid.UUID,
    payload: OverrideRequest,
    db: DbSession,
    recruiter: CurrentUser,
) -> OverrideResult:
    evaluation = await db.get(Evaluation, evaluation_id)
    if evaluation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Evaluation not found")

    evaluation.final_score = payload.final_score
    evaluation.needs_review = False
    evaluation.overridden_by_id = recruiter.id
    evaluation.override_note = payload.note
    await db.flush()
    return OverrideResult.model_validate(evaluation)
