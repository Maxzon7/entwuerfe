"""
Common UI Package (current_model/ui/common)
===========================================
Exports custom styling hooks and reusable KPI card renderers.
"""

from .styles import apply_custom_styles
from .cards import render_kpi_card

__all__ = [
    "apply_custom_styles",
    "render_kpi_card",
]
