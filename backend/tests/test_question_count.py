"""Every interview gets at least five questions."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.pipeline import (
    MAX_QUESTIONS,
    QUESTIONS_PER_INTERVIEW,
    GeneratedQuestion,
    QuestionGenerationResult,
)


def _questions(n: int) -> list[GeneratedQuestion]:
    return [
        GeneratedQuestion(text=f"Q{i}", topic="python", expected_concepts=["c"])
        for i in range(n)
    ]


def test_fewer_than_five_is_rejected():
    # Rejected at validation, so the repair wrapper gets a chance to re-ask.
    with pytest.raises(ValidationError):
        QuestionGenerationResult(questions=_questions(QUESTIONS_PER_INTERVIEW - 1))


def test_five_is_accepted():
    result = QuestionGenerationResult(questions=_questions(QUESTIONS_PER_INTERVIEW))
    assert len(result.questions) == 5


def test_there_is_a_ceiling():
    # Each answer is graded with its own LLM call, so the count has to stay bounded.
    with pytest.raises(ValidationError):
        QuestionGenerationResult(questions=_questions(MAX_QUESTIONS + 1))


async def test_a_full_interview_gets_five_questions(auth_client):
    from app.core.config import settings

    api = settings.API_V1_PREFIX
    rid = (await auth_client.post(f"{api}/resumes", json={"text": "python"})).json()["id"]
    sid = (await auth_client.post(f"{api}/sessions", json={"resume_id": rid})).json()["id"]
    session = (await auth_client.get(f"{api}/sessions/{sid}")).json()
    assert session["total_questions"] == QUESTIONS_PER_INTERVIEW
