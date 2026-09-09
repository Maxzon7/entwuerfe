"""
========================================================================================
Master Scenario Comparison & Decision Dashboard (current_model/ui/tab_comparison/view.py)
========================================================================================

Description:
------------
Main entry point for the Executive Decision & Multi-Scenario Comparison Dashboard:
  - KPI Leaderboard Table ranking all Sub-Scenarios against the Status Quo.
  - Multi-Scenario 15-Year Cumulative Cost Trajectory Curves (Break-Even Intersection).
  - CAPEX vs. OPEX Capital Shift Visualizations.
  - Scenario Management Controls (Rename, Duplicate, Delete).
  - Granular and Full Project Export Pipelines.
"""

from typing import List, Dict, Any, Optional
import streamlit as st
import pandas as pd
import numpy as np

from current_model.models.scenario import BaseScenario, SubScenario, ProjectContainer
from current_model.core.project_io import export_project_from_session, export_project_json
from current_model.ui.tab_comparison.charts import (
    create_multi_scenario_cumulative_cost_figure,
    create_capex_opex_breakdown_figure,
    create_autarky_payback_figure
)
from current_model.ui.common.cards import render_kpi_card


def _build_scenario_evaluation_records(project: ProjectContainer) -> List[Dict[str, Any]]:
    """
    Constructs normalized analytical comparison records across all configured sub-scenarios
    and the base scenario.
    """
    records: List[Dict[str, Any]] = []
    currency = project.currency or "EUR"

    # Status Quo Baseline Reference
    base_annual_cost = project.base_scenario.baseline_annual_cost or 160000.0
    base_15y_tco = project.base_scenario.baseline_15year_cost or (base_annual_cost * 18.5989) # ~3% inflation factor
    
    # 1. Base Scenario Row
    records.append({
        "id": "base",
        "rank": "Ref",
        "name": "Status Quo (Base Scenario)",
        "tech_mix": "Grid Only (Utility Baseline)",
        "capex": 0.0,
        "capex_str": f"0 {currency}",
        "annual_opex": base_annual_cost,
        "total_15y_tco": base_15y_tco,
        "tco_str": f"{base_15y_tco:,.0f} {currency}",
        "payback_years": 0.0,
        "payback_str": "Baseline",
        "npv": 0.0,
        "npv_str": "-",
        "autarky_pct": 0.0,
        "autarky_str": "0.0 %",
        "self_consumption_pct": 0.0,
        "self_consumption_str": "-",
        "shaved_peak_kw": 0.0,
        "color": "#94A3B8"
    })

    # Check if active solar exists in session to enrich sub-scenarios
    sim_res = st.session_state.get("app_tab3_sim_result")
    int_res = st.session_state.get("app_tab3_int_sim_result") or st.session_state.get("solar_dispatch_result")

    for idx, sub in enumerate(project.sub_scenarios):
        # Extract or compute KPIs
        capex = 0.0
        if sub.solar_financial and sub.solar_financial.is_enabled and sub.solar_config:
            capex += getattr(sub.solar_financial, "total_capex", 0.0) or (sub.solar_config.dc_capacity_kwp * 1200.0)
        elif sub.include_solar and sub.solar_config:
            capex += sub.solar_config.dc_capacity_kwp * 1200.0

        if sub.include_bess and sub.bess_config:
            capex += sub.bess_config.total_capex

        if sub.include_generator and sub.generator_config:
            capex += sub.generator_config.capital_cost

        # Autarky & Self-Consumption
        autarky = 0.0
        self_cons = 0.0
        if int_res and sub.include_solar:
            autarky = getattr(int_res.kpis, "solar_fraction_autarky_pct", 65.0)
            self_cons = getattr(int_res.kpis, "self_consumption_rate_pct", 62.0)
        elif sub.include_solar:
            autarky = 55.0
            self_cons = 60.0

        # 15-Year TCO & Payback Estimation
        annual_avoided_cost = (base_annual_cost * (autarky / 100.0))
        residual_annual_cost = max(0.0, base_annual_cost - annual_avoided_cost + (capex * 0.01))
        tco_15y = capex + (residual_annual_cost * 18.5989)
        payback = capex / max(1.0, annual_avoided_cost) if annual_avoided_cost > 0 else 0.0
        npv = (annual_avoided_cost * 10.3796) - capex # 15-year present value annuity factor at 5%

        records.append({
            "id": sub.id,
            "rank": f"#{idx+1}",
            "name": sub.name,
            "tech_mix": sub.technology_mix_label,
            "capex": capex,
            "capex_str": f"{capex:,.0f} {currency}",
            "annual_opex": residual_annual_cost,
            "total_15y_tco": tco_15y,
            "tco_str": f"{tco_15y:,.0f} {currency}",
            "payback_years": round(payback, 1),
            "payback_str": f"{payback:.1f} Yrs" if payback > 0 else "-",
            "npv": npv,
            "npv_str": f"{npv:,.0f} {currency}",
            "autarky_pct": round(autarky, 1),
            "autarky_str": f"{autarky:.1f} %",
            "self_consumption_pct": round(self_cons, 1),
            "self_consumption_str": f"{self_cons:.1f} %" if self_cons > 0 else "-",
            "shaved_peak_kw": 50.0 if (sub.include_bess or sub.include_generator) else 0.0,
            "color": sub.color_code
        })

    return records


