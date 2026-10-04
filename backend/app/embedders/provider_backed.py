"""ProviderEmbedder — today's behaviour, kept reachable.

Before the embedder seam existed, the deterministic grading pass called
`LLMProvider.embed`, which on Gemini means `gemini-embedding-001` over the
network. This adapter preserves that path exactly, so switching to a local
model is a config change rather than a one-way door: if `LocalEmbedder` turns
out to be too heavy for wherever this is deployed, `EMBEDDING_PROVIDER=gemini`
restores the previous behaviour with no code change.

Embedding calls pass through the resilience wrappers untouched (they only wrap
`complete`), so this inherits the circuit breaker and retry behaviour of
whatever provider it is handed.
"""

from __future__ import annotations

from app.providers.base import LLMProvider


class ProviderEmbedder:
    """Delegates embedding to an `LLMProvider`."""

    def __init__(self, provider: LLMProvider, *, name: str, dim: int) -> None:
        self._provider = provider
        self.name = name
        self.dim = dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return await self._provider.embed(texts)
