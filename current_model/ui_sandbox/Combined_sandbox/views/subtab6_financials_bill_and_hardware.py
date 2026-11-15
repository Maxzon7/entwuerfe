"""
Subtab 6.1 (Electricity Bill & Grid Tariffs) view plus shared financial sub-ledger HTML helpers
and isolated DSO/Supplier/Tax deep-dive fragment.
"""

from typing import List
import pandas as pd
import streamlit as st

from .state_and_helpers import (
    render_kpi_card,
    CombinedSystemConfig,
    CombinedFinancialConfig,
    evaluate_combined_financials,
    get_dso_preset_options,
    get_supplier_preset_options,
    get_metering_preset_options,
    apply_utility_tariff_presets,
    create_monthly_grid_bill_progression_figure,
    create_dso_isolated_breakdown_figure,
    create_supplier_isolated_breakdown_figure,
    create_tax_isolated_breakdown_figure,
)

# ======================================================================================
# LEVEL 2 — SUBTAB 6: Financials (3-Zone Sub-Ledger Workbench, @st.fragment Isolated)
# ======================================================================================

def _render_master_cost_equation_bar(sim_res) -> str:
    """Renders the top Live Master Cost & Savings Equation Bar inspired by Currentsituation_sandbox."""
    fk = sim_res.financial_kpis
    if fk is None:
        return ""

    sav_color = "#22C55E" if fk.annual_savings_eur >= 0 else "#EF4444"
    sav_bg = "#06281e" if fk.annual_savings_eur >= 0 else "#2a0e12"
    pb_str = f"{fk.payback_years:.1f} yrs" if fk.payback_years is not None else "N/A"
    npv_color = "#22C55E" if fk.npv_15y_eur >= 0 else "#F87171"

    return (
        f'<div style="background-color:#0b1329; border:1.5px solid #334155; border-radius:10px; padding:12px 16px; margin-bottom:14px;">\n'
        f'<div style="font-size:0.74rem; font-weight:700; color:#94a3b8; text-transform:uppercase; letter-spacing:0.06em; margin-bottom:8px;">'
        f'Annual Cost &amp; Savings'
        f'</div>\n'
        f'<div style="display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:8px;">\n'
        f'<div style="background-color:#1e293b; border-left:4px solid #F87171; border-radius:6px; padding:7px 11px; flex:1; min-width:140px;">'
        f'<div style="font-size:0.72rem; color:#94a3b8; font-weight:600;">Current Situation Bill</div>'
        f'<div style="font-size:1.00rem; color:#f8fafc; font-weight:700;">&euro;{fk.baseline_total_opex_eur:,.0f} / yr</div>'
        f'</div>\n'
        f'<div style="color:#64748b; font-weight:800; font-size:1.05rem;">&rarr;</div>\n'
        f'<div style="background-color:#1e293b; border-left:4px solid #38BDF8; border-radius:6px; padding:7px 11px; flex:1; min-width:140px;">'
        f'<div style="font-size:0.72rem; color:#94a3b8; font-weight:600;">New Grid Bill</div>'
        f'<div style="font-size:1.00rem; color:#f8fafc; font-weight:700;">&euro;{fk.combined_grid_total_eur:,.0f} / yr</div>'
        f'</div>\n'
        f'<div style="color:#64748b; font-weight:800; font-size:1.05rem;">+</div>\n'
        f'<div style="background-color:#1e293b; border-left:4px solid #F59E0B; border-radius:6px; padding:7px 11px; flex:1; min-width:145px;">'
        f'<div style="font-size:0.72rem; color:#94a3b8; font-weight:600;">Hardware O&amp;M &amp; Fuel</div>'
        f'<div style="font-size:1.00rem; color:#f8fafc; font-weight:700;">&euro;{fk.system_om_and_fuel_y1_eur:,.0f} / yr</div>'
        f'</div>\n'
        f'<div style="color:#64748b; font-weight:800; font-size:1.05rem;">&minus;</div>\n'
        f'<div style="background-color:#1e293b; border-left:4px solid #10B981; border-radius:6px; padding:7px 11px; flex:1; min-width:135px;">'
        f'<div style="font-size:0.72rem; color:#94a3b8; font-weight:600;">Solar Export Income</div>'
        f'<div style="font-size:1.00rem; color:#f8fafc; font-weight:700;">&euro;{fk.solar_export_revenue_eur:,.0f} / yr</div>'
        f'</div>\n'
        f'<div style="color:#38BDF8; font-weight:800; font-size:1.10rem;">=</div>\n'
        f'<div style="background-color:#0f172a; border:1.5px solid #38BDF8; border-radius:6px; padding:7px 12px; flex:1.1; min-width:155px;">'
        f'<div style="font-size:0.72rem; color:#38BDF8; font-weight:700; text-transform:uppercase;">Combined Annual Cost</div>'
        f'<div style="font-size:1.02rem; color:#ffffff; font-weight:800;">&euro;{fk.total_annual_opex_eur:,.0f} / yr</div>'
        f'</div>\n'
        f'<div style="color:{sav_color}; font-weight:800; font-size:1.10rem;">&rarr;</div>\n'
        f'<div style="background-color:{sav_bg}; border:2px solid {sav_color}; border-radius:6px; padding:7px 12px; flex:1.2; min-width:170px;">'
        f'<div style="font-size:0.72rem; color:{sav_color}; font-weight:800; text-transform:uppercase;">Net Annual Savings</div>'
        f'<div style="font-size:1.06rem; color:#ffffff; font-weight:800;">&euro;{fk.annual_savings_eur:+,.0f} / yr</div>'
        f'</div>\n'
        f'</div>\n'
        + (
            (
                f'<div style="margin-top:8px; padding:6px 10px; border-radius:6px; font-size:0.78rem; font-weight:700; '
                + (
                    'background-color:#06281e; border:1px solid #22C55E; color:#86EFAC;">'
                    'GRID CONGESTION LOCK ACTIVE: COMPLIANT (&le; Contracted Grid Limit, no grid expansion permitted)'
                    if fk.grid_congestion_compliant
                    else f'background-color:#2a0e12; border:1px solid #EF4444; color:#FCA5A5;">'
                         f'GRID CONGESTION LOCK VIOLATION: Exceeds contracted limit by +{fk.grid_congestion_breach_kw:,.1f} kW '
                         f'across {fk.grid_congestion_breach_months} month(s) &mdash; grid upgrade not allowed'
                )
                + '</div>\n'
            )
            if bool(getattr(getattr(sim_res, "financial_config", None), "strict_grid_congestion_mode", False))
            else ""
        )
        + f'<div style="display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:10px; margin-top:9px; padding-top:8px; border-top:1px solid #1e293b; font-size:0.80rem; color:#cbd5e1;">\n'
        f'<div><b>Net Investment (CAPEX):</b> Solar &euro;{fk.solar_capex_eur:,.0f} + Battery &euro;{fk.battery_capex_eur:,.0f} + Generator &euro;{fk.generator_capex_eur:,.0f} &minus; Avoided Grid Upgrade &euro;{fk.avoided_grid_upgrade_capex_eur:,.0f} = <b style="color:#ffffff;">&euro;{fk.total_capex_eur:,.0f}</b></div>\n'
        f'<div><b>Simple Payback:</b> <span style="color:#f8fafc; font-weight:700;">{pb_str}</span> &nbsp;|&nbsp; <b>15-Year NPV:</b> <span style="color:{npv_color}; font-weight:700;">&euro;{fk.npv_15y_eur:+,.0f}</span></div>\n'
        f'</div>\n'
        f'</div>'
    )


