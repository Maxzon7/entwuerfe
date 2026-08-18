# This File is purely for demonstration purposes
# Feel free to add or change Code at any time
# To Run: python -m streamlit run presentation2.py

"""
========================================================================================
PRESENTATION 2: INTERACTIVE CSV INSPECTOR & LOAD PROFILE VISUALIZER (presentation2.py)
========================================================================================

Purpose & Scope:
----------------
A visual, interactive CSV reader with an embedded File Inspector / Preview Window
allowing you to:
1. Inspect the raw uploaded CSV file in a live data table preview.
2. Select header rows, skip metadata lines, or filter row ranges.
3. Flexibly assign multiple timestamp columns (e.g. Date + Time) and measurement columns.
4. Preview the cleaned & converted values side-by-side in real time.
5. Render dark-theme interactive Plotly load profile charts and core KPIs.
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
    page_title="CSV Load Profile Visualizer & Inspector",
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
    .preview-container {
        background-color: #0f172a;
        border: 1px solid #334155;
        border-radius: 8px;
        padding: 16px;
        margin-bottom: 20px;
    }
    </style>
    """,
    unsafe_allow_html=True
)

st.title("📊 Interactive CSV Inspector & Load Profile Visualizer")
st.caption("Inspect raw uploaded CSV files in a visual preview window, map columns & rows, and visualize electrical power curves.")


# --------------------------------------------------------------------------------------
# Smart Parser & Heuristic Column Detection
# --------------------------------------------------------------------------------------
DATE_SYNONYMS = ['#', 'datum', 'date', 'zeit', 'timestamp', 'datetime', 'zeitstempel']
TIME_SYNONYMS = ['code', 'uhrzeit', 'time', 'time_of_day', 'tod', 'intervall', 'stunde', 'hour']
UNIT_SYNONYMS = ['eenheid', 'unit', 'einheit', 'status', 'valid', 'type']


def read_raw_content(file) -> str:
    """Reads raw string content handling multiple common encodings."""
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
    return content


def parse_csv_content(content: str, skiprows: int = 0) -> pd.DataFrame:
    """Parses raw text content into a pandas DataFrame with specified skiprows."""
    return pd.read_csv(StringIO(content), sep=None, engine='python', skiprows=skiprows)


def detect_suggested_columns(df: pd.DataFrame):
    """Detects initial recommendations for date, time, and measurement columns."""
    cols = list(df.columns)
    time_cols = []
    power_cols = []
    suggested_unit = "kW (Active Power - Direct)"

    # 1. Date Column
    date_col = None
    for c in cols:
        c_clean = str(c).strip().lower()
        if any(syn == c_clean or syn in c_clean for syn in DATE_SYNONYMS):
            date_col = c
            time_cols.append(c)
            break

    # 2. Time-of-Day Column (e.g. 'CODE', 'Uhrzeit')
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

    # 4. Measurement Columns
    for c in cols:
        if c in time_cols:
            continue
        c_clean = str(c).strip().lower()
        if any(u in c_clean for u in UNIT_SYNONYMS):
            continue
        col_clean_str = df[c].astype(str).str.replace(' ', '').str.replace(',', '.')
        valid_numeric = pd.to_numeric(col_clean_str, errors='coerce').notnull().sum()
        if valid_numeric > (0.4 * len(df)):
            power_cols.append(c)

    return time_cols, power_cols, suggested_unit


# --------------------------------------------------------------------------------------
# Sidebar: File Upload & Demo Loader
# --------------------------------------------------------------------------------------
st.sidebar.header("📁 CSV File Upload")

uploaded_files = st.sidebar.file_uploader(
    "Upload Load Profile CSV(s):",
    type=["csv", "txt"],
    accept_multiple_files=True,
    help="Upload your CSV files to inspect and visualize."
)

if uploaded_files:
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
            content = read_raw_content(f)
            files_to_process.append((f.name, content))
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
    buf = StringIO()
    demo_df.to_csv(buf, index=False, sep=";")
    files_to_process = [("Sample_Synthetic_Demo_Data.csv", buf.getvalue())]


