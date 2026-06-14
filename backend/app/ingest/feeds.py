"""Feed loading, URL canonicalization, and new-article discovery."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import feedparser
import yaml
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Article, Source

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"
FEEDS_FILE = CONFIG_DIR / "feeds.yaml"

# Query params dropped during canonicalization (tracking / analytics noise).
_TRACKING_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid", "igshid", "ref", "ref_src"}


def canonicalize_url(url: str) -> str:
    """Normalize a URL for dedup: lowercase host, drop fragment + tracking params,
    strip a trailing slash from the path."""
    p = urlparse(url.strip())
    query = [
        (k, v)
        for k, v in parse_qsl(p.query, keep_blank_values=False)
        if not k.lower().startswith("utm_") and k.lower() not in _TRACKING_KEYS
    ]
    path = p.path.rstrip("/") or "/"
    return urlunparse((p.scheme.lower(), p.netloc.lower(), path, "", urlencode(query), ""))


def _entry_published(entry) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    return datetime(*parsed[:6], tzinfo=timezone.utc)


def parse_feed(feed_url: str) -> list[dict]:
    """Fetch + parse a feed. Returns one dict per entry with url/title/published.
    Network errors are swallowed into an empty list (logged by the caller)."""
    parsed = feedparser.parse(feed_url)
    entries: list[dict] = []
    for entry in parsed.entries:
        link = entry.get("link")
        if not link:
            continue
        entries.append(
            {
                "url": link.strip(),
                "title": (entry.get("title") or "").strip() or None,
                "published_at": _entry_published(entry),
            }
        )
    return entries


def load_sources(session: Session, feeds_file: Path = FEEDS_FILE) -> int:
    """Upsert feeds.yaml into the `sources` table (matched by feed_url). Returns
    the number of sources now active."""
    data = yaml.safe_load(feeds_file.read_text(encoding="utf-8")) or {}
    feeds = data.get("feeds") or []
    existing = {s.feed_url: s for s in session.scalars(select(Source))}
    for f in feeds:
        src = existing.get(f["feed_url"])
        if src is None:
            session.add(
                Source(
                    name=f["name"],
                    feed_url=f["feed_url"],
                    homepage=f.get("homepage"),
                    reputation_tier=f.get("tier", "unknown"),
                    active=True,
                )
            )
        else:
            # Keep tier/name in sync with the config file.
            src.name = f["name"]
            src.reputation_tier = f.get("tier", "unknown")
            src.homepage = f.get("homepage")
    session.commit()
    active = session.scalar(
        select(func.count()).select_from(Source).where(Source.active.is_(True))
    )
    return active or 0


def discover_new_articles(session: Session) -> int:
    """Poll every active source and insert newly-seen articles (status=pending).
    Dedups on canonical URL. Returns the count of new articles inserted."""
    sources = list(session.scalars(select(Source).where(Source.active.is_(True))))
    # Canonical URLs already added this cycle but not yet visible to a DB query
    # (autoflush is off), plus a guard against the same URL appearing across feeds.
    seen: set[str] = set()
    inserted = 0
    for source in sources:
        try:
            entries = parse_feed(source.feed_url)
        except Exception as exc:  # one bad feed must not stop the rest
            print(f"[discover] feed error {source.feed_url}: {exc}", flush=True)
            continue

        new_for_source = 0
        for entry in entries:
            canonical = canonicalize_url(entry["url"])
            if canonical in seen:
                continue
            exists = session.scalar(
                select(Article.id).where(Article.url_canonical == canonical).limit(1)
            )
            if exists:
                seen.add(canonical)
                continue
            seen.add(canonical)
            session.add(
                Article(
                    source_id=source.id,
                    url=entry["url"],
                    url_canonical=canonical,
                    title=entry["title"],
                    published_at=entry["published_at"],
                    extraction_status="pending",
                )
            )
            new_for_source += 1

        try:
            session.commit()
            inserted += new_for_source
        except Exception as exc:  # isolate a bad source; keep the rest of the cycle
            session.rollback()
            print(f"[discover] commit error {source.feed_url}: {exc}", flush=True)
    return inserted
