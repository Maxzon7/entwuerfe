"""
========================================================================================
Scenario 2: Standalone New Contract & Capacity Optimization Sandbox (ui_sandbox/NewContract_sandbox/app.py)
========================================================================================

Standalone Execution:
    python -m streamlit run "ui_sandbox/NewContract_sandbox/app.py"

Evaluates commercial & contractual optimization WITHOUT hardware CAPEX:
  - Tab 1: Baseline Load Profile & Current 4-Pillar Contract Diagnostics
  - Tab 2: Contract Optimization Sub-Scenarios & Interactive Capacity Sweep Curve
      * Sub-Scenario A: Cost-Optimal Contracted Capacity (P_contract) Sweep (finds the exact kW
        that minimizes Reserved Capacity Fees + Excess/Breach Penalties)
      * Sub-Scenario B: Retail Commodity Pricing Switch (Fixed Single, Fixed Dual TOU HT/NT,
        Dynamic EPEX Spot)
      * Sub-Scenario C: Custom Alternative Contract Parameter Tuning
  - Tab 3: Side-by-Side 4-Pillar Electricity Bill Comparison (Current vs. New Contract + PDF Export)
  - Tab 4: 15-Year TCO NPV Comparison & Standardized `ScenarioEvaluationOutput`
========================================================================================
"""

