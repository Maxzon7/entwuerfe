"""
========================================================================================
Layer 1: Configuration & Data Models (engine/config_and_models.py)
Current Situation (Status Quo) Sandbox Engine
========================================================================================
Defines strict domain models and data structures for Dutch Grootverbruik electricity accounting:
  - LoadSeries2025: Standardized 15-minute intervals for 2025 (35,040 steps)
  - DSOTariff: Regulated Dutch grid operator parameters (Liander AC2–AC6, Enexis, Stedin)
    including PAV_mnd, Vastrecht_mnd, GTV, Monatspeak, Transport, 12-month ratchet, cos phi 0.85
  - SupplierTariff: Commercial retailer parameters supporting Fixed (Dual TOU), Variable,
    Dynamic Spot (EPEX Spot), and Tranche / Click (ICE Endex + Spot), with 5-component invoice
  - TrafoRentalTariff: Transformer & MV station rental/contracting (Fudura, Kenter, Joulz, Alfen)
  - MeteringTariff: Certified metering company (EMV) telemetry fees (15-min RLM)
  - LevyConfig & TaxBracket: Degressive cumulative 5-bracket Energiebelasting (2025/2026) + Vermindering
  - Result containers for monthly itemized records and consolidated annual KPIs
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
    TRANCHE = "tranche"
    TRANCHE_CLICK = "tranche"


class SupplierCategory(str, Enum):
    """Dutch commercial electricity supplier classification."""
    MAJOR_UTILITY = "Major Integrated Utilities"
    B2B_PORTFOLIO = "B2B Portfolio Specialists"
    DYNAMIC_SPOT = "Pure Dynamic & Spot Providers"
    GREEN_SOURCING = "Green Sourcing Specialists"


@dataclass
class TrancheBlock:
    """Quarterly or monthly tranche hedge block for Click contracts."""
    label: str = "Quarter"                         # e.g. "Q1 (Jan-Mar)"
    months: List[int] = field(default_factory=list)# e.g. [1, 2, 3]
    hedged_share_pct: float = 0.0                 # e.g. 75.0 (%)
    click_price_kwh: float = 0.0                  # e.g. 0.1080 (€/kWh)
    tranche_id: Optional[str] = None
    quarter_label: Optional[str] = None
    hedged_capacity_mw: Optional[float] = None
    hedged_price_eur_mwh: Optional[float] = None
    is_locked: bool = True

    def __post_init__(self):
        if self.quarter_label and (not self.label or self.label == "Quarter"):
            self.label = self.quarter_label
        if self.hedged_price_eur_mwh is not None and self.click_price_kwh == 0.0:
            self.click_price_kwh = self.hedged_price_eur_mwh / 1000.0
        if not self.months and self.label:
            if "Q1" in self.label:
                self.months = [1, 2, 3]
            elif "Q2" in self.label:
                self.months = [4, 5, 6]
            elif "Q3" in self.label:
                self.months = [7, 8, 9]
            elif "Q4" in self.label:
                self.months = [10, 11, 12]
            else:
                self.months = list(range(1, 13))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "months": list(self.months),
            "hedged_share_pct": self.hedged_share_pct,
            "click_price_kwh": self.click_price_kwh,
            "tranche_id": self.tranche_id,
            "quarter_label": self.quarter_label,
            "hedged_capacity_mw": self.hedged_capacity_mw,
            "hedged_price_eur_mwh": self.hedged_price_eur_mwh,
            "is_locked": self.is_locked,
        }


@dataclass
class TaxBracket:
    """Statutory energy tax bracket (Energiebelasting)."""
    zone_name: str                 # e.g. "Zone 1 & 2"
    lower_kwh: float               # e.g. 0.0
    upper_kwh: float               # e.g. 10000.0 (float("inf") for top tier)
    rate_kwh: float                # e.g. 0.09161 (€/kWh)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "zone_name": self.zone_name,
            "lower_kwh": self.lower_kwh,
            "upper_kwh": self.upper_kwh if self.upper_kwh != float("inf") else -1.0,
            "rate_kwh": self.rate_kwh,
        }


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
    Implements full 6-component Dutch Grootverbruik billing formula:
      K_Netz = PAV_mnd + Vastrecht_mnd + (P_contract * T_GTV) + (P_piek * T_piek) + Sum(E_i * T_trans,i) + K_Blind
    """
    dso_name: str = "Liander N.V."
    grid_tier: str = "AC5a - MS eigene Station (136 bis 536 kW)"
    connection_category: str = "AC5a"            # AC2, AC4a, AC4b, AC5a, AC5b, AC5, AC6
    
    # Standing fixed connection & grid fees
    fixed_connection_annual: float = 1013.88     # €/year (PAV = 12 x €84.49 for AC5a Liander)
    fixed_transport_annual: float = 441.00       # €/year (Vastrecht = 12 x €36.75)
    cable_surcharge_annual: float = 0.0          # €/year (Meerlengte cable surcharge > 25m)
    
    # Capacity tariffs
    contracted_capacity_kw: float = 536.0        # P_contract (Gecontracteerd Transportvermogen in kW)
    rate_contracted_capacity: float = 2.2233     # €/kW/month (GTV rate, e.g. €26.680 / 12 for AC5a)
    rate_peak_demand: float = 3.4600             # €/kW/month (Maandpiek rate for highest 15-min peak)
    
    # Volumetric transport tariffs
    rate_transport_peak_kwh: float = 0.0220      # €/kWh Peak / Normaal transport
    rate_transport_offpeak_kwh: float = 0.0220   # €/kWh Off-Peak / Dal transport

    # Breach & Ratchet logic specification
    # Regular Dutch rule: breach locks contracted capacity to peak for 12 months
    adjust_capacity_on_breach: bool = True
    ratchet_12_months: bool = True               # True 12-month ratchet locking

    # Hard physical connection limit and penalty (Netcongestie)
    max_physical_limit_kw: float = 1000.0
    peak_penalty_rate_kw: float = 0.2500

    # Reactive power parameters (ACM standard threshold: cos phi >= 0.85)
    reactive_power_tariff: float = 0.0188        # €/kVARh
    min_power_factor: float = 0.85               # ACM standard power factor (cos phi >= 0.85)
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
            "ratchet_12_months": self.ratchet_12_months,
            "max_physical_limit_kw": self.max_physical_limit_kw,
            "peak_penalty_rate_kw": self.peak_penalty_rate_kw,
            "reactive_power_tariff": self.reactive_power_tariff,
            "min_power_factor": self.min_power_factor,
            "reactive_allowance_pct": self.reactive_allowance_pct,
        }


