"""
UI Layer Package (current_model/ui)
==================================
Exports top-level UI components and views for synthetic simulation, CSV inspection,
and contract modeling.
"""

from .common.styles import apply_custom_styles
from .common.cards import render_kpi_card
from .synthetic.view import render_synthetic_simulator
from .csv_inspector.view import render_csv_inspector
from .contract.form import render_contract_form, render_contract_view

__all__ = [
    "apply_custom_styles",
    "render_kpi_card",
    "render_synthetic_simulator",
    "render_csv_inspector",
    "render_contract_form",
    "render_contract_view",
]
