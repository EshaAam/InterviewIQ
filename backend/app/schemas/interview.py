"""Wire schemas for the interview flow (resumes, sessions, questions, answers, report)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.resume import ParseStatus
from app.models.session import SessionState

# --- Resumes ---

class ResumeCreate(BaseModel):
    # Phase 2 accepts raw text; file upload arrives in Phase 5.
    text: str = Field(min_length=1)
    mime: str = "text/plain"


class SkillRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    name: str
    confidence: float
    evidence_span: str


class ResumeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    parse_status: ParseStatus
    skills: list[SkillRead] = []


# --- Sessions ---

class SessionCreate(BaseModel):
    resume_id: uuid.UUID


class SessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    state: SessionState
    expires_at: datetime | None = None
    failure_reason: str | None = None
    answered: int = 0
    total_questions: int = 0


# --- Questions ---

class QuestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    ordinal: int
    text: str
    difficulty: str
    topic: str


# --- Answers ---

class AnswerCreate(BaseModel):
    question_id: uuid.UUID
    text: str = Field(min_length=1)
    time_taken_ms: int | None = None
    paste_events: int = 0
    keystroke_count: int | None = None


class AnswerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    question_id: uuid.UUID
    submitted_at: datetime


# --- Report ---

class ReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    overall: float
    per_topic: dict
    strengths: list[str]
    gaps: list[str]


# --- Recruiter / human-review queue ---

class RecruiterSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    user_id: uuid.UUID
    state: SessionState
    created_at: datetime


class EvaluationReviewRead(BaseModel):
    id: uuid.UUID
    answer_id: uuid.UUID
    topic: str
    question_text: str
    answer_text: str
    final_score: float
    deterministic_score: float
    confidence: float
    needs_review: bool
    run_count: int


class OverrideRequest(BaseModel):
    final_score: float = Field(ge=0.0, le=1.0)
    note: str | None = None


class OverrideResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    final_score: float
    needs_review: bool
    overridden_by_id: uuid.UUID | None
