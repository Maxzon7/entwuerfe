"""
========================================================================================
Combined System Sandbox Engine (ui_sandbox/Combined_sandbox/combined_sandbox_engine.py)
========================================================================================

Physical 15-minute simulation engine (35,040 steps/year) uniting:
  - Grid (Contracted Grid Limit)
  - Solar (EU PVGIS - ERA5 TMY 15-min generation & transparent kWp derivation)
  - Battery (SoC envelope, round-trip efficiency, reserve management)
  - Generator (Rated power, minimum load wet-stacking protection, Willans fuel curve)

Controlled via 3 explicit Operating & Interaction Rules:
  - Rule 1: Peak Shaving Priority (Above Grid Limit)
      * "battery_first": Battery first, Generator second
      * "generator_first": Generator first, Battery second
  - Rule 2: Battery Usage Strategy (Below Grid Limit)
      * "peak_shaving_only": Peak Shaving only
      * "self_consumption_reserve": Self-Consumption + Peak Reserve
  - Rule 3: Battery Charging Sources
      * "solar_only": Solar surplus only
      * "solar_and_grid": Solar surplus + Grid (within Grid Limit)
      * "solar_and_generator": Solar surplus + Generator excess (Cycle Charging)

Designed with clean, decoupled data structures (`CombinedSimulationResult`) so that
Phase 2 Financial Evaluation can be attached directly without modifying physical dispatch.
========================================================================================
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Tuple
import math
import numpy as np
import pandas as pd

try:
    from current_model.models.solar import SolarLocation, SolarPVConfig
    from current_model.core.solar_engine import simulate_solar_pv_generation
    from current_model.core.bess_engine import analyze_grid_violations
    from current_model.models.generator import GeneratorConfig
except ImportError:
    from models.solar import SolarLocation, SolarPVConfig
    from core.solar_engine import simulate_solar_pv_generation
    from core.bess_engine import analyze_grid_violations
    from models.generator import GeneratorConfig


# ======================================================================================
# 1. Standard Site Presets & Fuel Specifications
# ======================================================================================

SOLAR_SITE_PRESETS: Dict[str, Dict[str, Any]] = {
    "Netherlands / Rotterdam": {
        "name": "Netherlands / Rotterdam",
        "latitude": 51.9244,
        "longitude": 4.4777,
        "elevation_m": 5.0,
        "tilt_deg": 35.0,
        "azimuth_deg": 180.0,
    },
    "Argentina / Mendoza": {
        "name": "Argentina / Mendoza",
        "latitude": -33.5133,
        "longitude": -69.2561,
        "elevation_m": 1100.0,
        "tilt_deg": 28.0,
        "azimuth_deg": 0.0,
    },
    "Germany / Munich": {
        "name": "Germany / Munich",
        "latitude": 48.1351,
        "longitude": 11.5820,
        "elevation_m": 519.0,
        "tilt_deg": 32.0,
        "azimuth_deg": 180.0,
    },
    "Spain / Madrid": {
        "name": "Spain / Madrid",
        "latitude": 40.4168,
        "longitude": -3.7038,
        "elevation_m": 667.0,
        "tilt_deg": 30.0,
        "azimuth_deg": 180.0,
    },
}

FUEL_SPECS: Dict[str, Dict[str, Any]] = {
    "Diesel": {
        "unit": "L",
        "slope_per_kwh": 0.24,
        "intercept_per_kw_rated": 0.04,
    },
    "Natural Gas": {
        "unit": "m³",
        "slope_per_kwh": 0.28,
        "intercept_per_kw_rated": 0.045,
    },
    "HVO": {
        "unit": "L",
        "slope_per_kwh": 0.25,
        "intercept_per_kw_rated": 0.04,
    },
}

# Rule Option Keys and Display Labels
RULE1_OPTIONS: Dict[str, str] = {
    "battery_first": "Battery first, Generator second",
    "generator_first": "Generator first, Battery second",
}

RULE2_OPTIONS: Dict[str, str] = {
    "peak_shaving_only": "Peak Shaving only",
    "self_consumption_reserve": "Self-Consumption + Peak Reserve",
}

RULE3_OPTIONS: Dict[str, str] = {
    "solar_only": "Solar surplus only",
    "solar_and_grid": "Solar surplus + Grid (within Grid Limit)",
    "solar_and_generator": "Solar surplus + Generator excess (Cycle Charging)",
}


# ======================================================================================
# 2. Configuration & Result Data Models
# ======================================================================================

@dataclass
class CombinedSystemConfig:
    """Physical configuration for all 4 system sources (Grid, Solar, Battery, Generator)."""
    # Column 1: Grid
    grid_limit_kw: float = 200.0

    # Column 2: Solar
    enable_solar: bool = True
    site_preset: str = "Netherlands / Rotterdam"
    latitude: float = 51.9244
    longitude: float = 4.4777
    elevation_m: float = 5.0
    tilt_deg: float = 35.0
    azimuth_deg: float = 180.0
    solar_sizing_method: str = "target_share_pct"  # "direct_kwp" or "target_share_pct"
    solar_kwp: float = 150.0
    panel_wp: float = 450.0
    target_consumption_share_pct: float = 60.0

    # Column 3: Battery
    enable_battery: bool = True
    battery_capacity_kwh: float = 300.0
    battery_power_kw: float = 150.0
    min_soc_pct: float = 10.0
    max_soc_pct: float = 90.0
    round_trip_efficiency_pct: float = 88.0

    # Column 4: Generator
    enable_generator: bool = True
    generator_rated_kw: float = 100.0
    generator_min_load_pct: float = 25.0
    fuel_type: str = "Diesel"


@dataclass
class InteractionRulesConfig:
    """Operating rules governing the 15-minute interaction between Grid, Solar, Battery, and Generator."""
    rule1_peak_priority: str = "battery_first"           # "battery_first" | "generator_first"
    rule2_battery_strategy: str = "self_consumption_reserve"  # "peak_shaving_only" | "self_consumption_reserve"
    peak_reserve_soc_pct: float = 30.0                   # Reserved SoC (%) for peaks when rule2 == "self_consumption_reserve"
    rule3_charging_sources: str = "solar_only"           # "solar_only" | "solar_and_grid" | "solar_and_generator"


@dataclass
class SolarDerivationInfo:
    """Transparent Solar sizing and weather source derivation data."""
    data_source_label: str
    specific_yield_kwh_per_kwp: float
    annual_consumption_kwh: float
    sizing_method: str
    target_share_pct: float
    effective_share_pct: float
    installed_kwp: float
    panel_count: int
    panel_wp: float
    expected_annual_yield_kwh: float
    formula_text: str
    source_info_text: str


@dataclass
class CombinedTechnicalKPIs:
    """Key technical results for the Combined System vs. Current situation."""
    # Consumption Baseline (Current situation)
    annual_consumption_kwh: float = 0.0
    original_peak_kw: float = 0.0
    average_load_kw: float = 0.0
    grid_limit_kw: float = 0.0
    baseline_overload_kw: float = 0.0
    baseline_overload_hours: float = 0.0
    baseline_overload_kwh: float = 0.0

    # KPI 1: Grid Peak Demand (Before vs. After)
    new_grid_peak_kw: float = 0.0
    peak_reduction_kw: float = 0.0
    grid_limit_met: bool = True
    remaining_overload_kw: float = 0.0

    # KPI 2: Remaining Unmet Overload (hrs / kWh)
    remaining_overload_hours: float = 0.0
    remaining_overload_kwh: float = 0.0
    overload_eliminated_pct: float = 100.0

    # KPI 3: Energy Supply Split (kWh & % of Consumption)
    grid_supplied_to_load_kwh: float = 0.0
    grid_import_total_kwh: float = 0.0
    solar_total_generation_kwh: float = 0.0
    solar_direct_kwh: float = 0.0
    solar_via_battery_kwh: float = 0.0
    solar_total_supplied_kwh: float = 0.0
    solar_export_kwh: float = 0.0
    battery_total_discharged_kwh: float = 0.0
    battery_charged_from_solar_kwh: float = 0.0
    battery_charged_from_grid_kwh: float = 0.0
    battery_charged_from_gen_kwh: float = 0.0
    battery_losses_kwh: float = 0.0
    battery_equivalent_cycles: float = 0.0
    generator_total_generation_kwh: float = 0.0
    generator_to_load_kwh: float = 0.0
    generator_to_battery_kwh: float = 0.0
    generator_curtailed_kwh: float = 0.0

    grid_supply_share_pct: float = 100.0
    solar_supply_share_pct: float = 0.0
    solar_direct_share_pct: float = 0.0
    battery_discharge_share_pct: float = 0.0
    generator_supply_share_pct: float = 0.0

    # KPI 4: Generator Runtime & Fuel
    generator_runtime_hours: float = 0.0
    generator_starts_count: int = 0
    generator_fuel_total: float = 0.0
    generator_fuel_unit: str = "L"


@dataclass
class CombinedSimulationResult:
    """
    Complete 35,040-step simulation output for the Combined System.
    Designed to serve both Phase 1 (Technical UI) and Phase 2 (Financial Evaluation).
    """
    system_config: CombinedSystemConfig
    rules_config: InteractionRulesConfig
    solar_derivation: SolarDerivationInfo
    kpis: CombinedTechnicalKPIs
    timestamps: pd.DatetimeIndex

    # 35,040-step 15-minute power series (kW)
    load_kw: np.ndarray
    solar_gen_kw: np.ndarray
    solar_direct_kw: np.ndarray
    solar_surplus_kw: np.ndarray
    solar_export_kw: np.ndarray
    bess_charge_solar_kw: np.ndarray
    bess_charge_grid_kw: np.ndarray
    bess_charge_gen_kw: np.ndarray
    bess_discharge_kw: np.ndarray
    bess_soc_pct: np.ndarray
    bess_energy_kwh: np.ndarray
    gen_output_kw: np.ndarray
    gen_to_load_kw: np.ndarray
    gen_to_bess_kw: np.ndarray
    gen_fuel_step: np.ndarray
    gen_running_mask: np.ndarray
    grid_import_kw: np.ndarray
    unmet_overload_kw: np.ndarray

    # Summary Table Rows (Component & Scenario Summary)
    summary_table_df: pd.DataFrame = field(default_factory=pd.DataFrame)

    # Phase 2 Financial Extension Hook (populated when financial module is attached)
    financial_summary: Optional[Dict[str, Any]] = None


# ======================================================================================
# 3. Reference Unit Solar Profile Cache & Transparent Solar Sizing Derivation
# ======================================================================================

_UNIT_SOLAR_CACHE: Dict[Tuple[float, float, float, float], Tuple[np.ndarray, float, str]] = {}


def get_unit_solar_generation_profile(
    latitude: float,
    longitude: float,
    tilt_deg: float = 30.0,
    azimuth_deg: float = 180.0,
) -> Tuple[np.ndarray, float, str]:
    """
    Computes (or retrieves from memory cache) a 35,040-step 15-minute AC generation profile
    for a reference 100 kWp TOPCon array, normalized to 1.0 kWp (`unit_kw_per_kwp`).

    Returns:
      - `unit_solar_kw`: np.ndarray of shape (35040,) in kW per installed kWp
      - `specific_yield_kwh_per_kwp`: float (annual kWh per 1 kWp)
      - `weather_source_label`: str
    """
    key = (round(float(latitude), 3), round(float(longitude), 3), round(float(tilt_deg), 1), round(float(azimuth_deg), 1))
    if key in _UNIT_SOLAR_CACHE:
        return _UNIT_SOLAR_CACHE[key]

    ref_loc = SolarLocation(
        name="Reference Site",
        latitude=float(latitude),
        longitude=float(longitude),
        elevation_m=50.0,
    )
    # 200 panels @ 500 Wp = 100.0 kWp reference system
    ref_cfg = SolarPVConfig(
        module_count=200,
        module_power_wp=500.0,
        technology_preset="TOPCon",
        module_technology="N-Type TOPCon",
        dc_capacity_kwp=100.0,
        inverter_capacity_kw=85.0,
        tilt_deg=float(tilt_deg),
        azimuth_deg=float(azimuth_deg),
        weather_mode="TMY",
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
    source_label = "EU PVGIS (ERA5 TMY, 15-min resolution)"

    _UNIT_SOLAR_CACHE[key] = (unit_profile, round(spec_yield, 1), source_label)
    return _UNIT_SOLAR_CACHE[key]


def derive_solar_sizing_and_formula(
    annual_consumption_kwh: float,
    specific_yield_kwh_per_kwp: float,
    sizing_method: str,
    direct_kwp: float,
    target_share_pct: float,
    panel_wp: float = 450.0,
    enable_solar: bool = True,
) -> SolarDerivationInfo:
    """
    Computes the installed Solar kWp, panel count, expected annual yield, and the
    single-line live calculation formula required by the Clean Screen Policy.
    """
    spec_yield = max(100.0, float(specific_yield_kwh_per_kwp))
    p_wp = max(100.0, float(panel_wp))
    ann_load = max(0.0, float(annual_consumption_kwh))

    source_info_text = (
        f"Data source: EU PVGIS (ERA5 TMY, 15-min resolution) | "
        f"Specific Yield: {spec_yield:,.0f} kWh/kWp/year"
    )

    if not enable_solar:
        return SolarDerivationInfo(
            data_source_label="EU PVGIS (ERA5 TMY, 15-min resolution)",
            specific_yield_kwh_per_kwp=spec_yield,
            annual_consumption_kwh=ann_load,
            sizing_method=sizing_method,
            target_share_pct=0.0,
            effective_share_pct=0.0,
            installed_kwp=0.0,
            panel_count=0,
            panel_wp=p_wp,
            expected_annual_yield_kwh=0.0,
            formula_text="Solar disabled (0.0 kWp)",
            source_info_text=source_info_text,
        )

    if sizing_method == "target_share_pct":
        share_pct = max(0.0, float(target_share_pct))
        raw_kwp = (ann_load * (share_pct / 100.0)) / spec_yield if ann_load > 0 else float(direct_kwp)
        installed_kwp = round(max(0.0, raw_kwp), 1)
        panel_count = int(round((installed_kwp * 1000.0) / p_wp))
        expected_yield_kwh = round(installed_kwp * spec_yield, 0)
        eff_share_pct = (expected_yield_kwh / ann_load * 100.0) if ann_load > 0 else share_pct
        formula_text = (
            f"Calculation: ({ann_load:,.0f} kWh × {share_pct:.0f}%) / "
            f"{spec_yield:,.0f} kWh/kWp = {installed_kwp:,.1f} kWp "
            f"({panel_count:,} panels @ {p_wp:.0f} Wp)"
        )
    else:
        installed_kwp = round(max(0.0, float(direct_kwp)), 1)
        panel_count = int(round((installed_kwp * 1000.0) / p_wp))
        expected_yield_kwh = round(installed_kwp * spec_yield, 0)
        eff_share_pct = (expected_yield_kwh / ann_load * 100.0) if ann_load > 0 else 0.0
        formula_text = (
            f"Calculation: {installed_kwp:,.1f} kWp ({panel_count:,} panels @ {p_wp:.0f} Wp) × "
            f"{spec_yield:,.0f} kWh/kWp = {expected_yield_kwh:,.0f} kWh/year "
            f"({eff_share_pct:.1f}% of consumption)"
        )

    return SolarDerivationInfo(
        data_source_label="EU PVGIS (ERA5 TMY, 15-min resolution)",
        specific_yield_kwh_per_kwp=spec_yield,
        annual_consumption_kwh=ann_load,
        sizing_method=sizing_method,
        target_share_pct=float(target_share_pct),
        effective_share_pct=round(eff_share_pct, 1),
        installed_kwp=installed_kwp,
        panel_count=panel_count,
        panel_wp=p_wp,
        expected_annual_yield_kwh=expected_yield_kwh,
        formula_text=formula_text,
        source_info_text=source_info_text,
    )


# ======================================================================================
# 4. Main 35,040-Step 4-Source Combined Dispatch Engine
# ======================================================================================

def simulate_combined_system_dispatch(
    load_kw: np.ndarray,
    timestamps: pd.DatetimeIndex,
    system_cfg: CombinedSystemConfig,
    rules_cfg: InteractionRulesConfig,
    step_hours: float = 0.25,
) -> CombinedSimulationResult:
    """
    Executes the 35,040-step (15-minute) physical interaction between Grid, Solar, Battery,
    and Generator governed by Rules 1, 2, and 3.
    """
    p_load = np.maximum(0.0, np.nan_to_num(np.asarray(load_kw, dtype=float), nan=0.0))
    n_steps = len(p_load)
    dt = float(step_hours)
    annual_consumption_kwh = float(np.sum(p_load) * dt)
    orig_peak_kw = float(np.max(p_load)) if n_steps > 0 else 0.0
    avg_load_kw = float(np.mean(p_load)) if n_steps > 0 else 0.0

    grid_limit_kw = max(0.0, float(system_cfg.grid_limit_kw))

    # 1. Solar Profile & Derivation
    unit_solar_kw, spec_yield, _ = get_unit_solar_generation_profile(
        latitude=system_cfg.latitude,
        longitude=system_cfg.longitude,
        tilt_deg=system_cfg.tilt_deg,
        azimuth_deg=system_cfg.azimuth_deg,
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
        enable_solar=system_cfg.enable_solar,
    )

    if system_cfg.enable_solar and solar_derivation.installed_kwp > 0.0:
        solar_gen_kw = unit_solar_kw * solar_derivation.installed_kwp
    else:
        solar_gen_kw = np.zeros(n_steps, dtype=float)

    # 2. Battery Parameters
    enable_bess = bool(system_cfg.enable_battery and system_cfg.battery_capacity_kwh > 0.0 and system_cfg.battery_power_kw > 0.0)
    bess_cap_kwh = max(0.0, float(system_cfg.battery_capacity_kwh)) if enable_bess else 0.0
    bess_p_max_kw = max(0.0, float(system_cfg.battery_power_kw)) if enable_bess else 0.0
    min_soc_pct = float(np.clip(system_cfg.min_soc_pct, 0.0, 95.0))
    max_soc_pct = float(np.clip(system_cfg.max_soc_pct, min_soc_pct + 5.0, 100.0))
    rte = float(np.clip(system_cfg.round_trip_efficiency_pct, 50.0, 100.0)) / 100.0
    eta_chg = math.sqrt(rte)
    eta_dis = math.sqrt(rte)

    e_min_kwh = bess_cap_kwh * (min_soc_pct / 100.0)
    e_max_kwh = bess_cap_kwh * (max_soc_pct / 100.0)

    # Reserve SoC for Rule 2 ("self_consumption_reserve")
    reserve_soc_pct = float(np.clip(rules_cfg.peak_reserve_soc_pct, min_soc_pct, max_soc_pct))
    e_reserve_kwh = bess_cap_kwh * (reserve_soc_pct / 100.0)

    # 3. Generator Parameters
    enable_gen = bool(system_cfg.enable_generator and system_cfg.generator_rated_kw > 0.0)
    gen_rated_kw = max(0.0, float(system_cfg.generator_rated_kw)) if enable_gen else 0.0
    gen_min_pct = float(np.clip(system_cfg.generator_min_load_pct, 0.0, 100.0))
    gen_min_kw = gen_rated_kw * (gen_min_pct / 100.0)
    fuel_spec = FUEL_SPECS.get(system_cfg.fuel_type, FUEL_SPECS["Diesel"])
    fuel_unit = str(fuel_spec["unit"])
    gen_model = GeneratorConfig(
        rated_power_kw=gen_rated_kw,
        fuel_type=system_cfg.fuel_type,
        min_load_ratio_pct=gen_min_pct,
        fuel_curve_slope_l_per_kwh=float(fuel_spec["slope_per_kwh"]),
        fuel_curve_intercept_l_per_kw_rated=float(fuel_spec["intercept_per_kw_rated"]),
    )

    # 4. Pre-allocate 35,040-step Arrays
    solar_direct_kw = np.minimum(p_load, solar_gen_kw)
    solar_surplus_kw = np.maximum(0.0, solar_gen_kw - solar_direct_kw)
    rem_load_after_solar_kw = np.maximum(0.0, p_load - solar_direct_kw)

    solar_export_kw = np.zeros(n_steps, dtype=float)
    bess_charge_solar_kw = np.zeros(n_steps, dtype=float)
    bess_charge_grid_kw = np.zeros(n_steps, dtype=float)
    bess_charge_gen_kw = np.zeros(n_steps, dtype=float)
    bess_discharge_kw = np.zeros(n_steps, dtype=float)
    bess_Discharge_from_solar_kwh_acc = 0.0
    bess_soc_pct = np.zeros(n_steps, dtype=float)
    bess_energy_kwh = np.zeros(n_steps, dtype=float)

    gen_output_kw = np.zeros(n_steps, dtype=float)
    gen_to_load_kw = np.zeros(n_steps, dtype=float)
    gen_to_bess_kw = np.zeros(n_steps, dtype=float)
    gen_fuel_step = np.zeros(n_steps, dtype=float)
    gen_running_mask = np.zeros(n_steps, dtype=bool)

    grid_import_kw = np.zeros(n_steps, dtype=float)
    unmet_overload_kw = np.zeros(n_steps, dtype=float)

    # Initial Battery Energy State:
    # Start at reserve SoC (if self-consumption + reserve) or 50% SoC (or max_soc if grid charging is enabled)
    if enable_bess:
        if rules_cfg.rule2_battery_strategy == "peak_shaving_only":
            cur_e_kwh = e_max_kwh if rules_cfg.rule3_charging_sources == "solar_and_grid" else (0.5 * (e_min_kwh + e_max_kwh))
        else:
            cur_e_kwh = max(e_min_kwh, e_reserve_kwh)
    else:
        cur_e_kwh = 0.0

    # Track fraction of stored battery energy originating from Solar PV (for accurate supply split)
    solar_energy_in_bess_kwh = cur_e_kwh if (system_cfg.enable_solar and rules_cfg.rule3_charging_sources == "solar_only") else 0.0

    rule1 = rules_cfg.rule1_peak_priority
    rule2 = rules_cfg.rule2_battery_strategy
    rule3 = rules_cfg.rule3_charging_sources

    # 5. Step-by-Step 15-Minute Simulation Loop
    for i in range(n_steps):
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
            room_ac_kw = (e_max_kwh - cur_e_kwh) / (dt * eta_chg)
            step_bess_chg_solar = min(p_surplus, bess_p_max_kw, room_ac_kw)
            added_e = step_bess_chg_solar * dt * eta_chg
            cur_e_kwh += added_e
            solar_energy_in_bess_kwh = min(cur_e_kwh, solar_energy_in_bess_kwh + added_e)
            solar_export_kw[i] = max(0.0, p_surplus - step_bess_chg_solar)
        else:
            solar_export_kw[i] = p_surplus

        rem_bess_chg_power_kw = max(0.0, bess_p_max_kw - step_bess_chg_solar)

        # B. Handle Residual Demand
        if p_rem > grid_limit_kw:
            # --- ABOVE GRID LIMIT (Peak Shaving Region) ---
            overload_kw = p_rem - grid_limit_kw

            if rule1 == "battery_first":
                # 1. Battery discharges first down to e_min_kwh
                if enable_bess and step_bess_chg_solar == 0.0 and cur_e_kwh > e_min_kwh:
                    avail_dis_ac_kw = ((cur_e_kwh - e_min_kwh) / dt) * eta_dis
                    step_bess_dis = min(overload_kw, bess_p_max_kw, avail_dis_ac_kw)
                    removed_e = (step_bess_dis * dt) / eta_dis
                    solar_share = (solar_energy_in_bess_kwh / cur_e_kwh) if cur_e_kwh > 0 else 0.0
                    bess_Discharge_from_solar_kwh_acc += (step_bess_dis * dt) * solar_share
                    cur_e_kwh = max(e_min_kwh, cur_e_kwh - removed_e)
                    solar_energy_in_bess_kwh = max(0.0, solar_energy_in_bess_kwh - removed_e * solar_share)

                rem_overload_kw = max(0.0, overload_kw - step_bess_dis)

                # 2. Generator covers remaining overload second
                if rem_overload_kw > 0.001 and enable_gen:
                    req_gen_kw = min(rem_overload_kw, gen_rated_kw)
                    actual_gen_kw = max(req_gen_kw, min(gen_rated_kw, gen_min_kw))
                    step_gen_out = actual_gen_kw
                    step_gen_to_load = min(actual_gen_kw, rem_overload_kw)

                    # Excess generator power from minimum load enforcement
                    gen_excess_kw = max(0.0, actual_gen_kw - step_gen_to_load)
                    if gen_excess_kw > 0.0:
                        if rule3 == "solar_and_generator" and enable_bess and step_bess_dis == 0.0 and cur_e_kwh < e_max_kwh:
                            room_ac_kw = (e_max_kwh - cur_e_kwh) / (dt * eta_chg)
                            step_bess_chg_gen = min(gen_excess_kw, rem_bess_chg_power_kw, room_ac_kw)
                            cur_e_kwh += step_bess_chg_gen * dt * eta_chg
                            gen_excess_after_bess = gen_excess_kw - step_bess_chg_gen
                        else:
                            gen_excess_after_bess = gen_excess_kw
                        # Any remaining generator output displaces residual load below grid limit
                        extra_to_load = min(gen_excess_after_bess, max(0.0, p_rem - step_bess_dis - step_gen_to_load))
                        step_gen_to_load += extra_to_load
                    step_gen_to_bess = step_bess_chg_gen

            else:
                # --- "generator_first": Generator first, Battery second ---
                # Check if overload is a small peak below generator minimum load that Battery can handle alone
                avail_bess_dis_kw = (((cur_e_kwh - e_min_kwh) / dt) * eta_dis) if (enable_bess and step_bess_chg_solar == 0.0 and cur_e_kwh > e_min_kwh) else 0.0
                avail_bess_dis_kw = min(bess_p_max_kw, avail_bess_dis_kw)

                if enable_gen and (overload_kw < gen_min_kw) and enable_bess and (avail_bess_dis_kw >= overload_kw):
                    # Battery absorbs small peak below generator minimum load
                    step_bess_dis = overload_kw
                    removed_e = (step_bess_dis * dt) / eta_dis
                    solar_share = (solar_energy_in_bess_kwh / cur_e_kwh) if cur_e_kwh > 0 else 0.0
                    bess_Discharge_from_solar_kwh_acc += (step_bess_dis * dt) * solar_share
                    cur_e_kwh = max(e_min_kwh, cur_e_kwh - removed_e)
                    solar_energy_in_bess_kwh = max(0.0, solar_energy_in_bess_kwh - removed_e * solar_share)
                else:
                    # 1. Generator runs first
                    if enable_gen:
                        req_gen_kw = min(overload_kw, gen_rated_kw)
                        actual_gen_kw = max(req_gen_kw, min(gen_rated_kw, gen_min_kw))
                        step_gen_out = actual_gen_kw
                        step_gen_to_load = min(actual_gen_kw, overload_kw)

                        gen_excess_kw = max(0.0, actual_gen_kw - step_gen_to_load)
                        if gen_excess_kw > 0.0:
                            if rule3 == "solar_and_generator" and enable_bess and cur_e_kwh < e_max_kwh:
                                room_ac_kw = (e_max_kwh - cur_e_kwh) / (dt * eta_chg)
                                step_bess_chg_gen = min(gen_excess_kw, rem_bess_chg_power_kw, room_ac_kw)
                                cur_e_kwh += step_bess_chg_gen * dt * eta_chg
                                gen_excess_after_bess = gen_excess_kw - step_bess_chg_gen
                            else:
                                gen_excess_after_bess = gen_excess_kw
                            extra_to_load = min(gen_excess_after_bess, max(0.0, p_rem - step_gen_to_load))
                            step_gen_to_load += extra_to_load
                        step_gen_to_bess = step_bess_chg_gen

                    rem_overload_kw = max(0.0, overload_kw - step_gen_to_load)

                    # 2. Battery covers any remaining peak exceeding Generator rated power
                    if rem_overload_kw > 0.001 and enable_bess and step_bess_chg_solar == 0.0 and step_bess_chg_gen == 0.0 and cur_e_kwh > e_min_kwh:
                        avail_dis_ac_kw = ((cur_e_kwh - e_min_kwh) / dt) * eta_dis
                        step_bess_dis = min(rem_overload_kw, bess_p_max_kw, avail_dis_ac_kw)
                        removed_e = (step_bess_dis * dt) / eta_dis
                        solar_share = (solar_energy_in_bess_kwh / cur_e_kwh) if cur_e_kwh > 0 else 0.0
                        bess_Discharge_from_solar_kwh_acc += (step_bess_dis * dt) * solar_share
                        cur_e_kwh = max(e_min_kwh, cur_e_kwh - removed_e)
                        solar_energy_in_bess_kwh = max(0.0, solar_energy_in_bess_kwh - removed_e * solar_share)

        else:
            # --- BELOW OR AT GRID LIMIT (Normal Load Region) ---
            # Rule 2: Self-Consumption + Peak Reserve allows discharging down to e_reserve_kwh
            if (
                rule2 == "self_consumption_reserve"
                and enable_bess
                and step_bess_chg_solar == 0.0
                and p_rem > 0.0
                and cur_e_kwh > e_reserve_kwh
            ):
                avail_dis_ac_kw = ((cur_e_kwh - e_reserve_kwh) / dt) * eta_dis
                step_bess_dis = min(p_rem, bess_p_max_kw, avail_dis_ac_kw)
                removed_e = (step_bess_dis * dt) / eta_dis
                solar_share = (solar_energy_in_bess_kwh / cur_e_kwh) if cur_e_kwh > 0 else 0.0
                bess_Discharge_from_solar_kwh_acc += (step_bess_dis * dt) * solar_share
                cur_e_kwh = max(e_reserve_kwh, cur_e_kwh - removed_e)
                solar_energy_in_bess_kwh = max(0.0, solar_energy_in_bess_kwh - removed_e * solar_share)

            # Rule 3: Battery Grid Recharging within Grid Limit
            if (
                rule3 == "solar_and_grid"
                and enable_bess
                and step_bess_dis == 0.0
                and rem_bess_chg_power_kw > 0.0
            ):
                # Target SoC for grid recharging:
                # If Peak Shaving only (or Solar disabled), recharge up to e_max_kwh.
                # If Self-Consumption + Peak Reserve (with Solar enabled), recharge from grid up to e_reserve_kwh
                # so peak reserve is guaranteed while leaving upper capacity for free daytime solar surplus.
                target_grid_e_kwh = (
                    e_max_kwh
                    if (rule2 == "peak_shaving_only" or not system_cfg.enable_solar)
                    else e_reserve_kwh
                )
                if cur_e_kwh < target_grid_e_kwh:
                    headroom_kw = max(0.0, grid_limit_kw - (p_rem - step_bess_dis))
                    if headroom_kw > 0.0:
                        room_ac_kw = (target_grid_e_kwh - cur_e_kwh) / (dt * eta_chg)
                        step_bess_chg_grid = min(headroom_kw, rem_bess_chg_power_kw, room_ac_kw)
                        cur_e_kwh += step_bess_chg_grid * dt * eta_chg

        # C. Record Step States
        bess_charge_solar_kw[i] = step_bess_chg_solar
        bess_charge_grid_kw[i] = step_bess_chg_grid
        bess_charge_gen_kw[i] = step_bess_chg_gen
        bess_discharge_kw[i] = step_bess_dis
        bess_energy_kwh[i] = cur_e_kwh
        bess_soc_pct[i] = (cur_e_kwh / bess_cap_kwh * 100.0) if bess_cap_kwh > 0.0 else 0.0

        gen_output_kw[i] = step_gen_out
        gen_to_load_kw[i] = step_gen_to_load
        gen_to_bess_kw[i] = step_gen_to_bess
        if step_gen_out > 0.0:
            gen_running_mask[i] = True
            gen_fuel_step[i] = gen_model.calc_fuel_consumption(step_gen_out, duration_hours=dt)

        net_grid_kw = max(0.0, p_rem - step_bess_dis - step_gen_to_load + step_bess_chg_grid)
        grid_import_kw[i] = net_grid_kw
        unmet_overload_kw[i] = max(0.0, net_grid_kw - grid_limit_kw)

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
    bess_dis_from_solar_kwh = float(min(bess_dis_total_kwh, bess_Discharge_from_solar_kwh_acc))
    bess_losses_kwh = max(0.0, (bess_chg_solar_kwh + bess_chg_grid_kwh + bess_chg_gen_kwh) - bess_dis_total_kwh)
    bess_cycles = (bess_dis_total_kwh / bess_cap_kwh) if bess_cap_kwh > 0.0 else 0.0

    gen_total_gen_kwh = float(np.sum(gen_output_kw) * dt)
    gen_to_load_kwh = float(np.sum(gen_to_load_kw) * dt)
    gen_to_bess_kwh = float(np.sum(gen_to_bess_kw) * dt)
    gen_curtailed_kwh = max(0.0, gen_total_gen_kwh - gen_to_load_kwh - gen_to_bess_kwh)
    gen_runtime_hours = float(np.sum(gen_running_mask) * dt)
    gen_fuel_total = float(np.sum(gen_fuel_step))
    if n_steps > 0:
        gen_starts = int(np.sum((gen_running_mask[1:] == True) & (gen_running_mask[:-1] == False))) + (
            1 if gen_running_mask[0] else 0
        )
    else:
        gen_starts = 0

    grid_import_total_kwh = float(np.sum(grid_import_kw) * dt)
    grid_supplied_to_load_kwh = max(0.0, grid_import_total_kwh - bess_chg_grid_kwh)

    # Supply Split Shares (% of Annual Consumption)
    denom = max(1.0, annual_consumption_kwh)
    solar_total_supplied_kwh = solar_direct_kwh + bess_dis_from_solar_kwh
    # Remainder of load supplied by generator (direct + via battery) and grid (direct + via battery)
    solar_direct_share_pct = (solar_direct_kwh / denom) * 100.0
    bess_dis_share_pct = (bess_dis_total_kwh / denom) * 100.0
    solar_supply_share_pct = min(100.0, (solar_total_supplied_kwh / denom) * 100.0)
    gen_supply_share_pct = min(100.0, ((gen_to_load_kwh + (bess_dis_total_kwh - bess_dis_from_solar_kwh) * (bess_chg_gen_kwh / max(0.01, bess_chg_grid_kwh + bess_chg_gen_kwh))) / denom) * 100.0) if (bess_chg_grid_kwh + bess_chg_gen_kwh) > 0 else min(100.0, (gen_to_load_kwh / denom) * 100.0)
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
        summary_table_df=summary_df,
    )


def build_component_summary_table(
    system_cfg: CombinedSystemConfig,
    solar_derivation: SolarDerivationInfo,
    kpis: CombinedTechnicalKPIs,
    solar_gen_kw: np.ndarray,
    bess_discharge_kw: np.ndarray,
    gen_output_kw: np.ndarray,
) -> pd.DataFrame:
    """
    Builds the clean Component & Scenario Summary Table for Level 4 (Phase 1: Technical Columns).
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

