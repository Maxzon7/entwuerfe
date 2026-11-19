"""
Vectorized Solar Production & Direct Consumption Phase Segmentation (`engine/solar_phase_events.py`).

Reuses `_find_true_runs` and `_format_clock_span` from `engine/bess_phase_events.py` to
extract daytime Solar Production phases, Direct Self-Consumption phases, Battery solar
charging, Grid export, inverter clipping, hover suffixes, and peak label anchors.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .bess_phase_events import _find_true_runs, _format_clock_span
from .models_and_presets import CombinedSimulationResult


SOLAR_EVENT_LOG_COLUMNS: List[str] = [
    "Phase #",
    "Start",
    "End",
    "Daylight (h)",
    "Solar Production AC (kWh)",
    "Solar Direct (kWh)",
    "To Battery (kWh)",
    "Grid Export (kWh)",
    "Unclipped Potential (kWh)",
    "Clipped (kWh)",
    "Peak AC (kW)",
    "Utilization / Split",
]

STANDALONE_SOLAR_LOG_COLUMNS: List[str] = [
    "Phase #",
    "Start",
    "End",
    "Daylight (h)",
    "Solar Production AC (kWh)",
    "Unclipped Potential (kWh)",
    "Clipped (kWh)",
    "Peak AC (kW)",
    "Specific Yield (kWh/kWp)",
]


@dataclass
class SolarPhaseEventsResult:
    """Container for segmented Solar daylight/production phases and Plotly overlay arrays."""

    events_df: pd.DataFrame
    direct_hover_suffix: List[str] = field(default_factory=list)
    prod_hover_suffix: List[str] = field(default_factory=list)
    pot_hover_suffix: List[str] = field(default_factory=list)
    dir_label_x: List[Any] = field(default_factory=list)
    dir_label_y: List[float] = field(default_factory=list)
    dir_label_text: List[str] = field(default_factory=list)
    dir_label_hover: List[str] = field(default_factory=list)
    prod_label_x: List[Any] = field(default_factory=list)
    prod_label_y: List[float] = field(default_factory=list)
    prod_label_text: List[str] = field(default_factory=list)
    prod_label_hover: List[str] = field(default_factory=list)


def _format_solar_allocation_split(
    prod_kwh: float,
    dir_kwh: float,
    bess_kwh: float,
    exp_kwh: float,
) -> str:
    """Builds a concise percentage split string for Solar AC generation use."""
    if prod_kwh <= 1e-6:
        return "Idle"
    parts: List[str] = []
    for label, val in (("Direct", dir_kwh), ("BESS", bess_kwh), ("Export", exp_kwh)):
        pct = (val / prod_kwh) * 100.0
        if pct >= 1.0:
            parts.append(f"{label} {pct:.0f}%")
    return " / ".join(parts) if parts else "Direct/Export"


def _fmt_kwh_label(kwh: float) -> str:
    """Formats concise chart peak labels (`kWh`)."""
    return f"{kwh:,.0f} kWh" if kwh >= 10.0 else f"{kwh:,.1f} kWh"


def _build_solar_phase_core(
    timestamps: Any,
    solar_production_kw: np.ndarray,
    solar_potential_kw: Optional[np.ndarray],
    solar_direct_kw: Optional[np.ndarray] = None,
    bess_charge_solar_kw: Optional[np.ndarray] = None,
    solar_export_kw: Optional[np.ndarray] = None,
    is_gap: Optional[np.ndarray] = None,
    installed_kwp: float = 0.0,
    standalone_mode: bool = False,
    threshold_kw: float = 0.1,
) -> SolarPhaseEventsResult:
    """Shared vectorized phase segmentation for coupled and standalone Solar views."""
    n = len(timestamps) if timestamps is not None else 0
    cols = STANDALONE_SOLAR_LOG_COLUMNS if standalone_mode else SOLAR_EVENT_LOG_COLUMNS
    empty_df = pd.DataFrame(columns=cols)
    if n == 0:
        return SolarPhaseEventsResult(events_df=empty_df)

    ts = pd.DatetimeIndex(timestamps)
    dt = 0.25

    p_prod = np.maximum(0.0, np.asarray(solar_production_kw, dtype=float))
    p_pot_raw = np.maximum(0.0, np.asarray(solar_potential_kw, dtype=float)) if solar_potential_kw is not None else p_prod
    p_pot = np.maximum(p_prod, p_pot_raw)

    gap_b = (
        np.asarray(is_gap, dtype=bool)
        if is_gap is not None and len(is_gap) == n
        else np.zeros(n, dtype=bool)
    )

    p_dir = np.maximum(0.0, np.asarray(solar_direct_kw, dtype=float)) if solar_direct_kw is not None else np.zeros(n, dtype=float)
    p_bess = np.maximum(0.0, np.asarray(bess_charge_solar_kw, dtype=float)) if bess_charge_solar_kw is not None else np.zeros(n, dtype=float)
    p_exp = np.maximum(0.0, np.asarray(solar_export_kw, dtype=float)) if solar_export_kw is not None else np.zeros(n, dtype=float)

    active_prod_mask = (np.maximum(p_prod, p_pot) > threshold_kw) & (~gap_b)
    prod_runs = _find_true_runs(active_prod_mask)

    direct_hover_suffix = [""] * n
    prod_hover_suffix = [""] * n
    pot_hover_suffix = [""] * n

    dir_lx: List[Any] = []
    dir_ly: List[float] = []
    dir_ltxt: List[str] = []
    dir_lhover: List[str] = []

    prod_lx: List[Any] = []
    prod_ly: List[float] = []
    prod_ltxt: List[str] = []
    prod_lhover: List[str] = []

    # Pre-estimate day peak energy threshold so labels skip tiny morning/cloud blips
    prod_energies = [float(np.sum(p_prod[s:e]) * dt) for s, e in prod_runs] if prod_runs else [0.0]
    min_prod_label_kwh = max(1.0, 0.01 * max(prod_energies))

    rows: List[Dict[str, Any]] = []
    for phase_num, (s, e) in enumerate(prod_runs, start=1):
        start_ts = pd.Timestamp(ts[s])
        end_ts = pd.Timestamp(ts[e - 1]) + pd.Timedelta(minutes=15)
        dur_h = round((e - s) * dt, 2)
        span_str = _format_clock_span(start_ts, end_ts)

        prod_kwh = float(np.sum(p_prod[s:e]) * dt)
        pot_kwh = float(np.sum(p_pot[s:e]) * dt)
        clip_kwh = max(0.0, pot_kwh - prod_kwh)
        peak_prod_idx = s + int(np.argmax(p_prod[s:e]))
        peak_prod_kw = float(p_prod[peak_prod_idx])

        if standalone_mode:
            prod_suffix = f" | Day/Phase: <b>{prod_kwh:,.1f} kWh</b> ({dur_h:.2f} h, {span_str})"
            spec_y = (prod_kwh / float(installed_kwp)) if installed_kwp > 0.0 else 0.0
            rows.append(
                {
                    "Phase #": phase_num,
                    "Start": start_ts.strftime("%Y-%m-%d %H:%M"),
                    "End": end_ts.strftime("%Y-%m-%d %H:%M"),
                    "Daylight (h)": round(dur_h, 2),
                    "Solar Production AC (kWh)": round(prod_kwh, 1),
                    "Unclipped Potential (kWh)": round(pot_kwh, 1),
                    "Clipped (kWh)": round(clip_kwh, 1),
                    "Peak AC (kW)": round(peak_prod_kw, 1),
                    "Specific Yield (kWh/kWp)": round(spec_y, 2),
                }
            )
        else:
            dir_kwh = float(np.sum(p_dir[s:e]) * dt)
            bess_kwh = float(np.sum(p_bess[s:e]) * dt)
            exp_kwh = float(np.sum(p_exp[s:e]) * dt)
            split_str = _format_solar_allocation_split(prod_kwh, dir_kwh, bess_kwh, exp_kwh)
            prod_suffix = f" | Phase: <b>{prod_kwh:,.1f} kWh</b> ({dur_h:.2f} h, {split_str})"
            rows.append(
                {
                    "Phase #": phase_num,
                    "Start": start_ts.strftime("%Y-%m-%d %H:%M"),
                    "End": end_ts.strftime("%Y-%m-%d %H:%M"),
                    "Daylight (h)": round(dur_h, 2),
                    "Solar Production AC (kWh)": round(prod_kwh, 1),
                    "Solar Direct (kWh)": round(dir_kwh, 1),
                    "To Battery (kWh)": round(bess_kwh, 1),
                    "Grid Export (kWh)": round(exp_kwh, 1),
                    "Unclipped Potential (kWh)": round(pot_kwh, 1),
                    "Clipped (kWh)": round(clip_kwh, 1),
                    "Peak AC (kW)": round(peak_prod_kw, 1),
                    "Utilization / Split": split_str,
                }
            )

        pot_suffix = f" | Day/Phase: <b>{pot_kwh:,.1f} kWh</b>" + (
            f" (Clipped -{clip_kwh:,.1f} kWh)" if clip_kwh >= 0.1 else ""
        )
        for k in range(s, e):
            if p_prod[k] > threshold_kw:
                prod_hover_suffix[k] = prod_suffix
            if p_pot[k] > threshold_kw:
                pot_hover_suffix[k] = pot_suffix

        if prod_kwh >= min_prod_label_kwh and peak_prod_kw > threshold_kw:
            prod_lx.append(ts[peak_prod_idx])
            prod_ly.append(peak_prod_kw)
            prod_ltxt.append(_fmt_kwh_label(prod_kwh))
            prod_lhover.append(
                f"Solar Production Phase: <b>{prod_kwh:,.1f} kWh</b><br>"
                f"{start_ts.strftime('%Y-%m-%d %H:%M')} - {end_ts.strftime('%H:%M')} ({dur_h:.2f} h)<br>"
                f"Peak: {peak_prod_kw:,.1f} kW AC"
                + (f" | Clipped: {clip_kwh:,.1f} kWh" if clip_kwh >= 0.1 else "")
            )

    # Contiguous Solar Direct runs for coupled Power Flow hover & labels
    if not standalone_mode:
        dir_runs = _find_true_runs((p_dir > threshold_kw) & (~gap_b))
        dir_energies = [float(np.sum(p_dir[s:e]) * dt) for s, e in dir_runs] if dir_runs else [0.0]
        min_dir_label_kwh = max(1.0, 0.01 * max(dir_energies))
        for ds, de in dir_runs:
            d_start = pd.Timestamp(ts[ds])
            d_end = pd.Timestamp(ts[de - 1]) + pd.Timedelta(minutes=15)
            d_dur_h = round((de - ds) * dt, 2)
            d_kwh = float(np.sum(p_dir[ds:de]) * dt)
            d_peak_idx = ds + int(np.argmax(p_dir[ds:de]))
            d_peak_kw = float(p_dir[d_peak_idx])
            d_span = _format_clock_span(d_start, d_end)

            d_suffix = f" | Phase: <b>{d_kwh:,.1f} kWh</b> ({d_dur_h:.2f} h, {d_span})"
            for k in range(ds, de):
                if p_dir[k] > threshold_kw:
                    direct_hover_suffix[k] = d_suffix

            if d_kwh >= min_dir_label_kwh and d_peak_kw > threshold_kw:
                dir_lx.append(ts[d_peak_idx])
                dir_ly.append(d_peak_kw)
                dir_ltxt.append(_fmt_kwh_label(d_kwh))
                dir_lhover.append(
                    f"Solar Direct Phase: <b>{d_kwh:,.1f} kWh</b><br>"
                    f"{d_start.strftime('%Y-%m-%d %H:%M')} - {d_end.strftime('%H:%M')} ({d_dur_h:.2f} h)<br>"
                    f"Peak Direct: {d_peak_kw:,.1f} kW"
                )

    events_df = pd.DataFrame(rows, columns=cols) if rows else empty_df
    return SolarPhaseEventsResult(
        events_df=events_df,
        direct_hover_suffix=direct_hover_suffix,
        prod_hover_suffix=prod_hover_suffix,
        pot_hover_suffix=pot_hover_suffix,
        dir_label_x=dir_lx,
        dir_label_y=dir_ly,
        dir_label_text=dir_ltxt,
        dir_label_hover=dir_lhover,
        prod_label_x=prod_lx,
        prod_label_y=prod_ly,
        prod_label_text=prod_ltxt,
        prod_label_hover=prod_lhover,
    )


def extract_combined_solar_phase_events(
    sim_res: CombinedSimulationResult,
    threshold_kw: float = 0.1,
) -> SolarPhaseEventsResult:
    """Segments Solar Production and Solar Direct daylight phases from `CombinedSimulationResult`."""
    ts_raw = getattr(sim_res, "timestamps", None)
    n = len(ts_raw) if ts_raw is not None else 0
    cfg = getattr(sim_res, "system_config", None)
    if n == 0 or cfg is None or not getattr(cfg, "enable_solar", False):
        return SolarPhaseEventsResult(
            events_df=pd.DataFrame(columns=SOLAR_EVENT_LOG_COLUMNS),
            direct_hover_suffix=[""] * n,
            prod_hover_suffix=[""] * n,
            pot_hover_suffix=[""] * n,
        )

    raw_pot = getattr(sim_res, "solar_potential_kw", None)
    return _build_solar_phase_core(
        timestamps=ts_raw,
        solar_production_kw=sim_res.solar_gen_kw,
        solar_potential_kw=raw_pot if raw_pot is not None else sim_res.solar_gen_kw,
        solar_direct_kw=sim_res.solar_direct_kw,
        bess_charge_solar_kw=sim_res.bess_charge_solar_kw,
        solar_export_kw=sim_res.solar_export_kw,
        is_gap=getattr(sim_res, "is_gap", None),
        installed_kwp=float(getattr(getattr(sim_res, "solar_derivation", None), "installed_kwp", 0.0) or 0.0),
        standalone_mode=False,
        threshold_kw=threshold_kw,
    )


def extract_standalone_solar_phase_events(
    timestamps: Any,
    solar_production_kw: np.ndarray,
    solar_potential_kw: Optional[np.ndarray] = None,
    installed_kwp: float = 0.0,
    threshold_kw: float = 0.1,
) -> SolarPhaseEventsResult:
    """Consumption-independent Solar daylight segmentation for Sub-Tab 2 `Solar Production`."""
    return _build_solar_phase_core(
        timestamps=timestamps,
        solar_production_kw=solar_production_kw,
        solar_potential_kw=solar_potential_kw,
        installed_kwp=installed_kwp,
        standalone_mode=True,
        threshold_kw=threshold_kw,
    )


def summarize_solar_window_energy(
    timestamps: Any,
    start_ts: Any,
    end_ts: Any,
    solar_production_kw: np.ndarray,
    solar_potential_kw: Optional[np.ndarray] = None,
    solar_direct_kw: Optional[np.ndarray] = None,
    bess_charge_solar_kw: Optional[np.ndarray] = None,
    solar_export_kw: Optional[np.ndarray] = None,
    is_gap: Optional[np.ndarray] = None,
) -> Dict[str, float]:
    """Computes exact Solar Production, Direct Use, Battery Charge, Export, and Clipping over `[start_ts, end_ts]`."""
    empty = {
        "production_kwh": 0.0,
        "potential_kwh": 0.0,
        "clipped_kwh": 0.0,
        "direct_kwh": 0.0,
        "to_battery_kwh": 0.0,
        "export_kwh": 0.0,
        "peak_production_kw": 0.0,
        "peak_direct_kw": 0.0,
        "active_hours": 0.0,
    }
    if timestamps is None or len(timestamps) == 0:
        return empty

    ts = pd.DatetimeIndex(timestamps)
    n = len(ts)
    gap_b = (
        np.asarray(is_gap, dtype=bool)
        if is_gap is not None and len(is_gap) == n
        else np.zeros(n, dtype=bool)
    )
    win_mask = (ts >= pd.Timestamp(start_ts)) & (ts <= pd.Timestamp(end_ts)) & (~gap_b)
    if not np.any(win_mask):
        return empty

    dt = 0.25
    p_prod = np.maximum(0.0, np.asarray(solar_production_kw, dtype=float))[win_mask]
    p_pot_src = np.maximum(0.0, np.asarray(solar_potential_kw, dtype=float))[win_mask] if solar_potential_kw is not None else p_prod
    p_pot = np.maximum(p_prod, p_pot_src)

    prod_kwh = float(np.sum(p_prod) * dt)
    pot_kwh = float(np.sum(p_pot) * dt)
    dir_arr = np.maximum(0.0, np.asarray(solar_direct_kw, dtype=float))[win_mask] if solar_direct_kw is not None else np.zeros_like(p_prod)
    bess_arr = np.maximum(0.0, np.asarray(bess_charge_solar_kw, dtype=float))[win_mask] if bess_charge_solar_kw is not None else np.zeros_like(p_prod)
    exp_arr = np.maximum(0.0, np.asarray(solar_export_kw, dtype=float))[win_mask] if solar_export_kw is not None else np.zeros_like(p_prod)

    return {
        "production_kwh": prod_kwh,
        "potential_kwh": pot_kwh,
        "clipped_kwh": max(0.0, pot_kwh - prod_kwh),
        "direct_kwh": float(np.sum(dir_arr) * dt),
        "to_battery_kwh": float(np.sum(bess_arr) * dt),
        "export_kwh": float(np.sum(exp_arr) * dt),
        "peak_production_kw": float(np.max(p_prod)) if p_prod.size > 0 else 0.0,
        "peak_direct_kw": float(np.max(dir_arr)) if dir_arr.size > 0 else 0.0,
        "active_hours": float(np.sum(p_prod > 0.1) * dt),
    }
