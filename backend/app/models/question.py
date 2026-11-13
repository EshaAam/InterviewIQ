"""Question — generated *with* its expected concepts, before any answer exists.

`expected_concepts` is the pivot that makes grading reproducible: evaluation
asks "which of these appeared?" instead of an unstable 0-100 (design doc §3).
"""

from __future__ import annotations

import uuid
from enum import StrEnum

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class GroundingStatus(StrEnum):
    """Why a question does or does not have cited evidence behind it.

    "Not grounded" covers several different facts, and a reviewer reads them
    differently: a question the model wrote while ignoring the sources it was
    given is a model failure, one written with retrieval switched off is a
    configuration choice, and one about a skill the corpus does not cover is a
    gap to fill. A single boolean cannot tell them apart.
    """

    #: The answer key cites passages, saved in `source_snapshots`.
    GROUNDED = "grounded"
    #: Passages were offered to the model, but this question cited none.
    UNCITED = "uncited"
    #: Retrieval ran and nothing in the knowledge base was relevant enough.
    NOT_COVERED = "not_covered"
    #: Retrieval was on but there was nothing to look up (no extracted skills).
    NO_SKILLS = "no_skills"
    #: `RAG_ENABLED` was false when the question was generated.
    RAG_DISABLED = "rag_disabled"
    #: Ungrounded, generated before the reason was recorded.
    UNKNOWN = "unknown"


def _default_status(context) -> str:  # noqa: ANN001 - SQLAlchemy execution context
    """Keep the status consistent with `grounded` when only the flag was set."""
    grounded = context.get_current_parameters().get("grounded")
    return GroundingStatus.GROUNDED if grounded else GroundingStatus.UNKNOWN


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
    #: The reason behind `grounded`, one of `GroundingStatus`. The boolean stays
    #: because it is indexed and already part of the API.
    grounding_status: Mapped[str] = mapped_column(String(32), default=_default_status)
    #: A copy of each cited passage as the model saw it: text, heading, document
    #: attribution and hashes, in citation order.
    #:
    #: `source_chunk_ids` alone is not enough. Re-ingesting an edited document
    #: deletes its chunks and mints new ids, so an id-only citation points at
    #: nothing afterwards and a finished interview can no longer show, or be
    #: re-graded against, the evidence its answer key was built from. The copy
    #: makes the citation self-contained. Empty for ungrounded questions, and
    #: for grounded ones written before this column whose chunks were already
    #: gone when it was backfilled.
    source_snapshots: Mapped[list[dict]] = mapped_column(JSON, default=list)
