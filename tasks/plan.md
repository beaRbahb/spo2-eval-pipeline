# Implementation Plan: SPEC-v3 Trend Tier + Dual Framing + Pediatric Lifecycle

**Spec:** `SPEC-v3-trend-and-framing.md` (locked 2026-05-17)
**Repos:** `/Users/Sterdb/spo2-eval-pipeline/` (Python, branch `feat/trend-layer`) and `/Users/Sterdb/pm-private/spo2-eval-dashboard/` (React, branch `feat/dual-framing`)
**Author:** plan generated 2026-05-17

## Overview

Three workstreams across two repos:
- **A (Python).** Add 4th triage tier — SatSeconds-EWMA trend detection over 25 babies × 16 nights, condition labels as BabyProfile metadata only, `[TREND]` block wired into the nurse-handoff generator.
- **B (React).** Restructure to a 4-destination top-level IA, build two new landings (`/clinical-ai` and `/rpm`) and a four-panel value story, embed a lifecycle schematic in `/clinical-ai`, add a `/pipeline/trends` dashboard tab.
- **C (React).** Render failure-modes content as JSX inside `/clinical-ai` (no markdown rendering dependency).

The Python branch lands first because it produces `trend-features.json` that React Phase C consumes. React Phase B (landings) does NOT depend on trend data and can develop in parallel.

## Architecture Decisions (load-bearing — re-spec required to change)

- **SatSeconds** (not mean-SpO2 EWMA) is the trend metric.
- **EWMA** (not CUSUM) for trend detection. **Alpha ≈ 0.13 (half-life 5 nights)** — locked default; tune within ±0.05 only if PY-4 fails.
- Trend tier wired into orchestrator with `[TREND]` block in handoff — NOT a standalone page divorced from the pipeline.
- "Stable-but-trending" handoffs ship as **urgency=MONITOR + `[TREND]` block** — no new urgency level, no parser extension.
- Condition labels (AOP / CHD interstage / BPD) are **metadata only** on `BabyProfile` — no per-condition signal modulation.
- Lifecycle is a **schematic section inside `/clinical-ai`**, not its own route.
- Top-level IA: `Story (/clinical-ai) | Business (/rpm) | Dashboard (/pipeline) | Strategy (/strategy)`. `/` → `/clinical-ai`. Landings outside `DashboardLayout`.
- No `react-markdown`. Failure modes is JSX inside `ClinicalAI.tsx`.
- `export_dashboard_data.py` stays a single file — no refactor.
- **`trend-features.json` is object-keyed by `baby_id`** with `schema_version: 1`. Full schema locked in PY-3 below; every React consumer references that block.
- Strict **80% sensitivity / 20% FPR** thresholds across **3 canonical seeds locked in the test file** with **n=10 seeded-deteriorating + n=20 stable per seed**. Failure means the trend tier is broken, not the seeds — do NOT re-roll seeds.
- **Route breaking change accepted.** Existing `/coverage`, `/rules`, `/evals`, `/traces`, `/interop` → new `/pipeline/*` paths. No redirects. Document in PR description.
- **PipelineDataProvider scope: `/pipeline/*` subtree only.** Landings (`/clinical-ai`, `/rpm`, `/strategy`) use static imports from `src/data/headline_metrics.ts` — no provider, no JSON fetch.

## Dependency Graph

```
[Python feat/trend-layer]                       [React feat/dual-framing]

PY-1 BabyProfile.condition                       RX-1 SiteLayout + routes + sidebar trim
  + 25×16 defaults                                 │
   │                                               ├──→ RX-2 ClinicalAI scaffold (1,2,5)
PY-2 Plant deteriorating cohort                    │       │
   │                                               │       ├──→ RX-3 Failure modes JSX (sec 4)
PY-3 patterns/trend_features.py                    │       └──→ RX-5 Lifecycle schematic (sec 6) [cut #3]
   │                                               │
PY-4 tests/test_trend_features.py ─── GATE         ├──→ RX-6 RPM scaffold + Panel 1 (actors)
   │                                               │       │
PY-5 orchestrator wires trend tier                 │       ├──→ RX-7 Panel 2 (TAM ceiling caveats)
   │                                               │       ├──→ RX-8 Panel 3 (structural model + cite)
PY-6 handoff [TREND] block + stable-               │       └──→ RX-9 Panel 4 (copy rules + Owlet) ⚠
       but-trending template                       │
   │                                               └──→ RX-10 AgenticStrategy edit [cut #2]
PY-7 llm_utils STRICT_LIVE guardrails
   │                                              ─────────── PY sync must complete ─────
PY-8 exporter trend-features.json + 25×16
   │                                               RX-11 Trends.tsx [cut #4 — §9 revisit]
PY-9 sync_to_frontend.sh allowlist                 RX-12 TraceExplorer [TREND] + condition chip
   │                                               RX-13 CoverageFunnel 4th tier + Overview tile
(/clear marker — Python branch done, sync run)──→ (Gate C-§9 — keep dedicated Trends tab or cut)

                                                   DOC-1 STATUS.md + LEARNINGS.md updates
                                                   Gate D — pre-merge review + SPEC §7 acceptance
```

Cuttable per §8 (in order if overrunning): RX-2 generalization preview → RX-10 → RX-5 (compress to AOP-only) → RX-11 (merge into Coverage + TraceExplorer).

---

## Phase A — Python `feat/trend-layer`

### PY-1: BabyProfile.condition field + 25×16 cohort defaults

**Description:** Add a `condition` field (Literal["AOP","CHD_interstage","BPD"]) to `BabyProfile`. Wire condition assignment into `generate_baby_cohort` with the distribution ~10 AOP / 8 BPD / 7 CHD for n_babies=25. Update `generate_dataset` defaults to 25 babies × 16 nights. Condition is **metadata only** — does NOT modulate signal generation in this task.

**Acceptance criteria:**
- [ ] `BabyProfile` has a `condition: str` field with one of three values
- [ ] `generate_dataset()` with default args returns 400 traces (25 × 16)
- [ ] Condition distribution within ±1 of target: ~10 AOP, 8 BPD, 7 CHD (for seed=42)
- [ ] **Minimum 1 of each condition enforced** — generator asserts no condition class is empty across the cohort; halts with clear error if any seed produces 0 of a class
- [ ] Existing `tests/test_safety_check.py` still passes (6 tests)

