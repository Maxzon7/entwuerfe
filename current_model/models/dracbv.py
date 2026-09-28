"""
========================================================================================
DRACBV Multi-Path Simulation Data Models (current_model/models/dracbv.py)
========================================================================================

Description:
------------
Defines domain data models for DRACBV consultancy scenarios:
  - Problem classification (Connection too small, Grid congestion, Off-grid, etc.)
  - Grid upgrade parameters (e.g. AC5 / higher tier connection and lead times)
  - BESS peak shaving parameters (e.g. AC4 + BESS)
  - Generator congestion bridging parameters (rental / purchase, fuel curves)
  - Lifecycle economic evaluation parameters (WACC, inflation, duration)
  - Comparative solution summary records
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional


@dataclass
class DRACBVConfig:
    """Configuration container for a DRACBV multi-path simulation."""
    # Problem Classification
    problem_type: str = "connection_too_small"
    # Options:
    # "connection_too_small": Contracted capacity too small for peak demand
    # "grid_congestion": Grid operator has a waiting list / lead time (e.g. 24-60 months)
    # "no_connection": Off-grid greenfield site / no physical connection
    # "connection_too_expensive": High connection reinforcement CAPEX quote
    # "unstable_connection": Power quality / frequent brownouts

    # Project Economics & Horizon
    project_duration_years: int = 10
    currency: str = "EUR"
    discount_rate_pct: float = 6.0          # WACC / Hurdle rate (%)
    inflation_rate_pct: float = 2.5         # General inflation (%)
    energy_price_escalation_pct: float = 3.0 # Annual energy cost rise (%)

    # Path A: Traditional Grid Upgrade (e.g. AC5 Upgrade)
    upgrade_enabled: bool = True
    upgrade_target_capacity_kw: float = 600.0
    upgrade_capex: float = 45000.0          # Transformer / network reinforcement fee (€)
    upgrade_monthly_capacity_tariff: float = 0.20 # Capacity fee (€/kW/month)
    upgrade_lead_time_months: int = 24      # Grid operator delivery queue (months)

    # Path B: Peak Shaving via BESS (e.g. Keep AC4 + BESS)
    bess_enabled: bool = True
    bess_target_cap_kw: float = 400.0       # Peak demand cap (kW)
    bess_capacity_kwh: float = 200.0        # Storage capacity (kWh)
    bess_power_kw: float = 100.0            # Max discharge/charge power (kW)
    bess_capex_per_kwh: float = 350.0       # Battery acquisition (€/kWh)
    bess_fixed_install_capex: float = 5000.0# Inverter & installation (€)
    bess_round_trip_eff_pct: float = 90.0   # Round-trip efficiency (%)
    bess_annual_om_pct: float = 1.5         # O&M (% of initial CAPEX)
    bess_replacement_year: int = 10         # Re-powering / cell refresh year
    bess_replacement_cost_pct: float = 50.0 # Refresh cost (% of battery CAPEX)

    # Path C: Congestion Bridging via Generator (Genset Assist)
    generator_enabled: bool = True
    generator_power_kw: float = 150.0       # Genset rated output (kW)
    generator_fuel_type: str = "Diesel"     # "Diesel", "Natural Gas", "HVO/Biofuel"
    generator_mode: str = "rental"          # "rental" or "purchase"
    generator_monthly_rental: float = 1200.0# Monthly leasing fee (€/month)
    generator_purchase_capex: float = 24000.0 # Purchase CAPEX (€)
    generator_fuel_price_per_unit: float = 1.50 # Fuel price (€/L or €/m³)
    generator_maintenance_per_op_hour: float = 4.0 # Service cost per hour (€/h)
    generator_min_load_pct: float = 25.0    # Minimum loading ratio (%)

    # Path D: Solar PV Self-Consumption Coupling
    solar_enabled: bool = True
    solar_target_coverage_pct: float = 40.0 # 40%, 60%, 80%, or 100% net coverage
    solar_capex_per_wp: float = 0.85        # PV turnkey CAPEX (€/Wp)
    solar_specific_yield_kwh_per_kwp: float = 1050.0 # Regional specific yield (kWh/kWp/a)
    solar_annual_om_pct: float = 1.2        # O&M (% of initial CAPEX)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes DRACBVConfig to a dictionary."""
        return {
            "problem_type": self.problem_type,
            "project_duration_years": self.project_duration_years,
            "currency": self.currency,
            "discount_rate_pct": self.discount_rate_pct,
            "inflation_rate_pct": self.inflation_rate_pct,
            "energy_price_escalation_pct": self.energy_price_escalation_pct,
            "upgrade_enabled": self.upgrade_enabled,
            "upgrade_target_capacity_kw": self.upgrade_target_capacity_kw,
            "upgrade_capex": self.upgrade_capex,
            "upgrade_monthly_capacity_tariff": self.upgrade_monthly_capacity_tariff,
            "upgrade_lead_time_months": self.upgrade_lead_time_months,
            "bess_enabled": self.bess_enabled,
            "bess_target_cap_kw": self.bess_target_cap_kw,
            "bess_capacity_kwh": self.bess_capacity_kwh,
            "bess_power_kw": self.bess_power_kw,
            "bess_capex_per_kwh": self.bess_capex_per_kwh,
            "bess_fixed_install_capex": self.bess_fixed_install_capex,
            "bess_round_trip_eff_pct": self.bess_round_trip_eff_pct,
            "bess_annual_om_pct": self.bess_annual_om_pct,
            "bess_replacement_year": self.bess_replacement_year,
            "bess_replacement_cost_pct": self.bess_replacement_cost_pct,
            "generator_enabled": self.generator_enabled,
            "generator_power_kw": self.generator_power_kw,
            "generator_fuel_type": self.generator_fuel_type,
            "generator_mode": self.generator_mode,
            "generator_monthly_rental": self.generator_monthly_rental,
            "generator_purchase_capex": self.generator_purchase_capex,
            "generator_fuel_price_per_unit": self.generator_fuel_price_per_unit,
            "generator_maintenance_per_op_hour": self.generator_maintenance_per_op_hour,
            "generator_min_load_pct": self.generator_min_load_pct,
            "solar_enabled": self.solar_enabled,
            "solar_target_coverage_pct": self.solar_target_coverage_pct,
            "solar_capex_per_wp": self.solar_capex_per_wp,
            "solar_specific_yield_kwh_per_kwp": self.solar_specific_yield_kwh_per_kwp,
            "solar_annual_om_pct": self.solar_annual_om_pct
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DRACBVConfig":
        """Deserializes dictionary into DRACBVConfig."""
        if not data:
            return cls()
        return cls(
            problem_type=str(data.get("problem_type", "connection_too_small")),
            project_duration_years=int(data.get("project_duration_years", 10)),
            currency=str(data.get("currency", "EUR")),
            discount_rate_pct=float(data.get("discount_rate_pct", 6.0)),
            inflation_rate_pct=float(data.get("inflation_rate_pct", 2.5)),
            energy_price_escalation_pct=float(data.get("energy_price_escalation_pct", 3.0)),
            upgrade_enabled=bool(data.get("upgrade_enabled", True)),
            upgrade_target_capacity_kw=float(data.get("upgrade_target_capacity_kw", 600.0)),
            upgrade_capex=float(data.get("upgrade_capex", 45000.0)),
            upgrade_monthly_capacity_tariff=float(data.get("upgrade_monthly_capacity_tariff", 0.20)),
            upgrade_lead_time_months=int(data.get("upgrade_lead_time_months", 24)),
            bess_enabled=bool(data.get("bess_enabled", True)),
            bess_target_cap_kw=float(data.get("bess_target_cap_kw", 400.0)),
            bess_capacity_kwh=float(data.get("bess_capacity_kwh", 200.0)),
            bess_power_kw=float(data.get("bess_power_kw", 100.0)),
            bess_capex_per_kwh=float(data.get("bess_capex_per_kwh", 350.0)),
            bess_fixed_install_capex=float(data.get("bess_fixed_install_capex", 5000.0)),
            bess_round_trip_eff_pct=float(data.get("bess_round_trip_eff_pct", 90.0)),
            bess_annual_om_pct=float(data.get("bess_annual_om_pct", 1.5)),
            bess_replacement_year=int(data.get("bess_replacement_year", 10)),
            bess_replacement_cost_pct=float(data.get("bess_replacement_cost_pct", 50.0)),
            generator_enabled=bool(data.get("generator_enabled", True)),
            generator_power_kw=float(data.get("generator_power_kw", 150.0)),
            generator_fuel_type=str(data.get("generator_fuel_type", "Diesel")),
            generator_mode=str(data.get("generator_mode", "rental")),
            generator_monthly_rental=float(data.get("generator_monthly_rental", 1200.0)),
            generator_purchase_capex=float(data.get("generator_purchase_capex", 24000.0)),
            generator_fuel_price_per_unit=float(data.get("generator_fuel_price_per_unit", 1.50)),
            generator_maintenance_per_op_hour=float(data.get("generator_maintenance_per_op_hour", 4.0)),
            generator_min_load_pct=float(data.get("generator_min_load_pct", 25.0)),
            solar_enabled=bool(data.get("solar_enabled", True)),
            solar_target_coverage_pct=float(data.get("solar_target_coverage_pct", 40.0)),
            solar_capex_per_wp=float(data.get("solar_capex_per_wp", 0.85)),
            solar_specific_yield_kwh_per_kwp=float(data.get("solar_specific_yield_kwh_per_kwp", 1050.0)),
            solar_annual_om_pct=float(data.get("solar_annual_om_pct", 1.2))
        )


@dataclass
class DRACBVSolutionSummary:
    """Evaluation summary for a single DRACBV solution path."""
    path_id: str
    name: str
    technology_label: str
    description: str
    color_code: str = "#2563EB"
    is_technically_feasible: bool = True
    feasibility_notes: str = ""

    # Electrical & Technical Metrics
    peak_grid_draw_kw: float = 0.0
    peak_reduction_kw: float = 0.0
    violations_count: int = 0
    violations_eliminated_pct: float = 100.0
    unserved_energy_kwh: float = 0.0
    solar_generation_mwh: float = 0.0
    bess_throughput_mwh: float = 0.0
    bess_cycles_annual: float = 0.0
    generator_runtime_hours: float = 0.0
    generator_fuel_liters: float = 0.0
    carbon_emissions_tons: float = 0.0

    # Economics & Lifecycle Metrics
    initial_capex: float = 0.0
    annual_opex_year1: float = 0.0
    annual_grid_bill_year1: float = 0.0
    lifetime_tco: float = 0.0
    npv_vs_baseline: float = 0.0
    payback_years: Optional[float] = None
    levelized_cost_per_kwh: float = 0.0

    # Multi-year cash flows (length = project_duration_years + 1)
    cashflows: List[float] = field(default_factory=list)
    cumulative_cashflows: List[float] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes DRACBVSolutionSummary to a dictionary."""
        return {
            "path_id": self.path_id,
            "name": self.name,
            "technology_label": self.technology_label,
            "description": self.description,
            "color_code": self.color_code,
            "is_technically_feasible": self.is_technically_feasible,
            "feasibility_notes": self.feasibility_notes,
            "peak_grid_draw_kw": self.peak_grid_draw_kw,
            "peak_reduction_kw": self.peak_reduction_kw,
            "violations_count": self.violations_count,
            "violations_eliminated_pct": self.violations_eliminated_pct,
            "unserved_energy_kwh": self.unserved_energy_kwh,
            "solar_generation_mwh": self.solar_generation_mwh,
            "bess_throughput_mwh": self.bess_throughput_mwh,
            "bess_cycles_annual": self.bess_cycles_annual,
            "generator_runtime_hours": self.generator_runtime_hours,
            "generator_fuel_liters": self.generator_fuel_liters,
            "carbon_emissions_tons": self.carbon_emissions_tons,
            "initial_capex": self.initial_capex,
            "annual_opex_year1": self.annual_opex_year1,
            "annual_grid_bill_year1": self.annual_grid_bill_year1,
            "lifetime_tco": self.lifetime_tco,
            "npv_vs_baseline": self.npv_vs_baseline,
            "payback_years": self.payback_years,
            "levelized_cost_per_kwh": self.levelized_cost_per_kwh,
            "cashflows": self.cashflows,
            "cumulative_cashflows": self.cumulative_cashflows
        }
