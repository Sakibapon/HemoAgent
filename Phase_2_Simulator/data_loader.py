"""
Data loading for the HemoAgent Session Simulator (Phase 2).

Reads a raw device file (~5 Hz, scaled-integer units) and decodes it to clinical units
at FULL resolution (every sample is kept - no per-minute aggregation). Derives UF removed
(L), UF rate (ml/min), TMP, and the hypotension risk score, all on the original
`time_min` axis. Exposes each configured raw file as a selectable session.
"""

import os

import numpy as np
import pandas as pd

import config


def _decode(path: str) -> pd.DataFrame:
    """Decode one raw file to full-resolution clinical units on the time_min axis."""
    raw = pd.read_csv(path)

    df = pd.DataFrame()
    df["time_min"] = pd.to_numeric(raw["time_min"], errors="coerce")

    for raw_col, (clean, scale) in config.RAW_COLUMN_MAP.items():
        if raw_col in raw.columns:
            df[clean] = pd.to_numeric(raw[raw_col], errors="coerce") * scale

    load_g = None
    if config.LOAD_CELL_RAW in raw.columns:
        load_g = pd.to_numeric(raw[config.LOAD_CELL_RAW], errors="coerce") \
            * config.LOAD_CELL_G_PER_COUNT

    for col in config.ADVERSE_EVENT_COLUMNS:
        df[col] = (pd.to_numeric(raw[col], errors="coerce").fillna(0).astype(int)
                   if col in raw.columns else 0)

    df = df[df["time_min"].notna()].sort_values("time_min").reset_index(drop=True)

    # UF removed (L, tare-subtracted) and UF rate (ml/min), derived from the load cell.
    if load_g is not None:
        load_g = load_g.reindex(df.index)
        df["UF_removed_L"] = (load_g - load_g.iloc[0]) / 1000.0
        # The load cell moves in coarse 10 g steps, so a short-window derivative snaps
        # between discrete levels (e.g. 10/20 ml/min). Measure the rate over a trailing
        # ~5-minute window so the 10 g quantization is negligible (grams removed over
        # the elapsed minutes -> ml/min), giving a smooth, readable trace.
        win = 1500                                      # ~5 minutes at ~5 Hz
        dg = load_g - load_g.shift(win)
        dtm = df["time_min"] - df["time_min"].shift(win)
        rate = (dg / dtm).replace([np.inf, -np.inf], np.nan).clip(lower=0.0)
        df["UF_rate_mlmin"] = rate.bfill().fillna(0.0)
    else:
        df["UF_removed_L"] = np.nan
        df["UF_rate_mlmin"] = np.nan

    # TMP (Exorenal formula) and the derived hypotension risk score.
    if {"Pv", "Pu", "Pd"}.issubset(df.columns):
        df["TMP"] = 1.45 * df["Pv"] - (df["Pu"] + df["Pd"]) / 2.0
    else:
        df["TMP"] = np.nan

    df["hypotension_risk_score"] = (
        0.95 * (df["UF_rate_mlmin"] / config.RISK_UF_NORM)
        + 0.85 * (df["TMP"] / config.RISK_TMP_NORM)
        + 0.05 * config.RISK_MEMVOL
    )

    return df


class DataStore:
    """Loads the configured raw files as full-resolution session frames."""

    def __init__(self):
        self.sessions = {}     # session_id -> full-resolution DataFrame
        self.meta = {}         # session_id -> {label, n_event_minutes, uf_total_L, duration_min}

        for entry in config.SESSION_FILES:
            path = os.path.join(config.DATA_DIR, entry["file"])
            if not os.path.exists(path):
                continue
            sid = entry["file"].split(".")[0]
            frame = _decode(path)
            self.sessions[sid] = frame

            any_event = frame[config.ADVERSE_EVENT_COLUMNS].sum(axis=1) > 0
            event_minutes = int(np.floor(frame.loc[any_event, "time_min"]).nunique())
            self.meta[sid] = {
                "label": entry["label"],
                "n_event_minutes": event_minutes,
                "uf_total_L": float(frame["UF_removed_L"].max()),
                "duration_min": float(frame["time_min"].max()),
            }

        if not self.sessions:
            raise FileNotFoundError(f"No configured session files found in {config.DATA_DIR}.")

    def session_ids(self):
        return list(self.sessions.keys())

    def label(self, sid: str) -> str:
        return self.meta[sid]["label"]


def load_datastore() -> DataStore:
    return DataStore()
