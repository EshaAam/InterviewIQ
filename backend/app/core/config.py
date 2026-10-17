"""Application settings.

Everything configurable lives here and comes from the environment.
No module anywhere else in the app reads os.environ directly.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Values shipped in code or in .env.example — never acceptable as a real key.
_PLACEHOLDER_SECRETS = {"change-me", "change-me-to-a-long-random-string"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- App ---
    PROJECT_NAME: str = "InterviewIQ"
    API_V1_PREFIX: str = "/api/v1"
    ENVIRONMENT: Literal["local", "staging", "production"] = "local"
    DEBUG: bool = False
    SECRET_KEY: str = "change-me"
    # Browser origins allowed to call the API, comma-separated.
    CORS_ORIGINS: str = "http://localhost:3000"

    # --- Postgres ---
    POSTGRES_USER: str = "interviewiq"
    POSTGRES_PASSWORD: str = "interviewiq"
    POSTGRES_DB: str = "interviewiq"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    # Empty for the compose stack's own Postgres. Hosted Postgres (Neon,
    # Supabase) refuses plain connections: set `require`.
    POSTGRES_SSLMODE: str = ""

    # --- Redis / Celery ---
    REDIS_URL: str = "redis://localhost:6379/0"
    # Broker and result backend default to the same Redis; override if needed.
    CELERY_BROKER_URL: str = ""
    CELERY_RESULT_BACKEND: str = ""

    # --- LLM provider ---
    LLM_PROVIDER: Literal["fake", "gemini", "ollama"] = "fake"
    # Load tests / chaos drills only: make the fake provider take this long per
    # call, so the queue sees model-like latency instead of instant answers.
    FAKE_LATENCY_MS: int = 0
    # Single key, or a comma-separated pool for free-tier rotation. Both are
    # merged by `gemini_keys`; put keys in .env, never in code.
    GEMINI_API_KEY: str = ""
    GEMINI_API_KEYS: str = ""
    # These aliases have free-tier quota; gemini-2.0-flash / text-embedding-004
    # report limit:0 on free keys, so default to the ones that work.
    GEMINI_MODEL: str = "gemini-flash-latest"
    GEMINI_EMBED_MODEL: str = "gemini-embedding-001"
    # How long a key is benched after it returns a rate-limit (429).
    GEMINI_KEY_COOLDOWN_SECONDS: float = 60.0
    # Tried in order when a model answers 503 "high demand". Overload is per
    # model, not per key — one model can shed load for hours while another
    # answers in two seconds — and free-tier quota is per model too.
    # Comma-separated; empty means no fallback.
    GEMINI_FALLBACK_MODELS: str = ""
    # How long an overloaded model is tried last rather than first.
    GEMINI_OVERLOAD_COOLDOWN_SECONDS: float = 60.0
    # Longest a single Gemini request may take before it counts as a transient
    # failure (and is retried). The SDK's default is to wait forever.
    GEMINI_TIMEOUT_SECONDS: float = 60.0

    # --- Embeddings (RAG Phase 1) ---
    # Separate from LLM_PROVIDER: the knowledge base is embedded once and every
    # retrieval embeds a query, which is a different cost profile from
    # generation and wants a local model even when generation stays hosted.
    #   auto   - what the app did before this seam: hash on the fake provider,
    #            Gemini otherwise. Changes no behaviour.
    #   hash   - deterministic bag-of-words; offline, used by the test suite.
    #   local  - bge-small via fastembed; free, offline, semantic. Recommended.
    #   gemini - the hosted embedding endpoint (the previous behaviour).
    EMBEDDING_PROVIDER: Literal["auto", "hash", "local", "gemini"] = "auto"
    EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"
    # Must match the width of the pgvector column the chunks are stored in.
    EMBEDDING_DIM: int = 384
    # Where fastembed keeps downloaded models. The image pre-populates this so a
    # worker never fetches a model mid-job; empty uses fastembed's default.
    EMBEDDING_CACHE_DIR: str = ""
    # 0 lets onnxruntime choose. Pin it low if several workers share a box.
    EMBEDDING_THREADS: int = 0
    # The hashing stand-in's width. Test assertions depend on 64 — don't change.
    EMBEDDING_HASH_DIM: int = 64
    # gemini-embedding-001's native width, used only to size a vector column.
    GEMINI_EMBED_DIM: int = 3072

    # --- LLM resilience wrappers (design spec §5) ---
    LLM_CACHE_TTL_SECONDS: int = 86_400
    LLM_RETRY_MAX_ATTEMPTS: int = 2  # attempts *after* the first try
    LLM_RETRY_BASE_DELAY_SECONDS: float = 0.2
    LLM_BREAKER_THRESHOLD: int = 5  # consecutive transient failures -> open
    LLM_BREAKER_RESET_SECONDS: float = 30.0

    # --- RAG retrieval (Phase 3) and grounded generation (Phase 4) ---
    # Off by default: the whole point of the flag is that the previous,
    # ungrounded behaviour stays one switch away for before/after comparison.
    RAG_ENABLED: bool = False
    # Passages handed to the prompt per extracted skill.
    RAG_TOP_K: int = 4
    # Candidates pulled from each retriever before fusion. Larger costs little
    # (both are index lookups) and gives RRF more to work with.
    RAG_CANDIDATES: int = 20
    # Below this cosine a skill counts as *not covered* and the question falls
    # back to ungrounded. Calibrated on the retrieval golden set plus 14
    # deliberately uncovered queries (Kubernetes, Kafka, sourdough), not guessed:
    #
    #   floor   keeps a good retrieval   grounds an uncovered query
    #   0.55            58/58                     11/14
    #   0.65            53/58                      4/14
    #   0.68            48/58                      0/14
    #
    # 0.68 because the errors are not symmetric. Discarding a good retrieval
    # costs one grounding opportunity and falls back to the pre-RAG behaviour.
    # Admitting an uncovered one builds an answer key from unrelated passages
    # and attaches a citation that actively misleads a reviewer - the exact
    # failure this whole effort exists to prevent. Re-run
    # `python -m app.cli eval-retrieval` after any embedder or corpus change.
    RAG_MIN_SIMILARITY: float = 0.68
    # Hard cap on retrieved context per generation. Grounded prompts are longer
    # and the free tier is rate-limited by tokens, so this is what stops a
    # ten-skill resume turning into one enormous request.
    RAG_CONTEXT_TOKEN_BUDGET: int = 2400

    # A job-description requirement counts as evidenced by the resume at or
    # above this cosine. Unlike RAG_MIN_SIMILARITY this is **not** calibrated
    # against a golden set - it is reasoned by analogy from the same
    # measurements (bge-small scores ~0.44 for unrelated text and 0.73+ for a
    # genuine match), so 0.65 sits in the same place in that distribution.
    # Calibrating it properly needs labelled (requirement, skill) pairs.
    JD_MATCH_THRESHOLD: float = 0.65

    # --- Cost & budget ---
    # Rough per-1K-token prices (USD); tune per model. Metered into LLMCall.
    LLM_PRICE_PROMPT_PER_1K: float = 0.000075
    LLM_PRICE_COMPLETION_PER_1K: float = 0.0003
    USER_DAILY_TOKEN_BUDGET: int = 200_000

    # --- Auth ---
    # Access tokens are short-lived; refresh tokens carry the session.
    ACCESS_TOKEN_TTL_MINUTES: int = 15
    REFRESH_TOKEN_TTL_DAYS: int = 30
    JWT_ALGORITHM: str = "HS256"

    # --- Interview ---
    # Server-authoritative interview deadline, set when a session starts.
    SESSION_TTL_MINUTES: int = 60

    # --- Evaluation (dual-pass reconcile, design spec §4) ---
    # A concept counts as covered when answer/concept cosine >= this.
    EVAL_COVERAGE_THRESHOLD: float = 0.55
    # If |llm_score - deterministic_score| exceeds this, the two passes diverge.
    EVAL_DIVERGENCE_THRESHOLD: float = 0.35
    # Extra LLM runs (at a nonzero temperature) to confirm a divergence.
    EVAL_RERUN_COUNT: int = 2
    EVAL_RERUN_TEMPERATURE: float = 0.4

    # --- Résumé upload (Phase 5) ---
    # Where original files are kept (LocalFileStorage). Compose mounts a volume here.
    UPLOAD_DIR: str = "uploads"
    RESUME_MAX_BYTES: int = 2 * 1024 * 1024
    # Less extracted text than this means the file had no usable text layer
    # (typically a scanned PDF) — reject it and ask for a paste instead.
    RESUME_MIN_TEXT_CHARS: int = 40

    # --- Voice answers (local speech-to-text) ---
    # Off by default, and needs the optional `voice` extra (faster-whisper). With
    # it off, or the package missing, the feature simply is not offered: the API
    # reports `voice_answers: false` and the interview page shows no microphone.
    VOICE_ENABLED: bool = False
    # base.en: ~145 MB, transcribes ~10x faster than real time on a laptop CPU
    # with int8. small.en is more accurate and ~3x slower.
    WHISPER_MODEL: str = "base.en"
    WHISPER_COMPUTE_TYPE: str = "int8"
    # Where the model lives. The image pre-downloads it here so a request never
    # stalls on a 145 MB fetch; empty uses the Hugging Face default cache.
    WHISPER_CACHE_DIR: str = ""
    # 0 lets CTranslate2 choose. Pin it low if the API shares a small box.
    WHISPER_THREADS: int = 0
    VOICE_LANGUAGE: str = "en"
    # Per clip. An answer can be built from several clips.
    VOICE_MAX_SECONDS: int = 180
    VOICE_MAX_BYTES: int = 10 * 1024 * 1024
    # Transcription is CPU-bound and local; this caps how much of the API's CPU
    # one candidate can take, without spending anything.
    VOICE_MAX_CLIPS_PER_QUESTION: int = 10
    # Clips transcribed at once per process. More just makes each one slower.
    VOICE_CONCURRENCY: int = 1

    # --- Integrity signals (Phase 5, advisory only) ---
    # Answers shorter than this are never flagged: pasting `SELECT 1` isn't a signal.
    INTEGRITY_MIN_CHARS: int = 120
    # Flag when keystrokes account for less than this share of the characters.
    INTEGRITY_MIN_TYPED_SHARE: float = 0.4
    # Flag above this many characters per second over the whole answer time.
    # Fast typists sustain ~8; the time also includes reading the question.
    INTEGRITY_MAX_CHARS_PER_SECOND: float = 12.0

    # --- Pipeline reliability (Phase 6) ---
    # Celery retries for transient provider errors, with exponential backoff
    # starting at the base delay (30 s, 60 s, 120 s, ...).
    TASK_MAX_RETRIES: int = 4
    TASK_RETRY_BASE_SECONDS: int = 30
    # The reaper re-dispatches sessions stuck longer than these.
    REAPER_CREATED_AFTER_MINUTES: int = 10
    REAPER_EVALUATING_AFTER_MINUTES: int = 30
    # Who triggers the reaper. Normally the `beat` service (docker-compose). The
    # single-container Render image runs no beat: an embedded one (`worker -B`)
    # is a forked copy of the whole worker, whose private share grows as the
    # copy diverges — memory a 512 MB instance can't spare. There the API
    # enqueues the sweep itself (see app.main), one small Redis publish per
    # interval. Only with exactly one API process.
    REAPER_IN_API: bool = False
    REAPER_INTERVAL_SECONDS: float = 300.0
    # The first sweep comes sooner than the interval, so sessions stranded by
    # whatever restarted the container are picked up promptly.
    REAPER_FIRST_SWEEP_SECONDS: float = 60.0

    @model_validator(mode="after")
    def _refuse_weak_secret_outside_local(self) -> Settings:
        """Signing tokens with a guessable key means anyone can mint them.
        Locally that's fine; anywhere else, fail at startup, not in an incident."""
        weak = self.SECRET_KEY in _PLACEHOLDER_SECRETS or len(self.SECRET_KEY) < 32
        if self.ENVIRONMENT != "local" and weak:
            raise ValueError(
                "SECRET_KEY must be a random string of at least 32 characters outside "
                "ENVIRONMENT=local (e.g. `python -c \"import secrets; "
                "print(secrets.token_urlsafe(48))\"`)."
            )
        return self

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @computed_field
    @property
    def gemini_fallback_models(self) -> list[str]:
        return [m.strip() for m in self.GEMINI_FALLBACK_MODELS.split(",") if m.strip()]

    @computed_field
    @property
    def gemini_keys(self) -> list[str]:
        """All configured Gemini keys, de-duplicated, order preserved."""
        raw = [self.GEMINI_API_KEY, *self.GEMINI_API_KEYS.split(",")]
        seen: dict[str, None] = {}
        for key in (k.strip() for k in raw):
            if key:
                seen.setdefault(key, None)
        return list(seen)

    @computed_field
    @property
    def celery_broker(self) -> str:
        return self.CELERY_BROKER_URL or self.REDIS_URL

    @computed_field
    @property
    def celery_backend(self) -> str:
        return self.CELERY_RESULT_BACKEND or self.REDIS_URL

    @computed_field
    @property
    def DATABASE_URL(self) -> str:
        """Sync DSN — used by Alembic and the readiness probe."""
        url = (
            f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )
        return f"{url}?sslmode={self.POSTGRES_SSLMODE}" if self.POSTGRES_SSLMODE else url

    @computed_field
    @property
    def DATABASE_URL_ASYNC(self) -> str:
        """Async DSN — used by the application's request path."""
        url = (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )
        # asyncpg spells it `ssl`, not libpq's `sslmode`; the values are the same.
        return f"{url}?ssl={self.POSTGRES_SSLMODE}" if self.POSTGRES_SSLMODE else url


@lru_cache
def get_settings() -> Settings:
    """Cached so the env is parsed once per process."""
    return Settings()


settings = get_settings()
