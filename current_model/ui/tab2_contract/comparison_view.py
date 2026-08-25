"""
========================================================================================
Multi-Contract Comparison View (current_model/ui/tab2_contract/comparison_view.py)
========================================================================================

Description:
------------
Orchestrates the Multi-Contract Tariff Benchmark & Comparison sub-tab (Tab 2.2):
  - Ingests multiple contracts (uploaded .drac/.json, presets, and active configured contract).
  - Calculates side-by-side financial billing against the active consumption load dataset.
  - Automatically designates the active contract in Tab 2.1 as the reference baseline.
  - Computes cost savings / surcharges, effective €/kWh rates, and ranking leaderboard.
  - Renders interactive comparison charts (stacked bar, monthly timeseries, and rate benchmark).
  - Displays a detailed contract parameter specification matrix.
"""

from typing import List, Dict, Any, Tuple, Optional
import streamlit as st
import pandas as pd
import numpy as np

from current_model.models.contract import Contract, get_contract_presets
from current_model.models.financial import FinancialCostBreakdown
from current_model.core.financial_engine import compute_financial_bill
from current_model.ui.common.cards import render_kpi_card
from current_model.ui.tab2_contract.comparison_charts import (
    create_comparison_stacked_bar_figure,
    create_monthly_comparison_series_figure,
    create_effective_rate_bar_figure
)


def _gather_available_contracts(reference_contract: Contract, key_prefix: str) -> Dict[str, Contract]:
    """
    Collects all available contracts from session state uploads, presets, and the reference contract.
    """
    all_contracts: Dict[str, Contract] = {}

    # 1. Reference contract from Tab 2.1 (Always included as baseline)
    ref_name = getattr(reference_contract, "name", "Reference Contract (Tab 2.1)") or "Reference Contract"
    ref_key = f"📌 {ref_name} [Baseline 2.1]"
    all_contracts[ref_key] = reference_contract

    # 2. Check for contracts uploaded in Tab 2 uploader
    # Check both with key_prefix and standard prefixes
    for k in [f"{key_prefix}_loaded_contracts_dict", "tab2_loaded_contracts_dict", "app_tab2_loaded_contracts_dict"]:
        if k in st.session_state and isinstance(st.session_state[k], dict):
            for label, c in st.session_state[k].items():
                if isinstance(c, Contract):
                    all_contracts[label] = c

    # 3. Presets for additional comparison options
    presets = get_contract_presets()
    for p_name, p_contract in presets.items():
        preset_key = f"📋 Preset: {p_name}"
        if preset_key not in all_contracts and p_name != ref_name:
            all_contracts[preset_key] = p_contract

    return all_contracts


