"""
Subtab 7: Scenario Comparison (Scenario A vs. Scenario B vs. Current Situation).

Completely encapsulated inside `@st.fragment` and `st.form` so snapshot capture,
renaming, clearing, and chart perspective switching never re-trigger the 35,040-step
live dispatch simulation kernel.
"""

import copy
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd
import streamlit as st

from .state_and_helpers import (
    LoadSeries2025,
    CombinedSystemConfig,
    InteractionRulesConfig,
    CombinedFinancialConfig,
    CombinedSimulationResult,
    CombinedScenarioSnapshot,
    DEFAULT_POWERFLOW_COLORS,
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
    compute_incremental_bwl_evaluation,
    build_segmented_comparison_tables,
    snapshot_to_sim_view,
    create_combined_dispatch_soc_figure,
    create_supply_mix_pie_figure,
    create_component_utilization_bars_figure,
    create_financial_tco_trajectory_figure,
    create_financial_waterfall_bridge_figure,
    create_ab_15y_tco_comparison_figure,
    create_ab_load_profile_overlay_figure,
    sync_side_by_side_yaxis,
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


def _render_scenario_scorecard_column(slot_id: str, snap: CombinedScenarioSnapshot) -> None:
    """Renders Sub-Tab 6.3 + Level 3 style KPI cards inside one scenario column for direct visual comparison."""
    kp = snap.kpis
    ut = snap.utilization_diagnostics
    has_fin = bool(getattr(snap.system_config, "enable_financials", False) and snap.financial_kpis is not None)
    fk = snap.financial_kpis
    curr = str(snap.financial_config.currency_code or "EUR")

    with st.container(border=True):
        st.markdown(f"###### Scenario {slot_id}: {snap.name}")
        st.caption(_hardware_badge(snap))

        if has_fin and fk is not None:
            pb_str = f"{fk.payback_years:.1f} yrs" if fk.payback_years is not None else "N/A"
            irr_str = f"{fk.irr_15y_pct:.1f}%" if fk.irr_15y_pct is not None else "N/A"
            f1, f2 = st.columns(2)
            with f1:
                render_kpi_card(
                    title="Total Investment",
                    value=format_currency_value(fk.total_capex_eur, curr),
                    subtext=(
                        f"Avoided grid upgrade: -{format_currency_value(fk.avoided_grid_upgrade_capex_eur, curr)}"
                        if fk.avoided_grid_upgrade_capex_eur > 0
                        else "Net upfront system cost"
                    ),
                    status="default",
                )
            with f2:
                render_kpi_card(
                    title="Annual Savings (Year 1)",
                    value=f"{format_currency_value(fk.annual_savings_eur, curr, signed=True)} / yr",
                    subtext=f"New cost: {format_currency_value(fk.total_annual_opex_eur, curr)}/yr",
                    status="ok" if fk.annual_savings_eur > 0 else "alert",
                )
            f3, f4 = st.columns(2)
            with f3:
                render_kpi_card(
                    title="Payback Period",
                    value=pb_str,
                    subtext=f"NPV: {format_currency_value(fk.npv_15y_eur, curr, signed=True)} | IRR: {irr_str}",
                    status="ok" if fk.payback_years is not None else "alert",
                )
            with f4:
                render_kpi_card(
                    title="15-Year Net Profit",
                    value=format_currency_value(fk.tco_15y_savings_eur, curr, signed=True),
                    subtext=f"15Y total cost: {format_currency_value(fk.tco_15y_combined_eur, curr)}",
                    status="ok" if fk.tco_15y_savings_eur > 0 else "alert",
                )

        t1, t2 = st.columns(2)
        with t1:
            render_kpi_card(
                title="Grid Peak Demand",
                value=f"{kp.original_peak_kw:,.1f} → {kp.new_grid_peak_kw:,.1f} kW",
                subtext=f"Limit {kp.grid_limit_kw:,.0f} kW (-{kp.peak_reduction_kw:,.1f} kW shaved)",
                status="ok" if kp.grid_limit_met else "alert",
            )
        with t2:
            render_kpi_card(
                title="Remaining Overload",
                value=f"{kp.remaining_overload_hours:,.1f} hrs | {kp.remaining_overload_kwh:,.0f} kWh",
                subtext="0.0 hrs remaining" if kp.remaining_overload_hours <= 0.05 else f"{kp.overload_eliminated_pct:.1f}% eliminated",
                status="ok" if kp.remaining_overload_hours <= 0.05 else "alert",
            )
        t3, t4 = st.columns(2)
        with t3:
            render_kpi_card(
                title="Electricity Supply Split",
                value=f"Grid {ut.grid_direct_pct:.0f}% | Solar {ut.solar_direct_pct:.0f}%",
                subtext=f"Battery {ut.battery_discharge_pct:.0f}% | Generator {ut.generator_direct_pct:.0f}%",
                status="default",
            )
        with t4:
            render_kpi_card(
                title="System Operation",
                value=f"{kp.battery_equivalent_cycles:.1f} cyc | {kp.generator_runtime_hours:,.1f} hrs",
                subtext=(
                    f"Gen fuel: {kp.generator_fuel_total:,.0f} {kp.generator_fuel_unit}"
                    if snap.system_config.enable_generator
                    else f"On-site supply: {max(0.0, 100.0 - ut.grid_direct_pct):.1f}%"
                ),
                status="default",
            )


def _render_executive_winner_and_kpis(
    snap_a: Optional[CombinedScenarioSnapshot],
    snap_b: Optional[CombinedScenarioSnapshot],
) -> None:
    """Renders Zone 2 Winner Banner and direct side-by-side single-scenario KPI scorecards."""
    if snap_a is None and snap_b is None:
        return

    has_fin_a = bool(snap_a is not None and getattr(snap_a.system_config, "enable_financials", False))
    has_fin_b = bool(snap_b is not None and getattr(snap_b.system_config, "enable_financials", False))
    both_fin = (snap_a is not None and snap_b is not None and has_fin_a and has_fin_b)

    if snap_a is not None and snap_b is not None:
        kp_a, kp_b = snap_a.kpis, snap_b.kpis
        ut_a, ut_b = snap_a.utilization_diagnostics, snap_b.utilization_diagnostics
        ov_a_ok, ov_b_ok = kp_a.remaining_overload_hours <= 0.05, kp_b.remaining_overload_hours <= 0.05
        if ov_a_ok and ov_b_ok:
            ov_summary = "Both A & B meet the grid limit with 0.0 hrs overload"
        elif ov_a_ok or ov_b_ok:
            ov_summary = f"{snap_a.name if ov_a_ok else snap_b.name} meets the grid limit with 0.0 hrs overload"
        else:
            better = snap_a if kp_a.remaining_overload_hours <= kp_b.remaining_overload_hours else snap_b
            ov_summary = f"Lowest remaining overload: {better.name}"

        if not both_fin:
            peak_winner = snap_a if kp_a.new_grid_peak_kw <= kp_b.new_grid_peak_kw else snap_b
            onsite_a = max(0.0, 100.0 - float(ut_a.grid_direct_pct))
            onsite_b = max(0.0, 100.0 - float(ut_b.grid_direct_pct))
            onsite_winner = snap_a if onsite_a >= onsite_b else snap_b
            st.success(
                f":material/emoji_events: **Side-by-Side Comparison Summary (Financials Off):**  \n"
                f"- **Lowest Grid Peak:** **{peak_winner.name}** ({peak_winner.kpis.new_grid_peak_kw:,.1f} kW)  \n"
                f"- **Highest On-Site Supply:** **{onsite_winner.name}** ({max(onsite_a, onsite_b):.1f}%)  \n"
                f"- **Grid Compliance:** **{ov_summary}**"
            )
            st.info(
                ":material/info: **Financials Off:** Enable **Financials** in the top bar and re-save a scenario to compare investment cost, savings, and payback."
            )
        else:
            curr_a = str(snap_a.financial_config.currency_code or "EUR")
            curr_b = str(snap_b.financial_config.currency_code or "EUR")
            fk_a, fk_b = snap_a.financial_kpis, snap_b.financial_kpis
            if curr_a == curr_b:
                tco_winner = snap_a if fk_a.tco_15y_combined_eur <= fk_b.tco_15y_combined_eur else snap_b
                capex_winner = snap_a if fk_a.total_capex_eur <= fk_b.total_capex_eur else snap_b
                pb_a = fk_a.payback_years if fk_a.payback_years is not None else float("inf")
                pb_b = fk_b.payback_years if fk_b.payback_years is not None else float("inf")
                pb_winner_txt = snap_a.name if pb_a < pb_b else (snap_b.name if pb_b < pb_a else ("Tie" if pb_a < float("inf") else "N/A"))
                st.success(
                    f":material/emoji_events: **Comparison Summary:**  \n"
                    f"- **Best 15-Year Cost / Profit:** **{tco_winner.name}** ({format_currency_value(tco_winner.financial_kpis.tco_15y_combined_eur, curr_a)} total cost)  \n"
                    f"- **Lowest Upfront Cost:** **{capex_winner.name}** ({format_currency_value(capex_winner.financial_kpis.total_capex_eur, curr_a)})  \n"
                    f"- **Fastest Payback:** **{pb_winner_txt}** | **Grid Limit:** **{ov_summary}**"
                )
            else:
                st.warning(
                    f":material/currency_exchange: **Mixed Currencies ({curr_a} vs. {curr_b}):** "
                    "Recalculate snapshots on the active baseline currency above for same-currency financial comparisons."
                )

        c_left, c_right = st.columns(2)
        with c_left:
            _render_scenario_scorecard_column("A", snap_a)
        with c_right:
            _render_scenario_scorecard_column("B", snap_b)
        return

    single_slot = "A" if snap_a is not None else "B"
    single_snap = snap_a if snap_a is not None else snap_b
    assert single_snap is not None
    st.info(
        f":material/info: **Slot {single_slot} Saved ({single_snap.name}):** "
        f"Save a second system in Slot {'B' if single_slot == 'A' else 'A'} for direct side-by-side comparison."
    )
    _render_scenario_scorecard_column(single_slot, single_snap)


def _build_supply_mix_mini_df(snap: CombinedScenarioSnapshot) -> pd.DataFrame:
    """Builds the 4-row MWh/yr + % + Peak kW summary table matching Sub-Tab 5."""
    d = snap.utilization_diagnostics
    return pd.DataFrame([
        {"Source": "Grid Direct", "Energy (MWh/yr)": round(d.grid_direct_kwh / 1000.0, 1), "Share (%)": round(d.grid_direct_pct, 1), "Peak (kW)": round(d.grid_peak_import_kw, 1)},
        {"Source": "Solar Direct", "Energy (MWh/yr)": round(d.solar_direct_kwh / 1000.0, 1), "Share (%)": round(d.solar_direct_pct, 1), "Peak (kW)": round(d.solar_peak_contribution_kw, 1)},
        {"Source": "Battery Discharge", "Energy (MWh/yr)": round(d.battery_discharge_kwh / 1000.0, 1), "Share (%)": round(d.battery_discharge_pct, 1), "Peak (kW)": round(d.bess_peak_discharged_kw, 1)},
        {"Source": "Generator Output", "Energy (MWh/yr)": round(d.generator_direct_kwh / 1000.0, 1), "Share (%)": round(d.generator_direct_pct, 1), "Peak (kW)": round(d.gen_peak_used_kw, 1)},
    ])


def _render_side_by_side_charts(
    items: List[Tuple[str, CombinedScenarioSnapshot]],
    builder_fn,
    chart_key_prefix: str,
    sync_axes: Optional[Tuple[str, ...]] = None,
) -> None:
    """Renders single-scenario Plotly figures side-by-side with optional Y-axis synchronization."""
    built = [(s_id, snap, builder_fn(snap)) for s_id, snap in items]
    if len(built) == 2 and sync_axes:
        sync_side_by_side_yaxis(built[0][2], built[1][2], axes=sync_axes)
    cols = st.columns(len(built))
    for col, (s_id, snap, fig) in zip(cols, built):
        with col:
            st.markdown(f"**Scenario {s_id}: {snap.name}**")
            st.plotly_chart(
                fig,
                use_container_width=True,
                config={"scrollZoom": False, "displayModeBar": "hover", "responsive": True},
                key=f"{chart_key_prefix}_{s_id}",
            )


def _render_supply_mix_tab(
    active_items: List[Tuple[str, CombinedScenarioSnapshot]],
    chart_cfg: Dict[str, Any],
) -> None:
    """Renders Sub-Tab 5 Supply Mix Donut + mini table and System Usage bars side by side."""
    st.caption("Direct comparison using the Sub-Tab 5 Supply Mix Donut and System Usage bars.")
    mix_cols = st.columns(len(active_items))
    for col, (s_id, snap) in zip(mix_cols, active_items):
        with col:
            st.markdown(f"**Scenario {s_id}: {snap.name}**")
            st.plotly_chart(
                create_supply_mix_pie_figure(snap.utilization_diagnostics, height=320),
                use_container_width=True,
                config=chart_cfg,
                key=f"comb_ab_sub5_pie_{s_id}",
            )
            st.dataframe(
                _build_supply_mix_mini_df(snap),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Energy (MWh/yr)": st.column_config.NumberColumn(format="%.1f MWh"),
                    "Share (%)": st.column_config.NumberColumn(format="%.1f%%"),
                    "Peak (kW)": st.column_config.NumberColumn(format="%.1f kW"),
                },
            )
    st.markdown("###### How Much of Your System You Actually Use")
    _render_side_by_side_charts(
        active_items,
        lambda s: create_component_utilization_bars_figure(s.utilization_diagnostics, height=310),
        chart_key_prefix="comb_ab_sub5_util",
    )


