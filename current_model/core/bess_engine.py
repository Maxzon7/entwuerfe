"""
========================================================================================
Battery Energy Storage System (BESS) Dispatch Engine (current_model/core/bess_engine.py)
========================================================================================

Description:
------------
Physical 15-minute resolution dispatch, peak shaving, and grid overload simulation engine:
  - Grid constraint & overload diagnostic analyzer (peak exceedance, longest run, exceedance energy).
  - 15-minute interval-by-interval battery charge/discharge dispatch with strict energy conservation.
  - Safe SoC envelope enforcement (SoC_min, SoC_max, C-rates, round-trip efficiency).
  - Peak demand shaving and grid violation elimination assessment.
  - Monthly cycling, throughput, and round-trip degradation tracking.
"""

from typing import Dict, Any, List, Optional, Tuple, Union
from dataclasses import dataclass, field
import numpy as np
import pandas as pd

from current_model.models.bess import BESSConfig, BESSKPIs


@dataclass
class BESSSimulationResult:
    """Complete results from a 15-minute BESS simulation."""
    config: BESSConfig
    grid_limit_kw: float
    target_shaving_cap_kw: float
    kpis: BESSKPIs
    df_timeseries: pd.DataFrame
    monthly_metrics: List[Dict[str, Any]]
    diagnostics_before: Dict[str, Any]
    diagnostics_after: Dict[str, Any]


def analyze_grid_violations(
    load_series_kw: Union[pd.Series, np.ndarray, List[float]],
    grid_limit_kw: float,
    step_hours: float = 0.25
) -> Dict[str, Any]:
    """
    Analyzes electrical load data against a contracted grid connection limit.
    Computes peak exceedance, violation counts, longest consecutive run, and total exceedance energy.
    """
    arr = np.asarray(load_series_kw, dtype=float)
    arr = np.nan_to_num(arr, nan=0.0)

    if len(arr) == 0 or grid_limit_kw <= 0:
        return {
            "grid_limit_kw": float(grid_limit_kw),
            "peak_load_kw": 0.0,
            "overload_peak_kw": 0.0,
            "total_violation_intervals": 0,
            "total_violation_hours": 0.0,
            "violation_share_pct": 0.0,
            "longest_violation_run_intervals": 0,
            "longest_violation_run_hours": 0.0,
            "worst_event_energy_kwh": 0.0,
            "worst_event_duration_hours": 0.0,
            "min_bess_capacity_kwh": 0.0,
            "total_exceedance_energy_kwh": 0.0,
            "total_exceedance_energy_mwh": 0.0,
            "avg_overload_power_kw": 0.0,
            "has_violations": False
        }

    peak_load = float(np.max(arr))
    diff = np.maximum(0.0, arr - grid_limit_kw)
    overload_peak = float(np.max(diff))
    violation_mask = (arr > grid_limit_kw)
    total_violation_intervals = int(np.sum(violation_mask))
    total_violation_hours = float(total_violation_intervals * step_hours)
    violation_share_pct = float(total_violation_intervals / len(arr) * 100.0) if len(arr) > 0 else 0.0
    total_exceedance_kwh = float(np.sum(diff) * step_hours)

    # Longest consecutive violation run & worst-case event energy integration
    longest_run = 0
    current_run = 0
    current_run_energy = 0.0
    worst_event_energy_kwh = 0.0
    worst_event_run_intervals = 0

    for val, is_over in zip(diff, violation_mask):
        if is_over:
            current_run += 1
            current_run_energy += float(val * step_hours)
            if current_run > longest_run:
                longest_run = current_run
            if current_run_energy > worst_event_energy_kwh:
                worst_event_energy_kwh = current_run_energy
                worst_event_run_intervals = current_run
        else:
            current_run = 0
            current_run_energy = 0.0

    longest_run_hours = float(longest_run * step_hours)
    worst_event_duration_hours = float(worst_event_run_intervals * step_hours)
    avg_overload = float(np.mean(diff[violation_mask])) if total_violation_intervals > 0 else 0.0

    return {
        "grid_limit_kw": float(grid_limit_kw),
        "peak_load_kw": round(peak_load, 1),
        "overload_peak_kw": round(overload_peak, 1),
        "total_violation_intervals": total_violation_intervals,
        "total_violation_hours": round(total_violation_hours, 1),
        "violation_share_pct": round(violation_share_pct, 2),
        "longest_violation_run_intervals": longest_run,
        "longest_violation_run_hours": round(longest_run_hours, 2),
        "worst_event_energy_kwh": round(worst_event_energy_kwh, 1),
        "worst_event_duration_hours": round(worst_event_duration_hours, 2),
        "min_bess_capacity_kwh": round(worst_event_energy_kwh, 1),
        "total_exceedance_energy_kwh": round(total_exceedance_kwh, 1),
        "total_exceedance_energy_mwh": round(total_exceedance_kwh / 1000.0, 2),
        "avg_overload_power_kw": round(avg_overload, 1),
        "has_violations": bool(overload_peak > 0.01)
    }


