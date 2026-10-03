# InterviewIQ

An AI-assisted technical interview platform. A candidate uploads a résumé, answers
questions written from their own skills, and gets a per-topic report. A recruiter sees
every interview, reviews the answers the AI was unsure about, and watches the cost.

The idea that shapes everything: **an AI grader gives a different score each time.**
So every answer is graded twice — by a deterministic embedding check and by the model —
and when the two disagree, the answer goes to a human instead of being averaged.

[![CI](https://github.com/EshaAam/InterviewIQ/actions/workflows/ci.yml/badge.svg)](https://github.com/EshaAam/InterviewIQ/actions/workflows/ci.yml)

| | |
|---|---|
| **How it works** | [docs/hld.md](docs/hld.md) — the whole system, from the big picture down to the code layout |
| **Deploying** | [docs/deploy.md](docs/deploy.md) |
| **Original design** | [docs/interviewiq-pipeline.md](docs/interviewiq-pipeline.md) |

---

## Run it

Needs Docker. No API key: by default the AI is a deterministic fake.

```bash
cp .env.example .env
docker compose up -d --build
docker compose exec api alembic upgrade head
```

Then the frontend:

```bash
cd frontend
cp .env.local.example .env.local
npm install && npm run dev        # http://localhost:3000
```

Sign up as a candidate on the page. To review interviews you need a recruiter account,
which can't be created from the sign-up form:

```bash
docker compose exec api python -m app.cli create-recruiter you@company.com
```

| What | Where |
|---|---|
| App | http://localhost:3000 |
| API docs (Swagger) | http://localhost:8000/docs |
| Readiness | http://localhost:8000/api/v1/health/ready |

To use the real model, set `LLM_PROVIDER=gemini` and `GEMINI_API_KEY` in `.env`
(several keys, comma-separated in `GEMINI_API_KEYS`, are rotated around rate limits).

---

## Architecture in one paragraph

A **Next.js** app talks to a **FastAPI** API. The API never waits on the AI: it saves
the request to **PostgreSQL**, commits, queues a job on **Redis**, and returns `202`.
**Celery** workers do the slow work — read the résumé, write questions, grade answers,
build the report — and the browser polls until it's done. A **state machine** owns
every session's lifecycle; every pipeline stage is **idempotent**, so a retried or
redelivered job can't double-score; and every AI call lands in a **ledger** that the
per-user token budget and the cost page both read. The AI sits behind one small
interface, wrapped in cache → circuit breaker → retry → JSON repair.

```
browser ── Next.js ── FastAPI ──┬── PostgreSQL   (everything that matters)
                                └── Redis ── Celery workers ── LLM (Gemini or fake)
                                              └── beat: re-queues lost jobs every 5 min
```

---

## Trade-offs worth knowing

- **Polling, not WebSockets.** One request per second per waiting candidate is cheap,
  and the server's deadline stays the only source of truth. Revisit at scale.
- **Two grading passes cost more** than one. That's the price of a score you can
  defend; disagreements go to a person rather than being averaged away.
- **Integrity signals are advisory.** Paste and typing-speed data comes from the
  browser and can be forged, so it flags a session for a recruiter and never changes
  a score.
- **Résumé text is extracted at upload,** not in the worker: an unreadable file is a
  clear error right away instead of a failed job a minute later.
- **Token counts are estimates** (about 4 characters per token), not the provider's
  billed numbers. Good enough for a budget; not an invoice.

## Reproducibility and cost

Questions carry their **expected concepts** before anyone answers, so what counts as a
good answer is fixed in advance. Grading runs at temperature 0; disagreements re-run at
0.4 *without* the cache, and the median decides. Every AI call — including failed,
cached and circuit-broken ones, each at what it really cost — is a row in `llm_calls`.
Each user has a daily token budget (200,000 by default); it gates *starting* work, so
an interview already under way can always finish.

---

## Tests

```bash
cd backend
uv run pytest            # ~125 tests, SQLite in memory, fake AI, no network
uv run ruff check app tests scripts
```

The suite runs a complete interview over real HTTP, plus the failure cases: AI
outages, malformed model output, a worker dying mid-grading, the budget versus the
ledger.

```bash
cd frontend
npm test                          # 31 unit tests (Vitest)
npm run build && npm run e2e      # Playwright, in Chromium; needs the backend running
```

**CI** ([.github/workflows/ci.yml](.github/workflows/ci.yml)) runs both suites, every
migration against real Postgres (up, `alembic check`, down, up), the browser tests
against the production backend stack, and builds both production images.

**Against a running stack:**

```bash
cd backend && uv run python scripts/smoke_test.py http://localhost:8000
```

**Load test** (fake AI with model-like latency — see [loadtest/locustfile.py](loadtest/locustfile.py)):

```bash
uvx locust -f loadtest/locustfile.py --host http://localhost:8000 --headless -u 20 -r 2 -t 2m
```

Baseline (20 concurrent candidates, 400 ms per AI call, 4 worker processes): every API
endpoint under 80 ms at p95 — sign-in ~300 ms, which is bcrypt doing its job — and
0 failures. The candidate's wait from "finish" to "graded" was 12 s at p50: that's the
worker pool, and `WORKER_CONCURRENCY` is the lever.

---

## Layout

```
InterviewIQ/
├── docker-compose.yml        # dev: db, redis, api (--reload), worker, beat
├── docker-compose.prod.yml   # production shape: migrate → api, worker, beat, web
├── .github/workflows/ci.yml
├── backend/
│   ├── app/
│   │   ├── api/v1/routes/    # HTTP only: auth, resumes, sessions, recruiter, health
│   │   ├── services/         # the rules: state machine, pipeline, scoring, budget, integrity
│   │   ├── providers/        # the AI: Gemini, fake, and the resilience wrappers
│   │   ├── workers/          # Celery tasks and the dispatcher
│   │   ├── models/ schemas/ db/ core/
│   │   └── cli.py            # admin commands (create-recruiter, promote)
│   ├── migrations/           # Alembic
│   ├── scripts/smoke_test.py
│   └── tests/
├── frontend/
│   ├── src/                  # Next.js App Router; lib/api.ts is the only HTTP client
│   ├── e2e/                  # Playwright browser tests
│   └── Dockerfile            # standalone server, non-root
├── loadtest/                 # Locust scenario
└── docs/                     # hld.md, deploy.md, design spec
```

The split that matters: **routes parse and validate, services decide, models store.**
