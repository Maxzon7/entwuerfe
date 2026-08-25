"""
========================================================================================
Contract Comparison Visualizer (current_model/ui/tab2_contract/comparison_charts.py)
========================================================================================

Description:
------------
Generates minimalist, professional Plotly dark-themed charts for side-by-side contract
and tariff benchmarking:
  1. Stacked Bar Chart: Cost Component Distribution per Contract (Energy, Capacity, Penalty, Taxes).
  2. Multi-Series Monthly Payment Curve: 12-Month comparison of billing trajectory across contracts.
  3. Effective Rate Benchmark Chart: Horizontal bar comparison of effective €/kWh price.
"""

from typing import List, Dict, Any, Optional
import plotly.graph_objects as go

COST_PALETTE: Dict[str, str] = {
    "Energy (Active)": "#38BDF8",        # Sky Blue
    "Capacity (Contracted)": "#F59E0B",  # Amber
    "Demand (Measured)": "#FB923C",      # Orange
    "Peak Penalty": "#EF4444",           # Red
    "Base Fee": "#8B5CF6",               # Violet
    "Reactive Power": "#EC4899",         # Pink
    "Taxes & Levies": "#10B981",         # Emerald
    "Other": "#94A3B8"                   # Slate
}

CONTRACT_COLORS = [
    "#38BDF8",  # Sky Blue
    "#10B981",  # Emerald Green
    "#F59E0B",  # Amber
    "#A855F7",  # Purple
    "#EC4899",  # Pink
    "#06B6D4",  # Cyan
    "#E11D48",  # Rose
    "#84CC16",  # Lime
]


def create_comparison_stacked_bar_figure(
    comparison_results: List[Dict[str, Any]],
    currency: str = "EUR"
) -> go.Figure:
    """
    Constructs a stacked bar chart showing the breakdown of cost components
    (Energy, Capacity, Fixed, Penalty, Taxes) for each evaluated contract.
    """
    fig = go.Figure()

    if not comparison_results:
        fig.update_layout(
            template="plotly_dark",
            annotations=[dict(text="No contract data to compare", showarrow=False, font=dict(size=14))]
        )
        return fig

    contract_names = [r["display_name"] for r in comparison_results]

    components = [
        ("Energy (Active)", [r["energy_cost"] for r in comparison_results], COST_PALETTE["Energy (Active)"]),
        ("Capacity (Contracted)", [r["capacity_cost"] for r in comparison_results], COST_PALETTE["Capacity (Contracted)"]),
        ("Demand (Measured)", [r["demand_cost"] for r in comparison_results], COST_PALETTE["Demand (Measured)"]),
        ("Base Fee", [r["base_fee"] for r in comparison_results], COST_PALETTE["Base Fee"]),
        ("Peak Penalty", [r["penalty_cost"] for r in comparison_results], COST_PALETTE["Peak Penalty"]),
        ("Reactive Power", [r["reactive_cost"] for r in comparison_results], COST_PALETTE["Reactive Power"]),
        ("Taxes & Levies", [r["taxes_cost"] for r in comparison_results], COST_PALETTE["Taxes & Levies"])
    ]

    for label, vals, color in components:
        if any(v > 0.001 for v in vals):
            fig.add_trace(
                go.Bar(
                    name=label,
                    x=contract_names,
                    y=vals,
                    marker=dict(color=color),
                    hovertemplate=f"<b>{label}</b>: %{{y:,.2f}} {currency}<extra></extra>"
                )
            )

    fig.update_layout(
        template="plotly_dark",
        barmode="stack",
        title=dict(
            text=f"<b>Total Cost Breakdown by Contract ({currency})</b>",
            font=dict(size=14, color="#F8FAFC"),
            x=0.02,
            y=0.96
        ),
        xaxis=dict(
            title="",
            tickfont=dict(size=11, color="#CBD5E1"),
            gridcolor="#1E293B"
        ),
        yaxis=dict(
            title=dict(text=f"Total Cost ({currency})", font=dict(size=12, color="#94A3B8")),
            tickfont=dict(size=11, color="#CBD5E1"),
            gridcolor="#1E293B"
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1.0,
            font=dict(size=10)
        ),
        margin=dict(l=20, r=20, t=60, b=40),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        height=390
    )

    return fig


