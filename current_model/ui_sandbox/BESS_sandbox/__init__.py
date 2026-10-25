"""
========================================================================================
BESS Sandbox Package
ui_sandbox/BESS_sandbox/__init__.py
========================================================================================

Exportable BESS Peak Shaving & 15-Year Life-Cycle TCO Sandbox components:
  - app: Standalone Streamlit application entrypoint.
  - baseline_presets: Pre-configured Dutch industrial & commercial benchmark scenarios.
  - sandbox_bess_engine: Dual-sizing recommendations, dynamic degradation & 15Y TCO engine.
  - view_problem: Tab 1 unmitigated load vs. grid connection limit.
  - view_technical: Tab 2 peak shaving feasibility, dual sizing & 15-min dispatch.
  - view_financial: Tab 3 avoided grid upgrade vs. BESS / Hybrid financial viability.
"""

from ui_sandbox.BESS_sandbox.app import render_bess_sandbox, main
from ui_sandbox.BESS_sandbox.baseline_presets import (
    BaselinePreset,
    get_case1_liander_industrial_preset,
    get_case2_enexis_commercial_preset,
    get_case3_paula_dutch_site_preset,
    build_custom_comparison_preset
)
from ui_sandbox.BESS_sandbox.sandbox_bess_engine import (
    ExcelSizingValidationResult,
    calculate_excel_bess_sizing_and_diagnostics,
    compute_exceedance_energy_summary,
    BottleneckCheckItem,
    BottleneckAuditResult,
    evaluate_comprehensive_bottlenecks,
    ParetoTradeoffResult,
    compute_pareto_coverage_curve,
    GrossSizingRecommendation,
    DualSizingRecommendation,
    compute_gross_minimum_bess_sizing,
    compute_dual_bess_sizing,
    compute_bess_degradation_profile,
    simulate_sandbox_bess_dispatch,
    evaluate_sandbox_bess_economics
)

from ui_sandbox.BESS_sandbox.sandbox_charts import (
    create_synced_dispatch_soc_figure,
    create_pareto_tradeoff_figure,
    compute_focus_range
)

from ui_sandbox.BESS_sandbox.view_problem import render_problem_baseline_tab
from ui_sandbox.BESS_sandbox.view_technical import render_technical_feasibility_tab
from ui_sandbox.BESS_sandbox.view_financial import render_financial_viability_tab

__all__ = [
    "render_bess_sandbox",
    "main",
    "render_problem_baseline_tab",
    "render_technical_feasibility_tab",
    "render_financial_viability_tab",
    "BaselinePreset",
    "get_case1_liander_industrial_preset",
    "get_case2_enexis_commercial_preset",
    "get_case3_paula_dutch_site_preset",
    "build_custom_comparison_preset",
    "ExcelSizingValidationResult",
    "calculate_excel_bess_sizing_and_diagnostics",
    "compute_exceedance_energy_summary",
    "BottleneckCheckItem",
    "BottleneckAuditResult",
    "evaluate_comprehensive_bottlenecks",
    "ParetoTradeoffResult",
    "compute_pareto_coverage_curve",
    "GrossSizingRecommendation",
    "DualSizingRecommendation",
    "compute_gross_minimum_bess_sizing",
    "compute_dual_bess_sizing",
    "compute_bess_degradation_profile",
    "simulate_sandbox_bess_dispatch",
    "evaluate_sandbox_bess_economics",
    "create_synced_dispatch_soc_figure",
    "create_pareto_tradeoff_figure",
    "compute_focus_range"
]

