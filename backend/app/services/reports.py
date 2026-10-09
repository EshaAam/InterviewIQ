"""Read-side helpers for reports (JSON and PDF), shared by the candidate and
recruiter routes."""

from __future__ import annotations

import uuid

from fastapi import Response
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Answer, Evaluation, InterviewSession, Question, Report, Resume
from app.schemas.interview import ReportRead, StudyLink
from app.services.citations import load_citations
from app.services.integrity import assess, assess_resume
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


#: A topic at or below this counts as weak enough to suggest reading for.
STUDY_LINK_THRESHOLD = 0.6
#: Keep the list short. A report that links twenty passages is a reading list
#: nobody opens; three or four is something a candidate might actually use.
MAX_STUDY_LINKS = 4


async def to_report_read(db: AsyncSession, report: Report) -> ReportRead:
    read = ReportRead.model_validate(report)
    read.human_reviewed = await was_human_reviewed(db, report.session_id)
    read.study_links = await _study_links(db, report)
    return read


async def _study_links(db: AsyncSession, report: Report) -> list[StudyLink]:
    """Passages behind the topics the candidate scored worst on.

    Built from citations already stored on the questions, never from a fresh
    retrieval. A report should point at what the interview actually used — if
    it retrieved now, a candidate re-opening an old report could be sent to
    material their questions were never based on.
    """
    per_topic = report.per_topic or {}
    weak = sorted(
        (t for t, score in per_topic.items() if score <= STUDY_LINK_THRESHOLD),
        key=lambda topic: per_topic.get(topic, 0.0),
    )
    if not weak:
        return []

    questions = list(
        await db.scalars(
            select(Question).where(
                Question.session_id == report.session_id,
                Question.topic.in_(weak),
            )
        )
    )
    citations = await load_citations(db, questions)

    links: list[StudyLink] = []
    seen: set[str] = set()
    # Weakest topic first, so a truncated list still leads with what matters.
    by_topic = {topic: index for index, topic in enumerate(weak)}
    for question in sorted(questions, key=lambda q: by_topic.get(q.topic, 0)):
        for source in citations.get(question.id, []):
            if source.heading_path in seen:
                continue
            seen.add(source.heading_path)
            links.append(
                StudyLink(
                    topic=question.topic,
                    heading_path=source.heading_path,
                    document_title=source.document_title,
                    url=source.url,
                )
            )
            if len(links) >= MAX_STUDY_LINKS:
                return links
    return links


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
        resume = await db.get(Resume, session.resume_id) if session.resume_id else None
        integrity = [
            IntegrityLine(question=None, topic="", detail=signal.detail)
            for signal in assess_resume(resume)
        ] + [
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
