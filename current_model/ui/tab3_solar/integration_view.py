"""
========================================================================================
Sub-Tab 3.2: Solar & Consumption Integration View (ui/tab3_solar/integration_view.py)
========================================================================================

Description:
------------
Orchestrates the coupled Solar PV and Electrical Consumption analysis (Sub-Tab 3.2):
  - Ingests active facility load profile from Tab 1 (CSV real meter or 365d/24h Synthetic).
  - 3 Operating Modes:
      1. Live Mirror from Sub-Tab 3.1 (Default, locked & synchronized with active scenario).
      2. Smart Target Coverage Auto-Sizer (40%, 60%, 80%, 100% Net Zero & custom slider with 1-click sync).
      3. Custom Sizing & Sensitivity Mode.
  - Interval-by-interval 15-minute electrical dispatch calculation (Direct, Surplus, Residual).
  - Performance KPIs:
      * Self-Consumption Rate (SCR % / Eigenverbrauchsquote)
      * Autarky Rate / Solar Fraction (SF % / Autarkiegrad)
      * Surplus export and Residual grid purchase (kWh & MWh)
      * Peak demand shaving (kW & % reduction)
      * BESS Storage Readiness (Surplus energy ready for battery storage)
  - 5 High-Contrast Plotly Figures:
      * 15-minute dispatch timeseries with rangeslider
      * 12-month coupled energy balance bar chart + monthly autarky %
      * Seasonal 24-hour diurnal dispatch overlay
      * Sankey energy flow diagram
      * BESS Storage Potential & Surplus Power Duration
  - Deep Financial & Tariff Savings Assessment:
      * Coupled with Tab 3 (Current Contract) Electricity Contract (Punta, Llano, Valle TOU periods)
      * Itemized billing comparison table
      * 15-Year Life-Cycle Cost Trajectory & Amortisation Curves (linked with Tab 3.1 CAPEX/OPEX)
"""

from typing import Optional, Dict, Any, Tuple
import streamlit as st
import pandas as pd
import numpy as np

from current_model.models.solar import SolarLocation, SolarPVConfig, SolarFinancialConfig, SolarSimulationResult
from current_model.models.scenario import ProjectContainer, SubScenario
from current_model.models.contract import Contract
from current_model.core.project_io import export_project_from_session, sync_active_scenario_into_session
from current_model.core.solar_engine import (
    simulate_solar_pv_generation,
    couple_solar_simulation_with_load,
    calculate_scenario_target_kwp,
    calculate_recommended_inverter_size
)
from current_model.core.financial_engine import compute_financial_bill
from current_model.core.solar_financial_engine import compute_solar_financial_metrics
from current_model.core.synthetic_engine import aggregate_synthetic_year
from current_model.models.presets import get_industry_preset_consumers
from current_model.ui.common.cards import render_kpi_card
from current_model.ui.common.session_utils import (
    find_active_load_data_in_session,
    find_active_contract_in_session,
    get_load_profile_summary
)
from current_model.ui.tab3_solar.integration_charts import (
    create_solar_load_dispatch_figure,
    create_monthly_energy_balance_figure,
    create_energy_flow_sankey_figure
)
from current_model.ui.tab3_solar.charts import (
    create_annual_running_costs_comparison_figure,
    create_unified_amortisation_master_figure
)


