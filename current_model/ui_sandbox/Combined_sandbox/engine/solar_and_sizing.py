"""
PV profile generation cache, transparent solar sizing formulas, modular BESS sizing,
dual standalone/coupled sizing, and 4-criterion bottleneck diagnostics.
"""

from dataclasses import replace
from typing import Dict, List, Optional, Tuple
import math
import numpy as np
import pandas as pd

try:
    from current_model.models.solar import SolarLocation, SolarPVConfig
    from current_model.core.solar_engine import simulate_solar_pv_generation
    from current_model.core.bess_engine import analyze_grid_violations
except ImportError:
    from models.solar import SolarLocation, SolarPVConfig
    from core.solar_engine import simulate_solar_pv_generation
    from core.bess_engine import analyze_grid_violations

from .models_and_presets import (
    _opt_njit,
    FUEL_SPECS,
    resolve_generator_fuel_curve,
    CombinedSystemConfig,
    InteractionRulesConfig,
    SolarDerivationInfo,
    QuickSizingResult,
    DualBatterySizingResult,
    DualGeneratorSizingResult,
)

# ======================================================================================
# 3. Reference Unit Solar Profile Cache & Transparent Solar Sizing Derivation
# ======================================================================================

_UNIT_SOLAR_CACHE: Dict[Tuple[float, float, float, float, float, str, int], Tuple[np.ndarray, float, str]] = {}


def get_unit_solar_generation_profile(
    latitude: float,
    longitude: float,
    tilt_deg: float = 30.0,
    azimuth_deg: float = 180.0,
    dc_ac_ratio: float = 1.18,
    weather_mode: str = "single_year",
    selected_year: int = 2025,
) -> Tuple[np.ndarray, float, str]:
    """
    Computes (or retrieves from memory cache) a 35,040-step 15-minute AC generation profile
    for a reference 100 kWp array, normalized to 1.0 kWp (`unit_kw_per_kwp`).
    Supports both concrete calendar year data (`weather_mode="single_year"`, default 2025)
    and long-term Typical Meteorological Year (`weather_mode="TMY"`).
    """
    ratio = max(1.0, min(2.0, float(dc_ac_ratio)))
    w_mode = "single_year" if str(weather_mode) == "single_year" else "TMY"
    w_year = int(selected_year) if w_mode == "single_year" else 0
    key = (
        round(float(latitude), 3),
        round(float(longitude), 3),
        round(float(tilt_deg), 1),
        round(float(azimuth_deg), 1),
        round(ratio, 2),
        w_mode,
        w_year,
    )
    if key in _UNIT_SOLAR_CACHE:
        return _UNIT_SOLAR_CACHE[key]

    ref_loc = SolarLocation(
        name="Reference Site",
        latitude=float(latitude),
        longitude=float(longitude),
        elevation_m=50.0,
    )
    inv_kw = round(100.0 / ratio, 1)
    ref_cfg = SolarPVConfig(
        module_count=200,
        module_power_wp=500.0,
        technology_preset="TOPCon",
        module_technology="Standard PV",
        dc_capacity_kwp=100.0,
        inverter_capacity_kw=inv_kw,
        tilt_deg=float(tilt_deg),
        azimuth_deg=float(azimuth_deg),
        weather_mode=w_mode,
        selected_weather_year=int(selected_year),
    )
    sim_res = simulate_solar_pv_generation(config=ref_cfg, location=ref_loc)
    p_ac_100 = sim_res.df_timeseries["P_AC_kW"].to_numpy(dtype=float)
    if len(p_ac_100) < 35040:
        reps = int(math.ceil(35040 / max(1, len(p_ac_100))))
        p_ac_100 = np.tile(p_ac_100, reps)[:35040]
    elif len(p_ac_100) > 35040:
        p_ac_100 = p_ac_100[:35040]

    unit_profile = np.maximum(0.0, p_ac_100 / 100.0)
    spec_yield = float(np.sum(unit_profile) * 0.25)
    fallback_lbl = (
        f"Solar Data {int(selected_year)} (Historical 15-min)"
        if w_mode == "single_year"
        else "EU PVGIS (ERA5 TMY, 15-min resolution)"
    )
    source_label = str(getattr(sim_res.kpis, "weather_data_source", "") or fallback_lbl)

    _UNIT_SOLAR_CACHE[key] = (unit_profile, round(spec_yield, 1), source_label)
    return _UNIT_SOLAR_CACHE[key]


