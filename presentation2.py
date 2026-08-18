# This File is purely for demonstration purposes
# Feel free to add or change Code at any time
# To Run: python -m streamlit run presentation2.py

"""
========================================================================================
PRESENTATION 2: MULTI-COLUMN CSV LOAD PROFILE UPLOADER & VISUALIZER (presentation2.py)
========================================================================================

Purpose & Scope:
----------------
A flexible and robust CSV reader allowing the user to map arbitrary columns manually
or with smart heuristics.

Key Features:
-------------
1. Multi-Column Timestamp Mapping:
   - Allows selecting one OR multiple timestamp columns (e.g. ['#', 'CODE'] or ['Date', 'Time']).
   - Automatically merges multiple selected columns into a unified datetime series.
2. Custom Power/Meter Column Assignment:
   - Full manual control to select one or multiple measurement/sub-meter columns.
3. Unit & Interval Conversion:
   - 'kWh (15-min interval) → kW' (multiplies by 4).
   - 'kW (Active Power - Direct)'.
   - 'W (Watt) → kW' (divides by 1,000).
   - 'kWh (Hourly) → kW'.
4. European Date Format:
   - Parses DD.MM.YYYY and DD/MM/YYYY reliably (`dayfirst=True`).
5. Interactive Dark Theme Plotly Charts with Range Zoom and KPI Metrics.
========================================================================================
"""

from io import StringIO
import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go

# --------------------------------------------------------------------------------------
# Page Setup & Dark Theme Styling
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

st.title("📊 Multi-Column CSV Load Profile Visualizer")
st.caption("Upload any CSV load profile and flexibly assign Date, Time, and Power measurement columns.")


# --------------------------------------------------------------------------------------
# Smart Parser & Heuristic Column Detection
# --------------------------------------------------------------------------------------
DATE_SYNONYMS = ['#', 'datum', 'date', 'zeit', 'timestamp', 'datetime', 'zeitstempel']
TIME_SYNONYMS = ['code', 'uhrzeit', 'time', 'time_of_day', 'tod', 'intervall', 'stunde', 'hour']
UNIT_SYNONYMS = ['eenheid', 'unit', 'einheit', 'status', 'valid', 'type']


def parse_csv_file(file) -> pd.DataFrame:
    """Reads CSV with automatic encoding fallback and delimiter sniffing."""
    file.seek(0)
    raw_bytes = file.read()
    
    content = None
    for enc in ['utf-8', 'latin1', 'cp1252', 'iso-8859-1']:
        try:
            content = raw_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if content is None:
        content = raw_bytes.decode('utf-8', errors='ignore')

    lines = content.splitlines()
    skip = 0
    for idx, l in enumerate(lines[:10]):
        stripped = l.strip()
        if not stripped or stripped.startswith(';;') or (stripped.startswith('#') and ';' in stripped and len(stripped.split(';')) < 2):
            skip = idx + 1
        else:
            break

    return pd.read_csv(StringIO(content), sep=None, engine='python', skiprows=skip)


