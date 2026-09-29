"""
========================================================================================
Tab: Solar PV + BESS Hybrid Simulator (Beta) (ui/tab_hybrid_beta/view.py)
========================================================================================

Description:
------------
Standalone, isolated Beta module evaluating unified Solar PV + Battery Storage (BESS):
  - Ingests active 15-minute facility load profile from Tab 1 and contract from Tab 2 in read-only mode.
  - Strictly isolated: Does not mutate or export sub-scenarios into the master scenario container.
  - Streamlined, non-financial configuration focused purely on physical parameters.
  - Strict priority ladder: Solar directly powers load -> Surplus charges BESS -> Excess exported to grid
    -> BESS discharges on deficit/peaks -> Grid covers remaining demand.
  - Real-time 15-minute multi-layer interactive dispatch charts, SoC envelopes, and monthly balances.
"""

from typing import Optional, Dict, Any, List
import streamlit as st
import pandas as pd
import numpy as np

from current_model.models.solar import SolarPVConfig, SolarLocation, TECHNOLOGY_SPECS
from current_model.models.bess import BESSConfig
from current_model.models.contract import Contract
from current_model.core.solar_bess_engine import (
    simulate_solar_bess_dispatch,
    SolarBESSSimulationResult,
    SolarBESSKPIs
)
from current_model.ui.common.session_utils import (
    find_active_load_data_in_session,
    find_active_contract_in_session,
    get_load_profile_summary
)
from current_model.ui.common.cards import render_kpi_card
from current_model.ui.tab_hybrid_beta.charts import (
    create_hybrid_dispatch_chart,
    create_hybrid_soc_chart,
    create_hybrid_monthly_balance_chart,
    create_hybrid_duration_curve
)


