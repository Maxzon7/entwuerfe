"""
Combined System Sandbox Package (ui_sandbox/Combined_sandbox/)
Unites Grid, Solar, Battery, and Generator under the Clean Screen Policy.
"""

from .combined_sandbox_engine import (
    SOLAR_SITE_PRESETS,
    FUEL_SPECS,
    RULE1_OPTIONS,
    RULE2_OPTIONS,
    RULE3_OPTIONS,
    CombinedSystemConfig,
    InteractionRulesConfig,
    CombinedFinancialConfig,
    derive_solar_sizing_and_formula,
    derive_quick_sizing,
    QUICK_PRESET_OPTIONS,
    simulate_combined_system_dispatch,
    evaluate_combined_financials,
)

