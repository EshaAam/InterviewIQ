"""Session routes — the candidate interview flow.

Every stage that touches the pipeline returns quickly and hands work to the
dispatcher; none block on an LLM call (design doc §7). State is driven only
through `SessionService`, and the interview deadline is enforced server-side.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbSession, require_budget
from app.core.config import settings
from app.models import (
    Answer,
    InterviewSession,
    Question,
    Report,
    Resume,
    SessionState,
)
from app.schemas.interview import (
    AnswerCreate,
    AnswerRead,
    QuestionRead,
    ReportRead,
    SessionCreate,
    SessionRead,
    SessionSummary,
)
from app.services.reports import pdf_response, render_session_pdf, to_report_read
from app.services.session_service import IllegalTransition, SessionService
from app.workers.dispatch import PipelineDispatcher, get_dispatcher

router = APIRouter(prefix="/sessions", tags=["sessions"])

Dispatcher = Annotated[PipelineDispatcher, Depends(get_dispatcher)]


async def _load_owned_session(
    db: DbSession, user_id: uuid.UUID, session_id: uuid.UUID
) -> InterviewSession:
    session = await db.get(InterviewSession, session_id)
    if session is None or session.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    # Enforce the deadline on every read/write touchpoint.
    SessionService.maybe_expire(session)
    return session


async def _to_read(db: DbSession, session: InterviewSession) -> SessionRead:
    total = await db.scalar(
        select(func.count(Question.id)).where(Question.session_id == session.id)
    )
    answered = await db.scalar(
        select(func.count(Answer.id))
        .select_from(Answer)
        .join(Question, Answer.question_id == Question.id)
        .where(Question.session_id == session.id)
    )
    return SessionRead(
        id=session.id,
        state=session.state,
        expires_at=session.expires_at,
        failure_reason=session.failure_reason,
        answered=answered or 0,
        total_questions=total or 0,
    )


@router.post("", response_model=SessionRead, status_code=status.HTTP_202_ACCEPTED)
async def create_session(
    payload: SessionCreate,
    db: DbSession,
    user: CurrentUser,
    dispatcher: Dispatcher,
    _budget: Annotated[None, Depends(require_budget)] = None,
) -> SessionRead:
    resume = await db.get(Resume, payload.resume_id)
    if resume is None or resume.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Resume not found")

    session = InterviewSession(user_id=user.id, resume_id=resume.id)
    db.add(session)
    # Commit, *then* dispatch. A worker is a different connection: if the task
    # were enqueued first, a fast worker could look for this row before our
    # transaction commits, find nothing, and drop the job — leaving the
    # session in CREATED forever. (If the publish itself fails after the
    # commit, the reaper re-dispatches the session later.)
    await db.commit()
    await dispatcher.generate_questions(session.id)
    return await _to_read(db, session)


@router.get("", response_model=list[SessionSummary])
async def list_my_sessions(
    db: DbSession,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[SessionSummary]:
    """The signed-in user's own interviews, newest first."""
    sessions = list(
        await db.scalars(
            select(InterviewSession)
            .where(InterviewSession.user_id == user.id)
            .order_by(InterviewSession.created_at.desc())
            .limit(limit)
        )
    )
    if not sessions:
        return []
    ids = [s.id for s in sessions]

    # Three grouped queries for the whole page, not three per row.
    totals = dict(
        (
            await db.execute(
                select(Question.session_id, func.count(Question.id))
                .where(Question.session_id.in_(ids))
                .group_by(Question.session_id)
            )
        ).all()
    )
    answered = dict(
        (
            await db.execute(
                select(Question.session_id, func.count(Answer.id))
                .join(Answer, Answer.question_id == Question.id)
                .where(Question.session_id.in_(ids))
                .group_by(Question.session_id)
            )
        ).all()
    )
    overall = dict(
        (
            await db.execute(
                select(Report.session_id, Report.overall).where(
                    Report.session_id.in_(ids)
                )
            )
        ).all()
    )

    rows = []
    for session in sessions:
        # Same lazy deadline as every other read, so the list never shows an
        # interview as IN_PROGRESS after its time is up.
        SessionService.maybe_expire(session)
        rows.append(
            SessionSummary(
                id=session.id,
                state=session.state,
                expires_at=session.expires_at,
                failure_reason=session.failure_reason,
                answered=answered.get(session.id, 0),
                total_questions=totals.get(session.id, 0),
                created_at=session.created_at,
                overall=overall.get(session.id),
            )
        )
    return rows


