"""The evaluation pipeline — async, idempotent, provider-agnostic.

These four functions are the actual work behind the Celery tasks. They're
written to be called directly (in tests, against a fake provider and an
in-memory DB) or wrapped by a Celery task (in production). Every function is
**idempotent**: re-running it on a session/answer already past that stage is a
no-op, so a retried worker task never double-writes.

Every provider call is metered into `LLMCall` regardless of outcome — that
ledger is what later answers "what did this interview cost?".
"""

from __future__ import annotations

import time
import uuid

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import (
    Answer,
    Evaluation,
    ExtractedSkill,
    InterviewSession,
    LLMCall,
    Question,
    Report,
    Resume,
    SessionState,
)
from app.models.resume import ParseStatus
from app.providers.base import LLMError, LLMProvider
from app.schemas.pipeline import (
    AnswerEvaluationResult,
    QuestionGenerationResult,
    SkillExtractionResult,
)
from app.services.scoring import coverage_ratio, llm_coverage_score, reconcile
from app.services.session_service import SessionService

PROMPT_VERSION = "p2-fake-v1"


# --- helpers ---

async def _meter(
    db: AsyncSession,
    provider: LLMProvider,
    session_id: uuid.UUID | None,
    prompt_tokens: int,
    completion_tokens: int,
    started: float,
    status: str,
) -> None:
    """Write one LLMCall ledger row — the audit/cost record, written on any outcome."""
    cost = (
        prompt_tokens / 1000 * settings.LLM_PRICE_PROMPT_PER_1K
        + completion_tokens / 1000 * settings.LLM_PRICE_COMPLETION_PER_1K
    )
    db.add(
        LLMCall(
            session_id=session_id,
            provider=provider.name,
            model=getattr(provider, "model", provider.name),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_estimate=round(cost, 8),
            latency_ms=int((time.perf_counter() - started) * 1000),
            status=status,
        )
    )


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


async def _complete_metered(
    db: AsyncSession,
    provider: LLMProvider,
    session_id: uuid.UUID | None,
    prompt: str,
    schema,
    *,
    temperature: float = 0.0,
):
    """provider.complete + guaranteed ledger write (ok or error)."""
    started = time.perf_counter()
    prompt_tokens = _estimate_tokens(prompt)
    try:
        result = await provider.complete(prompt, schema, temperature=temperature)
    except LLMError:
        await _meter(db, provider, session_id, prompt_tokens, 0, started, "error")
        raise
    completion_tokens = _estimate_tokens(result.model_dump_json())
    await _meter(
        db, provider, session_id, prompt_tokens, completion_tokens, started, "ok"
    )
    return result


# --- stage 1: parse resume -> skills ---

async def parse_resume(
    db: AsyncSession, provider: LLMProvider, resume_id: uuid.UUID
) -> Resume:
    resume = await db.get(Resume, resume_id)
    if resume is None:
        raise ValueError(f"resume {resume_id} not found")
    if resume.parse_status == ParseStatus.parsed:
        return resume  # idempotent

    resume.parse_status = ParseStatus.parsing
    await db.flush()

    prompt = f"Extract skills from this resume:\n{resume.text_content or ''}"
    result: SkillExtractionResult = await _complete_metered(
        db, provider, None, prompt, SkillExtractionResult
    )

    # Replace any prior skills so a re-parse is clean.
    await db.execute(
        delete(ExtractedSkill).where(ExtractedSkill.resume_id == resume_id)
    )
    for skill in result.skills:
        db.add(
            ExtractedSkill(
                resume_id=resume_id,
                name=skill.name,
                confidence=skill.confidence,
                evidence_span=skill.evidence_span,
            )
        )
    resume.parse_status = ParseStatus.parsed
    await db.flush()
    return resume


# --- stage 2: generate questions ---

async def generate_questions(
    db: AsyncSession, provider: LLMProvider, session_id: uuid.UUID
) -> InterviewSession:
    session = await db.get(InterviewSession, session_id)
    if session is None:
        raise ValueError(f"session {session_id} not found")
    # Already prepared (or further along) -> nothing to do.
    if session.state in (
        SessionState.READY,
        SessionState.IN_PROGRESS,
        SessionState.EVALUATING,
        SessionState.COMPLETED,
        SessionState.NEEDS_HUMAN_REVIEW,
    ):
        return session

    try:
        SessionService.transition(session, SessionState.PARSING)
        await db.flush()

        resume_text = ""
        if session.resume_id is not None:
            await parse_resume(db, provider, session.resume_id)
            resume = await db.get(Resume, session.resume_id)
            resume_text = resume.text_content or "" if resume else ""

        SessionService.transition(session, SessionState.GENERATING_QS)
        session.prompt_version = PROMPT_VERSION
        session.model_name = provider.name
        await db.flush()

        prompt = f"Generate interview questions for a candidate with:\n{resume_text}"
        result: QuestionGenerationResult = await _complete_metered(
            db, provider, session_id, prompt, QuestionGenerationResult
        )

        # Rebuild questions so a retry doesn't collide on (session, ordinal).
        await db.execute(delete(Question).where(Question.session_id == session_id))
        for ordinal, q in enumerate(result.questions):
            db.add(
                Question(
                    session_id=session_id,
                    ordinal=ordinal,
                    text=q.text,
                    difficulty=q.difficulty,
                    topic=q.topic,
                    expected_concepts=q.expected_concepts,
                    reference_answer=q.reference_answer,
                    prompt_version=PROMPT_VERSION,
                )
            )

        SessionService.transition(session, SessionState.READY)
        await db.flush()
        return session
    except LLMError as exc:
        # A malformed/unparseable response is a dead-letter: record FAILED and
        # stop. It's terminal, so the task reports success and does not retry —
        # the session lands in FAILED rather than getting stuck. (Transient 5xx
        # retries live in the Phase 3 provider wrapper, before this layer.)
        SessionService.transition(
            session, SessionState.FAILED, reason=f"question generation failed: {exc}"
        )
        await db.flush()
        return session


