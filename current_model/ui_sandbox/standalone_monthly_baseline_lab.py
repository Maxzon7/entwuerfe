"""
========================================================================================
Standalone Monthly Baseline & Commercial Electricity Tariff Lab
(current_model/ui_sandbox/standalone_monthly_baseline_lab.py)
========================================================================================

Architecture & Isolation:
-------------------------
- Fully autarkic UI laboratory for 12-month baseline load ingestion & commercial contract simulation.
- Symmetrical dual 12-month matrix layout:
    1. Table A: 12-Month Consumption & Peak Demand Matrix (kWh per TOU window, P_contract, P_max)
    2. Table B: 12-Month Contract & Tariff Matrix (Base fee, $/kW contracted, $/kW over limit,
       $/kW peak demand, $/kWh per TOU window, Taxes %)
- Dynamic N-Tier Time-of-Use (TOU) window management (configure number of windows and names).
- Exact monthly precision with live financial billing ledger, stacked Plotly charts, and CSV/JSON export.
- Strictly isolated inside ui_sandbox/ with zero production risk for app.py.
========================================================================================
"""

import io
import os
import sys
import json
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional, Tuple

import pandas as pd
import numpy as np
import streamlit as st
import plotly.graph_objects as go

# Ensure project root and current_model are on sys.path
SANDBOX_DIR = os.path.dirname(os.path.abspath(__file__))
CURRENT_MODEL_DIR = os.path.abspath(os.path.join(SANDBOX_DIR, ".."))
WORKSPACE_ROOT = os.path.abspath(os.path.join(CURRENT_MODEL_DIR, ".."))

for path in [WORKSPACE_ROOT, CURRENT_MODEL_DIR]:
    if path not in sys.path:
        sys.path.insert(0, path)

try:
    from current_model.ui.common.styles import apply_custom_styles
except ImportError:
    apply_custom_styles = None


# ========================================================================================
# 1. Domain Data Classes & Mathematical Core Engine
# ========================================================================================

@dataclass
class TOUTierConfig:
    """Represents a single Time-of-Use energy pricing window."""
    id: str
    name: str
    time_window: str = "Standard Hours"
    color: str = "#EF4444"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "time_window": self.time_window,
            "color": self.color
        }


@dataclass
class MonthlyBillingResult:
    """Detailed itemized bill for a single calendar month."""
    month_index: int
    month_name: str
    contracted_capacity_kw: float
    peak_demand_kw: float
    excess_peak_kw: float  # max(0, peak_demand_kw - contracted_capacity_kw)

    # Energy volume and cost by TOU tier
    kwh_by_tier: Dict[str, float]
    kwh_total: float
    cost_energy_by_tier_local: Dict[str, float]
    cost_energy_by_tier_eur: Dict[str, float]
    cost_energy_total_local: float
    cost_energy_total_eur: float

    # Capacity, Demand, Penalty, Standing and Exempt charges
    cost_contracted_capacity_local: float
    cost_contracted_capacity_eur: float
    cost_measured_demand_local: float
    cost_measured_demand_eur: float
    cost_penalty_local: float
    cost_penalty_eur: float
    cost_base_fee_local: float
    cost_base_fee_eur: float
    cost_exempt_surcharge_local: float
    cost_exempt_surcharge_eur: float

    # Monthly Aggregates
    cost_fixed_total_local: float
    cost_fixed_total_eur: float
    cost_total_local: float
    cost_total_eur: float
    blended_rate_eur_per_kwh: float
    blended_rate_local_per_kwh: float


@dataclass
class AnnualBillingSummary:
    """Aggregated annual financial statement across all 12 months."""
    monthly_results: List[MonthlyBillingResult]
    total_kwh_by_tier: Dict[str, float]
    total_kwh: float
    max_peak_kw: float
    contracted_kw: float
    total_excess_peak_kw_months: float
    months_with_excess_peak: int

    # Energy cost totals
    cost_energy_by_tier_total_eur: Dict[str, float]
    cost_energy_by_tier_total_local: Dict[str, float]
    cost_energy_total_eur: float
    cost_energy_total_local: float

    # Grid, demand, and penalty totals
    cost_contracted_capacity_annual_eur: float
    cost_contracted_capacity_annual_local: float
    cost_measured_demand_annual_eur: float
    cost_measured_demand_annual_local: float
    cost_penalty_annual_eur: float
    cost_penalty_annual_local: float
    cost_base_fee_annual_eur: float
    cost_base_fee_annual_local: float
    cost_exempt_surcharge_annual_eur: float
    cost_exempt_surcharge_annual_local: float

    # Overall grand totals
    cost_fixed_annual_eur: float
    cost_fixed_annual_local: float
    cost_total_annual_eur: float
    cost_total_annual_local: float
    blended_rate_annual_eur: float
    blended_rate_annual_local: float

    # Verification status for reference presets
    is_salentein_verified: bool = False
    verification_target_eur: float = 36234.97
    verification_delta_eur: float = 0.0


