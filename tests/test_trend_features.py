"""Hard gate for the trend tier: 80% sensitivity / 20% FPR across 3 canonical seeds.

Per the SPEC-v3 plan (`tasks/plan.md`, PY-4):

- **Canonical seeds are frozen as module-level constants.** They were chosen
  on 2026-05-17 as fixed test fixtures; they MUST NOT be re-rolled if the
  test fails. Failure means the trend tier is broken, not the seeds. Tune
  EWMA alpha or baseline window (PY-3 constants) within their spec'd
  envelopes, then re-run — do not chase a "lucky" seed.

- **Cohort size per seed: 10 seeded-deteriorating + 20 stable** (=30 babies).
  Larger than the production cohort (25 babies = 10 det + 15 stable) so a
  single missed baby drops sensitivity by 10% rather than 20%, giving real
  headroom around the 80% floor.

- **Pass criteria (all three seeds):** sensitivity >= 80%, FPR <= 20%.

The locked trend_score flag threshold is `TREND_FLAG_THRESHOLD = 150.0`
(see `src/patterns/trend_features.py`). A wide passing window 100-250 was
established during PY-3 tuning sweep; the chosen value sits center-of-window.
"""
from __future__ import annotations

import numpy as np
import pytest

from src.data_gen.synthetic import generate_dataset
from src.patterns.trend_features import run_trend_tier, TREND_FLAG_THRESHOLD
from src.rules.tier1_engine import apply_rules


CANONICAL_SEEDS: tuple[int, ...] = (42, 1234, 7890)

# Fixture cohort: 10 deteriorating (config.N_SEEDED_DETERIORATING) + 20 stable.
N_BABIES = 30
N_NIGHTS = 16

SENSITIVITY_MIN = 0.80
FPR_MAX = 0.20


def _trend_metrics(seed: int) -> tuple[float, float, int, int, int, int]:
    """Generate cohort, run trend tier, return (sens, fpr, tp, fn, fp, tn)."""
    traces = generate_dataset(n_babies=N_BABIES, nights_per_baby=N_NIGHTS, seed=seed)
    tier1_results = [apply_rules(t) for t in traces]
    records = run_trend_tier(traces, tier1_results)

    bid_to_det = {t.baby.baby_id: t.baby.seeded_deteriorating for t in traces}

    tp = sum(1 for bid, r in records.items() if bid_to_det[bid] and r.flagged)
    fn = sum(1 for bid, r in records.items() if bid_to_det[bid] and not r.flagged)
    fp = sum(1 for bid, r in records.items() if not bid_to_det[bid] and r.flagged)
    tn = sum(1 for bid, r in records.items() if not bid_to_det[bid] and not r.flagged)

    sens = tp / max(1, tp + fn)
    fpr = fp / max(1, fp + tn)
    return sens, fpr, tp, fn, fp, tn


@pytest.mark.parametrize("seed", CANONICAL_SEEDS)
def test_trend_tier_meets_80_20_threshold(seed: int) -> None:
    """80% sensitivity / 20% FPR on the canonical fixture cohort.

    Locked threshold: TREND_FLAG_THRESHOLD = {locked}. If this test fails,
    re-spec EWMA alpha or BASELINE_QUANTILE in trend_features.py — do NOT
    re-roll the seeds.
    """
    sens, fpr, tp, fn, fp, tn = _trend_metrics(seed)

    assert sens >= SENSITIVITY_MIN, (
        f"seed={seed}: sensitivity {sens:.0%} below {SENSITIVITY_MIN:.0%} floor "
        f"(TP={tp}, FN={fn}). Fix trend tier, do NOT re-roll seed."
    )
    assert fpr <= FPR_MAX, (
        f"seed={seed}: FPR {fpr:.0%} above {FPR_MAX:.0%} ceiling "
        f"(FP={fp}, TN={tn}). Fix trend tier, do NOT re-roll seed."
    )


def test_threshold_is_locked() -> None:
    """Guard against accidental TREND_FLAG_THRESHOLD drift.

    The 150.0 value was locked after the PY-3 tuning sweep. Any change must
    be re-justified against all three canonical seeds.
    """
    assert TREND_FLAG_THRESHOLD == 150.0, (
        "TREND_FLAG_THRESHOLD drifted from the locked 150.0 value. Re-run the "
        "tuning sweep against canonical seeds before changing."
    )
