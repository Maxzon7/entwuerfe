"""
Subtab 6.2 dispatch, Subtab 6.3 (Executive 15-Year Overview & Charts),
and top-level `render_subtab6_financials` fragment orchestrator.
"""

import pandas as pd
import streamlit as st

from .state_and_helpers import (
    CombinedSystemConfig,
    CombinedFinancialConfig,
    SystemUtilizationDiagnostics,
    render_kpi_card,
    evaluate_combined_financials,
    compute_system_utilization_diagnostics,
    create_financial_cost_comparison_figure,
    create_financial_tco_trajectory_figure,
    create_financial_waterfall_bridge_figure,
    create_financial_monthly_cashflow_figure,
    _activate_module_callback,
)
from .subtab5_mix_and_rules import render_supply_mix_and_utilization_overview
from .subtab6_isolated_pillars import (
    _get_curr_code,
    _curr_prefix,
    _fmt_curr,
    _render_master_cost_equation_bar,
    _render_sub_ledger_html,
)
from .subtab6_financials_bill_and_hardware import (
    _apply_pending_fin_widget_sync,
    _render_subtab6_1_grid_tariffs,
)
from .subtab6_hardware_costs import _render_subtab6_2_hardware_costs


@st.fragment
def _render_financial_chart_gallery_fragment(sim_res) -> None:
    """Isolates financial chart perspective switching inside a lightweight fragment."""
    with st.container(border=True):
        st.markdown("##### :material/analytics: Financial Charts")
        gallery_choice = st.radio(
            "Visualization Perspective",
            options=[
                "15-Year Cumulative TCO & Break-Even Trajectory",
                "Annual Cost Bridge (Waterfall)",
                "4-Pillar Annual Cost Comparison",
                "12-Month Seasonal Cashflow",
            ],
            index=0,
            horizontal=True,
            key="comb_fin_chart_gallery_sel",
            label_visibility="collapsed",
        )

        if gallery_choice == "15-Year Cumulative TCO & Break-Even Trajectory":
            fig_fin = create_financial_tco_trajectory_figure(sim_res)
        elif gallery_choice == "Annual Cost Bridge (Waterfall)":
            fig_fin = create_financial_waterfall_bridge_figure(sim_res)
        elif gallery_choice == "4-Pillar Annual Cost Comparison":
            fig_fin = create_financial_cost_comparison_figure(sim_res)
        else:
            fig_fin = create_financial_monthly_cashflow_figure(sim_res)

        st.plotly_chart(
            fig_fin,
            use_container_width=True,
            config={
                "scrollZoom": False,
                "displayModeBar": "hover",
                "responsive": True,
            },
            key=f"comb_fin_gallery_{gallery_choice.replace(' ', '_').replace('(', '').replace(')', '').replace('-', '_').lower()}",
        )


@st.fragment
def _render_cashflow_table_expander_fragment(sim_res) -> None:
    """Isolates the 15-year cashflow table behind a lazy expander + toggle to avoid unnecessary renders."""
    with st.expander(":material/table_chart: 15-Year Cashflow Table", expanded=False):
        show_cf_tbl = st.checkbox(
            "Show 15-Year Table",
            value=True,
            key="comb_fin_show_15y_ledger_chk",
        )
        if show_cf_tbl and sim_res.cashflow_15y_df is not None and not sim_res.cashflow_15y_df.empty:
            st.dataframe(
                sim_res.cashflow_15y_df,
                use_container_width=True,
                hide_index=True,
            )


