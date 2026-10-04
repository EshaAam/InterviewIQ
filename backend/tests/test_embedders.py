"""The embedder seam.

Two things matter here. First, that `HashEmbedder` still produces exactly what
`FakeProvider.embed` used to, because the cosine assertions elsewhere in the
suite were calibrated against those vectors. Second, that adding the seam did
not quietly change which embedder the app reaches for — `auto` must resolve to
the pre-seam behaviour.
"""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.embedders import Embedder, HashEmbedder, get_embedder, resolved_embedding_provider
from app.embedders.local import LocalEmbedder
from app.providers import FakeProvider
from app.services.scoring import cosine


@pytest.fixture(autouse=True)
def _clear_embedder_cache():
    get_embedder.cache_clear()
    yield
    get_embedder.cache_clear()


# --- HashEmbedder ----------------------------------------------------------


async def test_hash_embedder_is_deterministic():
    embedder = HashEmbedder(dim=64)
    assert await embedder.embed(["asyncpg pooling"]) == await embedder.embed(["asyncpg pooling"])


async def test_hash_embedder_returns_unit_vectors():
    [vector] = await HashEmbedder(dim=64).embed(["connection pool"])
    assert sum(v * v for v in vector) == pytest.approx(1.0)


async def test_hash_embedder_honours_its_declared_dim():
    embedder = HashEmbedder(dim=32)
    [vector] = await embedder.embed(["anything"])
    assert len(vector) == embedder.dim == 32


async def test_hash_embedder_scores_shared_words_above_unrelated_ones():
    """The property that makes the deterministic pass meaningful offline."""
    embedder = HashEmbedder(dim=64)
    shared, related, unrelated = await embedder.embed(
        ["database connection pooling", "connection pooling matters", "sourdough bread recipe"]
    )
    assert cosine(shared, related) > cosine(shared, unrelated)


async def test_hash_embedder_matches_what_fake_provider_used_to_return():
    """A behavioural pin, not a tautology.

    `FakeProvider` now delegates here instead of carrying its own copy of the
    algorithm. If the hash, the bucket count or the normalisation ever drift,
    every calibrated cosine assertion in the suite moves with it — so the two
    are checked against each other explicitly.
    """
    texts = ["fastapi dependency injection", "postgres index scan"]
    assert await FakeProvider().embed(texts) == await HashEmbedder(dim=64).embed(texts)


async def test_hash_embedder_handles_text_with_no_tokens():
    # An answer of pure punctuation must not divide by a zero norm.
    [vector] = await HashEmbedder(dim=16).embed(["!!! ???"])
    assert vector == [0.0] * 16


def test_hash_embedder_satisfies_the_protocol():
    assert isinstance(HashEmbedder(dim=8), Embedder)


# --- selection -------------------------------------------------------------


def test_auto_resolves_to_hash_on_the_fake_provider(monkeypatch):
    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER", "auto")
    monkeypatch.setattr(settings, "LLM_PROVIDER", "fake")
    assert resolved_embedding_provider() == "hash"
    assert isinstance(get_embedder(), HashEmbedder)


def test_auto_resolves_to_gemini_when_generation_is_hosted(monkeypatch):
    """Adding the seam must not silently downgrade a deployed stack."""
    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER", "auto")
    monkeypatch.setattr(settings, "LLM_PROVIDER", "gemini")
    assert resolved_embedding_provider() == "gemini"


def test_an_explicit_choice_overrides_auto(monkeypatch):
    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER", "hash")
    monkeypatch.setattr(settings, "LLM_PROVIDER", "gemini")
    assert resolved_embedding_provider() == "hash"
    assert isinstance(get_embedder(), HashEmbedder)


def test_the_embedder_is_cached_because_loading_a_model_is_expensive(monkeypatch):
    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER", "hash")
    assert get_embedder() is get_embedder()


# --- LocalEmbedder ---------------------------------------------------------


async def test_local_embedder_does_not_import_fastembed_until_used():
    """Constructing it must stay free, so `hash` deployments never pay for it."""
    embedder = LocalEmbedder(model_name="BAAI/bge-small-en-v1.5", dim=384)
    assert embedder._model is None
    assert embedder.name == "BAAI/bge-small-en-v1.5"
    assert embedder.dim == 384


async def test_local_embedder_skips_the_model_entirely_for_an_empty_batch():
    # No texts, no load — this is what makes a concept-less question cheap.
    assert await LocalEmbedder().embed([]) == []


async def test_local_embedder_refuses_a_width_that_would_break_the_index(monkeypatch):
    """A 384-wide index cannot hold a 768-wide vector.

    Discovering that at query time, after an ingest run has written thousands
    of rows, is far worse than failing on the first embed.
    """

    class WrongWidth:
        def embed(self, texts):
            return [[0.0] * 768 for _ in texts]

    embedder = LocalEmbedder(dim=384)
    monkeypatch.setattr(embedder, "_load", lambda: WrongWidth())

    with pytest.raises(RuntimeError, match="768-dim vectors but EMBEDDING_DIM is 384"):
        await embedder.embed(["anything"])


def test_local_embedder_explains_itself_when_fastembed_is_absent(monkeypatch):
    """The extra is optional, so the failure has to name the fix."""
    import builtins

    real_import = builtins.__import__

    def refuse_fastembed(name, *args, **kwargs):
        if name == "fastembed":
            raise ImportError("No module named 'fastembed'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", refuse_fastembed)

    with pytest.raises(RuntimeError, match="requires the `fastembed` package"):
        LocalEmbedder()._load()
