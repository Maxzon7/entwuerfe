"""
DRAC White-Green Design System (`ui_sandbox/Design_sandbox/theme.py`).

Provides centralized design tokens, cached DRAC logo/watermark asset loaders,
global Streamlit light-mode CSS overrides, reusable HTML UI components mirroring
the DRAC PDF Feasibility Study template, and an interactive light-mode Plotly
theme adapter for figures imported from `Combined_sandbox`.
"""

import base64
from contextlib import contextmanager
import copy
from functools import lru_cache
import html
import io
import os
import time
from typing import Any, Dict, Iterable, Iterator, Optional, Sequence, Tuple

import plotly.graph_objects as go
import streamlit as st

try:
    from ui_sandbox.Combined_sandbox.combined_sandbox_engine import (
        fmt_curr,
        fmt_num,
        format_currency_value,
        get_plotly_separators,
    )
except ImportError:
    from current_model.ui_sandbox.Combined_sandbox.combined_sandbox_engine import (
        fmt_curr,
        fmt_num,
        format_currency_value,
        get_plotly_separators,
    )


_DESIGN_DIR = os.path.abspath(os.path.dirname(__file__))
_ASSETS_DIR = os.path.join(_DESIGN_DIR, "assets")
_COMBINED_ASSETS_DIR = os.path.abspath(
    os.path.join(_DESIGN_DIR, "..", "Combined_sandbox", "assets")
)


DRAC_PALETTE: Dict[str, str] = {
    "brand": "#7a9f48",
    "brand_logo": "#73984e",
    "brand_dark": "#5d7c34",
    "brand_soft": "#f2f7ec",
    "brand_tint": "#e8f1dd",
    "brand_border": "#cddcb9",
    "canvas": "#f7f9f5",
    "surface": "#ffffff",
    "surface_subtle": "#f8fafc",
    "border": "#dce3d8",
    "ink_strong": "#0f172a",
    "ink": "#1e293b",
    "ink_muted": "#475569",
    "ink_subtle": "#64748b",
    "ok": "#16a34a",
    "ok_bg": "#f0fdf4",
    "ok_border": "#86efac",
    "ok_ink": "#14532d",
    "alert": "#dc2626",
    "alert_bg": "#fef2f2",
    "alert_border": "#fca5a5",
    "alert_ink": "#7f1d1d",
    "accent": "#2563eb",
    "accent_bg": "#eff6ff",
    "accent_border": "#bfdbfe",
    "accent_ink": "#1e3a8a",
    "solar": "#d97706",
    "generator": "#ea580c",
    "battery": "#16a34a",
    "soc": "#7c3aed",
}


_DARK_TO_LIGHT_COLOR_MAP: Dict[str, str] = {
    "#F8FAFC": "#0F172A",
    "#E2E8F0": "#1E293B",
    "#CBD5E1": "#334155",
    "#94A3B8": "#475569",
    "#FACC15": "#D97706",
    "#C4B5FD": "#6D28D9",
    "#A78BFA": "#7C3AED",
    "#F87171": "#DC2626",
    "#38BDF8": "#0284C7",
    "#22C55E": "#16A34A",
    "#F97316": "#EA580C",
}


def esc(value: object) -> str:
    """Safely HTML-escapes any value for inline HTML rendering."""
    return html.escape("" if value is None else str(value), quote=True)


def _inline_svg_logo_fallback() -> str:
    """Returns a clean vector fallback reproducing the DRAC slanted-panel emblem."""
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 420 150">'
        '<g fill="#e0e6e4">'
        '<polygon points="10,10 92,10 120,66 38,66"/>'
        '<polygon points="104,10 186,10 214,66 132,66"/>'
        '<polygon points="198,10 280,10 308,66 226,66"/>'
        '<polygon points="44,76 126,76 154,138 72,138"/>'
        '<polygon points="138,76 220,76 248,138 166,138"/>'
        '<polygon points="232,76 314,76 342,138 260,138"/>'
        "</g>"
        '<text x="48" y="88" font-family="Arial, Helvetica, sans-serif" '
        'font-size="52" font-weight="800" letter-spacing="4" fill="#73984e">DRAC</text>'
        '<text x="234" y="48" font-family="Arial, Helvetica, sans-serif" '
        'font-size="16" font-weight="700" fill="#73984e">&#174;</text>'
        '<rect x="48" y="98" width="320" height="4" fill="#73984e"/>'
        '<text x="48" y="124" font-family="Arial, Helvetica, sans-serif" '
        'font-size="21" font-weight="500" letter-spacing="1.4" fill="#73984e">'
        "Green Energy Solutions</text>"
        "</svg>"
    )
    b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"


