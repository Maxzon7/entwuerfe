"""
========================================================================================
BESS Sandbox - Financial Viability & 15-Year TCO View
(ui_sandbox/BESS_sandbox/view_financial.py)
========================================================================================

Description:
------------
Comprehensive multi-year lifecycle financial viability assessment:
  - Avoided grid upgrade CAPEX & monthly transformer rental comparison.
  - BESS turnkey CAPEX, OPEX, conversion loss costs, and cell stack replacement.
  - 6 executive KPI cards: Net Initial Investment Delta, Annual Gross/Net Savings,
    Payback, 15Y NPV, IRR, and LCOS (€/kWh).
  - Itemized annual cost comparison table (Baseline vs. With-BESS vs. Delta).
  - High-contrast Plotly figures: 15Y Cumulative Trajectory, Break-Even Payback,
    Annual Cost Bar Comparison, and CAPEX Sizing Donut.
"""

import os
import sys
from typing import Dict, Any, Optional
import numpy as np
import pandas as pd
import streamlit as st

# Path bootstrapping
CURRENT_DIR = os.path.abspath(os.path.dirname(__file__))
UI_SANDBOX_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
CURRENT_MODEL_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
WORKSPACE_DIR = os.path.abspath(os.path.join(CURRENT_MODEL_DIR, ".."))
for p in [CURRENT_DIR, UI_SANDBOX_DIR, CURRENT_MODEL_DIR, WORKSPACE_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from current_model.models.bess import BESSConfig, BESSFinancialMetrics
    from current_model.core.bess_engine import BESSSimulationResult
    from current_model.ui.tab4_bess.financial_charts import (
        create_bess_cashflow_payback_figure,
        create_bess_annual_cost_comparison_figure,
        create_bess_cumulative_cost_trajectory_figure,
        create_bess_capex_donut_figure
    )
except ImportError:
    from models.bess import BESSConfig, BESSFinancialMetrics
    from core.bess_engine import BESSSimulationResult
    from ui.tab4_bess.financial_charts import (
        create_bess_cashflow_payback_figure,
        create_bess_annual_cost_comparison_figure,
        create_bess_cumulative_cost_trajectory_figure,
        create_bess_capex_donut_figure
    )

from ui_sandbox.BESS_sandbox import baseline_presets as presets
from ui_sandbox.BESS_sandbox import sandbox_bess_engine as engine


def render_financial_viability_tab(
    preset: presets.BaselinePreset,
    sim_result: BESSSimulationResult
) -> BESSFinancialMetrics:
    """
    Renders the multi-year financial viability assessment comparing Status Quo / Grid Upgrade vs. With-BESS.
    """
    st.subheader(":material/account_balance: Financial Viability & 15-Year Life-Cycle TCO")
    st.caption(
        "Compare the total cost of ownership (TCO) between paying for grid reinforcement & elevated capacity fees "
        "versus investing in a Battery Energy Storage System (BESS)."
    )

    bess_cfg = sim_result.config
    currency = bess_cfg.currency or "EUR"

    # --- Section 1: Financial Inputs & Cost Assumptions ---
    with st.expander(":material/tune: Financial & Grid Upgrade Cost Parameters", expanded=True):
        col_f1, col_f2, col_f3 = st.columns(3)

        with col_f1:
            st.markdown("**Avoided Grid Upgrade Costs**")
            avoided_upgrade_capex = st.number_input(
                f"Avoided Upgrade CAPEX ({currency})",
                min_value=0.0,
                max_value=1000000.0,
                value=float(st.session_state.get("bess_sb_avoided_upgrade_capex", preset.avoided_grid_upgrade_capex)),
                step=5000.0,
                help="One-time capital cost of physical grid expansion (e.g. transformer station, cabling, civil works).",
                key="bess_sb_avoided_upgrade_capex"
            )
            avoided_trans_rent = st.number_input(
                f"Avoided Transformer Rent ({currency}/mo)",
                min_value=0.0,
                max_value=20000.0,
                value=float(st.session_state.get("bess_sb_avoided_trans_rent", preset.avoided_monthly_transformer_rent)),
                step=50.0,
                help="Recurring monthly lease/rental fee charged by utility or grid operator for dedicated transformer equipment.",
                key="bess_sb_avoided_trans_rent"
            )

        with col_f2:
            st.markdown("**BESS Turnkey CAPEX & OPEX**")
            capex_per_kwh = st.number_input(
                f"BESS Cost per Unit ({currency}/kWh)",
                min_value=150.0,
                max_value=1200.0,
                value=float(st.session_state.get("bess_sb_capex_per_kwh", bess_cfg.cost_per_kwh or 420.0)),
                step=20.0,
                key="bess_sb_capex_per_kwh"
            )
            fixed_install_fee = st.number_input(
                f"Fixed Installation & Grid Fee ({currency})",
                min_value=0.0,
                max_value=100000.0,
                value=float(st.session_state.get("bess_sb_fixed_install", bess_cfg.fixed_installation_cost or 15000.0)),
                step=2500.0,
                key="bess_sb_fixed_install"
            )
            annual_om_pct = st.slider(
                "Annual Fixed O&M (% of BESS CAPEX)",
                min_value=0.5,
                max_value=5.0,
                value=float(st.session_state.get("bess_sb_om_pct", bess_cfg.annual_om_pct or 1.5)),
                step=0.1,
                key="bess_sb_om_pct"
            )

        with col_f3:
            st.markdown("**Life-Cycle & Macro Assumptions**")
            discount_rate_pct = st.slider(
                "WACC / Discount Rate (%)",
                min_value=1.0,
                max_value=12.0,
                value=5.0,
                step=0.5,
                key="bess_sb_discount_rate"
            )
            inflation_pct = st.slider(
                "Electricity Price Inflation (%/yr)",
                min_value=0.0,
                max_value=8.0,
                value=2.0,
                step=0.5,
                key="bess_sb_inflation"
            )
            cell_rep_cost_pct = st.slider(
                "Year 10 Cell Overhaul (% of Stack)",
                min_value=20.0,
                max_value=70.0,
                value=float(bess_cfg.cell_replacement_cost_pct or 45.0),
                step=5.0,
                key="bess_sb_cell_rep_cost"
            )

    # Recalculate BESS total capex
    bess_cfg.cost_per_kwh = float(capex_per_kwh)
    bess_cfg.fixed_installation_cost = float(fixed_install_fee)
    bess_cfg.annual_om_pct = float(annual_om_pct)
    bess_cfg.cell_replacement_cost_pct = float(cell_rep_cost_pct)

    # --- Section 2: Execute Financial Evaluation ---
    fin_metrics = engine.evaluate_sandbox_bess_economics(
        bess_config=bess_cfg,
        sim_result=sim_result,
        contract_baseline=preset.contract_baseline,
        contract_bess=preset.contract_bess,
        avoided_grid_upgrade_capex=float(avoided_upgrade_capex),
        avoided_monthly_transformer_rent=float(avoided_trans_rent),
        analysis_horizon_years=15,
        discount_rate_pct=float(discount_rate_pct),
        electricity_price_inflation_pct=float(inflation_pct),
        ambient_temperature_c=25.0,
        step_hours=0.25
    )

    # Net Initial Investment
    gross_bess_capex = float(bess_cfg.total_capex)
    net_initial_investment = max(0.0, gross_bess_capex - avoided_upgrade_capex)

    # --- Section 3: Executive KPI Cards ---
    st.markdown("#### :material/analytics: Executive Investment & Savings KPIs")

    kpi_col1, kpi_col2, kpi_col3 = st.columns(3)
    with kpi_col1:
        st.metric(
            label="Net Initial Investment Delta",
            value=f"{net_initial_investment:,.0f} {currency}",
            delta=f"BESS: {gross_bess_capex:,.0f} | Avoided: -{avoided_upgrade_capex:,.0f} {currency}",
            delta_color="off",
            help="Net initial capital outlay required for BESS after offsetting the avoided physical grid expansion CAPEX."
        )
    with kpi_col2:
        st.metric(
            label="Annual Gross Savings (Year 1)",
            value=f"{fin_metrics.annual_gross_savings:,.0f} {currency}/yr",
            delta=f"Demand: {fin_metrics.annual_demand_charge_savings:,.0f} | Rent: {avoided_trans_rent * 12:,.0f} {currency}",
            delta_color="normal",
            help="Total annual cost reduction across peak demand charges, contracted capacity, and avoided transformer rental."
        )
    with kpi_col3:
        st.metric(
            label="Annual OPEX & Efficiency Cost",
            value=f"{fin_metrics.annual_opex_year1:,.0f} {currency}/yr",
            delta=f"O&M: {fin_metrics.annual_fixed_om:,.0f} | Loss: {fin_metrics.annual_loss_cost:,.0f} {currency}",
            delta_color="inverse",
            help="Annual operational costs including maintenance and energy lost to battery conversion inefficiency."
        )

    kpi_col4, kpi_col5, kpi_col6 = st.columns(3)
    with kpi_col4:
        pb_str = f"{fin_metrics.simple_payback_years:.1f} Years" if fin_metrics.simple_payback_years is not None else ">15 Years"
        st.metric(
            label="Simple Payback Period",
            value=pb_str,
            delta="Amortized" if fin_metrics.simple_payback_years is not None and fin_metrics.simple_payback_years <= 10.0 else "Long Amortization",
            delta_color="normal" if fin_metrics.simple_payback_years is not None and fin_metrics.simple_payback_years <= 10.0 else "inverse",
            help="Number of operating years until cumulative net cash flows fully recover the initial net investment."
        )
    with kpi_col5:
        npv_val = fin_metrics.net_present_value
        st.metric(
            label="15-Year Life-Cycle NPV",
            value=f"{npv_val:,.0f} {currency}",
            delta=f"Discounted at {discount_rate_pct:.1f}% WACC",
            delta_color="normal" if npv_val >= 0 else "inverse",
            help="Net Present Value of all cumulative net cash flows over 15 years discounted at the chosen WACC."
        )
    with kpi_col6:
        irr_str = f"{fin_metrics.internal_rate_of_return_pct:.1f}%" if fin_metrics.internal_rate_of_return_pct is not None else "N/A"
        lcos_str = f"{fin_metrics.levelized_cost_of_storage_eur_kwh:.3f} {currency}/kWh"
        st.metric(
            label="IRR & Levelized Cost (LCOS)",
            value=f"IRR: {irr_str}",
            delta=f"LCOS: {lcos_str}",
            delta_color="off",
            help="Internal Rate of Return (IRR) and Levelized Cost of Storage (LCOS) per discharged kilowatt-hour."
        )

    st.markdown("---")

    # --- Section 4: Itemized Annual Cost Comparison Table ---
    st.markdown("#### :material/table_chart: Annual Operational Cost Comparison (Year 1)")

    # Build clear itemized comparison rows
    sq_demand = fin_metrics.annual_status_quo_demand_cost
    wb_demand = fin_metrics.annual_with_bess_demand_cost

    sq_energy = fin_metrics.annual_status_quo_energy_cost
    wb_energy = fin_metrics.annual_with_bess_energy_cost

    sq_penalty = fin_metrics.annual_status_quo_penalty_cost
    wb_penalty = fin_metrics.annual_with_bess_penalty_cost

    sq_rent = avoided_trans_rent * 12.0
    wb_rent = 0.0

    sq_om = 0.0
    wb_om = fin_metrics.annual_fixed_om

    sq_losses = 0.0
    wb_losses = fin_metrics.annual_loss_cost

    sq_total = fin_metrics.annual_status_quo_total_bill + sq_rent
    wb_total = fin_metrics.annual_with_bess_total_bill + wb_om + wb_losses

    comparison_data = [
        {
            "Cost Component": "Contracted Capacity (GTV) & Peak Demand (kW-max)",
            "Baseline / Upgrade": f"{sq_demand:,.0f} {currency}",
            "With BESS System": f"{wb_demand:,.0f} {currency}",
            "Annual Delta (Savings)": f"-{sq_demand - wb_demand:,.0f} {currency}"
        },
        {
            "Cost Component": "Grid Overload Penalties",
            "Baseline / Upgrade": f"{sq_penalty:,.0f} {currency}",
            "With BESS System": f"{wb_penalty:,.0f} {currency}",
            "Annual Delta (Savings)": f"-{sq_penalty - wb_penalty:,.0f} {currency}"
        },
        {
            "Cost Component": "Active Energy Import Commodity Cost",
            "Baseline / Upgrade": f"{sq_energy:,.0f} {currency}",
            "With BESS System": f"{wb_energy:,.0f} {currency}",
            "Annual Delta (Savings)": f"-{sq_energy - wb_energy:,.0f} {currency}"
        },
        {
            "Cost Component": "Dedicated Substation / Transformer Rental",
            "Baseline / Upgrade": f"{sq_rent:,.0f} {currency}",
            "With BESS System": f"{wb_rent:,.0f} {currency}",
            "Annual Delta (Savings)": f"-{sq_rent - wb_rent:,.0f} {currency}"
        },
        {
            "Cost Component": "BESS Annual Maintenance (O&M)",
            "Baseline / Upgrade": f"{sq_om:,.0f} {currency}",
            "With BESS System": f"{wb_om:,.0f} {currency}",
            "Annual Delta (Savings)": f"+{wb_om:,.0f} {currency}"
        },
        {
            "Cost Component": "Battery Round-Trip Efficiency Conversion Losses",
            "Baseline / Upgrade": f"{sq_losses:,.0f} {currency}",
            "With BESS System": f"{wb_losses:,.0f} {currency}",
            "Annual Delta (Savings)": f"+{wb_losses:,.0f} {currency}"
        },
        {
            "Cost Component": "**TOTAL ANNUAL OPERATING EXPENDITURE**",
            "Baseline / Upgrade": f"**{sq_total:,.0f} {currency}**",
            "With BESS System": f"**{wb_total:,.0f} {currency}**",
            "Annual Delta (Savings)": f"**-{sq_total - wb_total:,.0f} {currency}**"
        }
    ]

    st.table(pd.DataFrame(comparison_data))

    st.markdown("---")

    # --- Section 5: Plotly Financial Visualizations ---
    st.markdown("#### :material/insights: Financial Trajectory Visualizations")

    tab_traj, tab_cf, tab_bar, tab_donut = st.tabs([
        ":material/trending_up: 15-Year Life-Cycle Trajectory",
        ":material/payments: Cumulative Cash Flow & Break-Even",
        ":material/bar_chart: Annual Cost Breakdown Bar",
        ":material/pie_chart: Turn-Key CAPEX Sizing Donut"
    ])

    with tab_traj:
        st.caption("15-year cumulative expenditure comparing status quo utility bills against turnkey BESS investment.")
        fig_traj = create_bess_cumulative_cost_trajectory_figure(fin_metrics, currency=currency)
        st.plotly_chart(fig_traj, use_container_width=True)

    with tab_cf:
        st.caption("Cumulative cash flow trajectory showing the exact amortization break-even year.")
        fig_cf = create_bess_cashflow_payback_figure(fin_metrics, currency=currency)
        st.plotly_chart(fig_cf, use_container_width=True)

    with tab_bar:
        st.caption("Stacked annual electricity and operating expenditure breakdown in Year 1.")
        fig_bar = create_bess_annual_cost_comparison_figure(fin_metrics, currency=currency)
        st.plotly_chart(fig_bar, use_container_width=True)

    with tab_donut:
        st.caption("Turn-key capital investment breakdown by hardware subsystem.")
        # Component breakdown
        cells_capex = gross_bess_capex * 0.52
        inverter_capex = gross_bess_capex * 0.18
        bos_capex = gross_bess_capex * 0.15
        install_capex = gross_bess_capex * 0.15
        capex_dict = {
            "capex_cells_modules": cells_capex,
            "capex_inverter_pcs": inverter_capex,
            "capex_bos_enclosure": bos_capex,
            "capex_installation_grid": install_capex,
            "total_capex": gross_bess_capex,
            "capex_per_kwh": bess_cfg.cost_per_kwh
        }
        fig_donut = create_bess_capex_donut_figure(capex_dict, currency=currency)
        st.plotly_chart(fig_donut, use_container_width=True)

    # --- Section 6: 15-Year Cash Flow Projection Table ---
    with st.expander(":material/list_alt: Detailed 15-Year Cash Flow & Capacity Degradation Table", expanded=False):
        if fin_metrics.cash_flow_table:
            cf_df = pd.DataFrame(fin_metrics.cash_flow_table)
            st.dataframe(
                cf_df.style.format({
                    "capacity_retention_pct": "{:.1f}%",
                    "status_quo_cost": "{:,.0f} " + currency,
                    "with_bess_cost": "{:,.0f} " + currency,
                    "net_cash_flow": "{:,.0f} " + currency,
                    "cumulative_cash_flow": "{:,.0f} " + currency,
                    "discounted_cash_flow": "{:,.0f} " + currency
                }),
                use_container_width=True
            )

    return fin_metrics
