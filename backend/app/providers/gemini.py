"""GeminiProvider — the concrete adapter over Google's `google-genai` SDK.

Kept deliberately thin: request structured JSON (temperature 0 for
reproducibility), coerce into the Pydantic schema, expose token usage, and map
SDK faults onto our exception taxonomy so the resilience wrappers can react.

Free-tier rate limits are per key, so the provider pools multiple keys and
rotates: each call round-robins to the next healthy key, and a key that returns
a 429 is benched for a cooldown window. When every key is benched we surface a
transient error and let the retry/breaker wrappers take over.

The SDK is synchronous, so calls run in a worker thread to stay async-friendly.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.providers.base import (
    LLMError,
    LLMProvider,
    LLMTransientError,
    LLMValidationError,
)

T = TypeVar("T", bound=BaseModel)


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0


class GeminiKeyPool:
    """Round-robin pool of API keys with per-key cooldown after a rate-limit.

    Pure logic (no SDK), so the rotation policy is unit-testable with a fake
    clock. `acquire` returns the next key not currently benched, or None when
    all keys are cooling down.
    """

    def __init__(
        self, keys: list[str], *, cooldown: float, clock: Callable[[], float] = time.monotonic
    ) -> None:
        if not keys:
            raise ValueError("GeminiKeyPool requires at least one key")
        self._keys = list(keys)
        self._until = [0.0] * len(self._keys)
        self._cooldown = cooldown
        self._clock = clock
        self._rr = 0

    def __len__(self) -> int:
        return len(self._keys)

    def acquire(self) -> tuple[int, str] | None:
        now = self._clock()
        n = len(self._keys)
        for offset in range(n):
            i = (self._rr + offset) % n
            if self._until[i] <= now:
                self._rr = (i + 1) % n
                return i, self._keys[i]
        return None

    def penalize(self, index: int) -> None:
        self._until[index] = self._clock() + self._cooldown


class GeminiProvider:
    """Google Gemini via google-genai, with key-pool rotation. Satisfies `LLMProvider`."""

    def __init__(
        self,
        *,
        keys: list[str],
        model: str,
        embed_model: str = "gemini-embedding-001",
        cooldown: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not keys:
            raise ValueError("GeminiProvider requires at least one API key")
        from google import genai

        self._genai = genai
        self._pool = GeminiKeyPool(keys, cooldown=cooldown, clock=clock)
        self._clients: dict[str, object] = {}
        self.name = model
        self.model = model
        self.embed_model = embed_model
        self.last_usage = Usage()

    def _client(self, key: str):
        if key not in self._clients:
            self._clients[key] = self._genai.Client(api_key=key)
        return self._clients[key]

    async def _execute(self, call: Callable[[object], object]):
        """Run `call(client)` against pooled keys, rotating past rate-limited ones."""
        from google.genai.errors import APIError

        last_rate_limit: Exception | None = None
        for _ in range(len(self._pool)):
            acquired = self._pool.acquire()
            if acquired is None:
                break
            index, key = acquired
            try:
                return await asyncio.to_thread(call, self._client(key))
            except APIError as exc:
                if getattr(exc, "code", None) == 429:
                    self._pool.penalize(index)
                    last_rate_limit = exc
                    continue
                raise self._map_error(exc) from exc
        raise LLMTransientError(
            f"all {len(self._pool)} gemini keys rate-limited: {last_rate_limit}"
        )

    async def complete(
        self, prompt: str, schema: type[T], *, temperature: float = 0.0
    ) -> T:
        from google.genai import types

        def call(client):
            return client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=schema,
                    temperature=temperature,
                ),
            )

        response = await self._execute(call)

        usage = getattr(response, "usage_metadata", None)
        self.last_usage = Usage(
            prompt_tokens=getattr(usage, "prompt_token_count", 0) or 0,
            completion_tokens=getattr(usage, "candidates_token_count", 0) or 0,
        )

        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, schema):
            return parsed
        try:
            return schema.model_validate_json(response.text or "")
        except (ValidationError, AttributeError) as exc:
            raise LLMValidationError(f"unparseable gemini output: {exc}") from exc

    async def embed(self, texts: list[str]) -> list[list[float]]:
        def call(client):
            return client.models.embed_content(model=self.embed_model, contents=texts)

        result = await self._execute(call)
        return [list(e.values) for e in result.embeddings]

    @staticmethod
    def _map_error(exc) -> LLMError:
        # 5xx is transient (retry/breaker); other 4xx are terminal.
        code = getattr(exc, "code", None)
        if isinstance(code, int) and code >= 500:
            return LLMTransientError(f"gemini transient error {code}: {exc}")
        return LLMError(f"gemini error {code}: {exc}")


_check: type[LLMProvider] = GeminiProvider