# --------------------------------------------------------------------------------------
# Empty State Notice
# --------------------------------------------------------------------------------------
if not files_to_process:
    st.info("👋 Upload a CSV file in the sidebar to open the **Interactive CSV Preview & Inspector Window**.")
    with st.expander("💡 Features of the Preview Window", expanded=True):
        st.markdown(
            """
            - **Raw Table Inspector:** Look directly into the uploaded CSV data and inspect all column headers and sample rows.
            - **Header Row Selection:** Skip top metadata lines or choose the exact header row.
            - **Multi-Column Timestamp:** Select one or multiple columns (e.g. `#` for Date and `CODE` for Time) to merge them.
            - **Row Range Filter:** Limit the analysis to specific row indices or date ranges.
            - **Unit Multipliers:** Convert 15-minute interval energy ($2\\text{ kWh}$) to active power ($8\\text{ kW}$) with one click.
            """
        )
    st.stop()


# --------------------------------------------------------------------------------------
# Process Each Uploaded File with Interactive Preview Window
# --------------------------------------------------------------------------------------
for file_name, raw_csv_text in files_to_process:
    st.markdown(f"## 📄 File: `{file_name}`")

    # ----------------------------------------------------------------------------------
    # Step 1: Interactive CSV Preview Window (Vorschaufenster)
    # ----------------------------------------------------------------------------------
    with st.expander("🔍 **1. CSV Preview & Table Inspector**", expanded=True):
        st.markdown("Inspect raw file content and configure header / row limits before processing:")
        
        col_opt1, col_opt2, col_opt3 = st.columns([2, 2, 2])
        
        with col_opt1:
            skip_header_rows = st.number_input(
                "Skip Metadata Rows (Top):",
                min_value=0,
                max_value=50,
                value=0,
                step=1,
                key=f"skip_{file_name}",
                help="Number of metadata comment rows to skip before column headers."
            )
        
        # Parse preview with current skip rows
        try:
            df_raw = parse_csv_content(raw_csv_text, skiprows=int(skip_header_rows))
        except Exception as e:
            st.error(f"Error parsing CSV preview: {e}")
            st.divider()
            continue

        total_file_rows = len(df_raw)
        
        with col_opt2:
            max_row_limit = st.number_input(
                f"Row Limit (Total: {total_file_rows:,} rows):",
                min_value=10,
                max_value=max(1000, total_file_rows),
                value=total_file_rows,
                step=500,
                key=f"limit_{file_name}",
                help="Optional limit to load only the first N rows for quick inspection."
            )

        with col_opt3:
            st.markdown(f"**Total Columns:** `{len(df_raw.columns)}`  \n**Total Rows:** `{total_file_rows:,}`")

        # Display Raw Data Table Preview
        st.markdown("**Raw CSV Preview (First 20 Rows):**")
        st.dataframe(df_raw.head(20), use_container_width=True, height=220)

    # ----------------------------------------------------------------------------------
    # Step 2: Column Assignment & Unit Configuration
    # ----------------------------------------------------------------------------------
    st.markdown("### ⚙️ **2. Column Mapping & Unit Assignment**")
    
    cols = list(df_raw.columns)
    suggested_time, suggested_power, suggested_unit = detect_suggested_columns(df_raw)

    map_col1, map_col2, map_col3 = st.columns([4, 4, 3])

    with map_col1:
        selected_time_cols = st.multiselect(
            "📅 Timestamp Column(s) (Select 1 or more):",
            options=cols,
            default=[c for c in suggested_time if c in cols],
            key=f"time_cols_{file_name}",
            help="Select Date and/or Time columns. Multiple columns (e.g. '#' + 'CODE') will be merged automatically."
        )

    with map_col2:
        selected_power_cols = st.multiselect(
            "⚡ Power / Meter Column(s):",
            options=cols,
            default=[c for c in suggested_power if c in cols],
            key=f"pwr_cols_{file_name}",
            help="Select one or multiple measurement columns (exclude text columns like 'Eenheid')."
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
            help="15-min kWh * 4 = kW active power."
        )

    if not selected_time_cols:
        st.warning("⚠️ Please select at least one column for Timestamp/Date above.")
        st.divider()
        continue

    if not selected_power_cols:
        st.warning("⚠️ Please select at least one numeric meter / power column above.")
        st.divider()
        continue

    # Apply row slice limit if set
    df_sliced = df_raw.iloc[:int(max_row_limit)].copy()

    # ----------------------------------------------------------------------------------
    # Step 3: Combine Timestamp & Clean Numeric Power Series
    # ----------------------------------------------------------------------------------
    df_clean = pd.DataFrame()

    if len(selected_time_cols) == 1:
        raw_ts_series = df_sliced[selected_time_cols[0]].astype(str).str.strip()
    else:
        raw_ts_series = df_sliced[selected_time_cols].astype(str).agg(' '.join, axis=1)

    df_clean["timestamp"] = pd.to_datetime(raw_ts_series, dayfirst=True, errors="coerce")
    valid_mask = df_clean["timestamp"].notnull()
    df_clean = df_clean[valid_mask].copy()

    if df_clean.empty:
        st.error("❌ Could not parse valid timestamps with the selected column(s). Check date format or column selection.")
        st.divider()
        continue

    for p_col in selected_power_cols:
        series = df_sliced.loc[valid_mask, p_col]
        if series.dtype == object:
            series = series.astype(str).str.replace(" ", "").str.replace(",", ".")
        numeric_series = pd.to_numeric(series, errors="coerce").fillna(0.0)

        # Unit Conversion
        if "15-min" in selected_unit:
            numeric_series = numeric_series * 4.0
        elif "Hourly" in selected_unit:
            numeric_series = numeric_series * 1.0
        elif "Watt" in selected_unit:
            numeric_series = numeric_series / 1000.0

        df_clean[p_col] = numeric_series

    df_clean["Total_Demand_kW"] = df_clean[selected_power_cols].sum(axis=1)
    df_clean = df_clean.sort_values("timestamp").reset_index(drop=True)

    # ----------------------------------------------------------------------------------
    # Step 4: Key Metrics (KPIs)
    # ----------------------------------------------------------------------------------
    total_series = df_clean["Total_Demand_kW"]
    peak_kw = float(total_series.max())
    min_kw = float(total_series.min())
    avg_kw = float(total_series.mean())
    count = len(df_clean)

    t_start = df_clean["timestamp"].min()
    t_end = df_clean["timestamp"].max()
    duration_days = max(1.0, (t_end - t_start).total_seconds() / 86400.0)

    if count > 1:
        dt_seconds = (df_clean["timestamp"].iloc[1] - df_clean["timestamp"].iloc[0]).total_seconds()
        hours_per_step = (dt_seconds / 3600.0) if dt_seconds > 0 else 0.25
    else:
        hours_per_step = 0.25

    total_kwh = float(total_series.sum() * hours_per_step)
    total_mwh = total_kwh / 1000.0

    st.markdown("### 📈 **3. Energy Metrics & Key Performance Indicators (KPIs)**")
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(
            f"""<div class="metric-box">
                <div class="metric-label">⚡ Peak Demand (P_max)</div>
                <div class="metric-val">{peak_kw:,.1f} kW</div>
                <div class="metric-sub">Min Baseload: {min_kw:,.1f} kW</div>
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
                <div class="metric-label">📋 Parsed Data Points</div>
                <div class="metric-val">{count:,}</div>
                <div class="metric-sub">{t_start.strftime('%d.%m.%Y %H:%M')} – {t_end.strftime('%d.%m.%Y %H:%M')}</div>
            </div>""",
            unsafe_allow_html=True
        )

    # ----------------------------------------------------------------------------------
    # Step 5: Interactive Dark Plotly Diagram
    # ----------------------------------------------------------------------------------
    st.markdown("### 📊 **4. Interactive Load Profile Curve**")
    fig = go.Figure()
    palette = ["#38BDF8", "#10B981", "#F59E0B", "#EC4899", "#8B5CF6", "#14B8A6"]

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

    # ----------------------------------------------------------------------------------
    # Step 6: Processed Clean Data Table & CSV Download
    # ----------------------------------------------------------------------------------
    with st.expander("📋 **5. Processed & Cleaned Data Table (Export Ready)**", expanded=False):
        st.dataframe(df_clean, use_container_width=True, height=250)

    st.divider()
