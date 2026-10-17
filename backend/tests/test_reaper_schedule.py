"""On the single-container deploy the API, not Celery beat, triggers the reaper.

Pinned because the alternative it replaces was an outage: an embedded beat is a
forked copy of the whole worker, and on a 512 MB instance that copy is what
got the container OOM-killed mid-grading, stranding sessions in EVALUATING.
"""

from __future__ import annotations

import asyncio

from app import main
from app.core.config import settings
from app.workers import tasks


def _fast_schedule(monkeypatch, sent: list[int], fail_first: bool = False) -> None:
    monkeypatch.setattr(settings, "REAPER_FIRST_SWEEP_SECONDS", 0.01)
    monkeypatch.setattr(settings, "REAPER_INTERVAL_SECONDS", 0.01)

    def delay() -> None:
        if fail_first and not sent:
            sent.append(0)
            raise ConnectionError("redis is restarting")
        sent.append(1)

    monkeypatch.setattr(tasks.reap_stale_sessions_task, "delay", delay)


async def test_the_api_enqueues_the_sweep_on_a_timer(monkeypatch):
    sent: list[int] = []
    monkeypatch.setattr(settings, "REAPER_IN_API", True)
    _fast_schedule(monkeypatch, sent)

    async with main.lifespan(main.app):
        await asyncio.sleep(0.15)

    assert sent.count(1) >= 2


async def test_off_by_default_so_compose_keeps_its_beat_service(monkeypatch):
    sent: list[int] = []
    _fast_schedule(monkeypatch, sent)

    async with main.lifespan(main.app):
        await asyncio.sleep(0.05)

    assert sent == []


async def test_a_failed_publish_does_not_end_the_schedule(monkeypatch):
    sent: list[int] = []
    monkeypatch.setattr(settings, "REAPER_IN_API", True)
    _fast_schedule(monkeypatch, sent, fail_first=True)

    async with main.lifespan(main.app):
        await asyncio.sleep(0.15)

    assert sent[0] == 0  # the failure happened
    assert 1 in sent  # and later sweeps still went out
