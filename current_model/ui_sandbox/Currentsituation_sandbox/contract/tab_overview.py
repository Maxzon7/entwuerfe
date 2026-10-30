"""
========================================================================================
Sub-Tab 4: Executive Overview & 15-Year TCO (contract/tab_overview.py)
========================================================================================

Implements the structured Executive Cost Overview & 15-Year Lifecycle Projection:
  1. Period Filter Selector (Full Year 2025 vs. Single Calendar Month)
  2. Executive 4-Pillar Cost Summary Table:
     Columns: Pillar | Net Annual ({CURR}) | Net Monthly Avg ({CURR}) | Effective Rate ({CURR}/kWh) | Share (%)
     Followed by Net Total, Value Added Tax (VAT), and Total Gross Bill rows.
  3. Cost Component Distribution Donut Chart & 12-Month Stacked Payment Schedule
  4. 12-Month Itemized Accounting Statement Table
  5. 15-Year Long-Term Cost Structure & Lifecycle Projection (2025 - 2039) + 4-Way Export
========================================================================================
"""

import io
import json
from typing import Dict, Any, List
import streamlit as st
import pandas as pd

try:
    from current_model.ui.common.cards import render_kpi_card
except ImportError:
    from ui.common.cards import render_kpi_card

try:
    from ui_sandbox.Currentsituation_sandbox.engine.config_and_models import (
        StatusQuoConfig2025,
        StatusQuoAnnualResult,
    )
    from ui_sandbox.Currentsituation_sandbox.engine.status_quo_master import (
        convert_to_financial_cost_breakdown,
    )
    from ui_sandbox.Currentsituation_sandbox.contract.charts import (
        create_cost_donut_figure,
        create_monthly_payment_series_figure,
        create_15_year_lifecycle_cost_figure,
    )
except ImportError:
    from current_model.ui_sandbox.Currentsituation_sandbox.engine.config_and_models import (
        StatusQuoConfig2025,
        StatusQuoAnnualResult,
    )
    from current_model.ui_sandbox.Currentsituation_sandbox.engine.status_quo_master import (
        convert_to_financial_cost_breakdown,
    )
    from current_model.ui_sandbox.Currentsituation_sandbox.contract.charts import (
        create_cost_donut_figure,
        create_monthly_payment_series_figure,
        create_15_year_lifecycle_cost_figure,
    )