def _render_subtab6_3_executive_overview(sim_res, cur_sys: CombinedSystemConfig, cur_fin: CombinedFinancialConfig) -> None:
    """Sub-Tab 6.3: Executive Summary, 15-Year Dynamics, Component Cost Matrix & Financial Charts."""
    # Long-Term Escalation, Degradation & Discount Rate Form
    with st.form("comb_fin_longterm_form"):
        st.markdown("##### :material/trending_up: Price Increases & Lifespan")
        lt1, lt2, lt3, lt4, lt_btn = st.columns([1.0, 1.0, 1.0, 1.0, 1.1])
        with lt1:
            tariff_esc = st.number_input(
                "Tariff Escalation (% p.a.)",
                min_value=0.0, max_value=15.0, value=float(cur_fin.tariff_escalation_pct_pa), step=0.5,
                key="comb_fin_tariff_esc",
                help="Annual electricity & grid tariff inflation.",
            )
        with lt2:
            om_inf = st.number_input(
                "O&M Inflation (% p.a.)",
                min_value=0.0, max_value=15.0, value=float(cur_fin.om_inflation_pct_pa), step=0.5,
                key="comb_fin_om_inf",
                help="Annual inflation for hardware maintenance and fuel.",
            )
        with lt3:
            sys_deg = st.number_input(
                "System Degradation (% p.a.)",
                min_value=0.0, max_value=5.0, value=float(cur_fin.system_degradation_pct_pa), step=0.1, format="%.2f",
                key="comb_fin_sys_deg",
                help="Annual volumetric yield degradation for PV energy & export (peak shaving stays stable while capacity holds).",
            )
        with lt4:
            disc_rate = st.number_input(
                "Discount Rate for NPV (%)",
                min_value=0.0, max_value=20.0, value=float(cur_fin.discount_rate_pct), step=0.5,
                key="comb_fin_disc_rate",
            )
        with lt_btn:
            st.write("")
            st.write("")
            lt_submitted = st.form_submit_button(
                "Update Projection",
                icon=":material/refresh:",
                type="primary",
                use_container_width=True,
            )

    if lt_submitted:
        cur_fin.tariff_escalation_pct_pa = float(tariff_esc)
        cur_fin.om_inflation_pct_pa = float(om_inf)
        cur_fin.system_degradation_pct_pa = float(sys_deg)
        cur_fin.discount_rate_pct = float(disc_rate)
        evaluate_combined_financials(sim_res, cur_fin)
        st.session_state.pop("comb_cached_excel_bytes", None)
        st.rerun(scope="fragment")

    fin_kpis = sim_res.financial_kpis
    curr = _get_curr_code(sim_res)
    c_pref = _curr_prefix(curr)

    # Economic Bottleneck Alert (Automatic Diagnostic)
    if cur_sys.enable_battery and fin_kpis.battery_om_eur > 0:
        bat_om = fin_kpis.battery_om_eur
        gross_sav = fin_kpis.gross_bill_savings_y1_eur
        bat_capex = fin_kpis.battery_capex_eur
        if bat_om > 0.5 * max(1.0, gross_sav) or (gross_sav > 0 and fin_kpis.annual_savings_eur <= 0):
            st.warning(
                f"**:material/lightbulb: Economic Bottleneck Alert:** Annual battery maintenance ({_fmt_curr(bat_om, curr)}/yr from {_fmt_curr(bat_capex, curr)} CAPEX) "
                f"consumes {(bat_om / max(1.0, gross_sav) * 100.0):.1f}% of the gross electricity bill savings ({_fmt_curr(gross_sav, curr)}/yr). "
                f"Tip: Selecting an 80% battery capacity target or pairing a smaller battery with a peaking generator "
                f"substantially reduces CAPEX and O&M costs."
            )

    st.markdown("##### :material/account_balance: Financial Summary")

    # Single Clear 4-Card Headline Overview
    fk1, fk2, fk3, fk4 = st.columns(4)
    pb_str = f"{fin_kpis.payback_years:.1f} yrs" if fin_kpis.payback_years is not None else "N/A"
    disc_pb_str = f"{fin_kpis.discounted_payback_years:.1f} yrs" if fin_kpis.discounted_payback_years is not None else "N/A"
    irr_str = f"{fin_kpis.irr_15y_pct:.1f}%" if fin_kpis.irr_15y_pct is not None else "N/A"
    with fk1:
        capex_subtext = (
            f"Gross: {_fmt_curr(fin_kpis.gross_capex_eur, curr)} | Avoided: -{_fmt_curr(fin_kpis.avoided_grid_upgrade_capex_eur, curr)}"
            if fin_kpis.avoided_grid_upgrade_capex_eur > 0
            else f"Solar: {_fmt_curr(fin_kpis.solar_capex_eur, curr)} | Battery: {_fmt_curr(fin_kpis.battery_capex_eur, curr)} | Gen: {_fmt_curr(fin_kpis.generator_capex_eur, curr)}"
        )
        render_kpi_card(
            title="Total Investment",
            value=_fmt_curr(fin_kpis.total_capex_eur, curr),
            subtext=capex_subtext,
            status="default",
        )
    with fk2:
        render_kpi_card(
            title="Annual Savings (Year 1)",
            value=f"{_fmt_curr(fin_kpis.annual_savings_eur, curr, signed=True)} / yr",
            subtext=f"New annual cost: {_fmt_curr(fin_kpis.total_annual_opex_eur, curr)} vs. {_fmt_curr(fin_kpis.baseline_total_opex_eur, curr)} current",
            status="ok" if fin_kpis.annual_savings_eur > 0 else "alert",
        )
    with fk3:
        render_kpi_card(
            title="Payback Period",
            value=pb_str,
            subtext="Years until investment is paid back",
            status="ok" if fin_kpis.payback_years is not None else "alert",
        )
    with fk4:
        render_kpi_card(
            title="15-Year Net Profit",
            value=_fmt_curr(fin_kpis.tco_15y_savings_eur, curr, signed=True),
            subtext=f"15Y total cost: {_fmt_curr(fin_kpis.tco_15y_combined_eur, curr)} vs. {_fmt_curr(fin_kpis.tco_15y_baseline_eur, curr)} current",
            status="ok" if fin_kpis.tco_15y_savings_eur > 0 else "alert",
        )

    if cur_fin.strict_grid_congestion_mode:
        if fin_kpis.grid_congestion_compliant:
            st.success(
                f":material/verified: **Strict Grid Congestion Lock Active — Compliant:** "
                f"System stays within the {cur_sys.grid_limit_kw:,.0f} kW contracted limit all year without grid upgrades."
            )
        else:
            st.error(
                f":material/gpp_bad: **Strict Grid Congestion Lock Active — Violation:** "
                f"Grid peak reaches {sim_res.kpis.new_grid_peak_kw:,.1f} kW (+{fin_kpis.grid_congestion_breach_kw:,.1f} kW over limit). "
                f"Avoided grid upgrade CAPEX is locked at {_fmt_curr(0, curr)}; adjust Battery, Generator, or Load Mix in Tab 5."
            )

    # Complete Component & Cost Summary Matrix
    with st.container(border=True):
        st.markdown("##### :material/summarize: System Cost Summary")
        comp_rows = [
            {"cells": ["1. Electricity Supply (Retailer)", _fmt_curr(0, curr, html=True), _fmt_curr(fin_kpis.baseline_pillar1_supply_eur, curr, html=True), _fmt_curr(fin_kpis.combined_pillar1_supply_eur, curr, html=True), _fmt_curr(fin_kpis.baseline_pillar1_supply_eur - fin_kpis.combined_pillar1_supply_eur, curr, signed=True, html=True)], "highlight": "#22C55E" if fin_kpis.baseline_pillar1_supply_eur > fin_kpis.combined_pillar1_supply_eur else None},
            {"cells": ["2. Grid Network (DSO &amp; Peaks)", f"-{_fmt_curr(fin_kpis.avoided_grid_upgrade_capex_eur, curr, html=True)}" if fin_kpis.avoided_grid_upgrade_capex_eur > 0 else _fmt_curr(0, curr, html=True), _fmt_curr(fin_kpis.baseline_pillar2_dso_eur, curr, html=True), _fmt_curr(fin_kpis.combined_pillar2_dso_eur, curr, html=True), _fmt_curr(fin_kpis.baseline_pillar2_dso_eur - fin_kpis.combined_pillar2_dso_eur, curr, signed=True, html=True)], "highlight": "#22C55E" if fin_kpis.baseline_pillar2_dso_eur > fin_kpis.combined_pillar2_dso_eur else None},
            {"cells": ["3. Metering &amp; Statutory Taxes", _fmt_curr(0, curr, html=True), _fmt_curr(fin_kpis.baseline_pillar3_metering_eur + fin_kpis.baseline_pillar4_taxes_eur, curr, html=True), _fmt_curr(fin_kpis.combined_pillar3_metering_eur + fin_kpis.combined_pillar4_taxes_eur, curr, html=True), _fmt_curr((fin_kpis.baseline_pillar3_metering_eur + fin_kpis.baseline_pillar4_taxes_eur) - (fin_kpis.combined_pillar3_metering_eur + fin_kpis.combined_pillar4_taxes_eur), curr, signed=True, html=True)], "highlight": "#22C55E" if fin_kpis.baseline_pillar4_taxes_eur > fin_kpis.combined_pillar4_taxes_eur else None},
            {"cells": ["4. Solar PV System (O&amp;M)", _fmt_curr(fin_kpis.solar_capex_eur, curr, html=True), _fmt_curr(0, curr, html=True), _fmt_curr(fin_kpis.solar_om_eur, curr, html=True), f"-{_fmt_curr(fin_kpis.solar_om_eur, curr, html=True)}" if fin_kpis.solar_om_eur > 0 else _fmt_curr(0, curr, html=True)], "highlight": "#EF4444" if fin_kpis.solar_om_eur > 0 else None},
            {"cells": ["5. Battery Storage BESS (O&amp;M)", _fmt_curr(fin_kpis.battery_capex_eur, curr, html=True), _fmt_curr(0, curr, html=True), _fmt_curr(fin_kpis.battery_om_eur, curr, html=True), f"-{_fmt_curr(fin_kpis.battery_om_eur, curr, html=True)}" if fin_kpis.battery_om_eur > 0 else _fmt_curr(0, curr, html=True)], "highlight": "#EF4444" if fin_kpis.battery_om_eur > 0 else None},
            {"cells": ["6. Peaking Generator (Fuel &amp; Service)", _fmt_curr(fin_kpis.generator_capex_eur, curr, html=True), _fmt_curr(0, curr, html=True), _fmt_curr(fin_kpis.generator_total_opex_eur, curr, html=True), f"-{_fmt_curr(fin_kpis.generator_total_opex_eur, curr, html=True)}" if fin_kpis.generator_total_opex_eur > 0 else _fmt_curr(0, curr, html=True)], "highlight": "#EF4444" if fin_kpis.generator_total_opex_eur > 0 else None},
            {"cells": ["7. Solar Export Feed-in Revenue", _fmt_curr(0, curr, html=True), _fmt_curr(0, curr, html=True), f"-{_fmt_curr(fin_kpis.solar_export_revenue_eur, curr, html=True)}" if fin_kpis.solar_export_revenue_eur > 0 else _fmt_curr(0, curr, html=True), f"+{_fmt_curr(fin_kpis.solar_export_revenue_eur, curr, html=True)}" if fin_kpis.solar_export_revenue_eur > 0 else _fmt_curr(0, curr, html=True)], "highlight": "#22C55E" if fin_kpis.solar_export_revenue_eur > 0 else None},
        ]
        st.markdown(
            _render_sub_ledger_html(
                header_title="Costs &amp; Savings by Component",
                columns=["Cost Component", "One-Off CAPEX", "Current (/yr)", "With System (/yr)", "Annual Impact (/yr)"],
                rows=comp_rows,
                footer_cells=[
                    "= TOTAL COMBINED SYSTEM (NET)",
                    _fmt_curr(fin_kpis.total_capex_eur, curr, html=True),
                    f"{_fmt_curr(fin_kpis.baseline_total_opex_eur, curr, html=True)}/yr",
                    f"{_fmt_curr(fin_kpis.total_annual_opex_eur, curr, html=True)}/yr",
                    f"{_fmt_curr(fin_kpis.annual_savings_eur, curr, signed=True, html=True)}/yr",
                ],
                accent_color="#10B981",
                is_enabled=True,
                currency_code=curr,
            ),
            unsafe_allow_html=True,
        )

    # Secondary Technical & Contract Indicators (collapsed by default for clean screen clarity)
    with st.expander(":material/analytics: Additional Financial & Contract Indicators (NPV, IRR, LCOE & Contract Split)", expanded=False):
        cong_val = (
            f"Compliant (0 breach mos, Peak {sim_res.kpis.new_grid_peak_kw:,.1f} <= {cur_sys.grid_limit_kw:,.0f} kW)"
            if fin_kpis.grid_congestion_compliant
            else f"Breach (+{fin_kpis.grid_congestion_breach_kw:,.1f} kW across {fin_kpis.grid_congestion_breach_months} mos)"
        )
        ind_df = pd.DataFrame([
            {"Indicator": "Discounted Payback", "Value": disc_pb_str, "Notes": f"Break-even discounted at {cur_fin.discount_rate_pct:.1f}% p.a."},
            {"Indicator": "15-Year NPV & IRR", "Value": f"{_fmt_curr(fin_kpis.npv_15y_eur, curr, signed=True)} | IRR: {irr_str}", "Notes": f"Discounted net present value at {cur_fin.discount_rate_pct:.1f}%"},
            {"Indicator": "15-Year Benefit-Cost Ratio (BCR)", "Value": f"{fin_kpis.benefit_cost_ratio_15y:.2f}x", "Notes": "Discounted 15-year savings divided by Net CAPEX"},
            {"Indicator": "On-Site Energy Cost vs. Grid", "Value": f"{c_pref}{fin_kpis.system_lcoe_eur_kwh:,.3f} / kWh", "Notes": f"Effective grid rate: {c_pref}{fin_kpis.effective_blended_grid_rate_eur_kwh:,.3f} / kWh"},
            {"Indicator": "Peak Shaving Cost Efficiency", "Value": f"{_fmt_curr(fin_kpis.annualized_cost_per_shaved_kw_eur, curr)} / kW/yr", "Notes": f"Peak demand reduced by {sim_res.kpis.peak_reduction_kw:,.1f} kW"},
            {"Indicator": "DSO Contract Savings (Isolated)", "Value": f"{_fmt_curr(fin_kpis.dso_savings_eur, curr, signed=True)} / yr ({fin_kpis.dso_savings_pct:+.1f}%)", "Notes": f"New DSO grid bill: {_fmt_curr(fin_kpis.combined_pillar2_dso_eur, curr)}/yr"},
            {"Indicator": "Supplier Commodity Savings (Isolated)", "Value": f"{_fmt_curr(fin_kpis.supplier_savings_eur, curr, signed=True)} / yr ({fin_kpis.supplier_savings_pct:+.1f}%)", "Notes": f"New energy bill: {_fmt_curr(fin_kpis.combined_pillar1_supply_eur, curr)}/yr"},
            {"Indicator": "Grid Congestion Compliance", "Value": cong_val, "Notes": "Checks whether all 12 monthly peaks stay within contracted grid limit"},
        ])
        st.dataframe(ind_df, use_container_width=True, hide_index=True)

    # Supply Mix, Asset Utilization & Financial Cost Share Bridge (collapsible fragment)
    _render_subtab6_supply_mix_bridge_fragment(sim_res)

    # Interactive Financial Chart Gallery (isolated fragment)
    _render_financial_chart_gallery_fragment(sim_res)

    # Expandable 15-Year Cashflow Table (isolated fragment)
    _render_cashflow_table_expander_fragment(sim_res)


