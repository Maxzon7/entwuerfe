"""
========================================================================================
Session Utilities (current_model/ui/common/session_utils.py)
========================================================================================

Description:
------------
Provides robust session-state discovery and cross-tab data synchronization:
  - Discovers active consumption load profiles created in Tab 1 (CSV or Synthetic).
  - Inspects active electricity contracts from Tab 2.
  - Generates fast summary metrics for load data (total energy, peak power, interval duration).
"""

from typing import Tuple, Optional, Any, Dict
import pandas as pd
import numpy as np
import streamlit as st

from current_model.core.synthetic_engine import aggregate_synthetic_24h


def find_active_load_data_in_session() -> Tuple[Optional[pd.DataFrame], str, str]:
    """
    Finds the active consumption load dataset established in Tab 1.
    Checks CSV real meter data, 365-day annual synthetic profiles, and 24-hour synthetic profiles.

    Returns:
      (df_load, source_description, power_column_name)
      If no active load is found, returns (None, "None", "").
    """
    active_source = st.session_state.get("tab1_active_source", "csv")

    def _get_power_col(df: pd.DataFrame) -> str:
        for c in ["Total_Demand_kW", "Power_kW", "kW", "Active_Power_kW", "P_Load_kW"]:
            if c in df.columns:
                return c
        # Fallback to last numeric column
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        return numeric_cols[-1] if numeric_cols else df.columns[-1]

    if active_source == "csv":
        # 1. Directly check active CSV dataframe
        if "active_csv_df" in st.session_state and isinstance(st.session_state["active_csv_df"], pd.DataFrame):
            df_active = st.session_state["active_csv_df"]
            if not df_active.empty:
                fname = st.session_state.get("active_csv_filename", "Uploaded CSV")
                return df_active, f"CSV Real Meter Data ({fname})", _get_power_col(df_active)

        # Fallback to reverse scan of calc_data
        for key in reversed(list(st.session_state.keys())):
            if "calc_data" in key and isinstance(st.session_state[key], dict) and "df_clean" in st.session_state[key]:
                df_clean = st.session_state[key]["df_clean"]
                if isinstance(df_clean, pd.DataFrame) and not df_clean.empty:
                    return df_clean, "CSV Real Meter Data", _get_power_col(df_clean)

        # Fallback to synthetic
        if "active_synthetic_df" in st.session_state and isinstance(st.session_state["active_synthetic_df"], pd.DataFrame):
            df_syn = st.session_state["active_synthetic_df"]
            if not df_syn.empty:
                return df_syn, "Synthetic Simulation", _get_power_col(df_syn)

    else:
        # Prioritize Synthetic
        if "active_synthetic_df" in st.session_state and isinstance(st.session_state["active_synthetic_df"], pd.DataFrame):
            df_syn = st.session_state["active_synthetic_df"]
            if not df_syn.empty:
                return df_syn, "Synthetic Simulation", _get_power_col(df_syn)

        if "active_csv_df" in st.session_state and isinstance(st.session_state["active_csv_df"], pd.DataFrame):
            df_active = st.session_state["active_csv_df"]
            if not df_active.empty:
                fname = st.session_state.get("active_csv_filename", "Uploaded CSV")
                return df_active, f"CSV Real Meter Data ({fname})", _get_power_col(df_active)

    # Fallback to consumer list if exists
    for key, val in st.session_state.items():
        if "consumers" in key and isinstance(val, list) and len(val) > 0:
            df_day, total_curve, _ = aggregate_synthetic_24h(val)
            if len(total_curve) > 0 and total_curve.sum() > 0:
                return df_day, "24-Hour Synthetic Simulation", _get_power_col(df_day)

    return None, "None", ""


def find_active_contract_in_session() -> Optional[Any]:
    """
    Finds the active electricity contract configured in Tab 2.
    """
    from current_model.models.contract import Contract
    for k in ["app_tab2_contract", "tab2_contract", "active_contract"]:
        if k in st.session_state and isinstance(st.session_state[k], Contract):
            return st.session_state[k]

    # Search dynamically in session keys
    for k, v in st.session_state.items():
        if "contract" in k and isinstance(v, Contract):
            return v
    return None


def get_load_profile_summary(df: pd.DataFrame, power_col: str) -> Dict[str, Any]:
    """
    Extracts high-level summary metrics from an electrical load profile dataframe.
    """
    if df is None or df.empty or power_col not in df.columns:
        return {
            "total_kwh": 0.0,
            "total_mwh": 0.0,
            "peak_kw": 0.0,
            "avg_kw": 0.0,
            "data_points": 0,
            "duration_days": 0.0,
            "hours_per_step": 0.25
        }

    p_arr = df[power_col].to_numpy(dtype=float)
    p_arr = np.nan_to_num(p_arr, nan=0.0)

    # Estimate time step
    dt_hours = 0.25
    if "timestamp" in df.columns:
        ts = pd.to_datetime(df["timestamp"])
        if len(ts) > 1:
            diff_sec = (ts.iloc[1] - ts.iloc[0]).total_seconds()
            if diff_sec > 0:
                dt_hours = diff_sec / 3600.0

    total_kwh = float(np.sum(p_arr) * dt_hours)
    peak_kw = float(np.max(p_arr)) if len(p_arr) > 0 else 0.0
    avg_kw = float(np.mean(p_arr)) if len(p_arr) > 0 else 0.0
    duration_days = (len(p_arr) * dt_hours) / 24.0

    return {
        "total_kwh": round(total_kwh, 1),
        "total_mwh": round(total_kwh / 1000.0, 2),
        "peak_kw": round(peak_kw, 1),
        "avg_kw": round(avg_kw, 1),
        "data_points": len(p_arr),
        "duration_days": round(duration_days, 1),
        "hours_per_step": dt_hours
    }
