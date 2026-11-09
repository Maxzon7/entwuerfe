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

import math
import os
import sys
from typing import Tuple, List, Optional
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
    )
    from ui_sandbox.Currentsituation_sandbox.consumption.view import render_tab1_consumption
except ImportError:
    from current_model.ui_sandbox.Currentsituation_sandbox.engine.config_and_models import LoadSeries2025
    from current_model.ui_sandbox.Currentsituation_sandbox.engine.consumption_pipeline import (
        normalize_load_profile_2025,
        synthesize_benchmark_load_profile_2025,
    )
    from current_model.ui_sandbox.Currentsituation_sandbox.consumption.view import render_tab1_consumption

try:
    from ui_sandbox.Combined_sandbox.combined_sandbox_engine import (
        SOLAR_SITE_PRESETS,
        FUEL_SPECS,
        RULE1_OPTIONS,
        RULE2_OPTIONS,
        RULE3_OPTIONS,
        CombinedSystemConfig,
        InteractionRulesConfig,
        CombinedFinancialConfig,
        get_unit_solar_generation_profile,
        derive_solar_sizing_and_formula,
        compute_dual_battery_sizing,
        refresh_bottleneck_table_configured_status,
        compute_dual_generator_sizing,
        simulate_combined_system_dispatch,
        evaluate_combined_financials,
    )
except (ImportError, AttributeError):
    for _m in list(sys.modules.keys()):
        if "Combined_sandbox" in _m:
            del sys.modules[_m]
    from ui_sandbox.Combined_sandbox.combined_sandbox_engine import (
        SOLAR_SITE_PRESETS,
        FUEL_SPECS,
        RULE1_OPTIONS,
        RULE2_OPTIONS,
        RULE3_OPTIONS,
        CombinedSystemConfig,
        InteractionRulesConfig,
        CombinedFinancialConfig,
        get_unit_solar_generation_profile,
        derive_solar_sizing_and_formula,
        compute_dual_battery_sizing,
        refresh_bottleneck_table_configured_status,
        compute_dual_generator_sizing,
        simulate_combined_system_dispatch,
        evaluate_combined_financials,
    )

from ui_sandbox.Combined_sandbox.combined_charts import (
    create_consumption_baseline_figure,
    create_combined_dispatch_soc_figure,
    create_financial_cost_comparison_figure,
)
from ui_sandbox.Combined_sandbox.combined_excel_exporter import (
    build_combined_verification_excel_bytes,
)


