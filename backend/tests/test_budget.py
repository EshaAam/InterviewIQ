"""Per-user token budget — rejected with 429 before spending, via the ledger.

Phase 6: the budget sums the ledger by `user_id` (so résumé parsing counts),
gates *starting* work (résumés, sessions) but never answering or finishing,
and the ledger itself is accurate: cache hits, circuit-open fast-fails and
divergence re-runs are each charged for what they actually cost.
"""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import func, select

from app.core.config import settings
from app.models import LLMCall
from app.providers.base import LLMCircuitOpen
from app.providers.cache import InMemoryCache
from app.providers.wrappers import CachingProvider
from app.schemas.pipeline import SkillExtractionResult
from app.services.budget import tokens_used_today

API = settings.API_V1_PREFIX
RESUME_TEXT = "python fastapi postgresql redis docker celery engineer"


async def _me(client: AsyncClient) -> str:
    return (await client.get(f"{API}/auth/me")).json()["id"]


async def _spend_some(client: AsyncClient) -> str:
    resume_id = (
        await client.post(f"{API}/resumes", json={"text": RESUME_TEXT})
    ).json()["id"]
    # Creating a session runs generate_questions inline, writing LLMCall rows.
    return (
        await client.post(f"{API}/sessions", json={"resume_id": resume_id})
    ).json()["id"]


async def test_over_budget_blocks_new_work(auth_client: AsyncClient, monkeypatch) -> None:
    await _spend_some(auth_client)  # some tokens now on the ledger
    monkeypatch.setattr(settings, "USER_DAILY_TOKEN_BUDGET", 1)

    # Both ways of starting new work are refused: a résumé (parsing spends
    # tokens) and a session.
    assert (
        await auth_client.post(f"{API}/resumes", json={"text": RESUME_TEXT})
    ).status_code == 429
    # The guard runs before the handler, so it answers 429 before even
    # looking the résumé up.
    resp = await auth_client.post(
        f"{API}/sessions", json={"resume_id": "00000000-0000-0000-0000-000000000000"}
    )
    assert resp.status_code == 429


async def test_interview_under_way_can_always_finish(
    auth_client: AsyncClient, monkeypatch
) -> None:
    sid = await _spend_some(auth_client)
    await auth_client.post(f"{API}/sessions/{sid}/start")
    monkeypatch.setattr(settings, "USER_DAILY_TOKEN_BUDGET", 1)  # now over the cap

    q = (await auth_client.get(f"{API}/sessions/{sid}/questions/next")).json()
    answered = await auth_client.post(
        f"{API}/sessions/{sid}/answers",
        json={"question_id": q["id"], "text": "an answer"},
        headers={"Idempotency-Key": "k1"},
    )
    assert answered.status_code == 202
    finished = await auth_client.post(f"{API}/sessions/{sid}/finish")
    assert finished.status_code == 200


async def test_within_budget_is_allowed(auth_client: AsyncClient) -> None:
    # Default budget is generous; a normal create succeeds (202).
    resume_id = (
        await auth_client.post(f"{API}/resumes", json={"text": RESUME_TEXT})
    ).json()["id"]
    resp = await auth_client.post(f"{API}/sessions", json={"resume_id": resume_id})
    assert resp.status_code == 202


async def test_ledger_accumulates_tokens_and_cost(
    auth_client: AsyncClient, db_session
) -> None:
    await _spend_some(auth_client)
    total_tokens = await db_session.scalar(
        select(func.sum(LLMCall.prompt_tokens + LLMCall.completion_tokens))
    )
    total_cost = await db_session.scalar(select(func.sum(LLMCall.cost_estimate)))
    assert total_tokens and total_tokens > 0
    assert total_cost is not None and total_cost >= 0.0


async def test_budget_counts_resume_parsing(auth_client: AsyncClient, db_session) -> None:
    import uuid

    await auth_client.post(f"{API}/resumes", json={"text": RESUME_TEXT})
    user_id = uuid.UUID(await _me(auth_client))

    (parse_row,) = list(await db_session.scalars(select(LLMCall)))
    assert parse_row.session_id is None  # résumé parsing has no session...
    assert parse_row.user_id == user_id  # ...but it is still this user's spend
    assert await tokens_used_today(db_session, user_id) > 0


async def test_budget_equals_the_users_ledger(auth_client: AsyncClient, db_session) -> None:
    """The cost test: what the budget counts is exactly the ledger's sum for
    the user — nothing spent is missing, nothing is counted twice."""
    import uuid

    await _spend_some(auth_client)
    user_id = uuid.UUID(await _me(auth_client))
    ledger_sum = await db_session.scalar(
        select(func.sum(LLMCall.prompt_tokens + LLMCall.completion_tokens)).where(
            LLMCall.user_id == user_id
        )
    )
    unattributed = await db_session.scalar(
        select(func.count(LLMCall.id)).where(LLMCall.user_id.is_(None))
    )
    assert unattributed == 0
    assert await tokens_used_today(db_session, user_id) == ledger_sum > 0


# --- metering what actually happened ---


async def test_cache_hit_is_metered_as_free(db_session, provider) -> None:
    from app.services.pipeline import _complete_metered

    cached = CachingProvider(provider, cache=InMemoryCache(), ttl=60, prompt_version="t")
    for _ in range(2):
        await _complete_metered(
            db_session, cached, "skills: python", SkillExtractionResult,
            session_id=None, user_id=None,
        )
    await db_session.flush()

    rows = list(await db_session.scalars(select(LLMCall).order_by(LLMCall.created_at)))
    assert [r.status for r in rows] == ["ok", "cached"]
    assert rows[0].prompt_tokens > 0
    assert (rows[1].prompt_tokens, rows[1].completion_tokens, rows[1].cost_estimate) == (
        0, 0, 0.0,
    )


async def test_reruns_bypass_the_cache(provider) -> None:
    cached = CachingProvider(provider, cache=InMemoryCache(), ttl=60, prompt_version="t")
    for temperature in (0.0, 0.0, 0.4, 0.4):
        await cached.complete("skills: python", SkillExtractionResult, temperature=temperature)
    # The second temperature-0 call is a hit; both re-runs reach the provider.
    assert len(provider.completions) == 3


async def test_circuit_open_is_metered_as_free(db_session, provider) -> None:
    import pytest

    from app.services.pipeline import _complete_metered

    provider.register(SkillExtractionResult, LLMCircuitOpen("open"))
    with pytest.raises(LLMCircuitOpen):
        await _complete_metered(
            db_session, provider, "skills", SkillExtractionResult,
            session_id=None, user_id=None,
        )
    await db_session.flush()
    (row,) = list(await db_session.scalars(select(LLMCall)))
    assert (row.status, row.prompt_tokens) == ("circuit_open", 0)