def simulate_bess_dispatch(
    bess_config: BESSConfig,
    load_df: pd.DataFrame,
    grid_limit_kw: float,
    step_hours: float = 0.25,
    power_col: Optional[str] = None
) -> BESSSimulationResult:
    """
    Executes a high-precision 15-minute BESS peak shaving simulation against a facility load curve.

    Algorithm:
      - When P_Load(t) > target_cap: Battery discharges to shave the peak down to target_cap.
      - When P_Load(t) < target_cap: Battery recharges from available grid headroom up to target_cap.
      - Strictly respects SoC_min, SoC_max, max charge/discharge kW ratings, and round-trip efficiency.
    """
    # 1. Extract power series
    if power_col and power_col in load_df.columns:
        p_load = load_df[power_col].to_numpy(dtype=float)
    elif "Total_Demand_kW" in load_df.columns:
        p_load = load_df["Total_Demand_kW"].to_numpy(dtype=float)
    elif "P_Load_kW" in load_df.columns:
        p_load = load_df["P_Load_kW"].to_numpy(dtype=float)
    else:
        num_cols = load_df.select_dtypes(include=[np.number]).columns
        p_load = load_df[num_cols[-1]].to_numpy(dtype=float) if len(num_cols) > 0 else np.zeros(len(load_df))

    p_load = np.nan_to_num(p_load, nan=0.0)
    n_steps = len(p_load)

    # 2. Extract timestamps if available
    if "timestamp" in load_df.columns:
        ts_series = pd.to_datetime(load_df["timestamp"])
    else:
        start_dt = pd.Timestamp("2026-01-01 00:00:00")
        ts_series = pd.date_range(start=start_dt, periods=n_steps, freq=f"{int(step_hours * 60)}min")

    # 3. Battery Technical Parameters
    cap_kwh = max(1.0, float(bess_config.capacity_kwh))
    p_chg_max = max(0.1, float(bess_config.max_charge_power_kw))
    p_dis_max = max(0.1, float(bess_config.max_discharge_power_kw))
    soc_min_kwh = cap_kwh * (max(0.0, min(100.0, float(bess_config.soc_min_pct))) / 100.0)
    soc_max_kwh = cap_kwh * (max(0.0, min(100.0, float(bess_config.soc_max_pct))) / 100.0)
    init_soc_kwh = cap_kwh * (max(0.0, min(100.0, float(bess_config.initial_soc_pct))) / 100.0)
    init_soc_kwh = max(soc_min_kwh, min(soc_max_kwh, init_soc_kwh))

    rte = max(0.50, min(1.0, float(bess_config.round_trip_efficiency_pct) / 100.0))
    eta_chg = np.sqrt(rte)
    eta_dis = np.sqrt(rte)

    target_cap_kw = float(bess_config.peak_shaving_threshold_kw)
    if target_cap_kw <= 0:
        target_cap_kw = float(grid_limit_kw)

    # 4. Simulation Arrays
    p_grid = np.zeros(n_steps, dtype=float)
    p_dis = np.zeros(n_steps, dtype=float)
    p_chg = np.zeros(n_steps, dtype=float)
    soc_kwh = np.zeros(n_steps, dtype=float)
    soc_pct = np.zeros(n_steps, dtype=float)
    p_unmet = np.zeros(n_steps, dtype=float)

    curr_soc = init_soc_kwh

    # Parse scheduled arbitrage charging window if enabled
    is_scheduled_charge = (bess_config.dispatch_strategy == "tariff_arbitrage")
    chg_start_h = 0
    chg_end_h = 6
    if is_scheduled_charge:
        try:
            chg_start_h = int(bess_config.arbitrage_charge_start.split(":")[0])
            chg_end_h = int(bess_config.arbitrage_charge_end.split(":")[0])
        except Exception:
            chg_start_h, chg_end_h = 0, 6

    # 5. Core 15-Minute Interval Simulation Loop
    for i in range(n_steps):
        load_kw = p_load[i]
        hour = ts_series[i].hour if hasattr(ts_series[i], "hour") else (int(i * step_hours) % 24)

        if load_kw > target_cap_kw:
            # --- DISCHARGE (Peak Shaving) ---
            req_shave_kw = load_kw - target_cap_kw
            power_limit_kw = min(req_shave_kw, p_dis_max)
            energy_avail_kw = max(0.0, (curr_soc - soc_min_kwh) * eta_dis / step_hours)

            actual_dis_kw = min(power_limit_kw, energy_avail_kw)
            p_dis[i] = actual_dis_kw
            p_chg[i] = 0.0

            # Internal chemical energy discharged
            energy_drawn_kwh = (actual_dis_kw / eta_dis) * step_hours
            curr_soc = max(soc_min_kwh, curr_soc - energy_drawn_kwh)

            grid_import_kw = load_kw - actual_dis_kw
            p_grid[i] = grid_import_kw
            p_unmet[i] = max(0.0, grid_import_kw - target_cap_kw)

        elif load_kw < target_cap_kw:
            # --- RECHARGE (Opportunistic or Scheduled Off-Peak) ---
            allow_charge = True
            if is_scheduled_charge:
                allow_charge = (chg_start_h <= hour < chg_end_h) if chg_start_h < chg_end_h else (hour >= chg_start_h or hour < chg_end_h)

            if allow_charge and curr_soc < soc_max_kwh:
                grid_headroom_kw = target_cap_kw - load_kw
                power_limit_kw = min(grid_headroom_kw, p_chg_max)
                energy_room_kw = max(0.0, (soc_max_kwh - curr_soc) / (eta_chg * step_hours))

                actual_chg_kw = min(power_limit_kw, energy_room_kw)
                p_chg[i] = actual_chg_kw
                p_dis[i] = 0.0

                energy_added_kwh = (actual_chg_kw * eta_chg) * step_hours
                curr_soc = min(soc_max_kwh, curr_soc + energy_added_kwh)

                p_grid[i] = load_kw + actual_chg_kw
                p_unmet[i] = 0.0
            else:
                p_grid[i] = load_kw
                p_chg[i] = 0.0
                p_dis[i] = 0.0
                p_unmet[i] = 0.0
        else:
            p_grid[i] = load_kw
            p_chg[i] = 0.0
            p_dis[i] = 0.0
            p_unmet[i] = 0.0

        soc_kwh[i] = curr_soc
        soc_pct[i] = (curr_soc / cap_kwh) * 100.0

    # 6. Assemble DataFrame
    df_result = pd.DataFrame({
        "timestamp": ts_series,
        "P_Load_kW": np.round(p_load, 2),
        "P_Grid_kW": np.round(p_grid, 2),
        "P_BESS_Discharge_kW": np.round(p_dis, 2),
        "P_BESS_Charge_kW": np.round(p_chg, 2),
        "P_BESS_Net_kW": np.round(p_dis - p_chg, 2),
        "SoC_kWh": np.round(soc_kwh, 2),
        "SoC_pct": np.round(soc_pct, 1),
        "P_Overload_Unmet_kW": np.round(p_unmet, 2)
    })

    # 7. Pre- and Post-Diagnostics
    diag_before = analyze_grid_violations(p_load, grid_limit_kw, step_hours=step_hours)
    diag_after = analyze_grid_violations(p_grid, grid_limit_kw, step_hours=step_hours)

    total_dis_kwh = float(np.sum(p_dis) * step_hours)
    total_chg_kwh = float(np.sum(p_chg) * step_hours)
    losses_kwh = max(0.0, total_chg_kwh - total_dis_kwh)
    usable_kwh = bess_config.effective_usable_kwh
    efc = (total_dis_kwh / max(1.0, usable_kwh)) if usable_kwh > 0 else 0.0

    orig_peak = float(np.max(p_load)) if len(p_load) > 0 else 0.0
    res_peak = float(np.max(p_grid)) if len(p_grid) > 0 else 0.0
    peak_shaved_kw = max(0.0, orig_peak - res_peak)

    kpis = BESSKPIs(
        total_charged_kwh=round(total_chg_kwh, 1),
        total_discharged_kwh=round(total_dis_kwh, 1),
        round_trip_loss_kwh=round(losses_kwh, 1),
        equivalent_full_cycles=round(efc, 1),
        peak_shaved_kw=round(peak_shaved_kw, 1),
        avg_daily_throughput_kwh=round(total_dis_kwh / max(1.0, (n_steps * step_hours / 24.0)), 1),
        annual_degradation_pct=2.0
    )

    # 8. Monthly Aggregation
    df_calc = df_result.copy()
    df_calc["month"] = df_calc["timestamp"].dt.month
    monthly_rows = []
    for m in range(1, 13):
        m_df = df_calc[df_calc["month"] == m]
        if not m_df.empty:
            m_dis = float(m_df["P_BESS_Discharge_kW"].sum() * step_hours)
            m_chg = float(m_df["P_BESS_Charge_kW"].sum() * step_hours)
            m_orig_pk = float(m_df["P_Load_kW"].max())
            m_res_pk = float(m_df["P_Grid_kW"].max())
            m_cycles = m_dis / max(1.0, usable_kwh)
        else:
            m_dis, m_chg, m_orig_pk, m_res_pk, m_cycles = 0.0, 0.0, 0.0, 0.0, 0.0

        monthly_rows.append({
            "month": m,
            "discharged_mwh": round(m_dis / 1000.0, 2),
            "charged_mwh": round(m_chg / 1000.0, 2),
            "orig_peak_kw": round(m_orig_pk, 1),
            "residual_peak_kw": round(m_res_pk, 1),
            "peak_shaved_kw": round(max(0.0, m_orig_pk - m_res_pk), 1),
            "cycles": round(m_cycles, 1)
        })

    return BESSSimulationResult(
        config=bess_config,
        grid_limit_kw=grid_limit_kw,
        target_shaving_cap_kw=target_cap_kw,
        kpis=kpis,
        df_timeseries=df_result,
        monthly_metrics=monthly_rows,
        diagnostics_before=diag_before,
        diagnostics_after=diag_after
    )


