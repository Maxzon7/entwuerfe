"""
========================================================================================
BESS Visualizations & Plotly Chart Constructors (ui/tab4_bess/charts.py)
========================================================================================

Description:
------------
Generates high-contrast, dark-themed Plotly charts for Tab 4:
  - 15-Minute interactive BESS electrical dispatch & SoC timeseries with range slider.
  - Peak Shaving Load Duration Curve (Before vs After BESS).
  - Seasonal 24-hour diurnal cycling and battery operation overlay.
  - Monthly energy throughput & equivalent full cycle count.
  - Pre-simulation grid violation exceedance preview chart.
"""

from typing import List, Dict, Any, Optional
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from current_model.models.bess import BESSConfig, BESSKPIs


MONTH_NAMES = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
]


def create_grid_violation_preview_figure(
    df: pd.DataFrame,
    grid_limit_kw: float,
    power_col: str = "P_Load_kW"
) -> go.Figure:
    """
    Constructs a visual preview of the facility load curve with red highlighted
    exceedance areas above the contracted grid connection limit.
    """
    fig = go.Figure()

    step = 2 if len(df) > 20000 else 1
    plot_df = df.iloc[::step]
    timestamps = plot_df["timestamp"] if "timestamp" in plot_df.columns else plot_df.index
    p_load = plot_df[power_col] if power_col in plot_df.columns else plot_df.iloc[:, 0]

    # 1. Base Facility Load Line
    fig.add_trace(
        go.Scattergl(
            x=timestamps,
            y=p_load,
            name="Facility Load (kW)",
            line=dict(color="#94A3B8", width=1.5),
            hovertemplate="<b>%{x|%d %b %Y %H:%M}</b><br>Facility Load: <b>%{y:,.1f} kW</b><extra></extra>",
            showlegend=True
        )
    )

    # 2. Overload Exceedance Shading
    p_over = np.maximum(0.0, p_load - grid_limit_kw)
    fig.add_trace(
        go.Scattergl(
            x=timestamps,
            y=np.where(p_load > grid_limit_kw, p_load, grid_limit_kw),
            name="Grid Overload Violation",
            line=dict(color="#EF4444", width=1.5),
            fill="tonexty",
            fillcolor="rgba(239, 68, 68, 0.35)",
            hovertemplate="Overload Peak: <b>%{y:,.1f} kW</b><extra></extra>",
            showlegend=True
        )
    )

    # 3. Grid Limit Reference Line
    fig.add_hline(
        y=grid_limit_kw,
        line_dash="dash",
        line_color="#F87171",
        line_width=2.0,
        annotation_text=f"Grid Limit ({grid_limit_kw:,.0f} kW)",
        annotation_position="top left",
        annotation_font=dict(color="#FCA5A5", size=11)
    )

    fig.update_layout(
        template="plotly_dark",
        title=dict(
            text=f"<b>Grid Limit Exceedance & Violation Profile</b> "
                 f"<span style='font-size:12px; color:#94A3B8;'>(Grid Limit: {grid_limit_kw:,.0f} kW)</span>",
            font=dict(size=14, color="#F8FAFC")
        ),
        xaxis=dict(
            title="Date & Time",
            rangeslider=dict(visible=True, thickness=0.06),
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
        margin=dict(l=20, r=20, t=55, b=20),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        height=380
    )

    return fig


def create_bess_dispatch_timeseries_figure(
    df: pd.DataFrame,
    grid_limit_kw: float,
    target_cap_kw: float,
    capacity_kwh: float
) -> go.Figure:
    """
    Constructs an interactive 15-minute active power dispatch and peak shaving profile:
    Facility Load, Residual Grid Import, Battery Discharge, Battery Charge, and Peak Shaving Target.
    Includes range selectors and defaults to an initial 14-day zoomed view.
    """
    fig = go.Figure()

    step = 2 if len(df) > 20000 else 1
    plot_df = df.iloc[::step]
    timestamps = pd.to_datetime(plot_df["timestamp"]) if "timestamp" in plot_df.columns else plot_df.index

    # 1. Facility Load Line (Slate)
    fig.add_trace(
        go.Scattergl(
            x=timestamps,
            y=plot_df["P_Load_kW"],
            name="Facility Load (kW)",
            line=dict(color="#64748B", width=1.5),
            hovertemplate="<b>%{x|%d %b %Y %H:%M}</b><br>Facility Load: <b>%{y:,.1f} kW</b><extra></extra>",
            showlegend=True
        )
    )

    # 2. Residual Grid Import (Sky Blue)
    fig.add_trace(
        go.Scattergl(
            x=timestamps,
            y=plot_df["P_Grid_kW"],
            name="Residual Grid Import (kW)",
            line=dict(color="#38BDF8", width=1.8),
            hovertemplate="Grid Import: <b>%{y:,.1f} kW</b><extra></extra>",
            showlegend=True
        )
    )

    # 3. Battery Discharge (Green Filled Area)
    fig.add_trace(
        go.Scattergl(
            x=timestamps,
            y=plot_df["P_BESS_Discharge_kW"],
            name="Battery Discharge (kW)",
            line=dict(color="#10B981", width=1.5),
            fill="tozeroy",
            fillcolor="rgba(16, 185, 129, 0.25)",
            hovertemplate="BESS Discharge: <b>%{y:,.1f} kW</b><extra></extra>",
            showlegend=True
        )
    )

    # 4. Battery Charge (Amber Area)
    fig.add_trace(
        go.Scattergl(
            x=timestamps,
            y=plot_df["P_BESS_Charge_kW"],
            name="Battery Charge (kW)",
            line=dict(color="#F59E0B", width=1.5, dash="dot"),
            hovertemplate="BESS Charge: <b>%{y:,.1f} kW</b><extra></extra>",
            showlegend=True
        )
    )

    # Grid Limit / Peak Shaving Threshold
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
    if len(timestamps) > 0:
        start_t = timestamps.iloc[0]
        end_14d = start_t + pd.Timedelta(days=14)
        if hasattr(timestamps.iloc[-1], "timestamp") and timestamps.iloc[-1] > end_14d:
            x_range = [start_t, end_14d]

    fig.update_layout(
        template="plotly_dark",
        title=dict(
            text=f"<b>15-Minute BESS Peak Shaving & Active Power Dispatch Profile</b> "
                 f"<span style='font-size:12px; color:#94A3B8;'>({capacity_kwh:,.0f} kWh BESS | Target Cap: {target_cap_kw:,.0f} kW)</span>",
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
        height=390
    )

    return fig


def create_average_week_dispatch_figure(
    df_avg_week: pd.DataFrame,
    target_cap_kw: float,
    capacity_kwh: float
) -> go.Figure:
    """
    Constructs a high-impact 7-day representative weekly dispatch figure (Monday 00:00 to Sunday 23:45).
    Shows load, residual grid, BESS discharge, BESS charge, and SoC % with clear day markers and weekend shading.
    """
    fig = go.Figure()

    x_vals = df_avg_week["week_hour"]
    hover_labels = df_avg_week["time_label"]

    # 1. Facility Load Line (Slate)
    fig.add_trace(
        go.Scatter(
            x=x_vals,
            y=df_avg_week["P_Load_kW"],
            name="Facility Load (kW)",
            line=dict(color="#94A3B8", width=1.8),
            customdata=hover_labels,
            hovertemplate="<b>%{customdata}</b><br>Facility Load: <b>%{y:,.1f} kW</b><extra></extra>",
            showlegend=True
        )
    )

    # 2. Residual Grid Import (Sky Blue)
    fig.add_trace(
        go.Scatter(
            x=x_vals,
            y=df_avg_week["P_Grid_kW"],
            name="Residual Grid Import (kW)",
            line=dict(color="#38BDF8", width=2.0),
            customdata=hover_labels,
            hovertemplate="<b>%{customdata}</b><br>Grid Import: <b>%{y:,.1f} kW</b><extra></extra>",
            showlegend=True
        )
    )

    # 3. Battery Discharge (Green Filled Area)
    fig.add_trace(
        go.Scatter(
            x=x_vals,
            y=df_avg_week["P_BESS_Discharge_kW"],
            name="Battery Discharge (kW)",
            line=dict(color="#10B981", width=1.5),
            fill="tozeroy",
            fillcolor="rgba(16, 185, 129, 0.25)",
            customdata=hover_labels,
            hovertemplate="<b>%{customdata}</b><br>BESS Discharge: <b>%{y:,.1f} kW</b><extra></extra>",
            showlegend=True
        )
    )

    # 4. Battery Charge (Amber Area)
    fig.add_trace(
        go.Scatter(
            x=x_vals,
            y=df_avg_week["P_BESS_Charge_kW"],
            name="Battery Charge (kW)",
            line=dict(color="#F59E0B", width=1.5, dash="dot"),
            customdata=hover_labels,
            hovertemplate="<b>%{customdata}</b><br>BESS Charge: <b>%{y:,.1f} kW</b><extra></extra>",
            showlegend=True
        )
    )

    # Peak Shaving Target
    fig.add_hline(
        y=target_cap_kw,
        line_dash="dash",
        line_color="#EF4444",
        line_width=1.5,
        annotation_text=f"Peak Shaving Target ({target_cap_kw:,.0f} kW)",
        annotation_position="top left",
        annotation_font=dict(color="#FCA5A5", size=10)
    )

    # Add vertical divider lines for days (24, 48, 72, 96, 120, 144)
    for day_h in [24, 48, 72, 96, 120, 144]:
        fig.add_vline(x=day_h, line_width=1.0, line_dash="dot", line_color="#334155")

    # Add subtle weekend shading (Hours 120 to 168 = Saturday to Sunday)
    fig.add_vrect(
        x0=120, x1=168,
        fillcolor="rgba(148, 163, 184, 0.05)",
        layer="below",
        line_width=0,
        annotation_text="Weekend (Sat-Sun)",
        annotation_position="top right",
        annotation_font=dict(color="#64748B", size=10)
    )

    tick_vals = [12, 36, 60, 84, 108, 132, 156]
    tick_texts = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    fig.update_layout(
        template="plotly_dark",
        title=dict(
            text=f"<b>Representative Average Week (7-Day Continuous Power Dispatch)</b><br>"
                 f"<span style='font-size:11px; color:#94A3B8;'>Aggregated 168-hour continuous cycle ({capacity_kwh:,.0f} kWh BESS | Target Cap: {target_cap_kw:,.0f} kW)</span>",
            font=dict(size=14, color="#F8FAFC")
        ),
        xaxis=dict(
            title="Day of Week & Time",
            tickmode="array",
            tickvals=tick_vals,
            ticktext=tick_texts,
            range=[0, 168],
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
        margin=dict(l=20, r=20, t=65, b=20),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        height=420
    )

    return fig


def create_bess_soc_analysis_figure(
    df: pd.DataFrame,
    bess_config: BESSConfig
) -> go.Figure:
    """
    Constructs a dedicated State of Charge (SoC %) and Stored Energy (kWh) analytics figure
    with safe operating envelope boundaries (SoC_min, SoC_max, and DoD buffers).
    """
    fig = go.Figure()

    step = 2 if len(df) > 20000 else 1
    plot_df = df.iloc[::step]
    timestamps = pd.to_datetime(plot_df["timestamp"]) if "timestamp" in plot_df.columns else plot_df.index

    cap_kwh = float(bess_config.capacity_kwh)
    soc_min_pct = float(bess_config.soc_min_pct)
    soc_max_pct = float(bess_config.soc_max_pct)

    # 1. State of Charge (%)
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

    # 2. Stored Energy (kWh) on Secondary Axis
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
    fig.add_hline(
        y=soc_max_pct,
        line_dash="dash",
        line_color="#10B981",
        line_width=1.5,
        annotation_text=f"Max SoC Limit ({soc_max_pct:.0f}% / {cap_kwh * soc_max_pct / 100:.1f} kWh)",
        annotation_position="top left",
        annotation_font=dict(color="#6EE7B7", size=10)
    )

    # Boundary 2: SoC Min Limit
    fig.add_hline(
        y=soc_min_pct,
        line_dash="dash",
        line_color="#EF4444",
        line_width=1.5,
        annotation_text=f"Min SoC Buffer ({soc_min_pct:.0f}% / {cap_kwh * soc_min_pct / 100:.1f} kWh)",
        annotation_position="bottom left",
        annotation_font=dict(color="#FCA5A5", size=10)
    )

    # Initial 14-day zoom window
    x_range = None
    if len(timestamps) > 0:
        start_t = timestamps.iloc[0]
        end_14d = start_t + pd.Timedelta(days=14)
        if hasattr(timestamps.iloc[-1], "timestamp") and timestamps.iloc[-1] > end_14d:
            x_range = [start_t, end_14d]

    fig.update_layout(
        template="plotly_dark",
        title=dict(
            text=f"<b>Battery State of Charge (SoC) Dynamics & Operating Envelope</b><br>"
                 f"<span style='font-size:11px; color:#94A3B8;'>Usable DoD Window: {bess_config.max_dod_pct:.0f}% | Usable Energy: {bess_config.effective_usable_kwh:,.1f} kWh</span>",
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


def create_bess_soc_heatmap_figure(df: pd.DataFrame) -> go.Figure:
    """
    Constructs a 24-Hour (y-axis) x 7-Day (x-axis Mon-Sun) Heatmap of average Battery State of Charge (SoC %).
    Reveals charging patterns, storage holding, and peak shaving discharge windows across the week.
    """
    df_calc = df.copy()
    if "timestamp" in df_calc.columns:
        ts = pd.to_datetime(df_calc["timestamp"])
        df_calc["day_of_week"] = ts.dt.dayofweek
        df_calc["hour"] = ts.dt.hour
    else:
        n_steps = len(df_calc)
        ts = pd.date_range("2026-01-05 00:00:00", periods=n_steps, freq="15min")
        df_calc["day_of_week"] = ts.dt.dayofweek
        df_calc["hour"] = ts.dt.hour

    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    hours = list(range(24))

    # Pivot table: rows = hours (0-23), cols = day_of_week (0-6)
    matrix = np.zeros((24, 7), dtype=float)
    for d in range(7):
        for h in range(24):
            subset = df_calc[(df_calc["day_of_week"] == d) & (df_calc["hour"] == h)]
            if not subset.empty:
                matrix[h, d] = float(subset["SoC_pct"].mean())
            else:
                matrix[h, d] = 50.0

    # Custom gradient: Deep Navy -> Violet -> Emerald -> Amber
    custom_colorscale = [
        [0.0, "#0F172A"],
        [0.3, "#4338CA"],
        [0.6, "#0D9488"],
        [0.85, "#10B981"],
        [1.0, "#F59E0B"]
    ]

    fig = go.Figure(
        data=go.Heatmap(
            z=matrix,
            x=day_names,
            y=[f"{h:02d}:00" for h in hours],
            colorscale=custom_colorscale,
            colorbar=dict(
                title=dict(
                    text="Average<br>SoC (%)",
                    side="top"
                ),
                ticksuffix="%",
                thickness=14,
                len=0.9
            ),
            hovertemplate="<b>%{x} at %{y}</b><br>Average Battery SoC: <b>%{z:.1f}%</b><extra></extra>"
        )
    )

    fig.update_layout(
        template="plotly_dark",
        title=dict(
            text="<b>24-Hour × 7-Day Battery State of Charge (SoC) Heatmap</b><br>"
                 "<span style='font-size:11px; color:#94A3B8;'>Average battery charge state by hour of day across all weekdays and weekends</span>",
            font=dict(size=14, color="#F8FAFC")
        ),
        xaxis=dict(
            title="Day of Week",
            gridcolor="#1E293B"
        ),
        yaxis=dict(
            title="Hour of Day",
            autorange="reversed",
            dtick=2,
            gridcolor="#1E293B"
        ),
        margin=dict(l=20, r=20, t=65, b=20),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        height=380
    )

    return fig


def create_load_duration_peak_shaving_figure(
    df: pd.DataFrame,
    grid_limit_kw: float,
    step_hours: float = 0.25
) -> go.Figure:
    """
    Constructs a Load Duration Curve comparing original load vs residual grid load
    to illustrate exact peak hours shaved by BESS.
    """
    orig_sorted = np.sort(df["P_Load_kW"].to_numpy())[::-1]
    res_sorted = np.sort(df["P_Grid_kW"].to_numpy())[::-1]
    hours_axis = np.arange(len(orig_sorted)) * step_hours

    # Downsample for smooth plotting if necessary
    step = 4 if len(hours_axis) > 10000 else 1
    h_plot = hours_axis[::step]
    o_plot = orig_sorted[::step]
    r_plot = res_sorted[::step]

    fig = go.Figure()

    # Trace 1: Original Load Duration
    fig.add_trace(
        go.Scatter(
            x=h_plot,
            y=o_plot,
            name="Original Facility Load",
            line=dict(color="#94A3B8", width=2.0),
            hovertemplate="<b>%{x:,.0f} Hours:</b> Original %{y:,.1f} kW<extra></extra>"
        )
    )

    # Trace 2: Residual Grid Load Duration
    fig.add_trace(
        go.Scatter(
            x=h_plot,
            y=r_plot,
            name="With BESS Peak Shaving",
            line=dict(color="#38BDF8", width=2.0),
            fill="tonexty",
            fillcolor="rgba(16, 185, 129, 0.25)",
            hovertemplate="<b>%{x:,.0f} Hours:</b> With BESS %{y:,.1f} kW<extra></extra>"
        )
    )

    # Grid Limit
    fig.add_hline(
        y=grid_limit_kw,
        line_dash="dash",
        line_color="#EF4444",
        line_width=1.5,
        annotation_text=f"Grid Limit ({grid_limit_kw:,.0f} kW)",
        annotation_position="top right",
        annotation_font=dict(color="#FCA5A5", size=10)
    )

    fig.update_layout(
        template="plotly_dark",
        title=dict(
            text="<b>Load Duration Curve: Peak Shaving Impact (Annual Hours)</b><br>"
                 "<span style='font-size:11px; color:#94A3B8;'>Green shaded area represents peak power shaved and shifted by the battery system</span>",
            font=dict(size=14, color="#F8FAFC")
        ),
        xaxis=dict(
            title="Operating Duration (Hours / Year)",
            gridcolor="#1E293B"
        ),
        yaxis=dict(
            title="Demand Power (kW)",
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
        margin=dict(l=20, r=20, t=65, b=20),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        height=360
    )

    return fig


def create_seasonal_bess_diurnal_figure(df: pd.DataFrame) -> go.Figure:
    """
    Constructs seasonal 24-hour diurnal operation profiles showing average charging,
    discharging, and SoC cycling across seasons.
    """
    df_calc = df.copy()
    ts = pd.to_datetime(df_calc["timestamp"])
    df_calc["hour"] = ts.dt.hour
    df_calc["month"] = ts.dt.month

    seasons = [
        ("Summer (Jan)", 1, "#F59E0B"),
        ("Autumn (Apr)", 4, "#FB923C"),
        ("Winter (Jul)", 7, "#38BDF8"),
        ("Spring (Oct)", 10, "#10B981")
    ]

    fig = go.Figure()
    hours = list(range(24))

    for s_name, m_num, s_color in seasons:
        s_df = df_calc[df_calc["month"] == m_num]
        if not s_df.empty:
            avg_dis = s_df.groupby("hour")["P_BESS_Discharge_kW"].mean().reindex(hours, fill_value=0.0)
            avg_chg = s_df.groupby("hour")["P_BESS_Charge_kW"].mean().reindex(hours, fill_value=0.0)
            avg_soc = s_df.groupby("hour")["SoC_pct"].mean().reindex(hours, fill_value=0.0)

            fig.add_trace(
                go.Scatter(
                    x=hours,
                    y=avg_dis.values,
                    name=f"{s_name} - Discharge",
                    mode="lines",
                    line=dict(color=s_color, width=2.0),
                    hovertemplate=f"<b>{s_name} Discharge:</b> %{{y:,.1f}} kW<extra></extra>"
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=hours,
                    y=-avg_chg.values,
                    name=f"{s_name} - Charge",
                    mode="lines",
                    line=dict(color=s_color, width=1.5, dash="dot"),
                    hovertemplate=f"<b>{s_name} Charge:</b> %{{y:,.1f}} kW<extra></extra>"
                )
            )

    fig.update_layout(
        template="plotly_dark",
        title=dict(
            text="<b>Seasonal Diurnal BESS Operation (24-Hour Average Cycles)</b><br>"
                 "<span style='font-size:11px; color:#94A3B8;'>Positive values = Battery Discharging (Peak Shaving) | Negative values = Battery Charging (Recharge)</span>",
            font=dict(size=14, color="#F8FAFC")
        ),
        xaxis=dict(
            title="Hour of Day (0 - 23)",
            tickmode="linear",
            tick0=0,
            dtick=2,
            gridcolor="#1E293B"
        ),
        yaxis=dict(
            title="BESS Power (+Discharge / -Charge kW)",
            gridcolor="#1E293B",
            zerolinecolor="#475569",
            zerolinewidth=1.5
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1.0,
            font=dict(size=10)
        ),
        margin=dict(l=20, r=20, t=65, b=20),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        height=360
    )

    return fig


def create_monthly_bess_throughput_figure(monthly_rows: List[Dict[str, Any]]) -> go.Figure:
    """
    Constructs a monthly bar chart of discharged energy (kWh) and equivalent full cycle count.
    """
    months = [MONTH_NAMES[r["month"] - 1] for r in monthly_rows]
    dis_kwh = [r.get("discharged_kwh", r.get("discharged_mwh", 0.0) * 1000.0) for r in monthly_rows]
    cycles = [r["cycles"] for r in monthly_rows]
    peak_shaved = [r["peak_shaved_kw"] for r in monthly_rows]

    fig = go.Figure()

    # Bar: Monthly Discharged Energy (kWh)
    fig.add_trace(
        go.Bar(
            name="Discharged Energy (kWh)",
            x=months,
            y=dis_kwh,
            marker_color="#10B981",
            hovertemplate="<b>%{x}</b> Discharged: <b>%{y:,.0f} kWh</b><extra></extra>"
        )
    )

    # Line: Equivalent Cycles on Secondary Axis
    fig.add_trace(
        go.Scatter(
            name="Equivalent Full Cycles",
            x=months,
            y=cycles,
            mode="lines+markers",
            yaxis="y2",
            line=dict(color="#A855F7", width=2.5),
            marker=dict(size=6, color="#C084FC"),
            hovertemplate="<b>%{x} Full Cycles:</b> <b>%{y:.1f}</b><extra></extra>"
        )
    )

    fig.update_layout(
        template="plotly_dark",
        title=dict(
            text="<b>Monthly BESS Throughput & Equivalent Full Cycles</b><br>"
                 "<span style='font-size:11px; color:#94A3B8;'>Energy throughput delivered for peak shaving and monthly cycling intensity</span>",
            font=dict(size=14, color="#F8FAFC")
        ),
        xaxis=dict(gridcolor="#1E293B"),
        yaxis=dict(
            title="Discharged Energy (kWh)",
            gridcolor="#1E293B",
            zerolinecolor="#334155"
        ),
        yaxis2=dict(
            title="Equivalent Full Cycles",
            overlaying="y",
            side="right",
            gridcolor="rgba(168, 85, 247, 0.15)",
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
        margin=dict(l=20, r=40, t=65, b=20),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        height=360
    )

    return fig
