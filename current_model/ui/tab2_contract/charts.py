"""
========================================================================================
Cost Structure & Financial Visualizer (current_model/ui/tab2_contract/charts.py)
========================================================================================

Description:
------------
Generates minimalist, professional Plotly dark-themed Donut charts visualizing
the monthly electricity cost distribution across Energy, Capacity, Base Fees, and Taxes.
"""

from typing import Optional
import plotly.graph_objects as go
from current_model.models.financial import FinancialCostBreakdown

COST_PALETTE = [
    "#38BDF8",  # Sky Blue - Energy
    "#F59E0B",  # Amber - Capacity
    "#EF4444",  # Red - Peak Penalty
    "#8B5CF6",  # Violet - Base Fee
    "#10B981",  # Emerald - Taxes & Levies
    "#64748B"   # Slate - Other
]


def create_cost_donut_figure(breakdown: FinancialCostBreakdown) -> go.Figure:
    """
    Constructs a clean, modern Donut chart displaying monthly cost distribution.
    """
    labels = []
    values = []

    if breakdown.energy_cost_monthly > 0:
        labels.append("Active Energy")
        values.append(breakdown.energy_cost_monthly)

    if breakdown.capacity_cost_monthly > 0:
        labels.append("Capacity Charge")
        values.append(breakdown.capacity_cost_monthly)

    if breakdown.penalty_cost_monthly > 0:
        labels.append("Peak Penalty")
        values.append(breakdown.penalty_cost_monthly)

    if breakdown.base_fee_monthly > 0:
        labels.append("Base Fee")
        values.append(breakdown.base_fee_monthly)

    if breakdown.total_taxes_monthly > 0:
        labels.append("Taxes & Levies")
        values.append(breakdown.total_taxes_monthly)

    if not values:
        labels = ["No Cost Data"]
        values = [1.0]

    currency = breakdown.currency

    fig = go.Figure(
        data=[
            go.Pie(
                labels=labels,
                values=values,
                hole=0.55,
                textinfo="label+percent",
                marker=dict(colors=COST_PALETTE[:len(labels)]),
                hovertemplate=f"<b>%{{label}}</b><br>Monthly: %{{value:,.2f}} {currency}<br>Share: %{{percent}}<extra></extra>"
            )
        ]
    )

    fig.update_layout(
        template="plotly_dark",
        title=dict(
            text="<b>Monthly Cost Distribution</b>",
            font=dict(size=15, color="#F8FAFC")
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.15,
            xanchor="center",
            x=0.5
        ),
        margin=dict(l=20, r=20, t=40, b=30),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        height=320
    )

    return fig
