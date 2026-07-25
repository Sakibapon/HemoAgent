"""
HD Prescription Generator  v4  —  Evidence-corrected
======================================================
Mimics clinician decision-making: patient profile → HD prescription.

WHAT CHANGED IN v4 vs v3:
  Qb  — AVG no longer penalised (same as AVF); catheter is a starting point not a cap;
         cardiac/HF and severe anaemia (Hb<8) cap Qb at 300; Pa-guided note added
  Qd  — documented as a guideline default (not a physiological rule); floor stays 500
  UF  — two warning tiers (10 ml/kg/h early warning; 13 ml/kg/h hard limit); HF cap 10
  T2  — fixed 35.5 replaced by "core_temp − 0.5°C, min 35.0"; fallback 36.5
  dK  — floor 2.0 for arrhythmia is correct; added note that DOPPS shows no mortality
          difference between dK 2 vs 3; hypoK floor elevated to avoid <3.5
  dCa — threshold corrected to 8.5 (KDIGO); IDH→3.0 labelled as heuristic;
          hypercalcaemia guard raised to >10.0 (serum Ca above 10.2 is the CMS QIP flag)
  Hep — infusion 1500 IU/hr (was 1200; literature range 1000-2000); stop window 30-60 min
  Dz  — BSA-based selection (Mosteller); 4 tiers S/M/L/XL; Kt/V<1.1 upgrades one tier

CLINICAL REFERENCES:
  [1] KDOQI 2015 — spKt/V ≥1.2 target; min Qb 200; UF>13 ml/kg/h mortality
  [2] Flythe et al. Kidney Int 2011 — UF rate and cardiovascular mortality
  [3] Flythe et al. CJASN 2023 (n=337,863) — early warning at 10 ml/kg/h
  [4] QEHB NHS Chronic HD Guidelines (v3) — Qb>350 for all; cardiac → lower Qb
  [5] Mora-Bravo et al. BMC Nephrol 2008 — DALP-guided Qb; catheter can reach >400
  [6] Tan et al. Semin Dial 2025 (26 RCTs, OR 0.35) — cool dialysate reduces IDH ~70%
  [7] NCT02628366 TEMP RCT — personalized T2 = core_temp − 0.5°C, min 35.5°C
  [8] Renal Fellow Network 2008 — Rule of 7 for dK
  [9] Pun & Middleton JASN 2017 (DOPPS, n=55,183) — dK 2 vs 3 no mortality difference
  [10] PMC8767120 (n=1,117) — hypokalemia (K≤4.0) risk equal to hyperkalemia
  [11] KDIGO 2017 CKD-MBD §4.1 — dCa 2.5-3.0 mEq/L; individualise to patient status
  [12] PMC7645386 — dCa history; 2.5 standard; >3.5 associated with higher mortality
  [13] PMC4088960 (Renal Fellow Network 2012) — heparin: 25 IU/kg + 1000 IU/hr
  [14] DrOracle synthesis — 25-30 IU/kg + 1500-2000 IU/hr; stop 30-60 min before end
  [15] Sci Reports 2021 (n=234,638) — larger dialyzer surface → lower mortality HR 0.75
  [16] Mosteller RD. N Engl J Med 1987 — BSA = sqrt(H_cm × W_kg / 3600)
"""

import math
from dataclasses import dataclass, field
from typing import Literal, Optional


# ══════════════════════════════════════════════════════════════════════════════
# INPUT — PATIENT PROFILE
# ══════════════════════════════════════════════════════════════════════════════
@dataclass
class PatientProfile:
    """
    All per-patient and per-session inputs.
    Column names match the Exorenal template exactly.
    """
    patient_id: str = "PID-001"

    # Anthropometrics
    weight_kg: float = 84.5        # Bwt — today's pre-dialysis weight (kg)
    dry_weight_kg: float = 82.0    # target dry weight (kg)
    height_cm: float = 175.0       # needed for BSA (dialyzer selection)

    # Vascular access
    access: Literal["AVF", "AVG", "catheter"] = "AVF"

    # Labs (monthly)
    serum_K: float = 5.2           # K   mEq/L → dK (Rule of 7)
    serum_Ca: float = 8.8          # Ca  mg/dL → dCa
    serum_albumin: float = 3.5     # Alb g/dL  → IDH risk, T2 decision
    Hb: float = 10.2               # Hb  g/dL  → Qb safety cap if severe anaemia

    # Previous session adequacy (feedback to adjust this prescription)
    prev_ktv: float = 1.15         # spKt/V last session; target ≥1.2  [KDOQI]
    prev_urr: float = 63.0         # URR last session (%); target ≥65%

    # Session history flags
    had_IDH: bool = False           # IDH in last session → cool T2
    had_arrhythmia: bool = False    # arrhythmia history → floor dK at 2.0

    # Comorbidities
    DM: bool = True
    HF: bool = False                # heart failure → cap Qb; tighter UF warning
    bleeding_risk: bool = False     # recent surgery, GI bleed → heparin-free

    # Optional — patient's core (body) temperature before session
    # If unknown leave as None; code will use 37.0°C as fallback for T2 calc
    core_temp_C: Optional[float] = None

    # Session config
    session_min: int = 240
    sessions_per_week: int = 3


