"""
========================================================================================
Combined System Sandbox Engine (ui_sandbox/Combined_sandbox/combined_sandbox_engine.py)
========================================================================================

Physical 15-minute simulation engine (35,040 steps/year) uniting:
  - Grid (Contracted Grid Limit)
  - Solar (Default GPS: Amsterdam 52.3676, 4.9041; EU PVGIS - ERA5 TMY 15-min generation)
  - Battery (Capacity, Power, SoC envelope, Round-Trip Efficiency, Reserve management)
  - Generator (Rated power, Minimum load wet-stacking limit, Willans curve, Min runtime)

Controlled via 3 explicit Operating & Interaction Rules:
  - Rule 1: Peak Shaving Priority (Above Grid Limit)
      * "battery_first": Battery first, Generator as backup
      * "generator_first": Generator first, Battery for fast/small peaks
  - Rule 2: Battery Usage Strategy (Below Grid Limit)
      * "peak_shaving_only": Peak Shaving only
      * "self_consumption_reserve": Self-Consumption + Peak Reserve
  - Rule 3: Battery Charging Sources
      * "solar_only": Solar surplus only
      * "solar_and_grid": Solar surplus + Grid headroom
      * "solar_and_generator": Solar surplus + Generator excess (Cycle Charging)

Includes a decoupled Financial Evaluation Engine (`evaluate_combined_financials`) used by
Tab 3 (`Financials`) and Sheet 4 of the Excel verification export.
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


MONTH_NAMES_SHORT = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]


# ======================================================================================
# 1. Standard GPS Presets (Default: Amsterdam) & Fuel Specifications
# ======================================================================================

SOLAR_SITE_PRESETS: Dict[str, Dict[str, Any]] = {
    "Amsterdam (Default GPS)": {
        "name": "Amsterdam, Netherlands",
        "latitude": 52.3676,
        "longitude": 4.9041,
        "elevation_m": 2.0,
        "tilt_deg": 30.0,
        "azimuth_deg": 180.0,
    },
    "Netherlands / Rotterdam": {
        "name": "Netherlands / Rotterdam",
        "latitude": 51.9244,
        "longitude": 4.4777,
        "elevation_m": 5.0,
        "tilt_deg": 30.0,
        "azimuth_deg": 180.0,
    },
    "Argentina / Mendoza": {
        "name": "Argentina / Mendoza",
        "latitude": -33.5133,
        "longitude": -69.2561,
        "elevation_m": 1100.0,
        "tilt_deg": 30.0,
        "azimuth_deg": 0.0,
    },
    "Germany / Munich": {
        "name": "Germany / Munich",
        "latitude": 48.1351,
        "longitude": 11.5820,
        "elevation_m": 519.0,
        "tilt_deg": 30.0,
        "azimuth_deg": 180.0,
    },
    "Germany / Berlin": {
        "name": "Germany / Berlin",
        "latitude": 52.5200,
        "longitude": 13.4050,
        "elevation_m": 34.0,
        "tilt_deg": 30.0,
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
    "battery_first": "Battery first, Generator as backup",
    "generator_first": "Generator first, Battery for fast/small peaks",
}

RULE2_OPTIONS: Dict[str, str] = {
    "peak_shaving_only": "Peak Shaving only",
    "self_consumption_reserve": "Self-Consumption + Peak Reserve",
}

RULE3_OPTIONS: Dict[str, str] = {
    "solar_only": "Solar surplus only",
    "solar_and_grid": "Solar surplus + Grid headroom",
    "solar_and_generator": "Solar surplus + Generator excess (Cycle Charging)",
}


# ======================================================================================
# 2. Configuration & Result Data Models
# ======================================================================================

@dataclass
class CombinedSystemConfig:
    """Purely physical/technical configuration for all 4 system sources."""
    # Tile 1: Grid
    enable_grid: bool = True
    grid_limit_kw: float = 180.0

    # Tile 2: Solar (Default GPS: Amsterdam 52.3676, 4.9041)
    enable_solar: bool = True
    site_preset: str = "Amsterdam (Default GPS)"
    latitude: float = 52.3676
    longitude: float = 4.9041
    elevation_m: float = 2.0
    tilt_deg: float = 30.0
    azimuth_deg: float = 180.0
    solar_sizing_method: str = "target_share_pct"  # "direct_kwp" or "target_share_pct"
    solar_kwp: float = 150.0
    panel_wp: float = 450.0
    dc_ac_ratio: float = 1.18
    target_consumption_share_pct: float = 60.0

    # Tile 3: Battery
    enable_battery: bool = True
    battery_capacity_kwh: float = 300.0
    battery_power_kw: float = 150.0
    min_soc_pct: float = 10.0
    max_soc_pct: float = 90.0
    round_trip_efficiency_pct: float = 88.0

    # Tile 4: Generator
    enable_generator: bool = True
    generator_rated_kw: float = 100.0
    generator_min_load_pct: float = 25.0
    fuel_type: str = "Diesel"
    gen_slope_per_kwh: float = 0.24
    gen_intercept_per_kw_rated: float = 0.04
    gen_min_runtime_minutes: int = 30


@dataclass
class InteractionRulesConfig:
    """Operating rules governing the 15-minute interaction between Grid, Solar, Battery, and Generator."""
    rule1_peak_priority: str = "battery_first"                # "battery_first" | "generator_first"
    rule2_battery_strategy: str = "self_consumption_reserve"  # "peak_shaving_only" | "self_consumption_reserve"
    peak_reserve_soc_pct: float = 30.0                        # Reserved SoC (%) for peaks when rule2 == "self_consumption_reserve"
    rule3_charging_sources: str = "solar_only"                # "solar_only" | "solar_and_grid" | "solar_and_generator"


@dataclass
class CombinedFinancialConfig:
    """Financial parameters configured in Tab 3 (Financials)."""
    # Grid Tariffs
    grid_energy_price_eur_kwh: float = 0.20
    grid_capacity_fee_eur_kw_month: float = 8.50
    grid_fixed_fee_eur_month: float = 150.0
    grid_overload_penalty_eur_kw: float = 15.00

    # Solar Costs
    solar_capex_eur_kwp: float = 850.0
    solar_om_pct_of_capex: float = 1.5

    # Battery Costs
    battery_capex_eur_kwh: float = 350.0
    battery_capex_eur_kw: float = 150.0
    battery_om_pct_of_capex: float = 1.5

    # Generator Costs
    generator_cost_model: str = "Purchase (CAPEX)"  # "Purchase (CAPEX)" or "Rental (OPEX)"
    generator_capex_eur: float = 22000.0
    generator_rental_eur_month: float = 1200.0
    fuel_price_eur_per_unit: float = 1.45
    generator_maintenance_eur_per_hour: float = 4.50


@dataclass
class CombinedFinancialKPIs:
    """Key financial results evaluated in Tab 3 (vs. Current situation)."""
    # CAPEX
    solar_capex_eur: float = 0.0
    battery_capex_eur: float = 0.0
    generator_capex_eur: float = 0.0
    total_capex_eur: float = 0.0

    # Baseline (Current situation) Annual OPEX
    baseline_energy_cost_eur: float = 0.0
    baseline_capacity_cost_eur: float = 0.0
    baseline_fixed_cost_eur: float = 0.0
    baseline_penalty_cost_eur: float = 0.0
    baseline_total_opex_eur: float = 0.0

    # Combined System Annual OPEX
    combined_grid_energy_cost_eur: float = 0.0
    combined_grid_capacity_cost_eur: float = 0.0
    combined_grid_fixed_cost_eur: float = 0.0
    combined_grid_penalty_cost_eur: float = 0.0
    combined_grid_total_eur: float = 0.0
    solar_om_eur: float = 0.0
    battery_om_eur: float = 0.0
    generator_fuel_cost_eur: float = 0.0
    generator_maintenance_cost_eur: float = 0.0
    generator_rental_cost_eur: float = 0.0
    generator_total_opex_eur: float = 0.0
    total_annual_opex_eur: float = 0.0

    # Savings & Payback
    annual_savings_eur: float = 0.0
    payback_years: Optional[float] = None


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
    inverter_ac_kw: float
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

    # Tables
    summary_table_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    monthly_balance_df: pd.DataFrame = field(default_factory=pd.DataFrame)

    # Financial Evaluation (populated via `evaluate_combined_financials`)
    financial_config: Optional[CombinedFinancialConfig] = None
    financial_kpis: Optional[CombinedFinancialKPIs] = None
    financial_table_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    monthly_cost_df: pd.DataFrame = field(default_factory=pd.DataFrame)


# ======================================================================================
# 3. Reference Unit Solar Profile Cache & Transparent Solar Sizing Derivation
# ======================================================================================

_UNIT_SOLAR_CACHE: Dict[Tuple[float, float, float, float, float], Tuple[np.ndarray, float, str]] = {}


def get_unit_solar_generation_profile(
    latitude: float,
    longitude: float,
    tilt_deg: float = 30.0,
    azimuth_deg: float = 180.0,
    dc_ac_ratio: float = 1.18,
) -> Tuple[np.ndarray, float, str]:
    """
    Computes (or retrieves from memory cache) a 35,040-step 15-minute AC generation profile
    for a reference 100 kWp array, normalized to 1.0 kWp (`unit_kw_per_kwp`).
    """
    ratio = max(1.0, min(2.0, float(dc_ac_ratio)))
    key = (
        round(float(latitude), 3),
        round(float(longitude), 3),
        round(float(tilt_deg), 1),
        round(float(azimuth_deg), 1),
        round(ratio, 2),
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
    dc_ac_ratio: float = 1.18,
    enable_solar: bool = True,
) -> SolarDerivationInfo:
    """
    Computes the installed Solar kWp, panel count, expected annual yield, and the
    single-line live calculation formula required by the Clean Screen Policy.
    """
    spec_yield = max(100.0, float(specific_yield_kwh_per_kwp))
    p_wp = max(100.0, float(panel_wp))
    ann_load = max(0.0, float(annual_consumption_kwh))
    ratio = max(1.0, float(dc_ac_ratio))

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
            inverter_ac_kw=0.0,
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

    inv_ac_kw = round(installed_kwp / ratio, 1)

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
        inverter_ac_kw=inv_ac_kw,
        expected_annual_yield_kwh=expected_yield_kwh,
        formula_text=formula_text,
        source_info_text=source_info_text,
    )


# ======================================================================================
# 3b. Quick Sizing Presets & Share Split
# ======================================================================================

QUICK_PRESET_OPTIONS: List[str] = ["20%", "40%", "60%", "100%", "Custom"]


@dataclass
class QuickSizingResult:
    """Sizes derived from percentage shares (Solar of Consumption, Battery/Generator of overload)."""
    solar_share_pct: float
    battery_share_pct: float
    generator_share_pct: float
    max_overload_kw: float
    largest_overload_event_kwh: float
    solar_kwp: float
    battery_power_kw: float
    battery_capacity_kwh: float
    generator_rated_kw: float


def compute_overload_reference(
    load_kw: np.ndarray, grid_limit_kw: float, step_hours: float = 0.25
) -> Tuple[float, float]:
    """Returns (max overload kW, energy of the largest continuous overload event in kWh)."""
    p = np.maximum(0.0, np.nan_to_num(np.asarray(load_kw, dtype=float), nan=0.0))
    over = np.maximum(0.0, p - float(grid_limit_kw))
    if over.size == 0 or float(np.max(over)) <= 0.0:
        return 0.0, 0.0
    max_kw = float(np.max(over))
    largest = 0.0
    current = 0.0
    for v in over:
        if v > 0.0:
            current += v * step_hours
        else:
            largest = max(largest, current)
            current = 0.0
    largest = max(largest, current)
    return max_kw, float(largest)


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
    rule3 = getattr(rules_cfg, "rule3_charging_sources", "solar_only") if rules_cfg else "solar_only"

    if rule2 == "self_consumption_reserve" and sol_share > 0.0:
        usable_dod = max(0.05, (peak_reserve - min_soc) / 100.0)
    else:
        usable_dod = max(0.05, (max_soc - min_soc) / 100.0)

    allow_grid_rech = (rule3 == "solar_and_grid") or (sol_share <= 0.0)

    # 4. 35,040-Step Cumulative Deficit Integration
    cum_deficit = 0.0
    max_cum_deficit = 0.0
    for i in range(n_steps):
        nl = p_net[i]
        if nl > eff_grid_limit:
            discharge_needed = ((nl - eff_grid_limit) / eta_dis) * dt
            cum_deficit += discharge_needed
            if cum_deficit > max_cum_deficit:
                max_cum_deficit = cum_deficit
        else:
            avail_rech = p_surplus[i]
            if allow_grid_rech:
                avail_rech += max(0.0, eff_grid_limit - nl)
            rech_energy = avail_rech * eta_chg * dt
            cum_deficit = max(0.0, cum_deficit - rech_energy)

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
    )

    if system_cfg.enable_solar and solar_derivation.installed_kwp > 0.0:
        solar_gen_kw = unit_solar_kw * solar_derivation.installed_kwp
    else:
        solar_gen_kw = np.zeros(n_steps, dtype=float)

    # 2. Battery Parameters
    enable_bess = bool(
        system_cfg.enable_battery
        and system_cfg.battery_capacity_kwh > 0.0
        and system_cfg.battery_power_kw > 0.0
    )
    bess_cap_kwh = max(0.0, float(system_cfg.battery_capacity_kwh)) if enable_bess else 0.0
    bess_p_max_kw = max(0.0, float(system_cfg.battery_power_kw)) if enable_bess else 0.0
    min_soc_pct = float(np.clip(system_cfg.min_soc_pct, 0.0, 95.0))
    max_soc_pct = float(np.clip(system_cfg.max_soc_pct, min_soc_pct + 5.0, 100.0))
    rte = float(np.clip(system_cfg.round_trip_efficiency_pct, 50.0, 100.0)) / 100.0
    eta_chg = math.sqrt(rte)
    eta_dis = math.sqrt(rte)

    e_min_kwh = bess_cap_kwh * (min_soc_pct / 100.0)
    e_max_kwh = bess_cap_kwh * (max_soc_pct / 100.0)

    reserve_soc_pct = float(np.clip(rules_cfg.peak_reserve_soc_pct, min_soc_pct, max_soc_pct))
    e_reserve_kwh = bess_cap_kwh * (reserve_soc_pct / 100.0)

    # 3. Generator Parameters
    enable_gen = bool(system_cfg.enable_generator and system_cfg.generator_rated_kw > 0.0)
    gen_rated_kw = max(0.0, float(system_cfg.generator_rated_kw)) if enable_gen else 0.0
    gen_min_pct = float(np.clip(system_cfg.generator_min_load_pct, 0.0, 100.0))
    gen_min_kw = gen_rated_kw * (gen_min_pct / 100.0)
    fuel_spec = FUEL_SPECS.get(system_cfg.fuel_type, FUEL_SPECS["Diesel"])
    fuel_unit = str(fuel_spec["unit"])

    slope_val = float(system_cfg.gen_slope_per_kwh) if system_cfg.gen_slope_per_kwh > 0 else float(fuel_spec["slope_per_kwh"])
    intercept_val = float(system_cfg.gen_intercept_per_kw_rated) if system_cfg.gen_intercept_per_kw_rated >= 0 else float(fuel_spec["intercept_per_kw_rated"])
    min_run_steps = max(1, int(round(float(system_cfg.gen_min_runtime_minutes) / (dt * 60.0))))

    gen_model = GeneratorConfig(
        rated_power_kw=gen_rated_kw,
        fuel_type=system_cfg.fuel_type,
        min_load_ratio_pct=gen_min_pct,
        fuel_curve_slope_l_per_kwh=slope_val,
        fuel_curve_intercept_l_per_kw_rated=intercept_val,
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
    bess_discharge_from_solar_kwh_acc = 0.0
    bess_soc_pct = np.zeros(n_steps, dtype=float)
    bess_energy_kwh = np.zeros(n_steps, dtype=float)

    gen_output_kw = np.zeros(n_steps, dtype=float)
    gen_to_load_kw = np.zeros(n_steps, dtype=float)
    gen_to_bess_kw = np.zeros(n_steps, dtype=float)
    gen_fuel_step = np.zeros(n_steps, dtype=float)
    gen_running_mask = np.zeros(n_steps, dtype=bool)

    grid_import_kw = np.zeros(n_steps, dtype=float)
    unmet_overload_kw = np.zeros(n_steps, dtype=float)

    if enable_bess:
        if rules_cfg.rule2_battery_strategy == "peak_shaving_only":
            cur_e_kwh = (
                e_max_kwh
                if rules_cfg.rule3_charging_sources == "solar_and_grid"
                else (0.5 * (e_min_kwh + e_max_kwh))
            )
        else:
            cur_e_kwh = max(e_min_kwh, e_reserve_kwh)
    else:
        cur_e_kwh = 0.0

    solar_energy_in_bess_kwh = (
        cur_e_kwh
        if (system_cfg.enable_solar and rules_cfg.rule3_charging_sources == "solar_only")
        else 0.0
    )

    rule1 = rules_cfg.rule1_peak_priority
    rule2 = rules_cfg.rule2_battery_strategy
    rule3 = rules_cfg.rule3_charging_sources

    gen_Forced_steps_remaining = 0

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
                    bess_discharge_from_solar_kwh_acc += (step_bess_dis * dt) * solar_share
                    cur_e_kwh = max(e_min_kwh, cur_e_kwh - removed_e)
                    solar_energy_in_bess_kwh = max(0.0, solar_energy_in_bess_kwh - removed_e * solar_share)

                rem_overload_kw = max(0.0, overload_kw - step_bess_dis)

                # 2. Generator covers remaining overload second (or continues if forced by min runtime)
                if (rem_overload_kw > 0.001 or gen_Forced_steps_remaining > 0) and enable_gen:
                    if rem_overload_kw > 0.001 and gen_Forced_steps_remaining == 0:
                        gen_Forced_steps_remaining = min_run_steps
                    req_gen_kw = min(rem_overload_kw, gen_rated_kw)
                    actual_gen_kw = max(req_gen_kw, min(gen_rated_kw, gen_min_kw))
                    step_gen_out = actual_gen_kw
                    step_gen_to_load = min(actual_gen_kw, rem_overload_kw)

                    gen_excess_kw = max(0.0, actual_gen_kw - step_gen_to_load)
                    if gen_excess_kw > 0.0:
                        if rule3 == "solar_and_generator" and enable_bess and step_bess_dis == 0.0 and cur_e_kwh < e_max_kwh:
                            room_ac_kw = (e_max_kwh - cur_e_kwh) / (dt * eta_chg)
                            step_bess_chg_gen = min(gen_excess_kw, rem_bess_chg_power_kw, room_ac_kw)
                            cur_e_kwh += step_bess_chg_gen * dt * eta_chg
                            gen_excess_after_bess = gen_excess_kw - step_bess_chg_gen
                        else:
                            gen_excess_after_bess = gen_excess_kw
                        extra_to_load = min(gen_excess_after_bess, max(0.0, p_rem - step_bess_dis - step_gen_to_load))
                        step_gen_to_load += extra_to_load
                    step_gen_to_bess = step_bess_chg_gen
                    gen_Forced_steps_remaining = max(0, gen_Forced_steps_remaining - 1)

            else:
                # --- "generator_first": Generator first, Battery for fast/small peaks ---
                avail_bess_dis_kw = (
                    ((cur_e_kwh - e_min_kwh) / dt) * eta_dis
                    if (enable_bess and step_bess_chg_solar == 0.0 and cur_e_kwh > e_min_kwh)
                    else 0.0
                )
                avail_bess_dis_kw = min(bess_p_max_kw, avail_bess_dis_kw)

                if (
                    enable_gen
                    and gen_Forced_steps_remaining == 0
                    and (overload_kw < gen_min_kw)
                    and enable_bess
                    and (avail_bess_dis_kw >= overload_kw)
                ):
                    # Battery absorbs small peak below generator minimum load
                    step_bess_dis = overload_kw
                    removed_e = (step_bess_dis * dt) / eta_dis
                    solar_share = (solar_energy_in_bess_kwh / cur_e_kwh) if cur_e_kwh > 0 else 0.0
                    bess_discharge_from_solar_kwh_acc += (step_bess_dis * dt) * solar_share
                    cur_e_kwh = max(e_min_kwh, cur_e_kwh - removed_e)
                    solar_energy_in_bess_kwh = max(0.0, solar_energy_in_bess_kwh - removed_e * solar_share)
                else:
                    # 1. Generator runs first
                    if enable_gen:
                        if gen_Forced_steps_remaining == 0:
                            gen_Forced_steps_remaining = min_run_steps
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
                        gen_Forced_steps_remaining = max(0, gen_Forced_steps_remaining - 1)

                    rem_overload_kw = max(0.0, overload_kw - step_gen_to_load)

                    # 2. Battery covers any remaining peak exceeding Generator rated power
                    if (
                        rem_overload_kw > 0.001
                        and enable_bess
                        and step_bess_chg_solar == 0.0
                        and step_bess_chg_gen == 0.0
                        and cur_e_kwh > e_min_kwh
                    ):
                        avail_dis_ac_kw = ((cur_e_kwh - e_min_kwh) / dt) * eta_dis
                        step_bess_dis = min(rem_overload_kw, bess_p_max_kw, avail_dis_ac_kw)
                        removed_e = (step_bess_dis * dt) / eta_dis
                        solar_share = (solar_energy_in_bess_kwh / cur_e_kwh) if cur_e_kwh > 0 else 0.0
                        bess_discharge_from_solar_kwh_acc += (step_bess_dis * dt) * solar_share
                        cur_e_kwh = max(e_min_kwh, cur_e_kwh - removed_e)
                        solar_energy_in_bess_kwh = max(0.0, solar_energy_in_bess_kwh - removed_e * solar_share)

        else:
            # --- BELOW OR AT GRID LIMIT (Normal Load Region) ---
            # Check if generator must finish its minimum runtime
            if gen_Forced_steps_remaining > 0 and enable_gen:
                actual_gen_kw = min(gen_rated_kw, gen_min_kw)
                step_gen_out = actual_gen_kw
                if rule3 == "solar_and_generator" and enable_bess and cur_e_kwh < e_max_kwh:
                    room_ac_kw = (e_max_kwh - cur_e_kwh) / (dt * eta_chg)
                    step_bess_chg_gen = min(actual_gen_kw, rem_bess_chg_power_kw, room_ac_kw)
                    cur_e_kwh += step_bess_chg_gen * dt * eta_chg
                    rem_gen = actual_gen_kw - step_bess_chg_gen
                else:
                    rem_gen = actual_gen_kw
                step_gen_to_load = min(rem_gen, p_rem)
                step_gen_to_bess = step_bess_chg_gen
                gen_Forced_steps_remaining = max(0, gen_Forced_steps_remaining - 1)

            rem_load_for_bess = max(0.0, p_rem - step_gen_to_load)

            # Rule 2: Self-Consumption + Peak Reserve allows discharging down to e_reserve_kwh
            if (
                rule2 == "self_consumption_reserve"
                and enable_bess
                and step_bess_chg_solar == 0.0
                and step_bess_chg_gen == 0.0
                and rem_load_for_bess > 0.0
                and cur_e_kwh > e_reserve_kwh
            ):
                avail_dis_ac_kw = ((cur_e_kwh - e_reserve_kwh) / dt) * eta_dis
                step_bess_dis = min(rem_load_for_bess, bess_p_max_kw, avail_dis_ac_kw)
                removed_e = (step_bess_dis * dt) / eta_dis
                solar_share = (solar_energy_in_bess_kwh / cur_e_kwh) if cur_e_kwh > 0 else 0.0
                bess_discharge_from_solar_kwh_acc += (step_bess_dis * dt) * solar_share
                cur_e_kwh = max(e_reserve_kwh, cur_e_kwh - removed_e)
                solar_energy_in_bess_kwh = max(0.0, solar_energy_in_bess_kwh - removed_e * solar_share)

            # Rule 3: Battery Grid Recharging within Grid Limit
            if (
                rule3 == "solar_and_grid"
                and enable_bess
                and step_bess_dis == 0.0
                and step_bess_chg_gen == 0.0
                and rem_bess_chg_power_kw > 0.0
            ):
                target_grid_e_kwh = (
                    e_max_kwh
                    if (rule2 == "peak_shaving_only" or not system_cfg.enable_solar)
                    else e_reserve_kwh
                )
                if cur_e_kwh < target_grid_e_kwh:
                    headroom_kw = max(0.0, grid_limit_kw - (p_rem - step_gen_to_load - step_bess_dis))
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
        summary_table_df=summary_df,
        monthly_balance_df=monthly_df,
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
    Builds the purely physical/technical Component & Scenario Summary Table for Tab 2.
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
    """Builds the 12-month technical energy & peak balance table (used for Sheet 3 in Excel)."""
    months = timestamps.month.to_numpy(dtype=int)
    rows = []
    for m_idx in range(1, 13):
        mask = months == m_idx
        if not np.any(mask):
            continue
        m_load = load_kw[mask]
        m_grid = grid_import_kw[mask]
        m_over_base = np.maximum(0.0, m_load - grid_limit_kw)
        m_over_comb = unmet_overload_kw[mask]

        rows.append({
            "Month": MONTH_NAMES_SHORT[m_idx - 1],
            "Consumption (kWh)": round(float(np.sum(m_load) * step_hours), 1),
            "Current situation Peak (kW)": round(float(np.max(m_load)), 1),
            "Current situation Overload (kW)": round(float(np.max(m_over_base)), 1),
            "Solar Generation (kWh)": round(float(np.sum(solar_gen_kw[mask]) * step_hours), 1),
            "Solar Direct (kWh)": round(float(np.sum(solar_direct_kw[mask]) * step_hours), 1),
            "Solar Export (kWh)": round(float(np.sum(solar_export_kw[mask]) * step_hours), 1),
            "Battery Discharge (kWh)": round(float(np.sum(bess_discharge_kw[mask]) * step_hours), 1),
            "Generator Output (kWh)": round(float(np.sum(gen_output_kw[mask]) * step_hours), 1),
            "Generator Runtime (hrs)": round(float(np.sum(gen_running_mask[mask]) * step_hours), 1),
            "Generator Fuel": round(float(np.sum(gen_fuel_step[mask])), 1),
            "Combined Grid Import (kWh)": round(float(np.sum(m_grid) * step_hours), 1),
            "Combined Grid Peak (kW)": round(float(np.max(m_grid)), 1),
            "Remaining Overload (kW)": round(float(np.max(m_over_comb)), 1),
            "Remaining Overload (hrs)": round(float(np.sum(m_over_comb > 0.05) * step_hours), 2),
            "Remaining Overload (kWh)": round(float(np.sum(m_over_comb) * step_hours), 1),
        })
    return pd.DataFrame(rows)


# ======================================================================================
# 6. Decoupled Financial Evaluation Engine (Tab 3 & Excel Sheet 4)
# ======================================================================================

def evaluate_combined_financials(
    sim_res: CombinedSimulationResult,
    fin_cfg: CombinedFinancialConfig,
) -> CombinedSimulationResult:
    """
    Evaluates CAPEX, OPEX, Annual Savings vs. Current situation, Payback, and
    12-month cost comparison for the simulated CombinedSimulationResult.
    """
    cfg = sim_res.system_config
    kpis = sim_res.kpis
    solar_deriv = sim_res.solar_derivation

    # 1. CAPEX
    solar_capex = (solar_deriv.installed_kwp * fin_cfg.solar_capex_eur_kwp) if cfg.enable_solar else 0.0
    battery_capex = (
        cfg.battery_capacity_kwh * fin_cfg.battery_capex_eur_kwh
        + cfg.battery_power_kw * fin_cfg.battery_capex_eur_kw
    ) if cfg.enable_battery else 0.0
    gen_is_purchase = fin_cfg.generator_cost_model == "Purchase (CAPEX)"
    generator_capex = fin_cfg.generator_capex_eur if (cfg.enable_generator and gen_is_purchase) else 0.0
    total_capex = solar_capex + battery_capex + generator_capex

    # 2. Monthly Grid & Operational Costs (12 Months)
    mb_df = sim_res.monthly_balance_df
    monthly_cost_rows = []

    base_energy_sum = 0.0
    base_cap_sum = 0.0
    base_fixed_sum = 0.0
    base_pen_sum = 0.0

    comb_energy_sum = 0.0
    comb_cap_sum = 0.0
    comb_fixed_sum = 0.0
    comb_pen_sum = 0.0
    gen_fuel_cost_sum = 0.0
    gen_maint_cost_sum = 0.0
    gen_rental_cost_sum = 0.0

    solar_om_annual = solar_capex * (fin_cfg.solar_om_pct_of_capex / 100.0)
    battery_om_annual = battery_capex * (fin_cfg.battery_om_pct_of_capex / 100.0)
    om_monthly = (solar_om_annual + battery_om_annual) / 12.0

    for _, row in mb_df.iterrows():
        m_name = str(row["Month"])
        cons_kwh = float(row["Consumption (kWh)"])
        base_over_kw = float(row["Current situation Overload (kW)"])
        comb_imp_kwh = float(row["Combined Grid Import (kWh)"])
        comb_over_kw = float(row["Remaining Overload (kW)"])
        gen_hrs = float(row["Generator Runtime (hrs)"])
        gen_fuel = float(row["Generator Fuel"])

        # Baseline (Current situation)
        b_energy = cons_kwh * fin_cfg.grid_energy_price_eur_kwh
        b_cap = cfg.grid_limit_kw * fin_cfg.grid_capacity_fee_eur_kw_month
        b_fixed = fin_cfg.grid_fixed_fee_eur_month
        b_pen = base_over_kw * fin_cfg.grid_overload_penalty_eur_kw
        b_tot = b_energy + b_cap + b_fixed + b_pen

        # Combined system
        c_energy = comb_imp_kwh * fin_cfg.grid_energy_price_eur_kwh
        c_cap = cfg.grid_limit_kw * fin_cfg.grid_capacity_fee_eur_kw_month
        c_fixed = fin_cfg.grid_fixed_fee_eur_month
        c_pen = comb_over_kw * fin_cfg.grid_overload_penalty_eur_kw
        c_fuel = (gen_fuel * fin_cfg.fuel_price_eur_per_unit) if cfg.enable_generator else 0.0
        c_maint = (gen_hrs * fin_cfg.generator_maintenance_eur_per_hour) if cfg.enable_generator else 0.0
        c_rent = fin_cfg.generator_rental_eur_month if (cfg.enable_generator and not gen_is_purchase) else 0.0
        c_tot = c_energy + c_cap + c_fixed + c_pen + c_fuel + c_maint + c_rent + om_monthly

        base_energy_sum += b_energy
        base_cap_sum += b_cap
        base_fixed_sum += b_fixed
        base_pen_sum += b_pen

        comb_energy_sum += c_energy
        comb_cap_sum += c_cap
        comb_fixed_sum += c_fixed
        comb_pen_sum += c_pen
        gen_fuel_cost_sum += c_fuel
        gen_maint_cost_sum += c_maint
        gen_rental_cost_sum += c_rent

        monthly_cost_rows.append({
            "Month": m_name,
            "Current situation Energy (€)": round(b_energy, 2),
            "Current situation Capacity & Fixed (€)": round(b_cap + b_fixed, 2),
            "Current situation Overload Penalty (€)": round(b_pen, 2),
            "Current situation Total (€)": round(b_tot, 2),
            "Combined Grid Energy (€)": round(c_energy, 2),
            "Combined Capacity & Fixed (€)": round(c_cap + c_fixed, 2),
            "Combined Overload Penalty (€)": round(c_pen, 2),
            "Generator Fuel & Maint & Rental (€)": round(c_fuel + c_maint + c_rent, 2),
            "Solar & Battery O&M (€)": round(om_monthly, 2),
            "Combined System Total OPEX (€)": round(c_tot, 2),
            "Monthly Savings (€)": round(b_tot - c_tot, 2),
        })

    baseline_total_opex = base_energy_sum + base_cap_sum + base_fixed_sum + base_pen_sum
    combined_grid_total = comb_energy_sum + comb_cap_sum + comb_fixed_sum + comb_pen_sum
    gen_total_opex = gen_fuel_cost_sum + gen_maint_cost_sum + gen_rental_cost_sum
    total_annual_opex = combined_grid_total + solar_om_annual + battery_om_annual + gen_total_opex
    annual_savings = baseline_total_opex - total_annual_opex

    if total_capex <= 0.0:
        payback_years = 0.0 if annual_savings >= 0.0 else None
    elif annual_savings > 0.0:
        payback_years = round(total_capex / annual_savings, 1)
    else:
        payback_years = None

    fin_kpis = CombinedFinancialKPIs(
        solar_capex_eur=round(solar_capex, 0),
        battery_capex_eur=round(battery_capex, 0),
        generator_capex_eur=round(generator_capex, 0),
        total_capex_eur=round(total_capex, 0),
        baseline_energy_cost_eur=round(base_energy_sum, 0),
        baseline_capacity_cost_eur=round(base_cap_sum, 0),
        baseline_fixed_cost_eur=round(base_fixed_sum, 0),
        baseline_penalty_cost_eur=round(base_pen_sum, 0),
        baseline_total_opex_eur=round(baseline_total_opex, 0),
        combined_grid_energy_cost_eur=round(comb_energy_sum, 0),
        combined_grid_capacity_cost_eur=round(comb_cap_sum, 0),
        combined_grid_fixed_cost_eur=round(comb_fixed_sum, 0),
        combined_grid_penalty_cost_eur=round(comb_pen_sum, 0),
        combined_grid_total_eur=round(combined_grid_total, 0),
        solar_om_eur=round(solar_om_annual, 0),
        battery_om_eur=round(battery_om_annual, 0),
        generator_fuel_cost_eur=round(gen_fuel_cost_sum, 0),
        generator_maintenance_cost_eur=round(gen_maint_cost_sum, 0),
        generator_rental_cost_eur=round(gen_rental_cost_sum, 0),
        generator_total_opex_eur=round(gen_total_opex, 0),
        total_annual_opex_eur=round(total_annual_opex, 0),
        annual_savings_eur=round(annual_savings, 0),
        payback_years=payback_years,
    )

    denom = max(1.0, kpis.annual_consumption_kwh)
    payback_str = f"{payback_years:.1f} yrs" if payback_years is not None else "N/A"

    fin_rows = [
        {
            "Component": "Grid",
            "Installed Size": f"{kpis.grid_limit_kw:,.0f} kW limit",
            "Energy Supplied (kWh/year & %)": f"{kpis.grid_supplied_to_load_kwh:,.0f} kWh ({(kpis.grid_supplied_to_load_kwh / denom * 100.0):.1f}%)",
            "Investment (CAPEX)": "€0",
            "Annual Operating Cost (OPEX)": f"€{fin_kpis.combined_grid_total_eur:,.0f}",
            "Annual Savings vs. Current situation": f"€{(fin_kpis.baseline_total_opex_eur - fin_kpis.combined_grid_total_eur):,.0f}",
            "Payback (Years)": "—",
        },
        {
            "Component": "Solar",
            "Installed Size": f"{solar_deriv.installed_kwp:,.1f} kWp" if cfg.enable_solar else "0.0 kWp",
            "Energy Supplied (kWh/year & %)": f"{kpis.solar_direct_kwh:,.0f} kWh direct ({kpis.solar_supply_share_pct:.1f}% total)" if cfg.enable_solar else "0 kWh (0.0%)",
            "Investment (CAPEX)": f"€{fin_kpis.solar_capex_eur:,.0f}",
            "Annual Operating Cost (OPEX)": f"€{fin_kpis.solar_om_eur:,.0f}",
            "Annual Savings vs. Current situation": "—",
            "Payback (Years)": "—",
        },
        {
            "Component": "Battery",
            "Installed Size": f"{cfg.battery_capacity_kwh:,.0f} kWh / {cfg.battery_power_kw:,.0f} kW" if cfg.enable_battery else "0 kWh / 0 kW",
            "Energy Supplied (kWh/year & %)": f"{kpis.battery_total_discharged_kwh:,.0f} kWh ({kpis.battery_discharge_share_pct:.1f}%)" if cfg.enable_battery else "0 kWh (0.0%)",
            "Investment (CAPEX)": f"€{fin_kpis.battery_capex_eur:,.0f}",
            "Annual Operating Cost (OPEX)": f"€{fin_kpis.battery_om_eur:,.0f}",
            "Annual Savings vs. Current situation": "—",
            "Payback (Years)": "—",
        },
        {
            "Component": "Generator",
            "Installed Size": f"{cfg.generator_rated_kw:,.0f} kW ({cfg.fuel_type})" if cfg.enable_generator else "0 kW",
            "Energy Supplied (kWh/year & %)": f"{kpis.generator_to_load_kwh:,.0f} kWh ({kpis.generator_supply_share_pct:.1f}%)" if cfg.enable_generator else "0 kWh (0.0%)",
            "Investment (CAPEX)": f"€{fin_kpis.generator_capex_eur:,.0f}",
            "Annual Operating Cost (OPEX)": f"€{fin_kpis.generator_total_opex_eur:,.0f}",
            "Annual Savings vs. Current situation": "—",
            "Payback (Years)": "—",
        },
        {
            "Component": "Combined system",
            "Installed Size": (
                f"Grid {kpis.grid_limit_kw:,.0f} kW + "
                f"Solar {solar_deriv.installed_kwp if cfg.enable_solar else 0.0:,.1f} kWp + "
                f"Battery {cfg.battery_capacity_kwh if cfg.enable_battery else 0.0:,.0f} kWh + "
                f"Generator {cfg.generator_rated_kw if cfg.enable_generator else 0.0:,.0f} kW"
            ),
            "Energy Supplied (kWh/year & %)": f"{kpis.annual_consumption_kwh:,.0f} kWh (100.0%)",
            "Investment (CAPEX)": f"€{fin_kpis.total_capex_eur:,.0f}",
            "Annual Operating Cost (OPEX)": f"€{fin_kpis.total_annual_opex_eur:,.0f}",
            "Annual Savings vs. Current situation": f"€{fin_kpis.annual_savings_eur:,.0f}",
            "Payback (Years)": payback_str,
        },
        {
            "Component": "Current situation",
            "Installed Size": f"Grid Limit {kpis.grid_limit_kw:,.0f} kW (Grid only)",
            "Energy Supplied (kWh/year & %)": f"{kpis.annual_consumption_kwh:,.0f} kWh (100.0%)",
            "Investment (CAPEX)": "€0",
            "Annual Operating Cost (OPEX)": f"€{fin_kpis.baseline_total_opex_eur:,.0f}",
            "Annual Savings vs. Current situation": "Baseline (€0)",
            "Payback (Years)": "—",
        },
    ]

    sim_res.financial_config = fin_cfg
    sim_res.financial_kpis = fin_kpis
    sim_res.financial_table_df = pd.DataFrame(fin_rows)
    sim_res.monthly_cost_df = pd.DataFrame(monthly_cost_rows)
    return sim_res
