"""Reproducible scoring: the deterministic anchor and the divergence reconcile.

The design-doc thesis (§4): an LLM asked to grade the same answer repeatedly
gives different numbers, so a scoring system built on the LLM alone isn't
reproducible. We anchor it with a deterministic embedding pass, and when the
two passes disagree by more than a threshold we don't guess — we re-run the LLM
and, if it still diverges, route the answer to a human. These functions are
pure so the policy is unit-testable without a DB or a provider.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import median


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def coverage_ratio(
    answer_vec: list[float], concept_vecs: list[list[float]], *, threshold: float
) -> float:
    """Deterministic coverage: fraction of expected concepts whose cosine
    similarity to the answer clears `threshold`. No network call."""
    if not concept_vecs:
        return 0.0
    covered = sum(1 for cv in concept_vecs if cosine(answer_vec, cv) >= threshold)
    return covered / len(concept_vecs)


def llm_coverage_score(covered_values: list[float]) -> float:
    """Collapse the LLM's per-concept coverage into one 0..1 score."""
    return sum(covered_values) / len(covered_values) if covered_values else 0.0


@dataclass
class Reconciliation:
    final_score: float
    confidence: float
    needs_review: bool
    run_count: int


def reconcile(
    llm_scores: list[float], deterministic_score: float, *, threshold: float
) -> Reconciliation:
    """Combine the LLM run(s) with the deterministic anchor.

    `llm_scores` holds one score per LLM run (the first pass, plus any re-runs).
    They agree with the anchor when |median(llm) - deterministic| <= threshold:
    high confidence, no review. Otherwise the answer diverges — surface it for a
    human with low confidence. `final_score` is always the blend of the two
    passes so a stored score is never a single unstable LLM number.
    """
    run_count = len(llm_scores)
    llm_final = median(llm_scores) if llm_scores else 0.0
    final = round((llm_final + deterministic_score) / 2, 4)
    diverged = abs(llm_final - deterministic_score) > threshold
    if diverged:
        return Reconciliation(final, confidence=0.4, needs_review=True, run_count=run_count)
    confidence = 0.9 if run_count == 1 else 0.75
    return Reconciliation(final, confidence=confidence, needs_review=False, run_count=run_count)
