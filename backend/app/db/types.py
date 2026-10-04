"""Column types that have to behave differently per dialect.

The test suite runs on in-memory SQLite, which has no pgvector. Rather than
split the models in two or move the knowledge base behind a Postgres-only test
job, the vector column degrades to JSON off Postgres: storage and round-trip
work everywhere, and only the index-backed nearest-neighbour search (Phase 3)
is Postgres-only — which is correct, because that is a Postgres feature.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator


class Vector(TypeDecorator):
    """A fixed-width embedding: `vector(n)` on Postgres, a JSON array elsewhere.

    The width is part of the schema, not a runtime detail — a `vector(384)`
    column cannot hold a 3072-wide Gemini embedding, and an index built at one
    width is meaningless at another. Changing `EMBEDDING_DIM` therefore needs a
    migration, not just an env var, which is why this takes the dimension
    explicitly instead of reading settings.
    """

    impl = JSON
    cache_ok = True

    def __init__(self, dim: int, **kwargs: Any) -> None:
        self.dim = dim
        super().__init__(**kwargs)

    def load_dialect_impl(self, dialect: Dialect):
        if dialect.name == "postgresql":
            from pgvector.sqlalchemy import Vector as PGVector

            return dialect.type_descriptor(PGVector(self.dim))
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value: list[float] | None, dialect: Dialect):
        if value is None:
            return None
        if len(value) != self.dim:
            # Catch a mismatched embedder at the write, not at query time after
            # an ingest run has already written thousands of rows.
            raise ValueError(
                f"expected a {self.dim}-dimension vector, got {len(value)}. "
                f"The embedder and the column disagree — check EMBEDDING_MODEL "
                f"and EMBEDDING_DIM against the migration that created this table."
            )
        # pgvector accepts a plain list; JSON stores one natively.
        return list(value)

    def process_result_value(self, value: Any, dialect: Dialect) -> list[float] | None:
        if value is None:
            return None
        return [float(v) for v in value]
