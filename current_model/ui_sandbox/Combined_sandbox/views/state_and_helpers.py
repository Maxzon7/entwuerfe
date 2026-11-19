"""
Shared external imports, Streamlit session state defaults, fingerprint builders,
module activation callbacks, and quick-sizing helpers for Combined System Sandbox.
"""

import copy
import importlib
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

_VIEWS_DIR = os.path.abspath(os.path.dirname(__file__))
_CURRENT_DIR = os.path.abspath(os.path.join(_VIEWS_DIR, ".."))
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

from .. import combined_sandbox_engine as _engine_mod
if getattr(_engine_mod, "ENGINE_VERSION", None) != "13.7":
    for _m in list(sys.modules.keys()):
        if "Combined_sandbox.engine" in _m or "Combined_sandbox.combined_sandbox_engine" in _m:
            del sys.modules[_m]
from ..combined_sandbox_engine import (
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
    CombinedSimulationResult,
    DualBatterySizingResult,
    DualGeneratorSizingResult,
    CoordinatedMixRecommendation,
    SystemUtilizationDiagnostics,
    CombinedScenarioSnapshot,
    get_unit_solar_generation_profile,
    derive_solar_sizing_and_formula,
    compute_standalone_solar_production_summary,
    determine_smart_modular_units,
    compute_dual_battery_sizing,
    refresh_bottleneck_table_configured_status,
    compute_dual_generator_sizing,
    compute_coordinated_mix_sizing,
    simulate_combined_system_dispatch,
    compute_system_utilization_diagnostics,
    extract_bess_phase_events,
    summarize_bess_window_energy,
    evaluate_combined_financials,
    get_dso_preset_options,
    get_supplier_preset_options,
    get_metering_preset_options,
    apply_utility_tariff_presets,
    sync_financial_config_from_status_quo,
    scale_eur_hardware_defaults_to_currency,
    format_currency_value,
    build_baseline_tariff_fingerprint,
    capture_scenario_snapshot,
    recalculate_snapshot_on_active_load,
    generate_quick_ab_preset_snapshots,
    build_restore_widget_sync_payload,
    build_ab_comparison_matrix_df,
    SCENARIO_COMPARISON_PALETTE,
    normalize_scenario_list,
    build_multi_scenario_leaderboard_df,
    compute_snapshot_bwl_extensions,
    compute_incremental_bwl_evaluation,
    build_segmented_comparison_tables,
    snapshot_to_sim_view,
)
from ..combined_charts import (
    DEFAULT_POWERFLOW_COLORS,
    create_consumption_baseline_figure,
    create_combined_dispatch_soc_figure,
    create_solar_production_figure,
    create_financial_cost_comparison_figure,
    create_financial_tco_trajectory_figure,
    create_financial_waterfall_bridge_figure,
    create_financial_monthly_cashflow_figure,
    create_monthly_grid_bill_progression_figure,
    create_dso_isolated_breakdown_figure,
    create_supplier_isolated_breakdown_figure,
    create_tax_isolated_breakdown_figure,
    create_solar_isolated_financial_figure,
    create_battery_isolated_financial_figure,
    create_generator_isolated_financial_figure,
    create_supply_mix_pie_figure,
    create_component_utilization_bars_figure,
    create_ab_15y_tco_comparison_figure,
    create_ab_annual_cost_stack_figure,
    create_ab_supply_and_utilization_figure,
    create_ab_monthly_peak_and_grid_import_figure,
    create_ab_energy_flow_balance_figure,
    create_ab_capex_vs_opex_shift_figure,
    create_ab_load_profile_overlay_figure,
    sync_side_by_side_yaxis,
)
from ..combined_excel_exporter import (
    build_combined_verification_excel_bytes,
)
from ..pdf_report import (
    PdfReportOptions,
    build_combined_system_pdf_bytes,
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
    if "comb_saved_scenarios" not in st.session_state:
        st.session_state["comb_saved_scenarios"] = {}

    for _pending_key in (
        "comb_pending_mix_widget_sync",
        "comb_pending_solar_widget_sync",
        "comb_pending_fin_widget_sync",
    ):
        pending_sync = st.session_state.pop(_pending_key, None)
        if isinstance(pending_sync, dict):
            for sk, sv in pending_sync.items():
                st.session_state[sk] = sv

    defaults = {
        "tab1_active_source": "csv",
        "comb_allow_empty_baseline": True,
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
        "comb_bess_include_gen": False,
        "comb_bess_include_gen_toggle_b3": False,
        "comb_bess_include_gen_radio_b1": "Without Generator (Default)",
        "comb_gen_sizing_mode": "Coupled (With active Solar / Battery & Rules)",
        "comb_mix_strategy_key": "hybrid_2h",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _create_empty_load_series_2025() -> LoadSeries2025:
    """Returns a valid 35,040-step all-zero 2025 LoadSeries2025 for a clean zero-start baseline."""
    ts = pd.date_range("2025-01-01 00:00:00", "2025-12-31 23:45:00", freq="15min")
    n = len(ts)
    zeros = np.zeros(n, dtype=float)
    is_peak = np.asarray((ts.dayofweek < 5) & (ts.hour >= 7) & (ts.hour < 23), dtype=bool)
    return LoadSeries2025(
        timestamps=ts,
        power_kw=zeros,
        energy_kwh=zeros,
        month_indices=ts.month.to_numpy(dtype=np.intp),
        is_peak_tou=is_peak,
    )


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

    empty_series = _create_empty_load_series_2025()
    st.session_state["comb_active_load_series"] = empty_series
    st.session_state["comb_active_load_label"] = "No Profile Loaded (0 kWh)"
    return empty_series, "No Profile Loaded (0 kWh)"


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
        bool(getattr(sys_cfg, "disable_solar_inverter_limit", False)),
        round(float(sys_cfg.inverter_efficiency_pct), 2),
        str(getattr(sys_cfg, "solar_weather_mode", "single_year")),
        int(getattr(sys_cfg, "solar_weather_year", 2025)),
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
        st.session_state.pop("comb_cached_dual_bess_pair", None)
        st.session_state.pop("comb_gen_sizing_fp", None)
        st.session_state.pop("comb_cached_dual_gen", None)
        st.session_state.pop("comb_mix_preview_bundle", None)
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


def compute_synced_solar_pair(
    sizing_method: str,
    direct_kwp: float,
    target_share_pct: float,
    annual_consumption_kwh: float,
    specific_yield_kwh_per_kwp: float,
    inverter_efficiency_pct: float = 98.0,
) -> Tuple[float, float]:
    """
    Synchronizes `(solar_kwp, target_share_pct)` two-way based on the active sizing mode:
      - `target_share_pct` -> computes matching `solar_kwp`
      - `direct_kwp` -> computes matching `target_share_pct`
    """
    spec_y = max(100.0, float(specific_yield_kwh_per_kwp))
    ann_load = max(0.0, float(annual_consumption_kwh))
    eff_factor = float(np.clip(inverter_efficiency_pct, 80.0, 100.0)) / 98.0
    if sizing_method == "target_share_pct":
        share = max(0.1, float(target_share_pct))
        kwp = round(max(1.0, (ann_load * (share / 100.0)) / spec_y), 1) if ann_load > 0.0 else round(max(1.0, float(direct_kwp)), 1)
        return kwp, round(share, 1)
    kwp = round(max(1.0, float(direct_kwp)), 1)
    if ann_load > 0.0:
        share = round(min(1000.0, max(0.1, (kwp * spec_y * eff_factor / ann_load) * 100.0)), 1)
    else:
        share = round(max(0.1, float(target_share_pct)), 1)
    return kwp, share


def _apply_solar_quick_share(share_pct: float) -> None:
    """Callback for Solar quick share buttons (20%, 40%, 60%, 100%)."""
    cfg: CombinedSystemConfig = st.session_state["comb_system_cfg"]
    cfg.solar_sizing_method = "target_share_pct"
    cfg.target_consumption_share_pct = float(share_pct)
    cfg.inverter_ac_limit_kw = 0.0
    load_series: Optional[LoadSeries2025] = st.session_state.get("comb_active_load_series")
    ann_kwh = float(load_series.total_energy_kwh) if load_series is not None else 0.0
    eff_lat = float(st.session_state.get("comb_solar_lat", cfg.latitude))
    eff_lon = float(st.session_state.get("comb_solar_lon", cfg.longitude))
    _, spec_yield, _ = get_unit_solar_generation_profile(
        latitude=eff_lat,
        longitude=eff_lon,
        tilt_deg=float(cfg.tilt_deg),
        azimuth_deg=180.0 if eff_lat >= 0.0 else 0.0,
        dc_ac_ratio=float(cfg.dc_ac_ratio),
        weather_mode=str(getattr(cfg, "solar_weather_mode", "single_year")),
        selected_year=int(getattr(cfg, "solar_weather_year", 2025)),
    )
    synced_kwp, synced_share = compute_synced_solar_pair(
        sizing_method="target_share_pct",
        direct_kwp=float(cfg.solar_kwp),
        target_share_pct=float(share_pct),
        annual_consumption_kwh=ann_kwh,
        specific_yield_kwh_per_kwp=spec_yield,
        inverter_efficiency_pct=float(cfg.inverter_efficiency_pct),
    )
    cfg.solar_kwp = float(synced_kwp)
    st.session_state["comb_solar_sizing_radio"] = "% of Annual Consumption"
    st.session_state["comb_solar_target_share_num"] = float(synced_share)
    st.session_state["comb_solar_direct_kwp_num"] = float(synced_kwp)
    st.session_state["comb_solar_inv_ac_limit_num"] = 0.0
    st.session_state.pop("comb_cached_excel_bytes", None)


def _apply_bess_quick_size(cap_kwh: float, p_kw: float) -> None:
    """Callback for Battery Dual-Sizing quick buttons (100%, 80%, 50%)."""
    cfg: CombinedSystemConfig = st.session_state["comb_system_cfg"]
    cfg.battery_capacity_kwh = max(10.0, float(cap_kwh))
    cfg.battery_power_kw = max(5.0, float(p_kw))
    units, unit_kwh = determine_smart_modular_units(cfg.battery_capacity_kwh)
    st.session_state["comb_bess_lock_05c"] = False
    st.session_state["comb_bess_lock_05c_box"] = False
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
