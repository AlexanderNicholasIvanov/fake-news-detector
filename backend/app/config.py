"""Application settings, loaded from environment (.env)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://fnd:fnd_dev_password@localhost:5432/fakenews"

    # Ollama / scoring (M2+). Named *_BASE_URL to avoid colliding with Ollama's
    # own OLLAMA_HOST env var (which sets the server's bind address on the host).
    # Native run: Ollama is on the same host, so plain localhost.
    ollama_base_url: str = "http://localhost:11434"
    scoring_model: str = "qwen3:14b"
    # How long Ollama keeps a model resident after a request. The default (5m)
    # is shorter than the poll interval, so models unload + reload every cycle
    # (qwen3:14b is ~9.3 GB). Keep them warm between cycles. "-1" = never unload.
    ollama_keep_alive: str = "30m"

    # Worker (M1+)
    poll_interval_minutes: int = 10

    # Scoring (M2+) — max articles graded per query before re-checking (LLM calls
    # are sequential; each article commits as it is graded). The grading loop runs
    # these back-to-back to drain a backlog. Override via SCORE_BATCH_SIZE.
    score_batch_size: int = 50

    # Fraction of each grading batch spent on the OLDEST unscored articles; the rest
    # are graded newest-first. > 0 keeps freshly ingested news scored promptly while
    # still draining any backlog so nothing is permanently starved. 0 = strict
    # newest-first (recent always first, but an old backlog can be starved).
    score_backlog_share: float = 0.25

    # Worker grading loop. Grading begins only after the API is serving, so the
    # dashboard "loads first"; then unscored articles are graded continuously.
    api_health_url: str = "http://localhost:8000/health"
    grade_start_after_api_seconds: int = 120  # max wait for the app to load before grading
    grade_idle_seconds: int = 30  # when the backlog is clear, recheck this often


settings = Settings()
