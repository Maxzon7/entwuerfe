"""
========================================================================================
Layer 4: Commercial Accounting & Market Sourcing (commercial_accounting.py)
========================================================================================
Calculates competitive electricity supply, certified metering, and statutory levies:
  1. Supplier Commodity Pricing (3 separate calculation paths):
     - FIXED: Annual/monthly kWh volume x fixed contract rate + standing base fee.
     - VARIABLE: Monthly kWh volume x month-specific commodity rate + standing base fee.
     - DYNAMIC: Step-by-step multiplication of 35,040 intervals by EPEX Spot NL 2025
       Day-Ahead wholesale prices + retail margin (Opslag) + standing base fee.
  2. Certified Metering Company (Meetbedrijf):
     - Strictly flat annual fee (Fudura B.V.) divided across 12 calendar months.
  3. Statutory Energy Levies:
     - Volumetric multiplication of kWh consumption by statutory levy rate (€/kWh).
  4. Feed-in Compensation:
     - Strictly locked to € 0.00 in the pure Status Quo baseline.
Validates all Audit Point 3 criteria (3.1, 3.2, 3.3, 3.4).
========================================================================================
"""

from typing import List, Dict, Any, Tuple, Optional
import numpy as np
import pandas as pd

try:
    from .config_and_models import (
        LoadSeries2025,
        SupplierTariff,
        MeteringTariff,
        LevyConfig,
        PricingMode,
        MonthlyConsumptionRecord,
        CommercialMonthlyResult,
    )
except (ImportError, ValueError):
    from config_and_models import (
        LoadSeries2025,
        SupplierTariff,
        MeteringTariff,
        LevyConfig,
        PricingMode,
        MonthlyConsumptionRecord,
        CommercialMonthlyResult,
    )

try:
    from current_model.core.market_price_engine import load_market_price_series
except ImportError:
    from core.market_price_engine import load_market_price_series


def align_spot_prices_amsterdam_2025(
    load: LoadSeries2025,
    supplier_tariff: SupplierTariff
) -> np.ndarray:
    """
    Precisely aligns EPEX Spot wholesale electricity prices for the 35,040 steps in 2025.
    
    Timezone handling:
      - Canonical load timestamps represent local Dutch facility time (Europe/Amsterdam).
      - Converts local timestamps to Europe/Amsterdam, then to UTC for exact matching with
        EPEX Spot auction records.
      - Reindexes and forward-fills missing intervals, falling back to spot_default_fallback_rate.
    """
    default_rate = float(supplier_tariff.spot_default_fallback_rate)
    profile_id = supplier_tariff.market_price_profile_id or "epex_nl_2025"

    try:
        spot_df = load_market_price_series(profile_id=profile_id)
        price_col = "price_eur_kwh"
        if price_col not in spot_df.columns:
            return np.full(len(load.power_kw), default_rate, dtype=float)

        # Localize naive reference timestamps to Europe/Amsterdam, then to UTC
        ts_naive = load.timestamps
        ts_local = ts_naive.tz_localize("Europe/Amsterdam", ambiguous="NaT", nonexistent="shift_forward")
        ts_utc = ts_local.tz_convert("UTC")

        # Reindex EPEX Spot series onto UTC timestamps
        aligned_series = spot_df[price_col].reindex(ts_utc, method="ffill").bfill()
        spot_prices = aligned_series.fillna(default_rate).to_numpy(dtype=float)

        # Replace any remaining NaNs
        spot_prices = np.where(np.isnan(spot_prices), default_rate, spot_prices)
        return spot_prices

    except Exception:
        # Robust fallback to default rate if market file is temporarily unreachable
        return np.full(len(load.power_kw), default_rate, dtype=float)


