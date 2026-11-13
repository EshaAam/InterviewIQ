# Deploying InterviewIQ

How to run the backend in production with `docker-compose.prod.yml` on a single
Linux host, and what to look after once it's running. Section 9 covers the live
Render + Neon RAG deployment. The Compose setup was exercised end to end against
the production image (fake provider) before being written down.

The frontend runs in the same compose file as the `web` service.

---

## 1. What runs

| Service | Image | Role | Scale |
|---|---|---|---|
| `db` | postgres:16 | All data | 1 (or use a managed Postgres) |
| `redis` | redis:7 | Job queue + AI response cache | 1 |
| `migrate` | backend `prod` | Runs `alembic upgrade head`, then exits | runs once per deploy |
| `api` | backend `prod` | FastAPI on :8000 (2 uvicorn workers) | any |
| `worker` | backend `prod` | Celery: parsing, questions, grading | any; `WORKER_CONCURRENCY` per container |
| `beat` | backend `prod` | Every 5 min, re-queues lost jobs | **exactly 1** |
| `web` | frontend | The Next.js app on :3000 (standalone server) | any |

`api`, `worker` and `beat` only start after `migrate` has **succeeded**, so new code
never runs against an old schema. Only the API's and the web app's ports are published.

Both images run as unprivileged users (backend uid 10001, web uid 1000), contain
runtime dependencies only, and have a liveness `HEALTHCHECK`.

---

## 2. Configuration

Copy `.env.example` to `.env` on the server (or point `ENV_FILE` at another file).
These **must** change from the example:

| Variable | Why |
|---|---|
| `ENVIRONMENT=production` | Turns on the startup check below. |
| `SECRET_KEY` | Signs every login token. The API **refuses to start** outside `local` with the placeholder or anything under 32 characters. Generate: `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `POSTGRES_PASSWORD` | The database password. |
| `CORS_ORIGINS` | The frontend's real origin(s), comma-separated, e.g. `https://app.example.com`. |
| `PUBLIC_API_URL` | Shell/compose variable, read when the **web image is built**: the API's URL *as a browser reaches it*, e.g. `https://api.example.com/api/v1`. It's baked into the JavaScript, so changing it means rebuilding `web`. Its page origin must be in `CORS_ORIGINS`. |
| `LLM_PROVIDER=gemini`, `GEMINI_API_KEY` / `GEMINI_API_KEYS` | The real model. `GEMINI_MODEL=gemini-3.6-flash` is the one this project has run on. |
| `DEBUG=false` | `true` logs every SQL statement. |

