"""Record why a resume parse failed

Nullable, so existing rows are untouched: a resume parsed before this migration
has no recorded reason and does not need one.

Revision ID: a93f52c0b7d4
Revises: f71c6a93d2e8
Create Date: 2026-10-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a93f52c0b7d4"
down_revision: str | None = "f71c6a93d2e8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("resumes", sa.Column("failure_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("resumes", "failure_reason")
