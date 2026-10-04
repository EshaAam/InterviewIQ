"""Embedder selection.

`auto` is the default and resolves to whatever the app did before this seam
existed: hashing when the LLM provider is the fake (so the offline suite keeps
its exact vectors), the Gemini embedding endpoint otherwise. Adding the seam
therefore changes no behaviour until someone opts in with
`EMBEDDING_PROVIDER=local`.
"""

from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.embedders.base import Embedder
from app.embedders.hashing import HashEmbedder


def resolved_embedding_provider() -> str:
    """`auto` → the pre-seam behaviour. Exposed so startup logs can state it."""
    choice = settings.EMBEDDING_PROVIDER
    if choice != "auto":
        return choice
    return "hash" if settings.LLM_PROVIDER == "fake" else "gemini"


@lru_cache
def get_embedder() -> Embedder:
    """The process-wide embedder. Cached: loading a model per call is ruinous."""
    match resolved_embedding_provider():
        case "hash":
            return HashEmbedder(dim=settings.EMBEDDING_HASH_DIM)
        case "local":
            from app.embedders.local import LocalEmbedder

            return LocalEmbedder(
                model_name=settings.EMBEDDING_MODEL,
                dim=settings.EMBEDDING_DIM,
                cache_dir=settings.EMBEDDING_CACHE_DIR or None,
                threads=settings.EMBEDDING_THREADS or None,
            )
        case "gemini":
            from app.embedders.provider_backed import ProviderEmbedder
            from app.providers import get_provider

            return ProviderEmbedder(
                get_provider(),
                name=settings.GEMINI_EMBED_MODEL,
                dim=settings.GEMINI_EMBED_DIM,
            )
        case other:  # pragma: no cover - guarded by the settings Literal
            raise ValueError(f"unknown EMBEDDING_PROVIDER: {other!r}")
