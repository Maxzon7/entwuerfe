"""
========================================================================================
Layer 5: Master Consolidation & 15-Year TCO Evaluation (status_quo_master.py)
========================================================================================
Aggregates the unbundled accounting layers into the definitive Status Quo baseline:
  - Consolidates 12 calendar monthly records into StatusQuoMonthlyResult.
  - Computes annual Net Status Quo sum across all market entities.
  - Determines net and gross blended electricity prices (€/kWh).
  - Explicitly isolates statutory Value Added Tax (VAT / BTW 21%).
  - Dynamically computes the 15-year Total Cost of Ownership (TCO NPV) based on
    WACC discount rate (r) and annual energy escalation (g).
  - Emits a standard FinancialCostBreakdown adapter for native Plotly chart rendering.
Validates all Audit Point 4 criteria (4.1, 4.2, 4.3).
========================================================================================
"""

from typing import List, Dict, Any, Tuple, Optional
import numpy as np

try:
    from .config_and_models import (
        LoadSeries2025,
        StatusQuoConfig2025,
        MonthlyConsumptionRecord,
        DSOMonthlyResult,
        CommercialMonthlyResult,
        StatusQuoMonthlyResult,
        StatusQuoAnnualResult,
    )
    from .consumption_pipeline import extract_monthly_consumption_records
    from .dso_accounting import calculate_dso_accounting_2025
    from .commercial_accounting import calculate_commercial_accounting_2025
except (ImportError, ValueError):
    from config_and_models import (
        LoadSeries2025,
        StatusQuoConfig2025,
        MonthlyConsumptionRecord,
        DSOMonthlyResult,
        CommercialMonthlyResult,
        StatusQuoMonthlyResult,
        StatusQuoAnnualResult,
    )
    from consumption_pipeline import extract_monthly_consumption_records
    from dso_accounting import calculate_dso_accounting_2025
    from commercial_accounting import calculate_commercial_accounting_2025

# Compatibility imports for standard charts
try:
    from current_model.models.financial import (
        FinancialCostBreakdown,
        MonthlyPaymentRecord,
        CostLineItem,
    )
except ImportError:
    from models.financial import (
        FinancialCostBreakdown,
        MonthlyPaymentRecord,
        CostLineItem,
    )


def compute_tco_15_npv(
    annual_net_cost: float,
    horizon_years: int = 15,
    discount_rate_pct: float = 5.0,
    energy_escalation_pct: float = 3.0
) -> Tuple[float, List[float], List[float]]:
    """
    Evaluates Criterion 4.3 (15-Jahres-TCO NPV):
      TCO_15 = sum_{y=1}^{15} [ Cost_net * (1 + g)^(y-1) / (1 + r)^y ]
      
    Returns:
      Tuple of:
        - Discounted NPV total (float)
        - List of 15 undiscounted yearly cashflows
        - List of 15 discounted cashflows
    """
    r = discount_rate_pct / 100.0
    g = energy_escalation_pct / 100.0

    yearly_cashflows: List[float] = []
    discounted_cashflows: List[float] = []
    total_npv = 0.0

    for y in range(1, horizon_years + 1):
        # Inflated cost for year y
        cf_y = annual_net_cost * ((1.0 + g) ** (y - 1))
        # Discounted to present value (Year 0)
        df_y = cf_y / ((1.0 + r) ** y)
        
        yearly_cashflows.append(round(cf_y, 2))
        discounted_cashflows.append(round(df_y, 2))
        total_npv += df_y

    return round(total_npv, 2), yearly_cashflows, discounted_cashflows


