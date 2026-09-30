"""
========================================================================================
Contract & Financial Assessment View (current_model/ui/tab2_contract/view.py)
========================================================================================

Description:
------------
Main view component for Tab 2 (Contract Data & Billing Assessment):
  - Electricity supply contract configuration form.
  - Active load dataset finder synchronizing with Tab 1.
  - Period filter allowing inspection of Full Duration or individual calendar months (e.g. Feb 2026).
  - Financial KPI metric cards in the selected currency (ARS, EUR, USD, etc.).
  - Itemized cost breakdown table and cost component Donut chart.
  - Interactive full-duration payment schedule timeseries chart (Zahlungsreihe) and summary table.
"""

from typing import Tuple, Optional, Any, List
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
from current_model.ui.tab2_contract.comparison_view import render_contract_comparison_view


def _find_active_load_data_in_session() -> Tuple[Optional[Any], str]:
    """
    Finds the active consumption load dataset created in Tab 1
    (either CSV real meter timeseries, 365-Day Annual Synthetic, or 24h Synthetic).
    Returns (data, source_type_description).
    """
    active_source = st.session_state.get("tab1_active_source", "csv")

    if active_source == "csv":
        # 1. Directly check the active CSV dataframe
        if "active_csv_df" in st.session_state and isinstance(st.session_state["active_csv_df"], pd.DataFrame):
            df_active = st.session_state["active_csv_df"]
            if not df_active.empty:
                fname = st.session_state.get("active_csv_filename", "Uploaded CSV")
                return df_active, f"CSV Real Meter Data ({fname})"

        # Fallback to reverse scan of calc_data
        for key in reversed(list(st.session_state.keys())):
            if "calc_data" in key and isinstance(st.session_state[key], dict) and "df_clean" in st.session_state[key]:
                df_clean = st.session_state[key]["df_clean"]
                if isinstance(df_clean, pd.DataFrame) and not df_clean.empty:
                    return df_clean, "CSV Real Meter Data"

        # Fallback to synthetic
        if "active_synthetic_df" in st.session_state and isinstance(st.session_state["active_synthetic_df"], pd.DataFrame):
            df_syn = st.session_state["active_synthetic_df"]
            if not df_syn.empty:
                return df_syn, "Synthetic Simulation"

    else:
        # Prioritize Synthetic
        if "active_synthetic_df" in st.session_state and isinstance(st.session_state["active_synthetic_df"], pd.DataFrame):
            df_syn = st.session_state["active_synthetic_df"]
            if not df_syn.empty:
                return df_syn, "Synthetic Simulation"

        if "active_csv_df" in st.session_state and isinstance(st.session_state["active_csv_df"], pd.DataFrame):
            df_active = st.session_state["active_csv_df"]
            if not df_active.empty:
                fname = st.session_state.get("active_csv_filename", "Uploaded CSV")
                return df_active, f"CSV Real Meter Data ({fname})"

    # Fallback to consumer list if exists
    for key, val in st.session_state.items():
        if "consumers" in key and isinstance(val, list) and len(val) > 0:
            df_day, total_curve, _ = aggregate_synthetic_24h(val)
            if len(total_curve) > 0 and total_curve.sum() > 0:
                return df_day, "24-Hour Synthetic Simulation"

    return None, "None"


