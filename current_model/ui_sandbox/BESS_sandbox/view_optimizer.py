"""
========================================================================================
BESS Sandbox - Sizing Optimizer & Sensitivity Analysis View
(ui_sandbox/BESS_sandbox/view_optimizer.py)
========================================================================================

Description:
------------
Algorithmic sizing optimization and multi-variable financial sensitivity analysis:
  - Parametric capacity sweep across strategic size multiples (0.5x to 2.0x recommended).
  - Identification of Minimum Feasible Sizing vs. Maximum Economic NPV Sizing.
  - One-click application of optimal sizing parameters to the hardware form.
  - Multi-parameter sensitivity evaluation (CAPEX shifts, Demand Tariff escalation,
    Avoided Grid Upgrade CAPEX variations).
  - High-contrast Plotly sensitivity bar charts and interactive tradeoff tables.
"""

import os
import sys
from typing import Dict, Any, List, Optional
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
    from current_model.core.bess_engine import analyze_grid_violations, BESSSimulationResult
    from current_model.ui.tab4_bess.financial_charts import create_bess_sensitivity_figure
except ImportError:
    from models.bess import BESSConfig, BESSFinancialMetrics
    from core.bess_engine import analyze_grid_violations, BESSSimulationResult
    from ui.tab4_bess.financial_charts import create_bess_sensitivity_figure

from ui_sandbox.BESS_sandbox import baseline_presets as presets
from ui_sandbox.BESS_sandbox import sandbox_bess_engine as engine


