"""Job-description matching and the knowledge-base coverage loop.

Both run entirely on the local embedder — no provider call anywhere in this
file, and that is a feature rather than a test convenience. The free Gemini
tier allows twenty requests per day, so a feature that spent several of them
re-deriving what cosine similarity answers for nothing would not be usable.
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
    InterviewSession,
    KBCoverageMiss,
    Question,
    Resume,
    User,
)
from app.models.resume import ParseStatus
from app.models.session import SessionState
from app.services.grounding import build_context
from app.services.job_match import (
    MAX_REQUIREMENTS,
    RequirementMatch,
    gaps,
    match,
    split_requirements,
)
from app.services.kb_ingest import DEFAULT_KB_DIR, ingest_kb
from app.services.pipeline import generate_questions

JD = """About the role:
- Build and maintain async Python services on PostgreSQL
- Operate Kubernetes clusters and write Helm charts
- Short
"""


@pytest.fixture
def embedder() -> HashEmbedder:
    return HashEmbedder(dim=KB_EMBEDDING_DIM)


# --- splitting -------------------------------------------------------------


def test_bullets_become_requirements():
    assert split_requirements(JD) == [
        "Build and maintain async Python services on PostgreSQL",
        "Operate Kubernetes clusters and write Helm charts",
    ]


def test_headings_and_short_lines_are_dropped():
    """"Requirements:" is a heading introducing a list, not a requirement."""
    text = "Requirements:\n- Java\n- Deep experience with distributed systems design\n"
    assert split_requirements(text) == ["Deep experience with distributed systems design"]


@pytest.mark.parametrize("bullet", ["-", "*", "•", "1.", "2)"])
def test_every_common_bullet_style_is_stripped(bullet):
    line = f"{bullet} Deep experience with distributed systems design"
    assert split_requirements(line) == ["Deep experience with distributed systems design"]


def test_a_long_job_description_is_capped():
    """An unbounded JD would dominate the retrieval budget and the prompt."""
    text = "\n".join(f"- Requirement number {i} with enough length here" for i in range(60))
    assert len(split_requirements(text)) == MAX_REQUIREMENTS


def test_an_empty_description_yields_nothing():
    assert split_requirements("\n\n  \n") == []


# --- matching --------------------------------------------------------------


async def test_a_requirement_the_resume_evidences_is_covered(embedder, monkeypatch):
    monkeypatch.setattr(settings, "JD_MATCH_THRESHOLD", 0.3)
    skills = [
        ExtractedSkill(
            resume_id=uuid.uuid4(),
            name="python",
            confidence=0.9,
            evidence_span="Build and maintain async Python services on PostgreSQL",
        )
    ]
    [result] = await match(
        embedder, "- Build and maintain async Python services on PostgreSQL", skills
    )
    assert result.covered
    assert result.best_skill == "python"


async def test_a_requirement_nothing_supports_is_a_gap(embedder, monkeypatch):
    monkeypatch.setattr(settings, "JD_MATCH_THRESHOLD", 0.5)
    skills = [
        ExtractedSkill(
            resume_id=uuid.uuid4(),
            name="python",
            confidence=0.9,
            evidence_span="wrote Python services",
        )
    ]
    matches = await match(embedder, JD, skills)
    assert "Operate Kubernetes clusters and write Helm charts" in gaps(matches)


async def test_a_resume_with_no_skills_makes_everything_a_gap(embedder):
    """The correct reading, not an error: nothing on the résumé supports anything."""
    matches = await match(embedder, JD, [])
    assert len(matches) == 2
    assert all(m.similarity == 0.0 and m.best_skill is None for m in matches)
    assert len(gaps(matches)) == 2


async def test_no_job_description_means_no_matches(embedder):
    assert await match(embedder, "", []) == []


def test_gaps_are_weakest_first():
    """The retrieval and prompt budgets are finite, so if something must be
    dropped it should be what the candidate is closest to demonstrating."""
    matches = [
        RequirementMatch("close", "python", 0.60),
        RequirementMatch("distant", None, 0.10),
        RequirementMatch("middling", "sql", 0.40),
    ]
    assert gaps(matches) == ["distant", "middling", "close"]


def test_a_covered_requirement_is_not_a_gap():
    assert gaps([RequirementMatch("done", "python", 0.99)]) == []


# --- gaps steer retrieval --------------------------------------------------


async def test_gap_queries_are_retrieved_before_skills(db_session, embedder, monkeypatch):
    """When the budget runs out it must be the already-evidenced skills that
    get dropped, not the requirements the interview exists to probe."""
    await ingest_kb(db_session, embedder, kb_dir=DEFAULT_KB_DIR)
    monkeypatch.setattr(settings, "RAG_MIN_SIMILARITY", 0.05)

    skills = [
        ExtractedSkill(
            resume_id=uuid.uuid4(), name="javascript", confidence=0.9,
            evidence_span="the browser event loop",
        )
    ]
    context = await build_context(
        db_session,
        embedder,
        skills,
        extra_queries=["Postgres index tuning and query plans"],
        k=1,
        token_budget=400,
    )
    # The first label is the first thing packed, and gaps are packed first, so it
    # must be the gap query's own top hit. Compared against a live search rather
    # than a fixed topic, so adding knowledge-base files can't break it.
    from app.services.retrieval import search

    [gap_top] = await search(
        db_session, embedder, "Postgres index tuning and query plans", k=1
    )
    first = next(iter(context.sources.values()))
    assert first.chunk_id == gap_top.chunk_id


# --- the coverage loop -----------------------------------------------------


async def test_an_uncovered_skill_is_recorded_for_the_corpus_backlog(
    db_session, provider, embedder, monkeypatch
):
    await ingest_kb(db_session, embedder, kb_dir=DEFAULT_KB_DIR)
    monkeypatch.setattr(settings, "RAG_ENABLED", True)
    monkeypatch.setattr(settings, "RAG_MIN_SIMILARITY", 0.999)  # nothing can match

    user = User(email="gap@example.com", hashed_password="x")
    db_session.add(user)
    await db_session.flush()
    resume = Resume(user_id=user.id, file_uri="inline://text", mime="text/plain")
    # Already parsed, so `parse_resume` short-circuits and leaves the skills
    # below alone instead of re-extracting them from the fake provider.
    resume.parse_status = ParseStatus.parsed
    resume.text_content = "Kubernetes operator work."
    db_session.add(resume)
    await db_session.flush()
    db_session.add(
        ExtractedSkill(
            resume_id=resume.id, name="kubernetes", confidence=0.9,
            evidence_span="Kubernetes operator work",
        )
    )
    session = InterviewSession(user_id=user.id, resume_id=resume.id)
    db_session.add(session)
    await db_session.flush()

    await generate_questions(db_session, provider, session.id, embedder=embedder)

    misses = list(await db_session.scalars(select(KBCoverageMiss)))
    assert [m.skill for m in misses] == ["kubernetes"]
    assert "Kubernetes operator work" in misses[0].query
    assert misses[0].session_id == session.id


async def test_a_covered_skill_records_no_miss(db_session, provider, embedder, monkeypatch):
    await ingest_kb(db_session, embedder, kb_dir=DEFAULT_KB_DIR)
    monkeypatch.setattr(settings, "RAG_ENABLED", True)
    monkeypatch.setattr(settings, "RAG_MIN_SIMILARITY", 0.0)

    user = User(email="ok@example.com", hashed_password="x")
    db_session.add(user)
    await db_session.flush()
    resume = Resume(user_id=user.id, file_uri="inline://text", mime="text/plain")
    # Already parsed, so `parse_resume` short-circuits and leaves the skills
    # below alone instead of re-extracting them from the fake provider.
    resume.parse_status = ParseStatus.parsed
    resume.text_content = "Python and the GIL."
    db_session.add(resume)
    await db_session.flush()
    db_session.add(
        ExtractedSkill(
            resume_id=resume.id, name="python", confidence=0.9,
            evidence_span="Python concurrency and the GIL",
        )
    )
    session = InterviewSession(user_id=user.id, resume_id=resume.id)
    db_session.add(session)
    await db_session.flush()

    await generate_questions(db_session, provider, session.id, embedder=embedder)
    assert list(await db_session.scalars(select(KBCoverageMiss))) == []


# --- end to end ------------------------------------------------------------


async def test_a_job_description_records_the_gaps_it_targeted(
    db_session, provider, embedder, monkeypatch
):
    """Stored, not recomputed, so a recruiter sees what the questions actually
    targeted rather than what they would target against today's thresholds."""
    await ingest_kb(db_session, embedder, kb_dir=DEFAULT_KB_DIR)
    monkeypatch.setattr(settings, "RAG_ENABLED", True)
    monkeypatch.setattr(settings, "RAG_MIN_SIMILARITY", 0.05)
    monkeypatch.setattr(settings, "JD_MATCH_THRESHOLD", 0.95)  # nothing counts as covered

    user = User(email="jd@example.com", hashed_password="x")
    db_session.add(user)
    await db_session.flush()
    resume = Resume(user_id=user.id, file_uri="inline://text", mime="text/plain")
    # Already parsed, so `parse_resume` short-circuits and leaves the skills
    # below alone instead of re-extracting them from the fake provider.
    resume.parse_status = ParseStatus.parsed
    resume.text_content = "Wrote some Python."
    db_session.add(resume)
    await db_session.flush()
    db_session.add(
        ExtractedSkill(
            resume_id=resume.id, name="python", confidence=0.9, evidence_span="Wrote Python"
        )
    )
    session = InterviewSession(
        user_id=user.id, resume_id=resume.id, job_description=JD
    )
    db_session.add(session)
    await db_session.flush()

    result = await generate_questions(db_session, provider, session.id, embedder=embedder)

    assert result.state is SessionState.READY
    assert "Operate Kubernetes clusters and write Helm charts" in result.jd_gaps
    assert list(await db_session.scalars(select(Question)))


async def test_a_session_without_a_job_description_targets_no_gaps(
    db_session, provider, embedder, monkeypatch
):
    monkeypatch.setattr(settings, "RAG_ENABLED", True)
    user = User(email="nojd@example.com", hashed_password="x")
    db_session.add(user)
    await db_session.flush()
    resume = Resume(user_id=user.id, file_uri="inline://text", mime="text/plain")
    db_session.add(resume)
    await db_session.flush()
    session = InterviewSession(user_id=user.id, resume_id=resume.id)
    db_session.add(session)
    await db_session.flush()

    result = await generate_questions(db_session, provider, session.id, embedder=embedder)
    assert result.jd_gaps == []
