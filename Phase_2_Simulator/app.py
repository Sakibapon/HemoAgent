"""
HemoAgent Session Simulator - Phase 2 (Streamlit).

Playback + Phase-1 emergency classifier ("From Detection to Action", left side of the
tree). Replays a raw device session; on every anomaly the deterministic classifier
(classifier.py) assigns a Tier: Tier 1/2 stop the pump + place an emergency call + pause
playback, Tier 3 recommends reducing UFR, and every other flag is an advisory. Tiered
messages are routed to the Patient / Clinician / LLM inboxes. No AI yet (Phase 2).

Run:  streamlit run app.py
"""

import time

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import config
import classifier
from classifier import Tier, TIER_META
from data_loader import load_datastore
from param_config import PARAM_SPECS, PARAM_SPECS_BY_KEY, EVENT_LABELS

st.set_page_config(page_title="HemoAgent Session Simulator", layout="wide")

st.markdown(
    "<style>.block-container{padding-top:2rem;padding-bottom:3rem;}"
    "h1,h2,h3{color:#1f2933;}</style>",
    unsafe_allow_html=True,
)

PALETTE = {
    "card": "#ffffff", "border": "#e5e9f0", "text": "#1f2933", "muted": "#64748b",
    "accent": "#2563eb", "green": "#16a34a", "red": "#dc2626", "track": "#eef1f6",
    "grid": "#e2e8f0", "shadow": "0 1px 3px rgba(15,23,42,0.06)",
}

TICK_SEC = 0.25
RESOLUTIONS = {"Seconds": 1 / 60, "Minutes": 1.0, "Hours": 60.0}
DEFAULT_RES = "Seconds"
PAGES = ["Main Dashboard", "Patient Inbox", "Clinician Inbox", "LLM Inbox"]
PAGE_RECIPIENT = {"Patient Inbox": "Patient", "Clinician Inbox": "Clinician", "LLM Inbox": "LLM"}
TIER_COLOR = {"red": "#dc2626", "amber": "#d97706", "accent": "#2563eb"}


# ---------------------------------------------------------------------------
# Data (cached)
# ---------------------------------------------------------------------------
@st.cache_resource
def get_datastore():
    return load_datastore()


try:
    DS = get_datastore()
except FileNotFoundError as e:
    st.error(f"Could not load the dataset. {e}")
    st.info(f"Expected raw session files in: {config.DATA_DIR}. "
            "Set HEMO_DATA_DIR to override the location.")
    st.stop()


@st.cache_data(show_spinner=False)
def resample(sid: str, resolution: str) -> pd.DataFrame:
    """Bin the full-resolution frame (mean sensors, max events) to a resolution."""
    f = DS.sessions[sid]
    key = np.floor(f["time_min"] / RESOLUTIONS[resolution])
    agg = {c: ("max" if c in config.ADVERSE_EVENT_COLUMNS else "mean") for c in f.columns}
    return f.groupby(key).agg(agg).reset_index(drop=True).sort_values("time_min").reset_index(drop=True)


@st.cache_data(show_spinner=False)
def event_intervals(sid: str):
    """Contiguous spans where any adverse event is active: (start_min, end_min, start_idx)."""
    f = DS.sessions[sid]
    mask = (f[config.ADVERSE_EVENT_COLUMNS].sum(axis=1) > 0).to_numpy()
    t = f["time_min"].to_numpy()
    idx = np.where(mask)[0]
    if idx.size == 0:
        return []
    groups = np.split(idx, np.where(np.diff(idx) > 1)[0] + 1)
    return [(float(t[g[0]]), float(t[g[-1]]), int(g[0])) for g in groups]


