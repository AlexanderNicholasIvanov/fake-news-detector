"""Phase 2 — cross-source corroboration.

A news event independently reported by several outlets (especially trusted ones)
is more credible than one that appears in a single low-reputation source and
nowhere else. This module finds other-source articles describing the SAME event
and turns that into a corroboration subscore.

Pipeline per article:
  1. lexical candidate filter  — cheap token-overlap over title+lead, in a time
     window, different source (no LLM; usually returns nothing → no LLM cost).
  2. LLM adjudication          — one structured call: "which candidates report the
     same event?" (only runs when step 1 found candidates).
  3. subscore                  — from the number of distinct corroborating sources,
     with a bonus if any is trusted.

The signal is POSITIVE-ONLY: zero corroboration returns None, which `fuse`
excludes from the blend, so an uncorroborated exclusive is never penalized.
"""

from __future__ import annotations

import json
import re
from datetime import timedelta

import httpx
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Article, ArticleEmbedding, Source
from app.scoring.embeddings import embed, embed_text
from app.scoring.settings import CORROBORATION, MODEL

REQUEST_TIMEOUT = 180.0

# Small, generic stopword set — enough to stop common words dominating overlap.
_STOPWORDS = frozenset(
    """the a an and or but of to in on for with from by at as is are was were be been
    being this that these those it its their his her our your they them we you he she
    will would could should may might can has have had do does did not no nor so than
    then there here over under into out up down off about after before during while
    new says said report reports according amid says year years day says week month""".split()
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def significant_tokens(title: str | None, lead: str | None) -> set[str]:
    """Lowercased alphanumeric tokens (len>=4, non-stopword) from title + lead."""
    blob = f"{title or ''} {lead or ''}".lower()
    return {
        t for t in _TOKEN_RE.findall(blob) if len(t) >= 4 and t not in _STOPWORDS
    }


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / len(a | b) if inter else 0.0


def corroboration_subscore(
    corroborating_tiers: list[str],
) -> tuple[int | None, dict | None]:
    """Map the tiers of distinct corroborating sources → (subscore, breakdown).

    `corroborating_tiers` has one entry per DISTINCT corroborating source. Empty
    → (None, None): no corroboration, excluded from the blend.
    """
    n = len(corroborating_tiers)
    if n == 0:
        return None, None

    table = CORROBORATION.get("subscore_by_sources", {"1": 62, "2": 74, "3": 84})
    max_key = max(int(k) for k in table)
    base = int(table[str(min(n, max_key))])

    any_trusted = "trusted" in corroborating_tiers
    bonus = int(CORROBORATION.get("trusted_bonus", 8)) if any_trusted else 0
    score = max(0, min(100, base + bonus))
    return score, {
        "distinct_sources": n,
        "any_trusted": any_trusted,
        "base": base,
        "trusted_bonus": bonus,
    }


def _lead(text: str | None) -> str:
    n = int(CORROBORATION.get("lead_chars", 300))
    return (text or "")[:n].strip()


def find_candidates(
    session: Session, article: dict
) -> list[dict]:
    """Other-source articles in the time window that lexically overlap `article`.

    `article` = {id, title, full_text, source_id, when} (when = published/created).
    Returns up to max_candidates dicts {id, title, lead, source_id, source_name,
    tier, overlap}, highest overlap first.
    """
    window = timedelta(hours=int(CORROBORATION.get("window_hours", 72)))
    min_overlap = float(CORROBORATION.get("min_overlap", 0.10))
    cap = int(CORROBORATION.get("max_candidates", 8))

    target_tokens = significant_tokens(article["title"], _lead(article["full_text"]))
    if len(target_tokens) < 3:  # too thin to match reliably
        return []

    when = article["when"]
    # coalesce(published_at, created_at) for the candidate's timestamp
    ts = func.coalesce(Article.published_at, Article.created_at)
    rows = session.execute(
        select(
            Article.id,
            Article.title,
            Article.full_text,
            Article.source_id,
            Source.name,
            Source.reputation_tier,
        )
        .join(Source, Source.id == Article.source_id)
        .where(
            Article.id != article["id"],
            Article.source_id != article["source_id"],
            Article.extraction_status == "ok",
            ts >= when - window,
            ts <= when + window,
        )
    ).all()

    scored = []
    for aid, title, full_text, source_id, source_name, tier in rows:
        toks = significant_tokens(title, _lead(full_text))
        ov = jaccard(target_tokens, toks)
        if ov >= min_overlap:
            scored.append(
                {
                    "id": aid,
                    "title": title,
                    "lead": _lead(full_text),
                    "source_id": source_id,
                    "source_name": source_name,
                    "tier": tier,
                    "overlap": round(ov, 3),
                }
            )
    scored.sort(key=lambda c: c["overlap"], reverse=True)
    return scored[:cap]


def _vector_candidates(
    session: Session, article: dict, target_vec: list[float]
) -> list[dict]:
    """Cosine nearest-neighbour candidates in the same window/other-source filter.

    Catches paraphrased coverage the lexical token-overlap filter misses. Same
    dict shape as `find_candidates`, with a `similarity` field instead of `overlap`.
    """
    window = timedelta(hours=int(CORROBORATION.get("window_hours", 72)))
    k = int(CORROBORATION.get("embedding_candidates", 8))
    min_sim = float(CORROBORATION.get("min_similarity", 0.55))

    when = article["when"]
    ts = func.coalesce(Article.published_at, Article.created_at)
    distance = ArticleEmbedding.embedding.cosine_distance(target_vec)
    rows = session.execute(
        select(
            Article.id,
            Article.title,
            Article.full_text,
            Article.source_id,
            Source.name,
            Source.reputation_tier,
            distance.label("dist"),
        )
        .join(Source, Source.id == Article.source_id)
        .join(ArticleEmbedding, ArticleEmbedding.article_id == Article.id)
        .where(
            Article.id != article["id"],
            Article.source_id != article["source_id"],
            Article.extraction_status == "ok",
            ts >= when - window,
            ts <= when + window,
        )
        .order_by(distance)
        .limit(k)
    ).all()

    out = []
    for aid, title, full_text, source_id, source_name, tier, dist in rows:
        sim = 1.0 - float(dist)
        if sim < min_sim:
            continue
        out.append(
            {
                "id": aid,
                "title": title,
                "lead": _lead(full_text),
                "source_id": source_id,
                "source_name": source_name,
                "tier": tier,
                "similarity": round(sim, 3),
            }
        )
    return out


def _merge_candidates(lexical: list[dict], vector: list[dict]) -> list[dict]:
    """Union by article id (lexical first), capped at max_candidates."""
    cap = int(CORROBORATION.get("max_candidates", 8))
    merged: dict[int, dict] = {}
    for c in (*lexical, *vector):
        merged.setdefault(c["id"], c)
    return list(merged.values())[:cap]


_ADJUDICATE_SYSTEM = """You decide whether news articles report the SAME underlying \
news event — the same who/what/when — as a TARGET article. Two articles report the \
same event if a reader would say "these are about the same thing that happened," even \
if the wording, framing, or outlet differs. Articles that merely share a topic or \
named person but describe DIFFERENT events do NOT match. Return only the ids of \
candidates that report the same event as the target."""

_MATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "matching_ids": {"type": "array", "items": {"type": "integer"}},
    },
    "required": ["matching_ids"],
}


