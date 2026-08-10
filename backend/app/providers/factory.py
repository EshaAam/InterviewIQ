"""Provider selection and wrapper composition.

`get_provider()` returns a fully-wrapped provider so the rest of the app depends
only on the `LLMProvider` protocol. The resilience stack (spec §5) is applied
outermost-first:

    Cache → CircuitBreaker → Retry → Repair → <concrete provider>

The fake provider is returned bare (deterministic; nothing to make resilient),
which keeps the Phase 2 test suite fast and unchanged.
"""

from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.providers.base import LLMProvider
from app.providers.cache import RedisCache
from app.providers.canned import default_canned_responses
from app.providers.fake import FakeProvider
from app.providers.wrappers import (
    CachingProvider,
    CircuitBreakerProvider,
    RepairingProvider,
    RetryingProvider,
)


def wrap_with_resilience(inner: LLMProvider, *, prompt_version: str) -> LLMProvider:
    """Apply the §5 stack around any concrete provider."""
    provider: LLMProvider = RepairingProvider(inner)
    provider = RetryingProvider(
        provider,
        max_attempts=settings.LLM_RETRY_MAX_ATTEMPTS,
        base_delay=settings.LLM_RETRY_BASE_DELAY_SECONDS,
    )
    provider = CircuitBreakerProvider(
        provider,
        threshold=settings.LLM_BREAKER_THRESHOLD,
        reset_seconds=settings.LLM_BREAKER_RESET_SECONDS,
    )
    provider = CachingProvider(
        provider,
        cache=RedisCache(settings.REDIS_URL),
        ttl=settings.LLM_CACHE_TTL_SECONDS,
        prompt_version=prompt_version,
    )
    return provider


@lru_cache
def get_provider() -> LLMProvider:
    from app.services.pipeline import PROMPT_VERSION

    match settings.LLM_PROVIDER:
        case "fake":
            return FakeProvider(canned=default_canned_responses())
        case "gemini":
            from app.providers.gemini import GeminiProvider

            keys = settings.gemini_keys
            if not keys:
                raise ValueError(
                    "LLM_PROVIDER=gemini requires GEMINI_API_KEY or GEMINI_API_KEYS"
                )
            concrete = GeminiProvider(
                keys=keys,
                model=settings.GEMINI_MODEL,
                embed_model=settings.GEMINI_EMBED_MODEL,
                cooldown=settings.GEMINI_KEY_COOLDOWN_SECONDS,
            )
            return wrap_with_resilience(concrete, prompt_version=PROMPT_VERSION)
        case "ollama":  # pragma: no cover - optional, Phase 3 stretch
            raise NotImplementedError("OllamaProvider not yet implemented")
        case other:  # pragma: no cover - guarded by settings Literal
            raise ValueError(f"unknown LLM_PROVIDER: {other!r}")
