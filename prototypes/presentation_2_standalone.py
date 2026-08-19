# This File is purely for demonstration purposes
# Feel free to add or change Code at any time
# To Run: python -m streamlit run presentation2.py

"""
========================================================================================
PRESENTATION 2: CSV LOAD PROFILE VISUALIZER & INSPECTOR (presentation2.py)
========================================================================================

Main entry point for the CSV Load Profile Visualizer.
All core business logic, parsers, KPI calculators, and visualizers are modularized
in the `presentation2/` package.
========================================================================================
"""

import sys
import os

# Ensure project root directory is at the front of sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import streamlit as st
import pandas as pd

from presentation2.parser import (
    read_raw_content,
    parse_csv_content,
    detect_suggested_columns,
    generate_sample_demo_csv,
)
from presentation2.processor import process_load_profile_data
from presentation2.metrics import compute_load_profile_kpis
from presentation2.visualizer import create_dark_load_profile_figure

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
    </style>
    """,
    unsafe_allow_html=True
)

st.title("📊 Interactive CSV Inspector & Load Profile Visualizer")
st.caption("Inspect raw uploaded CSV files in a visual preview window, map columns & rows, and visualize electrical power curves.")


# --------------------------------------------------------------------------------------
# Sidebar: File Upload & Sample Loader
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
    demo_name, demo_content = generate_sample_demo_csv(days=7)
    files_to_process = [(demo_name, demo_content)]


# --------------------------------------------------------------------------------------
# Empty State Notice
# --------------------------------------------------------------------------------------
if not files_to_process:
    st.info("👋 Upload a CSV file in the sidebar or click **'✨ Load Sample Demo CSV'** to open the inspector.")
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

    # Step 1: Interactive CSV Preview Window (Vorschaufenster)
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

        st.markdown("**Raw CSV Preview (First 20 Rows):**")
        st.dataframe(df_raw.head(20), use_container_width=True, height=220)

    # Step 2: Column Mapping & Unit Assignment Form
    cols = list(df_raw.columns)
    suggested_time, suggested_power, suggested_unit = detect_suggested_columns(df_raw)

    with st.form(key=f"config_form_{file_name}"):
        st.markdown("### ⚙️ **2. Column Mapping & Unit Assignment**")
        
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

        # Date Parsing Settings & Live Preview
        sample_raw_str = ""
        default_dayfirst = True
        if selected_time_cols:
            import re
            if len(selected_time_cols) == 1:
                sample_raw_str = str(df_raw[selected_time_cols[0]].dropna().iloc[0]) if not df_raw[selected_time_cols[0]].dropna().empty else ""
            else:
                sample_raw_str = " ".join([str(df_raw[c].dropna().iloc[0]) for c in selected_time_cols if not df_raw[c].dropna().empty])
            
            starts_with_year = bool(re.match(r"^\s*\d{4}", sample_raw_str))
            default_dayfirst = not starts_with_year

        date_opt_col1, date_opt_col2 = st.columns([5, 6])
        with date_opt_col1:
            dayfirst_choice = st.toggle(
                "🔄 **Day before month (Day-First / DD.MM)**",
                value=default_dayfirst,
                key=f"dayfirst_{file_name}",
                help="Switch to interpret the date as day-first (DD.MM.YYYY) or month-first (MM.DD.YYYY)."
            )

        with date_opt_col2:
            if sample_raw_str:
                try:
                    parsed_sample = pd.to_datetime(sample_raw_str, dayfirst=dayfirst_choice, errors="coerce")
                    if pd.notnull(parsed_sample):
                        st.caption(f"🗓️ **Datums-Vorschau:** `{sample_raw_str}` ➔ **{parsed_sample.strftime('%d. %B %Y %H:%M')}**")
                    else:
                        st.caption(f"🗓️ **Rohbeispiel:** `{sample_raw_str}`")
                except Exception:
                    st.caption(f"🗓️ **Rohbeispiel:** `{sample_raw_str}`")

        submit_calc = st.form_submit_button(
            "⚡ Calculate Load Profile & Metrics",
            type="primary",
            use_container_width=True
        )

    calc_cache_key = f"calc_data_{file_name}"

    # Step 3: Process Data with Modular Processor
    if submit_calc or calc_cache_key not in st.session_state:
        if not selected_time_cols:
            st.warning("⚠️ Please select at least one column for Timestamp/Date above.")
            st.divider()
            continue

        if not selected_power_cols:
            st.warning("⚠️ Please select at least one numeric meter / power column above.")
            st.divider()
            continue

        try:
            df_clean = process_load_profile_data(
                df_raw=df_raw,
                selected_time_cols=selected_time_cols,
                selected_power_cols=selected_power_cols,
                selected_unit=selected_unit,
                max_rows=int(max_row_limit),
                dayfirst=dayfirst_choice
            )
            kpis = compute_load_profile_kpis(df_clean, power_col="Total_Demand_kW")
            st.session_state[calc_cache_key] = {
                "df_clean": df_clean,
                "kpis": kpis,
                "selected_power_cols": selected_power_cols
            }
        except Exception as e:
            st.error(f"❌ Processing error: {e}")
            st.divider()
            continue

    cached = st.session_state.get(calc_cache_key)
    if cached:
        df_clean = cached["df_clean"]
        kpis = cached["kpis"]
        selected_power_cols = cached["selected_power_cols"]

        # Step 4: Compute KPIs
        st.markdown("### 📈 **3. Energy Metrics & Key Performance Indicators (KPIs)**")
        k1, k2, k3, k4 = st.columns(4)
        with k1:
            st.markdown(
                f"""<div class="metric-box">
                    <div class="metric-label">⚡ Peak Demand (P_max)</div>
                    <div class="metric-val">{kpis.peak_kw:,.1f} kW</div>
                    <div class="metric-sub">Min Baseload: {kpis.min_kw:,.1f} kW</div>
                </div>""",
                unsafe_allow_html=True
            )
        with k2:
            st.markdown(
                f"""<div class="metric-box">
                    <div class="metric-label">🔋 Total Energy</div>
                    <div class="metric-val">{kpis.total_mwh:,.2f} MWh</div>
                    <div class="metric-sub">{kpis.total_kwh:,.0f} kWh</div>
                </div>""",
                unsafe_allow_html=True
            )
        with k3:
            st.markdown(
                f"""<div class="metric-box">
                    <div class="metric-label">📊 Average Power</div>
                    <div class="metric-val">{kpis.avg_kw:,.1f} kW</div>
                    <div class="metric-sub">Across {kpis.duration_days:.1f} days</div>
                </div>""",
                unsafe_allow_html=True
            )
        with k4:
            start_str = kpis.start_date.strftime('%d.%m.%Y %H:%M') if kpis.start_date else ""
            end_str = kpis.end_date.strftime('%d.%m.%Y %H:%M') if kpis.end_date else ""
            st.markdown(
                f"""<div class="metric-box">
                    <div class="metric-label">📋 Parsed Data Points</div>
                    <div class="metric-val">{kpis.data_points_count:,}</div>
                    <div class="metric-sub">{start_str} – {end_str}</div>
                </div>""",
                unsafe_allow_html=True
            )

        # Step 5: Render Dark Theme Plotly Diagram
        st.markdown("### 📊 **4. Interactive Load Profile Curve**")
        fig = create_dark_load_profile_figure(
            df_clean=df_clean,
            file_name=file_name,
            selected_power_cols=selected_power_cols,
            total_col="Total_Demand_kW",
            peak_kw=kpis.peak_kw
        )
        st.plotly_chart(fig, use_container_width=True)

        # Step 6: Processed Clean Data Table Preview
        with st.expander("📋 **5. Processed & Cleaned Data Table (Export Ready)**", expanded=False):
            st.dataframe(df_clean, use_container_width=True, height=250)

    st.divider()