def _render_executive_summary_table_html(
    result: StatusQuoAnnualResult,
    selected_period: str,
    is_single_month: bool
) -> str:
    """Renders the structured 4-Pillar Executive Cost Summary Table without 4-space markdown indentation."""
    curr = getattr(result.config, "currency_code", "EUR")
    en_p1 = getattr(result.config, "enable_pillar_1_supplier", True)
    en_p2 = getattr(result.config, "enable_pillar_2_dso", True)
    en_p3 = getattr(result.config, "enable_pillar_3_metering", True)
    en_p4 = getattr(result.config, "enable_pillar_4_taxes", True)

    if is_single_month:
        rec = next((r for r in result.monthly_records if r.month_name == selected_period), result.monthly_records[0])
        kwh = max(1.0, rec.consumption.total_kwh)
        p1_net = round(rec.commercial.supplier_energy_cost + rec.commercial.supplier_base_fee, 2)
        p2_net = round(rec.dso.subtotal_dso_net, 2)
        p3_net = round(rec.commercial.metering_fee, 2)
        p4_net = round(rec.commercial.statutory_levies, 2)
        tot_net = round(rec.total_net, 2)
        vat_val = round(rec.vat_amount, 2)
        tot_gross = round(rec.total_gross, 2)
        col2_hdr = f"{selected_period} Net ({curr})"
        col3_hdr = f"Annualized Equiv. ({curr}/yr)"
        mult_col3 = 12.0
    else:
        kwh = max(1.0, result.total_consumption_kwh)
        p1_net = round(result.total_supplier_net, 2)
        p2_net = round(result.total_dso_net, 2)
        p3_net = round(result.total_metering_net, 2)
        p4_net = round(result.total_levies_net, 2)
        tot_net = round(result.total_status_quo_net, 2)
        vat_val = round(result.total_vat_amount, 2)
        tot_gross = round(result.total_status_quo_gross, 2)
        col2_hdr = f"Net Annual ({curr})"
        col3_hdr = f"Net Monthly Avg ({curr})"
        mult_col3 = 1.0 / 12.0

    pillars = [
        ("Pillar 1: Energy Supply (Retailer)", p1_net, "#38bdf8", en_p1),
        ("Pillar 2: Grid Network (DSO)", p2_net, "#f59e0b", en_p2),
        ("Pillar 3: Metering & Telemetry", p3_net, "#8b5cf6", en_p3),
        ("Pillar 4: Statutory Taxes & Levies", p4_net, "#10b981", en_p4),
    ]

    rows_html: List[str] = []
    for idx, (label, val_net, color_hex, is_en) in enumerate(pillars):
        bg = "#1e293b" if idx % 2 == 0 else "#0f172a"
        col3_val = val_net * mult_col3
        eff_r = val_net / kwh
        share_pct = (val_net / max(0.01, tot_net)) * 100.0
        row_opacity = "" if is_en else " opacity: 0.50;"
        lbl_str = label if is_en else f"{label} <span style='color:#94a3b8; font-size:0.78rem;'>[BYPASSED / BUNDLED]</span>"
        rows_html.append(
            f'<tr style="background-color: {bg}; border-bottom: 1px solid #334155;{row_opacity}">'
            f'<td style="padding: 9px 12px; font-weight: 600; color: #f8fafc; font-size: 0.88rem;">'
            f'<span style="display:inline-block; width:10px; height:10px; border-radius:2px; background-color:{color_hex}; margin-right:8px;"></span>{lbl_str}</td>'
            f'<td style="padding: 9px 12px; text-align: right; font-weight: 600; color: #f1f5f9; font-size: 0.90rem;">{curr} {val_net:,.2f}</td>'
            f'<td style="padding: 9px 12px; text-align: right; color: #cbd5e1; font-size: 0.88rem;">{curr} {col3_val:,.2f}</td>'
            f'<td style="padding: 9px 12px; text-align: right; color: #cbd5e1; font-size: 0.88rem; font-family: monospace;">{curr} {eff_r:.4f}/kWh</td>'
            f'<td style="padding: 9px 12px; text-align: right; font-weight: 600; color: {color_hex}; font-size: 0.88rem;">{share_pct:.1f}%</td>'
            f'</tr>'
        )

    vat_pct = result.config.levies.vat_rate_pct
    net_col3 = tot_net * mult_col3
    vat_col3 = vat_val * mult_col3
    gross_col3 = tot_gross * mult_col3
    eff_net_r = tot_net / kwh
    eff_vat_r = vat_val / kwh
    eff_gross_r = tot_gross / kwh

    body_str = "\n".join(rows_html)
    return (
        f'<div style="border-radius: 8px; border: 1px solid #334155; overflow: hidden; margin-bottom: 18px;">\n'
        f'<table style="width: 100%; border-collapse: collapse; font-family: -apple-system, BlinkMacSystemFont, sans-serif;">\n'
        f'<thead>\n'
        f'<tr style="background-color: #090d16; border-bottom: 2px solid #475569; color: #94a3b8; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.05em;">'
        f'<th style="padding: 10px 12px; text-align: left; width: 34%;">Cost Pillar / Bill Component</th>'
        f'<th style="padding: 10px 12px; text-align: right; width: 18%;">{col2_hdr}</th>'
        f'<th style="padding: 10px 12px; text-align: right; width: 18%;">{col3_hdr}</th>'
        f'<th style="padding: 10px 12px; text-align: right; width: 18%;">Effective Rate ({curr}/kWh)</th>'
        f'<th style="padding: 10px 12px; text-align: right; width: 12%;">Net Share (%)</th>'
        f'</tr>\n'
        f'</thead>\n'
        f'<tbody>\n'
        f'{body_str}\n'
        f'<tr style="background-color: #0b1329; border-top: 2px solid #38bdf8; font-weight: 700;">'
        f'<td style="padding: 10px 12px; color: #38bdf8; font-size: 0.90rem;">= TOTAL NET ELECTRICITY BILL (1 + 2 + 3 + 4)</td>'
        f'<td style="padding: 10px 12px; text-align: right; color: #38bdf8; font-size: 0.95rem;">{curr} {tot_net:,.2f}</td>'
        f'<td style="padding: 10px 12px; text-align: right; color: #38bdf8; font-size: 0.90rem;">{curr} {net_col3:,.2f}</td>'
        f'<td style="padding: 10px 12px; text-align: right; color: #38bdf8; font-size: 0.90rem; font-family: monospace;">{curr} {eff_net_r:.4f}/kWh</td>'
        f'<td style="padding: 10px 12px; text-align: right; color: #38bdf8; font-size: 0.90rem;">100.0%</td>'
        f'</tr>\n'
        f'<tr style="background-color: #0f172a; border-top: 1px solid #334155;">'
        f'<td style="padding: 8px 12px; color: #94a3b8; font-size: 0.86rem;">+ Value Added Tax ({vat_pct:.0f}% VAT)</td>'
        f'<td style="padding: 8px 12px; text-align: right; color: #cbd5e1; font-size: 0.88rem;">{curr} {vat_val:,.2f}</td>'
        f'<td style="padding: 8px 12px; text-align: right; color: #94a3b8; font-size: 0.86rem;">{curr} {vat_col3:,.2f}</td>'
        f'<td style="padding: 8px 12px; text-align: right; color: #94a3b8; font-size: 0.85rem; font-family: monospace;">{curr} {eff_vat_r:.4f}/kWh</td>'
        f'<td style="padding: 8px 12px; text-align: right; color: #64748b; font-size: 0.84rem;">—</td>'
        f'</tr>\n'
        f'<tr style="background-color: #111827; border-top: 2px solid #10b981; font-weight: 800;">'
        f'<td style="padding: 11px 12px; color: #ffffff; font-size: 0.94rem;">= TOTAL GROSS BILL AMOUNT DUE</td>'
        f'<td style="padding: 11px 12px; text-align: right; color: #10b981; font-size: 1.04rem;">{curr} {tot_gross:,.2f}</td>'
        f'<td style="padding: 11px 12px; text-align: right; color: #e2e8f0; font-size: 0.92rem;">{curr} {gross_col3:,.2f}</td>'
        f'<td style="padding: 11px 12px; text-align: right; color: #10b981; font-size: 0.92rem; font-family: monospace;">{curr} {eff_gross_r:.4f}/kWh</td>'
        f'<td style="padding: 11px 12px; text-align: right; color: #64748b; font-size: 0.84rem;">—</td>'
        f'</tr>\n'
        f'</tbody>\n'
        f'</table>\n'
        f'</div>'
    )


