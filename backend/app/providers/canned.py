"""Default canned responses for `FakeProvider`.

Deterministic functions of the prompt so the fake pipeline produces stable,
believable data end-to-end without any network call. Real semantics arrive
with the Gemini provider in Phase 3; the shapes here are exactly what that
provider must also return.
"""

from __future__ import annotations

from app.providers.fake import CannedMap
from app.schemas.pipeline import (
    AnswerEvaluationResult,
    ExtractedSkillOut,
    GeneratedQuestion,
    QuestionGenerationResult,
    SkillExtractionResult,
)

# A small skill vocabulary the fake parser "detects" when present in resume text.
_KNOWN_SKILLS = [
    "python",
    "fastapi",
    "postgresql",
    "redis",
    "docker",
    "celery",
    "asyncio",
    "sql",
]


def _fake_skills(prompt: str) -> SkillExtractionResult:
    text = prompt.lower()
    found = [s for s in _KNOWN_SKILLS if s in text]
    if not found:
        found = ["python", "sql"]  # never return an empty skill set
    skills = [
        ExtractedSkillOut(name=s, confidence=0.9, evidence_span=s) for s in found
    ]
    return SkillExtractionResult(skills=skills)


def _fake_questions(prompt: str) -> QuestionGenerationResult:
    text = prompt.lower()
    topics = [s for s in _KNOWN_SKILLS if s in text][:3] or ["python", "sql"]
    questions = [
        GeneratedQuestion(
            text=f"Explain how you would use {topic} in a production system.",
            difficulty="medium",
            topic=topic,
            expected_concepts=[
                f"{topic} fundamentals",
                f"{topic} tradeoffs",
                f"{topic} in production",
            ],
            reference_answer=f"A strong answer covers {topic} fundamentals, its "
            f"tradeoffs, and concrete production usage.",
        )
        for topic in topics
    ]
    return QuestionGenerationResult(questions=questions)


def _fake_evaluation(prompt: str) -> AnswerEvaluationResult:
    # A deterministic, plausible evaluation. The prompt embeds the expected
    # concepts as lines "- <concept>"; mark a concept covered if it appears in
    # the answer text of the same prompt.
    text = prompt.lower()
    concepts = [
        line.strip("- ").strip()
        for line in prompt.splitlines()
        if line.strip().startswith("-")
    ]
    coverage = {
        c: (1.0 if c.lower() in text else 0.4) for c in concepts
    } or {"general": 0.6}
    return AnswerEvaluationResult(
        concept_coverage=coverage,
        llm_scores={"correctness": 0.7, "depth": 0.6, "clarity": 0.8},
        confidence=0.75,
        evidence="fake-evaluation",
    )


def default_canned_responses() -> CannedMap:
    return {
        SkillExtractionResult: _fake_skills,
        QuestionGenerationResult: _fake_questions,
        AnswerEvaluationResult: _fake_evaluation,
    }
