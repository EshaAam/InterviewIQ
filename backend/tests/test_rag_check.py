"""A deployment probe must reject silent fallbacks and incompatible KB vectors."""

import pytest
from sqlalchemy import null, update

from app.core.config import settings
from app.embedders import HashEmbedder
from app.models import KB_EMBEDDING_DIM, KBChunk
from app.services.kb_ingest import ingest_kb
from app.services.rag_check import DEFAULT_QUERY, RAGNotReady, check_rag


@pytest.fixture
def probe_embedder(monkeypatch):
    monkeypatch.setattr(settings, "RAG_ENABLED", True)
    monkeypatch.setattr(settings, "RAG_MIN_SIMILARITY", 0.05)
    return HashEmbedder(dim=KB_EMBEDDING_DIM)


async def test_disabled_flag_rejected(db_session, probe_embedder, monkeypatch):
    monkeypatch.setattr(settings, "RAG_ENABLED", False)
    with pytest.raises(RAGNotReady, match="RAG_ENABLED is false"):
        await check_rag(db_session, probe_embedder)


async def test_wrong_vector_width_rejected(db_session, probe_embedder):
    with pytest.raises(RAGNotReady, match="does not match the KB schema"):
        await check_rag(db_session, HashEmbedder(dim=64))


async def test_empty_database_rejected(db_session, probe_embedder):
    with pytest.raises(RAGNotReady, match="knowledge base is empty"):
        await check_rag(db_session, probe_embedder)


async def test_retrieves_real_citations_without_writing(db_session, probe_embedder):
    await ingest_kb(db_session, probe_embedder)
    await db_session.flush()
    report = await check_rag(db_session, probe_embedder)
    assert report.documents > 0
    assert report.chunks > report.documents
    assert report.hits
    assert any("Docker" in hit.heading_path for hit in report.hits)
    assert not db_session.new
    assert not db_session.dirty
    assert not db_session.deleted


async def test_different_embedding_model_rejected(db_session, probe_embedder):
    await ingest_kb(db_session, probe_embedder)
    await db_session.execute(update(KBChunk).values(embedding_model="a-different-model"))
    with pytest.raises(RAGNotReady, match="do not match runtime embedder"):
        await check_rag(db_session, probe_embedder)


async def test_missing_embeddings_rejected(db_session, probe_embedder):
    await ingest_kb(db_session, probe_embedder)
    await db_session.execute(update(KBChunk).values(embedding=null()))
    with pytest.raises(RAGNotReady, match="have embeddings"):
        await check_rag(db_session, probe_embedder)


async def test_no_relevant_context_rejected(db_session, probe_embedder, monkeypatch):
    await ingest_kb(db_session, probe_embedder)
    monkeypatch.setattr(settings, "RAG_MIN_SIMILARITY", 1.1)
    with pytest.raises(RAGNotReady, match="returned no context"):
        await check_rag(db_session, probe_embedder, query=DEFAULT_QUERY)
