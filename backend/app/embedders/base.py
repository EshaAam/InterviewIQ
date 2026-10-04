"""The embedder contract.

Embeddings were reached through `LLMProvider.embed` because the only consumer
was the deterministic grading pass, and whatever graded was whatever generated.
RAG breaks that assumption: the knowledge base is embedded once at ingest time,
and every retrieval embeds a query — a workload with a completely different cost
profile from "generate some questions". It wants a local model even when
generation stays on a hosted one.

So embedding gets its own seam, deliberately narrower than `LLMProvider`.
Nothing here knows about prompts, schemas or temperature.

`dim` is declared rather than discovered because the Phase 2 `kb_chunks` vector
column is fixed-width: an index built at 384 dimensions cannot hold a 3072-wide
vector, and finding that out at query time is far worse than at startup.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Embedder(Protocol):
    """Text in, vectors out. One vector per input, order preserved."""

    #: Identifies the model that produced a vector. Stored on every chunk so a
    #: mixed-model index is detectable rather than silently wrong.
    name: str
    #: Output width. Must match the vector column the chunks are stored in.
    dim: int

    async def embed(self, texts: list[str]) -> list[list[float]]: ...
