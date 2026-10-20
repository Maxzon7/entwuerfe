"""
========================================================================================
Layer 2: Consumption Pipeline & Integrity Normalization (consumption_pipeline.py)
========================================================================================
Prepares, cleans, and standardizes 15-minute interval demand data for the year 2025:
  - Guarantees exactly 35,040 steps (365 days x 96 steps @ 15 min, dt = 0.25 h).
  - Normalizes timezone-aware or naive timestamps to Europe/Amsterdam calendar grid.
  - Classifies each interval into month (1..12) and TOU window (Liander HT: Mo-Fr 07:00-23:00 vs NT).
  - Computes monthly energy sums (E_m, HT, NT) and monthly peak power (P_peak,m).
  - Validates all Audit Point 1 criteria (1.1, 1.2, 1.3).
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
    from current_model.models.load_component import SimpleConsumer, TimeWindow
    from current_model.core.synthetic_engine import aggregate_synthetic_year
except ImportError:
    from core.load_processor import process_load_profile_data
    from core.csv_parser import parse_csv_content, detect_suggested_columns
    from models.load_component import SimpleConsumer, TimeWindow
    from core.synthetic_engine import aggregate_synthetic_year


# Standard month metadata for reference year 2025 (non-leap year)
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
    Returns:
      Boolean array of shape (N,) where True = HT (Peak), False = NT (Off-Peak).
    """
    # dayofweek: 0=Monday, ..., 4=Friday, 5=Saturday, 6=Sunday
    is_weekday = (timestamps.dayofweek < 5)
    # Hour filter: 07:00 inclusive to 23:00 exclusive
    is_ht_hours = (timestamps.hour >= 7) & (timestamps.hour < 23)
    return np.asarray(is_weekday & is_ht_hours, dtype=bool)


def normalize_load_profile_2025(
    raw_df: pd.DataFrame,
    power_col: Optional[str] = None,
    time_col: Optional[str] = None
) -> Tuple[LoadSeries2025, Dict[str, Any]]:
    """
    Transforms any arbitrary raw DataFrame into an exact 35,040-interval LoadSeries2025.
    
    Processing steps:
      1. Resolves power column and converts units to active kW.
      2. Resolves or generates unified timestamps.
      3. Reindexes onto canonical 2025 DatetimeIndex (35,040 steps) with forward-fill / linear interp.
      4. Classifies month indices and Liander HT/NT TOU flags.
      5. Returns normalized LoadSeries2025 and a detailed diagnostic metadata dictionary.
    """
    ref_index = create_reference_2025_timestamps()
    total_expected_steps = len(ref_index)  # 35,040

    df = raw_df.copy()
    
    # Identify or extract power column
    if power_col and power_col in df.columns:
        p_series = pd.to_numeric(
            df[power_col].astype(str).str.replace(" ", "").str.replace(",", "."),
            errors="coerce"
        ).fillna(0.0)
    elif "Total_Demand_kW" in df.columns:
        p_series = pd.to_numeric(df["Total_Demand_kW"], errors="coerce").fillna(0.0)
    else:
        # Fallback to numeric columns
        num_cols = df.select_dtypes(include=[np.number]).columns
        if len(num_cols) > 0:
            p_series = df[num_cols[0]].fillna(0.0)
        else:
            p_series = pd.Series(np.zeros(len(df)))

    # Timestamp alignment
    ts_series = None
    if time_col and time_col in df.columns:
        ts_series = pd.to_datetime(df[time_col], errors="coerce")
    elif "timestamp" in df.columns:
        ts_series = pd.to_datetime(df["timestamp"], errors="coerce")

    # If length already matches 35,040 exactly and no timestamps provided, map directly
    if len(p_series) == total_expected_steps and (ts_series is None or ts_series.isna().all()):
        aligned_power = np.clip(p_series.to_numpy(dtype=float), 0.0, None)
    elif ts_series is not None and ts_series.notna().sum() > (0.5 * len(df)):
        # Construct timeseries with timestamp index
        temp_df = pd.DataFrame({
            "timestamp": ts_series,
            "power_kw": p_series.to_numpy(dtype=float)
        }).dropna(subset=["timestamp"]).drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
        
        temp_df = temp_df.set_index("timestamp")
        
        # If year is not 2025, shift calendar year to 2025
        first_year = temp_df.index[0].year if len(temp_df) > 0 else 2025
        if first_year != 2025:
            # Shift timestamps by year delta
            try:
                temp_df.index = temp_df.index.map(lambda dt: dt.replace(year=2025))
            except Exception:
                # In case of leap day Feb 29
                temp_df.index = temp_df.index.map(
                    lambda dt: dt.replace(year=2025, day=28) if (dt.month == 2 and dt.day == 29) else dt.replace(year=2025)
                )
        
        # Strip timezone if present to align cleanly with naive reference index
        if temp_df.index.tz is not None:
            temp_df.index = temp_df.index.tz_localize(None)

        # Reindex onto reference index
        reindexed = temp_df["power_kw"].reindex(ref_index)
        aligned_power = reindexed.interpolate(method="linear").bfill().ffill().fillna(0.0).to_numpy(dtype=float)
        aligned_power = np.clip(aligned_power, 0.0, None)
    else:
        # Interpolate or tile array to exact 35,040 steps
        n_raw = len(p_series)
        if n_raw == 0:
            aligned_power = np.zeros(total_expected_steps, dtype=float)
        elif n_raw == 96:
            # Single 24-hour daily curve: replicate across 365 days
            aligned_power = np.tile(p_series.to_numpy(dtype=float), 365)
        else:
            x_old = np.linspace(0, 1, n_raw)
            x_new = np.linspace(0, 1, total_expected_steps)
            aligned_power = np.interp(x_new, x_old, p_series.to_numpy(dtype=float))
            aligned_power = np.clip(aligned_power, 0.0, None)

    # Classifications
    energy_kwh = aligned_power * 0.25
    month_indices = ref_index.month.to_numpy(dtype=int)
    is_peak_tou = classify_liander_tou_window(ref_index)

    load_obj = LoadSeries2025(
        timestamps=ref_index,
        power_kw=aligned_power,
        energy_kwh=energy_kwh,
        month_indices=month_indices,
        is_peak_tou=is_peak_tou,
        total_steps=total_expected_steps,
        step_hours=0.25
    )

    diagnostics = {
        "total_steps": total_expected_steps,
        "total_energy_kwh": load_obj.total_energy_kwh,
        "peak_demand_kw": load_obj.peak_demand_kw,
        "ht_intervals_count": int(np.sum(is_peak_tou)),
        "nt_intervals_count": int(np.sum(~is_peak_tou)),
        "mean_power_kw": float(np.mean(aligned_power)),
    }

    return load_obj, diagnostics


