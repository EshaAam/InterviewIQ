"""RAG phase 7: job-description matching and knowledge-base coverage gaps

`jd_gaps` is JSON with a server default of '[]' so existing sessions backfill
to the truth — they were generated without a job description, so they targeted
no gaps.

`kb_coverage_misses.session_id` is nullable with SET NULL for the same reason
the LLM call ledger is: deleting an interview must not erase the record that
the corpus had a gap.

Revision ID: f71c6a93d2e8
Revises: e58b3c74d916
Create Date: 2026-10-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f71c6a93d2e8"
down_revision: str | None = "e58b3c74d916"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "interview_sessions", sa.Column("job_description", sa.Text(), nullable=True)
    )
    op.add_column(
        "interview_sessions",
        sa.Column("jd_gaps", sa.JSON(), nullable=False, server_default="[]"),
    )

    op.create_table(
        "kb_coverage_misses",
        sa.Column("skill", sa.String(length=120), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["session_id"], ["interview_sessions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_kb_coverage_misses_skill"), "kb_coverage_misses", ["skill"], unique=False
    )
    op.create_index(
        op.f("ix_kb_coverage_misses_session_id"),
        "kb_coverage_misses",
        ["session_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_kb_coverage_misses_session_id"), table_name="kb_coverage_misses")
    op.drop_index(op.f("ix_kb_coverage_misses_skill"), table_name="kb_coverage_misses")
    op.drop_table("kb_coverage_misses")
    op.drop_column("interview_sessions", "jd_gaps")
    op.drop_column("interview_sessions", "job_description")
