# Evaluation Methodology

## Overview

The SpO2 AI Eval Pipeline uses **LLM-as-judge** evaluation to assess clinical output quality. This document describes the approach, prompt design, scoring methodology, and lessons learned.

## Why LLM-as-Judge?

Traditional ML metrics (accuracy, F1, precision, recall) measure classification correctness but miss clinical nuance:

| What metrics catch | What metrics miss |
|---|---|
| Wrong triage tier | Vague action items in handoffs |
| Overall accuracy | Whether urgency language matches clinical severity |
| Per-class distribution | Whether artifact handling preserves safety |
| Threshold sensitivity | Whether handoffs are actionable for nurses |

LLM evaluators bridge this gap by assessing **output quality** — not just correctness — against clinical criteria that would require domain expert review at scale.

## Three Evaluation Axes

### 1. Clinical Accuracy (`src/evals/clinical_accuracy.py`)
**Question**: Does the triage classification match the clinical picture?

**What it evaluates**:
- Is the urgency tier appropriate given the SpO2 statistics?
- Are GA-adjusted thresholds applied correctly?
- Does the system correctly identify emergency vs. urgent vs. routine?
- Are desaturation events counted and characterized accurately?

**Scoring rubric**:
- **Pass**: Correct tier assignment with appropriate clinical reasoning
- **Fail**: Wrong tier, missed desaturation, or inappropriate threshold application

### 2. Handoff Quality (`src/evals/handoff_quality.py`)
**Question**: Is the nurse handoff summary actionable, complete, and appropriate?

**What it evaluates**:
- Does the handoff include all required data elements (SpO2 stats, events, recommendations)?
- Are action items specific and appropriate for the urgency level?
- Is clinical language appropriate for the target audience (NICU nurses)?
- Does the handoff avoid both under-reaction (routine language for urgent cases) and over-reaction (alarm language for routine cases)?

**Scoring rubric**:
- **Pass**: Complete handoff with appropriate urgency-matched action items
- **Fail**: Missing data elements, vague actions, or urgency mismatch

### 3. Artifact Handling (`src/evals/artifact_handling.py`)
**Question**: Are artifact-affected traces correctly identified and handled safely?

**What it evaluates**:
- Are motion/probe artifacts detected without masking genuine desaturation?
- Does the safety check override artifact classification when a real event is present?
- Are artifact-only traces correctly classified as non-clinical findings?

**Scoring rubric**:
- **Pass**: Correct artifact identification with safety preservation
- **Fail**: Artifact masking a real event, or real event classified as artifact

## Prompt Design

### Structure
Each evaluator prompt follows the same structure:

```
ROLE: You are a neonatal SpO2 monitoring specialist evaluating [specific aspect].

CONTEXT: [Patient metadata, SpO2 statistics, desaturation events, GA-adjusted thresholds]

TASK: Evaluate the following [classification / handoff / artifact handling] against these criteria:
1. [Criterion 1]
2. [Criterion 2]
...

OUTPUT FORMAT:
- verdict: PASS or FAIL
- reasoning: [Brief clinical justification]
- issues: [List of specific problems found, if any]
```

### Key Prompt Design Decisions

**Explicit criteria, not vibes**: Each evaluator has numbered criteria, not "does this look good?" This prevents LLM hedging and ensures consistent evaluation.

**Clinical context first**: The prompt provides full patient context (GA, baseline SpO2, event details) before the item being evaluated. This mirrors how clinicians assess findings — context determines interpretation.

**Binary verdict**: PASS/FAIL, not a 1-5 scale. Clinical triage is binary: either the action is appropriate or it isn't. Gradient scales invite LLM fence-sitting (everything gets a 3-4).

**Structured output**: JSON format with verdict, reasoning, and issues fields. This enables automated parsing and aggregation across evaluation runs.

### Prompt Evolution

The prompts went through 3 major iterations:

**V1**: Basic evaluation — "Is this classification correct?" Resulted in 80% clinical accuracy pass rate but missed handoff quality issues entirely (mock templates always passed, live Claude generation didn't).

**V2 (post clinical fixes)**: Added GA-adjusted threshold awareness, SatSeconds metric, and emergency tier. Clinical accuracy dropped to 70% because the evaluator now caught cases where the system applied term thresholds to preterm patients.

**V2.1**: Added timeframe requirements to handoff evaluation ("within the next hour", not "soon"). Handoff quality recovered from 30% to 80% as the generator was updated to match stricter criteria.

## Mock vs. Live Modes

### Mock Mode ($0)
- Template-based scoring using heuristic rules
- Useful for development iteration and CI/CD
- Known limitation: Always passes certain edge cases that live mode catches
- Mock accuracy scores are inflated vs. reality

### Live Mode (~$0.02/trace)
- Uses Claude API for evaluation
- More accurate but costs money
- Recommended: 10-trace sample ($0.15-0.30) for pre-launch validation
- Catches: vague language, urgency mismatches, incomplete action items that templates miss

### Gap Between Mock and Live

| Evaluator | Mock Pass Rate | Live Pass Rate | Gap Source |
|-----------|---------------|----------------|------------|
| Clinical Accuracy | ~95% | 60-80% | Mock doesn't catch threshold edge cases |
| Handoff Quality | ~95% | 80-90% | Mock doesn't evaluate language quality |
| Artifact Handling | ~98% | ~100% | Artifact detection is more rule-based, less gap |

**Lesson**: Mock mode is necessary for development speed but should never be treated as the production quality bar. Always validate with a live eval run before shipping.

## Scoring Aggregation

### Per-Run Metrics
- Pass rate per evaluator (clinical accuracy, handoff quality, artifact handling)
- Overall pass rate (all three must pass for a trace to be "fully passing")
- Cost tracking (API calls × price per call)

### Cross-Run Tracking
`STATUS.md` tracks results across evaluation runs:
- V1 baseline → V2 (clinical fixes) → V2.1 (prompt fixes)
- Each run: 10 traces × 3 evaluators = 30 evaluations

### Statistical Considerations
- 10-trace samples give directional signal, not statistical significance
- For production validation: 100+ traces recommended for reliable confidence intervals
- Evaluator agreement: track how often live and mock modes agree to calibrate mock scoring

## Lessons Learned

1. **Mock ≠ real**: The biggest risk in eval pipelines is trusting mock scores. Our handoff quality was "95% passing" in mock mode and 20% in live mode. Mock templates don't catch language quality issues.

2. **Prompt specificity matters**: "Is this handoff good?" vs. "Does this handoff include specific timeframes for each action item?" — the second prompt catches 3x more failures.

3. **Evaluator drift**: When you change what the system produces (adding emergency tier, SatSeconds), you must also update evaluator prompts. Our V2 clinical accuracy dropped because the evaluator was updated but the generator wasn't, revealing a real quality gap.

4. **Binary > gradient**: PASS/FAIL forces the evaluator to commit. Gradient scales (1-5) produce a Gaussian around 3.5 that's useless for quality decisions.

5. **Safety checks are hard constraints, not model outputs**: The safety check (prevent artifact from masking urgent) is implemented in the rule engine, not the LLM. Critical safety logic should never be delegated to probabilistic systems.
