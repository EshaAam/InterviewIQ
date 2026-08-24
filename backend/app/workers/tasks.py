"""Celery task wrappers around the async pipeline.

Each task is a thin sync shell: it opens a fresh async DB session, runs the
corresponding `app.services.pipeline` coroutine, and commits. Tasks carry only
IDs (never ORM objects) and inherit the pipeline's idempotency, so `acks_late`
re-delivery after a worker crash is safe.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.providers import LLMProvider, get_provider
from app.services import pipeline
from app.workers.celery_app import celery_app


def _run[R](op: Callable[[AsyncSession, LLMProvider], Awaitable[R]]) -> None:
    """Run one pipeline coroutine in its own session + event loop, then commit.

    Each task builds a fresh NullPool engine *inside* the new event loop that
    `asyncio.run` creates. A pooled engine would bind its connections to the
    first task's loop and then fail with "attached to a different loop" on the
    next task; NullPool + per-task disposal sidesteps that entirely.
    """

    async def _inner() -> None:
        engine = create_async_engine(settings.DATABASE_URL_ASYNC, poolclass=NullPool)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        provider = get_provider()
        try:
            async with factory() as session:
                try:
                    await op(session, provider)
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise
        finally:
            await engine.dispose()

    asyncio.run(_inner())


@celery_app.task(name="pipeline.parse_resume", bind=True, max_retries=2)
def parse_resume_task(self, resume_id: str) -> None:
    _run(lambda db, p: pipeline.parse_resume(db, p, uuid.UUID(resume_id)))


@celery_app.task(name="pipeline.generate_questions", bind=True, max_retries=2)
def generate_questions_task(self, session_id: str) -> None:
    _run(lambda db, p: pipeline.generate_questions(db, p, uuid.UUID(session_id)))


@celery_app.task(name="pipeline.evaluate_answer", bind=True, max_retries=2)
def evaluate_answer_task(self, answer_id: str) -> None:
    _run(lambda db, p: pipeline.evaluate_answer(db, p, uuid.UUID(answer_id)))


@celery_app.task(name="pipeline.build_report", bind=True, max_retries=2)
def build_report_task(self, session_id: str) -> None:
    _run(lambda db, p: pipeline.build_report(db, p, uuid.UUID(session_id)))
