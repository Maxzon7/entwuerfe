"""
========================================================================================
BESS Financial & Life-Cycle Economic Engine (core/bess_financial_engine.py)
========================================================================================

Description:
------------
Pure economic and commercial assessment engine for Battery Energy Storage Systems (BESS):
  1. Turn-Key CAPEX & OPEX Breakdown:
     - Battery Module & Pack (€/kWh)
     - Power Conversion System / Inverter (PCS)
     - Balance of Plant (BOP / Enclosures / Fire suppression / HVAC)
     - Fixed Installation & Grid Interconnection
     - Annual O&M (% of CAPEX)
  2. Annual Electricity Bill & Tariff Savings:
     - Peak Demand / Capacity Charge Reductions (€/kW shaved * capacity tariff)
     - Avoided Grid Overload Penalties
     - Active Energy / TOU Arbitrage Savings
     - Total Gross & Net Annual Savings
  3. Multi-Year Life-Cycle Cash Flow & Investment Analysis:
     - 15-Year / 20-Year Cash Flow Projection with capacity degradation (-2%/yr)
     - Electricity Tariff Inflation Escalation (e.g., +2%/yr)
     - Scheduled mid-life battery cell replacement (e.g. at Year 10)
     - Net Present Value (NPV), Simple & Discounted Payback Period (Amortisation)
     - Internal Rate of Return (IRR) & Levelized Cost of Storage (LCOS in €/kWh)
     - Sensitivity Analysis (CAPEX, Demand Tariff, Price Escalation)
"""

from typing import Optional, Dict, Any, List, Tuple
import numpy as np
import pandas as pd

from current_model.models.bess import BESSConfig, BESSKPIs, BESSFinancialMetrics
from current_model.models.contract import Contract
from current_model.core.financial_engine import compute_financial_bill


def compute_bess_capex_breakdown(
    config: BESSConfig,
    inverter_cost_per_kw: float = 120.0,
    bos_cost_per_kwh: float = 40.0
) -> Dict[str, float]:
    """
    Computes an itemized turn-key CAPEX breakdown for the BESS installation.
    """
    if not config.is_financial_enabled:
        return {
            "capex_cells_modules": 0.0,
            "capex_inverter_pcs": 0.0,
            "capex_bos_enclosure": 0.0,
            "capex_installation_grid": 0.0,
            "total_capex": 0.0,
            "capex_per_kwh": 0.0
        }

    cap_kwh = max(1.0, float(config.capacity_kwh))
    p_dis_kw = max(0.1, float(config.max_discharge_power_kw))
    unit_cost_kwh = float(config.cost_per_kwh)
    fixed_install = float(config.fixed_installation_cost)

    # Estimate component shares from overall unit cost
    # Battery cell pack ~ 65%, Inverter/PCS ~ 15%, BOS/HVAC ~ 10%, Balance ~ 10%
    capex_cells = round(cap_kwh * unit_cost_kwh * 0.65, 2)
    capex_pcs = round(p_dis_kw * inverter_cost_per_kw, 2)
    capex_bos = round(cap_kwh * bos_cost_per_kwh, 2)
    capex_install = round(fixed_install + (cap_kwh * unit_cost_kwh * 0.15), 2)

    total_capex = round(config.total_capex, 2)
    capex_per_kwh = round(total_capex / cap_kwh, 2)

    return {
        "capex_cells_modules": capex_cells,
        "capex_inverter_pcs": capex_pcs,
        "capex_bos_enclosure": capex_bos,
        "capex_installation_grid": capex_install,
        "total_capex": total_capex,
        "capex_per_kwh": capex_per_kwh
    }


def _calculate_irr(cash_flows: List[float], max_iter: int = 1000) -> Optional[float]:
    """Computes the Internal Rate of Return (IRR %) using a robust secant/bisection solver."""
    if len(cash_flows) < 2 or cash_flows[0] >= 0:
        return None
    # Check if there are positive cash flows
    if all(cf <= 0 for cf in cash_flows[1:]):
        return None

    def npv_func(rate: float) -> float:
        val = 0.0
        for t, cf in enumerate(cash_flows):
            val += cf / ((1.0 + rate) ** t)
        return val

    # Try secant method with initial bounds [-0.5, 1.0]
    r0, r1 = 0.05, 0.15
    f0, f1 = npv_func(r0), npv_func(r1)

    for _ in range(max_iter):
        if abs(f1 - f0) < 1e-9:
            break
        r2 = r1 - f1 * (r1 - r0) / (f1 - f0)
        if r2 < -0.99 or r2 > 5.0 or np.isnan(r2):
            break
        f2 = npv_func(r2)
        if abs(f2) < 1e-4:
            return round(r2 * 100.0, 2)
        r0, r1 = r1, r2
        f0, f1 = f1, f2

    # Fallback search over a grid from -50% to +100%
    grid = np.linspace(-0.50, 1.00, 300)
    vals = [npv_func(r) for r in grid]
    for i in range(len(grid) - 1):
        if vals[i] * vals[i+1] <= 0:
            # Root bracket found
            low, high = grid[i], grid[i+1]
            for _ in range(50):
                mid = (low + high) / 2.0
                if npv_func(mid) * npv_func(low) <= 0:
                    high = mid
                else:
                    low = mid
            return round(mid * 100.0, 2)

    return None


