# This File is purely for demonstration purposes
# Feel free to add or change Code at any time
# To Run: python -m streamlit run presentation2.py

"""
========================================================================================
PRESENTATION 2: CSV LOAD PROFILE UPLOAD & VISUALIZER (presentation2.py)
========================================================================================

Purpose & Scope:
----------------
A clean, minimal, and standalone tool to upload arbitrary CSV files containing
load profile or meter data and instantly render them as interactive diagrams.

Features:
---------
- Upload one or multiple CSV files.
- Automatic delimiter detection (comma, semicolon, tab) and decimal comma handling (e.g. '12,5').
- Select timestamp and power/load columns.
- Interactive Dark-Theme Plotly time-series diagram with range zoom/pan.
- Instant calculation of key metrics (Peak kW, Total kWh, Average kW, Data point count).
- Data preview table.
========================================================================================
"""

from io import StringIO
import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go

# --------------------------------------------------------------------------------------
# Page Setup & Dark Styling
# --------------------------------------------------------------------------------------
st.set_page_config(
    page_title="CSV Load Profile Visualizer",
    page_icon="📊",
    layout="wide"
)

st.markdown(
    """
    <style>
    .metric-box {
        background-color: #1a1f2c;
        border-radius: 8px;
        padding: 14px 18px;
        border-left: 4px solid #38bdf8;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        margin-bottom: 12px;
    }
    .metric-label {
        font-size: 0.8rem;
        color: #94a3b8;
        text-transform: uppercase;
        font-weight: 600;
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

st.title("📊 CSV Load Profile Visualizer")
st.caption("Upload your load profile CSV files to instantly visualize electrical power curves and analyze energy metrics.")


# --------------------------------------------------------------------------------------
# Helper Functions: CSV Parsing & Column Detection
# --------------------------------------------------------------------------------------
def parse_csv(file) -> pd.DataFrame:
    """Reads a CSV file buffer, handles encoding, delimiters, and skips empty lines."""
    file.seek(0)
    raw_bytes = file.read()
    
    # Try different encodings
    content = None
    for enc in ['utf-8', 'latin1', 'cp1252', 'iso-8859-1']:
        try:
            content = raw_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if content is None:
        content = raw_bytes.decode('utf-8', errors='ignore')

    # Detect header and read
    return pd.read_csv(StringIO(content), sep=None, engine='python')


def auto_detect_columns(cols: list[str]) -> tuple[str, list[str]]:
    """Guesses the timestamp column and power/load columns based on common names."""
    time_keywords = ['time', 'date', 'zeit', 'datum', 'timestamp', 'uhrzeit', 'datetime']
    power_keywords = ['kw', 'power', 'load', 'leistung', 'verbrauch', 'watt', 'kwh', 'consumption']

    time_col = cols[0]
    for c in cols:
        if any(kw in str(c).lower() for kw in time_keywords):
            time_col = c
            break

    power_cols = [c for c in cols if c != time_col and any(kw in str(c).lower() for kw in power_keywords)]
    if not power_cols:
        # Fallback to remaining columns
        power_cols = [c for c in cols if c != time_col]

    return time_col, power_cols


# --------------------------------------------------------------------------------------
# Sidebar: File Upload & Configuration
# --------------------------------------------------------------------------------------
st.sidebar.header("📁 CSV File Upload")

uploaded_files = st.sidebar.file_uploader(
    "Choose CSV file(s):",
    type=["csv", "txt"],
    accept_multiple_files=True,
    help="Upload one or multiple CSV files containing timestamps and power measurements."
)

use_demo = st.sidebar.button("✨ Load Sample Demo CSV", use_container_width=True)

# Generate synthetic demo data if requested
if use_demo or ('demo_loaded' in st.session_state and not uploaded_files):
    st.session_state['demo_loaded'] = True
    dates = pd.date_range(start="2026-06-01 00:00", periods=96 * 7, freq="15min")
    hours = dates.hour
    workdays = dates.dayofweek < 5
    base = 15.0
    power = np.where(workdays & (hours >= 7) & (hours <= 17), base + 65.0, base)
    power = power + np.random.normal(0, 2.5, len(power))
    power = np.clip(power, a_min=5.0, a_max=None)

    demo_df = pd.DataFrame({
        "timestamp": dates.strftime("%Y-%m-%d %H:%M"),
        "Total_Power_kW": np.round(power, 2),
        "Production_Line_kW": np.round(power * 0.7, 2),
        "Lighting_HVAC_kW": np.round(power * 0.3, 2)
    })
    files_to_process = [("Demo_Load_Profile.csv", demo_df)]
elif uploaded_files:
    files_to_process = []
    for f in uploaded_files:
        try:
            parsed = parse_csv(f)
            files_to_process.append((f.name, parsed))
        except Exception as e:
            st.sidebar.error(f"Error reading {f.name}: {e}")
else:
    files_to_process = []


# --------------------------------------------------------------------------------------
# Main Area: When no file is loaded yet
# --------------------------------------------------------------------------------------
if not files_to_process:
    st.info("👋 Upload one or more CSV files in the sidebar, or click **'✨ Load Sample Demo CSV'** to see an immediate demonstration.")
    
    with st.expander("ℹ️ Supported CSV Formats & Tips", expanded=True):
        st.markdown(
            """
            - **Delimiters:** Auto-detected (comma `,`, semicolon `;`, or tab).
            - **Decimals:** Automatically supports both point (`12.5`) and comma decimals (`12,5`).
            - **Columns:** Any CSV containing at least one date/timestamp column and one or more numerical power/load columns (kW, W, or kWh).
            """
        )
    st.stop()


# --------------------------------------------------------------------------------------
# Process and Display Each File
# --------------------------------------------------------------------------------------
for file_name, df_raw in files_to_process:
    st.subheader(f"📄 File: `{file_name}`")
    
    cols = list(df_raw.columns)
    guessed_time, guessed_power = auto_detect_columns(cols)

    # Column Mapping Selectors
    c_map1, c_map2, c_map3 = st.columns([2, 3, 1])
    
    with c_map1:
        time_col = st.selectbox(
            "Timestamp Column:",
            options=cols,
            index=cols.index(guessed_time) if guessed_time in cols else 0,
            key=f"time_{file_name}"
        )
    
    with c_map2:
        power_cols = st.multiselect(
            "Power / Load Column(s):",
            options=[c for c in cols if c != time_col],
            default=[p for p in guessed_power if p in cols and p != time_col],
            key=f"pwr_{file_name}"
        )
    
    with c_map3:
        unit = st.selectbox(
            "Unit:",
            options=["kW", "W", "kWh (15-min)"],
            index=0,
            key=f"unit_{file_name}"
        )

    if not power_cols:
        st.warning("Please select at least one power column to visualize.")
        st.divider()
        continue

    # Clean and parse dataframe
    df_clean = pd.DataFrame()
    df_clean["timestamp"] = pd.to_datetime(df_raw[time_col], errors="coerce")
    df_clean = df_clean.dropna(subset=["timestamp"])

    for p_col in power_cols:
        series = df_raw[p_col]
        # Clean string decimals
        if series.dtype == object:
            series = series.astype(str).str.replace(" ", "").str.replace(",", ".")
        numeric_series = pd.to_numeric(series, errors="coerce").fillna(0.0)

        # Unit conversion to kW
        if unit == "W":
            numeric_series = numeric_series / 1000.0
        elif unit == "kWh (15-min)":
            numeric_series = numeric_series * 4.0  # 15-min kWh * 4 = kW

        df_clean[p_col] = numeric_series

    # Sum of all selected power columns
    df_clean["Total_Demand_kW"] = df_clean[power_cols].sum(axis=1)
    df_clean = df_clean.sort_values("timestamp").reset_index(drop=True)

    # ----------------------------------------------------------------------------------
    # Calculate Key Metrics (KPIs)
    # ----------------------------------------------------------------------------------
    total_series = df_clean["Total_Demand_kW"]
    peak_kw = float(total_series.max())
    min_kw = float(total_series.min())
    avg_kw = float(total_series.mean())
    count = len(df_clean)

    # Calculate duration and total energy
    time_start = df_clean["timestamp"].min()
    time_end = df_clean["timestamp"].max()
    duration_hours = max(0.25, (time_end - time_start).total_seconds() / 3600.0)
    
    # Estimate interval in hours
    if count > 1:
        interval_hours = duration_hours / (count - 1)
    else:
        interval_hours = 0.25

    total_kwh = float(total_series.sum() * interval_hours)
    total_mwh = total_kwh / 1000.0

    # Display KPI Cards
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(
            f"""<div class="metric-box">
                <div class="metric-label">⚡ Peak Demand (P_max)</div>
                <div class="metric-val">{peak_kw:,.1f} kW</div>
                <div class="metric-sub">Min: {min_kw:,.1f} kW</div>
            </div>""",
            unsafe_allow_html=True
        )
    with k2:
        st.markdown(
            f"""<div class="metric-box">
                <div class="metric-label">🔋 Total Energy</div>
                <div class="metric-val">{total_mwh:,.2f} MWh</div>
                <div class="metric-sub">{total_kwh:,.0f} kWh</div>
            </div>""",
            unsafe_allow_html=True
        )
    with k3:
        st.markdown(
            f"""<div class="metric-box">
                <div class="metric-label">📊 Average Power</div>
                <div class="metric-val">{avg_kw:,.1f} kW</div>
                <div class="metric-sub">Across {duration_hours / 24.0:.1f} days</div>
            </div>""",
            unsafe_allow_html=True
        )
    with k4:
        st.markdown(
            f"""<div class="metric-box">
                <div class="metric-label">📋 Data Points</div>
                <div class="metric-val">{count:,}</div>
                <div class="metric-sub">{time_start.strftime('%d.%m.%Y')} – {time_end.strftime('%d.%m.%Y')}</div>
            </div>""",
            unsafe_allow_html=True
        )

    # ----------------------------------------------------------------------------------
    # Interactive Plotly Diagram (Dark Theme)
    # ----------------------------------------------------------------------------------
    fig = go.Figure()
    palette = ["#38BDF8", "#10B981", "#F59E0B", "#EC4899", "#8B5CF6", "#14B8A6", "#F97316"]

    # If multiple sub-columns selected, plot each
    if len(power_cols) > 1:
        for idx, col_name in enumerate(power_cols):
            fig.add_trace(
                go.Scatter(
                    x=df_clean["timestamp"],
                    y=df_clean[col_name],
                    mode="lines",
                    name=col_name,
                    line=dict(width=1.2, color=palette[idx % len(palette)]),
                    hovertemplate=f"<b>{col_name}</b>: %{{y:.2f}} kW<extra></extra>"
                )
            )

    # Main Total Demand Trace
    fig.add_trace(
        go.Scatter(
            x=df_clean["timestamp"],
            y=df_clean["Total_Demand_kW"],
            mode="lines",
            name="Total Demand (kW)",
            line=dict(color="#FFFFFF", width=2.5),
            fill="tozeroy" if len(power_cols) == 1 else "none",
            fillcolor="rgba(56, 189, 248, 0.15)",
            hovertemplate="<b>Total Demand</b>: %{y:.2f} kW<br>Time: %{x}<extra></extra>"
        )
    )

    # Mark Peak Value
    peak_idx = total_series.idxmax()
    peak_timestamp = df_clean.loc[peak_idx, "timestamp"]
    fig.add_annotation(
        x=peak_timestamp,
        y=peak_kw,
        text=f"Peak: {peak_kw:.1f} kW",
        showarrow=True,
        arrowhead=2,
        arrowcolor="#EF4444",
        font=dict(color="#F87171", size=11, family="Arial Black"),
        bgcolor="rgba(15, 23, 42, 0.9)",
        bordercolor="#EF4444",
        borderwidth=1.5,
        borderpad=4
    )

    fig.update_layout(
        template="plotly_dark",
        title=dict(text=f"<b>Load Profile: {file_name}</b>", font=dict(size=16, color="#F8FAFC")),
        xaxis=dict(
            title="Timestamp",
            gridcolor="#1E293B",
            rangeslider=dict(visible=True, thickness=0.06),
            type="date"
        ),
        yaxis=dict(
            title="Active Electrical Power (kW)",
            rangemode="tozero",
            gridcolor="#1E293B"
        ),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=40, r=20, t=50, b=40),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        height=450
    )

    st.plotly_chart(fig, use_container_width=True)

    # Data Table Expander
    with st.expander("🔍 View Cleaned Data Table", expanded=False):
        st.dataframe(df_clean, use_container_width=True, height=250)

    st.divider()
