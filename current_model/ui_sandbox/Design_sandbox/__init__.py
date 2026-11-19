"""
DRAC White-Green Design Language Blueprint (`ui_sandbox/Design_sandbox/`).

Isolated design-testing sandbox derived from the official DRAC PDF Feasibility Study
template (`#7a9f48` brand green, crisp white surfaces, slate typography, and DRAC logo).
"""

from .i18n import (
    DEFAULT_LANGUAGE,
    LANGUAGE_FULL_NAMES,
    LANGUAGE_LABELS,
    SUPPORTED_LANGUAGES,
    TRANSLATIONS,
    t,
)
from .theme import (
    DRAC_PALETTE,
    apply_drac_light_chart_theme,
    drac_loading_overlay,
    get_drac_logo_data_uri,
    get_drac_watermark_data_uri,
    inject_drac_light_theme,
    render_drac_cost_bridge_bar,
    render_drac_footer,
    render_drac_kpi_card,
    render_drac_masthead,
    render_drac_table_html,
    render_module_pills,
    render_section_heading,
    render_status_banner,
)

__all__ = [
    "DEFAULT_LANGUAGE",
    "DRAC_PALETTE",
    "LANGUAGE_FULL_NAMES",
    "LANGUAGE_LABELS",
    "SUPPORTED_LANGUAGES",
    "TRANSLATIONS",
    "apply_drac_light_chart_theme",
    "drac_loading_overlay",
    "get_drac_logo_data_uri",
    "get_drac_watermark_data_uri",
    "inject_drac_light_theme",
    "render_drac_cost_bridge_bar",
    "render_drac_footer",
    "render_drac_kpi_card",
    "render_drac_masthead",
    "render_drac_table_html",
    "render_module_pills",
    "render_section_heading",
    "render_status_banner",
    "t",
]
