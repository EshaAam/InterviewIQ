# InterviewIQ — Backend Design Spec

An AI-assisted technical interview platform. FastAPI backend, async evaluation pipeline,
provider-agnostic LLM layer.

The engineering story is not "we call an LLM." It is: **how do you make an LLM-backed
scoring system reproducible, cheap, and safe to fail?**

---

## 1. System Pipeline

```
                        ┌─────────────┐
                        │   Client    │
                        └──────┬──────┘
                               │ HTTPS
                        ┌──────▼──────────────────────┐
                        │  FastAPI (API layer)        │
                        │  auth · rate limit · req-id │
                        └──────┬──────────────────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        │                      │                      │
┌───────▼────────┐    ┌────────▼────────┐    ┌────────▼────────┐
│  Session FSM   │    │  Redis          │    │  PostgreSQL     │
│  (domain core) │    │  cache · broker │    │  system of      │
└───────┬────────┘    │  idempotency    │    │  record         │
        │             └────────┬────────┘    └─────────────────┘
        │ enqueue               │
┌───────▼───────────────────────▼─────────┐
│  Celery Workers                          │
│  parse · generate · evaluate · report    │
└───────┬──────────────────────────────────┘
        │
┌───────▼──────────────────────────────────┐
│  LLMProvider (Protocol)                  │
│  ├── GeminiProvider                      │
│  ├── OllamaProvider                      │
│  └── FakeProvider  ← tests & local dev   │
│  wrapped in: retry · circuit breaker ·   │
│              token budget · cache        │
└──────────────────────────────────────────┘
```

Everything crossing the dashed boundary into the LLM is treated as **untrusted,
slow, and failure-prone**. That assumption drives most of the design below.

---

## 2. Session State Machine

The spine of the project. Illegal transitions raise; every terminal-failure state
carries a `failure_reason` and is retryable from a known point.

```
                      ┌──────────┐
                      │ CREATED  │
                      └────┬─────┘
                           │ resume uploaded
                      ┌────▼─────┐
              ┌───────│ PARSING  │
              │       └────┬─────┘
       parse  │            │ skills extracted
       failed │       ┌────▼──────────┐
              │       │ GENERATING_Qs │
              │       └────┬──────────┘
              │            │ questions ready
              │       ┌────▼─────┐
              │       │  READY   │
              │       └────┬─────┘
              │            │ candidate starts
              │       ┌────▼─────────┐      timeout
              │       │ IN_PROGRESS  │──────────────┐
              │       └────┬─────────┘              │
              │            │ last answer submitted  │
              │       ┌────▼────────┐               │
              │       │ EVALUATING  │               │
              │       └────┬────────┘               │
              │            │                        │
              │      ┌─────┴──────┐                 │
              │      │            │ low confidence  │
              │ ┌────▼─────┐ ┌────▼──────────────┐  │
              │ │ COMPLETED│ │ NEEDS_HUMAN_REVIEW│  │
              │ └──────────┘ └───────────────────┘  │
              │                                     │
         ┌────▼─────┐                        ┌──────▼────┐
         │  FAILED  │                        │  EXPIRED  │
         └──────────┘                        └───────────┘
```

**Rules**
- Transitions happen in one place (`SessionService.transition`), never scattered in routes.
- Each async phase is idempotent — re-running a Celery task on the same session is a no-op
  if the target state is already reached.
- `EXPIRED` is computed from `expires_at` server-side. The client is never trusted with time.

---

## 3. Data Model

```
User(id, email, hashed_pw, role[candidate|recruiter], created_at)

Resume(id, user_id, file_uri, mime, text_content, parse_status, created_at)

ExtractedSkill(id, resume_id, name, confidence, evidence_span)

InterviewSession(id, user_id, resume_id, state, expires_at,
                 prompt_version, model_name, created_at)

Question(id, session_id, ordinal, text, difficulty, topic,
         expected_concepts[], reference_answer, prompt_version)

Answer(id, question_id, text, submitted_at, time_taken_ms,
       paste_events, keystroke_count, idempotency_key)

Evaluation(id, answer_id, concept_coverage{}, llm_scores{},
           deterministic_score, final_score, confidence,
           model_name, temperature, prompt_version, run_count)

Report(id, session_id, overall, per_topic{}, strengths[], gaps[], pdf_uri)

LLMCall(id, session_id, provider, model, prompt_tokens, completion_tokens,
        cost_estimate, latency_ms, status, created_at)
```

Two tables carry disproportionate weight:

- **`Question.expected_concepts`** — generated *with* the question, before any answer exists.
  This converts grading from "score this 0–100" (unstable) into "which of these five
  concepts appeared?" (far more reproducible).
- **`LLMCall`** — the audit and cost ledger. Without it you cannot answer
  "why did this score change?" or "what does one interview cost?"

---

## 4. Evaluation Pipeline (the core)

```
Answer text
     │
     ├──────────────────────────────┐
     │                              │
┌────▼──────────────────┐  ┌────────▼─────────────────┐
│ Deterministic pass    │  │ LLM pass                 │
│ · embed answer        │  │ · structured JSON schema │
│ · cosine vs each      │  │ · temperature = 0        │
│   expected_concept    │  │ · rubric: correctness,   │
│ · coverage ratio      │  │   depth, clarity         │
│ · no network call     │  │ · must cite evidence     │
└────┬──────────────────┘  └────────┬─────────────────┘
     │                              │
     └──────────────┬───────────────┘
                    │
          ┌─────────▼──────────┐
          │ Reconcile          │
          │ |llm − det| > θ ?  │
          └─────────┬──────────┘
                    │
        ┌───────────┴────────────┐
        │ agree                  │ diverge
┌───────▼────────┐      ┌────────▼─────────────┐
│ final_score    │      │ re-run LLM (n=2)     │
│ confidence=hi  │      │ still diverge?       │
└────────────────┘      │   → NEEDS_HUMAN      │
                        └──────────────────────┘
```

