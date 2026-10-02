"""Celery task wrappers around the async pipeline.

Each task is a thin sync shell: it opens a fresh async DB session, runs the
corresponding `app.services.pipeline` coroutine, and commits. Tasks carry only
IDs (never ORM objects) and inherit the pipeline's idempotency, so `acks_late`
re-delivery after a worker crash is safe.

Retries: a transient provider error (rate limit, outage, circuit open) rolls
the attempt back and retries the task with exponential backoff. When the
retries run out, the task records the failure (`give_up_*`) instead of leaving
the résumé or session waiting forever.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable

from celery import Task
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.models import LLMCall
from app.providers import LLMProvider, get_provider
from app.services import ledger, pipeline
from app.workers.celery_app import celery_app


def _run[R](op: Callable[[AsyncSession, LLMProvider], Awaitable[R]]) -> R:
    """Run one pipeline coroutine in its own session + event loop, then commit.

    Each task builds a fresh NullPool engine *inside* the new event loop that
    `asyncio.run` creates. A pooled engine would bind its connections to the
    first task's loop and then fail with "attached to a different loop" on the
    next task; NullPool + per-task disposal sidesteps that entirely.

    Ledger rows bypass the task's transaction: each is committed on its own,
    so a rolled-back attempt still leaves a record of the calls it paid for.
    """

    async def _inner() -> R:
        engine = create_async_engine(settings.DATABASE_URL_ASYNC, poolclass=NullPool)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        provider = get_provider()

        async def write_ledger_row(row: LLMCall) -> None:
            async with factory() as ledger_session:
                ledger_session.add(row)
                await ledger_session.commit()

        try:
            with ledger.independent_ledger(write_ledger_row):
                async with factory() as session:
                    try:
                        result = await op(session, provider)
                        await session.commit()
                        return result
                    except Exception:
                        await session.rollback()
                        raise
        finally:
            await engine.dispose()

    return asyncio.run(_inner())


def _with_retries(
    task: Task,
    op: Callable[[AsyncSession, LLMProvider], Awaitable[object]],
    give_up: Callable[[AsyncSession, LLMProvider, Exception], Awaitable[None]],
) -> None:
    try:
        _run(op)
    except pipeline.RETRYABLE as exc:
        error = exc  # `exc` is unbound when the except block ends; the lambda needs a name
        attempt = task.request.retries
        if attempt >= settings.TASK_MAX_RETRIES:
            _run(lambda db, p: give_up(db, p, error))
            return
        # 30 s, 60 s, 120 s, 240 s — long enough for a rate limit or a short
        # outage to clear, short enough that a candidate isn't waiting an hour.
        raise task.retry(
            exc=exc, countdown=settings.TASK_RETRY_BASE_SECONDS * 2**attempt
        ) from exc


def _give_up_message(stage: str, exc: Exception) -> str:
    return (
        f"{stage} did not complete after {settings.TASK_MAX_RETRIES + 1} attempts "
        f"(the AI provider kept failing: {exc})"
    )


@celery_app.task(name="pipeline.parse_resume", bind=True, max_retries=None)
def parse_resume_task(self: Task, resume_id: str) -> None:
    rid = uuid.UUID(resume_id)
    _with_retries(
        self,
        lambda db, p: pipeline.parse_resume(db, p, rid),
        lambda db, p, exc: pipeline.give_up_resume(db, rid),
    )


@celery_app.task(name="pipeline.generate_questions", bind=True, max_retries=None)
def generate_questions_task(self: Task, session_id: str) -> None:
    sid = uuid.UUID(session_id)
    _with_retries(
        self,
        lambda db, p: pipeline.generate_questions(db, p, sid),
        lambda db, p, exc: pipeline.give_up_session(
            db, sid, _give_up_message("Question generation", exc)
        ),
    )


@celery_app.task(name="pipeline.evaluate_answer", bind=True, max_retries=None)
def evaluate_answer_task(self: Task, answer_id: str) -> None:
    aid = uuid.UUID(answer_id)

    async def _nothing(db: AsyncSession, p: LLMProvider, exc: Exception) -> None:
        return None  # build_report grades it again; nothing to mark here

    _with_retries(self, lambda db, p: pipeline.evaluate_answer(db, p, aid), _nothing)


@celery_app.task(name="pipeline.build_report", bind=True, max_retries=None)
def build_report_task(self: Task, session_id: str) -> None:
    sid = uuid.UUID(session_id)
    _with_retries(
        self,
        lambda db, p: pipeline.build_report(db, p, sid),
        lambda db, p, exc: pipeline.give_up_session(
            db, sid, _give_up_message("Grading", exc)
        ),
    )


@celery_app.task(name="pipeline.reap_stale_sessions")
def reap_stale_sessions_task() -> dict[str, int]:
    """Beat-scheduled: re-dispatch sessions whose job looks lost.

    Covers what retries can't: the message never reached a worker (the API
    committed but the broker publish failed), or a task was dropped. Dispatch
    happens after `_run` has committed the claim, for the same reason routes
    commit before they dispatch.
    """
    to_generate, to_report = _run(
        lambda db, p: pipeline.claim_stale_sessions(db)
    )
    for sid in to_generate:
        generate_questions_task.delay(str(sid))
    for sid in to_report:
        build_report_task.delay(str(sid))
    return {"generate_questions": len(to_generate), "build_report": len(to_report)}
