"""
Coordinated 4-source system mix recommendations, component utilization diagnostics,
and physical summary & 12-month balance tables.
"""

from dataclasses import replace
from typing import Optional
import math
import numpy as np
import pandas as pd

from .models_and_presets import (
    MONTH_NAMES_SHORT,
    MIX_STRATEGY_OPTIONS,
    CombinedSystemConfig,
    InteractionRulesConfig,
    SolarDerivationInfo,
    CombinedTechnicalKPIs,
    CombinedSimulationResult,
    CoordinatedMixRecommendation,
    SystemUtilizationDiagnostics,
)
from .solar_and_sizing import (
    get_unit_solar_generation_profile,
    derive_solar_sizing_and_formula,
)

def compute_coordinated_mix_sizing(
    load_kw: np.ndarray,
    system_cfg: CombinedSystemConfig,
    rules_cfg: InteractionRulesConfig,
    strategy_key: str,
    target_grid_limit_kw: float,
    solar_share_pct: float = 60.0,
    solar_enabled: bool = True,
    bess_duration_hours: float = 2.0,
    gen_cover_remaining_peaks: bool = True,
    step_hours: float = 0.25,
    is_gap: Optional[np.ndarray] = None,
) -> CoordinatedMixRecommendation:
    """
    Computes a coordinated 4-source sizing recommendation across Grid, Solar, Battery,
    and Generator, evaluating all KPIs over the full 35,040-step coupled dispatch kernel.
    """
    from .dispatch_simulation import (
        _calibrate_coupled_bess_capacity_kwh,
        _execute_coupled_dispatch_arrays,
    )

    p_load = np.maximum(0.0, np.nan_to_num(np.asarray(load_kw, dtype=float), nan=0.0))
    n_steps = len(p_load)
    dt = float(step_hours)
    gap_mask = (
        np.asarray(is_gap, dtype=bool)
        if is_gap is not None and len(is_gap) == n_steps
        else np.zeros(n_steps, dtype=bool)
    )
    grid_limit = max(0.0, float(target_grid_limit_kw))

    eff_solar_enabled = bool(solar_enabled and float(solar_share_pct) > 0.0)
    eff_solar_share = float(np.clip(solar_share_pct, 0.0, 200.0)) if eff_solar_enabled else 0.0

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

    ann_kwh = float(np.sum(p_load) * dt)
    solar_deriv = derive_solar_sizing_and_formula(
        annual_consumption_kwh=ann_kwh,
        specific_yield_kwh_per_kwp=spec_yield,
        sizing_method="target_share_pct",
        direct_kwp=system_cfg.solar_kwp,
        target_share_pct=eff_solar_share,
        panel_wp=system_cfg.panel_wp,
        dc_ac_ratio=system_cfg.dc_ac_ratio,
        enable_solar=eff_solar_enabled,
        inverter_ac_limit_kw=system_cfg.inverter_ac_limit_kw,
        inverter_efficiency_pct=system_cfg.inverter_efficiency_pct,
    )
    if eff_solar_enabled and solar_deriv.installed_kwp > 0.0:
        eff_scale = solar_deriv.inverter_efficiency_pct / 98.0
        p_solar = unit_solar_kw * solar_deriv.installed_kwp * eff_scale
        if solar_deriv.inverter_ac_kw > 0.0:
            p_solar = np.minimum(p_solar, solar_deriv.inverter_ac_kw)
    else:
        p_solar = np.zeros(n_steps, dtype=float)

    solar_direct = np.minimum(p_load, p_solar)
    p_after_solar = np.maximum(0.0, p_load - solar_direct)
    p_surplus = np.maximum(0.0, p_solar - solar_direct)
    over_after_solar = np.maximum(0.0, p_after_solar - grid_limit)
    peak_overload_kw = float(np.max(over_after_solar)) if n_steps > 0 else 0.0

    min_soc = float(np.clip(system_cfg.min_soc_pct, 0.0, 50.0))
    max_soc = float(np.clip(system_cfg.max_soc_pct, min_soc + 5.0, 100.0))
    full_dod = max(0.05, (max_soc - min_soc) / 100.0)

    strategy_key_clean = strategy_key if strategy_key in MIX_STRATEGY_OPTIONS else "hybrid_2h"
    strategy_label = MIX_STRATEGY_OPTIONS[strategy_key_clean]

    bat_en = False
    bat_kw = 0.0
    bat_kwh = 0.0
    gen_en = False
    gen_kw = 0.0
    rationale = ""

    base_solar_cfg = replace(
        system_cfg,
        enable_grid=True,
        grid_limit_kw=grid_limit,
        enable_solar=eff_solar_enabled,
        solar_sizing_method="target_share_pct",
        target_consumption_share_pct=eff_solar_share,
        solar_kwp=solar_deriv.installed_kwp,
    )

    if strategy_key_clean == "pure_generator_100":
        gen_en = peak_overload_kw > 0.05
        gen_kw = round(math.ceil(peak_overload_kw * 10.0) / 10.0, 1) if gen_en else 0.0
        rationale = (
            f"Generator-only peak shaving ({gen_kw:.1f} kW) covers 100% of net overload above "
            f"{grid_limit:.0f} kW; no battery installed."
        )
    elif strategy_key_clean == "pure_battery_100":
        bat_en = peak_overload_kw > 0.05
        if bat_en:
            bat_kw = round(math.ceil(peak_overload_kw * 10.0) / 10.0, 1)
            no_gen_cfg = replace(base_solar_cfg, enable_generator=False, generator_rated_kw=0.0)
            cal_kwh, _ = _calibrate_coupled_bess_capacity_kwh(
                p_load=p_load,
                p_solar=p_solar,
                grid_limit_kw=grid_limit,
                bess_p_max_kw=bat_kw,
                system_cfg=no_gen_cfg,
                rules_cfg=rules_cfg,
                hi_hint_kwh=max(500.0, bat_kw * 6.0),
                step_hours=dt,
                gap_mask=gap_mask,
            )
            bat_kwh = float(math.ceil(cal_kwh))
        rationale = (
            f"Battery-only zero-overload sizing ({bat_kw:.1f} kW / {bat_kwh:,.0f} kWh) covers "
            "every single and multi-day peak cluster without a generator."
        )
    else:
        if strategy_key_clean == "hybrid_2h":
            eff_dur_hrs = 2.0
        elif strategy_key_clean == "hybrid_4h":
            eff_dur_hrs = 4.0
        else:
            eff_dur_hrs = max(0.5, float(bess_duration_hours))

        if strategy_key_clean == "custom" and not gen_cover_remaining_peaks:
            bat_en = bool(system_cfg.enable_battery and system_cfg.battery_capacity_kwh > 0.0)
            bat_kw = float(system_cfg.battery_power_kw) if bat_en else 0.0
            bat_kwh = float(system_cfg.battery_capacity_kwh) if bat_en else 0.0
            gen_en = bool(system_cfg.enable_generator and system_cfg.generator_rated_kw > 0.0)
            gen_kw = float(system_cfg.generator_rated_kw) if gen_en else 0.0
        elif strategy_key_clean == "solar_buffer_gen_peak":
            pos_surplus = p_surplus[p_surplus > 0.1]
            p95_surplus = float(np.percentile(pos_surplus, 95)) if pos_surplus.size > 0 else 0.0
            if peak_overload_kw > 0.05:
                bat_kw = round(
                    max(min(peak_overload_kw, max(p95_surplus, peak_overload_kw * 0.40)), 1.0),
                    1,
                )
            elif p95_surplus > 0.5:
                bat_kw = round(p95_surplus, 1)
            else:
                bat_kw = 0.0
            bat_en = bat_kw > 0.05
            bat_kwh = float(math.ceil((bat_kw * eff_dur_hrs) / full_dod)) if bat_en else 0.0
        else:
            # hybrid_2h, hybrid_4h, or custom with manual battery + auto generator
            if strategy_key_clean == "custom":
                bat_en = bool(
                    system_cfg.enable_battery
                    and system_cfg.battery_capacity_kwh > 0.0
                    and system_cfg.battery_power_kw > 0.0
                )
                bat_kw = float(system_cfg.battery_power_kw) if bat_en else 0.0
                bat_kwh = float(system_cfg.battery_capacity_kwh) if bat_en else 0.0
            else:
                bat_en = peak_overload_kw > 0.05
                if bat_en:
                    bat_kw = round(math.ceil(peak_overload_kw * 10.0) / 10.0, 1)
                    bat_kwh = float(math.ceil((bat_kw * eff_dur_hrs) / full_dod))

        # Auto-size Generator to eliminate any residual overload left by the compact Battery
        should_auto_gen = (
            gen_cover_remaining_peaks and peak_overload_kw > 0.05
        )
        if should_auto_gen:
            probe_no_gen = replace(
                base_solar_cfg,
                enable_battery=bat_en,
                battery_power_kw=bat_kw,
                battery_capacity_kwh=bat_kwh,
                enable_generator=False,
                generator_rated_kw=0.0,
            )
            out_no_gen = _execute_coupled_dispatch_arrays(
                rem_load_after_solar_kw=p_after_solar,
                solar_surplus_kw=p_surplus,
                grid_limit_kw=grid_limit,
                system_cfg=probe_no_gen,
                rules_cfg=rules_cfg,
                step_hours=dt,
                gap_mask=gap_mask,
            )
            max_rem_ov = float(np.max(out_no_gen["unmet_overload_kw"])) if n_steps > 0 else 0.0
            if max_rem_ov > 0.05:
                gen_en = True
                gen_kw = round(math.ceil(max_rem_ov * 10.0) / 10.0, 1)
                # Verify zero overload under Generator min-load / min-runtime interaction
                probe_with_gen = replace(probe_no_gen, enable_generator=True, generator_rated_kw=gen_kw)
                out_chk = _execute_coupled_dispatch_arrays(
                    rem_load_after_solar_kw=p_after_solar,
                    solar_surplus_kw=p_surplus,
                    grid_limit_kw=grid_limit,
                    system_cfg=probe_with_gen,
                    rules_cfg=rules_cfg,
                    step_hours=dt,
                    gap_mask=gap_mask,
                )
                rem2 = float(np.max(out_chk["unmet_overload_kw"])) if n_steps > 0 else 0.0
                if rem2 > 0.05:
                    gen_kw = round(
                        math.ceil(max(peak_overload_kw, gen_kw + rem2) * 10.0) / 10.0,
                        1,
                    )
            else:
                gen_en = False
                gen_kw = 0.0

    final_cfg = replace(
        base_solar_cfg,
        enable_battery=bat_en,
        battery_power_kw=bat_kw,
        battery_capacity_kwh=bat_kwh,
        enable_generator=gen_en,
        generator_rated_kw=gen_kw,
    )
    out_final = _execute_coupled_dispatch_arrays(
        rem_load_after_solar_kw=p_after_solar,
        solar_surplus_kw=p_surplus,
        grid_limit_kw=grid_limit,
        system_cfg=final_cfg,
        rules_cfg=rules_cfg,
        step_hours=dt,
        gap_mask=gap_mask,
    )

    if bat_en and bat_kwh > 0.0 and np.any(~gap_mask):
        est_min_soc = round(float(np.min(out_final["bess_soc_pct"][~gap_mask])), 1)
    else:
        est_min_soc = 0.0
    est_cycles = round(
        float(np.sum(out_final["bess_discharge_kw"]) * dt / max(1e-6, bat_kwh))
        if (bat_en and bat_kwh > 0.0)
        else 0.0,
        1,
    )
    est_gen_hrs = round(float(np.sum(out_final["gen_running_mask"]) * dt), 1)
    est_gen_mwh = round(float(np.sum(out_final["gen_output_kw"]) * dt / 1000.0), 2)
    est_unmet_hrs = round(float(np.sum(out_final["unmet_overload_kw"] > 0.05) * dt), 1)

    if not rationale:
        if bat_en and gen_en:
            rationale = (
                f"Compact {bat_kw:.1f} kW / {bat_kwh:,.0f} kWh Battery ({est_cycles:.1f} cyc/yr) "
                f"covers short daily peaks and Solar surplus, while the {gen_kw:.1f} kW Generator "
                f"covers extended peak clusters ({est_gen_hrs:.1f} hrs/yr) for {est_unmet_hrs:.1f}h overload."
            )
        elif bat_en:
            rationale = (
                f"Battery ({bat_kw:.1f} kW / {bat_kwh:,.0f} kWh, {est_cycles:.1f} cyc/yr) "
                f"covers all peaks without starting a generator ({est_unmet_hrs:.1f}h overload)."
            )
        elif gen_en:
            rationale = (
                f"Generator ({gen_kw:.1f} kW, {est_gen_hrs:.1f} hrs/yr) handles peaks above "
                f"{grid_limit:.0f} kW ({est_unmet_hrs:.1f}h overload)."
            )
        else:
            rationale = (
                f"Grid Limit ({grid_limit:.0f} kW) plus Solar ({eff_solar_share:.0f}%) already "
                "covers peak demand with zero overload."
            )

    return CoordinatedMixRecommendation(
        strategy_key=strategy_key_clean,
        strategy_label=strategy_label,
        grid_limit_kw=round(grid_limit, 1),
        solar_enabled=eff_solar_enabled,
        solar_share_pct=round(eff_solar_share, 1),
        solar_kwp=round(solar_deriv.installed_kwp, 1) if eff_solar_enabled else 0.0,
        battery_enabled=bat_en,
        battery_capacity_kwh=round(bat_kwh, 0),
        battery_power_kw=round(bat_kw, 1),
        generator_enabled=gen_en,
        generator_rated_kw=round(gen_kw, 1),
        est_battery_min_soc_pct=est_min_soc,
        est_battery_cycles=est_cycles,
        est_generator_runtime_hrs=est_gen_hrs,
        est_generator_energy_mwh=est_gen_mwh,
        est_unmet_overload_hrs=est_unmet_hrs,
        rationale_text=rationale,
    )
