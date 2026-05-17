# SPEC v2 — Trend Tier + Dual Framing

**Status:** drafted 2026-05-17. Awaits final CPT-code confirmation for `/rpm` (big reframe inbound).
**Supersedes:** none. The original `SPEC.md` (April 2026) covered phases 1-7 and is retained as historical context.
**Repos in scope:** `/Users/Sterdb/spo2-eval-pipeline/` (Python) and `/Users/Sterdb/pm-private/spo2-eval-dashboard/` (React).

---

## 1. Objective

Ship two parallel workstreams that together convert the existing 3-tier triage demo into a closed-loop, dual-framed portfolio artifact:

- **Workstream A — Trend tier.** Add a 4th triage tier that detects multi-night deterioration in SatSeconds via EWMA. Regenerate synthetic data at 25 babies × 16 nights with a seeded "trending worse" cohort. Wire the trend signal into the existing nurse-handoff generator so the closed-loop story ("stable each night, trending worse across nights → escalate") is end-to-end demonstrable.
- **Workstream B — Dual framing + IA.** Add two new landings, `/clinical-ai` (eval-driven-dev narrative for PM-at-AI-co + clinical informatics audiences) and `/rpm` ("today vs tomorrow" reimbursement framing). Restructure the React app into 4 top-level destinations (`Story | Business | Dashboard | Strategy`) so positioning and discovery both work.

### Theme
"Building the data for the story." The artifact's value is not the dashboard — it's the demonstrated discipline of generating synthetic data, building tiered triage, running LLM-as-judge evals, surfacing clinical gaps in review, fixing them, and re-evaluating. The trend tier extends that loop by another turn; the dual framing makes the loop legible to two different audiences.

### Target audiences
- `/clinical-ai`: PM hiring managers at AI companies (Anthropic, OpenAI applied, Cursor, etc.) **and** clinical informatics leaders. Both value evals-as-product-discipline and clinical rigor.
- `/rpm`: clinical-ops and business leaders at RPM / consumer-pulse-ox companies. Tone is corrective — the page exists because the industry's default RPM framing for neonates is wrong, and the page's value is precisely that it doesn't repeat the wrong story.

---

## 2. Commands

```bash
# Python repo (/Users/Sterdb/spo2-eval-pipeline)
source venv/bin/activate

# Regenerate full dataset + all dashboard JSON artifacts (mock mode, $0, ~5s)
python scripts/export_dashboard_data.py                      # random seed
python scripts/export_dashboard_data.py --seed 42            # reproducible

# Trend-tier unit tests
python -m pytest tests/test_trend_features.py -v

# Sync exported artifacts into React repo (no auto-commit)
bash scripts/sync_to_frontend.sh

# Live LLM eval — REQUIRES EXPLICIT USER APPROVAL before running
# python -c "from src.pipeline.orchestrator import run_pipeline; run_pipeline(use_llm=True, llm_sample_size=10)"

# React repo (/Users/Sterdb/pm-private/spo2-eval-dashboard)
pnpm dev          # local dev server, Vite
pnpm build        # pre-merge gate (TS + Vite build must pass)
```

---

## 3. Project structure

### Python repo — files added or modified

```
src/
  data_gen/
    synthetic.py            MOD: parameterize n_babies/nights_per_baby (defaults → 25, 16);
                                 add seeded "trending worse" cohort (~5 of 25 babies) with
                                 monotonic SatSeconds deterioration across the 16-night sequence
  patterns/
    trend_features.py       NEW: EWMA over per-night SatSeconds; per-baby trend record
                                 {baby_id, ewma_series, trend_score, trend_direction,
                                  n_nights, flagged: bool}
  pipeline/
    orchestrator.py         MOD: run trend tier after per-night Tier 1/2/3; attach
                                 baby-level trend flag to each night's FinalTriage so the
                                 handoff can consume it. Trend tier does NOT override
                                 per-night labels — it adds a parallel signal.
  handoff/
    generator.py            MOD: emergency/urgent templates render an optional [TREND] block
                                 when baby-level flag is set; add new "stable-but-trending"
                                 template path for nights where per-night triage is routine
                                 but the multi-night flag fires.

scripts/
  export_dashboard_data.py  MOD: write new artifact data/export/trend-features.json;
                                 use n_babies=25, nights_per_baby=16 as new defaults.
  sync_to_frontend.sh       MOD: add trend-features.json to JSON_FILES allowlist.

tests/
  test_trend_features.py    NEW: 3 seeds × cohort. ≥80% sensitivity on seeded-bad babies,
                                 ≤20% false-positive on stable babies. All 3 seeds pass.

SPEC-v2-trend-and-framing.md NEW: this file.
SPEC.md                      KEEP: historical v1, do not edit.
STATUS.md                    MOD (later): update with v2 trend-tier metrics post-build.
LEARNINGS.md                 MOD (later): add entry on EWMA-over-CUSUM choice + trend
                                          handoff template lessons.
```

