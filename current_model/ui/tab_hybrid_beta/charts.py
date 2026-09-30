"""
========================================================================================
Solar + BESS Hybrid Charts Suite (current_model/ui/tab_hybrid_beta/charts.py)
========================================================================================

Description:
------------
Plotly visualization suite for the isolated Solar + BESS (Beta) module:
  1. 15-Minute Hybrid Dispatch Timeseries (Load, Solar, Direct PV, BESS Charge/Discharge, Net Grid).
  2. Battery State of Charge (SoC) Dynamics & Operating Envelope (aligned to BESS tab layout).
  3. Monthly Energy Balance Stacked Bar Chart.
  4. Load Duration Curve (archived reference).
"""

from typing import List, Dict, Any, Optional
import numpy as np
import pandas as pd
import plotly.graph_objects as go

from current_model.models.bess import BESSConfig


def create_hybrid_dispatch_chart(
    df_dispatch: pd.DataFrame,
    target_cap_kw: float,
    solar_kwp: float = 0.0,
    capacity_kwh: float = 0.0,
    days_to_show: Optional[int] = None
) -> go.Figure:
    """
    Renders an interactive 15-minute electrical dispatch profile comparing:
      - Facility Demand (Baseline)
      - Solar PV Generation
      - Direct Solar Self-Consumption
      - BESS Charge from PV
      - BESS Discharge
      - New Net Grid Import & Export
      - Grid Connection Limit / Target Shaving Cap
    Includes range selectors, range slider, and defaults to an initial 14-day zoomed view.
    """
    fig = go.Figure()
    step = 2 if len(df_dispatch) > 20000 else 1
    plot_df = df_dispatch.iloc[::step].copy()
    timestamps = pd.to_datetime(plot_df["timestamp"]) if "timestamp" in plot_df.columns else plot_df.index

    # 1. Baseline Facility Load (Dotted Slate Line)
    fig.add_trace(
        go.Scattergl(
            x=timestamps,
            y=plot_df["P_Load_kW"],
            name="Facility Load (Baseline)",
            line=dict(color="#64748B", width=1.5, dash="dot"),
            hovertemplate="<b>%{x|%d %b %Y %H:%M}</b><br>Facility Load: <b>%{y:,.1f} kW</b><extra></extra>",
            showlegend=True
        )
    )

    # 2. Solar PV Generation (Amber Line with subtle fill)
    fig.add_trace(
        go.Scattergl(
            x=timestamps,
            y=plot_df["P_Solar_kW"],
            name="Solar PV Generation",
            line=dict(color="#F59E0B", width=1.8),
            fill="tozeroy",
            fillcolor="rgba(245, 158, 11, 0.12)",
            hovertemplate="Solar PV: <b>%{y:,.1f} kW</b><extra></extra>",
            showlegend=True
        )
    )

    # 3. Direct PV Consumption (Emerald Area)
    fig.add_trace(
        go.Scattergl(
            x=timestamps,
            y=plot_df["P_Direct_kW"],
            name="Direct PV Consumption",
            line=dict(color="#10B981", width=1.5),
            fill="tozeroy",
            fillcolor="rgba(16, 185, 129, 0.25)",
            hovertemplate="Direct PV: <b>%{y:,.1f} kW</b><extra></extra>",
            showlegend=True
        )
    )

    # 4. BESS Charging from Solar PV (Cyan Dot)
    fig.add_trace(
        go.Scattergl(
            x=timestamps,
            y=plot_df["P_BESS_Charge_PV_kW"],
            name="BESS Charge (Solar Surplus)",
            line=dict(color="#06B6D4", width=1.8, dash="dot"),
            hovertemplate="BESS Charge: <b>%{y:,.1f} kW</b><extra></extra>",
            showlegend=True
        )
    )

    # 5. BESS Discharge (Purple Area)
    fig.add_trace(
        go.Scattergl(
            x=timestamps,
            y=plot_df["P_BESS_Discharge_kW"],
            name="BESS Discharge",
            line=dict(color="#A855F7", width=1.8),
            fill="tozeroy",
            fillcolor="rgba(168, 85, 247, 0.20)",
            hovertemplate="BESS Discharge: <b>%{y:,.1f} kW</b><extra></extra>",
            showlegend=True
        )
    )

    # 6. New Net Grid Import (Sky Blue Line)
    fig.add_trace(
        go.Scattergl(
            x=timestamps,
            y=plot_df["P_Grid_Import_kW"],
            name="New Grid Import (Post Hybrid)",
            line=dict(color="#38BDF8", width=2.0),
            hovertemplate="Grid Import: <b>%{y:,.1f} kW</b><extra></extra>",
            showlegend=True
        )
    )

    # 7. Grid Feed-in Export (Teal Dashed Line)
    if (plot_df["P_Grid_Export_kW"] > 0.01).any():
        fig.add_trace(
            go.Scattergl(
                x=timestamps,
                y=plot_df["P_Grid_Export_kW"],
                name="Grid Feed-in (Surplus Export)",
                line=dict(color="#2DD4BF", width=1.5, dash="dot"),
                hovertemplate="Grid Export: <b>%{y:,.1f} kW</b><extra></extra>",
                showlegend=True
            )
        )

    # 8. Target Cap / Grid Limit
    if target_cap_kw > 0:
        fig.add_hline(
            y=target_cap_kw,
            line_dash="dash",
            line_color="#EF4444",
            line_width=1.5,
            annotation_text=f"Peak Shaving Target ({target_cap_kw:,.0f} kW)",
            annotation_position="top left",
            annotation_font=dict(color="#FCA5A5", size=10)
        )

    # Determine initial 14-day default zoom window
    x_range = None
    if len(timestamps) > 0 and hasattr(timestamps, "iloc"):
        start_t = timestamps.iloc[0]
        end_14d = start_t + pd.Timedelta(days=14)
        if hasattr(timestamps.iloc[-1], "timestamp") and timestamps.iloc[-1] > end_14d:
            x_range = [start_t, end_14d]
    elif len(timestamps) > 0 and isinstance(timestamps, pd.DatetimeIndex):
        start_t = timestamps[0]
        end_14d = start_t + pd.Timedelta(days=14)
        if timestamps[-1] > end_14d:
            x_range = [start_t, end_14d]

    # Title with system parameters
    title_parts = ["<b>15-Minute Hybrid Dispatch: Solar PV + BESS</b>"]
    sub_parts = []
    if capacity_kwh > 0:
        sub_parts.append(f"{capacity_kwh:,.0f} kWh BESS")
    if solar_kwp > 0:
        sub_parts.append(f"{solar_kwp:,.0f} kWp Solar")
    if target_cap_kw > 0:
        sub_parts.append(f"Target Cap: {target_cap_kw:,.0f} kW")
    
    if sub_parts:
        title_text = f"{title_parts[0]} <span style='font-size:12px; color:#94A3B8;'>({' | '.join(sub_parts)})</span>"
    else:
        title_text = title_parts[0]

    fig.update_layout(
        template="plotly_dark",
        title=dict(
            text=title_text,
            font=dict(size=14, color="#F8FAFC")
        ),
        xaxis=dict(
            title="Date & Time",
            range=x_range,
            rangeslider=dict(visible=True, thickness=0.06),
            rangeselector=dict(
                buttons=list([
                    dict(count=1, label="1 Day", step="day", stepmode="backward"),
                    dict(count=7, label="1 Week", step="day", stepmode="backward"),
                    dict(count=14, label="2 Weeks", step="day", stepmode="backward"),
                    dict(count=1, label="1 Month", step="month", stepmode="backward"),
                    dict(step="all", label="Full Year")
                ]),
                font=dict(size=10, color="#F8FAFC"),
                bgcolor="#1E293B",
                activecolor="#3B82F6",
                y=1.12,
                x=0.0
            ),
            gridcolor="#1E293B"
        ),
        yaxis=dict(
            title="Active Power (kW)",
            gridcolor="#1E293B",
            zerolinecolor="#334155"
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1.0,
            font=dict(size=11)
        ),
        margin=dict(l=20, r=25, t=75, b=20),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        height=400
    )

    return fig