@dataclass
class SupplierTariff:
    """
    Commercial energy retailer contract parameters.
    Implements unbundled 5-component commercial supplier invoice:
      Total = Commodity Base + Supplier Markup + Balancing Fee + Green Surcharge + Standing Base Fee
    Supports Fixed (Single/Dual TOU), Variable Monthly, Dynamic Spot, and Tranche/Click.
    """
    supplier_name: str = "Scholt Energy"
    supplier_category: str = SupplierCategory.B2B_PORTFOLIO.value
    pricing_mode: PricingMode = PricingMode.TRANCHE
    tariff_product_name: str = "Klik-Contract (Quartale Tranchen)"
    
    # 5. Standing administrative fee (Vastrecht levering: €20 to €80/month -> €240 to €960/yr)
    base_fee_annual: float = 600.00              # €/year (e.g. 12 x €50.00/month)
    
    # 1. Commodity Base Rates
    # Mode FIXED: flat rate per kWh
    fixed_rate_kwh: float = 0.1100               # €/kWh
    
    # Mode FIXED (Dual TOU): Separate Normaal (HT) and Dal (NT)
    is_dual_rate: bool = False
    fixed_rate_peak_kwh: float = 0.1180          # €/kWh Normaal / HT
    fixed_rate_offpeak_kwh: float = 0.1040       # €/kWh Dal / NT
    
    # 2. Supplier Retail Markup (Leveranciersopslag: €0.0050 to €0.0180/kWh)
    supplier_margin_kwh: float = 0.0075          # €/kWh
    
    # 3. Balancing Fee (Onbalanskosten: €0.0010 to €0.0030/kWh)
    balancing_fee_kwh: float = 0.0015            # €/kWh
    
    # 4. Green Certificates (GvO: €0.0020 to €0.0080/kWh)
    green_certificate_surcharge_kwh: float = 0.0 # €/kWh
    
    # Legacy procurement handling fee
    procurement_fee_kwh: float = 0.0             # €/kWh
    
    # Mode TRANCHE: Hedge blocks + residual spot settlement
    tranche_blocks: List[TrancheBlock] = field(default_factory=lambda: [
        TrancheBlock(label="Q1 (Jan-Mar)", months=[1, 2, 3], hedged_share_pct=75.0, click_price_kwh=0.1080),
        TrancheBlock(label="Q2 (Apr-Jun)", months=[4, 5, 6], hedged_share_pct=65.0, click_price_kwh=0.1050),
        TrancheBlock(label="Q3 (Jul-Sep)", months=[7, 8, 9], hedged_share_pct=60.0, click_price_kwh=0.1020),
        TrancheBlock(label="Q4 (Oct-Dec)", months=[10, 11, 12], hedged_share_pct=80.0, click_price_kwh=0.1120),
    ])

    # Mode VARIABLE: 12 monthly rates
    monthly_variable_rates: List[float] = field(
        default_factory=lambda: [0.120, 0.115, 0.110, 0.105, 0.100, 0.095, 0.095, 0.100, 0.105, 0.110, 0.115, 0.120]
    )
    
    # Mode DYNAMIC & Tranche residual: EPEX Spot NL Day-Ahead
    market_price_profile_id: str = "epex_nl_2025"
    spot_default_fallback_rate: float = 0.1100

    def to_dict(self) -> Dict[str, Any]:
        return {
            "supplier_name": self.supplier_name,
            "supplier_category": self.supplier_category,
            "pricing_mode": self.pricing_mode.value,
            "tariff_product_name": self.tariff_product_name,
            "base_fee_annual": self.base_fee_annual,
            "fixed_rate_kwh": self.fixed_rate_kwh,
            "is_dual_rate": self.is_dual_rate,
            "fixed_rate_peak_kwh": self.fixed_rate_peak_kwh,
            "fixed_rate_offpeak_kwh": self.fixed_rate_offpeak_kwh,
            "supplier_margin_kwh": self.supplier_margin_kwh,
            "balancing_fee_kwh": self.balancing_fee_kwh,
            "green_certificate_surcharge_kwh": self.green_certificate_surcharge_kwh,
            "procurement_fee_kwh": self.procurement_fee_kwh,
            "tranche_blocks": [tb.to_dict() for tb in self.tranche_blocks],
            "monthly_variable_rates": list(self.monthly_variable_rates),
            "market_price_profile_id": self.market_price_profile_id,
            "spot_default_fallback_rate": self.spot_default_fallback_rate,
        }


