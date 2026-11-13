"""A citation has to outlive the knowledge base it was taken from.

Re-ingesting an edited document deletes its chunks and mints new ids. Before
snapshots, a finished interview then showed "not grounded" on its review screen
and was re-graded with no reference at all, although nothing about the
interview had changed. These tests pin the fix: the passage is copied onto the
question when it is generated, and that copy is what every reader uses.
"""

from __future__ import annotations

import pytest
from sqlalchemy import delete, select

from app.core.config import settings
from app.embedders import HashEmbedder
from app.models import (
    KB_EMBEDDING_DIM,
    ExtractedSkill,
    InterviewSession,
    KBChunk,
    KBDocument,
    Question,
    Resume,
    User,
)
from app.services.citations import load_citations, text_hash
from app.services.kb_ingest import DEFAULT_KB_DIR, ingest_kb
from app.services.pipeline import _cited_sources, generate_questions


@pytest.fixture
def embedder() -> HashEmbedder:
    return HashEmbedder(dim=KB_EMBEDDING_DIM)


async def _session(db, *, skills: bool = True) -> InterviewSession:
    user = User(email="snap@example.test", hashed_password="x")
    db.add(user)
    await db.flush()
    resume = Resume(user_id=user.id, file_uri="inline://text", mime="text/plain")
    resume.text_content = "Built async FastAPI services on PostgreSQL and tuned indexes."
    db.add(resume)
    await db.flush()
    if skills:
        for name, evidence in [
            ("fastapi", "Built async FastAPI services"),
            ("sql", "tuned indexes for a reporting workload"),
        ]:
            db.add(
                ExtractedSkill(
                    resume_id=resume.id, name=name, confidence=0.9, evidence_span=evidence
                )
            )
    interview = InterviewSession(user_id=user.id, resume_id=resume.id)
    db.add(interview)
    await db.flush()
    return interview


@pytest.fixture
async def grounded_questions(db_session, provider, embedder, monkeypatch):
    """An interview generated with RAG on, against the real corpus."""
    await ingest_kb(db_session, embedder, kb_dir=DEFAULT_KB_DIR)
    monkeypatch.setattr(settings, "RAG_ENABLED", True)
    monkeypatch.setattr(settings, "RAG_MIN_SIMILARITY", 0.05)
    interview = await _session(db_session)
    await generate_questions(db_session, provider, interview.id, embedder=embedder)
    questions = list(await db_session.scalars(select(Question).order_by(Question.ordinal)))
    assert any(q.grounded for q in questions)
    return questions


# --- the snapshot ----------------------------------------------------------


async def test_a_grounded_question_stores_a_copy_of_each_cited_passage(
    db_session, grounded_questions
):
    chunks = {str(c.id): c for c in await db_session.scalars(select(KBChunk))}
    documents = {d.id: d for d in await db_session.scalars(select(KBDocument))}

    for question in grounded_questions:
        if not question.grounded:
            assert question.source_snapshots == []
            continue
        # One copy per citation, in citation order.
        assert [s["chunk_id"] for s in question.source_snapshots] == question.source_chunk_ids
        for snapshot in question.source_snapshots:
            chunk = chunks[snapshot["chunk_id"]]
            document = documents[chunk.document_id]
            assert snapshot["text"] == chunk.text
            assert snapshot["heading_path"] == chunk.heading_path
            assert snapshot["text_hash"] == text_hash(chunk.text)
            assert snapshot["source"] == document.source
            assert snapshot["document_title"] == document.title
            assert snapshot["document_hash"] == document.content_hash


async def test_citations_survive_the_knowledge_base_being_replaced(
    db_session, grounded_questions
):
    """The regression this exists for: a re-ingest must not erase the evidence."""
    before = await load_citations(db_session, grounded_questions)
    graded_against = {
        q.id: await _cited_sources(db_session, q) for q in grounded_questions
    }
    assert any(before.values())

    # What `ingest-kb` does to every chunk of a document whose file changed.
    await db_session.execute(delete(KBChunk))
    await db_session.flush()

    after = await load_citations(db_session, grounded_questions)
    assert after == before
    for question in grounded_questions:
        assert await _cited_sources(db_session, question) == graded_against[question.id]
        if question.grounded:
            assert after[question.id], "a grounded question must still show its sources"


async def test_a_question_from_before_snapshots_still_resolves_from_live_chunks(
    db_session, grounded_questions
):
    question = next(q for q in grounded_questions if q.grounded)
    expected = await load_citations(db_session, [question])
    sources = await _cited_sources(db_session, question)

    question.source_snapshots = []  # as written before the column existed
    assert await load_citations(db_session, [question]) == expected
    assert await _cited_sources(db_session, question) == sources
