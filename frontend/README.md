# InterviewIQ — Frontend

Next.js 16.3 (App Router) + React 19 + Tailwind v4. One app for both roles:
candidates take interviews, recruiters review scores and costs. No state, data-fetching,
component or form library — everything is in `src/`. Dev-only: Vitest +
Testing Library for unit tests, Playwright for browser tests.

## Run it

The backend must be running first (`docker compose up` in the repo root, API at
`http://localhost:8000`).

```bash
cp .env.local.example .env.local   # sets NEXT_PUBLIC_API_URL
npm install
npm run dev                        # http://localhost:3000
```

The backend allows the origins in its `CORS_ORIGINS` setting (default `http://localhost:3000`), so keep that port or add yours there.

## Check it

```bash
npm run lint
npm run typecheck
npm test                 # unit tests (Vitest), beside the code as *.test.ts[x]
npm run build            # stricter than `dev` — run it before trusting a refactor
npm run e2e              # browser tests (Playwright) — see below
```

The browser tests drive a real Chromium through a whole interview. They need the
backend running on the fake provider, and a build that points at it:

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1 npm run build
npx playwright install chromium   # once
npm run e2e                       # starts `npm run serve` (the standalone server) itself
```

## Production

`output: "standalone"` + [Dockerfile](Dockerfile): a non-root Node 22 image that runs
`server.js`. `NEXT_PUBLIC_API_URL` is a build argument — it's inlined into the bundle,
so each environment needs its own build. Run it with the rest of the stack via
`docker-compose.prod.yml` (service `web`); see `docs/deploy.md`.

## Layout

| Path | What it is |
| --- | --- |
| `src/app/login` | Sign in / register. |
| `src/app/(app)/` | Everything behind a token. The folder's layout resolves the user once. |
| `src/app/(app)/interview` | Candidate: paste résumé → questions → timed interview. |
| `src/app/(app)/reports/[sessionId]` | Candidate report. |
| `src/app/(app)/recruiter/*` | Recruiter: sessions, review queue, costs (role-gated). |
| `src/lib/api.ts` | The only file that talks to the backend (token refresh on 401). |
| `src/lib/auth.ts` | Token storage. Dependency-free on purpose. |
| `src/lib/use-user.ts` | Who is signed in (`GET /auth/me`), and where each role lands. |
| `src/components/ui.tsx` | The design-system primitives. Tokens live in `src/app/globals.css` (every text colour meets WCAG AA contrast). |
| `src/app/error.tsx`, `not-found.tsx`, `global-error.tsx` | What users see instead of a blank screen. |
| `e2e/` | Playwright browser tests. |

The phase-by-phase build plan is in `docs/frontend.md`, and the system design is in
[`docs/hld.md`](../docs/hld.md).
