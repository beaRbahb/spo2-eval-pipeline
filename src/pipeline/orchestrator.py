"""End-to-end pipeline orchestrator.

Connects all phases: synthetic data → Tier 1 rules → pattern mining →
Tier 2 classifier → expert queue. Computes coverage stats and returns
a unified result object.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from collections import Counter

from src.data_gen.synthetic import (
    NightTrace,
    generate_dataset,
    summarize_dataset,
)
from src.rules.tier1_engine import RuleResult, run_tier1
from src.patterns.feature_eng import build_feature_matrix
from src.patterns.miner import CandidateRule, run_pattern_mining
from src.classifier.tier2 import Tier2Result, train_tier2, predict_tier2
from src.classifier.expert_sim import ExpertResult, run_expert_queue


@dataclass
class CoverageReport:
    """Pipeline coverage statistics."""
    total_traces: int
    tier1_auto: int
    tier2_auto: int
    expert_queue: int
    tier1_pct: float
    tier2_pct: float
    expert_pct: float


@dataclass
class FinalTriage:
    """Merged triage result for a single trace."""
    trace_id: str
    baby_id: str
    ground_truth: str
    final_label: str
    source: str  # "tier1_rules", "tier2_classifier", "expert_review"
    confidence: float


@dataclass
class PipelineResults:
    """All outputs from a full pipeline run."""
    traces: list[NightTrace]
    tier1_results: list[RuleResult]
    tier2_results: list[Tier2Result]
    expert_results: list[ExpertResult]
    coverage: CoverageReport
    candidate_rules: list[CandidateRule]
    final_triage: list[FinalTriage]
    tree: object = None  # fitted DecisionTreeClassifier for visualization


def merge_triage(
    tier1_results: list[RuleResult],
    tier2_results: list[Tier2Result],
    expert_results: list[ExpertResult],
) -> list[FinalTriage]:
    """Merge results from all tiers into a single final triage list."""
    final = []

    # Tier 1 labeled traces
    for r in tier1_results:
        if r.auto_labeled:
            final.append(FinalTriage(
                trace_id=r.trace_id,
                baby_id=r.baby_id,
                ground_truth=r.ground_truth,
                final_label=r.label,
                source="tier1_rules",
                confidence=r.confidence,
            ))

    # Tier 2 auto-labeled traces
    for r in tier2_results:
        if r.routed_to == "auto":
            final.append(FinalTriage(
                trace_id=r.trace_id,
                baby_id=r.baby_id,
                ground_truth=r.ground_truth,
                final_label=r.predicted_label,
                source="tier2_classifier",
                confidence=r.confidence,
            ))

    # Expert-reviewed traces
    for r in expert_results:
        final.append(FinalTriage(
            trace_id=r.trace_id,
            baby_id=r.baby_id,
            ground_truth=r.ground_truth,
            final_label=r.expert_label,
            source="expert_review",
            confidence=r.expert_confidence,
        ))

    return final


def compute_coverage(
    tier1_results: list[RuleResult],
    tier2_results: list[Tier2Result],
    expert_results: list[ExpertResult],
    total_traces: int,
) -> CoverageReport:
    """Compute coverage statistics across all tiers."""
    tier1_auto = sum(1 for r in tier1_results if r.auto_labeled)
    tier2_auto = sum(1 for r in tier2_results if r.routed_to == "auto")
    expert = len(expert_results)

    return CoverageReport(
        total_traces=total_traces,
        tier1_auto=tier1_auto,
        tier2_auto=tier2_auto,
        expert_queue=expert,
        tier1_pct=round(tier1_auto / total_traces * 100, 1),
        tier2_pct=round(tier2_auto / total_traces * 100, 1),
        expert_pct=round(expert / total_traces * 100, 1),
    )


def run_pipeline(
    n_babies: int = 100,
    nights_per_baby: int = 3,
    seed: int = 42,
) -> PipelineResults:
    """Run the full Phases 1-4 pipeline end-to-end."""
    print("=" * 60)
    print("SpO2 AI Eval Pipeline — Phases 1-4")
    print("=" * 60)

    # Phase 1: Generate synthetic data
    print("\n[Phase 1] Generating synthetic data...")
    traces = generate_dataset(n_babies, nights_per_baby, seed)
    summarize_dataset(traces)

    # Phase 2: Tier 1 rule-based pre-annotation
    print("[Phase 2] Running Tier 1 rules...")
    tier1_results, unlabeled_traces = run_tier1(traces)

    # Phase 3: Pattern mining
    print("[Phase 3] Mining patterns...")
    all_df = build_feature_matrix(traces, tier1_results)
    candidate_rules, tree = run_pattern_mining(all_df)

    # Phase 4: Tier 2 classifier + expert queue
    print("[Phase 4] Training Tier 2 classifier...")
    model, le, metrics = train_tier2(tier1_results, traces)

    print(f"\n[Phase 4] Predicting on {len(unlabeled_traces)} unlabeled traces...")
    tier2_results = predict_tier2(model, le, unlabeled_traces)

    # Route low-confidence traces to expert queue
    expert_traces = [
        t for t in unlabeled_traces
        for r in tier2_results
        if r.trace_id == t.night_id and r.routed_to == "expert_queue"
    ]
    print(f"\n[Phase 4] Processing {len(expert_traces)} traces in expert queue...")
    expert_results = run_expert_queue(expert_traces, tier2_results, seed=seed)

    # Merge and compute coverage
    final_triage = merge_triage(tier1_results, tier2_results, expert_results)
    coverage = compute_coverage(tier1_results, tier2_results, expert_results, len(traces))

    # Final summary
    print(f"\n{'=' * 60}")
    print(f"Pipeline Coverage Summary")
    print(f"{'=' * 60}")
    print(f"Total traces:       {coverage.total_traces}")
    print(f"Tier 1 (rules):     {coverage.tier1_auto:4d} ({coverage.tier1_pct}%)")
    print(f"Tier 2 (classifier):{coverage.tier2_auto:4d} ({coverage.tier2_pct}%)")
    print(f"Expert queue:       {coverage.expert_queue:4d} ({coverage.expert_pct}%)")
    print(f"{'=' * 60}")

    # Accuracy
    correct = sum(1 for t in final_triage if t.final_label == t.ground_truth)
    print(f"\nOverall accuracy: {correct}/{len(final_triage)} = {correct/len(final_triage)*100:.1f}%")

    by_source = Counter(t.source for t in final_triage)
    for source, count in sorted(by_source.items()):
        source_correct = sum(1 for t in final_triage if t.source == source and t.final_label == t.ground_truth)
        print(f"  {source:20s}: {source_correct}/{count} = {source_correct/count*100:.1f}%")

    return PipelineResults(
        traces=traces,
        tier1_results=tier1_results,
        tier2_results=tier2_results,
        expert_results=expert_results,
        coverage=coverage,
        candidate_rules=candidate_rules,
        final_triage=final_triage,
        tree=tree,
    )


if __name__ == "__main__":
    results = run_pipeline()
