"""
Tab 2: Contract Data UI Package (current_model/ui/tab2_contract)
===============================================================
Exports Tab 2 contract view and underlying form renderer.
"""

from .view import render_tab2_contract, render_tab2_base_contract, render_tab2_contract_switch
from .form import render_contract_form

__all__ = [
    "render_tab2_contract",
    "render_tab2_base_contract",
    "render_tab2_contract_switch",
    "render_contract_form",
]