@dataclass
class TrafoRentalTariff:
    """
    Dedicated Transformer & MV Infrastructure Rental / Contracting.
    Covers Fudura, Kenter, Joulz, Alfen, or Customer-owned (CAPEX).
    Includes 24/7 service, NEN 3840 maintenance, and Installatieverantwoordelijke (IV).
    """
    provider_name: str = "Fudura B.V."
    station_type: str = "Kompaktstation 400 bis 630 kVA"
    is_rented: bool = True
    monthly_rental_fee: float = 354.00           # €/month (All-in: €4,248 / year)
    capex_equivalent: float = 65000.0            # Indicative purchase price for comparison
    includes_nen3840: bool = True
    description: str = "Kompaktstation 630 kVA inkl. Wartung und Betreiberhaftung NEN 3840"

    @property
    def annual_rental_fee(self) -> float:
        return (self.monthly_rental_fee * 12.0) if self.is_rented else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider_name": self.provider_name,
            "station_type": self.station_type,
            "is_rented": self.is_rented,
            "monthly_rental_fee": self.monthly_rental_fee,
            "annual_rental_fee": self.annual_rental_fee,
            "capex_equivalent": self.capex_equivalent,
            "includes_nen3840": self.includes_nen3840,
            "description": self.description,
        }


@dataclass
class MeteringTariff:
    """
    Certified Metering Company (Erkend Meetverantwoordelijke - EMV) telemetry.
    15-minute interval data (RLM) according to ACM Meetcode Elektriciteit.
    """
    meter_company_name: str = "Fudura B.V."
    service_package_name: str = "Mittelspannung MS <= 1 MW Telemetrie"
    annual_flat_fee: float = 840.00              # €/year (12 x €70.00/month)
    voltage_level: str = "MS"
    description: str = "Grootverbruik kwartierdata telemetrie en validatie"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "meter_company_name": self.meter_company_name,
            "service_package_name": self.service_package_name,
            "annual_flat_fee": self.annual_flat_fee,
            "voltage_level": self.voltage_level,
            "description": self.description,
        }


