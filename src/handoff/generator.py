"""Nurse handoff summary generator.

Generates warm handoff summaries for telehealth nurses. Two modes:
- Mock (default): template-based, no API calls, $0
- Live: Claude API, requires ANTHROPIC_API_KEY and explicit opt-in
"""
from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np

from src.data_gen.synthetic import NightTrace
from src.config import CLAUDE_MODEL


@dataclass
class HandoffSummary:
    """Generated nurse handoff for a single trace."""
    trace_id: str
    baby_id: str
    urgency_level: str   # "URGENT", "MONITOR", "ROUTINE"
    summary_text: str
    source: str           # "mock_template" or "claude_api"
    model_used: str
    latency_ms: int


# ---------------------------------------------------------------------------
# Urgency mapping
# ---------------------------------------------------------------------------

_URGENCY_MAP = {
    "emergency": "EMERGENCY",
    "urgent": "URGENT",
    "borderline": "MONITOR",
    "normal": "ROUTINE",
    "artifact": "ROUTINE",
}


# ---------------------------------------------------------------------------
# Mock handoff templates (no API calls)
# ---------------------------------------------------------------------------

_MOCK_TEMPLATES = {
    "emergency": (
        "EMERGENCY — Baby had a severe desaturation event reaching {min_spo2:.0f}% "
        "overnight, lasting {max_dur}s. SatSeconds burden: {sat_seconds:.0f}.\n\n"
        "As a {ga_weeks}-week {ga_desc} infant (now {days} days old), "
        "{ga_context} This level of desaturation poses immediate risk.\n\n"
        "Action: Advise family to call 911 or go to nearest emergency department "
        "immediately. If family cannot be reached within 15 minutes, escalate to "
        "on-call physician for emergency welfare check.\n\n"
        "Ask family: Is the baby breathing normally? Any visible changes in "
        "skin color or feeding difficulty?"
    ),
    "urgent": (
        "URGENT — Baby had {n_urgent} desaturation event(s) below threshold overnight, "
        "with the longest lasting {max_dur}s and reaching {min_spo2:.0f}%. "
        "SatSeconds burden: {sat_seconds:.0f}.\n\n"
        "As a {ga_weeks}-week {ga_desc} infant (now {days} days old), "
        "{ga_context} This baby's overnight pattern requires prompt attention.\n\n"
        "Action: Call the family within 1 hour to confirm home oxygen equipment "
        "is functioning and check for visible breathing pauses. Flag for "
        "pediatrician follow-up today.\n\n"
        "Ask family: Have you noticed any breathing pauses, skin color changes, "
        "or feeding difficulty overnight?"
    ),
    "borderline": (
        "MONITOR — Baby had {n_borderline} borderline SpO2 event(s) in the 90-94% "
        "range overnight. Mean SpO2 was {mean_spo2:.1f}%, minimum {min_spo2:.0f}%.\n\n"
        "As a {ga_weeks}-week {ga_desc} infant (now {days} days old), "
        "{ga_context} These readings are not clearly urgent but need closer follow-up.\n\n"
        "Action: Schedule follow-up pulse oximetry within 48 hours. If this is the "
        "third consecutive borderline night, escalate to physician review."
    ),
    "normal": (
        "ROUTINE — Baby's overnight SpO2 was within normal range. "
        "Mean SpO2 {mean_spo2:.1f}%, minimum {min_spo2:.0f}%. No significant "
        "desaturation events detected.\n\n"
        "As a {ga_weeks}-week {ga_desc} infant (now {days} days old), "
        "{ga_context}\n\n"
        "Action: No contact with family needed. Document normal overnight result "
        "in the patient record and close this monitoring cycle. Next routine "
        "review in 7 days unless clinical status changes."
    ),
    "artifact": (
        "ROUTINE (with note) — Overnight monitoring detected {n_artifacts} motion "
        "artifact event(s) that were excluded from clinical analysis. After artifact "
        "removal, SpO2 was within normal range (mean {mean_spo2:.1f}%).\n\n"
        "As a {ga_weeks}-week {ga_desc} infant (now {days} days old), "
        "{ga_context} The artifacts suggest the sensor may need repositioning.\n\n"
        "Action: Advise family on sensor placement during next scheduled check-in "
        "within 7 days. No urgent clinical follow-up needed."
    ),
}