# ══════════════════════════════════════════════════════════════════════════════
# OUTPUT — PRESCRIPTION
# ══════════════════════════════════════════════════════════════════════════════
@dataclass
class HDPrescription:
    """All values the clinician enters into the machine."""
    Qb_mlmin: int = 0
    Qd_mlmin: int = 0
    UF_target_L: float = 0.0
    UF_rate_mlmin: float = 0.0
    UF_rate_mlkgh: float = 0.0
    T2_C: float = 0.0
    dK_mEqL: float = 0.0
    dCa_mEqL: float = 0.0
    heparin_free: bool = False
    heparin_bolus_IU: int = 0
    heparin_infusion_IUhr: int = 0
    heparin_stop_min: int = 0
    dialyzer: str = ""
    dialyzer_surface_m2: float = 0.0
    bsa_m2: float = 0.0
    IDWG_kg: float = 0.0
    warnings: list = field(default_factory=list)
    reasoning: dict = field(default_factory=dict)


# ══════════════════════════════════════════════════════════════════════════════
# PRESCRIPTION ENGINE  v4
# ══════════════════════════════════════════════════════════════════════════════
def generate_prescription(p: PatientProfile) -> HDPrescription:
    rx = HDPrescription()
    rx.reasoning = {}
    rx.warnings  = []

    # ── IDWG ─────────────────────────────────────────────────────────────────
    # Formula: IDWG = weight_today − dry_weight
    # No branching except negative guard.
    rx.IDWG_kg = round(p.weight_kg - p.dry_weight_kg, 2)
    if rx.IDWG_kg < 0:
        rx.IDWG_kg = 0.0
        rx.warnings.append("Weight below dry weight — dehydration or measurement error.")
    rx.reasoning["IDWG"] = f"{p.weight_kg} − {p.dry_weight_kg} = {rx.IDWG_kg} kg"

    # ── Qb: Blood flow rate ───────────────────────────────────────────────────
    # Tree (v4):
    #
    # STEP 1 — access-based starting point
    #   catheter  → 300  (starting point; Pa guides actual max — NOT a fixed cap)
    #   AVF / AVG → 350  (target ≥350; QEHB NHS: 400-450 in good access)
    #
    # STEP 2 — adequacy adjustments (if access is NOT catheter, and not already capped)
    #   prev_ktv < 1.2  → +50 (under-dialysed; boost clearance)
    #   prev_urr < 65%  → +25 (additional adequacy signal)
    #
    # STEP 3 — patient-factor safety caps (OVERRIDE)
    #   HF == True        → cap at 300  [QEHB NHS; cardiac preload/output concern]
    #   Hb < 8.0 g/dL    → cap at 300  [severe anaemia; cardiac O₂ reserve limited]
    #
    # STEP 4 — absolute max by access
    #   catheter          → Pa-guided; starting 300; machine alarms if Pa < -250
    #   AVF / AVG         → 450 absolute max (recirculation risk above this)
    #
    # NOTE: Qb is ultimately titrated upward or downward by the clinician during
    # the session using Pa (target Pa > -200 mmHg). [DALP study, BMC Nephrol 2008]

    if p.access == "catheter":
        Qb = 300    # starting point; Pa governs actual ceiling
        rx.reasoning["Qb"] = "Catheter: start at 300 ml/min. Clinician titrates upward using Pa > -200 mmHg. [DALP study, BMC Nephrol 2008]"
    else:
        Qb = 350    # AVF and AVG treated identically per QEHB NHS guideline v3
        rx.reasoning["Qb"] = f"{p.access}: starting at 350 ml/min. Target ≥350; 400-450 possible in good access. [QEHB NHS]"

    # Adequacy boosts (only for non-catheter)
    if p.access != "catheter":
        if p.prev_ktv < 1.2:
            Qb = min(Qb + 50, 450)
            rx.reasoning["Qb"] += f" +50 (prev Kt/V={p.prev_ktv} < 1.2 target). [KDOQI 2015]"
        if p.prev_urr < 65:
            Qb = min(Qb + 25, 450)
            rx.reasoning["Qb"] += f" +25 (prev URR={p.prev_urr}% < 65% target). [KDOQI 2015]"

    # Patient-factor safety caps (override boost)
    if p.HF:
        if Qb > 300:
            Qb = 300
            rx.reasoning["Qb"] += " → capped at 300: HF (cardiac preload & output concern). [QEHB NHS; KDOQI]"
            rx.warnings.append("HF: Qb capped at 300 ml/min. Monitor BP and cardiac response closely.")

    if p.Hb < 8.0:
        if Qb > 300:
            Qb = 300
            rx.reasoning["Qb"] += f" → capped at 300: severe anaemia Hb={p.Hb} g/dL (limited cardiac O₂ reserve)."
            rx.warnings.append(f"Severe anaemia (Hb {p.Hb} g/dL): Qb capped at 300. Consider EPO/transfusion.")

    rx.Qb_mlmin = Qb

    # ── Qd: Dialysate flow rate ───────────────────────────────────────────────
    # v4 note: Qd = 1.5× Qb is a widely-used guideline DEFAULT, not a
    # physiological necessity. Evidence (CKJ 2024) shows Qd 300 ml/min
    # maintains the same Kt/V as 500 ml/min. However, 500 ml/min remains
    # the standard minimum for standard 3×/week 4-hour sessions.
    # Practical upper limit where gains become minimal: Qd ≈ 2× Qb. [AJKD 2005]
    Qd = min(round(rx.Qb_mlmin * 1.5 / 50) * 50, 800)
    Qd = max(Qd, 500)
    rx.Qd_mlmin = Qd
    rx.reasoning["Qd"] = (
        f"Guideline default: 1.5 × Qb = {Qd} ml/min (clamped 500–800). "
        f"Note: Qd/Qb ratio is a practical default; Qd 300 ml/min maintains same "
        f"Kt/V in short-term studies but 500 remains standard minimum. [QEHB NHS; CKJ 2024]"
    )

    # ── UF target and rate ────────────────────────────────────────────────────
    # v4 adds a TWO-TIER warning system:
    #   Early warning: > 10 ml/kg/h (risk begins; HR 1.22 vs <10)
    #   Hard limit:    > 13 ml/kg/h (KDOQI mortality threshold; HR 1.31)
    # HF patients: target < 10 ml/kg/h (more conservative)
    # [Flythe Kidney Int 2011; Flythe CJASN 2023 n=337,863]
    rx.UF_target_L  = rx.IDWG_kg
    uf_mlmin        = (rx.UF_target_L * 1000) / p.session_min if p.session_min > 0 else 0
    uf_mlkgh        = (uf_mlmin * 60) / p.dry_weight_kg
    rx.UF_rate_mlmin = round(uf_mlmin, 2)
    rx.UF_rate_mlkgh = round(uf_mlkgh, 2)

    if uf_mlkgh > 13.0:
        rx.warnings.append(
            f"⚠ UF rate {uf_mlkgh:.1f} ml/kg/h EXCEEDS KDOQI hard limit of 13 ml/kg/h. "
            f"Extend session, reduce target, or schedule extra session. [Flythe 2011]"
        )
    elif uf_mlkgh > 10.0:
        rx.warnings.append(
            f"⚡ UF rate {uf_mlkgh:.1f} ml/kg/h exceeds early-warning threshold of 10 ml/kg/h "
            f"(HR 1.22 vs <10). Consider slower UF profile. [Flythe CJASN 2023]"
        )

    if p.HF and uf_mlkgh > 10.0:
        rx.warnings.append(
            "HF patient: target UF rate < 10 ml/kg/h. Monitor BP every 15 min. [KDOQI; Dialysafe trial]"
        )

    rx.reasoning["UF"] = (
        f"UF target = IDWG = {rx.UF_target_L} L → "
        f"{rx.UF_rate_mlmin} ml/min → {rx.UF_rate_mlkgh} ml/kg/h. "
        f"Thresholds: early warning >10, hard limit >13 ml/kg/h. [KDOQI §4.2; Flythe 2011/2023]"
    )

    # ── T2: Dialysate temperature ─────────────────────────────────────────────
    # v4: Best practice is PERSONALISED temperature = core_temp − 0.5°C (min 35.0°C).
    # [NCT02628366 TEMP RCT; Tan et al. Semin Dial 2025 meta-analysis of 26 RCTs]
    # If core_temp is unknown, fall back to fixed values:
    #   IDH history or DM+low albumin → 35.5°C (fixed)
    #   Otherwise → 36.5°C (standard)
    # Note: 34.5–35.0°C is most effective per subgroup analysis [Tan 2025]
    #       but 35.5°C is the minimum on most machines (Fresenius 5008).

    core = p.core_temp_C if p.core_temp_C is not None else None
    high_idh_risk = p.had_IDH or (p.DM and p.serum_albumin < 3.5)

    if high_idh_risk:
        if core is not None:
            T2 = max(35.0, round(core - 0.5, 1))
            rx.reasoning["T2"] = (
                f"IDH risk: personalized T2 = core_temp {core}°C − 0.5 = {T2}°C "
                f"(min 35.0). Cool dialysate reduces IDH by ~70% (OR 0.35). "
                f"[Tan 2025 meta-analysis; NCT02628366 TEMP RCT]"
            )
        else:
            T2 = 35.5
            rx.reasoning["T2"] = (
                "IDH risk but core_temp unknown: using fixed 35.5°C. "
                "Best practice: set to core_temp − 0.5°C. [TEMP RCT; EBPG §3.4]"
            )
    else:
        T2 = 36.5
        rx.reasoning["T2"] = (
            "No IDH risk factors → standard 36.5°C. "
            "Reduce to 35.5°C (or core_temp − 0.5°C) at first IDH event. [EBPG §3.4]"
        )

    rx.T2_C = T2

    # ── dK: Dialysate potassium ───────────────────────────────────────────────
    # v4 keeps Rule of 7 as the base (validated, widely used).
    # Key evidence update:
    #   - DOPPS (n=55,183): dK 2 vs 3 mEq/L shows NO clear mortality difference
    #     — the danger is the GRADIENT, not the absolute value. [Pun & Middleton JASN 2017]
    #   - dK < 2.0 mEq/L associated with higher arrhythmia/SCA risk [PMC8767120]
    #   - Hypokalemia (serum K ≤ 4.0) has same mortality risk as hyperkalemia [PMC8767120]
    #
    # Tree:
    #   raw_dK = 7.0 − serum_K
    #   dK     = clamp(raw_dK, 1.0, 4.0), rounded to nearest 0.5
    #
    #   OVERRIDE 1: had_arrhythmia AND dK < 2.0  → dK = 2.0  (floor; SCA risk)
    #   OVERRIDE 2: serum_K < 3.5 (hypokalemia)  → dK = min(dK + 1.0, 4.0)
    #   OVERRIDE 3: serum_K > 5.5 (severe hyperK) → dK may go as low as 1.0
    #               but only if no arrhythmia history (OVERRIDE 1 takes precedence)

    raw_dK = 7.0 - p.serum_K
    dK     = round(max(1.0, min(4.0, raw_dK)) * 2) / 2

    if p.serum_K < 3.5:
        # Hypokalemia — prevent further K drop
        dK = min(dK + 1.0, 4.0)
        rx.reasoning["dK"] = (
            f"Serum K={p.serum_K} (hypokalemia ≤3.5). "
            f"Rule of 7: {raw_dK:.1f} → boosted by +1.0 to {dK} to prevent further drop. "
            f"[PMC8767120 — hypoK risk = hyperK risk]"
        )
    elif p.had_arrhythmia and dK < 2.0:
        dK = 2.0
        rx.reasoning["dK"] = (
            f"Rule of 7: 7−{p.serum_K}={raw_dK:.1f} → floored to 2.0 "
            f"(arrhythmia history; dK<2.0 associated with SCA). [PMC8767120; Pun JASN 2017]"
        )
    else:
        rx.reasoning["dK"] = (
            f"Rule of 7: 7 − {p.serum_K} = {raw_dK:.1f} → dK = {dK} mEq/L. "
            f"DOPPS (n=55,183): dK 2 vs 3 mEq/L — no clear mortality difference; "
            f"danger is steep K gradient, not absolute value. [Pun & Middleton JASN 2017]"
        )

    rx.dK_mEqL = dK

    # ── dCa: Dialysate calcium ────────────────────────────────────────────────
    # v4 corrections:
    #   - KDIGO threshold for hypocalcaemia = serum Ca < 8.5 mg/dL  (was 8.4 in v3)
    #   - Hypercalcaemia guard raised to > 10.0 mg/dL
    #     (CMS QIP flags serum Ca > 10.2; dCa ≥ 3.5 mEq/L associated with 2.2× mortality)
    #   - IDH→dCa 3.0 retained but labelled as clinical HEURISTIC (not guideline)
    #   - KDIGO recommends range 2.5–3.0 mEq/L; individualise to CKD-MBD status [KDIGO 2017]
    #   - dCa 3.5 mEq/L is explicitly avoided (vascular calcification / mortality risk)
    #
    # Tree:
    #   IF serum_Ca < 8.5  (KDIGO hypocalcaemia)  → dCa = 3.0
    #   ELIF serum_Ca > 10.0 (hypercalcaemia)      → dCa = 2.5 (do NOT increase Ca)
    #   ELIF had_IDH                                → dCa = 3.0 (heuristic; cardiac stability)
    #   ELSE                                        → dCa = 2.5 (KDOQI/KDIGO default)

    if p.serum_Ca < 8.5:
        dCa = 3.0
        rx.reasoning["dCa"] = (
            f"Serum Ca={p.serum_Ca} mg/dL (hypocalcaemia <8.5 KDIGO threshold) → "
            f"dCa=3.0 to deliver Ca via diffusion gradient. [KDIGO 2017 §4.1]"
        )
    elif p.serum_Ca > 10.0:
        dCa = 2.5
        rx.reasoning["dCa"] = (
            f"Serum Ca={p.serum_Ca} mg/dL (hypercalcaemia >10.0) → "
            f"dCa=2.5. Do NOT increase Ca; dCa≥3.5 associated with 2.2× mortality. "
            f"[KDIGO 2017; PMC7645386]"
        )
    elif p.had_IDH:
        dCa = 3.0
        rx.reasoning["dCa"] = (
            "IDH history → dCa=3.0 (clinical heuristic: higher dCa improves myocardial "
            "contractility and hemodynamic stability during UF). "
            "Not a formal guideline — clinician judgment. [KDIGO 2017 2C evidence]"
        )
    else:
        dCa = 2.5
        rx.reasoning["dCa"] = (
            f"Serum Ca={p.serum_Ca} mg/dL (normal) → default dCa=2.5 mEq/L. "
            f"KDIGO recommends 2.5–3.0 mEq/L; 2.5 neutral Ca balance. [KDIGO 2017 §4.1]"
        )

    rx.dCa_mEqL = dCa

    # ── Heparin ───────────────────────────────────────────────────────────────
    # v4 corrections:
    #   - Bolus: 25 IU/kg (was 28; literature consensus 25-30 IU/kg) [PMC4088960; DrOracle]
    #   - Infusion: 1500 IU/hr (was 1200; literature range 1000-2000; commonly 1500) [14]
    #   - Stop window: session_min − 30 to session_min − 60 (expressed as target min-45,
    #     which is midpoint of 30-60 min window) [PMC4088960; ERA-EDTA]
    #   - Heparin-free: saline flush every 15-30 min + maintain high Qb [KDOQI]

    if p.bleeding_risk:
        rx.heparin_free          = True
        rx.heparin_bolus_IU      = 0
        rx.heparin_infusion_IUhr = 0
        rx.heparin_stop_min      = 0
        rx.reasoning["heparin"]  = (
            "Bleeding risk → heparin-free protocol. "
            "Flush circuit with saline q15-30 min; maintain high Qb to reduce stasis. "
            "[KDOQI; ERA-EDTA]"
        )
    else:
        # 25 IU/kg, rounded to nearest 100, clamped 1000-5000 IU
        bolus = round(25 * p.dry_weight_kg / 100) * 100
        bolus = max(1000, min(bolus, 5000))
        rx.heparin_bolus_IU      = bolus
        rx.heparin_infusion_IUhr = 1500          # midpoint of 1000-2000 IU/hr range
        rx.heparin_stop_min      = p.session_min - 45  # midpoint of 30-60 min window
        rx.reasoning["heparin"]  = (
            f"Bolus: 25 IU/kg × {p.dry_weight_kg} kg = {bolus} IU (rounded to 100). "
            f"Infusion: 1500 IU/hr (range 1000-2000 IU/hr; centre-specific). "
            f"Stop at min {rx.heparin_stop_min} (45 min before end; range 30-60 min). "
            f"[PMC4088960; DrOracle; ERA-EDTA]"
        )

    # ── Dialyzer ──────────────────────────────────────────────────────────────
    # v4: BSA-based selection using Mosteller formula (v3 used weight alone).
    # Evidence: larger surface → lower mortality (HR 0.75 XL vs M). [Sci Rep 2021 n=234,638]
    # Tiers:
    #   BSA < 1.5 m²  → Dx 1.3 m²  (small patient)
    #   BSA 1.5–1.7   → F160NR 1.6 m²  (standard)
    #   BSA 1.7–1.9   → F180NR 1.8 m²  (medium-large)
    #   BSA ≥ 1.9     → Dx 2.0+ m²  (large patient)
    #
    # Adequacy upgrade: if prev_ktv < 1.1 → step up one tier
    # All dialyzers: high-flux polysulfone [KDOQI 2015 §2]

    bsa = math.sqrt(p.height_cm * p.dry_weight_kg / 3600)  # Mosteller [16]
    rx.bsa_m2 = round(bsa, 2)

    # Base tier from BSA
    if bsa < 1.5:
        base_tier = 0   # 1.3 m²
    elif bsa < 1.7:
        base_tier = 1   # 1.6 m²
    elif bsa < 1.9:
        base_tier = 2   # 1.8 m²
    else:
        base_tier = 3   # 2.0+ m²

    # Adequacy upgrade
    upgraded = False
    if p.prev_ktv < 1.1:
        base_tier = min(base_tier + 1, 3)
        upgraded = True

    tier_map = {
        0: ("F130NR", 1.3),
        1: ("F160NR", 1.6),
        2: ("F180NR", 1.8),
        3: ("F200NR", 2.0),
    }
    dialyzer, surface = tier_map[base_tier]
    rx.dialyzer            = dialyzer
    rx.dialyzer_surface_m2 = surface

    upgrade_note = f" Upgraded one tier (prev Kt/V={p.prev_ktv} < 1.1)." if upgraded else ""
    rx.reasoning["dialyzer"] = (
        f"BSA (Mosteller) = sqrt({p.height_cm}×{p.dry_weight_kg}/3600) = {bsa:.2f} m². "
        f"Tier → {dialyzer} ({surface} m²).{upgrade_note} "
        f"All high-flux polysulfone. Larger surface → lower mortality. "
        f"[Sci Rep 2021 n=234,638; KDOQI 2015 §2; Mosteller 1987]"
    )

    return rx


