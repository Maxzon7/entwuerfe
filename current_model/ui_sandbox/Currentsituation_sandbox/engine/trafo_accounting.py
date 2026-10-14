"""
========================================================================================
Layer 6: Transformer & MV Infrastructure Accounting (engine/trafo_accounting.py)
Current Situation (Status Quo) Sandbox Engine
========================================================================================
Calculates transformer station rental, maintenance, and NEN 3840 compliance costs
for facilities on Medium Voltage (AC5a, AC5b, AC5, AC6):
  - Station rental (e.g. 630 kVA Kompaktstation @ €354/month = €4,248/year)
  - Full-service contracting (Installatieverantwoordelijke IV, 24/7 service)
  - Customer-owned option (CAPEX purchase @ €0/month rental)
========================================================================================
"""

from typing import List, Dict, Any, Tuple
try:
    from .config_and_models import TrafoRentalTariff, TrafoRentalMonthlyResult
except (ImportError, ValueError):
    from config_and_models import TrafoRentalTariff, TrafoRentalMonthlyResult


def calculate_trafo_rental_accounting(
    trafo_tariff: TrafoRentalTariff
) -> Tuple[List[TrafoRentalMonthlyResult], Dict[str, Any]]:
    """Calculates 12 monthly transformer rental fee records."""
    monthly_fee = float(trafo_tariff.monthly_rental_fee) if trafo_tariff.is_rented else 0.0
    monthly_results = [
        TrafoRentalMonthlyResult(
            month_index=m,
            trafo_rental_fee=round(monthly_fee, 2),
            is_rented=trafo_tariff.is_rented
        )
        for m in range(1, 13)
    ]

    annual_total = monthly_fee * 12.0
    summary = {
        "provider_name": trafo_tariff.provider_name,
        "station_type": trafo_tariff.station_type,
        "is_rented": trafo_tariff.is_rented,
        "monthly_rental_fee": round(monthly_fee, 2),
        "annual_rental_fee": round(annual_total, 2),
        "capex_equivalent": trafo_tariff.capex_equivalent,
        "includes_nen3840": trafo_tariff.includes_nen3840,
    }
    return monthly_results, summary
