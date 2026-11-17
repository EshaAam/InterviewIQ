"""A candidate's skills across every interview they have been graded on.

One report describes one interview. This answers the question a single report
cannot: taken together, which skills has this person shown, which are weak, and
which are on the résumé but have never been asked about.

It is a read over rows that already exist. Every evaluation stores per-concept
coverage, every question stores its topic and a copy of its cited passages, and
every résumé stores its extracted skills. Nothing here calls a model, retrieves
from the knowledge base or writes anything, so the map costs no provider quota
and always describes what the interviews actually recorded.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Answer,
    Evaluation,
    ExtractedSkill,
    InterviewSession,
    Question,
    Resume,
)
from app.schemas.interview import (
    CitedSourceRead,
    ConceptEvidence,
    QuestionEvidence,
    SkillAttempt,
    SkillEvidence,
    SkillMapRead,
    UnassessedSkill,
)
from app.services.citations import load_citations
from app.services.scoring import GAP_THRESHOLD, STRENGTH_THRESHOLD

#: A concept counts as missed below this coverage. The grader reports 0, 0.5 or
#: 1 in practice, so "half covered" is treated as covered, not as a miss.
CONCEPT_MISSED_BELOW = 0.5

#: Weakest first: the order a person reading the map should meet them in.
_STATUS_ORDER = {"weak": 0, "developing": 1, "demonstrated": 2}

Graded = list[tuple[Question, Evaluation]]


def skill_key(name: str) -> str:
    """Skills are matched case- and whitespace-insensitively.

    A question's topic comes from the model and a skill name from the résumé
    extractor, so "FastAPI", "fastapi" and "fastapi " have to be one skill.
    Nothing fuzzier than that: merging "sql" into "postgresql" would be a
    guess, and a wrong merge hides a skill instead of showing it twice.
    """
    return " ".join(name.lower().split())


def status_for(score: float) -> str:
    """The same cut-offs a report uses for strengths and gaps."""
    if score >= STRENGTH_THRESHOLD:
        return "demonstrated"
    if score < GAP_THRESHOLD:
        return "weak"
    return "developing"


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 4)


async def build_skill_map(db: AsyncSession, user_id: uuid.UUID) -> SkillMapRead:
    rows = (
        await db.execute(
            select(Question, Evaluation, InterviewSession)
            .join(InterviewSession, Question.session_id == InterviewSession.id)
            .join(Answer, Answer.question_id == Question.id)
            .join(Evaluation, Evaluation.answer_id == Answer.id)
            .where(InterviewSession.user_id == user_id)
            # Oldest interview first, so the last entry per skill is the latest.
            .order_by(
                InterviewSession.created_at,
                InterviewSession.id,
                Question.ordinal,
                Answer.submitted_at,
            )
        )
    ).all()

    # skill key -> session id -> that session's graded answers on the skill.
    by_skill: dict[str, dict[uuid.UUID, Graded]] = {}
    sessions: dict[uuid.UUID, InterviewSession] = {}
    for question, evaluation, session in rows:
        sessions[session.id] = session
        by_skill.setdefault(skill_key(question.topic), {}).setdefault(
            session.id, []
        ).append((question, evaluation))

    # Passages are only shown beside something the candidate missed, so only
    # those questions need their citations resolved.
    latest_rows: dict[str, Graded] = {
        key: list(per_session.values())[-1] for key, per_session in by_skill.items()
    }
    missed_questions = {
        question.id: question
        for graded in latest_rows.values()
        for question, evaluation in graded
        if _missed(question, evaluation)
    }
    citations = await load_citations(db, list(missed_questions.values()))

    skills: list[SkillEvidence] = []
    for key, per_session in by_skill.items():
        history = [
            SkillAttempt(
                session_id=session_id,
                assessed_at=sessions[session_id].created_at,
                score=_mean([evaluation.final_score for _, evaluation in graded]),
            )
            for session_id, graded in per_session.items()
        ]
        latest = latest_rows[key]
        score = history[-1].score
        skills.append(
            SkillEvidence(
                # The spelling the most recent interview used.
                name=latest[-1][0].topic.strip(),
                status=status_for(score),
                score=score,
                best=max(attempt.score for attempt in history),
                previous=history[-2].score if len(history) > 1 else None,
                sessions=len(history),
                answers=sum(len(graded) for graded in per_session.values()),
                last_assessed_at=history[-1].assessed_at,
                needs_review=any(evaluation.needs_review for _, evaluation in latest),
                history=history,
                evidence=[
                    QuestionEvidence(
                        question_id=question.id,
                        session_id=question.session_id,
                        text=question.text,
                        score=evaluation.final_score,
                        concepts=_concepts(question, evaluation),
                        sources=[
                            CitedSourceRead.model_validate(source)
                            for source in citations.get(question.id, [])
                        ]
                        if question.id in missed_questions
                        else [],
                    )
                    for question, evaluation in latest
                ],
            )
        )
    skills.sort(key=lambda s: (_STATUS_ORDER[s.status], s.score, s.name))

    return SkillMapRead(
        sessions_assessed=len(sessions),
        skills=skills,
        not_assessed=await _not_assessed(db, user_id, set(by_skill)),
    )


def _concepts(question: Question, evaluation: Evaluation) -> list[ConceptEvidence]:
    """Coverage in the question's own concept order.

    Keyed off `expected_concepts`, not the stored map, so a concept the grader
    never reported still appears, as not covered, rather than vanishing.
    """
    coverage = evaluation.concept_coverage or {}
    return [
        ConceptEvidence(concept=concept, covered=float(coverage.get(concept, 0.0)))
        for concept in (question.expected_concepts or [])
    ]


def _missed(question: Question, evaluation: Evaluation) -> bool:
    return any(c.covered < CONCEPT_MISSED_BELOW for c in _concepts(question, evaluation))


async def _not_assessed(
    db: AsyncSession, user_id: uuid.UUID, assessed: set[str]
) -> list[UnassessedSkill]:
    """Skills on any of the user's résumés with no graded answer behind them."""
    extracted = await db.scalars(
        select(ExtractedSkill)
        .join(Resume, ExtractedSkill.resume_id == Resume.id)
        .where(Resume.user_id == user_id)
        # Newest résumé first: its wording and evidence are the current ones.
        .order_by(Resume.created_at.desc(), ExtractedSkill.confidence.desc())
    )
    found: dict[str, UnassessedSkill] = {}
    for skill in extracted:
        key = skill_key(skill.name)
        if not key or key in assessed or key in found:
            continue
        found[key] = UnassessedSkill(
            name=skill.name.strip(),
            confidence=skill.confidence,
            evidence_span=skill.evidence_span,
        )
    return sorted(found.values(), key=lambda s: (-s.confidence, s.name))
