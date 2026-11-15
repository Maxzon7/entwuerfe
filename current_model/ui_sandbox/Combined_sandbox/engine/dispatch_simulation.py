"""
35,040-step coupled 4-source dispatch Numba kernel, coupled battery capacity calibration,
and main physical simulation orchestrator.
"""

from dataclasses import replace
from typing import Any, Dict, List, Optional, Tuple
import math
import numpy as np
import pandas as pd

try:
    from current_model.core.bess_engine import analyze_grid_violations
except ImportError:
    from core.bess_engine import analyze_grid_violations

from .models_and_presets import (
    _opt_njit,
    FUEL_SPECS,
    CombinedSystemConfig,
    InteractionRulesConfig,
    CombinedTechnicalKPIs,
    CombinedSimulationResult,
)
from .solar_and_sizing import (
    get_unit_solar_generation_profile,
    derive_solar_sizing_and_formula,
)
from .utilization_and_tables import (
    build_component_summary_table,
    build_monthly_balance_table,
)

# ======================================================================================
# 4. Main 35,040-Step 4-Source Combined Dispatch Engine
# ======================================================================================

@_opt_njit
def _fast_combined_dispatch_kernel(
    rem_load_after_solar_kw: np.ndarray,
    solar_surplus_kw: np.ndarray,
    grid_limit_kw: float,
    enable_bess: bool,
    bess_p_max_kw: float,
    e_min_kwh: float,
    e_max_kwh: float,
    e_reserve_kwh: float,
    eta_chg: float,
    eta_dis: float,
    enable_gen: bool,
    gen_rated_kw: float,
    gen_min_kw: float,
    min_run_steps: int,
    rule1_battery_first: bool,
    effective_rule2_self_cons: bool,
    allow_grid_chg: bool,
    allow_gen_chg: bool,
    target_grid_e_kwh: float,
    init_e_kwh: float,
    init_solar_e_kwh: float,
    dt: float,
    is_gap: np.ndarray,
) -> Tuple[
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    float,
]:
    """
    JIT-compiled / low-overhead 35,040-step stateful dispatch kernel.
    Eliminates Python object/attribute lookups and method call overhead inside the 15-min loop.
    """
    n_steps = len(rem_load_after_solar_kw)
    solar_export_kw = np.zeros(n_steps, dtype=np.float64)
    bess_charge_solar_kw = np.zeros(n_steps, dtype=np.float64)
    bess_charge_grid_kw = np.zeros(n_steps, dtype=np.float64)
    bess_charge_gen_kw = np.zeros(n_steps, dtype=np.float64)
    bess_discharge_kw = np.zeros(n_steps, dtype=np.float64)
    bess_energy_kwh = np.zeros(n_steps, dtype=np.float64)
    gen_output_kw = np.zeros(n_steps, dtype=np.float64)
    gen_to_load_kw = np.zeros(n_steps, dtype=np.float64)
    gen_to_bess_kw = np.zeros(n_steps, dtype=np.float64)

    cur_e_kwh = init_e_kwh
    solar_energy_in_bess_kwh = init_solar_e_kwh
    bess_discharge_from_solar_kwh_acc = 0.0
    gen_Forced_steps_remaining = 0

    inv_dt_eta_chg = 1.0 / (dt * eta_chg)
    dt_eta_chg = dt * eta_chg
    eta_dis_over_dt = eta_dis / dt
    dt_over_eta_dis = dt / eta_dis
    gen_min_clamped = gen_rated_kw if gen_rated_kw < gen_min_kw else gen_min_kw

    for i in range(n_steps):
        if is_gap[i]:
            bess_energy_kwh[i] = cur_e_kwh
            solar_export_kw[i] = 0.0
            continue

        p_rem = rem_load_after_solar_kw[i]
        p_surplus = solar_surplus_kw[i]

        step_bess_chg_solar = 0.0
        step_bess_chg_grid = 0.0
        step_bess_chg_gen = 0.0
        step_bess_dis = 0.0
        step_gen_out = 0.0
        step_gen_to_load = 0.0
        step_gen_to_bess = 0.0

        # A. Charge Battery from Solar Surplus (if available)
        if p_surplus > 0.0 and enable_bess and cur_e_kwh < e_max_kwh:
            room_ac_kw = (e_max_kwh - cur_e_kwh) * inv_dt_eta_chg
            step_bess_chg_solar = p_surplus
            if bess_p_max_kw < step_bess_chg_solar:
                step_bess_chg_solar = bess_p_max_kw
            if room_ac_kw < step_bess_chg_solar:
                step_bess_chg_solar = room_ac_kw
            added_e = step_bess_chg_solar * dt_eta_chg
            cur_e_kwh += added_e
            solar_energy_in_bess_kwh += added_e
            if solar_energy_in_bess_kwh > cur_e_kwh:
                solar_energy_in_bess_kwh = cur_e_kwh
            exp_kw = p_surplus - step_bess_chg_solar
            solar_export_kw[i] = exp_kw if exp_kw > 0.0 else 0.0
        else:
            solar_export_kw[i] = p_surplus

        rem_bess_chg_power_kw = bess_p_max_kw - step_bess_chg_solar
        if rem_bess_chg_power_kw < 0.0:
            rem_bess_chg_power_kw = 0.0

        # B. Handle Residual Demand
        if p_rem > grid_limit_kw:
            # --- ABOVE GRID LIMIT (Peak Shaving Region) ---
            overload_kw = p_rem - grid_limit_kw

            if rule1_battery_first:
                # 1. Battery discharges first down to e_min_kwh
                if enable_bess and step_bess_chg_solar == 0.0 and cur_e_kwh > e_min_kwh:
                    avail_dis_ac_kw = (cur_e_kwh - e_min_kwh) * eta_dis_over_dt
                    step_bess_dis = overload_kw
                    if bess_p_max_kw < step_bess_dis:
                        step_bess_dis = bess_p_max_kw
                    if avail_dis_ac_kw < step_bess_dis:
                        step_bess_dis = avail_dis_ac_kw
                    removed_e = step_bess_dis * dt_over_eta_dis
                    solar_share = (solar_energy_in_bess_kwh / cur_e_kwh) if cur_e_kwh > 0.0 else 0.0
                    bess_discharge_from_solar_kwh_acc += (step_bess_dis * dt) * solar_share
                    cur_e_kwh -= removed_e
                    if cur_e_kwh < e_min_kwh:
                        cur_e_kwh = e_min_kwh
                    solar_energy_in_bess_kwh -= removed_e * solar_share
                    if solar_energy_in_bess_kwh < 0.0:
                        solar_energy_in_bess_kwh = 0.0

                rem_overload_kw = overload_kw - step_bess_dis
                if rem_overload_kw < 0.0:
                    rem_overload_kw = 0.0

                # 2. Generator covers remaining overload second (or continues if forced by min runtime)
                if (rem_overload_kw > 0.001 or gen_Forced_steps_remaining > 0) and enable_gen:
                    if rem_overload_kw > 0.001 and gen_Forced_steps_remaining == 0:
                        gen_Forced_steps_remaining = min_run_steps
                    req_gen_kw = rem_overload_kw if rem_overload_kw < gen_rated_kw else gen_rated_kw
                    actual_gen_kw = req_gen_kw if req_gen_kw > gen_min_clamped else gen_min_clamped
                    step_gen_out = actual_gen_kw
                    step_gen_to_load = actual_gen_kw if actual_gen_kw < rem_overload_kw else rem_overload_kw

                    gen_excess_kw = actual_gen_kw - step_gen_to_load
                    if gen_excess_kw > 0.0:
                        if allow_gen_chg and enable_bess and step_bess_dis == 0.0 and cur_e_kwh < e_max_kwh:
                            room_ac_kw = (e_max_kwh - cur_e_kwh) * inv_dt_eta_chg
                            step_bess_chg_gen = gen_excess_kw
                            if rem_bess_chg_power_kw < step_bess_chg_gen:
                                step_bess_chg_gen = rem_bess_chg_power_kw
                            if room_ac_kw < step_bess_chg_gen:
                                step_bess_chg_gen = room_ac_kw
                            cur_e_kwh += step_bess_chg_gen * dt_eta_chg
                            gen_excess_after_bess = gen_excess_kw - step_bess_chg_gen
                        else:
                            gen_excess_after_bess = gen_excess_kw
                        rem_p = p_rem - step_bess_dis - step_gen_to_load
                        if rem_p > 0.0:
                            extra_to_load = gen_excess_after_bess if gen_excess_after_bess < rem_p else rem_p
                            step_gen_to_load += extra_to_load
                    step_gen_to_bess = step_bess_chg_gen
                    gen_Forced_steps_remaining -= 1
                    if gen_Forced_steps_remaining < 0:
                        gen_Forced_steps_remaining = 0

            else:
                # --- "generator_first": Generator first, Battery for fast/small peaks ---
                avail_bess_dis_kw = (
                    (cur_e_kwh - e_min_kwh) * eta_dis_over_dt
                    if (enable_bess and step_bess_chg_solar == 0.0 and cur_e_kwh > e_min_kwh)
                    else 0.0
                )
                if bess_p_max_kw < avail_bess_dis_kw:
                    avail_bess_dis_kw = bess_p_max_kw

                if (
                    enable_gen
                    and gen_Forced_steps_remaining == 0
                    and (overload_kw < gen_min_kw)
                    and enable_bess
                    and (avail_bess_dis_kw >= overload_kw)
                ):
                    step_bess_dis = overload_kw
                    removed_e = step_bess_dis * dt_over_eta_dis
                    solar_share = (solar_energy_in_bess_kwh / cur_e_kwh) if cur_e_kwh > 0.0 else 0.0
                    bess_discharge_from_solar_kwh_acc += (step_bess_dis * dt) * solar_share
                    cur_e_kwh -= removed_e
                    if cur_e_kwh < e_min_kwh:
                        cur_e_kwh = e_min_kwh
                    solar_energy_in_bess_kwh -= removed_e * solar_share
                    if solar_energy_in_bess_kwh < 0.0:
                        solar_energy_in_bess_kwh = 0.0
                else:
                    if enable_gen:
                        if gen_Forced_steps_remaining == 0:
                            gen_Forced_steps_remaining = min_run_steps
                        req_gen_kw = overload_kw if overload_kw < gen_rated_kw else gen_rated_kw
                        actual_gen_kw = req_gen_kw if req_gen_kw > gen_min_clamped else gen_min_clamped
                        step_gen_out = actual_gen_kw
                        step_gen_to_load = actual_gen_kw if actual_gen_kw < overload_kw else overload_kw

                        gen_excess_kw = actual_gen_kw - step_gen_to_load
                        if gen_excess_kw > 0.0:
                            if allow_gen_chg and enable_bess and cur_e_kwh < e_max_kwh:
                                room_ac_kw = (e_max_kwh - cur_e_kwh) * inv_dt_eta_chg
                                step_bess_chg_gen = gen_excess_kw
                                if rem_bess_chg_power_kw < step_bess_chg_gen:
                                    step_bess_chg_gen = rem_bess_chg_power_kw
                                if room_ac_kw < step_bess_chg_gen:
                                    step_bess_chg_gen = room_ac_kw
                                cur_e_kwh += step_bess_chg_gen * dt_eta_chg
                                gen_excess_after_bess = gen_excess_kw - step_bess_chg_gen
                            else:
                                gen_excess_after_bess = gen_excess_kw
                            rem_p = p_rem - step_gen_to_load
                            if rem_p > 0.0:
                                extra_to_load = gen_excess_after_bess if gen_excess_after_bess < rem_p else rem_p
                                step_gen_to_load += extra_to_load
                        step_gen_to_bess = step_bess_chg_gen
                        gen_Forced_steps_remaining -= 1
                        if gen_Forced_steps_remaining < 0:
                            gen_Forced_steps_remaining = 0

                    rem_overload_kw = overload_kw - step_gen_to_load
                    if rem_overload_kw < 0.0:
                        rem_overload_kw = 0.0

                    if (
                        rem_overload_kw > 0.001
                        and enable_bess
                        and step_bess_chg_solar == 0.0
                        and step_bess_chg_gen == 0.0
                        and cur_e_kwh > e_min_kwh
                    ):
                        avail_dis_ac_kw = (cur_e_kwh - e_min_kwh) * eta_dis_over_dt
                        step_bess_dis = rem_overload_kw
                        if bess_p_max_kw < step_bess_dis:
                            step_bess_dis = bess_p_max_kw
                        if avail_dis_ac_kw < step_bess_dis:
                            step_bess_dis = avail_dis_ac_kw
                        removed_e = step_bess_dis * dt_over_eta_dis
                        solar_share = (solar_energy_in_bess_kwh / cur_e_kwh) if cur_e_kwh > 0.0 else 0.0
                        bess_discharge_from_solar_kwh_acc += (step_bess_dis * dt) * solar_share
                        cur_e_kwh -= removed_e
                        if cur_e_kwh < e_min_kwh:
                            cur_e_kwh = e_min_kwh
                        solar_energy_in_bess_kwh -= removed_e * solar_share
                        if solar_energy_in_bess_kwh < 0.0:
                            solar_energy_in_bess_kwh = 0.0

        else:
            # --- BELOW OR AT GRID LIMIT (Normal Load Region) ---
            if gen_Forced_steps_remaining > 0 and enable_gen:
                actual_gen_kw = gen_min_clamped
                step_gen_out = actual_gen_kw
                if allow_gen_chg and enable_bess and cur_e_kwh < e_max_kwh:
                    room_ac_kw = (e_max_kwh - cur_e_kwh) * inv_dt_eta_chg
                    step_bess_chg_gen = actual_gen_kw
                    if rem_bess_chg_power_kw < step_bess_chg_gen:
                        step_bess_chg_gen = rem_bess_chg_power_kw
                    if room_ac_kw < step_bess_chg_gen:
                        step_bess_chg_gen = room_ac_kw
                    cur_e_kwh += step_bess_chg_gen * dt_eta_chg
                    rem_gen = actual_gen_kw - step_bess_chg_gen
                else:
                    rem_gen = actual_gen_kw
                step_gen_to_load = rem_gen if rem_gen < p_rem else p_rem
                step_gen_to_bess = step_bess_chg_gen
                gen_Forced_steps_remaining -= 1
                if gen_Forced_steps_remaining < 0:
                    gen_Forced_steps_remaining = 0

            rem_load_for_bess = p_rem - step_gen_to_load
            if rem_load_for_bess < 0.0:
                rem_load_for_bess = 0.0

            # Rule 2: Self-Consumption + Peak Reserve allows discharging stored solar down to e_reserve_kwh
            if (
                effective_rule2_self_cons
                and enable_bess
                and step_bess_chg_solar == 0.0
                and step_bess_chg_gen == 0.0
                and rem_load_for_bess > 0.0
                and cur_e_kwh > e_reserve_kwh
                and solar_energy_in_bess_kwh > 0.0
            ):
                avail_e = cur_e_kwh - e_reserve_kwh
                if solar_energy_in_bess_kwh < avail_e:
                    avail_e = solar_energy_in_bess_kwh
                avail_dis_ac_kw = avail_e * eta_dis_over_dt
                step_bess_dis = rem_load_for_bess
                if bess_p_max_kw < step_bess_dis:
                    step_bess_dis = bess_p_max_kw
                if avail_dis_ac_kw < step_bess_dis:
                    step_bess_dis = avail_dis_ac_kw
                removed_e = step_bess_dis * dt_over_eta_dis
                bess_discharge_from_solar_kwh_acc += step_bess_dis * dt
                cur_e_kwh -= removed_e
                if cur_e_kwh < e_reserve_kwh:
                    cur_e_kwh = e_reserve_kwh
                solar_energy_in_bess_kwh -= removed_e
                if solar_energy_in_bess_kwh < 0.0:
                    solar_energy_in_bess_kwh = 0.0

            # Rule 3: Battery Grid Recharging within Grid Limit
            if (
                allow_grid_chg
                and enable_bess
                and step_bess_dis == 0.0
                and step_bess_chg_gen == 0.0
                and rem_bess_chg_power_kw > 0.0
                and cur_e_kwh < target_grid_e_kwh
            ):
                headroom_kw = grid_limit_kw - (p_rem - step_gen_to_load - step_bess_dis)
                if headroom_kw > 0.0:
                    room_ac_kw = (target_grid_e_kwh - cur_e_kwh) * inv_dt_eta_chg
                    step_bess_chg_grid = headroom_kw
                    if rem_bess_chg_power_kw < step_bess_chg_grid:
                        step_bess_chg_grid = rem_bess_chg_power_kw
                    if room_ac_kw < step_bess_chg_grid:
                        step_bess_chg_grid = room_ac_kw
                    cur_e_kwh += step_bess_chg_grid * dt_eta_chg

        # C. Record Step States
        bess_charge_solar_kw[i] = step_bess_chg_solar
        bess_charge_grid_kw[i] = step_bess_chg_grid
        bess_charge_gen_kw[i] = step_bess_chg_gen
        bess_discharge_kw[i] = step_bess_dis
        bess_energy_kwh[i] = cur_e_kwh
        gen_output_kw[i] = step_gen_out
        gen_to_load_kw[i] = step_gen_to_load
        gen_to_bess_kw[i] = step_gen_to_bess

    return (
        solar_export_kw,
        bess_charge_solar_kw,
        bess_charge_grid_kw,
        bess_charge_gen_kw,
        bess_discharge_kw,
        bess_energy_kwh,
        gen_output_kw,
        gen_to_load_kw,
        gen_to_bess_kw,
        bess_discharge_from_solar_kwh_acc,
    )