@st.fragment
def _render_subtab6_supply_mix_bridge_fragment(sim_res) -> None:
    """Collapsible Supply Mix, Asset Utilization & Physical vs. Financial Cost Share comparison table."""
    fk = sim_res.financial_kpis
    if fk is None:
        return
    curr = _get_curr_code(sim_res)

    with st.expander(":material/donut_large: Supply Mix, Asset Utilization & Financial Cost Share", expanded=False):
        render_supply_mix_and_utilization_overview(sim_res, key_prefix="subtab6")

        diag: SystemUtilizationDiagnostics = compute_system_utilization_diagnostics(sim_res)
        grid_opex = max(0.0, float(fk.combined_grid_total_eur))
        solar_opex = max(0.0, float(fk.solar_om_eur))
        bat_opex = max(0.0, float(fk.battery_om_eur))
        gen_opex = max(0.0, float(fk.generator_total_opex_eur))
        gross_opex_sum = max(1.0, grid_opex + solar_opex + bat_opex + gen_opex)

        bridge_df = pd.DataFrame([
            {
                "Source": "Grid Import",
                "Physical Energy (MWh/yr)": round(diag.grid_direct_kwh / 1000.0, 1),
                "Physical Share (%)": round(diag.grid_direct_pct, 1),
                f"Annual Operating Cost ({curr}/yr)": round(grid_opex, 0),
                "Annual Cost Share (%)": round((grid_opex / gross_opex_sum) * 100.0, 1),
                f"CAPEX ({curr})": round(0.0, 0),
            },
            {
                "Source": "Solar Direct",
                "Physical Energy (MWh/yr)": round(diag.solar_direct_kwh / 1000.0, 1),
                "Physical Share (%)": round(diag.solar_direct_pct, 1),
                f"Annual Operating Cost ({curr}/yr)": round(solar_opex - float(fk.solar_export_revenue_eur), 0),
                "Annual Cost Share (%)": round((solar_opex / gross_opex_sum) * 100.0, 1),
                f"CAPEX ({curr})": round(float(fk.solar_capex_eur), 0),
            },
            {
                "Source": "Battery Storage",
                "Physical Energy (MWh/yr)": round(diag.battery_discharge_kwh / 1000.0, 1),
                "Physical Share (%)": round(diag.battery_discharge_pct, 1),
                f"Annual Operating Cost ({curr}/yr)": round(bat_opex, 0),
                "Annual Cost Share (%)": round((bat_opex / gross_opex_sum) * 100.0, 1),
                f"CAPEX ({curr})": round(float(fk.battery_capex_eur), 0),
            },
            {
                "Source": "Generator Backup",
                "Physical Energy (MWh/yr)": round(diag.generator_direct_kwh / 1000.0, 1),
                "Physical Share (%)": round(diag.generator_direct_pct, 1),
                f"Annual Operating Cost ({curr}/yr)": round(gen_opex, 0),
                "Annual Cost Share (%)": round((gen_opex / gross_opex_sum) * 100.0, 1),
                f"CAPEX ({curr})": round(float(fk.generator_capex_eur), 0),
            },
        ])
        st.markdown("**Physical Energy Share (%) vs. Annual Operating Cost Share (%)**")
        st.caption(
            "Solar operating cost shows Solar O&M minus Export Feed-in Revenue; "
            "Cost Share (%) reflects each source's share of gross annual operating outflows."
        )
        st.dataframe(bridge_df, use_container_width=True, hide_index=True)