def create_hybrid_soc_chart(
    df_dispatch: pd.DataFrame,
    bess_config: Optional[BESSConfig] = None,
    soc_min_pct: float = 10.0,
    soc_max_pct: float = 90.0,
    capacity_kwh: float = 100.0,
    days_to_show: Optional[int] = None
) -> go.Figure:
    """
    Constructs a dedicated State of Charge (SoC %) and Stored Energy (kWh) analytics figure
    with safe operating envelope boundaries (SoC_min, SoC_max, and DoD buffers),
    matching the aesthetic and functionality of the Tab 4 BESS layout.
    """
    fig = go.Figure()

    step = 2 if len(df_dispatch) > 20000 else 1
    plot_df = df_dispatch.iloc[::step].copy()
    timestamps = pd.to_datetime(plot_df["timestamp"]) if "timestamp" in plot_df.columns else plot_df.index

    if bess_config is not None:
        cap_kwh = float(bess_config.capacity_kwh)
        soc_min = float(bess_config.soc_min_pct)
        soc_max = float(bess_config.soc_max_pct)
        dod_pct = float(bess_config.max_dod_pct)
        usable_kwh = float(bess_config.effective_usable_kwh)
    else:
        cap_kwh = float(capacity_kwh)
        soc_min = float(soc_min_pct)
        soc_max = float(soc_max_pct)
        dod_pct = max(0.0, soc_max - soc_min)
        usable_kwh = cap_kwh * (dod_pct / 100.0)

    # Calculate SoC_kWh if not present
    if "SoC_kWh" not in plot_df.columns and "SoC_pct" in plot_df.columns:
        plot_df["SoC_kWh"] = plot_df["SoC_pct"] * cap_kwh / 100.0

    # 1. State of Charge (%) (Purple filled line)
    fig.add_trace(
        go.Scattergl(
            x=timestamps,
            y=plot_df["SoC_pct"],
            name="Battery SoC (%)",
            line=dict(color="#A855F7", width=2.0),
            fill="tozeroy",
            fillcolor="rgba(168, 85, 247, 0.22)",
            hovertemplate="<b>%{x|%d %b %Y %H:%M}</b><br>Battery SoC: <b>%{y:.1f}%</b><extra></extra>",
            showlegend=True
        )
    )

    # 2. Stored Energy (kWh) on Secondary Axis (Sky Blue Dashed Line)
    if "SoC_kWh" in plot_df.columns:
        fig.add_trace(
            go.Scattergl(
                x=timestamps,
                y=plot_df["SoC_kWh"],
                name="Stored Energy (kWh)",
                mode="lines",
                yaxis="y2",
                line=dict(color="#38BDF8", width=1.5, dash="dot"),
                hovertemplate="Stored Energy: <b>%{y:,.1f} kWh</b><extra></extra>",
                showlegend=True
            )
        )

    # Boundary 1: SoC Max Limit
    max_kwh = cap_kwh * soc_max / 100.0
    fig.add_hline(
        y=soc_max,
        line_dash="dash",
        line_color="#10B981",
        line_width=1.5,
        annotation_text=f"Max SoC Limit ({soc_max:.0f}% / {max_kwh:,.1f} kWh)",
        annotation_position="top left",
        annotation_font=dict(color="#6EE7B7", size=10)
    )

    # Boundary 2: SoC Min Limit
    min_kwh = cap_kwh * soc_min / 100.0
    fig.add_hline(
        y=soc_min,
        line_dash="dash",
        line_color="#EF4444",
        line_width=1.5,
        annotation_text=f"Min SoC Buffer ({soc_min:.0f}% / {min_kwh:,.1f} kWh)",
        annotation_position="bottom left",
        annotation_font=dict(color="#FCA5A5", size=10)
    )

    # Determine initial 14-day default zoom window
    x_range = None
    if len(timestamps) > 0 and hasattr(timestamps, "iloc"):
        start_t = timestamps.iloc[0]
        end_14d = start_t + pd.Timedelta(days=14)
        if hasattr(timestamps.iloc[-1], "timestamp") and timestamps.iloc[-1] > end_14d:
            x_range = [start_t, end_14d]
    elif len(timestamps) > 0 and isinstance(timestamps, pd.DatetimeIndex):
        start_t = timestamps[0]
        end_14d = start_t + pd.Timedelta(days=14)
        if timestamps[-1] > end_14d:
            x_range = [start_t, end_14d]

    fig.update_layout(
        template="plotly_dark",
        title=dict(
            text=f"<b>Battery State of Charge (SoC) Dynamics & Operating Envelope</b><br>"
                 f"<span style='font-size:11px; color:#94A3B8;'>Usable DoD Window: {dod_pct:.0f}% | Usable Energy: {usable_kwh:,.1f} kWh | Storage: {cap_kwh:,.0f} kWh</span>",
            font=dict(size=14, color="#F8FAFC")
        ),
        xaxis=dict(
            title="Date & Time",
            range=x_range,
            rangeslider=dict(visible=True, thickness=0.06),
            rangeselector=dict(
                buttons=list([
                    dict(count=1, label="1 Day", step="day", stepmode="backward"),
                    dict(count=7, label="1 Week", step="day", stepmode="backward"),
                    dict(count=14, label="2 Weeks", step="day", stepmode="backward"),
                    dict(count=1, label="1 Month", step="month", stepmode="backward"),
                    dict(step="all", label="Full Year")
                ]),
                font=dict(size=10, color="#F8FAFC"),
                bgcolor="#1E293B",
                activecolor="#3B82F6",
                y=1.12,
                x=0.0
            ),
            gridcolor="#1E293B"
        ),
        yaxis=dict(
            title="State of Charge (%)",
            range=[0, 105],
            gridcolor="#1E293B",
            zerolinecolor="#334155"
        ),
        yaxis2=dict(
            title="Stored Energy (kWh)",
            overlaying="y",
            side="right",
            range=[0, cap_kwh * 1.05],
            gridcolor="rgba(56, 189, 248, 0.15)",
            showgrid=False
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1.0,
            font=dict(size=11)
        ),
        margin=dict(l=20, r=45, t=75, b=20),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        height=400
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
        template="plotly_dark",
        title=dict(
            text="<b>Monthly Energy Balance: Facility Consumption Sourcing & Grid Interaction</b>",
            font=dict(size=14, color="#F8FAFC")
        ),
        xaxis=dict(
            title="Month",
            gridcolor="#1E293B"
        ),
        yaxis=dict(
            title="Energy (MWh)",
            gridcolor="#1E293B"
        ),
        barmode="stack",
        paper_bgcolor="#0B0F19",
        plot_bgcolor="#0B0F19",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1.0, font=dict(size=11)),
        margin=dict(l=20, r=20, t=70, b=20),
        height=400
    )
    return fig


def create_hybrid_duration_curve(
    df_dispatch: pd.DataFrame,
    grid_limit_kw: float
) -> go.Figure:
    """
    Renders Load Duration Curve comparing Original Load vs New Net Grid Import (archived reference).
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
            line_width=1.5,
            annotation_text=f"Contracted Grid Limit ({grid_limit_kw:.0f} kW)",
            annotation_position="top right",
            annotation_font=dict(color="#FCA5A5", size=10)
        )

    fig.update_layout(
        template="plotly_dark",
        title=dict(
            text="<b>Load Duration Curve: Grid Peak Shaving & Overload Mitigation</b>",
            font=dict(size=14, color="#F8FAFC")
        ),
        xaxis=dict(
            title="Duration (Hours / Year)",
            gridcolor="#1E293B"
        ),
        yaxis=dict(
            title="Power Demand (kW)",
            gridcolor="#1E293B"
        ),
        paper_bgcolor="#0B0F19",
        plot_bgcolor="#0B0F19",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1.0, font=dict(size=11)),
        margin=dict(l=20, r=20, t=70, b=20),
        height=400
    )
    return fig
