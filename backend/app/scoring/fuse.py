"""Fuse component sub-scores into a final credibility score + display band."""

from __future__ import annotations

from app.scoring.settings import BANDS, WEIGHTS


def band_for(score: int) -> str:
    if score >= BANDS.get("credible", 70):
        return "credible"
    if score >= BANDS.get("questionable", 40):
        return "questionable"
    return "misleading"


def fuse(
    content_subscore: int,
    reputation_subscore: int,
    corroboration_subscore: int | None = None,
) -> tuple[int, str]:
    """Weighted blend of the component sub-scores → (final_score, band).

    Corroboration is a Phase-2 placeholder: when it's None its weight is
    excluded and the remaining weights are renormalized, so the MVP blend is a
    clean content/reputation mix regardless of the configured corroboration weight.
    """
    wc = WEIGHTS.get("content", 0.6)
    wr = WEIGHTS.get("reputation", 0.4)
    wk = WEIGHTS.get("corroboration", 0.0)

    raw = wc * content_subscore + wr * reputation_subscore
    total = wc + wr
    if corroboration_subscore is not None:
        raw += wk * corroboration_subscore
        total += wk

    final = round(raw / total) if total else 0
    final = max(0, min(100, final))
    return final, band_for(final)
