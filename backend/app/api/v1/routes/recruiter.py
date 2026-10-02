"""Recruiter routes — the human-review queue (design spec §7).

Recruiter-only (role-gated). Recruiters browse sessions, pull the queue of
answers whose two scoring passes diverged (`needs_review`), and override a
score — which is recorded with the reviewer's id and note for audit.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession, require_role
from app.core.config import settings
from app.models import (
    Answer,
    Evaluation,
    InterviewSession,
    LLMCall,
    Question,
    Report,
    User,
)
from app.models.session import SessionState
from app.models.user import UserRole
from app.schemas.interview import (
    AnswerDetail,
    CostSummary,
    EvaluationDetail,
    EvaluationReviewPage,
    EvaluationReviewRead,
    IntegritySignalRead,
    LLMCallRead,
    OverrideRequest,
    OverrideResult,
    QuestionDetail,
    RecruiterSessionDetail,
    RecruiterSessionRead,
)
from app.services.budget import utc_day_start
from app.services.integrity import assess, flagged_sessions
from app.services.pipeline import rebuild_report
from app.services.reports import pdf_response, render_session_pdf, to_report_read

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
    query = (
        select(InterviewSession, User.email)
        .join(User, InterviewSession.user_id == User.id)
        .order_by(InterviewSession.created_at.desc())
    )
    if state is not None:
        query = query.where(InterviewSession.state == state)
    rows = (await db.execute(query.limit(limit).offset(offset))).all()
    flagged = await flagged_sessions(db, (s.id for s, _ in rows))
    return [
        RecruiterSessionRead(
            id=s.id,
            user_id=s.user_id,
            candidate_email=email,
            state=s.state,
            created_at=s.created_at,
            integrity_flag=s.id in flagged,
        )
        for s, email in rows
    ]


@router.get("/sessions/{session_id}", response_model=RecruiterSessionDetail)
async def session_detail(session_id: uuid.UUID, db: DbSession) -> RecruiterSessionDetail:
    """One interview end to end: candidate, every question with its answers
    and their grades, and the report if there is one."""
    row = (
        await db.execute(
            select(InterviewSession, User.email)
            .join(User, InterviewSession.user_id == User.id)
            .where(InterviewSession.id == session_id)
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    session, email = row

    questions = list(
        await db.scalars(
            select(Question)
            .where(Question.session_id == session_id)
            .order_by(Question.ordinal)
        )
    )
    # Answers joined to their (optional) evaluation, for all questions at once.
    answer_rows = (
        await db.execute(
            select(Answer, Evaluation)
            .join(Question, Answer.question_id == Question.id)
            .outerjoin(Evaluation, Evaluation.answer_id == Answer.id)
            .where(Question.session_id == session_id)
            .order_by(Answer.submitted_at)
        )
    ).all()
    answers_by_question: dict[uuid.UUID, list[AnswerDetail]] = {}
    integrity_flag = False
    for answer, evaluation in answer_rows:
        detail = AnswerDetail.model_validate(answer)
        if evaluation is not None:
            detail.evaluation = EvaluationDetail.model_validate(evaluation)
        detail.integrity = [IntegritySignalRead.model_validate(s) for s in assess(answer)]
        integrity_flag = integrity_flag or bool(detail.integrity)
        answers_by_question.setdefault(answer.question_id, []).append(detail)

    report = await db.scalar(select(Report).where(Report.session_id == session_id))
    return RecruiterSessionDetail(
        id=session.id,
        user_id=session.user_id,
        candidate_email=email,
        state=session.state,
        created_at=session.created_at,
        expires_at=session.expires_at,
        failure_reason=session.failure_reason,
        questions=[
            QuestionDetail(
                id=q.id,
                ordinal=q.ordinal,
                topic=q.topic,
                difficulty=q.difficulty,
                text=q.text,
                expected_concepts=q.expected_concepts or [],
                answers=answers_by_question.get(q.id, []),
            )
            for q in questions
        ],
        report=await to_report_read(db, report) if report is not None else None,
        integrity_flag=integrity_flag,
    )


@router.get(
    "/sessions/{session_id}/report.pdf",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def session_report_pdf(session_id: uuid.UUID, db: DbSession) -> Response:
    """The recruiter's copy: adds the candidate's email and integrity signals."""
    row = (
        await db.execute(
            select(InterviewSession, User.email)
            .join(User, InterviewSession.user_id == User.id)
            .where(InterviewSession.id == session_id)
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    session, email = row
    report = await db.scalar(select(Report).where(Report.session_id == session_id))
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not ready")
    pdf = await render_session_pdf(
        db, session, report, candidate_email=email, include_integrity=True
    )
    return pdf_response(pdf, session.id)


@router.get("/evaluations", response_model=EvaluationReviewPage)
async def review_queue(
    db: DbSession,
    needs_review: bool = True,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> EvaluationReviewPage:
    base = (
        select(Evaluation, Question, Answer, User.email)
        .join(Answer, Evaluation.answer_id == Answer.id)
        .join(Question, Answer.question_id == Question.id)
        .join(InterviewSession, Question.session_id == InterviewSession.id)
        .join(User, InterviewSession.user_id == User.id)
    )
    if needs_review:
        base = base.where(Evaluation.needs_review.is_(True))

    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    result = await db.execute(
        base.order_by(Evaluation.created_at.desc()).limit(limit).offset(offset)
    )
    return EvaluationReviewPage(
        total=total or 0,
        items=[
            EvaluationReviewRead(
                id=ev.id,
                answer_id=ev.answer_id,
                session_id=q.session_id,
                candidate_email=email,
                topic=q.topic,
                question_text=q.text,
                answer_text=a.text,
                final_score=ev.final_score,
                deterministic_score=ev.deterministic_score,
                confidence=ev.confidence,
                needs_review=ev.needs_review,
                run_count=ev.run_count,
            )
            for ev, q, a, email in result.all()
        ],
    )


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

    # The report is a rollup of final scores, so it is stale the moment one
    # changes. Rebuild it now — and let the session leave review once nothing
    # in it is still flagged.
    session_id = await db.scalar(
        select(Question.session_id)
        .join(Answer, Answer.question_id == Question.id)
        .where(Answer.id == evaluation.answer_id)
    )
    session_state = None
    if session_id is not None:
        await rebuild_report(db, session_id)
        session_state = (await db.get(InterviewSession, session_id)).state

    result = OverrideResult.model_validate(evaluation)
    result.session_state = session_state
    return result


@router.get("/costs", response_model=CostSummary)
async def costs(
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 25,
) -> CostSummary:
    """Today's spend across *all* users, plus the tail of the ledger.

    These are organisation-wide totals. `daily_token_budget` is the
    *per-user* cap the 429 enforces (each user's own rows, summed by
    `services/budget.py`), included for scale — the org total is expected to
    exceed it once more than a handful of people have interviewed.
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
