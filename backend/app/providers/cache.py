"""Pluggable cache for the caching provider wrapper.

A tiny async get/set protocol with two implementations: Redis for production
and an in-memory dict for tests (so the wrapper is exercised fully offline).
Only completion results are cached — keyed on the content that determines the
output: prompt + model + schema + prompt_version.
"""

from __future__ import annotations

import hashlib
from typing import Protocol


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
    """Redis-backed cache. Lazily creates the client so import stays cheap."""

    def __init__(self, url: str) -> None:
        self._url = url
        self._client = None

    def _redis(self):
        if self._client is None:
            from redis.asyncio import Redis

            self._client = Redis.from_url(self._url, decode_responses=True)
        return self._client

    async def get(self, key: str) -> str | None:
        return await self._redis().get(key)

    async def set(self, key: str, value: str, ttl: int) -> None:
        await self._redis().set(key, value, ex=ttl)
