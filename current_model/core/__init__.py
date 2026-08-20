"""
Core Engines Package (current_model/core)
========================================
Exports CSV parsing, load processing, metrics calculation, synthetic profile (24h & 365d),
and financial calculation engines.
"""

from .csv_parser import read_raw_content, parse_csv_content, detect_suggested_columns, generate_sample_demo_csv
from .load_processor import process_load_profile_data
from .metrics_engine import compute_load_profile_kpis, LoadProfileKPIs
from .synthetic_engine import aggregate_synthetic_24h, aggregate_synthetic_year, generate_time_labels_24h
from .financial_engine import compute_financial_bill

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
    "compute_financial_bill",
]
