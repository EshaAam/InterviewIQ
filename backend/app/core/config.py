"""Application settings.

Everything configurable lives here and comes from the environment.
No module anywhere else in the app reads os.environ directly.
"""

from functools import lru_cache
from typing import Literal

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # --- Postgres ---
    POSTGRES_USER: str = "interviewiq"
    POSTGRES_PASSWORD: str = "interviewiq"
    POSTGRES_DB: str = "interviewiq"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432

    # --- Redis / Celery ---
    REDIS_URL: str = "redis://localhost:6379/0"
    # Broker and result backend default to the same Redis; override if needed.
    CELERY_BROKER_URL: str = ""
    CELERY_RESULT_BACKEND: str = ""

    # --- LLM provider ---
    LLM_PROVIDER: Literal["fake", "gemini", "ollama"] = "fake"
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

    # --- LLM resilience wrappers (design spec §5) ---
    LLM_CACHE_TTL_SECONDS: int = 86_400
    LLM_RETRY_MAX_ATTEMPTS: int = 2  # attempts *after* the first try
    LLM_RETRY_BASE_DELAY_SECONDS: float = 0.2
    LLM_BREAKER_THRESHOLD: int = 5  # consecutive transient failures -> open
    LLM_BREAKER_RESET_SECONDS: float = 30.0

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
        return (
            f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @computed_field
    @property
    def DATABASE_URL_ASYNC(self) -> str:
        """Async DSN — used by the application's request path."""
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


@lru_cache
def get_settings() -> Settings:
    """Cached so the env is parsed once per process."""
    return Settings()


settings = get_settings()
