"""
========================================================================================
UI Tab: Solar PV + BESS Hybrid Simulator (Beta) Package (ui/tab_hybrid_beta/__init__.py)
========================================================================================
"""

from current_model.ui.tab_hybrid_beta.view import render_tab_solar_bess_beta
from current_model.ui.tab_hybrid_beta.charts import (
    create_hybrid_dispatch_chart,
    create_hybrid_soc_chart,
    create_hybrid_monthly_balance_chart,
    create_hybrid_duration_curve
)

__all__ = [
    "render_tab_solar_bess_beta",
    "create_hybrid_dispatch_chart",
    "create_hybrid_soc_chart",
    "create_hybrid_monthly_balance_chart",
    "create_hybrid_duration_curve"
]
