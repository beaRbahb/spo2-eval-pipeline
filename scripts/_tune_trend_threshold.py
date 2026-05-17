"""PY-3 threshold tuning sweep across 3 canonical seeds.

Generates the dataset once per seed, then evaluates many thresholds against
the cached records. Output guides the locked TREND_FLAG_THRESHOLD value.
"""
import numpy as np
from src.data_gen.synthetic import generate_dataset
from src.rules.tier1_engine import apply_rules
from src.patterns.trend_features import run_trend_tier
import src.patterns.trend_features as tf

SEEDS = (42, 1234, 7890)

print("Generating datasets + tier1 + trend records per seed...")
cached = {}
for seed in SEEDS:
    traces = generate_dataset(seed=seed)
    tier1_results = [apply_rules(t) for t in traces]
    records = run_trend_tier(traces, tier1_results)
    bid_to_det = {t.baby.baby_id: t.baby.seeded_deteriorating for t in traces}
    # Cache scores so threshold sweep just compares numbers.
    scored = [(bid, r.trend_score, bid_to_det[bid]) for bid, r in records.items()]
    cached[seed] = scored
    print(f"  seed={seed}: {len(scored)} babies cached")

# Sanity: print smoke summary for seed=42
print()
seed42 = cached[42]
for bid, score, is_det in seed42[:5]:
    print(f"  seed42 sample: bid={bid} det={is_det} score={score:.1f}")

print()
print("Score distributions per seed:")
for seed in SEEDS:
    det_scores = sorted([s for _, s, d in cached[seed] if d])
    stab_scores = sorted([s for _, s, d in cached[seed] if not d])
    print(f"  seed={seed}: det scores = {[f'{x:.0f}' for x in det_scores]}")
    print(f"  seed={seed}: stable scores = {[f'{x:.0f}' for x in stab_scores]}")

print()
print("Threshold sweep:")
print(f"{'thresh':>6}  {'seed=42 sens/fpr':>20}  {'seed=1234 sens/fpr':>22}  {'seed=7890 sens/fpr':>22}  pass?")
for thresh in (25, 50, 75, 100, 125, 150, 175, 200, 250, 300):
    row = [thresh]
    all_pass = True
    for seed in SEEDS:
        scored = cached[seed]
        tp = sum(1 for _, s, d in scored if d and s >= thresh)
        fn = sum(1 for _, s, d in scored if d and s < thresh)
        fp = sum(1 for _, s, d in scored if not d and s >= thresh)
        tn = sum(1 for _, s, d in scored if not d and s < thresh)
        sens = tp / max(1, tp + fn)
        fpr = fp / max(1, fp + tn)
        row.append((sens, fpr))
        # 80/20 acceptance per PY-4
        if sens < 0.80 or fpr > 0.20:
            all_pass = False
    parts = [f"{r[0]:.0%} / {r[1]:.0%}" for r in row[1:]]
    flag = "PASS" if all_pass else "FAIL"
    print(f"{row[0]:>6}  {parts[0]:>20}  {parts[1]:>22}  {parts[2]:>22}  {flag}")
