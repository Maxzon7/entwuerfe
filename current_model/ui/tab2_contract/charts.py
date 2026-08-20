"""
========================================================================================
Cost Structure & Financial Visualizer (current_model/ui/tab2_contract/charts.py)
========================================================================================

Description:
------------
Generates minimalist, professional Plotly dark-themed charts:
  1. Donut chart visualizing monthly cost distribution across all line item categories.
  2. Stacked Bar chart visualizing monthly payment timeseries (Zahlungsreihe) across full duration.
"""

from typing import Optional, List, Dict
import plotly.graph_objects as go
from current_model.models.financial import FinancialCostBreakdown, MonthlyPaymentRecord

COST_PALETTE: Dict[str, str] = {
    "Energy (Active)": "#38BDF8",       # Sky Blue
    "Capacity (Contracted)": "#F59E0B",  # Amber
    "Demand (Measured)": "#FB923C",      # Orange
    "Peak Penalty": "#EF4444",          # Red
    "Base Fee": "#8B5CF6",              # Violet
    "Taxes & Levies": "#10B981",        # Emerald
    "Other": "#94A3B8"                  # Slate
}


def create_cost_donut_figure(breakdown: FinancialCostBreakdown) -> go.Figure:
    """
    Constructs a clean, modern Donut chart displaying monthly cost distribution across all line items.
    """
    category_totals: Dict[str, float] = {}
    for item in breakdown.line_items:
        cat = item.category
        val = item.cost_monthly if breakdown.duration_days > 35 else item.cost_period
        if val > 0:
            category_totals[cat] = category_totals.get(cat, 0.0) + val

    labels = list(category_totals.keys())
    values = list(category_totals.values())
    colors = [COST_PALETTE.get(cat, COST_PALETTE["Other"]) for cat in labels]

    if not values:
        labels = ["No Cost Data"]
        values = [1.0]
        colors = ["#64748B"]

    currency = breakdown.currency

    fig = go.Figure(
        data=[
            go.Pie(
                labels=labels,
                values=values,
                hole=0.55,
                textinfo="label+percent",
                marker=dict(colors=colors),
                hovertemplate=f"<b>%{{label}}</b><br>Amount: %{{value:,.2f}} {currency}<br>Share: %{{percent}}<extra></extra>"
            )
        ]
    )

    fig.update_layout(
        template="plotly_dark",
        title=dict(
            text="<b>Cost Component Distribution</b>",
            font=dict(size=14, color="#F8FAFC")
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.18,
            xanchor="center",
            x=0.5
        ),
        margin=dict(l=20, r=20, t=35, b=25),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        height=300
    )

    return fig


def create_monthly_payment_series_figure(
    breakdown: FinancialCostBreakdown,
    highlight_month: Optional[str] = None
) -> go.Figure:
    """
    Constructs an interactive stacked bar chart visualizing monthly payment timeseries across full duration.
    """
    fig = go.Figure()
    currency = breakdown.currency

    if not breakdown.monthly_series:
        fig.update_layout(
            template="plotly_dark",
            title="No monthly payment data available",
            plot_bgcolor="#0B0F19",
            paper_bgcolor="#0B0F19"
        )
        return fig

    months = [m.period_label for m in breakdown.monthly_series]
    energy_costs = [m.energy_cost_net for m in breakdown.monthly_series]
    capacity_costs = [m.capacity_cost_net for m in breakdown.monthly_series]
    penalty_costs = [m.penalty_cost_net for m in breakdown.monthly_series]
    base_fees = [m.base_fee_net for m in breakdown.monthly_series]
    taxes = [m.taxes_and_levies for m in breakdown.monthly_series]
    gross_totals = [m.total_gross for m in breakdown.monthly_series]

    # Stacked Bars
    fig.add_trace(
        go.Bar(
            x=months,
            y=energy_costs,
            name="Active Energy",
            marker_color=COST_PALETTE["Energy (Active)"],
            hovertemplate=f"<b>Active Energy</b>: %{{y:,.2f}} {currency}<extra></extra>"
        )
    )

    fig.add_trace(
        go.Bar(
            x=months,
            y=capacity_costs,
            name="Capacity Charge",
            marker_color=COST_PALETTE["Capacity (Contracted)"],
            hovertemplate=f"<b>Capacity</b>: %{{y:,.2f}} {currency}<extra></extra>"
        )
    )

    if any(p > 0 for p in penalty_costs):
        fig.add_trace(
            go.Bar(
                x=months,
                y=penalty_costs,
                name="Peak Penalty",
                marker_color=COST_PALETTE["Peak Penalty"],
                hovertemplate=f"<b>Penalty</b>: %{{y:,.2f}} {currency}<extra></extra>"
            )
        )

    fig.add_trace(
        go.Bar(
            x=months,
            y=base_fees,
            name="Base Fee",
            marker_color=COST_PALETTE["Base Fee"],
            hovertemplate=f"<b>Base Fee</b>: %{{y:,.2f}} {currency}<extra></extra>"
        )
    )

    fig.add_trace(
        go.Bar(
            x=months,
            y=taxes,
            name="Taxes & Levies",
            marker_color=COST_PALETTE["Taxes & Levies"],
            hovertemplate=f"<b>Taxes</b>: %{{y:,.2f}} {currency}<extra></extra>"
        )
    )

    # Line trace for Total Gross Cost
    fig.add_trace(
        go.Scatter(
            x=months,
            y=gross_totals,
            mode="lines+markers",
            name="Total Gross Invoice",
            line=dict(color="#FFFFFF", width=2.5),
            marker=dict(size=6, color="#FFFFFF"),
            hovertemplate=f"<b>Total Gross</b>: %{{y:,.2f}} {currency}<extra></extra>"
        )
    )

    fig.update_layout(
        template="plotly_dark",
        barmode="stack",
        title=dict(
            text="<b>Monthly Payment Schedule across Duration (Zahlungsreihe)</b>",
            font=dict(size=15, color="#F8FAFC")
        ),
        xaxis=dict(
            title="Billing Period",
            gridcolor="#1E293B"
        ),
        yaxis=dict(
            title=f"Total Invoice Amount ({currency})",
            gridcolor="#1E293B",
            rangemode="tozero"
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
        margin=dict(l=40, r=20, t=60, b=40),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        height=380
    )

    if highlight_month and highlight_month in months:
        fig.add_vrect(
            x0=months.index(highlight_month) - 0.4,
            x1=months.index(highlight_month) + 0.4,
            fillcolor="#38BDF8",
            opacity=0.15,
            line_width=2,
            line_color="#38BDF8",
            annotation_text=f"Selected: {highlight_month}",
            annotation_position="top left",
            annotation_font_color="#38BDF8"
        )

    return fig
