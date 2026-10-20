"""
========================================================================================
BESS Sandbox - Technical Feasibility & Peak Shaving View
(ui_sandbox/BESS_sandbox/view_technical.py)
========================================================================================

Description:
------------
Technical simulation and feasibility assessment workspace for Battery Energy Storage:
  - Load profile diagnostics (peak demand, overload hours, worst-case deficit energy).
  - BESS hardware sizing form with automated gross nameplate recommendations.
  - Feasibility badge assessing whether 100% of grid overloads are eliminated.
  - Interactive Plotly dispatch charts: 15-min timeseries, 7-day average week,
    load duration curve, and 24x7 State of Charge heatmap.
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
    from current_model.models.bess import BESSConfig, BESSKPIs
    from current_model.core.bess_engine import (
        analyze_grid_violations,
        compute_average_week_dispatch,
        BESSSimulationResult
    )
    from current_model.ui.tab4_bess.charts import (
        create_grid_violation_preview_figure,
        create_bess_dispatch_timeseries_figure,
        create_average_week_dispatch_figure,
        create_bess_soc_analysis_figure,
        create_bess_soc_heatmap_figure,
        create_load_duration_peak_shaving_figure
    )
except ImportError:
    from models.bess import BESSConfig, BESSKPIs
    from core.bess_engine import (
        analyze_grid_violations,
        compute_average_week_dispatch,
        BESSSimulationResult
    )
    from ui.tab4_bess.charts import (
        create_grid_violation_preview_figure,
        create_bess_dispatch_timeseries_figure,
        create_average_week_dispatch_figure,
        create_bess_soc_analysis_figure,
        create_bess_soc_heatmap_figure,
        create_load_duration_peak_shaving_figure
    )

from ui_sandbox.BESS_sandbox import baseline_presets as presets
from ui_sandbox.BESS_sandbox import sandbox_bess_engine as engine


def render_technical_feasibility_tab(preset: presets.BaselineComparisonPreset) -> BESSSimulationResult:
    """
    Renders the technical feasibility and peak shaving simulation view.
    Returns the executed BESSSimulationResult for downstream financial evaluations.
    """
    st.subheader(":material/speed: Technical Feasibility & Peak Shaving Dispatch")
    st.caption(
        "Evaluate whether the battery configuration can physically shave 100% of facility peak "
        "demands down to the contracted grid connection limit without depleting energy or violating C-rate limits."
    )

    load_df = preset.load_df
    power_col = "Total_Demand_kW" if "Total_Demand_kW" in load_df.columns else "P_Load_kW"
    load_series = load_df[power_col]

    # --- Section 1: Target Grid Limit & Pre-Simulation Diagnostics ---
    col_ctrl1, col_ctrl2 = st.columns([2, 3])
    with col_ctrl1:
        grid_limit_kw = st.number_input(
            "Contracted Grid Limit (kW)",
            min_value=1.0,
            max_value=10000.0,
            value=float(preset.grid_limit_kw),
            step=5.0,
            help="Target maximum active power allowed from the public electrical grid.",
            key="bess_sb_grid_limit_kw"
        )
    with col_ctrl2:
        st.markdown("**Quick Preset Limits:**")
        q_cols = st.columns(3)
        if q_cols[0].button("147 kW (Liander AC4b)", use_container_width=True):
            st.session_state["bess_sb_grid_limit_kw"] = 147.0
            st.rerun()
        if q_cols[1].button("150 kW (Enexis Cap)", use_container_width=True):
            st.session_state["bess_sb_grid_limit_kw"] = 150.0
            st.rerun()
        if q_cols[2].button("200 kW (Mid Limit)", use_container_width=True):
            st.session_state["bess_sb_grid_limit_kw"] = 200.0
            st.rerun()

    # Pre-simulation Diagnostics
    diag = analyze_grid_violations(load_series, grid_limit_kw)
    sizing_rec = engine.compute_gross_minimum_bess_sizing(
        diag,
        round_trip_efficiency_pct=preset.bess_config.round_trip_efficiency_pct,
        soc_min_pct=preset.bess_config.soc_min_pct,
        soc_max_pct=preset.bess_config.soc_max_pct,
        safety_margin_pct=10.0
    )

    # 4 Diagnostics Metric Cards
    m_col1, m_col2, m_col3, m_col4 = st.columns(4)
    with m_col1:
        st.metric(
            label="Peak Facility Demand",
            value=f"{diag['peak_load_kw']:,.1f} kW",
            help="Absolute highest 15-minute active power demand observed in load profile."
        )
    with m_col2:
        st.metric(
            label="Overload Above Limit",
            value=f"{diag['overload_peak_kw']:,.1f} kW",
            delta=f"+{diag['overload_peak_kw']:,.1f} kW" if diag['overload_peak_kw'] > 0 else "None",
            delta_color="inverse",
            help="Maximum active power deficit above the contracted grid connection limit."
        )
    with m_col3:
        st.metric(
            label="Overload Duration",
            value=f"{diag['total_violation_hours']:,.1f} hrs",
            delta=f"{diag['violation_share_pct']:.1f}% of year",
            delta_color="inverse",
            help="Total cumulative duration when facility load exceeds the grid limit."
        )
    with m_col4:
        st.metric(
            label="Worst-Event Energy Deficit",
            value=f"{diag['worst_event_energy_kwh']:,.1f} kWh",
            help=f"Continuous deficit energy across {diag['worst_event_duration_hours']:.1f} hours of uninterrupted overload."
        )

    # Gross Nameplate Sizing Recommendation Banner
    with st.expander(":material/auto_fix: Automated Gross Nameplate Sizing Recommendation", expanded=False):
        st.markdown(
            f"**Recommendation Summary:** To shave 100% of overloads down to **{grid_limit_kw:,.1f} kW**, the battery system requires:\n"
            f"- **Minimum Usable Power:** `{sizing_rec.min_continuous_power_kw:,.1f} kW` continuous discharge\n"
            f"- **Minimum Usable Energy:** `{diag['worst_event_energy_kwh']:,.1f} kWh`\n"
            f"- **Minimum Gross Nameplate:** `{sizing_rec.min_gross_capacity_kwh:,.1f} kWh` (accounting for {sizing_rec.usable_dod_pct:.0f}% usable DoD & {sizing_rec.one_way_efficiency_pct:.1f}% discharge efficiency)\n"
            f"- **Suggested Modular Packaging:** `{sizing_rec.recommended_unit_count}` units of `{sizing_rec.recommended_unit_capacity_kwh:,.0f} kWh` (`{sizing_rec.recommended_total_capacity_kwh:,.0f} kWh` total) with `{sizing_rec.recommended_inverter_power_kw:,.0f} kW` PCS inverter."
        )
        if st.button(":material/check: Apply Recommended Sizing to Form", key="btn_apply_sizing"):
            st.session_state["bess_sb_unit_count"] = sizing_rec.recommended_unit_count
            st.session_state["bess_sb_unit_kwh"] = sizing_rec.recommended_unit_capacity_kwh
            st.session_state["bess_sb_discharge_kw"] = sizing_rec.recommended_inverter_power_kw
            st.session_state["bess_sb_charge_kw"] = sizing_rec.recommended_inverter_power_kw
            st.rerun()

    st.markdown("---")

    # --- Section 2: BESS Hardware Specification Form ---
    st.markdown("#### :material/tune: BESS Hardware Specification & Operating Limits")
    b_col1, b_col2, b_col3 = st.columns(3)

    cfg = preset.bess_config

    with b_col1:
        unit_count = st.number_input(
            "Modular Unit Count",
            min_value=1,
            max_value=100,
            value=st.session_state.get("bess_sb_unit_count", int(cfg.unit_count)),
            step=1,
            key="bess_sb_unit_count"
        )
        unit_kwh = st.number_input(
            "Capacity per Unit (kWh)",
            min_value=10.0,
            max_value=2000.0,
            value=st.session_state.get("bess_sb_unit_kwh", float(cfg.unit_capacity_kwh)),
            step=25.0,
            key="bess_sb_unit_kwh"
        )
        total_kwh = float(unit_count * unit_kwh)
        st.info(f"**Total Gross Nameplate:** `{total_kwh:,.1f} kWh`")

    with b_col2:
        p_dis_max = st.number_input(
            "Max Discharge Inverter (kW)",
            min_value=1.0,
            max_value=5000.0,
            value=st.session_state.get("bess_sb_discharge_kw", float(cfg.max_discharge_power_kw)),
            step=10.0,
            key="bess_sb_discharge_kw"
        )
        p_chg_max = st.number_input(
            "Max Charge Inverter (kW)",
            min_value=1.0,
            max_value=5000.0,
            value=st.session_state.get("bess_sb_charge_kw", float(cfg.max_charge_power_kw)),
            step=10.0,
            key="bess_sb_charge_kw"
        )
        rte_pct = st.slider(
            "Round-Trip Efficiency (RTE %)",
            min_value=70.0,
            max_value=98.0,
            value=float(cfg.round_trip_efficiency_pct),
            step=0.5,
            key="bess_sb_rte_pct"
        )

    with b_col3:
        soc_min_pct = st.slider(
            "SoC Minimum Buffer (%)",
            min_value=0.0,
            max_value=40.0,
            value=float(cfg.soc_min_pct),
            step=5.0,
            key="bess_sb_soc_min"
        )
        soc_max_pct = st.slider(
            "SoC Maximum Limit (%)",
            min_value=60.0,
            max_value=100.0,
            value=float(cfg.soc_max_pct),
            step=5.0,
            key="bess_sb_soc_max"
        )
        dod_window = max(10.0, soc_max_pct - soc_min_pct)
        usable_kwh = total_kwh * (dod_window / 100.0)
        st.success(f"**Effective Usable Storage:** `{usable_kwh:,.1f} kWh` ({dod_window:.0f}% DoD)")

    # Build active BESSConfig
    active_bess_config = BESSConfig(
        capacity_kwh=total_kwh,
        unit_count=int(unit_count),
        unit_capacity_kwh=float(unit_kwh),
        battery_chemistry=cfg.battery_chemistry,
        max_charge_power_kw=float(p_chg_max),
        max_discharge_power_kw=float(p_dis_max),
        round_trip_efficiency_pct=float(rte_pct),
        soc_min_pct=float(soc_min_pct),
        soc_max_pct=float(soc_max_pct),
        initial_soc_pct=float(soc_max_pct),
        max_dod_pct=float(dod_window),
        dispatch_strategy="peak_shaving",
        peak_shaving_threshold_kw=float(grid_limit_kw),
        allow_grid_charging=True,
        currency=cfg.currency,
        cost_per_kwh=cfg.cost_per_kwh,
        fixed_installation_cost=cfg.fixed_installation_cost,
        annual_om_pct=cfg.annual_om_pct,
        cell_replacement_year=cfg.cell_replacement_year,
        cell_replacement_cost_pct=cfg.cell_replacement_cost_pct
    )

    # --- Section 3: 15-Minute Dispatch Simulation ---
    sim_result = engine.simulate_sandbox_bess_dispatch(
        bess_config=active_bess_config,
        load_df=load_df,
        grid_limit_kw=grid_limit_kw,
        step_hours=0.25,
        power_col=power_col
    )

    # Assess Feasibility
    after_diag = sim_result.diagnostics_after
    res_peak_kw = float(after_diag.get("peak_load_kw", 0.0))
    res_overload_peak = float(after_diag.get("overload_peak_kw", 0.0))
    res_violation_hours = float(after_diag.get("total_violation_hours", 0.0))
    res_overload_energy = float(after_diag.get("worst_event_energy_kwh", 0.0))

    is_feasible = (res_overload_peak <= 0.05) and (res_violation_hours <= 0.05)

    st.markdown("---")
    st.markdown("#### :material/verified: Peak Shaving Feasibility Verdict")

    if is_feasible:
        st.success(
            f"**:material/check_circle: FEASIBLE: 100% of Grid Overloads Eliminated!**\n\n"
            f"- **Residual Peak Grid Demand:** `{res_peak_kw:,.1f} kW` (within target limit `{grid_limit_kw:,.1f} kW`).\n"
            f"- **Unserved Overload Duration:** `0.0 Hours` (100% violation elimination achieved).\n"
            f"- **Total Energy Shaved:** `{sim_result.kpis.total_discharged_kwh:,.1f} kWh` discharged across the annual profile.\n"
            f"- **Battery Cycling Intensity:** `{sim_result.kpis.equivalent_full_cycles:.1f} EFC/year`."
        )
    else:
        st.error(
            f"**:material/warning: UNDERSIZED / INFEASIBLE: Residual Overloads Detected!**\n\n"
            f"- **Residual Peak Grid Demand:** `{res_peak_kw:,.1f} kW` (exceeds limit by `{res_overload_peak:,.1f} kW`).\n"
            f"- **Unserved Overload Duration:** `{res_violation_hours:,.1f} Hours` remaining.\n"
            f"- **Deficit Energy During Worst Event:** `{res_overload_energy:,.1f} kWh` unserved due to energy depletion or inverter rating.\n"
            f"- **Action Required:** Increase battery capacity `{total_kwh:,.0f} kWh` or inverter power `{p_dis_max:,.0f} kW` to achieve 100% shave."
        )

    # --- Section 4: Visualizations ---
    st.markdown("---")
    st.markdown("#### :material/bar_chart: Physical Dispatch Visualizations")

    tab_ts, tab_week, tab_ldc, tab_soc = st.tabs([
        ":material/timeline: 15-Min Timeseries",
        ":material/calendar_view_week: 7-Day Average Week",
        ":material/show_chart: Load Duration Curve",
        ":material/battery_charging_full: State of Charge (SoC) Dynamics"
    ])

    with tab_ts:
        st.caption("Interactive 15-minute resolution power dispatch profile with zoom and range selection.")
        fig_ts = create_bess_dispatch_timeseries_figure(
            df=sim_result.df_timeseries,
            grid_limit_kw=grid_limit_kw,
            target_cap_kw=grid_limit_kw,
            capacity_kwh=total_kwh
        )
        st.plotly_chart(fig_ts, use_container_width=True)

    with tab_week:
        st.caption("Aggregated 168-hour representative Monday-to-Sunday profile revealing diurnal charging and discharging cycles.")
        df_avg_week = compute_average_week_dispatch(sim_result.df_timeseries)
        fig_week = create_average_week_dispatch_figure(
            df_avg_week=df_avg_week,
            target_cap_kw=grid_limit_kw,
            capacity_kwh=total_kwh
        )
        st.plotly_chart(fig_week, use_container_width=True)

    with tab_ldc:
        st.caption("Sorted cumulative duration curve showing peak power truncation before vs. after BESS installation.")
        fig_ldc = create_load_duration_peak_shaving_figure(
            df=sim_result.df_timeseries,
            grid_limit_kw=grid_limit_kw,
            step_hours=0.25
        )
        st.plotly_chart(fig_ldc, use_container_width=True)

    with tab_soc:
        st.caption("Battery State of Charge envelope tracking safe boundaries and average 24-hour diurnal patterns.")
        c_soc1, c_soc2 = st.columns(2)
        with c_soc1:
            fig_soc_env = create_bess_soc_analysis_figure(
                df=sim_result.df_timeseries,
                bess_config=active_bess_config
            )
            st.plotly_chart(fig_soc_env, use_container_width=True)
        with c_soc2:
            fig_soc_heat = create_bess_soc_heatmap_figure(
                df=sim_result.df_timeseries
            )
            st.plotly_chart(fig_soc_heat, use_container_width=True)

    # Store in session state for cross-tab sharing
    st.session_state["bess_sb_active_config"] = active_bess_config
    st.session_state["bess_sb_sim_result"] = sim_result
    st.session_state["bess_sb_active_limit_kw"] = grid_limit_kw

    return sim_result