def detect_suggested_columns(df: pd.DataFrame):
    """
    Returns initial intelligent guesses for:
      - suggested_time_cols: List of 1 or 2 columns (e.g. ['#', 'CODE'] or ['timestamp'])
      - suggested_power_cols: List of numeric measurement columns (excluding text/units)
      - suggested_unit: 'kWh (15-min interval) → kW' or 'kW'
    """
    cols = list(df.columns)
    time_cols = []
    power_cols = []
    suggested_unit = "kW (Active Power - Direct)"

    # 1. Look for Date Column
    date_col = None
    for c in cols:
        c_clean = str(c).strip().lower()
        if any(syn == c_clean or syn in c_clean for syn in DATE_SYNONYMS):
            date_col = c
            time_cols.append(c)
            break

    # 2. Look for separate Time-of-Day Column (e.g. 'CODE', 'Uhrzeit')
    for c in cols:
        if c == date_col:
            continue
        c_clean = str(c).strip().lower()
        if any(syn == c_clean for syn in TIME_SYNONYMS):
            time_cols.append(c)
            break

    if not time_cols and cols:
        time_cols = [cols[0]]

    # 3. Check for unit indicators (e.g. 'Eenheid' column containing 'kWh')
    for c in cols:
        c_clean = str(c).strip().lower()
        if any(u in c_clean for u in UNIT_SYNONYMS):
            sample_val = str(df[c].dropna().iloc[0]).lower() if not df[c].dropna().empty else ""
            if "kwh" in sample_val:
                suggested_unit = "kWh (15-min interval) → kW"
            elif "w" == sample_val:
                suggested_unit = "W (Watt) → kW"

    # 4. Filter power columns: find columns with numeric content
    for c in cols:
        if c in time_cols:
            continue
        c_clean = str(c).strip().lower()
        # Skip unit/status columns
        if any(u in c_clean for u in UNIT_SYNONYMS):
            continue
        
        # Test if column has numeric values
        col_clean_str = df[c].astype(str).str.replace(' ', '').str.replace(',', '.')
        valid_numeric = pd.to_numeric(col_clean_str, errors='coerce').notnull().sum()
        if valid_numeric > (0.5 * len(df)):
            power_cols.append(c)

    return time_cols, power_cols, suggested_unit


# --------------------------------------------------------------------------------------
# Sidebar: File Upload & Demo Loader
# --------------------------------------------------------------------------------------
# Sidebar file upload controls
uploaded_files = st.sidebar.file_uploader(
    "Upload Load Profile CSV(s):",
    type=["csv", "txt"],
    accept_multiple_files=True,
    help="Upload one or multiple CSV files. Single or split Date/Time columns are supported."
)

if uploaded_files:
    # If user uploads real files, clear demo state
    st.session_state['demo_loaded'] = False

use_demo = st.sidebar.button("✨ Load Sample Demo CSV", use_container_width=True)

if 'demo_loaded' in st.session_state and st.session_state['demo_loaded'] and not uploaded_files:
    if st.sidebar.button("❌ Unload Demo Data", use_container_width=True):
        st.session_state['demo_loaded'] = False
        st.rerun()

files_to_process = []

if uploaded_files:
    for f in uploaded_files:
        try:
            parsed = parse_csv_file(f)
            files_to_process.append((f.name, parsed))
        except Exception as e:
            st.sidebar.error(f"Error reading {f.name}: {e}")

elif use_demo or ('demo_loaded' in st.session_state and st.session_state['demo_loaded']):
    st.session_state['demo_loaded'] = True
    dates = pd.date_range(start="2024-01-01 00:00", periods=96 * 7, freq="15min")
    hours = dates.hour
    workdays = dates.dayofweek < 5
    base = 2.0
    energy_kwh = np.where(workdays & (hours >= 7) & (hours <= 17), base + 6.0, base)
    energy_kwh = np.round(np.clip(energy_kwh + np.random.normal(0, 0.4, len(energy_kwh)), 0.5, None), 2)

    demo_df = pd.DataFrame({
        "#": dates.strftime("%d.%m.%Y"),
        "CODE": dates.strftime("%H:%M"),
        "Eenheid": "kWh",
        "871687400008864731MV": energy_kwh
    })
    files_to_process = [("Sample_Synthetic_Demo_Data.csv", demo_df)]


# --------------------------------------------------------------------------------------
# Empty State Notice
# --------------------------------------------------------------------------------------
if not files_to_process:
    st.info("👋 Upload your CSV file(s) in the sidebar or click **'✨ Load Sample Demo CSV'** to begin.")
    with st.expander("💡 How Column Mapping Works", expanded=True):
        st.markdown(
            """
            - **Split Date & Time:** You can select **multiple columns** in the Timestamp selector (e.g. `['#', 'CODE']` or `['Date', 'Time']`). The system merges them automatically!
            - **Measurement Column(s):** Choose one or multiple meter columns to display.
            - **15-Min Energy Conversion:** If your meter records `kWh` in 15-minute intervals, select `kWh (15-min interval) → kW` to convert energy ($2\\text{ kWh}$) into average electrical power ($8\\text{ kW}$).
            """
        )
    st.stop()


