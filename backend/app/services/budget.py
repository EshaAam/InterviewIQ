"""Per-user daily token budget, enforced against the `LLMCall` ledger.

The budget is checked at request time (before any work is enqueued) so an
over-budget user is rejected with 429 *before* the system spends tokens on
their behalf — see the API dependency `require_budget`. Usage is summed from
the same ledger that records cost, so there is one source of truth.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import InterviewSession, LLMCall


def _utc_day_start() -> datetime:
    now = datetime.now(UTC)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


async def tokens_used_today(db: AsyncSession, user_id: uuid.UUID) -> int:
    """Total prompt+completion tokens the user has spent since UTC midnight."""
    total = await db.scalar(
        select(
            func.coalesce(
                func.sum(LLMCall.prompt_tokens + LLMCall.completion_tokens), 0
            )
        )
        .select_from(LLMCall)
        .join(InterviewSession, LLMCall.session_id == InterviewSession.id)
        .where(
            InterviewSession.user_id == user_id,
            LLMCall.created_at >= _utc_day_start(),
        )
    )
    return int(total or 0)
