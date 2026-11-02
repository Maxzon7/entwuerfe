"""
========================================================================================
Scenario 6: Standalone Peaking Generator & Grid Congestion Sandbox (ui_sandbox/Generator_sandbox/app.py)
========================================================================================

Standalone Execution:
    python -m streamlit run "ui_sandbox/Generator_sandbox/app.py"

Evaluates on-site Peaking Generator (Genset) dispatch for Grid Congestion (Netcongestie)
bridging and capacity breach penalty elimination, coupled with the 4-Pillar Billing Engine:
  - Tab 1: Grid Constraint & Overload Diagnostics (Exceedance frequency, duration, energy)
  - Tab 2: Generator Sizing, Minimum Load Physics, Fuel Curve & 15-Min Dispatch
      * Enforces minimum load ratio (e.g. 25–30% rated kW to prevent engine wet-stacking)
      * Linearized Willans fuel consumption model: F(P) = a * P_gen + b * P_rated
      * Supports Diesel, Natural Gas, and HVO / Renewable Biodiesel
  - Tab 3: Side-by-Side 4-Pillar Grid Bill Savings vs. Annual Fuel & Servicing OPEX + PDF Export
  - Tab 4: Purchase CAPEX vs. Rental/Leasing OPEX 15-Year TCO Sub-Scenario Comparison &
           Standardized `ScenarioEvaluationOutput`
========================================================================================
"""

