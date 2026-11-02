"""
========================================================================================
Scenario 5: Standalone Hybrid Solar PV + BESS Sandbox (ui_sandbox/SolarBESS_sandbox/app.py)
========================================================================================

Standalone Execution:
    python -m streamlit run "ui_sandbox/SolarBESS_sandbox/app.py"

Evaluates the combined "Double Lever" of Solar PV (volumetric kWh self-consumption) +
BESS (peak-shaving kW & solar surplus buffering) coupled with the 4-Pillar Billing Engine:
  - Tab 1: Baseline Load, Grid Limit & Solar Site Parameters
  - Tab 2: Combined PV + BESS Sizing & Operating Strategy Sub-Scenarios:
      * Strategy A (Peak-Shaving Priority): Reserves battery capacity strictly to cap P_Grid(t) <= P_limit
      * Strategy B (Max Self-Consumption + Peak-Shaving Hybrid): Stores midday PV surplus into BESS
        to displace evening HT/Pico grid import while also clipping demand peaks above P_limit
      * Synchronized 2-in-1 Power Flow & SoC Chart
  - Tab 3: Side-by-Side 4-Pillar Electricity Bill Comparison (Double Lever: Volumetric kWh + Peak kW) + PDF
  - Tab 4: Combined Turnkey CAPEX, Payback, 15Y TCO & Standardized `ScenarioEvaluationOutput`
========================================================================================
"""

import os
import sys
from typing import Dict, List, Any, Tuple
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
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
from ui_sandbox.Solar_sandbox.solar_sandbox_engine import (
    SOLAR_CLIMATE_PRESETS,
    generate_normalized_solar_unit_profile_2025,
)


