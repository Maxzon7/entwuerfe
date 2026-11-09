"""
========================================================================================
Combined System Sandbox Engine (ui_sandbox/Combined_sandbox/combined_sandbox_engine.py)
========================================================================================

Physical 15-minute simulation engine (35,040 steps/year) uniting:
  - Grid (Contracted Grid Limit)
  - Solar (Default GPS: Amsterdam 52.3676, 4.9041; EU PVGIS - ERA5 TMY 15-min generation,
    Inverter AC Limit & Inverter Efficiency)
  - Battery (Dual Sizing: Standalone vs. Coupled, 4-Criterion Bottleneck Diagnostic Table,
    Capacity, Power, SoC envelope, Round-Trip Efficiency, Reserve management)
  - Generator (Dual Sizing: Standalone vs. Coupled, Rated power, Minimum load wet-stacking
    limit, Willans fuel curve, Min runtime)

Controlled via 3 plain-language Operating & Interaction Rules:
  - Rule 1: Peak Shaving Priority (Above Grid Limit, after direct Solar)
      * "battery_first": Battery first, Generator as backup
      * "generator_first": Generator first, Battery for small/fast peaks
  - Rule 2: Normal Load Coverage (Below Grid Limit)
      * "peak_shaving_only": Peak Shaving only
      * "self_consumption_reserve": Self-Consumption + Peak Reserve
  - Rule 3: Battery Charging Sources & Timing
      * "solar_only": Solar surplus only
      * "solar_and_grid": Solar surplus + Grid headroom
      * "solar_and_generator": Solar surplus + Generator excess (Cycle Charging)
      * "all_sources": Solar + Grid + Generator excess

Includes a Lazy-Loaded Financial Evaluation Engine (`evaluate_combined_financials`) with
the 4-Pillar Tariff model, itemized Solar/Battery/Generator costs, optional Year-11
battery augmentation, 15-year cashflow table, and 15-year NPV.
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
    "generator_first": "Generator first, Battery for small/fast peaks",
}

RULE2_OPTIONS: Dict[str, str] = {
    "peak_shaving_only": "Peak Shaving only",
    "self_consumption_reserve": "Self-Consumption + Peak Reserve",
}

RULE3_OPTIONS: Dict[str, str] = {
    "solar_only": "Solar surplus only",
    "solar_and_grid": "Solar surplus + Grid headroom",
    "solar_and_generator": "Solar surplus + Generator excess (Cycle Charging)",
    "all_sources": "Solar + Grid + Generator excess",
}


# ======================================================================================
# 2. Configuration & Result Data Models
# ======================================================================================

@dataclass
class CombinedSystemConfig:
    """Physical/technical configuration for Grid, Solar, Battery, Generator, and Financials flag."""
    # Overview / Grid
    enable_grid: bool = True
    grid_limit_kw: float = 180.0
    enable_financials: bool = False

    # Sub-Tab 2: Solar (Default GPS: Amsterdam 52.3676, 4.9041)
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
    inverter_ac_limit_kw: float = 0.0              # 0.0 = auto from installed_kwp / dc_ac_ratio; >0 = explicit AC limit
    inverter_efficiency_pct: float = 98.0

    # Sub-Tab 3: Battery
    enable_battery: bool = True
    battery_capacity_kwh: float = 300.0
    battery_power_kw: float = 150.0
    min_soc_pct: float = 10.0
    max_soc_pct: float = 90.0
    round_trip_efficiency_pct: float = 88.0

    # Sub-Tab 4: Generator
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
    rule3_charging_sources: str = "solar_only"                # "solar_only" | "solar_and_grid" | "solar_and_generator" | "all_sources"


@dataclass
class CombinedFinancialConfig:
    """
    Financial parameters configured in Sub-Tab 6 (Financials).
    Block A always uses the 4-Pillar Tariff structure:
      - Pillar 1: Energy Supply (Supplier)
      - Pillar 2: Grid Network (DSO)
      - Pillar 3: Metering
      - Pillar 4: Taxes & Levies
    Also supports legacy flat tariff fields for backward compatibility.
    """
    # Pillar 1: Energy Supply (Supplier)
    supplier_energy_price_eur_kwh: float = 0.15
    supplier_fixed_fee_eur_month: float = 50.0

    # Pillar 2: Grid Network (DSO)
    dso_capacity_fee_eur_kw_month: float = 2.50
    dso_peak_demand_fee_eur_kw_month: float = 6.00
    dso_fixed_fee_eur_month: float = 100.0
    dso_transport_eur_kwh: float = 0.025
    grid_overload_penalty_eur_kw: float = 15.00

    # Avoided Grid Upgrade CAPEX & Avoided Transformer Rent OPEX
    avoided_grid_upgrade_capex_eur: float = 0.0
    avoided_transformer_rent_eur_month: float = 0.0

    # Pillar 3: Metering
    metering_fixed_fee_eur_month: float = 45.0

    # Pillar 4: Taxes & Levies
    energy_tax_eur_kwh: float = 0.05
    tax_surcharge_pct: float = 0.0

    # Legacy / Aggregate Tariff Aliases (if set explicitly by tests, used as overrides)
    grid_energy_price_eur_kwh: Optional[float] = None
    grid_capacity_fee_eur_kw_month: Optional[float] = None
    grid_fixed_fee_eur_month: Optional[float] = None

    # Block B: Solar Turnkey Costs
    solar_modules_eur_wp: float = 0.45
    solar_inverter_eur_w: float = 0.12
    solar_mounting_eur_wp: float = 0.28
    solar_capex_eur_kwp: Optional[float] = None
    solar_om_pct_of_capex: float = 1.5

    # Block C: Battery Turnkey Costs, O&M & Mid-Life Augmentation
    battery_capex_eur_kwh: float = 280.0
    battery_capex_eur_kw: float = 150.0
    battery_fixed_bop_eur: float = 15000.0
    battery_om_pct_of_capex: float = 1.5
    enable_battery_augmentation: bool = True
    battery_augmentation_year: int = 11
    battery_augmentation_pct_of_racks: float = 60.0

    # Block D: Generator Purchase vs. Rental & Fuel OPEX
    generator_cost_model: str = "Purchase (CAPEX)"  # "Purchase (CAPEX)" or "Monthly Rental (OPEX)"
    generator_capex_eur: float = 22000.0
    generator_rental_eur_month: float = 1200.0
    fuel_price_eur_per_unit: float = 1.45
    generator_maintenance_eur_per_hour: float = 4.50

    # Lifecycle Discount Rate
    discount_rate_pct: float = 6.0

    @property
    def effective_solar_capex_eur_kwp(self) -> float:
        if self.solar_capex_eur_kwp is not None:
            return float(self.solar_capex_eur_kwp)
        return float((self.solar_modules_eur_wp + self.solar_inverter_eur_w + self.solar_mounting_eur_wp) * 1000.0)


@dataclass
class CombinedFinancialKPIs:
    """Key financial results evaluated in Sub-Tab 6 (vs. Current situation)."""
    # CAPEX
    solar_capex_eur: float = 0.0
    battery_capex_eur: float = 0.0
    battery_augmentation_eur: float = 0.0
    generator_capex_eur: float = 0.0
    gross_capex_eur: float = 0.0
    avoided_grid_upgrade_capex_eur: float = 0.0
    total_capex_eur: float = 0.0

    # Baseline (Current situation) 4-Pillar Annual Costs
    baseline_pillar1_supply_eur: float = 0.0
    baseline_pillar2_dso_eur: float = 0.0
    baseline_pillar3_metering_eur: float = 0.0
    baseline_pillar4_taxes_eur: float = 0.0
    baseline_energy_cost_eur: float = 0.0
    baseline_capacity_cost_eur: float = 0.0
    baseline_fixed_cost_eur: float = 0.0
    baseline_penalty_cost_eur: float = 0.0
    baseline_total_opex_eur: float = 0.0

    # Combined System 4-Pillar + Component Annual OPEX
    combined_pillar1_supply_eur: float = 0.0
    combined_pillar2_dso_eur: float = 0.0
    combined_pillar3_metering_eur: float = 0.0
    combined_pillar4_taxes_eur: float = 0.0
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

    # Savings, Payback & 15Y NPV
    annual_savings_eur: float = 0.0
    payback_years: Optional[float] = None
    npv_15y_eur: float = 0.0


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
    inverter_efficiency_pct: float
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
    """Complete 35,040-step simulation output for the Combined System."""
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
    bess_bottleneck_df: pd.DataFrame = field(default_factory=pd.DataFrame)

    # Financial Evaluation (populated lazily via `evaluate_combined_financials`)
    financial_config: Optional[CombinedFinancialConfig] = None
    financial_kpis: Optional[CombinedFinancialKPIs] = None
    financial_table_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    monthly_cost_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    cashflow_15y_df: pd.DataFrame = field(default_factory=pd.DataFrame)


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
    inverter_ac_limit_kw: float = 0.0,
    inverter_efficiency_pct: float = 98.0,
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

    if inverter_ac_limit_kw and float(inverter_ac_limit_kw) > 0.0:
        inv_ac_kw = round(float(inverter_ac_limit_kw), 1)
    else:
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
        inverter_efficiency_pct=inv_eff,
        expected_annual_yield_kwh=expected_yield_kwh,
        formula_text=formula_text,
        source_info_text=source_info_text,
    )


# ======================================================================================
# 3b. Dual Sizing & 4-Criterion BESS Bottleneck Diagnostics
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


@dataclass
class DualBatterySizingResult:
    """
    Dual Battery Sizing Result comparing:
      - Mode A (Standalone: Battery only)
      - Mode B (Coupled: With active Solar / Generator & Interaction Rules)
    Plus the 4 physical sizing criteria for both modes.
    """
    # Mode A: Standalone (Battery only)
    standalone_100_kw: float
    standalone_100_kwh: float
    standalone_80_kw: float
    standalone_80_kwh: float
    standalone_50_kw: float
    standalone_50_kwh: float
    standalone_usable_kwh: float
    standalone_cluster_duration_hrs: float

    # Mode B: Coupled (With active Solar / Generator & Rules)
    coupled_100_kw: float
    coupled_100_kwh: float
    coupled_80_kw: float
    coupled_80_kwh: float
    coupled_50_kw: float
    coupled_50_kwh: float
    coupled_usable_kwh: float
    coupled_cluster_duration_hrs: float

    # 4 Physical Criteria (Standalone vs. Coupled)
    standalone_peak_discharge_kw: float
    coupled_peak_discharge_kw: float

    standalone_single_event_kwh: float
    coupled_single_event_kwh: float

    standalone_multiday_cluster_kwh: float
    coupled_multiday_cluster_kwh: float

    standalone_recharge_headroom_kw: float
    standalone_recharge_headroom_kwh: float
    coupled_recharge_headroom_kw: float
    coupled_recharge_headroom_kwh: float

    controlling_driver_standalone: str
    controlling_driver_coupled: str
    bottleneck_table_df: pd.DataFrame = field(default_factory=pd.DataFrame)


@dataclass
class DualGeneratorSizingResult:
    """
    Dual Generator Sizing Result comparing:
      - Mode A (Standalone: Generator only, sized to full unmitigated peak above Grid Limit)
      - Mode B (Coupled: Sized to residual peak remaining after active Solar & Battery)
    """
    standalone_100_kw: float
    standalone_80_kw: float
    standalone_50_kw: float

    coupled_100_kw: float
    coupled_80_kw: float
    coupled_50_kw: float

    # Diagnostic Metrics (Mode A Standalone vs Mode B Coupled)
    standalone_energy_mwh: float = 0.0
    standalone_runtime_hours: float = 0.0
    standalone_longest_run_hours: float = 0.0
    standalone_fuel_tank_liters: float = 0.0

    coupled_energy_mwh: float = 0.0
    coupled_runtime_hours: float = 0.0
    coupled_longest_run_hours: float = 0.0
    coupled_fuel_tank_liters: float = 0.0


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

    max_rech_kw = float(np.max(avail_rech_kw_arr)) if n > 0 else 0.0
    total_rech_kwh = float(np.sum(avail_rech_kw_arr) * eta_chg * dt)
    total_req_chem_kwh = float(np.sum(np.maximum(0.0, p - lim) / eta_dis) * dt)

    chg_cap_kw = float(peak_kw) if peak_kw > 0.0 else lim
    cum_def = 0.0
    max_cum_def = 0.0
    curr_cluster_steps = 0
    worst_cluster_steps = 0
    for i in range(n):
        nl = p[i]
        if nl > lim:
            cum_def += ((nl - lim) / eta_dis) * dt
            curr_cluster_steps += 1
            if cum_def > max_cum_def:
                max_cum_def = cum_def
            if curr_cluster_steps > worst_cluster_steps:
                worst_cluster_steps = curr_cluster_steps
        else:
            rech_e = min(avail_rech_kw_arr[i], chg_cap_kw) * eta_chg * dt
            cum_def = max(0.0, cum_def - rech_e)
            if cum_def <= 1e-6:
                curr_cluster_steps = 0
            else:
                curr_cluster_steps += 1
                if curr_cluster_steps > worst_cluster_steps:
                    worst_cluster_steps = curr_cluster_steps

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
) -> DualBatterySizingResult:
    """
    Computes both Mode A (Standalone: Battery only) and Mode B (Coupled: With active Solar,
    active Generator, and Interaction Rules) battery sizing along with the 4-Criterion
    Bottleneck Diagnostic Table.
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
        )
        p_solar = unit_solar_kw * deriv.installed_kwp * (deriv.inverter_efficiency_pct / 98.0)
        if deriv.inverter_ac_kw > 0.0:
            p_solar = np.minimum(p_solar, deriv.inverter_ac_kw)
    else:
        p_solar = np.zeros(n_steps, dtype=float)

    p_direct = np.minimum(p_load, p_solar)
    p_after_solar = np.maximum(0.0, p_load - p_direct)
    p_surplus = np.maximum(0.0, p_solar - p_direct)

    # Account for active Generator if enabled
    gen_Excess_chg = np.zeros(n_steps, dtype=float)
    if system_cfg.enable_generator and system_cfg.generator_rated_kw > 0.0:
        g_rated = float(system_cfg.generator_rated_kw)
        g_min = g_rated * (float(system_cfg.generator_min_load_pct) / 100.0)
        p_for_bess = p_after_solar.copy()
        over_arr = np.maximum(0.0, p_after_solar - grid_limit)
        if rules_cfg.rule1_peak_priority == "generator_first":
            # Generator takes peaks >= g_min up to g_rated; Battery handles small peaks < g_min and peaks > g_rated
            for idx in range(n_steps):
                ov = over_arr[idx]
                if ov >= g_min:
                    g_out = min(ov, g_rated)
                    p_for_bess[idx] = grid_limit + max(0.0, ov - g_out)
        else:
            # Battery first, Generator as backup: Generator caps overload above what it can cover
            for idx in range(n_steps):
                ov = over_arr[idx]
                if ov > 0.0:
                    g_assist = min(ov, g_rated)
                    p_for_bess[idx] = grid_limit + max(0.0, ov - g_assist)
                    if g_assist < g_min and rules_cfg.rule3_charging_sources in ("solar_and_generator", "all_sources"):
                        gen_Excess_chg[idx] = g_min - g_assist
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
    )
    cp_100_kw = round(math.ceil(cp_peak_kw * 10.0) / 10.0, 1) if cp_peak_kw > 0.05 else 0.0
    cp_100_kwh = float(math.ceil(cp_cluster_kwh))

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
        standalone_80_kw=round(sa_100_kw * 0.80, 1),
        standalone_80_kwh=round(sa_100_kwh * 0.80, 1),
        standalone_50_kw=round(sa_100_kw * 0.50, 1),
        standalone_50_kwh=round(sa_100_kwh * 0.50, 1),
        standalone_usable_kwh=sa_usable_kwh,
        standalone_cluster_duration_hrs=sa_cluster_duration_hrs,
        coupled_100_kw=cp_100_kw,
        coupled_100_kwh=cp_100_kwh,
        coupled_80_kw=round(cp_100_kw * 0.80, 1),
        coupled_80_kwh=round(cp_100_kwh * 0.80, 1),
        coupled_50_kw=round(cp_100_kw * 0.50, 1),
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
    timestamps: pd.DatetimeIndex,
    system_cfg: CombinedSystemConfig,
    rules_cfg: InteractionRulesConfig,
    step_hours: float = 0.25,
) -> DualGeneratorSizingResult:
    """
    Computes Dual Sizing for the Generator:
      - Mode A (Standalone: Generator only): Sized to full unmitigated peak overload above Grid Limit.
      - Mode B (Coupled: With active Solar / Battery & Interaction Rules): Sized to the residual peak
        that remains after Solar and Battery dispatch.
    """
    p_load = np.maximum(0.0, np.nan_to_num(np.asarray(load_kw, dtype=float), nan=0.0))
    grid_limit = float(system_cfg.grid_limit_kw) if system_cfg.enable_grid else 0.0
    raw_over_kw, _ = compute_overload_reference(p_load, grid_limit, step_hours)
    sa_100 = round(math.ceil(raw_over_kw * 10.0) / 10.0, 1) if raw_over_kw > 0.05 else 0.0

    # Diagnostic metrics for Standalone Generator
    over_sa = np.maximum(0.0, p_load - grid_limit)
    sa_kwh = float(np.sum(over_sa) * step_hours)
    sa_mwh = round(sa_kwh / 1000.0, 1)
    sa_is_over = over_sa > 0.05
    sa_runtime_hrs = round(float(np.sum(sa_is_over) * step_hours), 1)

    sa_cur_steps = 0
    sa_max_steps = 0
    for val in sa_is_over:
        if val:
            sa_cur_steps += 1
            if sa_cur_steps > sa_max_steps:
                sa_max_steps = sa_cur_steps
        else:
            sa_cur_steps = 0
    sa_longest_hrs = round(float(sa_max_steps * step_hours), 1)

    slope = float(system_cfg.gen_slope_per_kwh)
    intercept = float(system_cfg.gen_intercept_per_kw_rated)
    sa_event_fuel = (slope * raw_over_kw + intercept * sa_100) * sa_longest_hrs
    sa_avg_kw = (sa_kwh / max(0.1, sa_runtime_hrs)) if sa_runtime_hrs > 0 else (sa_100 * 0.5)
    sa_reserve_48h = (slope * sa_avg_kw + intercept * sa_100) * 48.0
    sa_tank = round(max(100.0, sa_event_fuel + sa_reserve_48h), 0) if sa_100 > 0 else 0.0

    # Simulate with Generator disabled to measure exact residual peak left after active Solar & Battery
    cfg_no_gen = CombinedSystemConfig(
        enable_grid=system_cfg.enable_grid,
        grid_limit_kw=system_cfg.grid_limit_kw,
        enable_solar=system_cfg.enable_solar,
        site_preset=system_cfg.site_preset,
        latitude=system_cfg.latitude,
        longitude=system_cfg.longitude,
        elevation_m=system_cfg.elevation_m,
        tilt_deg=system_cfg.tilt_deg,
        azimuth_deg=system_cfg.azimuth_deg,
        solar_sizing_method=system_cfg.solar_sizing_method,
        solar_kwp=system_cfg.solar_kwp,
        panel_wp=system_cfg.panel_wp,
        dc_ac_ratio=system_cfg.dc_ac_ratio,
        target_consumption_share_pct=system_cfg.target_consumption_share_pct,
        inverter_ac_limit_kw=system_cfg.inverter_ac_limit_kw,
        inverter_efficiency_pct=system_cfg.inverter_efficiency_pct,
        enable_battery=system_cfg.enable_battery,
        battery_capacity_kwh=system_cfg.battery_capacity_kwh,
        battery_power_kw=system_cfg.battery_power_kw,
        min_soc_pct=system_cfg.min_soc_pct,
        max_soc_pct=system_cfg.max_soc_pct,
        round_trip_efficiency_pct=system_cfg.round_trip_efficiency_pct,
        enable_generator=False,
        generator_rated_kw=0.0,
    )
    res_no_gen = simulate_combined_system_dispatch(
        load_kw=p_load,
        timestamps=timestamps,
        system_cfg=cfg_no_gen,
        rules_cfg=rules_cfg,
        step_hours=step_hours,
    )
    rem_over_kw = float(res_no_gen.kpis.remaining_overload_kw)
    cp_100 = round(math.ceil(rem_over_kw * 10.0) / 10.0, 1) if rem_over_kw > 0.05 else 0.0

    # Diagnostic metrics for Coupled Generator
    over_cp = np.maximum(0.0, res_no_gen.unmet_overload_kw)
    cp_kwh = float(np.sum(over_cp) * step_hours)
    cp_mwh = round(cp_kwh / 1000.0, 1)
    cp_is_over = over_cp > 0.05
    cp_runtime_hrs = round(float(np.sum(cp_is_over) * step_hours), 1)

    cp_cur_steps = 0
    cp_max_steps = 0
    for val in cp_is_over:
        if val:
            cp_cur_steps += 1
            if cp_cur_steps > cp_max_steps:
                cp_max_steps = cp_cur_steps
        else:
            cp_cur_steps = 0
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

    allow_grid_rech = (rule3 in ("solar_and_grid", "all_sources")) or (sol_share <= 0.0)

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

    rule1 = rules_cfg.rule1_peak_priority
    rule2 = rules_cfg.rule2_battery_strategy
    rule3 = rules_cfg.rule3_charging_sources

    allow_grid_chg = rule3 in ("solar_and_grid", "all_sources")
    allow_gen_chg = rule3 in ("solar_and_generator", "all_sources")

    if enable_bess:
        if rule2 == "peak_shaving_only":
            cur_e_kwh = (
                e_max_kwh
                if allow_grid_chg
                else (0.5 * (e_min_kwh + e_max_kwh))
            )
        else:
            cur_e_kwh = max(e_min_kwh, e_reserve_kwh)
    else:
        cur_e_kwh = 0.0

    solar_energy_in_bess_kwh = (
        cur_e_kwh
        if (system_cfg.enable_solar and rule3 == "solar_only")
        else 0.0
    )

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
                        if allow_gen_chg and enable_bess and step_bess_dis == 0.0 and cur_e_kwh < e_max_kwh:
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
                            if allow_gen_chg and enable_bess and cur_e_kwh < e_max_kwh:
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
            if gen_Forced_steps_remaining > 0 and enable_gen:
                actual_gen_kw = min(gen_rated_kw, gen_min_kw)
                step_gen_out = actual_gen_kw
                if allow_gen_chg and enable_bess and cur_e_kwh < e_max_kwh:
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
                allow_grid_chg
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
# 6. Lazy-Loaded Financial Evaluation Engine (4-Pillar Tariff + 15-Year Lifecycle)
# ======================================================================================

