"""
Print-optimized Plotly chart snapshot exporter (`pdf_report/chart_snapshots.py`).

Clones active Plotly figures into a clean light-mode print palette and renders
high-DPI PNG data URIs via `kaleido` for embedding inside WeasyPrint A4 pages.
Uses lightweight 2D `go.Scatter` on the 7-day peak window for the dispatch chart
instead of 35,040-point WebGL traces.
"""

import base64
import copy
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from ..combined_sandbox_engine import (
    CombinedScenarioSnapshot,
    CombinedSimulationResult,
    compute_system_utilization_diagnostics,
    get_plotly_separators,
)
from ..charts.dispatch_and_mix_charts import (
    compute_focus_range_for_timestamps,
    create_component_utilization_bars_figure,
    create_supply_mix_pie_figure,
)
from ..charts.financial_overview_charts import (
    create_financial_tco_trajectory_figure,
    create_financial_waterfall_bridge_figure,
)
from ..charts.scenario_comparison_charts import create_ab_15y_tco_comparison_figure


_LIGHT_COLORS_TO_DARKEN = {
    "#F8FAFC": "#0F172A",
    "#E2E8F0": "#1E293B",
    "#CBD5E1": "#334155",
    "#94A3B8": "#475569",
    "#FACC15": "#D97706",
    "#C4B5FD": "#6D28D9",
    "#F87171": "#DC2626",
}


def _darken_color_if_light(color_val: Any) -> Any:
    """Replaces light-on-dark UI colors with crisp print-readable shades."""
    if not isinstance(color_val, str):
        return color_val
    upper = color_val.strip().upper()
    if upper in _LIGHT_COLORS_TO_DARKEN:
        return _LIGHT_COLORS_TO_DARKEN[upper]
    if "248, 250, 252" in color_val or "248,250,252" in color_val:
        return "rgba(100, 116, 139, 0.55)"
    if "255, 255, 255" in color_val or "255,255,255" in color_val:
        return "rgba(30, 41, 59, 0.35)"
    return color_val


def apply_print_light_theme(fig: go.Figure, height: Optional[int] = None) -> go.Figure:
    """Returns a deep-copied Plotly figure restyled for crisp light-mode A4 printing."""
    out = copy.deepcopy(fig)
    layout_updates: Dict[str, Any] = {
        "template": "plotly_white",
        "separators": get_plotly_separators(),
        "paper_bgcolor": "rgba(255, 255, 255, 0.0)",
        "plot_bgcolor": "rgba(255, 255, 255, 0.92)",
        "font": dict(color="#1E293B", family="Arial, Helvetica, sans-serif", size=11),
    }
    if height is not None:
        layout_updates["height"] = int(height)

    if out.layout.title and out.layout.title.text:
        layout_updates["title_font"] = dict(color="#0F172A", size=13)
    if out.layout.legend:
        layout_updates["legend_font"] = dict(color="#1E293B", size=10)
        layout_updates["legend_bgcolor"] = "rgba(255, 255, 255, 0.75)"

    out.update_layout(**layout_updates)

    for axis_key in list(out.layout.to_plotly_json().keys()):
        if axis_key.startswith("xaxis") or axis_key.startswith("yaxis"):
            axis_obj = getattr(out.layout, axis_key, None)
            if axis_obj is not None:
                axis_obj.update(
                    gridcolor="rgba(148, 163, 184, 0.28)",
                    zerolinecolor="rgba(100, 116, 139, 0.55)",
                    tickfont=dict(color="#334155", size=10),
                    title_font=dict(color="#1E293B", size=11),
                )

    for shape in out.layout.shapes or ():
        if getattr(shape, "line", None) and getattr(shape.line, "color", None):
            shape.line.color = _darken_color_if_light(shape.line.color)

    for ann in out.layout.annotations or ():
        if getattr(ann, "font", None) and getattr(ann.font, "color", None):
            ann.font.color = _darken_color_if_light(ann.font.color)

    for tr in out.data:
        tr_json = tr.to_plotly_json()
        if "line" in tr_json and isinstance(tr_json["line"], dict):
            col = tr_json["line"].get("color")
            if col:
                tr.line.color = _darken_color_if_light(col)
        if tr_json.get("type") == "pie" and getattr(tr, "textfont", None):
            tr.textfont.color = "#0F172A"

    return out


