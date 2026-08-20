"""
========================================================================================
Tab 2: Contract Data & Financial Assessment (current_model/ui/tab2_contract/view.py)
========================================================================================

Description:
------------
Orchestrates Tab 2:
  - Electricity supply contract & dynamic tariff configuration form
  - Automated financial assessment of the status quo (monthly fee, period total, itemized table, and KPIs)
  - Full duration monthly payment schedule (Zahlungsreihe) table and stacked timeseries chart
  - Visual cost distribution donut chart
"""

from typing import Optional, Tuple, Any
import streamlit as st
import pandas as pd
import numpy as np

from current_model.models.contract import Contract
from current_model.models.financial import FinancialCostBreakdown
from current_model.core.financial_engine import compute_financial_bill
from current_model.core.synthetic_engine import aggregate_synthetic_24h
from current_model.ui.common.cards import render_kpi_card
from current_model.ui.tab2_contract.form import render_contract_form
from current_model.ui.tab2_contract.charts import create_cost_donut_figure, create_monthly_payment_series_figure


def _find_active_load_data_in_session() -> Tuple[Optional[Any], str]:
    """
    Finds the active consumption load dataset created in Tab 1
    (either CSV processed time series or Synthetic 24h consumers).
    Returns (data, source_type_description).
    """
    # 1. Check for CSV calculated datasets
    for key, val in st.session_state.items():
        if "calc_data" in key and isinstance(val, dict) and "df_clean" in val:
            df_clean = val["df_clean"]
            if isinstance(df_clean, pd.DataFrame) and not df_clean.empty:
                return df_clean, "CSV Real Meter Data"

    # 2. Check for Synthetic consumer lists
    for key, val in st.session_state.items():
        if "consumers" in key and isinstance(val, list) and len(val) > 0:
            df_day, total_curve, _ = aggregate_synthetic_24h(val)
            if len(total_curve) > 0 and total_curve.sum() > 0:
                return df_day, "24-Hour Synthetic Simulation"

    return None, "None"