def calculate_status_quo_master_2025(
    load: LoadSeries2025,
    config: StatusQuoConfig2025
) -> StatusQuoAnnualResult:
    """
    Executes the complete sequential 2025 Status Quo pipeline:
      Phase 1 & 2: Extraction of 12 monthly consumption records
      Phase 3: DSO accounting + Commercial accounting in parallel
      Phase 4: Monthly & annual consolidation, VAT isolation, and 15-year TCO
    """
    # Phase 2: Consumption records
    monthly_consumption = extract_monthly_consumption_records(load)

    # Phase 3: DSO accounting
    dso_results, dso_summary = calculate_dso_accounting_2025(
        load=load,
        monthly_consumption=monthly_consumption,
        dso_tariff=config.dso
    )

    # Phase 3: Commercial accounting
    comm_results, comm_summary = calculate_commercial_accounting_2025(
        load=load,
        monthly_consumption=monthly_consumption,
        supplier_tariff=config.supplier,
        metering_tariff=config.metering,
        levy_config=config.levies
    )

    # Phase 4: Master Monthly Consolidation (respecting Market Role Toggles)
    enable_p1 = getattr(config, "enable_pillar_1_supplier", True)
    enable_p2 = getattr(config, "enable_pillar_2_dso", True)
    enable_p3 = getattr(config, "enable_pillar_3_metering", True)
    enable_p4 = getattr(config, "enable_pillar_4_taxes", True)

    vat_rate = config.levies.vat_rate_pct / 100.0
    pct_levy_rate = float(getattr(config.levies, "percentage_levy_rate_pct", 0.0)) / 100.0
    vat_applies_to_levies = bool(getattr(config.levies, "vat_applies_to_levies", True))
    monthly_records: List[StatusQuoMonthlyResult] = []

    for c_rec, d_rec, m_rec in zip(monthly_consumption, dso_results, comm_results):
        if not enable_p2:
            d_rec.fixed_connection_fee = 0.0
            d_rec.fixed_transport_fee = 0.0
            d_rec.cable_surcharge = 0.0
            d_rec.volumetric_transport_fee = 0.0
            d_rec.volumetric_peak_fee = 0.0
            d_rec.volumetric_offpeak_fee = 0.0
            d_rec.volumetric_shoulder_fee = 0.0
            d_rec.contracted_capacity_fee = 0.0
            d_rec.peak_demand_fee = 0.0
            d_rec.excess_penalty_fee = 0.0
            d_rec.regulatory_adjustments_fee = 0.0
            d_rec.subtotal_dso_net = 0.0

        if not enable_p1:
            m_rec.supplier_base_fee = 0.0
            m_rec.supplier_energy_cost = 0.0

        if not enable_p3:
            m_rec.metering_fee = 0.0

        # Net electric concepts base (P1 + P2 + P3) for percentage levies and VAT
        m_electric_concepts_net = round(
            d_rec.subtotal_dso_net + m_rec.supplier_base_fee + m_rec.supplier_energy_cost + m_rec.metering_fee - m_rec.feed_in_credit,
            2
        )

        if enable_p4:
            pct_levy_m = round(m_electric_concepts_net * pct_levy_rate, 2) if pct_levy_rate > 0.0 else 0.0
            m_rec.statutory_levies = round(m_rec.statutory_levies + pct_levy_m, 2)
        else:
            m_rec.statutory_levies = 0.0

        m_rec.subtotal_commercial_net = round(
            m_rec.supplier_base_fee + m_rec.supplier_energy_cost + m_rec.metering_fee + m_rec.statutory_levies - m_rec.feed_in_credit,
            2
        )

        m_net = round(d_rec.subtotal_dso_net + m_rec.subtotal_commercial_net, 2)
        vat_base_m = m_net if vat_applies_to_levies else m_electric_concepts_net
        m_vat = round(vat_base_m * vat_rate, 2)
        m_gross = round(m_net + m_vat, 2)
        eff_rate_net = (m_net / c_rec.total_kwh) if c_rec.total_kwh > 0 else 0.0

        monthly_records.append(
            StatusQuoMonthlyResult(
                month_index=c_rec.month_index,
                month_name=c_rec.month_name,
                consumption=c_rec,
                dso=d_rec,
                commercial=m_rec,
                total_net=m_net,
                vat_amount=m_vat,
                total_gross=m_gross,
                effective_rate_net_kwh=round(eff_rate_net, 4)
            )
        )

    # Party Subtotals (Net) summed cleanly from monthly records
    total_dso_net = round(sum(r.dso.subtotal_dso_net for r in monthly_records), 2) if enable_p2 else 0.0
    total_supplier_net = round(sum(r.commercial.supplier_base_fee + r.commercial.supplier_energy_cost for r in monthly_records), 2) if enable_p1 else 0.0
    total_metering_net = round(sum(r.commercial.metering_fee for r in monthly_records), 2) if enable_p3 else 0.0
    total_levies_net = round(sum(r.commercial.statutory_levies for r in monthly_records), 2) if enable_p4 else 0.0
    total_feed_in_credit = 0.0

    # Criterion 4.1: Net Total
    total_status_quo_net = round(total_dso_net + total_supplier_net + total_metering_net + total_levies_net, 2)
    total_vat = round(sum(r.vat_amount for r in monthly_records), 2)
    total_status_quo_gross = round(total_status_quo_net + total_vat, 2)

    total_kwh = load.total_energy_kwh
    total_ht_kwh = sum(r.consumption.peak_tou_kwh for r in monthly_records)
    total_nt_kwh = sum(r.consumption.offpeak_tou_kwh for r in monthly_records)

    # Criterion 4.2: Blended price (€/kWh)
    blended_net = (total_status_quo_net / total_kwh) if total_kwh > 0 else 0.0
    blended_gross = (total_status_quo_gross / total_kwh) if total_kwh > 0 else 0.0

    # Criterion 4.3: 15-year TCO NPV
    tco_npv, yearly_cf, discounted_cf = compute_tco_15_npv(
        annual_net_cost=total_status_quo_net,
        horizon_years=config.evaluation_horizon_years,
        discount_rate_pct=config.discount_rate_pct,
        energy_escalation_pct=config.energy_escalation_pct
    )

    breach_months = [r.month_index for r in monthly_records if r.dso.is_capacity_breached]

    return StatusQuoAnnualResult(
        config=config,
        total_consumption_kwh=round(total_kwh, 2),
        total_peak_tou_kwh=round(total_ht_kwh, 2),
        total_offpeak_tou_kwh=round(total_nt_kwh, 2),
        annual_peak_demand_kw=round(load.peak_demand_kw, 2),
        monthly_records=monthly_records,
        total_dso_net=round(total_dso_net, 2),
        total_supplier_net=round(total_supplier_net, 2),
        total_metering_net=round(total_metering_net, 2),
        total_levies_net=round(total_levies_net, 2),
        total_feed_in_credit=0.0,
        total_status_quo_net=round(total_status_quo_net, 2),
        vat_rate_pct=config.levies.vat_rate_pct,
        total_vat_amount=round(total_vat, 2),
        total_status_quo_gross=round(total_status_quo_gross, 2),
        blended_price_net_kwh=round(blended_net, 4),
        blended_price_gross_kwh=round(blended_gross, 4),
        tco_15_npv=round(tco_npv, 2),
        tco_yearly_cashflows_net=yearly_cf,
        tco_discounted_cashflows=discounted_cf,
        has_capacity_breach=(len(breach_months) > 0),
        breach_months=breach_months
    )


