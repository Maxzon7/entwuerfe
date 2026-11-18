"""
Subtab 5: System Mix & Operating Rules view (Supply Mix & Utilization Cockpit,
Coordinated Right-Sizing Workbench, and Dispatch Interaction Rules).
"""

import copy
from typing import List, Optional
import numpy as np
import pandas as pd
import streamlit as st

from .state_and_helpers import (
    LoadSeries2025,
    CombinedSystemConfig,
    InteractionRulesConfig,
    CoordinatedMixRecommendation,
    SystemUtilizationDiagnostics,
    MIX_STRATEGY_OPTIONS,
    RULE1_OPTIONS,
    RULE2_OPTIONS,
    RULE3_OPTIONS,
    get_unit_solar_generation_profile,
    derive_solar_sizing_and_formula,
    compute_dual_generator_sizing,
    simulate_combined_system_dispatch,
    compute_coordinated_mix_sizing,
    compute_system_utilization_diagnostics,
    determine_smart_modular_units,
    create_supply_mix_pie_figure,
    create_component_utilization_bars_figure,
    _load_fingerprint,
    _physical_sys_tuple,
    _rules_tuple,
    _get_active_load_series,
)

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
        "comb_cached_dual_bess_pair",
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
                    weather_mode=str(getattr(cand_cfg, "solar_weather_mode", "single_year")),
                    selected_year=int(getattr(cand_cfg, "solar_weather_year", 2025)),
                )
                ann_cons_kwh = float(getattr(load_series, "total_energy_kwh", 0.0) or float(np.sum(load_series.power_kw) * 0.25))
                s_info = derive_solar_sizing_and_formula(
                    annual_consumption_kwh=ann_cons_kwh,
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
                    timestamps=load_series.timestamps,
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