def evaluate_combined_financials(
    sim_res: CombinedSimulationResult,
    fin_cfg: CombinedFinancialConfig,
) -> CombinedSimulationResult:
    """
    Evaluates the 4-Pillar Tariff costs (Supplier, DSO, Metering, Taxes), itemized component
    CAPEX & OPEX, Annual Net Savings vs. Current situation, Simple Payback, 15-Year NPV, and
    the 15-Year Cashflow Table.
    """
    cfg = sim_res.system_config
    kpis = sim_res.kpis
    solar_deriv = sim_res.solar_derivation

    # 1. Itemized Turnkey CAPEX
    solar_capex_kwp = fin_cfg.effective_solar_capex_eur_kwp
    solar_capex = (solar_deriv.installed_kwp * solar_capex_kwp) if cfg.enable_solar else 0.0

    battery_rack_capex = cfg.battery_capacity_kwh * fin_cfg.battery_capex_eur_kwh if cfg.enable_battery else 0.0
    battery_inv_capex = cfg.battery_power_kw * fin_cfg.battery_capex_eur_kw if cfg.enable_battery else 0.0
    battery_bop_capex = fin_cfg.battery_fixed_bop_eur if (cfg.enable_battery and cfg.battery_capacity_kwh > 0) else 0.0
    battery_capex = (battery_rack_capex + battery_inv_capex + battery_bop_capex) if cfg.enable_battery else 0.0

    battery_aug_eur = (
        battery_rack_capex * (fin_cfg.battery_augmentation_pct_of_racks / 100.0)
        if (cfg.enable_battery and fin_cfg.enable_battery_augmentation)
        else 0.0
    )

    gen_is_purchase = fin_cfg.generator_cost_model == "Purchase (CAPEX)"
    generator_capex = fin_cfg.generator_capex_eur if (cfg.enable_generator and gen_is_purchase) else 0.0
    gross_capex = solar_capex + battery_capex + generator_capex
    avoided_upgrade_capex = max(0.0, float(fin_cfg.avoided_grid_upgrade_capex_eur))
    net_total_capex = max(0.0, gross_capex - avoided_upgrade_capex)
    total_capex = net_total_capex

    # 2. Resolve 4-Pillar Rates
    if fin_cfg.grid_energy_price_eur_kwh is not None:
        supp_kwh_rate = float(fin_cfg.grid_energy_price_eur_kwh)
        tax_kwh_rate = 0.0
    else:
        supp_kwh_rate = float(fin_cfg.supplier_energy_price_eur_kwh)
        tax_kwh_rate = float(fin_cfg.energy_tax_eur_kwh)

    if fin_cfg.grid_capacity_fee_eur_kw_month is not None:
        dso_cap_rate = float(fin_cfg.grid_capacity_fee_eur_kw_month)
        dso_peak_rate = 0.0
    else:
        dso_cap_rate = float(fin_cfg.dso_capacity_fee_eur_kw_month)
        dso_peak_rate = float(fin_cfg.dso_peak_demand_fee_eur_kw_month)

    if fin_cfg.grid_fixed_fee_eur_month is not None:
        supp_fixed_mo = 0.0
        dso_fixed_mo = float(fin_cfg.grid_fixed_fee_eur_month)
        meter_fixed_mo = 0.0
    else:
        supp_fixed_mo = float(fin_cfg.supplier_fixed_fee_eur_month)
        dso_fixed_mo = float(fin_cfg.dso_fixed_fee_eur_month)
        meter_fixed_mo = float(fin_cfg.metering_fixed_fee_eur_month)

    pen_rate_kw = float(fin_cfg.grid_overload_penalty_eur_kw)
    tax_pct = float(fin_cfg.tax_surcharge_pct) / 100.0
    dso_vol_rate = float(fin_cfg.dso_transport_eur_kwh)
    trafo_rent_mo = float(fin_cfg.avoided_transformer_rent_eur_month)

    # 3. Monthly 4-Pillar Grid & Operational Costs (12 Months)
    mb_df = sim_res.monthly_balance_df
    monthly_cost_rows = []

    base_p1_sum = 0.0
    base_p2_sum = 0.0
    base_p3_sum = 0.0
    base_p4_sum = 0.0
    base_pen_sum = 0.0

    comb_p1_sum = 0.0
    comb_p2_sum = 0.0
    comb_p3_sum = 0.0
    comb_p4_sum = 0.0
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
        base_peak_kw = float(row["Current situation Peak (kW)"])
        base_over_kw = float(row["Current situation Overload (kW)"])

        comb_imp_kwh = float(row["Combined Grid Import (kWh)"])
        comb_peak_kw = float(row["Combined Grid Peak (kW)"])
        comb_over_kw = float(row["Remaining Overload (kW)"])
        gen_hrs = float(row["Generator Runtime (hrs)"])
        gen_fuel = float(row["Generator Fuel"])

        # Baseline (Current situation) 4 Pillars
        b_p1 = cons_kwh * supp_kwh_rate + supp_fixed_mo
        b_pen = base_over_kw * pen_rate_kw
        b_p2 = (cfg.grid_limit_kw * dso_cap_rate) + (base_peak_kw * dso_peak_rate) + dso_fixed_mo + (cons_kwh * dso_vol_rate) + trafo_rent_mo + b_pen
        b_p3 = meter_fixed_mo
        b_p4 = (cons_kwh * tax_kwh_rate) + (b_p1 + b_p2 + b_p3) * tax_pct
        b_tot = b_p1 + b_p2 + b_p3 + b_p4

        # Combined system 4 Pillars + Component OPEX
        c_p1 = comb_imp_kwh * supp_kwh_rate + supp_fixed_mo
        c_pen = comb_over_kw * pen_rate_kw
        c_p2 = (cfg.grid_limit_kw * dso_cap_rate) + (comb_peak_kw * dso_peak_rate) + dso_fixed_mo + (comb_imp_kwh * dso_vol_rate) + c_pen
        c_p3 = meter_fixed_mo
        c_p4 = (comb_imp_kwh * tax_kwh_rate) + (c_p1 + c_p2 + c_p3) * tax_pct

        c_fuel = (gen_fuel * fin_cfg.fuel_price_eur_per_unit) if cfg.enable_generator else 0.0
        c_maint = (gen_hrs * fin_cfg.generator_maintenance_eur_per_hour) if cfg.enable_generator else 0.0
        c_rent = fin_cfg.generator_rental_eur_month if (cfg.enable_generator and not gen_is_purchase) else 0.0
        c_tot = c_p1 + c_p2 + c_p3 + c_p4 + c_fuel + c_maint + c_rent + om_monthly

        base_p1_sum += b_p1
        base_p2_sum += b_p2
        base_p3_sum += b_p3
        base_p4_sum += b_p4
        base_pen_sum += b_pen

        comb_p1_sum += c_p1
        comb_p2_sum += c_p2
        comb_p3_sum += c_p3
        comb_p4_sum += c_p4
        comb_pen_sum += c_pen

        gen_fuel_cost_sum += c_fuel
        gen_maint_cost_sum += c_maint
        gen_rental_cost_sum += c_rent

        monthly_cost_rows.append({
            "Month": m_name,
            "Current situation Energy & Taxes (€)": round(b_p1 - supp_fixed_mo + b_p4, 2),
            "Current situation Network & Standing (€)": round(b_p2 - b_pen + supp_fixed_mo + b_p3, 2),
            "Current situation Overload Penalty (€)": round(b_pen, 2),
            "Current situation Total (€)": round(b_tot, 2),
            "Combined Grid Energy & Taxes (€)": round(c_p1 - supp_fixed_mo + c_p4, 2),
            "Combined Network & Standing (€)": round(c_p2 - c_pen + supp_fixed_mo + c_p3, 2),
            "Combined Overload Penalty (€)": round(c_pen, 2),
            "Generator Fuel & Maint & Rental (€)": round(c_fuel + c_maint + c_rent, 2),
            "Solar & Battery O&M (€)": round(om_monthly, 2),
            "Combined System Total OPEX (€)": round(c_tot, 2),
            "Monthly Savings (€)": round(b_tot - c_tot, 2),
        })

    baseline_total_opex = base_p1_sum + base_p2_sum + base_p3_sum + base_p4_sum
    combined_grid_total = comb_p1_sum + comb_p2_sum + comb_p3_sum + comb_p4_sum
    gen_total_opex = gen_fuel_cost_sum + gen_maint_cost_sum + gen_rental_cost_sum
    total_annual_opex = combined_grid_total + solar_om_annual + battery_om_annual + gen_total_opex
    annual_savings = baseline_total_opex - total_annual_opex

    if total_capex <= 0.0:
        payback_years = 0.0 if annual_savings >= 0.0 else None
    elif annual_savings > 0.0:
        payback_years = round(total_capex / annual_savings, 1)
    else:
        payback_years = None

    # 4. 15-Year Lifecycle Cashflow & NPV Calculation
    r_disc = max(0.0, float(fin_cfg.discount_rate_pct)) / 100.0
    aug_yr = int(fin_cfg.battery_augmentation_year)
    cashflow_rows = []
    cum_cf = -total_capex
    npv_acc = -total_capex

    cashflow_rows.append({
        "Year": 0,
        "Investment & Augmentation (€)": round(-total_capex, 0),
        "Current situation Bill (€)": 0.0,
        "Combined System OPEX (€)": 0.0,
        "Annual Net Savings (€)": 0.0,
        "Net Cashflow (€)": round(-total_capex, 0),
        "Cumulative Cashflow (€)": round(cum_cf, 0),
        "Discounted Cashflow (€)": round(-total_capex, 0),
    })

    for yr in range(1, 16):
        yr_aug = -battery_aug_eur if (battery_aug_eur > 0.0 and yr == aug_yr) else 0.0
        net_cf = annual_savings + yr_aug
        cum_cf += net_cf
        disc_cf = net_cf / ((1.0 + r_disc) ** yr)
        npv_acc += disc_cf
        cashflow_rows.append({
            "Year": yr,
            "Investment & Augmentation (€)": round(yr_aug, 0),
            "Current situation Bill (€)": round(baseline_total_opex, 0),
            "Combined System OPEX (€)": round(total_annual_opex, 0),
            "Annual Net Savings (€)": round(annual_savings, 0),
            "Net Cashflow (€)": round(net_cf, 0),
            "Cumulative Cashflow (€)": round(cum_cf, 0),
            "Discounted Cashflow (€)": round(disc_cf, 0),
        })

    fin_kpis = CombinedFinancialKPIs(
        solar_capex_eur=round(solar_capex, 0),
        battery_capex_eur=round(battery_capex, 0),
        battery_augmentation_eur=round(battery_aug_eur, 0),
        generator_capex_eur=round(generator_capex, 0),
        gross_capex_eur=round(gross_capex, 0),
        avoided_grid_upgrade_capex_eur=round(avoided_upgrade_capex, 0),
        total_capex_eur=round(total_capex, 0),
        baseline_pillar1_supply_eur=round(base_p1_sum, 0),
        baseline_pillar2_dso_eur=round(base_p2_sum, 0),
        baseline_pillar3_metering_eur=round(base_p3_sum, 0),
        baseline_pillar4_taxes_eur=round(base_p4_sum, 0),
        baseline_energy_cost_eur=round(base_p1_sum + base_p4_sum - 12.0 * supp_fixed_mo, 0),
        baseline_capacity_cost_eur=round(base_p2_sum - base_pen_sum - 12.0 * dso_fixed_mo, 0),
        baseline_fixed_cost_eur=round(12.0 * (supp_fixed_mo + dso_fixed_mo + meter_fixed_mo), 0),
        baseline_penalty_cost_eur=round(base_pen_sum, 0),
        baseline_total_opex_eur=round(baseline_total_opex, 0),
        combined_pillar1_supply_eur=round(comb_p1_sum, 0),
        combined_pillar2_dso_eur=round(comb_p2_sum, 0),
        combined_pillar3_metering_eur=round(comb_p3_sum, 0),
        combined_pillar4_taxes_eur=round(comb_p4_sum, 0),
        combined_grid_energy_cost_eur=round(comb_p1_sum + comb_p4_sum - 12.0 * supp_fixed_mo, 0),
        combined_grid_capacity_cost_eur=round(comb_p2_sum - comb_pen_sum - 12.0 * dso_fixed_mo, 0),
        combined_grid_fixed_cost_eur=round(12.0 * (supp_fixed_mo + dso_fixed_mo + meter_fixed_mo), 0),
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
        npv_15y_eur=round(npv_acc, 0),
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
    sim_res.cashflow_15y_df = pd.DataFrame(cashflow_rows)
    return sim_res


# ======================================================================================
# 7. Utility Tariff Preset Catalogs & 1-Click Template Loader
# ======================================================================================

UTILITY_DSO_PRESETS: Dict[str, Dict[str, Dict[str, float]]] = {
    "Enexis Netbeheer B.V.": {
        "MS-D (125 t/m 1.500 kW)": {
            "capacity_fee_kw_mo": 2.44,
            "peak_fee_kw_mo": 3.71,
            "fixed_fee_mo": round((1653.0 + 441.0) / 12.0, 2),  # €174.50/mo
            "transport_eur_kwh": 0.025,
            "penalty_kw": 15.00,
        },
        "MS/LS (> 50 t/m 125 kW)": {
            "capacity_fee_kw_mo": 4.20,
            "peak_fee_kw_mo": 3.71,
            "fixed_fee_mo": round((381.0 + 441.0) / 12.0, 2),   # €68.50/mo
            "transport_eur_kwh": 0.025,
            "penalty_kw": 15.00,
        },
        "LS (t/m 50 kW)": {
            "capacity_fee_kw_mo": 1.34,
            "peak_fee_kw_mo": 0.00,
            "fixed_fee_mo": round((381.0 + 18.0) / 12.0, 2),    # €33.25/mo
            "transport_eur_kwh": 0.061,
            "penalty_kw": 15.00,
        },
        "MS-T (> 1.500 kW)": {
            "capacity_fee_kw_mo": 2.31,
            "peak_fee_kw_mo": 3.10,
            "fixed_fee_mo": round((1653.0 + 441.0) / 12.0, 2),  # €174.50/mo
            "transport_eur_kwh": 0.015,
            "penalty_kw": 15.00,
        },
    },
    "Liander Netbeheer B.V.": {
        "MS-D (125 t/m 1.500 kW)": {
            "capacity_fee_kw_mo": 2.50,
            "peak_fee_kw_mo": 3.65,
            "fixed_fee_mo": round((1620.0 + 430.0) / 12.0, 2),  # €170.83/mo
            "transport_eur_kwh": 0.024,
            "penalty_kw": 15.00,
        },
        "MS/LS (> 50 t/m 125 kW)": {
            "capacity_fee_kw_mo": 4.15,
            "peak_fee_kw_mo": 3.65,
            "fixed_fee_mo": round((375.0 + 430.0) / 12.0, 2),   # €67.08/mo
            "transport_eur_kwh": 0.024,
            "penalty_kw": 15.00,
        },
        "LS (t/m 50 kW)": {
            "capacity_fee_kw_mo": 1.40,
            "peak_fee_kw_mo": 0.00,
            "fixed_fee_mo": round((375.0 + 18.0) / 12.0, 2),    # €32.75/mo
            "transport_eur_kwh": 0.058,
            "penalty_kw": 15.00,
        },
        "MS-T (> 1.500 kW)": {
            "capacity_fee_kw_mo": 2.25,
            "peak_fee_kw_mo": 3.05,
            "fixed_fee_mo": round((1620.0 + 430.0) / 12.0, 2),  # €170.83/mo
            "transport_eur_kwh": 0.014,
            "penalty_kw": 15.00,
        },
    },
    "Stedin Netbeheer B.V.": {
        "MS (125 t/m 1.500 kW)": {
            "capacity_fee_kw_mo": 2.40,
            "peak_fee_kw_mo": 3.80,
            "fixed_fee_mo": round((1590.0 + 450.0) / 12.0, 2),  # €170.00/mo
            "transport_eur_kwh": 0.026,
            "penalty_kw": 15.00,
        },
        "Trafo MS/LS (> 50 t/m 125 kW)": {
            "capacity_fee_kw_mo": 4.25,
            "peak_fee_kw_mo": 3.80,
            "fixed_fee_mo": round((390.0 + 450.0) / 12.0, 2),   # €70.00/mo
            "transport_eur_kwh": 0.026,
            "penalty_kw": 15.00,
        },
        "LS (t/m 50 kW)": {
            "capacity_fee_kw_mo": 1.55,
            "peak_fee_kw_mo": 0.00,
            "fixed_fee_mo": round((74.44 + 18.0) / 12.0, 2),    # €7.70/mo
            "transport_eur_kwh": 0.060,
            "penalty_kw": 15.00,
        },
        "Trafo HS+TS/MS (> 1.500 kW)": {
            "capacity_fee_kw_mo": 3.79,
            "peak_fee_kw_mo": 5.30,
            "fixed_fee_mo": round((3642.0 + 2760.0) / 12.0, 2), # €533.50/mo
            "transport_eur_kwh": 0.012,
            "penalty_kw": 15.00,
        },
    },
    "EDEMSA Mendoza (Single-Utility)": {
        "T2 RMT (Bodegas Salentein 430 kW)": {
            "capacity_fee_kw_mo": 32.50,
            "peak_fee_kw_mo": 6.80,
            "fixed_fee_mo": 411.00,
            "transport_eur_kwh": 0.054,
            "penalty_kw": 32.50,
        },
    },
}

UTILITY_SUPPLIER_PRESETS: Dict[str, Dict[str, Dict[str, float]]] = {
    "Vattenfall Zakelijk": {
        "Vast 1 Jaar (Dubbeltarief HT/NT)": {
            "energy_price_eur_kwh": 0.125,
            "fixed_fee_mo": round(180.0 / 12.0, 2),  # €15.00/mo
        },
        "Vast 3 Jaar (Zekerheid)": {
            "energy_price_eur_kwh": 0.121,
            "fixed_fee_mo": round(195.0 / 12.0, 2),  # €16.25/mo
        },
        "Dynamisch EPEX Spot Zakelijk": {
            "energy_price_eur_kwh": 0.120,
            "fixed_fee_mo": round(180.0 / 12.0, 2),  # €15.00/mo
        },
    },
    "Eneco Zakelijk": {
        "Vast 1 Jaar (Dubbeltarief HT/NT)": {
            "energy_price_eur_kwh": 0.127,
            "fixed_fee_mo": round(160.0 / 12.0, 2),  # €13.33/mo
        },
        "Vast 3 Jaar (Zekerheid)": {
            "energy_price_eur_kwh": 0.122,
            "fixed_fee_mo": round(175.0 / 12.0, 2),  # €14.58/mo
        },
    },
    "Essent Zakelijk": {
        "Vast 1 Jaar (Dubbeltarief HT/NT)": {
            "energy_price_eur_kwh": 0.123,
            "fixed_fee_mo": round(190.0 / 12.0, 2),  # €15.83/mo
        },
        "Vast 3 Jaar (Zekerheid)": {
            "energy_price_eur_kwh": 0.120,
            "fixed_fee_mo": round(205.0 / 12.0, 2),  # €17.08/mo
        },
    },
    "Shell Energy": {
        "Direct Fixed 1-Year": {
            "energy_price_eur_kwh": 0.126,
            "fixed_fee_mo": round(200.0 / 12.0, 2),  # €16.67/mo
        },
    },
}

UTILITY_METERING_PRESETS: Dict[str, Dict[str, Dict[str, float]]] = {
    "Fudura B.V.": {
        "Kwartierdata Telemetrie MS (Grootverbruik RLM)": {
            "fixed_fee_mo": round(900.0 / 12.0, 2),   # €75.00/mo
        },
        "Meettransformatoren MS (Trafo CT/VT)": {
            "fixed_fee_mo": round(1550.0 / 12.0, 2),  # €129.17/mo
        },
        "Kleinverbruik / Tussenmeting": {
            "fixed_fee_mo": round(420.0 / 12.0, 2),   # €35.00/mo
        },
    },
    "Joulz Meetbedrijf": {
        "Grootverbruik Telemetrie MS": {
            "fixed_fee_mo": round(850.0 / 12.0, 2),   # €70.83/mo
        },
        "Meettransformatoren MS": {
            "fixed_fee_mo": round(1480.0 / 12.0, 2),  # €123.33/mo
        },
    },
    "Kenter B.V.": {
        "Grootverbruik Kwartierdata Telemetrie": {
            "fixed_fee_mo": round(880.0 / 12.0, 2),   # €73.33/mo
        },
        "Combinatie Telemetrie + Transformatoren": {
            "fixed_fee_mo": round(2350.0 / 12.0, 2),  # €195.83/mo
        },
    },
}


def get_dso_preset_options() -> Dict[str, List[str]]:
    """Returns mapping of DSO provider name to available voltage/capacity tiers."""
    return {dso: list(tiers.keys()) for dso, tiers in UTILITY_DSO_PRESETS.items()}


def get_supplier_preset_options() -> Dict[str, List[str]]:
    """Returns mapping of energy supplier name to available contract products."""
    return {supp: list(plans.keys()) for supp, plans in UTILITY_SUPPLIER_PRESETS.items()}


def get_metering_preset_options() -> Dict[str, List[str]]:
    """Returns mapping of certified metering company to metering packages."""
    return {meter: list(plans.keys()) for meter, plans in UTILITY_METERING_PRESETS.items()}


def apply_utility_tariff_presets(
    dso_choice: str,
    tier_choice: str,
    supp_choice: str,
    supp_plan: str,
    meter_choice: str,
    meter_tier: str,
    fin_cfg: CombinedFinancialConfig,
) -> CombinedFinancialConfig:
    """
    Applies real-world DSO, Supplier, and Metering benchmark rates to CombinedFinancialConfig.
    Returns the updated configuration.
    """
    # DSO
    dso_tiers = UTILITY_DSO_PRESETS.get(dso_choice, {})
    dso_data = dso_tiers.get(tier_choice)
    if not dso_data and dso_tiers:
        dso_data = next(iter(dso_tiers.values()))
    if dso_data:
        fin_cfg.dso_capacity_fee_eur_kw_month = float(dso_data.get("capacity_fee_kw_mo", fin_cfg.dso_capacity_fee_eur_kw_month))
        fin_cfg.dso_peak_demand_fee_eur_kw_month = float(dso_data.get("peak_fee_kw_mo", fin_cfg.dso_peak_demand_fee_eur_kw_month))
        fin_cfg.dso_fixed_fee_eur_month = float(dso_data.get("fixed_fee_mo", fin_cfg.dso_fixed_fee_eur_month))
        fin_cfg.dso_transport_eur_kwh = float(dso_data.get("transport_eur_kwh", fin_cfg.dso_transport_eur_kwh))
        fin_cfg.grid_overload_penalty_eur_kw = float(dso_data.get("penalty_kw", fin_cfg.grid_overload_penalty_eur_kw))

    # Supplier
    supp_plans = UTILITY_SUPPLIER_PRESETS.get(supp_choice, {})
    supp_data = supp_plans.get(supp_plan)
    if not supp_data and supp_plans:
        supp_data = next(iter(supp_plans.values()))
    if supp_data:
        fin_cfg.supplier_energy_price_eur_kwh = float(supp_data.get("energy_price_eur_kwh", fin_cfg.supplier_energy_price_eur_kwh))
        fin_cfg.supplier_fixed_fee_eur_month = float(supp_data.get("fixed_fee_mo", fin_cfg.supplier_fixed_fee_eur_month))

    # Metering
    meter_tiers = UTILITY_METERING_PRESETS.get(meter_choice, {})
    meter_data = meter_tiers.get(meter_tier)
    if not meter_data and meter_tiers:
        meter_data = next(iter(meter_tiers.values()))
    if meter_data:
        fin_cfg.metering_fixed_fee_eur_month = float(meter_data.get("fixed_fee_mo", fin_cfg.metering_fixed_fee_eur_month))

    return fin_cfg
