"""
========================================================================================
BESS Sandbox - The Solution: Peak Shaving & Excel Validation View
(ui_sandbox/BESS_sandbox/view_technical.py)
========================================================================================

Description:
------------
Physical peak shaving solution, modular BESS sizing, simultaneous bottleneck audit,
Pareto coverage tradeoff, and synchronized 2-in-1 timeseries dispatch:
  - Block 1 (Top): Theoretical 100% Zero-Deficit Reference Box.
  - Block 2 (Middle Sub-Tabs):
      * Sub-Tab 2.1: Hardware Specification & Operating Limits (Manual / 0.5C Setup with st.form).
      * Sub-Tab 2.2: Interactive Pareto Sizing & Coverage Tradeoff (Smart Sizing).
  - Block 3: Simultaneous 4-Criterion Bottleneck Checklist & Paula's 5 Excel Validation KPIs.
  - Block 4 (Bottom): Synchronized 2-in-1 Timeseries Chart (Power Dispatch + SoC Envelope).
========================================================================================
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
    from current_model.core.bess_engine import analyze_grid_violations, BESSSimulationResult
except ImportError:
    from models.bess import BESSConfig, BESSKPIs
    from core.bess_engine import analyze_grid_violations, BESSSimulationResult

from ui_sandbox.BESS_sandbox import baseline_presets as presets
from ui_sandbox.BESS_sandbox import sandbox_bess_engine as engine
from ui_sandbox.BESS_sandbox.sandbox_charts import (
    create_synced_dispatch_soc_figure,
    create_pareto_tradeoff_figure,
    compute_focus_range
)


def render_technical_feasibility_tab(
    preset: presets.BaselinePreset,
    grid_limit_kw: Optional[float] = None
) -> BESSSimulationResult:
    """
    Renders the peak shaving solution and technical feasibility workspace:
      - Block 1: 100% Zero-Deficit Reference Box.
      - Block 2: Middle Sub-Tabs (Manual 0.5C Setup with st.form vs. Pareto Tradeoff).
      - Block 3: Simultaneous 4-Criterion Bottleneck Checklist & Paula's 5 Excel KPIs.
      - Block 4: Synchronized 2-in-1 Plotly Subplot (Power Dispatch + SoC Envelope).
    """
    st.subheader(":material/battery_charging_full: BESS Sizing & Physical Validation (The Solution)")
    st.caption(
        "Size and configure the Battery Energy Storage System (BESS) to eliminate peak overloads "
        "down to the contracted grid connection limit with 1:1 Excel-validated physics."
    )

    # Resolve active dataset (custom CSV if loaded, else preset benchmark)
    custom_df = st.session_state.get("bess_sb_custom_df")
    if custom_df is not None and isinstance(custom_df, pd.DataFrame) and not custom_df.empty:
        load_df = custom_df
    else:
        load_df = preset.load_df
    power_col = "Total_Demand_kW" if "Total_Demand_kW" in load_df.columns else "P_Load_kW"

    # Resolve contracted grid limit
    active_limit = float(grid_limit_kw if grid_limit_kw is not None else st.session_state.get("bess_sb_grid_limit_kw", preset.grid_limit_kw))

    cfg = preset.bess_config

    # Read current efficiency & SoC boundaries from session state (or preset defaults)
    cur_rte = float(st.session_state.get("bess_sb_rte_pct", cfg.round_trip_efficiency_pct))
    cur_soc_min = float(st.session_state.get("bess_sb_soc_min", cfg.soc_min_pct))
    cur_soc_max = float(st.session_state.get("bess_sb_soc_max", cfg.soc_max_pct))

    # --- Block 1 (Top): Theoretical 100% Zero-Deficit Reference Box ---
    sizing_diag = engine.calculate_excel_bess_sizing_and_diagnostics(
        load_series=load_df[power_col],
        grid_limit_kw=active_limit,
        round_trip_efficiency_pct=cur_rte,
        soc_min_pct=cur_soc_min,
        soc_max_pct=cur_soc_max,
        step_hours=0.25
    )

    with st.container(border=True):
        st.markdown("### :material/calculate: Minimum Required Battery Sizing (100% Zero-Deficit Reference)")
        st.caption(
            "Exact physical minimum sizing calculated using the Excel algorithm. "
            "Evaluates multi-day overload clusters and enforces grid recharge headroom constraints to ensure zero remaining deficit."
        )

        sz_col1, sz_col2, sz_col3, sz_col4 = st.columns(4)
        with sz_col1:
            st.metric(
                label="Min. Required Gross Capacity",
                value=f"{sizing_diag.min_required_gross_kwh:,.1f} kWh",
                help="Minimum nameplate storage capacity required to bridge the worst multi-peak deficit cluster."
            )
        with sz_col2:
            st.metric(
                label="Min. Required Usable Energy",
                value=f"{sizing_diag.min_required_usable_kwh:,.1f} kWh",
                help="Net chemical energy needed across the worst consecutive peak cluster."
            )
        with sz_col3:
            st.metric(
                label="Min. Required Discharge Power",
                value=f"{sizing_diag.min_required_discharge_kw:,.1f} kW",
                help="Continuous inverter discharge power required to shave the highest peak overload down to the grid limit."
            )
        with sz_col4:
            st.metric(
                label="Worst Multi-Peak Cluster Duration",
                value=f"{sizing_diag.worst_cluster_duration_hours:,.1f} hrs",
                help="Duration of the most demanding overload sequence until battery fully recharges below grid limit."
            )

        def _apply_100pct_zero_deficit():
            st.session_state["bess_sb_unit_count"] = int(sizing_diag.recommended_units)
            st.session_state["bess_sb_unit_kwh"] = float(sizing_diag.recommended_unit_kwh)
            dis_kw = float(np.ceil(sizing_diag.min_required_discharge_kw / 10.0) * 10.0)
            st.session_state["bess_sb_discharge_kw"] = dis_kw
            st.session_state["bess_sb_charge_kw"] = dis_kw

        st.button(
            ":material/auto_fix: Apply 100% Zero-Deficit Sizing",
            key="btn_apply_min_sizing",
            on_click=_apply_100pct_zero_deficit,
            use_container_width=True
        )

    st.markdown("---")

    # --- Block 2 (Middle Sub-Tabs): Manual 0.5C Setup vs. Pareto Tradeoff ---
    sub_tabs = st.tabs([
        ":material/tune: Hardware Specification & Operating Limits (Manual / 0.5C Setup)",
        ":material/analytics: Interactive Pareto Sizing & Coverage Tradeoff (Smart Sizing)"
    ])

    # Default initial values
    init_unit_count = int(st.session_state.get("bess_sb_unit_count", cfg.unit_count))
    init_unit_kwh = float(st.session_state.get("bess_sb_unit_kwh", cfg.unit_capacity_kwh))
    init_dis_kw = float(st.session_state.get("bess_sb_discharge_kw", cfg.max_discharge_power_kw))
    init_chg_kw = float(st.session_state.get("bess_sb_charge_kw", cfg.max_charge_power_kw))

    # --- Sub-Tab 2.1: Hardware Specification & Operating Limits ---
    with sub_tabs[0]:
        lock_05c = st.checkbox(
            "Lock to Standard 0.5 C (2-Hour Storage: Capacity kWh = 2 × Inverter Power kW)",
            value=bool(st.session_state.get("bess_sb_lock_05c", True)),
            key="bess_sb_lock_05c",
            help="When locked, capacity is automatically coupled to twice the inverter power rating."
        )

        with st.form("bess_hardware_form", clear_on_submit=False):
            b_col1, b_col2, b_col3 = st.columns(3)

            with b_col1:
                st.markdown("**Modular Storage Units:**")
                form_unit_count = st.number_input(
                    "Modular Unit Count",
                    min_value=1,
                    max_value=100,
                    value=init_unit_count,
                    step=1
                )
                form_unit_kwh = st.number_input(
                    "Capacity per Unit (kWh)",
                    min_value=10.0,
                    max_value=2000.0,
                    value=init_unit_kwh,
                    step=25.0
                )
                form_gross_kwh = float(form_unit_count * form_unit_kwh)
                st.caption(f"Configured Gross Nameplate: **{form_gross_kwh:,.1f} kWh**")

            with b_col2:
                st.markdown("**Inverter Power & Efficiency:**")
                form_dis_kw = st.number_input(
                    "Max Discharge Inverter (kW)",
                    min_value=1.0,
                    max_value=5000.0,
                    value=init_dis_kw,
                    step=10.0
                )
                form_chg_kw = st.number_input(
                    "Max Charge Inverter (kW)",
                    min_value=1.0,
                    max_value=5000.0,
                    value=init_chg_kw,
                    step=10.0
                )
                form_rte = st.slider(
                    "Round-Trip Efficiency (RTE %)",
                    min_value=70.0,
                    max_value=98.0,
                    value=cur_rte,
                    step=0.5
                )

            with b_col3:
                st.markdown("**State of Charge Boundaries:**")
                form_soc_min = st.slider(
                    "SoC Minimum Buffer (%)",
                    min_value=0.0,
                    max_value=40.0,
                    value=cur_soc_min,
                    step=5.0
                )
                form_soc_max = st.slider(
                    "SoC Maximum Limit (%)",
                    min_value=60.0,
                    max_value=100.0,
                    value=cur_soc_max,
                    step=5.0
                )
                form_dod = max(10.0, form_soc_max - form_soc_min)
                st.caption(f"Usable DoD Window: **{form_dod:.0f}%**")

            st.write("")
            form_submitted = st.form_submit_button(
                ":material/refresh: Update BESS Hardware & Run Simulation",
                use_container_width=True
            )

            if form_submitted:
                if lock_05c:
                    # Enforce 0.5C: Capacity kWh = 2 * Power kW
                    target_kwh = 2.0 * float(form_dis_kw)
                    computed_unit_kwh = round(target_kwh / float(form_unit_count), 1)
                    st.session_state["bess_sb_unit_count"] = int(form_unit_count)
                    st.session_state["bess_sb_unit_kwh"] = float(computed_unit_kwh)
                else:
                    st.session_state["bess_sb_unit_count"] = int(form_unit_count)
                    st.session_state["bess_sb_unit_kwh"] = float(form_unit_kwh)

                st.session_state["bess_sb_discharge_kw"] = float(form_dis_kw)
                st.session_state["bess_sb_charge_kw"] = float(form_chg_kw)
                st.session_state["bess_sb_rte_pct"] = float(form_rte)
                st.session_state["bess_sb_soc_min"] = float(form_soc_min)
                st.session_state["bess_sb_soc_max"] = float(form_soc_max)
                st.rerun()

    # --- Sub-Tab 2.2: Interactive Pareto Sizing & Coverage Tradeoff ---
    with sub_tabs[1]:
        st.markdown("#### :material/ssid_chart: Pareto Coverage Curve & Smart Sizing")
        st.caption(
            "Evaluate the diminishing returns of sizing for 100% standalone peak shaving. "
            "See how much battery capacity and CAPEX can be saved by allowing a small residual deficit."
        )

        # Compute precalculated Pareto curve across 10 support points
        pareto_res = engine.compute_pareto_coverage_curve(
            load_series=load_df[power_col],
            grid_limit_kw=active_limit,
            round_trip_efficiency_pct=cur_rte,
            soc_min_pct=cur_soc_min,
            soc_max_pct=cur_soc_max,
            step_hours=0.25
        )

        col_p_ctrl1, col_p_ctrl2 = st.columns([3, 2])
        with col_p_ctrl1:
            st.markdown("**Quick Target Coverage:**")
            q_p_cols = st.columns(4)
            if q_p_cols[0].button("80% Coverage", use_container_width=True):
                st.session_state["bess_sb_pareto_cov_pct"] = 80.0
                st.rerun()
            if q_p_cols[1].button("85% Coverage", use_container_width=True):
                st.session_state["bess_sb_pareto_cov_pct"] = 85.0
                st.rerun()
            if q_p_cols[2].button("90% Coverage", use_container_width=True):
                st.session_state["bess_sb_pareto_cov_pct"] = 90.0
                st.rerun()
            if q_p_cols[3].button("95% Coverage", use_container_width=True):
                st.session_state["bess_sb_pareto_cov_pct"] = 95.0
                st.rerun()

            selected_cov = st.slider(
                "Target Overload Energy Coverage (%)",
                min_value=70.0,
                max_value=100.0,
                value=float(st.session_state.get("bess_sb_pareto_cov_pct", 90.0)),
                step=1.0,
                key="bess_sb_pareto_cov_slider"
            )

        interp = pareto_res.interpolate(selected_cov)

        with col_p_ctrl2:
            st.markdown("**Smart Pareto Sizing Verdict:**")
            p_kpi1, p_kpi2, p_kpi3 = st.columns(3)
            with p_kpi1:
                st.metric("Battery Size", f"{interp['gross_kwh']:,.0f} kWh", delta=f"{interp['power_kw']:,.0f} kW", delta_color="off")
            with p_kpi2:
                st.metric("Capacity Saved", f"-{interp['capacity_savings_pct']:.1f}%", delta="vs. 100% Standalone", delta_color="normal")
            with p_kpi3:
                st.metric("Residual Deficit", f"{interp['residual_deficit_kwh']:,.0f} kWh", delta=f"+{interp['residual_peak_kw']:,.0f} kW peak", delta_color="inverse")

            def _apply_selected_pareto(p_kwh: float, p_kw: float):
                unit_kwh = 100.0 if p_kwh <= 500.0 else 250.0
                u_cnt = max(1, int(np.ceil(p_kwh / unit_kwh)))
                st.session_state["bess_sb_unit_count"] = u_cnt
                st.session_state["bess_sb_unit_kwh"] = round(p_kwh / u_cnt, 1)
                st.session_state["bess_sb_discharge_kw"] = round(p_kw, 1)
                st.session_state["bess_sb_charge_kw"] = round(p_kw, 1)

            st.button(
                f":material/check: Apply {selected_cov:.0f}% Pareto Size to Simulation",
                on_click=_apply_selected_pareto,
                args=(interp["gross_kwh"], interp["power_kw"]),
                use_container_width=True,
                key="btn_apply_pareto"
            )

        # Plotly Pareto hockey-stick chart
        fig_pareto = create_pareto_tradeoff_figure(pareto_res, selected_coverage_pct=selected_cov)
        st.plotly_chart(fig_pareto, use_container_width=True)

    # Active hardware configuration parameters
    active_unit_count = int(st.session_state.get("bess_sb_unit_count", init_unit_count))
    active_unit_kwh = float(st.session_state.get("bess_sb_unit_kwh", init_unit_kwh))
    active_total_kwh = float(active_unit_count * active_unit_kwh)
    active_dis_kw = float(st.session_state.get("bess_sb_discharge_kw", init_dis_kw))
    active_chg_kw = float(st.session_state.get("bess_sb_charge_kw", init_chg_kw))
    active_rte = float(st.session_state.get("bess_sb_rte_pct", cur_rte))
    active_soc_min = float(st.session_state.get("bess_sb_soc_min", cur_soc_min))
    active_soc_max = float(st.session_state.get("bess_sb_soc_max", cur_soc_max))
    active_dod = max(10.0, active_soc_max - active_soc_min)

    # Construct active BESSConfig
    active_bess_config = BESSConfig(
        capacity_kwh=active_total_kwh,
        unit_count=active_unit_count,
        unit_capacity_kwh=active_unit_kwh,
        battery_chemistry=cfg.battery_chemistry,
        max_charge_power_kw=active_chg_kw,
        max_discharge_power_kw=active_dis_kw,
        round_trip_efficiency_pct=active_rte,
        soc_min_pct=active_soc_min,
        soc_max_pct=active_soc_max,
        initial_soc_pct=active_soc_max,
        max_dod_pct=active_dod,
        dispatch_strategy="peak_shaving",
        peak_shaving_threshold_kw=active_limit,
        allow_grid_charging=True,
        currency=cfg.currency,
        cost_per_kwh=cfg.cost_per_kwh,
        fixed_installation_cost=cfg.fixed_installation_cost,
        annual_om_pct=cfg.annual_om_pct,
        cell_replacement_year=cfg.cell_replacement_year,
        cell_replacement_cost_pct=cfg.cell_replacement_cost_pct
    )

    # Run dispatch simulation
    sim_result = engine.simulate_sandbox_bess_dispatch(
        bess_config=active_bess_config,
        load_df=load_df,
        grid_limit_kw=active_limit,
        step_hours=0.25,
        power_col=power_col
    )

    # --- Block 3: Simultaneous Bottleneck Checklist & Paula's 5 Excel KPIs ---
    st.markdown("---")
    st.markdown("#### :material/checklist: Simultaneous Bottleneck Audit & Physical Constraints")
    st.caption("All 4 physical engineering criteria are evaluated simultaneously without short-circuiting.")

    bottleneck_audit = engine.evaluate_comprehensive_bottlenecks(
        load_series=load_df[power_col],
        grid_limit_kw=active_limit,
        bess_config=active_bess_config,
        step_hours=0.25,
        sim_result=sim_result
    )

    # Summary banner
    if bottleneck_audit.all_passed:
        st.success(
            "**:material/check_circle: 100% Physically Feasible: Zero Remaining Deficit**\n\n"
            "All physical constraints (inverter discharge power, multi-peak storage capacity, "
            "recharge power, and annual grid recharge headroom) are completely satisfied.",
            icon=":material/verified:"
        )
    else:
        st.warning(
            f"**:material/warning: Active Physical Bottlenecks Detected ({bottleneck_audit.failed_count} of 4 criteria flagged)**\n\n"
            "Review the simultaneous constraint checks below to identify the exact power or capacity deficits.",
            icon=":material/warning:"
        )

    # 4 Simultaneous Checks
    chk_cols = st.columns(4)
    for idx, check in enumerate(bottleneck_audit.checks):
        with chk_cols[idx]:
            icon = ":material/check_circle:" if check.passed else ":material/cancel:"
            st.markdown(f"**{icon} {check.name}**")
            st.metric(
                label="Configured vs. Required",
                value=f"{check.configured_value:,.1f} {check.unit}",
                delta=f"Req: {check.required_value:,.1f} {check.unit} ({check.margin_label})",
                delta_color="normal" if check.passed else "inverse",
                help=check.description
            )

    # Paula's 5 Excel Validation KPIs
    st.markdown("---")
    st.markdown("#### :material/fact_check: Excel Validation Summary (Identical Input Verification)")
    st.caption("Verify physical simulation outputs against the Excel benchmark across the 5 core dimensions.")

    val_col1, val_col2, val_col3, val_col4, val_col5 = st.columns(5)
    with val_col1:
        st.metric(
            label="Battery Capacity",
            value=f"{active_bess_config.capacity_kwh:,.1f} kWh",
            delta=f"Usable: {active_bess_config.effective_usable_kwh:,.1f} kWh",
            delta_color="off",
            help="Total gross nameplate battery storage capacity and net usable buffer."
        )
    with val_col2:
        c_rate = active_bess_config.max_discharge_power_kw / max(active_bess_config.capacity_kwh, 1.0)
        st.metric(
            label="Battery Power",
            value=f"{active_bess_config.max_discharge_power_kw:,.1f} kW",
            delta=f"Charge: {active_bess_config.max_charge_power_kw:,.1f} kW ({c_rate:.2f} C)",
            delta_color="off",
            help="Continuous discharge and charge power ratings with effective C-rate."
        )
    with val_col3:
        max_grid_import = float(sim_result.df_timeseries["P_Grid_kW"].max()) if "P_Grid_kW" in sim_result.df_timeseries.columns else 0.0
        st.metric(
            label="Max Grid Import",
            value=f"{max_grid_import:,.1f} kW",
            delta=f"Limit: {active_limit:,.1f} kW",
            delta_color="off",
            help="Peak grid import observed across all 15-minute dispatch intervals."
        )
    with val_col4:
        min_soc_pct = float(sim_result.df_timeseries["SoC_pct"].min()) if "SoC_pct" in sim_result.df_timeseries.columns else 0.0
        max_soc_pct = float(sim_result.df_timeseries["SoC_pct"].max()) if "SoC_pct" in sim_result.df_timeseries.columns else 0.0
        min_soc_kwh = float(sim_result.df_timeseries["SoC_kWh"].min()) if "SoC_kWh" in sim_result.df_timeseries.columns else 0.0
        st.metric(
            label="Observed SoC Range",
            value=f"{min_soc_pct:.1f}% – {max_soc_pct:.1f}%",
            delta=f"Min: {min_soc_kwh:,.1f} kWh",
            delta_color="off",
            help="Minimum and maximum battery State of Charge reached during the year."
        )
    with val_col5:
        rem_deficit_kw = float(sim_result.df_timeseries["P_Overload_Unmet_kW"].max()) if "P_Overload_Unmet_kW" in sim_result.df_timeseries.columns else 0.0
        rem_deficit_kwh = float(sim_result.df_timeseries["P_Overload_Unmet_kW"].sum() * 0.25) if "P_Overload_Unmet_kW" in sim_result.df_timeseries.columns else 0.0
        st.metric(
            label="Remaining Deficit (Excel 'Generator')",
            value=f"{rem_deficit_kwh:,.1f} kWh",
            delta=f"Peak Deficit: {rem_deficit_kw:,.1f} kW",
            delta_color="normal" if rem_deficit_kwh <= 0.05 else "inverse",
            help="Uncovered energy demand above the grid limit (modeled as backup generator in Excel)."
        )

    # --- Block 4 (Bottom): Synchronized 2-in-1 Timeseries Chart ---
    st.markdown("---")
    st.markdown("#### :material/monitoring: Synchronized 15-Min Power Dispatch & Battery SoC")
    st.caption(
        "Linked 2-panel Plotly subplot (shared X-axis): Zooming, panning, or selecting time ranges "
        "synchronously updates both active power flows (kW) and battery State of Charge envelope."
    )

    init_focus = compute_focus_range(sim_result.df_timeseries, days=7.0)

    fig_synced = create_synced_dispatch_soc_figure(
        df=sim_result.df_timeseries,
        grid_limit_kw=active_limit,
        soc_min_pct=active_soc_min,
        soc_max_pct=active_soc_max,
        capacity_kwh=active_total_kwh,
        initial_range=init_focus
    )
    st.plotly_chart(fig_synced, use_container_width=True)

    # Store in session state for cross-tab sharing
    st.session_state["bess_sb_active_config"] = active_bess_config
    st.session_state["bess_sb_sim_result"] = sim_result
    st.session_state["bess_sb_active_limit_kw"] = active_limit

    return sim_result