def compute_system_utilization_diagnostics(
    sim_res: CombinedSimulationResult,
) -> SystemUtilizationDiagnostics:
    """
    Computes exact annual supply shares (kWh / %) and physical utilization rates (0-100%)
    for Solar, Battery storage (kWh), Battery inverter (kW), Generator, and Grid connection.
    """
    cfg = sim_res.system_config
    kpis = sim_res.kpis
    solar_deriv = sim_res.solar_derivation

    ann_load = max(0.0, float(kpis.annual_consumption_kwh))
    solar_direct_kwh = max(0.0, float(kpis.solar_direct_kwh))
    battery_discharge_kwh = max(0.0, float(kpis.battery_total_discharged_kwh))
    generator_direct_kwh = max(0.0, float(kpis.generator_to_load_kwh))
    grid_direct_kwh = max(
        0.0,
        ann_load - solar_direct_kwh - battery_discharge_kwh - generator_direct_kwh,
    )

    denom = max(1.0, grid_direct_kwh + solar_direct_kwh + battery_discharge_kwh + generator_direct_kwh)
    grid_direct_pct = (grid_direct_kwh / denom) * 100.0 if ann_load > 0 else 0.0
    solar_direct_pct = (solar_direct_kwh / denom) * 100.0 if ann_load > 0 else 0.0
    battery_discharge_pct = (battery_discharge_kwh / denom) * 100.0 if ann_load > 0 else 0.0
    generator_direct_pct = (generator_direct_kwh / denom) * 100.0 if ann_load > 0 else 0.0

    solar_via_battery_kwh = min(battery_discharge_kwh, max(0.0, float(kpis.solar_via_battery_kwh)))
    grid_or_gen_via_battery_kwh = max(0.0, battery_discharge_kwh - solar_via_battery_kwh)

    gaps = getattr(sim_res, "is_gap", None)
    p_load = np.asarray(sim_res.load_kw, dtype=float)
    p_solar_dir = np.asarray(sim_res.solar_direct_kw, dtype=float)
    p_bess_dis = np.asarray(sim_res.bess_discharge_kw, dtype=float)
    p_bess_chg = (
        np.asarray(sim_res.bess_charge_solar_kw, dtype=float)
        + np.asarray(sim_res.bess_charge_grid_kw, dtype=float)
        + np.asarray(sim_res.bess_charge_gen_kw, dtype=float)
    )
    p_gen = np.asarray(sim_res.gen_output_kw, dtype=float)

    grid_lim = float(cfg.grid_limit_kw) if cfg.enable_grid else 0.0
    peak_mask = p_load > grid_lim
    if np.any(peak_mask) and p_solar_dir.size == peak_mask.size:
        solar_peak_contrib_kw = float(np.max(p_solar_dir[peak_mask]))
    elif p_solar_dir.size > 0:
        solar_peak_contrib_kw = float(np.max(p_solar_dir))
    else:
        solar_peak_contrib_kw = 0.0

    bess_peak_discharged_kw = float(np.max(p_bess_dis)) if p_bess_dis.size > 0 else 0.0
    bess_peak_charged_kw = float(np.max(p_bess_chg)) if p_bess_chg.size > 0 else 0.0
    gen_peak_used_kw = float(np.max(p_gen)) if p_gen.size > 0 else 0.0

    # Battery storage utilization
    bess_enabled = bool(cfg.enable_battery and cfg.battery_capacity_kwh > 0.0 and cfg.battery_power_kw > 0.0)
    if bess_enabled:
        bess_installed_kwh = float(cfg.battery_capacity_kwh)
        min_soc_cfg = float(np.clip(cfg.min_soc_pct, 0.0, 50.0))
        max_soc_cfg = float(np.clip(cfg.max_soc_pct, min_soc_cfg + 5.0, 100.0))
        usable_dod = max(0.05, (max_soc_cfg - min_soc_cfg) / 100.0)
        bess_usable_window_kwh = bess_installed_kwh * usable_dod

        soc_arr = np.asarray(sim_res.bess_soc_pct, dtype=float)
        valid_soc = (
            soc_arr[~np.asarray(gaps, dtype=bool)]
            if gaps is not None and len(gaps) == len(soc_arr) and np.any(~np.asarray(gaps, dtype=bool))
            else soc_arr
        )
        if valid_soc.size > 0:
            raw_min_soc = float(np.min(valid_soc))
            raw_max_soc = float(np.max(valid_soc))
        else:
            raw_min_soc = max_soc_cfg
            raw_max_soc = max_soc_cfg

        bess_min_soc_reached_pct = round(raw_min_soc, 1)
        bess_max_soc_reached_pct = round(raw_max_soc, 1)
        depth_pct = max(0.0, raw_max_soc - raw_min_soc)
        usable_win_round = round(bess_usable_window_kwh, 1)
        used_depth_round = round(
            min(bess_usable_window_kwh, bess_installed_kwh * (depth_pct / 100.0)),
            1,
        )
        bess_max_depth_used_kwh = min(usable_win_round, used_depth_round)
        bess_unused_usable_kwh = round(max(0.0, usable_win_round - bess_max_depth_used_kwh), 1)
        bess_usable_window_kwh = usable_win_round
        bess_capacity_utilization_pct = (
            min(100.0, (bess_max_depth_used_kwh / bess_usable_window_kwh) * 100.0)
            if bess_usable_window_kwh > 0.0
            else 0.0
        )
        if bess_max_depth_used_kwh > 0.1:
            right_raw = float(math.ceil((bess_max_depth_used_kwh * 1.10) / usable_dod))
            bess_right_sized_kwh = min(bess_installed_kwh, max(10.0, right_raw))
        else:
            bess_right_sized_kwh = 0.0

        bess_installed_kw = float(cfg.battery_power_kw)
        bess_peak_active_kw = max(bess_peak_discharged_kw, bess_peak_charged_kw)
        bess_power_utilization_pct = (
            min(100.0, (bess_peak_active_kw / bess_installed_kw) * 100.0)
            if bess_installed_kw > 0.0
            else 0.0
        )
    else:
        bess_installed_kwh = 0.0
        bess_usable_window_kwh = 0.0
        bess_min_soc_reached_pct = 0.0
        bess_max_soc_reached_pct = 0.0
        bess_max_depth_used_kwh = 0.0
        bess_unused_usable_kwh = 0.0
        bess_capacity_utilization_pct = 0.0
        bess_right_sized_kwh = 0.0
        bess_installed_kw = 0.0
        bess_power_utilization_pct = 0.0

    # Solar utilization
    solar_enabled = bool(cfg.enable_solar and solar_deriv.installed_kwp > 0.0)
    solar_installed_kwp = float(solar_deriv.installed_kwp) if solar_enabled else 0.0
    solar_total_potential_kwh = float(kpis.solar_total_generation_kwh) if solar_enabled else 0.0
    solar_used_direct_kwh = float(kpis.solar_direct_kwh) if solar_enabled else 0.0
    solar_used_via_battery_kwh = float(kpis.solar_via_battery_kwh) if solar_enabled else 0.0
    solar_exported_unused_kwh = float(kpis.solar_export_kwh) if solar_enabled else 0.0
    solar_utilization_pct = (
        min(
            100.0,
            ((solar_used_direct_kwh + solar_used_via_battery_kwh) / solar_total_potential_kwh) * 100.0,
        )
        if solar_enabled and solar_total_potential_kwh > 0.0
        else 0.0
    )

    # Generator utilization
    gen_enabled = bool(cfg.enable_generator and cfg.generator_rated_kw > 0.0)
    gen_rated_kw = float(cfg.generator_rated_kw) if gen_enabled else 0.0
    gen_power_utilization_pct = (
        min(100.0, (gen_peak_used_kw / gen_rated_kw) * 100.0)
        if gen_enabled and gen_rated_kw > 0.0
        else 0.0
    )

    # Grid connection utilization
    grid_peak_import_kw = float(kpis.new_grid_peak_kw)
    grid_utilization_pct = (
        min(100.0, (grid_peak_import_kw / grid_lim) * 100.0)
        if grid_lim > 0.0
        else 0.0
    )

    return SystemUtilizationDiagnostics(
        annual_consumption_kwh=round(ann_load, 1),
        grid_direct_kwh=round(grid_direct_kwh, 1),
        grid_direct_pct=round(grid_direct_pct, 1),
        solar_direct_kwh=round(solar_direct_kwh, 1),
        solar_direct_pct=round(solar_direct_pct, 1),
        battery_discharge_kwh=round(battery_discharge_kwh, 1),
        battery_discharge_pct=round(battery_discharge_pct, 1),
        solar_via_battery_kwh=round(solar_via_battery_kwh, 1),
        grid_or_gen_via_battery_kwh=round(grid_or_gen_via_battery_kwh, 1),
        generator_direct_kwh=round(generator_direct_kwh, 1),
        generator_direct_pct=round(generator_direct_pct, 1),
        unmet_overload_kwh=round(float(kpis.remaining_overload_kwh), 1),
        grid_peak_shaved_kw=round(float(kpis.peak_reduction_kw), 1),
        solar_peak_contribution_kw=round(solar_peak_contrib_kw, 1),
        bess_peak_discharged_kw=round(bess_peak_discharged_kw, 1),
        gen_peak_used_kw=round(gen_peak_used_kw, 1),
        bess_enabled=bess_enabled,
        bess_installed_kwh=round(bess_installed_kwh, 1),
        bess_usable_window_kwh=round(bess_usable_window_kwh, 1),
        bess_min_soc_reached_pct=bess_min_soc_reached_pct,
        bess_max_soc_reached_pct=bess_max_soc_reached_pct,
        bess_max_depth_used_kwh=round(bess_max_depth_used_kwh, 1),
        bess_unused_usable_kwh=round(bess_unused_usable_kwh, 1),
        bess_capacity_utilization_pct=round(bess_capacity_utilization_pct, 1),
        bess_right_sized_kwh=min(round(bess_installed_kwh, 1), round(bess_right_sized_kwh, 0)),
        bess_cycles_per_yr=round(float(kpis.battery_equivalent_cycles), 1),
        bess_installed_kw=round(bess_installed_kw, 1),
        bess_peak_charged_kw=round(bess_peak_charged_kw, 1),
        bess_power_utilization_pct=round(bess_power_utilization_pct, 1),
        solar_enabled=solar_enabled,
        solar_installed_kwp=round(solar_installed_kwp, 1),
        solar_total_potential_kwh=round(solar_total_potential_kwh, 1),
        solar_used_direct_kwh=round(solar_used_direct_kwh, 1),
        solar_used_via_battery_kwh=round(solar_used_via_battery_kwh, 1),
        solar_exported_unused_kwh=round(solar_exported_unused_kwh, 1),
        solar_utilization_pct=round(solar_utilization_pct, 1),
        gen_enabled=gen_enabled,
        gen_rated_kw=round(gen_rated_kw, 1),
        gen_power_utilization_pct=round(gen_power_utilization_pct, 1),
        gen_runtime_hours=round(float(kpis.generator_runtime_hours), 1),
        gen_starts_count=int(kpis.generator_starts_count),
        gen_energy_kwh=round(float(kpis.generator_total_generation_kwh), 1),
        grid_limit_kw=round(grid_lim, 1),
        grid_peak_import_kw=round(grid_peak_import_kw, 1),
        grid_utilization_pct=round(grid_utilization_pct, 1),
    )


