"""
========================================================================================
Battery Energy Storage System (BESS) Data Models (current_model/models/bess.py)
========================================================================================

Description:
------------
Defines dataclasses and helpers for Battery Energy Storage Systems (BESS):
  - `BESSConfig`: Storage capacity (kWh), charge/discharge ratings (kW), round-trip
    efficiency, DoD/SoC operational boundaries, dispatch strategies (Self-Consumption,
    Peak Shaving, Tariff Arbitrage), and lifecycle investment economics (CAPEX $/kWh,
    annual O&M, and mid-life cell replacement).
  - `BESSKPIs`: High-level annual performance indicators (cycles, throughput, losses).
  - `get_bess_presets`: Standard commercial & industrial battery configurations.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List


@dataclass
class BESSConfig:
    """
    Technical and economic specifications for a Battery Energy Storage System.
    """
    # Technical Ratings & Boundaries
    capacity_kwh: float = 100.0                   # Nominal storage capacity (kWh)
    max_charge_power_kw: float = 50.0             # Max continuous charging power (kW)
    max_discharge_power_kw: float = 50.0          # Max continuous discharging power (kW)
    round_trip_efficiency_pct: float = 90.0       # Round-trip AC/DC efficiency (%)
    soc_min_pct: float = 10.0                     # Minimum allowable State of Charge (%)
    soc_max_pct: float = 95.0                     # Maximum allowable State of Charge (%)
    initial_soc_pct: float = 50.0                 # Initial State of Charge at simulation start (%)
    max_dod_pct: float = 85.0                     # Maximum Depth of Discharge (%)

    # Dispatch Strategy Configuration
    # Options: "self_consumption", "peak_shaving", "tariff_arbitrage"
    dispatch_strategy: str = "self_consumption"
    peak_shaving_threshold_kw: float = 200.0      # Grid capping limit in kW for peak shaving mode
    arbitrage_charge_start: str = "00:00"         # TOU low-rate charge start time
    arbitrage_charge_end: str = "06:00"           # TOU low-rate charge end time
    arbitrage_discharge_start: str = "17:00"      # TOU high-rate discharge start time
    arbitrage_discharge_end: str = "22:00"        # TOU high-rate discharge end time

    # Financial & Lifecycle Assumptions
    is_financial_enabled: bool = True
    currency: str = "EUR"
    cost_per_kwh: float = 350.0                   # Specific investment cost per kWh (€/kWh or $/kWh)
    fixed_installation_cost: float = 5000.0       # Fixed Inverter/BOS/Grid connection fee (€)
    annual_om_pct: float = 1.5                    # Annual operations & maintenance (% of initial CAPEX)
    cell_replacement_year: int = 10               # Scheduled cell refresh year
    cell_replacement_cost_pct: float = 50.0       # Replacement cost (% of initial battery module CAPEX)

    @property
    def effective_usable_kwh(self) -> float:
        """Net usable energy capacity within safe SoC envelope (kWh)."""
        span_pct = max(0.0, min(100.0, self.soc_max_pct - self.soc_min_pct))
        return round(self.capacity_kwh * (span_pct / 100.0), 2)

    @property
    def c_rate_discharge(self) -> float:
        """Discharge C-rate (Power kW / Capacity kWh)."""
        return round(self.max_discharge_power_kw / max(1e-3, self.capacity_kwh), 2)

    @property
    def c_rate_charge(self) -> float:
        """Charge C-rate (Power kW / Capacity kWh)."""
        return round(self.max_charge_power_kw / max(1e-3, self.capacity_kwh), 2)

    @property
    def total_capex(self) -> float:
        """Total turn-key CAPEX investment for the BESS system."""
        if not self.is_financial_enabled:
            return 0.0
        return round((self.capacity_kwh * self.cost_per_kwh) + self.fixed_installation_cost, 2)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes BESSConfig to a JSON-ready dictionary."""
        return {
            "capacity_kwh": float(self.capacity_kwh),
            "max_charge_power_kw": float(self.max_charge_power_kw),
            "max_discharge_power_kw": float(self.max_discharge_power_kw),
            "round_trip_efficiency_pct": float(self.round_trip_efficiency_pct),
            "soc_min_pct": float(self.soc_min_pct),
            "soc_max_pct": float(self.soc_max_pct),
            "initial_soc_pct": float(self.initial_soc_pct),
            "max_dod_pct": float(self.max_dod_pct),
            "dispatch_strategy": str(self.dispatch_strategy),
            "peak_shaving_threshold_kw": float(self.peak_shaving_threshold_kw),
            "arbitrage_charge_start": str(self.arbitrage_charge_start),
            "arbitrage_charge_end": str(self.arbitrage_charge_end),
            "arbitrage_discharge_start": str(self.arbitrage_discharge_start),
            "arbitrage_discharge_end": str(self.arbitrage_discharge_end),
            "is_financial_enabled": bool(self.is_financial_enabled),
            "currency": str(self.currency),
            "cost_per_kwh": float(self.cost_per_kwh),
            "fixed_installation_cost": float(self.fixed_installation_cost),
            "annual_om_pct": float(self.annual_om_pct),
            "cell_replacement_year": int(self.cell_replacement_year),
            "cell_replacement_cost_pct": float(self.cell_replacement_cost_pct)
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BESSConfig":
        """Deserializes a dictionary into a BESSConfig instance."""
        if not data:
            return cls()
        return cls(
            capacity_kwh=float(data.get("capacity_kwh", 100.0)),
            max_charge_power_kw=float(data.get("max_charge_power_kw", 50.0)),
            max_discharge_power_kw=float(data.get("max_discharge_power_kw", 50.0)),
            round_trip_efficiency_pct=float(data.get("round_trip_efficiency_pct", 90.0)),
            soc_min_pct=float(data.get("soc_min_pct", 10.0)),
            soc_max_pct=float(data.get("soc_max_pct", 95.0)),
            initial_soc_pct=float(data.get("initial_soc_pct", 50.0)),
            max_dod_pct=float(data.get("max_dod_pct", 85.0)),
            dispatch_strategy=str(data.get("dispatch_strategy", "self_consumption")),
            peak_shaving_threshold_kw=float(data.get("peak_shaving_threshold_kw", 200.0)),
            arbitrage_charge_start=str(data.get("arbitrage_charge_start", "00:00")),
            arbitrage_charge_end=str(data.get("arbitrage_charge_end", "06:00")),
            arbitrage_discharge_start=str(data.get("arbitrage_discharge_start", "17:00")),
            arbitrage_discharge_end=str(data.get("arbitrage_discharge_end", "22:00")),
            is_financial_enabled=bool(data.get("is_financial_enabled", True)),
            currency=str(data.get("currency", "EUR")),
            cost_per_kwh=float(data.get("cost_per_kwh", 350.0)),
            fixed_installation_cost=float(data.get("fixed_installation_cost", 5000.0)),
            annual_om_pct=float(data.get("annual_om_pct", 1.5)),
            cell_replacement_year=int(data.get("cell_replacement_year", 10)),
            cell_replacement_cost_pct=float(data.get("cell_replacement_cost_pct", 50.0))
        )


@dataclass
class BESSKPIs:
    """Key performance metrics summarizing BESS simulation results."""
    total_charged_kwh: float = 0.0
    total_discharged_kwh: float = 0.0
    round_trip_loss_kwh: float = 0.0
    equivalent_full_cycles: float = 0.0
    peak_shaved_kw: float = 0.0
    avg_daily_throughput_kwh: float = 0.0
    annual_degradation_pct: float = 2.0


@dataclass
class BESSFinancialMetrics:
    """Complete multi-year lifecycle financial metrics for a BESS installation."""
    is_configured: bool = True
    total_capex: float = 0.0
    capex_per_kwh: float = 0.0
    annual_opex_year1: float = 0.0

    # Annual Savings Breakdown
    annual_energy_savings: float = 0.0
    annual_demand_charge_savings: float = 0.0
    annual_penalty_savings: float = 0.0
    annual_gross_savings: float = 0.0
    annual_net_savings_year1: float = 0.0

    # Investment & Amortization KPIs
    simple_payback_years: Optional[float] = None
    discounted_payback_years: Optional[float] = None
    net_present_value: float = 0.0
    internal_rate_of_return_pct: Optional[float] = None
    levelized_cost_of_storage_eur_kwh: float = 0.0  # LCOS (€/kWh)
    return_on_investment_pct: float = 0.0

    # Multi-Year Projections & Trajectories
    cash_flow_table: List[Dict[str, Any]] = field(default_factory=list)
    cumulative_cash_flow: List[float] = field(default_factory=list)
    cumulative_status_quo: List[float] = field(default_factory=list)
    cumulative_with_bess: List[float] = field(default_factory=list)
    annual_status_quo_costs: List[float] = field(default_factory=list)
    annual_with_bess_costs: List[float] = field(default_factory=list)


def get_bess_presets() -> Dict[str, BESSConfig]:
    """Returns standard pre-configured commercial and industrial BESS templates."""
    return {
        "Small C&I Storage (100 kWh / 50 kW)": BESSConfig(
            capacity_kwh=100.0,
            max_charge_power_kw=50.0,
            max_discharge_power_kw=50.0,
            dispatch_strategy="self_consumption",
            cost_per_kwh=380.0,
            fixed_installation_cost=4000.0
        ),
        "Medium Commercial Storage (250 kWh / 125 kW)": BESSConfig(
            capacity_kwh=250.0,
            max_charge_power_kw=125.0,
            max_discharge_power_kw=125.0,
            dispatch_strategy="self_consumption",
            cost_per_kwh=340.0,
            fixed_installation_cost=7500.0
        ),
        "Industrial Peak Shaver (200 kWh / 200 kW - 1C)": BESSConfig(
            capacity_kwh=200.0,
            max_charge_power_kw=200.0,
            max_discharge_power_kw=200.0,
            dispatch_strategy="peak_shaving",
            peak_shaving_threshold_kw=250.0,
            cost_per_kwh=360.0,
            fixed_installation_cost=8000.0
        ),
        "Large Industrial Hub (500 kWh / 250 kW)": BESSConfig(
            capacity_kwh=500.0,
            max_charge_power_kw=250.0,
            max_discharge_power_kw=250.0,
            dispatch_strategy="self_consumption",
            cost_per_kwh=310.0,
            fixed_installation_cost=12000.0
        )
    }
