"""
========================================================================================
Monthly Baseline & Commercial Electricity Tariff Lab Package
(current_model/ui_sandbox/monthly_baseline_lab/__init__.py)
========================================================================================
Exposes the modular 12-month baseline and commercial electricity tariff laboratory.
"""

from .monthly_presets import (
    MONTHS_LIST,
    TOUTierConfig,
    ENEXIS_2025_GRID_TIERS,
    ENEXIS_2025_CONNECTION_CAPACITIES,
    build_enexis_2025_tariff_dataframe,
    LIANDER_2025_GRID_TIERS,
    LIANDER_2025_CONNECTION_CAPACITIES,
    build_liander_2025_tariff_dataframe,
    get_salentein_pozo600_preset,
    get_3tier_argentine_preset,
    get_netherlands_commercial_preset,
    reload_preset_data,
    get_preset_three_party_entities,
)

from .monthly_calc import (
    MonthlyBillingResult,
    AnnualBillingSummary,
    compute_monthly_billing,
)

from .standalone_monthly_baseline_lab import render_monthly_baseline_lab

__all__ = [
    "MONTHS_LIST",
    "TOUTierConfig",
    "ENEXIS_2025_GRID_TIERS",
    "ENEXIS_2025_CONNECTION_CAPACITIES",
    "build_enexis_2025_tariff_dataframe",
    "LIANDER_2025_GRID_TIERS",
    "LIANDER_2025_CONNECTION_CAPACITIES",
    "build_liander_2025_tariff_dataframe",
    "get_salentein_pozo600_preset",
    "get_3tier_argentine_preset",
    "get_netherlands_commercial_preset",
    "reload_preset_data",
    "get_preset_three_party_entities",
    "MonthlyBillingResult",
    "AnnualBillingSummary",
    "compute_monthly_billing",
    "render_monthly_baseline_lab",
]
