"""
========================================================================================
Layer 2: Consumption Pipeline & Integrity Normalization (engine/consumption_pipeline.py)
Current Situation (Status Quo) Sandbox Engine
========================================================================================
Prepares, cleans, and standardizes 15-minute interval demand data for reference year 2025:
  - Guarantees exactly 35,040 steps (365 days x 96 steps @ 15 min, dt = 0.25 h).
  - Normalizes timezone-aware or naive timestamps to Europe/Amsterdam calendar grid.
  - Classifies each interval into month (1..12) and TOU window (Liander HT: Mo-Fr 07:00-23:00 vs NT).
  - Computes monthly energy sums (E_m, HT, NT) and monthly peak power (P_peak,m).
  - Supplies benchmark load generators for Profile A (360 MWh) and Profile B (1.2 GWh).
========================================================================================
"""

from typing import Tuple, List, Dict, Any, Optional
import numpy as np
import pandas as pd

try:
    from .config_and_models import LoadSeries2025, MonthlyConsumptionRecord
except (ImportError, ValueError):
    from config_and_models import LoadSeries2025, MonthlyConsumptionRecord

try:
    from current_model.core.load_processor import process_load_profile_data
    from current_model.core.csv_parser import parse_csv_content, detect_suggested_columns
except ImportError:
    pass


MONTH_DAYS_2025: Dict[int, int] = {
    1: 31, 2: 28, 3: 31, 4: 30, 5: 31, 6: 30,
    7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31
}

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
]


def create_reference_2025_timestamps() -> pd.DatetimeIndex:
    """Creates the canonical 35,040-step 15-minute DatetimeIndex for 2025."""
    return pd.date_range(
        start="2025-01-01 00:00:00",
        end="2025-12-31 23:45:00",
        freq="15min"
    )


def classify_liander_tou_window(timestamps: pd.DatetimeIndex) -> np.ndarray:
    """
    Classifies timestamps into Liander High-Tariff (HT / Peak) vs Low-Tariff (NT / Off-Peak):
      - HT (Peak): Monday to Friday between 07:00 and 23:00.
      - NT (Off-Peak): Monday to Friday 23:00 - 07:00, and all hours on Saturday and Sunday.
    """
    day_of_week = timestamps.dayofweek  # 0=Monday, 6=Sunday
    hour = timestamps.hour
    is_weekday = day_of_week < 5
    is_working_hours = (hour >= 7) & (hour < 23)
    return is_weekday & is_working_hours


def extract_monthly_consumption_records(load: LoadSeries2025) -> List[MonthlyConsumptionRecord]:
    """
    Aggregates a 35,040-interval LoadSeries into 12 MonthlyConsumptionRecord objects.
    """
    records: List[MonthlyConsumptionRecord] = []
    for m in range(1, 13):
        mask = (load.month_indices == m)
        m_energy = float(np.sum(load.energy_kwh[mask]))
        m_peak_power = float(np.max(load.power_kw[mask])) if np.any(mask) else 0.0

        mask_ht = mask & load.is_peak_tou
        mask_nt = mask & (~load.is_peak_tou)
        m_energy_ht = float(np.sum(load.energy_kwh[mask_ht]))
        m_energy_nt = float(np.sum(load.energy_kwh[mask_nt]))

        records.append(
            MonthlyConsumptionRecord(
                month_index=m,
                month_name=MONTH_NAMES[m - 1],
                days_count=MONTH_DAYS_2025[m],
                total_kwh=round(m_energy, 4),
                peak_tou_kwh=round(m_energy_ht, 4),
                offpeak_tou_kwh=round(m_energy_nt, 4),
                peak_demand_kw=round(m_peak_power, 4)
            )
        )
    return records


