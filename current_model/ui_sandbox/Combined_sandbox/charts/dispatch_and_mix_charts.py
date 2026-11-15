"""
Interactive Plotly visualizations for baseline consumption, synchronized 15-minute
dispatch & battery SoC, supply mix donut, and component utilization bars.
"""

from typing import Any, List, Optional, Tuple
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from ..combined_sandbox_engine import (
    CombinedSimulationResult,
    SystemUtilizationDiagnostics,
)

def _resolve_window_slice(
    timestamps: pd.DatetimeIndex,
    load_kw: np.ndarray,
    timeframe: str = "7D",
) -> Tuple[int, int]:
    """
    Determines the start and end index for a selected timeframe window:
      - "7D" or "Peak Week": 7-day window centered around the annual maximum peak demand
      - "1M": 30-day window centered around the annual maximum peak demand
      - "3M": 90-day window centered around the annual maximum peak demand
      - "All" or "Full Year": Full 35,040 steps
    """
    n = len(load_kw)
    if n == 0 or timeframe in ("All", "Full Year"):
        return 0, n

    peak_idx = int(np.argmax(load_kw))
    steps_per_day = 96

    if timeframe in ("7D", "Peak Week"):
        span = 7 * steps_per_day
    elif timeframe == "1M":
        span = 30 * steps_per_day
    elif timeframe == "3M":
        span = 90 * steps_per_day
    else:
        return 0, n

    half_w = span // 2
    start_i = max(0, peak_idx - half_w)
    end_i = min(n, start_i + span)
    start_i = max(0, end_i - span)
    return start_i, end_i


def create_consumption_baseline_figure(
    timestamps: pd.DatetimeIndex,
    load_kw: np.ndarray,
    timeframe: str = "All",
) -> go.Figure:
    """
    Creates the clean 15-minute Consumption Baseline chart with Range-Slider.
    """
    s_idx, e_idx = _resolve_window_slice(timestamps, load_kw, timeframe=timeframe)
    ts_slice = timestamps[s_idx:e_idx]
    load_slice = np.asarray(load_kw[s_idx:e_idx], dtype=np.float32)

    peak_kw = float(np.max(load_kw)) if len(load_kw) > 0 else 0.0
    avg_kw = float(np.mean(load_kw)) if len(load_kw) > 0 else 0.0

    fig = go.Figure()

    fig.add_trace(
        go.Scattergl(
            x=ts_slice,
            y=load_slice,
            mode="lines",
            name="Consumption (kW)",
            line=dict(color="#38BDF8", width=1.4),
            fill="tozeroy",
            fillcolor="rgba(56, 189, 248, 0.14)",
            hovertemplate="<b>%{x|%Y-%m-%d %H:%M}</b><br>Consumption: %{y:,.1f} kW<extra></extra>",
        )
    )

    fig.add_hline(
        y=peak_kw,
        line_dash="dot",
        line_color="#F87171",
        line_width=1.3,
        annotation_text=f"Peak Demand: {peak_kw:,.1f} kW",
        annotation_position="top right",
        annotation_font=dict(color="#F87171", size=11),
    )

    fig.add_hline(
        y=avg_kw,
        line_dash="dash",
        line_color="#94A3B8",
        line_width=1.1,
        annotation_text=f"Average Load: {avg_kw:,.1f} kW",
        annotation_position="bottom right",
        annotation_font=dict(color="#94A3B8", size=11),
    )

    fig.update_layout(
        template="plotly_dark",
        height=440,
        margin=dict(l=55, r=25, t=45, b=45),
        paper_bgcolor="rgba(15, 23, 42, 0.0)",
        plot_bgcolor="rgba(15, 23, 42, 0.45)",
        title=dict(
            text=f"Consumption Profile ({timeframe})",
            font=dict(size=15, color="#F8FAFC"),
            x=0.0,
        ),
        xaxis=dict(
            title="Time",
            gridcolor="rgba(148, 163, 184, 0.12)",
            showspikes=True,
            rangeslider=dict(visible=False),
        ),
        yaxis=dict(
            title="Power (kW)",
            gridcolor="rgba(148, 163, 184, 0.12)",
            rangemode="tozero",
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1.0,
            bgcolor="rgba(0,0,0,0)",
        ),
        hovermode="x unified",
    )

    return fig


