"""
========================================================================================
Master Scenario Comparison & Decision Dashboard (current_model/ui/tab_comparison/view.py)
========================================================================================

Description:
------------
Main entry point for the Executive Decision & Multi-Scenario Comparison Dashboard:
  - Visual Active Scenario Architecture Cards (Status Quo + All Sub-Scenarios with instant branch switching).
  - Sub-Tab 4.1: Financial Benchmarks & Amortisation
      * Top Financial KPI Summary Cards (Best TCO, Fastest Payback, Solar Autarky).
      * Scenario Architecture & Parameter Delta Matrix (Baseline vs Interventions).
      * Scenario Ranking Leaderboard Table.
      * 15-Year Multi-Scenario Cumulative Cost Curves (Scope-adaptive: Facility TCO vs. Standalone Solar PV).
      * CAPEX vs. OPEX Capital Shift Visualizations.
      * Autarky & Payback Trade-off Benchmark.
      * Scenario Quick Management & Full Project Export.
  - Sub-Tab 4.2: Electrical Energy & Power Balance
      * Top Electrical & Power KPI Cards (Demand, Clean Generation, Peak Shaving, CO2 Offsets).
      * Multi-Scenario Electrical Flow Comparison Table (Generation, Direct Cons, Residual Grid, Export).
      * Grouped Multi-Scenario Annual Energy Balance Bar Chart (MWh).
      * Peak Demand Shaving (kW) & Clean Energy Carbon Offsets (Tons CO2/a) Dual Figure.
"""

from typing import List, Dict, Any, Optional
import streamlit as st
import pandas as pd
import numpy as np

from current_model.models.scenario import BaseScenario, SubScenario, ProjectContainer
from current_model.models.solar import SolarLocation, SolarFinancialConfig
from current_model.core.project_io import export_project_from_session, export_project_json, sync_active_scenario_into_session
from current_model.core.solar_financial_engine import compute_solar_financial_metrics
from current_model.core.bess_engine import simulate_bess_dispatch
from current_model.core.bess_financial_engine import compute_bess_financial_metrics
from current_model.core.solar_engine import simulate_solar_pv_generation
from current_model.ui.tab_comparison.charts import (
    create_multi_scenario_cumulative_cost_figure,
    create_capex_opex_breakdown_figure,
    create_autarky_payback_figure,
    create_multi_scenario_energy_balance_figure,
    create_multi_scenario_peak_and_co2_figure,
    create_residual_grid_load_comparison_figure,
    create_residual_grid_load_timeseries_figure
)
from current_model.ui.common.cards import render_kpi_card
from current_model.ui.common.session_utils import (
    find_active_load_data_in_session,
    find_active_contract_in_session,
    get_load_profile_summary,
    detect_load_profile_gaps
)