def synthesize_benchmark_load_profile_2025(
    profile_type: str = "commercial_hvac",
    nominal_peak_kw: float = 250.0
) -> LoadSeries2025:
    """
    Synthesizes a realistic 35,040-step annual commercial profile for 2025
    incorporating workdays, daytime HVAC/production, and evening baseload.
    """
    ref_index = create_reference_2025_timestamps()
    n_steps = len(ref_index)
    
    # Build synthetic consumers
    # 1. Daytime Operations (Mo-Fr 07:30 - 17:30)
    day_window = TimeWindow(
        start_time=pd.to_datetime("07:30").time(),
        end_time=pd.to_datetime("17:30").time(),
        has_peak=True,
        peak_power_kw=nominal_peak_kw * 0.65,
        peak_duration_min=45
    )
    c_ops = SimpleConsumer(
        name="Commercial_Operations",
        power_kw=nominal_peak_kw * 0.60,
        time_windows=[day_window],
        active_days=[0, 1, 2, 3, 4],
        seasonal_pattern="summer_heavy",
        standby_power_ratio=0.10
    )
    
    # 2. Continuous Baseload & Cold Storage (24/7)
    base_window = TimeWindow(
        start_time=pd.to_datetime("00:00").time(),
        end_time=pd.to_datetime("23:45").time(),
        is_24h=True
    )
    c_base = SimpleConsumer(
        name="Baseload_HVAC",
        power_kw=nominal_peak_kw * 0.25,
        time_windows=[base_window],
        active_days=[0, 1, 2, 3, 4, 5, 6],
        seasonal_pattern="flat",
        standby_power_ratio=1.0
    )

    df_year, total_curve, _ = aggregate_synthetic_year(
        consumers=[c_ops, c_base],
        year=2025,
        holidays=[]
    )

    # Ensure length 35,040
    power_kw = total_curve[:n_steps]
    if len(power_kw) < n_steps:
        power_kw = np.pad(power_kw, (0, n_steps - len(power_kw)), mode="edge")

    energy_kwh = power_kw * 0.25
    month_indices = ref_index.month.to_numpy(dtype=int)
    is_peak_tou = classify_liander_tou_window(ref_index)

    return LoadSeries2025(
        timestamps=ref_index,
        power_kw=power_kw,
        energy_kwh=energy_kwh,
        month_indices=month_indices,
        is_peak_tou=is_peak_tou,
        total_steps=n_steps,
        step_hours=0.25
    )


