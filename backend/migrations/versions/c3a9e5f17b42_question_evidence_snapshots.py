"""Question evidence snapshots

`source_snapshots` holds a copy of every cited passage, so a citation survives
a knowledge-base re-ingest. Existing grounded questions are backfilled from the
chunks that are still there; one whose chunks were already replaced keeps an
empty list and falls back to the id lookup, exactly as before.

Revision ID: c3a9e5f17b42
Revises: b6d2f9a1c3e5
Create Date: 2026-11-13
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3a9e5f17b42"
down_revision: str | None = "b6d2f9a1c3e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "questions",
        sa.Column("source_snapshots", sa.JSON(), nullable=False, server_default="[]"),
    )

    bind = op.get_bind()
    questions = sa.table(
        "questions",
        sa.column("id", sa.Uuid()),
        sa.column("grounded", sa.Boolean()),
        sa.column("source_chunk_ids", sa.JSON()),
        sa.column("source_snapshots", sa.JSON()),
    )
    grounded = bind.execute(
        sa.select(questions.c.id, questions.c.source_chunk_ids).where(questions.c.grounded)
    ).all()
    if not grounded:
        return

    passages = {
        str(row.id): row
        for row in bind.execute(
            sa.text(
                """
                SELECT c.id, c.topic, c.heading_path, c.text,
                       d.source, d.title, d.content_hash, d.url, d.license
                FROM kb_chunks c JOIN kb_documents d ON d.id = c.document_id
                """
            )
        )
    }
    for question_id, chunk_ids in grounded:
        snapshots = [
            {
                "chunk_id": chunk_id,
                "topic": passage.topic,
                "heading_path": passage.heading_path,
                "text": passage.text,
                "text_hash": hashlib.sha256(passage.text.encode("utf-8")).hexdigest(),
                "source": passage.source,
                "document_title": passage.title,
                "document_hash": passage.content_hash,
                "url": passage.url,
                "license": passage.license,
            }
            for chunk_id in (chunk_ids or [])
            if (passage := passages.get(str(chunk_id))) is not None
        ]
        if snapshots:
            bind.execute(
                questions.update()
                .where(questions.c.id == question_id)
                .values(source_snapshots=snapshots)
            )


def downgrade() -> None:
    op.drop_column("questions", "source_snapshots")
