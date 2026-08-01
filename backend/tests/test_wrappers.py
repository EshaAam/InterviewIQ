"""Resilience wrapper stack — retry, circuit breaker, repair, cache.

Each wrapper is exercised against a scripted provider so the behavior is
deterministic and fully offline. Sleeps and clocks are injected so timing-based
logic (backoff, breaker reset) runs instantly.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from app.providers.base import (
    LLMCircuitOpen,
    LLMTransientError,
    LLMValidationError,
)
from app.providers.cache import InMemoryCache
from app.providers.wrappers import (
    CachingProvider,
    CircuitBreakerProvider,
    RepairingProvider,
    RetryingProvider,
)


class _Schema(BaseModel):
    value: int


class ScriptedProvider:
    """Returns/raises a scripted sequence; counts calls and records prompts."""

    name = "scripted"

    def __init__(self, script: list) -> None:
        self._script = list(script)
        self.calls = 0
        self.prompts: list[str] = []

    async def complete(self, prompt, schema, *, temperature=0.0):
        self.calls += 1
        self.prompts.append(prompt)
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        return schema.model_validate(item)

    async def embed(self, texts):
        return [[0.0] for _ in texts]


async def _nosleep(_seconds):
    return None


# --- Retry ---

async def test_retry_recovers_after_transient_failures() -> None:
    inner = ScriptedProvider(
        [LLMTransientError("503"), LLMTransientError("503"), {"value": 42}]
    )
    provider = RetryingProvider(
        inner, max_attempts=2, base_delay=0.0, sleep=_nosleep
    )
    result = await provider.complete("p", _Schema)
    assert result.value == 42
    assert inner.calls == 3  # 1 initial + 2 retries


async def test_retry_gives_up_after_max_attempts() -> None:
    inner = ScriptedProvider([LLMTransientError("a"), LLMTransientError("b")])
    provider = RetryingProvider(
        inner, max_attempts=1, base_delay=0.0, sleep=_nosleep
    )
    with pytest.raises(LLMTransientError):
        await provider.complete("p", _Schema)
    assert inner.calls == 2


async def test_retry_does_not_retry_terminal_errors() -> None:
    inner = ScriptedProvider([LLMValidationError("bad json")])
    provider = RetryingProvider(
        inner, max_attempts=2, base_delay=0.0, sleep=_nosleep
    )
    with pytest.raises(LLMValidationError):
        await provider.complete("p", _Schema)
    assert inner.calls == 1  # terminal -> no retry


# --- Circuit breaker ---

async def test_breaker_opens_after_threshold_and_fails_fast() -> None:
    inner = ScriptedProvider([LLMTransientError("x")] * 2)
    provider = CircuitBreakerProvider(
        inner, threshold=2, reset_seconds=30.0, clock=lambda: 0.0
    )
    for _ in range(2):
        with pytest.raises(LLMTransientError):
            await provider.complete("p", _Schema)

    # Now open: next call fails fast without touching the inner provider.
    with pytest.raises(LLMCircuitOpen):
        await provider.complete("p", _Schema)
    assert inner.calls == 2


async def test_breaker_half_opens_after_reset() -> None:
    clock = {"t": 0.0}
    inner = ScriptedProvider([LLMTransientError("x"), {"value": 7}])
    provider = CircuitBreakerProvider(
        inner, threshold=1, reset_seconds=10.0, clock=lambda: clock["t"]
    )
    with pytest.raises(LLMTransientError):
        await provider.complete("p", _Schema)  # opens

    clock["t"] = 11.0  # past reset window -> half-open, allow a probe
    result = await provider.complete("p", _Schema)
    assert result.value == 7


# --- Repair ---

async def test_repair_reasks_once_on_malformed_then_succeeds() -> None:
    inner = ScriptedProvider([LLMValidationError("bad"), {"value": 1}])
    provider = RepairingProvider(inner)
    result = await provider.complete("original", _Schema)
    assert result.value == 1
    assert inner.calls == 2
    assert inner.prompts[1].startswith("Your previous response")  # corrective preamble


async def test_repair_deadletters_if_still_malformed() -> None:
    inner = ScriptedProvider([LLMValidationError("a"), LLMValidationError("b")])
    provider = RepairingProvider(inner)
    with pytest.raises(LLMValidationError):
        await provider.complete("p", _Schema)
    assert inner.calls == 2


# --- Cache ---

async def test_cache_hit_skips_inner_call() -> None:
    inner = ScriptedProvider([{"value": 5}])  # only one response available
    cache = InMemoryCache()
    provider = CachingProvider(
        inner, cache=cache, ttl=60, prompt_version="v1"
    )
    first = await provider.complete("same prompt", _Schema)
    second = await provider.complete("same prompt", _Schema)
    assert first.value == second.value == 5
    assert inner.calls == 1  # second served from cache


async def test_cache_miss_on_different_prompt() -> None:
    inner = ScriptedProvider([{"value": 1}, {"value": 2}])
    provider = CachingProvider(
        inner, cache=InMemoryCache(), ttl=60, prompt_version="v1"
    )
    a = await provider.complete("prompt A", _Schema)
    b = await provider.complete("prompt B", _Schema)
    assert (a.value, b.value) == (1, 2)
    assert inner.calls == 2


async def test_full_stack_composes() -> None:
    # cache(breaker(retry(repair(inner)))) — one transient blip then success.
    inner = ScriptedProvider([LLMTransientError("blip"), {"value": 99}])
    provider = CachingProvider(
        CircuitBreakerProvider(
            RetryingProvider(
                RepairingProvider(inner), max_attempts=2, base_delay=0.0, sleep=_nosleep
            ),
            threshold=5,
            reset_seconds=30.0,
        ),
        cache=InMemoryCache(),
        ttl=60,
        prompt_version="v1",
    )
    result = await provider.complete("p", _Schema)
    assert result.value == 99
