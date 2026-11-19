"""
========================================================================================
Synthetic Load Aggregation Engine (current_model/core/synthetic_engine.py)
========================================================================================

Description:
------------
Aggregates bottom-up electrical consumer loads into:
  1. 24-hour / 96-interval dataframes and daily operational summaries.
  2. Full-year / 35,040-interval timeseries (365 days) accounting for individual weekday schedules
     (Mon-Fri vs. Weekend), seasonal patterns, and system-wide public holidays (treated as Sundays).
"""

from typing import List, Tuple, Dict, Any, Optional, Set
import datetime
import numpy as np
import pandas as pd
from current_model.models.load_component import SimpleConsumer
from current_model.models.calendar_config import CalendarConfig


def generate_time_labels_24h() -> List[str]:
    """Generates 96 quarter-hour string labels formatted as 'HH:MM' (00:00 to 23:45)."""
    return [f"{h:02d}:{m:02d}" for h in range(24) for m in (0, 15, 30, 45)]


def aggregate_synthetic_24h(consumers: List[SimpleConsumer]) -> Tuple[pd.DataFrame, np.ndarray, Dict[str, float]]:
    """
    Computes a 24-hour DataFrame (96 quarter-hour intervals) aggregating all active consumers.

    Returns:
        Tuple containing:
          - df_day (pd.DataFrame): DataFrame with 'time', individual consumer columns, and 'Total_kW'.
          - total_curve (np.ndarray): 96-element array of total active power demand in kW.
          - metrics (Dict[str, float]): Dictionary with peak_kw, daily_energy_kwh, avg_power_kw, consumer_count.
    """
    time_labels = generate_time_labels_24h()
    df_day = pd.DataFrame({"time": time_labels})
    total_curve = np.zeros(96, dtype=float)

    for c in consumers:
        if not c.is_active:
            continue
        c_curve = c.get_24h_array()
        df_day[c.name] = c_curve
        total_curve += c_curve

    df_day["Total_kW"] = total_curve
    df_day["Total_Demand_kW"] = total_curve  # For universal compatibility

    peak_kw = float(total_curve.max()) if len(total_curve) > 0 else 0.0
    daily_energy_kwh = float(total_curve.sum() * 0.25)
    avg_power_kw = daily_energy_kwh / 24.0 if daily_energy_kwh > 0 else 0.0

    metrics = {
        "peak_demand_kw": peak_kw,
        "daily_energy_kwh": daily_energy_kwh,
        "avg_power_kw": avg_power_kw,
        "consumer_count": len([c for c in consumers if c.is_active])
    }

    return df_day, total_curve, metrics


def aggregate_synthetic_year(
    consumers: List[SimpleConsumer],
    year: int = 2025,
    holidays: Optional[List[str]] = None
) -> Tuple[pd.DataFrame, np.ndarray, Dict[str, Any]]:
    """
    Simulates a complete 365-day (or 366-day leap year) annual load profile with 15-minute resolution (35,040 steps).

    Accounts for:
      - Individual consumer weekday availability (Monday..Sunday)
      - Seasonal variations (Flat, Winter-heavy, Summer-heavy, Custom monthly factors)
      - System-wide custom public holidays (treated as Sunday schedule)

    Returns:
        Tuple containing:
          - df_year (pd.DataFrame): 35,040-row DataFrame with 'timestamp', consumer columns, and 'Total_Demand_kW'.
          - total_curve (np.ndarray): 35,040-element array of active power demand in kW.
          - metrics (Dict[str, Any]): Annual KPIs (MWh, Peak kW, Full load hours, Load factor).
    """
    # 1. Generate full 15-minute timestamp index
    start_ts = pd.Timestamp(f"{year}-01-01 00:00:00")
    end_ts = pd.Timestamp(f"{year}-12-31 23:45:00")
    timestamps = pd.date_range(start=start_ts, end=end_ts, freq="15min")
    total_steps = len(timestamps)
    days_count = total_steps // 96

    # 2. Build holiday lookup set
    cal = CalendarConfig(year=year, holidays=holidays if holidays is not None else [])
    holiday_dates = cal.get_holiday_dates()

    df_year = pd.DataFrame({"timestamp": timestamps})
    total_annual_curve = np.zeros(total_steps, dtype=float)

    # Unique calendar days array
    day_starts = timestamps[::96]

    # 3. Vectorized simulation per consumer
    for c in consumers:
        if not c.is_active:
            continue

        c_annual_curve = np.zeros(total_steps, dtype=float)

        for day_idx in range(days_count):
            day_dt = day_starts[day_idx]
            d_date = day_dt.date()
            month = day_dt.month

            # Check if this day is configured as a system holiday (treat as Sunday = 6)
            if d_date in holiday_dates:
                effective_weekday = 6
            else:
                effective_weekday = day_dt.weekday()  # 0=Monday .. 6=Sunday

            day_curve = c.get_daily_array_for_weekday(day_of_week=effective_weekday, month=month)
            start_pos = day_idx * 96
            end_pos = start_pos + 96
            c_annual_curve[start_pos:end_pos] = day_curve

        df_year[c.name] = c_annual_curve
        total_annual_curve += c_annual_curve

    df_year["Total_Demand_kW"] = total_annual_curve
    df_year["Total_kW"] = total_annual_curve

    # 4. Calculate Annual KPIs
    annual_kwh = float(total_annual_curve.sum() * 0.25)
    annual_mwh = annual_kwh / 1000.0
    peak_kw = float(total_annual_curve.max()) if total_steps > 0 else 0.0
    min_kw = float(total_annual_curve.min()) if total_steps > 0 else 0.0
    avg_kw = float(total_annual_curve.mean()) if total_steps > 0 else 0.0
    full_load_hours = (annual_kwh / peak_kw) if peak_kw > 0 else 0.0
    load_factor_pct = (avg_kw / peak_kw * 100.0) if peak_kw > 0 else 0.0

    metrics: Dict[str, Any] = {
        "year": year,
        "days_count": days_count,
        "steps_count": total_steps,
        "annual_energy_mwh": annual_mwh,
        "annual_energy_kwh": annual_kwh,
        "peak_demand_kw": peak_kw,
        "min_demand_kw": min_kw,
        "avg_demand_kw": avg_kw,
        "full_load_hours": full_load_hours,
        "load_factor_pct": load_factor_pct,
        "holidays_applied_count": len([d for d in holiday_dates if d.year == year])
    }

    return df_year, total_annual_curve, metrics