@st.cache_data(show_spinner=False)
def drift_events(sid: str):
    """Tier-3 moderate-drift onsets from the PER-MINUTE risk score with hysteresis: fire
    when it rises above HI, re-arm only after it falls below LO. Excludes minutes inside a
    flagged adverse-event interval. Returns (minute, full_frame_idx, risk)."""
    f = DS.sessions[sid]
    t_full = f["time_min"].to_numpy()
    key = np.floor(f["time_min"])
    per_min = f.groupby(key)["hypotension_risk_score"].mean()
    minutes = per_min.index.to_numpy()
    risk = per_min.to_numpy()
    intervals = [(s, e) for s, e, _ in event_intervals(sid)]

    def in_event(tm):
        return any(s <= tm <= e for s, e in intervals)

    onsets, armed = [], True
    for m, v in zip(minutes, risk):
        if v >= config.MODERATE_DRIFT_RISK_HI and armed and not in_event(m):
            idx = int(np.searchsorted(t_full, m, side="left"))
            onsets.append((float(m), min(idx, len(f) - 1), float(v)))
            armed = False
        if v < config.MODERATE_DRIFT_RISK_LO:
            armed = True
    return onsets


@st.cache_data(show_spinner=False)
def status_events(sid: str):
    """Per-minute onsets where a NEW anomaly appears (the active-flag set gains a flag).
    One message/stop per genuinely new status; an unchanged status produces nothing, and a
    status merely shrinking (a flag resolving) produces nothing. Returns
    (minute, full_frame_idx, active_cols, Tier)."""
    f = DS.sessions[sid]
    cols = config.ADVERSE_EVENT_COLUMNS
    t_full = f["time_min"].to_numpy()
    key = np.floor(f["time_min"])
    grp = f.groupby(key)[cols].max()
    minutes = grp.index.to_numpy()
    mat = grp.to_numpy()

    out, prev = [], set()
    for mi, mrow in zip(minutes, mat):
        active = [cols[j] for j in range(len(cols)) if mrow[j]]
        s = set(active)
        if s and (s - prev):                       # a new flag appeared this minute
            idx = min(int(np.searchsorted(t_full, mi, side="left")), len(f) - 1)
            out.append((float(mi), idx, active, classifier.worst_tier(active)))
        prev = s
    return out


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
if "initialized" not in st.session_state:
    st.session_state.current_session = DS.session_ids()[0]
    st.session_state.cursor = 0.0
    st.session_state.running = False
    st.session_state.speed = config.DEFAULT_SPEED
    st.session_state.chart_var = PARAM_SPECS[0].key
    st.session_state.resolution = DEFAULT_RES
    st.session_state.last_stop_min = -1.0     # last Tier 1/2 onset we paused at
    st.session_state.initialized = True

SID = st.session_state.current_session
DURATION = DS.meta[SID]["duration_min"]

# Streamlit clears a widget's key when that widget is not rendered in a run (e.g. the
# resolution / variable pickers while viewing an inbox page). Reassigning them here every
# run keeps the selections alive across page switches and avoids KeyErrors on return.
for _k, _default in (("resolution", DEFAULT_RES), ("chart_var", PARAM_SPECS[0].key),
                     ("cursor", 0.0)):
    st.session_state[_k] = st.session_state.get(_k, _default)


def on_session_change():
    # Only reset when the session truly changed. The selectbox can re-fire this callback
    # when it re-instantiates on returning to the dashboard (its key is cleared while an
    # inbox page is shown); without this guard that would restart playback from 0.
    new = st.session_state.session_select
    if new != st.session_state.current_session:
        st.session_state.current_session = new
        st.session_state.cursor = 0.0
        st.session_state.running = False


def toggle_running():
    if st.session_state.cursor >= DURATION:
        st.session_state.cursor = 0.0
    st.session_state.running = not st.session_state.running


def reset_session():
    st.session_state.cursor = 0.0
    st.session_state.running = False


def nudge(delta_min: float):
    """Step the cursor by delta (minutes) and pause, for the -5s / +5s buttons."""
    st.session_state.running = False
    st.session_state.cursor = round(
        min(DURATION, max(0.0, st.session_state.cursor + delta_min)), 1)


def clock(minute: float) -> str:
    total = max(0, int(minute))
    return f"{(8 + total // 60) % 24:02d}:{total % 60:02d}"


# Minutes where a new STOP-tier status appears - playback pauses at each of these.
STOP_ONSETS = sorted(m for m, _idx, _cols, tier in status_events(SID)
                     if classifier.is_stop(tier))

# Re-arm STOP events if the user scrubbed backwards past the last one.
if st.session_state.cursor < st.session_state.last_stop_min:
    st.session_state.last_stop_min = st.session_state.cursor

