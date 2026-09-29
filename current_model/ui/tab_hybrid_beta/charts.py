"""
========================================================================================
Solar + BESS Hybrid Charts Suite (current_model/ui/tab_hybrid_beta/charts.py)
========================================================================================

Description:
------------
Plotly visualization suite for the isolated Solar + BESS (Beta) module:
  1. 15-Minute Hybrid Dispatch Timeseries (Load, Solar, Direct PV, BESS Charge/Discharge, Net Grid).
  2. Battery State of Charge (SoC) Envelope & Utilization.
  3. Monthly Energy Balance Stacked Bar Chart.
  4. Load Duration Curve & Peak Reduction Comparison.
"""

from typing import List, Dict, Any, Optional
import numpy as np
import pandas as pd
import plotly.graph_objects as go


def create_hybrid_dispatch_chart(
    df_dispatch: pd.DataFrame,
    target_cap_kw: float,
    days_to_show: Optional[int] = None
) -> go.Figure:
    """
    Renders 15-minute electrical dispatch comparing:
      - Facility Demand (Baseline)
      - Solar PV Generation
      - Direct Solar Self-Consumption
      - BESS Charge from PV
      - BESS Discharge
      - Net Grid Import & Export
      - Grid Connection Limit / Target Cap
    """
    fig = go.Figure()
    total_steps = len(df_dispatch)
    total_days = total_steps * 0.25 / 24.0

    if days_to_show is None or (days_to_show * 96) >= total_steps:
        steps_to_show = total_steps
        title_text = f"<b>15-Minute Hybrid Dispatch: Solar PV + BESS ({total_days:.0f} Days / {total_steps:,} Intervals)</b>"
    else:
        steps_to_show = min(total_steps, days_to_show * 96)
        title_text = f"<b>15-Minute Hybrid Dispatch: Solar PV + BESS ({days_to_show} Days Sample)</b>"

    df_slice = df_dispatch.iloc[:steps_to_show].copy()
    x_axis = df_slice["timestamp"] if "timestamp" in df_slice.columns else np.arange(steps_to_show)

    scatter_cls = go.Scattergl if steps_to_show > 4000 else go.Scatter

    # 1. Baseline Facility Load (Dotted Gray Line)
    fig.add_trace(scatter_cls(
        x=x_axis,
        y=df_slice["P_Load_kW"],
        name="Facility Load (Baseline)",
        mode="lines",
        line=dict(color="#64748B", width=1.5, dash="dot"),
        hovertemplate="Load: %{y:.1f} kW"
    ))

    # 2. Solar PV Generation (Amber Line with light fill)
    fig.add_trace(scatter_cls(
        x=x_axis,
        y=df_slice["P_Solar_kW"],
        name="Solar PV Generation",
        mode="lines",
        line=dict(color="#F59E0B", width=1.8),
        fill="tozeroy",
        fillcolor="rgba(245, 158, 11, 0.15)",
        hovertemplate="Solar: %{y:.1f} kW"
    ))

    # 3. Direct PV Consumption (Emerald Area)
    fig.add_trace(scatter_cls(
        x=x_axis,
        y=df_slice["P_Direct_kW"],
        name="Direct PV Consumption",
        mode="lines",
        line=dict(color="#10B981", width=1.5),
        fill="tozeroy",
        fillcolor="rgba(16, 185, 129, 0.25)",
        hovertemplate="Direct PV: %{y:.1f} kW"
    ))

    # 4. BESS Charging from PV (Teal)
    fig.add_trace(scatter_cls(
        x=x_axis,
        y=df_slice["P_BESS_Charge_PV_kW"],
        name="BESS Charge (Solar Surplus)",
        mode="lines",
        line=dict(color="#06B6D4", width=2.0, dash="dash"),
        hovertemplate="BESS Charge: %{y:.1f} kW"
    ))

    # 5. BESS Discharge (Purple Area)
    fig.add_trace(scatter_cls(
        x=x_axis,
        y=df_slice["P_BESS_Discharge_kW"],
        name="BESS Discharge",
        mode="lines",
        line=dict(color="#A855F7", width=2.0),
        hovertemplate="BESS Discharge: %{y:.1f} kW"
    ))

    # 6. New Net Grid Import (Solid Rose/Red Line)
    fig.add_trace(scatter_cls(
        x=x_axis,
        y=df_slice["P_Grid_Import_kW"],
        name="New Grid Import (Post Hybrid)",
        mode="lines",
        line=dict(color="#38BDF8", width=2.2),
        hovertemplate="Grid Import: %{y:.1f} kW"
    ))

    # 7. Grid Export (Cyan Line)
    if (df_slice["P_Grid_Export_kW"] > 0.01).any():
        fig.add_trace(scatter_cls(
            x=x_axis,
            y=df_slice["P_Grid_Export_kW"],
            name="Grid Feed-in (Surplus Export)",
            mode="lines",
            line=dict(color="#2DD4BF", width=1.5, dash="dot"),
            hovertemplate="Grid Export: %{y:.1f} kW"
        ))

    # 8. Target Cap / Grid Limit (Horizontal line)
    if target_cap_kw > 0:
        fig.add_hline(
            y=target_cap_kw,
            line_dash="dash",
            line_color="#EF4444",
            line_width=2,
            annotation_text=f"Target Cap / Grid Limit ({target_cap_kw:.0f} kW)",
            annotation_position="top left",
            annotation_font_color="#EF4444"
        )

    fig.update_layout(
        title=title_text,
        xaxis_title="Time",
        yaxis_title="Active Power (kW)",
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(15,23,42,0.6)",
        hovermode="x unified",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1.0,
            font=dict(size=11)
        ),
        margin=dict(l=40, r=20, t=80, b=40),
        height=520
    )
    if steps_to_show > 1000:
        fig.update_xaxes(rangeslider_visible=True)

    return fig