def compute_focus_range_for_timestamps(
    timestamps: pd.DatetimeIndex,
    load_kw: np.ndarray,
    days: float = 7.0,
) -> Optional[List[str]]:
    """Initial x-range centered on the annual peak load (default: one week)."""
    if len(load_kw) == 0 or len(timestamps) == 0:
        return None
    idx = int(np.argmax(load_kw))
    half = pd.Timedelta(days=days / 2.0)
    ts = pd.to_datetime(timestamps)
    start = max(ts[0], ts[idx] - half)
    end = min(ts[-1], start + 2 * half)
    return [start.isoformat(), end.isoformat()]


def _mask_gap_for_webgl_fill(arr: np.ndarray, gap_b: np.ndarray) -> np.ndarray:
    """
    Masks measurement data gaps for WebGL Scattergl traces that use fill='tozeroy'.
    Sets interior gap indices to NaN (preserving blank breaks) while anchoring the
    first and last index of multi-step gaps (>2 steps) to 0.0 so WebGL never draws
    diagonal filled polygons across missing weeks.
    """
    out = np.asarray(arr, dtype=np.float32).copy()
    if out.size == 0 or not np.any(gap_b):
        return out
    padded = np.empty(len(gap_b) + 2, dtype=bool)
    padded[0] = False
    padded[-1] = False
    padded[1:-1] = gap_b
    diffs = np.diff(padded.astype(np.int8))
    starts = np.where(diffs == 1)[0]
    ends = np.where(diffs == -1)[0]
    for s, e in zip(starts, ends):
        if (e - s) > 2:
            out[s] = np.float32(0.0)
            out[s + 1 : e - 1] = np.nan
            out[e - 1] = np.float32(0.0)
        else:
            out[s:e] = np.nan
    return out


