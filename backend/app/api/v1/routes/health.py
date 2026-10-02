"""Health endpoints.

`/health` is a liveness probe — is the process up?
`/health/ready` is a readiness probe — can it actually serve traffic
(Postgres and Redis reachable)? Orchestrators treat these differently:
a failing liveness check restarts the container, a failing readiness
check only pulls it out of the load balancer.

Readiness answers with the HTTP status, not just the body: an orchestrator
reads 200 vs 503 and never looks inside the JSON.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy import text

from app.core.config import settings
from app.db.session import engine

router = APIRouter(tags=["health"])

# A probe that hangs is worse than one that fails: it blocks the orchestrator's
# check. Each dependency gets this long to answer.
CHECK_TIMEOUT_SECONDS = 2.0


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.ENVIRONMENT}


async def _check_postgres() -> None:
    # The app's own pooled async engine: no new engine per probe, and no
    # blocking driver call on the event loop.
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


async def _check_redis() -> None:
    redis = Redis.from_url(settings.REDIS_URL)
    try:
        await redis.ping()
    finally:
        await redis.aclose()


@router.get(
    "/health/ready",
    responses={503: {"description": "A dependency is unreachable"}},
)
async def readiness() -> JSONResponse:
    checks: dict[str, str] = {}
    for name, check in (("postgres", _check_postgres), ("redis", _check_redis)):
        try:
            await asyncio.wait_for(check(), timeout=CHECK_TIMEOUT_SECONDS)
            checks[name] = "ok"
        except Exception as exc:  # noqa: BLE001 - report, never crash the probe
            checks[name] = f"error: {type(exc).__name__}"

    ready = all(v == "ok" for v in checks.values())
    return JSONResponse(
        {"ready": ready, "checks": checks}, status_code=200 if ready else 503
    )
