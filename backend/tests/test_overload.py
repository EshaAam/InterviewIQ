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
from app.schemas.pipeline import AnswerEvaluationResult, SkillExtractionResult
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


# --- model fallback ----------------------------------------------------------
# Overload is per model: on 2026-10-15 gemini-3.6/3.7/3.8-flash all answered 503
# for every key while gemini-3.5-flash and gemini-3.1-flash-lite answered in ~2 s.


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _gemini(fallbacks=("backup-a", "backup-b"), *, behaviour, clock=None):
    """A GeminiProvider whose per-model call is scripted: model -> exception or result."""
    provider = GeminiProvider(
        keys=["k"],
        model="primary",
        fallback_models=fallbacks,
        overload_cooldown=60.0,
        clock=clock or _Clock(),
    )
    tried: list[str] = []

    async def generate(model, prompt, schema, temperature):
        tried.append(model)
        outcome = behaviour.get(model, "ok")
        if isinstance(outcome, Exception):
            raise outcome
        return _Response()

    provider._generate = generate
    return provider, tried


class _Response:
    usage_metadata = None
    parsed = None
    text = '{"skills": []}'


async def test_an_overloaded_model_falls_back_to_the_next():
    from app.providers.gemini import answered_by

    provider, tried = _gemini(behaviour={"primary": LLMOverloaded("503")})
    token = answered_by.set("")
    try:
        result = await provider.complete("p", SkillExtractionResult)
        assert result.skills == []
        assert tried == ["primary", "backup-a"]
        assert answered_by.get() == "backup-a"
    finally:
        answered_by.reset(token)


async def test_an_overloaded_model_is_tried_last_until_its_cooldown_passes():
    clock = _Clock()
    provider, tried = _gemini(behaviour={"primary": LLMOverloaded("503")}, clock=clock)
    await provider.complete("p", SkillExtractionResult)
    tried.clear()

    # Within the cooldown the primary is not asked first: no doomed request.
    await provider.complete("p", SkillExtractionResult)
    assert tried == ["backup-a"]

    # After it, the primary gets its turn again.
    clock.now = 61.0
    tried.clear()
    await provider.complete("p", SkillExtractionResult)
    assert tried == ["primary", "backup-a"]


async def test_a_retired_model_is_skipped():
    from app.providers.gemini import LLMModelUnavailable

    provider, tried = _gemini(
        behaviour={"primary": LLMOverloaded("503"), "backup-a": LLMModelUnavailable("404")}
    )
    await provider.complete("p", SkillExtractionResult)
    assert tried == ["primary", "backup-a", "backup-b"]


async def test_when_every_model_is_overloaded_the_task_retry_takes_over():
    provider, tried = _gemini(
        behaviour={m: LLMOverloaded("503") for m in ("primary", "backup-a", "backup-b")}
    )
    with pytest.raises(LLMOverloaded):
        await provider.complete("p", SkillExtractionResult)
    assert tried == ["primary", "backup-a", "backup-b"]
    assert is_retryable(LLMOverloaded("503"))


async def test_other_errors_do_not_fall_back():
    """A rate limit or a malformed reply is not the model's capacity problem."""
    provider, tried = _gemini(behaviour={"primary": LLMRateLimited("429")})
    with pytest.raises(LLMRateLimited):
        await provider.complete("p", SkillExtractionResult)
    assert tried == ["primary"]


async def test_without_fallbacks_behaviour_is_unchanged():
    provider, tried = _gemini(fallbacks=(), behaviour={"primary": LLMOverloaded("503")})
    with pytest.raises(LLMOverloaded):
        await provider.complete("p", SkillExtractionResult)
    assert tried == ["primary"]


def test_gemini_404_means_the_model_is_unavailable():
    from app.providers.gemini import LLMModelUnavailable

    assert isinstance(GeminiProvider._map_error(_ApiError(404)), LLMModelUnavailable)


def test_fallback_models_are_read_from_config(monkeypatch):
    from app.core.config import settings

    raw = " gemini-3.5-flash, ,gemini-3.1-flash-lite "
    monkeypatch.setattr(settings, "GEMINI_FALLBACK_MODELS", raw)
    assert settings.gemini_fallback_models == ["gemini-3.5-flash", "gemini-3.1-flash-lite"]


async def test_the_ledger_records_the_model_that_actually_answered(db_session):
    """Billing and quota are per model, so the row must name the fallback."""
    from sqlalchemy import select

    from app.models import LLMCall
    from app.providers.gemini import answered_by
    from app.services.pipeline import _complete_metered

    class Answering:
        name = "primary"
        model = "primary"

        async def complete(self, prompt, schema, *, temperature=0.0):
            answered_by.set("backup-a")
            return SkillExtractionResult(skills=[])

        async def embed(self, texts):
            return []

    await _complete_metered(
        db_session, Answering(), "p", SkillExtractionResult, session_id=None, user_id=None
    )
    row = await db_session.scalar(select(LLMCall))
    assert row.model == "backup-a" and row.status == "ok"
    assert answered_by.get() == ""  # reset after the call