# --------------------------------------------------------------------------------------
# Process Each Uploaded File with Flexible User Column Mapping
# --------------------------------------------------------------------------------------
for file_name, df_raw in files_to_process:
    st.subheader(f"📄 File: `{file_name}`")

    cols = list(df_raw.columns)
    suggested_time, suggested_power, suggested_unit = detect_suggested_columns(df_raw)

    # Interactive Column Mapping Controls
    map_col1, map_col2, map_col3 = st.columns([4, 4, 3])

    with map_col1:
        selected_time_cols = st.multiselect(
            "📅 Timestamp Column(s) (Select 1 or more):",
            options=cols,
            default=[c for c in suggested_time if c in cols],
            key=f"time_cols_{file_name}",
            help="Select one column (if Date+Time are combined) OR select multiple columns (e.g. Date '#' and Time 'CODE') to merge them."
        )

    with map_col2:
        selected_power_cols = st.multiselect(
            "⚡ Power / Meter Measurement Column(s):",
            options=cols,
            default=[c for c in suggested_power if c in cols],
            key=f"pwr_cols_{file_name}",
            help="Select one or multiple numeric meter columns (exclude text/unit columns like 'Eenheid')."
        )

    with map_col3:
        unit_options = [
            "kWh (15-min interval) → kW",
            "kW (Active Power - Direct)",
            "W (Watt) → kW",
            "kWh (Hourly interval) → kW"
        ]
        unit_idx = unit_options.index(suggested_unit) if suggested_unit in unit_options else 0
        selected_unit = st.selectbox(
            "📊 Unit & Conversion:",
            options=unit_options,
            index=unit_idx,
            key=f"unit_sel_{file_name}",
            help="Example: 2 kWh in a 15-minute interval = 8 kW active power."
        )

    # Validation Checks
    if not selected_time_cols:
        st.warning("⚠️ Please select at least one column for Timestamp/Date.")
        st.divider()
        continue

    if not selected_power_cols:
        st.warning("⚠️ Please select at least one numeric meter / power column.")
        st.divider()
        continue

    # ----------------------------------------------------------------------------------
    # Step 1: Merge Selected Timestamp Column(s) & Parse Datetime
    # ----------------------------------------------------------------------------------
    df_clean = pd.DataFrame()

    if len(selected_time_cols) == 1:
        raw_ts_series = df_raw[selected_time_cols[0]].astype(str).str.strip()
    else:
        # Concatenate multiple columns (e.g. Date + Time) with space
        raw_ts_series = df_raw[selected_time_cols].astype(str).agg(' '.join, axis=1)

    df_clean["timestamp"] = pd.to_datetime(raw_ts_series, dayfirst=True, errors="coerce")
    
    # Check for invalid timestamp rows
    valid_mask = df_clean["timestamp"].notnull()
    invalid_count = int((~valid_mask).sum())
    df_clean = df_clean[valid_mask].copy()

    if df_clean.empty:
        st.error("❌ Could not parse any valid timestamps with the selected column(s). Please verify your selection.")
        st.divider()
        continue

    # ----------------------------------------------------------------------------------
    # Step 2: Clean and Convert Power Measurement Columns
    # ----------------------------------------------------------------------------------
    for p_col in selected_power_cols:
        series = df_raw.loc[valid_mask, p_col]
        if series.dtype == object:
            series = series.astype(str).str.replace(" ", "").str.replace(",", ".")
        numeric_series = pd.to_numeric(series, errors="coerce").fillna(0.0)

        # Apply Unit Conversion
        if "15-min" in selected_unit:
            # 15-min kWh * 4 = kW
            numeric_series = numeric_series * 4.0
        elif "Hourly" in selected_unit:
            numeric_series = numeric_series * 1.0
        elif "Watt" in selected_unit:
            numeric_series = numeric_series / 1000.0

        df_clean[p_col] = numeric_series

    # Sum total demand across all selected meter columns
    df_clean["Total_Demand_kW"] = df_clean[selected_power_cols].sum(axis=1)
    df_clean = df_clean.sort_values("timestamp").reset_index(drop=True)

    # ----------------------------------------------------------------------------------
    # Step 3: Compute Key Performance Indicators (KPIs)
    # ----------------------------------------------------------------------------------
    total_series = df_clean["Total_Demand_kW"]
    peak_kw = float(total_series.max())
    min_kw = float(total_series.min())
    avg_kw = float(total_series.mean())
    count = len(df_clean)

    t_start = df_clean["timestamp"].min()
    t_end = df_clean["timestamp"].max()
    duration_days = max(1.0, (t_end - t_start).total_seconds() / 86400.0)

    # Interval resolution in hours
    if count > 1:
        dt_seconds = (df_clean["timestamp"].iloc[1] - df_clean["timestamp"].iloc[0]).total_seconds()
        hours_per_step = (dt_seconds / 3600.0) if dt_seconds > 0 else 0.25
    else:
        hours_per_step = 0.25

    total_kwh = float(total_series.sum() * hours_per_step)
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
                <div class="metric-sub">Across {duration_days:.1f} days</div>
            </div>""",
            unsafe_allow_html=True
        )
    with k4:
        st.markdown(
            f"""<div class="metric-box">
                <div class="metric-label">📋 Data Points</div>
                <div class="metric-val">{count:,}</div>
                <div class="metric-sub">{t_start.strftime('%d.%m.%Y %H:%M')} – {t_end.strftime('%d.%m.%Y %H:%M')}</div>
            </div>""",
            unsafe_allow_html=True
        )

    # ----------------------------------------------------------------------------------
    # Step 4: Interactive Plotly Diagram
    # ----------------------------------------------------------------------------------
    fig = go.Figure()
    palette = ["#38BDF8", "#10B981", "#F59E0B", "#EC4899", "#8B5CF6", "#14B8A6"]

    # Sub-meter traces if multiple selected
    if len(selected_power_cols) > 1:
        for idx, col_name in enumerate(selected_power_cols):
            fig.add_trace(
                go.Scatter(
                    x=df_clean["timestamp"],
                    y=df_clean[col_name],
                    mode="lines",
                    name=col_name,
                    line=dict(width=1.0, color=palette[idx % len(palette)]),
                    hovertemplate=f"<b>{col_name}</b>: %{{y:.2f}} kW<extra></extra>"
                )
            )

    # Total Grid Demand Trace
    fig.add_trace(
        go.Scatter(
            x=df_clean["timestamp"],
            y=df_clean["Total_Demand_kW"],
            mode="lines",
            name="Total Grid Demand (kW)",
            line=dict(color="#FFFFFF", width=2.0),
            fill="tozeroy" if len(selected_power_cols) == 1 else "none",
            fillcolor="rgba(56, 189, 248, 0.15)",
            hovertemplate="<b>Power</b>: %{y:.2f} kW<br>Time: %{x}<extra></extra>"
        )
    )

    # Peak Annotation
    peak_idx = total_series.idxmax()
    peak_time = df_clean.loc[peak_idx, "timestamp"]
    fig.add_annotation(
        x=peak_time,
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
        height=470
    )

    st.plotly_chart(fig, use_container_width=True)

    # Cleaned Data Preview Table
    with st.expander("🔍 View Cleaned Data Preview (First 50 Rows)", expanded=False):
        st.dataframe(df_clean.head(50), use_container_width=True, height=250)

    st.divider()
