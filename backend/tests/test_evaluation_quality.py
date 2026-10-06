"""Phase 4 integration — divergence routes to human review; recruiter queue + override."""

from __future__ import annotations

from httpx import AsyncClient

from app.core.config import settings
from app.providers import FakeProvider
from app.schemas.pipeline import (
    QUESTIONS_PER_INTERVIEW,
    AnswerEvaluationResult,
    ConceptCoverage,
    RubricScores,
)

API = settings.API_V1_PREFIX


async def _login(client: AsyncClient, email: str) -> dict:
    """Register (always a candidate) and sign in. Recruiters: the `recruiter` fixture."""
    payload = {"email": email, "password": "hunter2secret"}
    await client.post(f"{API}/auth/register", json=payload)
    tok = (
        await client.post(
            f"{API}/auth/login", json={"email": email, "password": "hunter2secret"}
        )
    ).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _force_divergence(provider: FakeProvider) -> None:
    # LLM insists on full coverage; answers below share no words with the
    # concepts, so the deterministic pass scores ~0 -> the passes diverge.
    provider.register(
        AnswerEvaluationResult,
        AnswerEvaluationResult(
            concept_coverage=[ConceptCoverage(concept="x", covered=1.0)],
            llm_scores=RubricScores(correctness=1.0, depth=1.0, clarity=1.0),
            confidence=0.9,
        ),
    )


async def _run_diverging_interview(
    client: AsyncClient, headers: dict, resume: str = "python"
) -> str:
    rid = (
        await client.post(f"{API}/resumes", json={"text": resume}, headers=headers)
    ).json()["id"]
    sid = (
        await client.post(
            f"{API}/sessions", json={"resume_id": rid}, headers=headers
        )
    ).json()["id"]
    await client.post(f"{API}/sessions/{sid}/start", headers=headers)
    total = (await client.get(f"{API}/sessions/{sid}", headers=headers)).json()[
        "total_questions"
    ]
    for i in range(total):
        q = (
            await client.get(f"{API}/sessions/{sid}/questions/next", headers=headers)
        ).json()
        await client.post(
            f"{API}/sessions/{sid}/answers",
            json={"question_id": q["id"], "text": "zzz qqq unrelated"},
            headers={**headers, "Idempotency-Key": f"k{i}"},
        )
    await client.post(f"{API}/sessions/{sid}/finish", headers=headers)
    return sid


async def test_divergence_routes_session_to_human_review(
    client: AsyncClient, provider: FakeProvider
) -> None:
    _force_divergence(provider)
    headers = await _login(client, "cand@example.com")
    sid = await _run_diverging_interview(client, headers)

    state = (await client.get(f"{API}/sessions/{sid}", headers=headers)).json()["state"]
    assert state == "NEEDS_HUMAN_REVIEW"


async def test_reruns_increment_run_count_on_divergence(
    client: AsyncClient, provider: FakeProvider, db_session
) -> None:
    from sqlalchemy import select

    from app.models import Evaluation

    _force_divergence(provider)
    headers = await _login(client, "cand2@example.com")
    await _run_diverging_interview(client, headers)

    evals = list(await db_session.scalars(select(Evaluation)))
    assert evals and all(e.needs_review for e in evals)
    # 1 initial + EVAL_RERUN_COUNT re-runs.
    assert all(e.run_count == 1 + settings.EVAL_RERUN_COUNT for e in evals)


