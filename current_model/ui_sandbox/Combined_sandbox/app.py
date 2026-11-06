"""
========================================================================================
Combined System Sandbox Application (ui_sandbox/Combined_sandbox/app.py)
========================================================================================

Standalone Execution:
    python -m streamlit run "ui_sandbox/Combined_sandbox/app.py"

Design Standard ("Clean Screen Policy"):
  - Strict Terminology: Consumption, Current situation, Grid, Solar, Battery,
    Generator, Combined system.
  - 3-Tab Layout:
      * Tab 1: Consumption (CSV Upload as Default, Session-Persistent, Auto Sniffer,
        15-min-kWh * 4 -> kW, 4 KPI Cards, 15-Min Chart with 7D/1M/3M/All & RangeSlider)
      * Tab 2: Combined system (100% Purely Physical/Technical: Unified st.form with
        2x2 Grid & Expanders, Default GPS Amsterdam 52.3676 / 4.9041, Rules 1-3,
        4 Technical KPI Cards, Synchronized 15-Min Chart, Comparison Table &
        4-Sheet Excel Verification Export .xlsx)
      * Tab 3: Financials (Dedicated Separate Tab for Grid Tariffs, Solar/Battery/Generator
        CAPEX & OPEX Inputs, 4 Financial KPI Cards & Cost Comparison Tables)
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
        derive_quick_sizing,
        QUICK_PRESET_OPTIONS,
        simulate_combined_system_dispatch,
        evaluate_combined_financials,
    )
except (ImportError, AttributeError):
    # If a long-running Streamlit process cached an older in-memory version in sys.modules,
    # purge and re-import freshly from disk.
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
        derive_quick_sizing,
        QUICK_PRESET_OPTIONS,
        simulate_combined_system_dispatch,
        evaluate_combined_financials,
    )
from ui_sandbox.Combined_sandbox.combined_charts import (
    create_consumption_baseline_figure,
    create_combined_dispatch_soc_figure,
)
from ui_sandbox.Combined_sandbox.combined_excel_exporter import (
    build_combined_verification_excel_bytes,
)


BENCHMARK_PROFILES = {
    "Commercial Facility (250 kW Peak)": 250.0,
    "Industrial Facility (430 kW Peak)": 430.0,
    "Thermal / Heat Pump Facility (110 kW Peak)": 110.0,
    "Custom Peak Load (kW)": -1.0,
}

PRIORITY_TIME_NAMES = ["timestamp", "datum", "date", "datetime", "zeitstempel", "time", "period", "fecha"]
PRIORITY_POWER_NAMES = [
    "total_demand_kw", "kw", "power", "power_kw", "active_power_kw",
    "p_load_kw", "leistung_kw", "gesamt_kw", "demand_kw", "kwh", "energy_kwh",
]


def _pick_best_column(cols: List[str], suggested: List[str], priority_keywords: List[str], fallback_idx: int = 0) -> int:
    """Selects the most meaningful column index using priority names before falling back."""
    if not cols:
        return 0
    for kw in priority_keywords:
        for idx, c in enumerate(cols):
            if str(c).strip().lower() == kw:
                return idx
    for kw in priority_keywords:
        for idx, c in enumerate(cols):
            if kw in str(c).strip().lower():
                return idx
    if suggested:
        for s in suggested:
            if s in cols:
                return cols.index(s)
    return min(max(0, fallback_idx), len(cols) - 1)


def _init_session_defaults() -> None:
    """Initializes clean default session state values for the Combined System Sandbox."""
    if "comb_system_cfg" not in st.session_state:
        st.session_state["comb_system_cfg"] = CombinedSystemConfig()
    if "comb_rules_cfg" not in st.session_state:
        st.session_state["comb_rules_cfg"] = InteractionRulesConfig()
    if "comb_fin_cfg" not in st.session_state:
        st.session_state["comb_fin_cfg"] = CombinedFinancialConfig()

    defaults = {
        # Tab 1: CSV Upload is fixed as Default
        "tab1_active_source": "csv",
        "comb_load_source_mode": "CSV Upload",
        "comb_benchmark_preset": "Commercial Facility (250 kW Peak)",
        "comb_custom_peak_kw": 250.0,
        "comb_tab1_timeframe": "All",
        "comb_dispatch_timeframe": "7D",
        # Tab 2: Symmetrical 4-Source Toggles & Amsterdam GPS defaults
        "comb_enable_grid_toggle": True,
        "comb_enable_solar_toggle": True,
        "comb_enable_battery_toggle": True,
        "comb_enable_generator_toggle": True,
        "comb_solar_site_name": "Amsterdam, Netherlands",
        "comb_solar_preset_choice": "Amsterdam (Default GPS)",
        "comb_solar_lat": 52.3676,
        "comb_solar_lon": 4.9041,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _get_active_load_series() -> Tuple[LoadSeries2025, str]:
    """Retrieves or normalizes the active 35,040-step load profile for 2025 from session state."""
    # 1. Check shared active_load_series_2025 (populated by render_tab1_consumption)
    if (
        "active_load_series_2025" in st.session_state
        and isinstance(st.session_state["active_load_series_2025"], LoadSeries2025)
    ):
        fname = st.session_state.get("active_csv_filename", "Active Baseline Profile")
        label = f"CSV: {fname}" if st.session_state.get("tab1_active_source") == "csv" else "Synthetic Load Profile"
        st.session_state["comb_active_load_series"] = st.session_state["active_load_series_2025"]
        st.session_state["comb_active_load_label"] = label
        return st.session_state["active_load_series_2025"], label

    # 2. Check active_csv_df if normalized series needs reconstruction
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

    # 3. Check comb_active_load_series
    if (
        "comb_active_load_series" in st.session_state
        and isinstance(st.session_state["comb_active_load_series"], LoadSeries2025)
    ):
        return (
            st.session_state["comb_active_load_series"],
            st.session_state.get("comb_active_load_label", "Active Load Profile"),
        )

    # 4. Fallback: 250 kW commercial benchmark
    load_bench = synthesize_benchmark_load_profile_2025(nominal_peak_kw=250.0)
    st.session_state["active_load_series_2025"] = load_bench
    st.session_state["comb_active_load_series"] = load_bench
    st.session_state["comb_active_load_label"] = "Commercial Facility (250 kW Peak)"
    return load_bench, "Commercial Facility (250 kW Peak)"


def _sync_shared_load_series() -> None:
    """
    Detects if the active load profile has changed and invalidates downstream simulation caches
    so Tab 2 and Tab 3 always calculate against the current profile.
    """
    load_series, _ = _get_active_load_series()
    fingerprint = (
        len(load_series.power_kw),
        round(float(np.sum(load_series.power_kw)), 3),
        round(float(np.max(load_series.power_kw)), 3),
    )
    if st.session_state.get("comb_load_fingerprint") != fingerprint:
        st.session_state["comb_load_fingerprint"] = fingerprint
        st.session_state.pop("comb_sandbox_result", None)
        st.session_state.pop("comb_cached_excel_bytes", None)


# ======================================================================================
# TAB 1: Consumption (Baseline)
# ======================================================================================

def render_tab1_consumption_view() -> None:
    """
    Renders Tab 1: Consumption Profile Modeling & Ingestion.
    Shared 1:1 with all other sandboxes:
      - Multi-format file ingestion (.csv, .txt, .zip) with automatic archive extraction
      - Multi-encoding fallback decoding (utf-8, utf-8-sig, latin1, cp1252)
      - Skip header rows with interactive CSV Table Preview
      - Multi-column timestamp selection and multi-channel power summing
      - 4 unit conversion modes (15-min kWh -> kW, Direct kW, W -> kW, Hourly kWh -> kW)
      - Day-first date parsing toggle (DD.MM vs MM.DD) with live sample preview
      - Day-accurate date range filter (start_date, end_date)
      - Instant 1-click Demo CSV loader (Full Year 2025)
      - Bottom-up synthetic load simulator as an alternative source mode
    """
    st.markdown(
        """
        <div style="background: #0f172a; border-left: 4px solid #38bdf8; padding: 10px 16px; border-radius: 6px; margin-bottom: 12px;">
            <strong style="color:#f8fafc; font-size:0.95rem;">Consumption</strong>
            <p style="color:#94a3b8; font-size:0.82rem; margin:2px 0 0 0;">
                Import a 15-minute consumption CSV file or select a reference profile.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    render_tab1_consumption(key_prefix="comb_tab1_cons")
    _sync_shared_load_series()


