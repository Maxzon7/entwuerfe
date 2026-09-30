"""
========================================================================================
Dynamic Tab: Generator / Genset Solution Module (ui/tab_generator/view.py)
========================================================================================

Description:
------------
Sub-Scenario native module for on-site Generator dispatch & sizing:
  - Supports dual operational paradigms:
      1. Standalone / Primary Generator: Operates directly on facility demand to shave
         grid peak charges or support islanded off-grid baseload.
      2. Hybrid Residual Backup: Seamlessly couples behind Solar PV and/or BESS,
         calculating the exact residual demand and dispatching the generator as backup
         or residual peak shaving assist.
  - Interactive technical & financial configuration forms.
  - Multi-asset 15-minute dispatch timeseries visualization.
  - Complete cumulative payment schedule (Kumulierte Zahlungsreihe).
  - Bidirectional KPI synchronization with Sub-Scenario and master comparison leaderboard.
"""

from typing import Optional, Dict, Any, List
import streamlit as st
import pandas as pd
import numpy as np

from current_model.models.generator import GeneratorConfig, GeneratorKPIs, get_generator_presets
from current_model.models.contract import Contract
from current_model.models.scenario import ProjectContainer, SubScenario
from current_model.core.dracbv_engine import simulate_generator_peaking, simulate_hybrid_scenario_dispatch
from current_model.core.project_io import export_project_from_session, sync_active_scenario_into_session
from current_model.ui.common.session_utils import (
    find_active_load_data_in_session,
    find_active_contract_in_session,
    get_load_profile_summary
)
from current_model.ui.common.cards import render_kpi_card
from current_model.ui.tab_generator.charts import (
    create_generator_multi_asset_dispatch_chart,
    create_cumulative_payment_chart
)


