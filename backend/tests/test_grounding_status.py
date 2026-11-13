"""Why a question is or is not grounded.

"Not grounded" used to be one boolean standing in for several situations a
reviewer reads differently: retrieval was switched off, the corpus had nothing
relevant, there was no skill to look anything up for, or the model was handed
sources and cited none of them. Each is recorded as its own status.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.embedders import HashEmbedder
from app.models import (
    KB_EMBEDDING_DIM,
    ExtractedSkill,
    GroundingStatus,
    InterviewSession,
    Question,
    Resume,
    User,
)
from app.services.grounding import GroundedContext
from app.services.kb_ingest import DEFAULT_KB_DIR, ingest_kb
from app.services.pipeline import generate_questions
from app.services.retrieval import RetrievedChunk


@pytest.fixture
def embedder() -> HashEmbedder:
    return HashEmbedder(dim=KB_EMBEDDING_DIM)


async def _session(db, *, skills: bool = True) -> InterviewSession:
    user = User(email="status@example.test", hashed_password="x")
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


async def test_grounded_questions_are_marked_grounded(grounded_questions):
    for question in grounded_questions:
        expected = GroundingStatus.GROUNDED if question.grounded else GroundingStatus.UNCITED
        assert question.grounding_status == expected


async def test_rag_off_is_recorded_as_the_reason(db_session, provider, embedder):
    assert settings.RAG_ENABLED is False
    interview = await _session(db_session)
    await generate_questions(db_session, provider, interview.id, embedder=embedder)

    questions = list(await db_session.scalars(select(Question)))
    assert questions
    assert {q.grounding_status for q in questions} == {GroundingStatus.RAG_DISABLED}


async def test_a_corpus_that_covers_nothing_is_recorded_as_the_reason(
    db_session, provider, embedder, monkeypatch
):
    await ingest_kb(db_session, embedder, kb_dir=DEFAULT_KB_DIR)
    monkeypatch.setattr(settings, "RAG_ENABLED", True)
    monkeypatch.setattr(settings, "RAG_MIN_SIMILARITY", 0.999)  # nothing can clear it
    interview = await _session(db_session)
    await generate_questions(db_session, provider, interview.id, embedder=embedder)

    questions = list(await db_session.scalars(select(Question)))
    assert questions
    assert {q.grounding_status for q in questions} == {GroundingStatus.NOT_COVERED}
    assert all(q.source_snapshots == [] for q in questions)


def _context_with_one_source() -> GroundedContext:
    context = GroundedContext(queried=1)
    context.sources["S1"] = RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        topic="python",
        heading_path="Python > The GIL",
        text="Only one thread executes bytecode at a time.",
        token_estimate=10,
        score=0.03,
        similarity=0.8,
    )
    return context


def test_each_reason_is_told_apart():
    offered = _context_with_one_source()
    assert offered.status_for(["some-id"], rag_enabled=True) is GroundingStatus.GROUNDED
    # Sources were in the prompt and the model cited none of them.
    assert offered.status_for([], rag_enabled=True) is GroundingStatus.UNCITED
    # Retrieval ran for something and found nothing relevant enough.
    assert GroundedContext(queried=3).status_for([], rag_enabled=True) is (
        GroundingStatus.NOT_COVERED
    )
    # Retrieval was on, but there was no skill to look anything up for.
    assert GroundedContext().status_for([], rag_enabled=True) is GroundingStatus.NO_SKILLS
    assert GroundedContext().status_for([], rag_enabled=False) is GroundingStatus.RAG_DISABLED


async def test_the_status_defaults_from_the_grounded_flag(db_session):
    """Rows built with only the boolean stay consistent with it."""
    interview = await _session(db_session, skills=False)
    db_session.add_all(
        [
            Question(session_id=interview.id, ordinal=0, text="a", topic="t", grounded=True),
            Question(session_id=interview.id, ordinal=1, text="b", topic="t", grounded=False),
        ]
    )
    await db_session.flush()
    by_ordinal = {
        q.ordinal: q.grounding_status for q in await db_session.scalars(select(Question))
    }
    assert by_ordinal == {0: GroundingStatus.GROUNDED, 1: GroundingStatus.UNKNOWN}
