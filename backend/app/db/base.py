"""Declarative base and shared column mixins.

Every model inherits from `Base`. Import all models into `app.models`
(its `__init__`) so that `Base.metadata` is fully populated before
Alembic autogenerate or `create_all` runs.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


class UUIDPrimaryKeyMixin:
    """A UUID primary key generated application-side.

    Portable across Postgres (native `uuid`) and SQLite (used in tests),
    and avoids a round-trip to read a server-generated id.
    """

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    """`created_at` / `updated_at`, timezone-aware, DB-defaulted."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        server_default=func.now(),
    )
