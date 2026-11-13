"""Hybrid retrieval.

These run on SQLite against the real `kb/` corpus, using the hashing embedder so
no model is loaded. That combination exercises the fusion, the cut-off and the
topic filter — the parts that are pure policy — while the Postgres-specific SQL
paths are covered by the `eval-retrieval` job in CI.

The hashing embedder matches on shared words rather than meaning, so absolute
scores here are much lower than production's. Nothing below asserts a magnitude;
they assert *ordering* and *behaviour*, which is what the policy actually owns.
"""

from __future__ import annotations

import pytest

from app.embedders import HashEmbedder
from app.eval.golden import load_retrieval_golden, load_uncovered_queries
from app.models import KB_EMBEDDING_DIM, KBChunk
from app.services.kb_ingest import DEFAULT_KB_DIR, ingest_kb
from app.services.retrieval import RRF_K, SearchMode, search


@pytest.fixture
def embedder() -> HashEmbedder:
    return HashEmbedder(dim=KB_EMBEDDING_DIM)


@pytest.fixture
async def kb(db_session, embedder):
    """The real knowledge base, ingested into the in-memory database."""
    await ingest_kb(db_session, embedder, kb_dir=DEFAULT_KB_DIR)
    return db_session


# --- behaviour -------------------------------------------------------------


async def test_search_returns_at_most_k(kb, embedder):
    hits = await search(kb, embedder, "python generators", k=3, min_similarity=0.0)
    assert len(hits) <= 3


async def test_an_empty_query_retrieves_nothing(kb, embedder):
    assert await search(kb, embedder, "   ", min_similarity=0.0) == []


async def test_the_topic_filter_constrains_results(kb, embedder):
    hits = await search(kb, embedder, "indexes and joins", topic="sql", k=5, min_similarity=0.0)
    assert hits
    assert {h.topic for h in hits} == {"sql"}


async def test_results_are_ordered_by_fused_score(kb, embedder):
    hits = await search(kb, embedder, "database index performance", k=5, min_similarity=0.0)
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True)


async def test_search_is_deterministic(kb, embedder):
    """Ties are common in RRF — two chunks at the same rank in one list — so
    ordering is broken by similarity rather than left to dict iteration."""
    first = await search(kb, embedder, "transaction isolation", k=5, min_similarity=0.0)
    second = await search(kb, embedder, "transaction isolation", k=5, min_similarity=0.0)
    assert [h.chunk_id for h in first] == [h.chunk_id for h in second]


# --- fusion ----------------------------------------------------------------


async def test_a_chunk_found_by_both_retrievers_scores_above_one_found_by_one(kb, embedder):
    """The whole point of fusing: agreement between two independent signals is
    stronger evidence than a high rank in either alone."""
    hits = await search(kb, embedder, "connection pooling", k=10, min_similarity=0.0)
    both = [h for h in hits if h.vector_rank and h.keyword_rank]
    single = [h for h in hits if bool(h.vector_rank) != bool(h.keyword_rank)]
    if not both or not single:
        pytest.skip("this query did not produce both kinds of hit")
    assert min(h.score for h in both) > max(h.score for h in single)


async def test_rrf_score_matches_the_formula(kb, embedder):
    hits = await search(kb, embedder, "circuit breaker", k=5, min_similarity=0.0)
    assert hits
    for hit in hits:
        expected = 0.0
        if hit.vector_rank is not None:
            expected += 1 / (RRF_K + hit.vector_rank)
        if hit.keyword_rank is not None:
            expected += 1 / (RRF_K + hit.keyword_rank)
        assert hit.score == pytest.approx(expected)


async def test_vector_mode_sets_no_keyword_rank(kb, embedder):
    hits = await search(kb, embedder, "memory efficient iteration", mode=SearchMode.VECTOR,
                        k=5, min_similarity=0.0)
    assert hits
    assert all(h.keyword_rank is None and h.vector_rank is not None for h in hits)


async def test_keyword_mode_sets_no_vector_rank(kb, embedder):
    hits = await search(kb, embedder, "deadlock", mode=SearchMode.KEYWORD, k=5,
                        min_similarity=0.0)
    assert hits
    assert all(h.vector_rank is None and h.keyword_rank is not None for h in hits)


async def test_keyword_hits_carry_no_similarity_when_nothing_reads_it(kb, embedder):
    """With the cut-off disabled in keyword mode the query is never embedded,
    so there is no cosine to report and none is invented."""
    hits = await search(kb, embedder, "deadlock", mode=SearchMode.KEYWORD, k=5,
                        min_similarity=0.0)
    assert all(h.similarity == 0.0 for h in hits)


async def test_keyword_hits_are_measured_when_the_cut_off_is_on(kb, embedder):
    """Similarity is the cut-off's only input. A lexical hit used to carry 0.0
    and so could never be kept on its own merits; now it gets the same cosine a
    vector hit would, and is judged by it."""
    hits = await search(kb, embedder, "deadlock", mode=SearchMode.KEYWORD, k=5,
                        min_similarity=0.01)
    assert hits
    assert all(h.vector_rank is None and h.similarity >= 0.01 for h in hits)


