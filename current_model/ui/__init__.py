"""
UI Layer Package (current_model/ui)
==================================
Exports top-level UI components and tab orchestrators:
  - Tab 1: render_tab1_consumption (Synthetic & CSV)
  - Tab 2: render_tab2_contract (Contract & Tariffs)
"""

from .common.styles import apply_custom_styles
from .common.cards import render_kpi_card
from .tab1_consumption.view import render_tab1_consumption
from .tab1_consumption.synthetic.view import render_synthetic_simulator
from .tab1_consumption.csv_inspector.view import render_csv_inspector
from .tab2_contract.view import render_tab2_contract, render_tab2_base_contract, render_tab2_contract_switch
from .tab2_contract.form import render_contract_form
from .tab_comparison.view import render_scenario_management, render_master_comparison_dashboard

__all__ = [
    "apply_custom_styles",
    "render_kpi_card",
    "render_tab1_consumption",
    "render_synthetic_simulator",
    "render_csv_inspector",
    "render_tab2_contract",
    "render_tab2_base_contract",
    "render_tab2_contract_switch",
    "render_contract_form",
    "render_scenario_management",
    "render_master_comparison_dashboard",
]
