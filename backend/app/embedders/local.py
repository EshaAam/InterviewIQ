"""LocalEmbedder — a real embedding model, on the CPU, for free.

`bge-small-en-v1.5` through **fastembed**, which runs the model as ONNX. The
choice of fastembed over `sentence-transformers` is the whole reason this is
viable: sentence-transformers pulls in PyTorch and adds roughly 2 GB to the
image, while fastembed pulls onnxruntime and adds a few hundred megabytes. For
a 384-dimension model that fits in ~130 MB, carrying a deep-learning framework
to run it is a bad trade.

Why local at all, when the Gemini embedding endpoint already works: RAG embeds
the entire knowledge base once and then one query per skill per interview,
forever. That is the workload where a per-call hosted API stops making sense —
and a downloaded model is free, offline, and returns byte-identical vectors on
every run, which the deterministic grading pass genuinely wants.

The model is **pre-downloaded at image build time** (see `backend/Dockerfile`).
A worker that fetches 130 MB in the middle of a job is a worker that times out.
"""

from __future__ import annotations

import asyncio
from typing import Any


class LocalEmbedder:
    """fastembed-backed embedder. Loads the model once, on first use."""

    def __init__(
        self,
        *,
        model_name: str = "BAAI/bge-small-en-v1.5",
        dim: int = 384,
        cache_dir: str | None = None,
        threads: int | None = None,
    ) -> None:
        self.name = model_name
        self.dim = dim
        self._cache_dir = cache_dir
        self._threads = threads
        self._model: Any | None = None

    def _load(self) -> Any:
        """Import and construct lazily.

        fastembed is only needed when this embedder is actually selected, so the
        unit suite (which pins `EMBEDDING_PROVIDER=hash`) never imports it and
        never touches the filesystem cache.
        """
        if self._model is None:
            try:
                from fastembed import TextEmbedding
            except ImportError as exc:  # pragma: no cover - deployment error
                raise RuntimeError(
                    "EMBEDDING_PROVIDER=local requires the `fastembed` package. "
                    "Run `uv sync` in backend/, or set EMBEDDING_PROVIDER=hash."
                ) from exc
            self._model = TextEmbedding(
                model_name=self.name,
                cache_dir=self._cache_dir,
                threads=self._threads,
            )
        return self._model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        # fastembed is synchronous and CPU-bound. Calling it directly on the
        # event loop would stall every other coroutine in the worker for the
        # duration — the same reason the Gemini SDK is wrapped in to_thread.
        return await asyncio.to_thread(self._embed_sync, texts)

    def _embed_sync(self, texts: list[str]) -> list[list[float]]:
        model = self._load()
        vectors = [list(map(float, v)) for v in model.embed(texts)]
        if vectors and len(vectors[0]) != self.dim:
            raise RuntimeError(
                f"{self.name} returned {len(vectors[0])}-dim vectors but EMBEDDING_DIM "
                f"is {self.dim}. A vector index built at the wrong width fails at "
                f"query time, so this is fatal at startup instead."
            )
        return vectors
