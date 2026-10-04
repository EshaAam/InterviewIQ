"""Measure retrieval quality, and prove hybrid earns its complexity.

Running vector, keyword and hybrid over the same golden set is the point. Hybrid
is strictly more machinery than either half — two queries, a fusion step, a
tuning constant — and that is only worth carrying if the numbers say so. If
vector alone matched it, this module's job would be to tell us to delete the
fusion.

Two metrics, answering different questions:

- **recall@k** — of the passages that *should* come back, how many did, in the
  top k? This is what grounding needs: generation only sees the top k, so a
  relevant passage at rank 9 might as well not exist.
- **MRR** — how near the top was the *first* relevant hit? Two retrievers can
  share a recall@5 while one consistently ranks the right passage first and the
  other buries it at five. Under a token budget that difference decides what
  survives truncation.

The cut-off is disabled here (`min_similarity=0`). It answers "does the corpus
cover this query at all", which is a different question from "is the ranking
good", and leaving it on would conflate the two.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean

from sqlalchemy.ext.asyncio import AsyncSession

from app.embedders import Embedder
from app.eval.golden import RetrievalItem
from app.services.retrieval import SearchMode, search


@dataclass
class RetrievalReport:
    mode: str
    n: int
    k: int
    recall_at_k: float
    mrr: float
    #: recall@k split by query kind — where the two retrievers differ most.
    by_kind: dict[str, float] = field(default_factory=dict)
    #: Queries that returned nothing relevant at all. The list worth reading.
    misses: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "n": self.n,
            "k": self.k,
            "recall_at_k": round(self.recall_at_k, 4),
            "mrr": round(self.mrr, 4),
            "by_kind": {k: round(v, 4) for k, v in sorted(self.by_kind.items())},
            "misses": self.misses,
        }


async def evaluate_retrieval(
    db: AsyncSession,
    embedder: Embedder,
    items: list[RetrievalItem],
    *,
    mode: SearchMode,
    k: int = 5,
) -> RetrievalReport:
    recalls: list[float] = []
    reciprocal_ranks: list[float] = []
    per_kind: dict[str, list[float]] = {}
    misses: list[str] = []

    for item in items:
        hits = await search(
            db,
            embedder,
            item.query,
            k=k,
            mode=mode,
            min_similarity=0.0,
        )
        paths = [h.heading_path for h in hits]
        wanted = set(item.relevant)

        found = wanted.intersection(paths)
        recall = len(found) / len(wanted)
        recalls.append(recall)
        per_kind.setdefault(item.kind, []).append(recall)

        rank = next((i for i, p in enumerate(paths, start=1) if p in wanted), None)
        reciprocal_ranks.append(1 / rank if rank else 0.0)
        if not found:
            misses.append(f"{item.id} {item.query[:60]}")

    return RetrievalReport(
        mode=str(mode),
        n=len(items),
        k=k,
        recall_at_k=mean(recalls) if recalls else 0.0,
        mrr=mean(reciprocal_ranks) if reciprocal_ranks else 0.0,
        by_kind={kind: mean(values) for kind, values in per_kind.items()},
        misses=misses,
    )


async def compare_modes(
    db: AsyncSession,
    embedder: Embedder,
    items: list[RetrievalItem],
    *,
    k: int = 5,
) -> list[RetrievalReport]:
    """vector, keyword and hybrid over the same queries."""
    return [
        await evaluate_retrieval(db, embedder, items, mode=mode, k=k)
        for mode in (SearchMode.VECTOR, SearchMode.KEYWORD, SearchMode.HYBRID)
    ]


async def false_grounding_rate(
    db: AsyncSession,
    embedder: Embedder,
    queries: list[str],
    *,
    k: int = 5,
    min_similarity: float | None = None,
) -> tuple[int, int]:
    """How many uncovered queries still come back with passages.

    Run with the production cut-off, unlike the recall measurements: this is
    precisely the question of whether the floor is doing its job. A query about
    Kubernetes must return nothing rather than the least-bad SQL passage, or
    generation grounds an answer key in unrelated material and the citation
    misleads whoever reads it.
    """
    grounded = 0
    for query in queries:
        hits = await search(db, embedder, query, k=k, min_similarity=min_similarity)
        if hits:
            grounded += 1
    return grounded, len(queries)


def comparison_table(reports: list[RetrievalReport]) -> str:
    kinds = sorted({kind for r in reports for kind in r.by_kind})
    header = f"  {'mode':<9} {'recall@k':>9} {'MRR':>7}  " + "  ".join(
        f"{kind:>11}" for kind in kinds
    )
    lines = [header, "  " + "-" * (len(header) - 2)]
    for report in reports:
        cells = "  ".join(f"{report.by_kind.get(kind, 0.0):>11.3f}" for kind in kinds)
        lines.append(
            f"  {report.mode:<9} {report.recall_at_k:>9.3f} {report.mrr:>7.3f}  {cells}"
        )
    return "\n".join(lines)
