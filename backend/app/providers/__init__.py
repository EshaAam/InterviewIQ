"""LLM provider layer — provider-agnostic by contract (see base.LLMProvider)."""

from app.providers.base import (
    LLMBudgetExceeded,
    LLMCircuitOpen,
    LLMError,
    LLMOverloaded,
    LLMProvider,
    LLMRateLimited,
    LLMTransientError,
    LLMValidationError,
)
from app.providers.factory import get_provider, wrap_with_resilience
from app.providers.fake import FakeProvider

__all__ = [
    "LLMProvider",
    "LLMError",
    "LLMTransientError",
    "LLMRateLimited",
    "LLMOverloaded",
    "LLMValidationError",
    "LLMCircuitOpen",
    "LLMBudgetExceeded",
    "FakeProvider",
    "get_provider",
    "wrap_with_resilience",
]
