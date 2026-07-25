# HemoAgent — Project Knowledge Base

> Load this file at the start of any new session to restore full context.

---

## 1. Project Overview

**HemoAgent** is an agentic AI system for **home hemodialysis (HHD) monitoring**, built by Tasnim (PhD student, UVM CS). Faculty advisor: Prof. Byung Suk Lee. Industry partner: **Exorenal** ("Revolutionizing Dialysis").

### System Architecture

- **8 LLM agents** + **3 deep learning models**
- **CODE layer** (deterministic, 80% of cases, runs locally at 1 Hz) — handles hard stops, simple threshold alarms
- **LLM layer** (20% of cases) — handles complex multi-parameter reasoning
- **LLMs never make autonomous safety decisions** — core architectural constraint

### Three Deep Learning Models

| Model | Purpose |
|---|---|
| Personalized Threshold Predictor | Patient-specific alert thresholds |
| IDH Predictor (GRU-RNN) | Real-time intradialytic hypotension prediction |
| OTA Optimizer | Optimizes treatment profile to minimise adverse events |

### Exorenal OTA (Optimised Treatment Algorithm)

Transmitted wirelessly to the dialysis machine. Defines blood and dialysate flow rates, UF profile, heparin schedule, and dialysate composition per time block.

---

## 2. What Hemodialysis Is

HD cleans the blood of patients whose kidneys have failed (ESRD). Blood is pumped out, filtered through a dialyzer membrane, and returned. Dialysate on the other side draws out waste and excess fluid by diffusion and osmosis.

**Standard schedule:** 3 sessions/week, 4 hours each (240 minutes).

---

## 3. Session Stages

### Stage 1 — Pre-treatment
Patient weighed → IDWG calculated → pre-dialysis BUN drawn → clinician programs prescription into machine.

### Stage 2 — Start (min 0–10)
Circuit primed, needles inserted into AVF, heparin bolus given, blood pump ramps to prescribed Qb, alarm windows auto-set.

### Stage 3 — Hours 1–2 (min 10–120)
UF rate highest (10–13 ml/min, front-loaded). Qb steady. Heparin infusion running. TMP rises from membrane fouling. BP checked every 15–30 min.

### Stage 4 — Hours 3–4 (min 120–210)
UF rate tapered. Peak IDH risk window. Serum K falling since start. Heparin stopped at min 195 (45 min before end).

### Stage 5 — Termination (min 210–240)
UF stopped at target volume. Blood returned. Needles removed.

### Stage 6 — Post-session
Post weight, post BP, post BUN drawn. Kt/V and URR calculated from pre/post BUN. If Kt/V < 1.2 → adjust next prescription.

### Stage 7 — Interdialytic period
Fluid, K, BUN accumulate. **Monday effect:** 2-day gap → IDWG 2.5–3.2 kg (elevated IDH risk).

---

## 4. Parameter Classification

### 4A. Per-Patient Data (monthly labs + enrollment)

| Field | Code | Unit | Notes |
|---|---|---|---|
| Body weight today | Bwt | kg | IDWG = Bwt − dry_weight |
| BMI | BMI | kg/m² | Context only |
| Hemoglobin | Hb | g/dL | Target 10–12 for ESRD |
| Hematocrit | Hct | % | ≈ 3×Hb; rises during session |
| Sodium | Na | mmol/L | |
| Potassium | K | mEq/L | Drives dK (Rule of 7) |
| Calcium | Ca | mg/dL | Drives dCa |
| Serum albumin | Alb | g/dL | < 3.5 = major IDH risk factor |
| CRP | CRP | mg/L | Inflammation marker |
| Pre-dialysis BP | PreBP | mmHg | Baseline for IDH detection |
| Interdialytic weight gain | IDWG | kg | = UF target for this session |
| Diabetes | DM | Bool | Higher IDH risk (autonomic dysfunction) |
| Heart failure | HF | Bool | Limits fluid removal tolerance |
| Vascular access | Access | AVF/AVG/Catheter | Determines max Qb |
| Arrhythmia history | had_arrhythmia | Bool | Sets dK floor at 2.0 |
| Bleeding risk | bleeding_risk | Bool | Triggers heparin-free protocol |

