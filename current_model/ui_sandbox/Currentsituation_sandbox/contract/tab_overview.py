"""
========================================================================================
Sub-Tab 4: Total Overview & Statement (contract/tab_overview.py)
========================================================================================

Description:
------------
Renders the consolidated Total Overview & Statement view:
  1. Period filter inspector (Full Year Overview vs. Individual Month drilldown).
  2. 4 Executive financial and operational KPI cards.
  3. Cost Donut distribution and 12-Month Stacked Payment series charts.
  4. Itemized 12-Month master accounting statement table.
  5. 15-Year Long-Term Cost Structure & Lifecycle TCO forecast (with discount & escalation rates).
  6. Multi-format export toolbar (12-Month CSV, 15Y TCO CSV, Audit JSON, Contract JSON).
========================================================================================
"""

import io
import json
from typing import Dict, Any, List
import streamlit as st
import pandas as pd

from current_model.ui.common.cards import render_kpi_card
from ui_sandbox.Currentsituation_sandbox.engine.config_and_models import (
    LoadSeries2025,
    StatusQuoConfig2025,
    StatusQuoAnnualResult,
)
from ui_sandbox.Currentsituation_sandbox.engine.status_quo_master import (
    convert_to_financial_cost_breakdown,
)
try:
    from ui_sandbox.Currentsituation_sandbox.contract.charts import (
        create_cost_donut_figure,
        create_monthly_payment_series_figure,
        create_15_year_lifecycle_cost_figure,
    )
except (ImportError, AttributeError):
    try:
        from .charts import (
            create_cost_donut_figure,
            create_monthly_payment_series_figure,
            create_15_year_lifecycle_cost_figure,
        )
    except (ImportError, AttributeError):
        from contract.charts import (
            create_cost_donut_figure,
            create_monthly_payment_series_figure,
            create_15_year_lifecycle_cost_figure,
        )