def render_tab2_base_contract(key_prefix: str = "app_tab2") -> Contract:
    """
    Renders the foundational Status Quo Contract Configuration and Financial Assessment.
    Provides the fixed commercial baseline against which all sub-scenario investments are measured.
    """
    load_data, source_desc = _find_active_load_data_in_session()

    # 1. Guidance Warning
    st.warning("Should you wish to not use a contract, leave the fields empty.")

    # 2. Electricity Supply Contract & Tariff Configuration Form
    contract = render_contract_form(as_expander=False, key_prefix=key_prefix)
    st.session_state["active_contract"] = contract
    st.session_state[f"{key_prefix}_contract_model"] = contract
    if "project_container" in st.session_state:
        proj = st.session_state["project_container"]
        if proj and hasattr(proj, "base_scenario") and proj.base_scenario is not None:
            proj.base_scenario.base_contract = contract

    st.divider()

    # 3. Automated Financial Cost Assessment (Status Quo)
    st.subheader("Monthly Cost & Financial Assessment (Current situation)")

    if load_data is None:
        st.info("Configure a consumption profile in Tab 2 (Consumption) to view the automated monthly financial assessment.")
    else:
        st.caption(f"Calculated based on active profile: **{source_desc}**")

        # Compute complete full duration financial breakdown
        full_breakdown: FinancialCostBreakdown = compute_financial_bill(load_data=load_data, contract=contract)
        st.session_state["active_bill_breakdown"] = full_breakdown
        if "project_container" in st.session_state:
            proj = st.session_state["project_container"]
            if proj and hasattr(proj, "base_scenario"):
                dur = getattr(full_breakdown, "duration_days", 365)
                factor = (365.0 / dur) if dur > 0 else 1.0
                ann_cost = full_breakdown.total_gross_period * factor
                proj.base_scenario.baseline_annual_cost = ann_cost
                proj.base_scenario.baseline_15year_cost = ann_cost * 18.5989
                proj.base_scenario.base_contract = contract

        curr = getattr(contract, "currency", "ARS")

        # 4. Period Filter Selector (Full Duration vs. Single Month Inspection)
        is_synthetic_annual = (len(full_breakdown.monthly_series) == 12 and full_breakdown.duration_days <= 1.5)
        overview_label = "All Months (Full Year Overview)" if is_synthetic_annual else "All Months (Full Duration Overview)"
        month_options = [overview_label]
        if full_breakdown.monthly_series:
            month_options += [m.period_label for m in full_breakdown.monthly_series]

        col_sel1, col_sel2 = st.columns([5, 3])
        with col_sel1:
            selected_period = st.selectbox(
                "Select Billing Period / Month to Inspect:",
                options=month_options,
                index=0,
                key=f"{key_prefix}_period_select"
            )
        with col_sel2:
            st.write("")
            st.write("")
            is_single_month = (selected_period != overview_label)
            if is_single_month:
                st.info(f"Viewing single-month detail for **{selected_period}**")

        # If single month selected, compute exact single month breakdown
        if is_single_month:
            breakdown = compute_financial_bill(load_data=load_data, contract=contract, target_month=selected_period)
        else:
            breakdown = full_breakdown

        # 5. Financial KPI Cards
        kpi_col1, kpi_col2, kpi_col3, kpi_col4 = st.columns(4)
        if is_single_month:
            excess_p = max(0.0, breakdown.peak_demand_kw - breakdown.contracted_capacity_kw)
            with kpi_col1:
                render_kpi_card(
                    title=f"{selected_period} Gross Total",
                    value=f"{breakdown.total_gross_period:,.2f} {curr}",
                    subtext=f"Net: {breakdown.total_net_period:,.2f} | Taxes: {breakdown.total_taxes_period:,.2f}"
                )
            with kpi_col2:
                render_kpi_card(
                    title=f"{selected_period} Peak Demand",
                    value=f"{breakdown.peak_demand_kw:,.1f} kW",
                    subtext=f"Overload: +{excess_p:,.1f} kW (Limit: {breakdown.contracted_capacity_kw:.0f} kW)",
                    status="alert" if excess_p > 0 else "ok"
                )
            with kpi_col3:
                render_kpi_card(
                    title=f"{selected_period} Energy",
                    value=f"{breakdown.total_consumption_kwh:,.0f} kWh",
                    subtext=f"Duration: {breakdown.duration_days:.0f} days"
                )
            with kpi_col4:
                render_kpi_card(
                    title="Effective Unit Rate",
                    value=f"{breakdown.effective_kwh_price:.4f} {curr}/kWh",
                    subtext="All-inclusive unit cost"
                )
        else:
            # Aggregate across full monthly payment schedule
            if breakdown.monthly_series:
                sched_gross = sum(m.total_gross for m in breakdown.monthly_series)
                sched_net = sum(m.total_net for m in breakdown.monthly_series)
                sched_taxes = sum(m.taxes_and_levies for m in breakdown.monthly_series)
                sched_kwh = sum(m.energy_kwh for m in breakdown.monthly_series)
                sched_days = sum(m.days_count for m in breakdown.monthly_series)
                n_months = len(breakdown.monthly_series)
                avg_monthly_gross = sched_gross / max(1, n_months)
                avg_monthly_net = sched_net / max(1, n_months)
                avg_monthly_taxes = sched_taxes / max(1, n_months)
                effective_price = (sched_gross / sched_kwh) if sched_kwh > 0 else breakdown.effective_kwh_price
            else:
                sched_gross = breakdown.total_gross_period
                sched_net = breakdown.total_net_period
                sched_taxes = breakdown.total_taxes_period
                sched_kwh = breakdown.total_consumption_kwh
                sched_days = int(round(breakdown.duration_days))
                n_months = 1
                avg_monthly_gross = breakdown.total_gross_monthly
                avg_monthly_net = breakdown.total_net_monthly
                avg_monthly_taxes = breakdown.total_taxes_monthly
                effective_price = breakdown.effective_kwh_price

            is_full_year = (n_months == 12 or sched_days >= 360 or is_synthetic_annual)

            with kpi_col1:
                total_title =  "Total Cost over Period"
                total_sub = (
                    f"Net: {sched_net:,.2f} | 365 days ({sched_kwh:,.0f} kWh)" if is_synthetic_annual else
                    f"Net: {sched_net:,.2f} | {sched_days} days ({sched_kwh:,.0f} kWh)"
                )
                render_kpi_card(
                    title=total_title,
                    value=f"{sched_gross:,.2f} {curr}",
                    subtext=total_sub
                )
            with kpi_col2:
                render_kpi_card(
                    title="Average Monthly Cost",
                    value=f"{avg_monthly_gross:,.2f} {curr}",
                    subtext=f"Net: {avg_monthly_net:,.2f} | Taxes: {avg_monthly_taxes:,.2f}"
                )
            with kpi_col3:
                render_kpi_card(
                    title="Effective Electricity Price",
                    value=f"{effective_price:.4f} {curr}/kWh",
                    subtext="All-inclusive average unit price"
                )
            with kpi_col4:
                render_kpi_card(
                    title="Fixed Cost Share",
                    value=f"{breakdown.fixed_cost_share_pct:.1f} %",
                    subtext=f"Capacity & Base: {breakdown.capacity_cost_monthly + breakdown.base_fee_monthly:,.2f} {curr}/mo"
                )

        # 6. Itemized Breakdown Table & Donut Chart
        t_col, c_col = st.columns([7, 5])

        with t_col:
            header_title = f"Itemized Cost Breakdown ({selected_period})" if is_single_month else (
                "Itemized Cost Breakdown (Annualized vs. Monthly)" if is_synthetic_annual else "Itemized Cost Breakdown (Normalized Month vs. Period)"
            )
            st.markdown(f"#### {header_title}")
            table_rows = []
            for item in breakdown.line_items:
                if is_synthetic_annual:
                    cost_val = item.cost_monthly * 12.0
                    col_name = f"Annual Cost ({curr})"
                else:
                    cost_val = item.cost_period
                    col_name = f"Period Cost ({curr})"

                table_rows.append({
                    "Category": item.category,
                    "Description": item.description,
                    "Quantity": f"{item.basis_quantity:,.2f} {item.unit}",
                    "Unit Rate": f"{item.unit_rate:.4f} {curr}",
                    col_name: f"{cost_val:,.2f}",
                    f"Monthly Cost ({curr})": f"{item.cost_monthly:,.2f}",
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

        # 7. Monthly Payment Schedule across Full Duration (Zahlungsreihe)
        st.divider()
        st.subheader("Monthly Payment over Period ")
        st.caption("Month-by-month billing series detailing individual cost components, taxes, and total invoice amounts over the complete analyzed period.")

        fig_series = create_monthly_payment_series_figure(
            breakdown=full_breakdown,
            highlight_month=selected_period if is_single_month else None
        )
        st.plotly_chart(fig_series, use_container_width=True)

        if full_breakdown.monthly_series:
            series_rows = []
            total_kwh_sum = 0.0
            total_net_sum = 0.0
            total_tax_sum = 0.0
            total_gross_sum = 0.0

            for m in full_breakdown.monthly_series:
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
                "Days": int(sum(m.days_count for m in full_breakdown.monthly_series)),
                f"Energy ({curr})": f"{sum(m.energy_cost_net for m in full_breakdown.monthly_series):,.2f}",
                f"Capacity ({curr})": f"{sum(m.capacity_cost_net for m in full_breakdown.monthly_series):,.2f}",
                f"Penalties ({curr})": f"{sum(m.penalty_cost_net for m in full_breakdown.monthly_series):,.2f}",
                f"Base Fee ({curr})": f"{sum(m.base_fee_net for m in full_breakdown.monthly_series):,.2f}",
                f"Taxes & Levies ({curr})": f"{total_tax_sum:,.2f}",
                f"Total Net ({curr})": f"{total_net_sum:,.2f}",
                f"Total Gross ({curr})": f"{total_gross_sum:,.2f}",
                f"Rate ({curr}/kWh)": f"{overall_avg_rate:.4f}"
            })

            df_series = pd.DataFrame(series_rows)
            st.dataframe(df_series, use_container_width=True, hide_index=True)

    st.session_state["active_contract"] = contract
    return contract


