"""
========================================================================================
Tab 3 Solar PV Simulator View (current_model/ui/tab3_solar/view.py)
========================================================================================

Description:
------------
Orchestrates Tab 3:
  - Prominent standalone isolation notice banner (st.warning)
  - Folium interactive map coordinate selector and site presets
  - Comprehensive technical configuration form
  - High-performance physical simulation engine call
  - Key Performance Indicator (KPI) cards (Yield, Specific Yield, PR, Full Load Hours)
  - Interactive timeseries figure with range slider
  - Monthly yield bar chart & seasonal 24-hour daily profile
  - Energy loss waterfall diagram
  - Detailed monthly data table export preview
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
    create_solar_loss_waterfall_figure
)


def render_tab3_solar(key_prefix: str = "tab3_solar") -> None:
    """
    Renders the complete Tab 3 Solar PV Generator view.
    """
    # 1. Standalone Isolation Warning Banner
    st.warning(
        "⚠️ **Notice: The Solar PV Generation module is currently running in standalone simulation mode "
        "to validate calculation accuracy and radiation modeling independently before grid and dispatch integration.**"
    )

    st.markdown("### ☀️ Photovoltaic Solar Generation Simulator")
    st.caption(
        "Model real-world solar generation using high-resolution Open-Meteo radiation data, "
        "dynamic module temperature physics, balance-of-system losses, and inverter conversion characteristics."
    )

    # 2. Location Section (City Search, Interactive Map, Presets, and Coordinates)
    location: SolarLocation = render_solar_location_section(key_prefix=f"{key_prefix}_loc")

    # 3. Technical PV Configuration Form
    state_cfg_key = f"{key_prefix}_config"
    state_res_key = f"{key_prefix}_sim_result"

    current_cfg: Optional[SolarPVConfig] = st.session_state.get(state_cfg_key)

    config, submitted = render_solar_config_form(
        location=location,
        current_config=current_cfg,
        key_prefix=f"{key_prefix}_form"
    )

    st.session_state[state_cfg_key] = config

    # 4. Simulation Execution & Caching
    if submitted or state_res_key not in st.session_state:
        with st.spinner("Fetching Open-Meteo radiation data and simulating solar PV physics..."):
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



    st.divider()

    # 5. Energy Metrics & Key Performance Indicators
    st.subheader("3. Annual Performance Metrics & Key Performance Indicators")
    k1, k2, k3, k4 = st.columns(4)

    with k1:
        render_kpi_card(
            "⚡ Total Annual Yield",
            f"{kpis.annual_energy_mwh:,.2f} MWh",
            f"{kpis.annual_energy_kwh:,.0f} kWh total generation"
        )
    with k2:
        render_kpi_card(
            "🌟 Specific Yield",
            f"{kpis.specific_yield_kwh_per_kwp:,.1f} kWh/kWp",
            f"Full Load Hours: {kpis.full_load_hours:,.0f} h/a"
        )
    with k3:
        pr_status = "ok" if kpis.performance_ratio_pct >= 80.0 else "neutral"
        render_kpi_card(
            "📊 Performance Ratio (PR)",
            f"{kpis.performance_ratio_pct:.1f} %",
            f"BOS & Thermal Loss: {100.0 - kpis.performance_ratio_pct:.1f} %",
            status=pr_status
        )
    with k4:
        render_kpi_card(
            "🔋 Capacity Factor",
            f"{kpis.capacity_factor_pct:.1f} %",
            f"Peak AC Power: {kpis.max_ac_power_kw:,.1f} kW"
        )

    # 6. Interactive Timeseries Plot
    st.subheader("4. Solar Generation Profile Timeseries (Hourly Resolution)")
    fig_ts = create_solar_timeseries_figure(
        df=df_ts,
        dc_capacity_kwp=config.dc_capacity_kwp,
        inverter_capacity_kw=config.inverter_capacity_kw
    )
    st.plotly_chart(fig_ts, use_container_width=True)

    # 7. Monthly Yields & Seasonal Profiles
    st.subheader("5. Seasonal & Monthly Production Analysis")
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
    st.subheader("6. Energy Loss Cascade (Waterfall Diagram)")
    st.caption("Detailed breakdown from raw available sunlight on module plane to net usable AC energy delivered to grid/facility.")
    fig_loss = create_solar_loss_waterfall_figure(loss_breakdown=sim_res.loss_breakdown)
    st.plotly_chart(fig_loss, use_container_width=True)

    # 9. Itemized Monthly Yield Table
    with st.expander("📋 Itemized Monthly Yield Table & Statistics", expanded=False):
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
