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

    The base is a content/reputation mix (weights renormalized so they sum to 1,
    independent of the configured corroboration weight — the MVP 0.6/0.4 blend).

    Corroboration is **positive-only**: it can LIFT the score but never lower it.
    When absent it is excluded (base only); when present we take the max of the
    base and the corroboration-weighted blend, so a thinly-corroborated article
    whose content+reputation already scored higher is not dragged down.
    """
    wc = WEIGHTS.get("content", 0.6)
    wr = WEIGHTS.get("reputation", 0.4)
    wk = WEIGHTS.get("corroboration", 0.0)

    base = (wc * content_subscore + wr * reputation_subscore) / (wc + wr) if (wc + wr) else 0.0
    final = base
    if corroboration_subscore is not None and (wc + wr + wk):
        with_corro = (
            wc * content_subscore + wr * reputation_subscore + wk * corroboration_subscore
        ) / (wc + wr + wk)
        final = max(base, with_corro)  # lift-only: never below the base blend

    final = max(0, min(100, round(final)))
    return final, band_for(final)
