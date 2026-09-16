"""
========================================================================================
Sub-Tab 4.2: BESS Financial & Commercial Viability View (ui/tab4_bess/financial_view.py)
========================================================================================

Description:
------------
Renders the complete economic assessment and commercial viability for the BESS project:
  - Financial Parameter Configuration Form (CAPEX €/kWh, Fixed Fees, O&M %, WACC %, Inflation %).
  - Automated link with Tab 2 Electricity Contract (Peak demand tariffs, overload penalties, TOU rates).
  - 6 Key Performance Metric Cards (CAPEX, Net Annual Savings, Payback, NPV, LCOS, IRR).
  - 5 High-Contrast Plotly Financial Visualizations.
  - Itemized 15-Year Life-Cycle Cash Flow Table.
  - Detailed Electricity Billing Comparison Table (Status Quo vs. With BESS).
"""

from typing import Optional, Dict, Any, Tuple
import streamlit as st
import pandas as pd
import numpy as np

from current_model.models.bess import BESSConfig, BESSFinancialMetrics, get_bess_presets
from current_model.models.scenario import ProjectContainer, SubScenario
from current_model.models.contract import Contract
from current_model.core.project_io import export_project_from_session, sync_active_scenario_into_session
from current_model.core.bess_engine import simulate_bess_dispatch, BESSSimulationResult
from current_model.core.bess_financial_engine import (
    compute_bess_financial_metrics,
    compute_bess_capex_breakdown,
    compute_bess_sensitivity_matrix
)
from current_model.core.synthetic_engine import aggregate_synthetic_year
from current_model.models.presets import get_industry_preset_consumers
from current_model.ui.common.cards import render_kpi_card
from current_model.ui.common.session_utils import (
    find_active_load_data_in_session,
    find_active_contract_in_session,
    get_load_profile_summary
)
from current_model.ui.tab4_bess.financial_charts import (
    create_bess_cashflow_payback_figure,
    create_bess_annual_cost_comparison_figure,
    create_bess_cumulative_cost_trajectory_figure,
    create_bess_capex_donut_figure,
    create_bess_sensitivity_figure
)