def compute_monthly_billing(
    consumption_df: pd.DataFrame,
    tariff_df: pd.DataFrame,
    tou_tiers: List[TOUTierConfig],
    currency: str = "ARS",
    fx_rate: float = 1300.0
) -> AnnualBillingSummary:
    """
    Computes monthly and annual electricity costs by coupling the 12-month consumption
    matrix (Table A) with the 12-month contract & tariff matrix (Table B).
    """
    is_eur_currency = (str(currency).strip().upper() == "EUR")
    fx = 1.0 if is_eur_currency else max(float(fx_rate), 1e-9)
    monthly_results: List[MonthlyBillingResult] = []

    for idx in range(len(consumption_df)):
        c_row = consumption_df.iloc[idx]
        t_row = tariff_df.iloc[idx] if idx < len(tariff_df) else tariff_df.iloc[-1]

        m_idx = int(c_row.get("month_index", idx + 1))
        m_name = str(c_row.get("Month", f"Month {m_idx}"))
        p_contract = float(c_row.get("P_contract_kW", 104.0))
        p_max = float(c_row.get("P_max_kW", 0.0))
        excess_p = max(0.0, p_max - p_contract)

        # Tax rates for this month
        tax_pct = float(t_row.get("tax_rate_pct", 37.59))
        tax_mult = 1.0 + (tax_pct / 100.0)

        # Fixed tax rate: if the user edited tax_rate_pct in Table B, apply tax_pct;
        # otherwise preserve the preset's fixed tax percentage if specifically configured for Salentein
        if "tax_rate_fixed_pct" in t_row and not pd.isna(t_row["tax_rate_fixed_pct"]) and abs(tax_pct - 37.59) < 1e-3:
            fixed_tax_pct = float(t_row["tax_rate_fixed_pct"])
        else:
            fixed_tax_pct = tax_pct
        fixed_tax_mult = 1.0 + (fixed_tax_pct / 100.0)

        # 1. Energy Volumes and Costs per TOU Tier
        kwh_tier_dict: Dict[str, float] = {}
        cost_e_tier_local: Dict[str, float] = {}
        cost_e_tier_eur: Dict[str, float] = {}

        for tier in tou_tiers:
            c_col = f"kWh_{tier.id}"
            t_col = f"rate_{tier.id}"

            # Robust column fallback
            if c_col not in c_row and tier.id == "peak" and "kWh_peak" in c_row:
                kwh_val = float(c_row.get("kWh_peak", 0.0))
            elif c_col not in c_row and tier.id == "offpeak" and "kWh_offpeak" in c_row:
                kwh_val = float(c_row.get("kWh_offpeak", 0.0))
            else:
                kwh_val = float(c_row.get(c_col, 0.0))

            if t_col not in t_row and tier.id == "peak" and "rate_peak" in t_row:
                rate_net = float(t_row.get("rate_peak", 172.46))
            elif t_col not in t_row and tier.id == "offpeak" and "rate_offpeak" in t_row:
                rate_net = float(t_row.get("rate_offpeak", 106.97))
            else:
                rate_net = float(t_row.get(t_col, 0.0))

            kwh_tier_dict[tier.id] = kwh_val
            rate_gross_local = rate_net * tax_mult
            cost_tier_local = kwh_val * rate_gross_local
            cost_tier_eur = cost_tier_local / fx

            cost_e_tier_local[tier.id] = cost_tier_local
            cost_e_tier_eur[tier.id] = cost_tier_eur

        tot_kwh = sum(kwh_tier_dict.values())
        tot_energy_local = sum(cost_e_tier_local.values())
        tot_energy_eur = sum(cost_e_tier_eur.values())

        # 2. Contracted Capacity Fee ($/kW contracted)
        rate_contracted = float(t_row.get("rate_contracted_kw", 0.0))
        cap_cost_net_local = p_contract * rate_contracted
        cap_cost_gross_local = cap_cost_net_local * fixed_tax_mult
        cap_cost_eur = cap_cost_gross_local / fx

        # 3. Measured Peak Demand Fee ($/kW measured peak)
        rate_peak_dem = float(t_row.get("rate_peak_demand_kw", 0.0))
        dem_cost_net_local = p_max * rate_peak_dem
        dem_cost_gross_local = dem_cost_net_local * fixed_tax_mult
        dem_cost_eur = dem_cost_gross_local / fx

        # 4. Limit Exceedance Penalty ($/kW over limit)
        rate_penalty = float(t_row.get("rate_excess_kw", 0.0))
        pen_cost_net_local = excess_p * rate_penalty
        pen_cost_gross_local = pen_cost_net_local * fixed_tax_mult
        pen_cost_eur = pen_cost_gross_local / fx

        # 5. Base Standing Fee (Grundpreis / month)
        base_fee_net_local = float(t_row.get("base_fee", 0.0))
        base_fee_gross_local = base_fee_net_local * fixed_tax_mult
        base_fee_eur = base_fee_gross_local / fx

        # 6. Non-taxable Municipal Lighting / Fixed Exempt Surcharges (only for ARS preset)
        if is_eur_currency:
            exempt_val = float(t_row.get("exempt_surcharge", 0.0))
            exempt_eur = exempt_val if abs(exempt_val - 16688.0) > 1e-3 else 0.0
            exempt_local = exempt_eur
        else:
            exempt_local = float(t_row.get("exempt_surcharge", 0.0))
            exempt_eur = exempt_local / fx

        # Monthly Aggregations
        fixed_tot_local = cap_cost_gross_local + dem_cost_gross_local + pen_cost_gross_local + base_fee_gross_local + exempt_local
        fixed_tot_eur = cap_cost_eur + dem_cost_eur + pen_cost_eur + base_fee_eur + exempt_eur

        month_tot_local = tot_energy_local + fixed_tot_local
        month_tot_eur = tot_energy_eur + fixed_tot_eur

        blended_eur = month_tot_eur / tot_kwh if tot_kwh > 0 else 0.0
        blended_local = month_tot_local / tot_kwh if tot_kwh > 0 else 0.0

        monthly_results.append(MonthlyBillingResult(
            month_index=m_idx,
            month_name=m_name,
            contracted_capacity_kw=p_contract,
            peak_demand_kw=p_max,
            excess_peak_kw=excess_p,
            kwh_by_tier=kwh_tier_dict,
            kwh_total=tot_kwh,
            cost_energy_by_tier_local=cost_e_tier_local,
            cost_energy_by_tier_eur=cost_e_tier_eur,
            cost_energy_total_local=tot_energy_local,
            cost_energy_total_eur=tot_energy_eur,
            cost_contracted_capacity_local=cap_cost_gross_local,
            cost_contracted_capacity_eur=cap_cost_eur,
            cost_measured_demand_local=dem_cost_gross_local,
            cost_measured_demand_eur=dem_cost_eur,
            cost_penalty_local=pen_cost_gross_local,
            cost_penalty_eur=pen_cost_eur,
            cost_base_fee_local=base_fee_gross_local,
            cost_base_fee_eur=base_fee_eur,
            cost_exempt_surcharge_local=exempt_local,
            cost_exempt_surcharge_eur=exempt_eur,
            cost_fixed_total_local=fixed_tot_local,
            cost_fixed_total_eur=fixed_tot_eur,
            cost_total_local=month_tot_local,
            cost_total_eur=month_tot_eur,
            blended_rate_eur_per_kwh=blended_eur,
            blended_rate_local_per_kwh=blended_local
        ))

    # Annual Aggregations
    tot_kwh_by_tier: Dict[str, float] = {tier.id: 0.0 for tier in tou_tiers}
    cost_e_tier_tot_local: Dict[str, float] = {tier.id: 0.0 for tier in tou_tiers}
    cost_e_tier_tot_eur: Dict[str, float] = {tier.id: 0.0 for tier in tou_tiers}

    for r in monthly_results:
        for t_id in tot_kwh_by_tier.keys():
            tot_kwh_by_tier[t_id] += r.kwh_by_tier.get(t_id, 0.0)
            cost_e_tier_tot_local[t_id] += r.cost_energy_by_tier_local.get(t_id, 0.0)
            cost_e_tier_tot_eur[t_id] += r.cost_energy_by_tier_eur.get(t_id, 0.0)

    grand_tot_kwh = sum(r.kwh_total for r in monthly_results)
    max_peak = max((r.peak_demand_kw for r in monthly_results), default=0.0)
    avg_contracted = monthly_results[0].contracted_capacity_kw if monthly_results else 0.0
    tot_excess_kw = sum(r.excess_peak_kw for r in monthly_results)
    months_with_excess = sum(1 for r in monthly_results if r.excess_peak_kw > 0)

    cost_energy_tot_eur = sum(r.cost_energy_total_eur for r in monthly_results)
    cost_energy_tot_local = sum(r.cost_energy_total_local for r in monthly_results)

    cost_cap_annual_eur = sum(r.cost_contracted_capacity_eur for r in monthly_results)
    cost_cap_annual_local = sum(r.cost_contracted_capacity_local for r in monthly_results)

    cost_dem_annual_eur = sum(r.cost_measured_demand_eur for r in monthly_results)
    cost_dem_annual_local = sum(r.cost_measured_demand_local for r in monthly_results)

    cost_pen_annual_eur = sum(r.cost_penalty_eur for r in monthly_results)
    cost_pen_annual_local = sum(r.cost_penalty_local for r in monthly_results)

    cost_base_annual_eur = sum(r.cost_base_fee_eur for r in monthly_results)
    cost_base_annual_local = sum(r.cost_base_fee_local for r in monthly_results)

    cost_exempt_annual_eur = sum(r.cost_exempt_surcharge_eur for r in monthly_results)
    cost_exempt_annual_local = sum(r.cost_exempt_surcharge_local for r in monthly_results)

    cost_fixed_annual_eur = cost_cap_annual_eur + cost_dem_annual_eur + cost_pen_annual_eur + cost_base_annual_eur + cost_exempt_annual_eur
    cost_fixed_annual_local = cost_cap_annual_local + cost_dem_annual_local + cost_pen_annual_local + cost_base_annual_local + cost_exempt_annual_local

    cost_tot_annual_eur = cost_energy_tot_eur + cost_fixed_annual_eur
    cost_tot_annual_local = cost_energy_tot_local + cost_fixed_annual_local

    annual_blended_eur = cost_tot_annual_eur / grand_tot_kwh if grand_tot_kwh > 0 else 0.0
    annual_blended_local = cost_tot_annual_local / grand_tot_kwh if grand_tot_kwh > 0 else 0.0

    target_eur = 36234.97
    delta = abs(cost_tot_annual_eur - target_eur)
    is_verified = (delta < 0.05)

    return AnnualBillingSummary(
        monthly_results=monthly_results,
        total_kwh_by_tier=tot_kwh_by_tier,
        total_kwh=grand_tot_kwh,
        max_peak_kw=max_peak,
        contracted_kw=avg_contracted,
        total_excess_peak_kw_months=tot_excess_kw,
        months_with_excess_peak=months_with_excess,
        cost_energy_by_tier_total_eur=cost_e_tier_tot_eur,
        cost_energy_by_tier_total_local=cost_e_tier_tot_local,
        cost_energy_total_eur=cost_energy_tot_eur,
        cost_energy_total_local=cost_energy_tot_local,
        cost_contracted_capacity_annual_eur=cost_cap_annual_eur,
        cost_contracted_capacity_annual_local=cost_cap_annual_local,
        cost_measured_demand_annual_eur=cost_dem_annual_eur,
        cost_measured_demand_annual_local=cost_dem_annual_local,
        cost_penalty_annual_eur=cost_pen_annual_eur,
        cost_penalty_annual_local=cost_pen_annual_local,
        cost_base_fee_annual_eur=cost_base_annual_eur,
        cost_base_fee_annual_local=cost_base_annual_local,
        cost_exempt_surcharge_annual_eur=cost_exempt_annual_eur,
        cost_exempt_surcharge_annual_local=cost_exempt_annual_local,
        cost_fixed_annual_eur=cost_fixed_annual_eur,
        cost_fixed_annual_local=cost_fixed_annual_local,
        cost_total_annual_eur=cost_tot_annual_eur,
        cost_total_annual_local=cost_tot_annual_local,
        blended_rate_annual_eur=annual_blended_eur,
        blended_rate_annual_local=annual_blended_local,
        is_salentein_verified=is_verified,
        verification_target_eur=target_eur,
        verification_delta_eur=delta
    )


