"""
========================================================================================
Solar PV Data Models (current_model/models/solar.py)
========================================================================================

Description:
------------
Defines dataclasses for solar site locations, PV array specifications,
mounting geometry, inverter parameters, system loss factors, and simulation results.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
import datetime


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
    # DC System Sizing
    dc_capacity_kwp: float = 100.0                # Installed DC capacity (kWp)
    module_technology: str = "Mono-Si PERC/TOPCon"  # Technology type
    temp_coefficient_pct_c: float = -0.35         # Power temperature coefficient (%/°C)
    nmot_c: float = 45.0                          # Nominal Module Operating Temperature (°C)

    # Geometry & Mounting
    tilt_deg: float = 30.0                        # Panel tilt angle (0° = flat, 90° = vertical)
    azimuth_deg: float = 0.0                      # Azimuth (In Open-Meteo & South Hemisphere: 0° = North, 180° = South, 90° = East, -90° = West)
    mounting_type: str = "Open-Rack (Ground/Carport)"  # "Open-Rack", "Roof Flush", "1-Axis Tracker"

    # Inverter & AC Conversion
    inverter_capacity_kw: float = 90.0            # Max AC Inverter output power (kW)
    inverter_efficiency_pct: float = 98.0         # Nominal Inverter Efficiency (%)

    # System Derate & Balance of System (BOS) Losses
    soiling_loss_pct: float = 2.0                 # Soiling & dust losses (%)
    shading_loss_pct: float = 1.5                 # Near shading losses (%)
    dc_wiring_loss_pct: float = 1.5               # DC cable & mismatch losses (%)
    degradation_pct_a: float = 0.5                # Annual module degradation (%/year)

    @property
    def total_dc_loss_pct(self) -> float:
        """Combined DC derate percentage before inverter conversion."""
        # Multiplicative loss composition: 1 - (1-l1)(1-l2)...
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
    """Comprehensive key performance indicators for the Solar PV installation."""
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


@dataclass
class SolarSimulationResult:
    """Container for complete solar PV simulation results."""
    config: SolarPVConfig
    location: SolarLocation
    df_timeseries: Any                             # pd.DataFrame with timestamp, GHI, DNI, DHI, T_amb, T_cell, P_dc, P_ac
    monthly_yields: List[SolarMonthlyYield] = field(default_factory=list)
    kpis: SolarKPIs = field(default_factory=SolarKPIs)
    loss_breakdown: Dict[str, float] = field(default_factory=dict)
