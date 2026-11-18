"""
HTML templates, DRACBV brand asset loaders, and A4 Print CSS (`pdf_report/templates_and_css.py`).

Uses `weasyprint` `@page` rules with the official DRACBV Green Energy Solutions
letterhead background (`#7a9f48`), top-right company contact block on Page 1,
subtle center watermark, and dynamic page counter + terms in the green footer.
"""

import base64
from functools import lru_cache
import html
import os
from typing import Dict, List, Optional, Sequence


_ASSETS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets"))

DRACBV_GREEN = "#7a9f48"
DRACBV_GREEN_DARK = "#5d7c34"
DRACBV_GREEN_SOFT = "#f2f7ec"


def esc(value: object) -> str:
    """Safely HTML-escapes any arbitrary value for WeasyPrint rendering."""
    return html.escape("" if value is None else str(value), quote=True)


@lru_cache(maxsize=4)
def _load_asset_data_uri(filename: str, mime: str) -> str:
    """Reads a static brand asset from `assets/` and returns a base64 data URI."""
    path = os.path.join(_ASSETS_DIR, filename)
    if not os.path.isfile(path):
        return ""
    with open(path, "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def get_dracbv_brand_assets() -> Dict[str, str]:
    """Returns cached base64 data URIs for DRACBV letterhead assets."""
    return {
        "letterhead_bg": _load_asset_data_uri("dracbv_letterhead_bg.png", "image/png"),
        "watermark": _load_asset_data_uri("dracbv_watermark.png", "image/png"),
        "map_accent": _load_asset_data_uri("dracbv_map_accent.jpg", "image/jpeg"),
    }


def build_print_stylesheet() -> str:
    """Constructs the A4 Print CSS incorporating the DRACBV stationery design."""
    assets = get_dracbv_brand_assets()
    bg_uri = assets["letterhead_bg"]
    bg_rule = f'background-image: url("{bg_uri}");' if bg_uri else ""
    terms_line_1 = (
        "Op alle rechtsverhoudingen tussen DRACBV en haar cli\\00ebnten zijn uitsluitend "
        "de algemene voorwaarden van DRACBV van toepassing."
    )
    terms_line_2 = (
        "Deze algemene voorwaarden zijn te downloaden via onze website: "
        "www.dracbv.nl. Op verzoek worden deze kosteloos toegezonden."
    )

    return f"""
@page {{
    size: A4 portrait;
    margin: 32mm 14mm 26mm 14mm;
    {bg_rule}
    background-repeat: no-repeat;
    background-position: -14mm -32mm;
    background-size: 210mm 297mm;

    @bottom-left {{
        content: "DRACBV Feasibility Study  |  Page " counter(page) " of " counter(pages);
        white-space: nowrap;
        font-family: "Helvetica Neue", Arial, sans-serif;
        font-size: 7.4pt;
        font-weight: 700;
        color: #ffffff;
        vertical-align: top;
        padding-top: 5.5mm;
        padding-left: 1mm;
    }}
    @bottom-right {{
        content: "{terms_line_1}\\A {terms_line_2}";
        white-space: pre-line;
        font-family: "Helvetica Neue", Arial, sans-serif;
        font-size: 5.8pt;
        line-height: 1.25;
        color: #f4f7ef;
        text-align: right;
        vertical-align: bottom;
        padding-bottom: 4.5mm;
        padding-right: 1mm;
    }}
}}

@page :first {{
    margin-top: 14mm;
    background-position: -14mm -14mm;
}}

* {{
    box-sizing: border-box;
}}

body {{
    font-family: "Helvetica Neue", Arial, Helvetica, sans-serif;
    font-size: 8.8pt;
    line-height: 1.42;
    color: #1e293b;
    margin: 0;
    padding: 0;
}}

.watermark-layer {{
    position: fixed;
    top: 138mm;
    left: 34mm;
    width: 112mm;
    opacity: 0.08;
    z-index: -1;
    pointer-events: none;
}}

.map-accent-layer {{
    position: fixed;
    right: -12mm;
    bottom: 24mm;
    width: 72mm;
    height: 72mm;
    border-radius: 50%;
    object-fit: cover;
    opacity: 0.14;
    border: 0.5pt solid #cbd5e1;
    z-index: -1;
    pointer-events: none;
}}

.cover-header {{
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 10mm;
    margin-bottom: 5mm;
    padding-bottom: 4mm;
    border-bottom: 1.4pt solid {DRACBV_GREEN};
}}

.cover-title-col {{
    width: 63%;
    padding-top: 2mm;
}}

.cover-contact-col {{
    width: 35%;
    padding-top: 20.5mm;
    text-align: right;
    font-size: 7.4pt;
    line-height: 1.32;
    color: {DRACBV_GREEN_DARK};
}}

.cover-contact-col strong {{
    color: {DRACBV_GREEN_DARK};
    font-size: 7.8pt;
}}

.report-eyebrow {{
    display: inline-block;
    background: {DRACBV_GREEN_SOFT};
    color: {DRACBV_GREEN_DARK};
    border: 0.7pt solid {DRACBV_GREEN};
    border-radius: 3px;
    padding: 1.2mm 2.8mm;
    font-size: 7.3pt;
    font-weight: 700;
    letter-spacing: 0.5px;
    text-transform: uppercase;
    margin-bottom: 2.5mm;
}}

h1.report-title {{
    margin: 0 0 1.5mm 0;
    font-size: 16.5pt;
    line-height: 1.18;
    color: #0f172a;
}}

.report-subtitle {{
    margin: 0 0 3mm 0;
    font-size: 9.2pt;
    color: #475569;
}}

.meta-strip {{
    font-size: 7.8pt;
    color: #334155;
    background: rgba(248, 250, 252, 0.92);
    border: 0.6pt solid #cbd5e1;
    border-left: 2.8pt solid {DRACBV_GREEN};
    border-radius: 3px;
    padding: 2mm 3mm;
}}

.section {{
    margin-top: 4.5mm;
}}

.section-heading {{
    font-size: 10.5pt;
    font-weight: 700;
    color: #0f172a;
    border-left: 3.2pt solid {DRACBV_GREEN};
    padding: 0.8mm 0 0.8mm 2.8mm;
    margin: 0 0 2.6mm 0;
    background: linear-gradient(90deg, {DRACBV_GREEN_SOFT}, rgba(255,255,255,0));
    page-break-after: avoid;
    break-after: avoid;
}}

.kpi-grid {{
    display: flex;
    gap: 2.6mm;
    margin-bottom: 3.2mm;
    break-inside: avoid;
}}

.kpi-card {{
    flex: 1 1 0;
    background: rgba(255, 255, 255, 0.95);
    border: 0.6pt solid #cbd5e1;
    border-top: 2.4pt solid #64748b;
    border-radius: 4px;
    padding: 2.4mm 2.8mm;
}}

.kpi-card.ok {{
    border-top-color: {DRACBV_GREEN};
}}

.kpi-card.alert {{
    border-top-color: #dc2626;
}}

.kpi-card.accent {{
    border-top-color: #2563eb;
}}

.kpi-label {{
    font-size: 6.9pt;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.4px;
    color: #64748b;
}}

.kpi-value {{
    font-size: 11.4pt;
    font-weight: 700;
    color: #0f172a;
    margin: 0.8mm 0;
}}

.kpi-sub {{
    font-size: 7.0pt;
    color: #475569;
    line-height: 1.25;
}}

.status-banner {{
    border-radius: 4px;
    padding: 2.4mm 3.2mm;
    margin-bottom: 3.2mm;
    font-size: 8.2pt;
    break-inside: avoid;
}}

.status-banner.ok {{
    background: #f0fdf4;
    border: 0.7pt solid #86efac;
    border-left: 3pt solid #16a34a;
    color: #14532d;
}}

.status-banner.warn {{
    background: #fef2f2;
    border: 0.7pt solid #fca5a5;
    border-left: 3pt solid #dc2626;
    color: #7f1d1d;
}}

.status-banner.info {{
    background: #f8fafc;
    border: 0.7pt solid #cbd5e1;
    border-left: 3pt solid {DRACBV_GREEN};
    color: #1e293b;
}}

.two-col-grid {{
    display: flex;
    gap: 4mm;
    align-items: stretch;
}}

.col-half {{
    flex: 1 1 0;
}}

.chart-card {{
    background: rgba(255, 255, 255, 0.94);
    border: 0.6pt solid #cbd5e1;
    border-radius: 4px;
    padding: 2.5mm;
    margin-bottom: 3.5mm;
    break-inside: avoid;
}}

.chart-title {{
    font-size: 8.2pt;
    font-weight: 700;
    color: #0f172a;
    margin: 0 0 1.4mm 0;
}}

.chart-card img {{
    display: block;
    width: 100%;
    height: auto;
}}

table.data-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 7.6pt;
    margin-bottom: 3.5mm;
    background: rgba(255, 255, 255, 0.95);
}}

table.data-table thead {{
    display: table-header-group;
}}

table.data-table th {{
    background: #1e293b;
    color: #ffffff;
    font-weight: 700;
    text-align: left;
    padding: 1.8mm 2.2mm;
    border: 0.4pt solid #334155;
}}

table.data-table th.num,
table.data-table td.num {{
    text-align: right;
}}

table.data-table td {{
    padding: 1.5mm 2.2mm;
    border: 0.4pt solid #e2e8f0;
    color: #1e293b;
    vertical-align: top;
}}

table.data-table tbody tr:nth-child(even) {{
    background: #f8fafc;
}}

table.data-table tr.summary-row td {{
    background: {DRACBV_GREEN_SOFT};
    font-weight: 700;
    border-top: 1pt solid {DRACBV_GREEN};
    color: #0f172a;
}}

.page-break {{
    page-break-before: always;
    break-before: page;
}}

.footnote {{
    font-size: 7.2pt;
    color: #64748b;
    margin-top: 1.5mm;
}}
"""


def render_kpi_grid(cards: Sequence[Dict[str, str]]) -> str:
    """Renders a horizontal flex row of KPI cards."""
    parts = ['<div class="kpi-grid">']
    for c in cards:
        tone = esc(c.get("tone", "default"))
        parts.append(
            f'<div class="kpi-card {tone}">'
            f'<div class="kpi-label">{esc(c.get("title", ""))}</div>'
            f'<div class="kpi-value">{esc(c.get("value", ""))}</div>'
            f'<div class="kpi-sub">{esc(c.get("subtext", ""))}</div>'
            f"</div>"
        )
    parts.append("</div>")
    return "".join(parts)


def render_data_table(
    headers: Sequence[str],
    rows: Sequence[Sequence[object]],
    numeric_cols: Optional[Sequence[int]] = None,
    summary_last_row: bool = False,
) -> str:
    """Renders a clean WeasyPrint table with repeating thead headers."""
    num_set = set(numeric_cols or ())
    parts = ['<table class="data-table"><thead><tr>']
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


def wrap_html_document(title: str, body_html: str) -> str:
    """Wraps HTML sections in a complete A4 HTML document with DRACBV watermarks."""
    assets = get_dracbv_brand_assets()
    wm_html = (
        f'<img class="watermark-layer" src="{assets["watermark"]}" alt="DRACBV Watermark">'
        if assets["watermark"]
        else ""
    )
    map_html = (
        f'<img class="map-accent-layer" src="{assets["map_accent"]}" alt="Background Accent">'
        if assets["map_accent"]
        else ""
    )
    return (
        "<!DOCTYPE html>"
        '<html lang="en">'
        "<head>"
        '<meta charset="utf-8">'
        f"<title>{esc(title)}</title>"
        f"<style>{build_print_stylesheet()}</style>"
        "</head>"
        "<body>"
        f"{wm_html}"
        f"{map_html}"
        f"{body_html}"
        "</body>"
        "</html>"
    )