def _render_sub_ledger_html(
    header_title: str,
    columns: List[str],
    rows: List[dict],
    footer_cells: List[str],
    accent_color: str = "#38BDF8",
    is_enabled: bool = True,
) -> str:
    """
    Renders a clean dark-themed HTML Sub-Ledger table showing how costs and savings add up.
    Each entry in `rows` can be either:
      - {"group": "Group Title"} for a full-width category header row, or
      - {"cells": [...], "highlight": Optional[str]} for a standard data row.
    """
    wrapper_style = (
        "border-radius:8px; border:1px solid #334155; overflow:hidden; margin-bottom:10px;"
        if is_enabled
        else "border-radius:8px; border:1px dashed #475569; overflow:hidden; margin-bottom:10px; opacity:0.48; filter:grayscale(100%);"
    )
    status_badge = "" if is_enabled else " &mdash; [INACTIVE: &euro;0]"

    hdr_cells_html = "".join(
        f'<th style="padding:7px 9px; text-align:{"left" if i < 2 else "right"}; white-space:nowrap;">{col}</th>'
        for i, col in enumerate(columns)
    )

    body_rows_html: List[str] = []
    data_idx = 0
    for row in rows:
        if "group" in row:
            body_rows_html.append(
                f'<tr style="background-color:#0b1329; border-bottom:1px solid #334155;">'
                f'<td colspan="{len(columns)}" style="padding:6px 9px; color:{accent_color}; font-size:0.75rem; font-weight:700; text-transform:uppercase; letter-spacing:0.04em;">{row["group"]}</td>'
                f'</tr>'
            )
            continue

        bg = "#1e293b" if data_idx % 2 == 0 else "#0f172a"
        data_idx += 1
        cells = row.get("cells", [])
        hl = row.get("highlight")
        row_td: List[str] = []
        for i, cell in enumerate(cells):
            if i == 0:
                style = "padding:6px 9px; color:#f1f5f9; font-size:0.82rem; font-weight:500;"
            elif i == 1:
                style = "padding:6px 9px; color:#cbd5e1; font-size:0.78rem; font-family:monospace;"
            elif hl and i == len(cells) - 1:
                style = f"padding:6px 9px; text-align:right; color:{hl}; font-size:0.83rem; font-weight:700; white-space:nowrap;"
            elif i == len(cells) - 1:
                style = "padding:6px 9px; text-align:right; color:#f8fafc; font-size:0.83rem; font-weight:600; white-space:nowrap;"
            else:
                style = "padding:6px 9px; text-align:right; color:#e2e8f0; font-size:0.82rem; white-space:nowrap;"
            row_td.append(f'<td style="{style}">{cell}</td>')
        body_rows_html.append(f'<tr style="background-color:{bg}; border-bottom:1px solid #334155;">{"".join(row_td)}</tr>')

    ftr_cells_html: List[str] = []
    for i, cell in enumerate(footer_cells):
        align = "left" if i == 0 else "right"
        colspan_attr = f' colspan="{len(columns) - len(footer_cells) + 1}"' if (i == 0 and len(footer_cells) < len(columns)) else ""
        color = "#ffffff" if i == len(footer_cells) - 1 else accent_color
        ftr_cells_html.append(
            f'<td{colspan_attr} style="padding:8px 9px; text-align:{align}; color:{color}; font-size:0.86rem; white-space:nowrap;">{cell}</td>'
        )

    return (
        f'<div style="{wrapper_style}">\n'
        f'<div style="background-color:#0f172a; padding:8px 12px; border-bottom:2px solid {accent_color}; font-weight:700; color:#f8fafc; font-size:0.88rem;">'
        f'{header_title}{status_badge}'
        f'</div>\n'
        f'<table style="width:100%; border-collapse:collapse; font-family:-apple-system, BlinkMacSystemFont, sans-serif;">\n'
        f'<thead><tr style="background-color:#090d16; border-bottom:1px solid #475569; color:#94a3b8; font-size:0.72rem; text-transform:uppercase; letter-spacing:0.04em;">{hdr_cells_html}</tr></thead>\n'
        f'<tbody>{"".join(body_rows_html)}</tbody>\n'
        f'<tfoot><tr style="background-color:#0b1329; border-top:2px solid {accent_color}; font-weight:700;">{"".join(ftr_cells_html)}</tr></tfoot>\n'
        f'</table>\n'
        f'</div>'
    )