import os
import sys
from typing import Dict, List, Any
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# Ensure root and parent directories are on sys.path for standalone execution
_CURRENT_DIR = os.path.abspath(os.path.dirname(__file__))
_UI_SANDBOX_DIR = os.path.abspath(os.path.join(_CURRENT_DIR, ".."))
_PROJECT_ROOT = os.path.abspath(os.path.join(_UI_SANDBOX_DIR, ".."))
_WORKSPACE_DIR = os.path.abspath(os.path.join(_PROJECT_ROOT, ".."))
for _p in (_WORKSPACE_DIR, _PROJECT_ROOT, _UI_SANDBOX_DIR, _CURRENT_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from ui_sandbox.common import (
    ScenarioEvaluationOutput,
    build_residual_load_series_2025,
    evaluate_scenario_4pillar_bill_comparison,
    render_shared_4pillar_bill_comparison_ui,
    render_scenario_evaluation_output_card,
    compute_15y_tco_npv,
    render_standalone_baseline_control_bar,
)
from ui_sandbox.Currentsituation_sandbox.engine.config_and_models import LoadSeries2025
from ui_sandbox.Currentsituation_sandbox.engine.consumption_pipeline import MONTH_NAMES
from ui_sandbox.Currentsituation_sandbox.engine.status_quo_master import calculate_status_quo_master_2025
from ui_sandbox.Currentsituation_sandbox.contract.assumptions_banner import build_assumptions_register_dict


def _simulate_peaking_generator_2025(
    load: LoadSeries2025,
    grid_limit_kw: float,
    rated_power_kw: float,
    min_load_ratio_pct: float = 25.0,
    fuel_slope_per_kwh: float = 0.24,
    fuel_intercept_per_kw_rated: float = 0.04,
) -> Dict[str, Any]:
    """
    Simulates 35,040-step peaking generator dispatch triggered whenever P_Load(t) > grid_limit_kw:
      - Enforces minimum generator loading `P_min = rated_power_kw * (min_load_ratio_pct / 100)`
        when running (displacing additional grid import during active peaking intervals).
      - Computes exact fuel volume via Willans linear curve:
        Fuel_Rate (L/h or m³/h) = a * P_gen(t) + b * P_rated (when P_gen(t) > 0).
    """
    p_load = np.asarray(load.power_kw, dtype=float)
    dt = 0.25
    n_steps = len(p_load)

    p_excess = np.maximum(0.0, p_load - grid_limit_kw)
    active_mask = (p_excess > 0.0)
    min_gen_kw = rated_power_kw * (min_load_ratio_pct / 100.0)

    p_gen = np.zeros(n_steps, dtype=float)
    if rated_power_kw > 0.0:
        req_kw = np.where(active_mask, np.maximum(p_excess, min_gen_kw), 0.0)
        p_gen = np.minimum(rated_power_kw, np.minimum(p_load, req_kw))

    p_grid = np.maximum(0.0, p_load - p_gen)
    p_unmet_overload = np.maximum(0.0, p_grid - grid_limit_kw)

    # Fuel consumption per interval
    fuel_rate_per_hr = np.where(
        p_gen > 0.0,
        fuel_slope_per_kwh * p_gen + fuel_intercept_per_kw_rated * rated_power_kw,
        0.0,
    )
    fuel_units_step = fuel_rate_per_hr * dt

    # Count generator start events (transitions from 0 to >0)
    is_running = (p_gen > 0.0).astype(int)
    starts_count = int(np.sum(np.diff(np.concatenate(([0], is_running))) == 1))
    operating_hours = float(np.sum(is_running) * dt)
    gen_energy_kwh = float(np.sum(p_gen) * dt)
    total_fuel_units = float(np.sum(fuel_units_step))

    return {
        "p_load_kw": p_load,
        "p_gen_kw": p_gen,
        "p_grid_kw": p_grid,
        "p_unmet_kw": p_unmet_overload,
        "fuel_units_step": fuel_units_step,
        "operating_hours": operating_hours,
        "starts_count": starts_count,
        "gen_energy_kwh": gen_energy_kwh,
        "total_fuel_units": total_fuel_units,
        "load_kwh": float(np.sum(p_load) * dt),
        "grid_import_kwh": float(np.sum(p_grid) * dt),
        "peak_before_kw": float(np.max(p_load)),
        "peak_after_kw": float(np.max(p_grid)),
        "peak_shaved_kw": float(np.max(p_load) - np.max(p_grid)),
        "overload_hrs_before": float(np.sum(p_load > grid_limit_kw) * dt),
        "overload_hrs_after": float(np.sum(p_grid > grid_limit_kw + 1e-3) * dt),
        "unmet_energy_kwh": float(np.sum(p_unmet_overload) * dt),
    }


def render_generator_sandbox(key_prefix: str = "gen_sb") -> ScenarioEvaluationOutput:
    """Main orchestrator for Scenario 6: Standalone Peaking Generator & Grid Congestion Sandbox."""
    st.markdown(
        """
        <div style="background: linear-gradient(90deg, #0f172a 0%, #1e293b 100%);
                    border-left: 5px solid #ef4444; padding: 14px 20px; border-radius: 8px; margin-bottom: 12px;">
            <h3 style="margin:0; color:#f8fafc; font-size:1.25rem;">
                Scenario 6: Standalone Peaking Generator & Grid Congestion Sandbox
            </h3>
            <p style="margin:4px 0 0 0; color:#94a3b8; font-size:0.86rem;">
                Evaluates thermal/renewable peaking generator dispatch to bridge hard physical grid limits (Netcongestie)
                and eliminate DSO excess capacity penalties. Contrasts 4-Pillar grid bill savings directly against
                fuel/maintenance OPEX and compares <b>Purchase (CAPEX)</b> vs. <b>Rental/Leasing (OPEX)</b> over 15 years.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    base_load, base_config, site_label = render_standalone_baseline_control_bar(
        key_prefix=key_prefix,
        default_preset_idx=1,
    )
    curr = base_config.currency_code
    grid_limit_kw = base_config.dso.contracted_capacity_kw

    tabs = st.tabs(
        [
            ":material/warning: 1. Grid Constraint & Overload Analysis",
            ":material/local_gas_station: 2. Generator Sizing, Fuel Physics & Dispatch",
            ":material/receipt_long: 3. 4-Pillar Grid Bill Savings vs. Fuel Cost",
            ":material/account_balance: 4. Purchase CAPEX vs. Rental OPEX 15Y TCO",
        ]
    )

    excess_peak_kw = max(0.0, base_load.peak_demand_kw - grid_limit_kw)
    overload_hrs_base = float(np.sum(base_load.power_kw > grid_limit_kw) * 0.25)
    overload_kwh_base = float(np.sum(np.maximum(0.0, base_load.power_kw - grid_limit_kw)) * 0.25)

    # ----------------------------------------------------------------------------------
    # TAB 1: Grid Constraint & Overload Analysis
    # ----------------------------------------------------------------------------------
    with tabs[0]:
        st.markdown("#### :material/warning: Facility Overload & Peak Exceedance Profile")
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Measured Max Peak", f"{base_load.peak_demand_kw:,.1f} kW", f"Grid Limit: {grid_limit_kw:,.1f} kW", delta_color="off")
        k2.metric("Required Peaking Capacity", f"{excess_peak_kw:,.1f} kW", "To achieves 0.0 kW Breach", delta_color="inverse" if excess_peak_kw > 0 else "normal")
        k3.metric("Annual Overload Duration", f"{overload_hrs_base:,.2f} hrs/yr", f"{int(overload_hrs_base * 4)}x 15-min intervals")
        k4.metric("Annual Exceedance Energy", f"{overload_kwh_base:,.1f} kWh/yr", "Energy above P_contract")

        # Load duration curve above/below grid limit
        sorted_kw = np.sort(base_load.power_kw)[::-1]
        hours_axis = np.arange(1, len(sorted_kw) + 1) * 0.25
        fig_ldc = go.Figure()
        fig_ldc.add_trace(
            go.Scatter(x=hours_axis[:4000], y=sorted_kw[:4000], mode="lines", name="Load Duration Curve (Top 1,000 hrs)", fill="tozeroy", line=dict(color="#38bdf8", width=2.5))
        )
        fig_ldc.add_hline(y=grid_limit_kw, line_dash="dash", line_color="#ef4444", annotation_text=f"Contracted Grid Limit ({grid_limit_kw:,.0f} kW)")
        fig_ldc.update_layout(
            title=dict(text="<b>Top 1,000-Hour Load Duration Curve vs. Contracted Grid Limit</b>", x=0.01, y=0.98, xanchor="left"),
            template="plotly_dark",
            paper_bgcolor="rgba(15, 23, 42, 0.0)",
            plot_bgcolor="rgba(15, 23, 42, 0.55)",
            height=350,
            margin=dict(l=50, r=30, t=85, b=40),
            xaxis=dict(title="Operating Hours per Year (h)", gridcolor="#1e293b"),
            yaxis=dict(title="Facility Demand (kW)", gridcolor="#1e293b"),
        )
        st.plotly_chart(fig_ldc, use_container_width=True, key=f"{key_prefix}_ldc_chart")

    # ----------------------------------------------------------------------------------
    # TAB 2: Generator Sizing, Fuel Physics & Dispatch
    # ----------------------------------------------------------------------------------
    with tabs[1]:
        st.markdown("#### :material/local_gas_station: Peaking Generator Sizing, Willans Fuel Curve & 15-Min Dispatch")
        default_gen_kw = max(30.0, np.ceil(max(25.0, excess_peak_kw) / 10.0) * 10.0)

        g1, g2, g3 = st.columns(3)
        with g1:
            with st.container(border=True):
                st.markdown("##### :material/power: 1. Genset Rating & Min Load")
                gen_rated_kw = st.number_input(
                    "Generator Rated Capacity (kW)",
                    min_value=10.0,
                    max_value=10000.0,
                    value=float(default_gen_kw),
                    step=10.0,
                    key=f"{key_prefix}_rated_kw_{grid_limit_kw:.0f}",
                )
                min_load_pct = st.slider(
                    "Minimum Loading Ratio (% of Rated kW)",
                    min_value=10.0,
                    max_value=50.0,
                    value=25.0,
                    step=5.0,
                    key=f"{key_prefix}_min_load",
                    help="Prevents diesel wet-stacking / engine fouling when operating during shallow peaks.",
                )

        with g2:
            with st.container(border=True):
                st.markdown("##### :material/oil_barrel: 2. Fuel Type & Willans Curve")
                fuel_type = st.selectbox(
                    "Fuel Type",
                    options=["Diesel (Liters)", "HVO100 Renewable Biodiesel (Liters)", "Natural Gas (Nm³)"],
                    index=0,
                    key=f"{key_prefix}_fuel_type",
                )
                fuel_unit = "Nm³" if "Gas" in fuel_type else "Liters"
                fuel_slope = st.number_input(
                    f"Marginal Fuel Slope ({fuel_unit}/kWh)",
                    min_value=0.10,
                    max_value=0.60,
                    value=0.24,
                    step=0.01,
                    key=f"{key_prefix}_f_slope",
                )
                fuel_intercept = st.number_input(
                    f"No-Load Standby Intercept ({fuel_unit}/h per rated kW)",
                    min_value=0.0,
                    max_value=0.15,
                    value=0.04,
                    step=0.005,
                    format="%.3f",
                    key=f"{key_prefix}_f_int",
                )

        with g3:
            with st.container(border=True):
                st.markdown("##### :material/payments: 3. Fuel & Servicing Pricing")
                def_fuel_price = 1150.0 if curr == "ARS" else (1.85 if "HVO" in fuel_type else 1.55)
                def_maint_hr = 4500.0 if curr == "ARS" else 5.50
                fuel_price = st.number_input(
                    f"Fuel Price ({curr} per {fuel_unit})",
                    min_value=0.0,
                    value=float(def_fuel_price),
                    step=0.05 if curr != "ARS" else 50.0,
                    key=f"{key_prefix}_f_price_{curr}",
                )
                maint_per_hr = st.number_input(
                    f"Servicing & Lube Cost ({curr}/operating hour)",
                    min_value=0.0,
                    value=float(def_maint_hr),
                    step=0.5 if curr != "ARS" else 500.0,
                    key=f"{key_prefix}_m_hr_{curr}",
                )

        sim_gen = _simulate_peaking_generator_2025(
            load=base_load,
            grid_limit_kw=grid_limit_kw,
            rated_power_kw=gen_rated_kw,
            min_load_ratio_pct=min_load_pct,
            fuel_slope_per_kwh=fuel_slope,
            fuel_intercept_per_kw_rated=fuel_intercept,
        )

        annual_fuel_cost = sim_gen["total_fuel_units"] * fuel_price
        annual_maint_cost = sim_gen["operating_hours"] * maint_per_hr
        annual_var_gen_opex = annual_fuel_cost + annual_maint_cost

        d1, d2, d3, d4 = st.columns(4)
        d1.metric("Residual Grid Peak", f"{sim_gen['peak_after_kw']:,.1f} kW", f"-{sim_gen['peak_shaved_kw']:,.1f} kW shaved")
        d2.metric("Annual Operating Hours & Starts", f"{sim_gen['operating_hours']:,.1f} hrs/yr", f"{sim_gen['starts_count']} starts | {sim_gen['gen_energy_kwh']:,.0f} kWh gen")
        d3.metric(f"Annual Fuel Consumed ({fuel_unit})", f"{sim_gen['total_fuel_units']:,.1f} {fuel_unit}/yr", f"Fuel Cost: {curr} {annual_fuel_cost:,.0f}/yr", delta_color="inverse")
        d4.metric("Total Variable Genset OPEX", f"{curr} {annual_var_gen_opex:,.0f}/yr", f"Maint: {curr} {annual_maint_cost:,.0f}/yr", delta_color="inverse")

        # 7-Day Dispatch Window around peak
        peak_step = int(np.argmax(base_load.power_kw))
        s_idx = max(0, min(len(base_load.power_kw) - 96 * 7, peak_step - 96 * 2))
        e_idx = s_idx + 96 * 7
        ts_w = base_load.timestamps[s_idx:e_idx]

        fig_g = go.Figure()
        fig_g.add_trace(go.Scatter(x=ts_w, y=sim_gen["p_load_kw"][s_idx:e_idx], name="Facility Load P_Load (kW)", line=dict(color="#94a3b8", width=1.6)))
        fig_g.add_trace(go.Scatter(x=ts_w, y=sim_gen["p_grid_kw"][s_idx:e_idx], name="Clipped Grid Import P_Grid (kW)", line=dict(color="#38bdf8", width=2.4)))
        fig_g.add_trace(go.Scatter(x=ts_w, y=sim_gen["p_gen_kw"][s_idx:e_idx], name="Peaking Generator Output P_Gen (kW)", fill="tozeroy", line=dict(color="#ef4444", width=2.0), fillcolor="rgba(239, 68, 68, 0.25)"))
        fig_g.add_hline(y=grid_limit_kw, line_dash="dash", line_color="#f59e0b", annotation_text=f"Grid Limit ({grid_limit_kw:,.0f} kW)")
        fig_g.update_layout(
            title=dict(text="<b>15-Minute Peaking Generator Dispatch & Clipped Grid Import Profile</b>", x=0.01, y=0.98, xanchor="left"),
            template="plotly_dark",
            paper_bgcolor="rgba(15, 23, 42, 0.0)",
            plot_bgcolor="rgba(15, 23, 42, 0.55)",
            height=360,
            margin=dict(l=50, r=30, t=85, b=40),
            legend=dict(orientation="h", yanchor="bottom", y=1.08, xanchor="left", x=0.01),
            yaxis=dict(title="Active Power (kW)", gridcolor="#1e293b"),
        )
        st.plotly_chart(fig_g, use_container_width=True, key=f"{key_prefix}_disp_chart")

    residual_load = build_residual_load_series_2025(
        base_load=base_load,
        residual_power_kw=sim_gen["p_grid_kw"],
    )

    # ----------------------------------------------------------------------------------
    # TAB 3: 4-Pillar Grid Bill Savings vs. Fuel Cost
    # ----------------------------------------------------------------------------------
    with tabs[2]:
        period_options = ["Annual Statement 2025 (Full Year)"] + [
            f"2025-{m:02d} ({MONTH_NAMES[m - 1]})" for m in range(1, 13)
        ]
        sel_period = st.selectbox(
            ":material/calendar_month: Select Billing Statement Period",
            options=period_options,
            index=0,
            key=f"{key_prefix}_period_sel",
        )

        comp_data = evaluate_scenario_4pillar_bill_comparison(
            base_load=base_load,
            residual_load=residual_load,
            base_config=base_config,
            alt_config=base_config,
            period_choice=sel_period,
        )
        assumptions_dict = build_assumptions_register_dict(
            load_series=base_load,
            config=base_config,
            source_filename=site_label,
            bess_config=None,
        )
        physical_kpis = {
            "peak_before_kw": sim_gen["peak_before_kw"],
            "peak_after_kw": sim_gen["peak_after_kw"],
            "peak_shaved_kw": sim_gen["peak_shaved_kw"],
            "peak_shaved_pct": (sim_gen["peak_shaved_kw"] / max(1.0, sim_gen["peak_before_kw"]) * 100.0),
            "grid_limit_kw": grid_limit_kw,
            "overload_hrs_before": sim_gen["overload_hrs_before"],
            "overload_hrs_after": sim_gen["overload_hrs_after"],
            "remaining_deficit_kwh": sim_gen["unmet_energy_kwh"],
            "load_kwh": sim_gen["load_kwh"],
            "grid_import_kwh": sim_gen["grid_import_kwh"],
            "discharge_kwh": sim_gen["gen_energy_kwh"],
            "rte_loss_kwh": sim_gen["total_fuel_units"],
        }

        render_shared_4pillar_bill_comparison_ui(
            comp_data=comp_data,
            baseline_col_title="Baseline (No Generator)",
            scenario_col_title=f"With Genset ({gen_rated_kw:,.0f} kW)",
            site_name=site_label,
            assumptions_dict=assumptions_dict,
            physical_kpis=physical_kpis,
            key_prefix=key_prefix,
        )

    # ----------------------------------------------------------------------------------
    # TAB 4: Purchase CAPEX vs. Rental OPEX 15Y TCO
    # ----------------------------------------------------------------------------------
    with tabs[3]:
        st.markdown("#### :material/account_balance: Sub-Scenario Comparison: Generator Purchase (CAPEX) vs. Rental/Leasing (OPEX)")
        def_capex_kw = 280000.0 if curr == "ARS" else 280.0
        def_rent_mo = gen_rated_kw * (8500.0 if curr == "ARS" else 12.0)

        p1, p2, p3 = st.columns(3)
        with p1:
            acq_mode = st.radio(
                "Active Acquisition Sub-Scenario",
                options=[
                    "Option A: Generator Purchase (Turnkey CAPEX)",
                    "Option B: Generator Rental / Leasing (0 CAPEX, Monthly OPEX)",
                ],
                index=0,
                key=f"{key_prefix}_acq_mode",
            )
        with p2:
            purchase_capex = st.number_input(
                f"Option A: Purchase & Installation CAPEX ({curr})",
                min_value=0.0,
                value=float(gen_rated_kw * def_capex_kw),
                step=1000.0 if curr != "ARS" else 500000.0,
                key=f"{key_prefix}_pur_capex_{curr}",
            )
        with p3:
            monthly_lease = st.number_input(
                f"Option B: Monthly Rental / Lease Fee ({curr}/month)",
                min_value=0.0,
                value=float(def_rent_mo),
                step=100.0 if curr != "ARS" else 50000.0,
                key=f"{key_prefix}_rent_mo_{curr}",
            )

        res_base_full = calculate_status_quo_master_2025(load=base_load, config=base_config)
        res_after_full = calculate_status_quo_master_2025(load=residual_load, config=base_config)
        grid_bill_savings_net = res_base_full.total_status_quo_net - res_after_full.total_status_quo_net

        # Compute 15Y TCO for Status Quo, Option A (Purchase), and Option B (Rental)
        npv_sq, sched_sq = compute_15y_tco_npv(
            capex=0.0,
            annual_grid_bill_year1=res_base_full.total_status_quo_net,
            discount_rate_pct=base_config.discount_rate_pct,
            escalation_rate_pct=base_config.energy_escalation_pct,
        )
        npv_buy, sched_buy = compute_15y_tco_npv(
            capex=purchase_capex,
            annual_grid_bill_year1=res_after_full.total_status_quo_net,
            annual_tech_opex_year1=annual_var_gen_opex,
            discount_rate_pct=base_config.discount_rate_pct,
            escalation_rate_pct=base_config.energy_escalation_pct,
        )
        npv_rent, sched_rent = compute_15y_tco_npv(
            capex=0.0,
            annual_grid_bill_year1=res_after_full.total_status_quo_net,
            annual_tech_opex_year1=annual_var_gen_opex + (monthly_lease * 12.0),
            discount_rate_pct=base_config.discount_rate_pct,
            escalation_rate_pct=base_config.energy_escalation_pct,
        )

        fig_tco = go.Figure()
        fig_tco.add_trace(go.Scatter(x=[r["year"] for r in sched_sq], y=[r["cumulative_discounted"] for r in sched_sq], mode="lines+markers", name="Status Quo (Unmitigated Grid Bill)", line=dict(color="#ef4444", width=3, dash="dash")))
        fig_tco.add_trace(go.Scatter(x=[r["year"] for r in sched_buy], y=[r["cumulative_discounted"] for r in sched_buy], mode="lines+markers", name="Option A: Generator Purchase (CAPEX + Fuel)", line=dict(color="#10b981", width=3)))
        fig_tco.add_trace(go.Scatter(x=[r["year"] for r in sched_rent], y=[r["cumulative_discounted"] for r in sched_rent], mode="lines+markers", name="Option B: Generator Rental (Lease OPEX + Fuel)", line=dict(color="#f59e0b", width=3, dash="dot")))
        fig_tco.update_layout(
            title=dict(text="<b>15-Year Cumulative Discounted TCO: Status Quo vs. Generator Purchase vs. Generator Rental</b>", x=0.01, y=0.98, xanchor="left"),
            template="plotly_dark",
            paper_bgcolor="rgba(15, 23, 42, 0.0)",
            plot_bgcolor="rgba(15, 23, 42, 0.55)",
            height=370,
            margin=dict(l=50, r=30, t=85, b=40),
            xaxis=dict(title="Project Year", gridcolor="#1e293b"),
            yaxis=dict(title=f"Cumulative Discounted Cost ({curr})", gridcolor="#1e293b"),
        )
        st.plotly_chart(fig_tco, use_container_width=True, key=f"{key_prefix}_tco_chart")

        is_buy = "Option A" in acq_mode
        active_capex = purchase_capex if is_buy else 0.0
        active_opex = annual_var_gen_opex if is_buy else (annual_var_gen_opex + monthly_lease * 12.0)
        active_net_sav = grid_bill_savings_net - active_opex
        active_payback = (active_capex / active_net_sav) if (active_net_sav > 0 and active_capex > 0) else (0.0 if active_net_sav > 0 else 99.9)
        active_npv_after = npv_buy if is_buy else npv_rent

        scen_output = ScenarioEvaluationOutput(
            scenario_id="generator",
            scenario_name="Scenario 6: Peaking Generator & Congestion Bridging",
            sub_scenario_label=f"{gen_rated_kw:,.0f} kW {fuel_type.split(' ')[0]} ({'Purchase CAPEX' if is_buy else 'Rental OPEX'})",
            currency_code=curr,
            peak_before_kw=sim_gen["peak_before_kw"],
            peak_after_kw=sim_gen["peak_after_kw"],
            peak_shaved_kw=sim_gen["peak_shaved_kw"],
            peak_shaved_pct=(sim_gen["peak_shaved_kw"] / max(1.0, sim_gen["peak_before_kw"]) * 100.0),
            grid_limit_kw=grid_limit_kw,
            overload_hours_before=sim_gen["overload_hrs_before"],
            overload_hours_after=sim_gen["overload_hrs_after"],
            annual_load_kwh=sim_gen["load_kwh"],
            annual_grid_import_before_kwh=sim_gen["load_kwh"],
            annual_grid_import_after_kwh=sim_gen["grid_import_kwh"],
            self_consumption_pct=100.0,
            autarky_pct=(sim_gen["gen_energy_kwh"] / max(1.0, sim_gen["load_kwh"]) * 100.0),
            capex_total=float(active_capex),
            annual_tech_opex=float(active_opex),
            annual_grid_bill_net_before=float(res_base_full.total_status_quo_net),
            annual_grid_bill_net_after=float(res_after_full.total_status_quo_net),
            annual_grid_bill_gross_before=float(res_base_full.total_status_quo_gross),
            annual_grid_bill_gross_after=float(res_after_full.total_status_quo_gross),
            annual_net_savings=float(active_net_sav),
            simple_payback_years=float(active_payback),
            npv_15y_tco_before=float(npv_sq),
            npv_15y_tco_after=float(active_npv_after),
            npv_15y_net_benefit=float(npv_sq - active_npv_after),
        )
        render_scenario_evaluation_output_card(output=scen_output, key_prefix=key_prefix)

    return scen_output


def main() -> None:
    st.set_page_config(
        page_title="Peaking Generator Sandbox (Scenario 6)",
        page_icon=":material/local_gas_station:",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    render_generator_sandbox(key_prefix="gen_sb")


if __name__ == "__main__":
    main()