def _render_financial_tabs(
    snap_a: Optional[CombinedScenarioSnapshot],
    snap_b: Optional[CombinedScenarioSnapshot],
    fin_items: List[Tuple[str, CombinedScenarioSnapshot]],
    load_series: Optional[LoadSeries2025],
    chart_cfg: Dict[str, Any],
) -> None:
    """Renders Sub-Tab 6.3 Financial charts inside 2 instant client-side inner st.tabs."""
    ft_tco, ft_wf = st.tabs([
        ":material/trending_up: 15-Year TCO & Payback",
        ":material/stacked_bar_chart: Annual Cost Bridge",
    ])
    with ft_tco:
        st.plotly_chart(
            create_ab_15y_tco_comparison_figure(snap_a, snap_b, height=390),
            use_container_width=True,
            config=chart_cfg,
            key="comb_ab_fin_tco_shared",
        )
        _render_side_by_side_charts(
            fin_items,
            lambda s: create_financial_tco_trajectory_figure(snapshot_to_sim_view(s, load_series)),
            chart_key_prefix="comb_ab_fin_amort",
            sync_axes=("yaxis", "yaxis2"),
        )
    with ft_wf:
        _render_side_by_side_charts(
            fin_items,
            lambda s: create_financial_waterfall_bridge_figure(snapshot_to_sim_view(s, load_series)),
            chart_key_prefix="comb_ab_fin_wf",
            sync_axes=("yaxis",),
        )


