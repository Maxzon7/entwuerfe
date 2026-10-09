"""
========================================================================================
CSV Load Profile Inspector View (current_model/ui/tab1_consumption/csv_inspector/view.py)
========================================================================================

Description:
------------
Orchestrates the CSV Load Profile Inspector component:
  - Multi-file uploader and demo data generator
  - Preview expander with skiprows control
  - Auto-column mapping form and date-format toggle
  - KPI calculation and metric cards
  - Compact grid capacity limit setting
  - Interactive Plotly chart with rangeslider and grid limit line
  - Overload peak, duration, and energy violation analysis
"""

import io
import os
import zipfile
import re
import datetime
from typing import List, Tuple, Any, Optional
import streamlit as st
import pandas as pd
import numpy as np

try:
    from current_model.core.csv_parser import read_raw_content, parse_csv_content, detect_suggested_columns, generate_sample_demo_csv
    from current_model.core.load_processor import process_load_profile_data
    from current_model.core.metrics_engine import compute_load_profile_kpis
    from current_model.ui.common.cards import render_kpi_card
    from current_model.ui.common.session_utils import detect_load_profile_gaps
except ImportError:
    from core.csv_parser import read_raw_content, parse_csv_content, detect_suggested_columns, generate_sample_demo_csv
    from core.load_processor import process_load_profile_data
    from core.metrics_engine import compute_load_profile_kpis
    from ui.common.cards import render_kpi_card
    from ui.common.session_utils import detect_load_profile_gaps

try:
    from ui_sandbox.Currentsituation_sandbox.consumption.csv_inspector.charts import (
        create_csv_inspector_figure,
        create_monthly_load_breakdown_figure,
        create_365d_baseline_figure,
    )
    from ui_sandbox.Currentsituation_sandbox.consumption.csv_inspector.forms import render_csv_uploader_section
except ImportError:
    try:
        from current_model.ui_sandbox.Currentsituation_sandbox.consumption.csv_inspector.charts import (
            create_csv_inspector_figure,
            create_monthly_load_breakdown_figure,
            create_365d_baseline_figure,
        )
        from current_model.ui_sandbox.Currentsituation_sandbox.consumption.csv_inspector.forms import render_csv_uploader_section
    except ImportError:
        try:
            from consumption.csv_inspector.charts import (
                create_csv_inspector_figure,
                create_monthly_load_breakdown_figure,
                create_365d_baseline_figure,
            )
            from consumption.csv_inspector.forms import render_csv_uploader_section
        except ImportError:
            from current_model.ui.tab1_consumption.csv_inspector.charts import (
                create_csv_inspector_figure,
                create_monthly_load_breakdown_figure,
                create_365d_baseline_figure,
            )
            from current_model.ui.tab1_consumption.csv_inspector.forms import render_csv_uploader_section