def _simulate_hybrid_solar_bess_2025(
    load: LoadSeries2025,
    unit_pv_kw: np.ndarray,
    pv_kwp: float,
    bess_capacity_kwh: float,
    bess_power_kw: float,
    grid_limit_kw: float,
    strategy: str = "hybrid_self_cons_and_peak",
    soc_min_pct: float = 10.0,
    soc_max_pct: float = 90.0,
    rte_pct: float = 88.0,
) -> Dict[str, Any]:
    """
    Fast 35,040-step coupled Solar PV + BESS simulation supporting:
      - `peak_shaving_priority` (Strategy A): BESS charges from solar surplus first (or off-peak grid)
        and discharges ONLY when net load (P_Load - P_PV) exceeds `grid_limit_kw`.
      - `hybrid_self_cons_and_peak` (Strategy B): BESS stores midday solar surplus and discharges
        both to shave peaks above `grid_limit_kw` AND to cover remaining post-solar load (especially
        in afternoon/evening Pico/HT hours).
    """
    n_steps = len(load.power_kw)
    dt = 0.25
    p_load = np.asarray(load.power_kw, dtype=float)
    p_pv = np.asarray(unit_pv_kw, dtype=float) * max(0.0, float(pv_kwp))

    p_direct = np.minimum(p_load, p_pv)
    p_pv_surplus = np.maximum(0.0, p_pv - p_direct)
    p_rem_load = np.maximum(0.0, p_load - p_direct)

    eta_chg = np.sqrt(max(0.50, min(1.0, rte_pct / 100.0)))
    eta_dis = eta_chg
    soc_min_kwh = bess_capacity_kwh * (soc_min_pct / 100.0)
    soc_max_kwh = bess_capacity_kwh * (soc_max_pct / 100.0)
    soc_kwh = soc_max_kwh * 0.65 if strategy == "peak_shaving_priority" else soc_min_kwh

    p_bess_chg_pv = np.zeros(n_steps, dtype=float)
    p_bess_chg_grid = np.zeros(n_steps, dtype=float)
    p_bess_dis = np.zeros(n_steps, dtype=float)
    p_grid_import = np.zeros(n_steps, dtype=float)
    p_grid_export = np.zeros(n_steps, dtype=float)
    soc_trace_kwh = np.zeros(n_steps, dtype=float)

    for t in range(n_steps):
        rem_l = p_rem_load[t]
        surp_pv = p_pv_surplus[t]
        headroom_grid = max(0.0, grid_limit_kw - rem_l)

        if strategy == "peak_shaving_priority":
            # 1. If net load exceeds grid limit, discharge BESS to cap at grid_limit_kw
            if rem_l > grid_limit_kw:
                needed_kw = rem_l - grid_limit_kw
                max_dis_soc = max(0.0, (soc_kwh - soc_min_kwh) * eta_dis / dt)
                dis_kw = min(needed_kw, bess_power_kw, max_dis_soc)
                soc_kwh -= (dis_kw * dt) / eta_dis
                p_bess_dis[t] = dis_kw
                p_grid_import[t] = rem_l - dis_kw
                p_grid_export[t] = 0.0
            else:
                # 2. Recharge BESS from PV surplus first, then from grid headroom up to soc_max_kwh
                max_chg_soc = max(0.0, (soc_max_kwh - soc_kwh) / (eta_chg * dt))
                chg_pv_kw = min(surp_pv, bess_power_kw, max_chg_soc)
                soc_kwh += chg_pv_kw * dt * eta_chg
                p_bess_chg_pv[t] = chg_pv_kw
                p_grid_export[t] = surp_pv - chg_pv_kw

                rem_chg_cap = max(0.0, min(bess_power_kw - chg_pv_kw, (soc_max_kwh - soc_kwh) / (eta_chg * dt)))
                chg_grid_kw = min(rem_chg_cap, headroom_grid * 0.5)
                soc_kwh += chg_grid_kw * dt * eta_chg
                p_bess_chg_grid[t] = chg_grid_kw
                p_grid_import[t] = rem_l + chg_grid_kw
        else:
            # Strategy B: Hybrid Max Self-Consumption + Peak Shaving
            # Reserve a dynamic peak buffer (25% of usable capacity) for peak shaving, use rest for self-consumption
            peak_reserve_kwh = soc_min_kwh + 0.25 * (soc_max_kwh - soc_min_kwh)
            if surp_pv > 0.0:
                # Charge from solar surplus
                max_chg_soc = max(0.0, (soc_max_kwh - soc_kwh) / (eta_chg * dt))
                chg_pv_kw = min(surp_pv, bess_power_kw, max_chg_soc)
                soc_kwh += chg_pv_kw * dt * eta_chg
                p_bess_chg_pv[t] = chg_pv_kw
                p_grid_export[t] = surp_pv - chg_pv_kw
                p_grid_import[t] = 0.0
            else:
                if rem_l > grid_limit_kw:
                    # Must shave peak! Can use down to soc_min_kwh + also cover sub-limit if surplus SoC
                    needed_peak_kw = rem_l - grid_limit_kw
                    # If SoC is above peak_reserve_kwh, also discharge to reduce grid import
                    target_dis_kw = rem_l if soc_kwh > peak_reserve_kwh else needed_peak_kw
                    max_dis_soc = max(0.0, (soc_kwh - soc_min_kwh) * eta_dis / dt)
                    dis_kw = min(target_dis_kw, bess_power_kw, max_dis_soc)
                    soc_kwh -= (dis_kw * dt) / eta_dis
                    p_bess_dis[t] = dis_kw
                    p_grid_import[t] = rem_l - dis_kw
                else:
                    # Below grid limit: discharge solar-charged SoC above peak_reserve_kwh to maximize self-consumption
                    if soc_kwh > peak_reserve_kwh:
                        max_dis_sc = max(0.0, (soc_kwh - peak_reserve_kwh) * eta_dis / dt)
                        dis_kw = min(rem_l, bess_power_kw, max_dis_sc)
                        soc_kwh -= (dis_kw * dt) / eta_dis
                        p_bess_dis[t] = dis_kw
                        p_grid_import[t] = rem_l - dis_kw
                    elif soc_kwh < peak_reserve_kwh and headroom_grid > 10.0:
                        # Top up reserve buffer gently from grid headroom
                        max_chg_res = max(0.0, (peak_reserve_kwh - soc_kwh) / (eta_chg * dt))
                        chg_grid_kw = min(max_chg_res, bess_power_kw * 0.3, headroom_grid * 0.4)
                        soc_kwh += chg_grid_kw * dt * eta_chg
                        p_bess_chg_grid[t] = chg_grid_kw
                        p_grid_import[t] = rem_l + chg_grid_kw
                    else:
                        p_grid_import[t] = rem_l

        soc_trace_kwh[t] = soc_kwh

    load_kwh = float(np.sum(p_load) * dt)
    pv_kwh = float(np.sum(p_pv) * dt)
    direct_kwh = float(np.sum(p_direct) * dt)
    bess_dis_kwh = float(np.sum(p_bess_dis) * dt)
    bess_chg_pv_kwh = float(np.sum(p_bess_chg_pv) * dt)
    bess_chg_grid_kwh = float(np.sum(p_bess_chg_grid) * dt)
    grid_import_kwh = float(np.sum(p_grid_import) * dt)
    grid_export_kwh = float(np.sum(p_grid_export) * dt)

    total_solar_utilized_kwh = direct_kwh + bess_chg_pv_kwh * (eta_chg * eta_dis)
    scr_pct = (min(pv_kwh, direct_kwh + bess_chg_pv_kwh) / pv_kwh * 100.0) if pv_kwh > 0 else 0.0
    autarky_pct = (max(0.0, load_kwh - grid_import_kwh) / load_kwh * 100.0) if load_kwh > 0 else 0.0

    return {
        "p_load_kw": p_load,
        "p_pv_kw": p_pv,
        "p_direct_kw": p_direct,
        "p_bess_chg_kw": p_bess_chg_pv + p_bess_chg_grid,
        "p_bess_dis_kw": p_bess_dis,
        "p_grid_import_kw": p_grid_import,
        "p_grid_export_kw": p_grid_export,
        "soc_kwh": soc_trace_kwh,
        "load_kwh": load_kwh,
        "pv_kwh": pv_kwh,
        "direct_kwh": direct_kwh,
        "bess_dis_kwh": bess_dis_kwh,
        "bess_chg_pv_kwh": bess_chg_pv_kwh,
        "bess_chg_grid_kwh": bess_chg_grid_kwh,
        "grid_import_kwh": grid_import_kwh,
        "grid_export_kwh": grid_export_kwh,
        "total_solar_utilized_kwh": total_solar_utilized_kwh,
        "self_consumption_pct": scr_pct,
        "autarky_pct": autarky_pct,
        "peak_before_kw": float(np.max(p_load)),
        "peak_after_kw": float(np.max(p_grid_import)),
        "peak_shaved_kw": float(np.max(p_load) - np.max(p_grid_import)),
        "overload_hrs_before": float(np.sum(p_load > grid_limit_kw) * dt),
        "overload_hrs_after": float(np.sum(p_grid_import > grid_limit_kw + 1e-3) * dt),
    }


