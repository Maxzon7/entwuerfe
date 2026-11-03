"""
========================================================================================
Scenario 5: Standalone Hybrid Solar PV + BESS Sandbox (ui_sandbox/SolarBESS_sandbox/app.py)
========================================================================================

Standalone Execution:
    python -m streamlit run "ui_sandbox/SolarBESS_sandbox/app.py"

4-Tab Architecture (Upgraded to Match Solar_sandbox, BESS_sandbox & Main Program):
  - Top Header Banner: Active Load Baseline Source, 35,040 steps, Annual Energy, Peak Demand, Reset.
  - Global Action Bar & Live Grid Limit Controller (outside forms):
      * 1-Click Reference Benchmark Loaders (Mendoza Winery 270 kWp + 500 kWh / Rotterdam WKO 150 kWp + 300 kWh)
      * Interactive Contracted Grid Connection Limit (P_limit in kW) with quick Peak % buttons
  - Tab 1: Facility Load & Consumption Profile (1:1 from Currentsituation_sandbox / Main Program)
  - Tab 2: Solar PV Site, Sizing & Generation Baseline (1:1 from Solar_sandbox / ui/tab3_solar/)
      * Section 1: Geographic Site, Presets, Interactive Map & GPS Coordinates
      * Section 2: Technical PV Spec Form + Hockey-Stick 1-Click Auto-Sizing (40%, Sweet-Spot 55%, 60%, 80%, 100%)
      * Section 3: Compact 4-KPI Generation & BESS Charging Potential Preview (Available PV Surplus for BESS)
  - Tab 3: BESS Sizing & Coupled Hybrid Dispatch (Core Hybrid Engine)
      * A. Intelligent Battery Pre-Dimensioning (Post-Solar Peak Overload + Daily PV Surplus + 3 Sizing Tiers)
      * B. BESS Hardware & Operational Strategy Form (Strategy 1: Strict Peak-Shaving vs. Strategy 2: Double-Lever)
      * C. Side-by-Side Strategy Comparison Table & 8 Executive Hybrid KPIs
      * D. 4 Visual Dispatch Sub-Tabs:
          1. Synchronized 2-in-1 15-Minute Power Flow & SoC Subplot (with Peak Week Focus)
          2. Monthly Energy Balance (12-Month Stacked Bar)
          3. Hybrid Energy Flow Sankey Diagram
          4. Synergy Benchmark (Status Quo vs. Solar-Only vs. BESS-Only vs. Hybrid PV+BESS)
  - Tab 4: Combined Plant Economics (CAPEX, OPEX & LCOE) & Master Integration Data Contract
      * Combined Turnkey Cost & Mid-Life Augmentation Form
      * 4 Financial KPI Cards (Combined CAPEX with PV/BESS %, Annual OPEX, Hybrid LCOE, Specific EUR/Shaved kW)
      * CAPEX Breakdown Donut Chart, 15-Year Outflow & Cumulative Trajectory, Yearly Ledger Table
      * Standardized Master Integration Data Contract (`st.session_state["solar_bess_standalone_result"]` + JSON export)
========================================================================================
"""

import os
import sys
import json
from typing import Dict, List, Any, Optional, Tuple
import numpy as np
import pandas as pd
import streamlit as st

# Ensure root and parent directories are on sys.path for standalone execution
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
    )
    from core.solar_engine import simulate_solar_pv_generation, couple_solar_simulation_with_load
    from ui.tab3_solar.forms import render_solar_location_section, render_solar_config_form
    from ui.tab3_solar.charts import (
        create_solar_timeseries_figure,
        create_solar_monthly_bar_figure,
        create_solar_loss_waterfall_figure,
    )
    from ui.common.cards import render_kpi_card
    from ui.common.styles import apply_custom_styles
except ImportError:
    from current_model.models.solar import (
        SolarLocation,
        SolarPVConfig,
        SolarFinancialConfig,
        SolarSimulationResult,
    )
    from current_model.core.solar_engine import simulate_solar_pv_generation, couple_solar_simulation_with_load
    from current_model.ui.tab3_solar.forms import render_solar_location_section, render_solar_config_form
    from current_model.ui.tab3_solar.charts import (
        create_solar_timeseries_figure,
        create_solar_monthly_bar_figure,
        create_solar_loss_waterfall_figure,
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
)
from ui_sandbox.SolarBESS_sandbox.solar_bess_sandbox_engine import (
    compute_hybrid_bess_pre_dimensioning,
    simulate_dual_strategies_comparison,
    compute_synergy_comparison_metrics,
    compute_hybrid_plant_financials,
    create_hybrid_synchronized_dispatch_soc_figure,
    create_hybrid_monthly_balance_figure,
    create_hybrid_sankey_figure,
    create_hybrid_synergy_comparison_figure,
    create_hybrid_capex_donut_figure,
    create_hybrid_15y_outflow_figure,
)


def _get_or_create_active_load() -> Tuple[LoadSeries2025, str]:
    """Retrieves or normalizes the active 35,040-step load profile for 2025 from session state."""
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


def _apply_staged_widget_updates(key_prefix: str) -> None:
    """
    Applies staged programmatic updates to widget session state keys BEFORE
    any Streamlit widgets are instantiated in the current script run.
    This guarantees zero StreamlitAPIExceptions when 1-click sizing buttons are clicked.
    """
    # 1. Staged Grid Limit kW
    pending_limit_key = f"{key_prefix}_pending_grid_limit_kw"
    if pending_limit_key in st.session_state:
        st.session_state[f"{key_prefix}_grid_limit_input"] = float(st.session_state.pop(pending_limit_key))

    # 2. Staged Solar PV Module Count & Inverter Capacity (for ui/tab3_solar/forms.py)
    pending_mod_key = f"{key_prefix}_pending_mod_count"
    if pending_mod_key in st.session_state:
        st.session_state[f"{key_prefix}_cfg_mod_count"] = int(st.session_state.pop(pending_mod_key))

    pending_inv_key = f"{key_prefix}_pending_inv_kw"
    if pending_inv_key in st.session_state:
        st.session_state[f"{key_prefix}_cfg_inv_kw"] = float(st.session_state.pop(pending_inv_key))

    # 3. Staged BESS Capacity (kWh), Power (kW), and Strategy
    pending_bess_kwh_key = f"{key_prefix}_pending_bess_kwh"
    if pending_bess_kwh_key in st.session_state:
        val_kwh = float(st.session_state.pop(pending_bess_kwh_key))
        st.session_state[f"{key_prefix}_bess_form_kwh"] = val_kwh
        st.session_state[f"{key_prefix}_active_bess_kwh"] = val_kwh

    pending_bess_kw_key = f"{key_prefix}_pending_bess_kw"
    if pending_bess_kw_key in st.session_state:
        val_kw = float(st.session_state.pop(pending_bess_kw_key))
        st.session_state[f"{key_prefix}_bess_form_kw"] = val_kw
        st.session_state[f"{key_prefix}_active_bess_kw"] = val_kw

    pending_strat_key = f"{key_prefix}_pending_bess_strategy"
    if pending_strat_key in st.session_state:
        val_strat = str(st.session_state.pop(pending_strat_key))
        st.session_state[f"{key_prefix}_bess_form_strategy"] = val_strat
        st.session_state[f"{key_prefix}_active_bess_strategy"] = val_strat


def _stage_solar_target_kwp(target_kwp: float, sim_res: SolarSimulationResult, key_prefix: str) -> None:
    """Stages a new PV capacity (kWp) into session state and triggers a clean rerun."""
    p_wp = float(sim_res.config.module_power_wp or 450.0)
    mod_count = max(10, int(np.round(target_kwp * 1000.0 / p_wp)))
    new_dc_kwp = round((mod_count * p_wp) / 1000.0, 2)
    new_inv_kw = round(new_dc_kwp * 0.85, 0)

    cfg = sim_res.config
    cfg.module_count = mod_count
    cfg.dc_capacity_kwp = new_dc_kwp
    cfg.inverter_capacity_kw = new_inv_kw

    st.session_state[f"{key_prefix}_active_cfg"] = cfg
    st.session_state[f"{key_prefix}_pending_mod_count"] = mod_count
    st.session_state[f"{key_prefix}_pending_inv_kw"] = new_inv_kw
    st.session_state[f"{key_prefix}_trigger_calc"] = True
    st.rerun()


