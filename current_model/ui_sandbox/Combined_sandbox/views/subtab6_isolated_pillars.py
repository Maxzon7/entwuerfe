"""
Shared financial sub-ledger HTML helpers, currency formatting, and @st.fragment views
for Monthly Grid Bill Progression and Isolated Contract Pillar Deep-Dives.
"""

from typing import List
import pandas as pd
import streamlit as st

from .state_and_helpers import (
    curr_prefix,
    fmt_num,
    fmt_curr,
    render_kpi_card,
    create_monthly_grid_bill_progression_figure,
    create_dso_isolated_breakdown_figure,
    create_supplier_isolated_breakdown_figure,
    create_tax_isolated_breakdown_figure,
)


def _get_curr_code(sim_res) -> str:
    """Returns active ISO currency code ('EUR', 'ARS', 'USD') from simulation result."""
    fk = getattr(sim_res, "financial_kpis", None)
    fc = getattr(sim_res, "financial_config", None)
    return str(
        getattr(fc, "currency_code", None)
        or getattr(fk, "currency_code", None)
        or "EUR"
    )


def _curr_prefix(currency_code: str, html: bool = False) -> str:
    """Delegates to central `engine.formatting.curr_prefix`."""
    return curr_prefix(currency_code, html=html)


def _fmt_curr(
    val: float,
    currency_code: str = "EUR",
    signed: bool = False,
    html: bool = False,
    decimals: int = 0,
) -> str:
    """Delegates to central `engine.formatting.fmt_curr`."""
    return fmt_curr(val, currency_code=currency_code, decimals=decimals, signed=signed, html=html)


def _rename_df_currency_cols(df: pd.DataFrame, currency_code: str) -> pd.DataFrame:
    """Returns a display copy of a financial DataFrame with `(€)` headers replaced by active currency."""
    c_lbl = "€" if currency_code == "EUR" else currency_code
    if c_lbl == "€" or df is None or df.empty:
        return df
    return df.rename(columns={col: str(col).replace("(€)", f"({c_lbl})") for col in df.columns})