@st.fragment
def _render_monthly_grid_bill_progression_fragment(sim_res) -> None:
    """Isolates 12-Month Electricity & Grid Bill progression chart & ledger inside a fragment."""
    with st.container(border=True):
        st.markdown("##### :material/calendar_month: 3. Monthly Costs")
        view_mode = st.radio(
            "Monthly Progression Perspective",
            options=[
                "Combined System Bill",
                "Current Situation Bill",
                "Monthly Bill Comparison",
            ],
            index=0,
            horizontal=True,
            key="comb_fin_monthly_grid_view_mode",
            label_visibility="collapsed",
        )

        mc_col1, mc_col2 = st.columns([0.52, 0.48], gap="medium")
        with mc_col1:
            fig_monthly = create_monthly_grid_bill_progression_figure(sim_res, view_mode=view_mode)
            st.plotly_chart(
                fig_monthly,
                use_container_width=True,
                config={"scrollZoom": False, "displayModeBar": "hover", "responsive": True},
                key=f"comb_fin_monthly_grid_chart_{view_mode.lower().replace(' ', '_')}",
            )

        with mc_col2:
            m_df = sim_res.monthly_cost_df
            if m_df is not None and not m_df.empty:
                stmt_rows = []
                for _, r in m_df.iterrows():
                    comb_grid = (
                        float(r["Combined Grid Energy & Taxes (€)"])
                        + float(r["Combined Network & Standing (€)"])
                        + float(r["Combined Overload Penalty (€)"])
                    )
                    base_bill = float(r["Current situation Total (€)"])
                    dso_val = float(r["Combined DSO Total (€)"]) if "Combined DSO Total (€)" in m_df.columns else float(r["Combined Network & Standing (€)"])
                    supp_tax = float(r["Combined Supply & Tax (€)"]) if "Combined Supply & Tax (€)" in m_df.columns else float(r["Combined Grid Energy & Taxes (€)"])
                    stmt_rows.append({
                        "Month": str(r["Month"]),
                        "Peak (kW)": round(float(r.get("Combined Grid Peak (kW)", 0.0)), 1),
                        "Grid Import (kWh)": round(float(r.get("Combined Grid Import (kWh)", 0.0)), 0),
                        "Grid DSO (€)": round(dso_val, 0),
                        "Supply & Tax (€)": round(supp_tax, 0),
                        "Penalty (€)": round(float(r["Combined Overload Penalty (€)"]), 0),
                        "With System Bill (€)": round(comb_grid, 0),
                        "Grid Savings (€)": round(base_bill - comb_grid, 0),
                    })
                st.dataframe(
                    pd.DataFrame(stmt_rows),
                    use_container_width=True,
                    hide_index=True,
                    height=370,
                )
@st.fragment
def _render_isolated_pillar_deep_dive_fragment(sim_res) -> None:
    """Collapsible isolated contract pillar inspector (DSO vs. Supplier vs. Metering & Taxes) with chart & 12-month table."""
    fk = sim_res.financial_kpis
    if fk is None:
        return

    with st.expander(":material/troubleshoot: 4. Isolated Contract Pillar Deep-Dive (Chart & Monthly Table)", expanded=False):
        st.caption(
            "Inspect each electricity bill contract pillar in complete isolation—including monthly verification numbers and "
            "component breakdowns—independent of hardware investment or the other bill pillars."
        )
        pillar_choice = st.radio(
            "Select Contract Pillar",
            options=[
                "Grid Operator Contract Only (DSO)",
                "Energy Supplier Contract Only (Retailer)",
                "Metering & Statutory Taxes Only",
            ],
            horizontal=True,
            key="comb_fin_iso_pillar_radio",
        )

        if pillar_choice == "Grid Operator Contract Only (DSO)":
            d1, d2, d3, d4 = st.columns(4)
            with d1:
                render_kpi_card(
                    title="Current DSO Annual Bill",
                    value=f"€{fk.baseline_pillar2_dso_eur:,.0f} / yr",
                    subtext=f"Connection + Transport: €{fk.baseline_dso_connection_eur + fk.baseline_dso_transport_fixed_eur:,.0f}",
                    status="default",
                )
            with d2:
                render_kpi_card(
                    title="With System DSO Bill",
                    value=f"€{fk.combined_pillar2_dso_eur:,.0f} / yr",
                    subtext=f"Peaks: €{fk.combined_dso_peak_eur:,.0f} | Cap: €{fk.combined_dso_capacity_eur:,.0f}",
                    status="ok" if fk.dso_savings_eur >= 0 else "default",
                )
            with d3:
                render_kpi_card(
                    title="Isolated DSO Savings",
                    value=f"€{fk.dso_savings_eur:+,.0f} / yr",
                    subtext=f"{fk.dso_savings_pct:+.1f}% vs. current DSO contract",
                    status="ok" if fk.dso_savings_eur > 0 else ("alert" if fk.dso_savings_eur < 0 else "default"),
                )
            with d4:
                render_kpi_card(
                    title="Contract Breach Months",
                    value=f"{fk.combined_dso_breach_months} / 12 mos",
                    subtext=f"Current: {fk.baseline_dso_breach_months} mos above limit",
                    status="ok" if fk.combined_dso_breach_months == 0 else "alert",
                )
            st.plotly_chart(
                create_dso_isolated_breakdown_figure(sim_res),
                use_container_width=True,
                config={"scrollZoom": False, "displayModeBar": "hover", "responsive": True},
                key="comb_iso_dso_chart",
            )
            if sim_res.dso_monthly_df is not None and not sim_res.dso_monthly_df.empty:
                st.dataframe(sim_res.dso_monthly_df, use_container_width=True, hide_index=True)

        elif pillar_choice == "Energy Supplier Contract Only (Retailer)":
            s1, s2, s3, s4 = st.columns(4)
            with s1:
                render_kpi_card(
                    title="Current Supplier Bill",
                    value=f"€{fk.baseline_pillar1_supply_eur:,.0f} / yr",
                    subtext=f"Peak HT: €{fk.baseline_supply_peak_ht_eur:,.0f} | NT: €{fk.baseline_supply_offpeak_nt_eur:,.0f}",
                    status="default",
                )
            with s2:
                render_kpi_card(
                    title="With System Supplier Bill",
                    value=f"€{fk.combined_pillar1_supply_eur:,.0f} / yr",
                    subtext=f"Peak HT: €{fk.combined_supply_peak_ht_eur:,.0f} | NT: €{fk.combined_supply_offpeak_nt_eur:,.0f}",
                    status="ok" if fk.supplier_savings_eur >= 0 else "default",
                )
            with s3:
                render_kpi_card(
                    title="Isolated Supplier Savings",
                    value=f"€{fk.supplier_savings_eur:+,.0f} / yr",
                    subtext=f"{fk.supplier_savings_pct:+.1f}% commodity reduction",
                    status="ok" if fk.supplier_savings_eur > 0 else "default",
                )
            with s4:
                render_kpi_card(
                    title="Export & Surcharge Impact",
                    value=f"+€{fk.solar_export_revenue_eur:,.0f} export",
                    subtext=f"Certificates & procurement: €{fk.combined_supply_gvo_eur:,.0f}/yr",
                    status="ok" if fk.solar_export_revenue_eur > 0 else "default",
                )
            st.plotly_chart(
                create_supplier_isolated_breakdown_figure(sim_res),
                use_container_width=True,
                config={"scrollZoom": False, "displayModeBar": "hover", "responsive": True},
                key="comb_iso_supplier_chart",
            )
            if sim_res.supplier_monthly_df is not None and not sim_res.supplier_monthly_df.empty:
                st.dataframe(sim_res.supplier_monthly_df, use_container_width=True, hide_index=True)

        else:
            cur_mt = fk.baseline_pillar3_metering_eur + fk.baseline_pillar4_taxes_eur
            sys_mt = fk.combined_pillar3_metering_eur + fk.combined_pillar4_taxes_eur
            t1, t2, t3, t4 = st.columns(4)
            with t1:
                render_kpi_card(
                    title="Current Metering & Taxes",
                    value=f"€{cur_mt:,.0f} / yr",
                    subtext=f"Gross tax: €{fk.baseline_energy_tax_gross_eur:,.0f} | Metering: €{fk.baseline_pillar3_metering_eur:,.0f}",
                    status="default",
                )
            with t2:
                render_kpi_card(
                    title="With System Metering & Taxes",
                    value=f"€{sys_mt:,.0f} / yr",
                    subtext=f"Net tax after credit: €{fk.combined_energy_tax_eur:,.0f}",
                    status="ok" if fk.tax_and_metering_savings_eur >= 0 else "default",
                )
            with t3:
                render_kpi_card(
                    title="Tax & Metering Savings",
                    value=f"€{fk.tax_and_metering_savings_eur:+,.0f} / yr",
                    subtext=f"Annual tax credit: -€{abs(fk.combined_tax_credit_eur):,.0f}/yr",
                    status="ok" if fk.tax_and_metering_savings_eur > 0 else "default",
                )
            with t4:
                render_kpi_card(
                    title="VAT & Gross Total (With System)",
                    value=f"€{fk.combined_grid_gross_eur:,.0f} / yr",
                    subtext=f"Net: €{fk.combined_grid_total_eur:,.0f} + VAT: €{fk.combined_grid_vat_eur:,.0f}",
                    status="default",
                )
            st.plotly_chart(
                create_tax_isolated_breakdown_figure(sim_res),
                use_container_width=True,
                config={"scrollZoom": False, "displayModeBar": "hover", "responsive": True},
                key="comb_iso_tax_chart",
            )
            if sim_res.tax_monthly_df is not None and not sim_res.tax_monthly_df.empty:
                st.dataframe(sim_res.tax_monthly_df, use_container_width=True, hide_index=True)


