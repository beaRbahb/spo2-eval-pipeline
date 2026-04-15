"""Tests for HL7v2 interoperability message builders.

Validates ADT^A01 structure, ORU^R01 mapping, ACK handshake,
round-trip parsing, LOINC codes, abnormal flags, and HL7 escaping.
"""
import numpy as np
import pytest

from src.data_gen.synthetic import NightTrace, BabyProfile
from src.handoff.generator import HandoffSummary
from src.pipeline.orchestrator import FinalTriage
from src.interop.hl7_messages import (
    build_adt_a01,
    build_ack_a01,
    build_oru_r01,
    parse_adt_a01,
    _escape_hl7,
    LOINC_SPO2,
)


def _make_baby(
    baby_id: str = "TEST0001",
    ga_weeks: int = 30,
    ga_category: str = "very_preterm",
    conditions: list[str] | None = None,
) -> BabyProfile:
    """Create a minimal BabyProfile for testing."""
    return BabyProfile(
        baby_id=baby_id,
        gestational_age_weeks=ga_weeks,
        ga_category=ga_category,
        birth_weight_grams=1500,
        days_since_birth=14,
        known_conditions=conditions or ["apnea_of_prematurity"],
        spo2_baseline=93.0,
        spo2_variability=1.5,
    )


def _make_trace(baby: BabyProfile | None = None, label: str = "urgent") -> NightTrace:
    """Create a minimal NightTrace for testing."""
    if baby is None:
        baby = _make_baby()
    n = 28800
    spo2 = np.full(n, 93.0)
    # Inject a desat for urgent traces
    if label in ("urgent", "emergency"):
        spo2[5000:5020] = 82.0
    return NightTrace(
        baby=baby,
        night_id="TRACE001",
        night_number=1,
        timestamp_start="2026-01-15T21:00:00",
        spo2=spo2,
        accelerometer=np.zeros((n, 3)),
        accel_magnitude=np.full(n, 0.5),
        ground_truth_label=label,
        events=[],
    )


def _make_handoff(urgency: str = "URGENT") -> HandoffSummary:
    """Create a minimal HandoffSummary for testing."""
    return HandoffSummary(
        trace_id="TRACE001",
        baby_id="TEST0001",
        urgency_level=urgency,
        summary_text="URGENT — Baby had 2 desaturation events below threshold.",
        source="mock_template",
        model_used="none",
        latency_ms=0,
    )


def _make_triage(label: str = "urgent") -> FinalTriage:
    """Create a minimal FinalTriage for testing."""
    return FinalTriage(
        trace_id="TRACE001",
        baby_id="TEST0001",
        ground_truth="urgent",
        final_label=label,
        source="tier1_rules",
        confidence=0.95,
    )


# ---------------------------------------------------------------------------
# Test 1: ADT message structure
# ---------------------------------------------------------------------------

def test_adt_a01_structure():
    """ADT^A01 must contain MSH, EVN, PID, PV1, and OBX segments."""
    baby = _make_baby()
    msg = build_adt_a01(baby)
    segments = msg.split("\r")
    seg_ids = [s.split("|")[0] for s in segments]

    assert "MSH" in seg_ids
    assert "EVN" in seg_ids
    assert "PID" in seg_ids
    assert "PV1" in seg_ids
    assert "OBX" in seg_ids


# ---------------------------------------------------------------------------
# Test 2: MSH encoding correctness
# ---------------------------------------------------------------------------

def test_msh_encoding():
    """MSH must start with MSH|^~\\&| and MSH-9 must be ADT^A01^ADT_A01."""
    baby = _make_baby()
    msg = build_adt_a01(baby)
    msh = msg.split("\r")[0]

    assert msh.startswith("MSH|^~\\&|")

    # MSH field indexing: MSH|enc|send_app|send_fac|recv_app|recv_fac|ts||msg_type|ctrl_id|proc_id|ver
    # After split on |: [0]=MSH [1]=^~\& [2]=send_app ... [8]=msg_type
    fields = msh.split("|")
    assert fields[8] == "ADT^A01^ADT_A01"
    assert fields[11] == "2.5.1"


# ---------------------------------------------------------------------------
# Test 3: ADT round-trip parsing
# ---------------------------------------------------------------------------

def test_adt_round_trip():
    """parse_adt_a01(build_adt_a01(baby)) must reproduce key BabyProfile fields."""
    baby = _make_baby()
    msg = build_adt_a01(baby)
    parsed = parse_adt_a01(msg)

    assert parsed.baby_id == baby.baby_id
    assert parsed.gestational_age_weeks == baby.gestational_age_weeks
    assert parsed.birth_weight_grams == baby.birth_weight_grams
    assert abs(parsed.spo2_baseline - baby.spo2_baseline) < 0.1
    assert parsed.ga_category == baby.ga_category
    assert "apnea_of_prematurity" in parsed.known_conditions