def derive_solar_sizing_and_formula(
    annual_consumption_kwh: float,
    specific_yield_kwh_per_kwp: float,
    sizing_method: str,
    direct_kwp: float,
    target_share_pct: float,
    panel_wp: float = 450.0,
    dc_ac_ratio: float = 1.18,
    enable_solar: bool = True,
    inverter_ac_limit_kw: float = 0.0,
    inverter_efficiency_pct: float = 98.0,
    data_source_label: str = "EU PVGIS (ERA5 TMY, 15-min resolution)",
    disable_inverter_limit: bool = False,
) -> SolarDerivationInfo:
    """
    Computes the installed Solar kWp, panel count, expected annual yield, inverter AC limit,
    and the single-line live calculation formula.
    """
    spec_yield = max(100.0, float(specific_yield_kwh_per_kwp))
    p_wp = max(100.0, float(panel_wp))
    ann_load = max(0.0, float(annual_consumption_kwh))
    ratio = max(1.0, float(dc_ac_ratio))
    inv_eff = float(np.clip(inverter_efficiency_pct, 80.0, 100.0))

    source_info_text = (
        f"Data source: {data_source_label} | "
        f"Specific Yield: {spec_yield:,.0f} kWh/kWp/year"
    )

    if not enable_solar:
        return SolarDerivationInfo(
            data_source_label=data_source_label,
            specific_yield_kwh_per_kwp=spec_yield,
            annual_consumption_kwh=ann_load,
            sizing_method=sizing_method,
            target_share_pct=0.0,
            effective_share_pct=0.0,
            installed_kwp=0.0,
            panel_count=0,
            panel_wp=p_wp,
            inverter_ac_kw=0.0,
            inverter_efficiency_pct=inv_eff,
            expected_annual_yield_kwh=0.0,
            formula_text="Solar disabled (0.0 kWp)",
            source_info_text=source_info_text,
        )

    if sizing_method == "target_share_pct":
        share_pct = max(0.0, float(target_share_pct))
        raw_kwp = (ann_load * (share_pct / 100.0)) / spec_yield if ann_load > 0 else float(direct_kwp)
        installed_kwp = round(max(0.0, raw_kwp), 1)
        panel_count = int(round((installed_kwp * 1000.0) / p_wp))
        expected_yield_kwh = round(installed_kwp * spec_yield * (inv_eff / 98.0), 0)
        eff_share_pct = (expected_yield_kwh / ann_load * 100.0) if ann_load > 0 else share_pct
        formula_text = (
            f"Calculation: ({ann_load:,.0f} kWh × {share_pct:.0f}%) / "
            f"{spec_yield:,.0f} kWh/kWp = {installed_kwp:,.1f} kWp "
            f"({panel_count:,} panels @ {p_wp:.0f} Wp)"
        )
    else:
        installed_kwp = round(max(0.0, float(direct_kwp)), 1)
        panel_count = int(round((installed_kwp * 1000.0) / p_wp))
        expected_yield_kwh = round(installed_kwp * spec_yield * (inv_eff / 98.0), 0)
        eff_share_pct = (expected_yield_kwh / ann_load * 100.0) if ann_load > 0 else 0.0
        formula_text = (
            f"Calculation: {installed_kwp:,.1f} kWp ({panel_count:,} panels @ {p_wp:.0f} Wp) × "
            f"{spec_yield:,.0f} kWh/kWp = {expected_yield_kwh:,.0f} kWh/year "
            f"({eff_share_pct:.1f}% of consumption)"
        )

    if disable_inverter_limit:
        inv_ac_kw = 0.0
    elif inverter_ac_limit_kw and float(inverter_ac_limit_kw) > 0.0:
        inv_ac_kw = round(float(inverter_ac_limit_kw), 1)
    else:
        inv_ac_kw = round(installed_kwp / ratio, 1)

    return SolarDerivationInfo(
        data_source_label=data_source_label,
        specific_yield_kwh_per_kwp=spec_yield,
        annual_consumption_kwh=ann_load,
        sizing_method=sizing_method,
        target_share_pct=float(target_share_pct),
        effective_share_pct=round(eff_share_pct, 1),
        installed_kwp=installed_kwp,
        panel_count=panel_count,
        panel_wp=p_wp,
        inverter_ac_kw=inv_ac_kw,
        inverter_efficiency_pct=inv_eff,
        expected_annual_yield_kwh=expected_yield_kwh,
        formula_text=formula_text,
        source_info_text=source_info_text,
    )


def determine_smart_modular_units(capacity_kwh: float) -> Tuple[int, float]:
    """
    Calculates physically realistic modular unit count and capacity per unit:
      - Small C&I (<= 500 kWh): 50 kWh rack modules (e.g. 100 kWh -> 2 x 50 kWh)
      - Medium C&I (500 - 2,500 kWh): 100 kWh / 250 kWh cabinets (e.g. 1,000 kWh -> 4 x 250 kWh)
      - Large C&I (2,500 - 10,000 kWh): 500 kWh container blocks (e.g. 5,000 kWh -> 10 x 500 kWh)
      - Utility scale (10,000 - 50,000 kWh): 1,000 kWh (1 MWh) container blocks
      - Mega scale (> 50,000 kWh): 2,500 kWh (2.5 MWh) container units
    Returns:
      (modular_unit_count, capacity_per_unit_kwh)
    """
    c = max(10.0, float(capacity_kwh))
    if c <= 500.0:
        target_unit = 50.0
    elif c <= 2500.0:
        target_unit = 250.0 if c >= 1000.0 else 100.0
    elif c <= 10000.0:
        target_unit = 500.0
    elif c <= 50000.0:
        target_unit = 1000.0
    else:
        target_unit = 2500.0

    units = max(1, int(round(c / target_unit)))
    unit_kwh = round(c / units, 1)
    return units, unit_kwh
def _longest_true_run_steps(mask: np.ndarray) -> int:
    """Vectorized O(N) helper returning the length in steps of the longest continuous True run."""
    if mask.size == 0 or not np.any(mask):
        return 0
    padded = np.empty(len(mask) + 2, dtype=bool)
    padded[0] = False
    padded[-1] = False
    padded[1:-1] = mask
    bounds = np.flatnonzero(padded[1:] != padded[:-1])
    return int(np.max(bounds[1::2] - bounds[0::2]))


def compute_overload_reference(
    load_kw: np.ndarray, grid_limit_kw: float, step_hours: float = 0.25
) -> Tuple[float, float]:
    """Returns (max overload kW, energy of the largest continuous overload event in kWh)."""
    p = np.maximum(0.0, np.nan_to_num(np.asarray(load_kw, dtype=float), nan=0.0))
    over = np.maximum(0.0, p - float(grid_limit_kw))
    if over.size == 0:
        return 0.0, 0.0
    max_kw = float(np.max(over))
    if max_kw <= 0.0:
        return 0.0, 0.0

    is_over = over > 0.0
    padded = np.empty(len(is_over) + 2, dtype=bool)
    padded[0] = False
    padded[-1] = False
    padded[1:-1] = is_over
    bounds = np.flatnonzero(padded[1:] != padded[:-1])
    starts = bounds[0::2]
    ends = bounds[1::2]

    csum = np.empty(len(over) + 1, dtype=float)
    csum[0] = 0.0
    np.cumsum(over, out=csum[1:])
    largest = float(np.max(csum[ends] - csum[starts]) * step_hours)
    return max_kw, largest


