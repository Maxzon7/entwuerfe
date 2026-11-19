"""
Interactive Plotly (`plotly_dark` + GPU WebGL) 15-Minute Load Profile Comparison chart
for Sub-Tab 7 (`ui_sandbox/Combined_sandbox/charts/`, Stage 1.6 — `1..N` Ready):
  - `create_ab_load_profile_overlay_figure`: Synchronized 15-Min Grid Load & BESS SoC (%) overlay

Operates strictly on stored `np.float32` snapshot vectors with zero dispatch re-execution.
"""

from typing import List, Optional, Sequence, Tuple
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from ..combined_sandbox_engine import (
    CombinedScenarioSnapshot,
    normalize_scenario_list,
)
from .scenario_comparison_charts import (
    BASELINE_LINE_COLOR,
    _short_slot_label,
    _palette_style,
    _apply_comparison_layout,
    _empty_comparison_figure,
)


def _resolve_baseline_and_profile_snaps(
    snap_a: Optional[CombinedScenarioSnapshot] = None,
    snap_b: Optional[CombinedScenarioSnapshot] = None,
    baseline_load_kw: Optional[np.ndarray] = None,
    scenarios: Optional[Sequence[CombinedScenarioSnapshot]] = None,
) -> Tuple[List[CombinedScenarioSnapshot], List[CombinedScenarioSnapshot], Optional[np.ndarray]]:
    """Filters ordered snapshots to those containing 15-min `grid_import_kw_f32` vectors."""
    items = normalize_scenario_list(snap_a, snap_b, scenarios=scenarios)
    prof_snaps = [s for s in items if getattr(s, "grid_import_kw_f32", None) is not None and len(s.grid_import_kw_f32) > 0]
    base_arr = (
        np.asarray(baseline_load_kw, dtype=np.float32)
        if baseline_load_kw is not None and len(baseline_load_kw) > 0
        else None
    )
    return items, prof_snaps, base_arr


def _resolve_profile_window(base_arr: Optional[np.ndarray], n_steps: int, timeframe: str) -> Tuple[int, int]:
    """Centers an optional inspection window (`24h`, `7D`, `30D`) or returns full year (`All` / `Full Year`)."""
    tf = str(timeframe or "Full Year")
    if n_steps <= 0 or tf in ("All", "Full Year"):
        return 0, n_steps

    span_map = {
        "24h": 96,
        "Peak Day (24h)": 96,
        "7D": 7 * 96,
        "Peak Week (7D)": 7 * 96,
        "30D": 30 * 96,
        "Peak Month (30D)": 30 * 96,
    }
    span = span_map.get(tf)
    if span is None or span >= n_steps:
        return 0, n_steps

    peak_idx = int(np.argmax(base_arr)) if (base_arr is not None and len(base_arr) == n_steps) else (n_steps // 2)
    half_w = span // 2
    start_i = max(0, peak_idx - half_w)
    end_i = min(n_steps, start_i + span)
    start_i = max(0, end_i - span)
    return start_i, end_i


def create_ab_load_profile_overlay_figure(
    snap_a: Optional[CombinedScenarioSnapshot] = None,
    snap_b: Optional[CombinedScenarioSnapshot] = None,
    baseline_load_kw: Optional[np.ndarray] = None,
    timestamps: Optional[pd.DatetimeIndex] = None,
    timeframe: str = "Full Year",
    height: int = 500,
    scenarios: Optional[Sequence[CombinedScenarioSnapshot]] = None,
) -> go.Figure:
    """
    Synchronized 2-row WebGL comparison comparing full-year 15-minute residual grid load profiles (kW)
    against the original facility load and contracted Grid Limit, paired with Battery SoC (%).
    """
    _, prof_snaps, base_arr = _resolve_baseline_and_profile_snaps(
        snap_a, snap_b, baseline_load_kw=baseline_load_kw, scenarios=scenarios
    )
    if not prof_snaps:
        return _empty_comparison_figure(
            "15-Minute Load Profile & Battery SoC Overlay",
            height=height,
            message="Re-save Scenario A / B to capture 15-minute profile data for visual load comparison.",
        )

    n_steps = len(prof_snaps[0].grid_import_kw_f32)
    if timestamps is not None and len(timestamps) == n_steps:
        ts_idx = timestamps
    else:
        ts_idx = pd.date_range("2025-01-01 00:00:00", periods=n_steps, freq="15min")

    ref_arr = base_arr if (base_arr is not None and len(base_arr) == n_steps) else prof_snaps[0].grid_import_kw_f32
    s_i, e_i = _resolve_profile_window(ref_arr, n_steps, timeframe)
    x_slice = ts_idx[s_i:e_i]
    grid_limit_kw = float(prof_snaps[0].system_config.grid_limit_kw)

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.09,
        row_heights=[0.64, 0.36],
        subplot_titles=(
            "1. 15-Minute Residual Grid Load Comparison (kW) vs. Grid Limit",
            "2. Synchronized Battery State of Charge (SoC %)",
        ),
    )

    if base_arr is not None and len(base_arr) == n_steps:
        fig.add_trace(
            go.Scattergl(
                x=x_slice,
                y=base_arr[s_i:e_i],
                mode="lines",
                name="Current Load",
                line=dict(color=BASELINE_LINE_COLOR, width=1.6, dash="dash"),
                hovertemplate="%{x}<br>Original Load: %{y:,.1f} kW<extra></extra>",
            ),
            row=1,
            col=1,
        )

    any_bess_trace = False
    for idx_s, snap in enumerate(prof_snaps):
        color, _ = _palette_style(idx_s)
        slot_id = snap.slot_id or str(idx_s + 1)
        lbl = _short_slot_label(slot_id, snap.name, max_len=20)
        imp_slice = snap.grid_import_kw_f32[s_i:e_i]
        fig.add_trace(
            go.Scattergl(
                x=x_slice,
                y=imp_slice,
                mode="lines",
                name=f"{lbl} (Grid)",
                line=dict(color=color, width=2.0),
                legendgroup=f"prof_{idx_s}",
                hovertemplate=f"{lbl} Grid Import: %{{y:,.1f}} kW<extra></extra>",
            ),
            row=1,
            col=1,
        )

        if snap.system_config.enable_battery and getattr(snap, "bess_soc_pct_f32", None) is not None and len(snap.bess_soc_pct_f32) == n_steps:
            any_bess_trace = True
            fig.add_trace(
                go.Scattergl(
                    x=x_slice,
                    y=snap.bess_soc_pct_f32[s_i:e_i],
                    mode="lines",
                    name=f"{lbl} (SoC %)",
                    line=dict(color=color, width=1.8, dash="dot" if idx_s % 2 == 1 else "solid"),
                    legendgroup=f"prof_{idx_s}",
                    hovertemplate=f"{lbl} Battery SoC: %{{y:.1f}}%<extra></extra>",
                ),
                row=2,
                col=1,
            )

    fig.add_hline(
        y=grid_limit_kw,
        row=1,
        col=1,
        line_dash="dot",
        line_color="#FACC15",
        line_width=1.6,
        annotation_text=f"Grid Limit ({grid_limit_kw:,.0f} kW)",
        annotation_position="top left",
        annotation_font_color="#FDE047",
    )

    if not any_bess_trace and len(x_slice) > 0:
        fig.add_annotation(
            text="Battery storage is disabled across saved scenarios.",
            xref="x2 domain",
            yref="y2 domain",
            x=0.5,
            y=0.5,
            showarrow=False,
            font=dict(size=12, color="#94A3B8"),
        )

    fig.update_yaxes(title_text="Grid Power (kW)", rangemode="tozero", gridcolor="rgba(148, 163, 184, 0.12)", row=1, col=1)
    fig.update_yaxes(title_text="Battery SoC (%)", range=[-2, 105], gridcolor="rgba(148, 163, 184, 0.12)", row=2, col=1)
    fig.update_xaxes(gridcolor="rgba(148, 163, 184, 0.08)", row=2, col=1)
    _apply_comparison_layout(
        fig,
        f"15-Minute Residual Load Profile & Battery SoC Comparison ({timeframe})",
        height,
        margin_t=135,
        legend_y=1.09,
        hovermode="x unified",
    )
    return fig


