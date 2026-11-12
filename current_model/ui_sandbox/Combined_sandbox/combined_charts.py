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
    p_load = np.asarray(sim_res.load_kw, dtype=np.float32)
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

    # Mask measurement data gaps with NaN so Plotly connectgaps=False leaves intervals visually blank
    is_gap = getattr(sim_res, "is_gap", None)
    if is_gap is not None and np.any(is_gap):
        gap_b = np.asarray(is_gap, dtype=bool)
        p_load = np.where(gap_b, np.nan, p_load)
        p_solar_dir = np.where(gap_b, np.nan, p_solar_dir)
        p_bess_dis = np.where(gap_b, np.nan, p_bess_dis)
        p_bess_chg = np.where(gap_b, np.nan, p_bess_chg)
        p_unmet = np.where(gap_b, np.nan, p_unmet)
        p_gen_out = np.where(gap_b, np.nan, p_gen_out)
        p_grid_imp = np.where(gap_b, np.nan, p_grid_imp)
        soc_pct = np.where(gap_b, np.nan, soc_pct)
        soc_kwh = np.where(gap_b, np.nan, soc_kwh)
        gen_active_pct = np.where(gap_b, np.nan, gen_active_pct)

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

    # 3. Solar Direct (when enabled)
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


def create_financial_tco_trajectory_figure(
    sim_res: CombinedSimulationResult,
) -> go.Figure:
    """
    Creates the 15-Year Cumulative TCO & Break-Even Trajectory figure,
    comparing cumulative expenditures of Current situation vs. Combined system,
    with annual net cashflow bars and break-even point indicator.
    """
    df = sim_res.cashflow_15y_df
    fk = sim_res.financial_kpis
    if df.empty or fk is None:
        return go.Figure()

    years = df["Year"].tolist()
    tco_base = df["Cumulative TCO Current situation (€)"].tolist()
    tco_comb = df["Cumulative TCO Combined system (€)"].tolist()
    net_cf = df["Net Cashflow (€)"].tolist()

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # Background annual cashflow bars (secondary y-axis)
    bar_colors = ["#22C55E" if v >= 0 else "#EF4444" for v in net_cf]
    fig.add_trace(
        go.Bar(
            x=years,
            y=net_cf,
            name="Annual Net Cashflow (€)",
            marker_color=bar_colors,
            opacity=0.35,
            hovertemplate="Year %{x}<br>Net Cashflow: €%{y:,.0f}<extra></extra>",
        ),
        secondary_y=True,
    )

    # Current situation TCO line
    fig.add_trace(
        go.Scatter(
            x=years,
            y=tco_base,
            mode="lines+markers",
            name="Current situation TCO (€)",
            line=dict(color="#F87171", width=2.2, dash="dash"),
            hovertemplate="Year %{x}<br>Current situation TCO: €%{y:,.0f}<extra></extra>",
        ),
        secondary_y=False,
    )

    # Combined system TCO line
    fig.add_trace(
        go.Scatter(
            x=years,
            y=tco_comb,
            mode="lines+markers",
            name="Combined system TCO (€)",
            line=dict(color="#38BDF8", width=2.8),
            hovertemplate="Year %{x}<br>Combined system TCO: €%{y:,.0f}<extra></extra>",
        ),
        secondary_y=False,
    )

    # Break-Even indicator if payback occurs
    if fk.payback_years is not None and 0.0 < fk.payback_years <= 15.0:
        fig.add_vline(
            x=fk.payback_years,
            line_dash="dot",
            line_color="#22C55E",
            line_width=1.5,
            annotation_text=f"Break-Even: {fk.payback_years:.1f} yrs",
            annotation_position="top left",
            annotation_font=dict(color="#22C55E", size=11),
        )

    fig.update_layout(
        template="plotly_dark",
        height=430,
        margin=dict(l=55, r=55, t=75, b=45),
        paper_bgcolor="rgba(15, 23, 42, 0.0)",
        plot_bgcolor="rgba(15, 23, 42, 0.45)",
        title=dict(
            text="15-Year Cumulative TCO & Break-Even Trajectory (€)",
            font=dict(size=15, color="#F8FAFC"),
            x=0.0,
        ),
        xaxis=dict(
            title="Project Lifecycle (Years)",
            gridcolor="rgba(148, 163, 184, 0.12)",
            tickmode="linear",
            tick0=0,
            dtick=1,
        ),
        yaxis=dict(
            title="Cumulative TCO (€)",
            gridcolor="rgba(148, 163, 184, 0.12)",
            rangemode="tozero",
        ),
        yaxis2=dict(
            title="Annual Net Cashflow (€)",
            gridcolor="rgba(0,0,0,0)",
            overlaying="y",
            side="right",
            showgrid=False,
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


def create_financial_waterfall_bridge_figure(
    sim_res: CombinedSimulationResult,
) -> go.Figure:
    """
    Creates the Year-1 Annual Cost Bridge Waterfall chart, decomposing the transition
    from Current situation Bill down to Combined System Net OPEX.
    """
    fk = sim_res.financial_kpis
    if fk is None:
        return go.Figure()

    supply_sav = -(fk.baseline_pillar1_supply_eur - fk.combined_pillar1_supply_eur)
    dso_base_net = max(0.0, fk.baseline_pillar2_dso_eur - fk.baseline_penalty_cost_eur)
    dso_comb_net = max(0.0, fk.combined_pillar2_dso_eur - fk.combined_grid_penalty_cost_eur)
    dso_sav = -(dso_base_net - dso_comb_net)
    pen_sav = -(fk.baseline_penalty_cost_eur - fk.combined_grid_penalty_cost_eur)
    tax_sav = -(fk.baseline_pillar4_taxes_eur - fk.combined_pillar4_taxes_eur)
    export_rev = -fk.solar_export_revenue_eur
    sol_om = fk.solar_om_eur
    bat_om = fk.battery_om_eur
    gen_opex = fk.generator_total_opex_eur

    x_labels = ["Current situation Bill"]
    y_vals = [fk.baseline_total_opex_eur]
    measures = ["absolute"]

    if abs(supply_sav) > 0.5:
        x_labels.append("Supply Savings")
        y_vals.append(supply_sav)
        measures.append("relative")

    if abs(dso_sav) > 0.5:
        x_labels.append("Grid Capacity Savings")
        y_vals.append(dso_sav)
        measures.append("relative")

    if abs(pen_sav) > 0.5:
        x_labels.append("Avoided Penalties")
        y_vals.append(pen_sav)
        measures.append("relative")

    if abs(tax_sav) > 0.5:
        x_labels.append("Tax Reductions")
        y_vals.append(tax_sav)
        measures.append("relative")

    if abs(export_rev) > 0.5:
        x_labels.append("Solar Feed-in Export")
        y_vals.append(export_rev)
        measures.append("relative")

    if sol_om > 0.5:
        x_labels.append("Solar O&M")
        y_vals.append(sol_om)
        measures.append("relative")

    if bat_om > 0.5:
        x_labels.append("Battery O&M")
        y_vals.append(bat_om)
        measures.append("relative")

    if gen_opex > 0.5:
        x_labels.append("Generator OPEX")
        y_vals.append(gen_opex)
        measures.append("relative")

    x_labels.append("Combined System Net OPEX")
    y_vals.append(0.0)
    measures.append("total")

    fig = go.Figure(
        go.Waterfall(
            name="Cost Bridge",
            orientation="v",
            measure=measures,
            x=x_labels,
            y=y_vals,
            textposition="outside",
            text=[f"€{abs(v):,.0f}" if m != "total" else f"€{fk.total_annual_opex_eur:,.0f}" for v, m in zip(y_vals, measures)],
            connector={"line": {"color": "rgba(148, 163, 184, 0.4)"}},
            decreasing={"marker": {"color": "#22C55E"}},
            increasing={"marker": {"color": "#EF4444"}},
            totals={"marker": {"color": "#3B82F6"}},
            hovertemplate="%{x}<br>Amount: €%{y:,.0f}<extra></extra>",
        )
    )

    fig.update_layout(
        template="plotly_dark",
        height=430,
        margin=dict(l=55, r=25, t=75, b=65),
        paper_bgcolor="rgba(15, 23, 42, 0.0)",
        plot_bgcolor="rgba(15, 23, 42, 0.45)",
        title=dict(
            text="Year-1 Annual Cost Bridge: Current situation to Combined System (€/year)",
            font=dict(size=15, color="#F8FAFC"),
            x=0.0,
        ),
        yaxis=dict(
            title="Annual Cost (€/year)",
            gridcolor="rgba(148, 163, 184, 0.12)",
        ),
        xaxis=dict(
            tickangle=-25,
            gridcolor="rgba(148, 163, 184, 0.12)",
        ),
        hovermode="x unified",
    )

    return fig


def create_financial_monthly_cashflow_figure(
    sim_res: CombinedSimulationResult,
) -> go.Figure:
    """
    Creates the 12-Month Seasonal Financial Cashflow Chart,
    comparing monthly Current situation bills vs. Combined system OPEX,
    with an overlaid line for monthly net savings.
    """
    m_df = sim_res.monthly_cost_df
    if m_df.empty:
        return go.Figure()

    months = m_df["Month"].tolist()
    base_bills = m_df["Current situation Total (€)"].tolist()
    comb_opex = m_df["Combined System Total OPEX (€)"].tolist()
    m_savings = m_df["Monthly Savings (€)"].tolist()

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    fig.add_trace(
        go.Bar(
            x=months,
            y=base_bills,
            name="Current situation Bill (€)",
            marker_color="#F87171",
            hovertemplate="%{x}<br>Current situation: €%{y:,.0f}<extra></extra>",
        ),
        secondary_y=False,
    )

    fig.add_trace(
        go.Bar(
            x=months,
            y=comb_opex,
            name="Combined System OPEX (€)",
            marker_color="#38BDF8",
            hovertemplate="%{x}<br>Combined System: €%{y:,.0f}<extra></extra>",
        ),
        secondary_y=False,
    )

    fig.add_trace(
        go.Scatter(
            x=months,
            y=m_savings,
            mode="lines+markers",
            name="Monthly Net Savings (€)",
            line=dict(color="#22C55E", width=2.4),
            marker=dict(size=7, color="#22C55E"),
            hovertemplate="%{x}<br>Monthly Savings: €%{y:,.0f}<extra></extra>",
        ),
        secondary_y=True,
    )

    fig.update_layout(
        barmode="group",
        template="plotly_dark",
        height=430,
        margin=dict(l=55, r=55, t=75, b=45),
        paper_bgcolor="rgba(15, 23, 42, 0.0)",
        plot_bgcolor="rgba(15, 23, 42, 0.45)",
        title=dict(
            text="12-Month Seasonal Financial Cashflow & Net Savings (€/month)",
            font=dict(size=15, color="#F8FAFC"),
            x=0.0,
        ),
        yaxis=dict(
            title="Monthly Expense (€/month)",
            gridcolor="rgba(148, 163, 184, 0.12)",
            rangemode="tozero",
        ),
        yaxis2=dict(
            title="Monthly Savings (€/month)",
            gridcolor="rgba(0,0,0,0)",
            overlaying="y",
            side="right",
            showgrid=False,
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