def render_contract_comparison_view(
    load_data: Any,
    source_desc: str,
    reference_contract: Contract,
    key_prefix: str = "tab2_compare"
) -> None:
    """
    Renders Sub-tab 2.2: Multi-Contract Comparison & Tariff Benchmark.
    """
    st.subheader("⚖️ Multi-Contract Tariff Benchmark & Cost Comparison")
    st.caption("Simultaneously evaluate multiple electricity contracts against your active consumption load profile to find the most cost-effective tariff.")

    if load_data is None:
        st.info("💡 Please configure or import a consumption profile in **Tab 1 (Consumption)** first to run the multi-contract benchmark.")
        return

    # Gather available contracts
    available_contracts = _gather_available_contracts(reference_contract, key_prefix=key_prefix)

    # 1. Contract Selection Toolbar
    st.markdown("##### 1. Select Contracts for Comparison")
    col_sel, col_info = st.columns([3, 2])

    with col_sel:
        all_options = list(available_contracts.keys())
        ref_key = all_options[0]  # Reference contract is first

        # Default: select all uploaded contracts + reference contract (max 6)
        default_selected = [k for k in all_options if not k.startswith("📋 Preset:")][:6]
        if not default_selected:
            default_selected = all_options[:3]

        selected_contract_keys = st.multiselect(
            "Contracts to include in comparison:",
            options=all_options,
            default=default_selected,
            key=f"{key_prefix}_multiselect_contracts",
            help="Select 2 or more contracts to directly compare side-by-side."
        )

    with col_info:
        st.markdown(
            f"""
            <div style="background: rgba(30, 41, 59, 0.6); border: 1px solid rgba(51, 65, 85, 0.7); border-radius: 8px; padding: 12px 16px; margin-top: 4px;">
                <div style="font-size: 0.8rem; color: #94A3B8; text-transform: uppercase; letter-spacing: 0.05em;">Benchmark Baseline</div>
                <div style="font-size: 1.05rem; font-weight: 600; color: #38BDF8; margin-top: 2px;">📌 {reference_contract.name}</div>
                <div style="font-size: 0.8rem; color: #64748B; margin-top: 2px;">Active Load: {source_desc}</div>
            </div>
            """,
            unsafe_allow_html=True
        )

    if len(selected_contract_keys) < 1:
        st.warning("Please select at least one contract to calculate costs.")
        return

    # 2. Perform simultaneous financial computation for each selected contract
    comparison_results: List[Dict[str, Any]] = []

    # First calculate reference contract breakdown for savings delta
    ref_breakdown: FinancialCostBreakdown = compute_financial_bill(load_data=load_data, contract=reference_contract)
    ref_gross = ref_breakdown.total_gross_period
    ref_currency = getattr(reference_contract, "currency", "EUR")

    for key in selected_contract_keys:
        contract_obj = available_contracts[key]
        breakdown: FinancialCostBreakdown = compute_financial_bill(load_data=load_data, contract=contract_obj)

        total_gross = breakdown.total_gross_period
        total_net = breakdown.total_net_period
        total_kwh = max(1.0, breakdown.total_consumption_kwh)
        effective_rate = breakdown.effective_kwh_price if breakdown.effective_kwh_price > 0 else (total_gross / total_kwh)

        # Savings vs reference
        diff_gross = total_gross - ref_gross
        diff_pct = ((total_gross - ref_gross) / ref_gross * 100.0) if ref_gross > 0 else 0.0

        is_reference = (key == ref_key or contract_obj == reference_contract)

        comparison_results.append({
            "key": key,
            "display_name": contract_obj.name or key,
            "contract": contract_obj,
            "breakdown": breakdown,
            "currency": getattr(contract_obj, "currency", ref_currency),
            "total_gross": total_gross,
            "total_net": total_net,
            "energy_cost": breakdown.energy_cost_period,
            "capacity_cost": breakdown.capacity_cost_period,
            "demand_cost": 0.0,
            "base_fee": breakdown.base_fee_period,
            "penalty_cost": breakdown.penalty_cost_period,
            "reactive_cost": breakdown.reactive_cost_period,
            "taxes_cost": breakdown.total_taxes_period,
            "total_kwh": total_kwh,
            "effective_rate_kwh": effective_rate,
            "diff_gross": diff_gross,
            "diff_pct": diff_pct,
            "is_reference": is_reference,
            "monthly_series": breakdown.monthly_series,
            "is_winner": False
        })

    # Sort by total gross ascending to determine winner
    comparison_results.sort(key=lambda x: x["total_gross"])
    if comparison_results:
        comparison_results[0]["is_winner"] = True

    winner = comparison_results[0]
    cheapest_name = winner["display_name"]
    cheapest_gross = winner["total_gross"]
    max_savings_gross = ref_gross - cheapest_gross
    max_savings_pct = (max_savings_gross / ref_gross * 100.0) if ref_gross > 0 else 0.0

    st.divider()

    # 3. Winner & KPI Summary Cards
    st.markdown("##### 2. Financial Summary & Ranking")
    kpi_col1, kpi_col2, kpi_col3, kpi_col4 = st.columns(4)

    with kpi_col1:
        win_badge = "🏆 Most Cost-Effective"
        win_sub = f"{cheapest_name} (Savings: -{max_savings_gross:,.2f} {ref_currency} / -{max_savings_pct:.1f}%)" if max_savings_gross > 0.01 else f"{cheapest_name} (Matches Baseline)"
        render_kpi_card(
            title=win_badge,
            value=f"{cheapest_gross:,.2f} {winner['currency']}",
            subtext=win_sub,
            status="ok"
        )

    with kpi_col2:
        render_kpi_card(
            title="📌 Reference Baseline (2.1)",
            value=f"{ref_gross:,.2f} {ref_currency}",
            subtext=f"{reference_contract.name} (Eff. Rate: {ref_breakdown.effective_kwh_price:.4f} {ref_currency}/kWh)",
            status="default"
        )

    with kpi_col3:
        cheapest_eff_rate = winner["effective_rate_kwh"]
        render_kpi_card(
            title="💡 Lowest Effective Rate",
            value=f"{cheapest_eff_rate:.4f} {winner['currency']}/kWh",
            subtext=f"For {winner['total_kwh']:,.0f} active kWh",
            status="default"
        )

    with kpi_col4:
        most_expensive = comparison_results[-1]
        cost_spread = most_expensive["total_gross"] - cheapest_gross
        render_kpi_card(
            title="📊 Tariff Cost Spread",
            value=f"{cost_spread:,.2f} {ref_currency}",
            subtext=f"Spread between Min & Max Tariff",
            status="default"
        )

    st.write("")

    # 4. Detailed Comparison Table
    st.markdown("##### 3. Side-by-Side Comparison Table")

    table_rows = []
    for rank, res in enumerate(comparison_results, start=1):
        is_win = res["is_winner"]
        is_ref = res["is_reference"]

        status_tag = "🏆 Cheapest" if is_win else ("📌 Baseline" if is_ref else f"#{rank}")

        diff_str = "0.00 (Baseline)"
        if not is_ref:
            sign = "+" if res["diff_gross"] > 0 else "-"
            diff_str = f"{sign}{abs(res['diff_gross']):,.2f} {res['currency']} ({sign}{abs(res['diff_pct']):.1f}%)"

        table_rows.append({
            "Rank / Status": status_tag,
            "Contract Name": res["display_name"],
            "Currency": res["currency"],
            f"Gross Total ({ref_currency})": f"{res['total_gross']:,.2f}",
            f"Net Total ({ref_currency})": f"{res['total_net']:,.2f}",
            "Eff. Rate (/kWh)": f"{res['effective_rate_kwh']:.4f}",
            "Diff vs. Baseline": diff_str,
            "Energy Charge": f"{res['energy_cost']:,.2f}",
            "Capacity Charge": f"{res['capacity_cost']:,.2f}",
            "Peak Penalty": f"{res['penalty_cost']:,.2f}",
            "Fixed Base Fee": f"{res['base_fee']:,.2f}",
            "Taxes & Levies": f"{res['taxes_cost']:,.2f}",
        })

    df_comparison = pd.DataFrame(table_rows)
    st.dataframe(df_comparison, use_container_width=True, hide_index=True)

    st.write("")

    # 5. Interactive Visual Benchmark Charts
    st.markdown("##### 4. Visual Benchmark & Analysis")

    chart_tab1, chart_tab2, chart_tab3 = st.tabs([
        "📊 Cost Components Breakdown",
        "📅 12-Month Payment Trajectory",
        "💡 Effective Rate Benchmark (/kWh)"
    ])

    with chart_tab1:
        fig_stacked = create_comparison_stacked_bar_figure(comparison_results, currency=ref_currency)
        st.plotly_chart(fig_stacked, use_container_width=True)

    with chart_tab2:
        fig_monthly = create_monthly_comparison_series_figure(comparison_results, currency=ref_currency)
        st.plotly_chart(fig_monthly, use_container_width=True)

    with chart_tab3:
        fig_eff = create_effective_rate_bar_figure(comparison_results, currency=ref_currency)
        st.plotly_chart(fig_eff, use_container_width=True)

    # 6. Contract Parameter Specification Matrix
    with st.expander("🔍 **Contract Technical Parameters & Tariff Windows Matrix**", expanded=False):
        param_rows = []
        for res in comparison_results:
            c: Contract = res["contract"]
            tou_summary = " / ".join([f"{r.get('name', 'Rate')}: {r.get('rate', 0):.4f} ({r.get('start_time', '')}-{r.get('end_time', '')})" for r in c.tou_rates]) if c.tou_rates else f"{c.default_energy_rate:.4f}"
            tax_summary = " / ".join([f"{t.get('name', 'Tax')}: {t.get('value', 0)}{'%' if t.get('type')=='percentage' else ' /kWh'}" for t in c.taxes_and_fees]) if c.taxes_and_fees else "None"

            param_rows.append({
                "Contract Name": c.name,
                "Currency": c.currency,
                "Contracted Capacity (kW)": f"{c.contracted_capacity_kw:,.1f}",
                "Capacity Tariff (/kW/mo)": f"{c.monthly_capacity_tariff:.4f}",
                "Demand Tariff (/kW/mo)": f"{getattr(c, 'demand_capacity_tariff', 0.0):.4f}",
                "Peak Penalty Rate (/kW)": f"{c.peak_penalty_rate:.4f}",
                "Base Monthly Fee": f"{c.base_monthly_fee:,.2f}",
                "Weekend Off-Peak": "Yes" if c.weekend_is_off_peak else "No",
                "Time-of-Use (TOU) Windows": tou_summary,
                "Taxes & Fees": tax_summary
            })

        df_params = pd.DataFrame(param_rows)
        st.dataframe(df_params, use_container_width=True, hide_index=True)
