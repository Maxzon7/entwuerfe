"""
========================================================================================
Tab 4: Battery Energy Storage System (BESS) View (ui/tab4_bess/view.py)
========================================================================================

Description:
------------
Orchestrates the BESS peak shaving simulation and grid constraint mitigation (Tab 4):
  - Ingests active facility consumption profile from Tab 1.
  - Sub-Scenario Activation Guard: Status Quo remains pure grid baseline; BESS is configured on sub-scenarios.
  - Pre-Configuration Grid & Overload Diagnostic Panel:
      * Contracted Grid Limit (kW) input/discovery.
      * Peak demand, max overload peak, duration of longest consecutive grid violation, total exceedance energy.
      * Interactive exceedance visual preview.
  - Assignment-Aligned BESS Technical Form (`st.form`):
      * Sizing (Modular units x kWh = Nominal capacity).
      * Chemistry (LFP, NMC, Flow Battery).
      * Charge/Discharge power (kW) and live C-Rate.
      * Round-trip efficiency (%), Safe SoC envelope (SoC_min, SoC_max, initial SoC).
      * Peak shaving threshold cap (kW) and recharge strategy.
  - 15-Minute Electrical Simulation Engine Execution.
  - Key Performance Indicators (Peak shaving kW & %, violations eliminated %, annual MWh throughput, EFC cycles).
  - 4 High-Contrast Plotly Dispatch Charts.
"""

from typing import Optional, Dict, Any, Tuple
import streamlit as st
import pandas as pd
import numpy as np

from current_model.models.bess import BESSConfig, BESSKPIs, get_bess_presets
from current_model.models.scenario import ProjectContainer, SubScenario
from current_model.models.contract import Contract
from current_model.core.project_io import export_project_from_session, sync_active_scenario_into_session
from current_model.core.bess_engine import (
    analyze_grid_violations,
    simulate_bess_dispatch,
    compute_average_week_dispatch,
    BESSSimulationResult
)
from current_model.core.synthetic_engine import aggregate_synthetic_year
from current_model.models.presets import get_industry_preset_consumers
from current_model.ui.common.cards import render_kpi_card
from current_model.ui.common.session_utils import (
    find_active_load_data_in_session,
    find_active_contract_in_session,
    get_load_profile_summary
)
from current_model.ui.tab4_bess.charts import (
    create_grid_violation_preview_figure,
    create_average_week_dispatch_figure,
    create_bess_soc_analysis_figure,
    create_bess_dispatch_timeseries_figure,
    create_monthly_bess_throughput_figure
)
from current_model.ui.tab4_bess.financial_view import render_tab4_2_financial


def render_tab4_bess(key_prefix: str = "app_tab4_bess") -> None:
    """
    Main entry point for Tab 4: Battery Energy Storage System (BESS).
    Structured into Sub-Tabs:
      - 4.1 Technical Dispatch & Simulation
      - 4.2 Financial & Commercial Viability
    """
    subtab_tech, subtab_fin = st.tabs([
        ":material/battery_charging_full: 4.1 Technical Dispatch & Simulation",
        ":material/payments: 4.2 Financial & Commercial Viability"
    ])

    with subtab_tech:
        render_tab4_1_technical(key_prefix=f"{key_prefix}_tech")

    with subtab_fin:
        render_tab4_2_financial(key_prefix=f"{key_prefix}_fin")