def create_combined_dispatch_soc_figure(
    sim_res: CombinedSimulationResult,
    initial_range: Optional[List[Any]] = None,
    timeframe: Optional[str] = None,
    height: int = 780,
) -> go.Figure:
    """
    Creates the Synchronized 2-in-1 15-Minute Master Chart matching BESS Sandbox Standard:
      - Upper Subplot (15-Minute Power Dispatch in kW):
          * Facility Load (kW) line (#94A3B8)
          * Grid Import (kW) line (#3B82F6) capped at Grid Limit
          * Solar Direct (kW) yellow area (#FACC15) when Solar enabled
          * Solar Total Potential (kW) dashed amber line (#F59E0B), hidden by default
          * BESS Discharge (kW) green area (#22C55E) when Battery enabled
          * BESS Charge (kW, shown negative) cyan dotted area (#06B6D4) when Battery enabled
          * Generator Output (kW) orange area (#F97316) when Generator enabled
          * Remaining Deficit (kW) red area (#EF4444) highlighting any unmet overload
          * Red dashed Grid Limit line (#F87171) with top-left annotation
      - Lower Subplot (Synchronized X-Axis):
          * Battery State of Charge (% and stored kWh)
          * Primary Y-axis: SoC (%) [0, 105%] with translucent purple gradient (#A78BFA)
          * Secondary Y-axis: Stored Energy (kWh) [0, capacity * 1.05] dotted curve (#C4B5FD)
          * Bounds: Labeled dashed lines for SoC Min and SoC Max
          * Generator Active operating phases shaded in orange
      - Interactivity:
          * Full 35,040 points loaded in GPU WebGL (go.Scattergl) for 60 FPS performance
          * Native Plotly rangeselector: [1 Day] [1 Week] [2 Weeks] [1 Month] [Full Year]
          * Native range-slider on lower panel driving both panels synchronously
    """
    ts = sim_res.timestamps
    p_load = np.asarray(sim_res.load_kw, dtype=np.float32)
    p_solar_gen = np.asarray(sim_res.solar_gen_kw, dtype=np.float32)
    p_solar_dir = np.asarray(sim_res.solar_direct_kw, dtype=np.float32)
    p_bess_dis = np.asarray(sim_res.bess_discharge_kw, dtype=np.float32)
    p_bess_chg = np.asarray(
        sim_res.bess_charge_solar_kw
        + sim_res.bess_charge_grid_kw
        + sim_res.bess_charge_gen_kw,
        dtype=np.float32,
    )
    p_unmet = np.asarray(sim_res.unmet_overload_kw, dtype=np.float32)
    p_gen_out = np.asarray(sim_res.gen_output_kw, dtype=np.float32)
    p_grid_imp = np.asarray(sim_res.grid_import_kw, dtype=np.float32)
    soc_pct = np.asarray(sim_res.bess_soc_pct, dtype=np.float32)
    soc_kwh = np.asarray(sim_res.bess_energy_kwh, dtype=np.float32)
    gen_active_pct = np.where(sim_res.gen_running_mask, np.float32(100.0), np.float32(0.0))

    # Mask measurement data gaps so Plotly leaves intervals blank without WebGL fill polygons
    is_gap = getattr(sim_res, "is_gap", None)
    if is_gap is not None and np.any(is_gap):
        gap_b = np.asarray(is_gap, dtype=bool)
        p_load = np.where(gap_b, np.nan, p_load)
        p_solar_gen = np.where(gap_b, np.nan, p_solar_gen)
        p_solar_dir = _mask_gap_for_webgl_fill(p_solar_dir, gap_b)
        p_bess_dis = _mask_gap_for_webgl_fill(p_bess_dis, gap_b)
        p_bess_chg = _mask_gap_for_webgl_fill(p_bess_chg, gap_b)
        p_unmet = _mask_gap_for_webgl_fill(p_unmet, gap_b)
        p_gen_out = _mask_gap_for_webgl_fill(p_gen_out, gap_b)
        p_grid_imp = np.where(gap_b, np.nan, p_grid_imp)
        soc_pct = np.where(gap_b, np.nan, soc_pct)
        soc_kwh = np.where(gap_b, np.nan, soc_kwh)
        gen_active_pct = _mask_gap_for_webgl_fill(gen_active_pct, gap_b)

    cfg = sim_res.system_config
    rules = sim_res.rules_config

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.07,
        row_heights=[0.62, 0.38],
        specs=[[{"secondary_y": False}], [{"secondary_y": True}]],
        subplot_titles=(
            "15-Minute Power Dispatch (kW)",
            "Battery State of Charge (% and stored kWh)",
        ),
    )

    # --- ROW 1: Facility Load, Grid Import, Solar, BESS, Gen & Deficit (BESS Sandbox Standard) ---
    # 1. Facility Load
    fig.add_trace(
        go.Scattergl(
            x=ts,
            y=p_load,
            mode="lines",
            name="Facility Load (kW)",
            connectgaps=False,
            line=dict(color="#94A3B8", width=1.0),
            hovertemplate="Load: <b>%{y:,.1f} kW</b><extra></extra>",
        ),
        row=1,
        col=1,
    )

    # 2. Grid Import
    fig.add_trace(
        go.Scattergl(
            x=ts,
            y=p_grid_imp,
            mode="lines",
            name="Grid Import (kW)",
            connectgaps=False,
            line=dict(color="#3B82F6", width=1.4),
            hovertemplate="Grid: <b>%{y:,.1f} kW</b><extra></extra>",
        ),
        row=1,
        col=1,
    )

    # 3. Solar Direct & Total Potential (when enabled)
    if cfg.enable_solar:
        fig.add_trace(
            go.Scattergl(
                x=ts,
                y=p_solar_dir,
                mode="lines",
                name="Solar Direct (kW)",
                connectgaps=False,
                line=dict(color="#FACC15", width=1.0),
                fill="tozeroy",
                fillcolor="rgba(250, 204, 21, 0.25)",
                hovertemplate="Solar Direct: <b>%{y:,.1f} kW</b><extra></extra>",
            ),
            row=1,
            col=1,
        )
        fig.add_trace(
            go.Scattergl(
                x=ts,
                y=p_solar_gen,
                mode="lines",
                name="Solar Total Potential (kW)",
                connectgaps=False,
                line=dict(color="#F59E0B", width=1.2, dash="dash"),
                visible="legendonly",
                hovertemplate="Solar Total Potential: <b>%{y:,.1f} kW</b><extra></extra>",
            ),
            row=1,
            col=1,
        )

    # 4. Battery Discharge & Recharge (when enabled)
    if cfg.enable_battery:
        fig.add_trace(
            go.Scattergl(
                x=ts,
                y=p_bess_dis,
                mode="lines",
                name="BESS Discharge (kW)",
                connectgaps=False,
                line=dict(color="#22C55E", width=1.0),
                fill="tozeroy",
                fillcolor="rgba(34, 197, 94, 0.25)",
                hovertemplate="Discharge: <b>%{y:,.1f} kW</b><extra></extra>",
            ),
            row=1,
            col=1,
        )

        fig.add_trace(
            go.Scattergl(
                x=ts,
                y=-p_bess_chg,
                mode="lines",
                name="BESS Charge (kW, shown negative)",
                connectgaps=False,
                line=dict(color="#06B6D4", width=1.0, dash="dot"),
                fill="tozeroy",
                fillcolor="rgba(6, 182, 212, 0.18)",
                hovertemplate="Charge: <b>%{y:,.1f} kW</b><extra></extra>",
            ),
            row=1,
            col=1,
        )

    # 5. Generator Output (when enabled)
    if cfg.enable_generator:
        fig.add_trace(
            go.Scattergl(
                x=ts,
                y=p_gen_out,
                mode="lines",
                name="Generator Output (kW)",
                connectgaps=False,
                line=dict(color="#F97316", width=1.1),
                fill="tozeroy",
                fillcolor="rgba(249, 115, 22, 0.35)",
                hovertemplate="Generator Output: <b>%{y:,.1f} kW</b><extra></extra>",
            ),
            row=1,
            col=1,
        )

    # 6. Remaining Deficit (highlighted in red)
    if float(np.nanmax(p_unmet)) > 0.05:
        fig.add_trace(
            go.Scattergl(
                x=ts,
                y=p_unmet,
                mode="lines",
                name="Remaining Deficit (kW)",
                connectgaps=False,
                line=dict(color="#EF4444", width=1.8),
                fill="tozeroy",
                fillcolor="rgba(239, 68, 68, 0.45)",
                hovertemplate="Remaining Deficit: <b>%{y:,.1f} kW</b><extra></extra>",
            ),
            row=1,
            col=1,
        )

    # 7. Red dashed Grid Limit horizontal line with top-left annotation (BESS Standard)
    fig.add_hline(
        y=cfg.grid_limit_kw,
        row=1,
        col=1,
        line=dict(color="#F87171", width=1.6, dash="dash"),
        annotation_text=f"Grid Limit {cfg.grid_limit_kw:,.0f} kW",
        annotation_position="top left",
        annotation_font_color="#F87171",
    )

    # --- ROW 2: Battery SoC (% & kWh) & Generator Active Phases ---
    if cfg.enable_generator:
        fig.add_trace(
            go.Scattergl(
                x=ts,
                y=gen_active_pct,
                mode="lines",
                name="Generator Active",
                connectgaps=False,
                line=dict(width=0.0, color="rgba(249, 115, 22, 0.0)"),
                fill="tozeroy",
                fillcolor="rgba(249, 115, 22, 0.22)",
                hovertemplate="Generator Active: %{y:.0f}%<extra></extra>",
            ),
            row=2,
            col=1,
            secondary_y=False,
        )

    if cfg.enable_battery:
        # Primary axis: State of Charge (%)
        fig.add_trace(
            go.Scattergl(
                x=ts,
                y=soc_pct,
                mode="lines",
                name="SoC (%)",
                connectgaps=False,
                line=dict(color="#A78BFA", width=1.6),
                fill="tozeroy",
                fillcolor="rgba(167, 139, 250, 0.15)",
                hovertemplate="SoC: <b>%{y:.1f} %</b><extra></extra>",
            ),
            row=2,
            col=1,
            secondary_y=False,
        )

        # Secondary axis: Stored Energy (kWh)
        fig.add_trace(
            go.Scattergl(
                x=ts,
                y=soc_kwh,
                mode="lines",
                name="Stored Energy (kWh)",
                connectgaps=False,
                line=dict(color="#C4B5FD", width=0.8, dash="dot"),
                opacity=0.5,
                hovertemplate="Stored: <b>%{y:,.1f} kWh</b><extra></extra>",
            ),
            row=2,
            col=1,
            secondary_y=True,
        )

        # Min SoC line
        fig.add_hline(
            y=cfg.min_soc_pct,
            line_dash="dash",
            line_color="#F59E0B",
            line_width=1.2,
            annotation_text=f"SoC Min {cfg.min_soc_pct:.0f}%",
            annotation_position="bottom right",
            annotation_font_color="#F59E0B",
            row=2,
            col=1,
        )

        # Max SoC line
        fig.add_hline(
            y=cfg.max_soc_pct,
            line_dash="dash",
            line_color="#F59E0B",
            line_width=1.2,
            annotation_text=f"SoC Max {cfg.max_soc_pct:.0f}%",
            annotation_position="bottom right",
            annotation_font_color="#F59E0B",
            row=2,
            col=1,
        )

        # Peak Reserve SoC line if Self-Consumption + Peak Reserve is active AND Solar is enabled
        if cfg.enable_solar and rules.rule2_battery_strategy == "self_consumption_reserve":
            fig.add_hline(
                y=rules.peak_reserve_soc_pct,
                line_dash="dot",
                line_color="#38BDF8",
                line_width=1.2,
                annotation_text=f"Peak Reserve ({rules.peak_reserve_soc_pct:.0f}%)",
                annotation_position="top left",
                annotation_font_color="#38BDF8",
                row=2,
                col=1,
            )
    else:
        # Render a subtle zero-level baseline on row 2 when Battery is inactive
        fig.add_trace(
            go.Scattergl(
                x=ts,
                y=np.zeros(len(ts)),
                mode="lines",
                name="Battery Level (Inactive)",
                line=dict(color="#475569", width=1.0, dash="dot"),
                hovertemplate="Battery Inactive (0%)<extra></extra>",
            ),
            row=2,
            col=1,
            secondary_y=False,
        )

    cap_val = max(float(cfg.battery_capacity_kwh), 1.0) if cfg.enable_battery else 100.0

    fig.update_yaxes(
        title_text="Power (kW)",
        gridcolor="rgba(148, 163, 184, 0.12)",
        row=1,
        col=1,
    )
    fig.update_yaxes(
        title_text="SoC (%)",
        gridcolor="rgba(148, 163, 184, 0.12)",
        range=[0, 105],
        row=2,
        col=1,
        secondary_y=False,
    )
    fig.update_yaxes(
        title_text="Stored (kWh)",
        gridcolor="rgba(148, 163, 184, 0.05)",
        range=[0, cap_val * 1.05],
        showgrid=False,
        row=2,
        col=1,
        secondary_y=True,
    )

    # Shared range selector (top axis) + slider (bottom axis) matching BESS Sandbox Standard
    fig.update_xaxes(
        gridcolor="rgba(148, 163, 184, 0.12)",
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
        row=1,
        col=1,
    )
    fig.update_xaxes(
        title_text="Time (15-min intervals)",
        gridcolor="rgba(148, 163, 184, 0.12)",
        rangeslider=dict(visible=True, thickness=0.05),
        row=2,
        col=1,
    )

    # Determine initial focus window (centered on peak demand)
    eff_initial_range = initial_range
    if eff_initial_range is None:
        if timeframe in ("All", "Full Year"):
            eff_initial_range = None
        elif timeframe in ("1M", "3M", "7D", "Peak Week"):
            days_map = {"7D": 7.0, "Peak Week": 7.0, "1M": 30.0, "3M": 90.0}
            eff_initial_range = compute_focus_range_for_timestamps(
                timestamps=ts,
                load_kw=p_load,
                days=days_map.get(timeframe, 7.0),
            )
        else:
            eff_initial_range = compute_focus_range_for_timestamps(
                timestamps=ts,
                load_kw=p_load,
                days=7.0,
            )

    if eff_initial_range:
        fig.update_xaxes(range=eff_initial_range)

    fig.update_layout(
        template="plotly_dark",
        height=height,
        hovermode="x unified",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=60, r=60, t=90, b=40),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.10,
            xanchor="left",
            x=0.0,
            bgcolor="rgba(0,0,0,0)",
            font=dict(size=11),
        ),
    )

    return fig