# ========================================================================================
# 2. Standard Industry Presets
# ========================================================================================

MONTHS_LIST = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
]


def get_salentein_pozo600_preset() -> Tuple[pd.DataFrame, pd.DataFrame, List[TOUTierConfig], str, float, str]:
    """Bodegas Salentein Pozo 600 reference dataset (Excel Blatt 1.1 & 1.3)."""
    consumption_data = [
        {"month_index": 1, "Month": "January", "P_contract_kW": 104.0, "P_max_kW": 103.0, "kWh_peak": 11190.0, "kWh_offpeak": 17730.0},
        {"month_index": 2, "Month": "February", "P_contract_kW": 104.0, "P_max_kW": 103.0, "kWh_peak": 14130.0, "kWh_offpeak": 23820.0},
        {"month_index": 3, "Month": "March", "P_contract_kW": 104.0, "P_max_kW": 102.0, "kWh_peak": 16032.0, "kWh_offpeak": 23328.0},
        {"month_index": 4, "Month": "April", "P_contract_kW": 104.0, "P_max_kW": 104.0, "kWh_peak": 11322.0, "kWh_offpeak": 18318.0},
        {"month_index": 5, "Month": "May", "P_contract_kW": 104.0, "P_max_kW": 103.0, "kWh_peak": 3582.0, "kWh_offpeak": 6396.0},
        {"month_index": 6, "Month": "June", "P_contract_kW": 104.0, "P_max_kW": 0.0, "kWh_peak": 12.0, "kWh_offpeak": 30.0},
        {"month_index": 7, "Month": "July", "P_contract_kW": 104.0, "P_max_kW": 0.0, "kWh_peak": 12.0, "kWh_offpeak": 30.0},
        {"month_index": 8, "Month": "August", "P_contract_kW": 104.0, "P_max_kW": 101.0, "kWh_peak": 2898.0, "kWh_offpeak": 3444.0},
        {"month_index": 9, "Month": "September", "P_contract_kW": 104.0, "P_max_kW": 105.0, "kWh_peak": 4056.0, "kWh_offpeak": 5220.0},
        {"month_index": 10, "Month": "October", "P_contract_kW": 104.0, "P_max_kW": 103.0, "kWh_peak": 7038.0, "kWh_offpeak": 8748.0},
        {"month_index": 11, "Month": "November", "P_contract_kW": 104.0, "P_max_kW": 104.0, "kWh_peak": 6906.0, "kWh_offpeak": 10434.0},
        {"month_index": 12, "Month": "December", "P_contract_kW": 104.0, "P_max_kW": 103.0, "kWh_peak": 10824.0, "kWh_offpeak": 16350.0},
    ]
    c_df = pd.DataFrame(consumption_data)

    tou_tiers = [
        TOUTierConfig(id="peak", name="High Energy (Pico)", time_window="14:00 - 23:00", color="#EF4444"),
        TOUTierConfig(id="offpeak", name="Low Energy (Valle/Resto)", time_window="23:00 - 14:00", color="#3B82F6")
    ]

    tariff_data = []
    for idx, m in enumerate(MONTHS_LIST, 1):
        tariff_data.append({
            "month_index": idx,
            "Month": m,
            "base_fee": 28929.64,
            "rate_contracted_kw": 3589.886,
            "rate_excess_kw": 0.0,
            "rate_peak_demand_kw": 0.0,
            "rate_peak": 172.46,
            "rate_offpeak": 106.97,
            "tax_rate_pct": 37.59,
            "tax_rate_fixed_pct": 30.996984,
            "exempt_surcharge": 16688.00
        })
    t_df = pd.DataFrame(tariff_data)

    return c_df, t_df, tou_tiers, "ARS", 1300.0, "Bodegas Salentein (Pozo 600 - EDEMSA T2 R MT)"


def get_3tier_argentine_preset() -> Tuple[pd.DataFrame, pd.DataFrame, List[TOUTierConfig], str, float, str]:
    """3-Tier Argentine Industrial Supply Contract (Pico, Resto, Valle) with peak penalties."""
    consumption_data = [
        {"month_index": 1, "Month": "January", "P_contract_kW": 250.0, "P_max_kW": 240.0, "kWh_peak": 12500.0, "kWh_resto": 22000.0, "kWh_valle": 14500.0},
        {"month_index": 2, "Month": "February", "P_contract_kW": 250.0, "P_max_kW": 245.0, "kWh_peak": 13100.0, "kWh_resto": 23500.0, "kWh_valle": 15200.0},
        {"month_index": 3, "Month": "March", "P_contract_kW": 250.0, "P_max_kW": 252.0, "kWh_peak": 14200.0, "kWh_resto": 24800.0, "kWh_valle": 16000.0},
        {"month_index": 4, "Month": "April", "P_contract_kW": 250.0, "P_max_kW": 238.0, "kWh_peak": 11800.0, "kWh_resto": 21000.0, "kWh_valle": 13900.0},
        {"month_index": 5, "Month": "May", "P_contract_kW": 250.0, "P_max_kW": 220.0, "kWh_peak": 9500.0, "kWh_resto": 18200.0, "kWh_valle": 11400.0},
        {"month_index": 6, "Month": "June", "P_contract_kW": 250.0, "P_max_kW": 210.0, "kWh_peak": 8200.0, "kWh_resto": 16500.0, "kWh_valle": 10200.0},
        {"month_index": 7, "Month": "July", "P_contract_kW": 250.0, "P_max_kW": 215.0, "kWh_peak": 8400.0, "kWh_resto": 16800.0, "kWh_valle": 10500.0},
        {"month_index": 8, "Month": "August", "P_contract_kW": 250.0, "P_max_kW": 230.0, "kWh_peak": 10100.0, "kWh_resto": 19200.0, "kWh_valle": 12300.0},
        {"month_index": 9, "Month": "September", "P_contract_kW": 250.0, "P_max_kW": 258.0, "kWh_peak": 13800.0, "kWh_resto": 24000.0, "kWh_valle": 15800.0},
        {"month_index": 10, "Month": "October", "P_contract_kW": 250.0, "P_max_kW": 248.0, "kWh_peak": 12900.0, "kWh_resto": 22800.0, "kWh_valle": 14900.0},
        {"month_index": 11, "Month": "November", "P_contract_kW": 250.0, "P_max_kW": 250.0, "kWh_peak": 13400.0, "kWh_resto": 23600.0, "kWh_valle": 15400.0},
        {"month_index": 12, "Month": "December", "P_contract_kW": 250.0, "P_max_kW": 255.0, "kWh_peak": 14500.0, "kWh_resto": 25400.0, "kWh_valle": 16800.0},
    ]
    c_df = pd.DataFrame(consumption_data)

    tou_tiers = [
        TOUTierConfig(id="peak", name="Pico (On-Peak)", time_window="18:00 - 23:00", color="#EF4444"),
        TOUTierConfig(id="resto", name="Resto (Mid-Peak)", time_window="05:00 - 18:00", color="#F59E0B"),
        TOUTierConfig(id="valle", name="Valle (Off-Peak)", time_window="23:00 - 05:00", color="#3B82F6")
    ]

    tariff_data = []
    for idx, m in enumerate(MONTHS_LIST, 1):
        tariff_data.append({
            "month_index": idx,
            "Month": m,
            "base_fee": 45000.00,
            "rate_contracted_kw": 3589.886,
            "rate_excess_kw": 4500.00,
            "rate_peak_demand_kw": 450.00,
            "rate_peak": 172.46,
            "rate_resto": 135.20,
            "rate_valle": 106.97,
            "tax_rate_pct": 37.59,
            "tax_rate_fixed_pct": 37.59,
            "exempt_surcharge": 22500.00
        })
    t_df = pd.DataFrame(tariff_data)

    return c_df, t_df, tou_tiers, "ARS", 1300.0, "Argentine 3-Tier Industrial (Pico / Resto / Valle)"


