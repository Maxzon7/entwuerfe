"""
========================================================================================
Scenario 2: Standalone Contract Switch & Twin-Contract Benchmark Sandbox
ui_sandbox/NewContract_sandbox/__init__.py
========================================================================================
"""

from .contract_comparison_engine import (
    compute_contract_switch_kpis,
    create_4pillar_side_by_side_figure,
    create_12month_monthly_bill_comparison_figure,
    create_15year_tco_comparison_figure,
    build_4pillar_comparison_table,
)
from .app import (
    render_contract_workbench_instance,
    render_new_contract_sandbox,
    sync_contract_state,
    main,
)

__all__ = [
    "compute_contract_switch_kpis",
    "create_4pillar_side_by_side_figure",
    "create_12month_monthly_bill_comparison_figure",
    "create_15year_tco_comparison_figure",
    "build_4pillar_comparison_table",
    "render_contract_workbench_instance",
    "render_new_contract_sandbox",
    "sync_contract_state",
    "main",
]
