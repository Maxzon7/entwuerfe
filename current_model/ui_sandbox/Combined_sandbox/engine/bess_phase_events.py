"""
Vectorized BESS Charge & Discharge Phase Segmentation (`engine/bess_phase_events.py`).

Extracts contiguous battery Discharge and Charge events from 15-minute `CombinedSimulationResult`
arrays (`dt = 0.25 h`) without modifying the core dispatch simulation kernel.
Provides:
  - Per-interval hover suffixes (`dis_hover_suffix`, `chg_hover_suffix`) for unified tooltips
  - Peak/valley label anchor coordinates (`dis_label_*`, `chg_label_*`) for chart overlays
  - Event summary DataFrame (`events_df`) and arbitrary time-window energy aggregation
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .models_and_presets import CombinedSimulationResult


EVENT_LOG_COLUMNS: List[str] = [
    "Phase #",
    "Type",
    "Start",
    "End",
    "Duration (h)",
    "Energy AC (kWh)",
    "Peak Power (kW)",
    "Avg Power (kW)",
    "Start SoC (%)",
    "End SoC (%)",
    "SoC Delta (%)",
    "Charge Source / Role",
]


@dataclass
class BessPhaseEventsResult:
    """Container for segmented BESS Charge/Discharge phases and Plotly overlay arrays."""

    events_df: pd.DataFrame
    dis_hover_suffix: List[str] = field(default_factory=list)
    chg_hover_suffix: List[str] = field(default_factory=list)
    dis_label_x: List[Any] = field(default_factory=list)
    dis_label_y: List[float] = field(default_factory=list)
    dis_label_text: List[str] = field(default_factory=list)
    dis_label_hover: List[str] = field(default_factory=list)
    chg_label_x: List[Any] = field(default_factory=list)
    chg_label_y: List[float] = field(default_factory=list)
    chg_label_text: List[str] = field(default_factory=list)
    chg_label_hover: List[str] = field(default_factory=list)


def _find_true_runs(mask: np.ndarray) -> List[Tuple[int, int]]:
    """Returns `(start_idx, end_idx)` half-open intervals for contiguous True segments."""
    if mask.size == 0 or not np.any(mask):
        return []
    padded = np.empty(mask.size + 2, dtype=np.int8)
    padded[0] = 0
    padded[1:-1] = mask.astype(np.int8)
    padded[-1] = 0
    diffs = np.diff(padded)
    starts = np.where(diffs == 1)[0]
    ends = np.where(diffs == -1)[0]
    return [(int(s), int(e)) for s, e in zip(starts, ends)]


def _bridge_short_idle_gaps(
    active_mask: np.ndarray,
    blocked_mask: np.ndarray,
    max_gap_steps: int,
) -> np.ndarray:
    """
    Merges adjacent active runs separated by at most `max_gap_steps` idle intervals,
    never bridging across data gaps (`is_gap`) or opposite-direction BESS activity.
    """
    if max_gap_steps <= 0 or active_mask.size == 0:
        return active_mask.copy()
    runs = _find_true_runs(active_mask)
    if len(runs) <= 1:
        return active_mask.copy()
    out = active_mask.copy()
    for idx in range(len(runs) - 1):
        prev_end = runs[idx][1]
        next_start = runs[idx + 1][0]
        gap_len = next_start - prev_end
        if 0 < gap_len <= max_gap_steps and not np.any(blocked_mask[prev_end:next_start]):
            out[prev_end:next_start] = True
    return out


def _format_clock_span(start_ts: pd.Timestamp, end_ts: pd.Timestamp) -> str:
    """Formats concise clock span (`HH:MM-HH:MM` or `Mon DD HH:MM-Mon DD HH:MM` across days)."""
    if start_ts.date() == end_ts.date():
        return f"{start_ts.strftime('%H:%M')}-{end_ts.strftime('%H:%M')}"
    return f"{start_ts.strftime('%b %d %H:%M')}-{end_ts.strftime('%b %d %H:%M')}"


def _format_charge_sources(
    sol_kwh: float,
    grd_kwh: float,
    gen_kwh: float,
) -> str:
    """Builds a readable percentage attribution string for a BESS Charge phase."""
    tot = sol_kwh + grd_kwh + gen_kwh
    if tot <= 1e-6:
        return "Idle"
    parts: List[str] = []
    for label, val in (("Solar", sol_kwh), ("Grid", grd_kwh), ("Gen", gen_kwh)):
        pct = (val / tot) * 100.0
        if pct >= 1.0:
            parts.append(f"{label} {pct:.0f}%")
    return " / ".join(parts) if parts else "Solar/Grid"


def extract_bess_phase_events(
    sim_res: CombinedSimulationResult,
    threshold_kw: float = 0.1,
    merge_gap_steps: int = 0,
) -> BessPhaseEventsResult:
    """
    Segments 15-minute BESS operation into discrete Charge and Discharge phases,
    computing delivered/absorbed AC energy (`kWh`), duration (`h`), SoC trajectory,
    hover suffixes, and peak label anchors.
    """
    ts_raw = getattr(sim_res, "timestamps", None)
    n = len(ts_raw) if ts_raw is not None else 0
    empty_df = pd.DataFrame(columns=EVENT_LOG_COLUMNS)
    cfg = getattr(sim_res, "system_config", None)
    if n == 0 or cfg is None or not getattr(cfg, "enable_battery", False):
        return BessPhaseEventsResult(
            events_df=empty_df,
            dis_hover_suffix=[""] * n,
            chg_hover_suffix=[""] * n,
        )

    ts = pd.DatetimeIndex(ts_raw)
    dt = 0.25

    p_dis = np.maximum(0.0, np.asarray(sim_res.bess_discharge_kw, dtype=float))
    p_chg_sol = np.maximum(0.0, np.asarray(sim_res.bess_charge_solar_kw, dtype=float))
    p_chg_grd = np.maximum(0.0, np.asarray(sim_res.bess_charge_grid_kw, dtype=float))
    p_chg_gen = np.maximum(0.0, np.asarray(sim_res.bess_charge_gen_kw, dtype=float))
    p_chg = p_chg_sol + p_chg_grd + p_chg_gen
    soc = np.asarray(sim_res.bess_soc_pct, dtype=float)

    is_gap = getattr(sim_res, "is_gap", None)
    gap_b = (
        np.asarray(is_gap, dtype=bool)
        if is_gap is not None and len(is_gap) == n
        else np.zeros(n, dtype=bool)
    )

    dis_raw = (p_dis > threshold_kw) & (~gap_b)
    chg_raw = (p_chg > threshold_kw) & (~gap_b)

    if merge_gap_steps > 0:
        dis_mask = _bridge_short_idle_gaps(dis_raw, gap_b | chg_raw, merge_gap_steps)
        chg_mask = _bridge_short_idle_gaps(chg_raw, gap_b | dis_mask, merge_gap_steps)
    else:
        dis_mask = dis_raw
        chg_mask = chg_raw

    usable_pct = max(0.05, (float(cfg.max_soc_pct) - float(cfg.min_soc_pct)) / 100.0)
    usable_kwh = max(1.0, float(cfg.battery_capacity_kwh) * usable_pct)
    min_label_kwh = max(1.0, 0.01 * usable_kwh)

    dis_hover_suffix = [""] * n
    chg_hover_suffix = [""] * n
    dis_lx: List[Any] = []
    dis_ly: List[float] = []
    dis_ltxt: List[str] = []
    dis_lhover: List[str] = []
    chg_lx: List[Any] = []
    chg_ly: List[float] = []
    chg_ltxt: List[str] = []
    chg_lhover: List[str] = []

    raw_records: List[Tuple[int, Dict[str, Any]]] = []

    phase_specs = (
        ("Discharge", dis_mask, p_dis, dis_hover_suffix, dis_lx, dis_ly, dis_ltxt, dis_lhover, 1.0),
        ("Charge", chg_mask, p_chg, chg_hover_suffix, chg_lx, chg_ly, chg_ltxt, chg_lhover, -1.0),
    )

    for p_type, mask, p_vec, hover_arr, lx, ly, ltxt, lhover, sign in phase_specs:
        for s, e in _find_true_runs(mask):
            start_ts = pd.Timestamp(ts[s])
            end_ts = pd.Timestamp(ts[e - 1]) + pd.Timedelta(minutes=15)
            dur_h = round((e - s) * dt, 2)
            energy_kwh = float(np.sum(p_vec[s:e]) * dt)
            peak_rel = int(np.argmax(p_vec[s:e]))
            peak_idx = s + peak_rel
            peak_kw = float(p_vec[peak_idx])
            avg_kw = energy_kwh / max(dur_h, dt)

            start_soc = float(soc[s - 1]) if (s > 0 and not gap_b[s - 1]) else float(soc[s])
            end_soc = float(soc[e - 1])
            soc_delta = end_soc - start_soc
            span_str = _format_clock_span(start_ts, end_ts)

            suffix = f" | Phase: <b>{energy_kwh:,.1f} kWh</b> ({dur_h:.2f} h, {span_str})"
            for k in range(s, e):
                if not gap_b[k]:
                    hover_arr[k] = suffix

            if p_type == "Charge":
                role_str = _format_charge_sources(
                    float(np.sum(p_chg_sol[s:e]) * dt),
                    float(np.sum(p_chg_grd[s:e]) * dt),
                    float(np.sum(p_chg_gen[s:e]) * dt),
                )
            else:
                role_str = "Load / Peak Shaving"

            if energy_kwh >= min_label_kwh:
                lbl_val = f"{energy_kwh:,.0f} kWh" if energy_kwh >= 10.0 else f"{energy_kwh:,.1f} kWh"
                lx.append(ts[peak_idx])
                ly.append(sign * peak_kw)
                ltxt.append(f"+{lbl_val}" if sign > 0 else f"-{lbl_val}")
                lhover.append(
                    f"{p_type} Phase: <b>{energy_kwh:,.1f} kWh</b><br>"
                    f"{start_ts.strftime('%Y-%m-%d %H:%M')} - {end_ts.strftime('%H:%M')} ({dur_h:.2f} h)<br>"
                    f"Peak: {peak_kw:,.1f} kW | SoC: {start_soc:.1f}% -> {end_soc:.1f}%"
                )

            raw_records.append(
                (
                    s,
                    {
                        "Type": p_type,
                        "Start": start_ts.strftime("%Y-%m-%d %H:%M"),
                        "End": end_ts.strftime("%Y-%m-%d %H:%M"),
                        "Duration (h)": round(dur_h, 2),
                        "Energy AC (kWh)": round(energy_kwh, 1),
                        "Peak Power (kW)": round(peak_kw, 1),
                        "Avg Power (kW)": round(avg_kw, 1),
                        "Start SoC (%)": round(start_soc, 1),
                        "End SoC (%)": round(end_soc, 1),
                        "SoC Delta (%)": round(soc_delta, 1),
                        "Charge Source / Role": role_str,
                    },
                )
            )

    raw_records.sort(key=lambda item: (item[0], 0 if item[1]["Type"] == "Discharge" else 1))
    ordered_rows: List[Dict[str, Any]] = []
    for phase_num, (_, rec) in enumerate(raw_records, start=1):
        ordered_rows.append({"Phase #": phase_num, **rec})

    events_df = pd.DataFrame(ordered_rows, columns=EVENT_LOG_COLUMNS) if ordered_rows else empty_df
    return BessPhaseEventsResult(
        events_df=events_df,
        dis_hover_suffix=dis_hover_suffix,
        chg_hover_suffix=chg_hover_suffix,
        dis_label_x=dis_lx,
        dis_label_y=dis_ly,
        dis_label_text=dis_ltxt,
        dis_label_hover=dis_lhover,
        chg_label_x=chg_lx,
        chg_label_y=chg_ly,
        chg_label_text=chg_ltxt,
        chg_label_hover=chg_lhover,
    )


def summarize_bess_window_energy(
    sim_res: CombinedSimulationResult,
    start_ts: Any,
    end_ts: Any,
) -> Dict[str, float]:
    """Computes exact Discharge/Charge AC energies and SoC boundaries across a chosen time window."""
    ts_raw = getattr(sim_res, "timestamps", None)
    empty_summary = {
        "discharge_kwh": 0.0,
        "charge_total_kwh": 0.0,
        "charge_solar_kwh": 0.0,
        "charge_grid_kwh": 0.0,
        "charge_gen_kwh": 0.0,
        "peak_discharge_kw": 0.0,
        "peak_charge_kw": 0.0,
        "start_soc_pct": 0.0,
        "end_soc_pct": 0.0,
        "soc_delta_pct": 0.0,
        "hours_covered": 0.0,
    }
    if ts_raw is None or len(ts_raw) == 0:
        return empty_summary

    ts = pd.DatetimeIndex(ts_raw)
    n = len(ts)
    is_gap = getattr(sim_res, "is_gap", None)
    gap_b = (
        np.asarray(is_gap, dtype=bool)
        if is_gap is not None and len(is_gap) == n
        else np.zeros(n, dtype=bool)
    )
    t0 = pd.Timestamp(start_ts)
    t1 = pd.Timestamp(end_ts)
    win_mask = (ts >= t0) & (ts <= t1) & (~gap_b)
    if not np.any(win_mask):
        return empty_summary

    dt = 0.25
    p_dis = np.maximum(0.0, np.asarray(sim_res.bess_discharge_kw, dtype=float))[win_mask]
    p_sol = np.maximum(0.0, np.asarray(sim_res.bess_charge_solar_kw, dtype=float))[win_mask]
    p_grd = np.maximum(0.0, np.asarray(sim_res.bess_charge_grid_kw, dtype=float))[win_mask]
    p_gen = np.maximum(0.0, np.asarray(sim_res.bess_charge_gen_kw, dtype=float))[win_mask]
    p_chg = p_sol + p_grd + p_gen
    soc_w = np.asarray(sim_res.bess_soc_pct, dtype=float)[win_mask]

    start_soc = float(soc_w[0]) if soc_w.size > 0 else 0.0
    end_soc = float(soc_w[-1]) if soc_w.size > 0 else 0.0
    return {
        "discharge_kwh": float(np.sum(p_dis) * dt),
        "charge_total_kwh": float(np.sum(p_chg) * dt),
        "charge_solar_kwh": float(np.sum(p_sol) * dt),
        "charge_grid_kwh": float(np.sum(p_grd) * dt),
        "charge_gen_kwh": float(np.sum(p_gen) * dt),
        "peak_discharge_kw": float(np.max(p_dis)) if p_dis.size > 0 else 0.0,
        "peak_charge_kw": float(np.max(p_chg)) if p_chg.size > 0 else 0.0,
        "start_soc_pct": start_soc,
        "end_soc_pct": end_soc,
        "soc_delta_pct": end_soc - start_soc,
        "hours_covered": float(np.sum(win_mask) * dt),
    }
