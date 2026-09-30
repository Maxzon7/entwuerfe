"""
========================================================================================
Solar PV + BESS Hybrid Dispatch Engine (current_model/core/solar_bess_engine.py)
========================================================================================

Description:
------------
Physical 15-minute resolution hybrid photovoltaic and battery storage dispatch engine:
  - Strict priority ladder:
      1. Solar PV supplies facility load directly (Direct Self-Consumption).
      2. Solar PV surplus charges the battery storage system (BESS) up to max charge power and SoC_max.
      3. Remaining excess solar PV power is exported to the grid (or curtailed).
      4. If solar PV generation is insufficient, BESS discharges to cover residual load / shave peaks.
      5. Grid import covers any remaining unmet electrical demand.
  - Energy conservation & round-trip efficiency accounting (charge/discharge sqrt(RTE)).
  - Comprehensive physical KPIs: Autarky rate, Self-consumption rate, Peak demand reduction,
    Equivalent full battery cycles, and Grid overload mitigation.
"""

from typing import Dict, Any, List, Optional, Tuple, Union
from dataclasses import dataclass, field
import numpy as np
import pandas as pd

from current_model.models.solar import SolarPVConfig, SolarLocation, SolarSimulationResult
from current_model.models.bess import BESSConfig
from current_model.core.solar_engine import simulate_solar_pv_generation
from current_model.core.bess_engine import analyze_grid_violations


@dataclass
class SolarBESSKPIs:
    """High-level physical performance indicators for a hybrid Solar + BESS system."""
    # Facility Load & Solar Generation
    annual_load_kwh: float = 0.0
    annual_solar_kwh: float = 0.0
    
    # Solar Partitioning
    direct_consumption_kwh: float = 0.0
    direct_consumption_pct: float = 0.0
    bess_charged_from_pv_kwh: float = 0.0
    bess_charged_from_pv_pct: float = 0.0
    bess_charged_from_grid_kwh: float = 0.0
    bess_charged_total_kwh: float = 0.0
    annual_grid_export_kwh: float = 0.0
    grid_export_pct: float = 0.0
    
    # Battery Performance
    bess_discharged_kwh: float = 0.0
    bess_losses_kwh: float = 0.0
    bess_full_cycles: float = 0.0
    
    # Combined Self-Consumption & Autarky
    total_self_consumption_kwh: float = 0.0
    self_consumption_rate_pct: float = 0.0
    autarky_rate_pct: float = 0.0
    
    # Grid Import & Peak Demand
    annual_grid_import_kwh: float = 0.0
    grid_import_reduction_kwh: float = 0.0
    grid_import_reduction_pct: float = 0.0
    orig_peak_kw: float = 0.0
    new_peak_kw: float = 0.0
    peak_shaved_kw: float = 0.0
    peak_reduction_pct: float = 0.0
    
    # Grid Overload Diagnostics
    orig_violations_count: int = 0
    new_violations_count: int = 0
    violations_eliminated_pct: float = 0.0


@dataclass
class SolarBESSSimulationResult:
    """Complete results from a 15-minute Solar + BESS simulation."""
    solar_config: SolarPVConfig
    bess_config: BESSConfig
    grid_limit_kw: float
    target_shaving_cap_kw: float
    dispatch_strategy: str
    kpis: SolarBESSKPIs
    df_dispatch: pd.DataFrame
    monthly_metrics: List[Dict[str, Any]]
    diagnostics_before: Dict[str, Any]
    diagnostics_after: Dict[str, Any]


MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
]