def compute_average_week_dispatch(
    df_timeseries: pd.DataFrame,
    step_hours: float = 0.25
) -> pd.DataFrame:
    """
    Computes a representative 7-day (Monday to Sunday, 168 hours = 672 intervals)
    average dispatch and battery state-of-charge profile across the entire simulation dataset.

    Returns:
        pd.DataFrame containing 672 intervals of averaged load, residual grid, BESS charge/discharge,
        SoC %, stored kWh, week hour, day name, and time label.
    """
    df_calc = df_timeseries.copy()
    if "timestamp" in df_calc.columns:
        ts = pd.to_datetime(df_calc["timestamp"])
        df_calc["day_of_week"] = ts.dt.dayofweek  # 0=Monday, 6=Sunday
        df_calc["hour"] = ts.dt.hour
        df_calc["minute"] = ts.dt.minute
    else:
        n_steps = len(df_calc)
        ts = pd.date_range("2026-01-05 00:00:00", periods=n_steps, freq=f"{int(step_hours * 60)}min")
        df_calc["day_of_week"] = ts.dt.dayofweek
        df_calc["hour"] = ts.dt.hour
        df_calc["minute"] = ts.dt.minute

    cols_to_avg = [
        col for col in [
            "P_Load_kW", "P_Grid_kW", "P_BESS_Discharge_kW",
            "P_BESS_Charge_kW", "P_BESS_Net_kW", "SoC_kWh",
            "SoC_pct", "P_Overload_Unmet_kW"
        ] if col in df_calc.columns
    ]

    grouped = df_calc.groupby(["day_of_week", "hour", "minute"])[cols_to_avg].mean().reset_index()
    grouped = grouped.sort_values(by=["day_of_week", "hour", "minute"]).reset_index(drop=True)

    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    grouped["day_name"] = grouped["day_of_week"].apply(lambda d: day_names[int(d)] if int(d) < 7 else "Day")
    grouped["time_label"] = grouped.apply(
        lambda r: f"{r['day_name']} {int(r['hour']):02d}:{int(r['minute']):02d}", axis=1
    )
    grouped["week_hour"] = grouped["day_of_week"] * 24.0 + grouped["hour"] + grouped["minute"] / 60.0

    return grouped