### React repo — files added or modified

```
src/
  layouts/
    SiteLayout.tsx          NEW: top-level wrapper with 4-destination header strip.
                                 Renders on every route. No sidebar.
    DashboardLayout.tsx     MOD: nests under SiteLayout. Sidebar drops the "Strategy"
                                 entry (Strategy moves to top-level).

  pages/
    ClinicalAI.tsx          NEW: JSX long-form landing.
                                 Narrative: synthetic data → 3-tier triage → LLM-as-judge
                                 evals → clinical review → trend tier added → re-evaluated.
                                 Inline CTAs deep-link into /pipeline/evals, /pipeline/traces,
                                 /pipeline/coverage. Audience: PM at AI co + clinical informatics.
    RPM.tsx                 NEW: JSX two-column "today vs tomorrow" landing.
                                 Column 1: what actually pays for neonatal pulse-ox today.
                                 Column 2: what would need to change for RPM CPT coverage.
                                 EXACT CPT CODES — TBD pending user's big reframe.
                                 Reuses cost-model table from AgenticStrategy with
                                 reimbursement-side numbers.

  App.tsx                   MOD: route tree:
                                   /               → redirect to /clinical-ai
                                   /clinical-ai    → ClinicalAI (under SiteLayout only)
                                   /rpm            → RPM (under SiteLayout only)
                                   /strategy       → AgenticStrategy (under SiteLayout only)
                                   /pipeline       → DashboardLayout (under SiteLayout)
                                     index         → PipelineOverview
                                     /coverage     → CoverageFunnel
                                     /rules        → RuleDiscovery
                                     /evals        → EvalScores
                                     /traces       → TraceExplorer
                                     /interop      → Interoperability

  pages/PipelineOverview.tsx
  pages/CoverageFunnel.tsx
  pages/RuleDiscovery.tsx
  pages/EvalScores.tsx
  pages/TraceExplorer.tsx
  pages/Interoperability.tsx
                            MOD (small): each may surface trend-tier metrics where
                                         relevant (Coverage shows new tier slice; Eval
                                         scores stay unchanged since no 4th judge axis).
                                         TraceExplorer renders [TREND] block in handoffs.

public/data/
  trend-features.json       NEW: synced from Python export.
```

### Branch strategy
- Python repo: `feat/trend-layer` for Workstream A.
- React repo: `feat/dual-framing` for Workstream B (IA + landings + trend wiring).
- Merging to main = production deploy via Cloudflare Pages. Both repos require user approval before merge.

---

## 4. Code style

### Python
- Match existing conventions in `/Users/Sterdb/spo2-eval-pipeline/src/`: type hints on public functions, docstrings on modules and public APIs, prefer dataclasses for record types, keep modules under ~300 lines.
- Trend tier follows the existing tier-engine pattern (`tier1_engine.py`, `tier2.py`): single public entry point `run_trend_tier(...)`, internal helpers below.
- No new dependencies. EWMA computed directly with numpy.

### React / TypeScript
- Match existing conventions in `/Users/Sterdb/pm-private/spo2-eval-dashboard/src/`: function components with typed props, Tailwind 4 utility classes, theme tokens from `src/config/theme.ts`, no inline color literals outside the theme module.
- New landing pages follow `AgenticStrategy.tsx` as a reference: editorial JSX with `SectionCard`, `MetricCard`, `PageIntro`, `Callout`, inline subcomponents for repeated patterns.
- No new dependencies. No `react-markdown`, no `remark-gfm`. Landings are JSX, not markdown-driven.
- `pnpm`, not `npm`. Vite 8, React 19, Tailwind 4, react-router-dom 7.

### Visual / design
- Use existing theme tokens (`TEAL_DARK`, `TEAL_PRIMARY`, `SAGE`, `AMBER`, `URGENT_RED`, etc.). Do not invent new colors, border widths, or spacing scales.
- Landings outside `DashboardLayout` may differ in spatial composition (more whitespace, editorial typography) but reuse the same color and font tokens.
- Banned hero pattern: centered text + big title + subtitle + two symmetrical rounded buttons + vast empty space. Use asymmetry, 2-column layouts, left-aligned text, editorial composition.

---

## 5. Testing strategy

### Python — pytest
- `tests/test_trend_features.py` is the only new test file.
- Coverage: 3 deterministic seeds × ~5 seeded-bad + ~20 stable babies per seed.
- **Pass criteria, all three seeds:**
  - Sensitivity ≥ 80% on seeded-bad babies (true positives / seeded-bad count)
  - False-positive rate ≤ 20% on stable babies (false positives / stable count)