def compute_bess_financial_metrics(
    bess_config: BESSConfig,
    df_timeseries: pd.DataFrame,
    contract: Optional[Contract] = None,
    grid_limit_kw: float = 100.0,
    analysis_horizon_years: int = 15,
    discount_rate_pct: float = 5.0,
    electricity_price_inflation_pct: float = 2.0,
    step_hours: float = 0.25
) -> BESSFinancialMetrics:
    """
    Evaluates complete life-cycle commercial metrics for the BESS project.
    Compares Status Quo facility consumption vs With-BESS residual grid profile against utility tariffs.
    """
    total_capex = bess_config.total_capex
    if total_capex <= 0 or not bess_config.is_financial_enabled:
        return BESSFinancialMetrics(
            is_configured=False,
            total_capex=0.0,
            capex_per_kwh=0.0
        )

    # 1. Create a default contract if none is attached
    if contract is None:
        contract = Contract(
            name="Commercial Grid Tariff",
            currency="EUR",
            contracted_capacity_kw=grid_limit_kw,
            monthly_capacity_tariff=14.0,  # €14/kW/month
            peak_penalty_rate=25.0,        # €25/kW overload penalty
            default_energy_rate=0.20,      # €0.20/kWh
            base_monthly_fee=50.0,
            taxes_and_fees=[{"name": "VAT", "type": "percentage", "value": 19.0}]
        )

    currency = contract.currency or "EUR"
    cap_kwh = max(1.0, float(bess_config.capacity_kwh))

    # 2. Extract load curves
    p_load = np.nan_to_num(df_timeseries["P_Load_kW"].to_numpy(dtype=float), nan=0.0) if "P_Load_kW" in df_timeseries.columns else np.zeros(len(df_timeseries))
    p_grid = np.nan_to_num(df_timeseries["P_Grid_kW"].to_numpy(dtype=float), nan=0.0) if "P_Grid_kW" in df_timeseries.columns else np.zeros(len(df_timeseries))
    p_dis = np.nan_to_num(df_timeseries["P_BESS_Discharge_kW"].to_numpy(dtype=float), nan=0.0) if "P_BESS_Discharge_kW" in df_timeseries.columns else np.zeros(len(df_timeseries))

    # 3. Compute baseline utility bill (Status Quo) vs With-BESS bill
    df_base = pd.DataFrame({"Total_Demand_kW": p_load})
    if "timestamp" in df_timeseries.columns:
        df_base["timestamp"] = df_timeseries["timestamp"]

    df_bess = pd.DataFrame({"Total_Demand_kW": p_grid})
    if "timestamp" in df_timeseries.columns:
        df_bess["timestamp"] = df_timeseries["timestamp"]

    bill_base = compute_financial_bill(df_base, contract, step_hours=step_hours)
    bill_bess = compute_financial_bill(df_bess, contract, step_hours=step_hours)

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

    sq_total_bill = float(bill_base.total_gross_period * ann_factor)
    wb_total_bill = float(bill_bess.total_gross_period * ann_factor)
    annual_gross_savings = max(0.0, sq_total_bill - wb_total_bill)

    # Conversion efficiency losses
    annual_discharged_kwh = float(np.sum(p_dis) * step_hours) * ann_factor
    rte = max(0.50, min(1.0, float(bess_config.round_trip_efficiency_pct) / 100.0))
    annual_loss_kwh = annual_discharged_kwh * ((1.0 / rte) - 1.0)
    avg_energy_rate = float(getattr(contract, "default_energy_rate", 0.20) or 0.20)
    annual_loss_cost = float(annual_loss_kwh * avg_energy_rate)

    annual_fixed_om = round(total_capex * (bess_config.annual_om_pct / 100.0), 2)
    annual_opex_y1 = round(annual_fixed_om + annual_loss_cost, 2)
    annual_net_savings_y1 = round(annual_gross_savings - annual_fixed_om, 2)

    # 4. Multi-Year Cash Flow Projection (1 to Horizon Years)
    horizon_years = max(1, analysis_horizon_years)
    r = discount_rate_pct / 100.0
    infl = electricity_price_inflation_pct / 100.0
    deg = (bess_config.annual_degradation_pct if hasattr(bess_config, "annual_degradation_pct") else 2.0) / 100.0

    cash_flow_table: List[Dict[str, Any]] = []
    cumulative_cash_flow: List[float] = [-total_capex]
    cumulative_status_quo: List[float] = [0.0]
    cumulative_with_bess: List[float] = [total_capex]
    annual_sq_costs: List[float] = []
    annual_wb_costs: List[float] = []

    running_sq = 0.0
    running_wb = total_capex
    cum_cf = -total_capex
    cum_disc_cf = -total_capex

    payback_years: Optional[float] = None
    disc_payback_years: Optional[float] = None
    npv = -total_capex
    raw_cash_flows: List[float] = [-total_capex]

    disc_costs_sum = total_capex
    disc_energy_sum = 0.0

    cell_rep_year = bess_config.cell_replacement_year
    cell_rep_cost = round(total_capex * 0.65 * (bess_config.cell_replacement_cost_pct / 100.0), 2)

    for y in range(1, horizon_years + 1):
        # Physical battery capacity factor (degrades slightly each year)
        deg_factor = max(0.60, 1.0 - (y - 1) * deg)
        # After cell replacement, capacity restored to 95%
        if y > cell_rep_year:
            deg_factor = max(0.70, 0.95 - (y - cell_rep_year - 1) * deg)

        # Electricity price inflation escalation
        price_factor = (1.0 + infl) ** (y - 1)

        # Scaled annual bill and savings
        y_sq_cost = sq_total_bill * price_factor
        y_gross_savings = annual_gross_savings * deg_factor * price_factor
        y_wb_bill = y_sq_cost - y_gross_savings

        y_opex = annual_fixed_om * ((1.0 + infl * 0.8) ** (y - 1)) + (annual_loss_cost * price_factor)
        y_extra_capex = cell_rep_cost if (y == cell_rep_year) else 0.0

        y_total_bess_cost = y_wb_bill + y_opex + y_extra_capex
        y_net_cashflow = y_gross_savings - y_opex - y_extra_capex

        raw_cash_flows.append(y_net_cashflow)

        # Discounting
        discount_factor = 1.0 / ((1.0 + r) ** y)
        y_disc_cashflow = y_net_cashflow * discount_factor
        npv += y_disc_cashflow

        # LCOS accumulators
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

    # LCOS (€/kWh)
    lcos = round(disc_costs_sum / max(1.0, disc_energy_sum), 3) if disc_energy_sum > 0 else 0.0

    # IRR (%)
    irr_pct = _calculate_irr(raw_cash_flows)

    # ROI (%)
    total_lifetime_net_cf = sum(row["net_cash_flow"] for row in cash_flow_table)
    roi_pct = round((total_lifetime_net_cf / max(1.0, total_capex)) * 100.0, 1)

    return BESSFinancialMetrics(
        is_configured=True,
        total_capex=round(total_capex, 2),
        capex_per_kwh=round(total_capex / cap_kwh, 2),
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
        annual_status_quo_total_bill=round(sq_total_bill, 2),
        annual_with_bess_total_bill=round(wb_total_bill, 2),
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


def compute_bess_sensitivity_matrix(
    bess_config: BESSConfig,
    df_timeseries: pd.DataFrame,
    contract: Optional[Contract] = None,
    grid_limit_kw: float = 100.0,
    variations: Optional[List[float]] = None
) -> List[Dict[str, Any]]:
    """
    Computes sensitivity of Simple Payback Period and 15-Year NPV against ±10% and ±20% variation in:
      - Battery CAPEX (€/kWh)
      - Peak Demand / Capacity Tariff (€/kW/month)
      - Electricity Price Inflation Rate
    """
    if variations is None:
        variations = [-0.20, -0.10, 0.0, 0.10, 0.20]

    results: List[Dict[str, Any]] = []

    base_cost_kwh = bess_config.cost_per_kwh
    base_cap_tariff = contract.monthly_capacity_tariff if contract else 14.0

    # 1. Vary Battery CAPEX
    for delta in variations:
        cfg_copy = BESSConfig.from_dict(bess_config.to_dict())
        cfg_copy.cost_per_kwh = base_cost_kwh * (1.0 + delta)
        cfg_copy.fixed_installation_cost = bess_config.fixed_installation_cost * (1.0 + delta)
        res = compute_bess_financial_metrics(cfg_copy, df_timeseries, contract, grid_limit_kw=grid_limit_kw)
        results.append({
            "parameter": "Battery CAPEX",
            "variation_pct": f"{int(delta * 100):+d}%",
            "variation_val": delta,
            "payback_years": res.simple_payback_years if res.simple_payback_years else 20.0,
            "npv": res.net_present_value,
            "irr": res.internal_rate_of_return_pct
        })

    # 2. Vary Peak Demand Tariff
    for delta in variations:
        if contract:
            c_copy = Contract.from_dict(contract.to_dict())
            c_copy.monthly_capacity_tariff = base_cap_tariff * (1.0 + delta)
            c_copy.peak_penalty_rate = contract.peak_penalty_rate * (1.0 + delta)
        else:
            c_copy = None
        res = compute_bess_financial_metrics(bess_config, df_timeseries, c_copy, grid_limit_kw=grid_limit_kw)
        results.append({
            "parameter": "Peak Demand Tariff (€/kW)",
            "variation_pct": f"{int(delta * 100):+d}%",
            "variation_val": delta,
            "payback_years": res.simple_payback_years if res.simple_payback_years else 20.0,
            "npv": res.net_present_value,
            "irr": res.internal_rate_of_return_pct
        })

    return results
