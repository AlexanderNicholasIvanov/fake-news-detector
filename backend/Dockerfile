FROM python:3.12-slim

# uv: fast, lockfile-driven dependency management.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install deps first for layer caching. Copy lockfile if present.
COPY pyproject.toml ./
COPY uv.lock* ./
RUN uv sync --no-install-project

# App source
COPY . .
RUN uv sync

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000

# Apply migrations, then serve.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