def render_tab2_contract(key_prefix: str = "tab2") -> Contract:
    """
    Renders Tab 2: Contract Configuration and Financial Assessment.
    """
    # 1. Guidance Warning
    st.warning("Should you wish to not use a contract, leave the fields empty.")

    # 2. Electricity Supply Contract & Tariff Configuration Form
    contract = render_contract_form(as_expander=False, key_prefix=key_prefix)

    st.divider()

    # 3. Automated Financial Cost Assessment (Status Quo)
    load_data, source_desc = _find_active_load_data_in_session()

    st.subheader("Monthly Cost & Financial Assessment (Status Quo)")

    if load_data is None:
        st.info("Configure a consumption profile in Tab 1 (Synthetic Simulator or CSV Ingestion) to view the automated monthly financial assessment.")
        return contract

    st.caption(f"Calculated based on active profile: **{source_desc}**")

    # Compute complete financial breakdown
    breakdown: FinancialCostBreakdown = compute_financial_bill(load_data=load_data, contract=contract)
    curr = breakdown.currency

    # 4. Financial KPI Cards
    kpi_col1, kpi_col2, kpi_col3, kpi_col4 = st.columns(4)
    with kpi_col1:
        render_kpi_card(
            title="Estimated Monthly Cost",
            value=f"{breakdown.total_gross_monthly:,.2f} {curr}",
            subtext=f"Net: {breakdown.total_net_monthly:,.2f} | Taxes: {breakdown.total_taxes_monthly:,.2f}"
        )
    with kpi_col2:
        render_kpi_card(
            title="Total Cost over Period",
            value=f"{breakdown.total_gross_period:,.2f} {curr}",
            subtext=f"Analyzed period: {breakdown.duration_days:.0f} days ({breakdown.total_consumption_kwh:,.0f} kWh)"
        )
    with kpi_col3:
        render_kpi_card(
            title="Effective Electricity Price",
            value=f"{breakdown.effective_kwh_price:.4f} {curr}/kWh",
            subtext="All-inclusive average unit price"
        )
    with kpi_col4:
        render_kpi_card(
            title="Fixed Cost Share",
            value=f"{breakdown.fixed_cost_share_pct:.1f} %",
            subtext=f"Capacity & Base: {breakdown.capacity_cost_monthly + breakdown.base_fee_monthly:,.2f} {curr}/mo"
        )

    # 5. Itemized Breakdown Table & Donut Chart
    t_col, c_col = st.columns([7, 5])

    with t_col:
        st.markdown("#### Itemized Cost Breakdown (Normalized Month vs. Period)")
        table_rows = []
        for item in breakdown.line_items:
            table_rows.append({
                "Category": item.category,
                "Description": item.description,
                "Quantity": f"{item.basis_quantity:,.2f} {item.unit}",
                "Unit Rate": f"{item.unit_rate:.3f} {curr}",
                "Period Cost": f"{item.cost_period:,.2f} {curr}",
                "Monthly Cost": f"{item.cost_monthly:,.2f} {curr}",
                "Share": f"{item.share_pct:.1f} %"
            })

        if table_rows:
            df_invoice = pd.DataFrame(table_rows)
            st.dataframe(df_invoice, use_container_width=True, hide_index=True)

        if breakdown.contracted_capacity_kw > 0:
            st.caption(
                f"Capacity Utilization: Peak demand measured at **{breakdown.peak_demand_kw:,.1f} kW** "
                f"on **{breakdown.contracted_capacity_kw:,.1f} kW** contracted capacity "
                f"({breakdown.capacity_utilization_pct:.1f}% utilization)."
            )

    with c_col:
        fig_donut = create_cost_donut_figure(breakdown)
        st.plotly_chart(fig_donut, use_container_width=True)

    # 6. Monthly Payment Schedule across Full Duration (Zahlungsreihe)
    st.divider()
    st.subheader("Monthly Payment Schedule across Full Duration (Zahlungsreihe)")
    st.caption("Month-by-month billing series detailing individual cost components, taxes, and total invoice amounts over the complete analyzed period.")

    fig_series = create_monthly_payment_series_figure(breakdown)
    st.plotly_chart(fig_series, use_container_width=True)

    if breakdown.monthly_series:
        series_rows = []
        total_kwh_sum = 0.0
        total_net_sum = 0.0
        total_tax_sum = 0.0
        total_gross_sum = 0.0

        for m in breakdown.monthly_series:
            total_kwh_sum += m.energy_kwh
            total_net_sum += m.total_net
            total_tax_sum += m.taxes_and_levies
            total_gross_sum += m.total_gross

            series_rows.append({
                "Month / Period": m.period_label,
                "Days": m.days_count,
                f"Energy ({curr})": f"{m.energy_cost_net:,.2f}",
                f"Capacity ({curr})": f"{m.capacity_cost_net:,.2f}",
                f"Penalties ({curr})": f"{m.penalty_cost_net:,.2f}",
                f"Base Fee ({curr})": f"{m.base_fee_net:,.2f}",
                f"Taxes & Levies ({curr})": f"{m.taxes_and_levies:,.2f}",
                f"Total Net ({curr})": f"{m.total_net:,.2f}",
                f"Total Gross ({curr})": f"{m.total_gross:,.2f}",
                f"Rate ({curr}/kWh)": f"{m.effective_rate_kwh:.4f}"
            })

        # Append Total Summary Row
        overall_avg_rate = (total_gross_sum / total_kwh_sum) if total_kwh_sum > 0 else 0.0
        series_rows.append({
            "Month / Period": "TOTAL / FULL PERIOD",
            "Days": int(sum(m.days_count for m in breakdown.monthly_series)),
            f"Energy ({curr})": f"{sum(m.energy_cost_net for m in breakdown.monthly_series):,.2f}",
            f"Capacity ({curr})": f"{sum(m.capacity_cost_net for m in breakdown.monthly_series):,.2f}",
            f"Penalties ({curr})": f"{sum(m.penalty_cost_net for m in breakdown.monthly_series):,.2f}",
            f"Base Fee ({curr})": f"{sum(m.base_fee_net for m in breakdown.monthly_series):,.2f}",
            f"Taxes & Levies ({curr})": f"{total_tax_sum:,.2f}",
            f"Total Net ({curr})": f"{total_net_sum:,.2f}",
            f"Total Gross ({curr})": f"{total_gross_sum:,.2f}",
            f"Rate ({curr}/kWh)": f"{overall_avg_rate:.4f}"
        })

        df_series = pd.DataFrame(series_rows)
        st.dataframe(df_series, use_container_width=True, hide_index=True)

    return contract