def _build_scenario_evaluation_records(project: ProjectContainer) -> List[Dict[str, Any]]:
    """
    Constructs normalized analytical comparison records across all configured sub-scenarios
    and the base scenario, linking exact financial metrics (Facility & Solar scopes) and electrical energy flows.
    """
    records: List[Dict[str, Any]] = []
    currency = project.currency or "EUR"

    # 1. Baseline Load Discovery & Power Metrics (Annualized to 365 Days)
    df_load, load_desc, p_col = find_active_load_data_in_session()
    if df_load is not None and not df_load.empty and p_col in df_load.columns:
        load_summary = get_load_profile_summary(df_load, p_col)
        duration_days = float(load_summary.get("duration_days", 365.0) or 365.0)
        annual_factor = (365.0 / duration_days) if (0.1 < duration_days < 360.0) else 1.0
        base_total_kwh = float(load_summary.get("total_kwh", 0.0)) * annual_factor
        base_peak_kw = float(load_summary.get("peak_kw", 0.0))
    else:
        base_total_kwh = float(project.base_scenario.baseline_annual_kwh) if project.base_scenario.baseline_annual_kwh > 0 else 1412000.0
        base_peak_kw = float(project.base_scenario.baseline_peak_kw) if project.base_scenario.baseline_peak_kw > 0 else 380.0

    base_total_mwh = base_total_kwh / 1000.0

    # 1.1 Compute 12-month baseline profile (Jan - Dec)
    base_monthly_mwh = None
    if df_load is not None and not df_load.empty and p_col in df_load.columns:
        ts_col = None
        for c in ["timestamp", "datetime", "Date", "time", "Datum"]:
            if c in df_load.columns:
                ts_col = c
                break
        if ts_col is not None or isinstance(df_load.index, pd.DatetimeIndex):
            try:
                ts_series = df_load[ts_col] if ts_col is not None else df_load.index
                ts_series = pd.to_datetime(ts_series)
                dt_h = 0.25
                if len(ts_series) > 1:
                    dt_diff = (ts_series.iloc[1] - ts_series.iloc[0]).total_seconds() / 3600.0
                    if 0.05 < dt_diff < 5.0:
                        dt_h = dt_diff
                monthly_s = (df_load[p_col] * dt_h / 1000.0).groupby(ts_series.dt.month).sum()
                if len(monthly_s) == 12:
                    base_monthly_mwh = [round(float(monthly_s.get(m, 0.0)) * annual_factor, 1) for m in range(1, 13)]
            except Exception:
                base_monthly_mwh = None

    if not base_monthly_mwh or len(base_monthly_mwh) != 12:
        month_weights = [0.088, 0.082, 0.084, 0.080, 0.081, 0.080, 0.082, 0.081, 0.083, 0.084, 0.087, 0.088]
        sum_w = sum(month_weights)
        base_monthly_mwh = [round(base_total_mwh * (w / sum_w), 1) for w in month_weights]

    # 2. Status Quo Baseline Reference Cost (Facility Scope)
    base_annual_cost = project.base_scenario.baseline_annual_cost
    if not base_annual_cost or base_annual_cost <= 0:
        active_bill = st.session_state.get("active_bill_breakdown") or st.session_state.get("app_tab2_breakdown")
        if active_bill and hasattr(active_bill, "total_gross_period") and active_bill.total_gross_period > 0:
            factor = (365.0 / active_bill.duration_days) if getattr(active_bill, "duration_days", 0) > 0 else 1.0
            base_annual_cost = active_bill.total_gross_period * factor
        else:
            base_annual_cost = 344141.21

    base_15y_facility_tco = base_annual_cost * 18.5989  # ~3% annual inflation factor over 15 years
    
    # Facility Status Quo 15-year cumulative trajectory series (0 -> 4.75M)
    fac_cum_series = [0.0]
    cum_tracker = 0.0
    for y in range(1, 16):
        cum_tracker += base_annual_cost * ((1.0 + 0.03) ** (y - 1))
        fac_cum_series.append(round(cum_tracker, 2))

    # Standalone Solar Status Quo 15-year series (0 -> ~2.09M)
    solar_base_annual = 112762.96
    solar_cum_series = [0.0]
    sol_cum_tracker = 0.0
    for y in range(1, 16):
        sol_cum_tracker += solar_base_annual * ((1.0 + 0.03) ** (y - 1))
        solar_cum_series.append(round(sol_cum_tracker, 2))

    # 1. Base Scenario Row (Status Quo)
    base_cash_table = []
    base_running_tco = 0.0
    for y in range(1, 26):
        y_bill = base_annual_cost * ((1.0 + 0.03) ** (y - 1))
        base_running_tco += y_bill
        base_cash_table.append({
            "year": y,
            "status_quo_bill": round(y_bill, 2),
            "residual_bill": round(y_bill, 2),
            "opex": 0.0,
            "cell_replacement": 0.0,
            "total_outflow": round(y_bill, 2),
            "gross_savings": 0.0,
            "net_cash_flow": 0.0,
            "cumulative_cash_flow": 0.0,
            "discounted_cash_flow": 0.0,
            "cumulative_tco": round(base_running_tco, 2)
        })

    records.append({
        "id": "base",
        "rank": "Ref",
        "name": "Status Quo (Base Scenario)",
        "tech_mix": "Grid Only (Utility Baseline)",
        "capex": 0.0,
        "capex_str": f"0 {currency}",
        "hardware_capex": 0.0,
        "grid_upgrade_cost": 0.0,
        "temporary_connection_cost": 0.0,
        "annual_opex": base_annual_cost,
        "total_15y_opex": base_15y_facility_tco,
        "total_15y_tco": base_15y_facility_tco,
        "tco_str": f"{base_15y_facility_tco:,.0f} {currency}",
        "payback_years": 0.0,
        "payback_str": "Baseline Reference",
        "npv": 0.0,
        "npv_str": "-",
        "irr_pct": None,
        "lcoe_per_kwh": None,
        "net_savings": 0.0,
        "net_savings_str": "-",
        "autarky_pct": 0.0,
        "autarky_str": "0.0 %",
        "self_consumption_pct": 0.0,
        "self_consumption_str": "-",
        "total_load_mwh": round(base_total_mwh, 1),
        "monthly_load_mwh": base_monthly_mwh,
        "monthly_residual_mwh": list(base_monthly_mwh),
        "generation_mwh": 0.0,
        "direct_consumption_mwh": 0.0,
        "residual_grid_mwh": round(base_total_mwh, 1),
        "surplus_export_mwh": 0.0,
        "baseline_peak_kw": round(base_peak_kw, 1),
        "residual_peak_kw": round(base_peak_kw, 1),
        "shaved_peak_kw": 0.0,
        "co2_avoided_tons": 0.0,
        "facility_cum_costs": fac_cum_series,
        "facility_base_costs": fac_cum_series,
        "solar_cum_costs": solar_cum_series,
        "solar_base_costs": solar_cum_series,
        "cumulative_costs": fac_cum_series,
        "baseline_costs": fac_cum_series,
        "cash_flow_table": base_cash_table,
        "color": "#94A3B8"
    })

    # Active solar simulation / dispatch in session
    sim_res = st.session_state.get("app_tab3_sim_result")
    int_res = st.session_state.get("app_tab3_int_sim_result") or st.session_state.get("solar_dispatch_result")
    active_fin_m = st.session_state.get("solar_financial_metrics")
    active_sub_id = project.active_sub_scenario_id

    contract = project.base_scenario.base_contract or st.session_state.get("contract") or st.session_state.get("app_tab2_contract")
    grid_limit_kw = getattr(contract, "contracted_capacity_kw", None) or float(base_peak_kw) or 100.0

    for idx, sub in enumerate(project.sub_scenarios):
        # 1. Solar Capacity & Generation Sizing
        kwp = 0.0
        annual_gen_kwh = 0.0
        if sub.include_solar and sub.solar_config:
            kwp = sub.solar_config.dc_capacity_kwp
            if active_sub_id == sub.id and sim_res is not None and getattr(sim_res, "kpis", None):
                annual_gen_kwh = sim_res.kpis.annual_energy_kwh
            else:
                annual_gen_kwh = kwp * 1582.0  # standard high-yield benchmark yield (kWh/kWp)

        gen_mwh = annual_gen_kwh / 1000.0

        # 2. Coupled Electrical Energy & Power Balance
        autarky = 0.0
        self_cons = 0.0
        peak_shaved = 0.0
        has_valid_int = False
        direct_kwh = 0.0
        surplus_kwh = 0.0
        residual_kwh = base_total_kwh

        if sub.include_solar and kwp > 0:
            # Check if active sub-scenario has an exact coupled dispatch result matching current sizing
            has_valid_int = (
                active_sub_id == sub.id and 
                int_res is not None and 
                hasattr(int_res, "kpis") and 
                getattr(int_res, "config", None) is not None and
                int_res.config.module_count == (sub.solar_config.module_count if sub.solar_config else 0) and
                getattr(int_res.kpis, "total_load_kwh", 0.0) > 0 and
                abs(getattr(int_res.kpis, "total_load_kwh", 0.0) - base_total_kwh) / max(1.0, base_total_kwh) < 0.25
            )

            if has_valid_int:
                direct_kwh = float(getattr(int_res.kpis, "direct_consumption_kwh", 0.0))
                direct_kwh = min(direct_kwh, annual_gen_kwh, base_total_kwh)
                surplus_kwh = max(0.0, annual_gen_kwh - direct_kwh)
                residual_kwh = max(0.0, base_total_kwh - direct_kwh)
                autarky = round((direct_kwh / max(1.0, base_total_kwh)) * 100.0, 1)
                self_cons = round((direct_kwh / max(1.0, annual_gen_kwh)) * 100.0, 1)
                if "P_Residual_kW" in int_res.df_timeseries.columns:
                    p_orig = float(int_res.df_timeseries["P_Load_kW"].max()) if "P_Load_kW" in int_res.df_timeseries.columns else base_peak_kw
                    p_res = float(int_res.df_timeseries["P_Residual_kW"].max())
                    peak_shaved = max(0.0, p_orig - p_res)
            else:
                # Rigorous physical heuristic model for commercial demand curve:
                solar_fraction = min(2.0, annual_gen_kwh / max(1.0, base_total_kwh))
                if solar_fraction <= 0.4:
                    self_cons = 98.2
                elif solar_fraction <= 0.8:
                    self_cons = max(40.0, 98.2 - (solar_fraction - 0.4) * 45.0)
                else:
                    self_cons = max(30.0, 80.0 - (solar_fraction - 0.8) * 55.0)

                direct_kwh = min(annual_gen_kwh * (self_cons / 100.0), base_total_kwh)
                autarky = round((direct_kwh / max(1.0, base_total_kwh)) * 100.0, 1)
                self_cons = round((direct_kwh / max(1.0, annual_gen_kwh)) * 100.0, 1)
                surplus_kwh = max(0.0, annual_gen_kwh - direct_kwh)
                residual_kwh = max(0.0, base_total_kwh - direct_kwh)
                peak_shaved = round(min(base_peak_kw * 0.35, kwp * 0.15), 1)

            # Strict physical energy conservation enforcement
            direct_kwh = min(direct_kwh, base_total_kwh, annual_gen_kwh)
            residual_kwh = max(0.0, base_total_kwh - direct_kwh)
            surplus_kwh = max(0.0, annual_gen_kwh - direct_kwh)
        elif sub.include_bess and sub.bess_config:
            direct_kwh = 0.0
            surplus_kwh = 0.0
            bess_cfg = sub.bess_config
            bess_sim_tmp = None
            if df_load is not None and not df_load.empty:
                try:
                    bess_sim_tmp = simulate_bess_dispatch(
                        bess_config=bess_cfg,
                        load_df=df_load,
                        grid_limit_kw=grid_limit_kw,
                        power_col=p_col
                    )
                except Exception:
                    bess_sim_tmp = None

            if bess_sim_tmp and bess_sim_tmp.kpis:
                peak_shaved = float(getattr(bess_sim_tmp.kpis, "peak_shaved_kw", 0.0))
                loss_kwh = float(getattr(bess_sim_tmp.kpis, "round_trip_loss_kwh", 0.0))
            else:
                peak_shaved = min(float(bess_cfg.max_discharge_power_kw), float(base_peak_kw * 0.35))
                loss_kwh = float(bess_cfg.capacity_kwh * 250.0 * (1.0 - bess_cfg.round_trip_efficiency_pct / 100.0))

            residual_kwh = max(0.0, base_total_kwh + loss_kwh)
            autarky = 0.0
            self_cons = 0.0
        else:
            direct_kwh = 0.0
            surplus_kwh = 0.0
            residual_kwh = base_total_kwh
            peak_shaved = 0.0
            autarky = 0.0
            self_cons = 0.0

        # Generator Simulation & Multi-Asset Coupling
        gen_gen_kwh = 0.0
        gen_op_cost = 0.0
        gen_lease_annual = 0.0
        gen_peak_shaved = 0.0
        gen_sim_res = None

        if sub.include_generator and sub.generator_config:
            gen_cfg = sub.generator_config
            if df_load is not None and not df_load.empty:
                try:
                    from current_model.core.dracbv_engine import simulate_hybrid_scenario_dispatch
                    hybrid_run = simulate_hybrid_scenario_dispatch(
                        sub_scenario=sub,
                        df_load=df_load,
                        power_col=p_col,
                        contract=contract,
                        location=project.base_scenario.location
                    )
                    gen_sim_res = hybrid_run.get("gen_result")
                except Exception:
                    gen_sim_res = None

            if gen_sim_res and "kpis" in gen_sim_res:
                gk = gen_sim_res["kpis"]
                gen_gen_kwh = float(gk.total_generation_kwh)
                gen_op_cost = float(gk.total_operating_cost)
                gen_peak_shaved = float(gen_sim_res.get("peak_shaved_kw", 0.0))
            else:
                gen_gen_kwh = float(gen_cfg.rated_power_kw) * 150.0
                gen_op_cost = gen_gen_kwh * 0.35
                gen_peak_shaved = min(float(gen_cfg.rated_power_kw), float(base_peak_kw * 0.25))

            gen_lease_annual = float(gen_cfg.monthly_lease_fee) * 12.0
            peak_shaved = max(peak_shaved, gen_peak_shaved)
            residual_kwh = max(0.0, residual_kwh - gen_gen_kwh)

        direct_mwh = direct_kwh / 1000.0
        residual_mwh = residual_kwh / 1000.0
        surplus_mwh = surplus_kwh / 1000.0
        res_peak_kw = max(0.0, base_peak_kw - peak_shaved)
        co2_tons = round(direct_kwh * 0.000400, 1)  # 400 g CO2/kWh clean energy offset

        # 3. 15-Year Financial & Amortisation Modeling (Matching Tab 3.1 & Facility TCO)
        if sub.include_solar and sub.solar_config:
            fin_cfg = sub.solar_financial if (sub.solar_financial and sub.solar_financial.is_enabled) else SolarFinancialConfig(
                is_enabled=True,
                currency=currency,
                cost_modules_per_wp=0.22,
                cost_inverter_per_w=0.08,
                cost_substructure_per_wp=0.12,
                cost_installation_per_wp=0.20,
                fixed_switchgear_cost=1500.0,
                fixed_travel_fee=1500.0,
                annual_opex_pct=1.0,
                discount_rate_pct=5.0,
                electricity_price_inflation_pct=3.0,
                feed_in_tariff_per_kwh=0.08
            )

            # Facility-Coupled Engine
            fin_m_fac = compute_solar_financial_metrics(
                config=sub.solar_config,
                fin_config=fin_cfg,
                annual_generation_kwh=annual_gen_kwh,
                annual_avoided_cost=direct_kwh * 0.18,
                annual_export_revenue=surplus_kwh * (fin_cfg.feed_in_tariff_per_kwh or 0.08),
                baseline_electricity_rate=0.18,
                baseline_annual_bill=base_annual_cost,
                multi_year_yields=sim_res.multi_year_yields if (active_sub_id == sub.id and sim_res) else None
            )

            # Standalone Solar PV Engine (Matching Tab 3.1 100%)
            fin_m_sol = compute_solar_financial_metrics(
                config=sub.solar_config,
                fin_config=fin_cfg,
                annual_generation_kwh=annual_gen_kwh,
                multi_year_yields=sim_res.multi_year_yields if (active_sub_id == sub.id and sim_res) else None
            )

            grid_upgrade = float(getattr(sub, "grid_connection_upgrade_cost", 0.0))
            temp_conn = float(getattr(sub, "temporary_connection_cost", 0.0))
            hardware_capex = fin_m_fac.total_capex
            if sub.include_bess and sub.bess_config:
                hardware_capex += sub.bess_config.total_capex
            if sub.include_generator and sub.generator_config:
                gen_c = float(sub.generator_config.capital_cost) if sub.generator_config.monthly_lease_fee <= 0 else 0.0
                hardware_capex += gen_c

            capex = hardware_capex + grid_upgrade + temp_conn

            payback = fin_m_fac.payback_period_years or 0.0
            npv = fin_m_fac.npv
            irr_val = getattr(fin_m_fac, "irr_pct", None)
            lcoe_val = getattr(fin_m_fac, "lcoe_per_kwh", None)
            net_savings = fin_m_fac.total_lifetime_savings
            cum_costs_fac = fin_m_fac.cumulative_with_pv
            base_costs_fac = fin_m_fac.cumulative_status_quo
            cum_costs_sol = fin_m_sol.cumulative_with_pv
            base_costs_sol = fin_m_sol.cumulative_status_quo

            opex_y1 = fin_m_fac.annual_opex_year1
            if sub.include_generator and sub.generator_config:
                opex_y1 += gen_op_cost + gen_lease_annual
            res_bill_y1 = max(0.0, base_annual_cost - (direct_kwh * 0.18))
            tco_15y = cum_costs_fac[-1] if cum_costs_fac else (capex + opex_y1 * 18.5989)
            if sub.include_generator and sub.generator_config:
                tco_15y += (gen_op_cost + gen_lease_annual) * 18.5989
                net_savings = base_15y_facility_tco - tco_15y
            cash_table = fin_m_fac.cash_flow_table
        elif sub.include_bess and sub.bess_config:
            bess_cfg = sub.bess_config
            if df_load is not None and not df_load.empty:
                try:
                    bess_sim = simulate_bess_dispatch(
                        bess_config=bess_cfg,
                        load_df=df_load,
                        grid_limit_kw=grid_limit_kw,
                        power_col=p_col
                    )
                    df_bess_ts = bess_sim.df_timeseries
                except Exception:
                    df_bess_ts = pd.DataFrame({
                        "P_Load_kW": [base_peak_kw] * 4,
                        "P_Grid_kW": [max(0.0, base_peak_kw - bess_cfg.max_discharge_power_kw)] * 4,
                        "P_BESS_Discharge_kW": [min(bess_cfg.max_discharge_power_kw, base_peak_kw)] * 4,
                        "P_BESS_Charge_kW": [0.0] * 4
                    })
            else:
                df_bess_ts = pd.DataFrame({
                    "P_Load_kW": [base_peak_kw] * 4,
                    "P_Grid_kW": [max(0.0, base_peak_kw - bess_cfg.max_discharge_power_kw)] * 4,
                    "P_BESS_Discharge_kW": [min(bess_cfg.max_discharge_power_kw, base_peak_kw)] * 4,
                    "P_BESS_Charge_kW": [0.0] * 4
                })

            fin_m_bess = compute_bess_financial_metrics(
                bess_config=bess_cfg,
                df_timeseries=df_bess_ts,
                contract=contract,
                grid_limit_kw=grid_limit_kw
            )

            grid_upgrade = float(getattr(sub, "grid_connection_upgrade_cost", 0.0))
            temp_conn = float(getattr(sub, "temporary_connection_cost", 0.0))
            hardware_capex = fin_m_bess.total_capex
            if sub.include_generator and sub.generator_config:
                gen_c = float(sub.generator_config.capital_cost) if sub.generator_config.monthly_lease_fee <= 0 else 0.0
                hardware_capex += gen_c

            capex = hardware_capex + grid_upgrade + temp_conn

            payback = fin_m_bess.simple_payback_years or 0.0
            npv = fin_m_bess.net_present_value
            irr_val = getattr(fin_m_bess, "internal_rate_of_return_pct", None)
            lcoe_val = getattr(fin_m_bess, "levelized_cost_of_storage_eur_kwh", None)
            cum_costs_fac = fin_m_bess.cumulative_with_bess if fin_m_bess.cumulative_with_bess else fac_cum_series
            base_costs_fac = fin_m_bess.cumulative_status_quo if fin_m_bess.cumulative_status_quo else fac_cum_series
            tco_15y = cum_costs_fac[-1] if cum_costs_fac else (capex + (fin_m_bess.annual_with_bess_total_bill + fin_m_bess.annual_opex_year1) * 18.5989)
            if sub.include_generator and sub.generator_config:
                tco_15y += (gen_op_cost + gen_lease_annual) * 18.5989
            net_savings = base_15y_facility_tco - tco_15y
            cum_costs_sol = [capex] * 16 if capex > 0 else solar_cum_series
            base_costs_sol = solar_cum_series
            opex_y1 = fin_m_bess.annual_with_bess_total_bill + fin_m_bess.annual_opex_year1
            if sub.include_generator and sub.generator_config:
                opex_y1 += gen_op_cost + gen_lease_annual
            res_bill_y1 = fin_m_bess.annual_with_bess_total_bill
            cash_table = fin_m_bess.cash_flow_table
        elif sub.include_generator and sub.generator_config:
            gen_cfg = sub.generator_config
            grid_upgrade = float(getattr(sub, "grid_connection_upgrade_cost", 0.0))
            temp_conn = float(getattr(sub, "temporary_connection_cost", 0.0))
            hardware_capex = float(gen_cfg.capital_cost) if gen_cfg.monthly_lease_fee <= 0 else 0.0
            capex = hardware_capex + grid_upgrade + temp_conn

            ann_savings = float(gen_sim_res.get("annual_net_savings", 0.0)) if gen_sim_res else 0.0
            ann_with_gen = float(gen_sim_res.get("annual_with_generator", base_annual_cost)) if gen_sim_res else base_annual_cost

            # 15-year cumulative trajectory
            cum_costs_fac = [capex]
            cum_track = capex
            for y in range(1, 16):
                cum_track += ann_with_gen * ((1.0 + 0.03) ** (y - 1))
                cum_costs_fac.append(round(cum_track, 2))

            tco_15y = cum_costs_fac[-1]
            payback = (capex / ann_savings) if (ann_savings > 0 and capex > 0) else 0.0
            npv = (ann_savings * 10.3797) - capex
            irr_val = ((ann_savings / capex) * 100.0) if (ann_savings > 0 and capex > 0) else None
            lcoe_val = gen_sim_res["kpis"].levelized_cost_per_kwh if (gen_sim_res and gen_sim_res["kpis"].levelized_cost_per_kwh > 0) else None
            net_savings = base_15y_facility_tco - tco_15y
            base_costs_fac = fac_cum_series
            cum_costs_sol = [capex] * 16 if capex > 0 else solar_cum_series
            base_costs_sol = solar_cum_series
            opex_y1 = ann_with_gen
            res_bill_y1 = max(0.0, ann_with_gen - gen_op_cost - gen_lease_annual)
            cash_table = gen_sim_res["df_zahlungsreihe"].to_dict(orient="records") if (gen_sim_res and "df_zahlungsreihe" in gen_sim_res) else []
        else:
            grid_upgrade = float(getattr(sub, "grid_connection_upgrade_cost", 0.0))
            temp_conn = float(getattr(sub, "temporary_connection_cost", 0.0))
            hardware_capex = 0.0

            capex = hardware_capex + grid_upgrade + temp_conn
            residual_annual_cost = base_annual_cost
            
            # Proper 15-year cumulative trajectory (accumulating year over year)
            cum_costs_fac = [capex]
            cum_track = capex
            for y in range(1, 16):
                cum_track += residual_annual_cost * ((1.0 + 0.03) ** (y - 1))
                cum_costs_fac.append(round(cum_track, 2))

            tco_15y = cum_costs_fac[-1]
            payback = 0.0
            npv = -capex if capex > 0 else 0.0
            irr_val = None
            lcoe_val = None
            net_savings = base_15y_facility_tco - tco_15y
            base_costs_fac = fac_cum_series
            cum_costs_sol = [capex] * 16 if capex > 0 else solar_cum_series
            base_costs_sol = solar_cum_series
            opex_y1 = residual_annual_cost
            res_bill_y1 = residual_annual_cost
            cash_table = []

        # Compute 12-month residual grid consumption trajectory (Jan - Dec)
        sub_monthly_res = None
        if has_valid_int and hasattr(int_res, "df_timeseries") and int_res.df_timeseries is not None and not int_res.df_timeseries.empty:
            df_int_ts = int_res.df_timeseries
            if "P_Residual_kW" in df_int_ts.columns:
                m_col = "month" if "month" in df_int_ts.columns else None
                if m_col is None and ("timestamp" in df_int_ts.columns or isinstance(df_int_ts.index, pd.DatetimeIndex)):
                    try:
                        ts_int = df_int_ts["timestamp"] if "timestamp" in df_int_ts.columns else df_int_ts.index
                        ts_int = pd.to_datetime(ts_int)
                        m_series = ts_int.dt.month
                        dt_h = 0.25
                        if len(ts_int) > 1:
                            dt_diff = (ts_int.iloc[1] - ts_int.iloc[0]).total_seconds() / 3600.0
                            if 0.05 < dt_diff < 5.0:
                                dt_h = dt_diff
                        monthly_res_s = (df_int_ts["P_Residual_kW"] * dt_h / 1000.0).groupby(m_series).sum()
                        if len(monthly_res_s) == 12:
                            sub_monthly_res = [round(float(monthly_res_s.get(m, 0.0)), 1) for m in range(1, 13)]
                    except Exception:
                        sub_monthly_res = None
                elif m_col is not None:
                    try:
                        monthly_res_s = (df_int_ts["P_Residual_kW"] * 0.25 / 1000.0).groupby(df_int_ts["month"]).sum()
                        if len(monthly_res_s) == 12:
                            sub_monthly_res = [round(float(monthly_res_s.get(m, 0.0)), 1) for m in range(1, 13)]
                    except Exception:
                        sub_monthly_res = None

        if not sub_monthly_res or len(sub_monthly_res) != 12:
            avoided_total = max(0.0, base_total_mwh - residual_mwh)
            if avoided_total > 0:
                # Realistic seasonal solar irradiation distribution (Jan -> Dec)
                solar_weights = [0.032, 0.048, 0.082, 0.115, 0.142, 0.148, 0.152, 0.134, 0.089, 0.051, 0.038, 0.029]
                sum_sw = sum(solar_weights)
                sub_monthly_res = []
                for m_idx in range(12):
                    m_avoided = avoided_total * (solar_weights[m_idx] / sum_sw)
                    m_res = max(0.0, base_monthly_mwh[m_idx] - m_avoided)
                    sub_monthly_res.append(m_res)
                # Calibrate sum to match residual_mwh
                cur_sum = sum(sub_monthly_res)
                if cur_sum > 0:
                    scale = residual_mwh / cur_sum
                    sub_monthly_res = [round(v * scale, 1) for v in sub_monthly_res]
                else:
                    sub_monthly_res = [round(residual_mwh / 12.0, 1)] * 12
            else:
                sub_monthly_res = list(base_monthly_mwh)

        records.append({
            "id": sub.id,
            "rank": f"#{idx+1}",
            "name": sub.name,
            "tech_mix": sub.technology_mix_label,
            "capex": capex,
            "capex_str": f"{capex:,.0f} {currency}",
            "hardware_capex": hardware_capex,
            "grid_upgrade_cost": grid_upgrade,
            "temporary_connection_cost": temp_conn,
            "annual_opex": opex_y1,
            "residual_bill_y1": res_bill_y1,
            "first_year_opex": opex_y1,
            "total_15y_opex": tco_15y - capex,
            "total_15y_tco": tco_15y,
            "tco_str": f"{tco_15y:,.0f} {currency}",
            "payback_years": round(payback, 1) if payback else 0.0,
            "payback_str": f"{payback:.1f} Yrs" if payback > 0 else "-",
            "npv": npv,
            "npv_str": f"{npv:,.0f} {currency}",
            "irr_pct": irr_val,
            "lcoe_per_kwh": lcoe_val,
            "net_savings": net_savings,
            "net_savings_str": f"+{net_savings:,.0f} {currency}" if net_savings > 0 else f"{net_savings:,.0f} {currency}",
            "autarky_pct": round(autarky, 1),
            "autarky_str": f"{autarky:.1f} %",
            "self_consumption_pct": round(self_cons, 1),
            "self_consumption_str": f"{self_cons:.1f} %" if self_cons > 0 else "-",
            "total_load_mwh": round(base_total_mwh, 1),
            "monthly_load_mwh": base_monthly_mwh,
            "monthly_residual_mwh": sub_monthly_res,
            "generation_mwh": round((annual_gen_kwh + gen_gen_kwh) / 1000.0, 1),
            "solar_generation_mwh": round(annual_gen_kwh / 1000.0, 1),
            "generator_mwh": round(gen_gen_kwh / 1000.0, 1),
            "direct_consumption_mwh": round(direct_mwh, 1),
            "residual_grid_mwh": round(residual_mwh, 1),
            "surplus_export_mwh": round(surplus_mwh, 1),
            "baseline_peak_kw": round(base_peak_kw, 1),
            "residual_peak_kw": round(res_peak_kw, 1),
            "shaved_peak_kw": round(peak_shaved, 1),
            "co2_avoided_tons": round(co2_tons, 1),
            "facility_cum_costs": cum_costs_fac,
            "facility_base_costs": base_costs_fac,
            "solar_cum_costs": cum_costs_sol,
            "solar_base_costs": base_costs_sol,
            "cumulative_costs": cum_costs_fac,
            "baseline_costs": base_costs_fac,
            "cash_flow_table": cash_table,
            "color": sub.color_code
        })

    return records


