# To Run: python -m streamlit run prototypes/presentation_2_2.py

"""
========================================================================================
PRESENTATION 2.2: UNIFIED LOAD PROFILE SIMULATOR & INSPECTOR
========================================================================================

A minimal, high-performance application combining:
  1. Real-world CSV Ingestion & Scaling (Presentation 2)
  2. Modular Synthetic Load Modeling & Presets (Presentation 1)
  3. Hybrid Profiling (Measured Baseline + Planned New Consumers)
  4. Universal Grid Limits (e.g. 110 kW) & Target Cap Overload Analysis (e.g. 90.6 kW)

All controls are integrated in the main page (no sidebar) using st.form for fast execution.
========================================================================================
"""

import datetime
import uuid
import re
from io import StringIO
from typing import List, Dict, Any, Tuple

import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go


# --------------------------------------------------------------------------------------
# 1. Page Configuration & Professional Styling
# --------------------------------------------------------------------------------------
st.set_page_config(
    page_title="Load Profile & Energy Simulator",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown(
    """
    <style>
    /* Hide the sidebar */
    [data-testid="stSidebar"] {
        display: none;
    }
    .metric-card {
        background-color: #1a1f2c;
        border-radius: 8px;
        padding: 14px 18px;
        border-left: 4px solid #38bdf8;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        margin-bottom: 12px;
    }
    .metric-card-alert {
        background-color: #26171f;
        border-radius: 8px;
        padding: 14px 18px;
        border-left: 4px solid #f43f5e;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        margin-bottom: 12px;
    }
    .metric-title {
        font-size: 0.8rem;
        color: #94a3b8;
        text-transform: uppercase;
        font-weight: 600;
        letter-spacing: 0.5px;
    }
    .metric-val {
        font-size: 1.5rem;
        font-weight: 700;
        color: #f8fafc;
        margin-top: 2px;
    }
    .metric-sub {
        font-size: 0.75rem;
        color: #64748b;
    }
    </style>
    """,
    unsafe_allow_html=True
)

st.title("Unified Load Profile & Energy Simulator")
st.caption("Inspect CSV meter data, synthesize facility loads, scale capacities, and evaluate grid limits.")


# --------------------------------------------------------------------------------------
# 2. Core Business Logic & Helpers
# --------------------------------------------------------------------------------------
DATE_SYNONYMS = ['#', 'datum', 'date', 'zeit', 'timestamp', 'datetime', 'zeitstempel', 'period']
TIME_SYNONYMS = ['code', 'uhrzeit', 'time', 'time_of_day', 'tod', 'intervall', 'stunde', 'hour']
UNIT_SYNONYMS = ['eenheid', 'unit', 'einheit', 'status', 'valid', 'type', 'statuscode']


def read_uploaded_file(file_obj) -> str:
    """Reads raw string content from an uploaded buffer with multi-encoding fallback."""
    file_obj.seek(0)
    raw = file_obj.read()
    for enc in ['utf-8', 'latin1', 'cp1252', 'iso-8859-1']:
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode('utf-8', errors='ignore')


def parse_csv_string(content: str, skiprows: int = 0) -> pd.DataFrame:
    """Parses raw CSV string using python's flexible delimiter sniffer."""
    return pd.read_csv(StringIO(content), sep=None, engine='python', skiprows=skiprows)


def detect_csv_columns(df: pd.DataFrame) -> Tuple[List[str], List[str], str]:
    """Smart heuristic detection of timestamp, meter/power, and unit columns."""
    cols = list(df.columns)
    time_cols, power_cols = [], []
    unit_guess = "kWh (15-min interval) → kW"

    # Date Column
    date_col = None
    for c in cols:
        clean = str(c).strip().lower()
        if any(s == clean or s in clean for s in DATE_SYNONYMS):
            date_col = c
            time_cols.append(c)
            break

    # Time Column
    for c in cols:
        if c == date_col:
            continue
        clean = str(c).strip().lower()
        if any(s == clean or s in clean for s in TIME_SYNONYMS):
            time_cols.append(c)
            break

    if not time_cols and cols:
        time_cols = [cols[0]]

    # Power Columns
    for c in cols:
        if c in time_cols:
            continue
        clean = str(c).strip().lower()
        if any(u in clean for u in UNIT_SYNONYMS):
            continue
        cleaned_series = df[c].astype(str).str.replace(' ', '').str.replace(',', '.')
        if pd.to_numeric(cleaned_series, errors='coerce').notnull().sum() > (0.3 * len(df)):
            power_cols.append(c)

    return time_cols, power_cols, unit_guess


def generate_sample_demo_csv(days: int = 14) -> str:
    """Generates synthetic 15-minute Kwartierdata (2 connection meters) for testing."""
    periods = 96 * days
    timestamps = pd.date_range("2025-01-01 00:00", periods=periods, freq="15min")
    hours = timestamps.hour
    workdays = timestamps.dayofweek < 5

    # Meter 1: Small wing (17 rooms / baseline)
    m1_kwh = np.where(workdays & (hours >= 6) & (hours <= 22), 2.5, 1.2)
    m1_kwh = np.clip(m1_kwh + np.random.normal(0, 0.2, len(m1_kwh)), 0.5, None)

    # Meter 2: Main wing (35 rooms / kitchen / HVAC)
    m2_kwh = np.where(workdays & (hours >= 7) & (hours <= 21), 6.5, 2.0)
    m2_kwh = np.clip(m2_kwh + np.random.normal(0, 0.4, len(m2_kwh)), 0.8, None)

    demo_df = pd.DataFrame({
        "#": timestamps.strftime("%Y.%m.%d"),
        "CODE": timestamps.strftime("%H:%M"),
        "Eenheid": "kWh",
        "Meter_1_SmallWing_kWh": np.round(m1_kwh, 2),
        "Meter_2_MainWing_kWh": np.round(m2_kwh, 2)
    })
    buf = StringIO()
    demo_df.to_csv(buf, index=False, sep=";")
    return buf.getvalue()


# --------------------------------------------------------------------------------------
# 3. Synthetic Component Data Structure
# --------------------------------------------------------------------------------------
class SyntheticConsumer:
    """Represents a configurable electrical consumer load."""
    def __init__(
        self,
        name: str,
        power_kw: float,
        start_time: datetime.time,
        end_time: datetime.time,
        has_peak: bool = False,
        peak_power_kw: float = 0.0,
        peak_duration_min: int = 30
    ):
        self.id = str(uuid.uuid4())[:8]
        self.name = name
        self.power_kw = float(power_kw)
        self.start_time = start_time
        self.end_time = end_time
        self.has_peak = has_peak
        self.peak_power_kw = float(peak_power_kw) if has_peak else float(power_kw)
        self.peak_duration_min = int(peak_duration_min)

    def get_24h_curve(self) -> np.ndarray:
        """Computes a 96-slot (15-min) power curve in kW for 24 hours."""
        curve = np.zeros(96, dtype=float)
        for slot in range(96):
            slot_time = datetime.time(slot // 4, (slot % 4) * 15)
            if self.start_time <= self.end_time:
                active = (self.start_time <= slot_time < self.end_time)
            else:
                active = (slot_time >= self.start_time or slot_time < self.end_time)

            if active:
                if self.has_peak:
                    start_mins = self.start_time.hour * 60 + self.start_time.minute
                    curr_mins = slot_time.hour * 60 + slot_time.minute
                    elapsed = (curr_mins - start_mins) % 1440
                    if elapsed < self.peak_duration_min:
                        curve[slot] = self.peak_power_kw
                    else:
                        curve[slot] = self.power_kw
                else:
                    curve[slot] = self.power_kw
        return curve


# --------------------------------------------------------------------------------------
# 4. KPI Calculation & Figure Creation
# --------------------------------------------------------------------------------------
def compute_kpis(df: pd.DataFrame, power_col: str, grid_limit_kw: float, target_cap_kw: float) -> Dict[str, Any]:
    """Calculates all key energy performance indicators & overload metrics."""
    series = df[power_col].fillna(0.0)
    p_max = float(series.max()) if not series.empty else 0.0
    p_min = float(series.min()) if not series.empty else 0.0
    p_avg = float(series.mean()) if not series.empty else 0.0
    total_kwh = float(series.sum() * 0.25)
    total_mwh = total_kwh / 1000.0

    # Overload vs Grid Limit
    overload_diff = (series - grid_limit_kw).clip(lower=0.0)
    overload_peak = float(overload_diff.max())
    overload_hours = float((series > grid_limit_kw).sum() * 0.25)
    overload_energy_kwh = float(overload_diff.sum() * 0.25)

    # Shaving vs Target Cap
    shave_diff = (series - target_cap_kw).clip(lower=0.0)
    shave_peak = float(shave_diff.max())
    shave_hours = float((series > target_cap_kw).sum() * 0.25)
    shave_energy_kwh = float(shave_diff.sum() * 0.25)

    return {
        "p_max": p_max,
        "p_min": p_min,
        "p_avg": p_avg,
        "total_kwh": total_kwh,
        "total_mwh": total_mwh,
        "overload_peak": overload_peak,
        "overload_hours": overload_hours,
        "overload_energy_kwh": overload_energy_kwh,
        "shave_peak": shave_peak,
        "shave_hours": shave_hours,
        "shave_energy_kwh": shave_energy_kwh,
        "count": len(series)
    }


def create_load_figure(
    df: pd.DataFrame,
    time_col: str,
    component_cols: List[str],
    total_col: str,
    grid_limit_kw: float = None,
    target_cap_kw: float = None
) -> go.Figure:
    """Builds a responsive dark-themed Plotly time series chart."""
    fig = go.Figure()

    # Sub-meter / Sub-component lines
    palette = ["#38bdf8", "#34d399", "#fbbf24", "#a78bfa", "#f472b6", "#fb923c"]
    for i, col in enumerate(component_cols):
        if col in df.columns and col != total_col:
            fig.add_trace(go.Scatter(
                x=df[time_col],
                y=df[col],
                mode="lines",
                name=col,
                line=dict(width=1.5, color=palette[i % len(palette)], dash="solid"),
                opacity=0.7
            ))

    # Total Demand Curve (Bold White)
    if total_col in df.columns:
        fig.add_trace(go.Scatter(
            x=df[time_col],
            y=df[total_col],
            mode="lines",
            name="Total Active Load (kW)",
            line=dict(color="#ffffff", width=2.5)
        ))

    # Grid Limit Line (Red)
    if grid_limit_kw and grid_limit_kw > 0:
        fig.add_hline(
            y=grid_limit_kw,
            line_dash="dash",
            line_color="#f43f5e",
            line_width=2,
            annotation_text=f"Max Grid Limit ({grid_limit_kw:,.1f} kW)",
            annotation_position="top right"
        )

    # Target Cap Line (Cyan / Peak Shaving)
    if target_cap_kw and target_cap_kw > 0 and target_cap_kw != grid_limit_kw:
        fig.add_hline(
            y=target_cap_kw,
            line_dash="dot",
            line_color="#38bdf8",
            line_width=1.5,
            annotation_text=f"Target Shaving Cap ({target_cap_kw:,.1f} kW)",
            annotation_position="bottom right"
        )

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#0B0F19",
        plot_bgcolor="#111827",
        margin=dict(l=40, r=40, t=40, b=40),
        xaxis=dict(showgrid=True, gridcolor="#1f2937", title="Timestamp / Time of Day"),
        yaxis=dict(showgrid=True, gridcolor="#1f2937", title="Active Power (kW)", rangemode="tozero"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hovermode="x unified",
        height=480
    )
    return fig


# --------------------------------------------------------------------------------------
# 5. Top Controls: Mode & Global Grid Parameters (No Sidebar)
# --------------------------------------------------------------------------------------
top_col1, top_col2, top_col3 = st.columns([4, 3, 3])

with top_col1:
    app_mode = st.radio(
        "Select Mode:",
        options=[
            "CSV Real Data (Import & Scale)",
            "Synthetic Profile (Bottom-Up Builder)",
            "Hybrid (CSV Baseline + Planned Loads)"
        ],
        horizontal=True
    )

with top_col2:
    global_grid_limit = st.number_input(
        "Max Grid Capacity (kW):",
        min_value=10.0,
        max_value=5000.0,
        value=110.0,
        step=5.0,
        help="Total electrical connection capacity (e.g. 2 x 55 kW = 110 kW)."
    )

with top_col3:
    global_target_cap = st.number_input(
        "Target Peak-Shaving Cap (kW):",
        min_value=5.0,
        max_value=global_grid_limit,
        value=90.6,
        step=1.0,
        help="Target power ceiling for battery peak shaving."
    )

st.divider()


# ======================================================================================
# MODE 1: CSV Real Data (Import & Scale)
# ======================================================================================
if app_mode == "CSV Real Data (Import & Scale)":
    st.subheader("1. CSV Data Ingestion")
    
    csv_col1, csv_col2 = st.columns([5, 2])
    with csv_col1:
        uploaded_file = st.file_uploader("Upload Load Profile CSV:", type=["csv", "txt"], key="csv_upload_main")
        if uploaded_file:
            st.session_state["raw_csv_text"] = read_uploaded_file(uploaded_file)
            st.session_state["raw_csv_name"] = uploaded_file.name
    with csv_col2:
        st.write("")
        st.write("")
        if st.button("Load 15-Min Demo Dataset", use_container_width=True):
            st.session_state["raw_csv_text"] = generate_sample_demo_csv(days=14)
            st.session_state["raw_csv_name"] = "Sample_Hotel_15min_Kwartierdata.csv"
            st.rerun()

    if "raw_csv_text" not in st.session_state:
        st.info("Please upload a CSV file above or click 'Load 15-Min Demo Dataset'.")
        st.stop()

    raw_text = st.session_state["raw_csv_text"]
    file_name = st.session_state.get("raw_csv_name", "data.csv")
    st.caption(f"Active Dataset: **{file_name}**")

    # Optional table inspector
    with st.expander("CSV Table Inspector & Preview", expanded=False):
        skip_rows = st.number_input("Skip Header Rows:", min_value=0, max_value=50, value=0, step=1)
        df_raw_preview = parse_csv_string(raw_text, skiprows=int(skip_rows))
        st.markdown(f"**Rows:** `{len(df_raw_preview):,}` | **Columns:** `{len(df_raw_preview.columns)}`")
        st.dataframe(df_raw_preview.head(10), use_container_width=True, height=180)
    
    if "df_raw_preview" not in locals():
        df_raw_preview = parse_csv_string(raw_text, skiprows=0)

    suggested_time, suggested_power, suggested_unit = detect_csv_columns(df_raw_preview)
    all_cols = list(df_raw_preview.columns)

    # Configuration Form
    with st.form(key=f"csv_form_{file_name}"):
        st.subheader("2. Column Mapping & Scaling Configuration")
        c1, c2, c3 = st.columns([3, 3, 3])

        with c1:
            sel_time_cols = st.multiselect(
                "Timestamp Column(s):",
                options=all_cols,
                default=[c for c in suggested_time if c in all_cols]
            )

        with c2:
            sel_power_cols = st.multiselect(
                "Power / Meter Column(s):",
                options=all_cols,
                default=[c for c in suggested_power if c in all_cols]
            )

        with c3:
            unit_opts = [
                "kWh (15-min interval) → kW",
                "kW (Active Power - Direct)",
                "W (Watt) → kW",
                "kWh (Hourly interval) → kW"
            ]
            unit_idx = unit_opts.index(suggested_unit) if suggested_unit in unit_opts else 0
            sel_unit = st.selectbox("Unit Conversion:", options=unit_opts, index=unit_idx)

        # Date & Scaling settings
        c_date1, c_date2, c_scale = st.columns([3, 3, 3])
        
        sample_str = ""
        if sel_time_cols:
            sample_str = " ".join([str(df_raw_preview[c].dropna().iloc[0]) for c in sel_time_cols if not df_raw_preview[c].dropna().empty])
        starts_with_year = bool(re.match(r"^\s*\d{4}", sample_str))

        with c_date1:
            dayfirst_toggle = st.toggle(
                "Day-First Date Format (DD.MM)",
                value=not starts_with_year,
                help="Toggle on for European format (DD.MM.YYYY), off for ISO format (YYYY.MM.DD)."
            )

        with c_date2:
            if sample_str:
                try:
                    p_sample = pd.to_datetime(sample_str, dayfirst=dayfirst_toggle, errors="coerce")
                    st.caption(f"Preview: `{sample_str}` ➔ **{p_sample.strftime('%d %b %Y %H:%M')}**")
                except Exception:
                    st.caption(f"Raw: `{sample_str}`")

        with c_scale:
            scaling_mode = st.selectbox("Scaling Mode:", ["Direct Factor", "Unit Ratio (Target / Base)"])
            if scaling_mode == "Direct Factor":
                scale_val = st.number_input("Scaling Factor:", min_value=0.1, max_value=100.0, value=1.0, step=0.1)
                final_scaling_factor = float(scale_val)
            else:
                s_base = st.number_input("Base Units (e.g. 52 Rooms):", min_value=1, value=52, step=1)
                s_target = st.number_input("Target Units (e.g. 135 Rooms):", min_value=1, value=135, step=1)
                final_scaling_factor = float(s_target / s_base)
                st.caption(f"Calculated Ratio: **{final_scaling_factor:.3f}x**")

        submit_csv = st.form_submit_button("Calculate Load Profile & Metrics", type="primary", use_container_width=True)

    calc_key = f"calc_res_{file_name}"
    if submit_csv or calc_key not in st.session_state:
        if not sel_time_cols or not sel_power_cols:
            st.warning("Please select at least one timestamp column and one power column.")
            st.stop()

        raw_ts = df_raw_preview[sel_time_cols].astype(str).agg(' '.join, axis=1) if len(sel_time_cols) > 1 else df_raw_preview[sel_time_cols[0]].astype(str)
        df_clean = pd.DataFrame()
        df_clean["timestamp"] = pd.to_datetime(raw_ts, dayfirst=dayfirst_toggle, errors="coerce")
        valid_mask = df_clean["timestamp"].notnull()
        df_clean = df_clean[valid_mask].copy()

        for p_col in sel_power_cols:
            s_data = df_raw_preview.loc[valid_mask, p_col].astype(str).str.replace(' ', '').str.replace(',', '.')
            num = pd.to_numeric(s_data, errors="coerce").fillna(0.0)
            if "15-min" in sel_unit:
                num = num * 4.0
            elif "Watt" in sel_unit:
                num = num / 1000.0
            
            num = num * final_scaling_factor
            df_clean[p_col] = num

        df_clean["Total_Demand_kW"] = df_clean[sel_power_cols].sum(axis=1)
        df_clean = df_clean.sort_values("timestamp").reset_index(drop=True)

        kpis = compute_kpis(df_clean, "Total_Demand_kW", global_grid_limit, global_target_cap)
        st.session_state[calc_key] = {
            "df_clean": df_clean,
            "kpis": kpis,
            "power_cols": sel_power_cols
        }

    res = st.session_state.get(calc_key)
    if res:
        kpis = res["kpis"]
        df_clean = res["df_clean"]

        st.subheader("3. Energy & Grid Overload Metrics")
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.markdown(
                f"""<div class="metric-card">
                    <div class="metric-title">Peak Demand (P_max)</div>
                    <div class="metric-val">{kpis['p_max']:,.1f} kW</div>
                    <div class="metric-sub">Min Baseload: {kpis['p_min']:,.1f} kW | Avg: {kpis['p_avg']:,.1f} kW</div>
                </div>""",
                unsafe_allow_html=True
            )
        with m2:
            st.markdown(
                f"""<div class="metric-card">
                    <div class="metric-title">Total Energy</div>
                    <div class="metric-val">{kpis['total_mwh']:,.2f} MWh</div>
                    <div class="metric-sub">{kpis['total_kwh']:,.0f} kWh ({kpis['count']:,} intervals)</div>
                </div>""",
                unsafe_allow_html=True
            )
        with m3:
            is_overload = kpis["overload_peak"] > 0
            card_class = "metric-card-alert" if is_overload else "metric-card"
            st.markdown(
                f"""<div class="{card_class}">
                    <div class="metric-title">Grid Overload (> {global_grid_limit:,.0f} kW)</div>
                    <div class="metric-val">+{kpis['overload_peak']:,.1f} kW</div>
                    <div class="metric-sub">Duration: {kpis['overload_hours']:,.1f} hrs | Energy: {kpis['overload_energy_kwh']:,.1f} kWh</div>
                </div>""",
                unsafe_allow_html=True
            )
        with m4:
            st.markdown(
                f"""<div class="metric-card">
                    <div class="metric-title">Peak Shaving Target (> {global_target_cap:,.0f} kW)</div>
                    <div class="metric-val">+{kpis['shave_peak']:,.1f} kW</div>
                    <div class="metric-sub">Required Battery Energy: {kpis['shave_energy_kwh']:,.1f} kWh</div>
                </div>""",
                unsafe_allow_html=True
            )

        st.subheader("4. Load Profile Time Series")
        fig = create_load_figure(
            df=df_clean,
            time_col="timestamp",
            component_cols=res["power_cols"],
            total_col="Total_Demand_kW",
            grid_limit_kw=global_grid_limit,
            target_cap_kw=global_target_cap
        )
        st.plotly_chart(fig, use_container_width=True)

        with st.expander("Clean Data Table & Export", expanded=False):
            st.dataframe(df_clean, use_container_width=True, height=220)


# ======================================================================================
# MODE 2: Synthetic Bottom-Up Load Modeling
# ======================================================================================
elif app_mode == "Synthetic Profile (Bottom-Up Builder)":
    st.subheader("1. Facility Load Preset")

    if "synthetic_loads" not in st.session_state:
        st.session_state["synthetic_loads"] = [
            SyntheticConsumer("Room Baseload & Standby (135 Rooms)", 27.0, datetime.time(0, 0), datetime.time(23, 45)),
            SyntheticConsumer("Hot Water / Showers (ACS)", 30.0, datetime.time(6, 30), datetime.time(9, 30)),
            SyntheticConsumer("Commercial Kitchen & Restaurant", 35.0, datetime.time(6, 0), datetime.time(10, 30)),
            SyntheticConsumer("HVAC / Central Chiller & Ventilation", 25.0, datetime.time(7, 0), datetime.time(22, 0), has_peak=True, peak_power_kw=35.0, peak_duration_min=30),
            SyntheticConsumer("Spa, Sauna & Wellness Heaters", 20.0, datetime.time(14, 0), datetime.time(22, 0)),
        ]

    p1, p2, p3, p4 = st.columns(4)
    with p1:
        if st.button("Hotel (135 Rooms)", use_container_width=True):
            st.session_state["synthetic_loads"] = [
                SyntheticConsumer("Room Baseload (135 Rooms)", 27.0, datetime.time(0, 0), datetime.time(23, 45)),
                SyntheticConsumer("Hot Water Showers (ACS)", 30.0, datetime.time(6, 30), datetime.time(9, 30)),
                SyntheticConsumer("Kitchen & Dining", 35.0, datetime.time(6, 0), datetime.time(10, 30)),
                SyntheticConsumer("HVAC Air Conditioning", 25.0, datetime.time(7, 0), datetime.time(22, 0), has_peak=True, peak_power_kw=35.0),
                SyntheticConsumer("Spa & Sauna Facility", 20.0, datetime.time(14, 0), datetime.time(22, 0)),
            ]
            st.rerun()
    with p2:
        if st.button("Manufacturing & CNC", use_container_width=True):
            st.session_state["synthetic_loads"] = [
                SyntheticConsumer("Main Production Line", 80.0, datetime.time(6, 0), datetime.time(16, 0), has_peak=True, peak_power_kw=110.0),
                SyntheticConsumer("CNC Milling Station", 25.0, datetime.time(7, 0), datetime.time(17, 0)),
                SyntheticConsumer("Air Compressor System", 30.0, datetime.time(5, 30), datetime.time(18, 0)),
                SyntheticConsumer("Facility Lighting & Vent", 12.0, datetime.time(5, 0), datetime.time(22, 0)),
            ]
            st.rerun()
    with p3:
        if st.button("EV Charging Hub", use_container_width=True):
            st.session_state["synthetic_loads"] = [
                SyntheticConsumer("DC Fast Charger 1", 75.0, datetime.time(7, 30), datetime.time(10, 0)),
                SyntheticConsumer("DC Fast Charger 2", 75.0, datetime.time(16, 0), datetime.time(19, 30)),
                SyntheticConsumer("AC Wallbox Fleet (6x 11kW)", 66.0, datetime.time(8, 0), datetime.time(17, 0)),
                SyntheticConsumer("Site Infrastructure & Lighting", 8.0, datetime.time(0, 0), datetime.time(23, 45)),
            ]
            st.rerun()
    with p4:
        if st.button("Commercial Office", use_container_width=True):
            st.session_state["synthetic_loads"] = [
                SyntheticConsumer("Workstations & Lighting", 40.0, datetime.time(7, 30), datetime.time(18, 0)),
                SyntheticConsumer("Office HVAC & Chillers", 30.0, datetime.time(7, 0), datetime.time(19, 0), has_peak=True, peak_power_kw=45.0),
                SyntheticConsumer("Server Room & IT Infrastructure", 15.0, datetime.time(0, 0), datetime.time(23, 45)),
            ]
            st.rerun()

    # Form to calculate synthetic profile
    with st.form(key="synthetic_config_form"):
        st.subheader("2. Consumers & Standby Baseload")
        standby_kw = st.number_input("Continuous Standby Baseline (kW):", min_value=0.0, max_value=200.0, value=5.0, step=1.0)
        
        st.markdown("**Active Components:**")
        for idx, load in enumerate(st.session_state["synthetic_loads"]):
            st.text(f"{idx+1}. {load.name}: {load.power_kw:.1f} kW ({load.start_time.strftime('%H:%M')} - {load.end_time.strftime('%H:%M')})")

        submit_synth = st.form_submit_button("Calculate Synthetic Load Profile", type="primary", use_container_width=True)

    # Compute 24-hour Profile
    time_slots = [f"{h:02d}:{m:02d}" for h in range(24) for m in (0, 15, 30, 45)]
    df_synth = pd.DataFrame({"time": time_slots})
    total_synth = np.full(96, float(standby_kw), dtype=float)

    if standby_kw > 0:
        df_synth["Standby Baseload"] = float(standby_kw)

    synth_component_names = []
    for load in st.session_state["synthetic_loads"]:
        c_curve = load.get_24h_curve()
        df_synth[load.name] = c_curve
        total_synth += c_curve
        synth_component_names.append(load.name)

    df_synth["Total_Demand_kW"] = total_synth
    synth_kpis = compute_kpis(df_synth, "Total_Demand_kW", global_grid_limit, global_target_cap)

    st.subheader("3. Energy & Grid Metrics")
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.markdown(
            f"""<div class="metric-card">
                <div class="metric-title">24h Peak Demand</div>
                <div class="metric-val">{synth_kpis['p_max']:,.1f} kW</div>
                <div class="metric-sub">Baseload: {synth_kpis['p_min']:,.1f} kW | Avg: {synth_kpis['p_avg']:,.1f} kW</div>
            </div>""",
            unsafe_allow_html=True
        )
    with m2:
        st.markdown(
            f"""<div class="metric-card">
                <div class="metric-title">Daily Consumption</div>
                <div class="metric-val">{synth_kpis['total_kwh']:,.0f} kWh</div>
                <div class="metric-sub">{synth_kpis['total_mwh']:,.2f} MWh/day (~{synth_kpis['total_mwh']*365:,.1f} MWh/a)</div>
            </div>""",
            unsafe_allow_html=True
        )
    with m3:
        is_overload = synth_kpis["overload_peak"] > 0
        card_class = "metric-card-alert" if is_overload else "metric-card"
        st.markdown(
            f"""<div class="{card_class}">
                <div class="metric-title">Grid Overload (> {global_grid_limit:,.0f} kW)</div>
                <div class="metric-val">+{synth_kpis['overload_peak']:,.1f} kW</div>
                <div class="metric-sub">Overload: {synth_kpis['overload_hours']:,.1f} hrs/day | Energy: {synth_kpis['overload_energy_kwh']:,.1f} kWh</div>
            </div>""",
            unsafe_allow_html=True
        )
    with m4:
        st.markdown(
            f"""<div class="metric-card">
                <div class="metric-title">Peak Shaving Target (> {global_target_cap:,.0f} kW)</div>
                <div class="metric-val">+{synth_kpis['shave_peak']:,.1f} kW</div>
                <div class="metric-sub">Required Battery Energy: {synth_kpis['shave_energy_kwh']:,.1f} kWh</div>
            </div>""",
            unsafe_allow_html=True
        )

    st.subheader("4. 24-Hour Synthesized Load Curve")
    fig_synth = create_load_figure(
        df=df_synth,
        time_col="time",
        component_cols=synth_component_names + (["Standby Baseload"] if standby_kw > 0 else []),
        total_col="Total_Demand_kW",
        grid_limit_kw=global_grid_limit,
        target_cap_kw=global_target_cap
    )
    st.plotly_chart(fig_synth, use_container_width=True)


# ======================================================================================
# MODE 3: Hybrid (CSV Baseline + Planned Loads)
# ======================================================================================
elif app_mode == "Hybrid (CSV Baseline + Planned Loads)":
    st.subheader("1. Baseline CSV Selection")

    csv_col1, csv_col2 = st.columns([5, 2])
    with csv_col1:
        uploaded_file = st.file_uploader("Upload Baseline CSV:", type=["csv", "txt"], key="hybrid_upload_main")
        if uploaded_file:
            st.session_state["raw_csv_text"] = read_uploaded_file(uploaded_file)
            st.session_state["raw_csv_name"] = uploaded_file.name
    with csv_col2:
        st.write("")
        st.write("")
        if st.button("Load Demo Baseline", use_container_width=True):
            st.session_state["raw_csv_text"] = generate_sample_demo_csv(days=14)
            st.session_state["raw_csv_name"] = "Sample_Hotel_15min_Kwartierdata.csv"
            st.rerun()

    if "raw_csv_text" not in st.session_state:
        st.info("Please upload a baseline CSV file above or load Demo Data.")
        st.stop()

    df_base = parse_csv_string(st.session_state["raw_csv_text"])
    time_cols, power_cols, _ = detect_csv_columns(df_base)

    with st.form(key="hybrid_form"):
        st.subheader("2. Add Planned Expansion Consumers")
        h_col1, h_col2 = st.columns(2)
        with h_col1:
            st.markdown("**Planned Consumer 1:**")
            h1_name = st.text_input("Asset Name:", value="New DC EV Fast Charger (50 kW)")
            h1_power = st.number_input("Power (kW):", min_value=0.0, value=50.0, step=5.0)
            h1_start = st.time_input("Start Time:", value=datetime.time(8, 0))
            h1_end = st.time_input("End Time:", value=datetime.time(18, 0))

        with h_col2:
            st.markdown("**Planned Consumer 2:**")
            h2_name = st.text_input("Asset Name 2:", value="New Wellness & Sauna Wing (25 kW)")
            h2_power = st.number_input("Power 2 (kW):", min_value=0.0, value=25.0, step=5.0)
            h2_start = st.time_input("Start Time 2:", value=datetime.time(14, 0))
            h2_end = st.time_input("End Time 2:", value=datetime.time(22, 0))

        submit_hybrid = st.form_submit_button("Calculate Hybrid Load Profile", type="primary", use_container_width=True)

    # Process Hybrid
    raw_ts = df_base[time_cols].astype(str).agg(' '.join, axis=1) if len(time_cols) > 1 else df_base[time_cols[0]].astype(str)
    df_hybrid = pd.DataFrame()
    df_hybrid["timestamp"] = pd.to_datetime(raw_ts, errors="coerce")
    valid_mask = df_hybrid["timestamp"].notnull()
    df_hybrid = df_hybrid[valid_mask].copy()

    base_power = np.zeros(len(df_hybrid))
    for p_col in power_cols:
        s_data = df_base.loc[valid_mask, p_col].astype(str).str.replace(' ', '').str.replace(',', '.')
        base_power += pd.to_numeric(s_data, errors="coerce").fillna(0.0).values * 4.0

    df_hybrid["Measured Baseline (kW)"] = base_power

    hours = df_hybrid["timestamp"].dt.time
    h1_active = (hours >= h1_start) & (hours < h1_end) if h1_start <= h1_end else (hours >= h1_start) | (hours < h1_end)
    h2_active = (hours >= h2_start) & (hours < h2_end) if h2_start <= h2_end else (hours >= h2_start) | (hours < h2_end)

    df_hybrid[h1_name] = np.where(h1_active, float(h1_power), 0.0)
    df_hybrid[h2_name] = np.where(h2_active, float(h2_power), 0.0)
    df_hybrid["Total_Demand_kW"] = df_hybrid["Measured Baseline (kW)"] + df_hybrid[h1_name] + df_hybrid[h2_name]

    hybrid_kpis = compute_kpis(df_hybrid, "Total_Demand_kW", global_grid_limit, global_target_cap)

    st.subheader("3. Hybrid Metrics")
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.markdown(
            f"""<div class="metric-card">
                <div class="metric-title">Hybrid Peak Demand</div>
                <div class="metric-val">{hybrid_kpis['p_max']:,.1f} kW</div>
                <div class="metric-sub">Avg: {hybrid_kpis['p_avg']:,.1f} kW</div>
            </div>""",
            unsafe_allow_html=True
        )
    with m2:
        st.markdown(
            f"""<div class="metric-card">
                <div class="metric-title">Hybrid Energy</div>
                <div class="metric-val">{hybrid_kpis['total_mwh']:,.2f} MWh</div>
                <div class="metric-sub">{hybrid_kpis['total_kwh']:,.0f} kWh</div>
            </div>""",
            unsafe_allow_html=True
        )
    with m3:
        is_overload = hybrid_kpis["overload_peak"] > 0
        card_class = "metric-card-alert" if is_overload else "metric-card"
        st.markdown(
            f"""<div class="{card_class}">
                <div class="metric-title">Grid Overload (> {global_grid_limit:,.0f} kW)</div>
                <div class="metric-val">+{hybrid_kpis['overload_peak']:,.1f} kW</div>
                <div class="metric-sub">Duration: {hybrid_kpis['overload_hours']:,.1f} hrs | Energy: {hybrid_kpis['overload_energy_kwh']:,.1f} kWh</div>
            </div>""",
            unsafe_allow_html=True
        )
    with m4:
        st.markdown(
            f"""<div class="metric-card">
                <div class="metric-title">Peak Shaving Target (> {global_target_cap:,.0f} kW)</div>
                <div class="metric-val">+{hybrid_kpis['shave_peak']:,.1f} kW</div>
                <div class="metric-sub">Required Battery Energy: {hybrid_kpis['shave_energy_kwh']:,.1f} kWh</div>
            </div>""",
            unsafe_allow_html=True
        )

    st.subheader("4. Hybrid Load Profile Curve")
    fig_hybrid = create_load_figure(
        df=df_hybrid,
        time_col="timestamp",
        component_cols=["Measured Baseline (kW)", h1_name, h2_name],
        total_col="Total_Demand_kW",
        grid_limit_kw=global_grid_limit,
        target_cap_kw=global_target_cap
    )
    st.plotly_chart(fig_hybrid, use_container_width=True)
