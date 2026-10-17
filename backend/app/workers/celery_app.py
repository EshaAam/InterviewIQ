"""Celery application.

Redis is the broker and result backend (design doc §8 — a second broker we
can't justify is worse than none). Tasks live in `app.workers.tasks`.
"""

from __future__ import annotations

import logging

from celery import Celery
from celery.signals import worker_init, worker_process_init

from app.core.config import settings

logger = logging.getLogger(__name__)

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
    # Run by the `beat` service (docker-compose.yml). Only one beat process
    # may run, or every sweep is dispatched twice. The single-container Render
    # image runs no beat; its API enqueues the sweep instead (REAPER_IN_API).
    beat_schedule={
        "reap-stale-sessions": {
            "task": "pipeline.reap_stale_sessions",
            "schedule": 300.0,  # every 5 minutes
        },
    },
)


@worker_init.connect
def _refuse_to_start_broken(**_: object) -> None:
    """Fail at boot rather than at the first job.

    `SystemExit` rather than an ordinary exception: Celery catches and logs
    `Exception`s raised by signal receivers and carries on, which would put us
    straight back to a worker that accepts jobs it cannot finish.
    """
    from app.workers.preflight import remedy, runtime_problems

    problems = runtime_problems()
    if problems:
        for problem in problems:
            logger.critical("worker preflight failed: %s", problem)
        logger.critical(remedy())
        raise SystemExit(1)


@worker_process_init.connect
def _own_model_per_child(**_: object) -> None:
    """A forked pool child builds its own embedding model on first use.

    An onnxruntime session should not be shared across a fork, so the copy the
    parent loaded for the preflight check is dropped here. This signal only
    fires in forked children: under the solo pool (the single-container Render
    deploy) the preflight's model is the one the jobs use, loaded exactly once.
    """
    from app.embedders import get_embedder

    get_embedder.cache_clear()
