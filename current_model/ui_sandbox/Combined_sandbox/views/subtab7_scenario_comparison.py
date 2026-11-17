"""
Subtab 7: Scenario Comparison (Scenario A vs. Scenario B vs. Current Situation).

Completely encapsulated inside `@st.fragment` and `st.form` so snapshot capture,
renaming, clearing, and chart perspective switching never re-trigger the 35,040-step
live dispatch simulation kernel.
"""

import copy
from typing import Any, Dict, List, Optional
import streamlit as st

from .state_and_helpers import (
    LoadSeries2025,
    CombinedSystemConfig,
    InteractionRulesConfig,
    CombinedFinancialConfig,
    CombinedSimulationResult,
    CombinedScenarioSnapshot,
    render_kpi_card,
    _load_fingerprint,
    _physical_sys_tuple,
    format_currency_value,
    build_baseline_tariff_fingerprint,
    capture_scenario_snapshot,
    recalculate_snapshot_on_active_load,
    generate_quick_ab_preset_snapshots,
    build_restore_widget_sync_payload,
    build_ab_comparison_matrix_df,
    create_ab_15y_tco_comparison_figure,
    create_ab_annual_cost_stack_figure,
    create_ab_supply_and_utilization_figure,
)
from .subtab6_isolated_pillars import _render_sub_ledger_html


def _hardware_badge(snap: CombinedScenarioSnapshot) -> str:
    """Formats a concise hardware summary badge for a saved snapshot card."""
    cfg = snap.system_config
    parts = [f"Grid Limit {cfg.grid_limit_kw:,.0f} kW"]
    if cfg.enable_solar:
        parts.append(f"PV {snap.solar_derivation.installed_kwp:,.1f} kWp")
    else:
        parts.append("PV Off")
    if cfg.enable_battery:
        parts.append(f"BESS {cfg.battery_capacity_kwh:,.0f} kWh / {cfg.battery_power_kw:,.0f} kW")
    else:
        parts.append("BESS Off")
    if cfg.enable_generator:
        parts.append(f"Gen {cfg.generator_rated_kw:,.0f} kW ({cfg.fuel_type})")
    else:
        parts.append("Gen Off")
    return " | ".join(parts)


def _apply_snapshot_to_live_editor(snapshot: CombinedScenarioSnapshot) -> None:
    """Commits a snapshot's configs and staged widget keys to live session state and clears stale caches."""
    payload = build_restore_widget_sync_payload(
        snapshot=snapshot,
        current_dso_tou_v=int(st.session_state.get("comb_fin_dso_tou_v", 0)),
    )
    st.session_state["comb_system_cfg"] = payload["system_config"]
    st.session_state["comb_rules_cfg"] = payload["rules_config"]
    st.session_state["comb_fin_cfg"] = payload["financial_config"]
    st.session_state["comb_pending_mix_widget_sync"] = payload["comb_pending_mix_widget_sync"]
    st.session_state["comb_pending_solar_widget_sync"] = payload["comb_pending_solar_widget_sync"]
    st.session_state["comb_pending_fin_widget_sync"] = payload["comb_pending_fin_widget_sync"]

    for stale_key in (
        "comb_dispatch_fp",
        "comb_sandbox_result",
        "comb_cached_excel_bytes",
        "comb_bess_sizing_fp",
        "comb_cached_dual_bess",
        "comb_cached_dual_bess_pair",
        "comb_gen_sizing_fp",
        "comb_cached_dual_gen",
        "comb_mix_preview_bundle",
        "comb_mix_preview_fp",
        "comb_mix_synced_sys_fp",
        "comb_latest_bottleneck_df",
    ):
        st.session_state.pop(stale_key, None)


