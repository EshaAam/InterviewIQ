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

**The cut-off is applied twice, to two different questions.** `RAG_MIN_SIMILARITY`
asks whether the corpus covers the query at all: if no passage reaches it, the
answer is nothing. `RAG_PASSAGE_MIN_SIMILARITY` then asks it of each passage,
because one strong match used to carry every other result into the prompt with
it, and a passage that merely shared a word with the query became a source the
model could cite.

**Keyword search matches any term and ranks full matches first.** Production
queries are a skill name plus the resume sentence it came from. Requiring every
term (`plainto_tsquery`'s default) meant such a query matched no passage at all
and hybrid search quietly ran on its vector half alone: on the resume-shaped
golden queries the keyword retriever scored recall 0.000.
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
    #: only this — is what the relevance cut-off may read. Computed for keyword
    #: hits too, so a lexical match is held to the same standard as a semantic
    #: one. 0.0 only when no query vector exists: keyword mode with the cut-off
    #: disabled.
    similarity: float
    vector_rank: int | None = None
    keyword_rank: int | None = None


@dataclass
class _Candidate:
    chunk: KBChunk
    #: None until measured; the vector retriever supplies it, keyword-only hits
    #: have it computed from the stored embedding.
    similarity: float | None = None
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
        # index cannot be used.
        #
        # `plainto_tsquery` ANDs the terms. Alone that is too strict: a
        # fourteen-word resume sentence never matches a single passage on every
        # term, so the keyword retriever returned nothing for exactly the
        # queries production sends. `loose` is the same parsed query (same
        # stemming, same stop words) with the ANDs turned into ORs, and it
        # decides what matches. `strict` only reorders: a passage containing
        # every term still outranks one containing some, which keeps the
        # precision of the old behaviour for short exact-term queries.
        sql = text(
            """
            WITH q AS (
                SELECT plainto_tsquery('english', :q) AS strict,
                       replace(plainto_tsquery('english', :q)::text, ' & ', ' | ')::tsquery
                           AS loose
            )
            SELECT id
            FROM kb_chunks, q
            WHERE numnode(q.loose) > 0
              AND to_tsvector('english', text) @@ q.loose
              AND (CAST(:topic AS varchar) IS NULL OR topic = :topic)
            ORDER BY (to_tsvector('english', text) @@ q.strict) DESC,
                     ts_rank_cd(to_tsvector('english', text), q.loose) DESC,
                     id
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
    passage_min_similarity: float | None = None,
) -> list[RetrievedChunk]:
    """Return the best `k` passages for `query`, or nothing if none are relevant.

    Returning an empty list is a real answer: a skill the knowledge base does
    not cover must produce *no* context rather than the least-bad irrelevant
    passage, or generation gets grounded in something unrelated and the citation
    actively misleads.

    `min_similarity` is the coverage floor for the query as a whole and
    `passage_min_similarity` the floor each returned passage must clear; both
    default to the settings. `min_similarity=0` disables the cut-off entirely,
    which is what ranking evaluation wants.
    """
    if not query.strip():
        return []

    top_k = k if k is not None else settings.RAG_TOP_K
    pool = candidates if candidates is not None else settings.RAG_CANDIDATES
    floor = min_similarity if min_similarity is not None else settings.RAG_MIN_SIMILARITY
    passage_floor = (
        passage_min_similarity
        if passage_min_similarity is not None
        else settings.RAG_PASSAGE_MIN_SIMILARITY
    )
    # Never stricter than the coverage floor: a passage good enough to prove
    # the query is covered is good enough to be returned.
    passage_floor = min(passage_floor, floor)

    found: dict[uuid.UUID, _Candidate] = {}
    query_vector: list[float] | None = None

    # The cut-off needs a cosine for every candidate, so the query is embedded
    # whenever one is in force, even in keyword mode.
    if mode in (SearchMode.VECTOR, SearchMode.HYBRID) or floor > 0:
        [query_vector] = await embedder.embed([query])

    if mode in (SearchMode.VECTOR, SearchMode.HYBRID):
        assert query_vector is not None
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
        similarity = candidate.similarity
        if similarity is None:
            # Found by keyword search only. Measure it rather than leave it at
            # zero, so the cut-off judges it on relevance instead of on which
            # retriever happened to find it.
            similarity = (
                cosine(query_vector, list(chunk.embedding))
                if query_vector is not None and chunk.embedding is not None
                else 0.0
            )
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
                similarity=similarity,
                vector_rank=candidate.vector_rank,
                keyword_rank=candidate.keyword_rank,
            )
        )

    # Ties are common — two chunks found by one retriever each, at the same rank
    # — so break by similarity to keep ordering deterministic between runs.
    results.sort(key=lambda r: (r.score, r.similarity), reverse=True)

    if floor <= 0:
        return results[:top_k]

    # Coverage first, over the same top-k the ranking would have returned: if
    # none of them clears the floor the KB does not cover this query, and a
    # better passage further down the list does not change that.
    if not any(r.similarity >= floor for r in results[:top_k]):
        return []
    # Then each passage on its own. Filtering before the cut to k means a weak
    # passage gives its place to the next relevant one instead of leaving a gap.
    return [r for r in results if r.similarity >= passage_floor][:top_k]