# Advance the cursor BEFORE the seek slider is created, so the keyed slider both follows
# playback and stays freely draggable when paused. A Tier 1/2 onset pauses playback at that
# minute (mirrors a real machine stopping the pump); pressing Play resumes past it.
if st.session_state.running:
    nxt = round(min(DURATION, st.session_state.cursor + st.session_state.speed * TICK_SEC), 1)
    due = [m for m in STOP_ONSETS if st.session_state.last_stop_min < m <= nxt]
    if due:
        st.session_state.cursor = min(due)
        st.session_state.last_stop_min = min(due)
        st.session_state.running = False
    else:
        st.session_state.cursor = nxt
        if st.session_state.cursor >= DURATION:
            st.session_state.running = False


# ---------------------------------------------------------------------------
# Tier-classified messages posted to inboxes (deterministic; all onsets <= cursor)
# ---------------------------------------------------------------------------
def _params_at(row):
    return {spec.label: (row[spec.key], spec.unit) for spec in PARAM_SPECS}


def build_messages(sid: str, cursor: float):
    """All anomaly + drift onsets up to the cursor, each classified into a Tier with its
    action and inbox recipients (classifier.TIER_META)."""
    f = DS.sessions[sid]
    msgs = []

    # Flag-driven events: one message per new status (active-flag set gaining a flag).
    for minute, idx, cols, tier in status_events(sid):
        if minute > cursor:
            continue
        row = f.iloc[idx]
        meta = TIER_META[tier]
        msgs.append({
            "minute": minute, "clock": clock(minute), "tier": tier,
            "active": [EVENT_LABELS[c] for c in cols],
            "headline": meta["headline"], "action": meta["action"],
            "stop": meta["stop"], "recipients": meta["recipients"], "color": meta["color"],
            "params": _params_at(row),
        })

    # Derived Tier-3 moderate-drift events (risk score crossings, no pump stop).
    for start, start_idx, risk in drift_events(sid):
        if start > cursor:
            continue
        meta = TIER_META[Tier.TIER3]
        row = f.iloc[start_idx]
        msgs.append({
            "minute": start, "clock": clock(start), "tier": Tier.TIER3,
            "active": [f"Moderate drift (risk {risk:.2f})"],
            "headline": meta["headline"], "action": meta["action"],
            "stop": meta["stop"], "recipients": meta["recipients"], "color": meta["color"],
            "params": _params_at(row),
        })

    return sorted(msgs, key=lambda m: m["minute"])


MESSAGES = build_messages(SID, st.session_state.cursor)


def messages_for(recipient: str):
    return [m for m in MESSAGES if recipient in m["recipients"]]


def anomaly_strip_html(sid: str) -> str:
    """Red/blue markers over the session, each with a native hover tooltip naming the
    anomaly. Red = Tier 1/2 STOP event, blue = advisory event."""
    f = DS.sessions[sid]
    spans = []
    for s, e, idx in event_intervals(sid):
        row = f.iloc[idx]
        cols = [c for c in config.ADVERSE_EVENT_COLUMNS if int(row.get(c, 0))]
        tier = classifier.worst_tier(cols)
        labels = ", ".join(EVENT_LABELS[c] for c in cols) or "event"
        tip = f"min {s:.0f} ({clock(s)}) - {labels} [{tier.value}]"
        col = TIER_COLOR["red"] if classifier.is_stop(tier) else TIER_COLOR["accent"]
        left = s / DURATION * 100
        width = max(0.8, (e - s) / DURATION * 100)
        spans.append(
            f'<span title="{tip}" style="position:absolute;left:{left:.2f}%;'
            f'width:{width:.2f}%;top:0;bottom:0;background:{col};border-radius:2px;'
            f'cursor:help;"></span>'
        )
    return (
        f'<div style="position:relative;height:14px;background:{PALETTE["track"]};'
        f'border-radius:3px;margin:2px 0;">{"".join(spans)}</div>'
        f'<div style="font-size:11px;color:{PALETTE["muted"]};margin:2px 0 6px 0;">'
        f'Anomaly timeline - hover a marker to see the event '
        f'(red = STOP, blue = advisory)</div>'
    )