def _render_executive_winner_and_kpis(
    snap_a: Optional[CombinedScenarioSnapshot],
    snap_b: Optional[CombinedScenarioSnapshot],
) -> None:
    """Renders Zone 2 Executive Winner Banner and 4 Delta KPI cards."""
    if snap_a is None and snap_b is None:
        return

    if snap_a is not None and snap_b is not None:
        curr_a = str(snap_a.financial_config.currency_code or "EUR")
        curr_b = str(snap_b.financial_config.currency_code or "EUR")
        same_curr = (curr_a == curr_b)
        curr = curr_a

        fk_a = snap_a.financial_kpis
        fk_b = snap_b.financial_kpis
        kp_a = snap_a.kpis
        kp_b = snap_b.kpis

        tco_winner = snap_a if fk_a.tco_15y_combined_eur <= fk_b.tco_15y_combined_eur else snap_b
        capex_winner = snap_a if fk_a.total_capex_eur <= fk_b.total_capex_eur else snap_b

        pb_a = fk_a.payback_years if fk_a.payback_years is not None else float("inf")
        pb_b = fk_b.payback_years if fk_b.payback_years is not None else float("inf")
        pb_winner_txt = (
            snap_a.name
            if pb_a < pb_b
            else (snap_b.name if pb_b < pb_a else ("Tie" if pb_a < float("inf") else "N/A"))
        )

        ov_a_ok = kp_a.remaining_overload_hours <= 0.05
        ov_b_ok = kp_b.remaining_overload_hours <= 0.05
        if ov_a_ok and ov_b_ok:
            ov_summary = "Both A & B achieve 0.0 hrs overload"
        elif ov_a_ok:
            ov_summary = f"{snap_a.name} achieves 0.0 hrs overload"
        elif ov_b_ok:
            ov_summary = f"{snap_b.name} achieves 0.0 hrs overload"
        else:
            ov_summary = (
                f"Lowest residual overload: "
                f"{snap_a.name if kp_a.remaining_overload_hours <= kp_b.remaining_overload_hours else snap_b.name}"
            )

        if same_curr:
            tco_diff = fk_b.tco_15y_combined_eur - fk_a.tco_15y_combined_eur
            capex_diff = fk_b.total_capex_eur - fk_a.total_capex_eur
            tco_delta_str = format_currency_value(tco_diff, curr, signed=True)
            capex_delta_str = format_currency_value(capex_diff, curr, signed=True)
            st.success(
                f":material/emoji_events: **Executive Comparison Winner Summary:**  \n"
                f"- **Lowest 15-Year TCO:** **{tco_winner.name}** ({format_currency_value(tco_winner.financial_kpis.tco_15y_combined_eur, curr)})  \n"
                f"- **Lowest Net CAPEX:** **{capex_winner.name}** ({format_currency_value(capex_winner.financial_kpis.total_capex_eur, curr)})  \n"
                f"- **Fastest Simple Payback:** **{pb_winner_txt}** | **Grid Compliance:** **{ov_summary}**"
            )
        else:
            tco_delta_str = "Mixed Currency"
            capex_delta_str = "Mixed Currency"
            st.warning(
                f":material/currency_exchange: **Mixed Currencies Detected ({curr_a} vs. {curr_b}):** "
                "Recalculate snapshots on the active baseline currency above for apples-to-apples financial deltas."
            )

        k1, k2, k3, k4 = st.columns(4)
        with k1:
            render_kpi_card(
                title="15-Year TCO (Delta B vs. A)",
                value=tco_delta_str,
                subtext=(
                    f"A: {format_currency_value(fk_a.tco_15y_combined_eur, curr_a)} | "
                    f"B: {format_currency_value(fk_b.tco_15y_combined_eur, curr_b)}"
                ),
                status="ok" if same_curr else "default",
            )
        with k2:
            render_kpi_card(
                title="Net CAPEX (Delta B vs. A)",
                value=capex_delta_str,
                subtext=(
                    f"A: {format_currency_value(fk_a.total_capex_eur, curr_a)} | "
                    f"B: {format_currency_value(fk_b.total_capex_eur, curr_b)}"
                ),
                status="default",
            )
        with k3:
            pb_a_str = f"{fk_a.payback_years:.1f} yrs" if fk_a.payback_years is not None else "N/A"
            pb_b_str = f"{fk_b.payback_years:.1f} yrs" if fk_b.payback_years is not None else "N/A"
            render_kpi_card(
                title="Simple Payback (A vs. B)",
                value=f"{pb_a_str} vs. {pb_b_str}",
                subtext=(
                    f"Y1 Savings A: {format_currency_value(fk_a.annual_savings_eur, curr_a, signed=True)} | "
                    f"B: {format_currency_value(fk_b.annual_savings_eur, curr_b, signed=True)}"
                ),
                status="ok" if (fk_a.payback_years is not None or fk_b.payback_years is not None) else "alert",
            )
        with k4:
            render_kpi_card(
                title="Remaining Overload (A vs. B)",
                value=f"{kp_a.remaining_overload_hours:,.1f} vs. {kp_b.remaining_overload_hours:,.1f} hrs",
                subtext=(
                    f"Grid Peak A: {kp_a.new_grid_peak_kw:,.1f} kW | "
                    f"B: {kp_b.new_grid_peak_kw:,.1f} kW"
                ),
                status="ok" if (ov_a_ok and ov_b_ok) else "alert",
            )
        return

    # Single snapshot saved (A or B only)
    single_slot = "A" if snap_a is not None else "B"
    single_snap = snap_a if snap_a is not None else snap_b
    assert single_snap is not None
    fk = single_snap.financial_kpis
    kp = single_snap.kpis
    curr = str(single_snap.financial_config.currency_code or "EUR")
    pb_str = f"{fk.payback_years:.1f} yrs" if fk.payback_years is not None else "N/A"

    st.info(
        f":material/info: **Slot {single_slot} Saved ({single_snap.name}):** "
        f"Save a second configuration in Slot {'B' if single_slot == 'A' else 'A'} to unlock head-to-head B vs. A deltas."
    )
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        render_kpi_card(
            title=f"Slot {single_slot} Net CAPEX",
            value=format_currency_value(fk.total_capex_eur, curr),
            subtext=f"Avoided upgrade: {format_currency_value(fk.avoided_grid_upgrade_capex_eur, curr)}",
            status="default",
        )
    with k2:
        render_kpi_card(
            title=f"Slot {single_slot} Year-1 Net Savings",
            value=f"{format_currency_value(fk.annual_savings_eur, curr, signed=True)} / yr",
            subtext=f"Baseline bill: {format_currency_value(fk.baseline_total_opex_eur, curr)}/yr",
            status="ok" if fk.annual_savings_eur > 0 else "alert",
        )
    with k3:
        render_kpi_card(
            title=f"Slot {single_slot} Payback & 15Y TCO",
            value=f"{pb_str} | {format_currency_value(fk.tco_15y_combined_eur, curr)}",
            subtext=f"15Y TCO Savings: {format_currency_value(fk.tco_15y_savings_eur, curr, signed=True)}",
            status="ok" if fk.tco_15y_savings_eur > 0 else "default",
        )
    with k4:
        render_kpi_card(
            title=f"Slot {single_slot} Grid Peak & Overload",
            value=f"{kp.new_grid_peak_kw:,.1f} kW ({kp.remaining_overload_hours:,.1f} hrs)",
            subtext=f"Baseline overload: {kp.baseline_overload_hours:,.1f} hrs",
            status="ok" if kp.remaining_overload_hours <= 0.05 else "alert",
        )