@st.fragment
def render_subtab6_financials(sim_res) -> None:
    """
    Renders Subtab 6: Financials (Lazy-loaded, @st.fragment isolated):
      - Live Master Cost & Savings Equation Bar
      - 3 Structured Inner Sub-Tabs modeled after Currentsituation_sandbox:
          * 6.1: Electricity Bill & Grid Tariffs (3-Zone: Inputs | Bill Sub-Ledger | Monthly Progression)
          * 6.2: System Hardware & Operating Costs (Solar, Battery, Generator & Avoided Grid Credit)
          * 6.3: Executive Summary & 15-Year Projection (8 KPIs, Component Matrix, Charts, 15Y Ledger)
    """
    cur_sys: CombinedSystemConfig = st.session_state["comb_system_cfg"]
    cur_fin: CombinedFinancialConfig = st.session_state["comb_fin_cfg"]
    # Upgrade in-memory CombinedFinancialConfig after hot reloads so new fields exist cleanly.
    for _k, _v in CombinedFinancialConfig().__dict__.items():
        if not hasattr(cur_fin, _k):
            setattr(cur_fin, _k, _v)
    is_fin_active = bool(cur_sys.enable_financials)

    if not is_fin_active:
        with st.container(border=True):
            f_col1, f_col2 = st.columns([2.5, 1.2])
            with f_col1:
                st.markdown(
                    "**Financials is currently paused for maximum simulation speed.** "
                    "Click **Activate Financials** to run the 4-Pillar Tariff billing, component investment breakdown, "
                    "monthly progression charts, and 15-year cashflow analysis."
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

    _needs_fin_eval = (
        sim_res.financial_kpis is None
        or not hasattr(sim_res.financial_kpis, "dso_savings_eur")
        or not hasattr(sim_res.financial_kpis, "baseline_dso_vol_shoulder_eur")
        or not hasattr(sim_res.financial_kpis, "solar_pricing_mode")
        or getattr(sim_res.financial_kpis, "currency_code", None) != getattr(cur_fin, "currency_code", None)
        or getattr(sim_res, "dso_monthly_df", None) is None
        or sim_res.dso_monthly_df.empty
    )
    if _needs_fin_eval:
        evaluate_combined_financials(sim_res, cur_fin)

    # Top: Live Master Cost & Savings Equation Bar
    st.markdown(_render_master_cost_equation_bar(sim_res), unsafe_allow_html=True)

    # 3 Structured Financial Inner Sub-Tabs
    fin_tabs = st.tabs([
        ":material/receipt_long: 1. Electricity Bill",
        ":material/precision_manufacturing: 2. Hardware & Running Costs",
        ":material/analytics: 3. 15-Year Overview",
    ])

    with fin_tabs[0]:
        _render_subtab6_1_grid_tariffs(sim_res, cur_sys, cur_fin)

    with fin_tabs[1]:
        _render_subtab6_2_hardware_costs(sim_res, cur_sys, cur_fin)

    with fin_tabs[2]:
        _render_subtab6_3_executive_overview(sim_res, cur_sys, cur_fin)
