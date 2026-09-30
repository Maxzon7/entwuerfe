"""
========================================================================================
Generator Charts & Dispatch Visualizations (ui/tab_generator/charts.py)
========================================================================================

Description:
------------
Plotly visualization suite for the On-Site Generator (Peaking & Residual Backup):
  1. 15-Minute Multi-Asset Dispatch Timeseries:
     - Baseline Facility Load
     - Solar Direct Consumption (if active in hybrid sub-scenario)
     - BESS Discharge (if active in hybrid sub-scenario)
     - Residual Demand before Generator
     - Generator Power Output (amber fill)
     - Final Residual Grid Import (post-mitigation)
     - Contracted Grid Limit / Trigger Line
  2. Cumulative Payment Series (Kumulierte Zahlungsreihe):
     - Cumulative Baseline Status Quo vs. Cumulative with Generator
  3. Monthly Generation & Fuel Breakdown:
     - Generator kWh and Fuel Consumption per month
"""

from typing import List, Dict, Any, Optional
import numpy as np
import pandas as pd
import plotly.graph_objects as go


def create_generator_multi_asset_dispatch_chart(
    df_dispatch: pd.DataFrame,
    trigger_kw: float,
    days_to_show: Optional[int] = None,
    is_hybrid: bool = False
) -> go.Figure:
    """
    Renders 15-minute electrical dispatch timeseries for Standalone Peaker or Hybrid Residual Backup.
    Dynamically layers Solar Direct, BESS Discharge, Generator Power, and Net Grid Load.
    """
    fig = go.Figure()
    total_steps = len(df_dispatch)
    total_days = total_steps * 0.25 / 24.0

    if days_to_show is None or (days_to_show * 96) >= total_steps:
        steps_to_show = total_steps
        is_full = True
        title_suffix = f"Full Period: {total_days:.0f} Days / {total_steps:,} Intervals"
    else:
        steps_to_show = min(total_steps, days_to_show * 96)
        is_full = False
        title_suffix = f"{days_to_show} Days Sample"

    df_slice = df_dispatch.iloc[:steps_to_show].copy()
    x_axis = df_slice["timestamp"] if "timestamp" in df_slice.columns else np.arange(steps_to_show)

    scatter_cls = go.Scattergl if steps_to_show > 4000 else go.Scatter

    # 1. Baseline Facility Demand
    if "Original_Load_kW" in df_slice.columns:
        fig.add_trace(scatter_cls(
            x=x_axis,
            y=df_slice["Original_Load_kW"],
            name="Facility Baseline Load",
            mode="lines",
            line=dict(color="#94A3B8", width=1.5, dash="dot"),
            hovertemplate="%{y:.1f} kW"
        ))

    # 2. Solar Direct Self-Consumption (if hybrid)
    if "Solar_Direct_kW" in df_slice.columns and df_slice["Solar_Direct_kW"].sum() > 0:
        fig.add_trace(scatter_cls(
            x=x_axis,
            y=df_slice["Solar_Direct_kW"],
            name="Solar Direct Supply",
            mode="lines",
            line=dict(color="#EAB308", width=1.5),
            fill="tozeroy",
            fillcolor="rgba(234, 179, 8, 0.20)",
            hovertemplate="%{y:.1f} kW"
        ))

    # 3. BESS Discharge (if hybrid)
    if "BESS_Discharge_kW" in df_slice.columns and df_slice["BESS_Discharge_kW"].sum() > 0:
        fig.add_trace(scatter_cls(
            x=x_axis,
            y=df_slice["BESS_Discharge_kW"],
            name="BESS Discharge",
            mode="lines",
            line=dict(color="#06B6D4", width=1.5),
            fill="tozeroy",
            fillcolor="rgba(6, 182, 212, 0.20)",
            hovertemplate="%{y:.1f} kW"
        ))

    # 4. Residual Demand entering Generator (if hybrid and distinct from original load)
    if is_hybrid and "Residual_Load_Before_Gen_kW" in df_slice.columns:
        fig.add_trace(scatter_cls(
            x=x_axis,
            y=df_slice["Residual_Load_Before_Gen_kW"],
            name="Residual Deficit (pre-gen)",
            mode="lines",
            line=dict(color="#F97316", width=1.3, dash="dash"),
            hovertemplate="%{y:.1f} kW"
        ))

    # 5. Generator Active Power Output
    if "Generator_Power_kW" in df_slice.columns:
        fig.add_trace(scatter_cls(
            x=x_axis,
            y=df_slice["Generator_Power_kW"],
            name="Generator Power Output",
            mode="lines",
            line=dict(color="#F59E0B", width=2.0),
            fill="tozeroy",
            fillcolor="rgba(245, 158, 11, 0.35)",
            hovertemplate="%{y:.1f} kW"
        ))

    # 6. Final Net Grid Import
    if "New_Grid_Load_kW" in df_slice.columns:
        fig.add_trace(scatter_cls(
            x=x_axis,
            y=df_slice["New_Grid_Load_kW"],
            name="Final Grid Import",
            mode="lines",
            line=dict(color="#10B981", width=2.0),
            hovertemplate="%{y:.1f} kW"
        ))

    # 7. Grid Limit / Trigger Line
    if trigger_kw > 0:
        fig.add_hline(
            y=trigger_kw,
            line_dash="dash",
            line_color="#EF4444",
            line_width=2,
            annotation_text=f"Grid Limit / Trigger ({trigger_kw:.0f} kW)",
            annotation_position="top left",
            annotation_font_color="#EF4444"
        )

    mode_title = "Hybrid Residual Load & Backup" if is_hybrid else "Standalone Peaking & Backup"
    fig.update_layout(
        title=f"<b>15-Minute Electrical Dispatch: {mode_title} ({title_suffix})</b>",
        xaxis_title="Time",
        yaxis_title="Active Power (kW)",
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(15,23,42,0.6)",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=40, r=40, t=80, b=40),
        height=460,
        xaxis=dict(
            rangeslider=dict(visible=True if is_full or steps_to_show >= 96 * 30 else False)
        )
    )
    return fig