@st.fragment
def _render_ab_chart_gallery_fragment(
    snap_a: Optional[CombinedScenarioSnapshot],
    snap_b: Optional[CombinedScenarioSnapshot],
) -> None:
    """Zone 3: Isolated comparison chart perspective selector."""
    if snap_a is None and snap_b is None:
        return

    with st.container(border=True):
        st.markdown("##### :material/analytics: Visual Scenario Comparison")
        chart_view = st.radio(
            "Comparison Chart Perspective",
            options=[
                "15-Year TCO & Break-Even",
                "Annual Cost Structure (4-Pillar + O&M)",
                "Supply Mix & Asset Utilization",
            ],
            index=0,
            horizontal=True,
            key="comb_ab_chart_gallery_sel",
            label_visibility="collapsed",
        )

        if chart_view == "15-Year TCO & Break-Even":
            fig = create_ab_15y_tco_comparison_figure(snap_a, snap_b)
        elif chart_view == "Annual Cost Structure (4-Pillar + O&M)":
            fig = create_ab_annual_cost_stack_figure(snap_a, snap_b)
        else:
            fig = create_ab_supply_and_utilization_figure(snap_a, snap_b)

        st.plotly_chart(
            fig,
            use_container_width=True,
            config={"scrollZoom": False, "displayModeBar": "hover", "responsive": True},
            key=f"comb_ab_chart_{chart_view.replace(' ', '_').replace('(', '').replace(')', '').replace('&', '').lower()}",
        )


