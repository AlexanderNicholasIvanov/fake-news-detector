"""Full-text extraction: fetch the article page and pull clean body text."""

from __future__ import annotations

import asyncio
import hashlib

import httpx
import trafilatura

# Some publishers (e.g. NPR) silently hang or block an obviously-bot User-Agent,
# so present as a mainstream desktop browser. This is a public-page GET, not
# evasion of auth or paywalls — it just avoids naive bot filters.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
FETCH_TIMEOUT = 20.0


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _extract(html: str, url: str) -> str | None:
    """Run trafilatura on already-fetched HTML (sync; called via a thread)."""
    return trafilatura.extract(
        html,
        url=url,
        include_comments=False,
        include_tables=False,
        favor_recall=True,
    )


async def fetch_and_extract(client: httpx.AsyncClient, url: str) -> str | None:
    """Fetch a URL and return clean article text, or None on any failure."""
    resp = await client.get(url, follow_redirects=True, timeout=FETCH_TIMEOUT)
    resp.raise_for_status()
    return await asyncio.to_thread(_extract, resp.text, url)


async def extract_many(
    items: list[tuple[int, str]], concurrency: int = 6
) -> list[dict]:
    """Concurrently fetch+extract a list of (article_id, url). Returns a result
    dict per item: {id, status, full_text, content_hash}. Failures are isolated."""
    semaphore = asyncio.Semaphore(concurrency)
    headers = {"User-Agent": USER_AGENT}

    async with httpx.AsyncClient(headers=headers) as client:

        async def one(article_id: int, url: str) -> dict:
            async with semaphore:
                try:
                    text = await fetch_and_extract(client, url)
                except Exception as exc:
                    print(f"[extract] fetch error id={article_id} {url}: {exc}", flush=True)
                    return {"id": article_id, "status": "failed", "full_text": None, "content_hash": None}
            if not text:
                return {"id": article_id, "status": "failed", "full_text": None, "content_hash": None}
            return {
                "id": article_id,
                "status": "ok",
                "full_text": text,
                "content_hash": content_hash(text),
            }

        return await asyncio.gather(*(one(aid, url) for aid, url in items))
