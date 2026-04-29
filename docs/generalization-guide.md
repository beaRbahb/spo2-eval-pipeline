# Generalization Guide

How to adapt the SpO2 AI Eval Pipeline architecture for other clinical monitoring domains.

## Core Architecture Pattern

The pipeline follows a **three-tier classification + LLM evaluation** pattern that generalizes beyond pulse oximetry:

```
Synthetic Data → Rule Engine (Tier 1) → ML Classifier (Tier 2) → Expert Queue (Tier 3)
                                    ↓
                            LLM Evaluators → Clinical Handoffs → Dashboard
```

This pattern works for any domain where:
1. Some cases are clinically obvious (rule-based)
2. Some cases require nuanced classification (ML)
3. Quality assessment needs clinical judgment (LLM-as-judge)
4. End users need structured summaries (handoffs)

## Domain Adaptation Examples

### Cardiac Monitoring (ECG/Arrhythmia Triage)

**Data generation**: Synthetic ECG traces with known arrhythmia patterns (AFib, VT, SVT, PVCs, normal sinus). Vary by patient demographics and comorbidities.

**Tier 1 rules**:
- Heart rate <40 or >180 bpm sustained → **emergency**
- Known arrhythmia pattern (VT, VF) detected → **urgent**
- Regular sinus rhythm, normal rate → **routine**
- Excessive baseline wander / lead disconnect → **artifact**

**Tier 2 classifier**: Train on ambiguous rhythms where rate-based rules aren't sufficient (e.g., atrial flutter vs. AFib, benign PVCs vs. concerning patterns).

**LLM evaluators**:
- Clinical accuracy: Does the arrhythmia classification match the ECG pattern?
- Handoff quality: Is the cardiology consult recommendation actionable?
- Artifact handling: Are lead-off events correctly identified?

**Key adaptations**:
- Replace SpO2 thresholds with heart rate / rhythm thresholds
- Replace gestational age adjustment with patient age / cardiac history adjustment
- Replace SatSeconds with arrhythmia burden (% time in abnormal rhythm)

### Respiratory Monitoring (Ventilator Waveforms)

**Data generation**: Synthetic ventilator waveform data (pressure, flow, volume) with patient-ventilator asynchrony patterns, auto-PEEP, and circuit disconnects.

**Tier 1 rules**:
- Circuit disconnect detected �� **emergency**
- Auto-PEEP >5 cmH2O → **urgent**
- All waveforms within expected parameters → **routine**
- Condensation / circuit leak artifact → **artifact**

**Tier 2 classifier**: Patient-ventilator asynchrony types (double triggering, ineffective triggering, flow starvation) that require waveform pattern recognition.

**Key adaptations**:
- Replace SpO2 trace analysis with pressure/flow/volume waveform analysis
- Replace GA-adjusted thresholds with ventilator-mode-adjusted thresholds
- Handoff targets RT (respiratory therapist) instead of nurse

### Continuous Glucose Monitoring (CGM)

**Data generation**: Synthetic CGM traces with hypo/hyperglycemic events, calibration drift, and sensor compression artifacts.

**Tier 1 rules**:
- Glucose <54 mg/dL → **emergency** (severe hypoglycemia)
- Glucose <70 mg/dL sustained >15 min → **urgent**
- Glucose >250 mg/dL sustained >2 hours → **urgent**
- Rapid rate of change >3 mg/dL/min → **monitor**
- Signal gap or compression artifact → **artifact**

**Tier 2 classifier**: Distinguish true hypoglycemia from compression low artifacts. Identify meal-related vs. pathologic hyperglycemia patterns.

**Key adaptations**:
- Replace SpO2 with glucose values
- Replace SatSeconds with time-below-range (TBR) and time-in-range (TIR) metrics
- Adjust for patient factors: insulin type, meal timing, exercise

## Step-by-Step Adaptation Process

### 1. Define your clinical tiers
Map your domain's urgency levels to the 5-tier system:
- **Emergency**: Immediate clinical action required
- **Urgent**: Action needed within current shift
- **Monitor**: Increased surveillance, no immediate action
- **Routine**: Normal findings, standard care
- **Artifact**: Technical issue, not a clinical finding

### 2. Implement synthetic data generation
Replace `src/data_gen/synthetic.py`:
- Define your signal type (ECG, pressure, glucose, etc.)
- Model normal and abnormal patterns for your domain
- Include realistic artifact patterns
- Generate ground truth labels based on clinical definitions

### 3. Adapt the rule engine
Replace `src/rules/tier1_engine.py`:
- Convert your domain's clinical thresholds into rules
- Implement your version of the safety check (the principle: never let artifact detection mask a genuine clinical event)
- Add patient-factor adjustments (age, comorbidities, device type)

### 4. Retrain the Tier 2 classifier
Update `src/patterns/` and `src/classifier/`:
- Engineer features relevant to your signal type
- The training approach (train on Tier 1 outputs) remains the same
- Expect the same domain shift challenge: Tier 2 is trained on easy cases, tested on hard ones

### 5. Adapt LLM evaluators
Update `src/evals/`:
- Rewrite evaluation prompts for your clinical domain
- Keep the three evaluation axes: clinical accuracy, handoff quality, artifact handling
- Adjust scoring rubrics for your domain's clinical standards

### 6. Customize handoff templates
Update `src/handoff/generator.py`:
- Write templates appropriate for your end user (nurse, RT, physician)
- Include domain-specific metrics (arrhythmia burden, TBR, etc.)
- Define action items per urgency tier per your domain's clinical protocols

### 7. Update the dashboard
Update `app/dashboard.py`:
- Change labels and metrics to match your domain
- Keep the 7-view structure (it generalizes well)
- Update visualizations for your signal type

## What Stays the Same

Regardless of clinical domain, these patterns are reusable:
- **Three-tier classification architecture** (rules → ML → expert queue)
- **Safety check principle** (hard constraint preventing dangerous misclassification)
- **LLM-as-judge evaluation framework** (mock + live modes)
- **Progressive handoff templates** (urgency-matched action items)
- **Dashboard structure** (7 views covering pipeline, tiers, evals, handoffs)
- **Domain shift awareness** (Tier 2 trained on easy cases — flag this in your dashboard)

## What Changes

Per-domain customization required for:
- Signal type and feature engineering
- Clinical thresholds and urgency definitions
- Patient factor adjustments
- Evaluation prompt content
- Handoff template language and action items
- Regulatory context (device classification, predicate devices, applicable standards)
