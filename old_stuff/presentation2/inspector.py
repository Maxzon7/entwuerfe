"""
Presentation2 UI Inspector Component
====================================
Reusable Streamlit UI component for uploading, parsing, scaling,
and visualizing arbitrary CSV load profile data.
"""

import re
import streamlit as st
import pandas as pd
import numpy as np

from .parser import read_raw_content, parse_csv_content, detect_suggested_columns, generate_sample_demo_csv
from .processor import process_load_profile_data
from .metrics import compute_load_profile_kpis
from .visualizer import create_dark_load_profile_figure


def render_csv_inspector(key_prefix: str = "csv_inspector"):
    """
    Renders the interactive CSV Load Profile Inspector component.
    """
    st.subheader("1. CSV Data Ingestion & Demo Data")

    col_up, col_demo = st.columns([5, 2])
    with col_up:
        uploaded_files = st.file_uploader(
            "Upload Load Profile CSV(s):",
            type=["csv", "txt"],
            accept_multiple_files=True,
            key=f"{key_prefix}_uploader"
        )
    with col_demo:
        st.write("")
        st.write("")
        if st.session_state.get(f"{key_prefix}_demo_loaded"):
            if st.button("🔄 Reset / Reload Demo Data", key=f"{key_prefix}_reload_btn", use_container_width=True):
                keys_to_clear = [k for k in st.session_state if k.startswith(key_prefix)]
                for k in keys_to_clear:
                    del st.session_state[k]
                st.session_state[f"{key_prefix}_demo_loaded"] = True
                st.rerun()
        else:
            if st.button("Load 15-Min Demo CSV", key=f"{key_prefix}_demo_btn", use_container_width=True):
                keys_to_clear = [k for k in st.session_state if k.startswith(key_prefix)]
                for k in keys_to_clear:
                    del st.session_state[k]
                st.session_state[f"{key_prefix}_demo_loaded"] = True
                st.rerun()

    files_to_process = []
    if uploaded_files:
        st.session_state[f"{key_prefix}_demo_loaded"] = False
        for f in uploaded_files:
            try:
                content = read_raw_content(f)
                files_to_process.append((f.name, content))
            except Exception as e:
                st.error(f"Error reading {f.name}: {e}")
    elif st.session_state.get(f"{key_prefix}_demo_loaded"):
        demo_name, demo_content = generate_sample_demo_csv(days=14)
        files_to_process = [(demo_name, demo_content)]

    if not files_to_process:
        st.info("Upload a CSV file above or click **'Load 15-Min Demo CSV'** to begin inspecting meter data.")
        return None

    for file_name, raw_csv_text in files_to_process:
        st.caption(f"Active Dataset: **{file_name}**")

        with st.expander("🔍 **CSV Preview & Table Inspector**", expanded=False):
            skip_header_rows = st.number_input(
                "Skip Header Rows:",
                min_value=0, max_value=50, value=0, step=1,
                key=f"{key_prefix}_skip_{file_name}"
            )
            df_raw = parse_csv_content(raw_csv_text, skiprows=int(skip_header_rows))
            st.markdown(f"**Rows:** `{len(df_raw):,}` | **Columns:** `{len(df_raw.columns)}`")
            st.dataframe(df_raw.head(15), use_container_width=True, height=200)

        if "df_raw" not in locals():
            df_raw = parse_csv_content(raw_csv_text, skiprows=0)

        cols = list(df_raw.columns)
        suggested_time, suggested_power, suggested_unit = detect_suggested_columns(df_raw)

        with st.form(key=f"{key_prefix}_form_{file_name}"):
            st.subheader("2. Column Mapping & Unit Assignment")
            map_col1, map_col2, map_col3 = st.columns([4, 4, 3])

            with map_col1:
                selected_time_cols = st.multiselect(
                    "📅 Timestamp Column(s):",
                    options=cols,
                    default=[c for c in suggested_time if c in cols],
                    key=f"{key_prefix}_time_{file_name}"
                )

            with map_col2:
                selected_power_cols = st.multiselect(
                    "⚡ Power / Meter Column(s):",
                    options=cols,
                    default=[c for c in suggested_power if c in cols],
                    key=f"{key_prefix}_pwr_{file_name}"
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
                    "📊 Unit Conversion:",
                    options=unit_options,
                    index=unit_idx,
                    key=f"{key_prefix}_unit_{file_name}"
                )

            sample_raw_str = ""
            default_dayfirst = True
            if selected_time_cols:
                if len(selected_time_cols) == 1:
                    sample_raw_str = str(df_raw[selected_time_cols[0]].dropna().iloc[0]) if not df_raw[selected_time_cols[0]].dropna().empty else ""
                else:
                    sample_raw_str = " ".join([str(df_raw[c].dropna().iloc[0]) for c in selected_time_cols if not df_raw[c].dropna().empty])
                starts_with_year = bool(re.match(r"^\s*\d{4}", sample_raw_str))
                default_dayfirst = not starts_with_year

            date_opt_col1, date_opt_col2 = st.columns([5, 6])
            with date_opt_col1:
                dayfirst_choice = st.toggle(
                    "🔄 **Day-First Date Format (DD.MM)**",
                    value=default_dayfirst,
                    key=f"{key_prefix}_dayfirst_{file_name}"
                )

            with date_opt_col2:
                if sample_raw_str:
                    try:
                        parsed_sample = pd.to_datetime(sample_raw_str, dayfirst=dayfirst_choice, errors="coerce")
                        if pd.notnull(parsed_sample):
                            st.caption(f"🗓️ Preview: `{sample_raw_str}` ➔ **{parsed_sample.strftime('%d %b %Y %H:%M')}**")
                    except Exception:
                        pass

            submit_calc = st.form_submit_button("⚡ Calculate Load Profile & Metrics", type="primary", use_container_width=True)

        calc_cache_key = f"{key_prefix}_calc_data_{file_name}"

        if submit_calc or calc_cache_key not in st.session_state:
            if not selected_time_cols or not selected_power_cols:
                st.warning("Please select at least one timestamp column and one power column.")
                continue

            df_clean = process_load_profile_data(
                df_raw=df_raw,
                selected_time_cols=selected_time_cols,
                selected_power_cols=selected_power_cols,
                selected_unit=selected_unit,
                max_rows=len(df_raw),
                dayfirst=dayfirst_choice
            )
            kpis = compute_load_profile_kpis(df_clean, power_col="Total_Demand_kW")
            st.session_state[calc_cache_key] = {
                "df_clean": df_clean,
                "kpis": kpis,
                "selected_power_cols": selected_power_cols
            }

        cached = st.session_state.get(calc_cache_key)
        if cached:
            df_clean = cached["df_clean"]
            kpis = cached["kpis"]
            selected_power_cols = cached["selected_power_cols"]

            st.subheader("3. Energy Metrics & Key Performance Indicators")
            k1, k2, k3, k4 = st.columns(4)
            with k1:
                st.markdown(
                    f"""<div class="sandbox-card">
                        <div class="sandbox-title">⚡ Peak Demand (P_max)</div>
                        <div class="sandbox-value">{kpis.peak_kw:,.1f} kW</div>
                    </div>""",
                    unsafe_allow_html=True
                )
            with k2:
                st.markdown(
                    f"""<div class="sandbox-card">
                        <div class="sandbox-title">🔋 Total Energy</div>
                        <div class="sandbox-value">{kpis.total_mwh:,.2f} MWh</div>
                    </div>""",
                    unsafe_allow_html=True
                )
            with k3:
                st.markdown(
                    f"""<div class="sandbox-card">
                        <div class="sandbox-title">📊 Average Power</div>
                        <div class="sandbox-value">{kpis.avg_kw:,.1f} kW</div>
                    </div>""",
                    unsafe_allow_html=True
                )
            with k4:
                start_str = kpis.start_date.strftime('%d.%m.%Y %H:%M') if kpis.start_date else ""
                end_str = kpis.end_date.strftime('%d.%m.%Y %H:%M') if kpis.end_date else ""
                st.markdown(
                    f"""<div class="sandbox-card">
                        <div class="sandbox-title">📋 Data Points</div>
                        <div class="sandbox-value">{kpis.data_points_count:,}</div>
                    </div>""",
                    unsafe_allow_html=True
                )

            # Grid Limit Settings for CSV Mode
            st.subheader("⚡ Grid Capacity Limit & Peak Shaving Setup")
            g_col1, g_col2, g_col3 = st.columns([4, 4, 4])
            with g_col1:
                enable_grid_limit = st.toggle("Enable Grid Capacity Limit Monitoring", value=False, key=f"{key_prefix}_grid_toggle_{file_name}")
            with g_col2:
                if enable_grid_limit:
                    grid_limit_kw = st.number_input("Max Grid Capacity Limit (kW):", min_value=5.0, max_value=5000.0, value=float(np.round(kpis.peak_kw * 0.8, 0)), step=5.0, key=f"{key_prefix}_limit_val_{file_name}")
                else:
                    grid_limit_kw = None
            with g_col3:
                if enable_grid_limit:
                    target_cap_kw = st.number_input("Target Peak-Shaving Cap (kW):", min_value=1.0, max_value=float(grid_limit_kw), value=float(np.round(grid_limit_kw * 0.85, 0)), step=5.0, key=f"{key_prefix}_target_val_{file_name}")
                else:
                    target_cap_kw = None

            st.subheader("4. Interactive Load Profile Curve")
            fig = create_dark_load_profile_figure(
                df_clean=df_clean,
                file_name=file_name,
                selected_power_cols=selected_power_cols,
                total_col="Total_Demand_kW",
                peak_kw=kpis.peak_kw,
                grid_limit_kw=grid_limit_kw,
                target_cap_kw=target_cap_kw
            )
            st.plotly_chart(fig, use_container_width=True)

            # Grid Limit Overload Analysis & Violation Cards (Directly Below Chart)
            if enable_grid_limit and grid_limit_kw:
                series = df_clean["Total_Demand_kW"]
                overload_diff = (series - grid_limit_kw).clip(lower=0.0)
                overload_peak_kw = float(overload_diff.max())
                overload_hours = float((series > grid_limit_kw).sum() * 0.25)
                overload_kwh = float(overload_diff.sum() * 0.25)
                has_violation = overload_peak_kw > 0.0

                if target_cap_kw:
                    shave_diff = (series - target_cap_kw).clip(lower=0.0)
                    shave_kwh = float(shave_diff.sum() * 0.25)

                st.markdown("#### 🚨 Grid Capacity Limit & Overload Analysis")
                o_col1, o_col2, o_col3, o_col4 = st.columns(4)

                with o_col1:
                    card_style = "sandbox-card-alert" if has_violation else "sandbox-card-ok"
                    status_title = "⚠️ Grid Overload Peak" if has_violation else "✅ Grid Status"
                    val_str = f"+{overload_peak_kw:.1f} kW" if has_violation else "Within Limit"
                    st.markdown(
                        f"""<div class="{card_style}">
                            <div class="sandbox-title">{status_title}</div>
                            <div class="sandbox-value">{val_str}</div>
                            <div class="sandbox-sub">Max Limit: {grid_limit_kw:.1f} kW</div>
                        </div>""",
                        unsafe_allow_html=True
                    )

                with o_col2:
                    st.markdown(
                        f"""<div class="sandbox-card">
                            <div class="sandbox-title">⏱️ Overload Duration</div>
                            <div class="sandbox-value">{overload_hours:.2f} hrs</div>
                            <div class="sandbox-sub">{int(overload_hours * 4)} 15-min intervals</div>
                        </div>""",
                        unsafe_allow_html=True
                    )

                with o_col3:
                    st.markdown(
                        f"""<div class="sandbox-card">
                            <div class="sandbox-title">⚡ Overload Energy</div>
                            <div class="sandbox-value">{overload_kwh:.1f} kWh</div>
                            <div class="sandbox-sub">Excess Energy over Limit</div>
                        </div>""",
                        unsafe_allow_html=True
                    )

                with o_col4:
                    if target_cap_kw:
                        st.markdown(
                            f"""<div class="sandbox-card">
                                <div class="sandbox-title">🔋 Target Shaving Energy</div>
                                <div class="sandbox-value">{shave_kwh:.1f} kWh</div>
                                <div class="sandbox-sub">Peak Shaving Target: {target_cap_kw:.1f} kW</div>
                            </div>""",
                            unsafe_allow_html=True
                        )
                    else:
                        st.markdown(
                            f"""<div class="sandbox-card">
                                <div class="sandbox-title">🛡️ Status</div>
                                <div class="sandbox-value">{"LIMIT EXCEEDED" if has_violation else "OK"}</div>
                                <div class="sandbox-sub">Target Shaving Cap disabled</div>
                            </div>""",
                            unsafe_allow_html=True
                        )

            with st.expander("📋 Processed Data Table Preview", expanded=False):
                st.dataframe(df_clean, use_container_width=True, height=220)

