"""Content credibility scoring via a local LLM (Ollama native /api/chat)."""

from __future__ import annotations

import json

import httpx

from app.config import settings
from app.scoring.prompt import CONTENT_SCHEMA, SYSTEM_PROMPT, TOPICS, build_user_prompt
from app.scoring.settings import MODEL

REQUEST_TIMEOUT = 180.0


async def score_content(
    client: httpx.AsyncClient, title: str | None, text: str | None
) -> dict | None:
    """Call the local model and return {content_subscore, red_flags, rationale},
    or None if the response can't be parsed. `format` constrains output to the
    schema; `think=False` disables qwen3's reasoning block for clean JSON."""
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(title, text)},
        ],
        "stream": False,
        "think": False,
        "format": CONTENT_SCHEMA,
        "options": {"temperature": 0, "num_ctx": 8192},
    }
    resp = await client.post(
        f"{settings.ollama_base_url}/api/chat", json=payload, timeout=REQUEST_TIMEOUT
    )
    resp.raise_for_status()
    content = resp.json().get("message", {}).get("content", "")
    try:
        obj = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return None

    subscore = obj.get("content_subscore")
    if not isinstance(subscore, int):
        return None
    topic = obj.get("topic")
    return {
        "content_subscore": max(0, min(100, subscore)),
        "red_flags": obj.get("red_flags") or [],
        "rationale": (obj.get("rationale") or "").strip(),
        "topic": topic if topic in TOPICS else "other",
    }
