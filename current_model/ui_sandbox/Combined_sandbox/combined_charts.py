"""
========================================================================================
Combined System Sandbox Charts Facade (ui_sandbox/Combined_sandbox/combined_charts.py)
========================================================================================

Thin backward-compatible facade re-exporting all Plotly visualization builders
from `charts/`.
========================================================================================
"""

from .charts import (
    DEFAULT_POWERFLOW_COLORS,
    _resolve_window_slice,
    create_consumption_baseline_figure,
    compute_focus_range_for_timestamps,
    _mask_gap_for_webgl_fill,
    create_combined_dispatch_soc_figure,
    create_solar_production_figure,
    create_supply_mix_pie_figure,
    create_component_utilization_bars_figure,
    create_financial_cost_comparison_figure,
    create_financial_tco_trajectory_figure,
    create_financial_waterfall_bridge_figure,
    create_financial_monthly_cashflow_figure,
    create_monthly_grid_bill_progression_figure,
    create_dso_isolated_breakdown_figure,
    create_supplier_isolated_breakdown_figure,
    create_solar_isolated_financial_figure,
    create_battery_isolated_financial_figure,
    create_generator_isolated_financial_figure,
    create_tax_isolated_breakdown_figure,
    create_ab_15y_tco_comparison_figure,
    create_ab_annual_cost_stack_figure,
    create_ab_supply_and_utilization_figure,
)
