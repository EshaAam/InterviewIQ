"""Resume — the uploaded document and its parse lifecycle.

Parsing itself lands in Phase 2; here we model the record and its status
so sessions can reference a resume and the FSM can gate on parse state.
"""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ParseStatus(enum.StrEnum):
    pending = "pending"
    parsing = "parsing"
    parsed = "parsed"
    failed = "failed"


class Resume(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "resumes"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    file_uri: Mapped[str] = mapped_column(String(1024))
    mime: Mapped[str] = mapped_column(String(255))
    text_content: Mapped[str | None] = mapped_column(Text, default=None)
    parse_status: Mapped[ParseStatus] = mapped_column(
        SAEnum(ParseStatus, name="parse_status"), default=ParseStatus.pending
    )
