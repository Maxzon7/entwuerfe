"""
========================================================================================
DRAC White-Green Design Blueprint Sandbox (ui_sandbox/Design_sandbox/app.py)
========================================================================================

Standalone Execution:
    python -m streamlit run "ui_sandbox/Design_sandbox/app.py" --theme.base light --theme.primaryColor "#7a9f48"

Purpose:
    Design-language blueprint built on the white-and-green DRAC PDF Feasibility Study
    identity (`#7a9f48` brand green, crisp white surfaces, slate typography, and the
    official DRAC Green Energy Solutions logo), featuring an EN (default) / NL / ES
    UI language switcher. Reuses live 15-minute simulation engines, benchmark profiles,
    and Plotly chart builders from `Combined_sandbox` and `Currentsituation_sandbox`
    without modifying any production or Combined Sandbox files.
========================================================================================
"""

from dataclasses import replace
import os
import sys
import time
from typing import Any, Dict, List, Tuple

import streamlit as st

_CURRENT_DIR = os.path.abspath(os.path.dirname(__file__))
_UI_SANDBOX_DIR = os.path.abspath(os.path.join(_CURRENT_DIR, ".."))
_PROJECT_ROOT = os.path.abspath(os.path.join(_UI_SANDBOX_DIR, ".."))
_WORKSPACE_DIR = os.path.abspath(os.path.join(_PROJECT_ROOT, ".."))
for _p in (_WORKSPACE_DIR, _PROJECT_ROOT, _UI_SANDBOX_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from ui_sandbox.Currentsituation_sandbox.engine.consumption_pipeline import (
        synthesize_benchmark_load_profile_2025,
    )
    from ui_sandbox.Combined_sandbox.combined_sandbox_engine import (
        RULE1_OPTIONS,
        RULE2_OPTIONS,
        RULE3_OPTIONS,
        SOLAR_SITE_PRESETS,
        CombinedFinancialConfig,
        CombinedSimulationResult,
        CombinedSystemConfig,
        InteractionRulesConfig,
        apply_utility_tariff_presets,
        compute_system_utilization_diagnostics,
        evaluate_combined_financials,
        fmt_curr,
        fmt_num,
        format_currency_value,
        simulate_combined_system_dispatch,
    )
    from ui_sandbox.Combined_sandbox.combined_charts import (
        create_combined_dispatch_soc_figure,
        create_component_utilization_bars_figure,
        create_financial_tco_trajectory_figure,
        create_financial_waterfall_bridge_figure,
        create_supply_mix_pie_figure,
    )
    from ui_sandbox.Design_sandbox.i18n import (
        DEFAULT_LANGUAGE,
        LANGUAGE_FULL_NAMES,
        LANGUAGE_LABELS,
        SUPPORTED_LANGUAGES,
        t,
    )
    from ui_sandbox.Design_sandbox.theme import (
        DRAC_PALETTE,
        apply_drac_light_chart_theme,
        drac_loading_overlay,
        get_drac_logo_data_uri,
        get_drac_watermark_data_uri,
        inject_drac_light_theme,
        render_drac_cost_bridge_bar,
        render_drac_footer,
        render_drac_kpi_card,
        render_drac_masthead,
        render_drac_table_html,
        render_module_pills,
        render_section_heading,
        render_status_banner,
    )
except ImportError:
    from current_model.ui_sandbox.Currentsituation_sandbox.engine.consumption_pipeline import (
        synthesize_benchmark_load_profile_2025,
    )
    from current_model.ui_sandbox.Combined_sandbox.combined_sandbox_engine import (
        RULE1_OPTIONS,
        RULE2_OPTIONS,
        RULE3_OPTIONS,
        SOLAR_SITE_PRESETS,
        CombinedFinancialConfig,
        CombinedSimulationResult,
        CombinedSystemConfig,
        InteractionRulesConfig,
        apply_utility_tariff_presets,
        compute_system_utilization_diagnostics,
        evaluate_combined_financials,
        fmt_curr,
        fmt_num,
        format_currency_value,
        simulate_combined_system_dispatch,
    )
    from current_model.ui_sandbox.Combined_sandbox.combined_charts import (
        create_combined_dispatch_soc_figure,
        create_component_utilization_bars_figure,
        create_financial_tco_trajectory_figure,
        create_financial_waterfall_bridge_figure,
        create_supply_mix_pie_figure,
    )
    from current_model.ui_sandbox.Design_sandbox.i18n import (
        DEFAULT_LANGUAGE,
        LANGUAGE_FULL_NAMES,
        LANGUAGE_LABELS,
        SUPPORTED_LANGUAGES,
        t,
    )
    from current_model.ui_sandbox.Design_sandbox.theme import (
        DRAC_PALETTE,
        apply_drac_light_chart_theme,
        drac_loading_overlay,
        get_drac_logo_data_uri,
        get_drac_watermark_data_uri,
        inject_drac_light_theme,
        render_drac_cost_bridge_bar,
        render_drac_footer,
        render_drac_kpi_card,
        render_drac_masthead,
        render_drac_table_html,
        render_module_pills,
        render_section_heading,
        render_status_banner,
    )


BLUEPRINT_SCENARIOS: Dict[str, Dict[str, Any]] = {
    "bakery": {
        "scen_key": "scen_bakery",
        "site_key": "site_bakery",
        "profile_type": "commercial_hvac",
        "nominal_peak_kw": 250.0,
        "grid_limit_kw": 180.0,
        "solar_share_pct": 60.0,
        "bess_kwh": 300.0,
        "bess_kw": 150.0,
        "gen_kw": 100.0,
        "dso_name": "Enexis Netbeheer B.V.",
        "dso_tier": "MV-D (125 to 1,500 kW)",
    },
    "rotterdam": {
        "scen_key": "scen_rotterdam",
        "site_key": "site_rotterdam",
        "profile_type": "commercial_hvac",
        "nominal_peak_kw": 110.0,
        "grid_limit_kw": 75.0,
        "solar_share_pct": 50.0,
        "bess_kwh": 160.0,
        "bess_kw": 80.0,
        "gen_kw": 50.0,
        "dso_name": "Stedin Netbeheer B.V.",
        "dso_tier": "Transformer MV/LV (> 50 to 125 kW)",
    },
    "logistics": {
        "scen_key": "scen_logistics",
        "site_key": "site_logistics",
        "profile_type": "commercial_hvac",
        "nominal_peak_kw": 550.0,
        "grid_limit_kw": 380.0,
        "solar_share_pct": 45.0,
        "bess_kwh": 650.0,
        "bess_kw": 300.0,
        "gen_kw": 200.0,
        "dso_name": "Liander Netbeheer B.V.",
        "dso_tier": "MV-D (125 to 1,500 kW)",
    },
}

DEFAULT_SCENARIO_KEY = "bakery"


@st.cache_data(show_spinner=False)
def _load_blueprint_profile(profile_type: str, nominal_peak_kw: float):
    """Synthesizes and caches the 35,040-step 15-minute benchmark load profile."""
    return synthesize_benchmark_load_profile_2025(
        profile_type=profile_type,
        nominal_peak_kw=float(nominal_peak_kw),
    )


def _apply_scenario_to_state(scenario_key: str) -> None:
    """Populates `design_*` configs and widget keys from a blueprint scenario preset."""
    safe_key = scenario_key if scenario_key in BLUEPRINT_SCENARIOS else DEFAULT_SCENARIO_KEY
    spec = BLUEPRINT_SCENARIOS[safe_key]
    sys_cfg = CombinedSystemConfig(
        enable_grid=True,
        grid_limit_kw=float(spec["grid_limit_kw"]),
        enable_solar=True,
        enable_battery=True,
        enable_generator=False,
        enable_financials=True,
        solar_sizing_method="target_share_pct",
        target_consumption_share_pct=float(spec["solar_share_pct"]),
        battery_capacity_kwh=float(spec["bess_kwh"]),
        battery_power_kw=float(spec["bess_kw"]),
        generator_rated_kw=float(spec["gen_kw"]),
    )
    rules_cfg = InteractionRulesConfig()
    fin_cfg = apply_utility_tariff_presets(
        dso_choice=spec["dso_name"],
        tier_choice=spec["dso_tier"],
        supp_choice="Vattenfall Business",
        supp_plan="Fixed 1-Year (Dual TOU HT/NT)",
        meter_choice="Fudura B.V.",
        meter_tier="15-Min Interval Telemetry MV (Large Consumer)",
        fin_cfg=CombinedFinancialConfig(),
    )
    st.session_state["design_scenario_key"] = safe_key
    st.session_state["design_scenario_select"] = safe_key
    st.session_state["design_sys_cfg"] = sys_cfg
    st.session_state["design_rules_cfg"] = rules_cfg
    st.session_state["design_fin_cfg"] = fin_cfg

    st.session_state["design_grid_limit_w"] = float(sys_cfg.grid_limit_kw)
    st.session_state["design_en_solar_w"] = bool(sys_cfg.enable_solar)
    st.session_state["design_en_battery_w"] = bool(sys_cfg.enable_battery)
    st.session_state["design_en_generator_w"] = bool(sys_cfg.enable_generator)
    st.session_state["design_en_financials_w"] = bool(sys_cfg.enable_financials)

    site_names = list(SOLAR_SITE_PRESETS.keys())
    st.session_state["design_cfg_site"] = (
        sys_cfg.site_preset if sys_cfg.site_preset in site_names else site_names[0]
    )
    st.session_state["design_cfg_sol_share"] = float(sys_cfg.target_consumption_share_pct)
    st.session_state["design_cfg_tilt"] = float(sys_cfg.tilt_deg)
    st.session_state["design_cfg_gen_kw"] = float(sys_cfg.generator_rated_kw)
    st.session_state["design_cfg_fuel"] = str(sys_cfg.fuel_type)
    st.session_state["design_cfg_gen_min"] = float(sys_cfg.generator_min_load_pct)
    st.session_state["design_cfg_bess_kwh"] = float(sys_cfg.battery_capacity_kwh)
    st.session_state["design_cfg_bess_kw"] = float(sys_cfg.battery_power_kw)
    st.session_state["design_cfg_soc_range"] = (
        float(sys_cfg.min_soc_pct),
        float(sys_cfg.max_soc_pct),
    )
    st.session_state["design_cfg_rte"] = float(sys_cfg.round_trip_efficiency_pct)
    st.session_state["design_cfg_r1"] = str(rules_cfg.rule1_peak_priority)
    st.session_state["design_cfg_r2"] = str(rules_cfg.rule2_battery_strategy)
    st.session_state["design_cfg_r3"] = str(rules_cfg.rule3_charging_sources)
    st.session_state.pop("design_sim_cache", None)


def _init_blueprint_state() -> None:
    """Initializes session state defaults for the DRAC design blueprint."""
    if st.session_state.get("design_lang") not in SUPPORTED_LANGUAGES:
        st.session_state["design_lang"] = DEFAULT_LANGUAGE
    if st.session_state.get("design_header_variant") not in ("white_stationery", "soft_sage", "solid_green"):
        st.session_state["design_header_variant"] = "white_stationery"
    if st.session_state.get("design_density") not in ("executive", "compact"):
        st.session_state["design_density"] = "executive"
    if st.session_state.get("design_table_tone") not in ("slate", "green"):
        st.session_state["design_table_tone"] = "slate"
    if "design_show_watermark" not in st.session_state:
        st.session_state["design_show_watermark"] = False

    if "design_sys_cfg" not in st.session_state:
        _apply_scenario_to_state(DEFAULT_SCENARIO_KEY)
    elif "design_cfg_site" not in st.session_state:
        cur_sys: CombinedSystemConfig = st.session_state["design_sys_cfg"]
        cur_rules: InteractionRulesConfig = st.session_state["design_rules_cfg"]
        site_names = list(SOLAR_SITE_PRESETS.keys())
        st.session_state["design_cfg_site"] = (
            cur_sys.site_preset if cur_sys.site_preset in site_names else site_names[0]
        )
        st.session_state["design_cfg_sol_share"] = float(cur_sys.target_consumption_share_pct)
        st.session_state["design_cfg_tilt"] = float(cur_sys.tilt_deg)
        st.session_state["design_cfg_gen_kw"] = float(cur_sys.generator_rated_kw)
        st.session_state["design_cfg_fuel"] = str(cur_sys.fuel_type)
        st.session_state["design_cfg_gen_min"] = float(cur_sys.generator_min_load_pct)
        st.session_state["design_cfg_bess_kwh"] = float(cur_sys.battery_capacity_kwh)
        st.session_state["design_cfg_bess_kw"] = float(cur_sys.battery_power_kw)
        st.session_state["design_cfg_soc_range"] = (
            float(cur_sys.min_soc_pct),
            float(cur_sys.max_soc_pct),
        )
        st.session_state["design_cfg_rte"] = float(cur_sys.round_trip_efficiency_pct)
        st.session_state["design_cfg_r1"] = str(cur_rules.rule1_peak_priority)
        st.session_state["design_cfg_r2"] = str(cur_rules.rule2_battery_strategy)
        st.session_state["design_cfg_r3"] = str(cur_rules.rule3_charging_sources)


def _set_language(lang_code: str) -> None:
    """Callback switching the active UI language (`en`, `nl`, or `es`)."""
    st.session_state["design_lang"] = (
        lang_code if lang_code in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
    )


def _on_scenario_change() -> None:
    """Callback switching the active demo scenario."""
    chosen = st.session_state.get("design_scenario_select", DEFAULT_SCENARIO_KEY)
    _apply_scenario_to_state(chosen)


def _reset_blueprint_defaults() -> None:
    """Callback restoring initial language, scenario, and design variant selections."""
    st.session_state["design_lang"] = DEFAULT_LANGUAGE
    st.session_state["design_header_variant"] = "white_stationery"
    st.session_state["design_density"] = "executive"
    st.session_state["design_table_tone"] = "slate"
    st.session_state["design_show_watermark"] = False
    _apply_scenario_to_state(DEFAULT_SCENARIO_KEY)


def _apply_mix_preset(solar: bool, battery: bool, generator: bool) -> None:
    """Callback for Tab 2 quick system-mix preset buttons."""
    cfg: CombinedSystemConfig = st.session_state["design_sys_cfg"]
    cfg.enable_solar = bool(solar)
    cfg.enable_battery = bool(battery)
    cfg.enable_generator = bool(generator)
    st.session_state["design_en_solar_w"] = bool(solar)
    st.session_state["design_en_battery_w"] = bool(battery)
    st.session_state["design_en_generator_w"] = bool(generator)


def _enable_financials_cb() -> None:
    """Callback enabling financials from Tab 3 callout."""
    cfg: CombinedSystemConfig = st.session_state["design_sys_cfg"]
    cfg.enable_financials = True
    st.session_state["design_en_financials_w"] = True


def _apply_config_form_cb() -> None:
    """Single-pass callback applying Tab 2 form values before simulation runs."""
    cur_sys: CombinedSystemConfig = st.session_state["design_sys_cfg"]
    cur_rules: InteractionRulesConfig = st.session_state["design_rules_cfg"]
    site_sel = str(st.session_state.get("design_cfg_site", cur_sys.site_preset))
    if site_sel in SOLAR_SITE_PRESETS:
        site_info = SOLAR_SITE_PRESETS[site_sel]
        cur_sys.site_preset = site_sel
        cur_sys.latitude = float(site_info["latitude"])
        cur_sys.longitude = float(site_info["longitude"])
        cur_sys.azimuth_deg = float(site_info["azimuth_deg"])

    cur_sys.tilt_deg = float(st.session_state.get("design_cfg_tilt", cur_sys.tilt_deg))
    cur_sys.target_consumption_share_pct = float(
        st.session_state.get("design_cfg_sol_share", cur_sys.target_consumption_share_pct)
    )
    cur_sys.battery_capacity_kwh = float(
        st.session_state.get("design_cfg_bess_kwh", cur_sys.battery_capacity_kwh)
    )
    cur_sys.battery_power_kw = float(
        st.session_state.get("design_cfg_bess_kw", cur_sys.battery_power_kw)
    )
    soc_rng = st.session_state.get(
        "design_cfg_soc_range",
        (cur_sys.min_soc_pct, cur_sys.max_soc_pct),
    )
    cur_sys.min_soc_pct = float(soc_rng[0])
    cur_sys.max_soc_pct = float(soc_rng[1])
    cur_sys.round_trip_efficiency_pct = float(
        st.session_state.get("design_cfg_rte", cur_sys.round_trip_efficiency_pct)
    )
    cur_sys.generator_rated_kw = float(
        st.session_state.get("design_cfg_gen_kw", cur_sys.generator_rated_kw)
    )
    cur_sys.fuel_type = str(st.session_state.get("design_cfg_fuel", cur_sys.fuel_type))
    cur_sys.generator_min_load_pct = float(
        st.session_state.get("design_cfg_gen_min", cur_sys.generator_min_load_pct)
    )
    cur_rules.rule1_peak_priority = str(
        st.session_state.get("design_cfg_r1", cur_rules.rule1_peak_priority)
    )
    cur_rules.rule2_battery_strategy = str(
        st.session_state.get("design_cfg_r2", cur_rules.rule2_battery_strategy)
    )
    cur_rules.rule3_charging_sources = str(
        st.session_state.get("design_cfg_r3", cur_rules.rule3_charging_sources)
    )


def _sync_control_ribbon_to_sys(cur_sys: CombinedSystemConfig) -> None:
    """Syncs top control ribbon widget keys into `cur_sys` ahead of simulation."""
    if "design_grid_limit_w" in st.session_state:
        cur_sys.grid_limit_kw = float(st.session_state["design_grid_limit_w"])
    if "design_en_solar_w" in st.session_state:
        cur_sys.enable_solar = bool(st.session_state["design_en_solar_w"])
    if "design_en_battery_w" in st.session_state:
        cur_sys.enable_battery = bool(st.session_state["design_en_battery_w"])
    if "design_en_generator_w" in st.session_state:
        cur_sys.enable_generator = bool(st.session_state["design_en_generator_w"])
    if "design_en_financials_w" in st.session_state:
        cur_sys.enable_financials = bool(st.session_state["design_en_financials_w"])


def _sim_fingerprint(
    scenario_key: str,
    sys_cfg: CombinedSystemConfig,
    rules_cfg: InteractionRulesConfig,
) -> Tuple:
    """Builds an immutable cache key so style or language changes never re-run physics."""
    return (
        scenario_key,
        round(float(sys_cfg.grid_limit_kw), 2),
        bool(sys_cfg.enable_solar),
        round(float(sys_cfg.latitude), 4),
        round(float(sys_cfg.longitude), 4),
        round(float(sys_cfg.tilt_deg), 2),
        round(float(sys_cfg.azimuth_deg), 2),
        round(float(sys_cfg.target_consumption_share_pct), 2),
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
        rules_cfg.rule1_peak_priority,
        rules_cfg.rule2_battery_strategy,
        round(float(rules_cfg.peak_reserve_soc_pct), 2),
        rules_cfg.rule3_charging_sources,
        bool(sys_cfg.enable_financials),
    )


def _get_cached_simulation(
    scenario_key: str,
    load_series: Any,
    sys_cfg: CombinedSystemConfig,
    rules_cfg: InteractionRulesConfig,
    fin_cfg: CombinedFinancialConfig,
    lang: str = DEFAULT_LANGUAGE,
) -> CombinedSimulationResult:
    """Runs or retrieves cached Combined Sandbox 15-minute simulation & financials."""
    fp = _sim_fingerprint(scenario_key, sys_cfg, rules_cfg)
    cache = st.session_state.get("design_sim_cache")
    if isinstance(cache, dict) and cache.get("fp") == fp and "sim_res" in cache:
        return cache["sim_res"]

    with drac_loading_overlay(
        message=t("loader_calculating", lang),
        subtext=t("loader_subtext", lang),
    ):
        sim_res = simulate_combined_system_dispatch(
            load_kw=load_series.power_kw,
            timestamps=load_series.timestamps,
            system_cfg=replace(sys_cfg),
            rules_cfg=replace(rules_cfg),
            is_gap=getattr(load_series, "is_gap", None),
        )
        if sys_cfg.enable_financials:
            evaluate_combined_financials(sim_res, replace(fin_cfg))

    st.session_state["design_sim_cache"] = {"fp": fp, "sim_res": sim_res}
    return sim_res


def _render_top_language_bar(lang: str) -> None:
    """Renders a compact EN / NL / ES language switcher right above the masthead."""
    cols = st.columns([4.15, 0.75, 0.48, 0.48, 0.48])
    with cols[1]:
        st.markdown(
            '<div style="text-align:right; padding-top:7px; font-size:0.80rem; '
            f'font-weight:700; color:#5d7c34;">{t("lang_label", lang)}:</div>',
            unsafe_allow_html=True,
        )
    for idx, code in enumerate(SUPPORTED_LANGUAGES):
        with cols[idx + 2]:
            st.button(
                LANGUAGE_LABELS[code],
                key=f"top_lang_{code}",
                type="primary" if lang == code else "secondary",
                use_container_width=True,
                help=LANGUAGE_FULL_NAMES[code],
                on_click=_set_language,
                args=(code,),
            )


def _render_sidebar(lang: str) -> Tuple[str, str, str, bool]:
    """Renders the Design Studio sidebar and returns active visual variant settings."""
    logo_uri = get_drac_logo_data_uri()
    with st.sidebar:
        st.markdown(
            '<div style="padding:6px 4px 10px 4px; border-bottom:1px solid #dce3d8; margin-bottom:10px;">'
            f'<img src="{logo_uri}" alt="DRAC Logo" style="height:44px; width:auto; display:block; margin-bottom:6px;">'
            '<div style="font-size:0.74rem; font-weight:700; color:#5d7c34; letter-spacing:0.05em; text-transform:uppercase;">'
            f'{t("sb_studio_title", lang)}</div>'
            "</div>",
            unsafe_allow_html=True,
        )

        st.markdown(f"##### :material/language: {t('lang_label', lang)}")
        sb_lang_cols = st.columns(3)
        for idx, code in enumerate(SUPPORTED_LANGUAGES):
            with sb_lang_cols[idx]:
                st.button(
                    LANGUAGE_LABELS[code],
                    key=f"sb_lang_{code}",
                    type="primary" if lang == code else "secondary",
                    use_container_width=True,
                    help=LANGUAGE_FULL_NAMES[code],
                    on_click=_set_language,
                    args=(code,),
                )

        st.divider()
        st.markdown(f"##### :material/palette: {t('sb_visual_variants', lang)}")
        header_variant = st.radio(
            t("sb_masthead_style", lang),
            options=["white_stationery", "soft_sage", "solid_green"],
            format_func=lambda k: t(f"opt_{k}", lang),
            key="design_header_variant",
        )
        density = st.radio(
            t("sb_layout_density", lang),
            options=["executive", "compact"],
            format_func=lambda k: t(f"opt_{k}", lang),
            key="design_density",
        )
        table_tone = st.radio(
            t("sb_table_tone", lang),
            options=["slate", "green"],
            format_func=lambda k: t(f"opt_{k}", lang),
            key="design_table_tone",
        )
        show_wm = st.toggle(
            t("sb_watermark", lang),
            key="design_show_watermark",
        )

        st.divider()
        st.markdown(f"##### :material/dataset: {t('sb_demo_scenario', lang)}")
        st.selectbox(
            t("sb_ref_site", lang),
            options=list(BLUEPRINT_SCENARIOS.keys()),
            format_func=lambda k: t(BLUEPRINT_SCENARIOS[k]["scen_key"], lang),
            key="design_scenario_select",
            on_change=_on_scenario_change,
        )
        st.button(
            t("sb_reset_btn", lang),
            icon=":material/restart_alt:",
            use_container_width=True,
            on_click=_reset_blueprint_defaults,
        )
        st.caption(t("sb_caption", lang))

    return (
        str(header_variant or "white_stationery"),
        str(density or "executive"),
        str(table_tone or "slate"),
        bool(show_wm),
    )


def _render_control_ribbon(
    load_series: Any,
    cur_sys: CombinedSystemConfig,
    lang: str,
) -> None:
    """Renders the Level 1 white bordered system control bar."""
    orig_peak = float(load_series.peak_demand_kw)
    with st.container(border=True):
        c_grid, c_peak, c_sol, c_bat, c_gen, c_fin = st.columns([1.35, 1.35, 0.82, 0.82, 0.82, 0.84])
        with c_grid:
            new_limit = st.number_input(
                t("ctrl_grid_limit", lang),
                min_value=10.0,
                max_value=5000.0,
                step=10.0,
                key="design_grid_limit_w",
            )
            cur_sys.grid_limit_kw = float(new_limit)

        overload_kw = max(0.0, orig_peak - float(cur_sys.grid_limit_kw))
        with c_peak:
            st.metric(
                label=t("ctrl_baseline_peak", lang),
                value=f"{fmt_num(orig_peak, 1)} kW",
                delta=(
                    t("ctrl_above_limit", lang, val=fmt_num(overload_kw, 1))
                    if overload_kw > 0.05
                    else t("ctrl_within_limit", lang)
                ),
                delta_color="inverse" if overload_kw > 0.05 else "normal",
            )

        with c_sol:
            st.write("")
            cur_sys.enable_solar = bool(
                st.toggle(f":material/solar_power: {t('ctrl_solar', lang)}", key="design_en_solar_w")
            )
        with c_bat:
            st.write("")
            cur_sys.enable_battery = bool(
                st.toggle(f":material/battery_charging_full: {t('ctrl_battery', lang)}", key="design_en_battery_w")
            )
        with c_gen:
            st.write("")
            cur_sys.enable_generator = bool(
                st.toggle(f":material/power: {t('ctrl_generator', lang)}", key="design_en_generator_w")
            )
        with c_fin:
            st.write("")
            cur_sys.enable_financials = bool(
                st.toggle(f":material/payments: {t('ctrl_financials', lang)}", key="design_en_financials_w")
            )

        standby = t("pill_standby", lang)
        fuel_lbl = t(f"fuel_{cur_sys.fuel_type}", lang)
        render_module_pills(
            [
                (
                    t("pill_grid", lang),
                    True,
                    t("pill_limit_suffix", lang, val=fmt_num(cur_sys.grid_limit_kw, 0)),
                ),
                (
                    t("pill_solar", lang),
                    cur_sys.enable_solar,
                    t("pill_share_suffix", lang, val=fmt_num(cur_sys.target_consumption_share_pct, 0))
                    if cur_sys.enable_solar
                    else standby,
                ),
                (
                    t("pill_battery", lang),
                    cur_sys.enable_battery,
                    f"{fmt_num(cur_sys.battery_capacity_kwh, 0)} kWh / {fmt_num(cur_sys.battery_power_kw, 0)} kW"
                    if cur_sys.enable_battery
                    else standby,
                ),
                (
                    t("pill_generator", lang),
                    cur_sys.enable_generator,
                    f"{fmt_num(cur_sys.generator_rated_kw, 0)} kW {fuel_lbl}"
                    if cur_sys.enable_generator
                    else standby,
                ),
            ]
        )


def _render_tab1_executive_overview(sim_res: CombinedSimulationResult, lang: str) -> None:
    """Tab 1: Executive KPI cards, compliance banner, and light-mode interactive charts."""
    kpis = sim_res.kpis
    cfg = sim_res.system_config
    fk = sim_res.financial_kpis if cfg.enable_financials else None

    if kpis.grid_limit_met:
        render_status_banner(
            title=t("banner_ok_title", lang),
            body=t(
                "banner_ok_body",
                lang,
                peak=fmt_num(kpis.new_grid_peak_kw, 1),
                limit=fmt_num(cfg.grid_limit_kw, 0),
            ),
            tone="ok",
        )
    else:
        render_status_banner(
            title=t("banner_warn_title", lang),
            body=t(
                "banner_warn_body",
                lang,
                peak=fmt_num(kpis.new_grid_peak_kw, 1),
                over_kw=fmt_num(kpis.remaining_overload_kw, 1),
                limit=fmt_num(cfg.grid_limit_kw, 0),
                over_kwh=fmt_num(kpis.remaining_overload_kwh, 0),
                over_hrs=fmt_num(kpis.remaining_overload_hours, 1),
            ),
            tone="warn",
        )

    render_section_heading(
        t("sec1_title", lang),
        subtitle=t("sec1_sub", lang),
        badge=t("sec1_badge", lang),
    )
    t1, t2, t3, t4 = st.columns(4)
    with t1:
        render_drac_kpi_card(
            title=t("kpi_grid_peak", lang),
            value=f"{fmt_num(kpis.original_peak_kw, 1)} -> {fmt_num(kpis.new_grid_peak_kw, 1)} kW",
            subtext=t(
                "kpi_shaved_sub",
                lang,
                shaved=fmt_num(kpis.peak_reduction_kw, 1),
                limit=fmt_num(cfg.grid_limit_kw, 0),
            ),
            tone="ok" if kpis.grid_limit_met else "alert",
            badge=t("badge_compliant", lang) if kpis.grid_limit_met else t("badge_breach", lang),
        )
    with t2:
        render_drac_kpi_card(
            title=t("kpi_rem_overload", lang),
            value=f"{fmt_num(kpis.remaining_overload_hours, 1)} {t('unit_hrs_yr', lang)}",
            subtext=t(
                "kpi_unmet_sub",
                lang,
                unmet=fmt_num(kpis.remaining_overload_kwh, 0),
                base_hrs=fmt_num(kpis.baseline_overload_hours, 1),
            ),
            tone="ok" if kpis.grid_limit_met else "alert",
        )
    with t3:
        onsite_pct = max(0.0, 100.0 - kpis.grid_supply_share_pct)
        render_drac_kpi_card(
            title=t("kpi_onsite_share", lang),
            value=f"{fmt_num(onsite_pct, 1)}%",
            subtext=t(
                "kpi_onsite_sub",
                lang,
                grid=fmt_num(kpis.grid_supply_share_pct, 1),
                sol=fmt_num(kpis.solar_direct_share_pct, 1),
                bat=fmt_num(kpis.battery_discharge_share_pct, 1),
            ),
            tone="accent",
        )
    with t4:
        render_drac_kpi_card(
            title=t("kpi_storage_gen", lang),
            value=f"{fmt_num(kpis.battery_equivalent_cycles, 1)} {t('unit_cyc_yr', lang)}",
            subtext=t(
                "kpi_storage_gen_sub",
                lang,
                mwh=fmt_num(kpis.battery_total_discharged_kwh / 1000.0, 1),
                gen_hrs=fmt_num(kpis.generator_runtime_hours, 1),
            ),
            tone="default",
        )

    if fk is not None:
        curr = str(getattr(fk, "currency_code", "EUR") or "EUR")
        pb_str = (
            f"{fmt_num(fk.payback_years, 1)} {t('unit_yrs', lang)}"
            if fk.payback_years is not None
            else t("unit_gt15_yrs", lang)
        )
        irr_str = f"{fmt_num(fk.irr_15y_pct, 1)}%" if fk.irr_15y_pct is not None else "N/A"
        render_section_heading(
            t("sec2_title", lang),
            subtitle=t("sec2_sub", lang),
            badge=curr,
        )
        f1, f2, f3, f4 = st.columns(4)
        with f1:
            render_drac_kpi_card(
                title=t("kpi_net_capex", lang),
                value=format_currency_value(fk.total_capex_eur, curr),
                subtext=t(
                    "kpi_net_capex_sub",
                    lang,
                    sol=format_currency_value(fk.solar_capex_eur, curr),
                    bat=format_currency_value(fk.battery_capex_eur, curr),
                ),
                tone="default",
            )
        with f2:
            render_drac_kpi_card(
                title=t("kpi_y1_savings", lang),
                value=f"{format_currency_value(fk.annual_savings_eur, curr, signed=True)}/{t('unit_yr', lang)}",
                subtext=t(
                    "kpi_with_sys_vs",
                    lang,
                    new_opex=format_currency_value(fk.total_annual_opex_eur, curr),
                    base_opex=format_currency_value(fk.baseline_total_opex_eur, curr),
                ),
                tone="ok" if fk.annual_savings_eur > 0 else "alert",
                badge=t("badge_positive", lang) if fk.annual_savings_eur > 0 else t("badge_deficit", lang),
            )
        with f3:
            render_drac_kpi_card(
                title=t("kpi_payback_irr", lang),
                value=pb_str,
                subtext=t("kpi_payback_irr_sub", lang, irr=irr_str, bcr=fmt_num(fk.benefit_cost_ratio_15y, 2)),
                tone="ok" if fk.payback_years is not None else "alert",
            )
        with f4:
            render_drac_kpi_card(
                title=t("kpi_net_profit_15y", lang),
                value=format_currency_value(fk.tco_15y_savings_eur, curr, signed=True),
                subtext=t("kpi_npv_15y", lang, npv=format_currency_value(fk.npv_15y_eur, curr, signed=True)),
                tone="ok" if fk.tco_15y_savings_eur > 0 else "alert",
            )

    render_section_heading(t("sec3_title", lang), subtitle=t("sec3_sub", lang))
    with st.container(border=True):
        fig_dispatch = create_combined_dispatch_soc_figure(
            sim_res=sim_res,
            timeframe="7D",
            height=500,
        )
        st.plotly_chart(
            apply_drac_light_chart_theme(fig_dispatch, height=500),
            use_container_width=True,
            config={"scrollZoom": False, "displayModeBar": "hover", "responsive": True},
            key="design_dispatch_chart",
        )

    render_section_heading(t("sec4_title", lang), subtitle=t("sec4_sub", lang))
    diag = compute_system_utilization_diagnostics(sim_res)
    c_mix, c_util = st.columns(2)
    with c_mix:
        with st.container(border=True):
            fig_mix = create_supply_mix_pie_figure(diag, height=340)
            st.plotly_chart(
                apply_drac_light_chart_theme(fig_mix, height=340),
                use_container_width=True,
                config={"displayModeBar": False, "responsive": True},
                key="design_mix_chart",
            )
    with c_util:
        with st.container(border=True):
            fig_util = create_component_utilization_bars_figure(diag, height=340)
            st.plotly_chart(
                apply_drac_light_chart_theme(fig_util, height=340),
                use_container_width=True,
                config={"displayModeBar": False, "responsive": True},
                key="design_util_chart",
            )


def _render_tab2_configuration(
    sim_res: CombinedSimulationResult,
    cur_sys: CombinedSystemConfig,
    cur_rules: InteractionRulesConfig,
    lang: str,
) -> None:
    """Tab 2: Showcases white-green forms, inputs, sliders, selectboxes, and quick presets."""
    render_section_heading(t("cfg_sec_title", lang), subtitle=t("cfg_sec_sub", lang))

    qp1, qp2, qp3 = st.columns(3)
    with qp1:
        st.button(
            t("preset_balanced", lang),
            icon=":material/wb_sunny:",
            use_container_width=True,
            on_click=_apply_mix_preset,
            args=(True, True, False),
        )
    with qp2:
        st.button(
            t("preset_trihybrid", lang),
            icon=":material/hub:",
            use_container_width=True,
            on_click=_apply_mix_preset,
            args=(True, True, True),
        )
    with qp3:
        st.button(
            t("preset_grid_only", lang),
            icon=":material/electric_meter:",
            use_container_width=True,
            on_click=_apply_mix_preset,
            args=(False, False, False),
        )

    site_names = list(SOLAR_SITE_PRESETS.keys())
    fuel_opts = ["Diesel", "Natural Gas", "HVO"]
    r1_keys = list(RULE1_OPTIONS.keys())
    r2_keys = list(RULE2_OPTIONS.keys())
    r3_keys = list(RULE3_OPTIONS.keys())

    with st.form("drac_blueprint_config_form"):
        col_l, col_r = st.columns(2)
        with col_l:
            with st.container(border=True):
                st.markdown(f"##### :material/solar_power: {t('card_solar', lang)}")
                st.selectbox(
                    t("lbl_solar_site", lang),
                    options=site_names,
                    key="design_cfg_site",
                )
                st.slider(
                    t("lbl_solar_share", lang),
                    min_value=10.0,
                    max_value=150.0,
                    step=5.0,
                    key="design_cfg_sol_share",
                )
                st.number_input(
                    t("lbl_tilt", lang),
                    min_value=0.0,
                    max_value=60.0,
                    step=5.0,
                    key="design_cfg_tilt",
                )
                st.caption(
                    t(
                        "cap_derived_pv",
                        lang,
                        kwp=fmt_num(sim_res.solar_derivation.installed_kwp, 1),
                        source=sim_res.solar_derivation.data_source_label,
                    )
                )

            with st.container(border=True):
                st.markdown(f"##### :material/power: {t('card_gen', lang)}")
                st.number_input(
                    t("lbl_gen_power", lang),
                    min_value=10.0,
                    max_value=5000.0,
                    step=10.0,
                    key="design_cfg_gen_kw",
                )
                st.selectbox(
                    t("lbl_fuel_type", lang),
                    options=fuel_opts,
                    format_func=lambda f: t(f"fuel_{f}", lang),
                    key="design_cfg_fuel",
                )
                st.slider(
                    t("lbl_gen_min_load", lang),
                    min_value=15.0,
                    max_value=50.0,
                    step=5.0,
                    key="design_cfg_gen_min",
                )

        with col_r:
            with st.container(border=True):
                st.markdown(f"##### :material/battery_charging_full: {t('card_bess', lang)}")
                st.number_input(
                    t("lbl_bess_cap", lang),
                    min_value=10.0,
                    max_value=20000.0,
                    step=20.0,
                    key="design_cfg_bess_kwh",
                )
                st.number_input(
                    t("lbl_bess_pow", lang),
                    min_value=5.0,
                    max_value=10000.0,
                    step=10.0,
                    key="design_cfg_bess_kw",
                )
                st.slider(
                    t("lbl_soc_window", lang),
                    min_value=0.0,
                    max_value=100.0,
                    step=5.0,
                    key="design_cfg_soc_range",
                )
                st.slider(
                    t("lbl_rte", lang),
                    min_value=70.0,
                    max_value=98.0,
                    step=1.0,
                    key="design_cfg_rte",
                )

            with st.container(border=True):
                st.markdown(f"##### :material/tune: {t('card_rules', lang)}")
                st.selectbox(
                    t("lbl_rule1", lang),
                    options=r1_keys,
                    format_func=lambda k: t(f"rule1_{k}", lang),
                    key="design_cfg_r1",
                )
                st.selectbox(
                    t("lbl_rule2", lang),
                    options=r2_keys,
                    format_func=lambda k: t(f"rule2_{k}", lang),
                    key="design_cfg_r2",
                )
                st.selectbox(
                    t("lbl_rule3", lang),
                    options=r3_keys,
                    format_func=lambda k: t(f"rule3_{k}", lang),
                    key="design_cfg_r3",
                )

        st.form_submit_button(
            t("btn_apply_config", lang),
            icon=":material/check_circle:",
            type="primary",
            use_container_width=True,
            on_click=_apply_config_form_cb,
        )


def _render_tab3_financials(
    sim_res: CombinedSimulationResult,
    table_tone: str,
    lang: str,
) -> None:
    """Tab 3: White-Green cost bridge bar, component cost table, and light-mode TCO charts."""
    if not sim_res.system_config.enable_financials or sim_res.financial_kpis is None:
        render_status_banner(
            title=t("fin_off_title", lang),
            body=t("fin_off_body", lang),
            tone="info",
        )
        st.button(
            t("fin_activate_btn", lang),
            icon=":material/payments:",
            type="primary",
            on_click=_enable_financials_cb,
        )
        return

    fk = sim_res.financial_kpis
    curr = str(getattr(fk, "currency_code", "EUR") or "EUR")

    render_drac_cost_bridge_bar(
        sim_res,
        labels={
            "header": t("bridge_hdr", lang, curr=curr),
            "current_bill": t("bridge_curr_bill", lang),
            "new_grid": t("bridge_new_grid", lang),
            "hw_opex": t("bridge_hw_opex", lang),
            "export_income": t("bridge_export", lang),
            "combined_opex": t("bridge_comb_opex", lang),
            "net_savings": t("bridge_net_sav", lang),
            "net_capex": t("bridge_net_capex", lang),
            "payback": t("bridge_payback", lang),
            "npv_15y": t("bridge_npv", lang),
            "per_yr": t("unit_yr", lang),
            "yrs_unit": t("unit_yrs", lang),
            "solar": t("mod_solar", lang),
            "battery": t("ctrl_battery", lang),
            "gen": t("mod_gen", lang),
        },
    )

    render_section_heading(
        t("fin_sec1_title", lang),
        subtitle=t("fin_sec1_sub", lang),
        badge=curr,
    )
    cost_rows = [
        [
            t("row_p1", lang),
            format_currency_value(0.0, curr),
            format_currency_value(fk.baseline_pillar1_supply_eur, curr),
            format_currency_value(fk.combined_pillar1_supply_eur, curr),
            format_currency_value(fk.baseline_pillar1_supply_eur - fk.combined_pillar1_supply_eur, curr, signed=True),
        ],
        [
            t("row_p2", lang),
            format_currency_value(-fk.avoided_grid_upgrade_capex_eur, curr, signed=True)
            if fk.avoided_grid_upgrade_capex_eur > 0
            else format_currency_value(0.0, curr),
            format_currency_value(fk.baseline_pillar2_dso_eur, curr),
            format_currency_value(fk.combined_pillar2_dso_eur, curr),
            format_currency_value(fk.baseline_pillar2_dso_eur - fk.combined_pillar2_dso_eur, curr, signed=True),
        ],
        [
            t("row_p34", lang),
            format_currency_value(0.0, curr),
            format_currency_value(fk.baseline_pillar3_metering_eur + fk.baseline_pillar4_taxes_eur, curr),
            format_currency_value(fk.combined_pillar3_metering_eur + fk.combined_pillar4_taxes_eur, curr),
            format_currency_value(
                (fk.baseline_pillar3_metering_eur + fk.baseline_pillar4_taxes_eur)
                - (fk.combined_pillar3_metering_eur + fk.combined_pillar4_taxes_eur),
                curr,
                signed=True,
            ),
        ],
        [
            t("row_solar", lang),
            format_currency_value(fk.solar_capex_eur, curr),
            format_currency_value(0.0, curr),
            format_currency_value(fk.solar_om_eur, curr),
            format_currency_value(-fk.solar_om_eur, curr, signed=True),
        ],
        [
            t("row_bess", lang),
            format_currency_value(fk.battery_capex_eur, curr),
            format_currency_value(0.0, curr),
            format_currency_value(fk.battery_om_eur, curr),
            format_currency_value(-fk.battery_om_eur, curr, signed=True),
        ],
        [
            t("row_gen", lang),
            format_currency_value(fk.generator_capex_eur, curr),
            format_currency_value(0.0, curr),
            format_currency_value(fk.generator_total_opex_eur, curr),
            format_currency_value(-fk.generator_total_opex_eur, curr, signed=True),
        ],
        [
            t("row_export", lang),
            format_currency_value(0.0, curr),
            format_currency_value(0.0, curr),
            format_currency_value(-fk.solar_export_revenue_eur, curr, signed=True),
            format_currency_value(fk.solar_export_revenue_eur, curr, signed=True),
        ],
        [
            t("row_total", lang),
            format_currency_value(fk.total_capex_eur, curr),
            format_currency_value(fk.baseline_total_opex_eur, curr),
            format_currency_value(fk.total_annual_opex_eur, curr),
            format_currency_value(fk.annual_savings_eur, curr, signed=True),
        ],
    ]
    st.markdown(
        render_drac_table_html(
            headers=[
                t("fin_col_component", lang),
                t("fin_col_capex", lang),
                t("fin_col_curr", lang),
                t("fin_col_with_sys", lang),
                t("fin_col_impact", lang),
            ],
            rows=cost_rows,
            numeric_cols=(1, 2, 3, 4),
            summary_last_row=True,
            header_tone=table_tone,
        ),
        unsafe_allow_html=True,
    )

    render_section_heading(t("fin_sec2_title", lang), subtitle=t("fin_sec2_sub", lang))
    with st.container(border=True):
        fig_tco = create_financial_tco_trajectory_figure(sim_res)
        st.plotly_chart(
            apply_drac_light_chart_theme(fig_tco, height=540),
            use_container_width=True,
            config={"displayModeBar": "hover", "responsive": True},
            key="design_tco_chart",
        )

    with st.container(border=True):
        fig_wf = create_financial_waterfall_bridge_figure(sim_res)
        st.plotly_chart(
            apply_drac_light_chart_theme(fig_wf, height=420),
            use_container_width=True,
            config={"displayModeBar": "hover", "responsive": True},
            key="design_wf_chart",
        )

    if sim_res.cashflow_15y_df is not None and not sim_res.cashflow_15y_df.empty:
        with st.expander(t("exp_15y_cf", lang), expanded=False, icon=":material/table_chart:"):
            cf_rows: List[List[object]] = []
            for rec in sim_res.cashflow_15y_df.to_dict(orient="records"):
                cf_rows.append(
                    [
                        int(rec["Year"]),
                        format_currency_value(float(rec["Current situation Bill (€)"]), curr),
                        format_currency_value(float(rec["Combined System OPEX (€)"]), curr),
                        format_currency_value(float(rec.get("Investment & Augmentation (€)", 0.0)), curr),
                        format_currency_value(float(rec["Net Cashflow (€)"]), curr, signed=True),
                        format_currency_value(float(rec["Cumulative Cashflow (€)"]), curr, signed=True),
                    ]
                )
            st.markdown(
                render_drac_table_html(
                    headers=[
                        t("cf_col_year", lang),
                        t("cf_col_curr", lang),
                        t("cf_col_opex", lang),
                        t("cf_col_capex", lang),
                        t("cf_col_net", lang),
                        t("cf_col_cum", lang),
                    ],
                    rows=cf_rows,
                    numeric_cols=(0, 1, 2, 3, 4, 5),
                    summary_last_row=False,
                    header_tone=table_tone,
                ),
                unsafe_allow_html=True,
            )


def _render_tab4_specimen(lang: str) -> None:
    """Tab 4: Interactive DRAC Design System Specimen & Style Reference."""
    p = DRAC_PALETTE
    logo_uri = get_drac_logo_data_uri()
    wm_uri = get_drac_watermark_data_uri()

    render_section_heading(t("spec_sec1_title", lang), subtitle=t("spec_sec1_sub", lang))
    swatches = [
        (t("sw_brand_name", lang), p["brand"], t("sw_brand_use", lang)),
        (t("sw_logo_name", lang), p["brand_logo"], t("sw_logo_use", lang)),
        (t("sw_dark_name", lang), p["brand_dark"], t("sw_dark_use", lang)),
        (t("sw_soft_name", lang), p["brand_soft"], t("sw_soft_use", lang)),
        (t("sw_canvas_name", lang), p["canvas"], t("sw_canvas_use", lang)),
        (t("sw_surface_name", lang), p["surface"], t("sw_surface_use", lang)),
        (t("sw_ink_name", lang), p["ink_strong"], t("sw_ink_use", lang)),
        (t("sw_ok_name", lang), p["ok"], t("sw_ok_use", lang)),
        (t("sw_alert_name", lang), p["alert"], t("sw_alert_use", lang)),
        (t("sw_accent_name", lang), p["accent"], t("sw_accent_use", lang)),
    ]
    swatch_cards = []
    for name, hex_code, usage in swatches:
        border_col = "#cbd5e1" if hex_code.lower() in ("#ffffff", "#f7f9f5", "#f2f7ec") else hex_code
        swatch_cards.append(
            '<div style="background:#ffffff; border:1px solid #dce3d8; border-radius:9px; padding:10px; box-shadow:0 1px 2px rgba(15,23,42,0.03);">'
            f'<div style="height:42px; border-radius:6px; background:{hex_code}; border:1px solid {border_col}; margin-bottom:8px;"></div>'
            f'<div style="font-size:0.82rem; font-weight:700; color:#0f172a;">{name}</div>'
            f'<div style="font-size:0.76rem; font-family:monospace; color:#5d7c34; font-weight:700;">{hex_code}</div>'
            f'<div style="font-size:0.74rem; color:#64748b; margin-top:2px;">{usage}</div>'
            "</div>"
        )
    st.markdown(
        '<div style="display:grid; grid-template-columns:repeat(auto-fill, minmax(175px, 1fr)); gap:10px; margin-bottom:14px;">'
        + "".join(swatch_cards)
        + "</div>",
        unsafe_allow_html=True,
    )

    render_section_heading(t("spec_sec2_title", lang), subtitle=t("spec_sec2_sub", lang))
    lc1, lc2, lc3 = st.columns(3)
    with lc1:
        st.markdown(
            '<div style="background:#ffffff; border:1px solid #dce3d8; border-radius:10px; padding:18px; text-align:center;">'
            f'<div style="font-size:0.72rem; font-weight:700; color:#64748b; text-transform:uppercase; margin-bottom:10px;">{t("spec_on_white", lang)}</div>'
            f'<img src="{logo_uri}" alt="DRAC Logo White" style="height:76px; width:auto; display:inline-block;">'
            "</div>",
            unsafe_allow_html=True,
        )
    with lc2:
        st.markdown(
            '<div style="background:#f2f7ec; border:1px solid #cddcb9; border-radius:10px; padding:18px; text-align:center;">'
            f'<div style="font-size:0.72rem; font-weight:700; color:#5d7c34; text-transform:uppercase; margin-bottom:10px;">{t("spec_on_sage", lang)}</div>'
            f'<img src="{logo_uri}" alt="DRAC Logo Sage" style="height:76px; width:auto; display:inline-block;">'
            "</div>",
            unsafe_allow_html=True,
        )
    with lc3:
        st.markdown(
            '<div style="background:linear-gradient(120deg,#5d7c34,#7a9f48); border:1px solid #5d7c34; border-radius:10px; padding:18px; text-align:center;">'
            f'<div style="font-size:0.72rem; font-weight:700; color:#ffffff; text-transform:uppercase; margin-bottom:10px;">{t("spec_on_green", lang)}</div>'
            '<div style="background:#ffffff; border-radius:8px; padding:6px 14px; display:inline-block;">'
            f'<img src="{logo_uri}" alt="DRAC Logo Framed" style="height:64px; width:auto; display:block;">'
            "</div>"
            "</div>",
            unsafe_allow_html=True,
        )

    if wm_uri:
        st.caption(t("spec_wm_caption", lang))

    render_section_heading(t("spec_sec3_title", lang), subtitle=t("spec_sec3_sub", lang))
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        render_drac_kpi_card(
            t("spec_card_ok_title", lang),
            "178,4 kW",
            t("spec_card_ok_sub", lang),
            tone="ok",
            badge=t("badge_compliant", lang),
        )
    with k2:
        render_drac_kpi_card(
            t("spec_card_alert_title", lang),
            "+24,5 kW",
            t("spec_card_alert_sub", lang),
            tone="alert",
            badge=t("spec_card_alert_badge", lang),
        )
    with k3:
        render_drac_kpi_card(
            t("spec_card_accent_title", lang),
            "58,4%",
            t("spec_card_accent_sub", lang),
            tone="accent",
            badge=f"{t('mod_solar', lang)} + {t('mod_bess', lang)}",
        )
    with k4:
        render_drac_kpi_card(
            t("spec_card_def_title", lang),
            f"142 {t('unit_cyc_yr', lang)}",
            t("spec_card_def_sub", lang),
            tone="default",
        )

    render_status_banner(t("spec_banner_ok_t", lang), t("spec_banner_ok_b", lang), tone="ok")
    render_status_banner(t("spec_banner_warn_t", lang), t("spec_banner_warn_b", lang), tone="warn")
    render_status_banner(t("spec_banner_info_t", lang), t("spec_banner_info_b", lang), tone="info")

    render_section_heading(t("spec_sec4_title", lang), subtitle=t("spec_sec4_sub", lang))
    with st.container(border=True):
        bc1, bc2, bc3 = st.columns(3)
        with bc1:
            st.button(t("spec_btn_pri", lang), icon=":material/check_circle:", type="primary", use_container_width=True, key="spec_btn_pri")
        with bc2:
            st.button(t("spec_btn_sec", lang), icon=":material/tune:", use_container_width=True, key="spec_btn_sec")
        with bc3:
            st.button(t("spec_btn_dis", lang), icon=":material/block:", disabled=True, use_container_width=True, key="spec_btn_dis")

        if st.button(
            t("spec_btn_loader_preview", lang),
            icon=":material/progress_activity:",
            type="primary",
            use_container_width=True,
            key="spec_btn_loader_preview",
        ):
            with drac_loading_overlay(
                message=t("loader_calculating", lang),
                subtext=t("loader_subtext", lang),
            ):
                time.sleep(1.5)

        wc1, wc2, wc3 = st.columns(3)
        with wc1:
            st.number_input(t("spec_num_lbl", lang), min_value=0.0, max_value=2000.0, value=300.0, step=50.0, key="spec_num")
        with wc2:
            st.selectbox(t("spec_sel_lbl", lang), ["MV-D (125 to 1,500 kW)", "MV/LV (> 50 to 125 kW)"], key="spec_sel")
        with wc3:
            st.slider(t("spec_sld_lbl", lang), min_value=0, max_value=100, value=30, key="spec_sld")

    tc1, tc2 = st.columns(2)
    sample_headers = [t("spec_tbl_h1", lang), t("spec_tbl_h2", lang), t("spec_tbl_h3", lang)]
    sample_rows = [
        [t("spec_tbl_r1_c1", lang), "180 kW", "0,0 kW"],
        [t("spec_tbl_r2_c1", lang), "150 kWp", t("spec_tbl_r2_c3", lang)],
        [t("spec_tbl_r3_c1", lang), t("badge_compliant", lang), f"+EUR 18.400/{t('unit_yr', lang)}"],
    ]
    with tc1:
        st.caption(t("spec_tbl_opt_a", lang))
        st.markdown(
            render_drac_table_html(sample_headers, sample_rows, numeric_cols=(1, 2), summary_last_row=True, header_tone="slate"),
            unsafe_allow_html=True,
        )
    with tc2:
        st.caption(t("spec_tbl_opt_b", lang))
        st.markdown(
            render_drac_table_html(sample_headers, sample_rows, numeric_cols=(1, 2), summary_last_row=True, header_tone="green"),
            unsafe_allow_html=True,
        )


def main() -> None:
    st.set_page_config(
        page_title="DRAC Design Blueprint",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _init_blueprint_state()
    lang = str(st.session_state.get("design_lang", DEFAULT_LANGUAGE))
    header_variant, density, table_tone, show_watermark = _render_sidebar(lang)
    inject_drac_light_theme(
        density=density,
        show_watermark=show_watermark,
        loading_text=t("loader_calculating", lang),
    )

    _render_top_language_bar(lang)

    scenario_key = st.session_state.get("design_scenario_key", DEFAULT_SCENARIO_KEY)
    spec = BLUEPRINT_SCENARIOS.get(scenario_key, BLUEPRINT_SCENARIOS[DEFAULT_SCENARIO_KEY])
    load_series = _load_blueprint_profile(spec["profile_type"], spec["nominal_peak_kw"])

    cur_sys: CombinedSystemConfig = st.session_state["design_sys_cfg"]
    cur_rules: InteractionRulesConfig = st.session_state["design_rules_cfg"]
    cur_fin: CombinedFinancialConfig = st.session_state["design_fin_cfg"]
    _sync_control_ribbon_to_sys(cur_sys)

    sim_res = _get_cached_simulation(
        scenario_key=scenario_key,
        load_series=load_series,
        sys_cfg=cur_sys,
        rules_cfg=cur_rules,
        fin_cfg=cur_fin,
        lang=lang,
    )

    active_mods = [t("mod_grid", lang)]
    if cur_sys.enable_solar:
        active_mods.append(f"{t('mod_solar', lang)} {fmt_num(sim_res.solar_derivation.installed_kwp, 0)} kWp")
    if cur_sys.enable_battery:
        active_mods.append(f"{t('mod_bess', lang)} {fmt_num(cur_sys.battery_capacity_kwh, 0)} kWh")
    if cur_sys.enable_generator:
        active_mods.append(f"{t('mod_gen', lang)} {fmt_num(cur_sys.generator_rated_kw, 0)} kW")

    site_label = t(spec["site_key"], lang)
    render_drac_masthead(
        title=t("masthead_title", lang),
        subtitle=t("masthead_subtitle", lang, site_label=site_label),
        eyebrow=t("masthead_eyebrow", lang),
        meta_items=[
            (t("meta_grid_limit", lang), f"{fmt_num(cur_sys.grid_limit_kw, 0)} kW"),
            (t("meta_active_mix", lang), " + ".join(active_mods)),
            (
                t("meta_currency", lang),
                cur_fin.currency_code if cur_sys.enable_financials else t("meta_technical_only", lang),
            ),
            (t("meta_language", lang), LANGUAGE_FULL_NAMES.get(lang, "English")),
        ],
        header_variant=header_variant,
    )

    _render_control_ribbon(load_series, cur_sys, lang)

    tabs = st.tabs(
        [
            f":material/dashboard: {t('tab1_overview', lang)}",
            f":material/tune: {t('tab2_config', lang)}",
            f":material/payments: {t('tab3_financials', lang)}",
            f":material/palette: {t('tab4_specimen', lang)}",
        ]
    )

    with tabs[0]:
        _render_tab1_executive_overview(sim_res, lang=lang)
    with tabs[1]:
        _render_tab2_configuration(sim_res, cur_sys, cur_rules, lang=lang)
    with tabs[2]:
        _render_tab3_financials(sim_res, table_tone=table_tone, lang=lang)
    with tabs[3]:
        _render_tab4_specimen(lang=lang)

    render_drac_footer(note=t("footer_note", lang), right_text=t("footer_right", lang))


if __name__ == "__main__":
    main()
