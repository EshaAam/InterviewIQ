"""InterviewSession — the domain spine.

The `state` column is driven exclusively through `SessionService.transition`
(see app/services/session_service.py). Nothing else should write to it.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SessionState(enum.StrEnum):
    CREATED = "CREATED"
    PARSING = "PARSING"
    GENERATING_QS = "GENERATING_QS"
    READY = "READY"
    IN_PROGRESS = "IN_PROGRESS"
    EVALUATING = "EVALUATING"
    COMPLETED = "COMPLETED"
    NEEDS_HUMAN_REVIEW = "NEEDS_HUMAN_REVIEW"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"


class InterviewSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "interview_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    resume_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("resumes.id", ondelete="SET NULL"), default=None
    )
    state: Mapped[SessionState] = mapped_column(
        SAEnum(SessionState, name="session_state"),
        default=SessionState.CREATED,
        index=True,
    )
    # Set when a terminal-failure state is entered; nulled on recovery.
    failure_reason: Mapped[str | None] = mapped_column(String(500), default=None)
    # Server-authoritative deadline. The client is never trusted with time.
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    # Reproducibility metadata (populated in later phases).
    prompt_version: Mapped[str | None] = mapped_column(String(64), default=None)
    model_name: Mapped[str | None] = mapped_column(String(128), default=None)