def _render_subtab6_1_grid_tariffs(sim_res, cur_sys: CombinedSystemConfig, cur_fin: CombinedFinancialConfig) -> None:
    """Sub-Tab 6.1: Electricity Bill & Grid Tariffs (Congestion Lock, Utility Presets, 3-Zone Bill & Isolated Pillars)."""
    fk_live = sim_res.financial_kpis
    with st.container(border=True):
        cg1, cg2 = st.columns([0.55, 0.45])
        with cg1:
            strict_cong = st.toggle(
                "Strict Grid Congestion Lock: No Grid Upgrade or Contract Breach Allowed",
                value=bool(cur_fin.strict_grid_congestion_mode),
                key="comb_strict_congestion_toggle",
                help=(
                    "Enable when the local DSO grid is congested and exceeding contracted capacity or "
                    "buying a grid upgrade is physically or contractually impossible. "
                    "Sets Avoided Grid Upgrade CAPEX credits to €0 and flags any interval breach."
                ),
            )
            if bool(strict_cong) != bool(cur_fin.strict_grid_congestion_mode):
                cur_fin.strict_grid_congestion_mode = bool(strict_cong)
                if cur_fin.strict_grid_congestion_mode:
                    cur_fin.avoided_grid_upgrade_capex_eur = 0.0
                    st.session_state["comb_fin_avoided_upgrade"] = 0.0
                evaluate_combined_financials(sim_res, cur_fin)
                st.session_state.pop("comb_cached_excel_bytes", None)
                st.rerun(scope="fragment")
        with cg2:
            if cur_fin.strict_grid_congestion_mode:
                if fk_live is not None and fk_live.grid_congestion_compliant:
                    st.success(
                        f":material/verified: **CONGESTION COMPLIANT:** Peak demand stays within the {cur_sys.grid_limit_kw:,.0f} kW limit across all 12 months."
                    )
                else:
                    br_kw = fk_live.grid_congestion_breach_kw if fk_live is not None else 0.0
                    br_mo = fk_live.grid_congestion_breach_months if fk_live is not None else 0
                    st.error(
                        f":material/gpp_bad: **GRID CONGESTION VIOLATION:** Peak exceeds limit by **+{br_kw:,.1f} kW** "
                        f"in **{br_mo} month(s)**. Grid upgrades are locked out — increase Battery or Generator support."
                    )
            else:
                st.caption(
                    ":material/info: Grid Congestion Lock is off. Toggle it on if DSO congestion prohibits "
                    "contract breaches and grid expansion investments."
                )

    with st.expander(":material/account_balance: Utility Presets", expanded=False):
        with st.form("comb_utility_preset_form"):
            dso_opts = get_dso_preset_options()
            supp_opts = get_supplier_preset_options()
            meter_opts = get_metering_preset_options()

            dso_list = list(dso_opts.keys())
            supp_list = list(supp_opts.keys())
            meter_list = list(meter_opts.keys())
            for _sk, _opts in [
                ("comb_preset_dso_sel", dso_list),
                ("comb_preset_supp_sel", supp_list),
                ("comb_preset_meter_sel", meter_list),
            ]:
                if _sk in st.session_state and st.session_state[_sk] not in _opts:
                    st.session_state.pop(_sk, None)

            u_c1, u_c2, u_c3, u_btn = st.columns([1.3, 1.3, 1.3, 1.1])
            with u_c1:
                sel_dso = st.selectbox("Grid Operator (DSO)", options=dso_list, index=0, key="comb_preset_dso_sel")
                tier_list = dso_opts.get(sel_dso, ["MV-D (125 to 1,500 kW)"])
                if st.session_state.get("comb_preset_tier_sel") not in tier_list:
                    st.session_state.pop("comb_preset_tier_sel", None)
                sel_tier = st.selectbox("Voltage & Capacity Tier", options=tier_list, index=0, key="comb_preset_tier_sel")
            with u_c2:
                sel_supp = st.selectbox("Energy Supplier", options=supp_list, index=0, key="comb_preset_supp_sel")
                plan_list = supp_opts.get(sel_supp, ["Fixed 1-Year (Dual TOU HT/NT)"])
                if st.session_state.get("comb_preset_plan_sel") not in plan_list:
                    st.session_state.pop("comb_preset_plan_sel", None)
                sel_plan = st.selectbox("Contract Tariff Plan", options=plan_list, index=0, key="comb_preset_plan_sel")
            with u_c3:
                sel_meter = st.selectbox("Metering Company", options=meter_list, index=0, key="comb_preset_meter_sel")
                m_plan_list = meter_opts.get(sel_meter, ["15-Min Interval Telemetry MV (Large Consumer)"])
                if st.session_state.get("comb_preset_mplan_sel") not in m_plan_list:
                    st.session_state.pop("comb_preset_mplan_sel", None)
                sel_m_plan = st.selectbox("Metering Package", options=m_plan_list, index=0, key="comb_preset_mplan_sel")
            with u_btn:
                st.write("")
                st.write("")
                apply_tariffs = st.form_submit_button(
                    "Load Selected Utility Tariffs",
                    icon=":material/download:",
                    type="primary",
                    use_container_width=True,
                )

        if apply_tariffs:
            apply_utility_tariff_presets(
                dso_choice=sel_dso,
                tier_choice=sel_tier,
                supp_choice=sel_supp,
                supp_plan=sel_plan,
                meter_choice=sel_meter,
                meter_tier=sel_m_plan,
                fin_cfg=cur_fin,
            )
            st.session_state["comb_fin_supp_mode"] = (
                "Dual TOU Rate (Peak HT / Off-Peak NT)"
                if cur_fin.supplier_pricing_mode == "dual_tou"
                else "Single Flat Rate"
            )
            st.session_state["comb_fin_supp_kwh"] = cur_fin.supplier_energy_price_eur_kwh
            st.session_state["comb_fin_supp_ht"] = cur_fin.supplier_peak_ht_eur_kwh
            st.session_state["comb_fin_supp_nt"] = cur_fin.supplier_offpeak_nt_eur_kwh
            st.session_state["comb_fin_supp_gvo"] = cur_fin.supplier_gvo_surcharge_eur_kwh
            st.session_state["comb_fin_supp_fix"] = cur_fin.supplier_fixed_fee_eur_month
            st.session_state["comb_fin_dso_conn"] = cur_fin.dso_connection_fee_eur_month
            st.session_state["comb_fin_dso_fix"] = cur_fin.dso_fixed_fee_eur_month
            st.session_state["comb_fin_dso_cap"] = cur_fin.dso_capacity_fee_eur_kw_month
            st.session_state["comb_fin_dso_peak"] = cur_fin.dso_peak_demand_fee_eur_kw_month
            st.session_state["comb_fin_dso_vol"] = cur_fin.dso_transport_eur_kwh
            st.session_state["comb_fin_dso_pen"] = cur_fin.grid_overload_penalty_eur_kw
            st.session_state["comb_fin_dso_breach_adj"] = bool(cur_fin.dso_adjust_capacity_on_breach)
            st.session_state["comb_fin_meter_fix"] = cur_fin.metering_fixed_fee_eur_month
            st.session_state["comb_fin_tax_credit"] = cur_fin.annual_tax_reduction_credit_eur
            evaluate_combined_financials(sim_res, cur_fin)
            st.session_state.pop("comb_cached_excel_bytes", None)
            st.rerun(scope="fragment")

    col_za, col_zb = st.columns([0.48, 0.52], gap="large")

    with col_za:
        st.markdown("##### :material/tune: 1. Tariff Rates")
        with st.form("comb_tariff_inputs_form"):
            with st.expander(":material/cable: A. Grid Operator Contract (DSO)", expanded=True):
                g1, g2 = st.columns(2)
                with g1:
                    dso_conn = st.number_input(
                        "Fixed Connection Fee (€/month)",
                        min_value=0.0, max_value=5000.0, value=float(cur_fin.dso_connection_fee_eur_month), step=10.0,
                        key="comb_fin_dso_conn",
                        help="Fixed monthly grid connection service fee separate from transport base fee.",
                    )
                    dso_fix = st.number_input(
                        "Fixed Transport Fee (€/month)",
                        min_value=0.0, max_value=5000.0, value=float(cur_fin.dso_fixed_fee_eur_month), step=10.0,
                        key="comb_fin_dso_fix",
                    )
                    dso_cap = st.number_input(
                        "Booked Grid Capacity (€/kW/mo)",
                        min_value=0.0, max_value=100.0, value=float(cur_fin.dso_capacity_fee_eur_kw_month), step=0.25, format="%.2f",
                        key="comb_fin_dso_cap",
                        help="Charged monthly on contracted Grid Limit (kW).",
                    )
                    dso_vol = st.number_input(
                        "Grid Transport Rate (€/kWh)",
                        min_value=0.0, max_value=0.50, value=float(cur_fin.dso_transport_eur_kwh), step=0.005, format="%.4f",
                        key="comb_fin_dso_vol",
                    )
                with g2:
                    dso_peak = st.number_input(
                        "Monthly Peak Demand (€/kW/mo)",
                        min_value=0.0, max_value=100.0, value=float(cur_fin.dso_peak_demand_fee_eur_kw_month), step=0.25, format="%.2f",
                        key="comb_fin_dso_peak",
                        help="Charged monthly on highest measured 15-min grid import peak.",
                    )
                    dso_pen = st.number_input(
                        "Overload Penalty (€/kW above limit)",
                        min_value=0.0, max_value=500.0, value=float(cur_fin.grid_overload_penalty_eur_kw), step=1.0,
                        key="comb_fin_dso_pen",
                    )
                    avoided_trafo = st.number_input(
                        "Avoided Transformer Rental (€/mo)",
                        min_value=0.0, max_value=50000.0, value=float(cur_fin.avoided_transformer_rent_eur_month), step=50.0,
                        key="comb_fin_avoided_trafo",
                        help="Monthly transformer rent saved when staying within contracted grid capacity.",
                    )
                    dso_breach_adj = st.checkbox(
                        "Step Up Booked Capacity in Breach Months",
                        value=bool(cur_fin.dso_adjust_capacity_on_breach),
                        key="comb_fin_dso_breach_adj",
                        help="If enabled, any monthly peak exceeding contracted capacity automatically steps up billed capacity.",
                    )

            with st.expander(":material/bolt: B. Energy Supplier & Solar Export", expanded=True):
                _mode_options = ["Single Flat Rate", "Dual TOU Rate (Peak HT / Off-Peak NT)"]
                if st.session_state.get("comb_fin_supp_mode") not in _mode_options:
                    st.session_state["comb_fin_supp_mode"] = (
                        "Dual TOU Rate (Peak HT / Off-Peak NT)"
                        if cur_fin.supplier_pricing_mode == "dual_tou"
                        else "Single Flat Rate"
                    )
                supp_mode = st.radio(
                    "Supplier Pricing Structure",
                    options=_mode_options,
                    horizontal=True,
                    key="comb_fin_supp_mode",
                    help="Dual TOU bills Mon-Fri 07:00-23:00 at Peak HT Rate and nights/weekends at Off-Peak NT Rate.",
                )
                s1, s2, s3 = st.columns(3)
                with s1:
                    supp_kwh = st.number_input(
                        "Single Rate (€/kWh)",
                        min_value=0.0, max_value=2.0, value=float(cur_fin.supplier_energy_price_eur_kwh), step=0.01, format="%.3f",
                        key="comb_fin_supp_kwh",
                    )
                    supp_ht = st.number_input(
                        "Peak HT Rate (€/kWh)",
                        min_value=0.0, max_value=2.0, value=float(cur_fin.supplier_peak_ht_eur_kwh), step=0.01, format="%.3f",
                        key="comb_fin_supp_ht",
                    )
                with s2:
                    supp_nt = st.number_input(
                        "Off-Peak NT Rate (€/kWh)",
                        min_value=0.0, max_value=2.0, value=float(cur_fin.supplier_offpeak_nt_eur_kwh), step=0.01, format="%.3f",
                        key="comb_fin_supp_nt",
                    )
                    supp_gvo = st.number_input(
                        "Green Cert. Surcharge (€/kWh)",
                        min_value=0.0, max_value=0.20, value=float(cur_fin.supplier_gvo_surcharge_eur_kwh), step=0.001, format="%.4f",
                        key="comb_fin_supp_gvo",
                        help="Green certificate and procurement imbalance surcharge per imported kWh.",
                    )
                with s3:
                    supp_fix = st.number_input(
                        "Supplier Base Fee (€/mo)",
                        min_value=0.0, max_value=5000.0, value=float(cur_fin.supplier_fixed_fee_eur_month), step=10.0,
                        key="comb_fin_supp_fix",
                    )
                    solar_fi = st.number_input(
                        "Solar Feed-in (€/kWh)",
                        min_value=0.0, max_value=0.50, value=float(cur_fin.solar_export_feed_in_eur_kwh), step=0.01, format="%.3f",
                        key="comb_fin_solar_fi",
                        help="Revenue received per kWh of solar surplus exported to the grid.",
                    )

            with st.expander(":material/receipt: C. Metering, Taxes & VAT", expanded=False):
                m1, m2 = st.columns(2)
                with m1:
                    meter_fix = st.number_input(
                        "Metering Fee (€/mo)",
                        min_value=0.0, max_value=2000.0, value=float(cur_fin.metering_fixed_fee_eur_month), step=5.0,
                        key="comb_fin_meter_fix",
                    )
                    tax_kwh = st.number_input(
                        "Energy Tax (€/kWh)",
                        min_value=0.0, max_value=1.0, value=float(cur_fin.energy_tax_eur_kwh), step=0.005, format="%.4f",
                        key="comb_fin_tax_kwh",
                    )
                    tax_credit = st.number_input(
                        "Annual Tax Credit (€/yr)",
                        min_value=0.0, max_value=10000.0, value=float(cur_fin.annual_tax_reduction_credit_eur), step=50.0,
                        key="comb_fin_tax_credit",
                        help="Fixed statutory annual energy tax rebate deducted from Energy Tax.",
                    )
                with m2:
                    tax_pct = st.number_input(
                        "Tax Surcharge (%)",
                        min_value=0.0, max_value=50.0, value=float(cur_fin.tax_surcharge_pct), step=1.0,
                        key="comb_fin_tax_pct",
                    )
                    vat_pct = st.number_input(
                        "VAT Rate (%)",
                        min_value=0.0, max_value=30.0, value=float(cur_fin.vat_rate_pct), step=1.0,
                        key="comb_fin_vat_pct",
                        help="Reported alongside net ex-VAT B2B totals for full gross bill verification.",
                    )

            tariffs_submitted = st.form_submit_button(
                "Apply Grid & Electricity Tariffs",
                icon=":material/check_circle:",
                type="primary",
                use_container_width=True,
            )

        if tariffs_submitted:
            cur_fin.dso_connection_fee_eur_month = float(dso_conn)
            cur_fin.dso_fixed_fee_eur_month = float(dso_fix)
            cur_fin.dso_capacity_fee_eur_kw_month = float(dso_cap)
            cur_fin.dso_peak_demand_fee_eur_kw_month = float(dso_peak)
            cur_fin.dso_transport_eur_kwh = float(dso_vol)
            cur_fin.grid_overload_penalty_eur_kw = float(dso_pen)
            cur_fin.avoided_transformer_rent_eur_month = float(avoided_trafo)
            cur_fin.dso_adjust_capacity_on_breach = bool(dso_breach_adj)
            cur_fin.supplier_pricing_mode = "dual_tou" if str(supp_mode).startswith("Dual") else "single"
            cur_fin.supplier_energy_price_eur_kwh = float(supp_kwh)
            cur_fin.supplier_peak_ht_eur_kwh = float(supp_ht)
            cur_fin.supplier_offpeak_nt_eur_kwh = float(supp_nt)
            cur_fin.supplier_gvo_surcharge_eur_kwh = float(supp_gvo)
            cur_fin.supplier_fixed_fee_eur_month = float(supp_fix)
            cur_fin.solar_export_feed_in_eur_kwh = float(solar_fi)
            cur_fin.metering_fixed_fee_eur_month = float(meter_fix)
            cur_fin.energy_tax_eur_kwh = float(tax_kwh)
            cur_fin.annual_tax_reduction_credit_eur = float(tax_credit)
            cur_fin.tax_surcharge_pct = float(tax_pct)
            cur_fin.vat_rate_pct = float(vat_pct)
            evaluate_combined_financials(sim_res, cur_fin)
            st.session_state.pop("comb_cached_excel_bytes", None)
            st.rerun(scope="fragment")

    with col_zb:
        st.markdown("##### :material/receipt_long: 2. Annual Bill Summary")
        fk = sim_res.financial_kpis
        kpis = sim_res.kpis
        m_df = sim_res.monthly_cost_df

        base_kwh = float(kpis.annual_consumption_kwh)
        comb_kwh = float(kpis.grid_import_total_kwh)
        avg_base_pk = float(m_df["Current situation Peak (kW)"].mean()) if (not m_df.empty and "Current situation Peak (kW)" in m_df.columns) else float(kpis.original_peak_kw)
        avg_comb_pk = float(m_df["Combined Grid Peak (kW)"].mean()) if (not m_df.empty and "Combined Grid Peak (kW)" in m_df.columns) else float(kpis.new_grid_peak_kw)

        def _fmt_eur(val: float) -> str:
            return f"-&euro;{abs(val):,.0f}" if val < -0.5 else f"&euro;{val:,.0f}"

        def _row_bill(item: str, calc: str, b_val: float, c_val: float) -> dict:
            sav = b_val - c_val
            hl = "#22C55E" if sav > 0.5 else ("#EF4444" if sav < -0.5 else None)
            return {
                "cells": [
                    item,
                    calc,
                    _fmt_eur(b_val),
                    _fmt_eur(c_val),
                    f"&euro;{sav:+,.0f}",
                ],
                "highlight": hl,
            }

        bill_rows = [{"group": "1. Electricity Supply (Retailer)"}]
        if cur_fin.supplier_pricing_mode == "dual_tou":
            bill_rows.extend([
                _row_bill(
                    "1.1a Peak HT Commodity (Mon-Fri 07-23)",
                    f"&euro;{cur_fin.supplier_peak_ht_eur_kwh:.3f}/kWh",
                    fk.baseline_supply_peak_ht_eur,
                    fk.combined_supply_peak_ht_eur,
                ),
                _row_bill(
                    "1.1b Off-Peak NT Commodity",
                    f"&euro;{cur_fin.supplier_offpeak_nt_eur_kwh:.3f}/kWh",
                    fk.baseline_supply_offpeak_nt_eur,
                    fk.combined_supply_offpeak_nt_eur,
                ),
            ])
        else:
            bill_rows.append(
                _row_bill(
                    "1.1 Purchased Energy (Single Rate)",
                    f"{comb_kwh:,.0f} vs {base_kwh:,.0f} kWh &times; &euro;{cur_fin.supplier_energy_price_eur_kwh:.3f}",
                    fk.baseline_supply_energy_eur,
                    fk.combined_supply_energy_eur,
                )
            )
        if cur_fin.supplier_gvo_surcharge_eur_kwh > 0.0:
            bill_rows.append(
                _row_bill(
                    "1.2 Green Cert. & Surcharge",
                    f"{comb_kwh:,.0f} kWh &times; &euro;{cur_fin.supplier_gvo_surcharge_eur_kwh:.4f}/kWh",
                    fk.baseline_supply_gvo_eur,
                    fk.combined_supply_gvo_eur,
                )
            )
        bill_rows.append(
            _row_bill(
                "1.3 Supplier Base Fee",
                f"12 mos &times; &euro;{cur_fin.supplier_fixed_fee_eur_month:.2f}/mo",
                fk.baseline_supply_fixed_eur,
                fk.combined_supply_fixed_eur,
            )
        )

        bill_rows.append({"group": "2. Grid Network (DSO)"})
        if cur_fin.dso_connection_fee_eur_month > 0.0:
            bill_rows.extend([
                _row_bill(
                    "2.1a Fixed Connection Fee",
                    f"12 mos &times; &euro;{cur_fin.dso_connection_fee_eur_month:.2f}/mo",
                    fk.baseline_dso_connection_eur,
                    fk.combined_dso_connection_eur,
                ),
                _row_bill(
                    "2.1b Fixed Transport Fee",
                    f"12 mos &times; &euro;{cur_fin.dso_fixed_fee_eur_month:.2f}/mo",
                    fk.baseline_dso_transport_fixed_eur,
                    fk.combined_dso_transport_fixed_eur,
                ),
            ])
        else:
            bill_rows.append(
                _row_bill(
                    "2.1 Fixed Grid Base Fee",
                    f"12 mos &times; &euro;{cur_fin.dso_fixed_fee_eur_month:.2f}/mo",
                    fk.baseline_dso_fixed_eur,
                    fk.combined_dso_fixed_eur,
                )
            )

        breach_note = (
            f" [Breach-Adjusted: {fk.combined_dso_breach_months} mos]"
            if (cur_fin.dso_adjust_capacity_on_breach and (fk.combined_dso_breach_months > 0 or fk.baseline_dso_breach_months > 0))
            else ""
        )
        bill_rows.extend([
            _row_bill(
                "2.2 Booked Grid Capacity",
                f"{cur_sys.grid_limit_kw:,.0f} kW &times; 12 &times; &euro;{cur_fin.dso_capacity_fee_eur_kw_month:.2f}{breach_note}",
                fk.baseline_dso_capacity_eur,
                fk.combined_dso_capacity_eur,
            ),
            _row_bill(
                "2.3 Monthly Peak Demand",
                f"Avg {avg_comb_pk:.0f} vs {avg_base_pk:.0f} kW &times; 12 &times; &euro;{cur_fin.dso_peak_demand_fee_eur_kw_month:.2f}",
                fk.baseline_dso_peak_eur,
                fk.combined_dso_peak_eur,
            ),
            _row_bill(
                "2.4 Grid Transport Volume",
                f"{comb_kwh:,.0f} kWh &times; &euro;{cur_fin.dso_transport_eur_kwh:.3f}/kWh",
                fk.baseline_dso_transport_eur,
                fk.combined_dso_transport_eur,
            ),
            _row_bill(
                "2.5 Overload Penalties",
                f"Peak &gt; {cur_sys.grid_limit_kw:,.0f} kW &times; &euro;{cur_fin.grid_overload_penalty_eur_kw:.2f}/kW",
                fk.baseline_penalty_cost_eur,
                fk.combined_grid_penalty_cost_eur,
            ),
        ])

        if cur_fin.avoided_transformer_rent_eur_month > 0.0:
            bill_rows.append(
                _row_bill(
                    "2.6 Avoided Transformer Rent",
                    f"12 mos &times; &euro;{cur_fin.avoided_transformer_rent_eur_month:,.0f}/mo",
                    fk.baseline_dso_transformer_rent_eur,
                    fk.combined_dso_transformer_rent_eur,
                )
            )

        bill_rows.extend([
            {"group": "3. Metering & Statutory Taxes"},
            _row_bill(
                "3.1 Metering & Telemetry",
                f"12 mos &times; &euro;{cur_fin.metering_fixed_fee_eur_month:.2f}/mo",
                fk.baseline_pillar3_metering_eur,
                fk.combined_pillar3_metering_eur,
            ),
            _row_bill(
                "3.2 Government Energy Tax (Gross)",
                f"{comb_kwh:,.0f} kWh &times; &euro;{cur_fin.energy_tax_eur_kwh:.4f}/kWh",
                fk.baseline_energy_tax_gross_eur,
                fk.combined_energy_tax_gross_eur,
            ),
        ])
        if cur_fin.annual_tax_reduction_credit_eur > 0.0 or fk.baseline_tax_credit_eur > 0.5:
            bill_rows.append(
                _row_bill(
                    "3.3 Annual Tax Credit",
                    f"Fixed rebate &euro;{cur_fin.annual_tax_reduction_credit_eur:,.0f}/yr",
                    -fk.baseline_tax_credit_eur,
                    -fk.combined_tax_credit_eur,
                )
            )
        if cur_fin.tax_surcharge_pct > 0.0:
            bill_rows.append(
                _row_bill(
                    "3.4 Tax / Levy Surcharge",
                    f"{cur_fin.tax_surcharge_pct:.1f}% on net charges",
                    fk.baseline_tax_surcharge_eur,
                    fk.combined_tax_surcharge_eur,
                )
            )

        if cur_sys.enable_solar and fk.solar_export_revenue_eur > 0.0:
            bill_rows.append({"group": "4. Solar Export Credit"})
            bill_rows.append(
                {
                    "cells": [
                        "4.1 Grid Feed-in Revenue",
                        f"{kpis.solar_export_kwh:,.0f} kWh &times; &euro;{cur_fin.solar_export_feed_in_eur_kwh:.3f}",
                        "&euro;0",
                        f"-&euro;{fk.solar_export_revenue_eur:,.0f}",
                        f"&euro;{fk.solar_export_revenue_eur:+,.0f}",
                    ],
                    "highlight": "#22C55E",
                }
            )

        comb_bill_net_of_export = fk.combined_grid_total_eur - fk.solar_export_revenue_eur
        bill_savings_total = fk.baseline_total_opex_eur - comb_bill_net_of_export
        sub_html = _render_sub_ledger_html(
            header_title="Annual Electricity Bill Breakdown (Net Excl. VAT)",
            columns=["Bill Line Item", "Calculation (Qty &times; Rate)", "Current (/yr)", "With System (/yr)", "Savings (/yr)"],
            rows=bill_rows,
            footer_cells=[
                "= TOTAL ANNUAL UTILITY BILL (NET OF EXPORT)",
                f"&euro;{fk.baseline_total_opex_eur:,.0f}",
                f"&euro;{comb_bill_net_of_export:,.0f}",
                f"&euro;{bill_savings_total:+,.0f}",
            ],
            accent_color="#38BDF8",
            is_enabled=True,
        )
        st.markdown(sub_html, unsafe_allow_html=True)
        if cur_fin.vat_rate_pct > 0.0:
            st.caption(
                f":material/receipt: **Gross Bill Incl. {cur_fin.vat_rate_pct:.1f}% VAT:** "
                f"Current **€{fk.baseline_total_gross_eur:,.0f}/yr** (VAT €{fk.baseline_vat_eur:,.0f}) -> "
                f"With System **€{fk.combined_grid_gross_eur:,.0f}/yr** (VAT €{fk.combined_grid_vat_eur:,.0f})."
            )

        # System Impact & Compliance Box
        if kpis.grid_limit_met:
            st.success(
                f":material/check_circle: **Grid Compliance & Bill Impact:** Peak reduced from **{kpis.original_peak_kw:,.1f} kW** to **{kpis.new_grid_peak_kw:,.1f} kW** "
                f"(within {cur_sys.grid_limit_kw:,.0f} kW limit).  \n"
                f"**Where Grid Savings Come From:** **€{fk.grid_volume_savings_y1_eur:,.0f}/yr** from reduced energy imports + "
                f"**€{fk.grid_peak_and_penalty_savings_y1_eur:,.0f}/yr** from peak shaving & avoided penalties"
                + (f" + **€{fk.solar_export_revenue_eur:,.0f}/yr** solar export income." if fk.solar_export_revenue_eur > 0 else ".")
            )
        else:
            st.warning(
                f":material/warning: **Remaining Overload Warning:** Peak reduced from **{kpis.original_peak_kw:,.1f} kW** to **{kpis.new_grid_peak_kw:,.1f} kW** "
                f"(**+{kpis.remaining_overload_kw:,.1f} kW** above {cur_sys.grid_limit_kw:,.0f} kW limit).  \n"
                f"**Where Grid Savings Come From:** **€{fk.grid_volume_savings_y1_eur:,.0f}/yr** from reduced energy imports + "
                f"**€{fk.grid_peak_and_penalty_savings_y1_eur:,.0f}/yr** from peak & penalty reductions."
            )

    _render_monthly_grid_bill_progression_fragment(sim_res)
    _render_isolated_pillar_deep_dive_fragment(sim_res)
