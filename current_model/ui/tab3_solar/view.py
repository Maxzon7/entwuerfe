"""
========================================================================================
Tab 3 Solar PV Simulator View (current_model/ui/tab3_solar/view.py)
========================================================================================

Description:
------------
Pure Solar PV Generation Simulator (Excel-Aligned):
  - High-precision 15-minute resolution Open-Meteo physical simulation
  - Module quantity & wattage sizing (N_panels x Wp = DC kWp)
  - Physical area requirements calculator (Net m² & Gross required m²)
  - Multi-technology comparative production matrix (PERC vs TOPCon vs Backcontact across 15 years)
  - Technical technology explanations & educational glossary
  - Core generation KPIs, 15-minute interactive timeseries, 12-month bar chart, and loss waterfall
"""

from typing import Optional
import streamlit as st
import pandas as pd

from current_model.models.solar import SolarLocation, SolarPVConfig, SolarSimulationResult
from current_model.core.solar_engine import simulate_solar_pv_generation
from current_model.ui.common.cards import render_kpi_card
from current_model.ui.tab3_solar.forms import render_solar_location_section, render_solar_config_form
from current_model.ui.tab3_solar.charts import (
    create_solar_timeseries_figure,
    create_solar_monthly_bar_figure,
    create_solar_seasonal_daily_figure,
    create_solar_loss_waterfall_figure,
    create_technology_comparison_figure
)
from current_model.ui.tab3_solar.integration_view import render_solar_integration_view


def render_tab3_solar(key_prefix: str = "app_tab3") -> None:
    """
    Main entry point for Tab 3: Solar PV Generation & Load Integration.
    Structured into Sub-Tabs:
      - 3.1 Standalone Solar PV Generation (Status Quo)
      - 3.2 Solar & Consumption Integration
    """
    subtab_standalone, subtab_integration = st.tabs([
        ":material/solar_power: 3.1 Standalone Solar PV Generation",
        ":material/energy_savings_leaf: 3.2 Solar & Consumption Integration"
    ])

    with subtab_standalone:
        render_tab3_1_standalone(key_prefix=key_prefix)

    with subtab_integration:
        render_solar_integration_view(key_prefix=f"{key_prefix}_int")


