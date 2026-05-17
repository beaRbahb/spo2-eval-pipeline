# SPEC-v3 Build — Todo

Companion checklist to `plan.md`. Each item maps to a task in the plan.

## Phase A — Python `feat/trend-layer`

- [ ] **PY-1** BabyProfile.condition field + 25×16 cohort defaults (S)
- [ ] **PY-2** Plant deteriorating cohort with monotonic SatSeconds drift (M)
- [ ] **PY-3** patterns/trend_features.py — run_trend_tier with EWMA (M)
- [ ] **PY-4** tests/test_trend_features.py — 3 seeds × strict 80/20 (M)
- [ ] 🚦 **Gate A1** — trend test hard gate (halt if failing after 3 re-seeds)
- [ ] **PY-5** Orchestrator wires trend tier + threads baby_trend_flag (S)
- [ ] **PY-6** Handoff [TREND] block + stable-but-trending template (M)
- [ ] **PY-7** llm_utils STRICT_LIVE guardrails (S)
- [ ] **PY-8** Exporter — trend-features.json + 25×16 defaults (S)
- [ ] **PY-9** sync_to_frontend.sh — add trend-features.json (XS)
- [ ] 🧹 `/clear marker` — Python branch ready (good spot to drop into fresh React session)

## Phase B — React `feat/dual-framing` landings (parallelizable through PY-8)

- [ ] **RX-1** SiteLayout + restructured routes + sidebar trim (M)
- [ ] **RX-2** ClinicalAI scaffold — Hero + LLM-judge depth + generalization preview (M)
- [ ] **RX-3** ClinicalAI failure modes section (JSX, no markdown) (M)
- [ ] **RX-4** ClinicalAI trend tier section + hidden hypoxemia callout (S)
- [ ] **RX-5** ClinicalAI lifecycle schematic — section 6 — **cut #3 candidate** (M)
- [ ] **RX-6** RPM scaffold + Panel 1 (three-actor split) (M)
- [ ] **RX-7** ValueStoryPanels Panel 2 (TAM ceiling caveats) (S)
- [ ] **RX-8** ValueStoryPanels Panel 3 (structural model + citations) (M)
- [ ] **RX-9** ValueStoryPanels Panel 4 — ⚠ ETHICAL FLOOR (M)
- [ ] 🚦 **Gate B-Panel4** — copy review against 4 mandatory rules + Owlet policy
- [ ] **RX-10** AgenticStrategy edit — cross-link to /rpm — **cut #2 candidate** (XS)
- [ ] 🧹 `/clear marker` — landings done (good spot to drop into fresh trend-integration session)

## Phase C — React trend data integration (requires PY sync)

- [ ] **RX-11** Trends.tsx — dedicated tab — **cut #4 candidate** (M)
- [ ] 🚦 **Gate C-§9** — keep dedicated Trends tab OR apply cut #4 merge
- [ ] **RX-12** TraceExplorer — [TREND] block + condition chip (S)
- [ ] **RX-13** CoverageFunnel 4th tier slice + PipelineOverview tile (S)

## Phase D — Polish + final gate

- [ ] **DOC-1** STATUS.md + LEARNINGS.md updates (S)
- [ ] 🚦 **Gate D** — pre-merge `git diff` review on both branches + full SPEC §7 acceptance (no auto-merge)

## Held (not in build path)

- [ ] Live LLM eval on trend-aware handoff (~$0.20) — post-build go/no-go
- [ ] Exact wellness tier price — picked during RX-9
- [ ] Loom recording — plan separately

## Cut order if overrunning (§8, pull in order)

1. RX-2 generalization preview (last paragraph)
2. RX-10 AgenticStrategy cross-link
3. RX-5 compress to AOP-only
4. RX-11 merge dedicated Trends tab into Coverage + TraceExplorer

**Do NOT cut:** trend tier itself, four-panel story, hidden hypoxemia callout, failure modes JSX, 80/20 test thresholds, Panel 4 copy rules, Owlet policy.