_GA_CONTEXT = {
    "extremely_preterm": "some SpO2 variability is expected at this gestational age, and baseline readings of 91-93% are within the normal range for extremely preterm infants.",
    "very_preterm": "baseline SpO2 readings of 93-95% are expected for very preterm infants, and mild variability is normal.",
    "moderate_preterm": "SpO2 should be stabilizing toward term ranges, though occasional mild dips are still expected.",
    "term": "SpO2 readings should consistently be 97-100% at this gestational age.",
}


# Stable-but-trending template — used when per-night triage is routine (normal)
# but the baby's multi-night trend tier has fired. Urgency = MONITOR (handled by
# existing parser; no new urgency level needed).
_STABLE_BUT_TRENDING_TEMPLATE = (
    "MONITOR — Tonight's overnight SpO2 was within normal range "
    "(mean {mean_spo2:.1f}%, minimum {min_spo2:.0f}%, SatSeconds burden "
    "{sat_seconds:.0f}). The per-night reading is reassuring.\n\n"
    "However, this baby's multi-night hypoxemic burden has been trending "
    "upward across the recent monitoring window. As a {ga_weeks}-week "
    "{ga_desc} infant (now {days} days old), {ga_context}\n\n"
    "Action: Within 48 hours, review the multi-night trend view for context "
    "and schedule a clinical correlation call with the family. If the trend "
    "persists across another monitoring cycle, escalate to physician review."
)


# Appended to emergency/urgent/borderline templates when baby_trend_flag=True.
_TREND_BLOCK = (
    "\n\n[TREND] Trend tier has flagged this baby — hypoxemic burden has been "
    "rising across recent nights, even when individual nights fall within "
    "expected ranges. Review the multi-night trend view alongside tonight's "
    "result for full clinical context."
)


# Appended to the artifact template when baby_trend_flag=True. Artifact-dominated
# nights cannot reliably contribute to the trend signal, so we explicitly tell
# the nurse not to act on the trend flag for this night.
_ARTIFACT_TRENDING_NOTE = (
    "\n\nNote: trend tier signal not actionable on this night — the artifact-"
    "dominated reading does not reliably reflect the baby's hypoxemic burden. "
    "Re-evaluate after the next clean monitoring night."
)


def _compute_trace_stats(trace: NightTrace, rule_events: list[dict] | None = None) -> dict:
    """Extract summary stats needed for handoff templates.

    Args:
        rule_events: If provided, use rule engine detected events instead of
                     trace.events (synthetic generator events).
    """
    spo2 = trace.spo2
    baby = trace.baby

    # Use rule engine events when available (more accurate than generator events)
    events = rule_events if rule_events is not None else trace.events

    # Count events by type
    n_urgent = sum(1 for e in events if "urgent" in e.get("type", "") or e.get("rule") == "R1_SAFETY")
    n_borderline = sum(1 for e in events if "borderline" in e.get("type", ""))
    n_artifacts = sum(1 for e in events if e.get("type") == "artifact")

    # Duration of longest event
    durations = [e.get("duration_s", 0) for e in events]
    max_dur = max(durations) if durations else 0

    ga_desc = "preterm" if baby.gestational_age_weeks < 37 else "term"

    # SatSeconds: hypoxemic burden (GA-adjusted)
    from src.config import GA_URGENT_THRESHOLDS
    ga_threshold = GA_URGENT_THRESHOLDS.get(baby.ga_category, 90)
    sat_seconds = float(np.sum(np.maximum(0, ga_threshold - spo2)))

    return {
        "mean_spo2": float(np.mean(spo2)),
        "min_spo2": float(np.min(spo2)),
        "max_dur": max_dur,
        "n_urgent": n_urgent,
        "n_borderline": n_borderline,
        "n_artifacts": n_artifacts,
        "ga_weeks": baby.gestational_age_weeks,
        "ga_desc": ga_desc,
        "ga_context": _GA_CONTEXT.get(baby.ga_category, ""),
        "days": baby.days_since_birth,
        "sat_seconds": sat_seconds,
        "ga_threshold": ga_threshold,
    }


