"""
========================================================================================
Combined System Sandbox Application (ui_sandbox/Combined_sandbox/app.py)
========================================================================================

Standalone Execution:
    python -m streamlit run "ui_sandbox/Combined_sandbox/app.py"

Design Standard ("Clean Screen Policy"):
  - Strict Terminology: Consumption, Current situation, Grid, Solar, Battery,
    Generator, Combined system.
  - 2-Tab Layout:
      * Tab 1: Consumption (Baseline)
      * Tab 2: Combined system (Grid + Solar + Battery + Generator)
          - Level 1: System Inputs (4 equal columns side-by-side with Enable checkboxes)
          - Level 2: Interaction & Operating Rules (Rules 1, 2, and 3)
          - Level 3: Key Results (4 Technical KPI Cards)
          - Level 4: Visual Dispatch & Comparison Table (Synchronized 15-min Chart + Summary Table)
  - Phase 1 Scope: Purely physical/technical simulation; stores full `CombinedSimulationResult`
    in `st.session_state["combined_sandbox_result"]` for seamless Phase 2 financial integration.
========================================================================================
"""

import os
import sys
from typing import Tuple
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
    from core.csv_parser import parse_csv_content, detect_suggested_columns
except ImportError:
    from current_model.ui.common.styles import apply_custom_styles
    from current_model.ui.common.cards import render_kpi_card
    from current_model.core.csv_parser import parse_csv_content, detect_suggested_columns

try:
    from ui_sandbox.Currentsituation_sandbox.engine.config_and_models import LoadSeries2025
    from ui_sandbox.Currentsituation_sandbox.engine.consumption_pipeline import (
        normalize_load_profile_2025,
        synthesize_benchmark_load_profile_2025,
    )
except ImportError:
    from current_model.ui_sandbox.Currentsituation_sandbox.engine.config_and_models import LoadSeries2025
    from current_model.ui_sandbox.Currentsituation_sandbox.engine.consumption_pipeline import (
        normalize_load_profile_2025,
        synthesize_benchmark_load_profile_2025,
    )

from ui_sandbox.Combined_sandbox.combined_sandbox_engine import (
    SOLAR_SITE_PRESETS,
    FUEL_SPECS,
    RULE1_OPTIONS,
    RULE2_OPTIONS,
    RULE3_OPTIONS,
    CombinedSystemConfig,
    InteractionRulesConfig,
    get_unit_solar_generation_profile,
    derive_solar_sizing_and_formula,
    simulate_combined_system_dispatch,
)
from ui_sandbox.Combined_sandbox.combined_charts import (
    create_consumption_baseline_figure,
    create_combined_dispatch_soc_figure,
)


BENCHMARK_PROFILES = {
    "Commercial Facility (250 kW Peak)": 250.0,
    "Industrial Facility (430 kW Peak)": 430.0,
    "Thermal / Heat Pump Facility (110 kW Peak)": 110.0,
    "Custom Peak Load (kW)": -1.0,
}


