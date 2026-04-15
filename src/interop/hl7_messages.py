"""HL7v2 message builders for Rhapsody interoperability demo.

Generates ADT^A01 (patient admission), ACK^A01 (acknowledgment), and
ORU^R01 (observation result) messages using hand-crafted pipe-delimited
segments. No external HL7 libraries — demonstrates deep understanding
of the standard.

HL7 version: 2.5.1
Encoding: |^~\\&
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

import numpy as np

from src.data_gen.synthetic import BabyProfile, NightTrace
from src.handoff.generator import HandoffSummary
from src.pipeline.orchestrator import FinalTriage
from src.config import GA_CATEGORIES, GA_URGENT_THRESHOLDS


# ---------------------------------------------------------------------------
# HL7v2 constants
# ---------------------------------------------------------------------------

FIELD_SEP = "|"
COMPONENT_SEP = "^"
ENCODING_CHARS = "^~\\&"
HL7_VERSION = "2.5.1"

# Facility identifiers (simulated)
SENDING_APP_DEVICE = "NICU_SPO2_MONITOR"
SENDING_APP_PIPELINE = "SPO2_EVAL_PIPELINE"
RECEIVING_APP_RHAPSODY = "RHAPSODY_ENGINE"
RECEIVING_APP_EHR = "EHR_SYSTEM"
FACILITY = "DEMO_HOSPITAL"

# LOINC codes
LOINC_SPO2 = "59408-5"
LOINC_SPO2_TEXT = "Oxygen saturation Pulse oximetry"

# Local codes for pipeline-specific observations
LOCAL_GA_WEEKS = "X-GA-WEEKS"
LOCAL_BIRTH_WT = "X-BIRTH-WT"
LOCAL_TRIAGE = "X-TRIAGE-001"
LOCAL_URGENCY = "X-URGENCY-001"
LOCAL_SAT_SECONDS = "X-SATSEC-001"
LOCAL_DESAT_COUNT = "X-DESAT-001"

# ICD-10 mapping for known conditions
ICD10_MAP = {
    "apnea_of_prematurity": ("P28.4", "Primary apnea of newborn"),
    "bpd": ("P27.1", "Bronchopulmonary dysplasia"),
    "anemia": ("P61.2", "Anemia of prematurity"),
    "rop": ("H35.10", "Retinopathy of prematurity, unspecified"),
    "nec": ("P77.9", "Necrotizing enterocolitis, unspecified"),
}

# Abnormal flags: urgency → OBX-8 (drives clinical alerting in EHR)
ABNORMAL_FLAGS = {
    "EMERGENCY": "AA",   # Critical abnormal — immediate action
    "URGENT": "A",       # Abnormal — prompt review
    "MONITOR": "H",      # Above high normal — watch closely
    "ROUTINE": "N",      # Normal
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _timestamp(iso_str: str | None = None) -> str:
    """Convert ISO datetime string (or now) to HL7 timestamp YYYYMMDDHHmmss."""
    if iso_str:
        dt = datetime.fromisoformat(iso_str)
    else:
        dt = datetime.now()
    return dt.strftime("%Y%m%d%H%M%S")


def _message_control_id(identifier: str, msg_type: str) -> str:
    """Deterministic message control ID from identifier + type."""
    raw = f"{identifier}:{msg_type}"
    return hashlib.md5(raw.encode()).hexdigest()[:10].upper()


def _escape_hl7(text: str) -> str:
    """Escape HL7 special characters in free text.

    HL7 escape sequences: \\F\\ for |, \\S\\ for ^, \\R\\ for ~,
    \\E\\ for \\, \\T\\ for &.
    """
    # Escape backslash first to avoid double-escaping
    text = text.replace("\\", "\\E\\")
    text = text.replace("|", "\\F\\")
    text = text.replace("^", "\\S\\")
    text = text.replace("~", "\\R\\")
    text = text.replace("&", "\\T\\")
    return text


def _split_nte(text: str, max_len: int = 200) -> list[str]:
    """Split handoff text into NTE-sized chunks at sentence boundaries."""
    sentences = text.replace("\n\n", "\n").split(". ")
    chunks = []
    current = ""

    for sentence in sentences:
        candidate = f"{current}. {sentence}" if current else sentence
        if len(candidate) > max_len and current:
            chunks.append(current.strip())
            current = sentence
        else:
            current = candidate

    if current.strip():
        chunks.append(current.strip())

    return chunks


def _classify_ga(ga_weeks: int) -> str:
    """Return GA category string for a given gestational age."""
    for cat, (lo, hi) in GA_CATEGORIES.items():
        if lo <= ga_weeks < hi:
            return cat
    return "term"


def _compute_dob(days_since_birth: int) -> str:
    """Compute date of birth from days_since_birth as HL7 timestamp."""
    dob = datetime.now() - timedelta(days=days_since_birth)
    return dob.strftime("%Y%m%d")


# ---------------------------------------------------------------------------
# ADT^A01 — Patient Admission
# ---------------------------------------------------------------------------

def build_adt_a01(baby: BabyProfile) -> str:
    """Build an HL7v2 ADT^A01 (Patient Admission) message from a BabyProfile.

    Simulates a NICU monitor system sending an admission message through
    Rhapsody to trigger SpO2 monitoring for a new patient.

    Segments: MSH, EVN, PID, PV1, OBX (baseline SpO2, GA, birth weight),
    DG1 (conditions if applicable).
    """
    now = _timestamp()
    ctrl_id = _message_control_id(baby.baby_id, "ADT")
    dob = _compute_dob(baby.days_since_birth)
    segments = []

    # MSH — Message Header
    # Note: MSH-1 is the field separator itself, so the segment starts
    # with MSH| and MSH-2 (encoding chars) follows immediately.
    segments.append(
        f"MSH|{ENCODING_CHARS}|{SENDING_APP_DEVICE}|{FACILITY}|"
        f"{RECEIVING_APP_RHAPSODY}|{FACILITY}|{now}||ADT^A01^ADT_A01|"
        f"{ctrl_id}|P|{HL7_VERSION}"
    )

    # EVN — Event Type
    segments.append(f"EVN|A01|{now}")

    # PID — Patient Identification
    # PID-3: patient ID (MR = medical record number)
    # PID-5: patient name (simulated)
    # PID-7: date of birth
    # PID-8: sex (U = unknown, standard for neonatal)
    pid_name = f"BABY^DEMO_{baby.baby_id[:4]}"
    segments.append(
        f"PID|1||{baby.baby_id}^^^{FACILITY}^MR||{pid_name}||{dob}|U"
    )

    # PV1 — Patient Visit
    # Patient class I = inpatient, location = NICU
    segments.append(
        f"PV1|1|I|NICU^BED01^^{FACILITY}||||||||||||||||||||||||||||||||||||{now}"
    )

    # OBX — Baseline SpO2 on admission (LOINC 59408-5)
    segments.append(
        f"OBX|1|NM|{LOINC_SPO2}^{LOINC_SPO2_TEXT}^LN||"
        f"{baby.spo2_baseline:.1f}|%^percent^UCUM||||||F"
    )

    # OBX — Gestational Age (local code, for round-trip)
    segments.append(
        f"OBX|2|NM|{LOCAL_GA_WEEKS}^Gestational Age^L||"
        f"{baby.gestational_age_weeks}|wk^weeks^UCUM||||||F"
    )

    # OBX — Birth Weight (local code, for round-trip)
    segments.append(
        f"OBX|3|NM|{LOCAL_BIRTH_WT}^Birth Weight^L||"
        f"{baby.birth_weight_grams}|g^grams^UCUM||||||F"
    )

    # DG1 — Diagnosis (conditions, if any real ones exist)
    dg_set = 1
    for condition in baby.known_conditions:
        if condition in ICD10_MAP:
            code, desc = ICD10_MAP[condition]
            segments.append(
                f"DG1|{dg_set}||{code}^{_escape_hl7(desc)}^I10||{now}|A"
            )
            dg_set += 1

    return "\r".join(segments)


# ---------------------------------------------------------------------------
# ACK^A01 — Acknowledgment
# ---------------------------------------------------------------------------

def build_ack_a01(adt_message: str) -> str:
    """Build an HL7v2 ACK^A01 acknowledgment for an ADT message.

    Demonstrates the full HL7 handshake pattern — Rhapsody always expects
    an ACK before marking the message as successfully delivered.

    MSA-1 = AA (Application Accept), MSA-2 = original message control ID.
    """
    # Extract original MSH-10 (message control ID) from the ADT
    msh_line = adt_message.split("\r")[0]
    msh_fields = msh_line.split("|")
    # MSH field indexing: [0]=MSH, [1]=encoding, [2]=sending_app, ...
    # MSH-10 is at index 9 (0-based, but MSH-1 is the separator)
    original_ctrl_id = msh_fields[9] if len(msh_fields) > 9 else "UNKNOWN"

    # Swap sender/receiver from original message
    original_sender = msh_fields[2] if len(msh_fields) > 2 else ""
    original_receiver = msh_fields[4] if len(msh_fields) > 4 else ""

    now = _timestamp()
    ack_ctrl_id = _message_control_id(original_ctrl_id, "ACK")

    segments = []

    # MSH — receiver becomes sender, sender becomes receiver
    segments.append(
        f"MSH|{ENCODING_CHARS}|{original_receiver}|{FACILITY}|"
        f"{original_sender}|{FACILITY}|{now}||ACK^A01^ACK|"
        f"{ack_ctrl_id}|P|{HL7_VERSION}"
    )

    # MSA — Message Acknowledgment
    # MSA-1: AA = Application Accept (message processed successfully)
    # MSA-2: reference the original message control ID
    segments.append(f"MSA|AA|{original_ctrl_id}")

    return "\r".join(segments)


# ---------------------------------------------------------------------------
# ADT Parser — round-trip demo
# ---------------------------------------------------------------------------

def parse_adt_a01(message: str) -> BabyProfile:
    """Parse an HL7v2 ADT^A01 message back into a BabyProfile.

    Demonstrates round-trip capability: BabyProfile -> ADT -> BabyProfile.
    Extracts patient ID, gestational age, birth weight, and SpO2 baseline
    from the appropriate segments.
    """
    segments = message.split("\r")
    baby_id = ""
    ga_weeks = 38
    birth_weight = 3000
    spo2_baseline = 98.0
    days_since_birth = 0
    conditions: list[str] = []

    # Reverse ICD-10 map for condition lookup
    icd10_reverse = {code: cond for cond, (code, _) in ICD10_MAP.items()}

    for seg in segments:
        fields = seg.split("|")
        seg_id = fields[0]

        if seg_id == "PID":
            # PID-3: patient ID (component 1 of field)
            if len(fields) > 3:
                pid3_components = fields[3].split("^")
                baby_id = pid3_components[0]
            # PID-7: date of birth → compute days_since_birth
            if len(fields) > 7 and fields[7]:
                try:
                    dob = datetime.strptime(fields[7], "%Y%m%d")
                    days_since_birth = (datetime.now() - dob).days
                except ValueError:
                    pass

        elif seg_id == "OBX":
            # OBX-3: observation identifier (component 1 = code)
            if len(fields) > 5:
                obx3_components = fields[3].split("^")
                code = obx3_components[0]
                value = fields[5]

                if code == LOINC_SPO2:
                    spo2_baseline = float(value)
                elif code == LOCAL_GA_WEEKS:
                    ga_weeks = int(value)
                elif code == LOCAL_BIRTH_WT:
                    birth_weight = int(value)

        elif seg_id == "DG1":
            # DG1-3: diagnosis code (component 1)
            if len(fields) > 3:
                dg3_components = fields[3].split("^")
                icd_code = dg3_components[0]
                if icd_code in icd10_reverse:
                    conditions.append(icd10_reverse[icd_code])

    if not conditions:
        conditions = ["none"]

    ga_category = _classify_ga(ga_weeks)
    from src.config import SPO2_BASELINES
    _, variability = SPO2_BASELINES.get(ga_category, (98.0, 0.8))

    return BabyProfile(
        baby_id=baby_id,
        gestational_age_weeks=ga_weeks,
        ga_category=ga_category,
        birth_weight_grams=birth_weight,
        days_since_birth=days_since_birth,
        known_conditions=conditions,
        spo2_baseline=spo2_baseline,
        spo2_variability=variability,
    )


# ---------------------------------------------------------------------------
# ORU^R01 — Observation Result
# ---------------------------------------------------------------------------

def build_oru_r01(
    trace: NightTrace,
    triage: FinalTriage,
    handoff: HandoffSummary,
    rule_events: list[dict] | None = None,
) -> str:
    """Build an HL7v2 ORU^R01 (Observation Result) message from pipeline output.

    Maps pipeline results to standard HL7 observation segments:
    - SpO2 stats → OBX with LOINC 59408-5
    - Triage result → OBX with local code
    - SatSeconds → OBX with local code
    - Handoff text → NTE (notes) segments

    OBX-8 abnormal flags drive clinical alerting in the receiving EHR:
    AA (critical) for EMERGENCY, A (abnormal) for URGENT, etc.
    """
    baby = trace.baby
    now = _timestamp()
    obs_time = _timestamp(trace.timestamp_start)
    ctrl_id = _message_control_id(trace.night_id, "ORU")
    dob = _compute_dob(baby.days_since_birth)

    # Compute trace stats
    mean_spo2 = float(np.mean(trace.spo2))
    min_spo2 = float(np.min(trace.spo2))
    ga_threshold = GA_URGENT_THRESHOLDS.get(baby.ga_category, 90)
    sat_seconds = float(np.sum(np.maximum(0, ga_threshold - trace.spo2)))

    # Count desaturation events from rule events
    events = rule_events or []
    n_desats = sum(
        1 for e in events
        if "urgent" in e.get("type", "") or e.get("rule") == "R1_SAFETY"
    )

    abnormal_flag = ABNORMAL_FLAGS.get(handoff.urgency_level, "N")
    segments = []

    # MSH — Pipeline is now the sender, EHR is receiver
    segments.append(
        f"MSH|{ENCODING_CHARS}|{SENDING_APP_PIPELINE}|{FACILITY}|"
        f"{RECEIVING_APP_EHR}|{FACILITY}|{now}||ORU^R01^ORU_R01|"
        f"{ctrl_id}|P|{HL7_VERSION}"
    )

    # PID — same patient demographics
    pid_name = f"BABY^DEMO_{baby.baby_id[:4]}"
    segments.append(
        f"PID|1||{baby.baby_id}^^^{FACILITY}^MR||{pid_name}||{dob}|U"
    )

    # OBR — Observation Request (overnight SpO2 monitoring order)
    segments.append(
        f"OBR|1|{trace.night_id}||{LOINC_SPO2}^Overnight SpO2 Monitoring^LN|||"
        f"{obs_time}||||||||||||||||F"
    )

    # OBX 1 — Mean SpO2 (LOINC)
    segments.append(
        f"OBX|1|NM|{LOINC_SPO2}^{LOINC_SPO2_TEXT} Mean^LN||"
        f"{mean_spo2:.1f}|%^percent^UCUM|>94|{abnormal_flag}|||F|||{obs_time}"
    )

    # OBX 2 — Min SpO2 (LOINC)
    segments.append(
        f"OBX|2|NM|{LOINC_SPO2}^{LOINC_SPO2_TEXT} Min^LN||"
        f"{min_spo2:.1f}|%^percent^UCUM|>90|{abnormal_flag}|||F|||{obs_time}"
    )

    # OBX 3 — Triage Label (local code)
    segments.append(
        f"OBX|3|ST|{LOCAL_TRIAGE}^Triage Label^L||"
        f"{triage.final_label}||||||F|||{obs_time}"
    )

    # OBX 4 — Urgency Level (local code) — drives nurse station alerts
    segments.append(
        f"OBX|4|ST|{LOCAL_URGENCY}^Urgency Level^L||"
        f"{handoff.urgency_level}||||||F|||{obs_time}"
    )

    # OBX 5 — SatSeconds Burden (local code)
    segments.append(
        f"OBX|5|NM|{LOCAL_SAT_SECONDS}^SatSeconds Burden^L||"
        f"{sat_seconds:.0f}|sec^seconds^UCUM|<100||||F|||{obs_time}"
    )

    # OBX 6 — Desaturation Event Count (local code)
    segments.append(
        f"OBX|6|NM|{LOCAL_DESAT_COUNT}^Desat Event Count^L||"
        f"{n_desats}|{{events}}^events^UCUM|0||||F|||{obs_time}"
    )

    # NTE — Handoff summary text (split into 200-char chunks per HL7 best practice)
    chunks = _split_nte(_escape_hl7(handoff.summary_text))
    for i, chunk in enumerate(chunks, start=1):
        segments.append(f"NTE|{i}|L|{chunk}|RE")

    return "\r".join(segments)