def render_tab_generator(key_prefix: str = "app_tab_generator") -> None:
    """
    Main entry point for the Dynamic Generator / Genset Sub-Scenario tab.
    """
    # 1. Discover Project & Active Sub-Scenario
    project: ProjectContainer = export_project_from_session()
    active_sub = project.get_active_scenario()

    if active_sub is None:
        st.info(
            "### :material/lock: Status Quo Active\n\n"
            "The **Generator / Genset** module is an intervention asset configured on Sub-Scenarios. "
            "Please switch to or create a Sub-Scenario in the Sidebar to configure on-site generation."
        )
        return

    # 2. Discover Load Profile & Contract
    df_load, load_desc, power_col = find_active_load_data_in_session(prefer_annual=True)
    active_contract = active_sub.custom_contract or project.base_scenario.base_contract or find_active_contract_in_session()

    if active_contract is None:
        active_contract = Contract(
            name="Standard Industrial Contract (400 kW Limit)",
            contracted_capacity_kw=400.0,
            monthly_capacity_tariff=0.15,
            default_energy_rate=0.20,
            currency="EUR"
        )

    contract_cap_kw = float(getattr(active_contract, "contracted_capacity_kw", 0.0) or 0.0)

    # Ensure generator config exists and directly binds to contract capacity limit
    if active_sub.generator_config is None:
        active_sub.generator_config = GeneratorConfig(
            rated_power_kw=100.0,
            fuel_type="Diesel",
            dispatch_mode="peak_shaving_assist",
            peak_shaving_trigger_kw=contract_cap_kw if contract_cap_kw > 0 else 400.0,
            is_backup_mode=False
        )
        st.session_state["project_container"] = project

    gen_cfg = active_sub.generator_config
    if (not gen_cfg.peak_shaving_trigger_kw or gen_cfg.peak_shaving_trigger_kw <= 0) and contract_cap_kw > 0:
        gen_cfg.peak_shaving_trigger_kw = contract_cap_kw

    if df_load is None or df_load.empty or not power_col:
        st.info(
            "### :material/info: No Active Load Profile Found\n\n"
            "Please configure or generate a consumption profile in **Tab 2: Consumption (Baseline)** "
            "(via CSV meter upload or synthetic simulator) to evaluate Generator dispatch."
        )
        return

    load_summary = get_load_profile_summary(df_load, power_col)
    peak_kw = float(load_summary.get("peak_kw", 0.0))
    total_kwh = float(load_summary.get("total_kwh", 0.0))
    total_intervals = len(df_load)
    total_days = max(1, int(np.ceil(total_intervals * 0.25 / 24.0)))

    # Determine Currency
    currency = getattr(gen_cfg, "currency", None) or getattr(active_contract, "currency", "EUR")

    # 3. Detect Operational Mode: Standalone vs. Hybrid Residual Backup
    has_solar = active_sub.include_solar and active_sub.solar_config is not None
    has_bess = active_sub.include_bess and active_sub.bess_config is not None
    is_hybrid = has_solar or has_bess

    tech_elements = []
    if has_solar:
        tech_elements.append(f"Solar PV ({active_sub.solar_config.dc_capacity_kwp:.0f} kWp)")
    if has_bess:
        tech_elements.append(f"BESS ({active_sub.bess_config.capacity_kwh:.0f} kWh)")

    if is_hybrid:
        st.info(
            f":material/alt_route: **Hybrid Multi-Asset Scenario ({' + '.join(tech_elements)} + Generator)**  \n"
            f"The Generator is operating as a **Residual Load Peaker & Backup Asset**. It dispatches specifically on the "
            f"residual power demand remaining after direct Solar consumption and Battery discharge."
        )
    else:
        st.info(
            ":material/local_gas_station: **Standalone Generator Scenario**  \n"
            "The Generator operates directly on the facility baseline load profile to shave grid peaks or support islanded baseload."
        )

    # 4. Compute Upstream Dispatch (if Hybrid) to obtain exact Residual Load
    with st.spinner("Computing energy dispatch across upstream modules..."):
        hybrid_dispatch = simulate_hybrid_scenario_dispatch(
            sub_scenario=active_sub,
            df_load=df_load,
            power_col=power_col,
            contract=active_contract,
            location=project.base_scenario.location,
            step_hours=0.25
        )

    p_residual_pre_gen = hybrid_dispatch["p_residual_pre_gen"]
    p_solar_direct = hybrid_dispatch["p_solar_direct"] if has_solar else None
    p_bess_dis = hybrid_dispatch["p_bess_dis"] if has_bess else None

    residual_peak_kw = float(np.max(p_residual_pre_gen)) if len(p_residual_pre_gen) > 0 else peak_kw
    residual_total_kwh = float(np.sum(p_residual_pre_gen) * 0.25)
    is_overloaded = (residual_peak_kw > contract_cap_kw)
    overload_kw = max(0.0, residual_peak_kw - contract_cap_kw)

    # 5. Diagnostic Status Cards
    col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4)
    with col_stat1:
        render_kpi_card(
            title=":material/analytics: Facility Peak Demand",
            value=f"{peak_kw:.1f} kW",
            subtext=f"Total: {total_kwh:,.0f} kWh/a",
            status="default"
        )
    with col_stat2:
        render_kpi_card(
            title=":material/speed: Contracted Grid Limit",
            value=f"{contract_cap_kw:.0f} kW",
            subtext=f"Contract: {active_contract.name[:22]}",
            status="default"
        )
    with col_stat3:
        if is_hybrid:
            render_kpi_card(
                title=":material/alt_route: Residual Peak to Genset",
                value=f"{residual_peak_kw:.1f} kW",
                subtext=f"Residual Demand: {residual_total_kwh:,.0f} kWh",
                status="alert" if is_overloaded else "ok"
            )
        else:
            status_theme = "alert" if is_overloaded else "ok"
            render_kpi_card(
                title=":material/warning: Overload Status",
                value=f"+{overload_kw:.1f} kW Overload" if is_overloaded else "Within Limit",
                subtext="Grid Capacity Exceeded!" if is_overloaded else "No Overload Violations",
                status=status_theme
            )
    with col_stat4:
        suggested_kw = max(50.0, round((overload_kw * 1.25) / 25.0) * 25.0) if is_overloaded else 100.0
        render_kpi_card(
            title=":material/local_gas_station: Configured Capacity",
            value=f"{gen_cfg.rated_power_kw:.0f} kW",
            subtext=f"Role: {'Residual Backup' if getattr(gen_cfg, 'is_backup_mode', False) else 'Peak Shaver'}",
            status="default"
        )

    st.markdown("---")

    # 6. Generator Configuration Form
    st.subheader(":material/settings: Generator Technical & Commercial Sizing")

    presets = get_generator_presets()
    preset_names = ["Custom"] + list(presets.keys())

    selected_preset = st.selectbox(
        "Load Pre-Configured Generator Model Preset:",
        options=preset_names,
        index=0,
        key=f"{key_prefix}_preset_select"
    )

    if selected_preset != "Custom" and selected_preset in presets:
        base_cfg = presets[selected_preset]
        init_power_kw = float(base_cfg.rated_power_kw)
        init_fuel_type = base_cfg.fuel_type
        init_fuel_price = float(base_cfg.fuel_price_per_unit)
        init_maint_cost = float(base_cfg.maintenance_cost_per_op_hour)
        init_capex = float(base_cfg.capital_cost)
        init_trigger = contract_cap_kw if contract_cap_kw > 0 else float(base_cfg.peak_shaving_trigger_kw or 400.0)
        init_mode = base_cfg.dispatch_mode
        init_is_backup = (base_cfg.dispatch_mode in ["emergency_baseload", "residual_load_follow"])
    else:
        init_power_kw = float(gen_cfg.rated_power_kw or suggested_kw)
        init_fuel_type = gen_cfg.fuel_type or "Diesel"
        init_fuel_price = float(gen_cfg.fuel_price_per_unit or 1.45)
        init_maint_cost = float(gen_cfg.maintenance_cost_per_op_hour or 4.50)
        init_capex = float(gen_cfg.capital_cost or 18000.0)
        if contract_cap_kw > 0:
            init_trigger = float(gen_cfg.peak_shaving_trigger_kw) if (gen_cfg.peak_shaving_trigger_kw and gen_cfg.peak_shaving_trigger_kw > 0) else contract_cap_kw
        else:
            init_trigger = float(gen_cfg.peak_shaving_trigger_kw or 400.0)
        init_mode = gen_cfg.dispatch_mode or "peak_shaving_assist"
        init_is_backup = getattr(gen_cfg, "is_backup_mode", False)

    with st.form(key=f"{key_prefix}_generator_form"):
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            gen_power_kw = st.number_input(
                "Generator Rated Power (kW):",
                min_value=10.0,
                max_value=5000.0,
                value=float(init_power_kw),
                step=25.0,
                help="Continuous rated electrical output capacity of the generator set."
            )

            # Strategy Selection
            strategy_options = [
                "Peak Shaving Assist (shave peaks exceeding threshold)",
                "Full Residual Backup / Deficit Follower (cover unmet deficit)"
            ]
            default_strat_idx = 1 if (init_is_backup or is_hybrid and init_mode == "residual_load_follow") else 0
            strat_choice = st.selectbox(
                "Operational Dispatch Strategy:",
                options=strategy_options,
                index=default_strat_idx,
                help="Choose whether the generator acts as an overload peaker above a set limit or as a deficit follower."
            )
            form_is_backup = ("Full Residual Backup" in strat_choice)

            if form_is_backup:
                cov_pct = st.slider(
                    "Residual Deficit Target Coverage (%):",
                    min_value=10.0,
                    max_value=100.0,
                    value=float(getattr(gen_cfg, "backup_coverage_pct", 100.0)),
                    step=5.0,
                    help="Percentage of unmet deficit after Solar and BESS to cover with generator."
                )
                form_trigger_kw = contract_cap_kw if contract_cap_kw > 0 else 0.0
            else:
                help_text = (
                    f"Generator starts when load/residual load exceeds this active capacity cap. "
                    f"Initialized directly from contracted grid limit ({contract_cap_kw:,.1f} kW)."
                    if contract_cap_kw > 0 else
                    "Generator starts when load/residual load exceeds this active capacity cap."
                )
                form_trigger_kw = st.number_input(
                    "Dispatch Trigger Threshold (kW):",
                    min_value=10.0,
                    max_value=5000.0,
                    value=float(init_trigger if init_trigger > 0 else (contract_cap_kw if contract_cap_kw > 0 else 400.0)),
                    step=25.0,
                    help=help_text
                )
                if contract_cap_kw > 0:
                    st.caption(f":material/speed: Contract limit: **{contract_cap_kw:,.1f} kW** ({active_contract.name})")
                cov_pct = 100.0

        with col_f2:
            fuel_type_opts = ["Diesel", "Natural Gas", "HVO/Biofuel"]
            fuel_idx = fuel_type_opts.index(init_fuel_type) if init_fuel_type in fuel_type_opts else 0
            fuel_type = st.selectbox("Fuel Type:", options=fuel_type_opts, index=fuel_idx)

            fuel_price = st.number_input(
                f"Fuel Price ({currency}/Liter or m³):",
                min_value=0.01,
                max_value=10000.0,
                value=float(init_fuel_price),
                step=0.05
            )

            maint_per_hour = st.number_input(
                f"Maintenance Cost ({currency}/operating hour):",
                min_value=0.0,
                max_value=1000.0,
                value=float(init_maint_cost),
                step=0.5
            )

            min_load_pct = st.slider(
                "Minimum Loading Ratio (%):",
                min_value=0.0,
                max_value=50.0,
                value=float(gen_cfg.min_load_ratio_pct or 25.0),
                step=5.0,
                help="Minimum engine loading to prevent wet-stacking and cylinder glazing."
            )

        with col_f3:
            default_acq_idx = 0 if (gen_cfg.monthly_lease_fee > 0) else 1
            acq_mode = st.radio("Acquisition Model:", options=["Rental / Monthly Lease", "Capital Purchase (CAPEX)"], index=default_acq_idx)

            if acq_mode == "Rental / Monthly Lease":
                monthly_lease = st.number_input(
                    f"Monthly Equipment Lease Fee ({currency}/mo):",
                    min_value=0.0,
                    max_value=500000.0,
                    value=float(gen_cfg.monthly_lease_fee or 1200.0),
                    step=100.0
                )
                capital_cost = 0.0
            else:
                capital_cost = st.number_input(
                    f"Turnkey Purchase CAPEX ({currency}):",
                    min_value=0.0,
                    max_value=5000000.0,
                    value=float(init_capex or 18000.0),
                    step=1000.0
                )
                monthly_lease = 0.0

        submitted = st.form_submit_button(
            ":material/sync: Run Simulation & Synchronize with Sub-Scenario",
            type="primary",
            use_container_width=True
        )

    if submitted:
        gen_cfg.rated_power_kw = float(gen_power_kw)
        gen_cfg.fuel_type = str(fuel_type)
        gen_cfg.min_load_ratio_pct = float(min_load_pct)
        gen_cfg.is_backup_mode = bool(form_is_backup)
        gen_cfg.dispatch_mode = "residual_load_follow" if form_is_backup else "peak_shaving_assist"
        gen_cfg.peak_shaving_trigger_kw = float(form_trigger_kw)
        gen_cfg.backup_coverage_pct = float(cov_pct)
        gen_cfg.fuel_price_per_unit = float(fuel_price)
        gen_cfg.maintenance_cost_per_op_hour = float(maint_per_hour)
        gen_cfg.capital_cost = float(capital_cost)
        gen_cfg.monthly_lease_fee = float(monthly_lease)
        gen_cfg.currency = currency

        active_sub.generator_config = gen_cfg
        st.session_state["project_container"] = project
        st.success(":material/check_circle: Generator configuration updated and synchronized with active Sub-Scenario.")

    # 7. Execute 15-Minute Generator Dispatch
    sim_result = simulate_generator_peaking(
        df_load=df_load,
        power_col=power_col,
        contract=active_contract,
        gen_config=gen_cfg,
        step_hours=0.25,
        residual_series=p_residual_pre_gen,
        solar_direct_series=p_solar_direct,
        bess_discharge_series=p_bess_dis
    )

    kpis: GeneratorKPIs = sim_result["kpis"]
    df_dispatch = sim_result["df_dispatch"]
    df_zahlungsreihe = sim_result["df_zahlungsreihe"]
    shaved_peak = sim_result["peak_shaved_kw"]
    new_peak = sim_result["new_peak_kw"]
    annual_savings = sim_result["annual_net_savings"]

    # Cache KPIs in SubScenario
    active_sub.summary_kpis["generator_generation_kwh"] = kpis.total_generation_kwh
    active_sub.summary_kpis["generator_operating_hours"] = kpis.operating_hours
    active_sub.summary_kpis["generator_fuel_units"] = kpis.total_fuel_units
    active_sub.summary_kpis["generator_operating_cost"] = kpis.total_operating_cost
    active_sub.summary_kpis["generator_peak_shaved_kw"] = shaved_peak

    st.markdown("---")

    # 8. Executive KPI Results Cards
    st.subheader(":material/speed: Dispatch Performance & Peaking Results")

    col_r1, col_r2, col_r3, col_r4 = st.columns(4)
    with col_r1:
        render_kpi_card(
            title=":material/compress: Shaved Peak Demand",
            value=f"{shaved_peak:.1f} kW",
            subtext=f"New Grid Peak: {new_peak:.1f} kW",
            status="ok" if shaved_peak > 0 else "default"
        )
    with col_r2:
        render_kpi_card(
            title=":material/timer: Generator Runtime",
            value=f"{kpis.operating_hours:.1f} hrs",
            subtext=f"Generated: {kpis.total_generation_kwh:,.0f} kWh ({kpis.starts_count} starts)",
            status="default"
        )
    with col_r3:
        render_kpi_card(
            title=":material/local_gas_station: Fuel Consumption",
            value=f"{kpis.total_fuel_units:,.1f} {('L' if gen_cfg.fuel_type != 'Natural Gas' else 'm³')}",
            subtext=f"Fuel OPEX: {kpis.fuel_cost_total:,.0f} {currency}",
            status="default"
        )
    with col_r4:
        is_pos = (annual_savings > 0)
        render_kpi_card(
            title=":material/payments: Net Annual Impact",
            value=f"{annual_savings:,.0f} {currency}/a",
            subtext="Generates Net Savings!" if is_pos else "Genset Adds Operational Cost",
            status="ok" if is_pos else "alert"
        )

    # 9. 15-Minute Interactive Multi-Asset Dispatch Chart
    st.markdown("#### :material/show_chart: 15-Minute Electrical Dispatch Curve")

    effective_trigger = contract_cap_kw if (contract_cap_kw > 0 and getattr(gen_cfg, "is_backup_mode", False)) else (
        float(gen_cfg.peak_shaving_trigger_kw) if (gen_cfg.peak_shaving_trigger_kw and gen_cfg.peak_shaving_trigger_kw > 0) else (contract_cap_kw if contract_cap_kw > 0 else 400.0)
    )

    fig_dispatch = create_generator_multi_asset_dispatch_chart(
        df_dispatch=df_dispatch,
        trigger_kw=effective_trigger,
        days_to_show=None,
        is_hybrid=is_hybrid
    )
    st.plotly_chart(fig_dispatch, use_container_width=True)

    # 10. Cumulative Payment Trajectory (Kumulierte Zahlungsreihe)
    st.markdown("#### :material/stacked_line_chart: Cumulative Payment Trajectory (Kumulierte Zahlungsreihe)")
    fig_payment = create_cumulative_payment_chart(df_zahlungsreihe, currency=currency)
    st.plotly_chart(fig_payment, use_container_width=True)

    # 11. Month-by-Month Financial Table (Zahlungsreihe)
    with st.expander(":material/table_chart: Detailed Monthly Payment Schedule (Zahlungsreihe Table)", expanded=False):
        display_df = df_zahlungsreihe.rename(columns={
            "Month": "Billing Month",
            "Baseline_Peak_kW": "Baseline Peak (kW)",
            "New_Grid_Peak_kW": "New Peak (kW)",
            "Peak_Shaved_kW": "Peak Shaved (kW)",
            "Gen_Hours": "Genset Hours (h)",
            "Fuel_Liters": f"Fuel ({'L' if gen_cfg.fuel_type != 'Natural Gas' else 'm³'})",
            "Status_Quo_Bill": f"Status Quo Bill ({currency})",
            "New_Grid_Bill": f"New Grid Bill ({currency})",
            "Generator_Cost": f"Genset Expenses ({currency})",
            "Total_With_Generator": f"Total with Genset ({currency})",
            "Monthly_Savings": f"Net Monthly Savings ({currency})",
            "Cum_Status_Quo": f"Cum. Status Quo ({currency})",
            "Cum_With_Generator": f"Cum. with Genset ({currency})",
            "Cum_Savings": f"Cum. Savings ({currency})"
        })
        cols_to_show = [
            "Billing Month", "Baseline Peak (kW)", "New Peak (kW)", "Peak Shaved (kW)",
            "Genset Hours (h)", f"Fuel ({'L' if gen_cfg.fuel_type != 'Natural Gas' else 'm³'})",
            f"Status Quo Bill ({currency})", f"New Grid Bill ({currency})", f"Genset Expenses ({currency})",
            f"Total with Genset ({currency})", f"Net Monthly Savings ({currency})",
            f"Cum. Status Quo ({currency})", f"Cum. with Genset ({currency})", f"Cum. Savings ({currency})"
        ]
        st.dataframe(display_df[cols_to_show], use_container_width=True)
