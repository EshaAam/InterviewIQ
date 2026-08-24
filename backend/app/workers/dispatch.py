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
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.providers import LLMProvider
from app.services import pipeline
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
    """Runs the pipeline in-process against a supplied session (tests / no broker)."""

    def __init__(self, db: AsyncSession, provider: LLMProvider) -> None:
        self.db = db
        self.provider = provider

    async def parse_resume(self, resume_id: uuid.UUID) -> None:
        await pipeline.parse_resume(self.db, self.provider, resume_id)

    async def generate_questions(self, session_id: uuid.UUID) -> None:
        await pipeline.generate_questions(self.db, self.provider, session_id)

    async def evaluate_answer(self, answer_id: uuid.UUID) -> None:
        await pipeline.evaluate_answer(self.db, self.provider, answer_id)

    async def build_report(self, session_id: uuid.UUID) -> None:
        await pipeline.build_report(self.db, self.provider, session_id)


def get_dispatcher() -> PipelineDispatcher:
    return CeleryDispatcher()