def _build_adjudicate_prompt(article: dict, candidates: list[dict]) -> str:
    lines = [
        "TARGET ARTICLE:",
        f"  title: {article['title'] or '(no title)'}",
        f"  lead: {_lead(article['full_text'])}",
        "",
        "CANDIDATES (report the same event as the target?):",
    ]
    for c in candidates:
        lines.append(f"  [id={c['id']}] {c['title'] or '(no title)'} :: {c['lead']}")
    lines.append("")
    lines.append("Return matching_ids: the ids that report the SAME event as the target.")
    return "\n".join(lines)


async def _adjudicate(
    client: httpx.AsyncClient, article: dict, candidates: list[dict]
) -> set[int]:
    """Ask the LLM which candidate ids report the same event. Failure → empty set."""
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": _ADJUDICATE_SYSTEM},
            {"role": "user", "content": _build_adjudicate_prompt(article, candidates)},
        ],
        "stream": False,
        "think": False,
        "format": _MATCH_SCHEMA,
        "options": {"temperature": 0, "num_ctx": 8192},
    }
    resp = await client.post(
        f"{settings.ollama_base_url}/api/chat", json=payload, timeout=REQUEST_TIMEOUT
    )
    resp.raise_for_status()
    content = resp.json().get("message", {}).get("content", "")
    try:
        ids = json.loads(content).get("matching_ids", [])
    except (json.JSONDecodeError, TypeError, AttributeError):
        return set()
    valid = {c["id"] for c in candidates}
    return {int(i) for i in ids if isinstance(i, int) and i in valid}


async def score_corroboration(
    session: Session,
    client: httpx.AsyncClient,
    article: dict,
    target_vec: list[float] | None = None,
) -> tuple[int | None, dict | None]:
    """Full corroboration pass for one article.

    Candidates are the UNION of the lexical token-overlap filter and a cosine
    nearest-neighbour search over stored embeddings, so paraphrased coverage is
    not missed. `target_vec` (the article's embedding) is reused when the caller
    already computed it; otherwise it is embedded here. If embedding is
    unavailable, recall gracefully degrades to lexical-only.

    Returns (subscore, evidence) where subscore is None when nothing corroborates.
    evidence (when present) = {distinct_sources, any_trusted, matched:[...], ...}.
    """
    lexical = find_candidates(session, article)

    if target_vec is None:
        target_vec = await embed(client, embed_text(article["title"], article["full_text"]))
    vector = _vector_candidates(session, article, target_vec) if target_vec else []

    candidates = _merge_candidates(lexical, vector)
    if not candidates:
        return None, None

    matched_ids = await _adjudicate(client, article, candidates)
    matches = [c for c in candidates if c["id"] in matched_ids]
    if not matches:
        return None, None

    # One entry per DISTINCT corroborating source.
    by_source: dict[int, dict] = {}
    for m in matches:
        by_source.setdefault(m["source_id"], m)
    tiers = [m["tier"] for m in by_source.values()]

    subscore, breakdown = corroboration_subscore(tiers)
    if subscore is None:
        return None, None

    evidence = {
        **breakdown,
        "matched": [
            {
                "article_id": m["id"],
                "source_id": m["source_id"],
                "source_name": m["source_name"],
                "tier": m["tier"],
                "title": m["title"],
            }
            for m in matches
        ],
    }
    return subscore, evidence
