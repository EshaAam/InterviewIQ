"""Refuse to start a worker that cannot do the work.

This exists because of a real incident. The embedding extra was added to the
image, but a running container kept its old virtualenv (the dev compose file
mounts `.venv` as an anonymous volume, which survives a rebuild unless
`--renew-anon-volumes` is passed). With `EMBEDDING_PROVIDER=local` set, the
worker started happily, accepted jobs, and crashed on the first embedding call
of every grading task. Nothing failed loudly: a `RuntimeError` is not a provider
error, so no give-up path ran, and the reaper re-dispatched the same doomed job
every thirty minutes while a candidate watched "Scoring your answers" for ten
hours.

A configuration error should stop the process at boot, where it is one line in
`docker compose ps`, rather than at the first job, where it is a stuck session
and a traceback nobody is reading.

The check is deliberately cheap and offline: it loads the configured local
model and embeds one word, which catches a missing package, a missing model file
and a dimension mismatch. It does *not* call a hosted embedding API — on the
free tier that would spend quota on every worker restart.
"""

from __future__ import annotations

import asyncio
import importlib

from app.embedders import get_embedder, resolved_embedding_provider
from app.models import KB_EMBEDDING_DIM


def runtime_problems() -> list[str]:
    """Everything that would make this worker fail its jobs. Empty means ready."""
    problems: list[str] = []

    # Retrieval and grounded grading read `kb_chunks.embedding`, whose column
    # type comes from pgvector's SQLAlchemy bindings.
    try:
        importlib.import_module("pgvector")
    except ImportError:
        problems.append(
            "the `pgvector` package is not installed, so the knowledge base "
            "cannot be queried"
        )

    provider = resolved_embedding_provider()
    if provider == "local":
        embedder = get_embedder()
        try:
            [vector] = asyncio.run(embedder.embed(["preflight"]))
        except Exception as exc:  # noqa: BLE001 - report every cause the same way
            problems.append(f"the local embedder could not load: {exc}")
        else:
            if len(vector) != KB_EMBEDDING_DIM:
                problems.append(
                    f"{embedder.name} emits {len(vector)}-dimension vectors but the "
                    f"knowledge base column is {KB_EMBEDDING_DIM}-wide"
                )
        finally:
            # The worker forks after this. Each child should build its own model
            # rather than inherit an onnxruntime session across a fork.
            get_embedder.cache_clear()

    return problems


def remedy() -> str:
    return (
        "Rebuild with fresh virtualenvs:  docker compose up -d --build "
        "--renew-anon-volumes api worker beat   — or set EMBEDDING_PROVIDER=hash "
        "to run without the local model."
    )
