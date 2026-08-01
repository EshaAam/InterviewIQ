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

import hashlib
import math
import re
from collections.abc import Callable
from typing import TypeVar

from pydantic import BaseModel, ValidationError

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
        return [self._embed_one(t) for t in texts]

    def _embed_one(self, text: str) -> list[float]:
        """A deterministic, L2-normalized hashing bag-of-words vector.

        Each token is hashed to a dimension, so texts that share words get a
        positive cosine — a cheap, offline stand-in for semantic similarity.
        This makes the deterministic evaluation pass meaningful in tests without
        a real embedding model.
        """
        vals = [0.0] * self.embed_dim
        for token in re.findall(r"[a-z0-9]+", text.lower()):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            vals[int.from_bytes(digest[:4], "big") % self.embed_dim] += 1.0
        norm = math.sqrt(sum(v * v for v in vals)) or 1.0
        return [v / norm for v in vals]


# A tiny structural check so a signature drift trips at import time in tests.
_: type[LLMProvider] = FakeProvider