def sync_side_by_side_yaxis(
    fig_a: go.Figure,
    fig_b: go.Figure,
    axes: Sequence[str] = ("yaxis",),
) -> Tuple[go.Figure, go.Figure]:
    """
    Synchronizes Y-axis ranges across two side-by-side Plotly figures so bars and curves
    use identical vertical scaling for direct 1:1 visual comparison.
    """
    if fig_a is None or fig_b is None or not fig_a.data or not fig_b.data:
        return fig_a, fig_b

    for ax_name in axes:
        ax_short = "y" if ax_name == "yaxis" else f"y{ax_name[len('yaxis'):]}"
        y_vals: List[float] = []
        for fig in (fig_a, fig_b):
            for tr in fig.data:
                tr_ax = getattr(tr, "yaxis", None) or "y"
                if tr_ax != ax_short:
                    continue
                arr = getattr(tr, "y", None)
                if arr is None:
                    continue
                num = np.asarray(arr, dtype=float)
                finite = num[np.isfinite(num)]
                if finite.size > 0:
                    y_vals.append(float(np.min(finite)))
                    y_vals.append(float(np.max(finite)))
            for shp in (getattr(fig.layout, "shapes", None) or ()):
                shp_yref = getattr(shp, "yref", None) or "y"
                if shp_yref == ax_short:
                    for attr in ("y0", "y1"):
                        sv = getattr(shp, attr, None)
                        if isinstance(sv, (int, float)) and np.isfinite(sv):
                            y_vals.append(float(sv))

        if not y_vals:
            continue
        raw_min = min(y_vals)
        raw_max = max(y_vals)
        span = max(1.0, raw_max - raw_min)
        pad = span * 0.08
        lo = (raw_min - pad) if raw_min < 0.0 else 0.0
        hi = (raw_max + pad) if raw_max >= 0.0 else 0.0
        if hi <= lo:
            hi = lo + 1.0
        for fig in (fig_a, fig_b):
            fig.layout[ax_name].update(range=[lo, hi], autorange=False)

    return fig_a, fig_b