# --- the relevance cut-off -------------------------------------------------


async def test_an_impossibly_high_floor_rejects_everything(kb, embedder):
    assert await search(kb, embedder, "python generators", min_similarity=0.999) == []


async def test_a_zero_floor_disables_the_cut_off(kb, embedder):
    assert await search(kb, embedder, "python generators", min_similarity=0.0)


async def test_an_uncovered_query_returns_nothing_rather_than_the_least_bad(kb, embedder):
    """Returning an empty list is a real answer.

    Grounding a question in the nearest irrelevant passage is worse than not
    grounding it: the answer key comes from unrelated material and the citation
    actively misleads whoever checks it.
    """
    # The hashing embedder scores lower across the board than bge, so the
    # production floor is not meaningful here; what matters is that *some*
    # floor rejects a query the corpus has nothing for.
    hits = await search(kb, embedder, "Kubernetes ingress TLS termination", min_similarity=0.35)
    assert hits == []


async def test_each_passage_must_clear_the_floor_on_its_own(kb, embedder):
    """One strong match used to carry the whole top k into the prompt."""
    query = "python generators"
    ranked = await search(kb, embedder, query, k=5, min_similarity=0.0)
    similarities = sorted((h.similarity for h in ranked), reverse=True)
    assert similarities[0] > similarities[-1], "the fixture needs a spread to cut"
    # A floor only the best passage reaches: the query is covered, so the old
    # set-level check let all five through.
    floor = similarities[0]

    hits = await search(
        kb, embedder, query, k=5, min_similarity=floor, passage_min_similarity=floor
    )
    assert hits
    assert all(h.similarity >= floor for h in hits)
    assert len(hits) < len(ranked)


async def test_the_passage_floor_is_never_stricter_than_the_coverage_floor(kb, embedder):
    """A passage good enough to prove the query is covered is good enough to
    return, so an over-tight passage floor cannot empty a covered query."""
    hits = await search(
        kb, embedder, "python generators", k=5, min_similarity=0.05,
        passage_min_similarity=0.999,
    )
    assert hits
    assert all(h.similarity >= 0.05 for h in hits)


async def test_a_weak_passage_gives_its_place_to_the_next_relevant_one(kb, embedder):
    """Filtering happens before the cut to k, not after it."""
    query = "database index performance"
    pool = await search(kb, embedder, query, k=20, min_similarity=0.0)
    floor = sorted((h.similarity for h in pool), reverse=True)[3]
    eligible = [h for h in pool if h.similarity >= floor]

    hits = await search(
        kb, embedder, query, k=3, min_similarity=floor, passage_min_similarity=floor
    )
    if any(h.similarity >= floor for h in pool[:3]):
        assert [h.chunk_id for h in hits] == [h.chunk_id for h in eligible[:3]]


async def test_a_long_resume_sentence_still_gets_keyword_matches(kb, embedder):
    """The shape production sends. Requiring every term matched nothing."""
    hits = await search(
        kb,
        embedder,
        "PostgreSQL Tuned PostgreSQL connection pools and added indexes for a slow "
        "reporting workload at a fintech startup",
        mode=SearchMode.KEYWORD,
        k=5,
        min_similarity=0.0,
    )
    assert hits


# --- the golden sets -------------------------------------------------------


def test_the_golden_set_is_split_into_matching_halves():
    """Settings are fitted on `tune` and reported on `test`; the halves have to
    be disjoint and stress the same mix of query kinds, or the held-out number
    measures a different problem."""
    from collections import Counter

    tune = load_retrieval_golden(split="tune")
    test = load_retrieval_golden(split="test")
    assert tune and test
    assert not {i.id for i in tune} & {i.id for i in test}
    assert len(tune) + len(test) == len(load_retrieval_golden())
    assert Counter(i.kind for i in tune) == Counter(i.kind for i in test)
    assert "resume" in {i.kind for i in test}

    uncovered_tune = load_uncovered_queries(split="tune")
    uncovered_test = load_uncovered_queries(split="test")
    assert uncovered_tune and uncovered_test
    assert not set(uncovered_tune) & set(uncovered_test)



async def test_every_golden_heading_path_exists_in_the_corpus(kb):
    """A typo in a golden path makes that query permanently unanswerable and
    silently drags recall down, which looks like a retrieval regression."""
    known = set(await kb.scalars(KBChunk.__table__.select().with_only_columns(
        KBChunk.heading_path
    )))
    missing = {
        path
        for item in load_retrieval_golden()
        for path in item.relevant
        if path not in known
    }
    assert not missing, f"golden set references unknown heading paths: {sorted(missing)}"


def test_the_golden_set_stresses_both_retrievers():
    """A set made only of paraphrases would make hybrid look pointless by
    construction; one made only of exact terms would do the reverse."""
    kinds = [item.kind for item in load_retrieval_golden()]
    assert kinds.count("paraphrase") >= 15
    assert kinds.count("exact-term") >= 15


def test_uncovered_queries_exist_to_calibrate_the_floor():
    assert len(load_uncovered_queries()) >= 10