def _render_comparison_ledger(
    snap_a: Optional[CombinedScenarioSnapshot],
    snap_b: Optional[CombinedScenarioSnapshot],
) -> None:
    """Zone 4: Detailed Side-by-Side Technical & Economic Ledger using dark HTML sub-ledger styling."""
    if snap_a is None and snap_b is None:
        return

    df_comp = build_ab_comparison_matrix_df(snap_a, snap_b)
    if df_comp.empty:
        return

    ref = snap_a if snap_a is not None else snap_b
    assert ref is not None
    curr = str(ref.financial_config.currency_code or "EUR")

    ledger_rows: List[Dict[str, Any]] = []
    last_cat = None
    for rec in df_comp.to_dict(orient="records"):
        cat = str(rec["Category"])
        if cat != last_cat:
            ledger_rows.append({"group": cat})
            last_cat = cat
        delta_txt = str(rec["Delta (B vs. A)"])
        hl = None
        if delta_txt.startswith("+") or delta_txt.startswith("-"):
            metric_low = str(rec["Metric / KPI"]).lower()
            is_cost_or_overload = any(
                kw in metric_low
                for kw in ("capex", "cost", "opex", "pillar", "bill", "overload", "tco", "payback", "peak", "runtime")
            )
            is_positive_benefit = any(kw in metric_low for kw in ("savings", "npv", "irr", "bcr", "export revenue"))
            if is_positive_benefit:
                hl = "#22C55E" if delta_txt.startswith("+") else "#EF4444"
            elif is_cost_or_overload and not metric_low.startswith("avoided"):
                hl = "#22C55E" if delta_txt.startswith("-") else "#F59E0B"
        ledger_rows.append({
            "cells": [
                str(rec["Metric / KPI"]),
                str(rec["Current Situation"]),
                str(rec["Scenario A"]),
                str(rec["Scenario B"]),
                delta_txt,
            ],
            "highlight": hl,
        })

    col_a_hdr = f"Scenario A ({snap_a.name[:22]})" if snap_a else "Scenario A (Empty)"
    col_b_hdr = f"Scenario B ({snap_b.name[:22]})" if snap_b else "Scenario B (Empty)"
    pb_summary = (
        f"A: {snap_a.financial_kpis.payback_years:.1f}y" if (snap_a and snap_a.financial_kpis.payback_years is not None) else "A: N/A"
    ) + " | " + (
        f"B: {snap_b.financial_kpis.payback_years:.1f}y" if (snap_b and snap_b.financial_kpis.payback_years is not None) else "B: N/A"
    )

    with st.container(border=True):
        st.markdown("##### :material/table_chart: Detailed Side-by-Side Comparison Matrix")
        st.markdown(
            _render_sub_ledger_html(
                header_title=f"Technical &amp; Financial Comparison ({curr})",
                columns=["Metric / KPI", "Current Situation", col_a_hdr, col_b_hdr, "Delta (B vs. A)"],
                rows=ledger_rows,
                footer_cells=[
                    "Summary: 15-Year TCO &amp; Payback",
                    format_currency_value(ref.financial_kpis.tco_15y_baseline_eur, curr),
                    format_currency_value(snap_a.financial_kpis.tco_15y_combined_eur, str(snap_a.financial_config.currency_code or "EUR")) if snap_a else "—",
                    format_currency_value(snap_b.financial_kpis.tco_15y_combined_eur, str(snap_b.financial_config.currency_code or "EUR")) if snap_b else "—",
                    pb_summary,
                ],
                accent_color="#38BDF8",
                is_enabled=True,
                currency_code=curr,
                left_aligned_cols=1,
            ),
            unsafe_allow_html=True,
        )
        with st.expander(":material/dataset: Copy / Inspect Tabular Matrix", expanded=False):
            st.dataframe(df_comp, use_container_width=True, hide_index=True)


