"""
========================================================================================
BESS Sandbox Package
ui_sandbox/BESS_sandbox/__init__.py
========================================================================================

Exportable BESS Peak Shaving & 15-Year Life-Cycle TCO Sandbox components:
  - app: Standalone Streamlit application entrypoint.
  - baseline_presets: Pre-configured Dutch industrial & commercial benchmark scenarios.
  - sandbox_bess_engine: Gross sizing recommendations, dynamic degradation & 15Y TCO engine.
  - view_technical: Tab 1 peak shaving feasibility & 15-min dispatch.
  - view_financial: Tab 2 avoided grid upgrade vs. BESS financial viability.
  - view_optimizer: Tab 3 parametric capacity sweep & sensitivity analysis.
"""

from ui_sandbox.BESS_sandbox.app import render_bess_sandbox, main
from ui_sandbox.BESS_sandbox.baseline_presets import (
    BaselinePreset,
    get_case1_liander_industrial_preset,
    get_case2_enexis_commercial_preset,
    build_custom_comparison_preset
)
from ui_sandbox.BESS_sandbox.sandbox_bess_engine import (
    GrossSizingRecommendation,
    compute_gross_minimum_bess_sizing,
    compute_bess_degradation_profile,
    simulate_sandbox_bess_dispatch,
    evaluate_sandbox_bess_economics
)

__all__ = [
    "render_bess_sandbox",
    "main",
    "BaselinePreset",
    "get_case1_liander_industrial_preset",
    "get_case2_enexis_commercial_preset",
    "build_custom_comparison_preset",
    "GrossSizingRecommendation",
    "compute_gross_minimum_bess_sizing",
    "compute_bess_degradation_profile",
    "simulate_sandbox_bess_dispatch",
    "evaluate_sandbox_bess_economics"
]
