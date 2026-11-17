"""
Subtab 3: Battery Storage (BESS) view (Dual-Sizing reference fragment, modular sizing form & bottleneck check).
"""

from typing import List, Optional
import numpy as np
import streamlit as st

from .state_and_helpers import (
    ENGINE_VERSION,
    RULE1_OPTIONS,
    RULE2_OPTIONS,
    RULE3_OPTIONS,
    LoadSeries2025,
    CombinedSystemConfig,
    InteractionRulesConfig,
    DualBatterySizingResult,
    compute_dual_battery_sizing,
    refresh_bottleneck_table_configured_status,
    determine_smart_modular_units,
    _load_fingerprint,
    _rules_tuple,
    _activate_module_callback,
    _apply_bess_quick_size,
)

# ======================================================================================
# LEVEL 2 — SUBTAB 3: Battery (Dual-Sizing & 4-Bottleneck Diagnostic Table)
# ======================================================================================

def _sync_bess_include_gen_from_b1() -> None:
    """Syncs the shared Without/With Generator switch when toggled inside Block 1."""
    use_gen = st.session_state.get("comb_bess_include_gen_radio_b1") == "With Generator Backup"
    st.session_state["comb_bess_include_gen"] = use_gen
    st.session_state["comb_bess_include_gen_toggle_b3"] = use_gen
    st.session_state["_comb_bess_needs_full_rerun"] = True
    pair = st.session_state.get("comb_cached_dual_bess_pair")
    if isinstance(pair, tuple) and len(pair) == 2:
        st.session_state["comb_cached_dual_bess"] = pair[1] if use_gen else pair[0]


def _sync_bess_include_gen_from_b3() -> None:
    """Syncs the shared Without/With Generator switch when toggled inside Block 3."""
    use_gen = bool(st.session_state.get("comb_bess_include_gen_toggle_b3", False))
    st.session_state["comb_bess_include_gen"] = use_gen
    st.session_state["comb_bess_include_gen_radio_b1"] = (
        "With Generator Backup" if use_gen else "Without Generator (Default)"
    )
    pair = st.session_state.get("comb_cached_dual_bess_pair")
    if isinstance(pair, tuple) and len(pair) == 2:
        st.session_state["comb_cached_dual_bess"] = pair[1] if use_gen else pair[0]