# ======================================================================================
# Quick Sizing Presets & Share Split (callbacks run before the script re-renders)
# ======================================================================================

_SOLAR_WIDGET_KEYS = ["comb_solar_sizing_radio", "comb_solar_target_share_num", "comb_solar_direct_kwp_num"]
_BATTERY_WIDGET_KEYS = ["comb_battery_capacity_kwh_num", "comb_battery_power_kw_num"]
_GENERATOR_WIDGET_KEYS = ["comb_generator_rated_kw_num"]


def _pct_from_label(label) -> float:
    """Converts a preset label like '40%' to 40.0; returns -1 for Custom/None."""
    if not label or label == "Custom":
        return -1.0
    return float(str(label).replace("%", ""))


def _quick_sizing(solar_pct: float, battery_pct: float):
    """Runs the quick sizing engine with the current Grid limit, Solar net profile, and Battery envelope."""
    load_series, _ = _get_active_load_series()
    cfg: CombinedSystemConfig = st.session_state["comb_system_cfg"]
    rules_cfg: Optional[InteractionRulesConfig] = st.session_state.get("comb_rules_cfg")

    spec_yield = float(st.session_state.get("comb_spec_yield", 1000.0))
    solar_profile = None
    if solar_pct > 0:
        eff_lat = float(st.session_state.get("comb_solar_lat", cfg.latitude))
        eff_lon = float(st.session_state.get("comb_solar_lon", cfg.longitude))
        unit_solar_kw, spec_yield, _ = get_unit_solar_generation_profile(
            latitude=eff_lat,
            longitude=eff_lon,
            tilt_deg=cfg.tilt_deg,
            azimuth_deg=180.0 if eff_lat >= 0.0 else 0.0,
            dc_ac_ratio=cfg.dc_ac_ratio,
        )
        n_steps = len(load_series.power_kw)
        if len(unit_solar_kw) != n_steps and n_steps > 0:
            reps = int(math.ceil(n_steps / max(1, len(unit_solar_kw))))
            unit_solar_kw = np.tile(unit_solar_kw, reps)[:n_steps]
        ann_load = float(load_series.total_energy_kwh)
        solar_kwp = (ann_load * (solar_pct / 100.0)) / max(100.0, spec_yield)
        solar_profile = unit_solar_kw * solar_kwp

    return derive_quick_sizing(
        load_kw=load_series.power_kw,
        grid_limit_kw=float(st.session_state.get("comb_eff_grid_limit_kw", cfg.grid_limit_kw)),
        solar_share_pct=solar_pct,
        battery_share_pct=battery_pct,
        specific_yield_kwh_per_kwp=spec_yield,
        min_soc_pct=cfg.min_soc_pct,
        max_soc_pct=cfg.max_soc_pct,
        round_trip_efficiency_pct=cfg.round_trip_efficiency_pct,
        solar_profile_kw=solar_profile,
        rules_cfg=rules_cfg,
    )


def _set_solar_share(cfg: CombinedSystemConfig, pct: float) -> None:
    cfg.solar_sizing_method = "target_share_pct"
    cfg.target_consumption_share_pct = max(5.0, float(pct))
    for k in _SOLAR_WIDGET_KEYS:
        st.session_state.pop(k, None)


def _set_battery_share(cfg: CombinedSystemConfig, pct: float) -> None:
    sol_pct = cfg.target_consumption_share_pct if cfg.enable_solar else 0.0
    res = _quick_sizing(sol_pct, pct)
    cfg.battery_power_kw = max(5.0, res.battery_power_kw)
    cfg.battery_capacity_kwh = max(10.0, res.battery_capacity_kwh)
    for k in _BATTERY_WIDGET_KEYS:
        st.session_state.pop(k, None)


def _set_generator_share(cfg: CombinedSystemConfig, pct: float) -> None:
    sol_pct = cfg.target_consumption_share_pct if cfg.enable_solar else 0.0
    res = _quick_sizing(sol_pct, 100.0 - pct)
    cfg.generator_rated_kw = max(10.0, res.generator_rated_kw)
    for k in _GENERATOR_WIDGET_KEYS:
        st.session_state.pop(k, None)


def _on_tile_preset(source: str) -> None:
    """Callback for the 20/40/60/100% preset buttons inside the Solar/Battery/Generator tiles."""
    pct = _pct_from_label(st.session_state.get(f"comb_{source}_preset"))
    if pct < 0:
        return
    cfg: CombinedSystemConfig = st.session_state["comb_system_cfg"]
    if source == "solar":
        _set_solar_share(cfg, pct)
    elif source == "battery":
        _set_battery_share(cfg, pct)
    elif source == "generator":
        _set_generator_share(cfg, pct)


def _on_split_quick(solar_pct: float, battery_pct: float) -> None:
    """Callback for the '100% solution' buttons: sets the Share Split sliders."""
    st.session_state["comb_split_solar_pct"] = int(solar_pct)
    st.session_state["comb_split_battery_pct"] = int(battery_pct)


