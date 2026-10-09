# syntax=docker/dockerfile:1
#
# Two targets from one file:
#   dev  — what docker-compose.yml runs: dev dependencies, code bind-mounted,
#          uvicorn --reload. Fast edit loop, not fit for the internet.
#   prod — what docker-compose.prod.yml runs: runtime dependencies only, code
#          baked into the image, a non-root user, no reload, a healthcheck.
#
# Build one explicitly:  docker build --target prod -t interviewiq-api ./backend

# Pinned, not :latest — a new uv release must not change a build silently.
FROM ghcr.io/astral-sh/uv:0.10.6 AS uv

# ---------------------------------------------------------------------------
FROM python:3.12-slim AS dev

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY --from=uv /uv /usr/local/bin/uv

WORKDIR /app

# Dependencies are copied first so Docker caches the install layer and
# only re-runs it when the manifests actually change — not on every edit.
COPY pyproject.toml uv.lock ./
# --extra embed: the local embedding model (RAG Phase 1). --extra voice: local
# speech-to-text for voice answers (off until VOICE_ENABLED=true). Both are kept
# out of the lint and test CI job, which uses offline fakes for each.
RUN uv sync --frozen --no-install-project --extra embed --extra voice

ENV PATH="/app/.venv/bin:$PATH"     EMBEDDING_CACHE_DIR=/opt/models     WHISPER_CACHE_DIR=/opt/models/whisper

# Bake the embedding model into the image. The cache lives inside the
# container, so without this every container start re-downloads ~130 MB and
# a worker can stall mid-job fetching it. EMBEDDING_CACHE_DIR points the
# runtime at the same path.
RUN python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='BAAI/bge-small-en-v1.5', cache_dir='/opt/models')"
# The speech model too (~145 MB), for the same reason: a voice answer must not
# wait on a download. WHISPER_CACHE_DIR points the runtime at it.
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('base.en', device='cpu', compute_type='int8', download_root='/opt/models/whisper')"

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ---------------------------------------------------------------------------
# Build stage for prod: resolve and install runtime dependencies only.
FROM python:3.12-slim AS prod-deps

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
# --frozen: install exactly uv.lock, fail if it's out of date with pyproject.
# --no-dev: no pytest, ruff or test-only drivers in the shipped image.
RUN uv sync --frozen --no-dev --no-install-project --extra embed --extra voice

ENV PATH="/app/.venv/bin:$PATH"
# Bake the embedding model into the image. The cache lives inside the
# container, so without this every container start re-downloads ~130 MB and
# a worker can stall mid-job fetching it. EMBEDDING_CACHE_DIR points the
# runtime at the same path.
RUN python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='BAAI/bge-small-en-v1.5', cache_dir='/opt/models')"
# The speech model too (~145 MB), for the same reason: a voice answer must not
# wait on a download. WHISPER_CACHE_DIR points the runtime at it.
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('base.en', device='cpu', compute_type='int8', download_root='/opt/models/whisper')"

# ---------------------------------------------------------------------------
FROM python:3.12-slim AS prod

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

# A fixed, unprivileged user. If the app is ever compromised, it can't write
# to its own code or to anything outside the upload directory.
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --home-dir /app --no-create-home app \
 && mkdir -p /data/uploads \
 && chown app:app /data/uploads

WORKDIR /app
COPY --from=prod-deps /app/.venv /app/.venv
COPY --from=prod-deps /opt/models /opt/models
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./

USER app
ENV UPLOAD_DIR=/data/uploads EMBEDDING_CACHE_DIR=/opt/models WHISPER_CACHE_DIR=/opt/models/whisper

EXPOSE 8000
# The *liveness* endpoint: a dead process gets restarted. Readiness (which
# also checks Postgres and Redis) is for a load balancer, not for restarts.
# --start-interval: check every 2 s while starting, so `compose up --wait`
# and CI don't idle for a full interval before the first check.
HEALTHCHECK --interval=30s --timeout=3s --start-period=30s --start-interval=2s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=2).status == 200 else 1)"]

# Several worker processes; uvicorn restarts any that die. The container
# runtime (restart: unless-stopped) handles the whole container.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers", "--forwarded-allow-ips", "*"]
