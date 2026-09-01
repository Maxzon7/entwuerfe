"""
========================================================================================
Solar PV Data Models (current_model/models/solar.py)
========================================================================================

Description:
------------
Defines dataclasses for solar site locations, PV array specifications,
mounting geometry, inverter parameters, system loss factors, area requirements,
and multi-technology comparative simulation results.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
import datetime


# Standard Cell Technology Presets matching the DRACBV reference workbooks
TECHNOLOGY_SPECS = {
    "PERC": {
        "name": "PERC (Passivated Emitter and Rear Cell)",
        "short_name": "PERC",
        "power_wp": 410.0,
        "temp_coeff_pct_c": -0.35,
        "first_year_deg_pct": 2.00,
        "annual_deg_pct": 0.55,
        "description": "Standard P-Type monokristalline Technologie. Bewährter, robuster Industriestandard mit gutem Preis-Leistungs-Verhältnis."
    },
    "TOPCon": {
        "name": "TOPCon (Tunnel Oxide Passivated Contact)",
        "short_name": "TOPCon",
        "power_wp": 450.0,
        "temp_coeff_pct_c": -0.29,
        "first_year_deg_pct": 1.50,
        "annual_deg_pct": 0.40,
        "description": "Moderne N-Type Technologie der aktuellen Generation. Höhere Zelleffizienz (+9,8% Wp), geringere thermische Verluste und längere Lebensdauer."
    },
    "Backcontact": {
        "name": "Backcontact / IBC (Interdigitated Back Contact)",
        "short_name": "Backcontact",
        "power_wp": 470.0,
        "temp_coeff_pct_c": -0.26,
        "first_year_deg_pct": 1.00,
        "annual_deg_pct": 0.35,
        "description": "Premium-Zelltechnologie der Spitzenklasse. Kontakte auf der Rückseite verhindern Abschattungen auf der Vorderseite; minimaler Temperaturkoeffizient und minimale Degradation."
    }
}


@dataclass
class SolarLocation:
    """Represents the geographical site location for solar radiation assessment."""
    name: str = "Tunuyán, Mendoza (Bodegas Salentein)"
    latitude: float = -33.5133
    longitude: float = -69.2561
    elevation_m: float = 1100.0
    timezone_str: str = "America/Argentina/Mendoza"


@dataclass
class SolarPVConfig:
    """Represents the technical parameters of the Solar PV system."""
    # Module & DC Sizing
    module_count: int = 600                       # Number of solar panels (Stückzahl)
    module_power_wp: float = 450.0                # Rated power per panel (Wp)
    technology_preset: str = "TOPCon"             # "PERC", "TOPCon", "Backcontact", or "Custom"
    module_technology: str = "N-Type TOPCon"      # Human-readable label
    temp_coefficient_pct_c: float = -0.29         # Power temperature coefficient (%/°C)
    nmot_c: float = 45.0                          # Nominal Module Operating Temperature (°C)
    dc_capacity_kwp: Optional[float] = None       # Installed DC capacity (kWp)

    # 2-Stage Physical Degradation
    first_year_degradation_pct: float = 1.50      # Year 1 Initial LID degradation (%)
    annual_degradation_pct: float = 0.40          # Year 2+ linear degradation (%/year)
    degradation_pct_a: float = 0.40               # Fallback average for legacy references
    economic_lifetime_years: int = 15             # Target simulation horizon (15 years)

    # Physical Dimensions & Area Requirement
    module_length_m: float = 1.76                 # Panel length (m, standard: 1.76m or 1.2m)
    module_width_m: float = 1.13                  # Panel width (m, standard: 1.13m or 0.7m)
    area_factor: float = 1.40                     # Ground/roof spacing factor (1.0 = flush roof, 1.4 - 1.8 = tilted rows)

    # Geometry & Mounting
    tilt_deg: float = 30.0                        # Panel tilt angle (0° = flat, 90° = vertical)
    azimuth_deg: float = 0.0                      # Azimuth (0° = North in South Hemisphere, 180° = South in North Hemisphere)
    mounting_type: str = "Open-Rack (Ground/Carport)"
    albedo: float = 0.20                          # Ground albedo reflection factor (default: 0.20)

    # Inverter & AC Conversion
    inverter_capacity_kw: float = 230.0           # Max AC Inverter output power (kW)
    inverter_efficiency_pct: float = 98.0         # Nominal Inverter Efficiency (%)

    # System Derate & Balance of System (BOS) Losses
    soiling_loss_pct: float = 2.0                 # Soiling & dust losses (%)
    shading_loss_pct: float = 1.5                 # Near shading losses (%)
    dc_wiring_loss_pct: float = 1.5               # DC cable & mismatch losses (%)

    # Sizing Scenario Tag
    sizing_scenario: str = "custom"               # "40%", "60%", "80%", "100%", or "custom"

    def __post_init__(self):
        if self.dc_capacity_kwp is not None:
            # If user provided dc_capacity_kwp and module_count is at default 600, calculate module count
            if self.module_count == 600 and self.dc_capacity_kwp != round((600 * self.module_power_wp) / 1000.0, 2):
                if self.module_power_wp > 0:
                    self.module_count = max(1, int(round((self.dc_capacity_kwp * 1000.0) / self.module_power_wp)))
            else:
                self.dc_capacity_kwp = round((self.module_count * self.module_power_wp) / 1000.0, 2)
        else:
            self.dc_capacity_kwp = round((self.module_count * self.module_power_wp) / 1000.0, 2)


    @property
    def gross_panel_area_m2(self) -> float:
        """Net physical solar module active area in m²."""
        return round(self.module_count * self.module_length_m * self.module_width_m, 2)

    @property
    def required_area_m2(self) -> float:
        """Total required roof/land area including row spacing in m²."""
        return round(self.gross_panel_area_m2 * self.area_factor, 1)

    @property
    def total_dc_loss_pct(self) -> float:
        """Combined DC derate percentage before inverter conversion."""
        rem = (1.0 - self.soiling_loss_pct / 100.0) * \
              (1.0 - self.shading_loss_pct / 100.0) * \
              (1.0 - self.dc_wiring_loss_pct / 100.0)
        return (1.0 - rem) * 100.0



@dataclass
class SolarMonthlyYield:
    """Monthly aggregated solar PV generation metrics."""
    month_name: str
    month_idx: int
    days_count: int
    energy_kwh: float
    energy_mwh: float
    avg_daily_kwh: float
    peak_power_kw: float
    capacity_factor_pct: float
    specific_yield_kwh_kwp: float


@dataclass
class SolarKPIs:
    """Comprehensive key performance indicators for the Solar PV installation & load dispatch."""
    annual_energy_mwh: float = 0.0
    annual_energy_kwh: float = 0.0
    specific_yield_kwh_per_kwp: float = 0.0        # kWh/kWp/year
    performance_ratio_pct: float = 0.0             # PR (%)
    capacity_factor_pct: float = 0.0               # Capacity Factor (%)
    full_load_hours: float = 0.0                   # Equivalent full load hours (h/a)
    max_ac_power_kw: float = 0.0                   # Peak AC generation power (kW)
    max_dc_power_kw: float = 0.0                   # Peak DC generation power (kW)
    clipping_loss_kwh: float = 0.0                 # Inverter clipping loss (kWh)
    thermal_loss_kwh: float = 0.0                  # Cell temperature derate loss (kWh)
    location_name: str = ""
    global_horizontal_irradiance_mwh_m2: float = 0.0

    # Electrical Dispatch & Load Coupling KPIs (Tab 1 integration)
    total_load_kwh: float = 0.0                    # Total facility consumption over simulated horizon (kWh)
    direct_consumption_kwh: float = 0.0            # Solar PV energy directly consumed on-site (kWh)
    surplus_generation_kwh: float = 0.0            # Excess PV energy exported / available for BESS (kWh)
    residual_load_kwh: float = 0.0                 # Remaining facility load from grid / generator (kWh)
    self_consumption_rate_pct: float = 0.0         # Eigenverbrauchsquote: Direct / Solar Total (%)
    solar_fraction_autarky_pct: float = 0.0        # Autarkiegrad / Solar Deckung: Direct / Load Total (%)


@dataclass
class TechnologyComparisonItem:
    """Comparative production metrics for a specific solar cell technology."""
    tech_key: str                                  # "PERC", "TOPCon", "Backcontact"
    tech_name: str
    module_power_wp: float
    dc_capacity_kwp: float
    temp_coeff_pct_c: float
    first_year_deg_pct: float
    annual_deg_pct: float
    year_1_kwh: float = 0.0
    year_5_kwh: float = 0.0
    year_10_kwh: float = 0.0
    year_15_kwh: float = 0.0
    gain_pct_vs_perc: float = 0.0                  # Relative yield gain compared to PERC baseline (%)


@dataclass
class SolarSimulationResult:
    """Container for complete solar PV simulation results."""
    config: SolarPVConfig
    location: SolarLocation
    df_timeseries: Any                             # pd.DataFrame with 15-min (35,040 steps) timestamp, POA, T_amb, T_cell, P_dc, P_ac, E_ac...
    monthly_yields: List[SolarMonthlyYield] = field(default_factory=list)
    kpis: SolarKPIs = field(default_factory=SolarKPIs)
    loss_breakdown: Dict[str, float] = field(default_factory=dict)
    multi_year_yields: List[Dict[str, Any]] = field(default_factory=list)  # 15-year degradation profile
    technology_comparison: List[TechnologyComparisonItem] = field(default_factory=list)


