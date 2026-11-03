"""Shared test fixtures.

Tests run fully offline against an in-memory SQLite database â€” no Postgres,
no Docker needed for the suite. The app's `get_db` dependency is overridden
to hand out sessions bound to that in-memory engine, and the schema is built
from `Base.metadata` (the same metadata Alembic migrates in production).

The pipeline dispatcher is overridden with `InlineDispatcher`, so posting to an
async endpoint runs the real pipeline synchronously against the same session â€”
a true end-to-end flow on the fake provider, with no Celery or broker.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 - register all models on Base.metadata
from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.providers import FakeProvider
from app.providers.canned import default_canned_responses
from app.workers.dispatch import InlineDispatcher, get_dispatcher


@pytest.fixture(autouse=True)
def _test_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # Deterministic test config regardless of the developer's local .env:
    # always the fake provider, and a strong key so JWT emits no warning.
    from app.embedders.factory import get_embedder
    from app.providers.factory import get_provider

    monkeypatch.setattr(settings, "LLM_PROVIDER", "fake")
    # Feature tests opt in explicitly; local demo flags must not change the
    # baseline expected by tests for the disabled paths.
    monkeypatch.setattr(settings, "RAG_ENABLED", False)
    monkeypatch.setattr(settings, "VOICE_ENABLED", False)
    # Pinned, not left on "auto": the suite must never reach for fastembed or
    # the network, and the hashing vectors are what the cosine assertions
    # in test_providers / test_evaluation_quality were written against.
    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER", "hash")
    # The coverage threshold is calibrated *per embedder* - cosine values are
    # model-specific, and 0.65 (tuned for bge-small) applied to hashing vectors
    # drives every deterministic score to ~0, diverging from the LLM pass and
    # sending the whole suite to NEEDS_HUMAN_REVIEW. Pinning the embedder
    # without its matching threshold is the exact mistake `app.cli recalibrate`
    # exists to prevent, so the pair travels together here.
    monkeypatch.setattr(settings, "EVAL_COVERAGE_THRESHOLD", 0.55)
    monkeypatch.setattr(settings, "EVAL_DIVERGENCE_THRESHOLD", 0.35)
    monkeypatch.setattr(
        settings, "SECRET_KEY", "test-secret-key-at-least-32-bytes-long-000000"
    )
    get_provider.cache_clear()
    get_embedder.cache_clear()


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    # StaticPool keeps a single shared connection so the in-memory DB persists
    # across sessions within a test.
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture
def provider() -> FakeProvider:
    """A fresh fake provider per test; register bad responses to inject faults."""
    return FakeProvider(canned=default_canned_responses())


@pytest.fixture
async def client(
    db_session: AsyncSession, provider: FakeProvider
) -> AsyncGenerator[AsyncClient, None]:
    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        # Reuse the test's session and commit so route-created rows persist
        # for later assertions/requests within the same test.
        yield db_session
        await db_session.commit()

    def _override_get_dispatcher() -> InlineDispatcher:
        return InlineDispatcher(db_session, provider)

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_dispatcher] = _override_get_dispatcher
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def recruiter(client: AsyncClient, db_session: AsyncSession):
    """Factory: `headers = await recruiter("r@example.com")`.

    Recruiters can't self-register, so â€” like `python -m app.cli
    create-recruiter` â€” the account is created through the service, then
    signed in through the real login endpoint.
    """
    from app.models.user import UserRole
    from app.services.user_service import UserService

    async def _make(email: str) -> dict[str, str]:
        await UserService(db_session).register(
            email, "hunter2secret", role=UserRole.recruiter
        )
        await db_session.commit()
        tokens = (
            await client.post(
                f"{settings.API_V1_PREFIX}/auth/login",
                json={"email": email, "password": "hunter2secret"},
            )
        ).json()
        return {"Authorization": f"Bearer {tokens['access_token']}"}

    return _make


@pytest.fixture
async def auth_client(client: AsyncClient) -> AsyncClient:
    """A client with a registered candidate and a bearer token attached."""
    from app.core.config import settings

    creds = {"email": "cand@example.com", "password": "hunter2secret"}
    await client.post(f"{settings.API_V1_PREFIX}/auth/register", json=creds)
    tokens = (
        await client.post(f"{settings.API_V1_PREFIX}/auth/login", json=creds)
    ).json()
    client.headers["Authorization"] = f"Bearer {tokens['access_token']}"
    return client
