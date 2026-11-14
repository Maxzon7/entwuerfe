"""
========================================================================================
Combined System Sandbox Application (ui_sandbox/Combined_sandbox/app.py)
========================================================================================

Standalone Execution:
    python -m streamlit run "ui_sandbox/Combined_sandbox/app.py"

3-Level Modular Architecture ("Clean Screen Policy"):
  - Level 1 (Top — System Overview Bar):
      * Grid Limit (kW) input right next to measured Peak Demand (kW)
      * Global activation switches for Solar, Battery, Generator, and Financials
        (all add-on modules start deactivated/grayed out by default)
  - Level 2 (Middle — 6 Sub-Tabs with 1-Click Activation):
      * Subtab 1: Consumption (Always active; CSV upload default + benchmark switcher + 4 Base KPIs)
      * Subtab 2: Solar (City search & Amsterdam default, EU PVGIS, Dual Quick-Sizing, Formula Box,
        Inverter AC Limit & Efficiency)
      * Subtab 3: Battery (Dual Sizing: Standalone vs. Coupled, 4-Criterion Bottleneck Table,
        Min/Max SoC & Round-Trip Efficiency)
      * Subtab 4: Generator (Dual Sizing: Standalone vs. Coupled, Rated Power, Min Load %, Fuel Type)
      * Subtab 5: Interaction Rules (Rules 1-3 in plain language, including Solar auto-priority note
        and Option D full charging coupling)
      * Subtab 6: Financials (Lazy-loaded; 4-Pillar Tariff, conditional Solar/Battery/Generator cost
        blocks, 4 Financial KPIs, Cost Comparison Chart With vs. Without System, 15-Year Cashflow Table)
  - Level 3 (Bottom — Permanent Master Output):
      * Always visible below the sub-tabs across every tab switch
      * 4 Master KPIs, Synchronized 15-Min Power Flow & Battery Level Chart (7D/1M/3M/All + Range-Slider),
        Direct Excel Export (.xlsx), and Compact System Comparison Table
========================================================================================
"""

import copy
import math
import os
import sys
from typing import Tuple, List, Optional
import numpy as np
import pandas as pd
import streamlit as st

try:
    import folium
    from streamlit_folium import st_folium
    _HAS_FOLIUM = True
except ImportError:
    folium = None  # type: ignore
    st_folium = None  # type: ignore
    _HAS_FOLIUM = False

