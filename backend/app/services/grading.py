"""The grading policy, with no database and no persistence.

`pipeline.evaluate_answer` used to hold the prompt, the deterministic pass, the
LLM pass and the reconcile inline. That made grading quality unmeasurable
without a database, a session row and an answer row — so the only honest way to
ask "did this change help?" was to run a whole interview.

The policy lives here instead. `evaluate_answer` now supplies a metered
`complete` and persists the outcome; the offline harness in `app.eval` supplies
an unmetered one and persists nothing. Both grade through *the same* code, which
is the point: a baseline measured against a reimplementation measures a fiction.

Thresholds are parameters with settings-backed defaults, so the recalibration
sweep in `app.eval.recalibrate` can vary one without mutating global config.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field

from app.core.config import settings
from app.embedders import Embedder
from app.providers.base import LLMError
from app.schemas.pipeline import AnswerEvaluationResult
from app.services.scoring import coverage_ratio, llm_coverage_score, reconcile

# (prompt, temperature) -> validated model output. The caller decides whether
# that call is metered, cached, retried, or none of the above.
CompleteFn = Callable[[str, float], Awaitable[AnswerEvaluationResult]]


@dataclass(frozen=True)
class GradeOutcome:
    """Everything a caller needs to persist or score, and nothing about how."""

    deterministic_score: float
    llm_scores: list[float]
    final_score: float
    confidence: float
    needs_review: bool
    run_count: int
    concept_coverage: dict[str, float] = field(default_factory=dict)
    rubric: dict[str, float] = field(default_factory=dict)
    # False when the model could not produce a usable grade even after repair.
    # The answer is scored on the deterministic pass alone and sent to a human.
    llm_available: bool = True


def build_prompt(
    question: str,
    concepts: Sequence[str],
    answer: str,
    *,
    sources: Sequence[str] = (),
) -> str:
    """The grading prompt. Shared so the harness grades what production grades.

    `sources` are the passages the *question* cited, passed through unchanged —
    grading never retrieves. Two reasons. Retrieving again would let a later
    knowledge-base edit or retriever tweak silently move the score of an
    interview that finished weeks ago, which destroys reproducibility. And the
    judge should be checking the answer against the same material the answer key
    was written from; fresh passages would be a different reference.
    """
    concept_lines = "\n".join(f"- {c}" for c in concepts)
    prompt = f"Question: {question}\nExpected concepts:\n{concept_lines}\n"
    if sources:
        rendered = "\n\n".join(f"[S{i}] {s}" for i, s in enumerate(sources, start=1))
        prompt += (
            "Reference sources — the material these expected concepts were "
            "written from.\nDecide whether the answer covers each concept as "
            "described here, rather\nthan against your own recollection. Treat "
            "the sources as reference, not\nas a required wording: an answer may "
            "cover a concept in different words.\n\n"
            f"{rendered}\n"
        )
    # The answer goes last so a naive split on the final "Answer:" is correct
    # even when a source happens to contain that word.
    return prompt + f"Answer:\n{answer}"


async def deterministic_pass(
    embedder: Embedder,
    answer: str,
    concepts: Sequence[str],
    *,
    coverage_threshold: float | None = None,
) -> float:
    """Embedding-based concept coverage. No LLM, no network beyond the embedder."""
    if not concepts:
        return 0.0
    threshold = (
        settings.EVAL_COVERAGE_THRESHOLD if coverage_threshold is None else coverage_threshold
    )
    vectors = await embedder.embed([answer, *concepts])
    return coverage_ratio(vectors[0], vectors[1:], threshold=threshold)


async def grade(
    *,
    question: str,
    concepts: Sequence[str],
    answer: str,
    embedder: Embedder,
    complete: CompleteFn,
    is_retryable: Callable[[Exception], bool],
    sources: Sequence[str] = (),
    coverage_threshold: float | None = None,
    divergence_threshold: float | None = None,
    rerun_count: int | None = None,
    rerun_temperature: float | None = None,
) -> GradeOutcome:
    """Run both passes and reconcile them.

    A transient provider fault propagates — the caller's retry policy owns it.
    A *terminal* one (malformed output after the repair attempt) does not fail
    the interview: the answer is scored deterministically and flagged for
    review, which is exactly what the review queue exists for.
    """
    divergence = (
        settings.EVAL_DIVERGENCE_THRESHOLD
        if divergence_threshold is None
        else divergence_threshold
    )
    reruns = settings.EVAL_RERUN_COUNT if rerun_count is None else rerun_count
    rerun_temp = (
        settings.EVAL_RERUN_TEMPERATURE if rerun_temperature is None else rerun_temperature
    )

    deterministic = await deterministic_pass(
        embedder, answer, concepts, coverage_threshold=coverage_threshold
    )
    prompt = build_prompt(question, concepts, answer, sources=sources)

    try:
        first = await complete(prompt, 0.0)
    except LLMError as exc:
        if is_retryable(exc):
            raise
        return GradeOutcome(
            deterministic_score=round(deterministic, 4),
            llm_scores=[],
            final_score=round(deterministic, 4),
            confidence=0.0,
            needs_review=True,
            run_count=0,
            llm_available=False,
        )

    coverage_map = {c.concept: c.covered for c in first.concept_coverage}
    llm_scores = [llm_coverage_score(list(coverage_map.values()))]

    result = reconcile(llm_scores, deterministic, threshold=divergence)
    if result.needs_review and reruns > 0:
        for _ in range(reruns):
            try:
                rerun = await complete(prompt, rerun_temp)
            except LLMError as exc:
                if is_retryable(exc):
                    raise
                break  # a malformed re-run: decide on the runs we have
            llm_scores.append(llm_coverage_score([c.covered for c in rerun.concept_coverage]))
        result = reconcile(llm_scores, deterministic, threshold=divergence)

    return GradeOutcome(
        deterministic_score=round(deterministic, 4),
        llm_scores=llm_scores,
        final_score=result.final_score,
        confidence=result.confidence,
        needs_review=result.needs_review,
        run_count=result.run_count,
        concept_coverage=coverage_map,
        rubric=first.llm_scores.model_dump(),
    )
