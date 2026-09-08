"""
========================================================================================
Sub-Tab 3.2: Solar & Consumption Integration View (ui/tab3_solar/integration_view.py)
========================================================================================

Description:
------------
Orchestrates the coupled Solar PV and Electrical Consumption analysis (Sub-Tab 3.2):
  - Ingests active load profile from Tab 1 (CSV real meter or 365d/24h Synthetic).
  - Target auto-sizing toolbar: 40%, 60%, 80%, 100% Net Annual Coverage.
  - Interval-by-interval 15-minute electrical dispatch calculation (Direct, Surplus, Residual).
  - Key Performance Indicators:
      * Self-Consumption Rate (SCR % / Eigenverbrauchsquote)
      * Autarky Rate / Solar Fraction (SF % / Autarkiegrad)
      * Surplus export and Residual grid purchase (kWh & MWh)
      * Peak demand shaving (kW reduction)
  - Interactive Plotly figures:
      * 15-minute dispatch timeseries with rangeslider
      * 12-month coupled energy balance
      * Seasonal 24-hour diurnal dispatch overlay
      * Sankey energy flow diagram
  - Financial avoided cost assessment (coupled with Tab 2 Contract, or deactivated-by-default manual rate).
"""

from typing import Optional, Dict, Any, Tuple
import streamlit as st
import pandas as pd
import numpy as np

from current_model.models.solar import SolarLocation, SolarPVConfig, SolarSimulationResult
from current_model.models.contract import Contract
from current_model.core.solar_engine import (
    simulate_solar_pv_generation,
    calculate_scenario_target_kwp,
    calculate_recommended_inverter_size
)
from current_model.core.financial_engine import compute_financial_bill
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
    create_seasonal_dispatch_daily_figure,
    create_energy_flow_sankey_figure
)