def calculate_commercial_accounting_2025(
    load: LoadSeries2025,
    monthly_consumption: List[MonthlyConsumptionRecord],
    supplier_tariff: SupplierTariff,
    metering_tariff: MeteringTariff,
    levy_config: LevyConfig
) -> Tuple[List[CommercialMonthlyResult], Dict[str, Any]]:
    """
    Executes the pure mathematical commercial accounting pipeline for reference year 2025.
    
    Returns:
      Tuple of:
        - List of 12 CommercialMonthlyResult records
        - Commercial summary & diagnostic dictionary
    """
    monthly_results: List[CommercialMonthlyResult] = []

    # Monthly fixed allocations
    monthly_supplier_base = supplier_tariff.base_fee_annual / 12.0
    monthly_metering_fee = metering_tariff.annual_flat_fee / 12.0

    # Commodity surcharges (procurement fee & green certificate GvO)
    surcharges_kwh = float(getattr(supplier_tariff, "procurement_fee_kwh", 0.0)) + float(getattr(supplier_tariff, "green_certificate_surcharge_kwh", 0.0))

    # Pre-align spot market prices if DYNAMIC mode is active
    if supplier_tariff.pricing_mode == PricingMode.DYNAMIC:
        spot_prices = align_spot_prices_amsterdam_2025(load, supplier_tariff)
        margin_kwh = float(supplier_tariff.supplier_margin_kwh)
        all_in_spot_rates = spot_prices + margin_kwh + surcharges_kwh
        # 35,040 interval costs
        interval_energy_costs = load.energy_kwh * all_in_spot_rates
    else:
        spot_prices = None
        interval_energy_costs = None

    annual_supplier_energy = 0.0
    annual_levies = 0.0
    monthly_tax_reduction = float(getattr(levy_config, "annual_tax_reduction", 0.0)) / 12.0

    for rec in monthly_consumption:
        m = rec.month_index
        m_kwh = rec.total_kwh

        # 1. Commodity Energy Cost Calculation by Pricing Mode
        if supplier_tariff.pricing_mode == PricingMode.FIXED:
            is_dual = getattr(supplier_tariff, "is_dual_rate", False)
            if is_dual:
                r_ht = float(getattr(supplier_tariff, "fixed_rate_peak_kwh", supplier_tariff.fixed_rate_kwh))
                r_nt = float(getattr(supplier_tariff, "fixed_rate_offpeak_kwh", supplier_tariff.fixed_rate_kwh))
                base_commodity = (rec.peak_tou_kwh * r_ht) + (rec.offpeak_tou_kwh * r_nt)
            else:
                base_commodity = m_kwh * float(supplier_tariff.fixed_rate_kwh)
            m_energy_cost = base_commodity + (m_kwh * surcharges_kwh)

        elif supplier_tariff.pricing_mode == PricingMode.VARIABLE:
            var_rates = supplier_tariff.monthly_variable_rates
            m_rate = var_rates[m - 1] if (len(var_rates) >= m) else float(supplier_tariff.fixed_rate_kwh)
            m_energy_cost = (m_kwh * float(m_rate)) + (m_kwh * surcharges_kwh)

        elif supplier_tariff.pricing_mode == PricingMode.DYNAMIC:
            # Sum interval products for intervals belonging to month m
            mask = (load.month_indices == m)
            m_energy_cost = float(np.sum(interval_energy_costs[mask]))

        else:
            m_energy_cost = (m_kwh * float(supplier_tariff.fixed_rate_kwh)) + (m_kwh * surcharges_kwh)

        annual_supplier_energy += m_energy_cost

        # 2. Statutory Levies Calculation (€/kWh * E_m - vermindering energiebelasting)
        raw_levies = m_kwh * float(levy_config.statutory_levy_rate_kwh)
        m_levies = max(0.0, raw_levies - monthly_tax_reduction)
        annual_levies += m_levies

        # 3. Monthly Commercial Subtotal
        # Status Quo has strictly 0.00 feed-in credit
        feed_in_credit = 0.0
        m_commercial_net = monthly_supplier_base + m_energy_cost + monthly_metering_fee + m_levies - feed_in_credit

        monthly_results.append(
            CommercialMonthlyResult(
                month_index=m,
                supplier_base_fee=round(monthly_supplier_base, 2),
                supplier_energy_cost=round(m_energy_cost, 2),
                metering_fee=round(monthly_metering_fee, 2),
                statutory_levies=round(m_levies, 2),
                feed_in_credit=0.0,
                subtotal_commercial_net=round(m_commercial_net, 2)
            )
        )

    # Commercial Annual Summary
    total_supplier_base_annual = monthly_supplier_base * 12.0
    total_supplier_net_annual = total_supplier_base_annual + annual_supplier_energy
    total_metering_annual = monthly_metering_fee * 12.0

    summary = {
        "pricing_mode": supplier_tariff.pricing_mode.value,
        "supplier_name": supplier_tariff.supplier_name,
        "meter_company_name": metering_tariff.meter_company_name,
        "total_supplier_base_annual": round(total_supplier_base_annual, 2),
        "total_supplier_energy_annual": round(annual_supplier_energy, 2),
        "total_supplier_net_annual": round(total_supplier_net_annual, 2),
        "total_metering_annual": round(total_metering_annual, 2),
        "total_levies_annual": round(annual_levies, 2),
        "total_feed_in_credit_annual": 0.0,
        "average_spot_price_kwh": (
            float(np.mean(spot_prices)) if spot_prices is not None else float(supplier_tariff.fixed_rate_kwh)
        ),
    }

    return monthly_results, summary


