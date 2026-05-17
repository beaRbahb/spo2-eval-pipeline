# SPEC v3 — Trend Tier + Dual Framing + Pediatric Lifecycle

**Status:** locked 2026-05-17 at the framing level. Drives `/plan` next.
**Supersedes:** `SPEC-v2-trend-and-framing.md` (retained as evolution history; do not edit).
**Historical:** `SPEC.md` (April 2026, phases 1-7 original build) — retained as v1 context.
**Repos in scope:** `/Users/Sterdb/spo2-eval-pipeline/` (Python) and `/Users/Sterdb/pm-private/spo2-eval-dashboard/` (React).

---

## 1. Objective

Convert the existing 3-tier triage demo into a closed-loop, dual-framed pediatric monitoring portfolio artifact. Three workstreams:

- **A — Trend tier (Python).** Add a 4th triage tier that detects multi-night deterioration via SatSeconds-based EWMA. Regenerate synthetic data at 25 babies × 16 nights. Tag each baby with a clinical condition label (AOP / CHD interstage / BPD) as metadata. Wire the trend signal into the existing nurse-handoff generator so a `[TREND]` block renders in stable-but-trending-worse handoffs.
- **B — Dual framing + IA (React).** Add two new landings — `/clinical-ai` (eval-driven-dev narrative for PM-at-AI-co + clinical informatics audiences) and `/rpm` (corrected "today vs tomorrow" reimbursement framing with a four-panel value story). Restructure to a 4-destination top-level IA: `Story | Business | Dashboard | Strategy`. Embed a lifecycle schematic in `/clinical-ai` as the closing operating-model section.
- **C — Failure-modes surface (React).** Render the eval-discipline failure-modes content as a JSX section inside `/clinical-ai`, no markdown rendering dependency.

### Theme
"Building the data for the story." The artifact's value is not the dashboard — it's the demonstrated discipline of generating synthetic data, building tiered triage, running LLM-as-judge evals, surfacing clinical gaps in review, fixing them, and re-evaluating. The trend tier extends that loop by another turn; the dual framing makes the loop legible to two different audiences; the lifecycle schematic shows the operating model the architecture implies.

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

# Existing safety tests must continue to pass
python -m pytest tests/test_safety_check.py -v

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
                                 monotonic SatSeconds deterioration across the 16-night
                                 sequence. Add `condition: Literal["AOP", "CHD_interstage",
                                 "BPD"]` to BabyProfile as METADATA ONLY — no per-condition
                                 signal modulation. Cohort distribution: ~10 AOP, 8 BPD,
                                 7 CHD interstage. Per-night signal generation remains
                                 GA-adjusted only, as today.
  patterns/
    trend_features.py       NEW: EWMA over per-night SatSeconds; per-baby trend record
                                 {baby_id, condition, ewma_series, trend_score,
                                  trend_direction, n_nights, flagged: bool}.
                                 Baseline = nightly median SpO2 during non-event periods
                                 (simple — NOT the personalized low-variance-window
                                 baseline from v3 plan; cut for budget).
  pipeline/
    orchestrator.py         MOD: run trend tier after per-night Tier 1/2/3; attach
                                 baby-level trend flag to each night's FinalTriage so the
                                 handoff can consume it. Trend tier does NOT override
                                 per-night labels — it adds a parallel signal.
  handoff/
    generator.py            MOD: emergency/urgent templates render an optional [TREND] block
                                 when baby-level flag is set; add new "stable-but-trending"
                                 template path for nights where per-night triage is routine
                                 but the multi-night flag fires. Live LLM prompt updated to
                                 match (mock-only execution this phase).
  llm_utils.py              MOD: loud-fallback guardrails — CostTracker assertion that
                                 errors loudly if use_llm=True is invoked without
                                 explicit budget; STRICT_LIVE=1 env var to enforce.

scripts/
  export_dashboard_data.py  MOD: write new artifact data/export/trend-features.json;
                                 use n_babies=25, nights_per_baby=16 as new defaults.
                                 Keep as SINGLE FILE — do NOT refactor into 6 modules
                                 (bikeshedding under budget pressure).
  sync_to_frontend.sh       MOD: add trend-features.json to JSON_FILES allowlist.