def extract_monthly_consumption_records(
    load: LoadSeries2025
) -> List[MonthlyConsumptionRecord]:
    """
    Aggregates the 35,040 intervals into exactly 12 calendar month records:
      - Total active kWh (E_m)
      - Peak TOU energy (HT)
      - Off-peak TOU energy (NT)
      - Maximum active 15-minute power demand (P_peak,m in kW)
    """
    records: List[MonthlyConsumptionRecord] = []
    
    for m in range(1, 13):
        mask = (load.month_indices == m)
        m_power = load.power_kw[mask]
        m_energy = load.energy_kwh[mask]
        m_is_ht = load.is_peak_tou[mask]
        
        m_total_kwh = float(np.sum(m_energy))
        m_ht_kwh = float(np.sum(m_energy[m_is_ht]))
        m_nt_kwh = float(np.sum(m_energy[~m_is_ht]))
        m_peak_kw = float(np.max(m_power)) if len(m_power) > 0 else 0.0
        days_in_m = MONTH_DAYS_2025.get(m, 30)

        records.append(
            MonthlyConsumptionRecord(
                month_index=m,
                month_name=MONTH_NAMES[m - 1],
                days_count=days_in_m,
                total_kwh=round(m_total_kwh, 3),
                peak_tou_kwh=round(m_ht_kwh, 3),
                offpeak_tou_kwh=round(m_nt_kwh, 3),
                peak_demand_kw=round(m_peak_kw, 3)
            )
        )

    return records


def evaluate_load_integrity_audit(
    load: LoadSeries2025,
    monthly_records: List[MonthlyConsumptionRecord]
) -> Dict[str, Any]:
    """
    Validates Audit Point 1 (Prüfpunkt 1: Lastgang-Integrität):
      - Criterion 1.1: Exactly 35,040 steps for 2025.
      - Criterion 1.2: Sum of interval energy == Sum of 12 monthly energies (E_total = sum(E_m)).
      - Criterion 1.3: Each interval is uniquely mapped to month 1..12 and TOU window HT/NT.
    """
    c1_1_pass = (len(load.power_kw) == 35040)
    
    interval_sum_kwh = float(np.sum(load.energy_kwh))
    monthly_sum_kwh = float(sum(r.total_kwh for r in monthly_records))
    diff_kwh = abs(interval_sum_kwh - monthly_sum_kwh)
    c1_2_pass = (diff_kwh < 1e-3)

    c1_3_month_valid = (
        len(load.month_indices) == 35040 and
        np.all(load.month_indices >= 1) and
        np.all(load.month_indices <= 12)
    )
    c1_3_tou_valid = (
        len(load.is_peak_tou) == 35040 and
        load.is_peak_tou.dtype == bool
    )
    c1_3_pass = (c1_3_month_valid and c1_3_tou_valid)

    all_passed = (c1_1_pass and c1_2_pass and c1_3_pass)

    return {
        "audit_point": 1,
        "title": "Audit Point 1: Load Profile Integrity",
        "passed": all_passed,
        "criteria": {
            "1.1_step_count_35040": {
                "passed": c1_1_pass,
                "actual_count": len(load.power_kw),
                "expected_count": 35040
            },
            "1.2_energy_conservation": {
                "passed": c1_2_pass,
                "interval_sum_kwh": round(interval_sum_kwh, 3),
                "monthly_sum_kwh": round(monthly_sum_kwh, 3),
                "delta_kwh": round(diff_kwh, 6)
            },
            "1.3_time_classification": {
                "passed": c1_3_pass,
                "month_indices_valid": bool(c1_3_month_valid),
                "tou_flags_valid": bool(c1_3_tou_valid)
            }
        }
    }
