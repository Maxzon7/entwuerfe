"""
Standalone Core Engines Subset (`core`)
=======================================
Exports only the modules required by the DRACBV Energy Simulator.
"""

from .csv_parser import (
    read_raw_content,
    parse_csv_content,
    detect_suggested_columns,
    generate_sample_demo_csv,
)
from .load_processor import process_load_profile_data
from .metrics_engine import compute_load_profile_kpis, LoadProfileKPIs
from .synthetic_engine import (
    aggregate_synthetic_24h,
    aggregate_synthetic_year,
    generate_time_labels_24h,
)
from .market_price_engine import (
    load_market_price_series,
    list_available_market_profiles,
)

__all__ = [
    "read_raw_content",
    "parse_csv_content",
    "detect_suggested_columns",
    "generate_sample_demo_csv",
    "process_load_profile_data",
    "compute_load_profile_kpis",
    "LoadProfileKPIs",
    "aggregate_synthetic_24h",
    "aggregate_synthetic_year",
    "generate_time_labels_24h",
    "load_market_price_series",
    "list_available_market_profiles",
]
