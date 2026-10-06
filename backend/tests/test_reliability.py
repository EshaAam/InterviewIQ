"""Phase 6 — the error policy, the reaper, retries, and a crash mid-grading.

Transient errors are retried and finally given up on; permanent ones are
recorded where they happen; a task that dies half-way leaves nothing behind;
and a re-delivered task produces exactly one grade per answer.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.core.config import settings
from app.main import app
from app.models import Answer, Evaluation, InterviewSession, LLMCall, Report, Resume
from app.models.session import SessionState
from app.providers import FakeProvider, LLMTransientError, LLMValidationError
from app.schemas.pipeline import (
    QUESTIONS_PER_INTERVIEW,
    AnswerEvaluationResult,
    QuestionGenerationResult,
    SkillExtractionResult,
)
from app.services import ledger, pipeline
from app.workers.dispatch import InlineDispatcher, get_dispatcher

API = settings.API_V1_PREFIX


async def _count(db, model) -> int:
    return await db.scalar(select(func.count()).select_from(model))


async def _start_interview(client: AsyncClient, resume: str = "python and fastapi") -> str:
    rid = (await client.post(f"{API}/resumes", json={"text": resume})).json()["id"]
    sid = (await client.post(f"{API}/sessions", json={"resume_id": rid})).json()["id"]
    await client.post(f"{API}/sessions/{sid}/start")
    return sid


async def _answer_all(client: AsyncClient, sid: str) -> None:
    for i in range(10):
        resp = await client.get(f"{API}/sessions/{sid}/questions/next")
        if resp.status_code == 404:
            return
        await client.post(
            f"{API}/sessions/{sid}/answers",
            json={"question_id": resp.json()["id"], "text": "fundamentals tradeoffs"},
            headers={"Idempotency-Key": f"k{i}"},
        )


# --- transient errors: retried, then given up on ---


async def test_transient_generation_failure_gives_up_with_a_reason(
    auth_client: AsyncClient, provider: FakeProvider, db_session
) -> None:
    provider.register(QuestionGenerationResult, LLMTransientError("503 from provider"))
    rid = (await auth_client.post(f"{API}/resumes", json={"text": "python"})).json()["id"]
    sid = (await auth_client.post(f"{API}/sessions", json={"resume_id": rid})).json()["id"]

    session = (await auth_client.get(f"{API}/sessions/{sid}")).json()
    assert session["state"] == "FAILED"  # not stuck in CREATED
    # Names the stage and tells the person what to do, without leaking the raw
    # provider message (model names, quota ids, sometimes key hints).
    reason = session["failure_reason"]
    assert "Generating your questions" in reason
    assert "Try again" in reason
    assert "503 from provider" not in reason
    # The failed attempt was rolled back, but its bill wasn't.
    statuses = set(await db_session.scalars(select(LLMCall.status)))
    assert "error" in statuses


async def test_transient_parse_failure_marks_resume_failed(
    auth_client: AsyncClient, provider: FakeProvider
) -> None:
    provider.register(SkillExtractionResult, LLMTransientError("rate limited"))
    rid = (await auth_client.post(f"{API}/resumes", json={"text": "python"})).json()["id"]
    body = (await auth_client.get(f"{API}/resumes/{rid}")).json()
    assert body["parse_status"] == "failed"


async def test_transient_grading_failure_fails_session_and_keeps_nothing(
    auth_client: AsyncClient, provider: FakeProvider, db_session
) -> None:
    sid = await _start_interview(auth_client)
    await _answer_all(auth_client, sid)
    provider.register(AnswerEvaluationResult, LLMTransientError("provider down"))
    await auth_client.post(f"{API}/sessions/{sid}/finish")

    session = (await auth_client.get(f"{API}/sessions/{sid}")).json()
    assert session["state"] == "FAILED"  # not stuck in EVALUATING
    reason = session["failure_reason"]
    assert "Grading your answers" in reason
    assert "provider down" not in reason
    assert await _count(db_session, Evaluation) == 0  # the attempt rolled back
    assert await _count(db_session, Report) == 0


# --- permanent errors: recorded where they happen ---


async def test_ungradeable_answer_goes_to_a_human_not_to_failed(
    auth_client: AsyncClient, provider: FakeProvider, db_session
) -> None:
    sid = await _start_interview(auth_client)
    await _answer_all(auth_client, sid)
    provider.register(AnswerEvaluationResult, LLMValidationError("still malformed"))
    await auth_client.post(f"{API}/sessions/{sid}/finish")

    session = (await auth_client.get(f"{API}/sessions/{sid}")).json()
    assert session["state"] == "NEEDS_HUMAN_REVIEW"  # the interview survives
    evaluations = list(await db_session.scalars(select(Evaluation)))
    assert evaluations and all(
        e.needs_review and e.run_count == 0 and e.final_score == e.deterministic_score
        for e in evaluations
    )


# --- chaos: a worker dies mid-build_report ---


class CrashOnSecondGrade(FakeProvider):
    """Grades one answer, then the process "dies" (an exception no layer
    handles — what a killed worker looks like from the transaction's side)."""

    def __init__(self, inner: FakeProvider) -> None:
        super().__init__(canned=inner._canned)
        self.grades = 0

    async def complete(self, prompt, schema, *, temperature=0.0):
        if schema is AnswerEvaluationResult:
            self.grades += 1
            if self.grades == 2:
                raise RuntimeError("worker killed")
        return await super().complete(prompt, schema, temperature=temperature)


class NoReportDispatcher(InlineDispatcher):
    """Leaves the finished session in EVALUATING, as if the task were queued."""

    async def build_report(self, session_id: uuid.UUID) -> None:
        return None


async def test_crash_mid_grading_leaves_nothing_and_redelivery_scores_once(
    client: AsyncClient, auth_client: AsyncClient, provider: FakeProvider, db_session
) -> None:
    app.dependency_overrides[get_dispatcher] = lambda: NoReportDispatcher(
        db_session, provider
    )
    sid = await _start_interview(auth_client)
    await _answer_all(auth_client, sid)
    await auth_client.post(f"{API}/sessions/{sid}/finish")
    session_id = uuid.UUID(sid)
    answers = await _count(db_session, Answer)
    assert answers == QUESTIONS_PER_INTERVIEW

    # Attempt 1 dies after grading one answer. Its transaction (here a
    # savepoint) rolls back; the ledger rows go through the independent writer.
    billed: list[LLMCall] = []

    async def bill(row: LLMCall) -> None:
        billed.append(row)

    with pytest.raises(RuntimeError), ledger.independent_ledger(bill):
        async with db_session.begin_nested():
            await pipeline.build_report(db_session, CrashOnSecondGrade(provider), session_id)

    assert await _count(db_session, Evaluation) == 0  # nothing half-written
    assert await _count(db_session, Report) == 0
    state = await db_session.scalar(
        select(InterviewSession.state).where(InterviewSession.id == session_id)
    )
    assert state == SessionState.EVALUATING
    assert len(billed) >= 1  # ...but the call it paid for is on record

    # Redelivery (acks_late) runs the task again, and a duplicate delivery
    # after that must change nothing.
    await pipeline.build_report(db_session, provider, session_id)
    await pipeline.build_report(db_session, provider, session_id)
    await db_session.flush()

    assert await _count(db_session, Evaluation) == answers  # one grade per answer
    assert await _count(db_session, Report) == 1


# --- the reaper ---


async def test_reaper_claims_only_stale_sessions_once(auth_client: AsyncClient, db_session):
    user_id = uuid.UUID((await auth_client.get(f"{API}/auth/me")).json()["id"])
    resume = Resume(user_id=user_id, file_uri="inline://text", mime="text/plain")
    db_session.add(resume)
    await db_session.flush()

    now = datetime.now(UTC)
    old, fresh = now - timedelta(hours=2), now - timedelta(minutes=1)

    def make(state: SessionState, updated: datetime) -> InterviewSession:
        session = InterviewSession(user_id=user_id, resume_id=resume.id, state=state)
        session.updated_at = updated
        db_session.add(session)
        return session

    stuck_created = make(SessionState.CREATED, old)
    stuck_grading = make(SessionState.EVALUATING, old)
    make(SessionState.CREATED, fresh)  # just created: leave it alone
    make(SessionState.IN_PROGRESS, old)  # candidate is answering: not ours
    await db_session.flush()

    to_generate, to_report = await pipeline.claim_stale_sessions(db_session, now=now)
    assert to_generate == [stuck_created.id]
    assert to_report == [stuck_grading.id]

    # Claimed: the next sweep leaves them alone for another window.
    assert await pipeline.claim_stale_sessions(db_session, now=now) == ([], [])


# --- the Celery retry wrapper ---


def test_task_retries_with_backoff_then_gives_up(monkeypatch) -> None:
    from celery.exceptions import Retry

    from app.workers import tasks

    monkeypatch.setattr(tasks, "_run", lambda op: asyncio.run(op(None, None)))

    async def flaky(db, p):
        raise LLMTransientError("429")

    given_up: list[str] = []

    async def give_up(db, p, exc):
        given_up.append(str(exc))

    countdowns: list[int] = []

    def retry(exc, countdown):
        countdowns.append(countdown)
        return Retry()

    for attempt in range(settings.TASK_MAX_RETRIES):
        task = SimpleNamespace(request=SimpleNamespace(retries=attempt), retry=retry)
        with pytest.raises(Retry):
            tasks._with_retries(task, flaky, give_up)
    assert countdowns == [
        settings.TASK_RETRY_BASE_SECONDS * 2**n for n in range(settings.TASK_MAX_RETRIES)
    ]
    assert given_up == []

    last = SimpleNamespace(
        request=SimpleNamespace(retries=settings.TASK_MAX_RETRIES), retry=retry
    )
    tasks._with_retries(last, flaky, give_up)  # no raise: it gave up instead
    assert given_up == ["429"]


def test_db_session_commits_before_the_response_is_sent() -> None:
    """Regression guard for the read-after-write race the load test found.

    The in-process test client waits for the whole ASGI call, so it can't
    reproduce the race itself — this pins the setting that prevents it.
    """
    from typing import get_args

    from app.api.deps import DbSession

    _, depends = get_args(DbSession)
    assert depends.scope == "function"
