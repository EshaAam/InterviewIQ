"""The skill evidence map: one candidate across all their interviews.

A report covers one interview. The map is built from the same stored rows and
says which skills the candidate has demonstrated, which are weak and which sit
on the résumé ungraded. These tests pin how it reads those rows, because a
wrong aggregate here looks exactly as confident as a right one.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient

from app.core.config import settings
from app.models import (
    Answer,
    Evaluation,
    ExtractedSkill,
    InterviewSession,
    Question,
    Resume,
    User,
)
from app.services.skill_map import build_skill_map, skill_key, status_for

API = settings.API_V1_PREFIX
START = datetime(2026, 11, 1, tzinfo=UTC)

PASSAGE = {
    "chunk_id": str(uuid.uuid4()),
    "topic": "sql",
    "heading_path": "SQL > Indexes",
    "text": "A B-tree index keeps keys sorted, so range scans are cheap.",
    "text_hash": "h",
    "source": "sql.md",
    "document_title": "SQL",
    "document_hash": "d",
    "url": "https://example.test/sql#indexes",
    "license": "",
}


async def _candidate(db, email: str = "map@example.test", skills=()) -> User:
    user = User(email=email, hashed_password="x")
    db.add(user)
    await db.flush()
    if skills:
        resume = Resume(user_id=user.id, file_uri="inline://text", mime="text/plain")
        db.add(resume)
        await db.flush()
        for name, confidence in skills:
            db.add(
                ExtractedSkill(
                    resume_id=resume.id,
                    name=name,
                    confidence=confidence,
                    evidence_span=f"used {name}",
                )
            )
        await db.flush()
    return user


async def _interview(db, user: User, *, day: int, graded: list[dict]) -> InterviewSession:
    """One finished interview. Each `graded` item is one question and its grade."""
    session = InterviewSession(user_id=user.id, created_at=START + timedelta(days=day))
    db.add(session)
    await db.flush()
    for ordinal, item in enumerate(graded):
        coverage = item.get("coverage", {"c1": 1.0})
        question = Question(
            session_id=session.id,
            ordinal=ordinal,
            text=f"A question about {item['topic']}",
            topic=item["topic"],
            expected_concepts=item.get("concepts", list(coverage)),
            source_snapshots=item.get("snapshots", []),
            grounded=bool(item.get("snapshots")),
        )
        db.add(question)
        await db.flush()
        answer = Answer(question_id=question.id, text="an answer", idempotency_key="k")
        db.add(answer)
        await db.flush()
        db.add(
            Evaluation(
                answer_id=answer.id,
                final_score=item["score"],
                concept_coverage=coverage,
                needs_review=item.get("needs_review", False),
            )
        )
    await db.flush()
    return session


def _by_name(skill_map) -> dict:
    return {skill.name: skill for skill in skill_map.skills}


# --- pure rules ------------------------------------------------------------


def test_status_uses_the_report_cut_offs():
    assert status_for(0.7) == "demonstrated"
    assert status_for(0.69) == "developing"
    assert status_for(0.5) == "developing"
    assert status_for(0.49) == "weak"


def test_skill_names_match_ignoring_case_and_spacing_only():
    assert skill_key("  FastAPI ") == skill_key("fastapi")
    assert skill_key("System  Design") == skill_key("system design")
    assert skill_key("sql") != skill_key("postgresql")


# --- the aggregate ---------------------------------------------------------


async def test_a_candidate_with_no_graded_interviews_gets_an_empty_map(db_session):
    user = await _candidate(db_session)

    skill_map = await build_skill_map(db_session, user.id)

    assert skill_map.sessions_assessed == 0
    assert skill_map.skills == []
    assert skill_map.not_assessed == []


async def test_status_follows_the_latest_interview_and_keeps_the_history(db_session):
    user = await _candidate(db_session)
    first = await _interview(db_session, user, day=0, graded=[{"topic": "sql", "score": 0.3}])
    second = await _interview(db_session, user, day=3, graded=[{"topic": "sql", "score": 0.8}])

    skill_map = await build_skill_map(db_session, user.id)

    [sql] = skill_map.skills
    assert sql.status == "demonstrated"  # not the 0.55 average of the two
    assert (sql.score, sql.previous, sql.best) == (0.8, 0.3, 0.8)
    assert (sql.sessions, sql.answers) == (2, 2)
    assert [a.session_id for a in sql.history] == [first.id, second.id]
    assert [a.score for a in sql.history] == [0.3, 0.8]
    # Evidence is the latest interview's questions only.
    assert {e.session_id for e in sql.evidence} == {second.id}
    assert skill_map.sessions_assessed == 2


async def test_a_skill_that_got_worse_is_reported_as_it_stands_now(db_session):
    user = await _candidate(db_session)
    await _interview(db_session, user, day=0, graded=[{"topic": "redis", "score": 0.9}])
    await _interview(db_session, user, day=1, graded=[{"topic": "redis", "score": 0.4}])

    [redis] = (await build_skill_map(db_session, user.id)).skills

    assert redis.status == "weak"
    assert (redis.score, redis.best) == (0.4, 0.9)


async def test_several_questions_on_one_skill_in_an_interview_are_averaged(db_session):
    user = await _candidate(db_session)
    await _interview(
        db_session,
        user,
        day=0,
        graded=[{"topic": "python", "score": 1.0}, {"topic": "python", "score": 0.5}],
    )

    [python] = (await build_skill_map(db_session, user.id)).skills

    assert python.score == 0.75
    assert (python.sessions, python.answers) == (1, 2)
    assert len(python.evidence) == 2


async def test_differently_cased_topics_are_one_skill(db_session):
    user = await _candidate(db_session)
    await _interview(db_session, user, day=0, graded=[{"topic": "fastapi", "score": 0.2}])
    await _interview(db_session, user, day=1, graded=[{"topic": "FastAPI", "score": 0.9}])

    [skill] = (await build_skill_map(db_session, user.id)).skills

    assert skill.name == "FastAPI"  # the latest interview's spelling
    assert skill.sessions == 2


async def test_skills_are_listed_weakest_first(db_session):
    user = await _candidate(db_session)
    await _interview(
        db_session,
        user,
        day=0,
        graded=[
            {"topic": "strong", "score": 0.9},
            {"topic": "weak", "score": 0.1},
            {"topic": "middling", "score": 0.6},
        ],
    )

    skill_map = await build_skill_map(db_session, user.id)

    assert [s.name for s in skill_map.skills] == ["weak", "middling", "strong"]
    assert [s.status for s in skill_map.skills] == ["weak", "developing", "demonstrated"]


async def test_an_answer_awaiting_review_marks_the_skill(db_session):
    user = await _candidate(db_session)
    await _interview(
        db_session,
        user,
        day=0,
        graded=[
            {"topic": "sql", "score": 0.5, "needs_review": True},
            {"topic": "python", "score": 0.9},
        ],
    )

    skills = _by_name(await build_skill_map(db_session, user.id))

    assert skills["sql"].needs_review is True
    assert skills["python"].needs_review is False


# --- concepts and sources --------------------------------------------------


async def test_concepts_keep_the_question_order_and_default_to_not_covered(db_session):
    user = await _candidate(db_session)
    await _interview(
        db_session,
        user,
        day=0,
        graded=[
            {
                "topic": "sql",
                "score": 0.5,
                "concepts": ["indexes", "joins", "isolation"],
                # The grader never reported "isolation".
                "coverage": {"joins": 0.0, "indexes": 1.0},
            }
        ],
    )

    [sql] = (await build_skill_map(db_session, user.id)).skills
    [evidence] = sql.evidence

    assert [(c.concept, c.covered) for c in evidence.concepts] == [
        ("indexes", 1.0),
        ("joins", 0.0),
        ("isolation", 0.0),
    ]


async def test_a_missed_concept_comes_with_the_passage_to_read(db_session):
    user = await _candidate(db_session)
    await _interview(
        db_session,
        user,
        day=0,
        graded=[
            {
                "topic": "sql",
                "score": 0.5,
                "coverage": {"indexes": 0.0, "joins": 1.0},
                "snapshots": [PASSAGE],
            },
            {
                "topic": "sql",
                "score": 1.0,
                "coverage": {"transactions": 1.0},
                "snapshots": [PASSAGE],
            },
        ],
    )

    [sql] = (await build_skill_map(db_session, user.id)).skills
    missed, covered = sql.evidence

    [source] = missed.sources
    assert source.heading_path == "SQL > Indexes"
    assert source.text == PASSAGE["text"]
    assert source.url == PASSAGE["url"]
    # Nothing was missed on the second question, so it has nothing to read up on.
    assert covered.sources == []


async def test_an_ungrounded_miss_simply_has_no_sources(db_session):
    user = await _candidate(db_session)
    await _interview(
        db_session, user, day=0, graded=[{"topic": "go", "score": 0.0, "coverage": {"c": 0.0}}]
    )

    [go] = (await build_skill_map(db_session, user.id)).skills

    assert go.evidence[0].sources == []


# --- not assessed ----------------------------------------------------------


async def test_resume_skills_nobody_asked_about_are_not_assessed(db_session):
    user = await _candidate(
        db_session, skills=[("Python", 0.9), ("kubernetes", 0.6), ("redis", 0.8)]
    )
    await _interview(db_session, user, day=0, graded=[{"topic": "python", "score": 0.9}])

    skill_map = await build_skill_map(db_session, user.id)

    assert [s.name for s in skill_map.skills] == ["python"]
    # Highest résumé confidence first; "Python" is graded, so it is not here.
    assert [s.name for s in skill_map.not_assessed] == ["redis", "kubernetes"]
    assert skill_map.not_assessed[0].evidence_span == "used redis"


async def test_a_skill_on_two_resumes_is_listed_once(db_session):
    user = await _candidate(db_session, skills=[("docker", 0.5)])
    second = Resume(user_id=user.id, file_uri="inline://text", mime="text/plain")
    db_session.add(second)
    await db_session.flush()
    db_session.add(
        ExtractedSkill(resume_id=second.id, name="Docker", confidence=0.7, evidence_span="")
    )
    await db_session.flush()

    skill_map = await build_skill_map(db_session, user.id)

    assert len(skill_map.not_assessed) == 1


async def test_a_question_asked_but_never_graded_is_not_evidence(db_session):
    user = await _candidate(db_session, skills=[("sql", 0.9)])
    session = InterviewSession(user_id=user.id)
    db_session.add(session)
    await db_session.flush()
    db_session.add(
        Question(session_id=session.id, ordinal=0, text="q", topic="sql", expected_concepts=["c"])
    )
    await db_session.flush()

    skill_map = await build_skill_map(db_session, user.id)

    assert skill_map.skills == []
    assert [s.name for s in skill_map.not_assessed] == ["sql"]


async def test_one_candidate_never_sees_another_candidates_interviews(db_session):
    mine = await _candidate(db_session, "mine@example.test", skills=[("python", 0.9)])
    theirs = await _candidate(db_session, "theirs@example.test", skills=[("rust", 0.9)])
    await _interview(db_session, theirs, day=0, graded=[{"topic": "rust", "score": 0.9}])

    skill_map = await build_skill_map(db_session, mine.id)

    assert skill_map.skills == []
    assert [s.name for s in skill_map.not_assessed] == ["python"]


# --- over HTTP -------------------------------------------------------------


async def _finished_interview(client: AsyncClient) -> str:
    resume = await client.post(
        f"{API}/resumes",
        json={"text": "Senior engineer with python, fastapi, postgresql and redis experience."},
    )
    session_id = (
        await client.post(f"{API}/sessions", json={"resume_id": resume.json()["id"]})
    ).json()["id"]
    await client.post(f"{API}/sessions/{session_id}/start")
    total = (await client.get(f"{API}/sessions/{session_id}")).json()["total_questions"]
    for i in range(total):
        question = (await client.get(f"{API}/sessions/{session_id}/questions/next")).json()
        await client.post(
            f"{API}/sessions/{session_id}/answers",
            json={
                "question_id": question["id"],
                "text": f"{question['topic']} fundamentals, tradeoffs, in production.",
            },
            headers={"Idempotency-Key": f"key-{i}"},
        )
    finished = await client.post(f"{API}/sessions/{session_id}/finish")
    assert finished.json()["state"] in {"COMPLETED", "NEEDS_HUMAN_REVIEW"}
    return session_id


async def test_the_map_needs_a_signed_in_user(client: AsyncClient):
    assert (await client.get(f"{API}/skill-map")).status_code == 401


async def test_a_real_interview_shows_up_in_the_candidates_map(auth_client: AsyncClient):
    session_id = await _finished_interview(auth_client)
    report = (await auth_client.get(f"{API}/sessions/{session_id}/report")).json()

    response = await auth_client.get(f"{API}/skill-map")

    assert response.status_code == 200
    body = response.json()
    assert body["candidate_email"] is None
    assert body["sessions_assessed"] == 1
    # One skill per report topic, carrying the report's own score.
    assert {s["name"]: s["score"] for s in body["skills"]} == report["per_topic"]
    for skill in body["skills"]:
        assert skill["history"][0]["session_id"] == session_id
        assert skill["evidence"][0]["concepts"]


async def test_a_recruiter_reads_any_candidates_map_and_a_candidate_cannot(
    auth_client: AsyncClient, recruiter
):
    await _finished_interview(auth_client)
    candidate_id = (await auth_client.get(f"{API}/auth/me")).json()["id"]
    path = f"{API}/recruiter/candidates/{candidate_id}/skill-map"

    assert (await auth_client.get(path)).status_code == 403

    headers = await recruiter("rec-map@example.com")
    response = await auth_client.get(path, headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["candidate_email"] == "cand@example.com"
    assert body["skills"]

    missing = await auth_client.get(
        f"{API}/recruiter/candidates/{uuid.uuid4()}/skill-map", headers=headers
    )
    assert missing.status_code == 404
