"""RAG phase 3: full-text and vector indexes for hybrid retrieval

Both indexes are Postgres-only and are created with raw SQL rather than through
the model, which is deliberate.

**Full text** is an *expression* index over `to_tsvector('english', text)`
rather than a stored `tsvector` column. A generated column would have to be
declared on the model, and SQLite — which the unit suite runs on — cannot create
one from a Postgres function. An expression index keeps the model dialect-free
and costs nothing at query time, as long as the query repeats the same
expression.

**The vector index** is HNSW with `vector_cosine_ops`, matching the `<=>`
operator the retrieval service uses. An index built for one distance operator
does not serve another: build it for L2 and cosine queries silently fall back to
a sequential scan.

A note on scale: at 59 chunks Postgres will choose a sequential scan over either
index, and correctly — they exist so the query plan does not change shape when
the knowledge base grows. `SET enable_seqscan = off` is how you check the index
is actually usable at this size.

Revision ID: d41a8f6b2c57
Revises: c92d4b17e0a3
Create Date: 2026-10-05
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "d41a8f6b2c57"
down_revision: str | None = "c92d4b17e0a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FTS_INDEX = "ix_kb_chunks_fts"
VECTOR_INDEX = "ix_kb_chunks_embedding_hnsw"


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute(
        f"CREATE INDEX {FTS_INDEX} ON kb_chunks "
        f"USING gin (to_tsvector('english', text))"
    )
    # m/ef_construction are the pgvector defaults, stated explicitly: they are a
    # build-time/recall trade-off worth seeing rather than inheriting.
    op.execute(
        f"CREATE INDEX {VECTOR_INDEX} ON kb_chunks "
        f"USING hnsw (embedding vector_cosine_ops) "
        f"WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(f"DROP INDEX IF EXISTS {VECTOR_INDEX}")
    op.execute(f"DROP INDEX IF EXISTS {FTS_INDEX}")