# ---------------------------------------------------------------------------
# Sidebar: navbar + playback transport (rendered on every page)
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("HemoAgent")
    page = st.radio(
        "Navigation", PAGES,
        format_func=lambda p: p if p == "Main Dashboard"
        else f"{p} ({len(messages_for(PAGE_RECIPIENT[p]))})",
        label_visibility="collapsed",
    )

    st.markdown("---")
    st.caption("Playback")
    b1, b2 = st.columns(2)
    b1.button("Pause" if st.session_state.running else "Play", type="primary",
              width="stretch", on_click=toggle_running)
    b2.button("Reset", width="stretch", on_click=reset_session)
    st.session_state.speed = st.radio(
        "Speed (sim-min / sec)", config.PLAYBACK_SPEEDS, horizontal=True,
        index=config.PLAYBACK_SPEEDS.index(st.session_state.speed),
        format_func=lambda s: f"{s}x",
    )

    st.markdown("---")
    st.caption(f"Session: {DS.label(SID)}")
    st.caption(f"Minute {st.session_state.cursor:.1f} / {config.SESSION_MINUTES} "
               f"({clock(st.session_state.cursor)})")
    st.caption(f"Anomalies so far: {len(MESSAGES)}")


# ---------------------------------------------------------------------------
# Inbox pages
# ---------------------------------------------------------------------------
def render_inbox(recipient: str):
    st.title(f"{recipient} Inbox")
    st.caption("Auto-posted by the emergency classifier. Not a medical device.")
    msgs = messages_for(recipient)
    if not msgs:
        st.info("No messages yet. Messages arrive as anomalies occur during playback.")
        return
    p = config.PATIENT_PROFILE
    for msg in reversed(msgs):
        c = TIER_COLOR[msg["color"]]
        sign = "\U0001F534 " if msg["stop"] else ""     # big red circle for STOP events
        with st.container(border=True):
            # Tier banner.
            st.markdown(
                f'<div style="background:{c};color:#fff;border-radius:8px;padding:10px 14px;'
                f'font-weight:700;font-size:{"20px" if msg["stop"] else "15px"};">'
                f'{sign}{msg["tier"].value} - {msg["headline"]}</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f"**Minute {msg['minute']:.1f} ({msg['clock']})** &nbsp;|&nbsp; "
                f"**To:** {recipient} &nbsp;|&nbsp; **Session:** {DS.label(SID)}  \n"
                f"**Action:** {msg['action']}"
            )
            st.markdown(
                f"**Patient:** {p['name']} ({p['age']}{p['sex'][:1]}) - {p['esrd_cause']}  \n"
                f"{p['vascular_access']} | Dialyzer {p['dialyzer']} | {p['schedule']}  \n"
                f"Labs: {p['baseline_labs']}"
            )
            st.markdown("**Anomaly:** " + (", ".join(msg["active"]) if msg["active"] else "-"))
            st.markdown("**Parameters at event:**")
            rows = {lbl: [f"{v:.2f} {u}" if not pd.isna(v) else "--"]
                    for lbl, (v, u) in msg["params"].items()}
            st.table(pd.DataFrame(rows, index=["value"]).T)


if page in PAGE_RECIPIENT:
    render_inbox(PAGE_RECIPIENT[page])


