"""Unit tests for the pure corroboration logic (token overlap + subscore)."""

from app.scoring.corroboration import (
    _merge_candidates,
    corroboration_subscore,
    jaccard,
    significant_tokens,
)


def test_significant_tokens_drops_stopwords_and_short_words():
    toks = significant_tokens("The Fed holds rates at a high", None)
    assert "holds" in toks and "rates" in toks and "high" in toks
    # stopwords / short words excluded
    assert "the" not in toks and "at" not in toks and "a" not in toks


def test_significant_tokens_merges_title_and_lead():
    toks = significant_tokens("Central bank decision", "inflation cooled sharply")
    assert {"central", "bank", "decision", "inflation", "cooled", "sharply"} <= toks


def test_jaccard_basic():
    assert jaccard(set(), {"a"}) == 0.0
    assert jaccard({"a", "b"}, {"a", "b"}) == 1.0
    # |inter|=1, |union|=3
    assert abs(jaccard({"a", "b"}, {"b", "c"}) - 1 / 3) < 1e-9


def test_same_event_headlines_overlap_above_floor():
    a = significant_tokens("Central bank holds interest rates steady", "")
    b = significant_tokens("Federal Reserve keeps interest rates unchanged", "")
    # shares 'interest' + 'rates' — enough to clear the 0.10 candidate floor
    assert jaccard(a, b) >= 0.10


def test_unrelated_headlines_below_floor():
    a = significant_tokens("Local library expands weekend hours", "")
    b = significant_tokens("Striker signs record transfer deal", "")
    assert jaccard(a, b) < 0.10


def test_subscore_none_when_no_corroboration():
    assert corroboration_subscore([]) == (None, None)


def test_subscore_scales_with_distinct_sources():
    s1, _ = corroboration_subscore(["questionable"])
    s2, _ = corroboration_subscore(["questionable", "unknown"])
    s3, _ = corroboration_subscore(["questionable", "unknown", "questionable"])
    assert s1 == 62 and s2 == 74 and s3 == 84


def test_subscore_caps_distinct_sources():
    s4, info = corroboration_subscore(["unknown"] * 4)
    assert s4 == 84 and info["distinct_sources"] == 4  # 4+ uses the 3-source value


def test_trusted_corroborator_adds_bonus():
    score, info = corroboration_subscore(["trusted"])
    assert score == 70 and info["any_trusted"] is True  # 62 + 8 bonus


def test_subscore_clamped_to_100():
    score, _ = corroboration_subscore(["trusted", "trusted", "trusted"])
    assert score == 92  # 84 + 8, still under 100


def _cand(i: int, **extra) -> dict:
    return {"id": i, "title": f"t{i}", "lead": "", "source_id": i, "tier": "unknown", **extra}


def test_merge_union_dedups_preferring_lexical():
    lexical = [_cand(1, overlap=0.5)]
    vector = [_cand(1, similarity=0.9), _cand(2, similarity=0.8)]
    merged = _merge_candidates(lexical, vector)
    ids = [c["id"] for c in merged]
    assert ids == [1, 2]  # id=1 unioned once
    by_id = {c["id"]: c for c in merged}
    assert "overlap" in by_id[1] and "similarity" not in by_id[1]  # lexical entry wins
    assert "similarity" in by_id[2]  # vector-only candidate retained


def test_merge_caps_at_max_candidates():
    lexical = [_cand(i, overlap=0.2) for i in range(6)]
    vector = [_cand(i, similarity=0.7) for i in range(6, 14)]
    merged = _merge_candidates(lexical, vector)
    assert len(merged) == 8  # max_candidates floor; lexical-first ordering preserved
    assert [c["id"] for c in merged] == list(range(8))