import os
import sys
import copy
from typing import Dict, List, Any, Tuple
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# Ensure root and parent directories are on sys.path for standalone execution
_CURRENT_DIR = os.path.abspath(os.path.dirname(__file__))
_UI_SANDBOX_DIR = os.path.abspath(os.path.join(_CURRENT_DIR, ".."))
_PROJECT_ROOT = os.path.abspath(os.path.join(_UI_SANDBOX_DIR, ".."))
for _p in (_PROJECT_ROOT, _UI_SANDBOX_DIR, _CURRENT_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from ui_sandbox.common import (
    ScenarioEvaluationOutput,
    evaluate_scenario_4pillar_bill_comparison,
    render_shared_4pillar_bill_comparison_ui,
    render_scenario_evaluation_output_card,
    compute_15y_tco_npv,
    render_standalone_baseline_control_bar,
)
from ui_sandbox.Currentsituation_sandbox.engine.config_and_models import (
    LoadSeries2025,
    StatusQuoConfig2025,
    PricingMode,
)
from ui_sandbox.Currentsituation_sandbox.engine.consumption_pipeline import (
    extract_monthly_consumption_records,
    MONTH_NAMES,
)
from ui_sandbox.Currentsituation_sandbox.engine.status_quo_master import (
    calculate_status_quo_master_2025,
)
from ui_sandbox.Currentsituation_sandbox.contract.assumptions_banner import (
    build_assumptions_register_dict,
)


def _compute_contract_capacity_optimization_sweep(
    load: LoadSeries2025,
    base_config: StatusQuoConfig2025,
    n_points: int = 25,
) -> Tuple[pd.DataFrame, float]:
    """
    Sweeps Contracted Capacity (P_contract) from 40% of peak demand up to 115% of peak demand,
    evaluating the exact 4-Pillar annual bill at each step to find the mathematical minimum
    between standing contracted capacity fees and capacity breach / excess penalties.
    """
    p_max = max(50.0, load.peak_demand_kw)
    p_min_sweep = max(20.0, round(p_max * 0.45, -1))
    p_max_sweep = round(p_max * 1.15, -1)
    grid_kws = np.unique(np.round(np.linspace(p_min_sweep, p_max_sweep, n_points), 1))
    # Ensure current contracted kW and measured peak kW are included in the sweep
    grid_kws = np.unique(np.sort(np.append(grid_kws, [base_config.dso.contracted_capacity_kw, round(p_max, 1)])))

    rows: List[Dict[str, float]] = []
    for kw_cand in grid_kws:
        cfg_tmp = copy.deepcopy(base_config)
        cfg_tmp.dso.contracted_capacity_kw = float(kw_cand)
        res_tmp = calculate_status_quo_master_2025(load=load, config=cfg_tmp)

        cap_fee_yr = sum(r.contracted_capacity_fee for r in res_tmp.dso_monthly)
        peak_fee_yr = sum(r.peak_demand_fee for r in res_tmp.dso_monthly)
        pen_fee_yr = sum(r.excess_penalty_fee for r in res_tmp.dso_monthly)
        breach_months = sum(1 for r in res_tmp.dso_monthly if r.is_capacity_breached)

        rows.append(
            {
                "contracted_kw": float(kw_cand),
                "annual_dso_net": float(res_tmp.annual_dso_net),
                "annual_total_net": float(res_tmp.total_annual_net),
                "annual_total_gross": float(res_tmp.total_annual_gross),
                "contracted_capacity_fee_yr": float(cap_fee_yr),
                "peak_demand_fee_yr": float(peak_fee_yr),
                "excess_penalty_fee_yr": float(pen_fee_yr),
                "capacity_plus_penalty_yr": float(cap_fee_yr + pen_fee_yr),
                "breach_months": int(breach_months),
            }
        )

    df_sweep = pd.DataFrame(rows)
    best_idx = int(df_sweep["annual_total_net"].idxmin())
    optimal_kw = float(df_sweep.loc[best_idx, "contracted_kw"])
    return df_sweep, optimal_kw


def _create_capacity_sweep_figure(
    df_sweep: pd.DataFrame,
    current_kw: float,
    optimal_kw: float,
    selected_kw: float,
    currency_code: str,
) -> go.Figure:
    """Creates the interactive Contracted Capacity Optimization Curve (Total DSO Cost vs. P_contract)."""
    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=df_sweep["contracted_kw"],
            y=df_sweep["annual_total_net"],
            mode="lines+markers",
            name=f"Total Annual Net Bill ({currency_code}/yr)",
            line=dict(color="#38bdf8", width=3),
            marker=dict(size=6),
        )
    )
    fig.add_trace(
        go.Bar(
            x=df_sweep["contracted_kw"],
            y=df_sweep["contracted_capacity_fee_yr"],
            name=f"Pos 2.2 Reserved Capacity Fee ({currency_code}/yr)",
            marker_color="rgba(59, 130, 246, 0.45)",
        )
    )
    fig.add_trace(
        go.Bar(
            x=df_sweep["contracted_kw"],
            y=df_sweep["excess_penalty_fee_yr"],
            name=f"Pos 2.6 Excess Capacity Penalty ({currency_code}/yr)",
            marker_color="rgba(239, 68, 68, 0.65)",
        )
    )

    fig.add_vline(
        x=current_kw,
        line_dash="dash",
        line_color="#f59e0b",
        annotation_text=f"Status Quo: {current_kw:,.0f} kW",
        annotation_position="top left",
    )
    fig.add_vline(
        x=optimal_kw,
        line_dash="dot",
        line_color="#10b981",
        annotation_text=f"Cost-Optimal: {optimal_kw:,.0f} kW",
        annotation_position="top right",
    )
    if abs(selected_kw - optimal_kw) > 1.0 and abs(selected_kw - current_kw) > 1.0:
        fig.add_vline(
            x=selected_kw,
            line_dash="solid",
            line_color="#a855f7",
            annotation_text=f"Selected: {selected_kw:,.0f} kW",
            annotation_position="bottom right",
        )

    fig.update_layout(
        title=dict(
            text="<b>Contracted Capacity (P_contract) Optimization Curve: Standing Capacity Fee vs. Breach Penalty</b>",
            x=0.01,
            y=0.98,
            xanchor="left",
            font=dict(size=14, color="#f8fafc"),
        ),
        barmode="stack",
        template="plotly_dark",
        paper_bgcolor="rgba(15, 23, 42, 0.0)",
        plot_bgcolor="rgba(15, 23, 42, 0.55)",
        height=400,
        margin=dict(l=50, r=30, t=90, b=45),
        legend=dict(orientation="h", yanchor="bottom", y=1.08, xanchor="left", x=0.01),
        xaxis=dict(title="Contracted Grid Capacity P_contract (kW)", gridcolor="#1e293b"),
        yaxis=dict(title=f"Annual Cost ({currency_code}/yr)", gridcolor="#1e293b"),
    )
    return fig