async def test_recruiter_can_list_queue_and_override(
    client: AsyncClient, provider: FakeProvider, recruiter
) -> None:
    _force_divergence(provider)
    cand = await _login(client, "cand3@example.com")
    await _run_diverging_interview(client, cand)

    rec = await recruiter("recruiter@example.com")
    page = (
        await client.get(f"{API}/recruiter/evaluations?needs_review=true", headers=rec)
    ).json()
    queue = page["items"]
    assert len(queue) >= 1
    assert page["total"] >= len(queue)
    assert queue[0]["candidate_email"] == "cand3@example.com"
    ev_id = queue[0]["id"]

    resp = await client.post(
        f"{API}/recruiter/evaluations/{ev_id}/override",
        json={"final_score": 0.85, "note": "answer was fine on manual read"},
        headers=rec,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["final_score"] == 0.85
    assert body["needs_review"] is False
    assert body["overridden_by_id"] is not None


async def test_recruiter_can_filter_sessions_by_state(
    client: AsyncClient, provider: FakeProvider, recruiter
) -> None:
    _force_divergence(provider)
    cand = await _login(client, "cand4@example.com")
    await _run_diverging_interview(client, cand)

    rec = await recruiter("recruiter2@example.com")
    rows = (
        await client.get(
            f"{API}/recruiter/sessions?state=NEEDS_HUMAN_REVIEW", headers=rec
        )
    ).json()
    assert len(rows) >= 1
    assert all(r["state"] == "NEEDS_HUMAN_REVIEW" for r in rows)


async def test_recruiter_routes_reject_candidates(client: AsyncClient) -> None:
    cand = await _login(client, "cand5@example.com")  # default role
    resp = await client.get(f"{API}/recruiter/sessions", headers=cand)
    assert resp.status_code == 403


# --- F8: overrides flow into the report; candidate list; recruiter drill-down ---


async def _queue_for(client: AsyncClient, rec: dict, session_id: str) -> list[dict]:
    page = (
        await client.get(f"{API}/recruiter/evaluations?limit=100", headers=rec)
    ).json()
    return [item for item in page["items"] if item["session_id"] == session_id]


async def test_clearing_every_flag_completes_session_and_rebuilds_report(
    client: AsyncClient, provider: FakeProvider, recruiter
) -> None:
    _force_divergence(provider)
    cand = await _login(client, "cand6@example.com")
    # Every question diverges, so every answer is flagged.
    sid = await _run_diverging_interview(client, cand, resume="python and fastapi")
    before = (await client.get(f"{API}/sessions/{sid}/report", headers=cand)).json()
    assert before["human_reviewed"] is False

    rec = await recruiter("recruiter3@example.com")
    flagged = await _queue_for(client, rec, sid)
    assert len(flagged) == QUESTIONS_PER_INTERVIEW

    # Clearing all but the last keeps the session in review...
    for item in flagged[:-1]:
        body = (
            await client.post(
                f"{API}/recruiter/evaluations/{item['id']}/override",
                json={"final_score": 1.0, "note": None},
                headers=rec,
            )
        ).json()
        assert body["session_state"] == "NEEDS_HUMAN_REVIEW"

    # ...and clearing the last one completes it.
    body = (
        await client.post(
            f"{API}/recruiter/evaluations/{flagged[-1]['id']}/override",
            json={"final_score": 1.0, "note": "read it, all fine"},
            headers=rec,
        )
    ).json()
    assert body["session_state"] == "COMPLETED"

    state = (await client.get(f"{API}/sessions/{sid}", headers=cand)).json()["state"]
    assert state == "COMPLETED"
    after = (await client.get(f"{API}/sessions/{sid}/report", headers=cand)).json()
    assert after["human_reviewed"] is True
    assert after["overall"] == 1.0
    assert after["overall"] != before["overall"]
    assert set(after["strengths"]) == set(after["per_topic"])


async def test_candidate_lists_only_their_own_sessions(
    client: AsyncClient, provider: FakeProvider
) -> None:
    _force_divergence(provider)
    mine = await _login(client, "cand7@example.com")
    other = await _login(client, "cand8@example.com")
    sid = await _run_diverging_interview(client, mine)
    await _run_diverging_interview(client, other)

    rows = (await client.get(f"{API}/sessions", headers=mine)).json()
    assert [r["id"] for r in rows] == [sid]
    assert rows[0]["state"] == "NEEDS_HUMAN_REVIEW"
    assert rows[0]["overall"] is not None
    assert rows[0]["answered"] == rows[0]["total_questions"] > 0
    # Distinct topics, one entry each, and the same on the single-session read.
    assert rows[0]["topics"] and len(set(rows[0]["topics"])) == len(rows[0]["topics"])
    assert rows[0]["updated_at"] is not None
    single = (await client.get(f"{API}/sessions/{sid}", headers=mine)).json()
    assert single["topics"] == rows[0]["topics"]


async def test_recruiter_session_detail(
    client: AsyncClient, provider: FakeProvider, recruiter
) -> None:
    _force_divergence(provider)
    cand = await _login(client, "cand9@example.com")
    sid = await _run_diverging_interview(client, cand)
    rec = await recruiter("recruiter4@example.com")

    detail = (await client.get(f"{API}/recruiter/sessions/{sid}", headers=rec)).json()
    assert detail["candidate_email"] == "cand9@example.com"
    assert detail["state"] == "NEEDS_HUMAN_REVIEW"
    assert detail["report"] is not None
    assert [q["ordinal"] for q in detail["questions"]] == sorted(
        q["ordinal"] for q in detail["questions"]
    )
    for question in detail["questions"]:
        assert question["expected_concepts"]
        (answer,) = question["answers"]
        assert answer["text"] == "zzz qqq unrelated"
        assert answer["evaluation"]["needs_review"] is True

    rows = (await client.get(f"{API}/recruiter/sessions", headers=rec)).json()
    assert any(r["candidate_email"] == "cand9@example.com" for r in rows)

    missing = await client.get(
        f"{API}/recruiter/sessions/00000000-0000-0000-0000-000000000000", headers=rec
    )
    assert missing.status_code == 404
    forbidden = await client.get(f"{API}/recruiter/sessions/{sid}", headers=cand)
    assert forbidden.status_code == 403