def normalize_load_profile_2025(
    raw_df: pd.DataFrame,
    power_col: str = "power_kw",
    time_col: Optional[str] = None
) -> Tuple[LoadSeries2025, Dict[str, Any]]:
    """
    Normalizes arbitrary meter CSV or DataFrame into strict 35,040-step LoadSeries2025.
    """
    canonical_ts = create_reference_2025_timestamps()
    total_steps = len(canonical_ts)

    if raw_df.empty or power_col not in raw_df.columns:
        raise ValueError(f"Required power column '{power_col}' not found in DataFrame.")

    df = raw_df.copy()
    if time_col and time_col in df.columns:
        df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
        df = df.dropna(subset=[time_col]).sort_values(by=time_col)
        df.set_index(time_col, inplace=True)
    elif not isinstance(df.index, pd.DatetimeIndex):
        for candidate in ["timestamp", "datetime", "date_time", "time", "Datum", "Tijd"]:
            if candidate in df.columns:
                df[candidate] = pd.to_datetime(df[candidate], errors="coerce")
                df = df.dropna(subset=[candidate]).sort_values(by=candidate)
                df.set_index(candidate, inplace=True)
                break

    if isinstance(df.index, pd.DatetimeIndex):
        ts_index = df.index
        if ts_index.tz is not None:
            ts_index = ts_index.tz_convert("Europe/Amsterdam").tz_localize(None)
        df.index = ts_index
        reindexed_power = df[power_col].reindex(canonical_ts, method="nearest").fillna(method="ffill").fillna(0.0)
        power_array = np.maximum(0.0, reindexed_power.to_numpy(dtype=float))
    else:
        raw_vals = pd.to_numeric(df[power_col], errors="coerce").fillna(0.0).to_numpy(dtype=float)
        if len(raw_vals) == total_steps:
            power_array = np.maximum(0.0, raw_vals)
        elif len(raw_vals) > total_steps:
            power_array = np.maximum(0.0, raw_vals[:total_steps])
        else:
            repeats = int(np.ceil(total_steps / len(raw_vals)))
            tiled = np.tile(raw_vals, repeats)[:total_steps]
            power_array = np.maximum(0.0, tiled)

    energy_array = power_array * 0.25
    month_indices = canonical_ts.month.to_numpy(dtype=int)
    is_peak_tou = classify_liander_tou_window(canonical_ts)

    series = LoadSeries2025(
        timestamps=canonical_ts,
        power_kw=power_array,
        energy_kwh=energy_array,
        month_indices=month_indices,
        is_peak_tou=is_peak_tou
    )

    diagnostics = {
        "status": "success",
        "total_kwh": series.total_energy_kwh,
        "peak_kw": series.peak_demand_kw,
        "steps_count": len(series.power_kw)
    }
    return series, diagnostics


def synthesize_benchmark_load_profile_2025(
    nominal_peak_kw: float = 250.0,
    annual_energy_kwh: Optional[float] = None
) -> LoadSeries2025:
    """
    Synthesizes a standardized commercial load profile with diurnal patterns.
    """
    canonical_ts = create_reference_2025_timestamps()
    total_steps = len(canonical_ts)
    hour = canonical_ts.hour.to_numpy(dtype=float) + canonical_ts.minute.to_numpy(dtype=float) / 60.0
    day_of_week = canonical_ts.dayofweek.to_numpy(dtype=int)
    is_weekday = (day_of_week < 5).astype(float)

    # Base profile: night base 0.25, day working peak up to 0.90
    day_profile = np.exp(-0.5 * ((hour - 14.0) / 4.0) ** 2)
    work_load = 0.25 + 0.65 * day_profile
    weekend_load = 0.20 + 0.15 * day_profile
    relative_power = is_weekday * work_load + (1.0 - is_weekday) * weekend_load

    # Peak hour spike once a month to establish exact nominal peak
    for m in range(1, 13):
        idx_month = np.where(canonical_ts.month == m)[0]
        if len(idx_month) > 100:
            relative_power[idx_month[50]] = 1.0

    power_array = relative_power * nominal_peak_kw
    if annual_energy_kwh is not None and annual_energy_kwh > 0.0:
        current_sum = float(np.sum(power_array * 0.25))
        if current_sum > 0:
            power_array = power_array * (annual_energy_kwh / current_sum)

    energy_array = power_array * 0.25
    month_indices = canonical_ts.month.to_numpy(dtype=int)
    is_peak_tou = classify_liander_tou_window(canonical_ts)

    return LoadSeries2025(
        timestamps=canonical_ts,
        power_kw=power_array,
        energy_kwh=energy_array,
        month_indices=month_indices,
        is_peak_tou=is_peak_tou
    )


