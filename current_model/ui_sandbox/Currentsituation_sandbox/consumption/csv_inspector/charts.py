"""
========================================================================================
CSV Load Profile Visualizer (current_model/ui/tab1_consumption/csv_inspector/charts.py)
========================================================================================

Description:
------------
Builds high-contrast, interactive load profile time series figures with sub-meters,
total demand curve, peak annotations, grid limit line, and range sliders.
"""

from typing import List, Optional
import pandas as pd
import plotly.graph_objects as go


def create_csv_inspector_figure(
    df_clean: pd.DataFrame,
    file_name: str,
    selected_power_cols: List[str],
    total_col: str = "Total_Demand_kW",
    peak_kw: Optional[float] = None,
    grid_limit_kw: Optional[float] = None
) -> go.Figure:
    """
    Constructs an interactive dark-theme Plotly line chart with optional grid limit line.
    """
    fig = go.Figure()

    if df_clean.empty or total_col not in df_clean.columns:
        fig.update_layout(
            template="plotly_dark",
            title="No data available to display",
            plot_bgcolor="#0B0F19",
            paper_bgcolor="#0B0F19"
        )
        return fig

    palette = ["#38BDF8", "#10B981", "#F59E0B", "#EC4899", "#8B5CF6", "#14B8A6"]

    # 1. Plot individual sub-meter measurement lines (if multiple selected)
    if len(selected_power_cols) > 1:
        for idx, col_name in enumerate(selected_power_cols):
            if col_name in df_clean.columns:
                fig.add_trace(
                    go.Scatter(
                        x=df_clean["timestamp"],
                        y=df_clean[col_name],
                        mode="lines",
                        name=col_name,
                        connectgaps=False,
                        line=dict(width=1.0, color=palette[idx % len(palette)]),
                        hovertemplate=f"<b>{col_name}</b>: %{{y:.2f}} kW<extra></extra>"
                    )
                )

    # 2. Main Total Demand Trace (Solid White Line)
    fig.add_trace(
        go.Scatter(
            x=df_clean["timestamp"],
            y=df_clean[total_col],
            mode="lines",
            name="Total Grid Demand (kW)",
            connectgaps=False,
            line=dict(color="#FFFFFF", width=2.0),
            fill="tozeroy" if len(selected_power_cols) == 1 else "none",
            fillcolor="rgba(56, 189, 248, 0.15)",
            hovertemplate="<b>Total Power</b>: %{y:.2f} kW<br>Time: %{x}<extra></extra>"
        )
    )

    # 3. Grid Limit Line
    if grid_limit_kw and grid_limit_kw > 0:
        fig.add_hline(
            y=grid_limit_kw,
            line_dash="dash",
            line_color="#f43f5e",
            line_width=2,
            annotation_text=f"Max Grid Limit ({grid_limit_kw:.1f} kW)",
            annotation_position="top right"
        )

    # 4. Peak Annotation Marker
    if peak_kw is None:
        peak_kw = float(df_clean[total_col].max())

    peak_idx = df_clean[total_col].idxmax()
    peak_time = df_clean.loc[peak_idx, "timestamp"]

    fig.add_annotation(
        x=peak_time,
        y=peak_kw,
        text=f"Peak: {peak_kw:.1f} kW",
        showarrow=True,
        arrowhead=2,
        arrowcolor="#EF4444",
        font=dict(color="#F87171", size=11, family="Arial Black"),
        bgcolor="rgba(15, 23, 42, 0.9)",
        bordercolor="#EF4444",
        borderwidth=1.5,
        borderpad=4
    )

    # 5. Dark Theme Layout
    fig.update_layout(
        template="plotly_dark",
        title=dict(text=f"<b>Load Profile: {file_name}</b>", font=dict(size=16, color="#F8FAFC")),
        xaxis=dict(
            title="Timestamp",
            gridcolor="#1E293B",
            rangeslider=dict(visible=True, thickness=0.06),
            type="date"
        ),
        yaxis=dict(
            title="Active Electrical Power (kW)",
            rangemode="tozero",
            gridcolor="#1E293B"
        ),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=40, r=20, t=50, b=40),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        height=470
    )

    return fig


