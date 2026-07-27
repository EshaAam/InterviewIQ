"""Structured LLM output schemas — the JSON contracts each pipeline stage
requires the model to return.

Grading is framed as "which of these expected concepts appeared?" rather than
"score 0-100", which is what makes it reproducible (design doc §4). These
schemas are the wire format for that; the ORM `Evaluation`/`Question` rows are
the storage format.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# --- Stage 1: resume parsing / skill extraction ---

class ExtractedSkillOut(BaseModel):
    name: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_span: str = ""


class SkillExtractionResult(BaseModel):
    skills: list[ExtractedSkillOut]


# --- Stage 2: question generation ---

class GeneratedQuestion(BaseModel):
    text: str
    difficulty: str = "medium"
    topic: str
    expected_concepts: list[str] = Field(min_length=1)
    reference_answer: str = ""


class QuestionGenerationResult(BaseModel):
    questions: list[GeneratedQuestion] = Field(min_length=1)


# --- Stage 3: answer evaluation ---

class AnswerEvaluationResult(BaseModel):
    # Which expected concepts the answer covered, 0..1 each.
    concept_coverage: dict[str, float]
    # Rubric sub-scores, 0..1: correctness, depth, clarity.
    llm_scores: dict[str, float]
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: str = ""
