"""
========================================================================================
Synthetic Profile Visualizer (current_model/ui/tab1_consumption/synthetic/charts.py)
========================================================================================

Description:
------------
Generates interactive Plotly dark-themed visualizations:
  1. 24-Hour stacked load profile curves with custom channel colors and grid limit line.
  2. 365-Day full-year load profile timeseries (35,040 intervals) with interactive range slider.
  3. 24h x 365d Annual Load Heatmap displaying consumption intensity patterns.
"""

from typing import List, Optional
import numpy as np
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
        if not c.is_active:
            continue
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


def create_annual_synthetic_figure(
    df_year: pd.DataFrame,
    grid_limit_kw: Optional[float] = None
) -> go.Figure:
    """
    Constructs an interactive 365-day (35,040 points) time series figure with a range slider.
    """
    fig = go.Figure()

    if "timestamp" in df_year.columns and "Total_Demand_kW" in df_year.columns:
        fig.add_trace(
            go.Scatter(
                x=df_year["timestamp"],
                y=df_year["Total_Demand_kW"],
                mode="lines",
                name="Annual Total Demand (kW)",
                line=dict(color="#38BDF8", width=1.2),
                fill="tozeroy",
                fillcolor="rgba(56, 189, 248, 0.12)",
                hovertemplate="<b>Total Power</b>: %{y:.1f} kW<br>Time: %{x|%d %b %H:%M}<extra></extra>"
            )
        )

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
        title=dict(text="<b>Annual Load Profile Time Series (365 Days)</b>", font=dict(size=15, color="#F8FAFC")),
        xaxis=dict(
            title="Calendar Timeline",
            gridcolor="#1E293B",
            rangeslider=dict(visible=True, thickness=0.06),
            type="date"
        ),
        yaxis=dict(
            title="Active Power (kW)",
            rangemode="tozero",
            gridcolor="#1E293B"
        ),
        hovermode="x unified",
        margin=dict(l=40, r=20, t=50, b=40),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        height=450
    )

    return fig


def create_annual_heatmap_figure(df_year: pd.DataFrame) -> go.Figure:
    """
    Constructs a 2D Heatmap (Hour of Day vs. Day of Year) to visualize operating patterns.
    """
    fig = go.Figure()

    if "timestamp" not in df_year.columns or "Total_Demand_kW" not in df_year.columns:
        return fig

    # Reshape 35,040 intervals into a (96, 365) 2D matrix
    total_vals = df_year["Total_Demand_kW"].to_numpy()
    days_count = len(total_vals) // 96
    matrix_2d = total_vals[:days_count * 96].reshape((days_count, 96)).T  # shape (96, days_count)

    # Generate labels
    time_slots = [f"{h:02d}:{m:02d}" for h in range(24) for m in (0, 15, 30, 45)]
    unique_dates = df_year["timestamp"].dt.strftime("%d %b").iloc[::96].tolist()[:days_count]

    fig.add_trace(
        go.Heatmap(
            z=matrix_2d,
            x=unique_dates,
            y=time_slots,
            colorscale="Viridis",
            colorbar=dict(title="kW"),
            hovertemplate="Date: %{x}<br>Time: %{y}<br>Power: <b>%{z:.1f} kW</b><extra></extra>"
        )
    )

    fig.update_layout(
        template="plotly_dark",
        title=dict(text="<b>Annual Load Intensity Heatmap (24 Hours x 365 Days)</b>", font=dict(size=15, color="#F8FAFC")),
        xaxis=dict(title="Day of Year", nticks=12, gridcolor="#1E293B"),
        yaxis=dict(title="Time of Day", dtick=8, gridcolor="#1E293B"),
        margin=dict(l=40, r=20, t=50, b=40),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        height=380
    )

    return fig