**Why this matters:** ask a model to grade the same answer three times at default
temperature and you get three different numbers. A scoring system that is not
reproducible is not a scoring system. The deterministic pass anchors it; the
divergence check catches the cases where the anchor and the model disagree —
which is exactly where a human should look.

---

## 5. LLM Provider Layer

```python
class LLMProvider(Protocol):
    async def complete(self, prompt: str, schema: type[BaseModel]) -> BaseModel: ...
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
```

Wrapped, in order:

| Layer | Responsibility |
|---|---|
| Cache | Redis, keyed on `hash(prompt + model + prompt_version)` |
| Budget | per-user daily token cap; reject with `429` before spending |
| Circuit breaker | open after N consecutive 5xx; fail fast instead of queueing |
| Retry | exponential backoff, jitter, max 2 attempts |
| Validate | parse into Pydantic; malformed JSON → one repair attempt → dead-letter |
| Meter | write `LLMCall` row regardless of outcome |

Implementations: `GeminiProvider`, `OllamaProvider`, `FakeProvider`.

**Build against `FakeProvider` first.** The entire pipeline should run end-to-end with
canned responses before you make a single real API call. This keeps the architecture
honest, makes the test suite fast and free, and means a provider outage never blocks you.

---

## 6. Integrity Signals

Not a solved problem — but ignoring it makes the product a toy. Collect, score, surface:

- **Paste events** and clipboard-length deltas from the client.
- **Time-to-first-keystroke** vs. answer length. A 400-word answer that started 3 seconds
  after the question appeared is a signal.
- **Perplexity band** of the submitted text. LLM-generated prose sits in a measurably
  narrow distribution compared to human writing under time pressure.
- Roll these into an `integrity_flag` on the report. Advisory, never auto-rejecting.

Implement two of the three. The point is demonstrating you thought about adversarial
users, not building a proctoring company.

---

## 7. API Surface

```
POST   /auth/register
POST   /auth/login                  → access + refresh
POST   /auth/refresh

POST   /resumes                     → 202 + job_id
GET    /resumes/{id}                → parse status, extracted skills

POST   /sessions                    → 202, creates session from resume
GET    /sessions/{id}               → state, progress, expires_at
POST   /sessions/{id}/start
GET    /sessions/{id}/questions/next
POST   /sessions/{id}/answers       → Idempotency-Key header required
POST   /sessions/{id}/finish

GET    /sessions/{id}/report
GET    /sessions/{id}/report.pdf

GET    /recruiter/sessions          → filtered, paginated
POST   /recruiter/evaluations/{id}/override   → human review queue
```

All async work returns `202` with a resource whose state can be polled.
No endpoint blocks on an LLM call.

---

## 8. Deliberately Excluded

| Cut | Why |
|---|---|
| Leaderboard | Gamifying interview scores is a bad product signal; pure CRUD |
| Email verification / password reset | Two days of work, zero interview value. Stub it. |
| RabbitMQ | Redis broker is correct for this load. A second broker you can't justify is worse than none. |
| WebSocket timer | A timer is `expires_at` validated server-side. Over WS it's both more work and easier to cheat. |
| Admin role | Two roles is enough. Three means a permissions matrix you'll never fill. |

If you want WebSockets, use them to stream evaluation progress during the async job —
somewhere they actually earn their place.

---

## 9. Build Order

| Phase | Focus | Done when |
|---|---|---|
| **1** | Infra & domain | Docker Compose up, auth works, FSM enforces transitions, Alembic clean. **No AI yet.** |
| **2** | Pipeline on fakes | Full flow end-to-end with `FakeProvider`. Integration tests green, offline. |
| **3** | Real provider | Gemini wired, structured output, retries, cache, budget, circuit breaker. |
| **4** | Evaluation quality | Expected-concepts generation, dual-pass scoring, divergence check, human-review queue. |
| **5** | Integrity & reports | Paste/timing signals, per-topic aggregation, PDF report. |
| **6** | Harden & ship | Load test, chaos test (kill a worker mid-task), CI, README, live deploy. |

Phase 2 is the one people skip and the one that matters most.

---

## 10. Tests Worth Writing

- FSM: every illegal transition raises. Table-driven.
- Idempotency: submitting the same answer twice creates one `Answer` row.
- Malformed LLM output: unparseable JSON → repair → dead-letter, session lands in `FAILED`, not stuck.
- **Chaos:** `docker kill` a worker mid-evaluation; assert the session recovers on retry
  and no double-scoring occurs.
- Cost: a session cannot exceed its token budget, verified against the `LLMCall` ledger.

The chaos test is the one to mention in an interview.

---

## 11. README Must Contain

1. Architecture diagram + the state machine.
2. **"Tradeoffs I made"** — 5 bullets, each naming what you rejected and why.
3. Reproducibility note: how scoring is kept stable, with numbers if you have them.
4. Cost per interview, measured.
5. A live Swagger link.

A project nobody can click is half a project.
