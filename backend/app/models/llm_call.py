"""LLMCall — the audit and cost ledger.

One row per provider call, written regardless of outcome. Without it you can't
answer "why did this score change?" or "what does one interview cost?"
(design doc §3). The token-budget cap in Phase 3 is enforced against this ledger.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class LLMCall(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "llm_calls"

    session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("interview_sessions.id", ondelete="SET NULL"),
        index=True,
        default=None,
    )
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128))
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_estimate: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="ok")