@router.get("/{session_id}", response_model=SessionRead)
async def get_session(
    session_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> SessionRead:
    session = await _load_owned_session(db, user.id, session_id)
    return await _to_read(db, session)


@router.post("/{session_id}/start", response_model=SessionRead)
async def start_session(
    session_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> SessionRead:
    session = await _load_owned_session(db, user.id, session_id)
    if session.state != SessionState.READY:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Session is {session.state.value}, not READY",
        )
    session.expires_at = datetime.now(UTC) + timedelta(
        minutes=settings.SESSION_TTL_MINUTES
    )
    SessionService.transition(session, SessionState.IN_PROGRESS)
    return await _to_read(db, session)


@router.get("/{session_id}/questions/next", response_model=QuestionRead)
async def next_question(
    session_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> QuestionRead:
    session = await _load_owned_session(db, user.id, session_id)
    if session.state != SessionState.IN_PROGRESS:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Session is {session.state.value}, not IN_PROGRESS"
        )

    answered_subq = (
        select(Answer.question_id)
        .join(Question, Answer.question_id == Question.id)
        .where(Question.session_id == session_id)
    )
    question = await db.scalar(
        select(Question)
        .where(Question.session_id == session_id, Question.id.notin_(answered_subq))
        .order_by(Question.ordinal)
        .limit(1)
    )
    if question is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No more questions")
    return QuestionRead.model_validate(question)


@router.post(
    "/{session_id}/answers",
    response_model=AnswerRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_answer(
    session_id: uuid.UUID,
    payload: AnswerCreate,
    db: DbSession,
    user: CurrentUser,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> AnswerRead:
    # No budget guard: storing an answer spends nothing, and an interview
    # already under way may always be completed (see services/budget.py).
    session = await _load_owned_session(db, user.id, session_id)
    if session.state != SessionState.IN_PROGRESS:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Session is {session.state.value}, not IN_PROGRESS"
        )

    question = await db.get(Question, payload.question_id)
    if question is None or question.session_id != session_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Question not found")

    # Idempotent: same (question, key) returns the existing answer, no new row.
    existing = await db.scalar(
        select(Answer).where(
            Answer.question_id == payload.question_id,
            Answer.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        return AnswerRead.model_validate(existing)

    answer = Answer(
        question_id=payload.question_id,
        text=payload.text,
        idempotency_key=idempotency_key,
        time_taken_ms=payload.time_taken_ms,
        paste_events=payload.paste_events,
        keystroke_count=payload.keystroke_count,
    )
    db.add(answer)
    try:
        await db.flush()
    except IntegrityError:
        # Concurrent duplicate submission raced us; return the row that won.
        await db.rollback()
        winner = await db.scalar(
            select(Answer).where(
                Answer.question_id == payload.question_id,
                Answer.idempotency_key == idempotency_key,
            )
        )
        if winner is None:
            raise
        return AnswerRead.model_validate(winner)

    # Evaluation happens once, in the EVALUATING phase (build_report), not here —
    # evaluating on submit would race build_report on the same answer.
    return AnswerRead.model_validate(answer)


@router.post("/{session_id}/finish", response_model=SessionRead)
async def finish_session(
    session_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
    dispatcher: Dispatcher,
) -> SessionRead:
    # No budget guard here either: a candidate who crosses the cap mid-interview
    # can still finish. The overshoot is bounded by one interview's grading.
    session = await _load_owned_session(db, user.id, session_id)
    try:
        SessionService.transition(session, SessionState.EVALUATING)
    except IllegalTransition:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Cannot finish from {session.state.value}",
        ) from None
    await db.commit()  # commit, then dispatch — see create_session
    await dispatcher.build_report(session.id)
    return await _to_read(db, session)


@router.get("/{session_id}/report", response_model=ReportRead)
async def get_report(
    session_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> ReportRead:
    session = await _load_owned_session(db, user.id, session_id)
    report = await db.scalar(select(Report).where(Report.session_id == session.id))
    if report is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Report not ready"
        )
    return await to_report_read(db, report)


@router.get(
    "/{session_id}/report.pdf",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def get_report_pdf(
    session_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> Response:
    """The candidate's copy: scores, strengths, gaps — no integrity section."""
    session = await _load_owned_session(db, user.id, session_id)
    report = await db.scalar(select(Report).where(Report.session_id == session.id))
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not ready")
    pdf = await render_session_pdf(db, session, report)
    return pdf_response(pdf, session.id)