def render_overview_tab(
    result: StatusQuoAnnualResult,
    active_config: StatusQuoConfig2025,
    load_series: LoadSeries2025,
    key_prefix: str = "currsit_contract"
) -> None:
    """
    Renders the consolidated Total Overview and Statement tab.
    """
    st.markdown("### :material/dashboard: Key Financial & Operational Metrics")

    # 1. Period Filter Selector
    month_options = ["All Months (Full Year 2025 Overview)"] + [r.month_name for r in result.monthly_records]
    col_p_sel, col_p_info = st.columns([2, 3])
    with col_p_sel:
        selected_period = st.selectbox(
            "Billing Period / Month to Inspect:",
            options=month_options,
            index=0,
            key=f"{key_prefix}_period_inspector"
        )
    is_single_month = (selected_period != "All Months (Full Year 2025 Overview)")

    contracted_kw = active_config.dso.contracted_capacity_kw

    with col_p_info:
        if is_single_month:
            st.info(f":material/filter_alt: Inspecting single-month accounting statement for **{selected_period}**", icon=":material/filter_alt:")
        else:
            st.caption(":material/calendar_month: *Consolidated 12-month annual accounting overview (reference year 2025).*")

    # 2. Executive KPI Cards
    col_kpi1, col_kpi2, col_kpi3, col_kpi4 = st.columns(4)
    if is_single_month:
        target_rec = next((r for r in result.monthly_records if r.month_name == selected_period), result.monthly_records[0])
        excess_p = max(0.0, target_rec.consumption.peak_demand_kw - contracted_kw)
        with col_kpi1:
            render_kpi_card(
                title=f":material/receipt_long: {selected_period} Net Total",
                value=f"€ {target_rec.total_net:,.2f}",
                subtext=f"Gross (+{active_config.levies.vat_rate_pct:.0f}% VAT): € {target_rec.total_gross:,.2f} | VAT: € {target_rec.vat_amount:,.2f}",
                status="default"
            )
        with col_kpi2:
            render_kpi_card(
                title=f":material/price_change: {selected_period} Net Rate",
                value=f"€ {target_rec.effective_rate_net_kwh:.4f} / kWh",
                subtext=f"Energy: {target_rec.consumption.total_kwh:,.0f} kWh ({target_rec.consumption.days_count} days)",
                status="default"
            )
        with col_kpi3:
            breach_status = "alert" if excess_p > 0 else "ok"
            breach_sub = f"Overload: +{excess_p:.1f} kW (Limit: {contracted_kw:.0f} kW)" if excess_p > 0 else f"Peak within limit ({contracted_kw:.0f} kW)"
            render_kpi_card(
                title=f":material/speed: {selected_period} Peak Demand",
                value=f"{target_rec.consumption.peak_demand_kw:,.1f} kW",
                subtext=breach_sub,
                status=breach_status
            )
        with col_kpi4:
            supp_cost = target_rec.commercial.supplier_energy_cost + target_rec.commercial.supplier_base_fee
            render_kpi_card(
                title=f":material/account_tree: {selected_period} Actor Split",
                value=f"DSO: € {target_rec.dso.subtotal_dso_net:,.0f}",
                subtext=f"Supplier: € {supp_cost:,.0f} | Meter: € {target_rec.commercial.metering_fee:,.0f}",
                status="default"
            )
    else:
        with col_kpi1:
            render_kpi_card(
                title=":material/receipt_long: Annual Net Invoice",
                value=f"€ {result.total_status_quo_net:,.2f}",
                subtext=f"Gross (+{active_config.levies.vat_rate_pct:.0f}% VAT): € {result.total_status_quo_gross:,.2f}",
                status="default"
            )
        with col_kpi2:
            render_kpi_card(
                title=":material/price_change: Blended Net Rate",
                value=f"€ {result.blended_price_net_kwh:.4f} / kWh",
                subtext=f"Gross: € {result.blended_price_gross_kwh:.4f} / kWh",
                status="default"
            )
        with col_kpi3:
            breach_status = "alert" if result.has_capacity_breach else "ok"
            breach_sub = (
                f"Breach in {len(result.breach_months)} month(s): {result.breach_months}"
                if result.has_capacity_breach
                else f"Max peak {result.annual_peak_demand_kw:.1f} kW ≤ {contracted_kw:.1f} kW"
            )
            render_kpi_card(
                title=":material/speed: Annual Peak Demand",
                value=f"{result.annual_peak_demand_kw:,.1f} kW",
                subtext=breach_sub,
                status=breach_status
            )
        with col_kpi4:
            render_kpi_card(
                title=":material/savings: 15-Year TCO (NPV)",
                value=f"€ {result.tco_15_npv:,.2f}",
                subtext=f"WACC: {active_config.discount_rate_pct:.1f}% | Escalation: {active_config.energy_escalation_pct:.1f}%",
                status="default"
            )

    # 3. Operational Alerts & Breach Status
    if result.has_capacity_breach:
        st.warning(
            f":material/warning: **Capacity Breach Detected**: Recorded peak in month(s) "
            f"{result.breach_months} exceeded reserved grid capacity ({contracted_kw:.1f} kW). "
            f"Under standard grid regulation, capacity fee was adjusted to the actual measured peak for those months.",
            icon=":material/warning:"
        )

    st.markdown("---")

    # 4. Unbundled Charts: Donut & 12-Month Payment Series
    st.markdown("### :material/bar_chart: Cost Distribution & 12-Month Payment Schedule")

    breakdown_adapter = convert_to_financial_cost_breakdown(result, target_month=selected_period)

    col_chart1, col_chart2 = st.columns([1.2, 1.8])
    with col_chart1:
        chart_title = f"Cost Share by Component ({selected_period})" if is_single_month else "Cost Share by Component (Annualized)"
        st.markdown(f"##### {chart_title}")
        donut_fig = create_cost_donut_figure(breakdown_adapter)
        st.plotly_chart(donut_fig, use_container_width=True)

    with col_chart2:
        st.markdown("##### 12-Month Stacked Payment Series")
        annual_adapter = convert_to_financial_cost_breakdown(result)
        series_fig = create_monthly_payment_series_figure(annual_adapter)
        st.plotly_chart(series_fig, use_container_width=True)

    # 5. 12-Month Itemized Statement Table
    st.markdown("### :material/table_view: 12-Month Accounting Statement Table")

    table_data = []
    for r in result.monthly_records:
        table_data.append({
            "Month": r.month_name,
            "Consumption (kWh)": round(r.consumption.total_kwh, 1),
            "Peak kW (P_max)": round(r.consumption.peak_demand_kw, 1),
            "DSO Net (€)": round(r.dso.subtotal_dso_net, 2),
            "Supplier Net (€)": round(r.commercial.supplier_energy_cost + r.commercial.supplier_base_fee, 2),
            "Metering Net (€)": round(r.commercial.metering_fee, 2),
            "Levies Net (€)": round(r.commercial.statutory_levies, 2),
            "Total Net (€)": round(r.total_net, 2),
            f"VAT {active_config.levies.vat_rate_pct:.0f}% (€)": round(r.vat_amount, 2),
            "Total Gross (€)": round(r.total_gross, 2),
            "Net Rate (€/kWh)": round(r.effective_rate_net_kwh, 4),
            "Breach": "YES" if r.dso.is_capacity_breached else "NO"
        })

    df_table = pd.DataFrame(table_data)
    st.dataframe(df_table, use_container_width=True, hide_index=True)

    # 6. 15-Year Long-Term Cost Structure & Lifecycle Projection
    st.markdown("---")
    st.markdown("### :material/trending_up: 15-Year Long-Term Cost Structure & Lifecycle Projection (2025 – 2039)")
    st.caption(
        "Comprehensive 15-year lifecycle forecast consolidating **all 4 cost pillars** (Regulated DSO Grid, "
        "Energy Supplier Commodity, Certified Metering, and Statutory Taxes) assuming "
        f"{active_config.energy_escalation_pct:.1f}% annual inflation and discounted at "
        f"{active_config.discount_rate_pct:.1f}% WACC."
    )

    # Contextual TCO Economics Parameters in Overview
    tco_col1, tco_col2, tco_col3 = st.columns([1, 1, 2])
    with tco_col1:
        new_disc = st.number_input(
            "WACC / Discount Rate r (%):",
            min_value=0.0,
            max_value=25.0,
            value=float(st.session_state.get(f"{key_prefix}_tco_r", active_config.discount_rate_pct)),
            step=0.5,
            key=f"{key_prefix}_tco_r_input",
            help="Discount rate for 15-year Net Present Value (NPV) evaluation"
        )
        if new_disc != st.session_state.get(f"{key_prefix}_tco_r"):
            st.session_state[f"{key_prefix}_tco_r"] = new_disc
    with tco_col2:
        new_esc = st.number_input(
            "Annual Price Escalation g (%):",
            min_value=0.0,
            max_value=25.0,
            value=float(st.session_state.get(f"{key_prefix}_tco_g", active_config.energy_escalation_pct)),
            step=0.5,
            key=f"{key_prefix}_tco_g_input",
            help="Annual compound inflation rate of electricity prices"
        )
        if new_esc != st.session_state.get(f"{key_prefix}_tco_g"):
            st.session_state[f"{key_prefix}_tco_g"] = new_esc
    with tco_col3:
        st.info(
            f":material/info: Lifecycle modeling over **{active_config.evaluation_horizon_years} years** "
            f"with annual compounding.",
            icon=":material/info:"
        )

    horizon_years = int(getattr(active_config, "evaluation_horizon_years", 15))
    g_rate = float(new_esc) / 100.0
    r_rate = float(new_disc) / 100.0
    start_calendar_year = 2025

    base_dso = float(result.total_dso_net)
    base_supp = float(result.total_supplier_net)
    base_meter_taxes = float(result.total_metering_net) + float(result.total_levies_net)
    base_kwh = float(result.total_consumption_kwh)

    tco_15_rows = []
    cum_nominal_spend = 0.0
    total_npv_calc = 0.0
    for i in range(horizon_years):
        esc_factor = (1.0 + g_rate) ** i
        disc_factor = 1.0 / ((1.0 + r_rate) ** (i + 1))

        dso_y = round(base_dso * esc_factor, 2)
        supp_y = round(base_supp * esc_factor, 2)
        met_y = round(base_meter_taxes * esc_factor, 2)
        tot_y = round(dso_y + supp_y + met_y, 2)
        cum_nominal_spend += tot_y
        pv_y = round(tot_y * disc_factor, 2)
        total_npv_calc += pv_y
        blended_y = round((tot_y / base_kwh), 4) if base_kwh > 0 else 0.0

        tco_15_rows.append({
            "Period": f"Year {i + 1}",
            "Calendar Year": start_calendar_year + i,
            "DSO Grid (€)": dso_y,
            "Supplier (€)": supp_y,
            "Metering & Taxes (€)": met_y,
            "Annual Net Spend (€)": tot_y,
            "Cumulative Spend (€)": round(cum_nominal_spend, 2),
            "Discount Factor": round(disc_factor, 4),
            "Present Value (€)": pv_y,
            "Blended Rate (€/kWh)": blended_y,
        })

    df_tco_15 = pd.DataFrame(tco_15_rows)
    total_15y_nominal = round(cum_nominal_spend, 2)
    avg_annual_spend = round(total_15y_nominal / horizon_years, 2)
    yr15_spend = tco_15_rows[-1]["Annual Net Spend (€)"] if tco_15_rows else 0.0

    col_tco_kpi1, col_tco_kpi2, col_tco_kpi3, col_tco_kpi4 = st.columns(4)
    with col_tco_kpi1:
        render_kpi_card(
            title=":material/payments: 15-Year Spend (Nominal)",
            value=f"€ {total_15y_nominal:,.2f}",
            subtext=f"Total cash outlay across {horizon_years} years (+{new_esc:.1f}%/yr)",
            status="default"
        )
    with col_tco_kpi2:
        render_kpi_card(
            title=":material/savings: 15-Year TCO (NPV)",
            value=f"€ {total_npv_calc:,.2f}",
            subtext=f"Discounted present value today @ {new_disc:.1f}% WACC",
            status="default"
        )
    with col_tco_kpi3:
        render_kpi_card(
            title=":material/analytics: Average Annual Spend",
            value=f"€ {avg_annual_spend:,.2f}",
            subtext="Mean annual consolidated electricity budget",
            status="default"
        )
    with col_tco_kpi4:
        render_kpi_card(
            title=":material/event: Projected Year 15 Cost",
            value=f"€ {yr15_spend:,.2f}",
            subtext=f"Compounded budget in {start_calendar_year + horizon_years - 1}",
            status="default"
        )

    # Render interactive 15-Year Stacked Figure
    fig_15y = create_15_year_lifecycle_cost_figure(result, start_year=start_calendar_year)
    st.plotly_chart(fig_15y, use_container_width=True)

    # Itemized 15-Year Cashflow Table
    st.markdown("##### :material/table_rows: 15-Year Annual Financial Schedule")
    st.dataframe(df_tco_15, use_container_width=True, hide_index=True)

    # 7. Export Toolbar (CSV & JSON)
    st.markdown("---")
    st.markdown("##### :material/download: Export Accounting Statements & Configurations")
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
            "total_consumption_kwh": result.total_consumption_kwh,
            "total_status_quo_net": result.total_status_quo_net,
            "total_status_quo_gross": result.total_status_quo_gross,
            "blended_price_net_kwh": result.blended_price_net_kwh,
            "tco_15_npv": total_npv_calc,
            "total_15_year_nominal_spend": total_15y_nominal,
            "monthly_records": table_data,
            "lifecycle_15_year_schedule": tco_15_rows
        }
        json_str = json.dumps(export_payload, indent=2)
        st.download_button(
            label=":material/download: Audit JSON",
            data=json_str,
            file_name="status_quo_2025_audit.json",
            mime="application/json",
            key=f"{key_prefix}_export_json",
            use_container_width=True
        )
    with col_exp4:
        contract_payload = {
            "version": "2025.1",
            "dso": active_config.dso.to_dict(),
            "supplier": active_config.supplier.to_dict(),
            "metering": active_config.metering.to_dict(),
            "levies": active_config.levies.to_dict(),
            "tco": {
                "discount_rate_pct": new_disc,
                "energy_escalation_pct": new_esc,
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