@dataclass
class LevyConfig:
    """
    Statutory energy taxation: Degressive 5-bracket Energiebelasting + Vermindering + BTW.
    Supports toggleable reference tax years (2025 vs. 2026).
    """
    tax_year: int = 2026                         # 2025 or 2026
    use_tiered_energy_tax: bool = True
    has_verblijfsfunctie: bool = True            # Official human occupancy function
    annual_tax_reduction: float = 519.80         # €/year (€524.95 for 2025, €519.80 for 2026)
    vat_rate_pct: float = 21.0                   # Statutory 21% BTW

    # Fallback rate if flat mode is requested
    statutory_levy_rate_kwh: float = 0.03735

    # 5-Bracket Degressive Tax Schedule
    # Zone 1 & 2 (0 - 10,000 kWh): 2025: 0.10154 | 2026: 0.09161
    # Zone 3 (10,001 - 50,000 kWh): 2025: 0.06937 | 2026: 0.06671
    # Zone 4 (50,001 - 10,000,000 kWh): 2025: 0.03868 | 2026: 0.03735
    # Zone 5 (> 10,000,000 kWh): 2025: 0.00321 | 2026: 0.00310
    tax_brackets: List[TaxBracket] = field(default_factory=lambda: [
        TaxBracket(zone_name="Zone 1 & 2 (0 bis 10.000 kWh)", lower_kwh=0.0, upper_kwh=10000.0, rate_kwh=0.09161),
        TaxBracket(zone_name="Zone 3 (10.001 bis 50.000 kWh)", lower_kwh=10000.0, upper_kwh=50000.0, rate_kwh=0.06671),
        TaxBracket(zone_name="Zone 4 (50.001 bis 10.000.000 kWh)", lower_kwh=50000.0, upper_kwh=10000000.0, rate_kwh=0.03735),
        TaxBracket(zone_name="Zone 5 (> 10.000.000 kWh)", lower_kwh=10000000.0, upper_kwh=float("inf"), rate_kwh=0.00310),
    ])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tax_year": self.tax_year,
            "use_tiered_energy_tax": self.use_tiered_energy_tax,
            "has_verblijfsfunctie": self.has_verblijfsfunctie,
            "annual_tax_reduction": self.annual_tax_reduction,
            "vat_rate_pct": self.vat_rate_pct,
            "statutory_levy_rate_kwh": self.statutory_levy_rate_kwh,
            "tax_brackets": [b.to_dict() for b in self.tax_brackets],
        }


@dataclass
class StatusQuoConfig2025:
    """Master configuration container for Status Quo Dutch Grootverbruik accounting."""
    stage: TariffStage = TariffStage.STAGE_1_DEFAULT
    dso: DSOTariff = field(default_factory=DSOTariff)
    supplier: SupplierTariff = field(default_factory=SupplierTariff)
    metering: MeteringTariff = field(default_factory=MeteringTariff)
    trafo: TrafoRentalTariff = field(default_factory=TrafoRentalTariff)
    levies: LevyConfig = field(default_factory=LevyConfig)
    
    # Financial lifecycle evaluation parameters
    discount_rate_pct: float = 5.0               # r: WACC discount rate (5.0%)
    energy_escalation_pct: float = 3.0           # g: Annual electricity price escalation (3.0%)
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
    fixed_connection_fee: float                  # Monthly connection fee (PAV_mnd)
    fixed_transport_fee: float                   # Monthly vastrecht
    cable_surcharge: float                       # Monthly cable fee
    volumetric_transport_fee: float              # kWh transport cost
    measured_peak_demand_kw: float               # P_peak,m
    billed_capacity_kw: float                    # Max(P_contract, P_peak_m) under ratchet
    contracted_capacity_fee: float               # GTV capacity fee
    peak_demand_fee: float                       # Measured monthly peak fee
    is_capacity_breached: bool                   # True if P_peak,m > P_contract
    excess_capacity_kw: float                    # Max(0, P_peak,m - P_contract)
    subtotal_dso_net: float                      # Total DSO net for this month
    penalty_fee: float = 0.0                     # Overload penalty fee if peak_penalty_rate_kw > 0

    @property
    def reactive_power_fee(self) -> float:
        """Reactive power fee (cos phi < 0.85), default 0.0."""
        return 0.0


