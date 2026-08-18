"""
Presentation2 Module Package
============================
A modular toolkit for inspecting, processing, analyzing, and visualizing arbitrary CSV load profile data.
"""

from .parser import read_raw_content, parse_csv_content, detect_suggested_columns, generate_sample_demo_csv
from .processor import process_load_profile_data
from .metrics import compute_load_profile_kpis, LoadProfileKPIs
from .visualizer import create_dark_load_profile_figure

__all__ = [
    "read_raw_content",
    "parse_csv_content",
    "detect_suggested_columns",
    "generate_sample_demo_csv",
    "process_load_profile_data",
    "compute_load_profile_kpis",
    "LoadProfileKPIs",
    "create_dark_load_profile_figure",
]
