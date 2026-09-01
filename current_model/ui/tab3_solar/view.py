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


def render_tab3_solar(key_prefix: str = "tab3_solar") -> None:
    """
    Renders the Excel-aligned Tab 3 Solar PV Generation Simulator view.
    """
    st.markdown("### ☀️ Photovoltaic Solar Generation Simulator")
    st.caption(
        "Calculate exact electrical solar power (kW) and energy yield (kWh / MWh) based on "
        "15-minute radiation data, panel count × wattage, cell technologies, mounting area, and inverter efficiency."
    )

    # 1. Location Section (Search, Map, Presets, Coordinates)
    location: SolarLocation = render_solar_location_section(key_prefix=f"{key_prefix}_loc")

    # 2. Technical PV Configuration Form (Input Panel)
    state_cfg_key = f"{key_prefix}_config"
    state_res_key = f"{key_prefix}_sim_result"

    current_cfg: Optional[SolarPVConfig] = st.session_state.get(state_cfg_key)
    if current_cfg is not None and not hasattr(current_cfg, "technology_preset"):
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
    cached_res = st.session_state.get(state_res_key)
    config_changed = False
    if cached_res is not None and hasattr(cached_res, "config"):
        prev_cfg = cached_res.config
        if (getattr(prev_cfg, "module_count", None) != config.module_count or
            getattr(prev_cfg, "module_power_wp", None) != config.module_power_wp or
            getattr(prev_cfg, "tilt_deg", None) != config.tilt_deg or
            getattr(prev_cfg, "azimuth_deg", None) != config.azimuth_deg or
            getattr(prev_cfg, "inverter_capacity_kw", None) != config.inverter_capacity_kw or
            getattr(prev_cfg, "temp_coefficient_pct_c", None) != config.temp_coefficient_pct_c):
            config_changed = True

    need_simulation = (
        submitted or
        config_changed or
        cached_res is None or
        not hasattr(cached_res, "technology_comparison") or
        not getattr(cached_res, "technology_comparison", None)
    )

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


    sim_res: SolarSimulationResult = st.session_state[state_res_key]
    kpis = sim_res.kpis
    df_ts = sim_res.df_timeseries

    # Save to global session state for downstream use
    st.session_state["solar_kw_15min"] = df_ts["P_AC_kW"]
    st.session_state["solar_kpis"] = kpis
    st.session_state["solar_config"] = config

    st.divider()


    # 4. Core Electrical Generation KPIs & Area Metrics
    st.subheader("3. Annual Electricity Generation & System Metrics")
    k1, k2, k3, k4 = st.columns(4)

    with k1:
        render_kpi_card(
            "⚡ Total Annual Yield",
            f"{kpis.annual_energy_mwh:,.2f} MWh",
            f"{kpis.annual_energy_kwh:,.0f} kWh total AC generation"
        )
    with k2:
        render_kpi_card(
            "🌟 Specific Yield",
            f"{kpis.specific_yield_kwh_per_kwp:,.1f} kWh/kWp",
            f"Full Load Hours: {kpis.full_load_hours:,.0f} h/a"
        )
    with k3:
        render_kpi_card(
            "📐 Generator Sizing",
            f"{config.dc_capacity_kwp:,.1f} kWp",
            f"{config.module_count:,} Panels à {config.module_power_wp:.0f} Wp"
        )
    with k4:
        render_kpi_card(
            "🏢 Required Area",
            f"{config.required_area_m2:,.0f} m²",
            f"Net Panel Area: {config.gross_panel_area_m2:,.0f} m² (Factor: {config.area_factor:.1f})"
        )

    # 5. Multi-Technology Comparative Production Analysis (Output Panel)
    st.subheader("4. Multi-Technology Production Analysis (PERC vs. TOPCon vs. Backcontact)")
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

    # 6. Interactive 15-Minute Generation Timeseries Plot
    st.subheader("5. Solar Generation Profile Timeseries (15-Minute Resolution)")
    fig_ts = create_solar_timeseries_figure(
        df=df_ts,
        dc_capacity_kwp=config.dc_capacity_kwp,
        inverter_capacity_kw=config.inverter_capacity_kw
    )
    st.plotly_chart(fig_ts, use_container_width=True)

    # 7. Monthly Yields & Seasonal Profiles (Year Sheet)
    st.subheader("6. Monthly Energy Production & Seasonal Profiles (Year Sheet)")
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

    # 8. Loss Waterfall Analysis
    st.subheader("7. Physical Energy Loss Cascade (Waterfall Diagram)")
    st.caption("Detailed breakdown from raw available sunlight on module plane to net usable AC energy delivered to grid.")
    fig_loss = create_solar_loss_waterfall_figure(loss_breakdown=sim_res.loss_breakdown)
    st.plotly_chart(fig_loss, use_container_width=True)

    # 9. Itemized Monthly Yield Table (Matching Bild 4)
    with st.expander("📋 Itemized Monthly Yield Table & Statistics (Year Sheet Data)", expanded=False):
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

