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

from typing import Tuple
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


def create_combined_dispatch_soc_figure(
    sim_res: CombinedSimulationResult,
    timeframe: str = "7D",
) -> go.Figure:
    """
    Creates the Synchronized 2-in-1 15-Minute Master Chart:
      - Upper Subplot (Power Flow in kW):
          * Stacked supply layers: Grid Import, Solar Direct, Battery Discharge, Generator Output
          * Consumption (kW) line
          * Dashed red Grid Limit (kW) line
      - Lower Subplot (Synchronized X-Axis):
          * Battery Level (SoC % and kWh) + Reserve Threshold
          * Generator Active operating phases
    """
    s_idx, e_idx = _resolve_window_slice(
        sim_res.timestamps,
        sim_res.load_kw,
        timeframe=timeframe,
    )

    ts = sim_res.timestamps[s_idx:e_idx]
    p_load = sim_res.load_kw[s_idx:e_idx]
    p_solar_dir = sim_res.solar_direct_kw[s_idx:e_idx]
    p_bess_dis = sim_res.bess_discharge_kw[s_idx:e_idx]
    p_gen_out = sim_res.gen_output_kw[s_idx:e_idx]
    p_grid_imp = sim_res.grid_import_kw[s_idx:e_idx]
    soc_pct = sim_res.bess_soc_pct[s_idx:e_idx]
    soc_kwh = sim_res.bess_energy_kwh[s_idx:e_idx]
    gen_active_pct = np.where(sim_res.gen_running_mask[s_idx:e_idx], 100.0, 0.0)

    cfg = sim_res.system_config
    rules = sim_res.rules_config

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        row_heights=[0.65, 0.35],
        subplot_titles=(
            f"Power Flow ({timeframe})",
            "Battery Level & Generator",
        ),
    )

    # --- ROW 1: Stacked Supply Breakdown + Consumption + Grid Limit ---
    fig.add_trace(
        go.Scatter(
            x=ts,
            y=p_grid_imp,
            mode="lines",
            name="Grid Import (kW)",
            stackgroup="supply",
            line=dict(width=0.6, color="#3B82F6"),
            fillcolor="rgba(59, 130, 246, 0.45)",
            hovertemplate="Grid Import: %{y:,.1f} kW<extra></extra>",
        ),
        row=1,
        col=1,
    )

    if cfg.enable_solar:
        fig.add_trace(
            go.Scatter(
                x=ts,
                y=p_solar_dir,
                mode="lines",
                name="Solar Direct (kW)",
                stackgroup="supply",
                line=dict(width=0.6, color="#FACC15"),
                fillcolor="rgba(250, 204, 21, 0.55)",
                hovertemplate="Solar Direct: %{y:,.1f} kW<extra></extra>",
            ),
            row=1,
            col=1,
        )

    if cfg.enable_battery:
        fig.add_trace(
            go.Scatter(
                x=ts,
                y=p_bess_dis,
                mode="lines",
                name="Battery Discharge (kW)",
                stackgroup="supply",
                line=dict(width=0.6, color="#10B981"),
                fillcolor="rgba(16, 185, 129, 0.60)",
                hovertemplate="Battery Discharge: %{y:,.1f} kW<extra></extra>",
            ),
            row=1,
            col=1,
        )

    if cfg.enable_generator:
        fig.add_trace(
            go.Scatter(
                x=ts,
                y=p_gen_out,
                mode="lines",
                name="Generator Output (kW)",
                stackgroup="supply",
                line=dict(width=0.6, color="#F97316"),
                fillcolor="rgba(249, 115, 22, 0.65)",
                hovertemplate="Generator Output: %{y:,.1f} kW<extra></extra>",
            ),
            row=1,
            col=1,
        )

    # Consumption reference line
    fig.add_trace(
        go.Scatter(
            x=ts,
            y=p_load,
            mode="lines",
            name="Consumption (kW)",
            line=dict(color="#F8FAFC", width=1.7),
            hovertemplate="Consumption: %{y:,.1f} kW<extra></extra>",
        ),
        row=1,
        col=1,
    )

    # Red dashed Grid Limit line
    fig.add_trace(
        go.Scatter(
            x=ts,
            y=np.full(len(ts), cfg.grid_limit_kw),
            mode="lines",
            name=f"Grid Limit ({cfg.grid_limit_kw:,.0f} kW)",
            line=dict(color="#EF4444", width=2.0, dash="dash"),
            hovertemplate="Grid Limit: %{y:,.1f} kW<extra></extra>",
        ),
        row=1,
        col=1,
    )

    # --- ROW 2: Battery SoC (% & kWh) & Generator Active Phases ---
    if cfg.enable_generator:
        fig.add_trace(
            go.Scatter(
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
        )

    if cfg.enable_battery:
        fig.add_trace(
            go.Scatter(
                x=ts,
                y=soc_pct,
                customdata=soc_kwh,
                mode="lines",
                name=f"Battery Level (% of {cfg.battery_capacity_kwh:,.0f} kWh)",
                line=dict(color="#10B981", width=1.8),
                fill="tozeroy",
                fillcolor="rgba(16, 185, 129, 0.15)",
                hovertemplate="Battery Level: %{y:.1f}% (%{customdata:,.1f} kWh)<extra></extra>",
            ),
            row=2,
            col=1,
        )

        # Min SoC line
        fig.add_hline(
            y=cfg.min_soc_pct,
            line_dash="dot",
            line_color="#64748B",
            line_width=1.0,
            row=2,
            col=1,
        )

        # Peak Reserve SoC line if Self-Consumption + Peak Reserve is active
        if rules.rule2_battery_strategy == "self_consumption_reserve":
            fig.add_hline(
                y=rules.peak_reserve_soc_pct,
                line_dash="dash",
                line_color="#F59E0B",
                line_width=1.2,
                annotation_text=f"Peak Reserve ({rules.peak_reserve_soc_pct:.0f}%)",
                annotation_position="top right",
                annotation_font=dict(color="#F59E0B", size=10),
                row=2,
                col=1,
            )
    else:
        # Render a subtle zero-level baseline on row 2 when Battery is inactive so the shared x-axis remains synchronized
        fig.add_trace(
            go.Scatter(
                x=ts,
                y=np.zeros(len(ts)),
                mode="lines",
                name="Battery Level (Inactive)",
                line=dict(color="#475569", width=1.0, dash="dot"),
                hovertemplate="Battery Inactive (0%)<extra></extra>",
            ),
            row=2,
            col=1,
        )

    fig.update_layout(
        template="plotly_dark",
        height=640,
        margin=dict(l=55, r=25, t=95, b=45),
        paper_bgcolor="rgba(15, 23, 42, 0.0)",
        plot_bgcolor="rgba(15, 23, 42, 0.45)",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.12,
            xanchor="left",
            x=0.0,
            bgcolor="rgba(0,0,0,0)",
            font=dict(size=11),
        ),
        hovermode="x unified",
        uirevision=timeframe,
    )

    fig.update_yaxes(
        title_text="Power (kW)",
        gridcolor="rgba(148, 163, 184, 0.12)",
        rangemode="tozero",
        row=1,
        col=1,
    )
    fig.update_yaxes(
        title_text="Battery Level (%)",
        gridcolor="rgba(148, 163, 184, 0.12)",
        range=[0, 105],
        row=2,
        col=1,
    )
    fig.update_xaxes(
        gridcolor="rgba(148, 163, 184, 0.12)",
        rangeselector=dict(
            buttons=list([
                dict(count=7, label="7D", step="day", stepmode="backward"),
                dict(count=1, label="1M", step="month", stepmode="backward"),
                dict(count=3, label="3M", step="month", stepmode="backward"),
                dict(step="all", label="All"),
            ]),
            bgcolor="#1E293B",
            activecolor="#EF4444",
            font=dict(color="#F8FAFC", size=10),
        ),
        row=1,
        col=1,
    )
    fig.update_xaxes(
        title_text="Time (15-min intervals)",
        gridcolor="rgba(148, 163, 184, 0.12)",
        rangeslider=dict(visible=False),
        row=2,
        col=1,
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