def render_tab4_1_technical(key_prefix: str = "tab4_bess") -> None:
    """
    Renders Sub-Tab 4.1: Technical BESS Peak Shaving & 15-Minute Dispatch Simulation.
    """
    project: ProjectContainer = export_project_from_session()
    active_sub = project.get_active_scenario()

    # --------------------------------------------------------------------------
    # 0. Status Quo (Base Benchmark) Guard
    # --------------------------------------------------------------------------
    if active_sub is None:
        st.info(
            "### :material/anchor: Status Quo (Base Benchmark) Active\n\n"
            "The **Status Quo (Base Scenario)** represents your pure utility grid electricity baseline without Battery Energy Storage (0 kWh BESS).\n\n"
            "To configure, size, and simulate a Battery Energy Storage System (BESS) for peak shaving and grid congestion mitigation, switch to an active Sub-Scenario branch or instantiate a new branch below."
        )
        c_act1, c_act2, _ = st.columns([3.5, 3.5, 5])
        with c_act1:
            if project.sub_scenarios:
                first_sub = project.sub_scenarios[0]
                if st.button(f"Switch to '{first_sub.name}'", icon=":material/arrow_forward:", type="primary", use_container_width=True, key=f"{key_prefix}_switch_sub1_btn"):
                    project.active_sub_scenario_id = first_sub.id
                    st.session_state["project_container"] = project
                    sync_active_scenario_into_session(project, auto_execute=False)
                    st.rerun()
        with c_act2:
            if st.button("Instantiate New BESS Branch", icon=":material/add_circle:", use_container_width=True, key=f"{key_prefix}_instantiate_new_btn"):
                new_sub = SubScenario(
                    name=f"Sub-Scenario {len(project.sub_scenarios) + 1}: BESS Peak Shaving",
                    color_code="#059669",
                    include_bess=True,
                    bess_config=BESSConfig(
                        capacity_kwh=200.0,
                        unit_count=2,
                        unit_capacity_kwh=100.0,
                        battery_chemistry="LFP (Lithium Iron Phosphate - Standard)",
                        max_charge_power_kw=100.0,
                        max_discharge_power_kw=100.0,
                        round_trip_efficiency_pct=90.0,
                        soc_min_pct=10.0,
                        soc_max_pct=95.0,
                        dispatch_strategy="peak_shaving",
                        peak_shaving_threshold_kw=120.0
                    )
                )
                project.add_sub_scenario(new_sub)
                project.active_sub_scenario_id = new_sub.id
                st.session_state["project_container"] = project
                sync_active_scenario_into_session(project, auto_execute=False)
                st.rerun()
        return

    # --------------------------------------------------------------------------
    # Sub-Scenario Active Configuration Header
    # --------------------------------------------------------------------------
    st.markdown(f"### Battery Energy Storage System (BESS) Simulator")
    st.caption(
        f"Active Branch: **{active_sub.name}** | High-precision 15-minute battery dispatch for peak shaving, "
        f"grid congestion mitigation, contracted capacity optimization, and supply stabilization."
    )

    # --------------------------------------------------------------------------
    # 1. Active Load Discovery
    # --------------------------------------------------------------------------
    df_load, load_desc, p_col = find_active_load_data_in_session()

    if df_load is None or df_load.empty:
        st.info(
            "**No active consumption profile detected from Tab 1.**\n\n"
            "Configure a profile in **Tab 1: Consumption** (Synthetic Simulator or CSV Ingestion), "
            "or load a demo profile below to explore the BESS simulation:"
        )
        col_demo1, col_demo2, _ = st.columns([3, 3, 4])
        with col_demo1:
            if st.button("Load 365-Day Industry Preset", icon=":material/bolt:", key=f"{key_prefix}_load_demo_ind_btn"):
                consumers = get_industry_preset_consumers()
                df_year, _, _ = aggregate_synthetic_year(consumers, year=2025)
                st.session_state["active_synthetic_df"] = df_year
                st.session_state["tab1_active_source"] = "synthetic"
                st.rerun()
        with col_demo2:
            if st.button("Navigate to Tab 1 (Consumption)", icon=":material/arrow_forward:", key=f"{key_prefix}_go_tab1_btn"):
                st.info("Switch to Tab 1 at the top of the page to import your real meter CSV data.")
        return

    load_summary = get_load_profile_summary(df_load, power_col=p_col)

    # Data gaps notice for BESS simulation
    bess_gaps = load_summary.get("gaps", [])
    if bess_gaps:
        gaps_text = ", ".join([f"{g['start_str']} to {g['end_str']} ({g['duration_days']:.1f} days)" for g in bess_gaps[:3]])
        if len(bess_gaps) > 3:
            gaps_text += f" and {len(bess_gaps) - 3} additional intervals"
        st.warning(
            f":material/warning: **Data Gaps Detected in Active Profile:** Due to missing meter data, "
            f"the period(s) from **{gaps_text}** cannot be accurately resolved. "
            f"During these intervals, BESS charging and discharging are bypassed and excluded from peak shaving calculations "
            f"to prevent unphysical battery cycling.",
            icon=":material/warning:"
        )
    # 2. Pre-Configuration Grid Overload & Peak Diagnostic Panel (Above st.form)
    # --------------------------------------------------------------------------
    st.markdown("##### 1. Grid Connection Limit & Overload Diagnostics")
    st.caption("Analyzes your facility demand against the contracted grid capacity to identify peak exceedances, violation durations, and required shaving energy:")

    active_contract: Optional[Contract] = find_active_contract_in_session()
    contract_kw = float(getattr(active_contract, "contracted_capacity_kw", 0.0) or 0.0) if active_contract else 0.0

    # Grid Limit Input (Auto-filled with Tab 2 contract if present, else user input/default)
    gl_col1, gl_col2 = st.columns([3.5, 6.5])
    with gl_col1:
        default_gl = contract_kw if contract_kw > 0 else round(load_summary["peak_kw"] * 0.8, 0)
        default_gl = max(10.0, default_gl)

        grid_limit_val = st.number_input(
            "Contracted Grid Connection Limit (kW):",
            min_value=1.0,
            max_value=100000.0,
            value=float(st.session_state.get(f"{key_prefix}_grid_limit_kw", default_gl)),
            step=10.0,
            key=f"{key_prefix}_grid_limit_kw",
            help="The maximum allowable power draw from the utility grid connection before overload fees, curtailment, or breaker tripping occur."
        )

    with gl_col2:
        if active_contract and contract_kw > 0:
            st.info(f":material/link: Contract linked: **{active_contract.name}** (Contracted Capacity: **{contract_kw:,.1f} kW**). You can adjust this limit above to test alternative grid constraints.", icon=":material/info:")
        else:
            st.caption(":material/tune: *No contracted capacity set in Tab 3 (Current Contract). You can freely set your site grid connection limit above to simulate peak shaving.*")

    # Run Pre-Simulation Violation Diagnostics
    p_load_arr = df_load[p_col].to_numpy(dtype=float) if p_col in df_load.columns else df_load.iloc[:, 0].to_numpy(dtype=float)
    pre_diag = analyze_grid_violations(p_load_arr, grid_limit_val, step_hours=load_summary.get("hours_per_step", 0.25))

    # Pre-Diagnostic KPI Cards
    d1, d2, d3, d4, d5 = st.columns(5)
    with d1:
        render_kpi_card(
            "Contracted Grid Limit",
            f"{pre_diag['grid_limit_kw']:,.1f} kW",
            "Max utility connection capacity",
            status="ok"
        )
    with d2:
        render_kpi_card(
            "Facility Peak Demand",
            f"{pre_diag['peak_load_kw']:,.1f} kW",
            f"Annual load: {load_summary['total_mwh']:,.1f} MWh",
            status="default"
        )
    with d3:
        has_over = pre_diag["overload_peak_kw"] > 0
        render_kpi_card(
            "Max Grid Overload Peak",
            f"{pre_diag['overload_peak_kw']:,.1f} kW" if has_over else "0.0 kW",
            f"Exceeds limit by +{(pre_diag['overload_peak_kw'] / max(1.0, pre_diag['grid_limit_kw']) * 100.0):.1f}%" if has_over else "No grid limit exceedance",
            status="alert" if has_over else "ok"
        )
    with d4:
        render_kpi_card(
            "Longest Violation Duration",
            f"{pre_diag['longest_violation_run_hours']:.1f} Hours",
            f"{pre_diag['longest_violation_run_intervals']} consecutive 15-min intervals",
            status="alert" if pre_diag["longest_violation_run_hours"] > 0 else "ok"
        )
    with d5:
        has_min_cap = pre_diag.get("min_bess_capacity_kwh", 0.0) > 0
        render_kpi_card(
            "Min. BESS Capacity",
            f"{pre_diag['min_bess_capacity_kwh']:,.1f} kWh" if has_min_cap else "0.0 kWh",
            f"Worst-case event ({pre_diag['worst_event_duration_hours']:.1f}h run)" if has_min_cap else "No grid limit exceedance",
            status="alert" if has_min_cap else "ok"
        )

    # Exceedance Preview Expander
    if pre_diag["has_violations"]:
        with st.expander("Interactive Grid Overload & Exceedance Profile (Preview)", icon=":material/crisis_alert:", expanded=False):
            fig_prev = create_grid_violation_preview_figure(df_load, grid_limit_val, power_col=p_col)
            st.plotly_chart(fig_prev, use_container_width=True)

    st.divider()

    # --------------------------------------------------------------------------
    # 3. BESS Configuration Form - Mapped to DRACBV Section 7.4
    # --------------------------------------------------------------------------
    st.markdown("##### 2. Battery Energy Storage System (BESS) Technical Configuration")
    st.caption("Configure battery capacity, chemistry, charge/discharge power ratings, safe operating envelope, and peak shaving targets:")

    presets = get_bess_presets()
    preset_names = ["Custom Sizing"] + list(presets.keys())

    # Session state keys
    k_units = f"{key_prefix}_units"
    k_unit_kwh = f"{key_prefix}_unit_kwh"
    k_chem = f"{key_prefix}_chem"
    k_dis = f"{key_prefix}_dis_kw"
    k_chg = f"{key_prefix}_chg_kw"
    k_rte = f"{key_prefix}_rte"
    k_soc_min = f"{key_prefix}_soc_min"
    k_soc_max = f"{key_prefix}_soc_max"
    k_init_soc = f"{key_prefix}_init_soc"
    k_shaving_cap = f"{key_prefix}_shaving_cap"
    k_recharge = f"{key_prefix}_recharge_mode"
    state_res_key = f"{key_prefix}_sim_result"

    # Default BESS config
    curr_bess_cfg: Optional[BESSConfig] = active_sub.bess_config or st.session_state.get(f"{key_prefix}_config")
    if curr_bess_cfg is None:
        curr_bess_cfg = BESSConfig(
            capacity_kwh=200.0,
            unit_count=2,
            unit_capacity_kwh=100.0,
            battery_chemistry="LFP (Lithium Iron Phosphate - Standard)",
            max_charge_power_kw=100.0,
            max_discharge_power_kw=100.0,
            peak_shaving_threshold_kw=grid_limit_val
        )

    # Toolbar: Load Benchmark BESS / Reset Form
    act_col1, act_col2, _ = st.columns([3.5, 2.5, 4])
    with act_col1:
        if st.button(
            "Load Benchmark Case (200 kWh / 100 kW)",
            icon=":material/play_circle:",
            key=f"{key_prefix}_load_benchmark_btn",
            help="Loads the standard 200 kWh / 100 kW industrial LFP storage benchmark."
        ):
            bench_cfg = BESSConfig(
                capacity_kwh=200.0,
                unit_count=2,
                unit_capacity_kwh=100.0,
                battery_chemistry="LFP (Lithium Iron Phosphate - Standard)",
                max_charge_power_kw=100.0,
                max_discharge_power_kw=100.0,
                round_trip_efficiency_pct=90.0,
                soc_min_pct=10.0,
                soc_max_pct=95.0,
                initial_soc_pct=50.0,
                dispatch_strategy="peak_shaving",
                peak_shaving_threshold_kw=grid_limit_val,
                cost_per_kwh=350.0,
                fixed_installation_cost=5000.0
            )
            st.session_state[k_units] = 2
            st.session_state[k_unit_kwh] = 100.0
            st.session_state[k_chem] = "LFP (Lithium Iron Phosphate - Standard)"
            st.session_state[k_dis] = 100.0
            st.session_state[k_chg] = 100.0
            st.session_state[k_rte] = 90.0
            st.session_state[k_soc_min] = 10.0
            st.session_state[k_soc_max] = 95.0
            st.session_state[k_init_soc] = 50.0
            st.session_state[k_shaving_cap] = float(grid_limit_val)
            st.session_state[f"{key_prefix}_config"] = bench_cfg
            st.session_state["app_tab4_bess_config"] = bench_cfg
            active_sub.bess_config = bench_cfg
            active_sub.include_bess = True
            st.session_state["project_container"] = project
            if state_res_key in st.session_state:
                del st.session_state[state_res_key]
            st.rerun()

    with act_col2:
        if st.button(
            "Reset / Clear BESS",
            icon=":material/restart_alt:",
            key=f"{key_prefix}_reset_btn",
            help="Resets all BESS inputs back to empty state and removes BESS from this branch."
        ):
            active_sub.remove_component("bess")
            st.session_state["project_container"] = project
            sync_active_scenario_into_session(project, auto_execute=False)
            st.rerun()

    # Preset selection handling
    preset_options = ["-- Select Standard Preset --"] + list(presets.keys())
    preset_choice = st.selectbox(
        "Load Commercial & Industrial BESS Preset:",
        options=preset_options,
        index=0,
        key=f"{key_prefix}_preset_select_widget",
        help="Quickly pre-fill standard industrial battery parameters."
    )

    if preset_choice in presets:
        p_obj = presets[preset_choice]
        st.session_state[k_units] = p_obj.unit_count
        st.session_state[k_unit_kwh] = p_obj.unit_capacity_kwh
        st.session_state[k_chem] = p_obj.battery_chemistry
        st.session_state[k_dis] = float(p_obj.max_discharge_power_kw)
        st.session_state[k_chg] = float(p_obj.max_charge_power_kw)
        st.session_state[k_rte] = float(p_obj.round_trip_efficiency_pct)
        st.session_state[k_soc_min] = float(p_obj.soc_min_pct)
        st.session_state[k_soc_max] = float(p_obj.soc_max_pct)
        st.session_state[k_init_soc] = float(p_obj.initial_soc_pct)
        st.session_state[k_shaving_cap] = float(p_obj.peak_shaving_threshold_kw or grid_limit_val)
        st.session_state[f"{key_prefix}_config"] = p_obj
        st.session_state["app_tab4_bess_config"] = p_obj
        active_sub.bess_config = p_obj
        active_sub.include_bess = True
        st.session_state["project_container"] = project
        if state_res_key in st.session_state:
            del st.session_state[state_res_key]
        st.rerun()

    # Initial default values for session keys if not yet present
    if k_units not in st.session_state:
        st.session_state[k_units] = getattr(curr_bess_cfg, "unit_count", 2)
    if k_unit_kwh not in st.session_state:
        st.session_state[k_unit_kwh] = getattr(curr_bess_cfg, "unit_capacity_kwh", 100.0)
    if k_chem not in st.session_state:
        st.session_state[k_chem] = getattr(curr_bess_cfg, "battery_chemistry", "LFP (Lithium Iron Phosphate - Standard)")
    if k_dis not in st.session_state:
        st.session_state[k_dis] = float(curr_bess_cfg.max_discharge_power_kw)
    if k_chg not in st.session_state:
        st.session_state[k_chg] = float(curr_bess_cfg.max_charge_power_kw)
    if k_rte not in st.session_state:
        st.session_state[k_rte] = float(curr_bess_cfg.round_trip_efficiency_pct)
    if k_soc_min not in st.session_state:
        st.session_state[k_soc_min] = float(curr_bess_cfg.soc_min_pct)
    if k_soc_max not in st.session_state:
        st.session_state[k_soc_max] = float(curr_bess_cfg.soc_max_pct)
    if k_init_soc not in st.session_state:
        st.session_state[k_init_soc] = float(curr_bess_cfg.initial_soc_pct)
    if k_shaving_cap not in st.session_state:
        st.session_state[k_shaving_cap] = float(curr_bess_cfg.peak_shaving_threshold_kw or grid_limit_val)

    # --------------------------------------------------------------------------
    # Technical Specifications Form (Buffered in st.form to eliminate UI lag & reruns on input)
    # --------------------------------------------------------------------------
    with st.form(key=f"{key_prefix}_specs_form", clear_on_submit=False):
        # Section A: Storage Capacity & Modular Units
        st.markdown("###### A. Storage Capacity & Unit Sizing")
        col_c1, col_c2, col_c3 = st.columns([1.2, 1.2, 1.6])

        with col_c1:
            unit_count = st.number_input(
                "Number of Battery Units:",
                min_value=1,
                max_value=100,
                step=1,
                key=k_units,
                help="Modular battery cabinet / rack units."
            )

        with col_c2:
            unit_kwh = st.number_input(
                "Capacity per Unit (kWh):",
                min_value=10.0,
                max_value=5000.0,
                step=10.0,
                key=k_unit_kwh,
                help="Nominal energy rating per individual battery unit."
            )

        calc_nom_kwh = float(unit_count * unit_kwh)
        with col_c3:
            st.metric(
                "Configured Nominal Capacity",
                f"{calc_nom_kwh:,.1f} kWh",
                f"↑ {unit_count} {'Unit' if unit_count == 1 else 'Units'} × {unit_kwh:,.0f} kWh"
            )

        # Section B: Power Ratings, C-Rate & Efficiency
        st.markdown("###### B. Power Ratings & Operational Boundary")
        col_p1, col_p2, col_p3, col_p4 = st.columns(4)

        with col_p1:
            dis_kw = st.number_input(
                "Max Continuous Discharge Power (kW):",
                min_value=1.0,
                max_value=50000.0,
                step=10.0,
                key=k_dis,
                help="Maximum continuous active power the battery can inject to shave peaks."
            )

        with col_p2:
            chg_kw = st.number_input(
                "Max Continuous Charge Power (kW):",
                min_value=1.0,
                max_value=50000.0,
                step=10.0,
                key=k_chg,
                help="Maximum continuous charging power from grid headroom."
            )

        with col_p3:
            calc_c_rate = dis_kw / max(1.0, calc_nom_kwh)
            st.metric(
                "Configured C-Rate",
                f"{calc_c_rate:.2f} C",
                f"↑ Full discharge in ~{1.0/max(0.01, calc_c_rate):.1f} h"
            )

        with col_p4:
            rte_pct = st.number_input(
                "Round-Trip AC/AC Efficiency (%):",
                min_value=50.0,
                max_value=99.0,
                step=1.0,
                key=k_rte,
                help="Combined conversion efficiency (including inverter, cabling, and battery cell losses)."
            )

        # Section C: Safe SoC Envelope & Dispatch Target
        st.markdown("###### C. SoC Envelope & Peak Shaving Dispatch Target")
        col_s1, col_s2, col_s3, col_s4 = st.columns(4)

        with col_s1:
            soc_min = st.number_input(
                "Minimum SoC Boundary (%):",
                min_value=0.0,
                max_value=50.0,
                step=5.0,
                key=k_soc_min,
                help="Reserve margin to prevent deep discharge degradation."
            )

        with col_s2:
            soc_max = st.number_input(
                "Maximum SoC Boundary (%):",
                min_value=50.0,
                max_value=100.0,
                step=5.0,
                key=k_soc_max,
                help="Upper charge limit to avoid overvoltage stress."
            )

        with col_s3:
            init_soc = st.number_input(
                "Initial SoC at Simulation Start (%):",
                min_value=0.0,
                max_value=100.0,
                step=5.0,
                key=k_init_soc
            )

        with col_s4:
            calc_usable_kwh = calc_nom_kwh * (max(0.0, soc_max - soc_min) / 100.0)
            st.metric(
                "Configured Usable Capacity",
                f"{calc_usable_kwh:,.1f} kWh",
                f"↑ DoD: {(soc_max - soc_min):.0f}%"
            )

        # Section D: Peak Shaving Threshold & Recharge Strategy
        col_t1, col_t2 = st.columns(2)
        with col_t1:
            shaving_cap_kw = st.number_input(
                "Target Peak Shaving Grid Cap (kW):",
                min_value=1.0,
                max_value=100000.0,
                step=10.0,
                key=k_shaving_cap,
                help="The battery will discharge to ensure net grid import never exceeds this threshold (defaults to your Grid Connection Limit)."
            )

        recharge_options = [
            "Opportunistic Capping (Recharge whenever Load < Target Grid Cap)",
            "Scheduled Off-Peak / Valley Hours (Recharge exclusively 00:00 - 06:00)"
        ]
        curr_recharge_val = st.session_state.get(k_recharge, recharge_options[0])
        recharge_idx = recharge_options.index(curr_recharge_val) if curr_recharge_val in recharge_options else 0

        with col_t2:
            recharge_mode = st.selectbox(
                "Recharge Strategy:",
                options=recharge_options,
                index=recharge_idx,
                key=k_recharge,
                help="Defines when the battery is allowed to draw power from the grid to replenish its charge."
            )

        # Action Button (Inside st.form)
        submitted = st.form_submit_button(
            "Calculate BESS Peak Shaving & Electrical Dispatch",
            icon=":material/calculate:",
            type="primary",
            use_container_width=True
        )

    # Compute values and handle synchronization
    total_nom_kwh = float(unit_count * unit_kwh)
    clamped_init_soc = float(min(float(soc_max), max(float(soc_min), float(init_soc))))

    if submitted:
        updated_bess_cfg = BESSConfig(
            capacity_kwh=total_nom_kwh,
            unit_count=int(unit_count),
            unit_capacity_kwh=float(unit_kwh),
            battery_chemistry=getattr(curr_bess_cfg, "battery_chemistry", "LFP (Lithium Iron Phosphate - Standard)"),
            max_charge_power_kw=float(chg_kw),
            max_discharge_power_kw=float(dis_kw),
            round_trip_efficiency_pct=float(rte_pct),
            soc_min_pct=float(soc_min),
            soc_max_pct=float(soc_max),
            initial_soc_pct=clamped_init_soc,
            max_dod_pct=float(soc_max - soc_min),
            dispatch_strategy="tariff_arbitrage" if "Scheduled" in recharge_mode else "peak_shaving",
            peak_shaving_threshold_kw=float(shaving_cap_kw),
            cost_per_kwh=curr_bess_cfg.cost_per_kwh,
            fixed_installation_cost=curr_bess_cfg.fixed_installation_cost,
            annual_om_pct=curr_bess_cfg.annual_om_pct,
            cell_replacement_year=curr_bess_cfg.cell_replacement_year,
            cell_replacement_cost_pct=curr_bess_cfg.cell_replacement_cost_pct
        )
        st.session_state[f"{key_prefix}_config"] = updated_bess_cfg
        st.session_state["app_tab4_bess_config"] = updated_bess_cfg
        active_sub.bess_config = updated_bess_cfg
        active_sub.include_bess = True
        st.session_state["project_container"] = project
    else:
        updated_bess_cfg = active_sub.bess_config or curr_bess_cfg

    # --------------------------------------------------------------------------
    # 4. Simulation Execution & Calculation
    # --------------------------------------------------------------------------
    sim_res: Optional[BESSSimulationResult] = st.session_state.get(state_res_key)

    need_simulation = (
        (sim_res is None or submitted)
        and (df_load is not None and not df_load.empty and updated_bess_cfg.capacity_kwh > 0)
    )

    if need_simulation and df_load is not None and not df_load.empty and updated_bess_cfg.capacity_kwh > 0:
        with st.spinner("Computing 15-minute physical BESS dispatch & peak shaving..."):
            try:
                sim_res = simulate_bess_dispatch(
                    bess_config=updated_bess_cfg,
                    load_df=df_load,
                    grid_limit_kw=float(updated_bess_cfg.peak_shaving_threshold_kw),
                    step_hours=load_summary.get("hours_per_step", 0.25),
                    power_col=p_col
                )
                st.session_state[state_res_key] = sim_res
                active_sub.summary_kpis["bess_peak_shaved_kw"] = sim_res.kpis.peak_shaved_kw
                active_sub.summary_kpis["bess_throughput_kwh"] = sim_res.kpis.total_discharged_kwh
                st.session_state["project_container"] = project
                if submitted:
                    st.toast(f"BESS Dispatch Updated: {updated_bess_cfg.capacity_kwh:,.0f} kWh ({updated_bess_cfg.max_discharge_power_kw:,.0f} kW)", icon="⚡")
            except Exception as err:
                st.error(f"BESS Simulation Error: {err}", icon=":material/error:")
                return

    if sim_res is None:
        st.info(
            "Ready to simulate BESS. Please ensure an active load profile is loaded from Tab 1.",
            icon=":material/info:"
        )
        return

    kpis = sim_res.kpis
    df_ts = sim_res.df_timeseries
    d_after = sim_res.diagnostics_after

    st.divider()

    # --------------------------------------------------------------------------
    # 5. Coupled Performance Metrics (KPI Cards)
    # --------------------------------------------------------------------------
    st.markdown("##### 3. BESS Peak Shaving & Technical Performance Metrics")

    orig_pk = pre_diag["peak_load_kw"]
    res_pk = d_after["peak_load_kw"]
    shaved_kw = kpis.peak_shaved_kw
    shaved_pct = (shaved_kw / max(1.0, orig_pk) * 100.0) if orig_pk > 0 else 0.0

    violations_eliminated = pre_diag["total_violation_intervals"] - d_after["total_violation_intervals"]
    eliminated_pct = (violations_eliminated / max(1, pre_diag["total_violation_intervals"]) * 100.0) if pre_diag["total_violation_intervals"] > 0 else 100.0

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        render_kpi_card(
            "Peak Demand Reduction",
            f"-{shaved_kw:,.1f} kW",
            f"Original: {orig_pk:,.1f} kW -> Residual: {res_pk:,.1f} kW (-{shaved_pct:.1f}%)",
            status="ok" if shaved_kw > 0.1 else "default"
        )
    with m2:
        render_kpi_card(
            "Grid Violations Eliminated",
            f"{eliminated_pct:.1f} %",
            f"Remaining violations: {d_after['total_violation_intervals']} intervals ({d_after['total_violation_hours']:.1f} h)",
            status="ok" if eliminated_pct > 95.0 else ("alert" if d_after["total_violation_intervals"] > 0 else "ok")
        )
    with m3:
        render_kpi_card(
            "Annual Energy Discharged",
            f"{kpis.total_discharged_kwh / 1000.0:,.2f} MWh",
            f"Total charged: {kpis.total_charged_kwh / 1000.0:,.2f} MWh",
            status="ok"
        )
    with m4:
        render_kpi_card(
            "Equivalent Full Cycles",
            f"{kpis.equivalent_full_cycles:.1f} EFC/a",
            f"Avg throughput: {kpis.avg_daily_throughput_kwh:,.1f} kWh/day"
        )

    # Secondary row of metrics
    s1, s2, s3, s4 = st.columns(4)
    with s1:
        render_kpi_card(
            "Round-Trip Conversion Losses",
            f"{kpis.round_trip_loss_kwh / 1000.0:,.2f} MWh",
            f"Efficiency: {updated_bess_cfg.round_trip_efficiency_pct:.1f}% AC/AC"
        )
    with s2:
        render_kpi_card(
            "Effective Usable Capacity",
            f"{updated_bess_cfg.effective_usable_kwh:,.1f} kWh",
            f"Nominal: {updated_bess_cfg.capacity_kwh:,.0f} kWh (DoD: {updated_bess_cfg.max_dod_pct:.0f}%)"
        )
    with s3:
        render_kpi_card(
            "Unmet Overload Peak",
            f"{d_after['overload_peak_kw']:,.1f} kW",
            f"Remaining exceedance energy: {d_after['total_exceedance_energy_mwh']:,.2f} MWh",
            status="alert" if d_after["overload_peak_kw"] > 0 else "ok"
        )
    with s4:
        render_kpi_card(
            "Longest Residual Overload",
            f"{d_after['longest_violation_run_hours']:.1f} Hours",
            f"Reduced from {pre_diag['longest_violation_run_hours']:.1f} h (Before BESS)",
            status="ok" if d_after["longest_violation_run_hours"] == 0 else "default"
        )

    st.write("")

    # --------------------------------------------------------------------------
    # 6. Interactive Visual Dispatch Analytics (4 Modern Tabs)
    # --------------------------------------------------------------------------
    st.markdown("##### 4. Visual Dispatch & Battery Dynamics Analysis")

    tab_avg_week, tab_ts, tab_monthly = st.tabs([
        ":material/view_week: Representative Average Week (7-Day Dispatch)",
        ":material/timeline: 15-Minute Timeseries Dispatch & Battery SoC (Zoomable)",
        ":material/bar_chart: Monthly Throughput & Cycles"
    ])

    with tab_avg_week:
        st.caption(":material/info: *Continuous 168-hour representative Monday–Sunday profile averaged across the full simulation period, showing peak shaving dispatch and recharging.*")
        df_avg_week = compute_average_week_dispatch(df_ts, step_hours=load_summary.get("hours_per_step", 0.25))
        fig_avg = create_average_week_dispatch_figure(
            df_avg_week=df_avg_week,
            target_cap_kw=shaving_cap_kw,
            capacity_kwh=updated_bess_cfg.capacity_kwh
        )
        st.plotly_chart(fig_avg, use_container_width=True)

    with tab_ts:
        st.caption(":material/info: *High-resolution 15-minute interval active power dispatch profile, directly coupled with the battery State of Charge (SoC %) dynamics below:*")
        fig_ts = create_bess_dispatch_timeseries_figure(
            df=df_ts,
            grid_limit_kw=grid_limit_val,
            target_cap_kw=shaving_cap_kw,
            capacity_kwh=updated_bess_cfg.capacity_kwh
        )
        st.plotly_chart(fig_ts, use_container_width=True)

        fig_soc_dyn = create_bess_soc_analysis_figure(df=df_ts, bess_config=updated_bess_cfg)
        st.plotly_chart(fig_soc_dyn, use_container_width=True)

    with tab_monthly:
        st.caption(":material/info: *Monthly discharged energy (MWh) and equivalent full cycle counts over the annual operation cycle.*")
        fig_monthly = create_monthly_bess_throughput_figure(sim_res.monthly_metrics)
        st.plotly_chart(fig_monthly, use_container_width=True)

    # --------------------------------------------------------------------------
    # 7. Itemized Comparison Table (Status Quo vs With BESS)
    # --------------------------------------------------------------------------
    with st.expander("Itemized Grid Compliance & Peak Comparison: Status Quo vs. With BESS", icon=":material/table_chart:", expanded=False):
        comp_rows = [
            {
                "Metric": "Peak Grid Demand",
                "Status Quo (No BESS)": f"{orig_pk:,.1f} kW",
                "With BESS": f"{res_pk:,.1f} kW",
                "Reduction / Delta": f"-{shaved_kw:,.1f} kW (-{shaved_pct:.1f}%)"
            },
            {
                "Metric": "Max Grid Limit Overload",
                "Status Quo (No BESS)": f"{pre_diag['overload_peak_kw']:,.1f} kW",
                "With BESS": f"{d_after['overload_peak_kw']:,.1f} kW",
                "Reduction / Delta": f"-{(pre_diag['overload_peak_kw'] - d_after['overload_peak_kw']):,.1f} kW"
            },
            {
                "Metric": "Total Overload Violation Intervals",
                "Status Quo (No BESS)": f"{pre_diag['total_violation_intervals']:,} intervals ({pre_diag['total_violation_hours']:.1f} h)",
                "With BESS": f"{d_after['total_violation_intervals']:,} intervals ({d_after['total_violation_hours']:.1f} h)",
                "Reduction / Delta": f"-{violations_eliminated:,} intervals (-{eliminated_pct:.1f}%)"
            },
            {
                "Metric": "Longest Consecutive Overload Run",
                "Status Quo (No BESS)": f"{pre_diag['longest_violation_run_hours']:.1f} Hours",
                "With BESS": f"{d_after['longest_violation_run_hours']:.1f} Hours",
                "Reduction / Delta": f"-{(pre_diag['longest_violation_run_hours'] - d_after['longest_violation_run_hours']):.1f} Hours"
            },
            {
                "Metric": "Total Overload Exceedance Energy",
                "Status Quo (No BESS)": f"{pre_diag['total_exceedance_energy_mwh']:,.2f} MWh",
                "With BESS": f"{d_after['total_exceedance_energy_mwh']:,.2f} MWh",
                "Reduction / Delta": f"-{(pre_diag['total_exceedance_energy_mwh'] - d_after['total_exceedance_energy_mwh']):,.2f} MWh"
            }
        ]
        st.dataframe(pd.DataFrame(comp_rows), use_container_width=True, hide_index=True)