def synthesize_profile_a_360mwh() -> LoadSeries2025:
    """
    Generates exact Benchmark Profile A (Low Voltage AC4b):
      - Annual Energy: exactly 360,000 kWh (30,000 kWh per month)
      - Monthly Peak: exactly 140.0 kW in each month
    """
    canonical_ts = create_reference_2025_timestamps()
    power_array = np.zeros(len(canonical_ts), dtype=float)
    month_indices = canonical_ts.month.to_numpy(dtype=int)

    for m in range(1, 13):
        mask = (month_indices == m)
        indices = np.where(mask)[0]
        n_steps = len(indices)
        # Target: 30,000 kWh in month m -> sum(energy) = 30000 -> sum(power) = 120,000 kW
        # Peak step: 140 kW
        # Remaining power to distribute: 120,000 - 140 = 119,860 kW across (n_steps - 1)
        base_power = (120000.0 - 140.0) / (n_steps - 1)
        power_array[indices] = base_power
        power_array[indices[200]] = 140.0  # Peak in working hours

    energy_array = power_array * 0.25
    is_peak_tou = classify_liander_tou_window(canonical_ts)

    return LoadSeries2025(
        timestamps=canonical_ts,
        power_kw=power_array,
        energy_kwh=energy_array,
        month_indices=month_indices,
        is_peak_tou=is_peak_tou
    )


def synthesize_profile_b_1200mwh() -> LoadSeries2025:
    """
    Generates exact Benchmark Profile B (Medium Voltage AC5a):
      - Annual Energy: exactly 1,200,000 kWh (100,000 kWh per month)
      - Monthly Peak: exactly 500.0 kW in each month
    """
    canonical_ts = create_reference_2025_timestamps()
    power_array = np.zeros(len(canonical_ts), dtype=float)
    month_indices = canonical_ts.month.to_numpy(dtype=int)

    for m in range(1, 13):
        mask = (month_indices == m)
        indices = np.where(mask)[0]
        n_steps = len(indices)
        # Target: 100,000 kWh in month m -> sum(energy) = 100,000 -> sum(power) = 400,000 kW
        # Peak step: 500 kW
        base_power = (400000.0 - 500.0) / (n_steps - 1)
        power_array[indices] = base_power
        power_array[indices[200]] = 500.0  # Peak in working hours

    energy_array = power_array * 0.25
    is_peak_tou = classify_liander_tou_window(canonical_ts)

    return LoadSeries2025(
        timestamps=canonical_ts,
        power_kw=power_array,
        energy_kwh=energy_array,
        month_indices=month_indices,
        is_peak_tou=is_peak_tou
    )


def evaluate_consumption_audit(
    load: LoadSeries2025,
    monthly_records: List[MonthlyConsumptionRecord]
) -> Dict[str, Any]:
    """
    Validates Audit Point 1 (Load profile step count and conservation).
    """
    c1_1_pass = (len(load.power_kw) == 35040)
    interval_sum_kwh = float(np.sum(load.energy_kwh))
    monthly_sum_kwh = float(sum(r.total_kwh for r in monthly_records))
    diff_kwh = abs(interval_sum_kwh - monthly_sum_kwh)
    c1_2_pass = (diff_kwh < 1e-3)

    c1_3_pass = (
        len(load.month_indices) == 35040 and
        np.all(load.month_indices >= 1) and
        np.all(load.month_indices <= 12) and
        len(load.is_peak_tou) == 35040
    )

    return {
        "audit_point": 1,
        "title": "Audit Point 1: Load Profile Integrity",
        "passed": (c1_1_pass and c1_2_pass and c1_3_pass),
        "criteria": {
            "1.1_step_count_35040": {"passed": c1_1_pass, "actual": len(load.power_kw)},
            "1.2_energy_conservation": {"passed": c1_2_pass, "interval_sum": interval_sum_kwh, "monthly_sum": monthly_sum_kwh},
            "1.3_time_classification": {"passed": c1_3_pass}
        }
    }
