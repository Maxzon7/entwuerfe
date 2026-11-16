"""
Modular Engine Subpackage for Combined System Sandbox (`ui_sandbox/Combined_sandbox/engine/`).
"""

from .models_and_presets import (
    ENGINE_VERSION,
    MONTH_NAMES_SHORT,
    SOLAR_SITE_PRESETS,
    FUEL_SPECS,
    RULE1_OPTIONS,
    RULE2_OPTIONS,
    RULE3_OPTIONS,
    QUICK_PRESET_OPTIONS,
    MIX_STRATEGY_OPTIONS,
    CombinedSystemConfig,
    InteractionRulesConfig,
    CombinedFinancialConfig,
    CombinedFinancialKPIs,
    SolarDerivationInfo,
    CombinedTechnicalKPIs,
    CombinedSimulationResult,
    QuickSizingResult,
    DualBatterySizingResult,
    DualGeneratorSizingResult,
    CoordinatedMixRecommendation,
    SystemUtilizationDiagnostics,
)
from .solar_and_sizing import (
    get_unit_solar_generation_profile,
    derive_solar_sizing_and_formula,
    determine_smart_modular_units,
    _longest_true_run_steps,
    compute_overload_reference,
    _cluster_deficit_kernel,
    _evaluate_bess_criteria_for_profile,
    build_bess_bottleneck_table_df,
    refresh_bottleneck_table_configured_status,
    compute_dual_battery_sizing,
    compute_dual_generator_sizing,
    derive_quick_sizing,
)
from .dispatch_simulation import (
    _fast_combined_dispatch_kernel,
    _execute_coupled_dispatch_arrays,
    _calibrate_coupled_bess_capacity_kwh,
    simulate_combined_system_dispatch,
)
from .utilization_and_tables import (
    compute_coordinated_mix_sizing,
    compute_system_utilization_diagnostics,
    build_component_summary_table,
    build_monthly_balance_table,
)
from .financial_engine import (
    _calculate_irr,
    evaluate_combined_financials,
)
from .tariff_presets import (
    UTILITY_DSO_PRESETS,
    UTILITY_SUPPLIER_PRESETS,
    UTILITY_METERING_PRESETS,
    get_dso_preset_options,
    get_supplier_preset_options,
    get_metering_preset_options,
    apply_utility_tariff_presets,
    sync_financial_config_from_status_quo,
    scale_eur_hardware_defaults_to_currency,
)