def render_plotly_png_data_uri(
    fig: go.Figure,
    width: int = 960,
    height: int = 400,
    scale: float = 2.0,
) -> Optional[str]:
    """Renders a Plotly figure to a base64 PNG data URI via Kaleido, or None if empty."""
    if fig is None or not fig.data:
        return None
    themed = apply_print_light_theme(fig, height=height)
    png_bytes = themed.to_image(format="png", width=width, height=height, scale=scale)
    b64 = base64.b64encode(png_bytes).decode("ascii")
    return f"data:image/png;base64,{b64}"


def create_peak_week_dispatch_print_figure(sim_res: CombinedSimulationResult) -> go.Figure:
    """
    Creates a lightweight 2D SVG `go.Scatter` snapshot focused on the 7-day peak
    window for crisp PDF export without 35,040-point WebGL traces.
    """
    ts = pd.DatetimeIndex(sim_res.timestamps)
    is_gap = getattr(sim_res, "is_gap", None)
    safe_load = (
        np.where(np.asarray(is_gap, dtype=bool), 0.0, sim_res.load_kw)
        if is_gap is not None and len(is_gap) == len(ts)
        else sim_res.load_kw
    )
    focus_range = compute_focus_range_for_timestamps(ts, safe_load, days=7.0)
    if focus_range and len(focus_range) == 2:
        focus_start, focus_end = focus_range
        mask = (ts >= pd.Timestamp(focus_start)) & (ts <= pd.Timestamp(focus_end))
    else:
        mask = np.zeros(len(ts), dtype=bool)
    if not np.any(mask):
        mask = np.ones(len(ts), dtype=bool)
        if len(ts) > 672:
            mask[672:] = False

    idx = np.where(mask)[0]
    ts_w = ts[idx]
    gap_w = np.asarray(is_gap[idx], dtype=bool) if is_gap is not None and len(is_gap) == len(ts) else None

    def _clean(arr: np.ndarray) -> np.ndarray:
        vals = np.asarray(arr[idx], dtype=float).copy()
        if gap_w is not None:
            vals[gap_w] = np.nan
        return vals

    cfg = sim_res.system_config
    fig = make_subplots(
        rows=2 if cfg.enable_battery else 1,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.10,
        row_heights=[0.65, 0.35] if cfg.enable_battery else [1.0],
        subplot_titles=(
            ("Peak-Week 15-Minute Power Dispatch (kW)", "Battery State of Charge (%)")
            if cfg.enable_battery
            else ("Peak-Week 15-Minute Power Dispatch (kW)",)
        ),
    )

    fig.add_trace(
        go.Scatter(
            x=ts_w,
            y=_clean(sim_res.load_kw),
            name="Facility Load (kW)",
            line=dict(color="#475569", width=1.6),
            connectgaps=False,
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=ts_w,
            y=_clean(sim_res.grid_import_kw),
            name="Grid Import (kW)",
            line=dict(color="#2563EB", width=1.8),
            connectgaps=False,
        ),
        row=1,
        col=1,
    )
    if cfg.enable_solar:
        fig.add_trace(
            go.Scatter(
                x=ts_w,
                y=_clean(sim_res.solar_direct_kw),
                name="Solar Direct (kW)",
                line=dict(color="#D97706", width=1.3),
                fill="tozeroy",
                fillcolor="rgba(217, 119, 6, 0.16)",
                connectgaps=False,
            ),
            row=1,
            col=1,
        )
    if cfg.enable_battery:
        fig.add_trace(
            go.Scatter(
                x=ts_w,
                y=_clean(sim_res.bess_discharge_kw),
                name="BESS Discharge (kW)",
                line=dict(color="#16A34A", width=1.3),
                fill="tozeroy",
                fillcolor="rgba(22, 163, 74, 0.18)",
                connectgaps=False,
            ),
            row=1,
            col=1,
        )
    if cfg.enable_generator:
        fig.add_trace(
            go.Scatter(
                x=ts_w,
                y=_clean(sim_res.gen_output_kw),
                name="Generator Output (kW)",
                line=dict(color="#EA580C", width=1.5),
                fill="tozeroy",
                fillcolor="rgba(234, 88, 12, 0.18)",
                connectgaps=False,
            ),
            row=1,
            col=1,
        )

    unmet_w = _clean(sim_res.unmet_overload_kw)
    if np.nanmax(np.nan_to_num(unmet_w, nan=0.0)) > 0.1:
        fig.add_trace(
            go.Scatter(
                x=ts_w,
                y=unmet_w,
                name="Remaining Overload (kW)",
                line=dict(color="#DC2626", width=1.4),
                fill="tozeroy",
                fillcolor="rgba(220, 38, 38, 0.20)",
                connectgaps=False,
            ),
            row=1,
            col=1,
        )

    fig.add_hline(
        y=float(cfg.grid_limit_kw),
        row=1,
        col=1,
        line_dash="dash",
        line_color="#DC2626",
        line_width=1.4,
        annotation_text=f"Grid Limit ({cfg.grid_limit_kw:,.0f} kW)",
        annotation_position="top left",
        annotation_font=dict(color="#DC2626", size=10),
    )

    if cfg.enable_battery:
        fig.add_trace(
            go.Scatter(
                x=ts_w,
                y=_clean(sim_res.bess_soc_pct),
                name="Battery SoC (%)",
                line=dict(color="#7C3AED", width=1.8),
                fill="tozeroy",
                fillcolor="rgba(124, 58, 237, 0.14)",
                connectgaps=False,
            ),
            row=2,
            col=1,
        )
        fig.update_yaxes(title_text="SoC (%)", range=[0, 105], row=2, col=1)

    fig.update_yaxes(title_text="Power (kW)", row=1, col=1)
    fig.update_layout(
        margin=dict(l=55, r=25, t=65, b=35),
        legend=dict(orientation="h", yanchor="bottom", y=1.08, xanchor="left", x=0.0, font=dict(size=9.5)),
    )
    return fig


