"""Resilience decorators around any `LLMProvider` (design spec §5).

Each wrapper *is* an `LLMProvider` and delegates to an inner one, so they
compose. The intended production order, outermost first:

    Cache → CircuitBreaker → Retry → Repair → <concrete provider>

- **Cache** short-circuits identical calls (no inner call on a hit).
- **CircuitBreaker** fails fast while the provider is known-down.
- **Retry** backs off on transient faults only.
- **Repair** turns one malformed response into a single re-ask, then dead-letters.

`embed` is passed straight through by every wrapper except the cache (which
only memoizes completions).
"""

from __future__ import annotations

import asyncio
import random
import time
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.providers.base import (
    LLMCircuitOpen,
    LLMProvider,
    LLMTransientError,
    LLMValidationError,
)
from app.providers.cache import LLMCache, cache_key

T = TypeVar("T", bound=BaseModel)


class RetryingProvider:
    """Exponential backoff + jitter on transient faults only."""

    def __init__(
        self,
        inner: LLMProvider,
        *,
        max_attempts: int,
        base_delay: float,
        sleep=asyncio.sleep,
    ) -> None:
        self.inner = inner
        self.name = inner.name
        self._max_attempts = max_attempts
        self._base_delay = base_delay
        self._sleep = sleep

    async def complete(
        self, prompt: str, schema: type[T], *, temperature: float = 0.0
    ) -> T:
        last: LLMTransientError | None = None
        for attempt in range(self._max_attempts + 1):
            try:
                return await self.inner.complete(prompt, schema, temperature=temperature)
            except LLMTransientError as exc:
                last = exc
                if attempt == self._max_attempts:
                    break
                delay = self._base_delay * (2**attempt)
                await self._sleep(delay + random.uniform(0, self._base_delay))
        assert last is not None
        raise last

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return await self.inner.embed(texts)


class CircuitBreakerProvider:
    """Open after N consecutive transient failures; fail fast until reset elapses."""

    def __init__(
        self,
        inner: LLMProvider,
        *,
        threshold: int,
        reset_seconds: float,
        clock=time.monotonic,
    ) -> None:
        self.inner = inner
        self.name = inner.name
        self._threshold = threshold
        self._reset_seconds = reset_seconds
        self._clock = clock
        self._failures = 0
        self._opened_at: float | None = None

    def _is_open(self) -> bool:
        if self._opened_at is None:
            return False
        if self._clock() - self._opened_at >= self._reset_seconds:
            # Half-open: allow the next call through to probe recovery.
            self._opened_at = None
            self._failures = 0
            return False
        return True

    async def complete(
        self, prompt: str, schema: type[T], *, temperature: float = 0.0
    ) -> T:
        if self._is_open():
            raise LLMCircuitOpen(f"{self.name} circuit open")
        try:
            result = await self.inner.complete(prompt, schema, temperature=temperature)
        except LLMTransientError:
            self._failures += 1
            if self._failures >= self._threshold:
                self._opened_at = self._clock()
            raise
        self._failures = 0
        return result

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return await self.inner.embed(texts)


class RepairingProvider:
    """One repair attempt on malformed output, then dead-letter.

    A structured provider raises `LLMValidationError` when it can't coerce the
    response. We re-ask once with a corrective preamble; if it still fails, the
    error propagates as a terminal dead-letter.
    """

    _PREAMBLE = (
        "Your previous response could not be parsed as valid JSON matching the "
        "required schema. Respond again with ONLY valid JSON.\n\n"
    )

    def __init__(self, inner: LLMProvider) -> None:
        self.inner = inner
        self.name = inner.name

    async def complete(
        self, prompt: str, schema: type[T], *, temperature: float = 0.0
    ) -> T:
        try:
            return await self.inner.complete(prompt, schema, temperature=temperature)
        except LLMValidationError:
            return await self.inner.complete(
                self._PREAMBLE + prompt, schema, temperature=temperature
            )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return await self.inner.embed(texts)


class CachingProvider:
    """Memoize completions in an `LLMCache`, keyed on output-determining inputs."""

    def __init__(
        self, inner: LLMProvider, *, cache: LLMCache, ttl: int, prompt_version: str
    ) -> None:
        self.inner = inner
        self.name = inner.name
        self._cache = cache
        self._ttl = ttl
        self._prompt_version = prompt_version

    async def complete(
        self, prompt: str, schema: type[T], *, temperature: float = 0.0
    ) -> T:
        key = cache_key(
            prompt=prompt,
            model=self.name,
            schema=schema.__name__,
            prompt_version=self._prompt_version,
        )
        # The cache is an optimization, never a dependency: if the store is down
        # (e.g. Redis unreachable) we degrade to calling the provider directly.
        try:
            cached = await self._cache.get(key)
        except Exception:
            cached = None
        if cached is not None:
            try:
                return schema.model_validate_json(cached)
            except ValidationError:
                pass  # poisoned entry — fall through and recompute

        result = await self.inner.complete(prompt, schema, temperature=temperature)
        try:
            await self._cache.set(key, result.model_dump_json(), self._ttl)
        except Exception:
            pass  # cache write failure must not fail the request
        return result

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return await self.inner.embed(texts)


# Structural checks: every wrapper must satisfy the protocol.
_checks: list[type[LLMProvider]] = [
    RetryingProvider,
    CircuitBreakerProvider,
    RepairingProvider,
    CachingProvider,
]
