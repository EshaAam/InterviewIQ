"""FakeProvider — canned, deterministic, offline.

The entire pipeline is built and tested against this before a real API key
exists. Two properties matter:

- **Deterministic:** `embed` is a hash-derived unit vector, so the same text
  always yields the same vector and cosine scores are reproducible in tests.
- **Scriptable:** `complete` looks up a canned response per output schema. A
  response may be a model instance, a dict (validated on return), a callable
  `(prompt) -> dict|model`, or an `Exception` to simulate malformed output /
  a provider fault. This is what drives the "malformed → FAILED" test.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.embedders.hashing import HashEmbedder
from app.providers.base import LLMError, LLMProvider, LLMValidationError

T = TypeVar("T", bound=BaseModel)

# A canned response: a model, a raw dict, a factory, or an error to raise.
CannedResponse = BaseModel | dict | Callable[[str], "BaseModel | dict"] | Exception
CannedMap = dict[type[BaseModel], CannedResponse]


class FakeProvider:
    """In-memory LLM stand-in. Satisfies the `LLMProvider` protocol."""

    name = "fake"

    def __init__(self, *, canned: CannedMap | None = None, embed_dim: int = 64) -> None:
        self._canned: CannedMap = canned or {}
        self.embed_dim = embed_dim
        # The hashing vectors now live in the embedder seam; delegating keeps
        # one implementation rather than two that must stay bit-identical.
        self._embedder = HashEmbedder(dim=embed_dim)
        # Recorded for test assertions and to mimic the metering ledger.
        self.completions: list[tuple[str, str]] = []

    def register(self, schema: type[BaseModel], response: CannedResponse) -> None:
        self._canned[schema] = response

    async def complete(
        self, prompt: str, schema: type[T], *, temperature: float = 0.0
    ) -> T:
        self.completions.append((schema.__name__, prompt))

        if schema not in self._canned:
            raise LLMError(f"FakeProvider has no canned response for {schema.__name__}")

        response = self._canned[schema]
        if isinstance(response, Exception):
            raise response
        if callable(response) and not isinstance(response, BaseModel):
            response = response(prompt)
        if isinstance(response, schema):
            return response
        try:
            return schema.model_validate(response)
        except ValidationError as exc:
            # Simulates unparseable model output surfacing at the validation layer.
            raise LLMValidationError(str(exc)) from exc

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return await self._embedder.embed(texts)

    def _embed_one(self, text: str) -> list[float]:
        """Kept for tests that assert on a single vector directly."""
        return self._embedder.embed_one(text)


# A tiny structural check so a signature drift trips at import time in tests.
_: type[LLMProvider] = FakeProvider


class LatencyProvider:
    """Adds a fixed delay to every call of the provider it wraps.

    For load tests and chaos drills only (`FAKE_LATENCY_MS`). The fake answers
    in microseconds, so without this a load test measures a queue that never
    fills and a "kill the worker mid-grading" drill has no middle to kill in.
    A real model call takes seconds; this puts that shape back.
    """

    def __init__(self, inner: LLMProvider, *, latency_ms: int) -> None:
        self.inner = inner
        self.name = inner.name
        self._delay = latency_ms / 1000

    async def complete(self, prompt: str, schema: type[T], *, temperature: float = 0.0) -> T:
        await asyncio.sleep(self._delay)
        return await self.inner.complete(prompt, schema, temperature=temperature)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        await asyncio.sleep(self._delay)
        return await self.inner.embed(texts)
