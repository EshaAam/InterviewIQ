"""Run the grader over the golden set and reduce it to numbers.

Deliberately has no database and no Celery: it calls `app.services.grading.grade`
directly, which is the same function `pipeline.evaluate_answer` calls. The
alternative — reimplementing the scoring here — would produce a baseline that
drifts from production the first time either side changes, and a baseline you
cannot trust is worse than none.

Completions are *not* metered. A ledger row charges a user for an interview;
an evaluation sweep belongs to nobody, and polluting `llm_calls` would corrupt
the budget numbers the recruiter cost page reports.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean, median

from app.core.config import settings
from app.embedders import Embedder
from app.eval.golden import GoldenItem, label_source
from app.eval.metrics import (
    GradingReport,
    band,
    cohens_kappa,
    mean_absolute_error,
    review_rate,
    score_spread,
)
from app.providers.base import LLMProvider
from app.schemas.pipeline import AnswerEvaluationResult
from app.services.grading import grade
from app.services.scoring import coverage_ratio, llm_coverage_score, reconcile

DEFAULT_BASELINE_DIR = Path(__file__).resolve().parents[2] / "eval" / "baselines"


@dataclass
class ItemResult:
    """What the grader said about one golden item."""

    id: str
    topic: str
    label: float
    predicted: float
    deterministic: float
    llm_median: float
    needs_review: bool


def _completer(provider: LLMProvider):
    """An unmetered `CompleteFn` bound to a provider."""

    async def complete(prompt: str, temperature: float) -> AnswerEvaluationResult:
        return await provider.complete(prompt, AnswerEvaluationResult, temperature=temperature)

    return complete


async def sources_for_golden_items(
    db,
    embedder: Embedder,
    items: list[GoldenItem],
    *,
    k: int | None = None,
) -> dict[str, list[str]]:
    """Retrieve the passages a *grounded* version of each item would have cited.

    A simulation, and worth being explicit about why. Real grounded grading
    replays citations stored on the question at generation time; the golden set
    predates grounding and has none. Retrieving here from the question and its
    concepts approximates what generation would have attached, which is enough
    to answer "does giving the judge reference material change its agreement
    with a human?" — but it is not a replay of a real interview, and the
    comparison should be read as indicative rather than final.
    """
    from app.services.retrieval import search

    out: dict[str, list[str]] = {}
    for item in items:
        query = f"{item.question} {' '.join(item.expected_concepts)}"
        hits = await search(db, embedder, query, k=k)
        out[item.id] = [f"{h.heading_path}\n{h.text}" for h in hits]
    return out


async def evaluate(
    items: list[GoldenItem],
    *,
    embedder: Embedder,
    provider: LLMProvider,
    runs: int = 1,
    coverage_threshold: float | None = None,
    sources_by_item: dict[str, list[str]] | None = None,
    delay_seconds: float = 0.0,
) -> tuple[GradingReport, list[ItemResult]]:
    """Grade every item `runs` times. The last run's scores are the reported ones.

    `runs > 1` exists only to measure reproducibility: at temperature 0 against a
    deterministic provider the spread should be exactly 0.0, and any drift is a
    finding.
    """
    from app.services.pipeline import is_retryable

    complete = _completer(provider)
    all_runs: list[list[float]] = []
    latest: list[ItemResult] = []

    for _ in range(runs):
        this_run: list[float] = []
        latest = []
        for index, item in enumerate(items):
            # Pace the run. A free-tier key allows a low requests-per-minute
            # rate, and a divergent item costs three calls rather than one, so
            # an unpaced sweep benches every key in the pool within seconds and
            # the whole evaluation dies partway through. The retry wrapper
            # cannot rescue it either: its backoff is tuned for a transient
            # blip, not for a 60-second rate-limit cooldown.
            if delay_seconds and index:
                await asyncio.sleep(delay_seconds)
            outcome = await grade(
                question=item.question,
                concepts=item.expected_concepts,
                answer=item.answer,
                embedder=embedder,
                complete=complete,
                is_retryable=is_retryable,
                coverage_threshold=coverage_threshold,
                sources=(sources_by_item or {}).get(item.id, ()),
            )
            this_run.append(outcome.final_score)
            latest.append(
                ItemResult(
                    id=item.id,
                    topic=item.topic,
                    label=item.label,
                    predicted=outcome.final_score,
                    deterministic=outcome.deterministic_score,
                    llm_median=median(outcome.llm_scores) if outcome.llm_scores else 0.0,
                    needs_review=outcome.needs_review,
                )
            )
        all_runs.append(this_run)

    predicted = [r.predicted for r in latest]
    labels = [r.label for r in latest]
    report = GradingReport(
        n=len(items),
        label_source=label_source(items),
        runs=runs,
        mae=mean_absolute_error(predicted, labels),
        kappa=cohens_kappa([band(p) for p in predicted], [band(a) for a in labels]),
        review_rate=review_rate([r.needs_review for r in latest]),
        score_spread=score_spread(all_runs),
        mean_predicted=mean(predicted) if predicted else 0.0,
        mean_label=mean(labels) if labels else 0.0,
    )
    return report, latest


async def sweep_coverage_threshold(
    items: list[GoldenItem],
    *,
    embedder: Embedder,
    provider: LLMProvider,
    candidates: list[float],
) -> list[tuple[float, GradingReport]]:
    """Recalibrate `EVAL_COVERAGE_THRESHOLD` without re-asking the LLM per candidate.

    Cosine values are model-specific: a threshold tuned for the hashing stand-in
    means something different under bge-small, so switching embedders without
    re-tuning silently moves every deterministic score. This sweeps candidates
    against the golden set so the new value is chosen from evidence.

    The LLM pass does not depend on the threshold, so it runs **once per item**
    and is reused across every candidate. Embeddings are cached the same way.
    That turns an O(candidates x items) bill into O(items).
    """
    from app.services.pipeline import is_retryable

    complete = _completer(provider)

    cached: list[tuple[GoldenItem, list[float], list[list[float]]]] = []
    for item in items:
        vectors = await embedder.embed([item.answer, *item.expected_concepts])
        outcome = await grade(
            question=item.question,
            concepts=item.expected_concepts,
            answer=item.answer,
            embedder=embedder,
            complete=complete,
            is_retryable=is_retryable,
        )
        cached.append((item, outcome.llm_scores, vectors))

    results: list[tuple[float, GradingReport]] = []
    for threshold in candidates:
        predicted: list[float] = []
        labels: list[float] = []
        flags: list[bool] = []
        for item, llm_scores, vectors in cached:
            deterministic = coverage_ratio(vectors[0], vectors[1:], threshold=threshold)
            scores = llm_scores or [llm_coverage_score([])]
            outcome = reconcile(
                scores, deterministic, threshold=settings.EVAL_DIVERGENCE_THRESHOLD
            )
            predicted.append(outcome.final_score)
            labels.append(item.label)
            flags.append(outcome.needs_review)
        results.append(
            (
                threshold,
                GradingReport(
                    n=len(items),
                    label_source=label_source(items),
                    runs=1,
                    mae=mean_absolute_error(predicted, labels),
                    kappa=cohens_kappa([band(p) for p in predicted], [band(a) for a in labels]),
                    review_rate=review_rate(flags),
                    score_spread=0.0,
                    mean_predicted=mean(predicted) if predicted else 0.0,
                    mean_label=mean(labels) if labels else 0.0,
                ),
            )
        )
    return results


def write_baseline(
    report: GradingReport,
    results: list[ItemResult],
    *,
    name: str,
    embedder: Embedder | None = None,
    directory: Path | None = None,
) -> Path:
    """Commit the numbers. A baseline nobody can diff is not a baseline.

    The config block records what the run *resolved to*, not what was
    configured: `EMBEDDING_PROVIDER=auto` means different things depending on
    `LLM_PROVIDER`, and a baseline that cannot tell you which model produced it
    is not reproducible.
    """
    from app.embedders import resolved_embedding_provider

    target = (directory or DEFAULT_BASELINE_DIR) / f"{name}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "config": {
            "llm_provider": settings.LLM_PROVIDER,
            "embedding_provider": resolved_embedding_provider(),
            "embedding_model": embedder.name if embedder else None,
            "coverage_threshold": settings.EVAL_COVERAGE_THRESHOLD,
            "divergence_threshold": settings.EVAL_DIVERGENCE_THRESHOLD,
            "rerun_count": settings.EVAL_RERUN_COUNT,
        },
        "metrics": report.as_dict(),
        "items": [
            {
                "id": r.id,
                "topic": r.topic,
                "label": r.label,
                "predicted": r.predicted,
                "deterministic": r.deterministic,
                "llm_median": r.llm_median,
                "needs_review": r.needs_review,
            }
            for r in results
        ],
    }
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return target
