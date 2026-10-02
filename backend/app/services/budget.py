"""Per-user daily token budget, enforced against the `LLMCall` ledger.

The budget is checked when a user *starts* work — a résumé or a new session —
so an over-budget user is rejected with 429 before the system spends tokens on
their behalf (the API dependency `require_budget`). It is deliberately not
checked on answers or on finishing: an interview already under way may always
complete, so the most a user can overshoot by is one interview's grading.
Usage is summed from the same ledger that records cost: one source of truth.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import LLMCall


def utc_day_start() -> datetime:
    """The window every daily number in the app is measured against."""
    now = datetime.now(UTC)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


async def tokens_used_today(db: AsyncSession, user_id: uuid.UUID) -> int:
    """Total prompt+completion tokens spent for the user since UTC midnight.

    Summed on `LLMCall.user_id`, not through the session: résumé parsing has
    no session, and spend must not vanish when a session row does.
    """
    total = await db.scalar(
        select(
            func.coalesce(
                func.sum(LLMCall.prompt_tokens + LLMCall.completion_tokens), 0
            )
        ).where(
            LLMCall.user_id == user_id,
            LLMCall.created_at >= utc_day_start(),
        )
    )
    return int(total or 0)