def render_tab3_1_standalone(key_prefix: str = "tab3_solar") -> None:
    """
    Renders the Excel-aligned Sub-Tab 3.1 Pure Standalone Solar PV Generation Simulator view.
    """
    st.markdown("### Photovoltaic Solar Generation Simulator")
    st.caption(
        "Calculate exact electrical solar power (kW) and energy yield (kWh / MWh) based on "
        "15-minute radiation data, panel count × wattage, cell technologies, mounting area, and inverter efficiency."
    )

    state_cfg_key = f"{key_prefix}_config"
    state_res_key = f"{key_prefix}_sim_result"

    # Action Toolbar: Load Example Case / Clear Form
    act_col1, act_col2, _ = st.columns([3.5, 2.5, 6])
    with act_col1:
        if st.button(
            "Load Example Case (Mendoza Benchmark)",
            icon=":material/play_circle:",
            key=f"{key_prefix}_load_example_btn",
            help="Loads the DRACBV reference benchmark case (Mendoza, Argentina with 1,548 TOPCon modules à 450 Wp = 696.6 kWp)."
        ):
            st.session_state[f"{key_prefix}_loc_lat"] = -32.8908
            st.session_state[f"{key_prefix}_loc_lon"] = -68.8272
            st.session_state[f"{key_prefix}_loc_name"] = "Mendoza, Argentina"
            st.session_state[f"{key_prefix}_loc_elev"] = 746.0
            st.session_state[state_cfg_key] = SolarPVConfig(
                module_count=1548,
                module_power_wp=450.0,
                technology_preset="TOPCon",
                module_technology="TOPCon (450 Wp - N-Type Modern Standard)",
                inverter_capacity_kw=590.0,
                tilt_deg=28.0,
                azimuth_deg=0.0,
                weather_mode="TMY"
            )
            for k in [
                f"{key_prefix}_form_mod_count",
                f"{key_prefix}_form_tech_choice",
                f"{key_prefix}_form_inv_kw",
                f"{key_prefix}_form_tilt",
                f"{key_prefix}_form_azimuth",
                f"{key_prefix}_form_weather_mode_select",
                f"{key_prefix}_form_hist_year_select"
            ]:
                if k in st.session_state:
                    del st.session_state[k]

            st.session_state[f"{key_prefix}_trigger_calc"] = True
            st.rerun()

    with act_col2:
        if st.button(
            "Reset / Clear Form",
            icon=":material/restart_alt:",
            key=f"{key_prefix}_reset_btn",
            help="Resets all inputs back to empty state and clears simulation results."
        ):
            for k in [
                state_cfg_key,
                state_res_key,
                "solar_kw_15min",
                "solar_kpis",
                "solar_config",
                f"{key_prefix}_trigger_calc"
            ]:
                if k in st.session_state:
                    del st.session_state[k]
            for k in [
                f"{key_prefix}_form_mod_count",
                f"{key_prefix}_form_tech_choice",
                f"{key_prefix}_form_inv_kw",
                f"{key_prefix}_form_tilt",
                f"{key_prefix}_form_azimuth",
                f"{key_prefix}_form_weather_mode_select",
                f"{key_prefix}_form_hist_year_select"
            ]:
                if k in st.session_state:
                    del st.session_state[k]
            st.rerun()

    # 1. Location Section (Search, Map, Presets, Coordinates)
    location: SolarLocation = render_solar_location_section(key_prefix=f"{key_prefix}_loc")

    # 2. Technical PV Configuration Form (Input Panel)
    current_cfg: Optional[SolarPVConfig] = st.session_state.get(state_cfg_key)
    if current_cfg is not None and (not hasattr(current_cfg, "technology_preset") or not hasattr(current_cfg, "weather_mode")):
        current_cfg = None
        if state_res_key in st.session_state:
            del st.session_state[state_res_key]

    config, fin_config, submitted = render_solar_config_form(
        location=location,
        current_config=current_cfg,
        key_prefix=f"{key_prefix}_form"
    )

    st.session_state[state_cfg_key] = config
    st.session_state[f"{key_prefix}_fin_config"] = fin_config

    # 3. Physical Simulation Execution & Caching
    auto_trigger = st.session_state.pop(f"{key_prefix}_trigger_calc", False)
    cached_res = st.session_state.get(state_res_key)
    if cached_res is not None:
        if not hasattr(cached_res, "kpis") or not hasattr(cached_res.kpis, "multi_year_risk_summary"):
            if state_res_key in st.session_state:
                del st.session_state[state_res_key]
            cached_res = None

    physical_config_changed = False
    financial_config_changed = False
    if cached_res is not None and hasattr(cached_res, "config"):
        prev_cfg = cached_res.config
        prev_fin = getattr(cached_res, "financial_config", None)
        if (getattr(prev_cfg, "module_count", None) != config.module_count or
            getattr(prev_cfg, "module_power_wp", None) != config.module_power_wp or
            getattr(prev_cfg, "tilt_deg", None) != config.tilt_deg or
            getattr(prev_cfg, "azimuth_deg", None) != config.azimuth_deg or
            getattr(prev_cfg, "inverter_capacity_kw", None) != config.inverter_capacity_kw or
            getattr(prev_cfg, "temp_coefficient_pct_c", None) != config.temp_coefficient_pct_c or
            getattr(prev_cfg, "weather_mode", None) != getattr(config, "weather_mode", None) or
            getattr(prev_cfg, "selected_weather_year", None) != getattr(config, "selected_weather_year", None) or
            getattr(getattr(cached_res, "location", None), "latitude", None) != location.latitude or
            getattr(getattr(cached_res, "location", None), "longitude", None) != location.longitude):
            physical_config_changed = True

        if (getattr(prev_fin, "is_enabled", False) != getattr(fin_config, "is_enabled", False) or
            getattr(prev_fin, "cost_modules_per_wp", None) != getattr(fin_config, "cost_modules_per_wp", None) or
            getattr(prev_fin, "cost_inverter_per_w", None) != getattr(fin_config, "cost_inverter_per_w", None) or
            getattr(prev_fin, "cost_substructure_per_wp", None) != getattr(fin_config, "cost_substructure_per_wp", None) or
            getattr(prev_fin, "cost_installation_per_wp", None) != getattr(fin_config, "cost_installation_per_wp", None) or
            getattr(prev_fin, "fixed_switchgear_cost", None) != getattr(fin_config, "fixed_switchgear_cost", None) or
            getattr(prev_fin, "fixed_travel_fee", None) != getattr(fin_config, "fixed_travel_fee", None) or
            getattr(prev_fin, "annual_opex_pct", None) != getattr(fin_config, "annual_opex_pct", None) or
            getattr(prev_fin, "discount_rate_pct", None) != getattr(fin_config, "discount_rate_pct", None) or
            getattr(prev_fin, "feed_in_tariff_per_kwh", None) != getattr(fin_config, "feed_in_tariff_per_kwh", None)):
            financial_config_changed = True

    valid_sizing = config.module_count > 0 and (config.dc_capacity_kwp or 0) > 0
    from current_model.core.solar_financial_engine import compute_solar_financial_metrics
    from current_model.ui.tab3_solar.charts import create_solar_capex_donut_figure, create_solar_cashflow_payback_figure

    if submitted and not valid_sizing:
        st.error("⚠️ Sizing Required: Please enter a module count greater than 0 in Section 2 above to calculate solar generation.")

    need_full_simulation = (submitted or auto_trigger) and valid_sizing and (physical_config_changed or cached_res is None)
    need_financial_recalc = (submitted or auto_trigger or financial_config_changed) and valid_sizing and not need_full_simulation and cached_res is not None

    if need_full_simulation:
        with st.spinner("Calculating 15-minute physical solar PV generation & technology comparison..."):
            try:
                sim_result: SolarSimulationResult = simulate_solar_pv_generation(
                    config=config,
                    location=location
                )

                # Compute financial metrics if enabled
                if fin_config and fin_config.is_enabled:
                    fin_metrics = compute_solar_financial_metrics(
                        config=config,
                        fin_config=fin_config,
                        annual_generation_kwh=sim_result.kpis.annual_energy_kwh,
                        multi_year_yields=sim_result.multi_year_yields
                    )
                    sim_result.financial_config = fin_config
                    sim_result.financial_metrics = fin_metrics
                else:
                    sim_result.financial_config = fin_config
                    sim_result.financial_metrics = None

                st.session_state[state_res_key] = sim_result
                physical_config_changed = False
                financial_config_changed = False
                cached_res = sim_result
            except Exception as err:
                st.error(f"Solar Simulation Error: {err}")
                return

    elif need_financial_recalc:
        if fin_config and fin_config.is_enabled:
            fin_metrics = compute_solar_financial_metrics(
                config=config,
                fin_config=fin_config,
                annual_generation_kwh=cached_res.kpis.annual_energy_kwh,
                multi_year_yields=cached_res.multi_year_yields
            )
            cached_res.financial_config = fin_config
            cached_res.financial_metrics = fin_metrics
        else:
            cached_res.financial_config = fin_config
            cached_res.financial_metrics = None
        st.session_state[state_res_key] = cached_res
        financial_config_changed = False

    # If no simulation result exists yet, show clean empty-state guidance
    if state_res_key not in st.session_state:
        st.divider()
        st.info(
            "**No solar simulation calculated yet.**\n\n"
            "Enter your installation parameters above and click **'Calculate Solar PV Generation & Multi-Technology Comparison'**, "
            "or click **'Load Example Case (Mendoza Benchmark)'** to load the preconfigured reference scenario."
        )
        return

    if physical_config_changed and valid_sizing:
        st.warning("Solar physical configuration was changed above. Click **'Calculate Solar PV Generation & Multi-Technology Comparison'** to refresh the results.")

    sim_res: SolarSimulationResult = st.session_state[state_res_key]

    # Dynamically evaluate financial metrics if user toggled on financials on existing simulation
    if fin_config and fin_config.is_enabled and (sim_res.financial_metrics is None or not sim_res.financial_metrics.is_configured):
        sim_res.financial_config = fin_config
        sim_res.financial_metrics = compute_solar_financial_metrics(
            config=config,
            fin_config=fin_config,
            annual_generation_kwh=sim_res.kpis.annual_energy_kwh,
            multi_year_yields=sim_res.multi_year_yields
        )
    elif fin_config and not fin_config.is_enabled:
        sim_res.financial_metrics = None

    kpis = sim_res.kpis
    df_ts = sim_res.df_timeseries

    # Save to global session state for downstream use
    st.session_state["solar_kw_15min"] = df_ts["P_AC_kW"]
    st.session_state["solar_kpis"] = kpis
    st.session_state["solar_config"] = config
    st.session_state["solar_financial_config"] = fin_config
    st.session_state["solar_financial_metrics"] = sim_res.financial_metrics

    st.divider()

    # --------------------------------------------------------------------------
    # View Filter Toolbar (Technical Electricity Generation vs. Financial Costs)
    # --------------------------------------------------------------------------
    col_v1, col_v2 = st.columns([6.5, 3.5])
    with col_v1:
        view_options = [
            "⚡ Electricity Generation & Technical Yield",
            "💶 Solar Financial & Turn-Key Investment Costs"
        ]
        active_views = st.pills(
            "Select Display Views (Click to toggle on / off):",
            options=view_options,
            default=view_options,
            selection_mode="multi",
            key=f"{key_prefix}_active_views"
        )
    with col_v2:
        st.write("")
        st.caption("Toggle views with a single click: Show pure technical generation, pure financial investment costs, or both side-by-side.")

    show_technical = "⚡ Electricity Generation & Technical Yield" in (active_views or [])
    show_financial = "💶 Solar Financial & Turn-Key Investment Costs" in (active_views or [])

    if not show_technical and not show_financial:
        st.info("💡 Both display views are currently hidden. Click on **'⚡ Electricity Generation & Technical Yield'** or **'💶 Solar Financial & Turn-Key Investment Costs'** above to display the analysis.")
        return

    # ==========================================================================
    # SECTION A: TECHNICAL SOLAR PV GENERATION & ELECTRICAL METRICS
    # ==========================================================================
    if show_technical:
        # Active Weather Data Foundation Status
        weather_source = getattr(kpis, "weather_data_source", "PVGIS-ERA5 Typical Meteorological Year (TMY)")
        st.info(f"Active Weather Data Foundation: **{weather_source}** | 35,040 Time Steps (15-Minute Grid)")

        # 3. Core Electrical Generation KPIs & Area Metrics
        st.subheader("3. Annual Electricity Generation & System Metrics")
        k1, k2, k3, k4 = st.columns(4)

        with k1:
            render_kpi_card(
                "Total Annual Yield",
                f"{kpis.annual_energy_mwh:,.2f} MWh",
                f"{kpis.annual_energy_kwh:,.0f} kWh total AC generation"
            )
        with k2:
            render_kpi_card(
                "Specific Yield",
                f"{kpis.specific_yield_kwh_per_kwp:,.1f} kWh/kWp",
                f"Full Load Hours: {kpis.full_load_hours:,.0f} h/a"
            )
        with k3:
            render_kpi_card(
                "Generator Sizing",
                f"{config.dc_capacity_kwp:,.1f} kWp",
                f"{config.module_count:,} Panels à {config.module_power_wp:.0f} Wp"
            )
        with k4:
            render_kpi_card(
                "Required Area",
                f"{config.required_area_m2:,.0f} m²",
                f"Net Panel Area: {config.gross_panel_area_m2:,.0f} m² (Factor: {config.area_factor:.1f})"
            )

        # 4. Interactive 15-Minute Generation Timeseries Plot
        st.subheader("4. Solar Generation Profile Timeseries (15-Minute Resolution)")
        fig_ts = create_solar_timeseries_figure(
            df=df_ts,
            dc_capacity_kwp=config.dc_capacity_kwp,
            inverter_capacity_kw=config.inverter_capacity_kw
        )
        st.plotly_chart(fig_ts, use_container_width=True)

        # 5. Monthly Yields & Seasonal Profiles (Year Sheet)
        st.subheader("5. Monthly Energy Production & Seasonal Profiles (Year Sheet)")
        col_m, col_s = st.columns(2)

        with col_m:
            fig_monthly = create_solar_monthly_bar_figure(
                monthly_yields=sim_res.monthly_yields,
                dc_capacity_kwp=config.dc_capacity_kwp
            )
            st.plotly_chart(fig_monthly, use_container_width=True)

        with col_s:
            fig_seasonal = create_solar_seasonal_daily_figure(df=df_ts)
            st.plotly_chart(fig_seasonal, use_container_width=True)

        # 6. Loss Waterfall Analysis
        st.subheader("6. Physical Energy Loss Cascade (Waterfall Diagram)")
        st.caption("Detailed breakdown from raw available sunlight on module plane to net usable AC energy delivered to grid.")
        fig_loss = create_solar_loss_waterfall_figure(loss_breakdown=sim_res.loss_breakdown)
        st.plotly_chart(fig_loss, use_container_width=True)

        # 7. Itemized Monthly Yield Table (Matching Bild 4)
        with st.expander("Itemized Monthly Yield Table & Statistics (Year Sheet Data)", icon=":material/table_chart:", expanded=False):
            table_rows = []
            for m in sim_res.monthly_yields:
                table_rows.append({
                    "Month": m.month_name,
                    "Days": m.days_count,
                    "Energy (MWh)": f"{m.energy_mwh:,.3f}",
                    "Energy (kWh)": f"{m.energy_kwh:,.1f}",
                    "Specific Yield (kWh/kWp)": f"{m.specific_yield_kwh_kwp:.1f}",
                    "Avg Daily (kWh/d)": f"{m.avg_daily_kwh:,.1f}",
                    "Peak Power (kW)": f"{m.peak_power_kw:,.1f}",
                    "Capacity Factor (%)": f"{m.capacity_factor_pct:.1f} %"
                })
            st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)

        # 8. Multi-Technology Comparative Production Analysis (Output Panel)
        st.subheader("7. Multi-Technology Production Analysis (PERC vs. TOPCon vs. Backcontact)")
        st.caption(
            f"Direct performance comparison for **{config.module_count:,} identical module positions** "
            f"across a 15-year operational lifetime (accounting for cell wattage, temperature coefficient, and 2-stage degradation):"
        )

        if sim_res.technology_comparison:
            fig_tech = create_technology_comparison_figure(sim_res.technology_comparison)
            st.plotly_chart(fig_tech, use_container_width=True)

            tech_rows = []
            for t in sim_res.technology_comparison:
                gain_label = f"+{t.gain_pct_vs_perc:.1f} %" if t.gain_pct_vs_perc > 0 else "Baseline (0.0 %)"
                tech_rows.append({
                    "Technology": t.tech_name,
                    "Module Wattage": f"{t.module_power_wp:.0f} Wp",
                    "DC Peak (kWp)": f"{t.dc_capacity_kwp:,.1f} kWp",
                    "Temp. Coeff. (γ)": f"{t.temp_coeff_pct_c:.2f} %/°C",
                    "1st Year (kWh)": f"{t.year_1_kwh:,.0f} kWh",
                    "5th Year (kWh)": f"{t.year_5_kwh:,.0f} kWh",
                    "10th Year (kWh)": f"{t.year_10_kwh:,.0f} kWh",
                    "15th Year (kWh)": f"{t.year_15_kwh:,.0f} kWh",
                    "Yield Gain vs. PERC": gain_label
                })
            st.dataframe(pd.DataFrame(tech_rows), use_container_width=True, hide_index=True)

        # Multi-Year P50 / P90 Risk Section (if evaluated)
        risk = getattr(kpis, "multi_year_risk_summary", None)
        if risk:
            st.subheader("8. Climatological Multi-Year Risk Assessment (10-Year Horizon: 2015 - 2024)")
            r1, r2, r3, r4 = st.columns(4)
            with r1:
                render_kpi_card(
                    "P50 Expected Median",
                    f"{risk['p50_kwh'] / 1000.0:,.2f} MWh/a",
                    f"{risk['p50_kwh']:,.0f} kWh (50% exceedance baseline)"
                )
            with r2:
                render_kpi_card(
                    "P90 Debt Financing Limit",
                    f"{risk['p90_kwh'] / 1000.0:,.2f} MWh/a",
                    f"{risk['p90_kwh']:,.0f} kWh (90% exceedance bankable)"
                )
            with r3:
                render_kpi_card(
                    "P95 High Security Limit",
                    f"{risk['p95_kwh'] / 1000.0:,.2f} MWh/a",
                    f"{risk['p95_kwh']:,.0f} kWh (95% exceedance conservative)"
                )
            with r4:
                render_kpi_card(
                    "Historical Volatility Bandwidth",
                    f"{risk['volatility_pct']:.1f} %",
                    f"Min: {risk['min_kwh']/1000.0:,.1f} MWh | Max: {risk['max_kwh']/1000.0:,.1f} MWh"
                )

            with st.expander("Historical Multi-Year Generation Breakdown (2015 - 2024)", icon=":material/history:", expanded=False):
                y_rows = []
                for y_int, y_val in risk["yearly_breakdown"].items():
                    dev_pct = ((y_val - risk["mean_kwh"]) / max(1.0, risk["mean_kwh"])) * 100.0
                    sign_str = "+" if dev_pct > 0 else ""
                    y_rows.append({
                        "Year": y_int,
                        "Annual AC Generation (MWh)": f"{y_val / 1000.0:,.2f}",
                        "Annual AC Generation (kWh)": f"{y_val:,.0f}",
                        "Specific Yield (kWh/kWp)": f"{y_val / max(0.1, config.dc_capacity_kwp):,.1f}",
                        "Deviation from 10-Year Mean": f"{sign_str}{dev_pct:.1f} %"
                    })
                st.dataframe(pd.DataFrame(y_rows), use_container_width=True, hide_index=True)

    # ==========================================================================
    # SECTION B: PURE SOLAR FINANCIALS & TURN-KEY INVESTMENT COSTS
    # ==========================================================================
    if show_financial:
        st.subheader("Solar Turn-Key Investment Costs & CAPEX Breakdown")
        fin_m = sim_res.financial_metrics
        if fin_m and fin_m.is_configured and fin_m.total_capex > 0:
            f_curr = fin_m.currency
            st.caption(f"Turn-key solar plant investment breakdown (DRACBV Kosten-/Berechnungs-Dashboard) and standalone electricity generation costs (LCOE):")

            fk1, fk2, fk3, fk4 = st.columns(4)
            with fk1:
                render_kpi_card(
                    "Total Solar CAPEX",
                    f"{fin_m.total_capex:,.2f} {f_curr}",
                    f"Turn-key system investment",
                    status="ok"
                )
            with fk2:
                render_kpi_card(
                    "Specific Investment",
                    f"{fin_m.capex_per_kwp:,.2f} {f_curr}/kWp",
                    f"Per kWp installed DC capacity"
                )
            with fk3:
                render_kpi_card(
                    "Electricity Generation Cost (LCOE)",
                    f"{fin_m.lcoe_per_kwh:.4f} {f_curr}/kWh",
                    f"Levelized cost across 15-year horizon"
                )
            with fk4:
                render_kpi_card(
                    "Annual Maintenance / OPEX",
                    f"{fin_m.annual_opex_year1:,.2f} {f_curr}/a",
                    f"Year 1 O&M reserve ({fin_config.annual_opex_pct:.1f}% p.a.)"
                )

            # CAPEX Itemized Breakdown Table & Donut Chart
            col_c_tbl, col_c_pie = st.columns([6, 5])
            with col_c_tbl:
                st.markdown("##### Turn-Key Itemized Cost Table")
                capex_rows = [
                    {
                        "Component": "1. PV Solar Modules",
                        "Basis": f"{config.module_count:,} Modules ({config.dc_capacity_kwp * 1000.0:,.0f} Wp)",
                        "Unit Rate": f"{fin_config.cost_modules_per_wp:.2f} {f_curr}/Wp" if fin_config.cost_modules_per_wp else "-",
                        f"Total ({f_curr})": f"{fin_m.capex_modules:,.2f}",
                        "Share": f"{(fin_m.capex_modules / fin_m.total_capex * 100.0):.1f} %"
                    },
                    {
                        "Component": "2. Inverter(s)",
                        "Basis": f"{config.inverter_capacity_kw:,.1f} kW AC ({config.inverter_capacity_kw * 1000.0:,.0f} W)",
                        "Unit Rate": f"{fin_config.cost_inverter_per_w:.2f} {f_curr}/W AC" if fin_config.cost_inverter_per_w else "-",
                        f"Total ({f_curr})": f"{fin_m.capex_inverter:,.2f}",
                        "Share": f"{(fin_m.capex_inverter / fin_m.total_capex * 100.0):.1f} %"
                    },
                    {
                        "Component": "3. Substructure & Mounting (Maschinenbau)",
                        "Basis": f"{config.dc_capacity_kwp * 1000.0:,.0f} Wp DC",
                        "Unit Rate": f"{fin_config.cost_substructure_per_wp:.2f} {f_curr}/Wp" if fin_config.cost_substructure_per_wp else "-",
                        f"Total ({f_curr})": f"{fin_m.capex_substructure:,.2f}",
                        "Share": f"{(fin_m.capex_substructure / fin_m.total_capex * 100.0):.1f} %"
                    },
                    {
                        "Component": "4. Electrical Installation & Grid Connection",
                        "Basis": f"{config.dc_capacity_kwp * 1000.0:,.0f} Wp DC",
                        "Unit Rate": f"{fin_config.cost_installation_per_wp:.2f} {f_curr}/Wp" if fin_config.cost_installation_per_wp else "-",
                        f"Total ({f_curr})": f"{fin_m.capex_installation:,.2f}",
                        "Share": f"{(fin_m.capex_installation / fin_m.total_capex * 100.0):.1f} %"
                    },
                    {
                        "Component": "5. Switchgear Cabinet (Zählerschrank)",
                        "Basis": "Fixed Turn-Key Item",
                        "Unit Rate": f"{fin_config.fixed_switchgear_cost:,.2f} {f_curr}" if fin_config.fixed_switchgear_cost else "-",
                        f"Total ({f_curr})": f"{fin_config.fixed_switchgear_cost:,.2f}",
                        "Share": f"{(fin_config.fixed_switchgear_cost / fin_m.total_capex * 100.0):.1f} %"
                    },
                    {
                        "Component": "6. Mobilization Fee (Anfahrtsgebühr)",
                        "Basis": "Fixed Turn-Key Item",
                        "Unit Rate": f"{fin_config.fixed_travel_fee:,.2f} {f_curr}" if fin_config.fixed_travel_fee else "-",
                        f"Total ({f_curr})": f"{fin_config.fixed_travel_fee:,.2f}",
                        "Share": f"{(fin_config.fixed_travel_fee / fin_m.total_capex * 100.0):.1f} %"
                    }
                ]
                st.dataframe(pd.DataFrame(capex_rows), use_container_width=True, hide_index=True)

            with col_c_pie:
                fig_donut = create_solar_capex_donut_figure(fin_m, currency=f_curr)
                st.plotly_chart(fig_donut, use_container_width=True)

            st.caption("ℹ️ *Note: For comparative analysis showing how these solar costs offset your electricity bill compared to the Status Quo without solar, see Sub-Tab 3.2 (Solar & Consumption Integration).*")
        else:
            st.info(
                "💡 **Solar Financial Assessment is currently disabled.**\n\n"
                "To calculate and display turn-key CAPEX breakdown, specific investment per kWp, and LCOE (€/kWh), "
                "check **'Enable Solar Financial Assessment & Turn-Key CAPEX Calculation'** in Section 5 above."
            )

