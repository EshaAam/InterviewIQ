"""The knowledge base: source documents and the passages retrieved from them.

Today a question's expected concepts and reference answer come out of the
model's memory, so a wrong answer key is both undetectable and unfixable. These
two tables are what a grounded question will cite instead — and because they
live in the same Postgres as everything else, a question can join to the exact
passages it was built from.

Split in two because the unit of *provenance* (a document, with a licence and a
URL) is not the unit of *retrieval* (a passage small enough to put in a prompt).
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import Vector

#: Width of the `kb_chunks.embedding` column. This is **schema**, not config:
#: it must match the literal in migration c92d4b17e0a3, and changing it needs a
#: migration plus a full re-embed. `EMBEDDING_DIM` asserts what the *model*
#: emits; the two disagreeing is caught at write time by `Vector`, not here.
KB_EMBEDDING_DIM = 384


class KBDocument(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One source file. Carries everything needed to attribute a citation."""

    __tablename__ = "kb_documents"

    #: Path relative to the KB root, e.g. "python.md". The natural key.
    source: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    topic: Mapped[str] = mapped_column(String(80), index=True)
    #: Where it came from. Empty for hand-written content.
    url: Mapped[str] = mapped_column(String(500), default="")
    #: Stored per document because attribution requirements differ per source:
    #: CC-BY-SA has to be shown in the UI, hand-written content does not.
    license: Mapped[str] = mapped_column(String(120), default="")
    #: sha256 of the file. Re-ingesting unchanged content is a no-op because of
    #: this, which is what makes `ingest-kb` safe to run on every deploy.
    content_hash: Mapped[str] = mapped_column(String(64), index=True)


class KBChunk(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One retrievable passage."""

    __tablename__ = "kb_chunks"

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("kb_documents.id", ondelete="CASCADE"), index=True
    )
    #: Position within the document. Stable, so citations read in source order.
    ordinal: Mapped[int] = mapped_column(Integer)
    #: e.g. "FastAPI > Dependencies > Yield". Improves retrieval (the headings
    #: carry terms the body often omits) and makes a citation readable without
    #: fetching the document.
    heading_path: Mapped[str] = mapped_column(String(500), default="")
    text: Mapped[str] = mapped_column(Text)
    #: Denormalised from the document so retrieval can filter by topic without
    #: a join on the hot path.
    topic: Mapped[str] = mapped_column(String(80), index=True)
    token_estimate: Mapped[int] = mapped_column(Integer, default=0)

    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(KB_EMBEDDING_DIM), nullable=True
    )
    #: Which model produced `embedding`. Vectors from two different models are
    #: not comparable, so a mixed index silently returns nonsense; ingestion
    #: refuses to mix, and this column is how it can tell.
    embedding_model: Mapped[str] = mapped_column(String(120), index=True, default="")

    __table_args__ = (
        UniqueConstraint("document_id", "ordinal", name="uq_kb_chunk_document_ordinal"),
    )