def render_optimizer_tab(
    preset: presets.BaselinePreset,
    active_bess_config: BESSConfig,
    active_sim_result: Optional[BESSSimulationResult] = None
) -> None:
    """
    Renders the Sizing Optimizer and Sensitivity Analysis workspace.
    """
    st.subheader(":material/precision_manufacturing: BESS Sizing Optimizer & Sensitivity Analysis")
    st.caption(
        "Explore parametric sizing tradeoffs to determine the sweet spot between technical peak shaving reliability "
        "and maximum financial return on investment (NPV & Payback)."
    )

    load_df = preset.load_df
    power_col = "Total_Demand_kW" if "Total_Demand_kW" in load_df.columns else "P_Load_kW"
    grid_limit_kw = float(st.session_state.get("bess_sb_grid_limit_kw", preset.grid_limit_kw))
    currency = active_bess_config.currency or "EUR"

    # Pre-simulation diagnostics to baseline sizing
    diag = analyze_grid_violations(load_df[power_col], grid_limit_kw)
    sizing_rec = engine.compute_gross_minimum_bess_sizing(
        diag,
        round_trip_efficiency_pct=active_bess_config.round_trip_efficiency_pct,
        soc_min_pct=active_bess_config.soc_min_pct,
        soc_max_pct=active_bess_config.soc_max_pct,
        safety_margin_pct=10.0
    )

    # --- Section 1: Parametric Capacity Sweep ---
    st.markdown("#### :material/stacked_bar_chart: Parametric Capacity & Power Sweep")
    st.markdown(
        f"Evaluating 6 strategic sizing multiples centered around the gross recommendation "
        f"(`{sizing_rec.recommended_total_capacity_kwh:,.0f} kWh` / `{sizing_rec.recommended_inverter_power_kw:,.0f} kW`):"
    )

    multipliers = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]
    base_kwh = max(50.0, sizing_rec.recommended_total_capacity_kwh)
    base_kw = max(20.0, sizing_rec.recommended_inverter_power_kw)

    sweep_results: List[Dict[str, Any]] = []

    with st.spinner("Running parametric dispatch simulation sweep..."):
        for m in multipliers:
            cand_kwh = round(base_kwh * m, 0)
            cand_kw = round(base_kw * min(1.5, max(0.6, m)), 0)
            cand_units = max(1, int(np.ceil(cand_kwh / active_bess_config.unit_capacity_kwh)))

            cand_cfg = BESSConfig(
                capacity_kwh=cand_kwh,
                unit_count=cand_units,
                unit_capacity_kwh=active_bess_config.unit_capacity_kwh,
                battery_chemistry=active_bess_config.battery_chemistry,
                max_charge_power_kw=cand_kw,
                max_discharge_power_kw=cand_kw,
                round_trip_efficiency_pct=active_bess_config.round_trip_efficiency_pct,
                soc_min_pct=active_bess_config.soc_min_pct,
                soc_max_pct=active_bess_config.soc_max_pct,
                initial_soc_pct=active_bess_config.soc_max_pct,
                max_dod_pct=active_bess_config.max_dod_pct,
                dispatch_strategy="peak_shaving",
                peak_shaving_threshold_kw=grid_limit_kw,
                allow_grid_charging=True,
                currency=currency,
                cost_per_kwh=active_bess_config.cost_per_kwh,
                fixed_installation_cost=active_bess_config.fixed_installation_cost,
                annual_om_pct=active_bess_config.annual_om_pct,
                cell_replacement_year=active_bess_config.cell_replacement_year,
                cell_replacement_cost_pct=active_bess_config.cell_replacement_cost_pct
            )

            sim = engine.simulate_sandbox_bess_dispatch(
                bess_config=cand_cfg,
                load_df=load_df,
                grid_limit_kw=grid_limit_kw,
                step_hours=0.25,
                power_col=power_col
            )

            res_peak = float(sim.diagnostics_after.get("peak_load_kw", 0.0))
            res_overload = float(sim.diagnostics_after.get("overload_peak_kw", 0.0))
            res_hours = float(sim.diagnostics_after.get("total_violation_hours", 0.0))
            is_feasible = (res_overload <= 0.1) and (res_hours <= 0.1)

            econ = engine.evaluate_sandbox_bess_economics(
                bess_config=cand_cfg,
                sim_result=sim,
                contract_baseline=preset.contract_baseline,
                contract_bess=preset.contract_bess,
                avoided_grid_upgrade_capex=float(st.session_state.get("bess_sb_avoided_upgrade_capex", preset.avoided_grid_upgrade_capex)),
                avoided_monthly_transformer_rent=float(st.session_state.get("bess_sb_avoided_trans_rent", preset.avoided_monthly_transformer_rent)),
                analysis_horizon_years=15,
                discount_rate_pct=float(st.session_state.get("bess_sb_discount_rate", 5.0)),
                electricity_price_inflation_pct=float(st.session_state.get("bess_sb_inflation", 2.0)),
                ambient_temperature_c=25.0,
                step_hours=0.25
            )

            sweep_results.append({
                "Multiplier": f"{m:.2f}x",
                "Capacity (kWh)": cand_kwh,
                "Inverter (kW)": cand_kw,
                "Residual Peak (kW)": round(res_peak, 1),
                "Feasibility": "100% Shaved" if is_feasible else f"{res_overload:.1f} kW Overload",
                "Is Feasible": is_feasible,
                "Turnkey CAPEX": round(cand_cfg.total_capex, 0),
                "Annual Gross Savings": round(econ.annual_gross_savings, 0),
                "Simple Payback (Yrs)": econ.simple_payback_years if econ.simple_payback_years is not None else 999.0,
                "15Y NPV": round(econ.net_present_value, 0),
                "IRR (%)": econ.internal_rate_of_return_pct if econ.internal_rate_of_return_pct is not None else -99.0,
                "config_obj": cand_cfg
            })

    df_sweep = pd.DataFrame(sweep_results)

    # Identify sweet spot configurations
    feasible_cands = [r for r in sweep_results if r["Is Feasible"]]
    min_feasible = feasible_cands[0] if feasible_cands else None
    best_npv = max(sweep_results, key=lambda r: r["15Y NPV"]) if sweep_results else None

    # Highlight summary cards
    sc1, sc2, sc3 = st.columns(3)
    with sc1:
        if min_feasible:
            st.success(
                f"**:material/check_circle: Minimum Feasible Sizing**\n\n"
                f"- **Capacity:** `{min_feasible['Capacity (kWh)']:,.0f} kWh` ({min_feasible['Multiplier']})\n"
                f"- **PCS Inverter:** `{min_feasible['Inverter (kW)']:,.0f} kW`\n"
                f"- **Turnkey CAPEX:** `{min_feasible['Turnkey CAPEX']:,.0f} {currency}`\n"
                f"- **Payback:** `{min_feasible['Simple Payback (Yrs)']:.1f} Years`"
            )
        else:
            st.warning("No candidate in range achieved 100% shave. Increase base multiplier.")

    with sc2:
        if best_npv:
            st.info(
                f"**:material/trending_up: Optimal Economic Sizing (Max NPV)**\n\n"
                f"- **Capacity:** `{best_npv['Capacity (kWh)']:,.0f} kWh` ({best_npv['Multiplier']})\n"
                f"- **PCS Inverter:** `{best_npv['Inverter (kW)']:,.0f} kW`\n"
                f"- **15Y NPV:** `{best_npv['15Y NPV']:,.0f} {currency}`\n"
                f"- **Status:** {'Feasible (100% Shaved)' if best_npv['Is Feasible'] else 'Undersized'}"
            )
        else:
            st.info("Calculating optimal sizing...")

    with sc3:
        st.markdown("**Apply to Simulation Form:**")
        if min_feasible and st.button(":material/check: Apply Minimum Feasible Size", use_container_width=True):
            st.session_state["bess_sb_unit_count"] = min_feasible["config_obj"].unit_count
            st.session_state["bess_sb_unit_kwh"] = min_feasible["config_obj"].unit_capacity_kwh
            st.session_state["bess_sb_discharge_kw"] = min_feasible["config_obj"].max_discharge_power_kw
            st.session_state["bess_sb_charge_kw"] = min_feasible["config_obj"].max_charge_power_kw
            st.rerun()

        if best_npv and st.button(":material/star: Apply Optimal Economic Size", use_container_width=True):
            st.session_state["bess_sb_unit_count"] = best_npv["config_obj"].unit_count
            st.session_state["bess_sb_unit_kwh"] = best_npv["config_obj"].unit_capacity_kwh
            st.session_state["bess_sb_discharge_kw"] = best_npv["config_obj"].max_discharge_power_kw
            st.session_state["bess_sb_charge_kw"] = best_npv["config_obj"].max_charge_power_kw
            st.rerun()

    # Formatted display table
    display_cols = [
        "Multiplier", "Capacity (kWh)", "Inverter (kW)", "Feasibility",
        "Turnkey CAPEX", "Annual Gross Savings", "Simple Payback (Yrs)", "15Y NPV"
    ]
    st.dataframe(
        df_sweep[display_cols].style.format({
            "Capacity (kWh)": "{:,.0f}",
            "Inverter (kW)": "{:,.0f}",
            "Turnkey CAPEX": "{:,.0f} " + currency,
            "Annual Gross Savings": "{:,.0f} " + currency,
            "Simple Payback (Yrs)": lambda v: f"{v:.1f} Yrs" if v < 90 else ">15 Yrs",
            "15Y NPV": "{:,.0f} " + currency
        }),
        use_container_width=True
    )

    st.markdown("---")

    # --- Section 2: Multi-Parameter Sensitivity Analysis ---
    st.markdown("#### :material/tune: Financial Sensitivity Tornado Analysis")
    st.caption(
        "Evaluate the stability of the investment amortization (Simple Payback) under ±10% and ±20% variations "
        "in battery CAPEX, avoided grid upgrade CAPEX, and monthly peak demand tariffs."
    )

    if active_sim_result is None:
        st.info("Run technical simulation in Tab 1 to activate sensitivity model.")
        return

    base_capex_per_kwh = float(active_bess_config.cost_per_kwh or 420.0)
    base_avoided_upgrade = float(st.session_state.get("bess_sb_avoided_upgrade_capex", preset.avoided_grid_upgrade_capex))
    base_demand_tariff = float(preset.contract_baseline.demand_capacity_tariff or 3.50)

    variations = [
        ("-20%", -0.20),
        ("-10%", -0.10),
        ("Base (0%)", 0.0),
        ("+10%", 0.10),
        ("+20%", 0.20)
    ]

    sensitivity_rows: List[Dict[str, Any]] = []

    for v_lbl, v_val in variations:
        # Parameter 1: BESS CAPEX
        cfg_mod = BESSConfig(
            capacity_kwh=active_bess_config.capacity_kwh,
            unit_count=active_bess_config.unit_count,
            unit_capacity_kwh=active_bess_config.unit_capacity_kwh,
            battery_chemistry=active_bess_config.battery_chemistry,
            max_charge_power_kw=active_bess_config.max_charge_power_kw,
            max_discharge_power_kw=active_bess_config.max_discharge_power_kw,
            round_trip_efficiency_pct=active_bess_config.round_trip_efficiency_pct,
            soc_min_pct=active_bess_config.soc_min_pct,
            soc_max_pct=active_bess_config.soc_max_pct,
            initial_soc_pct=active_bess_config.initial_soc_pct,
            max_dod_pct=active_bess_config.max_dod_pct,
            dispatch_strategy=active_bess_config.dispatch_strategy,
            peak_shaving_threshold_kw=active_bess_config.peak_shaving_threshold_kw,
            allow_grid_charging=active_bess_config.allow_grid_charging,
            currency=currency,
            cost_per_kwh=base_capex_per_kwh * (1.0 + v_val),
            fixed_installation_cost=active_bess_config.fixed_installation_cost,
            annual_om_pct=active_bess_config.annual_om_pct,
            cell_replacement_year=active_bess_config.cell_replacement_year,
            cell_replacement_cost_pct=active_bess_config.cell_replacement_cost_pct
        )
        econ_capex = engine.evaluate_sandbox_bess_economics(
            bess_config=cfg_mod,
            sim_result=active_sim_result,
            contract_baseline=preset.contract_baseline,
            contract_bess=preset.contract_bess,
            avoided_grid_upgrade_capex=base_avoided_upgrade,
            avoided_monthly_transformer_rent=float(st.session_state.get("bess_sb_avoided_trans_rent", preset.avoided_monthly_transformer_rent)),
            analysis_horizon_years=15,
            discount_rate_pct=float(st.session_state.get("bess_sb_discount_rate", 5.0)),
            electricity_price_inflation_pct=float(st.session_state.get("bess_sb_inflation", 2.0)),
            ambient_temperature_c=25.0,
            step_hours=0.25
        )
        sensitivity_rows.append({
            "parameter": "BESS CAPEX (€/kWh)",
            "variation_pct": v_lbl,
            "variation_val": v_val,
            "payback_years": econ_capex.simple_payback_years if econ_capex.simple_payback_years is not None else 15.0,
            "npv": econ_capex.net_present_value
        })

        # Parameter 2: Avoided Grid Upgrade CAPEX
        econ_upgrade = engine.evaluate_sandbox_bess_economics(
            bess_config=active_bess_config,
            sim_result=active_sim_result,
            contract_baseline=preset.contract_baseline,
            contract_bess=preset.contract_bess,
            avoided_grid_upgrade_capex=max(0.0, base_avoided_upgrade * (1.0 + v_val)),
            avoided_monthly_transformer_rent=float(st.session_state.get("bess_sb_avoided_trans_rent", preset.avoided_monthly_transformer_rent)),
            analysis_horizon_years=15,
            discount_rate_pct=float(st.session_state.get("bess_sb_discount_rate", 5.0)),
            electricity_price_inflation_pct=float(st.session_state.get("bess_sb_inflation", 2.0)),
            ambient_temperature_c=25.0,
            step_hours=0.25
        )
        sensitivity_rows.append({
            "parameter": "Avoided Grid Upgrade CAPEX (€)",
            "variation_pct": v_lbl,
            "variation_val": v_val,
            "payback_years": econ_upgrade.simple_payback_years if econ_upgrade.simple_payback_years is not None else 15.0,
            "npv": econ_upgrade.net_present_value
        })

        # Parameter 3: Capacity & Demand Tariff Rate
        c_base_mod = presets.Contract(
            name=preset.contract_baseline.name,
            currency=currency,
            contracted_capacity_kw=preset.contract_baseline.contracted_capacity_kw,
            monthly_capacity_tariff=preset.contract_baseline.monthly_capacity_tariff * (1.0 + v_val),
            demand_capacity_tariff=base_demand_tariff * (1.0 + v_val),
            peak_penalty_rate=preset.contract_baseline.peak_penalty_rate,
            default_energy_rate=preset.contract_baseline.default_energy_rate,
            base_monthly_fee=preset.contract_baseline.base_monthly_fee,
            taxes_and_fees=preset.contract_baseline.taxes_and_fees
        )
        econ_tariff = engine.evaluate_sandbox_bess_economics(
            bess_config=active_bess_config,
            sim_result=active_sim_result,
            contract_baseline=c_base_mod,
            contract_bess=preset.contract_bess,
            avoided_grid_upgrade_capex=base_avoided_upgrade,
            avoided_monthly_transformer_rent=float(st.session_state.get("bess_sb_avoided_trans_rent", preset.avoided_monthly_transformer_rent)),
            analysis_horizon_years=15,
            discount_rate_pct=float(st.session_state.get("bess_sb_discount_rate", 5.0)),
            electricity_price_inflation_pct=float(st.session_state.get("bess_sb_inflation", 2.0)),
            ambient_temperature_c=25.0,
            step_hours=0.25
        )
        sensitivity_rows.append({
            "parameter": "Monthly Demand Tariff Rate (€/kW)",
            "variation_pct": v_lbl,
            "variation_val": v_val,
            "payback_years": econ_tariff.simple_payback_years if econ_tariff.simple_payback_years is not None else 15.0,
            "npv": econ_tariff.net_present_value
        })

    # Render sensitivity chart
    fig_sens = create_bess_sensitivity_figure(sensitivity_rows, metric="payback_years")
    st.plotly_chart(fig_sens, use_container_width=True)
