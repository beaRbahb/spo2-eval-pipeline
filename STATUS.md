# SpO2 Eval Pipeline — Status

## Current State: V2.1 — Clinical Review Fixes + GT Labels
**Last updated**: April 14, 2026

## Phase Tracker

| Phase | Description | Status | Notes |
|-------|-------------|--------|-------|
| 1 | Synthetic Data Generator | Done | 300 traces (100 babies x 3 nights), 5 labels (incl. emergency), GA-adjusted |
| 2 | Rule Engine (Tier 1) | Done (v2) | 58% auto-labeled, GA-adjusted thresholds, emergency tier, safety check |
| 3 | Pattern Mining Layer | Done | 54 rules discovered (4 tree + 50 Apriori) |
| 4 | Pre-Annotation Classifier (Tier 2) | Done | 39.3% coverage, expert queue 2.7%, with domain shift warnings |
| 5 | LLM Evaluators | Done (live tested) | 3 evaluators, live eval pass rates 80-100% |
| 6 | Nurse Handoff Generator | Done | 5 templates (emergency/urgent/monitor/routine/artifact), SatSeconds |
| 7 | Streamlit Dashboard | Done | 6 views, custom theming, per-label metrics, Tier 2 warnings |

## Pipeline Metrics (v2.1 — post GT label fix)
- Tier 1 (rules): 58.0%
- Tier 2 (classifier): 39.3%
- Expert queue: 2.7%
- **Overall accuracy: 88.3%** (was 76.3% before GT fix, 68.3% v1)
- **Tier 1 accuracy: 96.0%** (was 75.3% before GT fix)
- Urgent false negatives: 0
- Emergency cases detected: 36

## Live Eval Results

### V2.1 (10 traces, 30 evals, $0.20 — after prompt + parser fixes)
- Clinical accuracy: 60-70% pass (variance across runs)
- Handoff quality: 80% pass (recovered from 20-30% pre-fix)
- Artifact handling: 100% pass

### V2 (10 traces, 30 evals, $0.19 — post clinical fixes, pre prompt fix)
- Clinical accuracy: 70% pass (down from 80% v1)
- Handoff quality: 30% pass (regressed — live prompt not updated)
- Artifact handling: 100% pass

### V1 (10 traces, 30 evals, $0.18 — pre-v2 fixes)
- Clinical accuracy: 80% pass
- Handoff quality: 90% pass (was 20% before template fixes)
- Artifact handling: 100% pass

## Clinical Review Fixes (v2)
Applied based on domain review (Bonafide/CHOP persona). See LEARNINGS.md #13.

### P1 — Safety Critical (done)
- [x] Urgent false negative safety constraint — raw signal check overrides artifact masking
- [x] Tier 2 domain shift warning in dashboard
- [x] Expert queue labeled as simulated (95% oracle) with footnote

### P2 — Clinical Accuracy (done)
- [x] Emergency tier (SpO2 <80% → call 911)
- [x] GA-adjusted thresholds from published references (Castillo 2008, Hay 2002)
- [x] SatSeconds severity metric in handoffs and features
- [x] Per-label sensitivity/PPV/F1 in dashboard

### Safety Tests
6 tests in `tests/test_safety_check.py` — all passing:
- Artifact cannot mask genuine urgent desat
- Pure artifact (brief drops) stays artifact
- SpO2 <80% sustained → emergency
- GA-adjusted: 87% not urgent for extremely preterm
- Safety check finds desats in raw signal
- SpO2 80-90% sustained → urgent (not emergency)

## V2 Clinical Review Findings
Live handoff quality regressed 90% → 30% and clinical accuracy dropped 80% → 70%. Root cause: `_HANDOFF_PROMPT` and urgency parser were never updated when emergency tier, SatSeconds, and GA-adjusted thresholds were added. Mock templates (dashboard) were fine — only the live Claude path was broken. Additionally, `_compute_trace_stats` used synthetic generator events instead of rule engine detected events. See LEARNINGS.md #19 for full details.

**Fixes applied:**
- [x] Live prompt updated with EMERGENCY, SatSeconds, GA threshold, clinical correlation
- [x] Urgency parser: EMERGENCY check before URGENT (was silently downgrading to ROUTINE)
- [x] `ga_threshold` added to stats dict
- [x] Rule engine events passed through handoff chain (replaces `trace.events`)
- [x] Clinical correlation questions added to emergency/urgent templates

## Known Issues
- Tier 2 accuracy (76.3%) still reflects domain shift — trained on easy cases, tested on harder ones. Dashboard has warning callout.
- Expert queue 100% accuracy is simulated oracle — dashboard footnote explains this.
- Clinical accuracy evaluator still uses `trace.events` instead of rule engine events (handoff generator was fixed, evals not yet).
- Handoff quality recovered to 80% after prompt fixes but hasn't reached v1's 90%. Remaining failures are legitimate edge cases (ROUTINE handoffs where Claude hedges action language).

## Next Actions
- [x] Rerun live eval — handoff quality recovered 30% → 80%
- [x] Push to GitHub with README
- [ ] Thread rule_events through evaluators (clinical_accuracy, artifact_handling)
- [ ] Update interview talk track with v2 clinical review story

## How To Run
```bash
cd ~/spo2-eval-pipeline
source venv/bin/activate

# Full pipeline (mock mode, $0)
python -m src.pipeline.orchestrator

# Dashboard
streamlit run app/dashboard.py

# Tests
python -m pytest tests/test_safety_check.py -v

# Live mode (costs money — confirm first)
# python -c "from src.pipeline.orchestrator import run_pipeline; run_pipeline(use_llm=True, llm_sample_size=10)"
```

## Commits
1. `da08465` — Phases 1-4 (data pipeline)
2. `2324f48` — LEARNINGS.md
3. `dcce022` — Phases 5-7 (evals, handoffs, dashboard)
4. `d050586` — Custom theming, CLAUDE.md
5. `d5915b1` — Shared theme module
6. `9b70781` — Dashboard polish
7. `2175d4e` — V2 clinical fixes, README, remove brand references
8. `68185e5` — Fix live handoff prompt, urgency parser, event source
9. `fd04886` — Add timeframe requirement, fix markdown urgency parsing
10. `442d0c2` — LEARNINGS.md #19 live eval rerun findings
11. `864222b` — Emergency ground truth labels, clinical eval max_tokens fix

## Interview Talk Track
_60 seconds — what this is, why, what you learned:_

> I built an end-to-end AI evaluation pipeline for neonatal SpO2 monitoring — the kind of system needed to validate overnight triage algorithms at scale for consumer pulse oximetry devices.
>
> It generates synthetic pulse oximetry data with gestational-age-adjusted baselines, then runs it through a three-tier classification system: rules for clear cases, a classifier for ambiguous ones, and a simulated expert queue for the rest. On top of that, I built three LLM-as-judge evaluators that assess clinical accuracy, handoff quality, and artifact handling.
>
> After the initial build, I ran a clinical domain review that found two critical issues: the rule engine could mask genuine urgent desaturations behind artifact detections, and the system had no emergency tier for SpO2 below 80%. I fixed both — added a safety check that prevents artifact labeling from ever hiding a real desat, implemented GA-adjusted thresholds from published neonatal reference ranges, and added a SatSeconds severity metric.
>
> The LLM evaluators also caught that my handoff templates had vague action steps — mock evals said 95% pass rate, but real Claude evaluation said 20%. After fixing the templates, it went to 90%. That's the whole point of eval pipelines — they catch quality gaps that rule-based testing misses.