def create_monthly_comparison_series_figure(
    comparison_results: List[Dict[str, Any]],
    currency: str = "EUR"
) -> go.Figure:
    """
    Constructs a multi-line comparison chart showing the 12-month payment trajectory
    across all selected contracts.
    """
    fig = go.Figure()

    if not comparison_results:
        return fig

    for idx, res in enumerate(comparison_results):
        series = res.get("monthly_series", [])
        if not series:
            continue

        months = [m.period_label for m in series]
        gross_totals = [m.total_gross for m in series]
        color = CONTRACT_COLORS[idx % len(CONTRACT_COLORS)]
        is_ref = res.get("is_reference", False)

        fig.add_trace(
            go.Scatter(
                x=months,
                y=gross_totals,
                mode="lines+markers",
                name=f"{'📌 ' if is_ref else ''}{res['display_name']}",
                line=dict(
                    color=color,
                    width=3 if is_ref else 2,
                    dash="solid" if is_ref else "dot"
                ),
                marker=dict(size=6),
                hovertemplate=f"<b>{res['display_name']}</b><br>%{{x}}: %{{y:,.2f}} {currency}<extra></extra>"
            )
        )

    fig.update_layout(
        template="plotly_dark",
        title=dict(
            text=f"<b>Monthly Billing Trajectory Comparison ({currency})</b>",
            font=dict(size=14, color="#F8FAFC"),
            x=0.02,
            y=0.96
        ),
        xaxis=dict(
            title="",
            tickfont=dict(size=11, color="#CBD5E1"),
            gridcolor="#1E293B"
        ),
        yaxis=dict(
            title=dict(text=f"Monthly Gross Invoice ({currency})", font=dict(size=12, color="#94A3B8")),
            tickfont=dict(size=11, color="#CBD5E1"),
            gridcolor="#1E293B"
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1.0,
            font=dict(size=10)
        ),
        margin=dict(l=20, r=20, t=60, b=40),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        height=390
    )

    return fig


def create_effective_rate_bar_figure(
    comparison_results: List[Dict[str, Any]],
    currency: str = "EUR"
) -> go.Figure:
    """
    Constructs a horizontal bar chart showing the effective cost per kWh (€/kWh)
    sorted from cheapest to most expensive.
    """
    fig = go.Figure()

    if not comparison_results:
        return fig

    # Sort results by effective rate ascending (cheapest on top)
    sorted_res = sorted(comparison_results, key=lambda x: x["effective_rate_kwh"], reverse=True)

    names = [r["display_name"] for r in sorted_res]
    rates = [r["effective_rate_kwh"] for r in sorted_res]
    colors = []

    for r in sorted_res:
        if r.get("is_winner", False):
            colors.append("#10B981")  # Emerald for cheapest
        elif r.get("is_reference", False):
            colors.append("#38BDF8")  # Sky blue for reference
        else:
            colors.append("#64748B")  # Slate for others

    fig.add_trace(
        go.Bar(
            y=names,
            x=rates,
            orientation="h",
            marker=dict(color=colors, line=dict(color="#0B0F19", width=1.5)),
            text=[f"{rate:.4f} {currency}/kWh" for rate in rates],
            textposition="auto",
            hovertemplate=f"<b>%{{y}}</b><br>Effective Rate: %{{x:.4f}} {currency}/kWh<extra></extra>"
        )
    )

    fig.update_layout(
        template="plotly_dark",
        title=dict(
            text=f"<b>Effective Electricity Cost Benchmark ({currency}/kWh)</b>",
            font=dict(size=14, color="#F8FAFC"),
            x=0.02,
            y=0.96
        ),
        xaxis=dict(
            title=dict(text=f"Effective Rate ({currency}/kWh)", font=dict(size=12, color="#94A3B8")),
            tickfont=dict(size=11, color="#CBD5E1"),
            gridcolor="#1E293B"
        ),
        yaxis=dict(
            title="",
            tickfont=dict(size=11, color="#CBD5E1"),
            autorange=True
        ),
        margin=dict(l=20, r=20, t=50, b=40),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        height=max(260, len(names) * 45)
    )

    return fig