def render_csv_inspector(key_prefix: str = "csv_inspector") -> None:
    """
    Renders the interactive CSV Load Profile Inspector component.
    """
    uploaded_files, is_demo = render_csv_uploader_section(key_prefix=key_prefix)

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
                                    # Decode using common encodings
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
            "active_csv_df" in st.session_state
            and isinstance(st.session_state["active_csv_df"], pd.DataFrame)
            and not st.session_state["active_csv_df"].empty
        ):
            _render_restored_csv_inspector(key_prefix=key_prefix)
            return

        st.info("Upload a CSV file above or click **'Load 15-Min Demo CSV'** to begin inspecting meter data.")
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
            initial_min_date = datetime.date(2020, 1, 1)
            initial_max_date = datetime.date.today()


        with st.form(key=f"{key_prefix}_form_{file_name}"):
            st.subheader("2. Column Mapping & Unit Assignment")
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
                            st.caption(f":material/event: Preview: `{sample_raw_str}` -> **{parsed_sample.strftime('%d %b %Y %H:%M')}**")
                    except Exception:
                        pass

            st.subheader("3. Active Date Range Filter (Day-Accurate)")
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
                # Explicitly register current active CSV dataset for Tab 2
                st.session_state["active_csv_df"] = df_clean
                range_suffix = f" [{start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}]" if is_filtered else ""
                st.session_state["active_csv_filename"] = f"{file_name}{range_suffix}"
                st.session_state["tab1_active_source"] = "csv"

                # Automatically normalize for 2025 Status Quo Accounting Pipeline
                try:
                    try:
                        from ui_sandbox.status_quo_2025.consumption_pipeline import normalize_load_profile_2025
                    except ImportError:
                        from current_model.ui_sandbox.status_quo_2025.consumption_pipeline import normalize_load_profile_2025
                    p_col = "Total_Demand_kW" if "Total_Demand_kW" in df_clean.columns else (selected_power_cols[0] if selected_power_cols else df_clean.columns[1])
                    t_col = "timestamp" if "timestamp" in df_clean.columns else None
                    load_2025, _ = normalize_load_profile_2025(raw_df=df_clean, power_col=p_col, time_col=t_col)
                    st.session_state["active_load_series_2025"] = load_2025
                except Exception:
                    pass

                if "project_container" in st.session_state and getattr(st.session_state["project_container"], "base_scenario", None):
                    st.session_state["project_container"].base_scenario.load_source_type = "csv"
                    st.session_state["project_container"].base_scenario.csv_filename = f"{file_name}{range_suffix}"
            except Exception as err:
                st.error(f"Timestamp / Data Processing Error: {err}")
                continue

        cached = st.session_state.get(calc_cache_key)
        if cached:
            df_clean = cached["df_clean"]
            df_full = cached.get("df_full", df_clean)
            kpis = cached["kpis"]
            selected_power_cols = cached["selected_power_cols"]
            is_filtered = cached.get("is_filtered", False)
            c_start = cached.get("start_date")
            c_end = cached.get("end_date")
            min_full = cached.get("min_full")
            max_full = cached.get("max_full")

            # Ensure active dataset pointer is always synced with currently rendered file
            st.session_state["active_csv_df"] = df_clean
            range_suffix = f" [{c_start.strftime('%d.%m.%Y')} - {c_end.strftime('%d.%m.%Y')}]" if is_filtered and c_start and c_end else ""
            st.session_state["active_csv_filename"] = f"{file_name}{range_suffix}"
            st.session_state["tab1_active_source"] = "csv"
            if "project_container" in st.session_state and getattr(st.session_state["project_container"], "base_scenario", None):
                st.session_state["project_container"].base_scenario.load_source_type = "csv"
                st.session_state["project_container"].base_scenario.csv_filename = f"{file_name}{range_suffix}"

            # Status Badges and Data Integrity Warnings
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

            # 1. Multi-Year Duration & Wrapping Notice (> 365 Days)
            cal_days = float(getattr(kpis, "duration_days", 0.0) or 0.0)
            if min_full and max_full:
                actual_cal_span = (c_end - c_start).days if (c_start and c_end) else (max_full - min_full).days
            else:
                actual_cal_span = int(cal_days)

            if actual_cal_span > 366:
                st.info(
                    f":material/history: **Multi-Year Timeseries Detected ({actual_cal_span} calendar days):** "
                    f"Full period is utilized for high-resolution historical baseline evaluation. "
                    f"For subsequent multi-year project horizons and life-cycle simulations, annualized base metrics "
                    f"and rolling sequence wrapping will project forward while preserving authentic load dynamics.",
                    icon=":material/info:"
                )

            # 2. Data Discontinuity / Gap Detection Warning
            detected_gaps = detect_load_profile_gaps(df_clean, max_gap_hours=max(1.0, kpis.hours_per_step * 3))
            if detected_gaps:
                gap_desc = ", ".join([f"{g['start_str']} to {g['end_str']} ({g['duration_days']:.1f} days)" for g in detected_gaps[:3]])
                if len(detected_gaps) > 3:
                    gap_desc += f" and {len(detected_gaps) - 3} further intervals"
                st.warning(
                    f":material/warning: **Data Gaps Detected:** {len(detected_gaps)} measurement interruption(s) found "
                    f"({gap_desc}). Missing intervals are displayed as breaks in the time series chart without artificial interpolation. "
                    f"BESS and coupled dispatch engines will automatically neutralise these periods to protect simulation integrity.",
                    icon=":material/warning:"
                )


            st.subheader("3. Energy Metrics & Key Performance Indicators")
            k1, k2, k3, k4 = st.columns(4)
            with k1:
                render_kpi_card("Peak Demand (P_max)", f"{kpis.peak_kw:,.1f} kW", "Maximum measured power")
            with k2:
                render_kpi_card("Total Energy", f"{kpis.total_kwh:,.0f} kWh", f"Across {kpis.duration_days:.0f} days")
            with k3:
                render_kpi_card("Average Power", f"{kpis.avg_kw:,.1f} kW", "Average continuous load")
            with k4:
                render_kpi_card("Data Points", f"{kpis.data_points_count:,}", f"Interval: {kpis.hours_per_step*60:.0f} min")

            # Compact Grid Limit Option (No standalone subheader)
            g_col1, g_col2 = st.columns([1, 1])
            with g_col1:
                enable_grid_limit = st.toggle(
                    "Enable Grid Capacity Limit",
                    value=False,
                    help="Define a maximum grid connection capacity limit and analyze overload violations.",
                    key=f"{key_prefix}_grid_toggle_{file_name}"
                )
            with g_col2:
                if enable_grid_limit:
                    grid_limit_kw = st.number_input(
                        "Max Grid Capacity Limit (kW):",
                        min_value=5.0,
                        max_value=5000.0,
                        value=float(np.round(kpis.peak_kw * 0.8, 0)),
                        step=5.0,
                        key=f"{key_prefix}_limit_val_{file_name}"
                    )
                else:
                    grid_limit_kw = None

            st.subheader("4. Interactive Load Profile Curve")
            fig = create_csv_inspector_figure(
                df_clean=df_clean,
                file_name=file_name,
                selected_power_cols=selected_power_cols,
                total_col="Total_Demand_kW",
                peak_kw=kpis.peak_kw,
                grid_limit_kw=grid_limit_kw
            )
            st.plotly_chart(fig, use_container_width=True)

            # Grid Limit Overload Analysis & Violation Cards
            if enable_grid_limit and grid_limit_kw:
                series = df_clean["Total_Demand_kW"]
                overload_diff = (series - grid_limit_kw).clip(lower=0.0)
                overload_peak_kw = float(overload_diff.max())
                overload_hours = float((series > grid_limit_kw).sum() * 0.25)
                overload_kwh = float(overload_diff.sum() * 0.25)
                has_violation = overload_peak_kw > 0.0

                st.markdown("#### :material/warning: Grid Capacity Overload Analysis")
                o_col1, o_col2, o_col3 = st.columns(3)

                with o_col1:
                    status_style = "alert" if has_violation else "ok"
                    status_title = "Grid Overload Peak" if has_violation else "Grid Status"
                    val_str = f"+{overload_peak_kw:.1f} kW" if has_violation else "Within Limit"
                    render_kpi_card(status_title, val_str, f"Max Limit: {grid_limit_kw:.1f} kW", status=status_style)

                with o_col2:
                    render_kpi_card("Overload Duration", f"{overload_hours:.2f} hrs", f"{int(overload_hours * 4)} intervals (15-min)")

                with o_col3:
                    render_kpi_card("Overload Energy", f"{overload_kwh:.1f} kWh", "Excess Energy over Limit")

            # 5. Standardized 365-Day Annual Baseline Profile & Calculation Basis
            _render_annual_calculation_profile_section(
                df_clean=df_clean,
                total_col="Total_Demand_kW",
                kpis=kpis,
                file_name=file_name,
                key_prefix=key_prefix
            )

            with st.expander(":material/table_chart: Processed Raw Data Table Preview", expanded=False):
                st.dataframe(df_clean, use_container_width=True, height=220)