# Ensure root and parent directories are on sys.path for standalone execution
_CURRENT_DIR = os.path.abspath(os.path.dirname(__file__))
_UI_SANDBOX_DIR = os.path.abspath(os.path.join(_CURRENT_DIR, ".."))
_PROJECT_ROOT = os.path.abspath(os.path.join(_UI_SANDBOX_DIR, ".."))
_WORKSPACE_DIR = os.path.abspath(os.path.join(_PROJECT_ROOT, ".."))
for _p in (_WORKSPACE_DIR, _PROJECT_ROOT, _UI_SANDBOX_DIR, _CURRENT_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from ui.common.styles import apply_custom_styles
    from ui.common.cards import render_kpi_card
    from core.csv_parser import read_raw_content, parse_csv_content, detect_suggested_columns
    from core.solar_engine import search_locations_open_meteo
except ImportError:
    from current_model.ui.common.styles import apply_custom_styles
    from current_model.ui.common.cards import render_kpi_card
    from current_model.core.csv_parser import read_raw_content, parse_csv_content, detect_suggested_columns
    from current_model.core.solar_engine import search_locations_open_meteo

try:
    from ui_sandbox.Currentsituation_sandbox.engine.config_and_models import LoadSeries2025
    from ui_sandbox.Currentsituation_sandbox.engine.consumption_pipeline import (
        normalize_load_profile_2025,
        synthesize_benchmark_load_profile_2025,
        synthesize_edemsa_salentein_load_profile_2025,
    )
    from ui_sandbox.Currentsituation_sandbox.consumption.view import render_tab1_consumption
except ImportError:
    from current_model.ui_sandbox.Currentsituation_sandbox.engine.config_and_models import LoadSeries2025
    from current_model.ui_sandbox.Currentsituation_sandbox.engine.consumption_pipeline import (
        normalize_load_profile_2025,
        synthesize_benchmark_load_profile_2025,
        synthesize_edemsa_salentein_load_profile_2025,
    )
    from current_model.ui_sandbox.Currentsituation_sandbox.consumption.view import render_tab1_consumption

import importlib

try:
    import ui_sandbox.Combined_sandbox.combined_sandbox_engine as _engine_mod
    if getattr(_engine_mod, "ENGINE_VERSION", None) != "13.7":
        _engine_mod = importlib.reload(_engine_mod)
    from ui_sandbox.Combined_sandbox.combined_sandbox_engine import (
        ENGINE_VERSION,
        SOLAR_SITE_PRESETS,
        FUEL_SPECS,
        RULE1_OPTIONS,
        RULE2_OPTIONS,
        RULE3_OPTIONS,
        MIX_STRATEGY_OPTIONS,
        CombinedSystemConfig,
        InteractionRulesConfig,
        CombinedFinancialConfig,
        DualBatterySizingResult,
        DualGeneratorSizingResult,
        CoordinatedMixRecommendation,
        SystemUtilizationDiagnostics,
        get_unit_solar_generation_profile,
        derive_solar_sizing_and_formula,
        determine_smart_modular_units,
        compute_dual_battery_sizing,
        refresh_bottleneck_table_configured_status,
        compute_dual_generator_sizing,
        compute_coordinated_mix_sizing,
        simulate_combined_system_dispatch,
        compute_system_utilization_diagnostics,
        evaluate_combined_financials,
        get_dso_preset_options,
        get_supplier_preset_options,
        get_metering_preset_options,
        apply_utility_tariff_presets,
    )
except (ImportError, AttributeError):
    for _m in list(sys.modules.keys()):
        if "Combined_sandbox" in _m:
            del sys.modules[_m]
    from ui_sandbox.Combined_sandbox.combined_sandbox_engine import (
        ENGINE_VERSION,
        SOLAR_SITE_PRESETS,
        FUEL_SPECS,
        RULE1_OPTIONS,
        RULE2_OPTIONS,
        RULE3_OPTIONS,
        MIX_STRATEGY_OPTIONS,
        CombinedSystemConfig,
        InteractionRulesConfig,
        CombinedFinancialConfig,
        DualBatterySizingResult,
        DualGeneratorSizingResult,
        CoordinatedMixRecommendation,
        SystemUtilizationDiagnostics,
        get_unit_solar_generation_profile,
        derive_solar_sizing_and_formula,
        determine_smart_modular_units,
        compute_dual_battery_sizing,
        refresh_bottleneck_table_configured_status,
        compute_dual_generator_sizing,
        compute_coordinated_mix_sizing,
        simulate_combined_system_dispatch,
        compute_system_utilization_diagnostics,
        evaluate_combined_financials,
        get_dso_preset_options,
        get_supplier_preset_options,
        get_metering_preset_options,
        apply_utility_tariff_presets,
    )

import ui_sandbox.Combined_sandbox.combined_charts as _charts_mod
_charts_mod = importlib.reload(_charts_mod)
from ui_sandbox.Combined_sandbox.combined_charts import (
    create_consumption_baseline_figure,
    create_combined_dispatch_soc_figure,
    create_financial_cost_comparison_figure,
    create_financial_tco_trajectory_figure,
    create_financial_waterfall_bridge_figure,
    create_financial_monthly_cashflow_figure,
    create_monthly_grid_bill_progression_figure,
    create_supply_mix_pie_figure,
    create_component_utilization_bars_figure,
)
from ui_sandbox.Combined_sandbox.combined_excel_exporter import (
    build_combined_verification_excel_bytes,
)


def _init_session_defaults() -> None:
    """Initializes default session state values and applies any pending coordinated-mix widget sync."""
    if "comb_system_cfg" not in st.session_state:
        st.session_state["comb_system_cfg"] = CombinedSystemConfig(
            enable_grid=True,
            grid_limit_kw=180.0,
            enable_solar=False,
            enable_battery=False,
            enable_generator=False,
            enable_financials=False,
        )
    if "comb_rules_cfg" not in st.session_state:
        st.session_state["comb_rules_cfg"] = InteractionRulesConfig()
    if "comb_fin_cfg" not in st.session_state:
        st.session_state["comb_fin_cfg"] = CombinedFinancialConfig()

    pending_sync = st.session_state.pop("comb_pending_mix_widget_sync", None)
    if isinstance(pending_sync, dict):
        for sk, sv in pending_sync.items():
            st.session_state[sk] = sv

    defaults = {
        "tab1_active_source": "csv",
        "comb_load_source_mode": "CSV Upload",
        "comb_dispatch_timeframe": "7D",
        # Global Overview Switches: All add-on modules start OFF
        "comb_enable_solar_toggle": False,
        "comb_enable_battery_toggle": False,
        "comb_enable_generator_toggle": False,
        "comb_enable_financials_toggle": False,
        # Solar defaults (Amsterdam)
        "comb_solar_site_name": "Amsterdam, Netherlands",
        "comb_solar_preset_choice": "Amsterdam (Default GPS)",
        "comb_solar_lat": 52.3676,
        "comb_solar_lon": 4.9041,
        # Dual-Sizing mode selections
        "comb_bess_sizing_mode": "Coupled (With active Solar / Generator & Rules)",
        "comb_gen_sizing_mode": "Coupled (With active Solar / Battery & Rules)",
        "comb_mix_strategy_key": "hybrid_2h",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _get_active_load_series() -> Tuple[LoadSeries2025, str]:
    """Retrieves or normalizes the active 35,040-step load profile for 2025 from session state."""
    if (
        "active_load_series_2025" in st.session_state
        and isinstance(st.session_state["active_load_series_2025"], LoadSeries2025)
    ):
        fname = st.session_state.get("active_csv_filename", "Active Baseline Profile")
        label = f"CSV: {fname}" if st.session_state.get("tab1_active_source") == "csv" else "Synthetic Load Profile"
        st.session_state["comb_active_load_series"] = st.session_state["active_load_series_2025"]
        st.session_state["comb_active_load_label"] = label
        return st.session_state["active_load_series_2025"], label

    if "active_csv_df" in st.session_state and isinstance(st.session_state["active_csv_df"], pd.DataFrame):
        df_csv = st.session_state["active_csv_df"]
        if not df_csv.empty:
            fname = st.session_state.get("active_csv_filename", "Uploaded Meter File")
            p_col = "Total_Demand_kW" if "Total_Demand_kW" in df_csv.columns else df_csv.columns[1]
            t_col = "timestamp" if "timestamp" in df_csv.columns else None
            try:
                load_norm, _ = normalize_load_profile_2025(raw_df=df_csv, power_col=p_col, time_col=t_col)
                st.session_state["active_load_series_2025"] = load_norm
                st.session_state["comb_active_load_series"] = load_norm
                st.session_state["comb_active_load_label"] = f"CSV: {fname}"
                return load_norm, f"CSV: {fname}"
            except Exception:
                pass

    if (
        "comb_active_load_series" in st.session_state
        and isinstance(st.session_state["comb_active_load_series"], LoadSeries2025)
    ):
        return (
            st.session_state["comb_active_load_series"],
            st.session_state.get("comb_active_load_label", "Active Load Profile"),
        )

    load_bench = synthesize_benchmark_load_profile_2025(nominal_peak_kw=250.0)
    st.session_state["active_load_series_2025"] = load_bench
    st.session_state["comb_active_load_series"] = load_bench
    st.session_state["comb_active_load_label"] = "Commercial Facility (250 kW Peak)"
    return load_bench, "Commercial Facility (250 kW Peak)"


def _load_fingerprint(load_series: LoadSeries2025) -> Tuple[int, float, float]:
    """Returns a fast O(1) tuple fingerprint of the active 35,040-step load profile."""
    return (
        len(load_series.power_kw),
        round(float(load_series.total_energy_kwh), 2),
        round(float(load_series.peak_demand_kw), 2),
    )


def _rules_tuple(rules_cfg: InteractionRulesConfig) -> Tuple:
    """Returns an immutable tuple of the interaction rules for fingerprint comparison."""
    return (
        rules_cfg.rule1_peak_priority,
        rules_cfg.rule2_battery_strategy,
        round(float(rules_cfg.peak_reserve_soc_pct), 2),
        rules_cfg.rule3_charging_sources,
    )


def _physical_sys_tuple(sys_cfg: CombinedSystemConfig) -> Tuple:
    """Returns an immutable tuple of all physical system parameters (excluding financials)."""
    return (
        ENGINE_VERSION,
        bool(sys_cfg.enable_grid),
        round(float(sys_cfg.grid_limit_kw), 2),
        bool(sys_cfg.enable_solar),
        round(float(sys_cfg.latitude), 4),
        round(float(sys_cfg.longitude), 4),
        round(float(sys_cfg.tilt_deg), 2),
        round(float(sys_cfg.azimuth_deg), 2),
        sys_cfg.solar_sizing_method,
        round(float(sys_cfg.solar_kwp), 2),
        round(float(sys_cfg.panel_wp), 1),
        round(float(sys_cfg.dc_ac_ratio), 3),
        round(float(sys_cfg.target_consumption_share_pct), 2),
        round(float(sys_cfg.inverter_ac_limit_kw), 2),
        round(float(sys_cfg.inverter_efficiency_pct), 2),
        bool(sys_cfg.enable_battery),
        round(float(sys_cfg.battery_capacity_kwh), 2),
        round(float(sys_cfg.battery_power_kw), 2),
        round(float(sys_cfg.min_soc_pct), 2),
        round(float(sys_cfg.max_soc_pct), 2),
        round(float(sys_cfg.round_trip_efficiency_pct), 2),
        bool(sys_cfg.enable_generator),
        round(float(sys_cfg.generator_rated_kw), 2),
        round(float(sys_cfg.generator_min_load_pct), 2),
        str(sys_cfg.fuel_type),
        round(float(sys_cfg.gen_min_runtime_minutes), 1),
    )


def _sync_shared_load_series() -> None:
    """Invalidates cached simulation outputs when the underlying load profile changes or engine updates."""
    load_series, _ = _get_active_load_series()
    fingerprint = _load_fingerprint(load_series)
    if (
        st.session_state.get("comb_load_fingerprint") != fingerprint
        or st.session_state.get("comb_engine_version") != ENGINE_VERSION
    ):
        st.session_state["comb_load_fingerprint"] = fingerprint
        st.session_state["comb_engine_version"] = ENGINE_VERSION
        st.session_state.pop("comb_sandbox_result", None)
        st.session_state.pop("comb_dispatch_fp", None)
        st.session_state.pop("comb_bess_sizing_fp", None)
        st.session_state.pop("comb_cached_dual_bess", None)
        st.session_state.pop("comb_gen_sizing_fp", None)
        st.session_state.pop("comb_cached_dual_gen", None)
        st.session_state.pop("comb_cached_excel_bytes", None)


def _activate_module_callback(toggle_key: str) -> None:
    """Callback for 1-click module activation buttons inside inactive sub-tabs."""
    st.session_state[toggle_key] = True
    if (
        toggle_key == "comb_enable_battery_toggle"
        and not st.session_state.get("comb_bess_user_configured", False)
    ):
        cfg: Optional[CombinedSystemConfig] = st.session_state.get("comb_system_cfg")
        dual_bess: Optional[DualBatterySizingResult] = st.session_state.get("comb_cached_dual_bess")
        if cfg is not None and dual_bess is not None and dual_bess.coupled_100_kwh > 0.0:
            cfg.battery_capacity_kwh = max(10.0, float(dual_bess.coupled_100_kwh))
            cfg.battery_power_kw = max(5.0, float(dual_bess.coupled_100_kw))
            units, unit_kwh = determine_smart_modular_units(cfg.battery_capacity_kwh)
            st.session_state["comb_bess_unit_count"] = units
            st.session_state["comb_bess_unit_kwh"] = unit_kwh
            st.session_state["comb_bess_unit_count_num"] = units
            st.session_state["comb_bess_unit_kwh_num"] = unit_kwh
            st.session_state["comb_battery_power_kw_num"] = cfg.battery_power_kw
            st.session_state["comb_bess_user_configured"] = True
    st.session_state.pop("comb_cached_excel_bytes", None)


def _apply_solar_quick_share(share_pct: float) -> None:
    """Callback for Solar quick share buttons (20%, 40%, 60%, 100%)."""
    cfg: CombinedSystemConfig = st.session_state["comb_system_cfg"]
    cfg.solar_sizing_method = "target_share_pct"
    cfg.target_consumption_share_pct = float(share_pct)
    cfg.inverter_ac_limit_kw = 0.0
    st.session_state["comb_solar_sizing_radio"] = "% of Annual Consumption"
    st.session_state["comb_solar_target_share_num"] = float(share_pct)
    st.session_state.pop("comb_solar_inv_ac_limit_num", None)
    st.session_state.pop("comb_cached_excel_bytes", None)


def _apply_bess_quick_size(cap_kwh: float, p_kw: float) -> None:
    """Callback for Battery Dual-Sizing quick buttons (100%, 80%, 50%)."""
    cfg: CombinedSystemConfig = st.session_state["comb_system_cfg"]
    cfg.battery_capacity_kwh = max(10.0, float(cap_kwh))
    cfg.battery_power_kw = max(5.0, float(p_kw))
    units, unit_kwh = determine_smart_modular_units(cfg.battery_capacity_kwh)
    st.session_state["comb_bess_unit_count"] = units
    st.session_state["comb_bess_unit_kwh"] = unit_kwh
    st.session_state["comb_bess_unit_count_num"] = units
    st.session_state["comb_bess_unit_kwh_num"] = unit_kwh
    st.session_state["comb_battery_power_kw_num"] = cfg.battery_power_kw
    st.session_state["comb_bess_user_configured"] = True
    st.session_state.pop("comb_cached_excel_bytes", None)


def _apply_gen_quick_size(p_kw: float) -> None:
    """Callback for Generator Dual-Sizing quick buttons (100%, 80%, 50%)."""
    cfg: CombinedSystemConfig = st.session_state["comb_system_cfg"]
    cfg.generator_rated_kw = max(10.0, float(p_kw))
    st.session_state["comb_generator_rated_kw_num"] = cfg.generator_rated_kw
    st.session_state.pop("comb_cached_excel_bytes", None)


# ======================================================================================
# LEVEL 1: System Overview Bar (Top)
# ======================================================================================

def render_level1_overview_bar(load_series: LoadSeries2025, load_label: str) -> None:
    """
    Renders the top System Overview Bar:
      - Contracted Grid Limit (kW) input right next to measured Peak Demand (kW)
      - Global activation toggles for Solar, Battery, Generator, and Financials
    """
    cur_sys: CombinedSystemConfig = st.session_state["comb_system_cfg"]
    orig_peak_kw = float(load_series.peak_demand_kw)

    with st.container(border=True):
        c_grid, c_peak, c_sol, c_bat, c_gen, c_fin = st.columns([1.4, 1.2, 0.85, 0.85, 0.85, 0.85])

        with c_grid:
            with st.form("comb_grid_limit_form"):
                raw_grid_limit = float(cur_sys.grid_limit_kw)
                max_grid_limit = max(100000.0, raw_grid_limit * 2, orig_peak_kw * 2)
                safe_grid_limit = min(max_grid_limit, max(10.0, raw_grid_limit))
                grid_limit_val = st.number_input(
                    "Grid Limit (kW)",
                    min_value=10.0,
                    max_value=max_grid_limit,
                    value=safe_grid_limit,
                    step=10.0,
                    key="comb_grid_limit_input",
                )
                gl_submitted = st.form_submit_button(
                    "Apply Limit",
                    use_container_width=True,
                )
            if gl_submitted:
                cur_sys.grid_limit_kw = float(grid_limit_val)
                st.session_state.pop("comb_cached_excel_bytes", None)

        overload_kw = max(0.0, orig_peak_kw - float(cur_sys.grid_limit_kw))
        with c_peak:
            st.metric(
                label="Peak Demand",
                value=f"{orig_peak_kw:,.1f} kW",
                delta=(
                    f"+{overload_kw:,.1f} kW above Grid Limit"
                    if overload_kw > 0.05
                    else "Within Grid Limit"
                ),
                delta_color="inverse" if overload_kw > 0.05 else "normal",
            )

        with c_sol:
            st.write("")
            en_sol = st.toggle(
                ":material/solar_power: Solar",
                key="comb_enable_solar_toggle",
            )
            cur_sys.enable_solar = bool(en_sol)

        with c_bat:
            st.write("")
            en_bat = st.toggle(
                ":material/battery_charging_full: Battery",
                key="comb_enable_battery_toggle",
            )
            cur_sys.enable_battery = bool(en_bat)

        with c_gen:
            st.write("")
            en_gen = st.toggle(
                ":material/power: Generator",
                key="comb_enable_generator_toggle",
            )
            cur_sys.enable_generator = bool(en_gen)

        with c_fin:
            st.write("")
            en_fin = st.toggle(
                ":material/payments: Financials",
                key="comb_enable_financials_toggle",
            )
            cur_sys.enable_financials = bool(en_fin)


# ======================================================================================
# LEVEL 2 — SUBTAB 1: Consumption (Always Active)
# ======================================================================================

REFERENCE_SCENARIOS: dict = {
    "Commercial Bakery / Office (250 kW Peak / Enexis Netbeheer)": {
        "type": "commercial_hvac",
        "peak_kw": 250.0,
        "grid_limit_kw": 180.0,
    },
    "Rotterdam WKO Heat Pump (110 kW Peak / Stedin Netbeheer)": {
        "type": "commercial_hvac",
        "peak_kw": 110.0,
        "grid_limit_kw": 75.0,
    },
    "Heavy Industrial Logistics (550 kW Peak / Liander Netbeheer)": {
        "type": "commercial_hvac",
        "peak_kw": 550.0,
        "grid_limit_kw": 380.0,
    },
    "Bodegas Salentein Mendoza (430 kW Peak / EDEMSA)": {
        "type": "edemsa_salentein",
        "peak_kw": 691.0,
        "grid_limit_kw": 430.0,
    },
}


def render_subtab1_consumption(load_series: LoadSeries2025) -> None:
    """
    Renders Subtab 1: Consumption (1-Click Reference Scenarios, CSV upload, and 4 Base KPIs).
    """
    cur_sys: CombinedSystemConfig = st.session_state["comb_system_cfg"]
    load_kw = load_series.power_kw
    ann_kwh = float(load_series.total_energy_kwh)
    peak_kw = float(load_series.peak_demand_kw)
    avg_kw = float(np.mean(load_kw)) if len(load_kw) > 0 else 0.0
    over_arr = np.maximum(0.0, load_kw - float(cur_sys.grid_limit_kw))
    over_kw = float(np.max(over_arr)) if len(over_arr) > 0 else 0.0
    over_hrs = float(np.sum(over_arr > 0.05) * 0.25)
    over_kwh = float(np.sum(over_arr) * 0.25)

    # 4 Base KPIs
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        render_kpi_card(
            title="Annual Consumption",
            value=f"{ann_kwh:,.0f} kWh",
            subtext="Total annual electricity demand",
            status="default",
        )
    with k2:
        render_kpi_card(
            title="Peak Demand",
            value=f"{peak_kw:,.1f} kW",
            subtext="Highest 15-minute load spike",
            status="default",
        )
    with k3:
        render_kpi_card(
            title="Average Load",
            value=f"{avg_kw:,.1f} kW",
            subtext=f"Load factor: {(avg_kw / max(1.0, peak_kw) * 100.0):.1f}%",
            status="default",
        )
    with k4:
        render_kpi_card(
            title="Overload above Grid Limit",
            value=f"{over_kw:,.1f} kW ({over_hrs:,.1f} hrs)",
            subtext=f"{over_kwh:,.0f} kWh above {cur_sys.grid_limit_kw:,.0f} kW limit",
            status="ok" if over_kw <= 0.05 else "alert",
        )

    # Reference Profiles
    with st.container(border=True):
        st.markdown("##### :material/dataset: Example Profiles")
        with st.form("comb_ref_scenario_form"):
            sc1, sc_btn = st.columns([2.5, 1.2])
            with sc1:
                ref_names = list(REFERENCE_SCENARIOS.keys())
                sel_sc = st.selectbox(
                    "Select Profile",
                    options=ref_names,
                    index=0,
                    key="comb_ref_scenario_select",
                    help="Loads a ready-made consumption profile and grid limit.",
                )
            with sc_btn:
                st.write("")
                apply_sc = st.form_submit_button(
                    "Load Profile",
                    icon=":material/download:",
                    use_container_width=True,
                )

        if apply_sc and sel_sc in REFERENCE_SCENARIOS:
            sc_info = REFERENCE_SCENARIOS[sel_sc]
            cur_sys.grid_limit_kw = float(sc_info["grid_limit_kw"])
            st.session_state["comb_grid_limit_num"] = cur_sys.grid_limit_kw
            if sc_info["type"] == "edemsa_salentein":
                bench_profile = synthesize_edemsa_salentein_load_profile_2025()
            else:
                bench_profile = synthesize_benchmark_load_profile_2025(
                    profile_type=sc_info["type"],
                    nominal_peak_kw=float(sc_info["peak_kw"]),
                )
            st.session_state["active_load_series_2025"] = bench_profile
            st.session_state["comb_active_load_series"] = bench_profile
            st.session_state["active_csv_filename"] = sel_sc
            st.session_state["comb_active_load_label"] = f"Reference: {sel_sc}"
            st.session_state["tab1_active_source"] = "benchmark"
            _sync_shared_load_series()
            st.rerun()

    st.write("")
    render_tab1_consumption(key_prefix="comb_tab1_cons")
    _sync_shared_load_series()


# ======================================================================================
# LEVEL 2 — SUBTAB 2: Solar (Grayed Out Until Activated)
# ======================================================================================

@st.fragment
def _render_solar_map_fragment(eff_lat: float, eff_lon: float, site_disp: str, is_active: bool) -> None:
    """Renders an interactive Folium map fragment so panning/zooming never reloads the app."""
    if not _HAS_FOLIUM:
        st.info(
            f"Map preview unavailable (`folium` / `streamlit-folium` not installed). "
            f"Active Pin: **{site_disp}** ({eff_lat:.4f}°N, {eff_lon:.4f}°E).",
            icon=":material/map:",
        )
        return

    st.caption("Click anywhere on the map to move the Solar location pin and recalculate PVGIS irradiance.")
    m = folium.Map(
        location=[eff_lat, eff_lon],
        zoom_start=8,
        tiles="OpenStreetMap",
        control_scale=True,
    )
    folium.Marker(
        [eff_lat, eff_lon],
        tooltip=f"{site_disp} ({eff_lat:.4f}°, {eff_lon:.4f}°)",
        popup=site_disp,
        icon=folium.Icon(color="orange", icon="sun", prefix="fa"),
    ).add_to(m)

    map_out = st_folium(
        m,
        width="100%",
        height=300,
        returned_objects=["last_clicked"],
        key="comb_solar_interactive_map",
    )
    if is_active and map_out and map_out.get("last_clicked"):
        c_lat = float(map_out["last_clicked"]["lat"])
        c_lon = float(map_out["last_clicked"]["lng"])
        click_sig = (round(c_lat, 5), round(c_lon, 5))
        prev_sig = st.session_state.get("comb_solar_last_map_click")
        if click_sig != prev_sig and (abs(c_lat - eff_lat) > 1e-4 or abs(c_lon - eff_lon) > 1e-4):
            st.session_state["comb_solar_last_map_click"] = click_sig
            st.session_state["comb_solar_lat"] = c_lat
            st.session_state["comb_solar_lon"] = c_lon
            st.session_state["comb_solar_site_name"] = f"Map Pin ({c_lat:.4f}°, {c_lon:.4f}°)"
            st.session_state["comb_solar_preset_choice"] = "Custom GPS Coordinates"
            cur_sys_ref: Optional[CombinedSystemConfig] = st.session_state.get("comb_system_cfg")
            if cur_sys_ref is not None:
                cur_sys_ref.latitude = c_lat
                cur_sys_ref.longitude = c_lon
            st.session_state.pop("comb_cached_excel_bytes", None)
            st.rerun()


def render_subtab2_solar(load_series: LoadSeries2025) -> None:
    """
    Renders Subtab 2: Solar
      - 1-Click Activate button if inactive
      - Location (City search, Presets, Manual GPS & Interactive Map) + EU PVGIS source line
      - Dual Quick-Sizing (% of Annual Consumption: 20/40/60/100% vs. Direct Size kWp)
      - Blue live formula box + Plain-language Solar & Weather Explanation Expander
      - Inverter AC Limit (kW) & Inverter Efficiency (%) (Default: 98%)
    """
    cur_sys: CombinedSystemConfig = st.session_state["comb_system_cfg"]
    is_active = bool(cur_sys.enable_solar)
    ann_kwh = float(load_series.total_energy_kwh)

    if not is_active:
        with st.container(border=True):
            b_col1, b_col2 = st.columns([2.5, 1.2])
            with b_col1:
                st.markdown(
                    "**Solar is currently inactive.** Click **Activate Solar** to include solar generation in your system."
                )
            with b_col2:
                st.button(
                    "Activate Solar",
                    icon=":material/power_settings_new:",
                    type="primary",
                    use_container_width=True,
                    key="comb_btn_activate_solar",
                    on_click=_activate_module_callback,
                    args=("comb_enable_solar_toggle",),
                )

    with st.container(border=True):
        st.markdown("##### :material/solar_power: Solar Settings")

        curr_lat = float(st.session_state.get("comb_solar_lat", 52.3676))
        curr_lon = float(st.session_state.get("comb_solar_lon", 4.9041))

        # 1. Location: City Search, Presets & Manual GPS Coordinates (Default: Amsterdam)
        with st.form("comb_solar_location_form"):
            loc_c1, loc_c2 = st.columns(2)
            with loc_c1:
                search_query = st.text_input(
                    "City Search",
                    value=st.session_state.get("comb_solar_search_input", ""),
                    placeholder="Type city (e.g. Amsterdam, Berlin, Madrid)...",
                    disabled=not is_active,
                    key="comb_solar_search_input",
                )
            with loc_c2:
                preset_options = list(SOLAR_SITE_PRESETS.keys()) + ["Custom GPS Coordinates"]
                curr_preset = st.session_state.get("comb_solar_preset_choice", "Amsterdam (Default GPS)")
                preset_idx = preset_options.index(curr_preset) if curr_preset in preset_options else 0
                preset_choice = st.selectbox(
                    "Location Presets (Default: Amsterdam)",
                    options=preset_options,
                    index=preset_idx,
                    disabled=not is_active,
                    key="comb_solar_preset_select",
                )

            gps_c1, gps_c2, loc_btn = st.columns([1.2, 1.2, 1.0])
            with gps_c1:
                lat_input = st.number_input(
                    "Latitude (°N)",
                    min_value=-90.0,
                    max_value=90.0,
                    value=curr_lat,
                    step=0.01,
                    format="%.4f",
                    disabled=not is_active,
                )
            with gps_c2:
                lon_input = st.number_input(
                    "Longitude (°E)",
                    min_value=-180.0,
                    max_value=180.0,
                    value=curr_lon,
                    step=0.01,
                    format="%.4f",
                    disabled=not is_active,
                )
            with loc_btn:
                st.write("")
                loc_submitted = st.form_submit_button(
                    "Apply Location",
                    use_container_width=True,
                    disabled=not is_active,
                )

        if loc_submitted:
            clean_q = (search_query or "").strip()
            manual_changed = (
                abs(float(lat_input) - curr_lat) > 1e-5
                or abs(float(lon_input) - curr_lon) > 1e-5
            )
            preset_changed = (
                preset_choice in SOLAR_SITE_PRESETS
                and preset_choice != st.session_state.get("comb_solar_preset_choice")
            )
            search_changed = (
                len(clean_q) >= 2
                and clean_q != st.session_state.get("comb_solar_last_search", "")
            )

            if preset_changed:
                p_data = SOLAR_SITE_PRESETS[preset_choice]
                st.session_state["comb_solar_lat"] = float(p_data["latitude"])
                st.session_state["comb_solar_lon"] = float(p_data["longitude"])
                st.session_state["comb_solar_site_name"] = p_data["name"]
                st.session_state["comb_solar_preset_choice"] = preset_choice
            elif search_changed:
                search_results = search_locations_open_meteo(clean_q, count=1)
                if search_results:
                    chosen = search_results[0]
                    st.session_state["comb_solar_lat"] = float(chosen["lat"])
                    st.session_state["comb_solar_lon"] = float(chosen["lon"])
                    st.session_state["comb_solar_site_name"] = chosen["display_name"]
                    st.session_state["comb_solar_preset_choice"] = "Custom GPS Coordinates"
                st.session_state["comb_solar_last_search"] = clean_q
            elif manual_changed:
                st.session_state["comb_solar_lat"] = float(lat_input)
                st.session_state["comb_solar_lon"] = float(lon_input)
                st.session_state["comb_solar_site_name"] = (
                    f"Custom ({float(lat_input):.4f}°N, {float(lon_input):.4f}°E)"
                )
                st.session_state["comb_solar_preset_choice"] = "Custom GPS Coordinates"
            elif preset_choice in SOLAR_SITE_PRESETS:
                p_data = SOLAR_SITE_PRESETS[preset_choice]
                st.session_state["comb_solar_lat"] = float(p_data["latitude"])
                st.session_state["comb_solar_lon"] = float(p_data["longitude"])
                st.session_state["comb_solar_site_name"] = p_data["name"]
                st.session_state["comb_solar_preset_choice"] = preset_choice

            st.session_state.pop("comb_cached_excel_bytes", None)
            st.rerun()

        eff_lat = float(st.session_state.get("comb_solar_lat", 52.3676))
        eff_lon = float(st.session_state.get("comb_solar_lon", 4.9041))
        _, spec_yield, _ = get_unit_solar_generation_profile(
            latitude=eff_lat,
            longitude=eff_lon,
            tilt_deg=30.0,
            azimuth_deg=180.0 if eff_lat >= 0.0 else 0.0,
            dc_ac_ratio=cur_sys.dc_ac_ratio,
        )
        site_disp = st.session_state.get("comb_solar_site_name", "Amsterdam, Netherlands")
        st.caption(
            f"Data source: **EU PVGIS (ERA5 15-min TMY)** | Location: **{site_disp}** "
            f"(`{eff_lat:.4f}°N, {eff_lon:.4f}°E`) | Specific Yield: **{spec_yield:,.0f} kWh/kWp/year**"
        )

        with st.expander("Location Map & Pin Selection", expanded=False, icon=":material/map:"):
            _render_solar_map_fragment(
                eff_lat=eff_lat,
                eff_lon=eff_lon,
                site_disp=site_disp,
                is_active=is_active,
            )

        st.markdown("---")

        # 2. Dual Quick-Sizing & Manual Input (st.form encapsulated)
        st.caption("Quick Sizing Presets (% of Annual Consumption):")
        qb1, qb2, qb3, qb4 = st.columns(4)
        qb1.button(
            "20%", use_container_width=True, disabled=not is_active,
            key="comb_sol_q20", on_click=_apply_solar_quick_share, args=(20.0,),
        )
        qb2.button(
            "40%", use_container_width=True, disabled=not is_active,
            key="comb_sol_q40", on_click=_apply_solar_quick_share, args=(40.0,),
        )
        qb3.button(
            "60%", use_container_width=True, disabled=not is_active,
            key="comb_sol_q60", on_click=_apply_solar_quick_share, args=(60.0,),
        )
        qb4.button(
            "100%", use_container_width=True, disabled=not is_active,
            key="comb_sol_q100", on_click=_apply_solar_quick_share, args=(100.0,),
        )

        preview_kwp = (
            round((ann_kwh * (float(cur_sys.target_consumption_share_pct) / 100.0)) / max(100.0, spec_yield), 1)
            if cur_sys.solar_sizing_method == "target_share_pct"
            else round(float(cur_sys.solar_kwp), 1)
        )
        default_inv_kw = (
            float(cur_sys.inverter_ac_limit_kw)
            if cur_sys.inverter_ac_limit_kw > 0.0
            else round(preview_kwp / max(1.0, cur_sys.dc_ac_ratio), 1)
        )

        with st.form("comb_solar_form"):
            sz_c1, sz_c2, sz_c3 = st.columns(3)
            with sz_c1:
                st.markdown("**Sizing Mode & Energy Share:**")
                sizing_mode_label = st.radio(
                    "Sizing Mode",
                    options=["% of Annual Consumption", "Direct Size (kWp)"],
                    index=0 if cur_sys.solar_sizing_method == "target_share_pct" else 1,
                    horizontal=True,
                    disabled=not is_active,
                    key="comb_solar_sizing_radio",
                )
                target_share_val = st.number_input(
                    "Share of Consumption (%)",
                    min_value=5.0,
                    max_value=250.0,
                    value=float(cur_sys.target_consumption_share_pct),
                    step=5.0,
                    disabled=not is_active,
                    key="comb_solar_target_share_num",
                    help="Percentage of total annual electricity demand to be supplied by solar.",
                )
            with sz_c2:
                st.markdown("**Size & Inverter Limit:**")
                raw_solar_kwp = float(cur_sys.solar_kwp)
                max_solar_kwp = max(100000.0, raw_solar_kwp * 2)
                safe_solar_kwp = min(max_solar_kwp, max(1.0, raw_solar_kwp))
                direct_kwp_val = st.number_input(
                    "Direct Size (kWp)",
                    min_value=1.0,
                    max_value=max_solar_kwp,
                    value=safe_solar_kwp,
                    step=10.0,
                    disabled=not is_active,
                    key="comb_solar_direct_kwp_num",
                    help="Direct nameplate DC capacity in kWp.",
                )
                raw_inv_ac = max(0.0, float(default_inv_kw))
                max_inv_ac = max(100000.0, raw_inv_ac * 2)
                safe_inv_ac = min(max_inv_ac, max(0.0, raw_inv_ac))
                inv_ac_limit_val = st.number_input(
                    "Inverter AC Limit (kW)",
                    min_value=0.0,
                    max_value=max_inv_ac,
                    value=safe_inv_ac,
                    step=10.0,
                    disabled=not is_active,
                    key="comb_solar_inv_ac_limit_num",
                    help="Maximum continuous AC feed-in power to the site/grid.",
                )
            with sz_c3:
                st.markdown("**Efficiency & Apply:**")
                inv_eff_val = st.slider(
                    "Inverter Efficiency (%)",
                    min_value=85,
                    max_value=100,
                    value=int(round(cur_sys.inverter_efficiency_pct)),
                    step=1,
                    disabled=not is_active,
                    key="comb_solar_inv_eff_num",
                )
                st.write("")
                sol_submitted = st.form_submit_button(
                    "Update Solar Settings & Run Simulation",
                    icon=":material/refresh:",
                    type="primary",
                    use_container_width=True,
                    disabled=not is_active,
                )

        if sol_submitted:
            sizing_method_key = "target_share_pct" if sizing_mode_label == "% of Annual Consumption" else "direct_kwp"
            cur_sys.solar_sizing_method = sizing_method_key
            cur_sys.target_consumption_share_pct = float(target_share_val)
            cur_sys.solar_kwp = float(direct_kwp_val)
            cur_sys.inverter_ac_limit_kw = float(inv_ac_limit_val)
            cur_sys.inverter_efficiency_pct = float(inv_eff_val)
            st.session_state.pop("comb_cached_excel_bytes", None)

        cur_sys.latitude = eff_lat
        cur_sys.longitude = eff_lon

        solar_deriv = derive_solar_sizing_and_formula(
            annual_consumption_kwh=ann_kwh,
            specific_yield_kwh_per_kwp=spec_yield,
            sizing_method=cur_sys.solar_sizing_method,
            direct_kwp=float(cur_sys.solar_kwp),
            target_share_pct=float(cur_sys.target_consumption_share_pct),
            panel_wp=cur_sys.panel_wp,
            dc_ac_ratio=cur_sys.dc_ac_ratio,
            enable_solar=True,
            inverter_ac_limit_kw=float(cur_sys.inverter_ac_limit_kw),
            inverter_efficiency_pct=float(cur_sys.inverter_efficiency_pct),
        )
        st.info(solar_deriv.formula_text, icon=":material/calculate:")

        with st.expander("How Solar Sizing & Weather Data Work", expanded=False, icon=":material/help_outline:"):
            st.markdown(
                f"""
**1. Quick Sizing Presets (`20% / 40% / 60% / 100%`)**  
Each percentage scales the PV array so its expected **annual electricity generation** equals that share of your annual facility consumption (`{ann_kwh:,.0f} kWh/yr`):
- `Target Solar Generation (kWh/yr) = Annual Consumption (kWh/yr) × Target Share (%)`
- `Required PV Size (kWp) = Target Solar Generation / Specific Yield ({spec_yield:,.0f} kWh/kWp/yr)`

**2. Why 100% Annual Solar Does Not Mean 100% Direct Self-Consumption**  
Solar irradiance peaks around midday and during summer months, whereas electricity demand also occurs at night, early mornings, and overcast winter weeks. Without a battery or generator, daytime surpluses above your live load are exported while evening/winter peaks still require Grid, Battery, or Generator power.  
*Tip:* In the bottom **Power Flow & Battery Level** chart, click **Solar Total Potential (kW)** in the legend to compare maximum possible PV output against **Solar Direct (kW)** actually absorbed on-site.

**3. Weather Data Basis (Typical Meteorological Year — TMY)**  
Solar generation is simulated from **EU PVGIS (ERA5) 15-minute TMY** profiles for your active GPS pin (`{eff_lat:.4f}°N, {eff_lon:.4f}°E`). A TMY dataset combines statistically typical months from multi-year satellite/reanalysis weather records to represent normal seasonal sunlight and temperature rather than a single outlier weather year.
                """.strip()
            )


# ======================================================================================
# LEVEL 2 — SUBTAB 3: Battery (Dual-Sizing & 4-Bottleneck Diagnostic Table)
# ======================================================================================

@st.fragment
def _render_battery_reference_fragment(dual_bess: DualBatterySizingResult, is_active: bool) -> None:
    """Renders the interactive Mode A / Mode B reference box inside an isolated fragment to prevent full app reruns."""
    st.markdown("##### :material/battery_charging_full: 1. Recommended Battery Size")
    st.caption(
        "Minimum battery size needed to avoid exceeding the Grid Limit."
    )

    mode_options = [
        "Mode A – Standalone (Battery only)",
        "Mode B – Coupled (With active Solar / Generator & Rules)",
    ]
    cur_mode = st.session_state.get("comb_bess_ref_mode", "Mode B – Coupled (With active Solar / Generator & Rules)")
    sel_idx = 0 if cur_mode.startswith("Mode A") else 1
    selected_mode = st.radio(
        "Quick-Sizing Reference Mode",
        options=mode_options,
        index=sel_idx,
        horizontal=True,
        disabled=not is_active,
        key="comb_bess_ref_mode_radio",
    )
    st.session_state["comb_bess_ref_mode"] = selected_mode
    is_sa = selected_mode.startswith("Mode A")

    req_gross = dual_bess.standalone_100_kwh if is_sa else dual_bess.coupled_100_kwh
    req_usable = dual_bess.standalone_usable_kwh if is_sa else dual_bess.coupled_usable_kwh
    req_power = dual_bess.standalone_100_kw if is_sa else dual_bess.coupled_100_kw
    req_duration = dual_bess.standalone_cluster_duration_hrs if is_sa else dual_bess.coupled_cluster_duration_hrs

    cur_sys_ref: Optional[CombinedSystemConfig] = st.session_state.get("comb_system_cfg")
    cur_rules_ref: Optional[InteractionRulesConfig] = st.session_state.get("comb_rules_cfg")
    if cur_sys_ref is not None and cur_rules_ref is not None and not is_sa:
        r1_lbl = RULE1_OPTIONS.get(cur_rules_ref.rule1_peak_priority, cur_rules_ref.rule1_peak_priority)
        r2_lbl = RULE2_OPTIONS.get(cur_rules_ref.rule2_battery_strategy, cur_rules_ref.rule2_battery_strategy)
        r3_lbl = RULE3_OPTIONS.get(cur_rules_ref.rule3_charging_sources, cur_rules_ref.rule3_charging_sources)
        active_partners: List[str] = []
        if cur_sys_ref.enable_solar:
            active_partners.append("Solar")
        if cur_sys_ref.enable_generator and cur_sys_ref.generator_rated_kw > 0:
            active_partners.append(f"Generator ({cur_sys_ref.generator_rated_kw:,.0f} kW)")
        partners_str = " + ".join(active_partners) if active_partners else "Grid Only"
        st.info(
            f"**Active Sizing Assumptions ({partners_str}):** "
            f"**Rule 1:** {r1_lbl} | **Rule 2:** {r2_lbl} "
            f"(Reserve {cur_rules_ref.peak_reserve_soc_pct:.0f}%) | **Rule 3:** {r3_lbl}",
            icon=":material/rule:",
        )

    # 4 Metric Cards (1:1 with Screenshot 2)
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric(
            label="Min. Required Gross Capacity",
            value=f"{req_gross:,.1f} kWh",
            help="Minimum nameplate storage capacity required to bridge the worst multi-peak deficit cluster.",
        )
    with m2:
        st.metric(
            label="Min. Required Usable Energy",
            value=f"{req_usable:,.1f} kWh",
            help="Net chemical energy needed across the worst consecutive peak cluster.",
        )
    with m3:
        st.metric(
            label="Min. Required Discharge Power",
            value=f"{req_power:,.1f} kW",
            help="Continuous inverter discharge power required to shave the highest peak overload down to the grid limit.",
        )
    with m4:
        st.metric(
            label="Worst Multi-Peak Cluster Duration",
            value=f"{req_duration:.1f} hrs",
            help="Duration of the most demanding overload sequence until battery fully recharges below grid limit.",
        )

    # Quick Apply Buttons (100%, 80%, 50% capacity while keeping 100% required discharge power kW)
    st.caption(
        f"Apply Quick Size ({'Standalone: Battery alone' if is_sa else 'Coupled: With active Solar/Generator'} — "
        "80% / 50% scales kWh storage while preserving 100% peak power kW):"
    )
    q_col1, q_col2, q_col3 = st.columns(3)
    with q_col1:
        if st.button(
            f"Apply 100% Zero-Overload ({req_gross:,.0f} kWh / {req_power:,.1f} kW)",
            icon=":material/bolt:",
            type="primary",
            use_container_width=True,
            disabled=not is_active,
            key="comb_bess_btn_apply_100",
        ):
            _apply_bess_quick_size(req_gross, req_power)
            st.rerun()
    with q_col2:
        q80_kwh = round(req_gross * 0.80, 1)
        q80_kw = float(req_power)
        if st.button(
            f"Apply 80% Quick-Size ({q80_kwh:,.0f} kWh / {q80_kw:,.1f} kW)",
            use_container_width=True,
            disabled=not is_active,
            key="comb_bess_btn_apply_80",
        ):
            _apply_bess_quick_size(q80_kwh, q80_kw)
            st.rerun()
    with q_col3:
        q50_kwh = round(req_gross * 0.50, 1)
        q50_kw = float(req_power)
        if st.button(
            f"Apply 50% Quick-Size ({q50_kwh:,.0f} kWh / {q50_kw:,.1f} kW)",
            use_container_width=True,
            disabled=not is_active,
            key="comb_bess_btn_apply_50",
        ):
            _apply_bess_quick_size(q50_kwh, q50_kw)
            st.rerun()


def render_subtab3_battery(load_series: LoadSeries2025) -> None:
    """
    Renders Subtab 3: Battery
      - 1-Click Activate button if inactive
      - Block 1: Minimum Required Battery Sizing (100% Zero-Overload Reference) with 4 metrics & quick apply
      - Block 2: 3-Column Battery Hardware & Operating Limits Form with single Battery Power (kW)
      - Block 3: Simultaneous Bottleneck Audit & Physical Constraints (status banner + 4 diagnostic cards)
    """
    cur_sys: CombinedSystemConfig = st.session_state["comb_system_cfg"]
    cur_rules: InteractionRulesConfig = st.session_state["comb_rules_cfg"]
    is_active = bool(cur_sys.enable_battery)

    if not is_active:
        with st.container(border=True):
            b_col1, b_col2 = st.columns([2.5, 1.2])
            with b_col1:
                st.markdown(
                    "**Battery is currently inactive.** Click **Activate Battery** to include battery storage in your system."
                )
            with b_col2:
                st.button(
                    "Activate Battery",
                    icon=":material/power_settings_new:",
                    type="primary",
                    use_container_width=True,
                    key="comb_btn_activate_battery",
                    on_click=_activate_module_callback,
                    args=("comb_enable_battery_toggle",),
                )

    # Fingerprint-cached Dual Battery Sizing (runs 35,040-step loop only when upstream parameters change)
    bess_sizing_fp = (
        ENGINE_VERSION,
        _load_fingerprint(load_series),
        bool(cur_sys.enable_grid),
        round(float(cur_sys.grid_limit_kw), 2),
        bool(cur_sys.enable_solar),
        round(float(cur_sys.latitude), 4),
        round(float(cur_sys.longitude), 4),
        cur_sys.solar_sizing_method,
        round(float(cur_sys.solar_kwp), 2),
        round(float(cur_sys.target_consumption_share_pct), 2),
        round(float(cur_sys.inverter_ac_limit_kw), 2),
        round(float(cur_sys.inverter_efficiency_pct), 2),
        bool(cur_sys.enable_generator),
        round(float(cur_sys.generator_rated_kw), 2),
        round(float(cur_sys.generator_min_load_pct), 2),
        round(float(cur_sys.min_soc_pct), 2),
        round(float(cur_sys.max_soc_pct), 2),
        round(float(cur_sys.round_trip_efficiency_pct), 2),
        _rules_tuple(cur_rules),
    )
    if (
        st.session_state.get("comb_bess_sizing_fp") != bess_sizing_fp
        or "comb_cached_dual_bess" not in st.session_state
    ):
        st.session_state["comb_cached_dual_bess"] = compute_dual_battery_sizing(
            load_kw=load_series.power_kw,
            system_cfg=cur_sys,
            rules_cfg=cur_rules,
            is_gap=getattr(load_series, "is_gap", None),
        )
        st.session_state["comb_bess_sizing_fp"] = bess_sizing_fp

    dual_bess = st.session_state["comb_cached_dual_bess"]

    # Block 1: Minimum Required Battery Sizing Reference Box
    with st.container(border=True):
        _render_battery_reference_fragment(dual_bess=dual_bess, is_active=is_active)

    # Block 2: Battery Hardware & Operating Limits Form
    with st.container(border=True):
        st.markdown("##### :material/tune: 2. Battery Size & Settings")
        with st.form("comb_battery_form"):
            lock_05c = st.checkbox(
                "Lock to Standard 0.5 C (2-Hour Storage: Capacity kWh = 2 × Battery Power kW)",
                value=st.session_state.get("comb_bess_lock_05c", False),
                disabled=not is_active,
                key="comb_bess_lock_05c_box",
            )
            col_b1, col_b2, col_b3 = st.columns(3)
            with col_b1:
                st.markdown("**Modular Storage Units:**")
                def_cap = float(cur_sys.battery_capacity_kwh)
                def_units, def_unit_kwh = determine_smart_modular_units(def_cap) if def_cap > 0 else (2, 50.0)

                raw_units = int(st.session_state.get("comb_bess_unit_count", def_units))
                max_units = max(100000, raw_units * 2)
                safe_units = min(max_units, max(1, raw_units))
                unit_count = st.number_input(
                    "Modular Unit Count",
                    min_value=1,
                    max_value=max_units,
                    value=safe_units,
                    step=1,
                    disabled=not is_active,
                    key="comb_bess_unit_count_num",
                )

                raw_unit_kwh = float(st.session_state.get("comb_bess_unit_kwh", def_unit_kwh))
                max_unit_kwh = max(50000.0, raw_unit_kwh * 2)
                safe_unit_kwh = min(max_unit_kwh, max(1.0, raw_unit_kwh))
                cap_per_unit = st.number_input(
                    "Capacity per Unit (kWh)",
                    min_value=1.0,
                    max_value=max_unit_kwh,
                    value=safe_unit_kwh,
                    step=10.0,
                    disabled=not is_active,
                    key="comb_bess_unit_kwh_num",
                )
                total_kwh_disp = float(unit_count * cap_per_unit)
                st.caption(f"Configured Gross Nameplate: **{total_kwh_disp:,.1f} kWh**")

            with col_b2:
                st.markdown("**Inverter Power & Efficiency:**")
                def_kw = round(total_kwh_disp / 2.0, 1) if lock_05c else float(cur_sys.battery_power_kw)
                max_bat_kw = max(100000.0, float(def_kw) * 2)
                safe_bat_kw = min(max_bat_kw, max(1.0, float(def_kw)))
                bat_kw = st.number_input(
                    "Battery Power (kW)",
                    min_value=1.0,
                    max_value=max_bat_kw,
                    value=safe_bat_kw,
                    step=10.0,
                    disabled=not is_active,
                    key="comb_battery_power_kw_num",
                    help="Unified bidirectional power rating for charging and discharging.",
                )
                rte_val = st.slider(
                    "Round-Trip Efficiency (RTE %)",
                    min_value=70,
                    max_value=98,
                    value=int(round(cur_sys.round_trip_efficiency_pct)),
                    step=1,
                    disabled=not is_active,
                    key="comb_battery_rte_slider",
                )

            with col_b3:
                st.markdown("**State of Charge Boundaries:**")
                min_soc_val = st.slider(
                    "SoC Minimum Buffer (%)",
                    min_value=0,
                    max_value=40,
                    value=int(round(cur_sys.min_soc_pct)),
                    step=1,
                    disabled=not is_active,
                    key="comb_battery_min_soc_slider",
                )
                max_soc_val = st.slider(
                    "SoC Maximum Limit (%)",
                    min_value=60,
                    max_value=100,
                    value=int(round(cur_sys.max_soc_pct)),
                    step=1,
                    disabled=not is_active,
                    key="comb_battery_max_soc_slider",
                )
                usable_window = max(0, max_soc_val - min_soc_val)
                st.caption(f"Usable DoD Window: **{usable_window}%**")

            st.write("")
            bess_submitted = st.form_submit_button(
                "Update Battery Settings & Run Simulation",
                icon=":material/refresh:",
                type="primary",
                use_container_width=True,
                disabled=not is_active,
            )

        if bess_submitted:
            st.session_state["comb_bess_lock_05c"] = bool(lock_05c)
            st.session_state["comb_bess_unit_count"] = int(unit_count)
            st.session_state["comb_bess_unit_kwh"] = float(cap_per_unit)
            st.session_state["comb_bess_user_configured"] = True
            new_kwh = float(unit_count * cap_per_unit)
            new_kw = round(new_kwh / 2.0, 1) if lock_05c else float(bat_kw)

            so_c_changed = (
                abs(cur_sys.min_soc_pct - float(min_soc_val)) > 1e-4
                or abs(cur_sys.max_soc_pct - float(max_soc_val)) > 1e-4
                or abs(cur_sys.round_trip_efficiency_pct - float(rte_val)) > 1e-4
            )
            cur_sys.battery_capacity_kwh = new_kwh
            cur_sys.battery_power_kw = new_kw
            cur_sys.min_soc_pct = float(min_soc_val)
            cur_sys.max_soc_pct = float(max_soc_val)
            cur_sys.round_trip_efficiency_pct = float(rte_val)
            if so_c_changed:
                dual_bess = compute_dual_battery_sizing(
                    load_kw=load_series.power_kw,
                    system_cfg=cur_sys,
                    rules_cfg=cur_rules,
                )
                st.session_state["comb_cached_dual_bess"] = dual_bess
            st.session_state.pop("comb_cached_excel_bytes", None)

    # Block 3: Simultaneous Bottleneck Audit & Physical Constraints
    with st.container(border=True):
        cfg_kw = float(cur_sys.battery_power_kw) if is_active else 0.0
        cfg_kwh = float(cur_sys.battery_capacity_kwh) if is_active else 0.0
        req_kw = dual_bess.coupled_100_kw
        req_kwh = dual_bess.coupled_100_kwh
        rech_kw_avail = dual_bess.coupled_recharge_headroom_kw
        rech_kwh_avail = dual_bess.coupled_recharge_headroom_kwh

        pass_power = cfg_kw >= (req_kw - 0.1)
        pass_capacity = cfg_kwh >= (req_kwh - 0.5)
        pass_recharge = dual_bess.controlling_driver_coupled != "Available Recharge Headroom"
        pass_all = pass_power and pass_capacity and pass_recharge and is_active

        # Live utilization insights when prior simulation matches current physical sizing
        sim_cached = st.session_state.get("comb_sandbox_result")
        live_min_soc_pct: Optional[float] = None
        live_cycles: Optional[float] = None
        if (
            sim_cached is not None
            and is_active
            and getattr(sim_cached, "bess_soc_pct", None) is not None
            and abs(float(sim_cached.system_config.battery_capacity_kwh) - cfg_kwh) < 1.0
            and abs(float(sim_cached.system_config.battery_power_kw) - cfg_kw) < 0.5
        ):
            gaps = getattr(load_series, "is_gap", None)
            soc_arr = np.asarray(sim_cached.bess_soc_pct, dtype=float)
            valid_soc = soc_arr[~np.asarray(gaps, dtype=bool)] if gaps is not None and len(gaps) == len(soc_arr) else soc_arr
            if valid_soc.size > 0:
                live_min_soc_pct = float(np.min(valid_soc))
            live_cycles = float(sim_cached.kpis.battery_equivalent_cycles)

        st.markdown("##### :material/fact_check: 3. System Limit Check")
        st.caption("Checks whether inverter discharge power, storage capacity, and recharge headroom cover every peak.")

        if pass_all:
            st.success(
                ":material/check_circle: **Grid Limit Met (Zero Overload)**  \n"
                "Your battery covers every peak above the Grid Limit."
            )
            if live_min_soc_pct is not None and live_min_soc_pct > max(50.0, float(cur_sys.min_soc_pct) + 35.0):
                st.info(
                    f":material/compress: **Battery Oversized (Min SoC {live_min_soc_pct:.1f}% | "
                    f"{live_cycles or 0.0:.1f} cyc/yr)**  \n"
                    f"Over {live_min_soc_pct - float(cur_sys.min_soc_pct):.0f}% of usable capacity stayed untouched all year "
                    "(usually sized around a rare multi-day winter cluster). Visit **5. System Mix & Rules** "
                    "to pair a compact 2h/4h Battery with Generator backup.",
                )
        elif not is_active:
            st.info("Battery is inactive. Activate to check limits.")
        else:
            diag_reasons: List[str] = []
            if not pass_power:
                diag_reasons.append(
                    f"**Inverter Power Bottleneck (`kW`):** Configured **{cfg_kw:,.1f} kW** is below required "
                    f"**{req_kw:,.1f} kW**. Discharge power clips during steep peaks even while battery energy (SoC%) remains."
                )
            if not pass_capacity:
                diag_reasons.append(
                    f"**Energy Capacity Bottleneck (`kWh`):** Configured **{cfg_kwh:,.0f} kWh** is below required "
                    f"**{req_kwh:,.0f} kWh**. Storage depletes down to SoC Min ({cur_sys.min_soc_pct:.0f}%) during sustained peak clusters."
                )
            if not pass_recharge:
                diag_reasons.append(
                    "**Recharge Headroom Deficit:** Available below-limit periods cannot refill all consecutive peaks cleanly without Solar or Generator support."
                )
            reason_body = "  \n".join(diag_reasons) if diag_reasons else "Check the 4 items below."
            st.warning(
                f":material/warning: **Remaining Overload Expected**  \n{reason_body}"
            )

        # 4 Diagnostic Check Cards (1:1 visual match with BESS Sandbox layout)
        chk_col1, chk_col2, chk_col3, chk_col4 = st.columns(4)
        with chk_col1:
            icon_p = ":material/check_circle:" if pass_power else ":material/error:"
            delta_kw = cfg_kw - req_kw
            delta_kw_str = f"+{delta_kw:,.1f} kW" if delta_kw >= 0 else f"{delta_kw:,.1f} kW"
            st.markdown(f"**{icon_p} Inverter Discharge Power**")
            st.metric(
                label="Configured vs. Required",
                value=f"{cfg_kw:,.1f} kW",
                delta=f"Req: {req_kw:,.1f} kW ({delta_kw_str})",
                delta_color="normal" if pass_power else "inverse",
                help="Continuous inverter discharge power required to shave the highest peak overload down to the grid limit.",
            )
        with chk_col2:
            icon_c = ":material/check_circle:" if pass_capacity else ":material/error:"
            delta_kwh = cfg_kwh - req_kwh
            delta_kwh_str = f"+{delta_kwh:,.1f} kWh" if delta_kwh >= 0 else f"{delta_kwh:,.1f} kWh"
            st.markdown(f"**{icon_c} Storage Capacity (Multi-Peak Clusters)**")
            st.metric(
                label="Configured vs. Required",
                value=f"{cfg_kwh:,.1f} kWh",
                delta=f"Req: {req_kwh:,.1f} kWh ({delta_kwh_str})",
                delta_color="normal" if pass_capacity else "inverse",
                help="Minimum nameplate storage capacity required across consecutive peak days without sufficient recharge time.",
            )
        with chk_col3:
            pass_rech_inv = cfg_kw >= min(req_kw, rech_kw_avail)
            icon_r = ":material/check_circle:" if pass_rech_inv else ":material/warning:"
            req_rech_p = min(req_kw, rech_kw_avail)
            delta_rech = cfg_kw - req_rech_p
            delta_rech_str = f"+{delta_rech:,.1f} kW" if delta_rech >= 0 else f"{delta_rech:,.1f} kW"
            st.markdown(f"**{icon_r} Recharge Inverter Power**")
            st.metric(
                label="Configured vs. Required",
                value=f"{cfg_kw:,.1f} kW",
                delta=f"Req: {req_rech_p:,.1f} kW ({delta_rech_str})",
                delta_color="normal" if pass_rech_inv else "inverse",
                help="Inverter recharge power capability to replenish the battery buffer during off-peak periods.",
            )
        with chk_col4:
            icon_h = ":material/check_circle:" if pass_recharge else ":material/error:"
            st.markdown(f"**{icon_h} Grid Recharge Headroom**")
            st.metric(
                label="Configured vs. Required",
                value=f"{rech_kwh_avail:,.0f} kWh/yr",
                delta="Req: Available (Pass)" if pass_recharge else "Req: Insufficient (Deficit)",
                delta_color="normal" if pass_recharge else "inverse",
                help="Total cumulative annual energy available below the grid limit for battery recharging.",
            )

        with st.expander(":material/table_chart: Sizing Comparison Table", expanded=False):
            bottleneck_df = refresh_bottleneck_table_configured_status(
                dual_bess=dual_bess,
                configured_kwh=cur_sys.battery_capacity_kwh,
                configured_kw=cur_sys.battery_power_kw,
                enable_battery=is_active,
            )
            st.dataframe(bottleneck_df, use_container_width=True, hide_index=True)


# ======================================================================================
# LEVEL 2 — SUBTAB 4: Generator (With Dual-Sizing & Model Presets)
# ======================================================================================

GENERATOR_MODEL_PRESETS: dict = {
    "Custom Size (Manual kW)": {},
    "50 kW Small Diesel Backup (Cummins / Kohler 50 kVA)": {
        "kw": 50.0,
        "fuel": "Diesel",
        "min_load": 25.0,
    },
    "100 kW Medium Commercial Genset (Caterpillar DE110)": {
        "kw": 100.0,
        "fuel": "Diesel",
        "min_load": 25.0,
    },
    "200 kW Heavy Commercial Genset (CAT DE220 / MTU)": {
        "kw": 200.0,
        "fuel": "Diesel",
        "min_load": 25.0,
    },
    "500 kW Industrial Prime Power (Cummins QSK19)": {
        "kw": 500.0,
        "fuel": "Diesel",
        "min_load": 25.0,
    },
    "100 kW Natural Gas Continuous (Jenbacher / MAN)": {
        "kw": 100.0,
        "fuel": "Natural Gas",
        "min_load": 30.0,
    },
    "250 kW Clean HVO Biofuel (Volvo Penta)": {
        "kw": 250.0,
        "fuel": "HVO",
        "min_load": 25.0,
    },
}


@st.fragment
def _render_generator_reference_fragment(dual_gen: DualGeneratorSizingResult, is_active: bool) -> None:
    """Renders the interactive Mode A / Mode B reference box inside an isolated fragment to prevent full app reruns."""
    st.markdown("##### :material/electric_bolt: 1. Recommended Generator Size")
    st.caption(
        "Minimum generator size needed to cover peaks above the Grid Limit."
    )

    mode_options = [
        "Mode A – Standalone (Generator only)",
        "Mode B – Coupled (With active Solar / Battery & Rules)",
    ]
    cur_mode = st.session_state.get("comb_gen_ref_mode", "Mode B – Coupled (With active Solar / Battery & Rules)")
    sel_idx = 0 if cur_mode.startswith("Mode A") else 1
    selected_mode = st.radio(
        "Quick-Sizing Reference Mode",
        options=mode_options,
        index=sel_idx,
        horizontal=True,
        disabled=not is_active,
        key="comb_gen_ref_mode_radio",
    )
    st.session_state["comb_gen_ref_mode"] = selected_mode
    is_sa = selected_mode.startswith("Mode A")

    req_kw = dual_gen.standalone_100_kw if is_sa else dual_gen.coupled_100_kw
    req_mwh = dual_gen.standalone_energy_mwh if is_sa else dual_gen.coupled_energy_mwh
    req_longest = dual_gen.standalone_longest_run_hours if is_sa else dual_gen.coupled_longest_run_hours
    req_runtime = dual_gen.standalone_runtime_hours if is_sa else dual_gen.coupled_runtime_hours
    req_tank = dual_gen.standalone_fuel_tank_liters if is_sa else dual_gen.coupled_fuel_tank_liters

    # 4 Metric Cards
    gm1, gm2, gm3, gm4 = st.columns(4)
    with gm1:
        st.metric("Min. Required Generator Power", f"{req_kw:,.1f} kW")
    with gm2:
        st.metric("Annual Energy to Supply", f"{req_mwh:,.1f} MWh/yr")
    with gm3:
        st.metric(
            "Longest Continuous Run",
            f"{req_longest:,.1f} hrs",
            delta=f"Total: {req_runtime:,.1f} hrs/yr",
        )
    with gm4:
        st.metric(
            "Recommended Fuel Tank",
            f"{req_tank:,.0f} L",
            delta="Includes 48h emergency reserve",
        )

    # 3 Quick Apply Buttons
    st.caption(f"Apply Quick Size ({'Standalone: Full Peak' if is_sa else 'Coupled: Remaining Peak after Solar/Battery'}):")
    gq1, gq2, gq3 = st.columns(3)
    with gq1:
        if st.button(
            f"Apply 100% Zero-Overload ({req_kw:,.1f} kW)",
            icon=":material/bolt:",
            type="primary",
            use_container_width=True,
            disabled=not is_active,
            key="comb_gen_btn_apply_100",
        ):
            _apply_gen_quick_size(req_kw)
            st.rerun()
    with gq2:
        q80_kw = round(req_kw * 0.80, 1)
        if st.button(
            f"Apply 80% Quick-Size ({q80_kw:,.1f} kW)",
            use_container_width=True,
            disabled=not is_active,
            key="comb_gen_btn_apply_80",
        ):
            _apply_gen_quick_size(q80_kw)
            st.rerun()
    with gq3:
        q50_kw = round(req_kw * 0.50, 1)
        if st.button(
            f"Apply 50% Quick-Size ({q50_kw:,.1f} kW)",
            use_container_width=True,
            disabled=not is_active,
            key="comb_gen_btn_apply_50",
        ):
            _apply_gen_quick_size(q50_kw)
            st.rerun()


def render_subtab4_generator(load_series: LoadSeries2025) -> None:
    """
    Renders Subtab 4: Generator
      - 1-Click Activate button if inactive
      - Block 1: Minimum Required Generator Sizing (100% Zero-Overload Reference) with 4 metrics & quick apply
      - Block 2: Standard Generator Models Preset Mini-Form (encapsulated to prevent intermediate reruns)
      - Block 3: Generator Hardware & Operating Limits Form
    """
    cur_sys: CombinedSystemConfig = st.session_state["comb_system_cfg"]
    cur_rules: InteractionRulesConfig = st.session_state["comb_rules_cfg"]
    is_active = bool(cur_sys.enable_generator)

    if not is_active:
        with st.container(border=True):
            g_col1, g_col2 = st.columns([2.5, 1.2])
            with g_col1:
                st.markdown(
                    "**Generator is currently inactive.** Click **Activate Generator** to include a backup generator in your system."
                )
            with g_col2:
                st.button(
                    "Activate Generator",
                    icon=":material/power_settings_new:",
                    type="primary",
                    use_container_width=True,
                    key="comb_btn_activate_generator",
                    on_click=_activate_module_callback,
                    args=("comb_enable_generator_toggle",),
                )

    # Fingerprint-cached Dual Generator Sizing (runs only when upstream Solar/Battery/Grid/Rules change)
    gen_sizing_fp = (
        ENGINE_VERSION,
        _load_fingerprint(load_series),
        bool(cur_sys.enable_grid),
        round(float(cur_sys.grid_limit_kw), 2),
        bool(cur_sys.enable_solar),
        round(float(cur_sys.latitude), 4),
        round(float(cur_sys.longitude), 4),
        cur_sys.solar_sizing_method,
        round(float(cur_sys.solar_kwp), 2),
        round(float(cur_sys.target_consumption_share_pct), 2),
        round(float(cur_sys.inverter_ac_limit_kw), 2),
        round(float(cur_sys.inverter_efficiency_pct), 2),
        bool(cur_sys.enable_battery),
        round(float(cur_sys.battery_capacity_kwh), 2),
        round(float(cur_sys.battery_power_kw), 2),
        round(float(cur_sys.min_soc_pct), 2),
        round(float(cur_sys.max_soc_pct), 2),
        round(float(cur_sys.round_trip_efficiency_pct), 2),
        _rules_tuple(cur_rules),
    )
    if (
        st.session_state.get("comb_gen_sizing_fp") != gen_sizing_fp
        or "comb_cached_dual_gen" not in st.session_state
    ):
        st.session_state["comb_cached_dual_gen"] = compute_dual_generator_sizing(
            load_kw=load_series.power_kw,
            timestamps=load_series.timestamps,
            system_cfg=cur_sys,
            rules_cfg=cur_rules,
            is_gap=getattr(load_series, "is_gap", None),
        )
        st.session_state["comb_gen_sizing_fp"] = gen_sizing_fp

    dual_gen = st.session_state["comb_cached_dual_gen"]

    # Block 1: Minimum Required Generator Sizing Reference Box
    with st.container(border=True):
        _render_generator_reference_fragment(dual_gen=dual_gen, is_active=is_active)

    # Block 2: Standard Generator Models Preset Mini-Form
    with st.container(border=True):
        st.markdown("##### :material/category: 2. Generator Models")
        with st.form("comb_gen_preset_form"):
            gp_c1, gp_btn = st.columns([2.5, 1.2])
            with gp_c1:
                preset_keys = list(GENERATOR_MODEL_PRESETS.keys())
                sel_preset = st.selectbox(
                    "Select Model",
                    options=preset_keys,
                    index=0,
                    disabled=not is_active,
                    key="comb_gen_preset_select",
                    help="Loads standard commercial power ratings and fuel configurations.",
                )
            with gp_btn:
                st.write("")
                apply_preset_submitted = st.form_submit_button(
                    "Apply Generator Model",
                    icon=":material/done:",
                    use_container_width=True,
                    disabled=not is_active,
                )

        if apply_preset_submitted and sel_preset in GENERATOR_MODEL_PRESETS:
            p_data = GENERATOR_MODEL_PRESETS[sel_preset]
            if p_data:
                cur_sys.generator_rated_kw = float(p_data["kw"])
                cur_sys.fuel_type = str(p_data["fuel"])
                cur_sys.generator_min_load_pct = float(p_data["min_load"])
                st.session_state["comb_generator_rated_kw_num"] = cur_sys.generator_rated_kw
                st.session_state["comb_generator_fuel_type_select"] = cur_sys.fuel_type
                st.session_state["comb_generator_min_load_num"] = cur_sys.generator_min_load_pct
                st.session_state.pop("comb_cached_excel_bytes", None)
                st.rerun()

    # Block 3: Generator Hardware & Operating Limits Form
    with st.container(border=True):
        st.markdown("##### :material/tune: 3. Generator Size & Settings")
        with st.form("comb_generator_form"):
            gc1, gc2, gc3 = st.columns(3)
            with gc1:
                raw_gen_kw = float(cur_sys.generator_rated_kw)
                max_gen_kw = max(100000.0, raw_gen_kw * 2)
                safe_gen_kw = min(max_gen_kw, max(10.0, raw_gen_kw))
                gen_kw_val = st.number_input(
                    "Generator Power (kW)",
                    min_value=10.0,
                    max_value=max_gen_kw,
                    value=safe_gen_kw,
                    step=10.0,
                    disabled=not is_active,
                    key="comb_generator_rated_kw_num",
                    help="Rated continuous prime power output of the generator.",
                )
            with gc2:
                fuel_keys = list(FUEL_SPECS.keys())
                fuel_idx = fuel_keys.index(cur_sys.fuel_type) if cur_sys.fuel_type in fuel_keys else 0
                fuel_type_val = st.selectbox(
                    "Fuel Type",
                    options=fuel_keys,
                    index=fuel_idx,
                    disabled=not is_active,
                    key="comb_generator_fuel_type_select",
                )
            with gc3:
                gen_min_pct_val = st.slider(
                    "Minimum Load (%)",
                    min_value=15,
                    max_value=50,
                    value=int(round(cur_sys.generator_min_load_pct)),
                    step=5,
                    disabled=not is_active,
                    key="comb_generator_min_load_num",
                    help="Prevents engine damage from light-load operation by enforcing minimum loading.",
                )

            st.write("")
            gen_submitted = st.form_submit_button(
                "Update Generator Settings & Run Simulation",
                icon=":material/refresh:",
                type="primary",
                use_container_width=True,
                disabled=not is_active,
            )

        if gen_submitted:
            cur_sys.generator_rated_kw = float(gen_kw_val)
            cur_sys.generator_min_load_pct = float(gen_min_pct_val)
            cur_sys.fuel_type = str(fuel_type_val)
            st.session_state.pop("comb_cached_excel_bytes", None)


# ======================================================================================
# LEVEL 2 — SUBTAB 5: System Mix & Rules (Central Co-Sizing & Operating Rules Cockpit)
# ======================================================================================

def _ensure_live_sim_for_mix_tab(
    load_series: LoadSeries2025,
    cur_sys: CombinedSystemConfig,
    cur_rules: InteractionRulesConfig,
):
    """Returns cached simulation result or computes it cleanly once for Zone 1 utilization metrics."""
    dispatch_fp = (
        _load_fingerprint(load_series),
        _physical_sys_tuple(cur_sys),
        _rules_tuple(cur_rules),
    )
    if (
        st.session_state.get("comb_dispatch_fp") == dispatch_fp
        and "comb_sandbox_result" in st.session_state
    ):
        return st.session_state["comb_sandbox_result"]

    sim_res = simulate_combined_system_dispatch(
        load_kw=load_series.power_kw,
        timestamps=load_series.timestamps,
        system_cfg=cur_sys,
        rules_cfg=cur_rules,
        is_gap=getattr(load_series, "is_gap", None),
    )
    if "comb_latest_bottleneck_df" in st.session_state:
        sim_res.bess_bottleneck_df = st.session_state["comb_latest_bottleneck_df"]
    st.session_state["comb_sandbox_result"] = sim_res
    st.session_state["comb_dispatch_fp"] = dispatch_fp
    st.session_state.pop("comb_cached_excel_bytes", None)
    return sim_res


def _derive_effective_solar_share_pct(cur_sys: CombinedSystemConfig, sim_res) -> float:
    """Returns the effective annual solar target share (%) for the current system configuration."""
    if not cur_sys.enable_solar:
        return 0.0
    if getattr(cur_sys, "solar_sizing_method", "target_share_pct") == "target_share_pct":
        return float(cur_sys.target_consumption_share_pct)
    ann_load = max(1.0, float(sim_res.kpis.annual_consumption_kwh))
    return float(np.clip((sim_res.kpis.solar_total_generation_kwh / ann_load) * 100.0, 0.0, 150.0))


def _apply_system_mix_to_state(
    cur_sys: CombinedSystemConfig,
    grid_limit_kw: float,
    solar_enabled: bool,
    solar_share_pct: float,
    solar_kwp: float,
    battery_enabled: bool,
    battery_capacity_kwh: float,
    battery_power_kw: float,
    generator_enabled: bool,
    generator_rated_kw: float,
    solar_sizing_method: str = "target_share_pct",
    inverter_ac_limit_kw: float = 0.0,
) -> None:
    """Commits a coordinated or manually tuned Grid/Solar/Battery/Generator mix to session state."""
    cur_sys.enable_grid = True
    cur_sys.grid_limit_kw = float(max(10.0, grid_limit_kw))

    cur_sys.enable_solar = bool(solar_enabled and (solar_kwp > 0.0 or solar_share_pct > 0.0))
    if cur_sys.enable_solar:
        cur_sys.solar_sizing_method = str(solar_sizing_method or "target_share_pct")
        cur_sys.target_consumption_share_pct = float(solar_share_pct)
        cur_sys.solar_kwp = float(max(0.0, solar_kwp))
        cur_sys.inverter_ac_limit_kw = float(max(0.0, inverter_ac_limit_kw))

    cur_sys.enable_battery = bool(battery_enabled and battery_capacity_kwh > 0.0 and battery_power_kw > 0.0)
    if cur_sys.enable_battery:
        cur_sys.battery_power_kw = max(5.0, float(battery_power_kw))
        cur_sys.battery_capacity_kwh = max(10.0, float(battery_capacity_kwh))
        units, unit_kwh = determine_smart_modular_units(cur_sys.battery_capacity_kwh)
    else:
        units, unit_kwh = (2, 50.0)

    cur_sys.enable_generator = bool(generator_enabled and generator_rated_kw > 0.0)
    if cur_sys.enable_generator:
        cur_sys.generator_rated_kw = max(10.0, float(generator_rated_kw))

    st.session_state["comb_bess_user_configured"] = True
    st.session_state["comb_bess_unit_count"] = units
    st.session_state["comb_bess_unit_kwh"] = unit_kwh

    pending_widgets = {
        "comb_enable_solar_toggle": bool(cur_sys.enable_solar),
        "comb_enable_battery_toggle": bool(cur_sys.enable_battery),
        "comb_enable_generator_toggle": bool(cur_sys.enable_generator),
        "comb_grid_limit_input": float(cur_sys.grid_limit_kw),
        "comb_bess_unit_count_num": units,
        "comb_bess_unit_kwh_num": unit_kwh,
        "comb_battery_power_kw_num": float(cur_sys.battery_power_kw),
        "comb_generator_rated_kw_num": float(cur_sys.generator_rated_kw),
        "comb_mix_grid_limit_num": float(cur_sys.grid_limit_kw),
        "comb_mix_solar_share_slider": int(round(np.clip(solar_share_pct if cur_sys.enable_solar else 0.0, 0.0, 150.0))),
        "comb_mix_bess_kwh_num": float(cur_sys.battery_capacity_kwh if cur_sys.enable_battery else 0.0),
        "comb_mix_bess_kw_num": float(cur_sys.battery_power_kw if cur_sys.enable_battery else 0.0),
        "comb_mix_gen_kw_num": float(cur_sys.generator_rated_kw if cur_sys.enable_generator else 0.0),
    }
    if cur_sys.enable_solar and cur_sys.solar_sizing_method == "target_share_pct":
        pending_widgets["comb_solar_sizing_radio"] = "% of Annual Consumption"
        pending_widgets["comb_solar_target_share_num"] = float(cur_sys.target_consumption_share_pct)

    st.session_state["comb_pending_mix_widget_sync"] = pending_widgets
    for cache_key in (
        "comb_cached_dual_bess",
        "comb_bess_sizing_fp",
        "comb_cached_dual_gen",
        "comb_gen_sizing_fp",
        "comb_cached_excel_bytes",
        "comb_mix_preview",
        "comb_mix_preview_fp",
        "comb_mix_preview_bundle",
        "comb_mix_synced_sys_fp",
    ):
        st.session_state.pop(cache_key, None)
    st.rerun()


@st.fragment
def render_supply_mix_and_utilization_overview(
    sim_res,
    key_prefix: str = "subtab5",
) -> None:
    """
    Reusable Supply Mix Pie Chart & Component Utilization Breakdown.
    Shared by Subtab 5 (System Mix & Rules) and Subtab 6 (Financials).
    """
    diag: SystemUtilizationDiagnostics = compute_system_utilization_diagnostics(sim_res)

    with st.container(border=True):
        st.markdown("##### :material/donut_large: 1. Where Your Electricity Comes From & How Much You Use It")
        st.caption(
            "Left: exact electricity supply shares covering your annual consumption. "
            "Right: how much of each installed asset's capacity is actively used vs. sitting idle."
        )

        col_mix, col_util = st.columns([1.0, 1.15])

        with col_mix:
            st.markdown("**a) Electricity Supply Mix**")
            fig_pie = create_supply_mix_pie_figure(diag, height=340)
            st.plotly_chart(
                fig_pie,
                use_container_width=True,
                key=f"{key_prefix}_supply_mix_pie_chart",
            )

            mix_rows = [
                {
                    "Source": "Grid Direct",
                    "Energy (MWh/yr)": round(diag.grid_direct_kwh / 1000.0, 1),
                    "Share (%)": round(diag.grid_direct_pct, 1),
                    "Peak Contrib. (kW)": round(diag.grid_peak_import_kw, 1),
                },
                {
                    "Source": "Solar Direct",
                    "Energy (MWh/yr)": round(diag.solar_direct_kwh / 1000.0, 1),
                    "Share (%)": round(diag.solar_direct_pct, 1),
                    "Peak Contrib. (kW)": round(diag.solar_peak_contribution_kw, 1),
                },
                {
                    "Source": "Battery Discharge",
                    "Energy (MWh/yr)": round(diag.battery_discharge_kwh / 1000.0, 1),
                    "Share (%)": round(diag.battery_discharge_pct, 1),
                    "Peak Contrib. (kW)": round(diag.bess_peak_discharged_kw, 1),
                },
                {
                    "Source": "Generator Output",
                    "Energy (MWh/yr)": round(diag.generator_direct_kwh / 1000.0, 1),
                    "Share (%)": round(diag.generator_direct_pct, 1),
                    "Peak Contrib. (kW)": round(diag.gen_peak_used_kw, 1),
                },
            ]
            st.dataframe(
                pd.DataFrame(mix_rows),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Energy (MWh/yr)": st.column_config.NumberColumn(format="%.1f MWh"),
                    "Share (%)": st.column_config.NumberColumn(format="%.1f%%"),
                    "Peak Contrib. (kW)": st.column_config.NumberColumn(format="%.1f kW"),
                },
            )

            if diag.battery_discharge_kwh > 0.5:
                st.caption(
                    f"Battery discharge origin: {diag.solar_via_battery_kwh / 1000.0:,.1f} MWh/yr "
                    f"from solar surplus + {diag.grid_or_gen_via_battery_kwh / 1000.0:,.1f} MWh/yr "
                    f"from grid/generator recharging."
                )

            if diag.unmet_overload_kwh > 0.5:
                st.warning(
                    f"Remaining unmet overload: {diag.unmet_overload_kwh:,.0f} kWh across "
                    f"{sim_res.kpis.remaining_overload_hours:.1f} hrs above the "
                    f"{diag.grid_limit_kw:,.0f} kW Grid Limit.",
                    icon=":material/warning:",
                )
            else:
                st.success(
                    f"Grid Limit ({diag.grid_limit_kw:,.0f} kW) met with 0.0 hrs remaining overload.",
                    icon=":material/check_circle:",
                )

        with col_util:
            st.markdown("**b) Component Utilization & Right-Sizing Check**")
            fig_bars = create_component_utilization_bars_figure(diag, height=340)
            st.plotly_chart(
                fig_bars,
                use_container_width=True,
                key=f"{key_prefix}_component_util_bars_chart",
            )

            bullets: List[str] = []
            if diag.solar_enabled and diag.solar_installed_kwp > 0:
                used_sol_mwh = (diag.solar_used_direct_kwh + diag.solar_used_via_battery_kwh) / 1000.0
                exp_sol_mwh = diag.solar_exported_unused_kwh / 1000.0
                bullets.append(
                    f"- **Solar ({diag.solar_installed_kwp:,.1f} kWp):** "
                    f"**{used_sol_mwh:,.1f} MWh/yr ({diag.solar_utilization_pct:.1f}%)** used on-site "
                    f"({diag.solar_used_direct_kwh / 1000.0:,.1f} MWh direct + "
                    f"{diag.solar_used_via_battery_kwh / 1000.0:,.1f} MWh via battery); "
                    f"**{exp_sol_mwh:,.1f} MWh/yr** exported/unused."
                )
            else:
                bullets.append("- **Solar:** Inactive.")

            if diag.bess_enabled and diag.bess_installed_kwh > 0:
                trim_hint = ""
                if diag.bess_capacity_utilization_pct < 65.0 and diag.bess_right_sized_kwh + 10.0 < diag.bess_installed_kwh:
                    trim_hint = (
                        f" Trimming to **~{diag.bess_right_sized_kwh:,.0f} kWh** removes untouched "
                        "dead capacity while keeping zero extra overload."
                    )
                else:
                    trim_hint = " Storage depth fits the active load profile."
                bullets.append(
                    f"- **Battery Storage ({diag.bess_installed_kwh:,.0f} kWh / {diag.bess_installed_kw:,.1f} kW):** Max "
                    f"**{diag.bess_max_depth_used_kwh:,.0f} kWh** used out of "
                    f"**{diag.bess_usable_window_kwh:,.0f} kWh** usable "
                    f"(**{diag.bess_capacity_utilization_pct:.1f}%** used, "
                    f"SoC {diag.bess_min_soc_reached_pct:.1f}%–{diag.bess_max_soc_reached_pct:.1f}%, "
                    f"{diag.bess_cycles_per_yr:.1f} cyc/yr) -> "
                    f"**{diag.bess_unused_usable_kwh:,.0f} kWh** stayed unused all year.{trim_hint}"
                )
            else:
                bullets.append("- **Battery:** Inactive.")

            if diag.gen_enabled and diag.gen_rated_kw > 0:
                bullets.append(
                    f"- **Generator ({diag.gen_rated_kw:,.1f} kW):** Peak output "
                    f"**{diag.gen_peak_used_kw:,.1f} kW ({diag.gen_power_utilization_pct:.1f}%)** "
                    f"across **{diag.gen_runtime_hours:,.1f} hrs/yr** "
                    f"({diag.gen_starts_count} starts, {diag.gen_energy_kwh / 1000.0:,.1f} MWh/yr)."
                )
            else:
                bullets.append("- **Generator:** Inactive.")

            st.markdown("\n".join(bullets))


def render_subtab5_interaction_rules(load_series: Optional[LoadSeries2025] = None) -> None:
    """
    Renders Subtab 5: System Mix & Rules Cockpit:
      - Section 1: Reusable Supply Mix Pie Chart & Component Utilization Check
      - Section 2: Direct 1-Click Right-Sizing & 4-Column System Mix Form (st.form("comb_system_mix_form"))
      - Section 3: Dispatch Interaction Rules (st.form("comb_rules_form"))
    """
    if load_series is None:
        load_series, _ = _get_active_load_series()

    cur_sys: CombinedSystemConfig = st.session_state["comb_system_cfg"]
    cur_rules: InteractionRulesConfig = st.session_state["comb_rules_cfg"]
    sim_res = _ensure_live_sim_for_mix_tab(load_series, cur_sys, cur_rules)
    diag = compute_system_utilization_diagnostics(sim_res)

    # ----------------------------------------------------------------------------------
    # SECTION 1: Where Your Electricity Comes From & How Much You Use It
    # ----------------------------------------------------------------------------------
    render_supply_mix_and_utilization_overview(sim_res, key_prefix="subtab5")

    # ----------------------------------------------------------------------------------
    # SECTION 2: Adjust System Mix (Right-Sizing)
    # ----------------------------------------------------------------------------------
    eff_sol_share_pct = _derive_effective_solar_share_pct(cur_sys, sim_res)
    eff_sol_slider_seed = int(round(np.clip(eff_sol_share_pct, 0.0, 150.0)))

    orig_peak = float(load_series.peak_demand_kw)
    max_gl = max(100000.0, orig_peak * 2.0, float(cur_sys.grid_limit_kw) * 2.0)
    max_bess_kwh = max(500000.0, float(cur_sys.battery_capacity_kwh) * 2.0)
    max_bess_kw = max(100000.0, float(cur_sys.battery_power_kw) * 2.0)
    max_gen_kw = max(100000.0, float(cur_sys.generator_rated_kw) * 2.0)

    sys_fp = _physical_sys_tuple(cur_sys)
    required_mix_keys = (
        "comb_mix_grid_limit_num",
        "comb_mix_solar_share_slider",
        "comb_mix_bess_kwh_num",
        "comb_mix_bess_kw_num",
        "comb_mix_gen_kw_num",
    )
    if st.session_state.get("comb_mix_synced_sys_fp") != sys_fp or any(
        k not in st.session_state for k in required_mix_keys
    ):
        st.session_state["comb_mix_grid_limit_num"] = float(
            np.clip(cur_sys.grid_limit_kw, 10.0, max_gl)
        )
        st.session_state["comb_mix_solar_share_slider"] = eff_sol_slider_seed
        st.session_state["comb_mix_bess_kwh_num"] = float(
            np.clip(cur_sys.battery_capacity_kwh if cur_sys.enable_battery else 0.0, 0.0, max_bess_kwh)
        )
        st.session_state["comb_mix_bess_kw_num"] = float(
            np.clip(cur_sys.battery_power_kw if cur_sys.enable_battery else 0.0, 0.0, max_bess_kw)
        )
        st.session_state["comb_mix_gen_kw_num"] = float(
            np.clip(cur_sys.generator_rated_kw if cur_sys.enable_generator else 0.0, 0.0, max_gen_kw)
        )
        st.session_state["comb_mix_synced_sys_fp"] = sys_fp

    with st.container(border=True):
        st.markdown("##### :material/tune: 2. Adjust System Mix (Right-Sizing)")
        st.caption(
            "Apply a direct 1-click size adjustment from the utilization check above, "
            "or tune Grid Limit, Solar, Battery, and Generator together below."
        )

        # 4 Direct 1-Click Preset Actions
        can_trim_bess = bool(
            diag.bess_enabled
            and diag.bess_right_sized_kwh >= 10.0
            and diag.bess_installed_kwh > diag.bess_right_sized_kwh + 10.0
        )
        p1, p2, p3, p4 = st.columns(4)
        with p1:
            trim_help = (
                f"Shrinks Battery energy from {diag.bess_installed_kwh:,.0f} kWh to "
                f"{diag.bess_right_sized_kwh:,.0f} kWh while keeping {diag.bess_installed_kw:,.1f} kW peak power."
                if can_trim_bess
                else "Battery already closely matches its peak depth (or is off)."
            )
            if st.button(
                "Trim Unused Battery Capacity",
                icon=":material/content_cut:",
                disabled=not can_trim_bess,
                help=trim_help,
                use_container_width=True,
                key="comb_btn_trim_bess",
            ):
                _apply_system_mix_to_state(
                    cur_sys=cur_sys,
                    grid_limit_kw=float(cur_sys.grid_limit_kw),
                    solar_enabled=bool(cur_sys.enable_solar),
                    solar_share_pct=eff_sol_share_pct,
                    solar_kwp=float(sim_res.solar_derivation.installed_kwp),
                    battery_enabled=True,
                    battery_capacity_kwh=float(diag.bess_right_sized_kwh),
                    battery_power_kw=float(cur_sys.battery_power_kw),
                    generator_enabled=bool(cur_sys.enable_generator),
                    generator_rated_kw=float(cur_sys.generator_rated_kw),
                    solar_sizing_method=cur_sys.solar_sizing_method,
                    inverter_ac_limit_kw=cur_sys.inverter_ac_limit_kw,
                )

        with p2:
            if st.button(
                "Compact 2h Battery + Generator Backup",
                icon=":material/auto_fix_high:",
                help="Pairs a compact 2h daily/solar Battery with an auto-sized Generator for extended peak clusters.",
                use_container_width=True,
                key="comb_btn_hybrid_2h",
            ):
                rec_2h = compute_coordinated_mix_sizing(
                    load_kw=load_series.power_kw,
                    system_cfg=cur_sys,
                    rules_cfg=cur_rules,
                    strategy_key="hybrid_2h",
                    target_grid_limit_kw=float(cur_sys.grid_limit_kw),
                    solar_share_pct=eff_sol_share_pct,
                    solar_enabled=bool(cur_sys.enable_solar),
                    bess_duration_hours=2.0,
                    gen_cover_remaining_peaks=True,
                    is_gap=getattr(load_series, "is_gap", None),
                )
                _apply_system_mix_to_state(
                    cur_sys=cur_sys,
                    grid_limit_kw=rec_2h.grid_limit_kw,
                    solar_enabled=bool(cur_sys.enable_solar),
                    solar_share_pct=eff_sol_share_pct,
                    solar_kwp=float(sim_res.solar_derivation.installed_kwp) if cur_sys.enable_solar else 0.0,
                    battery_enabled=rec_2h.battery_enabled,
                    battery_capacity_kwh=rec_2h.battery_capacity_kwh,
                    battery_power_kw=rec_2h.battery_power_kw,
                    generator_enabled=rec_2h.generator_enabled,
                    generator_rated_kw=rec_2h.generator_rated_kw,
                    solar_sizing_method=cur_sys.solar_sizing_method,
                    inverter_ac_limit_kw=cur_sys.inverter_ac_limit_kw,
                )

        with p3:
            if st.button(
                "100% Battery (No Generator)",
                icon=":material/battery_charging_full:",
                help="Removes the Generator and sizes Battery kWh + kW for 0.0 hrs overload.",
                use_container_width=True,
                key="comb_btn_bess_only",
            ):
                rec_bess = compute_coordinated_mix_sizing(
                    load_kw=load_series.power_kw,
                    system_cfg=cur_sys,
                    rules_cfg=cur_rules,
                    strategy_key="pure_battery_100",
                    target_grid_limit_kw=float(cur_sys.grid_limit_kw),
                    solar_share_pct=eff_sol_share_pct,
                    solar_enabled=bool(cur_sys.enable_solar),
                    bess_duration_hours=2.0,
                    gen_cover_remaining_peaks=False,
                    is_gap=getattr(load_series, "is_gap", None),
                )
                _apply_system_mix_to_state(
                    cur_sys=cur_sys,
                    grid_limit_kw=rec_bess.grid_limit_kw,
                    solar_enabled=bool(cur_sys.enable_solar),
                    solar_share_pct=eff_sol_share_pct,
                    solar_kwp=float(sim_res.solar_derivation.installed_kwp) if cur_sys.enable_solar else 0.0,
                    battery_enabled=rec_bess.battery_enabled,
                    battery_capacity_kwh=rec_bess.battery_capacity_kwh,
                    battery_power_kw=rec_bess.battery_power_kw,
                    generator_enabled=False,
                    generator_rated_kw=0.0,
                    solar_sizing_method=cur_sys.solar_sizing_method,
                    inverter_ac_limit_kw=cur_sys.inverter_ac_limit_kw,
                )

        with p4:
            if st.button(
                "100% Generator (No Battery)",
                icon=":material/local_gas_station:",
                help="Removes the Battery and sizes Generator kW for 0.0 hrs overload.",
                use_container_width=True,
                key="comb_btn_gen_only",
            ):
                rec_gen = compute_coordinated_mix_sizing(
                    load_kw=load_series.power_kw,
                    system_cfg=cur_sys,
                    rules_cfg=cur_rules,
                    strategy_key="pure_generator_100",
                    target_grid_limit_kw=float(cur_sys.grid_limit_kw),
                    solar_share_pct=eff_sol_share_pct,
                    solar_enabled=bool(cur_sys.enable_solar),
                    bess_duration_hours=2.0,
                    gen_cover_remaining_peaks=True,
                    is_gap=getattr(load_series, "is_gap", None),
                )
                _apply_system_mix_to_state(
                    cur_sys=cur_sys,
                    grid_limit_kw=rec_gen.grid_limit_kw,
                    solar_enabled=bool(cur_sys.enable_solar),
                    solar_share_pct=eff_sol_share_pct,
                    solar_kwp=float(sim_res.solar_derivation.installed_kwp) if cur_sys.enable_solar else 0.0,
                    battery_enabled=False,
                    battery_capacity_kwh=0.0,
                    battery_power_kw=0.0,
                    generator_enabled=rec_gen.generator_enabled,
                    generator_rated_kw=rec_gen.generator_rated_kw,
                    solar_sizing_method=cur_sys.solar_sizing_method,
                    inverter_ac_limit_kw=cur_sys.inverter_ac_limit_kw,
                )

        # Manual 4-Column System Mix Tuning Form
        with st.form("comb_system_mix_form"):
            mc1, mc2, mc3, mc4 = st.columns(4)

            with mc1:
                st.markdown("**Grid Limit**")
                mix_grid_kw = st.number_input(
                    "Grid Limit (kW)",
                    min_value=10.0,
                    max_value=max_gl,
                    step=10.0,
                    key="comb_mix_grid_limit_num",
                )

            with mc2:
                st.markdown("**Solar Target**")
                mix_solar_pct = st.slider(
                    "Solar Share (% of Annual Load, 0 = Off)",
                    min_value=0,
                    max_value=150,
                    step=5,
                    key="comb_mix_solar_share_slider",
                )

            with mc3:
                st.markdown("**Battery Size**")
                mix_bess_kwh = st.number_input(
                    "Battery Capacity (kWh, 0 = Off)",
                    min_value=0.0,
                    max_value=max_bess_kwh,
                    step=25.0,
                    key="comb_mix_bess_kwh_num",
                )
                mix_bess_kw = st.number_input(
                    "Battery Power (kW, 0 = Off)",
                    min_value=0.0,
                    max_value=max_bess_kw,
                    step=10.0,
                    key="comb_mix_bess_kw_num",
                )

            with mc4:
                st.markdown("**Generator Backup**")
                mix_gen_kw = st.number_input(
                    "Generator Power (kW, 0 = Off)",
                    min_value=0.0,
                    max_value=max_gen_kw,
                    step=10.0,
                    key="comb_mix_gen_kw_num",
                )
                mix_auto_gen = st.checkbox(
                    "Auto-size Generator for remaining peaks",
                    value=bool(st.session_state.get("comb_mix_auto_gen", False)),
                    key="comb_mix_auto_gen_chk",
                )

            btn_c1, btn_c2 = st.columns(2)
            with btn_c1:
                preview_clicked = st.form_submit_button(
                    "Preview Mix",
                    icon=":material/preview:",
                    use_container_width=True,
                )
            with btn_c2:
                apply_mix_clicked = st.form_submit_button(
                    "Apply Mix to System",
                    icon=":material/check_circle:",
                    type="primary",
                    use_container_width=True,
                )

        if preview_clicked or apply_mix_clicked:
            st.session_state["comb_mix_auto_gen"] = bool(mix_auto_gen)

            cand_cfg = copy.copy(cur_sys)
            cand_cfg.enable_grid = True
            cand_cfg.grid_limit_kw = float(max(10.0, mix_grid_kw))

            if int(mix_solar_pct) <= 0:
                cand_cfg.enable_solar = False
                cand_cfg.solar_kwp = 0.0
                cand_share_pct = 0.0
            elif cur_sys.enable_solar and int(mix_solar_pct) == eff_sol_slider_seed:
                cand_cfg.enable_solar = True
                cand_share_pct = eff_sol_share_pct
            else:
                cand_cfg.enable_solar = True
                cand_cfg.solar_sizing_method = "target_share_pct"
                cand_cfg.target_consumption_share_pct = float(mix_solar_pct)
                azim = 180.0 if cand_cfg.latitude >= 0.0 else 0.0
                _, spec_y, _ = get_unit_solar_generation_profile(
                    latitude=cand_cfg.latitude,
                    longitude=cand_cfg.longitude,
                    tilt_deg=cand_cfg.tilt_deg,
                    azimuth_deg=azim,
                    dc_ac_ratio=cand_cfg.dc_ac_ratio,
                )
                s_info = derive_solar_sizing_and_formula(
                    annual_consumption_kwh=float(load_series.annual_consumption_kwh),
                    specific_yield_kwh_per_kwp=spec_y,
                    sizing_method="target_share_pct",
                    direct_kwp=cand_cfg.solar_kwp,
                    target_share_pct=float(mix_solar_pct),
                    panel_wp=cand_cfg.panel_wp,
                    dc_ac_ratio=cand_cfg.dc_ac_ratio,
                    enable_solar=True,
                    inverter_ac_limit_kw=0.0,
                    inverter_efficiency_pct=cand_cfg.inverter_efficiency_pct,
                )
                cand_cfg.solar_kwp = float(s_info.installed_kwp)
                cand_cfg.inverter_ac_limit_kw = 0.0
                cand_share_pct = float(mix_solar_pct)

            cand_cfg.enable_battery = bool(float(mix_bess_kwh) > 0.0 and float(mix_bess_kw) > 0.0)
            cand_cfg.battery_capacity_kwh = float(mix_bess_kwh) if cand_cfg.enable_battery else 0.0
            cand_cfg.battery_power_kw = float(mix_bess_kw) if cand_cfg.enable_battery else 0.0

            cand_cfg.enable_generator = bool(float(mix_gen_kw) > 0.0)
            cand_cfg.generator_rated_kw = float(mix_gen_kw) if cand_cfg.enable_generator else 0.0

            if mix_auto_gen:
                gen_dual = compute_dual_generator_sizing(
                    load_kw=load_series.power_kw,
                    system_cfg=cand_cfg,
                    rules_cfg=cur_rules,
                    is_gap=getattr(load_series, "is_gap", None),
                )
                if gen_dual.coupled_100_kw > 0.0:
                    cand_cfg.enable_generator = True
                    cand_cfg.generator_rated_kw = float(gen_dual.coupled_100_kw)
                else:
                    cand_cfg.enable_generator = False
                    cand_cfg.generator_rated_kw = 0.0

            if apply_mix_clicked:
                _apply_system_mix_to_state(
                    cur_sys=cur_sys,
                    grid_limit_kw=cand_cfg.grid_limit_kw,
                    solar_enabled=cand_cfg.enable_solar,
                    solar_share_pct=cand_share_pct,
                    solar_kwp=cand_cfg.solar_kwp,
                    battery_enabled=cand_cfg.enable_battery,
                    battery_capacity_kwh=cand_cfg.battery_capacity_kwh,
                    battery_power_kw=cand_cfg.battery_power_kw,
                    generator_enabled=cand_cfg.enable_generator,
                    generator_rated_kw=cand_cfg.generator_rated_kw,
                    solar_sizing_method=cand_cfg.solar_sizing_method,
                    inverter_ac_limit_kw=cand_cfg.inverter_ac_limit_kw,
                )
            else:
                cand_sim = simulate_combined_system_dispatch(
                    load_kw=load_series.power_kw,
                    timestamps=load_series.timestamps,
                    system_cfg=cand_cfg,
                    rules_cfg=cur_rules,
                    is_gap=getattr(load_series, "is_gap", None),
                )
                cand_diag = compute_system_utilization_diagnostics(cand_sim)
                st.session_state["comb_mix_preview_bundle"] = {
                    "cfg": cand_cfg,
                    "sim": cand_sim,
                    "diag": cand_diag,
                }

        preview_bundle = st.session_state.get("comb_mix_preview_bundle")
        if isinstance(preview_bundle, dict) and "diag" in preview_bundle:
            p_cfg: CombinedSystemConfig = preview_bundle["cfg"]
            p_sim = preview_bundle["sim"]
            p_diag: SystemUtilizationDiagnostics = preview_bundle["diag"]

            st.markdown("**Current System vs. Proposed Mix Preview**")
            comp_rows = [
                {
                    "Parameter / Outcome": "Grid Limit",
                    "Current System": f"{diag.grid_limit_kw:,.0f} kW",
                    "Proposed Mix": f"{p_diag.grid_limit_kw:,.0f} kW",
                    "Change": f"{p_diag.grid_limit_kw - diag.grid_limit_kw:+,.0f} kW",
                },
                {
                    "Parameter / Outcome": "Solar Array",
                    "Current System": f"{diag.solar_installed_kwp:,.1f} kWp" if diag.solar_enabled else "Off",
                    "Proposed Mix": f"{p_diag.solar_installed_kwp:,.1f} kWp" if p_diag.solar_enabled else "Off",
                    "Change": f"{p_diag.solar_installed_kwp - diag.solar_installed_kwp:+,.1f} kWp",
                },
                {
                    "Parameter / Outcome": "Battery System",
                    "Current System": (
                        f"{diag.bess_installed_kwh:,.0f} kWh / {diag.bess_installed_kw:,.1f} kW"
                        if diag.bess_enabled
                        else "Off"
                    ),
                    "Proposed Mix": (
                        f"{p_diag.bess_installed_kwh:,.0f} kWh / {p_diag.bess_installed_kw:,.1f} kW"
                        if p_diag.bess_enabled
                        else "Off"
                    ),
                    "Change": f"{p_diag.bess_installed_kwh - diag.bess_installed_kwh:+,.0f} kWh",
                },
                {
                    "Parameter / Outcome": "Generator Power",
                    "Current System": f"{diag.gen_rated_kw:,.1f} kW" if diag.gen_enabled else "Off",
                    "Proposed Mix": f"{p_diag.gen_rated_kw:,.1f} kW" if p_diag.gen_enabled else "Off",
                    "Change": f"{p_diag.gen_rated_kw - diag.gen_rated_kw:+,.1f} kW",
                },
                {
                    "Parameter / Outcome": "Supply Split (Grid / Sol / Bat / Gen)",
                    "Current System": (
                        f"{diag.grid_direct_pct:.0f}% / {diag.solar_direct_pct:.0f}% / "
                        f"{diag.battery_discharge_pct:.0f}% / {diag.generator_direct_pct:.0f}%"
                    ),
                    "Proposed Mix": (
                        f"{p_diag.grid_direct_pct:.0f}% / {p_diag.solar_direct_pct:.0f}% / "
                        f"{p_diag.battery_discharge_pct:.0f}% / {p_diag.generator_direct_pct:.0f}%"
                    ),
                    "Change": "-",
                },
                {
                    "Parameter / Outcome": "Battery Capacity Utilization",
                    "Current System": f"{diag.bess_capacity_utilization_pct:.1f}%" if diag.bess_enabled else "Off",
                    "Proposed Mix": f"{p_diag.bess_capacity_utilization_pct:.1f}%" if p_diag.bess_enabled else "Off",
                    "Change": (
                        f"{p_diag.bess_capacity_utilization_pct - diag.bess_capacity_utilization_pct:+.1f} pp"
                        if diag.bess_enabled and p_diag.bess_enabled
                        else "-"
                    ),
                },
                {
                    "Parameter / Outcome": "Remaining Overload",
                    "Current System": f"{sim_res.kpis.remaining_overload_hours:.1f} hrs ({diag.unmet_overload_kwh:,.0f} kWh)",
                    "Proposed Mix": f"{p_sim.kpis.remaining_overload_hours:.1f} hrs ({p_diag.unmet_overload_kwh:,.0f} kWh)",
                    "Change": f"{p_sim.kpis.remaining_overload_hours - sim_res.kpis.remaining_overload_hours:+.1f} hrs",
                },
            ]
            st.dataframe(pd.DataFrame(comp_rows), use_container_width=True, hide_index=True)

            if p_cfg.enable_battery and p_diag.bess_capacity_utilization_pct < 65.0 and p_diag.bess_right_sized_kwh + 10.0 < p_diag.bess_installed_kwh:
                st.info(
                    f"Proposed Battery uses {p_diag.bess_max_depth_used_kwh:,.0f} of "
                    f"{p_diag.bess_usable_window_kwh:,.0f} kWh usable ({p_diag.bess_capacity_utilization_pct:.1f}%). "
                    f"~{p_diag.bess_right_sized_kwh:,.0f} kWh would cover the same peaks without unused reserve.",
                    icon=":material/tips_and_updates:",
                )

    # ----------------------------------------------------------------------------------
    # SECTION 3: Interaction Rules (Rules 1-3)
    # ----------------------------------------------------------------------------------
    st.markdown("##### :material/rule: 3. Dispatch Interaction Rules")
    st.info(
        "**How Solar Works Automatically:** Whenever Solar is active, solar power always feeds your "
        "Consumption directly first. This automatically reduces your grid demand and lowers daytime "
        "peaks before the Battery or Generator ever need to step in.",
        icon=":material/solar_power:",
    )

    r1_keys = list(RULE1_OPTIONS.keys())
    r2_keys = list(RULE2_OPTIONS.keys())
    r3_keys = list(RULE3_OPTIONS.keys())

    with st.form("comb_rules_form"):
        with st.container(border=True):
            r_c1, r_c2, r_c3 = st.columns(3)

            with r_c1:
                st.markdown("##### :material/priority_high: Rule 1 – Peak Priority")
                st.caption("Who steps in first when remaining demand (after direct Solar) exceeds the Grid Limit?")
                rule1_val = st.radio(
                    "Rule 1 Priority",
                    options=r1_keys,
                    index=r1_keys.index(cur_rules.rule1_peak_priority) if cur_rules.rule1_peak_priority in r1_keys else 0,
                    format_func=lambda k: RULE1_OPTIONS[k],
                    label_visibility="collapsed",
                    key="comb_rule1_select",
                )
                st.caption(
                    "Battery first: Battery absorbs peaks first; Generator starts as backup. / "
                    "Generator first: Generator covers sustained peaks; Battery covers small or excess peaks."
                )

            with r_c2:
                st.markdown("##### :material/battery_saver: Rule 2 – Daily Battery Use")
                st.caption("May stored battery energy also be used when demand is below the Grid Limit?")
                rule2_val = st.radio(
                    "Rule 2 Strategy",
                    options=r2_keys,
                    index=r2_keys.index(cur_rules.rule2_battery_strategy) if cur_rules.rule2_battery_strategy in r2_keys else 0,
                    format_func=lambda k: RULE2_OPTIONS[k],
                    label_visibility="collapsed",
                    key="comb_rule2_select",
                )
                reserve_val = st.slider(
                    "Peak Reserve SoC (%)",
                    min_value=10,
                    max_value=90,
                    value=int(np.clip(cur_rules.peak_reserve_soc_pct, 10, 90)),
                    step=5,
                    key="comb_rule2_reserve_slider",
                )
                st.caption(
                    "If Self-Consumption + Peak Reserve is active, extra solar energy shifts into evening load "
                    "while protecting this SoC % exclusively for peak shaving. "
                    "(Note: When Solar is inactive, the battery operates in pure Peak Shaving mode to avoid discharging into normal base load)."
                )

            with r_c3:
                st.markdown("##### :material/bolt: Rule 3 – Charging Sources")
                st.caption("Where and when does the Battery recharge?")
                rule3_val = st.radio(
                    "Rule 3 Charging",
                    options=r3_keys,
                    index=r3_keys.index(cur_rules.rule3_charging_sources) if cur_rules.rule3_charging_sources in r3_keys else 0,
                    format_func=lambda k: RULE3_OPTIONS[k],
                    label_visibility="collapsed",
                    key="comb_rule3_select",
                )
                st.caption(
                    "Options range from Solar only to full multi-source coupling (Solar surplus + Grid headroom + Generator excess)."
                )

        rules_submitted = st.form_submit_button(
            "Apply Interaction Rules",
            type="primary",
            use_container_width=True,
        )

    if rules_submitted:
        cur_rules.rule1_peak_priority = str(rule1_val)
        cur_rules.rule2_battery_strategy = str(rule2_val)
        cur_rules.peak_reserve_soc_pct = float(reserve_val)
        cur_rules.rule3_charging_sources = str(rule3_val)
        st.session_state.pop("comb_mix_preview_fp", None)
        st.session_state.pop("comb_cached_excel_bytes", None)
        st.rerun()


# ======================================================================================
# LEVEL 2 — SUBTAB 6: Financials (3-Zone Sub-Ledger Workbench, @st.fragment Isolated)
# ======================================================================================

def _render_master_cost_equation_bar(sim_res) -> str:
    """Renders the top Live Master Cost & Savings Equation Bar inspired by Currentsituation_sandbox."""
    fk = sim_res.financial_kpis
    if fk is None:
        return ""

    sav_color = "#22C55E" if fk.annual_savings_eur >= 0 else "#EF4444"
    sav_bg = "#06281e" if fk.annual_savings_eur >= 0 else "#2a0e12"
    pb_str = f"{fk.payback_years:.1f} yrs" if fk.payback_years is not None else "N/A"
    npv_color = "#22C55E" if fk.npv_15y_eur >= 0 else "#F87171"

    return (
        f'<div style="background-color:#0b1329; border:1.5px solid #334155; border-radius:10px; padding:12px 16px; margin-bottom:14px;">\n'
        f'<div style="font-size:0.74rem; font-weight:700; color:#94a3b8; text-transform:uppercase; letter-spacing:0.06em; margin-bottom:8px;">'
        f'Annual Cost &amp; Savings'
        f'</div>\n'
        f'<div style="display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:8px;">\n'
        f'<div style="background-color:#1e293b; border-left:4px solid #F87171; border-radius:6px; padding:7px 11px; flex:1; min-width:140px;">'
        f'<div style="font-size:0.72rem; color:#94a3b8; font-weight:600;">Current Situation Bill</div>'
        f'<div style="font-size:1.00rem; color:#f8fafc; font-weight:700;">&euro;{fk.baseline_total_opex_eur:,.0f} / yr</div>'
        f'</div>\n'
        f'<div style="color:#64748b; font-weight:800; font-size:1.05rem;">&rarr;</div>\n'
        f'<div style="background-color:#1e293b; border-left:4px solid #38BDF8; border-radius:6px; padding:7px 11px; flex:1; min-width:140px;">'
        f'<div style="font-size:0.72rem; color:#94a3b8; font-weight:600;">New Grid Bill</div>'
        f'<div style="font-size:1.00rem; color:#f8fafc; font-weight:700;">&euro;{fk.combined_grid_total_eur:,.0f} / yr</div>'
        f'</div>\n'
        f'<div style="color:#64748b; font-weight:800; font-size:1.05rem;">+</div>\n'
        f'<div style="background-color:#1e293b; border-left:4px solid #F59E0B; border-radius:6px; padding:7px 11px; flex:1; min-width:145px;">'
        f'<div style="font-size:0.72rem; color:#94a3b8; font-weight:600;">Hardware O&amp;M &amp; Fuel</div>'
        f'<div style="font-size:1.00rem; color:#f8fafc; font-weight:700;">&euro;{fk.system_om_and_fuel_y1_eur:,.0f} / yr</div>'
        f'</div>\n'
        f'<div style="color:#64748b; font-weight:800; font-size:1.05rem;">&minus;</div>\n'
        f'<div style="background-color:#1e293b; border-left:4px solid #10B981; border-radius:6px; padding:7px 11px; flex:1; min-width:135px;">'
        f'<div style="font-size:0.72rem; color:#94a3b8; font-weight:600;">Solar Export Income</div>'
        f'<div style="font-size:1.00rem; color:#f8fafc; font-weight:700;">&euro;{fk.solar_export_revenue_eur:,.0f} / yr</div>'
        f'</div>\n'
        f'<div style="color:#38BDF8; font-weight:800; font-size:1.10rem;">=</div>\n'
        f'<div style="background-color:#0f172a; border:1.5px solid #38BDF8; border-radius:6px; padding:7px 12px; flex:1.1; min-width:155px;">'
        f'<div style="font-size:0.72rem; color:#38BDF8; font-weight:700; text-transform:uppercase;">Combined Annual Cost</div>'
        f'<div style="font-size:1.02rem; color:#ffffff; font-weight:800;">&euro;{fk.total_annual_opex_eur:,.0f} / yr</div>'
        f'</div>\n'
        f'<div style="color:{sav_color}; font-weight:800; font-size:1.10rem;">&rarr;</div>\n'
        f'<div style="background-color:{sav_bg}; border:2px solid {sav_color}; border-radius:6px; padding:7px 12px; flex:1.2; min-width:170px;">'
        f'<div style="font-size:0.72rem; color:{sav_color}; font-weight:800; text-transform:uppercase;">Net Annual Savings</div>'
        f'<div style="font-size:1.06rem; color:#ffffff; font-weight:800;">&euro;{fk.annual_savings_eur:+,.0f} / yr</div>'
        f'</div>\n'
        f'</div>\n'
        f'<div style="display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:10px; margin-top:9px; padding-top:8px; border-top:1px solid #1e293b; font-size:0.80rem; color:#cbd5e1;">\n'
        f'<div><b>Net Investment (CAPEX):</b> Solar &euro;{fk.solar_capex_eur:,.0f} + Battery &euro;{fk.battery_capex_eur:,.0f} + Generator &euro;{fk.generator_capex_eur:,.0f} &minus; Avoided Grid Upgrade &euro;{fk.avoided_grid_upgrade_capex_eur:,.0f} = <b style="color:#ffffff;">&euro;{fk.total_capex_eur:,.0f}</b></div>\n'
        f'<div><b>Simple Payback:</b> <span style="color:#f8fafc; font-weight:700;">{pb_str}</span> &nbsp;|&nbsp; <b>15-Year NPV:</b> <span style="color:{npv_color}; font-weight:700;">&euro;{fk.npv_15y_eur:+,.0f}</span></div>\n'
        f'</div>\n'
        f'</div>'
    )


def _render_sub_ledger_html(
    header_title: str,
    columns: List[str],
    rows: List[dict],
    footer_cells: List[str],
    accent_color: str = "#38BDF8",
    is_enabled: bool = True,
) -> str:
    """
    Renders a clean dark-themed HTML Sub-Ledger table showing how costs and savings add up.
    Each entry in `rows` can be either:
      - {"group": "Group Title"} for a full-width category header row, or
      - {"cells": [...], "highlight": Optional[str]} for a standard data row.
    """
    wrapper_style = (
        "border-radius:8px; border:1px solid #334155; overflow:hidden; margin-bottom:10px;"
        if is_enabled
        else "border-radius:8px; border:1px dashed #475569; overflow:hidden; margin-bottom:10px; opacity:0.48; filter:grayscale(100%);"
    )
    status_badge = "" if is_enabled else " &mdash; [INACTIVE: &euro;0]"

    hdr_cells_html = "".join(
        f'<th style="padding:7px 9px; text-align:{"left" if i < 2 else "right"}; white-space:nowrap;">{col}</th>'
        for i, col in enumerate(columns)
    )

    body_rows_html: List[str] = []
    data_idx = 0
    for row in rows:
        if "group" in row:
            body_rows_html.append(
                f'<tr style="background-color:#0b1329; border-bottom:1px solid #334155;">'
                f'<td colspan="{len(columns)}" style="padding:6px 9px; color:{accent_color}; font-size:0.75rem; font-weight:700; text-transform:uppercase; letter-spacing:0.04em;">{row["group"]}</td>'
                f'</tr>'
            )
            continue

        bg = "#1e293b" if data_idx % 2 == 0 else "#0f172a"
        data_idx += 1
        cells = row.get("cells", [])
        hl = row.get("highlight")
        row_td: List[str] = []
        for i, cell in enumerate(cells):
            if i == 0:
                style = "padding:6px 9px; color:#f1f5f9; font-size:0.82rem; font-weight:500;"
            elif i == 1:
                style = "padding:6px 9px; color:#cbd5e1; font-size:0.78rem; font-family:monospace;"
            elif hl and i == len(cells) - 1:
                style = f"padding:6px 9px; text-align:right; color:{hl}; font-size:0.83rem; font-weight:700; white-space:nowrap;"
            elif i == len(cells) - 1:
                style = "padding:6px 9px; text-align:right; color:#f8fafc; font-size:0.83rem; font-weight:600; white-space:nowrap;"
            else:
                style = "padding:6px 9px; text-align:right; color:#e2e8f0; font-size:0.82rem; white-space:nowrap;"
            row_td.append(f'<td style="{style}">{cell}</td>')
        body_rows_html.append(f'<tr style="background-color:{bg}; border-bottom:1px solid #334155;">{"".join(row_td)}</tr>')

    ftr_cells_html: List[str] = []
    for i, cell in enumerate(footer_cells):
        align = "left" if i == 0 else "right"
        colspan_attr = f' colspan="{len(columns) - len(footer_cells) + 1}"' if (i == 0 and len(footer_cells) < len(columns)) else ""
        color = "#ffffff" if i == len(footer_cells) - 1 else accent_color
        ftr_cells_html.append(
            f'<td{colspan_attr} style="padding:8px 9px; text-align:{align}; color:{color}; font-size:0.86rem; white-space:nowrap;">{cell}</td>'
        )

    return (
        f'<div style="{wrapper_style}">\n'
        f'<div style="background-color:#0f172a; padding:8px 12px; border-bottom:2px solid {accent_color}; font-weight:700; color:#f8fafc; font-size:0.88rem;">'
        f'{header_title}{status_badge}'
        f'</div>\n'
        f'<table style="width:100%; border-collapse:collapse; font-family:-apple-system, BlinkMacSystemFont, sans-serif;">\n'
        f'<thead><tr style="background-color:#090d16; border-bottom:1px solid #475569; color:#94a3b8; font-size:0.72rem; text-transform:uppercase; letter-spacing:0.04em;">{hdr_cells_html}</tr></thead>\n'
        f'<tbody>{"".join(body_rows_html)}</tbody>\n'
        f'<tfoot><tr style="background-color:#0b1329; border-top:2px solid {accent_color}; font-weight:700;">{"".join(ftr_cells_html)}</tr></tfoot>\n'
        f'</table>\n'
        f'</div>'
    )


@st.fragment
def _render_monthly_grid_bill_progression_fragment(sim_res) -> None:
    """Isolates 12-Month Electricity & Grid Bill progression chart & ledger inside a fragment."""
    with st.container(border=True):
        st.markdown("##### :material/calendar_month: 3. Monthly Costs")
        view_mode = st.radio(
            "Monthly Progression Perspective",
            options=[
                "Combined System Bill",
                "Current Situation Bill",
                "Monthly Bill Comparison",
            ],
            index=0,
            horizontal=True,
            key="comb_fin_monthly_grid_view_mode",
            label_visibility="collapsed",
        )

        mc_col1, mc_col2 = st.columns([0.52, 0.48], gap="medium")
        with mc_col1:
            fig_monthly = create_monthly_grid_bill_progression_figure(sim_res, view_mode=view_mode)
            st.plotly_chart(
                fig_monthly,
                use_container_width=True,
                config={"scrollZoom": False, "displayModeBar": "hover", "responsive": True},
                key=f"comb_fin_monthly_grid_chart_{view_mode.lower().replace(' ', '_')}",
            )

        with mc_col2:
            m_df = sim_res.monthly_cost_df
            if m_df is not None and not m_df.empty:
                stmt_rows = []
                for _, r in m_df.iterrows():
                    comb_grid = (
                        float(r["Combined Grid Energy & Taxes (€)"])
                        + float(r["Combined Network & Standing (€)"])
                        + float(r["Combined Overload Penalty (€)"])
                    )
                    base_bill = float(r["Current situation Total (€)"])
                    dso_val = float(r["Combined DSO Total (€)"]) if "Combined DSO Total (€)" in m_df.columns else float(r["Combined Network & Standing (€)"])
                    supp_tax = float(r["Combined Supply & Tax (€)"]) if "Combined Supply & Tax (€)" in m_df.columns else float(r["Combined Grid Energy & Taxes (€)"])
                    stmt_rows.append({
                        "Month": str(r["Month"]),
                        "Peak (kW)": round(float(r.get("Combined Grid Peak (kW)", 0.0)), 1),
                        "Grid Import (kWh)": round(float(r.get("Combined Grid Import (kWh)", 0.0)), 0),
                        "Grid DSO (€)": round(dso_val, 0),
                        "Supply & Tax (€)": round(supp_tax, 0),
                        "Penalty (€)": round(float(r["Combined Overload Penalty (€)"]), 0),
                        "With System Bill (€)": round(comb_grid, 0),
                        "Grid Savings (€)": round(base_bill - comb_grid, 0),
                    })
                st.dataframe(
                    pd.DataFrame(stmt_rows),
                    use_container_width=True,
                    hide_index=True,
                    height=370,
                )


@st.fragment
def _render_financial_chart_gallery_fragment(sim_res) -> None:
    """Isolates financial chart perspective switching inside a lightweight fragment."""
    with st.container(border=True):
        st.markdown("##### :material/analytics: Financial Charts")
        gallery_choice = st.radio(
            "Visualization Perspective",
            options=[
                "15-Year Cumulative TCO & Break-Even Trajectory",
                "Annual Cost Bridge (Waterfall)",
                "4-Pillar Annual Cost Comparison",
                "12-Month Seasonal Cashflow",
            ],
            index=0,
            horizontal=True,
            key="comb_fin_chart_gallery_sel",
            label_visibility="collapsed",
        )

        if gallery_choice == "15-Year Cumulative TCO & Break-Even Trajectory":
            fig_fin = create_financial_tco_trajectory_figure(sim_res)
        elif gallery_choice == "Annual Cost Bridge (Waterfall)":
            fig_fin = create_financial_waterfall_bridge_figure(sim_res)
        elif gallery_choice == "4-Pillar Annual Cost Comparison":
            fig_fin = create_financial_cost_comparison_figure(sim_res)
        else:
            fig_fin = create_financial_monthly_cashflow_figure(sim_res)

        st.plotly_chart(
            fig_fin,
            use_container_width=True,
            config={
                "scrollZoom": False,
                "displayModeBar": "hover",
                "responsive": True,
            },
            key=f"comb_fin_gallery_{gallery_choice.replace(' ', '_').replace('(', '').replace(')', '').replace('-', '_').lower()}",
        )


@st.fragment
def _render_cashflow_table_expander_fragment(sim_res) -> None:
    """Isolates the 15-year cashflow table behind a lazy expander + toggle to avoid unnecessary renders."""
    with st.expander(":material/table_chart: 15-Year Cashflow Table", expanded=False):
        show_cf_tbl = st.checkbox(
            "Show 15-Year Table",
            value=True,
            key="comb_fin_show_15y_ledger_chk",
        )
        if show_cf_tbl and sim_res.cashflow_15y_df is not None and not sim_res.cashflow_15y_df.empty:
            st.dataframe(
                sim_res.cashflow_15y_df,
                use_container_width=True,
                hide_index=True,
            )


def _render_subtab6_1_grid_tariffs(sim_res, cur_sys: CombinedSystemConfig, cur_fin: CombinedFinancialConfig) -> None:
    """Sub-Tab 6.1: Electricity Bill & Grid Tariffs (3-Zone Layout: Inputs | Bill Sub-Ledger | Monthly Progression)."""
    with st.expander(":material/account_balance: Utility Presets", expanded=False):
        with st.form("comb_utility_preset_form"):
            dso_opts = get_dso_preset_options()
            supp_opts = get_supplier_preset_options()
            meter_opts = get_metering_preset_options()

            u_c1, u_c2, u_c3, u_btn = st.columns([1.3, 1.3, 1.3, 1.1])
            with u_c1:
                dso_list = list(dso_opts.keys())
                sel_dso = st.selectbox("Grid Operator (DSO)", options=dso_list, index=0, key="comb_preset_dso_sel")
                tier_list = dso_opts.get(sel_dso, ["MS-D (125 t/m 1.500 kW)"])
                sel_tier = st.selectbox("Voltage & Capacity Tier", options=tier_list, index=0, key="comb_preset_tier_sel")
            with u_c2:
                supp_list = list(supp_opts.keys())
                sel_supp = st.selectbox("Energy Supplier", options=supp_list, index=0, key="comb_preset_supp_sel")
                plan_list = supp_opts.get(sel_supp, ["Vast 1 Jaar (Dubbeltarief HT/NT)"])
                sel_plan = st.selectbox("Contract Tariff Plan", options=plan_list, index=0, key="comb_preset_plan_sel")
            with u_c3:
                meter_list = list(meter_opts.keys())
                sel_meter = st.selectbox("Metering Company", options=meter_list, index=0, key="comb_preset_meter_sel")
                m_plan_list = meter_opts.get(sel_meter, ["Kwartierdata Telemetrie MS (Grootverbruik RLM)"])
                sel_m_plan = st.selectbox("Metering Package", options=m_plan_list, index=0, key="comb_preset_mplan_sel")
            with u_btn:
                st.write("")
                st.write("")
                apply_tariffs = st.form_submit_button(
                    "Load Selected Utility Tariffs",
                    icon=":material/download:",
                    type="primary",
                    use_container_width=True,
                )

        if apply_tariffs:
            apply_utility_tariff_presets(
                dso_choice=sel_dso,
                tier_choice=sel_tier,
                supp_choice=sel_supp,
                supp_plan=sel_plan,
                meter_choice=sel_meter,
                meter_tier=sel_m_plan,
                fin_cfg=cur_fin,
            )
            st.session_state["comb_fin_supp_kwh"] = cur_fin.supplier_energy_price_eur_kwh
            st.session_state["comb_fin_supp_fix"] = cur_fin.supplier_fixed_fee_eur_month
            st.session_state["comb_fin_dso_cap"] = cur_fin.dso_capacity_fee_eur_kw_month
            st.session_state["comb_fin_dso_peak"] = cur_fin.dso_peak_demand_fee_eur_kw_month
            st.session_state["comb_fin_dso_pen"] = cur_fin.grid_overload_penalty_eur_kw
            st.session_state["comb_fin_dso_fix"] = cur_fin.dso_fixed_fee_eur_month
            st.session_state["comb_fin_dso_vol"] = cur_fin.dso_transport_eur_kwh
            st.session_state["comb_fin_meter_fix"] = cur_fin.metering_fixed_fee_eur_month
            evaluate_combined_financials(sim_res, cur_fin)
            st.session_state.pop("comb_cached_excel_bytes", None)
            st.rerun(scope="fragment")

    col_za, col_zb = st.columns([0.48, 0.52], gap="large")

    with col_za:
        st.markdown("##### :material/tune: 1. Tariff Rates")
        with st.form("comb_tariff_inputs_form"):
            st.markdown("**A. Grid Connection, Peaks & Penalties (Grid Operator)**")
            g1, g2 = st.columns(2)
            with g1:
                dso_fix = st.number_input(
                    "Monthly Grid Base Fee (€/month)",
                    min_value=0.0, max_value=5000.0, value=float(cur_fin.dso_fixed_fee_eur_month), step=10.0,
                    key="comb_fin_dso_fix",
                )
                dso_cap = st.number_input(
                    "Booked Grid Capacity (€/kW/mo)",
                    min_value=0.0, max_value=100.0, value=float(cur_fin.dso_capacity_fee_eur_kw_month), step=0.25, format="%.2f",
                    key="comb_fin_dso_cap",
                    help="Charged monthly on the contracted Grid Limit (kW).",
                )
                dso_vol = st.number_input(
                    "Grid Transport Rate (€/kWh)",
                    min_value=0.0, max_value=0.50, value=float(cur_fin.dso_transport_eur_kwh), step=0.005, format="%.4f",
                    key="comb_fin_dso_vol",
                )
            with g2:
                dso_peak = st.number_input(
                    "Monthly Peak Demand (€/kW/mo)",
                    min_value=0.0, max_value=100.0, value=float(cur_fin.dso_peak_demand_fee_eur_kw_month), step=0.25, format="%.2f",
                    key="comb_fin_dso_peak",
                    help="Charged monthly on the highest measured 15-min peak imported from the grid.",
                )
                dso_pen = st.number_input(
                    "Overload Penalty (€/kW above limit)",
                    min_value=0.0, max_value=500.0, value=float(cur_fin.grid_overload_penalty_eur_kw), step=1.0,
                    key="comb_fin_dso_pen",
                )
                avoided_trafo = st.number_input(
                    "Avoided Transformer Rental (€/mo)",
                    min_value=0.0, max_value=50000.0, value=float(cur_fin.avoided_transformer_rent_eur_month), step=50.0,
                    key="comb_fin_avoided_trafo",
                    help="Monthly transformer rent saved when staying within grid capacity.",
                )

            st.markdown("**B. Electricity Purchase & Solar Feed-in (Supplier)**")
            s1, s2, s3 = st.columns(3)
            with s1:
                supp_kwh = st.number_input(
                    "Electricity Price (€/kWh)",
                    min_value=0.0, max_value=2.0, value=float(cur_fin.supplier_energy_price_eur_kwh), step=0.01, format="%.3f",
                    key="comb_fin_supp_kwh",
                )
            with s2:
                supp_fix = st.number_input(
                    "Supplier Base Fee (€/mo)",
                    min_value=0.0, max_value=5000.0, value=float(cur_fin.supplier_fixed_fee_eur_month), step=10.0,
                    key="comb_fin_supp_fix",
                )
            with s3:
                solar_fi = st.number_input(
                    "Solar Feed-in (€/kWh)",
                    min_value=0.0, max_value=0.50, value=float(cur_fin.solar_export_feed_in_eur_kwh), step=0.01, format="%.3f",
                    key="comb_fin_solar_fi",
                    help="Revenue received per kWh of solar surplus exported to the grid.",
                )

            st.markdown("**C. Metering & Government Taxes**")
            m1, m2, m3 = st.columns(3)
            with m1:
                meter_fix = st.number_input(
                    "Metering Fee (€/mo)",
                    min_value=0.0, max_value=2000.0, value=float(cur_fin.metering_fixed_fee_eur_month), step=5.0,
                    key="comb_fin_meter_fix",
                )
            with m2:
                tax_kwh = st.number_input(
                    "Energy Tax (€/kWh)",
                    min_value=0.0, max_value=1.0, value=float(cur_fin.energy_tax_eur_kwh), step=0.005, format="%.4f",
                    key="comb_fin_tax_kwh",
                )
            with m3:
                tax_pct = st.number_input(
                    "Tax Surcharge (%)",
                    min_value=0.0, max_value=50.0, value=float(cur_fin.tax_surcharge_pct), step=1.0,
                    key="comb_fin_tax_pct",
                )

            tariffs_submitted = st.form_submit_button(
                "Apply Grid & Electricity Tariffs",
                icon=":material/check_circle:",
                type="primary",
                use_container_width=True,
            )

        if tariffs_submitted:
            cur_fin.dso_fixed_fee_eur_month = float(dso_fix)
            cur_fin.dso_capacity_fee_eur_kw_month = float(dso_cap)
            cur_fin.dso_peak_demand_fee_eur_kw_month = float(dso_peak)
            cur_fin.dso_transport_eur_kwh = float(dso_vol)
            cur_fin.grid_overload_penalty_eur_kw = float(dso_pen)
            cur_fin.avoided_transformer_rent_eur_month = float(avoided_trafo)
            cur_fin.supplier_energy_price_eur_kwh = float(supp_kwh)
            cur_fin.supplier_fixed_fee_eur_month = float(supp_fix)
            cur_fin.solar_export_feed_in_eur_kwh = float(solar_fi)
            cur_fin.metering_fixed_fee_eur_month = float(meter_fix)
            cur_fin.energy_tax_eur_kwh = float(tax_kwh)
            cur_fin.tax_surcharge_pct = float(tax_pct)
            evaluate_combined_financials(sim_res, cur_fin)
            st.session_state.pop("comb_cached_excel_bytes", None)
            st.rerun(scope="fragment")

    with col_zb:
        st.markdown("##### :material/receipt_long: 2. Annual Bill Summary")
        fk = sim_res.financial_kpis
        kpis = sim_res.kpis
        m_df = sim_res.monthly_cost_df

        base_kwh = float(kpis.annual_consumption_kwh)
        comb_kwh = float(kpis.grid_import_total_kwh)
        avg_base_pk = float(m_df["Current situation Peak (kW)"].mean()) if (not m_df.empty and "Current situation Peak (kW)" in m_df.columns) else float(kpis.original_peak_kw)
        avg_comb_pk = float(m_df["Combined Grid Peak (kW)"].mean()) if (not m_df.empty and "Combined Grid Peak (kW)" in m_df.columns) else float(kpis.new_grid_peak_kw)

        def _row_bill(item: str, calc: str, b_val: float, c_val: float) -> dict:
            sav = b_val - c_val
            hl = "#22C55E" if sav > 0.5 else ("#EF4444" if sav < -0.5 else None)
            return {
                "cells": [
                    item,
                    calc,
                    f"&euro;{b_val:,.0f}",
                    f"&euro;{c_val:,.0f}",
                    f"&euro;{sav:+,.0f}",
                ],
                "highlight": hl,
            }

        bill_rows = [
            {"group": "1. Electricity Supply (Retailer)"},
            _row_bill(
                "1.1 Purchased Energy",
                f"{comb_kwh:,.0f} vs {base_kwh:,.0f} kWh &times; &euro;{cur_fin.supplier_energy_price_eur_kwh:.3f}",
                fk.baseline_supply_energy_eur,
                fk.combined_supply_energy_eur,
            ),
            _row_bill(
                "1.2 Supplier Base Fee",
                f"12 mos &times; &euro;{cur_fin.supplier_fixed_fee_eur_month:.2f}/mo",
                fk.baseline_supply_fixed_eur,
                fk.combined_supply_fixed_eur,
            ),
            {"group": "2. Grid Network (DSO)"},
            _row_bill(
                "2.1 Fixed Grid Connection Fee",
                f"12 mos &times; &euro;{cur_fin.dso_fixed_fee_eur_month:.2f}/mo",
                fk.baseline_dso_fixed_eur,
                fk.combined_dso_fixed_eur,
            ),
            _row_bill(
                "2.2 Booked Grid Capacity",
                f"{cur_sys.grid_limit_kw:,.0f} kW &times; 12 &times; &euro;{cur_fin.dso_capacity_fee_eur_kw_month:.2f}",
                fk.baseline_dso_capacity_eur,
                fk.combined_dso_capacity_eur,
            ),
            _row_bill(
                "2.3 Monthly Peak Demand",
                f"Avg {avg_comb_pk:.0f} vs {avg_base_pk:.0f} kW &times; 12 &times; &euro;{cur_fin.dso_peak_demand_fee_eur_kw_month:.2f}",
                fk.baseline_dso_peak_eur,
                fk.combined_dso_peak_eur,
            ),
            _row_bill(
                "2.4 Grid Transport Volume",
                f"{comb_kwh:,.0f} kWh &times; &euro;{cur_fin.dso_transport_eur_kwh:.3f}/kWh",
                fk.baseline_dso_transport_eur,
                fk.combined_dso_transport_eur,
            ),
            _row_bill(
                "2.5 Overload Penalties",
                f"Peak &gt; {cur_sys.grid_limit_kw:,.0f} kW &times; &euro;{cur_fin.grid_overload_penalty_eur_kw:.2f}/kW",
                fk.baseline_penalty_cost_eur,
                fk.combined_grid_penalty_cost_eur,
            ),
        ]

        if cur_fin.avoided_transformer_rent_eur_month > 0.0:
            bill_rows.append(
                _row_bill(
                    "2.6 Avoided Transformer Rent",
                    f"12 mos &times; &euro;{cur_fin.avoided_transformer_rent_eur_month:,.0f}/mo",
                    fk.baseline_dso_transformer_rent_eur,
                    fk.combined_dso_transformer_rent_eur,
                )
            )

        bill_rows.extend([
            {"group": "3. Metering & Statutory Taxes"},
            _row_bill(
                "3.1 Metering & Telemetry",
                f"12 mos &times; &euro;{cur_fin.metering_fixed_fee_eur_month:.2f}/mo",
                fk.baseline_pillar3_metering_eur,
                fk.combined_pillar3_metering_eur,
            ),
            _row_bill(
                "3.2 Government Energy Tax",
                f"{comb_kwh:,.0f} kWh &times; &euro;{cur_fin.energy_tax_eur_kwh:.4f}/kWh",
                fk.baseline_energy_tax_eur,
                fk.combined_energy_tax_eur,
            ),
        ])
        if cur_fin.tax_surcharge_pct > 0.0:
            bill_rows.append(
                _row_bill(
                    "3.3 Tax / Levy Surcharge",
                    f"{cur_fin.tax_surcharge_pct:.1f}% on net charges",
                    fk.baseline_tax_surcharge_eur,
                    fk.combined_tax_surcharge_eur,
                )
            )

        if cur_sys.enable_solar and fk.solar_export_revenue_eur > 0.0:
            bill_rows.append({"group": "4. Solar Export Credit"})
            bill_rows.append(
                {
                    "cells": [
                        "4.1 Grid Feed-in Revenue",
                        f"{kpis.solar_export_kwh:,.0f} kWh &times; &euro;{cur_fin.solar_export_feed_in_eur_kwh:.3f}",
                        "&euro;0",
                        f"-&euro;{fk.solar_export_revenue_eur:,.0f}",
                        f"&euro;{fk.solar_export_revenue_eur:+,.0f}",
                    ],
                    "highlight": "#22C55E",
                }
            )

        comb_bill_net_of_export = fk.combined_grid_total_eur - fk.solar_export_revenue_eur
        bill_savings_total = fk.baseline_total_opex_eur - comb_bill_net_of_export
        sub_html = _render_sub_ledger_html(
            header_title="Annual Electricity Bill Breakdown",
            columns=["Bill Line Item", "Calculation (Qty &times; Rate)", "Current (/yr)", "With System (/yr)", "Savings (/yr)"],
            rows=bill_rows,
            footer_cells=[
                "= TOTAL ANNUAL UTILITY BILL (NET OF EXPORT)",
                f"&euro;{fk.baseline_total_opex_eur:,.0f}",
                f"&euro;{comb_bill_net_of_export:,.0f}",
                f"&euro;{bill_savings_total:+,.0f}",
            ],
            accent_color="#38BDF8",
            is_enabled=True,
        )
        st.markdown(sub_html, unsafe_allow_html=True)

        # System Impact & Compliance Box
        if kpis.grid_limit_met:
            st.success(
                f":material/check_circle: **Grid Compliance & Bill Impact:** Peak reduced from **{kpis.original_peak_kw:,.1f} kW** to **{kpis.new_grid_peak_kw:,.1f} kW** "
                f"(within {cur_sys.grid_limit_kw:,.0f} kW limit).  \n"
                f"**Where Grid Savings Come From:** **€{fk.grid_volume_savings_y1_eur:,.0f}/yr** from reduced energy imports + "
                f"**€{fk.grid_peak_and_penalty_savings_y1_eur:,.0f}/yr** from peak shaving & avoided penalties"
                + (f" + **€{fk.solar_export_revenue_eur:,.0f}/yr** solar export income." if fk.solar_export_revenue_eur > 0 else "."),
            )
        else:
            st.warning(
                f":material/warning: **Remaining Overload Warning:** Peak reduced from **{kpis.original_peak_kw:,.1f} kW** to **{kpis.new_grid_peak_kw:,.1f} kW** "
                f"(**+{kpis.remaining_overload_kw:,.1f} kW** above {cur_sys.grid_limit_kw:,.0f} kW limit).  \n"
                f"**Where Grid Savings Come From:** **€{fk.grid_volume_savings_y1_eur:,.0f}/yr** from reduced energy imports + "
                f"**€{fk.grid_peak_and_penalty_savings_y1_eur:,.0f}/yr** from peak & penalty reductions."
            )

    _render_monthly_grid_bill_progression_fragment(sim_res)


def _render_subtab6_2_hardware_costs(sim_res, cur_sys: CombinedSystemConfig, cur_fin: CombinedFinancialConfig) -> None:
    """Sub-Tab 6.2: System Hardware & Operating Costs (Component CAPEX/OPEX Inputs + How It Adds Up Sub-Ledgers)."""
    fk = sim_res.financial_kpis
    kpis = sim_res.kpis
    deriv = sim_res.solar_derivation

    with st.form("comb_hardware_costs_form"):
        # --- 1. Solar PV System ---
        sol_badge = f"{deriv.installed_kwp:,.1f} kWp Active" if cur_sys.enable_solar else "INACTIVE — €0"
        with st.expander(f":material/solar_power: Solar Costs ({sol_badge})", expanded=cur_sys.enable_solar):
            s_in, s_led = st.columns([0.44, 0.56], gap="large")
            with s_in:
                sol_mod = st.number_input(
                    "Solar Modules (€/Wp)",
                    min_value=0.0, max_value=3.0, value=float(cur_fin.solar_modules_eur_wp), step=0.02, format="%.2f",
                    key="comb_fin_sol_mod", disabled=not cur_sys.enable_solar,
                )
                sol_inv = st.number_input(
                    "Solar Inverter (€/W)",
                    min_value=0.0, max_value=2.0, value=float(cur_fin.solar_inverter_eur_w), step=0.01, format="%.2f",
                    key="comb_fin_sol_inv", disabled=not cur_sys.enable_solar,
                )
                sol_mnt = st.number_input(
                    "Mounting & Installation (€/Wp)",
                    min_value=0.0, max_value=3.0, value=float(cur_fin.solar_mounting_eur_wp), step=0.02, format="%.2f",
                    key="comb_fin_sol_mnt", disabled=not cur_sys.enable_solar,
                )
                sol_om = st.number_input(
                    "Annual Maintenance (% of CAPEX/yr)",
                    min_value=0.0, max_value=15.0, value=float(cur_fin.solar_om_pct_of_capex), step=0.25,
                    key="comb_fin_sol_om", disabled=not cur_sys.enable_solar,
                )
            with s_led:
                sol_net_benefit = fk.solar_direct_value_y1_eur + fk.solar_export_revenue_eur - fk.solar_om_eur
                sol_rows = [
                    {"group": "Upfront Investment (CAPEX)"},
                    {"cells": ["1.1 Solar Modules", f"{deriv.installed_kwp:,.1f} kWp &times; 1,000 &times; &euro;{cur_fin.solar_modules_eur_wp:.2f}", "&mdash;", f"&euro;{fk.solar_modules_capex_eur:,.0f}"]},
                    {"cells": ["1.2 Solar Inverters", f"{deriv.installed_kwp:,.1f} kWp &times; 1,000 &times; &euro;{cur_fin.solar_inverter_eur_w:.2f}", "&mdash;", f"&euro;{fk.solar_inverter_capex_eur:,.0f}"]},
                    {"cells": ["1.3 Mounting &amp; Installation", f"{deriv.installed_kwp:,.1f} kWp &times; 1,000 &times; &euro;{cur_fin.solar_mounting_eur_wp:.2f}", "&mdash;", f"&euro;{fk.solar_mounting_capex_eur:,.0f}"]},
                    {"group": "Annual Operating Cost &amp; Value Generated"},
                    {"cells": ["Annual Maintenance (O&amp;M)", f"{cur_fin.solar_om_pct_of_capex:.2f}% &times; &euro;{fk.solar_capex_eur:,.0f}", f"-&euro;{fk.solar_om_eur / 12.0:,.0f}", f"-&euro;{fk.solar_om_eur:,.0f}"], "highlight": "#EF4444"},
                    {"cells": ["Direct Electricity Saved", f"{kpis.solar_direct_kwh:,.0f} kWh &times; &euro;{fk.variable_grid_rate_eur_kwh:.3f}", f"+&euro;{fk.solar_direct_value_y1_eur / 12.0:,.0f}", f"+&euro;{fk.solar_direct_value_y1_eur:,.0f}"], "highlight": "#22C55E"},
                    {"cells": ["Export Feed-in Revenue", f"{kpis.solar_export_kwh:,.0f} kWh &times; &euro;{cur_fin.solar_export_feed_in_eur_kwh:.3f}", f"+&euro;{fk.solar_export_revenue_eur / 12.0:,.0f}", f"+&euro;{fk.solar_export_revenue_eur:,.0f}"], "highlight": "#22C55E"},
                ]
                st.markdown(
                    _render_sub_ledger_html(
                        header_title=f"Solar PV Financial Breakdown (Total CAPEX: &euro;{fk.solar_capex_eur:,.0f})",
                        columns=["Line Item", "Calculation (Qty &times; Rate)", "Monthly", "One-Off / Annual"],
                        rows=sol_rows,
                        footer_cells=[
                            "= NET ANNUAL SOLAR VALUE (AFTER O&amp;M)",
                            f"&euro;{sol_net_benefit / 12.0:+,.0f}/mo",
                            f"&euro;{sol_net_benefit:+,.0f}/yr",
                        ],
                        accent_color="#FACC15",
                        is_enabled=cur_sys.enable_solar,
                    ),
                    unsafe_allow_html=True,
                )

        # --- 2. Battery Storage (BESS) ---
        bat_badge = f"{cur_sys.battery_capacity_kwh:,.0f} kWh / {cur_sys.battery_power_kw:,.0f} kW Active" if cur_sys.enable_battery else "INACTIVE — €0"
        with st.expander(f":material/battery_charging_full: Battery Costs ({bat_badge})", expanded=cur_sys.enable_battery):
            b_in, b_led = st.columns([0.44, 0.56], gap="large")
            with b_in:
                b1, b2 = st.columns(2)
                with b1:
                    bat_rack = st.number_input(
                        "Storage Racks (€/kWh)",
                        min_value=0.0, max_value=2000.0, value=float(cur_fin.battery_capex_eur_kwh), step=10.0,
                        key="comb_fin_bat_rack", disabled=not cur_sys.enable_battery,
                    )
                    bat_bop = st.number_input(
                        "Installation & Cabling (€)",
                        min_value=0.0, max_value=500000.0, value=float(cur_fin.battery_fixed_bop_eur), step=1000.0,
                        key="comb_fin_bat_bop", disabled=not cur_sys.enable_battery,
                    )
                with b2:
                    bat_inv = st.number_input(
                        "Power Inverter (€/kW)",
                        min_value=0.0, max_value=2000.0, value=float(cur_fin.battery_capex_eur_kw), step=10.0,
                        key="comb_fin_bat_inv", disabled=not cur_sys.enable_battery,
                    )
                    bat_om = st.number_input(
                        "Annual Maintenance (% of CAPEX/yr)",
                        min_value=0.0, max_value=15.0, value=float(cur_fin.battery_om_pct_of_capex), step=0.25,
                        key="comb_fin_bat_om", disabled=not cur_sys.enable_battery,
                    )
                a1, a2, a3 = st.columns([1.3, 0.85, 0.85])
                with a1:
                    en_aug = st.checkbox(
                        "Mid-Life Cell Replacement",
                        value=bool(cur_fin.enable_battery_augmentation),
                        key="comb_fin_bat_aug_chk", disabled=not cur_sys.enable_battery,
                    )
                with a2:
                    aug_yr = st.number_input(
                        "Year", min_value=5, max_value=14, value=int(cur_fin.battery_augmentation_year), step=1,
                        key="comb_fin_bat_aug_yr", disabled=not cur_sys.enable_battery,
                    )
                with a3:
                    aug_pct = st.number_input(
                        "Cost (% Racks)", min_value=10.0, max_value=100.0, value=float(cur_fin.battery_augmentation_pct_of_racks), step=5.0,
                        key="comb_fin_bat_aug_pct", disabled=not cur_sys.enable_battery,
                    )
            with b_led:
                bat_rows = [
                    {"group": "Upfront Investment (CAPEX)"},
                    {"cells": ["2.1 Storage Racks", f"{cur_sys.battery_capacity_kwh:,.0f} kWh &times; &euro;{cur_fin.battery_capex_eur_kwh:,.0f}/kWh", "&mdash;", f"&euro;{fk.battery_rack_capex_eur:,.0f}"]},
                    {"cells": ["2.2 Bidirectional Inverter", f"{cur_sys.battery_power_kw:,.0f} kW &times; &euro;{cur_fin.battery_capex_eur_kw:,.0f}/kW", "&mdash;", f"&euro;{fk.battery_inverter_capex_eur:,.0f}"]},
                    {"cells": ["2.3 Installation &amp; Cabling", "Fixed Balance of Plant", "&mdash;", f"&euro;{fk.battery_bop_capex_eur:,.0f}"]},
                    {"cells": [f"Planned Cell Replacement (Yr {int(cur_fin.battery_augmentation_year)})", f"{cur_fin.battery_augmentation_pct_of_racks:.0f}% of Racks (if enabled)", "&mdash;", f"&euro;{fk.battery_augmentation_eur:,.0f}"]},
                    {"group": "Annual Operating Cost &amp; Value Enabled"},
                    {"cells": ["Annual Battery Maintenance (O&amp;M)", f"{cur_fin.battery_om_pct_of_capex:.2f}% &times; &euro;{fk.battery_capex_eur:,.0f}", f"&euro;{fk.battery_om_eur / 12.0:,.0f}", f"&euro;{fk.battery_om_eur:,.0f}"], "highlight": "#EF4444"},
                    {"cells": ["Stored Solar Discharged", f"{kpis.solar_via_battery_kwh:,.0f} kWh &times; &euro;{fk.variable_grid_rate_eur_kwh:.3f}", f"+&euro;{fk.solar_stored_value_y1_eur / 12.0:,.0f}", f"+&euro;{fk.solar_stored_value_y1_eur:,.0f}"], "highlight": "#22C55E"},
                    {"cells": ["Peak Shaving &amp; Penalty Savings", f"Shared peak reduction ({kpis.peak_reduction_kw:,.1f} kW)", f"+&euro;{fk.grid_peak_and_penalty_savings_y1_eur / 12.0:,.0f}", f"+&euro;{fk.grid_peak_and_penalty_savings_y1_eur:,.0f}"], "highlight": "#22C55E"},
                ]
                st.markdown(
                    _render_sub_ledger_html(
                        header_title=f"Battery Storage (BESS) Financial Breakdown (Total CAPEX: &euro;{fk.battery_capex_eur:,.0f})",
                        columns=["Line Item", "Calculation (Qty &times; Rate)", "Monthly", "One-Off / Annual"],
                        rows=bat_rows,
                        footer_cells=[
                            "= ANNUAL BATTERY MAINTENANCE (O&amp;M)",
                            f"&euro;{fk.battery_om_eur / 12.0:,.0f}/mo",
                            f"&euro;{fk.battery_om_eur:,.0f}/yr",
                        ],
                        accent_color="#22C55E",
                        is_enabled=cur_sys.enable_battery,
                    ),
                    unsafe_allow_html=True,
                )

        # --- 3. Peaking Generator ---
        gen_badge = f"{cur_sys.generator_rated_kw:,.0f} kW {cur_sys.fuel_type} Active" if cur_sys.enable_generator else "INACTIVE — €0"
        with st.expander(f":material/power: Generator Costs ({gen_badge})", expanded=cur_sys.enable_generator):
            gn_in, gn_led = st.columns([0.44, 0.56], gap="large")
            with gn_in:
                gen_model = st.selectbox(
                    "Acquisition Mode",
                    options=["Purchase (CAPEX)", "Monthly Rental (OPEX)"],
                    index=0 if cur_fin.generator_cost_model == "Purchase (CAPEX)" else 1,
                    key="comb_fin_gen_model", disabled=not cur_sys.enable_generator,
                )
                g_c1, g_c2 = st.columns(2)
                with g_c1:
                    gen_capex = st.number_input(
                        "Purchase Price (€)",
                        min_value=0.0, max_value=2000000.0, value=float(cur_fin.generator_capex_eur), step=1000.0,
                        key="comb_fin_gen_capex", disabled=not cur_sys.enable_generator,
                    )
                    fuel_pr = st.number_input(
                        f"Fuel Price (€/{kpis.generator_fuel_unit})",
                        min_value=0.0, max_value=10.0, value=float(cur_fin.fuel_price_eur_per_unit), step=0.05, format="%.2f",
                        key="comb_fin_gen_fuel", disabled=not cur_sys.enable_generator,
                    )
                with g_c2:
                    gen_rent = st.number_input(
                        "Monthly Rental (€/mo)",
                        min_value=0.0, max_value=100000.0, value=float(cur_fin.generator_rental_eur_month), step=100.0,
                        key="comb_fin_gen_rent", disabled=not cur_sys.enable_generator,
                    )
                    gen_maint = st.number_input(
                        "Maintenance (€/op hr)",
                        min_value=0.0, max_value=500.0, value=float(cur_fin.generator_maintenance_eur_per_hour), step=0.5,
                        key="comb_fin_gen_maint", disabled=not cur_sys.enable_generator,
                    )
            with gn_led:
                gen_rows = [
                    {"group": f"Acquisition ({cur_fin.generator_cost_model})"},
                    {"cells": ["3.1 Purchase Investment (CAPEX)", "One-off purchase (if selected)", "&mdash;", f"&euro;{fk.generator_capex_eur:,.0f}"]},
                    {"cells": ["3.2 Rental / Leasing Fee (OPEX)", f"12 mos &times; &euro;{cur_fin.generator_rental_eur_month:,.0f}/mo (if rental)", f"&euro;{fk.generator_rental_cost_eur / 12.0:,.0f}", f"&euro;{fk.generator_rental_cost_eur:,.0f}"]},
                    {"group": "Annual Fuel &amp; Operating Maintenance"},
                    {"cells": [f"3.3 Fuel Consumption ({cur_sys.fuel_type})", f"{kpis.generator_fuel_total:,.1f} {kpis.generator_fuel_unit} &times; &euro;{cur_fin.fuel_price_eur_per_unit:.2f}", f"&euro;{fk.generator_fuel_cost_eur / 12.0:,.0f}", f"&euro;{fk.generator_fuel_cost_eur:,.0f}"]},
                    {"cells": ["3.4 Running Hour Service", f"{kpis.generator_runtime_hours:,.1f} hrs &times; &euro;{cur_fin.generator_maintenance_eur_per_hour:.2f}/hr", f"&euro;{fk.generator_maintenance_cost_eur / 12.0:,.0f}", f"&euro;{fk.generator_maintenance_cost_eur:,.0f}"]},
                ]
                st.markdown(
                    _render_sub_ledger_html(
                        header_title=f"Generator Financial Breakdown (Generated to Load: {kpis.generator_to_load_kwh:,.0f} kWh/yr)",
                        columns=["Line Item", "Calculation (Qty &times; Rate)", "Monthly", "One-Off / Annual"],
                        rows=gen_rows,
                        footer_cells=[
                            "= TOTAL GENERATOR ANNUAL OPEX",
                            f"&euro;{fk.generator_total_opex_eur / 12.0:,.0f}/mo",
                            f"&euro;{fk.generator_total_opex_eur:,.0f}/yr",
                        ],
                        accent_color="#F97316",
                        is_enabled=cur_sys.enable_generator,
                    ),
                    unsafe_allow_html=True,
                )

        # --- 4. Avoided Grid Expansion Credits ---
        with st.expander(":material/savings: Saved Grid Upgrade Cost", expanded=bool(cur_fin.avoided_grid_upgrade_capex_eur > 0.0)):
            av_in, av_led = st.columns([0.44, 0.56], gap="large")
            with av_in:
                avoided_upgrade = st.number_input(
                    "One-Off Avoided Grid Upgrade Cost (€)",
                    min_value=0.0, max_value=5000000.0, value=float(cur_fin.avoided_grid_upgrade_capex_eur), step=5000.0,
                    key="comb_fin_avoided_upgrade",
                    help="Capital expenditure avoided by peak shaving instead of paying the DSO for a grid expansion.",
                )
            with av_led:
                st.info(
                    f":material/info: **Net Project Investment Summary:**  \n"
                    f"Gross Hardware CAPEX (**€{fk.gross_capex_eur:,.0f}**) &minus; Avoided Grid Upgrade (**€{fk.avoided_grid_upgrade_capex_eur:,.0f}**) "
                    f"= **Net Turnkey Investment: €{fk.total_capex_eur:,.0f}**."
                )

        hw_submitted = st.form_submit_button(
            "Apply Hardware & Operating Costs",
            icon=":material/check_circle:",
            type="primary",
            use_container_width=True,
        )

    if hw_submitted:
        if cur_sys.enable_solar:
            cur_fin.solar_modules_eur_wp = float(sol_mod)
            cur_fin.solar_inverter_eur_w = float(sol_inv)
            cur_fin.solar_mounting_eur_wp = float(sol_mnt)
            cur_fin.solar_capex_eur_kwp = None
            cur_fin.solar_om_pct_of_capex = float(sol_om)

        if cur_sys.enable_battery:
            cur_fin.battery_capex_eur_kwh = float(bat_rack)
            cur_fin.battery_capex_eur_kw = float(bat_inv)
            cur_fin.battery_fixed_bop_eur = float(bat_bop)
            cur_fin.battery_om_pct_of_capex = float(bat_om)
            cur_fin.enable_battery_augmentation = bool(en_aug)
            cur_fin.battery_augmentation_year = int(aug_yr)
            cur_fin.battery_augmentation_pct_of_racks = float(aug_pct)

        if cur_sys.enable_generator:
            cur_fin.generator_cost_model = str(gen_model)
            cur_fin.generator_capex_eur = float(gen_capex)
            cur_fin.generator_rental_eur_month = float(gen_rent)
            cur_fin.fuel_price_eur_per_unit = float(fuel_pr)
            cur_fin.generator_maintenance_eur_per_hour = float(gen_maint)

        cur_fin.avoided_grid_upgrade_capex_eur = float(avoided_upgrade)
        evaluate_combined_financials(sim_res, cur_fin)
        st.session_state.pop("comb_cached_excel_bytes", None)
        st.rerun(scope="fragment")


def _render_subtab6_3_executive_overview(sim_res, cur_sys: CombinedSystemConfig, cur_fin: CombinedFinancialConfig) -> None:
    """Sub-Tab 6.3: Executive Summary, 15-Year Dynamics, Component Cost Matrix & Financial Charts."""
    # Long-Term Escalation, Degradation & Discount Rate Form
    with st.form("comb_fin_longterm_form"):
        st.markdown("##### :material/trending_up: Price Increases & Lifespan")
        lt1, lt2, lt3, lt4, lt_btn = st.columns([1.0, 1.0, 1.0, 1.0, 1.1])
        with lt1:
            tariff_esc = st.number_input(
                "Tariff Escalation (% p.a.)",
                min_value=0.0, max_value=15.0, value=float(cur_fin.tariff_escalation_pct_pa), step=0.5,
                key="comb_fin_tariff_esc",
                help="Annual electricity & grid tariff inflation.",
            )
        with lt2:
            om_inf = st.number_input(
                "O&M Inflation (% p.a.)",
                min_value=0.0, max_value=15.0, value=float(cur_fin.om_inflation_pct_pa), step=0.5,
                key="comb_fin_om_inf",
                help="Annual inflation for hardware maintenance and fuel.",
            )
        with lt3:
            sys_deg = st.number_input(
                "System Degradation (% p.a.)",
                min_value=0.0, max_value=5.0, value=float(cur_fin.system_degradation_pct_pa), step=0.1, format="%.2f",
                key="comb_fin_sys_deg",
                help="Annual yield/capacity degradation of solar & battery.",
            )
        with lt4:
            disc_rate = st.number_input(
                "Discount Rate for NPV (%)",
                min_value=0.0, max_value=20.0, value=float(cur_fin.discount_rate_pct), step=0.5,
                key="comb_fin_disc_rate",
            )
        with lt_btn:
            st.write("")
            st.write("")
            lt_submitted = st.form_submit_button(
                "Update Projection",
                icon=":material/refresh:",
                type="primary",
                use_container_width=True,
            )

    if lt_submitted:
        cur_fin.tariff_escalation_pct_pa = float(tariff_esc)
        cur_fin.om_inflation_pct_pa = float(om_inf)
        cur_fin.system_degradation_pct_pa = float(sys_deg)
        cur_fin.discount_rate_pct = float(disc_rate)
        evaluate_combined_financials(sim_res, cur_fin)
        st.session_state.pop("comb_cached_excel_bytes", None)
        st.rerun(scope="fragment")

    fin_kpis = sim_res.financial_kpis

    # Economic Bottleneck Alert (Automatic Diagnostic)
    if cur_sys.enable_battery and fin_kpis.battery_om_eur > 0:
        bat_om = fin_kpis.battery_om_eur
        gross_sav = fin_kpis.gross_bill_savings_y1_eur
        bat_capex = fin_kpis.battery_capex_eur
        if bat_om > 0.5 * max(1.0, gross_sav) or (gross_sav > 0 and fin_kpis.annual_savings_eur <= 0):
            st.warning(
                f"**:material/lightbulb: Economic Bottleneck Alert:** Annual battery maintenance (€{bat_om:,.0f}/yr from €{bat_capex:,.0f} CAPEX) "
                f"consumes {(bat_om / max(1.0, gross_sav) * 100.0):.1f}% of the gross electricity bill savings (€{gross_sav:,.0f}/yr). "
                f"Tip: Selecting an 80% battery capacity target or pairing a smaller battery with a peaking generator "
                f"substantially reduces CAPEX and O&M costs."
            )

    st.markdown("##### :material/account_balance: Financial Summary")

    # Row 1: Year-1 Operations & Turnkey Investment
    fk1, fk2, fk3, fk4 = st.columns(4)
    with fk1:
        capex_subtext = (
            f"Gross: €{fin_kpis.gross_capex_eur:,.0f} | Avoided: -€{fin_kpis.avoided_grid_upgrade_capex_eur:,.0f}"
            if fin_kpis.avoided_grid_upgrade_capex_eur > 0
            else f"Solar: €{fin_kpis.solar_capex_eur:,.0f} | Battery: €{fin_kpis.battery_capex_eur:,.0f} | Gen: €{fin_kpis.generator_capex_eur:,.0f}"
        )
        render_kpi_card(
            title="Net Turnkey Investment (CAPEX)",
            value=f"€{fin_kpis.total_capex_eur:,.0f}",
            subtext=capex_subtext,
            status="default",
        )
    with fk2:
        render_kpi_card(
            title="Year-1 Operating Cost (OPEX)",
            value=f"€{fin_kpis.total_annual_opex_eur:,.0f} / yr",
            subtext=f"Grid: €{fin_kpis.combined_grid_total_eur:,.0f} | O&M + Fuel: €{fin_kpis.system_om_and_fuel_y1_eur:,.0f}",
            status="default",
        )
    with fk3:
        render_kpi_card(
            title="Year-1 Net Cash Savings",
            value=f"€{fin_kpis.annual_savings_eur:,.0f} / yr",
            subtext=f"Gross Bill Savings: €{fin_kpis.gross_bill_savings_y1_eur:,.0f} - O&M: €{fin_kpis.system_om_and_fuel_y1_eur:,.0f}",
            status="ok" if fin_kpis.annual_savings_eur > 0 else "alert",
        )
    with fk4:
        pb_str = f"{fin_kpis.payback_years:.1f} yrs" if fin_kpis.payback_years is not None else "N/A"
        disc_pb_str = f"{fin_kpis.discounted_payback_years:.1f} yrs" if fin_kpis.discounted_payback_years is not None else "N/A"
        render_kpi_card(
            title="Payback (Simple & Discounted)",
            value=f"{pb_str} | {disc_pb_str}",
            subtext="Simple Payback vs. Discounted Break-Even",
            status="ok" if fin_kpis.payback_years is not None else "alert",
        )

    # Row 2: 15-Year Lifecycle & Unit Economics
    fk5, fk6, fk7, fk8 = st.columns(4)
    with fk5:
        render_kpi_card(
            title="15-Year Cumulative TCO",
            value=f"€{fin_kpis.tco_15y_combined_eur:,.0f}",
            subtext=f"Current situation: €{fin_kpis.tco_15y_baseline_eur:,.0f} (Net: €{fin_kpis.tco_15y_savings_eur:+,.0f})",
            status="ok" if fin_kpis.tco_15y_savings_eur > 0 else "default",
        )
    with fk6:
        irr_str = f"IRR: {fin_kpis.irr_15y_pct:.1f}%" if fin_kpis.irr_15y_pct is not None else "IRR: N/A"
        render_kpi_card(
            title="15-Year Net Profit (NPV) & IRR",
            value=f"€{fin_kpis.npv_15y_eur:,.0f} | {irr_str}",
            subtext=f"15-Year NPV at {cur_fin.discount_rate_pct:.1f}% discount rate",
            status="ok" if fin_kpis.npv_15y_eur > 0 else "default",
        )
    with fk7:
        render_kpi_card(
            title="On-Site Energy Cost vs. Grid",
            value=f"€{fin_kpis.system_lcoe_eur_kwh:.3f} / kWh",
            subtext=f"Effective Grid Rate: €{fin_kpis.effective_blended_grid_rate_eur_kwh:.3f} / kWh",
            status="ok" if (0.0 < fin_kpis.system_lcoe_eur_kwh < fin_kpis.effective_blended_grid_rate_eur_kwh) else "default",
        )
    with fk8:
        render_kpi_card(
            title="Peak Shaving Cost Efficiency",
            value=f"€{fin_kpis.annualized_cost_per_shaved_kw_eur:,.0f} / kW/yr",
            subtext=f"Peak Reduction: {sim_res.kpis.peak_reduction_kw:,.1f} kW shaved",
            status="default",
        )

    # Complete Component & Cost Summary Matrix
    with st.container(border=True):
        st.markdown("##### :material/summarize: System Cost Summary")
        comp_rows = [
            {"cells": ["1. Electricity Supply (Retailer)", "&euro;0", f"&euro;{fin_kpis.baseline_pillar1_supply_eur:,.0f}", f"&euro;{fin_kpis.combined_pillar1_supply_eur:,.0f}", f"&euro;{fin_kpis.baseline_pillar1_supply_eur - fin_kpis.combined_pillar1_supply_eur:+,.0f}"], "highlight": "#22C55E" if fin_kpis.baseline_pillar1_supply_eur > fin_kpis.combined_pillar1_supply_eur else None},
            {"cells": ["2. Grid Network (DSO &amp; Peaks)", f"-&euro;{fin_kpis.avoided_grid_upgrade_capex_eur:,.0f}" if fin_kpis.avoided_grid_upgrade_capex_eur > 0 else "&euro;0", f"&euro;{fin_kpis.baseline_pillar2_dso_eur:,.0f}", f"&euro;{fin_kpis.combined_pillar2_dso_eur:,.0f}", f"&euro;{fin_kpis.baseline_pillar2_dso_eur - fin_kpis.combined_pillar2_dso_eur:+,.0f}"], "highlight": "#22C55E" if fin_kpis.baseline_pillar2_dso_eur > fin_kpis.combined_pillar2_dso_eur else None},
            {"cells": ["3. Metering &amp; Statutory Taxes", "&euro;0", f"&euro;{fin_kpis.baseline_pillar3_metering_eur + fin_kpis.baseline_pillar4_taxes_eur:,.0f}", f"&euro;{fin_kpis.combined_pillar3_metering_eur + fin_kpis.combined_pillar4_taxes_eur:,.0f}", f"&euro;{(fin_kpis.baseline_pillar3_metering_eur + fin_kpis.baseline_pillar4_taxes_eur) - (fin_kpis.combined_pillar3_metering_eur + fin_kpis.combined_pillar4_taxes_eur):+,.0f}"], "highlight": "#22C55E" if fin_kpis.baseline_pillar4_taxes_eur > fin_kpis.combined_pillar4_taxes_eur else None},
            {"cells": ["4. Solar PV System (O&amp;M)", f"&euro;{fin_kpis.solar_capex_eur:,.0f}", "&euro;0", f"&euro;{fin_kpis.solar_om_eur:,.0f}", f"-&euro;{fin_kpis.solar_om_eur:,.0f}" if fin_kpis.solar_om_eur > 0 else "&euro;0"], "highlight": "#EF4444" if fin_kpis.solar_om_eur > 0 else None},
            {"cells": ["5. Battery Storage BESS (O&amp;M)", f"&euro;{fin_kpis.battery_capex_eur:,.0f}", "&euro;0", f"&euro;{fin_kpis.battery_om_eur:,.0f}", f"-&euro;{fin_kpis.battery_om_eur:,.0f}" if fin_kpis.battery_om_eur > 0 else "&euro;0"], "highlight": "#EF4444" if fin_kpis.battery_om_eur > 0 else None},
            {"cells": ["6. Peaking Generator (Fuel &amp; Service)", f"&euro;{fin_kpis.generator_capex_eur:,.0f}", "&euro;0", f"&euro;{fin_kpis.generator_total_opex_eur:,.0f}", f"-&euro;{fin_kpis.generator_total_opex_eur:,.0f}" if fin_kpis.generator_total_opex_eur > 0 else "&euro;0"], "highlight": "#EF4444" if fin_kpis.generator_total_opex_eur > 0 else None},
            {"cells": ["7. Solar Export Feed-in Revenue", "&euro;0", "&euro;0", f"-&euro;{fin_kpis.solar_export_revenue_eur:,.0f}" if fin_kpis.solar_export_revenue_eur > 0 else "&euro;0", f"+&euro;{fin_kpis.solar_export_revenue_eur:,.0f}" if fin_kpis.solar_export_revenue_eur > 0 else "&euro;0"], "highlight": "#22C55E" if fin_kpis.solar_export_revenue_eur > 0 else None},
        ]
        st.markdown(
            _render_sub_ledger_html(
                header_title="Costs &amp; Savings by Component",
                columns=["Cost Component", "One-Off CAPEX", "Current (/yr)", "With System (/yr)", "Annual Impact (/yr)"],
                rows=comp_rows,
                footer_cells=[
                    "= TOTAL COMBINED SYSTEM (NET)",
                    f"&euro;{fin_kpis.total_capex_eur:,.0f}",
                    f"&euro;{fin_kpis.baseline_total_opex_eur:,.0f}/yr",
                    f"&euro;{fin_kpis.total_annual_opex_eur:,.0f}/yr",
                    f"&euro;{fin_kpis.annual_savings_eur:+,.0f}/yr",
                ],
                accent_color="#10B981",
                is_enabled=True,
            ),
            unsafe_allow_html=True,
        )

    # Interactive Financial Chart Gallery (isolated fragment)
    _render_financial_chart_gallery_fragment(sim_res)

    # Expandable 15-Year Cashflow Table (isolated fragment)
    _render_cashflow_table_expander_fragment(sim_res)


@st.fragment
def render_subtab6_financials(sim_res) -> None:
    """
    Renders Subtab 6: Financials (Lazy-loaded, @st.fragment isolated):
      - Live Master Cost & Savings Equation Bar
      - 3 Structured Inner Sub-Tabs modeled after Currentsituation_sandbox:
          * 6.1: Electricity Bill & Grid Tariffs (3-Zone: Inputs | Bill Sub-Ledger | Monthly Progression)
          * 6.2: System Hardware & Operating Costs (Solar, Battery, Generator & Avoided Grid Credit)
          * 6.3: Executive Summary & 15-Year Projection (8 KPIs, Component Matrix, Charts, 15Y Ledger)
    """
    cur_sys: CombinedSystemConfig = st.session_state["comb_system_cfg"]
    cur_fin: CombinedFinancialConfig = st.session_state["comb_fin_cfg"]
    is_fin_active = bool(cur_sys.enable_financials)

    if not is_fin_active:
        with st.container(border=True):
            f_col1, f_col2 = st.columns([2.5, 1.2])
            with f_col1:
                st.markdown(
                    "**Financials is currently paused for maximum simulation speed.** "
                    "Click **Activate Financials** to run the 4-Pillar Tariff billing, component investment breakdown, "
                    "monthly progression charts, and 15-year cashflow analysis."
                )
            with f_col2:
                st.button(
                    "Activate Financials",
                    icon=":material/power_settings_new:",
                    type="primary",
                    use_container_width=True,
                    key="comb_btn_activate_financials",
                    on_click=_activate_module_callback,
                    args=("comb_enable_financials_toggle",),
                )
        return

    if sim_res.financial_kpis is None:
        evaluate_combined_financials(sim_res, cur_fin)

    # Top: Live Master Cost & Savings Equation Bar
    st.markdown(_render_master_cost_equation_bar(sim_res), unsafe_allow_html=True)

    # 3 Structured Financial Inner Sub-Tabs
    fin_tabs = st.tabs([
        ":material/receipt_long: 1. Electricity Bill",
        ":material/precision_manufacturing: 2. Hardware & Running Costs",
        ":material/analytics: 3. 15-Year Overview",
    ])

    with fin_tabs[0]:
        _render_subtab6_1_grid_tariffs(sim_res, cur_sys, cur_fin)

    with fin_tabs[1]:
        _render_subtab6_2_hardware_costs(sim_res, cur_sys, cur_fin)

    with fin_tabs[2]:
        _render_subtab6_3_executive_overview(sim_res, cur_sys, cur_fin)


# ======================================================================================
# LEVEL 3: Permanent Master Output (Always Visible Below Sub-Tabs)
# ======================================================================================

@st.fragment
def _render_excel_export_fragment(sim_res) -> None:
    """Renders the on-demand Excel export button without blocking normal simulation reruns."""
    if "comb_cached_excel_bytes" not in st.session_state:
        if st.button(
            "Prepare Excel (.xlsx)",
            icon=":material/table_view:",
            use_container_width=True,
            key="comb_btn_prep_excel",
        ):
            st.session_state["comb_cached_excel_bytes"] = build_combined_verification_excel_bytes(sim_res)

    if "comb_cached_excel_bytes" in st.session_state:
        st.download_button(
            label="Download Excel (.xlsx)",
            data=st.session_state["comb_cached_excel_bytes"],
            file_name="Combined_System_Verification.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            icon=":material/download:",
            use_container_width=True,
            type="primary",
            key="comb_btn_dl_excel",
        )


@st.fragment
def _render_master_dispatch_chart_fragment(sim_res) -> None:
    """Renders the 15-minute dispatch chart matching the BESS Sandbox standard."""
    kpis = getattr(sim_res, "kpis", None)
    if kpis is not None:
        unmet_kwh = float(getattr(kpis, "remaining_overload_kwh", 0.0))
        unmet_hours = float(getattr(kpis, "remaining_overload_hours", 0.0))
    elif hasattr(sim_res, "unmet_overload_kw") and sim_res.unmet_overload_kw is not None:
        unmet_kwh = float(np.sum(sim_res.unmet_overload_kw) * 0.25)
        unmet_hours = float(np.sum(sim_res.unmet_overload_kw > 0.05) * 0.25)
    else:
        unmet_kwh = 0.0
        unmet_hours = 0.0

    has_unmet = (unmet_kwh > 0.05 or unmet_hours > 0.05)
    cfg = getattr(sim_res, "system_config", None)
    has_active_system = (
        cfg is not None
        and (cfg.enable_solar or cfg.enable_battery or cfg.enable_generator)
    )

    live_min_soc: Optional[float] = None
    if cfg is not None and cfg.enable_battery and getattr(sim_res, "bess_soc_pct", None) is not None:
        gaps = getattr(sim_res, "is_gap", None)
        soc_arr = np.asarray(sim_res.bess_soc_pct, dtype=float)
        valid_soc = (
            soc_arr[~np.asarray(gaps, dtype=bool)]
            if gaps is not None and len(gaps) == len(soc_arr)
            else soc_arr
        )
        if valid_soc.size > 0:
            live_min_soc = float(np.min(valid_soc))

    if has_active_system and not has_unmet:
        st.success(
            "**:material/check_circle: Grid Limit Met (Zero Overload)**\n\n"
            "Your system covers all demand peaks above the Grid Limit."
        )
        if (
            cfg is not None
            and cfg.enable_battery
            and live_min_soc is not None
            and live_min_soc > max(50.0, float(cfg.min_soc_pct) + 35.0)
        ):
            cycles_yr = float(getattr(kpis, "battery_equivalent_cycles", 0.0)) if kpis is not None else 0.0
            st.info(
                f"**:material/compress: Battery Utilization Notice (Min SoC {live_min_soc:.1f}% | {cycles_yr:.1f} cyc/yr)**\n\n"
                "Your battery stays above 50% SoC all year. Visit **5. System Mix & Rules** to test a compact "
                "Battery + Generator mix for higher storage utilization."
            )
    elif has_active_system and has_unmet:
        reason_hint = "Some peaks still exceed the Grid Limit. Increase battery or generator size if needed."
        dual_bess_cached = st.session_state.get("comb_cached_dual_bess")
        if cfg is not None and cfg.enable_battery:
            req_kw_hint = (
                float(dual_bess_cached.coupled_100_kw)
                if dual_bess_cached is not None
                else float(getattr(kpis, "baseline_overload_kw", 0.0)) if kpis is not None else 0.0
            )
            if (
                req_kw_hint > float(cfg.battery_power_kw) + 0.5
                and live_min_soc is not None
                and live_min_soc > float(cfg.min_soc_pct) + 10.0
            ):
                reason_hint = (
                    f"**Inverter Power Bottleneck (`kW`):** Battery inverter is limited to "
                    f"**{cfg.battery_power_kw:,.1f} kW** while up to **{req_kw_hint:,.1f} kW** is needed "
                    f"(Min SoC remained {live_min_soc:.1f}%). Increase Inverter Power (`kW`) in **3. Battery**."
                )
            elif live_min_soc is not None and live_min_soc <= float(cfg.min_soc_pct) + 2.0:
                reason_hint = (
                    f"**Storage Capacity Depleted (`kWh`):** Battery emptied to SoC Min ({cfg.min_soc_pct:.0f}%) "
                    "during multi-hour / multi-day clusters. Increase Battery `kWh` or add a Generator in **5. System Mix & Rules**."
                )
        st.warning(
            f"**:material/warning: Remaining Overload ({unmet_kwh:,.0f} kWh across {unmet_hours:,.1f} hrs)**\n\n"
            f"{reason_hint}"
        )

    with st.container(border=True):
        hdr1, hdr2 = st.columns([3.5, 1.3])
        with hdr1:
            st.markdown("#### :material/monitoring: Power Flow & Battery Level")
            st.caption("Zoom or select a timeframe to inspect power flows and battery charge.")
        with hdr2:
            st.write("")
            _render_excel_export_fragment(sim_res)

        fig_master = create_combined_dispatch_soc_figure(sim_res=sim_res)
        st.plotly_chart(
            fig_master,
            use_container_width=True,
            config={
                "scrollZoom": False,
                "displayModeBar": "hover",
                "responsive": True,
            },
            key="comb_master_dispatch_chart",
        )


def render_level3_permanent_master_output(sim_res) -> None:
    """
    Renders Level 3 permanently below the sub-tabs so it stays visible across all tab switches:
      - 4 Compact Master KPIs
      - Synchronized 15-Minute Power Flow & Battery Level Chart (with 7D/1M/3M/All, Range-Slider & Excel Export)
      - Compact System Comparison Table (Active Components vs. Current situation)
    """
    kpis = sim_res.kpis
    cfg = sim_res.system_config
    fin_kpis = sim_res.financial_kpis

    st.markdown("---")
    st.markdown("#### :material/monitoring: Simulation Results")

    # 1. 4 Compact Master KPIs
    mk1, mk2, mk3, mk4 = st.columns(4)
    with mk1:
        limit_status = (
            f"Grid Limit ({kpis.grid_limit_kw:,.0f} kW) Met"
            if kpis.grid_limit_met
            else f"Exceeds Limit by {kpis.remaining_overload_kw:,.1f} kW"
        )
        render_kpi_card(
            title="Grid Peak Demand",
            value=f"{kpis.original_peak_kw:,.1f} → {kpis.new_grid_peak_kw:,.1f} kW",
            subtext=f"{limit_status} (-{kpis.peak_reduction_kw:,.1f} kW shaved)",
            status="ok" if kpis.grid_limit_met else "alert",
        )

    with mk2:
        render_kpi_card(
            title="Remaining Overload",
            value=f"{kpis.remaining_overload_hours:,.1f} hrs | {kpis.remaining_overload_kwh:,.0f} kWh",
            subtext=(
                f"0.0 hrs remaining (Before: {kpis.baseline_overload_hours:,.1f} hrs)"
                if kpis.remaining_overload_hours == 0.0
                else f"{kpis.overload_eliminated_pct:.1f}% of {kpis.baseline_overload_hours:,.1f} hrs eliminated"
            ),
            status="ok" if kpis.remaining_overload_hours == 0.0 else "alert",
        )

    with mk3:
        render_kpi_card(
            title="Energy Supply Split",
            value=(
                f"Grid {kpis.grid_supply_share_pct:.0f}% | "
                f"Solar {kpis.solar_direct_share_pct:.0f}% | "
                f"Bat {kpis.battery_discharge_share_pct:.0f}% | "
                f"Gen {kpis.generator_supply_share_pct:.0f}%"
            ),
            subtext=f"Annual Consumption: {kpis.annual_consumption_kwh:,.0f} kWh",
            status="default",
        )

    with mk4:
        if cfg.enable_financials and fin_kpis is not None:
            pb_txt = f"{fin_kpis.payback_years:.1f} yrs" if fin_kpis.payback_years is not None else "N/A"
            render_kpi_card(
                title="System Operation & Financials",
                value=f"€{fin_kpis.annual_savings_eur:,.0f}/yr | {pb_txt}",
                subtext=(
                    f"BESS: {kpis.battery_equivalent_cycles:.1f} cyc | "
                    f"Gen: {kpis.generator_runtime_hours:,.1f} hrs ({kpis.generator_fuel_total:,.0f} {kpis.generator_fuel_unit})"
                ),
                status="ok" if fin_kpis.annual_savings_eur > 0 else "default",
            )
        else:
            render_kpi_card(
                title="System Operation",
                value=f"{kpis.battery_equivalent_cycles:.1f} cyc | {kpis.generator_runtime_hours:,.1f} hrs",
                subtext=(
                    f"Gen Fuel: {kpis.generator_fuel_total:,.0f} {kpis.generator_fuel_unit} "
                    f"({kpis.generator_starts_count} starts/yr)"
                ),
                status="default",
            )

    # 2. Shared Synchronized 15-Minute Master Chart (isolated in fragment)
    _render_master_dispatch_chart_fragment(sim_res=sim_res)

    # 3. Compact System Comparison Table
    with st.container(border=True):
        st.markdown("##### :material/table_chart: System Comparison")
        if cfg.enable_financials and not sim_res.financial_table_df.empty:
            st.dataframe(
                sim_res.financial_table_df,
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.dataframe(
                sim_res.summary_table_df,
                use_container_width=True,
                hide_index=True,
            )


def main() -> None:
    st.set_page_config(
        page_title="Combined System",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    apply_custom_styles()
    _init_session_defaults()

    st.markdown("### :material/hub: Combined System")
    st.caption("Grid + Solar + Battery + Generator")

    load_series, load_label = _get_active_load_series()

    # LEVEL 1: System Overview Bar (Top)
    render_level1_overview_bar(load_series, load_label)

    # LEVEL 2: 6 Modular Sub-Tabs (Middle)
    subtabs = st.tabs(
        [
            ":material/analytics: 1. Consumption",
            ":material/solar_power: 2. Solar",
            ":material/battery_charging_full: 3. Battery",
            ":material/power: 4. Generator",
            ":material/tune: 5. System Mix & Rules",
            ":material/payments: 6. Financials",
        ]
    )

    with subtabs[0]:
        render_subtab1_consumption(load_series)

    # Refresh load_series if changed inside Subtab 1
    load_series, load_label = _get_active_load_series()

    with subtabs[1]:
        render_subtab2_solar(load_series)

    with subtabs[2]:
        render_subtab3_battery(load_series)

    with subtabs[3]:
        render_subtab4_generator(load_series)

    with subtabs[4]:
        render_subtab5_interaction_rules(load_series)

    # Run fast physical 15-minute simulation only when physical fingerprint changes
    cur_sys: CombinedSystemConfig = st.session_state["comb_system_cfg"]
    cur_rules: InteractionRulesConfig = st.session_state["comb_rules_cfg"]
    dispatch_fp = (
        _load_fingerprint(load_series),
        _physical_sys_tuple(cur_sys),
        _rules_tuple(cur_rules),
    )
    if (
        st.session_state.get("comb_dispatch_fp") != dispatch_fp
        or "comb_sandbox_result" not in st.session_state
    ):
        sim_res = simulate_combined_system_dispatch(
            load_kw=load_series.power_kw,
            timestamps=load_series.timestamps,
            system_cfg=cur_sys,
            rules_cfg=cur_rules,
            is_gap=getattr(load_series, "is_gap", None),
        )
        if "comb_latest_bottleneck_df" in st.session_state:
            sim_res.bess_bottleneck_df = st.session_state["comb_latest_bottleneck_df"]
        st.session_state["comb_sandbox_result"] = sim_res
        st.session_state["comb_dispatch_fp"] = dispatch_fp
        st.session_state.pop("comb_cached_excel_bytes", None)
    else:
        sim_res = st.session_state["comb_sandbox_result"]
        sim_res.system_config.enable_financials = bool(cur_sys.enable_financials)
        if "comb_latest_bottleneck_df" in st.session_state:
            sim_res.bess_bottleneck_df = st.session_state["comb_latest_bottleneck_df"]

    with subtabs[5]:
        render_subtab6_financials(sim_res)

    # LEVEL 3: Permanent Master Output (Bottom — outside subtabs so always visible)
    render_level3_permanent_master_output(sim_res)


if __name__ == "__main__":
    main()