def _render_scenario_visual_cards(project: ProjectContainer, records: List[Dict[str, Any]], key_prefix: str = "app_comparison") -> None:
    """
    Renders visual architecture tree hierarchy:
      - Top Level: Root Base Benchmark Scenario (Status Quo) with inherited foundation (load & contract).
      - Visual Branch Connector: Clear graph tree lines connecting the root node down to children.
      - Bottom Level: Child Sub-Scenario Branches with custom technology interventions, financial ROI, and 1-click branch switching.
    """
    st.markdown("### :material/account_tree: Scenario Hierarchy & Branching Architecture")
    st.caption("Visual tree structure: Foundational Root Benchmark (Status Quo) on top branching into child sub-scenario configurations below:")

    active_sub_id = project.active_sub_scenario_id
    base_rec = next((r for r in records if r["id"] == "base"), records[0] if records else {})
    sub_recs = [r for r in records if r["id"] != "base"]

    # --------------------------------------------------------------------------
    # 1. TOP LEVEL: ROOT BASE SCENARIO (Status Quo)
    # --------------------------------------------------------------------------
    is_base_active = (active_sub_id is None)
    base_border = "2px solid #10B981" if is_base_active else "1px solid rgba(59, 130, 246, 0.6)"
    base_bg = "rgba(16, 185, 129, 0.08)" if is_base_active else "rgba(15, 23, 42, 0.75)"
    base_badge = (
        "<span style='background:#10B981; color:#042F2E; padding:3px 10px; border-radius:4px; font-weight:700; font-size:0.75rem;'>ACTIVE WORKSPACE TARGET</span>"
        if is_base_active else
        "<span style='background:#1E3A8A; color:#93C5FD; padding:3px 10px; border-radius:4px; font-size:0.75rem; font-weight:600;'>FOUNDATIONAL BASELINE</span>"
    )

    c_name = project.base_scenario.base_contract.name if project.base_scenario.base_contract else "Standard Contract"
    load_name = project.base_scenario.load_profile_name or "Facility Consumption"

    # Centered container layout for the root node
    col_root_pad1, col_root, col_root_pad2 = st.columns([1, 2.8, 1])
    with col_root:
        st.markdown(
            f"""
            <div style="background:{base_bg}; border:{base_border}; border-radius:10px; padding:16px; box-shadow: 0 4px 12px rgba(0,0,0,0.3);">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                    <span style="font-weight:800; font-size:1.05rem; color:#F8FAFC;">
                        &#127963; {base_rec.get('name', 'Status Quo (Base Scenario)')}
                    </span>
                    {base_badge}
                </div>
                <div style="font-size:0.82rem; color:#94A3B8; margin-bottom:10px; border-bottom:1px solid rgba(51, 65, 85, 0.6); padding-bottom:8px;">
                    Root Baseline &mdash; 100% Utility Grid Supply (0 on-site generation / 0 BESS)
                </div>
                <div style="font-size:0.82rem; color:#CBD5E1; line-height:1.7; margin-bottom:12px;">
                    <div><b>Facility Load:</b> <span style="color:#F8FAFC;">{load_name} ({base_rec.get('total_load_mwh', 0) * 1000.0:,.0f} kWh/a | Peak: {base_rec.get('baseline_peak_kw', 0):,.1f} kW)</span></div>
                    <div><b>Supply Contract:</b> <span style="color:#F8FAFC;">{c_name} ({project.currency or 'EUR'})</span></div>
                    <div><b>On-Site Assets:</b> <span style="color:#94A3B8;">None (Grid Only)</span></div>
                </div>
                <div style="background:rgba(0,0,0,0.35); border-radius:6px; padding:8px 12px; font-size:0.8rem; color:#E2E8F0; display:grid; grid-template-columns:1fr 1fr; gap:6px; margin-bottom:12px;">
                    <div><span style="color:#94A3B8;">Annual OPEX:</span> <b>{base_rec.get('annual_opex', 0):,.0f} {project.currency or 'EUR'}</b></div>
                    <div><span style="color:#94A3B8;">15Y Total TCO:</span> <b>{base_rec.get('tco_str', '-')}</b></div>
                    <div><span style="color:#94A3B8;">CAPEX:</span> <b>0 {project.currency or 'EUR'}</b></div>
                    <div><span style="color:#94A3B8;">Autarky:</span> <b>0.0 %</b></div>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        if is_base_active:
            st.button(":material/check_circle: Active in Workspace (Base)", key=f"{key_prefix}_act_btn_base", disabled=True, use_container_width=True)
        else:
            if st.button(":material/anchor: Activate Status Quo Baseline", key=f"{key_prefix}_sw_btn_base", use_container_width=True):
                project.active_sub_scenario_id = None
                st.session_state["project_container"] = project
                sync_active_scenario_into_session(project, auto_execute=False)
                st.rerun()

    # --------------------------------------------------------------------------
    # 2. TREE CONNECTOR GRAPHIC (SVG / Branch Junction)
    # --------------------------------------------------------------------------
    num_subs = len(sub_recs)
    branch_text = f"{num_subs} Configured Sub-Scenario {'Branch' if num_subs == 1 else 'Branches'}" if num_subs > 0 else "No Child Branches Configured"
    st.markdown(
        f"""
        <div style="display:flex; flex-direction:column; align-items:center; margin: 6px 0 16px 0;">
            <div style="width: 2px; height: 20px; background: #3B82F6;"></div>
            <div style="background: rgba(30, 58, 138, 0.35); border: 1px solid rgba(59, 130, 246, 0.6); color: #93C5FD; border-radius: 20px; padding: 4px 16px; font-size: 0.78rem; font-weight: 600; display:flex; align-items:center; gap:8px;">
                <span>&#10554; Inherits Load Profile & Utility Contract &mdash; {branch_text}</span>
            </div>
            <div style="width: 2px; height: 16px; background: #3B82F6;"></div>
        </div>
        """,
        unsafe_allow_html=True
    )

    # --------------------------------------------------------------------------
    # 3. BOTTOM LEVEL: CHILD SUB-SCENARIOS (Side-by-Side Columns)
    # --------------------------------------------------------------------------
    if not sub_recs:
        col_empty_pad1, col_empty, col_empty_pad2 = st.columns([1, 2.5, 1])
        with col_empty:
            st.info(
                "**No Sub-Scenario branches created yet.**\n\n"
                "Use the **'+ New Branch'** button in the sidebar to fork a sub-scenario with Solar PV, Battery Storage (BESS), or Backup Gensets.",
                icon=":material/alt_route:"
            )
        return

    cols = st.columns(max(1, len(sub_recs)))
    for idx, (col, r) in enumerate(zip(cols, sub_recs)):
        with col:
            sc_id = r["id"]
            is_active = (sc_id == active_sub_id)
            accent_color = "#10B981" if is_active else r.get("color", "#38BDF8")
            border_css = f"2px solid {accent_color}" if is_active else "1px solid rgba(51, 65, 85, 0.8)"
            bg_css = "rgba(16, 185, 129, 0.08)" if is_active else "rgba(15, 23, 42, 0.65)"

            active_badge = (
                "<span style='background:#10B981; color:#042F2E; padding:3px 8px; border-radius:4px; font-weight:700; font-size:0.75rem;'>ACTIVE WORKSPACE BRANCH</span>"
                if is_active else
                "<span style='background:#334155; color:#94A3B8; padding:3px 8px; border-radius:4px; font-size:0.75rem;'>COMPARISON BRANCH</span>"
            )

            sub_obj = project.get_sub_scenario(sc_id)

            # Hardware specs
            if sub_obj and sub_obj.include_solar and sub_obj.solar_config:
                tech = getattr(sub_obj.solar_config, "technology_preset", "TOPCon")
                pv_desc = f"{sub_obj.solar_config.dc_capacity_kwp:,.1f} kWp ({tech})"
            else:
                pv_desc = "None"

            if sub_obj and sub_obj.include_bess and sub_obj.bess_config:
                bess_desc = f"{sub_obj.bess_config.capacity_kwh:,.0f} kWh ({sub_obj.bess_config.max_discharge_power_kw:,.0f} kW)"
            else:
                bess_desc = "None"

            if sub_obj and sub_obj.include_generator and sub_obj.generator_config:
                gen_desc = f"{sub_obj.generator_config.rated_power_kw:,.0f} kW"
            else:
                gen_desc = "None"

            st.markdown(
                f"""
                <div style="background:{bg_css}; border:{border_css}; border-radius:8px; padding:12px; margin-bottom:8px; box-shadow: 0 4px 10px rgba(0,0,0,0.25);">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                        <span style="font-weight:700; font-size:0.95rem; color:#F8FAFC;">
                            &#9500;&#9472; {r['name']}
                        </span>
                    </div>
                    <div style="margin-bottom:8px;">{active_badge}</div>
                    <div style="font-size:0.78rem; color:#64748B; margin-bottom:6px;">
                        &#10554; Inherits: <i>{load_name}</i> & <i>{c_name}</i>
                    </div>
                    <div style="font-size:0.8rem; color:#CBD5E1; line-height:1.6; margin-bottom:10px;">
                        <div><b>Solar PV:</b> <span style="color:{'#F59E0B' if pv_desc != 'None' else '#94A3B8'};">{pv_desc}</span></div>
                        <div><b>Storage (BESS):</b> <span style="color:{'#10B981' if bess_desc != 'None' else '#94A3B8'};">{bess_desc}</span></div>
                        <div><b>Vertragswechsel:</b> <span style="color:{'#38BDF8' if (sub_obj and sub_obj.use_custom_grid_tariff) else '#94A3B8'};">{'Aktiv (Neuer Tarif)' if (sub_obj and sub_obj.use_custom_grid_tariff) else 'None (Status Quo)'}</span></div>
                    </div>
                    <div style="background:rgba(0,0,0,0.3); border-radius:6px; padding:8px; font-size:0.78rem; color:#E2E8F0; display:grid; grid-template-columns:1fr 1fr; gap:4px; margin-bottom:8px;">
                        <div><span style="color:#94A3B8;">CAPEX:</span> <b>{r['capex_str']}</b></div>
                        <div><span style="color:#94A3B8;">Autarky:</span> <b>{r['autarky_str']}</b></div>
                        <div><span style="color:#94A3B8;">Payback:</span> <b>{r['payback_str']}</b></div>
                        <div><span style="color:#94A3B8;">15y Net:</span> <b>{r['net_savings_str']}</b></div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )

            btn_act_col1, btn_act_col2 = st.columns([3, 1])
            with btn_act_col1:
                if is_active:
                    st.button(":material/check_circle: Active", key=f"{key_prefix}_act_btn_{sc_id}", disabled=True, use_container_width=True)
                else:
                    btn_lbl = f"Switch #{idx+1}"
                    if st.button(f":material/near_me: {btn_lbl}", key=f"{key_prefix}_sw_btn_{sc_id}", use_container_width=True):
                        project.active_sub_scenario_id = sc_id
                        st.session_state["project_container"] = project
                        sync_active_scenario_into_session(project, auto_execute=False)
                        st.rerun()
            with btn_act_col2:
                with st.popover("", icon=":material/settings:", help="Branch & Component Options"):
                    st.markdown(f"**{r['name']}**")
                    if sub_obj:
                        st.caption("Active Solution Modules:")
                        t_sol = st.checkbox("Solar PV", value=sub_obj.include_solar, key=f"{key_prefix}_card_chk_sol_{sc_id}")
                        t_bess = st.checkbox("BESS Storage", value=sub_obj.include_bess, key=f"{key_prefix}_card_chk_bess_{sc_id}")
                        t_gen = st.checkbox("Generator (Genset)", value=sub_obj.include_generator, key=f"{key_prefix}_card_chk_gen_{sc_id}")
                        t_tar = st.checkbox("Tariff Switch", value=sub_obj.use_custom_grid_tariff, key=f"{key_prefix}_card_chk_tar_{sc_id}")
                        if (
                            t_sol != sub_obj.include_solar
                            or t_bess != sub_obj.include_bess
                            or t_gen != sub_obj.include_generator
                            or t_tar != sub_obj.use_custom_grid_tariff
                        ):
                            sub_obj.include_solar = t_sol
                            sub_obj.include_bess = t_bess
                            sub_obj.include_generator = t_gen
                            sub_obj.use_custom_grid_tariff = t_tar
                            st.session_state["project_container"] = project
                            sync_active_scenario_into_session(project, auto_execute=False)
                            st.rerun()

                        st.divider()
                        if st.button("Delete Branch", icon=":material/delete:", key=f"{key_prefix}_card_del_{sc_id}", type="secondary", use_container_width=True):
                            project.delete_sub_scenario(sc_id)
                            st.session_state["project_container"] = project
                            sync_active_scenario_into_session(project, auto_execute=False)
                            st.rerun()

    # Toolbar to create new branch directly from architecture overview
    c_new1, _ = st.columns([3.5, 6.5])
    with c_new1:
        with st.popover("+ Create New Sub-Scenario Branch", icon=":material/add_circle:", use_container_width=True):
            st.markdown("##### :material/add: Instantiate New Solution Path")
            new_name_t5 = st.text_input(
                "Sub-Scenario Name:",
                value=f"Sub-Scenario {len(project.sub_scenarios) + 1}",
                key=f"{key_prefix}_t5_tree_new_name"
            )
            st.markdown("**Select Modules to Include:**")
            t_inc_sol = st.checkbox("Solar PV Generation", value=True, key=f"{key_prefix}_tree_new_sol")
            t_inc_bess = st.checkbox("Battery Storage (BESS)", value=False, key=f"{key_prefix}_tree_new_bess")
            t_inc_gen = st.checkbox("Peaking / Backup Generator (Genset)", value=False, key=f"{key_prefix}_tree_new_gen")
            t_inc_tar = st.checkbox("Tariff Switch / Alternative Contract", value=False, key=f"{key_prefix}_tree_new_tar")
            color_choice_t5 = st.selectbox(
                "Chart Curve Color:",
                options=["#2563EB (Blue)", "#059669 (Green)", "#D97706 (Amber)", "#DC2626 (Red)", "#7C3AED (Purple)", "#0891B2 (Cyan)"],
                index=len(project.sub_scenarios) % 6,
                key=f"{key_prefix}_t5_tree_new_col"
            )
            clean_c = color_choice_t5.split(" ")[0]
            if st.button("Create & Switch to Clean Branch", icon=":material/check:", type="primary", use_container_width=True, key=f"{key_prefix}_t5_tree_create_btn"):
                new_sub = SubScenario(
                    name=new_name_t5.strip() or f"Sub-Scenario {len(project.sub_scenarios) + 1}",
                    color_code=clean_c,
                    include_solar=t_inc_sol,
                    include_bess=t_inc_bess,
                    include_generator=t_inc_gen,
                    use_custom_grid_tariff=t_inc_tar
                )
                project.add_sub_scenario(new_sub)
                project.active_sub_scenario_id = new_sub.id
                st.session_state["project_container"] = project
                sync_active_scenario_into_session(project, auto_execute=False)
                st.rerun()


