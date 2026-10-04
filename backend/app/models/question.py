"""Question — generated *with* its expected concepts, before any answer exists.

`expected_concepts` is the pivot that makes grading reproducible: evaluation
asks "which of these appeared?" instead of an unstable 0-100 (design doc §3).
"""

from __future__ import annotations

import uuid

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Question(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "questions"
    __table_args__ = (
        UniqueConstraint("session_id", "ordinal", name="uq_question_session_ordinal"),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("interview_sessions.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    difficulty: Mapped[str] = mapped_column(String(32), default="medium")
    topic: Mapped[str] = mapped_column(String(120))
    expected_concepts: Mapped[list[str]] = mapped_column(JSON, default=list)
    reference_answer: Mapped[str] = mapped_column(Text, default="")
    prompt_version: Mapped[str | None] = mapped_column(String(64), default=None)

    #: `kb_chunks.id` values this question was built from, as strings.
    #:
    #: Not a foreign key, deliberately. A citation is a record of what the model
    #: was shown at generation time, and it has to stay readable even if the
    #: knowledge base is later re-ingested or a document is withdrawn. A real FK
    #: would either block that or cascade the history away.
    source_chunk_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    #: True when the answer key came from cited passages rather than model
    #: memory. Stored rather than derived from `source_chunk_ids` being
    #: non-empty, because "the KB did not cover this skill" and "RAG was off"
    #: are different facts and a report should be able to tell them apart.
    grounded: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
