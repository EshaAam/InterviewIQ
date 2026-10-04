"""Embedding layer — separate from `LLMProvider` by design (see base.Embedder)."""

from app.embedders.base import Embedder
from app.embedders.factory import get_embedder, resolved_embedding_provider
from app.embedders.hashing import HashEmbedder

__all__ = [
    "Embedder",
    "HashEmbedder",
    "get_embedder",
    "resolved_embedding_provider",
]
