"""Simulated expert reviewer for the expert queue.

Uses the ground truth label with 95% accuracy + 5% noise to simulate
human expert disagreement. Provides the "gold standard" label for traces
that couldn't be confidently classified by rules or ML.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from src.data_gen.synthetic import NightTrace
from src.classifier.tier2 import Tier2Result


@dataclass
class ExpertResult:
    """Result from simulated expert review."""
    trace_id: str
    baby_id: str
    ground_truth: str
    expert_label: str
    expert_confidence: float
    notes: str


# Simulated expert notes by label
_EXPERT_NOTES = {
    "urgent": "Significant desaturation pattern. Recommend immediate clinical follow-up.",
    "borderline": "Ambiguous pattern — monitor closely. May warrant additional night of data.",
    "normal": "Trace appears within normal range for gestational age.",
    "artifact": "Signal irregularities consistent with motion artifact. Low clinical concern.",
}

_ALL_LABELS = ["normal", "urgent", "borderline", "artifact"]


def simulate_expert_review(
    trace: NightTrace,
    tier2_result: Tier2Result | None = None,
    accuracy: float = 0.95,
    seed: int | None = None,
) -> ExpertResult:
    """Simulate expert review of a trace.

    The expert agrees with ground truth 95% of the time.
    The 5% disagreement simulates real clinical ambiguity.
    """
    rng = np.random.default_rng(seed)

    if rng.random() < accuracy:
        expert_label = trace.ground_truth_label
        confidence = rng.uniform(0.85, 0.99)
    else:
        # Expert disagrees — pick a different label
        other_labels = [l for l in _ALL_LABELS if l != trace.ground_truth_label]
        expert_label = rng.choice(other_labels)
        confidence = rng.uniform(0.55, 0.75)

    notes = _EXPERT_NOTES.get(expert_label, "No additional notes.")

    return ExpertResult(
        trace_id=trace.night_id,
        baby_id=trace.baby.baby_id,
        ground_truth=trace.ground_truth_label,
        expert_label=expert_label,
        expert_confidence=round(float(confidence), 2),
        notes=notes,
    )


def run_expert_queue(
    expert_traces: list[NightTrace],
    tier2_results: list[Tier2Result] | None = None,
    seed: int = 42,
) -> list[ExpertResult]:
    """Process all traces routed to the expert queue."""
    rng = np.random.default_rng(seed)
    results = []

    t2_map = {}
    if tier2_results:
        t2_map = {r.trace_id: r for r in tier2_results}

    for trace in expert_traces:
        t2 = t2_map.get(trace.night_id)
        # Use a unique seed per trace for reproducibility
        trace_seed = int(rng.integers(0, 2**31))
        result = simulate_expert_review(trace, t2, seed=trace_seed)
        results.append(result)

    if results:
        from collections import Counter
        label_counts = Counter(r.expert_label for r in results)
        correct = sum(1 for r in results if r.expert_label == r.ground_truth)
        print(f"\nExpert Queue Results:")
        print(f"  Reviewed: {len(results)}")
        print(f"  Labels: {dict(label_counts)}")
        print(f"  Accuracy: {correct}/{len(results)} = {correct/len(results)*100:.1f}%")

    return results
