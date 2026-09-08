"""
========================================================================================
Solar Financial & CAPEX/OPEX Economic Engine (current_model/core/solar_financial_engine.py)
========================================================================================

Description:
------------
Pure economic calculation engine for Solar PV systems matching the DRACBV reference workbooks:
  1. Itemized CAPEX Breakdown:
     - Modules (€/Wp * DC Wp)
     - Inverters (€/W * AC W)
     - Mechanical Substructure / Mounting (€/Wp * DC Wp)
     - Electrical Installation & Grid Connection (€/Wp * DC Wp)
     - Fixed Switchgear / Metering Cabinet (Zählerschrank)
     - Fixed Mobilization / Travel Fee (Einmalige Anfahrtsgebühr)
  2. Operational Lifecycle Economics:
     - Annual O&M, monitoring, and insurance OPEX
     - 15-Year Life-Cycle Cashflow with physical degradation (Y1 vs Y2+)
     - Levelized Cost of Electricity (LCOE in €/kWh):
         LCOE = (CAPEX + Sum(OPEX_t / (1+r)^t)) / Sum(Yield_t / (1+r)^t)
     - Avoided electricity purchases & export revenue (when contract or flat tariff provided)
     - Net Present Value (NPV), Payback Period, and Discounted Payback
"""

from typing import Optional, Dict, Any, List, Tuple
import numpy as np
import pandas as pd

from current_model.models.solar import (
    SolarPVConfig,
    SolarFinancialConfig,
    SolarFinancialMetrics,
    SolarSimulationResult
)


def compute_solar_capex(
    config: SolarPVConfig,
    fin_config: SolarFinancialConfig
) -> Dict[str, float]:
    """
    Computes the detailed turn-key CAPEX breakdown according to the DRACBV Kosten-/Berechnungs-Dashboard.
    Returns itemized and total CAPEX amounts.
    """
    if not fin_config or not fin_config.is_enabled:
        return {
            "capex_modules": 0.0,
            "capex_inverter": 0.0,
            "capex_substructure": 0.0,
            "capex_installation": 0.0,
            "capex_fixed_fees": 0.0,
            "total_capex": 0.0,
            "capex_per_kwp": 0.0
        }

    total_dc_wp = (config.module_count * config.module_power_wp)
    total_dc_kwp = total_dc_wp / 1000.0
    total_inv_w = (config.inverter_capacity_kw or 0.0) * 1000.0

    # Itemized costs (defaults to 0.0 if not specified by user)
    cost_mod_wp = fin_config.cost_modules_per_wp or 0.0
    cost_inv_w = fin_config.cost_inverter_per_w or 0.0
    cost_sub_wp = fin_config.cost_substructure_per_wp or 0.0
    cost_inst_wp = fin_config.cost_installation_per_wp or 0.0

    capex_modules = total_dc_wp * cost_mod_wp
    capex_inverter = total_inv_w * cost_inv_w
    capex_substructure = total_dc_wp * cost_sub_wp
    capex_installation = total_dc_wp * cost_inst_wp
    capex_fixed = (
        (fin_config.fixed_switchgear_cost or 0.0) +
        (fin_config.fixed_travel_fee or 0.0) +
        (fin_config.custom_additional_capex or 0.0)
    )

    total_capex = capex_modules + capex_inverter + capex_substructure + capex_installation + capex_fixed
    capex_per_kwp = (total_capex / total_dc_kwp) if total_dc_kwp > 0 else 0.0

    return {
        "capex_modules": round(capex_modules, 2),
        "capex_inverter": round(capex_inverter, 2),
        "capex_substructure": round(capex_substructure, 2),
        "capex_installation": round(capex_installation, 2),
        "capex_fixed_fees": round(capex_fixed, 2),
        "total_capex": round(total_capex, 2),
        "capex_per_kwp": round(capex_per_kwp, 2)
    }


