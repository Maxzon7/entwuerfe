"""
========================================================================================
UI Design System & Performance Theme (ui_theme.py)
Current Situation (Status Quo) Sandbox
========================================================================================
Supplies:
  - High-performance dark aesthetic tokens (deep slate, electric teal, violet, amber)
  - Google Fonts typography (Inter for UI, JetBrains Mono for financial figures)
  - Unified Plotly dark theme (currsit_dark)
  - Live 4-pillar unbundled invoice breakdown component
  - Strictly compliant with zero emoji rule (Streamlit :material/...: symbols exclusively)
========================================================================================
"""

from typing import Any, Optional, Dict, List
import streamlit as st
import plotly.graph_objects as go
import plotly.io as pio

# Custom Plotly Template Colorway
CURRSIT_COLORWAY = [
    "#00D2B4",  # Electric Teal (DSO / Primary)
    "#8B5CF6",  # Violet (Supplier / Commodity)
    "#F59E0B",  # Amber (Metering & Trafo)
    "#38BDF8",  # Sky Blue (Taxes / Levies)
    "#EC4899",  # Pink (Peak / Ratchet)
    "#10B981",  # Emerald (Green GvO / Flex)
]


def apply_currsit_theme() -> None:
    """Injects high-contrast dark mode CSS tokens and typography."""
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap');

        :root {
            --currsit-bg-base: #0B0F19;
            --currsit-bg-surface: #131B2E;
            --currsit-bg-card: #182238;
            --currsit-border: #23304A;
            --currsit-teal: #00D2B4;
            --currsit-violet: #8B5CF6;
            --currsit-amber: #F59E0B;
            --currsit-sky: #38BDF8;
            --currsit-text: #F1F5F9;
            --currsit-muted: #94A3B8;
        }

        /* Typography */
        html, body, [class*="css"] {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        }

        .mono-val {
            font-family: 'JetBrains Mono', monospace !important;
            font-variant-numeric: tabular-nums;
            font-weight: 600;
        }

        /* Hero Header */
        .currsit-hero {
            background: linear-gradient(135deg, #131B2E 0%, #182238 100%);
            border: 1px solid #23304A;
            border-radius: 12px;
            padding: 20px 24px;
            margin-bottom: 20px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
        }
        .currsit-hero h2 {
            margin: 0 0 6px 0;
            color: #F1F5F9;
            font-weight: 700;
            font-size: 1.5rem;
            letter-spacing: -0.5px;
        }
        .currsit-hero p {
            margin: 0;
            color: #94A3B8;
            font-size: 0.9rem;
        }

        /* Chip Badges */
        .chip-container {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 14px;
        }
        .chip {
            background: rgba(35, 48, 74, 0.6);
            border: 1px solid #23304A;
            border-radius: 6px;
            padding: 4px 10px;
            font-size: 0.8rem;
            color: #E2E8F0;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }
        .chip strong {
            color: #00D2B4;
        }

        /* Live Invoice Card */
        .invoice-card {
            background: #131B2E;
            border: 1px solid #23304A;
            border-radius: 10px;
            padding: 18px 20px;
            box-shadow: 0 4px 16px rgba(0,0,0,0.3);
            margin-bottom: 16px;
        }
        .invoice-header {
            font-size: 0.85rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.8px;
            color: #00D2B4;
            margin-bottom: 12px;
            border-bottom: 1px solid #23304A;
            padding-bottom: 8px;
        }
        .invoice-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 6px 0;
            font-size: 0.88rem;
            color: #CBD5E1;
            border-bottom: 1px solid rgba(35, 48, 74, 0.4);
        }
        .invoice-row.sub-item {
            padding-left: 12px;
            font-size: 0.82rem;
            color: #94A3B8;
        }
        .invoice-row.total {
            font-size: 1.05rem;
            font-weight: 700;
            color: #F8FAFC;
            border-top: 1px solid #00D2B4;
            border-bottom: none;
            padding-top: 10px;
            margin-top: 6px;
        }
        .invoice-row.gross {
            font-size: 0.95rem;
            font-weight: 600;
            color: #38BDF8;
            border-bottom: none;
            padding-top: 4px;
        }

        /* Metric Accent Cards */
        .metric-box {
            background: #182238;
            border: 1px solid #23304A;
            border-radius: 8px;
            padding: 14px 16px;
            margin-bottom: 10px;
        }
        .metric-label {
            font-size: 0.78rem;
            color: #94A3B8;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            font-weight: 600;
        }
        .metric-number {
            font-family: 'JetBrains Mono', monospace;
            font-size: 1.5rem;
            font-weight: 700;
            color: #F8FAFC;
            margin: 4px 0;
        }
        .metric-sub {
            font-size: 0.78rem;
            color: #64748B;
        }
        </style>
        """,
        unsafe_allow_html=True
    )


def configure_plotly_currsit_theme() -> None:
    """Configures and registers the unified Plotly dark theme."""
    currsit_template = go.layout.Template(
        layout=go.Layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            colorway=CURRSIT_COLORWAY,
            font=dict(family="Inter, sans-serif", color="#CBD5E1", size=12),
            xaxis=dict(
                gridcolor="#1E293B",
                zerolinecolor="#334155",
                linecolor="#334155",
                tickfont=dict(family="JetBrains Mono, monospace", size=11),
            ),
            yaxis=dict(
                gridcolor="#1E293B",
                zerolinecolor="#334155",
                linecolor="#334155",
                tickfont=dict(family="JetBrains Mono, monospace", size=11),
            ),
            legend=dict(
                bgcolor="rgba(19, 27, 46, 0.8)",
                bordercolor="#23304A",
                borderwidth=1,
                font=dict(size=11),
            ),
            hoverlabel=dict(
                bgcolor="#182238",
                bordercolor="#00D2B4",
                font=dict(family="JetBrains Mono, monospace", color="#F8FAFC", size=12),
            ),
        )
    )
    pio.templates["currsit_dark"] = currsit_template
    pio.templates.default = "currsit_dark"


def render_hero_banner(
    title: Optional[str] = None,
    subtitle: Optional[str] = None,
    badge_text: Optional[str] = None,
    icon: Optional[str] = None,
    source_label: Optional[str] = None,
    annual_kwh: Optional[float] = None,
    peak_kw: Optional[float] = None,
    contracted_kw: Optional[float] = None,
    dso_name: Optional[str] = None,
    supplier_name: Optional[str] = None,
    pricing_mode: Optional[str] = None,
    *args: Any,
    **kwargs: Any
) -> None:
    """
    Renders the executive hero banner adhering to the currsit dark theme.
    Supports both overview header mode (title, subtitle, badge_text, icon)
    and detailed metrics chips mode (source_label, annual_kwh, peak_kw, ...),
    with full backward compatibility for legacy positional arguments.
    """
    # Check if called with legacy positional arguments:
    # render_hero_banner(source_label, annual_kwh, peak_kw, contracted_kw, dso_name, supplier_name, pricing_mode)
    if isinstance(subtitle, (int, float)):
        source_label = title
        annual_kwh = float(subtitle)
        peak_kw = args[0] if len(args) > 0 else kwargs.get("peak_kw", 0.0)
        contracted_kw = args[1] if len(args) > 1 else kwargs.get("contracted_kw", 0.0)
        dso_name = args[2] if len(args) > 2 else kwargs.get("dso_name", "")
        supplier_name = args[3] if len(args) > 3 else kwargs.get("supplier_name", "")
        pricing_mode = args[4] if len(args) > 4 else kwargs.get("pricing_mode", "fixed")
        title = None
        subtitle = None

    # Resolve keyword arguments if passed under alternate names
    if not source_label and "source_label" in kwargs:
        source_label = kwargs["source_label"]
    if annual_kwh is None and "annual_kwh" in kwargs:
        annual_kwh = kwargs["annual_kwh"]
    if peak_kw is None and "peak_kw" in kwargs:
        peak_kw = kwargs["peak_kw"]
    if contracted_kw is None and "contracted_kw" in kwargs:
        contracted_kw = kwargs["contracted_kw"]
    if not dso_name and "dso_name" in kwargs:
        dso_name = kwargs["dso_name"]
    if not supplier_name and "supplier_name" in kwargs:
        supplier_name = kwargs["supplier_name"]
    if not pricing_mode and "pricing_mode" in kwargs:
        pricing_mode = kwargs["pricing_mode"]
    if not badge_text and "badge_text" in kwargs:
        badge_text = kwargs["badge_text"]

    effective_title = title or "Current Situation (Status Quo) Laboratory"
    effective_subtitle = (
        subtitle
        if subtitle is not None
        else "Dutch Commercial Large-Consumer Electricity Accounting (Grootverbruik &gt; 3&times;80A / Medium Voltage)"
    )

    badge_html = f'<span class="badge badge-teal" style="font-size: 0.75rem; vertical-align: middle; margin-left: 8px;">{badge_text}</span>' if badge_text else ""
    icon_html = f'<span style="color: #00D2B4; margin-right: 8px;">{icon}</span>' if icon else ""
    subtitle_html = f"<p>{effective_subtitle}</p>" if effective_subtitle else ""

    chips = []
    if source_label:
        chips.append(f'<div class="chip">:material/power: <span>Load: <strong>{source_label}</strong></span></div>')
    if annual_kwh is not None:
        chips.append(f'<div class="chip">:material/bolt: <span>Energy: <strong>{annual_kwh:,.0f} kWh</strong></span></div>')
    if peak_kw is not None:
        chips.append(f'<div class="chip">:material/speed: <span>Measured Peak: <strong>{peak_kw:,.1f} kW</strong></span></div>')
    if contracted_kw is not None:
        chips.append(f'<div class="chip">:material/grid_view: <span>Reserved GTV: <strong>{contracted_kw:,.1f} kW</strong></span></div>')
    if dso_name:
        chips.append(f'<div class="chip">:material/hub: <span>DSO: <strong>{dso_name}</strong></span></div>')
    if supplier_name:
        chips.append(f'<div class="chip">:material/storefront: <span>Supplier: <strong>{supplier_name}</strong></span></div>')
    if pricing_mode:
        chips.append(f'<div class="chip">:material/tune: <span>Mode: <strong>{pricing_mode.upper()}</strong></span></div>')

    chips_container_html = f'<div class="chip-container">{"".join(chips)}</div>' if chips else ""

    st.markdown(
        f"""
        <div class="currsit-hero">
            <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 6px;">
                <h2 style="margin: 0;">{icon_html}{effective_title}</h2>
                {badge_html}
            </div>
            {subtitle_html}
            {chips_container_html}
        </div>
        """,
        unsafe_allow_html=True
    )


def render_metric_card(
    title: str,
    value: str,
    subtext: str = "",
    badge: Optional[str] = None,
    icon: Optional[str] = None
) -> None:
    """Renders a styled KPI card adhering to the currsit dark theme."""
    badge_html = f'<span class="badge badge-teal">{badge}</span>' if badge else ""
    icon_html = f'<span style="color: #00D2B4; margin-right: 6px;">{icon}</span>' if icon else ""
    subtext_html = f'<div style="font-size: 0.78rem; color: #94A3B8; margin-top: 4px;">{subtext}</div>' if subtext else ""
    st.markdown(
        f"""
        <div class="kpi-card">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                <span class="label">{icon_html}{title}</span>
                {badge_html}
            </div>
            <div class="value">{value}</div>
            {subtext_html}
        </div>
        """,
        unsafe_allow_html=True
    )



def render_live_invoice_card(
    result: Any,
    period_title: str = "Annual Consolidated Statement"
) -> None:
    """
    Renders the live unbundled 4-pillar invoice card with the 5-component supplier breakdown.
    """
    total_net = result.total_status_quo_net
    total_gross = result.total_status_quo_gross
    total_vat = result.total_vat_amount
    blended_rate = result.blended_price_net_kwh

    dso_net = result.total_dso_net
    supp_net = result.total_supplier_net
    meter_net = result.total_metering_net
    trafo_net = result.total_trafo_net
    tax_net = result.total_taxes_net

    # Supplier 5 parts from result.config and records
    supplier_cfg = result.config.supplier
    comm_cost = sum(m.supplier.commodity_cost for m in result.monthly_records)
    markup_cost = sum(m.supplier.markup_cost for m in result.monthly_records)
    bal_cost = sum(m.supplier.balancing_cost for m in result.monthly_records)
    gvo_cost = sum(m.supplier.gvo_cost for m in result.monthly_records)
    base_cost = sum(m.supplier.supplier_base_fee for m in result.monthly_records)

    st.markdown(
        f"""
        <div class="invoice-card">
            <div class="invoice-header">:material/receipt_long: {period_title}</div>
            
            <!-- Pillar 1: Regulated DSO -->
            <div class="invoice-row">
                <span>1. Regulated DSO Transport (Netbeheer)</span>
                <span class="mono-val">€ {dso_net:,.2f}</span>
            </div>
            
            <!-- Pillar 2: Supplier 5 parts -->
            <div class="invoice-row">
                <span>2. Energy Supplier (Leverancier)</span>
                <span class="mono-val" style="color:#8B5CF6;">€ {supp_net:,.2f}</span>
            </div>
            <div class="invoice-row sub-item">
                <span>&bull; Wholesale Commodity Base</span>
                <span class="mono-val">€ {comm_cost:,.2f}</span>
            </div>
            <div class="invoice-row sub-item">
                <span>&bull; Retail Markup (Opslag)</span>
                <span class="mono-val">€ {markup_cost:,.2f}</span>
            </div>
            <div class="invoice-row sub-item">
                <span>&bull; Balancing Fee (Onbalanskosten)</span>
                <span class="mono-val">€ {bal_cost:,.2f}</span>
            </div>
            <div class="invoice-row sub-item">
                <span>&bull; Green Power Surcharge (GvO)</span>
                <span class="mono-val">€ {gvo_cost:,.2f}</span>
            </div>
            <div class="invoice-row sub-item">
                <span>&bull; Standing Fee (Vastrecht levering)</span>
                <span class="mono-val">€ {base_cost:,.2f}</span>
            </div>
            
            <!-- Pillar 3: Telemetry Metering -->
            <div class="invoice-row">
                <span>3. Certified Metering (Meetbedrijf EMV)</span>
                <span class="mono-val">€ {meter_net:,.2f}</span>
            </div>
            
            <!-- Pillar 4: Transformer Rental -->
            <div class="invoice-row">
                <span>4. Transformer Station Rental (Trafo)</span>
                <span class="mono-val" style="color:#F59E0B;">€ {trafo_net:,.2f}</span>
            </div>
            
            <!-- Statutory Taxes -->
            <div class="invoice-row">
                <span>5. Energiebelasting (Net of Rebate)</span>
                <span class="mono-val" style="color:#38BDF8;">€ {tax_net:,.2f}</span>
            </div>
            
            <!-- Total Net -->
            <div class="invoice-row total">
                <span>Total Net Expenditure</span>
                <span class="mono-val" style="color:#00D2B4;">€ {total_net:,.2f}</span>
            </div>
            
            <!-- VAT & Gross -->
            <div class="invoice-row gross">
                <span>+ 21% VAT (BTW)</span>
                <span class="mono-val">€ {total_vat:,.2f}</span>
            </div>
            <div class="invoice-row gross">
                <span>Total Gross Expenditure</span>
                <span class="mono-val">€ {total_gross:,.2f}</span>
            </div>
            <div class="invoice-row" style="border:none; padding-top:6px; font-size:0.82rem; color:#94A3B8;">
                <span>Effective Net Commodity Rate</span>
                <span class="mono-val" style="color:#00D2B4;">€ {blended_rate:.4f} / kWh</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )
