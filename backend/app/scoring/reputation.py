"""Source-reputation sub-score: maps a reputation tier (with optional per-domain
override) to a 0–100 sub-score."""

from __future__ import annotations

from urllib.parse import urlparse

from app.scoring.settings import DOMAIN_OVERRIDES, REPUTATION_SUBSCORES


def domain_of(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def reputation_subscore(source_tier: str, url: str | None = None) -> tuple[int, str]:
    """Return (sub-score, effective_tier). A per-domain override in
    reputation.yaml takes precedence over the source's configured tier."""
    tier = source_tier
    if url:
        override = DOMAIN_OVERRIDES.get(domain_of(url))
        if override:
            tier = override
    default = REPUTATION_SUBSCORES.get("unknown", 50)
    return REPUTATION_SUBSCORES.get(tier, default), tier