def _execute_coupled_dispatch_arrays(
    rem_load_after_solar_kw: np.ndarray,
    solar_surplus_kw: np.ndarray,
    grid_limit_kw: float,
    system_cfg: CombinedSystemConfig,
    rules_cfg: InteractionRulesConfig,
    step_hours: float = 0.25,
    gap_mask: Optional[np.ndarray] = None,
) -> Dict[str, Any]:
    """
    Executes the stateful dispatch kernel for given residual load and solar surplus arrays
    and returns full physical time-series arrays (no Excel/KPI overhead).
    """
    n_steps = len(rem_load_after_solar_kw)
    dt = float(step_hours)
    gaps = (
        np.asarray(gap_mask, dtype=bool)
        if gap_mask is not None and len(gap_mask) == n_steps
        else np.zeros(n_steps, dtype=bool)
    )

    enable_bess = bool(
        system_cfg.enable_battery
        and system_cfg.battery_capacity_kwh > 0.0
        and system_cfg.battery_power_kw > 0.0
    )
    bess_cap_kwh = max(0.0, float(system_cfg.battery_capacity_kwh)) if enable_bess else 0.0
    bess_p_max_kw = max(0.0, float(system_cfg.battery_power_kw)) if enable_bess else 0.0

    min_soc_pct = float(np.clip(system_cfg.min_soc_pct, 0.0, 50.0))
    max_soc_pct = float(np.clip(system_cfg.max_soc_pct, min_soc_pct + 5.0, 100.0))
    e_min_kwh = bess_cap_kwh * (min_soc_pct / 100.0)
    e_max_kwh = bess_cap_kwh * (max_soc_pct / 100.0)

    rte = float(np.clip(system_cfg.round_trip_efficiency_pct, 50.0, 100.0)) / 100.0
    eta_chg = math.sqrt(rte)
    eta_dis = math.sqrt(rte)

    res_soc_pct = float(np.clip(rules_cfg.peak_reserve_soc_pct, min_soc_pct, max_soc_pct))
    effective_rule2_self_cons = (
        rules_cfg.rule2_battery_strategy == "self_consumption_reserve"
        and bool(system_cfg.enable_solar)
    )
    e_reserve_kwh = bess_cap_kwh * (res_soc_pct / 100.0) if effective_rule2_self_cons else e_max_kwh

    allow_grid_chg = (
        rules_cfg.rule3_charging_sources in ("solar_and_grid", "all_sources")
        or not bool(system_cfg.enable_solar)
    )
    allow_gen_chg = rules_cfg.rule3_charging_sources in ("solar_and_generator", "all_sources")
    target_grid_e_kwh = e_reserve_kwh if effective_rule2_self_cons else e_max_kwh

    enable_gen = bool(system_cfg.enable_generator and system_cfg.generator_rated_kw > 0.0)
    gen_rated_kw = max(0.0, float(system_cfg.generator_rated_kw)) if enable_gen else 0.0
    gen_min_kw = gen_rated_kw * (
        float(np.clip(system_cfg.generator_min_load_pct, 0.0, 100.0)) / 100.0
    )
    min_run_steps = max(
        1,
        int(round(max(0, int(system_cfg.gen_min_runtime_minutes)) / max(1.0, dt * 60.0))),
    )
    rule1_battery_first = rules_cfg.rule1_peak_priority == "battery_first"

    init_e_kwh = e_max_kwh if enable_bess else 0.0
    init_solar_e_kwh = 0.0

    (
        solar_export_kw,
        bess_charge_solar_kw,
        bess_charge_grid_kw,
        bess_charge_gen_kw,
        bess_discharge_kw,
        bess_energy_kwh,
        gen_output_kw,
        gen_to_load_kw,
        gen_to_bess_kw,
        bess_discharge_from_solar_kwh_acc,
    ) = _fast_combined_dispatch_kernel(
        rem_load_after_solar_kw=np.ascontiguousarray(rem_load_after_solar_kw, dtype=np.float64),
        solar_surplus_kw=np.ascontiguousarray(solar_surplus_kw, dtype=np.float64),
        grid_limit_kw=float(grid_limit_kw),
        enable_bess=enable_bess,
        bess_p_max_kw=bess_p_max_kw,
        e_min_kwh=e_min_kwh,
        e_max_kwh=e_max_kwh,
        e_reserve_kwh=e_reserve_kwh,
        eta_chg=eta_chg,
        eta_dis=eta_dis,
        enable_gen=enable_gen,
        gen_rated_kw=gen_rated_kw,
        gen_min_kw=gen_min_kw,
        min_run_steps=min_run_steps,
        rule1_battery_first=rule1_battery_first,
        effective_rule2_self_cons=effective_rule2_self_cons,
        allow_grid_chg=allow_grid_chg,
        allow_gen_chg=allow_gen_chg,
        target_grid_e_kwh=target_grid_e_kwh,
        init_e_kwh=init_e_kwh,
        init_solar_e_kwh=init_solar_e_kwh,
        dt=dt,
        is_gap=gaps,
    )

    if enable_bess and bess_cap_kwh > 0.0:
        bess_soc_pct = (bess_energy_kwh / bess_cap_kwh) * 100.0
    else:
        bess_soc_pct = np.zeros(n_steps, dtype=np.float64)

    gen_running_mask = gen_output_kw > 0.001
    slope = float(system_cfg.gen_slope_per_kwh)
    intercept = float(system_cfg.gen_intercept_per_kw_rated)
    gen_fuel_step = np.where(
        gen_running_mask,
        (gen_output_kw * slope + gen_rated_kw * intercept) * dt,
        0.0,
    )

    net_load_served_by_grid = np.maximum(
        0.0, rem_load_after_solar_kw - bess_discharge_kw - gen_to_load_kw
    )
    grid_import_kw = np.where(gaps, 0.0, net_load_served_by_grid + bess_charge_grid_kw)
    unmet_overload_kw = np.where(gaps, 0.0, np.maximum(0.0, grid_import_kw - grid_limit_kw))

    return {
        "solar_export_kw": solar_export_kw,
        "bess_charge_solar_kw": bess_charge_solar_kw,
        "bess_charge_grid_kw": bess_charge_grid_kw,
        "bess_charge_gen_kw": bess_charge_gen_kw,
        "bess_discharge_kw": bess_discharge_kw,
        "bess_energy_kwh": bess_energy_kwh,
        "bess_soc_pct": bess_soc_pct,
        "bess_discharge_from_solar_kwh_acc": float(bess_discharge_from_solar_kwh_acc),
        "gen_output_kw": gen_output_kw,
        "gen_to_load_kw": gen_to_load_kw,
        "gen_to_bess_kw": gen_to_bess_kw,
        "gen_fuel_step": gen_fuel_step,
        "gen_running_mask": gen_running_mask,
        "grid_import_kw": grid_import_kw,
        "unmet_overload_kw": unmet_overload_kw,
    }