def get_netherlands_commercial_preset() -> Tuple[pd.DataFrame, pd.DataFrame, List[TOUTierConfig], str, float, str]:
    """Dutch commercial customer under Enexis MS-D network tariffs."""
    consumption_data = [
        {"month_index": 1, "Month": "January", "P_contract_kW": 250.0, "P_max_kW": 210.0, "kWh_peak": 18500.0, "kWh_offpeak": 14200.0},
        {"month_index": 2, "Month": "February", "P_contract_kW": 250.0, "P_max_kW": 215.0, "kWh_peak": 17200.0, "kWh_offpeak": 13800.0},
        {"month_index": 3, "Month": "March", "P_contract_kW": 250.0, "P_max_kW": 195.0, "kWh_peak": 16400.0, "kWh_offpeak": 12900.0},
        {"month_index": 4, "Month": "April", "P_contract_kW": 250.0, "P_max_kW": 180.0, "kWh_peak": 14800.0, "kWh_offpeak": 11500.0},
        {"month_index": 5, "Month": "May", "P_contract_kW": 250.0, "P_max_kW": 170.0, "kWh_peak": 13900.0, "kWh_offpeak": 10800.0},
        {"month_index": 6, "Month": "June", "P_contract_kW": 250.0, "P_max_kW": 165.0, "kWh_peak": 13200.0, "kWh_offpeak": 10400.0},
        {"month_index": 7, "Month": "July", "P_contract_kW": 250.0, "P_max_kW": 160.0, "kWh_peak": 12800.0, "kWh_offpeak": 9900.0},
        {"month_index": 8, "Month": "August", "P_contract_kW": 250.0, "P_max_kW": 168.0, "kWh_peak": 13500.0, "kWh_offpeak": 10200.0},
        {"month_index": 9, "Month": "September", "P_contract_kW": 250.0, "P_max_kW": 260.0, "kWh_peak": 15100.0, "kWh_offpeak": 11800.0},
        {"month_index": 10, "Month": "October", "P_contract_kW": 250.0, "P_max_kW": 200.0, "kWh_peak": 16800.0, "kWh_offpeak": 13100.0},
        {"month_index": 11, "Month": "November", "P_contract_kW": 250.0, "P_max_kW": 220.0, "kWh_peak": 18100.0, "kWh_offpeak": 14500.0},
        {"month_index": 12, "Month": "December", "P_contract_kW": 250.0, "P_max_kW": 230.0, "kWh_peak": 19600.0, "kWh_offpeak": 15400.0},
    ]
    c_df = pd.DataFrame(consumption_data)

    tou_tiers = [
        TOUTierConfig(id="peak", name="Piek (07:00 - 23:00)", time_window="07:00 - 23:00", color="#EF4444"),
        TOUTierConfig(id="offpeak", name="Dal (23:00 - 07:00)", time_window="23:00 - 07:00", color="#3B82F6")
    ]

    tariff_data = []
    for idx, m in enumerate(MONTHS_LIST, 1):
        tariff_data.append({
            "month_index": idx,
            "Month": m,
            "base_fee": 125.00,
            "rate_contracted_kw": 3.85,
            "rate_excess_kw": 8.50,
            "rate_peak_demand_kw": 1.20,
            "rate_peak": 0.1450,
            "rate_offpeak": 0.1050,
            "tax_rate_pct": 21.0,
            "tax_rate_fixed_pct": 21.0,
            "exempt_surcharge": 0.0
        })
    t_df = pd.DataFrame(tariff_data)

    return c_df, t_df, tou_tiers, "EUR", 1.0, "Netherlands Commercial (Enexis MS-D Grid + ToU)"


# ========================================================================================
# 3. Streamlit Laboratory UI
# ========================================================================================