def render_overview_tab(
    result: StatusQuoAnnualResult,
    active_config: StatusQuoConfig2025,
    key_prefix: str = "currsit_contract"
) -> None:
    """
    Renders Sub-Tab 4: Executive Cost Summary Table, Cost Distribution Charts,
    12-Month Statement, and 15-Year TCO Lifecycle Projection.
    """
    curr = getattr(active_config, "currency_code", "EUR")
    st.markdown("#### :material/analytics: Executive Cost Summary & 15-Year Lifecycle Projection")

    # 1. Period Filter Selector
    month_options = ["All Months (Full Year 2025 Overview)"] + [r.month_name for r in result.monthly_records]
    col_p_sel, col_p_info = st.columns([2, 3])
    with col_p_sel:
        selected_period = st.selectbox(
            "Billing Period to Inspect:",
            options=month_options,
            index=0,
            key=f"{key_prefix}_period_inspector"
        )
    is_single_month = (selected_period != "All Months (Full Year 2025 Overview)")

    with col_p_info:
        if is_single_month:
            st.info(
                f":material/filter_alt: Displaying single-month cost breakdown for **{selected_period} 2025**.",
                icon=":material/filter_alt:"
            )
        else:
            st.caption(
                f":material/calendar_month: **Consolidated Full-Year 2025 Statement** | "
                f"Total Consumption: **{result.total_consumption_kwh:,.0f} kWh** | "
                f"Measured Annual Peak: **{result.annual_peak_demand_kw:,.1f} kW** "
                f"(Contracted Capacity: **{active_config.dso.contracted_capacity_kw:,.1f} kW**)."
            )

    # 2. Structured 4-Pillar Executive Cost Summary Table
    st.markdown("##### :material/receipt_long: 1. Executive 4-Pillar Electricity Cost Summary")
    st.markdown(
        _render_executive_summary_table_html(
            result=result,
            selected_period=selected_period,
            is_single_month=is_single_month
        ),
        unsafe_allow_html=True
    )

    if result.has_capacity_breach:
        st.warning(
            f":material/warning: **Contracted Capacity Breach Notice:** Measured monthly peak demand in month(s) "
            f"{result.breach_months} exceeded the contracted grid capacity ({active_config.dso.contracted_capacity_kw:.1f} kW).",
            icon=":material/warning:"
        )

    st.markdown("---")

    # 3. Cost Distribution Donut & 12-Month Stacked Payment Schedule
    st.markdown("##### :material/bar_chart: 2. Cost Component Distribution & 12-Month Payment Schedule")

    breakdown_adapter = convert_to_financial_cost_breakdown(result, target_month=selected_period)

    col_chart1, col_chart2 = st.columns([1.2, 1.8])
    with col_chart1:
        chart_title = f"Cost Share by Component ({selected_period})" if is_single_month else "Cost Share by Component (Annual)"
        st.markdown(f"###### {chart_title}")
        donut_fig = create_cost_donut_figure(breakdown_adapter)
        st.plotly_chart(donut_fig, use_container_width=True, key=f"{key_prefix}_ov_donut_chart")

    with col_chart2:
        st.markdown("###### 12-Month Stacked Payment Schedule")
        annual_adapter = convert_to_financial_cost_breakdown(result)
        series_fig = create_monthly_payment_series_figure(
            annual_adapter,
            highlight_month=selected_period if is_single_month else None
        )
        st.plotly_chart(series_fig, use_container_width=True, key=f"{key_prefix}_ov_series_chart")

    # 4. 12-Month Itemized Accounting Statement Table
    st.markdown("##### :material/table_view: 3. 12-Month Itemized Accounting Statement")

    table_data = []
    for r in result.monthly_records:
        table_data.append({
            "Month": r.month_name,
            "Consumption (kWh)": round(r.consumption.total_kwh, 1),
            "Peak Demand (kW)": round(r.consumption.peak_demand_kw, 1),
            f"1. Energy Supply ({curr})": round(r.commercial.supplier_energy_cost + r.commercial.supplier_base_fee, 2),
            f"2. Grid Network DSO ({curr})": round(r.dso.subtotal_dso_net, 2),
            f"3. Metering ({curr})": round(r.commercial.metering_fee, 2),
            f"4. Statutory Taxes ({curr})": round(r.commercial.statutory_levies, 2),
            f"Total Net ({curr})": round(r.total_net, 2),
            f"VAT ({curr})": round(r.vat_amount, 2),
            f"Total Gross ({curr})": round(r.total_gross, 2),
            f"Blended Rate Net ({curr}/kWh)": round(r.effective_rate_net_kwh, 4),
            "Capacity Breach": "YES" if r.dso.is_capacity_breached else "NO"
        })

    df_table = pd.DataFrame(table_data)
    st.dataframe(df_table, use_container_width=True, hide_index=True)

    # 5. 15-Year Long-Term Cost Structure & Lifecycle Projection
    st.markdown("---")
    st.markdown("##### :material/trending_up: 4. 15-Year Lifecycle Economics & TCO Projection (2025 – 2039)")
    st.caption(
        "15-year lifecycle expenditure forecast across all 4 cost pillars assuming "
        f"{active_config.energy_escalation_pct:.1f}% annual cost escalation and discounted at "
        f"{active_config.discount_rate_pct:.1f}% WACC."
    )

    horizon_years = int(getattr(active_config, "evaluation_horizon_years", 15))
    g_rate = float(getattr(active_config, "energy_escalation_pct", 3.0)) / 100.0
    r_rate = float(getattr(active_config, "discount_rate_pct", 5.0)) / 100.0
    start_calendar_year = 2025

    base_supp = float(result.total_supplier_net)
    base_dso = float(result.total_dso_net)
    base_meter_taxes = float(result.total_metering_net) + float(result.total_levies_net)
    base_kwh = float(result.total_consumption_kwh)

    tco_15_rows = []
    cum_nominal_spend = 0.0
    for i in range(horizon_years):
        esc_factor = (1.0 + g_rate) ** i
        disc_factor = 1.0 / ((1.0 + r_rate) ** (i + 1))

        supp_y = round(base_supp * esc_factor, 2)
        dso_y = round(base_dso * esc_factor, 2)
        met_y = round(base_meter_taxes * esc_factor, 2)
        tot_y = round(supp_y + dso_y + met_y, 2)
        cum_nominal_spend += tot_y
        pv_y = round(tot_y * disc_factor, 2)
        blended_y = round((tot_y / base_kwh), 4) if base_kwh > 0 else 0.0

        tco_15_rows.append({
            "Period": f"Year {i + 1}",
            "Calendar Year": start_calendar_year + i,
            f"1. Energy Supply ({curr})": supp_y,
            f"2. Grid Network DSO ({curr})": dso_y,
            f"3 & 4. Metering & Taxes ({curr})": met_y,
            f"Annual Net Spend ({curr})": tot_y,
            f"Cumulative Spend ({curr})": round(cum_nominal_spend, 2),
            "Discount Factor": round(disc_factor, 4),
            f"Present Value ({curr})": pv_y,
            f"Blended Rate Net ({curr}/kWh)": blended_y,
        })

    df_tco_15 = pd.DataFrame(tco_15_rows)
    total_15y_nominal = round(cum_nominal_spend, 2)
    avg_annual_spend = round(total_15y_nominal / horizon_years, 2)
    yr15_spend = tco_15_rows[-1][f"Annual Net Spend ({curr})"] if tco_15_rows else 0.0

    col_tco_kpi1, col_tco_kpi2, col_tco_kpi3, col_tco_kpi4 = st.columns(4)
    with col_tco_kpi1:
        render_kpi_card(
            title=":material/payments: 15-Year Spend (Nominal)",
            value=f"{curr} {total_15y_nominal:,.2f}",
            subtext=f"Total cash outflow over {horizon_years} yrs (+{active_config.energy_escalation_pct:.1f}%/yr)",
            status="default"
        )
    with col_tco_kpi2:
        render_kpi_card(
            title=":material/savings: 15-Year TCO (NPV)",
            value=f"{curr} {result.tco_15_npv:,.2f}",
            subtext=f"Discounted present value @ {active_config.discount_rate_pct:.1f}% WACC",
            status="default"
        )
    with col_tco_kpi3:
        render_kpi_card(
            title=":material/analytics: Average Annual Spend",
            value=f"{curr} {avg_annual_spend:,.2f}",
            subtext="Mean annual electricity budget (Net)",
            status="default"
        )
    with col_tco_kpi4:
        render_kpi_card(
            title=":material/event: Projected Year 15 Cost",
            value=f"{curr} {yr15_spend:,.2f}",
            subtext=f"Escalated annual budget in {start_calendar_year + horizon_years - 1}",
            status="default"
        )

    fig_15y = create_15_year_lifecycle_cost_figure(result, start_year=start_calendar_year)
    st.plotly_chart(fig_15y, use_container_width=True, key=f"{key_prefix}_ov_tco15_chart")

    with st.expander(":material/table_rows: 15-Year Annual Financial Schedule & Multi-Format Export", expanded=False):
        st.dataframe(df_tco_15, use_container_width=True, hide_index=True)

        col_exp1, col_exp2, col_exp3, col_exp4 = st.columns(4)
        with col_exp1:
            csv_buf = io.StringIO()
            df_table.to_csv(csv_buf, index=False, sep=";")
            st.download_button(
                label=":material/download: 12-Month CSV",
                data=csv_buf.getvalue(),
                file_name="status_quo_2025_statement.csv",
                mime="text/csv",
                key=f"{key_prefix}_export_csv",
                use_container_width=True
            )
        with col_exp2:
            csv_15y_buf = io.StringIO()
            df_tco_15.to_csv(csv_15y_buf, index=False, sep=";")
            st.download_button(
                label=":material/download: 15-Year TCO CSV",
                data=csv_15y_buf.getvalue(),
                file_name="status_quo_15_year_lifecycle_projection.csv",
                mime="text/csv",
                key=f"{key_prefix}_export_15y_csv",
                use_container_width=True
            )
        with col_exp3:
            export_payload = {
                "evaluation_year": 2025,
                "currency": curr,
                "total_consumption_kwh": result.total_consumption_kwh,
                "total_status_quo_net": result.total_status_quo_net,
                "total_status_quo_gross": result.total_status_quo_gross,
                "blended_price_net_kwh": result.blended_price_net_kwh,
                "tco_15_npv": result.tco_15_npv,
                "total_15_year_nominal_spend": total_15y_nominal,
                "monthly_records": table_data,
                "lifecycle_15_year_schedule": tco_15_rows
            }
            st.download_button(
                label=":material/download: Audit JSON",
                data=json.dumps(export_payload, indent=2),
                file_name="status_quo_2025_audit.json",
                mime="application/json",
                key=f"{key_prefix}_export_json",
                use_container_width=True
            )
        with col_exp4:
            contract_payload = {
                "version": "2025.2",
                "currency": curr,
                "market_mode": getattr(active_config, "market_mode", "unbundled_4_pillar"),
                "dso": active_config.dso.to_dict(),
                "supplier": active_config.supplier.to_dict(),
                "metering": active_config.metering.to_dict(),
                "levies": active_config.levies.to_dict(),
                "tco": {
                    "discount_rate_pct": active_config.discount_rate_pct,
                    "energy_escalation_pct": active_config.energy_escalation_pct,
                    "evaluation_horizon_years": active_config.evaluation_horizon_years,
                }
            }
            st.download_button(
                label=":material/save: Contract JSON",
                data=json.dumps(contract_payload, indent=2),
                file_name="unbundled_contract_2025.json",
                mime="application/json",
                key=f"{key_prefix}_export_contract",
                use_container_width=True
            )