# ══════════════════════════════════════════════════════════════════════════════
# PRINT HELPER
# ══════════════════════════════════════════════════════════════════════════════
def print_prescription(p: PatientProfile, rx: HDPrescription):
    print("=" * 64)
    print(f"PRESCRIPTION v4  —  {p.patient_id}")
    print("=" * 64)
    print(f"  Access: {p.access}  |  DM:{p.DM}  HF:{p.HF}  IDH:{p.had_IDH}"
          f"  Arr:{p.had_arrhythmia}  Bleed:{p.bleeding_risk}")
    print(f"  Wt today: {p.weight_kg} kg  |  Dry wt: {p.dry_weight_kg} kg"
          f"  |  IDWG: {rx.IDWG_kg} kg")
    print(f"  Hb: {p.Hb} g/dL  |  K: {p.serum_K}  Ca: {p.serum_Ca}  Alb: {p.serum_albumin}")
    print(f"  Prev Kt/V: {p.prev_ktv}  URR: {p.prev_urr}%  |  BSA: {rx.bsa_m2} m²")
    print()
    print(f"  Qb:         {rx.Qb_mlmin} ml/min")
    print(f"  Qd:         {rx.Qd_mlmin} ml/min")
    print(f"  UF target:  {rx.UF_target_L} L  |  rate: {rx.UF_rate_mlkgh} ml/kg/h")
    print(f"  T2:         {rx.T2_C} °C")
    print(f"  dK:         {rx.dK_mEqL} mEq/L")
    print(f"  dCa:        {rx.dCa_mEqL} mEq/L")
    if rx.heparin_free:
        print(f"  Heparin:    HEPARIN-FREE (bleeding risk)")
    else:
        print(f"  Heparin:    {rx.heparin_bolus_IU} IU bolus + {rx.heparin_infusion_IUhr} IU/hr,"
              f" stop min {rx.heparin_stop_min}")
    print(f"  Dialyzer:   {rx.dialyzer} ({rx.dialyzer_surface_m2} m²)")
    if rx.warnings:
        print()
        for w in rx.warnings:
            print(f"  {w}")
    print()
    print("  REASONING:")
    for k, v in rx.reasoning.items():
        print(f"    {k.upper():10s}: {v}")
    print("=" * 64)


