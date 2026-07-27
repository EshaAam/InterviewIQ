"""The provider contract.

Everything downstream depends on this Protocol, never on a concrete provider.
Phase 2 runs entirely on `FakeProvider`; Phase 3 adds Gemini/Ollama behind the
same two methods. The wrapper stack from the design doc (cache, budget, circuit
breaker, retry, meter) also lands in Phase 3 — it composes *around* a provider
without changing this interface.
"""

from __future__ import annotations

from typing import Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """Base class for all provider-layer failures."""


class LLMValidationError(LLMError):
    """Model output could not be coerced into the requested schema.

    Raised after the (single) repair attempt is exhausted — the caller treats
    this as a dead-letter and fails the session, rather than looping forever.
    """


@runtime_checkable
class LLMProvider(Protocol):
    """Provider-agnostic LLM interface.

    `complete` returns a *validated* instance of `schema`; producing malformed
    output that can't be validated is signalled with `LLMValidationError`.
    `embed` powers the deterministic evaluation pass and never hits an LLM
    completion endpoint.
    """

    name: str

    async def complete(
        self, prompt: str, schema: type[T], *, temperature: float = 0.0
    ) -> T: ...

    async def embed(self, texts: list[str]) -> list[list[float]]: ...
