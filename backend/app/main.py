"""FastAPI application factory."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings

logger = logging.getLogger(__name__)


async def _schedule_reaper() -> None:
    """Enqueue the stale-session sweep on a timer, in place of Celery beat.

    Only enqueues: the sweep itself runs on the worker, exactly as when beat
    sends it. A failed publish (Redis restarting) is logged and retried at the
    next tick rather than ending the loop.
    """
    from app.workers.tasks import reap_stale_sessions_task

    delay = settings.REAPER_FIRST_SWEEP_SECONDS
    while True:
        await asyncio.sleep(delay)
        delay = settings.REAPER_INTERVAL_SECONDS
        try:
            await asyncio.to_thread(reap_stale_sessions_task.delay)
        except Exception:
            logger.exception("could not enqueue the stale-session sweep")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    reaper = asyncio.create_task(_schedule_reaper()) if settings.REAPER_IN_API else None
    try:
        yield
    finally:
        if reaper is not None:
            reaper.cancel()
            with suppress(asyncio.CancelledError):
                await reaper


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version="0.1.0",
        docs_url="/docs",
        openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix=settings.API_V1_PREFIX)
    return app


app = create_app()