@_opt_njit
def _cluster_deficit_kernel(
    p: np.ndarray,
    avail_rech_kw_arr: np.ndarray,
    lim: float,
    eta_dis: float,
    eta_chg: float,
    chg_cap_kw: float,
    dt: float,
    is_gap: np.ndarray,
) -> Tuple[float, int]:
    """Fast JIT/compiled kernel for 35,040-step multi-day cluster deficit integration."""
    n = len(p)
    cum_def = 0.0
    max_cum_def = 0.0
    curr_cluster_steps = 0
    worst_cluster_steps = 0
    inv_eta_dis_dt = dt / eta_dis
    eta_chg_dt = eta_chg * dt

    for i in range(n):
        if is_gap[i]:
            continue
        nl = p[i]
        if nl > lim:
            cum_def += (nl - lim) * inv_eta_dis_dt
            curr_cluster_steps += 1
            if cum_def > max_cum_def:
                max_cum_def = cum_def
            if curr_cluster_steps > worst_cluster_steps:
                worst_cluster_steps = curr_cluster_steps
        elif cum_def > 0.0:
            av = avail_rech_kw_arr[i]
            rech_kw = av if av < chg_cap_kw else chg_cap_kw
            cum_def -= rech_kw * eta_chg_dt
            if cum_def <= 1e-6:
                cum_def = 0.0
                curr_cluster_steps = 0
            else:
                curr_cluster_steps += 1
                if curr_cluster_steps > worst_cluster_steps:
                    worst_cluster_steps = curr_cluster_steps

    return max_cum_def, worst_cluster_steps


def _evaluate_bess_criteria_for_profile(
    net_load_kw: np.ndarray,
    grid_limit_kw: float,
    min_soc_pct: float,
    max_soc_pct: float,
    round_trip_efficiency_pct: float,
    usable_dod_frac: float,
    extra_recharge_kw: Optional[np.ndarray] = None,
    allow_grid_recharge: bool = True,
    step_hours: float = 0.25,
    is_gap: Optional[np.ndarray] = None,
) -> Tuple[float, float, float, float, float, str, float, float]:
    """
    Evaluates the 4 physical BESS sizing criteria on a given net load profile:
      1. Peak Discharge Power (kW)
      2. Single Peak Event Gross Energy (kWh)
      3. Multi-Day Cluster Gross Energy (kWh)
      4. Available Recharge Headroom (max kW, annual kWh)
    Returns (peak_kw, single_gross_kwh, cluster_gross_kwh, max_rech_kw, total_rech_kwh, driver_label, usable_chem_kwh, cluster_duration_hrs).
    """
    p = np.maximum(0.0, np.nan_to_num(np.asarray(net_load_kw, dtype=float), nan=0.0))
    n = len(p)
    dt = float(step_hours)
    lim = float(grid_limit_kw)
    gap_mask = np.asarray(is_gap, dtype=bool) if is_gap is not None and len(is_gap) == n else np.zeros(n, dtype=bool)

    rte = float(np.clip(round_trip_efficiency_pct, 50.0, 100.0)) / 100.0
    eta_dis = math.sqrt(rte)
    eta_chg = math.sqrt(rte)
    dod = max(0.05, float(usable_dod_frac))

    peak_kw, single_net_kwh = compute_overload_reference(p, lim, dt)
    single_gross_kwh = (single_net_kwh / (eta_dis * dod)) * 1.05 if single_net_kwh > 0.0 else 0.0

    extra_chg = (
        np.maximum(0.0, np.asarray(extra_recharge_kw, dtype=float))
        if extra_recharge_kw is not None and len(extra_recharge_kw) == n
        else np.zeros(n, dtype=float)
    )
    grid_headroom_arr = np.maximum(0.0, lim - p) if allow_grid_recharge else np.zeros(n, dtype=float)
    avail_rech_kw_arr = np.where(p <= lim, grid_headroom_arr + extra_chg, extra_chg)
    avail_rech_kw_arr[gap_mask] = 0.0

    max_rech_kw = float(np.max(avail_rech_kw_arr)) if n > 0 else 0.0
    total_rech_kwh = float(np.sum(avail_rech_kw_arr) * eta_chg * dt)
    total_req_chem_kwh = float(np.sum(np.maximum(0.0, p - lim) / eta_dis) * dt)

    chg_cap_kw = float(peak_kw) if peak_kw > 0.0 else lim
    if peak_kw > 0.0:
        max_cum_def, worst_cluster_steps = _cluster_deficit_kernel(
            p, avail_rech_kw_arr, lim, eta_dis, eta_chg, chg_cap_kw, dt, gap_mask
        )
    else:
        max_cum_def, worst_cluster_steps = 0.0, 0

    cluster_gross_kwh = (max_cum_def / dod) * 1.05 if max_cum_def > 0.0 else 0.0
    cluster_gross_kwh = max(cluster_gross_kwh, single_gross_kwh)
    usable_chem_kwh = round(cluster_gross_kwh * dod, 1)
    cluster_duration_hrs = round(worst_cluster_steps * dt, 1)

    if peak_kw <= 0.05:
        driver = "No Overload"
    elif total_rech_kwh < total_req_chem_kwh:
        driver = "Available Recharge Headroom"
    elif cluster_gross_kwh > single_gross_kwh * 1.05:
        driver = "Multi-Day Cluster Energy"
    else:
        driver = "Single Peak Event Energy"

    return (
        round(peak_kw, 1),
        round(single_gross_kwh, 1),
        round(cluster_gross_kwh, 1),
        round(max_rech_kw, 1),
        round(total_rech_kwh, 0),
        driver,
        usable_chem_kwh,
        cluster_duration_hrs,
    )


