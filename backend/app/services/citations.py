"""Resolve the citations stored on questions into readable sources.

`questions.source_chunk_ids` holds chunk ids as JSON rather than foreign keys,
deliberately — a citation records what the model was shown and must survive a
re-ingest or a withdrawn document. The cost of that choice is that it cannot be
joined, so resolving citations is an explicit lookup. This is that lookup, done
once per request for every question at a time rather than per question, because
a review screen shows a whole interview.

A chunk that no longer exists is simply omitted. The alternative — failing the
request, or showing a dangling id — would make a withdrawn document break a
review screen, which is worse than showing one fewer source.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import KBChunk, KBDocument


@dataclass(frozen=True)
class CitedSource:
    """One passage a question was built from, with its attribution."""

    chunk_id: uuid.UUID
    topic: str
    heading_path: str
    text: str
    document_title: str
    url: str
    #: Shown in the UI where the licence requires attribution. Empty for
    #: hand-written content, which needs none.
    license: str


async def load_citations(
    db: AsyncSession, questions: list
) -> dict[uuid.UUID, list[CitedSource]]:
    """question id -> its cited passages, in the order the question stored them."""
    wanted: set[str] = set()
    for question in questions:
        wanted.update(question.source_chunk_ids or [])
    if not wanted:
        return {}

    ids: list[uuid.UUID] = []
    for raw in wanted:
        try:
            ids.append(uuid.UUID(raw))
        except ValueError:  # pragma: no cover - guarded at write time
            continue
    if not ids:
        return {}

    rows = await db.execute(
        select(KBChunk, KBDocument)
        .join(KBDocument, KBChunk.document_id == KBDocument.id)
        .where(KBChunk.id.in_(ids))
    )
    by_id = {
        str(chunk.id): CitedSource(
            chunk_id=chunk.id,
            topic=chunk.topic,
            heading_path=chunk.heading_path,
            text=chunk.text,
            document_title=document.title,
            url=document.url,
            license=document.license,
        )
        for chunk, document in rows.all()
    }

    return {
        question.id: [
            by_id[c] for c in (question.source_chunk_ids or []) if c in by_id
        ]
        for question in questions
    }
