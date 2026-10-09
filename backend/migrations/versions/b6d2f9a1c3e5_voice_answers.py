"""Voice answers: server-side transcripts and dictated characters

`answers.dictated_chars` defaults to 0, so every existing answer reads as fully
typed — which it was. `voice_transcriptions` is new and empty.

Revision ID: b6d2f9a1c3e5
Revises: a93f52c0b7d4
Create Date: 2026-10-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b6d2f9a1c3e5"
down_revision: str | None = "a93f52c0b7d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "answers",
        sa.Column("dictated_chars", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "voice_transcriptions",
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
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
            ["session_id"], ["interview_sessions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_voice_transcriptions_session_id"),
        "voice_transcriptions",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_voice_transcriptions_question_id"),
        "voice_transcriptions",
        ["question_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_voice_transcriptions_question_id"), table_name="voice_transcriptions"
    )
    op.drop_index(
        op.f("ix_voice_transcriptions_session_id"), table_name="voice_transcriptions"
    )
    op.drop_table("voice_transcriptions")
    op.drop_column("answers", "dictated_chars")
