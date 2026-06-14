"""Reputation sub-score unit tests (no LLM/DB)."""

from app.scoring.reputation import domain_of, reputation_subscore
from app.scoring.settings import REPUTATION_SUBSCORES


def test_domain_strips_www() -> None:
    assert domain_of("https://www.bbc.com/news/x") == "bbc.com"
    assert domain_of("https://nypost.com/a") == "nypost.com"


def test_tier_maps_to_configured_subscore() -> None:
    assert reputation_subscore("trusted")[0] == REPUTATION_SUBSCORES["trusted"]
    assert reputation_subscore("questionable")[0] == REPUTATION_SUBSCORES["questionable"]


def test_unknown_tier_falls_back() -> None:
    score, tier = reputation_subscore("does-not-exist")
    assert score == REPUTATION_SUBSCORES["unknown"]
    assert tier == "does-not-exist"