tests/
  test_trend_features.py    NEW: 3 deterministic seeds. Per seed: ~5 seeded-bad +
                                 ~20 stable babies. Pass criteria, all 3 seeds:
                                 sensitivity ≥ 80% on seeded-bad, FPR ≤ 20% on stable.
                                 Strict thresholds, no relaxation.

SPEC-v3-trend-and-framing.md NEW: this file.
SPEC-v2-trend-and-framing.md KEEP: superseded but retained as evolution history.
SPEC.md                      KEEP: historical v1, do not edit.
STATUS.md                    MOD (post-build): update with v3 trend tier metrics, IA change.
LEARNINGS.md                 MOD (post-build): entry on EWMA-over-CUSUM, trend handoff
                                               template lessons, four-panel value story
                                               framing decisions, Owlet reference policy.

docs/ (or content lives in React JSX — see below)
                            NO new markdown rendering. Failure modes content lives
                            directly as JSX in src/pages/ClinicalAI.tsx subsection.
                            Day-1 "failure modes markdown doc" from v3 plan is CUT.
```

### React repo — files added or modified

```
src/
  layouts/
    SiteLayout.tsx          NEW: top-level wrapper with 4-destination header strip.
                                 Renders on every route. No sidebar. Theme tokens only.
    DashboardLayout.tsx     MOD: nests under SiteLayout. Sidebar drops the "Strategy"
                                 entry (Strategy moves to top-level). Sidebar adds
                                 "Trends" entry for the new trend tier surface.

  pages/
    ClinicalAI.tsx          NEW: JSX long-form landing.
                                 Narrative sections (in order):
                                 1. Hero — eval rigor, three-tier architecture, zero
                                    urgent false negatives
                                 2. LLM-judge depth (clinical accuracy, handoff quality,
                                    artifact handling)
                                 3. Trend tier — SatSeconds EWMA, [TREND] handoff
                                    integration. ONE-LINE CALLOUT: "Peer-reviewed
                                    evidence: 67% of BPD infants clinically ready to
                                    wean from oxygen had abnormal nocturnal oximetry on
                                    objective measurement (J Pediatr 2022)." Frames why
                                    the trend tier matters empirically.
                                 4. Failure modes — JSX section, content mined from
                                    LEARNINGS #1, #2, #5, #17, #19. NO markdown render.
                                 5. Generalization preview — one paragraph + single-
                                    direction link to /rpm. No return CTA.
                                 6. Lifecycle schematic — closing operating-model
                                    section. One representative AOP-or-trio synthetic
                                    patient overlaid on the early section of an
                                    abstract multi-month tier-progression timeline.
                                    Explicitly framed: "the platform operates on the
                                    rolling window shown here; the full clinical
                                    lifecycle plays out over the months illustrated."
                                 Inline CTAs deep-link to /pipeline/evals, /pipeline/traces,
                                 /pipeline/coverage, /pipeline/trends.
                                 Audience: PM at AI co + clinical informatics.

    RPM.tsx                 NEW: JSX two-column "today vs tomorrow" landing.
                                 Sections:
                                 1. Hero — corrected framing: "operational infrastructure
                                    for pediatric home monitoring as a category, with
                                    adult RPM as a generalization, not the primary frame"
                                 2. Four-panel value story (ValueStoryPanels.tsx — see
                                    below)
                                 3. Adult RPM generalization — one paragraph

    AgenticStrategy.tsx     MOD (~30 min): one-paragraph edit pointing reimbursement
                                            readers at /rpm. The existing AI-inference-cost
                                            table stays but adds a "for full reimbursement
                                            framing see /rpm" line. No other changes.

  components/
    ValueStoryPanels.tsx    NEW: four-panel component, lives on /rpm.

                            Panel 1 — Today's economics.
                              Three sub-rows by ACTOR (no P&L mixing):
                              (a) Device manufacturer's P&L: DME reimbursement
                                  ($200-500/pt/mo, marked illustrative if no clean
                                  source), retention LTV
                              (b) Payer's P&L: avoided ER/admission utilization
                                  (~$50-150/pt/mo cohort-attributable, AHRQ HCUPnet
                                  cited), prescriber E/M visit appropriateness
                              (c) Risk-bearing provider's P&L: shared savings, quality
                                  bonuses for ACOs / pediatric value-based entities
                              Each row labeled by actor. No blending.

                            Panel 2 — The CPT parity possibility (TAM ceiling).
                              Explicit framing: "billable capacity if codes applied at
                              full utilization."
                              Caveats stated on the panel:
                              - "Assumes adult RPM coverage extended to infants
                                (currently doesn't apply)"
                              - "Assumes full 99457 + 2× 99458 utilization (real-world
                                averages lower)"
                              - "Anchor: CMS PFS 2026 Final Rule"
                              Math:
                              - 99453 setup: $22 one-time
                              - 99454 device supply: $52/mo
                              - 99457 first 20 min: $52/mo
                              - 99458 each +20 min × 2: $82/mo
                              - Recurring ceiling: $135-180/pt/mo
                              - × estimated 50K-100K US infants on prescribed home
                                pulse ox = $80M-200M annual category ceiling
                              Static graphic, NO interactive calculator.

                            Panel 3 — Capped-rental + step-down model (CPAP analog).
                              Reframed: "the structural model that would need to exist,"
                              NOT "the model we'd adopt." Policy-roadmap honest.
                              Four stages:
                                1. Trial period (months 0-3) — CPAP-analog 12-week
                                   compliance demonstration
                                2. Capped rental — condition-specific duration:
                                   AOP ~3-6 mo (NICU discharge → 43 wks PMA + stable
                                     interval; Eichenwald 2016 AAP)
                                   CHD interstage 3-6 mo (Stage 1 → Stage 2 palliation;
                                     Rudd 2020 AHA)
                                   BPD 12-18 mo (median home oxygen weaning ~14 mo
                                     corrected age; Everitt 2020)
                                3. Step-down period — reduced monitoring intensity
                                4. Ownership transition + supply coverage
                              Note on policy lift: "pediatric home pulse-ox today is
                              commercial + Medicaid with no equivalent rulemaking; this
                              would require CMS rulemaking for dual-eligibles OR state-
                              by-state Medicaid + commercial payer adoption — a 5-10
                              year roadmap."
                              Visual: timeline diagram with overlaid condition-specific
                              duration bars.

                            Panel 4 — Caregiver continuation tier (the dual-timeline).
                              Two timelines side-by-side:
                              (a) Medical necessity timeline (payer view): defined by
                                  clinical trajectory, ends at AOP resolution / BPD
                                  wean / CHD Stage 2
                              (b) Caregiver need timeline: defined by family readiness,
                                  outlasts medical timeline
                              Three tiers shown:
                              - Active monitoring (payer-funded)
                              - Step-down (payer-funded, lower rate)
                              - Wellness/caregiver (family-paid subscription, $9.99-15/mo
                                band — copy author picks exact figure with visible
                                justification; anchor to Owlet 360 ~$9.99/mo)

                              COPY RULES (mandatory before public):
                              1. NO postpartum-anxiety language. Medical-intervention
                                 claim territory.
                              2. Position as continuity-of-relationship post-medical-
                                 necessity, NOT as anxiety mitigation.
                              3. Include "talk to your provider if anxiety persists"
                                 line on the panel.
                              4. Anchor to "you've already built the habit, here's an
                                 opt-in continuation" — NOT "NICU parent PTSD."

                              OWLET REFERENCE POLICY:
                              - Default: abstract — "a consumer-grade wellness
                                subscription post-discharge"
                              - Explicit Owlet naming only when accompanied by
                                acknowledgment of the 2021 FDA warning letter history
                                and explanation of how tier-aware framing prevents the
                                same misstep

                              Visual: two parallel timelines diverging at the medical-
                              necessity endpoint, with a "graduation" transition
                              between coverage and wellness tiers.

  pages/
    [no separate MonitoringLifecycle.tsx route — lifecycle is a section inside
     ClinicalAI.tsx, not its own page]

    [new dashboard tab — Trends]
    Trends.tsx              NEW: dedicated /pipeline/trends tab. Surfaces:
                                 - Per-baby trend records from trend-features.json
                                 - Condition label as chip per patient (AOP / CHD
                                   interstage / BPD)
                                 - EWMA series viz (Plotly)
                                 - Planted "trending worse" trajectories explicitly
                                   labeled "ground truth for demo"
                                 - "Why no eval on trends yet" section (no 4th LLM-
                                   judge axis — explained honestly)
                                 Sits alongside existing dashboard tabs.
                                 Treated as the 4th tier's primary surface.
                                 NOTE: revisit during build if signals feel awkwardly
                                 split across Trends/Coverage/TraceExplorer — fallback
                                 is to merge into Coverage tier-slice + TraceExplorer
                                 trend column.

  pages/TraceExplorer.tsx   MOD (small): render [TREND] block in handoffs when trend
                                          flag is set. Add condition chip per trace.

  pages/CoverageFunnel.tsx  MOD (small): add 4th tier slice for trend tier coverage
                                          (per-baby flagged count).

  pages/PipelineOverview.tsx MOD (small): one tile showing trend-tier coverage.

  App.tsx                   MOD: route tree:
                                   /               → redirect to /clinical-ai
                                   /clinical-ai    → ClinicalAI (SiteLayout only)
                                   /rpm            → RPM (SiteLayout only)
                                   /strategy       → AgenticStrategy (SiteLayout only)
                                   /pipeline       → DashboardLayout (under SiteLayout)
                                     index         → PipelineOverview
                                     /coverage     → CoverageFunnel
                                     /rules        → RuleDiscovery
                                     /evals        → EvalScores
                                     /traces       → TraceExplorer
                                     /trends       → Trends (NEW)
                                     /interop      → Interoperability

