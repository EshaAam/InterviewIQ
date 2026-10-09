"""Default canned responses for `FakeProvider`.

Deterministic functions of the prompt so the fake pipeline produces stable,
believable data end-to-end without any network call. Real semantics arrive
with the Gemini provider in Phase 3; the shapes here are exactly what that
provider must also return.
"""

from __future__ import annotations

import re

from app.providers.fake import CannedMap
from app.schemas.pipeline import (
    QUESTIONS_PER_INTERVIEW,
    AnswerEvaluationResult,
    ConceptCoverage,
    ExtractedSkillOut,
    GeneratedQuestion,
    QuestionGenerationResult,
    RubricScores,
    SkillExtractionResult,
)
from app.services.prompt_safety import unfence

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
    found = [s for s in _KNOWN_SKILLS if s in text]
    # Pad with the rest of the known list so there are always enough topics
    # for the schema minimum, keeping the order (and so the output) stable.
    topics = (found + [s for s in _KNOWN_SKILLS if s not in found])[
        :QUESTIONS_PER_INTERVIEW
    ]
    # When the prompt carries a sources block, cite from it — a real model would,
    # and without this the fake could never exercise the grounded path at all.
    # Deliberately *valid* labels only; a test that wants the invented-citation
    # dead-letter registers its own canned response for that.
    labels = _source_labels(prompt)
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
            # One label per question, rotating, so different questions carry
            # different citations the way grounded output actually looks.
            source_chunk_ids=[labels[index % len(labels)]] if labels else [],
        )
        for index, topic in enumerate(topics)
    ]
    return QuestionGenerationResult(questions=questions)


def _source_labels(prompt: str) -> list[str]:
    """Labels the grounded prompt offered, in order, de-duplicated."""
    seen: dict[str, None] = {}
    for label in re.findall(r"^\[(S\d+)\]", prompt, flags=re.MULTILINE):
        seen.setdefault(label, None)
    return list(seen)


def prompt_concepts(prompt: str) -> list[str]:
    """The expected concepts a grading prompt lists, in order.

    Public so a test can build a grader that answers about the real concepts —
    one that names concepts the prompt never asked about is now ignored.
    """
    _, _, block = prompt.partition("Expected concepts:\n")
    concepts: list[str] = []
    for line in block.splitlines():
        if not line.startswith("- "):
            break
        concepts.append(line[2:].strip())
    return concepts


def _fake_evaluation(prompt: str) -> AnswerEvaluationResult:
    # Deterministic, plausible evaluation based on word overlap between each
    # expected concept and the answer text — the same signal the (fake)
    # embedding pass uses, so the two passes naturally agree for real answers.
    # The answer is read from its fence, and the concepts from the block under
    # "Expected concepts:" only — so neither a bulleted answer nor a bulleted
    # source passage can pass itself off as an expected concept.
    fenced = unfence(prompt, "answer")
    answer_text = fenced if fenced is not None else prompt.rpartition("Answer:")[2]
    answer_tokens = set(re.findall(r"[a-z0-9]+", answer_text.lower()))
    concepts = prompt_concepts(prompt) or ["general"]

    coverage = []
    for concept in concepts:
        tokens = re.findall(r"[a-z0-9]+", concept.lower())
        hit = sum(1 for t in tokens if t in answer_tokens)
        ratio = hit / len(tokens) if tokens else 0.0
        coverage.append(ConceptCoverage(concept=concept, covered=round(ratio, 3)))

    mean = sum(c.covered for c in coverage) / len(coverage)
    return AnswerEvaluationResult(
        concept_coverage=coverage,
        llm_scores=RubricScores(
            correctness=round(mean, 3),
            depth=round(mean * 0.9, 3),
            clarity=0.8,
        ),
        confidence=0.75,
        evidence="fake-evaluation",
    )


def default_canned_responses() -> CannedMap:
    return {
        SkillExtractionResult: _fake_skills,
        QuestionGenerationResult: _fake_questions,
        AnswerEvaluationResult: _fake_evaluation,
    }