def _stage_bess_sizing(target_kwh: float, target_kw: float, key_prefix: str, strategy_label: Optional[str] = None) -> None:
    """Stages BESS capacity (kWh) and power rating (kW) before widget instantiation and reruns."""
    st.session_state[f"{key_prefix}_pending_bess_kwh"] = max(10.0, round(float(target_kwh), 0))
    st.session_state[f"{key_prefix}_pending_bess_kw"] = max(10.0, round(float(target_kw), 0))
    if strategy_label is not None:
        st.session_state[f"{key_prefix}_pending_bess_strategy"] = strategy_label
    st.rerun()


def _load_reference_benchmark(case_id: str, load_series: LoadSeries2025, key_prefix: str) -> None:
    """Pre-fills location, PV configuration, BESS sizing, and grid limit for a reference benchmark."""
    orig_peak = float(load_series.peak_demand_kw)
    if case_id == "mendoza":
        st.session_state[f"{key_prefix}_loc_lat"] = -33.5133
        st.session_state[f"{key_prefix}_loc_lon"] = -69.2561
        st.session_state[f"{key_prefix}_loc_name"] = "Tunuyan, Mendoza (Bodegas Salentein)"
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
            temp_coefficient_pct_c=-0.29,
            weather_mode="TMY",
        )
        bess_kwh, bess_kw = 500.0, 250.0
        target_limit = round(orig_peak * 0.75, 0) if orig_peak > 120.0 else 200.0
    else:
        # Rotterdam WKO Commercial Benchmark
        st.session_state[f"{key_prefix}_loc_lat"] = 51.9244
        st.session_state[f"{key_prefix}_loc_lon"] = 4.4777
        st.session_state[f"{key_prefix}_loc_name"] = "Rotterdam Commercial WKO Facility (NL)"
        st.session_state[f"{key_prefix}_loc_elev"] = 5.0

        ex_cfg = SolarPVConfig(
            module_count=340,
            module_power_wp=450.0,
            technology_preset="TOPCon",
            module_technology="TOPCon (450 Wp - N-Type Modern Standard)",
            inverter_capacity_kw=130.0,
            tilt_deg=35.0,
            azimuth_deg=180.0,
            dc_capacity_kwp=153.0,
            temp_coefficient_pct_c=-0.29,
            weather_mode="TMY",
        )
        bess_kwh, bess_kw = 300.0, 150.0
        target_limit = round(orig_peak * 0.70, 0) if orig_peak > 100.0 else 150.0

    ex_fin = SolarFinancialConfig(
        is_enabled=True,
        currency="EUR",
        cost_modules_per_wp=0.55,
        cost_inverter_per_w=0.07,
        cost_substructure_per_wp=0.12,
        cost_installation_per_wp=0.21,
        fixed_switchgear_cost=0.0,
        fixed_travel_fee=0.0,
        annual_opex_pct=1.2,
        discount_rate_pct=6.0,
    )

    st.session_state[f"{key_prefix}_active_cfg"] = ex_cfg
    st.session_state[f"{key_prefix}_active_fin"] = ex_fin
    st.session_state[f"{key_prefix}_pending_mod_count"] = ex_cfg.module_count
    st.session_state[f"{key_prefix}_pending_inv_kw"] = ex_cfg.inverter_capacity_kw
    st.session_state[f"{key_prefix}_pending_bess_kwh"] = bess_kwh
    st.session_state[f"{key_prefix}_pending_bess_kw"] = bess_kw
    st.session_state[f"{key_prefix}_pending_grid_limit_kw"] = target_limit

    # Clear previous widget state keys so forms cleanly re-render with benchmark defaults
    for k in [
        f"{key_prefix}_cfg_mod_count",
        f"{key_prefix}_cfg_inv_kw",
        f"{key_prefix}_cfg_tilt",
        f"{key_prefix}_cfg_azimuth",
        f"{key_prefix}_cfg_tech_choice",
        f"{key_prefix}_bess_form_kwh",
        f"{key_prefix}_bess_form_kw",
    ]:
        if k in st.session_state:
            del st.session_state[k]

    st.session_state[f"{key_prefix}_trigger_calc"] = True
    st.rerun()