def build_bess_bottleneck_table_df(
    sa_100_kw: float,
    cp_100_kw: float,
    sa_single_kwh: float,
    cp_single_kwh: float,
    sa_100_kwh: float,
    cp_100_kwh: float,
    sa_rech_kw: float,
    sa_rech_kwh: float,
    cp_rech_kw: float,
    cp_rech_kwh: float,
    cp_driver: str,
    cfg_kw: float,
    cfg_kwh: float,
) -> pd.DataFrame:
    """
    Constructs the 4-Criterion Bottleneck Diagnostic Table in O(1) time without running
    any 35,040-step loops.
    """
    rows = [
        {
            "Criterion": "1. Peak Discharge Power (kW)",
            "What It Checks": "Highest power spike above the Grid Limit",
            "Standalone Required": f"{sa_100_kw:,.1f} kW",
            "Coupled Required": f"{cp_100_kw:,.1f} kW",
            "Configured Battery": f"{cfg_kw:,.1f} kW",
            "Status": "Pass" if cfg_kw >= cp_100_kw - 0.1 else f"Bottleneck (-{max(0.0, cp_100_kw - cfg_kw):,.1f} kW)",
        },
        {
            "Criterion": "2. Single Peak Event Energy (kWh)",
            "What It Checks": "Largest single continuous overload event",
            "Standalone Required": f"{sa_single_kwh:,.1f} kWh",
            "Coupled Required": f"{cp_single_kwh:,.1f} kWh",
            "Configured Battery": f"{cfg_kwh:,.1f} kWh",
            "Status": "Pass" if cfg_kwh >= cp_single_kwh - 0.5 else f"Bottleneck (-{max(0.0, cp_single_kwh - cfg_kwh):,.1f} kWh)",
        },
        {
            "Criterion": "3. Multi-Day Cluster Energy (kWh)",
            "What It Checks": "Consecutive peak days without enough time to recharge in between",
            "Standalone Required": f"{sa_100_kwh:,.1f} kWh",
            "Coupled Required": f"{cp_100_kwh:,.1f} kWh",
            "Configured Battery": f"{cfg_kwh:,.1f} kWh",
            "Status": "Pass" if cfg_kwh >= cp_100_kwh - 0.5 else f"Bottleneck (-{max(0.0, cp_100_kwh - cfg_kwh):,.1f} kWh)",
        },
        {
            "Criterion": "4. Available Recharge Headroom",
            "What It Checks": "Charging room available below Grid Limit & from Solar surplus",
            "Standalone Required": f"{sa_rech_kw:,.0f} kW max ({sa_rech_kwh:,.0f} kWh/yr)",
            "Coupled Required": f"{cp_rech_kw:,.0f} kW max ({cp_rech_kwh:,.0f} kWh/yr)",
            "Configured Battery": f"{cfg_kw:,.1f} kW charge limit",
            "Status": "Pass" if cp_driver != "Available Recharge Headroom" else "Bottleneck (Low Recharge Room)",
        },
    ]
    return pd.DataFrame(rows)


def refresh_bottleneck_table_configured_status(
    dual_bess: DualBatterySizingResult,
    configured_kwh: float,
    configured_kw: float,
    enable_battery: bool = True,
) -> pd.DataFrame:
    """
    Updates only the 'Configured Battery' and 'Status' columns of an existing
    DualBatterySizingResult in O(1) time without re-running the 35,040-step sizing loop.
    """
    cfg_kw = float(configured_kw) if enable_battery else 0.0
    cfg_kwh = float(configured_kwh) if enable_battery else 0.0
    df = build_bess_bottleneck_table_df(
        sa_100_kw=dual_bess.standalone_100_kw,
        cp_100_kw=dual_bess.coupled_100_kw,
        sa_single_kwh=dual_bess.standalone_single_event_kwh,
        cp_single_kwh=dual_bess.coupled_single_event_kwh,
        sa_100_kwh=dual_bess.standalone_100_kwh,
        cp_100_kwh=dual_bess.coupled_100_kwh,
        sa_rech_kw=dual_bess.standalone_recharge_headroom_kw,
        sa_rech_kwh=dual_bess.standalone_recharge_headroom_kwh,
        cp_rech_kw=dual_bess.coupled_recharge_headroom_kw,
        cp_rech_kwh=dual_bess.coupled_recharge_headroom_kwh,
        cp_driver=dual_bess.controlling_driver_coupled,
        cfg_kw=cfg_kw,
        cfg_kwh=cfg_kwh,
    )
    dual_bess.bottleneck_table_df = df
    return df