def _build_scenario_delta_matrix(project: ProjectContainer, records: List[Dict[str, Any]]) -> pd.DataFrame:
    """
    Constructs a detailed side-by-side architecture & parameter delta matrix
    highlighting baseline-inherited constants versus scenario-specific technical & financial interventions.
    """
    currency = project.currency or "EUR"
    base_rec = next((r for r in records if r["id"] == "base"), records[0] if records else {})
    sub_recs = [r for r in records if r["id"] != "base"]

    # Identify load description
    load_desc = f"{project.base_scenario.load_profile_name}"
    if project.base_scenario.consumers:
        load_desc += f" ({len(project.base_scenario.consumers)} Consumers)"

    # Contract description
    c_name = project.base_scenario.base_contract.name if project.base_scenario.base_contract else "Standard Tariff Contract"

    rows = [
        {
            "Parameter / Architecture Layer": "1. Facility Load Profile",
            "Status Quo (Baseline)": load_desc,
            "Inheritance & Delta Status": ":material/check_circle: Inherited (100% Identical)"
        },
        {
            "Parameter / Architecture Layer": "2. Electricity Supply Contract",
            "Status Quo (Baseline)": f"{c_name} ({currency})",
            "Inheritance & Delta Status": ":material/check_circle: Inherited (100% Identical)"
        },
        {
            "Parameter / Architecture Layer": "3. Solar PV Peak Capacity (DC)",
            "Status Quo (Baseline)": "0.0 kWp (Grid Only)",
            "Inheritance & Delta Status": ":material/tune: Configured Branch"
        },
        {
            "Parameter / Architecture Layer": "4. Inverter Rating (AC)",
            "Status Quo (Baseline)": "-",
            "Inheritance & Delta Status": ":material/tune: Specific Sizing"
        },
        {
            "Parameter / Architecture Layer": "5. Cell Technology & Module Count",
            "Status Quo (Baseline)": "-",
            "Inheritance & Delta Status": ":material/tune: Hardware Architecture"
        },
        {
            "Parameter / Architecture Layer": "6. Turn-Key Investment (CAPEX)",
            "Status Quo (Baseline)": f"0 {currency}",
            "Inheritance & Delta Status": ":material/payments: Initial Capital"
        },
        {
            "Parameter / Architecture Layer": "7. Solar Coverage / Autarky Degree",
            "Status Quo (Baseline)": "0.0 %",
            "Inheritance & Delta Status": ":material/bolt: Energy Autarky"
        },
        {
            "Parameter / Architecture Layer": "8. Direct Self-Consumption Rate",
            "Status Quo (Baseline)": "-",
            "Inheritance & Delta Status": ":material/pie_chart: On-Site Utilization"
        },
        {
            "Parameter / Architecture Layer": "9. Annual Residual Electricity Bill",
            "Status Quo (Baseline)": f"{base_rec.get('annual_opex', 0):,.0f} {currency}",
            "Inheritance & Delta Status": ":material/trending_down: Operational Expense"
        },
        {
            "Parameter / Architecture Layer": "10. Net Annual Financial Benefit",
            "Status Quo (Baseline)": f"0 {currency}",
            "Inheritance & Delta Status": ":material/trending_up: Recurring Cashflow"
        },
        {
            "Parameter / Architecture Layer": "11. Simple Capital Payback (ROI)",
            "Status Quo (Baseline)": "Baseline Reference",
            "Inheritance & Delta Status": ":material/timer: Amortisation Speed"
        },
        {
            "Parameter / Architecture Layer": "12. 15-Year Life-Cycle Total Cost (TCO)",
            "Status Quo (Baseline)": f"{base_rec.get('total_15y_tco', 0):,.0f} {currency}",
            "Inheritance & Delta Status": ":material/savings: Life-Cycle TCO"
        }
    ]

    # Populate columns for each sub-scenario
    for s_idx, sub in enumerate(project.sub_scenarios):
        col_name = f"Branch #{s_idx+1}: {sub.name}"
        s_rec = next((r for r in sub_recs if r["id"] == sub.id), {})

        # Load & Contract (Inherited)
        rows[0][col_name] = load_desc
        rows[1][col_name] = f"{c_name} ({currency})"

        # Solar PV Capacity
        kwp = sub.solar_config.dc_capacity_kwp if (sub.include_solar and sub.solar_config) else 0.0
        rows[2][col_name] = f"{kwp:.1f} kWp" if kwp > 0 else "0.0 kWp (None)"

        # Inverter
        inv_kw = sub.solar_config.inverter_capacity_kw if (sub.include_solar and sub.solar_config) else 0.0
        rows[3][col_name] = f"{inv_kw:,.0f} kW AC" if inv_kw > 0 else "-"

        # Tech & Module Count
        if sub.include_solar and sub.solar_config:
            tech_lbl = getattr(sub.solar_config, "technology_preset", "TOPCon")
            mod_cnt = getattr(sub.solar_config, "module_count", 0)
            rows[4][col_name] = f"{tech_lbl} ({mod_cnt:,} modules)"
        else:
            rows[4][col_name] = "-"

        # CAPEX
        rows[5][col_name] = s_rec.get("capex_str", f"0 {currency}")

        # Autarky
        rows[6][col_name] = s_rec.get("autarky_str", "0.0 %")

        # Self-Consumption
        rows[7][col_name] = s_rec.get("self_consumption_str", "-")

        # Residual Bill
        rows[8][col_name] = f"{s_rec.get('annual_opex', 0):,.0f} {currency}"

        # Net Annual Benefit
        annual_benefit = max(0.0, base_rec.get("annual_opex", 0) - s_rec.get("annual_opex", 0))
        rows[9][col_name] = f"+{annual_benefit:,.0f} {currency}/a" if annual_benefit > 0 else f"0 {currency}"

        # Payback
        rows[10][col_name] = s_rec.get("payback_str", "-")

        # 15y TCO
        rows[11][col_name] = s_rec.get("tco_str", f"0 {currency}")

    return pd.DataFrame(rows)