def convert_to_financial_cost_breakdown(
    result: StatusQuoAnnualResult,
    target_month: Optional[str] = None,
) -> FinancialCostBreakdown:
    """
    Adapter converting StatusQuoAnnualResult into a FinancialCostBreakdown dataclass.
    Enables instant reuse of project Plotly visualization figures without code changes.
    If target_month is provided (e.g. 'January'), yields a single-month breakdown.
    """
    if target_month and target_month not in ("All Months", "All Months (Full Year Overview)", "All Months (Full Year 2025 Overview)"):
        # Match by month name or prefix
        target_rec = next((r for r in result.monthly_records if r.month_name.lower() in target_month.lower() or target_month.lower() in r.month_name.lower()), None)
        if target_rec is not None:
            r = target_rec
            gross = r.total_gross if r.total_gross > 0 else 1.0
            line_items = [
                CostLineItem(
                    category="Energy (Active)",
                    description=f"Supplier Commodity ({r.month_name})",
                    basis_quantity=r.consumption.total_kwh,
                    unit="kWh",
                    unit_rate=round(r.commercial.supplier_energy_cost / r.consumption.total_kwh, 4) if r.consumption.total_kwh > 0 else 0.0,
                    cost_period=r.commercial.supplier_energy_cost,
                    cost_monthly=r.commercial.supplier_energy_cost,
                    share_pct=round((r.commercial.supplier_energy_cost / gross * 100.0), 1)
                ),
                CostLineItem(
                    category="Capacity (Contracted)",
                    description=f"DSO Contract Capacity ({r.dso.billed_capacity_kw:.0f} kW)",
                    basis_quantity=r.dso.billed_capacity_kw,
                    unit="kW",
                    unit_rate=result.config.dso.rate_contracted_capacity,
                    cost_period=r.dso.contracted_capacity_fee,
                    cost_monthly=r.dso.contracted_capacity_fee,
                    share_pct=round((r.dso.contracted_capacity_fee / gross * 100.0), 1)
                ),
                CostLineItem(
                    category="Demand (Measured)",
                    description=f"DSO Peak Demand Fee ({r.dso.measured_peak_demand_kw:.1f} kW)",
                    basis_quantity=r.dso.measured_peak_demand_kw,
                    unit="kW",
                    unit_rate=result.config.dso.rate_peak_demand,
                    cost_period=r.dso.peak_demand_fee,
                    cost_monthly=r.dso.peak_demand_fee,
                    share_pct=round((r.dso.peak_demand_fee / gross * 100.0), 1)
                ),
                CostLineItem(
                    category="Base Fee",
                    description="Standing Network, Metering & Supplier Fees",
                    basis_quantity=1.0,
                    unit="Month",
                    unit_rate=round(r.dso.fixed_connection_fee + r.dso.fixed_transport_fee + r.commercial.metering_fee + r.commercial.supplier_base_fee, 2),
                    cost_period=round(r.dso.fixed_connection_fee + r.dso.fixed_transport_fee + r.commercial.metering_fee + r.commercial.supplier_base_fee, 2),
                    cost_monthly=round(r.dso.fixed_connection_fee + r.dso.fixed_transport_fee + r.commercial.metering_fee + r.commercial.supplier_base_fee, 2),
                    share_pct=round(((r.dso.fixed_connection_fee + r.dso.fixed_transport_fee + r.commercial.metering_fee + r.commercial.supplier_base_fee) / gross * 100.0), 1)
                ),
                CostLineItem(
                    category="Taxes & Levies",
                    description=f"Statutory Levies & VAT ({result.vat_rate_pct}%)",
                    basis_quantity=r.consumption.total_kwh,
                    unit="kWh",
                    unit_rate=result.config.levies.statutory_levy_rate_kwh,
                    cost_period=round(r.commercial.statutory_levies + r.vat_amount, 2),
                    cost_monthly=round(r.commercial.statutory_levies + r.vat_amount, 2),
                    share_pct=round(((r.commercial.statutory_levies + r.vat_amount) / gross * 100.0), 1)
                ),
            ]
            if r.dso.volumetric_transport_fee > 0:
                line_items.append(
                    CostLineItem(
                        category="Network (Volume)",
                        description="DSO kWh Volumetric Transport Fee",
                        basis_quantity=r.consumption.total_kwh,
                        unit="kWh",
                        unit_rate=result.config.dso.rate_transport_peak_kwh,
                        cost_period=r.dso.volumetric_transport_fee,
                        cost_monthly=r.dso.volumetric_transport_fee,
                        share_pct=round((r.dso.volumetric_transport_fee / gross * 100.0), 1)
                    )
                )

            return FinancialCostBreakdown(
                currency=getattr(result.config, "currency_code", "EUR"),
                duration_days=float(r.consumption.days_count),
                total_consumption_kwh=r.consumption.total_kwh,
                peak_demand_kw=r.consumption.peak_demand_kw,
                contracted_capacity_kw=result.config.dso.contracted_capacity_kw,
                line_items=line_items,
                monthly_series=[],
                energy_cost_period=r.commercial.supplier_energy_cost,
                capacity_cost_period=r.dso.contracted_capacity_fee + r.dso.peak_demand_fee + getattr(r.dso, "excess_penalty_fee", 0.0),
                network_cost_period=r.dso.volumetric_transport_fee,
                base_fee_period=r.dso.fixed_connection_fee + r.dso.fixed_transport_fee + r.commercial.metering_fee + r.commercial.supplier_base_fee,
                total_net_period=r.total_net,
                total_taxes_period=r.commercial.statutory_levies + r.vat_amount,
                total_gross_period=r.total_gross,
                effective_kwh_price=r.effective_rate_net_kwh
            )

    monthly_series: List[MonthlyPaymentRecord] = []
    
    for r in result.monthly_records:
        rec = MonthlyPaymentRecord(
            period_label=f"{r.month_name[:3]} 2025",
            days_count=r.consumption.days_count,
            energy_kwh=r.consumption.total_kwh,
            peak_demand_kw=r.consumption.peak_demand_kw,
            energy_cost_net=r.commercial.supplier_energy_cost,
            capacity_cost_net=r.dso.contracted_capacity_fee,
            penalty_cost_net=r.dso.peak_demand_fee + getattr(r.dso, "excess_penalty_fee", 0.0),
            base_fee_net=r.dso.fixed_connection_fee + r.dso.fixed_transport_fee + r.commercial.metering_fee + r.commercial.supplier_base_fee,
            reactive_cost_net=0.0,
            total_net=r.total_net,
            taxes_and_levies=r.commercial.statutory_levies + r.vat_amount,
            total_gross=r.total_gross,
            effective_rate_kwh=r.total_gross / r.consumption.total_kwh if r.consumption.total_kwh > 0 else 0.0,
            network_cost_net=r.dso.volumetric_transport_fee
        )
        monthly_series.append(rec)

    gross_denom = result.total_status_quo_gross if result.total_status_quo_gross > 0 else 1.0
    # Line items
    line_items: List[CostLineItem] = [
        CostLineItem(
            category="Energy (Active)",
            description=f"Supplier Commodity ({result.config.supplier.supplier_name} - {result.config.supplier.pricing_mode.value.upper()})",
            basis_quantity=result.total_consumption_kwh,
            unit="kWh",
            unit_rate=round(result.total_supplier_net / result.total_consumption_kwh, 4) if result.total_consumption_kwh > 0 else 0.0,
            cost_period=result.total_supplier_net,
            cost_monthly=round(result.total_supplier_net / 12.0, 2),
            share_pct=round((result.total_supplier_net / gross_denom * 100.0), 1)
        ),
        CostLineItem(
            category="Capacity (Contracted)",
            description=f"DSO Capacity & Peak ({result.config.dso.dso_name})",
            basis_quantity=result.config.dso.contracted_capacity_kw,
            unit="kW",
            unit_rate=result.config.dso.rate_contracted_capacity,
            cost_period=result.total_dso_net,
            cost_monthly=round(result.total_dso_net / 12.0, 2),
            share_pct=round((result.total_dso_net / gross_denom * 100.0), 1)
        ),
        CostLineItem(
            category="Base Fee",
            description=f"Interval Telemetry ({result.config.metering.meter_company_name})",
            basis_quantity=12.0,
            unit="Month",
            unit_rate=round(result.total_metering_net / 12.0, 2),
            cost_period=result.total_metering_net,
            cost_monthly=round(result.total_metering_net / 12.0, 2),
            share_pct=round((result.total_metering_net / gross_denom * 100.0), 1)
        ),
        CostLineItem(
            category="Taxes & Levies",
            description=f"Statutory Levies & VAT ({result.vat_rate_pct}%)",
            basis_quantity=result.total_consumption_kwh,
            unit="kWh",
            unit_rate=result.config.levies.statutory_levy_rate_kwh,
            cost_period=round(result.total_levies_net + result.total_vat_amount, 2),
            cost_monthly=round((result.total_levies_net + result.total_vat_amount) / 12.0, 2),
            share_pct=round(((result.total_levies_net + result.total_vat_amount) / gross_denom * 100.0), 1)
        ),
    ]

    return FinancialCostBreakdown(
        currency=getattr(result.config, "currency_code", "EUR"),
        duration_days=365.0,
        total_consumption_kwh=result.total_consumption_kwh,
        peak_demand_kw=result.annual_peak_demand_kw,
        contracted_capacity_kw=result.config.dso.contracted_capacity_kw,
        line_items=line_items,
        monthly_series=monthly_series,
        energy_cost_period=result.total_supplier_net,
        capacity_cost_period=result.total_dso_net,
        network_cost_period=0.0,
        base_fee_period=result.total_metering_net,
        total_net_period=result.total_status_quo_net,
        total_taxes_period=result.total_vat_amount + result.total_levies_net,
        total_gross_period=result.total_status_quo_gross,
        effective_kwh_price=result.blended_price_gross_kwh
    )