### 4B. Per-Session Data (entered before each session)

| Field | Code | Unit | Notes |
|---|---|---|---|
| Dialyzer | Dz | — | e.g. F200NR |
| Dialysate K | dK | mEq/L | Set by Rule of 7 |
| Dialysate Ca | dCa | mEq/L | Default 2.5, adjusted per serum Ca |
| Pre-dialysis BUN | pBUN | mg/dL | Blood draw, entered manually |
| Previous Kt/V | prev_ktv | — | Outcome from last session. Target ≥ 1.2 |
| Previous URR | prev_urr | % | Outcome from last session. Target ≥ 65% |
| Had IDH last session | had_IDH | Bool | Triggers cool T2 |

> Kt/V and URR are calculated outcomes from the previous session, not clinician inputs.

### 4C. Prescription Outputs (clinician programs into machine)

| Parameter | Code | Typical value | Logic |
|---|---|---|---|
| Blood flow rate | Qb | 300–450 ml/min | Access type + adequacy + safety caps |
| Dialysate flow rate | Qd | 500–800 ml/min | round(Qb × 1.5 / 50) × 50, clamped |
| UF total target | UF target | = IDWG in L | Must not exceed 13 ml/kg/h |
| UF rate | UF rate | ml/kg/h | Front-loaded profile |
| Dialysate temperature | T2 | 35.5–36.5°C | Cool if IDH risk |
| Dialysate K | dK | 1.0–4.0 mEq/L | Rule of 7: dK = 7 − serum K |
| Dialysate Ca | dCa | 2.5–3.0 mEq/L | Default 2.5; adjust for Ca levels or IDH |
| Heparin protocol | — | bolus + infusion | 25 IU/kg bolus; 1500 IU/hr; stop at min 195 |
| Dialyzer | Dz | F130NR–F200NR | BSA-based 4-tier; upgrade if Kt/V < 1.1 |

### 4D. Machine Sensors (per-minute, automated)

| Parameter | Code | Unit | Alarm condition |
|---|---|---|---|
| Arterial pressure | Pa | mmHg | < −250 (hemolysis risk) |
| Venous pressure | Pv | mmHg | Drop ≥ 25 mmHg from baseline (VND) |
| Upstream dialysate P | Pu | mmHg | > 88 |
| Downstream dialysate P | Pd | mmHg | < 0 |
| Transmembrane pressure | TMP | mmHg | > 300 or ± 40 from baseline |
| Actual UF delivered | UF/min | ml/min | Deviation from prescription |
| Inlet conductivity | CD1 | mS/cm | ± 5% → bypass dialysate (not full stop) |
| Outlet conductivity | CD2 | mS/cm | ΔCD > 1.0 |
| Dialysate temperature | T2 | °C | < 35 or > 38 → bypass |
| Air detection | — | Bool | Any detection → immediate pump stop |
| Blood leak | — | Bool | Any detection → immediate pump stop |

### 4E. Patient Vitals

| Parameter | Code | Normal | Alert |
|---|---|---|---|
| Blood pressure | BP | SBP 100–155 mmHg | Drop ≥ 20 mmHg or SBP < 90 |
| ECG | ECG | Normal sinus | Any arrhythmia |
| Oxygen saturation | SpO₂ | 94–99% | < 92% |

> BP is measured every 15–30 min, not per minute. `bp_measured` column = 1 at actual readings, 0 elsewhere.

### 4F. Adverse Events

| Event | Rate | Timing |
|---|---|---|
| Hypotension (IDH) | 12% | Hr 2–3 (min 90–180). Primary event. |
| Muscle cramp | 12% | Hr 3–4 |
| Nausea/vomiting | 10% | Early or co-occurs with IDH (60%) |
| Dizziness/syncope | 6% | 2–5 min after IDH |
| Arrhythmia | 6% | Any time, more common late |
| Chest pain | 2.5% | During severe IDH |
| Desaturation | 2.5% | During IDH |
| Fever/chills | 1.5% | Min 30–60 |
| Seizure | < 1% | Any |

