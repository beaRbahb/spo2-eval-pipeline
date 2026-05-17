"""Tier-4 trend detection: EWMA over per-night SatSeconds.

The first three tiers (rules, classifier, expert queue) label individual nights.
This tier looks across nights for the same baby and flags babies whose
hypoxemic burden is trending upward — even when each individual night still
falls within "normal" or "borderline" by per-night rules.

Algorithm:
  1. Per baby, compute SatSeconds per night (same formula as the handoff
     generator: `sum(max(0, ga_urgent_threshold - spo2))`).
  2. Smooth the per-night series with EWMA (alpha = 0.13, half-life ~5 nights).
  3. Compute a per-baby baseline as the mean SatSeconds over the **lower half
     of the baby's own nights, ordered by SatSeconds** — i.e. the baby's
     quieter half, their personal quiet-night floor.
  4. trend_score = current EWMA value minus baseline. Positive = trending
     worse. Flagged when trend_score exceeds TREND_FLAG_THRESHOLD.
  5. Edge: babies with fewer than MIN_TREND_NIGHTS total nights have no
     defensible trend signal; they get trend_direction="insufficient_data"
     and flagged=False.

Constants below are locked. EWMA_ALPHA may only be tuned within +/-0.05 if
PY-4 canonical-seed tests fail; the trend_score threshold is tuned empirically
to hit 80% sensitivity / 20% FPR on those tests and then frozen here.

**Spec deviation note** (re-spec authorized by PY-4 risk mitigation): the
SPEC-v3 baseline definition originally read "mean SatSeconds over nights
labeled normal or artifact by Tier 1." That definition collapses for preterm
babies because Tier 1 rule R3 requires >98% of readings above 95%, which a
baby with baseline SpO2 of 91% never satisfies. The preterm "clean nights"
come back as `label=None`, dropping out of the baseline pool and forcing
trend_direction="insufficient_data" on 6 of 10 deteriorating babies (seed=42),
capping sensitivity at 40%. Replacing tier1-label-based selection with
within-baby SatSeconds-quantile selection makes the baseline robust across
all GA categories — same clinical intent ("quiet-night floor"), spec-honoring
ground truth (each baby is its own control).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import numpy as np

from src.config import GA_URGENT_THRESHOLDS
from src.data_gen.synthetic import NightTrace
from src.rules.tier1_engine import RuleResult


# ---------------------------------------------------------------------------
# Locked constants — re-spec required to change
# ---------------------------------------------------------------------------

EWMA_ALPHA: float = 0.13           # half-life ~5 nights
MIN_TREND_NIGHTS: int = 4          # below this, trend_direction = insufficient_data
BASELINE_QUANTILE: float = 0.50    # lower half of a baby's nights = baseline pool
# TREND_FLAG_THRESHOLD frozen at 150.0 SatSeconds units after PY-4 tuning sweep
# (canonical seeds 42, 1234, 7890; 25-baby production cohort): yields 90%/100%/90%
# sensitivity at 0% FPR — well above the 80/20 PY-4 gate. Passing window spans
# 100-250; 150 sits center-of-window for robustness against fixture drift.
TREND_FLAG_THRESHOLD: float = 150.0


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class BabyTrendRecord:
    """Trend-tier output for one baby across all of their nights."""
    baby_id: str
    condition: str  # "AOP" | "BPD" | "CHD_interstage"
    n_nights: int
    sat_seconds_series: list[float]      # per-night SatSeconds (ordered by night_number)
    ewma_series: list[float]             # per-night EWMA value
    trend_score: float                   # ewma_current - baseline; positive = worse
    trend_direction: str                 # "stable" | "improving" | "deteriorating" | "insufficient_data"
    flagged: bool
    flag_reason: str | None              # set when flagged
    baseline_sat_seconds: float | None   # None when insufficient non-event nights


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _sat_seconds(trace: NightTrace) -> float:
    """SatSeconds = integral of (GA-threshold - SpO2) over time below threshold."""
    threshold = GA_URGENT_THRESHOLDS.get(trace.baby.ga_category, 90)
    return float(np.sum(np.maximum(0.0, threshold - trace.spo2)))


def _ewma(values: list[float], alpha: float) -> list[float]:
    """Exponentially weighted moving average. Seeded with the first value."""
    if not values:
        return []
    out = [values[0]]
    for v in values[1:]:
        out.append(alpha * v + (1.0 - alpha) * out[-1])
    return out


def _classify_direction(trend_score: float) -> str:
    """Map a trend_score scalar to a direction label."""
    if trend_score >= TREND_FLAG_THRESHOLD:
        return "deteriorating"
    if trend_score <= -TREND_FLAG_THRESHOLD:
        return "improving"
    return "stable"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_trend_tier(
    traces: list[NightTrace],
    tier1_results: list[RuleResult],
) -> dict[str, BabyTrendRecord]:
    """Compute per-baby trend records across all nights in the cohort.

    Returns a dict keyed by baby_id (matches the locked JSON shape consumed
    by the React dashboard via trend-features.json).

    `tier1_results` is accepted on the signature for compatibility with the
    orchestrator and downstream consumers; baseline computation is currently
    derived from each baby's own SatSeconds distribution (see module docstring
    for why tier1 labels are insufficient for preterm babies).
    """
    del tier1_results  # not used for baseline; see module docstring

    # Group traces by baby, ordered by night_number
    traces_by_baby: dict[str, list[NightTrace]] = defaultdict(list)
    for t in traces:
        traces_by_baby[t.baby.baby_id].append(t)
    for bid in traces_by_baby:
        traces_by_baby[bid].sort(key=lambda t: t.night_number)

    records: dict[str, BabyTrendRecord] = {}
    for baby_id, baby_traces in traces_by_baby.items():
        baby = baby_traces[0].baby
        n_nights = len(baby_traces)

        sat_series = [_sat_seconds(t) for t in baby_traces]
        ewma_series = _ewma(sat_series, EWMA_ALPHA)

        if n_nights < MIN_TREND_NIGHTS:
            records[baby_id] = BabyTrendRecord(
                baby_id=baby_id,
                condition=baby.condition,
                n_nights=n_nights,
                sat_seconds_series=sat_series,
                ewma_series=ewma_series,
                trend_score=0.0,
                trend_direction="insufficient_data",
                flagged=False,
                flag_reason=None,
                baseline_sat_seconds=None,
            )
            continue

        # Baseline = mean of the baby's lower-half SatSeconds nights — their
        # personal quiet-night floor. Robust across GA categories where Tier 1
        # label coverage varies (preterm babies rarely satisfy R3 "normal").
        n_baseline = max(1, int(n_nights * BASELINE_QUANTILE))
        baseline_values = sorted(sat_series)[:n_baseline]
        baseline = float(np.mean(baseline_values))
        ewma_current = ewma_series[-1]
        trend_score = ewma_current - baseline
        direction = _classify_direction(trend_score)
        flagged = direction == "deteriorating"

        flag_reason: str | None = None
        if flagged:
            flag_reason = (
                f"EWMA SatSeconds {ewma_current:.0f} exceeds quiet-night baseline "
                f"{baseline:.0f} by {trend_score:.0f} over {n_nights} nights"
            )

        records[baby_id] = BabyTrendRecord(
            baby_id=baby_id,
            condition=baby.condition,
            n_nights=n_nights,
            sat_seconds_series=sat_series,
            ewma_series=ewma_series,
            trend_score=trend_score,
            trend_direction=direction,
            flagged=flagged,
            flag_reason=flag_reason,
            baseline_sat_seconds=baseline,
        )

    return records
