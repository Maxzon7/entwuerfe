"""
Data Models Package (current_model/models)
=========================================
Exports all core data structures: LoadComponent, TimeWindow, SimpleConsumer, Contract,
GridLimitConfig, OverloadAnalysisResult, CostLineItem, MonthlyPaymentRecord, FinancialCostBreakdown,
CalendarConfig, and presets.
"""

from .load_component import TimeWindow, SimpleConsumer, LoadComponent, Consumer
from .contract import Contract
from .grid_limit import GridLimitConfig, OverloadAnalysisResult
from .financial import CostLineItem, MonthlyPaymentRecord, FinancialCostBreakdown
from .calendar_config import CalendarConfig
from .presets import (
    PRESET_FACTORIES,
    PRESET_TEMPLATES,
    get_preset_factory,
    get_industry_preset_consumers,
    get_office_preset_consumers,
    get_ev_hub_preset_consumers
)
from .solar import (
    SolarLocation,
    SolarPVConfig,
    SolarMonthlyYield,
    SolarKPIs,
    SolarSimulationResult
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
    "MonthlyPaymentRecord",
    "FinancialCostBreakdown",
    "CalendarConfig",
    "PRESET_FACTORIES",
    "PRESET_TEMPLATES",
    "get_preset_factory",
    "get_industry_preset_consumers",
    "get_office_preset_consumers",
    "get_ev_hub_preset_consumers",
    "SolarLocation",
    "SolarPVConfig",
    "SolarMonthlyYield",
    "SolarKPIs",
    "SolarSimulationResult",
]