@st.fragment
def render_subtab7_scenario_comparison(
    sim_res: CombinedSimulationResult,
    load_series: LoadSeries2025,
) -> None:
    """
    Renders Sub-Tab 7: Scenario Comparison (Scenario A vs. Scenario B vs. Current Situation).
      - Zone 1: Quick-Generate A/B Preset Pair, Consistency Guard, and Slot A / Slot B cards
      - Zone 2: Executive Winner Banner & 4 Delta KPI cards
      - Zone 3: Isolated Plotly Comparison Chart Gallery
      - Zone 4: Detailed Technical & 4-Pillar/15Y Financial Comparison Matrix
    """
    cur_sys: CombinedSystemConfig = st.session_state["comb_system_cfg"]
    cur_rules: InteractionRulesConfig = st.session_state["comb_rules_cfg"]
    cur_fin: CombinedFinancialConfig = st.session_state["comb_fin_cfg"]

    saved_scenarios: Dict[str, CombinedScenarioSnapshot] = st.session_state.setdefault(
        "comb_saved_scenarios", {}
    )

    pending_names = st.session_state.pop("comb_pending_slot_name_sync", None)
    if isinstance(pending_names, dict):
        for wk, wv in pending_names.items():
            st.session_state[wk] = wv

    cur_load_fp = _load_fingerprint(load_series)
    cur_tariff_fp = build_baseline_tariff_fingerprint(cur_fin)
    cur_phys_fp = _physical_sys_tuple(cur_sys)

    # Zone 1: Quick-Generate Bar + Consistency Guard + Slot A & Slot B Cards
    with st.container(border=True):
        hdr_c1, hdr_c2 = st.columns([2.2, 1.4])
        with hdr_c1:
            st.markdown("##### :material/compare_arrows: Scenario A vs. Scenario B Workbench")
            st.caption(
                "Capture lightweight snapshots (< 50 KB) of your configured systems to compare "
                "Current Situation vs. Scenario A vs. Scenario B side by side without re-running the live kernel."
            )
        with hdr_c2:
            st.write("")
            quick_gen_clicked = st.button(
                "Quick-Generate A/B Preset Pair",
                icon=":material/auto_awesome_motion:",
                use_container_width=True,
                key="comb_btn_quick_generate_ab",
                help=(
                    "Automatically computes Scenario A (100% Battery - Zero Overload) and "
                    "Scenario B (Compact 2h Battery + Generator) on your active load profile & solar settings."
                ),
            )

        if quick_gen_clicked:
            if float(load_series.total_energy_kwh) <= 0.0:
                st.warning(
                    ":material/info: Load or select a consumption profile in **1. Consumption** "
                    "before generating an A/B preset pair."
                )
            else:
                qa_snap, qb_snap = generate_quick_ab_preset_snapshots(
                    load_series=load_series,
                    base_sys_cfg=cur_sys,
                    base_rules_cfg=cur_rules,
                    fin_cfg=cur_fin,
                )
                saved_scenarios["A"] = qa_snap
                saved_scenarios["B"] = qb_snap
                st.session_state["comb_pending_slot_name_sync"] = {
                    "comb_sc_name_input_A": qa_snap.name,
                    "comb_sc_name_input_B": qb_snap.name,
                }
                st.session_state.pop("comb_cached_excel_bytes", None)
                st.rerun(scope="fragment")

        # Consistency Guard: detect Load Profile or Baseline Tariff / Currency changes since snapshot capture
        stale_reasons: List[str] = []
        for s_id in ("A", "B"):
            s_obj = saved_scenarios.get(s_id)
            if s_obj is None:
                continue
            if tuple(s_obj.load_fingerprint) != tuple(cur_load_fp):
                stale_reasons.append(f"Slot {s_id} load profile differs")
            elif tuple(s_obj.baseline_tariff_fingerprint) != tuple(cur_tariff_fp):
                stale_reasons.append(f"Slot {s_id} baseline tariff/currency differs")

        if stale_reasons:
            g_col1, g_col2 = st.columns([2.4, 1.2])
            with g_col1:
                st.warning(
                    f":material/warning: **Baseline Changed ({', '.join(stale_reasons)}):** "
                    "Your active consumption profile, currency, or electricity tariff has changed since "
                    "these snapshots were saved. Recalculate to keep comparisons aligned."
                )
            with g_col2:
                st.write("")
                if st.button(
                    "Recalculate Snapshots on Active Baseline",
                    icon=":material/sync:",
                    type="primary",
                    use_container_width=True,
                    key="comb_btn_recalc_snapshots",
                ):
                    for s_id in list(saved_scenarios.keys()):
                        saved_scenarios[s_id] = recalculate_snapshot_on_active_load(
                            snapshot=saved_scenarios[s_id],
                            load_series=load_series,
                            active_fin_cfg=cur_fin,
                        )
                    st.session_state.pop("comb_cached_excel_bytes", None)
                    st.rerun(scope="app")

        col_a, col_b = st.columns(2, gap="medium")
        for col_slot, slot_id, default_name in [
            (col_a, "A", "Scenario A: 100% Battery"),
            (col_b, "B", "Scenario B: 2h Battery + Generator"),
        ]:
            snap: Optional[CombinedScenarioSnapshot] = saved_scenarios.get(slot_id)
            with col_slot:
                with st.container(border=True):
                    if snap is not None:
                        s_curr = str(snap.financial_config.currency_code or "EUR")
                        fk_s = snap.financial_kpis
                        pb_s = f"{fk_s.payback_years:.1f} yrs" if fk_s.payback_years is not None else "N/A"
                        st.markdown(f"###### :material/bookmark_added: Slot {slot_id}: {snap.name}")
                        st.caption(f"Captured {snap.created_at} | `{_hardware_badge(snap)}`")
                        st.markdown(
                            f"**Net CAPEX:** {format_currency_value(fk_s.total_capex_eur, s_curr)} | "
                            f"**Y1 Savings:** {format_currency_value(fk_s.annual_savings_eur, s_curr, signed=True)}/yr | "
                            f"**Payback:** {pb_s} | "
                            f"**15Y TCO:** {format_currency_value(fk_s.tco_15y_combined_eur, s_curr)}"
                        )
                    else:
                        st.markdown(f"###### :material/bookmark_border: Slot {slot_id} (Empty)")
                        st.caption(
                            "Configure your system in Sub-Tabs 1–6 and capture it here for side-by-side comparison."
                        )

                    input_key = f"comb_sc_name_input_{slot_id}"
                    seed_name = snap.name if snap is not None else default_name
                    with st.form(f"comb_save_slot_{slot_id}_form"):
                        name_input = st.text_input(
                            f"Scenario {slot_id} Label",
                            value=st.session_state.get(input_key, seed_name),
                            key=input_key,
                            placeholder=default_name,
                        )
                        save_clicked = st.form_submit_button(
                            f"Save Current System as Scenario {slot_id}",
                            icon=":material/photo_camera:",
                            type="primary",
                            use_container_width=True,
                        )

                    if save_clicked:
                        captured = capture_scenario_snapshot(
                            sim_res=sim_res,
                            fin_cfg=cur_fin,
                            slot_id=slot_id,
                            custom_name=(name_input or default_name).strip(),
                            load_fp=cur_load_fp,
                            physical_fp=cur_phys_fp,
                        )
                        saved_scenarios[slot_id] = captured
                        st.session_state.pop("comb_cached_excel_bytes", None)
                        st.rerun(scope="fragment")

                    if snap is not None:
                        act1, act2 = st.columns([1.6, 1.0])
                        with act1:
                            if st.button(
                                "Load into Live Editor",
                                icon=":material/upload:",
                                use_container_width=True,
                                key=f"comb_btn_load_slot_{slot_id}",
                                help="Restores all technical, rules, and tariff/hardware settings into Sub-Tabs 1–6.",
                            ):
                                _apply_snapshot_to_live_editor(copy.deepcopy(snap))
                                st.rerun(scope="app")
                        with act2:
                            if st.button(
                                "Clear Slot",
                                icon=":material/delete:",
                                use_container_width=True,
                                key=f"comb_btn_clear_slot_{slot_id}",
                            ):
                                saved_scenarios.pop(slot_id, None)
                                st.session_state.pop("comb_cached_excel_bytes", None)
                                st.rerun(scope="fragment")

    snap_a = saved_scenarios.get("A")
    snap_b = saved_scenarios.get("B")

    if snap_a is None and snap_b is None:
        st.info(
            ":material/compare_arrows: **No scenarios saved yet.** "
            "Use **Save Current System as Scenario A / B** above or click **Quick-Generate A/B Preset Pair** "
            "to generate an instant head-to-head comparison against the Current Situation."
        )
        return

    # Zone 2: Executive Winner Banner & 4 Delta KPIs
    _render_executive_winner_and_kpis(snap_a, snap_b)

    # Zone 3: Isolated Comparison Chart Gallery
    _render_ab_chart_gallery_fragment(snap_a, snap_b)

    # Zone 4: Detailed Technical & Financial Comparison Matrix
    _render_comparison_ledger(snap_a, snap_b)