def collect_report_chart_data_uris(
    sim_res: CombinedSimulationResult,
    saved_scenarios: Optional[Dict[str, CombinedScenarioSnapshot]] = None,
) -> Dict[str, str]:
    """Renders all applicable print-themed PNG chart snapshots for the PDF report."""
    charts: Dict[str, str] = {}

    dispatch_uri = render_plotly_png_data_uri(
        create_peak_week_dispatch_print_figure(sim_res),
        width=980,
        height=440 if sim_res.system_config.enable_battery else 330,
    )
    if dispatch_uri:
        charts["dispatch_peak_week"] = dispatch_uri

    diag = compute_system_utilization_diagnostics(sim_res)

    mix_uri = render_plotly_png_data_uri(
        create_supply_mix_pie_figure(diag),
        width=540,
        height=340,
    )
    if mix_uri:
        charts["supply_mix"] = mix_uri

    util_uri = render_plotly_png_data_uri(
        create_component_utilization_bars_figure(diag),
        width=560,
        height=340,
    )
    if util_uri:
        charts["asset_utilization"] = util_uri

    if sim_res.system_config.enable_financials and sim_res.financial_kpis is not None:
        tco_uri = render_plotly_png_data_uri(
            create_financial_tco_trajectory_figure(sim_res),
            width=980,
            height=480,
        )
        if tco_uri:
            charts["financial_tco"] = tco_uri

        wf_uri = render_plotly_png_data_uri(
            create_financial_waterfall_bridge_figure(sim_res),
            width=960,
            height=360,
        )
        if wf_uri:
            charts["financial_waterfall"] = wf_uri

    if isinstance(saved_scenarios, dict):
        snap_a = saved_scenarios.get("A")
        snap_b = saved_scenarios.get("B")
        if snap_a is not None or snap_b is not None:
            ab_uri = render_plotly_png_data_uri(
                create_ab_15y_tco_comparison_figure(snap_a, snap_b, height=350),
                width=960,
                height=350,
            )
            if ab_uri:
                charts["ab_tco_comparison"] = ab_uri

    return charts