def _calibrate_coupled_bess_capacity_kwh(
    p_load: np.ndarray,
    p_solar: np.ndarray,
    grid_limit_kw: float,
    bess_p_max_kw: float,
    system_cfg: CombinedSystemConfig,
    rules_cfg: InteractionRulesConfig,
    hi_hint_kwh: float = 2000.0,
    step_hours: float = 0.25,
    gap_mask: Optional[np.ndarray] = None,
) -> Tuple[float, bool]:
    """
    Binary-searches the exact minimum battery nameplate capacity (kWh) required to reach
    zero grid overload under active Solar, Generator, and Rules 1-3 using the real
    35,040-step dispatch kernel.
    """
    n_steps = len(p_load)
    if n_steps == 0 or bess_p_max_kw <= 0.05:
        return 0.0, True

    solar_direct = np.minimum(p_load, p_solar)
    solar_surplus = np.maximum(0.0, p_solar - solar_direct)
    rem_load_after_solar = np.maximum(0.0, p_load - solar_direct)

    def _is_zero_overload(cap_kwh: float) -> bool:
        probe_cfg = replace(
            system_cfg,
            enable_battery=True,
            battery_capacity_kwh=float(cap_kwh),
            battery_power_kw=float(bess_p_max_kw),
        )
        out = _execute_coupled_dispatch_arrays(
            rem_load_after_solar_kw=rem_load_after_solar,
            solar_surplus_kw=solar_surplus,
            grid_limit_kw=grid_limit_kw,
            system_cfg=probe_cfg,
            rules_cfg=rules_cfg,
            step_hours=step_hours,
            gap_mask=gap_mask,
        )
        return float(np.max(out["unmet_overload_kw"])) <= 0.05

    lo = 1.0
    if _is_zero_overload(lo):
        return 1.0, True

    max_cap_bound = max(500_000.0, float(hi_hint_kwh) * 16.0)
    hi = max(10.0, float(hi_hint_kwh))
    while not _is_zero_overload(hi):
        if hi >= max_cap_bound:
            return float(hi_hint_kwh), False
        lo = hi
        hi *= 2.0

    best_kwh = hi
    for _ in range(16):
        if (hi - lo) < 1.0:
            break
        mid = 0.5 * (lo + hi)
        if _is_zero_overload(mid):
            best_kwh = mid
            hi = mid
        else:
            lo = mid

    return float(math.ceil(best_kwh)), True
