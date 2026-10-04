"""Build the knowledge base from source files.

Run from the CLI, never over HTTP: there is no user-facing upload into the KB,
so the only way content gets in is someone with shell access running
`python -m app.cli ingest-kb`. That is the whole access-control story for the
corpus a grounded answer key will be built from.

Two properties the plan calls for, and why each one matters:

**Idempotent by content hash.** Re-running on unchanged files writes nothing.
That is what makes it safe to run on every deploy rather than something a human
has to remember — and embedding is the expensive step, so skipping it is also
the difference between seconds and minutes.

**Refuses to mix embedding models.** Vectors from two models are not comparable;
a cosine between a bge-small vector and a Gemini one is a meaningless number
that still sorts. An index half-written by each silently returns nonsense
rather than failing, so ingestion refuses up front and makes you ask for the
re-embed explicitly.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.embedders import Embedder
from app.models import KBChunk, KBDocument
from app.services.chunking import chunk_markdown, parse_front_matter

#: Repo-relative default, resolved from this file so it works from any cwd.
DEFAULT_KB_DIR = Path(__file__).resolve().parents[2] / "kb"


class MixedEmbeddingModels(Exception):
    """The index already holds vectors from a different model."""


@dataclass
class IngestReport:
    embedding_model: str
    ingested: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    chunks_written: int = 0
    chunks_per_topic: dict[str, int] = field(default_factory=dict)
    #: In the database but no longer on disk. Reported, never deleted — Phase 4
    #: questions will cite chunks, and a citation must not rot because someone
    #: renamed a file.
    orphaned: list[str] = field(default_factory=list)

    def table(self) -> str:
        lines = [
            f"  embedding model      {self.embedding_model}",
            f"  documents ingested   {len(self.ingested)}",
            f"  documents unchanged  {len(self.skipped)}",
            f"  chunks written       {self.chunks_written}",
        ]
        if self.chunks_per_topic:
            lines.append("")
            lines.append("  chunks per topic:")
            width = max(len(t) for t in self.chunks_per_topic)
            for topic, count in sorted(self.chunks_per_topic.items()):
                lines.append(f"    {topic:<{width}}  {count:>4}")
        if self.orphaned:
            lines.append("")
            lines.append(
                "  in the database but not on disk (left in place, see Phase 4):"
            )
            lines.extend(f"    {source}" for source in self.orphaned)
        return "\n".join(lines)


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def _guard_against_mixed_models(db: AsyncSession, embedder: Embedder) -> None:
    rows = await db.scalars(
        select(KBChunk.embedding_model).distinct().where(KBChunk.embedding_model != "")
    )
    foreign = {model for model in rows if model != embedder.name}
    if foreign:
        raise MixedEmbeddingModels(
            f"the knowledge base was built with {', '.join(sorted(foreign))} but the "
            f"configured embedder is {embedder.name}. Cosine similarity between "
            f"vectors from different models is meaningless, so this would corrupt "
            f"retrieval silently. Re-embed everything with --force, or set "
            f"EMBEDDING_MODEL back."
        )


async def ingest_kb(
    db: AsyncSession,
    embedder: Embedder,
    *,
    kb_dir: Path | None = None,
    force: bool = False,
    max_tokens: int = 400,
    overlap_tokens: int = 50,
) -> IngestReport:
    """Chunk, embed and store every markdown file under `kb_dir`."""
    root = kb_dir or DEFAULT_KB_DIR
    if not root.is_dir():
        raise FileNotFoundError(f"no knowledge base directory at {root}")

    if not force:
        await _guard_against_mixed_models(db, embedder)

    report = IngestReport(embedding_model=embedder.name)
    seen: set[str] = set()

    for path in sorted(root.rglob("*.md")):
        source = path.relative_to(root).as_posix()
        seen.add(source)
        raw = path.read_text(encoding="utf-8")
        content_hash = _hash(raw)

        document = await db.scalar(select(KBDocument).where(KBDocument.source == source))
        if document is not None and document.content_hash == content_hash and not force:
            report.skipped.append(source)
            continue

        meta, body = parse_front_matter(raw)
        chunks = chunk_markdown(
            body,
            root_title=meta.title,
            max_tokens=max_tokens,
            overlap_tokens=overlap_tokens,
        )
        if not chunks:
            raise ValueError(f"{source} produced no chunks — is the body empty?")

        # One call for the whole document: embedders batch far better than they
        # loop, and this is the expensive step.
        vectors = await embedder.embed([c.text for c in chunks])

        if document is None:
            document = KBDocument(source=source)
            db.add(document)
        document.title = meta.title
        document.topic = meta.topic
        document.url = meta.url
        document.license = meta.license
        document.content_hash = content_hash
        await db.flush()  # assigns document.id for the chunk rows below

        # Replace rather than merge: chunk boundaries move when the source
        # changes, so matching old chunks to new ones is guesswork.
        await db.execute(delete(KBChunk).where(KBChunk.document_id == document.id))
        for chunk, vector in zip(chunks, vectors, strict=True):
            db.add(
                KBChunk(
                    document_id=document.id,
                    ordinal=chunk.ordinal,
                    heading_path=chunk.heading_path,
                    text=chunk.text,
                    topic=meta.topic,
                    token_estimate=chunk.token_estimate,
                    embedding=vector,
                    embedding_model=embedder.name,
                )
            )
        await db.flush()
        report.ingested.append(source)
        report.chunks_written += len(chunks)

    stored = await db.execute(
        select(KBChunk.topic, func.count(KBChunk.id)).group_by(KBChunk.topic)
    )
    report.chunks_per_topic = dict(stored.all())

    known = await db.scalars(select(KBDocument.source))
    report.orphaned = sorted(set(known) - seen)

    if not report.chunks_per_topic:
        report.chunks_per_topic = dict(Counter())
    return report
