"""
========================================================================================
Master Scenario Comparison Charts (current_model/ui/tab_comparison/charts.py)
========================================================================================

Description:
------------
Provides interactive Plotly visualization figures for the Master Scenario Comparison:
  - 15-Year Multi-Scenario Cumulative Cost Trajectory Curves (Break-Even Analysis)
  - CAPEX vs. OPEX Capital Shift Grouped Bar Chart
  - Autarky & Self-Consumption Benchmark Bar Chart
"""

from typing import List, Dict, Any, Optional
import plotly.graph_objects as go
import numpy as np


def create_multi_scenario_cumulative_cost_figure(
    scenarios_data: List[Dict[str, Any]],
    baseline_series: Optional[List[float]] = None,
    currency: str = "EUR"
) -> go.Figure:
    """
    Creates a multi-line Plotly figure illustrating the 15-year cumulative cost development
    across the Base Scenario (Status Quo) and all active Sub-Scenarios.
    """
    fig = go.Figure()
    years = list(range(0, 16))

    # 1. Base Scenario (Status Quo Line)
    if baseline_series and len(baseline_series) >= 16:
        base_y = baseline_series[:16]
    else:
        # Default extrapolation if not fully simulated
        base_annual = 150000.0
        base_y = [0.0]
        cum = 0.0
        for y in range(1, 16):
            cum += base_annual * ((1.0 + 0.03) ** (y - 1))
            base_y.append(cum)

    fig.add_trace(go.Scatter(
        x=years,
        y=base_y,
        mode="lines+markers",
        name="Status Quo (Base Utility Line)",
        line=dict(color="#94A3B8", width=3, dash="dash"),
        marker=dict(size=6),
        hovertemplate="<b>Status Quo</b><br>Year %{x}: %{y:,.0f} " + currency + "<extra></extra>"
    ))

    # 2. Sub-Scenarios
    palette = ["#2563EB", "#059669", "#D97706", "#DC2626", "#7C3AED", "#DB2777", "#0891B2"]
    for idx, sc in enumerate(scenarios_data):
        name = sc.get("name", f"Sub-Scenario {idx+1}")
        color = sc.get("color", palette[idx % len(palette)])
        series = sc.get("cumulative_costs")

        if not series or len(series) < 16:
            # Synthetic approximation from CAPEX + residual OPEX
            capex = sc.get("capex", 0.0)
            opex = sc.get("annual_opex", 50000.0)
            series = [capex]
            cum = capex
            for y in range(1, 16):
                cum += opex * ((1.0 + 0.03) ** (y - 1))
                series.append(cum)

        fig.add_trace(go.Scatter(
            x=years,
            y=series[:16],
            mode="lines+markers",
            name=name,
            line=dict(color=color, width=3),
            marker=dict(size=6),
            hovertemplate=f"<b>{name}</b><br>Year %{{x}}: %{{y:,.0f}} {currency}<extra></extra>"
        ))

    fig.update_layout(
        title=dict(
            text=f"<b>15-Year Cumulative Cost Trajectories & Break-Even Analysis ({currency})</b>",
            font=dict(size=15, color="#F8FAFC")
        ),
        xaxis=dict(
            title="Analysis Horizon (Years)",
            dtick=1,
            gridcolor="#334155",
            showgrid=True
        ),
        yaxis=dict(
            title=f"Cumulative Expenditure ({currency})",
            gridcolor="#334155",
            showgrid=True,
            tickformat=",.0f"
        ),
        paper_bgcolor="#1E293B",
        plot_bgcolor="#0F172A",
        font=dict(color="#E2E8F0"),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            bgcolor="rgba(15, 23, 42, 0.8)",
            bordercolor="#334155",
            borderwidth=1
        ),
        margin=dict(l=60, r=30, t=80, b=50),
        hovermode="x unified"
    )

    return fig


def create_capex_opex_breakdown_figure(
    scenarios_data: List[Dict[str, Any]],
    currency: str = "EUR"
) -> go.Figure:
    """
    Creates a stacked bar chart illustrating Turn-Key CAPEX vs 15-Year OPEX/Utility Energy Costs.
    """
    names = [s.get("name", "Scenario") for s in scenarios_data]
    capex_vals = [s.get("capex", 0.0) for s in scenarios_data]
    opex_vals = [s.get("total_15y_opex", 0.0) for s in scenarios_data]

    fig = go.Figure()

    fig.add_trace(go.Bar(
        name="Turn-Key Initial CAPEX",
        x=names,
        y=capex_vals,
        marker_color="#38BDF8",
        hovertemplate="CAPEX: %{y:,.0f} " + currency + "<extra></extra>"
    ))

    fig.add_trace(go.Bar(
        name="15-Year OPEX & Residual Utility Cost",
        x=names,
        y=opex_vals,
        marker_color="#F59E0B",
        hovertemplate="15-Yr OPEX: %{y:,.0f} " + currency + "<extra></extra>"
    ))

    fig.update_layout(
        barmode="stack",
        title=dict(
            text=f"<b>Total Cost of Ownership (TCO) Structure: CAPEX vs. OPEX ({currency})</b>",
            font=dict(size=15, color="#F8FAFC")
        ),
        xaxis=dict(gridcolor="#334155"),
        yaxis=dict(
            title=f"15-Year Total Expense ({currency})",
            gridcolor="#334155",
            tickformat=",.0f"
        ),
        paper_bgcolor="#1E293B",
        plot_bgcolor="#0F172A",
        font=dict(color="#E2E8F0"),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            bgcolor="rgba(15, 23, 42, 0.8)"
        ),
        margin=dict(l=60, r=30, t=80, b=50)
    )

    return fig


def create_autarky_payback_figure(
    scenarios_data: List[Dict[str, Any]]
) -> go.Figure:
    """
    Creates a grouped bar chart comparing Solar Autarky (%) and Simple Payback Period (Years).
    """
    names = [s.get("name", "Scenario") for s in scenarios_data]
    autarky_vals = [s.get("autarky_pct", 0.0) for s in scenarios_data]
    payback_vals = [s.get("payback_years", 0.0) for s in scenarios_data]

    fig = go.Figure()

    fig.add_trace(go.Bar(
        name="Solar Autarky Degree (%)",
        x=names,
        y=autarky_vals,
        marker_color="#10B981",
        yaxis="y",
        hovertemplate="Autarky: %{y:.1f}%<extra></extra>"
    ))

    fig.add_trace(go.Bar(
        name="Simple Payback (Years)",
        x=names,
        y=payback_vals,
        marker_color="#818CF8",
        yaxis="y2",
        hovertemplate="Payback: %{y:.1f} Yrs<extra></extra>"
    ))

    fig.update_layout(
        title=dict(
            text="<b>Autarky Degree (%) vs. Payback Horizon (Years)</b>",
            font=dict(size=15, color="#F8FAFC")
        ),
        xaxis=dict(gridcolor="#334155"),
        yaxis=dict(
            title="Autarky Degree (%)",
            gridcolor="#334155",
            range=[0, 100]
        ),
        yaxis2=dict(
            title="Payback Period (Years)",
            overlaying="y",
            side="right",
            showgrid=False
        ),
        paper_bgcolor="#1E293B",
        plot_bgcolor="#0F172A",
        font=dict(color="#E2E8F0"),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            bgcolor="rgba(15, 23, 42, 0.8)"
        ),
        margin=dict(l=60, r=60, t=80, b=50)
    )

    return fig
