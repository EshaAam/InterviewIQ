"""Evaluation — the reconciled score for one answer, with full provenance.

Stores both passes (deterministic + LLM) and the reproducibility metadata
(model, temperature, prompt_version, run_count) so a score can always be
explained and re-derived. Phase 2 writes a single pass; Phase 4 fills in the
divergence/reconcile logic.
"""

from __future__ import annotations

import uuid

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Evaluation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "evaluations"

    answer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("answers.id", ondelete="CASCADE"), unique=True, index=True
    )
    concept_coverage: Mapped[dict] = mapped_column(JSON, default=dict)
    llm_scores: Mapped[dict] = mapped_column(JSON, default=dict)
    deterministic_score: Mapped[float] = mapped_column(Float, default=0.0)
    final_score: Mapped[float] = mapped_column(Float, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    # Set when the LLM and deterministic passes diverge past threshold — the
    # answer is queued for a recruiter rather than auto-scored with confidence.
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    model_name: Mapped[str | None] = mapped_column(String(128), default=None)
    temperature: Mapped[float] = mapped_column(Float, default=0.0)
    prompt_version: Mapped[str | None] = mapped_column(String(64), default=None)
    run_count: Mapped[int] = mapped_column(Integer, default=1)

    # Human-review audit: who overrode the score, and their note.
    overridden_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )
    override_note: Mapped[str | None] = mapped_column(Text, default=None)
