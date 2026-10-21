"""
========================================================================================
BESS Sandbox - Physics Charts (ui_sandbox/BESS_sandbox/sandbox_charts.py)
========================================================================================

Description:
------------
Sandbox-local Plotly figures for the physics-first BESS workflow:
  1. create_synced_dispatch_soc_figure:
       Single 2-panel subplot (shared x-axis) combining the 15-minute power dispatch
       (load, grid import, BESS discharge/charge, remaining deficit) with the battery
       State of Charge envelope. One range selector (1 Day ... Full Year) and one
       range slider drive both panels synchronously.
  2. create_pareto_tradeoff_figure:
       Hockey-stick curve of required battery capacity (kWh) and inverter power (kW)
       vs. covered share of annual exceedance energy.
"""

from typing import Any, List, Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

COLORS = {
    "load": "#94A3B8",
    "grid": "#3B82F6",
    "limit": "#F87171",
    "discharge": "#22C55E",
    "charge": "#06B6D4",
    "deficit": "#EF4444",
    "soc": "#A78BFA",
    "soc_kwh": "#C4B5FD",
    "bounds": "#F59E0B",
    "capacity": "#F59E0B",
    "power": "#38BDF8",
}


def _timestamps(df: pd.DataFrame) -> pd.Series:
    """Returns the timestamp axis of a dispatch DataFrame."""
    if "timestamp" in df.columns:
        return pd.to_datetime(df["timestamp"])
    return pd.Series(df.index)


def compute_focus_range(df: pd.DataFrame, days: float = 7.0) -> Optional[List[str]]:
    """Initial x-range centered on the annual peak load (default: one week)."""
    if df is None or df.empty:
        return None
    ts = _timestamps(df).reset_index(drop=True)
    if not pd.api.types.is_datetime64_any_dtype(ts):
        return None
    load_col = "P_Load_kW" if "P_Load_kW" in df.columns else None
    idx = int(np.argmax(df[load_col].to_numpy(dtype=float))) if load_col else 0
    half = pd.Timedelta(days=days / 2.0)
    start = max(ts.iloc[0], ts.iloc[idx] - half)
    end = min(ts.iloc[-1], start + 2 * half)
    return [start.isoformat(), end.isoformat()]


def create_synced_dispatch_soc_figure(
    df: pd.DataFrame,
    grid_limit_kw: float,
    soc_min_pct: float,
    soc_max_pct: float,
    capacity_kwh: float,
    initial_range: Optional[List[Any]] = None,
    height: int = 780
) -> go.Figure:
    """Synchronized 2-in-1 figure: power dispatch (top) and SoC envelope (bottom)."""
    ts = _timestamps(df)

    def col(name: str) -> np.ndarray:
        return df[name].to_numpy(dtype=float) if name in df.columns else np.zeros(len(df))

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.07,
        row_heights=[0.62, 0.38],
        specs=[[{"secondary_y": False}], [{"secondary_y": True}]],
        subplot_titles=(
            "15-Minute Power Dispatch (kW)",
            "Battery State of Charge (% and stored kWh)"
        )
    )

    # --- Upper panel: power flows ---
    fig.add_trace(go.Scattergl(
        x=ts, y=col("P_Load_kW"), name="Facility Load (kW)",
        line=dict(color=COLORS["load"], width=1.0),
        hovertemplate="Load: <b>%{y:,.1f} kW</b><extra></extra>"
    ), row=1, col=1)
    fig.add_trace(go.Scattergl(
        x=ts, y=col("P_Grid_kW"), name="Grid Import (kW)",
        line=dict(color=COLORS["grid"], width=1.4),
        hovertemplate="Grid: <b>%{y:,.1f} kW</b><extra></extra>"
    ), row=1, col=1)
    fig.add_trace(go.Scattergl(
        x=ts, y=col("P_BESS_Discharge_kW"), name="BESS Discharge (kW)",
        line=dict(color=COLORS["discharge"], width=1.0),
        fill="tozeroy", fillcolor="rgba(34, 197, 94, 0.25)",
        hovertemplate="Discharge: <b>%{y:,.1f} kW</b><extra></extra>"
    ), row=1, col=1)
    fig.add_trace(go.Scattergl(
        x=ts, y=-col("P_BESS_Charge_kW"), name="BESS Charge (kW, shown negative)",
        line=dict(color=COLORS["charge"], width=1.0, dash="dot"),
        fill="tozeroy", fillcolor="rgba(6, 182, 212, 0.18)",
        hovertemplate="Charge: <b>%{y:,.1f} kW</b><extra></extra>"
    ), row=1, col=1)
    deficit = col("P_Overload_Unmet_kW")
    if float(np.max(deficit, initial=0.0)) > 0.05:
        fig.add_trace(go.Scattergl(
            x=ts, y=deficit, name="Remaining Deficit (kW)",
            line=dict(color=COLORS["deficit"], width=1.8),
            fill="tozeroy", fillcolor="rgba(239, 68, 68, 0.45)",
            hovertemplate="Remaining Deficit: <b>%{y:,.1f} kW</b><extra></extra>"
        ), row=1, col=1)
    fig.add_hline(
        y=grid_limit_kw, row=1, col=1,
        line=dict(color=COLORS["limit"], width=1.6, dash="dash"),
        annotation_text=f"Grid Limit {grid_limit_kw:,.0f} kW",
        annotation_position="top left",
        annotation_font_color=COLORS["limit"]
    )

    # --- Lower panel: SoC envelope ---
    fig.add_trace(go.Scattergl(
        x=ts, y=col("SoC_pct"), name="SoC (%)",
        line=dict(color=COLORS["soc"], width=1.6),
        fill="tozeroy", fillcolor="rgba(167, 139, 250, 0.15)",
        hovertemplate="SoC: <b>%{y:.1f} %</b><extra></extra>"
    ), row=2, col=1, secondary_y=False)
    fig.add_trace(go.Scattergl(
        x=ts, y=col("SoC_kWh"), name="Stored Energy (kWh)",
        line=dict(color=COLORS["soc_kwh"], width=0.8, dash="dot"),
        opacity=0.5,
        hovertemplate="Stored: <b>%{y:,.1f} kWh</b><extra></extra>"
    ), row=2, col=1, secondary_y=True)
    for val, label in [(soc_min_pct, "SoC Min"), (soc_max_pct, "SoC Max")]:
        fig.add_hline(
            y=val, row=2, col=1,
            line=dict(color=COLORS["bounds"], width=1.2, dash="dash"),
            annotation_text=f"{label} {val:.0f}%",
            annotation_position="bottom right",
            annotation_font_color=COLORS["bounds"]
        )

    # Align % and kWh axes so both traces overlay exactly
    cap = max(float(capacity_kwh), 1.0)
    fig.update_yaxes(title_text="Power (kW)", row=1, col=1)
    fig.update_yaxes(title_text="SoC (%)", range=[0, 105], row=2, col=1, secondary_y=False)
    fig.update_yaxes(title_text="Stored (kWh)", range=[0, cap * 1.05], showgrid=False, row=2, col=1, secondary_y=True)

    # Shared range selector (top axis) + slider (bottom axis) drive both panels
    fig.update_xaxes(
        rangeselector=dict(
            buttons=[
                dict(count=1, label="1 Day", step="day", stepmode="backward"),
                dict(count=7, label="1 Week", step="day", stepmode="backward"),
                dict(count=14, label="2 Weeks", step="day", stepmode="backward"),
                dict(count=1, label="1 Month", step="month", stepmode="backward"),
                dict(step="all", label="Full Year"),
            ],
            bgcolor="rgba(30, 41, 59, 0.85)",
            activecolor="#3B82F6",
            font=dict(color="#E2E8F0"),
            y=1.06,
        ),
        row=1, col=1
    )
    fig.update_xaxes(rangeslider=dict(visible=True, thickness=0.05), row=2, col=1)
    if initial_range:
        fig.update_xaxes(range=initial_range)

    fig.update_layout(
        template="plotly_dark",
        height=height,
        hovermode="x unified",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=60, r=60, t=90, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.10, xanchor="left", x=0.0),
    )
    return fig


