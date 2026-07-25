# HemoAgent Session Simulator - Phase 2

A minimal Streamlit **playback** simulator for the raw device-level synthetic home
hemodialysis data from Phase 1. It replays a session minute by minute, shows the current
machine-parameter readouts, one large trend chart with a variable selector, and the
adverse-event status board read straight from the data.

Playback only - no detection, alerts, or LLM. Not a medical device.

## Files

| File | Role |
|------|------|
| `config.py` | Paths, raw-column scaling, patient profile, risk formula, playback speeds |
| `data_loader.py` | Decodes raw ~5 Hz CSV, resamples to per-minute, derives UF rate / TMP / risk |
| `param_config.py` | `PARAM_SPECS` (labels, units, chart ranges) and event labels |
| `classifier.py` | Phase-1 emergency classifier: maps an anomaly's active flags to a Tier + action + inbox recipients |
| `app.py` | Streamlit UI: left navbar, dashboard (status banner, chart + resolution button, readouts, anomaly strip, event board), and Patient / Clinician / LLM inbox pages |

## Phase 1 — emergency classifier (From Detection to Action)

Deterministic CODE-layer tiering runs on every anomaly (no AI yet):

- **Tier 1** (`air_detection`, `blood_leak`) and **Tier 2** (`hypotension`, `seizure`) →
  🔴 **STOP + emergency call**: a red message (patient profile + parameters + anomaly) is
  posted to the Patient and Clinician inboxes, the dashboard banner turns red, and
  **playback pauses** at that minute (press Play to resume past it).
- **Tier 3** — derived *moderate drift* (per-minute hypotension risk rising above HI=1.8,
  re-armed below LO=1.5) → amber "reduce UFR" note to the Clinician inbox. No stop.
- **Every other flag** (arrhythmia, desaturation, dizziness, nausea, cramp, chest pain,
  fever) → advisory message to Patient / Clinician / LLM. (These become the LLM path in
  Phase 2.)

Tiers and thresholds live in `config.py` (`TIER1_EVENTS`, `TIER2_EVENTS`,
`MODERATE_DRIFT_RISK_HI/LO`). VND is skipped for now (no column in the data).

## Pages

A left navbar switches between:

- **Main Dashboard** - playback controls, seek slider with a red anomaly strip beneath it,
  the big trend chart with a **Variable** selector and a **Time resolution** button
  (Seconds / Minutes / Hours) directly under it, machine-parameter readouts, and the
  adverse-event status board.
- **Patient / Clinician / LLM Inbox** - each shows the same auto-posted messages: on every
  anomaly in the data a card is posted with the patient profile, active anomalies, and the
  current parameter values at that moment. (Placeholder routing - all three are identical
  for now.)

## Data

Replays the raw files in `../Phase_1_SytheticData/`: `PID_0001_xkidneyData.csv`
(baseline) and `PID_0161_anomaly.csv` (adverse events). Each is one 240-minute session at
~5 Hz in scaled-integer units. `data_loader.py` decodes the headers (e.g.
`CD2 (x100 mS/cm)` -> /100), resamples to one row per minute, and derives UF removed (L),
UF rate (ml/min), TMP = `1.45*Pv - (Pu+Pd)/2`, and the hypotension risk score
= `0.95*(UF_rate/13) + 0.85*(TMP/300) + 0.05`.

Override the location with `HEMO_DATA_DIR`; add more files via `config.SESSION_FILES`.

## Run

```
pip install -r requirements.txt
streamlit run app.py
```

Pick a session, press Play, choose a speed (1x-100x), and switch the charted variable
with the selector above the chart. The seek slider jumps to any minute when paused.
