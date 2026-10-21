"""
========================================================================================
BESS Sandbox - The Problem: Baseline Grid Exceedance View
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

import os
import sys
from typing import Dict, Any, Optional
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
    from current_model.core.csv_parser import read_raw_content, parse_csv_content, detect_suggested_columns
    from current_model.core.load_processor import process_load_profile_data
except ImportError:
    from core.bess_engine import analyze_grid_violations
    from ui.tab4_bess.charts import create_grid_violation_preview_figure
    from core.csv_parser import read_raw_content, parse_csv_content, detect_suggested_columns
    from core.load_processor import process_load_profile_data

from ui_sandbox.BESS_sandbox import baseline_presets as presets
from ui_sandbox.BESS_sandbox import sandbox_bess_engine as engine


def render_problem_baseline_tab(preset: presets.BaselinePreset) -> float:
    """
    Renders the baseline grid constraint & overload problem view:
      1. Compact in-tab data ingestor (Benchmark Profiles vs. Quick CSV Ingestor for Paula).
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

    with st.container(border=True):
        col_src1, col_src2 = st.columns([2, 3])
        with col_src1:
            st.markdown("##### :material/input: Load Profile Source")
            src_options = ["Preset Benchmark Profile", "Minimal CSV Quick-Ingestor (Paula)"]
            selected_mode = st.radio(
                "Data Source Mode",
                options=src_options,
                index=1 if has_custom else 0,
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
                    st.rerun()
            else:
                st.markdown("**15-Minute Load CSV Upload:**")
                uploaded_file = st.file_uploader(
                    "Choose a CSV load profile",
                    type=["csv"],
                    label_visibility="collapsed",
                    key="bess_sb_quick_csv_file"
                )
                if uploaded_file is not None:
                    try:
                        raw_content = read_raw_content(uploaded_file)
                        raw_df = parse_csv_content(raw_content)
                        sug_time, sug_power, sug_unit = detect_suggested_columns(raw_df)

                        st.markdown("---")
                        st.caption("**:material/auto_fix: Auto-Detected Column Mapping:** Verify and apply to set as active profile.")
                        c_col1, c_col2, c_col3, c_col4 = st.columns([2, 2, 2, 1])

                        with c_col1:
                            time_selection = st.multiselect(
                                "Timestamp Column(s)",
                                options=list(raw_df.columns),
                                default=[c for c in sug_time if c in raw_df.columns] or [raw_df.columns[0]],
                                key="bess_sb_time_cols"
                            )
                        with c_col2:
                            power_selection = st.multiselect(
                                "Power Measurement Column(s)",
                                options=[c for c in raw_df.columns if c not in time_selection],
                                default=[c for c in sug_power if c in raw_df.columns and c not in time_selection] or [raw_df.columns[-1]],
                                key="bess_sb_power_cols"
                            )
                        with c_col3:
                            unit_opts = [
                                "kW (Active Power - Direct)",
                                "kWh (15-min interval) → kW",
                                "W (Watt) → kW",
                                "kWh (Hourly) → kW"
                            ]
                            unit_idx = 0
                            for idx, u in enumerate(unit_opts):
                                if "15-min" in sug_unit and "15-min" in u:
                                    unit_idx = idx
                                    break
                                elif "Direct" in sug_unit and "Direct" in u:
                                    unit_idx = idx
                                    break
                            selected_unit = st.selectbox("Measurement Unit", options=unit_opts, index=unit_idx, key="bess_sb_unit_choice")

                        with c_col4:
                            st.write("")
                            st.write("")
                            if st.button(":material/play_arrow: Apply Profile", use_container_width=True, key="btn_apply_csv_profile"):
                                with st.spinner("Processing load profile..."):
                                    clean_custom_df = process_load_profile_data(
                                        df_raw=raw_df,
                                        selected_time_cols=time_selection,
                                        selected_power_cols=power_selection,
                                        selected_unit=selected_unit
                                    )
                                    st.session_state["bess_sb_custom_df"] = clean_custom_df
                                    st.session_state["bess_sb_custom_filename"] = uploaded_file.name
                                    st.success(f"Loaded {len(clean_custom_df):,} rows!")
                                    st.rerun()

                    except Exception as err:
                        st.error(f"Error parsing uploaded CSV: {err}")

    # Determine the active DataFrame for Tab 1
    if selected_mode == "Minimal CSV Quick-Ingestor (Paula)" and has_custom:
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