def evaluate_master_audit(
    result: StatusQuoAnnualResult
) -> Dict[str, Any]:
    """
    Validates Audit Point 4 (Prüfpunkt 4: Gesamtrechnung und Wirtschaftlichkeit):
      - Criterion 4.1: Net annual sum == DSO + Supplier + Metering + Levies.
      - Criterion 4.2: Blended price == Net total / E_total (€/kWh).
      - Criterion 4.3: 15-year TCO NPV equals the discounted sum over 15 years with g and r.
    """
    # 4.1: Net Sum
    expected_net = (
        result.total_dso_net +
        result.total_supplier_net +
        result.total_metering_net +
        result.total_levies_net
    )
    c4_1_pass = (abs(expected_net - result.total_status_quo_net) < 0.20)

    # 4.2: Blended Price
    expected_blended = (
        (result.total_status_quo_net / result.total_consumption_kwh)
        if result.total_consumption_kwh > 0 else 0.0
    )
    c4_2_pass = (abs(expected_blended - result.blended_price_net_kwh) < 1e-3)

    # 4.3: TCO NPV
    r = result.config.discount_rate_pct / 100.0
    g = result.config.energy_escalation_pct / 100.0
    expected_tco = sum(
        (result.total_status_quo_net * ((1.0 + g) ** (y - 1))) / ((1.0 + r) ** y)
        for y in range(1, result.config.evaluation_horizon_years + 1)
    )
    c4_3_pass = (abs(expected_tco - result.tco_15_npv) < 1.00)

    all_passed = (c4_1_pass and c4_2_pass and c4_3_pass)

    return {
        "audit_point": 4,
        "title": "Audit Point 4: Master Consolidation & 15-Year TCO Verification",
        "passed": all_passed,
        "criteria": {
            "4.1_net_annual_sum": {
                "passed": c4_1_pass,
                "expected_net": round(expected_net, 2),
                "actual_net": round(result.total_status_quo_net, 2),
                "diff": round(abs(expected_net - result.total_status_quo_net), 4)
            },
            "4.2_blended_net_price": {
                "passed": c4_2_pass,
                "expected_blended_eur_kwh": round(expected_blended, 4),
                "actual_blended_eur_kwh": round(result.blended_price_net_kwh, 4)
            },
            "4.3_tco_15_npv": {
                "passed": c4_3_pass,
                "expected_tco_npv": round(expected_tco, 2),
                "actual_tco_npv": round(result.tco_15_npv, 2),
                "diff": round(abs(expected_tco - result.tco_15_npv), 2)
            }
        }
    }
