"""
========================================================================================
Synthetic Profile Visualizer (current_model/ui/synthetic/charts.py)
========================================================================================

Description:
------------
Generates interactive Plotly dark-themed stacked load profile charts with
custom channel colors and horizontal grid capacity limit line.
"""

from typing import List, Optional
import pandas as pd
import plotly.graph_objects as go
from current_model.models.load_component import SimpleConsumer

COLOR_PALETTE = [
    "#3B82F6", "#10B981", "#F59E0B", "#EC4899",
    "#8B5CF6", "#14B8A6", "#F97316", "#06B6D4", "#84CC16"
]


def create_synthetic_profile_figure(
    df_day: pd.DataFrame,
    consumers: List[SimpleConsumer],
    grid_limit_kw: Optional[float] = None
) -> go.Figure:
    """
    Constructs a stacked area Plotly figure for 24-hour synthetic profiles.
    """
    fig = go.Figure()

    for idx, c in enumerate(consumers):
        color = COLOR_PALETTE[idx % len(COLOR_PALETTE)]
        if c.name in df_day.columns:
            fig.add_trace(
                go.Scatter(
                    x=df_day["time"],
                    y=df_day[c.name],
                    mode="lines",
                    name=c.name,
                    stackgroup="one",
                    line=dict(width=1.0, color=color),
                    hovertemplate=f"<b>{c.name}</b>: %{{y:.1f}} kW<extra></extra>"
                )
            )

    # Total grid demand curve (White thick line)
    if "Total_kW" in df_day.columns:
        fig.add_trace(
            go.Scatter(
                x=df_day["time"],
                y=df_day["Total_kW"],
                mode="lines",
                name="Total Grid Demand",
                line=dict(color="#FFFFFF", width=3.0),
                hovertemplate="<b>Total Demand</b>: %{y:.1f} kW at %{x}<extra></extra>"
            )
        )

    # Grid limit horizontal line
    if grid_limit_kw is not None and grid_limit_kw > 0:
        fig.add_hline(
            y=grid_limit_kw,
            line_dash="dash",
            line_color="#f43f5e",
            line_width=2,
            annotation_text=f"Max Grid Limit ({grid_limit_kw:.1f} kW)",
            annotation_position="top right"
        )

    fig.update_layout(
        template="plotly_dark",
        xaxis=dict(title="Time of Day (HH:MM)", tickmode="linear", dtick=8, gridcolor="#1E293B"),
        yaxis=dict(title="Active Electrical Power (kW)", rangemode="tozero", gridcolor="#1E293B"),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=-0.28, xanchor="center", x=0.5),
        margin=dict(l=40, r=20, t=30, b=80),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        height=420
    )

    return fig
