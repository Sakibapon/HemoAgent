"""
Parameter and event display configuration for the HemoAgent Session Simulator.

`PARAM_SPECS` defines, per parameter, the display label, unit, and gauge range. Ranges
are tuned to the raw device-derived data (Pa is negative and large; Pv ~80-110). These
are DEMONSTRATION values for visualization, not clinical thresholds.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ParamSpec:
    key: str        # column name in the per-minute frame
    label: str
    unit: str
    gmin: float     # gauge / chart scale minimum
    gmax: float     # gauge / chart scale maximum


# Display order for the readout panel and the chart selector.
PARAM_SPECS = [
    ParamSpec("UF_rate_mlmin",        "UF rate",           "ml/min",  0,  25),
    ParamSpec("UF_removed_L",         "UF removed",        "L",       0,   6),
    ParamSpec("TMP",                  "TMP",               "mmHg",    0, 320),
    ParamSpec("Pv",                   "Pv (venous)",       "mmHg",    0, 160),
    ParamSpec("Pa",                   "Pa (arterial)",     "mmHg", -280, -80),
    ParamSpec("Pu",                   "Pu (upstream)",     "mmHg",    0, 140),
    ParamSpec("Pd",                   "Pd (downstream)",   "mmHg",    0,  90),
    ParamSpec("Upump",                "Blood pump (Up)",   "pulse/s", 0,  40),
    ParamSpec("Dpump",                "Dial. pump (Dp)",   "pulse/s", 0,  25),
    ParamSpec("CD2",                  "Conductivity CD2",  "mS/cm",  12,  16),
    ParamSpec("T2",                   "Dialysate temp",    "C",      34,  38),
    ParamSpec("hypotension_risk_score", "Hypotension risk", "score", 0, 3.5),
]

PARAM_SPECS_BY_KEY = {p.key: p for p in PARAM_SPECS}

# Adverse-event / safety flags -> display label (for the status board).
EVENT_LABELS = {
    "hypotension":       "Hypotension",
    "arrhythmia":        "Arrhythmia",
    "desaturation":      "Desaturation",
    "dizziness_syncope": "Dizziness / Syncope",
    "nausea_vomiting":   "Nausea / Vomiting",
    "muscle_cramp":      "Muscle Cramp",
    "chest_pain":        "Chest Pain",
    "fever_chill":       "Fever / Chills",
    "seizure":           "Seizure",
    "air_detection":     "Air Detection",
    "blood_leak":        "Blood Leak",
}
