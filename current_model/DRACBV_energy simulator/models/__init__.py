"""
Standalone Data Models Subset (`models`)
========================================
Exports only the dataclasses and presets required by the DRACBV Energy Simulator.
"""

from .load_component import TimeWindow, SimpleConsumer, LoadComponent, Consumer
from .contract import Contract
from .financial import CostLineItem, MonthlyPaymentRecord, FinancialCostBreakdown
from .calendar_config import CalendarConfig
from .presets import (
    PRESET_FACTORIES,
    PRESET_TEMPLATES,
    get_preset_factory,
    get_industry_preset_consumers,
    get_office_preset_consumers,
    get_ev_hub_preset_consumers,
)
from .solar import (
    SolarLocation,
    SolarPVConfig,
    SolarMonthlyYield,
    SolarKPIs,
    SolarSimulationResult,
    SolarFinancialConfig,
    SolarFinancialMetrics,
)
from .bess import BESSConfig, BESSKPIs, get_bess_presets

__all__ = [
    "TimeWindow",
    "SimpleConsumer",
    "LoadComponent",
    "Consumer",
    "Contract",
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
    "SolarFinancialConfig",
    "SolarFinancialMetrics",
    "BESSConfig",
    "BESSKPIs",
    "get_bess_presets",
]