Worth reviewing: `USER_DAILY_TOKEN_BUDGET` (per user per UTC day),
`SESSION_TTL_MINUTES` (interview length), `WORKER_CONCURRENCY` (see §6),
`LLM_PRICE_*_PER_1K` (match your model's price so the cost page is right).

Never commit `.env`. Never set `FAKE_LATENCY_MS` in production (load tests only).

---

## 3. First deploy

```bash
git clone https://github.com/EshaAam/InterviewIQ.git && cd InterviewIQ
cp .env.example .env && $EDITOR .env           # §2

PUBLIC_API_URL=https://api.example.com/api/v1   docker compose -f docker-compose.prod.yml up -d --build --wait
docker compose -f docker-compose.prod.yml ps   # migrate: Exited (0); the rest: healthy
```

Create the first recruiter — the sign-up form only ever makes candidates:

```bash
docker compose -f docker-compose.prod.yml exec api python -m app.cli create-recruiter you@company.com
```

Check it end to end (creates one throwaway candidate; spends real tokens on Gemini):

```bash
cd backend
uv run python tests/smoke_test.py https://api.example.com \
  --recruiter-email you@company.com --recruiter-password '...'
```

Put a TLS-terminating reverse proxy (Caddy, nginx, a cloud load balancer) in front of
port 8000 (API) and port 3000 (web), usually as two hostnames. The API trusts `X-Forwarded-*` headers from it. Point the load balancer's
health check at `GET /api/v1/health/ready`. It answers **503** when Postgres or Redis
is unreachable.

---

## 4. Upgrading

```bash
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

`migrate` runs first on every `up`. If it fails, the old containers keep serving and
nothing new starts. Read `docker compose -f docker-compose.prod.yml logs migrate`.

Migrations are checked in CI against real Postgres (upgrade, `alembic check`,
downgrade, upgrade), but a downgrade on a live database still loses the data in the
dropped columns. **Back up first** (§5) if a release contains a migration.

New Python dependencies are baked into the image by `--build`. (In the *dev* stack
they also need `--renew-anon-volumes`; production has no bind mounts.)

---

## 5. Backups

| What | Where | How |
|---|---|---|
| Database | volume `postgres_data` | `docker compose -f docker-compose.prod.yml exec db pg_dump -U interviewiq -Fc interviewiq > backup-$(date +%F).dump` |
| Uploaded résumés | volume `uploads` (`/data/uploads`) | Copy the volume, or move to object storage. The text is also in the DB. |
| Redis | volume `redis_data` | No backup needed: a queue and a cache. Lost jobs are re-queued by `beat`. |

Restore: `pg_restore -U interviewiq -d interviewiq --clean backup.dump` into the `db`
container, then `up` again.

---

## 6. Capacity

From the Phase 7 load test (20 concurrent candidates, AI calls faked at 400 ms):

- The **API** stayed under 80 ms at p95 on every endpoint. It isn't the bottleneck.
- **Workers** are. Each one grades interviews one AI call at a time. The wait from
  "finish" to "graded" was ~12 s at p50 with `WORKER_CONCURRENCY=4`. Raise it, or run
  more `worker` containers (`--scale worker=3`), when that wait grows.
- Real model calls take seconds, not 400 ms, and are rate-limited per key. More
  Gemini keys (`GEMINI_API_KEYS`) raise that ceiling.

Re-run the load test against a staging stack on the fake provider:
`uvx locust -f loadtest/locustfile.py --host http://staging:8000 --headless -u 20 -r 2 -t 2m`.

---

## 7. What to watch

| Signal | Where | Means |
|---|---|---|
| `/health/ready` is 503 | load balancer | Postgres or Redis is down. |
| Sessions `FAILED` with "did not complete after 5 attempts" | Recruiter → Sessions → FAILED | The AI provider was down for longer than the retry window (~8 min). |
| `llm_calls` rows with `status='error'` / `'circuit_open'` climbing | Recruiter → Costs | Provider trouble, or a bad key. |
| Many sessions stuck in `CREATED` / `EVALUATING` | Recruiter → Sessions | Workers down, or `beat` not running. |
| Review queue growing | Recruiter → Review | The two grading passes disagree often; `EVAL_*` thresholds may need tuning. |
| `docker compose ps` shows `worker` unhealthy | host | The worker stopped answering Celery pings. It will be restarted. |

---

## 8. Failure drills

These were run against the production image during Phase 7:

- **A worker killed mid-grading** (`docker kill`): the half-done grading rolls back.
  Redis returns the job only after its visibility timeout (1 hour), so the **reaper**
  (`beat`) re-queues the session once it has sat in `EVALUATING` for 30 minutes. The
  result is exactly one grade per answer and one report.
- **The AI provider down:** jobs retry after 30 s, 60 s, 120 s and 240 s, then the
  session is marked `FAILED` with the reason. No session waits forever.

---

## 9. RAG on Render + Neon

The live demo uses the Render backend, Neon Postgres and Vercel frontend. Its
knowledge base is stored in Neon; Render does not need to ingest Markdown at
startup. The deployed image includes the BGE-small embedding model and uses a
solo Celery worker with one embedding thread to fit Render's free instance.
Keep the existing Vercel API URL, CORS origins, Gemini keys, database credentials
and `SECRET_KEY` when changing RAG settings.

### Seed a new database before enabling RAG

The current production database was seeded and verified. Repeat these steps only
for a new database, a changed corpus, or a deliberate re-embedding. Confirm that
Alembic is current and pgvector is installed; rehearse on a Neon branch when
possible. Build the same image used by Render:

```powershell
docker build -f backend/Dockerfile.render -t interviewiq-render:rag backend
```

Create `.env.neon.local` in the repository root. It is ignored by Git; keep the
database password there rather than in a command line or committed file:

```dotenv
POSTGRES_HOST=<direct Neon host without -pooler>
POSTGRES_PORT=5432
POSTGRES_USER=<database role>
POSTGRES_PASSWORD=<database password>
POSTGRES_DB=<database name>
POSTGRES_SSLMODE=require
DEBUG=false
LLM_PROVIDER=fake
EMBEDDING_PROVIDER=local
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
EMBEDDING_DIM=384
EMBEDDING_THREADS=1
RAG_ENABLED=true
```

`LLM_PROVIDER=fake` applies only to these operator commands. Ingestion and the
RAG check do not call a generation model; the live service keeps Gemini.

```powershell
$kbPath = (Resolve-Path ./backend/kb).Path
docker run --rm --env-file .env.neon.local --mount "type=bind,source=$kbPath,target=/kb,readonly" --entrypoint python interviewiq-render:rag -m app.cli ingest-kb --kb-dir /kb
if ($LASTEXITCODE -ne 0) { throw 'KB ingestion failed; do not enable production RAG.' }
docker run --rm --env-file .env.neon.local --entrypoint python interviewiq-render:rag -m app.cli check-rag
if ($LASTEXITCODE -ne 0) { throw 'RAG check failed; do not enable production RAG.' }
```

Ingestion is idempotent and commits once. Do not use `--force` to bypass a model
mismatch: existing questions cite chunk IDs, so investigate compatibility before
re-embedding. A different embedding width requires a schema migration and full
re-embedding.

### Enable and verify

The Render Blueprint in `render.yaml` declares `RAG_ENABLED=true`,
`EMBEDDING_PROVIDER=local`, `EMBEDDING_MODEL=BAAI/bge-small-en-v1.5`,
`EMBEDDING_DIM=384` and `EMBEDDING_THREADS=1`. Confirm these synced to the
existing service. Check `/api/v1/health/ready`, then create a new interview
using a CV with skills covered by the KB. In the recruiter view, inspect
`grounded` questions and their resolved source passages. Old interviews retain
their generation-time citations.

For an automated full-interview check, run this from `backend` with recruiter
credentials. It creates a test candidate, calls the configured model, submits
answers and checks the report, PDF and saved citations:

```bash
uv run python tests/smoke_test.py https://api.example.com \
  --recruiter-email you@company.com --recruiter-password '...' --require-grounded
```

Monitor memory, restarts, question-generation latency and Gemini quota after a
deploy. A local fake-provider resource test checks the container and embedding
path; a live Gemini interview confirms the deployed path.

### Roll back

Set `RAG_ENABLED=false` on Render and redeploy if the RAG path becomes unstable.
Leave the KB tables and embedding model in place. New interviews then use the
existing ungrounded generation path; stored citations on earlier questions
remain available. Do not switch the embedding provider to `hash` while the KB
contains BGE vectors.
