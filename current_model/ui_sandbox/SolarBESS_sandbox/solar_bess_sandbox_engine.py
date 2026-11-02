"""
========================================================================================
Hybrid Solar PV + BESS Sandbox Engine (ui_sandbox/SolarBESS_sandbox/solar_bess_sandbox_engine.py)
========================================================================================

Provides the analytical and physical simulation engine for Scenario 5 (Hybrid Solar + BESS):
  1. Intelligent BESS Pre-Dimensioning after Direct Solar PV:
     - Evaluates net residual load after direct PV self-consumption
     - Performs unconstrained buffer exceedance integration (100% Zero-Breach sizing)
     - Evaluates daily solar surplus buffering potential
     - Emits 3 Sizing Tiers: Peak-Shaving Focus, Self-Consumption Focus, Double-Lever Optimum
  2. Fast 35,040-Step Coupled Hybrid Dispatch Engine:
     - Strategy 1 (`peak_shaving_priority`): Reserves battery strictly for shaving peaks > P_limit
     - Strategy 2 (`hybrid_self_cons_and_peak`): Double-Lever dispatch shifting midday solar surplus
       into afternoon/evening demand while holding a configurable SoC reserve for peak shaving
     - Supports optional grid recharging from available headroom below P_limit
  3. Synergy Benchmark Engine:
     - Evaluates Baseline vs. Solar-Only vs. BESS-Only vs. Hybrid PV+BESS
  4. Combined Plant Economics (Turnkey CAPEX, OPEX, Augmentation & Hybrid LCOE):
     - Itemized PV + BESS CAPEX breakdown, 15-year cashflow outflow schedule, and LCOE
  5. Interactive Plotly Visualization Builders:
     - Synchronized 2-in-1 15-Minute Power Flow & Battery SoC Subplot
     - 12-Month Coupled Energy Balance Stacked Bar Chart
     - Multi-Node Hybrid Energy Flow Sankey Diagram
     - Synergy Benchmark Comparison Chart
     - Combined CAPEX Breakdown Donut & 15-Year Expenditure Trajectory
========================================================================================
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Tuple, Union
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

MONTH_NAMES_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# ======================================================================================
# 1. Data Models
# ======================================================================================

@dataclass
class HybridPreDimensioningResult:
    """Diagnostic pre-dimensioning results for BESS sizing on post-solar net load."""
    orig_peak_kw: float
    net_peak_after_pv_kw: float
    pv_peak_reduction_kw: float
    grid_limit_kw: float
    rem_peak_overload_kw: float
    rem_overload_energy_kwh: float
    rem_overload_energy_mwh: float
    rem_overload_hours: float
    remaining_overload_events: int = 0
    max_single_event_overload_kwh: float = 0.0
    annual_pv_surplus_kwh: float = 0.0
    annual_pv_surplus_mwh: float = 0.0
    avg_daily_pv_surplus_kwh: float = 0.0
    design_sunny_day_surplus_kwh: float = 0.0
    sunny_surplus_days_count: int = 0
    # Tier 1: Peak-Shaving Focus (100% Zero-Breach)
    tier1_peak_kwh: float = 50.0
    tier1_peak_kw: float = 25.0
    # Tier 2: Self-Consumption Focus (Solar Buffer)
    tier2_solar_kwh: float = 100.0
    tier2_solar_kw: float = 50.0
    # Tier 3: Double-Lever Optimum (Combined Peak + Solar Cycle)
    tier3_opt_kwh: float = 125.0
    tier3_opt_kw: float = 50.0

    # Aliases for 100% naming flexibility
    @property
    def original_peak_kw(self) -> float:
        return self.orig_peak_kw

    @property
    def post_solar_peak_kw(self) -> float:
        return self.net_peak_after_pv_kw

    @property
    def remaining_overload_kw(self) -> float:
        return self.rem_peak_overload_kw

    @property
    def remaining_overload_hours(self) -> float:
        return self.rem_overload_hours

    @property
    def remaining_overload_energy_kwh(self) -> float:
        return self.rem_overload_energy_kwh

    @property
    def avg_sunny_day_surplus_kwh(self) -> float:
        return self.avg_daily_pv_surplus_kwh

    @property
    def p75_sunny_day_surplus_kwh(self) -> float:
        return self.design_sunny_day_surplus_kwh

    @property
    def rec_peak_kwh(self) -> float:
        return self.tier1_peak_kwh

    @property
    def rec_peak_kw(self) -> float:
        return self.tier1_peak_kw

    @property
    def rec_solar_kwh(self) -> float:
        return self.tier2_solar_kwh

    @property
    def rec_solar_kw(self) -> float:
        return self.tier2_solar_kw

    @property
    def rec_hybrid_kwh(self) -> float:
        return self.tier3_opt_kwh

    @property
    def rec_hybrid_kw(self) -> float:
        return self.tier3_opt_kw


@dataclass
class HybridKPIs:
    """Comprehensive technical KPIs for a coupled 35,040-step Hybrid Solar + BESS run."""
    annual_load_kwh: float = 0.0
    annual_solar_kwh: float = 0.0
    direct_pv_kwh: float = 0.0
    bess_charged_pv_kwh: float = 0.0
    bess_charged_grid_kwh: float = 0.0
    bess_discharged_kwh: float = 0.0
    bess_discharged_from_pv_kwh: float = 0.0
    bess_losses_kwh: float = 0.0
    grid_import_kwh: float = 0.0
    grid_export_kwh: float = 0.0
    total_self_consumption_kwh: float = 0.0
    self_consumption_rate_pct: float = 0.0
    direct_only_scr_pct: float = 0.0
    autarky_rate_pct: float = 0.0
    direct_only_autarky_pct: float = 0.0
    equivalent_full_cycles: float = 0.0
    orig_peak_kw: float = 0.0
    solar_only_peak_kw: float = 0.0
    new_peak_kw: float = 0.0
    peak_shaved_kw: float = 0.0
    overload_hours_before: float = 0.0
    overload_hours_after_pv_only: float = 0.0
    overload_hours_after_hybrid: float = 0.0
    overload_eliminated_pct: float = 0.0

    # Aliases
    @property
    def total_load_kwh(self) -> float:
        return self.annual_load_kwh

    @property
    def total_pv_kwh(self) -> float:
        return self.annual_solar_kwh

    @property
    def original_peak_kw(self) -> float:
        return self.orig_peak_kw

    @property
    def new_grid_peak_kw(self) -> float:
        return self.new_peak_kw

    @property
    def peak_shaved_pct(self) -> float:
        return (self.peak_shaved_kw / max(0.1, self.orig_peak_kw) * 100.0) if self.orig_peak_kw > 0 else 0.0

    @property
    def eliminated_overload_pct(self) -> float:
        return self.overload_eliminated_pct

    @property
    def overload_hours_after(self) -> float:
        return self.overload_hours_after_hybrid

    @property
    def green_charging_share_pct(self) -> float:
        tot_chg = self.bess_charged_pv_kwh + self.bess_charged_grid_kwh
        return (self.bess_charged_pv_kwh / max(0.01, tot_chg) * 100.0) if tot_chg > 0 else 100.0


@dataclass
class HybridFinancialResult:
    """Combined Turnkey CAPEX, OPEX, Augmentation and LCOE outputs for PV + BESS."""
    currency: str
    pv_kwp: float
    bess_kwh: float
    bess_kw: float
    # CAPEX Breakdown
    capex_pv_modules: float
    capex_pv_mounting_install: float
    capex_pv_inverter_bos: float
    capex_pv_total: float
    capex_bess_racks: float
    capex_bess_pcs: float
    capex_bess_bop_install: float
    capex_bess_total: float
    combined_total_capex: float
    pv_capex_share_pct: float
    bess_capex_share_pct: float
    # OPEX & Augmentation
    annual_opex_pv: float
    annual_opex_bess: float
    combined_annual_opex_year1: float
    augmentation_year: int
    augmentation_cost: float
    # LCOE & Specific Metrics
    lifetime_years: int
    discount_rate_pct: float
    total_lifetime_clean_energy_kwh: float
    npv_total_lifecycle_cost: float
    hybrid_lcoe_per_kwh: float
    specific_capex_per_shaved_kw: float
    df_cashflow_15y: pd.DataFrame
    total_nominal_solar_kwh: float = 0.0

    # Aliases
    @property
    def total_combined_capex(self) -> float:
        return self.combined_total_capex

    @property
    def pv_total_capex(self) -> float:
        return self.capex_pv_total

    @property
    def bess_total_capex(self) -> float:
        return self.capex_bess_total

    @property
    def pv_share_pct(self) -> float:
        return self.pv_capex_share_pct

    @property
    def bess_share_pct(self) -> float:
        return self.bess_capex_share_pct

    @property
    def total_annual_opex_year1(self) -> float:
        return self.combined_annual_opex_year1

    @property
    def pv_annual_opex(self) -> float:
        return self.annual_opex_pv

    @property
    def bess_annual_opex(self) -> float:
        return self.annual_opex_bess

    @property
    def discounted_lcoe_per_kwh(self) -> float:
        return self.hybrid_lcoe_per_kwh

    @property
    def lifetime_clean_energy_delivered_kwh(self) -> float:
        return self.total_lifetime_clean_energy_kwh

    @property
    def lifetime_total_solar_kwh(self) -> float:
        return self.total_nominal_solar_kwh or self.total_lifetime_clean_energy_kwh

    @property
    def df_yearly(self) -> pd.DataFrame:
        return self.df_cashflow_15y


class DualStrategyResult(dict):
    """
    Subclass of dict supporting both dictionary indexing:
        res["peak_shaving_priority"], res["hybrid_self_cons_and_peak"], res["comparison_df"]
    AND tuple unpacking:
        s1, s2, df_comp = simulate_dual_strategies_comparison(...)
    """
    def __iter__(self):
        yield self["peak_shaving_priority"]
        yield self["hybrid_self_cons_and_peak"]
        yield self["comparison_df"]


# ======================================================================================
# 2. Intelligent BESS Pre-Dimensioning Engine
# ======================================================================================

def compute_hybrid_bess_pre_dimensioning(
    load_kw: np.ndarray,
    pv_kw: Optional[np.ndarray] = None,
    grid_limit_kw: float = 0.0,
    solar_kw: Optional[np.ndarray] = None,
    step_hours: float = 0.25,
    usable_dod_pct: float = 80.0,
    rte_pct: float = 88.0,
    soc_min_pct: Optional[float] = None,
    soc_max_pct: Optional[float] = None,
) -> HybridPreDimensioningResult:
    """
    Analyzes the post-solar net load profile and solar surplus to recommend three
    distinct BESS sizing tiers:
      - Tier 1: 100% Zero-Breach Peak Shaving
      - Tier 2: Solar Surplus Self-Consumption Buffer
      - Tier 3: Double-Lever Combined Optimum
    """
    p_load = np.nan_to_num(np.asarray(load_kw, dtype=float), nan=0.0)
    p_solar_src = pv_kw if pv_kw is not None else (solar_kw if solar_kw is not None else np.zeros_like(p_load))
    p_pv = np.nan_to_num(np.asarray(p_solar_src, dtype=float), nan=0.0)
    n_steps = len(p_load)

    if soc_min_pct is not None and soc_max_pct is not None:
        usable_dod_pct = max(10.0, min(100.0, float(soc_max_pct) - float(soc_min_pct)))

    orig_peak = float(np.max(p_load)) if n_steps > 0 else 0.0
    p_direct = np.minimum(p_load, p_pv)
    p_net_after_pv = np.maximum(0.0, p_load - p_direct)
    p_pv_surplus = np.maximum(0.0, p_pv - p_direct)

    net_peak = float(np.max(p_net_after_pv)) if n_steps > 0 else 0.0
    pv_peak_red = max(0.0, orig_peak - net_peak)

    # Remaining overload above grid_limit_kw after direct PV
    overload_arr = np.maximum(0.0, p_net_after_pv - grid_limit_kw)
    rem_peak_overload = float(np.max(overload_arr)) if n_steps > 0 else 0.0
    rem_overload_kwh = float(np.sum(overload_arr) * step_hours)
    rem_overload_mwh = rem_overload_kwh / 1000.0
    rem_overload_hrs = float(np.sum(overload_arr > 0.05) * step_hours)

    # Event analysis: count continuous breach events & worst single-event energy
    in_breach = False
    curr_event_energy = 0.0
    max_event_energy = 0.0
    event_count = 0
    for val in overload_arr:
        if val > 0.05:
            if not in_breach:
                in_breach = True
                event_count += 1
                curr_event_energy = 0.0
            curr_event_energy += val * step_hours
            if curr_event_energy > max_event_energy:
                max_event_energy = curr_event_energy
        else:
            in_breach = False

    # Unconstrained deficit buffer integration (with recharge from PV surplus + grid headroom)
    eta_oneway = np.sqrt(max(0.50, min(1.0, rte_pct / 100.0)))
    dod_frac = max(0.20, min(1.0, usable_dod_pct / 100.0))

    cum_deficit_kwh = 0.0
    max_cum_deficit_kwh = 0.0
    for i in range(n_steps):
        net_l = p_net_after_pv[i]
        surp = p_pv_surplus[i]
        if net_l > grid_limit_kw:
            discharge_needed_kwh = ((net_l - grid_limit_kw) / eta_oneway) * step_hours
            cum_deficit_kwh += discharge_needed_kwh
            if cum_deficit_kwh > max_cum_deficit_kwh:
                max_cum_deficit_kwh = cum_deficit_kwh
        else:
            headroom_kw = max(0.0, grid_limit_kw * 0.90 - net_l)
            avail_chg_kw = surp + headroom_kw
            recharge_kwh = avail_chg_kw * eta_oneway * step_hours
            cum_deficit_kwh = max(0.0, cum_deficit_kwh - recharge_kwh)

    # Tier 1: Peak-Shaving Focus (100% Zero-Breach)
    if rem_peak_overload > 0.1:
        raw_t1_kwh = (max_cum_deficit_kwh / dod_frac) * 1.10
        tier1_kwh = float(max(50.0, np.ceil(raw_t1_kwh / 25.0) * 25.0))
        tier1_kw = float(max(25.0, np.ceil((rem_peak_overload * 1.08) / 10.0) * 10.0))
    else:
        tier1_kwh = 50.0
        tier1_kw = 25.0

    # Solar surplus statistics
    annual_surplus_kwh = float(np.sum(p_pv_surplus) * step_hours)
    annual_surplus_mwh = annual_surplus_kwh / 1000.0
    avg_daily_surplus_kwh = annual_surplus_kwh / 365.0

    steps_per_day = max(1, int(round(24.0 / step_hours)))
    n_days = n_steps // steps_per_day
    sunny_days_count = 0
    if n_days > 0:
        daily_surplus = np.sum(p_pv_surplus[: n_days * steps_per_day].reshape(n_days, steps_per_day), axis=1) * step_hours
        active_days = daily_surplus[daily_surplus > 5.0]
        sunny_days_count = int(len(active_days))
        design_sunny_surplus_kwh = float(np.percentile(active_days, 75)) if len(active_days) > 0 else avg_daily_surplus_kwh
    else:
        design_sunny_surplus_kwh = avg_daily_surplus_kwh

    # Tier 2: Self-Consumption Focus (Solar Buffer)
    if design_sunny_surplus_kwh > 10.0:
        raw_t2_kwh = design_sunny_surplus_kwh / dod_frac
        tier2_kwh = float(max(50.0, np.ceil(raw_t2_kwh / 25.0) * 25.0))
        surplus_pos = p_pv_surplus[p_pv_surplus > 1.0]
        p_surp_75 = float(np.percentile(surplus_pos, 75)) if len(surplus_pos) > 0 else (tier2_kwh * 0.5)
        tier2_kw = float(max(25.0, np.ceil(max(p_surp_75, tier2_kwh * 0.4) / 10.0) * 10.0))
    else:
        tier2_kwh = 100.0
        tier2_kw = 50.0

    # Tier 3: Double-Lever Optimum (Peak Shaving + Solar Shifting)
    if rem_peak_overload > 0.1:
        raw_t3_kwh = max(tier1_kwh, tier2_kwh) + 0.35 * min(tier1_kwh, tier2_kwh)
    else:
        raw_t3_kwh = tier2_kwh
    tier3_kwh = float(max(50.0, np.ceil(raw_t3_kwh / 25.0) * 25.0))
    tier3_kw = float(max(tier1_kw, tier2_kw))

    return HybridPreDimensioningResult(
        orig_peak_kw=round(orig_peak, 1),
        net_peak_after_pv_kw=round(net_peak, 1),
        pv_peak_reduction_kw=round(pv_peak_red, 1),
        grid_limit_kw=round(grid_limit_kw, 1),
        rem_peak_overload_kw=round(rem_peak_overload, 1),
        rem_overload_energy_kwh=round(rem_overload_kwh, 1),
        rem_overload_energy_mwh=round(rem_overload_mwh, 2),
        rem_overload_hours=round(rem_overload_hrs, 1),
        remaining_overload_events=event_count,
        max_single_event_overload_kwh=round(max_event_energy, 1),
        annual_pv_surplus_kwh=round(annual_surplus_kwh, 1),
        annual_pv_surplus_mwh=round(annual_surplus_mwh, 2),
        avg_daily_pv_surplus_kwh=round(avg_daily_surplus_kwh, 1),
        design_sunny_day_surplus_kwh=round(design_sunny_surplus_kwh, 1),
        sunny_surplus_days_count=sunny_days_count,
        tier1_peak_kwh=tier1_kwh,
        tier1_peak_kw=tier1_kw,
        tier2_solar_kwh=tier2_kwh,
        tier2_solar_kw=tier2_kw,
        tier3_opt_kwh=tier3_kwh,
        tier3_opt_kw=tier3_kw,
    )


# ======================================================================================
# 3. Coupled 35,040-Step Hybrid Dispatch Engine (Dual Strategy Support)
# ======================================================================================

def simulate_hybrid_dispatch_2025(
    load_kw: np.ndarray,
    solar_kw: Optional[np.ndarray] = None,
    timestamps: Any = None,
    bess_capacity_kwh: float = 0.0,
    bess_power_kw: float = 0.0,
    grid_limit_kw: float = 0.0,
    strategy: str = "hybrid_self_cons_and_peak",
    allow_grid_charging: bool = True,
    allow_grid_recharge: Optional[bool] = None,
    soc_min_pct: float = 10.0,
    soc_max_pct: float = 90.0,
    peak_reserve_soc_pct: float = 30.0,
    rte_pct: float = 88.0,
    step_hours: float = 0.25,
    pv_kw: Optional[np.ndarray] = None,
) -> Dict[str, Any]:
    """
    Executes a 35,040-step coupled Solar PV + BESS simulation.

    Strategies:
      - `peak_shaving_priority`:
          BESS charges from PV surplus (and off-peak grid headroom if `allow_grid_charging=True`),
          and discharges STRICTLY when residual load exceeds `grid_limit_kw`.
      - `hybrid_self_cons_and_peak` (Double Lever):
          BESS stores midday PV surplus. Discharges above `peak_reserve_soc_pct` to cover afternoon/evening
          facility load (maximizing self-consumption & autarky), while reserving `peak_reserve_soc_pct` down to
          `soc_min_pct` strictly to clip demand peaks exceeding `grid_limit_kw`.
    """
    if allow_grid_recharge is not None:
        allow_grid_charging = allow_grid_recharge

    p_load = np.nan_to_num(np.asarray(load_kw, dtype=float), nan=0.0)
    p_solar_src = pv_kw if pv_kw is not None else (solar_kw if solar_kw is not None else np.zeros_like(p_load))
    p_pv = np.nan_to_num(np.asarray(p_solar_src, dtype=float), nan=0.0)
    n_steps = len(p_load)

    if len(p_pv) < n_steps:
        p_pv = np.pad(p_pv, (0, n_steps - len(p_pv)), mode="constant")
    elif len(p_pv) > n_steps:
        p_pv = p_pv[:n_steps]

    cap_kwh = max(0.0, float(bess_capacity_kwh))
    p_max_kw = max(0.0, float(bess_power_kw))

    eta_chg = np.sqrt(max(0.50, min(1.0, rte_pct / 100.0)))
    eta_dis = eta_chg

    soc_min_kwh = cap_kwh * (max(0.0, min(100.0, soc_min_pct)) / 100.0)
    soc_max_kwh = cap_kwh * (max(0.0, min(100.0, soc_max_pct)) / 100.0)
    eff_reserve_pct = max(soc_min_pct, min(soc_max_pct, peak_reserve_soc_pct))
    soc_reserve_kwh = cap_kwh * (eff_reserve_pct / 100.0)

    # Initial SoC
    curr_soc = soc_max_kwh * 0.70 if strategy == "peak_shaving_priority" else soc_reserve_kwh

    p_direct = np.minimum(p_load, p_pv)
    p_surplus = np.maximum(0.0, p_pv - p_direct)
    p_rem_load = np.maximum(0.0, p_load - p_direct)

    p_bess_chg_pv = np.zeros(n_steps, dtype=float)
    p_bess_chg_grid = np.zeros(n_steps, dtype=float)
    p_bess_dis = np.zeros(n_steps, dtype=float)
    p_grid_import = np.zeros(n_steps, dtype=float)
    p_grid_export = np.zeros(n_steps, dtype=float)
    soc_trace_kwh = np.zeros(n_steps, dtype=float)
    soc_trace_pct = np.zeros(n_steps, dtype=float)

    if cap_kwh <= 0.01 or p_max_kw <= 0.01:
        # No BESS active
        p_grid_import = p_rem_load.copy()
        p_grid_export = p_surplus.copy()
    else:
        for i in range(n_steps):
            surp_kw = p_surplus[i]
            rem_kw = p_rem_load[i]

            if surp_kw > 0.0:
                # 1. Charge BESS from Solar PV Surplus
                room_kwh = max(0.0, soc_max_kwh - curr_soc)
                chg_pv_kw = min(surp_kw, p_max_kw, room_kwh / (eta_chg * step_hours))
                curr_soc += chg_pv_kw * eta_chg * step_hours
                p_bess_chg_pv[i] = chg_pv_kw
                p_grid_export[i] = max(0.0, surp_kw - chg_pv_kw)
                p_grid_import[i] = 0.0
            else:
                # 2. Solar Deficit -> Discharge or Grid Recharge
                if strategy == "peak_shaving_priority":
                    if rem_kw > grid_limit_kw:
                        # Strictly shave peak above grid_limit_kw
                        overload_kw = rem_kw - grid_limit_kw
                        avail_kwh = max(0.0, curr_soc - soc_min_kwh)
                        dis_kw = min(overload_kw, p_max_kw, (avail_kwh * eta_dis) / step_hours)
                        curr_soc -= (dis_kw / eta_dis) * step_hours
                        p_bess_dis[i] = dis_kw
                        p_grid_import[i] = rem_kw - dis_kw
                    else:
                        # Recharge from grid headroom if allowed and SoC < target
                        if allow_grid_charging and curr_soc < (soc_max_kwh * 0.85) and rem_kw < (grid_limit_kw * 0.85):
                            headroom_kw = max(0.0, (grid_limit_kw * 0.88) - rem_kw)
                            room_kwh = max(0.0, (soc_max_kwh * 0.85) - curr_soc)
                            chg_grid_kw = min(headroom_kw, p_max_kw * 0.5, room_kwh / (eta_chg * step_hours))
                            curr_soc += chg_grid_kw * eta_chg * step_hours
                            p_bess_chg_grid[i] = chg_grid_kw
                            p_grid_import[i] = rem_kw + chg_grid_kw
                        else:
                            p_grid_import[i] = rem_kw

                else:
                    # Strategy 2: Double Lever (Max Self-Consumption + Peak-Shaving Reserve)
                    dis_peak_kw = 0.0
                    if rem_kw > grid_limit_kw:
                        # Priority A: Shave overload above grid_limit_kw using full usable capacity down to soc_min_kwh
                        overload_kw = rem_kw - grid_limit_kw
                        avail_peak_kwh = max(0.0, curr_soc - soc_min_kwh)
                        dis_peak_kw = min(overload_kw, p_max_kw, (avail_peak_kwh * eta_dis) / step_hours)
                        curr_soc -= (dis_peak_kw / eta_dis) * step_hours

                    # Priority B: Cover remaining demand below grid_limit_kw using SoC above soc_reserve_kwh
                    rem_after_peak_kw = rem_kw - dis_peak_kw
                    dis_sc_kw = 0.0
                    if rem_after_peak_kw > 0.0 and curr_soc > soc_reserve_kwh:
                        avail_sc_kwh = max(0.0, curr_soc - soc_reserve_kwh)
                        rem_inv_kw = max(0.0, p_max_kw - dis_peak_kw)
                        dis_sc_kw = min(rem_after_peak_kw, rem_inv_kw, (avail_sc_kwh * eta_dis) / step_hours)
                        curr_soc -= (dis_sc_kw / eta_dis) * step_hours

                    total_dis_kw = dis_peak_kw + dis_sc_kw
                    p_bess_dis[i] = total_dis_kw
                    net_grid_kw = rem_kw - total_dis_kw

                    # Priority C: If SoC fell below Peak Reserve during winter/peak event, recharge gently up to Peak Reserve
                    if total_dis_kw == 0.0 and allow_grid_charging and curr_soc < soc_reserve_kwh and net_grid_kw < (grid_limit_kw * 0.85):
                        headroom_kw = max(0.0, (grid_limit_kw * 0.88) - net_grid_kw)
                        room_kwh = max(0.0, soc_reserve_kwh - curr_soc)
                        chg_grid_kw = min(headroom_kw, p_max_kw * 0.4, room_kwh / (eta_chg * step_hours))
                        curr_soc += chg_grid_kw * eta_chg * step_hours
                        p_bess_chg_grid[i] = chg_grid_kw
                        net_grid_kw += chg_grid_kw

                    p_grid_import[i] = net_grid_kw

            soc_trace_kwh[i] = curr_soc
            soc_trace_pct[i] = (curr_soc / cap_kwh * 100.0) if cap_kwh > 0 else 0.0

    # Aggregate Energy Totals (kWh)
    total_load_kwh = float(np.sum(p_load) * step_hours)
    total_pv_kwh = float(np.sum(p_pv) * step_hours)
    direct_pv_kwh = float(np.sum(p_direct) * step_hours)
    bess_chg_pv_kwh = float(np.sum(p_bess_chg_pv) * step_hours)
    bess_chg_grid_kwh = float(np.sum(p_bess_chg_grid) * step_hours)
    bess_dis_kwh = float(np.sum(p_bess_dis) * step_hours)
    grid_import_kwh = float(np.sum(p_grid_import) * step_hours)
    grid_export_kwh = float(np.sum(p_grid_export) * step_hours)

    # Attribute BESS discharge to PV vs Grid
    total_chg_kwh = bess_chg_pv_kwh + bess_chg_grid_kwh
    pv_chg_share = (bess_chg_pv_kwh / total_chg_kwh) if total_chg_kwh > 0 else 1.0
    bess_dis_from_pv_kwh = bess_dis_kwh * pv_chg_share
    bess_losses_kwh = max(0.0, total_chg_kwh - bess_dis_kwh)

    total_self_cons_kwh = direct_pv_kwh + bess_dis_from_pv_kwh
    scr_pct = (total_self_cons_kwh / max(1.0, total_pv_kwh) * 100.0) if total_pv_kwh > 0 else 0.0
    direct_scr_pct = (direct_pv_kwh / max(1.0, total_pv_kwh) * 100.0) if total_pv_kwh > 0 else 0.0

    autarky_pct = (total_self_cons_kwh / max(1.0, total_load_kwh) * 100.0) if total_load_kwh > 0 else 0.0
    direct_autarky_pct = (direct_pv_kwh / max(1.0, total_load_kwh) * 100.0) if total_load_kwh > 0 else 0.0

    efc = (bess_dis_kwh / max(1.0, cap_kwh)) if cap_kwh > 0 else 0.0

    # Peak & Overload Metrics
    orig_peak_kw = float(np.max(p_load)) if n_steps > 0 else 0.0
    solar_only_peak_kw = float(np.max(p_rem_load)) if n_steps > 0 else 0.0
    new_peak_kw = float(np.max(p_grid_import)) if n_steps > 0 else 0.0
    peak_shaved_kw = max(0.0, orig_peak_kw - new_peak_kw)

    ov_hrs_before = float(np.sum(p_load > grid_limit_kw) * step_hours)
    ov_hrs_pv_only = float(np.sum(p_rem_load > grid_limit_kw) * step_hours)
    ov_hrs_hybrid = float(np.sum(p_grid_import > (grid_limit_kw + 0.1)) * step_hours)
    ov_elim_pct = ((ov_hrs_before - ov_hrs_hybrid) / ov_hrs_before * 100.0) if ov_hrs_before > 0 else 100.0

    kpis = HybridKPIs(
        annual_load_kwh=round(total_load_kwh, 1),
        annual_solar_kwh=round(total_pv_kwh, 1),
        direct_pv_kwh=round(direct_pv_kwh, 1),
        bess_charged_pv_kwh=round(bess_chg_pv_kwh, 1),
        bess_charged_grid_kwh=round(bess_chg_grid_kwh, 1),
        bess_discharged_kwh=round(bess_dis_kwh, 1),
        bess_discharged_from_pv_kwh=round(bess_dis_from_pv_kwh, 1),
        bess_losses_kwh=round(bess_losses_kwh, 1),
        grid_import_kwh=round(grid_import_kwh, 1),
        grid_export_kwh=round(grid_export_kwh, 1),
        total_self_consumption_kwh=round(total_self_cons_kwh, 1),
        self_consumption_rate_pct=round(min(100.0, scr_pct), 1),
        direct_only_scr_pct=round(min(100.0, direct_scr_pct), 1),
        autarky_rate_pct=round(min(100.0, autarky_pct), 1),
        direct_only_autarky_pct=round(min(100.0, direct_autarky_pct), 1),
        equivalent_full_cycles=round(efc, 1),
        orig_peak_kw=round(orig_peak_kw, 1),
        solar_only_peak_kw=round(solar_only_peak_kw, 1),
        new_peak_kw=round(new_peak_kw, 1),
        peak_shaved_kw=round(peak_shaved_kw, 1),
        overload_hours_before=round(ov_hrs_before, 1),
        overload_hours_after_pv_only=round(ov_hrs_pv_only, 1),
        overload_hours_after_hybrid=round(ov_hrs_hybrid, 1),
        overload_eliminated_pct=round(max(0.0, min(100.0, ov_elim_pct)), 1),
    )

    df_dispatch = pd.DataFrame({
        "timestamp": timestamps if timestamps is not None else np.arange(n_steps),
        "P_Load_kW": np.round(p_load, 2),
        "P_Solar_kW": np.round(p_pv, 2),
        "P_PV_kW": np.round(p_pv, 2),
        "P_Direct_kW": np.round(p_direct, 2),
        "P_Direct_PV_kW": np.round(p_direct, 2),
        "P_Surplus_kW": np.round(p_surplus, 2),
        "P_BESS_Chg_PV_kW": np.round(p_bess_chg_pv, 2),
        "P_BESS_Chg_Grid_kW": np.round(p_bess_chg_grid, 2),
        "P_BESS_Charge_Total_kW": np.round(p_bess_chg_pv + p_bess_chg_grid, 2),
        "P_BESS_Dis_kW": np.round(p_bess_dis, 2),
        "P_BESS_Discharge_kW": np.round(p_bess_dis, 2),
        "P_Grid_Import_kW": np.round(p_grid_import, 2),
        "P_Grid_Export_kW": np.round(p_grid_export, 2),
        "SoC_kWh": np.round(soc_trace_kwh, 2),
        "SoC_pct": np.round(soc_trace_pct, 1),
    })

    return {
        "kpis": kpis,
        "df_dispatch": df_dispatch,
        "df_timeseries": df_dispatch,
        "p_grid_import_kw": p_grid_import,
        "p_grid_export_kw": p_grid_export,
        "p_bess_dis_kw": p_bess_dis,
        "p_bess_chg_pv_kw": p_bess_chg_pv,
        "p_bess_chg_grid_kw": p_bess_chg_grid,
        "soc_trace_kwh": soc_trace_kwh,
        "soc_trace_pct": soc_trace_pct,
    }


def simulate_dual_strategies_comparison(
    load_kw: np.ndarray,
    solar_kw: Optional[np.ndarray] = None,
    timestamps: Any = None,
    bess_capacity_kwh: float = 0.0,
    bess_power_kw: float = 0.0,
    grid_limit_kw: float = 0.0,
    allow_grid_charging: bool = True,
    allow_grid_recharge: Optional[bool] = None,
    soc_min_pct: float = 10.0,
    soc_max_pct: float = 90.0,
    peak_reserve_soc_pct: float = 30.0,
    rte_pct: float = 88.0,
    pv_kw: Optional[np.ndarray] = None,
) -> DualStrategyResult:
    """
    Runs both Strategy 1 (Strict Peak-Shaving Priority) and Strategy 2 (Double-Lever Self-Consumption + Peak Shaving)
    and returns a DualStrategyResult supporting both dict lookup and tuple unpacking.
    """
    if allow_grid_recharge is not None:
        allow_grid_charging = allow_grid_recharge
    p_pv = pv_kw if pv_kw is not None else (solar_kw if solar_kw is not None else np.zeros_like(load_kw))

    res_s1 = simulate_hybrid_dispatch_2025(
        load_kw=load_kw,
        solar_kw=p_pv,
        timestamps=timestamps,
        bess_capacity_kwh=bess_capacity_kwh,
        bess_power_kw=bess_power_kw,
        grid_limit_kw=grid_limit_kw,
        strategy="peak_shaving_priority",
        allow_grid_charging=allow_grid_charging,
        soc_min_pct=soc_min_pct,
        soc_max_pct=soc_max_pct,
        peak_reserve_soc_pct=peak_reserve_soc_pct,
        rte_pct=rte_pct,
    )

    res_s2 = simulate_hybrid_dispatch_2025(
        load_kw=load_kw,
        solar_kw=p_pv,
        timestamps=timestamps,
        bess_capacity_kwh=bess_capacity_kwh,
        bess_power_kw=bess_power_kw,
        grid_limit_kw=grid_limit_kw,
        strategy="hybrid_self_cons_and_peak",
        allow_grid_charging=allow_grid_charging,
        soc_min_pct=soc_min_pct,
        soc_max_pct=soc_max_pct,
        peak_reserve_soc_pct=peak_reserve_soc_pct,
        rte_pct=rte_pct,
    )

    k1: HybridKPIs = res_s1["kpis"]
    k2: HybridKPIs = res_s2["kpis"]

    df_comp = pd.DataFrame([
        {
            "Operational Strategy": "Strategy 1: Strict Peak-Shaving Priority",
            "New Grid Peak (kW)": f"{k1.new_peak_kw:,.1f} kW",
            "Peak Shaved (kW)": f"-{k1.peak_shaved_kw:,.1f} kW",
            "Remaining Overload (hrs)": f"{k1.overload_hours_after_hybrid:,.1f} hrs ({k1.overload_eliminated_pct:.1f}% elim.)",
            "Combined SCR (%)": f"{k1.self_consumption_rate_pct:.1f} %",
            "Total Autarky (%)": f"{k1.autarky_rate_pct:.1f} %",
            "BESS PV Throughput (MWh)": f"{k1.bess_discharged_from_pv_kwh / 1000.0:,.1f} MWh",
            "Annual Cycles (EFC)": f"{k1.equivalent_full_cycles:.1f}",
            "Residual Grid Import (MWh)": f"{k1.grid_import_kwh / 1000.0:,.1f} MWh",
        },
        {
            "Operational Strategy": "Strategy 2: Double-Lever (Max Self-Consumption + Peak Shaving)",
            "New Grid Peak (kW)": f"{k2.new_peak_kw:,.1f} kW",
            "Peak Shaved (kW)": f"-{k2.peak_shaved_kw:,.1f} kW",
            "Remaining Overload (hrs)": f"{k2.overload_hours_after_hybrid:,.1f} hrs ({k2.overload_eliminated_pct:.1f}% elim.)",
            "Combined SCR (%)": f"{k2.self_consumption_rate_pct:.1f} %",
            "Total Autarky (%)": f"{k2.autarky_rate_pct:.1f} %",
            "BESS PV Throughput (MWh)": f"{k2.bess_discharged_from_pv_kwh / 1000.0:,.1f} MWh",
            "Annual Cycles (EFC)": f"{k2.equivalent_full_cycles:.1f}",
            "Residual Grid Import (MWh)": f"{k2.grid_import_kwh / 1000.0:,.1f} MWh",
        },
    ])

    out = DualStrategyResult({
        "peak_shaving_priority": res_s1,
        "hybrid_self_cons_and_peak": res_s2,
        "comparison_df": df_comp,
    })
    return out


# ======================================================================================
# 4. Synergy Comparison Engine (Baseline vs PV-Only vs BESS-Only vs Hybrid)
# ======================================================================================

def compute_synergy_comparison_metrics(
    load_kw: np.ndarray,
    solar_kw: Optional[np.ndarray] = None,
    timestamps: Any = None,
    bess_capacity_kwh: float = 0.0,
    bess_power_kw: float = 0.0,
    grid_limit_kw: float = 0.0,
    active_hybrid_res: Optional[Dict[str, Any]] = None,
    soc_min_pct: float = 10.0,
    soc_max_pct: float = 90.0,
    rte_pct: float = 88.0,
    pv_kw: Optional[np.ndarray] = None,
) -> pd.DataFrame:
    """
    Computes a 4-way comparison table:
      1. Status Quo (Grid Only)
      2. Standalone Solar PV Only
      3. Standalone BESS Only
      4. Hybrid Solar PV + BESS
    """
    p_load = np.nan_to_num(np.asarray(load_kw, dtype=float), nan=0.0)
    p_pv = pv_kw if pv_kw is not None else (solar_kw if solar_kw is not None else np.zeros_like(p_load))
    p_pv = np.nan_to_num(np.asarray(p_pv, dtype=float), nan=0.0)

    if active_hybrid_res is None:
        active_hybrid_res = simulate_hybrid_dispatch_2025(
            load_kw=p_load,
            solar_kw=p_pv,
            timestamps=timestamps,
            bess_capacity_kwh=bess_capacity_kwh,
            bess_power_kw=bess_power_kw,
            grid_limit_kw=grid_limit_kw,
            strategy="hybrid_self_cons_and_peak",
            soc_min_pct=soc_min_pct,
            soc_max_pct=soc_max_pct,
            rte_pct=rte_pct,
        )

    k_hyb: HybridKPIs = active_hybrid_res["kpis"]

    # Run BESS-only (zero solar)
    zero_solar = np.zeros_like(p_load, dtype=float)
    res_bess_only = simulate_hybrid_dispatch_2025(
        load_kw=p_load,
        solar_kw=zero_solar,
        timestamps=timestamps,
        bess_capacity_kwh=bess_capacity_kwh,
        bess_power_kw=bess_power_kw,
        grid_limit_kw=grid_limit_kw,
        strategy="peak_shaving_priority",
        allow_grid_charging=True,
        soc_min_pct=soc_min_pct,
        soc_max_pct=soc_max_pct,
        rte_pct=rte_pct,
    )
    k_bess: HybridKPIs = res_bess_only["kpis"]

    # Solar-only metrics
    p_direct_solar = np.minimum(p_load, p_pv)
    p_rem_solar = np.maximum(0.0, p_load - p_direct_solar)
    pv_only_import_mwh = float(np.sum(p_rem_solar) * 0.25) / 1000.0
    pv_only_export_mwh = float(np.sum(np.maximum(0.0, p_pv - p_direct_solar)) * 0.25) / 1000.0

    rows = [
        {
            "Configuration": "1. Status Quo (Grid Only)",
            "Grid Peak_kW": k_hyb.orig_peak_kw,
            "Overload_Hours": k_hyb.overload_hours_before,
            "Grid_Import_MWh": round(k_hyb.annual_load_kwh / 1000.0, 1),
            "Clean_Energy_Used_MWh": 0.0,
            "Autarky_pct": 0.0,
            "SCR_pct": 0.0,
            "PV_Export_MWh": 0.0,
        },
        {
            "Configuration": "2. Standalone Solar PV",
            "Grid Peak_kW": k_hyb.solar_only_peak_kw,
            "Overload_Hours": k_hyb.overload_hours_after_pv_only,
            "Grid_Import_MWh": round(pv_only_import_mwh, 1),
            "Clean_Energy_Used_MWh": round(k_hyb.direct_pv_kwh / 1000.0, 1),
            "Autarky_pct": k_hyb.direct_only_autarky_pct,
            "SCR_pct": k_hyb.direct_only_scr_pct,
            "PV_Export_MWh": round(pv_only_export_mwh, 1),
        },
        {
            "Configuration": "3. Standalone BESS Only",
            "Grid Peak_kW": k_bess.new_peak_kw,
            "Overload_Hours": k_bess.overload_hours_after_hybrid,
            "Grid_Import_MWh": round(k_bess.grid_import_kwh / 1000.0, 1),
            "Clean_Energy_Used_MWh": 0.0,
            "Autarky_pct": 0.0,
            "SCR_pct": 0.0,
            "PV_Export_MWh": 0.0,
        },
        {
            "Configuration": "4. Hybrid Solar PV + BESS",
            "Grid Peak_kW": k_hyb.new_peak_kw,
            "Overload_Hours": k_hyb.overload_hours_after_hybrid,
            "Grid_Import_MWh": round(k_hyb.grid_import_kwh / 1000.0, 1),
            "Clean_Energy_Used_MWh": round(k_hyb.total_self_consumption_kwh / 1000.0, 1),
            "Autarky_pct": k_hyb.autarky_rate_pct,
            "SCR_pct": k_hyb.self_consumption_rate_pct,
            "PV_Export_MWh": round(k_hyb.grid_export_kwh / 1000.0, 1),
        },
    ]
    return pd.DataFrame(rows)


# ======================================================================================
# 5. Combined Turnkey Plant Economics Engine (CAPEX, OPEX, Augmentation & Hybrid LCOE)
# ======================================================================================

def compute_hybrid_plant_financials(
    pv_kwp: float,
    bess_kwh: Optional[float] = None,
    bess_kw: Optional[float] = None,
    kpis: Optional[HybridKPIs] = None,
    pv_capex_per_kwp: Optional[float] = None,
    bess_cost_per_kwh: Optional[float] = None,
    bess_cost_per_kw: Optional[float] = None,
    bess_bop_fixed: Optional[float] = None,
    pv_opex_pct: Optional[float] = None,
    bess_opex_pct: Optional[float] = None,
    include_augmentation: bool = True,
    augmentation_year: int = 11,
    augmentation_pct_of_bess_racks: Optional[float] = None,
    discount_rate_pct: float = 6.0,
    lifetime_years: Optional[int] = None,
    pv_degradation_pct: float = 0.45,
    currency: str = "EUR",
    # Flexible keyword aliases matching app.py
    bess_capacity_kwh: Optional[float] = None,
    bess_power_kw: Optional[float] = None,
    pv_capex_eur_per_kwp: Optional[float] = None,
    bess_energy_cost_eur_per_kwh: Optional[float] = None,
    bess_power_cost_eur_per_kw: Optional[float] = None,
    bess_fixed_bop_eur: Optional[float] = None,
    pv_om_pct_pa: Optional[float] = None,
    bess_om_pct_pa: Optional[float] = None,
    augmentation_share_of_energy_capex_pct: Optional[float] = None,
    project_lifetime_years: Optional[int] = None,
) -> HybridFinancialResult:
    """
    Calculates combined PV + BESS turnkey CAPEX, O&M outflows, mid-life augmentation,
    and discounted Hybrid LCOE (EUR/kWh of clean energy utilized on-site + exported).
    """
    eff_bess_kwh = bess_capacity_kwh if bess_capacity_kwh is not None else (bess_kwh if bess_kwh is not None else 0.0)
    eff_bess_kw = bess_power_kw if bess_power_kw is not None else (bess_kw if bess_kw is not None else 0.0)

    eff_pv_capex = pv_capex_eur_per_kwp if pv_capex_eur_per_kwp is not None else (pv_capex_per_kwp if pv_capex_per_kwp is not None else 850.0)
    eff_bess_eur_kwh = bess_energy_cost_eur_per_kwh if bess_energy_cost_eur_per_kwh is not None else (bess_cost_per_kwh if bess_cost_per_kwh is not None else 280.0)
    eff_bess_eur_kw = bess_power_cost_eur_per_kw if bess_power_cost_eur_per_kw is not None else (bess_cost_per_kw if bess_cost_per_kw is not None else 160.0)
    eff_bop_fixed = bess_fixed_bop_eur if bess_fixed_bop_eur is not None else (bess_bop_fixed if bess_bop_fixed is not None else 12000.0)

    eff_pv_om_pct = pv_om_pct_pa if pv_om_pct_pa is not None else (pv_opex_pct if pv_opex_pct is not None else 1.2)
    eff_bess_om_pct = bess_om_pct_pa if bess_om_pct_pa is not None else (bess_opex_pct if bess_opex_pct is not None else 1.5)
    eff_aug_pct = augmentation_share_of_energy_capex_pct if augmentation_share_of_energy_capex_pct is not None else (augmentation_pct_of_bess_racks if augmentation_pct_of_bess_racks is not None else 45.0)
    eff_lifetime = project_lifetime_years if project_lifetime_years is not None else (lifetime_years if lifetime_years is not None else 15)

    if kpis is None:
        kpis = HybridKPIs()

    # 1. Solar CAPEX Partitioning (~55% Modules, ~28% Mounting/Install, ~17% Inverter/BoS)
    capex_pv_total = max(0.0, pv_kwp * eff_pv_capex)
    capex_pv_modules = capex_pv_total * 0.55
    capex_pv_mounting = capex_pv_total * 0.28
    capex_pv_inv = capex_pv_total * 0.17

    # 2. BESS CAPEX Partitioning
    capex_bess_racks = max(0.0, eff_bess_kwh * eff_bess_eur_kwh)
    capex_bess_pcs = max(0.0, eff_bess_kw * eff_bess_eur_kw)
    capex_bess_bop = max(0.0, eff_bop_fixed) if (eff_bess_kwh > 0 or eff_bess_kw > 0) else 0.0
    capex_bess_total = capex_bess_racks + capex_bess_pcs + capex_bess_bop

    combined_capex = capex_pv_total + capex_bess_total
    pv_share_pct = (capex_pv_total / combined_capex * 100.0) if combined_capex > 0 else 0.0
    bess_share_pct = (capex_bess_total / combined_capex * 100.0) if combined_capex > 0 else 0.0

    # 3. Annual O&M & Augmentation
    opex_pv = capex_pv_total * (eff_pv_om_pct / 100.0)
    opex_bess = capex_bess_total * (eff_bess_om_pct / 100.0)
    combined_opex_y1 = opex_pv + opex_bess

    aug_cost = (capex_bess_racks * (eff_aug_pct / 100.0)) if include_augmentation else 0.0

    # 4. Lifecycle Cashflow Outflow & Discounted LCOE
    r = max(0.0, discount_rate_pct / 100.0)
    deg = max(0.0, pv_degradation_pct / 100.0)

    npv_cost = combined_capex
    npv_energy_kwh = 0.0
    total_nominal_energy_kwh = 0.0
    total_nominal_solar_kwh = 0.0
    cum_outflow = combined_capex

    base_clean_used_kwh = kpis.total_self_consumption_kwh + kpis.grid_export_kwh
    if base_clean_used_kwh <= 0:
        base_clean_used_kwh = kpis.annual_solar_kwh

    cf_rows = [
        {
            "Year": 0,
            "Label": "Year 0 (Turnkey CAPEX)",
            "CAPEX_Outflow": round(combined_capex, 2),
            "Annual_OPEX": 0.0,
            "Augmentation_Reserve": 0.0,
            "Total_Annual_Outflow": round(combined_capex, 2),
            "Cumulative_Outflow": round(cum_outflow, 2),
            "Clean_Energy_Delivered_MWh": 0.0,
        }
    ]

    for yr in range(1, eff_lifetime + 1):
        df_fac = (1.0 + r) ** yr
        yr_opex = combined_opex_y1 * ((1.02) ** (yr - 1))
        yr_aug = aug_cost if (include_augmentation and yr == augmentation_year) else 0.0
        yr_total_outflow = yr_opex + yr_aug
        cum_outflow += yr_total_outflow

        yr_energy_kwh = base_clean_used_kwh * ((1.0 - deg) ** (yr - 1))
        yr_solar_kwh = kpis.annual_solar_kwh * ((1.0 - deg) ** (yr - 1))
        total_nominal_energy_kwh += yr_energy_kwh
        total_nominal_solar_kwh += yr_solar_kwh

        npv_cost += yr_total_outflow / df_fac
        npv_energy_kwh += yr_energy_kwh / df_fac

        cf_rows.append({
            "Year": yr,
            "Label": f"Year {yr}",
            "CAPEX_Outflow": 0.0,
            "Annual_OPEX": round(yr_opex, 2),
            "Augmentation_Reserve": round(yr_aug, 2),
            "Total_Annual_Outflow": round(yr_total_outflow, 2),
            "Cumulative_Outflow": round(cum_outflow, 2),
            "Clean_Energy_Delivered_MWh": round(yr_energy_kwh / 1000.0, 1),
        })

    hybrid_lcoe = (npv_cost / npv_energy_kwh) if npv_energy_kwh > 0 else 0.0
    spec_capex_shaved_kw = (combined_capex / kpis.peak_shaved_kw) if kpis.peak_shaved_kw > 0.1 else 0.0

    return HybridFinancialResult(
        currency=currency,
        pv_kwp=round(pv_kwp, 2),
        bess_kwh=round(eff_bess_kwh, 1),
        bess_kw=round(eff_bess_kw, 1),
        capex_pv_modules=round(capex_pv_modules, 2),
        capex_pv_mounting_install=round(capex_pv_mounting, 2),
        capex_pv_inverter_bos=round(capex_pv_inv, 2),
        capex_pv_total=round(capex_pv_total, 2),
        capex_bess_racks=round(capex_bess_racks, 2),
        capex_bess_pcs=round(capex_bess_pcs, 2),
        capex_bess_bop_install=round(capex_bess_bop, 2),
        capex_bess_total=round(capex_bess_total, 2),
        combined_total_capex=round(combined_capex, 2),
        pv_capex_share_pct=round(pv_share_pct, 1),
        bess_capex_share_pct=round(bess_share_pct, 1),
        annual_opex_pv=round(opex_pv, 2),
        annual_opex_bess=round(opex_bess, 2),
        combined_annual_opex_year1=round(combined_opex_y1, 2),
        augmentation_year=augmentation_year,
        augmentation_cost=round(aug_cost, 2),
        lifetime_years=eff_lifetime,
        discount_rate_pct=discount_rate_pct,
        total_lifetime_clean_energy_kwh=round(total_nominal_energy_kwh, 0),
        npv_total_lifecycle_cost=round(npv_cost, 2),
        hybrid_lcoe_per_kwh=round(hybrid_lcoe, 4),
        specific_capex_per_shaved_kw=round(spec_capex_shaved_kw, 2),
        df_cashflow_15y=pd.DataFrame(cf_rows),
        total_nominal_solar_kwh=round(total_nominal_solar_kwh, 0),
    )


# ======================================================================================
# 6. Interactive Plotly Visualization Builders
# ======================================================================================

def create_hybrid_synchronized_dispatch_soc_figure(
    df_dispatch: Optional[pd.DataFrame] = None,
    grid_limit_kw: float = 0.0,
    pv_kwp: float = 0.0,
    bess_kwh: Optional[float] = None,
    bess_kw: Optional[float] = None,
    soc_min_pct: float = 10.0,
    soc_max_pct: float = 90.0,
    focus_peak_week: bool = False,
    # Flexible keyword aliases matching app.py
    df_ts: Optional[pd.DataFrame] = None,
    bess_capacity_kwh: Optional[float] = None,
    bess_power_kw: Optional[float] = None,
) -> go.Figure:
    """
    Constructs a synchronized 2-in-1 subplot:
      - Top Subplot (Row 1): 15-Minute Power Flows (Facility Load, Solar PV, BESS Charge/Discharge,
        Residual Grid Import, and Red Dashed Grid Limit Line).
      - Bottom Subplot (Row 2): Battery State of Charge (SoC % and kWh) with operating bounds.
    """
    target_df = df_ts if df_ts is not None else df_dispatch
    if target_df is None:
        target_df = pd.DataFrame()

    eff_bess_kwh = bess_capacity_kwh if bess_capacity_kwh is not None else (bess_kwh if bess_kwh is not None else 0.0)
    eff_bess_kw = bess_power_kw if bess_power_kw is not None else (bess_kw if bess_kw is not None else 0.0)

    step = 2 if (len(target_df) > 20000 and not focus_peak_week) else 1
    if focus_peak_week and len(target_df) > 672:
        peak_idx = int(target_df["P_Load_kW"].idxmax())
        start_idx = max(0, peak_idx - 336)
        end_idx = min(len(target_df), start_idx + 672)
        plot_df = target_df.iloc[start_idx:end_idx].copy()
    else:
        plot_df = target_df.iloc[::step].copy()

    timestamps = pd.to_datetime(plot_df["timestamp"])

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.07,
        row_heights=[0.65, 0.35],
        subplot_titles=(
            f"<b>15-Minute Hybrid Power Dispatch</b> ({pv_kwp:,.0f} kWp Solar PV + {eff_bess_kwh:,.0f} kWh / {eff_bess_kw:,.0f} kW BESS)",
            "<b>Synchronized Battery State of Charge (SoC %)</b>",
        ),
    )

    # --- ROW 1: Power Flows ---
    fig.add_trace(
        go.Scattergl(
            x=timestamps,
            y=plot_df["P_Load_kW"],
            name="Facility Load (kW)",
            line=dict(color="#94A3B8", width=1.4, dash="dot"),
            hovertemplate="Facility Load: <b>%{y:,.1f} kW</b><extra></extra>",
        ),
        row=1,
        col=1,
    )

    p_sol_col = "P_Solar_kW" if "P_Solar_kW" in plot_df.columns else "P_PV_kW"
    fig.add_trace(
        go.Scattergl(
            x=timestamps,
            y=plot_df[p_sol_col],
            name="Solar PV Generation (kW)",
            line=dict(color="#FACC15", width=1.6),
            fill="tozeroy",
            fillcolor="rgba(250, 204, 21, 0.16)",
            hovertemplate="Solar PV: <b>%{y:,.1f} kW</b><extra></extra>",
        ),
        row=1,
        col=1,
    )

    p_dis_col = "P_BESS_Discharge_kW" if "P_BESS_Discharge_kW" in plot_df.columns else "P_BESS_Dis_kW"
    fig.add_trace(
        go.Scattergl(
            x=timestamps,
            y=plot_df[p_dis_col],
            name="BESS Discharge (kW)",
            line=dict(color="#10B981", width=1.8),
            fill="tozeroy",
            fillcolor="rgba(16, 185, 129, 0.28)",
            hovertemplate="BESS Discharge: <b>%{y:,.1f} kW</b><extra></extra>",
        ),
        row=1,
        col=1,
    )

    if "P_BESS_Charge_Total_kW" in plot_df.columns:
        total_chg_kw = plot_df["P_BESS_Charge_Total_kW"]
    else:
        total_chg_kw = plot_df["P_BESS_Chg_PV_kW"] + plot_df["P_BESS_Chg_Grid_kW"]

    fig.add_trace(
        go.Scattergl(
            x=timestamps,
            y=-total_chg_kw,
            name="BESS Charging (-kW)",
            line=dict(color="#06B6D4", width=1.4),
            fill="tozeroy",
            fillcolor="rgba(6, 182, 212, 0.20)",
            hovertemplate="BESS Charging: <b>%{y:,.1f} kW</b><extra></extra>",
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Scattergl(
            x=timestamps,
            y=plot_df["P_Grid_Import_kW"],
            name="Residual Grid Import (kW)",
            line=dict(color="#38BDF8", width=2.0),
            hovertemplate="Net Grid Import: <b>%{y:,.1f} kW</b><extra></extra>",
        ),
        row=1,
        col=1,
    )

    if grid_limit_kw > 0:
        fig.add_hline(
            y=grid_limit_kw,
            line_dash="dash",
            line_color="#EF4444",
            line_width=2,
            annotation_text=f"Grid Limit ({grid_limit_kw:,.0f} kW)",
            annotation_position="top left",
            annotation_font_color="#EF4444",
            row=1,
            col=1,
        )

    # --- ROW 2: Battery State of Charge ---
    fig.add_trace(
        go.Scattergl(
            x=timestamps,
            y=plot_df["SoC_pct"],
            name="Battery SoC (%)",
            line=dict(color="#A855F7", width=2.0),
            fill="tozeroy",
            fillcolor="rgba(168, 85, 247, 0.20)",
            customdata=plot_df["SoC_kWh"],
            hovertemplate="SoC: <b>%{y:.1f}%</b> (%{customdata:,.1f} kWh)<extra></extra>",
        ),
        row=2,
        col=1,
    )

    fig.add_hline(
        y=soc_max_pct,
        line_dash="dot",
        line_color="#64748B",
        line_width=1,
        annotation_text=f"Max SoC ({soc_max_pct:.0f}%)",
        annotation_position="top right",
        annotation_font_color="#94A3B8",
        row=2,
        col=1,
    )
    fig.add_hline(
        y=soc_min_pct,
        line_dash="dot",
        line_color="#EF4444",
        line_width=1,
        annotation_text=f"Min SoC ({soc_min_pct:.0f}%)",
        annotation_position="bottom right",
        annotation_font_color="#EF4444",
        row=2,
        col=1,
    )

    fig.update_layout(
        template="plotly_dark",
        height=640,
        margin=dict(l=20, r=20, t=75, b=20),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.06, xanchor="right", x=1.0),
        xaxis=dict(
            rangeselector=dict(
                buttons=list([
                    dict(count=7, label="7D", step="day", stepmode="backward"),
                    dict(count=1, label="1M", step="month", stepmode="backward"),
                    dict(count=3, label="3M", step="month", stepmode="backward"),
                    dict(step="all", label="All"),
                ]),
                bgcolor="#1E293B",
                activecolor="#2563EB",
                font=dict(color="#F8FAFC", size=11),
            ),
            gridcolor="#1E293B",
        ),
        xaxis2=dict(
            title="Date & Time",
            rangeslider=dict(visible=True, thickness=0.05),
            gridcolor="#1E293B",
        ),
        yaxis=dict(title="Power (kW)", gridcolor="#1E293B"),
        yaxis2=dict(title="SoC (%)", range=[0, 105], gridcolor="#1E293B"),
    )

    return fig


def create_hybrid_monthly_balance_figure(
    df_dispatch: Optional[pd.DataFrame] = None,
    df_ts: Optional[pd.DataFrame] = None,
) -> go.Figure:
    """
    Constructs a 12-month stacked bar chart decomposing monthly energy flows:
      - Direct Solar PV Self-Consumption (MWh)
      - Solar PV Buffered via BESS (MWh)
      - Residual Grid Import (MWh)
      - Net Solar PV Grid Export (MWh)
    """
    target_df = df_ts if df_ts is not None else df_dispatch
    if target_df is None or target_df.empty:
        return go.Figure()

    df_c = target_df.copy()
    df_c["month"] = pd.to_datetime(df_c["timestamp"]).dt.month
    dt = 0.25

    p_dir_col = "P_Direct_PV_kW" if "P_Direct_PV_kW" in df_c.columns else "P_Direct_kW"
    p_dis_col = "P_BESS_Discharge_kW" if "P_BESS_Discharge_kW" in df_c.columns else "P_BESS_Dis_kW"

    direct_mwh = []
    bess_dis_mwh = []
    grid_imp_mwh = []
    grid_exp_mwh = []

    for m in range(1, 13):
        sub = df_c[df_c["month"] == m]
        if not sub.empty:
            direct_mwh.append(float(sub[p_dir_col].sum() * dt) / 1000.0)
            bess_dis_mwh.append(float(sub[p_dis_col].sum() * dt) / 1000.0)
            grid_imp_mwh.append(float(sub["P_Grid_Import_kW"].sum() * dt) / 1000.0)
            grid_exp_mwh.append(float(sub["P_Grid_Export_kW"].sum() * dt) / 1000.0)
        else:
            direct_mwh.append(0.0)
            bess_dis_mwh.append(0.0)
            grid_imp_mwh.append(0.0)
            grid_exp_mwh.append(0.0)

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=MONTH_NAMES_SHORT,
            y=direct_mwh,
            name="Direct Solar PV Used (MWh)",
            marker_color="#10B981",
        )
    )
    fig.add_trace(
        go.Bar(
            x=MONTH_NAMES_SHORT,
            y=bess_dis_mwh,
            name="BESS Discharged to Load (MWh)",
            marker_color="#A855F7",
        )
    )
    fig.add_trace(
        go.Bar(
            x=MONTH_NAMES_SHORT,
            y=grid_imp_mwh,
            name="Residual Grid Import (MWh)",
            marker_color="#38BDF8",
        )
    )
    fig.add_trace(
        go.Bar(
            x=MONTH_NAMES_SHORT,
            y=grid_exp_mwh,
            name="Net PV Grid Export (MWh)",
            marker_color="#FACC15",
        )
    )

    fig.update_layout(
        barmode="stack",
        template="plotly_dark",
        title=dict(text="<b>12-Month Coupled Hybrid Energy Balance (MWh)</b>", font=dict(size=14, color="#F8FAFC")),
        xaxis=dict(title="Month", gridcolor="#1E293B"),
        yaxis=dict(title="Energy (MWh)", gridcolor="#1E293B"),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        height=420,
        margin=dict(l=20, r=20, t=60, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1.0),
    )
    return fig


def create_hybrid_sankey_figure(kpis: HybridKPIs) -> go.Figure:
    """
    Constructs a multi-node Sankey diagram tracing:
      - Sources: Solar PV Generation, Public Grid Import
      - Intermediate: BESS Storage
      - Sinks: Facility Demand, Grid Export, BESS Round-Trip Losses
    """
    pv_gen = max(0.0, kpis.annual_solar_kwh)
    grid_imp = max(0.0, kpis.grid_import_kwh)
    direct_pv = max(0.0, kpis.direct_pv_kwh)
    bess_chg_pv = max(0.0, kpis.bess_charged_pv_kwh)
    bess_chg_grid = max(0.0, kpis.bess_charged_grid_kwh)
    bess_dis = max(0.0, kpis.bess_discharged_kwh)
    bess_loss = max(0.0, kpis.bess_losses_kwh)
    pv_exp = max(0.0, kpis.grid_export_kwh)
    load_total = max(1.0, kpis.annual_load_kwh)

    grid_to_load = max(0.0, grid_imp - bess_chg_grid)

    labels = [
        f"<b>Solar PV Generation</b><br>{pv_gen / 1000.0:,.1f} MWh",
        f"<b>Public Grid Supply</b><br>{grid_imp / 1000.0:,.1f} MWh",
        f"<b>BESS Energy Buffer</b><br>{(bess_chg_pv + bess_chg_grid) / 1000.0:,.1f} MWh in",
        f"<b>Facility Load Demand</b><br>{load_total / 1000.0:,.1f} MWh (Autarky: {kpis.autarky_rate_pct:.1f}%)",
        f"<b>PV Surplus Grid Export</b><br>{pv_exp / 1000.0:,.1f} MWh",
        f"<b>BESS Conversion Losses</b><br>{bess_loss / 1000.0:,.1f} MWh",
    ]

    colors = ["#FACC15", "#38BDF8", "#A855F7", "#10B981", "#F59E0B", "#EF4444"]

    sources = [0, 0, 0, 1, 1, 2, 2]
    targets = [3, 2, 4, 3, 2, 3, 5]
    values = [
        max(0.1, direct_pv),
        max(0.1, bess_chg_pv),
        max(0.1, pv_exp),
        max(0.1, grid_to_load),
        max(0.01, bess_chg_grid),
        max(0.1, bess_dis),
        max(0.01, bess_loss),
    ]
    link_colors = [
        "rgba(16, 185, 129, 0.42)",
        "rgba(168, 85, 247, 0.42)",
        "rgba(250, 204, 21, 0.35)",
        "rgba(56, 189, 248, 0.38)",
        "rgba(56, 189, 248, 0.25)",
        "rgba(168, 85, 247, 0.48)",
        "rgba(239, 68, 68, 0.35)",
    ]

    fig = go.Figure(
        go.Sankey(
            node=dict(
                pad=20,
                thickness=24,
                line=dict(color="#0B0F19", width=1.5),
                label=labels,
                color=colors,
            ),
            link=dict(source=sources, target=targets, value=values, color=link_colors),
        )
    )

    fig.update_layout(
        template="plotly_dark",
        title=dict(text="<b>Annual Hybrid Energy Flow Sankey Diagram (MWh)</b>", font=dict(size=14, color="#F8FAFC")),
        font=dict(size=11, color="#F8FAFC"),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        height=400,
        margin=dict(l=20, r=20, t=55, b=20),
    )
    return fig


def create_hybrid_synergy_comparison_figure(df_synergy: pd.DataFrame, grid_limit_kw: float) -> go.Figure:
    """
    Constructs a dual-panel comparison chart comparing:
      - Left: Grid Peak Demand (kW) & Overload Hours across Status Quo, Solar-Only, BESS-Only, Hybrid
      - Right: Autarky Rate (%) & Self-Consumption Rate (%)
    """
    fig = make_subplots(
        rows=1,
        cols=2,
        subplot_titles=(
            "<b>Grid Peak Demand (kW) vs. Contract Limit</b>",
            "<b>Clean Energy Autarky (%) & Self-Consumption (SCR %)</b>",
        ),
    )

    configs = df_synergy["Configuration"].tolist()

    # Left: Grid Peak Demand
    fig.add_trace(
        go.Bar(
            x=configs,
            y=df_synergy["Grid Peak_kW"],
            name="Grid Peak Demand (kW)",
            marker_color=["#EF4444", "#FACC15", "#38BDF8", "#10B981"],
            text=[f"{v:,.0f} kW" for v in df_synergy["Grid Peak_kW"]],
            textposition="auto",
        ),
        row=1,
        col=1,
    )
    if grid_limit_kw > 0:
        fig.add_hline(
            y=grid_limit_kw,
            line_dash="dash",
            line_color="#EF4444",
            annotation_text=f"Grid Limit ({grid_limit_kw:,.0f} kW)",
            row=1,
            col=1,
        )

    # Right: Autarky & SCR
    fig.add_trace(
        go.Bar(
            x=configs,
            y=df_synergy["Autarky_pct"],
            name="Facility Autarky (%)",
            marker_color="#10B981",
            text=[f"{v:.1f}%" for v in df_synergy["Autarky_pct"]],
            textposition="auto",
        ),
        row=1,
        col=2,
    )
    fig.add_trace(
        go.Bar(
            x=configs,
            y=df_synergy["SCR_pct"],
            name="Solar Self-Consumption (SCR %)",
            marker_color="#A855F7",
            text=[f"{v:.1f}%" for v in df_synergy["SCR_pct"]],
            textposition="auto",
        ),
        row=1,
        col=2,
    )

    fig.update_layout(
        template="plotly_dark",
        barmode="group",
        height=390,
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        margin=dict(l=20, r=20, t=60, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.08, xanchor="right", x=1.0),
    )
    fig.update_yaxes(title_text="Peak Demand (kW)", gridcolor="#1E293B", row=1, col=1)
    fig.update_yaxes(title_text="Percentage (%)", range=[0, 108], gridcolor="#1E293B", row=1, col=2)

    return fig


def create_hybrid_capex_donut_figure(fin_res: HybridFinancialResult) -> go.Figure:
    """Renders a 5-component donut chart of the combined PV + BESS Turnkey CAPEX."""
    labels = [
        "PV Solar Modules",
        "PV Substructure & Installation",
        "PV Inverters & Electrical BoS",
        "BESS Battery Storage Racks",
        "BESS Power Conversion (PCS) & BoP",
    ]
    values = [
        fin_res.capex_pv_modules,
        fin_res.capex_pv_mounting_install,
        fin_res.capex_pv_inverter_bos,
        fin_res.capex_bess_racks,
        fin_res.capex_bess_pcs + fin_res.capex_bess_bop_install,
    ]
    colors = ["#FACC15", "#F59E0B", "#D97706", "#A855F7", "#38BDF8"]

    fig = go.Figure(
        go.Pie(
            labels=labels,
            values=values,
            hole=0.55,
            marker=dict(colors=colors, line=dict(color="#0B0F19", width=2)),
            textinfo="label+percent",
            hovertemplate="<b>%{label}</b><br>%{value:,.0f} " + fin_res.currency + " (%{percent})<extra></extra>",
        )
    )
    fig.update_layout(
        template="plotly_dark",
        title=dict(text=f"<b>Combined Turnkey CAPEX Breakdown ({fin_res.combined_total_capex:,.0f} {fin_res.currency})</b>", font=dict(size=14, color="#F8FAFC")),
        height=380,
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        margin=dict(l=20, r=20, t=55, b=20),
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=-0.18, xanchor="center", x=0.5),
    )
    return fig


def create_hybrid_15y_outflow_figure(fin_res: HybridFinancialResult) -> go.Figure:
    """Renders the 15-Year Expenditure Schedule (Annual O&M, Augmentation & Cumulative Outflow)."""
    df_cf = fin_res.df_cashflow_15y
    df_ops = df_cf[df_cf["Year"] >= 1].copy()

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    fig.add_trace(
        go.Bar(
            x=df_ops["Label"],
            y=df_ops["Annual_OPEX"],
            name=f"Annual O&M ({fin_res.currency})",
            marker_color="#38BDF8",
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Bar(
            x=df_ops["Label"],
            y=df_ops["Augmentation_Reserve"],
            name=f"BESS Mid-Life Augmentation ({fin_res.currency})",
            marker_color="#F59E0B",
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=df_ops["Label"],
            y=df_ops["Cumulative_Outflow"],
            name=f"Cumulative Total Expenditure ({fin_res.currency})",
            mode="lines+markers",
            line=dict(color="#10B981", width=2.5),
            marker=dict(size=6),
        ),
        secondary_y=True,
    )

    fig.update_layout(
        barmode="stack",
        template="plotly_dark",
        title=dict(text="<b>15-Year Operating Expenditure, Augmentation & Cumulative Outflow</b>", font=dict(size=14, color="#F8FAFC")),
        height=380,
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        margin=dict(l=20, r=20, t=55, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1.0),
    )
    fig.update_yaxes(title_text=f"Annual Outflow ({fin_res.currency}/yr)", gridcolor="#1E293B", secondary_y=False)
    fig.update_yaxes(title_text=f"Cumulative Outflow ({fin_res.currency})", gridcolor="#1E293B", secondary_y=True)

    return fig
