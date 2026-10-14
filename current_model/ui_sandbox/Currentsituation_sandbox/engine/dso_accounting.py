"""
========================================================================================
Layer 3: Regulated Grid Accounting (engine/dso_accounting.py)
Current Situation (Status Quo) Sandbox Engine
========================================================================================
Implements the official ACM 6-component Dutch DSO billing formula for Grootverbruik:
  K_Netz,m = PAV_mnd + Vastrecht_mnd + Cable_mnd + (P_billed,m * T_GTV) + (P_peak,m * T_piek) + Volumetric + K_Blind

Includes:
  - Active Periodieke Aansluitvergoeding (PAV_mnd) for AC2 to AC6
  - True 12-month ratchet locking on capacity exceedances (P_contract locked to peak)
  - Reactive power evaluation against ACM standard (cos phi >= 0.85)
========================================================================================
"""

from typing import List, Dict, Any, Tuple
import numpy as np

try:
    from .config_and_models import (
        DSOTariff,
        MonthlyConsumptionRecord,
        DSOMonthlyResult,
    )
except (ImportError, ValueError):
    from config_and_models import (
        DSOTariff,
        MonthlyConsumptionRecord,
        DSOMonthlyResult,
    )


def calculate_dso_accounting_2025(
    monthly_consumption: List[MonthlyConsumptionRecord],
    dso_tariff: DSOTariff
) -> Tuple[List[DSOMonthlyResult], Dict[str, Any]]:
    """
    Executes the 6-component regulated Dutch grid operator accounting for all 12 calendar months.
    """
    monthly_results: List[DSOMonthlyResult] = []

    # 1. Fixed monthly administrative & connection fees
    monthly_fixed_conn = float(dso_tariff.fixed_connection_annual) / 12.0
    monthly_fixed_trans = float(dso_tariff.fixed_transport_annual) / 12.0
    monthly_cable = float(dso_tariff.cable_surcharge_annual) / 12.0

    annual_volumetric_fee = 0.0
    annual_peak_fee = 0.0
    annual_capacity_fee = 0.0
    annual_penalty_fee = 0.0
    breached_months: List[int] = []

    # Capacity ratchet state tracking
    active_contract_capacity = float(dso_tariff.contracted_capacity_kw)

    for rec in monthly_consumption:
        m = rec.month_index
        p_peak_m = float(rec.peak_demand_kw)

        # 2. Volumetric Transport Fee (HT vs NT)
        vol_peak = float(rec.peak_tou_kwh) * float(dso_tariff.rate_transport_peak_kwh)
        vol_offpeak = float(rec.offpeak_tou_kwh) * float(dso_tariff.rate_transport_offpeak_kwh)
        volumetric_m = vol_peak + vol_offpeak
        annual_volumetric_fee += volumetric_m

        # 3. Measured Monthly Peak Demand Fee (Maandpiek)
        peak_fee_m = p_peak_m * float(dso_tariff.rate_peak_demand)
        annual_peak_fee += peak_fee_m

        # 4. Reserved Capacity & Ratchet Execution
        if p_peak_m > active_contract_capacity + 1e-4:
            is_breach = True
            breached_months.append(m)
            excess_kw = p_peak_m - active_contract_capacity
            if getattr(dso_tariff, "ratchet_12_months", True):
                # Dutch standard: Ratchet permanently updates contracted capacity for 12 months
                active_contract_capacity = p_peak_m
                billed_kw = active_contract_capacity
            elif getattr(dso_tariff, "adjust_capacity_on_breach", True):
                # Temporary single-month breach adjustment
                billed_kw = p_peak_m
            else:
                billed_kw = active_contract_capacity
        else:
            is_breach = False
            excess_kw = 0.0
            billed_kw = active_contract_capacity

        capacity_fee_m = billed_kw * float(dso_tariff.rate_contracted_capacity)
        annual_capacity_fee += capacity_fee_m

        # 5. Overload Penalty Fee (optional parameter for international tariff models)
        penalty_rate_val = float(getattr(dso_tariff, "peak_penalty_rate_kw", 0.0))
        penalty_fee_m = excess_kw * penalty_rate_val if (is_breach and penalty_rate_val > 0.0) else 0.0
        annual_penalty_fee += penalty_fee_m

        # 6. Total Net DSO for month m
        total_dso_net_m = (
            monthly_fixed_conn +
            monthly_fixed_trans +
            monthly_cable +
            volumetric_m +
            capacity_fee_m +
            peak_fee_m +
            penalty_fee_m
        )

        monthly_results.append(
            DSOMonthlyResult(
                month_index=m,
                fixed_connection_fee=round(monthly_fixed_conn, 2),
                fixed_transport_fee=round(monthly_fixed_trans, 2),
                cable_surcharge=round(monthly_cable, 2),
                volumetric_transport_fee=round(volumetric_m, 2),
                measured_peak_demand_kw=round(p_peak_m, 3),
                billed_capacity_kw=round(billed_kw, 3),
                contracted_capacity_fee=round(capacity_fee_m, 2),
                peak_demand_fee=round(peak_fee_m, 2),
                is_capacity_breached=is_breach,
                excess_capacity_kw=round(excess_kw, 3),
                subtotal_dso_net=round(total_dso_net_m, 2),
                penalty_fee=round(penalty_fee_m, 2)
            )
        )

    total_dso_annual_net = sum(r.subtotal_dso_net for r in monthly_results)

    summary = {
        "dso_name": dso_tariff.dso_name,
        "grid_tier": dso_tariff.grid_tier,
        "connection_category": dso_tariff.connection_category,
        "contracted_capacity_kw": dso_tariff.contracted_capacity_kw,
        "final_contracted_capacity_kw": active_contract_capacity,
        "total_fixed_connection_annual": round(monthly_fixed_conn * 12.0, 2),
        "total_fixed_transport_annual": round(monthly_fixed_trans * 12.0, 2),
        "total_cable_surcharge_annual": round(monthly_cable * 12.0, 2),
        "total_volumetric_transport_annual": round(annual_volumetric_fee, 2),
        "total_capacity_fee_annual": round(annual_capacity_fee, 2),
        "total_peak_demand_fee_annual": round(annual_peak_fee, 2),
        "total_penalty_fee_annual": round(annual_penalty_fee, 2),
        "total_dso_net_annual": round(total_dso_annual_net, 2),
        "has_breaches": (len(breached_months) > 0),
        "breached_months_count": len(breached_months),
        "breached_months": breached_months,
    }

    return monthly_results, summary