# ======================================================================================
# 5. Summary Tables & Monthly Aggregations
# ======================================================================================

def build_component_summary_table(
    system_cfg: CombinedSystemConfig,
    solar_derivation: SolarDerivationInfo,
    kpis: CombinedTechnicalKPIs,
    solar_gen_kw: np.ndarray,
    bess_discharge_kw: np.ndarray,
    gen_output_kw: np.ndarray,
) -> pd.DataFrame:
    """
    Builds the physical/technical Component & Scenario Summary Table.
    Rows: Grid, Solar, Battery, Generator, Combined system, Current situation.
    """
    denom = max(1.0, kpis.annual_consumption_kwh)
    grid_direct_share = (kpis.grid_supplied_to_load_kwh / denom) * 100.0
    solar_direct_share = (kpis.solar_direct_kwh / denom) * 100.0
    bess_dis_share = (kpis.battery_total_discharged_kwh / denom) * 100.0
    gen_load_share = (kpis.generator_to_load_kwh / denom) * 100.0

    rows = [
        {
            "Component": "Grid",
            "Status": "Active",
            "Installed Size": f"{kpis.grid_limit_kw:,.0f} kW limit",
            "Energy Supplied (kWh/year)": f"{kpis.grid_supplied_to_load_kwh:,.0f} kWh (Total Import: {kpis.grid_import_total_kwh:,.0f} kWh)",
            "Share of Consumption (%)": f"{grid_direct_share:.1f}%",
            "Peak Power (kW)": f"{kpis.new_grid_peak_kw:,.1f} kW",
            "Technical Operation": (
                f"Limit Met ({kpis.remaining_overload_hours:.1f} hrs overload)"
                if kpis.grid_limit_met
                else f"Overload: {kpis.remaining_overload_hours:.1f} hrs ({kpis.remaining_overload_kwh:,.0f} kWh)"
            ),
        },
        {
            "Component": "Solar",
            "Status": "Active" if system_cfg.enable_solar else "Disabled",
            "Installed Size": f"{solar_derivation.installed_kwp:,.1f} kWp ({solar_derivation.panel_count:,} panels)" if system_cfg.enable_solar else "0.0 kWp",
            "Energy Supplied (kWh/year)": (
                f"{kpis.solar_direct_kwh:,.0f} kWh direct (+ {kpis.solar_via_battery_kwh:,.0f} kWh via Battery)"
                if system_cfg.enable_solar
                else "0 kWh"
            ),
            "Share of Consumption (%)": f"{solar_direct_share:.1f}% direct ({kpis.solar_supply_share_pct:.1f}% total)" if system_cfg.enable_solar else "0.0%",
            "Peak Power (kW)": f"{float(np.max(solar_gen_kw)):,.1f} kW" if (system_cfg.enable_solar and len(solar_gen_kw) > 0) else "0.0 kW",
            "Technical Operation": (
                f"Total Gen: {kpis.solar_total_generation_kwh:,.0f} kWh | Export: {kpis.solar_export_kwh:,.0f} kWh"
                if system_cfg.enable_solar
                else "Disabled"
            ),
        },
        {
            "Component": "Battery",
            "Status": "Active" if system_cfg.enable_battery else "Disabled",
            "Installed Size": f"{system_cfg.battery_capacity_kwh:,.0f} kWh / {system_cfg.battery_power_kw:,.0f} kW" if system_cfg.enable_battery else "0 kWh / 0 kW",
            "Energy Supplied (kWh/year)": f"{kpis.battery_total_discharged_kwh:,.0f} kWh discharged" if system_cfg.enable_battery else "0 kWh",
            "Share of Consumption (%)": f"{bess_dis_share:.1f}%" if system_cfg.enable_battery else "0.0%",
            "Peak Power (kW)": f"{float(np.max(bess_discharge_kw)):,.1f} kW" if (system_cfg.enable_battery and len(bess_discharge_kw) > 0) else "0.0 kW",
            "Technical Operation": (
                f"{kpis.battery_equivalent_cycles:.1f} cycles/yr | Chg (Solar: {kpis.battery_charged_from_solar_kwh:,.0f}, Grid: {kpis.battery_charged_from_grid_kwh:,.0f}, Gen: {kpis.battery_charged_from_gen_kwh:,.0f} kWh)"
                if system_cfg.enable_battery
                else "Disabled"
            ),
        },
        {
            "Component": "Generator",
            "Status": "Active" if system_cfg.enable_generator else "Disabled",
            "Installed Size": f"{system_cfg.generator_rated_kw:,.0f} kW ({system_cfg.fuel_type}, Min {system_cfg.generator_min_load_pct:.0f}%)" if system_cfg.enable_generator else "0 kW",
            "Energy Supplied (kWh/year)": f"{kpis.generator_to_load_kwh:,.0f} kWh (+ {kpis.generator_to_battery_kwh:,.0f} kWh to Battery)" if system_cfg.enable_generator else "0 kWh",
            "Share of Consumption (%)": f"{gen_load_share:.1f}%" if system_cfg.enable_generator else "0.0%",
            "Peak Power (kW)": f"{float(np.max(gen_output_kw)):,.1f} kW" if (system_cfg.enable_generator and len(gen_output_kw) > 0) else "0.0 kW",
            "Technical Operation": (
                f"{kpis.generator_runtime_hours:,.1f} hrs/yr ({kpis.generator_starts_count} starts) | Fuel: {kpis.generator_fuel_total:,.0f} {kpis.generator_fuel_unit}"
                if system_cfg.enable_generator
                else "Disabled"
            ),
        },
        {
            "Component": "Combined system",
            "Status": "Active",
            "Installed Size": (
                f"Grid {kpis.grid_limit_kw:,.0f} kW + "
                f"Solar {solar_derivation.installed_kwp if system_cfg.enable_solar else 0.0:,.1f} kWp + "
                f"Battery {system_cfg.battery_capacity_kwh if system_cfg.enable_battery else 0.0:,.0f} kWh + "
                f"Generator {system_cfg.generator_rated_kw if system_cfg.enable_generator else 0.0:,.0f} kW"
            ),
            "Energy Supplied (kWh/year)": f"{kpis.annual_consumption_kwh:,.0f} kWh",
            "Share of Consumption (%)": "100.0%",
            "Peak Power (kW)": f"Grid Peak: {kpis.new_grid_peak_kw:,.1f} kW (-{kpis.peak_reduction_kw:,.1f} kW)",
            "Technical Operation": (
                f"Remaining Overload: {kpis.remaining_overload_hours:.1f} hrs ({kpis.remaining_overload_kwh:,.0f} kWh) | "
                f"Eliminated: {kpis.overload_eliminated_pct:.1f}%"
            ),
        },
        {
            "Component": "Current situation",
            "Status": "Baseline",
            "Installed Size": f"Grid Limit {kpis.grid_limit_kw:,.0f} kW (Grid only)",
            "Energy Supplied (kWh/year)": f"{kpis.annual_consumption_kwh:,.0f} kWh (100% Grid)",
            "Share of Consumption (%)": "100.0%",
            "Peak Power (kW)": f"Grid Peak: {kpis.original_peak_kw:,.1f} kW",
            "Technical Operation": (
                f"Baseline Overload: {kpis.baseline_overload_hours:.1f} hrs ({kpis.baseline_overload_kwh:,.0f} kWh)"
            ),
        },
    ]

    return pd.DataFrame(rows)