def render_tab4_2_financial(key_prefix: str = "tab4_fin") -> None:
    """
    Renders Sub-Tab 4.2: BESS Financial & Commercial Viability Assessment.
    """
    st.subheader("BESS Financial & Commercial Viability Assessment")
    st.caption(
        "Evaluates the investment return, peak shaving capacity charge savings, "
        "amortization payback period, Net Present Value (NPV), and Levelized Cost of Storage (LCOS)."
    )

    project: ProjectContainer = export_project_from_session()
    active_sub = project.get_active_scenario()

    # --------------------------------------------------------------------------
    # 0. Status Quo Guard
    # --------------------------------------------------------------------------
    if active_sub is None:
        st.info(
            "### :material/anchor: Status Quo (Base Benchmark) Active\n\n"
            "The **Status Quo (Base Scenario)** represents your pure utility grid baseline without BESS investment.\n\n"
            "To evaluate battery CAPEX, peak shaving savings, and amortization, switch to an active Sub-Scenario branch."
        )
        if project.sub_scenarios:
            first_sub = project.sub_scenarios[0]
            if st.button(f"Switch to '{first_sub.name}'", icon=":material/arrow_forward:", type="primary", key=f"{key_prefix}_switch_sub_btn"):
                project.active_sub_scenario_id = first_sub.id
                st.session_state["project_container"] = project
                sync_active_scenario_into_session(project, auto_execute=False)
                st.rerun()
        return

    # --------------------------------------------------------------------------
    # 1. Active Load & Contract Discovery
    # --------------------------------------------------------------------------
    df_load, load_desc, p_col = find_active_load_data_in_session()
    if df_load is None or df_load.empty:
        st.warning("No active consumption profile found from Tab 1. Please import or synthesize a load curve first.")
        return

    load_summary = get_load_profile_summary(df_load, power_col=p_col)
    active_contract = find_active_contract_in_session()
    contract_kw = float(getattr(active_contract, "contracted_capacity_kw", 0.0)) if active_contract else 0.0

    # Retrieve or initialize BESS config
    bess_cfg: Optional[BESSConfig] = active_sub.bess_config or st.session_state.get(f"{key_prefix}_bess_config")
    if bess_cfg is None:
        bess_cfg = BESSConfig(
            capacity_kwh=200.0,
            max_charge_power_kw=100.0,
            max_discharge_power_kw=100.0,
            peak_shaving_threshold_kw=contract_kw if contract_kw > 0 else round(load_summary["peak_kw"] * 0.8, 0)
        )

    grid_limit_val = float(st.session_state.get(f"app_tab4_bess_tech_grid_limit_kw", contract_kw if contract_kw > 0 else round(load_summary["peak_kw"] * 0.8, 0)))
    grid_limit_val = max(10.0, grid_limit_val)

    # --------------------------------------------------------------------------
    # 2. Financial Assumptions Configuration Form
    # --------------------------------------------------------------------------
    with st.expander("Investment & Economic Assumptions Configuration", icon=":material/tune:", expanded=True):
        with st.form(key=f"{key_prefix}_fin_form"):
            col_f1, col_f2, col_f3, col_f4 = st.columns(4)
            with col_f1:
                cost_per_kwh = st.number_input(
                    "Specific Battery Cost (€/kWh):",
                    min_value=50.0,
                    max_value=3000.0,
                    value=float(bess_cfg.cost_per_kwh),
                    step=25.0,
                    help="Turn-key hardware cost per usable/nominal kWh of battery storage."
                )
            with col_f2:
                fixed_fee = st.number_input(
                    "Fixed BOS & Grid Fee (€):",
                    min_value=0.0,
                    max_value=200000.0,
                    value=float(bess_cfg.fixed_installation_cost),
                    step=500.0,
                    help="Fixed project fee including engineering, switchgear, and grid certification."
                )
            with col_f3:
                annual_om_pct = st.number_input(
                    "Annual O&M (% of CAPEX):",
                    min_value=0.0,
                    max_value=10.0,
                    value=float(bess_cfg.annual_om_pct),
                    step=0.1,
                    help="Annual operations, maintenance, telemetry, and insurance expenses."
                )
            with col_f4:
                horizon_years = st.selectbox(
                    "Analysis Horizon:",
                    options=[10, 15, 20, 25],
                    index=1,
                    help="Life-cycle evaluation period (Years)."
                )

            col_d1, col_d2, col_d3, col_d4 = st.columns(4)
            with col_d1:
                wacc_rate = st.number_input(
                    "Discount Rate / WACC (%):",
                    min_value=0.0,
                    max_value=20.0,
                    value=5.0,
                    step=0.5,
                    help="Weighted Average Cost of Capital used for discounting future cash flows (NPV)."
                )
            with col_d2:
                price_escalation = st.number_input(
                    "Electricity Price Escalation (%/yr):",
                    min_value=0.0,
                    max_value=15.0,
                    value=2.0,
                    step=0.5,
                    help="Expected annual increase in utility electricity tariffs and capacity charges."
                )
            with col_d3:
                cell_rep_yr = st.number_input(
                    "Cell Replacement Year:",
                    min_value=5,
                    max_value=20,
                    value=int(bess_cfg.cell_replacement_year),
                    step=1,
                    help="Year in which battery cell modules are refreshed."
                )
            with col_d4:
                cell_rep_cost_pct = st.number_input(
                    "Cell Replacement Cost (%):",
                    min_value=10.0,
                    max_value=100.0,
                    value=float(bess_cfg.cell_replacement_cost_pct),
                    step=5.0,
                    help="Module replacement cost as a % of initial battery module investment."
                )

            submit_fin = st.form_submit_button(
                "Update Financial Parameters & Recalculate ROI",
                icon=":material/calculate:",
                type="primary",
                use_container_width=True
            )

        if submit_fin:
            bess_cfg.cost_per_kwh = cost_per_kwh
            bess_cfg.fixed_installation_cost = fixed_fee
            bess_cfg.annual_om_pct = annual_om_pct
            bess_cfg.cell_replacement_year = cell_rep_yr
            bess_cfg.cell_replacement_cost_pct = cell_rep_cost_pct
            active_sub.bess_config = bess_cfg
            st.session_state["project_container"] = project
            sync_active_scenario_into_session(project, auto_execute=False)

    # --------------------------------------------------------------------------
    # 3. Execute Simulation & Financial Calculations
    # --------------------------------------------------------------------------
    # Perform dispatch simulation to obtain 15-minute load vs residual profile
    sim_res: BESSSimulationResult = simulate_bess_dispatch(
        bess_config=bess_cfg,
        load_df=df_load,
        grid_limit_kw=grid_limit_val,
        step_hours=load_summary.get("hours_per_step", 0.25),
        power_col=p_col
    )

    fin_metrics: BESSFinancialMetrics = compute_bess_financial_metrics(
        bess_config=bess_cfg,
        df_timeseries=sim_res.df_timeseries,
        contract=active_contract,
        grid_limit_kw=grid_limit_val,
        analysis_horizon_years=horizon_years,
        discount_rate_pct=wacc_rate,
        electricity_price_inflation_pct=price_escalation,
        step_hours=load_summary.get("hours_per_step", 0.25)
    )

    capex_breakdown = compute_bess_capex_breakdown(bess_cfg)
    currency = active_contract.currency if active_contract and active_contract.currency else "EUR"

    # --------------------------------------------------------------------------
    # 4. High-Impact Commercial KPI Cards
    # --------------------------------------------------------------------------
    st.markdown("##### Key Commercial & Amortization Metrics")

    k1, k2, k3, k4, k5, k6 = st.columns(6)
    with k1:
        render_kpi_card(
            "Turn-Key CAPEX",
            f"{fin_metrics.total_capex:,.0f} {currency}",
            f"{fin_metrics.capex_per_kwh:,.1f} {currency}/kWh ({bess_cfg.capacity_kwh:,.0f} kWh)",
            status="default"
        )
    with k2:
        render_kpi_card(
            "Net Annual Savings",
            f"{fin_metrics.annual_net_savings_year1:,.0f} {currency}/yr",
            f"Gross: {fin_metrics.annual_gross_savings:,.0f} {currency} - OPEX: {fin_metrics.annual_opex_year1:,.0f} {currency}",
            status="ok" if fin_metrics.annual_net_savings_year1 > 0 else "alert"
        )
    with k3:
        pb_str = f"{fin_metrics.simple_payback_years:.1f} Years" if fin_metrics.simple_payback_years else "> 20 Years"
        render_kpi_card(
            "Simple Payback Period",
            pb_str,
            f"Discounted: {fin_metrics.discounted_payback_years:.1f} Y" if fin_metrics.discounted_payback_years else "Discounted: > 20 Y",
            status="ok" if fin_metrics.simple_payback_years and fin_metrics.simple_payback_years <= 8.0 else "default"
        )
    with k4:
        npv_val = fin_metrics.net_present_value
        render_kpi_card(
            f"{horizon_years}Y Net Present Value",
            f"{npv_val:,.0f} {currency}",
            f"WACC: {wacc_rate:.1f}% | Escalation: {price_escalation:.1f}%",
            status="ok" if npv_val > 0 else "alert"
        )
    with k5:
        irr_str = f"{fin_metrics.internal_rate_of_return_pct:.1f} %" if fin_metrics.internal_rate_of_return_pct else "N/A"
        render_kpi_card(
            "Internal Rate of Return",
            irr_str,
            f"ROI: {fin_metrics.return_on_investment_pct:.0f}% lifetime",
            status="ok" if fin_metrics.internal_rate_of_return_pct and fin_metrics.internal_rate_of_return_pct > 8.0 else "default"
        )
    with k6:
        render_kpi_card(
            "Levelized Cost (LCOS)",
            f"{fin_metrics.levelized_cost_of_storage_eur_kwh:.3f} {currency}/kWh",
            f"{fin_metrics.levelized_cost_of_storage_eur_kwh * 1000.0:,.1f} {currency}/MWh throughput",
            status="ok" if fin_metrics.levelized_cost_of_storage_eur_kwh < 0.25 else "default"
        )

    st.write("")

    # --------------------------------------------------------------------------
    # 5. Interactive Financial Visualization Tabs
    # --------------------------------------------------------------------------
    st.markdown("##### Visual Financial Analysis & Investment Trajectory")

    tab_cf, tab_comp, tab_traj, tab_donut, tab_sens = st.tabs([
        ":material/timeline: 15-Year Cash Flow & Amortization",
        ":material/balance: Annual Electricity Cost Comparison",
        ":material/trending_up: 15-Year Cumulative Total Cost",
        ":material/pie_chart: CAPEX Sizing Breakdown",
        ":material/tune: Parameter Sensitivity Analysis"
    ])

    with tab_cf:
        st.caption(":material/info: *Cumulative project cash flow starting from upfront CAPEX, crossing break-even at the amortization threshold into net lifetime profits.*")
        fig_cf = create_bess_cashflow_payback_figure(fin_metrics, currency=currency)
        st.plotly_chart(fig_cf, use_container_width=True)

    with tab_comp:
        st.caption(":material/info: *Annual electricity bill breakdown comparing Status Quo (Grid without BESS) vs With BESS Peak Shaving & OPEX.*")
        fig_comp = create_bess_annual_cost_comparison_figure(fin_metrics, currency=currency)
        st.plotly_chart(fig_comp, use_container_width=True)

    with tab_traj:
        st.caption(":material/info: *Cumulative 15-year expenditure comparing utility grid bills (Status Quo) vs Storage investment + operating costs (With BESS).*")
        fig_traj = create_bess_cumulative_cost_trajectory_figure(fin_metrics, currency=currency)
        st.plotly_chart(fig_traj, use_container_width=True)

    with tab_donut:
        st.caption(":material/info: *Itemized Turn-Key CAPEX breakdown into Battery Modules, Inverter/PCS, BOS, and Grid Integration.*")
        fig_donut = create_bess_capex_donut_figure(capex_breakdown, currency=currency)
        st.plotly_chart(fig_donut, use_container_width=True)

    with tab_sens:
        st.caption(":material/info: *Sensitivity of Simple Payback Period against ±10% and ±20% shifts in Battery CAPEX and Peak Demand Tariffs.*")
        sens_rows = compute_bess_sensitivity_matrix(
            bess_config=bess_cfg,
            df_timeseries=sim_res.df_timeseries,
            contract=active_contract,
            grid_limit_kw=grid_limit_val
        )
        fig_sens = create_bess_sensitivity_figure(sens_rows, metric="payback_years")
        st.plotly_chart(fig_sens, use_container_width=True)

    # --------------------------------------------------------------------------
    # 6. Detailed 15-Year Life-Cycle Cash Flow Table
    # --------------------------------------------------------------------------
    with st.expander("Detailed 15-Year Life-Cycle Cash Flow Projection Table", icon=":material/table_chart:", expanded=False):
        if fin_metrics.cash_flow_table:
            df_cf = pd.DataFrame(fin_metrics.cash_flow_table)
            df_cf.rename(columns={
                "year": "Operating Year",
                "status_quo_bill": f"Status Quo Bill ({currency})",
                "with_bess_bill": f"With BESS Bill ({currency})",
                "gross_savings": f"Gross Savings ({currency})",
                "bess_opex": f"BESS O&M ({currency})",
                "cell_replacement": f"Cell Refresh ({currency})",
                "net_cash_flow": f"Net Cash Flow ({currency})",
                "cumulative_cash_flow": f"Cumulative CF ({currency})",
                "discounted_cash_flow": f"Discounted CF ({currency})",
                "cumulative_npv": f"Cumulative NPV ({currency})"
            }, inplace=True)
            st.dataframe(df_cf.style.format({col: "{:,.2f}" for col in df_cf.columns if col != "Operating Year"}), use_container_width=True)

    # --------------------------------------------------------------------------
    # 7. Itemized Electricity Billing Comparison Table
    # --------------------------------------------------------------------------
    with st.expander("Itemized Tariff & Bill Reductions (Status Quo vs. With BESS)", icon=":material/receipt_long:", expanded=False):
        b_rows = [
            {
                "Bill Component": "Peak Demand / Capacity Charges",
                "Status Quo": f"{fin_metrics.annual_demand_charge_savings:,.2f} {currency}",
                "With BESS": f"0.00 {currency}",
                "Annual Savings": f"-{fin_metrics.annual_demand_charge_savings:,.2f} {currency}"
            },
            {
                "Bill Component": "Grid Overload Penalties",
                "Status Quo": f"{fin_metrics.annual_penalty_savings:,.2f} {currency}",
                "With BESS": f"0.00 {currency}",
                "Annual Savings": f"-{fin_metrics.annual_penalty_savings:,.2f} {currency}"
            },
            {
                "Bill Component": "Active Energy Charges",
                "Status Quo": f"{fin_metrics.annual_energy_savings:,.2f} {currency}",
                "With BESS": f"0.00 {currency}",
                "Annual Savings": f"-{fin_metrics.annual_energy_savings:,.2f} {currency}"
            },
            {
                "Bill Component": "Total Gross Electricity Bill",
                "Status Quo": f"{fin_metrics.annual_gross_savings:,.2f} {currency}",
                "With BESS": f"0.00 {currency}",
                "Annual Savings": f"-{fin_metrics.annual_gross_savings:,.2f} {currency}"
            },
            {
                "Bill Component": "BESS Annual O&M Expenses",
                "Status Quo": f"0.00 {currency}",
                "With BESS": f"{fin_metrics.annual_opex_year1:,.2f} {currency}",
                "Annual Savings": f"+{fin_metrics.annual_opex_year1:,.2f} {currency} (Cost)"
            },
            {
                "Bill Component": "Net Annual Commercial Benefit",
                "Status Quo": f"0.00 {currency}",
                "With BESS": f"{fin_metrics.annual_net_savings_year1:,.2f} {currency}",
                "Annual Savings": f"+{fin_metrics.annual_net_savings_year1:,.2f} {currency}/Year"
            }
        ]
        st.table(pd.DataFrame(b_rows))
