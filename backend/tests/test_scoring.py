"""Pure scoring logic — coverage ratio and the divergence reconcile."""

from __future__ import annotations

from app.services.scoring import coverage_ratio, reconcile


def test_coverage_ratio_counts_concepts_over_threshold() -> None:
    answer = [1.0, 0.0]
    concepts = [[1.0, 0.0], [0.0, 1.0]]  # one matches, one orthogonal
    assert coverage_ratio(answer, concepts, threshold=0.5) == 0.5


def test_coverage_ratio_empty_is_zero() -> None:
    assert coverage_ratio([1.0], [], threshold=0.5) == 0.0


def test_reconcile_agreement_is_high_confidence_no_review() -> None:
    r = reconcile([0.8], 0.75, threshold=0.35)
    assert r.needs_review is False
    assert r.confidence == 0.9
    assert r.run_count == 1
    assert r.final_score == round((0.8 + 0.75) / 2, 4)


def test_reconcile_divergence_flags_review() -> None:
    r = reconcile([0.95], 0.1, threshold=0.35)  # gap 0.85 > 0.35
    assert r.needs_review is True
    assert r.confidence == 0.4


def test_reconcile_uses_median_of_reruns() -> None:
    # Three runs; median 0.5 vs deterministic 0.55 -> agree, multi-run confidence.
    r = reconcile([0.2, 0.5, 0.9], 0.55, threshold=0.35)
    assert r.needs_review is False
    assert r.confidence == 0.75
    assert r.run_count == 3


def test_reconcile_boundary_is_not_divergent() -> None:
    # Exactly at threshold counts as agreement (strict >).
    r = reconcile([0.6], 0.25, threshold=0.35)
    assert r.needs_review is False