- Test failure is a hard stop for the phase. Failed seeds get re-seeded, not the threshold relaxed.
- Existing `tests/test_safety_check.py` (6 tests) must continue to pass — trend tier must not regress safety guarantees.

### React — none formal
- `pnpm build` is the merge gate. TS errors or Vite build failures block merge.
- Visual review in browser before merge. Test routes: `/`, `/clinical-ai`, `/rpm`, `/strategy`, `/pipeline`, and every `/pipeline/<tab>`.
- Confirm trend block renders in at least one trace in `/pipeline/traces`.

### Live LLM evals
- Not part of acceptance for this phase. If user approves a paid live eval to verify the trend-aware handoff prompt, run on 10 traces (~$0.20 budgeted) and append results to STATUS.md.

---

## 6. Boundaries

### Always do
- Default to mock mode (`use_llm=False`) for any pipeline invocation.
- Use the existing theme tokens in React work. Use the existing tier-engine pattern in Python work.
- Treat the locked decisions in this spec as load-bearing. Any change requires re-spec.
- After Workstream A passes pytest, run `scripts/export_dashboard_data.py` once with a fixed seed to produce the canonical artifacts; commit only that seed's outputs to React `public/data/`.

### Ask first (require explicit user approval before acting)
- **Any `use_llm=True` invocation.** Surface cost estimate (trace count × ~$0.02) before spending. Current balance is ~$4.78 net of prior runs; assume ~$5 ceiling.
- **Merging `feat/trend-layer` (Python) or `feat/dual-framing` (React)** to main. React main auto-deploys to `sp02eval.mccaybarnes.health`. Python main is the source-of-truth for the artifact's narrative.
- **Changing any of these locked decisions:**
  - SatSeconds as the trend metric
  - New-tier integration (vs overlay)
  - 25 babies × 16 nights regen
  - EWMA (not CUSUM) for trend detection
  - No 4th LLM-judge axis on trends
  - JSX (not markdown-driven) landings
  - 4-destination top-level IA (Story | Business | Dashboard | Strategy)
  - `/` redirects to `/clinical-ai`
  - Strict 80%/20% acceptance thresholds with 3 seeds
- **CPT code list for `/rpm`** — explicitly held pending user's big reframe. Do not draft CPT content speculatively.

### Never do
- Auto-commit or auto-push in either repo. Staging and commit messages are user-driven.
- Enable Vite source maps. The React repo ships static and must not leak source paths.
- Run the exporter from inside `sync_to_frontend.sh`. The two scripts are deliberately separated.
- Add `react-markdown`, `remark-gfm`, or any other dependency to the React repo without surfacing the decision.
- Relitigate locked decisions during build. If a decision becomes wrong, surface and re-spec — don't quietly drift.
- Commit any file from `pm-private/` to a public repo. The React repo's git remote points to a separate GitHub repo (`beaRbahb/spo2-eval-dashboard`); the Python repo is the public one. Cross-contamination would defeat the privacy boundary.

---

## 7. Phase acceptance

The phase is done when **all** of the following are true:

- [ ] `pytest tests/test_trend_features.py` passes across 3 seeds with strict thresholds
- [ ] `pytest tests/test_safety_check.py` still passes (no regression)
- [ ] `python scripts/export_dashboard_data.py` produces 8 JSON artifacts (existing 7 + `trend-features.json`) plus `waveforms/`
- [ ] `bash scripts/sync_to_frontend.sh` copies all 8 + waveforms into `public/data/` with zero missing-file errors
- [ ] `pnpm build` in React repo completes clean
- [ ] `/clinical-ai`, `/rpm`, `/strategy`, `/pipeline`, and every `/pipeline/<tab>` route loads in browser
- [ ] `/` redirects to `/clinical-ai`
- [ ] Top-level 4-destination header strip renders on every route
- [ ] At least one trace in `/pipeline/traces` shows the `[TREND]` block in its handoff
- [ ] STATUS.md updated with v2 trend metrics
- [ ] LEARNINGS.md entry added for EWMA + trend handoff lessons
- [ ] User has reviewed and approved both `feat/trend-layer` and `feat/dual-framing` before any merge to main

---

## 8. Open items (held, not blocking spec)

- `/rpm` CPT code list — user's big reframe pending
- Whether to extend `/strategy`'s "Alert Follow-Up Agent" copy now that the trend tier exists in code (not just on the roadmap) — decide after Workstream A lands
- Whether `/clinical-ai`'s narrative pulls excerpts from `LEARNINGS.md` directly (would require markdown rendering) or restates them in JSX — leaning JSX-only per locked decision
