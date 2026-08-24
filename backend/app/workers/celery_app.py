"""Celery application.

Redis is the broker and result backend (design doc §8 — a second broker we
can't justify is worse than none). Tasks live in `app.workers.tasks`.
"""

from __future__ import annotations

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "interviewiq",
    broker=settings.celery_broker,
    backend=settings.celery_backend,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_acks_late=True,  # a killed worker re-delivers the task (chaos-safe)
    task_reject_on_worker_lost=True,
    task_track_started=True,
    result_expires=3600,
    worker_prefetch_multiplier=1,
)
