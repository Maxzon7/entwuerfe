"""
Data Processor & Normalization Module
=====================================
Transforms raw CSV tables into unified, standardized, and unit-corrected load profile time series.
"""

from typing import List
import pandas as pd
import numpy as np


def process_load_profile_data(
    df_raw: pd.DataFrame,
    selected_time_cols: List[str],
    selected_power_cols: List[str],
    selected_unit: str,
    max_rows: int = None,
    dayfirst: bool = None
) -> pd.DataFrame:
    """
    Transforms raw CSV data into a clean, chronologically sorted DataFrame with:
      - 'timestamp': Unified pandas DatetimeIndex
      - Each selected power measurement column converted to kW
      - 'Total_Demand_kW': Sum of all selected active measurement columns in kW
    """
    if not selected_time_cols:
        raise ValueError("At least one timestamp column must be selected.")
    if not selected_power_cols:
        raise ValueError("At least one power measurement column must be selected.")

    # Slice max rows if requested
    df_sliced = df_raw.iloc[:max_rows].copy() if max_rows else df_raw.copy()

    # 1. Construct unified timestamp series from single or multiple columns
    if len(selected_time_cols) == 1:
        raw_ts = df_sliced[selected_time_cols[0]].astype(str).str.strip()
    else:
        # Concatenate in selected order with space (e.g. Date + Time)
        raw_ts = df_sliced[selected_time_cols].astype(str).agg(' '.join, axis=1)

    import re
    if dayfirst is None:
        # Check if raw timestamp starts with a 4-digit year (e.g. YYYY.MM.DD or YYYY-MM-DD)
        first_valid = raw_ts.dropna().iloc[0] if not raw_ts.dropna().empty else ""
        starts_with_year = bool(re.match(r"^\s*\d{4}", str(first_valid)))
        dayfirst = not starts_with_year

    df_clean = pd.DataFrame()
    df_clean["timestamp"] = pd.to_datetime(
        raw_ts,
        dayfirst=dayfirst,
        errors="coerce"
    )

    # Filter out unparseable rows
    valid_mask = df_clean["timestamp"].notnull()
    df_clean = df_clean[valid_mask].copy()

    if df_clean.empty:
        raise ValueError("Could not parse any valid timestamps with the selected column(s).")

    # 2. Process numeric columns and convert units to kW
    for p_col in selected_power_cols:
        series = df_sliced.loc[valid_mask, p_col]
        
        # Clean European commas and spaces if object/string
        if series.dtype == object:
            series = series.astype(str).str.replace(" ", "").str.replace(",", ".")
        
        numeric_series = pd.to_numeric(series, errors="coerce").fillna(0.0)

        # Apply Unit Multiplier to convert to active power (kW)
        if "15-min" in selected_unit:
            # 15-minute interval energy (kWh) to active electrical power (kW): E / 0.25h = E * 4
            numeric_series = numeric_series * 4.0
        elif "Hourly" in selected_unit:
            numeric_series = numeric_series * 1.0
        elif "Watt" in selected_unit:
            numeric_series = numeric_series / 1000.0

        df_clean[p_col] = numeric_series

    # 3. Compute Total Demand (kW)
    df_clean["Total_Demand_kW"] = df_clean[selected_power_cols].sum(axis=1)

    # 4. Sort chronologically
    df_clean = df_clean.sort_values("timestamp").reset_index(drop=True)
    return df_clean
