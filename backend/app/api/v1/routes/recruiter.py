"""Recruiter routes — the human-review queue (design spec §7).

Recruiter-only (role-gated). Recruiters browse sessions, pull the queue of
answers whose two scoring passes diverged (`needs_review`), and override a
score — which is recorded with the reviewer's id and note for audit.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession, require_role
from app.core.config import settings
from app.models import Answer, Evaluation, InterviewSession, LLMCall, Question
from app.models.session import SessionState
from app.models.user import UserRole
from app.schemas.interview import (
    CostSummary,
    EvaluationReviewRead,
    LLMCallRead,
    OverrideRequest,
    OverrideResult,
    RecruiterSessionRead,
)
from app.services.budget import utc_day_start

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


@router.get("/costs", response_model=CostSummary)
async def costs(
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 25,
) -> CostSummary:
    """Today's spend plus the tail of the ledger.

    Read-only view over the same `LLMCall` rows the budget guard sums, so the
    number a recruiter sees here is the number that gates the 429.
    """
    day_start = utc_day_start()
    totals = (
        await db.execute(
            select(
                func.coalesce(
                    func.sum(LLMCall.prompt_tokens + LLMCall.completion_tokens), 0
                ),
                func.coalesce(func.sum(LLMCall.cost_estimate), 0.0),
                func.count(LLMCall.id),
            ).where(LLMCall.created_at >= day_start)
        )
    ).one()
    failed = await db.scalar(
        select(func.count(LLMCall.id)).where(
            LLMCall.created_at >= day_start, LLMCall.status != "ok"
        )
    )
    recent = await db.scalars(
        select(LLMCall).order_by(LLMCall.created_at.desc()).limit(limit)
    )
    return CostSummary(
        tokens_today=int(totals[0] or 0),
        spend_today=float(totals[1] or 0.0),
        calls_today=int(totals[2] or 0),
        failed_today=int(failed or 0),
        daily_token_budget=settings.USER_DAILY_TOKEN_BUDGET,
        recent=[LLMCallRead.model_validate(row) for row in recent],
    )
