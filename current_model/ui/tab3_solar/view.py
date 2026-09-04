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
        "3.1 Standalone Solar PV Generation",
        "3.2 Solar & Consumption Integration"
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

    config, submitted = render_solar_config_form(
        location=location,
        current_config=current_cfg,
        key_prefix=f"{key_prefix}_form"
    )

    st.session_state[state_cfg_key] = config

    # 3. Physical Simulation Execution & Caching
    auto_trigger = st.session_state.pop(f"{key_prefix}_trigger_calc", False)
    cached_res = st.session_state.get(state_res_key)
    if cached_res is not None:
        if not hasattr(cached_res, "kpis") or not hasattr(cached_res.kpis, "multi_year_risk_summary"):
            if state_res_key in st.session_state:
                del st.session_state[state_res_key]
            cached_res = None

    config_changed = False
    if cached_res is not None and hasattr(cached_res, "config"):
        prev_cfg = cached_res.config
        if (getattr(prev_cfg, "module_count", None) != config.module_count or
            getattr(prev_cfg, "module_power_wp", None) != config.module_power_wp or
            getattr(prev_cfg, "tilt_deg", None) != config.tilt_deg or
            getattr(prev_cfg, "azimuth_deg", None) != config.azimuth_deg or
            getattr(prev_cfg, "inverter_capacity_kw", None) != config.inverter_capacity_kw or
            getattr(prev_cfg, "temp_coefficient_pct_c", None) != config.temp_coefficient_pct_c or
            getattr(prev_cfg, "weather_mode", None) != getattr(config, "weather_mode", None) or
            getattr(prev_cfg, "selected_weather_year", None) != getattr(config, "selected_weather_year", None)):
            config_changed = True

    # Only run simulation on explicit calculate button click or loaded example trigger
    valid_sizing = config.module_count > 0 and (config.dc_capacity_kwp or 0) > 0
    need_simulation = (submitted or auto_trigger) and valid_sizing

    if need_simulation:
        with st.spinner("Calculating 15-minute physical solar PV generation & technology comparison..."):
            try:
                sim_result: SolarSimulationResult = simulate_solar_pv_generation(
                    config=config,
                    location=location
                )
                st.session_state[state_res_key] = sim_result
            except Exception as err:
                st.error(f"Solar Simulation Error: {err}")
                return

    # If no simulation result exists yet, show clean empty-state guidance
    if state_res_key not in st.session_state:
        st.divider()
        st.info(
            "**No solar simulation calculated yet.**\n\n"
            "Enter your installation parameters above and click **'Calculate Solar PV Generation & Multi-Technology Comparison'**, "
            "or click **'Load Example Case (Mendoza Benchmark)'** to load the preconfigured reference scenario."
        )
        return

    if config_changed:
        st.warning("Solar configuration was changed above. Click **'Calculate Solar PV Generation & Multi-Technology Comparison'** to refresh the results.")

    sim_res: SolarSimulationResult = st.session_state[state_res_key]
    kpis = sim_res.kpis
    df_ts = sim_res.df_timeseries

    # Save to global session state for downstream use
    st.session_state["solar_kw_15min"] = df_ts["P_AC_kW"]
    st.session_state["solar_kpis"] = kpis
    st.session_state["solar_config"] = config

    st.divider()

    # Active Weather Data Foundation Status
    weather_source = getattr(kpis, "weather_data_source", "PVGIS-ERA5 Typical Meteorological Year (TMY)")
    st.info(f"Active Weather Data Foundation: **{weather_source}** | 35,040 Time Steps (15-Minute Grid)")

    # 4. Core Electrical Generation KPIs & Area Metrics
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

    # Multi-Year P50 / P90 Risk Section (if evaluated)
    risk = getattr(kpis, "multi_year_risk_summary", None)
    if risk:
        st.subheader("Climatological Multi-Year Risk Assessment (10-Year Horizon: 2015 - 2024)")
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

        with st.expander("Historical Multi-Year Generation Breakdown (2015 - 2024)", expanded=False):
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
    with st.expander("Itemized Monthly Yield Table & Statistics (Year Sheet Data)", expanded=False):
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
    st.subheader("8. Multi-Technology Production Analysis (PERC vs. TOPCon vs. Backcontact)")
    st.caption(
        f"Direct performance comparison for **{config.module_count:,} identical module positions** "
        f"across a 15-year operational lifetime (accounting for cell wattage, temperature coefficient, and 2-stage degradation):"
    )

    if sim_res.technology_comparison:
        # 1. Comparative Chart
        fig_tech = create_technology_comparison_figure(sim_res.technology_comparison)
        st.plotly_chart(fig_tech, use_container_width=True)

        # 2. Comparative Data Table (Matching Excel Bild 1 Output Panel)
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

