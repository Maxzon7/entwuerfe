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

from current_model.core.synthetic_engine import aggregate_synthetic_24h, aggregate_synthetic_year


def find_active_load_data_in_session(prefer_annual: bool = True) -> Tuple[Optional[pd.DataFrame], str, str]:
    """
    Finds the active consumption load dataset established in Tab 1.
    Checks CSV real meter data, 365-day annual synthetic profiles, and 24-hour synthetic profiles.

    When prefer_annual=True (default), automatically ensures downstream simulation tabs
    (Tab 4 BESS, Tab 3 Solar, Tab 2 Contract) receive the full 365-day annual profile
    rather than a single 24-hour day.

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

    def _resolve_synthetic_dataset() -> Optional[Tuple[pd.DataFrame, str, str]]:
        if prefer_annual:
            # 1. Check for dedicated annual 365-day profile
            if "active_synthetic_year_df" in st.session_state and isinstance(st.session_state["active_synthetic_year_df"], pd.DataFrame):
                df_y = st.session_state["active_synthetic_year_df"]
                if not df_y.empty:
                    return df_y, "Synthetic Simulation (365 Days)", _get_power_col(df_y)

            # 2. Check active_synthetic_df
            if "active_synthetic_df" in st.session_state and isinstance(st.session_state["active_synthetic_df"], pd.DataFrame):
                df_syn = st.session_state["active_synthetic_df"]
                if not df_syn.empty:
                    if len(df_syn) > 96:
                        return df_syn, "Synthetic Simulation (365 Days)", _get_power_col(df_syn)
                    # If 24h is stored, generate full 365-day profile from consumers if available
                    for k, val in st.session_state.items():
                        if "consumers" in k and isinstance(val, list) and len(val) > 0:
                            df_year, _, _ = aggregate_synthetic_year(val, year=2025)
                            st.session_state["active_synthetic_df"] = df_year
                            st.session_state["active_synthetic_year_df"] = df_year
                            return df_year, "Synthetic Simulation (365 Days)", _get_power_col(df_year)
                    return df_syn, "Synthetic Simulation (24-Hour)", _get_power_col(df_syn)

            # 3. Fallback: generate from consumers
            for k, val in st.session_state.items():
                if "consumers" in k and isinstance(val, list) and len(val) > 0:
                    df_year, _, _ = aggregate_synthetic_year(val, year=2025)
                    st.session_state["active_synthetic_df"] = df_year
                    st.session_state["active_synthetic_year_df"] = df_year
                    return df_year, "Synthetic Simulation (365 Days)", _get_power_col(df_year)
        else:
            if "active_synthetic_day_df" in st.session_state and isinstance(st.session_state["active_synthetic_day_df"], pd.DataFrame):
                df_d = st.session_state["active_synthetic_day_df"]
                if not df_d.empty:
                    return df_d, "Synthetic Simulation (24-Hour)", _get_power_col(df_d)
            if "active_synthetic_df" in st.session_state and isinstance(st.session_state["active_synthetic_df"], pd.DataFrame):
                df_syn = st.session_state["active_synthetic_df"]
                if not df_syn.empty:
                    return df_syn, "Synthetic Simulation", _get_power_col(df_syn)

        return None

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
        syn_res = _resolve_synthetic_dataset()
        if syn_res:
            return syn_res

    else:
        # Prioritize Synthetic
        syn_res = _resolve_synthetic_dataset()
        if syn_res:
            return syn_res

        if "active_csv_df" in st.session_state and isinstance(st.session_state["active_csv_df"], pd.DataFrame):
            df_active = st.session_state["active_csv_df"]
            if not df_active.empty:
                fname = st.session_state.get("active_csv_filename", "Uploaded CSV")
                return df_active, f"CSV Real Meter Data ({fname})", _get_power_col(df_active)

    # Final fallback to consumer list if exists
    for key, val in st.session_state.items():
        if "consumers" in key and isinstance(val, list) and len(val) > 0:
            if prefer_annual:
                df_year, _, _ = aggregate_synthetic_year(val, year=2025)
                st.session_state["active_synthetic_df"] = df_year
                st.session_state["active_synthetic_year_df"] = df_year
                return df_year, "Synthetic Simulation (365 Days)", _get_power_col(df_year)
            else:
                df_day, total_curve, _ = aggregate_synthetic_24h(val)
                if len(total_curve) > 0 and total_curve.sum() > 0:
                    return df_day, "24-Hour Synthetic Simulation", _get_power_col(df_day)

    return None, "None", ""


def find_active_contract_in_session() -> Optional[Any]:
    """
    Finds the active electricity contract configured in the workspace (Tab 3: Current Contract,
    active sub-scenario custom tariff, or active project container).
    """
    from current_model.models.contract import Contract

    def _as_contract(obj: Any) -> Optional[Contract]:
        if obj is None:
            return None
        if isinstance(obj, Contract):
            return obj
        # Duck typing or reloaded class
        if hasattr(obj, "to_dict") and (hasattr(obj, "contracted_capacity_kw") or hasattr(obj, "tou_rates")):
            try:
                return Contract.from_dict(obj.to_dict())
            except Exception:
                pass
        if hasattr(obj, "contracted_capacity_kw") and hasattr(obj, "tou_rates"):
            return obj
        if isinstance(obj, dict) and ("contracted_capacity_kw" in obj or "tou_rates" in obj):
            try:
                return Contract.from_dict(obj)
            except Exception:
                pass
        return None

    # 1. Inspect ProjectContainer in session_state
    if "project_container" in st.session_state:
        proj = st.session_state["project_container"]
        if proj:
            # Check if active sub-scenario has a custom tariff
            if hasattr(proj, "get_active_scenario"):
                active_sub = proj.get_active_scenario()
                if active_sub and getattr(active_sub, "use_custom_grid_tariff", False):
                    cust = getattr(active_sub, "custom_contract", None) or getattr(active_sub, "custom_grid_tariff", None)
                    if cust is not None:
                        c = _as_contract(cust)
                        if c is not None:
                            return c
            # Check base scenario contract
            if hasattr(proj, "base_scenario") and proj.base_scenario and getattr(proj.base_scenario, "base_contract", None):
                c = _as_contract(proj.base_scenario.base_contract)
                if c is not None:
                    return c

    # 2. Check prioritized session keys
    priority_keys = [
        "active_contract",
        "app_tab2_contract_model",
        "app_tab2_contract",
        "app_tab2_base_contract_model",
        "tab2_contract_model",
        "tab2_contract",
        "tab2_base_contract_model",
        "app_contract_switch_contract_model",
        "contract"
    ]
    for k in priority_keys:
        if k in st.session_state:
            c = _as_contract(st.session_state[k])
            if c is not None:
                return c

    # 3. Search dynamically across all session keys
    for k, v in st.session_state.items():
        if "contract" in k.lower():
            c = _as_contract(v)
            if c is not None:
                return c

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