def render_solar_bess_sandbox(key_prefix: str = "hyb_sb") -> None:
    """Main orchestrator for the 4-Tab Standalone Hybrid Solar PV + BESS Workbench."""
    st.set_page_config(
        page_title="Hybrid Solar PV + BESS Workbench",
        page_icon=":material/battery_charging_full:",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    apply_custom_styles()
    _apply_staged_widget_updates(key_prefix)

    # ----------------------------------------------------------------------------------
    # 1. Top Status & Control Header Banner
    # ----------------------------------------------------------------------------------
    load_series, source_label = _get_or_create_active_load()
    active_source_type = st.session_state.get("tab1_active_source", "synthetic")
    source_badge = "CSV Real Meter Data" if active_source_type == "csv" else "Synthetic Simulator"
    orig_peak_kw = float(load_series.peak_demand_kw)

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
                        Annual Energy: {load_series.total_energy_kwh:,.0f} kWh | Unmitigated Peak: {orig_peak_kw:,.1f} kW
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with c_reset:
            if st.button(":material/restart_alt: Reset Session", use_container_width=True, key=f"{key_prefix}_top_reset_btn"):
                keys_to_clear = [k for k in list(st.session_state.keys()) if k.startswith(key_prefix)]
                for k in keys_to_clear:
                    del st.session_state[k]
                st.rerun()

    # ----------------------------------------------------------------------------------
    # 2. Global Action Bar: Reference Case Loaders & Live Grid Connection Limit
    # ----------------------------------------------------------------------------------
    default_limit_kw = round(orig_peak_kw * 0.78, 0) if orig_peak_kw > 50.0 else 200.0
    if f"{key_prefix}_grid_limit_input" not in st.session_state:
        st.session_state[f"{key_prefix}_grid_limit_input"] = default_limit_kw

    with st.container(border=True):
        g_col1, g_col2, g_col3 = st.columns([1.45, 1.35, 1.2])
        with g_col1:
            st.markdown("##### :material/bolt: Contracted Grid Connection Limit ($P_{\\text{limit}}$)")
            grid_limit_kw = st.number_input(
                "Maximum Allowed Grid Import Power (kW):",
                min_value=10.0,
                max_value=50000.0,
                step=25.0,
                format="%.1f",
                key=f"{key_prefix}_grid_limit_input",
                help=(
                    "Central control threshold for BESS Peak Shaving. Any facility demand above this kW ceiling "
                    "must be shaved by direct Solar PV and/or BESS discharge."
                ),
            )
        with g_col2:
            st.markdown("##### :material/tune: Quick Grid Limit Presets (vs. Peak)")
            ql1, ql2, ql3 = st.columns(3)
            if ql1.button(
                f"80% Peak ({orig_peak_kw * 0.80:,.0f} kW)",
                use_container_width=True,
                key=f"{key_prefix}_ql_80",
            ):
                st.session_state[f"{key_prefix}_pending_grid_limit_kw"] = round(orig_peak_kw * 0.80, 0)
                st.rerun()
            if ql2.button(
                f"65% Peak ({orig_peak_kw * 0.65:,.0f} kW)",
                use_container_width=True,
                key=f"{key_prefix}_ql_65",
            ):
                st.session_state[f"{key_prefix}_pending_grid_limit_kw"] = round(orig_peak_kw * 0.65, 0)
                st.rerun()
            if ql3.button(
                f"50% Peak ({orig_peak_kw * 0.50:,.0f} kW)",
                use_container_width=True,
                key=f"{key_prefix}_ql_50",
            ):
                st.session_state[f"{key_prefix}_pending_grid_limit_kw"] = round(orig_peak_kw * 0.50, 0)
                st.rerun()
            shave_target_kw = max(0.0, orig_peak_kw - grid_limit_kw)
            st.caption(
                f"Unmitigated Facility Peak: **{orig_peak_kw:,.1f} kW** | "
                f"Required Total Peak Shaving: **{shave_target_kw:,.1f} kW** "
                f"(`-{shave_target_kw / max(1.0, orig_peak_kw) * 100.0:.1f}%`)"
            )
        with g_col3:
            st.markdown("##### :material/play_circle: Reference Hybrid Case Loaders")
            rc1, rc2 = st.columns(2)
            if rc1.button(
                "Mendoza Winery",
                icon=":material/wb_sunny:",
                use_container_width=True,
                key=f"{key_prefix}_ref_mendoza",
                help="Loads Bodegas Salentein (Mendoza): 270 kWp TOPCon PV + 500 kWh / 250 kW LFP BESS.",
            ):
                _load_reference_benchmark("mendoza", load_series, key_prefix)
            if rc2.button(
                "Rotterdam WKO",
                icon=":material/factory:",
                use_container_width=True,
                key=f"{key_prefix}_ref_rotterdam",
                help="Loads Rotterdam Commercial WKO: 153 kWp TOPCon PV + 300 kWh / 150 kW LFP BESS.",
            ):
                _load_reference_benchmark("rotterdam", load_series, key_prefix)
            st.caption("One-click setup for site coordinates, PV array, and BESS sizing.")

    # ----------------------------------------------------------------------------------
    # 3. 4-Tab Main Architecture
    # ----------------------------------------------------------------------------------
    tab1, tab2, tab3, tab4 = st.tabs(
        [
            ":material/analytics: Tab 1: Facility Load & Consumption Profile",
            ":material/solar_power: Tab 2: Solar PV Site, Sizing & Generation Baseline",
            ":material/battery_charging_full: Tab 3: BESS Sizing & Coupled Hybrid Dispatch",
            ":material/payments: Tab 4: Combined Plant Economics (CAPEX/OPEX/LCOE) & Master Contract",
        ]
    )

    # ==================================================================================
    # TAB 1: Facility Load & Consumption Profile (1:1 Reuse from Main Program)
    # ==================================================================================
    with tab1:
        st.markdown(
            """
            <div style="background: #0f172a; border-left: 4px solid #38bdf8; padding: 10px 16px; border-radius: 6px; margin-bottom: 12px;">
                <strong style="color:#f8fafc; font-size:0.95rem;">Consumption Baseline Workbench (35,040 Steps / 15-Minute Grid)</strong>
                <p style="color:#94a3b8; font-size:0.82rem; margin:2px 0 0 0;">
                    Switch seamlessly between real 15-minute CSV smart meter measurements and the synthetic 24h/365-day facility load simulator.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        render_tab1_consumption(key_prefix=f"{key_prefix}_tab1_cons")
        load_series, source_label = _get_or_create_active_load()

    # ==================================================================================
    # TAB 2: Solar PV Site, Sizing & Generation Baseline (Imported from Solar_sandbox)
    # ==================================================================================
    with tab2:
        st.markdown(
            """
            <div style="background: #0f172a; border-left: 4px solid #f59e0b; padding: 10px 16px; border-radius: 6px; margin-bottom: 14px;">
                <strong style="color:#f8fafc; font-size:0.95rem;">Solar PV Site, Array Sizing & BESS Charging Pool Foundation</strong>
                <p style="color:#94a3b8; font-size:0.82rem; margin:2px 0 0 0;">
                    Configure your geographic site, PV cell technology, and array sizing. Direct daytime self-consumption reduces facility load immediately,
                    while midday PV surplus forms the free charging energy pool for the BESS in Tab 3.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Section 1: Geographic Site & Irradiation
        location: SolarLocation = render_solar_location_section(key_prefix=f"{key_prefix}_loc")

        # Section 2: Technical PV Specification Form
        current_cfg: Optional[SolarPVConfig] = st.session_state.get(f"{key_prefix}_active_cfg")
        current_fin: Optional[SolarFinancialConfig] = st.session_state.get(f"{key_prefix}_active_fin")

        config, fin_config, submitted = render_solar_config_form(
            location=location,
            current_config=current_cfg,
            current_fin_config=current_fin,
            key_prefix=f"{key_prefix}_cfg",
        )
        st.session_state[f"{key_prefix}_active_cfg"] = config
        st.session_state[f"{key_prefix}_active_fin"] = fin_config

        # Execute or retrieve cached 35,040-step physical PV simulation
        auto_trigger = st.session_state.pop(f"{key_prefix}_trigger_calc", False)
        cached_res: Optional[SolarSimulationResult] = st.session_state.get(f"{key_prefix}_sim_result")

        valid_sizing = config.module_count > 0 and (config.dc_capacity_kwp or 0) > 0
        need_simulation = valid_sizing and (submitted or auto_trigger or cached_res is None)

        if need_simulation:
            with st.spinner("Simulating 15-minute physical Solar PV generation (35,040 intervals)..."):
                try:
                    sim_result: SolarSimulationResult = simulate_solar_pv_generation(
                        config=config,
                        location=location,
                    )
                    st.session_state[f"{key_prefix}_sim_result"] = sim_result
                    cached_res = sim_result
                except Exception as err:
                    st.error(f"Solar Simulation Error: {err}", icon=":material/error:")
                    return

        if cached_res is None:
            st.info(
                "Configure your Solar PV parameters above and click **Calculate Solar PV Generation** to initialize the hybrid model.",
                icon=":material/info:",
            )
            return

        # Couple Solar PV with active 35,040-step Facility Load
        load_df = pd.DataFrame({
            "timestamp": load_series.timestamps,
            "Total_Demand_kW": load_series.power_kw,
        })
        sim_res_coupled = couple_solar_simulation_with_load(
            solar_res=cached_res,
            load_df=load_df,
            gap_handling="bypass",
        )
        df_coupled = sim_res_coupled.df_timeseries
        kpis_coupled = sim_res_coupled.kpis
        p_solar_kw = df_coupled["P_AC_kW"].to_numpy(dtype=float)

        st.divider()

        # Section 3: Compact Solar Generation & BESS Charging Potential Preview (4 Bridge KPIs)
        st.subheader("3. Solar Generation Baseline & Free BESS Charging Pool")
        st.caption(
            "Summary of standalone Solar PV performance prior to battery storage. "
            "Card 4 (**Available PV Surplus for BESS**) quantifies the exact solar energy that would be exported or curtailed without a battery."
        )

        pv_surplus_pct = (
            kpis_coupled.surplus_generation_kwh / max(1.0, kpis_coupled.annual_energy_kwh) * 100.0
        )
        sk1, sk2, sk3, sk4 = st.columns(4)
        with sk1:
            render_kpi_card(
                "Annual Solar Yield",
                f"{kpis_coupled.annual_energy_kwh:,.0f} kWh",
                f"Array: {cached_res.config.dc_capacity_kwp:,.1f} kWp DC ({cached_res.config.module_count:,} panels)",
                status="ok",
            )
        with sk2:
            render_kpi_card(
                "Specific Yield",
                f"{kpis_coupled.specific_yield_kwh_per_kwp:,.1f} kWh/kWp",
                f"Full Load Hours: {kpis_coupled.full_load_hours:,.0f} h/a | Area: {cached_res.config.required_area_m2:,.0f} m²",
            )
        with sk3:
            render_kpi_card(
                "Direct PV Self-Consumption (No BESS)",
                f"{kpis_coupled.direct_consumption_kwh:,.0f} kWh",
                f"Standalone SCR: {kpis_coupled.self_consumption_rate_pct:.1f}% | Autarky: {kpis_coupled.solar_fraction_autarky_pct:.1f}%",
                status="ok",
            )
        with sk4:
            render_kpi_card(
                "Available PV Surplus for BESS",
                f"{kpis_coupled.surplus_generation_kwh:,.0f} kWh",
                f"{pv_surplus_pct:.1f}% of PV yield available as free BESS charging pool",
                status="warning" if pv_surplus_pct > 25.0 else "ok",
            )

        st.write("")

        # Section 4: Solar Generation Profile Timeseries (15-Minute Resolution)
        st.subheader("4. Solar Generation Profile Timeseries (15-Minute Resolution)")
        fig_sol_ts = create_solar_timeseries_figure(
            df=cached_res.df_timeseries,
            dc_capacity_kwp=cached_res.config.dc_capacity_kwp,
            inverter_capacity_kw=cached_res.config.inverter_capacity_kw,
        )
        st.plotly_chart(fig_sol_ts, use_container_width=True)

        with st.expander(":material/bar_chart: Monthly Energy Production & Physical Loss Waterfall", expanded=False):
            c_m, c_l = st.columns(2)
            with c_m:
                st.plotly_chart(
                    create_solar_monthly_bar_figure(
                        monthly_yields=cached_res.monthly_yields,
                        dc_capacity_kwp=cached_res.config.dc_capacity_kwp,
                    ),
                    use_container_width=True,
                )
            with c_l:
                st.plotly_chart(
                    create_solar_loss_waterfall_figure(loss_breakdown=cached_res.loss_breakdown),
                    use_container_width=True,
                )

        st.divider()

        # Section 5: Hockey-Stick 1-Click Auto-Sizing Presets (from Solar_sandbox)
        st.subheader("5. Hockey-Stick Auto-Sizing & Demand Coverage Curve")
        st.caption(
            "One-click PV array pre-dimensioning relative to your annual facility consumption from Tab 1. "
            "In a hybrid PV + BESS system, sizing PV at **60% to 100% Demand** intentionally generates midday surplus to charge the battery."
        )

        unit_pv_kw = p_solar_kw / max(0.1, cached_res.config.dc_capacity_kwp)
        spec_yield = float(kpis_coupled.specific_yield_kwh_per_kwp)
        df_hockey, presets_kwp = compute_solar_hockey_stick_curve(
            load=load_series,
            unit_pv_kw=unit_pv_kw,
            specific_yield_kwh_per_kwp=spec_yield,
        )

        hb1, hb2, hb3, hb4, hb5 = st.columns(5)
        if hb1.button(
            f"40% Demand ({presets_kwp['40_pct']:,.0f} kWp)",
            use_container_width=True,
            key=f"{key_prefix}_hs_40",
        ):
            _stage_solar_target_kwp(presets_kwp["40_pct"], cached_res, key_prefix)
        if hb2.button(
            f"Sweet-Spot 55% ({presets_kwp['sweet_spot']:,.0f} kWp)",
            use_container_width=True,
            key=f"{key_prefix}_hs_sweet",
            type="primary",
        ):
            _stage_solar_target_kwp(presets_kwp["sweet_spot"], cached_res, key_prefix)
        if hb3.button(
            f"60% Demand ({presets_kwp['60_pct']:,.0f} kWp)",
            use_container_width=True,
            key=f"{key_prefix}_hs_60",
        ):
            _stage_solar_target_kwp(presets_kwp["60_pct"], cached_res, key_prefix)
        if hb4.button(
            f"80% Demand ({presets_kwp['80_pct']:,.0f} kWp)",
            use_container_width=True,
            key=f"{key_prefix}_hs_80",
        ):
            _stage_solar_target_kwp(presets_kwp["80_pct"], cached_res, key_prefix)
        if hb5.button(
            f"100% Net-Zero ({presets_kwp['100_pct']:,.0f} kWp)",
            use_container_width=True,
            key=f"{key_prefix}_hs_100",
        ):
            _stage_solar_target_kwp(presets_kwp["100_pct"], cached_res, key_prefix)

        daylight_mask = p_solar_kw > 1.0
        daylight_demand_kwh = float(np.sum(load_series.power_kw[daylight_mask]) * 0.25)
        daylight_cov_pct = (
            (kpis_coupled.direct_consumption_kwh / daylight_demand_kwh * 100.0)
            if daylight_demand_kwh > 0
            else 0.0
        )

        fig_hockey = create_solar_hockey_stick_figure(
            df_curve=df_hockey,
            selected_kwp=cached_res.config.dc_capacity_kwp,
            selected_daylight_cov_pct=daylight_cov_pct,
            selected_scr_pct=kpis_coupled.self_consumption_rate_pct,
        )
        st.plotly_chart(fig_hockey, use_container_width=True)

    # ==================================================================================
    # TAB 3: BESS Sizing & Coupled Hybrid Dispatch (Core Hybrid Workbench)
    # ==================================================================================
    with tab3:
        st.markdown(
            """
            <div style="background: #0f172a; border-left: 4px solid #10b981; padding: 10px 16px; border-radius: 6px; margin-bottom: 14px;">
                <strong style="color:#f8fafc; font-size:0.95rem;">Coupled BESS Dimensioning & Double-Lever Hybrid Dispatch Engine</strong>
                <p style="color:#94a3b8; font-size:0.82rem; margin:2px 0 0 0;">
                    Diagnoses remaining post-solar grid overloads and daily midday PV surplus to size your battery storage system.
                    Compares Strict Peak-Shaving Priority (Strategy 1) against Double-Lever Self-Consumption + Peak Shaving (Strategy 2).
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Retrieve current BESS parameters for pre-dimensioning calculation
        cur_rte_pct = float(st.session_state.get(f"{key_prefix}_active_bess_rte", 88.0))
        cur_soc_min = float(st.session_state.get(f"{key_prefix}_active_bess_soc_min", 10.0))
        cur_soc_max = float(st.session_state.get(f"{key_prefix}_active_bess_soc_max", 90.0))

        pre_dim = compute_hybrid_bess_pre_dimensioning(
            load_kw=load_series.power_kw,
            pv_kw=p_solar_kw,
            grid_limit_kw=grid_limit_kw,
            rte_pct=cur_rte_pct,
            soc_min_pct=cur_soc_min,
            soc_max_pct=cur_soc_max,
        )

        # ------------------------------------------------------------------------------
        # A. Intelligent Battery Pre-Dimensioning ("What does the battery need to do?")
        # ------------------------------------------------------------------------------
        st.subheader("1. Intelligent Battery Pre-Dimensioning (Synergy of PV + Peak Shaving)")
        st.caption(
            f"Evaluates the **Post-Solar Net Load** ($P_{{\\text{{Load}}}} - P_{{\\text{{PV, Direct}}}}$) against your "
            f"**{grid_limit_kw:,.1f} kW** grid connection limit and the **{kpis_coupled.surplus_generation_kwh:,.0f} kWh/a** solar surplus pool."
        )

        pd1, pd2, pd3, pd4 = st.columns(4)
        with pd1:
            pv_peak_cut = max(0.0, pre_dim.original_peak_kw - pre_dim.post_solar_peak_kw)
            render_kpi_card(
                "Post-Solar Residual Peak",
                f"{pre_dim.post_solar_peak_kw:,.1f} kW",
                f"Original Peak: {pre_dim.original_peak_kw:,.1f} kW (PV cut -{pv_peak_cut:.1f} kW)",
                status="ok" if pre_dim.post_solar_peak_kw <= grid_limit_kw else "warning",
            )
        with pd2:
            render_kpi_card(
                "Remaining Peak Overload",
                f"{pre_dim.remaining_overload_kw:,.1f} kW",
                f"{pre_dim.remaining_overload_hours:,.2f} hrs/a ({pre_dim.remaining_overload_events} events) > {grid_limit_kw:,.0f} kW",
                status="warning" if pre_dim.remaining_overload_kw > 0.1 else "ok",
            )
        with pd3:
            render_kpi_card(
                "Worst Single-Event Energy",
                f"{pre_dim.max_single_event_overload_kwh:,.1f} kWh",
                f"Total annual overload energy: {pre_dim.remaining_overload_energy_kwh:,.0f} kWh",
            )
        with pd4:
            render_kpi_card(
                "Daily PV Surplus Pool",
                f"{pre_dim.avg_sunny_day_surplus_kwh:,.1f} kWh/d",
                f"P75 Sunny Day: {pre_dim.p75_sunny_day_surplus_kwh:,.1f} kWh/d ({pre_dim.sunny_surplus_days_count} days/a)",
                status="ok",
            )

        st.write("")
        with st.expander(
            ":material/auto_awesome: One-Click BESS Dimensioning Recommendations (Tier 1: Peak-Shaving, Tier 2: Solar Buffer, Tier 3: Optimum)",
            expanded=False,
        ):
            tier_col1, tier_col2, tier_col3 = st.columns(3)

            STRAT_1_LABEL = "Strategy 1: Strict Peak-Shaving Priority (Cap Grid <= Limit)"
            STRAT_2_LABEL = "Strategy 2: Double-Lever (Max Self-Consumption + Peak-Shaving Reserve)"

            with tier_col1:
                with st.container(border=True):
                    st.markdown(
                        """
                        <div style="border-left: 3px solid #38bdf8; padding-left: 10px; margin-bottom: 8px;">
                            <strong style="color:#f8fafc; font-size:0.92rem;">Tier 1: Peak-Shaving Focus (100% Zero-Breach)</strong>
                            <div style="color:#94a3b8; font-size:0.78rem;">Sized strictly to eliminate all remaining post-solar grid breaches above P_limit</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        f"**Recommended BESS:** `{pre_dim.rec_peak_kwh:,.0f} kWh` / `{pre_dim.rec_peak_kw:,.0f} kW` "
                        f"*(C-Rate: {pre_dim.rec_peak_kw / max(1.0, pre_dim.rec_peak_kwh):.2f}C)*"
                    )
                    if st.button(
                        f":material/bolt: Apply Tier 1 ({pre_dim.rec_peak_kwh:,.0f} kWh / {pre_dim.rec_peak_kw:,.0f} kW)",
                        use_container_width=True,
                        key=f"{key_prefix}_btn_tier1",
                    ):
                        _stage_bess_sizing(pre_dim.rec_peak_kwh, pre_dim.rec_peak_kw, key_prefix, STRAT_1_LABEL)

            with tier_col2:
                with st.container(border=True):
                    st.markdown(
                        """
                        <div style="border-left: 3px solid #f59e0b; padding-left: 10px; margin-bottom: 8px;">
                            <strong style="color:#f8fafc; font-size:0.92rem;">Tier 2: Self-Consumption Focus (Solar Buffer)</strong>
                            <div style="color:#94a3b8; font-size:0.78rem;">Sized to absorb P75 midday PV surplus and shift it into evening/night hours</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        f"**Recommended BESS:** `{pre_dim.rec_solar_kwh:,.0f} kWh` / `{pre_dim.rec_solar_kw:,.0f} kW` "
                        f"*(C-Rate: {pre_dim.rec_solar_kw / max(1.0, pre_dim.rec_solar_kwh):.2f}C)*"
                    )
                    if st.button(
                        f":material/wb_sunny: Apply Tier 2 ({pre_dim.rec_solar_kwh:,.0f} kWh / {pre_dim.rec_solar_kw:,.0f} kW)",
                        use_container_width=True,
                        key=f"{key_prefix}_btn_tier2",
                    ):
                        _stage_bess_sizing(pre_dim.rec_solar_kwh, pre_dim.rec_solar_kw, key_prefix, STRAT_2_LABEL)

            with tier_col3:
                with st.container(border=True):
                    st.markdown(
                        """
                        <div style="border-left: 3px solid #10b981; padding-left: 10px; margin-bottom: 8px;">
                            <strong style="color:#f8fafc; font-size:0.92rem;">Tier 3: Double-Lever Optimum (Peak + Solar Cycle)</strong>
                            <div style="color:#94a3b8; font-size:0.78rem;">Combines peak-shaving reserve with daily solar shifting for maximum synergy</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        f"**Recommended BESS:** `{pre_dim.rec_hybrid_kwh:,.0f} kWh` / `{pre_dim.rec_hybrid_kw:,.0f} kW` "
                        f"*(C-Rate: {pre_dim.rec_hybrid_kw / max(1.0, pre_dim.rec_hybrid_kwh):.2f}C)*"
                    )
                    if st.button(
                        f":material/stars: Apply Tier 3 ({pre_dim.rec_hybrid_kwh:,.0f} kWh / {pre_dim.rec_hybrid_kw:,.0f} kW)",
                        type="primary",
                        use_container_width=True,
                        key=f"{key_prefix}_btn_tier3",
                    ):
                        _stage_bess_sizing(pre_dim.rec_hybrid_kwh, pre_dim.rec_hybrid_kw, key_prefix, STRAT_2_LABEL)

        st.divider()

        # ------------------------------------------------------------------------------
        # B. BESS Hardware & Coupled Operational Strategy Form (st.form)
        # ------------------------------------------------------------------------------
        st.subheader("2. BESS Hardware & Coupled Dispatch Strategy Configuration")

        if f"{key_prefix}_bess_form_kwh" not in st.session_state:
            st.session_state[f"{key_prefix}_bess_form_kwh"] = float(
                st.session_state.get(f"{key_prefix}_active_bess_kwh", pre_dim.rec_hybrid_kwh)
            )
        if f"{key_prefix}_bess_form_kw" not in st.session_state:
            st.session_state[f"{key_prefix}_bess_form_kw"] = float(
                st.session_state.get(f"{key_prefix}_active_bess_kw", pre_dim.rec_hybrid_kw)
            )
        if f"{key_prefix}_bess_form_strategy" not in st.session_state:
            st.session_state[f"{key_prefix}_bess_form_strategy"] = STRAT_2_LABEL

        with st.form(key=f"{key_prefix}_bess_dispatch_form", clear_on_submit=False):
            bf1, bf2, bf3, bf4 = st.columns(4)
            with bf1:
                bess_kwh_in = st.number_input(
                    "Nominal BESS Capacity (kWh):",
                    min_value=10.0,
                    max_value=100000.0,
                    step=25.0,
                    format="%.0f",
                    key=f"{key_prefix}_bess_form_kwh",
                    help="Installed battery energy storage capacity in kWh.",
                )
            with bf2:
                bess_kw_in = st.number_input(
                    "Inverter / PCS Power Rating (kW):",
                    min_value=5.0,
                    max_value=50000.0,
                    step=10.0,
                    format="%.0f",
                    key=f"{key_prefix}_bess_form_kw",
                    help="Maximum continuous charge and discharge active power in kW.",
                )
            with bf3:
                chem_choice = st.selectbox(
                    "Battery Cell Chemistry:",
                    options=[
                        "LFP (LiFePO4 - High Cycle Life, 6,000+ Cycles)",
                        "NMC (Lithium Nickel Manganese Cobalt - High C-Rate)",
                    ],
                    index=0,
                    key=f"{key_prefix}_bess_form_chem",
                )
            with bf4:
                rte_in = st.number_input(
                    "Round-Trip Efficiency RTE (%):",
                    min_value=70.0,
                    max_value=98.0,
                    value=cur_rte_pct,
                    step=0.5,
                    format="%.1f",
                    key=f"{key_prefix}_bess_form_rte",
                    help="Full AC-to-AC round-trip efficiency including inverter and cell losses.",
                )

            bs1, bs2, bs3, bs4 = st.columns([1.8, 0.7, 0.7, 0.8])
            with bs1:
                strat_choice = st.selectbox(
                    "Active Coupled EMS Dispatch Strategy:",
                    options=[STRAT_2_LABEL, STRAT_1_LABEL],
                    key=f"{key_prefix}_bess_form_strategy",
                    help=(
                        "Strategy 2 (Double-Lever) cycles midday solar surplus to displace evening/night load while "
                        "maintaining a dynamic peak-shaving reserve. Strategy 1 reserves the battery strictly for peak clipping."
                    ),
                )
            with bs2:
                soc_min_in = st.number_input(
                    "Min SoC Floor (%):",
                    min_value=0.0,
                    max_value=40.0,
                    value=cur_soc_min,
                    step=5.0,
                    format="%.0f",
                    key=f"{key_prefix}_bess_form_soc_min",
                )
            with bs3:
                soc_max_in = st.number_input(
                    "Max SoC Ceiling (%):",
                    min_value=60.0,
                    max_value=100.0,
                    value=cur_soc_max,
                    step=5.0,
                    format="%.0f",
                    key=f"{key_prefix}_bess_form_soc_max",
                )
            with bs4:
                peak_res_in = st.number_input(
                    "Peak Reserve SoC (%):",
                    min_value=0.0,
                    max_value=80.0,
                    value=25.0,
                    step=5.0,
                    format="%.0f",
                    key=f"{key_prefix}_bess_form_peak_res",
                    help="In Strategy 2 (Double-Lever), percentage of usable window reserved exclusively for peak shaving above P_limit.",
                )

            allow_grid_chg_in = st.checkbox(
                "Allow Preventive Grid Recharging (within Grid Limit headroom) to maintain Peak-Shaving Reserve SoC during winter/cloudy periods",
                value=True,
                key=f"{key_prefix}_bess_form_allow_grid",
            )

            bess_submitted = st.form_submit_button(
                "Run Coupled Hybrid Solar + BESS Simulation",
                icon=":material/play_arrow:",
                type="primary",
                use_container_width=True,
            )

        if bess_submitted:
            st.session_state[f"{key_prefix}_active_bess_kwh"] = bess_kwh_in
            st.session_state[f"{key_prefix}_active_bess_kw"] = bess_kw_in
            st.session_state[f"{key_prefix}_active_bess_rte"] = rte_in
            st.session_state[f"{key_prefix}_active_bess_soc_min"] = soc_min_in
            st.session_state[f"{key_prefix}_active_bess_soc_max"] = soc_max_in
            st.session_state[f"{key_prefix}_active_bess_strategy"] = strat_choice

        active_bess_kwh = float(st.session_state.get(f"{key_prefix}_active_bess_kwh", bess_kwh_in))
        active_bess_kw = float(st.session_state.get(f"{key_prefix}_active_bess_kw", bess_kw_in))
        active_rte = float(st.session_state.get(f"{key_prefix}_active_bess_rte", rte_in))
        active_soc_min = float(st.session_state.get(f"{key_prefix}_active_bess_soc_min", soc_min_in))
        active_soc_max = float(st.session_state.get(f"{key_prefix}_active_bess_soc_max", soc_max_in))
        active_strat_label = str(st.session_state.get(f"{key_prefix}_active_bess_strategy", strat_choice))
        active_strategy_code = (
            "peak_shaving_priority" if "Strategy 1" in active_strat_label else "hybrid_self_cons_and_peak"
        )

        # ------------------------------------------------------------------------------
        # C. Dual-Strategy Simulation & Side-by-Side Comparison Table + 8 KPIs
        # ------------------------------------------------------------------------------
        dual_sim = simulate_dual_strategies_comparison(
            timestamps=load_series.timestamps,
            load_kw=load_series.power_kw,
            pv_kw=p_solar_kw,
            bess_capacity_kwh=active_bess_kwh,
            bess_power_kw=active_bess_kw,
            grid_limit_kw=grid_limit_kw,
            soc_min_pct=active_soc_min,
            soc_max_pct=active_soc_max,
            rte_pct=active_rte,
            peak_reserve_soc_pct=float(peak_res_in),
            allow_grid_recharge=bool(allow_grid_chg_in),
        )

        active_sim = dual_sim[active_strategy_code]
        df_hyb = active_sim["df_timeseries"]
        hyb_kpis = active_sim["kpis"]
        df_strat_comp = dual_sim["comparison_df"]

        st.subheader("3. Coupled Dispatch Performance & Strategy Comparison")
        active_badge_txt = (
            "Strategy 1: Strict Peak-Shaving Priority"
            if active_strategy_code == "peak_shaving_priority"
            else "Strategy 2: Double-Lever (Max Self-Consumption + Peak-Shaving Reserve)"
        )
        st.info(
            f"**Active Hardware:** `{cached_res.config.dc_capacity_kwp:,.1f} kWp PV` + "
            f"`{active_bess_kwh:,.0f} kWh / {active_bess_kw:,.0f} kW BESS` | "
            f"**Grid Limit:** `{grid_limit_kw:,.1f} kW` | **Active EMS Mode:** `{active_badge_txt}`",
            icon=":material/electric_bolt:",
        )

        # 8 Executive Hybrid KPI Cards (2 rows of 4)
        hk1, hk2, hk3, hk4 = st.columns(4)
        with hk1:
            scr_gain = hyb_kpis.self_consumption_rate_pct - kpis_coupled.self_consumption_rate_pct
            render_kpi_card(
                "Combined Self-Consumption (SCR)",
                f"{hyb_kpis.self_consumption_rate_pct:.1f} %",
                f"Standalone PV: {kpis_coupled.self_consumption_rate_pct:.1f}% (+{scr_gain:.1f}% via BESS)",
                status="ok",
            )
        with hk2:
            aut_gain = hyb_kpis.autarky_rate_pct - kpis_coupled.solar_fraction_autarky_pct
            render_kpi_card(
                "Total Facility Autarky",
                f"{hyb_kpis.autarky_rate_pct:.1f} %",
                f"Standalone PV: {kpis_coupled.solar_fraction_autarky_pct:.1f}% (+{aut_gain:.1f}% via BESS)",
                status="ok",
            )
        with hk3:
            is_capped = hyb_kpis.new_grid_peak_kw <= grid_limit_kw + 0.5
            render_kpi_card(
                "New Grid Peak Demand",
                f"{hyb_kpis.new_grid_peak_kw:,.1f} kW",
                f"Shaved -{hyb_kpis.peak_shaved_kw:,.1f} kW (-{hyb_kpis.peak_shaved_pct:.1f}%) vs. {hyb_kpis.original_peak_kw:,.1f} kW",
                status="ok" if is_capped else "warning",
            )
        with hk4:
            render_kpi_card(
                "Eliminated Overload Hours",
                f"{hyb_kpis.eliminated_overload_pct:.1f} %",
                f"Remaining > {grid_limit_kw:,.0f} kW: {hyb_kpis.overload_hours_after:.2f} h/a (was {hyb_kpis.overload_hours_before:.2f} h/a)",
                status="ok" if hyb_kpis.overload_hours_after <= 0.01 else "warning",
            )

        hk5, hk6, hk7, hk8 = st.columns(4)
        with hk5:
            render_kpi_card(
                "BESS Charged from PV Surplus",
                f"{hyb_kpis.bess_charged_pv_kwh / 1000.0:,.2f} MWh",
                f"{hyb_kpis.green_charging_share_pct:.1f}% of total BESS charging is green solar",
                status="ok",
            )
        with hk6:
            render_kpi_card(
                "BESS Charged from Grid",
                f"{hyb_kpis.bess_charged_grid_kwh / 1000.0:,.2f} MWh",
                "Off-peak preventive reserve recharging within grid limit",
            )
        with hk7:
            render_kpi_card(
                "Equivalent Full Cycles (EFC)",
                f"{hyb_kpis.equivalent_full_cycles:.1f} cycles/a",
                f"Discharged: {hyb_kpis.bess_discharged_kwh / 1000.0:,.1f} MWh/a | Losses: {hyb_kpis.bess_losses_kwh / 1000.0:,.1f} MWh/a",
            )
        with hk8:
            render_kpi_card(
                "Residual Grid Import",
                f"{hyb_kpis.grid_import_kwh / 1000.0:,.1f} MWh",
                f"Remaining PV Export: {hyb_kpis.grid_export_kwh / 1000.0:,.1f} MWh/a",
            )

        st.write("")
        with st.expander(":material/compare: Direct Strategy Comparison Table (Strategy 1 vs. Strategy 2 on Identical Hardware)", expanded=True):
            st.caption(
                "Side-by-side comparison on your current PV + BESS hardware showing how **Strategy 1 (Strict Peak-Shaving Priority)** "
                "and **Strategy 2 (Double-Lever Hybrid)** trade off peak reserve margin against daily solar cycle utilization."
            )
            st.dataframe(df_strat_comp, use_container_width=True, hide_index=True)

        st.divider()

        # ------------------------------------------------------------------------------
        # D. 4 Visual Dispatch Analysis Sub-Tabs
        # ------------------------------------------------------------------------------
        st.subheader("4. Interactive Hybrid Dispatch & Synergy Visualizations")
        vtab1, vtab2, vtab3, vtab4 = st.tabs(
            [
                ":material/timeline: 2-in-1 Synchronized Dispatch & SoC",
                ":material/bar_chart: Monthly Energy Balance",
                ":material/schema: Hybrid Energy Flow (Sankey)",
                ":material/compare_arrows: Synergy Benchmark (PV vs. BESS vs. Hybrid)",
            ]
        )

        with vtab1:
            c_tog1, c_tog2 = st.columns([1.4, 2.6])
            with c_tog1:
                focus_peak_wk = st.checkbox(
                    "Zoom to Peak Demand Week (7-Day Stress Window)",
                    value=False,
                    key=f"{key_prefix}_zoom_peak_wk",
                )
            with c_tog2:
                st.caption(
                    "Use the top-left `7D`, `1M`, `3M`, `All` buttons or drag the bottom range slider. "
                    "Top chart shows 15-minute active power dispatch (kW); bottom chart shows synchronized Battery SoC (%)."
                )
            fig_sync = create_hybrid_synchronized_dispatch_soc_figure(
                df_ts=df_hyb,
                grid_limit_kw=grid_limit_kw,
                bess_capacity_kwh=active_bess_kwh,
                bess_power_kw=active_bess_kw,
                pv_kwp=cached_res.config.dc_capacity_kwp,
                soc_min_pct=active_soc_min,
                soc_max_pct=active_soc_max,
                focus_peak_week=focus_peak_wk,
            )
            st.plotly_chart(fig_sync, use_container_width=True)

        with vtab2:
            fig_mon = create_hybrid_monthly_balance_figure(df_ts=df_hyb)
            st.plotly_chart(fig_mon, use_container_width=True)

        with vtab3:
            fig_sankey = create_hybrid_sankey_figure(kpis=hyb_kpis)
            st.plotly_chart(fig_sankey, use_container_width=True)

        with vtab4:
            st.caption(
                "Demonstrates the **Double-Lever Synergy**: Standalone Solar PV reduces volumetric kWh import but leaves winter/evening peaks unclipped; "
                "Standalone BESS clips peaks using grid power but generates zero clean kWh; **Hybrid PV + BESS** combines both levers."
            )
            df_synergy = compute_synergy_comparison_metrics(
                timestamps=load_series.timestamps,
                load_kw=load_series.power_kw,
                pv_kw=p_solar_kw,
                bess_capacity_kwh=active_bess_kwh,
                bess_power_kw=active_bess_kw,
                grid_limit_kw=grid_limit_kw,
                soc_min_pct=active_soc_min,
                soc_max_pct=active_soc_max,
                rte_pct=active_rte,
            )
            fig_syn = create_hybrid_synergy_comparison_figure(df_synergy=df_synergy, grid_limit_kw=grid_limit_kw)
            st.plotly_chart(fig_syn, use_container_width=True)
            st.dataframe(df_synergy, use_container_width=True, hide_index=True)

    # ==================================================================================
    # TAB 4: Combined Plant Economics (CAPEX, OPEX & LCOE) & Master Integration Contract
    # ==================================================================================
    with tab4:
        st.markdown(
            """
            <div style="background: #0f172a; border-left: 4px solid #8b5cf6; padding: 10px 16px; border-radius: 6px; margin-bottom: 14px;">
                <strong style="color:#f8fafc; font-size:0.95rem;">Combined Hybrid Plant Economics (Turnkey CAPEX, OPEX, Augmentation & LCOE)</strong>
                <p style="color:#94a3b8; font-size:0.82rem; margin:2px 0 0 0;">
                    Evaluates pure combined plant investment costs, 15-year O&M, mid-life BESS augmentation, and discounted Hybrid LCOE (EUR/kWh of clean on-site energy),
                    plus exports the standardized Master Integration Data Contract for Phase 2 4-Pillar tariff billing.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.subheader("1. Combined Turnkey Cost & 15-Year Lifecycle Parameters")
        with st.form(key=f"{key_prefix}_hybrid_fin_form", clear_on_submit=False):
            fc1, fc2, fc3, fc4 = st.columns(4)
            with fc1:
                pv_eur_kwp = st.number_input(
                    "Solar PV Turnkey CAPEX (EUR/kWp):",
                    min_value=100.0,
                    max_value=5000.0,
                    value=950.0,
                    step=25.0,
                    format="%.0f",
                    help="All-in turnkey Solar PV cost per kWp DC (modules, inverters, mounting, installation).",
                )
                pv_om_pct = st.number_input(
                    "Solar Annual O&M (% of PV CAPEX/a):",
                    min_value=0.0,
                    max_value=10.0,
                    value=1.2,
                    step=0.1,
                    format="%.1f",
                )
            with fc2:
                bess_eur_kwh = st.number_input(
                    "BESS Storage Racks (EUR/kWh):",
                    min_value=50.0,
                    max_value=2000.0,
                    value=320.0,
                    step=10.0,
                    format="%.0f",
                    help="Specific cost of battery racks, BMS, and thermal enclosure per kWh.",
                )
                bess_om_pct = st.number_input(
                    "BESS Annual O&M (% of BESS CAPEX/a):",
                    min_value=0.0,
                    max_value=10.0,
                    value=1.5,
                    step=0.1,
                    format="%.1f",
                )
            with fc3:
                bess_eur_kw = st.number_input(
                    "BESS Hybrid PCS / Inverter (EUR/kW):",
                    min_value=0.0,
                    max_value=1500.0,
                    value=150.0,
                    step=10.0,
                    format="%.0f",
                    help="Specific cost of bidirectional power conversion system (PCS) per kW.",
                )
                bop_fixed_eur = st.number_input(
                    "Fixed Hybrid EMS / Switchgear BoP (EUR):",
                    min_value=0.0,
                    max_value=500000.0,
                    value=15000.0,
                    step=2500.0,
                    format="%.0f",
                )
            with fc4:
                disc_rate_pct = st.number_input(
                    "Real Discount Rate / WACC (%/a):",
                    min_value=0.0,
                    max_value=20.0,
                    value=6.0,
                    step=0.5,
                    format="%.1f",
                )
                aug_pct = st.number_input(
                    "Year 11 Cell Augmentation (% of Rack CAPEX):",
                    min_value=0.0,
                    max_value=100.0,
                    value=30.0,
                    step=5.0,
                    format="%.0f",
                    help="Mid-life battery cell augmentation or replacement reserve in Year 11.",
                )

            include_aug = st.checkbox(
                "Include Mid-Life BESS Cell Augmentation Reserve in Year 11 Cashflow & LCOE",
                value=True,
                key=f"{key_prefix}_fin_inc_aug",
            )
            st.form_submit_button(
                "Update Combined Plant Financials & LCOE",
                icon=":material/calculate:",
                type="primary",
                use_container_width=True,
            )

        fin_res = compute_hybrid_plant_financials(
            pv_kwp=cached_res.config.dc_capacity_kwp,
            bess_capacity_kwh=active_bess_kwh,
            bess_power_kw=active_bess_kw,
            kpis=hyb_kpis,
            pv_capex_eur_per_kwp=pv_eur_kwp,
            bess_energy_cost_eur_per_kwh=bess_eur_kwh,
            bess_power_cost_eur_per_kw=bess_eur_kw,
            bess_fixed_bop_eur=bop_fixed_eur,
            pv_om_pct_pa=pv_om_pct,
            bess_om_pct_pa=bess_om_pct,
            include_augmentation=include_aug,
            augmentation_year=11,
            augmentation_share_of_energy_capex_pct=aug_pct,
            discount_rate_pct=disc_rate_pct,
            project_lifetime_years=15,
            currency="EUR",
        )

        st.subheader("2. Combined Hybrid Investment & Levelized Cost KPIs")
        fk1, fk2, fk3, fk4 = st.columns(4)
        with fk1:
            render_kpi_card(
                "Combined Total CAPEX",
                f"{fin_res.total_combined_capex:,.0f} {fin_res.currency}",
                f"Solar PV: {fin_res.pv_share_pct:.1f}% ({fin_res.pv_total_capex:,.0f} EUR) | BESS: {fin_res.bess_share_pct:.1f}% ({fin_res.bess_total_capex:,.0f} EUR)",
                status="ok",
            )
        with fk2:
            render_kpi_card(
                "Combined Annual OPEX",
                f"{fin_res.total_annual_opex_year1:,.0f} {fin_res.currency}/a",
                f"PV O&M: {fin_res.pv_annual_opex:,.0f} EUR/a + BESS O&M: {fin_res.bess_annual_opex:,.0f} EUR/a",
            )
        with fk3:
            render_kpi_card(
                "Discounted Hybrid LCOE",
                f"{fin_res.discounted_lcoe_per_kwh:.4f} {fin_res.currency}/kWh",
                f"15Y NPV Cost: {fin_res.npv_total_lifecycle_cost:,.0f} EUR | Clean On-Site: {fin_res.lifetime_clean_energy_delivered_kwh / 1000.0:,.0f} MWh",
                status="ok",
            )
        with fk4:
            shaved_str = (
                f"{fin_res.specific_capex_per_shaved_kw:,.0f} {fin_res.currency}/kW"
                if fin_res.specific_capex_per_shaved_kw > 0
                else "N/A (0 kW shaved)"
            )
            render_kpi_card(
                "Specific Cost per Shaved kW",
                shaved_str,
                f"Shaved Peak: -{hyb_kpis.peak_shaved_kw:,.1f} kW | Total 15Y Solar Gen: {fin_res.lifetime_total_solar_kwh / 1000.0:,.0f} MWh",
            )

        st.write("")
        st.subheader("3. Turnkey Cost Breakdown & 15-Year Plant Outflow Schedule")
        ch_left, ch_right = st.columns([1.05, 1.35])
        with ch_left:
            st.plotly_chart(create_hybrid_capex_donut_figure(fin_res), use_container_width=True)
        with ch_right:
            st.plotly_chart(create_hybrid_15y_outflow_figure(fin_res), use_container_width=True)

        with st.expander(":material/table_chart: Detailed 15-Year Plant Expenditure & Clean Energy Ledger", expanded=False):
            st.dataframe(fin_res.df_yearly, use_container_width=True, hide_index=True)

        st.divider()

        # ------------------------------------------------------------------------------
        # 4. Standardized Session State Output Contract for Master Integration
        # ------------------------------------------------------------------------------
        st.subheader("4. Master Integration Data Contract (Phase 2 Billing Readiness)")
        st.caption(
            "Stores the 35,040-step coupled hybrid residual grid load array `residual_power_kw` and combined plant financials in "
            "`st.session_state['solar_bess_standalone_result']` so the Master 4-Pillar Billing Engine can price the exact tariff savings."
        )

        st.session_state["solar_bess_standalone_result"] = {
            "scenario": "hybrid_solar_bess",
            "load_series": load_series,
            "residual_power_kw": df_hyb["P_Grid_Import_kW"].to_numpy(dtype=float),
            "p_solar_kw": df_hyb["P_PV_kW"].to_numpy(dtype=float),
            "p_direct_kw": df_hyb["P_Direct_PV_kW"].to_numpy(dtype=float),
            "p_bess_charge_kw": df_hyb["P_BESS_Charge_Total_kW"].to_numpy(dtype=float),
            "p_bess_discharge_kw": df_hyb["P_BESS_Discharge_kW"].to_numpy(dtype=float),
            "p_export_kw": df_hyb["P_Grid_Export_kW"].to_numpy(dtype=float),
            "soc_pct": df_hyb["SoC_pct"].to_numpy(dtype=float),
            "pv_kwp": cached_res.config.dc_capacity_kwp,
            "bess_capacity_kwh": active_bess_kwh,
            "bess_power_kw": active_bess_kw,
            "grid_limit_kw": grid_limit_kw,
            "strategy": active_strategy_code,
            "total_capex": fin_res.total_combined_capex,
            "pv_capex": fin_res.pv_total_capex,
            "bess_capex": fin_res.bess_total_capex,
            "annual_om_year1": fin_res.total_annual_opex_year1,
            "discounted_lcoe_eur_per_kwh": fin_res.discounted_lcoe_per_kwh,
            "currency_code": fin_res.currency,
        }

        contract_summary = {
            "scenario": "hybrid_solar_bess_standalone",
            "site_name": location.name,
            "installed_pv_kwp": round(cached_res.config.dc_capacity_kwp, 2),
            "bess_capacity_kwh": round(active_bess_kwh, 1),
            "bess_power_kw": round(active_bess_kw, 1),
            "contracted_grid_limit_kw": round(grid_limit_kw, 1),
            "active_ems_strategy": active_strategy_code,
            "annual_load_kwh": round(hyb_kpis.total_load_kwh, 1),
            "annual_pv_generation_kwh": round(hyb_kpis.total_pv_kwh, 1),
            "direct_pv_consumption_kwh": round(hyb_kpis.direct_pv_kwh, 1),
            "bess_charged_from_pv_kwh": round(hyb_kpis.bess_charged_pv_kwh, 1),
            "bess_charged_from_grid_kwh": round(hyb_kpis.bess_charged_grid_kwh, 1),
            "bess_discharged_kwh": round(hyb_kpis.bess_discharged_kwh, 1),
            "residual_grid_import_kwh": round(hyb_kpis.grid_import_kwh, 1),
            "remaining_grid_export_kwh": round(hyb_kpis.grid_export_kwh, 1),
            "combined_self_consumption_rate_pct": round(hyb_kpis.self_consumption_rate_pct, 2),
            "combined_autarky_rate_pct": round(hyb_kpis.autarky_rate_pct, 2),
            "original_peak_kw": round(hyb_kpis.original_peak_kw, 2),
            "new_grid_peak_kw": round(hyb_kpis.new_grid_peak_kw, 2),
            "peak_shaved_kw": round(hyb_kpis.peak_shaved_kw, 2),
            "equivalent_full_cycles_pa": round(hyb_kpis.equivalent_full_cycles, 2),
            "combined_total_capex_eur": round(fin_res.total_combined_capex, 2),
            "combined_annual_opex_eur": round(fin_res.total_annual_opex_year1, 2),
            "discounted_hybrid_lcoe_eur_per_kwh": round(fin_res.discounted_lcoe_per_kwh, 5),
        }

        with st.expander(":material/integration_instructions: View & Export Master Integration JSON Payload", expanded=False):
            st.json(contract_summary)
            st.download_button(
                label=":material/download: Download Hybrid Solar + BESS Plant Summary (.json)",
                data=json.dumps(contract_summary, indent=2).encode("utf-8"),
                file_name=(
                    f"hybrid_pv_{cached_res.config.dc_capacity_kwp:.0f}kWp_"
                    f"bess_{active_bess_kwh:.0f}kWh_summary.json"
                ),
                mime="application/json",
                key=f"{key_prefix}_dl_hybrid_json",
            )


def main() -> None:
    render_solar_bess_sandbox(key_prefix="hyb_sb")


if __name__ == "__main__":
    main()