def _init_session_defaults() -> None:
    """Initializes default session state values (all add-on modules start deactivated)."""
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
    """Invalidates cached simulation outputs when the underlying load profile changes."""
    load_series, _ = _get_active_load_series()
    fingerprint = _load_fingerprint(load_series)
    if st.session_state.get("comb_load_fingerprint") != fingerprint:
        st.session_state["comb_load_fingerprint"] = fingerprint
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
    st.session_state["comb_battery_capacity_kwh_num"] = cfg.battery_capacity_kwh
    st.session_state["comb_battery_power_kw_num"] = cfg.battery_power_kw
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
                grid_limit_val = st.number_input(
                    "Grid Limit (kW)",
                    min_value=10.0,
                    max_value=20000.0,
                    value=float(cur_sys.grid_limit_kw),
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

def render_subtab1_consumption(load_series: LoadSeries2025) -> None:
    """
    Renders Subtab 1: Consumption (CSV upload as default, benchmark switcher, and 4 Base KPIs).
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

    st.write("")
    render_tab1_consumption(key_prefix="comb_tab1_cons")
    _sync_shared_load_series()


# ======================================================================================
# LEVEL 2 — SUBTAB 2: Solar (Grayed Out Until Activated)
# ======================================================================================

def render_subtab2_solar(load_series: LoadSeries2025) -> None:
    """
    Renders Subtab 2: Solar
      - 1-Click Activate button if inactive
      - Location (City search & Presets, Default: Amsterdam) + EU PVGIS source line
      - Dual Quick-Sizing (% of Annual Consumption: 20/40/60/100% vs. Direct Size kWp)
      - Blue live formula box
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
        st.markdown("##### :material/solar_power: Solar Configuration")

        # 1. Location: City Search & Presets (Default: Amsterdam)
        with st.form("comb_solar_location_form"):
            loc_c1, loc_c2, loc_btn = st.columns([1.5, 1.5, 0.9])
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
            with loc_btn:
                st.write("")
                loc_submitted = st.form_submit_button(
                    "Apply Location",
                    use_container_width=True,
                    disabled=not is_active,
                )

        if loc_submitted:
            if search_query and len(search_query.strip()) >= 2 and search_query.strip() != st.session_state.get("comb_solar_site_name", ""):
                search_results = search_locations_open_meteo(search_query.strip(), count=1)
                if search_results:
                    chosen = search_results[0]
                    st.session_state["comb_solar_lat"] = float(chosen["lat"])
                    st.session_state["comb_solar_lon"] = float(chosen["lon"])
                    st.session_state["comb_solar_site_name"] = chosen["display_name"]
                    st.session_state["comb_solar_preset_choice"] = "Custom GPS Coordinates"
            elif preset_choice in SOLAR_SITE_PRESETS:
                p_data = SOLAR_SITE_PRESETS[preset_choice]
                st.session_state["comb_solar_lat"] = float(p_data["latitude"])
                st.session_state["comb_solar_lon"] = float(p_data["longitude"])
                st.session_state["comb_solar_site_name"] = p_data["name"]
                st.session_state["comb_solar_preset_choice"] = preset_choice
            st.session_state.pop("comb_cached_excel_bytes", None)

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
            f"Data source: **EU PVGIS (ERA5 15-min TMY)** | Location: **{site_disp}** | "
            f"Specific Yield: **{spec_yield:,.0f} kWh/kWp/year**"
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
            sz_m1, sz_m2 = st.columns([1.5, 2.5])
            with sz_m1:
                sizing_mode_label = st.radio(
                    "Sizing Mode",
                    options=["% of Annual Consumption", "Direct Size (kWp)"],
                    index=0 if cur_sys.solar_sizing_method == "target_share_pct" else 1,
                    horizontal=True,
                    disabled=not is_active,
                    key="comb_solar_sizing_radio",
                )
            with sz_m2:
                st.caption(
                    "Select '% of Annual Consumption' to auto-size Solar from energy share, "
                    "or 'Direct Size (kWp)' to specify exact installed capacity."
                )

            in_c1, in_c2, in_c3, in_c4, in_btn = st.columns([1.1, 1.1, 1.1, 1.1, 0.9])
            with in_c1:
                target_share_val = st.number_input(
                    "Share of Consumption (%)",
                    min_value=5.0,
                    max_value=250.0,
                    value=float(cur_sys.target_consumption_share_pct),
                    step=5.0,
                    disabled=not is_active,
                    key="comb_solar_target_share_num",
                )
            with in_c2:
                direct_kwp_val = st.number_input(
                    "Direct Size (kWp)",
                    min_value=1.0,
                    max_value=25000.0,
                    value=float(cur_sys.solar_kwp),
                    step=10.0,
                    disabled=not is_active,
                    key="comb_solar_direct_kwp_num",
                )
            with in_c3:
                inv_ac_limit_val = st.number_input(
                    "Inverter AC Limit (kW)",
                    min_value=0.0,
                    max_value=25000.0,
                    value=max(0.0, default_inv_kw),
                    step=10.0,
                    disabled=not is_active,
                    key="comb_solar_inv_ac_limit_num",
                )
            with in_c4:
                inv_eff_val = st.number_input(
                    "Inverter Efficiency (%)",
                    min_value=80.0,
                    max_value=100.0,
                    value=float(cur_sys.inverter_efficiency_pct),
                    step=0.5,
                    disabled=not is_active,
                    key="comb_solar_inv_eff_num",
                )
            with in_btn:
                st.write("")
                sol_submitted = st.form_submit_button(
                    "Apply Solar Settings",
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


# ======================================================================================
# LEVEL 2 — SUBTAB 3: Battery (Dual-Sizing & 4-Bottleneck Diagnostic Table)
# ======================================================================================

def render_subtab3_battery(load_series: LoadSeries2025) -> None:
    """
    Renders Subtab 3: Battery
      - 1-Click Activate button if inactive
      - 1. Dual Sizing System (Mode A: Standalone vs. Mode B: Coupled) with 100%, 80%, 50% quick buttons
      - Manual inputs: Battery Capacity (kWh) & Battery Power (kW)
      - 2. 4-Criterion Bottleneck Diagnostic Table
      - 3. Core technical parameters: Min SoC (%), Max SoC (%), Round-Trip Efficiency (%)
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
        )
        st.session_state["comb_bess_sizing_fp"] = bess_sizing_fp

    dual_bess = st.session_state["comb_cached_dual_bess"]

    with st.container(border=True):
        st.markdown("##### :material/battery_charging_full: 1. Dual Quick-Sizing & Manual Configuration")

        mode_c1, mode_c2 = st.columns([1.6, 1.8])
        with mode_c1:
            bess_mode = st.radio(
                "Quick-Sizing Mode",
                options=[
                    "Mode A – Standalone (Battery only)",
                    "Mode B – Coupled (With active Solar / Generator & Rules)",
                ],
                index=1,
                disabled=not is_active,
                key="comb_bess_sizing_mode_radio",
            )
            is_standalone = bess_mode.startswith("Mode A")

            if is_standalone:
                q100_kwh, q100_kw = dual_bess.standalone_100_kwh, dual_bess.standalone_100_kw
                q80_kwh, q80_kw = dual_bess.standalone_80_kwh, dual_bess.standalone_80_kw
                q50_kwh, q50_kw = dual_bess.standalone_50_kwh, dual_bess.standalone_50_kw
            else:
                q100_kwh, q100_kw = dual_bess.coupled_100_kwh, dual_bess.coupled_100_kw
                q80_kwh, q80_kw = dual_bess.coupled_80_kwh, dual_bess.coupled_80_kw
                q50_kwh, q50_kw = dual_bess.coupled_50_kwh, dual_bess.coupled_50_kw

        with mode_c2:
            st.caption(
                f"Apply Quick Size ({'Standalone: Battery alone' if is_standalone else 'Coupled: With active Solar/Generator'}):"
            )
            bq1, bq2, bq3 = st.columns(3)
            bq1.button(
                f"100% Zero-Overload ({q100_kwh:,.0f} kWh)",
                use_container_width=True,
                disabled=not is_active,
                key="comb_bess_q100",
                on_click=_apply_bess_quick_size,
                args=(q100_kwh, q100_kw),
            )
            bq2.button(
                f"80% ({q80_kwh:,.0f} kWh)",
                use_container_width=True,
                disabled=not is_active,
                key="comb_bess_q80",
                on_click=_apply_bess_quick_size,
                args=(q80_kwh, q80_kw),
            )
            bq3.button(
                f"50% ({q50_kwh:,.0f} kWh)",
                use_container_width=True,
                disabled=not is_active,
                key="comb_bess_q50",
                on_click=_apply_bess_quick_size,
                args=(q50_kwh, q50_kw),
            )
            st.caption(
                f"100% Reference — **Standalone:** {dual_bess.standalone_100_kwh:,.0f} kWh / {dual_bess.standalone_100_kw:,.1f} kW | "
                f"**Coupled:** {dual_bess.coupled_100_kwh:,.0f} kWh / {dual_bess.coupled_100_kw:,.1f} kW"
            )

        # Manual Override & Core Technical Parameters (encapsulated in st.form)
        with st.form("comb_battery_form"):
            bc1, bc2, bc3, bc4, bc5, bc_btn = st.columns([1.15, 1.15, 0.85, 0.85, 0.95, 0.95])
            with bc1:
                bess_kwh = st.number_input(
                    "Battery Capacity (kWh)",
                    min_value=10.0,
                    max_value=50000.0,
                    value=float(cur_sys.battery_capacity_kwh),
                    step=25.0,
                    disabled=not is_active,
                    key="comb_battery_capacity_kwh_num",
                )
            with bc2:
                bess_kw = st.number_input(
                    "Battery Power (kW)",
                    min_value=5.0,
                    max_value=25000.0,
                    value=float(cur_sys.battery_power_kw),
                    step=10.0,
                    disabled=not is_active,
                    key="comb_battery_power_kw_num",
                )
            with bc3:
                min_soc = st.number_input(
                    "Min SoC (%)",
                    min_value=0.0,
                    max_value=50.0,
                    value=float(cur_sys.min_soc_pct),
                    step=5.0,
                    disabled=not is_active,
                    key="comb_battery_min_soc_num",
                )
            with bc4:
                max_soc = st.number_input(
                    "Max SoC (%)",
                    min_value=55.0,
                    max_value=100.0,
                    value=float(cur_sys.max_soc_pct),
                    step=5.0,
                    disabled=not is_active,
                    key="comb_battery_max_soc_num",
                )
            with bc5:
                rte_pct = st.number_input(
                    "Round-Trip Efficiency (%)",
                    min_value=60.0,
                    max_value=100.0,
                    value=float(cur_sys.round_trip_efficiency_pct),
                    step=1.0,
                    disabled=not is_active,
                    key="comb_battery_rte_num",
                )
            with bc_btn:
                st.write("")
                bess_submitted = st.form_submit_button(
                    "Apply Battery Settings",
                    use_container_width=True,
                    disabled=not is_active,
                )

        if bess_submitted:
            so_c_changed = (
                abs(cur_sys.min_soc_pct - float(min_soc)) > 1e-4
                or abs(cur_sys.max_soc_pct - float(max_soc)) > 1e-4
                or abs(cur_sys.round_trip_efficiency_pct - float(rte_pct)) > 1e-4
            )
            cur_sys.battery_capacity_kwh = float(bess_kwh)
            cur_sys.battery_power_kw = float(bess_kw)
            cur_sys.min_soc_pct = float(min_soc)
            cur_sys.max_soc_pct = float(max_soc)
            cur_sys.round_trip_efficiency_pct = float(rte_pct)
            if so_c_changed:
                dual_bess = compute_dual_battery_sizing(
                    load_kw=load_series.power_kw,
                    system_cfg=cur_sys,
                    rules_cfg=cur_rules,
                )
                st.session_state["comb_cached_dual_bess"] = dual_bess
            st.session_state.pop("comb_cached_excel_bytes", None)

        # Lightweight O(1) update of 'Configured Battery' & 'Status' columns (no 35,040-step re-run!)
        bottleneck_df = refresh_bottleneck_table_configured_status(
            dual_bess=dual_bess,
            configured_kwh=cur_sys.battery_capacity_kwh,
            configured_kw=cur_sys.battery_power_kw,
            enable_battery=is_active,
        )
        st.session_state["comb_latest_bottleneck_df"] = bottleneck_df

        st.markdown("---")
        st.markdown("##### :material/checklist: 2. 4-Criterion Bottleneck Diagnostic Table")
        st.caption(
            f"Shows which of the 4 physical limits determines the required battery size "
            f"(Primary driver: **{dual_bess.controlling_driver_coupled}**)."
        )
        st.dataframe(
            bottleneck_df,
            use_container_width=True,
            hide_index=True,
        )


# ======================================================================================
# LEVEL 2 — SUBTAB 4: Generator (With Dual-Sizing)
# ======================================================================================

def render_subtab4_generator(load_series: LoadSeries2025) -> None:
    """
    Renders Subtab 4: Generator
      - 1-Click Activate button if inactive
      - 1. Dual Sizing System (Mode A: Standalone vs. Mode B: Coupled) with 100%, 80%, 50% buttons
      - 2. Minimalist Core Inputs: Generator Power (kW), Minimum Load (%), Fuel Type
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
        )
        st.session_state["comb_gen_sizing_fp"] = gen_sizing_fp

    dual_gen = st.session_state["comb_cached_dual_gen"]

    with st.container(border=True):
        st.markdown("##### :material/power: 1. Dual Quick-Sizing & Generator Configuration")

        gm1, gm2 = st.columns([1.6, 1.8])
        with gm1:
            gen_mode = st.radio(
                "Generator Sizing Mode",
                options=[
                    "Mode A – Standalone (Generator only)",
                    "Mode B – Coupled (With active Solar / Battery & Rules)",
                ],
                index=1,
                disabled=not is_active,
                key="comb_gen_sizing_mode_radio",
            )
            is_gen_standalone = gen_mode.startswith("Mode A")
            if is_gen_standalone:
                g100, g80, g50 = dual_gen.standalone_100_kw, dual_gen.standalone_80_kw, dual_gen.standalone_50_kw
            else:
                g100, g80, g50 = dual_gen.coupled_100_kw, dual_gen.coupled_80_kw, dual_gen.coupled_50_kw

        with gm2:
            st.caption(
                f"Apply Quick Size ({'Standalone: Full Peak' if is_gen_standalone else 'Coupled: Remaining Peak after Solar/Battery'}):"
            )
            gq1, gq2, gq3 = st.columns(3)
            gq1.button(
                f"100% ({g100:,.1f} kW)",
                use_container_width=True,
                disabled=not is_active,
                key="comb_gen_q100",
                on_click=_apply_gen_quick_size,
                args=(g100,),
            )
            gq2.button(
                f"80% ({g80:,.1f} kW)",
                use_container_width=True,
                disabled=not is_active,
                key="comb_gen_q80",
                on_click=_apply_gen_quick_size,
                args=(g80,),
            )
            gq3.button(
                f"50% ({g50:,.1f} kW)",
                use_container_width=True,
                disabled=not is_active,
                key="comb_gen_q50",
                on_click=_apply_gen_quick_size,
                args=(g50,),
            )
            st.caption(
                f"100% Reference — **Standalone:** {dual_gen.standalone_100_kw:,.1f} kW | "
                f"**Coupled (Remaining Peak):** {dual_gen.coupled_100_kw:,.1f} kW"
            )

        with st.form("comb_generator_form"):
            gc1, gc2, gc3, gc_btn = st.columns([1.2, 1.3, 1.0, 0.9])
            with gc1:
                gen_kw_val = st.number_input(
                    "Generator Power (kW)",
                    min_value=10.0,
                    max_value=20000.0,
                    value=float(cur_sys.generator_rated_kw),
                    step=10.0,
                    disabled=not is_active,
                    key="comb_generator_rated_kw_num",
                )
            with gc2:
                gen_min_pct_val = st.number_input(
                    "Minimum Load (%) — Wet-Stacking Protection",
                    min_value=0.0,
                    max_value=80.0,
                    value=float(cur_sys.generator_min_load_pct),
                    step=5.0,
                    disabled=not is_active,
                    key="comb_generator_min_load_num",
                )
            with gc3:
                fuel_keys = list(FUEL_SPECS.keys())
                fuel_idx = fuel_keys.index(cur_sys.fuel_type) if cur_sys.fuel_type in fuel_keys else 0
                fuel_type_val = st.selectbox(
                    "Fuel Type",
                    options=fuel_keys,
                    index=fuel_idx,
                    disabled=not is_active,
                    key="comb_generator_fuel_type_select",
                )
            with gc_btn:
                st.write("")
                gen_submitted = st.form_submit_button(
                    "Apply Generator Settings",
                    use_container_width=True,
                    disabled=not is_active,
                )

        if gen_submitted:
            cur_sys.generator_rated_kw = float(gen_kw_val)
            cur_sys.generator_min_load_pct = float(gen_min_pct_val)
            cur_sys.fuel_type = str(fuel_type_val)
            st.session_state.pop("comb_cached_excel_bytes", None)


# ======================================================================================
# LEVEL 2 — SUBTAB 5: Interaction Rules
# ======================================================================================

def render_subtab5_interaction_rules() -> None:
    """
    Renders Subtab 5: Interaction Rules in simple, clear language:
      - Automatic Solar direct priority explanation
      - Rule 1: Peak Shaving Priority (Above Grid Limit)
      - Rule 2: Normal Load Coverage (Below Grid Limit)
      - Rule 3: Battery Charging Sources & Timing (Options A, B, C, D)
      - Encapsulated in st.form("comb_rules_form") to prevent intermediate 20s reruns while adjusting
    """
    cur_rules: InteractionRulesConfig = st.session_state["comb_rules_cfg"]

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
                st.markdown("##### :material/priority_high: Rule 1 – Peak Shaving Priority")
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
                st.markdown("##### :material/battery_saver: Rule 2 – Normal Load Coverage")
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
                    "Peak Reserve SoC (%) — when Self-Consumption is active",
                    min_value=10,
                    max_value=90,
                    value=int(np.clip(cur_rules.peak_reserve_soc_pct, 10, 90)),
                    step=5,
                    key="comb_rule2_reserve_slider",
                )
                st.caption(
                    "If Self-Consumption + Peak Reserve is active, extra solar energy shifts into evening load "
                    "while protecting this SoC % exclusively for peak shaving."
                )

            with r_c3:
                st.markdown("##### :material/bolt: Rule 3 – Battery Charging Sources")
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
        st.session_state.pop("comb_cached_excel_bytes", None)