# --- stage 3: evaluate one answer ---

async def evaluate_answer(
    db: AsyncSession, provider: LLMProvider, answer_id: uuid.UUID
) -> Evaluation:
    existing = await db.scalar(
        select(Evaluation).where(Evaluation.answer_id == answer_id)
    )
    if existing is not None:
        return existing  # idempotent

    answer = await db.get(Answer, answer_id)
    if answer is None:
        raise ValueError(f"answer {answer_id} not found")
    question = await db.get(Question, answer.question_id)
    if question is None:
        raise ValueError(f"question for answer {answer_id} not found")

    concepts = question.expected_concepts or []
    concept_lines = "\n".join(f"- {c}" for c in concepts)
    prompt = (
        f"Question: {question.text}\n"
        f"Expected concepts:\n{concept_lines}\n"
        f"Answer:\n{answer.text}"
    )
    session_id = question.session_id

    # --- Deterministic pass: embed answer + concepts, coverage ratio. No LLM. ---
    deterministic_score = 0.0
    if concepts:
        vectors = await provider.embed([answer.text, *concepts])
        deterministic_score = coverage_ratio(
            vectors[0], vectors[1:], threshold=settings.EVAL_COVERAGE_THRESHOLD
        )

    # --- LLM pass (temp 0 for reproducibility). ---
    llm: AnswerEvaluationResult = await _complete_metered(
        db, provider, session_id, prompt, AnswerEvaluationResult, temperature=0.0
    )
    coverage_map = {c.concept: c.covered for c in llm.concept_coverage}
    llm_scores = [llm_coverage_score(list(coverage_map.values()))]

    # --- Reconcile. On divergence, re-run the LLM (nonzero temp) to confirm. ---
    result = reconcile(
        llm_scores, deterministic_score, threshold=settings.EVAL_DIVERGENCE_THRESHOLD
    )
    if result.needs_review and settings.EVAL_RERUN_COUNT > 0:
        for _ in range(settings.EVAL_RERUN_COUNT):
            rerun = await _complete_metered(
                db,
                provider,
                session_id,
                prompt,
                AnswerEvaluationResult,
                temperature=settings.EVAL_RERUN_TEMPERATURE,
            )
            llm_scores.append(
                llm_coverage_score([c.covered for c in rerun.concept_coverage])
            )
        result = reconcile(
            llm_scores,
            deterministic_score,
            threshold=settings.EVAL_DIVERGENCE_THRESHOLD,
        )

    evaluation = Evaluation(
        answer_id=answer_id,
        concept_coverage=coverage_map,
        llm_scores=llm.llm_scores.model_dump(),
        deterministic_score=round(deterministic_score, 4),
        final_score=result.final_score,
        confidence=result.confidence,
        needs_review=result.needs_review,
        model_name=provider.name,
        temperature=0.0,
        prompt_version=PROMPT_VERSION,
        run_count=result.run_count,
    )
    # Insert inside a savepoint so a concurrent evaluator racing on the same
    # answer_id (unique) doesn't poison the outer transaction — we just fetch
    # and return the row that won the race.
    try:
        async with db.begin_nested():
            db.add(evaluation)
            await db.flush()
    except IntegrityError:
        winner = await db.scalar(
            select(Evaluation).where(Evaluation.answer_id == answer_id)
        )
        if winner is None:
            raise
        return winner
    return evaluation


# --- stage 4: build report ---

async def build_report(
    db: AsyncSession, provider: LLMProvider, session_id: uuid.UUID
) -> Report:
    existing = await db.scalar(select(Report).where(Report.session_id == session_id))
    if existing is not None:
        return existing  # idempotent

    session = await db.get(InterviewSession, session_id)
    if session is None:
        raise ValueError(f"session {session_id} not found")

    questions = list(
        await db.scalars(
            select(Question).where(Question.session_id == session_id)
        )
    )
    per_topic_scores: dict[str, list[float]] = {}
    needs_review = False
    for question in questions:
        answers = list(
            await db.scalars(
                select(Answer).where(Answer.question_id == question.id)
            )
        )
        for answer in answers:
            evaluation = await evaluate_answer(db, provider, answer.id)
            needs_review = needs_review or evaluation.needs_review
            per_topic_scores.setdefault(question.topic, []).append(
                evaluation.final_score
            )

    per_topic = {
        topic: round(sum(scores) / len(scores), 4)
        for topic, scores in per_topic_scores.items()
    }
    overall = round(sum(per_topic.values()) / len(per_topic), 4) if per_topic else 0.0
    strengths = [t for t, s in per_topic.items() if s >= 0.7]
    gaps = [t for t, s in per_topic.items() if s < 0.5]

    report = Report(
        session_id=session_id,
        overall=overall,
        per_topic=per_topic,
        strengths=strengths,
        gaps=gaps,
    )
    db.add(report)

    # If any answer's passes diverged, the session goes to the human-review
    # queue instead of auto-completing.
    target = (
        SessionState.NEEDS_HUMAN_REVIEW if needs_review else SessionState.COMPLETED
    )
    SessionService.transition(session, target)
    await db.flush()
    return report
