# SpO2 Baby Monitoring — AI Eval Pipeline Demo

## Project Goal
Build a prototype demonstrating an AI-powered evaluation pipeline for neonatal SpO2 monitoring data, culminating in a warm handoff summary for telehealth nurses. Purpose: present to a clinical AI company showing familiarity with clinical data, LLM evals, and eval pipeline architecture.

## Context
- Dataset scale: 2.5M babies, 3 months of nightly data (~225M traces)
- Real data not available — use synthetic data mimicking real patterns
- End output: a nurse-facing handoff summary triaging each baby's night

---

## What To Build

### 1. Synthetic Data Generator
Generate nightly SpO2 traces covering four pattern types:
- **Normal**: SpO2 98-100%, mild natural variation, clean signal
- **Urgent**: SpO2 < 90% sustained >10 seconds
- **Borderline**: SpO2 90-94% sustained, ambiguous
- **Artifact**: sudden spikes/drops correlated with high accelerometer variance

Vary by gestational age (premature babies have lower baseline ranges).
Reference PhysioNet neonatal datasets for realistic signal shapes.

### 2. Rule-Based Tier 1 Pre-Annotation
Hardcode clinical thresholds to auto-label the easy cases:
- SpO2 < 90% for >10s → urgent
- SpO2 90-94% sustained → borderline
- Clean signal >95% all night → normal
- Accelerometer spike + SpO2 drop → artifact candidate

Target: auto-label ~65% of traces with zero model involvement.

### 3. Pattern Learning Layer
On the borderline tier, run pattern mining to discover new candidate rules:
- Temporal patterns: does a 2am dip predict a worse 4am event?
- Multi-night trends: three consecutive borderline nights vs. one urgent night
- Contextual clusters: gestational age + dip duration combinations

Use scikit-learn decision tree or mlxtend Apriori association rules.
Output: candidate new rules with confidence scores for expert confirmation.

### 4. Pre-Annotation Classifier (Tier 2)
Train a lightweight logistic regression classifier on Tier 1 auto-labels.
High confidence predictions pass through. Low confidence escalates to "expert review" queue. Simulate expert with a held-out rule set.
Target: classifier handles ~25%, expert queue ~10%.

### 5. LLM Eval Pipeline
Three separate evaluators using Claude API. Each is its own prompt, Pass/Fail output with reasoning field, JSON structured output.

**Evaluator 1 — Clinical Accuracy**
Did the system correctly triage this night?

**Evaluator 2 — Handoff Quality**
Is the nurse summary urgent-first, plain language, actionable?

**Evaluator 3 — Artifact Handling**
Did the system correctly exclude noise/artifact events?

Each evaluator needs:
- Clear Pass/Fail definition
- 2-3 few-shot examples (one clear Pass, one clear Fail)
- JSON output: `{reasoning: string, answer: "Pass" | "Fail"}`

### 6. Nurse Handoff Generator
LLM prompt that takes a triaged night and generates a warm handoff summary.
Requirements:
- Lead with urgency level
- Plain language (not researcher jargon)
- Include gestational age and patient baseline context
- Specific actionable next step for the nurse

### 7. Streamlit Dashboard
Four views:
- **Eval scores over time**: TPR/TNR per evaluator, trended
- **Pre-annotation coverage**: % handled by rules vs. model vs. expert queue
- **Rule discovery log**: new patterns found, confidence scores
- **Sample handoffs**: side-by-side bad vs. good nurse summary output

---

## Tech Stack
- Synthetic data: Python, numpy
- Rule engine: Python threshold functions
- Pattern mining: scikit-learn / mlxtend
- Pre-annotation classifier: scikit-learn logistic regression
- LLM evaluators + handoff: Claude API (claude-sonnet-4-6)
- Dashboard: Streamlit

---

## Key Clinical Parameters To Respect
- Premature (<37 weeks): baseline SpO2 may be 92-95% (not 98-100%)
- Term babies: baseline 97-100%
- Clinically significant desat: <90% sustained >10 seconds
- Artifact signal: correlated accelerometer + implausible SpO2 swing
- Handoff audience: telehealth nurse, not neonatologist

---

## Build Order
1. Synthetic data generator
2. Rule engine (Tier 1)
3. Pattern mining layer
4. Pre-annotation classifier (Tier 2)
5. LLM evaluators
6. Nurse handoff generator
7. Streamlit dashboard wiring everything together

## Success Criteria
A working demo where you can feed in a synthetic nightly trace and see:
- Automatic triage classification with reasoning
- Which tier handled it (rules / model / expert queue)
- Eval scores for that output
- A nurse-ready handoff summary
- Any new candidate rules discovered from the pattern layer
