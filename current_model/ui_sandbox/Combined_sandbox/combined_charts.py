"""
========================================================================================
Combined System Sandbox Charts (ui_sandbox/Combined_sandbox/combined_charts.py)
========================================================================================

Provides the interactive Plotly visualizations for the Combined System Sandbox:
  1. `create_consumption_baseline_figure` — 15-Minute Consumption Profile
     with timeframe switches (7D, 1M, 3M, All) and Range-Slider.
  2. `create_combined_dispatch_soc_figure` — Synchronized 2-in-1 15-Minute
     Master Chart (Grid Import, Solar Direct, Battery Discharge, Generator Output,
     Consumption, Grid Limit) & Battery Level (SoC % and kWh) + Generator Runtime.
  3. `create_financial_cost_comparison_figure` — Side-by-side stacked bar chart comparing
     annual costs of `Current situation` (Without System) vs. `Combined system` (With System)
     across the 4 Tariff Pillars and system operating costs.
========================================================================================
"""

from typing import Any, List, Optional, Tuple
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .combined_sandbox_engine import CombinedSimulationResult


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
    load_slice = load_kw[s_idx:e_idx]

    peak_kw = float(np.max(load_kw)) if len(load_kw) > 0 else 0.0
    avg_kw = float(np.mean(load_kw)) if len(load_kw) > 0 else 0.0

    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
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
            text=f"15-Minute Consumption Profile ({timeframe})",
            font=dict(size=15, color="#F8FAFC"),
            x=0.0,
        ),
        xaxis=dict(
            title="Time (15-min intervals)",
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
    p_load = sim_res.load_kw
    p_solar_dir = sim_res.solar_direct_kw
    p_bess_dis = sim_res.bess_discharge_kw
    p_bess_chg = (
        sim_res.bess_charge_solar_kw
        + sim_res.bess_charge_grid_kw
        + sim_res.bess_charge_gen_kw
    )
    p_unmet = sim_res.unmet_overload_kw
    p_gen_out = sim_res.gen_output_kw
    p_grid_imp = sim_res.grid_import_kw
    soc_pct = sim_res.bess_soc_pct
    soc_kwh = sim_res.bess_energy_kwh
    gen_active_pct = np.where(sim_res.gen_running_mask, 100.0, 0.0)

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
            line=dict(color="#3B82F6", width=1.4),
            hovertemplate="Grid: <b>%{y:,.1f} kW</b><extra></extra>",
        ),
        row=1,
        col=1,
    )

    # 3. Solar Direct (when enabled)
    if cfg.enable_solar:
        fig.add_trace(
            go.Scattergl(
                x=ts,
                y=p_solar_dir,
                mode="lines",
                name="Solar Direct (kW)",
                line=dict(color="#FACC15", width=1.0),
                fill="tozeroy",
                fillcolor="rgba(250, 204, 21, 0.25)",
                hovertemplate="Solar Direct: <b>%{y:,.1f} kW</b><extra></extra>",
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
                line=dict(color="#F97316", width=1.1),
                fill="tozeroy",
                fillcolor="rgba(249, 115, 22, 0.35)",
                hovertemplate="Generator Output: <b>%{y:,.1f} kW</b><extra></extra>",
            ),
            row=1,
            col=1,
        )

    # 6. Remaining Deficit (highlighted in red)
    if float(np.max(p_unmet, initial=0.0)) > 0.05:
        fig.add_trace(
            go.Scattergl(
                x=ts,
                y=p_unmet,
                mode="lines",
                name="Remaining Deficit (kW)",
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


def create_financial_cost_comparison_figure(
    sim_res: CombinedSimulationResult,
) -> go.Figure:
    """
    Creates the Side-by-Side Annual Cost Comparison Bar Chart for Sub-Tab 6 (Financials),
    comparing `Current situation (Without System)` vs. `Combined system (With System)`
    across the 4 Tariff Pillars and System Operations (O&M, Fuel, Rental).
    """
    fk = sim_res.financial_kpis
    scenarios = ["Current situation (Without System)", "Combined system (With System)"]

    if fk is None:
        return go.Figure()

    p1_vals = [fk.baseline_pillar1_supply_eur, fk.combined_pillar1_supply_eur]
    p2_net_vals = [
        max(0.0, fk.baseline_pillar2_dso_eur - fk.baseline_penalty_cost_eur),
        max(0.0, fk.combined_pillar2_dso_eur - fk.combined_grid_penalty_cost_eur),
    ]
    pen_vals = [fk.baseline_penalty_cost_eur, fk.combined_grid_penalty_cost_eur]
    p3_vals = [fk.baseline_pillar3_metering_eur, fk.combined_pillar3_metering_eur]
    p4_vals = [fk.baseline_pillar4_taxes_eur, fk.combined_pillar4_taxes_eur]
    sys_opex_vals = [
        0.0,
        fk.solar_om_eur + fk.battery_om_eur + fk.generator_total_opex_eur,
    ]

    fig = go.Figure()

    fig.add_trace(
        go.Bar(
            name="Pillar 1: Energy Supply",
            x=scenarios,
            y=p1_vals,
            marker_color="#3B82F6",
            hovertemplate="%{x}<br>Energy Supply: €%{y:,.0f}/yr<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            name="Pillar 2: Grid Network (DSO)",
            x=scenarios,
            y=p2_net_vals,
            marker_color="#0EA5E9",
            hovertemplate="%{x}<br>Grid Network (DSO): €%{y:,.0f}/yr<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            name="Pillar 2: Overload Penalties",
            x=scenarios,
            y=pen_vals,
            marker_color="#EF4444",
            hovertemplate="%{x}<br>Overload Penalties: €%{y:,.0f}/yr<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            name="Pillar 3: Metering",
            x=scenarios,
            y=p3_vals,
            marker_color="#A855F7",
            hovertemplate="%{x}<br>Metering: €%{y:,.0f}/yr<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            name="Pillar 4: Taxes & Levies",
            x=scenarios,
            y=p4_vals,
            marker_color="#F59E0B",
            hovertemplate="%{x}<br>Taxes & Levies: €%{y:,.0f}/yr<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            name="System O&M, Fuel & Rental",
            x=scenarios,
            y=sys_opex_vals,
            marker_color="#10B981",
            hovertemplate="%{x}<br>System O&M, Fuel & Rental: €%{y:,.0f}/yr<extra></extra>",
        )
    )

    fig.update_layout(
        barmode="stack",
        template="plotly_dark",
        height=420,
        margin=dict(l=55, r=25, t=75, b=45),
        paper_bgcolor="rgba(15, 23, 42, 0.0)",
        plot_bgcolor="rgba(15, 23, 42, 0.45)",
        title=dict(
            text="Annual Cost Comparison: Current situation vs. Combined system (€/year)",
            font=dict(size=15, color="#F8FAFC"),
            x=0.0,
        ),
        yaxis=dict(
            title="Annual Cost (€/year)",
            gridcolor="rgba(148, 163, 184, 0.12)",
            rangemode="tozero",
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.04,
            xanchor="left",
            x=0.0,
            bgcolor="rgba(0,0,0,0)",
            font=dict(size=11),
        ),
        hovermode="x unified",
    )

    return fig