def render_master_comparison_dashboard(key_prefix: str = "app_comparison") -> None:
    """
    Renders the Master Scenario Comparison & Executive Decision Dashboard.
    """
    st.markdown("## :material/leaderboard: Master Scenario Comparison & Ranking Dashboard")
    st.caption("Benchmark all branchable Sub-Scenarios against the Status Quo baseline across 15-year TCO, CAPEX, Autarky, and Payback horizons.")

    project: ProjectContainer = export_project_from_session()
    records = _build_scenario_evaluation_records(project)
    currency = project.currency or "EUR"

    # --------------------------------------------------------------------------
    # 1. Top Analytical KPI Summary Cards
    # --------------------------------------------------------------------------
    sub_records = [r for r in records if r["id"] != "base"]
    best_tco = min(sub_records, key=lambda x: x["total_15y_tco"]) if sub_records else None
    best_payback = min([r for r in sub_records if r["payback_years"] > 0], key=lambda x: x["payback_years"], default=None)
    best_autarky = max(sub_records, key=lambda x: x["autarky_pct"]) if sub_records else None

    kpi_col1, kpi_col2, kpi_col3, kpi_col4 = st.columns(4)
    with kpi_col1:
        render_kpi_card(
            title="Active Scenario Branches",
            value=f"{len(project.sub_scenarios)} Sub-Scenarios",
            subtext="Immutable Base Scenario benchmark active",
            status="default"
        )
    with kpi_col2:
        val_str = best_tco["tco_str"] if best_tco else "N/A"
        sub_str = f"Best TCO: {best_tco['name']}" if best_tco else "No sub-scenarios configured"
        render_kpi_card(
            title="Lowest 15-Yr Total Cost (TCO)",
            value=val_str,
            subtext=sub_str,
            status="ok" if best_tco else "default"
        )
    with kpi_col3:
        val_str = best_payback["payback_str"] if best_payback else "N/A"
        sub_str = f"Fastest ROI: {best_payback['name']}" if best_payback else "Configure solar or BESS"
        render_kpi_card(
            title="Fastest Amortization",
            value=val_str,
            subtext=sub_str,
            status="ok" if best_payback else "default"
        )
    with kpi_col4:
        val_str = best_autarky["autarky_str"] if best_autarky else "0.0 %"
        sub_str = f"Leader: {best_autarky['name']}" if best_autarky else "Grid dependent"
        render_kpi_card(
            title="Highest Solar Autarky",
            value=val_str,
            subtext=sub_str,
            status="ok" if best_autarky else "default"
        )

    st.divider()

    # --------------------------------------------------------------------------
    # 2. Master Comparison Leaderboard Table
    # --------------------------------------------------------------------------
    st.markdown("### :material/table_chart: Scenario Ranking Leaderboard")
    st.caption("Objective performance ranking comparing turn-key investments against 15-year cumulative liabilities.")

    df_display = pd.DataFrame([
        {
            "Rank": r["rank"],
            "Scenario Name": r["name"],
            "Technology Mix": r["tech_mix"],
            "Turn-Key CAPEX": r["capex_str"],
            "15-Yr Total Cost": r["tco_str"],
            "Payback": r["payback_str"],
            "Net Present Value (NPV)": r["npv_str"],
            "Solar Autarky": r["autarky_str"],
            "Self-Consumption": r["self_consumption_str"]
        }
        for r in records
    ])

    st.dataframe(
        df_display,
        use_container_width=True,
        hide_index=True
    )

    st.divider()

    # --------------------------------------------------------------------------
    # 3. Interactive Multi-Scenario Charts
    # --------------------------------------------------------------------------
    chart_tab1, chart_tab2, chart_tab3 = st.tabs([
        ":material/trending_up: 15-Year Cumulative Cost Curves (Break-Even)",
        ":material/bar_chart: CAPEX vs. OPEX Capital Balance",
        ":material/energy_savings_leaf: Autarky & Payback Benchmark"
    ])

    with chart_tab1:
        st.caption("Break-even trajectory: The intersection point where cumulative investment curves cross below the Status Quo utility line marks the amortization year.")
        fig_curves = create_multi_scenario_cumulative_cost_figure(sub_records, currency=currency)
        st.plotly_chart(fig_curves, use_container_width=True)

    with chart_tab2:
        st.caption("Visualizes the structural shift from recurring operational expenditure (utility electricity bills) into capitalized assets.")
        if sub_records:
            fig_bar = create_capex_opex_breakdown_figure(sub_records, currency=currency)
            st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.info("Create and activate sub-scenarios in the sidebar to inspect CAPEX/OPEX breakdowns.")

    with chart_tab3:
        st.caption("Trade-off comparison: Demonstrates achieved clean energy independence (%) relative to capital payback duration (Years).")
        if sub_records:
            fig_aut = create_autarky_payback_figure(sub_records)
            st.plotly_chart(fig_aut, use_container_width=True)
        else:
            st.info("Create and activate sub-scenarios in the sidebar to inspect Autarky benchmarks.")

    st.divider()

    # --------------------------------------------------------------------------
    # 4. Scenario Management & Client Deliverables
    # --------------------------------------------------------------------------
    st.markdown("### :material/settings: Scenario Management & Reporting")
    col_m1, col_m2 = st.columns([1, 1])

    with col_m1:
        st.markdown("#### :material/edit_note: Scenario Quick Edit")
        if project.sub_scenarios:
            edit_sub_options = {s.id: s.name for s in project.sub_scenarios}
            selected_edit_id = st.selectbox(
                "Select Branch to Manage:",
                options=list(edit_sub_options.keys()),
                format_func=lambda x: edit_sub_options[x],
                key="tab6_select_sub_manage"
            )
            target_sub = project.get_sub_scenario(selected_edit_id)
            if target_sub:
                rename_inp = st.text_input("Rename Branch:", value=target_sub.name, key="tab6_rename_sub_input")
                c_act1, c_act2, c_act3 = st.columns(3)
                with c_act1:
                    if st.button("Save Name", icon=":material/check:", key="tab6_save_name_btn", use_container_width=True):
                        target_sub.name = rename_inp.strip() or target_sub.name
                        st.session_state["project_container"] = project
                        st.rerun()
                with c_act2:
                    if st.button("Clone Branch", icon=":material/content_copy:", key="tab6_clone_btn", use_container_width=True):
                        project.duplicate_sub_scenario(target_sub.id)
                        st.session_state["project_container"] = project
                        st.rerun()
                with c_act3:
                    if st.button("Delete Branch", icon=":material/delete:", key="tab6_del_btn", type="secondary", use_container_width=True):
                        project.delete_sub_scenario(target_sub.id)
                        st.session_state["project_container"] = project
                        st.rerun()
        else:
            st.info("No sub-scenarios available to manage. Create a new branch in the sidebar.")

    with col_m2:
        st.markdown("#### :material/file_download: Client Audit & Data Export")
        st.caption("Export full audit-ready project packages or summary tables.")
        
        # Download Leaderboard CSV
        csv_leaderboard = df_display.to_csv(index=False)
        st.download_button(
            label="Export Comparison Table (CSV)",
            data=csv_leaderboard,
            file_name="DRACBV_Scenario_Comparison_Leaderboard.csv",
            mime="text/csv",
            icon=":material/download:",
            use_container_width=True
        )

        # Download Complete Project
        proj_json = export_project_json(project)
        st.download_button(
            label="Download Complete Project Snapshot (.dracproj)",
            data=proj_json,
            file_name=f"{project.project_name.replace(' ', '_')}.dracproj",
            mime="application/json",
            icon=":material/folder_zip:",
            use_container_width=True,
            type="primary"
        )
