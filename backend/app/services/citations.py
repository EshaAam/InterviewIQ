"""Resolve the citations stored on questions into readable sources.

A grounded question carries two things: `source_chunk_ids`, and
`source_snapshots`, a copy of each cited passage taken when the question was
generated. The copy is what gets read. A citation records what the model was
shown, and that has to stay true after the knowledge base changes: re-ingesting
an edited document deletes its chunks and mints new ids, so a citation that was
only an id would resolve to nothing and the review screen would silently lose
the evidence a score was based on.

Questions written before snapshots existed fall back to looking the ids up in
the live knowledge base, once per request for every such question at a time. A
chunk that no longer exists is omitted there, because for those rows there is
nothing else left to show.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import KBChunk, KBDocument
from app.services.retrieval import RetrievedChunk


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


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def snapshot_chunks(
    db: AsyncSession, chunks: list[RetrievedChunk]
) -> dict[str, dict[str, Any]]:
    """chunk id -> a self-contained copy of the passage and its attribution.

    Taken from the retrieved passages themselves, so the stored text is exactly
    what went into the prompt rather than whatever the row says later.
    """
    if not chunks:
        return {}
    documents = await db.scalars(
        select(KBDocument).where(KBDocument.id.in_({c.document_id for c in chunks}))
    )
    by_document = {document.id: document for document in documents}

    snapshots: dict[str, dict[str, Any]] = {}
    for chunk in chunks:
        document = by_document.get(chunk.document_id)
        snapshots[str(chunk.chunk_id)] = {
            "chunk_id": str(chunk.chunk_id),
            "topic": chunk.topic,
            "heading_path": chunk.heading_path,
            "text": chunk.text,
            "text_hash": text_hash(chunk.text),
            "source": document.source if document else "",
            "document_title": document.title if document else "",
            "document_hash": document.content_hash if document else "",
            "url": document.url if document else "",
            "license": document.license if document else "",
        }
    return snapshots


def _from_snapshot(snapshot: dict[str, Any]) -> CitedSource | None:
    try:
        return CitedSource(
            chunk_id=uuid.UUID(str(snapshot["chunk_id"])),
            topic=snapshot.get("topic", ""),
            heading_path=snapshot.get("heading_path", ""),
            text=snapshot["text"],
            document_title=snapshot.get("document_title", ""),
            url=snapshot.get("url", ""),
            license=snapshot.get("license", ""),
        )
    except (KeyError, ValueError):  # pragma: no cover - written by snapshot_chunks
        return None


async def load_citations(
    db: AsyncSession, questions: list
) -> dict[uuid.UUID, list[CitedSource]]:
    """question id -> its cited passages, in the order the question stored them."""
    resolved: dict[uuid.UUID, list[CitedSource]] = {}
    legacy = []
    for question in questions:
        snapshots = question.source_snapshots or []
        if snapshots:
            resolved[question.id] = [
                source for s in snapshots if (source := _from_snapshot(s)) is not None
            ]
        elif question.source_chunk_ids:
            legacy.append(question)
    if not legacy:
        return resolved

    wanted: set[str] = set()
    for question in legacy:
        wanted.update(question.source_chunk_ids or [])

    ids: list[uuid.UUID] = []
    for raw in wanted:
        try:
            ids.append(uuid.UUID(raw))
        except ValueError:  # pragma: no cover - guarded at write time
            continue
    if not ids:
        return resolved

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

    for question in legacy:
        resolved[question.id] = [
            by_id[c] for c in (question.source_chunk_ids or []) if c in by_id
        ]
    return resolved
