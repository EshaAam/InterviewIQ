# Enable RAG on Render + Neon

Keep Vercel's API URL and the deployed CORS origins unchanged. The existing
Render image already includes BGE-small and uses one solo Celery worker with
one embedding thread. No new hosted service or database migration is needed
for this rollout if the current migrations are already applied.

## Seed before enabling the deployed flag

1. Confirm the target Neon database has the current Alembic revision and the
   `vector` extension. Use a Neon branch to rehearse the rollout if available.
2. Build the backend image from the repository root:

   ```powershell
   docker build -f backend/Dockerfile.render -t interviewiq-render:rag backend
   ```

3. Create `.env.neon.local` in the repository root (ignored by Git). Supply
   the target database's direct host and credentials through this file, never
   through committed files or command-line arguments:

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

   `LLM_PROVIDER=fake` applies only to these operator commands. Neither ingestion
   nor `check-rag` calls a generation model; the live service keeps Gemini.

4. Run ingestion from your PC, mounting only the KB directory read-only:

   ```powershell
   $kbPath = (Resolve-Path ./backend/kb).Path
   docker run --rm --env-file .env.neon.local --mount "type=bind,source=$kbPath,target=/kb,readonly" --entrypoint python interviewiq-render:rag -m app.cli ingest-kb --kb-dir /kb
   if ($LASTEXITCODE -ne 0) { throw 'KB ingestion failed; do not enable production RAG.' }
   docker run --rm --env-file .env.neon.local --entrypoint python interviewiq-render:rag -m app.cli check-rag
   if ($LASTEXITCODE -ne 0) { throw 'RAG probe failed; do not enable production RAG.' }
   ```

   Ingestion is idempotent and commits once. Do not pass `--force` to bypass a
   model mismatch: existing questions cite chunk IDs, so investigate compatibility
   before re-ingesting any changed corpus. Runtime retrieval uses Neon, not the
   Markdown files, so no KB files or ingestion process are needed on Render.

## Enable and verify

5. Deploy the code, then verify Render actually has `RAG_ENABLED=true`,
   `EMBEDDING_PROVIDER=local`, `EMBEDDING_MODEL=BAAI/bge-small-en-v1.5`,
   `EMBEDDING_DIM=384`, and `EMBEDDING_THREADS=1`. The Blueprint declares these
   values; confirm they synced to the existing service. Preserve the existing
   Gemini keys, database credentials, SECRET_KEY, and Vercel CORS origin.
6. Check `/api/v1/health/ready`, then run a new interview using a CV whose skills
   the KB covers. In the recruiter view, inspect `grounded` and the actual source
   passages. Old interviews retain their original generation-time evidence.
7. For an automated full-interview check, run `scripts/smoke_test.py` against the
   deployed backend with recruiter credentials and `--require-grounded`. It creates
   a test candidate, calls the configured Gemini provider, submits answers,
   checks the report/PDF, and rejects interviews without resolved citations.
8. Monitor memory, restarts, generation latency, and Gemini quota. A local
   resource test with fake generation checks the container and embedding paths;
   it does not replace a real Gemini check on the deployed service.

## Rollback

Set `RAG_ENABLED=false` on Render and redeploy if the new path is unstable.
Leave the KB tables and embedding model in place. This returns new interviews
to the existing ungrounded generation path; stored citations on earlier
questions remain available. Do not change embedding provider to `hash` while
the KB still contains BGE vectors.
