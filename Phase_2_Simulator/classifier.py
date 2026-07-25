"""
Emergency classifier for the HemoAgent Simulator (Phase 1).

Deterministic CODE-layer logic - the left side of the "From Detection to Action" tree.
Maps the active adverse-event flags of an anomaly onto a severity Tier and the action that
follows (stop the pump, recommend UFR reduction, or just notify). No AI is involved.

Tier 3 ("moderate drift") is not a flag; it is derived in app.py from the hypotension risk
score crossing a threshold. This module only assigns tiers to the event flags and holds the
per-tier action metadata.
"""

from enum import Enum

import config


class Tier(Enum):
    TIER1 = "TIER 1"    # catastrophic mechanical (air, blood leak)
    TIER2 = "TIER 2"    # severe physiologic (hypotension, seizure)
    TIER3 = "TIER 3"    # moderate drift (derived from risk score)
    INFO = "ADVISORY"   # every other adverse-event flag


# Per-tier action metadata used to build messages, route inboxes, and colour the UI.
TIER_META = {
    Tier.TIER1: {
        "headline": "EMERGENCY - PUMP STOPPED",
        "action": "Blood pump halted and emergency call placed to patient and clinician.",
        "stop": True, "recipients": ["Patient", "Clinician"], "color": "red",
    },
    Tier.TIER2: {
        "headline": "EMERGENCY - PUMP STOPPED",
        "action": "Blood pump halted and emergency call placed to patient and clinician.",
        "stop": True, "recipients": ["Patient", "Clinician"], "color": "red",
    },
    Tier.TIER3: {
        "headline": "MODERATE DRIFT",
        "action": "Recommend reducing the ultrafiltration rate (UFR). No pump stop.",
        "stop": False, "recipients": ["Clinician"], "color": "amber",
    },
    Tier.INFO: {
        "headline": "ADVISORY",
        "action": "Care team notified for review.",
        "stop": False, "recipients": ["Patient", "Clinician", "LLM"], "color": "accent",
    },
}


def event_tier(col: str) -> Tier:
    """Tier of a single adverse-event column."""
    if col in config.TIER1_EVENTS:
        return Tier.TIER1
    if col in config.TIER2_EVENTS:
        return Tier.TIER2
    return Tier.INFO


def worst_tier(active_cols) -> Tier:
    """Most severe tier among the active event columns (Tier 3 never comes from flags)."""
    tiers = {event_tier(c) for c in active_cols}
    for t in (Tier.TIER1, Tier.TIER2, Tier.INFO):
        if t in tiers:
            return t
    return Tier.INFO


def is_stop(tier: Tier) -> bool:
    return TIER_META[tier]["stop"]
