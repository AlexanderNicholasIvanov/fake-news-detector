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

    # Scoring (M2+) — max articles scored per cycle (LLM calls are sequential).
    # Sized to drain ingestion backlogs faster; a cycle that runs longer than the
    # poll interval just means the next poll is skipped (APScheduler max_instances=1),
    # so scoring runs effectively back-to-back. Override via SCORE_BATCH_SIZE.
    score_batch_size: int = 50


settings = Settings()
