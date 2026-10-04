"""RAG phase 4: question citations and the grounded flag

`grounded` is NOT NULL with a server default so the backfill works on existing
rows: every question generated before this migration came from model memory, so
false is the correct history rather than a convenient placeholder.

`source_chunk_ids` is JSON rather than a foreign key table. A citation records
what the model was shown at generation time; it must survive a knowledge-base
re-ingest or a withdrawn document, and a real FK would either block that or
cascade the evidence away.

Revision ID: e58b3c74d916
Revises: d41a8f6b2c57
Create Date: 2026-10-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e58b3c74d916"
down_revision: str | None = "d41a8f6b2c57"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "questions",
        sa.Column("source_chunk_ids", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "questions",
        sa.Column(
            "grounded", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.create_index(op.f("ix_questions_grounded"), "questions", ["grounded"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_questions_grounded"), table_name="questions")
    op.drop_column("questions", "grounded")
    op.drop_column("questions", "source_chunk_ids")
