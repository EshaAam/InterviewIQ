"""Read-only deployment check for the configured knowledge base and retriever."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.embedders import Embedder
from app.models import KB_EMBEDDING_DIM, KBChunk, KBDocument
from app.services.retrieval import RetrievedChunk, search

DEFAULT_QUERY = "What is the difference between a Docker image and a container?"


class RAGNotReady(Exception):
    """RAG would be disabled, incompatible, or unable to retrieve context."""


@dataclass(frozen=True)
class RAGCheck:
    documents: int
    chunks: int
    hits: list[RetrievedChunk]


async def check_rag(
    db: AsyncSession, embedder: Embedder, *, query: str = DEFAULT_QUERY
) -> RAGCheck:
    """Exercise hybrid retrieval without changing data or calling a generation model."""
    if not settings.RAG_ENABLED:
        raise RAGNotReady("RAG_ENABLED is false; enable it in the API and worker environment.")
    if embedder.dim != KB_EMBEDDING_DIM:
        raise RAGNotReady(
            f"embedder width {embedder.dim} does not match the KB schema "
            f"({KB_EMBEDDING_DIM}); keep the ingestion and runtime models compatible."
        )

    documents = await db.scalar(select(func.count()).select_from(KBDocument)) or 0
    chunks = await db.scalar(select(func.count()).select_from(KBChunk)) or 0
    if not documents or not chunks:
        raise RAGNotReady("knowledge base is empty; run python -m app.cli ingest-kb first.")
    embedded = await db.scalar(
        select(func.count()).select_from(KBChunk).where(KBChunk.embedding.is_not(None))
    )
    if embedded != chunks:
        raise RAGNotReady(f"only {embedded}/{chunks} KB chunks have embeddings.")
    models = set(await db.scalars(select(KBChunk.embedding_model).distinct()))
    if models != {embedder.name}:
        raise RAGNotReady(
            f"KB models {sorted(models)} do not match runtime embedder {embedder.name}; "
            "use the original model or plan a compatible re-ingestion."
        )

    hits = await search(db, embedder, query)
    if not hits:
        raise RAGNotReady(
            "hybrid retrieval returned no context at the configured similarity floor; "
            "check the corpus, embedding model, and probe query."
        )
    return RAGCheck(documents=documents, chunks=chunks, hits=hits)
