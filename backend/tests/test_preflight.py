"""The worker refuses to start when it cannot do the work.

Pinned because the failure it prevents is silent: a worker missing its
embedding model accepted grading jobs and crashed on every one, leaving a
session in EVALUATING for ten hours with nothing in the ledger and no reason on
the row. Boot is the right place for that to fail.
"""

from __future__ import annotations

import builtins

import pytest

from app.core.config import settings
from app.embedders import get_embedder
from app.workers import preflight


@pytest.fixture(autouse=True)
def _fresh_embedder():
    get_embedder.cache_clear()
    yield
    get_embedder.cache_clear()


def test_a_healthy_offline_worker_has_no_problems():
    # The suite runs on the hashing embedder with pgvector installed.
    assert preflight.runtime_problems() == []


def test_a_missing_local_model_is_reported(monkeypatch):
    """The exact incident: EMBEDDING_PROVIDER=local, fastembed not installed."""
    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER", "local")
    real_import = builtins.__import__

    def no_fastembed(name, *args, **kwargs):
        if name == "fastembed":
            raise ImportError("No module named 'fastembed'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_fastembed)

    problems = preflight.runtime_problems()
    assert any("local embedder could not load" in p for p in problems)


def test_a_missing_pgvector_package_is_reported(monkeypatch):
    real = preflight.importlib.import_module

    def no_pgvector(name, *args, **kwargs):
        if name == "pgvector":
            raise ImportError("No module named 'pgvector'")
        return real(name, *args, **kwargs)

    monkeypatch.setattr(preflight.importlib, "import_module", no_pgvector)
    assert any("pgvector" in p for p in preflight.runtime_problems())


def test_a_model_of_the_wrong_width_is_reported(monkeypatch):
    """A model swap without a migration would write vectors the column rejects."""
    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER", "local")

    class Narrow:
        name = "narrow-model"
        dim = 128

        async def embed(self, texts):
            return [[0.1] * 128 for _ in texts]

    def factory() -> Narrow:
        return Narrow()

    factory.cache_clear = lambda: None  # mirrors the lru_cache API preflight calls
    monkeypatch.setattr(preflight, "get_embedder", factory)

    problems = preflight.runtime_problems()
    assert any("128-dimension" in p for p in problems)


def test_a_hosted_embedder_is_not_called_at_boot(monkeypatch):
    """Probing a hosted embedding API on every restart would spend free-tier
    quota for nothing."""
    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER", "gemini")

    def explode():  # pragma: no cover - must not be reached
        raise AssertionError("preflight must not build a hosted embedder")

    monkeypatch.setattr(preflight, "get_embedder", explode)
    assert preflight.runtime_problems() == []


def test_the_remedy_names_the_rebuild_flag_that_matters():
    """A plain rebuild keeps the stale venv; the flag is the whole fix."""
    assert "--renew-anon-volumes" in preflight.remedy()


def test_the_worker_exits_rather_than_starting_broken(monkeypatch):
    from app.workers import celery_app

    monkeypatch.setattr(preflight, "runtime_problems", lambda: ["broken"])
    with pytest.raises(SystemExit):
        celery_app._refuse_to_start_broken()


def test_a_healthy_worker_starts(monkeypatch):
    from app.workers import celery_app

    monkeypatch.setattr(preflight, "runtime_problems", lambda: [])
    celery_app._refuse_to_start_broken()  # does not raise
