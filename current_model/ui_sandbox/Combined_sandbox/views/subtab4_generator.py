"""
Subtab 4: Generator view (Dual-Sizing reference fragment, commercial presets & technical sizing form).
"""

import streamlit as st

from .state_and_helpers import (
    ENGINE_VERSION,
    LoadSeries2025,
    CombinedSystemConfig,
    InteractionRulesConfig,
    DualGeneratorSizingResult,
    FUEL_SPECS,
    compute_dual_generator_sizing,
    _load_fingerprint,
    _rules_tuple,
    _activate_module_callback,
    _apply_gen_quick_size,
)

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
        bool(getattr(cur_sys, "disable_solar_inverter_limit", False)),
        round(float(cur_sys.inverter_efficiency_pct), 2),
        str(getattr(cur_sys, "solar_weather_mode", "single_year")),
        int(getattr(cur_sys, "solar_weather_year", 2025)),
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
                f_spec = FUEL_SPECS.get(cur_sys.fuel_type, FUEL_SPECS["Diesel"])
                cur_sys.gen_slope_per_kwh = float(f_spec["slope_per_kwh"])
                cur_sys.gen_intercept_per_kw_rated = float(f_spec["intercept_per_kw_rated"])
                cur_sys.generator_min_load_pct = float(p_data["min_load"])
                st.session_state["comb_generator_rated_kw_num"] = cur_sys.generator_rated_kw
                st.session_state["comb_generator_fuel_type_select"] = cur_sys.fuel_type
                st.session_state["comb_generator_min_load_num"] = int(round(cur_sys.generator_min_load_pct))
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
            f_spec = FUEL_SPECS.get(cur_sys.fuel_type, FUEL_SPECS["Diesel"])
            cur_sys.gen_slope_per_kwh = float(f_spec["slope_per_kwh"])
            cur_sys.gen_intercept_per_kw_rated = float(f_spec["intercept_per_kw_rated"])
            st.session_state.pop("comb_cached_excel_bytes", None)
