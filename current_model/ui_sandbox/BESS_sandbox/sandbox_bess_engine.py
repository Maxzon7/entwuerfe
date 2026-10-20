"""
========================================================================================
BESS Sandbox: Enhanced Calculation & Economics Engine (sandbox_bess_engine.py)
========================================================================================

Engine refinements for the standalone BESS sandbox:
  1. Gross vs. Net Minimum Sizing (DoD & discharge efficiency accounting).
  2. Dynamic Storage Degradation Model (Calendar age, EFC cycles, and ambient temperature).
  3. Realistic Baseline vs. BESS Financial Delta Accounting:
     - Month-by-month peak demand reduction (kW-max)
     - Contracted capacity shifts (GTV optimization)
     - Avoided grid connection upgrade CAPEX (e.g., MV transformer station)
     - Avoided recurring transformer rental fees
     - Conversion round-trip losses & mid-life cell overhaul
========================================================================================
"""

import os
import sys
from typing import Dict, Any, List, Optional, Tuple, Union
from dataclasses import dataclass, field
import numpy as np
import pandas as pd

# Path bootstrapping
CURRENT_DIR = os.path.abspath(os.path.dirname(__file__))
UI_SANDBOX_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
CURRENT_MODEL_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
WORKSPACE_DIR = os.path.abspath(os.path.join(CURRENT_MODEL_DIR, ".."))
for p in [CURRENT_DIR, UI_SANDBOX_DIR, CURRENT_MODEL_DIR, WORKSPACE_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

# Production Models & Engines
try:
    from current_model.models.bess import BESSConfig, BESSKPIs, BESSFinancialMetrics
    from current_model.models.contract import Contract
    from current_model.core.bess_engine import (
        analyze_grid_violations,
        simulate_bess_dispatch,
        compute_average_week_dispatch,
        BESSSimulationResult,
    )
    from current_model.core.bess_financial_engine import _calculate_irr
    from current_model.core.financial_engine import compute_financial_bill
except ImportError:
    from models.bess import BESSConfig, BESSKPIs, BESSFinancialMetrics
    from models.contract import Contract
    from core.bess_engine import (
        analyze_grid_violations,
        simulate_bess_dispatch,
        compute_average_week_dispatch,
        BESSSimulationResult,
    )
    from core.bess_financial_engine import _calculate_irr
    from core.financial_engine import compute_financial_bill


def simulate_sandbox_bess_dispatch(
    bess_config: BESSConfig,
    load_df: pd.DataFrame,
    grid_limit_kw: float,
    step_hours: float = 0.25,
    power_col: Optional[str] = None
) -> BESSSimulationResult:
    """Wrapper around simulate_bess_dispatch for sandbox convenience."""
    return simulate_bess_dispatch(
        bess_config=bess_config,
        load_df=load_df,
        grid_limit_kw=grid_limit_kw,
        step_hours=step_hours,
        power_col=power_col
    )


@dataclass
class GrossSizingRecommendation:
    """Gross battery nameplate sizing recommendations based on load diagnostics."""
    net_deficit_energy_kwh: float
    overload_peak_kw: float
    usable_dod_pct: float
    one_way_efficiency_pct: float
    min_gross_capacity_kwh: float
    min_continuous_power_kw: float
    recommended_unit_count: int
    recommended_unit_capacity_kwh: float
    recommended_total_capacity_kwh: float
    recommended_inverter_power_kw: float
    c_rate_discharge: float
    description: str


def compute_gross_minimum_bess_sizing(
    diagnostics: Dict[str, Any],
    round_trip_efficiency_pct: float = 90.0,
    soc_min_pct: float = 10.0,
    soc_max_pct: float = 95.0,
    safety_margin_pct: float = 10.0
) -> GrossSizingRecommendation:
    """
    Computes true gross battery nameplate capacity accounting for:
      - Usable DoD (SoC_max - SoC_min)
      - One-way discharge inverter efficiency (sqrt(RTE))
      - Worst continuous overload event energy
      - Peak overload power with safety margin
    """
    net_kwh = float(diagnostics.get("worst_event_energy_kwh", 0.0))
    peak_overload_kw = float(diagnostics.get("overload_peak_kw", 0.0))

    if net_kwh <= 0.0 or peak_overload_kw <= 0.0:
        return GrossSizingRecommendation(
            net_deficit_energy_kwh=0.0,
            overload_peak_kw=0.0,
            usable_dod_pct=max(10.0, soc_max_pct - soc_min_pct),
            one_way_efficiency_pct=np.sqrt(round_trip_efficiency_pct / 100.0) * 100.0,
            min_gross_capacity_kwh=0.0,
            min_continuous_power_kw=0.0,
            recommended_unit_count=1,
            recommended_unit_capacity_kwh=50.0,
            recommended_total_capacity_kwh=50.0,
            recommended_inverter_power_kw=50.0,
            c_rate_discharge=1.0,
            description="No grid overloads detected. Nominal benchmark storage setup."
        )

    dod_frac = max(0.20, min(1.0, (soc_max_pct - soc_min_pct) / 100.0))
    rte_frac = max(0.50, min(1.0, round_trip_efficiency_pct / 100.0))
    eta_dis = np.sqrt(rte_frac)

    # True Gross Energy: E_nom = E_net / (DoD * eta_dis)
    raw_gross_kwh = net_kwh / (dod_frac * eta_dis)
    margin_factor = 1.0 + (safety_margin_pct / 100.0)
    buffered_gross_kwh = raw_gross_kwh * margin_factor

    # Inverter Power: deliver peak overload with safety margin
    min_power_kw = peak_overload_kw
    buffered_power_kw = min_power_kw * margin_factor

    # Modular unit packaging (standard 50 kWh, 100 kWh, or 250 kWh modular blocks)
    if buffered_gross_kwh <= 120.0:
        unit_cap = 50.0
    elif buffered_gross_kwh <= 450.0:
        unit_cap = 100.0
    else:
        unit_cap = 250.0

    unit_count = max(1, int(np.ceil(buffered_gross_kwh / unit_cap)))
    rec_total_kwh = float(unit_count * unit_cap)
    rec_inverter_kw = float(np.ceil(buffered_power_kw / 10.0) * 10.0)

    c_rate = round(rec_inverter_kw / max(1.0, rec_total_kwh), 2)

    desc = (
        f"Requires at least {buffered_gross_kwh:.1f} kWh gross nameplate capacity and "
        f"{buffered_power_kw:.1f} kW continuous power to eliminate worst-case "
        f"{net_kwh:.1f} kWh deficit across {diagnostics.get('worst_event_duration_hours', 0.0):.2f} hours."
    )

    return GrossSizingRecommendation(
        net_deficit_energy_kwh=round(net_kwh, 1),
        overload_peak_kw=round(peak_overload_kw, 1),
        usable_dod_pct=round(dod_frac * 100.0, 1),
        one_way_efficiency_pct=round(eta_dis * 100.0, 1),
        min_gross_capacity_kwh=round(buffered_gross_kwh, 1),
        min_continuous_power_kw=round(buffered_power_kw, 1),
        recommended_unit_count=unit_count,
        recommended_unit_capacity_kwh=unit_cap,
        recommended_total_capacity_kwh=rec_total_kwh,
        recommended_inverter_power_kw=rec_inverter_kw,
        c_rate_discharge=c_rate,
        description=desc
    )


def compute_bess_degradation_profile(
    analysis_horizon_years: int = 15,
    equivalent_full_cycles_per_year: float = 250.0,
    ambient_temperature_c: float = 25.0,
    cell_replacement_year: int = 10,
    base_calendar_fade_pct_yr: float = 1.0,
    cycle_fade_per_100_efc_pct: float = 0.04
) -> List[float]:
    """
    Computes multi-year usable battery capacity retention factors (0.0 to 1.0).
    Accounts for calendar aging, cycle throughput wear, and temperature stress.
    Restores capacity to 95% at cell replacement year.
    """
    factors = []
    
    # Temperature penalty: +0.05% per degree above 25°C
    temp_penalty_pct = max(0.0, ambient_temperature_c - 25.0) * 0.05
    annual_cycle_fade_pct = (equivalent_full_cycles_per_year / 100.0) * cycle_fade_per_100_efc_pct
    annual_total_fade_pct = base_calendar_fade_pct_yr + annual_cycle_fade_pct + temp_penalty_pct
    annual_fade_frac = annual_total_fade_pct / 100.0

    for y in range(1, analysis_horizon_years + 1):
        if y <= cell_replacement_year:
            factor = max(0.60, 1.0 - (y - 1) * annual_fade_frac)
        else:
            # Restored to 95% upon cell replacement
            years_post_refresh = y - cell_replacement_year - 1
            factor = max(0.65, 0.95 - years_post_refresh * annual_fade_frac)
        factors.append(round(factor, 4))

    return factors


def evaluate_sandbox_bess_economics(
    bess_config: BESSConfig,
    sim_result: BESSSimulationResult,
    contract_baseline: Contract,
    contract_bess: Contract,
    avoided_grid_upgrade_capex: float = 0.0,
    avoided_monthly_transformer_rent: float = 0.0,
    analysis_horizon_years: int = 15,
    discount_rate_pct: float = 5.0,
    electricity_price_inflation_pct: float = 2.0,
    ambient_temperature_c: float = 25.0,
    step_hours: float = 0.25
) -> BESSFinancialMetrics:
    """
    Evaluates comprehensive life-cycle economics comparing Status Quo / Grid Upgrade vs. With-BESS.
    Accounts for:
      - 12-month peak demand reductions (kW-max)
      - Contracted capacity GTV differences
      - Avoided one-time grid upgrade CAPEX (e.g. station upgrade)
      - Avoided monthly transformer rent
      - Battery round-trip conversion losses
      - Dynamic multi-year degradation & Year-10 cell overhaul
    """
    # 1. Hardware CAPEX & Initial Investment
    gross_bess_capex = float(bess_config.total_capex)
    cap_kwh = max(1.0, float(bess_config.capacity_kwh))
    
    # Net Initial Investment = BESS Turnkey CAPEX minus avoided grid upgrade CAPEX
    net_initial_investment = max(0.0, gross_bess_capex - avoided_grid_upgrade_capex)

    # 2. Year 1 Baseline vs. With-BESS Bills
    df_ts = sim_result.df_timeseries
    p_load = df_ts["P_Load_kW"].to_numpy(dtype=float)
    p_grid = df_ts["P_Grid_kW"].to_numpy(dtype=float)
    p_dis = df_ts["P_BESS_Discharge_kW"].to_numpy(dtype=float)

    df_base = pd.DataFrame({"Total_Demand_kW": p_load})
    if "timestamp" in df_ts.columns:
        df_base["timestamp"] = df_ts["timestamp"]

    df_bess = pd.DataFrame({"Total_Demand_kW": p_grid})
    if "timestamp" in df_ts.columns:
        df_bess["timestamp"] = df_ts["timestamp"]

    bill_base = compute_financial_bill(df_base, contract_baseline, step_hours=step_hours)
    bill_bess = compute_financial_bill(df_bess, contract_bess, step_hours=step_hours)

    dur = getattr(bill_base, "duration_days", 365.0) or 365.0
    ann_factor = (365.0 / dur) if (0.01 < dur < 360.0) else 1.0

    sq_demand_cost = float(bill_base.capacity_cost_period * ann_factor)
    wb_demand_cost = float(bill_bess.capacity_cost_period * ann_factor)
    demand_savings = max(0.0, sq_demand_cost - wb_demand_cost)

    sq_energy_cost = float(bill_base.energy_cost_period * ann_factor)
    wb_energy_cost = float(bill_bess.energy_cost_period * ann_factor)
    energy_savings = float(sq_energy_cost - wb_energy_cost)

    sq_penalty_cost = float(bill_base.penalty_cost_period * ann_factor)
    wb_penalty_cost = float(bill_bess.penalty_cost_period * ann_factor)
    penalty_savings = max(0.0, sq_penalty_cost - wb_penalty_cost)

    sq_base_bill = float(bill_base.total_gross_period * ann_factor)
    wb_base_bill = float(bill_bess.total_gross_period * ann_factor)

    # Add avoided recurring transformer rental to baseline cost
    annual_transformer_rent = float(avoided_monthly_transformer_rent * 12.0)
    sq_total_annual_cost = sq_base_bill + annual_transformer_rent

    # Efficiency Losses Cost
    annual_discharged_kwh = float(np.sum(p_dis) * step_hours) * ann_factor
    rte = max(0.50, min(1.0, float(bess_config.round_trip_efficiency_pct) / 100.0))
    annual_loss_kwh = annual_discharged_kwh * ((1.0 / rte) - 1.0)
    avg_energy_rate = float(getattr(contract_bess, "default_energy_rate", 0.20) or 0.20)
    annual_loss_cost = float(annual_loss_kwh * avg_energy_rate)

    # BESS O&M
    annual_fixed_om = round(gross_bess_capex * (bess_config.annual_om_pct / 100.0), 2)
    annual_opex_y1 = round(annual_fixed_om + annual_loss_cost, 2)

    # Annual Gross & Net Savings
    annual_bill_savings = max(0.0, sq_base_bill - wb_base_bill)
    annual_gross_savings = annual_bill_savings + annual_transformer_rent
    annual_net_savings_y1 = round(annual_gross_savings - annual_opex_y1, 2)

    # 3. Dynamic Degradation Vector
    efc = float(sim_result.kpis.equivalent_full_cycles)
    deg_factors = compute_bess_degradation_profile(
        analysis_horizon_years=analysis_horizon_years,
        equivalent_full_cycles_per_year=efc,
        ambient_temperature_c=ambient_temperature_c,
        cell_replacement_year=bess_config.cell_replacement_year,
        base_calendar_fade_pct_yr=1.0,
        cycle_fade_per_100_efc_pct=0.04
    )

    # 4. Multi-Year Cash Flow & TCO Projection
    r = discount_rate_pct / 100.0
    infl = electricity_price_inflation_pct / 100.0
    
    cash_flow_table: List[Dict[str, Any]] = []
    cumulative_cash_flow: List[float] = [-net_initial_investment]
    cumulative_status_quo: List[float] = [0.0]
    cumulative_with_bess: List[float] = [net_initial_investment]
    annual_sq_costs: List[float] = []
    annual_wb_costs: List[float] = []

    running_sq = 0.0
    running_wb = net_initial_investment
    cum_cf = -net_initial_investment
    cum_disc_cf = -net_initial_investment
    npv = -net_initial_investment
    raw_cash_flows: List[float] = [-net_initial_investment]

    payback_years: Optional[float] = None
    disc_payback_years: Optional[float] = None
    disc_costs_sum = net_initial_investment
    disc_energy_sum = 0.0

    cell_rep_year = bess_config.cell_replacement_year
    cell_rep_cost = round(gross_bess_capex * 0.65 * (bess_config.cell_replacement_cost_pct / 100.0), 2)

    for y in range(1, analysis_horizon_years + 1):
        deg_factor = deg_factors[y - 1]
        price_factor = (1.0 + infl) ** (y - 1)

        y_sq_cost = sq_total_annual_cost * price_factor
        y_gross_savings = annual_gross_savings * deg_factor * price_factor
        y_wb_bill = (wb_base_bill * price_factor)

        y_opex = (annual_fixed_om * ((1.0 + infl * 0.8) ** (y - 1))) + (annual_loss_cost * price_factor)
        y_extra_capex = cell_rep_cost if (y == cell_rep_year) else 0.0

        y_total_bess_cost = y_wb_bill + y_opex + y_extra_capex
        y_net_cashflow = y_gross_savings - y_opex - y_extra_capex

        raw_cash_flows.append(y_net_cashflow)

        discount_factor = 1.0 / ((1.0 + r) ** y)
        y_disc_cashflow = y_net_cashflow * discount_factor
        npv += y_disc_cashflow

        disc_costs_sum += (y_opex + y_extra_capex) * discount_factor
        disc_energy_sum += (annual_discharged_kwh * deg_factor) * discount_factor

        # Payback tracking
        prev_cum_cf = cum_cf
        cum_cf += y_net_cashflow
        cumulative_cash_flow.append(round(cum_cf, 2))

        if payback_years is None and cum_cf >= 0:
            if y_net_cashflow > 0:
                fraction = abs(prev_cum_cf) / y_net_cashflow
                payback_years = round((y - 1) + fraction, 2)
            else:
                payback_years = float(y)

        prev_cum_disc = cum_disc_cf
        cum_disc_cf += y_disc_cashflow
        if disc_payback_years is None and cum_disc_cf >= 0:
            if y_disc_cashflow > 0:
                fraction = abs(prev_cum_disc) / y_disc_cashflow
                disc_payback_years = round((y - 1) + fraction, 2)
            else:
                disc_payback_years = float(y)

        running_sq += y_sq_cost
        running_wb += y_total_bess_cost
        cumulative_status_quo.append(round(running_sq, 2))
        cumulative_with_bess.append(round(running_wb, 2))
        annual_sq_costs.append(round(y_sq_cost, 2))
        annual_wb_costs.append(round(y_total_bess_cost, 2))

        cash_flow_table.append({
            "year": y,
            "status_quo_bill": round(y_sq_cost, 2),
            "with_bess_bill": round(y_wb_bill, 2),
            "gross_savings": round(y_gross_savings, 2),
            "bess_opex": round(y_opex, 2),
            "cell_replacement": round(y_extra_capex, 2),
            "net_cash_flow": round(y_net_cashflow, 2),
            "cumulative_cash_flow": round(cum_cf, 2),
            "discounted_cash_flow": round(y_disc_cashflow, 2),
            "cumulative_npv": round(npv, 2)
        })

    lcos = round(disc_costs_sum / max(1.0, disc_energy_sum), 3) if disc_energy_sum > 0 else 0.0
    irr_pct = _calculate_irr(raw_cash_flows)
    total_lifetime_net_cf = sum(row["net_cash_flow"] for row in cash_flow_table)
    roi_pct = round((total_lifetime_net_cf / max(1.0, net_initial_investment)) * 100.0, 1) if net_initial_investment > 0 else 999.0

    return BESSFinancialMetrics(
        is_configured=True,
        total_capex=round(net_initial_investment, 2),
        capex_per_kwh=round(net_initial_investment / cap_kwh, 2),
        annual_opex_year1=annual_opex_y1,
        annual_fixed_om=annual_fixed_om,
        annual_loss_kwh=round(annual_loss_kwh, 1),
        annual_loss_cost=round(annual_loss_cost, 2),
        annual_status_quo_demand_cost=round(sq_demand_cost, 2),
        annual_with_bess_demand_cost=round(wb_demand_cost, 2),
        annual_status_quo_energy_cost=round(sq_energy_cost, 2),
        annual_with_bess_energy_cost=round(wb_energy_cost, 2),
        annual_status_quo_penalty_cost=round(sq_penalty_cost, 2),
        annual_with_bess_penalty_cost=round(wb_penalty_cost, 2),
        annual_status_quo_total_bill=round(sq_total_annual_cost, 2),
        annual_with_bess_total_bill=round(wb_base_bill, 2),
        annual_demand_charge_savings=round(demand_savings, 2),
        annual_penalty_savings=round(penalty_savings, 2),
        annual_energy_savings=round(energy_savings, 2),
        annual_gross_savings=round(annual_gross_savings, 2),
        annual_net_savings_year1=round(annual_net_savings_y1, 2),
        simple_payback_years=payback_years,
        discounted_payback_years=disc_payback_years,
        net_present_value=round(npv, 2),
        internal_rate_of_return_pct=irr_pct,
        levelized_cost_of_storage_eur_kwh=lcos,
        return_on_investment_pct=roi_pct,
        cash_flow_table=cash_flow_table,
        cumulative_cash_flow=cumulative_cash_flow,
        cumulative_status_quo=cumulative_status_quo,
        cumulative_with_bess=cumulative_with_bess,
        annual_status_quo_costs=annual_sq_costs,
        annual_with_bess_costs=annual_wb_costs
    )