def create_hybrid_soc_chart(
    df_dispatch: pd.DataFrame,
    soc_min_pct: float = 10.0,
    soc_max_pct: float = 90.0,
    days_to_show: Optional[int] = None
) -> go.Figure:
    """
    Renders Battery State of Charge (SoC %) timeseries with safe operating boundary envelope.
    """
    fig = go.Figure()
    total_steps = len(df_dispatch)
    total_days = total_steps * 0.25 / 24.0

    if days_to_show is None or (days_to_show * 96) >= total_steps:
        steps_to_show = total_steps
        title_text = f"<b>Battery State of Charge (SoC %) Profile ({total_days:.0f} Days / {total_steps:,} Intervals)</b>"
    else:
        steps_to_show = min(total_steps, days_to_show * 96)
        title_text = f"<b>Battery State of Charge (SoC %) Profile ({days_to_show} Days Sample)</b>"

    df_slice = df_dispatch.iloc[:steps_to_show].copy()
    x_axis = df_slice["timestamp"] if "timestamp" in df_slice.columns else np.arange(steps_to_show)

    scatter_cls = go.Scattergl if steps_to_show > 4000 else go.Scatter

    # SoC Line
    fig.add_trace(scatter_cls(
        x=x_axis,
        y=df_slice["SoC_pct"],
        name="State of Charge (SoC)",
        mode="lines",
        line=dict(color="#38BDF8", width=2.0),
        fill="tozeroy",
        fillcolor="rgba(56, 189, 248, 0.15)",
        hovertemplate="SoC: %{y:.1f}%"
    ))

    # SoC Min Line
    fig.add_hline(
        y=soc_min_pct,
        line_dash="dash",
        line_color="#F43F5E",
        line_width=1.5,
        annotation_text=f"SoC Min ({soc_min_pct:.0f}%)",
        annotation_position="bottom left",
        annotation_font_color="#F43F5E"
    )

    # SoC Max Line
    fig.add_hline(
        y=soc_max_pct,
        line_dash="dash",
        line_color="#10B981",
        line_width=1.5,
        annotation_text=f"SoC Max ({soc_max_pct:.0f}%)",
        annotation_position="top left",
        annotation_font_color="#10B981"
    )

    fig.update_layout(
        title=title_text,
        xaxis_title="Time",
        yaxis_title="State of Charge (%)",
        yaxis=dict(range=[0, 105]),
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(15,23,42,0.6)",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1.0),
        margin=dict(l=40, r=20, t=60, b=40),
        height=360
    )
    return fig


