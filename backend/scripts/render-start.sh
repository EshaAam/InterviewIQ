#!/usr/bin/env bash
# Entrypoint for Dockerfile.render: the whole backend in one container.
#
# If any long-running process dies, the container exits, so the host restarts
# all of it. A container serving the API while its worker is dead would accept
# interviews it can never grade.
set -euo pipefail

# Queue and cache only, so nothing to persist. volatile-lru evicts only keys
# with a TTL (the LLM cache), never the job queue's lists.
redis-server --bind 127.0.0.1 --port 6379 --dir /tmp \
  --save "" --appendonly no \
  --maxmemory 48mb --maxmemory-policy volatile-lru &

until redis-cli -h 127.0.0.1 ping >/dev/null 2>&1; do sleep 0.2; done

# Schema first, before any code serves traffic.
alembic upgrade head

# Solo pool: one process instead of a parent plus children, each of which
# would load its own copy of the embedding model. No -B: embedded beat is a
# forked copy of this whole process, a second Python heap the 512 MB instance
# can't spare. The API enqueues the 5-minute reaper instead (REAPER_IN_API,
# set in Dockerfile.render).
celery -A app.workers.celery_app worker --pool=solo --loglevel=info &

uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-10000}" --workers 1 \
  --proxy-headers --forwarded-allow-ips '*' &

wait -n
echo "a process exited; stopping the container so it is restarted" >&2
exit 1