def render_solar_integration_view(key_prefix: str = "tab3_int") -> None:
    """
    Renders Sub-Tab 3.2: Solar PV & Facility Consumption Integration.
    """
    st.subheader("Solar PV & Facility Consumption Integration")
    st.caption(
        "Couples 15-minute physical Solar PV generation with your active facility load profile. "
        "Calculates direct self-consumption, surplus export, residual grid purchases, peak shaving, and financial bill reduction."
    )

    project: ProjectContainer = export_project_from_session()
    active_sub = project.get_active_scenario()

    # --------------------------------------------------------------------------
    # 0. Status Quo (Base Benchmark) Guard
    # --------------------------------------------------------------------------
    if active_sub is None:
        st.info(
            "### :material/anchor: Status Quo (Base Benchmark) Active\n\n"
            "The **Status Quo (Base Scenario)** represents your pure utility grid electricity baseline without on-site Solar PV (100% Grid Import).\n\n"
            "To simulate coupled solar self-consumption, load integration, and peak shaving, switch to an active Sub-Scenario branch or instantiate a new branch below."
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
            if st.button("Instantiate New Solar PV Branch", icon=":material/add_circle:", use_container_width=True, key=f"{key_prefix}_instantiate_new_btn"):
                new_sub = SubScenario(
                    name=f"Sub-Scenario {len(project.sub_scenarios) + 1}: Solar PV",
                    color_code="#2563EB",
                    include_solar=True,
                    solar_config=SolarPVConfig(
                        module_count=778,
                        module_power_wp=450.0,
                        technology_preset="TOPCon",
                        module_technology="TOPCon (450 Wp - N-Type Modern Standard)",
                        inverter_capacity_kw=300.0,
                        tilt_deg=28.0,
                        azimuth_deg=0.0,
                        weather_mode="TMY"
                    )
                )
                project.add_sub_scenario(new_sub)
                project.active_sub_scenario_id = new_sub.id
                st.session_state["project_container"] = project
                sync_active_scenario_into_session(project, auto_execute=False)
                st.rerun()
        return

    # --------------------------------------------------------------------------
    # 1. Active Load Discovery
    # --------------------------------------------------------------------------
    df_load, load_desc, p_col = find_active_load_data_in_session()

    if df_load is None or df_load.empty:
        st.info(
            "**No active consumption profile detected from Tab 1.**\n\n"
            "Configure a profile in **Tab 1: Consumption** (Synthetic Simulator or CSV Ingestion), "
            "or load a demo profile below to explore the solar-load coupling:"
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
    gaps = load_summary.get("gaps", [])

    # Status Banner: Active Consumption Foundation & Active Scenario
    st.markdown(
        f"""
        <div style="background: rgba(30, 41, 59, 0.6); border: 1px solid rgba(51, 65, 85, 0.7); border-radius: 8px; padding: 12px 16px; margin-bottom: 12px;">
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
                <div>
                    <span style="font-size: 0.75rem; color: #94A3B8; text-transform: uppercase; letter-spacing: 0.05em;">Active Foundation</span>
                    <div style="font-size: 1.05rem; font-weight: 600; color: #F8FAFC; margin-top: 2px;">
                        Branch: <span style="color: #38BDF8;">{active_sub.name}</span> | Load: <span style="color: #10B981;">{load_desc}</span>
                    </div>
                </div>
                <div style="text-align: right;">
                    <span style="font-size: 0.95rem; color: #38BDF8; font-weight: 600;">{load_summary['total_kwh']:,.0f} kWh/year</span>
                    <span style="font-size: 0.8rem; color: #94A3B8;"> | Peak: {load_summary['peak_kw']:,.1f} kW | {load_summary['data_points']:,} intervals</span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    if gaps:
        total_gap_d = load_summary.get("total_gap_days", 0.0)
        dur_d = load_summary.get("duration_days", 0.0)
        cal_d = load_summary.get("calendar_days", dur_d)
        cov_pct = (dur_d / max(1.0, cal_d) * 100.0)
        gap_desc_items = [f"{g['start_str']} to {g['end_str']} ({g['duration_days']:.1f} days)" for g in gaps[:2]]
        gap_desc_str = ", ".join(gap_desc_items)
        if len(gaps) > 2:
            gap_desc_str += f" (+{len(gaps)-2} more)"
        st.warning(
            f":material/timeline: **Load Profile Discontinuity Detected:** {len(gaps)} measurement interruption(s) found ({gap_desc_str}, totaling {total_gap_d:.1f} missing days / {cov_pct:.1f}% data coverage). "
            f"Coupled solar dispatch maintains strict diurnal calendar synchronization (preventing day/night phase shift). "
            f"Configure your gap strategy in the calculation options below.",
            icon=":material/warning:"
        )

    # Inherit location from Tab 3.1 parent simulation, project container, or session state
    parent_sim: Optional[SolarSimulationResult] = st.session_state.get("app_tab3_sim_result") or st.session_state.get("tab3_solar_sim_result")
    if parent_sim is not None and getattr(parent_sim, "location", None) is not None:
        location = parent_sim.location
    elif getattr(project.base_scenario, "location", None) is not None:
        location = project.base_scenario.location
    else:
        loc_lat = st.session_state.get("app_tab3_loc_lat") or st.session_state.get("tab3_solar_loc_lat") or -32.8908
        loc_lon = st.session_state.get("app_tab3_loc_lon") or st.session_state.get("tab3_solar_loc_lon") or -68.8272
        loc_name = st.session_state.get("app_tab3_loc_name") or st.session_state.get("tab3_solar_loc_name") or "Mendoza, Argentina"
        loc_elev = st.session_state.get("app_tab3_loc_elev") or st.session_state.get("tab3_solar_loc_elev") or 746.0
        location = SolarLocation(name=loc_name, latitude=float(loc_lat), longitude=float(loc_lon), elevation_m=float(loc_elev))

    estimated_spec_yield = 1600.0  # Baseline specific yield estimate

    # Parent configuration from Sub-Tab 3.1 / Active SubScenario
    parent_cfg: Optional[SolarPVConfig] = active_sub.solar_config or st.session_state.get("app_tab3_config") or st.session_state.get("tab3_solar_config")
    if parent_cfg is None or getattr(parent_cfg, "module_count", 0) <= 0:
        parent_cfg = SolarPVConfig(
            module_count=778,
            module_power_wp=450.0,
            technology_preset="TOPCon",
            module_technology="TOPCon (450 Wp - N-Type Modern Standard)",
            inverter_capacity_kw=300.0,
            tilt_deg=28.0,
            azimuth_deg=0.0,
            weather_mode="TMY"
        )

    # --------------------------------------------------------------------------
    # 2. Operating Mode & System Sizing Toolbar
    # --------------------------------------------------------------------------
    st.markdown("##### 1. Solar Sizing & Integration Mode")

    mode_key = f"{key_prefix}_operating_mode"
    if mode_key not in st.session_state:
        st.session_state[mode_key] = "Live Mirror from Sub-Tab 3.1 (Recommended)"

    op_mode = st.radio(
        "Select Sizing & Integration Mode:",
        options=[
            "Live Mirror from Sub-Tab 3.1 (Recommended)",
            "Smart Target Coverage Auto-Sizer",
            "Custom Sizing & Sensitivity"
        ],
        key=mode_key,
        horizontal=True
    )

    state_cfg_key = f"{key_prefix}_config"
    curr_cfg: Optional[SolarPVConfig] = st.session_state.get(state_cfg_key)

    if op_mode == "Live Mirror from Sub-Tab 3.1 (Recommended)":
        # Always synchronize completely with parent config from Sub-Tab 3.1
        curr_cfg = SolarPVConfig(
            module_count=parent_cfg.module_count,
            module_power_wp=parent_cfg.module_power_wp,
            technology_preset=parent_cfg.technology_preset,
            module_technology=parent_cfg.module_technology,
            inverter_capacity_kw=parent_cfg.inverter_capacity_kw,
            tilt_deg=parent_cfg.tilt_deg,
            azimuth_deg=parent_cfg.azimuth_deg,
            temp_coefficient_pct_c=parent_cfg.temp_coefficient_pct_c,
            first_year_degradation_pct=parent_cfg.first_year_degradation_pct,
            annual_degradation_pct=parent_cfg.annual_degradation_pct,
            weather_mode=getattr(parent_cfg, "weather_mode", "TMY"),
            selected_weather_year=getattr(parent_cfg, "selected_weather_year", 2024),
            sizing_scenario="Mirror 3.1"
        )
        st.session_state[state_cfg_key] = curr_cfg

        st.info(
            f"**Linked to Sub-Tab 3.1 Engineering System:** Using **{curr_cfg.module_count:,} modules** à {curr_cfg.module_power_wp:.0f} Wp "
            f"({curr_cfg.dc_capacity_kwp:,.1f} kWp DC / {curr_cfg.inverter_capacity_kw:,.1f} kW AC, {curr_cfg.technology_preset}, {curr_cfg.tilt_deg:.0f}° tilt). "
            f"Any modification in Sub-Tab 3.1 updates this coupled dispatch automatically.",
            icon=":material/link:"
        )

    elif op_mode == "Smart Target Coverage Auto-Sizer":
        st.caption(
            "Auto-sizes your PV plant to generate an exact target percentage of your annual facility consumption (Tab 1). "
            "Click a preset or drag the slider, then optionally apply the sized system back to Sub-Tab 3.1."
        )

        # Quick preset buttons
        t_col1, t_col2, t_col3, t_col4 = st.columns(4)
        load_kwh = load_summary.get("total_kwh", 600000.0)

        target_cov_slider_key = f"{key_prefix}_target_pct_slider"
        current_slider_val = st.session_state.get(target_cov_slider_key, 60.0)

        with t_col1:
            if st.button("40% Coverage", key=f"{key_prefix}_s40_btn", help="Target 40% of annual electricity consumption (maximizes direct self-consumption)."):
                st.session_state[target_cov_slider_key] = 40.0
                st.rerun()
        with t_col2:
            if st.button("60% Coverage", key=f"{key_prefix}_s60_btn", help="Target 60% of annual electricity consumption (balanced commercial standard)."):
                st.session_state[target_cov_slider_key] = 60.0
                st.rerun()
        with t_col3:
            if st.button("80% Coverage", key=f"{key_prefix}_s80_btn", help="Target 80% of annual electricity consumption (high autarky / self-sufficiency)."):
                st.session_state[target_cov_slider_key] = 80.0
                st.rerun()
        with t_col4:
            if st.button("100% Net Zero", key=f"{key_prefix}_s100_btn", help="Target 100% of annual electricity demand on a net annual basis."):
                st.session_state[target_cov_slider_key] = 100.0
                st.rerun()

        target_pct = st.slider(
            "Target Annual Net Coverage (% of Tab 1 Load):",
            min_value=10.0,
            max_value=200.0,
            value=float(st.session_state.get(target_cov_slider_key, 60.0)),
            step=5.0,
            key=target_cov_slider_key
        )

        target_kwp = calculate_scenario_target_kwp(load_kwh, estimated_spec_yield, target_pct)
        mod_wp = float(getattr(parent_cfg, "module_power_wp", 450.0) or 450.0)
        calc_mod_count = max(1, int(round((target_kwp * 1000.0) / mod_wp)))
        calc_dc_kwp = round((calc_mod_count * mod_wp) / 1000.0, 1)
        calc_inv_kw = calculate_recommended_inverter_size(calc_dc_kwp)

        curr_cfg = SolarPVConfig(
            module_count=calc_mod_count,
            module_power_wp=mod_wp,
            technology_preset=getattr(parent_cfg, "technology_preset", "TOPCon"),
            module_technology=getattr(parent_cfg, "module_technology", "TOPCon (450 Wp)"),
            inverter_capacity_kw=calc_inv_kw,
            tilt_deg=getattr(parent_cfg, "tilt_deg", 28.0),
            azimuth_deg=getattr(parent_cfg, "azimuth_deg", 0.0),
            weather_mode=getattr(parent_cfg, "weather_mode", "TMY"),
            sizing_scenario=f"{target_pct:.0f}% Target"
        )
        st.session_state[state_cfg_key] = curr_cfg

        # Sync back to Sub-Tab 3.1 action
        c_sync_btn, _ = st.columns([4, 6])
        with c_sync_btn:
            if st.button("Apply Sizing to Sub-Tab 3.1 & Active Scenario", icon=":material/publish:", type="secondary", key=f"{key_prefix}_apply_to_31_btn"):
                parent_cfg.module_count = curr_cfg.module_count
                parent_cfg.module_power_wp = curr_cfg.module_power_wp
                parent_cfg.dc_capacity_kwp = curr_cfg.dc_capacity_kwp
                parent_cfg.inverter_capacity_kw = curr_cfg.inverter_capacity_kw
                active_sub.solar_config = parent_cfg
                st.session_state["project_container"] = project
                st.session_state["app_tab3_config"] = parent_cfg
                st.session_state["tab3_solar_config"] = parent_cfg
                st.success(f"Successfully applied {curr_cfg.dc_capacity_kwp:,.1f} kWp ({curr_cfg.module_count:,} modules) to Sub-Tab 3.1 and '{active_sub.name}'.", icon=":material/check_circle:")

    else:  # Custom Sizing & Sensitivity
        st.caption("Manually adjust panel count, module wattage, and inverter rating to test custom sensitivity scenarios:")
        if curr_cfg is None:
            curr_cfg = SolarPVConfig(
                module_count=parent_cfg.module_count,
                module_power_wp=parent_cfg.module_power_wp,
                technology_preset=parent_cfg.technology_preset,
                module_technology=parent_cfg.module_technology,
                inverter_capacity_kw=parent_cfg.inverter_capacity_kw,
                tilt_deg=parent_cfg.tilt_deg,
                azimuth_deg=parent_cfg.azimuth_deg
            )

        p_col1, p_col2, p_col3 = st.columns(3)
        with p_col1:
            inp_mod_count = st.number_input(
                "Module Count (Panels):",
                min_value=1,
                max_value=30000,
                value=int(curr_cfg.module_count),
                step=10,
                key=f"{key_prefix}_custom_mod_count_inp"
            )
            curr_cfg.module_count = inp_mod_count

        with p_col2:
            inp_mod_wp = st.number_input(
                "Module Wattage (Wp):",
                min_value=200.0,
                max_value=800.0,
                value=float(curr_cfg.module_power_wp),
                step=10.0,
                key=f"{key_prefix}_custom_mod_wp_inp"
            )
            curr_cfg.module_power_wp = inp_mod_wp
            curr_cfg.dc_capacity_kwp = round((curr_cfg.module_count * curr_cfg.module_power_wp) / 1000.0, 1)

        with p_col3:
            rec_inv = calculate_recommended_inverter_size(curr_cfg.dc_capacity_kwp)
            init_inv = float(curr_cfg.inverter_capacity_kw) if curr_cfg.inverter_capacity_kw > 1.0 else rec_inv
            inp_inv_kw = st.number_input(
                "Inverter Rating (kW AC):",
                min_value=1.0,
                max_value=20000.0,
                value=float(init_inv),
                step=10.0,
                key=f"{key_prefix}_custom_inv_kw_inp",
                help=f"Recommended standard inverter capacity: {rec_inv:.1f} kW AC."
            )
            curr_cfg.inverter_capacity_kw = inp_inv_kw

        st.session_state[state_cfg_key] = curr_cfg

    if curr_cfg is None or curr_cfg.module_count <= 0:
        curr_cfg = parent_cfg

    # --------------------------------------------------------------------------
    # 3. System Architecture Specification Badge Bar
    # --------------------------------------------------------------------------
    dc_ac_ratio = (curr_cfg.dc_capacity_kwp / max(1.0, curr_cfg.inverter_capacity_kw))
    st.markdown(
        f"""
        <div style="background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(51, 65, 85, 0.8); border-radius: 8px; padding: 10px 16px; margin-top: 8px; margin-bottom: 16px;">
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;">
                <div>
                    <span style="font-size: 0.75rem; color: #94A3B8; text-transform: uppercase;">System Architecture</span>
                    <div style="font-size: 1.15rem; font-weight: 700; color: #F8FAFC;">
                        {curr_cfg.dc_capacity_kwp:,.1f} kWp DC <span style="font-size: 0.9rem; font-weight: 400; color: #94A3B8;">({curr_cfg.module_count:,} × {curr_cfg.module_power_wp:.0f} Wp {curr_cfg.technology_preset})</span>
                    </div>
                </div>
                <div style="display: flex; gap: 24px; flex-wrap: wrap;">
                    <div>
                        <span style="font-size: 0.7rem; color: #94A3B8; text-transform: uppercase;">Inverter AC</span>
                        <div style="font-size: 0.95rem; font-weight: 600; color: #38BDF8;">{curr_cfg.inverter_capacity_kw:,.1f} kW <span style="font-size: 0.8rem; color: #64748B;">(DC/AC: {dc_ac_ratio:.2f})</span></div>
                    </div>
                    <div>
                        <span style="font-size: 0.7rem; color: #94A3B8; text-transform: uppercase;">Orientation</span>
                        <div style="font-size: 0.95rem; font-weight: 600; color: #F8FAFC;">{curr_cfg.tilt_deg:.0f}° Tilt / {curr_cfg.azimuth_deg:.0f}° Azimuth</div>
                    </div>
                    <div>
                        <span style="font-size: 0.7rem; color: #94A3B8; text-transform: uppercase;">Required Area</span>
                        <div style="font-size: 0.95rem; font-weight: 600; color: #10B981;">{curr_cfg.required_area_m2:,.0f} m² <span style="font-size: 0.8rem; color: #64748B;">(Gross)</span></div>
                    </div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    # --------------------------------------------------------------------------
    # 4. Calculation Action & Execution
    # --------------------------------------------------------------------------
    state_res_key = f"{key_prefix}_sim_result"
    sim_res: Optional[SolarSimulationResult] = st.session_state.get(state_res_key)

    # Discontinuity Strategy Selection (if load profile has gaps)
    gap_strat_key = f"{key_prefix}_gap_strategy"
    if gaps:
        if gap_strat_key not in st.session_state:
            st.session_state[gap_strat_key] = "Real Measured Breaks (Solar Export Surplus)"
        gap_opt = st.radio(
            "Load Profile Discontinuity Strategy:",
            options=[
                "Real Measured Breaks (Solar Export Surplus)",
                "Synthetically Impute Gaps (Typical Day Pattern)"
            ],
            key=gap_strat_key,
            horizontal=True,
            help="Real Measured Breaks: Displays authentic data gaps with zero load, routing unmonitored solar power to grid feed-in without distorting diurnal phase alignment. Synthetically Impute Gaps: Replaces missing intervals with the facility's average weekday/weekend load pattern."
        )
        gap_handling = "impute" if "Impute" in gap_opt else "bypass"
    else:
        gap_handling = "bypass"

    load_signature = f"{load_desc}_{len(df_load)}_{round(float(load_summary.get('total_mwh', 0.0)), 2)}_{gap_handling}"
    last_coupled_load_sig = st.session_state.get(f"{key_prefix}_last_coupled_load_sig")
    load_has_changed = bool(last_coupled_load_sig is not None and last_coupled_load_sig != load_signature)

    # Automatic Fast-Coupling from Sub-Tab 3.1:
    # When in 'Live Mirror from Sub-Tab 3.1' mode and Sub-Tab 3.1 has an active simulation,
    # automatically couple it with the facility load profile in milliseconds!
    if (op_mode == "Live Mirror from Sub-Tab 3.1 (Recommended)" and
        parent_sim is not None and
        getattr(parent_sim, "df_timeseries", None) is not None and
        "P_AC_kW" in parent_sim.df_timeseries.columns):
        p_cfg = getattr(parent_sim, "config", None)
        is_same_config = (
            p_cfg is not None and
            p_cfg.module_count == curr_cfg.module_count and
            p_cfg.module_power_wp == curr_cfg.module_power_wp and
            p_cfg.inverter_capacity_kw == curr_cfg.inverter_capacity_kw and
            p_cfg.tilt_deg == curr_cfg.tilt_deg
        )
        needs_auto_coupling = (
            sim_res is None or
            "P_Load_kW" not in getattr(sim_res, "df_timeseries", pd.DataFrame()).columns or
            getattr(sim_res, "config", None) != curr_cfg or
            getattr(getattr(sim_res, "kpis", None), "gap_handling_mode", "bypass") != gap_handling or
            load_has_changed
        )
        if is_same_config and needs_auto_coupling:
            sim_res = couple_solar_simulation_with_load(parent_sim, df_load, gap_handling=gap_handling)
            st.session_state[state_res_key] = sim_res
            st.session_state[f"{key_prefix}_last_coupled_load_sig"] = load_signature
            load_has_changed = False
            if active_sub is not None:
                active_sub.solar_config = curr_cfg
                active_sub.include_solar = True
                st.session_state["project_container"] = project

    if load_has_changed:
        st.warning(
            f":material/sync_problem: **Active Consumption Profile Updated:** Tab 2 load profile has changed to **{load_desc}**. "
            f"Click **'Recalculate Coupled Solar & Consumption Dispatch'** below to re-align dispatch and savings.",
            icon=":material/warning:"
        )

    auto_trigger = st.session_state.pop(f"{key_prefix}_trigger_calc", False)
    btn_label = "Recalculate Coupled Solar & Consumption Dispatch" if sim_res is not None else "Calculate Coupled Solar & Consumption Dispatch"
    btn_type = "secondary" if sim_res is not None else "primary"
    calc_btn_clicked = st.button(
        btn_label,
        icon=":material/calculate:",
        type=btn_type,
        use_container_width=True,
        key=f"{key_prefix}_calc_dispatch_btn"
    )

    config_changed = False
    if sim_res is not None and hasattr(sim_res, "config"):
        if (sim_res.config.module_count != curr_cfg.module_count or
            sim_res.config.module_power_wp != curr_cfg.module_power_wp or
            sim_res.config.inverter_capacity_kw != curr_cfg.inverter_capacity_kw or
            sim_res.config.tilt_deg != curr_cfg.tilt_deg):
            config_changed = True

    should_simulate = (calc_btn_clicked or auto_trigger) and curr_cfg.module_count > 0

    if should_simulate:
        with st.spinner("Calculating 15-minute physical solar-load dispatch balance..."):
            try:
                # If we have parent_sim matching curr_cfg, fast-couple it
                if (op_mode == "Live Mirror from Sub-Tab 3.1 (Recommended)" and
                    parent_sim is not None and
                    getattr(parent_sim, "df_timeseries", None) is not None and
                    "P_AC_kW" in parent_sim.df_timeseries.columns and
                    getattr(parent_sim, "config", None) is not None and
                    parent_sim.config.module_count == curr_cfg.module_count and
                    parent_sim.config.module_power_wp == curr_cfg.module_power_wp and
                    parent_sim.config.tilt_deg == curr_cfg.tilt_deg):
                    sim_res = couple_solar_simulation_with_load(parent_sim, df_load, gap_handling=gap_handling)
                else:
                    sim_res = simulate_solar_pv_generation(
                        config=curr_cfg,
                        location=location,
                        load_df=df_load,
                        gap_handling=gap_handling
                    )
                    # Also keep Sub-Tab 3.1 in sync
                    st.session_state["app_tab3_sim_result"] = sim_res
                    st.session_state["solar_kw_15min"] = sim_res.df_timeseries["P_AC_kW"]

                st.session_state[state_res_key] = sim_res
                st.session_state[f"{key_prefix}_last_coupled_load_sig"] = load_signature
                config_changed = False
                if active_sub is not None:
                    active_sub.solar_config = curr_cfg
                    active_sub.include_solar = True
                    st.session_state["project_container"] = project
                st.success("Coupled dispatch calculated successfully!", icon=":material/check_circle:")
            except Exception as err:
                st.error(f"Coupled Dispatch Simulation Error: {err}", icon=":material/error:")
                return

    # If no simulation result exists yet, show clean empty-state guidance
    if sim_res is None:
        st.divider()
        st.info(
            "**Ready to Compute Coupled Solar & Consumption Dispatch**\n\n"
            "Review your system architecture above, then click **':material/calculate: Calculate Coupled Solar & Consumption Dispatch'** "
            "to calculate 15-minute direct self-consumption, grid residual load, surplus export, and financial tariff savings.",
            icon=":material/info:"
        )
        return

    if config_changed:
        st.warning("Solar configuration parameters were modified above. Click **'Calculate Coupled Solar & Consumption Dispatch'** to update dispatch analytics.", icon=":material/warning:")

    kpis = sim_res.kpis
    df_ts = sim_res.df_timeseries

    # Save to global session state for downstream use
    st.session_state["solar_dispatch_result"] = sim_res
    st.session_state["solar_kw_15min"] = df_ts["P_AC_kW"]

    st.divider()

    # --------------------------------------------------------------------------
    # 5. Coupled Dispatch Performance Metrics (10 Modern Cards)
    # --------------------------------------------------------------------------
    st.markdown("##### 2. Coupled Dispatch Performance Metrics")

    # Peak Shaving Analysis
    p_orig_max = float(df_ts["P_Load_kW"].max()) if "P_Load_kW" in df_ts.columns else 0.0
    p_res_max = float(df_ts["P_Residual_kW"].max()) if "P_Residual_kW" in df_ts.columns else 0.0
    peak_shaved_kw = max(0.0, p_orig_max - p_res_max)
    peak_shaved_pct = (peak_shaved_kw / p_orig_max * 100.0) if p_orig_max > 0 else 0.0

    # Discontinuity Banner above KPIs if gaps present
    if getattr(kpis, "has_load_gaps", False):
        if getattr(kpis, "gap_handling_mode", "bypass") == "bypass":
            ann_load_kwh = (kpis.annualized_load_kwh or 0.0)
            st.caption(
                f":material/info: **Discontinuity Reconciliation:** Baseline load contains **{kpis.total_gap_days:.1f} unmonitored days** "
                f"({kpis.data_coverage_pct:.1f}% measured data availability). Solar generation during interruptions is accounted as grid export. "
                f"Annualized load equivalent: **{ann_load_kwh:,.0f} kWh/year**."
            )
        else:
            st.caption(
                f":material/auto_fix_high: **Synthetically Imputed Load Discontinuities:** Missing {kpis.total_gap_days:.1f} days "
                f"were filled using the facility's typical weekday/weekend load pattern for a continuous 8,760-hour projection."
            )

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        render_kpi_card(
            "Self-Consumption Rate",
            f"{kpis.self_consumption_rate_pct:.1f} %",
            f"{kpis.direct_consumption_kwh:,.0f} kWh of {kpis.annual_energy_kwh:,.0f} kWh used on-site",
            status="ok"
        )
    with k2:
        if getattr(kpis, "has_load_gaps", False) and getattr(kpis, "gap_handling_mode", "bypass") == "bypass":
            sub_k2 = f"Covers {kpis.direct_consumption_kwh:,.0f} kWh of {kpis.total_load_kwh:,.0f} kWh measured ({kpis.data_coverage_pct:.0f}% coverage)"
        elif getattr(kpis, "has_load_gaps", False):
            sub_k2 = f"Covers {kpis.direct_consumption_kwh:,.0f} kWh of {kpis.total_load_kwh:,.0f} kWh (Imputed)"
        else:
            sub_k2 = f"Covers {kpis.direct_consumption_kwh:,.0f} kWh of {kpis.total_load_kwh:,.0f} kWh facility demand"

        render_kpi_card(
            "Autarky / Solar Fraction",
            f"{kpis.solar_fraction_autarky_pct:.1f} %",
            sub_k2,
            status="ok"
        )
    with k3:
        if getattr(kpis, "has_load_gaps", False) and getattr(kpis, "gap_handling_mode", "bypass") == "bypass":
            sub_k3 = f"{(kpis.surplus_generation_kwh / max(1.0, kpis.annual_energy_kwh) * 100.0):.1f}% of generation (includes {kpis.total_gap_days:.1f}d unmonitored export)"
        else:
            sub_k3 = f"{(kpis.surplus_generation_kwh / max(1.0, kpis.annual_energy_kwh) * 100.0):.1f}% of generation available for feed-in / BESS"

        render_kpi_card(
            "PV Surplus / Grid Export",
            f"{kpis.surplus_generation_kwh:,.0f} kWh",
            sub_k3,
            status="default"
        )
    with k4:
        render_kpi_card(
            "Residual Grid Import",
            f"{kpis.residual_load_kwh:,.0f} kWh",
            f"Remaining facility demand purchased from grid",
            status="default"
        )

    # Secondary row of metrics
    s1, s2, s3, s4 = st.columns(4)
    with s1:
        render_kpi_card(
            "Peak Demand Reduction",
            f"-{peak_shaved_kw:.1f} kW",
            f"Original: {p_orig_max:.1f} kW -> Residual: {p_res_max:.1f} kW (-{peak_shaved_pct:.1f}%)",
            status="ok" if peak_shaved_kw > 0.1 else "default"
        )
    with s2:
        net_cov_pct = (kpis.annual_energy_kwh / max(1.0, kpis.total_load_kwh) * 100.0)
        cov_info = f" ({kpis.data_coverage_pct:.0f}% data)" if getattr(kpis, "has_load_gaps", False) and getattr(kpis, "gap_handling_mode", "bypass") == "bypass" else ""
        render_kpi_card(
            "Annual Net Energy Coverage",
            f"{net_cov_pct:.1f} %",
            f"Generation: {kpis.annual_energy_kwh:,.0f} kWh vs. Demand: {kpis.total_load_kwh:,.0f} kWh{cov_info}"
        )
    with s3:
        render_kpi_card(
            "Specific Solar Yield",
            f"{kpis.specific_yield_kwh_per_kwp:.1f} kWh/kWp",
            f"Full Load Hours: {kpis.full_load_hours:,.0f} h/a"
        )
    with s4:
        render_kpi_card(
            "Direct Solar Consumption",
            f"{kpis.direct_consumption_kwh:,.0f} kWh",
            f"Total clean energy consumed instantaneously"
        )

    st.write("")

    # --------------------------------------------------------------------------
    # 6. Interactive Visual Dispatch Analytics (3 Core Tabs)
    # --------------------------------------------------------------------------
    st.markdown("##### 3. Visual Dispatch Analysis")

    chart_tab1, chart_tab2, chart_tab3 = st.tabs([
        ":material/timeline: 15-Minute Dispatch Timeseries",
        ":material/bar_chart: Monthly Energy Balance",
        ":material/schema: Energy Flow (Sankey)"
    ])

    with chart_tab1:
        fig_ts = create_solar_load_dispatch_figure(
            df=df_ts,
            dc_capacity_kwp=curr_cfg.dc_capacity_kwp,
            inverter_capacity_kw=curr_cfg.inverter_capacity_kw
        )
        st.plotly_chart(fig_ts, use_container_width=True)

    with chart_tab2:
        fig_monthly = create_monthly_energy_balance_figure(df=df_ts)
        st.plotly_chart(fig_monthly, use_container_width=True)

    with chart_tab3:
        fig_sankey = create_energy_flow_sankey_figure(kpis=kpis)
        st.plotly_chart(fig_sankey, use_container_width=True)

    st.divider()

    # --------------------------------------------------------------------------
    # 7. Economic & Avoided Cost Assessment (Coupled with Tab 3 Contract)
    # --------------------------------------------------------------------------
    st.markdown("##### 4. Financial & Tariff Savings Assessment")

    active_contract: Optional[Contract] = find_active_contract_in_session()
    if active_contract is None:
        if active_sub and getattr(active_sub, "use_custom_grid_tariff", False):
            active_contract = getattr(active_sub, "custom_contract", None) or getattr(active_sub, "custom_grid_tariff", None)
        if active_contract is None and project and project.base_scenario and project.base_scenario.base_contract:
            active_contract = project.base_scenario.base_contract

    if active_contract is not None:
        st.caption(f"Linked Electricity Contract: **{active_contract.name}** ({active_contract.currency})")
        try:
            curr = getattr(active_contract, "currency", "EUR")

            # 1. Baseline bill (Facility load before solar)
            df_base = pd.DataFrame({
                "timestamp": df_ts["timestamp"],
                "Total_Demand_kW": df_ts["P_Load_kW"]
            })
            base_bill = compute_financial_bill(load_data=df_base, contract=active_contract)

            # 2. Solar bill (Residual load after direct solar self-consumption)
            df_residual = pd.DataFrame({
                "timestamp": df_ts["timestamp"],
                "Total_Demand_kW": df_ts["P_Residual_kW"]
            })
            solar_bill = compute_financial_bill(load_data=df_residual, contract=active_contract)

            cost_savings_gross = base_bill.total_gross_period - solar_bill.total_gross_period
            cost_savings_pct = (cost_savings_gross / base_bill.total_gross_period * 100.0) if base_bill.total_gross_period > 0 else 0.0

            energy_savings_net = base_bill.energy_cost_period - solar_bill.energy_cost_period
            capacity_savings_net = base_bill.capacity_cost_period - solar_bill.capacity_cost_period
            taxes_savings = base_bill.total_taxes_period - solar_bill.total_taxes_period

            has_savings = cost_savings_gross >= 0.0

            f1, f2, f3, f4 = st.columns(4)
            with f1:
                render_kpi_card(
                    "Annual Gross Cost Savings",
                    f"{cost_savings_gross:,.2f} {curr}" if has_savings else f"-{abs(cost_savings_gross):,.2f} {curr}",
                    f"Bill reduction: -{cost_savings_pct:.1f}% ({base_bill.duration_days:.0f} days)" if has_savings else f"Cost increase: +{abs(cost_savings_pct):.1f}%",
                    status="ok" if has_savings else "alert"
                )
            with f2:
                render_kpi_card(
                    "Status Quo Annual Bill",
                    f"{base_bill.total_gross_period:,.2f} {curr}",
                    f"Baseline electricity invoice without Solar PV ({base_bill.duration_days:.0f} days)"
                )
            with f3:
                render_kpi_card(
                    "Residual Annual Bill with PV",
                    f"{solar_bill.total_gross_period:,.2f} {curr}",
                    f"Remaining electricity invoice after PV self-consumption"
                )
            with f4:
                render_kpi_card(
                    "Energy Charge Reduction",
                    f"{energy_savings_net:,.2f} {curr}" if energy_savings_net >= 0 else f"-{abs(energy_savings_net):,.2f} {curr}",
                    f"Capacity charge savings: {capacity_savings_net:,.2f} {curr}",
                    status="ok" if energy_savings_net >= 0 else "default"
                )

            # Itemized comparison table
            with st.expander("Itemized Financial Comparison: Status Quo vs. With Solar PV", icon=":material/table_chart:", expanded=False):
                savings_label = f"-{cost_savings_gross:,.2f} (-{cost_savings_pct:.1f}%)" if has_savings else f"+{abs(cost_savings_gross):,.2f} (+{abs(cost_savings_pct):.1f}%)"
                fin_rows = [
                    {
                        "Cost Component": "Total Gross Invoice",
                        f"Status Quo ({curr})": f"{base_bill.total_gross_period:,.2f}",
                        f"With Solar PV ({curr})": f"{solar_bill.total_gross_period:,.2f}",
                        "Savings / Delta": savings_label
                    },
                    {
                        "Cost Component": "Net Energy Charge",
                        f"Status Quo ({curr})": f"{base_bill.energy_cost_period:,.2f}",
                        f"With Solar PV ({curr})": f"{solar_bill.energy_cost_period:,.2f}",
                        "Savings / Delta": f"-{energy_savings_net:,.2f}" if energy_savings_net >= 0 else f"+{abs(energy_savings_net):,.2f}"
                    },
                    {
                        "Cost Component": "Capacity & Demand Charge",
                        f"Status Quo ({curr})": f"{base_bill.capacity_cost_period:,.2f}",
                        f"With Solar PV ({curr})": f"{solar_bill.capacity_cost_period:,.2f}",
                        "Savings / Delta": f"-{capacity_savings_net:,.2f}" if capacity_savings_net >= 0 else f"+{abs(capacity_savings_net):,.2f}"
                    },
                    {
                        "Cost Component": "Taxes & Levies",
                        f"Status Quo ({curr})": f"{base_bill.total_taxes_period:,.2f}",
                        f"With Solar PV ({curr})": f"{solar_bill.total_taxes_period:,.2f}",
                        "Savings / Delta": f"-{taxes_savings:,.2f}" if taxes_savings >= 0 else f"+{abs(taxes_savings):,.2f}"
                    },
                    {
                        "Cost Component": "Effective Unit Rate",
                        f"Status Quo ({curr})": f"{base_bill.effective_kwh_price:.4f} {curr}/kWh",
                        f"With Solar PV ({curr})": f"{solar_bill.effective_kwh_price:.4f} {curr}/kWh",
                        "Savings / Delta": f"{(solar_bill.effective_kwh_price - base_bill.effective_kwh_price):+.4f} {curr}/kWh"
                    }
                ]
                st.dataframe(pd.DataFrame(fin_rows), use_container_width=True, hide_index=True)

            # 3. 15-Year Life-Cycle Trajectory (Linked to Solar Financial CAPEX in Tab 3.1)
            solar_fin_cfg: Optional[SolarFinancialConfig] = active_sub.solar_financial or st.session_state.get("solar_financial_config") or st.session_state.get("app_tab3_fin_config")

            if solar_fin_cfg and solar_fin_cfg.is_enabled:
                export_rev = kpis.surplus_generation_kwh * (solar_fin_cfg.feed_in_tariff_per_kwh or 0.06)
                coupled_fin_metrics = compute_solar_financial_metrics(
                    config=curr_cfg,
                    fin_config=solar_fin_cfg,
                    annual_generation_kwh=kpis.annual_energy_kwh,
                    annual_avoided_cost=cost_savings_gross,
                    annual_export_revenue=export_rev,
                    baseline_annual_bill=base_bill.total_gross_period
                )

                if coupled_fin_metrics.is_configured and coupled_fin_metrics.total_capex > 0:
                    st.write("")
                    st.markdown("##### 15-Year Life-Cycle Cost Trajectory & Amortisation Analysis")
                    st.caption("Directly compare total cumulative expenses, annual running operating costs, and the exact investment amortisation point (Status Quo vs. With Solar PV):")

                    roi1, roi2, roi3, roi4 = st.columns(4)
                    with roi1:
                        pb_text = f"{coupled_fin_metrics.payback_period_years:.1f} Years" if coupled_fin_metrics.payback_period_years else "Over 15 Years"
                        render_kpi_card(
                            "Amortisation / Payback",
                            pb_text,
                            f"Discounted: {coupled_fin_metrics.discounted_payback_years:.1f} Yrs" if coupled_fin_metrics.discounted_payback_years else "Break-even timeline",
                            status="ok" if coupled_fin_metrics.payback_period_years and coupled_fin_metrics.payback_period_years <= 10.0 else "default"
                        )
                    with roi2:
                        render_kpi_card(
                            "15-Year Net Benefit",
                            f"{coupled_fin_metrics.total_lifetime_savings:,.2f} {curr}",
                            f"Cumulative cash savings after CAPEX & OPEX",
                            status="ok" if coupled_fin_metrics.total_lifetime_savings > 0 else "alert"
                        )
                    with roi3:
                        render_kpi_card(
                            "Net Present Value (NPV)",
                            f"{coupled_fin_metrics.npv:,.2f} {curr}",
                            f"Discounted at {solar_fin_cfg.discount_rate_pct:.1f}% interest"
                        )
                    with roi4:
                        irr_text = f"{coupled_fin_metrics.irr_pct:.1f}%" if coupled_fin_metrics.irr_pct is not None else "N/A"
                        render_kpi_card(
                            "Internal Rate of Return (IRR)",
                            irr_text,
                            f"Capital return rate across horizon"
                        )

                    # 15-Year Life-Cycle Master Trajectory & Amortisation Diagram
                    diag_tab_master, diag_tab_running = st.tabs([
                        ":material/show_chart: Master Amortisation & Cash Flow Curve",
                        ":material/bar_chart: Annual Running Costs & Invoices"
                    ])

                    with diag_tab_master:
                        fig_master = create_unified_amortisation_master_figure(coupled_fin_metrics, currency=curr)
                        st.plotly_chart(fig_master, use_container_width=True)

                    with diag_tab_running:
                        fig_running = create_annual_running_costs_comparison_figure(coupled_fin_metrics, currency=curr)
                        st.plotly_chart(fig_running, use_container_width=True)

                    # 15-Year Year-by-Year Table
                    with st.expander("15-Year Life-Cycle Year-by-Year Table (Cashflow, Degradation, OPEX, Savings)", icon=":material/view_timeline:", expanded=False):
                        detail_rows = []
                        for row in coupled_fin_metrics.cash_flow_table:
                            detail_rows.append({
                                "Year": f"Year {row['year']}",
                                "Aging / Degradation": f"{row['aging_factor'] * 100.0:.1f} %",
                                "PV Gen (kWh)": f"{row.get('generation_kwh', row.get('generation_mwh', 0.0) * 1000.0):,.0f}",
                                f"Status Quo Bill ({curr})": f"{row.get('status_quo_bill', 0.0):,.2f}",
                                f"Residual Bill ({curr})": f"{row.get('residual_bill', 0.0):,.2f}",
                                f"PV OPEX ({curr})": f"{row.get('opex_annual', 0.0):,.2f}",
                                f"Feed-in Revenue ({curr})": f"{row.get('export_revenue', 0.0):,.2f}",
                                f"Net Running Cost ({curr})": f"{row.get('running_cost_with_pv', row.get('net_running_cost_pv', 0.0)):,.2f}",
                                f"Annual Net Benefit ({curr})": f"{row['net_cash_flow']:,.2f}",
                                f"Cum. Status Quo ({curr})": f"{row.get('cum_status_quo', 0.0):,.2f}",
                                f"Cum. With PV ({curr})": f"{row.get('cum_with_pv', 0.0):,.2f}",
                                f"Cum. Net Benefit ({curr})": f"{row['cumulative_cash_flow']:,.2f}"
                            })
                        st.dataframe(pd.DataFrame(detail_rows), use_container_width=True, hide_index=True)

        except Exception as err:
            st.warning(f"Unable to calculate financial savings against Tab 3 contract: {err}")

    else:
        st.info("No active electricity contract configured in Tab 3 (Current Contract).")

        enable_manual_rate = st.toggle(
            "Enable simplified avoided cost estimate",
            value=False,
            key=f"{key_prefix}_enable_rate_toggle",
            help="Activate to enter an estimated flat electricity rate and optional feed-in tariff."
        )

        if enable_manual_rate:
            r_col1, r_col2, r_col3 = st.columns(3)
            with r_col1:
                flat_rate = st.number_input(
                    "Electricity Purchase Rate ($/kWh):",
                    min_value=0.01,
                    max_value=2.00,
                    value=0.15,
                    step=0.01,
                    key=f"{key_prefix}_flat_rate_inp"
                )
            with r_col2:
                feed_in_rate = st.number_input(
                    "Surplus Feed-in Remuneration ($/kWh):",
                    min_value=0.00,
                    max_value=1.00,
                    value=0.06,
                    step=0.01,
                    key=f"{key_prefix}_feed_rate_inp"
                )
            with r_col3:
                currency_code = st.text_input(
                    "Currency Symbol / Code:",
                    value="EUR",
                    key=f"{key_prefix}_curr_inp"
                )

            avoided_energy_cost = kpis.direct_consumption_kwh * flat_rate
            feed_in_revenue = kpis.surplus_generation_kwh * feed_in_rate
            total_annual_benefit = avoided_energy_cost + feed_in_revenue

            m1, m2, m3 = st.columns(3)
            with m1:
                render_kpi_card(
                    "Total Annual Economic Benefit",
                    f"{total_annual_benefit:,.2f} {currency_code}",
                    f"Avoided energy purchases + surplus feed-in revenue",
                    status="ok"
                )
            with m2:
                render_kpi_card(
                    "Avoided Grid Electricity Purchases",
                    f"{avoided_energy_cost:,.2f} {currency_code}",
                    f"For {kpis.direct_consumption_kwh:,.0f} kWh self-consumed @ {flat_rate:.2f} {currency_code}/kWh"
                )
            with m3:
                render_kpi_card(
                    "Surplus Feed-in Remuneration",
                    f"{feed_in_revenue:,.2f} {currency_code}",
                    f"For {kpis.surplus_generation_kwh:,.0f} kWh exported @ {feed_in_rate:.2f} {currency_code}/kWh"
                )
        else:
            st.caption("Tip: You can configure an electricity contract in Tab 3 (Current Contract) for exact Time-of-Use and capacity billing, or toggle on the simplified rate estimate above.")
