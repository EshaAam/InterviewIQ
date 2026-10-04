"""Hybrid retrieval over the knowledge base.

Two retrievers, fused.

**Vector search** finds passages that mean the same thing as the query, which is
what catches "async database access" matching a passage about `asyncpg`
connection pooling. It is weak on exact tokens: an embedding of
`SELECT FOR UPDATE` is not especially close to an embedding of the paragraph
that explains it, because the model has compressed away the literal string.

**Keyword search** is the mirror image. Postgres full text nails the exact term
and is helpless with a paraphrase.

The R2 ingest check showed this concretely: *"why does a promise callback run
before setTimeout zero?"* retrieved `JavaScript > Promises` above
`JavaScript > The event loop`, although only the event-loop passage contains the
`setTimeout(0)` example. A keyword match on `setTimeout` would have corrected
it. That observation is what this module exists to act on.

**Fusion is by rank, not by score.** A cosine of 0.72 and a `ts_rank_cd` of 0.09
are not on the same scale, and any weighting that makes them comparable is a
constant someone tuned once against a corpus that has since changed. Reciprocal
Rank Fusion ignores the magnitudes and sums `1 / (K + rank)` across the lists a
document appears in, which needs no tuning and degrades gracefully when one
retriever returns nothing.

**The relevance cut-off reads cosine, never the fused score.** RRF scores are a
function of position only, so the top result of a hopeless query scores exactly
as well as the top result of a perfect one. Deciding "the knowledge base does
not cover this" from an RRF score is therefore meaningless; it has to come from
a calibrated similarity.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.embedders import Embedder
from app.models import KBChunk
from app.services.scoring import cosine

#: The constant in `1 / (K + rank)`. 60 is the value from the original RRF
#: paper and the de facto default; it damps the difference between ranks 1 and
#: 2 so a single retriever cannot dominate the fusion on its own.
RRF_K = 60


class SearchMode(StrEnum):
    """Used by the evaluation to compare fusion against each half alone."""

    VECTOR = "vector"
    KEYWORD = "keyword"
    HYBRID = "hybrid"


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    topic: str
    heading_path: str
    text: str
    token_estimate: int
    #: Fused RRF score. Ranks results *within* one query; meaningless across queries.
    score: float
    #: Raw cosine against the query. Comparable across queries, so this — and
    #: only this — is what the relevance cut-off may read. 0.0 when the chunk
    #: was found by keyword search alone.
    similarity: float
    vector_rank: int | None = None
    keyword_rank: int | None = None


@dataclass
class _Candidate:
    chunk: KBChunk
    similarity: float = 0.0
    vector_rank: int | None = None
    keyword_rank: int | None = None


async def _vector_candidates(
    db: AsyncSession, query_vector: list[float], *, topic: str | None, limit: int
) -> list[tuple[uuid.UUID, float]]:
    """(chunk_id, cosine) best-first."""
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        literal = "[" + ",".join(f"{v:.8f}" for v in query_vector) + "]"
        sql = text(
            """
            SELECT id, 1 - (embedding <=> CAST(:vec AS vector)) AS similarity
            FROM kb_chunks
            WHERE embedding IS NOT NULL
              AND (CAST(:topic AS varchar) IS NULL OR topic = :topic)
            ORDER BY embedding <=> CAST(:vec AS vector)
            LIMIT :limit
            """
        )
        rows = await db.execute(sql, {"vec": literal, "topic": topic, "limit": limit})
        return [(row[0], float(row[1])) for row in rows]

    # Off Postgres (the unit suite on SQLite) there is no vector index, so score
    # in Python. Correct and obviously O(n) — fine for a test-sized corpus, and
    # never the path production takes.
    statement = select(KBChunk).where(KBChunk.embedding.is_not(None))
    if topic:
        statement = statement.where(KBChunk.topic == topic)
    chunks = list(await db.scalars(statement))
    scored = [(c.id, cosine(query_vector, c.embedding or [])) for c in chunks]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:limit]


def _tokenize(value: str) -> set[str]:
    return {t for t in "".join(c if c.isalnum() else " " for c in value.lower()).split() if t}


async def _keyword_candidates(
    db: AsyncSession, query: str, *, topic: str | None, limit: int
) -> list[uuid.UUID]:
    """chunk_ids best-first by lexical relevance."""
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        # The expression repeats the one the GIN index was built on, or the
        # index cannot be used. `plainto_tsquery` ANDs the terms, which is the
        # behaviour we want: a query matching every term beats a loose one.
        sql = text(
            """
            SELECT id
            FROM kb_chunks
            WHERE to_tsvector('english', text) @@ plainto_tsquery('english', :q)
              AND (CAST(:topic AS varchar) IS NULL OR topic = :topic)
            ORDER BY ts_rank_cd(to_tsvector('english', text),
                                plainto_tsquery('english', :q)) DESC
            LIMIT :limit
            """
        )
        rows = await db.execute(sql, {"q": query, "topic": topic, "limit": limit})
        return [row[0] for row in rows]

    terms = _tokenize(query)
    if not terms:
        return []
    statement = select(KBChunk)
    if topic:
        statement = statement.where(KBChunk.topic == topic)
    chunks = list(await db.scalars(statement))
    scored: list[tuple[uuid.UUID, float]] = []
    for chunk in chunks:
        chunk_terms = _tokenize(chunk.text)
        overlap = len(terms & chunk_terms)
        if overlap:
            # Length-normalised so a long passage does not win on size alone —
            # roughly what ts_rank_cd does for us on Postgres.
            scored.append((chunk.id, overlap / math.sqrt(len(chunk_terms) or 1)))
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return [chunk_id for chunk_id, _ in scored[:limit]]


async def search(
    db: AsyncSession,
    embedder: Embedder,
    query: str,
    *,
    topic: str | None = None,
    k: int | None = None,
    candidates: int | None = None,
    mode: SearchMode = SearchMode.HYBRID,
    min_similarity: float | None = None,
) -> list[RetrievedChunk]:
    """Return the best `k` passages for `query`, or nothing if none are relevant.

    Returning an empty list is a real answer: a skill the knowledge base does
    not cover must produce *no* context rather than the least-bad irrelevant
    passage, or generation gets grounded in something unrelated and the citation
    actively misleads.
    """
    if not query.strip():
        return []

    top_k = k if k is not None else settings.RAG_TOP_K
    pool = candidates if candidates is not None else settings.RAG_CANDIDATES
    floor = min_similarity if min_similarity is not None else settings.RAG_MIN_SIMILARITY

    found: dict[uuid.UUID, _Candidate] = {}

    if mode in (SearchMode.VECTOR, SearchMode.HYBRID):
        [query_vector] = await embedder.embed([query])
        for rank, (chunk_id, similarity) in enumerate(
            await _vector_candidates(db, query_vector, topic=topic, limit=pool), start=1
        ):
            found[chunk_id] = _Candidate(
                chunk=None,  # type: ignore[arg-type]  - filled in below
                similarity=similarity,
                vector_rank=rank,
            )

    if mode in (SearchMode.KEYWORD, SearchMode.HYBRID):
        for rank, chunk_id in enumerate(
            await _keyword_candidates(db, query, topic=topic, limit=pool), start=1
        ):
            existing = found.get(chunk_id)
            if existing is None:
                found[chunk_id] = _Candidate(chunk=None, keyword_rank=rank)  # type: ignore[arg-type]
            else:
                existing.keyword_rank = rank

    if not found:
        return []

    rows = await db.scalars(select(KBChunk).where(KBChunk.id.in_(list(found))))
    by_id = {chunk.id: chunk for chunk in rows}

    results: list[RetrievedChunk] = []
    for chunk_id, candidate in found.items():
        chunk = by_id.get(chunk_id)
        if chunk is None:  # pragma: no cover - deleted between the two queries
            continue
        score = 0.0
        if candidate.vector_rank is not None:
            score += 1 / (RRF_K + candidate.vector_rank)
        if candidate.keyword_rank is not None:
            score += 1 / (RRF_K + candidate.keyword_rank)
        results.append(
            RetrievedChunk(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                topic=chunk.topic,
                heading_path=chunk.heading_path,
                text=chunk.text,
                token_estimate=chunk.token_estimate,
                score=score,
                similarity=candidate.similarity,
                vector_rank=candidate.vector_rank,
                keyword_rank=candidate.keyword_rank,
            )
        )

    # Ties are common — two chunks found by one retriever each, at the same rank
    # — so break by similarity to keep ordering deterministic between runs.
    results.sort(key=lambda r: (r.score, r.similarity), reverse=True)
    top = results[:top_k]

    # The cut-off applies to the *set*: if nothing clears the floor the KB does
    # not cover this query. Keyword-only hits carry similarity 0.0 and cannot
    # rescue it on their own, which is intended — a lexical match with no
    # semantic support is usually an incidental word collision.
    if floor > 0 and not any(r.similarity >= floor for r in top):
        return []
    return top