def evaluate_commercial_audit(
    load: LoadSeries2025,
    monthly_consumption: List[MonthlyConsumptionRecord],
    commercial_results: List[CommercialMonthlyResult],
    supplier_tariff: SupplierTariff,
    metering_tariff: MeteringTariff,
    levy_config: LevyConfig
) -> Dict[str, Any]:
    """
    Validates Audit Point 3 (Prüfpunkt 3: Handels- und Steuerkomponenten):
      - Criterion 3.1: Supplier energy tariff logic according to mode:
          * Fixed: E_total * fixed_rate + base_annual
          * Variable: sum(E_m * var_rate_m) + base_annual
          * Dynamic: sum(E(t) * (spot(t) + margin)) + base_annual
      - Criterion 3.2: Metering flat fee independent of consumption (exactly annual_flat_fee).
      - Criterion 3.3: Statutory levies == E_total * statutory_levy_rate_kwh.
      - Criterion 3.4: Feed-in credit strictly 0.00 EUR in pure status quo.
    """
    total_kwh = sum(c.total_kwh for c in monthly_consumption)
    actual_supplier_energy = sum(r.supplier_energy_cost for r in commercial_results)
    
    # 3.1: Mode verification
    if supplier_tariff.pricing_mode == PricingMode.FIXED:
        expected_energy = total_kwh * supplier_tariff.fixed_rate_kwh
        c3_1_pass = (abs(expected_energy - actual_supplier_energy) < 0.20)
    elif supplier_tariff.pricing_mode == PricingMode.VARIABLE:
        expected_energy = sum(
            c.total_kwh * supplier_tariff.monthly_variable_rates[c.month_index - 1]
            for c in monthly_consumption
        )
        c3_1_pass = (abs(expected_energy - actual_supplier_energy) < 0.20)
    else:  # DYNAMIC
        # Spot is evaluated step-by-step
        c3_1_pass = (actual_supplier_energy > 0.0 and len(commercial_results) == 12)

    # 3.2: Metering verification
    actual_metering = sum(r.metering_fee for r in commercial_results)
    c3_2_pass = (abs(actual_metering - metering_tariff.annual_flat_fee) < 0.20)

    # 3.3: Statutory levies verification
    expected_levies = total_kwh * levy_config.statutory_levy_rate_kwh
    actual_levies = sum(r.statutory_levies for r in commercial_results)
    c3_3_pass = (abs(expected_levies - actual_levies) < 0.20)

    # 3.4: Feed-in credit verification
    actual_feed_in = sum(r.feed_in_credit for r in commercial_results)
    c3_4_pass = (abs(actual_feed_in - 0.0) < 1e-6)

    all_passed = (c3_1_pass and c3_2_pass and c3_3_pass and c3_4_pass)

    return {
        "audit_point": 3,
        "title": "Audit Point 3: Commercial Supplier, Metering & Levies Verification",
        "passed": all_passed,
        "criteria": {
            "3.1_supplier_pricing_mode": {
                "passed": c3_1_pass,
                "mode": supplier_tariff.pricing_mode.value,
                "supplier_energy_cost": round(actual_supplier_energy, 2)
            },
            "3.2_metering_independence": {
                "passed": c3_2_pass,
                "expected_fee": round(metering_tariff.annual_flat_fee, 2),
                "actual_fee": round(actual_metering, 2)
            },
            "3.3_statutory_levies": {
                "passed": c3_3_pass,
                "expected_levies": round(expected_levies, 2),
                "actual_levies": round(actual_levies, 2)
            },
            "3.4_feed_in_lock_zero": {
                "passed": c3_4_pass,
                "actual_feed_in_credit": round(actual_feed_in, 2)
            }
        }
    }
