"""
========================================================================================
Scenario 6: Standalone Generator & Grid Congestion Sandbox (ui_sandbox/Generator_sandbox/app.py)
========================================================================================

Standalone Execution:
    python -m streamlit run "ui_sandbox/Generator_sandbox/app.py"

Architecture (1:1 with Main Program UI & Component Architecture):
  - Top Header Status Banner: Active Load Source, Step count, Session Reset.
  - Action Controls Bar: Load Example Case (Liander 400 kW Grid Congestion Benchmark) & Reset / Clear Generator.
  - Tab 1: Facility Load & Consumption Profile (1:1 from Currentsituation_sandbox / Main App)
      * Real CSV Smart Meter Ingestion & Synthetic 24h/365d Load Simulator
      * 35,040-step 15-min interactive profile, Load Duration Curve (LDC), and 4 Base KPIs
  - Tab 2: Standalone Generator Sizing & Fuel Economics (1:1 with ui/tab_generator/view.py)
      * 1. Diagnostic Status Cards (Facility Peak Demand, Contracted Grid Limit, Overload Status, Configured Capacity)
      * 2. Generator Technical & Commercial Sizing Form (Model Presets, Rated kW, Fuel Curve, Wet-Stacking, Rental vs. CAPEX)
      * Primary action button: Run Generator Simulation & Dispatch
      * 3. Executive KPI Results Cards (Shaved Peak Demand, Runtime hrs & Starts, Fuel OPEX, Net Annual Impact)
      * 4. Consolidated Visual Dispatch & Financial Analysis Suite (4 Sub-Tabs):
          - Subtab 1: 15-Minute Dispatch Timeseries (with 7D, 1M, 3M, All zoom & range slider)
          - Subtab 2: Monthly Generation & Fuel Breakdown (12-month dual-axis chart)
          - Subtab 3: Energy Flow Sankey Diagram
          - Subtab 4: Commercial Zahlungsreihe & Amortization Trajectory + Ledger Table
  - Tab 3: Ideal Peaker Dimensioning & Sizing Optimizer ("The Perfect Generator")
      * 1. Coupled Performance Metrics: 8 KPI cards
      * 2. "The Perfect Generator" Diagnostic Blueprint (Unconstrained Sizing Analysis):
          - 4 Diagnostic KPI Cards (Peak Overload kW, Overload Energy MWh, Continuous Run hrs, Safe Fuel Tank Autonomy)
          - Wet-stacking risk alert (<25% minimum engine loading)
          - 3 Sizing Tiers with 1-Click Sync to Tab 2 Form (100% Zero-Breach, 80% Sweet Spot, 50% Peak-Assist)
      * 3. Parametric Capacity Sweep Curve & Tradeoff Analysis
      * 4. Standardized Master Integration Data Contract (residual_power_kw + JSON export)
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
    from models.generator import GeneratorConfig, GeneratorKPIs, get_generator_presets
    from models.contract import Contract
    from core.dracbv_engine import simulate_generator_peaking
    from ui.tab_generator.charts import (
        create_generator_multi_asset_dispatch_chart,
        create_cumulative_payment_chart,
    )
    from ui.common.cards import render_kpi_card
    from ui.common.styles import apply_custom_styles
except ImportError:
    from current_model.models.generator import GeneratorConfig, GeneratorKPIs, get_generator_presets
    from current_model.models.contract import Contract
    from current_model.core.dracbv_engine import simulate_generator_peaking
    from current_model.ui.tab_generator.charts import (
        create_generator_multi_asset_dispatch_chart,
        create_cumulative_payment_chart,
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

from ui_sandbox.Generator_sandbox.generator_sandbox_engine import (
    IdealGeneratorSizingResult,
    compute_ideal_generator_dimensioning,
    simulate_generator_dispatch_2025,
    compute_generator_sizing_sweep,
    create_generator_dispatch_timeseries_figure,
    create_generator_monthly_fuel_figure,
    create_generator_sankey_figure,
    create_generator_sweep_figure,
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

    load_bench = synthesize_benchmark_load_profile_2025(nominal_peak_kw=550.0)
    st.session_state["active_load_series_2025"] = load_bench
    return load_bench, "Industrial Grid Congestion Benchmark (550 kW peak)"


def render_generator_sandbox(key_prefix: str = "gen_sb") -> None:
    """Main orchestrator for the Standalone Generator & Grid Congestion Sandbox."""
    st.set_page_config(
        page_title="Generator & Grid Congestion Workbench",
        page_icon=":material/local_gas_station:",
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
                keys_to_clear = [k for k in list(st.session_state.keys()) if k.startswith(key_prefix) or "gen_" in k]
                for k in keys_to_clear:
                    del st.session_state[k]
                st.rerun()

    # ----------------------------------------------------------------------------------
    # 3-Tab Main Layout
    # ----------------------------------------------------------------------------------
    tab1, tab2, tab3 = st.tabs(
        [
            ":material/analytics: Tab 1: Facility Load & Consumption Profile",
            ":material/local_gas_station: Tab 2: Standalone Generator Sizing & Fuel Economics",
            ":material/precision_manufacturing: Tab 3: Ideal Peaker Dimensioning & Sizing Optimizer",
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

    # Default Contract for grid limit reference
    grid_limit_key = f"{key_prefix}_grid_limit_kw"
    if grid_limit_key not in st.session_state:
        st.session_state[grid_limit_key] = 400.0
    contract_cap_kw = float(st.session_state[grid_limit_key])

    active_contract = Contract(
        name="Standard Industrial Contract (400 kW Limit)",
        contracted_capacity_kw=contract_cap_kw,
        monthly_capacity_tariff=0.15,
        default_energy_rate=0.20,
        currency="EUR",
    )

    # ----------------------------------------------------------------------------------
    # TAB 2: Standalone Generator Sizing & Fuel Economics (1:1 with Main Program UI)
    # ----------------------------------------------------------------------------------
    with tab2:
        # Top Action Controls Bar
        act_col1, act_col2, _ = st.columns([4.0, 3.0, 5.0])
        with act_col1:
            if st.button(
                "Load Example Case (Liander 400 kW Grid Congestion Benchmark)",
                icon=":material/play_circle:",
                key=f"{key_prefix}_load_preset_btn",
                help="Pre-fills a real-world industrial grid constraint benchmark: 400 kW grid limit, 150 kW diesel generator, €1.45/L fuel, 25% min load."
            ):
                st.session_state[grid_limit_key] = 400.0
                st.session_state[f"{key_prefix}_cfg_power_kw"] = 150.0
                st.session_state[f"{key_prefix}_cfg_fuel_type"] = "Diesel"
                st.session_state[f"{key_prefix}_cfg_fuel_price"] = 1.45
                st.session_state[f"{key_prefix}_cfg_maint_hour"] = 4.50
                st.session_state[f"{key_prefix}_cfg_min_load"] = 25.0
                st.session_state[f"{key_prefix}_cfg_trigger_kw"] = 400.0
                st.session_state[f"{key_prefix}_cfg_acq_mode"] = "Rental / Monthly Lease"
                st.session_state[f"{key_prefix}_cfg_monthly_lease"] = 1200.0
                st.session_state[f"{key_prefix}_cfg_capital_cost"] = 0.0
                st.session_state[f"{key_prefix}_trigger_calc"] = True
                st.rerun()

        with act_col2:
            if st.button(
                "Reset / Clear Generator",
                icon=":material/restart_alt:",
                key=f"{key_prefix}_clear_gen_btn",
                help="Resets all inputs back to empty state and clears simulation results."
            ):
                for k in [
                    f"{key_prefix}_active_cfg",
                    f"{key_prefix}_sim_result",
                    f"{key_prefix}_trigger_calc",
                ]:
                    if k in st.session_state:
                        del st.session_state[k]
                st.rerun()

        peak_kw = float(load_series.peak_demand_kw)
        total_kwh = float(load_series.total_energy_kwh)

        # ------------------------------------------------------------------------------
        # 1. Interactive Grid Limit Controller (OUTSIDE of st.form for live updates)
        # ------------------------------------------------------------------------------
        with st.container(border=True):
            gl_c1, gl_c2 = st.columns([1.5, 2.5])
            with gl_c1:
                new_grid_limit = st.number_input(
                    "Contracted Grid Connection Limit (kW):",
                    min_value=10.0,
                    max_value=10000.0,
                    value=float(st.session_state.get(grid_limit_key, 400.0)),
                    step=25.0,
                    key=f"{key_prefix}_grid_limit_input",
                    help="Maximum capacity permitted by your utility/DSO before grid congestion breach occurs.",
                )
                if new_grid_limit != st.session_state[grid_limit_key]:
                    st.session_state[grid_limit_key] = float(new_grid_limit)
                    contract_cap_kw = float(new_grid_limit)
                    active_contract.contracted_capacity_kw = contract_cap_kw
                    # Update trigger threshold as well if peak shaving assist
                    st.session_state[f"{key_prefix}_cfg_trigger_kw"] = float(new_grid_limit)
                    st.session_state[f"{key_prefix}_form_trigger_kw"] = float(new_grid_limit)
                    st.session_state[f"{key_prefix}_trigger_calc"] = True
                    if f"{key_prefix}_sim_result" in st.session_state:
                        del st.session_state[f"{key_prefix}_sim_result"]
                    st.rerun()
                contract_cap_kw = float(new_grid_limit)

            with gl_c2:
                st.markdown("<div style='font-size:0.8rem; color:#94a3b8; font-weight:600; margin-bottom:6px;'>Quick Grid Limit Presets:</div>", unsafe_allow_html=True)
                p_c1, p_c2, p_c3 = st.columns(3)
                p_80_kw = round((peak_kw * 0.80) / 25.0) * 25.0
                p_50_kw = round((peak_kw * 0.50) / 25.0) * 25.0
                if p_c1.button(f"80% Peak ({p_80_kw:,.0f} kW)", key=f"{key_prefix}_btn_gl_80", use_container_width=True):
                    st.session_state[grid_limit_key] = float(p_80_kw)
                    st.session_state[f"{key_prefix}_cfg_trigger_kw"] = float(p_80_kw)
                    st.session_state[f"{key_prefix}_form_trigger_kw"] = float(p_80_kw)
                    st.session_state[f"{key_prefix}_trigger_calc"] = True
                    if f"{key_prefix}_sim_result" in st.session_state:
                        del st.session_state[f"{key_prefix}_sim_result"]
                    st.rerun()
                if p_c2.button(f"50% Peak ({p_50_kw:,.0f} kW)", key=f"{key_prefix}_btn_gl_50", use_container_width=True):
                    st.session_state[grid_limit_key] = float(p_50_kw)
                    st.session_state[f"{key_prefix}_cfg_trigger_kw"] = float(p_50_kw)
                    st.session_state[f"{key_prefix}_form_trigger_kw"] = float(p_50_kw)
                    st.session_state[f"{key_prefix}_trigger_calc"] = True
                    if f"{key_prefix}_sim_result" in st.session_state:
                        del st.session_state[f"{key_prefix}_sim_result"]
                    st.rerun()
                if p_c3.button("Default 400 kW", key=f"{key_prefix}_btn_gl_400", use_container_width=True):
                    st.session_state[grid_limit_key] = 400.0
                    st.session_state[f"{key_prefix}_cfg_trigger_kw"] = 400.0
                    st.session_state[f"{key_prefix}_form_trigger_kw"] = 400.0
                    st.session_state[f"{key_prefix}_trigger_calc"] = True
                    if f"{key_prefix}_sim_result" in st.session_state:
                        del st.session_state[f"{key_prefix}_sim_result"]
                    st.rerun()

        is_overloaded = (peak_kw > contract_cap_kw)
        overload_kw = max(0.0, peak_kw - contract_cap_kw)
        suggested_kw = max(50.0, round((overload_kw * 1.25) / 25.0) * 25.0) if is_overloaded else 100.0

        # ------------------------------------------------------------------------------
        # 2. Diagnostic Status Cards (Real-Time Reactive)
        # ------------------------------------------------------------------------------
        col_s1, col_s2, col_s3, col_s4 = st.columns(4)
        with col_s1:
            render_kpi_card(
                title="Facility Peak Demand",
                value=f"{peak_kw:.1f} kW",
                subtext=f"Total: {total_kwh:,.0f} kWh/a",
                status="default",
            )
        with col_s2:
            render_kpi_card(
                title="Contracted Grid Limit",
                value=f"{contract_cap_kw:.0f} kW",
                subtext="Contract Capacity Threshold",
                status="default",
            )
        with col_s3:
            status_theme = "alert" if is_overloaded else "ok"
            render_kpi_card(
                title="Overload Status",
                value=f"+{overload_kw:.1f} kW Overload" if is_overloaded else "Within Limit",
                subtext="Grid Capacity Exceeded!" if is_overloaded else "No Overload Violations",
                status=status_theme,
            )
        with col_s4:
            configured_kw = float(st.session_state.get(f"{key_prefix}_form_power_kw", st.session_state.get(f"{key_prefix}_cfg_power_kw", suggested_kw)))
            render_kpi_card(
                title="Configured Capacity",
                value=f"{configured_kw:.0f} kW",
                subtext="Peaking Generator Asset",
                status="default",
            )

        st.markdown("---")

        # ------------------------------------------------------------------------------
        # 3. Generator Configuration Form (Template for Master Program)
        # ------------------------------------------------------------------------------
        st.subheader(":material/settings: Generator Technical & Commercial Sizing")

        presets = get_generator_presets()
        preset_names = ["Custom"] + list(presets.keys())

        selected_preset = st.selectbox(
            "Load Pre-Configured Generator Model Preset:",
            options=preset_names,
            index=0,
            key=f"{key_prefix}_preset_select",
        )

        preset_tracker_key = f"{key_prefix}_last_selected_preset"
        if st.session_state.get(preset_tracker_key) != selected_preset:
            st.session_state[preset_tracker_key] = selected_preset
            if selected_preset != "Custom" and selected_preset in presets:
                base_cfg = presets[selected_preset]
                st.session_state[f"{key_prefix}_form_power_kw"] = float(base_cfg.rated_power_kw)
                st.session_state[f"{key_prefix}_form_fuel_type"] = base_cfg.fuel_type
                st.session_state[f"{key_prefix}_form_fuel_price"] = float(base_cfg.fuel_price_per_unit)
                st.session_state[f"{key_prefix}_form_maint_hour"] = float(base_cfg.maintenance_cost_per_op_hour)
                st.session_state[f"{key_prefix}_form_capital_cost"] = float(base_cfg.capital_cost)
                st.session_state[f"{key_prefix}_form_trigger_kw"] = contract_cap_kw if contract_cap_kw > 0 else float(base_cfg.peak_shaving_trigger_kw or 400.0)
                st.session_state[f"{key_prefix}_form_min_load"] = float(base_cfg.min_load_ratio_pct or 25.0)
                st.session_state[f"{key_prefix}_form_acq_mode"] = "Capital Purchase (CAPEX)"
                st.session_state[f"{key_prefix}_form_monthly_lease"] = 0.0
                st.session_state[f"{key_prefix}_trigger_calc"] = True
                if f"{key_prefix}_sim_result" in st.session_state:
                    del st.session_state[f"{key_prefix}_sim_result"]

        if selected_preset != "Custom" and selected_preset in presets:
            base_cfg = presets[selected_preset]
            init_power_kw = float(st.session_state.get(f"{key_prefix}_form_power_kw", base_cfg.rated_power_kw))
            init_fuel_type = str(st.session_state.get(f"{key_prefix}_form_fuel_type", base_cfg.fuel_type))
            init_fuel_price = float(st.session_state.get(f"{key_prefix}_form_fuel_price", base_cfg.fuel_price_per_unit))
            init_maint_cost = float(st.session_state.get(f"{key_prefix}_form_maint_hour", base_cfg.maintenance_cost_per_op_hour))
            init_capex = float(st.session_state.get(f"{key_prefix}_form_capital_cost", base_cfg.capital_cost))
            init_trigger = float(st.session_state.get(f"{key_prefix}_form_trigger_kw", contract_cap_kw if contract_cap_kw > 0 else 400.0))
            init_min_load = float(st.session_state.get(f"{key_prefix}_form_min_load", base_cfg.min_load_ratio_pct or 25.0))
            init_monthly_lease = float(st.session_state.get(f"{key_prefix}_form_monthly_lease", 0.0))
            init_acq_mode = str(st.session_state.get(f"{key_prefix}_form_acq_mode", "Capital Purchase (CAPEX)"))
        else:
            init_power_kw = float(st.session_state.get(f"{key_prefix}_form_power_kw", st.session_state.get(f"{key_prefix}_cfg_power_kw", suggested_kw)))
            init_fuel_type = str(st.session_state.get(f"{key_prefix}_form_fuel_type", st.session_state.get(f"{key_prefix}_cfg_fuel_type", "Diesel")))
            init_fuel_price = float(st.session_state.get(f"{key_prefix}_form_fuel_price", st.session_state.get(f"{key_prefix}_cfg_fuel_price", 1.45)))
            init_maint_cost = float(st.session_state.get(f"{key_prefix}_form_maint_hour", st.session_state.get(f"{key_prefix}_cfg_maint_hour", 4.50)))
            init_capex = float(st.session_state.get(f"{key_prefix}_form_capital_cost", st.session_state.get(f"{key_prefix}_cfg_capital_cost", 18000.0)))
            init_trigger = float(st.session_state.get(f"{key_prefix}_form_trigger_kw", st.session_state.get(f"{key_prefix}_cfg_trigger_kw", contract_cap_kw)))
            init_min_load = float(st.session_state.get(f"{key_prefix}_form_min_load", st.session_state.get(f"{key_prefix}_cfg_min_load", 25.0)))
            init_monthly_lease = float(st.session_state.get(f"{key_prefix}_form_monthly_lease", st.session_state.get(f"{key_prefix}_cfg_monthly_lease", 0.0)))
            init_acq_mode = str(st.session_state.get(f"{key_prefix}_form_acq_mode", st.session_state.get(f"{key_prefix}_cfg_acq_mode", "Capital Purchase (CAPEX)" if init_monthly_lease <= 0 else "Rental / Monthly Lease")))

        currency = "EUR"

        with st.form(key=f"{key_prefix}_generator_form"):
            col_f1, col_f2, col_f3 = st.columns(3)
            with col_f1:
                gen_power_kw = st.number_input(
                    "Generator Rated Power (kW):",
                    min_value=10.0,
                    max_value=5000.0,
                    value=float(init_power_kw),
                    step=25.0,
                    key=f"{key_prefix}_form_power_kw",
                    help="Continuous rated electrical output capacity of the generator set.",
                )

                strat_options = [
                    "Peak Shaving Assist (shave peaks exceeding threshold)",
                    "Full Residual Backup / Deficit Follower (cover unmet deficit)",
                ]
                strat_choice = st.selectbox(
                    "Operational Dispatch Strategy:",
                    options=strat_options,
                    index=0,
                    key=f"{key_prefix}_form_strat_choice",
                    help="Choose whether the generator acts as an overload peaker above a set limit or as a deficit follower.",
                )
                form_is_backup = ("Full Residual Backup" in strat_choice)

                if form_is_backup:
                    cov_pct = st.slider(
                        "Residual Deficit Target Coverage (%):",
                        min_value=10.0,
                        max_value=100.0,
                        value=100.0,
                        step=5.0,
                        key=f"{key_prefix}_form_cov_pct",
                    )
                    form_trigger_kw = contract_cap_kw
                else:
                    form_trigger_kw = st.number_input(
                        "Dispatch Trigger Threshold (kW):",
                        min_value=10.0,
                        max_value=5000.0,
                        value=float(init_trigger),
                        step=25.0,
                        key=f"{key_prefix}_form_trigger_kw",
                        help=f"Generator starts when load exceeds this capacity cap. Grid limit: {contract_cap_kw:.0f} kW.",
                    )
                    cov_pct = 100.0

            with col_f2:
                fuel_type_opts = ["Diesel", "Natural Gas", "HVO/Biofuel"]
                fuel_idx = fuel_type_opts.index(init_fuel_type) if init_fuel_type in fuel_type_opts else 0
                fuel_type = st.selectbox("Fuel Type:", options=fuel_type_opts, index=fuel_idx, key=f"{key_prefix}_form_fuel_type")

                fuel_price = st.number_input(
                    f"Fuel Price ({currency}/Liter or m³):",
                    min_value=0.01,
                    max_value=1000.0,
                    value=float(init_fuel_price),
                    step=0.05,
                    key=f"{key_prefix}_form_fuel_price",
                )

                maint_per_hour = st.number_input(
                    f"Maintenance Cost ({currency}/operating hour):",
                    min_value=0.0,
                    max_value=1000.0,
                    value=float(init_maint_cost),
                    step=0.5,
                    key=f"{key_prefix}_form_maint_hour",
                )

                min_load_pct = st.slider(
                    "Minimum Loading Ratio (%):",
                    min_value=0.0,
                    max_value=50.0,
                    value=float(init_min_load),
                    step=5.0,
                    key=f"{key_prefix}_form_min_load",
                    help="Minimum engine loading to prevent wet-stacking and cylinder glazing.",
                )

            with col_f3:
                acq_opts = ["Rental / Monthly Lease", "Capital Purchase (CAPEX)"]
                acq_idx = acq_opts.index(init_acq_mode) if init_acq_mode in acq_opts else 1
                acq_mode = st.radio("Acquisition Model:", options=acq_opts, index=acq_idx, key=f"{key_prefix}_form_acq_mode")

                if acq_mode == "Rental / Monthly Lease":
                    monthly_lease = st.number_input(
                        f"Monthly Equipment Lease Fee ({currency}/mo):",
                        min_value=0.0,
                        max_value=500000.0,
                        value=float(init_monthly_lease or 1200.0),
                        step=100.0,
                        key=f"{key_prefix}_form_monthly_lease",
                    )
                    capital_cost = 0.0
                else:
                    capital_cost = st.number_input(
                        f"Turnkey Purchase CAPEX ({currency}):",
                        min_value=0.0,
                        max_value=5000000.0,
                        value=float(init_capex or 18000.0),
                        step=1000.0,
                        key=f"{key_prefix}_form_capital_cost",
                    )
                    monthly_lease = 0.0

            submitted = st.form_submit_button(
                ":material/calculate: Run Generator Simulation & Dispatch",
                type="primary",
                use_container_width=True,
            )

        # Update Session State Config
        gen_cfg = GeneratorConfig(
            rated_power_kw=float(gen_power_kw),
            fuel_type=str(fuel_type),
            min_load_ratio_pct=float(min_load_pct),
            fuel_curve_slope_l_per_kwh=0.28 if fuel_type == "Natural Gas" else 0.24,
            fuel_curve_intercept_l_per_kw_rated=0.045 if fuel_type == "Natural Gas" else 0.04,
            dispatch_mode="residual_load_follow" if form_is_backup else "peak_shaving_assist",
            peak_shaving_trigger_kw=float(form_trigger_kw),
            is_backup_mode=bool(form_is_backup),
            backup_coverage_pct=float(cov_pct),
            fuel_price_per_unit=float(fuel_price),
            maintenance_cost_per_op_hour=float(maint_per_hour),
            capital_cost=float(capital_cost),
            monthly_lease_fee=float(monthly_lease),
            currency=currency,
        )
        st.session_state[f"{key_prefix}_active_cfg"] = gen_cfg
        st.session_state[f"{key_prefix}_cfg_power_kw"] = float(gen_power_kw)
        st.session_state[f"{key_prefix}_cfg_trigger_kw"] = float(form_trigger_kw)

        # ------------------------------------------------------------------------------
        # 4. Execute 15-Minute Simulation (st.form submitted OR auto-trigger on grid limit change)
        # ------------------------------------------------------------------------------
        auto_trigger = st.session_state.pop(f"{key_prefix}_trigger_calc", False)
        cached_sim = st.session_state.get(f"{key_prefix}_sim_result")

        stale_trigger = False
        if cached_sim is not None:
            cached_trig = float(cached_sim.get("trigger_kw", 0.0))
            if abs(cached_trig - float(gen_cfg.peak_shaving_trigger_kw)) > 0.1:
                stale_trigger = True

        if submitted or auto_trigger or cached_sim is None or stale_trigger:
            with st.spinner("Calculating 15-minute physical generator dispatch & fuel curve..."):
                raw_df = pd.DataFrame({
                    "timestamp": load_series.timestamps,
                    "Total_Demand_kW": load_series.power_kw,
                })
                sim_res = simulate_generator_peaking(
                    df_load=raw_df,
                    power_col="Total_Demand_kW",
                    contract=active_contract,
                    gen_config=gen_cfg,
                    step_hours=0.25,
                )
                st.session_state[f"{key_prefix}_sim_result"] = sim_res
                cached_sim = sim_res

        sim_res = cached_sim
        kpis: GeneratorKPIs = sim_res["kpis"]
        df_dispatch = sim_res["df_dispatch"]
        df_zahlungsreihe = sim_res["df_zahlungsreihe"]
        shaved_peak = sim_res["peak_shaved_kw"]
        new_peak = sim_res["new_peak_kw"]
        annual_savings = sim_res["annual_net_savings"]

        st.markdown("---")

        # ------------------------------------------------------------------------------
        # 4. Executive KPI Results Cards Matching Main Program
        # ------------------------------------------------------------------------------
        st.subheader(":material/speed: Dispatch Performance & Peaking Results")
        col_r1, col_r2, col_r3, col_r4 = st.columns(4)
        with col_r1:
            render_kpi_card(
                title="Shaved Peak Demand",
                value=f"{shaved_peak:.1f} kW",
                subtext=f"New Grid Peak: {new_peak:.1f} kW",
                status="ok" if shaved_peak > 0 else "default",
            )
        with col_r2:
            render_kpi_card(
                title="Generator Runtime",
                value=f"{kpis.operating_hours:.1f} hrs",
                subtext=f"Generated: {kpis.total_generation_kwh:,.0f} kWh ({kpis.starts_count} starts)",
                status="default",
            )
        with col_r3:
            unit_lbl = "m³" if gen_cfg.fuel_type == "Natural Gas" else "L"
            render_kpi_card(
                title="Fuel Consumption",
                value=f"{kpis.total_fuel_units:,.1f} {unit_lbl}",
                subtext=f"Fuel OPEX: {kpis.fuel_cost_total:,.0f} {currency}",
                status="default",
            )
        with col_r4:
            is_pos = (annual_savings > 0)
            render_kpi_card(
                title="Net Annual Impact",
                value=f"{annual_savings:,.0f} {currency}/a",
                subtext="Generates Net Savings!" if is_pos else "Genset Adds Operational Cost",
                status="ok" if is_pos else "alert",
            )

        # 5. Comprehensive Visual Dispatch & Financial Analysis Suite (Consolidated)
        st.markdown("#### :material/monitoring: Visual Dispatch & Financial Analysis")
        tab_v1, tab_v2, tab_v3, tab_v4 = st.tabs([
            ":material/timeline: 15-Minute Dispatch Timeseries",
            ":material/bar_chart: Monthly Generation & Fuel Breakdown",
            ":material/schema: Energy Flow (Sankey)",
            ":material/payments: Commercial Zahlungsreihe & Amortization",
        ])

        with tab_v1:
            fig_ts = create_generator_dispatch_timeseries_figure(
                df=df_dispatch,
                trigger_kw=float(gen_cfg.peak_shaving_trigger_kw or contract_cap_kw),
                rated_power_kw=float(gen_cfg.rated_power_kw),
            )
            st.plotly_chart(fig_ts, use_container_width=True)

        with tab_v2:
            fig_m = create_generator_monthly_fuel_figure(df=df_dispatch, fuel_type=gen_cfg.fuel_type)
            st.plotly_chart(fig_m, use_container_width=True)

        with tab_v3:
            fig_s = create_generator_sankey_figure(
                total_load_kwh=load_series.total_energy_kwh,
                gen_kwh=kpis.total_generation_kwh,
                grid_kwh=kpis.residual_demand_after_kwh,
                fuel_units=kpis.total_fuel_units,
                fuel_type=gen_cfg.fuel_type,
            )
            st.plotly_chart(fig_s, use_container_width=True)

        with tab_v4:
            fig_payment = create_cumulative_payment_chart(df_zahlungsreihe, currency=currency)
            st.plotly_chart(fig_payment, use_container_width=True)
            with st.expander(":material/table_chart: Detailed Monthly Payment Schedule (Zahlungsreihe Table)", expanded=False):
                st.dataframe(df_zahlungsreihe, use_container_width=True, hide_index=True)

    # ==================================================================================
    # TAB 3: Ideal Peaker Dimensioning & Sizing Optimizer ("The Perfect Generator")
    # ==================================================================================
    with tab3:
        st.markdown(
            """
            <div style="background: #0f172a; border-left: 4px solid #10b981; padding: 12px 18px; border-radius: 6px; margin-bottom: 16px;">
                <strong style="color:#f8fafc; font-size:1.05rem;">"The Perfect Generator" — Ideal Peaker Dimensioning & Sizing Optimizer</strong>
                <p style="color:#94a3b8; font-size:0.84rem; margin:3px 0 0 0;">
                    Calculates the unconstrained physical generator dimensioning required to completely eradicate all grid limit breaches,
                    inspired by the unconstrained BESS diagnostics. Automatically computes optimal rated power, continuous runtime duration,
                    safe on-site fuel tank autonomy, wet-stacking risks, and parametric capacity tradeoffs.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        sim_res_tab2 = st.session_state.get(f"{key_prefix}_sim_result")
        gen_cfg_active: Optional[GeneratorConfig] = st.session_state.get(f"{key_prefix}_active_cfg")

        if sim_res_tab2 is None or gen_cfg_active is None:
            st.warning("Please configure and calculate generator dispatch in **Tab 2** first to view integration analytics.", icon=":material/warning:")
            return

        # Execute high-performance 35,040-step dispatch coupling
        dt = 0.25
        res_coupled = simulate_generator_dispatch_2025(
            load_kw=load_series.power_kw,
            timestamps=load_series.timestamps,
            grid_limit_kw=contract_cap_kw,
            gen_config=gen_cfg_active,
            step_hours=dt,
        )

        df_coupled = res_coupled["df_dispatch"]
        kpis_coupled: GeneratorKPIs = res_coupled["kpis"]

        # ------------------------------------------------------------------------------
        # 1. Coupled Performance Metrics (8 KPI Cards)
        # ------------------------------------------------------------------------------
        st.subheader("1. Active Generator Dispatch vs. Grid Congestion")
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            render_kpi_card(
                "Shaved Peak Demand",
                f"{res_coupled['peak_shaved_kw']:.1f} kW",
                f"Peak: {res_coupled['orig_peak_kw']:.1f} kW -> New: {res_coupled['new_peak_kw']:.1f} kW",
                status="ok" if res_coupled['peak_shaved_kw'] > 0 else "default",
            )
        with m2:
            base_hrs = res_coupled["overload_hours_before"]
            after_hrs = res_coupled["overload_hours_after"]
            hrs_eliminated_pct = ((base_hrs - after_hrs) / max(0.1, base_hrs) * 100.0) if base_hrs > 0 else 100.0
            render_kpi_card(
                "Avoided Overload Hours",
                f"{hrs_eliminated_pct:.1f} %",
                f"Overload: {base_hrs:.1f} hrs -> {after_hrs:.1f} hrs",
                status="ok" if hrs_eliminated_pct >= 99.0 else "default",
            )
        with m3:
            render_kpi_card(
                "Generator Generation",
                f"{kpis_coupled.total_generation_kwh / 1000.0:,.1f} MWh/a",
                f"Displaced Grid Import ({kpis_coupled.operating_hours:.1f} hrs runtime)",
                status="default",
            )
        with m4:
            unit_lbl = "m³" if gen_cfg_active.fuel_type == "Natural Gas" else "Liters"
            render_kpi_card(
                "Fuel Consumption",
                f"{kpis_coupled.total_fuel_units:,.0f} {unit_lbl}",
                f"Fuel OPEX: {kpis_coupled.fuel_cost_total:,.0f} {currency}",
                status="default",
            )

        m5, m6, m7, m8 = st.columns(4)
        with m5:
            render_kpi_card(
                "Operating Hours & Starts",
                f"{kpis_coupled.operating_hours:.1f} hrs",
                f"{kpis_coupled.starts_count} cold engine starts",
                status="default",
            )
        with m6:
            render_kpi_card(
                "Total Operating Cost",
                f"{kpis_coupled.total_operating_cost:,.0f} {currency}/a",
                f"Levelized: {kpis_coupled.levelized_cost_per_kwh:.3f} {currency}/kWh",
            )
        with m7:
            avoided_overload_mwh = (res_coupled["overload_energy_before_kwh"] - res_coupled["overload_energy_after_kwh"]) / 1000.0
            render_kpi_card(
                "Avoided Overload Energy",
                f"{avoided_overload_mwh:,.1f} MWh",
                "Direct capacity breach volume mitigated",
                status="ok",
            )
        with m8:
            res_import_mwh = kpis_coupled.residual_demand_after_kwh / 1000.0
            render_kpi_card(
                "Residual Grid Purchase",
                f"{res_import_mwh:,.1f} MWh/a",
                "Remaining facility energy from grid",
            )

        st.markdown("---")

        # ------------------------------------------------------------------------------
        # 2. "The Perfect Generator" Diagnostic Blueprint (Unconstrained Sizing Analysis)
        # ------------------------------------------------------------------------------
        st.subheader("2. :material/auto_awesome: 'The Perfect Generator' Diagnostic Blueprint")
        st.caption(
            "Inspired by the unconstrained BESS diagnostics, this blueprint models the ideal genset required to completely eradicate all facility grid overload breaches. "
            "It computes the unconstrained power demand peak, required continuous runtime, safe fuel storage, wet-stacking exposure, and sizing tiers."
        )

        ideal_res = compute_ideal_generator_dimensioning(
            load_kw=load_series.power_kw,
            grid_limit_kw=contract_cap_kw,
            step_hours=0.25,
            fuel_type=gen_cfg_active.fuel_type,
            fuel_price_per_unit=gen_cfg_active.fuel_price_per_unit,
            min_load_pct=gen_cfg_active.min_load_ratio_pct,
        )

        tank_unit = "m³" if gen_cfg_active.fuel_type == "Natural Gas" else "Liters"

        # Diagnostic KPI Cards
        d1, d2, d3, d4 = st.columns(4)
        with d1:
            render_kpi_card(
                "Peak Grid Overload",
                f"{ideal_res.peak_overload_kw:,.1f} kW",
                f"Instantaneous peak breach above {contract_cap_kw:.0f} kW limit",
                status="alert" if ideal_res.peak_overload_kw > 0 else "ok",
            )
        with d2:
            render_kpi_card(
                "Annual Overload Energy",
                f"{ideal_res.annual_overload_energy_mwh:,.1f} MWh/a",
                f"{ideal_res.overload_hours_count:,.1f} breach hours ({ideal_res.engine_starts_count} start events)",
                status="alert" if ideal_res.annual_overload_energy_mwh > 0 else "ok",
            )
        with d3:
            render_kpi_card(
                "Longest Continuous Run",
                f"{ideal_res.max_continuous_breach_hours:.1f} hrs",
                "Longest unbroken grid breach duration",
                status="default",
            )
        with d4:
            render_kpi_card(
                "Safe Tank Autonomy",
                f"{ideal_res.recommended_fuel_tank_liters:,.0f} {tank_unit}",
                "Worst event burn + 48h emergency reserve",
                status="ok",
            )

        # Wet-stacking risk alert if needed
        if ideal_res.wet_stacking_risk_pct > 15.0:
            st.warning(
                f":material/warning: **Wet-Stacking Risk Warning:** {ideal_res.wet_stacking_risk_pct:.1f}% of overload intervals demand less than 25% nameplate capacity. "
                "Running a single oversized generator below minimum loading causes unburned fuel buildup. Consider multi-genset modularity or a BESS hybrid buffer.",
                icon=":material/warning:",
            )

        # 3 Sizing Recommendations Cards with 1-Click Apply Buttons
        st.markdown("##### :material/recommend: Peaker Sizing Tiers & 1-Click Synchronization to Tab 2")
        rec_c1, rec_c2, rec_c3 = st.columns(3)

        with rec_c1:
            with st.container(border=True):
                st.markdown("**:material/verified: Tier 1: 100% Zero-Breach Champion**")
                st.markdown(f"<h3 style='margin:4px 0; color:#38bdf8;'>{ideal_res.recommended_rated_kw_100:,.0f} kW</h3>", unsafe_allow_html=True)
                st.caption(f"Guarantees 100% contract compliance with 10% safety margin. Projected annual fuel: ~{ideal_res.annual_estimated_fuel_liters:,.0f} {tank_unit} (~{ideal_res.annual_fuel_cost_est:,.0f} {currency}).")
                if st.button(
                    f":material/auto_fix_high: Apply 100% Sizing ({ideal_res.recommended_rated_kw_100:,.0f} kW)",
                    key=f"{key_prefix}_btn_apply_ideal_100",
                    type="primary",
                    use_container_width=True,
                    help="Transfers 100% zero-breach rated power directly into Tab 2 form and re-dispatches.",
                ):
                    _recalc_target_gen_kw(ideal_res.recommended_rated_kw_100, gen_cfg_active, key_prefix)

        with rec_c2:
            with st.container(border=True):
                st.markdown("**:material/savings: Tier 2: 80% Economic Sweet Spot**")
                st.markdown(f"<h3 style='margin:4px 0; color:#34d399;'>{ideal_res.recommended_rated_kw_80:,.0f} kW</h3>", unsafe_allow_html=True)
                st.caption("Eradicates 80% of grid breach capacity. Substantially lowers equipment CAPEX and avoids wet-stacking during small peaks.")
                if st.button(
                    f":material/auto_fix_high: Apply 80% Sizing ({ideal_res.recommended_rated_kw_80:,.0f} kW)",
                    key=f"{key_prefix}_btn_apply_ideal_80",
                    use_container_width=True,
                    help="Transfers 80% economic sweet spot rated power directly into Tab 2 form and re-dispatches.",
                ):
                    _recalc_target_gen_kw(ideal_res.recommended_rated_kw_80, gen_cfg_active, key_prefix)

        with rec_c3:
            with st.container(border=True):
                st.markdown("**:material/battery_charging_full: Tier 3: 50% Peak-Assist Model**")
                st.markdown(f"<h3 style='margin:4px 0; color:#fbbf24;'>{ideal_res.recommended_rated_kw_50:,.0f} kW</h3>", unsafe_allow_html=True)
                st.caption("Cuts top 50% peak breaches. Highly recommended when paired with an on-site battery (BESS) or active demand-response.")
                if st.button(
                    f":material/auto_fix_high: Apply 50% Sizing ({ideal_res.recommended_rated_kw_50:,.0f} kW)",
                    key=f"{key_prefix}_btn_apply_ideal_50",
                    use_container_width=True,
                    help="Transfers 50% assist rated power directly into Tab 2 form and re-dispatches.",
                ):
                    _recalc_target_gen_kw(ideal_res.recommended_rated_kw_50, gen_cfg_active, key_prefix)

        st.markdown("---")

        # ------------------------------------------------------------------------------
        # 3. Parametric Capacity Sweep & Tradeoff Curve
        # ------------------------------------------------------------------------------
        st.subheader("3. Parametric Capacity Sweep & Sizing Tradeoff Curve")
        st.caption(
            "The **Capacity Sweep Curve** visualizes the continuous tradeoff between generator continuous rated kW, "
            "avoided overload breach hours, and operating fuel burn across different sizing points."
        )

        df_sweep, sweep_presets = compute_generator_sizing_sweep(
            load_kw=load_series.power_kw,
            grid_limit_kw=contract_cap_kw,
            timestamps=load_series.timestamps,
            base_config=gen_cfg_active,
        )

        col_sweep_curve, col_sweep_kpis = st.columns([1.5, 1.0])
        with col_sweep_curve:
            fig_sweep = create_generator_sweep_figure(
                df_sweep=df_sweep,
                selected_kw=float(gen_cfg_active.rated_power_kw),
            )
            st.plotly_chart(fig_sweep, use_container_width=True)

        with col_sweep_kpis:
            with st.container(border=True):
                st.markdown("##### Current Sizing Summary")
                st.metric("Continuous Rated Capacity", f"{gen_cfg_active.rated_power_kw:,.0f} kW", f"Min Load: {gen_cfg_active.min_power_kw:,.0f} kW")
                st.metric("Avoided Overload Hours", f"{hrs_eliminated_pct:.1f}%", f"Remaining Overload: {res_coupled['overload_hours_after']:.1f} hrs")
                st.metric("Total Operating OPEX", f"{kpis_coupled.total_operating_cost:,.0f} {currency}/a", f"Fuel: {kpis_coupled.fuel_cost_total:,.0f} {currency}")

        # ------------------------------------------------------------------------------
        # 4. Standardized Session State Output Contract for Phase 2 Master Integration
        # ------------------------------------------------------------------------------
        p_residual_arr = res_coupled["p_grid_kw"]
        p_gen_arr = res_coupled["p_gen_kw"]

        st.session_state["generator_standalone_result"] = {
            "load_series": load_series,
            "residual_power_kw": p_residual_arr,
            "p_gen_kw": p_gen_arr,
            "rated_power_kw": gen_cfg_active.rated_power_kw,
            "total_capex": gen_cfg_active.capital_cost,
            "monthly_lease_fee": gen_cfg_active.monthly_lease_fee,
            "annual_opex": kpis_coupled.total_operating_cost,
            "operating_hours": kpis_coupled.operating_hours,
            "fuel_units": kpis_coupled.total_fuel_units,
            "peak_shaved_kw": res_coupled["peak_shaved_kw"],
            "grid_limit_kw": contract_cap_kw,
            "currency_code": currency,
        }

        with st.expander(":material/integration_instructions: Developer & Future Master Integration Data Contract", expanded=False):
            st.caption(
                "This clean data contract holds the 35,040-step residual load array `residual_power_kw` and generator metrics. "
                "In Phase 2, this object will directly feed into the 4-Pillar electricity billing engine to evaluate penalty and bill savings."
            )
            summary_dict = {
                "scenario": "generator_only_pure",
                "rated_power_kw": gen_cfg_active.rated_power_kw,
                "grid_limit_kw": contract_cap_kw,
                "peak_shaved_kw": round(res_coupled["peak_shaved_kw"], 1),
                "new_peak_kw": round(res_coupled["new_peak_kw"], 1),
                "operating_hours": round(kpis_coupled.operating_hours, 1),
                "starts_count": kpis_coupled.starts_count,
                "fuel_units": round(kpis_coupled.total_fuel_units, 1),
                "fuel_type": gen_cfg_active.fuel_type,
                "total_operating_cost": round(kpis_coupled.total_operating_cost, 2),
                "capital_cost": round(gen_cfg_active.capital_cost, 2),
                "monthly_lease_fee": round(gen_cfg_active.monthly_lease_fee, 2),
                "currency": currency,
                "residual_peak_kw": round(float(np.max(p_residual_arr)), 2),
            }
            st.json(summary_dict)
            st.download_button(
                label=":material/download: Download Standalone Generator Plant Summary (.json)",
                data=json.dumps(summary_dict, indent=2).encode("utf-8"),
                file_name=f"generator_summary_{gen_cfg_active.rated_power_kw:.0f}kW.json",
                mime="application/json",
                key=f"{key_prefix}_dl_sum_json",
            )


def _recalc_target_gen_kw(target_kw: float, cfg: GeneratorConfig, key_prefix: str) -> None:
    """Helper to update generator rated capacity and trigger re-simulation."""
    target_val = float(target_kw)
    cfg.rated_power_kw = target_val
    st.session_state[f"{key_prefix}_cfg_power_kw"] = target_val
    st.session_state[f"{key_prefix}_form_power_kw"] = target_val
    st.session_state[f"{key_prefix}_active_cfg"] = cfg
    st.session_state[f"{key_prefix}_trigger_calc"] = True
    if f"{key_prefix}_sim_result" in st.session_state:
        del st.session_state[f"{key_prefix}_sim_result"]
    st.rerun()


def main() -> None:
    render_generator_sandbox(key_prefix="gen_sb")


if __name__ == "__main__":
    main()