def create_pareto_tradeoff_figure(pareto: Any, selected_coverage_pct: Optional[float] = None) -> go.Figure:
    """Hockey-stick curve: required gross capacity and inverter power vs. exceedance coverage."""
    x = list(pareto.coverage_pct)
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(
        x=x, y=pareto.required_gross_kwh, name="Required Gross Capacity (kWh)",
        mode="lines+markers",
        line=dict(color=COLORS["capacity"], width=3),
        marker=dict(size=8),
        fill="tozeroy", fillcolor="rgba(245, 158, 11, 0.12)",
        hovertemplate="Coverage %{x:.0f}%<br>Capacity: <b>%{y:,.0f} kWh</b><extra></extra>"
    ), secondary_y=False)
    fig.add_trace(go.Scatter(
        x=x, y=pareto.required_power_kw, name="Required Inverter Power (kW)",
        mode="lines+markers",
        line=dict(color=COLORS["power"], width=2, dash="dash"),
        marker=dict(size=6, symbol="diamond"),
        hovertemplate="Coverage %{x:.0f}%<br>Power: <b>%{y:,.0f} kW</b><extra></extra>"
    ), secondary_y=True)

    if selected_coverage_pct is not None and pareto.has_exceedance:
        sel = pareto.interpolate(selected_coverage_pct)
        fig.add_vline(
            x=sel["coverage_pct"], line=dict(color="#E2E8F0", width=1.2, dash="dot"),
            annotation_text=f"Selected {sel['coverage_pct']:.0f}%",
            annotation_position="top left"
        )
        fig.add_trace(go.Scatter(
            x=[sel["coverage_pct"]], y=[sel["gross_kwh"]], name="Selected Size",
            mode="markers", marker=dict(size=16, color="#F8FAFC", symbol="star", line=dict(color=COLORS["capacity"], width=2)),
            hovertemplate="Selected: <b>%{y:,.0f} kWh</b><extra></extra>"
        ), secondary_y=False)

    fig.update_xaxes(title_text="Covered Share of Annual Exceedance Energy (%)", range=[min(x) - 2, 101])
    fig.update_yaxes(title_text="Gross Capacity (kWh)", secondary_y=False, rangemode="tozero")
    fig.update_yaxes(title_text="Inverter Power (kW)", secondary_y=True, showgrid=False, rangemode="tozero")
    fig.update_layout(
        template="plotly_dark",
        height=420,
        hovermode="x unified",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=60, r=60, t=40, b=50),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0.0),
    )
    return fig