def _render_master_cost_equation_bar(sim_res) -> str:
    """Renders the top Live Annual Cost & Savings Equation Bar using active currency."""
    fk = sim_res.financial_kpis
    if fk is None:
        return ""

    curr = _get_curr_code(sim_res)
    sav_color = "#22C55E" if fk.annual_savings_eur >= 0 else "#EF4444"
    sav_bg = "#06281e" if fk.annual_savings_eur >= 0 else "#2a0e12"
    pb_str = f"{fmt_num(fk.payback_years, 1)} yrs" if fk.payback_years is not None else "N/A"
    npv_color = "#22C55E" if fk.npv_15y_eur >= 0 else "#F87171"

    return (
        f'<div style="background-color:#0b1329; border:1.5px solid #334155; border-radius:10px; padding:12px 16px; margin-bottom:14px;">\n'
        f'<div style="font-size:0.74rem; font-weight:700; color:#94a3b8; text-transform:uppercase; letter-spacing:0.06em; margin-bottom:8px;">'
        f'Annual Cost &amp; Savings ({curr})'
        f'</div>\n'
        f'<div style="display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:8px;">\n'
        f'<div style="background-color:#1e293b; border-left:4px solid #F87171; border-radius:6px; padding:7px 11px; flex:1; min-width:140px;">'
        f'<div style="font-size:0.72rem; color:#94a3b8; font-weight:600;">Current Situation Bill</div>'
        f'<div style="font-size:1.00rem; color:#f8fafc; font-weight:700;">{_fmt_curr(fk.baseline_total_opex_eur, curr, html=True)} / yr</div>'
        f'</div>\n'
        f'<div style="color:#64748b; font-weight:800; font-size:1.05rem;">&rarr;</div>\n'
        f'<div style="background-color:#1e293b; border-left:4px solid #38BDF8; border-radius:6px; padding:7px 11px; flex:1; min-width:140px;">'
        f'<div style="font-size:0.72rem; color:#94a3b8; font-weight:600;">New Grid Bill</div>'
        f'<div style="font-size:1.00rem; color:#f8fafc; font-weight:700;">{_fmt_curr(fk.combined_grid_total_eur, curr, html=True)} / yr</div>'
        f'</div>\n'
        f'<div style="color:#64748b; font-weight:800; font-size:1.05rem;">+</div>\n'
        f'<div style="background-color:#1e293b; border-left:4px solid #F59E0B; border-radius:6px; padding:7px 11px; flex:1; min-width:145px;">'
        f'<div style="font-size:0.72rem; color:#94a3b8; font-weight:600;">Hardware OPEX &amp; Fuel</div>'
        f'<div style="font-size:1.00rem; color:#f8fafc; font-weight:700;">{_fmt_curr(fk.system_om_and_fuel_y1_eur, curr, html=True)} / yr</div>'
        f'</div>\n'
        f'<div style="color:#64748b; font-weight:800; font-size:1.05rem;">&minus;</div>\n'
        f'<div style="background-color:#1e293b; border-left:4px solid #10B981; border-radius:6px; padding:7px 11px; flex:1; min-width:135px;">'
        f'<div style="font-size:0.72rem; color:#94a3b8; font-weight:600;">Solar Export Income</div>'
        f'<div style="font-size:1.00rem; color:#f8fafc; font-weight:700;">{_fmt_curr(fk.solar_export_revenue_eur, curr, html=True)} / yr</div>'
        f'</div>\n'
        f'<div style="color:#38BDF8; font-weight:800; font-size:1.10rem;">=</div>\n'
        f'<div style="background-color:#0f172a; border:1.5px solid #38BDF8; border-radius:6px; padding:7px 12px; flex:1.1; min-width:155px;">'
        f'<div style="font-size:0.72rem; color:#38BDF8; font-weight:700; text-transform:uppercase;">Combined Annual OPEX</div>'
        f'<div style="font-size:1.02rem; color:#ffffff; font-weight:800;">{_fmt_curr(fk.total_annual_opex_eur, curr, html=True)} / yr</div>'
        f'</div>\n'
        f'<div style="color:{sav_color}; font-weight:800; font-size:1.10rem;">&rarr;</div>\n'
        f'<div style="background-color:{sav_bg}; border:2px solid {sav_color}; border-radius:6px; padding:7px 12px; flex:1.2; min-width:170px;">'
        f'<div style="font-size:0.72rem; color:{sav_color}; font-weight:800; text-transform:uppercase;">Net Annual Savings</div>'
        f'<div style="font-size:1.06rem; color:#ffffff; font-weight:800;">{_fmt_curr(fk.annual_savings_eur, curr, signed=True, html=True)} / yr</div>'
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
                         f'GRID CONGESTION LOCK VIOLATION: Exceeds contracted limit by +{fmt_num(fk.grid_congestion_breach_kw, 1)} kW '
                         f'across {fk.grid_congestion_breach_months} month(s) &mdash; grid upgrade not allowed'
                )
                + '</div>\n'
            )
            if bool(getattr(getattr(sim_res, "financial_config", None), "strict_grid_congestion_mode", False))
            else ""
        )
        + f'<div style="display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:10px; margin-top:9px; padding-top:8px; border-top:1px solid #1e293b; font-size:0.80rem; color:#cbd5e1;">\n'
        f'<div><b>Net CAPEX:</b> Solar {_fmt_curr(fk.solar_capex_eur, curr, html=True)} + '
        f'Battery {_fmt_curr(fk.battery_capex_eur, curr, html=True)} + '
        f'Generator {_fmt_curr(fk.generator_capex_eur, curr, html=True)} &minus; '
        f'Avoided Grid Upgrade {_fmt_curr(fk.avoided_grid_upgrade_capex_eur, curr, html=True)} = '
        f'<b style="color:#ffffff;">{_fmt_curr(fk.total_capex_eur, curr, html=True)}</b></div>\n'
        f'<div><b>Payback Period:</b> <span style="color:#f8fafc; font-weight:700;">{pb_str}</span> &nbsp;|&nbsp; '
        f'<b>15-Year NPV:</b> <span style="color:{npv_color}; font-weight:700;">{_fmt_curr(fk.npv_15y_eur, curr, signed=True, html=True)}</span></div>\n'
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
    currency_code: str = "EUR",
    left_aligned_cols: int = 2,
) -> str:
    """
    Renders a dark-themed HTML Sub-Ledger table showing how bill items add up.
    """
    wrapper_style = (
        "border-radius:8px; border:1px solid #334155; overflow:hidden; margin-bottom:10px;"
        if is_enabled
        else "border-radius:8px; border:1px dashed #475569; overflow:hidden; margin-bottom:10px; opacity:0.48; filter:grayscale(100%);"
    )
    zero_lbl = _fmt_curr(0.0, currency_code, html=True)
    status_badge = "" if is_enabled else f" &mdash; [INACTIVE: {zero_lbl}]"

    hdr_cells_html = "".join(
        f'<th style="padding:7px 9px; text-align:{"left" if i < left_aligned_cols else "right"}; white-space:nowrap;">{col}</th>'
        for i, col in enumerate(columns)
    )

    body_rows_html: List[str] = []
    data_idx = 0
    for row in rows:
        if "group" in row:
            grp_style = (
                "color:#64748b;" if row.get("bypassed") else f"color:{accent_color};"
            )
            body_rows_html.append(
                f'<tr style="background-color:#0b1329; border-bottom:1px solid #334155;">'
                f'<td colspan="{len(columns)}" style="padding:6px 9px; {grp_style} font-size:0.75rem; font-weight:700; text-transform:uppercase; letter-spacing:0.04em;">{row["group"]}</td>'
                f'</tr>'
            )
            continue

        bg = "#1e293b" if data_idx % 2 == 0 else "#0f172a"
        data_idx += 1
        cells = row.get("cells", [])
        hl = row.get("highlight")
        dimmed = bool(row.get("bypassed"))
        row_td: List[str] = []
        for i, cell in enumerate(cells):
            if dimmed:
                align = "left" if i < left_aligned_cols else "right"
                style = f"padding:6px 9px; text-align:{align}; color:#64748b; font-size:0.80rem; font-style:italic;"
            elif i == 0:
                style = "padding:6px 9px; color:#f1f5f9; font-size:0.82rem; font-weight:500;"
            elif i < left_aligned_cols:
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
    curr = _get_curr_code(sim_res)
    c_lbl = "€" if curr == "EUR" else curr
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
                        f"Grid DSO ({c_lbl})": round(dso_val, 0),
                        f"Supply & Tax ({c_lbl})": round(supp_tax, 0),
                        f"Penalty ({c_lbl})": round(float(r["Combined Overload Penalty (€)"]), 0),
                        f"With System ({c_lbl})": round(comb_grid, 0),
                        f"Savings ({c_lbl})": round(base_bill - comb_grid, 0),
                    })
                st.dataframe(
                    pd.DataFrame(stmt_rows),
                    use_container_width=True,
                    hide_index=True,
                    height=370,
                )


