"""
Lightweight Plotly Text-Overlay Helpers for BESS & Solar Phase Energies
(`charts/phase_overlay_helpers.py`).

Produces compact Python-list-backed `go.Scatter(mode="text")` traces so 60 FPS
WebGL dispatch traces stay untouched and `dispatch_and_mix_charts.py` stays well
below the 960-line architectural limit.
"""

from typing import Any, List
import plotly.graph_objects as go

from ..combined_sandbox_engine import (
    BessPhaseEventsResult,
    SolarPhaseEventsResult,
)


def _make_phase_text_trace(
    x: List[Any],
    y: List[float],
    text: List[str],
    hover: List[str],
    name: str,
    legendgroup: str,
    showlegend: bool,
    visible: Any,
    textposition: str,
    color: str,
) -> go.Scatter:
    """Builds a lightweight `go.Scatter(mode='text')` overlay trace from Python lists."""
    return go.Scatter(
        x=list(x),
        y=[float(v) for v in y],
        text=list(text),
        customdata=list(hover),
        mode="text",
        name=name,
        legendgroup=legendgroup,
        showlegend=showlegend,
        visible=visible,
        cliponaxis=True,
        textposition=textposition,
        textfont=dict(color=color, size=10),
        hovertemplate="%{customdata}<extra></extra>",
    )


def build_bess_phase_label_traces(
    phase_res: BessPhaseEventsResult,
    show_phase_labels: bool = False,
) -> List[go.Scatter]:
    """
    Returns legend-toggleable `go.Scatter(mode="text")` peak/valley label traces
    showing delivered AC energy (`kWh`) per Charge and Discharge phase.
    """
    vis: Any = True if show_phase_labels else "legendonly"
    traces: List[go.Scatter] = []
    has_dis = bool(phase_res.dis_label_x)

    if has_dis:
        traces.append(
            _make_phase_text_trace(
                phase_res.dis_label_x, phase_res.dis_label_y, phase_res.dis_label_text,
                phase_res.dis_label_hover, "BESS Phase Energy (kWh)", "bess_phase_labels",
                True, vis, "top center", "#4ADE80",
            )
        )
    if phase_res.chg_label_x:
        traces.append(
            _make_phase_text_trace(
                phase_res.chg_label_x, phase_res.chg_label_y, phase_res.chg_label_text,
                phase_res.chg_label_hover, "BESS Phase Energy (kWh)", "bess_phase_labels",
                not has_dis, vis, "bottom center", "#22D3EE",
            )
        )
    return traces


def build_solar_direct_label_traces(
    solar_res: SolarPhaseEventsResult,
    show_phase_labels: bool = False,
) -> List[go.Scatter]:
    """Returns legend-toggleable `Solar Direct Phase (kWh)` peak label trace for integrated dispatch."""
    if not solar_res.dir_label_x:
        return []
    vis: Any = True if show_phase_labels else "legendonly"
    return [
        _make_phase_text_trace(
            solar_res.dir_label_x, solar_res.dir_label_y, solar_res.dir_label_text,
            solar_res.dir_label_hover, "Solar Direct Phase (kWh)", "solar_direct_phase_labels",
            True, vis, "top center", "#FACC15",
        )
    ]


def build_solar_production_label_traces(
    solar_res: SolarPhaseEventsResult,
    show_phase_labels: bool = False,
) -> List[go.Scatter]:
    """Returns legend-toggleable `Solar Phase Energy (kWh)` peak label trace for standalone Solar Production."""
    if not solar_res.prod_label_x:
        return []
    vis: Any = True if show_phase_labels else "legendonly"
    return [
        _make_phase_text_trace(
            solar_res.prod_label_x, solar_res.prod_label_y, solar_res.prod_label_text,
            solar_res.prod_label_hover, "Solar Phase Energy (kWh)", "solar_prod_phase_labels",
            True, vis, "top center", "#FACC15",
        )
    ]