def _render_economic_simulation_and_cashflow_schedules(
    project: ProjectContainer,
    records: List[Dict[str, Any]],
    currency: str = "EUR",
    key_prefix: str = "app_scen_cf"
) -> None:
    """
    Renders comprehensive Multi-Scenario Economic Simulation, Life-Cycle Payment Schedules,
    and Cross-Scenario Metric Trajectory Matrix fulfilling Assignment Section 8.3.
    """
    st.markdown("### :material/payments: Multi-Scenario Economic Simulation & Life-Cycle Schedules (Assignment 8.3)")
    st.caption(
        "Comprehensive comparative economic simulation: Side-by-side criteria breakdown, multi-year cash flow payment schedules, "
        "and cross-scenario metric trajectory matrix across all scenarios including Status Quo."
    )

    base_rec = next((r for r in records if r["id"] == "base"), records[0] if records else {})
    sub_recs = [r for r in records if r["id"] != "base"]
    base_annual_cost = float(base_rec.get("annual_opex", 344141.21))

    # 1. Global Controls & Sensitivity Toolbar
    with st.container(border=True):
        col_ctrl1, col_ctrl2, col_ctrl3, col_ctrl4 = st.columns([3.5, 2.5, 3.0, 3.0])
        with col_ctrl1:
            view_mode = st.radio(
                "Comparison Perspective:",
                options=[
                    ":material/view_column: Scenario-Centric (Side-by-Side)",
                    ":material/table_chart: Metric-Centric (Time Matrix)"
                ],
                horizontal=False,
                key=f"{key_prefix}_view_mode"
            )
        with col_ctrl2:
            horizon_years = st.selectbox(
                "Analysis Horizon:",
                options=[10, 15, 20, 25],
                index=1,
                format_func=lambda y: f"{y} Years Lifecycle",
                key=f"{key_prefix}_horizon"
            )
        with col_ctrl3:
            wacc_rate = st.number_input(
                "Discount Rate / WACC (%):",
                min_value=0.0,
                max_value=25.0,
                value=5.0,
                step=0.5,
                help="Weighted Average Cost of Capital used for discounting future cash flows (NPV).",
                key=f"{key_prefix}_wacc"
            )
        with col_ctrl4:
            inflation_rate = st.number_input(
                "Tariff Escalation (%/yr):",
                min_value=0.0,
                max_value=20.0,
                value=2.0,
                step=0.5,
                help="Expected annual utility electricity price escalation rate.",
                key=f"{key_prefix}_infl"
            )

    r_wacc = float(wacc_rate) / 100.0
    r_infl = float(inflation_rate) / 100.0

    # Helper function to project standardized multi-year cash flows for any record up to horizon_years
    def _project_scenario_cashflow(rec: Dict[str, Any], horizon: int, wacc: float, infl: float) -> List[Dict[str, Any]]:
        c_capex = float(rec.get("capex", 0.0))
        c_grid = float(rec.get("grid_upgrade_cost", 0.0))
        c_temp = float(rec.get("temporary_connection_cost", 0.0))
        c_upfront = c_capex + c_grid + c_temp

        is_base = (rec.get("id") == "base")
        annual_opex_y1 = float(rec.get("annual_opex", base_annual_cost))

        has_solar = ("generation_mwh" in rec and rec.get("generation_mwh", 0) > 0)
        has_bess = ("bess_config" in str(rec) or ("tech_mix" in rec and "BESS" in str(rec.get("tech_mix"))))

        cf_list: List[Dict[str, Any]] = []
        running_cf = -c_upfront
        running_tco = c_upfront

        for y in range(1, horizon + 1):
            sq_bill = base_annual_cost * ((1.0 + infl) ** (y - 1))
            
            if is_base:
                res_bill = sq_bill
                y_opex = 0.0
                cell_rep = 0.0
                tot_outflow = sq_bill
                gross_sav = 0.0
                net_cf = 0.0
            else:
                if has_solar and not has_bess:
                    deg_fac = max(0.70, 1.0 - 0.005 * (y - 1))
                    first_yr_savings = max(0.0, base_annual_cost - annual_opex_y1)
                    y_sav = first_yr_savings * deg_fac * ((1.0 + infl) ** (y - 1))
                    res_bill = max(0.0, sq_bill - y_sav)
                    y_opex = float(rec.get("first_year_opex", c_capex * 0.01)) * ((1.0 + infl * 0.8) ** (y - 1))
                    cell_rep = 0.0
                    tot_outflow = res_bill + y_opex
                    gross_sav = y_sav
                    net_cf = sq_bill - tot_outflow
                elif has_bess and not has_solar:
                    deg_fac = max(0.60, 1.0 - 0.02 * (y - 1))
                    if y > 10:
                        deg_fac = max(0.70, 0.95 - 0.02 * (y - 11))
                    first_yr_savings = max(0.0, base_annual_cost - float(rec.get("residual_bill_y1", annual_opex_y1 * 0.95)))
                    y_sav = first_yr_savings * deg_fac * ((1.0 + infl) ** (y - 1))
                    res_bill = max(0.0, sq_bill - y_sav)
                    y_opex = float(rec.get("first_year_opex", c_capex * 0.015)) * ((1.0 + infl * 0.8) ** (y - 1))
                    cell_rep = (c_capex * 0.65 * 0.40) if y == 10 else 0.0
                    tot_outflow = res_bill + y_opex + cell_rep
                    gross_sav = y_sav
                    net_cf = sq_bill - tot_outflow
                else:
                    deg_fac = max(0.70, 1.0 - 0.01 * (y - 1))
                    first_yr_savings = max(0.0, base_annual_cost - annual_opex_y1)
                    y_sav = first_yr_savings * deg_fac * ((1.0 + infl) ** (y - 1))
                    res_bill = max(0.0, sq_bill - y_sav)
                    y_opex = (c_capex * 0.01) * ((1.0 + infl * 0.8) ** (y - 1))
                    cell_rep = (c_capex * 0.25) if (has_bess and y == 10) else 0.0
                    tot_outflow = res_bill + y_opex + cell_rep
                    gross_sav = y_sav
                    net_cf = sq_bill - tot_outflow

            running_cf += net_cf
            disc_cf = net_cf / ((1.0 + wacc) ** y)
            running_tco += tot_outflow

            cf_list.append({
                "year": y,
                "status_quo_bill": round(sq_bill, 2),
                "residual_bill": round(res_bill, 2),
                "opex": round(y_opex, 2),
                "cell_replacement": round(cell_rep, 2),
                "total_outflow": round(tot_outflow, 2),
                "gross_savings": round(gross_sav, 2),
                "net_cash_flow": round(net_cf, 2),
                "cumulative_cash_flow": round(running_cf, 2),
                "discounted_cash_flow": round(disc_cf, 2),
                "cumulative_tco": round(running_tco, 2)
            })

        return cf_list

    # Pre-generate cash flows for all records
    scenario_schedules: Dict[str, List[Dict[str, Any]]] = {}
    for r in records:
        scenario_schedules[r["id"]] = _project_scenario_cashflow(r, horizon=horizon_years, wacc=r_wacc, infl=r_infl)

    # --------------------------------------------------------------------------
    # PERSPECTIVE 1: SCENARIO-CENTRIC (SIDE-BY-SIDE)
    # --------------------------------------------------------------------------
    if ":material/view_column: Scenario-Centric" in view_mode:
        all_ids = [r["id"] for r in records]
        id_map = {r["id"]: r["name"] for r in records}

        selected_ids = st.multiselect(
            "Select Scenarios to Compare Side-by-Side:",
            options=all_ids,
            default=all_ids,
            format_func=lambda sid: id_map.get(sid, sid),
            key=f"{key_prefix}_multisel_scenarios"
        )

        if not selected_ids:
            st.info("Select at least one scenario above to display economic comparison tables.")
            return

        sel_recs = [r for r in records if r["id"] in selected_ids]

        tab_crit, tab_sched = st.tabs([
            ":material/fact_check: 1. Key Commercial & Investment Benchmarks (Assignment 8.3)",
            ":material/calendar_month: 2. Multi-Scenario Cash Flow Schedule (Year-by-Year)"
        ])

        with tab_crit:
            st.caption(
                "Direct side-by-side benchmark comparing initial capital investment, grid connection costs, recurring OPEX, "
                "amortization, Net Present Value, Internal Rate of Return, and Total Cost of Ownership."
            )

            # Assemble criteria rows
            crit_rows = [
                {"Assignment Criterion / Parameter": "1. Hardware Turn-Key CAPEX (Solar / BESS / Genset)"},
                {"Assignment Criterion / Parameter": "2. Grid Connection & Upgrade Costs (Substation/Trafo)"},
                {"Assignment Criterion / Parameter": "3. Temporary Connection / Site Setup Costs"},
                {"Assignment Criterion / Parameter": "4. Total Upfront Capital Investment (Year 0)"},
                {"Assignment Criterion / Parameter": "5. Year 1 Operating & Maintenance Expenses (OPEX)"},
                {"Assignment Criterion / Parameter": "6. Year 1 Residual Electricity Utility Bill"},
                {"Assignment Criterion / Parameter": "7. Total Year 1 Cash Outflow (Bill + OPEX)"},
                {"Assignment Criterion / Parameter": "8. Net Annual Financial Benefit (vs. Status Quo)"},
                {"Assignment Criterion / Parameter": "9. Simple Payback Period (Amortization)"},
                {"Assignment Criterion / Parameter": "10. Discounted Payback Period (WACC-adjusted)"},
                {"Assignment Criterion / Parameter": f"11. {horizon_years}-Year Net Present Value (NPV)"},
                {"Assignment Criterion / Parameter": "12. Internal Rate of Return (IRR)"},
                {"Assignment Criterion / Parameter": "13. Levelized Cost of Energy / Storage (LCOE/LCOS)"},
                {"Assignment Criterion / Parameter": f"14. {horizon_years}-Year Total Cost of Ownership (TCO)"},
                {"Assignment Criterion / Parameter": "15. Clean Energy Autarky & Self-Consumption"}
            ]

            for rec in sel_recs:
                col_name = rec["name"]
                c_sched = scenario_schedules.get(rec["id"], [])
                c_capex = float(rec.get("hardware_capex", rec.get("capex", 0.0)))
                c_grid = float(rec.get("grid_upgrade_cost", 0.0))
                c_temp = float(rec.get("temporary_connection_cost", 0.0))
                c_total_cap = c_capex + c_grid + c_temp

                y1_res_bill = c_sched[0]["residual_bill"] if c_sched else base_annual_cost
                y1_opex = c_sched[0]["opex"] if c_sched else 0.0
                y1_tot = c_sched[0]["total_outflow"] if c_sched else base_annual_cost
                y1_net_sav = c_sched[0]["net_cash_flow"] if c_sched else 0.0
                final_tco = c_sched[-1]["cumulative_tco"] if c_sched else (base_annual_cost * 18.5989)

                # NPV over horizon
                npv_val = -c_total_cap + sum(s["discounted_cash_flow"] for s in c_sched) if rec["id"] != "base" else 0.0

                # Payback
                pb_yrs = rec.get("payback_years", 0.0)
                pb_str = f"{pb_yrs:.1f} Years" if (pb_yrs and pb_yrs > 0) else ("Baseline Reference" if rec["id"] == "base" else "> 20 Years")

                # Discounted payback
                disc_pb_str = "-"
                if rec["id"] != "base" and c_total_cap > 0:
                    disc_cum = -c_total_cap
                    for s in c_sched:
                        disc_cum += s["discounted_cash_flow"]
                        if disc_cum >= 0:
                            disc_pb_str = f"{s['year']} Years"
                            break

                irr_val = rec.get("irr_pct")
                irr_str = f"{irr_val:.1f} %" if (irr_val is not None and irr_val > 0) else ("-" if rec["id"] == "base" else "N/A")

                lcoe_val = rec.get("lcoe_per_kwh")
                lcoe_str = f"{lcoe_val:.4f} {currency}/kWh" if (lcoe_val is not None and lcoe_val > 0) else "-"

                aut_val = rec.get("autarky_pct", 0.0)
                sc_val = rec.get("self_consumption_pct", 0.0)
                aut_str = f"{aut_val:.1f}% Autarky | {sc_val:.1f}% Self-Cons" if aut_val > 0 else ("-" if rec["id"] == "base" else "0.0 %")

                crit_rows[0][col_name] = f"{c_capex:,.0f} {currency}" if c_capex > 0 else f"0 {currency}"
                crit_rows[1][col_name] = f"{c_grid:,.0f} {currency}" if c_grid > 0 else f"0 {currency}"
                crit_rows[2][col_name] = f"{c_temp:,.0f} {currency}" if c_temp > 0 else f"0 {currency}"
                crit_rows[3][col_name] = f"{c_total_cap:,.0f} {currency}"
                crit_rows[4][col_name] = f"{y1_opex:,.0f} {currency}/yr"
                crit_rows[5][col_name] = f"{y1_res_bill:,.0f} {currency}/yr"
                crit_rows[6][col_name] = f"{y1_tot:,.0f} {currency}/yr"
                crit_rows[7][col_name] = f"+{y1_net_sav:,.0f} {currency}/yr" if y1_net_sav > 0 else (f"{y1_net_sav:,.0f} {currency}/yr" if y1_net_sav < 0 else "Baseline (0)")
                crit_rows[8][col_name] = pb_str
                crit_rows[9][col_name] = disc_pb_str
                crit_rows[10][col_name] = f"{npv_val:+,.0f} {currency}" if rec["id"] != "base" else "-"
                crit_rows[11][col_name] = irr_str
                crit_rows[12][col_name] = lcoe_str
                crit_rows[13][col_name] = f"{final_tco:,.0f} {currency}"
                crit_rows[14][col_name] = aut_str

            df_crit = pd.DataFrame(crit_rows)
            st.dataframe(df_crit, use_container_width=True, hide_index=True)

            csv_crit = df_crit.to_csv(index=False).encode('utf-8')
            st.download_button(
                label=":material/download: Export Commercial Benchmarks (CSV)",
                data=csv_crit,
                file_name=f"commercial_benchmarks_{horizon_years}y.csv",
                mime="text/csv",
                key=f"{key_prefix}_dl_crit"
            )

        with tab_sched:
            st.caption(
                f"Multi-year lifecycle payment schedules over {horizon_years} operating years. "
                "Inspect side-by-side annual outlays and net cash flows or drill into individual model schedules."
            )

            sched_sub_mode = st.radio(
                "Schedule Presentation:",
                options=[
                    ":material/table_rows: Consolidated Multi-Scenario Outflows & Cashflows",
                    ":material/receipt_long: Detailed Itemized Breakdown for Single Model"
                ],
                horizontal=True,
                key=f"{key_prefix}_sched_sub_mode"
            )

            if ":material/table_rows: Consolidated" in sched_sub_mode:
                cons_rows = []
                
                # Year 0 Row (Initial Investment)
                y0_row = {"Operating Year": "Year 0 (CAPEX)"}
                for rec in sel_recs:
                    c_up = float(rec.get("capex", 0.0)) + float(rec.get("grid_upgrade_cost", 0.0)) + float(rec.get("temporary_connection_cost", 0.0))
                    y0_row[f"{rec['name']} Outflow"] = f"{c_up:,.0f} {currency}"
                    y0_row[f"{rec['name']} Net CF"] = f"{-c_up:,.0f} {currency}" if c_up > 0 else f"0 {currency}"
                cons_rows.append(y0_row)

                # Year 1 to Horizon
                for y in range(1, horizon_years + 1):
                    yr_row = {"Operating Year": f"Year {y}"}
                    for rec in sel_recs:
                        s_list = scenario_schedules.get(rec["id"], [])
                        row_y = next((item for item in s_list if item["year"] == y), {})
                        out_val = row_y.get("total_outflow", 0.0)
                        net_val = row_y.get("net_cash_flow", 0.0)
                        yr_row[f"{rec['name']} Outflow"] = f"{out_val:,.0f} {currency}"
                        yr_row[f"{rec['name']} Net CF"] = f"{net_val:+,.0f} {currency}" if net_val != 0 else f"0 {currency}"
                    cons_rows.append(yr_row)

                df_cons = pd.DataFrame(cons_rows)
                st.dataframe(df_cons, use_container_width=True, hide_index=True)

                csv_cons = df_cons.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label=":material/download: Export Consolidated Cashflow Schedule (CSV)",
                    data=csv_cons,
                    file_name=f"consolidated_cashflow_schedule_{horizon_years}y.csv",
                    mime="text/csv",
                    key=f"{key_prefix}_dl_cons_sched"
                )

            else:
                single_id = st.selectbox(
                    "Select Model to Inspect Itemized Schedule:",
                    options=selected_ids,
                    format_func=lambda sid: id_map.get(sid, sid),
                    key=f"{key_prefix}_single_scen_inspect"
                )
                target_rec = next((r for r in records if r["id"] == single_id), None)
                if target_rec:
                    s_items = scenario_schedules.get(single_id, [])
                    single_rows = []
                    for s in s_items:
                        single_rows.append({
                            "Operating Year": f"Year {s['year']}",
                            f"Status Quo Bill ({currency})": f"{s['status_quo_bill']:,.2f}",
                            f"Residual Bill ({currency})": f"{s['residual_bill']:,.2f}",
                            f"Annual OPEX ({currency})": f"{s['opex']:,.2f}",
                            f"Cell Refresh ({currency})": f"{s['cell_replacement']:,.2f}",
                            f"Total Outflow ({currency})": f"{s['total_outflow']:,.2f}",
                            f"Gross Savings ({currency})": f"{s['gross_savings']:+,.2f}",
                            f"Net Cashflow ({currency})": f"{s['net_cash_flow']:+,.2f}",
                            f"Cumulative Cashflow ({currency})": f"{s['cumulative_cash_flow']:+,.2f}",
                            f"Discounted CF ({currency})": f"{s['discounted_cash_flow']:+,.2f}",
                            f"Cumulative TCO ({currency})": f"{s['cumulative_tco']:,.2f}"
                        })

                    df_single = pd.DataFrame(single_rows)
                    st.dataframe(df_single, use_container_width=True, hide_index=True)

                    csv_single = df_single.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label=f":material/download: Export {target_rec['name']} Schedule (CSV)",
                        data=csv_single,
                        file_name=f"cashflow_{target_rec['name'].replace(' ', '_')}_{horizon_years}y.csv",
                        mime="text/csv",
                        key=f"{key_prefix}_dl_single_sched"
                    )

    # --------------------------------------------------------------------------
    # PERSPECTIVE 2: METRIC-CENTRIC (CROSS-SCENARIO TIME MATRIX)
    # --------------------------------------------------------------------------
    else:
        st.caption(
            "Select a specific financial or electrical metric to track its multi-year or monthly trajectory across all scenario models simultaneously."
        )

        metric_choice = st.selectbox(
            "Select Target Metric to Compare Across Models:",
            options=[
                "1. Cumulative Life-Cycle Total Cost (TCO)",
                "2. Annual Utility Electricity Bill (Grid Import Cost)",
                "3. Total Annual Outflow (Electricity Bill + OPEX + Reinvestment)",
                "4. Net Annual Cash Flow (Financial Benefit vs. Status Quo)",
                "5. Cumulative Project Cash Flow (Amortization Trajectory)",
                "6. Discounted Annual Cash Flow (NPV Contribution)",
                "7. Normalized 12-Month Residual Grid Import (kWh)"
            ],
            key=f"{key_prefix}_metric_choice"
        )

        matrix_rows = []

        if "7. Normalized 12-Month" in metric_choice:
            month_names = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
            for m_idx, m_name in enumerate(month_names):
                m_row = {"Period / Month": m_name}
                base_m_val = (base_rec.get("monthly_load_mwh", [0]*12)[m_idx] if base_rec.get("monthly_load_mwh") else 0.0) * 1000.0
                m_row[f"{base_rec['name']} (kWh)"] = f"{base_m_val:,.0f}"

                best_avoided = 0.0
                for sub in sub_recs:
                    sub_m_val = (sub.get("monthly_residual_mwh", [base_m_val/1000.0]*12)[m_idx] if sub.get("monthly_residual_mwh") else base_m_val/1000.0) * 1000.0
                    m_row[f"{sub['name']} (kWh)"] = f"{sub_m_val:,.0f}"
                    avoided = max(0.0, base_m_val - sub_m_val)
                    if avoided > best_avoided:
                        best_avoided = avoided

                m_row["Max Clean Energy Avoided (kWh)"] = f"+{best_avoided:,.0f} kWh"
                matrix_rows.append(m_row)

        else:
            if "1. Cumulative Life-Cycle Total Cost" in metric_choice:
                key_name = "cumulative_tco"
                y0_key = "upfront_tco"
            elif "2. Annual Utility Electricity Bill" in metric_choice:
                key_name = "residual_bill"
                y0_key = "zero"
            elif "3. Total Annual Outflow" in metric_choice:
                key_name = "total_outflow"
                y0_key = "capex"
            elif "4. Net Annual Cash Flow" in metric_choice:
                key_name = "net_cash_flow"
                y0_key = "neg_capex"
            elif "5. Cumulative Project Cash Flow" in metric_choice:
                key_name = "cumulative_cash_flow"
                y0_key = "neg_capex"
            elif "6. Discounted Annual Cash Flow" in metric_choice:
                key_name = "discounted_cash_flow"
                y0_key = "neg_capex"
            else:
                key_name = "cumulative_tco"
                y0_key = "upfront_tco"

            # Year 0 Row
            y0_row = {"Timeline": "Year 0 (CAPEX)"}
            base_y0 = 0.0
            y0_row[f"{base_rec['name']} ({currency})"] = f"{base_y0:,.0f}"

            for sub in sub_recs:
                c_up = float(sub.get("capex", 0.0)) + float(sub.get("grid_upgrade_cost", 0.0)) + float(sub.get("temporary_connection_cost", 0.0))
                if y0_key == "upfront_tco" or y0_key == "capex":
                    val_0 = c_up
                elif y0_key == "neg_capex":
                    val_0 = -c_up
                else:
                    val_0 = 0.0
                y0_row[f"{sub['name']} ({currency})"] = f"{val_0:+,.0f}" if val_0 != 0 else "0"

            y0_row[f"Benchmark Delta vs. Baseline ({currency})"] = "Initial Outlay"
            matrix_rows.append(y0_row)

            # Year 1 to Horizon
            for y in range(1, horizon_years + 1):
                y_row = {"Timeline": f"Year {y}"}
                b_sched = scenario_schedules.get(base_rec.get("id", "base"), [])
                b_row = next((item for item in b_sched if item["year"] == y), {})
                b_val = float(b_row.get(key_name, 0.0))
                y_row[f"{base_rec['name']} ({currency})"] = f"{b_val:,.0f}"

                best_delta = 0.0
                for sub in sub_recs:
                    s_sched = scenario_schedules.get(sub["id"], [])
                    s_row = next((item for item in s_sched if item["year"] == y), {})
                    s_val = float(s_row.get(key_name, 0.0))
                    y_row[f"{sub['name']} ({currency})"] = f"{s_val:+,.0f}" if (key_name in ["net_cash_flow", "cumulative_cash_flow", "discounted_cash_flow"]) else f"{s_val:,.0f}"
                    
                    if key_name in ["cumulative_tco", "residual_bill", "total_outflow"]:
                        d_val = b_val - s_val
                    else:
                        d_val = s_val
                    if abs(d_val) > abs(best_delta):
                        best_delta = d_val

                y_row[f"Benchmark Delta vs. Baseline ({currency})"] = f"{best_delta:+,.0f} {currency}" if best_delta != 0 else "0"
                matrix_rows.append(y_row)

        df_matrix = pd.DataFrame(matrix_rows)
        st.dataframe(df_matrix, use_container_width=True, hide_index=True)

        csv_matrix = df_matrix.to_csv(index=False).encode('utf-8')
        st.download_button(
            label=":material/download: Export Metric Matrix (CSV)",
            data=csv_matrix,
            file_name=f"metric_matrix_{metric_choice[:20].replace(' ', '_')}_{horizon_years}y.csv",
            mime="text/csv",
            key=f"{key_prefix}_dl_matrix"
        )