@st.fragment
def _render_power_flow_lazy_fragment(
    snap_a: Optional[CombinedScenarioSnapshot],
    snap_b: Optional[CombinedScenarioSnapshot],
    active_items: List[Tuple[str, CombinedScenarioSnapshot]],
    load_series: Optional[LoadSeries2025],
    chart_cfg: Dict[str, Any],
) -> None:
    """Lazy-loaded fragment for heavy 35,040-step WebGL Power Flow comparison charts."""
    st.caption(
        "Enable a chart below to inspect 15-minute data (35,040 steps). "
        "Keeping these off by default keeps tab switching and snapshot saving fast."
    )
    tg1, tg2 = st.columns(2)
    with tg1:
        show_overlay = st.toggle(
            "Show Direct Grid Load & Battery SoC Overlay (35,040 steps)",
            value=False,
            key="comb_ab_show_overlay_pf",
        )
    with tg2:
        show_sbs = st.toggle(
            "Show Full Power Flow & Battery Level Side by Side (35,040 steps)",
            value=False,
            key="comb_ab_show_side_by_side_pf",
        )

    if show_overlay:
        st.plotly_chart(
            create_ab_load_profile_overlay_figure(
                snap_a,
                snap_b,
                baseline_load_kw=getattr(load_series, "power_kw", None),
                timestamps=getattr(load_series, "timestamps", None),
                timeframe="Full Year",
            ),
            use_container_width=True,
            config=chart_cfg,
            key="comb_ab_pf_overlay",
        )

    if show_sbs:
        if any(getattr(s, "dispatch_f32_dict", None) is None for _, s in active_items):
            st.caption("Tip: Re-save older snapshots once to display full Solar, Battery, and Generator traces.")
        clr = dict(st.session_state.get("comb_powerflow_colors") or DEFAULT_POWERFLOW_COLORS)
        _render_side_by_side_charts(
            active_items,
            lambda s: create_combined_dispatch_soc_figure(snapshot_to_sim_view(s, load_series), color_overrides=clr),
            chart_key_prefix="comb_ab_lvl3_pf",
            sync_axes=("yaxis",),
        )


