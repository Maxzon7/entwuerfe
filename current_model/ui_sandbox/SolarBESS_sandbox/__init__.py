"""
========================================================================================
Scenario 5: Standalone Hybrid Solar PV + BESS Sandbox (ui_sandbox/SolarBESS_sandbox/__init__.py)
========================================================================================
"""

from .solar_bess_sandbox_engine import (
    HybridPreDimensioningResult,
    HybridKPIs,
    HybridFinancialResult,
    compute_hybrid_bess_pre_dimensioning,
    simulate_hybrid_dispatch_2025,
    simulate_dual_strategies_comparison,
    compute_synergy_comparison_metrics,
    compute_hybrid_plant_financials,
    create_hybrid_synchronized_dispatch_soc_figure,
    create_hybrid_monthly_balance_figure,
    create_hybrid_sankey_figure,
    create_hybrid_synergy_comparison_figure,
    create_hybrid_capex_donut_figure,
    create_hybrid_15y_outflow_figure,
)
from .app import render_solar_bess_sandbox, main

__all__ = [
    "HybridPreDimensioningResult",
    "HybridKPIs",
    "HybridFinancialResult",
    "compute_hybrid_bess_pre_dimensioning",
    "simulate_hybrid_dispatch_2025",
    "simulate_dual_strategies_comparison",
    "compute_synergy_comparison_metrics",
    "compute_hybrid_plant_financials",
    "create_hybrid_synchronized_dispatch_soc_figure",
    "create_hybrid_monthly_balance_figure",
    "create_hybrid_sankey_figure",
    "create_hybrid_synergy_comparison_figure",
    "create_hybrid_capex_donut_figure",
    "create_hybrid_15y_outflow_figure",
    "render_solar_bess_sandbox",
    "main",
]
