"""Scoring metrics for the grading evaluation.

Small, pure, and dependency-free on purpose: numpy/sklearn would be two more
things in the image for four functions that are a dozen lines each, and the
arithmetic here should be readable by anyone checking whether the headline
number is honest.

Four questions, four metrics:

- *Is the grader close to the human?* -> mean absolute error.
- *Does it agree on the decision, beyond luck?* -> Cohen's kappa on pass/fail.
  Raw agreement flatters a lopsided set: if 85% of answers pass, a grader that
  says "pass" every time scores 85% and has learned nothing. Kappa subtracts
  the agreement you would get by chance, so that grader scores ~0.
- *How much work is it pushing onto a human?* -> review rate.
- *Does it say the same thing twice?* -> score spread across repeated runs.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from statistics import mean, pstdev

#: A score at or above this counts as "pass" when forming bands for kappa.
#: 0.5 splits the 0/0.25/0.5/0.75/1.0 labelling scale down the middle.
PASS_CUTOFF = 0.5


def mean_absolute_error(predicted: Sequence[float], actual: Sequence[float]) -> float:
    """Average distance between the grader's score and the human's."""
    if not predicted:
        return 0.0
    return sum(abs(p - a) for p, a in zip(predicted, actual, strict=True)) / len(predicted)


def band(score: float, *, cutoff: float = PASS_CUTOFF) -> bool:
    """Collapse a 0..1 score to the pass/fail decision it would drive."""
    return score >= cutoff


def cohens_kappa(a: Sequence[bool], b: Sequence[bool]) -> float:
    """Agreement between two binary raters, corrected for chance.

    1.0 is perfect, 0.0 is chance-level, negative is worse than guessing.
    """
    n = len(a)
    if n == 0:
        return 0.0
    observed = sum(1 for x, y in zip(a, b, strict=True) if x == y) / n

    a_pos, b_pos = sum(a) / n, sum(b) / n
    expected = a_pos * b_pos + (1 - a_pos) * (1 - b_pos)
    if expected >= 1.0:
        # Both raters used a single class for everything; chance already
        # explains all the agreement, so there is no signal to report.
        return 0.0
    return (observed - expected) / (1 - expected)


def review_rate(flags: Sequence[bool]) -> float:
    """Share of answers the grader refused to decide and sent to a human."""
    return (sum(flags) / len(flags)) if flags else 0.0


def score_spread(runs: Sequence[Sequence[float]]) -> float:
    """Mean per-item population standard deviation across repeated runs.

    `runs[r][i]` is the score run `r` gave item `i`. 0.0 means the grader is
    perfectly reproducible; this is the number the deterministic pass exists
    to hold down.
    """
    if len(runs) < 2:
        return 0.0
    per_item = zip(*runs, strict=True)
    return mean(pstdev(scores) for scores in per_item)


@dataclass(frozen=True)
class GradingReport:
    """One evaluation run, reduced to the numbers worth committing."""

    n: int
    label_source: str
    mae: float
    kappa: float
    review_rate: float
    score_spread: float
    mean_predicted: float
    mean_label: float
    runs: int

    def as_dict(self) -> dict[str, object]:
        return {
            "n": self.n,
            "label_source": self.label_source,
            "runs": self.runs,
            "mae": round(self.mae, 4),
            "kappa": round(self.kappa, 4),
            "review_rate": round(self.review_rate, 4),
            "score_spread": round(self.score_spread, 4),
            "mean_predicted": round(self.mean_predicted, 4),
            "mean_label": round(self.mean_label, 4),
        }

    def table(self) -> str:
        caveat = (
            ""
            if self.label_source == "human"
            else "\n  NOTE: labels are AI-bootstrapped, so `mae` and `kappa` measure\n"
            "        self-consistency, not human agreement. Re-label to make them real."
        )
        return (
            f"  items                {self.n}  ({self.label_source} labels)\n"
            f"  runs per item        {self.runs}\n"
            f"  mean abs error       {self.mae:.3f}   (lower is better)\n"
            f"  Cohen's kappa        {self.kappa:.3f}   (1.0 perfect, 0.0 chance)\n"
            f"  review-queue rate    {self.review_rate:.1%}\n"
            f"  score spread         {self.score_spread:.3f}   (0.0 fully reproducible)\n"
            f"  mean predicted       {self.mean_predicted:.3f}\n"
            f"  mean label           {self.mean_label:.3f}"
            f"{caveat}"
        )