def create_monthly_load_breakdown_figure(df_monthly: pd.DataFrame) -> go.Figure:
    """
    Constructs an interactive dark-theme Plotly figure showing monthly total energy consumption (MWh)
    and monthly peak demand (kW) for the standardized 365-day annual baseline.
    """
    fig = go.Figure()

    if df_monthly.empty:
        fig.update_layout(
            template="plotly_dark",
            title="No monthly data available",
            plot_bgcolor="#0B0F19",
            paper_bgcolor="#0B0F19"
        )
        return fig

    months = df_monthly["Month"]
    energy_mwh = df_monthly["Energy_MWh"]
    peak_kw = df_monthly["Peak_Demand_kW"]

    # 1. Bar Chart: Monthly Total Energy (MWh)
    fig.add_trace(
        go.Bar(
            x=months,
            y=energy_mwh,
            name="Monthly Energy (MWh)",
            marker=dict(
                color="#0284C7",
                line=dict(color="#38BDF8", width=1.5)
            ),
            hovertemplate="<b>%{x}</b><br>Energy: <b>%{y:,.1f} MWh</b><extra></extra>",
            yaxis="y"
        )
    )

    # 2. Line Chart: Monthly Peak Power (kW) on Secondary Y-Axis
    fig.add_trace(
        go.Scatter(
            x=months,
            y=peak_kw,
            name="Monthly Peak Demand (kW)",
            mode="lines+markers",
            marker=dict(size=8, color="#F59E0B"),
            line=dict(color="#F59E0B", width=2.5),
            hovertemplate="<b>%{x}</b><br>Peak Power: <b>%{y:,.1f} kW</b><extra></extra>",
            yaxis="y2"
        )
    )

    fig.update_layout(
        template="plotly_dark",
        title=dict(text="<b>Annual 12-Month Baseline Distribution (Energy & Peak Demand)</b>", font=dict(size=15, color="#F8FAFC")),
        xaxis=dict(
            title="Month",
            gridcolor="#1E293B"
        ),
        yaxis=dict(
            title="Energy Consumption (MWh)",
            rangemode="tozero",
            gridcolor="#1E293B"
        ),
        yaxis2=dict(
            title="Peak Demand (kW)",
            rangemode="tozero",
            overlaying="y",
            side="right",
            gridcolor="rgba(0,0,0,0)",
            showgrid=False
        ),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=40, r=40, t=50, b=30),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        height=360
    )

    return fig


def create_365d_baseline_figure(
    df_365: pd.DataFrame,
    total_col: str = "Total_Demand_kW",
    peak_kw: Optional[float] = None
) -> go.Figure:
    """
    Constructs an interactive dark-theme Plotly line chart displaying the exact 365-day (8,760-hour)
    standardized baseline profile at full 15-minute resolution with range slider.
    """
    fig = go.Figure()

    if df_365.empty or total_col not in df_365.columns:
        fig.update_layout(
            template="plotly_dark",
            title="No 365-day baseline data available to display",
            plot_bgcolor="#0B0F19",
            paper_bgcolor="#0B0F19"
        )
        return fig

    # 1. 15-Minute Load Curve Trace
    fig.add_trace(
        go.Scatter(
            x=df_365["timestamp"] if "timestamp" in df_365.columns else list(range(len(df_365))),
            y=df_365[total_col],
            mode="lines",
            name="365-Day Baseline Load (kW)",
            connectgaps=False,
            line=dict(color="#38BDF8", width=1.5),
            fill="tozeroy",
            fillcolor="rgba(56, 189, 248, 0.10)",
            hovertemplate="<b>Demand</b>: %{y:.2f} kW<br>Time: %{x|%d %b %Y %H:%M}<extra></extra>" if "timestamp" in df_365.columns else "<b>Demand</b>: %{y:.2f} kW<extra></extra>"
        )
    )

    # 2. Peak Power Annotation
    if peak_kw is None:
        peak_kw = float(df_365[total_col].max())

    if "timestamp" in df_365.columns and not df_365.empty:
        peak_idx = df_365[total_col].idxmax()
        peak_time = df_365.loc[peak_idx, "timestamp"]
        fig.add_annotation(
            x=peak_time,
            y=peak_kw,
            text=f"Annual Peak: {peak_kw:.1f} kW",
            showarrow=True,
            arrowhead=2,
            arrowcolor="#EF4444",
            font=dict(color="#F87171", size=11, family="Arial Black"),
            bgcolor="rgba(15, 23, 42, 0.9)",
            bordercolor="#EF4444",
            borderwidth=1.5,
            borderpad=4
        )

    # 3. Layout Configuration
    fig.update_layout(
        template="plotly_dark",
        title=dict(
            text="<b>Standardized 365-Day Simulation Baseline (15-Minute Resolution — 35,040 Intervals)</b>",
            font=dict(size=15, color="#F8FAFC")
        ),
        xaxis=dict(
            title="Calendar Timeline (Year 1 Benchmark)",
            gridcolor="#1E293B",
            rangeslider=dict(visible=True, thickness=0.06),
            type="date" if "timestamp" in df_365.columns else "linear"
        ),
        yaxis=dict(
            title="Active Electrical Power (kW)",
            rangemode="tozero",
            gridcolor="#1E293B"
        ),
        hovermode="x unified",
        margin=dict(l=40, r=20, t=50, b=40),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        height=420
    )

    return fig
