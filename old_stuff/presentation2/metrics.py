"""
Key Performance Indicators (KPIs) Calculation Module
====================================================
Computes peak demand, continuous baseload, average power, and integrated energy consumption.
"""

from dataclasses import dataclass
from typing import Optional
import pandas as pd
import numpy as np


@dataclass
class LoadProfileKPIs:
    """Dataclass holding all core energy metrics."""
    peak_kw: float
    peak_timestamp: Optional[pd.Timestamp]
    min_kw: float
    avg_kw: float
    total_kwh: float
    total_mwh: float
    data_points_count: int
    duration_days: float
    start_date: Optional[pd.Timestamp]
    end_date: Optional[pd.Timestamp]
    hours_per_step: float


def compute_load_profile_kpis(
    df_clean: pd.DataFrame,
    power_col: str = "Total_Demand_kW"
) -> LoadProfileKPIs:
    """
    Calculates key performance indicators from a processed load profile DataFrame.
    """
    if df_clean.empty or power_col not in df_clean.columns:
        return LoadProfileKPIs(
            peak_kw=0.0,
            peak_timestamp=None,
            min_kw=0.0,
            avg_kw=0.0,
            total_kwh=0.0,
            total_mwh=0.0,
            data_points_count=0,
            duration_days=0.0,
            start_date=None,
            end_date=None,
            hours_per_step=0.25
        )

    power_series = df_clean[power_col]
    count = len(df_clean)

    peak_val = float(power_series.max())
    min_val = float(power_series.min())
    avg_val = float(power_series.mean())

    peak_idx = power_series.idxmax()
    peak_time = df_clean.loc[peak_idx, "timestamp"] if "timestamp" in df_clean.columns else None

    start_date = df_clean["timestamp"].min() if "timestamp" in df_clean.columns else None
    end_date = df_clean["timestamp"].max() if "timestamp" in df_clean.columns else None

    if start_date and end_date:
        duration_seconds = (end_date - start_date).total_seconds()
        duration_days = max(1.0, duration_seconds / 86400.0)
    else:
        duration_days = max(1.0, (count * 15.0) / 1440.0)

    # Estimate sampling interval in hours
    if count > 1:
        dt_sec = (df_clean["timestamp"].iloc[1] - df_clean["timestamp"].iloc[0]).total_seconds()
        hours_per_step = (dt_sec / 3600.0) if dt_sec > 0 else 0.25
    else:
        hours_per_step = 0.25

    total_kwh = float(power_series.sum() * hours_per_step)
    total_mwh = total_kwh / 1000.0

    return LoadProfileKPIs(
        peak_kw=round(peak_val, 2),
        peak_timestamp=peak_time,
        min_kw=round(min_val, 2),
        avg_kw=round(avg_val, 2),
        total_kwh=round(total_kwh, 2),
        total_mwh=round(total_mwh, 2),
        data_points_count=count,
        duration_days=round(duration_days, 1),
        start_date=start_date,
        end_date=end_date,
        hours_per_step=hours_per_step
    )
