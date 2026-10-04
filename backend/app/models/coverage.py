"""Skills the knowledge base failed to answer for.

R2 scoped the corpus narrowly on purpose — six topics, written by hand — which
means it is incomplete by design and will stay that way unless something says
what to write next. Guessing produces a knowledge base shaped like its author's
assumptions; this records what candidates actually got asked about and the
corpus could not support.

One row per (skill, session) miss rather than a running counter, because
*when* and *for whom* matter: a skill that missed thirty times last month and
not since is already fixed, and a counter cannot tell you that.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class KBCoverageMiss(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "kb_coverage_misses"

    #: The extracted skill name, lowercased by the extractor.
    skill: Mapped[str] = mapped_column(String(120), index=True)
    #: The full retrieval query, so a near-miss can be reproduced. The skill
    #: name alone often is not enough to see why nothing matched.
    query: Mapped[str] = mapped_column(Text, default="")
    #: Nullable with SET NULL: deleting an interview must not erase the record
    #: that the corpus had a gap, the same reasoning as the LLM call ledger.
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("interview_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