@st.fragment
def _render_ab_chart_gallery_fragment(
    snap_a: Optional[CombinedScenarioSnapshot],
    snap_b: Optional[CombinedScenarioSnapshot],
    load_series: Optional[LoadSeries2025] = None,
) -> None:
    """Zone 3: Instant client-side st.tabs visual comparison + lazy Power Flow fragment."""
    active_items: List[Tuple[str, CombinedScenarioSnapshot]] = []
    if snap_a is not None:
        active_items.append(("A", snap_a))
    if snap_b is not None:
        active_items.append(("B", snap_b))
    if not active_items:
        return

    any_fin = any(bool(getattr(s.system_config, "enable_financials", False) and s.financial_kpis is not None) for _, s in active_items)
    chart_cfg = {"scrollZoom": False, "displayModeBar": "hover", "responsive": True}

    with st.container(border=True):
        st.markdown("##### :material/analytics: Visual Scenario Comparison")
        if any_fin:
            tab_mix, tab_fin, tab_pf = st.tabs([
                ":material/donut_large: Supply Mix & System Usage",
                ":material/account_balance: Financial Charts",
                ":material/monitoring: Power Flow & Battery Level",
            ])
            with tab_mix:
                _render_supply_mix_tab(active_items, chart_cfg)
            with tab_fin:
                fin_items = [
                    (s_id, s)
                    for s_id, s in active_items
                    if getattr(s.system_config, "enable_financials", False) and s.financial_kpis is not None
                ]
                if len(fin_items) < len(active_items):
                    st.caption("Financials are off on one saved slot — showing charts for the slot with Financials enabled.")
                _render_financial_tabs(snap_a, snap_b, fin_items, load_series, chart_cfg)
            with tab_pf:
                _render_power_flow_lazy_fragment(snap_a, snap_b, active_items, load_series, chart_cfg)
        else:
            tab_mix, tab_pf = st.tabs([
                ":material/donut_large: Supply Mix & System Usage",
                ":material/monitoring: Power Flow & Battery Level",
            ])
            with tab_mix:
                _render_supply_mix_tab(active_items, chart_cfg)
            with tab_pf:
                _render_power_flow_lazy_fragment(snap_a, snap_b, active_items, load_series, chart_cfg)