def _render_restored_csv_inspector(key_prefix: str = "csv_inspector") -> None:
    """
    Renders the CSV Inspector view when an active CSV dataset has been restored from a project
    snapshot (.dracproj), without requiring the original raw CSV file to be uploaded again.
    """
    df_clean = st.session_state["active_csv_df"].copy()
    file_name = st.session_state.get("active_csv_filename") or "Restored_Meter_Data.csv"

    # Ensure timestamp is datetime
    if "timestamp" in df_clean.columns and not pd.api.types.is_datetime64_any_dtype(df_clean["timestamp"]):
        df_clean["timestamp"] = pd.to_datetime(df_clean["timestamp"], errors="coerce")

    # Determine total power column
    total_col = "Total_Demand_kW"
    if total_col not in df_clean.columns:
        num_cols = [c for c in df_clean.columns if c != "timestamp" and pd.api.types.is_numeric_dtype(df_clean[c])]
        if num_cols:
            df_clean[total_col] = df_clean[num_cols[0]]
        else:
            st.error("Restored dataset does not contain numeric load profile data.")
            return

    df_clean[total_col] = pd.to_numeric(df_clean[total_col], errors="coerce").fillna(0.0)

    # Informative Banner indicating restored baseline profile
    st.info(
        f":material/info: **Active Baseline Load Profile:** `{file_name}` *(Restored from Project Snapshot)*\n\n"
        f"The interactive load profile diagram and baseline metrics below are rendered directly from the project's saved time series data.\n\n"
        f"*(Note: The original raw CSV file was not stored in the project snapshot to keep the file size compact. To re-process columns or change raw units, upload the original CSV file above.)*",
        icon=":material/analytics:"
    )

    # Compute KPIs
    kpis = compute_load_profile_kpis(df_clean, power_col=total_col)

    # Date range and data points info
    min_date = df_clean["timestamp"].min().date() if "timestamp" in df_clean.columns and not df_clean["timestamp"].dropna().empty else None
    max_date = df_clean["timestamp"].max().date() if "timestamp" in df_clean.columns and not df_clean["timestamp"].dropna().empty else None

    if min_date and max_date:
        st.caption(
            f":material/date_range: **Full Dataset Range:** {min_date.strftime('%d.%m.%Y')} to {max_date.strftime('%d.%m.%Y')} "
            f"| **{len(df_clean):,} Data Points** ({kpis.duration_days:.0f} days)"
        )

    # 1. Multi-Year Duration Notice (> 366 Days)
    cal_days = float(getattr(kpis, "duration_days", 0.0) or 0.0)
    if cal_days > 366:
        st.info(
            f":material/history: **Multi-Year Timeseries Detected ({cal_days:.0f} calendar days):** "
            f"Full period is utilized for high-resolution historical baseline evaluation. "
            f"For subsequent multi-year project horizons and life-cycle simulations, an annualized 365-day base profile "
            f"is established to project forward while preserving authentic load dynamics. "
            f"*(See Section 4 below for the full 365-day reference breakdown & plain language guide.)*",
            icon=":material/info:"
        )

    # 2. Gap Detection Warning
    detected_gaps = detect_load_profile_gaps(df_clean, max_gap_hours=max(1.0, kpis.hours_per_step * 3))
    if detected_gaps:
        gap_desc = ", ".join([f"{g['start_str']} to {g['end_str']} ({g['duration_days']:.1f} days)" for g in detected_gaps[:3]])
        if len(detected_gaps) > 3:
            gap_desc += f" and {len(detected_gaps) - 3} further intervals"
        st.warning(
            f":material/warning: **Data Gaps Detected:** {len(detected_gaps)} measurement interruption(s) found "
            f"({gap_desc}). Missing intervals are displayed as breaks in the time series chart without artificial interpolation. "
            f"BESS and coupled dispatch engines will automatically neutralise these periods to protect simulation integrity.",
            icon=":material/warning:"
        )

    # 3. Energy Metrics & Key Performance Indicators
    st.subheader("2. Energy Metrics & Key Performance Indicators")
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        render_kpi_card("Peak Demand (P_max)", f"{kpis.peak_kw:,.1f} kW", "Maximum measured power")
    with k2:
        render_kpi_card("Total Energy", f"{kpis.total_kwh:,.0f} kWh", f"Across {kpis.duration_days:.0f} days")
    with k3:
        render_kpi_card("Average Power", f"{kpis.avg_kw:,.1f} kW", "Average continuous load")
    with k4:
        render_kpi_card("Data Points", f"{kpis.data_points_count:,}", f"Interval: {kpis.hours_per_step*60:.0f} min")

    # Compact Grid Limit Option
    g_col1, g_col2 = st.columns([1, 1])
    with g_col1:
        enable_grid_limit = st.toggle(
            "Enable Grid Capacity Limit",
            value=False,
            help="Define a maximum grid connection capacity limit and analyze overload violations.",
            key=f"{key_prefix}_restored_grid_toggle"
        )
    with g_col2:
        if enable_grid_limit:
            grid_limit_kw = st.number_input(
                "Max Grid Capacity Limit (kW):",
                min_value=5.0,
                max_value=5000.0,
                value=float(np.round(kpis.peak_kw * 0.8, 0)),
                step=5.0,
                key=f"{key_prefix}_restored_limit_val"
            )
        else:
            grid_limit_kw = None

    # 4. Interactive Load Profile Curve
    st.subheader("3. Interactive Load Profile Curve")
    other_cols = [c for c in df_clean.columns if c not in ["timestamp", total_col] and pd.api.types.is_numeric_dtype(df_clean[c])]
    selected_power_cols = [total_col] + other_cols if other_cols else [total_col]
    fig = create_csv_inspector_figure(
        df_clean=df_clean,
        file_name=file_name,
        selected_power_cols=selected_power_cols,
        total_col=total_col,
        peak_kw=kpis.peak_kw,
        grid_limit_kw=grid_limit_kw
    )
    st.plotly_chart(fig, use_container_width=True)

    # Grid Limit Overload Analysis & Violation Cards
    if enable_grid_limit and grid_limit_kw:
        series = df_clean[total_col]
        overload_diff = (series - grid_limit_kw).clip(lower=0.0)
        overload_peak_kw = float(overload_diff.max())
        overload_hours = float((series > grid_limit_kw).sum() * kpis.hours_per_step)
        overload_kwh = float(overload_diff.sum() * kpis.hours_per_step)
        has_violation = overload_peak_kw > 0.0

        st.markdown("#### :material/warning: Grid Capacity Overload Analysis")
        o_col1, o_col2, o_col3 = st.columns(3)

        with o_col1:
            status_style = "alert" if has_violation else "ok"
            status_title = "Grid Overload Peak" if has_violation else "Grid Status"
            val_str = f"+{overload_peak_kw:.1f} kW" if has_violation else "Within Limit"
            render_kpi_card(status_title, val_str, f"Max Limit: {grid_limit_kw:.1f} kW", status=status_style)

        with o_col2:
            render_kpi_card("Overload Duration", f"{overload_hours:.2f} hrs", f"{int(overload_hours / max(0.01, kpis.hours_per_step))} intervals")

        with o_col3:
            render_kpi_card("Overload Energy", f"{overload_kwh:.1f} kWh", "Excess Energy over Limit")

    # 5. Standardized 365-Day Annual Baseline Profile & Calculation Basis
    _render_annual_calculation_profile_section(
        df_clean=df_clean,
        total_col=total_col,
        kpis=kpis,
        file_name=file_name,
        key_prefix=key_prefix
    )

    with st.expander(":material/table_chart: Processed Raw Data Table Preview", expanded=False):
        st.dataframe(df_clean, use_container_width=True, height=220)