@dataclass
class CommercialMonthlyResult:
    """Monthly commercial supplier 5-component invoice breakdown."""
    month_index: int
    commodity_cost: float                        # Wholesale base commodity (Fixed/Tranche/Spot)
    markup_cost: float                           # Leveranciersopslag (€/kWh)
    balancing_cost: float                        # Onbalanskosten (€/kWh)
    gvo_cost: float                              # Green certificates GvO (€/kWh)
    supplier_base_fee: float                     # Standing monthly fee (Vastrecht)
    supplier_energy_cost: float                  # Commodity + Markup + Balancing + GvO
    subtotal_supplier_net: float                 # supplier_energy_cost + supplier_base_fee
    hedged_kwh: float = 0.0                      # Hedged volume under tranche contract
    spot_kwh: float = 0.0                        # Residual volume settled at EPEX Spot

    @property
    def supplier_total_net(self) -> float:
        """Alias for subtotal_supplier_net."""
        return self.subtotal_supplier_net


@dataclass
class TrafoRentalMonthlyResult:
    """Monthly transformer & MV station rental/maintenance result."""
    month_index: int
    trafo_rental_fee: float                      # Monthly rental fee (€ 0.00 if CAPEX)
    is_rented: bool


@dataclass
class TaxMonthlyResult:
    """Monthly degressive Energiebelasting and tax reduction record."""
    month_index: int
    cumulative_kwh_start: float
    cumulative_kwh_end: float
    gross_energy_tax: float                      # Total Energiebelasting before reduction
    tax_reduction_credit: float                  # Monthly Vermindering credit
    net_energy_tax: float                        # Max(0, gross - reduction)


@dataclass
class StatusQuoMonthlyResult:
    """Consolidated monthly record containing all 4 market pillars + taxes."""
    month_index: int
    month_name: str
    consumption: MonthlyConsumptionRecord
    dso: DSOMonthlyResult
    supplier: CommercialMonthlyResult
    metering_fee: float
    trafo: TrafoRentalMonthlyResult
    tax: TaxMonthlyResult
    total_net: float
    vat_amount: float
    total_gross: float
    effective_rate_net_kwh: float

    @property
    def commercial(self) -> CommercialMonthlyResult:
        """Backward-compatible alias for supplier commercial result."""
        return self.supplier

    @property
    def metering_net(self) -> float:
        """Alias for monthly metering net fee."""
        return self.metering_fee

    @property
    def trafo_net(self) -> float:
        """Alias for transformer rental net fee."""
        return self.trafo.trafo_rental_fee

    @property
    def taxes_net(self) -> float:
        """Alias for net energy tax."""
        return self.tax.net_energy_tax


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
    
    # Pillar Subtotals (Net)
    total_dso_net: float
    total_supplier_net: float
    total_metering_net: float
    total_trafo_net: float
    total_taxes_net: float
    
    # Consolidated Totals
    total_status_quo_net: float = 0.0
    vat_rate_pct: float = 21.0
    total_vat_amount: float = 0.0
    total_status_quo_gross: float = 0.0
    
    # Economic KPIs
    blended_price_net_kwh: float = 0.0           # Total Net / Total kWh (€/kWh)
    blended_price_gross_kwh: float = 0.0         # Total Gross / Total kWh (€/kWh)
    
    # 15-year Lifecycle TCO
    tco_15_npv: float = 0.0
    tco_yearly_cashflows_net: List[float] = field(default_factory=list)
    tco_discounted_cashflows: List[float] = field(default_factory=list)

    # Audit points tracking
    has_capacity_breach: bool = False
    breached_months: List[int] = field(default_factory=list)

    @property
    def breach_months(self) -> List[int]:
        """Alias for breached_months."""
        return self.breached_months
