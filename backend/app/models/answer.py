"""Answer — a candidate's response, plus the integrity signals collected client-side.

`idempotency_key` (from the required `Idempotency-Key` header) is unique per
question, so submitting the same answer twice creates exactly one row.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, _utcnow


class Answer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "answers"
    __table_args__ = (
        UniqueConstraint(
            "question_id", "idempotency_key", name="uq_answer_question_idem"
        ),
    )

    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(Text)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    idempotency_key: Mapped[str] = mapped_column(String(255))

    # Integrity signals (design doc §6) — advisory, never auto-rejecting.
    time_taken_ms: Mapped[int | None] = mapped_column(Integer, default=None)
    paste_events: Mapped[int] = mapped_column(Integer, default=0)
    keystroke_count: Mapped[int | None] = mapped_column(Integer, default=None)
