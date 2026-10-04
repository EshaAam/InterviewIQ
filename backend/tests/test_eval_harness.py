"""The evaluation harness has to be trustworthy before its numbers are.

A metric that is subtly wrong is worse than no metric: it produces a confident
number that justifies the wrong decision. These tests pin the arithmetic
against cases where the answer is known by hand, and check the golden set is
well-formed enough to measure anything.
"""

from __future__ import annotations

import pytest

from app.embedders import HashEmbedder
from app.eval.golden import GoldenItem, label_source, load_golden, save_golden
from app.eval.grading_eval import evaluate, sweep_coverage_threshold
from app.eval.metrics import (
    band,
    cohens_kappa,
    mean_absolute_error,
    review_rate,
    score_spread,
)

# --- metrics ---------------------------------------------------------------


def test_mae_is_average_distance():
    assert mean_absolute_error([1.0, 0.0], [0.0, 0.0]) == 0.5
    assert mean_absolute_error([0.5, 0.5], [0.5, 0.5]) == 0.0


def test_mae_of_nothing_is_zero_not_a_crash():
    assert mean_absolute_error([], []) == 0.0


def test_kappa_is_one_when_raters_agree_completely():
    a = [True, False, True, False]
    assert cohens_kappa(a, a) == pytest.approx(1.0)


def test_kappa_is_negative_when_raters_always_disagree():
    a = [True, False, True, False]
    b = [False, True, False, True]
    assert cohens_kappa(a, b) == pytest.approx(-1.0)


def test_kappa_refuses_to_reward_a_grader_that_says_one_thing_always():
    """The whole reason kappa is here rather than raw agreement.

    A grader that passes everything agrees with a mostly-passing label set most
    of the time, and has learned nothing. Raw agreement would score it 0.9;
    kappa scores it 0.
    """
    labels = [True] * 9 + [False]
    always_pass = [True] * 10

    raw_agreement = sum(x == y for x, y in zip(labels, always_pass, strict=True)) / 10
    assert raw_agreement == 0.9
    assert cohens_kappa(always_pass, labels) == pytest.approx(0.0)


def test_kappa_handles_a_set_where_both_raters_used_one_class():
    # Chance explains everything; there is no signal to report, and no ZeroDivisionError.
    assert cohens_kappa([True] * 5, [True] * 5) == 0.0


def test_band_splits_on_the_pass_cutoff():
    assert band(0.5) is True  # the cutoff itself passes
    assert band(0.49) is False


def test_review_rate_is_the_share_flagged():
    assert review_rate([True, False, False, False]) == 0.25
    assert review_rate([]) == 0.0


def test_score_spread_is_zero_for_identical_runs():
    assert score_spread([[0.4, 0.8], [0.4, 0.8]]) == 0.0


def test_score_spread_grows_when_runs_disagree():
    assert score_spread([[0.0, 0.0], [1.0, 1.0]]) == pytest.approx(0.5)


def test_score_spread_needs_two_runs_to_mean_anything():
    assert score_spread([[0.4, 0.8]]) == 0.0


# --- the golden set --------------------------------------------------------


def test_golden_set_is_big_enough_to_support_kappa():
    items = load_golden()
    assert len(items) >= 40, "below ~40 items kappa is noise, not a measurement"


def test_golden_set_ids_are_unique():
    ids = [i.id for i in load_golden()]
    assert len(ids) == len(set(ids))


def test_golden_labels_span_the_scale():
    """A set clustered at one end cannot distinguish a grader from a constant."""
    labels = {i.label for i in load_golden()}
    assert labels == {0.0, 0.25, 0.5, 0.75, 1.0}


def test_golden_set_is_not_lopsided():
    items = load_golden()
    passing = sum(1 for i in items if i.label >= 0.5) / len(items)
    assert 0.35 <= passing <= 0.65, "a lopsided set inflates raw agreement"


def test_label_source_reports_mixed_sets_honestly():
    base = dict(
        topic="python", question="q", expected_concepts=["c"], answer="a", label=0.5
    )
    ai = GoldenItem(id="1", labeled_by="ai-bootstrap", **base)
    human = GoldenItem(id="2", labeled_by="human", **base)

    assert label_source([ai, ai]) == "ai-bootstrap"
    assert label_source([human, human]) == "human"
    assert label_source([ai, human]) == "mixed (1/2 human)"


def test_golden_set_round_trips_through_save(tmp_path):
    original = load_golden()
    target = tmp_path / "grading.jsonl"
    save_golden(original, target)
    assert load_golden(target) == original


def test_loading_a_missing_golden_set_says_where_it_looked(tmp_path):
    with pytest.raises(FileNotFoundError, match="No golden set at"):
        load_golden(tmp_path / "nope.jsonl")


# --- the runner ------------------------------------------------------------


async def test_evaluate_is_reproducible_on_a_deterministic_stack(provider):
    """Spread is the metric the deterministic pass exists to hold down.

    On the fake provider at temperature 0 with hashing embeddings, three runs
    must produce byte-identical scores. Any drift here means something
    non-deterministic crept into the grading path.
    """
    items = load_golden()[:6]
    report, results = await evaluate(
        items, embedder=HashEmbedder(dim=64), provider=provider, runs=3
    )

    assert report.score_spread == 0.0
    assert report.n == len(items)
    assert report.runs == 3
    assert len(results) == len(items)
    assert all(0.0 <= r.predicted <= 1.0 for r in results)


async def test_evaluate_reports_the_shipped_set_as_human_labelled(provider):
    """The shipped labels were reviewed by hand, so the metrics are real.

    If an unreviewed item is ever appended, this fails and the report starts
    printing the self-consistency caveat again — which is the point: the
    provenance of the labels has to stay visible, not be assumed.
    """
    report, _ = await evaluate(
        load_golden()[:4], embedder=HashEmbedder(dim=64), provider=provider
    )
    assert report.label_source == "human"
    assert "AI-bootstrapped" not in report.table()


def test_every_shipped_label_is_human_reviewed():
    assert all(i.labeled_by == "human" for i in load_golden())


async def test_a_bootstrapped_set_still_carries_the_caveat(provider):
    """The warning must survive: it is what stops a future unreviewed set
    being read as a human-agreement measurement."""
    items = load_golden()[:3]
    for item in items:
        item.labeled_by = "ai-bootstrap"

    report, _ = await evaluate(items, embedder=HashEmbedder(dim=64), provider=provider)
    assert report.label_source == "ai-bootstrap"
    assert "AI-bootstrapped" in report.table()


async def test_threshold_sweep_changes_the_deterministic_score(provider):
    """A lower coverage threshold counts more concepts as covered.

    This is exactly why switching embedders requires recalibration: the
    threshold is a property of the model's cosine distribution, not a universal
    constant.
    """
    items = load_golden()[:8]
    rows = await sweep_coverage_threshold(
        items,
        embedder=HashEmbedder(dim=64),
        provider=provider,
        candidates=[0.1, 0.9],
    )

    lenient = next(r for t, r in rows if t == 0.1)
    strict = next(r for t, r in rows if t == 0.9)
    assert lenient.mean_predicted > strict.mean_predicted


async def test_threshold_sweep_asks_the_llm_once_per_item(provider):
    """The sweep must not multiply the provider bill by the candidate count."""
    items = load_golden()[:5]
    await sweep_coverage_threshold(
        items,
        embedder=HashEmbedder(dim=64),
        provider=provider,
        candidates=[0.2, 0.4, 0.6, 0.8],
    )
    # One grade() per item. Divergent items re-run, so allow the rerun budget,
    # but nothing close to items x candidates.
    assert len(provider.completions) <= len(items) * 3