def create_cumulative_payment_chart(
    df_zahlungsreihe: pd.DataFrame,
    currency: str = "EUR"
) -> go.Figure:
    """
    Renders Cumulative Payment Trajectory (Kumulierte Zahlungsreihe) comparing
    Status Quo vs. Mitigated Solution with Generator over billing periods.
    """
    fig = go.Figure()

    months = df_zahlungsreihe["Month"].tolist()
    cum_base = df_zahlungsreihe["Cum_Status_Quo"].tolist()
    cum_gen = df_zahlungsreihe["Cum_With_Generator"].tolist()

    # 1. Status Quo Cumulative
    fig.add_trace(go.Scatter(
        x=months,
        y=cum_base,
        name="Status Quo (Grid Only - Baseline)",
        mode="lines+markers",
        line=dict(color="#EF4444", width=2.5),
        marker=dict(size=7),
        hovertemplate=f"%{{y:,.0f}} {currency}"
    ))

    # 2. With Generator Cumulative
    fig.add_trace(go.Scatter(
        x=months,
        y=cum_gen,
        name="With Generator (Mitigated Grid + Genset OPEX)",
        mode="lines+markers",
        line=dict(color="#10B981", width=2.5),
        marker=dict(size=7),
        hovertemplate=f"%{{y:,.0f}} {currency}"
    ))

    fig.update_layout(
        title="<b>Cumulative Payment Trajectory: Status Quo vs. Solution with Generator</b>",
        xaxis_title="Billing Period",
        yaxis_title=f"Cumulative Cost ({currency})",
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(15,23,42,0.6)",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=40, r=40, t=80, b=40),
        height=400
    )
    return fig
