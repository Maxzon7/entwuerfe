"""
========================================================================================
Scenario 3: Standalone Solar PV Sandbox (ui_sandbox/Solar_sandbox/app.py)
========================================================================================

Standalone Execution:
    python -m streamlit run "ui_sandbox/Solar_sandbox/app.py"

Architecture (1:1 with Main Program UI & Component Architecture):
  - Top Header Status Banner: Active Load Source, Step count, Session Reset.
  - Action Controls Bar: Load Example Case (Mendoza Benchmark) & Reset / Clear Solar.
  - Tab 1: Facility Load & Consumption Profile (1:1 from Currentsituation_sandbox / Main App)
      * Real CSV Smart Meter Ingestion & Synthetic 24h/365d Load Simulator
      * 35,040-step 15-min interactive profile, Load Duration Curve (LDC), and 4 Base KPIs
  - Tab 2: Standalone Solar PV Generation & Financials (1:1 with ui/tab3_solar/view.py)
      * 1. Geographic Location & Solar Radiation Site (Open-Meteo search, Presets, Folium Map, GPS fine-tuning)
      * Active Site Info Banner (Location, GPS, Hemisphere, Optimal Orientation & Tilt)
      * 2. Solar PV Technical Specifications & Generator Sizing (TMY weather, module count x Wp, DC capacity banner)
      * Extended Options expander (Cell technology, orientation, inverter capacity, losses)
      * Solar Financial & Turn-Key Investment Costs expander (Itemized EUR/Wp, OPEX %, discount rate)
      * Primary action button: Calculate Solar PV Generation
      * Sub-Tab A (Electricity Generation & Technical Yield):
          - Weather data callout & 4 KPI cards (Total Annual Yield, Specific Yield, Generator Sizing, Required Area)
          - 15-Minute Solar Generation Timeseries (POA Irradiance, DC Array, AC Grid Power, Inverter limit)
          - Monthly Production Bar Chart, Seasonal 24h curves, Physical Loss Waterfall
          - Multi-Technology Production Analysis (PERC vs TOPCon vs Backcontact) & Climatological P50/P90 Risk
      * Sub-Tab B (Solar Financial & Turn-Key CAPEX Assessment):
          - Quick Cost & Financial Parameter Tuner expander
          - 4 Primary CAPEX & LCOE KPIs + 4 Secondary Return KPIs (Payback, Net Benefit, NPV, IRR)
          - CAPEX Breakdown Donut Chart, 15-Year Cashflow Waterfall, and Year-by-Year Financial Ledger
  - Tab 3: Solar & Consumption Integration (Load Coupling & Hockey-Stick Sizing)
      * Coupled 15-min electrical dispatch (Direct self-consumption, surplus export, residual import)
      * Quick Auto-Sizing Presets (40%, Sweet-Spot 55%, 60%, 80%, 100% Demand Net-Zero)
      * Interactive Hockey-Stick Pareto Curve (Daylight coverage % vs. kWp vs. SCR %)
      * 15-Minute 7-day power flow dispatch curve & Monthly coupled energy balance stacked bar
      * Developer & Future Master Integration Data Contract (residual_power_kw + JSON export)
========================================================================================
"""