def render_solar_integration_view(key_prefix: str = "tab3_int") -> None:
    """
    Renders Sub-Tab 3.2: Solar PV & Facility Consumption Integration.
    """
    st.subheader("Solar PV & Facility Consumption Integration")
    st.caption(
        "Couples 15-minute physical Solar PV generation with your active facility load profile. "
        "Calculates direct self-consumption, surplus generation, residual grid import, and peak load shaving."
    )

    # 1. Active Load Discovery
    df_load, load_desc, p_col = find_active_load_data_in_session()

    # If no load is found, provide a friendly helper toolbar with sample loader
    if df_load is None or df_load.empty:
        st.info(
            "**No active consumption profile detected from Tab 1.**\n\n"
            "Configure a profile in **Tab 1: Consumption** (Synthetic Simulator or CSV Ingestion), "
            "or load a demo profile below to explore the solar-load coupling:"
        )
        col_demo1, col_demo2, _ = st.columns([3, 3, 4])
        with col_demo1:
            if st.button("Load 365-Day Industry Preset", key=f"{key_prefix}_load_demo_ind_btn"):
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

    # Status Banner: Active Consumption Foundation
    st.markdown(
        f"""
        <div style="background: rgba(30, 41, 59, 0.6); border: 1px solid rgba(51, 65, 85, 0.7); border-radius: 8px; padding: 12px 16px; margin-bottom: 12px;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <span style="font-size: 0.75rem; color: #94A3B8; text-transform: uppercase; letter-spacing: 0.05em;">Active Facility Load Foundation</span>
                    <div style="font-size: 1.05rem; font-weight: 600; color: #F8FAFC; margin-top: 2px;">{load_desc}</div>
                </div>
                <div style="text-align: right;">
                    <span style="font-size: 0.85rem; color: #38BDF8; font-weight: 600;">{load_summary['total_mwh']:,.2f} MWh/year</span>
                    <span style="font-size: 0.8rem; color: #64748B;"> | Peak: {load_summary['peak_kw']:,.1f} kW | {load_summary['data_points']:,} intervals</span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    # 2. Solar System Sizing & Target Net Coverage Bar
    st.markdown("##### 1. Solar Sizing & Target Net Coverage")

    # Inherit existing location from Tab 3.1 or Mendoza default
    loc_lat = st.session_state.get("app_tab3_loc_lat", -32.8908)
    loc_lon = st.session_state.get("app_tab3_loc_lon", -68.8272)
    loc_name = st.session_state.get("app_tab3_loc_name", "Mendoza, Argentina")
    loc_elev = st.session_state.get("app_tab3_loc_elev", 746.0)
    location = SolarLocation(name=loc_name, latitude=loc_lat, longitude=loc_lon, elevation_m=loc_elev)

    # Baseline specific yield estimate for sizing scenarios (~1,600 kWh/kWp for standard Mendoza benchmark)
    estimated_spec_yield = 1600.0

    state_cfg_key = f"{key_prefix}_config"
    parent_cfg = st.session_state.get("app_tab3_config") or st.session_state.get("tab3_solar_config")

    if state_cfg_key not in st.session_state:
        if parent_cfg is not None and getattr(parent_cfg, "module_count", 0) > 0:
            st.session_state[state_cfg_key] = SolarPVConfig(
                module_count=parent_cfg.module_count,
                module_power_wp=parent_cfg.module_power_wp,
                technology_preset=parent_cfg.technology_preset,
                module_technology=parent_cfg.module_technology,
                inverter_capacity_kw=parent_cfg.inverter_capacity_kw,
                tilt_deg=parent_cfg.tilt_deg,
                azimuth_deg=parent_cfg.azimuth_deg,
                weather_mode=getattr(parent_cfg, "weather_mode", "TMY")
            )
        else:
            # Default to ~60% net coverage sizing or baseline 600 modules
            load_kwh = load_summary.get("total_kwh", 0.0)
            if load_kwh > 0:
                target_kwp = calculate_scenario_target_kwp(load_kwh, estimated_spec_yield, 60.0)
            else:
                target_kwp = 270.0
            inv_kw = calculate_recommended_inverter_size(target_kwp)
            mod_count = max(1, int(round((target_kwp * 1000.0) / 450.0)))
            st.session_state[state_cfg_key] = SolarPVConfig(
                module_count=mod_count,
                module_power_wp=450.0,
                technology_preset="TOPCon",
                module_technology="TOPCon (450 Wp)",
                inverter_capacity_kw=inv_kw,
                tilt_deg=28.0,
                azimuth_deg=0.0
            )

    curr_cfg: SolarPVConfig = st.session_state[state_cfg_key]
    if not hasattr(curr_cfg, "module_count") or curr_cfg.module_count <= 0:
        curr_cfg.module_count = 600
        curr_cfg.module_power_wp = 450.0
        curr_cfg.dc_capacity_kwp = 270.0
        curr_cfg.inverter_capacity_kw = 230.0

    # Quick Sizing Preset Buttons (40%, 60%, 80%, 100% Net Coverage)
    sc_col1, sc_col2, sc_col3, sc_col4, sc_sync = st.columns([2, 2, 2, 2, 3])

    with sc_col1:
        if st.button("40% Coverage", key=f"{key_prefix}_sc40_btn", help="Size system to generate 40% of annual electricity consumption (high self-consumption)."):
            t_kwp = calculate_scenario_target_kwp(load_summary["total_kwh"], estimated_spec_yield, 40.0)
            curr_cfg.module_power_wp = 450.0
            curr_cfg.module_count = max(1, int(round((t_kwp * 1000.0) / 450.0)))
            curr_cfg.dc_capacity_kwp = round(curr_cfg.module_count * 0.45, 1)
            curr_cfg.inverter_capacity_kw = calculate_recommended_inverter_size(curr_cfg.dc_capacity_kwp)
            curr_cfg.sizing_scenario = "40%"
            st.rerun()

    with sc_col2:
        if st.button("60% Coverage", key=f"{key_prefix}_sc60_btn", help="Size system to generate 60% of annual electricity consumption (balanced commercial standard)."):
            t_kwp = calculate_scenario_target_kwp(load_summary["total_kwh"], estimated_spec_yield, 60.0)
            curr_cfg.module_power_wp = 450.0
            curr_cfg.module_count = max(1, int(round((t_kwp * 1000.0) / 450.0)))
            curr_cfg.dc_capacity_kwp = round(curr_cfg.module_count * 0.45, 1)
            curr_cfg.inverter_capacity_kw = calculate_recommended_inverter_size(curr_cfg.dc_capacity_kwp)
            curr_cfg.sizing_scenario = "60%"
            st.rerun()

    with sc_col3:
        if st.button("80% Coverage", key=f"{key_prefix}_sc80_btn", help="Size system to generate 80% of annual electricity consumption (high autarky)."):
            t_kwp = calculate_scenario_target_kwp(load_summary["total_kwh"], estimated_spec_yield, 80.0)
            curr_cfg.module_power_wp = 450.0
            curr_cfg.module_count = max(1, int(round((t_kwp * 1000.0) / 450.0)))
            curr_cfg.dc_capacity_kwp = round(curr_cfg.module_count * 0.45, 1)
            curr_cfg.inverter_capacity_kw = calculate_recommended_inverter_size(curr_cfg.dc_capacity_kwp)
            curr_cfg.sizing_scenario = "80%"
            st.rerun()

    with sc_col4:
        if st.button("100% Net Zero", key=f"{key_prefix}_sc100_btn", help="Size system to match 100% of annual energy demand on an annual net basis."):
            t_kwp = calculate_scenario_target_kwp(load_summary["total_kwh"], estimated_spec_yield, 100.0)
            curr_cfg.module_power_wp = 450.0
            curr_cfg.module_count = max(1, int(round((t_kwp * 1000.0) / 450.0)))
            curr_cfg.dc_capacity_kwp = round(curr_cfg.module_count * 0.45, 1)
            curr_cfg.inverter_capacity_kw = calculate_recommended_inverter_size(curr_cfg.dc_capacity_kwp)
            curr_cfg.sizing_scenario = "100%"
            st.rerun()

    with sc_sync:
        if parent_cfg is not None:
            if st.button("Sync with Sub-Tab 3.1", icon=":material/sync:", key=f"{key_prefix}_sync_btn", help="Import the active PV installation parameters currently configured in Sub-Tab 3.1."):
                curr_cfg.module_count = parent_cfg.module_count
                curr_cfg.module_power_wp = parent_cfg.module_power_wp
                curr_cfg.dc_capacity_kwp = parent_cfg.dc_capacity_kwp
                curr_cfg.inverter_capacity_kw = parent_cfg.inverter_capacity_kw
                curr_cfg.technology_preset = parent_cfg.technology_preset
                curr_cfg.tilt_deg = parent_cfg.tilt_deg
                curr_cfg.azimuth_deg = parent_cfg.azimuth_deg
                st.rerun()

    # Sizing Parameter Inputs
    with st.expander("Sizing & Installation Parameters", icon=":material/tune:", expanded=True):
        p_col1, p_col2, p_col3, p_col4 = st.columns(4)

        with p_col1:
            init_mod_count = max(1, min(20000, int(getattr(curr_cfg, "module_count", 600) or 600)))
            inp_mod_count = st.number_input(
                "Module Count (Panels):",
                min_value=1,
                max_value=20000,
                value=init_mod_count,
                step=10,
                key=f"{key_prefix}_mod_count_inp"
            )
            curr_cfg.module_count = inp_mod_count

        with p_col2:
            init_wp = float(getattr(curr_cfg, "module_power_wp", 450.0) or 450.0)
            init_wp = max(200.0, min(800.0, init_wp))
            inp_mod_wp = st.number_input(
                "Module Wattage (Wp):",
                min_value=200.0,
                max_value=800.0,
                value=init_wp,
                step=10.0,
                key=f"{key_prefix}_mod_wp_inp"
            )
            curr_cfg.module_power_wp = inp_mod_wp
            curr_cfg.dc_capacity_kwp = round((curr_cfg.module_count * curr_cfg.module_power_wp) / 1000.0, 1)

        with p_col3:
            rec_inv = calculate_recommended_inverter_size(curr_cfg.dc_capacity_kwp)
            init_inv = float(getattr(curr_cfg, "inverter_capacity_kw", 0.0) or 0.0)
            if init_inv < 1.0:
                init_inv = rec_inv
            init_inv = max(1.0, min(15000.0, init_inv))
            inp_inv_kw = st.number_input(
                "Inverter Rating (kW AC):",
                min_value=1.0,
                max_value=15000.0,
                value=init_inv,
                step=10.0,
                key=f"{key_prefix}_inv_kw_inp",
                help=f"Standard DC/AC oversizing recommendation: {rec_inv:.1f} kW AC."
            )
            curr_cfg.inverter_capacity_kw = inp_inv_kw

        with p_col4:
            st.metric("DC System Capacity", f"{curr_cfg.dc_capacity_kwp:,.1f} kWp", f"Area: {curr_cfg.required_area_m2:,.0f} m²")

    # 3. Physical Dispatch Simulation Calculation
    state_res_key = f"{key_prefix}_sim_result"
    sim_res: Optional[SolarSimulationResult] = st.session_state.get(state_res_key)

    need_calc = (sim_res is None or
                 sim_res.config.module_count != curr_cfg.module_count or
                 sim_res.config.module_power_wp != curr_cfg.module_power_wp or
                 sim_res.config.inverter_capacity_kw != curr_cfg.inverter_capacity_kw)

    if need_calc:
        with st.spinner("Calculating 15-minute electrical solar-load dispatch..."):
            try:
                sim_res = simulate_solar_pv_generation(
                    config=curr_cfg,
                    location=location,
                    load_df=df_load
                )
                st.session_state[state_res_key] = sim_res
            except Exception as err:
                st.error(f"Coupled Simulation Error: {err}")
                return

    kpis = sim_res.kpis
    df_ts = sim_res.df_timeseries

    # Save to global session state for downstream use
    st.session_state["solar_dispatch_result"] = sim_res
    st.session_state["solar_kw_15min"] = df_ts["P_AC_kW"]

    st.divider()

    # 4. Integrated Electrical Dispatch & Autarky KPIs
    st.markdown("##### 2. Coupled Dispatch Performance Metrics")

    # Peak Shaving Analysis
    p_orig_max = float(df_ts["P_Load_kW"].max()) if "P_Load_kW" in df_ts.columns else 0.0
    p_res_max = float(df_ts["P_Residual_kW"].max()) if "P_Residual_kW" in df_ts.columns else 0.0
    peak_shaved_kw = max(0.0, p_orig_max - p_res_max)
    peak_shaved_pct = (peak_shaved_kw / p_orig_max * 100.0) if p_orig_max > 0 else 0.0

    k1, k2, k3, k4 = st.columns(4)

    with k1:
        render_kpi_card(
            "Self-Consumption Rate",
            f"{kpis.self_consumption_rate_pct:.1f} %",
            f"{kpis.direct_consumption_kwh / 1000.0:,.1f} MWh of {kpis.annual_energy_mwh:,.1f} MWh used on-site",
            status="ok"
        )
    with k2:
        render_kpi_card(
            "Autarky / Solar Fraction",
            f"{kpis.solar_fraction_autarky_pct:.1f} %",
            f"Covers {kpis.direct_consumption_kwh / 1000.0:,.1f} MWh of {kpis.total_load_kwh / 1000.0:,.1f} MWh facility demand",
            status="ok"
        )
    with k3:
        render_kpi_card(
            "PV Surplus / Grid Export",
            f"{kpis.surplus_generation_kwh / 1000.0:,.1f} MWh",
            f"{(kpis.surplus_generation_kwh / max(1.0, kpis.annual_energy_kwh) * 100.0):.1f}% of generation available for feed-in / BESS",
            status="default"
        )
    with k4:
        render_kpi_card(
            "Residual Grid Import",
            f"{kpis.residual_load_kwh / 1000.0:,.1f} MWh",
            f"Remaining facility demand purchased from grid",
            status="default"
        )

    # Secondary row of metrics
    s1, s2, s3, s4 = st.columns(4)
    with s1:
        render_kpi_card(
            "Peak Demand Reduction",
            f"-{peak_shaved_kw:.1f} kW",
            f"Original: {p_orig_max:.1f} kW ➔ Residual: {p_res_max:.1f} kW (-{peak_shaved_pct:.1f}%)",
            status="ok" if peak_shaved_kw > 0.1 else "default"
        )
    with s2:
        net_cov_pct = (kpis.annual_energy_kwh / max(1.0, kpis.total_load_kwh) * 100.0)
        render_kpi_card(
            "Annual Net Energy Coverage",
            f"{net_cov_pct:.1f} %",
            f"Generation: {kpis.annual_energy_mwh:,.1f} MWh vs. Demand: {kpis.total_load_kwh/1000.0:,.1f} MWh"
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

    # 5. Interactive Dispatch Visualizations
    st.markdown("##### 3. Visual Dispatch Analysis")

    chart_tab1, chart_tab2, chart_tab3, chart_tab4 = st.tabs([
        "15-Minute Dispatch Timeseries",
        "Monthly Energy Balance",
        "Seasonal Diurnal Profiles",
        "Energy Flow (Sankey)"
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
        fig_seasonal = create_seasonal_dispatch_daily_figure(df=df_ts)
        st.plotly_chart(fig_seasonal, use_container_width=True)

    with chart_tab4:
        fig_sankey = create_energy_flow_sankey_figure(kpis=kpis)
        st.plotly_chart(fig_sankey, use_container_width=True)

    st.divider()

    # 6. Economic & Avoided Cost Assessment
    st.markdown("##### 4. Financial & Tariff Savings Assessment")

    active_contract: Optional[Contract] = find_active_contract_in_session()

    if active_contract is not None:
        # Full contract evaluation
        st.caption(f"Linked Electricity Contract: **{active_contract.name}** ({active_contract.currency})")
        try:
            curr = getattr(active_contract, "currency", "EUR")

            # 1. Baseline bill (Facility load before solar, aligned to the full simulation horizon)
            df_base = pd.DataFrame({
                "timestamp": df_ts["timestamp"],
                "Total_Demand_kW": df_ts["P_Load_kW"]
            })
            base_bill = compute_financial_bill(load_data=df_base, contract=active_contract)

            # 2. Solar bill (Residual load after direct solar self-consumption, identical horizon)
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

            # Comparison breakdown table
            with st.expander("Itemized Financial Comparison: Status Quo vs. With Solar PV", expanded=False):
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

            # 3. 15-Year Life-Cycle Economic Evaluation & Payback (If Solar CAPEX is configured)
            from current_model.core.solar_financial_engine import compute_solar_financial_metrics
            from current_model.ui.tab3_solar.charts import (
                create_solar_cashflow_payback_figure,
                create_cumulative_cost_comparison_figure,
                create_annual_running_costs_comparison_figure
            )

            solar_fin_cfg = st.session_state.get("solar_financial_config") or st.session_state.get("app_tab3_fin_config")

            if solar_fin_cfg and solar_fin_cfg.is_enabled:
                export_rev = kpis.surplus_generation_kwh * (solar_fin_cfg.feed_in_tariff_per_kwh or 0.06)
                coupled_fin_metrics = compute_solar_financial_metrics(
                    config=config,
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

                    # 15-Year Life-Cycle Comparison Diagrams (3 Interactive Tabs)
                    diag_tab1, diag_tab2, diag_tab3 = st.tabs([
                        "📈 Cumulative Total Cost & Amortisation (Status Quo vs. Mit PV)",
                        "📊 Annual Running Costs & Operating Expenses",
                        "💰 Net Cash Flow & Payback Curve"
                    ])

                    with diag_tab1:
                        fig_cum = create_cumulative_cost_comparison_figure(coupled_fin_metrics, currency=curr)
                        st.plotly_chart(fig_cum, use_container_width=True)

                    with diag_tab2:
                        fig_running = create_annual_running_costs_comparison_figure(coupled_fin_metrics, currency=curr)
                        st.plotly_chart(fig_running, use_container_width=True)

                    with diag_tab3:
                        fig_cf = create_solar_cashflow_payback_figure(coupled_fin_metrics, currency=curr)
                        st.plotly_chart(fig_cf, use_container_width=True)

                    # 15-Year Table (Matching GRID vs GRID+SOLAR Excel Sheet)
                    with st.expander("15-Year Life-Cycle Year-by-Year Table (Cashflow, Degradation, OPEX, Savings)", icon=":material/view_timeline:", expanded=False):
                        detail_rows = []
                        for row in coupled_fin_metrics.cash_flow_table:
                            detail_rows.append({
                                "Year": f"Year {row['year']}",
                                "Aging / Degradation": f"{row['aging_factor'] * 100.0:.1f} %",
                                "PV Gen (MWh)": f"{row['generation_mwh']:,.2f}",
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
            st.warning(f"Unable to calculate financial savings against Tab 2 contract: {err}")

    else:
        # User requirement: "the unit rate field in case of lack of contract is deactivated by default"
        st.info("No active electricity contract configured in Tab 2.")

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
            st.caption("Tip: You can configure an electricity contract in Tab 2 for exact Time-of-Use and capacity billing, or toggle on the simplified rate estimate above.")
