"""Provider overload: one request per attempt, and an honest message.

Gemini answered 503 "high demand" for hours. The in-process retry tried three
times per task attempt and the task tried five times, so one stuck stage sent
up to 15 requests against a free tier of 20 a day. Overload and rate limits now
skip the in-process retry and go straight to the task-level backoff.
"""

from __future__ import annotations

import pytest

from app.providers.base import (
    LLMOverloaded,
    LLMRateLimited,
    LLMTransientError,
)
from app.providers.gemini import GeminiProvider
from app.providers.wrappers import RetryingProvider
from app.schemas.pipeline import AnswerEvaluationResult
from app.services.pipeline import describe_failure, is_retryable


class Failing:
    name = "failing"

    def __init__(self, exc: Exception) -> None:
        self.exc = exc
        self.calls = 0

    async def complete(self, prompt, schema, *, temperature=0.0):
        self.calls += 1
        raise self.exc

    async def embed(self, texts):
        return []


async def _no_sleep(_):
    return None


@pytest.mark.parametrize("exc", [LLMOverloaded("503"), LLMRateLimited("429")])
async def test_overload_and_rate_limits_are_not_retried_in_process(exc):
    inner = Failing(exc)
    retrying = RetryingProvider(inner, max_attempts=2, base_delay=0, sleep=_no_sleep)

    with pytest.raises(type(exc)):
        await retrying.complete("p", AnswerEvaluationResult)
    assert inner.calls == 1


async def test_a_brief_transient_fault_is_still_retried():
    """A dropped connection or a stray 500 can clear in under a second."""
    inner = Failing(LLMTransientError("500"))
    retrying = RetryingProvider(inner, max_attempts=2, base_delay=0, sleep=_no_sleep)

    with pytest.raises(LLMTransientError):
        await retrying.complete("p", AnswerEvaluationResult)
    assert inner.calls == 3


def test_overload_is_still_retried_by_the_task():
    # It skips the in-process retry, not the 30s/60s/120s task backoff.
    assert is_retryable(LLMOverloaded("503"))


class _ApiError(Exception):
    def __init__(self, code: int) -> None:
        super().__init__(f"{code}")
        self.code = code


def test_gemini_503_is_an_overload():
    assert isinstance(GeminiProvider._map_error(_ApiError(503)), LLMOverloaded)


def test_other_5xx_stay_ordinary_transient_errors():
    error = GeminiProvider._map_error(_ApiError(500))
    assert isinstance(error, LLMTransientError)
    assert not isinstance(error, LLMOverloaded)


def test_the_candidate_is_told_the_provider_is_overloaded():
    message = describe_failure("Generating your questions", LLMOverloaded("503 high demand"))
    assert "overloaded" in message
    assert "503" not in message
