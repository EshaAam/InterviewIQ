"""GeminiProvider — the concrete adapter over Google's `google-genai` SDK.

Kept deliberately thin: request structured JSON (temperature 0 for
reproducibility), coerce into the Pydantic schema, expose token usage, and map
SDK faults onto our exception taxonomy so the resilience wrappers can react.

Free-tier rate limits are per key, so the provider pools multiple keys and
rotates: each call round-robins to the next healthy key, and a key that returns
a 429 is benched for a cooldown window. When every key is benched we surface a
transient error and let the retry/breaker wrappers take over.

Overload is per *model*, not per key: when Google sheds load on one model
(503 "high demand"), every key gets the same answer, sometimes for hours, while
a neighbouring model answers in two seconds. So completions walk a fallback
chain — the configured model, then `GEMINI_FALLBACK_MODELS` in order — and a
model that just answered 503 is skipped for a short cooldown, so each call does
not pay for a doomed request first. A retired model (404) is skipped too.
Whichever model answered is published in `answered_by`, so the ledger records
the model that was actually billed.

The SDK is synchronous, so calls run in a worker thread to stay async-friendly.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Sequence
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.providers.base import (
    LLMError,
    LLMOverloaded,
    LLMProvider,
    LLMRateLimited,
    LLMTransientError,
    LLMValidationError,
)

T = TypeVar("T", bound=BaseModel)

#: The model that produced the last completion in this context — the fallback
#: when the primary was overloaded. A ContextVar, not an attribute: one provider
#: serves many concurrent calls. Read by the metering code; empty means "the
#: configured model".
answered_by: ContextVar[str] = ContextVar("gemini_answered_by", default="")


class LLMModelUnavailable(LLMError):
    """The model does not exist for this key (404) — retired or misspelled.

    Terminal for that model, so it is skipped in the fallback chain; if it is
    the last model left, the call fails like any other permanent error.
    """


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
        fallback_models: Sequence[str] = (),
        embed_model: str = "gemini-embedding-001",
        cooldown: float = 60.0,
        overload_cooldown: float = 60.0,
        timeout: float | None = 60.0,
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
        # Primary first, then fallbacks in order, without repeats.
        self.models = list(dict.fromkeys([model, *(m for m in fallback_models if m)]))
        self.embed_model = embed_model
        self.last_usage = Usage()
        self._clock = clock
        self._overload_cooldown = overload_cooldown
        self._overloaded_until: dict[str, float] = {}
        # Per request, in seconds. google-genai's own default is *no* timeout,
        # and the Render worker is a single process: one call that never
        # returns would freeze every grading job behind it, leaving sessions
        # in "Scoring" until something restarts the container.
        self._timeout = timeout

    def _client(self, key: str):
        if key not in self._clients:
            from google.genai import types

            http_options = (
                types.HttpOptions(timeout=int(self._timeout * 1000)) if self._timeout else None
            )
            self._clients[key] = self._genai.Client(api_key=key, http_options=http_options)
        return self._clients[key]

    async def _execute(self, call: Callable[[object], object]):
        """Run `call(client)` against pooled keys, rotating past rate-limited ones."""
        import httpx
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
            except httpx.TimeoutException as exc:
                # Transient: the task's retry/give-up path takes it from here,
                # so a stalled call ends in a retry or a stated failure.
                raise LLMTransientError(
                    f"gemini did not answer within {self._timeout:g}s: {exc!r}"
                ) from exc
        raise LLMRateLimited(
            f"all {len(self._pool)} gemini keys rate-limited: {last_rate_limit}"
        )

    def _chain(self) -> list[str]:
        """Models to try, in order: rested ones first, recently-overloaded last.

        A model in its overload cooldown is not dropped — if every model is
        overloaded, trying them all again is still the right last resort.
        """
        now = self._clock()
        rested = [m for m in self.models if self._overloaded_until.get(m, 0.0) <= now]
        tired = [m for m in self.models if m not in rested]
        return rested + tired

    async def _generate(self, model: str, prompt: str, schema: type[T], temperature: float):
        from google.genai import types

        def call(client):
            return client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=schema,
                    temperature=temperature,
                ),
            )

        return await self._execute(call)

    async def complete(
        self, prompt: str, schema: type[T], *, temperature: float = 0.0
    ) -> T:
        response = None
        last: LLMError | None = None
        for model in self._chain():
            try:
                response = await self._generate(model, prompt, schema, temperature)
            except LLMOverloaded as exc:
                # Shedding load on this model; its neighbours usually are not.
                self._overloaded_until[model] = self._clock() + self._overload_cooldown
                last = exc
                continue
            except LLMModelUnavailable as exc:
                last = exc
                continue
            self._overloaded_until.pop(model, None)
            answered_by.set(model)
            break
        if response is None:
            assert last is not None
            raise last

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
        if code == 503:
            return LLMOverloaded(f"gemini overloaded (503): {exc}")
        if code == 404:
            return LLMModelUnavailable(f"gemini model unavailable (404): {exc}")
        if isinstance(code, int) and code >= 500:
            return LLMTransientError(f"gemini transient error {code}: {exc}")
        return LLMError(f"gemini error {code}: {exc}")


_check: type[LLMProvider] = GeminiProvider
