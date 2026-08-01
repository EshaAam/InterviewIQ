"""FakeProvider unit tests — determinism, canned dispatch, and fault injection."""

from __future__ import annotations

import math

import pytest
from pydantic import BaseModel

from app.providers import FakeProvider, LLMError, LLMValidationError, get_provider
from app.schemas.pipeline import QuestionGenerationResult, SkillExtractionResult


class _Schema(BaseModel):
    value: int


async def test_embeddings_are_deterministic_and_normalized() -> None:
    p = FakeProvider(embed_dim=64)
    a1, a2 = await p.embed(["hello world", "hello world"])

    assert a1 == a2  # same text -> same vector
    assert len(a1) == 64
    assert math.isclose(math.sqrt(sum(x * x for x in a1)), 1.0, rel_tol=1e-9)


async def test_embeddings_capture_word_overlap() -> None:
    from app.services.scoring import cosine

    p = FakeProvider(embed_dim=128)
    (shared, related, unrelated) = await p.embed(
        ["python async event loop",
         "the event loop runs python coroutines",
         "gardening tips for tomatoes"]
    )
    # Texts sharing words are closer than texts sharing none.
    assert cosine(shared, related) > cosine(shared, unrelated)


async def test_complete_validates_dict_response() -> None:
    p = FakeProvider(canned={_Schema: {"value": 7}})
    result = await p.complete("prompt", _Schema)
    assert isinstance(result, _Schema) and result.value == 7


async def test_complete_accepts_callable_response() -> None:
    p = FakeProvider(canned={_Schema: lambda prompt: {"value": len(prompt)}})
    result = await p.complete("abcd", _Schema)
    assert result.value == 4


async def test_missing_canned_response_raises_llm_error() -> None:
    p = FakeProvider()
    with pytest.raises(LLMError):
        await p.complete("prompt", _Schema)


async def test_malformed_response_raises_validation_error() -> None:
    # A dict that violates the schema simulates unparseable model output.
    p = FakeProvider(canned={_Schema: {"value": "not-an-int"}})
    with pytest.raises(LLMValidationError):
        await p.complete("prompt", _Schema)


async def test_injected_exception_is_raised() -> None:
    boom = LLMValidationError("dead letter")
    p = FakeProvider(canned={_Schema: boom})
    with pytest.raises(LLMValidationError):
        await p.complete("prompt", _Schema)


async def test_completions_are_recorded() -> None:
    p = FakeProvider(canned={_Schema: {"value": 1}})
    await p.complete("first", _Schema)
    assert p.completions == [("_Schema", "first")]


async def test_factory_returns_fake_with_pipeline_responses() -> None:
    provider = get_provider()
    assert provider.name == "fake"
    skills = await provider.complete("python fastapi resume", SkillExtractionResult)
    assert any(s.name == "fastapi" for s in skills.skills)
    questions = await provider.complete("python fastapi", QuestionGenerationResult)
    assert len(questions.questions) >= 1