Cascade: IDH → dizziness (2–5 min lag) → nausea. Events persist 5–20 min.

---

## 5. Machine Alarm Rules (Hard Stops — CODE Layer)

| Condition | Machine Action |
|---|---|
| Air detected | Immediate pump stop + venous clamp |
| Blood leak detected | Immediate pump stop |
| Pa < −250 mmHg | Alarm (hemolysis risk) |
| Pv drops ≥ 25 mmHg from baseline | Alarm (VND risk) |
| TMP > 300 mmHg | Alarm (clotting risk) |
| CD1 out of range (± 5%) | **Bypass dialysate; keep blood pump running** |
| T2 < 35°C or > 38°C | Alarm; bypass dialysate |

> Conductivity alarm → bypass (not full stop). Air/blood leak → full stop.

---

## 6. Prescription Decision Rules — v4 (Evidence-Corrected)

### 1. IDWG
```
IDWG = weight_today − dry_weight
IF IDWG < 0 → IDWG = 0, ⚠ warning (dehydration or error)
```

### 2. Qb — Blood flow rate (3 steps)
```
STEP 1 — Access-based start:
  catheter → Qb = 300 (Pa-guided; NOT a hard cap)
  AVF/AVG  → Qb = 350

STEP 2 — Adequacy boosts (AVF/AVG only):
  IF prev_ktv < 1.2 → Qb += 50, max 450
  IF prev_urr < 65% → Qb += 25, max 450

STEP 3 — Safety caps (override boosts):
  IF HF == True AND Qb > 300 → Qb = 300
  IF Hb < 8.0 g/dL AND Qb > 300 → Qb = 300
```
*KDOQI 2015 §3 · QEHB NHS v3 · DALP BMC Nephrol 2008*

### 3. Qd — Dialysate flow rate
```
Qd = round(Qb × 1.5 / 50) × 50
Qd = clamp(Qd, min=500, max=800)
```
*Note: 1.5× is a guideline default. CKJ 2024: Qd 300 ml/min achieves same Kt/V as 500. · QEHB NHS v3*

### 4. UF target & rate
```
UF_target_L   = IDWG
UF_rate_mlmin = (IDWG × 1000) / session_min
UF_rate_mlkgh = (UF_rate_mlmin × 60) / dry_weight

IF UF_rate_mlkgh > 13.0 → ⚠ HARD LIMIT (KDOQI; HR 1.31)
ELIF UF_rate_mlkgh > 10.0 → ⚡ Early warning (HR 1.22)
IF HF == True AND rate > 10.0 → ⚠ Additional HF warning
```
*KDOQI 2015 §4.2 · Flythe Kidney Int 2011 · Flythe CJASN 2023 (n=337,863)*

### 5. T2 — Dialysate temperature
```
high_idh_risk = had_IDH OR (DM AND albumin < 3.5)

IF high_idh_risk:
    IF core_temp known → T2 = max(35.0, core_temp − 0.5°C)
    ELSE               → T2 = 35.5°C (fixed fallback)
ELSE → T2 = 36.5°C (standard)
```
*Tan et al. Semin Dial 2025 (26 RCTs, OR=0.35) · TEMP RCT NCT02628366 · EBPG §3.4*

### 6. dK — Dialysate potassium (Rule of 7)
```
raw_dK = 7.0 − serum_K
dK     = clamp(raw_dK, 1.0, 4.0)
dK     = round(dK × 2) / 2    ← nearest 0.5

Overrides (in order):
  IF serum_K < 3.5 (hypokalemia) → dK = min(dK + 1.0, 4.0)
  ELIF had_arrhythmia AND dK < 2.0 → dK = 2.0  (safety floor)
```
*Rule of 7: Renal Fellow Network 2008 · Pun & Middleton JASN 2017 (DOPPS n=55,183) · PMC8767120*

