"""
Data Models Package (current_model/models)
=========================================
Exports all core data structures: LoadComponent, TimeWindow, SimpleConsumer, Contract,
GridLimitConfig, OverloadAnalysisResult, CostLineItem, FinancialCostBreakdown, and presets.
"""

from .load_component import TimeWindow, SimpleConsumer, LoadComponent, Consumer
from .contract import Contract
from .grid_limit import GridLimitConfig, OverloadAnalysisResult
from .financial import CostLineItem, FinancialCostBreakdown
from .presets import (
    PRESET_FACTORIES,
    get_industry_preset_consumers,
    get_office_preset_consumers,
    get_ev_hub_preset_consumers
)

__all__ = [
    "TimeWindow",
    "SimpleConsumer",
    "LoadComponent",
    "Consumer",
    "Contract",
    "GridLimitConfig",
    "OverloadAnalysisResult",
    "CostLineItem",
    "FinancialCostBreakdown",
    "PRESET_FACTORIES",
    "get_industry_preset_consumers",
    "get_office_preset_consumers",
    "get_ev_hub_preset_consumers",
]