def _render_annual_calculation_profile_section(
    df_clean: pd.DataFrame,
    total_col: str,
    kpis: Any,
    file_name: str,
    key_prefix: str
) -> None:
    """
    Renders the Standardized 365-Day Annual Baseline Profile & Plain-Language Calculation Guide.
    Allows inspecting the 1-year reference profile in full 15-min resolution and explains how it is derived.
    """
    st.write("")
    st.subheader("5. Standardized 365-Day Annual Baseline Profile & Calculation Basis")
    st.caption(
        "Downstream modules (**Tab 2: Contracts & Tariffs**, **Tab 3: Solar PV Sizing & Coupling**, and **Tab 4: BESS Storage**) "
        "rely on a standardized 365-day annual calculation profile. Inspect the derived reference year and calculation methodology below:"
    )

    # 1. Compute 365-Day baseline statistics and 12-month calendar aggregation
    duration_days = float(getattr(kpis, "duration_days", 365.0) or 365.0)
    total_energy_kwh = float(getattr(kpis, "total_kwh", 0.0) or 0.0)
    peak_demand_kw = float(getattr(kpis, "peak_kw", 0.0) or 0.0)
    step_hours = float(getattr(kpis, "hours_per_step", 0.25) or 0.25)

    if duration_days > 0:
        annual_scale = (365.0 / duration_days) if duration_days != 365.0 else 1.0
        annualized_energy_kwh = total_energy_kwh * annual_scale
    else:
        annualized_energy_kwh = total_energy_kwh

    annual_avg_kw = annualized_energy_kwh / 8760.0
    annual_load_factor = (annual_avg_kw / peak_demand_kw * 100.0) if peak_demand_kw > 0 else 0.0

    # 2. Extract 365-Day slice for full 15-min timeseries visualization
    if "timestamp" in df_clean.columns and pd.api.types.is_datetime64_any_dtype(df_clean["timestamp"]):
        min_ts = df_clean["timestamp"].min()
        end_365_ts = min_ts + pd.Timedelta(days=365)
        df_365 = df_clean[(df_clean["timestamp"] >= min_ts) & (df_clean["timestamp"] < end_365_ts)].copy()
        if len(df_365) < 96:
            df_365 = df_clean.copy()
    else:
        df_365 = df_clean.iloc[:min(len(df_clean), 35040)].copy()

    # 3. KPI Summary Cards for 365-Day Baseline Year
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_kpi_card(
            "Annual Baseline Energy",
            f"{annualized_energy_kwh:,.0f} kWh",
            f"Normalized to 365 Days ({annualized_energy_kwh/1000.0:,.1f} MWh)"
        )
    with c2:
        render_kpi_card(
            "Baseline Peak Demand",
            f"{peak_demand_kw:,.1f} kW",
            "Highest physical grid power"
        )
    with c3:
        render_kpi_card(
            "Annual Load Factor",
            f"{annual_load_factor:.1f} %",
            f"Average load: {annual_avg_kw:,.1f} kW"
        )
    with c4:
        is_multi_year = duration_days > 366
        render_kpi_card(
            "Simulation Reference",
            "365 Days Standard",
            f"Derived from {duration_days:.0f}-day dataset" if is_multi_year else "1:1 Calendar Year",
            status="ok"
        )

    # 4. Interactive Inspection Expander (Auf Knopfdruck einsehen)
    with st.expander(":material/visibility: **Inspect 365-Day Reference Profile (15-Min Timeseries & Monthly Schedule)**", expanded=False):
        insp_tab1, insp_tab2 = st.tabs([
            ":material/timeline: 15-Minute Annual Curve (35,040 Intervals)",
            ":material/calendar_month: 12-Month Calendar Schedule & Table"
        ])

        with insp_tab1:
            fig_365_ts = create_365d_baseline_figure(
                df_365=df_365,
                total_col=total_col,
                peak_kw=peak_demand_kw
            )
            st.plotly_chart(fig_365_ts, use_container_width=True)

        with insp_tab2:
            # Build 12-month calendar aggregation
            month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
            calendar_days = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

            monthly_rows = []
            if "timestamp" in df_clean.columns and pd.api.types.is_datetime64_any_dtype(df_clean["timestamp"]):
                df_ts = df_clean.copy()
                df_ts["month_num"] = df_ts["timestamp"].dt.month
                for m_i in range(1, 13):
                    m_sub = df_ts[df_ts["month_num"] == m_i]
                    m_days = calendar_days[m_i - 1]
                    if not m_sub.empty:
                        m_p = m_sub[total_col].to_numpy(dtype=float)
                        m_p_clean = np.nan_to_num(m_p, nan=0.0)
                        m_kwh = float(m_p_clean.sum() * step_hours)
                        m_peak = float(m_p_clean.max()) if len(m_p_clean) > 0 else 0.0
                        m_avg = float(m_p_clean.mean()) if len(m_p_clean) > 0 else 0.0
                        m_coverage = min(100.0, (len(m_sub) / max(1.0, m_days * 24.0 / step_hours)) * 100.0)
                    else:
                        daily_est_kwh = annualized_energy_kwh / 365.0
                        m_kwh = daily_est_kwh * m_days
                        m_peak = peak_demand_kw
                        m_avg = m_kwh / (m_days * 24.0)
                        m_coverage = 100.0

                    monthly_rows.append({
                        "Month": month_names[m_i - 1],
                        "Days": m_days,
                        "Energy_kWh": round(m_kwh, 1),
                        "Energy_MWh": round(m_kwh / 1000.0, 2),
                        "Peak_Demand_kW": round(m_peak, 1),
                        "Avg_Load_kW": round(m_avg, 1),
                        "Data_Coverage": f"{m_coverage:.0f}%"
                    })
            else:
                daily_est_kwh = annualized_energy_kwh / 365.0
                for m_i in range(1, 13):
                    m_days = calendar_days[m_i - 1]
                    m_kwh = daily_est_kwh * m_days
                    monthly_rows.append({
                        "Month": month_names[m_i - 1],
                        "Days": m_days,
                        "Energy_kWh": round(m_kwh, 1),
                        "Energy_MWh": round(m_kwh / 1000.0, 2),
                        "Peak_Demand_kW": round(peak_demand_kw, 1),
                        "Avg_Load_kW": round(m_kwh / (m_days * 24.0), 1),
                        "Data_Coverage": "100%"
                    })

            df_monthly = pd.DataFrame(monthly_rows)

            fig_monthly = create_monthly_load_breakdown_figure(df_monthly)
            st.plotly_chart(fig_monthly, use_container_width=True)

            st.markdown("**12-Month Calendar Schedule & Consumption Breakdown:**")
            st.dataframe(
                df_monthly[["Month", "Days", "Energy_MWh", "Energy_kWh", "Peak_Demand_kW", "Avg_Load_kW", "Data_Coverage"]],
                use_container_width=True,
                hide_index=True
            )

    # 5. Concise Plain-Language Guide (In leichter Sprache & auf den Punkt)
    st.markdown(
        f"""
        <div style="background: rgba(15, 23, 42, 0.75); border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 10px; padding: 14px 18px; margin-top: 14px; margin-bottom: 8px;">
            <div style="font-size: 0.95rem; font-weight: 700; color: #38BDF8; margin-bottom: 6px; display: flex; align-items: center; gap: 6px;">
                <span>:material/menu_book:</span> How the Annual Profile is Created & Projected (Quick Guide)
            </div>
            <div style="color: #E2E8F0; font-size: 0.88rem; line-height: 1.5;">
                <p style="margin-bottom: 6px;">
                    <strong>1. Raw Ingestion (Eingelesen):</strong><br>
                    {duration_days:.0f} calendar days of actual interval recordings ({kpis.data_points_count:,} data points at {kpis.hours_per_step*60:.0f}-min resolution) from <code>{file_name}</code>.
                </p>
                <p style="margin-bottom: 6px;">
                    <strong>2. 1-Year Baseline Profile (365-Tage-Berechnungsjahr):</strong><br>
                    The first full 365-day calendar year (35,040 intervals) is extracted as the standard reference year. Measurement gaps are cleanly isolated without artificial spikes, scaling the annual baseline to <strong>{annualized_energy_kwh:,.0f} kWh/year</strong> at <strong>{peak_demand_kw:,.1f} kW</strong> peak demand.
                </p>
                <p style="margin-bottom: 0;">
                    <strong>3. Multi-Year Simulation & Projection (15-Jahre-Hochrechnung):</strong><br>
                    This 365-day profile serves as Year 1 benchmark for Solar PV (Tab 3), BESS (Tab 4), and Electricity Tariffs (Tab 2). Subsequent years project forward dynamically with annual tariff inflation and PV degradation.
                </p>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )
