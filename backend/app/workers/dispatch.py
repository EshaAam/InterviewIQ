"""The dispatch seam between the API and the pipeline.

Routes depend on a `PipelineDispatcher`, never on Celery directly. In
production `get_dispatcher` returns `CeleryDispatcher`, which enqueues tasks and
returns immediately (so no endpoint blocks on the pipeline — design doc §7). In
tests the dependency is overridden with `InlineDispatcher`, which runs the
pipeline synchronously against the request's own session — giving a true,
offline, end-to-end flow with no broker.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.embedders import Embedder, get_embedder
from app.models import LLMCall
from app.providers import LLMProvider
from app.services import ledger, pipeline
from app.workers.tasks import (
    build_report_task,
    evaluate_answer_task,
    generate_questions_task,
    parse_resume_task,
)


class PipelineDispatcher(Protocol):
    async def parse_resume(self, resume_id: uuid.UUID) -> None: ...
    async def generate_questions(self, session_id: uuid.UUID) -> None: ...
    async def evaluate_answer(self, answer_id: uuid.UUID) -> None: ...
    async def build_report(self, session_id: uuid.UUID) -> None: ...


class CeleryDispatcher:
    """Fire-and-forget: hand work to the broker, return control to the request."""

    async def parse_resume(self, resume_id: uuid.UUID) -> None:
        parse_resume_task.delay(str(resume_id))

    async def generate_questions(self, session_id: uuid.UUID) -> None:
        generate_questions_task.delay(str(session_id))

    async def evaluate_answer(self, answer_id: uuid.UUID) -> None:
        evaluate_answer_task.delay(str(answer_id))

    async def build_report(self, session_id: uuid.UUID) -> None:
        build_report_task.delay(str(session_id))


class InlineDispatcher:
    """Runs the pipeline in-process against a supplied session (tests / no broker).

    Behaves like a worker whose retries have all run out: each attempt runs in
    a savepoint (a failed attempt is rolled back, as a task's transaction
    would be), ledger rows are kept even when it is (as the worker's
    independent ledger does), and a transient failure goes straight to the
    give-up path instead of being retried later.
    """

    def __init__(
        self,
        db: AsyncSession,
        provider: LLMProvider,
        embedder: Embedder | None = None,
    ) -> None:
        self.db = db
        self.provider = provider
        # Injectable so a grounded-generation test can supply an embedder
        # whose width matches the knowledge base it ingested.
        self.embedder = embedder or get_embedder()

    async def _attempt(
        self,
        op: Callable[[], Awaitable[object]],
        give_up: Callable[[Exception], Awaitable[None]],
    ) -> None:
        kept: list[LLMCall] = []

        async def keep(row: LLMCall) -> None:
            kept.append(row)

        try:
            with ledger.independent_ledger(keep):
                async with self.db.begin_nested():
                    await op()
        except pipeline.RETRYABLE as exc:
            await give_up(exc)
        finally:
            self.db.add_all(kept)  # outside the savepoint: survives its rollback

    async def parse_resume(self, resume_id: uuid.UUID) -> None:
        await self._attempt(
            lambda: pipeline.parse_resume(self.db, self.provider, resume_id),
            lambda exc: pipeline.give_up_resume(self.db, resume_id, exc),
        )

    async def generate_questions(self, session_id: uuid.UUID) -> None:
        await self._attempt(
            lambda: pipeline.generate_questions(
                self.db, self.provider, session_id, embedder=self.embedder
            ),
            lambda exc: pipeline.give_up_session(
                self.db,
                session_id,
                pipeline.describe_failure("Generating your questions", exc),
            ),
        )

    async def evaluate_answer(self, answer_id: uuid.UUID) -> None:
        async def _nothing(exc: Exception) -> None:
            return None

        await self._attempt(
            lambda: pipeline.evaluate_answer(
                self.db, self.provider, answer_id, embedder=self.embedder
            ),
            _nothing,
        )

    async def build_report(self, session_id: uuid.UUID) -> None:
        await self._attempt(
            lambda: pipeline.build_report(self.db, self.provider, session_id),
            lambda exc: pipeline.give_up_session(
                self.db,
                session_id,
                pipeline.describe_failure("Grading your answers", exc),
            ),
        )


def get_dispatcher() -> PipelineDispatcher:
    return CeleryDispatcher()