def render_monthly_baseline_lab(key_prefix: str = "monthly_baseline"):
    """Main renderer for the standalone monthly baseline and commercial tariff laboratory."""

    # Session State Keys
    state_cdf_key = f"{key_prefix}_consumption_df"
    state_tdf_key = f"{key_prefix}_tariff_df"
    state_tiers_key = f"{key_prefix}_tou_tiers"
    state_currency_key = f"{key_prefix}_currency"
    state_fx_key = f"{key_prefix}_fx_rate"
    state_preset_name_key = f"{key_prefix}_preset_name"

    # Robust Initialization
    needs_init = (
        state_cdf_key not in st.session_state
        or state_tdf_key not in st.session_state
        or state_tiers_key not in st.session_state
    )

    if needs_init:
        c_init, t_init, tiers_init, cur_init, fx_init, name_init = get_salentein_pozo600_preset()
        st.session_state[state_cdf_key] = c_init
        st.session_state[state_tdf_key] = t_init
        st.session_state[state_tiers_key] = tiers_init
        st.session_state[state_currency_key] = cur_init
        st.session_state[state_fx_key] = fx_init
        st.session_state[state_preset_name_key] = name_init

    active_tiers: List[TOUTierConfig] = st.session_state[state_tiers_key]
    currency: str = st.session_state[state_currency_key]
    fx_rate: float = float(st.session_state[state_fx_key])
    preset_name: str = st.session_state[state_preset_name_key]

    # ==============================================================================
    # Section 1: Header, Standard Presets & Currency
    # ==============================================================================
    st.markdown("## :material/science: Monthly Baseline & Commercial Tariff Laboratory")
    st.caption(
        "Symmetrical dual-matrix workspace: enter monthly consumption volumes and monthly contract tariffs "
        "across all 12 calendar months with dynamic Time-of-Use windows."
    )

    pcol1, pcol2, pcol3, pcol4 = st.columns([1.5, 1.5, 1.5, 2.0])

    with pcol1:
        if st.button(":material/download: Salentein Pozo 600", key=f"{key_prefix}_btn_salentein", use_container_width=True):
            c_s, t_s, tiers_s, cur_s, fx_s, name_s = get_salentein_pozo600_preset()
            st.session_state[state_cdf_key] = c_s
            st.session_state[state_tdf_key] = t_s
            st.session_state[state_tiers_key] = tiers_s
            st.session_state[state_currency_key] = cur_s
            st.session_state[state_fx_key] = fx_s
            st.session_state[state_preset_name_key] = name_s
            st.rerun()

    with pcol2:
        if st.button(":material/factory: Argentine 3-Tier", key=f"{key_prefix}_btn_3tier", use_container_width=True):
            c_3, t_3, tiers_3, cur_3, fx_3, name_3 = get_3tier_argentine_preset()
            st.session_state[state_cdf_key] = c_3
            st.session_state[state_tdf_key] = t_3
            st.session_state[state_tiers_key] = tiers_3
            st.session_state[state_currency_key] = cur_3
            st.session_state[state_fx_key] = fx_3
            st.session_state[state_preset_name_key] = name_3
            st.rerun()

    with pcol3:
        if st.button(":material/euro: Netherlands Enexis", key=f"{key_prefix}_btn_nl", use_container_width=True):
            c_n, t_n, tiers_n, cur_n, fx_n, name_n = get_netherlands_commercial_preset()
            st.session_state[state_cdf_key] = c_n
            st.session_state[state_tdf_key] = t_n
            st.session_state[state_tiers_key] = tiers_n
            st.session_state[state_currency_key] = cur_n
            st.session_state[state_fx_key] = fx_n
            st.session_state[state_preset_name_key] = name_n
            st.rerun()

    with pcol4:
        st.info(f":material/bookmark: Active: **{preset_name}**", icon=":material/tune:")

    # Currency & FX Conversion Controls
    with st.container(border=True):
        cur_col1, cur_col2, cur_col3 = st.columns([1.5, 1.5, 3.0])
        with cur_col1:
            prev_cur = st.session_state.get(state_currency_key, currency)
            selected_cur = st.selectbox(
                "Contract Currency",
                options=["ARS", "EUR", "USD", "GBP"],
                index=0 if currency == "ARS" else (1 if currency == "EUR" else (2 if currency == "USD" else 3)),
                key=f"{key_prefix}_select_currency"
            )
            # If currency was changed, update sensible default FX rate
            if selected_cur != prev_cur:
                st.session_state[state_currency_key] = selected_cur
                if selected_cur == "EUR":
                    st.session_state[state_fx_key] = 1.0
                elif selected_cur == "ARS":
                    st.session_state[state_fx_key] = 1300.0
                elif selected_cur == "USD":
                    st.session_state[state_fx_key] = 1.08
                elif selected_cur == "GBP":
                    st.session_state[state_fx_key] = 0.86
                st.rerun()

        with cur_col2:
            is_eur = (selected_cur == "EUR")
            if is_eur:
                st.session_state[state_fx_key] = 1.0
                input_fx = 1.0
                st.text_input(
                    f"Exchange Rate ({selected_cur} / EUR)",
                    value="1.0000 (Direct €)",
                    disabled=True,
                    help="1 EUR = 1 EUR. Contract rates in Table B are directly evaluated in Euro without currency conversion."
                )
            else:
                curr_fx_val = float(st.session_state.get(state_fx_key, fx_rate))
                input_fx = st.number_input(
                    f"Exchange Rate ({selected_cur} / EUR)",
                    min_value=0.0001,
                    max_value=100000.0,
                    value=curr_fx_val,
                    step=10.0 if selected_cur == "ARS" else 0.05,
                    format="%.4f",
                    help=f"Rates in {selected_cur} are divided by this exchange rate to calculate Euro (€) totals.",
                    key=f"{key_prefix}_num_fx"
                )
                st.session_state[state_fx_key] = input_fx
        with cur_col3:
            if is_eur:
                st.caption("Reporting Currency: **EUR (€)**  \nExchange rate is locked at `1.0000` (1 EUR = 1 EUR). Contract rates in Table B are directly evaluated in Euro without foreign currency division.")
            else:
                st.caption(f"Reporting Currency: **EUR (€)**  \nContract rates in `{selected_cur}` are converted to Euro (€) using: `Cost_EUR = Cost_{selected_cur} / {input_fx:.2f}`.")

    st.markdown("---")

    # ==============================================================================
    # Section 2: Time-of-Use (TOU) Windows Configuration
    # ==============================================================================
    st.markdown("### :material/schedule: 1. Time-of-Use (TOU) Windows Configuration")
    st.caption("Configure the number of TOU windows and their names. Both tables below automatically adapt their columns.")

    with st.container(border=True):
        col_t_title, col_t_actions = st.columns([3, 2])
        with col_t_title:
            st.markdown(f"**Active TOU Windows ({len(active_tiers)} Tiers)**")
        with col_t_actions:
            btn_add, btn_del = st.columns(2)
            with btn_add:
                if st.button(":material/add: Add TOU Tier", key=f"{key_prefix}_add_tier", use_container_width=True):
                    tier_idx = len(active_tiers) + 1
                    tier_colors = ["#EF4444", "#3B82F6", "#F59E0B", "#10B981", "#8B5CF6", "#EC4899", "#06B6D4"]
                    new_color = tier_colors[(tier_idx - 1) % len(tier_colors)]
                    new_tier = TOUTierConfig(
                        id=f"tier_{tier_idx}",
                        name=f"Tier {tier_idx} (Hours)",
                        time_window="Custom Hours",
                        color=new_color
                    )
                    active_tiers.append(new_tier)

                    # Update consumption DataFrame
                    c_col = f"kWh_{new_tier.id}"
                    if c_col not in st.session_state[state_cdf_key].columns:
                        st.session_state[state_cdf_key][c_col] = 5000.0

                    # Update tariff DataFrame
                    t_col = f"rate_{new_tier.id}"
                    if t_col not in st.session_state[state_tdf_key].columns:
                        st.session_state[state_tdf_key][t_col] = 100.0 if selected_cur == "ARS" else 0.1500

                    st.session_state[state_tiers_key] = active_tiers
                    st.rerun()

            with btn_del:
                if len(active_tiers) > 1:
                    if st.button(":material/delete: Remove Tier", key=f"{key_prefix}_del_tier", use_container_width=True):
                        removed = active_tiers.pop()
                        st.session_state[state_cdf_key].drop(columns=[f"kWh_{removed.id}"], inplace=True, errors="ignore")
                        st.session_state[state_tdf_key].drop(columns=[f"rate_{removed.id}"], inplace=True, errors="ignore")
                        st.session_state[state_tiers_key] = active_tiers
                        st.rerun()

        # Renameable tier headers
        tier_cols = st.columns(len(active_tiers))
        for t_idx, tier in enumerate(active_tiers):
            with tier_cols[t_idx]:
                st.markdown(f"<span style='color:{tier.color}; font-weight:bold;'>:material/circle: Tier {t_idx+1}</span>", unsafe_allow_html=True)
                new_name = st.text_input(
                    f"Tier {t_idx+1} Name",
                    value=tier.name,
                    key=f"{key_prefix}_tier_edit_name_{tier.id}_{t_idx}"
                )
                tier.name = new_name

        st.session_state[state_tiers_key] = active_tiers

    st.markdown("---")

    # ==============================================================================
    # Section 3: Table A — 12-Month Consumption & Peak Demand Matrix
    # ==============================================================================
    st.markdown("### :material/table_chart: 2. Consumption Matrix (12 Months)")
    st.caption("Enter monthly energy volumes (kWh) per TOU window, contracted capacity ($P_{vertrag}$), and measured monthly peak ($P_{max}$).")

    cdf_raw = st.session_state[state_cdf_key].copy()

    # Ensure all tier columns exist in consumption DataFrame
    for tier in active_tiers:
        col_id = f"kWh_{tier.id}"
        if col_id not in cdf_raw.columns:
            if tier.id == "peak" and "kWh_peak" in cdf_raw.columns:
                cdf_raw[col_id] = cdf_raw["kWh_peak"]
            elif tier.id == "offpeak" and "kWh_offpeak" in cdf_raw.columns:
                cdf_raw[col_id] = cdf_raw["kWh_offpeak"]
            else:
                cdf_raw[col_id] = 10000.0

    # Column configuration for Table A
    col_cfg_c = {
        "month_index": st.column_config.NumberColumn("Month #", disabled=True, width="small"),
        "Month": st.column_config.TextColumn("Month", disabled=True, width="medium"),
        "P_contract_kW": st.column_config.NumberColumn("P_contract (kW)", min_value=0.0, max_value=50000.0, step=1.0, format="%.0f kW"),
        "P_max_kW": st.column_config.NumberColumn("P_max (kW)", min_value=0.0, max_value=50000.0, step=1.0, format="%.0f kW"),
    }
    for tier in active_tiers:
        col_cfg_c[f"kWh_{tier.id}"] = st.column_config.NumberColumn(
            f"{tier.name} (kWh)",
            min_value=0.0,
            max_value=1e9,
            step=100.0,
            format="%.0f kWh"
        )

    edited_cdf = st.data_editor(
        cdf_raw,
        use_container_width=True,
        num_rows="fixed",
        key=f"{key_prefix}_consumption_editor",
        column_config=col_cfg_c,
        hide_index=True
    )
    st.session_state[state_cdf_key] = edited_cdf

    st.markdown("---")

    # ==============================================================================
    # Section 4: Table B — 12-Month Contract & Tariff Matrix
    # ==============================================================================
    st.markdown(f"### :material/request_quote: 3. Contract & Tariff Matrix (12 Months) — Currency: `{selected_cur}`")
    st.caption(
        "Enter monthly standing fees, capacity rates, limit violation penalties, peak demand charges, "
        "energy unit rates per TOU window, and statutory tax rates."
    )

    tdf_raw = st.session_state[state_tdf_key].copy()

    # Ensure all rate columns exist in tariff DataFrame
    for tier in active_tiers:
        col_id = f"rate_{tier.id}"
        if col_id not in tdf_raw.columns:
            if tier.id == "peak" and "rate_peak" in tdf_raw.columns:
                tdf_raw[col_id] = tdf_raw["rate_peak"]
            elif tier.id == "offpeak" and "rate_offpeak" in tdf_raw.columns:
                tdf_raw[col_id] = tdf_raw["rate_offpeak"]
            else:
                tdf_raw[col_id] = 100.0 if selected_cur == "ARS" else 0.1500

    # Ensure default numeric columns exist
    default_cols = {
        "base_fee": 28929.64 if selected_cur == "ARS" else 125.0,
        "rate_contracted_kw": 3589.886 if selected_cur == "ARS" else 3.85,
        "rate_excess_kw": 3589.886 if selected_cur == "ARS" else 8.50,
        "rate_peak_demand_kw": 0.0 if selected_cur == "ARS" else 1.20,
        "tax_rate_pct": 37.59 if selected_cur == "ARS" else 21.0,
        "exempt_surcharge": 16688.00 if selected_cur == "ARS" else 0.0
    }
    for col_name, def_val in default_cols.items():
        if col_name not in tdf_raw.columns:
            tdf_raw[col_name] = def_val

    # Replicate helper button
    col_t_space, col_t_btn = st.columns([3.5, 1.5])
    with col_t_btn:
        if st.button(":material/content_copy: Copy Month 1 Rates to All 12 Months", key=f"{key_prefix}_copy_m1", use_container_width=True):
            m1_row = tdf_raw.iloc[0]
            for col in tdf_raw.columns:
                if col not in ["month_index", "Month"]:
                    tdf_raw[col] = m1_row[col]
            st.session_state[state_tdf_key] = tdf_raw
            st.rerun()

    # Column configuration for Table B
    col_cfg_t = {
        "month_index": st.column_config.NumberColumn("Month #", disabled=True, width="small"),
        "Month": st.column_config.TextColumn("Month", disabled=True, width="medium"),
        "base_fee": st.column_config.NumberColumn(f"Base Fee ({selected_cur})", min_value=0.0, max_value=1e9, step=100.0 if selected_cur == "ARS" else 5.0, format="%.2f"),
        "rate_contracted_kw": st.column_config.NumberColumn(f"Price/kW Contracted ({selected_cur}/kW)", min_value=0.0, max_value=1e8, step=10.0 if selected_cur == "ARS" else 0.10, format="%.3f"),
        "rate_excess_kw": st.column_config.NumberColumn(f"Price/kW Over Limit ({selected_cur}/kW)", min_value=0.0, max_value=1e8, step=10.0 if selected_cur == "ARS" else 0.50, format="%.3f"),
        "rate_peak_demand_kw": st.column_config.NumberColumn(f"Price/Peak kW Demand ({selected_cur}/kW)", min_value=0.0, max_value=1e8, step=10.0 if selected_cur == "ARS" else 0.10, format="%.3f"),
    }
    for tier in active_tiers:
        col_cfg_t[f"rate_{tier.id}"] = st.column_config.NumberColumn(
            f"Price {tier.name} ({selected_cur}/kWh)",
            min_value=0.0,
            max_value=1e6,
            step=1.0 if selected_cur == "ARS" else 0.005,
            format="%.4f"
        )
    col_cfg_t["tax_rate_pct"] = st.column_config.NumberColumn("Taxes (%)", min_value=0.0, max_value=200.0, step=0.01, format="%.2f%%")
    col_cfg_t["exempt_surcharge"] = st.column_config.NumberColumn(f"Exempt Surcharge ({selected_cur})", min_value=0.0, max_value=1e9, step=100.0 if selected_cur == "ARS" else 5.0, format="%.2f")

    edited_tdf = st.data_editor(
        tdf_raw,
        use_container_width=True,
        num_rows="fixed",
        key=f"{key_prefix}_tariff_editor",
        column_config=col_cfg_t,
        hide_index=True
    )
    st.session_state[state_tdf_key] = edited_tdf

    st.markdown("---")

    # ==============================================================================
    # Section 5: Financial Assessment & Full-Year Billing Statement
    # ==============================================================================
    st.markdown("### :material/analytics: 4. Financial Assessment & Full-Year Statement")

    # Calculate financial bill
    summary = compute_monthly_billing(
        consumption_df=edited_cdf,
        tariff_df=edited_tdf,
        tou_tiers=active_tiers,
        currency=selected_cur,
        fx_rate=input_fx
    )

    # 4 Key Financial Metrics Cards
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    with kpi1:
        st.metric(
            label="Total Annual Electricity Cost",
            value=f"€ {summary.cost_total_annual_eur:,.2f}",
            delta=f"${summary.cost_total_annual_local:,.2f} {selected_cur}" if selected_cur != "EUR" else None
        )
    with kpi2:
        st.metric(
            label="Annual Energy Volume Cost",
            value=f"€ {summary.cost_energy_total_eur:,.2f}",
            delta=f"{summary.total_kwh:,.0f} kWh Total"
        )
    with kpi3:
        demand_info = []
        if summary.cost_measured_demand_annual_eur > 0:
            demand_info.append(f"Demand: € {summary.cost_measured_demand_annual_eur:,.2f}")
        if summary.cost_penalty_annual_eur > 0:
            demand_info.append(f"Penalties: € {summary.cost_penalty_annual_eur:,.2f}")
        delta_str = " | ".join(demand_info) if demand_info else ("No Penalties" if summary.cost_penalty_annual_eur == 0 else None)
        st.metric(
            label="Annual Capacity & Grid Fees",
            value=f"€ {summary.cost_fixed_annual_eur:,.2f}",
            delta=delta_str
        )
    with kpi4:
        st.metric(
            label="Effective Blended Price",
            value=f"€ {summary.blended_rate_annual_eur:.4f} / kWh",
            delta=f"${summary.blended_rate_annual_local:.4f} {selected_cur}/kWh" if selected_cur != "EUR" else None
        )

    # Monthly Stacked Bar Chart (Plotly)
    st.markdown("#### :material/bar_chart: Monthly Cost Composition Breakdown (Stacked)")

    months_list = [r.month_name for r in summary.monthly_results]
    fig = go.Figure()

    # Add bar trace for each TOU tier
    for tier in active_tiers:
        tier_costs = [r.cost_energy_by_tier_eur.get(tier.id, 0.0) for r in summary.monthly_results]
        fig.add_trace(go.Bar(
            x=months_list,
            y=tier_costs,
            name=f"Energy: {tier.name}",
            marker_color=tier.color,
            hovertemplate=f"<b>%{{x}}</b><br>{tier.name}: € %{{y:,.2f}}<extra></extra>"
        ))

    # Add Contracted Capacity Fee
    if summary.cost_contracted_capacity_annual_eur > 0:
        fig.add_trace(go.Bar(
            x=months_list,
            y=[r.cost_contracted_capacity_eur for r in summary.monthly_results],
            name="Contracted Capacity Fee",
            marker_color="#10B981",
            hovertemplate="<b>%{x}</b><br>Contracted Capacity Fee: € %{y:,.2f}<extra></extra>"
        ))

    # Add Base & Exempt Standing Fees
    if (summary.cost_base_fee_annual_eur + summary.cost_exempt_surcharge_annual_eur) > 0:
        fig.add_trace(go.Bar(
            x=months_list,
            y=[r.cost_base_fee_eur + r.cost_exempt_surcharge_eur for r in summary.monthly_results],
            name="Base Fee & Surcharges",
            marker_color="#06B6D4",
            hovertemplate="<b>%{x}</b><br>Base & Standing Fees: € %{y:,.2f}<extra></extra>"
        ))

    # Add Measured Demand Charges if applicable
    if summary.cost_measured_demand_annual_eur > 0:
        fig.add_trace(go.Bar(
            x=months_list,
            y=[r.cost_measured_demand_eur for r in summary.monthly_results],
            name="Measured Peak Demand Fee",
            marker_color="#8B5CF6",
            hovertemplate="<b>%{x}</b><br>Peak Demand Fee: € %{y:,.2f}<extra></extra>"
        ))

    # Add Penalties if applicable
    if summary.cost_penalty_annual_eur > 0:
        fig.add_trace(go.Bar(
            x=months_list,
            y=[r.cost_penalty_eur for r in summary.monthly_results],
            name="Exceedance Penalties",
            marker_color="#DC2626",
            hovertemplate="<b>%{x}</b><br>Exceedance Penalty: € %{y:,.2f}<extra></extra>"
        ))

    fig.update_layout(
        barmode="stack",
        height=390,
        margin=dict(l=20, r=20, t=30, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis=dict(title=None),
        yaxis=dict(title="Monthly Cost (€)", tickprefix="€ "),
        template="plotly_white"
    )

    st.plotly_chart(fig, use_container_width=True)

    # Complete 12-Month Itemized Statement Table
    st.markdown("#### :material/format_list_bulleted: Comprehensive Full-Year Billing Statement")

    table_rows = []
    for r in summary.monthly_results:
        row_dict = {
            "Month": r.month_name,
            "P_contract (kW)": f"{r.contracted_capacity_kw:.0f}",
            "P_max (kW)": f"{r.peak_demand_kw:.0f}",
            "Excess (kW)": f"{r.excess_peak_kw:.0f}" if r.excess_peak_kw > 0 else "—",
            "kWh Total": f"{r.kwh_total:,.0f}",
        }
        for tier in active_tiers:
            row_dict[f"kWh {tier.name}"] = f"{r.kwh_by_tier.get(tier.id, 0.0):,.0f}"

        row_dict["Energy Cost (€)"] = f"€ {r.cost_energy_total_eur:,.2f}"
        row_dict["Contracted Cap Fee (€)"] = f"€ {r.cost_contracted_capacity_eur:,.2f}"
        if summary.cost_measured_demand_annual_eur > 0:
            row_dict["Peak Demand Fee (€)"] = f"€ {r.cost_measured_demand_eur:,.2f}"
        if summary.cost_penalty_annual_eur > 0:
            row_dict["Penalty (€)"] = f"€ {r.cost_penalty_eur:,.2f}"
        if (summary.cost_base_fee_annual_eur + summary.cost_exempt_surcharge_annual_eur) > 0:
            row_dict["Standing Base Fee (€)"] = f"€ {r.cost_base_fee_eur + r.cost_exempt_surcharge_eur:,.2f}"
        row_dict["Total Month (€)"] = f"€ {r.cost_total_eur:,.2f}"
        row_dict["Blended (€/kWh)"] = f"€ {r.blended_rate_eur_per_kwh:.4f}"

        table_rows.append(row_dict)

    # Annual Summary Row
    summary_row = {
        "Month": "JAHRESSUMME (TOTAL)",
        "P_contract (kW)": f"{summary.contracted_kw:.0f}",
        "P_max (kW)": f"{summary.max_peak_kw:.0f}",
        "Excess (kW)": f"{summary.total_excess_peak_kw_months:.0f} kW-mo" if summary.total_excess_peak_kw_months > 0 else "—",
        "kWh Total": f"{summary.total_kwh:,.0f}",
    }
    for tier in active_tiers:
        summary_row[f"kWh {tier.name}"] = f"{summary.total_kwh_by_tier.get(tier.id, 0.0):,.0f}"

    summary_row["Energy Cost (€)"] = f"€ {summary.cost_energy_total_eur:,.2f}"
    summary_row["Contracted Cap Fee (€)"] = f"€ {summary.cost_contracted_capacity_annual_eur:,.2f}"
    if summary.cost_measured_demand_annual_eur > 0:
        summary_row["Peak Demand Fee (€)"] = f"€ {summary.cost_measured_demand_annual_eur:,.2f}"
    if summary.cost_penalty_annual_eur > 0:
        summary_row["Penalty (€)"] = f"€ {summary.cost_penalty_annual_eur:,.2f}"
    if (summary.cost_base_fee_annual_eur + summary.cost_exempt_surcharge_annual_eur) > 0:
        summary_row["Standing Base Fee (€)"] = f"€ {summary.cost_base_fee_annual_eur + summary.cost_exempt_surcharge_annual_eur:,.2f}"
    summary_row["Total Month (€)"] = f"€ {summary.cost_total_annual_eur:,.2f}"
    summary_row["Blended (€/kWh)"] = f"€ {summary.blended_rate_annual_eur:.4f}"

    table_rows.append(summary_row)

    st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)

    # Dynamic Calculation & Arithmetic Audit Panel
    with st.expander(":material/calculate: Detailed Mathematical Audit & Intermediate Calculations", expanded=True):
        st.caption("Inspect the exact numerical arithmetic for each monthly bill and full-year totals with all applied rates, taxes, and volumes.")

        tab_month_audit, tab_annual_audit = st.tabs([":material/calendar_today: Monthly Bill Audit", ":material/functions: Full-Year Grand Totals"])

        with tab_month_audit:
            month_names = [r.month_name for r in summary.monthly_results]
            sel_m_idx = st.selectbox(
                "Select Month to Audit",
                options=list(range(len(month_names))),
                format_func=lambda x: f"Month {x+1}: {month_names[x]}",
                key=f"{key_prefix}_audit_month_select"
            )
            res_m = summary.monthly_results[sel_m_idx]
            t_row_m = edited_tdf.iloc[sel_m_idx] if sel_m_idx < len(edited_tdf) else edited_tdf.iloc[-1]
            tax_pct_m = float(t_row_m.get("tax_rate_pct", 22.0))
            tax_mult_m = 1.0 + (tax_pct_m / 100.0)

            c_audit1, c_audit2 = st.columns(2)
            with c_audit1:
                st.markdown(f"#### :material/power: Capacity, Demand & Fixed Charges ({res_m.month_name})")

                # Contracted capacity calculation
                rate_cap_m = float(t_row_m.get("rate_contracted_kw", 0.0))
                net_cap_val = res_m.contracted_capacity_kw * rate_cap_m
                st.markdown(
                    f"**1. Contracted Capacity Fee ($P_{{contract}}$):**  \n"
                    f"`{res_m.contracted_capacity_kw:,.0f} kW` × `{rate_cap_m:,.3f} {selected_cur}/kW` = `{net_cap_val:,.2f} {selected_cur}` net  \n"
                    f"→ Gross (inkl. {tax_pct_m:.1f}% Tax): **€ {res_m.cost_contracted_capacity_eur:,.2f}**"
                )

                # Measured peak demand calculation
                rate_dem_m = float(t_row_m.get("rate_peak_demand_kw", 0.0))
                net_dem_val = res_m.peak_demand_kw * rate_dem_m
                st.markdown(
                    f"**2. Measured Peak Demand Fee ($P_{{max}}$):**  \n"
                    f"`{res_m.peak_demand_kw:,.0f} kW` × `{rate_dem_m:,.3f} {selected_cur}/kW` = `{net_dem_val:,.2f} {selected_cur}` net  \n"
                    f"→ Gross (inkl. {tax_pct_m:.1f}% Tax): **€ {res_m.cost_measured_demand_eur:,.2f}**"
                )

                # Limit exceedance penalty calculation
                rate_pen_m = float(t_row_m.get("rate_excess_kw", 0.0))
                if res_m.excess_peak_kw > 0:
                    net_pen_val = res_m.excess_peak_kw * rate_pen_m
                    st.markdown(
                        f"**3. Capacity Exceedance Penalty:**  \n"
                        f"`({res_m.peak_demand_kw:,.0f} - {res_m.contracted_capacity_kw:,.0f}) = {res_m.excess_peak_kw:,.0f} kW Overrun` × `{rate_pen_m:,.3f} {selected_cur}/kW` = `{net_pen_val:,.2f} {selected_cur}` net  \n"
                        f"→ Gross (inkl. {tax_pct_m:.1f}% Tax): **€ {res_m.cost_penalty_eur:,.2f}**"
                    )
                else:
                    st.markdown(f"**3. Capacity Exceedance Penalty:**  \n`0 kW Overrun` (Within limit) → **€ 0.00**")

                # Base Standing fee calculation
                base_val = float(t_row_m.get("base_fee", 0.0))
                st.markdown(
                    f"**4. Standing Base Fee:**  \n"
                    f"`{base_val:,.2f} {selected_cur}` net × (1 + {tax_pct_m:.1f}% Tax) → **€ {res_m.cost_base_fee_eur + res_m.cost_exempt_surcharge_eur:,.2f}**"
                )

            with c_audit2:
                st.markdown(f"#### :material/bolt: TOU Energy Volume Charges ({res_m.month_name})")

                tot_e_gross = 0.0
                for tier in active_tiers:
                    kwh_t = res_m.kwh_by_tier.get(tier.id, 0.0)
                    rate_t = float(t_row_m.get(f"rate_{tier.id}", 0.0))
                    cost_t_eur = res_m.cost_energy_by_tier_eur.get(tier.id, 0.0)
                    tot_e_gross += cost_t_eur
                    st.markdown(
                        f"**• {tier.name}:**  \n"
                        f"`{kwh_t:,.0f} kWh` × `{rate_t:,.4f} {selected_cur}/kWh` × (1 + {tax_pct_m:.1f}% Tax) = **€ {cost_t_eur:,.2f}**"
                    )

                st.markdown(f"**Total Energy Volume Cost ({res_m.month_name}):** `€ {tot_e_gross:,.2f}` (`{res_m.kwh_total:,.0f} kWh`)")

                st.markdown("---")
                st.markdown(
                    f"### :material/receipt_long: **Month Total ({res_m.month_name}):**  \n"
                    f"`€ {res_m.cost_energy_total_eur:,.2f} (Energy)` + `€ {res_m.cost_contracted_capacity_eur:,.2f} (Capacity)` + "
                    f"`€ {res_m.cost_measured_demand_eur:,.2f} (Demand)` + `€ {res_m.cost_penalty_eur:,.2f} (Penalty)` + "
                    f"`€ {res_m.cost_base_fee_eur + res_m.cost_exempt_surcharge_eur:,.2f} (Base Fee)`  \n"
                    f"= **€ {res_m.cost_total_eur:,.2f}** *(Effective Blended: `€ {res_m.blended_rate_eur_per_kwh:.4f} / kWh`)*"
                )

        with tab_annual_audit:
            st.markdown("#### :material/summarize: Full-Year Grand Aggregations (12 Months)")
            a_col1, a_col2 = st.columns(2)
            with a_col1:
                st.markdown(
                    f"1. **Annual Energy Total:** `{summary.total_kwh:,.0f} kWh`  \n"
                    f"   → Grand Energy Cost: **€ {summary.cost_energy_total_eur:,.2f}**"
                )
                st.markdown(
                    f"2. **Annual Contracted Capacity Fees:**  \n"
                    f"   → Sum across 12 months: **€ {summary.cost_contracted_capacity_annual_eur:,.2f}**"
                )
                st.markdown(
                    f"3. **Annual Measured Peak Demand Fees:**  \n"
                    f"   → Sum across 12 months: **€ {summary.cost_measured_demand_annual_eur:,.2f}**"
                )
            with a_col2:
                st.markdown(
                    f"4. **Annual Exceedance Penalties:**  \n"
                    f"   → Total Overrun ({summary.months_with_excess_peak} months): **€ {summary.cost_penalty_annual_eur:,.2f}**"
                )
                st.markdown(
                    f"5. **Annual Standing & Base Fees:**  \n"
                    f"   → Total Base Charges: **€ {summary.cost_base_fee_annual_eur + summary.cost_exempt_surcharge_annual_eur:,.2f}**"
                )
                st.markdown(
                    f"### :material/account_balance_wallet: **Grand Total Annual Electricity Cost:**  \n"
                    f"= **€ {summary.cost_total_annual_eur:,.2f}**  \n"
                    f"*(Annual Blended Average: `€ {summary.blended_rate_annual_eur:.4f} / kWh`)*"
                )

    # Baseline Export
    col_exp1, col_exp2 = st.columns(2)
    with col_exp1:
        export_df = pd.DataFrame([asdict(r) for r in summary.monthly_results])
        csv_data = export_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label=":material/file_download: Export Monthly Baseline (CSV)",
            data=csv_data,
            file_name="monthly_baseline_summary.csv",
            mime="text/csv",
            use_container_width=True
        )
    with col_exp2:
        export_payload = {
            "preset_name": preset_name,
            "currency": selected_cur,
            "fx_rate": input_fx,
            "annual_summary": {
                "total_annual_cost_eur": summary.cost_total_annual_eur,
                "total_annual_cost_local": summary.cost_total_annual_local,
                "total_kwh": summary.total_kwh,
                "blended_price_eur": summary.blended_rate_annual_eur,
                "contracted_kw": summary.contracted_kw,
                "max_peak_kw": summary.max_peak_kw,
                "exceedances_count": summary.months_with_excess_peak
            },
            "tou_tiers": [t.to_dict() for t in active_tiers],
            "consumption_matrix": edited_cdf.to_dict(orient="records"),
            "tariff_matrix": edited_tdf.to_dict(orient="records"),
            "monthly_billing_breakdown": [asdict(r) for r in summary.monthly_results]
        }
        json_str = json.dumps(export_payload, indent=2)
        st.download_button(
            label=":material/data_object: Export Complete Baseline Model (JSON)",
            data=json_str.encode("utf-8"),
            file_name="monthly_baseline_config.json",
            mime="application/json",
            use_container_width=True
        )


# ========================================================================================
# 4. Standalone Runner
# ========================================================================================

def main():
    st.set_page_config(
        page_title="Monthly Baseline & Commercial Tariff Lab",
        page_icon=":material/calendar_month:",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    if apply_custom_styles:
        apply_custom_styles()

    render_monthly_baseline_lab(key_prefix="standalone_lab")


if __name__ == "__main__":
    main()
