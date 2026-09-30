"""
========================================================================================
Data Processor & Normalization Engine (current_model/core/load_processor.py)
========================================================================================

Description:
------------
Transforms raw CSV data tables into unified, standardized, and unit-corrected load profile time series.
Includes smart fallback timestamp recovery if an invalid ID column was selected.
"""

from typing import List, Optional, Tuple, Any
import re
import pandas as pd
import numpy as np


def _extract_datetime_string(s: str) -> str:
    """Extracts date/time pattern (e.g. DD.MM.YYYY HH:MM:SS) if mixed with extraneous ID text."""
    s_str = str(s).strip()
    match = re.search(r'(\b\d{1,4}[./-]\d{1,2}[./-]\d{2,4}(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?\b)', s_str)
    return match.group(1) if match else s_str


def _try_parse_timestamps(
    df: pd.DataFrame,
    cols: List[str],
    dayfirst: Optional[bool] = None
) -> Tuple[Optional[pd.Series], bool]:
    """Helper to try parsing a unified timestamp Series from given column(s) with adaptive coverage maximization."""
    if not cols:
        return None, True

    if len(cols) == 1:
        raw_ts = df[cols[0]].astype(str).str.strip()
    else:
        raw_ts = df[cols].astype(str).agg(' '.join, axis=1)

    cleaned_ts = raw_ts.apply(_extract_datetime_string)
    sample_first = cleaned_ts.dropna().iloc[0] if not cleaned_ts.dropna().empty else ""
    starts_with_year = bool(re.match(r"^\s*\d{4}", str(sample_first)))

    # Candidates:
    # 1. Standard dayfirst=True (DD/MM/YYYY, DD.MM.YYYY)
    # 2. Standard dayfirst=False (YYYY-MM-DD or MM/DD/YYYY)
    # 3. format="mixed"
    candidates = []

    p_dtrue = pd.to_datetime(cleaned_ts, dayfirst=True, errors="coerce")
    candidates.append((p_dtrue.notnull().sum(), True, p_dtrue))

    p_dfalse = pd.to_datetime(cleaned_ts, dayfirst=False, errors="coerce")
    candidates.append((p_dfalse.notnull().sum(), False, p_dfalse))

    try:
        p_mixed = pd.to_datetime(cleaned_ts, format="mixed", errors="coerce")
        candidates.append((p_mixed.notnull().sum(), not starts_with_year, p_mixed))
    except Exception:
        pass

    # Sort candidates by number of successfully parsed timestamps descending
    candidates.sort(key=lambda x: x[0], reverse=True)
    best_count, best_dayfirst, best_parsed = candidates[0]

    # If user explicitly requested dayfirst, and it achieves at least 95% of best_count, respect user choice
    if dayfirst is not None:
        user_candidates = [c for c in candidates if c[1] == dayfirst]
        if user_candidates and user_candidates[0][0] >= max(1, int(0.95 * best_count)):
            return user_candidates[0][2], dayfirst

    # Otherwise return the highest-coverage parser
    return best_parsed, best_dayfirst


def process_load_profile_data(
    df_raw: pd.DataFrame,
    selected_time_cols: List[str],
    selected_power_cols: List[str],
    selected_unit: str,
    max_rows: Optional[int] = None,
    dayfirst: Optional[bool] = None
) -> pd.DataFrame:
    """
    Transforms raw CSV data into a clean, chronologically sorted DataFrame with:
      - 'timestamp': Unified pandas DatetimeIndex
      - Each selected power measurement column converted to kW
      - 'Total_Demand_kW': Sum of all selected active measurement columns in kW
    """
    if not selected_power_cols:
        raise ValueError("At least one power measurement column must be selected.")

    df_sliced = df_raw.iloc[:max_rows].copy() if max_rows else df_raw.copy()

    # 1. Attempt parsing timestamps from user-selected columns
    parsed_ts, dayfirst_used = _try_parse_timestamps(df_sliced, selected_time_cols, dayfirst)

    # 2. Smart auto-recovery: If user selection yielded no valid dates (e.g. user selected Col_1 instead of Col_2 + Col_3)
    if parsed_ts is None or parsed_ts.notnull().sum() == 0:
        # Search all columns in df_raw for valid date & time columns
        from current_model.core.csv_parser import detect_suggested_columns
        suggested_time, _, _ = detect_suggested_columns(df_sliced)
        if suggested_time and suggested_time != selected_time_cols:
            parsed_ts, dayfirst_used = _try_parse_timestamps(df_sliced, suggested_time, dayfirst)

    if parsed_ts is None or parsed_ts.notnull().sum() == 0:
        cols_str = ", ".join(f"'{c}'" for c in selected_time_cols)
        raise ValueError(
            f"The selected timestamp column(s) ({cols_str}) do not contain valid date/time values. "
            "Please select the Date and Time columns (e.g. 'Col_2' and 'Col_3' or 'FECHA_REG' and 'HORA_REG') in the dropdown."
        )

    df_clean = pd.DataFrame()
    df_clean["timestamp"] = parsed_ts

    valid_mask = df_clean["timestamp"].notnull()
    df_clean = df_clean[valid_mask].copy()

    if df_clean.empty:
        raise ValueError("Could not parse any valid timestamps with the selected column(s).")

    # 3. Process numeric columns and convert units to kW
    for p_col in selected_power_cols:
        if p_col not in df_sliced.columns:
            continue
        series = df_sliced.loc[valid_mask, p_col]

        # Clean European decimal commas and thousand spaces
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

    # 4. Compute Total Demand (kW)
    existing_p_cols = [c for c in selected_power_cols if c in df_clean.columns]
    df_clean["Total_Demand_kW"] = df_clean[existing_p_cols].sum(axis=1)

    # 5. Sort chronologically
    df_clean = df_clean.sort_values("timestamp").reset_index(drop=True)
    return df_clean
