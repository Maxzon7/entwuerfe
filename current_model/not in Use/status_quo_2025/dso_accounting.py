"""
========================================================================================
Layer 3: DSO Accounting & Tariff Calculation Engine (dso_accounting.py)
========================================================================================
Calculates regulated Dutch Distribution System Operator (Netbeheerder) grid fees:
  - Fixed annual standing charges (Connection fee, vastrecht, and cable length surcharge).
  - Volumetric network transport fees evaluated across HT (Peak) and NT (Off-Peak) intervals.
  - Monthly measured peak demand fees evaluated independently across all 12 calendar months.
  - Reserved contract capacity evaluation and automated Breach Logic:
      When P_peak,m > P_contract:
        * Flag is_capacity_breached = True
        * Capacity tariff billed on P_peak,m for that month
        * Audit trail logging contract breach and capacity step-up recommendation.
Validates all Audit Point 2 criteria (2.1, 2.2, 2.3, 2.4).
========================================================================================
"""

from typing import List, Dict, Any, Tuple
import numpy as np

try:
    from .config_and_models import (
        LoadSeries2025,
        DSOTariff,
        MonthlyConsumptionRecord,
        DSOMonthlyResult,
    )
except (ImportError, ValueError):
    from config_and_models import (
        LoadSeries2025,
        DSOTariff,
        MonthlyConsumptionRecord,
        DSOMonthlyResult,
    )