def simulate_combined_system_dispatch(
    load_kw: np.ndarray,
    timestamps: pd.DatetimeIndex,
    system_cfg: CombinedSystemConfig,
    rules_cfg: InteractionRulesConfig,
    step_hours: float = 0.25,
    is_gap: Optional[np.ndarray] = None,
) -> CombinedSimulationResult:
    """
    Executes the 35,040-step (15-minute) physical interaction between Grid, Solar, Battery,
    and Generator governed by Rules 1, 2, and 3.
    """
    p_load = np.maximum(0.0, np.nan_to_num(np.asarray(load_kw, dtype=float), nan=0.0))
    n_steps = len(p_load)
    dt = float(step_hours)
    gap_mask = (
        np.asarray(is_gap, dtype=bool)
        if is_gap is not None and len(is_gap) == n_steps
        else np.zeros(n_steps, dtype=bool)
    )
    annual_consumption_kwh = float(np.sum(p_load) * dt)
    orig_peak_kw = float(np.max(p_load)) if n_steps > 0 else 0.0
    avg_load_kw = float(np.mean(p_load[~gap_mask])) if np.any(~gap_mask) else 0.0

    grid_limit_kw = (
        max(0.0, float(system_cfg.grid_limit_kw))
        if getattr(system_cfg, "enable_grid", True)
        else 0.0
    )

    # 1. Solar Profile & Derivation
    azim = 180.0 if system_cfg.latitude >= 0.0 else 0.0
    unit_solar_kw, spec_yield, _ = get_unit_solar_generation_profile(
        latitude=system_cfg.latitude,
        longitude=system_cfg.longitude,
        tilt_deg=system_cfg.tilt_deg,
        azimuth_deg=azim,
        dc_ac_ratio=system_cfg.dc_ac_ratio,
    )
    if len(unit_solar_kw) != n_steps:
        reps = int(math.ceil(n_steps / max(1, len(unit_solar_kw))))
        unit_solar_kw = np.tile(unit_solar_kw, reps)[:n_steps]

    solar_derivation = derive_solar_sizing_and_formula(
        annual_consumption_kwh=annual_consumption_kwh,
        specific_yield_kwh_per_kwp=spec_yield,
        sizing_method=system_cfg.solar_sizing_method,
        direct_kwp=system_cfg.solar_kwp,
        target_share_pct=system_cfg.target_consumption_share_pct,
        panel_wp=system_cfg.panel_wp,
        dc_ac_ratio=system_cfg.dc_ac_ratio,
        enable_solar=system_cfg.enable_solar,
        inverter_ac_limit_kw=getattr(system_cfg, "inverter_ac_limit_kw", 0.0),
        inverter_efficiency_pct=getattr(system_cfg, "inverter_efficiency_pct", 98.0),
    )

    if system_cfg.enable_solar and solar_derivation.installed_kwp > 0.0:
        eff_scale = solar_derivation.inverter_efficiency_pct / 98.0
        solar_gen_kw = unit_solar_kw * solar_derivation.installed_kwp * eff_scale
        if solar_derivation.inverter_ac_kw > 0.0:
            solar_gen_kw = np.minimum(solar_gen_kw, solar_derivation.inverter_ac_kw)
    else:
        solar_gen_kw = np.zeros(n_steps, dtype=float)

    fuel_spec = FUEL_SPECS.get(system_cfg.fuel_type, FUEL_SPECS["Diesel"])
    fuel_unit = str(fuel_spec["unit"])
    enable_bess = bool(
        system_cfg.enable_battery
        and system_cfg.battery_capacity_kwh > 0.0
        and system_cfg.battery_power_kw > 0.0
    )
    bess_cap_kwh = max(0.0, float(system_cfg.battery_capacity_kwh)) if enable_bess else 0.0

    # Pre-allocate Solar Split Arrays & Run Dispatch Arrays Helper
    solar_direct_kw = np.minimum(p_load, solar_gen_kw)
    solar_surplus_kw = np.maximum(0.0, solar_gen_kw - solar_direct_kw)
    rem_load_after_solar_kw = np.maximum(0.0, p_load - solar_direct_kw)

    dispatch_out = _execute_coupled_dispatch_arrays(
        rem_load_after_solar_kw=rem_load_after_solar_kw,
        solar_surplus_kw=solar_surplus_kw,
        grid_limit_kw=grid_limit_kw,
        system_cfg=system_cfg,
        rules_cfg=rules_cfg,
        step_hours=dt,
        gap_mask=gap_mask,
    )
    solar_export_kw = dispatch_out["solar_export_kw"]
    bess_charge_solar_kw = dispatch_out["bess_charge_solar_kw"]
    bess_charge_grid_kw = dispatch_out["bess_charge_grid_kw"]
    bess_charge_gen_kw = dispatch_out["bess_charge_gen_kw"]
    bess_discharge_kw = dispatch_out["bess_discharge_kw"]
    bess_energy_kwh = dispatch_out["bess_energy_kwh"]
    bess_soc_pct = dispatch_out["bess_soc_pct"]
    bess_discharge_from_solar_kwh_acc = dispatch_out["bess_discharge_from_solar_kwh_acc"]
    gen_output_kw = dispatch_out["gen_output_kw"]
    gen_to_load_kw = dispatch_out["gen_to_load_kw"]
    gen_to_bess_kw = dispatch_out["gen_to_bess_kw"]
    gen_fuel_step = dispatch_out["gen_fuel_step"]
    gen_running_mask = dispatch_out["gen_running_mask"]
    grid_import_kw = dispatch_out["grid_import_kw"]
    unmet_overload_kw = dispatch_out["unmet_overload_kw"]

    # 6. Compute Technical KPIs
    diag_before = analyze_grid_violations(p_load, grid_limit_kw, step_hours=dt)
    diag_after = analyze_grid_violations(grid_import_kw, grid_limit_kw, step_hours=dt)

    new_grid_peak_kw = float(np.max(grid_import_kw)) if n_steps > 0 else 0.0
    peak_reduction_kw = max(0.0, orig_peak_kw - new_grid_peak_kw)
    rem_overload_kw = max(0.0, new_grid_peak_kw - grid_limit_kw)
    grid_limit_met = bool(new_grid_peak_kw <= grid_limit_kw + 0.05)

    baseline_overload_kwh = float(diag_before["total_exceedance_energy_kwh"])
    remaining_overload_kwh = float(diag_after["total_exceedance_energy_kwh"])
    overload_eliminated_pct = (
        ((baseline_overload_kwh - remaining_overload_kwh) / baseline_overload_kwh * 100.0)
        if baseline_overload_kwh > 0.01
        else 100.0
    )

    # Energy Totals (kWh)
    solar_total_gen_kwh = float(np.sum(solar_gen_kw) * dt)
    solar_direct_kwh = float(np.sum(solar_direct_kw) * dt)
    solar_export_kwh = float(np.sum(solar_export_kw) * dt)

    bess_chg_solar_kwh = float(np.sum(bess_charge_solar_kw) * dt)
    bess_chg_grid_kwh = float(np.sum(bess_charge_grid_kw) * dt)
    bess_chg_gen_kwh = float(np.sum(bess_charge_gen_kw) * dt)
    bess_dis_total_kwh = float(np.sum(bess_discharge_kw) * dt)
    bess_dis_from_solar_kwh = float(min(bess_dis_total_kwh, bess_discharge_from_solar_kwh_acc))
    bess_losses_kwh = max(
        0.0, (bess_chg_solar_kwh + bess_chg_grid_kwh + bess_chg_gen_kwh) - bess_dis_total_kwh
    )
    bess_cycles = (bess_dis_total_kwh / bess_cap_kwh) if bess_cap_kwh > 0.0 else 0.0

    gen_total_gen_kwh = float(np.sum(gen_output_kw) * dt)
    gen_to_load_kwh = float(np.sum(gen_to_load_kw) * dt)
    gen_to_bess_kwh = float(np.sum(gen_to_bess_kw) * dt)
    gen_curtailed_kwh = max(0.0, gen_total_gen_kwh - gen_to_load_kwh - gen_to_bess_kwh)
    gen_runtime_hours = float(np.sum(gen_running_mask) * dt)
    gen_fuel_total = float(np.sum(gen_fuel_step))
    if n_steps > 0:
        gen_starts = int(
            np.sum((gen_running_mask[1:] == True) & (gen_running_mask[:-1] == False))
        ) + (1 if gen_running_mask[0] else 0)
    else:
        gen_starts = 0

    grid_import_total_kwh = float(np.sum(grid_import_kw) * dt)
    grid_supplied_to_load_kwh = max(0.0, grid_import_total_kwh - bess_chg_grid_kwh)

    # Supply Split Shares (% of Annual Consumption)
    denom = max(1.0, annual_consumption_kwh)
    solar_total_supplied_kwh = solar_direct_kwh + bess_dis_from_solar_kwh
    solar_direct_share_pct = (solar_direct_kwh / denom) * 100.0
    bess_dis_share_pct = (bess_dis_total_kwh / denom) * 100.0
    solar_supply_share_pct = min(100.0, (solar_total_supplied_kwh / denom) * 100.0)
    if (bess_chg_grid_kwh + bess_chg_gen_kwh) > 0:
        gen_via_bess_kwh = (bess_dis_total_kwh - bess_dis_from_solar_kwh) * (
            bess_chg_gen_kwh / max(0.01, bess_chg_grid_kwh + bess_chg_gen_kwh)
        )
        gen_supply_share_pct = min(100.0, ((gen_to_load_kwh + gen_via_bess_kwh) / denom) * 100.0)
    else:
        gen_supply_share_pct = min(100.0, (gen_to_load_kwh / denom) * 100.0)
    grid_supply_share_pct = max(0.0, 100.0 - solar_supply_share_pct - gen_supply_share_pct)

    kpis = CombinedTechnicalKPIs(
        annual_consumption_kwh=round(annual_consumption_kwh, 0),
        original_peak_kw=round(orig_peak_kw, 1),
        average_load_kw=round(avg_load_kw, 1),
        grid_limit_kw=round(grid_limit_kw, 1),
        baseline_overload_kw=round(float(diag_before["overload_peak_kw"]), 1),
        baseline_overload_hours=round(float(diag_before["total_violation_hours"]), 1),
        baseline_overload_kwh=round(baseline_overload_kwh, 1),
        new_grid_peak_kw=round(new_grid_peak_kw, 1),
        peak_reduction_kw=round(peak_reduction_kw, 1),
        grid_limit_met=grid_limit_met,
        remaining_overload_kw=round(rem_overload_kw, 1),
        remaining_overload_hours=round(float(diag_after["total_violation_hours"]), 1),
        remaining_overload_kwh=round(remaining_overload_kwh, 1),
        overload_eliminated_pct=round(overload_eliminated_pct, 1),
        grid_supplied_to_load_kwh=round(grid_supplied_to_load_kwh, 0),
        grid_import_total_kwh=round(grid_import_total_kwh, 0),
        solar_total_generation_kwh=round(solar_total_gen_kwh, 0),
        solar_direct_kwh=round(solar_direct_kwh, 0),
        solar_via_battery_kwh=round(bess_dis_from_solar_kwh, 0),
        solar_total_supplied_kwh=round(solar_total_supplied_kwh, 0),
        solar_export_kwh=round(solar_export_kwh, 0),
        battery_total_discharged_kwh=round(bess_dis_total_kwh, 0),
        battery_charged_from_solar_kwh=round(bess_chg_solar_kwh, 0),
        battery_charged_from_grid_kwh=round(bess_chg_grid_kwh, 0),
        battery_charged_from_gen_kwh=round(bess_chg_gen_kwh, 0),
        battery_losses_kwh=round(bess_losses_kwh, 0),
        battery_equivalent_cycles=round(bess_cycles, 1),
        generator_total_generation_kwh=round(gen_total_gen_kwh, 0),
        generator_to_load_kwh=round(gen_to_load_kwh, 0),
        generator_to_battery_kwh=round(gen_to_bess_kwh, 0),
        generator_curtailed_kwh=round(gen_curtailed_kwh, 0),
        grid_supply_share_pct=round(grid_supply_share_pct, 1),
        solar_supply_share_pct=round(solar_supply_share_pct, 1),
        solar_direct_share_pct=round(solar_direct_share_pct, 1),
        battery_discharge_share_pct=round(bess_dis_share_pct, 1),
        generator_supply_share_pct=round(gen_supply_share_pct, 1),
        generator_runtime_hours=round(gen_runtime_hours, 1),
        generator_starts_count=gen_starts,
        generator_fuel_total=round(gen_fuel_total, 1),
        generator_fuel_unit=fuel_unit,
    )

    summary_df = build_component_summary_table(
        system_cfg=system_cfg,
        solar_derivation=solar_derivation,
        kpis=kpis,
        solar_gen_kw=solar_gen_kw,
        bess_discharge_kw=bess_discharge_kw,
        gen_output_kw=gen_output_kw,
    )

    monthly_df = build_monthly_balance_table(
        timestamps=timestamps,
        load_kw=p_load,
        grid_limit_kw=grid_limit_kw,
        solar_gen_kw=solar_gen_kw,
        solar_direct_kw=solar_direct_kw,
        solar_export_kw=solar_export_kw,
        bess_discharge_kw=bess_discharge_kw,
        gen_output_kw=gen_output_kw,
        gen_running_mask=gen_running_mask,
        gen_fuel_step=gen_fuel_step,
        grid_import_kw=grid_import_kw,
        unmet_overload_kw=unmet_overload_kw,
        step_hours=dt,
    )

    return CombinedSimulationResult(
        system_config=system_cfg,
        rules_config=rules_cfg,
        solar_derivation=solar_derivation,
        kpis=kpis,
        timestamps=timestamps,
        load_kw=p_load,
        solar_gen_kw=solar_gen_kw,
        solar_direct_kw=solar_direct_kw,
        solar_surplus_kw=solar_surplus_kw,
        solar_export_kw=solar_export_kw,
        bess_charge_solar_kw=bess_charge_solar_kw,
        bess_charge_grid_kw=bess_charge_grid_kw,
        bess_charge_gen_kw=bess_charge_gen_kw,
        bess_discharge_kw=bess_discharge_kw,
        bess_soc_pct=bess_soc_pct,
        bess_energy_kwh=bess_energy_kwh,
        gen_output_kw=gen_output_kw,
        gen_to_load_kw=gen_to_load_kw,
        gen_to_bess_kw=gen_to_bess_kw,
        gen_fuel_step=gen_fuel_step,
        gen_running_mask=gen_running_mask,
        grid_import_kw=grid_import_kw,
        unmet_overload_kw=unmet_overload_kw,
        is_gap=gap_mask,
        summary_table_df=summary_df,
        monthly_balance_df=monthly_df,
    )