def compute_solar_financial_metrics(
    config: SolarPVConfig,
    fin_config: Optional[SolarFinancialConfig],
    annual_generation_kwh: float,
    multi_year_yields: Optional[List[Dict[str, Any]]] = None,
    annual_avoided_cost: Optional[float] = None,
    annual_export_revenue: Optional[float] = None,
    baseline_electricity_rate: Optional[float] = None
) -> SolarFinancialMetrics:
    """
    Computes complete 15-year lifecycle financial metrics, LCOE, NPV, and Payback.
    Handles empty/unconfigured financial parameters gracefully.
    """
    if not fin_config or not fin_config.is_enabled:
        return SolarFinancialMetrics(is_configured=False)

    capex_dict = compute_solar_capex(config, fin_config)
    total_capex = capex_dict["total_capex"]
    if total_capex <= 0.0:
        return SolarFinancialMetrics(is_configured=False)

    horizon_years = max(1, fin_config.analysis_horizon_years or 15)
    r = (fin_config.discount_rate_pct or 0.0) / 100.0
    infl = (fin_config.electricity_price_inflation_pct or 0.0) / 100.0

    # OPEX: percentage of CAPEX or fixed
    opex_year1 = total_capex * (fin_config.annual_opex_pct / 100.0) + (fin_config.annual_opex_fixed or 0.0)

    # 15-Year yields with degradation
    d1 = (config.first_year_degradation_pct or 1.50) / 100.0
    d2 = (config.annual_degradation_pct or 0.40) / 100.0

    # Prepare cashflow projection
    cash_flow_table: List[Dict[str, Any]] = []
    cumulative_cash_flow: List[float] = []

    # Initial Year 0 outflow
    cum_cf = -total_capex
    cumulative_cash_flow.append(cum_cf)

    # Discounted LCOE summations
    discounted_costs_sum = total_capex
    discounted_energy_sum = 0.0
    total_energy_lifetime = 0.0

    # Payback tracker
    payback_years: Optional[float] = None
    discounted_payback_years: Optional[float] = None
    prev_cum_cf = -total_capex
    cum_discounted_cf = -total_capex

    # Default unit benefits if no direct avoided cost was supplied
    # If baseline rate supplied, use it; else fallback to flat feed-in rate or 0.15 €/kWh
    ref_rate = baseline_electricity_rate if (baseline_electricity_rate and baseline_electricity_rate > 0) else 0.18
    feed_in = fin_config.feed_in_tariff_per_kwh or 0.06

    has_detailed_benefits = (annual_avoided_cost is not None and annual_avoided_cost > 0)

    for y in range(1, horizon_years + 1):
        # 1. Degradation factor
        if y == 1:
            f_deg = (1.0 - d1)
        else:
            f_deg = (1.0 - d1) * ((1.0 - d2) ** (y - 1))

        # 2. PV Production in Year y
        y_gen_kwh = annual_generation_kwh * f_deg
        total_energy_lifetime += y_gen_kwh

        # 3. OPEX with small inflation (e.g. 2% p.a. for service)
        y_opex = opex_year1 * ((1.0 + 0.02) ** (y - 1))

        # 4. Energy Savings / Revenue
        # Tariff escalates with electricity inflation
        tariff_factor = (1.0 + infl) ** (y - 1)
        if has_detailed_benefits:
            # Scale avoided costs by degradation and tariff inflation
            y_savings = (annual_avoided_cost * f_deg * tariff_factor) + (annual_export_revenue * f_deg * tariff_factor if annual_export_revenue else 0.0)
        else:
            # Standalone estimation: 70% self-consumed @ ref_rate, 30% exported @ feed-in
            y_self_kwh = y_gen_kwh * 0.70
            y_surplus_kwh = y_gen_kwh * 0.30
            y_savings = (y_self_kwh * (ref_rate * tariff_factor)) + (y_surplus_kwh * feed_in)

        # Net cashflow for year y
        net_cf = y_savings - y_opex
        discount_factor = 1.0 / ((1.0 + r) ** y)
        discounted_net_cf = net_cf * discount_factor

        # Cumulative cashflows
        prev_cum_cf = cum_cf
        cum_cf += net_cf
        cumulative_cash_flow.append(round(cum_cf, 2))

        prev_disc_cum = cum_discounted_cf
        cum_discounted_cf += discounted_net_cf

        # Check simple payback
        if payback_years is None and cum_cf >= 0.0:
            # Linear interpolation for fractional year
            fraction = (-prev_cum_cf) / net_cf if net_cf > 0 else 0.0
            payback_years = round((y - 1) + fraction, 1)

        # Check discounted payback
        if discounted_payback_years is None and cum_discounted_cf >= 0.0:
            fraction_d = (-prev_disc_cum) / discounted_net_cf if discounted_net_cf > 0 else 0.0
            discounted_payback_years = round((y - 1) + fraction_d, 1)

        # LCOE accumulation
        discounted_costs_sum += (y_opex * discount_factor)
        discounted_energy_sum += (y_gen_kwh * discount_factor)

        cash_flow_table.append({
            "year": y,
            "aging_factor": round(f_deg, 4),
            "generation_kwh": round(y_gen_kwh, 0),
            "generation_mwh": round(y_gen_kwh / 1000.0, 2),
            "opex_annual": round(y_opex, 2),
            "gross_savings": round(y_savings, 2),
            "net_cash_flow": round(net_cf, 2),
            "cumulative_cash_flow": round(cum_cf, 2),
            "discounted_cash_flow": round(discounted_net_cf, 2)
        })

    # LCOE = (Total discounted costs) / (Total discounted electricity)
    lcoe = (discounted_costs_sum / discounted_energy_sum) if discounted_energy_sum > 0 else 0.0

    # NPV = Cumulative discounted cashflow at end of horizon
    npv = cum_discounted_cf

    # IRR Calculation (Internal Rate of Return)
    irr_val: Optional[float] = None
    try:
        cf_stream = [-total_capex] + [row["net_cash_flow"] for row in cash_flow_table]
        # np.irr is deprecated in newer numpy, use npf.irr fallback or manual bisection
        irr_calc = _compute_irr(cf_stream)
        if irr_calc is not None and -0.5 < irr_calc < 2.0:
            irr_val = round(irr_calc * 100.0, 2)
    except Exception:
        irr_val = None

    total_lifetime_savings = cum_cf

    return SolarFinancialMetrics(
        is_configured=True,
        currency=fin_config.currency or "EUR",
        capex_modules=capex_dict["capex_modules"],
        capex_inverter=capex_dict["capex_inverter"],
        capex_substructure=capex_dict["capex_substructure"],
        capex_installation=capex_dict["capex_installation"],
        capex_fixed_fees=capex_dict["capex_fixed_fees"],
        total_capex=total_capex,
        capex_per_kwp=capex_dict["capex_per_kwp"],
        annual_opex_year1=round(opex_year1, 2),
        lifetime_total_generation_kwh=round(total_energy_lifetime, 0),
        lcoe_per_kwh=round(lcoe, 4),
        cash_flow_table=cash_flow_table,
        cumulative_cash_flow=cumulative_cash_flow,
        payback_period_years=payback_years,
        discounted_payback_years=discounted_payback_years,
        npv=round(npv, 2),
        irr_pct=irr_val,
        total_lifetime_savings=round(total_lifetime_savings, 2)
    )


def _compute_irr(cash_flows: List[float], max_iter: int = 100) -> Optional[float]:
    """
    Computes Internal Rate of Return (IRR) via bisection and Newton-Raphson.
    Returns float (e.g. 0.12 for 12%) or None if undefined.
    """
    if not cash_flows or cash_flows[0] >= 0:
        return None

    # Check if there are any positive cash flows
    if all(cf <= 0 for cf in cash_flows[1:]):
        return None

    # Newton-Raphson with bounds
    rate = 0.10
    for _ in range(max_iter):
        npv = 0.0
        d_npv = 0.0
        for t, cf in enumerate(cash_flows):
            denom = (1.0 + rate) ** t
            npv += cf / denom
            if t > 0:
                d_npv -= (t * cf) / ((1.0 + rate) ** (t + 1))

        if abs(d_npv) < 1e-9:
            break
        new_rate = rate - (npv / d_npv)
        if abs(new_rate - rate) < 1e-6:
            return new_rate
        rate = max(-0.9, min(2.0, new_rate))

    return rate if abs(npv) < 100.0 else None
