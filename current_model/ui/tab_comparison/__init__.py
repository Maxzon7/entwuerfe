"""
Master Scenario Comparison Tab Package
"""

from .view import render_master_comparison_dashboard
from .charts import (
    create_multi_scenario_cumulative_cost_figure,
    create_capex_opex_breakdown_figure,
    create_autarky_payback_figure
)

__all__ = [
    "render_master_comparison_dashboard",
    "create_multi_scenario_cumulative_cost_figure",
    "create_capex_opex_breakdown_figure",
    "create_autarky_payback_figure",
]