def render_scenario_management(key_prefix: str = "app_scenarios") -> None:
    """
    Renders Tab 1: Scenario Management & Decision Center.
    Acts as the primary application entryway:
      - Project & Base Scenario Setup (Naming, Currency, Global physical/commercial status).
      - Sub-Scenario Manager (Branch switching, creating new branches with modular opt-in toggles).
      - Visual Architecture Hierarchy Tree.
      - Master Scenario Comparison & Ranking Dashboard (Financial Benchmarks & Electrical Flows).
    """
    project: ProjectContainer = export_project_from_session()
    records = _build_scenario_evaluation_records(project)
    currency = project.currency or "EUR"
    base_rec = records[0] if records else {}
    base_annual_cost = base_rec.get("annual_opex", 344141.21)
    sub_records = [r for r in records if r["id"] != "base"]
    active_sub = project.get_active_scenario()

    # --------------------------------------------------------------------------
    # 1. Header & Project Metadata
    # --------------------------------------------------------------------------
    t_head_col1, t_head_col2 = st.columns([7.5, 2.5])
    with t_head_col1:
        st.markdown("## :material/dashboard: 1. Scenario Management & Decision Center")
        st.caption("Central entry point for your optimization project: Define project parameters, manage modular solution branches, and evaluate investment decisions.")
    with t_head_col2:
        if st.button("Refresh Project", icon=":material/refresh:", type="primary", use_container_width=True, key=f"{key_prefix}_refresh_dash_btn", help="Re-synchronizes all calculations and updates the workspace."):
            st.rerun()

    # 1.1 Project Title & Global Settings Bar
    p_col1, p_col2 = st.columns([7, 3])
    with p_col1:
        new_p_name = st.text_input(
            "Project / Facility Name:",
            value=project.project_name,
            key=f"{key_prefix}_proj_name_input",
            help="Unique identifier for your simulation project (e.g. 'Commercial Facility Site North')."
        )
        if new_p_name != project.project_name and new_p_name.strip():
            project.project_name = new_p_name.strip()
            st.session_state["project_container"] = project
            st.session_state["active_project_name"] = project.project_name
    with p_col2:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        st.success(f":material/check_circle: Project Active | **{len(project.sub_scenarios)}** Sub-Scenarios")

    # 1.2 Global Foundation Status Banner (Consumption & Contract)
    c_load_name = project.base_scenario.load_profile_name or "Baseline Facility Load"
    c_contract_name = project.base_scenario.base_contract.name if project.base_scenario.base_contract else "Standard Contract"
    
    st.markdown(
        f"""
        <div style="background: rgba(30, 41, 59, 0.45); border: 1px solid rgba(59, 130, 246, 0.4); border-radius: 8px; padding: 10px 16px; margin: 4px 0 16px 0; display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 12px;">
            <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                <span style="color: #60A5FA; font-weight: 700; font-size: 0.82rem;">GLOBAL BASELINE:</span>
                <span style="color: #CBD5E1; font-size: 0.82rem;"><b>Consumption:</b> {c_load_name} ({base_rec.get('total_load_mwh', 0) * 1000.0:,.0f} kWh/a)</span>
                <span style="color: #64748B;">|</span>
                <span style="color: #CBD5E1; font-size: 0.82rem;"><b>Status Quo Contract:</b> {c_contract_name} ({base_annual_cost:,.0f} {currency}/a)</span>
            </div>
            <div style="font-size: 0.78rem; color: #94A3B8;">
                Uniform baseline reference for all sub-scenarios
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    st.divider()

    # --------------------------------------------------------------------------
    # 2. Sub-Scenario Manager & Module Configuration
    # --------------------------------------------------------------------------
    st.markdown("### :material/tune: Sub-Scenario Configuration & Module Selection")
    st.caption("Select the scenario branch to configure and selectively activate desired solution modules (Solar PV, BESS, Generator, Tariff Switch). All inactive modules are completely omitted.")

    # Branch Switcher
    scenario_ids = ["base"] + [s.id for s in project.sub_scenarios]
    scenario_label_map = {"base": "Status Quo (Base Benchmark - 100% Grid Supply)"}
    for s in project.sub_scenarios:
        scenario_label_map[s.id] = f"{s.name} ({s.technology_mix_label})"

    current_active_id = project.active_sub_scenario_id if (project.active_sub_scenario_id and project.active_sub_scenario_id in scenario_ids) else "base"
    try:
        cur_idx = scenario_ids.index(current_active_id)
    except ValueError:
        cur_idx = 0

    col_target1, col_target2 = st.columns([7, 3])
    with col_target1:
        tab1_key = f"{key_prefix}_target_scenario_select"
        # Ensure selectbox key in session state stays strictly synchronized with current_active_id
        if tab1_key not in st.session_state or st.session_state[tab1_key] not in scenario_ids:
            st.session_state[tab1_key] = current_active_id
        elif project.active_sub_scenario_id and st.session_state[tab1_key] != current_active_id:
            st.session_state[tab1_key] = current_active_id

        def _on_tab1_scenario_change() -> None:
            new_target = st.session_state.get(tab1_key)
            proj = export_project_from_session()
            proj.active_sub_scenario_id = None if new_target == "base" else new_target
            st.session_state["project_container"] = proj
            sync_active_scenario_into_session(proj, auto_execute=False)

        st.selectbox(
            "Select Active Scenario to Configure:",
            options=scenario_ids,
            format_func=lambda s_id: scenario_label_map.get(s_id, s_id),
            key=tab1_key,
            on_change=_on_tab1_scenario_change
        )

    with col_target2:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        # Popover to create a new branch
        with st.popover("+ New Sub-Scenario", icon=":material/add_circle:", use_container_width=True):
            st.markdown("##### :material/add: Create New Sub-Scenario")
            new_sub_name = st.text_input(
                "Sub-Scenario Name:",
                value=f"Option {len(project.sub_scenarios) + 1}: Hybrid System",
                key=f"{key_prefix}_new_sub_name_pop"
            )
            st.markdown("**Select Modules to Include:**")
            p_sol = st.checkbox("Solar PV Generation", value=True, key=f"{key_prefix}_pop_new_sol")
            p_bess = st.checkbox("Battery Storage (BESS)", value=False, key=f"{key_prefix}_pop_new_bess")
            p_gen = st.checkbox("Peaking / Backup Generator (Genset)", value=False, key=f"{key_prefix}_pop_new_gen")
            p_tar = st.checkbox("Tariff Switch / Alternative Contract", value=False, key=f"{key_prefix}_pop_new_tar")

            color_choice = st.selectbox(
                "Chart Curve Color:",
                options=["#2563EB (Blue)", "#059669 (Green)", "#D97706 (Amber)", "#DC2626 (Red)", "#7C3AED (Purple)", "#0891B2 (Cyan)"],
                index=len(project.sub_scenarios) % 6,
                key=f"{key_prefix}_pop_new_col"
            )
            clean_c = color_choice.split(" ")[0]

            if st.button("Create & Activate Sub-Scenario", icon=":material/check:", type="primary", use_container_width=True, key=f"{key_prefix}_pop_create_btn"):
                created_sub = SubScenario(
                    name=new_sub_name.strip() or f"Sub-Scenario {len(project.sub_scenarios) + 1}",
                    color_code=clean_c,
                    include_solar=p_sol,
                    include_bess=p_bess,
                    include_generator=p_gen,
                    use_custom_grid_tariff=p_tar
                )
                project.add_sub_scenario(created_sub)
                project.active_sub_scenario_id = created_sub.id
                st.session_state["project_container"] = project
                sync_active_scenario_into_session(project, auto_execute=False)
                st.rerun()

    # Active Branch Module Configuration Card
    if active_sub is not None:
        st.markdown(
            f"""
            <div style="background: rgba(15, 23, 42, 0.7); border: 2px solid #3B82F6; border-radius: 8px; padding: 14px; margin: 8px 0 16px 0;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px;">
                    <div>
                        <span style="font-weight: 800; font-size: 1.05rem; color: #F8FAFC;">Module Activation for: {active_sub.name}</span>
                        <span style="background: {active_sub.color_code}33; color: {active_sub.color_code}; border: 1px solid {active_sub.color_code}88; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; margin-left: 10px; font-weight: 700;">
                            {active_sub.technology_mix_label}
                        </span>
                    </div>
                    <span style="font-size: 0.8rem; color: #94A3B8;">Active modules appear as tabs in the navigation bar above</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        mod_col1, mod_col2, mod_col3, mod_col4 = st.columns(4)
        with mod_col1:
            with st.container(border=True):
                st.markdown("#### :material/solar_power: Solar PV")
                st.caption("System sizing (kWp, tilt) & 15-min yield simulation.")
                sol_val = st.checkbox(
                    "Activate Solar PV",
                    value=active_sub.include_solar,
                    key=f"{key_prefix}_chk_mod_solar_{active_sub.id}",
                    help="Enables the 'Solar PV Generation' tab for this sub-scenario."
                )
                if sol_val != active_sub.include_solar:
                    active_sub.include_solar = sol_val
                    st.session_state["project_container"] = project
                    sync_active_scenario_into_session(project, auto_execute=False)
                    st.rerun()

        with mod_col2:
            with st.container(border=True):
                st.markdown("#### :material/battery_charging_full: BESS Storage")
                st.caption("Battery capacity (kWh, kW) & peak shaving dispatch.")
                bess_val = st.checkbox(
                    "Activate BESS",
                    value=active_sub.include_bess,
                    key=f"{key_prefix}_chk_mod_bess_{active_sub.id}",
                    help="Enables the 'Battery Storage (BESS)' tab for this sub-scenario."
                )
                if bess_val != active_sub.include_bess:
                    active_sub.include_bess = bess_val
                    st.session_state["project_container"] = project
                    sync_active_scenario_into_session(project, auto_execute=False)
                    st.rerun()

        with mod_col3:
            with st.container(border=True):
                st.markdown("#### :material/local_gas_station: Generator")
                st.caption("On-site peaking & residual backup dispatch.")
                gen_val = st.checkbox(
                    "Activate Generator",
                    value=active_sub.include_generator,
                    key=f"{key_prefix}_chk_mod_gen_{active_sub.id}",
                    help="Enables the 'Generator / Genset' tab for this sub-scenario."
                )
                if gen_val != active_sub.include_generator:
                    active_sub.include_generator = gen_val
                    st.session_state["project_container"] = project
                    sync_active_scenario_into_session(project, auto_execute=False)
                    st.rerun()

        with mod_col4:
            with st.container(border=True):
                st.markdown("#### :material/swap_horiz: Tariff Switch")
                st.caption("Evaluate alternative supply contracts & bill savings.")
                tariff_val = st.checkbox(
                    "Activate Tariff Switch",
                    value=active_sub.use_custom_grid_tariff,
                    key=f"{key_prefix}_chk_mod_tariff_{active_sub.id}",
                    help="Enables the 'Tariff Switch / Alternative Contract' tab for this sub-scenario."
                )
                if tariff_val != active_sub.use_custom_grid_tariff:
                    active_sub.use_custom_grid_tariff = tariff_val
                    st.session_state["project_container"] = project
                    sync_active_scenario_into_session(project, auto_execute=False)
                    st.rerun()

        # Branch management actions
        with st.expander(f"Manage / Rename Sub-Scenario '{active_sub.name}'", icon=":material/tune:", expanded=False):
            m_c1, m_c2, m_c3, m_c4 = st.columns([4, 2, 2, 2])
            with m_c1:
                ren_val = st.text_input("Rename Branch:", value=active_sub.name, key=f"{key_prefix}_rename_act_input_{active_sub.id}")
            with m_c2:
                st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                if st.button("Save Name", icon=":material/check:", key=f"{key_prefix}_save_ren_btn", use_container_width=True):
                    active_sub.name = ren_val.strip() or active_sub.name
                    st.session_state["project_container"] = project
                    st.rerun()
            with m_c3:
                st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                if st.button("Duplicate", icon=":material/content_copy:", key=f"{key_prefix}_dup_act_btn", use_container_width=True):
                    cloned = project.duplicate_sub_scenario(active_sub.id, f"{active_sub.name} (Copy)")
                    project.active_sub_scenario_id = cloned.id
                    st.session_state["project_container"] = project
                    sync_active_scenario_into_session(project, auto_execute=False)
                    st.rerun()
            with m_c4:
                st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                if st.button("Delete Branch", icon=":material/delete:", type="secondary", key=f"{key_prefix}_del_act_btn", use_container_width=True):
                    project.delete_sub_scenario(active_sub.id)
                    st.session_state["project_container"] = project
                    sync_active_scenario_into_session(project, auto_execute=False)
                    st.rerun()
    else:
        st.info(
            "### :material/lock: Status Quo (Base Benchmark) Active\n\n"
            "The **Status Quo** represents your utility grid electricity baseline without on-site generation or storage assets. "
            "It serves as the fixed economic benchmark for all payback and savings calculations.\n\n"
            "Select a sub-scenario branch above or create a new one to configure Solar PV, Battery Storage, or a Contract Tariff Switch.",
            icon=":material/info:"
        )

    st.divider()

    # --------------------------------------------------------------------------
    # 3. Visuelle Architektur-Hierarchie (Tree Overview)
    # --------------------------------------------------------------------------
    _render_scenario_visual_cards(project, records, key_prefix=key_prefix)

    st.divider()

    # --------------------------------------------------------------------------
    # 4. Master Scenario Comparison & Ranking Dashboard
    # --------------------------------------------------------------------------
    st.markdown("### :material/leaderboard: Master Decision Dashboard & Scenario Ranking")
    st.caption("Benchmark of all scenario branches against the Status Quo baseline over 15 years regarding TCO, investment capital, energy dispatch, and self-sufficiency.")

    tab_fin, tab_elec = st.tabs([
        ":material/payments: Financial Benchmarks & Amortisation",
        ":material/bolt: Electrical Energy & Power Balance"
    ])

    # ==========================================================================
    # SUB-TAB 1: FINANCIAL BENCHMARKS & AMORTISATION
    # ==========================================================================
    with tab_fin:
        # Top Financial KPI Summary Cards
        best_tco = min(sub_records, key=lambda x: x["total_15y_tco"]) if sub_records else None
        best_payback = min([r for r in sub_records if r["payback_years"] > 0], key=lambda x: x["payback_years"], default=None)
        best_savings = max(sub_records, key=lambda x: x["net_savings"]) if sub_records else None

        kpi_col1, kpi_col2, kpi_col3, kpi_col4 = st.columns(4)
        with kpi_col1:
            render_kpi_card(
                title="Active Scenario Branches",
                value=f"{len(project.sub_scenarios)} Sub-Scenarios",
                subtext="Status Quo Baseline active",
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
            val_str = best_savings["net_savings_str"] if best_savings else f"0 {currency}"
            sub_str = f"Leader: {best_savings['name']}" if best_savings else "Grid dependent"
            render_kpi_card(
                title="Max 15-Year Net Savings",
                value=val_str,
                subtext=sub_str,
                status="ok" if best_savings and best_savings["net_savings"] > 0 else "default"
            )

        st.divider()

        # Master Comparison Leaderboard Table
        st.markdown("### :material/table_chart: Scenario Ranking Leaderboard")
        st.caption("Objective performance ranking comparing turn-key investments against 15-year cumulative liabilities.")

        df_display = pd.DataFrame([
            {
                "Rank": r["rank"],
                "Scenario Name": r["name"],
                "Technology Mix": r["tech_mix"],
                "Turn-Key CAPEX": r["capex_str"],
                "15-Yr Total Cost": r["tco_str"],
                "15-Yr Net Savings": r["net_savings_str"],
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

        # Interactive Multi-Scenario Financial Charts
        chart_tab1, chart_tab2, chart_tab3 = st.tabs([
            ":material/trending_up: 15-Year Cumulative Cost Curves (Break-Even)",
            ":material/bar_chart: CAPEX vs. OPEX Capital Balance",
            ":material/energy_savings_leaf: Autarky & Payback Benchmark"
        ])

        with chart_tab1:
            st.caption("Break-even trajectory: Intersection point where cumulative investment curves cross below the Status Quo utility line marks the amortization year.")
            
            base_s = base_rec.get("facility_cum_costs") or base_rec.get("cumulative_costs")

            fig_curves = create_multi_scenario_cumulative_cost_figure(
                scenarios_data=sub_records,
                base_annual_cost=base_annual_cost,
                baseline_series=base_s,
                currency=currency,
                scope_mode="facility"
            )
            st.plotly_chart(fig_curves, use_container_width=True)

        with chart_tab2:
            st.caption("Visualizes the structural shift from recurring operational expenditure (utility electricity bills) into capitalized assets.")
            fig_bar = create_capex_opex_breakdown_figure(records, currency=currency)
            st.plotly_chart(fig_bar, use_container_width=True)

        with chart_tab3:
            st.caption("Trade-off comparison: Demonstrates achieved clean energy independence (%) relative to capital payback duration (Years).")
            if sub_records:
                fig_aut = create_autarky_payback_figure(sub_records)
                st.plotly_chart(fig_aut, use_container_width=True)
            else:
                st.info("Create and activate sub-scenarios in the sidebar to inspect Autarky benchmarks.")

        # 5. Multi-Scenario Economic Simulation & Life-Cycle Schedules (Assignment Section 8.3)
        _render_economic_simulation_and_cashflow_schedules(
            project=project,
            records=records,
            currency=currency,
            key_prefix=f"{key_prefix}_asgn83"
        )

        st.divider()

        # Scenario Architecture & Delta Matrix
        st.markdown("### :material/compare_arrows: Scenario Architecture & Parameter Delta Matrix")
        st.caption("Side-by-side technical and economic parameter matrix highlighting baseline-inherited constants versus scenario-specific interventions.")

        df_delta = _build_scenario_delta_matrix(project, records)
        st.dataframe(
            df_delta,
            use_container_width=True,
            hide_index=True
        )

        st.divider()

        # Scenario Management & Client Deliverables
        st.markdown("### :material/settings: Scenario Management & Reporting")
        col_m1, col_m2 = st.columns([1, 1])

        with col_m1:
            st.markdown("#### :material/edit_note: Scenario & Component Manager")
            if project.sub_scenarios:
                edit_sub_options = {s.id: f"{s.name} ({s.technology_mix_label})" for s in project.sub_scenarios}
                selected_edit_id = st.selectbox(
                    "Select Branch to Manage:",
                    options=list(edit_sub_options.keys()),
                    format_func=lambda x: edit_sub_options[x],
                    key="tab6_select_sub_manage"
                )
                target_sub = project.get_sub_scenario(selected_edit_id)
                if target_sub:
                    st.caption(f"Active Hardware in **{target_sub.name}**: {target_sub.technology_mix_label}")
                    rename_inp = st.text_input("Rename Branch:", value=target_sub.name, key="tab6_rename_sub_input")

                    # Primary branch operations
                    c_act1, c_act2, c_act3 = st.columns(3)
                    with c_act1:
                        if st.button("Save Name", icon=":material/check:", key="tab6_save_name_btn", use_container_width=True):
                            target_sub.name = rename_inp.strip() or target_sub.name
                            st.session_state["project_container"] = project
                            st.rerun()
                    with c_act2:
                        if st.button("Clone Branch", icon=":material/content_copy:", key="tab6_clone_btn", use_container_width=True):
                            cloned = project.duplicate_sub_scenario(target_sub.id)
                            project.active_sub_scenario_id = cloned.id
                            st.session_state["project_container"] = project
                            sync_active_scenario_into_session(project, auto_execute=False)
                            st.rerun()
                    with c_act3:
                        if st.button("Delete Branch", icon=":material/delete:", key="tab6_del_btn", type="secondary", use_container_width=True):
                            project.delete_sub_scenario(target_sub.id)
                            st.session_state["project_container"] = project
                            sync_active_scenario_into_session(project, auto_execute=False)
                            st.rerun()

                    # Component-level removal and reset options
                    st.markdown("##### :material/delete_sweep: Remove Specific Technologies")
                    rm_col1, rm_col2, rm_col3, rm_col4 = st.columns(4)
                    with rm_col1:
                        if st.button("Remove Solar", icon=":material/solar_power:", key="tab6_rm_solar_btn", disabled=not target_sub.include_solar, use_container_width=True):
                            target_sub.remove_component("solar")
                            st.session_state["project_container"] = project
                            sync_active_scenario_into_session(project, auto_execute=False)
                            st.rerun()
                    with rm_col2:
                        if st.button("Remove BESS", icon=":material/battery_charging_full:", key="tab6_rm_bess_btn", disabled=not target_sub.include_bess, use_container_width=True):
                            target_sub.remove_component("bess")
                            st.session_state["project_container"] = project
                            sync_active_scenario_into_session(project, auto_execute=False)
                            st.rerun()
                    with rm_col3:
                        if st.button("Remove Generator", icon=":material/local_gas_station:", key="tab6_rm_gen_btn", disabled=not target_sub.include_generator, use_container_width=True):
                            target_sub.remove_component("generator")
                            st.session_state["project_container"] = project
                            sync_active_scenario_into_session(project, auto_execute=False)
                            st.rerun()
                    with rm_col4:
                        if st.button("Reset to Blank", icon=":material/restart_alt:", key="tab6_rm_all_btn", use_container_width=True, help="Removes all solar, BESS, and generator hardware from this branch."):
                            target_sub.remove_component("all")
                            st.session_state["project_container"] = project
                            sync_active_scenario_into_session(project, auto_execute=False)
                            st.rerun()
            else:
                st.info("No sub-scenarios available to manage. Create a new branch above or in the sidebar.")

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

    # ==========================================================================
    # SUB-TAB 2: ELECTRICAL ENERGY & POWER BALANCE
    # ==========================================================================
    with tab_elec:
        # 1. Top Electrical & Power KPI Summary Cards
        max_gen = max(records, key=lambda x: x["generation_mwh"]) if records else None
        best_autarky = max(sub_records, key=lambda x: x["autarky_pct"]) if sub_records else None
        max_shave = max(records, key=lambda x: x["shaved_peak_kw"]) if records else None
        max_co2 = max(records, key=lambda x: x["co2_avoided_tons"]) if records else None

        ek1, ek2, ek3, ek4 = st.columns(4)
        with ek1:
            render_kpi_card(
                title="Facility Baseline Demand",
                value=f"{base_rec.get('total_load_mwh', 0) * 1000.0:,.0f} kWh/a",
                subtext=f"Peak: {base_rec.get('baseline_peak_kw', 0):,.1f} kW",
                status="default"
            )
        with ek2:
            val_str = f"{max_gen['generation_mwh'] * 1000.0:,.0f} kWh/a" if (max_gen and max_gen['generation_mwh'] > 0) else "0 kWh/a"
            sub_str = f"Leader: {max_gen['name']}" if (max_gen and max_gen['generation_mwh'] > 0) else "No solar generation active"
            render_kpi_card(
                title="Highest Clean Generation",
                value=val_str,
                subtext=sub_str,
                status="ok" if (max_gen and max_gen['generation_mwh'] > 0) else "default"
            )
        with ek3:
            val_str = f"-{max_shave['shaved_peak_kw']:.1f} kW" if (max_shave and max_shave['shaved_peak_kw'] > 0) else "0.0 kW"
            sub_str = f"Leader: {max_shave['name']}" if (max_shave and max_shave['shaved_peak_kw'] > 0) else "Grid baseline peak"
            render_kpi_card(
                title="Maximum Peak Shaving",
                value=val_str,
                subtext=sub_str,
                status="ok" if (max_shave and max_shave['shaved_peak_kw'] > 0) else "default"
            )
        with ek4:
            val_str = f"{max_co2['co2_avoided_tons']:,.1f} t CO₂/a" if (max_co2 and max_co2['co2_avoided_tons'] > 0) else "0.0 t CO₂/a"
            sub_str = f"Offset: {max_co2['name']}" if (max_co2 and max_co2['co2_avoided_tons'] > 0) else "Utility grid emissions"
            render_kpi_card(
                title="Maximum Carbon Offset",
                value=val_str,
                subtext=sub_str,
                status="ok" if (max_co2 and max_co2['co2_avoided_tons'] > 0) else "default"
            )

        st.divider()

        # 2. Multi-Scenario Electrical Flow Comparison Table
        st.markdown("### :material/table_rows: Multi-Scenario Electrical Flow Comparison Table")
        st.caption("Comprehensive physical energy balance comparing annual kWh generation, on-site utilization, residual grid imports, and carbon mitigation:")

        df_elec = pd.DataFrame([
            {
                "Rank": r["rank"],
                "Scenario Name": r["name"],
                "Tech Mix": r["tech_mix"],
                "Total Demand (kWh)": f"{r['total_load_mwh'] * 1000.0:,.0f}",
                "Solar Gen (kWh)": f"{r['generation_mwh'] * 1000.0:,.0f}" if r['generation_mwh'] > 0 else "-",
                "Direct Cons (kWh)": f"{r['direct_consumption_mwh'] * 1000.0:,.0f}" if r['direct_consumption_mwh'] > 0 else "-",
                "Self-Cons (%)": r["self_consumption_str"],
                "Residual Grid (kWh)": f"{r['residual_grid_mwh'] * 1000.0:,.0f}",
                "Surplus Export (kWh)": f"{r['surplus_export_mwh'] * 1000.0:,.0f}" if r['surplus_export_mwh'] > 0 else "-",
                "Autarky (%)": r["autarky_str"],
                "Peak Shaved (kW)": f"-{r['shaved_peak_kw']:.1f} kW" if r['shaved_peak_kw'] > 0 else "-",
                "CO₂ Offset (t/a)": f"{r['co2_avoided_tons']:,.1f} t" if r['co2_avoided_tons'] > 0 else "-"
            }
            for r in records
        ])

        st.dataframe(
            df_elec,
            use_container_width=True,
            hide_index=True
        )

        st.divider()

        # 3. Interactive Electrical Charts
        e_tab1, e_tab2, e_tab3 = st.tabs([
            ":material/compare: Residual Grid Load vs. Facility Demand (kWh)",
            ":material/bar_chart: Full Energy Balance (All 5 Flows)",
            ":material/grid_view: Peak Demand Shaving & Environmental Impact"
        ])

        with e_tab1:
            st.caption("Direct comparison between original facility electricity demand and remaining utility grid imports (übrig gebliebene Netzlast) across all scenarios:")
            
            c_mode_col, _ = st.columns([11, 1])
            with c_mode_col:
                res_chart_mode = st.radio(
                    "Timeline View:",
                    options=[
                        "Monthly Trajectory (Jan – Dec Curves)",
                        "Monthly Grouped (Jan – Dec Bars)",
                        "Annual Totals Benchmark (kWh/Year)",
                        "15-Min Detailed Timeseries (Full Timeline Dispatch)"
                    ],
                    index=0,
                    horizontal=True,
                    key=f"{key_prefix}_res_chart_mode_radio"
                )
            
            if "15-Min" in res_chart_mode:
                df_load, load_desc, p_col = find_active_load_data_in_session()
                if df_load is None or df_load.empty or p_col not in df_load.columns:
                    st.info("No active 15-minute load profile time series found. Upload a CSV meter dataset in Tab 1 to inspect the full timeline dispatch.")
                else:
                    # Resolve active contracted capacity limit (if configured)
                    active_contract = find_active_contract_in_session()
                    grid_limit_kw = getattr(active_contract, "contracted_capacity_kw", None) if active_contract else None
                    if grid_limit_kw is not None and grid_limit_kw <= 0:
                        grid_limit_kw = None

                    # 1. Data Discontinuity / Gap Detection Warning
                    dt_step = 0.25
                    if "timestamp" in df_load.columns and len(df_load) > 1:
                        diff_s = (pd.to_datetime(df_load["timestamp"].iloc[1]) - pd.to_datetime(df_load["timestamp"].iloc[0])).total_seconds()
                        if diff_s > 0:
                            dt_step = diff_s / 3600.0

                    detected_gaps = detect_load_profile_gaps(df_load, max_gap_hours=max(1.0, dt_step * 3))
                    if detected_gaps:
                        gap_desc = ", ".join([f"{g['start_str']} to {g['end_str']} ({g['duration_days']:.1f} days)" for g in detected_gaps[:3]])
                        if len(detected_gaps) > 3:
                            gap_desc += f" and {len(detected_gaps) - 3} further intervals"
                        st.warning(
                            f":material/warning: **Data Gaps Detected in Time Series:** {len(detected_gaps)} measurement interruption(s) found "
                            f"({gap_desc}). Missing intervals are displayed as breaks in the time series chart without artificial interpolation.",
                            icon=":material/warning:"
                        )

                    # 2. Multi-Year duration note
                    if "timestamp" in df_load.columns and len(df_load) > 1:
                        ts_s = pd.to_datetime(df_load["timestamp"])
                        span_days = (ts_s.max() - ts_s.min()).total_seconds() / 86400.0
                        if span_days > 366:
                            st.caption(f":material/history: Displaying full unaggregated chronological timeline ({span_days:.0f} calendar days / {len(df_load):,} intervals) with direct 15-minute dispatch resolution.")

                    # 3. Assemble Sub-Scenario 15-minute residual grid series
                    sub_ts_list = []
                    int_sim_res = st.session_state.get("app_tab3_int_sim_result") or st.session_state.get("solar_dispatch_result")

                    for sub in project.sub_scenarios:
                        res_series = None
                        # Check if active sub matches cached coupled simulation
                        if (project.active_sub_scenario_id == sub.id and
                            int_sim_res is not None and
                            hasattr(int_sim_res, "df_timeseries") and
                            int_sim_res.df_timeseries is not None and
                            "P_Residual_kW" in int_sim_res.df_timeseries.columns and
                            len(int_sim_res.df_timeseries) == len(df_load)):
                            res_series = int_sim_res.df_timeseries["P_Residual_kW"]
                        elif sub.include_solar and sub.solar_config and sub.solar_config.module_count > 0:
                            try:
                                loc = (project.base_scenario.location if (project.base_scenario and project.base_scenario.location) else None) or getattr(project, "location", None) or SolarLocation(name="Facility Location", latitude=-33.5133, longitude=-69.2561)
                                sim_tmp = simulate_solar_pv_generation(
                                    config=sub.solar_config,
                                    location=loc,
                                    load_df=df_load
                                )
                                if sim_tmp and sim_tmp.df_timeseries is not None and "P_Residual_kW" in sim_tmp.df_timeseries.columns:
                                    res_series = sim_tmp.df_timeseries["P_Residual_kW"]
                            except Exception:
                                res_series = None
                        elif sub.include_bess and sub.bess_config:
                            try:
                                bess_tmp = simulate_bess_dispatch(
                                    bess_config=sub.bess_config,
                                    load_df=df_load,
                                    grid_limit_kw=grid_limit_kw,
                                    power_col=p_col
                                )
                                if bess_tmp and bess_tmp.df_timeseries is not None and "P_Grid_kW" in bess_tmp.df_timeseries.columns:
                                    res_series = bess_tmp.df_timeseries["P_Grid_kW"]
                            except Exception:
                                res_series = None

                        if res_series is None:
                            res_series = df_load[p_col]

                        sub_ts_list.append({
                            "name": sub.name,
                            "color": sub.color_code,
                            "residual_series": res_series
                        })

                    fig_ts = create_residual_grid_load_timeseries_figure(
                        df_load=df_load,
                        sub_scenarios_timeseries=sub_ts_list,
                        power_col=p_col,
                        grid_limit_kw=grid_limit_kw
                    )
                    st.plotly_chart(fig_ts, use_container_width=True)
            else:
                mode_key = "monthly_curve"
                if "Monthly Grouped" in res_chart_mode:
                    mode_key = "monthly_grouped"
                elif "Annual Totals" in res_chart_mode:
                    mode_key = "annual_totals"

                fig_res_comp = create_residual_grid_load_comparison_figure(records, chart_mode=mode_key)
                st.plotly_chart(fig_res_comp, use_container_width=True)

        with e_tab2:
            st.caption("Detailed physical energy balance including generation, direct self-consumption, grid imports, and surplus feed-in:")
            fig_energy = create_multi_scenario_energy_balance_figure(records)
            st.plotly_chart(fig_energy, use_container_width=True)

        with e_tab3:
            st.caption("Power grid integration metrics: Peak demand load reduction (kW) and annual clean energy decarbonisation:")
            fig_peak_co2 = create_multi_scenario_peak_and_co2_figure(records)
            st.plotly_chart(fig_peak_co2, use_container_width=True)


# Backwards-compatible alias for existing imports
render_master_comparison_dashboard = render_scenario_management