def build_monthly_balance_table(
    timestamps: pd.DatetimeIndex,
    load_kw: np.ndarray,
    grid_limit_kw: float,
    solar_gen_kw: np.ndarray,
    solar_direct_kw: np.ndarray,
    solar_export_kw: np.ndarray,
    bess_discharge_kw: np.ndarray,
    gen_output_kw: np.ndarray,
    gen_running_mask: np.ndarray,
    gen_fuel_step: np.ndarray,
    grid_import_kw: np.ndarray,
    unmet_overload_kw: np.ndarray,
    step_hours: float = 0.25,
) -> pd.DataFrame:
    """Builds the 12-month technical energy & peak balance table via vectorized np.bincount & np.maximum.at."""
    if len(load_kw) == 0:
        return pd.DataFrame()

    m_idx = timestamps.month.to_numpy(dtype=np.intp) - 1
    counts = np.bincount(m_idx, minlength=12)

    cons_m = np.bincount(m_idx, weights=load_kw, minlength=12) * step_hours
    s_gen_m = np.bincount(m_idx, weights=solar_gen_kw, minlength=12) * step_hours
    s_dir_m = np.bincount(m_idx, weights=solar_direct_kw, minlength=12) * step_hours
    s_exp_m = np.bincount(m_idx, weights=solar_export_kw, minlength=12) * step_hours
    b_dis_m = np.bincount(m_idx, weights=bess_discharge_kw, minlength=12) * step_hours
    g_out_m = np.bincount(m_idx, weights=gen_output_kw, minlength=12) * step_hours
    g_run_m = np.bincount(m_idx, weights=gen_running_mask, minlength=12) * step_hours
    g_fuel_m = np.bincount(m_idx, weights=gen_fuel_step, minlength=12)
    grid_imp_m = np.bincount(m_idx, weights=grid_import_kw, minlength=12) * step_hours
    over_hrs_m = np.bincount(m_idx, weights=(unmet_overload_kw > 0.05), minlength=12) * step_hours
    over_kwh_m = np.bincount(m_idx, weights=unmet_overload_kw, minlength=12) * step_hours

    base_peak_m = np.zeros(12, dtype=float)
    np.maximum.at(base_peak_m, m_idx, load_kw)
    comb_peak_m = np.zeros(12, dtype=float)
    np.maximum.at(comb_peak_m, m_idx, grid_import_kw)
    over_comb_peak_m = np.zeros(12, dtype=float)
    np.maximum.at(over_comb_peak_m, m_idx, unmet_overload_kw)

    rows = []
    for m in range(12):
        if counts[m] == 0:
            continue
        b_peak = float(base_peak_m[m])
        rows.append({
            "Month": MONTH_NAMES_SHORT[m],
            "Consumption (kWh)": round(float(cons_m[m]), 1),
            "Current situation Peak (kW)": round(b_peak, 1),
            "Current situation Overload (kW)": round(max(0.0, b_peak - grid_limit_kw), 1),
            "Solar Generation (kWh)": round(float(s_gen_m[m]), 1),
            "Solar Direct (kWh)": round(float(s_dir_m[m]), 1),
            "Solar Export (kWh)": round(float(s_exp_m[m]), 1),
            "Battery Discharge (kWh)": round(float(b_dis_m[m]), 1),
            "Generator Output (kWh)": round(float(g_out_m[m]), 1),
            "Generator Runtime (hrs)": round(float(g_run_m[m]), 1),
            "Generator Fuel": round(float(g_fuel_m[m]), 1),
            "Combined Grid Import (kWh)": round(float(grid_imp_m[m]), 1),
            "Combined Grid Peak (kW)": round(float(comb_peak_m[m]), 1),
            "Remaining Overload (kW)": round(float(over_comb_peak_m[m]), 1),
            "Remaining Overload (hrs)": round(float(over_hrs_m[m]), 2),
            "Remaining Overload (kWh)": round(float(over_kwh_m[m]), 1),
        })
    return pd.DataFrame(rows)
