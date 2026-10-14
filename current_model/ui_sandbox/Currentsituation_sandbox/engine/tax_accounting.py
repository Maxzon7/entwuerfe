"""
========================================================================================
Layer 4: Statutory Taxation & Degressive Energy Tax (engine/tax_accounting.py)
Current Situation (Status Quo) Sandbox Engine
========================================================================================
Calculates the official Dutch Energiebelasting across cumulative annual volume brackets:
  - 5 statutory zones:
      Zone 1 & 2: 0 to 10,000 kWh
      Zone 3: 10,001 to 50,000 kWh
      Zone 4: 50,001 to 10,000,000 kWh
      Zone 5: > 10,000,000 kWh
  - Supports 2025 and 2026 rates
  - Applies monthly proportional Vermindering energiebelasting (tax reduction) for Verblijfsfunctie
========================================================================================
"""

from typing import List, Dict, Any, Tuple
import numpy as np

try:
    from .config_and_models import (
        LevyConfig,
        TaxBracket,
        MonthlyConsumptionRecord,
        TaxMonthlyResult,
    )
except (ImportError, ValueError):
    from config_and_models import (
        LevyConfig,
        TaxBracket,
        MonthlyConsumptionRecord,
        TaxMonthlyResult,
    )


# Official statutory rate schedules
TAX_SCHEDULE_2025: List[TaxBracket] = [
    TaxBracket(zone_name="Zone 1 & 2 (0 bis 10.000 kWh)", lower_kwh=0.0, upper_kwh=10000.0, rate_kwh=0.10154),
    TaxBracket(zone_name="Zone 3 (10.001 bis 50.000 kWh)", lower_kwh=10000.0, upper_kwh=50000.0, rate_kwh=0.06937),
    TaxBracket(zone_name="Zone 4 (50.001 bis 10.000.000 kWh)", lower_kwh=50000.0, upper_kwh=10000000.0, rate_kwh=0.03868),
    TaxBracket(zone_name="Zone 5 (> 10.000.000 kWh)", lower_kwh=10000000.0, upper_kwh=float("inf"), rate_kwh=0.00321),
]

TAX_SCHEDULE_2026: List[TaxBracket] = [
    TaxBracket(zone_name="Zone 1 & 2 (0 bis 10.000 kWh)", lower_kwh=0.0, upper_kwh=10000.0, rate_kwh=0.09161),
    TaxBracket(zone_name="Zone 3 (10.001 bis 50.000 kWh)", lower_kwh=10000.0, upper_kwh=50000.0, rate_kwh=0.06671),
    TaxBracket(zone_name="Zone 4 (50.001 bis 10.000.000 kWh)", lower_kwh=50000.0, upper_kwh=10000000.0, rate_kwh=0.03735),
    TaxBracket(zone_name="Zone 5 (> 10.000.000 kWh)", lower_kwh=10000000.0, upper_kwh=float("inf"), rate_kwh=0.00310),
]

VERMINDERING_2025: float = 524.95
VERMINDERING_2026: float = 519.80


def compute_bracket_tax(start_kwh: float, end_kwh: float, brackets: List[TaxBracket]) -> float:
    """
    Computes statutory energy tax for volume consumed between start_kwh and end_kwh.
    """
    if end_kwh <= start_kwh:
        return 0.0

    total_tax = 0.0
    for b in brackets:
        overlap_start = max(start_kwh, b.lower_kwh)
        overlap_end = min(end_kwh, b.upper_kwh)
        if overlap_end > overlap_start:
            overlap_volume = overlap_end - overlap_start
            total_tax += overlap_volume * b.rate_kwh
    return total_tax


def calculate_tax_accounting(
    monthly_consumption: List[MonthlyConsumptionRecord],
    levy_config: LevyConfig
) -> Tuple[List[TaxMonthlyResult], Dict[str, Any]]:
    """
    Calculates 12 monthly tax records tracking cumulative annual volume.
    """
    monthly_results: List[TaxMonthlyResult] = []

    # Select schedule based on tax year
    brackets = levy_config.tax_brackets
    if not brackets or len(brackets) == 0:
        brackets = TAX_SCHEDULE_2026 if levy_config.tax_year == 2026 else TAX_SCHEDULE_2025

    # Annual tax reduction
    annual_reduction = levy_config.annual_tax_reduction if levy_config.has_verblijfsfunctie else 0.0
    monthly_reduction = annual_reduction / 12.0

    cumulative_kwh = 0.0
    annual_gross_tax = 0.0
    annual_net_tax = 0.0

    for rec in monthly_consumption:
        m = rec.month_index
        m_kwh = float(rec.total_kwh)

        m_start = cumulative_kwh
        m_end = cumulative_kwh + m_kwh
        cumulative_kwh = m_end

        if levy_config.use_tiered_energy_tax:
            m_gross_tax = compute_bracket_tax(m_start, m_end, brackets)
        else:
            # Fallback legacy flat rate
            m_gross_tax = m_kwh * levy_config.statutory_levy_rate_kwh

        m_net_tax = max(0.0, m_gross_tax - monthly_reduction)

        annual_gross_tax += m_gross_tax
        annual_net_tax += m_net_tax

        monthly_results.append(
            TaxMonthlyResult(
                month_index=m,
                cumulative_kwh_start=round(m_start, 2),
                cumulative_kwh_end=round(m_end, 2),
                gross_energy_tax=round(m_gross_tax, 2),
                tax_reduction_credit=round(monthly_reduction, 2),
                net_energy_tax=round(m_net_tax, 2)
            )
        )

    summary = {
        "tax_year": levy_config.tax_year,
        "use_tiered_energy_tax": levy_config.use_tiered_energy_tax,
        "has_verblijfsfunctie": levy_config.has_verblijfsfunctie,
        "annual_tax_reduction": round(annual_reduction, 2),
        "total_gross_tax_annual": round(annual_gross_tax, 2),
        "total_net_tax_annual": round(annual_net_tax, 2),
        "vat_rate_pct": levy_config.vat_rate_pct,
    }

    return monthly_results, summary