### 7. dCa — Dialysate calcium
```
IF serum_Ca < 8.5  (hypocalcaemia, KDIGO 2017) → dCa = 3.0
ELIF serum_Ca > 10.0 (hypercalcaemia)           → dCa = 2.5
ELIF had_IDH                                     → dCa = 3.0 (heuristic)
ELSE                                              → dCa = 2.5 (default)
```
*KDIGO 2017 CKD-MBD §4.1 · Korean registry 2019 (dCa ≥ 3.5 → 2.2× mortality)*

### 8. Heparin
```
IF bleeding_risk:
    heparin_free = True; bolus = 0; infusion = 0
    Flush circuit with saline q15–30 min + maintain high Qb
ELSE:
    bolus    = clamp(round(25 × dry_weight / 100) × 100, 1000, 5000)
    infusion = 1500 IU/hr  (range 1000–2000; centre-specific)
    stop_min = session_min − 45  (range 30–60 min before end)
```
*PMC4088960 · ERA-EDTA · Daugirdas Handbook of Dialysis §14 (2015)*

### 9. Dialyzer — BSA-based 4-tier
```
BSA = sqrt(height_cm × dry_weight_kg / 3600)   [Mosteller 1987]

BSA < 1.5  → F130NR (1.3 m²)
BSA 1.5–1.7 → F160NR (1.6 m²)
BSA 1.7–1.9 → F180NR (1.8 m²)
BSA ≥ 1.9  → F200NR (2.0 m²)

IF prev_ktv < 1.1 → upgrade one tier (max F200NR)
All: high-flux polysulfone
```
*Mosteller 1987 · Sci Reports 2021 (n=234,638; XL HR 0.75 vs medium) · KDOQI 2015 §2*

---

## 7. OTA Hypotension Risk Model

### Causal Tree

```
TMP = 1.45 × Pv − (Pu + Pd) / 2    [Exorenal proprietary formula]

Pa_Pv_score = 0.85×Qb_norm + 0.10×NeedleSize + 0.05×MemVol
TMP_score   = 0.45×Pa_Pv_score + 0.45×Pu_Pd_score + 0.05×Hct_slope
Risk        = 0.95×UF_rate + 0.85×TMP_score + 0.05×MemVol
```

### Worked Example

| Input | Value | Contribution |
|---|---|---|
| UF rate | 13.2 ml/min → norm 1.015 | 0.95 × 1.015 = **0.964** |
| Pv | 143.8 → TMP = 160.2 → norm 0.534 | 0.85 × 0.534 = **0.454** |
| MemVol | 1.0 (norm) | 0.05 × 1.0 = **0.050** |
| **Pre-IDH risk score** | | **1.47** |

Post-recovery (UF = 6 ml/min, TMP = 138 mmHg) → risk score = **0.88**

---

## 8. Synthetic Patient — James R. Mitchell

Single patient used for the timeseries dataset.

| Attribute | Value |
|---|---|
| ID | PID-HHD-0001 |
| Age / Sex | 63 yr, Male |
| Height / Dry weight | 175 cm / 82 kg |
| BMI | 26.8 |
| ESRD cause | Diabetic nephropathy (T2DM) |
| Access | AVF, left forearm |
| Dialyzer | F160NR (1.6 m², high-flux polysulfone) |
| Schedule | M-W-F, 240 min |
| Hb / Hct | 10.2 g/dL / 31% |
| Na / K / Ca / Alb / CRP | 137 / 4.8 / 8.8 / 3.5 / 6.5 |
| Dialysate Rx | dK 2.0, dCa 2.5, T2 36.0°C |
| IDWG | Mon 2.5–3.2 kg / Wed–Fri 1.8–2.5 kg |

### Timeseries Dataset Files