public/data/
  trend-features.json       NEW: synced from Python export.
```

### Branch strategy
- Python repo: `feat/trend-layer` for Workstream A.
- React repo: `feat/dual-framing` for Workstreams B + C.
- Merging to main = production deploy via Cloudflare Pages on the React side. Both repos require explicit user approval before merge.

---

## 4. Code style

### Python
- Match existing conventions in `/Users/Sterdb/spo2-eval-pipeline/src/`: type hints on public functions, docstrings on modules and public APIs, prefer dataclasses for record types, keep modules under ~300 lines.
- Trend tier follows the existing tier-engine pattern (`tier1_engine.py`, `tier2.py`): single public entry point `run_trend_tier(...)`, internal helpers below.
- No new dependencies. EWMA computed directly with numpy.

### React / TypeScript
- Match existing conventions in `/Users/Sterdb/pm-private/spo2-eval-dashboard/src/`: function components with typed props, Tailwind 4 utility classes, theme tokens from `src/config/theme.ts`, no inline color literals outside the theme module.
- New landing pages follow `AgenticStrategy.tsx` as a reference: editorial JSX with `SectionCard`, `MetricCard`, `PageIntro`, `Callout`, inline subcomponents for repeated patterns.
- No new dependencies. No `react-markdown`, no `remark-gfm`. Landings and failure modes are JSX, not markdown-driven.
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
- `tests/test_lifecycle_transitions.py` from v3 plan is CUT. Testing logic without well-defined acceptance criteria is theater.

### React — none formal
- `pnpm build` is the merge gate. TS errors or Vite build failures block merge.
- Visual review in browser before merge. Test routes: `/`, `/clinical-ai`, `/rpm`, `/strategy`, `/pipeline`, and every `/pipeline/<tab>` including the new `/pipeline/trends`.
- Confirm `[TREND]` block renders in at least one trace in `/pipeline/traces`.

### Live LLM evals
- Not part of acceptance for this phase. The new trend-aware handoff prompt is unevaluated by Claude in this phase by design — ship the architecture first, validate after.
- Post-build, surface a cost estimate (~$0.20 for 10 traces) for a separate go/no-go decision on a paid trend-handoff eval pass.

---

## 6. Boundaries

### Always do
- Default to mock mode (`use_llm=False`) for any pipeline invocation.
- Use existing theme tokens in React work. Use the existing tier-engine pattern in Python work.
- Treat locked decisions in this spec as load-bearing. Any change requires re-spec.
- After Workstream A passes pytest, run `scripts/export_dashboard_data.py` once with a fixed seed to produce the canonical artifacts; commit only that seed's outputs to React `public/data/`.
- Apply the Panel 4 copy rules and Owlet reference policy without exception on `/rpm`.

### Ask first (require explicit user approval before acting)
- **Any `use_llm=True` invocation.** Surface cost estimate (trace count × ~$0.02) and trigger reason before spending. Current balance assumed ~$4.78.
- **Merging `feat/trend-layer` (Python) or `feat/dual-framing` (React)** to main. React main auto-deploys to `sp02eval.mccaybarnes.health`.
- **Changing any of these locked decisions:**
  - SatSeconds as the trend metric
  - New-tier integration with `[TREND]` handoff consumption (not standalone)
  - 25 babies × 16 nights regen
  - EWMA (not CUSUM) for trend detection
  - No 4th LLM-judge axis on trends
  - JSX (not markdown-driven) landings and failure modes
  - 4-destination top-level IA (Story | Business | Dashboard | Strategy)
  - `/` redirects to `/clinical-ai`
  - Lifecycle as schematic section inside `/clinical-ai`, NOT its own route
  - Strict 80%/20% acceptance thresholds across 3 seeds
  - Condition label as metadata-only (no per-condition signal modulation)
  - Single-file `export_dashboard_data.py` (no refactor)
  - Panel 1 three-actor split, Panel 2 TAM-ceiling framing, Panel 3 "structural model that would need to exist," Panel 4 continuity-of-relationship framing
  - Owlet reference: abstract by default, explicit only with 2021 history acknowledgment
  - Wellness tier price band $9.99-15
- **Citation set changes.** The five locked citations (Eichenwald 2016 AAP AOP, Rudd 2020 AHA Interstage, Everitt 2020 BPD weaning, J Pediatr 2022 hidden hypoxemia, CMS PFS 2026, AHRQ HCUPnet) are load-bearing. Adding or removing one requires confirmation.

### Never do
- Auto-commit or auto-push in either repo. Staging and commit messages are user-driven.
- Enable Vite source maps. The React repo ships static and must not leak source paths.
- Run the exporter from inside `sync_to_frontend.sh`. The two scripts are deliberately separated.
- Add `react-markdown`, `remark-gfm`, or any other dependency to the React repo without surfacing the decision.
- Relitigate locked decisions during build. If a decision becomes wrong, surface and re-spec — don't quietly drift.
- Commit any file from `pm-private/` to the public Python repo. Cross-contamination defeats the privacy boundary.
- Frame Panel 4 wellness tier as anxiety mitigation. Use the four-copy-rule framing or don't ship the panel.
- Name Owlet on the page without the 2021-FDA-warning acknowledgment context.

---

## 7. Phase acceptance

The phase is done when **all** of the following are true:

- [ ] `pytest tests/test_trend_features.py` passes across 3 seeds with strict 80/20 thresholds
- [ ] `pytest tests/test_safety_check.py` still passes (no regression)
- [ ] `python scripts/export_dashboard_data.py` produces 8 JSON artifacts (existing 7 + `trend-features.json`) plus `waveforms/`
- [ ] `bash scripts/sync_to_frontend.sh` copies all 8 + waveforms into `public/data/` with zero missing-file errors
- [ ] `pnpm build` in React repo completes clean
- [ ] `/clinical-ai`, `/rpm`, `/strategy`, `/pipeline`, and every `/pipeline/<tab>` route loads in browser including new `/pipeline/trends`
- [ ] `/` redirects to `/clinical-ai`
- [ ] Top-level 4-destination header strip renders on every route
- [ ] At least one trace in `/pipeline/traces` shows the `[TREND]` block in its handoff
- [ ] Lifecycle schematic renders as closing section of `/clinical-ai` with the "rolling-window operates on this; full lifecycle plays out over months illustrated" framing
- [ ] Four-panel value story renders on `/rpm` with all four panels respecting their framing rules (P1 three-actor split, P2 TAM ceiling caveats, P3 "would need to exist," P4 continuity-of-relationship + copy rules + Owlet policy)
- [ ] Hidden hypoxemia one-line callout present in `/clinical-ai` trend tier section
- [ ] Failure modes JSX section present in `/clinical-ai` (no markdown rendering)
- [ ] Generalization preview paragraph + single-direction link to `/rpm` present at end of `/clinical-ai`
- [ ] AgenticStrategy small edit pointing reimbursement readers at `/rpm` complete
- [ ] STATUS.md updated with v3 trend metrics and IA change
- [ ] LEARNINGS.md entry added for EWMA + trend handoff + four-panel framing + Owlet policy
- [ ] User has reviewed and approved both `feat/trend-layer` and `feat/dual-framing` before any merge to main

---

## 8. Cut order (Day 2-3 overrun triage)

If the build runs long, cut in this order. Cheapest first. Do NOT relitigate during build — pull from this list in order and continue.

1. **Generalization preview on `/clinical-ai`** — drop the one-paragraph link to `/rpm`. Saves ~30 min. Pages stand alone.
2. **AgenticStrategy.tsx edit** — leave the existing reimbursement-cost table unmodified. Saves ~30 min. Minor cross-link missing.
3. **Lifecycle schematic compression** — drop CHD and BPD overlays from the schematic; keep AOP only as the single representative trajectory. Saves ~1-2 hrs. Demonstration story narrows but survives.
4. **Dedicated `/pipeline/trends` tab** — merge trend signals into Coverage (tier-slice card) + TraceExplorer (trend column). Saves ~2-3 hrs. Trend surface area reduced; this is the structural cut to make only if 1-3 weren't enough.

**Do NOT cut:**
- The trend tier itself (engineering centerpiece)
- The four-panel value story (strategic centerpiece)
- The hidden hypoxemia callout (empirical anchor for trend tier)
- The failure modes JSX section (eval discipline signal)
- The 80/20 multi-seed test thresholds (credibility floor)
- The Panel 4 copy rules or Owlet reference policy (ethical floor)

---

## 9. Open items (held, not blocking spec)

- **TrendWatch surface placement** — `/pipeline/trends` as dedicated tab is the lock, but this is marked revisitable during build. If the build reveals the trend signals split awkwardly across Trends + Coverage + TraceExplorer (i.e., users have to hop tabs to follow a trend story), fall back to the merge-into-existing-tabs alternative per §8 cut #4. Decision point: end of React work, before pre-merge review.
- **Wellness tier exact price** — band locked at $9.99-15, exact pick by copy author with visible justification on the panel. Verify Owlet 360's current price (~$9.99) before publishing.
- **Live LLM eval for trend-aware handoff** — held for post-build go/no-go. Cost estimate ~$0.20 for 10 traces. Decision after build acceptance is met, separately approved.
- **STATUS.md and LEARNINGS.md post-build entries** — exact content drafted after Day 4-5 lands. Outline known: trend metrics, EWMA choice rationale, four-panel framing decisions, Owlet policy, IA restructure.
- **Loom recording plan** — Day 5 polish + Loom is part of the phase but specifics (script structure, take count, hosting) are outside SPEC scope. Plan separately when build is acceptance-ready.

---

## 10. What's explicitly cut from v3 plan (vs. what made it into v3 spec)

For future reference, so the build doesn't drift back toward v3 plan scope:

**Cut:**
- Condition-specific signal modulation (AOP event-frequency curves, BPD room-air-trial cycling, CHD interstage decompensation patterns) → condition is metadata-only label
- Step-down readiness flag in trend module → out of scope
- Personalized rolling baseline with low-variance windowing → simpler nightly median during non-event periods
- Exporter refactor into 6 modules → single-file exporter retained
- `tests/test_lifecycle_transitions.py` → cut, testing without well-defined criteria
- Day 1 failure-modes markdown doc → content lives directly in JSX
- Separate `MonitoringLifecycle.tsx` page route → embedded section in `/clinical-ai`
- Interactive Panel 2 calculator → static graphic
- Full second-modality React generalization page → one paragraph + link on `/clinical-ai`
- Mixing P&Ls in Panel 1 → three-actor split
- $135-180/mo as realized revenue → reframed as billable capacity at full utilization
- "The model we'd adopt" Panel 3 → "the model that would need to exist"
- Postpartum anxiety / PTSD framing in Panel 4 → continuity-of-relationship framing
- Naked Owlet reference → abstract by default + acknowledgment when explicit
- $15-30/mo wellness pricing → $9.99-15 anchored to Owlet 360

**Kept (additions on top of SPEC-v2 engineering):**
- Condition label (AOP / CHD interstage / BPD) on BabyProfile metadata
- Four-panel value story on `/rpm`
- Lifecycle schematic embedded in `/clinical-ai`
- Failure modes JSX section in `/clinical-ai`
- Dedicated `/pipeline/trends` tab (revisitable per §9)
- Hidden hypoxemia citation as one-line callout in `/clinical-ai` trend section
- Six locked citations (Eichenwald, Rudd, Everitt, J Pediatr 2022, CMS PFS 2026, AHRQ HCUPnet)
- AgenticStrategy minimal edit cross-linking to `/rpm`
- Loud-fallback guardrails in `llm_utils.py` (CostTracker, STRICT_LIVE env var)
