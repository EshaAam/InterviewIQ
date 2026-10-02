"""phase 6: llm_calls.user_id — budget by user, résumé parsing included

Revision ID: 4c1e7a2b9d10
Revises: 909390dbf94c
Create Date: 2026-10-01 12:00:00.000000

Hand-written (no Postgres available to autogenerate against). Adds the column,
backfills it from each call's session, then indexes it for the budget query.
Calls with no session (résumé parsing before this change) can't be attributed
and stay NULL — they were never counted, and still aren't.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '4c1e7a2b9d10'
down_revision: str | None = '909390dbf94c'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('llm_calls', sa.Column('user_id', sa.Uuid(), nullable=True))
    op.create_foreign_key(
        'fk_llm_calls_user_id_users',
        'llm_calls', 'users', ['user_id'], ['id'], ondelete='SET NULL',
    )
    op.execute(
        """
        UPDATE llm_calls
        SET user_id = interview_sessions.user_id
        FROM interview_sessions
        WHERE llm_calls.session_id = interview_sessions.id
          AND llm_calls.user_id IS NULL
        """
    )
    op.create_index(
        'ix_llm_calls_user_created', 'llm_calls', ['user_id', 'created_at'], unique=False
    )


def downgrade() -> None:
    op.drop_index('ix_llm_calls_user_created', table_name='llm_calls')
    op.drop_constraint('fk_llm_calls_user_id_users', 'llm_calls', type_='foreignkey')
    op.drop_column('llm_calls', 'user_id')