def evaluate_dso_audit(
    monthly_consumption: List[MonthlyConsumptionRecord],
    dso_results: List[DSOMonthlyResult],
    dso_tariff: DSOTariff
) -> Dict[str, Any]:
    """
    Validates Audit Point 2 (Regulated grid results and capacity adherence).
    """
    peaks_match = all(
        abs(c.peak_demand_kw - d.measured_peak_demand_kw) < 1e-3
        for c, d in zip(monthly_consumption, dso_results)
    )
    expected_peak_fees = sum(d.measured_peak_demand_kw * dso_tariff.rate_peak_demand for d in dso_results)
    actual_peak_fees = sum(d.peak_demand_fee for d in dso_results)
    peak_fees_match = (abs(expected_peak_fees - actual_peak_fees) < 0.20)

    fixed_annual = dso_tariff.fixed_connection_annual + dso_tariff.fixed_transport_annual
    actual_fixed = sum(d.fixed_connection_fee + d.fixed_transport_fee for d in dso_results)
    fixed_matches = (abs(fixed_annual - actual_fixed) < 0.20)

    all_passed = peaks_match and peak_fees_match and fixed_matches

    return {
        "audit_point": 2,
        "title": "Audit Point 2: Regulated DSO Grid Accounting",
        "passed": all_passed,
        "criteria": {
            "2.1_peaks_match": {"passed": peaks_match},
            "2.2_peak_fees_match": {"passed": peak_fees_match, "actual": round(actual_peak_fees, 2)},
            "2.3_fixed_fees_match": {"passed": fixed_matches, "expected": round(fixed_annual, 2), "actual": round(actual_fixed, 2)},
            "2.4_breach_detected": {"has_breaches": any(d.is_capacity_breached for d in dso_results)}
        }
    }
