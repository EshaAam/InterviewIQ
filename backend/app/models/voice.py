"""Every transcript the server produced for a question.

Kept so that "how much of this answer was spoken?" is answered by the server
rather than claimed by the browser. When the answer is submitted it is compared
against these, and the overlap becomes `answers.dictated_chars` — which the
typing-based integrity signals then discount, because a spoken answer has no
keystrokes and is "typed" faster than any person can.

The audio itself is never stored: it is decoded in memory and dropped.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class VoiceTranscription(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "voice_transcriptions"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("interview_sessions.id", ondelete="CASCADE"), index=True
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(Text, default="")
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    model: Mapped[str] = mapped_column(String(120), default="")