@st.fragment
def _render_battery_reference_fragment(dual_bess: DualBatterySizingResult, is_active: bool) -> None:
    """Renders the interactive Battery Size Recommendation box inside an isolated fragment."""
    st.markdown("##### :material/battery_charging_full: 1. Recommended Battery Size")
    st.caption(
        "Smallest battery needed so your site stays below the Grid Limit all year."
    )

    include_gen = bool(st.session_state.get("comb_bess_include_gen", False))
    mode_options = [
        "Battery Alone (No Solar or Generator)",
        (
            "With Your Active Solar + Generator & Rules"
            if include_gen
            else "With Your Active Solar & Rules (Without Generator)"
        ),
    ]
    cur_mode = st.session_state.get("comb_bess_ref_mode", "With Your Active")
    sel_idx = 0 if (str(cur_mode).startswith("Mode A") or str(cur_mode).startswith("Battery Alone")) else 1

    r_col1, r_col2 = st.columns([1.3, 1.0])
    with r_col1:
        selected_mode = st.radio(
            "Calculate For",
            options=mode_options,
            index=sel_idx,
            horizontal=True,
            disabled=not is_active,
            key="comb_bess_ref_mode_radio",
        )
    with r_col2:
        gen_switch_options = ["Without Generator (Default)", "With Generator Backup"]
        if "comb_bess_include_gen_radio_b1" not in st.session_state:
            st.session_state["comb_bess_include_gen_radio_b1"] = (
                "With Generator Backup" if include_gen else "Without Generator (Default)"
            )
        st.radio(
            "Include Generator in Calculation?",
            options=gen_switch_options,
            horizontal=True,
            key="comb_bess_include_gen_radio_b1",
            on_change=_sync_bess_include_gen_from_b1,
            help=(
                "Without Generator (Default): Calculates the battery size needed without relying on a Generator. "
                "With Generator Backup: Subtracts active Generator capacity from the battery requirement."
            ),
        )
    if st.session_state.pop("_comb_bess_needs_full_rerun", False):
        st.rerun()

    st.session_state["comb_bess_ref_mode"] = selected_mode
    is_sa = selected_mode.startswith("Battery Alone")

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
        r2_detail = (
            f" (Reserve {cur_rules_ref.peak_reserve_soc_pct:.0f}%)"
            if cur_rules_ref.rule2_battery_strategy == "self_consumption_reserve"
            else ""
        )
        active_partners: List[str] = []
        if cur_sys_ref.enable_solar:
            active_partners.append("Solar")
        if include_gen and cur_sys_ref.enable_generator and cur_sys_ref.generator_rated_kw > 0:
            active_partners.append(f"Generator ({cur_sys_ref.generator_rated_kw:,.0f} kW)")
        partners_str = " + ".join(active_partners) if active_partners else "Grid Only"
        gen_mode_note = (
            " | Generator Backup Included"
            if (include_gen and cur_sys_ref.enable_generator and cur_sys_ref.generator_rated_kw > 0)
            else (" | Without Generator" if cur_sys_ref.enable_generator else "")
        )
        st.info(
            f"**Active Sizing Assumptions ({partners_str}{gen_mode_note}):** "
            f"**Rule 1:** {r1_lbl} | **Rule 2:** {r2_lbl}{r2_detail} | **Rule 3:** {r3_lbl}",
            icon=":material/rule:",
        )

    # Clear Summary Table (Matching Solar At-a-Glance Standard)
    min_soc_disp = float(cur_sys_ref.min_soc_pct) if cur_sys_ref is not None else 10.0
    max_soc_disp = float(cur_sys_ref.max_soc_pct) if cur_sys_ref is not None else 90.0
    bess_rows_html = "".join(
        f'<tr style="border-bottom:1px solid #1e293b;">'
        f'<td style="padding:8px 12px; color:#cbd5e1; font-weight:600;">{item}</td>'
        f'<td style="padding:8px 12px; color:#f8fafc; font-weight:700; text-align:right;">{val}</td>'
        f'<td style="padding:8px 12px; color:#94a3b8; font-size:0.86rem;">{note}</td>'
        f'</tr>'
        for item, val, note in [
            (
                "Total Battery Size Needed",
                f"{req_gross:,.1f} kWh",
                f"Full nameplate size including charge limits ({min_soc_disp:.0f}%–{max_soc_disp:.0f}% usable window)",
            ),
            (
                "Usable Energy Needed",
                f"{req_usable:,.1f} kWh",
                "Actual energy discharged across the longest period above your Grid Limit",
            ),
            (
                "Inverter Power Needed",
                f"{req_power:,.1f} kW",
                "Discharge power needed to cut the highest single peak down to the Grid Limit",
            ),
            (
                "Longest Peak Period",
                f"{req_duration:.1f} hrs",
                "Longest continuous period above the Grid Limit before the battery can recharge",
            ),
        ]
    )
    bess_table_html = (
        '<div style="border-radius:8px; border:1px solid #334155; overflow:hidden; margin-bottom:10px;">'
        '<table style="width:100%; border-collapse:collapse; font-family:-apple-system, BlinkMacSystemFont, sans-serif;">'
        '<thead><tr style="background-color:#090d16; border-bottom:1px solid #475569; color:#94a3b8; font-size:0.72rem; text-transform:uppercase; letter-spacing:0.04em;">'
        '<th style="padding:8px 12px; text-align:left;">Requirement</th>'
        '<th style="padding:8px 12px; text-align:right;">Recommended Value</th>'
        '<th style="padding:8px 12px; text-align:left;">What This Means</th>'
        '</tr></thead>'
        f'<tbody style="background-color:#0f172a;">{bess_rows_html}</tbody>'
        '</table>'
        '</div>'
    )
    st.markdown(bess_table_html, unsafe_allow_html=True)

    # Quick Apply Buttons (100%, 80%, 50% capacity while keeping 100% required discharge power kW)
    coupled_scope = (
        "With Solar + Generator"
        if include_gen
        else "With Solar (Without Generator)"
    )
    st.caption(
        f"**Quick Size ({'Battery Alone' if is_sa else coupled_scope}):** "
        "80% / 50% shrinks the battery kWh for lower cost while keeping 100% peak power kW (rare long peaks may need Generator backup)."
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
            f"Apply 80% Compact ({q80_kwh:,.0f} kWh / {q80_kw:,.1f} kW)",
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
            f"Apply 50% Peak Shaver ({q50_kwh:,.0f} kWh / {q50_kw:,.1f} kW)",
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
        str(getattr(cur_sys, "solar_weather_mode", "single_year")),
        int(getattr(cur_sys, "solar_weather_year", 2025)),
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
        or "comb_cached_dual_bess_pair" not in st.session_state
    ):
        dual_no_gen = compute_dual_battery_sizing(
            load_kw=load_series.power_kw,
            system_cfg=cur_sys,
            rules_cfg=cur_rules,
            is_gap=getattr(load_series, "is_gap", None),
            include_generator_in_coupled=False,
        )
        if cur_sys.enable_generator and cur_sys.generator_rated_kw > 0.0:
            dual_with_gen = compute_dual_battery_sizing(
                load_kw=load_series.power_kw,
                system_cfg=cur_sys,
                rules_cfg=cur_rules,
                is_gap=getattr(load_series, "is_gap", None),
                include_generator_in_coupled=True,
            )
        else:
            dual_with_gen = dual_no_gen
        st.session_state["comb_cached_dual_bess_pair"] = (dual_no_gen, dual_with_gen)
        st.session_state["comb_bess_sizing_fp"] = bess_sizing_fp

    include_gen = bool(st.session_state.get("comb_bess_include_gen", False))
    dual_no_gen, dual_with_gen = st.session_state["comb_cached_dual_bess_pair"]
    dual_bess = dual_with_gen if include_gen else dual_no_gen
    st.session_state["comb_cached_dual_bess"] = dual_bess

    # Block 1: Minimum Required Battery Sizing Reference Box
    with st.container(border=True):
        _render_battery_reference_fragment(dual_bess=dual_bess, is_active=is_active)

    # Block 2: Battery Hardware & Operating Limits Form
    pending_bess_sync = st.session_state.pop("comb_pending_bess_widget_sync", None)
    if isinstance(pending_bess_sync, dict):
        for sk, sv in pending_bess_sync.items():
            st.session_state[sk] = sv

    with st.container(border=True):
        st.markdown("##### :material/tune: 2. Battery Size & Settings")
        with st.form("comb_battery_form"):
            lock_05c = st.checkbox(
                "Lock to Standard 0.5 C (2-Hour Storage: Capacity kWh = 2 × Battery Power kW)",
                value=st.session_state.get("comb_bess_lock_05c", False),
                disabled=not is_active,
                key="comb_bess_lock_05c_box",
                help="When checked, applying this form automatically sets Battery Power (kW) to half of total kWh. Turned off automatically when you click a Quick-Size button.",
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
                if st.session_state.get("comb_bess_lock_05c", False):
                    st.caption("Locked to **0.5 C**: Power updates to half of total kWh when you apply. Uncheck above to set power freely.")
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
                dual_no_gen = compute_dual_battery_sizing(
                    load_kw=load_series.power_kw,
                    system_cfg=cur_sys,
                    rules_cfg=cur_rules,
                    is_gap=getattr(load_series, "is_gap", None),
                    include_generator_in_coupled=False,
                )
                if cur_sys.enable_generator and cur_sys.generator_rated_kw > 0.0:
                    dual_with_gen = compute_dual_battery_sizing(
                        load_kw=load_series.power_kw,
                        system_cfg=cur_sys,
                        rules_cfg=cur_rules,
                        is_gap=getattr(load_series, "is_gap", None),
                        include_generator_in_coupled=True,
                    )
                else:
                    dual_with_gen = dual_no_gen
                st.session_state["comb_cached_dual_bess_pair"] = (dual_no_gen, dual_with_gen)
                dual_bess = dual_with_gen if include_gen else dual_no_gen
                st.session_state["comb_cached_dual_bess"] = dual_bess
            st.session_state.pop("comb_cached_excel_bytes", None)
            if lock_05c and abs(float(bat_kw) - float(new_kw)) > 0.05:
                st.session_state["comb_pending_bess_widget_sync"] = {
                    "comb_battery_power_kw_num": float(new_kw),
                }
                st.rerun()

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

        hdr_c1, hdr_c2 = st.columns([2.4, 1.4])
        with hdr_c1:
            st.markdown("##### :material/fact_check: 3. System Limit Check")
            st.caption("Checks whether inverter discharge power, storage capacity, and recharge headroom cover every peak.")
        with hdr_c2:
            st.write("")
            if "comb_bess_include_gen_toggle_b3" not in st.session_state:
                st.session_state["comb_bess_include_gen_toggle_b3"] = include_gen
            st.toggle(
                "Include Generator Backup in Limit Check",
                key="comb_bess_include_gen_toggle_b3",
                on_change=_sync_bess_include_gen_from_b3,
                help=(
                    "Default OFF: Checks whether the Battery (+ Solar) covers all peaks without Generator backup. "
                    "Turn ON to include the active Generator when checking residual battery limits."
                ),
            )

        if pass_all:
            limit_ok_msg = (
                "Your Battery + active Generator cover every peak above the Grid Limit."
                if (include_gen and cur_sys.enable_generator and cur_sys.generator_rated_kw > 0)
                else "Your battery covers every peak above the Grid Limit."
            )
            st.success(
                f":material/check_circle: **Grid Limit Met (Zero Overload)**  \n{limit_ok_msg}"
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
            if not include_gen and cur_sys.enable_generator and cur_sys.generator_rated_kw > 0:
                st.warning(
                    f":material/warning: **Battery Alone Insufficient for All Peaks (Without Generator)**  \n{reason_body}"
                )
                st.info(
                    f":material/electric_bolt: **Generator Backup Active in Combined Simulation ({cur_sys.generator_rated_kw:,.0f} kW):** "
                    "Your active Generator covers the remaining multi-day peaks once the Battery reaches SoC Min. "
                    "Turn ON **Include Generator Backup in Limit Check** above to check combined Battery + Generator compliance."
                )
            else:
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
