"""
========================================================================================
Layer 1: Configuration & Data Models (config_and_models.py)
========================================================================================
Defines strict domain models and data structures without business calculation logic:
  - LoadSeries2025: Standardized 15-minute intervals for 2025 (35,040 steps)
  - DSOTariff: Regulated Dutch grid operator parameters (Liander/Stedin)
  - SupplierTariff: Commercial retailer parameters (Fixed, Variable, Dynamic Spot)
  - MeteringTariff: Certified metering company parameters (flat annual fee)
  - LevyConfig: Statutory energy taxes and VAT rate
  - TariffStage: Switch between Stage 1 (Default Benchmark) and Stage 2 (Custom Quote)
  - Output result containers for monthly series and annual KPIs
========================================================================================
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Any, Optional
import numpy as np
import pandas as pd


class TariffStage(str, Enum):
    """Switch for tariff sourcing level."""
    STAGE_1_DEFAULT = "stage_1_default"
    STAGE_2_QUOTE = "stage_2_quote"


class PricingMode(str, Enum):
    """Energy supplier commodity pricing mechanism."""
    FIXED = "fixed"
    VARIABLE = "variable"
    DYNAMIC = "dynamic"


@dataclass
class LoadSeries2025:
    """
    Standardized, validated 365-day annual load profile for reference year 2025.
    Must contain exactly 35,040 intervals at Delta_t = 0.25 h.
    """
    timestamps: pd.DatetimeIndex
    power_kw: np.ndarray             # 35,040 float array of active power demand (kW)
    energy_kwh: np.ndarray           # 35,040 float array (power_kw * 0.25)
    month_indices: np.ndarray        # 35,040 integer array (1 to 12)
    is_peak_tou: np.ndarray          # 35,040 boolean array (True = Peak/HT, False = Off-Peak/NT)
    total_steps: int = 35040
    step_hours: float = 0.25

    def __post_init__(self):
        if len(self.power_kw) != self.total_steps:
            raise ValueError(
                f"LoadSeries2025 must have exactly {self.total_steps} entries for 2025, "
                f"got {len(self.power_kw)}."
            )
        if len(self.energy_kwh) != self.total_steps:
            self.energy_kwh = self.power_kw * self.step_hours
        if len(self.month_indices) != self.total_steps:
            raise ValueError("Month indices count mismatch.")
        if len(self.is_peak_tou) != self.total_steps:
            raise ValueError("TOU peak classification count mismatch.")

    @property
    def total_energy_kwh(self) -> float:
        return float(np.sum(self.energy_kwh))

    @property
    def peak_demand_kw(self) -> float:
        return float(np.max(self.power_kw)) if len(self.power_kw) > 0 else 0.0


@dataclass
class DSOTariff:
    """
    Regulated Distribution System Operator tariff parameters (Liander/Stedin/Enexis).
    """
    dso_name: str = "Liander Netbeheer B.V."
    grid_tier: str = "MS"                         # Voltage tier, e.g. MS (Medium Voltage)
    connection_category: str = "cap_630"         # Connection category (>160 to 630 kVA)
    
    # Standing fixed connection & grid fees
    fixed_connection_annual: float = 1013.88     # €/year (e.g. 12 x €84.49 for MS transformer)
    fixed_transport_annual: float = 441.00       # €/year (e.g. 12 x €36.75 vastrecht)
    cable_surcharge_annual: float = 0.0          # €/year (Kabellängenaufschlag / line extension fee)
    
    # Capacity tariffs
    contracted_capacity_kw: float = 250.0        # P_vertrag (kW reserved transformer capacity)
    rate_contracted_capacity: float = 2.2233     # €/kW/month (capaciteitstarief for reserved kW)
    rate_peak_demand: float = 3.4600             # €/kW/month (piekvermogenstarief for measured kW max)
    
    # Volumetric transport tariffs
    rate_transport_peak_kwh: float = 0.0000      # €/kWh for Peak (HT) transport (0.00 for MS Liander)
    rate_transport_offpeak_kwh: float = 0.0000   # €/kWh for Off-Peak (NT) transport

    # Breach logic specification
    # When P_peak_m > P_contract: capacity fee billed on P_peak_m in that month
    adjust_capacity_on_breach: bool = True

    # Hard physical connection limit and penalty
    max_physical_limit_kw: float = 1000.0
    peak_penalty_rate_kw: float = 0.2500

    # Reactive power parameters
    reactive_power_tariff: float = 0.0188        # €/kVARh
    min_power_factor: float = 0.90
    reactive_allowance_pct: float = 33.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dso_name": self.dso_name,
            "grid_tier": self.grid_tier,
            "connection_category": self.connection_category,
            "fixed_connection_annual": self.fixed_connection_annual,
            "fixed_transport_annual": self.fixed_transport_annual,
            "cable_surcharge_annual": self.cable_surcharge_annual,
            "contracted_capacity_kw": self.contracted_capacity_kw,
            "rate_contracted_capacity": self.rate_contracted_capacity,
            "rate_peak_demand": self.rate_peak_demand,
            "rate_transport_peak_kwh": self.rate_transport_peak_kwh,
            "rate_transport_offpeak_kwh": self.rate_transport_offpeak_kwh,
            "adjust_capacity_on_breach": self.adjust_capacity_on_breach,
            "max_physical_limit_kw": self.max_physical_limit_kw,
            "peak_penalty_rate_kw": self.peak_penalty_rate_kw,
            "reactive_power_tariff": self.reactive_power_tariff,
            "min_power_factor": self.min_power_factor,
            "reactive_allowance_pct": self.reactive_allowance_pct,
        }


@dataclass
class SupplierTariff:
    """
    Commercial energy retailer contract parameters (Vattenfall, Eneco, etc.).
    Supports three distinct calculation mechanisms: Fixed, Variable, Dynamic Spot,
    as well as Dual TOU (Normaal / Dal) commodity pricing and procurement surcharges.
    """
    supplier_name: str = "Vattenfall Zakelijk"
    pricing_mode: PricingMode = PricingMode.DYNAMIC
    tariff_product_name: str = "Vast 1 Jaar (Dubbeltarief)"
    
    # Standing administrative fee
    base_fee_annual: float = 180.00              # €/year (e.g. 12 x €15.00/month)
    
    # Mode FIXED: flat rate per kWh across the whole year (Single rate)
    fixed_rate_kwh: float = 0.1250               # €/kWh
    
    # Mode FIXED (Dual TOU): Separate High Tariff (HT) and Low Tariff (NT) commodity rates
    is_dual_rate: bool = False                   # True = Dubbeltarief (HT / NT), False = Enkeltarief
    fixed_rate_peak_kwh: float = 0.1340          # €/kWh Normaal / High Tariff
    fixed_rate_offpeak_kwh: float = 0.1180       # €/kWh Dal / Low Tariff
    
    # Surcharges & Guarantees
    procurement_fee_kwh: float = 0.0000          # €/kWh Inkoopvergoeding
    green_certificate_surcharge_kwh: float = 0.0 # €/kWh GvO (Garantie van Oorsprong)
    
    # Mode VARIABLE: 12 monthly rates (€/kWh per month)
    monthly_variable_rates: List[float] = field(
        default_factory=lambda: [0.130, 0.125, 0.120, 0.115, 0.110, 0.105, 0.105, 0.110, 0.115, 0.120, 0.125, 0.130]
    )
    
    # Mode DYNAMIC: EPEX Spot wholesale price series + supplier retail markup
    market_price_profile_id: str = "epex_nl_2025"
    supplier_margin_kwh: float = 0.0075          # €/kWh retail margin (Opslag)
    spot_default_fallback_rate: float = 0.1200   # €/kWh fallback if spot profile step missing

    def to_dict(self) -> Dict[str, Any]:
        return {
            "supplier_name": self.supplier_name,
            "pricing_mode": self.pricing_mode.value,
            "tariff_product_name": self.tariff_product_name,
            "base_fee_annual": self.base_fee_annual,
            "fixed_rate_kwh": self.fixed_rate_kwh,
            "is_dual_rate": self.is_dual_rate,
            "fixed_rate_peak_kwh": self.fixed_rate_peak_kwh,
            "fixed_rate_offpeak_kwh": self.fixed_rate_offpeak_kwh,
            "procurement_fee_kwh": self.procurement_fee_kwh,
            "green_certificate_surcharge_kwh": self.green_certificate_surcharge_kwh,
            "monthly_variable_rates": list(self.monthly_variable_rates),
            "market_price_profile_id": self.market_price_profile_id,
            "supplier_margin_kwh": self.supplier_margin_kwh,
            "spot_default_fallback_rate": self.spot_default_fallback_rate,
        }


@dataclass
class MeteringTariff:
    """
    Certified Metering Company (Meetbedrijf / Messstellenbetrieb) flat fee & service tier.
    Independent of volume or peak demand.
    """
    meter_company_name: str = "Fudura B.V."
    service_package_name: str = "Kwartierdata Telemetrie MS"
    annual_flat_fee: float = 900.00              # €/year (e.g. 12 x €75.00/month RLM interval telemetry)
    description: str = "Grootverbruik kwartierdata telemetrie (RLM)"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "meter_company_name": self.meter_company_name,
            "service_package_name": self.service_package_name,
            "annual_flat_fee": self.annual_flat_fee,
            "description": self.description,
        }


@dataclass
class LevyConfig:
    """
    Statutory government levies, environmental taxes, tax reduction credits, and VAT.
    """
    # Flat volumetric levy (€/kWh) for 2025 baseline evaluation
    statutory_levy_rate_kwh: float = 0.0125      # €/kWh (Energiebelasting & ODE approximation)
    annual_tax_reduction: float = 0.0            # €/year (Vermindering energiebelasting / Heffingskorting)
    vat_rate_pct: float = 21.0                   # Statutory VAT (BTW 21.0% in the Netherlands)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "statutory_levy_rate_kwh": self.statutory_levy_rate_kwh,
            "annual_tax_reduction": self.annual_tax_reduction,
            "vat_rate_pct": self.vat_rate_pct,
        }


@dataclass
class StatusQuoConfig2025:
    """Master configuration container for the 2025 Status Quo baseline assessment."""
    stage: TariffStage = TariffStage.STAGE_1_DEFAULT
    dso: DSOTariff = field(default_factory=DSOTariff)
    supplier: SupplierTariff = field(default_factory=SupplierTariff)
    metering: MeteringTariff = field(default_factory=MeteringTariff)
    levies: LevyConfig = field(default_factory=LevyConfig)
    
    # Financial lifecycle evaluation parameters
    discount_rate_pct: float = 5.0               # r: WACC / hurdle rate (5.0%)
    energy_escalation_pct: float = 3.0           # g: Annual price escalation rate (3.0%)
    evaluation_horizon_years: int = 15           # 15-year TCO horizon


# ======================================================================================
# Calculation Result Containers
# ======================================================================================

@dataclass
class MonthlyConsumptionRecord:
    """Consumption metrics aggregated for a single calendar month."""
    month_index: int                             # 1 to 12
    month_name: str                              # "January", "February", ...
    days_count: int                              # 31, 28, 31, ...
    total_kwh: float                             # Total energy E_m
    peak_tou_kwh: float                          # High-tariff / Peak energy (HT)
    offpeak_tou_kwh: float                       # Low-tariff / Off-peak energy (NT)
    peak_demand_kw: float                        # P_peak,m: Highest 15-minute active power (kW)


@dataclass
class DSOMonthlyResult:
    """Monthly DSO cost statement and contract capacity audit."""
    month_index: int
    fixed_connection_fee: float                  # Monthly connection fee
    fixed_transport_fee: float                   # Monthly vastrecht
    cable_surcharge: float                       # Monthly cable fee
    volumetric_transport_fee: float              # kWh transport cost
    measured_peak_demand_kw: float               # P_peak,m
    billed_capacity_kw: float                    # Max(P_contract, P_peak_m) if breach
    contracted_capacity_fee: float               # Contract capacity charge
    peak_demand_fee: float                       # Measured peak fee (P_peak,m * rate)
    is_capacity_breached: bool                   # True if P_peak,m > P_contract
    excess_capacity_kw: float                    # Max(0, P_peak,m - P_contract)
    subtotal_dso_net: float                      # Total DSO net for this month


@dataclass
class CommercialMonthlyResult:
    """Monthly commercial supplier, metering, and tax results."""
    month_index: int
    supplier_base_fee: float                     # Base standing charge
    supplier_energy_cost: float                  # Energy commodity cost (Fixed/Var/Spot)
    metering_fee: float                          # Meetbedrijf flat fee (annual / 12)
    statutory_levies: float                      # E_m * levy rate
    feed_in_credit: float = 0.0                  # Status Quo has 0.00 feed-in credit
    subtotal_commercial_net: float = 0.0         # Supplier + Metering + Levies net


@dataclass
class StatusQuoMonthlyResult:
    """Consolidated monthly record containing all components."""
    month_index: int
    month_name: str
    consumption: MonthlyConsumptionRecord
    dso: DSOMonthlyResult
    commercial: CommercialMonthlyResult
    total_net: float
    vat_amount: float
    total_gross: float
    effective_rate_net_kwh: float


@dataclass
class StatusQuoAnnualResult:
    """Final annual accounting aggregation and 15-year TCO KPI summary."""
    config: StatusQuoConfig2025
    total_consumption_kwh: float
    total_peak_tou_kwh: float
    total_offpeak_tou_kwh: float
    annual_peak_demand_kw: float
    
    # 12-month series
    monthly_records: List[StatusQuoMonthlyResult]
    
    # Party Subtotals (Net)
    total_dso_net: float
    total_supplier_net: float
    total_metering_net: float
    total_levies_net: float
    total_feed_in_credit: float = 0.0
    
    # Consolidated Totals
    total_status_quo_net: float = 0.0
    vat_rate_pct: float = 21.0
    total_vat_amount: float = 0.0
    total_status_quo_gross: float = 0.0
    
    # Economic KPIs
    blended_price_net_kwh: float = 0.0           # Total Net / Total kWh (€/kWh)
    blended_price_gross_kwh: float = 0.0         # Total Gross / Total kWh (€/kWh)
    
    # 15-year Lifecycle TCO
    tco_15_npv: float = 0.0                      # Discounted NPV sum over 15 years
    tco_yearly_cashflows_net: List[float] = field(default_factory=list)
    tco_discounted_cashflows: List[float] = field(default_factory=list)

    # Audit points tracking
    has_capacity_breach: bool = False
    breach_months: List[int] = field(default_factory=list)