# ======================================================================================
# LEVEL 2 — SUBTAB 6: Financials (Lazy-Loaded, 4-Pillar Tariff + Cost Comparison Chart)
# ======================================================================================

def render_subtab6_financials(sim_res) -> None:
    """
    Renders Subtab 6: Financials (Lazy-loaded for performance):
      - When inactive: Prominent 'Activate Financials' button; skips financial calculations
      - When active:
          * Block A: 4-Pillar Grid & Tariff Costs (Energy Supply, Grid Network DSO, Metering, Taxes)
          * Block B: Solar Turnkey CAPEX & O&M (shown if Solar is active)
          * Block C: Battery Turnkey CAPEX, O&M & Year-11 Augmentation (shown if Battery is active)
          * Block D: Generator Purchase vs. Rental & Fuel OPEX (shown if Generator is active)
          * Consolidated Financial Evaluation: 4 KPIs, Annual Cost Comparison Chart (With vs. Without System),
            and 15-Year Cashflow Table
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
                    "Click **Activate Financials** to run the 4-Pillar Tariff billing, investment costs, "
                    "cost comparison chart, and 15-year cashflow analysis."
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

    with st.form("comb_financials_form"):
        # --- Block A: 4-Pillar Grid & Tariff Costs (Always visible when Financials active) ---
        with st.container(border=True):
            st.markdown("##### :material/receipt_long: Block A – Grid & Tariff Costs (4-Pillar Tariff)")
            p1_col, p2_col, p3_col, p4_col = st.columns(4)

            with p1_col:
                st.markdown("**1. Energy Supply (Supplier)**")
                supp_kwh = st.number_input(
                    "Electricity Price (€/kWh)",
                    min_value=0.0,
                    max_value=2.0,
                    value=float(cur_fin.supplier_energy_price_eur_kwh),
                    step=0.01,
                    format="%.3f",
                    key="comb_fin_supp_kwh",
                )
                supp_fix = st.number_input(
                    "Supplier Standing Fee (€/month)",
                    min_value=0.0,
                    max_value=5000.0,
                    value=float(cur_fin.supplier_fixed_fee_eur_month),
                    step=10.0,
                    key="comb_fin_supp_fix",
                )

            with p2_col:
                st.markdown("**2. Grid Network (DSO)**")
                dso_cap = st.number_input(
                    "Contracted Capacity Fee (€/kW/mo)",
                    min_value=0.0,
                    max_value=100.0,
                    value=float(cur_fin.dso_capacity_fee_eur_kw_month),
                    step=0.5,
                    key="comb_fin_dso_cap",
                )
                dso_peak = st.number_input(
                    "Monthly Peak Demand Fee (€/kW/mo)",
                    min_value=0.0,
                    max_value=100.0,
                    value=float(cur_fin.dso_peak_demand_fee_eur_kw_month),
                    step=0.5,
                    key="comb_fin_dso_peak",
                )
                dso_pen = st.number_input(
                    "Overload Penalty (€/kW)",
                    min_value=0.0,
                    max_value=500.0,
                    value=float(cur_fin.grid_overload_penalty_eur_kw),
                    step=1.0,
                    key="comb_fin_dso_pen",
                )
                dso_fix = st.number_input(
                    "Grid Standing Fee (€/month)",
                    min_value=0.0,
                    max_value=5000.0,
                    value=float(cur_fin.dso_fixed_fee_eur_month),
                    step=10.0,
                    key="comb_fin_dso_fix",
                )

            with p3_col:
                st.markdown("**3. Metering**")
                meter_fix = st.number_input(
                    "Metering Fee (€/month)",
                    min_value=0.0,
                    max_value=2000.0,
                    value=float(cur_fin.metering_fixed_fee_eur_month),
                    step=5.0,
                    key="comb_fin_meter_fix",
                )

            with p4_col:
                st.markdown("**4. Taxes & Discount Rate**")
                tax_kwh = st.number_input(
                    "Energy Tax (€/kWh)",
                    min_value=0.0,
                    max_value=1.0,
                    value=float(cur_fin.energy_tax_eur_kwh),
                    step=0.005,
                    format="%.3f",
                    key="comb_fin_tax_kwh",
                )
                tax_pct = st.number_input(
                    "Levy / Tax Surcharge (%)",
                    min_value=0.0,
                    max_value=50.0,
                    value=float(cur_fin.tax_surcharge_pct),
                    step=1.0,
                    key="comb_fin_tax_pct",
                )
                disc_rate = st.number_input(
                    "Discount Rate for 15Y NPV (%)",
                    min_value=0.0,
                    max_value=20.0,
                    value=float(cur_fin.discount_rate_pct),
                    step=0.5,
                    key="comb_fin_disc_rate",
                )

        # --- Conditional Technology Cost Blocks (Only shown for active modules) ---
        if cur_sys.enable_solar:
            with st.container(border=True):
                st.markdown(
                    f"##### :material/solar_power: Block B – Solar Costs ({sim_res.solar_derivation.installed_kwp:,.1f} kWp Active)"
                )
                sc1, sc2, sc3, sc4 = st.columns(4)
                with sc1:
                    sol_mod = st.number_input(
                        "Modules (€/Wp)",
                        min_value=0.0, max_value=3.0, value=float(cur_fin.solar_modules_eur_wp), step=0.02, format="%.2f",
                        key="comb_fin_sol_mod",
                    )
                with sc2:
                    sol_inv = st.number_input(
                        "Inverter (€/W)",
                        min_value=0.0, max_value=2.0, value=float(cur_fin.solar_inverter_eur_w), step=0.01, format="%.2f",
                        key="comb_fin_sol_inv",
                    )
                with sc3:
                    sol_mnt = st.number_input(
                        "Mounting & Installation (€/Wp)",
                        min_value=0.0, max_value=3.0, value=float(cur_fin.solar_mounting_eur_wp), step=0.02, format="%.2f",
                        key="comb_fin_sol_mnt",
                    )
                with sc4:
                    sol_om = st.number_input(
                        "Annual O&M (% of CAPEX/year)",
                        min_value=0.0, max_value=15.0, value=float(cur_fin.solar_om_pct_of_capex), step=0.25,
                        key="comb_fin_sol_om",
                    )

        if cur_sys.enable_battery:
            with st.container(border=True):
                st.markdown(
                    f"##### :material/battery_charging_full: Block C – Battery Costs "
                    f"({cur_sys.battery_capacity_kwh:,.0f} kWh / {cur_sys.battery_power_kw:,.0f} kW Active)"
                )
                bc1, bc2, bc3, bc4 = st.columns(4)
                with bc1:
                    bat_rack = st.number_input(
                        "Storage Racks (€/kWh)",
                        min_value=0.0, max_value=2000.0, value=float(cur_fin.battery_capex_eur_kwh), step=10.0,
                        key="comb_fin_bat_rack",
                    )
                with bc2:
                    bat_inv = st.number_input(
                        "Inverter (€/kW)",
                        min_value=0.0, max_value=2000.0, value=float(cur_fin.battery_capex_eur_kw), step=10.0,
                        key="comb_fin_bat_inv",
                    )
                with bc3:
                    bat_bop = st.number_input(
                        "Installation & Cabling (€)",
                        min_value=0.0, max_value=500000.0, value=float(cur_fin.battery_fixed_bop_eur), step=1000.0,
                        key="comb_fin_bat_bop",
                    )
                with bc4:
                    bat_om = st.number_input(
                        "Annual O&M (% of CAPEX/year)",
                        min_value=0.0, max_value=15.0, value=float(cur_fin.battery_om_pct_of_capex), step=0.25,
                        key="comb_fin_bat_om",
                    )

                aug1, aug2, aug3 = st.columns([1.4, 1.1, 1.1])
                with aug1:
                    en_aug = st.checkbox(
                        "Include Mid-Life Cell Replacement (Augmentation)",
                        value=bool(cur_fin.enable_battery_augmentation),
                        key="comb_fin_bat_aug_chk",
                    )
                with aug2:
                    aug_yr = st.number_input(
                        "Replacement Year",
                        min_value=5, max_value=14, value=int(cur_fin.battery_augmentation_year), step=1,
                        key="comb_fin_bat_aug_yr",
                    )
                with aug3:
                    aug_pct = st.number_input(
                        "Replacement Cost (% of Storage Racks)",
                        min_value=10.0, max_value=100.0, value=float(cur_fin.battery_augmentation_pct_of_racks), step=5.0,
                        key="comb_fin_bat_aug_pct",
                    )

        if cur_sys.enable_generator:
            with st.container(border=True):
                st.markdown(
                    f"##### :material/power: Block D – Generator Costs "
                    f"({cur_sys.generator_rated_kw:,.0f} kW {cur_sys.fuel_type} Active)"
                )
                gc1, gc2, gc3, gc4, gc5 = st.columns([1.2, 1.1, 1.1, 0.9, 1.0])
                with gc1:
                    gen_model = st.selectbox(
                        "Acquisition Mode",
                        options=["Purchase (CAPEX)", "Monthly Rental (OPEX)"],
                        index=0 if cur_fin.generator_cost_model == "Purchase (CAPEX)" else 1,
                        key="comb_fin_gen_model",
                    )
                with gc2:
                    gen_capex = st.number_input(
                        "Purchase Price (€)",
                        min_value=0.0, max_value=2000000.0, value=float(cur_fin.generator_capex_eur), step=1000.0,
                        key="comb_fin_gen_capex",
                    )
                with gc3:
                    gen_rent = st.number_input(
                        "Monthly Rental (€/month)",
                        min_value=0.0, max_value=100000.0, value=float(cur_fin.generator_rental_eur_month), step=100.0,
                        key="comb_fin_gen_rent",
                    )
                with gc4:
                    fuel_pr = st.number_input(
                        f"Fuel Price (€/{sim_res.kpis.generator_fuel_unit})",
                        min_value=0.0, max_value=10.0, value=float(cur_fin.fuel_price_eur_per_unit), step=0.05, format="%.2f",
                        key="comb_fin_gen_fuel",
                    )
                with gc5:
                    gen_maint = st.number_input(
                        "Maintenance (€/operating hour)",
                        min_value=0.0, max_value=500.0, value=float(cur_fin.generator_maintenance_eur_per_hour), step=0.5,
                        key="comb_fin_gen_maint",
                    )

        fin_submitted = st.form_submit_button(
            "Calculate Financials",
            type="primary",
            use_container_width=True,
        )

    if fin_submitted or sim_res.financial_kpis is None:
        cur_fin.supplier_energy_price_eur_kwh = float(supp_kwh)
        cur_fin.supplier_fixed_fee_eur_month = float(supp_fix)
        cur_fin.dso_capacity_fee_eur_kw_month = float(dso_cap)
        cur_fin.dso_peak_demand_fee_eur_kw_month = float(dso_peak)
        cur_fin.grid_overload_penalty_eur_kw = float(dso_pen)
        cur_fin.dso_fixed_fee_eur_month = float(dso_fix)
        cur_fin.metering_fixed_fee_eur_month = float(meter_fix)
        cur_fin.energy_tax_eur_kwh = float(tax_kwh)
        cur_fin.tax_surcharge_pct = float(tax_pct)
        cur_fin.discount_rate_pct = float(disc_rate)

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

        evaluate_combined_financials(sim_res, cur_fin)
        st.session_state.pop("comb_cached_excel_bytes", None)

    fin_kpis = sim_res.financial_kpis

    st.markdown("---")
    st.markdown("##### :material/account_balance: Consolidated Financial Summary")

    fk1, fk2, fk3, fk4 = st.columns(4)
    with fk1:
        render_kpi_card(
            title="Total Combined CAPEX",
            value=f"€{fin_kpis.total_capex_eur:,.0f}",
            subtext=(
                f"Solar: €{fin_kpis.solar_capex_eur:,.0f} | "
                f"Battery: €{fin_kpis.battery_capex_eur:,.0f} | "
                f"Gen: €{fin_kpis.generator_capex_eur:,.0f}"
            ),
            status="default",
        )
    with fk2:
        render_kpi_card(
            title="Annual Total OPEX",
            value=f"€{fin_kpis.total_annual_opex_eur:,.0f} / yr",
            subtext=f"Current situation: €{fin_kpis.baseline_total_opex_eur:,.0f} / yr",
            status="default",
        )
    with fk3:
        render_kpi_card(
            title="Annual Net Savings vs. Current situation",
            value=f"€{fin_kpis.annual_savings_eur:,.0f} / yr",
            subtext=(
                f"Cost change: {(-fin_kpis.annual_savings_eur / max(1.0, fin_kpis.baseline_total_opex_eur) * 100.0):+.1f}%"
            ),
            status="ok" if fin_kpis.annual_savings_eur > 0 else "alert",
        )
    with fk4:
        pb_str = f"{fin_kpis.payback_years:.1f} yrs" if fin_kpis.payback_years is not None else "N/A"
        render_kpi_card(
            title="Payback Period & 15Y NPV",
            value=f"{pb_str} | €{fin_kpis.npv_15y_eur:,.0f}",
            subtext=f"15-Year NPV at {cur_fin.discount_rate_pct:.1f}% discount rate",
            status="ok" if fin_kpis.npv_15y_eur > 0 else "default",
        )

    # Cost Comparison Chart (Current situation vs. Combined system)
    with st.container(border=True):
        fig_cost_cmp = create_financial_cost_comparison_figure(sim_res)
        st.plotly_chart(fig_cost_cmp, use_container_width=True, key="comb_fin_cost_cmp_chart")

    # 15-Year Cashflow Table
    with st.container(border=True):
        st.markdown("##### :material/table_chart: 15-Year Lifecycle Cashflow Table")
        st.dataframe(
            sim_res.cashflow_15y_df,
            use_container_width=True,
            hide_index=True,
        )


# ======================================================================================
# LEVEL 3: Permanent Master Output (Always Visible Below Sub-Tabs)
# ======================================================================================

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
    st.markdown("#### :material/monitoring: Master System Output (Live 15-Minute Simulation)")

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

    # 2. Shared Synchronized 15-Minute Master Chart + Timeframe Filter + Excel Download
    with st.container(border=True):
        hdr1, hdr2, hdr3 = st.columns([2.2, 1.3, 1.3])
        with hdr1:
            st.markdown("##### :material/stacked_line_chart: 15-Minute Power Flow & Battery Level")
        with hdr2:
            if "comb_dispatch_timeframe" not in st.session_state or not st.session_state["comb_dispatch_timeframe"]:
                st.session_state["comb_dispatch_timeframe"] = "7D"
            disp_tf = st.segmented_control(
                "Dispatch Window",
                options=["7D", "1M", "3M", "All"],
                default=st.session_state["comb_dispatch_timeframe"],
                key="comb_dispatch_tf_ctrl",
                label_visibility="collapsed",
            )
            if not disp_tf:
                disp_tf = st.session_state.get("comb_dispatch_timeframe", "7D")
            else:
                st.session_state["comb_dispatch_timeframe"] = disp_tf
        with hdr3:
            if "comb_cached_excel_bytes" not in st.session_state:
                st.session_state["comb_cached_excel_bytes"] = build_combined_verification_excel_bytes(sim_res)
            st.download_button(
                label="Download Excel (.xlsx)",
                data=st.session_state["comb_cached_excel_bytes"],
                file_name="Combined_System_Verification.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                icon=":material/download:",
                use_container_width=True,
                type="primary",
            )

        fig_master = create_combined_dispatch_soc_figure(sim_res=sim_res, timeframe=disp_tf)
        st.plotly_chart(
            fig_master,
            use_container_width=True,
            key=f"comb_master_dispatch_chart_{disp_tf}",
        )

    # 3. Compact System Comparison Table
    with st.container(border=True):
        st.markdown("##### :material/table_chart: System Comparison Table (vs. Current situation)")
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
        page_title="Combined system (Grid + Solar + Battery + Generator)",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    apply_custom_styles()
    _init_session_defaults()

    st.markdown("### :material/hub: Combined system (Grid + Solar + Battery + Generator)")

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
            ":material/rule: 5. Interaction Rules",
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
        render_subtab5_interaction_rules()

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