def compute_dual_battery_sizing(
    load_kw: np.ndarray,
    system_cfg: CombinedSystemConfig,
    rules_cfg: InteractionRulesConfig,
    step_hours: float = 0.25,
    is_gap: Optional[np.ndarray] = None,
    include_generator_in_coupled: bool = False,
) -> DualBatterySizingResult:
    """
    Computes both Mode A (Standalone: Battery only) and Mode B (Coupled: With active Solar,
    Interaction Rules, and optionally active Generator) battery sizing along with the
    4-Criterion Bottleneck Diagnostic Table.

    By default (`include_generator_in_coupled=False`), Mode B evaluates what the Battery needs
    without Generator backup covering deficits, so adding a BESS or prioritizing Battery first
    remains transparent.
    """
    p_load = np.maximum(0.0, np.nan_to_num(np.asarray(load_kw, dtype=float), nan=0.0))
    n_steps = len(p_load)
    dt = float(step_hours)
    grid_limit = float(system_cfg.grid_limit_kw) if system_cfg.enable_grid else 0.0

    min_soc = float(np.clip(system_cfg.min_soc_pct, 0.0, 50.0))
    max_soc = float(np.clip(system_cfg.max_soc_pct, min_soc + 5.0, 100.0))
    rte = float(np.clip(system_cfg.round_trip_efficiency_pct, 50.0, 100.0))
    full_dod = max(0.05, (max_soc - min_soc) / 100.0)

    # 1. Mode A: Standalone (Battery only, full DoD window, grid headroom recharge allowed)
    (
        sa_peak_kw,
        sa_single_kwh,
        sa_cluster_kwh,
        sa_rech_kw,
        sa_rech_kwh,
        sa_driver,
        sa_usable_kwh,
        sa_cluster_duration_hrs,
    ) = _evaluate_bess_criteria_for_profile(
        net_load_kw=p_load,
        grid_limit_kw=grid_limit,
        min_soc_pct=min_soc,
        max_soc_pct=max_soc,
        round_trip_efficiency_pct=rte,
        usable_dod_frac=full_dod,
        extra_recharge_kw=None,
        allow_grid_recharge=True,
        step_hours=dt,
        is_gap=is_gap,
    )
    sa_100_kw = round(math.ceil(sa_peak_kw * 10.0) / 10.0, 1) if sa_peak_kw > 0.05 else 0.0
    sa_100_kwh = float(math.ceil(sa_cluster_kwh))

    # 2. Mode B: Coupled (With active Solar, active Generator, and Rules 1-3)
    if system_cfg.enable_solar and n_steps > 0:
        azim = 180.0 if system_cfg.latitude >= 0.0 else 0.0
        unit_solar_kw, spec_yield, _ = get_unit_solar_generation_profile(
            latitude=system_cfg.latitude,
            longitude=system_cfg.longitude,
            tilt_deg=system_cfg.tilt_deg,
            azimuth_deg=azim,
            dc_ac_ratio=system_cfg.dc_ac_ratio,
            weather_mode=str(getattr(system_cfg, "solar_weather_mode", "single_year") or "single_year"),
            selected_year=int(getattr(system_cfg, "solar_weather_year", 2025) or 2025),
        )
        if len(unit_solar_kw) != n_steps:
            reps = int(math.ceil(n_steps / max(1, len(unit_solar_kw))))
            unit_solar_kw = np.tile(unit_solar_kw, reps)[:n_steps]
        ann_kwh = float(np.sum(p_load) * dt)
        deriv = derive_solar_sizing_and_formula(
            annual_consumption_kwh=ann_kwh,
            specific_yield_kwh_per_kwp=spec_yield,
            sizing_method=system_cfg.solar_sizing_method,
            direct_kwp=system_cfg.solar_kwp,
            target_share_pct=system_cfg.target_consumption_share_pct,
            panel_wp=system_cfg.panel_wp,
            dc_ac_ratio=system_cfg.dc_ac_ratio,
            enable_solar=True,
            inverter_ac_limit_kw=system_cfg.inverter_ac_limit_kw,
            inverter_efficiency_pct=system_cfg.inverter_efficiency_pct,
            disable_inverter_limit=bool(getattr(system_cfg, "disable_solar_inverter_limit", False)),
        )
        p_solar = unit_solar_kw * deriv.installed_kwp * (deriv.inverter_efficiency_pct / 98.0)
        if deriv.inverter_ac_kw > 0.0:
            p_solar = np.minimum(p_solar, deriv.inverter_ac_kw)
    else:
        p_solar = np.zeros(n_steps, dtype=float)

    p_direct = np.minimum(p_load, p_solar)
    p_after_solar = np.maximum(0.0, p_load - p_direct)
    p_surplus = np.maximum(0.0, p_solar - p_direct)

    # Account for active Generator only when explicitly requested (include_generator_in_coupled=True)
    gen_Excess_chg = np.zeros(n_steps, dtype=float)
    use_gen_in_coupled = bool(
        include_generator_in_coupled
        and system_cfg.enable_generator
        and system_cfg.generator_rated_kw > 0.0
    )
    if use_gen_in_coupled:
        g_rated = float(system_cfg.generator_rated_kw)
        g_min = g_rated * (float(system_cfg.generator_min_load_pct) / 100.0)
        over_arr = np.maximum(0.0, p_after_solar - grid_limit)
        if rules_cfg.rule1_peak_priority == "generator_first":
            # Generator takes peaks >= g_min up to g_rated; Battery handles small peaks < g_min and peaks > g_rated
            g_out = np.where(over_arr >= g_min, np.minimum(over_arr, g_rated), 0.0)
            p_for_bess = np.where(
                over_arr >= g_min,
                grid_limit + np.maximum(0.0, over_arr - g_out),
                p_after_solar,
            )
        else:
            # Battery first, Generator as backup: Generator caps overload above what it can cover
            g_assist = np.minimum(over_arr, g_rated)
            p_for_bess = np.where(
                over_arr > 0.0,
                grid_limit + np.maximum(0.0, over_arr - g_assist),
                p_after_solar,
            )
            if rules_cfg.rule3_charging_sources in ("solar_and_generator", "all_sources"):
                gen_Excess_chg = np.where(
                    (over_arr > 0.0) & (g_assist < g_min),
                    g_min - g_assist,
                    0.0,
                )
    else:
        p_for_bess = p_after_solar

    if rules_cfg.rule2_battery_strategy == "self_consumption_reserve" and system_cfg.enable_solar:
        coupled_dod = max(0.05, ( float(rules_cfg.peak_reserve_soc_pct) - min_soc ) / 100.0)
    else:
        coupled_dod = full_dod

    allow_grid_rech_coupled = (
        rules_cfg.rule3_charging_sources in ("solar_and_grid", "all_sources")
        or not system_cfg.enable_solar
    )
    extra_rech_coupled = p_surplus + gen_Excess_chg

    (
        cp_peak_kw,
        cp_single_kwh,
        cp_cluster_kwh,
        cp_rech_kw,
        cp_rech_kwh,
        cp_driver,
        cp_usable_kwh,
        cp_cluster_duration_hrs,
    ) = _evaluate_bess_criteria_for_profile(
        net_load_kw=p_for_bess,
        grid_limit_kw=grid_limit,
        min_soc_pct=min_soc,
        max_soc_pct=max_soc,
        round_trip_efficiency_pct=rte,
        usable_dod_frac=coupled_dod,
        extra_recharge_kw=extra_rech_coupled,
        allow_grid_recharge=allow_grid_rech_coupled,
        step_hours=dt,
        is_gap=is_gap,
    )
    cp_100_kw = round(math.ceil(cp_peak_kw * 10.0) / 10.0, 1) if cp_peak_kw > 0.05 else 0.0
    cp_100_kwh = float(math.ceil(cp_cluster_kwh))

    if cp_100_kw > 0.05 and n_steps > 0:
        gap_b = (
            np.asarray(is_gap, dtype=bool)
            if is_gap is not None and len(is_gap) == n_steps
            else np.zeros(n_steps, dtype=bool)
        )
        from .dispatch_simulation import _calibrate_coupled_bess_capacity_kwh
        calib_cfg = (
            system_cfg
            if use_gen_in_coupled
            else replace(system_cfg, enable_generator=False, generator_rated_kw=0.0)
        )
        cal_kwh, feasible = _calibrate_coupled_bess_capacity_kwh(
            p_load=p_load,
            p_solar=p_solar,
            grid_limit_kw=grid_limit,
            bess_p_max_kw=cp_100_kw,
            system_cfg=calib_cfg,
            rules_cfg=rules_cfg,
            hi_hint_kwh=max(100.0, sa_100_kwh * 2.0, cp_100_kwh * 1.25),
            step_hours=dt,
            gap_mask=gap_b,
        )
        if feasible and cal_kwh > 0.0:
            cp_100_kwh = float(math.ceil(cal_kwh))
            cp_cluster_kwh = cp_100_kwh
            cp_single_kwh = round(min(cp_single_kwh, cp_100_kwh), 1)
            cp_usable_kwh = round(cp_100_kwh * full_dod, 1)
            if cp_driver == "Available Recharge Headroom":
                cp_driver = (
                    "Multi-Day Cluster Energy"
                    if cp_100_kwh > cp_single_kwh * 1.05
                    else "Single Peak Event Energy"
                )
        elif not feasible:
            cp_driver = "Available Recharge Headroom"

    # Build the 4-Criterion Bottleneck Diagnostic Table
    cfg_kw = float(system_cfg.battery_power_kw) if system_cfg.enable_battery else 0.0
    cfg_kwh = float(system_cfg.battery_capacity_kwh) if system_cfg.enable_battery else 0.0

    bottleneck_df = build_bess_bottleneck_table_df(
        sa_100_kw=sa_100_kw,
        cp_100_kw=cp_100_kw,
        sa_single_kwh=sa_single_kwh,
        cp_single_kwh=cp_single_kwh,
        sa_100_kwh=sa_100_kwh,
        cp_100_kwh=cp_100_kwh,
        sa_rech_kw=sa_rech_kw,
        sa_rech_kwh=sa_rech_kwh,
        cp_rech_kw=cp_rech_kw,
        cp_rech_kwh=cp_rech_kwh,
        cp_driver=cp_driver,
        cfg_kw=cfg_kw,
        cfg_kwh=cfg_kwh,
    )

    return DualBatterySizingResult(
        standalone_100_kw=sa_100_kw,
        standalone_100_kwh=sa_100_kwh,
        standalone_80_kw=sa_100_kw,
        standalone_80_kwh=round(sa_100_kwh * 0.80, 1),
        standalone_50_kw=sa_100_kw,
        standalone_50_kwh=round(sa_100_kwh * 0.50, 1),
        standalone_usable_kwh=sa_usable_kwh,
        standalone_cluster_duration_hrs=sa_cluster_duration_hrs,
        coupled_100_kw=cp_100_kw,
        coupled_100_kwh=cp_100_kwh,
        coupled_80_kw=cp_100_kw,
        coupled_80_kwh=round(cp_100_kwh * 0.80, 1),
        coupled_50_kw=cp_100_kw,
        coupled_50_kwh=round(cp_100_kwh * 0.50, 1),
        coupled_usable_kwh=cp_usable_kwh,
        coupled_cluster_duration_hrs=cp_cluster_duration_hrs,
        standalone_peak_discharge_kw=sa_peak_kw,
        coupled_peak_discharge_kw=cp_peak_kw,
        standalone_single_event_kwh=sa_single_kwh,
        coupled_single_event_kwh=cp_single_kwh,
        standalone_multiday_cluster_kwh=sa_cluster_kwh,
        coupled_multiday_cluster_kwh=cp_cluster_kwh,
        standalone_recharge_headroom_kw=sa_rech_kw,
        standalone_recharge_headroom_kwh=sa_rech_kwh,
        coupled_recharge_headroom_kw=cp_rech_kw,
        coupled_recharge_headroom_kwh=cp_rech_kwh,
        controlling_driver_standalone=sa_driver,
        controlling_driver_coupled=cp_driver,
        bottleneck_table_df=bottleneck_df,
    )


