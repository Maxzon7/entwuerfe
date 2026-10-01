"""
========================================================================================
Wholesale Electricity Market Price Engine (current_model/core/market_price_engine.py)
========================================================================================

Description:
------------
Provides robust ingestion, high-speed caching, temporal alignment, and lookup
for historical and day-ahead wholesale electricity spot market price time series
(e.g., EPEX Spot Netherlands 2025, ENTSO-E, Energy-Charts).
Harmonizes 60-minute auction prices and 15-minute continuous contracts into
sub-hourly 15-minute settlement resolution for load profiling and financial billing.
========================================================================================
"""

import os
import sys
from typing import Dict, Any, List, Optional, Tuple, Union
import datetime
import numpy as np
import pandas as pd

# Path resolution for market_prices directory
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
MARKET_PRICES_DIR = os.path.join(MODEL_ROOT, "sample_data", "market_prices")

# Module-level memory cache for loaded and resampled price series
_PRICE_CACHE: Dict[str, pd.DataFrame] = {}
_ALIGNMENT_CACHE: Dict[str, Dict[Tuple[int, int, int, int], float]] = {}

AVAILABLE_MARKET_PROFILES: Dict[str, Dict[str, Any]] = {
    "epex_nl_2025": {
        "id": "epex_nl_2025",
        "name": "Netherlands Day-Ahead (EPEX Spot NL 2025)",
        "country": "Netherlands",
        "currency": "EUR",
        "resolution": "15-minute / 60-minute harmonized",
        "filename": "energy-charts_Stromproduktion_und_Börsenstrompreise_der_Niederlande_2025.csv",
        "description": "Hourly and 15-minute Day-Ahead auction prices for bidding zone NL published via Energy-Charts / Bundesnetzagentur."
    }
}


def list_available_market_profiles() -> Dict[str, Dict[str, Any]]:
    """
    Returns registered market price profiles and their availability on disk.
    """
    results = {}
    for p_id, meta in AVAILABLE_MARKET_PROFILES.items():
        entry = dict(meta)
        fpath = os.path.join(MARKET_PRICES_DIR, entry["filename"])
        entry["file_path"] = fpath
        entry["is_available"] = os.path.isfile(fpath)
        results[p_id] = entry
    return results


def load_market_price_series(
    profile_id: str = "epex_nl_2025",
    force_reload: bool = False
) -> pd.DataFrame:
    """
    Loads, cleans, and standardizes a market price CSV dataset.
    Coalesces 15-minute and hourly day-ahead auction columns, converts
    prices from EUR/MWh to EUR/kWh, and forward-fills to regular 15-minute
    resolution covering the entire year.

    Returns:
        pd.DataFrame indexed by timezone-aware Timestamp with columns:
        ['price_eur_kwh', 'price_eur_mwh']
    """
    global _PRICE_CACHE
    if not force_reload and profile_id in _PRICE_CACHE:
        return _PRICE_CACHE[profile_id]

    meta = AVAILABLE_MARKET_PROFILES.get(profile_id)
    if not meta:
        raise ValueError(f"Unknown market price profile '{profile_id}'. Available: {list(AVAILABLE_MARKET_PROFILES.keys())}")

    fpath = os.path.join(MARKET_PRICES_DIR, meta["filename"])
    if not os.path.isfile(fpath):
        # Fallback check for ascii filename if utf-8 umlauts differ on some systems
        for fname in os.listdir(MARKET_PRICES_DIR) if os.path.isdir(MARKET_PRICES_DIR) else []:
            if "energy-charts" in fname.lower() and "niederlande" in fname.lower() and "2025" in fname:
                fpath = os.path.join(MARKET_PRICES_DIR, fname)
                break

    if not os.path.isfile(fpath):
        raise FileNotFoundError(f"Market price dataset not found on disk: {fpath}")

    # Read CSV skipping initial disclaimer line (row 0) and units line (row 2)
    # The header line is row 1
    raw_df = pd.read_csv(fpath, skiprows=[0, 2], encoding="utf-8-sig")

    date_col = None
    for col in raw_df.columns:
        if "datum" in str(col).lower() or "date" in str(col).lower():
            date_col = col
            break
    if not date_col:
        date_col = raw_df.columns[0]

    # Parse timestamps to UTC
    ts_series = pd.to_datetime(raw_df[date_col], utc=True, errors="coerce")

    # Coalesce 15-minute auction column with hourly auction column
    col_15m = None
    col_60m = None
    for c in raw_df.columns:
        c_str = str(c).lower()
        if "15 minuten" in c_str or "15min" in c_str:
            col_15m = c
        elif "day ahead auktion" in c_str or "day-ahead" in c_str or "auktion" in c_str:
            col_60m = c

    series_15m = pd.to_numeric(raw_df[col_15m], errors="coerce") if col_15m else pd.Series(np.nan, index=raw_df.index)
    series_60m = pd.to_numeric(raw_df[col_60m], errors="coerce") if col_60m else pd.Series(np.nan, index=raw_df.index)

    p_mwh = series_15m.fillna(series_60m)
    p_kwh = p_mwh / 1000.0

    clean_df = pd.DataFrame({
        "timestamp": ts_series,
        "price_eur_kwh": p_kwh,
        "price_eur_mwh": p_mwh
    }).dropna(subset=["timestamp"]).sort_values("timestamp")

    # Drop duplicate timestamps if any
    clean_df = clean_df.drop_duplicates(subset=["timestamp"])
    clean_df = clean_df.set_index("timestamp")

    # Resample to regular 15-minute frequency with forward fill
    resampled_df = clean_df.resample("15min").ffill()

    _PRICE_CACHE[profile_id] = resampled_df

    # Populate alignment fast lookup dictionary: (month, day, hour, minute) -> price_eur_kwh
    lookup_dict: Dict[Tuple[int, int, int, int], float] = {}
    for idx_ts, row_val in zip(resampled_df.index, resampled_df["price_eur_kwh"].to_numpy(dtype=float)):
        key = (idx_ts.month, idx_ts.day, idx_ts.hour, idx_ts.minute)
        lookup_dict[key] = float(row_val)
    _ALIGNMENT_CACHE[profile_id] = lookup_dict

    return resampled_df


