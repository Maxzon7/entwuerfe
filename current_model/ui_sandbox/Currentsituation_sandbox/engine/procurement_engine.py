"""
========================================================================================
Layer 8: Procurement Strategy & Asset Advisory Suite (engine/procurement_engine.py)
Current Situation (Status Quo) Sandbox Engine
========================================================================================
Provides strategic executive evaluation tools for Dutch Grootverbruik decisions:
  1. 3-Route Comparator: Simultaneously evaluates Fixed, Tranche/Click, and Dynamic Spot
  2. Voltage Level Transition Advisor: Computes net ROI of switching from AC4b to AC5a
     with a rented transformer station
  3. BESS & Flex Readiness Advisor: Quantifies peak shaving on Maandpiek (€3.46/kW/mo),
     GTV reservation downsizing, and CBC congestion flexibility potential
========================================================================================
"""

from typing import Dict, Any, List, Tuple, Optional
from copy import deepcopy
import numpy as np

try:
    from .config_and_models import (
        LoadSeries2025,
        StatusQuoConfig2025,
        PricingMode,
        StatusQuoAnnualResult,
    )
    from .status_quo_master import calculate_status_quo_master
    from .tariff_defaults_2025 import (
        get_dso_tariff_from_catalog,
        get_supplier_tariff_from_catalog,
        get_trafo_tariff_from_catalog,
    )
except (ImportError, ValueError):
    from config_and_models import (
        LoadSeries2025,
        StatusQuoConfig2025,
        PricingMode,
        StatusQuoAnnualResult,
    )
    from status_quo_master import calculate_status_quo_master
    from tariff_defaults_2025 import (
        get_dso_tariff_from_catalog,
        get_supplier_tariff_from_catalog,
        get_trafo_tariff_from_catalog,
    )


def compare_procurement_routes(
    load: LoadSeries2025,
    base_config: StatusQuoConfig2025
) -> Dict[str, Any]:
    """
    Evaluates the active facility load simultaneously across all 3 procurement routes:
      1. Fixed Price (Vaste Prijs)
      2. Tranche / Click Contract (Klik-contract)
      3. Dynamic Spot (EPEX Spot NL)
    """
    routes: Dict[str, Dict[str, Any]] = {}

    # Common shared supplier markup, balancing, and GvO
    markup = base_config.supplier.supplier_margin_kwh
    balancing = base_config.supplier.balancing_fee_kwh
    gvo = base_config.supplier.green_certificate_surcharge_kwh
    base_fee = base_config.supplier.base_fee_annual

    # Route 1: Fixed
    cfg_fixed = deepcopy(base_config)
    cfg_fixed.supplier.pricing_mode = PricingMode.FIXED
    cfg_fixed.supplier.is_dual_rate = False
    cfg_fixed.supplier.fixed_rate_kwh = 0.1150
    res_fixed = calculate_status_quo_master(load, cfg_fixed)

    # Route 2: Tranche
    cfg_tranche = deepcopy(base_config)
    cfg_tranche.supplier.pricing_mode = PricingMode.TRANCHE
    res_tranche = calculate_status_quo_master(load, cfg_tranche)

    # Route 3: Dynamic Spot
    cfg_spot = deepcopy(base_config)
    cfg_spot.supplier.pricing_mode = PricingMode.DYNAMIC
    res_spot = calculate_status_quo_master(load, cfg_spot)

    spot_annual_net = res_spot.total_supplier_net
    fixed_risk_premium = res_fixed.total_supplier_net - spot_annual_net
    tranche_risk_premium = res_tranche.total_supplier_net - spot_annual_net

    routes = {
        "fixed": {
            "title": "Fixed-Price Contract (Vaste Prijs)",
            "pricing_mode": "fixed",
            "annual_supplier_net": res_fixed.total_supplier_net,
            "annual_total_net": res_fixed.total_status_quo_net,
            "blended_net_rate": res_fixed.blended_price_net_kwh,
            "risk_premium_eur": round(fixed_risk_premium, 2),
            "monthly_totals_net": [m.total_net for m in res_fixed.monthly_records],
            "monthly_supplier_net": [m.supplier.subtotal_supplier_net for m in res_fixed.monthly_records],
        },
        "tranche": {
            "title": "Tranche & Click Contract (Klik-Contract)",
            "pricing_mode": "tranche",
            "annual_supplier_net": res_tranche.total_supplier_net,
            "annual_total_net": res_tranche.total_status_quo_net,
            "blended_net_rate": res_tranche.blended_price_net_kwh,
            "risk_premium_eur": round(tranche_risk_premium, 2),
            "monthly_totals_net": [m.total_net for m in res_tranche.monthly_records],
            "monthly_supplier_net": [m.supplier.subtotal_supplier_net for m in res_tranche.monthly_records],
        },
        "dynamic": {
            "title": "Dynamic Spot Contract (EPEX Spot NL)",
            "pricing_mode": "dynamic",
            "annual_supplier_net": res_spot.total_supplier_net,
            "annual_total_net": res_spot.total_status_quo_net,
            "blended_net_rate": res_spot.blended_price_net_kwh,
            "risk_premium_eur": 0.0,
            "monthly_totals_net": [m.total_net for m in res_spot.monthly_records],
            "monthly_supplier_net": [m.supplier.subtotal_supplier_net for m in res_spot.monthly_records],
        },
    }

    return routes


