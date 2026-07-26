from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import app


async def test_health_returns_ok():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"{settings.API_V1_PREFIX}/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
