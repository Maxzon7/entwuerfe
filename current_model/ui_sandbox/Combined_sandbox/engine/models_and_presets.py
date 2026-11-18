"""
Domain data models, configuration dataclasses, KPI containers, and hardware/rule presets
for the Combined System Sandbox Engine.
"""

from dataclasses import dataclass, field, replace
from typing import Dict, List, Any, Optional, Tuple
import numpy as np
import pandas as pd

try:
    from numba import njit as _numba_njit

    def _opt_njit(func):
        return _numba_njit(cache=True, fastmath=True)(func)
except ImportError:
    def _opt_njit(func):
        return func


ENGINE_VERSION = "13.7"

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


def resolve_generator_fuel_curve(system_cfg: Any) -> Tuple[float, float]:
    """Returns `(slope_per_kwh, intercept_per_kw_rated)` resolving `FUEL_SPECS` when dataclass defaults are untouched."""
    fuel_type = str(getattr(system_cfg, "fuel_type", "Diesel") or "Diesel")
    raw_slope = float(getattr(system_cfg, "gen_slope_per_kwh", 0.24))
    raw_int = float(getattr(system_cfg, "gen_intercept_per_kw_rated", 0.04))
    if fuel_type != "Diesel" and abs(raw_slope - 0.24) < 1e-6 and abs(raw_int - 0.04) < 1e-6:
        spec = FUEL_SPECS.get(fuel_type, FUEL_SPECS["Diesel"])
        return float(spec["slope_per_kwh"]), float(spec["intercept_per_kw_rated"])
    return raw_slope, raw_int

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
    disable_solar_inverter_limit: bool = False     # True = no AC clipping limit (100% unclipped output)
    inverter_efficiency_pct: float = 98.0
    solar_weather_mode: str = "single_year"        # "single_year" (concrete year e.g. 2025) | "TMY"
    solar_weather_year: int = 2025                 # Reference year when solar_weather_mode == "single_year"

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
    rule2_battery_strategy: str = "peak_shaving_only"         # "peak_shaving_only" | "self_consumption_reserve"
    peak_reserve_soc_pct: float = 30.0                        # Reserved SoC (%) for peaks when rule2 == "self_consumption_reserve"
    rule3_charging_sources: str = "solar_and_grid"            # "solar_only" | "solar_and_grid" | "solar_and_generator" | "all_sources"


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
    # Market Structure, Currency & Pillar Toggles (Aligned with Currentsituation_sandbox)
    currency_code: str = "EUR"                       # "EUR", "ARS", "USD"
    market_mode: str = "unbundled_4_pillar"          # "unbundled_4_pillar" | "single_utility" | "custom"
    enable_pillar_1_supplier: bool = True
    enable_pillar_2_dso: bool = True
    enable_pillar_3_metering: bool = True
    enable_pillar_4_taxes: bool = True

    # Pillar 1: Energy Supply (Supplier)
    supplier_energy_price_eur_kwh: float = 0.15
    supplier_fixed_fee_eur_month: float = 50.0
    supplier_pricing_mode: str = "single"            # "single" (Flat Rate) or "dual_tou" (Peak HT / Off-Peak NT)
    supplier_peak_ht_eur_kwh: float = 0.134          # Peak / High Tariff (Mon-Fri 07:00-23:00)
    supplier_offpeak_nt_eur_kwh: float = 0.118       # Off-Peak / Low Tariff (Nights & Weekends)
    supplier_gvo_surcharge_eur_kwh: float = 0.0      # Green Certificate & Procurement Surcharge (€/kWh)

    # Pillar 2: Grid Network (DSO / Single-Utility Bundled Network)
    dso_capacity_fee_eur_kw_month: float = 2.50
    dso_peak_demand_fee_eur_kw_month: float = 6.00
    dso_connection_fee_eur_month: float = 0.0        # Fixed Connection Fee (/month)
    dso_fixed_fee_eur_month: float = 100.0           # Fixed Transport Fee (/month)
    dso_transport_eur_kwh: float = 0.025
    dso_enable_three_window_tou: bool = False        # True = 3-Window TOU (Pico / Valle / Resto)
    dso_transport_peak_eur_kwh: Optional[float] = None
    dso_transport_offpeak_eur_kwh: Optional[float] = None
    dso_transport_shoulder_eur_kwh: float = 0.0
    grid_overload_penalty_eur_kw: float = 15.00
    dso_enable_excess_capacity_penalty: bool = True
    dso_adjust_capacity_on_breach: bool = False      # Bill contracted capacity on max(limit, monthly peak) in breach months
    dso_bill_peak_on_pico_only: bool = False         # EDEMSA T2 Rule: Bill Pos 2.3 Peak Demand on Peak/Pico 18-23h window only
    dso_regulatory_adjustments_eur_month: float = 0.0  # Monthly regulatory/seasonal pass-through adjustments
    strict_grid_congestion_mode: bool = False        # Strict Grid Congestion Lock (No Grid Upgrade or Contract Breach Allowed)

    # Avoided Grid Upgrade CAPEX & Avoided Transformer Rent OPEX
    avoided_grid_upgrade_capex_eur: float = 0.0
    avoided_transformer_rent_eur_month: float = 0.0

    # Pillar 3: Metering
    metering_fixed_fee_eur_month: float = 45.0

    # Pillar 4: Taxes & Levies
    energy_tax_eur_kwh: float = 0.05
    tax_surcharge_pct: float = 0.0
    annual_tax_reduction_credit_eur: float = 0.0     # Annual Energy Tax Credit (/year)
    vat_rate_pct: float = 21.0                       # Value Added Tax (VAT %)
    vat_applies_to_levies: bool = True               # True = VAT on P1..P4 (NL); False = VAT on Electric Concepts P1..P3 only (AR)

    # Legacy / Aggregate Tariff Aliases (if set explicitly by tests, used as overrides)
    grid_energy_price_eur_kwh: Optional[float] = None
    grid_capacity_fee_eur_kw_month: Optional[float] = None
    grid_fixed_fee_eur_month: Optional[float] = None

    # Block B: Solar Turnkey Costs & Overrides
    solar_modules_eur_wp: float = 0.45
    solar_inverter_eur_w: float = 0.12
    solar_mounting_eur_wp: float = 0.28
    solar_turnkey_eur_kwp: float = 850.0
    solar_use_detailed_breakdown: bool = False
    solar_capex_eur_kwp: Optional[float] = None
    solar_lump_sum_capex_eur: float = 0.0
    solar_om_pct_of_capex: float = 1.5
    solar_lump_sum_om_eur_year: float = 0.0

    # Block C: Battery Turnkey Costs, O&M, Overrides & Mid-Life Augmentation
    battery_capex_eur_kwh: float = 280.0
    battery_capex_eur_kw: float = 150.0
    battery_fixed_bop_eur: float = 15000.0
    battery_lump_sum_capex_eur: float = 0.0
    battery_om_pct_of_capex: float = 1.5
    battery_lump_sum_om_eur_year: float = 0.0
    enable_battery_augmentation: bool = True
    battery_augmentation_year: int = 11
    battery_augmentation_pct_of_racks: float = 60.0
    battery_augmentation_lump_sum_eur: float = 0.0

    # Block D: Generator Purchase vs. Rental, Fuel OPEX & Overrides
    generator_cost_model: str = "Purchase (CAPEX)"  # "Purchase (CAPEX)" or "Monthly Rental (OPEX)"
    generator_capex_eur: float = 22000.0
    generator_lump_sum_capex_eur: float = 0.0
    generator_rental_eur_month: float = 1200.0
    generator_rental_active_months_only: bool = False
    fuel_price_eur_per_unit: float = 1.45
    generator_maintenance_eur_per_hour: float = 4.50
    generator_lump_sum_service_opex_eur_year: float = 0.0

    # Lifecycle Discount Rate
    discount_rate_pct: float = 6.0

    # Long-Term Escalation, Degradation & Feed-in Assumptions (v13.7)
    tariff_escalation_pct_pa: float = 2.5
    om_inflation_pct_pa: float = 2.0
    solar_export_feed_in_eur_kwh: float = 0.05
    system_degradation_pct_pa: float = 0.4

    @property
    def effective_solar_capex_eur_kwp(self) -> float:
        if self.solar_capex_eur_kwp is not None:
            return float(self.solar_capex_eur_kwp)
        if self.solar_use_detailed_breakdown:
            return float((self.solar_modules_eur_wp + self.solar_inverter_eur_w + self.solar_mounting_eur_wp) * 1000.0)
        return float(self.solar_turnkey_eur_kwp)


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

    # Extended Year-1 & 15-Year Metrics (v13.7)
    solar_export_revenue_eur: float = 0.0
    gross_bill_savings_y1_eur: float = 0.0
    system_om_and_fuel_y1_eur: float = 0.0
    discounted_payback_years: Optional[float] = None
    irr_15y_pct: Optional[float] = None
    tco_15y_baseline_eur: float = 0.0
    tco_15y_combined_eur: float = 0.0
    tco_15y_savings_eur: float = 0.0
    effective_blended_grid_rate_eur_kwh: float = 0.0
    system_lcoe_eur_kwh: float = 0.0
    annualized_cost_per_shaved_kw_eur: float = 0.0

    # Granular Sub-Ledger Itemization (for 3-Zone Financial Workbench)
    baseline_supply_energy_eur: float = 0.0
    combined_supply_energy_eur: float = 0.0
    baseline_supply_fixed_eur: float = 0.0
    combined_supply_fixed_eur: float = 0.0
    baseline_dso_fixed_eur: float = 0.0
    combined_dso_fixed_eur: float = 0.0
    baseline_dso_capacity_eur: float = 0.0
    combined_dso_capacity_eur: float = 0.0
    baseline_dso_peak_eur: float = 0.0
    combined_dso_peak_eur: float = 0.0
    baseline_dso_transport_eur: float = 0.0
    combined_dso_transport_eur: float = 0.0
    baseline_dso_transformer_rent_eur: float = 0.0
    combined_dso_transformer_rent_eur: float = 0.0
    baseline_energy_tax_eur: float = 0.0
    combined_energy_tax_eur: float = 0.0
    baseline_tax_surcharge_eur: float = 0.0
    combined_tax_surcharge_eur: float = 0.0

    # Hardware CAPEX Sub-Itemization & Component Impact Attribution
    solar_modules_capex_eur: float = 0.0
    solar_inverter_capex_eur: float = 0.0
    solar_mounting_capex_eur: float = 0.0
    battery_rack_capex_eur: float = 0.0
    battery_inverter_capex_eur: float = 0.0
    battery_bop_capex_eur: float = 0.0
    variable_grid_rate_eur_kwh: float = 0.0
    grid_volume_savings_y1_eur: float = 0.0
    grid_peak_and_penalty_savings_y1_eur: float = 0.0
    solar_direct_value_y1_eur: float = 0.0
    solar_stored_value_y1_eur: float = 0.0

    # Classic Bill Breakdown Extensions (TOU HT/NT, GvO, DSO Split, Tax Credit & VAT)
    baseline_supply_peak_ht_eur: float = 0.0
    combined_supply_peak_ht_eur: float = 0.0
    baseline_supply_offpeak_nt_eur: float = 0.0
    combined_supply_offpeak_nt_eur: float = 0.0
    baseline_supply_gvo_eur: float = 0.0
    combined_supply_gvo_eur: float = 0.0
    baseline_dso_connection_eur: float = 0.0
    combined_dso_connection_eur: float = 0.0
    baseline_dso_transport_fixed_eur: float = 0.0
    combined_dso_transport_fixed_eur: float = 0.0
    baseline_dso_breach_months: int = 0
    combined_dso_breach_months: int = 0
    baseline_energy_tax_gross_eur: float = 0.0
    combined_energy_tax_gross_eur: float = 0.0
    baseline_tax_credit_eur: float = 0.0
    combined_tax_credit_eur: float = 0.0
    baseline_vat_eur: float = 0.0
    combined_grid_vat_eur: float = 0.0
    baseline_total_gross_eur: float = 0.0
    combined_grid_gross_eur: float = 0.0

    # Grid Congestion Mode & Isolated Actor Indicators
    grid_congestion_compliant: bool = True
    grid_congestion_breach_kw: float = 0.0
    grid_congestion_breach_months: int = 0
    dso_savings_eur: float = 0.0
    dso_savings_pct: float = 0.0
    supplier_savings_eur: float = 0.0
    supplier_savings_pct: float = 0.0
    tax_and_metering_savings_eur: float = 0.0
    benefit_cost_ratio_15y: float = 0.0

    # Isolated Component Economics
    solar_gross_value_y1_eur: float = 0.0
    solar_net_value_y1_eur: float = 0.0
    solar_isolated_payback_years: Optional[float] = None
    solar_isolated_lcoe_eur_kwh: float = 0.0
    battery_peak_savings_y1_eur: float = 0.0
    battery_grid_charge_cost_y1_eur: float = 0.0
    battery_gross_value_y1_eur: float = 0.0
    battery_net_value_y1_eur: float = 0.0
    battery_isolated_payback_years: Optional[float] = None
    battery_cost_per_discharged_kwh: float = 0.0
    generator_peak_savings_y1_eur: float = 0.0
    generator_net_value_y1_eur: float = 0.0
    generator_isolated_payback_years: Optional[float] = None
    generator_cost_per_kwh: float = 0.0

    # Active Currency & Detailed DSO Window / Regulatory Sub-Ledger Attribution
    currency_code: str = "EUR"
    baseline_dso_vol_peak_eur: float = 0.0
    combined_dso_vol_peak_eur: float = 0.0
    baseline_dso_vol_offpeak_eur: float = 0.0
    combined_dso_vol_offpeak_eur: float = 0.0
    baseline_dso_vol_shoulder_eur: float = 0.0
    combined_dso_vol_shoulder_eur: float = 0.0
    baseline_dso_peak_tou_kwh: float = 0.0
    combined_dso_peak_tou_kwh: float = 0.0
    baseline_dso_offpeak_tou_kwh: float = 0.0
    combined_dso_offpeak_tou_kwh: float = 0.0
    baseline_dso_shoulder_tou_kwh: float = 0.0
    combined_dso_shoulder_tou_kwh: float = 0.0
    baseline_dso_regulatory_adj_eur: float = 0.0
    combined_dso_regulatory_adj_eur: float = 0.0
    baseline_dso_billed_peak_avg_kw: float = 0.0
    combined_dso_billed_peak_avg_kw: float = 0.0
    baseline_dso_billed_cap_avg_kw: float = 0.0
    combined_dso_billed_cap_avg_kw: float = 0.0

    # Hardware Pricing Mode & Implied Unit Benchmark Transparency
    solar_pricing_mode: str = "Turnkey Unit Rate"
    solar_opex_pricing_mode: str = "% of CAPEX"
    solar_implied_eur_kwp: float = 0.0
    battery_pricing_mode: str = "Unit Rates"
    battery_opex_pricing_mode: str = "% of CAPEX"
    battery_repowering_mode: str = "% of Racks"
    battery_implied_eur_kwh: float = 0.0
    battery_implied_eur_kw: float = 0.0
    generator_pricing_mode: str = "Purchase (CAPEX)"
    generator_opex_pricing_mode: str = "Runtime & Fuel"
    generator_implied_eur_kw: float = 0.0


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
    is_gap: np.ndarray = field(default_factory=lambda: np.zeros(35040, dtype=bool))
    solar_potential_kw: Optional[np.ndarray] = None

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
    dso_monthly_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    supplier_monthly_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    tax_monthly_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    solar_fin_monthly_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    battery_fin_monthly_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    generator_fin_monthly_df: pd.DataFrame = field(default_factory=pd.DataFrame)
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