def create_hybrid_monthly_balance_chart(monthly_metrics: List[Dict[str, Any]]) -> go.Figure:
    """
    Renders monthly stacked bar chart showing energy consumption coverage and grid export.
    """
    fig = go.Figure()
    if not monthly_metrics:
        return fig

    months = [m["month_name"][:3] for m in monthly_metrics]
    direct_kwh = [m.get("direct_kwh", 0.0) / 1000.0 for m in monthly_metrics]
    bess_dis_kwh = [m.get("bess_discharge_kwh", 0.0) / 1000.0 for m in monthly_metrics]
    grid_imp_kwh = [m.get("grid_import_kwh", 0.0) / 1000.0 for m in monthly_metrics]
    grid_exp_kwh = [m.get("grid_export_kwh", 0.0) / 1000.0 for m in monthly_metrics]

    # Stacked Bars: Demand Fulfillment (in MWh)
    fig.add_trace(go.Bar(
        x=months,
        y=direct_kwh,
        name="Direct PV Consumption",
        marker_color="#10B981",
        hovertemplate="%{y:.2f} MWh"
    ))

    fig.add_trace(go.Bar(
        x=months,
        y=bess_dis_kwh,
        name="BESS Stored PV Discharge",
        marker_color="#A855F7",
        hovertemplate="%{y:.2f} MWh"
    ))

    fig.add_trace(go.Bar(
        x=months,
        y=grid_imp_kwh,
        name="Grid Import",
        marker_color="#38BDF8",
        hovertemplate="%{y:.2f} MWh"
    ))

    # Side-by-side or separate bar for Grid Export
    fig.add_trace(go.Bar(
        x=months,
        y=grid_exp_kwh,
        name="Grid Export (Surplus Feed-In)",
        marker_color="#F59E0B",
        hovertemplate="%{y:.2f} MWh"
    ))

    fig.update_layout(
        title="<b>Monthly Energy Balance: Facility Consumption Sourcing & Grid Interaction</b>",
        xaxis_title="Month",
        yaxis_title="Energy (MWh)",
        barmode="stack",
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(15,23,42,0.6)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1.0),
        margin=dict(l=40, r=20, t=70, b=40),
        height=420
    )
    return fig


def create_hybrid_duration_curve(
    df_dispatch: pd.DataFrame,
    grid_limit_kw: float
) -> go.Figure:
    """
    Renders Load Duration Curve comparing Original Load vs New Net Grid Import.
    """
    fig = go.Figure()

    orig_load_sorted = np.sort(df_dispatch["P_Load_kW"].to_numpy(dtype=float))[::-1]
    new_grid_sorted = np.sort(df_dispatch["P_Grid_Import_kW"].to_numpy(dtype=float))[::-1]
    n_steps = len(orig_load_sorted)
    hours = np.arange(n_steps) * 0.25

    fig.add_trace(go.Scatter(
        x=hours,
        y=orig_load_sorted,
        name="Original Facility Load Duration",
        mode="lines",
        line=dict(color="#64748B", width=2.0, dash="dot"),
        hovertemplate="%{y:.1f} kW at %{x:.1f} hours"
    ))

    fig.add_trace(go.Scatter(
        x=hours,
        y=new_grid_sorted,
        name="New Grid Import Duration (Post Hybrid)",
        mode="lines",
        line=dict(color="#10B981", width=2.5),
        fill="tozeroy",
        fillcolor="rgba(16, 185, 129, 0.15)",
        hovertemplate="%{y:.1f} kW at %{x:.1f} hours"
    ))

    if grid_limit_kw > 0:
        fig.add_hline(
            y=grid_limit_kw,
            line_dash="dash",
            line_color="#EF4444",
            line_width=2,
            annotation_text=f"Contracted Grid Limit ({grid_limit_kw:.0f} kW)",
            annotation_position="top right",
            annotation_font_color="#EF4444"
        )

    fig.update_layout(
        title="<b>Load Duration Curve: Grid Peak Shaving & Overload Mitigation</b>",
        xaxis_title="Duration (Hours / Year)",
        yaxis_title="Power Demand (kW)",
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(15,23,42,0.6)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1.0),
        margin=dict(l=40, r=20, t=70, b=40),
        height=400
    )
    return fig
