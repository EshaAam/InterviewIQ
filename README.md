# InterviewIQ

An AI-assisted technical interview platform. FastAPI backend with an async evaluation
pipeline and a provider-agnostic LLM layer; Next.js frontend.

Full design spec: [docs/interviewiq-pipeline.md](docs/interviewiq-pipeline.md)

> **Status:** Phase 1 — infrastructure. No AI wired yet, by design.

---

## Stack

| Layer | Choice |
|---|---|
| API | FastAPI (Python 3.12), uv for dependency management |
| Database | PostgreSQL 16 + SQLAlchemy 2.0 + Alembic |
| Cache / broker | Redis 7 |
| Background jobs | Celery |
| Frontend | Next.js (App Router), TypeScript, Tailwind |
| Local orchestration | Docker Compose |

---

## Layout

```
InterviewIQ/
├── docker-compose.yml       # db + redis + api
├── .env.example             # copy to .env
├── docs/                    # design spec
├── backend/
│   ├── pyproject.toml
│   ├── Dockerfile
│   ├── app/
│   │   ├── main.py          # app factory
│   │   ├── core/            # config, logging, security
│   │   ├── api/v1/          # routers — HTTP only, no business logic
│   │   ├── db/              # engine, session, Base
│   │   ├── models/          # SQLAlchemy tables
│   │   ├── schemas/         # Pydantic request/response contracts
│   │   ├── services/        # business logic (SessionService, FSM)
│   │   ├── providers/       # LLM provider implementations
│   │   └── workers/         # Celery tasks
│   └── tests/
└── frontend/
    └── src/
        ├── app/             # App Router pages
        └── lib/api.ts       # single backend entry point
```

The split that matters: **routes parse and validate, services decide, models store.**
A route should never contain an `if` that encodes a business rule.

---

## Running it

```bash
cp .env.example .env
docker compose up -d --build
```

| What | Where |
|---|---|
| API docs (Swagger) | http://localhost:8000/docs |
| Liveness | http://localhost:8000/api/v1/health |
| Readiness | http://localhost:8000/api/v1/health/ready |

Frontend:

```bash
cd frontend
cp .env.local.example .env.local
npm run dev            # http://localhost:3000
```

### Backend without Docker

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload
```

Set `POSTGRES_HOST=localhost` in `.env` when running this way — `db` is the
container's hostname and only resolves inside the Compose network.

### Tests & lint

```bash
cd backend
uv run pytest
uv run ruff check .
```

---

## Build order

| Phase | Focus | Status |
|---|---|---|
| 1 | Infra & domain — Compose, auth, FSM, Alembic | in progress |
| 2 | Full pipeline against `FakeProvider`, offline | |
| 3 | Real provider — retries, cache, budget, circuit breaker | |
| 4 | Evaluation quality — dual-pass scoring, divergence check | |
| 5 | Integrity signals & PDF reports | |
| 6 | Harden & ship — load test, chaos test, CI, deploy | |
