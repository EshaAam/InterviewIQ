"""Pluggable cache for the caching provider wrapper.

A tiny async get/set protocol with two implementations: Redis for production
and an in-memory dict for tests (so the wrapper is exercised fully offline).
Only completion results are cached — keyed on the content that determines the
output: prompt + model + schema + prompt_version.
"""

from __future__ import annotations

import asyncio
import hashlib
from contextvars import ContextVar
from typing import Protocol

# Set to True by CachingProvider when it answers from the cache, so the meter
# (which sits outside the provider stack) can record the call as free rather
# than charging for tokens nobody spent. A ContextVar, not an attribute on the
# provider: one provider instance serves many concurrent calls, and a shared
# attribute would let one call read another's answer.
served_from_cache: ContextVar[bool] = ContextVar("served_from_cache", default=False)


class LLMCache(Protocol):
    async def get(self, key: str) -> str | None: ...
    async def set(self, key: str, value: str, ttl: int) -> None: ...


def cache_key(*, prompt: str, model: str, schema: str, prompt_version: str) -> str:
    raw = f"{model}\x1f{schema}\x1f{prompt_version}\x1f{prompt}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"llm:complete:{digest}"


class InMemoryCache:
    """Non-expiring in-process cache. Test/dev only."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def set(self, key: str, value: str, ttl: int) -> None:
        self._store[key] = value


class RedisCache:
    """Redis-backed cache. Lazily creates the client so import stays cheap.

    One client per event loop. The provider (and so this cache) is cached for
    the whole process, but every Celery task runs in a fresh `asyncio.run`
    loop, and an asyncio Redis client is bound to the loop that created it.
    A single shared client failed on every task after the first — silently,
    because the caching wrapper swallows cache errors — so workers never hit.
    """

    def __init__(self, url: str) -> None:
        self._url = url
        self._client = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def _redis(self):
        loop = asyncio.get_running_loop()
        if self._client is None or self._loop is not loop:
            from redis.asyncio import Redis

            self._client = Redis.from_url(self._url, decode_responses=True)
            self._loop = loop
        return self._client

    async def get(self, key: str) -> str | None:
        return await self._redis().get(key)

    async def set(self, key: str, value: str, ttl: int) -> None:
        await self._redis().set(key, value, ex=ttl)
