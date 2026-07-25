"""
Configuration for the HemoAgent Session Simulator (Phase 2).

Playback only: replays the raw device-level Phase-1 data (~5 Hz, scaled-integer units),
decoded and resampled to one row per minute. Paths, column scaling, the single patient
profile, the derived risk formula, and playback speeds all live here.
"""

import os

# ---------------------------------------------------------------------------
# Data paths
# ---------------------------------------------------------------------------
DEFAULT_DATA_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "Phase_1_SytheticData")
)
DATA_DIR = os.environ.get("HEMO_DATA_DIR", DEFAULT_DATA_DIR)

# Raw session files shown in the selector (label is the dropdown text).
SESSION_FILES = [
    {"file": "PID_0001_xkidneyData.csv", "label": "Session 1 - Baseline (stable)"},
    {"file": "PID_0161_anomaly.csv",      "label": "Session 2 - Anomaly (adverse events)"},
]

# ---------------------------------------------------------------------------
# Single synthetic patient profile (project README section 8)
# ---------------------------------------------------------------------------
PATIENT_PROFILE = {
    "name": "James R. Mitchell",
    "age": 63,
    "sex": "Male",
    "esrd_cause": "Diabetic nephropathy (T2DM)",
    "vascular_access": "AVF, left forearm",
    "dialyzer": "F160NR (1.6 m2)",
    "schedule": "M-W-F, 240 min",
    "baseline_labs": "Hb 10.2 / Hct 31% | Na 137 K 4.8 Ca 8.8 Alb 3.5",
}

# ---------------------------------------------------------------------------
# Raw-column decoding (scaling is embedded in the CSV header names)
# ---------------------------------------------------------------------------
# raw header -> (clean key, scale divisor).
RAW_COLUMN_MAP = {
    "Upump_Encoder (pulse/sec)": ("Upump", 1.0),   # blood pump speed (Qb proxy)
    "Dpump_Encoder (pulse/sec)": ("Dpump", 1.0),   # dialysate pump (Qd proxy)
    "CD1 (x100 mS/cm)": ("CD1", 0.01),
    "CD2 (x100 mS/cm)": ("CD2", 0.01),
    "Temperature2 (x100 C)": ("T2", 0.01),         # dialysate temperature
    "Pa (mmHg)": ("Pa", 1.0),
    "Pd (mmHg)": ("Pd", 1.0),
    "Pu (mmHg)": ("Pu", 1.0),
    "Pv (mmHg)": ("Pv", 1.0),
}
# Load cell: each stored count = 10 g, used to derive UF removed (L) and UF rate.
LOAD_CELL_RAW = "Load Cell (x10 g)"
LOAD_CELL_G_PER_COUNT = 10.0

# Adverse-event / safety flag columns (0/1) shown on the status board.
ADVERSE_EVENT_COLUMNS = [
    "hypotension", "arrhythmia", "desaturation", "dizziness_syncope",
    "nausea_vomiting", "muscle_cramp", "chest_pain", "fever_chill",
    "seizure", "air_detection", "blood_leak",
]

# ---------------------------------------------------------------------------
# Derived hypotension risk score (README section 7 / Exorenal formula)
#   TMP  = 1.45 * Pv - (Pu + Pd) / 2
#   Risk = 0.95 * (UF_rate / 13) + 0.85 * (TMP / 300) + 0.05
# ---------------------------------------------------------------------------
RISK_UF_NORM = 13.0
RISK_TMP_NORM = 300.0
RISK_MEMVOL = 1.0

# ---------------------------------------------------------------------------
# Phase 1 - emergency classifier tiers ("From Detection to Action")
# ---------------------------------------------------------------------------
# Deterministic CODE-layer tiering. Tier 1/2 -> STOP the pump + emergency call and pause
# playback; Tier 3 -> reduce-UFR recommendation (no stop); every other adverse-event flag
# is an advisory that just notifies the inboxes. VND is skipped for now (no column).
TIER1_EVENTS = ["air_detection", "blood_leak"]      # catastrophic mechanical -> STOP + call
TIER2_EVENTS = ["hypotension", "seizure"]           # severe physiologic     -> STOP + call
# Tier 3 "moderate drift" is derived (not a flag): the per-minute hypotension risk score
# rising above HI, re-armed only after it falls back below LO (hysteresis, so the noisy
# risk signal does not fire repeatedly while hovering near the threshold).
MODERATE_DRIFT_RISK_HI = 1.8
MODERATE_DRIFT_RISK_LO = 1.5

# ---------------------------------------------------------------------------
# Session / playback
# ---------------------------------------------------------------------------
SESSION_MINUTES = 240
PLAYBACK_SPEEDS = [1, 5, 20, 60, 100]
DEFAULT_SPEED = 5
