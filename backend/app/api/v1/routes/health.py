"""Health endpoints.

`/health` is a liveness probe — is the process up?
`/health/ready` is a readiness probe — can it actually serve traffic
(Postgres and Redis reachable)? Orchestrators treat these differently:
a failing liveness check restarts the container, a failing readiness
check only pulls it out of the load balancer.
"""

from fastapi import APIRouter
from redis.asyncio import Redis
from sqlalchemy import create_engine, text

from app.core.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.ENVIRONMENT}


@router.get("/health/ready")
async def readiness() -> dict[str, object]:
    checks: dict[str, str] = {}

    try:
        engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as exc:  # noqa: BLE001 - report, never crash the probe
        checks["postgres"] = f"error: {type(exc).__name__}"

    try:
        redis = Redis.from_url(settings.REDIS_URL)
        await redis.ping()
        await redis.aclose()
        checks["redis"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = f"error: {type(exc).__name__}"

    ready = all(v == "ok" for v in checks.values())
    return {"ready": ready, "checks": checks}