def get_aligned_market_prices(
    timestamps: Optional[Union[List[Any], pd.Series, pd.DatetimeIndex]] = None,
    profile_id: str = "epex_nl_2025",
    default_rate: float = 0.20,
    n_steps: Optional[int] = None,
    step_hours: float = 0.25
) -> np.ndarray:
    """
    Returns a 1D numpy array of spot market prices (€/kWh) aligned with the provided
    meter timestamps. If timestamps are from a non-2025 year, seamlessly aligns by
    calendar day and hour (month, day, hour, minute) so that market price shape
    is fully applied.

    If timestamps is None, uses synthetic representative day mapping (96 steps)
    or returns array of default_rate.
    """
    try:
        price_df = load_market_price_series(profile_id=profile_id)
        lookup_dict = _ALIGNMENT_CACHE.get(profile_id, {})
    except Exception:
        # If dataset could not be loaded, fallback to default rate
        count = len(timestamps) if timestamps is not None else (n_steps or 96)
        return np.full(count, default_rate, dtype=float)

    if timestamps is not None and len(timestamps) > 0:
        ts_series = pd.Series(pd.to_datetime(timestamps, errors="coerce"))
        n = len(ts_series)
        out_prices = np.empty(n, dtype=float)

        # Check if year is mostly 2025
        non_null = ts_series.dropna()
        is_year_2025 = False
        if len(non_null) > 0:
            sample_years = non_null.head(10).dt.year.to_numpy()
            if np.all(sample_years == 2025):
                is_year_2025 = True

        if is_year_2025:
            # Direct index lookup using pandas reindex or asof
            ts_idx = pd.DatetimeIndex(ts_series)
            ts_utc = ts_idx.tz_localize("UTC") if ts_idx.tz is None else ts_idx.tz_convert("UTC")
            aligned = price_df["price_eur_kwh"].reindex(ts_utc, method="ffill").bfill()
            arr = aligned.to_numpy(dtype=float)
            # Replace remaining NaNs with default_rate
            out_prices = np.where(np.isnan(arr), default_rate, arr)
            return out_prices

        # Non-2025 year or mixed dates: match by (month, day, hour, minute)
        for i in range(n):
            t = ts_series.iloc[i]
            if pd.isnull(t):
                out_prices[i] = default_rate
                continue
            m, d, h, mi = t.month, t.day, t.hour, (t.minute // 15) * 15
            # Handle leap day February 29
            if m == 2 and d == 29:
                d = 28
            key = (m, d, h, mi)
            if key in lookup_dict:
                out_prices[i] = lookup_dict[key]
            else:
                # Try hour boundary
                key_h = (m, d, h, 0)
                out_prices[i] = lookup_dict.get(key_h, default_rate)

        return out_prices

    else:
        # Synthetic daily profile (no timestamps, e.g. 24h curve with 96 steps)
        steps = n_steps or 96
        out_prices = np.empty(steps, dtype=float)
        # Average hourly price across the entire year for each hour of day
        hourly_means = price_df.groupby(price_df.index.hour)["price_eur_kwh"].mean().to_dict()
        for i in range(steps):
            hour = int((i * (step_hours * 60)) // 60) % 24
            out_prices[i] = float(hourly_means.get(hour, default_rate))
        return out_prices


def get_market_price_kpis(profile_id: str = "epex_nl_2025") -> Dict[str, Any]:
    """
    Computes summary metrics for a market price series.
    """
    price_df = load_market_price_series(profile_id=profile_id)
    kwh = price_df["price_eur_kwh"].to_numpy(dtype=float)
    mwh = price_df["price_eur_mwh"].to_numpy(dtype=float)

    neg_hours = float((kwh < 0.0).sum() * 0.25)
    zero_hours = float((np.isclose(kwh, 0.0, atol=1e-5)).sum() * 0.25)
    total_hours = float(len(kwh) * 0.25)

    return {
        "profile_id": profile_id,
        "count": len(kwh),
        "total_hours": round(total_hours, 1),
        "min_eur_kwh": float(np.min(kwh)),
        "max_eur_kwh": float(np.max(kwh)),
        "mean_eur_kwh": float(np.mean(kwh)),
        "median_eur_kwh": float(np.median(kwh)),
        "std_eur_kwh": float(np.std(kwh)),
        "min_eur_mwh": float(np.min(mwh)),
        "max_eur_mwh": float(np.max(mwh)),
        "mean_eur_mwh": float(np.mean(mwh)),
        "negative_price_hours": round(neg_hours, 1),
        "zero_price_hours": round(zero_hours, 1)
    }
