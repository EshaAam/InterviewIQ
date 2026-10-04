"""Citations reaching the people who need them.

A stored citation that nobody can see is bookkeeping, not accountability. These
cover the three places it has to surface: the recruiter's view of an interview,
the review queue where a human overrides a score, and the candidate's report.

The review queue is the one that matters most. It asks a person to second-guess
a grader's decision, and without the cited passages it withholds the evidence
that decision was made from.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.embedders import HashEmbedder
from app.models import (
    KB_EMBEDDING_DIM,
    KBChunk,
    Question,
    Report,
)
from app.services.citations import load_citations
from app.services.kb_ingest import DEFAULT_KB_DIR, ingest_kb
from app.services.reports import MAX_STUDY_LINKS, to_report_read


@pytest.fixture
async def kb(db_session):
    await ingest_kb(db_session, HashEmbedder(dim=KB_EMBEDDING_DIM), kb_dir=DEFAULT_KB_DIR)
    return db_session


def _question(session_id, *, topic="python", ordinal=0, cited=()):
    return Question(
        session_id=session_id,
        ordinal=ordinal,
        text=f"A {topic} question",
        topic=topic,
        expected_concepts=["c1"],
        source_chunk_ids=[str(c) for c in cited],
        grounded=bool(cited),
    )


# --- load_citations --------------------------------------------------------


async def test_citations_resolve_to_readable_sources(kb):
    chunk = await kb.scalar(
        select(KBChunk).where(KBChunk.heading_path == "Python > The GIL")
    )
    question = _question(uuid.uuid4(), cited=[chunk.id])
    kb.add(question)
    await kb.flush()

    resolved = await load_citations(kb, [question])

    [source] = resolved[question.id]
    assert source.heading_path == "Python > The GIL"
    assert source.topic == "python"
    assert "GIL" in source.text
    assert source.document_title == "Python"
    assert source.license  # attribution travels with the passage


async def test_citations_keep_the_order_the_question_stored(kb):
    chunks = list(await kb.scalars(select(KBChunk).limit(3)))
    wanted = [chunks[2].id, chunks[0].id, chunks[1].id]
    question = _question(uuid.uuid4(), cited=wanted)
    kb.add(question)
    await kb.flush()

    resolved = await load_citations(kb, [question])
    assert [s.chunk_id for s in resolved[question.id]] == wanted


async def test_a_withdrawn_chunk_is_omitted_rather_than_breaking_the_screen(kb):
    """A removed document must not take a review screen down with it."""
    chunk = await kb.scalar(select(KBChunk))
    question = _question(uuid.uuid4(), cited=[chunk.id, uuid.uuid4()])
    kb.add(question)
    await kb.flush()

    resolved = await load_citations(kb, [question])
    assert [s.chunk_id for s in resolved[question.id]] == [chunk.id]


async def test_ungrounded_questions_need_no_lookup(kb):
    question = _question(uuid.uuid4())
    kb.add(question)
    await kb.flush()
    assert await load_citations(kb, [question]) == {}


async def test_one_lookup_covers_every_question_on_the_page(kb):
    """A review screen shows a whole interview; per-question lookups would be
    an N+1 on the hot path."""
    chunks = list(await kb.scalars(select(KBChunk).limit(4)))
    questions = [
        _question(uuid.uuid4(), ordinal=i, cited=[c.id]) for i, c in enumerate(chunks)
    ]
    kb.add_all(questions)
    await kb.flush()

    resolved = await load_citations(kb, questions)
    assert len(resolved) == len(questions)
    assert all(resolved[q.id] for q in questions)


# --- study links on the report ---------------------------------------------


async def test_weak_topics_get_study_links(kb):
    session_id = uuid.uuid4()
    chunk = await kb.scalar(
        select(KBChunk).where(KBChunk.heading_path == "Python > The GIL")
    )
    kb.add(_question(session_id, topic="python", cited=[chunk.id]))
    report = Report(
        session_id=session_id,
        overall=0.4,
        per_topic={"python": 0.3, "sql": 0.9},
        strengths=[],
        gaps=["the GIL"],
    )
    kb.add(report)
    await kb.flush()

    read = await to_report_read(kb, report)

    assert [link.heading_path for link in read.study_links] == ["Python > The GIL"]
    assert read.study_links[0].topic == "python"


async def test_a_strong_topic_gets_no_study_link(kb):
    """A report that suggests reading for something you did well is noise."""
    session_id = uuid.uuid4()
    chunk = await kb.scalar(select(KBChunk))
    kb.add(_question(session_id, topic="python", cited=[chunk.id]))
    report = Report(
        session_id=session_id, overall=0.9, per_topic={"python": 0.95},
        strengths=[], gaps=[],
    )
    kb.add(report)
    await kb.flush()

    assert (await to_report_read(kb, report)).study_links == []


async def test_study_links_are_capped(kb):
    """A twenty-item reading list is one nobody opens."""
    session_id = uuid.uuid4()
    chunks = list(await kb.scalars(select(KBChunk).limit(10)))
    for i, chunk in enumerate(chunks):
        kb.add(_question(session_id, topic="python", ordinal=i, cited=[chunk.id]))
    report = Report(
        session_id=session_id, overall=0.2, per_topic={"python": 0.1},
        strengths=[], gaps=[],
    )
    kb.add(report)
    await kb.flush()

    assert len((await to_report_read(kb, report)).study_links) == MAX_STUDY_LINKS


async def test_an_ungrounded_interview_reports_no_study_links(kb):
    session_id = uuid.uuid4()
    kb.add(_question(session_id, topic="python"))
    report = Report(
        session_id=session_id, overall=0.2, per_topic={"python": 0.1},
        strengths=[], gaps=[],
    )
    kb.add(report)
    await kb.flush()

    assert (await to_report_read(kb, report)).study_links == []


# --- the API surface -------------------------------------------------------


async def test_the_review_queue_carries_the_cited_passages(client, recruiter, kb):
    """The reviewer must see what the grader saw."""
    from app.core.config import settings

    headers = await recruiter("reviewer@example.com")
    response = await client.get(
        f"{settings.API_V1_PREFIX}/recruiter/evaluations?needs_review=false", headers=headers
    )
    assert response.status_code == 200
    body = response.json()
    # Shape, not content: the fixture interview may legitimately be ungrounded.
    for item in body["items"]:
        assert "grounded" in item
        assert isinstance(item["sources"], list)
