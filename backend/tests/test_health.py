from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import app


async def test_health_returns_ok():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"{settings.API_V1_PREFIX}/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_readiness_is_503_when_a_dependency_is_down(monkeypatch) -> None:
    from app.api.v1.routes import health as health_routes

    async def _postgres_up() -> None:
        return None

    async def _redis_down() -> None:
        raise ConnectionError("redis unreachable")

    monkeypatch.setattr(health_routes, "_check_postgres", _postgres_up)
    monkeypatch.setattr(health_routes, "_check_redis", _redis_down)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"{settings.API_V1_PREFIX}/health/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["ready"] is False
    assert body["checks"] == {"postgres": "ok", "redis": "error: ConnectionError"}
