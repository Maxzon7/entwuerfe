"""
========================================================================================
Synthetic Load Aggregation Engine (current_model/core/synthetic_engine.py)
========================================================================================

Description:
------------
Aggregates bottom-up electrical consumer loads into 24-hour / 96-interval dataframes,
computes total power demand curves, and calculates daily operational energy consumption.
"""

from typing import List, Tuple, Dict, Any
import numpy as np
import pandas as pd
from current_model.models.load_component import SimpleConsumer


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
        c_curve = c.get_24h_array()
        df_day[c.name] = c_curve
        total_curve += c_curve

    df_day["Total_kW"] = total_curve

    peak_kw = float(total_curve.max()) if len(total_curve) > 0 else 0.0
    daily_energy_kwh = float(total_curve.sum() * 0.25)
    avg_power_kw = daily_energy_kwh / 24.0

    metrics = {
        "peak_demand_kw": peak_kw,
        "daily_energy_kwh": daily_energy_kwh,
        "avg_power_kw": avg_power_kw,
        "consumer_count": len(consumers)
    }

    return df_day, total_curve, metrics
