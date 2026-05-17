"""Diagnostic: confirm tier1 label distribution per baby explains zero-scores."""
from collections import Counter
from src.data_gen.synthetic import generate_dataset
from src.rules.tier1_engine import apply_rules
from src.patterns.trend_features import run_trend_tier

traces = generate_dataset(seed=42)
tier1_results = [apply_rules(t) for t in traces]
records = run_trend_tier(traces, tier1_results)

label_by_trace = {r.trace_id: r.label for r in tier1_results}

# Per-baby breakdown for deteriorating babies
from collections import defaultdict
traces_by_baby = defaultdict(list)
for t in traces:
    traces_by_baby[t.baby.baby_id].append(t)

print("Per-baby tier1 label distribution (deteriorating babies):")
for bid, bts in traces_by_baby.items():
    if not bts[0].baby.seeded_deteriorating:
        continue
    labels = Counter(label_by_trace.get(t.night_id) for t in bts)
    rec = records[bid]
    print(f"  {bid}: ga={bts[0].baby.ga_category}, "
          f"labels={dict(labels)}, "
          f"score={rec.trend_score:.1f}, dir={rec.trend_direction}, "
          f"baseline={rec.baseline_sat_seconds}")

print("\nPer-baby tier1 label distribution (5 stable babies):")
stable_count = 0
for bid, bts in traces_by_baby.items():
    if bts[0].baby.seeded_deteriorating:
        continue
    labels = Counter(label_by_trace.get(t.night_id) for t in bts)
    rec = records[bid]
    print(f"  {bid}: ga={bts[0].baby.ga_category}, "
          f"labels={dict(labels)}, "
          f"score={rec.trend_score:.1f}, dir={rec.trend_direction}, "
          f"baseline={rec.baseline_sat_seconds}")
    stable_count += 1
    if stable_count >= 5:
        break
