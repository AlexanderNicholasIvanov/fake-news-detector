"""Application settings, loaded from environment (.env)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://fnd:fnd_dev_password@localhost:5432/fakenews"

    # Ollama / scoring (M2+). Named *_BASE_URL to avoid colliding with Ollama's
    # own OLLAMA_HOST env var (which sets the server's bind address on the host).
    ollama_base_url: str = "http://host.docker.internal:11434"
    scoring_model: str = "qwen3:14b"

    # Worker (M1+)
    poll_interval_minutes: int = 10

    # Scoring (M2+) — max articles scored per cycle (LLM calls are sequential)
    score_batch_size: int = 25


settings = Settings()
