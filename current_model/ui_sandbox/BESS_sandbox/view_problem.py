"""
========================================================================================
BESS Sandbox - Baseline Grid Exceedance View
(ui_sandbox/BESS_sandbox/view_problem.py)
========================================================================================

Description:
------------
Unmitigated facility demand diagnostics against the contracted grid connection limit:
  - Contracted grid limit controller with quick regional utility preset buttons.
  - Diagnostic analyzer identifying peak exceedance, overload hours, and deficit energy.
  - Problem status banner and 4 executive KPI cards.
  - Single high-contrast Plotly preview figure highlighting overload violations in red.
"""

import io
import os
import sys
import zipfile
import re
import datetime
from typing import Dict, Any, Optional, List, Tuple
import numpy as np
import pandas as pd
import streamlit as st

# Path bootstrapping
CURRENT_DIR = os.path.abspath(os.path.dirname(__file__))
UI_SANDBOX_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
CURRENT_MODEL_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
WORKSPACE_DIR = os.path.abspath(os.path.join(CURRENT_MODEL_DIR, ".."))
for p in [CURRENT_DIR, UI_SANDBOX_DIR, CURRENT_MODEL_DIR, WORKSPACE_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from current_model.core.bess_engine import analyze_grid_violations
    from current_model.ui.tab4_bess.charts import create_grid_violation_preview_figure
    from current_model.core.csv_parser import (
        read_raw_content,
        parse_csv_content,
        detect_suggested_columns,
        generate_sample_demo_csv
    )
    from current_model.core.load_processor import process_load_profile_data
    from current_model.core.metrics_engine import compute_load_profile_kpis
    from current_model.ui.common.session_utils import detect_load_profile_gaps
except ImportError:
    from core.bess_engine import analyze_grid_violations
    from ui.tab4_bess.charts import create_grid_violation_preview_figure
    from core.csv_parser import (
        read_raw_content,
        parse_csv_content,
        detect_suggested_columns,
        generate_sample_demo_csv
    )
    from core.load_processor import process_load_profile_data
    from core.metrics_engine import compute_load_profile_kpis
    from ui.common.session_utils import detect_load_profile_gaps

from ui_sandbox.BESS_sandbox import baseline_presets as presets
from ui_sandbox.BESS_sandbox import sandbox_bess_engine as engine


def _render_bess_csv_ingestion_pipeline(key_prefix: str = "bess_sb_csv") -> None:
    """
    1:1 CSV Ingestion and Validation Pipeline adapted from Current Situation Sandbox:
      1. Multi-format uploader (.csv, .txt, .zip) with multi-encoding fallback and 15-min demo generator.
      2. Raw table inspector with dynamic skiprows control.
      3. Column auto-detection, multi-channel meter aggregation, and 4 unit conversion modes.
      4. Day-first timestamp parsing heuristic with live formatted sample preview.
      5. Day-accurate date range filter (DD.MM.YYYY) with validation.
      6. Processed load profile KPIs, time discontinuity gap detection, and multi-year notices.
      7. Processed raw data table preview expander.
    """
    col_up, col_demo = st.columns([5, 2])
    with col_up:
        uploaded_files = st.file_uploader(
            "Upload Load Profile CSV(s) or ZIP folder:",
            type=["csv", "txt", "zip"],
            accept_multiple_files=True,
            key=f"{key_prefix}_uploader"
        )

    has_active_csv = bool(st.session_state.get(f"{key_prefix}_cached_files")) or (
        "bess_sb_custom_df" in st.session_state
        and isinstance(st.session_state["bess_sb_custom_df"], pd.DataFrame)
        and not st.session_state["bess_sb_custom_df"].empty
    )
    is_demo = bool(st.session_state.get(f"{key_prefix}_demo_loaded"))

    with col_demo:
        st.write("")
        st.write("")
        if is_demo:
            if st.button("Reset / Reload Demo Data", icon=":material/refresh:", key=f"{key_prefix}_reload_btn", use_container_width=True):
                keys_to_clear = [k for k in list(st.session_state.keys()) if k.startswith(key_prefix)]
                for k in keys_to_clear:
                    del st.session_state[k]
                st.session_state.pop("bess_sb_custom_df", None)
                st.session_state.pop("bess_sb_custom_filename", None)
                st.session_state.pop("active_csv_df", None)
                st.session_state.pop("active_csv_filename", None)
                st.session_state[f"{key_prefix}_demo_loaded"] = True
                st.rerun()
        elif has_active_csv:
            if st.button("Clear / Remove Uploaded Data", icon=":material/delete:", key=f"{key_prefix}_clear_btn", use_container_width=True):
                keys_to_clear = [k for k in list(st.session_state.keys()) if k.startswith(key_prefix)]
                for k in keys_to_clear:
                    del st.session_state[k]
                st.session_state.pop("bess_sb_custom_df", None)
                st.session_state.pop("bess_sb_custom_filename", None)
                st.session_state.pop("active_csv_df", None)
                st.session_state.pop("active_csv_filename", None)
                st.rerun()
        else:
            if st.button("Load 15-Min Demo CSV (Full Year 2025)", icon=":material/play_circle:", key=f"{key_prefix}_demo_btn", use_container_width=True):
                keys_to_clear = [k for k in list(st.session_state.keys()) if k.startswith(key_prefix)]
                for k in keys_to_clear:
                    del st.session_state[k]
                st.session_state[f"{key_prefix}_demo_loaded"] = True
                st.rerun()

    files_to_process: List[Tuple[str, str]] = []
    if uploaded_files:
        st.session_state[f"{key_prefix}_demo_loaded"] = False
        for f in uploaded_files:
            fname = getattr(f, "name", "file.csv")
            if fname.lower().endswith(".zip"):
                try:
                    with zipfile.ZipFile(io.BytesIO(f.getvalue())) as z:
                        for member in z.namelist():
                            if member.lower().endswith((".csv", ".txt")) and not member.startswith("__MACOSX"):
                                try:
                                    raw_bytes = z.read(member)
                                    content = None
                                    for enc in ["utf-8", "utf-8-sig", "latin1", "cp1252"]:
                                        try:
                                            content = raw_bytes.decode(enc)
                                            break
                                        except Exception:
                                            continue
                                    if content:
                                        base_member = os.path.basename(member)
                                        files_to_process.append((base_member or member, content))
                                except Exception:
                                    continue
                except Exception as e:
                    st.error(f"Error extracting ZIP archive {fname}: {e}")
            else:
                try:
                    content = read_raw_content(f)
                    files_to_process.append((fname, content))
                except Exception as e:
                    st.error(f"Error reading {fname}: {e}")
        if files_to_process:
            st.session_state[f"{key_prefix}_cached_files"] = files_to_process
    elif is_demo:
        demo_name, demo_content = generate_sample_demo_csv(days=365)
        files_to_process = [(demo_name, demo_content)]
        st.session_state[f"{key_prefix}_cached_files"] = files_to_process
    elif f"{key_prefix}_cached_files" in st.session_state and st.session_state[f"{key_prefix}_cached_files"]:
        files_to_process = st.session_state[f"{key_prefix}_cached_files"]

    if not files_to_process:
        if (
            "bess_sb_custom_df" in st.session_state
            and isinstance(st.session_state["bess_sb_custom_df"], pd.DataFrame)
            and not st.session_state["bess_sb_custom_df"].empty
        ):
            c_name = st.session_state.get("bess_sb_custom_filename", "Custom_Load_Profile.csv")
            c_df = st.session_state["bess_sb_custom_df"]
            st.info(
                f":material/check_circle: **Active Custom Profile Retained:** `{c_name}` "
                f"({len(c_df):,} intervals | Peak: `{c_df['Total_Demand_kW'].max():,.1f} kW`).\n\n"
                f"Upload a new file above or click **'Clear / Remove Uploaded Data'** to reset.",
                icon=":material/verified:"
            )
            with st.expander(":material/table_chart: Active Cleaned Profile Preview", expanded=False):
                st.dataframe(c_df, use_container_width=True, height=200)
            return

        st.info("Upload a CSV/ZIP file above or click **'Load 15-Min Demo CSV'** to begin inspecting meter data.")
        return

    # Inform user if dataset was restored from active session
    if not uploaded_files and not is_demo and files_to_process:
        fnames = ", ".join([f[0] for f in files_to_process])
        st.caption(f":material/check_circle: Active Dataset: **{fnames}** (Retained from active session)")

    for file_name, raw_csv_text in files_to_process:
        st.caption(f"Active Dataset: **{file_name}**")

        with st.expander(":material/search: **CSV Preview & Table Inspector**", expanded=False):
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

        # Detect sample raw timestamp string and default dayfirst preference
        sample_raw_str = ""
        default_dayfirst = True
        if suggested_time:
            time_cols_present = [c for c in suggested_time if c in cols]
            if len(time_cols_present) == 1:
                sample_raw_str = str(df_raw[time_cols_present[0]].dropna().iloc[0]) if not df_raw[time_cols_present[0]].dropna().empty else ""
            elif len(time_cols_present) > 1:
                sample_raw_str = " ".join([str(df_raw[c].dropna().iloc[0]) for c in time_cols_present if not df_raw[c].dropna().empty])
            starts_with_year = bool(re.match(r"^\s*\d{4}[./-]", sample_raw_str))
            default_dayfirst = not starts_with_year

        # Check if full raw parsed data exists in session state
        raw_cache_key = f"{key_prefix}_raw_df_{file_name}"
        calc_cache_key = f"{key_prefix}_calc_data_{file_name}"

        initial_min_date = None
        initial_max_date = None

        if raw_cache_key in st.session_state and isinstance(st.session_state[raw_cache_key], pd.DataFrame):
            df_cached_full = st.session_state[raw_cache_key]
            if not df_cached_full.empty and "timestamp" in df_cached_full.columns:
                initial_min_date = df_cached_full["timestamp"].min().date()
                initial_max_date = df_cached_full["timestamp"].max().date()
        elif suggested_time and suggested_power:
            try:
                df_init = process_load_profile_data(
                    df_raw=df_raw,
                    selected_time_cols=[c for c in suggested_time if c in cols],
                    selected_power_cols=[c for c in suggested_power if c in cols],
                    selected_unit=suggested_unit,
                    max_rows=len(df_raw),
                    dayfirst=default_dayfirst
                )
                st.session_state[raw_cache_key] = df_init
                initial_min_date = df_init["timestamp"].min().date()
                initial_max_date = df_init["timestamp"].max().date()
            except Exception:
                pass

        if initial_min_date is None:
            initial_min_date = datetime.date(2025, 1, 1)
            initial_max_date = datetime.date(2025, 12, 31)

        with st.form(key=f"{key_prefix}_form_{file_name}"):
            st.markdown("##### 2. Column Mapping & Unit Assignment")
            map_col1, map_col2, map_col3 = st.columns([4, 4, 3])

            with map_col1:
                selected_time_cols = st.multiselect(
                    ":material/calendar_today: Timestamp Column(s):",
                    options=cols,
                    default=[c for c in suggested_time if c in cols],
                    key=f"{key_prefix}_time_{file_name}"
                )

            with map_col2:
                selected_power_cols = st.multiselect(
                    ":material/bolt: Power / Meter Column(s):",
                    options=cols,
                    default=[c for c in suggested_power if c in cols and c not in selected_time_cols],
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
                    ":material/tune: Unit Conversion:",
                    options=unit_options,
                    index=unit_idx,
                    key=f"{key_prefix}_unit_{file_name}"
                )

            date_opt_col1, date_opt_col2 = st.columns([5, 6])
            with date_opt_col1:
                dayfirst_choice = st.toggle(
                    ":material/sync: **Day-First Date Format (DD.MM)**",
                    value=default_dayfirst,
                    key=f"{key_prefix}_dayfirst_{file_name}"
                )

            with date_opt_col2:
                if sample_raw_str:
                    try:
                        parsed_sample = pd.to_datetime(sample_raw_str, dayfirst=dayfirst_choice, errors="coerce")
                        if pd.notnull(parsed_sample):
                            st.caption(f":material/event: Preview: `{sample_raw_str}` → **{parsed_sample.strftime('%d %b %Y %H:%M')}**")
                    except Exception:
                        pass

            st.markdown("##### 3. Active Date Range Filter (Day-Accurate)")
            st.caption("By default, the complete uploaded recording is analyzed. You can optionally restrict the evaluation window to a specific single year or custom date interval.")

            f_col1, f_col2 = st.columns(2)
            with f_col1:
                start_date = st.date_input(
                    ":material/calendar_today: Start Date (inclusive):",
                    value=initial_min_date,
                    format="DD.MM.YYYY",
                    key=f"{key_prefix}_start_date_{file_name}"
                )
            with f_col2:
                end_date = st.date_input(
                    ":material/calendar_today: End Date (inclusive):",
                    value=initial_max_date,
                    format="DD.MM.YYYY",
                    key=f"{key_prefix}_end_date_{file_name}"
                )

            submit_calc = st.form_submit_button("Calculate Load Profile & Metrics", icon=":material/calculate:", type="primary", use_container_width=True)

        if submit_calc or calc_cache_key not in st.session_state:
            if not selected_time_cols or not selected_power_cols:
                st.warning("Please select at least one timestamp column and one power column.")
                continue

            if start_date and end_date and start_date > end_date:
                st.error("Start date cannot be after end date. Please adjust the selected dates.")
                continue

            try:
                df_full = process_load_profile_data(
                    df_raw=df_raw,
                    selected_time_cols=selected_time_cols,
                    selected_power_cols=selected_power_cols,
                    selected_unit=selected_unit,
                    max_rows=len(df_raw),
                    dayfirst=dayfirst_choice
                )
                st.session_state[raw_cache_key] = df_full

                min_full = df_full["timestamp"].min().date()
                max_full = df_full["timestamp"].max().date()

                # Apply date filter
                if start_date and end_date:
                    mask = (df_full["timestamp"].dt.date >= start_date) & (df_full["timestamp"].dt.date <= end_date)
                    df_clean = df_full.loc[mask].reset_index(drop=True)
                else:
                    df_clean = df_full

                if df_clean.empty:
                    st.warning(f"No data points found for the selected date range ({start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}).")
                    continue

                kpis = compute_load_profile_kpis(df_clean, power_col="Total_Demand_kW")
                is_filtered = (start_date > min_full) or (end_date < max_full) if start_date and end_date else False

                st.session_state[calc_cache_key] = {
                    "df_clean": df_clean,
                    "df_full": df_full,
                    "kpis": kpis,
                    "selected_power_cols": selected_power_cols,
                    "start_date": start_date,
                    "end_date": end_date,
                    "is_filtered": is_filtered,
                    "min_full": min_full,
                    "max_full": max_full
                }
                # Register active custom profile for BESS Sandbox and session
                st.session_state["bess_sb_custom_df"] = df_clean
                range_suffix = f" [{start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}]" if is_filtered else ""
                st.session_state["bess_sb_custom_filename"] = f"{file_name}{range_suffix}"
                st.session_state["active_csv_df"] = df_clean
                st.session_state["active_csv_filename"] = f"{file_name}{range_suffix}"
                st.session_state["tab1_active_source"] = "csv"

            except Exception as err:
                st.error(f"Timestamp / Data Processing Error: {err}")
                continue

        cached = st.session_state.get(calc_cache_key)
        if cached:
            df_clean = cached["df_clean"]
            df_full = cached.get("df_full", df_clean)
            kpis = cached["kpis"]
            is_filtered = cached.get("is_filtered", False)
            c_start = cached.get("start_date")
            c_end = cached.get("end_date")
            min_full = cached.get("min_full")
            max_full = cached.get("max_full")

            # Always ensure session state has latest
            st.session_state["bess_sb_custom_df"] = df_clean
            range_suffix = f" [{c_start.strftime('%d.%m.%Y')} - {c_end.strftime('%d.%m.%Y')}]" if is_filtered and c_start and c_end else ""
            st.session_state["bess_sb_custom_filename"] = f"{file_name}{range_suffix}"
            st.session_state["active_csv_df"] = df_clean
            st.session_state["active_csv_filename"] = f"{file_name}{range_suffix}"
            st.session_state["tab1_active_source"] = "csv"

            # Filter feedback
            if is_filtered and c_start and c_end:
                st.info(
                    f":material/filter_alt: **Active Filter Applied:** {c_start.strftime('%d.%m.%Y')} to {c_end.strftime('%d.%m.%Y')} "
                    f"| **{len(df_clean):,}** of {len(df_full):,} data points active "
                    f"({(len(df_clean)/len(df_full)*100.0):.1f}% of total data, {kpis.duration_days:.0f} days)"
                )
            elif min_full and max_full:
                st.caption(
                    f":material/date_range: **Full Dataset Range:** {min_full.strftime('%d.%m.%Y')} to {max_full.strftime('%d.%m.%Y')} "
                    f"| **{len(df_clean):,} Data Points** ({kpis.duration_days:.0f} days)"
                )

            # Multi-Year Notice
            cal_days = float(getattr(kpis, "duration_days", 0.0) or 0.0)
            if min_full and max_full:
                actual_cal_span = (c_end - c_start).days if (c_start and c_end) else (max_full - min_full).days
            else:
                actual_cal_span = int(cal_days)

            if actual_cal_span > 366:
                st.info(
                    f":material/history: **Multi-Year Timeseries Detected ({actual_cal_span} calendar days):** "
                    f"Full period is utilized for high-resolution baseline evaluation and BESS dispatch simulation. "
                    f"For annual lifecycle financial metrics, annualized base metrics project forward while preserving authentic load dynamics.",
                    icon=":material/info:"
                )

            # Time Discontinuity / Gap Detection Warning
            detected_gaps = detect_load_profile_gaps(df_clean, max_gap_hours=max(1.0, kpis.hours_per_step * 3))
            if detected_gaps:
                gap_desc = ", ".join([f"{g['start_str']} to {g['end_str']} ({g['duration_days']:.1f} days)" for g in detected_gaps[:3]])
                if len(detected_gaps) > 3:
                    gap_desc += f" and {len(detected_gaps) - 3} further intervals"
                st.warning(
                    f":material/warning: **Data Gaps Detected:** {len(detected_gaps)} measurement interruption(s) found "
                    f"({gap_desc}). Missing intervals are displayed as breaks in the time series chart without artificial interpolation. "
                    f"The BESS dispatch engine will neutralize these periods to protect simulation integrity.",
                    icon=":material/warning:"
                )

            with st.expander(":material/table_chart: Processed 15-Minute Load Profile Table Preview", expanded=False):
                st.dataframe(df_clean, use_container_width=True, height=200)


def render_problem_baseline_tab(preset: presets.BaselinePreset) -> float:
    """
    Renders the baseline grid constraint & overload problem view:
      1. Compact in-tab data ingestor (Benchmark Profiles vs. Custom CSV Ingestion).
      2. Grid limit controller with callback buttons.
      3. Purified 4 Problem KPI cards (0% battery logic, featuring Total Exceedance Energy).
      4. High-contrast facility load & overload preview chart.
    """
    st.subheader(":material/warning: Current Situation: Facility Load & Grid Bottleneck")
    st.caption(
        "Diagnose unmitigated facility power demand against the contracted grid connection limit. "
        "Any demand spikes exceeding this threshold result in severe utility capacity penalties, "
        "tripped breakers, or expensive mandatory transformer station upgrades."
    )

    # --- 1. Compact Data Ingestion Toolbar ---
    custom_df = st.session_state.get("bess_sb_custom_df")
    has_custom = custom_df is not None and isinstance(custom_df, pd.DataFrame) and not custom_df.empty

    is_custom_selected = (
        has_custom
        or "Custom Profile" in str(preset.title)
        or "custom" in str(preset.key).lower()
    )

    with st.container(border=True):
        col_src1, col_src2 = st.columns([2, 3])
        with col_src1:
            st.markdown("##### :material/input: Load Profile Source")
            src_options = ["Preset Benchmark Profile", "Custom CSV Upload"]
            selected_mode = st.radio(
                "Data Source Mode",
                options=src_options,
                index=1 if is_custom_selected else 0,
                horizontal=True,
                label_visibility="collapsed",
                key="bess_sb_src_radio"
            )

        with col_src2:
            if selected_mode == "Preset Benchmark Profile":
                st.markdown(f"**Active Preset:** `{preset.title}`")
                st.caption(f"Profile length: `{len(preset.load_df):,}` rows | Peak: `{preset.load_df['Total_Demand_kW'].max():,.1f} kW`")
                if has_custom and st.button(":material/swap_horiz: Clear Custom CSV & Use Preset", use_container_width=False):
                    st.session_state.pop("bess_sb_custom_df", None)
                    st.session_state.pop("bess_sb_custom_filename", None)
                    st.session_state.pop("bess_sb_csv_cached_files", None)
                    st.session_state.pop("bess_sb_csv_demo_loaded", None)
                    st.rerun()
            else:
                st.caption("Custom CSV ingestion active. Configure file, mapping and dates below.")

        if selected_mode == "Custom CSV Upload":
            st.markdown("---")
            _render_bess_csv_ingestion_pipeline(key_prefix="bess_sb_csv")

    # Determine the active DataFrame for Tab 1
    custom_df = st.session_state.get("bess_sb_custom_df")
    has_custom = custom_df is not None and isinstance(custom_df, pd.DataFrame) and not custom_df.empty

    if selected_mode == "Custom CSV Upload" and has_custom:
        load_df = custom_df
        power_col = "Total_Demand_kW" if "Total_Demand_kW" in load_df.columns else "P_Load_kW"
    else:
        load_df = preset.load_df
        power_col = "Total_Demand_kW" if "Total_Demand_kW" in load_df.columns else "P_Load_kW"

    # --- 2. Grid Limit Controller & Quick Preset Buttons ---
    if "bess_sb_grid_limit_kw" not in st.session_state:
        st.session_state["bess_sb_grid_limit_kw"] = float(preset.grid_limit_kw)

    def _set_quick_grid_limit(val: float) -> None:
        st.session_state["bess_sb_grid_limit_kw"] = float(val)

    col_ctrl1, col_ctrl2 = st.columns([2, 3])
    with col_ctrl1:
        grid_limit_kw = st.number_input(
            "Contracted Grid Connection Limit (kW)",
            min_value=1.0,
            max_value=10000.0,
            step=5.0,
            help="Maximum active power allowed by the regional distribution system operator (DSO).",
            key="bess_sb_grid_limit_kw"
        )
    with col_ctrl2:
        st.markdown("**Quick Preset Limits:**")
        q_cols = st.columns(3)
        q_cols[0].button("147 kW (Liander AC4b)", on_click=_set_quick_grid_limit, args=(147.0,), use_container_width=True)
        q_cols[1].button("150 kW (Enexis Cap)", on_click=_set_quick_grid_limit, args=(150.0,), use_container_width=True)
        q_cols[2].button("430 kW (Salentein EDEMSA)", on_click=_set_quick_grid_limit, args=(430.0,), use_container_width=True)

    # --- 3. Diagnostics Calculation & Purified 4 Problem KPI Cards ---
    diag = analyze_grid_violations(load_df[power_col], grid_limit_kw, step_hours=0.25)
    st.session_state["bess_sb_pre_diag"] = diag

    # Pure physical exceedance calculation (0% battery assumptions)
    exceedance_summary = engine.compute_exceedance_energy_summary(load_df[power_col], grid_limit_kw, step_hours=0.25)

    has_overload = bool(diag.get("has_violations", False) or diag.get("overload_peak_kw", 0.0) > 0.0)

    if has_overload:
        st.error(
            f"**:material/error: Grid Capacity Violation Detected!**\n\n"
            f"The facility exceeds the contracted **{grid_limit_kw:,.1f} kW** limit by up to "
            f"**+{diag['overload_peak_kw']:,.1f} kW** across **{diag['total_violation_hours']:,.1f} hours/year**. "
            f"Total unmitigated energy above the limit is **{exceedance_summary['total_exceedance_kwh']:,.1f} kWh/year**.",
            icon=":material/warning:"
        )
    else:
        st.success(
            f"**:material/check_circle: Facility Load Within Grid Capacity!**\n\n"
            f"Peak demand (`{diag['peak_load_kw']:,.1f} kW`) does not exceed the contracted "
            f"**{grid_limit_kw:,.1f} kW** connection limit.",
            icon=":material/verified:"
        )

    # 4 Purified Problem KPI Cards (0% Battery Physics)
    m_col1, m_col2, m_col3, m_col4 = st.columns(4)
    with m_col1:
        st.metric(
            label="Peak Facility Demand",
            value=f"{diag['peak_load_kw']:,.1f} kW",
            delta=f"Limit: {grid_limit_kw:,.0f} kW",
            delta_color="off",
            help="Maximum 15-minute active electrical power demand registered across the year."
        )
    with m_col2:
        overload_kw = diag.get("overload_peak_kw", 0.0)
        st.metric(
            label="Peak Overload Above Limit",
            value=f"+{overload_kw:,.1f} kW",
            delta_color="inverse",
            help="Maximum active power deficit above the contracted grid connection limit."
        )
    with m_col3:
        st.metric(
            label="Total Overload Duration",
            value=f"{diag['total_violation_hours']:,.1f} hrs",
            delta=f"{diag['violation_share_pct']:.1f}% of year",
            delta_color="inverse",
            help="Cumulative hours throughout the year when facility demand exceeds the contracted limit."
        )
    with m_col4:
        st.metric(
            label="Total Exceedance Energy",
            value=f"{exceedance_summary['total_exceedance_kwh']:,.1f} kWh",
            delta=f"{exceedance_summary['exceedance_share_pct']:.2f}% of total demand",
            delta_color="inverse" if exceedance_summary['total_exceedance_kwh'] > 0 else "off",
            help="Pure physical energy integral above the grid limit curve over the year (0% battery assumptions)."
        )

    st.markdown("---")

    # --- 4. Single Problem Chart: Unmitigated Load & Overload Area ---
    st.markdown("#### :material/show_chart: Facility Load Profile & Exceedance Preview")
    st.caption("Visual inspection of facility demand. Highlighted red zones represent grid limit breaches.")

    fig_prev = create_grid_violation_preview_figure(
        df=load_df,
        grid_limit_kw=grid_limit_kw,
        power_col=power_col
    )
    st.plotly_chart(fig_prev, use_container_width=True)

    # Save active limit and return
    st.session_state["bess_sb_active_limit_kw"] = float(grid_limit_kw)
    return float(grid_limit_kw)
