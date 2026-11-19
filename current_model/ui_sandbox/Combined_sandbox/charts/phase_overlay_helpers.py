"""
Lightweight Plotly Text-Overlay Helper for BESS Charge/Discharge Phase Energies
(`charts/phase_overlay_helpers.py`).

Produces at most two Python-list-backed `go.Scatter(mode="text")` traces so 60 FPS
WebGL dispatch traces stay untouched and `dispatch_and_mix_charts.py` remains compact.
"""

from typing import List
import plotly.graph_objects as go

from ..combined_sandbox_engine import BessPhaseEventsResult


def build_bess_phase_label_traces(
    phase_res: BessPhaseEventsResult,
    show_phase_labels: bool = False,
) -> List[go.Scatter]:
    """
    Returns legend-toggleable `go.Scatter(mode="text")` peak/valley label traces
    showing delivered AC energy (`kWh`) per Charge and Discharge phase.
    """
    vis = True if show_phase_labels else "legendonly"
    traces: List[go.Scatter] = []
    has_dis = bool(phase_res.dis_label_x)
    has_chg = bool(phase_res.chg_label_x)

    if has_dis:
        traces.append(
            go.Scatter(
                x=list(phase_res.dis_label_x),
                y=[float(v) for v in phase_res.dis_label_y],
                text=list(phase_res.dis_label_text),
                customdata=list(phase_res.dis_label_hover),
                mode="text",
                name="BESS Phase Energy (kWh)",
                legendgroup="bess_phase_labels",
                showlegend=True,
                visible=vis,
                cliponaxis=True,
                textposition="top center",
                textfont=dict(color="#4ADE80", size=10),
                hovertemplate="%{customdata}<extra></extra>",
            )
        )

    if has_chg:
        traces.append(
            go.Scatter(
                x=list(phase_res.chg_label_x),
                y=[float(v) for v in phase_res.chg_label_y],
                text=list(phase_res.chg_label_text),
                customdata=list(phase_res.chg_label_hover),
                mode="text",
                name="BESS Phase Energy (kWh)",
                legendgroup="bess_phase_labels",
                showlegend=(not has_dis),
                visible=vis,
                cliponaxis=True,
                textposition="bottom center",
                textfont=dict(color="#22D3EE", size=10),
                hovertemplate="%{customdata}<extra></extra>",
            )
        )

    return traces
