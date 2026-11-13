"""An explicit grounding status on questions

`grounding_status` says why a question is or is not grounded. History only
recorded the boolean, so old ungrounded questions become `unknown` rather than
being assigned a reason nobody wrote down.

Revision ID: d4b0f6a28c53
Revises: c3a9e5f17b42
Create Date: 2026-11-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4b0f6a28c53"
down_revision: str | None = "c3a9e5f17b42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "questions",
        sa.Column(
            "grounding_status", sa.String(length=32), nullable=False, server_default="unknown"
        ),
    )
    op.execute("UPDATE questions SET grounding_status = 'grounded' WHERE grounded")


def downgrade() -> None:
    op.drop_column("questions", "grounding_status")
