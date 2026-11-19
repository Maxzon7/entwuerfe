"""
Centralized Number & Currency Formatting Helpers (`engine/formatting.py`).

Pure Python module (zero Streamlit imports) providing consistent European
number formatting (dot `.` thousands separator, comma `,` decimal separator)
for high-visibility KPI cards, HTML sub-ledgers, phase logs, tables, Plotly
charts, and the DRACBV PDF report.

# [ROLLBACK NOTE]
# To revert numeric and currency displays back to Anglo-American formatting
# (comma `,` thousands separator, dot `.` decimal separator, e.g. `1,234.56`):
#   1. Change `USE_EU_NUMBER_FORMAT: bool = False` directly below.
#      Every `fmt_num()`, `fmt_curr()`, `format_currency_value()`, `_fmt_curr()`,
#      and Plotly chart `separators` setting switches back immediately without
#      editing any view, chart, or PDF module.
#   2. Unified `CAPEX` / `OPEX` / `Current Situation` / `Payback Period` display
#      labels live strictly in 6 display modules (no dataclass or state keys changed):
#        - views/subtab6_isolated_pillars.py
#        - views/subtab6_hardware_costs.py
#        - views/subtab6_financials_overview.py
#        - views/subtab7_scenario_comparison.py
#        - engine/scenario_tables_and_profiles.py
#        - pdf_report/report_builder.py
"""

import math
from typing import Any, Dict


# Master 1-line switch for European number formatting (1.234,56 vs 1,234.56)
USE_EU_NUMBER_FORMAT: bool = True
PLOTLY_NUMBER_SEPARATORS: str = ",." if USE_EU_NUMBER_FORMAT else ".,"

CURRENCY_PREFIXES: Dict[str, str] = {
    "EUR": "€",
    "USD": "$",
}


def get_plotly_separators() -> str:
    """Returns Plotly `layout.separators` matching `USE_EU_NUMBER_FORMAT`."""
    return ",." if USE_EU_NUMBER_FORMAT else ".,"


def curr_prefix(currency_code: str = "EUR", html: bool = False) -> str:
    """Returns compact currency prefix (`€`/`&euro;`, `$`, or `<ISO> `)."""
    code = str(currency_code or "EUR").strip() or "EUR"
    if code == "EUR":
        return "&euro;" if html else "€"
    if code in CURRENCY_PREFIXES:
        return CURRENCY_PREFIXES[code]
    return f"{code} "


def fmt_num(
    val: Any,
    decimals: int = 0,
    signed: bool = False,
    na_label: str = "N/A",
) -> str:
    """
    Formats a numeric value using European grouping (`1.234,56`) when
    `USE_EU_NUMBER_FORMAT` is True, or Anglo-American (`1,234.56`) when False.
    """
    if val is None:
        return na_label
    try:
        v = float(val)
    except (TypeError, ValueError):
        return na_label
    if not math.isfinite(v):
        return na_label

    dec = max(0, int(decimals))
    if abs(v) < 0.5 * (10.0 ** (-dec)):
        v = 0.0

    sign = "+" if (signed and v >= 0.0) else ("-" if v < 0.0 else "")
    num_str = f"{abs(v):,.{dec}f}"
    if USE_EU_NUMBER_FORMAT:
        num_str = num_str.replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    return f"{sign}{num_str}"


def fmt_curr(
    val: Any,
    currency_code: str = "EUR",
    decimals: int = 0,
    signed: bool = False,
    html: bool = False,
    na_label: str = "N/A",
) -> str:
    """
    Formats a monetary value with leading sign before the currency symbol
    (e.g. `+€125.000`, `-ARS 4.500,50`) respecting `USE_EU_NUMBER_FORMAT`.
    """
    if val is None:
        return na_label
    try:
        v = float(val)
    except (TypeError, ValueError):
        return na_label
    if not math.isfinite(v):
        return na_label

    dec = max(0, int(decimals))
    if abs(v) < 0.5 * (10.0 ** (-dec)):
        v = 0.0

    pref = curr_prefix(currency_code, html=html)
    num_str = fmt_num(abs(v), decimals=dec, signed=False, na_label=na_label)
    if signed:
        sign = "+" if v >= 0.0 else "-"
        return f"{sign}{pref}{num_str}"
    if v < 0.0:
        return f"-{pref}{num_str}"
    return f"{pref}{num_str}"