def render_tab2_contract_switch(key_prefix: str = "app_contract_switch") -> None:
    """
    Renders the dedicated Vertragswechsel (Contract Switch / Alternative Tariff) module.
    Compares alternative electricity contracts against the baseline load and Status Quo contract.
    """
    load_data, source_desc = _find_active_load_data_in_session()
    contract = st.session_state.get("active_contract")
    if contract is None:
        from current_model.core.project_io import export_project_from_session
        project = export_project_from_session()
        contract = project.base_scenario.base_contract

    render_contract_comparison_view(
        load_data=load_data,
        source_desc=source_desc,
        reference_contract=contract,
        key_prefix=key_prefix
    )


def render_tab2_contract(key_prefix: str = "tab2") -> Contract:
    """
    Backward-compatible wrapper rendering Tab 2 Contract assessment and comparison.
    """
    subtab_config, subtab_compare = st.tabs([
        ":material/tune: 2.1 Contract Configuration & Assessment",
        ":material/balance: 2.2 Multi-Contract Comparison & Tariff Benchmark"
    ])

    with subtab_config:
        contract = render_tab2_base_contract(key_prefix=f"{key_prefix}_base")

    with subtab_compare:
        render_tab2_contract_switch(key_prefix=f"{key_prefix}_switch")

    return contract