# ══════════════════════════════════════════════════════════════════════════════
# BATCH — CSV IN → COMBINED CSV OUT
# ══════════════════════════════════════════════════════════════════════════════
def batch_from_csv(input_csv: str, output_csv: str):
    """
    Read patient profiles from CSV (Exorenal column names).
    Output: one combined CSV — patient profile LEFT, prescription RIGHT.
    """
    import pandas as pd

    df = pd.read_csv(input_csv)
    print(f"Loaded {len(df)} patient profiles from: {input_csv}")

    rx_rows = []
    for _, row in df.iterrows():
        p = PatientProfile(
            patient_id        = str(row["patient_id"]),
            weight_kg         = float(row["Bwt"]),
            dry_weight_kg     = float(row["dry_weight_kg"]),
            height_cm         = float(row["height_cm"]),
            access            = str(row["Access"]),
            serum_K           = float(row["K"]),
            serum_Ca          = float(row["Ca"]),
            serum_albumin     = float(row["Alb"]),
            Hb                = float(row["Hb"]),
            prev_ktv          = float(row["prev_ktv"]),
            prev_urr          = float(row["prev_urr"]),
            had_IDH           = bool(row["had_IDH"]),
            had_arrhythmia    = bool(row["had_arrhythmia"]),
            DM                = bool(row["DM"]),
            HF                = bool(row["HF"]),
            bleeding_risk     = bool(row["bleeding_risk"]),
            session_min       = int(row["session_min"]),
            sessions_per_week = int(row["sessions_per_week"]),
            # core_temp not in profile CSV — will use fallback
            core_temp_C       = float(row["core_temp_C"]) if "core_temp_C" in row and not pd.isna(row.get("core_temp_C")) else None,
        )
        rx = generate_prescription(p)
        rx_rows.append({
            "IDWG_kg":               rx.IDWG_kg,
            "bsa_m2":                rx.bsa_m2,
            "Qb_mlmin":              rx.Qb_mlmin,
            "Qd_mlmin":              rx.Qd_mlmin,
            "UF_target_L":           rx.UF_target_L,
            "UF_rate_mlmin":         rx.UF_rate_mlmin,
            "UF_rate_mlkgh":         rx.UF_rate_mlkgh,
            "T2_C":                  rx.T2_C,
            "dK_mEqL":               rx.dK_mEqL,
            "dCa_mEqL":              rx.dCa_mEqL,
            "heparin_free":          rx.heparin_free,
            "heparin_bolus_IU":      rx.heparin_bolus_IU,
            "heparin_infusion_IUhr": rx.heparin_infusion_IUhr,
            "heparin_stop_min":      rx.heparin_stop_min,
            "dialyzer":              rx.dialyzer,
            "dialyzer_surface_m2":   rx.dialyzer_surface_m2,
            "uf_early_warning":      10.0 < rx.UF_rate_mlkgh <= 13.0,
            "uf_exceeds_kdoqi":      rx.UF_rate_mlkgh > 13.0,
            "warnings":              " | ".join(rx.warnings) if rx.warnings else "",
        })

    rx_df = pd.DataFrame(rx_rows)
    out   = pd.concat([df.reset_index(drop=True), rx_df.reset_index(drop=True)], axis=1)
    out.to_csv(output_csv, index=False)

    print(f"\nOutput: {out.shape[0]} rows × {out.shape[1]} cols")
    print(f"  Left  ({len(df.columns)} cols): patient profile")
    print(f"  Right ({len(rx_df.columns)} cols): prescription outputs")
    print(f"\nPrescription summary (v4):")
    print(f"  Qb range:          {rx_df.Qb_mlmin.min()}–{rx_df.Qb_mlmin.max()} ml/min  (mean {rx_df.Qb_mlmin.mean():.0f})")
    print(f"  Qd range:          {rx_df.Qd_mlmin.min()}–{rx_df.Qd_mlmin.max()} ml/min")
    print(f"  T2 = 35.5°C:       {(rx_df.T2_C==35.5).sum()} patients (IDH/risk-cooled)")
    print(f"  dK ≥ 3.0:          {(rx_df.dK_mEqL>=3.0).sum()} patients")
    print(f"  dCa = 3.0:         {(rx_df.dCa_mEqL==3.0).sum()} patients")
    print(f"  Heparin-free:      {rx_df.heparin_free.sum()} patients")
    print(f"  UF early warning:  {rx_df.uf_early_warning.sum()} patients (10-13 ml/kg/h)")
    print(f"  UF > 13 ml/kg/h:   {rx_df.uf_exceeds_kdoqi.sum()} patients")
    print(f"  BSA mean:          {rx_df.bsa_m2.mean():.2f} m²")
    print(f"  Dialyzer F130NR:   {(rx_df.dialyzer=='F130NR').sum()}")
    print(f"  Dialyzer F160NR:   {(rx_df.dialyzer=='F160NR').sum()}")
    print(f"  Dialyzer F180NR:   {(rx_df.dialyzer=='F180NR').sum()}")
    print(f"  Dialyzer F200NR:   {(rx_df.dialyzer=='F200NR').sum()}")
    print(f"\nSaved: {output_csv}")


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import sys

    if len(sys.argv) == 3:
        batch_from_csv(sys.argv[1], sys.argv[2])
    else:
        # Example 1: Standard patient (James R. Mitchell)
        p1 = PatientProfile(
            patient_id="James R. Mitchell",
            weight_kg=84.5, dry_weight_kg=82.0, height_cm=175.0,
            access="AVF", serum_K=5.2, serum_Ca=8.8, serum_albumin=3.5,
            Hb=10.2, prev_ktv=1.15, prev_urr=63.0,
            had_IDH=False, had_arrhythmia=False,
            DM=True, HF=False, bleeding_risk=False,
            core_temp_C=36.8, session_min=240,
        )
        print_prescription(p1, generate_prescription(p1))
        print()

        # Example 2: High-risk patient
        p2 = PatientProfile(
            patient_id="High-risk patient",
            weight_kg=91.0, dry_weight_kg=85.0, height_cm=168.0,
            access="catheter", serum_K=6.1, serum_Ca=7.9, serum_albumin=2.8,
            Hb=7.5, prev_ktv=1.05, prev_urr=59.0,
            had_IDH=True, had_arrhythmia=True,
            DM=True, HF=True, bleeding_risk=True,
            core_temp_C=37.1, session_min=240,
        )
        print_prescription(p2, generate_prescription(p2))
        print()

        # Example 3: Large, well-dialysed AVF patient
        p3 = PatientProfile(
            patient_id="Large well-dialysed",
            weight_kg=112.0, dry_weight_kg=108.0, height_cm=185.0,
            access="AVF", serum_K=4.5, serum_Ca=9.2, serum_albumin=4.0,
            Hb=11.5, prev_ktv=1.35, prev_urr=71.0,
            had_IDH=False, had_arrhythmia=False,
            DM=False, HF=False, bleeding_risk=False,
            core_temp_C=36.6, session_min=240,
        )
        print_prescription(p3, generate_prescription(p3))
        print()

        print("--- Batch: 500 patients ---")
        batch_from_csv(
            "PatientProfiles.csv",
            "HemoClinicianOutput.csv.csv",
        )