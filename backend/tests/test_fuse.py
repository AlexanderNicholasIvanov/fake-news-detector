"""Fusion + band-mapping unit tests (no LLM/DB)."""

import pytest

from app.scoring.fuse import band_for, fuse


@pytest.mark.parametrize(
    ("score", "band"),
    [(100, "credible"), (70, "credible"), (69, "questionable"),
     (40, "questionable"), (39, "misleading"), (0, "misleading")],
)
def test_band_for(score: int, band: str) -> None:
    assert band_for(score) == band


def test_fuse_blends_with_default_weights() -> None:
    # default weights 0.6 content / 0.4 reputation, corroboration excluded
    final, band = fuse(content_subscore=80, reputation_subscore=85)
    assert final == 82  # round(0.6*80 + 0.4*85)
    assert band == "credible"


def test_fuse_low_content_trusted_source_is_dragged_down() -> None:
    # sensational article from a trusted outlet: content dominates the blend
    final, _ = fuse(content_subscore=20, reputation_subscore=85)
    assert final == 46  # round(0.6*20 + 0.4*85) = 46


def test_fuse_clamps_to_0_100() -> None:
    assert fuse(100, 100)[0] == 100
    assert fuse(0, 0)[0] == 0


def test_fuse_uncorroborated_matches_legacy_6040_blend() -> None:
    # No-regression guard: with corroboration absent, the content:reputation
    # weights (0.51:0.34) renormalize to exactly 0.6:0.4, so uncorroborated
    # articles score identically to the MVP — keeps the eval/audit valid.
    assert fuse(80, 85)[0] == 82          # round(0.6*80 + 0.4*85)
    assert fuse(95, 25)[0] == 67          # clean content, questionable source


def test_fuse_corroboration_is_applied_when_present() -> None:
    # Phase 2 weights 0.51/0.34/0.15. Corroboration is a positive-only signal.
    final, _ = fuse(80, 85, corroboration_subscore=50)
    assert final == 77  # round(0.51*80 + 0.34*85 + 0.15*50)


def test_fuse_corroboration_lifts_a_borderline_score() -> None:
    base = fuse(50, 25)[0]                          # uncorroborated → 40 (misleading)
    lifted = fuse(50, 25, corroboration_subscore=84)[0]  # widely corroborated
    assert lifted > base and lifted >= 40
