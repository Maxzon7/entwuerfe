"""
Standalone Common UI Subset (`ui`)
==================================
Exposes shared card and stylesheet primitives from `ui.common`.
"""

from .common.styles import apply_custom_styles
from .common.cards import render_kpi_card

__all__ = [
    "apply_custom_styles",
    "render_kpi_card",
]
