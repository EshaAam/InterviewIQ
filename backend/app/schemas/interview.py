"""Wire schemas for the interview flow (resumes, sessions, questions, answers, report)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

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
    # Populated only when parse_status is `failed`. The UI shows this instead of
    # a generic timeout, so the person knows whether to retry or to wait.
    failure_reason: str | None = None
    skills: list[SkillRead] = []


# --- Sessions ---

class SessionCreate(BaseModel):
    resume_id: uuid.UUID
    # Optional. When present, question generation targets the requirements the
    # resume does not evidence rather than the skills it does — an interview
    # that asks about what is already on the page is largely wasted.
    job_description: str | None = Field(default=None, max_length=20_000)


class SessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    state: SessionState
    expires_at: datetime | None = None
    failure_reason: str | None = None
    answered: int = 0
    total_questions: int = 0
    # Distinct question topics, in question order — what the interview covers.
    topics: list[str] = []
    created_at: datetime | None = None
    # Last state change; for a finished session, roughly when it finished.
    updated_at: datetime | None = None


class SessionSummary(SessionRead):
    """One row of the candidate's own interview list."""

    created_at: datetime
    # The report's overall score, once one exists.
    overall: float | None = None


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
    # True once a recruiter has overridden any score in this session — the
    # numbers above already include that human decision.
    human_reviewed: bool = False
    # Passages behind the weakest topics, so a report doubles as a study plan.
    # Drawn from citations already on the questions — never retrieved afresh,
    # so a report shows what the interview actually used.
    study_links: list[StudyLink] = Field(default_factory=list)


# --- Recruiter / human-review queue ---

class RecruiterSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    user_id: uuid.UUID
    candidate_email: str
    state: SessionState
    created_at: datetime
    # Advisory: at least one answer tripped an integrity signal.
    integrity_flag: bool = False


class EvaluationReviewRead(BaseModel):
    id: uuid.UUID
    answer_id: uuid.UUID
    session_id: uuid.UUID
    candidate_email: str
    topic: str
    question_text: str
    answer_text: str
    final_score: float
    deterministic_score: float
    confidence: float
    needs_review: bool
    run_count: int
    # The reviewer judges against the same passages the grader was given.
    # Without them the screen asks a human to second-guess a decision while
    # withholding the evidence it was made from.
    grounded: bool = False
    sources: list[CitedSourceRead] = Field(default_factory=list)


class EvaluationReviewPage(BaseModel):
    """A page of the queue plus the size of the whole queue, so the UI can say
    "37 waiting" while showing 20."""

    items: list[EvaluationReviewRead]
    total: int


class EvaluationDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    deterministic_score: float
    final_score: float
    confidence: float
    needs_review: bool
    run_count: int
    # The LLM's rubric (correctness / depth / clarity), 0..1 each.
    llm_scores: dict
    overridden_by_id: uuid.UUID | None
    override_note: str | None


class IntegritySignalRead(BaseModel):
    """An advisory hint — never a verdict, never applied to a score."""

    model_config = ConfigDict(from_attributes=True)
    code: Literal["mostly_pasted", "too_fast"]
    detail: str


class AnswerDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    text: str
    submitted_at: datetime
    time_taken_ms: int | None
    paste_events: int
    keystroke_count: int | None
    evaluation: EvaluationDetail | None = None
    integrity: list[IntegritySignalRead] = []


class CitedSourceRead(BaseModel):
    """A passage a question was grounded in.

    `text` is included so a reviewer can judge against the same material the
    grader saw without a second request — the point of showing a citation is
    that it can be checked, and a link nobody follows is not a check.
    """

    model_config = ConfigDict(from_attributes=True)
    chunk_id: uuid.UUID
    topic: str
    heading_path: str
    text: str
    document_title: str
    url: str
    #: Non-empty only where the source licence requires visible attribution.
    license: str


class StudyLink(BaseModel):
    """A passage behind a concept the candidate missed."""

    topic: str
    heading_path: str
    document_title: str
    url: str


class QuestionDetail(BaseModel):
    id: uuid.UUID
    ordinal: int
    topic: str
    difficulty: str
    text: str
    expected_concepts: list[str]
    # Whether the answer key came from cited passages or from model memory.
    # Shown explicitly rather than inferred from `sources` being empty, so an
    # ungrounded question is labelled instead of just looking unremarkable.
    grounded: bool = False
    sources: list[CitedSourceRead] = Field(default_factory=list)
    # A list, not a single answer: the database allows more than one per
    # question, and a review screen should show what is stored, not hide it.
    answers: list[AnswerDetail]


class RecruiterSessionDetail(BaseModel):
    """Everything a reviewer needs about one interview, in one response."""

    id: uuid.UUID
    user_id: uuid.UUID
    candidate_email: str
    state: SessionState
    created_at: datetime
    expires_at: datetime | None
    failure_reason: str | None
    job_description: str | None = None
    # Requirements the resume did not evidence, as computed at generation time.
    # Stored rather than recomputed so this shows what the questions actually
    # targeted, not what they would target against today's thresholds.
    jd_gaps: list[str] = Field(default_factory=list)
    questions: list[QuestionDetail]
    report: ReportRead | None
    integrity_flag: bool = False


class OverrideRequest(BaseModel):
    final_score: float = Field(ge=0.0, le=1.0)
    note: str | None = None


class OverrideResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    final_score: float
    needs_review: bool
    overridden_by_id: uuid.UUID | None
    # Where the session stands after the report was rebuilt — COMPLETED once
    # the last flagged answer in it has been cleared.
    session_state: SessionState | None = None


# --- Recruiter / cost ledger ---

class LLMCallRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    session_id: uuid.UUID | None
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_estimate: float
    latency_ms: int
    status: str
    created_at: datetime


class CostSummary(BaseModel):
    """Today's spend, read off the same ledger the budget guard enforces against."""

    tokens_today: int
    spend_today: float
    calls_today: int
    failed_today: int
    daily_token_budget: int
    recent: list[LLMCallRead]
