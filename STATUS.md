# SpO2 Eval Pipeline — Status

## Current Phase: Phases 1-4 Complete
**Last updated**: April 14, 2026

## Phase Tracker

| Phase | Description | Status | Notes |
|-------|-------------|--------|-------|
| 1 | Synthetic Data Generator | Done | 300 traces (100 babies x 3 nights), 4 pattern types, GA-adjusted |
| 2 | Rule Engine (Tier 1) | Done | 61% auto-labeled, 84.7% accuracy |
| 3 | Pattern Mining Layer | Done | 54 rules discovered (4 tree + 50 Apriori) |
| 4 | Pre-Annotation Classifier (Tier 2) | Done | 31.3% coverage, expert queue 7.7% |
| 5 | LLM Evaluators | Not started | Needs ANTHROPIC_API_KEY |
| 6 | Nurse Handoff Generator | Not started | Needs ANTHROPIC_API_KEY |
| 7 | Streamlit Dashboard | Not started | |

## Pipeline Coverage (Phases 1-4)
- Tier 1 (rules): 61.0%
- Tier 2 (classifier): 31.3%
- Expert queue: 7.7%
- Overall accuracy: 68.3%

## Next Actions
- [ ] Set ANTHROPIC_API_KEY environment variable
- [ ] Build Phase 5: LLM evaluators (clinical accuracy, handoff quality, artifact handling)
- [ ] Build Phase 6: Nurse handoff generator
- [ ] Build Phase 7: Streamlit dashboard

## Blockers
- ANTHROPIC_API_KEY needed for Phases 5-6

## How To Run
```bash
cd /Users/Sterdb/pm-os/projects/spo2-eval-pipeline
source venv/bin/activate
python -m src.pipeline.orchestrator
```

## Interview Talk Track
_Fill in as the project progresses — how to describe this project in 60 seconds to a hiring manager._