@st.fragment
def _render_isolated_pillar_deep_dive_fragment(sim_res) -> None:
    """Collapsible isolated contract breakdown (Grid vs. Supplier vs. Taxes) with chart & monthly table."""
    fk = sim_res.financial_kpis
    fc = getattr(sim_res, "financial_config", None)
    if fk is None:
        return
    curr = _get_curr_code(sim_res)

    with st.expander(":material/troubleshoot: 4. Detailed Breakdown by Bill Part (Chart & Monthly Table)", expanded=False):
        st.caption(
            "Inspect each part of your electricity bill separately — with charts and monthly verification numbers."
        )
        pillar_choice = st.radio(
            "Select Contract Part",
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
                    value=f"{_fmt_curr(fk.baseline_pillar2_dso_eur, curr)} / yr",
                    subtext=f"Connection + Transport: {_fmt_curr(fk.baseline_dso_connection_eur + fk.baseline_dso_transport_fixed_eur, curr)}",
                    status="default",
                )
            with d2:
                render_kpi_card(
                    title="With System DSO Bill",
                    value=f"{_fmt_curr(fk.combined_pillar2_dso_eur, curr)} / yr",
                    subtext=f"Peaks: {_fmt_curr(fk.combined_dso_peak_eur, curr)} | Cap: {_fmt_curr(fk.combined_dso_capacity_eur, curr)}",
                    status="ok" if fk.dso_savings_eur >= 0 else "default",
                )
            with d3:
                render_kpi_card(
                    title="Isolated DSO Savings",
                    value=f"{_fmt_curr(fk.dso_savings_eur, curr, signed=True)} / yr",
                    subtext=f"{fmt_num(fk.dso_savings_pct, 1, signed=True)}% vs. current DSO contract",
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
                st.dataframe(_rename_df_currency_cols(sim_res.dso_monthly_df, curr), use_container_width=True, hide_index=True)

        elif pillar_choice == "Energy Supplier Contract Only (Retailer)":
            if fc is not None and not getattr(fc, "enable_pillar_1_supplier", True):
                st.info(
                    ":material/info: Separate Energy Supplier charges are currently **bypassed** because this contract uses a single combined utility bill (energy & grid are billed together under Grid Operator DSO)."
                )
            s1, s2, s3, s4 = st.columns(4)
            with s1:
                render_kpi_card(
                    title="Current Supplier Bill",
                    value=f"{_fmt_curr(fk.baseline_pillar1_supply_eur, curr)} / yr",
                    subtext=f"Peak HT: {_fmt_curr(fk.baseline_supply_peak_ht_eur, curr)} | NT: {_fmt_curr(fk.baseline_supply_offpeak_nt_eur, curr)}",
                    status="default",
                )
            with s2:
                render_kpi_card(
                    title="With System Supplier Bill",
                    value=f"{_fmt_curr(fk.combined_pillar1_supply_eur, curr)} / yr",
                    subtext=f"Peak HT: {_fmt_curr(fk.combined_supply_peak_ht_eur, curr)} | NT: {_fmt_curr(fk.combined_supply_offpeak_nt_eur, curr)}",
                    status="ok" if fk.supplier_savings_eur >= 0 else "default",
                )
            with s3:
                render_kpi_card(
                    title="Isolated Supplier Savings",
                    value=f"{_fmt_curr(fk.supplier_savings_eur, curr, signed=True)} / yr",
                    subtext=f"{fmt_num(fk.supplier_savings_pct, 1, signed=True)}% energy cost change",
                    status="ok" if fk.supplier_savings_eur > 0 else "default",
                )
            with s4:
                render_kpi_card(
                    title="Export & Surcharge Impact",
                    value=f"+{_fmt_curr(fk.solar_export_revenue_eur, curr)} export",
                    subtext=f"Green cert. surcharge: {_fmt_curr(fk.combined_supply_gvo_eur, curr)}/yr",
                    status="ok" if fk.solar_export_revenue_eur > 0 else "default",
                )
            st.plotly_chart(
                create_supplier_isolated_breakdown_figure(sim_res),
                use_container_width=True,
                config={"scrollZoom": False, "displayModeBar": "hover", "responsive": True},
                key="comb_iso_supplier_chart",
            )
            if sim_res.supplier_monthly_df is not None and not sim_res.supplier_monthly_df.empty:
                st.dataframe(_rename_df_currency_cols(sim_res.supplier_monthly_df, curr), use_container_width=True, hide_index=True)

        else:
            cur_mt = fk.baseline_pillar3_metering_eur + fk.baseline_pillar4_taxes_eur
            sys_mt = fk.combined_pillar3_metering_eur + fk.combined_pillar4_taxes_eur
            t1, t2, t3, t4 = st.columns(4)
            with t1:
                render_kpi_card(
                    title="Current Metering & Taxes",
                    value=f"{_fmt_curr(cur_mt, curr)} / yr",
                    subtext=f"Gross tax: {_fmt_curr(fk.baseline_energy_tax_gross_eur, curr)} | Metering: {_fmt_curr(fk.baseline_pillar3_metering_eur, curr)}",
                    status="default",
                )
            with t2:
                render_kpi_card(
                    title="With System Metering & Taxes",
                    value=f"{_fmt_curr(sys_mt, curr)} / yr",
                    subtext=f"Net tax after credit: {_fmt_curr(fk.combined_energy_tax_eur, curr)}",
                    status="ok" if fk.tax_and_metering_savings_eur >= 0 else "default",
                )
            with t3:
                render_kpi_card(
                    title="Tax & Metering Savings",
                    value=f"{_fmt_curr(fk.tax_and_metering_savings_eur, curr, signed=True)} / yr",
                    subtext=f"Annual tax credit: -{_fmt_curr(abs(fk.combined_tax_credit_eur), curr)}/yr",
                    status="ok" if fk.tax_and_metering_savings_eur > 0 else "default",
                )
            with t4:
                render_kpi_card(
                    title="VAT & Gross Total (With System)",
                    value=f"{_fmt_curr(fk.combined_grid_gross_eur, curr)} / yr",
                    subtext=f"Net: {_fmt_curr(fk.combined_grid_total_eur, curr)} + VAT: {_fmt_curr(fk.combined_grid_vat_eur, curr)}",
                    status="default",
                )
            st.plotly_chart(
                create_tax_isolated_breakdown_figure(sim_res),
                use_container_width=True,
                config={"scrollZoom": False, "displayModeBar": "hover", "responsive": True},
                key="comb_iso_tax_chart",
            )
            if sim_res.tax_monthly_df is not None and not sim_res.tax_monthly_df.empty:
                st.dataframe(_rename_df_currency_cols(sim_res.tax_monthly_df, curr), use_container_width=True, hide_index=True)