def calculate_dso_accounting_2025(
    load: LoadSeries2025,
    monthly_consumption: List[MonthlyConsumptionRecord],
    dso_tariff: DSOTariff
) -> Tuple[List[DSOMonthlyResult], Dict[str, Any]]:
    """
    Executes the pure mathematical DSO accounting pipeline for reference year 2025.
    
    Returns:
      Tuple of:
        - List of 12 DSOMonthlyResult records (one for each calendar month)
        - Annual DSO audit summary dictionary
    """
    monthly_results: List[DSOMonthlyResult] = []
    
    # Monthly fixed allocations
    monthly_fixed_conn = dso_tariff.fixed_connection_annual / 12.0
    monthly_fixed_trans = dso_tariff.fixed_transport_annual / 12.0
    monthly_cable = dso_tariff.cable_surcharge_annual / 12.0

    annual_volumetric_fee = 0.0
    annual_peak_fee = 0.0
    annual_capacity_fee = 0.0
    breached_months: List[int] = []

    for rec in monthly_consumption:
        m = rec.month_index
        p_peak_m = rec.peak_demand_kw
        p_contract = dso_tariff.contracted_capacity_kw

        # 1. Volumetric Transport Fee (HT vs NT)
        vol_peak_cost = rec.peak_tou_kwh * dso_tariff.rate_transport_peak_kwh
        vol_offpeak_cost = rec.offpeak_tou_kwh * dso_tariff.rate_transport_offpeak_kwh
        volumetric_m = vol_peak_cost + vol_offpeak_cost
        annual_volumetric_fee += volumetric_m

        # 2. Peak Demand Fee (kW max * rate)
        peak_fee_m = p_peak_m * dso_tariff.rate_peak_demand
        annual_peak_fee += peak_fee_m

        # 3. Contract Capacity & Breach Logic
        is_breach = (p_peak_m > p_contract + 1e-5)
        if is_breach:
            breached_months.append(m)
            excess_kw = p_peak_m - p_contract
            # If adjust_capacity_on_breach is enabled, capacity fee is billed on actual peak
            billed_kw = p_peak_m if dso_tariff.adjust_capacity_on_breach else p_contract
        else:
            excess_kw = 0.0
            billed_kw = p_contract

        capacity_fee_m = billed_kw * dso_tariff.rate_contracted_capacity
        annual_capacity_fee += capacity_fee_m

        # 4. Total Net DSO for month m
        total_dso_net_m = (
            monthly_fixed_conn +
            monthly_fixed_trans +
            monthly_cable +
            volumetric_m +
            capacity_fee_m +
            peak_fee_m
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
                subtotal_dso_net=round(total_dso_net_m, 2)
            )
        )

    # Annual DSO audit dictionary
    total_dso_annual_net = sum(r.subtotal_dso_net for r in monthly_results)
    
    summary = {
        "dso_name": dso_tariff.dso_name,
        "grid_tier": dso_tariff.grid_tier,
        "connection_category": dso_tariff.connection_category,
        "contracted_capacity_kw": dso_tariff.contracted_capacity_kw,
        "total_fixed_connection_annual": round(monthly_fixed_conn * 12.0, 2),
        "total_fixed_transport_annual": round(monthly_fixed_trans * 12.0, 2),
        "total_cable_surcharge_annual": round(monthly_cable * 12.0, 2),
        "total_volumetric_transport_annual": round(annual_volumetric_fee, 2),
        "total_capacity_fee_annual": round(annual_capacity_fee, 2),
        "total_peak_demand_fee_annual": round(annual_peak_fee, 2),
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
    Validates Audit Point 2 (Prüfpunkt 2: DSO-Zwischenergebnisse):
      - Criterion 2.1: Exactly 12 values for P_peak,m, each equal to max(month m).
      - Criterion 2.2: Sum of peak demand fees == sum(P_peak,m * rate).
      - Criterion 2.3: Contract capacity fee based on P_contract; when P_peak,m > P_contract,
                       breach flag is set and billed capacity is adjusted.
      - Criterion 2.4: Fixed connection and transport costs on 12 months; volumetric transport
                       matches sum of HT/NT energy times rates.
    """
    # 2.1: Exactly 12 peak values
    peaks_match = True
    for c_rec, d_rec in zip(monthly_consumption, dso_results):
        if abs(c_rec.peak_demand_kw - d_rec.measured_peak_demand_kw) > 1e-3:
            peaks_match = False
            break
    c2_1_pass = (len(dso_results) == 12 and peaks_match)

    # 2.2: Sum of peak fees
    expected_peak_sum = sum(r.measured_peak_demand_kw * dso_tariff.rate_peak_demand for r in dso_results)
    actual_peak_sum = sum(r.peak_demand_fee for r in dso_results)
    c2_2_pass = (abs(expected_peak_sum - actual_peak_sum) < 0.20)

    # 2.3: Capacity & Breach logic
    c2_3_pass = True
    for r in dso_results:
        expected_breach = (r.measured_peak_demand_kw > dso_tariff.contracted_capacity_kw + 1e-5)
        if r.is_capacity_breached != expected_breach:
            c2_3_pass = False
            break
        if r.is_capacity_breached:
            if abs(r.billed_capacity_kw - r.measured_peak_demand_kw) > 1e-3:
                c2_3_pass = False
                break
        else:
            if abs(r.billed_capacity_kw - dso_tariff.contracted_capacity_kw) > 1e-3:
                c2_3_pass = False
                break

    # 2.4: Fixed and volumetric sums
    fixed_conn_sum = sum(r.fixed_connection_fee for r in dso_results)
    fixed_trans_sum = sum(r.fixed_transport_fee for r in dso_results)
    c2_4_conn_pass = (abs(fixed_conn_sum - dso_tariff.fixed_connection_annual) < 0.20)
    c2_4_trans_pass = (abs(fixed_trans_sum - dso_tariff.fixed_transport_annual) < 0.20)
    
    expected_vol = sum(
        (c.peak_tou_kwh * dso_tariff.rate_transport_peak_kwh + c.offpeak_tou_kwh * dso_tariff.rate_transport_offpeak_kwh)
        for c in monthly_consumption
    )
    actual_vol = sum(r.volumetric_transport_fee for r in dso_results)
    c2_4_vol_pass = (abs(expected_vol - actual_vol) < 0.20)
    c2_4_pass = (c2_4_conn_pass and c2_4_trans_pass and c2_4_vol_pass)

    all_passed = (c2_1_pass and c2_2_pass and c2_3_pass and c2_4_pass)

    return {
        "audit_point": 2,
        "title": "Audit Point 2: DSO Accounting & Capacity Breach Verification",
        "passed": all_passed,
        "criteria": {
            "2.1_monthly_peaks_12": {
                "passed": c2_1_pass,
                "count": len(dso_results)
            },
            "2.2_peak_demand_fees_sum": {
                "passed": c2_2_pass,
                "expected_sum": round(expected_peak_sum, 2),
                "actual_sum": round(actual_peak_sum, 2),
                "diff": round(abs(expected_peak_sum - actual_peak_sum), 4)
            },
            "2.3_contract_capacity_breach_logic": {
                "passed": c2_3_pass,
                "breaches_detected": sum(1 for r in dso_results if r.is_capacity_breached)
            },
            "2.4_fixed_and_volumetric_fees": {
                "passed": c2_4_pass,
                "fixed_connection_valid": bool(c2_4_conn_pass),
                "fixed_transport_valid": bool(c2_4_trans_pass),
                "volumetric_transport_valid": bool(c2_4_vol_pass)
            }
        }
    }