# ---------------------------------------------------------------------------
# Main dashboard
# ---------------------------------------------------------------------------
if page == "Main Dashboard":
    p = config.PATIENT_PROFILE
    st.title("HemoAgent Session Simulator")
    st.caption("Phase 1 - emergency classifier over raw device playback - not a medical device")

    h1, h2 = st.columns([3, 2])
    with h1:
        st.markdown(
            f"**{p['name']}** ({p['age']}{p['sex'][:1]}) | {p['esrd_cause']}  \n"
            f"{p['vascular_access']} | Dialyzer {p['dialyzer']} | {p['schedule']}  \n"
            f"Labs: {p['baseline_labs']}"
        )
    with h2:
        ids = DS.session_ids()
        st.selectbox("Session", ids, index=ids.index(SID), format_func=DS.label,
                     key="session_select", on_change=on_session_change)
        m = DS.meta[SID]
        st.caption(f"UF removed {m['uf_total_L']:.2f} L | event-minutes {m['n_event_minutes']}")

    # Current CODE-layer status at the cursor, from the FULL-resolution data (precise, so
    # the slider/chart colour matches the exact moment even between resample bins).
    full = DS.sessions[SID]
    _ft = full["time_min"].to_numpy()
    _ci = min(max(int(np.searchsorted(_ft, st.session_state.cursor, side="right")) - 1, 0),
              len(full) - 1)
    crow = full.iloc[_ci]
    cur_cols = [c for c in config.ADVERSE_EVENT_COLUMNS if int(crow.get(c, 0))]
    cur_risk = float(crow.get("hypotension_risk_score", float("nan")))
    if cur_cols:
        cur_tier = classifier.worst_tier(cur_cols)
        cur_labels = ", ".join(EVENT_LABELS[c] for c in cur_cols)
    elif np.isfinite(cur_risk) and cur_risk >= config.MODERATE_DRIFT_RISK_HI:
        cur_tier, cur_labels = Tier.TIER3, f"risk {cur_risk:.2f}"
    else:
        cur_tier, cur_labels = None, ""
    stop_active = cur_tier in (Tier.TIER1, Tier.TIER2)

    # When stopped, recolour the seek slider red (default is blue). Injected before the
    # slider so it applies this run; the chart line is coloured to match below.
    if stop_active:
        st.markdown(
            "<style>"
            'div[data-testid="stSlider"] [role="slider"]{background-color:#dc2626 !important;}'
            'div[data-testid="stSlider"] [data-baseweb="slider"] > div > div:nth-child(2)'
            "{background:#dc2626 !important;}"
            "</style>",
            unsafe_allow_html=True,
        )

    # Full-width seek + before/after (-5s / +5s) buttons + hoverable anomaly strip.
    st.slider(f"Seek - minute {st.session_state.cursor:.1f} / {config.SESSION_MINUTES} "
              f"({clock(st.session_state.cursor)})",
              0.0, float(round(DURATION, 1)), step=0.1, key="cursor")
    nb1, nb2, _ = st.columns([1, 1, 8])
    nb1.button("⏪ 5s", width="stretch", on_click=nudge, args=(-5 / 60,))
    nb2.button("5s ⏩", width="stretch", on_click=nudge, args=(5 / 60,))
    st.markdown(anomaly_strip_html(SID), unsafe_allow_html=True)

    # Emergency status banner (same status that colours the slider / chart).
    if stop_active:
        b_col = TIER_COLOR["red"]
        b_txt = f"\U0001F534 PUMP STOPPED - {cur_tier.value}: {cur_labels}"
    elif cur_tier == Tier.TIER3:
        b_col, b_txt = TIER_COLOR["amber"], f"MODERATE DRIFT - reduce UFR ({cur_labels})"
    elif cur_tier == Tier.INFO:
        b_col, b_txt = TIER_COLOR["accent"], f"ADVISORY - {cur_labels}"
    else:
        b_col, b_txt = PALETTE["green"], "NOMINAL - no active anomaly"
    st.markdown(
        f'<div style="background:{b_col};color:#fff;border-radius:8px;padding:12px 16px;'
        f'font-weight:700;font-size:18px;margin-bottom:12px;">{b_txt}</div>',
        unsafe_allow_html=True,
    )

    # Resampled view up to the cursor (for readouts / event board / chart data).
    FRAME = resample(SID, st.session_state.resolution)
    TIMES = FRAME["time_min"].to_numpy()
    n = max(1, int(np.searchsorted(TIMES, st.session_state.cursor, side="right")))
    seen = FRAME.iloc[:n]
    current = seen.iloc[-1]

    # Big central trend chart
    st.subheader("Parameter trend")
    st.selectbox(
        "Variable", [s.key for s in PARAM_SPECS],
        format_func=lambda k: f"{PARAM_SPECS_BY_KEY[k].label} ({PARAM_SPECS_BY_KEY[k].unit})",
        key="chart_var",
    )
    spec = PARAM_SPECS_BY_KEY[st.session_state.chart_var]

    # Y-axis fitted to the variable's actual range over the whole session (stable during
    # playback), with a little padding - the wide gauge ranges are only for the readouts.
    col = FRAME[spec.key]
    lo, hi = float(col.min()), float(col.max())
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        lo, hi = spec.gmin, spec.gmax
    pad = (hi - lo) * 0.08 or 1.0
    y_range = [lo - pad, hi + pad]

    fig = go.Figure()
    line_color = PALETTE["red"] if stop_active else PALETTE["accent"]
    fig.add_trace(go.Scatter(
        x=seen["time_min"], y=seen[spec.key], mode="lines",
        line=dict(color=line_color, width=1.6, shape="spline", smoothing=0.6),
    ))
    fig.update_layout(
        height=460, margin=dict(l=70, r=30, t=20, b=60),
        paper_bgcolor=PALETTE["card"], plot_bgcolor=PALETTE["card"],
        font=dict(color=PALETTE["text"], size=17), showlegend=False,
        xaxis=dict(title=dict(text="Time (minutes)", font=dict(size=20)),
                   range=[0, config.SESSION_MINUTES], gridcolor=PALETTE["grid"],
                   tickfont=dict(size=16)),
        yaxis=dict(title=dict(text=f"{spec.label} ({spec.unit})", font=dict(size=20)),
                   range=y_range, gridcolor=PALETTE["grid"],
                   tickfont=dict(size=16)),
    )
    st.plotly_chart(fig, width="stretch")

    # Resolution button, directly under the chart.
    st.radio("Time resolution", list(RESOLUTIONS.keys()), horizontal=True, key="resolution")

    # Machine-parameter readouts
    st.subheader("Machine parameters")
    html = ['<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:14px;">']
    for s in PARAM_SPECS:
        v = current.get(s.key, float("nan"))
        disp = "--" if pd.isna(v) else f"{v:.1f}"
        pct = 0.0 if (pd.isna(v) or s.gmax <= s.gmin) else \
            max(0.0, min(100.0, (v - s.gmin) / (s.gmax - s.gmin) * 100))
        html.append(
            f'<div style="background:{PALETTE["card"]};border:1px solid {PALETTE["border"]};'
            f'border-radius:8px;padding:14px 16px;box-shadow:{PALETTE["shadow"]};">'
            f'<div style="display:flex;justify-content:space-between;align-items:baseline;">'
            f'<span style="font-size:14px;color:{PALETTE["muted"]};">{s.label}</span>'
            f'<span style="font-size:24px;font-weight:700;color:{PALETTE["text"]};">{disp}'
            f'<span style="font-size:12px;color:{PALETTE["muted"]};margin-left:4px;">{s.unit}</span></span></div>'
            f'<div style="height:8px;background:{PALETTE["track"]};border-radius:4px;margin-top:9px;overflow:hidden;">'
            f'<div style="height:100%;width:{pct:.0f}%;background:{PALETTE["accent"]};"></div></div></div>'
        )
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)

    # Adverse-event status board
    st.subheader("Adverse events")
    board = ['<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;">']
    for key, label in EVENT_LABELS.items():
        active = bool(int(current.get(key, 0)))
        bg = "#fef2f2" if active else "#f0fdf4"
        border = PALETTE["red"] if active else PALETTE["green"]
        text = "#b91c1c" if active else "#15803d"
        board.append(
            f'<div style="background:{bg};border:1px solid {border};border-radius:8px;'
            f'padding:10px 12px;display:flex;align-items:center;gap:10px;">'
            f'<span style="width:12px;height:12px;border-radius:50%;background:{border};flex:none;"></span>'
            f'<span><span style="display:block;font-size:13px;font-weight:600;color:{PALETTE["text"]};">{label}</span>'
            f'<span style="font-size:11px;color:{text};font-weight:600;">'
            f'{"ACTIVE" if active else "clear"}</span></span></div>'
        )
    board.append("</div>")
    st.markdown("".join(board), unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Playback loop (runs on every page so inboxes fill live)
# ---------------------------------------------------------------------------
if st.session_state.running:
    time.sleep(TICK_SEC)
    st.rerun()