def compute_dual_generator_sizing(
    load_kw: np.ndarray,
    timestamps: Optional[pd.DatetimeIndex] = None,
    system_cfg: Optional[CombinedSystemConfig] = None,
    rules_cfg: Optional[InteractionRulesConfig] = None,
    step_hours: float = 0.25,
    is_gap: Optional[np.ndarray] = None,
) -> DualGeneratorSizingResult:
    """
    Computes Dual Sizing for the Generator:
      - Mode A (Standalone: Generator only): Sized to full unmitigated peak overload above Grid Limit.
      - Mode B (Coupled: With active Solar / Battery & Interaction Rules): Sized to the residual peak
        that remains after Solar and Battery dispatch.
    """
    p_load = np.maximum(0.0, np.nan_to_num(np.asarray(load_kw, dtype=float), nan=0.0))
    if timestamps is None:
        freq_str = f"{max(1, int(round(float(step_hours) * 60.0)))}min"
        timestamps = pd.date_range("2025-01-01 00:00:00", periods=len(p_load), freq=freq_str)
    if system_cfg is None:
        system_cfg = CombinedSystemConfig()
    if rules_cfg is None:
        rules_cfg = InteractionRulesConfig()
    grid_limit = float(system_cfg.grid_limit_kw) if system_cfg.enable_grid else 0.0
    raw_over_kw, _ = compute_overload_reference(p_load, grid_limit, step_hours)
    sa_100 = round(math.ceil(raw_over_kw * 10.0) / 10.0, 1) if raw_over_kw > 0.05 else 0.0

    # Diagnostic metrics for Standalone Generator
    over_sa = np.maximum(0.0, p_load - grid_limit)
    sa_kwh = float(np.sum(over_sa) * step_hours)
    sa_mwh = round(sa_kwh / 1000.0, 1)
    sa_is_over = over_sa > 0.05
    sa_runtime_hrs = round(float(np.sum(sa_is_over) * step_hours), 1)

    sa_max_steps = _longest_true_run_steps(sa_is_over)
    sa_longest_hrs = round(float(sa_max_steps * step_hours), 1)

    slope, intercept = resolve_generator_fuel_curve(system_cfg)
    sa_event_fuel = (slope * raw_over_kw + intercept * sa_100) * sa_longest_hrs
    sa_avg_kw = (sa_kwh / max(0.1, sa_runtime_hrs)) if sa_runtime_hrs > 0 else (sa_100 * 0.5)
    sa_reserve_48h = (slope * sa_avg_kw + intercept * sa_100) * 48.0
    sa_tank = round(max(100.0, sa_event_fuel + sa_reserve_48h), 0) if sa_100 > 0 else 0.0

    # Simulate with Generator disabled to measure exact residual peak left after active Solar & Battery
    cfg_no_gen = replace(system_cfg, enable_generator=False, generator_rated_kw=0.0)
    from .dispatch_simulation import simulate_combined_system_dispatch
    res_no_gen = simulate_combined_system_dispatch(
        load_kw=p_load,
        timestamps=timestamps,
        system_cfg=cfg_no_gen,
        rules_cfg=rules_cfg,
        step_hours=step_hours,
        is_gap=is_gap,
    )
    rem_over_kw = float(res_no_gen.kpis.remaining_overload_kw)
    cp_100 = round(math.ceil(rem_over_kw * 10.0) / 10.0, 1) if rem_over_kw > 0.05 else 0.0

    # Diagnostic metrics for Coupled Generator
    over_cp = np.maximum(0.0, res_no_gen.unmet_overload_kw)
    cp_kwh = float(np.sum(over_cp) * step_hours)
    cp_mwh = round(cp_kwh / 1000.0, 1)
    cp_is_over = over_cp > 0.05
    cp_runtime_hrs = round(float(np.sum(cp_is_over) * step_hours), 1)

    cp_max_steps = _longest_true_run_steps(cp_is_over)
    cp_longest_hrs = round(float(cp_max_steps * step_hours), 1)

    cp_event_fuel = (slope * rem_over_kw + intercept * cp_100) * cp_longest_hrs
    cp_avg_kw = (cp_kwh / max(0.1, cp_runtime_hrs)) if cp_runtime_hrs > 0 else (cp_100 * 0.5)
    cp_reserve_48h = (slope * cp_avg_kw + intercept * cp_100) * 48.0
    cp_tank = round(max(100.0, cp_event_fuel + cp_reserve_48h), 0) if cp_100 > 0 else 0.0

    return DualGeneratorSizingResult(
        standalone_100_kw=sa_100,
        standalone_80_kw=round(sa_100 * 0.80, 1),
        standalone_50_kw=round(sa_100 * 0.50, 1),
        coupled_100_kw=cp_100,
        coupled_80_kw=round(cp_100 * 0.80, 1),
        coupled_50_kw=round(cp_100 * 0.50, 1),
        standalone_energy_mwh=sa_mwh,
        standalone_runtime_hours=sa_runtime_hrs,
        standalone_longest_run_hours=sa_longest_hrs,
        standalone_fuel_tank_liters=sa_tank,
        coupled_energy_mwh=cp_mwh,
        coupled_runtime_hours=cp_runtime_hrs,
        coupled_longest_run_hours=cp_longest_hrs,
        coupled_fuel_tank_liters=cp_tank,
    )


