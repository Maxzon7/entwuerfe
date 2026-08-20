"""
Contract UI Package (current_model/ui/contract)
==============================================
Exports the electricity supply contract and tariff configuration form & view.
"""

from .form import render_contract_form, render_contract_view

__all__ = [
    "render_contract_form",
    "render_contract_view",
]