| File | Rows | Description |
|---|---|---|
| `patient_profile.csv` | 1 | Static profile |
| `session_summary.csv` | 100 | Per-session metadata (Jan–Aug 2025) |
| `session_timeseries.csv` | 24,000 | 240 min × 100 sessions, all parameters per minute |

### Pre-IDH Signal Validation (v2)

| Signal | Pre-IDH | Non-IDH | Delta |
|---|---|---|---|
| UF rate (ml/min) | 14.84 | 11.62 | +27.7% |
| OTA risk score | 1.577 | 1.332 | +18.4% |
| Hct slope (%/min) | 0.028 | 0.018 | +52.6% |
| TMP (mmHg) | 156.2 | 152.9 | +2.2% |

---

## 9. 500-Patient Prescription Dataset

### Files

| File | Shape | Description |
|---|---|---|
| `patient_profiles_500.csv` | 500 × 30 | Synthetic patient profiles (X inputs) |
| `patients_with_prescriptions.csv` | 500 × 49 | Profiles + generated prescriptions (X + Y) — validated ✅ |
| `prescriptions_500.csv` | 500 × 17 | Prescription outputs only (Y) |

### Patient Profile Columns — 30 cols (X inputs)

**Per-patient:** `patient_id, age, sex, height_cm, Bwt, dry_weight_kg, BMI, Hb, Hct, Na, K, Ca, Alb, CRP, PreBP, IDWG, DM, HF, Access, had_arrhythmia, bleeding_risk`

**Per-session:** `Dz, dK, dCa, pBUN, prev_ktv, prev_urr, had_IDH`

**Session config:** `session_min, sessions_per_week`

### Prescription Output Columns — 19 cols (Y outputs)

`IDWG_kg, bsa_m2, Qb_mlmin, Qd_mlmin, UF_target_L, UF_rate_mlmin, UF_rate_mlkgh, T2_C, dK_mEqL, dCa_mEqL, heparin_free, heparin_bolus_IU, heparin_infusion_IUhr, heparin_stop_min, dialyzer, dialyzer_surface_m2, uf_early_warning, uf_exceeds_kdoqi, warnings`

### Population Distributions (research-calibrated)

| Parameter | Value | Source |
|---|---|---|
| Sex | 61% M / 39% F | USRDS 2023 |
| Age | mean 63.1 ± 13.6 | USRDS 2023 |
| BMI | mean 28.5 | DOPPS |
| Access | 68% AVF / 21% AVG / 11% catheter | DOPPS US |
| Hb | 10.4 ± 1.1 g/dL | Lee H CJASN 2021 |
| Albumin | 3.56 ± 0.44 g/dL | PMC8714045 |
| pBUN | 59.8 ± 13.0 mg/dL | Lee SW 2022 |
| IDWG | 2.91 ± 1.18 kg | Al Maimani 2021 |
| DM | 37.4% | USRDS |
| HF | 23.6% | DOPPS |

### Prescription Output Distribution (across 500 patients)

| Metric | Value |
|---|---|
| Qb range | 300–425 ml/min, mean 349 |
| T2 = 35.5°C (cooled) | 147 / 500 |
| dCa = 3.0 (raised) | 191 / 500 |
| Heparin-free | 43 / 500 |
| UF early warning (10–13 ml/kg/h) | 117 / 500 |
| UF hard limit (> 13 ml/kg/h) | 83 / 500 |
| BSA mean | 1.94 m² |
| Dialyzer tiers | F130NR: 1 / F160NR: 41 / F180NR: 146 / F200NR: 312 |

### Validation Status ✅

All 17 logic checks passed across 500 rows. One non-issue noted: the input `IDWG` column (RNG float, 2 decimal) differs from the computed `IDWG_kg` (Bwt − dry_weight) in 405/500 rows by rounding — the prescription engine correctly uses `IDWG_kg`.

---

## 10. Worked Example — PID-0001

**Profile:** Female, 41, 158.6 cm, Bwt 93.0 kg, dry 89.0 kg, BMI 35.4, AVF, Hb 11.6, K 4.8, Ca 8.8, Alb 3.5, Kt/V 1.496, URR 78%, DM Yes, HF No, IDH No, arrhythmia No, bleed No, session 240 min