def create_supply_mix_pie_figure(
    diag: SystemUtilizationDiagnostics,
    height: int = 340,
) -> go.Figure:
    """
    Creates a Donut/Pie chart showing how annual facility electricity consumption (MWh & %)
    is supplied across Grid Direct, Solar Direct, Battery Discharge, and Generator Output.
    """
    raw_items = [
        ("Grid Direct", max(0.0, diag.grid_direct_kwh) / 1000.0, "#3B82F6"),
        ("Solar Direct", max(0.0, diag.solar_direct_kwh) / 1000.0, "#FACC15"),
        ("Battery Discharge", max(0.0, diag.battery_discharge_kwh) / 1000.0, "#22C55E"),
        ("Generator Output", max(0.0, diag.generator_direct_kwh) / 1000.0, "#F97316"),
    ]
    active_items = [(lbl, mwh, clr) for lbl, mwh, clr in raw_items if mwh > 0.001]
    if not active_items:
        active_items = [("Grid Direct", 1.0, "#3B82F6")]

    labels = [x[0] for x in active_items]
    values = [round(x[1], 2) for x in active_items]
    colors = [x[2] for x in active_items]

    fig = go.Figure(
        data=[
            go.Pie(
                labels=labels,
                values=values,
                hole=0.54,
                sort=False,
                direction="clockwise",
                marker=dict(colors=colors, line=dict(color="#0F172A", width=2)),
                textinfo="label+percent",
                textposition="inside",
                insidetextorientation="horizontal",
                hovertemplate="<b>%{label}</b><br>%{value:,.1f} MWh/yr (%{percent})<extra></extra>",
            )
        ]
    )

    ann_mwh = diag.annual_consumption_kwh / 1000.0
    fig.update_layout(
        template="plotly_dark",
        height=height,
        margin=dict(l=15, r=15, t=42, b=15),
        paper_bgcolor="rgba(15, 23, 42, 0.0)",
        plot_bgcolor="rgba(15, 23, 42, 0.0)",
        title=dict(
            text="Annual Electricity Coverage by Source (%)",
            font=dict(size=14, color="#F8FAFC"),
            x=0.0,
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.12,
            xanchor="center",
            x=0.5,
            bgcolor="rgba(0,0,0,0)",
            font=dict(size=11),
        ),
        annotations=[
            dict(
                text=f"<b>{ann_mwh:,.0f} MWh</b><br><span style='font-size:11px;color:#94A3B8;'>Annual Load</span>",
                x=0.5,
                y=0.5,
                font=dict(size=14, color="#F8FAFC"),
                showarrow=False,
            )
        ],
    )
    return fig