import os
import sys
import json
from typing import Dict, List, Any, Optional, Tuple
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# Path bootstrapping for 100% standalone execution
_CURRENT_DIR = os.path.abspath(os.path.dirname(__file__))
_UI_SANDBOX_DIR = os.path.abspath(os.path.join(_CURRENT_DIR, ".."))
_PROJECT_ROOT = os.path.abspath(os.path.join(_UI_SANDBOX_DIR, ".."))
_WORKSPACE_DIR = os.path.abspath(os.path.join(_PROJECT_ROOT, ".."))
for _p in (_WORKSPACE_DIR, _PROJECT_ROOT, _UI_SANDBOX_DIR, _CURRENT_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from models.solar import (
        SolarLocation,
        SolarPVConfig,
        SolarFinancialConfig,
        SolarSimulationResult,
        TECHNOLOGY_SPECS,
    )
    from core.solar_engine import simulate_solar_pv_generation, couple_solar_simulation_with_load
    from core.solar_financial_engine import compute_solar_financial_metrics
    from ui.tab3_solar.forms import render_solar_location_section, render_solar_config_form
    from ui.tab3_solar.charts import (
        create_solar_timeseries_figure,
        create_solar_monthly_bar_figure,
        create_solar_seasonal_daily_figure,
        create_solar_loss_waterfall_figure,
        create_technology_comparison_figure,
        create_solar_capex_donut_figure,
        create_solar_cashflow_payback_figure,
    )
    from ui.tab3_solar.integration_charts import (
        create_solar_load_dispatch_figure,
        create_monthly_energy_balance_figure as create_coupled_monthly_energy_balance_figure,
        create_energy_flow_sankey_figure,
    )
    from ui.common.cards import render_kpi_card
    from ui.common.styles import apply_custom_styles
except ImportError:
    from current_model.models.solar import (
        SolarLocation,
        SolarPVConfig,
        SolarFinancialConfig,
        SolarSimulationResult,
        TECHNOLOGY_SPECS,
    )
    from current_model.core.solar_engine import simulate_solar_pv_generation, couple_solar_simulation_with_load
    from current_model.core.solar_financial_engine import compute_solar_financial_metrics
    from current_model.ui.tab3_solar.forms import render_solar_location_section, render_solar_config_form
    from current_model.ui.tab3_solar.charts import (
        create_solar_timeseries_figure,
        create_solar_monthly_bar_figure,
        create_solar_seasonal_daily_figure,
        create_solar_loss_waterfall_figure,
        create_technology_comparison_figure,
        create_solar_capex_donut_figure,
        create_solar_cashflow_payback_figure,
    )
    from current_model.ui.tab3_solar.integration_charts import (
        create_solar_load_dispatch_figure,
        create_monthly_energy_balance_figure as create_coupled_monthly_energy_balance_figure,
        create_energy_flow_sankey_figure,
    )
    from current_model.ui.common.cards import render_kpi_card
    from current_model.ui.common.styles import apply_custom_styles

try:
    from ui_sandbox.Currentsituation_sandbox.engine.config_and_models import LoadSeries2025
    from ui_sandbox.Currentsituation_sandbox.engine.consumption_pipeline import (
        normalize_load_profile_2025,
        synthesize_benchmark_load_profile_2025,
    )
    from ui_sandbox.Currentsituation_sandbox.consumption.view import render_tab1_consumption
except ImportError:
    from current_model.ui_sandbox.Currentsituation_sandbox.engine.config_and_models import LoadSeries2025
    from current_model.ui_sandbox.Currentsituation_sandbox.engine.consumption_pipeline import (
        normalize_load_profile_2025,
        synthesize_benchmark_load_profile_2025,
    )
    from current_model.ui_sandbox.Currentsituation_sandbox.consumption.view import render_tab1_consumption

from ui_sandbox.Solar_sandbox.solar_sandbox_engine import (
    compute_solar_hockey_stick_curve,
    create_solar_hockey_stick_figure,
    create_monthly_solar_balance_figure,
)


def _get_or_create_active_load() -> Tuple[LoadSeries2025, str]:
    """Retrieves or normalizes the active load profile for 2025 from session state."""
    if "active_load_series_2025" in st.session_state and isinstance(st.session_state["active_load_series_2025"], LoadSeries2025):
        fname = st.session_state.get("active_csv_filename", "Active Baseline Profile")
        return st.session_state["active_load_series_2025"], fname

    if "active_csv_df" in st.session_state and isinstance(st.session_state["active_csv_df"], pd.DataFrame):
        df_csv = st.session_state["active_csv_df"]
        if not df_csv.empty:
            fname = st.session_state.get("active_csv_filename", "Uploaded Meter File")
            p_col = "Total_Demand_kW" if "Total_Demand_kW" in df_csv.columns else df_csv.columns[1]
            t_col = "timestamp" if "timestamp" in df_csv.columns else None
            try:
                load_norm, _ = normalize_load_profile_2025(raw_df=df_csv, power_col=p_col, time_col=t_col)
                st.session_state["active_load_series_2025"] = load_norm
                return load_norm, f"CSV Real Meter Data ({fname})"
            except Exception:
                pass

    load_bench = synthesize_benchmark_load_profile_2025(nominal_peak_kw=250.0)
    st.session_state["active_load_series_2025"] = load_bench
    return load_bench, "Commercial Benchmark Simulation (250 kW peak)"


def render_solar_sandbox(key_prefix: str = "solar_sb") -> None:
    """Main orchestrator for the Standalone Solar PV Sandbox."""
    st.set_page_config(
        page_title="Isolated Solar PV Workbench",
        page_icon=":material/solar_power:",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    # Inject global dark mode card and typography styles
    apply_custom_styles()

    # ----------------------------------------------------------------------------------
    # Top Status & Control Header Banner
    # ----------------------------------------------------------------------------------
    load_series, source_label = _get_or_create_active_load()
    active_source_type = st.session_state.get("tab1_active_source", "synthetic")
    source_badge = "CSV Real Meter Data" if active_source_type == "csv" else "Synthetic Simulator"

    with st.container(border=True):
        c_status, c_steps, c_reset = st.columns([1.8, 1.4, 0.8])
        with c_status:
            st.markdown(
                f"""
                <div style="font-size:0.85rem;">
                    <span style="color:#94a3b8; font-weight:600;">Active Load Baseline Source:</span>
                    <strong style="color:#38bdf8; margin-left:6px;">{source_badge}</strong>
                    <div style="color:#cbd5e1; font-size:0.80rem; margin-top:2px;">{source_label}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with c_steps:
            st.markdown(
                f"""
                <div style="font-size:0.85rem;">
                    <span style="color:#94a3b8; font-weight:600;">Data Resolution & Shape:</span>
                    <strong style="color:#10b981; margin-left:6px;">{len(load_series.power_kw):,} steps (15-min / 2025)</strong>
                    <div style="color:#cbd5e1; font-size:0.80rem; margin-top:2px;">
                        Annual Energy: {load_series.total_energy_kwh:,.0f} kWh | Peak: {load_series.peak_demand_kw:,.1f} kW
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with c_reset:
            if st.button(":material/restart_alt: Reset Session", use_container_width=True, key=f"{key_prefix}_top_reset_btn"):
                keys_to_clear = [k for k in list(st.session_state.keys()) if k.startswith(key_prefix) or "solar_" in k]
                for k in keys_to_clear:
                    del st.session_state[k]
                st.rerun()

    # ----------------------------------------------------------------------------------
    # 3-Tab Main Layout
    # ----------------------------------------------------------------------------------
    tab1, tab2, tab3 = st.tabs(
        [
            ":material/analytics: Tab 1: Facility Load & Consumption Profile",
            ":material/solar_power: Tab 2: Standalone Solar PV Generation & Financials",
            ":material/energy_savings_leaf: Tab 3: Solar & Consumption Integration",
        ]
    )

    # ==================================================================================
    # TAB 1: Facility Load & Consumption Profile (1:1 from Main Program)
    # ==================================================================================
    with tab1:
        st.markdown(
            """
            <div style="background: #0f172a; border-left: 4px solid #38bdf8; padding: 10px 16px; border-radius: 6px; margin-bottom: 12px;">
                <strong style="color:#f8fafc; font-size:0.95rem;">Consumption Baseline Workbench</strong>
                <p style="color:#94a3b8; font-size:0.82rem; margin:2px 0 0 0;">
                    Select between real 15-minute interval smart meter CSV data ingestion or the 24h/365-day bottom-up synthetic load simulator.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        render_tab1_consumption(key_prefix=f"{key_prefix}_tab1_cons")
        load_series, source_label = _get_or_create_active_load()

    # ==================================================================================
    # TAB 2: Standalone Solar PV Generation & Financials (Matching Main Program Layout)
    # ==================================================================================
    with tab2:
        # Action Bar Matching Image 1
        act_col1, act_col2, _ = st.columns([3.5, 3.5, 5])
        with act_col1:
            if st.button(
                "Load Example Case (Mendoza Benchmark)",
                icon=":material/play_circle:",
                key=f"{key_prefix}_load_mendoza_btn",
                help="Pre-fills a real-world winery reference installation in Mendoza (600 panels, 270 kWp, TOPCon technology, 230 kW AC inverter)."
            ):
                st.session_state[f"{key_prefix}_loc_lat"] = -33.5133
                st.session_state[f"{key_prefix}_loc_lon"] = -69.2561
                st.session_state[f"{key_prefix}_loc_name"] = "Tunuyán, Mendoza (Bodegas Salentein)"
                st.session_state[f"{key_prefix}_loc_elev"] = 1100.0

                ex_cfg = SolarPVConfig(
                    module_count=600,
                    module_power_wp=450.0,
                    technology_preset="TOPCon",
                    module_technology="TOPCon (450 Wp - N-Type Modern Standard)",
                    inverter_capacity_kw=230.0,
                    tilt_deg=28.0,
                    azimuth_deg=0.0,
                    dc_capacity_kwp=270.0,
                    temp_coefficient_pct_c=-0.30,
                    weather_mode="TMY"
                )
                ex_fin = SolarFinancialConfig(
                    is_enabled=True,
                    currency="EUR",
                    cost_modules_per_wp=1.00,
                    cost_inverter_per_w=0.07,
                    cost_substructure_per_wp=0.15,
                    cost_installation_per_wp=0.35,
                    fixed_switchgear_cost=0.0,
                    fixed_travel_fee=0.0,
                    annual_opex_pct=1.0,
                    discount_rate_pct=5.0
                )
                st.session_state[f"{key_prefix}_active_cfg"] = ex_cfg
                st.session_state[f"{key_prefix}_active_fin"] = ex_fin

                # Clear previous form widget state keys so they refresh cleanly with Mendoza values
                for k in [
                    f"{key_prefix}_cfg_form_mod_count",
                    f"{key_prefix}_cfg_form_tech_choice",
                    f"{key_prefix}_cfg_form_inv_kw",
                    f"{key_prefix}_cfg_form_tilt",
                    f"{key_prefix}_cfg_form_azimuth",
                    f"{key_prefix}_cfg_form_weather_mode_select",
                ]:
                    if k in st.session_state:
                        del st.session_state[k]

                st.session_state[f"{key_prefix}_trigger_calc"] = True
                st.rerun()

        with act_col2:
            if st.button(
                "Reset / Clear Solar",
                icon=":material/restart_alt:",
                key=f"{key_prefix}_clear_solar_btn",
                help="Resets all inputs back to empty state and clears cached simulation results."
            ):
                for k in [
                    f"{key_prefix}_active_cfg",
                    f"{key_prefix}_active_fin",
                    f"{key_prefix}_sim_result",
                    f"{key_prefix}_trigger_calc",
                ]:
                    if k in st.session_state:
                        del st.session_state[k]
                st.rerun()

        # ------------------------------------------------------------------------------
        # Section 1: Geographic Location & Solar Radiation Site (Matching Image 1)
        # ------------------------------------------------------------------------------
        location: SolarLocation = render_solar_location_section(key_prefix=f"{key_prefix}_loc")

        # ------------------------------------------------------------------------------
        # Section 2: Technical PV Configuration Form (Matching Image 2 & Image 4)
        # ------------------------------------------------------------------------------
        current_cfg: Optional[SolarPVConfig] = st.session_state.get(f"{key_prefix}_active_cfg")
        current_fin: Optional[SolarFinancialConfig] = st.session_state.get(f"{key_prefix}_active_fin")

        config, fin_config, submitted = render_solar_config_form(
            location=location,
            current_config=current_cfg,
            current_fin_config=current_fin,
            key_prefix=f"{key_prefix}_cfg"
        )

        st.session_state[f"{key_prefix}_active_cfg"] = config
        st.session_state[f"{key_prefix}_active_fin"] = fin_config

        # ------------------------------------------------------------------------------
        # Section 3: Physical Simulation Execution & Caching
        # ------------------------------------------------------------------------------
        auto_trigger = st.session_state.pop(f"{key_prefix}_trigger_calc", False)
        cached_res: Optional[SolarSimulationResult] = st.session_state.get(f"{key_prefix}_sim_result")

        valid_sizing = config.module_count > 0 and (config.dc_capacity_kwp or 0) > 0
        need_simulation = valid_sizing and (submitted or auto_trigger or cached_res is None)

        if need_simulation:
            with st.spinner("Calculating 15-minute physical solar PV generation..."):
                try:
                    sim_result: SolarSimulationResult = simulate_solar_pv_generation(
                        config=config,
                        location=location
                    )
                    if fin_config and (fin_config.is_enabled or (getattr(fin_config, "cost_modules_per_wp", None) and fin_config.cost_modules_per_wp > 0)):
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

                    st.session_state[f"{key_prefix}_sim_result"] = sim_result
                    cached_res = sim_result
                except Exception as err:
                    st.error(f"Solar Simulation Error: {err}", icon=":material/error:")
                    return

        if cached_res is None:
            st.divider()
            st.info(
                "**Ready to Simulate Solar PV Generation**\n\n"
                "Review or adjust your solar system specifications and financial parameters above, then click "
                "**:material/calculate: Calculate Solar PV Generation** to compute the 15-minute physical generation profile, KPIs, and yield.",
                icon=":material/info:"
            )
            return

        sim_res = cached_res
        kpis = sim_res.kpis
        df_ts = sim_res.df_timeseries

        st.divider()

        # ------------------------------------------------------------------------------
        # Section 4: Results Sub-Tabs Navigation (Matching Image 3)
        # ------------------------------------------------------------------------------
        tab_yield, tab_finance = st.tabs([
            ":material/bolt: Electricity Generation & Technical Yield",
            ":material/payments: Solar Financial & Turn-Key CAPEX Assessment"
        ])

        # ==============================================================================
        # SUB-TAB A: Technical Solar PV Generation & Electrical Metrics
        # ==============================================================================
        with tab_yield:
            weather_source = getattr(kpis, "weather_data_source", "PVGIS-ERA5 Typical Meteorological Year (TMY)")
            st.info(f"Active Weather Data Foundation: **{weather_source}** | 35,040 Time Steps (15-Minute Grid)", icon=":material/info:")

            # 3. Core Electrical Generation KPIs Matching Image 3
            st.subheader("3. Annual Electricity Generation & System Metrics")
            k1, k2, k3, k4 = st.columns(4)
            with k1:
                render_kpi_card(
                    "Total Annual Yield",
                    f"{kpis.annual_energy_kwh:,.0f} kWh",
                    "Total annual AC electricity generation"
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

            # 4. Interactive 15-Minute Generation Timeseries Plot Matching Image 3
            st.subheader("4. Solar Generation Profile Timeseries (15-Minute Resolution)")
            fig_ts = create_solar_timeseries_figure(
                df=df_ts,
                dc_capacity_kwp=config.dc_capacity_kwp,
                inverter_capacity_kw=config.inverter_capacity_kw
            )
            st.plotly_chart(fig_ts, use_container_width=True)

            # 5. Monthly Yields & Seasonal Profiles
            st.subheader("5. Monthly Energy Production & Seasonal Profiles (Year Sheet)")
            col_m, col_s = st.columns(2)
            with col_m:
                fig_monthly = create_solar_monthly_bar_figure(
                    monthly_yields=sim_res.monthly_yields,
                    dc_capacity_kwp=config.dc_capacity_kwp
                )
                st.plotly_chart(fig_monthly, use_container_width=True)
            with col_s:
                fig_seasonal = create_solar_seasonal_daily_figure(df=df_ts, latitude=location.latitude)
                st.plotly_chart(fig_seasonal, use_container_width=True)

            # 6. Physical Loss Waterfall Analysis
            st.subheader("6. Physical Energy Loss Cascade (Waterfall Diagram)")
            fig_loss = create_solar_loss_waterfall_figure(loss_breakdown=sim_res.loss_breakdown)
            st.plotly_chart(fig_loss, use_container_width=True)

            # 7. Itemized Monthly Yield Table
            with st.expander(":material/table_chart: Itemized Monthly Yield Table & Statistics", expanded=False):
                table_rows = []
                for m in sim_res.monthly_yields:
                    table_rows.append({
                        "Month": m.month_name,
                        "Days": m.days_count,
                        "Energy (kWh)": f"{m.energy_kwh:,.0f}",
                        "Specific Yield (kWh/kWp)": f"{m.specific_yield_kwh_kwp:.1f}",
                        "Avg Daily (kWh/d)": f"{m.avg_daily_kwh:,.1f}",
                        "Peak Power (kW)": f"{m.peak_power_kw:,.1f}",
                        "Capacity Factor (%)": f"{m.capacity_factor_pct:.1f} %"
                    })
                st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)

            # 8. Multi-Technology Comparative Production Analysis
            if sim_res.technology_comparison and len(sim_res.technology_comparison) > 0:
                st.subheader("7. Multi-Technology Production Analysis (PERC vs. TOPCon vs. Backcontact)")
                fig_tech = create_technology_comparison_figure(sim_res.technology_comparison)
                st.plotly_chart(fig_tech, use_container_width=True)

        # ==============================================================================
        # SUB-TAB B: Solar Financial & Turn-Key CAPEX Assessment
        # ==============================================================================
        with tab_finance:
            fin_m = sim_res.financial_metrics
            active_fin = fin_config or getattr(sim_res, "financial_config", None) or SolarFinancialConfig(
                is_enabled=True,
                currency="EUR",
                cost_modules_per_wp=1.00,
                cost_inverter_per_w=0.07,
                cost_substructure_per_wp=0.15,
                cost_installation_per_wp=0.35,
                annual_opex_pct=1.0,
                discount_rate_pct=5.0
            )

            if fin_m is None or not getattr(fin_m, "is_configured", False) or getattr(fin_m, "total_capex", 0) <= 0:
                fin_m = compute_solar_financial_metrics(
                    config=config,
                    fin_config=active_fin,
                    annual_generation_kwh=sim_res.kpis.annual_energy_kwh,
                    multi_year_yields=sim_res.multi_year_yields
                )
                sim_res.financial_config = active_fin
                sim_res.financial_metrics = fin_m
                st.session_state[f"{key_prefix}_sim_result"] = sim_res

            if fin_m and fin_m.is_configured and fin_m.total_capex > 0:
                f_curr = fin_m.currency
                st.subheader("Solar Turn-Key Investment Costs & CAPEX Breakdown")
                st.caption("Turn-key solar plant investment breakdown and standalone electricity generation costs (LCOE):")

                # Quick Parameter Tuner Expander
                with st.expander(":material/tune: Quick Turn-Key Cost & Financial Parameter Tuner", expanded=False):
                    with st.form(key=f"{key_prefix}_quick_fin_tuner_form"):
                        tf_c1, tf_c2, tf_c3, tf_c4 = st.columns(4)
                        with tf_c1:
                            t_mod = st.number_input(f"Modules ({f_curr}/Wp):", min_value=0.0, value=float(active_fin.cost_modules_per_wp or 1.00), step=0.05, format="%.2f")
                            t_inv = st.number_input(f"Inverter ({f_curr}/W AC):", min_value=0.0, value=float(active_fin.cost_inverter_per_w or 0.07), step=0.01, format="%.2f")
                        with tf_c2:
                            t_sub = st.number_input(f"Substructure ({f_curr}/Wp):", min_value=0.0, value=float(active_fin.cost_substructure_per_wp or 0.15), step=0.01, format="%.2f")
                            t_inst = st.number_input(f"Installation ({f_curr}/Wp):", min_value=0.0, value=float(active_fin.cost_installation_per_wp or 0.35), step=0.01, format="%.2f")
                        with tf_c3:
                            t_switch = st.number_input(f"Switchgear Cabinet ({f_curr}):", min_value=0.0, value=float(active_fin.fixed_switchgear_cost or 0.0), step=250.0)
                            t_travel = st.number_input(f"Mobilization Fee ({f_curr}):", min_value=0.0, value=float(active_fin.fixed_travel_fee or 0.0), step=100.0)
                        with tf_c4:
                            t_opex = st.number_input("Annual O&M (%/a):", min_value=0.0, max_value=10.0, value=float(active_fin.annual_opex_pct or 1.0), step=0.1, format="%.1f")
                            t_disc = st.number_input("Discount Rate (%):", min_value=0.0, max_value=20.0, value=float(active_fin.discount_rate_pct or 5.0), step=0.5, format="%.1f")

                        tuner_submitted = st.form_submit_button("Update & Recalculate Turn-Key Financials", icon=":material/refresh:", type="primary", use_container_width=True)

                    if tuner_submitted:
                        t_fin = SolarFinancialConfig(
                            is_enabled=True,
                            currency=active_fin.currency or "EUR",
                            cost_modules_per_wp=t_mod,
                            cost_inverter_per_w=t_inv,
                            cost_substructure_per_wp=t_sub,
                            cost_installation_per_wp=t_inst,
                            fixed_switchgear_cost=t_switch,
                            fixed_travel_fee=t_travel,
                            annual_opex_pct=t_opex,
                            discount_rate_pct=t_disc,
                            electricity_price_inflation_pct=active_fin.electricity_price_inflation_pct,
                            feed_in_tariff_per_kwh=active_fin.feed_in_tariff_per_kwh,
                            analysis_horizon_years=15
                        )
                        fin_m = compute_solar_financial_metrics(
                            config=config,
                            fin_config=t_fin,
                            annual_generation_kwh=sim_res.kpis.annual_energy_kwh,
                            multi_year_yields=sim_res.multi_year_yields
                        )
                        sim_res.financial_config = t_fin
                        sim_res.financial_metrics = fin_m
                        st.session_state[f"{key_prefix}_sim_result"] = sim_res
                        st.session_state[f"{key_prefix}_active_fin"] = t_fin
                        st.rerun()

                # 1. Primary CAPEX & LCOE KPIs
                fk1, fk2, fk3, fk4 = st.columns(4)
                with fk1:
                    render_kpi_card("Total Solar CAPEX", f"{fin_m.total_capex:,.2f} {f_curr}", "Turn-key system investment", status="ok")
                with fk2:
                    render_kpi_card("Specific Investment", f"{fin_m.capex_per_kwp:,.2f} {f_curr}/kWp", "Per kWp installed DC capacity")
                with fk3:
                    render_kpi_card("Electricity Generation Cost (LCOE)", f"{fin_m.lcoe_per_kwh:.4f} {f_curr}/kWh", "Levelized cost across 15-year horizon")
                with fk4:
                    render_kpi_card("Annual Maintenance / OPEX", f"{fin_m.annual_opex_year1:,.2f} {f_curr}/a", f"Year 1 O&M reserve ({active_fin.annual_opex_pct:.1f}% p.a.)")

                # 2. Secondary Financial Return KPIs
                st.write("")
                fk5, fk6, fk7, fk8 = st.columns(4)
                with fk5:
                    pb_text = f"{fin_m.payback_period_years:.1f} Years" if fin_m.payback_period_years else "Over 15 Years"
                    render_kpi_card("Amortisation / Payback", pb_text, f"Discounted: {fin_m.discounted_payback_years:.1f} Yrs" if fin_m.discounted_payback_years else "Break-even timeline", status="ok" if fin_m.payback_period_years and fin_m.payback_period_years <= 10.0 else "default")
                with fk6:
                    render_kpi_card("15-Year Net Benefit", f"{fin_m.total_lifetime_savings:,.2f} {f_curr}", "Cumulative cash benefit after CAPEX & OPEX")
                with fk7:
                    render_kpi_card("15-Year Net Present Value (NPV)", f"{fin_m.npv:,.2f} {f_curr}", f"Discounted @ {active_fin.discount_rate_pct:.1f}%")
                with fk8:
                    irr_text = f"{fin_m.irr_pct:.1f} %" if fin_m.irr_pct else "N/A"
                    render_kpi_card("Internal Rate of Return (IRR)", irr_text, "Financial yield of invested capital", status="ok" if fin_m.irr_pct and fin_m.irr_pct > 10.0 else "default")

                # Charts
                f_ch1, f_ch2 = st.columns(2)
                with f_ch1:
                    fig_donut = create_solar_capex_donut_figure(fin_m, currency=f_curr)
                    st.plotly_chart(fig_donut, use_container_width=True)
                with f_ch2:
                    fig_pb = create_solar_cashflow_payback_figure(fin_m, currency=f_curr)
                    st.plotly_chart(fig_pb, use_container_width=True)

    # ==================================================================================
    # TAB 3: Solar & Consumption Integration (Hockey-Stick Curve & Load Coupling)
    # ==================================================================================
    with tab3:
        st.markdown(
            """
            <div style="background: #0f172a; border-left: 4px solid #10b981; padding: 10px 16px; border-radius: 6px; margin-bottom: 16px;">
                <strong style="color:#f8fafc; font-size:1.0rem;">Solar PV & Facility Load Coupling (Self-Consumption & Auto-Sizing)</strong>
                <p style="color:#94a3b8; font-size:0.82rem; margin:2px 0 0 0;">
                    Couples 15-minute physical Solar PV generation with your facility consumption baseline from Tab 1.
                    Evaluates direct self-consumption, surplus export, residual grid import, and the interactive Hockey-Stick Pareto sizing curve.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        sim_res_active: Optional[SolarSimulationResult] = st.session_state.get(f"{key_prefix}_sim_result")
        if sim_res_active is None:
            st.warning("Please configure and calculate solar generation in **Tab 2** first to view load integration.", icon=":material/warning:")
            return

        # Prepare 35,040-step load dataframe for full physical coupling
        load_df = pd.DataFrame({
            "timestamp": load_series.timestamps,
            "Total_Demand_kW": load_series.power_kw
        })

        sim_res_coupled = couple_solar_simulation_with_load(
            solar_res=sim_res_active,
            load_df=load_df,
            gap_handling="bypass"
        )
        df_coupled = sim_res_coupled.df_timeseries
        kpis_coupled = sim_res_coupled.kpis

        p_orig_max = float(df_coupled["P_Load_kW"].max()) if "P_Load_kW" in df_coupled.columns else 0.0
        p_res_max = float(df_coupled["P_Residual_kW"].max()) if "P_Residual_kW" in df_coupled.columns else 0.0
        peak_shaved_kw = max(0.0, p_orig_max - p_res_max)
        peak_shaved_pct = (peak_shaved_kw / p_orig_max * 100.0) if p_orig_max > 0 else 0.0

        # ------------------------------------------------------------------------------
        # 1. Coupled Dispatch Performance Metrics (Matching Main Program Sub-Tab 3.2)
        # ------------------------------------------------------------------------------
        st.subheader("1. Coupled Dispatch Performance Metrics")
        k1, k2, k3, k4 = st.columns(4)
        with k1:
            render_kpi_card(
                "Self-Consumption Rate",
                f"{kpis_coupled.self_consumption_rate_pct:.1f} %",
                f"{kpis_coupled.direct_consumption_kwh:,.0f} kWh of {kpis_coupled.annual_energy_kwh:,.0f} kWh used on-site",
                status="ok"
            )
        with k2:
            render_kpi_card(
                "Autarky / Solar Fraction",
                f"{kpis_coupled.solar_fraction_autarky_pct:.1f} %",
                f"Covers {kpis_coupled.direct_consumption_kwh:,.0f} kWh of {kpis_coupled.total_load_kwh:,.0f} kWh demand",
                status="ok"
            )
        with k3:
            render_kpi_card(
                "PV Surplus / Grid Export",
                f"{kpis_coupled.surplus_generation_kwh:,.0f} kWh",
                f"{(kpis_coupled.surplus_generation_kwh / max(1.0, kpis_coupled.annual_energy_kwh) * 100.0):.1f}% of generation for export / BESS",
                status="default"
            )
        with k4:
            render_kpi_card(
                "Residual Grid Import",
                f"{kpis_coupled.residual_load_kwh:,.0f} kWh",
                "Remaining facility demand purchased from grid",
                status="default"
            )

        s1, s2, s3, s4 = st.columns(4)
        with s1:
            render_kpi_card(
                "Peak Demand Reduction",
                f"-{peak_shaved_kw:.1f} kW",
                f"Original: {p_orig_max:.1f} kW -> Residual: {p_res_max:.1f} kW (-{peak_shaved_pct:.1f}%)",
                status="ok" if peak_shaved_kw > 0.1 else "default"
            )
        with s2:
            net_cov_pct = (kpis_coupled.annual_energy_kwh / max(1.0, kpis_coupled.total_load_kwh) * 100.0)
            render_kpi_card(
                "Annual Net Energy Coverage",
                f"{net_cov_pct:.1f} %",
                f"Generation: {kpis_coupled.annual_energy_kwh:,.0f} kWh vs Demand: {kpis_coupled.total_load_kwh:,.0f} kWh"
            )
        with s3:
            render_kpi_card(
                "Specific Solar Yield",
                f"{kpis_coupled.specific_yield_kwh_per_kwp:.1f} kWh/kWp",
                f"Full Load Hours: {kpis_coupled.full_load_hours:,.0f} h/a"
            )
        with s4:
            render_kpi_card(
                "Direct Solar Consumption",
                f"{kpis_coupled.direct_consumption_kwh:,.0f} kWh",
                "Total clean energy consumed instantaneously"
            )

        st.write("")

        # ------------------------------------------------------------------------------
        # 2. Visual Dispatch Analysis (3 Sub-Tabs matching Screenshot 2)
        # ------------------------------------------------------------------------------
        st.subheader("2. Visual Dispatch Analysis")
        chart_tab1, chart_tab2, chart_tab3 = st.tabs([
            ":material/timeline: 15-Minute Dispatch Timeseries",
            ":material/bar_chart: Monthly Energy Balance",
            ":material/schema: Energy Flow (Sankey)"
        ])

        with chart_tab1:
            fig_ts = create_solar_load_dispatch_figure(
                df=df_coupled,
                dc_capacity_kwp=sim_res_active.config.dc_capacity_kwp,
                inverter_capacity_kw=sim_res_active.config.inverter_capacity_kw
            )
            st.plotly_chart(fig_ts, use_container_width=True)

        with chart_tab2:
            fig_monthly = create_coupled_monthly_energy_balance_figure(df=df_coupled)
            st.plotly_chart(fig_monthly, use_container_width=True)

        with chart_tab3:
            fig_sankey = create_energy_flow_sankey_figure(kpis=kpis_coupled)
            st.plotly_chart(fig_sankey, use_container_width=True)

        st.divider()

        # ------------------------------------------------------------------------------
        # 3. Sizing Optimization & Hockey-Stick Pareto Curve (Moved to the Bottom)
        # ------------------------------------------------------------------------------
        st.subheader("3. Sizing Optimization & Hockey-Stick Pareto Curve")
        st.caption(
            "Auto-size your PV plant relative to annual facility demand. "
            "The **Hockey-Stick Curve** illustrates the diminishing returns of solar self-consumption: "
            "as capacity exceeds midday load, further kWp additions predominantly export to the grid."
        )

        p_solar_kw = df_coupled["P_AC_kW"].to_numpy()
        unit_pv_kw = p_solar_kw / max(0.1, sim_res_active.config.dc_capacity_kwp)
        spec_yield = float(sim_res_active.kpis.specific_yield_kwh_per_kwp)
        df_hockey, presets_kwp = compute_solar_hockey_stick_curve(
            load=load_series,
            unit_pv_kw=unit_pv_kw,
            specific_yield_kwh_per_kwp=spec_yield,
        )

        st.markdown("##### :material/auto_awesome: Quick Sizing Presets (Target Demand Ratio)")
        b1, b2, b3, b4, b5 = st.columns(5)
        if b1.button(f"40% Demand ({presets_kwp['40_pct']:,.0f} kWp)", use_container_width=True, key=f"{key_prefix}_sz_40"):
            _recalc_target_kwp(presets_kwp["40_pct"], sim_res_active, key_prefix)
        if b2.button(f"Sweet-Spot 55% ({presets_kwp['sweet_spot']:,.0f} kWp)", use_container_width=True, key=f"{key_prefix}_sz_sweet", type="primary"):
            _recalc_target_kwp(presets_kwp["sweet_spot"], sim_res_active, key_prefix)
        if b3.button(f"60% Demand ({presets_kwp['60_pct']:,.0f} kWp)", use_container_width=True, key=f"{key_prefix}_sz_60"):
            _recalc_target_kwp(presets_kwp["60_pct"], sim_res_active, key_prefix)
        if b4.button(f"80% Demand ({presets_kwp['80_pct']:,.0f} kWp)", use_container_width=True, key=f"{key_prefix}_sz_80"):
            _recalc_target_kwp(presets_kwp["80_pct"], sim_res_active, key_prefix)
        if b5.button(f"100% Net-Zero ({presets_kwp['100_pct']:,.0f} kWp)", use_container_width=True, key=f"{key_prefix}_sz_100"):
            _recalc_target_kwp(presets_kwp["100_pct"], sim_res_active, key_prefix)

        daylight_mask = p_solar_kw > 1.0
        daylight_demand_kwh = float(np.sum(load_series.power_kw[daylight_mask]) * 0.25)
        daylight_cov_pct = (kpis_coupled.direct_consumption_kwh / daylight_demand_kwh * 100.0) if daylight_demand_kwh > 0 else 0.0

        col_curve, col_kpis = st.columns([1.5, 1.0])
        with col_curve:
            fig_hockey = create_solar_hockey_stick_figure(
                df_curve=df_hockey,
                selected_kwp=sim_res_active.config.dc_capacity_kwp,
                selected_daylight_cov_pct=daylight_cov_pct,
                selected_scr_pct=kpis_coupled.self_consumption_rate_pct,
            )
            st.plotly_chart(fig_hockey, use_container_width=True)

        with col_kpis:
            with st.container(border=True):
                st.markdown("##### System Sizing & Energy Balance")
                st.metric("Installed PV Capacity", f"{sim_res_active.config.dc_capacity_kwp:,.1f} kWp DC", f"{sim_res_active.config.module_count:,} Panels")
                st.metric("Daylight Demand Coverage", f"{daylight_cov_pct:.1f}%", f"Total Autarky: {kpis_coupled.solar_fraction_autarky_pct:.1f}%")
                st.metric("Self-Consumption Rate (SCR)", f"{kpis_coupled.self_consumption_rate_pct:.1f}%", f"Direct: {kpis_coupled.direct_consumption_kwh / 1000.0:,.1f} MWh/a")

        # ------------------------------------------------------------------------------
        # 4. Standardized Session State Output Contract for Phase 2 Master Integration
        # ------------------------------------------------------------------------------
        p_residual_arr = df_coupled["P_Residual_kW"].to_numpy()
        p_direct_arr = df_coupled["P_Direct_kW"].to_numpy()
        p_export_arr = df_coupled["P_Surplus_kW"].to_numpy()
        p_solar_arr = df_coupled["P_AC_kW"].to_numpy()

        st.session_state["solar_standalone_result"] = {
            "load_series": load_series,
            "residual_power_kw": p_residual_arr,
            "p_solar_kw": p_solar_arr,
            "p_direct_kw": p_direct_arr,
            "p_export_kw": p_export_arr,
            "pv_kwp": sim_res_active.config.dc_capacity_kwp,
            "total_capex": getattr(sim_res_active.financial_metrics, "total_capex", 0.0),
            "annual_om_year1": getattr(sim_res_active.financial_metrics, "annual_opex_year1", 0.0),
            "lcoe": getattr(sim_res_active.financial_metrics, "lcoe_per_kwh", 0.0),
            "annual_generation_kwh": kpis_coupled.annual_energy_kwh,
            "direct_self_consumption_kwh": kpis_coupled.direct_consumption_kwh,
            "surplus_export_kwh": kpis_coupled.surplus_generation_kwh,
            "currency_code": getattr(sim_res_active.financial_metrics, "currency", "EUR"),
        }

        with st.expander(":material/integration_instructions: Developer & Future Master Integration Data Contract", expanded=False):
            st.caption(
                "This clean data contract holds the 35,040-step residual load array `residual_power_kw` and pure plant metrics. "
                "In Phase 2, this object will directly feed into the 4-Pillar electricity billing engine to evaluate tariff bill savings."
            )
            summary_dict = {
                "scenario": "solar_only_pure",
                "installed_kwp": sim_res_active.config.dc_capacity_kwp,
                "annual_generation_kwh": round(kpis_coupled.annual_energy_kwh, 1),
                "direct_self_consumption_kwh": round(kpis_coupled.direct_consumption_kwh, 1),
                "surplus_export_kwh": round(kpis_coupled.surplus_generation_kwh, 1),
                "self_consumption_rate_pct": round(kpis_coupled.self_consumption_rate_pct, 2),
                "autarky_pct": round(kpis_coupled.solar_fraction_autarky_pct, 2),
                "total_capex": round(getattr(sim_res_active.financial_metrics, "total_capex", 0.0), 2),
                "lcoe": round(getattr(sim_res_active.financial_metrics, "lcoe_per_kwh", 0.0), 5),
                "residual_peak_kw": round(float(np.max(p_residual_arr)), 2),
            }
            st.json(summary_dict)
            st.download_button(
                label=":material/download: Download Standalone Solar Plant Summary (.json)",
                data=json.dumps(summary_dict, indent=2).encode("utf-8"),
                file_name=f"solar_plant_summary_{sim_res_active.config.dc_capacity_kwp:.0f}kWp.json",
                mime="application/json",
                key=f"{key_prefix}_dl_sum_json",
            )


def _recalc_target_kwp(target_kwp: float, sim_res: SolarSimulationResult, key_prefix: str) -> None:
    """Helper to update module count for a target kWp preset and trigger re-simulation."""
    p_wp = sim_res.config.module_power_wp or 450.0
    mod_count = int(np.round(target_kwp * 1000.0 / p_wp))
    cfg = sim_res.config
    cfg.module_count = mod_count
    cfg.dc_capacity_kwp = mod_count * p_wp / 1000.0
    cfg.inverter_capacity_kw = round(cfg.dc_capacity_kwp * 0.85, 0)
    st.session_state[f"{key_prefix}_active_cfg"] = cfg
    st.session_state[f"{key_prefix}_trigger_calc"] = True
    st.rerun()


def main() -> None:
    render_solar_sandbox(key_prefix="solar_sb")


if __name__ == "__main__":
    main()