def render_solar_bess_sandbox(key_prefix: str = "solbess_sb") -> ScenarioEvaluationOutput:
    """Main orchestrator for Scenario 5: Standalone Hybrid Solar PV + BESS Sandbox."""
    st.markdown(
        """
        <div style="background: linear-gradient(90deg, #0f172a 0%, #1e293b 100%);
                    border-left: 5px solid #10b981; padding: 14px 20px; border-radius: 8px; margin-bottom: 12px;">
            <h3 style="margin:0; color:#f8fafc; font-size:1.25rem;">
                Scenario 5: Standalone Hybrid Solar PV + BESS Sandbox (The Double Lever)
            </h3>
            <p style="margin:4px 0 0 0; color:#94a3b8; font-size:0.86rem;">
                Combines <b>Solar PV</b> (volumetric kWh bill reduction) with <b>Battery Energy Storage</b>
                (peak demand shaving kW + midday PV surplus shifting into evening high-tariff windows).
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    base_load, base_config, site_label = render_standalone_baseline_control_bar(
        key_prefix=key_prefix,
        default_preset_idx=0,
    )
    curr = base_config.currency_code
    grid_limit_kw = base_config.dso.contracted_capacity_kw

    tabs = st.tabs(
        [
            ":material/bolt: 1. Baseline Overload & Solar Site Parameters",
            ":material/battery_charging_full: 2. Combined PV + BESS Sizing & Operating Strategies",
            ":material/receipt_long: 3. 4-Pillar Bill Comparison (Double Lever)",
            ":material/account_balance: 4. Combined Investment, Payback & 15Y TCO",
        ]
    )

    # ----------------------------------------------------------------------------------
    # TAB 1: Baseline Overload & Solar Site Parameters
    # ----------------------------------------------------------------------------------
    default_clim_idx = 1 if curr == "ARS" else 0
    climate_keys = list(SOLAR_CLIMATE_PRESETS.keys())

    with tabs[0]:
        st.markdown("#### :material/bolt: Baseline Grid Overload & Solar Irradiance Setup")
        c1, c2 = st.columns([1.2, 1.0])
        with c1:
            clim_choice = st.selectbox(
                "Regional Solar Climate Preset",
                options=climate_keys,
                index=default_clim_idx,
                key=f"{key_prefix}_clim",
            )
            clim_meta = SOLAR_CLIMATE_PRESETS[clim_choice]
            s1, s2, s3 = st.columns(3)
            tilt_deg = s1.number_input("Tilt (deg)", 0.0, 60.0, float(clim_meta["default_tilt_deg"]), 1.0, key=f"{key_prefix}_tilt")
            az_deg = s2.number_input("Azimuth (deg)", 0.0, 360.0, float(clim_meta["default_azimuth_deg"]), 5.0, key=f"{key_prefix}_az")
            tech_choice = s3.selectbox("PV Tech", ["TOPCon", "Backcontact", "PERC"], index=0, key=f"{key_prefix}_tech")

        unit_pv_kw, spec_yield = generate_normalized_solar_unit_profile_2025(
            timestamps=base_load.timestamps,
            latitude=float(clim_meta["latitude"]),
            tilt_deg=tilt_deg,
            azimuth_deg=az_deg,
            technology=tech_choice,
        )

        with c2:
            excess_kw = max(0.0, base_load.peak_demand_kw - grid_limit_kw)
            ov_hrs = float(np.sum(base_load.power_kw > grid_limit_kw) * 0.25)
            st.metric("Baseline Peak vs. Limit", f"{base_load.peak_demand_kw:,.1f} kW", f"Excess: +{excess_kw:,.1f} kW ({ov_hrs:.1f} hrs/yr)", delta_color="inverse" if excess_kw > 0 else "normal")
            st.metric("Regional Solar Specific Yield", f"{spec_yield:,.0f} kWh/kWp/yr", f"Annual Facility Demand: {base_load.total_energy_kwh:,.0f} kWh")

    # ----------------------------------------------------------------------------------
    # TAB 2: Combined PV + BESS Sizing & Operating Strategies
    # ----------------------------------------------------------------------------------
    with tabs[1]:
        st.markdown("#### :material/battery_charging_full: Combined PV + BESS Sizing & Dispatch Strategy Comparison")

        default_pv_kwp = round((base_load.total_energy_kwh / max(800.0, spec_yield)) * 0.65, -1)
        default_bess_kw = max(25.0, round(max(20.0, base_load.peak_demand_kw - grid_limit_kw) * 1.15, 0))
        default_bess_kwh = round(default_bess_kw * 2.5, -1)

        cfg_c1, cfg_c2, cfg_c3 = st.columns(3)
        with cfg_c1:
            with st.container(border=True):
                st.markdown("##### :material/wb_sunny: Solar PV Sizing")
                pv_kwp = st.number_input(
                    "Solar PV Capacity (kWp DC)",
                    min_value=10.0,
                    max_value=25000.0,
                    value=float(default_pv_kwp),
                    step=10.0,
                    key=f"{key_prefix}_pv_kwp",
                )
        with cfg_c2:
            with st.container(border=True):
                st.markdown("##### :material/battery_full: BESS Sizing")
                bess_kwh = st.number_input(
                    "BESS Nominal Capacity (kWh)",
                    min_value=10.0,
                    max_value=50000.0,
                    value=float(default_bess_kwh),
                    step=25.0,
                    key=f"{key_prefix}_bess_kwh",
                )
                bess_kw = st.number_input(
                    "BESS Inverter Max Power (kW)",
                    min_value=5.0,
                    max_value=25000.0,
                    value=float(default_bess_kw),
                    step=10.0,
                    key=f"{key_prefix}_bess_kw",
                )
        with cfg_c3:
            with st.container(border=True):
                st.markdown("##### :material/psychology: Operating Strategy")
                strat_choice = st.radio(
                    "Active BESS Dispatch Mode",
                    options=[
                        "Strategy B: Max Self-Consumption + Peak-Shaving (Double Lever)",
                        "Strategy A: Strict Peak-Shaving Priority (Reserve for Peaks)",
                    ],
                    index=0,
                    key=f"{key_prefix}_strat",
                )
                active_strat_code = "hybrid_self_cons_and_peak" if "Strategy B" in strat_choice else "peak_shaving_priority"

        # Run both strategies for side-by-side sub-scenario comparison
        sim_strat_a = _simulate_hybrid_solar_bess_2025(
            load=base_load,
            unit_pv_kw=unit_pv_kw,
            pv_kwp=pv_kwp,
            bess_capacity_kwh=bess_kwh,
            bess_power_kw=bess_kw,
            grid_limit_kw=grid_limit_kw,
            strategy="peak_shaving_priority",
        )
        sim_strat_b = _simulate_hybrid_solar_bess_2025(
            load=base_load,
            unit_pv_kw=unit_pv_kw,
            pv_kwp=pv_kwp,
            bess_capacity_kwh=bess_kwh,
            bess_power_kw=bess_kw,
            grid_limit_kw=grid_limit_kw,
            strategy="hybrid_self_cons_and_peak",
        )
        sim_active = sim_strat_b if active_strat_code == "hybrid_self_cons_and_peak" else sim_strat_a

        # Strategy Sub-Scenario Table
        st.markdown("##### :material/compare: Operating Strategy Sub-Scenario Comparison")
        strat_df = pd.DataFrame(
            [
                {
                    "Operating Strategy Sub-Scenario": "Strategy A: Strict Peak-Shaving Priority",
                    "Residual Peak (kW)": f"{sim_strat_a['peak_after_kw']:,.1f}",
                    "Overload Hours (h/yr)": f"{sim_strat_a['overload_hrs_after']:,.2f}",
                    "PV Direct + BESS Solar Used (kWh)": f"{sim_strat_a['total_solar_utilized_kwh']:,.0f}",
                    "Self-Consumption Rate (SCR %)": f"{sim_strat_a['self_consumption_pct']:.1f}%",
                    "Facility Autarky (%)": f"{sim_strat_a['autarky_pct']:.1f}%",
                    "Residual Grid Import (kWh)": f"{sim_strat_a['grid_import_kwh']:,.0f}",
                },
                {
                    "Operating Strategy Sub-Scenario": "Strategy B: Max Self-Consumption + Peak-Shaving (Double Lever)",
                    "Residual Peak (kW)": f"{sim_strat_b['peak_after_kw']:,.1f}",
                    "Overload Hours (h/yr)": f"{sim_strat_b['overload_hrs_after']:,.2f}",
                    "PV Direct + BESS Solar Used (kWh)": f"{sim_strat_b['total_solar_utilized_kwh']:,.0f}",
                    "Self-Consumption Rate (SCR %)": f"{sim_strat_b['self_consumption_pct']:.1f}%",
                    "Facility Autarky (%)": f"{sim_strat_b['autarky_pct']:.1f}%",
                    "Residual Grid Import (kWh)": f"{sim_strat_b['grid_import_kwh']:,.0f}",
                },
            ]
        )
        st.dataframe(strat_df, use_container_width=True, hide_index=True)

        # Synchronized 2-in-1 Power Flow & SoC Chart (7-day window around peak demand)
        peak_step = int(np.argmax(base_load.power_kw))
        s_idx = max(0, min(len(base_load.power_kw) - 96 * 7, peak_step - 96 * 2))
        e_idx = s_idx + 96 * 7
        ts_w = base_load.timestamps[s_idx:e_idx]

        fig_sync = make_subplots(
            rows=2,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.08,
            row_heights=[0.65, 0.35],
            subplot_titles=("15-Minute Power Flows (Facility Load, Solar PV, BESS & Residual Grid Import)", "Battery State of Charge (SoC kWh)"),
        )
        fig_sync.add_trace(
            go.Scatter(x=ts_w, y=sim_active["p_load_kw"][s_idx:e_idx], name="Facility Load (kW)", line=dict(color="#94a3b8", width=1.6)),
            row=1,
            col=1,
        )
        fig_sync.add_trace(
            go.Scatter(x=ts_w, y=sim_active["p_pv_kw"][s_idx:e_idx], name="Solar PV Output (kW)", line=dict(color="#f59e0b", width=2.0)),
            row=1,
            col=1,
        )
        fig_sync.add_trace(
            go.Scatter(x=ts_w, y=sim_active["p_grid_import_kw"][s_idx:e_idx], name="Residual Grid Import P_Grid (kW)", line=dict(color="#38bdf8", width=2.4)),
            row=1,
            col=1,
        )
        fig_sync.add_hline(y=grid_limit_kw, line_dash="dash", line_color="#ef4444", row=1, col=1)

        fig_sync.add_trace(
            go.Scatter(
                x=ts_w,
                y=sim_active["soc_kwh"][s_idx:e_idx],
                name="BESS SoC (kWh)",
                fill="tozeroy",
                line=dict(color="#10b981", width=2.2),
                fillcolor="rgba(16, 185, 129, 0.20)",
            ),
            row=2,
            col=1,
        )
        fig_sync.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(15, 23, 42, 0.0)",
            plot_bgcolor="rgba(15, 23, 42, 0.55)",
            height=480,
            margin=dict(l=50, r=30, t=65, b=40),
            legend=dict(orientation="h", yanchor="bottom", y=1.06, xanchor="left", x=0.01),
        )
        st.plotly_chart(fig_sync, use_container_width=True, key=f"{key_prefix}_sync_chart")

    residual_load = build_residual_load_series_2025(
        base_load=base_load,
        residual_power_kw=sim_active["p_grid_import_kw"],
    )

    # ----------------------------------------------------------------------------------
    # TAB 3: 4-Pillar Bill Comparison (Double Lever)
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
            "peak_before_kw": sim_active["peak_before_kw"],
            "peak_after_kw": sim_active["peak_after_kw"],
            "peak_shaved_kw": sim_active["peak_shaved_kw"],
            "peak_shaved_pct": (sim_active["peak_shaved_kw"] / max(1.0, sim_active["peak_before_kw"]) * 100.0),
            "grid_limit_kw": grid_limit_kw,
            "overload_hrs_before": sim_active["overload_hrs_before"],
            "overload_hrs_after": sim_active["overload_hrs_after"],
            "remaining_deficit_kwh": 0.0,
            "load_kwh": sim_active["load_kwh"],
            "grid_import_kwh": sim_active["grid_import_kwh"],
            "discharge_kwh": sim_active["bess_dis_kwh"] + sim_active["direct_kwh"],
            "rte_loss_kwh": max(0.0, (sim_active["bess_chg_pv_kwh"] + sim_active["bess_chg_grid_kwh"]) - sim_active["bess_dis_kwh"]),
        }

        render_shared_4pillar_bill_comparison_ui(
            comp_data=comp_data,
            baseline_col_title="Baseline (Status Quo)",
            scenario_col_title=f"Solar ({pv_kwp:.0f} kWp) + BESS ({bess_kwh:.0f} kWh)",
            site_name=site_label,
            assumptions_dict=assumptions_dict,
            physical_kpis=physical_kpis,
            key_prefix=key_prefix,
        )

    # ----------------------------------------------------------------------------------
    # TAB 4: Combined Investment, Payback & 15Y TCO
    # ----------------------------------------------------------------------------------
    with tabs[3]:
        st.markdown("#### :material/account_balance: Combined Hybrid PV + BESS Turnkey CAPEX & 15-Year TCO")
        fc1, fc2, fc3 = st.columns(3)
        def_pv_capex = 850000.0 if curr == "ARS" else 880.0
        def_bess_capex = 420000.0 if curr == "ARS" else 420.0
        def_om_pct = 1.5

        with fc1:
            pv_capex_unit = st.number_input(f"Solar PV CAPEX ({curr}/kWp)", 0.0, value=float(def_pv_capex), step=25.0, key=f"{key_prefix}_pv_cap_{curr}")
        with fc2:
            bess_capex_unit = st.number_input(f"BESS Turnkey CAPEX ({curr}/kWh)", 0.0, value=float(def_bess_capex), step=25.0, key=f"{key_prefix}_bess_cap_{curr}")
        with fc3:
            om_pct_capex = st.number_input("Combined Annual O&M (% of CAPEX/yr)", 0.0, 10.0, float(def_om_pct), 0.25, key=f"{key_prefix}_om_pct")

        res_base_full = calculate_status_quo_master_2025(load=base_load, config=base_config)
        res_after_full = calculate_status_quo_master_2025(load=residual_load, config=base_config)

        total_capex = pv_kwp * pv_capex_unit + bess_kwh * bess_capex_unit
        annual_om = total_capex * (om_pct_capex / 100.0)
        bill_savings_net = res_base_full.total_status_quo_net - res_after_full.total_status_quo_net
        annual_net_savings = bill_savings_net - annual_om
        payback_yrs = (total_capex / annual_net_savings) if annual_net_savings > 0 else 99.9

        npv_before, sched_before = compute_15y_tco_npv(
            capex=0.0,
            annual_grid_bill_year1=res_base_full.total_status_quo_net,
            discount_rate_pct=base_config.discount_rate_pct,
            escalation_rate_pct=base_config.energy_escalation_pct,
        )
        npv_after, sched_after = compute_15y_tco_npv(
            capex=total_capex,
            annual_grid_bill_year1=res_after_full.total_status_quo_net,
            annual_tech_opex_year1=annual_om,
            discount_rate_pct=base_config.discount_rate_pct,
            escalation_rate_pct=base_config.energy_escalation_pct,
            replacement_year=11,
            replacement_cost=bess_kwh * bess_capex_unit * 0.45,
        )

        fig_tco = go.Figure()
        fig_tco.add_trace(
            go.Scatter(x=[r["year"] for r in sched_before], y=[r["cumulative_discounted"] for r in sched_before], mode="lines+markers", name="Status Quo (Grid Only)", line=dict(color="#ef4444", width=3, dash="dash"))
        )
        fig_tco.add_trace(
            go.Scatter(x=[r["year"] for r in sched_after], y=[r["cumulative_discounted"] for r in sched_after], mode="lines+markers", name=f"Hybrid PV ({pv_kwp:.0f} kWp) + BESS ({bess_kwh:.0f} kWh)", line=dict(color="#10b981", width=3))
        )
        fig_tco.update_layout(
            title=dict(text="<b>15-Year Cumulative Discounted TCO: Status Quo vs. Hybrid Solar + BESS</b>", x=0.01, y=0.98, xanchor="left"),
            template="plotly_dark",
            paper_bgcolor="rgba(15, 23, 42, 0.0)",
            plot_bgcolor="rgba(15, 23, 42, 0.55)",
            height=360,
            margin=dict(l=50, r=30, t=85, b=40),
            xaxis=dict(title="Project Year", gridcolor="#1e293b"),
            yaxis=dict(title=f"Cumulative Discounted Cost ({curr})", gridcolor="#1e293b"),
        )
        st.plotly_chart(fig_tco, use_container_width=True, key=f"{key_prefix}_tco_chart")

        scen_output = ScenarioEvaluationOutput(
            scenario_id="solar_bess",
            scenario_name="Scenario 5: Hybrid Solar PV + BESS",
            sub_scenario_label=f"{pv_kwp:.0f} kWp PV + {bess_kwh:.0f} kWh/{bess_kw:.0f} kW BESS ({active_strat_code})",
            currency_code=curr,
            peak_before_kw=sim_active["peak_before_kw"],
            peak_after_kw=sim_active["peak_after_kw"],
            peak_shaved_kw=sim_active["peak_shaved_kw"],
            peak_shaved_pct=(sim_active["peak_shaved_kw"] / max(1.0, sim_active["peak_before_kw"]) * 100.0),
            grid_limit_kw=grid_limit_kw,
            overload_hours_before=sim_active["overload_hrs_before"],
            overload_hours_after=sim_active["overload_hrs_after"],
            annual_load_kwh=sim_active["load_kwh"],
            annual_grid_import_before_kwh=sim_active["load_kwh"],
            annual_grid_import_after_kwh=sim_active["grid_import_kwh"],
            self_consumption_pct=sim_active["self_consumption_pct"],
            autarky_pct=sim_active["autarky_pct"],
            capex_total=float(total_capex),
            annual_tech_opex=float(annual_om),
            annual_grid_bill_net_before=float(res_base_full.total_status_quo_net),
            annual_grid_bill_net_after=float(res_after_full.total_status_quo_net),
            annual_grid_bill_gross_before=float(res_base_full.total_status_quo_gross),
            annual_grid_bill_gross_after=float(res_after_full.total_status_quo_gross),
            annual_net_savings=float(annual_net_savings),
            simple_payback_years=float(payback_yrs),
            npv_15y_tco_before=float(npv_before),
            npv_15y_tco_after=float(npv_after),
            npv_15y_net_benefit=float(npv_before - npv_after),
        )
        render_scenario_evaluation_output_card(output=scen_output, key_prefix=key_prefix)

    return scen_output


def main() -> None:
    st.set_page_config(
        page_title="Hybrid Solar PV + BESS Sandbox (Scenario 5)",
        page_icon=":material/battery_charging_full:",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    render_solar_bess_sandbox(key_prefix="solbess_sb")


if __name__ == "__main__":
    main()