def derive_quick_sizing(
    load_kw: np.ndarray,
    grid_limit_kw: float,
    solar_share_pct: float,
    battery_share_pct: float,
    specific_yield_kwh_per_kwp: float,
    min_soc_pct: float = 10.0,
    max_soc_pct: float = 90.0,
    round_trip_efficiency_pct: float = 88.0,
    step_hours: float = 0.25,
    solar_profile_kw: Optional[np.ndarray] = None,
    rules_cfg: Optional[InteractionRulesConfig] = None,
    is_gap: Optional[np.ndarray] = None,
) -> QuickSizingResult:
    """
    Derives source sizes from percentage shares with accurate 100% Zero-Overload sizing:
      - Solar: % of annual Consumption (overall energy source).
      - Battery: Exact 35,040-step cumulative deficit integration taking direct solar
        self-consumption, multi-day peak clustering, and recharge from solar surplus and
        grid headroom (governed by Rules 2 and 3) into account.
      - Generator: Sized to cover the maximum remaining overload peak above the Grid limit.
    """
    p = np.maximum(0.0, np.nan_to_num(np.asarray(load_kw, dtype=float), nan=0.0))
    n_steps = len(p)
    dt = float(step_hours)
    gap_mask = np.asarray(is_gap, dtype=bool) if is_gap is not None and len(is_gap) == n_steps else np.zeros(n_steps, dtype=bool)
    annual_kwh = float(np.sum(p) * dt)
    bat_share = float(np.clip(battery_share_pct, 0.0, 100.0))
    gen_share = 100.0 - bat_share
    sol_share = float(np.clip(solar_share_pct, 0.0, 250.0))
    eff_grid_limit = float(grid_limit_kw)

    spec = max(1.0, float(specific_yield_kwh_per_kwp))
    solar_kwp = round(annual_kwh * sol_share / 100.0 / spec, 1)

    # 1. Solar Profile & Net Load (subtract direct solar self-consumption)
    if solar_profile_kw is not None:
        p_solar = np.maximum(0.0, np.nan_to_num(np.asarray(solar_profile_kw, dtype=float), nan=0.0))
        if len(p_solar) != n_steps and n_steps > 0:
            reps = int(math.ceil(n_steps / max(1, len(p_solar))))
            p_solar = np.tile(p_solar, reps)[:n_steps]
    elif solar_kwp > 0.0 and n_steps > 0:
        unit_profile, _, _ = get_unit_solar_generation_profile(
            latitude=52.3676,
            longitude=4.9041,
            tilt_deg=30.0,
            azimuth_deg=180.0,
            dc_ac_ratio=1.18,
        )
        if len(unit_profile) != n_steps:
            reps = int(math.ceil(n_steps / max(1, len(unit_profile))))
            unit_profile = np.tile(unit_profile, reps)[:n_steps]
        p_solar = unit_profile * solar_kwp
    else:
        p_solar = np.zeros(n_steps, dtype=float)

    p_direct = np.minimum(p, p_solar)
    p_net = np.maximum(0.0, p - p_direct)
    p_surplus = np.maximum(0.0, p_solar - p_direct)

    # 2. Overload above Grid Limit
    overload_arr = np.maximum(0.0, p_net - eff_grid_limit)
    rem_peak_overload = float(np.max(overload_arr)) if n_steps > 0 else 0.0
    _, event_kwh = compute_overload_reference(p_net, eff_grid_limit, dt)

    # 3. DoD Envelope & Efficiency
    min_soc = float(np.clip(min_soc_pct, 0.0, 50.0))
    max_soc = float(np.clip(max_soc_pct, min_soc + 5.0, 100.0))
    rte = float(np.clip(round_trip_efficiency_pct, 50.0, 100.0)) / 100.0
    eta_dis = math.sqrt(rte)
    eta_chg = math.sqrt(rte)

    rule2 = getattr(rules_cfg, "rule2_battery_strategy", "self_consumption_reserve") if rules_cfg else "self_consumption_reserve"
    peak_reserve = float(getattr(rules_cfg, "peak_reserve_soc_pct", 30.0)) if rules_cfg else 30.0
    rule3 = getattr(rules_cfg, "rule3_charging_sources", "solar_and_grid") if rules_cfg else "solar_and_grid"

    if rule2 == "self_consumption_reserve" and sol_share > 0.0:
        usable_dod = max(0.05, (peak_reserve - min_soc) / 100.0)
    else:
        usable_dod = max(0.05, (max_soc - min_soc) / 100.0)

    allow_grid_rech = (rule3 in ("solar_and_grid", "all_sources")) or (sol_share <= 0.0)

    # 4. 35,040-Step Cumulative Deficit Integration (via compiled kernel)
    avail_rech_qs = (
        p_surplus + np.maximum(0.0, eff_grid_limit - p_net)
        if allow_grid_rech
        else p_surplus
    )
    avail_rech_qs[gap_mask] = 0.0
    if rem_peak_overload > 0.0:
        max_cum_deficit, _ = _cluster_deficit_kernel(
            p_net,
            avail_rech_qs,
            eff_grid_limit,
            eta_dis,
            eta_chg,
            float(np.max(avail_rech_qs)) if n_steps > 0 else eff_grid_limit,
            dt,
            gap_mask,
        )
    else:
        max_cum_deficit = 0.0

    # 5. 100% Sizing Anchors
    if rem_peak_overload > 0.05:
        bess_kw_100 = round(math.ceil(rem_peak_overload * 10.0) / 10.0, 1)
        bess_kwh_100 = round((max_cum_deficit / usable_dod) * 1.05, 1) if max_cum_deficit > 0 else 0.0
        gen_kw_100 = round(math.ceil(rem_peak_overload * 10.0) / 10.0, 1)
    else:
        bess_kw_100 = 0.0
        bess_kwh_100 = 0.0
        gen_kw_100 = 0.0

    # 6. Proportional Share Sizing
    bat_kw = round(bess_kw_100 * (bat_share / 100.0), 1)
    bat_kwh = round(bess_kwh_100 * (bat_share / 100.0), 1)
    gen_kw = round(bess_kw_100 - bat_kw, 1) if (0.0 < bat_share < 100.0) else round(gen_kw_100 * (gen_share / 100.0), 1)

    return QuickSizingResult(
        solar_share_pct=sol_share,
        battery_share_pct=bat_share,
        generator_share_pct=gen_share,
        max_overload_kw=rem_peak_overload,
        largest_overload_event_kwh=event_kwh,
        solar_kwp=solar_kwp,
        battery_power_kw=bat_kw,
        battery_capacity_kwh=bat_kwh,
        generator_rated_kw=gen_kw,
    )
