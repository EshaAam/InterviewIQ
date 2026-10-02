"""The evaluation pipeline — async, idempotent, provider-agnostic.

These four functions are the actual work behind the Celery tasks. They're
written to be called directly (in tests, against a fake provider and an
in-memory DB) or wrapped by a Celery task (in production). Every function is
**idempotent**: re-running it on a session/answer already past that stage is a
no-op, so a retried worker task never double-writes.

Every provider call is metered into `LLMCall` regardless of outcome — that
ledger is what later answers "what did this interview cost?".

Error policy (the same for every stage):

- **Transient** (`LLMTransientError`, `LLMCircuitOpen`): raise. The task rolls
  back and Celery retries it later; nothing half-written survives.
- **Permanent** (anything else from the provider): record it where it
  happened — résumé `failed`, generation `FAILED`, and for grading, that one
  answer is scored on the deterministic pass alone and sent to a human.
- **Retries exhausted**: `give_up_*` marks the résumé or session failed with
  a reason, so nothing is ever left waiting forever.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta

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
from app.providers.base import LLMCircuitOpen, LLMError, LLMProvider, LLMTransientError
from app.providers.cache import served_from_cache
from app.schemas.pipeline import (
    AnswerEvaluationResult,
    QuestionGenerationResult,
    SkillExtractionResult,
)
from app.services import ledger
from app.services.scoring import coverage_ratio, llm_coverage_score, reconcile
from app.services.session_service import SessionService, can_transition

PROMPT_VERSION = "p2-fake-v1"

# Worth trying again later; everything else is a real answer.
RETRYABLE: tuple[type[Exception], ...] = (LLMTransientError, LLMCircuitOpen)


def is_retryable(exc: BaseException) -> bool:
    return isinstance(exc, RETRYABLE)


# --- helpers ---

async def _meter(
    db: AsyncSession,
    provider: LLMProvider,
    *,
    session_id: uuid.UUID | None,
    user_id: uuid.UUID | None,
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
    await ledger.record(
        db,
        LLMCall(
            session_id=session_id,
            user_id=user_id,
            provider=provider.name,
            model=getattr(provider, "model", provider.name),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_estimate=round(cost, 8),
            latency_ms=int((time.perf_counter() - started) * 1000),
            status=status,
        ),
    )


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


async def _complete_metered(
    db: AsyncSession,
    provider: LLMProvider,
    prompt: str,
    schema,
    *,
    session_id: uuid.UUID | None,
    user_id: uuid.UUID | None,
    temperature: float = 0.0,
):
    """provider.complete + a ledger row for every outcome.

    What a row charges depends on what actually happened:
    ok → estimated tokens; error → the prompt (it was sent); circuit open →
    nothing (no request left the building); cache hit → nothing.
    """
    started = time.perf_counter()
    prompt_tokens = _estimate_tokens(prompt)
    meter = {"session_id": session_id, "user_id": user_id, "started": started}

    token = served_from_cache.set(False)
    try:
        result = await provider.complete(prompt, schema, temperature=temperature)
        cached = served_from_cache.get()
    except LLMCircuitOpen:
        await _meter(
            db, provider, prompt_tokens=0, completion_tokens=0, status="circuit_open", **meter
        )
        raise
    except LLMError:
        await _meter(
            db, provider, prompt_tokens=prompt_tokens, completion_tokens=0,
            status="error", **meter,
        )
        raise
    finally:
        served_from_cache.reset(token)

    if cached:
        await _meter(
            db, provider, prompt_tokens=0, completion_tokens=0, status="cached", **meter
        )
    else:
        await _meter(
            db,
            provider,
            prompt_tokens=prompt_tokens,
            completion_tokens=_estimate_tokens(result.model_dump_json()),
            status="ok",
            **meter,
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
    try:
        result: SkillExtractionResult = await _complete_metered(
            db, provider, prompt, SkillExtractionResult,
            session_id=None, user_id=resume.user_id,
        )
    except LLMError as exc:
        if is_retryable(exc):
            raise  # the task retries; the rollback returns the row to `pending`
        # Permanent: record it. `failed` is a real answer the client can show.
        resume.parse_status = ParseStatus.failed
        await db.flush()
        return resume

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
    # Already prepared (or further along, or failed) -> nothing to do.
    if session.state not in (
        SessionState.CREATED,
        SessionState.PARSING,
        SessionState.GENERATING_QS,
    ):
        return session

    try:
        SessionService.transition(session, SessionState.PARSING)
        await db.flush()

        resume_text = ""
        if session.resume_id is not None:
            resume = await parse_resume(db, provider, session.resume_id)
            if resume.parse_status == ParseStatus.failed:
                SessionService.transition(
                    session,
                    SessionState.FAILED,
                    reason="the resume could not be read — try uploading it again",
                )
                await db.flush()
                return session
            resume_text = resume.text_content or ""

        SessionService.transition(session, SessionState.GENERATING_QS)
        session.prompt_version = PROMPT_VERSION
        session.model_name = provider.name
        await db.flush()

        prompt = f"Generate interview questions for a candidate with:\n{resume_text}"
        result: QuestionGenerationResult = await _complete_metered(
            db, provider, prompt, QuestionGenerationResult,
            session_id=session_id, user_id=session.user_id,
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
        if is_retryable(exc):
            raise  # rolled back to CREATED; the task retries later
        # Permanent (e.g. output still malformed after the repair attempt):
        # a dead-letter. Record FAILED rather than leave the session stuck.
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
    session = await db.get(InterviewSession, question.session_id)
    meter = {"session_id": question.session_id, "user_id": session.user_id if session else None}

    concepts = question.expected_concepts or []
    concept_lines = "\n".join(f"- {c}" for c in concepts)
    prompt = (
        f"Question: {question.text}\n"
        f"Expected concepts:\n{concept_lines}\n"
        f"Answer:\n{answer.text}"
    )

    # --- Deterministic pass: embed answer + concepts, coverage ratio. No LLM. ---
    deterministic_score = 0.0
    if concepts:
        vectors = await provider.embed([answer.text, *concepts])
        deterministic_score = coverage_ratio(
            vectors[0], vectors[1:], threshold=settings.EVAL_COVERAGE_THRESHOLD
        )

    # --- LLM pass (temp 0 for reproducibility). ---
    try:
        llm: AnswerEvaluationResult = await _complete_metered(
            db, provider, prompt, AnswerEvaluationResult, temperature=0.0, **meter
        )
    except LLMError as exc:
        if is_retryable(exc):
            raise
        # The model can't produce a usable grade for this answer even after
        # the repair attempt. Don't fail the whole interview over one answer:
        # score it on the deterministic pass alone and put it in front of a
        # human, which is exactly what the review queue exists for.
        return await _insert_evaluation(
            db,
            Evaluation(
                answer_id=answer_id,
                concept_coverage={},
                llm_scores={},
                deterministic_score=round(deterministic_score, 4),
                final_score=round(deterministic_score, 4),
                confidence=0.0,
                needs_review=True,
                model_name=provider.name,
                temperature=0.0,
                prompt_version=PROMPT_VERSION,
                run_count=0,
            ),
        )
    coverage_map = {c.concept: c.covered for c in llm.concept_coverage}
    llm_scores = [llm_coverage_score(list(coverage_map.values()))]

    # --- Reconcile. On divergence, re-run the LLM (nonzero temp) to confirm. ---
    result = reconcile(
        llm_scores, deterministic_score, threshold=settings.EVAL_DIVERGENCE_THRESHOLD
    )
    if result.needs_review and settings.EVAL_RERUN_COUNT > 0:
        for _ in range(settings.EVAL_RERUN_COUNT):
            try:
                rerun = await _complete_metered(
                    db,
                    provider,
                    prompt,
                    AnswerEvaluationResult,
                    temperature=settings.EVAL_RERUN_TEMPERATURE,
                    **meter,
                )
            except LLMError as exc:
                if is_retryable(exc):
                    raise
                break  # a malformed re-run: decide on the runs we have
            llm_scores.append(
                llm_coverage_score([c.covered for c in rerun.concept_coverage])
            )
        result = reconcile(
            llm_scores,
            deterministic_score,
            threshold=settings.EVAL_DIVERGENCE_THRESHOLD,
        )

    return await _insert_evaluation(
        db,
        Evaluation(
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
        ),
    )


async def _insert_evaluation(db: AsyncSession, evaluation: Evaluation) -> Evaluation:
    """Insert inside a savepoint so a concurrent evaluator racing on the same
    answer_id (unique) doesn't poison the outer transaction — we just fetch
    and return the row that won the race."""
    try:
        async with db.begin_nested():
            db.add(evaluation)
            await db.flush()
    except IntegrityError:
        winner = await db.scalar(
            select(Evaluation).where(Evaluation.answer_id == evaluation.answer_id)
        )
        if winner is None:
            raise
        return winner
    return evaluation


# --- stage 4: build report ---

def summarize(per_topic_scores: dict[str, list[float]]) -> dict:
    """The report's numbers from final scores grouped by topic.

    Mean per topic, mean of topics overall, strengths >= 0.7, gaps < 0.5.
    One function for both the first build and every rebuild after a recruiter
    override, so the two can never disagree on how a report is computed.
    """
    per_topic = {
        topic: round(sum(scores) / len(scores), 4)
        for topic, scores in per_topic_scores.items()
    }
    overall = round(sum(per_topic.values()) / len(per_topic), 4) if per_topic else 0.0
    return {
        "overall": overall,
        "per_topic": per_topic,
        "strengths": [t for t, s in per_topic.items() if s >= 0.7],
        "gaps": [t for t, s in per_topic.items() if s < 0.5],
    }


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

    report = Report(session_id=session_id, **summarize(per_topic_scores))
    # A redelivered task can race the original to this point (the session's
    # report is unique). Same savepoint pattern as evaluations: the loser
    # returns the winner's report instead of failing.
    try:
        async with db.begin_nested():
            db.add(report)
            await db.flush()
    except IntegrityError:
        winner = await db.scalar(select(Report).where(Report.session_id == session_id))
        if winner is None:
            raise
        return winner

    # If any answer's passes diverged, the session goes to the human-review
    # queue instead of auto-completing.
    target = (
        SessionState.NEEDS_HUMAN_REVIEW if needs_review else SessionState.COMPLETED
    )
    SessionService.transition(session, target)
    await db.flush()
    return report


# --- after human review ---

async def rebuild_report(db: AsyncSession, session_id: uuid.UUID) -> Report | None:
    """Recompute a session's report from its evaluations as they stand now.

    Called after a recruiter overrides a score. Reads stored evaluations only
    — it never grades — so build_report stays the single evaluator. Once no
    answer in the session still needs review, the session leaves
    NEEDS_HUMAN_REVIEW for COMPLETED.

    Returns None if the report hasn't been built yet: build_report will read
    the overridden score itself when it runs.
    """
    report = await db.scalar(select(Report).where(Report.session_id == session_id))
    if report is None:
        return None

    rows = await db.execute(
        select(Question.topic, Evaluation.final_score, Evaluation.needs_review)
        .join(Answer, Answer.question_id == Question.id)
        .join(Evaluation, Evaluation.answer_id == Answer.id)
        .where(Question.session_id == session_id)
    )
    per_topic_scores: dict[str, list[float]] = {}
    still_flagged = False
    for topic, final_score, needs_review in rows.all():
        per_topic_scores.setdefault(topic, []).append(final_score)
        still_flagged = still_flagged or needs_review

    for field, value in summarize(per_topic_scores).items():
        setattr(report, field, value)

    session = await db.get(InterviewSession, session_id)
    if (
        session is not None
        and session.state == SessionState.NEEDS_HUMAN_REVIEW
        and not still_flagged
    ):
        SessionService.transition(session, SessionState.COMPLETED)
    await db.flush()
    return report


# --- when retries run out ---

async def give_up_resume(db: AsyncSession, resume_id: uuid.UUID) -> None:
    """Retries exhausted on a parse: say so, rather than leave `pending`."""
    resume = await db.get(Resume, resume_id)
    if resume is not None and resume.parse_status != ParseStatus.parsed:
        resume.parse_status = ParseStatus.failed
        await db.flush()


async def give_up_session(db: AsyncSession, session_id: uuid.UUID, reason: str) -> None:
    """Retries exhausted on generation or grading: FAILED, with the reason.

    A no-op if the session already moved on (another delivery finished it).
    """
    session = await db.get(InterviewSession, session_id)
    if session is not None and can_transition(session.state, SessionState.FAILED):
        SessionService.transition(session, SessionState.FAILED, reason=reason)
        await db.flush()


# --- the reaper ---

async def claim_stale_sessions(
    db: AsyncSession, *, now: datetime | None = None
) -> tuple[list[uuid.UUID], list[uuid.UUID]]:
    """Sessions whose job seems to have been lost: still CREATED (no one
    generated questions) or still EVALUATING (no one built the report) well
    past the time that takes. Returns (to_generate, to_report).

    "Claim" because it bumps `updated_at` on what it returns: the next sweep
    then leaves them alone for another full window, so a session that is
    merely slow gets one re-dispatch per window, not one every five minutes.
    Re-dispatching is safe either way — every stage is idempotent.
    """
    now = now or datetime.now(UTC)
    created_cutoff = now - timedelta(minutes=settings.REAPER_CREATED_AFTER_MINUTES)
    evaluating_cutoff = now - timedelta(minutes=settings.REAPER_EVALUATING_AFTER_MINUTES)

    stale = list(
        await db.scalars(
            select(InterviewSession).where(
                (
                    (InterviewSession.state == SessionState.CREATED)
                    & (InterviewSession.updated_at < created_cutoff)
                )
                | (
                    (InterviewSession.state == SessionState.EVALUATING)
                    & (InterviewSession.updated_at < evaluating_cutoff)
                )
            )
        )
    )
    for session in stale:
        session.updated_at = now
    await db.flush()
    return (
        [s.id for s in stale if s.state == SessionState.CREATED],
        [s.id for s in stale if s.state == SessionState.EVALUATING],
    )