def _highlight_delta_color(metric_low: str, delta_txt: str) -> Optional[str]:
    """Determines semantic green/amber/red highlight color for a scenario B vs. A delta."""
    if not (delta_txt.startswith("+") or delta_txt.startswith("-")):
        return None
    is_positive_benefit = any(
        kw in metric_low
        for kw in ("savings", "npv", "irr", "bcr", "export revenue", "autarky", "shaved", "eliminated")
    )
    if is_positive_benefit:
        return "#22C55E" if delta_txt.startswith("+") else "#EF4444"
    is_cost_or_overload = any(
        kw in metric_low
        for kw in ("capex", "cost", "opex", "pillar", "bill", "overload", "tco", "payback", "peak", "runtime", "import", "unused battery value", "lcoe")
    )
    if is_cost_or_overload and not metric_low.startswith("avoided"):
        return "#22C55E" if delta_txt.startswith("-") else "#F59E0B"
    return None


@st.fragment
def _render_comparison_ledger(
    snap_a: Optional[CombinedScenarioSnapshot],
    snap_b: Optional[CombinedScenarioSnapshot],
) -> None:
    """Zone 4: Plain-language upgrade payback summary & collapsible comparison tables."""
    if snap_a is None and snap_b is None:
        return

    tables = build_segmented_comparison_tables(snap_a, snap_b)
    if not tables:
        return

    ref = snap_a if snap_a is not None else snap_b
    assert ref is not None
    curr = str(ref.financial_config.currency_code or "EUR")
    any_fin = "capex_y1_pnl" in tables

    if any_fin:
        bwl_inc = compute_incremental_bwl_evaluation(snap_a, snap_b)
        if bwl_inc is not None:
            inc_curr = bwl_inc["currency_code"]
            high_n = bwl_inc["high_cap_name"]
            low_n = bwl_inc["low_cap_name"]
            d_cap = float(bwl_inc["delta_capex_eur"])
            d_sav = float(bwl_inc["delta_annual_opex_savings_eur"])
            d_tco = float(bwl_inc["delta_tco_15y_savings_eur"])
            never_pb = bool(bwl_inc.get("never_pays_back", d_cap > 0.5 and d_sav <= 1.0))
            if bwl_inc["incremental_payback_years"] is not None:
                inc_pb = f"{bwl_inc['incremental_payback_years']:.1f} yrs"
                pb_sub = "Time for extra savings to repay extra cost"
            elif never_pb:
                inc_pb = "Never"
                pb_sub = f"{low_n[:24]} is cheaper upfront & saves more"
            else:
                inc_pb = "> 15 yrs (N/A)"
                pb_sub = "Extra upfront cost / extra yearly savings"
            banner_fn = st.success if bwl_inc["is_upgrade_value_accretive"] else st.info
            with st.container(border=True):
                st.markdown(f"##### :material/balance: Head-to-Head Comparison: {high_n} vs. {low_n}")
                st.caption("Direct comparison between the two saved options (this compares them against each other, not against doing nothing).")
                banner_fn(f"**{bwl_inc['verdict_title']}** — {bwl_inc['verdict_text']}", icon=":material/insights:")
                m1, m2, m3, m4 = st.columns(4)
                with m1:
                    render_kpi_card(
                        title="Upfront Cost Difference",
                        value=format_currency_value(d_cap, inc_curr, signed=True),
                        subtext=(
                            f"{high_n[:22]} costs more than {low_n[:22]}"
                            if d_cap > 0.5
                            else "Both options have the same upfront cost"
                        ),
                        status="default",
                    )
                with m2:
                    render_kpi_card(
                        title="Yearly Savings Difference",
                        value=f"{format_currency_value(d_sav, inc_curr, signed=True)}/yr",
                        subtext=(
                            f"{high_n[:22]} saves more/yr than {low_n[:22]}"
                            if d_sav >= 0.0
                            else f"{high_n[:20]} saves {format_currency_value(abs(d_sav), inc_curr)}/yr less than {low_n[:20]}"
                        ),
                        status="ok" if d_sav > 0 else "alert",
                    )
                with m3:
                    render_kpi_card(
                        title="Payback on Extra Cost",
                        value=inc_pb,
                        subtext=pb_sub,
                        status="ok" if (bwl_inc["incremental_payback_years"] is not None and bwl_inc["incremental_payback_years"] <= 10.0) else "default",
                    )
                with m4:
                    winner_n = str(bwl_inc.get("winner_name") or (high_n if d_tco > 0 else low_n))
                    render_kpi_card(
                        title="15-Year Profit Difference",
                        value=format_currency_value(d_tco, inc_curr, signed=True),
                        subtext=f"{winner_n[:22]} ahead by {format_currency_value(abs(d_tco), inc_curr)} (NPV: {format_currency_value(bwl_inc['delta_npv_15y_eur'], inc_curr, signed=True)})",
                        status="ok" if d_tco > 0 else "alert",
                    )

    col_a_hdr = f"Scenario A ({snap_a.name[:22]})" if snap_a else "Scenario A (Empty)"
    col_b_hdr = f"Scenario B ({snap_b.name[:22]})" if snap_b else "Scenario B (Empty)"
    table_keys = ["sizing_rules", "grid_balance", "utilization_dead_cap"]
    if any_fin:
        table_keys.extend(["capex_y1_pnl", "bwl_15y_metrics"])
    keys_to_show = [key for key in table_keys if key in tables]

    with st.container(border=True):
        st.markdown("##### :material/table_chart: Detailed Comparison Tables (Expand as Needed)")

        for t_key in keys_to_show:
            spec = tables[t_key]
            rows_html = []
            for rec in spec["df"].to_dict(orient="records"):
                delta_txt = str(rec["Delta (B vs. A)"])
                rows_html.append({
                    "cells": [
                        str(rec["Metric / KPI"]),
                        str(rec["Current Situation"]),
                        str(rec["Scenario A"]),
                        str(rec["Scenario B"]),
                        delta_txt,
                    ],
                    "highlight": _highlight_delta_color(str(rec["Metric / KPI"]).lower(), delta_txt),
                })
            with st.expander(spec["title"], expanded=False):
                st.markdown(
                    _render_sub_ledger_html(
                        header_title=spec["header_title"],
                        columns=["Metric / KPI", "Current Situation", col_a_hdr, col_b_hdr, "Delta (B vs. A)"],
                        rows=rows_html,
                        footer_cells=spec["footer_cells"],
                        accent_color=spec["accent_color"],
                        is_enabled=True,
                        currency_code=curr,
                        left_aligned_cols=1,
                    ),
                    unsafe_allow_html=True,
                )

        with st.expander(":material/dataset: Copy / Inspect Complete Tabular Matrix", expanded=False):
            st.dataframe(build_ab_comparison_matrix_df(snap_a, snap_b), use_container_width=True, hide_index=True)


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
                "Save snapshots of your configured systems to compare Scenario A vs. Scenario B "
                "side by side across headline cards, familiar charts, and expandable summary tables."
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
                        st.markdown(f"###### :material/bookmark_added: Slot {slot_id}: {snap.name}")
                        st.caption(f"Captured {snap.created_at} | `{_hardware_badge(snap)}`")
                        if getattr(snap.system_config, "enable_financials", False):
                            s_curr = str(snap.financial_config.currency_code or "EUR")
                            fk_s = snap.financial_kpis
                            pb_s = f"{fk_s.payback_years:.1f} yrs" if fk_s.payback_years is not None else "N/A"
                            st.markdown(
                                f"**Net CAPEX:** {format_currency_value(fk_s.total_capex_eur, s_curr)} | "
                                f"**Y1 Savings:** {format_currency_value(fk_s.annual_savings_eur, s_curr, signed=True)}/yr | "
                                f"**Payback:** {pb_s} | "
                                f"**15Y TCO:** {format_currency_value(fk_s.tco_15y_combined_eur, s_curr)}"
                            )
                        else:
                            kp_s = snap.kpis
                            onsite_s = max(0.0, 100.0 - float(snap.utilization_diagnostics.grid_direct_pct))
                            st.markdown(
                                f"**Grid Peak:** {kp_s.new_grid_peak_kw:,.1f} kW | "
                                f"**Overload:** {kp_s.remaining_overload_hours:,.1f} hrs | "
                                f"**On-Site Share:** {onsite_s:.1f}% | "
                                f"**Financials:** Off"
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

    # Zone 3: Isolated Comparison Chart Gallery (with 15-min Load Profile Comparison)
    _render_ab_chart_gallery_fragment(snap_a, snap_b, load_series=load_series)

    # Zone 4: BWL Incremental Investment & Segmented 5-Domain Comparison Tables
    _render_comparison_ledger(snap_a, snap_b)
