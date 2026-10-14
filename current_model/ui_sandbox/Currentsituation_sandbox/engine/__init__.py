"""
========================================================================================
Current Situation (Status Quo) Sandbox Engine
engine/__init__.py
========================================================================================
Public package API exporting all core models, accounting functions, catalogs,
and advisory tools for Dutch Grootverbruik electricity procurement.
========================================================================================
"""

from .config_and_models import (
    TariffStage,
    PricingMode,
    SupplierCategory,
    TrancheBlock,
    TaxBracket,
    LoadSeries2025,
    DSOTariff,
    SupplierTariff,
    TrafoRentalTariff,
    MeteringTariff,
    LevyConfig,
    StatusQuoConfig2025,
    MonthlyConsumptionRecord,
    DSOMonthlyResult,
    CommercialMonthlyResult,
    TrafoRentalMonthlyResult,
    TaxMonthlyResult,
    StatusQuoMonthlyResult,
    StatusQuoAnnualResult,
)

from .consumption_pipeline import (
    normalize_load_profile_2025,
    synthesize_benchmark_load_profile_2025,
    synthesize_profile_a_360mwh,
    synthesize_profile_b_1200mwh,
    extract_monthly_consumption_records,
)

from .dso_accounting import calculate_dso_accounting_2025
from .commercial_accounting import calculate_commercial_accounting
from .trafo_accounting import calculate_trafo_rental_accounting
from .tax_accounting import calculate_tax_accounting
from .status_quo_master import (
    calculate_status_quo_master,
    convert_to_financial_cost_breakdown,
)
from .procurement_engine import (
    compare_procurement_routes,
    evaluate_voltage_transition_advisor,
    evaluate_bess_flexibility_upside,
)
from .audit import perform_full_status_quo_audit

from .tariff_defaults_2025 import (
    LIANDER_2025_GRID_TIERS,
    ENEXIS_2025_GRID_TIERS,
    STEDIN_2025_GRID_TIERS,
    DSO_CATALOGS_2025,
    SUPPLIER_CATALOG_2025,
    TRAFO_RENTAL_CATALOG_2025,
    METERING_CATALOG_2025,
    get_dso_tariff_from_catalog,
    get_supplier_tariff_from_catalog,
    get_trafo_tariff_from_catalog,
    get_metering_tariff_from_catalog,
    get_default_levy_config,
)

TRAFO_CATALOG_2025 = TRAFO_RENTAL_CATALOG_2025

__all__ = [
    "TariffStage",
    "PricingMode",
    "SupplierCategory",
    "TrancheBlock",
    "TaxBracket",
    "LoadSeries2025",
    "DSOTariff",
    "SupplierTariff",
    "TrafoRentalTariff",
    "MeteringTariff",
    "LevyConfig",
    "StatusQuoConfig2025",
    "MonthlyConsumptionRecord",
    "DSOMonthlyResult",
    "CommercialMonthlyResult",
    "TrafoRentalMonthlyResult",
    "TaxMonthlyResult",
    "StatusQuoMonthlyResult",
    "StatusQuoAnnualResult",
    "normalize_load_profile_2025",
    "synthesize_benchmark_load_profile_2025",
    "synthesize_profile_a_360mwh",
    "synthesize_profile_b_1200mwh",
    "extract_monthly_consumption_records",
    "calculate_dso_accounting_2025",
    "calculate_commercial_accounting",
    "calculate_trafo_rental_accounting",
    "calculate_tax_accounting",
    "calculate_status_quo_master",
    "convert_to_financial_cost_breakdown",
    "compare_procurement_routes",
    "evaluate_voltage_transition_advisor",
    "evaluate_bess_flexibility_upside",
    "perform_full_status_quo_audit",
    "LIANDER_2025_GRID_TIERS",
    "ENEXIS_2025_GRID_TIERS",
    "STEDIN_2025_GRID_TIERS",
    "DSO_CATALOGS_2025",
    "SUPPLIER_CATALOG_2025",
    "TRAFO_RENTAL_CATALOG_2025",
    "METERING_CATALOG_2025",
    "get_dso_tariff_from_catalog",
    "get_supplier_tariff_from_catalog",
    "get_trafo_tariff_from_catalog",
    "get_metering_tariff_from_catalog",
    "get_default_levy_config",
]