def generate_handoff_mock(
    trace: NightTrace,
    final_label: str,
    rule_events: list[dict] | None = None,
    baby_trend_flag: bool = False,
) -> HandoffSummary:
    """Generate a handoff using templates (no API call).

    Trend-tier integration (when `baby_trend_flag=True`):
    - emergency / urgent / borderline: existing template + [TREND] block
    - normal:                          stable_but_trending template, urgency=MONITOR
    - artifact:                        existing artifact template + non-actionable note
                                       (the artifact-dominated night cannot reliably
                                        contribute to the trend signal)
    """
    stats = _compute_trace_stats(trace, rule_events=rule_events)

    if baby_trend_flag and final_label == "normal":
        # Stable per-night, trending baby: route to MONITOR with trend rationale.
        summary_text = _STABLE_BUT_TRENDING_TEMPLATE.format(**stats)
        urgency = "MONITOR"
    else:
        template = _MOCK_TEMPLATES.get(final_label, _MOCK_TEMPLATES["normal"])
        summary_text = template.format(**stats)
        urgency = _URGENCY_MAP.get(final_label, "ROUTINE")

        if baby_trend_flag:
            if final_label == "artifact":
                summary_text += _ARTIFACT_TRENDING_NOTE
            elif final_label in ("emergency", "urgent", "borderline"):
                summary_text += _TREND_BLOCK
            # final_label == "normal" handled above; nothing else routes here.

    return HandoffSummary(
        trace_id=trace.night_id,
        baby_id=trace.baby.baby_id,
        urgency_level=urgency,
        summary_text=summary_text,
        source="mock_template",
        model_used="none",
        latency_ms=0,
    )


# ---------------------------------------------------------------------------
# Live handoff generation (Claude API)
# ---------------------------------------------------------------------------

_HANDOFF_PROMPT = """You are generating a warm handoff summary for a telehealth nurse receiving a neonatal SpO2 overnight monitoring case.

PATIENT PROFILE:
- Baby ID: {baby_id}
- Gestational age at birth: {ga_weeks} weeks ({ga_category})
- Current age: {days_since_birth} days old
- Birth weight: {birth_weight}g
- Known conditions: {known_conditions}

OVERNIGHT MONITORING RESULTS:
- Triage classification: {triage_label}
- Classified by: {classified_by}
- Mean SpO2: {mean_spo2:.1f}%
- Minimum SpO2: {min_spo2:.0f}%
- Desaturation events (SpO2 <{ga_threshold}% >10s): {n_urgent}
- Borderline events (SpO2 near threshold, sustained): {n_borderline}
- Artifact events excluded: {n_artifacts}
- SatSeconds burden (hypoxemic severity): {sat_seconds:.0f}
- Desaturation threshold (GA-adjusted): {ga_threshold}%
{trend_context}
REQUIREMENTS:
1. Start with urgency level in caps: EMERGENCY / URGENT / MONITOR / ROUTINE
2. First sentence: the single most important clinical finding
3. Second paragraph: gestational age context and how it affects interpretation
4. Third paragraph: specific actionable next step for the nurse
5. Plain language appropriate for a telehealth nurse (not a neonatologist)
6. Keep to 4-6 sentences total
7. If artifact events were excluded, briefly note this
8. For EMERGENCY cases, direct family to call 911 or go to nearest ED
9. For URGENT or EMERGENCY, include a clinical correlation question for the family
10. Every action step MUST include a specific timeframe (e.g., "within 1 hour", "within 48 hours", "in 7 days"). Never say "at your next scheduled check-in" without a concrete timeframe.
11. {trend_requirement}

Generate the handoff summary now."""


# Inserted into the OVERNIGHT MONITORING RESULTS block of _HANDOFF_PROMPT when
# `baby_trend_flag=True`. Carries the multi-night signal that no single-night
# snapshot can convey.
_TREND_CONTEXT_BLOCK_FLAGGED = """
TREND TIER (multi-night signal):
- This baby has been flagged by the trend tier: hypoxemic burden (SatSeconds)
  has been rising across the recent monitoring window, even where individual
  nights fall within expected per-night ranges.
"""

_TREND_CONTEXT_BLOCK_NONE = ""