MIX_STRATEGY_OPTIONS: Dict[str, str] = {
    "hybrid_2h": "Hybrid Peak Split: 2h Compact Battery + Generator Backup",
    "hybrid_4h": "Hybrid Peak Split: 4h Peak Battery + Generator Backup",
    "solar_buffer_gen_peak": "Solar Surplus Buffer Battery + Generator Winter Peaks",
    "pure_battery_100": "100% Battery Zero-Overload (No Generator)",
    "pure_generator_100": "100% Generator Zero-Overload (No Battery)",
    "custom": "Custom Manual Mix (Fine-Tune All 4 Sources)",
}


@dataclass
class CoordinatedMixRecommendation:
    """Coordinated 4-source physical sizing plan across Grid, Solar, Battery, and Generator."""
    strategy_key: str
    strategy_label: str
    grid_limit_kw: float
    solar_enabled: bool
    solar_share_pct: float
    solar_kwp: float
    battery_enabled: bool
    battery_capacity_kwh: float
    battery_power_kw: float
    generator_enabled: bool
    generator_rated_kw: float
    est_battery_min_soc_pct: float
    est_battery_cycles: float
    est_generator_runtime_hrs: float
    est_generator_energy_mwh: float
    est_unmet_overload_hrs: float
    rationale_text: str


