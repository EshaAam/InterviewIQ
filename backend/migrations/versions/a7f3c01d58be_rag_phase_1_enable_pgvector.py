"""RAG Phase 1: enable the pgvector extension

No tables yet — `kb_documents` and `kb_chunks` arrive in Phase 2. This migration
exists on its own so the infrastructure change lands (and can be reverted)
independently of any schema that depends on it.

`CREATE EXTENSION` needs privileges an application role often lacks. It works
here because the Compose/CI Postgres runs as the superuser named in
POSTGRES_USER; on managed Postgres (RDS, Cloud SQL, Neon) pgvector is usually
enabled from the provider console instead, and this becomes a no-op thanks to
IF NOT EXISTS.

The image must ship the extension — stock `postgres:16-alpine` does not have
it. Compose, the production compose file and CI all move to
`pgvector/pgvector:pg16`; running this against the stock image fails with
"extension \"vector\" is not available", which is the correct, loud failure.

Revision ID: a7f3c01d58be
Revises: 4c1e7a2b9d10
Create Date: 2026-10-03

"""

from __future__ import annotations

from alembic import op

revision = "a7f3c01d58be"
down_revision = "4c1e7a2b9d10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    # Only safe while nothing uses it. Phase 2 adds `kb_chunks.embedding`, and
    # that migration's own downgrade drops the table first, so by the time this
    # runs there is no dependent object left.
    op.execute("DROP EXTENSION IF EXISTS vector")