def _init_session_defaults() -> None:
    """Initializes clean default session state values for the Combined System Sandbox."""
    defaults = {
        "comb_load_source_mode": "Benchmark Profile",
        "comb_benchmark_preset": "Commercial Facility (250 kW Peak)",
        "comb_custom_peak_kw": 250.0,
        "comb_tab1_timeframe": "Full Year",
        # Level 1: Grid
        "comb_grid_limit_kw": 180.0,
        # Level 1: Solar
        "comb_enable_solar": True,
        "comb_site_preset": "Netherlands / Rotterdam",
        "comb_custom_lat": 51.9244,
        "comb_custom_lon": 4.4777,
        "comb_solar_sizing_method": "Target Consumption Share (%)",
        "comb_solar_direct_mode": "Solar Size (kWp)",
        "comb_solar_kwp": 150.0,
        "comb_solar_panels": 333,
        "comb_solar_panel_wp": 450.0,
        "comb_solar_target_share_pct": 60.0,
        # Level 1: Battery
        "comb_enable_battery": True,
        "comb_bess_kwh": 300.0,
        "comb_bess_kw": 150.0,
        "comb_bess_min_soc": 10.0,
        "comb_bess_max_soc": 90.0,
        "comb_bess_rte": 88.0,
        # Level 1: Generator
        "comb_enable_generator": True,
        "comb_gen_rated_kw": 100.0,
        "comb_gen_min_load_pct": 25.0,
        "comb_gen_fuel_type": "Diesel",
        # Level 2: Interaction Rules
        "comb_rule1_key": "battery_first",
        "comb_rule2_key": "self_consumption_reserve",
        "comb_peak_reserve_soc_pct": 30.0,
        "comb_rule3_key": "solar_only",
        # Level 4: Dispatch Chart Timeframe
        "comb_dispatch_timeframe": "Peak Week",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _get_active_load_series() -> Tuple[LoadSeries2025, str]:
    """Returns the active 35,040-step LoadSeries2025 and its descriptive label."""
    if (
        "comb_active_load_series" in st.session_state
        and isinstance(st.session_state["comb_active_load_series"], LoadSeries2025)
    ):
        return (
            st.session_state["comb_active_load_series"],
            st.session_state.get("comb_active_load_label", "Benchmark Profile (250 kW Peak)"),
        )

    load_bench = synthesize_benchmark_load_profile_2025(nominal_peak_kw=250.0)
    st.session_state["comb_active_load_series"] = load_bench
    st.session_state["comb_active_load_label"] = "Commercial Facility (250 kW Peak)"
    return load_bench, st.session_state["comb_active_load_label"]


def render_tab1_consumption_view() -> None:
    """
    Renders Tab 1: Consumption (Baseline) reduced strictly to the essentials:
      1. Data source selection (Benchmark Profile or CSV Upload)
      2. 4 Basis-KPIs (Annual Consumption, Maximum Peak Demand, Average Load, Time Resolution)
      3. 1 Interactive 15-Minute Consumption Chart
    """
    with st.container(border=True):
        st.markdown("#### :material/Input: Consumption Data Source")
        col_mode, col_cfg = st.columns([1, 2])

        with col_mode:
            source_mode = st.radio(
                "Select Data Source",
                options=["Benchmark Profile", "CSV Upload"],
                key="comb_load_source_mode",
                horizontal=True,
            )

        with col_cfg:
            if source_mode == "Benchmark Profile":
                b_col1, b_col2, b_col3 = st.columns([2.2, 1.2, 1.0])
                with b_col1:
                    preset_label = st.selectbox(
                        "Facility Benchmark Profile",
                        options=list(BENCHMARK_PROFILES.keys()),
                        key="comb_benchmark_preset",
                    )
                with b_col2:
                    preset_peak = BENCHMARK_PROFILES[preset_label]
                    if preset_peak < 0:
                        target_peak_kw = st.number_input(
                            "Peak Demand (kW)",
                            min_value=10.0,
                            max_value=10000.0,
                            step=10.0,
                            key="comb_custom_peak_kw",
                        )
                    else:
                        target_peak_kw = preset_peak
                        st.metric("Nominal Peak", f"{target_peak_kw:,.0f} kW")
                with b_col3:
                    st.write("")
                    if st.button(
                        "Apply Profile",
                        icon=":material/check_circle:",
                        use_container_width=True,
                        type="primary",
                    ):
                        new_series = synthesize_benchmark_load_profile_2025(nominal_peak_kw=float(target_peak_kw))
                        st.session_state["comb_active_load_series"] = new_series
                        st.session_state["comb_active_load_label"] = (
                            f"{preset_label}" if preset_peak > 0 else f"Custom Benchmark ({target_peak_kw:,.0f} kW Peak)"
                        )
                        st.rerun()
            else:
                uploaded_file = st.file_uploader(
                    "Upload 15-Minute Consumption CSV",
                    type=["csv", "txt"],
                    key="comb_csv_uploader",
                )
                if uploaded_file is not None:
                    raw_bytes = uploaded_file.getvalue()
                    df_parsed, _ = parse_csv_content(raw_bytes, uploaded_file.name)
                    if df_parsed is not None and not df_parsed.empty:
                        suggested = detect_suggested_columns(df_parsed)
                        c_time, c_pow, c_btn = st.columns([1.5, 1.5, 1.0])
                        all_cols = list(df_parsed.columns)
                        default_t_idx = all_cols.index(suggested["time_col"]) if suggested.get("time_col") in all_cols else 0
                        default_p_idx = all_cols.index(suggested["power_col"]) if suggested.get("power_col") in all_cols else min(1, len(all_cols) - 1)
                        with c_time:
                            t_col = st.selectbox("Timestamp Column", options=all_cols, index=default_t_idx, key="comb_csv_tcol")
                        with c_pow:
                            p_col = st.selectbox("Power / Demand Column (kW)", options=all_cols, index=default_p_idx, key="comb_csv_pcol")
                        with c_btn:
                            st.write("")
                            if st.button("Load CSV", icon=":material/upload_file:", use_container_width=True, type="primary"):
                                norm_series, _ = normalize_load_profile_2025(raw_df=df_parsed, power_col=p_col, time_col=t_col)
                                st.session_state["comb_active_load_series"] = norm_series
                                st.session_state["comb_active_load_label"] = f"CSV: {uploaded_file.name}"
                                st.rerun()

    load_series, load_label = _get_active_load_series()
    load_kw = load_series.power_kw
    annual_kwh = float(load_series.total_energy_kwh)
    max_peak_kw = float(load_series.peak_demand_kw)
    avg_load_kw = float(np.mean(load_kw)) if len(load_kw) > 0 else 0.0
    n_steps = len(load_kw)

    # 4 Baseline KPIs
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        render_kpi_card(
            title="Annual Consumption (kWh)",
            value=f"{annual_kwh:,.0f} kWh",
            subtext=f"Source: {load_label}",
            status="default",
        )
    with k2:
        render_kpi_card(
            title="Maximum Peak Demand (kW)",
            value=f"{max_peak_kw:,.1f} kW",
            subtext="Annual 15-minute maximum load",
            status="default",
        )
    with k3:
        render_kpi_card(
            title="Average Load (kW)",
            value=f"{avg_load_kw:,.1f} kW",
            subtext=f"Load factor: {(avg_load_kw / max(0.1, max_peak_kw) * 100.0):.1f}%",
            status="default",
        )
    with k4:
        render_kpi_card(
            title="Time Resolution",
            value=f"15-min / {n_steps:,} steps",
            subtext="Full calendar year (365 days)",
            status="ok",
        )

    st.write("")
    with st.container(border=True):
        tf_col1, tf_col2 = st.columns([3, 1.5])
        with tf_col1:
            st.markdown("#### :material/show_chart: Consumption Profile (15-Minute Resolution)")
        with tf_col2:
            timeframe = st.segmented_control(
                "Timeframe",
                options=["7D", "1M", "Peak Week", "Full Year"],
                default=st.session_state.get("comb_tab1_timeframe", "Full Year"),
                key="comb_tab1_tf_ctrl",
                label_visibility="collapsed",
            )
            if not timeframe:
                timeframe = "Full Year"
            st.session_state["comb_tab1_timeframe"] = timeframe

        fig_load = create_consumption_baseline_figure(
            timestamps=load_series.timestamps,
            load_kw=load_kw,
            timeframe=timeframe,
        )
        st.plotly_chart(fig_load, use_container_width=True)


def render_tab2_combined_system_view() -> None:
    """
    Renders Tab 2: Combined system (Grid + Solar + Battery + Generator)
    in 4 clean vertical levels from top to bottom:
      - Level 1: System Inputs (Grid, Solar, Battery, Generator side-by-side)
      - Level 2: Interaction & Operating Rules (Rules 1, 2, and 3)
      - Level 3: Key Results (4 Technical KPI Cards)
      - Level 4: Visual Dispatch & Comparison Table
    """
    load_series, _ = _get_active_load_series()
    load_kw = load_series.power_kw
    annual_consumption_kwh = float(load_series.total_energy_kwh)
    orig_peak_kw = float(load_series.peak_demand_kw)

    # ==================================================================================
    # LEVEL 1: System Inputs (4 Equal Columns Side-by-Side)
    # ==================================================================================
    st.markdown("#### :material/tune: 1. System Inputs")
    col_grid, col_solar, col_bess, col_gen = st.columns(4)

    # --- COLUMN 1: GRID ---
    with col_grid:
        with st.container(border=True):
            st.markdown("##### :material/electrical_services: Grid")
            st.caption("Utility grid connection & capacity limit")
            grid_limit_kw = st.number_input(
                "Contracted Grid Limit (kW)",
                min_value=10.0,
                max_value=20000.0,
                step=10.0,
                key="comb_grid_limit_kw",
            )
            overload_arr = np.maximum(0.0, load_kw - grid_limit_kw)
            init_overload_kw = float(np.max(overload_arr)) if len(overload_arr) > 0 else 0.0
            init_overload_hrs = float(np.sum(overload_arr > 0.05) * 0.25)
            init_overload_kwh = float(np.sum(overload_arr) * 0.25)

            st.markdown("---")
            st.caption("**Current situation (Grid only):**")
            st.markdown(
                f"- **Consumption:** `{annual_consumption_kwh:,.0f} kWh/yr`\n"
                f"- **Peak Demand:** `{orig_peak_kw:,.1f} kW`\n"
                f"- **Initial Overload:** `{init_overload_kw:,.1f} kW` (`{init_overload_hrs:,.1f} hrs` / `{init_overload_kwh:,.0f} kWh`)"
            )

    # --- COLUMN 2: SOLAR ---
    with col_solar:
        with st.container(border=True):
            hdr_s1, hdr_s2 = st.columns([1.4, 1.0])
            with hdr_s1:
                st.markdown("##### :material/solar_power: Solar")
            with hdr_s2:
                enable_solar = st.checkbox("Enable Solar", key="comb_enable_solar")

            site_options = list(SOLAR_SITE_PRESETS.keys()) + ["Custom GPS"]
            site_preset = st.selectbox(
                "Site / Location",
                options=site_options,
                key="comb_site_preset",
                disabled=not enable_solar,
            )

            if site_preset in SOLAR_SITE_PRESETS:
                site_meta = SOLAR_SITE_PRESETS[site_preset]
                lat = float(site_meta["latitude"])
                lon = float(site_meta["longitude"])
                elev = float(site_meta["elevation_m"])
                tilt = float(site_meta["tilt_deg"])
                azim = float(site_meta["azimuth_deg"])
            else:
                g_c1, g_c2 = st.columns(2)
                with g_c1:
                    lat = st.number_input("Latitude (°)", min_value=-65.0, max_value=65.0, step=0.1, key="comb_custom_lat", disabled=not enable_solar)
                with g_c2:
                    lon = st.number_input("Longitude (°)", min_value=-180.0, max_value=180.0, step=0.1, key="comb_custom_lon", disabled=not enable_solar)
                elev = 100.0
                tilt = 30.0
                azim = 180.0 if lat >= 0.0 else 0.0

            _, spec_yield, _ = get_unit_solar_generation_profile(
                latitude=lat,
                longitude=lon,
                tilt_deg=tilt,
                azimuth_deg=azim,
            )

            # Visible Weather Data Source & Specific Yield Note
            st.caption(
                f"Data source: EU PVGIS (ERA5 TMY, 15-min resolution) | "
                f"Specific Yield: **{spec_yield:,.0f} kWh/kWp/year**"
            )

            sizing_label = st.radio(
                "Sizing Method",
                options=["Target Consumption Share (%)", "Direct kWp / Panels"],
                key="comb_solar_sizing_method",
                horizontal=True,
                disabled=not enable_solar,
            )

            if sizing_label == "Target Consumption Share (%)":
                sizing_method_key = "target_share_pct"
                s_c1, s_c2 = st.columns([1.4, 1.0])
                with s_c1:
                    target_share_pct = st.number_input(
                        "% of Annual Consumption",
                        min_value=5.0,
                        max_value=250.0,
                        step=5.0,
                        key="comb_solar_target_share_pct",
                        disabled=not enable_solar,
                    )
                with s_c2:
                    panel_wp = st.number_input(
                        "Wp per Panel",
                        min_value=250.0,
                        max_value=750.0,
                        step=10.0,
                        key="comb_solar_panel_wp",
                        disabled=not enable_solar,
                    )
                direct_kwp_val = st.session_state.get("comb_solar_kwp", 150.0)
            else:
                sizing_method_key = "direct_kwp"
                target_share_pct = st.session_state.get("comb_solar_target_share_pct", 60.0)
                d_mode = st.selectbox(
                    "Direct Input Mode",
                    options=["Solar Size (kWp)", "Number of Panels × Wp"],
                    key="comb_solar_direct_mode",
                    disabled=not enable_solar,
                )
                if d_mode == "Solar Size (kWp)":
                    d_c1, d_c2 = st.columns([1.4, 1.0])
                    with d_c1:
                        direct_kwp_val = st.number_input(
                            "Solar Size (kWp)",
                            min_value=1.0,
                            max_value=20000.0,
                            step=10.0,
                            key="comb_solar_kwp",
                            disabled=not enable_solar,
                        )
                    with d_c2:
                        panel_wp = st.number_input(
                            "Wp per Panel",
                            min_value=250.0,
                            max_value=750.0,
                            step=10.0,
                            key="comb_solar_panel_wp",
                            disabled=not enable_solar,
                        )
                else:
                    d_c1, d_c2 = st.columns([1.3, 1.1])
                    with d_c1:
                        n_panels = st.number_input(
                            "Number of Panels",
                            min_value=1,
                            max_value=50000,
                            step=10,
                            key="comb_solar_panels",
                            disabled=not enable_solar,
                        )
                    with d_c2:
                        panel_wp = st.number_input(
                            "Wp per Panel",
                            min_value=250.0,
                            max_value=750.0,
                            step=10.0,
                            key="comb_solar_panel_wp",
                            disabled=not enable_solar,
                        )
                    direct_kwp_val = round((float(n_panels) * float(panel_wp)) / 1000.0, 1)

            solar_deriv_preview = derive_solar_sizing_and_formula(
                annual_consumption_kwh=annual_consumption_kwh,
                specific_yield_kwh_per_kwp=spec_yield,
                sizing_method=sizing_method_key,
                direct_kwp=float(direct_kwp_val),
                target_share_pct=float(target_share_pct),
                panel_wp=float(panel_wp),
                enable_solar=enable_solar,
            )
            st.info(solar_deriv_preview.formula_text, icon=":material/calculate:")

    # --- COLUMN 3: BATTERY ---
    with col_bess:
        with st.container(border=True):
            hdr_b1, hdr_b2 = st.columns([1.3, 1.1])
            with hdr_b1:
                st.markdown("##### :material/battery_charging_full: Battery")
            with hdr_b2:
                enable_battery = st.checkbox("Enable Battery", key="comb_enable_battery")

            bess_kwh = st.number_input(
                "Battery Capacity (kWh)",
                min_value=10.0,
                max_value=50000.0,
                step=25.0,
                key="comb_bess_kwh",
                disabled=not enable_battery,
            )
            bess_kw = st.number_input(
                "Battery Power (kW)",
                min_value=5.0,
                max_value=25000.0,
                step=10.0,
                key="comb_bess_kw",
                disabled=not enable_battery,
            )

            s_col1, s_col2, s_col3 = st.columns(3)
            with s_col1:
                min_soc_pct = st.number_input(
                    "Min SoC (%)",
                    min_value=0.0,
                    max_value=50.0,
                    step=5.0,
                    key="comb_bess_min_soc",
                    disabled=not enable_battery,
                )
            with s_col2:
                max_soc_pct = st.number_input(
                    "Max SoC (%)",
                    min_value=55.0,
                    max_value=100.0,
                    step=5.0,
                    key="comb_bess_max_soc",
                    disabled=not enable_battery,
                )
            with s_col3:
                rte_pct = st.number_input(
                    "Efficiency (%)",
                    min_value=60.0,
                    max_value=100.0,
                    step=1.0,
                    key="comb_bess_rte",
                    disabled=not enable_battery,
                )

            usable_kwh = bess_kwh * max(0.0, (max_soc_pct - min_soc_pct) / 100.0)
            c_rate = (bess_kw / max(1.0, bess_kwh)) if bess_kwh > 0 else 0.0
            st.caption(
                f"Usable Window: **{usable_kwh:,.0f} kWh** ({min_soc_pct:.0f}%–{max_soc_pct:.0f}% SoC) | "
                f"C-Rate: **{c_rate:.2f}C** | Round-Trip: **{rte_pct:.0f}%**"
            )

    # --- COLUMN 4: GENERATOR ---
    with col_gen:
        with st.container(border=True):
            hdr_g1, hdr_g2 = st.columns([1.3, 1.1])
            with hdr_g1:
                st.markdown("##### :material/power: Generator")
            with hdr_g2:
                enable_generator = st.checkbox("Enable Generator", key="comb_enable_generator")

            gen_rated_kw = st.number_input(
                "Generator Rated Power (kW)",
                min_value=10.0,
                max_value=20000.0,
                step=25.0,
                key="comb_gen_rated_kw",
                disabled=not enable_generator,
            )
            gen_min_load_pct = st.number_input(
                "Minimum Load (%) — Wet-Stacking Limit",
                min_value=0.0,
                max_value=80.0,
                step=5.0,
                key="comb_gen_min_load_pct",
                disabled=not enable_generator,
            )
            fuel_type = st.selectbox(
                "Fuel Type",
                options=list(FUEL_SPECS.keys()),
                key="comb_gen_fuel_type",
                disabled=not enable_generator,
            )

            min_gen_kw = gen_rated_kw * (gen_min_load_pct / 100.0)
            f_spec = FUEL_SPECS[fuel_type]
            st.caption(
                f"Min Active Output: **{min_gen_kw:,.1f} kW** ({gen_min_load_pct:.0f}%) | "
                f"Fuel Unit: **{f_spec['unit']}** ({fuel_type})"
            )

    # ==================================================================================
    # LEVEL 2: Interaction & Operating Rules (Horizontal 3-Column Bar)
    # ==================================================================================
    st.markdown("#### :material/rule: 2. Interaction & Operating Rules")
    with st.container(border=True):
        r_col1, r_col2, r_col3 = st.columns(3)

        with r_col1:
            rule1_key = st.selectbox(
                "Rule 1 – Peak Shaving Priority (Above Grid Limit)",
                options=list(RULE1_OPTIONS.keys()),
                format_func=lambda k: RULE1_OPTIONS[k],
                key="comb_rule1_key",
            )

        with r_col2:
            rule2_key = st.selectbox(
                "Rule 2 – Battery Usage Strategy (Below Grid Limit)",
                options=list(RULE2_OPTIONS.keys()),
                format_func=lambda k: RULE2_OPTIONS[k],
                key="comb_rule2_key",
            )
            if rule2_key == "self_consumption_reserve":
                peak_reserve_soc_pct = st.slider(
                    "Peak Reserve SoC (%) held strictly for peaks above Grid Limit",
                    min_value=int(min_soc_pct),
                    max_value=int(max_soc_pct),
                    value=int(np.clip(st.session_state.get("comb_peak_reserve_soc_pct", 30.0), min_soc_pct, max_soc_pct)),
                    step=5,
                    key="comb_reserve_slider",
                )
                st.session_state["comb_peak_reserve_soc_pct"] = float(peak_reserve_soc_pct)
            else:
                peak_reserve_soc_pct = float(st.session_state.get("comb_peak_reserve_soc_pct", 30.0))

        with r_col3:
            rule3_key = st.selectbox(
                "Rule 3 – Battery Charging Sources",
                options=list(RULE3_OPTIONS.keys()),
                format_func=lambda k: RULE3_OPTIONS[k],
                key="comb_rule3_key",
            )

    # ==================================================================================
    # RUN 35,040-STEP SIMULATION
    # ==================================================================================
    system_cfg = CombinedSystemConfig(
        grid_limit_kw=float(grid_limit_kw),
        enable_solar=bool(enable_solar),
        site_preset=str(site_preset),
        latitude=float(lat),
        longitude=float(lon),
        elevation_m=float(elev),
        tilt_deg=float(tilt),
        azimuth_deg=float(azim),
        solar_sizing_method=sizing_method_key,
        solar_kwp=float(solar_deriv_preview.installed_kwp),
        panel_wp=float(panel_wp),
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
    )

    rules_cfg = InteractionRulesConfig(
        rule1_peak_priority=str(rule1_key),
        rule2_battery_strategy=str(rule2_key),
        peak_reserve_soc_pct=float(peak_reserve_soc_pct),
        rule3_charging_sources=str(rule3_key),
    )

    sim_res = simulate_combined_system_dispatch(
        load_kw=load_kw,
        timestamps=load_series.timestamps,
        system_cfg=system_cfg,
        rules_cfg=rules_cfg,
    )

    # Store full result in session_state for seamless Phase 2 Financial Integration
    st.session_state["combined_sandbox_result"] = sim_res
    kpis = sim_res.kpis

    # ==================================================================================
    # LEVEL 3: Key Results (4 Technical KPI Cards)
    # ==================================================================================
    st.markdown("#### :material/speed: 3. Key Results (Technical)")
    kpi_c1, kpi_c2, kpi_c3, kpi_c4 = st.columns(4)

    with kpi_c1:
        limit_badge = (
            f"Grid Limit ({kpis.grid_limit_kw:,.0f} kW) Met"
            if kpis.grid_limit_met
            else f"Exceeds Limit by {kpis.remaining_overload_kw:,.1f} kW"
        )
        render_kpi_card(
            title="Grid Peak Demand (kW)",
            value=f"{kpis.original_peak_kw:,.1f} → {kpis.new_grid_peak_kw:,.1f} kW",
            subtext=f"{limit_badge} (-{kpis.peak_reduction_kw:,.1f} kW shaved)",
            status="ok" if kpis.grid_limit_met else "alert",
        )

    with kpi_c2:
        render_kpi_card(
            title="Remaining Unmet Overload",
            value=f"{kpis.remaining_overload_hours:,.1f} hrs / {kpis.remaining_overload_kwh:,.0f} kWh",
            subtext=(
                f"100% bottleneck solved (Before: {kpis.baseline_overload_hours:,.1f} hrs)"
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
    # LEVEL 4: Visual Dispatch & Comparison Table
    # ==================================================================================
    st.write("")
    st.markdown("#### :material/stacked_line_chart: 4. Visual Dispatch & Comparison Table")

    with st.container(border=True):
        hdr_d1, hdr_d2 = st.columns([3.0, 1.5])
        with hdr_d1:
            st.markdown("##### :material/timeline: Synchronized 15-Minute Dispatch & Battery SoC")
        with hdr_d2:
            disp_tf = st.segmented_control(
                "Dispatch Window",
                options=["7D", "1M", "Peak Week", "Full Year"],
                default=st.session_state.get("comb_dispatch_timeframe", "Peak Week"),
                key="comb_dispatch_tf_ctrl",
                label_visibility="collapsed",
            )
            if not disp_tf:
                disp_tf = "Peak Week"
            st.session_state["comb_dispatch_timeframe"] = disp_tf

        fig_dispatch = create_combined_dispatch_soc_figure(sim_res=sim_res, timeframe=disp_tf)
        st.plotly_chart(fig_dispatch, use_container_width=True)

    with st.container(border=True):
        st.markdown("##### :material/table_chart: Component & Scenario Summary Table")
        st.dataframe(
            sim_res.summary_table_df,
            use_container_width=True,
            hide_index=True,
        )


def main() -> None:
    st.set_page_config(
        page_title="Combined System Sandbox — Grid + Solar + Battery + Generator",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    apply_custom_styles()
    _init_session_defaults()

    st.markdown(
        "### :material/hub: Combined System Workbench (`Grid + Solar + Battery + Generator`)"
    )

    tab_consumption, tab_combined = st.tabs(
        [
            ":material/analytics: Consumption",
            ":material/hub: Combined system",
        ]
    )

    with tab_consumption:
        render_tab1_consumption_view()

    with tab_combined:
        render_tab2_combined_system_view()


if __name__ == "__main__":
    main()