@dataclass
class SystemUtilizationDiagnostics:
    """Reusable physical supply-mix and component utilization summary (Technical & Financials)."""
    # Supply Mix Breakdown (summing to Annual Consumption)
    annual_consumption_kwh: float
    grid_direct_kwh: float
    grid_direct_pct: float
    solar_direct_kwh: float
    solar_direct_pct: float
    battery_discharge_kwh: float
    battery_discharge_pct: float
    solar_via_battery_kwh: float
    grid_or_gen_via_battery_kwh: float
    generator_direct_kwh: float
    generator_direct_pct: float
    unmet_overload_kwh: float
    grid_peak_shaved_kw: float
    solar_peak_contribution_kw: float
    bess_peak_discharged_kw: float
    gen_peak_used_kw: float

    # Battery Storage Utilization (kWh)
    bess_enabled: bool
    bess_installed_kwh: float
    bess_usable_window_kwh: float
    bess_min_soc_reached_pct: float
    bess_max_soc_reached_pct: float
    bess_max_depth_used_kwh: float
    bess_unused_usable_kwh: float
    bess_capacity_utilization_pct: float
    bess_right_sized_kwh: float
    bess_cycles_per_yr: float

    # Battery Inverter Utilization (kW)
    bess_installed_kw: float
    bess_peak_charged_kw: float
    bess_power_utilization_pct: float

    # Solar Yield Utilization
    solar_enabled: bool
    solar_installed_kwp: float
    solar_total_potential_kwh: float
    solar_used_direct_kwh: float
    solar_used_via_battery_kwh: float
    solar_exported_unused_kwh: float
    solar_utilization_pct: float

    # Generator Utilization
    gen_enabled: bool
    gen_rated_kw: float
    gen_power_utilization_pct: float
    gen_runtime_hours: float
    gen_starts_count: int
    gen_energy_kwh: float

    # Grid Connection Utilization
    grid_limit_kw: float
    grid_peak_import_kw: float
    grid_utilization_pct: float


@dataclass
class CombinedScenarioSnapshot:
    """
    Lightweight (< 50 KB) scenario snapshot storing configs, KPIs, and summary tables
    without duplicating 35,040-step NumPy dispatch arrays in RAM.
    """
    slot_id: str
    name: str
    created_at: str
    load_fingerprint: Tuple[int, float, float]
    baseline_tariff_fingerprint: Tuple
    physical_fingerprint: Tuple
    system_config: CombinedSystemConfig
    rules_config: InteractionRulesConfig
    financial_config: CombinedFinancialConfig
    solar_derivation: SolarDerivationInfo
    kpis: CombinedTechnicalKPIs
    financial_kpis: CombinedFinancialKPIs
    utilization_diagnostics: SystemUtilizationDiagnostics
    monthly_balance_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    monthly_cost_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    cashflow_15y_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    grid_import_kw_f32: Optional[np.ndarray] = None
    bess_soc_pct_f32: Optional[np.ndarray] = None
    unmet_overload_kw_f32: Optional[np.ndarray] = None
    dispatch_f32_dict: Optional[Dict[str, np.ndarray]] = None