**Verification:**
- [ ] `python -c "from collections import Counter; from src.data_gen.synthetic import generate_dataset; ts=generate_dataset(seed=42); print(len(ts)); print(Counter(t.baby.condition for t in ts))"`
- [ ] `pytest tests/test_safety_check.py -v`

**Dependencies:** None
**Files:** `src/data_gen/synthetic.py`, `src/config.py` (if defaults move there)
**Scope:** S

---

### PY-2: Plant deteriorating cohort via deterministic pattern override

**Description:** Tag the first 10 babies (by cohort index) as "deteriorating" — fully deterministic, no RNG draw for tag assignment. For these babies, **override `_assign_pattern` with a night-index function** that produces a trajectory: early nights draw from a normal-weighted distribution, middle nights from borderline, late nights from borderline-with-escalating-severity-multiplier or urgent. For the remaining ~15 stable babies, **narrow the per-night pattern distribution** — either draw once at baby creation and hold across nights, or draw from a narrower distribution centered on the baby-wide draw. Severity multiplier alone on existing stochastic pattern selection is insufficient because random pattern draws would produce "deteriorating" babies with random normal/artifact nights — breaks trajectory coherence.

Add a `seeded_deteriorating: bool` field on `BabyProfile` (or return alongside cohort) so PY-4 tests can assert ground truth.

**Acceptance criteria:**
- [ ] Exactly 10 babies tagged `seeded_deteriorating=True`, deterministic by cohort index (not RNG)
- [ ] `_assign_pattern` is overridden for deteriorating babies with a night-index function: early third → normal-weighted, middle third → borderline, late third → borderline-escalating or urgent
- [ ] Stable babies have narrowed per-night pattern distribution (draw-once-and-hold OR narrowed-per-night) — no random urgent nights for stable babies
- [ ] For deteriorating babies, per-baby SatSeconds regression slope across 16 nights is positive and statistically distinct from stable cohort
- [ ] For stable babies, SatSeconds is noisy around a flat trend (no monotonic drift)

**Verification:**
- [ ] Scripted check: compute per-(baby, night) SatSeconds, fit linear regression per baby, assert mean slope of deteriorating cohort > stable cohort by a meaningful margin
- [ ] Visual sanity: print SatSeconds trajectories for all 10 deteriorating + 5 sample stable babies

**Dependencies:** PY-1
**Files:** `src/data_gen/synthetic.py`
**Scope:** M

---

### PY-3: `patterns/trend_features.py` — run_trend_tier with EWMA

**Description:** New module mirroring the tier-engine pattern (single public `run_trend_tier(traces, tier1_results) -> dict[str, BabyTrendRecord]`, returning a baby_id-keyed dict to match the JSON shape downstream). Compute per-(baby, night) SatSeconds using GA-adjusted threshold (matches `handoff/generator.py:135` existing computation). Apply EWMA over the per-night SatSeconds series with **alpha=0.13 (half-life ≈ 5 nights)**. Derive per-baby `trend_score` (current EWMA value normalized against baseline) and `trend_direction`.

**Baseline definition:** mean SatSeconds over the baby's nights labeled "normal" or "artifact" by Tier 1 (these are the "non-event" nights). If a baby has fewer than 4 non-event nights, baseline is `null` and `trend_direction = "insufficient_data"`, `flagged=False`.

**Trend score → flagged threshold:** tune to hit 80/20 on the 3 canonical seeds locked in PY-4. **Report the final threshold value in PY-3 acceptance** so it's reproducible.

**Dataclass shape (Python):**
```python
@dataclass
class BabyTrendRecord:
    baby_id: str
    condition: str  # "AOP" | "CHD_interstage" | "BPD"
    n_nights: int
    sat_seconds_series: list[float]              # per-night SatSeconds
    ewma_series: list[float]                     # per-night EWMA value
    trend_score: float                            # current scalar
    trend_direction: str                          # "stable" | "improving" | "deteriorating" | "insufficient_data"
    flagged: bool
    flag_reason: str | None                       # human-readable when flagged, else None
    baseline_sat_seconds: float | None            # None if insufficient non-event nights
```

**JSON shape (locked — every React consumer references this):**
```json
{
  "schema_version": 1,
  "generated_at": "<ISO8601>",
  "babies": {
    "<baby_id>": { /* fields above, baby_id repeated inside record */ }
  }
}
```

**Acceptance criteria:**
- [ ] Function returns a `dict[baby_id, BabyTrendRecord]` with 25 entries for default cohort
- [ ] `n_nights == 16` per record
- [ ] `flagged=True` for all 10 deteriorating babies in canonical seed cohort (after threshold tune)
- [ ] EWMA alpha locked at 0.13 in module constants (only changeable via re-spec)
- [ ] **Final `trend_score` flag threshold documented in module docstring + plan.md** after PY-4 tune
- [ ] Edge: all-artifact baby → `trend_direction="insufficient_data"`, `baseline_sat_seconds=null`, `flagged=False`
- [ ] Edge: `n_nights < 4` → `trend_direction="insufficient_data"`, no flag
- [ ] No new dependencies — EWMA via numpy directly
- [ ] Module under ~300 lines (matches existing convention)

**Verification:**
- [ ] Smoke run from repl: `run_trend_tier(traces, tier1_results)` returns 25-entry dict, no crash
- [ ] Print `[(bid, r.flagged, r.trend_direction) for bid, r in records.items()]` and sanity-check shape

**Dependencies:** PY-1, PY-2
**Files:** `src/patterns/trend_features.py` (NEW), `src/patterns/__init__.py` (if exports needed)
**Scope:** M

---

### PY-4: tests/test_trend_features.py — 3 canonical seeds × strict 80/20 thresholds — **HARD GATE**

**Description:** Three canonical seeds **locked in the test file as module-level constants** (e.g., `CANONICAL_SEEDS = (42, 1234, 7890)`). For each seed, generate a cohort with **n=10 seeded-deteriorating + n=20 stable babies** (bumped from n=5 per arch review — at n=5 each missed baby drops sensitivity by 20%, at n=10 by 10%, giving real headroom). Pass criteria across all three seeds:
- Sensitivity ≥ 80% on seeded-deteriorating (≥8 of 10)
- FPR ≤ 20% on stable (≤4 of 20)

