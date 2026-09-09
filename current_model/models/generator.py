"""
========================================================================================
Generator (Genset) Data Models (current_model/models/generator.py)
========================================================================================

Description:
------------
Defines dataclasses and calculation helpers for Backup and Peaking Generators (Gensets):
  - `GeneratorConfig`: Rated capacity (kW), fuel type (Diesel, Natural Gas, Biofuel),
    non-linear fuel consumption curve, dispatch modes (Islanding / Grid Congestion,
    Peak Shaving Assist, Emergency Baseload), CAPEX acquisition or monthly leasing,
    fuel pricing ($/L or $/m³), and operating hour servicing costs ($/hr).
  - `GeneratorKPIs`: Performance indicators (annual generation kWh, runtime hours, fuel used, OPEX).
  - `get_generator_presets`: Standard commercial & industrial generator models.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List


@dataclass
class GeneratorConfig:
    """
    Technical and economic specifications for an on-site backup or peaking generator.
    """
    # Technical Specifications
    rated_power_kw: float = 100.0                 # Nameplate electrical power capacity (kW)
    fuel_type: str = "Diesel"                     # "Diesel", "Natural Gas", or "Biofuel"
    min_load_ratio_pct: float = 25.0              # Minimum loading ratio to prevent engine fouling (%)
    
    # Fuel Consumption Linearization Curve: Fuel_Rate (L/h or m³/h) = a * Power_kW + b * Rated_kW
    fuel_curve_slope_l_per_kwh: float = 0.24      # Marginal fuel consumption (L/kWh or m³/kWh)
    fuel_curve_intercept_l_per_kw_rated: float = 0.04 # No-load / standby fuel intercept (L/h per rated kW)

    # Operational Dispatch Modes
    # Options: "islanding_grid_congestion", "peak_shaving_assist", "emergency_baseload"
    dispatch_mode: str = "peak_shaving_assist"
    islanding_grid_limit_kw: float = 0.0          # Grid physical cap above which generator assists (kW)
    peak_shaving_trigger_kw: float = 300.0        # Facility demand trigger threshold for genset start (kW)

    # Financial & Operational Economics
    is_financial_enabled: bool = True
    currency: str = "EUR"
    capital_cost: float = 18000.0                 # Initial purchase & commissioning CAPEX (€)
    monthly_lease_fee: float = 0.0                # Optional monthly equipment rental/lease fee (€/month)
    fuel_price_per_unit: float = 1.45             # Fuel cost per unit (€/Liter for diesel or €/m³ for gas)
    maintenance_cost_per_op_hour: float = 4.50    # Maintenance, lubrication & overhaul fee (€/operating hour)
    carbon_tax_per_unit: float = 0.0              # Environmental surcharge / CO2 tax per fuel unit (€/unit)

    @property
    def min_power_kw(self) -> float:
        """Minimum allowable active generation power when running (kW)."""
        return round(self.rated_power_kw * (self.min_load_ratio_pct / 100.0), 2)

    def calc_fuel_rate_per_hour(self, power_kw: float) -> float:
        """
        Calculates fuel consumption rate in units per hour (L/h or m³/h) for a given active power level.
        Enforces no fuel consumption if power is 0.
        """
        if power_kw <= 0:
            return 0.0
        # Linear genset fuel model: F = a * P + b * P_rated
        rate = (self.fuel_curve_slope_l_per_kwh * power_kw) + \
               (self.fuel_curve_intercept_l_per_kw_rated * self.rated_power_kw)
        return round(max(0.0, rate), 3)

    def calc_fuel_consumption(self, power_kw: float, duration_hours: float = 0.25) -> float:
        """Calculates total fuel consumed in units (L or m³) over a time interval."""
        rate_per_hour = self.calc_fuel_rate_per_hour(power_kw)
        return round(rate_per_hour * duration_hours, 4)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes GeneratorConfig to dictionary."""
        return {
            "rated_power_kw": float(self.rated_power_kw),
            "fuel_type": str(self.fuel_type),
            "min_load_ratio_pct": float(self.min_load_ratio_pct),
            "fuel_curve_slope_l_per_kwh": float(self.fuel_curve_slope_l_per_kwh),
            "fuel_curve_intercept_l_per_kw_rated": float(self.fuel_curve_intercept_l_per_kw_rated),
            "dispatch_mode": str(self.dispatch_mode),
            "islanding_grid_limit_kw": float(self.islanding_grid_limit_kw),
            "peak_shaving_trigger_kw": float(self.peak_shaving_trigger_kw),
            "is_financial_enabled": bool(self.is_financial_enabled),
            "currency": str(self.currency),
            "capital_cost": float(self.capital_cost),
            "monthly_lease_fee": float(self.monthly_lease_fee),
            "fuel_price_per_unit": float(self.fuel_price_per_unit),
            "maintenance_cost_per_op_hour": float(self.maintenance_cost_per_op_hour),
            "carbon_tax_per_unit": float(self.carbon_tax_per_unit)
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GeneratorConfig":
        """Deserializes dictionary to GeneratorConfig."""
        if not data:
            return cls()
        return cls(
            rated_power_kw=float(data.get("rated_power_kw", 100.0)),
            fuel_type=str(data.get("fuel_type", "Diesel")),
            min_load_ratio_pct=float(data.get("min_load_ratio_pct", 25.0)),
            fuel_curve_slope_l_per_kwh=float(data.get("fuel_curve_slope_l_per_kwh", 0.24)),
            fuel_curve_intercept_l_per_kw_rated=float(data.get("fuel_curve_intercept_l_per_kw_rated", 0.04)),
            dispatch_mode=str(data.get("dispatch_mode", "peak_shaving_assist")),
            islanding_grid_limit_kw=float(data.get("islanding_grid_limit_kw", 0.0)),
            peak_shaving_trigger_kw=float(data.get("peak_shaving_trigger_kw", 300.0)),
            is_financial_enabled=bool(data.get("is_financial_enabled", True)),
            currency=str(data.get("currency", "EUR")),
            capital_cost=float(data.get("capital_cost", 18000.0)),
            monthly_lease_fee=float(data.get("monthly_lease_fee", 0.0)),
            fuel_price_per_unit=float(data.get("fuel_price_per_unit", 1.45)),
            maintenance_cost_per_op_hour=float(data.get("maintenance_cost_per_op_hour", 4.50)),
            carbon_tax_per_unit=float(data.get("carbon_tax_per_unit", 0.0))
        )


@dataclass
class GeneratorKPIs:
    """Key performance metrics summarizing generator simulation results."""
    total_generation_kwh: float = 0.0
    total_fuel_units: float = 0.0                 # Liters or m³
    operating_hours: float = 0.0
    starts_count: int = 0
    fuel_cost_total: float = 0.0
    om_cost_total: float = 0.0
    total_operating_cost: float = 0.0
    levelized_cost_per_kwh: float = 0.0


def get_generator_presets() -> Dict[str, GeneratorConfig]:
    """Returns standard pre-configured commercial and industrial generator presets."""
    return {
        "100 kW Diesel Peaker": GeneratorConfig(
            rated_power_kw=100.0,
            fuel_type="Diesel",
            fuel_curve_slope_l_per_kwh=0.24,
            fuel_curve_intercept_l_per_kw_rated=0.04,
            dispatch_mode="peak_shaving_assist",
            capital_cost=18000.0,
            fuel_price_per_unit=1.45,
            maintenance_cost_per_op_hour=4.50
        ),
        "250 kW Heavy Industrial Diesel": GeneratorConfig(
            rated_power_kw=250.0,
            fuel_type="Diesel",
            fuel_curve_slope_l_per_kwh=0.23,
            fuel_curve_intercept_l_per_kw_rated=0.035,
            dispatch_mode="peak_shaving_assist",
            capital_cost=38000.0,
            fuel_price_per_unit=1.45,
            maintenance_cost_per_op_hour=8.00
        ),
        "150 kW Natural Gas Baseload/Island": GeneratorConfig(
            rated_power_kw=150.0,
            fuel_type="Natural Gas",
            fuel_curve_slope_l_per_kwh=0.28,       # m³/kWh
            fuel_curve_intercept_l_per_kw_rated=0.045,
            dispatch_mode="islanding_grid_congestion",
            islanding_grid_limit_kw=0.0,
            capital_cost=42000.0,
            fuel_price_per_unit=0.85,             # €/m³
            maintenance_cost_per_op_hour=5.50
        ),
        "50 kW Commercial Backup": GeneratorConfig(
            rated_power_kw=50.0,
            fuel_type="Diesel",
            fuel_curve_slope_l_per_kwh=0.26,
            fuel_curve_intercept_l_per_kw_rated=0.05,
            dispatch_mode="emergency_baseload",
            capital_cost=11000.0,
            fuel_price_per_unit=1.45,
            maintenance_cost_per_op_hour=3.00
        )
    }
