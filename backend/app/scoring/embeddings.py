"""Dense embeddings for corroboration recall.

Embeds an article's `title + lead` via the host Ollama (`/api/embed`) and stores
the vector in `article_embeddings`. The vector side of the hybrid candidate
filter (see `corroboration.find_candidates`) does cosine-nearest-neighbour search
over these, so paraphrased coverage of the same event — which the lexical
token-overlap filter misses — still surfaces as a candidate.

All calls are failure-tolerant: an embedding error returns None and the caller
falls back to lexical-only recall. The signal is purely additive.
"""

from __future__ import annotations

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import ArticleEmbedding
from app.scoring.settings import CORROBORATION

REQUEST_TIMEOUT = 60.0

EMBED_MODEL: str = CORROBORATION.get("embedding_model", "nomic-embed-text")
EMBED_DIM: int = int(CORROBORATION.get("embedding_dim", 768))
_LEAD_CHARS: int = int(CORROBORATION.get("lead_chars", 300))


def embed_text(title: str | None, full_text: str | None) -> str:
    """The text embedded for matching: title + the same lead the lexical filter uses."""
    lead = (full_text or "")[:_LEAD_CHARS].strip()
    return f"{title or ''}\n{lead}".strip()


async def embed(client: httpx.AsyncClient, text: str) -> list[float] | None:
    """Embed `text` via Ollama. Returns the vector, or None on failure/empty input."""
    if not text:
        return None
    payload = {"model": EMBED_MODEL, "input": text}
    try:
        resp = await client.post(
            f"{settings.ollama_base_url}/api/embed", json=payload, timeout=REQUEST_TIMEOUT
        )
        resp.raise_for_status()
        vectors = resp.json().get("embeddings") or []
    except (httpx.HTTPError, ValueError):
        return None
    if not vectors or not isinstance(vectors[0], list):
        return None
    vec = vectors[0]
    return vec if len(vec) == EMBED_DIM else None


def store_embedding(session: Session, article_id: int, vec: list[float]) -> None:
    """Upsert the embedding for `article_id` (1:1). Commits."""
    existing = session.get(ArticleEmbedding, article_id)
    if existing is None:
        session.add(
            ArticleEmbedding(
                article_id=article_id, model=EMBED_MODEL, dim=EMBED_DIM, embedding=vec
            )
        )
    else:
        existing.model = EMBED_MODEL
        existing.dim = EMBED_DIM
        existing.embedding = vec
    session.commit()


def has_embedding(session: Session, article_id: int) -> bool:
    return session.scalar(
        select(ArticleEmbedding.article_id).where(
            ArticleEmbedding.article_id == article_id
        )
    ) is not None
