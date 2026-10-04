"""RAG phase 2: knowledge base documents and chunks

The `embedding` column is `vector(384)` on Postgres and JSON elsewhere (see
`app.db.types.Vector`), so the unit suite keeps running on SQLite while the
real index lives in Postgres. **The width is schema, not config:** changing
`EMBEDDING_DIM` needs a migration, because a vector column cannot hold a vector
of another size and an index built at one width is meaningless at another.

No ANN index here. An IVFFlat/HNSW index wants to be built against a populated
table — building it on an empty one produces a useless plan — and nothing
queries these vectors until Phase 3. The index lands with the retrieval
service that needs it, alongside the full-text column for hybrid search.

Revision ID: c92d4b17e0a3
Revises: a7f3c01d58be
Create Date: 2026-10-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.db.types import Vector

revision: str = "c92d4b17e0a3"
down_revision: str | None = "a7f3c01d58be"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "kb_documents",
        sa.Column("source", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("topic", sa.String(length=80), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("license", sa.String(length=120), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_kb_documents_source"), "kb_documents", ["source"], unique=True
    )
    op.create_index(op.f("ix_kb_documents_topic"), "kb_documents", ["topic"], unique=False)
    op.create_index(
        op.f("ix_kb_documents_content_hash"), "kb_documents", ["content_hash"], unique=False
    )

    op.create_table(
        "kb_chunks",
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("heading_path", sa.String(length=500), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("topic", sa.String(length=80), nullable=False),
        sa.Column("token_estimate", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(384), nullable=True),
        sa.Column("embedding_model", sa.String(length=120), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["document_id"], ["kb_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "ordinal", name="uq_kb_chunk_document_ordinal"),
    )
    op.create_index(
        op.f("ix_kb_chunks_document_id"), "kb_chunks", ["document_id"], unique=False
    )
    op.create_index(op.f("ix_kb_chunks_topic"), "kb_chunks", ["topic"], unique=False)
    op.create_index(
        op.f("ix_kb_chunks_embedding_model"), "kb_chunks", ["embedding_model"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_kb_chunks_embedding_model"), table_name="kb_chunks")
    op.drop_index(op.f("ix_kb_chunks_topic"), table_name="kb_chunks")
    op.drop_index(op.f("ix_kb_chunks_document_id"), table_name="kb_chunks")
    op.drop_table("kb_chunks")
    op.drop_index(op.f("ix_kb_documents_content_hash"), table_name="kb_documents")
    op.drop_index(op.f("ix_kb_documents_topic"), table_name="kb_documents")
    op.drop_index(op.f("ix_kb_documents_source"), table_name="kb_documents")
    op.drop_table("kb_documents")