def render_new_contract_sandbox(key_prefix: str = "newcon_sb") -> ScenarioEvaluationOutput:
    """Main orchestrator for Scenario 2: Standalone New Contract & Capacity Optimization Sandbox."""
    st.markdown(
        """
        <div style="background: linear-gradient(90deg, #0f172a 0%, #1e293b 100%);
                    border-left: 5px solid #38bdf8; padding: 14px 20px; border-radius: 8px; margin-bottom: 12px;">
            <h3 style="margin:0; color:#f8fafc; font-size:1.25rem;">
                Scenario 2: Standalone Contract & Capacity Optimization Sandbox (Zero-Hardware Baseline)
            </h3>
            <p style="margin:4px 0 0 0; color:#94a3b8; font-size:0.86rem;">
                Quantifies how much of the electricity bill and capacity breach penalties can be eliminated purely by
                right-sizing Contracted Grid Capacity (P_contract) or switching Retail Commodity Tariff Models — before investing in PV or BESS hardware.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Top standalone baseline selector (Default: Preset B EDEMSA Salentein where excess penalty is huge, or user choice)
    base_load, base_config, site_label = render_standalone_baseline_control_bar(
        key_prefix=key_prefix,
        default_preset_idx=1,
    )
    curr = base_config.currency_code
    res_base = calculate_status_quo_master_2025(load=base_load, config=base_config)
    monthly_cons = extract_monthly_consumption_records(base_load)

    # Pre-compute capacity optimization sweep
    df_sweep, optimal_kw = _compute_contract_capacity_optimization_sweep(load=base_load, base_config=base_config)

    tabs = st.tabs(
        [
            ":material/analytics: 1. Baseline Contract Audit & Breach Diagnostics",
            ":material/tune: 2. Contract Configurator & Sub-Scenarios",
            ":material/compare_arrows: 3. Side-by-Side 4-Pillar Bill Comparison",
            ":material/account_balance: 4. 15-Year TCO & Standardized Output",
        ]
    )

    # ----------------------------------------------------------------------------------
    # TAB 1: Baseline Contract Audit & Breach Diagnostics
    # ----------------------------------------------------------------------------------
    with tabs[0]:
        st.markdown("#### :material/warning: Current Contract Capacity Audit & Penalty Exposure")
        breach_months_cnt = sum(1 for r in res_base.dso_monthly if r.is_capacity_breached)
        annual_pen_cost = sum(r.excess_penalty_fee for r in res_base.dso_monthly)
        annual_cap_cost = sum(r.contracted_capacity_fee for r in res_base.dso_monthly)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric(
            "Current Contracted Limit",
            f"{base_config.dso.contracted_capacity_kw:,.1f} kW",
            f"Measured Max Peak: {base_load.peak_demand_kw:,.1f} kW",
            delta_color="off",
        )
        m2.metric(
            "Months with Capacity Breach",
            f"{breach_months_cnt} / 12 months",
            f"Max Excess: +{max(0.0, base_load.peak_demand_kw - base_config.dso.contracted_capacity_kw):,.1f} kW",
            delta_color="inverse" if breach_months_cnt > 0 else "normal",
        )
        m3.metric(
            "Status Quo Capacity + Penalty Cost",
            f"{curr} {annual_cap_cost + annual_pen_cost:,.2f}/yr",
            f"Excess Penalty: {curr} {annual_pen_cost:,.2f}/yr",
            delta_color="inverse" if annual_pen_cost > 0 else "off",
        )
        m4.metric(
            "Cost-Optimal Contracted Capacity",
            f"{optimal_kw:,.1f} kW",
            f"Optimal Net Bill: {curr} {df_sweep['annual_total_net'].min():,.0f}/yr",
            delta_color="normal",
        )

        # Monthly Peak vs Contracted Capacity Bar Chart
        fig_m = go.Figure()
        fig_m.add_trace(
            go.Bar(
                x=[r.month_name[:3] for r in monthly_cons],
                y=[r.peak_demand_kw for r in monthly_cons],
                name="Registered Monthly Peak (kW)",
                marker_color=[
                    "#ef4444" if r.peak_demand_kw > base_config.dso.contracted_capacity_kw else "#38bdf8"
                    for r in monthly_cons
                ],
            )
        )
        fig_m.add_hline(
            y=base_config.dso.contracted_capacity_kw,
            line_dash="dash",
            line_color="#f59e0b",
            annotation_text=f"Current Contracted Limit ({base_config.dso.contracted_capacity_kw:,.0f} kW)",
        )
        fig_m.add_hline(
            y=optimal_kw,
            line_dash="dot",
            line_color="#10b981",
            annotation_text=f"Cost-Optimal Limit ({optimal_kw:,.0f} kW)",
        )
        fig_m.update_layout(
            title=dict(
                text="<b>12-Month Registered Peak Demand vs. Current & Cost-Optimal Contracted Capacity</b>",
                x=0.01,
                y=0.98,
                xanchor="left",
            ),
            template="plotly_dark",
            paper_bgcolor="rgba(15, 23, 42, 0.0)",
            plot_bgcolor="rgba(15, 23, 42, 0.55)",
            height=360,
            margin=dict(l=50, r=30, t=85, b=40),
            yaxis=dict(title="Power Demand (kW)", gridcolor="#1e293b"),
        )
        st.plotly_chart(fig_m, use_container_width=True, key=f"{key_prefix}_t1_monthly_peaks")

    # ----------------------------------------------------------------------------------
    # TAB 2: Contract Configurator & Sub-Scenarios
    # ----------------------------------------------------------------------------------
    with tabs[1]:
        st.markdown("#### :material/tune: Select or Configure Alternative Contract Sub-Scenario")

        sub_mode = st.radio(
            "Contract Optimization Strategy (Sub-Scenario)",
            options=[
                "Sub-Scenario A: Cost-Optimal Contracted Capacity (P_contract) Right-Sizing",
                "Sub-Scenario B: Retail Commodity Pricing Switch (Fixed Dual TOU vs. Flat vs. Dynamic Spot)",
                "Sub-Scenario C: Combined Custom Contract & Tariff Negotiation",
            ],
            horizontal=True,
            key=f"{key_prefix}_sub_mode",
        )

        alt_config = copy.deepcopy(base_config)

        c_left, c_right = st.columns([1.35, 1.0])
        with c_right:
            with st.container(border=True):
                st.markdown("##### :material/settings: New Contract Parameters")
                default_new_kw = optimal_kw if "Sub-Scenario A" in sub_mode else base_config.dso.contracted_capacity_kw
                new_p_contract = st.number_input(
                    "New Contracted Capacity P_contract (kW)",
                    min_value=10.0,
                    max_value=20000.0,
                    value=float(default_new_kw),
                    step=5.0,
                    key=f"{key_prefix}_new_p_kw_{sub_mode[:14]}",
                )
                alt_config.dso.contracted_capacity_kw = float(new_p_contract)

                new_adjust_breach = st.checkbox(
                    "DSO Breach Rule: Auto-bill monthly peak if P_peak > P_contract",
                    value=bool(base_config.dso.adjust_capacity_on_breach),
                    key=f"{key_prefix}_new_adj_breach",
                )
                alt_config.dso.adjust_capacity_on_breach = bool(new_adjust_breach)

                new_enable_pen = st.checkbox(
                    "DSO Excess Capacity Penalty Active (Exceso de Potencia)",
                    value=bool(base_config.dso.enable_excess_capacity_penalty),
                    key=f"{key_prefix}_new_en_pen",
                )
                alt_config.dso.enable_excess_capacity_penalty = bool(new_enable_pen)

                if alt_config.enable_pillar_1_supplier or "Sub-Scenario B" in sub_mode or "Sub-Scenario C" in sub_mode:
                    st.markdown("---")
                    st.markdown("##### :material/storefront: Pillar 1 Retailer Pricing Model")
                    enable_p1_alt = st.checkbox(
                        "Enable Pillar 1 Unbundled Retailer (Uncheck for Bundled Single-Utility)",
                        value=bool(base_config.enable_pillar_1_supplier),
                        key=f"{key_prefix}_en_p1_alt",
                    )
                    alt_config.enable_pillar_1_supplier = bool(enable_p1_alt)

                    mode_map = {
                        "Fixed Single Rate (Enkeltarief)": (PricingMode.FIXED, False),
                        "Fixed Dual TOU Rate (Dubbeltarief HT/NT)": (PricingMode.FIXED, True),
                        "Dynamic Wholesale Spot (EPEX + Margin)": (PricingMode.DYNAMIC, False),
                    }
                    curr_mode_idx = 1 if base_config.supplier.is_dual_rate else (2 if base_config.supplier.pricing_mode == PricingMode.DYNAMIC else 0)
                    sel_mode_lbl = st.selectbox(
                        "Retail Commodity Tariff Model",
                        options=list(mode_map.keys()),
                        index=curr_mode_idx,
                        key=f"{key_prefix}_sup_mode_sel",
                    )
                    p_mode, is_dual = mode_map[sel_mode_lbl]
                    alt_config.supplier.pricing_mode = p_mode
                    alt_config.supplier.is_dual_rate = is_dual

                    if p_mode == PricingMode.FIXED and not is_dual:
                        alt_config.supplier.fixed_rate_kwh = st.number_input(
                            f"Flat Commodity Rate ({curr}/kWh)",
                            min_value=0.0,
                            value=float(base_config.supplier.fixed_rate_kwh),
                            step=0.005,
                            format="%.4f",
                            key=f"{key_prefix}_flat_rate",
                        )
                    elif p_mode == PricingMode.FIXED and is_dual:
                        r1, r2 = st.columns(2)
                        alt_config.supplier.fixed_rate_peak_kwh = r1.number_input(
                            f"Peak / HT Rate ({curr}/kWh)",
                            min_value=0.0,
                            value=float(base_config.supplier.fixed_rate_peak_kwh),
                            step=0.005,
                            format="%.4f",
                            key=f"{key_prefix}_ht_rate",
                        )
                        alt_config.supplier.fixed_rate_offpeak_kwh = r2.number_input(
                            f"Off-Peak / NT Rate ({curr}/kWh)",
                            min_value=0.0,
                            value=float(base_config.supplier.fixed_rate_offpeak_kwh),
                            step=0.005,
                            format="%.4f",
                            key=f"{key_prefix}_nt_rate",
                        )
                    else:
                        alt_config.supplier.supplier_margin_kwh = st.number_input(
                            f"Supplier Spot Margin ({curr}/kWh)",
                            min_value=0.0,
                            value=float(base_config.supplier.supplier_margin_kwh),
                            step=0.001,
                            format="%.4f",
                            key=f"{key_prefix}_spot_margin",
                        )

                one_off_contract_fee = st.number_input(
                    f"One-Off Contract Upgrade / Connection Fee CAPEX ({curr})",
                    min_value=0.0,
                    value=0.0,
                    step=500.0,
                    key=f"{key_prefix}_one_off_capex",
                    help="Optional one-time administrative or transformer upgrade fee charged by the DSO when increasing contracted capacity.",
                )

        with c_left:
            fig_sweep = _create_capacity_sweep_figure(
                df_sweep=df_sweep,
                current_kw=base_config.dso.contracted_capacity_kw,
                optimal_kw=optimal_kw,
                selected_kw=alt_config.dso.contracted_capacity_kw,
                currency_code=curr,
            )
            st.plotly_chart(fig_sweep, use_container_width=True, key=f"{key_prefix}_sweep_chart")

            # Sub-Scenario Comparison Summary Table
            cfg_opt = copy.deepcopy(base_config)
            cfg_opt.dso.contracted_capacity_kw = optimal_kw
            res_opt = calculate_status_quo_master_2025(load=base_load, config=cfg_opt)
            res_alt = calculate_status_quo_master_2025(load=base_load, config=alt_config)

            sub_df = pd.DataFrame(
                [
                    {
                        "Contract Variant": "1. Status Quo Contract (Baseline)",
                        "P_contract (kW)": f"{base_config.dso.contracted_capacity_kw:,.1f}",
                        "Breach Months": sum(1 for r in res_base.dso_monthly if r.is_capacity_breached),
                        f"Annual Net Bill ({curr})": f"{res_base.total_annual_net:,.2f}",
                        f"Net Savings vs. Baseline ({curr}/yr)": "0.00",
                    },
                    {
                        "Contract Variant": "2. Auto Cost-Optimal P_contract",
                        "P_contract (kW)": f"{optimal_kw:,.1f}",
                        "Breach Months": sum(1 for r in res_opt.dso_monthly if r.is_capacity_breached),
                        f"Annual Net Bill ({curr})": f"{res_opt.total_annual_net:,.2f}",
                        f"Net Savings vs. Baseline ({curr}/yr)": f"{res_base.total_annual_net - res_opt.total_annual_net:+,.2f}",
                    },
                    {
                        "Contract Variant": "3. Active Configured New Contract",
                        "P_contract (kW)": f"{alt_config.dso.contracted_capacity_kw:,.1f}",
                        "Breach Months": sum(1 for r in res_alt.dso_monthly if r.is_capacity_breached),
                        f"Annual Net Bill ({curr})": f"{res_alt.total_annual_net:,.2f}",
                        f"Net Savings vs. Baseline ({curr}/yr)": f"{res_base.total_annual_net - res_alt.total_annual_net:+,.2f}",
                    },
                ]
            )
            st.markdown("##### :material/table_chart: Multi-Sub-Scenario Contract Comparison")
            st.dataframe(sub_df, use_container_width=True, hide_index=True)

    # ----------------------------------------------------------------------------------
    # TAB 3: Side-by-Side 4-Pillar Bill Comparison
    # ----------------------------------------------------------------------------------
    with tabs[2]:
        period_options = ["Annual Statement 2025 (Full Year)"] + [
            f"2025-{m:02d} ({MONTH_NAMES[m - 1]})" for m in range(1, 13)
        ]
        sel_period = st.selectbox(
            ":material/calendar_month: Select Billing Statement Period for Line-by-Line Comparison",
            options=period_options,
            index=0,
            key=f"{key_prefix}_period_sel",
        )

        comp_data = evaluate_scenario_4pillar_bill_comparison(
            base_load=base_load,
            residual_load=base_load,
            base_config=base_config,
            alt_config=alt_config,
            period_choice=sel_period,
        )

        assumptions_dict = build_assumptions_register_dict(
            load_series=base_load,
            config=alt_config,
            source_filename=site_label,
            bess_config=None,
        )
        physical_kpis = {
            "peak_before_kw": base_load.peak_demand_kw,
            "peak_after_kw": base_load.peak_demand_kw,
            "peak_shaved_kw": 0.0,
            "peak_shaved_pct": 0.0,
            "grid_limit_kw": alt_config.dso.contracted_capacity_kw,
            "overload_hrs_before": float(np.sum(base_load.power_kw > base_config.dso.contracted_capacity_kw) * 0.25),
            "overload_hrs_after": float(np.sum(base_load.power_kw > alt_config.dso.contracted_capacity_kw) * 0.25),
            "remaining_deficit_kwh": 0.0,
            "load_kwh": base_load.total_energy_kwh,
            "grid_import_kwh": base_load.total_energy_kwh,
            "discharge_kwh": 0.0,
            "rte_loss_kwh": 0.0,
        }

        render_shared_4pillar_bill_comparison_ui(
            comp_data=comp_data,
            baseline_col_title=f"Current Contract ({base_config.dso.contracted_capacity_kw:.0f} kW)",
            scenario_col_title=f"New Contract ({alt_config.dso.contracted_capacity_kw:.0f} kW)",
            site_name=site_label,
            assumptions_dict=assumptions_dict,
            physical_kpis=physical_kpis,
            key_prefix=key_prefix,
        )

    # ----------------------------------------------------------------------------------
    # TAB 4: 15-Year TCO & Standardized Output
    # ----------------------------------------------------------------------------------
    res_after_full = calculate_status_quo_master_2025(load=base_load, config=alt_config)
    annual_net_sav = res_base.total_annual_net - res_after_full.total_annual_net
    payback_yrs = (one_off_contract_fee / annual_net_sav) if (annual_net_sav > 0 and one_off_contract_fee > 0) else (0.0 if annual_net_sav > 0 else 99.9)

    npv_before, sched_before = compute_15y_tco_npv(
        capex=0.0,
        annual_grid_bill_year1=res_base.total_annual_net,
        discount_rate_pct=base_config.discount_rate_pct,
        escalation_rate_pct=base_config.energy_escalation_pct,
        horizon_years=15,
    )
    npv_after, sched_after = compute_15y_tco_npv(
        capex=one_off_contract_fee,
        annual_grid_bill_year1=res_after_full.total_annual_net,
        discount_rate_pct=alt_config.discount_rate_pct,
        escalation_rate_pct=alt_config.energy_escalation_pct,
        horizon_years=15,
    )

    scen_output = ScenarioEvaluationOutput(
        scenario_id="new_contract",
        scenario_name="Scenario 2: Contract & Capacity Optimization",
        sub_scenario_label=f"P_contract = {alt_config.dso.contracted_capacity_kw:.0f} kW ({alt_config.supplier.pricing_mode.value.upper()})",
        currency_code=curr,
        peak_before_kw=base_load.peak_demand_kw,
        peak_after_kw=base_load.peak_demand_kw,
        peak_shaved_kw=0.0,
        peak_shaved_pct=0.0,
        grid_limit_kw=alt_config.dso.contracted_capacity_kw,
        overload_hours_before=float(np.sum(base_load.power_kw > base_config.dso.contracted_capacity_kw) * 0.25),
        overload_hours_after=float(np.sum(base_load.power_kw > alt_config.dso.contracted_capacity_kw) * 0.25),
        annual_load_kwh=base_load.total_energy_kwh,
        annual_grid_import_before_kwh=base_load.total_energy_kwh,
        annual_grid_import_after_kwh=base_load.total_energy_kwh,
        self_consumption_pct=0.0,
        autarky_pct=0.0,
        capex_total=float(one_off_contract_fee),
        annual_tech_opex=0.0,
        annual_grid_bill_net_before=float(res_base.total_annual_net),
        annual_grid_bill_net_after=float(res_after_full.total_annual_net),
        annual_grid_bill_gross_before=float(res_base.total_annual_gross),
        annual_grid_bill_gross_after=float(res_after_full.total_annual_gross),
        annual_net_savings=float(annual_net_sav),
        simple_payback_years=float(payback_yrs),
        npv_15y_tco_before=float(npv_before),
        npv_15y_tco_after=float(npv_after),
        npv_15y_net_benefit=float(npv_before - npv_after),
    )

    with tabs[3]:
        st.markdown("#### :material/account_balance: 15-Year Cumulative TCO Comparison (Status Quo vs. New Contract)")
        fig_tco = go.Figure()
        fig_tco.add_trace(
            go.Scatter(
                x=[r["year"] for r in sched_before],
                y=[r["cumulative_discounted"] for r in sched_before],
                mode="lines+markers",
                name="Status Quo Contract (15Y Cumulative NPV Cost)",
                line=dict(color="#ef4444", width=3, dash="dash"),
            )
        )
        fig_tco.add_trace(
            go.Scatter(
                x=[r["year"] for r in sched_after],
                y=[r["cumulative_discounted"] for r in sched_after],
                mode="lines+markers",
                name="New Optimized Contract (15Y Cumulative NPV Cost)",
                line=dict(color="#10b981", width=3),
            )
        )
        fig_tco.update_layout(
            title=dict(text="<b>15-Year Discounted Cumulative Electricity TCO</b>", x=0.01, y=0.98, xanchor="left"),
            template="plotly_dark",
            paper_bgcolor="rgba(15, 23, 42, 0.0)",
            plot_bgcolor="rgba(15, 23, 42, 0.55)",
            height=380,
            margin=dict(l=50, r=30, t=85, b=40),
            xaxis=dict(title="Project Year", gridcolor="#1e293b"),
            yaxis=dict(title=f"Cumulative Discounted Cost ({curr})", gridcolor="#1e293b"),
        )
        st.plotly_chart(fig_tco, use_container_width=True, key=f"{key_prefix}_tco_chart")

        render_scenario_evaluation_output_card(output=scen_output, key_prefix=key_prefix)

    return scen_output


def main() -> None:
    st.set_page_config(
        page_title="New Contract Optimization Sandbox (Scenario 2)",
        page_icon=":material/tune:",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    render_new_contract_sandbox(key_prefix="newcon_sb")


if __name__ == "__main__":
    main()