def _on_apply_split() -> None:
    """Writes the Share Split into all tiles, switches sources on/off and runs the simulation."""
    sol = float(st.session_state.get("comb_split_solar_pct", 40))
    bat = float(st.session_state.get("comb_split_battery_pct", 60))
    gen = 100.0 - bat
    cfg: CombinedSystemConfig = st.session_state["comb_system_cfg"]
    rules: Optional[InteractionRulesConfig] = st.session_state.get("comb_rules_cfg")
    if sol > 0:
        _set_solar_share(cfg, sol)
    if bat > 0:
        _set_battery_share(cfg, bat)
    if gen > 0:
        _set_generator_share(cfg, gen)
    st.session_state["comb_enable_solar_toggle"] = sol > 0
    st.session_state["comb_enable_battery_toggle"] = bat > 0
    st.session_state["comb_enable_generator_toggle"] = gen > 0

    # When pure battery without solar is chosen, ensure grid recharging is active
    if bat > 0 and sol == 0 and rules is not None:
        rules.rule3_charging_sources = "solar_and_grid"
        rules.rule2_battery_strategy = "peak_shaving_only"
        st.session_state["comb_rule3_select"] = "solar_and_grid"
        st.session_state["comb_rule2_select"] = "peak_shaving_only"

    for src in ("solar", "battery", "generator"):
        st.session_state.pop(f"comb_{src}_preset", None)
    st.session_state["comb_force_simulate"] = True


def _on_reset_defaults() -> None:
    """Resets all technical inputs of Tab 2 to defaults (Amsterdam GPS, all sources on)."""
    keep_prefixes = ("comb_active_load", "comb_load_", "comb_benchmark", "comb_custom_peak", "comb_fin_cfg")
    for k in list(st.session_state.keys()):
        if k.startswith("comb_") and not k.startswith(keep_prefixes):
            del st.session_state[k]
    st.session_state["comb_system_cfg"] = CombinedSystemConfig()
    st.session_state["comb_rules_cfg"] = InteractionRulesConfig()
    _init_session_defaults()


def render_share_split_block() -> None:
    """Share Split: Solar as overall energy source, Battery/Generator split the overload (100%)."""
    st.caption(
        "Solar covers a share of annual Consumption. The overload above the Grid limit is split "
        "between Battery and Generator (always 100%)."
    )
    if "comb_split_solar_pct" not in st.session_state:
        st.session_state["comb_split_solar_pct"] = 40
    if "comb_split_battery_pct" not in st.session_state:
        st.session_state["comb_split_battery_pct"] = 60

    c1, c2, c3 = st.columns([1.2, 1.2, 1.0])
    with c1:
        sol = st.slider(
            "Solar (% of Consumption)", min_value=0, max_value=150, step=5,
            key="comb_split_solar_pct",
        )
    with c2:
        bat = st.slider(
            "Battery (% of overload)", min_value=0, max_value=100, step=5,
            key="comb_split_battery_pct",
        )
    gen = 100 - bat
    with c3:
        st.metric("Generator (rest of overload)", f"{gen} %")

    q1, q2, q3, q4, q5 = st.columns(5)
    q1.button("100% Battery", icon=":material/battery_charging_full:", use_container_width=True,
              key="comb_q_bat100", on_click=_on_split_quick, args=(sol, 100))
    q2.button("100% Generator", icon=":material/power:", use_container_width=True,
              key="comb_q_gen100", on_click=_on_split_quick, args=(sol, 0))
    q3.button("100% Solar", icon=":material/solar_power:", use_container_width=True,
              key="comb_q_sol100", on_click=_on_split_quick, args=(100, bat))
    q4.button("50 / 50", icon=":material/balance:", use_container_width=True,
              key="comb_q_5050", on_click=_on_split_quick, args=(sol, 50))
    q5.button("All 100%", icon=":material/done_all:", use_container_width=True,
              key="comb_q_all100", on_click=_on_split_quick, args=(100, 100))

    preview = _quick_sizing(float(sol), float(bat))
    st.caption(
        f"Preview: Solar **{preview.solar_kwp:,.1f} kWp** | "
        f"Battery **{preview.battery_power_kw:,.1f} kW / {preview.battery_capacity_kwh:,.0f} kWh** | "
        f"Generator **{preview.generator_rated_kw:,.1f} kW** "
        f"(max overload {preview.max_overload_kw:,.1f} kW, largest event "
        f"{preview.largest_overload_event_kwh:,.0f} kWh)"
    )
    st.button(
        "Apply Split & Simulate", icon=":material/play_arrow:", type="primary",
        use_container_width=True, key="comb_apply_split_btn", on_click=_on_apply_split,
    )


# ======================================================================================
# TAB 2: Combined system (100% Purely Physical & Technical)
# ======================================================================================