def simulate_solar_bess_dispatch(
    load_df: pd.DataFrame,
    solar_config: SolarPVConfig,
    bess_config: BESSConfig,
    location: Optional[SolarLocation] = None,
    grid_limit_kw: float = 400.0,
    power_col: Optional[str] = None,
    step_hours: float = 0.25,
    precomputed_solar_df: Optional[pd.DataFrame] = None
) -> SolarBESSSimulationResult:
    """
    Simulates a unified 15-minute Solar PV + BESS hybrid dispatch against facility demand.

    Dispatch Rules:
      1. Solar PV directly supplies load: P_Direct(t) = min(P_Load(t), P_Solar(t)).
      2. If P_Solar(t) > P_Load(t):
           Surplus P_Surplus(t) = P_Solar(t) - P_Load(t).
           Priority 1: Charges BESS up to max_charge_power_kw and SoC_max.
           Priority 2: Any remaining solar is exported to the grid.
      3. If P_Solar(t) < P_Load(t):
           Residual load P_Residual(t) = P_Load(t) - P_Solar(t).
           In Peak Shaving mode:
             - If P_Residual(t) > target_cap_kw: BESS discharges to shave peak down to target_cap_kw.
             - If P_Residual(t) < target_cap_kw: BESS recharges from available grid headroom if allow_grid_charging is True.
           In Self-Consumption mode:
             - BESS discharges to cover residual load from stored solar energy.
           Grid import covers remaining unmet electrical demand.
    """
    # 1. Extract Facility Load Time Series
    if power_col and power_col in load_df.columns:
        p_load = load_df[power_col].to_numpy(dtype=float)
    elif "Total_Demand_kW" in load_df.columns:
        p_load = load_df["Total_Demand_kW"].to_numpy(dtype=float)
    elif "P_Load_kW" in load_df.columns:
        p_load = load_df["P_Load_kW"].to_numpy(dtype=float)
    else:
        num_cols = load_df.select_dtypes(include=[np.number]).columns
        p_load = load_df[num_cols[-1]].to_numpy(dtype=float) if len(num_cols) > 0 else np.zeros(len(load_df))

    p_load = np.nan_to_num(p_load, nan=0.0)
    n_steps = len(p_load)

    # 2. Extract or Generate Timestamps
    if "timestamp" in load_df.columns:
        ts_series = pd.to_datetime(load_df["timestamp"])
    else:
        start_dt = pd.Timestamp("2026-01-01 00:00:00")
        ts_series = pd.date_range(start=start_dt, periods=n_steps, freq=f"{int(step_hours * 60)}min")

    # 3. Obtain Solar Generation Curve (P_AC_kW) with diurnal calendar alignment
    if precomputed_solar_df is not None and "P_AC_kW" in precomputed_solar_df.columns:
        from current_model.core.solar_engine import align_solar_to_load_timestamps
        p_solar = align_solar_to_load_timestamps(precomputed_solar_df, ts_series, solar_power_col="P_AC_kW")
    else:
        # Run solar simulation engine
        from current_model.core.solar_engine import align_solar_to_load_timestamps
        loc = location or SolarLocation()
        solar_sim: SolarSimulationResult = simulate_solar_pv_generation(
            config=solar_config,
            location=loc,
            load_df=load_df
        )
        p_solar = align_solar_to_load_timestamps(solar_sim.df_timeseries, ts_series, solar_power_col="P_AC_kW")

    p_solar = np.nan_to_num(p_solar, nan=0.0)

    # 4. Battery Parameters
    cap_kwh = max(1.0, float(bess_config.capacity_kwh))
    p_chg_max = max(0.1, float(bess_config.max_charge_power_kw))
    p_dis_max = max(0.1, float(bess_config.max_discharge_power_kw))
    soc_min_kwh = cap_kwh * (max(0.0, min(100.0, float(bess_config.soc_min_pct))) / 100.0)
    soc_max_kwh = cap_kwh * (max(0.0, min(100.0, float(bess_config.soc_max_pct))) / 100.0)
    init_soc_kwh = cap_kwh * (max(0.0, min(100.0, float(bess_config.initial_soc_pct))) / 100.0)
    init_soc_kwh = max(soc_min_kwh, min(soc_max_kwh, init_soc_kwh))

    rte = max(0.50, min(1.0, float(bess_config.round_trip_efficiency_pct) / 100.0))
    eta_chg = np.sqrt(rte)
    eta_dis = np.sqrt(rte)

    target_cap_kw = float(bess_config.peak_shaving_threshold_kw)
    if target_cap_kw <= 0:
        target_cap_kw = float(grid_limit_kw)

    strategy = getattr(bess_config, "dispatch_strategy", "self_consumption")
    allow_grid_chg = getattr(bess_config, "allow_grid_charging", True)

    # 5. Output Arrays
    p_direct = np.zeros(n_steps, dtype=float)
    p_surplus = np.zeros(n_steps, dtype=float)
    p_residual = np.zeros(n_steps, dtype=float)
    p_bess_chg_pv = np.zeros(n_steps, dtype=float)
    p_bess_chg_grid = np.zeros(n_steps, dtype=float)
    p_bess_dis = np.zeros(n_steps, dtype=float)
    p_grid_import = np.zeros(n_steps, dtype=float)
    p_grid_export = np.zeros(n_steps, dtype=float)
    soc_kwh = np.zeros(n_steps, dtype=float)
    soc_pct = np.zeros(n_steps, dtype=float)
    p_unmet_peak = np.zeros(n_steps, dtype=float)

    curr_soc = init_soc_kwh

    # 6. Core 15-Minute Hybrid Dispatch Loop
    for i in range(n_steps):
        load_kw = p_load[i]
        solar_kw = p_solar[i]

        if np.isnan(load_kw) or load_kw <= 0.0:
            load_kw = 0.0
        if np.isnan(solar_kw) or solar_kw <= 0.0:
            solar_kw = 0.0

        if solar_kw >= load_kw:
            # --- Case A: Solar Surplus ---
            direct_kw = load_kw
            surplus_kw = solar_kw - load_kw
            residual_kw = 0.0

            p_direct[i] = direct_kw
            p_surplus[i] = surplus_kw
            p_residual[i] = residual_kw
            p_bess_dis[i] = 0.0
            p_bess_chg_grid[i] = 0.0

            # Priority 1: Charge BESS from solar surplus
            if curr_soc < soc_max_kwh and surplus_kw > 0.0:
                room_kwh = max(0.0, soc_max_kwh - curr_soc)
                p_room_kw = room_kwh / (eta_chg * step_hours)
                actual_chg_kw = min(surplus_kw, p_chg_max, p_room_kw)

                p_bess_chg_pv[i] = actual_chg_kw
                energy_added_kwh = actual_chg_kw * eta_chg * step_hours
                curr_soc = min(soc_max_kwh, curr_soc + energy_added_kwh)

                # Priority 2: Export remaining surplus to grid
                export_kw = surplus_kw - actual_chg_kw
                p_grid_export[i] = export_kw
            else:
                p_bess_chg_pv[i] = 0.0
                p_grid_export[i] = surplus_kw

            p_grid_import[i] = 0.0
            p_unmet_peak[i] = 0.0

        else:
            # --- Case B: Solar Deficit / Residual Load ---
            direct_kw = solar_kw
            surplus_kw = 0.0
            residual_kw = load_kw - solar_kw

            p_direct[i] = direct_kw
            p_surplus[i] = surplus_kw
            p_residual[i] = residual_kw
            p_bess_chg_pv[i] = 0.0
            p_grid_export[i] = 0.0

            if strategy == "peak_shaving":
                if residual_kw > target_cap_kw:
                    # Peak Shaving Discharge
                    if curr_soc > soc_min_kwh:
                        avail_kwh = max(0.0, curr_soc - soc_min_kwh)
                        p_avail_kw = (avail_kwh * eta_dis) / step_hours
                        req_shave_kw = residual_kw - target_cap_kw
                        actual_dis_kw = min(req_shave_kw, p_dis_max, p_avail_kw)

                        p_bess_dis[i] = actual_dis_kw
                        energy_drawn_kwh = (actual_dis_kw / eta_dis) * step_hours
                        curr_soc = max(soc_min_kwh, curr_soc - energy_drawn_kwh)
                    else:
                        p_bess_dis[i] = 0.0

                    p_bess_chg_grid[i] = 0.0
                    net_import_kw = residual_kw - p_bess_dis[i]
                    p_grid_import[i] = net_import_kw
                    p_unmet_peak[i] = max(0.0, net_import_kw - target_cap_kw)

                else:
                    # Residual load is under target cap: No discharge needed
                    p_bess_dis[i] = 0.0
                    if allow_grid_chg and curr_soc < soc_max_kwh:
                        grid_headroom_kw = max(0.0, target_cap_kw - residual_kw)
                        room_kwh = max(0.0, soc_max_kwh - curr_soc)
                        p_room_kw = room_kwh / (eta_chg * step_hours)
                        actual_chg_grid_kw = min(grid_headroom_kw, p_chg_max, p_room_kw)

                        p_bess_chg_grid[i] = actual_chg_grid_kw
                        energy_added_kwh = actual_chg_grid_kw * eta_chg * step_hours
                        curr_soc = min(soc_max_kwh, curr_soc + energy_added_kwh)
                        p_grid_import[i] = residual_kw + actual_chg_grid_kw
                    else:
                        p_bess_chg_grid[i] = 0.0
                        p_grid_import[i] = residual_kw

                    p_unmet_peak[i] = 0.0

            elif strategy == "tariff_arbitrage":
                # Check scheduled window
                ts_val = ts_series[i] if i < len(ts_series) else None
                hour = ts_val.hour if (ts_val is not None and hasattr(ts_val, "hour")) else (int(i * step_hours) % 24)
                try:
                    chg_start_h = int(bess_config.arbitrage_charge_start.split(":")[0])
                    chg_end_h = int(bess_config.arbitrage_charge_end.split(":")[0])
                except Exception:
                    chg_start_h, chg_end_h = 0, 6
                try:
                    dis_start_h = int(bess_config.arbitrage_discharge_start.split(":")[0])
                    dis_end_h = int(bess_config.arbitrage_discharge_end.split(":")[0])
                except Exception:
                    dis_start_h, dis_end_h = 17, 22

                in_chg_win = (chg_start_h <= hour < chg_end_h) if chg_start_h < chg_end_h else (hour >= chg_start_h or hour < chg_end_h)
                in_dis_win = (dis_start_h <= hour < dis_end_h) if dis_start_h < dis_end_h else (hour >= dis_start_h or hour < dis_end_h)

                if in_chg_win and allow_grid_chg and curr_soc < soc_max_kwh:
                    grid_headroom_kw = max(0.0, target_cap_kw - residual_kw)
                    room_kwh = max(0.0, soc_max_kwh - curr_soc)
                    p_room_kw = room_kwh / (eta_chg * step_hours)
                    actual_chg_grid_kw = min(grid_headroom_kw, p_chg_max, p_room_kw)

                    p_bess_chg_grid[i] = actual_chg_grid_kw
                    p_bess_dis[i] = 0.0
                    curr_soc = min(soc_max_kwh, curr_soc + actual_chg_grid_kw * eta_chg * step_hours)
                    p_grid_import[i] = residual_kw + actual_chg_grid_kw
                    p_unmet_peak[i] = max(0.0, p_grid_import[i] - target_cap_kw)
                elif in_dis_win and curr_soc > soc_min_kwh and residual_kw > 0.0:
                    avail_kwh = max(0.0, curr_soc - soc_min_kwh)
                    p_avail_kw = (avail_kwh * eta_dis) / step_hours
                    actual_dis_kw = min(residual_kw, p_dis_max, p_avail_kw)

                    p_bess_dis[i] = actual_dis_kw
                    p_bess_chg_grid[i] = 0.0
                    curr_soc = max(soc_min_kwh, curr_soc - (actual_dis_kw / eta_dis) * step_hours)
                    p_grid_import[i] = residual_kw - actual_dis_kw
                    p_unmet_peak[i] = max(0.0, p_grid_import[i] - target_cap_kw)
                else:
                    p_bess_dis[i] = 0.0
                    p_bess_chg_grid[i] = 0.0
                    p_grid_import[i] = residual_kw
                    p_unmet_peak[i] = max(0.0, residual_kw - target_cap_kw)

            else:
                # Default: self_consumption mode
                if curr_soc > soc_min_kwh and residual_kw > 0.0:
                    avail_kwh = max(0.0, curr_soc - soc_min_kwh)
                    p_avail_kw = (avail_kwh * eta_dis) / step_hours
                    actual_dis_kw = min(residual_kw, p_dis_max, p_avail_kw)

                    p_bess_dis[i] = actual_dis_kw
                    energy_drawn_kwh = (actual_dis_kw / eta_dis) * step_hours
                    curr_soc = max(soc_min_kwh, curr_soc - energy_drawn_kwh)
                else:
                    p_bess_dis[i] = 0.0

                p_bess_chg_grid[i] = 0.0
                net_import_kw = residual_kw - p_bess_dis[i]
                p_grid_import[i] = net_import_kw
                p_unmet_peak[i] = max(0.0, net_import_kw - target_cap_kw)

        soc_kwh[i] = curr_soc
        soc_pct[i] = (curr_soc / cap_kwh) * 100.0

    # 7. Build Timeseries DataFrame
    df_dispatch = pd.DataFrame({
        "timestamp": ts_series,
        "P_Load_kW": np.round(p_load, 2),
        "P_Solar_kW": np.round(p_solar, 2),
        "P_Direct_kW": np.round(p_direct, 2),
        "P_Surplus_kW": np.round(p_surplus, 2),
        "P_Residual_kW": np.round(p_residual, 2),
        "P_BESS_Charge_PV_kW": np.round(p_bess_chg_pv, 2),
        "P_BESS_Charge_Grid_kW": np.round(p_bess_chg_grid, 2),
        "P_BESS_Charge_Total_kW": np.round(p_bess_chg_pv + p_bess_chg_grid, 2),
        "P_BESS_Discharge_kW": np.round(p_bess_dis, 2),
        "P_Grid_Import_kW": np.round(p_grid_import, 2),
        "P_Grid_Export_kW": np.round(p_grid_export, 2),
        "P_Unmet_Peak_kW": np.round(p_unmet_peak, 2),
        "SoC_kWh": np.round(soc_kwh, 2),
        "SoC_pct": np.round(soc_pct, 1)
    })

    # 8. Compute Monthly Aggregations
    df_dispatch["month"] = ts_series.dt.month if hasattr(ts_series, "dt") else 1
    monthly_metrics: List[Dict[str, Any]] = []

    for m_idx in range(1, 13):
        m_mask = (df_dispatch["month"] == m_idx)
        m_df = df_dispatch.loc[m_mask]
        m_name = MONTH_NAMES[m_idx - 1]

        if not m_df.empty:
            m_load_kwh = float(m_df["P_Load_kW"].sum() * step_hours)
            m_solar_kwh = float(m_df["P_Solar_kW"].sum() * step_hours)
            m_direct_kwh = float(m_df["P_Direct_kW"].sum() * step_hours)
            m_bess_chg_pv_kwh = float(m_df["P_BESS_Charge_PV_kW"].sum() * step_hours)
            m_bess_chg_grid_kwh = float(m_df["P_BESS_Charge_Grid_kW"].sum() * step_hours)
            m_bess_chg_total_kwh = m_bess_chg_pv_kwh + m_bess_chg_grid_kwh
            m_bess_dis_kwh = float(m_df["P_BESS_Discharge_kW"].sum() * step_hours)
            m_grid_imp_kwh = float(m_df["P_Grid_Import_kW"].sum() * step_hours)
            m_grid_exp_kwh = float(m_df["P_Grid_Export_kW"].sum() * step_hours)
            m_orig_peak = float(m_df["P_Load_kW"].max())
            m_new_peak = float(m_df["P_Grid_Import_kW"].max())
        else:
            m_load_kwh = m_solar_kwh = m_direct_kwh = m_bess_chg_pv_kwh = m_bess_chg_grid_kwh = m_bess_chg_total_kwh = 0.0
            m_bess_dis_kwh = m_grid_imp_kwh = m_grid_exp_kwh = m_orig_peak = m_new_peak = 0.0

        monthly_metrics.append({
            "month_idx": m_idx,
            "month_name": m_name,
            "load_kwh": round(m_load_kwh, 1),
            "solar_kwh": round(m_solar_kwh, 1),
            "direct_kwh": round(m_direct_kwh, 1),
            "bess_charge_pv_kwh": round(m_bess_chg_pv_kwh, 1),
            "bess_charge_grid_kwh": round(m_bess_chg_grid_kwh, 1),
            "bess_charge_kwh": round(m_bess_chg_total_kwh, 1),
            "bess_discharge_kwh": round(m_bess_dis_kwh, 1),
            "grid_import_kwh": round(m_grid_imp_kwh, 1),
            "grid_export_kwh": round(m_grid_exp_kwh, 1),
            "orig_peak_kw": round(m_orig_peak, 1),
            "new_peak_kw": round(m_new_peak, 1)
        })

    # 9. Comprehensive KPIs
    annual_load_kwh = float(np.sum(p_load) * step_hours)
    annual_solar_kwh = float(np.sum(p_solar) * step_hours)
    direct_consumption_kwh = float(np.sum(p_direct) * step_hours)
    bess_charged_pv_kwh = float(np.sum(p_bess_chg_pv) * step_hours)
    bess_charged_grid_kwh = float(np.sum(p_bess_chg_grid) * step_hours)
    bess_charged_total_kwh = bess_charged_pv_kwh + bess_charged_grid_kwh
    bess_discharged_kwh = float(np.sum(p_bess_dis) * step_hours)
    annual_grid_import_kwh = float(np.sum(p_grid_import) * step_hours)
    annual_grid_export_kwh = float(np.sum(p_grid_export) * step_hours)

    bess_losses_kwh = max(0.0, bess_charged_total_kwh - bess_discharged_kwh)
    total_self_consumption_kwh = direct_consumption_kwh + bess_discharged_kwh

    direct_consumption_pct = (direct_consumption_kwh / annual_solar_kwh * 100.0) if annual_solar_kwh > 0 else 0.0
    bess_charged_pv_pct = (bess_charged_pv_kwh / annual_solar_kwh * 100.0) if annual_solar_kwh > 0 else 0.0
    grid_export_pct = (annual_grid_export_kwh / annual_solar_kwh * 100.0) if annual_solar_kwh > 0 else 0.0

    self_consumption_rate_pct = (total_self_consumption_kwh / annual_solar_kwh * 100.0) if annual_solar_kwh > 0 else 0.0
    autarky_rate_pct = (total_self_consumption_kwh / annual_load_kwh * 100.0) if annual_load_kwh > 0 else 0.0

    grid_import_reduction_kwh = max(0.0, annual_load_kwh - annual_grid_import_kwh)
    grid_import_reduction_pct = (grid_import_reduction_kwh / annual_load_kwh * 100.0) if annual_load_kwh > 0 else 0.0

    orig_peak_kw = float(np.max(p_load)) if len(p_load) > 0 else 0.0
    new_peak_kw = float(np.max(p_grid_import)) if len(p_grid_import) > 0 else 0.0
    peak_shaved_kw = max(0.0, orig_peak_kw - new_peak_kw)
    peak_reduction_pct = (peak_shaved_kw / orig_peak_kw * 100.0) if orig_peak_kw > 0 else 0.0

    bess_full_cycles = (bess_discharged_kwh / cap_kwh) if cap_kwh > 0 else 0.0

    # 10. Grid Overload Diagnostics (Before vs After)
    diag_before = analyze_grid_violations(p_load, grid_limit_kw, step_hours)
    diag_after = analyze_grid_violations(p_grid_import, grid_limit_kw, step_hours)

    orig_violations = diag_before.get("total_violation_intervals", 0)
    new_violations = diag_after.get("total_violation_intervals", 0)
    violations_eliminated_pct = (
        ((orig_violations - new_violations) / orig_violations * 100.0)
        if orig_violations > 0 else 100.0
    )

    kpis = SolarBESSKPIs(
        annual_load_kwh=round(annual_load_kwh, 1),
        annual_solar_kwh=round(annual_solar_kwh, 1),
        direct_consumption_kwh=round(direct_consumption_kwh, 1),
        direct_consumption_pct=round(direct_consumption_pct, 1),
        bess_charged_from_pv_kwh=round(bess_charged_pv_kwh, 1),
        bess_charged_from_pv_pct=round(bess_charged_pv_pct, 1),
        bess_charged_from_grid_kwh=round(bess_charged_grid_kwh, 1),
        bess_charged_total_kwh=round(bess_charged_total_kwh, 1),
        annual_grid_export_kwh=round(annual_grid_export_kwh, 1),
        grid_export_pct=round(grid_export_pct, 1),
        bess_discharged_kwh=round(bess_discharged_kwh, 1),
        bess_losses_kwh=round(bess_losses_kwh, 1),
        bess_full_cycles=round(bess_full_cycles, 1),
        total_self_consumption_kwh=round(total_self_consumption_kwh, 1),
        self_consumption_rate_pct=round(self_consumption_rate_pct, 1),
        autarky_rate_pct=round(autarky_rate_pct, 1),
        annual_grid_import_kwh=round(annual_grid_import_kwh, 1),
        grid_import_reduction_kwh=round(grid_import_reduction_kwh, 1),
        grid_import_reduction_pct=round(grid_import_reduction_pct, 1),
        orig_peak_kw=round(orig_peak_kw, 1),
        new_peak_kw=round(new_peak_kw, 1),
        peak_shaved_kw=round(peak_shaved_kw, 1),
        peak_reduction_pct=round(peak_reduction_pct, 1),
        orig_violations_count=orig_violations,
        new_violations_count=new_violations,
        violations_eliminated_pct=round(violations_eliminated_pct, 1)
    )

    return SolarBESSSimulationResult(
        solar_config=solar_config,
        bess_config=bess_config,
        grid_limit_kw=float(grid_limit_kw),
        target_shaving_cap_kw=float(target_cap_kw),
        dispatch_strategy=strategy,
        kpis=kpis,
        df_dispatch=df_dispatch,
        monthly_metrics=monthly_metrics,
        diagnostics_before=diag_before,
        diagnostics_after=diag_after
    )
