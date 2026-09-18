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
        "description": "Standard P-Type monocrystalline technology. Proven, robust industry standard with favorable price-performance ratio."
    },
    "TOPCon": {
        "name": "TOPCon (Tunnel Oxide Passivated Contact)",
        "short_name": "TOPCon",
        "power_wp": 450.0,
        "temp_coeff_pct_c": -0.29,
        "first_year_deg_pct": 1.50,
        "annual_deg_pct": 0.40,
        "description": "Modern N-Type technology of current generation. Higher cell efficiency (+9.8% Wp), lower thermal losses, and extended operational lifetime."
    },
    "Backcontact": {
        "name": "Backcontact / IBC (Interdigitated Back Contact)",
        "short_name": "Backcontact",
        "power_wp": 470.0,
        "temp_coeff_pct_c": -0.26,
        "first_year_deg_pct": 1.00,
        "annual_deg_pct": 0.35,
        "description": "Premium IBC back-contact cell architecture. Eliminates front-side busbar shading, offering lowest temperature coefficient and minimal degradation."
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

    def to_dict(self) -> Dict[str, Any]:
        """Serializes SolarLocation to dictionary."""
        return {
            "name": self.name,
            "latitude": float(self.latitude),
            "longitude": float(self.longitude),
            "elevation_m": float(self.elevation_m),
            "timezone_str": str(self.timezone_str)
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SolarLocation":
        """Deserializes dictionary to SolarLocation."""
        if not data:
            return cls()
        return cls(
            name=data.get("name", "Custom Location"),
            latitude=float(data.get("latitude", -33.5133)),
            longitude=float(data.get("longitude", -69.2561)),
            elevation_m=float(data.get("elevation_m", 1100.0)),
            timezone_str=data.get("timezone_str", "America/Argentina/Mendoza")
        )


@dataclass
class SolarPVConfig:
    """Represents the technical parameters of the Solar PV system."""
    # Module & DC Sizing
    module_count: int = 600                       # Number of solar panels (quantity)
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

    # Weather Data Foundation
    weather_mode: str = "TMY"                     # "TMY", "single_year", or "multi_year"
    selected_weather_year: int = 2024             # Used when weather_mode == "single_year"
    multi_year_start: int = 2015                  # Start year for multi-year risk evaluation
    multi_year_end: int = 2024                    # End year for multi-year risk evaluation

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

    def to_dict(self) -> Dict[str, Any]:
        """Serializes SolarPVConfig to dictionary."""
        return {
            "module_count": int(self.module_count),
            "module_power_wp": float(self.module_power_wp),
            "technology_preset": str(self.technology_preset),
            "module_technology": str(self.module_technology),
            "temp_coefficient_pct_c": float(self.temp_coefficient_pct_c),
            "nmot_c": float(self.nmot_c),
            "dc_capacity_kwp": float(self.dc_capacity_kwp) if self.dc_capacity_kwp is not None else None,
            "first_year_degradation_pct": float(self.first_year_degradation_pct),
            "annual_degradation_pct": float(self.annual_degradation_pct),
            "degradation_pct_a": float(self.degradation_pct_a),
            "economic_lifetime_years": int(self.economic_lifetime_years),
            "module_length_m": float(self.module_length_m),
            "module_width_m": float(self.module_width_m),
            "area_factor": float(self.area_factor),
            "tilt_deg": float(self.tilt_deg),
            "azimuth_deg": float(self.azimuth_deg),
            "mounting_type": str(self.mounting_type),
            "albedo": float(self.albedo),
            "inverter_capacity_kw": float(self.inverter_capacity_kw),
            "inverter_efficiency_pct": float(self.inverter_efficiency_pct),
            "soiling_loss_pct": float(self.soiling_loss_pct),
            "shading_loss_pct": float(self.shading_loss_pct),
            "dc_wiring_loss_pct": float(self.dc_wiring_loss_pct),
            "weather_mode": str(self.weather_mode),
            "selected_weather_year": int(self.selected_weather_year),
            "multi_year_start": int(self.multi_year_start),
            "multi_year_end": int(self.multi_year_end),
            "sizing_scenario": str(self.sizing_scenario)
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SolarPVConfig":
        """Deserializes dictionary to SolarPVConfig."""
        if not data:
            return cls()
        return cls(
            module_count=int(data.get("module_count", 600)),
            module_power_wp=float(data.get("module_power_wp", 450.0)),
            technology_preset=data.get("technology_preset", "TOPCon"),
            module_technology=data.get("module_technology", "N-Type TOPCon"),
            temp_coefficient_pct_c=float(data.get("temp_coefficient_pct_c", -0.29)),
            nmot_c=float(data.get("nmot_c", 45.0)),
            dc_capacity_kwp=float(data.get("dc_capacity_kwp")) if data.get("dc_capacity_kwp") is not None else None,
            first_year_degradation_pct=float(data.get("first_year_degradation_pct", 1.50)),
            annual_degradation_pct=float(data.get("annual_degradation_pct", 0.40)),
            degradation_pct_a=float(data.get("degradation_pct_a", 0.40)),
            economic_lifetime_years=int(data.get("economic_lifetime_years", 15)),
            module_length_m=float(data.get("module_length_m", 1.76)),
            module_width_m=float(data.get("module_width_m", 1.13)),
            area_factor=float(data.get("area_factor", 1.40)),
            tilt_deg=float(data.get("tilt_deg", 30.0)),
            azimuth_deg=float(data.get("azimuth_deg", 0.0)),
            mounting_type=data.get("mounting_type", "Open-Rack (Ground/Carport)"),
            albedo=float(data.get("albedo", 0.20)),
            inverter_capacity_kw=float(data.get("inverter_capacity_kw", 230.0)),
            inverter_efficiency_pct=float(data.get("inverter_efficiency_pct", 98.0)),
            soiling_loss_pct=float(data.get("soiling_loss_pct", 2.0)),
            shading_loss_pct=float(data.get("shading_loss_pct", 1.5)),
            dc_wiring_loss_pct=float(data.get("dc_wiring_loss_pct", 1.5)),
            weather_mode=data.get("weather_mode", "TMY"),
            selected_weather_year=int(data.get("selected_weather_year", 2024)),
            multi_year_start=int(data.get("multi_year_start", 2015)),
            multi_year_end=int(data.get("multi_year_end", 2024)),
            sizing_scenario=data.get("sizing_scenario", "custom")
        )



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
    weather_data_source: str = ""                  # Description of active weather database

    # Multi-Year P50 / P90 Risk Metrics
    p50_annual_kwh: Optional[float] = None         # Median expected yield (50% exceedance)
    p90_annual_kwh: Optional[float] = None         # Conservative debt sizing yield (90% exceedance)
    p95_annual_kwh: Optional[float] = None         # Extreme conservative limit (95% exceedance)
    multi_year_risk_summary: Optional[Dict[str, Any]] = None

    # Electrical Dispatch & Load Coupling KPIs (Tab 1 integration)
    total_load_kwh: float = 0.0                    # Total facility consumption over simulated horizon (kWh)
    direct_consumption_kwh: float = 0.0            # Solar PV energy directly consumed on-site (kWh)
    surplus_generation_kwh: float = 0.0            # Excess PV energy exported / available for BESS (kWh)
    residual_load_kwh: float = 0.0                 # Remaining facility load from grid / generator (kWh)
    self_consumption_rate_pct: float = 0.0         # Self-consumption rate: Direct / Solar Total (%)
    solar_fraction_autarky_pct: float = 0.0        # Autarky / Solar Fraction: Direct / Load Total (%)


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
class SolarFinancialConfig:
    """Represents financial, investment, and operational cost parameters for the Solar PV installation."""
    is_enabled: bool = True                       # True by default to provide immediate financial assessment
    currency: str = "EUR"                         # Currency code / symbol (e.g. EUR, USD, ARS)

    # CAPEX Parameter Breakdown (Turn-Key Cost Breakdown)
    cost_modules_per_wp: Optional[float] = 1.00   # €/Wp (e.g. 1.00 €/Wp)
    cost_inverter_per_w: Optional[float] = 0.07   # €/W AC (e.g. 0.07 €/W)
    cost_substructure_per_wp: Optional[float] = 0.15 # €/Wp (Racking / Mounting structure, e.g. 0.15 €/Wp)
    cost_installation_per_wp: Optional[float] = 0.35 # €/Wp (Electrical installation & labor, e.g. 0.35 €/Wp)
    fixed_switchgear_cost: float = 0.0            # Switchgear cabinet (€)
    fixed_travel_fee: float = 0.0                 # One-off mobilization & travel fee (€)
    custom_additional_capex: float = 0.0          # Additional custom initial investment (€)

    # Operational Parameters (OPEX & Lifecycle Assumptions)
    annual_opex_pct: float = 1.0                  # Annual O&M, insurance & monitoring (% of CAPEX per year)
    annual_opex_fixed: float = 0.0                # Optional fixed OPEX per year (€/a)
    discount_rate_pct: float = 5.0                # Weighted average cost of capital / Discount rate (%)
    electricity_price_inflation_pct: float = 3.0  # Annual electricity price escalation (%)
    feed_in_tariff_per_kwh: float = 0.06          # Export compensation rate for surplus solar power (€/kWh)
    analysis_horizon_years: int = 15              # Life-cycle economic assessment horizon (15–25 years)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes SolarFinancialConfig to dictionary."""
        return {
            "is_enabled": bool(self.is_enabled),
            "currency": str(self.currency),
            "cost_modules_per_wp": float(self.cost_modules_per_wp) if self.cost_modules_per_wp is not None else None,
            "cost_inverter_per_w": float(self.cost_inverter_per_w) if self.cost_inverter_per_w is not None else None,
            "cost_substructure_per_wp": float(self.cost_substructure_per_wp) if self.cost_substructure_per_wp is not None else None,
            "cost_installation_per_wp": float(self.cost_installation_per_wp) if self.cost_installation_per_wp is not None else None,
            "fixed_switchgear_cost": float(self.fixed_switchgear_cost),
            "fixed_travel_fee": float(self.fixed_travel_fee),
            "custom_additional_capex": float(self.custom_additional_capex),
            "annual_opex_pct": float(self.annual_opex_pct),
            "annual_opex_fixed": float(self.annual_opex_fixed),
            "discount_rate_pct": float(self.discount_rate_pct),
            "electricity_price_inflation_pct": float(self.electricity_price_inflation_pct),
            "feed_in_tariff_per_kwh": float(self.feed_in_tariff_per_kwh),
            "analysis_horizon_years": int(self.analysis_horizon_years)
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SolarFinancialConfig":
        """Deserializes dictionary to SolarFinancialConfig."""
        if not data:
            return cls()
        return cls(
            is_enabled=bool(data.get("is_enabled", False)),
            currency=str(data.get("currency", "EUR")),
            cost_modules_per_wp=float(data.get("cost_modules_per_wp")) if data.get("cost_modules_per_wp") is not None else None,
            cost_inverter_per_w=float(data.get("cost_inverter_per_w")) if data.get("cost_inverter_per_w") is not None else None,
            cost_substructure_per_wp=float(data.get("cost_substructure_per_wp")) if data.get("cost_substructure_per_wp") is not None else None,
            cost_installation_per_wp=float(data.get("cost_installation_per_wp")) if data.get("cost_installation_per_wp") is not None else None,
            fixed_switchgear_cost=float(data.get("fixed_switchgear_cost", 0.0)),
            fixed_travel_fee=float(data.get("fixed_travel_fee", 0.0)),
            custom_additional_capex=float(data.get("custom_additional_capex", 0.0)),
            annual_opex_pct=float(data.get("annual_opex_pct", 1.0)),
            annual_opex_fixed=float(data.get("annual_opex_fixed", 0.0)),
            discount_rate_pct=float(data.get("discount_rate_pct", 5.0)),
            electricity_price_inflation_pct=float(data.get("electricity_price_inflation_pct", 3.0)),
            feed_in_tariff_per_kwh=float(data.get("feed_in_tariff_per_kwh", 0.06)),
            analysis_horizon_years=int(data.get("analysis_horizon_years", 15))
        )


@dataclass
class SolarFinancialMetrics:
    """Comprehensive standalone and lifecycle financial performance metrics for Solar PV."""
    is_configured: bool = False
    currency: str = "EUR"

    # CAPEX Breakdown
    capex_modules: float = 0.0
    capex_inverter: float = 0.0
    capex_substructure: float = 0.0
    capex_installation: float = 0.0
    capex_fixed_fees: float = 0.0
    total_capex: float = 0.0
    capex_per_kwp: float = 0.0                    # Specific investment (€/kWp)

    # Operational Economics
    annual_opex_year1: float = 0.0                # Year 1 maintenance cost
    lifetime_total_generation_kwh: float = 0.0    # 15-year cumulative AC energy
    lcoe_per_kwh: float = 0.0                     # Levelized Cost of Electricity (€/kWh)

    # Cashflow & Trajectory (15 Years)
    cash_flow_table: List[Dict[str, Any]] = field(default_factory=list)
    cumulative_cash_flow: List[float] = field(default_factory=list)
    cumulative_status_quo: List[float] = field(default_factory=list)
    cumulative_with_pv: List[float] = field(default_factory=list)

    # Return on Investment Indicators (when coupled with load/avoided costs or flat rate)
    payback_period_years: Optional[float] = None
    discounted_payback_years: Optional[float] = None
    npv: Optional[float] = None
    irr_pct: Optional[float] = None
    total_lifetime_savings: float = 0.0


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
    multi_year_risk_summary: Optional[Dict[str, Any]] = None
    financial_config: Optional[SolarFinancialConfig] = None
    financial_metrics: Optional[SolarFinancialMetrics] = None