# Used as requirement #11 in the prompt — instructs the model how to reason
# about the trend signal vs the per-night signal.
_TREND_REQUIREMENT_FLAGGED = (
    "Because the trend tier has flagged this baby, append a final paragraph "
    "starting with [TREND] that explains the multi-night pattern and the "
    "rationale for elevated vigilance even if tonight's per-night triage is "
    "routine. EXCEPTION: when tonight's classification is artifact, do NOT "
    "append the [TREND] paragraph; instead, briefly note that the trend signal "
    "is not actionable on an artifact-dominated night."
)
_TREND_REQUIREMENT_NONE = (
    "If you have no multi-night trend signal, do not invent one — keep the "
    "handoff focused on tonight's reading."
)


def generate_handoff_live(
    trace: NightTrace,
    final_label: str,
    classified_by: str = "pipeline",
    model: str | None = None,
    rule_events: list[dict] | None = None,
    baby_trend_flag: bool = False,
) -> HandoffSummary | None:
    """Generate a handoff using Claude API. Returns None if budget exceeded.

    When `baby_trend_flag=True`, the prompt gains a TREND TIER context block
    and a requirement to append a [TREND] paragraph to the output (except on
    artifact-dominated nights, where the trend signal is not actionable).
    """
    from src.llm_utils import call_llm

    stats = _compute_trace_stats(trace, rule_events=rule_events)
    baby = trace.baby

    prompt = _HANDOFF_PROMPT.format(
        baby_id=baby.baby_id,
        ga_weeks=baby.gestational_age_weeks,
        ga_category=baby.ga_category,
        days_since_birth=baby.days_since_birth,
        birth_weight=baby.birth_weight_grams,
        known_conditions=", ".join(baby.known_conditions),
        triage_label=final_label,
        classified_by=classified_by,
        mean_spo2=stats["mean_spo2"],
        min_spo2=stats["min_spo2"],
        n_urgent=stats["n_urgent"],
        n_borderline=stats["n_borderline"],
        n_artifacts=stats["n_artifacts"],
        sat_seconds=stats["sat_seconds"],
        ga_threshold=stats["ga_threshold"],
        trend_context=(_TREND_CONTEXT_BLOCK_FLAGGED if baby_trend_flag
                       else _TREND_CONTEXT_BLOCK_NONE),
        trend_requirement=(_TREND_REQUIREMENT_FLAGGED if baby_trend_flag
                           else _TREND_REQUIREMENT_NONE),
    )

    result = call_llm(prompt, model=model, max_tokens=400)
    if result is None:
        return None

    # Parse urgency from the response (strip markdown formatting like **URGENT** or # URGENT)
    text = result["text"]
    text_clean = text.lstrip("#* \t")
    if text_clean.startswith("EMERGENCY"):
        urgency = "EMERGENCY"
    elif text_clean.startswith("URGENT"):
        urgency = "URGENT"
    elif text_clean.startswith("MONITOR"):
        urgency = "MONITOR"
    else:
        urgency = "ROUTINE"

    return HandoffSummary(
        trace_id=trace.night_id,
        baby_id=trace.baby.baby_id,
        urgency_level=urgency,
        summary_text=text,
        source="claude_api",
        model_used=model or CLAUDE_MODEL,
        latency_ms=result["latency_ms"],
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_handoff(
    trace: NightTrace,
    final_label: str,
    classified_by: str = "pipeline",
    use_llm: bool = False,
    model: str | None = None,
    rule_events: list[dict] | None = None,
    baby_trend_flag: bool = False,
) -> HandoffSummary:
    """Generate a handoff summary. Mock by default, live with use_llm=True.

    `baby_trend_flag` carries the trend-tier signal from the orchestrator
    (see FinalTriage.baby_trend_flag). When True, the handoff gains a
    [TREND] block (mock) or a trend-aware paragraph (live), and routine
    per-night triage routes through the stable-but-trending template.
    Exception: artifact-dominated nights collapse to the artifact template
    with a non-actionable note rather than carrying [TREND].
    """
    if use_llm:
        result = generate_handoff_live(
            trace, final_label, classified_by, model,
            rule_events=rule_events,
            baby_trend_flag=baby_trend_flag,
        )
        if result is not None:
            return result
        # Fall back to mock if API call failed or budget exceeded
        print(f"[HANDOFF] Falling back to mock for trace {trace.night_id}")

    return generate_handoff_mock(
        trace, final_label,
        rule_events=rule_events,
        baby_trend_flag=baby_trend_flag,
    )