# ---------------------------------------------------------------------------
# Test 4: ACK message structure
# ---------------------------------------------------------------------------

def test_ack_a01_structure():
    """ACK must contain MSH + MSA, with MSA-1=AA and MSA-2=original control ID."""
    baby = _make_baby()
    adt = build_adt_a01(baby)
    ack = build_ack_a01(adt)
    segments = ack.split("\r")
    seg_ids = [s.split("|")[0] for s in segments]

    assert "MSH" in seg_ids
    assert "MSA" in seg_ids

    # MSA fields
    msa = [s for s in segments if s.startswith("MSA")][0]
    msa_fields = msa.split("|")
    assert msa_fields[1] == "AA"  # Application Accept

    # MSA-2 should reference the original ADT control ID
    adt_msh = adt.split("\r")[0].split("|")
    original_ctrl_id = adt_msh[9]
    assert msa_fields[2] == original_ctrl_id


# ---------------------------------------------------------------------------
# Test 5: ORU message structure
# ---------------------------------------------------------------------------

def test_oru_r01_structure():
    """ORU^R01 must contain MSH, PID, OBR, OBX, and NTE segments."""
    trace = _make_trace()
    triage = _make_triage()
    handoff = _make_handoff()

    msg = build_oru_r01(trace, triage, handoff)
    segments = msg.split("\r")
    seg_ids = [s.split("|")[0] for s in segments]

    assert "MSH" in seg_ids
    assert "PID" in seg_ids
    assert "OBR" in seg_ids
    assert "OBX" in seg_ids
    assert "NTE" in seg_ids

    # MSH-9 must be ORU^R01^ORU_R01
    msh = segments[0].split("|")
    assert msh[8] == "ORU^R01^ORU_R01"


# ---------------------------------------------------------------------------
# Test 6: LOINC code in OBX-3
# ---------------------------------------------------------------------------

def test_oru_loinc_code():
    """OBX-3 must contain LOINC 59408-5 for SpO2 observations."""
    trace = _make_trace()
    triage = _make_triage()
    handoff = _make_handoff()

    msg = build_oru_r01(trace, triage, handoff)
    obx_segments = [s for s in msg.split("\r") if s.startswith("OBX")]

    # At least one OBX should have LOINC 59408-5
    loinc_found = any(LOINC_SPO2 in seg for seg in obx_segments)
    assert loinc_found, f"LOINC {LOINC_SPO2} not found in OBX segments"


# ---------------------------------------------------------------------------
# Test 7: Abnormal flags mapping
# ---------------------------------------------------------------------------

def test_abnormal_flags_emergency():
    """EMERGENCY urgency must map to OBX-8 = AA (critical abnormal)."""
    trace = _make_trace(label="emergency")
    triage = _make_triage(label="emergency")
    handoff = _make_handoff(urgency="EMERGENCY")

    msg = build_oru_r01(trace, triage, handoff)
    # Check the first OBX (mean SpO2) for abnormal flag
    obx_segments = [s for s in msg.split("\r") if s.startswith("OBX")]
    first_obx = obx_segments[0].split("|")
    # OBX-8 is at index 8
    assert first_obx[8] == "AA"


def test_abnormal_flags_routine():
    """ROUTINE urgency must map to OBX-8 = N (normal)."""
    baby = _make_baby(ga_weeks=39, ga_category="term")
    trace = _make_trace(baby=baby, label="normal")
    triage = _make_triage(label="normal")
    handoff = _make_handoff(urgency="ROUTINE")

    msg = build_oru_r01(trace, triage, handoff)
    obx_segments = [s for s in msg.split("\r") if s.startswith("OBX")]
    first_obx = obx_segments[0].split("|")
    assert first_obx[8] == "N"


# ---------------------------------------------------------------------------
# Test 8: HL7 special character escaping
# ---------------------------------------------------------------------------

def test_escape_hl7():
    """Pipe and caret characters in free text must be properly escaped."""
    assert _escape_hl7("SpO2 | test") == "SpO2 \\F\\ test"
    assert _escape_hl7("A^B") == "A\\S\\B"
    assert _escape_hl7("x~y") == "x\\R\\y"
    assert _escape_hl7("a&b") == "a\\T\\b"
    # Backslash itself
    assert _escape_hl7("path\\file") == "path\\E\\file"
