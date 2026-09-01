# exports/__init__.py
"""
Standalone exports package containing:
- advanced_baseline_export: Independent Advanced Baseline generator with 12-month seasonality & anomalies.
- demo_contract_data_export: Independent Demo Mode grid contract data model & 4-pillar billing engine.
"""

from .advanced_baseline_export import (
    AnomalyConfig,
    generate_advanced_baseline,
    compute_baseline_metrics
)

from .demo_contract_data_export import (
    get_default_demo_contract_params,
    build_custom_contract_params,
    get_bill_components,
    calculate_bill_comparison
)

__all__ = [
    "AnomalyConfig",
    "generate_advanced_baseline",
    "compute_baseline_metrics",
    "get_default_demo_contract_params",
    "build_custom_contract_params",
    "get_bill_components",
    "calculate_bill_comparison"
]
