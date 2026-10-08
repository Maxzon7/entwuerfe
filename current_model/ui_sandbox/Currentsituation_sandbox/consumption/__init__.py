"""
Tab 1: Consumption UI Package (current_model/ui/tab1_consumption)
=================================================================
Exports Tab 1 main orchestrator along with synthetic and CSV sub-packages.
"""

from .view import render_tab1_consumption
from .synthetic.view import render_synthetic_simulator
from .csv_inspector.view import render_csv_inspector

__all__ = [
    "render_tab1_consumption",
    "render_synthetic_simulator",
    "render_csv_inspector",
]
