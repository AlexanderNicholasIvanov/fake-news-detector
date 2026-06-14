"""Load scoring + reputation config from YAML (config/scoring.yaml, reputation.yaml)."""

from pathlib import Path

import yaml

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


def _load(name: str) -> dict:
    return yaml.safe_load((CONFIG_DIR / name).read_text(encoding="utf-8")) or {}


_scoring = _load("scoring.yaml")
_reputation = _load("reputation.yaml")

MODEL: str = _scoring.get("model", "qwen3:14b")
WEIGHTS: dict = _scoring.get(
    "weights", {"content": 0.6, "reputation": 0.4, "corroboration": 0.0}
)
BANDS: dict = _scoring.get("bands", {"credible": 70, "questionable": 40})
REPUTATION_SUBSCORES: dict = _scoring.get(
    "reputation_subscores", {"trusted": 85, "unknown": 50, "questionable": 25}
)
DOMAIN_OVERRIDES: dict = _reputation.get("overrides", {}) or {}
