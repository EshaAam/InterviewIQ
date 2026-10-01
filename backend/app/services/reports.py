"""Read-side helpers for reports (JSON and PDF), shared by the candidate and
recruiter routes."""

from __future__ import annotations

import uuid

from fastapi import Response
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Answer, Evaluation, InterviewSession, Question, Report
from app.schemas.interview import ReportRead
from app.services.integrity import assess
from app.services.report_pdf import IntegrityLine, ReportPdfData, render_report_pdf


async def was_human_reviewed(db: AsyncSession, session_id: uuid.UUID) -> bool:
    """True if a recruiter has overridden any evaluation in the session."""
    hit = await db.scalar(
        select(Evaluation.id)
        .join(Answer, Evaluation.answer_id == Answer.id)
        .join(Question, Answer.question_id == Question.id)
        .where(
            Question.session_id == session_id,
            Evaluation.overridden_by_id.is_not(None),
        )
        .limit(1)
    )
    return hit is not None


async def to_report_read(db: AsyncSession, report: Report) -> ReportRead:
    read = ReportRead.model_validate(report)
    read.human_reviewed = await was_human_reviewed(db, report.session_id)
    return read


async def render_session_pdf(
    db: AsyncSession,
    session: InterviewSession,
    report: Report,
    *,
    candidate_email: str | None = None,
    include_integrity: bool = False,
) -> bytes:
    """Gather what the PDF shows, then draw it off the event loop.

    `include_integrity` is the recruiter's copy. The candidate's copy leaves
    the section out entirely rather than showing an empty one.
    """
    integrity: list[IntegrityLine] | None = None
    if include_integrity:
        rows = await db.execute(
            select(Question.ordinal, Question.topic, Answer)
            .join(Answer, Answer.question_id == Question.id)
            .where(Question.session_id == session.id)
            .order_by(Question.ordinal)
        )
        integrity = [
            IntegrityLine(question=ordinal + 1, topic=topic, detail=signal.detail)
            for ordinal, topic, answer in rows.all()
            for signal in assess(answer)
        ]

    data = ReportPdfData(
        session_id=str(session.id),
        created_at=session.created_at,
        state=session.state.value,
        overall=report.overall,
        per_topic=dict(report.per_topic or {}),
        strengths=list(report.strengths or []),
        gaps=list(report.gaps or []),
        human_reviewed=await was_human_reviewed(db, session.id),
        candidate_email=candidate_email,
        integrity=integrity,
    )
    return await run_in_threadpool(render_report_pdf, data)


def pdf_response(pdf: bytes, session_id: uuid.UUID) -> Response:
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="interviewiq-report-{str(session_id)[:8]}.pdf"'
            )
        },
    )