**Failure semantics: the trend tier is broken, not the seeds.** Do NOT re-roll seeds. Fix the trend tier (EWMA alpha within ±0.05, baseline window, trend_score threshold). If three fix attempts still fail, halt and re-spec.

**Acceptance criteria:**
- [ ] 3 canonical seeds documented in test file docstring with rationale ("chosen 2026-05-17 as fixed test fixtures; never re-roll")
- [ ] Per seed: 10 deteriorating + 20 stable cohort (use a separate generation hook from PY-1's 25-baby cohort if needed — these are *test fixtures*, not the production cohort)
- [ ] All three seeds pass 80%/20% thresholds
- [ ] Test docstring includes the final `trend_score` threshold value (locked at PY-3)

**Verification:**
- [ ] `python -m pytest tests/test_trend_features.py -v` → 3 tests pass (one per seed)

**Dependencies:** PY-3
**Files:** `tests/test_trend_features.py` (NEW)
**Scope:** M
**Risk:** This is the gating test. If canonical seeds fail after trend tier fixes, the EWMA+SatSeconds approach needs revisiting — not the seeds.

---

### Gate A1 — Trend test hard gate (after PY-4)
**Halt if failing. Do not continue.**
- [ ] `pytest tests/test_trend_features.py -v` passes (3 seeds × 80/20)
- [ ] `pytest tests/test_safety_check.py -v` still passes (no regression)
- [ ] If fails after 3 re-seed attempts → re-spec EWMA half-life or baseline window, do not proceed

---

### PY-5: Orchestrator wires trend tier + threads baby_trend_flag

**Description:** In `src/pipeline/orchestrator.py`, call `run_trend_tier(traces, tier1_results)` after expert queue and before handoff generation. Build a `baby_id → flagged` map. Add `baby_trend_flag: bool` to `FinalTriage` dataclass. Per-night labels are NOT overridden by trend tier — it's a parallel signal.

**Tier 2 stratification check:** with new 25×16 cohort + condition metadata, verify Tier 1 auto-labeled class distribution has ≥2 examples per class before Tier 2 training. If a class has <2 examples, surface a loud warning and use the `train_test_split` workaround pattern from LEARNINGS #16.

**Acceptance criteria:**
- [ ] `python -m src.pipeline.orchestrator` prints a `[Phase 4c] Running trend tier...` line and per-baby flagged count
- [ ] `FinalTriage.baby_trend_flag` is populated correctly (True for nights whose baby is flagged)
- [ ] Existing accuracy metrics in the printed summary are unchanged (trend tier does not alter per-night labels)
- [ ] Tier 2 training does NOT crash on stratify-class-too-small (LEARNINGS #16 redux check)
- [ ] Smoke-print Tier 1 class distribution to confirm ≥2 per class

**Verification:**
- [ ] `python -m src.pipeline.orchestrator` runs end-to-end without exception
- [ ] Output includes trend tier line; expert queue + tier1 + tier2 numbers unchanged from pre-trend baseline

**Dependencies:** PY-3 (PY-4 should pass first as gate)
**Files:** `src/pipeline/orchestrator.py`
**Scope:** S

---

### PY-6: Handoff [TREND] block + stable-but-trending template path

**Description:** In `src/handoff/generator.py`:
1. Extend emergency/urgent/borderline mock templates to inject a `[TREND] …` block when `baby_trend_flag=True`
2. Add a new template path `stable_but_trending` for nights where per-night triage is routine but baby-level flag fires — **urgency level is `MONITOR`** (existing parser handles, no extension needed). The `[TREND]` block carries the trend-specific reasoning.
3. **Artifact-trending edge case:** when per-night label = `artifact` AND `baby_trend_flag=True`, collapse to the existing artifact template — do NOT add a `[TREND]` block. Rationale: artifact label means we don't trust this night's SatSeconds, so we don't trust its contribution to the trend signal enough to act on. Note in the handoff summary something like "trend signal not actionable due to artifact-dominated night."
4. Update `_HANDOFF_PROMPT` (live) symmetrically — extra paragraph about trend-aware reasoning when flag is set
5. Pass `baby_trend_flag` through `generate_handoff(...)` signature

**Acceptance criteria:**
- [ ] Mock handoff for an urgent flagged baby contains `[TREND]` text
- [ ] Mock handoff for a normal-per-night flagged baby uses `stable_but_trending` template, urgency = `MONITOR`, contains `[TREND]` text
- [ ] Mock handoff for an artifact-per-night flagged baby uses existing artifact template, NO `[TREND]` block, summary notes "trend signal not actionable"
- [ ] Non-flagged babies do NOT contain `[TREND]` text
- [ ] `_HANDOFF_PROMPT` (live) references trend context when flag is set
- [ ] Existing urgency parser unchanged — handles `MONITOR` as today

**LEARNINGS #19 redux risk (explicit):** changing `_HANDOFF_PROMPT` without a live LLM eval pass is structurally identical to the v2 prompt regression that collapsed handoff quality 90% → 30%. The deferred eval (spec §9) is a **Gate D blocker for any public demo or recording**, not just a post-build go/no-go. Surface this risk explicitly at Gate D.

**Verification:**
- [ ] Scripted check on at least 4 cases: flagged-urgent, flagged-normal, flagged-artifact, non-flagged
- [ ] `python -m src.pipeline.orchestrator` prints sample handoffs; visually confirm [TREND] block appears in flagged-non-artifact outputs

**Dependencies:** PY-5
**Files:** `src/handoff/generator.py`
**Scope:** M

---

### PY-7: llm_utils STRICT_LIVE guardrails

**Description:** In `src/llm_utils.py`: add an `is_explicit: bool` field to `CostTracker` (default `False`). `reset_tracker(...)` sets `is_explicit=True` only when **both** `max_calls` and `max_spend_usd` are passed by the caller (use sentinel `_UNSET` defaults to detect explicit vs default). Add `STRICT_LIVE` env var support — when set, `call_llm` requires `tracker.is_explicit == True` before allowing the call. If not, raise a loud error referencing the budget that needs to be set.

**Acceptance criteria:**
- [ ] `CostTracker` gains `is_explicit: bool = False` field
- [ ] `reset_tracker(max_calls=X, max_spend_usd=Y)` sets `is_explicit=True` only when both args are explicitly passed (sentinel detection)
- [ ] `reset_tracker()` with no args leaves `is_explicit=False`
- [ ] With `STRICT_LIVE=1` and `is_explicit=False`, `call_llm(...)` raises a clear error naming the missing explicit budget
- [ ] Without `STRICT_LIVE`, behavior is unchanged (back-compat for existing orchestrator code path)

**Verification:**
- [ ] Scripted check: `STRICT_LIVE=1 python -c "from src.llm_utils import call_llm; call_llm('test')"` raises with explanatory message
- [ ] `STRICT_LIVE=1` + `reset_tracker(max_calls=10, max_spend_usd=0.50)` + `call_llm(...)` proceeds normally

**Dependencies:** None (independent)
**Files:** `src/llm_utils.py`
**Scope:** S

---

### PY-8: Exporter — trend-features.json + 25×16 defaults

**Description:** In `scripts/export_dashboard_data.py`: change `N_BABIES = 25, NIGHTS = 16`. Add `export_trend_features(data) -> dict` returning the **locked JSON shape from PY-3**: `{schema_version: 1, generated_at, babies: {baby_id: {...}}}`. Add to `write_json` call list. **Keep the script as a single file** — do NOT refactor per locked decision.

**Acceptance criteria:**
- [ ] `python scripts/export_dashboard_data.py --seed 42` succeeds without error
- [ ] `data/export/` contains 8 JSON files (existing 7 + `trend-features.json`) plus `waveforms/`
- [ ] `trend-features.json` matches the locked PY-3 schema exactly (object-keyed by baby_id, schema_version=1, generated_at present)
- [ ] `trend-features.json` has 25 entries under `babies`
- [ ] Existing 7 JSON files unchanged in shape (only data values change due to 25×16 vs 100×3)
- [ ] Waveforms folder has 400 files (25 × 16); total size under ~6MB (Cloudflare Pages bundle headroom)
- [ ] Script file still under ~700 lines (no refactor sprawl)

**Verification:**
- [ ] `python scripts/export_dashboard_data.py --seed 42`
- [ ] `ls data/export/*.json | wc -l` returns 8
- [ ] `python -c "import json; d=json.load(open('data/export/trend-features.json')); print(d['schema_version'], len(d['babies']))"` returns `1 25`
- [ ] `du -sh data/export/waveforms/` reports under ~6MB

**Dependencies:** PY-5, PY-6
**Files:** `scripts/export_dashboard_data.py`
**Scope:** S

---

### PY-9: sync_to_frontend.sh — add trend-features.json to allowlist

**Description:** Add `"trend-features.json"` to the `JSON_FILES` array in `scripts/sync_to_frontend.sh`. Script policy unchanged otherwise (does NOT regenerate; does NOT auto-commit).

**Acceptance criteria:**
- [ ] `bash scripts/sync_to_frontend.sh` succeeds with zero missing-file errors
- [ ] `trend-features.json` appears in the copied-files list output

**Verification:**
- [ ] `bash scripts/sync_to_frontend.sh`
- [ ] `ls /Users/Sterdb/pm-private/spo2-eval-dashboard/public/data/trend-features.json` exists

**Dependencies:** PY-8
**Files:** `scripts/sync_to_frontend.sh`
**Scope:** XS

---

### /clear marker — Python branch ready (after PY-9)
Not a gate. Natural context-clear point before dropping into React work. Quick sanity check:
- Exporter produces 8 JSON files + `waveforms/`
- `sync_to_frontend.sh` copies cleanly to React `public/data/`
- `git status` on `feat/trend-layer` clean / staged as expected

`/review-code` will auto-run at end of `/build` per workflow.

---

## Phase B — React `feat/dual-framing` landings (parallelizable with Phase A through PY-8)

### RX-1: SiteLayout + restructured routes + sidebar trim

**Description:**
1. NEW `src/layouts/SiteLayout.tsx` — top-level wrapper with 4-destination header strip (Story / Business / Dashboard / Strategy). Renders on every route. Theme tokens only. **Mobile note:** SiteLayout uses its own header; DashboardLayout's existing mobile hamburger lives inside the dashboard subtree and renders below SiteLayout's header — no conflict, but verify visually.
2. MOD `src/App.tsx` — route tree per spec §3:
   - `/` redirects to `/clinical-ai`
   - `/clinical-ai`, `/rpm`, `/strategy` mount under `SiteLayout` only (no PipelineDataProvider)
   - `/pipeline/*` mounts under `SiteLayout` > `PipelineDataProvider` > `DashboardLayout`
   - `/pipeline` (root, no sub-path) renders `PipelineOverview` (preserve existing index-route behavior)
3. MOD `src/layouts/DashboardLayout.tsx` — `NAV_ITEMS` paths update to new tree:
   - `/` → `/pipeline` (Pipeline Overview)
   - drop `/strategy` entirely (now top-level)
   - `/coverage` → `/pipeline/coverage`, `/rules` → `/pipeline/rules`, `/evals` → `/pipeline/evals`, `/traces` → `/pipeline/traces`, `/interop` → `/pipeline/interop`
   - add `/pipeline/trends` (NEW)

Trends page is a **pure-static stub** at this stage — no provider context, no JSON fetch (`trend-features.json` doesn't exist yet on the React side). Just a placeholder component returning a "coming soon" SectionCard. Fleshed out in RX-11 after PY sync runs.

**Acceptance criteria:**
- [ ] `/`, `/clinical-ai`, `/rpm`, `/strategy`, `/pipeline`, `/pipeline/coverage`, `/pipeline/rules`, `/pipeline/evals`, `/pipeline/traces`, `/pipeline/trends`, `/pipeline/interop` all load without 404
- [ ] Top-level 4-destination header renders on every route
- [ ] `/` redirects to `/clinical-ai`
- [ ] `/pipeline` renders PipelineOverview (not a 404 or blank)
- [ ] Sidebar no longer shows "Agentic AI Strategy"; does show "Trends"; all sidebar links route correctly under new `/pipeline/*` tree
- [ ] Landing routes do NOT mount PipelineDataProvider (verify by reading routing tree)
- [ ] Trends.tsx stub has zero data fetches (no `usePipelineData`, no `fetch("...trend-features.json")`)
- [ ] **Vite source maps remain disabled** — verify `vite.config.ts` has no sourcemap enablement and `pnpm build` output dist/ contains no `.map` files
- [ ] No new dependencies added
- [ ] Mobile: header strip stacks cleanly with dashboard hamburger on `<768px`

**Verification:**
- [ ] `pnpm dev`; click through all 4 top-level destinations and all 7 sidebar items
- [ ] `pnpm build` passes
- [ ] `find dist -name "*.map" | head` returns nothing
- [ ] Resize browser to mobile width; confirm no header overlap

**Dependencies:** None (React side foundation)
**Files:** `src/layouts/SiteLayout.tsx` (NEW), `src/App.tsx`, `src/layouts/DashboardLayout.tsx`, `src/pages/Trends.tsx` (NEW stub)
**Scope:** M

---

### RX-2: ClinicalAI scaffold — Hero + LLM-judge depth + generalization preview

**Description:** NEW `src/pages/ClinicalAI.tsx` with sections 1 (Hero — eval rigor, three-tier architecture, zero urgent false negatives), 2 (LLM-judge depth — clinical accuracy / handoff quality / artifact handling), 5 (generalization preview — one paragraph + single-direction link to /rpm, no return CTA).

**Hero must be editorial, NOT centered+two-buttons AI-slop.** Use asymmetric layout, 2-column composition, left-aligned text. Reuse existing UI components (`SectionCard`, `MetricCard`, `PageIntro`) and theme tokens.

**Metrics source:** NEW `src/data/headline_metrics.ts` — hand-maintained TS module exporting constants for the hero (clinical accuracy 90%, handoff quality 100%, artifact handling 100% from STATUS.md final pre-launch run, zero urgent false negatives, etc.). **Do NOT read from `public/data/*.json`** — landings stay provider-free per locked decision. Updated by hand when pipeline metrics shift (rare; happens at regen time).

Sections 3 (trend tier), 4 (failure modes), 6 (lifecycle) deferred to RX-3 / RX-4 / RX-5.

**Acceptance criteria:**
- [ ] Page renders at `/clinical-ai`
- [ ] Hero is asymmetric / editorial (passes the "doesn't look AI-generated" check)
- [ ] `src/data/headline_metrics.ts` exists and exports the 4-5 constants the hero + LLM-judge section consume
- [ ] LLM-judge section references clinical accuracy 90%, handoff quality 100%, artifact handling 100% (from STATUS.md final pre-launch numbers — all sourced from the new `headline_metrics.ts`)
- [ ] No `usePipelineData()` calls and no `fetch(...)` calls in ClinicalAI.tsx
- [ ] Generalization preview present at end with link to `/rpm`
- [ ] Inline CTAs deep-link to `/pipeline/evals`, `/pipeline/traces`, `/pipeline/coverage`

**Verification:**
- [ ] `pnpm dev`; visit `/clinical-ai`; confirm structure
- [ ] `pnpm build` passes
- [ ] `grep -E "usePipelineData|fetch\(" src/pages/ClinicalAI.tsx` returns nothing

**Dependencies:** RX-1
**Files:** `src/pages/ClinicalAI.tsx` (NEW), `src/data/headline_metrics.ts` (NEW)
**Scope:** M

---

### RX-3: ClinicalAI failure modes section (JSX, no markdown)

**Description:** Add section 4 to `ClinicalAI.tsx`. Content mined from LEARNINGS #1 (preterm baseline problem), #2 (artifact detection), #5 (Tier 2 accuracy gap), #17 (safety test design lesson), #19 (v2 prompt regression). JSX only — no `react-markdown`, no `remark-gfm`, no new deps. Each failure-mode card: what failed, why, what we learned, what a real system would need.

**Acceptance criteria:**
- [ ] Section renders with 4-5 distinct failure-mode cards
- [ ] All content is inline JSX
- [ ] No markdown-rendering dependency added
- [ ] Each card has the four content beats (what failed / why / lesson / production gap)

**Verification:**
- [ ] Visual review at `/clinical-ai`
- [ ] `grep -i markdown package.json` returns no new entries

**Dependencies:** RX-2
**Files:** `src/pages/ClinicalAI.tsx`
**Scope:** M

---

### RX-4: ClinicalAI trend tier section + hidden hypoxemia callout

**Description:** Add section 3 to `ClinicalAI.tsx`. Describe SatSeconds-EWMA trend tier and `[TREND]` handoff integration. Include the one-line callout: "Peer-reviewed evidence: 67% of BPD infants clinically ready to wean from oxygen had abnormal nocturnal oximetry on objective measurement (J Pediatr 2022)." Frames why the trend tier matters empirically.

**Acceptance criteria:**
- [ ] Section renders with trend tier explanation
- [ ] Hidden hypoxemia callout is visually prominent (≤2 sentences, citation visible)
- [ ] No `[TREND]`-rendering Tracex-style preview here (that lives in RX-12)

**Verification:**
- [ ] Visual review at `/clinical-ai`

**Dependencies:** RX-3 (sequential edits on same file)
**Files:** `src/pages/ClinicalAI.tsx`
**Scope:** S

---

### RX-5: ClinicalAI lifecycle schematic (section 6) — **CUT #3 candidate**

**Description:** Closing operating-model section in `ClinicalAI.tsx`. One representative AOP-or-trio synthetic patient overlaid on an abstract multi-month tier-progression timeline. Explicit framing line: "the platform operates on the rolling window shown here; the full clinical lifecycle plays out over the months illustrated."

**Cut path if overrunning (§8 #3):** AOP-only single trajectory; drop CHD and BPD overlays.

**Acceptance criteria:**
- [ ] Section renders with at least the AOP trajectory overlay
- [ ] Explicit rolling-window-vs-multi-month framing line present
- [ ] Built as inline JSX or a small component in `src/components/` — no new deps

**Verification:**
- [ ] Visual review at `/clinical-ai`
- [ ] `pnpm build` passes

**Dependencies:** RX-4
**Files:** `src/pages/ClinicalAI.tsx` (+ optional `src/components/LifecycleSchematic.tsx`)
**Scope:** M

---

### RX-6: RPM scaffold + Panel 1 (Today's economics — three-actor split)

**Description:**
1. NEW `src/pages/RPM.tsx` — hero with corrected framing ("operational infrastructure for pediatric home monitoring as a category, with adult RPM as a generalization, not the primary frame"); section that renders `ValueStoryPanels`; closing one-paragraph adult-RPM generalization
2. NEW `src/components/ValueStoryPanels.tsx` — scaffold + **Panel 1**: three sub-rows by ACTOR:
   - (a) Device manufacturer P&L: DME reimbursement $200-500/pt/mo (mark illustrative if no clean source), retention LTV
   - (b) Payer P&L: avoided ER/admission utilization ~$50-150/pt/mo cohort-attributable (AHRQ HCUPnet cited), prescriber E/M visit appropriateness
   - (c) Risk-bearing provider P&L: shared savings, quality bonuses for ACOs / pediatric value-based entities

**No row may blend two actors' P&Ls.**

**Acceptance criteria:**
- [ ] `/rpm` route loads
- [ ] Hero copy explicitly frames pediatric-as-primary, adult-as-generalization
- [ ] Panel 1 has three labeled sub-rows, one per actor
- [ ] Each row's numbers are illustrative-marked where no clean source
- [ ] AHRQ HCUPnet cited on the payer row

**Verification:**
- [ ] Visual review at `/rpm`
- [ ] `pnpm build` passes

**Dependencies:** RX-1
**Files:** `src/pages/RPM.tsx` (NEW), `src/components/ValueStoryPanels.tsx` (NEW)
**Scope:** M

---

### RX-7: ValueStoryPanels — Panel 2 (CPT parity TAM ceiling)

**Description:** Add Panel 2 to `ValueStoryPanels.tsx`. Explicit framing line: "billable capacity if codes applied at full utilization." All three caveats on the panel:
- "Assumes adult RPM coverage extended to infants (currently doesn't apply)"
- "Assumes full 99457 + 2× 99458 utilization (real-world averages lower)"
- "Anchor: CMS PFS 2026 Final Rule"

Static math (no calculator):
- 99453 setup: $22 one-time
- 99454 device supply: $52/mo
- 99457 first 20 min: $52/mo
- 99458 each +20 min × 2: $82/mo
- Recurring ceiling: $135-180/pt/mo
- × estimated 50K-100K US infants on prescribed home pulse-ox = $80M-$200M annual category ceiling

**Acceptance criteria:**
- [ ] Panel 2 renders with the three caveats visible
- [ ] "Billable capacity at full utilization" framing line present
- [ ] No realized-revenue language anywhere
- [ ] Static graphic only — NO interactive calculator
- [ ] CMS PFS 2026 anchor cited

**Verification:**
- [ ] Visual review at `/rpm`

**Dependencies:** RX-6
**Files:** `src/components/ValueStoryPanels.tsx`
**Scope:** S

---

### RX-8: ValueStoryPanels — Panel 3 (Capped-rental "structural model that would need to exist")

**Description:** Add Panel 3 to `ValueStoryPanels.tsx`. Framing: "the structural model that would need to exist," NOT "the model we'd adopt." Four stages with overlaid condition-specific duration bars:

1. Trial period (months 0-3) — CPAP-analog 12-week compliance demonstration
2. Capped rental — condition-specific:
   - AOP ~3-6 mo (Eichenwald 2016 AAP)
   - CHD interstage 3-6 mo (Rudd 2020 AHA)
   - BPD 12-18 mo (Everitt 2020)
3. Step-down period — reduced monitoring intensity
4. Ownership transition + supply coverage

Policy-lift note: "pediatric home pulse-ox today is commercial + Medicaid with no equivalent rulemaking; this would require CMS rulemaking for dual-eligibles OR state-by-state Medicaid + commercial payer adoption — a 5-10 year roadmap."

**Acceptance criteria:**
- [ ] Panel 3 renders with all four stages
- [ ] Three condition-specific duration bars cited (Eichenwald, Rudd, Everitt)
- [ ] Policy-lift roadmap note present ("would need to exist" framing, NOT "would adopt")
- [ ] Timeline diagram with duration overlays

**Verification:**
- [ ] Visual review at `/rpm`

**Dependencies:** RX-7
**Files:** `src/components/ValueStoryPanels.tsx`
**Scope:** M

---

### RX-9: ValueStoryPanels — Panel 4 (Caregiver continuation tier) ⚠ ETHICAL FLOOR

**Description:** Add Panel 4 to `ValueStoryPanels.tsx`. Two-timeline diagram side-by-side:
- (a) Medical necessity timeline (payer view): defined by clinical trajectory, ends at AOP resolution / BPD wean / CHD Stage 2
- (b) Caregiver need timeline: defined by family readiness; outlasts medical timeline

Three tiers:
- Active monitoring (payer-funded)
- Step-down (payer-funded, lower rate)
- Wellness/caregiver (family-paid subscription, **$9.99-15/mo band** — exact figure as **inline parenthetical with footnote link** to comparable consumer wellness wearable subscription benchmarks; anchor to Owlet 360 ~$9.99/mo)

#### Copy review checklist (draft — user locks before Gate B-Panel4)

**Banned phrases anywhere on panel** (except where noted):
- "peace of mind"
- "anxiety" — exception: the literal "talk to your provider if anxiety persists" line
- "worry" / "worried"
- "stress" / "stressful"
- "PTSD"
- "trauma" / "traumatic"
- "postpartum"
- "mental health"
- "depression"
- "fear"
- "panic"
- "sleepless"

**Required content:**
- Literal phrase "talk to your provider if anxiety persists" — placed at end of panel, NOT buried mid-body
- "You've already built the habit" OR a paraphrase that passes the test "describes behavior continuation, not emotional state"
- Explicit "opt-in" language for the wellness tier (the family chooses; not auto-enrolled)
- Explicit "your baby is medically stable" OR "medical monitoring has concluded" framing **before** any continuation language

**Owlet reference policy:**
- Abstract OK: "consumer wellness wearable," "post-discharge wellness subscription," "the consumer device category"
- Explicit names banned without acknowledgment: "smart sock," "Owlet 360," "Dream Sock" — unless paired with explicit acknowledgment of the 2021 FDA warning letter context AND explanation of how tier-aware framing prevents the same misstep
- Brand-name acknowledgment, when used, must be in body copy NOT a footnote

**Acceptance criteria:**
- [ ] Panel 4 renders the two timelines diverging at medical-necessity endpoint
- [ ] Three tiers shown with the wellness tier price within $9.99-15, format = inline parenthetical + footnote link
- [ ] All banned phrases absent (verify with `grep -i` against the checklist above)
- [ ] All required content present
- [ ] Owlet either abstract OR accompanied by 2021 acknowledgment in body copy — no naked naming, no footnote-only acknowledgment

**Verification:**
- [ ] Visual review at `/rpm`
- [ ] Automated grep check against banned/required phrase lists
- [ ] **Gate B-Panel4 — user copy review checkpoint** — user reviews and locks the checklist, then signs off on the panel copy against the locked checklist before RX-9 is marked complete

**Dependencies:** RX-8
**Files:** `src/components/ValueStoryPanels.tsx`
**Scope:** M
**Risk:** Highest-stakes copy task. Ethical floor — not a preference.

---

### RX-10: AgenticStrategy edit — cross-link to /rpm — **CUT #2 candidate**

**Description:** ~30-min edit to `src/pages/AgenticStrategy.tsx`. Add one-paragraph cross-link at the end of the reimbursement-cost section saying "for full reimbursement framing see /rpm." Existing AI-inference-cost table stays unchanged.

**Acceptance criteria:**
- [ ] Cross-link paragraph present at end of reimbursement section
- [ ] Existing reimbursement table unchanged

**Verification:**
- [ ] Visual review at `/strategy`

**Dependencies:** RX-1
**Files:** `src/pages/AgenticStrategy.tsx`
**Scope:** XS

---

### Gate B-Panel4 — Ethical-floor copy review (during RX-9)
**Block on user signoff before considering RX-9 complete.** Panel 4 copy must satisfy:
- [ ] No postpartum-anxiety language anywhere on the panel
- [ ] Continuity-of-relationship framing (not anxiety mitigation)
- [ ] "Talk to your provider if anxiety persists" line present
- [ ] "You've already built the habit" anchor (not "NICU parent PTSD")
- [ ] Owlet: either abstract OR explicit with 2021 FDA warning letter acknowledgment — no naked naming
- [ ] Wellness tier price within $9.99-15 with visible justification

### /clear marker — React landings done (after RX-10)
Not a gate. Natural context-clear point before trend integration work. Quick sanity check:
- All routes load (`/`, `/clinical-ai`, `/rpm`, `/strategy`, all `/pipeline/*`)
- `pnpm build` passes
- No `react-markdown` / `remark-gfm` in package.json
- Hero on `/clinical-ai` is editorial, not centered AI-slop

---

## Phase C — React trend data integration (requires PY sync complete)

### RX-11: Trends.tsx — dedicated /pipeline/trends page — **CUT #4 candidate, §9 REVISIT POINT**

**Description:** Flesh out `src/pages/Trends.tsx` to consume `trend-features.json` (object-keyed by baby_id per PY-3 schema). Per-baby trend records with condition chip (AOP / CHD interstage / BPD), EWMA series viz (Plotly), planted "trending worse" trajectories labeled "ground truth for demo," and a "Why no eval on trends yet" section explaining honestly there's no 4th LLM-judge axis.

**Reads** `public/data/trend-features.json` and joins on `baby_id` with traces-meta.json for per-trace context. Verify `schema_version === 1` on load; if not, show explicit version-mismatch error.

**§9 revisit at end of build:** if trend signals feel awkwardly split across Trends + Coverage + TraceExplorer, fall back per §8 cut #4 — merge into Coverage tier-slice + TraceExplorer trend column, drop the dedicated tab.

**Acceptance criteria:**
- [ ] Page renders at `/pipeline/trends`
- [ ] 25 babies displayed (one card per baby_id key in `babies` object)
- [ ] Deteriorating babies visually distinct from stable (e.g., color-coded chip or border)
- [ ] EWMA chart renders without console errors
- [ ] Planted trajectories explicitly labeled "ground truth"
- [ ] Honest "no 4th LLM-judge axis" explanation present
- [ ] `schema_version` check: if `trend-features.json` is missing or `schema_version !== 1`, render explicit error state (NOT white screen, NOT silent fallback)

**Verification:**
- [ ] Visual review at `/pipeline/trends`
- [ ] Temporarily rename `trend-features.json` and confirm error state renders gracefully
- [ ] §9 decision logged: keep dedicated tab vs cut #4 merge

**Dependencies:** PY-9 + sync run
**Files:** `src/pages/Trends.tsx`
**Scope:** M

---

### RX-12: TraceExplorer — render [TREND] block + condition chip

**Description:** In `src/pages/TraceExplorer.tsx`:
- When a handoff includes a `[TREND]` block, render it visually distinct
- Add a condition chip (AOP / CHD interstage / BPD) per trace from the baby metadata (sourced from `traces-meta.json` baby object; condition lives on `BabyProfile`, not on trend-features — trend-features only references baby_id)
- Cross-reference `trend-features.json` to determine flagged status when rendering [TREND] block context

**Acceptance criteria:**
- [ ] At least one trace in the displayed list shows the `[TREND]` block
- [ ] All traces display a condition chip
- [ ] Existing trace display behavior unchanged for non-flagged traces
- [ ] Edge: a `baby_id` present in traces but missing from `trend-features.json` → render "no trend data" fallback for that trace; log to console; do NOT crash

**Verification:**
- [ ] Visual review at `/pipeline/traces`
- [ ] Filter or scroll to a flagged baby; confirm [TREND] renders
- [ ] Temporarily corrupt one `baby_id` mapping; confirm fallback works

**Dependencies:** PY-9 + sync run
**Files:** `src/pages/TraceExplorer.tsx`
**Scope:** S

---

### RX-13: CoverageFunnel + PipelineOverview — 4th-tier visibility

**Description:**
- `src/pages/CoverageFunnel.tsx` — add 4th tier slice for trend tier coverage (per-baby flagged count)
- `src/pages/PipelineOverview.tsx` — one tile showing trend-tier coverage

**Acceptance criteria:**
- [ ] 4th tier slice renders on `/pipeline/coverage`
- [ ] Trend-tier tile renders on `/pipeline` (root)
- [ ] Existing tiers / slices unchanged

**Verification:**
- [ ] Visual review at both routes

**Dependencies:** PY-9 + sync run
**Files:** `src/pages/CoverageFunnel.tsx`, `src/pages/PipelineOverview.tsx`
**Scope:** S

---

### Gate C-§9 — Trends-tab surface decision (after RX-11)
**Quick decision call.** After Trends.tsx is implemented, evaluate whether trend signals split awkwardly across Trends + Coverage + TraceExplorer.
- [ ] Decision logged: **keep dedicated Trends tab** OR **apply cut #4** (merge into Coverage tier-slice + TraceExplorer trend column, drop dedicated tab)
- [ ] If cut #4 chosen: RX-12 + RX-13 absorb the surface area; Trends.tsx route removed

---

## Phase D — Polish + gate

### DOC-1: STATUS.md + LEARNINGS.md updates + citation verification

**Description:**
- `STATUS.md`: add v3 trend tier metrics section (n_babies=25, n_nights=16, sensitivity/FPR on canonical seeds, flagged count, condition distribution, locked EWMA alpha, locked trend_score threshold) and IA change note (4-destination top-level)
- `LEARNINGS.md`: new entry covering EWMA-over-CUSUM rationale, trend handoff template lessons (including LEARNINGS #19 deferred-eval risk explicitly), four-panel framing decisions, Owlet reference policy, route breaking-change rationale

**Citation verification (manual sub-task):** before Gate D, verify the 5-6 load-bearing citations are correctly cited:
- [ ] J Pediatr 2022 "67% of BPD infants clinically ready to wean from oxygen had abnormal nocturnal oximetry" — verify paper title, authors, year, and the 67% figure exactly
- [ ] Eichenwald 2016 AAP — verify AOP discharge guidance, 43 wks PMA + stable interval
- [ ] Rudd 2020 AHA — verify CHD interstage monitoring, Stage 1 → Stage 2 duration
- [ ] Everitt 2020 — verify BPD home oxygen weaning median ~14 mo corrected age
- [ ] CMS PFS 2026 Final Rule — verify the 99453/99454/99457/99458 rates exactly
- [ ] AHRQ HCUPnet — verify the ~$50-150/pt/mo avoided utilization figure has a defensible source path

**Acceptance criteria:**
- [ ] STATUS.md updated with v3 metrics
- [ ] LEARNINGS.md gains one new entry covering all four topics above
- [ ] All 6 citations verified (user confirms each manually)
- [ ] Dates current
- [ ] No broken cross-references to renamed/moved files

**Dependencies:** All preceding tasks
**Files:** `STATUS.md`, `LEARNINGS.md`
**Scope:** S

---

### GATE-1: Pre-merge review — user-driven

**Description:** User runs `git diff` on `feat/trend-layer` and `feat/dual-framing`. Re-reads SPEC-v3 §6 boundaries. Specifically reviews Panel 4 copy against the locked checklist and Owlet policy. Confirms ready to merge each branch.

**Acceptance criteria:**
- [ ] User-reviewed `git diff` on `feat/trend-layer`
- [ ] User-reviewed `git diff` on `feat/dual-framing`
- [ ] Panel 4 copy verified clean (locked checklist from RX-9)
- [ ] Owlet references verified per policy
- [ ] All 6 citations verified (DOC-1)
- [ ] User explicitly approves each merge
- [ ] **PUBLIC DEMO BLOCKER:** if a public demo or Loom recording is planned, the trend-aware handoff prompt must have a live LLM eval pass (~$0.20 for 10 traces) BEFORE the demo, per LEARNINGS #19 risk. If no public demo is planned in the near term, this blocker can defer.

**Hard rules:**
- NO auto-commit
- NO auto-push
- NO auto-merge (React main auto-deploys to `sp02eval.mccaybarnes.health`)

**Dependencies:** DOC-1
**Scope:** N/A (manual)

---

### Gate D — Pre-merge review + SPEC §7 acceptance (final)
- [ ] `pytest tests/test_trend_features.py` passes 3 seeds × 80/20
- [ ] `pytest tests/test_safety_check.py` still passes
- [ ] `python scripts/export_dashboard_data.py` produces 8 JSON + waveforms/
- [ ] `bash scripts/sync_to_frontend.sh` copies cleanly
- [ ] `pnpm build` passes
- [ ] All routes load
- [ ] `/` redirects to `/clinical-ai`
- [ ] 4-destination header on every route
- [ ] At least one trace shows `[TREND]` block
- [ ] Lifecycle schematic renders with rolling-window framing
- [ ] Four-panel value story renders with framing rules respected
- [ ] Hidden hypoxemia callout present
- [ ] Failure modes JSX section present (no markdown)
- [ ] Generalization preview present
- [ ] AgenticStrategy edit complete
- [ ] STATUS.md + LEARNINGS.md updated
- [ ] User-approved both branches

---

## Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| PY-4 trend tier tests fail thresholds | **High** — gates whole phase | Re-seed up to 3 times. Do NOT relax thresholds. If still failing → halt, re-spec EWMA half-life or baseline window. |
| `/pipeline/trends` signals split awkwardly | Medium | §9 revisit at end of build. Cut #4 ready: merge into Coverage + TraceExplorer. |
| Panel 4 copy drifts toward anxiety framing | **Critical** — ethical floor | Explicit copy-review checkpoint in CHECKPOINT B. Four mandatory rules listed verbatim in RX-9. |
| Owlet named without 2021 context | **Critical** — ethical floor | Default abstract. Explicit naming only after 2021-acknowledgment review. |
| React route restructure breaks existing dashboard | Medium | RX-1 verified by clicking through all 7 existing sidebar routes before any landings work. |
| Exporter refactor temptation | Low | Locked decision — single file. Acceptable for the file to grow. |
| Branch merges to main without review | **Critical** | GATE-1 enforced. No auto-commit / auto-merge anywhere in the plan. |
| Live LLM call without budget | High — burns balance | PY-7 STRICT_LIVE guardrails + §6 "ask first" boundary. |
| Cross-contamination of `pm-private/` files into public repo | **Critical** — privacy boundary | Each task scoped to one repo. No cross-repo file copying except via `sync_to_frontend.sh` (allowlist enforced). |

---

## Open questions (require user input)

- **Before starting:** Confirm SPEC-v3 §6 boundaries acknowledged and task ordering acceptable. If different sequencing preferred (e.g., React landings first), reorder.
- **At RX-9 (Panel 4):** Pick exact wellness tier price within $9.99-15 band — copy author choice with visible justification on the panel.
- **At GATE-1 / post-build:** Live LLM eval go/no-go for trend-aware handoff (~$0.20 for 10 traces) — separately approved, not part of acceptance.

---

## Held items (not in plan, tracked here)

- Live LLM eval on trend-aware handoff (~$0.20) — post-build go/no-go per SPEC-v3 §9
- Wellness tier exact price — decided during RX-9
- Loom recording plan — outside SPEC scope, plan separately when build is acceptance-ready
