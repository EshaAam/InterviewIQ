"""End-to-end interview flow on the fake provider — fully offline.

Drives the real HTTP surface with the pipeline running inline (see conftest's
InlineDispatcher). Covers the happy path, answer idempotency, and the
malformed-output -> FAILED dead-letter path.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy import func, select

from app.core.config import settings
from app.models import Answer
from app.providers import FakeProvider, LLMValidationError
from app.schemas.pipeline import QuestionGenerationResult

API = settings.API_V1_PREFIX
RESUME_TEXT = "Senior engineer with python, fastapi, postgresql and redis experience."


async def _make_resume(client: AsyncClient) -> str:
    resp = await client.post(f"{API}/resumes", json={"text": RESUME_TEXT})
    assert resp.status_code == 202
    return resp.json()["id"]


async def _make_ready_session(client: AsyncClient, resume_id: str) -> str:
    resp = await client.post(f"{API}/sessions", json={"resume_id": resume_id})
    assert resp.status_code == 202
    return resp.json()["id"]


async def test_resume_parses_and_extracts_skills(auth_client: AsyncClient) -> None:
    resume_id = await _make_resume(auth_client)
    resp = await auth_client.get(f"{API}/resumes/{resume_id}")
    body = resp.json()
    assert body["parse_status"] == "parsed"
    names = {s["name"] for s in body["skills"]}
    assert {"python", "fastapi", "postgresql"} <= names


async def test_full_happy_path_to_report(auth_client: AsyncClient) -> None:
    resume_id = await _make_resume(auth_client)
    session_id = await _make_ready_session(auth_client, resume_id)

    # Questions were generated inline -> session is READY.
    got = (await auth_client.get(f"{API}/sessions/{session_id}")).json()
    assert got["state"] == "READY"
    assert got["total_questions"] >= 1

    # Start the interview.
    started = await auth_client.post(f"{API}/sessions/{session_id}/start")
    assert started.status_code == 200
    assert started.json()["state"] == "IN_PROGRESS"
    assert started.json()["expires_at"] is not None

    # Answer every question, fetched via /questions/next.
    for i in range(got["total_questions"]):
        nxt = await auth_client.get(f"{API}/sessions/{session_id}/questions/next")
        assert nxt.status_code == 200
        question = nxt.json()
        ans = await auth_client.post(
            f"{API}/sessions/{session_id}/answers",
            json={
                "question_id": question["id"],
                "text": f"{question['topic']} fundamentals, tradeoffs, in production.",
            },
            headers={"Idempotency-Key": f"key-{i}"},
        )
        assert ans.status_code == 202

    # No more questions.
    empty = await auth_client.get(f"{API}/sessions/{session_id}/questions/next")
    assert empty.status_code == 404

    # Finish -> report built inline -> COMPLETED.
    finished = await auth_client.post(f"{API}/sessions/{session_id}/finish")
    assert finished.json()["state"] == "COMPLETED"

    report = await auth_client.get(f"{API}/sessions/{session_id}/report")
    assert report.status_code == 200
    body = report.json()
    assert 0.0 <= body["overall"] <= 1.0
    assert len(body["per_topic"]) == got["total_questions"]


async def test_answer_submission_is_idempotent(
    auth_client: AsyncClient, db_session
) -> None:
    resume_id = await _make_resume(auth_client)
    session_id = await _make_ready_session(auth_client, resume_id)
    await auth_client.post(f"{API}/sessions/{session_id}/start")
    question = (
        await auth_client.get(f"{API}/sessions/{session_id}/questions/next")
    ).json()

    payload = {"question_id": question["id"], "text": "my answer"}
    headers = {"Idempotency-Key": "same-key"}

    first = await auth_client.post(
        f"{API}/sessions/{session_id}/answers", json=payload, headers=headers
    )
    second = await auth_client.post(
        f"{API}/sessions/{session_id}/answers", json=payload, headers=headers
    )

    assert first.status_code == 202 and second.status_code == 202
    assert first.json()["id"] == second.json()["id"]  # same row returned

    count = await db_session.scalar(
        select(func.count(Answer.id)).where(
            Answer.question_id == uuid.UUID(question["id"])
        )
    )
    assert count == 1  # exactly one Answer row despite two submissions


async def test_answers_require_idempotency_key(auth_client: AsyncClient) -> None:
    resume_id = await _make_resume(auth_client)
    session_id = await _make_ready_session(auth_client, resume_id)
    await auth_client.post(f"{API}/sessions/{session_id}/start")
    question = (
        await auth_client.get(f"{API}/sessions/{session_id}/questions/next")
    ).json()

    resp = await auth_client.post(
        f"{API}/sessions/{session_id}/answers",
        json={"question_id": question["id"], "text": "x"},
    )  # no Idempotency-Key header
    assert resp.status_code == 422


async def test_malformed_generation_lands_session_in_failed(
    auth_client: AsyncClient, provider: FakeProvider
) -> None:
    # Force the question-generation call to return unparseable output.
    provider.register(
        QuestionGenerationResult, LLMValidationError("unparseable model output")
    )
    resume_id = await _make_resume(auth_client)
    resp = await auth_client.post(f"{API}/sessions", json={"resume_id": resume_id})
    assert resp.status_code == 202  # request itself never crashes

    got = (await auth_client.get(f"{API}/sessions/{resp.json()['id']}")).json()
    assert got["state"] == "FAILED"  # not stuck
    assert "generation failed" in got["failure_reason"]


async def test_cannot_start_before_ready(
    auth_client: AsyncClient, provider: FakeProvider
) -> None:
    # A failed session is not READY -> start is a 409, not a 500.
    provider.register(QuestionGenerationResult, LLMValidationError("boom"))
    resume_id = await _make_resume(auth_client)
    session_id = (
        await auth_client.post(f"{API}/sessions", json={"resume_id": resume_id})
    ).json()["id"]

    resp = await auth_client.post(f"{API}/sessions/{session_id}/start")
    assert resp.status_code == 409


async def test_requires_authentication(client: AsyncClient) -> None:
    resp = await client.post(f"{API}/resumes", json={"text": "hi"})
    assert resp.status_code == 401