def render_tab2_combined_system_view() -> None:
    """
    Renders Tab 2: Combined system (Grid + Solar + Battery + Generator)
      - Symmetrical 4-source layout: each source in its own bordered container with
        a top header row containing an activation toggle (st.toggle), and ALL source
        parameters neatly grouped in a single expander underneath.
      - GPS Location in Solar matching the Solar module: City/Address search via Open-Meteo,
        quick site presets with Amsterdam as default, and manual coordinate inputs.
      - 1 Row of 4 Technical KPI Cards
      - Synchronized 15-Minute Dispatch & SoC Chart (with 7D, 1M, 3M, All & RangeSlider)
      - Direct 4-Sheet Excel Verification Export (.xlsx) + Compact Comparison Table
    """
    load_series, load_label = _get_active_load_series()
    load_kw = load_series.power_kw
    annual_consumption_kwh = float(load_series.total_energy_kwh)
    orig_peak_kw = float(load_series.peak_demand_kw)

    cur_sys: CombinedSystemConfig = st.session_state["comb_system_cfg"]
    cur_rules: InteractionRulesConfig = st.session_state["comb_rules_cfg"]

    st.markdown("#### :material/tune: 1. System Inputs")

    with st.expander(":material/pie_chart: Optional: Quick System Sizing (Share Split)", expanded=False):
        render_share_split_block()

    # Row 1 of 2x2 Grid: Tile 1 (Grid) & Tile 2 (Solar)
    row1_col1, row1_col2 = st.columns(2)

    # --- TILE 1 (Top Left): Grid Connection & Baseline ---
    with row1_col1:
        with st.container(border=True):
            hdr_g1, hdr_g2 = st.columns([1.5, 1.0])
            with hdr_g1:
                st.markdown("##### :material/electrical_services: Grid")
            with hdr_g2:
                enable_grid = st.toggle(
                    "Enable Grid",
                    key="comb_enable_grid_toggle",
                )

            g_c1, g_c2 = st.columns([1.3, 1.2])
            with g_c1:
                grid_limit_input = st.number_input(
                    "Contracted Grid Limit (kW)",
                    min_value=10.0,
                    max_value=20000.0,
                    value=float(cur_sys.grid_limit_kw),
                    step=10.0,
                    key="comb_grid_limit_input",
                )
            with g_c2:
                quick_limit_mode = st.selectbox(
                    "Quick Sizing (% of Peak)",
                    options=[
                        "Manual kW Input",
                        f"80% of Peak ({orig_peak_kw * 0.80:,.0f} kW)",
                        f"65% of Peak ({orig_peak_kw * 0.65:,.0f} kW)",
                        f"50% of Peak ({orig_peak_kw * 0.50:,.0f} kW)",
                    ],
                    index=0,
                    key="comb_grid_quick_mode",
                )

            if "80%" in quick_limit_mode:
                eff_grid_limit_kw = round(orig_peak_kw * 0.80, 1)
            elif "65%" in quick_limit_mode:
                eff_grid_limit_kw = round(orig_peak_kw * 0.65, 1)
            elif "50%" in quick_limit_mode:
                eff_grid_limit_kw = round(orig_peak_kw * 0.50, 1)
            else:
                eff_grid_limit_kw = float(grid_limit_input)
            st.session_state["comb_eff_grid_limit_kw"] = float(eff_grid_limit_kw)

            overload_arr = np.maximum(0.0, load_kw - eff_grid_limit_kw)
            init_overload_kw = float(np.max(overload_arr)) if len(overload_arr) > 0 else 0.0
            init_overload_hrs = float(np.sum(overload_arr > 0.05) * 0.25)
            init_overload_kwh = float(np.sum(overload_arr) * 0.25)

            st.caption(
                f"**Current situation ({load_label}):** "
                f"Measured Peak = **{orig_peak_kw:,.1f} kW** | "
                f"Overload above {eff_grid_limit_kw:,.0f} kW = **{init_overload_kw:,.1f} kW** "
                f"(**{init_overload_hrs:,.1f} hrs/yr** / **{init_overload_kwh:,.0f} kWh/yr**)"
            )

    # --- TILE 2 (Top Right): Solar PV System (Matching Solar Module GPS) ---
    with row1_col2:
        with st.container(border=True):
            hdr_s1, hdr_s2 = st.columns([1.5, 1.0])
            with hdr_s1:
                st.markdown("##### :material/solar_power: Solar")
            with hdr_s2:
                enable_solar = st.toggle(
                    "Enable Solar",
                    key="comb_enable_solar_toggle",
                )

            st.segmented_control(
                "Quick Preset", options=QUICK_PRESET_OPTIONS, key="comb_solar_preset",
                on_change=_on_tile_preset, args=("solar",),
            )
            # Location Search & Quick Presets (Solar Module Style)
            col_search, col_preset = st.columns(2)
            with col_search:
                search_query = st.text_input(
                    "Search City or Address (Worldwide):",
                    placeholder="e.g. Amsterdam, Rotterdam, Berlin, Madrid, Mendoza...",
                    key="comb_solar_search_input",
                )
                if search_query and len(search_query.strip()) >= 2:
                    search_results = search_locations_open_meteo(search_query.strip(), count=5)
                    if search_results:
                        match_dict = {
                            f"{r['display_name']} ({r['lat']}°, {r['lon']}°)": r
                            for r in search_results
                        }
                        selected_match = st.selectbox(
                            "Matching Locations (Select to apply):",
                            options=list(match_dict.keys()),
                            key="comb_solar_search_match_select",
                        )
                        if selected_match in match_dict:
                            chosen = match_dict[selected_match]
                            if (
                                abs(st.session_state.get("comb_solar_lat", 52.3676) - chosen["lat"]) > 0.001
                                or abs(st.session_state.get("comb_solar_lon", 4.9041) - chosen["lon"]) > 0.001
                            ):
                                st.session_state["comb_solar_lat"] = chosen["lat"]
                                st.session_state["comb_solar_lon"] = chosen["lon"]
                                st.session_state["comb_solar_site_name"] = chosen["display_name"]
                                st.session_state.pop("comb_solar_lat_num_input", None)
                                st.session_state.pop("comb_solar_lon_num_input", None)
                                st.session_state["comb_solar_preset_choice"] = "Custom GPS Coordinates"
                                st.rerun()
                    else:
                        st.caption("No matching cities found. Try another spelling.")

            with col_preset:
                preset_options = list(SOLAR_SITE_PRESETS.keys()) + ["Custom GPS Coordinates"]
                curr_preset = st.session_state.get("comb_solar_preset_choice", "Amsterdam (Default GPS)")
                preset_idx = (
                    preset_options.index(curr_preset)
                    if curr_preset in preset_options
                    else 0
                )
                preset_choice = st.selectbox(
                    "Quick Site Presets:",
                    options=preset_options,
                    index=preset_idx,
                    key="comb_solar_preset_select",
                )
                if preset_choice in SOLAR_SITE_PRESETS and preset_choice != st.session_state.get("comb_solar_preset_choice"):
                    p_data = SOLAR_SITE_PRESETS[preset_choice]
                    st.session_state["comb_solar_lat"] = float(p_data["latitude"])
                    st.session_state["comb_solar_lon"] = float(p_data["longitude"])
                    st.session_state["comb_solar_site_name"] = p_data["name"]
                    st.session_state.pop("comb_solar_lat_num_input", None)
                    st.session_state.pop("comb_solar_lon_num_input", None)
                    st.session_state["comb_solar_preset_choice"] = preset_choice
                    st.rerun()

            # Sizing Controls
            sz_c1, sz_c2, sz_c3 = st.columns([1.3, 1.1, 1.1])
            with sz_c1:
                sizing_label = st.radio(
                    "Sizing Method",
                    options=["% of Consumption", "Direct kWp"],
                    index=0 if cur_sys.solar_sizing_method == "target_share_pct" else 1,
                    horizontal=True,
                    key="comb_solar_sizing_radio",
                )
            with sz_c2:
                target_share_pct = st.number_input(
                    "Target Share (% of Consumption)",
                    min_value=5.0,
                    max_value=250.0,
                    value=float(cur_sys.target_consumption_share_pct),
                    step=5.0,
                    key="comb_solar_target_share_num",
                )
            with sz_c3:
                direct_kwp_val = st.number_input(
                    "Direct Solar Size (kWp)",
                    min_value=1.0,
                    max_value=20000.0,
                    value=float(cur_sys.solar_kwp),
                    step=10.0,
                    key="comb_solar_direct_kwp_num",
                )

            # Collapsed Mini-Expander: Advanced Solar Settings
            with st.expander(":material/tune: Advanced Solar Settings", expanded=False):
                coord_c1, coord_c2 = st.columns(2)
                cur_lat_val = float(st.session_state.get("comb_solar_lat", 52.3676))
                cur_lon_val = float(st.session_state.get("comb_solar_lon", 4.9041))
                with coord_c1:
                    eff_lat = st.number_input(
                        "GPS Latitude (°)",
                        min_value=-65.0,
                        max_value=65.0,
                        value=cur_lat_val,
                        step=0.0001,
                        format="%.4f",
                        key="comb_solar_lat_num_input",
                    )
                with coord_c2:
                    eff_lon = st.number_input(
                        "GPS Longitude (°)",
                        min_value=-180.0,
                        max_value=180.0,
                        value=cur_lon_val,
                        step=0.0001,
                        format="%.4f",
                        key="comb_solar_lon_num_input",
                    )
                if abs(eff_lat - cur_lat_val) > 0.0001 or abs(eff_lon - cur_lon_val) > 0.0001:
                    st.session_state["comb_solar_lat"] = eff_lat
                    st.session_state["comb_solar_lon"] = eff_lon

                adv_s1, adv_s2 = st.columns(2)
                with adv_s1:
                    panel_wp = st.number_input(
                        "Panel Wattage (Wp)",
                        min_value=250.0,
                        max_value=750.0,
                        value=float(cur_sys.panel_wp),
                        step=10.0,
                        key="comb_solar_panel_wp_num",
                    )
                with adv_s2:
                    dc_ac_ratio = st.number_input(
                        "DC/AC Ratio (Inverter Clipping)",
                        min_value=1.00,
                        max_value=1.60,
                        value=float(cur_sys.dc_ac_ratio),
                        step=0.02,
                        key="comb_solar_dc_ac_ratio_num",
                    )

            sizing_method_key = (
                "target_share_pct" if sizing_label == "% of Consumption" else "direct_kwp"
            )
            _, spec_yield, _ = get_unit_solar_generation_profile(
                latitude=eff_lat,
                longitude=eff_lon,
                tilt_deg=30.0,
                azimuth_deg=180.0 if eff_lat >= 0.0 else 0.0,
                dc_ac_ratio=float(dc_ac_ratio),
            )
            st.session_state["comb_spec_yield"] = float(spec_yield)
            solar_deriv_preview = derive_solar_sizing_and_formula(
                annual_consumption_kwh=annual_consumption_kwh,
                specific_yield_kwh_per_kwp=spec_yield,
                sizing_method=sizing_method_key,
                direct_kwp=float(direct_kwp_val),
                target_share_pct=float(target_share_pct),
                panel_wp=float(panel_wp),
                dc_ac_ratio=float(dc_ac_ratio),
                enable_solar=bool(enable_solar),
            )
            site_disp_name = st.session_state.get("comb_solar_site_name", "Amsterdam, Netherlands")
            st.caption(
                f"Data source: EU PVGIS (ERA5 TMY, 15-min resolution) | Location: **{site_disp_name}** | "
                f"Specific Yield: **{spec_yield:,.0f} kWh/kWp/year**"
            )
            st.info(solar_deriv_preview.formula_text, icon=":material/calculate:")

    # Row 2 of 2x2 Grid: Tile 3 (Battery) & Tile 4 (Generator)
    row2_col1, row2_col2 = st.columns(2)

    # --- TILE 3 (Bottom Left): Battery Storage (BESS) ---
    with row2_col1:
        with st.container(border=True):
            hdr_b1, hdr_b2 = st.columns([1.5, 1.0])
            with hdr_b1:
                st.markdown("##### :material/battery_charging_full: Battery")
            with hdr_b2:
                enable_battery = st.toggle(
                    "Enable Battery",
                    key="comb_enable_battery_toggle",
                )

            st.segmented_control(
                "Quick Preset", options=QUICK_PRESET_OPTIONS, key="comb_battery_preset",
                on_change=_on_tile_preset, args=("battery",),
            )
            b_c1, b_c2 = st.columns(2)
            with b_c1:
                bess_kwh = st.number_input(
                    "Battery Capacity (kWh)",
                    min_value=10.0,
                    max_value=50000.0,
                    value=float(cur_sys.battery_capacity_kwh),
                    step=25.0,
                    key="comb_battery_capacity_kwh_num",
                )
            with b_c2:
                bess_kw = st.number_input(
                    "Battery Power (kW)",
                    min_value=5.0,
                    max_value=25000.0,
                    value=float(cur_sys.battery_power_kw),
                    step=10.0,
                    key="comb_battery_power_kw_num",
                )

            with st.expander(":material/tune: Advanced Battery Settings", expanded=False):
                s_col1, s_col2, s_col3 = st.columns(3)
                with s_col1:
                    min_soc_pct = st.number_input(
                        "Min SoC (%)",
                        min_value=0.0,
                        max_value=50.0,
                        value=float(cur_sys.min_soc_pct),
                        step=5.0,
                        key="comb_battery_min_soc_num",
                    )
                with s_col2:
                    max_soc_pct = st.number_input(
                        "Max SoC (%)",
                        min_value=55.0,
                        max_value=100.0,
                        value=float(cur_sys.max_soc_pct),
                        step=5.0,
                        key="comb_battery_max_soc_num",
                    )
                with s_col3:
                    rte_pct = st.number_input(
                        "Round-Trip Efficiency (%)",
                        min_value=60.0,
                        max_value=100.0,
                        value=float(cur_sys.round_trip_efficiency_pct),
                        step=1.0,
                        key="comb_battery_rte_num",
                    )

            usable_kwh = bess_kwh * max(0.0, (max_soc_pct - min_soc_pct) / 100.0)
            c_rate = (bess_kw / max(1.0, bess_kwh)) if bess_kwh > 0 else 0.0
            st.caption(
                f"Usable Energy: **{usable_kwh:,.0f} kWh** ({min_soc_pct:.0f}%–{max_soc_pct:.0f}% SoC) | "
                f"C-Rate: **{c_rate:.2f}C** | Efficiency: **{rte_pct:.0f}%**"
            )

    # --- TILE 4 (Bottom Right): Peaking Generator ---
    with row2_col2:
        with st.container(border=True):
            hdr_g1, hdr_g2 = st.columns([1.5, 1.0])
            with hdr_g1:
                st.markdown("##### :material/power: Generator")
            with hdr_g2:
                enable_generator = st.toggle(
                    "Enable Generator",
                    key="comb_enable_generator_toggle",
                )

            st.segmented_control(
                "Quick Preset", options=QUICK_PRESET_OPTIONS, key="comb_generator_preset",
                on_change=_on_tile_preset, args=("generator",),
            )
            gen_c1, gen_c2, gen_c3 = st.columns([1.1, 1.1, 1.0])
            with gen_c1:
                gen_rated_kw = st.number_input(
                    "Generator Rated Power (kW)",
                    min_value=10.0,
                    max_value=20000.0,
                    value=float(cur_sys.generator_rated_kw),
                    step=25.0,
                    key="comb_generator_rated_kw_num",
                )
            with gen_c2:
                gen_min_load_pct = st.number_input(
                    "Minimum Load (%) — Wet-Stacking Limit",
                    min_value=0.0,
                    max_value=80.0,
                    value=float(cur_sys.generator_min_load_pct),
                    step=5.0,
                    key="comb_generator_min_load_num",
                )
            with gen_c3:
                fuel_keys = list(FUEL_SPECS.keys())
                fuel_idx = fuel_keys.index(cur_sys.fuel_type) if cur_sys.fuel_type in fuel_keys else 0
                fuel_type = st.selectbox(
                    "Fuel Type",
                    options=fuel_keys,
                    index=fuel_idx,
                    key="comb_generator_fuel_type_select",
                )

            with st.expander(":material/tune: Advanced Generator Settings", expanded=False):
                adv_g1, adv_g2, adv_g3 = st.columns(3)
                with adv_g1:
                    gen_intercept = st.number_input(
                        "Standby Fuel Factor (unit/h/kW)",
                        min_value=0.0,
                        max_value=0.25,
                        value=float(cur_sys.gen_intercept_per_kw_rated),
                        step=0.005,
                        format="%.3f",
                        key="comb_generator_intercept_num",
                    )
                with adv_g2:
                    gen_slope = st.number_input(
                        "Fuel Consumption per kWh (unit/kWh)",
                        min_value=0.05,
                        max_value=0.80,
                        value=float(cur_sys.gen_slope_per_kwh),
                        step=0.01,
                        format="%.2f",
                        key="comb_generator_slope_num",
                    )
                with adv_g3:
                    gen_min_runtime_min = st.number_input(
                        "Minimum Runtime (minutes)",
                        min_value=15,
                        max_value=240,
                        value=int(cur_sys.gen_min_runtime_minutes),
                        step=15,
                        key="comb_generator_runtime_num",
                    )

            min_gen_kw = gen_rated_kw * (gen_min_load_pct / 100.0)
            f_spec = FUEL_SPECS[fuel_type]
            st.caption(
                f"Min Active Output: **{min_gen_kw:,.1f} kW** ({gen_min_load_pct:.0f}%) | "
                f"Fuel Unit: **{f_spec['unit']}**"
            )

    # ==================================================================================
    # SECTION 2: Interaction & Operating Rules
    # ==================================================================================
    st.markdown("#### :material/rule: 2. Interaction & Operating Rules")
    with st.container(border=True):
        r_col1, r_col2, r_col3 = st.columns(3)

        r1_keys = list(RULE1_OPTIONS.keys())
        r2_keys = list(RULE2_OPTIONS.keys())
        r3_keys = list(RULE3_OPTIONS.keys())

        with r_col1:
            rule1_key = st.selectbox(
                "Peak Priority (Above Grid Limit)",
                options=r1_keys,
                index=r1_keys.index(cur_rules.rule1_peak_priority) if cur_rules.rule1_peak_priority in r1_keys else 0,
                format_func=lambda k: RULE1_OPTIONS[k],
                key="comb_rule1_select",
            )

        with r_col2:
            rule2_key = st.selectbox(
                "Battery Strategy (Below Grid Limit)",
                options=r2_keys,
                index=r2_keys.index(cur_rules.rule2_battery_strategy) if cur_rules.rule2_battery_strategy in r2_keys else 0,
                format_func=lambda k: RULE2_OPTIONS[k],
                key="comb_rule2_select",
            )
            if rule2_key == "self_consumption_reserve":
                peak_reserve_soc_pct = st.slider(
                    "Peak Reserve SoC (%) held for peaks",
                    min_value=10,
                    max_value=90,
                    value=int(np.clip(cur_rules.peak_reserve_soc_pct, 10, 90)),
                    step=5,
                    key="comb_rule2_reserve_slider",
                )
            else:
                peak_reserve_soc_pct = float(cur_rules.peak_reserve_soc_pct)

        with r_col3:
            rule3_key = st.selectbox(
                "Battery Charging Sources",
                options=r3_keys,
                index=r3_keys.index(cur_rules.rule3_charging_sources) if cur_rules.rule3_charging_sources in r3_keys else 0,
                format_func=lambda k: RULE3_OPTIONS[k],
                key="comb_rule3_select",
            )

    # Primary Action Buttons
    sim_col1, sim_col2 = st.columns([4.0, 1.2])
    with sim_col1:
        simulate_clicked = st.button(
            "Simulate Combined System",
            icon=":material/play_arrow:",
            type="primary",
            use_container_width=True,
            key="comb_run_sim_btn",
        )
    with sim_col2:
        st.button(
            "Reset Defaults",
            icon=":material/restart_alt:",
            use_container_width=True,
            key="comb_reset_all_tech_btn",
            on_click=_on_reset_defaults,
        )

    force_sim = bool(st.session_state.pop("comb_force_simulate", False))
    if simulate_clicked or force_sim or "comb_sandbox_result" not in st.session_state:
        new_sys_cfg = CombinedSystemConfig(
            enable_grid=bool(enable_grid),
            grid_limit_kw=float(eff_grid_limit_kw),
            enable_solar=bool(enable_solar),
            site_preset=str(preset_choice),
            latitude=float(eff_lat),
            longitude=float(eff_lon),
            elevation_m=2.0,
            tilt_deg=30.0,
            azimuth_deg=180.0 if eff_lat >= 0.0 else 0.0,
            solar_sizing_method=sizing_method_key,
            solar_kwp=float(direct_kwp_val),
            panel_wp=float(panel_wp),
            dc_ac_ratio=float(dc_ac_ratio),
            target_consumption_share_pct=float(target_share_pct),
            enable_battery=bool(enable_battery),
            battery_capacity_kwh=float(bess_kwh),
            battery_power_kw=float(bess_kw),
            min_soc_pct=float(min_soc_pct),
            max_soc_pct=float(max_soc_pct),
            round_trip_efficiency_pct=float(rte_pct),
            enable_generator=bool(enable_generator),
            generator_rated_kw=float(gen_rated_kw),
            generator_min_load_pct=float(gen_min_load_pct),
            fuel_type=str(fuel_type),
            gen_slope_per_kwh=float(gen_slope),
            gen_intercept_per_kw_rated=float(gen_intercept),
            gen_min_runtime_minutes=int(gen_min_runtime_min),
        )
        new_rules_cfg = InteractionRulesConfig(
            rule1_peak_priority=str(rule1_key),
            rule2_battery_strategy=str(rule2_key),
            peak_reserve_soc_pct=float(peak_reserve_soc_pct),
            rule3_charging_sources=str(rule3_key),
        )
        st.session_state["comb_system_cfg"] = new_sys_cfg
        st.session_state["comb_rules_cfg"] = new_rules_cfg

        sim_res = simulate_combined_system_dispatch(
            load_kw=load_kw,
            timestamps=load_series.timestamps,
            system_cfg=new_sys_cfg,
            rules_cfg=new_rules_cfg,
        )
        evaluate_combined_financials(sim_res, st.session_state["comb_fin_cfg"])
        st.session_state["comb_sandbox_result"] = sim_res
        st.session_state.pop("comb_cached_excel_bytes", None)

    sim_res = st.session_state["comb_sandbox_result"]
    kpis = sim_res.kpis
    system_cfg = sim_res.system_config

    # ==================================================================================
    # SECTION 3: Key Results
    # ==================================================================================
    st.markdown("#### :material/speed: 3. Key Results")
    kpi_c1, kpi_c2, kpi_c3, kpi_c4 = st.columns(4)

    with kpi_c1:
        limit_badge = (
            f"Grid Limit ({kpis.grid_limit_kw:,.0f} kW) Met"
            if kpis.grid_limit_met
            else f"Exceeds Limit by {kpis.remaining_overload_kw:,.1f} kW"
        )
        render_kpi_card(
            title="New Grid Peak (kW)",
            value=f"{kpis.original_peak_kw:,.1f} → {kpis.new_grid_peak_kw:,.1f} kW",
            subtext=f"{limit_badge} (-{kpis.peak_reduction_kw:,.1f} kW shaved)",
            status="ok" if kpis.grid_limit_met else "alert",
        )

    with kpi_c2:
        render_kpi_card(
            title="Remaining Overload (hrs / kWh)",
            value=f"{kpis.remaining_overload_hours:,.1f} hrs / {kpis.remaining_overload_kwh:,.0f} kWh",
            subtext=(
                f"0.0 hrs remaining (Before: {kpis.baseline_overload_hours:,.1f} hrs)"
                if kpis.remaining_overload_hours == 0.0
                else f"{kpis.overload_eliminated_pct:.1f}% of {kpis.baseline_overload_hours:,.1f} hrs eliminated"
            ),
            status="ok" if kpis.remaining_overload_hours == 0.0 else "alert",
        )

    with kpi_c3:
        render_kpi_card(
            title="Energy Supply Split (%)",
            value=f"Grid {kpis.grid_supply_share_pct:.0f}% | Solar {kpis.solar_supply_share_pct:.0f}% | Gen {kpis.generator_supply_share_pct:.0f}%",
            subtext=(
                f"Solar Direct: {kpis.solar_direct_share_pct:.1f}% | "
                f"Battery Discharge: {kpis.battery_discharge_share_pct:.1f}%"
            ),
            status="default",
        )

    with kpi_c4:
        render_kpi_card(
            title="Generator Runtime & Fuel",
            value=f"{kpis.generator_runtime_hours:,.1f} hrs | {kpis.generator_fuel_total:,.0f} {kpis.generator_fuel_unit}",
            subtext=(
                f"{kpis.generator_starts_count} starts/yr | Gen output: {kpis.generator_total_generation_kwh:,.0f} kWh"
                if system_cfg.enable_generator
                else "Generator disabled"
            ),
            status="default",
        )

    # ==================================================================================
    # SECTION 4: Power Flow & Data
    # ==================================================================================
    st.write("")
    st.markdown("#### :material/stacked_line_chart: 4. Power Flow & Data")

    with st.container(border=True):
        hdr_d1, hdr_d2, hdr_d3 = st.columns([2.2, 1.3, 1.3])
        with hdr_d1:
            st.markdown("##### :material/timeline: Power Flow & Battery Level")
        with hdr_d2:
            disp_tf = st.segmented_control(
                "Dispatch Window",
                options=["7D", "1M", "3M", "All"],
                default=st.session_state.get("comb_dispatch_timeframe", "7D"),
                key="comb_dispatch_tf_ctrl",
                label_visibility="collapsed",
            )
            if not disp_tf:
                disp_tf = "7D"
            st.session_state["comb_dispatch_timeframe"] = disp_tf
        with hdr_d3:
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

        fig_dispatch = create_combined_dispatch_soc_figure(sim_res=sim_res, timeframe=disp_tf)
        st.plotly_chart(fig_dispatch, use_container_width=True)

    with st.container(border=True):
        st.markdown("##### :material/table_chart: System Overview Table")
        st.dataframe(
            sim_res.summary_table_df,
            use_container_width=True,
            hide_index=True,
        )


