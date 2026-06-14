"""Offline evaluation harness for the credibility detector (M4).

Scores every case in golden_set.yaml through the real pipeline (content LLM +
reputation + fuse) and compares the predicted band to the expected band.

Run (inside the worker image, so host.docker.internal resolves to Ollama):
    docker compose run --rm -v "$PWD/backend/tests:/app/tests" worker \
        python tests/eval/run_eval.py

Exits non-zero if band accuracy falls below ACCURACY_THRESHOLD — use it as a
regression gate after changing the prompt, weights, or model.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import httpx
import yaml

from app.scoring.content import score_content
from app.scoring.fuse import fuse
from app.scoring.reputation import reputation_subscore
from app.scoring.settings import MODEL

GOLDEN_SET = Path(__file__).parent / "golden_set.yaml"
ACCURACY_THRESHOLD = 0.70
BANDS = ("credible", "questionable", "misleading")


async def _score_case(client: httpx.AsyncClient, case: dict) -> dict:
    content = await score_content(client, case.get("title"), case["text"])
    if content is None:
        return {**case, "ok": False}
    rep, _ = reputation_subscore(case["source_tier"])
    final, band = fuse(content["content_subscore"], rep)
    return {
        **case,
        "ok": True,
        "content_subscore": content["content_subscore"],
        "reputation_subscore": rep,
        "final_score": final,
        "predicted_band": band,
        "n_flags": len(content["red_flags"]),
        "pass": band == case["expected_band"],
    }


async def main() -> int:
    data = yaml.safe_load(GOLDEN_SET.read_text(encoding="utf-8"))
    cases = data["cases"]
    print(f"Evaluating {len(cases)} cases with model '{MODEL}'\n")

    results = []
    async with httpx.AsyncClient() as client:
        for case in cases:
            try:
                results.append(await _score_case(client, case))
            except Exception as exc:
                print(f"  ERROR {case['id']}: {exc}")
                results.append({**case, "ok": False})

    # Per-case table
    header = f"{'id':<34} {'tier':<12} {'cont':>4} {'fin':>4} {'flags':>5}  {'expected':<12} {'predicted':<12} result"
    print(header)
    print("-" * len(header))
    passed = 0
    confusion: dict[tuple[str, str], int] = {}
    scored = 0
    for r in results:
        if not r.get("ok"):
            print(f"{r['id']:<34} {r['source_tier']:<12} {'--':>4} {'--':>4} {'--':>5}  "
                  f"{r['expected_band']:<12} {'(no response)':<12} FAIL")
            continue
        scored += 1
        passed += r["pass"]
        confusion[(r["expected_band"], r["predicted_band"])] = (
            confusion.get((r["expected_band"], r["predicted_band"]), 0) + 1
        )
        mark = "PASS" if r["pass"] else "FAIL"
        print(f"{r['id']:<34} {r['source_tier']:<12} {r['content_subscore']:>4} "
              f"{r['final_score']:>4} {r['n_flags']:>5}  {r['expected_band']:<12} "
              f"{r['predicted_band']:<12} {mark}")

    total = len(results)
    accuracy = passed / total if total else 0.0

    # Confusion matrix (rows = expected, cols = predicted)
    print("\nConfusion matrix (rows = expected, cols = predicted):")
    print(f"{'':<14}" + "".join(f"{b:<14}" for b in BANDS))
    for exp in BANDS:
        row = "".join(f"{confusion.get((exp, pred), 0):<14}" for pred in BANDS)
        print(f"{exp:<14}{row}")

    print(f"\nBand accuracy: {passed}/{total} = {accuracy:.0%} "
          f"(threshold {ACCURACY_THRESHOLD:.0%})")
    if scored < total:
        print(f"WARNING: {total - scored} case(s) returned no parseable response.")

    if accuracy < ACCURACY_THRESHOLD:
        print("RESULT: FAIL — accuracy below threshold.")
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