def render_tab_solar_bess_beta(key_prefix: str = "app_solar_bess_beta") -> None:
    """
    Main entry point for the isolated Solar + BESS Hybrid Simulator (Beta).
    """
    # --------------------------------------------------------------------------
    # 0. Prominent Experimental Beta Warning Banner
    # --------------------------------------------------------------------------
    st.warning(
        ":material/science: **Solar PV + BESS Hybrid Simulator (Experimental Beta - Physical Dispatch Only)**  \n"
        "This isolated module evaluates the combined energetic operation of on-site **Solar PV and Battery Storage (BESS)**. "
        "It simulates 15-minute energy flows with strict priority hierarchy: Solar directly serves facility demand first; "
        "surplus solar charges the battery before exporting to the grid; and the battery discharges during solar deficits or peaks.  \n"
        "*Note: This tab is fully isolated. It reads baseline load and grid contract in read-only mode without financial metrics or sub-scenario exports.*"
    )

    # --------------------------------------------------------------------------
    # 1. Discover Active Load & Contract in Workspace
    # --------------------------------------------------------------------------
    df_load, load_desc, power_col = find_active_load_data_in_session(prefer_annual=True)
    active_contract = find_active_contract_in_session()

    if active_contract is None:
        active_contract = Contract(
            name="Standard Industrial Contract (400 kW Limit)",
            contracted_capacity_kw=400.0,
            monthly_capacity_tariff=0.15,
            default_energy_rate=0.20,
            currency="EUR"
        )

    if df_load is None or df_load.empty or not power_col:
        st.info(
            "### :material/info: No Active Load Profile Found\n\n"
            "Please configure or generate a consumption profile in **Tab 2: Consumption (Baseline)** "
            "(via CSV real meter upload or the 365-day synthetic simulator) to run the Solar + BESS simulation."
        )
        return

    load_summary = get_load_profile_summary(df_load, power_col)
    peak_kw = float(load_summary.get("peak_kw", 0.0))
    total_kwh = float(load_summary.get("total_kwh", 0.0))
    contract_cap_kw = float(active_contract.contracted_capacity_kw)
    total_intervals = len(df_load)
    total_days = max(1, int(np.ceil(total_intervals * 0.25 / 24.0)))

    is_overloaded = (peak_kw > contract_cap_kw)
    overload_kw = max(0.0, peak_kw - contract_cap_kw)

    st.markdown(f"**Active Facility Profile:** `{load_desc}` | **Analysis Horizon:** `{total_days} Days ({total_intervals:,} intervals)`")

    # --------------------------------------------------------------------------
    # 2. Diagnostic Status Cards
    # --------------------------------------------------------------------------
    col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4)
    with col_stat1:
        render_kpi_card(
            title=":material/analytics: Facility Peak Demand",
            value=f"{peak_kw:.1f} kW",
            subtext=f"Total Demand: {total_kwh:,.0f} kWh/a",
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
        status_theme = "alert" if is_overloaded else "ok"
        status_val = f"+{overload_kw:.1f} kW Overload" if is_overloaded else "Within Limit"
        status_sub = "Grid Overload Detected" if is_overloaded else "No Overload Violations"
        render_kpi_card(
            title=":material/warning: Overload Status",
            value=status_val,
            subtext=status_sub,
            status=status_theme
        )
    with col_stat4:
        # Suggested battery size indicator
        sugg_cap = round(overload_kw * 2.0 / 25.0) * 25.0 if is_overloaded else 100.0
        render_kpi_card(
            title=":material/battery_charging_full: Recommended BESS",
            value=f"{max(50.0, sugg_cap):.0f} kWh",
            subtext="Baseline Sizing Benchmark",
            status="default"
        )

    st.markdown("---")

    # --------------------------------------------------------------------------
    # 3. Streamlined Physical Configuration Form (Solar + BESS)
    # --------------------------------------------------------------------------
    st.subheader(":material/tune: Hybrid System Physical Sizing (No Financial Data)")

    # Suggested solar sizing: ~50-80% of peak load
    suggested_solar_kwp = max(50.0, round((peak_kw * 0.70) / 25.0) * 25.0)
    suggested_bess_kwh = max(50.0, round((peak_kw * 0.50) / 25.0) * 25.0)
    suggested_bess_kw = max(25.0, round((suggested_bess_kwh * 0.50) / 10.0) * 10.0)

    with st.form(key=f"{key_prefix}_hybrid_form"):
        col_solar, col_bess = st.columns(2)

        # 3.1 Solar PV Parameters
        with col_solar:
            st.markdown("##### :material/solar_power: Solar PV Sizing")
            solar_kwp = st.number_input(
                "Installed Solar Capacity (kWp)",
                min_value=5.0,
                max_value=5000.0,
                value=float(st.session_state.get(f"{key_prefix}_solar_kwp", suggested_solar_kwp)),
                step=25.0,
                help="Total DC peak rated capacity of the photovoltaic array."
            )
            inverter_kw = st.number_input(
                "Inverter AC Capacity (kW)",
                min_value=5.0,
                max_value=5000.0,
                value=float(st.session_state.get(f"{key_prefix}_inverter_kw", round(solar_kwp * 0.85, 1))),
                step=25.0,
                help="Maximum continuous AC power rating of the solar inverters (clipping limit)."
            )

            col_s1, col_s2 = st.columns(2)
            with col_s1:
                tech_choice = st.selectbox(
                    "Cell Technology",
                    options=["TOPCon", "PERC", "Backcontact"],
                    index=0,
                    help="TOPCon (N-Type standard), PERC (P-Type legacy), or Backcontact (IBC high-efficiency)."
                )
                tilt_deg = st.number_input("Tilt Angle (°)", min_value=0.0, max_value=90.0, value=30.0, step=5.0)
            with col_s2:
                mounting = st.selectbox("Mounting Type", options=["Open-Rack (Ground/Carport)", "Flush Roof"], index=0)
                azimuth_deg = st.number_input(
                    "Azimuth (°)",
                    min_value=-180.0,
                    max_value=180.0,
                    value=0.0,
                    step=15.0,
                    help="0° = North (South Hemisphere), 180° = South (North Hemisphere)."
                )

        # 3.2 BESS Parameters
        with col_bess:
            st.markdown("##### :material/battery_charging_full: Battery Storage (BESS) Sizing")
            bess_kwh = st.number_input(
                "BESS Energy Capacity (kWh)",
                min_value=10.0,
                max_value=10000.0,
                value=float(st.session_state.get(f"{key_prefix}_bess_kwh", suggested_bess_kwh)),
                step=25.0,
                help="Nominal nameplate energy storage capacity."
            )
            col_b1, col_b2 = st.columns(2)
            with col_b1:
                bess_chg_kw = st.number_input(
                    "Max Charge Power (kW)",
                    min_value=5.0,
                    max_value=5000.0,
                    value=float(st.session_state.get(f"{key_prefix}_bess_chg_kw", suggested_bess_kw)),
                    step=10.0,
                    help="Maximum continuous charging power (from solar surplus)."
                )
                soc_min = st.slider("Min State of Charge (SoC Min %)", min_value=0.0, max_value=30.0, value=10.0, step=5.0)
            with col_b2:
                bess_dis_kw = st.number_input(
                    "Max Discharge Power (kW)",
                    min_value=5.0,
                    max_value=5000.0,
                    value=float(st.session_state.get(f"{key_prefix}_bess_dis_kw", suggested_bess_kw)),
                    step=10.0,
                    help="Maximum continuous discharge power into facility load."
                )
                soc_max = st.slider("Max State of Charge (SoC Max %)", min_value=70.0, max_value=100.0, value=90.0, step=5.0)

            dispatch_strat = st.radio(
                "BESS Discharge Strategy",
                options=[
                    "Self-Consumption Maximization (Discharge on any residual load)",
                    "Peak Shaving (Only discharge when residual load exceeds target cap)"
                ],
                index=0,
                help="Choose whether the battery discharges to cover all deficit load or strictly preserves energy for peaks above a limit."
            )

            is_peak_shaving = ("Peak Shaving" in dispatch_strat)
            target_shaving_cap = st.number_input(
                "Target Shaving Limit / Grid Cap (kW)",
                min_value=10.0,
                max_value=5000.0,
                value=float(contract_cap_kw),
                step=25.0,
                help="Used in peak shaving mode to cap residual demand draw from the utility grid."
            )

        submit_btn = st.form_submit_button(
            ":material/play_arrow: Run 15-Minute Solar + BESS Hybrid Simulation",
            type="primary"
        )

    # Persist input settings in session state for reactivity
    st.session_state[f"{key_prefix}_solar_kwp"] = solar_kwp
    st.session_state[f"{key_prefix}_inverter_kw"] = inverter_kw
    st.session_state[f"{key_prefix}_bess_kwh"] = bess_kwh
    st.session_state[f"{key_prefix}_bess_chg_kw"] = bess_chg_kw
    st.session_state[f"{key_prefix}_bess_dis_kw"] = bess_dis_kw

    # --------------------------------------------------------------------------
    # 4. Assemble Configurations & Execute Simulation
    # --------------------------------------------------------------------------
    # Module spec calculation
    tech_spec = TECHNOLOGY_SPECS.get(tech_choice, TECHNOLOGY_SPECS["TOPCon"])
    mod_wp = float(tech_spec.get("power_wp", 450.0))
    mod_count = max(1, int(round((solar_kwp * 1000.0) / mod_wp)))

    solar_config = SolarPVConfig(
        module_count=mod_count,
        module_power_wp=mod_wp,
        technology_preset=tech_choice,
        module_technology=tech_spec.get("name", "N-Type TOPCon"),
        inverter_capacity_kw=float(inverter_kw),
        tilt_deg=float(tilt_deg),
        azimuth_deg=float(azimuth_deg),
        mounting_type=mounting,
        weather_mode="TMY"
    )

    strat_key = "peak_shaving" if is_peak_shaving else "self_consumption"
    bess_config = BESSConfig(
        capacity_kwh=float(bess_kwh),
        max_charge_power_kw=float(bess_chg_kw),
        max_discharge_power_kw=float(bess_dis_kw),
        soc_min_pct=float(soc_min),
        soc_max_pct=float(soc_max),
        initial_soc_pct=50.0,
        dispatch_strategy=strat_key,
        peak_shaving_threshold_kw=float(target_shaving_cap),
        round_trip_efficiency_pct=90.0,
        is_financial_enabled=False
    )

    with st.spinner("Executing high-resolution 15-minute Solar PV + BESS hybrid dispatch..."):
        sim_res: SolarBESSSimulationResult = simulate_solar_bess_dispatch(
            load_df=df_load,
            solar_config=solar_config,
            bess_config=bess_config,
            grid_limit_kw=float(contract_cap_kw),
            power_col=power_col,
            step_hours=0.25
        )

    kpis: SolarBESSKPIs = sim_res.kpis
    df_dispatch = sim_res.df_dispatch
    monthly_metrics = sim_res.monthly_metrics

    st.markdown("---")

    # --------------------------------------------------------------------------
    # 5. Hybrid Results & Physical Performance Indicators
    # --------------------------------------------------------------------------
    st.subheader(":material/insights: Hybrid Physical Performance & Self-Sufficiency KPIs")

    # Row 1: Generation, Autarky, Self-Consumption, Peak Shaving
    col_k1, col_k2, col_k3, col_k4 = st.columns(4)
    with col_k1:
        render_kpi_card(
            title=":material/solar_power: Solar PV Generation",
            value=f"{kpis.annual_solar_kwh:,.0f} kWh/a",
            subtext=f"Installed DC: {solar_kwp:.1f} kWp",
            status="default"
        )
    with col_k2:
        render_kpi_card(
            title=":material/bolt: Autarky / Solar Fraction",
            value=f"{kpis.autarky_rate_pct:.1f} %",
            subtext=f"Direct: {kpis.direct_consumption_pct:.1f}% | BESS: {kpis.bess_charged_from_pv_pct:.1f}%",
            status="ok" if kpis.autarky_rate_pct >= 40.0 else "default"
        )
    with col_k3:
        render_kpi_card(
            title=":material/sync: Total Self-Consumption",
            value=f"{kpis.self_consumption_rate_pct:.1f} %",
            subtext=f"Used On-Site: {kpis.total_self_consumption_kwh:,.0f} kWh/a",
            status="ok" if kpis.self_consumption_rate_pct >= 70.0 else "default"
        )
    with col_k4:
        peak_status = "ok" if kpis.peak_shaved_kw > 0.1 else "default"
        render_kpi_card(
            title=":material/trending_down: Grid Peak Reduction",
            value=f"-{kpis.peak_shaved_kw:.1f} kW",
            subtext=f"{kpis.orig_peak_kw:.1f} kW → {kpis.new_peak_kw:.1f} kW (-{kpis.peak_reduction_pct:.1f}%)",
            status=peak_status
        )

    # Row 2: Grid Import Reduction, BESS Cycles, Grid Export, Violations
    col_k5, col_k6, col_k7, col_k8 = st.columns(4)
    with col_k5:
        render_kpi_card(
            title=":material/arrow_downward: Grid Import Avoided",
            value=f"-{kpis.grid_import_reduction_kwh:,.0f} kWh",
            subtext=f"Remaining Import: {kpis.annual_grid_import_kwh:,.0f} kWh/a (-{kpis.grid_import_reduction_pct:.1f}%)",
            status="ok"
        )
    with col_k6:
        render_kpi_card(
            title=":material/sync_alt: Battery Utilization",
            value=f"{kpis.bess_full_cycles:.1f} Cycles/a",
            subtext=f"Throughput: {kpis.bess_discharged_kwh:,.0f} kWh/a",
            status="default"
        )
    with col_k7:
        render_kpi_card(
            title=":material/upload: Surplus Grid Feed-in",
            value=f"{kpis.annual_grid_export_kwh:,.0f} kWh/a",
            subtext=f"Export Share: {kpis.grid_export_pct:.1f}% of Solar",
            status="default"
        )
    with col_k8:
        v_status = "ok" if kpis.new_violations_count == 0 else "alert"
        render_kpi_card(
            title=":material/security: Overload Violations",
            value=f"{kpis.new_violations_count} intervals",
            subtext=f"Before: {kpis.orig_violations_count} ({kpis.violations_eliminated_pct:.0f}% eliminated)",
            status=v_status
        )

    st.markdown("---")

    # --------------------------------------------------------------------------
    # 6. Interactive Visualizations Suite
    # --------------------------------------------------------------------------
    tab_chart1, tab_chart2, tab_chart3, tab_chart4, tab_chart5 = st.tabs([
        ":material/show_chart: 15-Min Dispatch Curve",
        ":material/battery_charging_full: BESS State of Charge (SoC)",
        ":material/bar_chart: Monthly Energy Balance",
        ":material/stacked_line_chart: Load Duration & Peak Shaving",
        ":material/table_chart: Monthly Summary Table"
    ])

    with tab_chart1:
        st.markdown("##### 15-Minute Combined Power Dispatch (Load, Solar, Battery, Grid)")
        col_ctrl1, col_ctrl2 = st.columns([3, 1])
        with col_ctrl2:
            days_sample = st.select_slider(
                "Display Sample Duration",
                options=[1, 3, 7, 14, 30, "Full Period"],
                value=7,
                key=f"{key_prefix}_days_slider"
            )
        sample_days = None if days_sample == "Full Period" else int(days_sample)
        fig_dispatch = create_hybrid_dispatch_chart(df_dispatch, target_cap_kw=float(target_shaving_cap), days_to_show=sample_days)
        st.plotly_chart(fig_dispatch, use_container_width=True)

    with tab_chart2:
        st.markdown("##### Battery Storage State of Charge (%) & Operating Limits")
        fig_soc = create_hybrid_soc_chart(df_dispatch, soc_min_pct=float(soc_min), soc_max_pct=float(soc_max), days_to_show=sample_days)
        st.plotly_chart(fig_soc, use_container_width=True)

    with tab_chart3:
        st.markdown("##### Monthly Energy Balance & Sourcing Composition")
        fig_monthly = create_hybrid_monthly_balance_chart(monthly_metrics)
        st.plotly_chart(fig_monthly, use_container_width=True)

    with tab_chart4:
        st.markdown("##### Load Duration Curve: Peak Demand Shaving & Overload Mitigation")
        fig_duration = create_hybrid_duration_curve(df_dispatch, grid_limit_kw=float(contract_cap_kw))
        st.plotly_chart(fig_duration, use_container_width=True)

    with tab_chart5:
        st.markdown("##### Monthly Energy Metrics Breakdown (MWh)")
        df_monthly_table = pd.DataFrame([
            {
                "Month": m["month_name"],
                "Load Demand (MWh)": round(m["load_kwh"] / 1000.0, 2),
                "Solar PV (MWh)": round(m["solar_kwh"] / 1000.0, 2),
                "Direct PV (MWh)": round(m["direct_kwh"] / 1000.0, 2),
                "BESS Charge (MWh)": round(m["bess_charge_kwh"] / 1000.0, 2),
                "BESS Discharge (MWh)": round(m["bess_discharge_kwh"] / 1000.0, 2),
                "Net Grid Import (MWh)": round(m["grid_import_kwh"] / 1000.0, 2),
                "Grid Feed-In (MWh)": round(m["grid_export_kwh"] / 1000.0, 2),
                "Peak Load (kW)": round(m["orig_peak_kw"], 1),
                "New Grid Peak (kW)": round(m["new_peak_kw"], 1)
            }
            for m in monthly_metrics
        ])
        st.dataframe(df_monthly_table, use_container_width=True, hide_index=True)