# ======================================================================================
# TAB 3: Financials (Dedicated Separate Tab for All Financial Inputs & KPIs)
# ======================================================================================

def render_tab3_financials_view() -> None:
    """
    Renders Tab 3: Financials (Separate Tab for all cost parameters and financial KPIs):
      1. 2x2 Financial Inputs Form (Grid Tariffs, Solar CAPEX/O&M, Battery CAPEX/O&M, Generator Costs)
      2. 4 Financial KPI Cards (Total Investment CAPEX, Annual OPEX, Annual Savings, Payback Years)
      3. Component & Scenario Financial Comparison Table + 12-Month Cost Table
    """
    load_series, _ = _get_active_load_series()
    if "comb_sandbox_result" not in st.session_state:
        sim_res = simulate_combined_system_dispatch(
            load_kw=load_series.power_kw,
            timestamps=load_series.timestamps,
            system_cfg=st.session_state["comb_system_cfg"],
            rules_cfg=st.session_state["comb_rules_cfg"],
        )
        evaluate_combined_financials(sim_res, st.session_state["comb_fin_cfg"])
        st.session_state["comb_sandbox_result"] = sim_res

    sim_res = st.session_state["comb_sandbox_result"]
    cur_fin: CombinedFinancialConfig = st.session_state["comb_fin_cfg"]
    sys_cfg = sim_res.system_config

    with st.form(key="comb_financial_form"):
        st.markdown("#### :material/payments: 1. Financial Inputs (2×2 Cost & Tariff Configuration)")
        f_row1_c1, f_row1_c2 = st.columns(2)

        # --- Financial Tile 1: Grid Tariffs & Overload Penalties ---
        with f_row1_c1:
            with st.container(border=True):
                st.markdown("##### :material/electrical_services: Grid Tariffs & Penalties")
                gt1, gt2 = st.columns(2)
                with gt1:
                    grid_energy_price = st.number_input(
                        "Reference Electricity Price (€/kWh)",
                        min_value=0.01,
                        max_value=2.00,
                        value=float(cur_fin.grid_energy_price_eur_kwh),
                        step=0.01,
                        format="%.3f",
                    )
                    grid_cap_fee = st.number_input(
                        "Network Capacity Charge (€/kW/month)",
                        min_value=0.0,
                        max_value=100.0,
                        value=float(cur_fin.grid_capacity_fee_eur_kw_month),
                        step=0.50,
                    )
                with gt2:
                    grid_fixed_fee = st.number_input(
                        "Monthly Standing Fee (€/month)",
                        min_value=0.0,
                        max_value=10000.0,
                        value=float(cur_fin.grid_fixed_fee_eur_month),
                        step=25.0,
                    )
                    grid_penalty_rate = st.number_input(
                        "Overload Penalty / Breach Rate (€/kW)",
                        min_value=0.0,
                        max_value=500.0,
                        value=float(cur_fin.grid_overload_penalty_eur_kw),
                        step=1.0,
                    )

        # --- Financial Tile 2: Solar Costs ---
        with f_row1_c2:
            with st.container(border=True):
                st.markdown(
                    f"##### :material/solar_power: Solar Costs "
                    f"({'Active: ' + f'{sim_res.solar_derivation.installed_kwp:,.1f} kWp' if sys_cfg.enable_solar else 'Disabled'})"
                )
                sc1, sc2 = st.columns(2)
                with sc1:
                    solar_capex_kwp = st.number_input(
                        "Solar Turnkey CAPEX (€/kWp)",
                        min_value=0.0,
                        max_value=5000.0,
                        value=float(cur_fin.solar_capex_eur_kwp),
                        step=25.0,
                    )
                with sc2:
                    solar_om_pct = st.number_input(
                        "Solar Annual O&M (% of CAPEX)",
                        min_value=0.0,
                        max_value=15.0,
                        value=float(cur_fin.solar_om_pct_of_capex),
                        step=0.25,
                    )

        f_row2_c1, f_row2_c2 = st.columns(2)

        # --- Financial Tile 3: Battery Costs ---
        with f_row2_c1:
            with st.container(border=True):
                st.markdown(
                    f"##### :material/battery_charging_full: Battery Costs "
                    f"({'Active: ' + f'{sys_cfg.battery_capacity_kwh:,.0f} kWh / {sys_cfg.battery_power_kw:,.0f} kW' if sys_cfg.enable_battery else 'Disabled'})"
                )
                bc1, bc2, bc3 = st.columns(3)
                with bc1:
                    bess_capex_kwh = st.number_input(
                        "Energy Pack CAPEX (€/kWh)",
                        min_value=0.0,
                        max_value=3000.0,
                        value=float(cur_fin.battery_capex_eur_kwh),
                        step=25.0,
                    )
                with bc2:
                    bess_capex_kw = st.number_input(
                        "Power / Inverter CAPEX (€/kW)",
                        min_value=0.0,
                        max_value=2000.0,
                        value=float(cur_fin.battery_capex_eur_kw),
                        step=25.0,
                    )
                with bc3:
                    bess_om_pct = st.number_input(
                        "Battery Annual O&M (% of CAPEX)",
                        min_value=0.0,
                        max_value=15.0,
                        value=float(cur_fin.battery_om_pct_of_capex),
                        step=0.25,
                    )

        # --- Financial Tile 4: Generator Costs ---
        with f_row2_c2:
            with st.container(border=True):
                st.markdown(
                    f"##### :material/power: Generator Costs "
                    f"({'Active: ' + f'{sys_cfg.generator_rated_kw:,.0f} kW ({sys_cfg.fuel_type})' if sys_cfg.enable_generator else 'Disabled'})"
                )
                gc1, gc2 = st.columns(2)
                with gc1:
                    gen_cost_model = st.selectbox(
                        "Cost Model",
                        options=["Purchase (CAPEX)", "Rental (OPEX)"],
                        index=0 if cur_fin.generator_cost_model == "Purchase (CAPEX)" else 1,
                    )
                    gen_capex_eur = st.number_input(
                        "Generator Purchase CAPEX (€)",
                        min_value=0.0,
                        max_value=2000000.0,
                        value=float(cur_fin.generator_capex_eur),
                        step=1000.0,
                    )
                    gen_rental_mo = st.number_input(
                        "Generator Rental Fee (€/month)",
                        min_value=0.0,
                        max_value=100000.0,
                        value=float(cur_fin.generator_rental_eur_month),
                        step=100.0,
                    )
                with gc2:
                    fuel_price_unit = st.number_input(
                        f"Fuel Price (€/{sim_res.kpis.generator_fuel_unit})",
                        min_value=0.0,
                        max_value=10.0,
                        value=float(cur_fin.fuel_price_eur_per_unit),
                        step=0.05,
                        format="%.2f",
                    )
                    gen_maint_hr = st.number_input(
                        "Maintenance Cost (€/operating hour)",
                        min_value=0.0,
                        max_value=500.0,
                        value=float(cur_fin.generator_maintenance_eur_per_hour),
                        step=0.50,
                    )

        fin_submitted = st.form_submit_button(
            "Calculate Financials",
            icon=":material/calculate:",
            type="primary",
            use_container_width=True,
        )

    if fin_submitted or sim_res.financial_kpis is None:
        new_fin_cfg = CombinedFinancialConfig(
            grid_energy_price_eur_kwh=float(grid_energy_price),
            grid_capacity_fee_eur_kw_month=float(grid_cap_fee),
            grid_fixed_fee_eur_month=float(grid_fixed_fee),
            grid_overload_penalty_eur_kw=float(grid_penalty_rate),
            solar_capex_eur_kwp=float(solar_capex_kwp),
            solar_om_pct_of_capex=float(solar_om_pct),
            battery_capex_eur_kwh=float(bess_capex_kwh),
            battery_capex_eur_kw=float(bess_capex_kw),
            battery_om_pct_of_capex=float(bess_om_pct),
            generator_cost_model=str(gen_cost_model),
            generator_capex_eur=float(gen_capex_eur),
            generator_rental_eur_month=float(gen_rental_mo),
            fuel_price_eur_per_unit=float(fuel_price_unit),
            generator_maintenance_eur_per_hour=float(gen_maint_hr),
        )
        st.session_state["comb_fin_cfg"] = new_fin_cfg
        evaluate_combined_financials(sim_res, new_fin_cfg)
        st.session_state["comb_sandbox_result"] = sim_res
        st.session_state.pop("comb_cached_excel_bytes", None)
        if fin_submitted:
            st.rerun()

    fin_kpis = sim_res.financial_kpis

    # 4 Financial KPI Cards
    st.markdown("#### :material/account_balance: 2. Financial Results (vs. Current situation)")
    fk1, fk2, fk3, fk4 = st.columns(4)
    with fk1:
        render_kpi_card(
            title="Total Investment (CAPEX)",
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
            title="Annual Operating Costs (OPEX)",
            value=f"€{fin_kpis.total_annual_opex_eur:,.0f} / yr",
            subtext=(
                f"Current situation: €{fin_kpis.baseline_total_opex_eur:,.0f} / yr"
            ),
            status="default",
        )
    with fk3:
        render_kpi_card(
            title="Annual Savings vs. Current situation",
            value=f"€{fin_kpis.annual_savings_eur:,.0f} / yr",
            subtext=(
                f"Net OPEX reduction ({(fin_kpis.annual_savings_eur / max(1.0, fin_kpis.baseline_total_opex_eur) * 100.0):.1f}%)"
            ),
            status="ok" if fin_kpis.annual_savings_eur > 0 else "alert",
        )
    with fk4:
        pb_val = (
            f"{fin_kpis.payback_years:.1f} Years"
            if fin_kpis.payback_years is not None
            else "N/A"
        )
        render_kpi_card(
            title="Payback (Years)",
            value=pb_val,
            subtext="Simple Payback (CAPEX / Annual Savings)",
            status="ok" if (fin_kpis.payback_years is not None and fin_kpis.payback_years <= 10.0) else "default",
        )

    st.write("")
    with st.container(border=True):
        st.markdown("##### :material/table_chart: Component & Scenario Financial Summary Table")
        st.dataframe(
            sim_res.financial_table_df,
            use_container_width=True,
            hide_index=True,
        )

    with st.container(border=True):
        st.markdown("##### :material/calendar_month: 12-Month Cost & Savings Breakdown")
        st.dataframe(
            sim_res.monthly_cost_df,
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

    st.markdown(
        "### :material/hub: Combined system (Grid + Solar + Battery + Generator)"
    )

    tab_consumption, tab_combined, tab_financials = st.tabs(
        [
            ":material/analytics: Consumption",
            ":material/hub: Combined system",
            ":material/payments: Financials",
        ]
    )

    with tab_consumption:
        render_tab1_consumption_view()

    with tab_combined:
        render_tab2_combined_system_view()

    with tab_financials:
        render_tab3_financials_view()


if __name__ == "__main__":
    main()
