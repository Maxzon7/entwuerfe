"""
========================================================================================
Status Quo 2025 Accounting & Verification Package (ui_sandbox/status_quo_2025)
========================================================================================
Implements an unbundled, 5-layer European commercial electricity billing pipeline
for the reference year 2025 (35,040 steps @ 15-min):
  1. config_and_models: Strict data models without calculation logic
  2. consumption_pipeline: Normalization to 35,040 steps & calendar/TOU segmentation
  3. dso_accounting: Dutch DSO tariff calculation & capacity breach detection
  4. commercial_accounting: Energy supplier (Fixed/Var/Spot), metering, and levies
  5. status_quo_master: Consolidation, blended kWh price, VAT, and 15-year TCO NPV
========================================================================================
"""

from .config_and_models import (
    TariffStage,
    PricingMode,
    LoadSeries2025,
    DSOTariff,
    SupplierTariff,
    MeteringTariff,
    LevyConfig,
    StatusQuoConfig2025,
    MonthlyConsumptionRecord,
    DSOMonthlyResult,
    CommercialMonthlyResult,
    StatusQuoMonthlyResult,
    StatusQuoAnnualResult,
)
from .tariff_defaults_2025 import (
    get_liander_2025_dso_defaults,
    get_default_supplier_tariff_2025,
    get_default_metering_tariff_2025,
    get_default_levy_config_2025,
    get_stage_1_default_config_2025,
)
from .consumption_pipeline import (
    normalize_load_profile_2025,
    synthesize_benchmark_load_profile_2025,
    evaluate_load_integrity_audit,
)
from .dso_accounting import calculate_dso_accounting_2025
from .commercial_accounting import calculate_commercial_accounting_2025
from .status_quo_master import calculate_status_quo_master_2025
from .audit import perform_full_status_quo_audit, AuditReport

__all__ = [
    "TariffStage",
    "PricingMode",
    "LoadSeries2025",
    "DSOTariff",
    "SupplierTariff",
    "MeteringTariff",
    "LevyConfig",
    "StatusQuoConfig2025",
    "MonthlyConsumptionRecord",
    "DSOMonthlyResult",
    "CommercialMonthlyResult",
    "StatusQuoMonthlyResult",
    "StatusQuoAnnualResult",
    "get_liander_2025_dso_defaults",
    "get_default_supplier_tariff_2025",
    "get_default_metering_tariff_2025",
    "get_default_levy_config_2025",
    "get_stage_1_default_config_2025",
    "normalize_load_profile_2025",
    "synthesize_benchmark_load_profile_2025",
    "evaluate_load_integrity_audit",
    "calculate_dso_accounting_2025",
    "calculate_commercial_accounting_2025",
    "calculate_status_quo_master_2025",
    "perform_full_status_quo_audit",
    "AuditReport",
]