| Parameter | Result | Key logic |
|---|---|---|
| IDWG | 4.0 kg | 93.0 − 89.0 |
| Qb | 350 ml/min | AVF start; Kt/V ≥ 1.2 → no boost; HF No; Hb OK |
| Qd | 500 ml/min | round(350×1.5/50)×50; clamp 500–800 |
| UF target | 4.0 L | = IDWG |
| UF rate | 11.24 ml/kg/h ⚡ | (4000/240)×60/89 → 10–13 early warning zone |
| T2 | 36.5°C | DM but Alb = 3.5 (not < 3.5); no IDH → standard |
| dK | 2.0 mEq/L | 7 − 4.8 = 2.2 → round → 2.0; no overrides |
| dCa | 2.5 mEq/L | Ca = 8.8 normal; no IDH → default |
| Heparin bolus | 2,200 IU | 25×89=2,225 → round to 100 |
| Heparin infusion | 1,500 IU/hr | standard |
| Heparin stop | min 195 | 240 − 45 |
| Dialyzer | F200NR 2.0 m² | BSA = 1.98 ≥ 1.9 → tier 3; Kt/V ≥ 1.1 → no upgrade |

---

## 11. Python Files

### `hd_prescription.py` — Prescription engine v4

Takes a patient profile, outputs a full HD prescription. All 9 parameters, all decision rules from Section 6.

```bash
python3 hd_prescription.py                    # three built-in examples
python3 hd_prescription.py input.csv out.csv  # batch mode
```

**Key classes:** `PatientProfile` (14+ input fields incl. optional `core_temp_C`), `HDPrescription` (19 output fields + reasoning + warnings), `generate_prescription(p)`, `batch_from_csv(in, out)`

### `generate_hhd_data.py` — Synthetic timeseries generator (v2, OTA causal model)

```bash
python3 generate_hhd_data.py
```

Outputs: `patient_profile.csv`, `session_summary.csv`, `session_timeseries.csv`

Key features: Ornstein-Uhlenbeck noise, TMP = 1.45×Pv − (Pu+Pd)/2, pre-IDH build-up window (50 min), IDH cascade, Monday effect, `bp_measured` column, seed = 42.

---

## 12. Output Files

| File | Description |
|---|---|
| `patient_profiles_500.csv` | 500 synthetic patients, 30 cols, research-calibrated |
| `patients_with_prescriptions.csv` | 500 × 49 (profiles + prescriptions) — validated ✅ |
| `prescriptions_500.csv` | 500 × 17 prescription outputs only |
| `hd_prescription.py` | Prescription engine v4 |
| `generate_hhd_data.py` | Timeseries generator v2 |
| `patient_profile.csv` | James R. Mitchell static profile |
| `session_summary.csv` | 100-session metadata |
| `session_timeseries.csv` | 24,000-row per-minute timeseries |
| `HD_Prescription_Logic.html` | Full scrolling website — 9 parameters, SVG decision trees, plain-language summaries, worked examples, 12 references |
| `HD_Prescription_Logic.pptx` | 12-slide academic deck (white, Calibri) |
| `calculation.drawio` | draw.io XML — 5 decision trees (T2, dK, dCa, Heparin, Dialyzer) |
| `cohort_report.html` | 4-page HTML cohort analysis with Chart.js charts + 15 citations |
| `HHD_Synthetic_Data_Reference.html` | 4-page clinical reference (Patient, Parameters, Adverse Events, OTA Model) |
| `HemoAgent_LLM_PRD.docx` | Product requirements document |

---

## 13. Key Clinical References

