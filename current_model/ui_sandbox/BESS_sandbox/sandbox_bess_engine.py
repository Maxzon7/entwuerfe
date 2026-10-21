"""
========================================================================================
BESS Sandbox: Enhanced Calculation & Economics Engine (sandbox_bess_engine.py)
========================================================================================

Engine refinements for the standalone BESS sandbox:
  1. Gross vs. Net Minimum Sizing (DoD & discharge efficiency accounting).
  2. Dynamic Storage Degradation Model (Calendar age, EFC cycles, and ambient temperature).
  3. Realistic Baseline vs. BESS Financial Delta Accounting:
     - Month-by-month peak demand reduction (kW-max)
     - Contracted capacity shifts (GTV optimization)
     - Avoided grid connection upgrade CAPEX (e.g., MV transformer station)
     - Avoided recurring transformer rental fees
     - Conversion round-trip losses & mid-life cell overhaul
========================================================================================
"""

import os
import sys
from typing import Dict, Any, List, Optional, Tuple, Union
from dataclasses import dataclass, field
import numpy as np
import pandas as pd

# Path bootstrapping
CURRENT_DIR = os.path.abspath(os.path.dirname(__file__))
UI_SANDBOX_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
CURRENT_MODEL_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
WORKSPACE_DIR = os.path.abspath(os.path.join(CURRENT_MODEL_DIR, ".."))
for p in [CURRENT_DIR, UI_SANDBOX_DIR, CURRENT_MODEL_DIR, WORKSPACE_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

# Production Models & Engines
try:
    from current_model.models.bess import BESSConfig, BESSKPIs, BESSFinancialMetrics
    from current_model.models.contract import Contract
    from current_model.core.bess_engine import (
        analyze_grid_violations,
        simulate_bess_dispatch,
        compute_average_week_dispatch,
        BESSSimulationResult,
    )
    from current_model.core.bess_financial_engine import _calculate_irr
    from current_model.core.financial_engine import compute_financial_bill
except ImportError:
    from models.bess import BESSConfig, BESSKPIs, BESSFinancialMetrics
    from models.contract import Contract
    from core.bess_engine import (
        analyze_grid_violations,
        simulate_bess_dispatch,
        compute_average_week_dispatch,
        BESSSimulationResult,
    )
    from core.bess_financial_engine import _calculate_irr
    from core.financial_engine import compute_financial_bill


def simulate_sandbox_bess_dispatch(
    bess_config: BESSConfig,
    load_df: pd.DataFrame,
    grid_limit_kw: float,
    step_hours: float = 0.25,
    power_col: Optional[str] = None,
    enable_generator_assist: bool = False,
    generator_rated_kw: float = 0.0
) -> BESSSimulationResult:
    """
    Wrapper around simulate_bess_dispatch with optional Peaking Generator Assist:
      - Simulates physical BESS dispatch down to target_cap.
      - If enable_generator_assist is True and generator_rated_kw > 0:
        Dispatches generator to cover residual overload when battery is depleted.
        Populates P_Generator_kW, updates P_Grid_kW and unmet overload, and recalculates diagnostics.
    """
    sim_res = simulate_bess_dispatch(
        bess_config=bess_config,
        load_df=load_df,
        grid_limit_kw=grid_limit_kw,
        step_hours=step_hours,
        power_col=power_col
    )

    if enable_generator_assist and generator_rated_kw > 0.0:
        unmet_kw = sim_res.df_timeseries["P_Overload_Unmet_kW"].to_numpy(dtype=float)
        p_gen_kw = np.minimum(unmet_kw, float(generator_rated_kw))
        p_grid_curr = sim_res.df_timeseries["P_Grid_kW"].to_numpy(dtype=float)
        p_grid_new = np.maximum(0.0, p_grid_curr - p_gen_kw)
        p_unmet_new = np.maximum(0.0, unmet_kw - p_gen_kw)

        sim_res.df_timeseries["P_Generator_kW"] = np.round(p_gen_kw, 2)
        sim_res.df_timeseries["P_Grid_kW"] = np.round(p_grid_new, 2)
        sim_res.df_timeseries["P_Overload_Unmet_kW"] = np.round(p_unmet_new, 2)

        # Recalculate diagnostics after
        sim_res.diagnostics_after = analyze_grid_violations(
            sim_res.df_timeseries["P_Grid_kW"],
            grid_limit_kw,
            step_hours=step_hours
        )
        orig_peak = float(sim_res.diagnostics_before.get("peak_load_kw", 0.0))
        res_peak = float(sim_res.diagnostics_after.get("peak_load_kw", 0.0))
        sim_res.kpis.peak_shaved_kw = round(max(0.0, orig_peak - res_peak), 1)
    else:
        sim_res.df_timeseries["P_Generator_kW"] = 0.0

    return sim_res


@dataclass
class ExcelSizingValidationResult:
    """Reusable output of the Excel-aligned BESS sizing and feasibility diagnostic module."""
    # Physical Feasibility of a Battery-Only Solution at the given Grid Limit
    is_battery_only_physically_feasible: bool
    feasibility_status_code: str          # "FEASIBLE", "GRID_RECHARGE_BOTTLENECK", "POWER_BOTTLENECK", "CAPACITY_BOTTLENECK", "RECHARGE_POWER_BOTTLENECK"
    failure_reason_explanation: str       # Clear human-readable diagnosis
    # Minimum Required BESS Sizing for 0.0 kWh Remaining Deficit
    min_required_discharge_kw: float
    min_required_charge_kw: float
    min_required_usable_kwh: float
    min_required_gross_kwh: float
    recommended_units: int
    recommended_unit_kwh: float
    # Recharge & Multi-Day Cluster Diagnostics
    total_annual_overload_kwh: float
    total_annual_recharge_headroom_kwh: float
    worst_cluster_net_deficit_kwh: float
    worst_cluster_duration_hours: float


def calculate_excel_bess_sizing_and_diagnostics(
    load_series: Union[pd.Series, np.ndarray],
    grid_limit_kw: float,
    round_trip_efficiency_pct: float = 90.0,
    soc_min_pct: float = 10.0,
    soc_max_pct: float = 95.0,
    max_charge_kw_limit: Optional[float] = None,
    step_hours: float = 0.25,
    configured_bess: Optional[BESSConfig] = None,
    sim_result: Optional[BESSSimulationResult] = None
) -> ExcelSizingValidationResult:
    """
    Reproduces the Excel battery-sizing calculation in Python:
    computes the exact minimum required battery capacity (kWh) and power (kW)
    considering consecutive peaks, recharge headroom, charge/discharge power limits,
    round-trip efficiency, and SoC limits.
    """
    arr = np.nan_to_num(np.asarray(load_series, dtype=float), nan=0.0)

    # Compute efficiencies and usable window
    dod_frac = max(0.10, min(1.0, (soc_max_pct - soc_min_pct) / 100.0))
    rte_frac = max(0.50, min(1.0, round_trip_efficiency_pct / 100.0))
    eta_dis = float(np.sqrt(rte_frac))
    eta_chg = float(np.sqrt(rte_frac))

    # Compute raw overload and recharge headroom across the year
    overload_kw_arr = np.maximum(0.0, arr - grid_limit_kw)
    headroom_kw_arr = np.maximum(0.0, grid_limit_kw - arr)

    min_dis_kw = float(np.max(overload_kw_arr)) if len(arr) > 0 else 0.0
    total_overload_kwh = float(np.sum(overload_kw_arr) * step_hours)
    total_headroom_kwh = float(np.sum(headroom_kw_arr) * step_hours)

    # Simulate Cumulative Energy Deficit with Consecutive Peaks & Recharge Opportunities ("Infinite Battery" tracker)
    chg_cap_kw = float(max_charge_kw_limit) if (max_charge_kw_limit is not None and max_charge_kw_limit > 0) else max(min_dis_kw, grid_limit_kw)

    cum_chem_deficit_kwh = 0.0
    max_chem_deficit_kwh = 0.0
    cur_cluster_steps = 0
    worst_cluster_steps = 0

    for p_kw in arr:
        if p_kw > grid_limit_kw:
            drawn_chem_kwh = ((p_kw - grid_limit_kw) / eta_dis) * step_hours
            cum_chem_deficit_kwh += drawn_chem_kwh
            cur_cluster_steps += 1
            if cum_chem_deficit_kwh > max_chem_deficit_kwh:
                max_chem_deficit_kwh = cum_chem_deficit_kwh
                worst_cluster_steps = cur_cluster_steps
        else:
            if cum_chem_deficit_kwh > 0.0:
                avail_chg_kw = min(grid_limit_kw - p_kw, chg_cap_kw)
                recharged_chem_kwh = (avail_chg_kw * eta_chg) * step_hours
                cum_chem_deficit_kwh = max(0.0, cum_chem_deficit_kwh - recharged_chem_kwh)
                if cum_chem_deficit_kwh == 0.0:
                    cur_cluster_steps = 0
                else:
                    cur_cluster_steps += 1

    # Minimum Required Usable & Gross Capacity
    min_usable_kwh = max_chem_deficit_kwh
    min_gross_kwh = (min_usable_kwh / dod_frac) if dod_frac > 0 else 0.0
    min_chg_kw = float(min_dis_kw)

    unit_kwh = 100.0 if min_gross_kwh <= 500.0 else 250.0
    units = max(1, int(np.ceil(min_gross_kwh / unit_kwh))) if min_gross_kwh > 0 else 1

    worst_cluster_duration_hours = worst_cluster_steps * step_hours
    worst_cluster_net_deficit_kwh = max_chem_deficit_kwh * eta_dis

    # Feasibility and Bottleneck Diagnostics
    is_battery_only_physically_feasible = True
    status_code = "FEASIBLE"
    reason = "100% Feasible: Battery covers all peaks within grid limit, power ratings, and SoC boundaries (Remaining Deficit = 0.0 kWh)."

    # Check 1: Grid Recharge Bottleneck
    if (total_overload_kwh / eta_dis) > (total_headroom_kwh * eta_chg):
        is_battery_only_physically_feasible = False
        status_code = "GRID_RECHARGE_BOTTLENECK"
        reason = (
            "Grid Recharge Bottleneck: Cumulative energy above the grid limit exceeds total available "
            "recharge headroom below the grid limit (accounting for RTE losses). Even an infinite battery cannot recharge fully."
        )
    elif configured_bess is not None and sim_result is not None:
        unmet_peak_kw = float(sim_result.df_timeseries["P_Overload_Unmet_kW"].max()) if "P_Overload_Unmet_kW" in sim_result.df_timeseries.columns else 0.0
        unmet_kwh = float(sim_result.df_timeseries["P_Overload_Unmet_kW"].sum() * step_hours) if "P_Overload_Unmet_kW" in sim_result.df_timeseries.columns else 0.0

        if unmet_peak_kw <= 0.05 and unmet_kwh <= 0.05:
            status_code = "FEASIBLE"
            reason = "100% Feasible: Battery covers all peaks within grid limit, power ratings, and SoC boundaries (Remaining Deficit = 0.0 kWh)."
        elif configured_bess.max_discharge_power_kw < min_dis_kw - 0.1:
            status_code = "POWER_BOTTLENECK"
            reason = f"Discharge Power Bottleneck: Configured max discharge power ({configured_bess.max_discharge_power_kw:,.1f} kW) is lower than the maximum peak overload ({min_dis_kw:,.1f} kW)."
        elif configured_bess.capacity_kwh < min_gross_kwh - 0.5:
            status_code = "CAPACITY_BOTTLENECK"
            reason = f"Storage Capacity Depletion (Multi-Peak Cluster): Configured gross capacity ({configured_bess.capacity_kwh:,.1f} kWh) is smaller than the minimum required {min_gross_kwh:,.1f} kWh to bridge consecutive peaks and limited recharge windows."
        else:
            status_code = "RECHARGE_POWER_BOTTLENECK"
            reason = f"Recharge Power / Window Bottleneck: Battery charge power ({configured_bess.max_charge_power_kw:,.1f} kW) or restricted charging window prevented full recovery between consecutive peaks."

    return ExcelSizingValidationResult(
        is_battery_only_physically_feasible=is_battery_only_physically_feasible,
        feasibility_status_code=status_code,
        failure_reason_explanation=reason,
        min_required_discharge_kw=round(min_dis_kw, 1),
        min_required_charge_kw=round(min_chg_kw, 1),
        min_required_usable_kwh=round(min_usable_kwh, 1),
        min_required_gross_kwh=round(min_gross_kwh, 1),
        recommended_units=units,
        recommended_unit_kwh=unit_kwh,
        total_annual_overload_kwh=round(total_overload_kwh, 1),
        total_annual_recharge_headroom_kwh=round(total_headroom_kwh, 1),
        worst_cluster_net_deficit_kwh=round(worst_cluster_net_deficit_kwh, 1),
        worst_cluster_duration_hours=round(worst_cluster_duration_hours, 1)
    )


@dataclass
class DualSizingRecommendation:
    """Comparison between 100% Standalone BESS sizing and Smart Target-% BESS + Peaking Generator."""
    single_event_gross_kwh: float
    # Option A: 100% Standalone BESS (Full multi-day cumulative deficit)
    full_100pct_net_deficit_kwh: float
    full_100pct_gross_kwh: float
    full_100pct_power_kw: float
    full_100pct_units: int
    full_100pct_unit_kwh: float
    # Option B: Smart Partial BESS (e.g. 90% episode coverage) + Backup Generator
    target_coverage_pct: float
    smart_net_deficit_kwh: float
    smart_gross_kwh: float
    smart_bess_power_kw: float
    smart_units: int
    smart_unit_kwh: float
    # Peaking Generator required to cover the remaining (100 - X)% extreme spikes
    required_generator_kw: float
    estimated_gen_energy_kwh: float
    estimated_gen_hours: float
    violation_hours_pct_of_year: float

    @property
    def option_a_gross_kwh(self) -> float:
        return self.full_100pct_gross_kwh

    @property
    def option_a_unit_count(self) -> int:
        return self.full_100pct_units

    @property
    def option_b_gross_kwh(self) -> float:
        return self.smart_gross_kwh

    @property
    def option_b_unit_count(self) -> int:
        return self.smart_units

    @property
    def inverter_power_kw(self) -> float:
        return self.full_100pct_power_kw

    @property
    def capacity_reduction_pct(self) -> float:
        if self.full_100pct_gross_kwh <= 0.0:
            return 0.0
        return max(0.0, (1.0 - (self.smart_gross_kwh / self.full_100pct_gross_kwh)) * 100.0)


def compute_dual_bess_sizing(
    load_series: Union[pd.Series, np.ndarray, List[float]],
    grid_limit_kw: float,
    target_coverage_pct: float = 90.0,
    round_trip_efficiency_pct: float = 90.0,
    soc_min_pct: float = 10.0,
    soc_max_pct: float = 95.0,
    unit_capacity_kwh: Optional[float] = None,
    step_hours: float = 0.25,
    **kwargs: Any
) -> DualSizingRecommendation:
    """
    Computes honest dual sizing by simulating an Infinite Ghost Battery across all 35,040 steps:
      - Tracks real multi-day cumulative chemical deficits under physical grid headroom recharge limits.
      - Option A: 100% Standalone All-In BESS (covers all multi-day congestion clusters).
      - Option B: Smart Target-% BESS (e.g. 90th percentile) + Peaking Generator for extreme tail events.
    """
    # Support target_percentile alias
    if "target_percentile" in kwargs:
        target_coverage_pct = float(kwargs["target_percentile"])
    arr = np.asarray(load_series, dtype=float)
    arr = np.nan_to_num(arr, nan=0.0)

    dod_frac = max(0.20, min(1.0, (soc_max_pct - soc_min_pct) / 100.0))
    rte_frac = max(0.50, min(1.0, round_trip_efficiency_pct / 100.0))
    eta = np.sqrt(rte_frac)

    overload_arr = np.maximum(0.0, arr - grid_limit_kw)
    overload_peak_kw = float(np.max(overload_arr)) if len(overload_arr) > 0 else 0.0
    violation_steps = int(np.sum(overload_arr > 0))
    violation_hours_pct = (violation_steps / max(1, len(arr))) * 100.0

    if overload_peak_kw <= 0.0 or len(arr) == 0:
        return DualSizingRecommendation(
            single_event_gross_kwh=0.0,
            full_100pct_net_deficit_kwh=0.0,
            full_100pct_gross_kwh=50.0,
            full_100pct_power_kw=50.0,
            full_100pct_units=1,
            full_100pct_unit_kwh=50.0,
            target_coverage_pct=float(target_coverage_pct),
            smart_net_deficit_kwh=0.0,
            smart_gross_kwh=50.0,
            smart_bess_power_kw=50.0,
            smart_units=1,
            smart_unit_kwh=50.0,
            required_generator_kw=0.0,
            estimated_gen_energy_kwh=0.0,
            estimated_gen_hours=0.0,
            violation_hours_pct_of_year=0.0
        )

    # Infinite Ghost Battery simulation with physical headroom recharge
    virtual_deficit_kwh = 0.0
    current_episode_max = 0.0
    episode_peak_deficits: List[float] = []

    for p_kw in arr:
        if p_kw > grid_limit_kw:
            overload_kw = p_kw - grid_limit_kw
            virtual_deficit_kwh += (overload_kw / eta) * step_hours
            current_episode_max = max(current_episode_max, virtual_deficit_kwh)
        else:
            if virtual_deficit_kwh > 0.0:
                headroom_kw = grid_limit_kw - p_kw
                recharged_kwh = (headroom_kw * eta) * step_hours
                virtual_deficit_kwh = max(0.0, virtual_deficit_kwh - recharged_kwh)
                if virtual_deficit_kwh <= 0.0 and current_episode_max > 0.0:
                    episode_peak_deficits.append(current_episode_max)
                    current_episode_max = 0.0

    if current_episode_max > 0.0:
        episode_peak_deficits.append(current_episode_max)

    if not episode_peak_deficits:
        episode_peak_deficits = [0.0]

    # Single-event naive
    single_event_gross = (float(np.max(overload_arr * step_hours)) / (dod_frac * eta)) * 1.05

    # Option A: 100% All-In Standalone BESS
    max_chem_deficit = float(np.max(episode_peak_deficits))
    full_net_deficit = max_chem_deficit * eta
    full_gross_raw = (max_chem_deficit / dod_frac) * 1.05
    full_power_kw = float(np.ceil(overload_peak_kw / 10.0) * 10.0)

    if unit_capacity_kwh is not None and unit_capacity_kwh > 0.0:
        full_unit_cap = float(unit_capacity_kwh)
    else:
        full_unit_cap = 250.0 if full_gross_raw > 450.0 else (100.0 if full_gross_raw > 120.0 else 50.0)
    full_units = max(1, int(np.ceil(full_gross_raw / full_unit_cap)))
    full_gross_kwh = float(full_units * full_unit_cap)

    # Option B: Smart Target-% BESS + Peaking Generator
    pct = max(50.0, min(99.0, float(target_coverage_pct)))
    smart_chem_deficit = float(np.percentile(episode_peak_deficits, pct))
    smart_net_deficit = smart_chem_deficit * eta
    smart_gross_raw = (smart_chem_deficit / dod_frac) * 1.05
    smart_power_kw = float(np.ceil(overload_peak_kw / 10.0) * 10.0)

    if unit_capacity_kwh is not None and unit_capacity_kwh > 0.0:
        smart_unit_cap = float(unit_capacity_kwh)
    else:
        smart_unit_cap = 250.0 if smart_gross_raw > 450.0 else (100.0 if smart_gross_raw > 120.0 else 50.0)
    smart_units = max(1, int(np.ceil(smart_gross_raw / smart_unit_cap)))
    smart_gross_kwh = float(smart_units * smart_unit_cap)

    # Peaking Generator sizing
    req_gen_kw = float(np.ceil(overload_peak_kw / 10.0) * 10.0)
    unserved_chem = [max(0.0, ep - smart_chem_deficit) for ep in episode_peak_deficits]
    est_gen_kwh = float(sum(unserved_chem) * eta)
    est_gen_hours = round(est_gen_kwh / max(10.0, req_gen_kw * 0.5), 1)

    return DualSizingRecommendation(
        single_event_gross_kwh=round(single_event_gross, 1),
        full_100pct_net_deficit_kwh=round(full_net_deficit, 1),
        full_100pct_gross_kwh=round(full_gross_kwh, 1),
        full_100pct_power_kw=round(full_power_kw, 1),
        full_100pct_units=full_units,
        full_100pct_unit_kwh=full_unit_cap,
        target_coverage_pct=pct,
        smart_net_deficit_kwh=round(smart_net_deficit, 1),
        smart_gross_kwh=round(smart_gross_kwh, 1),
        smart_bess_power_kw=round(smart_power_kw, 1),
        smart_units=smart_units,
        smart_unit_kwh=smart_unit_cap,
        required_generator_kw=round(req_gen_kw, 1),
        estimated_gen_energy_kwh=round(est_gen_kwh, 1),
        estimated_gen_hours=est_gen_hours,
        violation_hours_pct_of_year=round(violation_hours_pct, 2)
    )


@dataclass
class GrossSizingRecommendation:
    """Gross battery nameplate sizing recommendations based on load diagnostics."""
    net_deficit_energy_kwh: float
    overload_peak_kw: float
    usable_dod_pct: float
    one_way_efficiency_pct: float
    min_gross_capacity_kwh: float
    min_continuous_power_kw: float
    recommended_unit_count: int
    recommended_unit_capacity_kwh: float
    recommended_total_capacity_kwh: float
    recommended_inverter_power_kw: float
    c_rate_discharge: float
    description: str


def compute_gross_minimum_bess_sizing(
    diagnostics: Dict[str, Any],
    round_trip_efficiency_pct: float = 90.0,
    soc_min_pct: float = 10.0,
    soc_max_pct: float = 95.0,
    safety_margin_pct: float = 10.0
) -> GrossSizingRecommendation:
    """
    Computes true gross battery nameplate capacity accounting for:
      - Usable DoD (SoC_max - SoC_min)
      - One-way discharge inverter efficiency (sqrt(RTE))
      - Worst continuous overload event energy
      - Peak overload power with safety margin
    """
    net_kwh = float(diagnostics.get("worst_event_energy_kwh", 0.0))
    peak_overload_kw = float(diagnostics.get("overload_peak_kw", 0.0))

    if net_kwh <= 0.0 or peak_overload_kw <= 0.0:
        return GrossSizingRecommendation(
            net_deficit_energy_kwh=0.0,
            overload_peak_kw=0.0,
            usable_dod_pct=max(10.0, soc_max_pct - soc_min_pct),
            one_way_efficiency_pct=np.sqrt(round_trip_efficiency_pct / 100.0) * 100.0,
            min_gross_capacity_kwh=0.0,
            min_continuous_power_kw=0.0,
            recommended_unit_count=1,
            recommended_unit_capacity_kwh=50.0,
            recommended_total_capacity_kwh=50.0,
            recommended_inverter_power_kw=50.0,
            c_rate_discharge=1.0,
            description="No grid overloads detected. Nominal benchmark storage setup."
        )

    dod_frac = max(0.20, min(1.0, (soc_max_pct - soc_min_pct) / 100.0))
    rte_frac = max(0.50, min(1.0, round_trip_efficiency_pct / 100.0))
    eta_dis = np.sqrt(rte_frac)

    # True Gross Energy: E_nom = E_net / (DoD * eta_dis)
    raw_gross_kwh = net_kwh / (dod_frac * eta_dis)
    margin_factor = 1.0 + (safety_margin_pct / 100.0)
    buffered_gross_kwh = raw_gross_kwh * margin_factor

    # Inverter Power: deliver peak overload with safety margin
    min_power_kw = peak_overload_kw
    buffered_power_kw = min_power_kw * margin_factor

    # Modular unit packaging (standard 50 kWh, 100 kWh, or 250 kWh modular blocks)
    if buffered_gross_kwh <= 120.0:
        unit_cap = 50.0
    elif buffered_gross_kwh <= 450.0:
        unit_cap = 100.0
    else:
        unit_cap = 250.0

    unit_count = max(1, int(np.ceil(buffered_gross_kwh / unit_cap)))
    rec_total_kwh = float(unit_count * unit_cap)
    rec_inverter_kw = float(np.ceil(buffered_power_kw / 10.0) * 10.0)

    c_rate = round(rec_inverter_kw / max(1.0, rec_total_kwh), 2)

    desc = (
        f"Requires at least {buffered_gross_kwh:.1f} kWh gross nameplate capacity and "
        f"{buffered_power_kw:.1f} kW continuous power to eliminate worst-case "
        f"{net_kwh:.1f} kWh deficit across {diagnostics.get('worst_event_duration_hours', 0.0):.2f} hours."
    )

    return GrossSizingRecommendation(
        net_deficit_energy_kwh=round(net_kwh, 1),
        overload_peak_kw=round(peak_overload_kw, 1),
        usable_dod_pct=round(dod_frac * 100.0, 1),
        one_way_efficiency_pct=round(eta_dis * 100.0, 1),
        min_gross_capacity_kwh=round(buffered_gross_kwh, 1),
        min_continuous_power_kw=round(buffered_power_kw, 1),
        recommended_unit_count=unit_count,
        recommended_unit_capacity_kwh=unit_cap,
        recommended_total_capacity_kwh=rec_total_kwh,
        recommended_inverter_power_kw=rec_inverter_kw,
        c_rate_discharge=c_rate,
        description=desc
    )


def compute_bess_degradation_profile(
    analysis_horizon_years: int = 15,
    equivalent_full_cycles_per_year: float = 250.0,
    ambient_temperature_c: float = 25.0,
    cell_replacement_year: int = 10,
    base_calendar_fade_pct_yr: float = 1.0,
    cycle_fade_per_100_efc_pct: float = 0.04
) -> List[float]:
    """
    Computes multi-year usable battery capacity retention factors (0.0 to 1.0).
    Accounts for calendar aging, cycle throughput wear, and temperature stress.
    Restores capacity to 95% at cell replacement year.
    """
    factors = []
    
    # Temperature penalty: +0.05% per degree above 25°C
    temp_penalty_pct = max(0.0, ambient_temperature_c - 25.0) * 0.05
    annual_cycle_fade_pct = (equivalent_full_cycles_per_year / 100.0) * cycle_fade_per_100_efc_pct
    annual_total_fade_pct = base_calendar_fade_pct_yr + annual_cycle_fade_pct + temp_penalty_pct
    annual_fade_frac = annual_total_fade_pct / 100.0

    for y in range(1, analysis_horizon_years + 1):
        if y <= cell_replacement_year:
            factor = max(0.60, 1.0 - (y - 1) * annual_fade_frac)
        else:
            # Restored to 95% upon cell replacement
            years_post_refresh = y - cell_replacement_year - 1
            factor = max(0.65, 0.95 - years_post_refresh * annual_fade_frac)
        factors.append(round(factor, 4))

    return factors


def evaluate_sandbox_bess_economics(
    bess_config: BESSConfig,
    sim_result: BESSSimulationResult,
    contract_baseline: Contract,
    contract_bess: Contract,
    avoided_grid_upgrade_capex: float = 0.0,
    avoided_monthly_transformer_rent: float = 0.0,
    analysis_horizon_years: int = 15,
    discount_rate_pct: float = 5.0,
    electricity_price_inflation_pct: float = 2.0,
    ambient_temperature_c: float = 25.0,
    step_hours: float = 0.25,
    generator_capex: float = 0.0,
    generator_monthly_rent: float = 0.0,
    diesel_price_per_liter: float = 1.45,
    fuel_liters_per_kwh: float = 0.25
) -> BESSFinancialMetrics:
    """
    Evaluates comprehensive life-cycle economics comparing Status Quo / Grid Upgrade vs. With-BESS.
    Accounts for:
      - 12-month peak demand reductions (kW-max)
      - Contracted capacity GTV differences
      - Avoided one-time grid upgrade CAPEX (e.g. station upgrade)
      - Avoided monthly transformer rent
      - Battery round-trip conversion losses
      - Optional Peaking Generator purchase/rental & fuel costs
      - Dynamic multi-year degradation & Year-10 cell overhaul
    """
    # 1. Hardware CAPEX & Initial Investment
    gross_bess_capex = float(bess_config.total_capex)
    total_hardware_capex = gross_bess_capex + float(generator_capex)
    cap_kwh = max(1.0, float(bess_config.capacity_kwh))
    
    # Net Initial Investment = (BESS Turnkey CAPEX + Generator CAPEX) minus avoided grid upgrade CAPEX
    net_initial_investment = max(0.0, total_hardware_capex - avoided_grid_upgrade_capex)

    # 2. Year 1 Baseline vs. With-BESS Bills
    df_ts = sim_result.df_timeseries
    p_load = df_ts["P_Load_kW"].to_numpy(dtype=float)
    p_grid = df_ts["P_Grid_kW"].to_numpy(dtype=float)
    p_dis = df_ts["P_BESS_Discharge_kW"].to_numpy(dtype=float)

    df_base = pd.DataFrame({"Total_Demand_kW": p_load})
    if "timestamp" in df_ts.columns:
        df_base["timestamp"] = df_ts["timestamp"]

    df_bess = pd.DataFrame({"Total_Demand_kW": p_grid})
    if "timestamp" in df_ts.columns:
        df_bess["timestamp"] = df_ts["timestamp"]

    bill_base = compute_financial_bill(df_base, contract_baseline, step_hours=step_hours)
    bill_bess = compute_financial_bill(df_bess, contract_bess, step_hours=step_hours)

    dur = getattr(bill_base, "duration_days", 365.0) or 365.0
    ann_factor = (365.0 / dur) if (0.01 < dur < 360.0) else 1.0

    sq_demand_cost = float(bill_base.capacity_cost_period * ann_factor)
    wb_demand_cost = float(bill_bess.capacity_cost_period * ann_factor)
    demand_savings = max(0.0, sq_demand_cost - wb_demand_cost)

    sq_energy_cost = float(bill_base.energy_cost_period * ann_factor)
    wb_energy_cost = float(bill_bess.energy_cost_period * ann_factor)
    energy_savings = float(sq_energy_cost - wb_energy_cost)

    sq_penalty_cost = float(bill_base.penalty_cost_period * ann_factor)
    wb_penalty_cost = float(bill_bess.penalty_cost_period * ann_factor)
    penalty_savings = max(0.0, sq_penalty_cost - wb_penalty_cost)

    sq_base_bill = float(bill_base.total_gross_period * ann_factor)
    wb_base_bill = float(bill_bess.total_gross_period * ann_factor)

    # Add avoided recurring transformer rental to baseline cost
    annual_transformer_rent = float(avoided_monthly_transformer_rent * 12.0)
    sq_total_annual_cost = sq_base_bill + annual_transformer_rent

    # Efficiency Losses Cost
    annual_discharged_kwh = float(np.sum(p_dis) * step_hours) * ann_factor
    rte = max(0.50, min(1.0, float(bess_config.round_trip_efficiency_pct) / 100.0))
    annual_loss_kwh = annual_discharged_kwh * ((1.0 / rte) - 1.0)
    avg_energy_rate = float(getattr(contract_bess, "default_energy_rate", 0.20) or 0.20)
    annual_loss_cost = float(annual_loss_kwh * avg_energy_rate)

    # Generator OPEX (fuel and recurring rental)
    if "P_Generator_kW" in df_ts.columns:
        gen_annual_kwh = float(np.sum(df_ts["P_Generator_kW"].to_numpy(dtype=float)) * step_hours) * ann_factor
    else:
        gen_annual_kwh = 0.0
    gen_annual_fuel_cost = round(gen_annual_kwh * fuel_liters_per_kwh * diesel_price_per_liter, 2)
    gen_annual_rent_cost = round(float(generator_monthly_rent * 12.0), 2)
    gen_total_annual_opex = gen_annual_fuel_cost + gen_annual_rent_cost

    # BESS O&M + Generator OPEX
    annual_fixed_om = round(gross_bess_capex * (bess_config.annual_om_pct / 100.0), 2)
    annual_opex_y1 = round(annual_fixed_om + annual_loss_cost + gen_total_annual_opex, 2)

    # Annual Gross & Net Savings
    annual_bill_savings = max(0.0, sq_base_bill - wb_base_bill)
    annual_gross_savings = annual_bill_savings + annual_transformer_rent
    annual_net_savings_y1 = round(annual_gross_savings - annual_opex_y1, 2)

    # 3. Dynamic Degradation Vector
    efc = float(sim_result.kpis.equivalent_full_cycles)
    deg_factors = compute_bess_degradation_profile(
        analysis_horizon_years=analysis_horizon_years,
        equivalent_full_cycles_per_year=efc,
        ambient_temperature_c=ambient_temperature_c,
        cell_replacement_year=bess_config.cell_replacement_year,
        base_calendar_fade_pct_yr=1.0,
        cycle_fade_per_100_efc_pct=0.04
    )

    # 4. Multi-Year Cash Flow & TCO Projection
    r = discount_rate_pct / 100.0
    infl = electricity_price_inflation_pct / 100.0
    
    cash_flow_table: List[Dict[str, Any]] = []
    cumulative_cash_flow: List[float] = [-net_initial_investment]
    cumulative_status_quo: List[float] = [0.0]
    cumulative_with_bess: List[float] = [net_initial_investment]
    annual_sq_costs: List[float] = []
    annual_wb_costs: List[float] = []

    running_sq = 0.0
    running_wb = net_initial_investment
    cum_cf = -net_initial_investment
    cum_disc_cf = -net_initial_investment
    npv = -net_initial_investment
    raw_cash_flows: List[float] = [-net_initial_investment]

    payback_years: Optional[float] = None
    disc_payback_years: Optional[float] = None
    disc_costs_sum = net_initial_investment
    disc_energy_sum = 0.0

    cell_rep_year = bess_config.cell_replacement_year
    cell_rep_cost = round(gross_bess_capex * 0.65 * (bess_config.cell_replacement_cost_pct / 100.0), 2)

    for y in range(1, analysis_horizon_years + 1):
        deg_factor = deg_factors[y - 1]
        price_factor = (1.0 + infl) ** (y - 1)

        y_sq_cost = sq_total_annual_cost * price_factor
        y_gross_savings = annual_gross_savings * deg_factor * price_factor
        y_wb_bill = (wb_base_bill * price_factor)

        y_gen_opex = gen_annual_rent_cost + (gen_annual_fuel_cost * price_factor)
        y_opex = (annual_fixed_om * ((1.0 + infl * 0.8) ** (y - 1))) + (annual_loss_cost * price_factor) + y_gen_opex
        y_extra_capex = cell_rep_cost if (y == cell_rep_year) else 0.0

        y_total_bess_cost = y_wb_bill + y_opex + y_extra_capex
        y_net_cashflow = y_gross_savings - y_opex - y_extra_capex

        raw_cash_flows.append(y_net_cashflow)

        discount_factor = 1.0 / ((1.0 + r) ** y)
        y_disc_cashflow = y_net_cashflow * discount_factor
        npv += y_disc_cashflow

        disc_costs_sum += (y_opex + y_extra_capex) * discount_factor
        disc_energy_sum += (annual_discharged_kwh * deg_factor) * discount_factor

        # Payback tracking
        prev_cum_cf = cum_cf
        cum_cf += y_net_cashflow
        cumulative_cash_flow.append(round(cum_cf, 2))

        if payback_years is None and cum_cf >= 0:
            if y_net_cashflow > 0:
                fraction = abs(prev_cum_cf) / y_net_cashflow
                payback_years = round((y - 1) + fraction, 2)
            else:
                payback_years = float(y)

        prev_cum_disc = cum_disc_cf
        cum_disc_cf += y_disc_cashflow
        if disc_payback_years is None and cum_disc_cf >= 0:
            if y_disc_cashflow > 0:
                fraction = abs(prev_cum_disc) / y_disc_cashflow
                disc_payback_years = round((y - 1) + fraction, 2)
            else:
                disc_payback_years = float(y)

        running_sq += y_sq_cost
        running_wb += y_total_bess_cost
        cumulative_status_quo.append(round(running_sq, 2))
        cumulative_with_bess.append(round(running_wb, 2))
        annual_sq_costs.append(round(y_sq_cost, 2))
        annual_wb_costs.append(round(y_total_bess_cost, 2))

        cash_flow_table.append({
            "year": y,
            "status_quo_bill": round(y_sq_cost, 2),
            "with_bess_bill": round(y_wb_bill, 2),
            "gross_savings": round(y_gross_savings, 2),
            "bess_opex": round(y_opex, 2),
            "cell_replacement": round(y_extra_capex, 2),
            "net_cash_flow": round(y_net_cashflow, 2),
            "cumulative_cash_flow": round(cum_cf, 2),
            "discounted_cash_flow": round(y_disc_cashflow, 2),
            "cumulative_npv": round(npv, 2)
        })

    lcos = round(disc_costs_sum / max(1.0, disc_energy_sum), 3) if disc_energy_sum > 0 else 0.0
    irr_pct = _calculate_irr(raw_cash_flows)
    total_lifetime_net_cf = sum(row["net_cash_flow"] for row in cash_flow_table)
    roi_pct = round((total_lifetime_net_cf / max(1.0, net_initial_investment)) * 100.0, 1) if net_initial_investment > 0 else 999.0

    return BESSFinancialMetrics(
        is_configured=True,
        total_capex=round(net_initial_investment, 2),
        capex_per_kwh=round(net_initial_investment / cap_kwh, 2),
        annual_opex_year1=annual_opex_y1,
        annual_fixed_om=annual_fixed_om,
        annual_loss_kwh=round(annual_loss_kwh, 1),
        annual_loss_cost=round(annual_loss_cost, 2),
        annual_status_quo_demand_cost=round(sq_demand_cost, 2),
        annual_with_bess_demand_cost=round(wb_demand_cost, 2),
        annual_status_quo_energy_cost=round(sq_energy_cost, 2),
        annual_with_bess_energy_cost=round(wb_energy_cost, 2),
        annual_status_quo_penalty_cost=round(sq_penalty_cost, 2),
        annual_with_bess_penalty_cost=round(wb_penalty_cost, 2),
        annual_status_quo_total_bill=round(sq_total_annual_cost, 2),
        annual_with_bess_total_bill=round(wb_base_bill, 2),
        annual_demand_charge_savings=round(demand_savings, 2),
        annual_penalty_savings=round(penalty_savings, 2),
        annual_energy_savings=round(energy_savings, 2),
        annual_gross_savings=round(annual_gross_savings, 2),
        annual_net_savings_year1=round(annual_net_savings_y1, 2),
        simple_payback_years=payback_years,
        discounted_payback_years=disc_payback_years,
        net_present_value=round(npv, 2),
        internal_rate_of_return_pct=irr_pct,
        levelized_cost_of_storage_eur_kwh=lcos,
        return_on_investment_pct=roi_pct,
        cash_flow_table=cash_flow_table,
        cumulative_cash_flow=cumulative_cash_flow,
        cumulative_status_quo=cumulative_status_quo,
        cumulative_with_bess=cumulative_with_bess,
        annual_status_quo_costs=annual_sq_costs,
        annual_with_bess_costs=annual_wb_costs
    )


# ======================================================================================
# Physics-First Additions (Step 1):
#   1. Pure exceedance energy summary (0% battery assumptions)
#   2. Simultaneous multivariate bottleneck audit (replaces if/elif short-circuiting)
#   3. Precomputed Pareto coverage tradeoff curve (10 support points)
# ======================================================================================

PARETO_DEFAULT_TARGETS: Tuple[float, ...] = (50.0, 60.0, 70.0, 75.0, 80.0, 85.0, 90.0, 95.0, 98.0, 100.0)


def compute_exceedance_energy_summary(
    load_series: Union[pd.Series, np.ndarray],
    grid_limit_kw: float,
    step_hours: float = 0.25
) -> Dict[str, float]:
    """
    Pure physical exceedance statistics of a load profile against a grid limit.
    Contains no battery efficiencies, DoD, or SoC assumptions.
    """
    arr = np.nan_to_num(np.asarray(load_series, dtype=float), nan=0.0)
    if arr.size == 0:
        return {
            "total_exceedance_kwh": 0.0, "total_headroom_kwh": 0.0, "max_overload_kw": 0.0,
            "peak_load_kw": 0.0, "overload_intervals": 0, "overload_hours": 0.0,
            "annual_consumption_kwh": 0.0, "exceedance_share_pct": 0.0, "overload_share_pct": 0.0,
        }
    overload = np.maximum(0.0, arr - grid_limit_kw)
    headroom = np.maximum(0.0, grid_limit_kw - arr)
    consumption_kwh = float(np.sum(np.maximum(arr, 0.0)) * step_hours)
    exceedance_kwh = float(np.sum(overload) * step_hours)
    n_over = int(np.count_nonzero(overload > 0.0))
    return {
        "total_exceedance_kwh": exceedance_kwh,
        "total_headroom_kwh": float(np.sum(headroom) * step_hours),
        "max_overload_kw": float(np.max(overload)),
        "peak_load_kw": float(np.max(arr)),
        "overload_intervals": n_over,
        "overload_hours": float(n_over * step_hours),
        "annual_consumption_kwh": consumption_kwh,
        "exceedance_share_pct": (exceedance_kwh / consumption_kwh * 100.0) if consumption_kwh > 0 else 0.0,
        "overload_share_pct": (n_over / arr.size * 100.0),
    }


def _efficiency_split(round_trip_efficiency_pct: float) -> Tuple[float, float]:
    """Splits round-trip efficiency symmetrically into discharge and charge efficiency."""
    rte = max(0.50, min(1.0, float(round_trip_efficiency_pct) / 100.0))
    eta = float(np.sqrt(rte))
    return eta, eta


def _usable_window_fraction(soc_min_pct: float, soc_max_pct: float) -> float:
    """Usable SoC window as a fraction of gross nameplate (floored at 10%)."""
    return max(0.10, min(1.0, (float(soc_max_pct) - float(soc_min_pct)) / 100.0))


def _cluster_deficit_tracker(
    load_list: List[float],
    grid_limit_kw: float,
    eta_dis: float,
    eta_chg: float,
    dis_cap_kw: float,
    chg_cap_kw: float,
    step_hours: float
) -> Tuple[float, float, float]:
    """
    "Infinite battery" tracker across consecutive peaks and recharge windows.

    Discharge is capped at dis_cap_kw (battery serves the bottom slice of each overload
    from the grid line upwards), recharge is limited by grid headroom and chg_cap_kw.

    Returns:
        (max_chemical_deficit_kwh, worst_cluster_hours, served_exceedance_kwh)
    """
    cum = 0.0
    max_cum = 0.0
    cur_steps = 0
    worst_steps = 0
    served = 0.0
    for p in load_list:
        if p > grid_limit_kw:
            serve_kw = p - grid_limit_kw
            if serve_kw > dis_cap_kw:
                serve_kw = dis_cap_kw
            if serve_kw > 0.0:
                cum += (serve_kw / eta_dis) * step_hours
                served += serve_kw * step_hours
            cur_steps += 1
            if cum > max_cum:
                max_cum = cum
                worst_steps = cur_steps
        elif cum > 0.0:
            avail = grid_limit_kw - p
            if avail > chg_cap_kw:
                avail = chg_cap_kw
            cum -= avail * eta_chg * step_hours
            if cum <= 0.0:
                cum = 0.0
                cur_steps = 0
            else:
                cur_steps += 1
    return max_cum, worst_steps * step_hours, served


@dataclass
class BottleneckCheckItem:
    """Single physical constraint check of the simultaneous bottleneck audit."""
    key: str
    name: str
    passed: bool
    configured_value: float
    required_value: float
    unit: str
    description: str

    @property
    def margin_value(self) -> float:
        return float(self.configured_value - self.required_value)

    @property
    def margin_label(self) -> str:
        m = self.margin_value
        sign = "+" if m >= 0 else "-"
        return f"{sign}{abs(m):,.1f} {self.unit}"


@dataclass
class BottleneckAuditResult:
    """Result of evaluating all physical bottlenecks simultaneously."""
    checks: List[BottleneckCheckItem]
    all_passed: bool
    failed_count: int
    required_gross_kwh_ideal_recharge: float
    required_gross_kwh_configured_recharge: float
    simulated_remaining_deficit_kwh: Optional[float] = None
    simulated_peak_deficit_kw: Optional[float] = None


def evaluate_comprehensive_bottlenecks(
    load_series: Union[pd.Series, np.ndarray],
    grid_limit_kw: float,
    bess_config: BESSConfig,
    step_hours: float = 0.25,
    sim_result: Optional[BESSSimulationResult] = None
) -> BottleneckAuditResult:
    """
    Evaluates all 4 physical constraint criteria simultaneously (each in isolation):
      1. Grid Recharge Headroom: annual headroom below the limit can replenish annual exceedance.
      2. Inverter Discharge Power: max discharge power >= highest overload.
      3. Storage Capacity (Multi-Peak Clusters): gross capacity >= worst cluster deficit (ideal recharge).
      4. Recharge Inverter Power: configured charge power recovers the buffer between peaks.
    """
    arr = np.nan_to_num(np.asarray(load_series, dtype=float), nan=0.0)
    load_list = arr.tolist()
    eta_dis, eta_chg = _efficiency_split(bess_config.round_trip_efficiency_pct)
    dod = _usable_window_fraction(bess_config.soc_min_pct, bess_config.soc_max_pct)
    cap_kwh = float(bess_config.capacity_kwh)
    p_dis = float(bess_config.max_discharge_power_kw)
    p_chg = float(bess_config.max_charge_power_kw)
    inf = float("inf")

    summary = compute_exceedance_energy_summary(arr, grid_limit_kw, step_hours)
    max_ov = summary["max_overload_kw"]

    # Criterion 1: Grid Recharge Headroom (pure grid physics)
    req_recharge = summary["total_exceedance_kwh"] / eta_dis
    avail_recharge = summary["total_headroom_kwh"] * eta_chg
    c1 = BottleneckCheckItem(
        key="grid_headroom",
        name="Grid Recharge Headroom",
        passed=avail_recharge >= req_recharge - 0.05,
        configured_value=avail_recharge,
        required_value=req_recharge,
        unit="kWh/yr",
        description="Annual recharge energy available below the grid limit vs. energy the battery must deliver (incl. RTE losses)."
    )

    # Criterion 2: Inverter Discharge Power
    c2 = BottleneckCheckItem(
        key="discharge_power",
        name="Inverter Discharge Power",
        passed=p_dis >= max_ov - 0.1,
        configured_value=p_dis,
        required_value=max_ov,
        unit="kW",
        description="Configured discharge power vs. the highest 15-minute overload above the grid limit."
    )

    # Criterion 3: Storage Capacity across Multi-Peak Clusters (ideal recharge)
    e_ideal, _, _ = _cluster_deficit_tracker(load_list, grid_limit_kw, eta_dis, eta_chg, inf, inf, step_hours)
    gross_ideal = e_ideal / dod
    c3 = BottleneckCheckItem(
        key="storage_capacity",
        name="Storage Capacity (Multi-Peak Clusters)",
        passed=cap_kwh >= gross_ideal - 0.5,
        configured_value=cap_kwh,
        required_value=gross_ideal,
        unit="kWh",
        description="Gross capacity vs. the worst consecutive-peak deficit, assuming unrestricted recharge below the grid limit."
    )

    # Criterion 4: Recharge Inverter Power (between consecutive peaks)
    e_cfg, _, _ = _cluster_deficit_tracker(load_list, grid_limit_kw, eta_dis, eta_chg, inf, p_chg, step_hours)
    gross_cfg = e_cfg / dod
    target_gross = max(cap_kwh, gross_ideal)
    c4_passed = gross_cfg <= target_gross + 0.5
    req_chg_kw = p_chg
    if not c4_passed:
        hi = float(np.max(np.maximum(0.0, grid_limit_kw - arr))) if arr.size else p_chg
        lo = p_chg
        hi = max(hi, lo)
        for _ in range(14):
            mid = 0.5 * (lo + hi)
            e_mid, _, _ = _cluster_deficit_tracker(load_list, grid_limit_kw, eta_dis, eta_chg, inf, mid, step_hours)
            if e_mid / dod <= target_gross + 0.5:
                hi = mid
            else:
                lo = mid
        req_chg_kw = hi
    c4 = BottleneckCheckItem(
        key="recharge_power",
        name="Recharge Inverter Power",
        passed=c4_passed,
        configured_value=p_chg,
        required_value=req_chg_kw,
        unit="kW",
        description="Configured charge power vs. the minimum needed to refill the buffer in the short lulls between consecutive peaks."
    )

    checks = [c2, c3, c4, c1]
    failed = sum(1 for c in checks if not c.passed)

    sim_kwh: Optional[float] = None
    sim_kw: Optional[float] = None
    if sim_result is not None and "P_Overload_Unmet_kW" in sim_result.df_timeseries.columns:
        unmet = sim_result.df_timeseries["P_Overload_Unmet_kW"].to_numpy(dtype=float)
        sim_kwh = float(np.sum(unmet) * step_hours)
        sim_kw = float(np.max(unmet)) if unmet.size else 0.0

    return BottleneckAuditResult(
        checks=checks,
        all_passed=failed == 0,
        failed_count=failed,
        required_gross_kwh_ideal_recharge=round(gross_ideal, 1),
        required_gross_kwh_configured_recharge=round(gross_cfg, 1),
        simulated_remaining_deficit_kwh=sim_kwh,
        simulated_peak_deficit_kw=sim_kw,
    )


@dataclass
class ParetoTradeoffResult:
    """Required battery size vs. coverage of annual exceedance energy (support points)."""
    coverage_pct: List[float]
    required_power_kw: List[float]
    required_usable_kwh: List[float]
    required_gross_kwh: List[float]
    residual_deficit_kwh: List[float]
    residual_peak_kw: List[float]
    capacity_savings_pct: List[float]
    total_exceedance_kwh: float
    max_overload_kw: float

    @property
    def has_exceedance(self) -> bool:
        return self.total_exceedance_kwh > 0.05

    def interpolate(self, coverage_pct: float) -> Dict[str, float]:
        """Linear interpolation between support points for an arbitrary coverage target."""
        x = np.asarray(self.coverage_pct, dtype=float)
        c = float(np.clip(coverage_pct, x[0], x[-1]))
        gross = float(np.interp(c, x, self.required_gross_kwh))
        gross_100 = float(self.required_gross_kwh[-1])
        return {
            "coverage_pct": c,
            "power_kw": float(np.interp(c, x, self.required_power_kw)),
            "usable_kwh": float(np.interp(c, x, self.required_usable_kwh)),
            "gross_kwh": gross,
            "residual_deficit_kwh": float(np.interp(c, x, self.residual_deficit_kwh)),
            "residual_peak_kw": float(np.interp(c, x, self.residual_peak_kw)),
            "capacity_savings_pct": (1.0 - gross / gross_100) * 100.0 if gross_100 > 0 else 0.0,
        }


def compute_pareto_coverage_curve(
    load_series: Union[pd.Series, np.ndarray],
    grid_limit_kw: float,
    round_trip_efficiency_pct: float = 90.0,
    soc_min_pct: float = 10.0,
    soc_max_pct: float = 95.0,
    step_hours: float = 0.25,
    targets: Tuple[float, ...] = PARETO_DEFAULT_TARGETS
) -> ParetoTradeoffResult:
    """
    For each target coverage of annual exceedance energy, determines:
      - the inverter power P (battery shaves the slice between grid limit and limit + P;
        the extreme tips above remain as residual deficit), solved by bisection,
      - the required usable/gross capacity via the multi-peak cluster tracker
        (symmetric inverter: charge power = discharge power = P).
    """
    arr = np.nan_to_num(np.asarray(load_series, dtype=float), nan=0.0)
    overload = np.maximum(0.0, arr - grid_limit_kw)
    total_kwh = float(np.sum(overload) * step_hours)
    max_ov = float(np.max(overload)) if overload.size else 0.0

    tg = sorted({float(t) for t in targets if 0.0 < float(t) <= 100.0} | {100.0})
    n = len(tg)

    if total_kwh <= 0.05:
        zeros = [0.0] * n
        return ParetoTradeoffResult(
            coverage_pct=tg, required_power_kw=list(zeros), required_usable_kwh=list(zeros),
            required_gross_kwh=list(zeros), residual_deficit_kwh=list(zeros), residual_peak_kw=list(zeros),
            capacity_savings_pct=list(zeros), total_exceedance_kwh=total_kwh, max_overload_kw=max_ov
        )

    eta_dis, eta_chg = _efficiency_split(round_trip_efficiency_pct)
    dod = _usable_window_fraction(soc_min_pct, soc_max_pct)
    load_list = arr.tolist()

    def served_fraction(p_kw: float) -> float:
        return float(np.sum(np.minimum(overload, p_kw)) * step_hours) / total_kwh

    powers, usable, gross, residual, residual_peak = [], [], [], [], []
    for t in tg:
        frac = t / 100.0
        if frac >= 0.99999:
            p_kw = max_ov
        else:
            lo, hi = 0.0, max_ov
            for _ in range(40):
                mid = 0.5 * (lo + hi)
                if served_fraction(mid) < frac:
                    lo = mid
                else:
                    hi = mid
            p_kw = hi
        e_use, _, served = _cluster_deficit_tracker(load_list, grid_limit_kw, eta_dis, eta_chg, p_kw, p_kw, step_hours)
        powers.append(p_kw)
        usable.append(e_use)
        gross.append(e_use / dod)
        residual.append(max(0.0, total_kwh - served))
        residual_peak.append(max(0.0, max_ov - p_kw))

    # Enforce monotonic hockey-stick (numerical safety)
    usable_arr = np.maximum.accumulate(np.asarray(usable))
    gross_arr = np.maximum.accumulate(np.asarray(gross))
    gross_100 = float(gross_arr[-1])
    savings = [(1.0 - g / gross_100) * 100.0 if gross_100 > 0 else 0.0 for g in gross_arr]

    return ParetoTradeoffResult(
        coverage_pct=tg,
        required_power_kw=[round(v, 2) for v in powers],
        required_usable_kwh=[round(float(v), 2) for v in usable_arr],
        required_gross_kwh=[round(float(v), 2) for v in gross_arr],
        residual_deficit_kwh=[round(v, 2) for v in residual],
        residual_peak_kw=[round(v, 2) for v in residual_peak],
        capacity_savings_pct=[round(v, 2) for v in savings],
        total_exceedance_kwh=round(total_kwh, 2),
        max_overload_kw=round(max_ov, 2),
    )
