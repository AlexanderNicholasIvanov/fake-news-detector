"""Application settings, loaded from environment (.env)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://fnd:fnd_dev_password@localhost:5432/fakenews"

    # Ollama / scoring (M2+)
    ollama_host: str = "http://host.docker.internal:11434"
    scoring_model: str = "qwen3:14b"

    # Worker (M1+)
    poll_interval_minutes: int = 10


settings = Settings()
