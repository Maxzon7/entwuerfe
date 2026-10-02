"""
========================================================================================
Monthly Baseline Financial KPI Cards & Export Toolbar
(current_model/ui_sandbox/monthly_financial_view.py)
========================================================================================

Description:
------------
Renders:
1. Four master financial KPI cards (Total Annual Cost, Energy Volume Cost, Capacity & Grid Fees, Blended Price).
2. Export toolbar with one-click CSV and full JSON baseline configuration download.
========================================================================================
"""

import json
from dataclasses import asdict
from typing import List
import pandas as pd
import streamlit as st

# Safe imports
try:
    from current_model.ui_sandbox.monthly_presets import TOUTierConfig
    from current_model.ui_sandbox.monthly_calc import AnnualBillingSummary, build_baseline_export_payload
except ImportError:
    from monthly_presets import TOUTierConfig
    from monthly_calc import AnnualBillingSummary, build_baseline_export_payload


def render_financial_kpi_cards(
    summary: AnnualBillingSummary,
    selected_cur: str = "EUR"
):
    """Renders the 4 top financial summary metrics cards and the 3-Party Market Attribution breakdown."""
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    with kpi1:
        st.metric(
            label="Total Annual Electricity Cost",
            value=f"€ {summary.cost_total_annual_eur:,.2f}",
            delta=f"${summary.cost_total_annual_local:,.2f} {selected_cur}" if selected_cur != "EUR" else None
        )
    with kpi2:
        st.metric(
            label="Annual Energy Volume Cost",
            value=f"€ {summary.cost_energy_total_eur:,.2f}",
            delta=f"{summary.total_kwh:,.0f} kWh Total"
        )
    with kpi3:
        demand_info = []
        if summary.cost_measured_demand_annual_eur > 0:
            demand_info.append(f"Demand: € {summary.cost_measured_demand_annual_eur:,.2f}")
        if summary.cost_penalty_annual_eur > 0:
            demand_info.append(f"Penalties: € {summary.cost_penalty_annual_eur:,.2f}")
        delta_str = " | ".join(demand_info) if demand_info else ("No Penalties" if summary.cost_penalty_annual_eur == 0 else None)
        st.metric(
            label="Annual Capacity & Grid Fees",
            value=f"€ {summary.cost_fixed_annual_eur:,.2f}",
            delta=delta_str
        )
    with kpi4:
        st.metric(
            label="Effective Blended Price",
            value=f"€ {summary.blended_rate_annual_eur:.4f} / kWh",
            delta=f"${summary.blended_rate_annual_local:.4f} {selected_cur}/kWh" if selected_cur != "EUR" else None
        )

    # 3-Party Market Entities Financial Attribution Banner
    tot_cost = max(summary.cost_total_annual_eur, 1e-9)
    dso_share = (summary.cost_dso_annual_eur / tot_cost) * 100.0
    supp_share = (summary.cost_supplier_annual_eur / tot_cost) * 100.0
    meter_share = (summary.cost_metering_annual_eur / tot_cost) * 100.0

    with st.container(border=True):
        st.markdown("##### :material/payments: Unbundled 3-Party Cost Attribution")
        c_dso, c_supp, c_meter = st.columns(3)
        with c_dso:
            st.markdown(f"**:material/account_tree: Grid Operator (DSO):**  \n`{summary.dso_name}`")
            st.markdown(f"**€ {summary.cost_dso_annual_eur:,.2f}** ({dso_share:.1f}%)")
            st.caption("Contracted kW, peak demand, base standing & network fees")
        with c_supp:
            st.markdown(f"**:material/storefront: Energy Supplier:**  \n`{summary.supplier_name}`")
            st.markdown(f"**€ {summary.cost_supplier_annual_eur:,.2f}** ({supp_share:.1f}%)")
            st.caption("Time-of-Use active energy commodity volume (kWh)")
        with c_meter:
            st.markdown(f"**:material/speed: Meter Company (Meetbedrijf):**  \n`{summary.meter_company_name}`")
            st.markdown(f"**€ {summary.cost_metering_annual_eur:,.2f}** ({meter_share:.1f}%)")
            st.caption("Certified meter provisioning, interval data & telemetry")


def render_export_toolbar(
    summary: AnnualBillingSummary,
    active_tiers: List[TOUTierConfig],
    consumption_df: pd.DataFrame,
    tariff_df: pd.DataFrame,
    preset_name: str,
    selected_cur: str,
    fx_rate: float
):
    """Renders the CSV and JSON baseline export download buttons."""
    col_exp1, col_exp2 = st.columns(2)
    with col_exp1:
        export_df = pd.DataFrame([asdict(r) for r in summary.monthly_results])
        csv_data = export_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label=":material/file_download: Export Monthly Baseline (CSV)",
            data=csv_data,
            file_name="monthly_baseline_summary.csv",
            mime="text/csv",
            use_container_width=True
        )
    with col_exp2:
        export_payload = build_baseline_export_payload(
            preset_name=preset_name,
            currency=selected_cur,
            fx_rate=fx_rate,
            summary=summary,
            active_tiers=active_tiers,
            consumption_df=consumption_df,
            tariff_df=tariff_df
        )
        json_str = json.dumps(export_payload, indent=2)
        st.download_button(
            label=":material/data_object: Export Complete Baseline Model (JSON)",
            data=json_str.encode("utf-8"),
            file_name="monthly_baseline_config.json",
            mime="application/json",
            use_container_width=True
        )