def create_component_utilization_bars_figure(
    diag: SystemUtilizationDiagnostics,
    height: int = 340,
) -> go.Figure:
    """
    Creates a 0-100% stacked horizontal bar chart showing how much of each installed
    asset's capability is actively used vs. sitting unused/idle across the full year.
    """
    rows: List[Tuple[str, float, float, str, str]] = []

    if diag.gen_enabled and diag.gen_rated_kw > 0:
        gen_used = min(100.0, max(0.0, diag.gen_power_utilization_pct))
        gen_idle = round(100.0 - gen_used, 1)
        gen_txt = f"{gen_used:.0f}% ({diag.gen_peak_used_kw:,.0f} / {diag.gen_rated_kw:,.0f} kW)"
        gen_idle_txt = f"Unused peak headroom: {max(0.0, diag.gen_rated_kw - diag.gen_peak_used_kw):,.0f} kW | {diag.gen_runtime_hours:,.1f} hrs/yr"
    else:
        gen_used, gen_idle = 0.0, 0.0
        gen_txt = "Inactive"
        gen_idle_txt = "Generator inactive"
    rows.append(("Generator Power (kW)", gen_used, gen_idle, gen_txt, gen_idle_txt))

    if diag.bess_enabled and diag.bess_usable_window_kwh > 0:
        bc_used = min(100.0, max(0.0, diag.bess_capacity_utilization_pct))
        bc_idle = round(100.0 - bc_used, 1)
        bc_txt = f"{bc_used:.0f}% ({diag.bess_max_depth_used_kwh:,.0f} / {diag.bess_usable_window_kwh:,.0f} kWh)"
        bc_idle_txt = f"Untouched usable capacity: {diag.bess_unused_usable_kwh:,.0f} kWh (Installed: {diag.bess_installed_kwh:,.0f} kWh)"
    else:
        bc_used, bc_idle = 0.0, 0.0
        bc_txt = "Inactive"
        bc_idle_txt = "Battery storage inactive"
    rows.append(("Battery Capacity (kWh)", bc_used, bc_idle, bc_txt, bc_idle_txt))

    if diag.solar_enabled and diag.solar_total_potential_kwh > 0:
        sol_used = min(100.0, max(0.0, diag.solar_utilization_pct))
        sol_idle = round(100.0 - sol_used, 1)
        sol_used_mwh = (diag.solar_used_direct_kwh + diag.solar_used_via_battery_kwh) / 1000.0
        sol_tot_mwh = diag.solar_total_potential_kwh / 1000.0
        sol_txt = f"{sol_used:.0f}% ({sol_used_mwh:,.0f} / {sol_tot_mwh:,.0f} MWh)"
        sol_idle_txt = f"Exported / unused surplus: {diag.solar_exported_unused_kwh / 1000.0:,.0f} MWh/yr"
    else:
        sol_used, sol_idle = 0.0, 0.0
        sol_txt = "Inactive"
        sol_idle_txt = "Solar array inactive"
    rows.append(("Solar Yield (MWh)", sol_used, sol_idle, sol_txt, sol_idle_txt))

    y_labels = [r[0] for r in rows]
    used_vals = [round(r[1], 1) for r in rows]
    idle_vals = [round(r[2], 1) for r in rows]
    used_texts = [r[3] for r in rows]
    idle_hovers = [r[4] for r in rows]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            y=y_labels,
            x=used_vals,
            orientation="h",
            name="Actively Used (%)",
            marker_color="#22C55E",
            text=used_texts,
            textposition="auto",
            customdata=used_texts,
            hovertemplate="<b>%{y}</b><br>Used: %{customdata}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            y=y_labels,
            x=idle_vals,
            orientation="h",
            name="Unused / Idle Reserve (%)",
            marker_color="rgba(148, 163, 184, 0.25)",
            customdata=idle_hovers,
            hovertemplate="<b>%{y}</b><br>%{customdata} (%{x:.1f}%)<extra></extra>",
        )
    )

    fig.update_layout(
        barmode="stack",
        template="plotly_dark",
        height=height,
        margin=dict(l=15, r=20, t=58, b=42),
        paper_bgcolor="rgba(15, 23, 42, 0.0)",
        plot_bgcolor="rgba(15, 23, 42, 0.45)",
        title=dict(
            text="Component Utilization (Used % vs. Unused Reserve)",
            font=dict(size=14, color="#F8FAFC"),
            x=0.0,
        ),
        xaxis=dict(
            range=[0, 100],
            title="Share of Installed / Usable Capacity (%)",
            gridcolor="rgba(148, 163, 184, 0.12)",
        ),
        yaxis=dict(
            gridcolor="rgba(148, 163, 184, 0.08)",
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1.0,
            bgcolor="rgba(0,0,0,0)",
            font=dict(size=11),
        ),
    )
    return fig