def evaluate_voltage_transition_advisor(
    load: LoadSeries2025,
    contracted_kw: Optional[float] = None
) -> Dict[str, Any]:
    """
    Evaluates whether the facility should transition from Low Voltage (AC4b)
    to Medium Voltage with a rented transformer station (AC5a).
    Calculates exact annual GTV savings vs. station rental costs.
    """
    peak_demand = float(load.peak_demand_kw)
    p_contract = contracted_kw or max(50.0, round(peak_demand * 1.05, 0))

    # GTV rates under Liander
    gtv_ac4b_annual = 43.881    # €/kW/year for AC4b
    gtv_ac5a_annual = 26.680    # €/kW/year for AC5a

    annual_gtv_ac4b = p_contract * gtv_ac4b_annual
    annual_gtv_ac5a = p_contract * gtv_ac5a_annual
    annual_gtv_savings = annual_gtv_ac4b - annual_gtv_ac5a

    # PAV rates under Liander
    pav_ac4b_annual = 283.68    # 12 x €23.64
    pav_ac5a_annual = 1013.88   # 12 x €84.49
    pav_delta = pav_ac5a_annual - pav_ac4b_annual  # +€730.20/yr

    # Rental cost for a 630 kVA transformer station
    annual_trafo_rent = 354.00 * 12.0  # €4,248.00 / year

    # Net annual economic benefit
    net_annual_benefit = annual_gtv_savings - pav_delta - annual_trafo_rent
    break_even_kw = (pav_delta + annual_trafo_rent) / (gtv_ac4b_annual - gtv_ac5a_annual)

    is_beneficial = (net_annual_benefit > 0.0)

    return {
        "contracted_kw": p_contract,
        "peak_demand_kw": peak_demand,
        "annual_gtv_savings": round(annual_gtv_savings, 2),
        "pav_delta": round(pav_delta, 2),
        "annual_trafo_rent": round(annual_trafo_rent, 2),
        "net_annual_benefit": round(net_annual_benefit, 2),
        "break_even_kw": round(break_even_kw, 1),
        "is_beneficial": is_beneficial,
        "recommendation": (
            f"Transition to Medium Voltage (AC5a) with a rented 630 kVA transformer station is highly recommended: "
            f"Annual net savings = € {net_annual_benefit:,.2f} / year."
            if is_beneficial else
            f"Remain on Low Voltage (AC4b). Facility peak ({peak_demand:.1f} kW) is below the break-even threshold "
            f"({break_even_kw:.1f} kW)."
        ),
    }


def evaluate_bess_flexibility_upside(
    load: LoadSeries2025,
    active_config: StatusQuoConfig2025,
    shave_kw: float = 100.0
) -> Dict[str, Any]:
    """
    Quantifies the economic levers of on-site Battery Energy Storage (BESS):
      1. Peak Shaving savings on Maandpiek (€3.46/kW/month * 12)
      2. Downsizing of contracted GTV (e.g. €26.680/kW/year under AC5a)
      3. CBC Congestion Flexibility Availability credit estimation
    """
    peak_rate = float(active_config.dso.rate_peak_demand)  # €3.46
    gtv_rate_annual = float(active_config.dso.rate_contracted_capacity) * 12.0  # e.g. €26.68

    # 1. Direct peak fee shaving (assuming 100 kW clipped across all 12 months)
    annual_peak_fee_savings = shave_kw * peak_rate * 12.0

    # 2. Potential GTV contract reduction
    annual_gtv_savings = shave_kw * gtv_rate_annual

    # 3. CBC Congestion flexibility remuneration (indicative €15/kW/month availability)
    cbc_availability_rate = 15.00  # €/kW/month
    annual_cbc_income = shave_kw * cbc_availability_rate * 12.0

    total_flex_value = annual_peak_fee_savings + annual_gtv_savings + annual_cbc_income

    return {
        "shave_kw": shave_kw,
        "annual_peak_fee_savings": round(annual_peak_fee_savings, 2),
        "annual_gtv_savings": round(annual_gtv_savings, 2),
        "annual_cbc_income": round(annual_cbc_income, 2),
        "total_flex_value": round(total_flex_value, 2),
        "bess_contract_requirement": (
            "A Dynamic Spot contract (or Tranche contract with spot residual) is mandatory to monetize "
            "BESS arbitrage and avoid negative wholesale feed-in penalties."
        ),
    }
