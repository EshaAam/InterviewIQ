"""ExtractedSkill — a skill parsed out of a resume, with its evidence."""

from __future__ import annotations

import uuid

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ExtractedSkill(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "extracted_skills"

    resume_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("resumes.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    evidence_span: Mapped[str] = mapped_column(Text, default="")
