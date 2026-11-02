"""
========================================================================================
Shared Foundation Package for Standalone Scenario Sandboxes (ui_sandbox/common/__init__.py)
========================================================================================

Provides the 3 shared architectural building blocks across all 6 scenario sandboxes:
  1. Standardized 15-Minute Load & Residual Load Builder (`LoadSeries2025` & `build_residual_load_series_2025`)
  2. 4-Pillar Electricity Bill Engine & Side-by-Side Comparison (`evaluate_scenario_4pillar_bill_comparison`,
     `render_shared_4pillar_bill_comparison_ui`)
  3. Standardized Scenario Evaluation Result Container (`ScenarioEvaluationOutput`,
     `render_scenario_evaluation_output_card`)
  4. Standalone Baseline Quick-Loader & Snapshot Export/Import (`render_standalone_baseline_control_bar`,
     `export_baseline_snapshot_json`, `import_baseline_snapshot_json`)
========================================================================================
"""

from .evaluation_models import (
    ScenarioEvaluationOutput,
    build_residual_load_series_2025,
    evaluate_scenario_4pillar_bill_comparison,
    render_shared_4pillar_bill_comparison_ui,
    render_scenario_evaluation_output_card,
    compute_15y_tco_npv,
)
from .baseline_loader import (
    render_standalone_baseline_control_bar,
    export_baseline_snapshot_json,
    import_baseline_snapshot_json,
    load_preset_baseline_2025,
)

__all__ = [
    "ScenarioEvaluationOutput",
    "build_residual_load_series_2025",
    "evaluate_scenario_4pillar_bill_comparison",
    "render_shared_4pillar_bill_comparison_ui",
    "render_scenario_evaluation_output_card",
    "compute_15y_tco_npv",
    "render_standalone_baseline_control_bar",
    "export_baseline_snapshot_json",
    "import_baseline_snapshot_json",
    "load_preset_baseline_2025",
]