| Source | Key finding used |
|---|---|
| KDOQI 2015 (NKF) | spKt/V ≥ 1.2; UF > 13 ml/kg/h mortality risk; Qb range; high-flux preferred |
| Flythe et al. Kidney Int 2011 | UF > 13 ml/kg/h → mortality. Established hard threshold |
| Flythe et al. CJASN 2023 (n=337,863) | Two-threshold: HR 1.22 at 10–13; HR 1.31 above 13 ml/kg/h |
| QEHB NHS HD Guidelines v3 | Target Qb ≥ 350 ml/min; Qd = 1.5× Qb; cardiac disease → lower Qb |
| Tan et al. Semin Dial 2025 (26 RCTs) | Cool dialysate OR = 0.35 for IDH. 34.5–35.0°C most effective |
| NCT02628366 TEMP RCT | Personalised T2 = core_temp − 0.5°C; min 35.5°C |
| Pun & Middleton JASN 2017 (DOPPS n=55,183) | dK 2 vs 3: no mortality difference. Gradient is the risk |
| KDIGO 2017 CKD-MBD §4.1 | dCa 2.5–3.0 mEq/L. Hypocalcaemia threshold: serum Ca < 8.5 mg/dL |
| Korean registry 2019 | dCa ≥ 3.5 → 2.2× all-cause mortality |
| PMC4088960 (Renal Fellow Network) | Heparin: 25 IU/kg bolus; stop 30–60 min before end |
| Sci Reports 2021 (n=234,638) | XL dialyzer (≥ 2.0 m²) → HR 0.75 vs medium. Basis for 4-tier |
| Mosteller RD. NEJM 1987 | BSA = sqrt(height_cm × weight_kg / 3600) |
| Al Maimani et al. OJNEPH 2021 | Mean IDWG 2.9 ± 1.7 kg in HD population |
| Lee H et al. CJASN 2021 | IDH study n=261,647 sessions. GRU-RNN AUC 0.94 |
| Exorenal PA15 patent | OTA definition, UF profiling, TMP = 1.45×Pv − (Pu+Pd)/2 |

---

## 14. Important Distinctions

1. **TMP is calculated, never directly sensed.** Exorenal formula: `TMP = 1.45×Pv − (Pu+Pd)/2`. Standard clinical formula omits the 1.45 multiplier.

2. **Qb and Qd are targets.** Pa and Pv are what sensors measure as a result of running at those targets.

3. **BP is not per-minute.** Measured every 15–30 min. Use `bp_measured` column (1 = actual, 0 = interpolated).

4. **Conductivity alarm → bypass, not full stop.** Machine diverts dialysate but keeps blood pump running. Air/blood leak = full stop.

5. **Venous pressure alarm is dynamic.** Set ±25–40 mmHg from the stabilised starting Pv. Not a fixed number — this is why VND can be missed if Pv drifts upward first.

6. **Kt/V and URR are outcomes, not prescriptions.** Calculated from pre/post BUN after the session. Feed back to the next session's Qb and dialyzer decision.

7. **LLMs never make autonomous safety decisions.** Core architectural constraint.

8. **dCa threshold is 8.5 mg/dL, not 8.4.** KDIGO 2017. An earlier version of the prescription engine incorrectly used 8.4 — corrected in v4.

9. **AVF and AVG start at the same Qb (350 ml/min).** QEHB NHS makes no distinction. Earlier versions of the engine differentiated them — removed in v4.

10. **Catheter Qb = 300 is a starting point, not a hard cap.** The real ceiling is set by arterial line pressure (Pa) during the session.

---

## 15. Open / Pending

- [ ] Regenerate session timeseries data reflecting prescription engine v4 corrections
- [ ] Add `core_temp_C` column to `patient_profiles_500.csv` to enable personalised T2
- [ ] Update `prescriptions_500.csv` — currently missing `bsa_m2` and `uf_early_warning` columns present in `patients_with_prescriptions.csv`
- [ ] Decision trees for IDWG, Qb, Qd, UF not yet in `calculation.drawio` (only T2, dK, dCa, Heparin, Dialyzer)

---

*Last updated: 2026-07-23. HemoAgent project — Tasnim, UVM CS, advisor Prof. Byung Suk Lee, industry partner Exorenal.*