"""Per-user token budget — rejected with 429 before spending, via the ledger."""

from __future__ import annotations

from httpx import AsyncClient

from app.core.config import settings

API = settings.API_V1_PREFIX
RESUME_TEXT = "python fastapi postgresql redis docker celery engineer"


async def _spend_some(client: AsyncClient) -> None:
    resume_id = (
        await client.post(f"{API}/resumes", json={"text": RESUME_TEXT})
    ).json()["id"]
    # Creating a session runs generate_questions inline, writing LLMCall rows.
    await client.post(f"{API}/sessions", json={"resume_id": resume_id})


async def test_over_budget_returns_429(
    auth_client: AsyncClient, monkeypatch
) -> None:
    await _spend_some(auth_client)  # some tokens now on the ledger
    monkeypatch.setattr(settings, "USER_DAILY_TOKEN_BUDGET", 1)

    resume_id = (
        await auth_client.post(f"{API}/resumes", json={"text": RESUME_TEXT})
    ).json()["id"]
    resp = await auth_client.post(f"{API}/sessions", json={"resume_id": resume_id})
    assert resp.status_code == 429


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
    from sqlalchemy import func, select

    from app.models import LLMCall

    await _spend_some(auth_client)
    total_tokens = await db_session.scalar(
        select(func.sum(LLMCall.prompt_tokens + LLMCall.completion_tokens))
    )
    total_cost = await db_session.scalar(select(func.sum(LLMCall.cost_estimate)))
    assert total_tokens and total_tokens > 0
    assert total_cost is not None and total_cost >= 0.0