@lru_cache(maxsize=2)
def get_drac_logo_data_uri() -> str:
    """
    Returns a cached base64 data URI for the transparent DRAC Green Energy Solutions logo.
    Falls back to cropping the Combined Sandbox letterhead asset or inline SVG if absent.
    """
    primary_path = os.path.join(_ASSETS_DIR, "drac_logo.png")
    if os.path.isfile(primary_path):
        with open(primary_path, "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode("ascii")
        return f"data:image/png;base64,{b64}"

    letterhead_path = os.path.join(_COMBINED_ASSETS_DIR, "dracbv_letterhead_bg.png")
    if os.path.isfile(letterhead_path):
        try:
            from PIL import Image

            im = Image.open(letterhead_path).convert("RGBA")
            w, h = im.size
            crop = im.crop((int(w * 0.54), 0, w, int(h * 0.14)))
            buf = io.BytesIO()
            crop.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            return f"data:image/png;base64,{b64}"
        except Exception:
            pass

    return _inline_svg_logo_fallback()


@lru_cache(maxsize=2)
def get_drac_watermark_data_uri() -> str:
    """Returns a cached base64 data URI for the subtle DRAC watermark asset."""
    wm_path = os.path.join(_COMBINED_ASSETS_DIR, "dracbv_watermark.png")
    if not os.path.isfile(wm_path):
        return ""
    with open(wm_path, "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def inject_drac_light_theme(
    density: str = "executive",
    show_watermark: bool = False,
    loading_text: str = "Calculating...",
) -> None:
    """
    Injects global DRAC White-Green Light Mode CSS overrides across Streamlit widgets,
    containers, tabs, inputs, and custom design-system components.
    """
    p = DRAC_PALETTE
    is_compact = str(density).lower() == "compact"
    pad_top = "1.1rem" if is_compact else "1.65rem"
    pad_side = "1.5rem" if is_compact else "2.25rem"
    pad_bottom = "1.5rem" if is_compact else "2.5rem"
    card_pad = "11px 14px" if is_compact else "15px 18px"
    kpi_val_size = "1.32rem" if is_compact else "1.48rem"
    logo_uri = get_drac_logo_data_uri()
    css_calc_text = str(loading_text or "Calculating...").replace("\\", "\\\\").replace('"', '\\"')

    css = f"""
<style>
:root {{
    color-scheme: light;
    --drac-brand: {p["brand"]};
    --drac-brand-logo: {p["brand_logo"]};
    --drac-brand-dark: {p["brand_dark"]};
    --drac-brand-soft: {p["brand_soft"]};
    --drac-brand-tint: {p["brand_tint"]};
    --drac-brand-border: {p["brand_border"]};
    --drac-canvas: {p["canvas"]};
    --drac-surface: {p["surface"]};
    --drac-border: {p["border"]};
    --drac-ink-strong: {p["ink_strong"]};
    --drac-ink: {p["ink"]};
    --drac-ink-muted: {p["ink_muted"]};
    --drac-ink-subtle: {p["ink_subtle"]};
}}

/* Global Page Canvas & Typography */
html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {{
    background-color: {p["canvas"]} !important;
    color: {p["ink"]} !important;
    font-family: "Inter", "Segoe UI", "Helvetica Neue", Arial, sans-serif;
}}

[data-testid="stHeader"] {{
    background-color: {p["canvas"]} !important;
    border-bottom: 1px solid {p["border"]};
}}

[data-testid="stHeader"] * {{
    color: {p["ink"]} !important;
}}

.block-container {{
    max-width: 1440px;
    padding-top: {pad_top} !important;
    padding-left: {pad_side} !important;
    padding-right: {pad_side} !important;
    padding-bottom: {pad_bottom} !important;
}}

/* Sidebar Surface */
[data-testid="stSidebar"], [data-testid="stSidebarContent"], section[data-testid="stSidebar"] > div {{
    background-color: {p["surface"]} !important;
    border-right: 1px solid {p["border"]} !important;
    color: {p["ink"]} !important;
}}

[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3,
[data-testid="stSidebar"] h4,
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] {{
    color: {p["ink"]} !important;
}}

/* Global Text Readability (override dark-theme defaults) */
[data-testid="stMain"] p,
[data-testid="stMain"] li,
[data-testid="stMain"] label,
[data-testid="stMain"] h1,
[data-testid="stMain"] h2,
[data-testid="stMain"] h3,
[data-testid="stMain"] h4,
[data-testid="stMain"] h5,
[data-testid="stMain"] [data-testid="stWidgetLabel"] p {{
    color: {p["ink"]};
}}

[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {{
    color: {p["ink_subtle"]} !important;
}}

/* White Elevated Bordered Containers & Forms */
[data-testid="stVerticalBlockBorderWrapper"],
[data-testid="stForm"] {{
    background-color: {p["surface"]} !important;
    border: 1px solid {p["border"]} !important;
    border-radius: 10px !important;
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04), 0 1px 2px rgba(15, 23, 42, 0.03);
}}

[data-testid="stForm"] {{
    padding: 14px 16px !important;
}}

/* Navigation Tabs */
[data-baseweb="tab-list"] {{
    background-color: {p["surface"]} !important;
    border: 1px solid {p["border"]} !important;
    border-radius: 10px !important;
    padding: 4px 6px !important;
    gap: 4px !important;
    margin-bottom: 12px !important;
}}

[data-baseweb="tab"] {{
    background-color: transparent !important;
    color: {p["ink_muted"]} !important;
    border-radius: 7px !important;
    padding: 8px 14px !important;
    font-weight: 600 !important;
    font-size: 0.90rem !important;
    transition: background-color 0.15s ease, color 0.15s ease;
}}

[data-baseweb="tab"]:hover {{
    background-color: {p["brand_soft"]} !important;
    color: {p["brand_dark"]} !important;
}}

[data-baseweb="tab"][aria-selected="true"] {{
    background-color: {p["brand_soft"]} !important;
    color: {p["brand_dark"]} !important;
    font-weight: 700 !important;
}}

[data-baseweb="tab-highlight"] {{
    background-color: {p["brand"]} !important;
    height: 3px !important;
    border-radius: 2px !important;
}}

[data-baseweb="tab-border"] {{
    display: none !important;
}}

/* Primary & Secondary Buttons */
button[kind="primary"],
[data-testid="baseButton-primary"],
[data-testid="stFormSubmitButton"] button[kind="primary"],
[data-testid="stFormSubmitButton"] button[kind="primaryFormSubmit"] {{
    background-color: {p["brand"]} !important;
    border: 1px solid {p["brand"]} !important;
    color: #ffffff !important;
    font-weight: 600 !important;
    border-radius: 8px !important;
    box-shadow: 0 1px 2px rgba(93, 124, 52, 0.18);
}}

button[kind="primary"]:hover,
[data-testid="baseButton-primary"]:hover,
[data-testid="stFormSubmitButton"] button[kind="primary"]:hover,
[data-testid="stFormSubmitButton"] button[kind="primaryFormSubmit"]:hover {{
    background-color: {p["brand_dark"]} !important;
    border-color: {p["brand_dark"]} !important;
    color: #ffffff !important;
}}

button[kind="primary"] *,
[data-testid="baseButton-primary"] * {{
    color: #ffffff !important;
}}

button[kind="secondary"],
[data-testid="baseButton-secondary"],
[data-testid="stFormSubmitButton"] button[kind="secondary"],
[data-testid="stFormSubmitButton"] button[kind="secondaryFormSubmit"] {{
    background-color: {p["surface"]} !important;
    border: 1px solid #cbd5e1 !important;
    color: {p["ink"]} !important;
    font-weight: 600 !important;
    border-radius: 8px !important;
}}

button[kind="secondary"]:hover,
[data-testid="baseButton-secondary"]:hover,
[data-testid="stFormSubmitButton"] button[kind="secondary"]:hover,
[data-testid="stFormSubmitButton"] button[kind="secondaryFormSubmit"]:hover {{
    background-color: {p["brand_soft"]} !important;
    border-color: {p["brand"]} !important;
    color: {p["brand_dark"]} !important;
}}

button:disabled, [data-testid="baseButton-secondary"]:disabled {{
    background-color: #f1f5f9 !important;
    border-color: #e2e8f0 !important;
    color: #94a3b8 !important;
    opacity: 0.78 !important;
}}

/* Inputs, Number Inputs, Selectboxes, Textareas */
[data-baseweb="input"],
[data-baseweb="base-input"],
[data-baseweb="select"] > div {{
    background-color: {p["surface"]} !important;
    border-color: #cbd5e1 !important;
    color: {p["ink"]} !important;
    border-radius: 7px !important;
}}

[data-baseweb="input"]:focus-within,
[data-baseweb="select"] > div:focus-within {{
    border-color: {p["brand"]} !important;
    box-shadow: 0 0 0 2px rgba(122, 159, 72, 0.22) !important;
}}

input, textarea, [data-baseweb="select"] span, [data-baseweb="select"] input {{
    color: {p["ink"]} !important;
    background-color: transparent !important;
}}

[data-testid="stNumberInputStepDown"], [data-testid="stNumberInputStepUp"] {{
    background-color: {p["surface_subtle"]} !important;
    color: {p["ink"]} !important;
    border-left: 1px solid #e2e8f0 !important;
}}

[data-testid="stNumberInputStepDown"]:hover, [data-testid="stNumberInputStepUp"]:hover {{
    background-color: {p["brand_soft"]} !important;
    color: {p["brand_dark"]} !important;
}}

/* Popover Dropdown Lists */
[data-baseweb="popover"], [data-baseweb="popover"] > div, [role="listbox"] {{
    background-color: {p["surface"]} !important;
    color: {p["ink"]} !important;
    border: 1px solid {p["border"]} !important;
}}

[role="option"] {{
    background-color: {p["surface"]} !important;
    color: {p["ink"]} !important;
}}

[role="option"]:hover, [role="option"][aria-selected="true"] {{
    background-color: {p["brand_soft"]} !important;
    color: {p["brand_dark"]} !important;
}}

/* Sliders, Toggles, Checkboxes, Radios */
[data-baseweb="slider"] div[role="slider"] {{
    background-color: {p["brand"]} !important;
    border: 2px solid #ffffff !important;
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.25) !important;
}}

[data-testid="stCheckbox"] label span,
[data-testid="stRadio"] label span,
[data-testid="stToggle"] label span {{
    color: {p["ink"]} !important;
}}

/* Metrics */
[data-testid="stMetric"] {{
    background-color: {p["surface_subtle"]};
    border: 1px solid {p["border"]};
    border-radius: 8px;
    padding: 8px 12px;
}}

[data-testid="stMetricLabel"] p {{
    color: {p["ink_subtle"]} !important;
    font-size: 0.78rem !important;
    font-weight: 600 !important;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}}

[data-testid="stMetricValue"] {{
    color: {p["ink_strong"]} !important;
    font-weight: 700 !important;
}}

/* Expanders */
[data-testid="stExpander"] {{
    background-color: {p["surface"]} !important;
    border: 1px solid {p["border"]} !important;
    border-radius: 10px !important;
    overflow: hidden;
}}

[data-testid="stExpander"] summary {{
    background-color: {p["surface"]} !important;
    color: {p["ink_strong"]} !important;
    font-weight: 600 !important;
}}

[data-testid="stExpander"] summary:hover {{
    background-color: {p["brand_soft"]} !important;
    color: {p["brand_dark"]} !important;
}}

[data-testid="stExpander"] summary svg {{
    fill: {p["ink"]} !important;
    color: {p["ink"]} !important;
}}

/* DataFrames */
[data-testid="stDataFrame"] {{
    border: 1px solid {p["border"]};
    border-radius: 8px;
    overflow: hidden;
}}

/* Custom DRAC Design System Classes */
.drac-watermark-layer {{
    position: fixed;
    right: 22px;
    bottom: 22px;
    width: 300px;
    opacity: 0.05;
    pointer-events: none;
    z-index: 0;
}}

.drac-masthead {{
    border-radius: 12px;
    padding: 18px 22px;
    margin-bottom: 14px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 18px;
    box-shadow: 0 2px 8px rgba(15, 23, 42, 0.05);
}}

.drac-masthead--white_stationery {{
    background: {p["surface"]};
    border: 1px solid {p["border"]};
    border-top: 4px solid {p["brand"]};
    border-bottom: 2px solid {p["brand"]};
}}

.drac-masthead--soft_sage {{
    background: linear-gradient(135deg, #ffffff 0%, {p["brand_soft"]} 100%);
    border: 1px solid {p["brand_border"]};
    border-left: 5px solid {p["brand"]};
}}

.drac-masthead--solid_green {{
    background: linear-gradient(120deg, {p["brand_dark"]} 0%, {p["brand"]} 100%);
    border: 1px solid {p["brand_dark"]};
    color: #ffffff;
}}

.drac-masthead-left {{
    flex: 1 1 auto;
    min-width: 240px;
}}

.drac-masthead-right {{
    flex: 0 0 auto;
    display: flex;
    align-items: center;
    justify-content: flex-end;
}}

.drac-logo-frame-light {{
    padding: 4px 6px;
}}

.drac-logo-frame-solid {{
    background: #ffffff;
    border-radius: 10px;
    padding: 8px 14px;
    box-shadow: 0 2px 8px rgba(15, 23, 42, 0.14);
}}

.drac-eyebrow {{
    display: inline-block;
    background: {p["brand_soft"]};
    color: {p["brand_dark"]};
    border: 1px solid {p["brand_border"]};
    border-radius: 999px;
    padding: 3px 10px;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    margin-bottom: 6px;
}}

.drac-masthead--solid_green .drac-eyebrow {{
    background: rgba(255, 255, 255, 0.18);
    color: #ffffff;
    border-color: rgba(255, 255, 255, 0.38);
}}

.drac-masthead-title {{
    margin: 0 0 3px 0;
    font-size: 1.48rem;
    font-weight: 800;
    line-height: 1.18;
    color: {p["ink_strong"]};
}}

.drac-masthead--solid_green .drac-masthead-title {{
    color: #ffffff;
}}

.drac-masthead-subtitle {{
    margin: 0 0 10px 0;
    font-size: 0.90rem;
    color: {p["ink_muted"]};
}}

.drac-masthead--solid_green .drac-masthead-subtitle {{
    color: rgba(255, 255, 255, 0.90);
}}

.drac-meta-strip {{
    display: inline-block;
    font-size: 0.79rem;
    color: {p["ink"]};
    background: {p["surface_subtle"]};
    border: 1px solid {p["border"]};
    border-left: 3px solid {p["brand"]};
    border-radius: 6px;
    padding: 6px 11px;
}}

.drac-masthead--solid_green .drac-meta-strip {{
    background: rgba(255, 255, 255, 0.14);
    border-color: rgba(255, 255, 255, 0.28);
    border-left-color: #ffffff;
    color: #ffffff;
}}

.drac-section-heading {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 10px;
    font-size: 1.02rem;
    font-weight: 700;
    color: {p["ink_strong"]};
    border-left: 4px solid {p["brand"]};
    padding: 6px 12px;
    margin: 14px 0 10px 0;
    border-radius: 0 6px 6px 0;
    background: linear-gradient(90deg, {p["brand_soft"]} 0%, rgba(255, 255, 255, 0.0) 85%);
}}

.drac-section-sub {{
    font-size: 0.78rem;
    font-weight: 500;
    color: {p["ink_subtle"]};
    margin-left: 8px;
}}

.drac-section-badge {{
    font-size: 0.72rem;
    font-weight: 700;
    color: {p["brand_dark"]};
    background: {p["brand_soft"]};
    border: 1px solid {p["brand_border"]};
    border-radius: 999px;
    padding: 2px 9px;
    white-space: nowrap;
}}

.drac-kpi-card {{
    background: {p["surface"]};
    border: 1px solid {p["border"]};
    border-top: 3.5px solid {p["ink_subtle"]};
    border-radius: 10px;
    padding: {card_pad};
    margin-bottom: 10px;
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
    min-height: 106px;
}}

.drac-kpi-card--ok {{
    border-top-color: {p["brand"]};
}}

.drac-kpi-card--alert {{
    border-top-color: {p["alert"]};
}}

.drac-kpi-card--accent {{
    border-top-color: {p["accent"]};
}}

.drac-kpi-top {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 6px;
}}

.drac-kpi-label {{
    font-size: 0.72rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: {p["ink_subtle"]};
}}

.drac-kpi-pill {{
    font-size: 0.68rem;
    font-weight: 700;
    padding: 1px 7px;
    border-radius: 999px;
    background: {p["brand_soft"]};
    color: {p["brand_dark"]};
    border: 1px solid {p["brand_border"]};
}}

.drac-kpi-card--alert .drac-kpi-pill {{
    background: {p["alert_bg"]};
    color: {p["alert_ink"]};
    border-color: {p["alert_border"]};
}}

.drac-kpi-card--accent .drac-kpi-pill {{
    background: {p["accent_bg"]};
    color: {p["accent_ink"]};
    border-color: {p["accent_border"]};
}}

.drac-kpi-value {{
    font-size: {kpi_val_size};
    font-weight: 800;
    color: {p["ink_strong"]};
    margin: 5px 0 4px 0;
    line-height: 1.18;
}}

.drac-kpi-sub {{
    font-size: 0.77rem;
    color: {p["ink_muted"]};
    line-height: 1.3;
}}

.drac-banner {{
    border-radius: 9px;
    padding: 10px 14px;
    margin-bottom: 12px;
    font-size: 0.88rem;
    line-height: 1.42;
}}

.drac-banner--ok {{
    background: {p["ok_bg"]};
    border: 1px solid {p["ok_border"]};
    border-left: 4px solid {p["ok"]};
    color: {p["ok_ink"]};
}}

.drac-banner--warn {{
    background: {p["alert_bg"]};
    border: 1px solid {p["alert_border"]};
    border-left: 4px solid {p["alert"]};
    color: {p["alert_ink"]};
}}

.drac-banner--info {{
    background: {p["surface"]};
    border: 1px solid {p["brand_border"]};
    border-left: 4px solid {p["brand"]};
    color: {p["ink"]};
}}

.drac-pills-row {{
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 6px;
}}

.drac-pill {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    border-radius: 999px;
    padding: 3px 10px;
    font-size: 0.76rem;
    font-weight: 600;
}}

.drac-pill--active {{
    background: {p["brand_soft"]};
    color: {p["brand_dark"]};
    border: 1px solid {p["brand_border"]};
}}

.drac-pill--idle {{
    background: {p["surface_subtle"]};
    color: {p["ink_subtle"]};
    border: 1px solid #e2e8f0;
}}

.drac-dot {{
    width: 7px;
    height: 7px;
    border-radius: 50%;
    display: inline-block;
}}

.drac-bridge {{
    background: {p["surface"]};
    border: 1px solid {p["border"]};
    border-top: 3px solid {p["brand"]};
    border-radius: 10px;
    padding: 13px 16px;
    margin-bottom: 14px;
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
}}

.drac-bridge-hdr {{
    font-size: 0.74rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: {p["brand_dark"]};
    margin-bottom: 9px;
}}

.drac-bridge-flow {{
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
}}

.drac-bridge-box {{
    background: {p["surface_subtle"]};
    border: 1px solid #e2e8f0;
    border-left: 4px solid {p["ink_subtle"]};
    border-radius: 7px;
    padding: 8px 11px;
    flex: 1 1 130px;
}}

.drac-bridge-box--result {{
    background: {p["brand_soft"]};
    border: 1.5px solid {p["brand"]};
    border-left: 4px solid {p["brand_dark"]};
}}

.drac-bridge-op {{
    color: {p["ink_subtle"]};
    font-weight: 800;
    font-size: 1.05rem;
}}

.drac-bridge-foot {{
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    gap: 10px;
    margin-top: 10px;
    padding-top: 9px;
    border-top: 1px solid #e2e8f0;
    font-size: 0.81rem;
    color: {p["ink_muted"]};
}}

table.drac-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.84rem;
    background: {p["surface"]};
    border: 1px solid {p["border"]};
    border-radius: 8px;
    overflow: hidden;
    margin-bottom: 10px;
}}

table.drac-table thead th {{
    text-align: left;
    font-weight: 700;
    padding: 9px 11px;
    color: #ffffff;
    font-size: 0.79rem;
    letter-spacing: 0.02em;
}}

table.drac-table--slate thead th {{
    background: {p["ink"]};
    border-bottom: 2px solid {p["brand"]};
}}

table.drac-table--green thead th {{
    background: {p["brand_dark"]};
    border-bottom: 2px solid {p["brand"]};
}}

table.drac-table th.num,
table.drac-table td.num {{
    text-align: right;
    font-variant-numeric: tabular-nums;
}}

table.drac-table td {{
    padding: 8px 11px;
    border-bottom: 1px solid #e2e8f0;
    color: {p["ink"]};
}}

table.drac-table tbody tr:nth-child(even) {{
    background: {p["surface_subtle"]};
}}

table.drac-table tbody tr:hover {{
    background: {p["brand_soft"]};
}}

table.drac-table tr.summary-row td {{
    background: {p["brand_soft"]} !important;
    font-weight: 700;
    color: {p["ink_strong"]};
    border-top: 2px solid {p["brand"]};
    border-bottom: none;
}}

.drac-footer {{
    margin-top: 22px;
    background: {p["brand"]};
    color: #ffffff;
    border-radius: 8px;
    padding: 10px 16px;
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    align-items: center;
    gap: 10px;
    font-size: 0.78rem;
}}

@keyframes dracOverlayFadeIn {{
    from {{
        opacity: 0;
    }}
    to {{
        opacity: 1;
    }}
}}

/* Transform Streamlit's active rerun status widget into a centered DRAC overlay */
[data-testid="stStatusWidget"] {{
    position: fixed !important;
    inset: 0 !important;
    width: 100vw !important;
    height: 100vh !important;
    background: rgba(247, 249, 245, 0.78) !important;
    backdrop-filter: blur(3px);
    -webkit-backdrop-filter: blur(3px);
    z-index: 999990 !important;
    pointer-events: none !important;
    animation: dracOverlayFadeIn 0.22s ease 0.10s both;
}}

[data-testid="stStatusWidget"] * {{
    display: none !important;
}}

[data-testid="stStatusWidget"]::before {{
    content: "";
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: 310px;
    height: 170px;
    background-color: {p["surface"]};
    background-image: url("{logo_uri}");
    background-repeat: no-repeat;
    background-position: center 26px;
    background-size: auto 70px;
    border: 1px solid {p["brand_border"]};
    border-top: 4px solid {p["brand"]};
    border-radius: 14px;
    box-shadow: 0 14px 36px rgba(15, 23, 42, 0.12), 0 4px 12px rgba(122, 159, 72, 0.12);
    animation: dracOverlayFadeIn 0.22s ease 0.10s both;
}}

[data-testid="stStatusWidget"]::after {{
    content: "{css_calc_text}";
    position: fixed;
    top: calc(50% + 44px);
    left: 50%;
    transform: translate(-50%, -50%);
    font-family: "Inter", "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    font-size: 1.02rem;
    font-weight: 800;
    color: {p["ink_strong"]};
    letter-spacing: 0.01em;
    white-space: nowrap;
    animation: dracOverlayFadeIn 0.22s ease 0.10s both;
}}

@keyframes dracPulse {{
    0%, 100% {{
        transform: scale(1);
        opacity: 0.94;
    }}
    50% {{
        transform: scale(1.045);
        opacity: 1;
    }}
}}

@keyframes dracBarSlide {{
    0% {{
        transform: translateX(-110%);
    }}
    100% {{
        transform: translateX(260%);
    }}
}}

.drac-loader-backdrop {{
    position: fixed;
    inset: 0;
    background: rgba(247, 249, 245, 0.84);
    backdrop-filter: blur(4px);
    -webkit-backdrop-filter: blur(4px);
    z-index: 999999;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px;
}}

.drac-loader-card {{
    background: {p["surface"]};
    border: 1px solid {p["brand_border"]};
    border-top: 4px solid {p["brand"]};
    border-radius: 14px;
    padding: 28px 38px;
    text-align: center;
    box-shadow: 0 14px 36px rgba(15, 23, 42, 0.12), 0 4px 12px rgba(122, 159, 72, 0.12);
    min-width: 280px;
    max-width: 380px;
}}

.drac-loader-logo {{
    height: 74px;
    width: auto;
    display: block;
    margin: 0 auto 16px auto;
    animation: dracPulse 1.6s ease-in-out infinite;
}}

.drac-loader-bar-track {{
    width: 100%;
    height: 5px;
    border-radius: 999px;
    background: {p["brand_soft"]};
    border: 1px solid {p["brand_border"]};
    overflow: hidden;
    margin-bottom: 14px;
}}

.drac-loader-bar-fill {{
    width: 40%;
    height: 100%;
    border-radius: 999px;
    background: linear-gradient(90deg, {p["brand_dark"]} 0%, {p["brand"]} 100%);
    animation: dracBarSlide 1.25s ease-in-out infinite;
}}

.drac-loader-title {{
    font-size: 1.04rem;
    font-weight: 800;
    color: {p["ink_strong"]};
    letter-spacing: 0.01em;
    margin-bottom: 4px;
}}

.drac-loader-sub {{
    font-size: 0.78rem;
    color: {p["ink_subtle"]};
}}
</style>
"""
    st.markdown(css, unsafe_allow_html=True)

    if show_watermark:
        wm_uri = get_drac_watermark_data_uri()
        if wm_uri:
            st.markdown(
                f'<img class="drac-watermark-layer" src="{wm_uri}" alt="DRAC Watermark">',
                unsafe_allow_html=True,
            )


def render_drac_masthead(
    title: str,
    subtitle: str,
    eyebrow: str = "DRAC DESIGN BLUEPRINT",
    meta_items: Optional[Sequence[Tuple[str, str]]] = None,
    header_variant: str = "white_stationery",
) -> None:
    """Renders the branded DRAC top masthead featuring the official DRAC logo."""
    variant = (
        header_variant
        if header_variant in ("white_stationery", "soft_sage", "solid_green")
        else "white_stationery"
    )
    logo_uri = get_drac_logo_data_uri()
    logo_frame_cls = "drac-logo-frame-solid" if variant == "solid_green" else "drac-logo-frame-light"

    meta_html = ""
    if meta_items:
        parts = [f"<strong>{esc(k)}:</strong> {esc(v)}" for k, v in meta_items]
        meta_html = f'<div class="drac-meta-strip">{" &nbsp;|&nbsp; ".join(parts)}</div>'

    html_block = (
        f'<div class="drac-masthead drac-masthead--{variant}">'
        '<div class="drac-masthead-left">'
        f'<div class="drac-eyebrow">{esc(eyebrow)}</div>'
        f'<div class="drac-masthead-title">{esc(title)}</div>'
        f'<div class="drac-masthead-subtitle">{esc(subtitle)}</div>'
        f"{meta_html}"
        "</div>"
        '<div class="drac-masthead-right">'
        f'<div class="{logo_frame_cls}">'
        f'<img src="{logo_uri}" alt="DRAC Green Energy Solutions" style="height:68px; width:auto; display:block;">'
        "</div>"
        "</div>"
        "</div>"
    )
    st.markdown(html_block, unsafe_allow_html=True)


def render_section_heading(
    title: str,
    subtitle: Optional[str] = None,
    badge: Optional[str] = None,
) -> None:
    """Renders a DRAC PDF-inspired section header bar with green left rule and sage wash."""
    sub_html = f'<span class="drac-section-sub">{esc(subtitle)}</span>' if subtitle else ""
    badge_html = f'<span class="drac-section-badge">{esc(badge)}</span>' if badge else ""
    st.markdown(
        f'<div class="drac-section-heading">'
        f"<div><span>{esc(title)}</span>{sub_html}</div>"
        f"{badge_html}"
        "</div>",
        unsafe_allow_html=True,
    )


def render_drac_kpi_card(
    title: str,
    value: str,
    subtext: str = "",
    tone: str = "default",
    badge: Optional[str] = None,
) -> None:
    """Renders a clean white KPI card with a top semantic accent rule."""
    safe_tone = tone if tone in ("default", "ok", "alert", "accent") else "default"
    pill_html = f'<span class="drac-kpi-pill">{esc(badge)}</span>' if badge else ""
    sub_html = f'<div class="drac-kpi-sub">{esc(subtext)}</div>' if subtext else ""
    st.markdown(
        f'<div class="drac-kpi-card drac-kpi-card--{safe_tone}">'
        '<div class="drac-kpi-top">'
        f'<span class="drac-kpi-label">{esc(title)}</span>'
        f"{pill_html}"
        "</div>"
        f'<div class="drac-kpi-value">{esc(value)}</div>'
        f"{sub_html}"
        "</div>",
        unsafe_allow_html=True,
    )


def render_status_banner(title: str, body: str, tone: str = "ok") -> None:
    """Renders a light-mode compliance or informational banner."""
    safe_tone = tone if tone in ("ok", "warn", "info") else "info"
    st.markdown(
        f'<div class="drac-banner drac-banner--{safe_tone}">'
        f"<strong>{esc(title)}</strong> {esc(body)}"
        "</div>",
        unsafe_allow_html=True,
    )


def render_module_pills(modules: Sequence[Tuple[str, bool, str]]) -> None:
    """Renders horizontal status pills for active vs. standby system modules."""
    p = DRAC_PALETTE
    items = []
    for label, is_active, detail in modules:
        cls = "drac-pill--active" if is_active else "drac-pill--idle"
        dot_color = p["brand"] if is_active else "#94a3b8"
        text = f"{label}: {detail}" if detail else label
        items.append(
            f'<span class="drac-pill {cls}">'
            f'<span class="drac-dot" style="background:{dot_color};"></span>'
            f"{esc(text)}"
            "</span>"
        )
    st.markdown(f'<div class="drac-pills-row">{"".join(items)}</div>', unsafe_allow_html=True)


def render_drac_cost_bridge_bar(
    sim_res: Any,
    labels: Optional[Dict[str, str]] = None,
) -> None:
    """Renders a White-Green executive Annual Cost & Savings equation bar."""
    fk = getattr(sim_res, "financial_kpis", None)
    if fk is None:
        return
    p = DRAC_PALETTE
    lbl = labels or {}
    curr = str(getattr(fk, "currency_code", "EUR") or "EUR")
    yrs_unit = lbl.get("yrs_unit", "yrs")
    per_yr = lbl.get("per_yr", "yr")
    pb_str = f"{fmt_num(fk.payback_years, 1)} {yrs_unit}" if fk.payback_years is not None else "N/A"
    sav_pos = fk.annual_savings_eur >= 0.0
    sav_border = p["brand_dark"] if sav_pos else p["alert"]
    sav_bg = p["brand_soft"] if sav_pos else p["alert_bg"]
    sav_ink = p["brand_dark"] if sav_pos else p["alert_ink"]

    hdr_txt = lbl.get("header", f"Annual Cost & Savings Bridge ({curr})")
    curr_bill_lbl = lbl.get("current_bill", "Current Situation Bill")
    new_grid_lbl = lbl.get("new_grid", "New Grid Bill")
    hw_opex_lbl = lbl.get("hw_opex", "Hardware OPEX & Fuel")
    export_lbl = lbl.get("export_income", "Solar Export Income")
    comb_opex_lbl = lbl.get("combined_opex", "Combined Annual OPEX")
    net_sav_lbl = lbl.get("net_savings", "Net Annual Savings")
    net_capex_lbl = lbl.get("net_capex", "Net CAPEX")
    payback_lbl = lbl.get("payback", "Payback Period")
    npv_lbl = lbl.get("npv_15y", "15-Year NPV")
    sol_lbl = lbl.get("solar", "Solar")
    bat_lbl = lbl.get("battery", "Battery")
    gen_lbl = lbl.get("gen", "Gen")

    html_block = (
        '<div class="drac-bridge">'
        f'<div class="drac-bridge-hdr">{esc(hdr_txt)}</div>'
        '<div class="drac-bridge-flow">'
        f'<div class="drac-bridge-box" style="border-left-color:{p["alert"]};">'
        f'<div style="font-size:0.72rem; color:#64748b; font-weight:600;">{esc(curr_bill_lbl)}</div>'
        f'<div style="font-size:1.02rem; color:#0f172a; font-weight:700;">{esc(fmt_curr(fk.baseline_total_opex_eur, curr))} / {esc(per_yr)}</div>'
        "</div>"
        '<div class="drac-bridge-op">&rarr;</div>'
        f'<div class="drac-bridge-box" style="border-left-color:{p["accent"]};">'
        f'<div style="font-size:0.72rem; color:#64748b; font-weight:600;">{esc(new_grid_lbl)}</div>'
        f'<div style="font-size:1.02rem; color:#0f172a; font-weight:700;">{esc(fmt_curr(fk.combined_grid_total_eur, curr))} / {esc(per_yr)}</div>'
        "</div>"
        '<div class="drac-bridge-op">+</div>'
        f'<div class="drac-bridge-box" style="border-left-color:{p["solar"]};">'
        f'<div style="font-size:0.72rem; color:#64748b; font-weight:600;">{esc(hw_opex_lbl)}</div>'
        f'<div style="font-size:1.02rem; color:#0f172a; font-weight:700;">{esc(fmt_curr(fk.system_om_and_fuel_y1_eur, curr))} / {esc(per_yr)}</div>'
        "</div>"
        '<div class="drac-bridge-op">&minus;</div>'
        f'<div class="drac-bridge-box" style="border-left-color:{p["ok"]};">'
        f'<div style="font-size:0.72rem; color:#64748b; font-weight:600;">{esc(export_lbl)}</div>'
        f'<div style="font-size:1.02rem; color:#0f172a; font-weight:700;">{esc(fmt_curr(fk.solar_export_revenue_eur, curr))} / {esc(per_yr)}</div>'
        "</div>"
        '<div class="drac-bridge-op">=</div>'
        '<div class="drac-bridge-box drac-bridge-box--result">'
        f'<div style="font-size:0.72rem; color:{p["brand_dark"]}; font-weight:700; text-transform:uppercase;">{esc(comb_opex_lbl)}</div>'
        f'<div style="font-size:1.04rem; color:#0f172a; font-weight:800;">{esc(fmt_curr(fk.total_annual_opex_eur, curr))} / {esc(per_yr)}</div>'
        "</div>"
        '<div class="drac-bridge-op">&rarr;</div>'
        f'<div class="drac-bridge-box" style="background:{sav_bg}; border:1.5px solid {sav_border}; border-left:4px solid {sav_border};">'
        f'<div style="font-size:0.72rem; color:{sav_ink}; font-weight:800; text-transform:uppercase;">{esc(net_sav_lbl)}</div>'
        f'<div style="font-size:1.06rem; color:{sav_ink}; font-weight:800;">{esc(fmt_curr(fk.annual_savings_eur, curr, signed=True))} / {esc(per_yr)}</div>'
        "</div>"
        "</div>"
        '<div class="drac-bridge-foot">'
        f"<div><strong>{esc(net_capex_lbl)}:</strong> {esc(format_currency_value(fk.total_capex_eur, curr))} "
        f"({esc(sol_lbl)} {esc(format_currency_value(fk.solar_capex_eur, curr))} + "
        f"{esc(bat_lbl)} {esc(format_currency_value(fk.battery_capex_eur, curr))} + "
        f"{esc(gen_lbl)} {esc(format_currency_value(fk.generator_capex_eur, curr))})</div>"
        f"<div><strong>{esc(payback_lbl)}:</strong> {esc(pb_str)} &nbsp;|&nbsp; "
        f"<strong>{esc(npv_lbl)}:</strong> {esc(format_currency_value(fk.npv_15y_eur, curr, signed=True))}</div>"
        "</div>"
        "</div>"
    )
    st.markdown(html_block, unsafe_allow_html=True)


def render_drac_table_html(
    headers: Sequence[str],
    rows: Sequence[Sequence[object]],
    numeric_cols: Iterable[int] = (),
    summary_last_row: bool = False,
    header_tone: str = "slate",
) -> str:
    """
    Returns clean, indentation-free HTML for a DRAC print-grade data table.
    Supports `header_tone="slate"` (PDF match) or `header_tone="green"`.
    """
    num_set = set(numeric_cols)
    tone_cls = "drac-table--green" if header_tone == "green" else "drac-table--slate"
    parts = [f'<table class="drac-table {tone_cls}"><thead><tr>']
    for idx, h in enumerate(headers):
        cls = ' class="num"' if idx in num_set else ""
        parts.append(f"<th{cls}>{esc(h)}</th>")
    parts.append("</tr></thead><tbody>")

    last_idx = len(rows) - 1
    for r_idx, row in enumerate(rows):
        row_cls = ' class="summary-row"' if (summary_last_row and r_idx == last_idx) else ""
        parts.append(f"<tr{row_cls}>")
        for c_idx, val in enumerate(row):
            cls = ' class="num"' if c_idx in num_set else ""
            parts.append(f"<td{cls}>{esc(val)}</td>")
        parts.append("</tr>")
    parts.append("</tbody></table>")
    return "".join(parts)


def render_drac_footer(
    note: str = "DRAC Design Language Blueprint  |  White & Brand Green Light Theme",
    right_text: str = "Brand Primary: #7a9f48  |  Soft Sage: #f2f7ec",
) -> None:
    """Renders the solid DRAC green bottom stationery bar."""
    st.markdown(
        '<div class="drac-footer">'
        f"<span><strong>DRAC Green Energy Solutions</strong> &nbsp;|&nbsp; {esc(note)}</span>"
        f"<span>{esc(right_text)}</span>"
        "</div>",
        unsafe_allow_html=True,
    )


@contextmanager
def drac_loading_overlay(
    message: str = "Calculating...",
    subtext: str = "",
    min_duration_s: float = 0.65,
) -> Iterator[None]:
    """
    Context manager displaying a centered animated DRAC logo overlay with status
    text during heavy calculations, holding long enough for WebSocket paint before clearing.
    """
    placeholder = st.empty()
    logo_uri = get_drac_logo_data_uri()
    sub_html = f'<div class="drac-loader-sub">{esc(subtext)}</div>' if subtext else ""
    placeholder.markdown(
        '<div class="drac-loader-backdrop">'
        '<div class="drac-loader-card">'
        f'<img class="drac-loader-logo" src="{logo_uri}" alt="DRAC Loading">'
        '<div class="drac-loader-bar-track"><div class="drac-loader-bar-fill"></div></div>'
        f'<div class="drac-loader-title">{esc(message)}</div>'
        f"{sub_html}"
        "</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    t0 = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - t0
        if min_duration_s > 0.0 and elapsed < min_duration_s:
            time.sleep(min_duration_s - elapsed)
        placeholder.empty()


def _darken_color(color_val: Any) -> Any:
    """Converts light-on-dark colors into crisp light-mode shades."""
    if not isinstance(color_val, str):
        return color_val
    upper = color_val.strip().upper()
    if upper in _DARK_TO_LIGHT_COLOR_MAP:
        return _DARK_TO_LIGHT_COLOR_MAP[upper]
    if "248, 250, 252" in color_val or "248,250,252" in color_val:
        return "rgba(100, 116, 139, 0.50)"
    if "255, 255, 255" in color_val or "255,255,255" in color_val:
        return "rgba(30, 41, 59, 0.30)"
    return color_val


def apply_drac_light_chart_theme(
    fig: go.Figure,
    height: Optional[int] = None,
) -> go.Figure:
    """
    Adapts an interactive `Combined_sandbox` Plotly figure (`plotly_dark`) into a crisp
    DRAC White-Green light theme while preserving WebGL performance, zoom, and hover behavior.
    """
    out = copy.deepcopy(fig)
    p = DRAC_PALETTE

    layout_updates: Dict[str, Any] = {
        "template": "plotly_white",
        "separators": get_plotly_separators(),
        "paper_bgcolor": "rgba(255, 255, 255, 0.0)",
        "plot_bgcolor": "#ffffff",
        "font": dict(
            color=p["ink"],
            family="Inter, Segoe UI, Arial, sans-serif",
            size=12,
        ),
        "hoverlabel": dict(
            bgcolor="#ffffff",
            bordercolor="#cbd5e1",
            font=dict(color=p["ink_strong"], size=12),
        ),
    }
    if height is not None:
        layout_updates["height"] = int(height)

    if out.layout.title and out.layout.title.text:
        layout_updates["title_font"] = dict(color=p["ink_strong"], size=14)
    if out.layout.legend:
        layout_updates["legend_font"] = dict(color=p["ink"], size=11)
        layout_updates["legend_bgcolor"] = "rgba(255, 255, 255, 0.85)"

    out.update_layout(**layout_updates)

    for axis_key in list(out.layout.to_plotly_json().keys()):
        if not (axis_key.startswith("xaxis") or axis_key.startswith("yaxis")):
            continue
        axis_obj = getattr(out.layout, axis_key, None)
        if axis_obj is None:
            continue
        axis_updates: Dict[str, Any] = {
            "gridcolor": "rgba(148, 163, 184, 0.25)",
            "zerolinecolor": "rgba(100, 116, 139, 0.45)",
            "tickfont": dict(color="#334155", size=11),
            "title_font": dict(color=p["ink"], size=12),
        }
        if axis_key.startswith("xaxis"):
            rs = getattr(axis_obj, "rangeselector", None)
            if rs is not None and getattr(rs, "buttons", None):
                axis_updates["rangeselector"] = dict(
                    bgcolor=p["brand_soft"],
                    activecolor=p["brand"],
                    bordercolor=p["brand_border"],
                    borderwidth=1,
                    font=dict(color=p["ink"], size=11),
                )
            rsl = getattr(axis_obj, "rangeslider", None)
            if rsl is not None and getattr(rsl, "visible", False):
                axis_updates["rangeslider"] = dict(
                    bgcolor=p["canvas"],
                    bordercolor=p["border"],
                    borderwidth=1,
                )
        axis_obj.update(**axis_updates)

    for shape in out.layout.shapes or ():
        if getattr(shape, "line", None) and getattr(shape.line, "color", None):
            shape.line.color = _darken_color(shape.line.color)

    for ann in out.layout.annotations or ():
        if getattr(ann, "font", None) and getattr(ann.font, "color", None):
            ann.font.color = _darken_color(ann.font.color)
        if isinstance(getattr(ann, "text", None), str):
            ann.text = (
                ann.text.replace("#F8FAFC", "#0F172A")
                .replace("#f8fafc", "#0f172a")
                .replace("#94A3B8", "#64748B")
                .replace("#94a3b8", "#64748b")
            )

    for tr in out.data:
        tr_json = tr.to_plotly_json()
        if "line" in tr_json and isinstance(tr_json["line"], dict):
            col = tr_json["line"].get("color")
            if col:
                tr.line.color = _darken_color(col)
        if "marker" in tr_json and isinstance(tr_json["marker"], dict):
            m_col = tr_json["marker"].get("color")
            if isinstance(m_col, str):
                tr.marker.color = _darken_color(m_col)
            elif isinstance(m_col, list):
                tr.marker.color = [_darken_color(x) for x in m_col]
        if tr_json.get("type") == "pie":
            if getattr(tr, "marker", None) and getattr(tr.marker, "colors", None):
                tr.marker.colors = [_darken_color(c) for c in tr.marker.colors]
            if getattr(tr, "marker", None) and getattr(tr.marker, "line", None):
                tr.marker.line.color = "#FFFFFF"
            if getattr(tr, "textfont", None):
                tr.textfont.color = "#0F172A"

    return out
