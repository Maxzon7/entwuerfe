"""
========================================================================================
Layer 7: Master Status Quo Consolidator (engine/status_quo_master.py)
Current Situation (Status Quo) Sandbox Engine
========================================================================================
Integrates and consolidates all 4 market pillars + statutory taxes:
  Pillar 1: Regulated Grid Operator (DSO 6 components including PAV and GTV)
  Pillar 2: Energy Retailer (Commercial Supplier 5-component invoice)
  Pillar 3: Certified Metering Company (EMV telemetry flat fee)
  Pillar 4: Transformer Station Rental / MV Contracting (NEN 3840)
  Statutory: Degressive 5-bracket Energiebelasting + Vermindering + 21% BTW

Computes 12-month consolidated series, annual KPIs, and 15-year TCO trajectory.
========================================================================================
"""

from typing import List, Dict, Any, Optional
import numpy as np

try:
    from .config_and_models import (
        LoadSeries2025,
        StatusQuoConfig2025,
        MonthlyConsumptionRecord,
        DSOMonthlyResult,
        CommercialMonthlyResult,
        TrafoRentalMonthlyResult,
        TaxMonthlyResult,
        StatusQuoMonthlyResult,
        StatusQuoAnnualResult,
    )
    from .consumption_pipeline import extract_monthly_consumption_records
    from .dso_accounting import calculate_dso_accounting_2025
    from .commercial_accounting import calculate_commercial_accounting
    from .trafo_accounting import calculate_trafo_rental_accounting
    from .tax_accounting import calculate_tax_accounting
except (ImportError, ValueError):
    from config_and_models import (
        LoadSeries2025,
        StatusQuoConfig2025,
        MonthlyConsumptionRecord,
        DSOMonthlyResult,
        CommercialMonthlyResult,
        TrafoRentalMonthlyResult,
        TaxMonthlyResult,
        StatusQuoMonthlyResult,
        StatusQuoAnnualResult,
    )
    from consumption_pipeline import extract_monthly_consumption_records
    from dso_accounting import calculate_dso_accounting_2025
    from commercial_accounting import calculate_commercial_accounting
    from trafo_accounting import calculate_trafo_rental_accounting
    from tax_accounting import calculate_tax_accounting

try:
    from current_model.models.financial import FinancialCostBreakdown
except ImportError:
    FinancialCostBreakdown = None


def calculate_status_quo_master(
    load: LoadSeries2025,
    config: StatusQuoConfig2025
) -> StatusQuoAnnualResult:
    """
    Executes the complete Dutch Grootverbruik status quo assessment across all 4 pillars.
    """
    # 1. Monthly consumption aggregation
    monthly_consumption = extract_monthly_consumption_records(load)
    total_consumption_kwh = float(load.total_energy_kwh)
    total_peak_tou_kwh = float(sum(r.peak_tou_kwh for r in monthly_consumption))
    total_offpeak_tou_kwh = float(sum(r.offpeak_tou_kwh for r in monthly_consumption))
    annual_peak_demand_kw = float(load.peak_demand_kw)

    # 2. Pillar 1: Regulated DSO accounting
    dso_monthly, dso_summary = calculate_dso_accounting_2025(
        monthly_consumption=monthly_consumption,
        dso_tariff=config.dso
    )

    # 3. Pillar 2: Commercial Supplier accounting (5-component invoice)
    supplier_monthly, supplier_summary = calculate_commercial_accounting(
        load=load,
        monthly_consumption=monthly_consumption,
        supplier_tariff=config.supplier
    )

    # 4. Pillar 3: Certified Metering EMV
    monthly_metering_fee = float(config.metering.annual_flat_fee) / 12.0

    # 5. Pillar 4: Transformer Station Rental / Contracting
    trafo_monthly, trafo_summary = calculate_trafo_rental_accounting(
        trafo_tariff=config.trafo
    )

    # 6. Statutory Taxes: Degressive 5-bracket Energiebelasting + Vermindering
    tax_monthly, tax_summary = calculate_tax_accounting(
        monthly_consumption=monthly_consumption,
        levy_config=config.levies
    )

    # 7. Consolidate monthly statements
    consolidated_monthly: List[StatusQuoMonthlyResult] = []
    vat_rate = float(config.levies.vat_rate_pct) / 100.0

    for m_idx in range(12):
        c_rec = monthly_consumption[m_idx]
        d_rec = dso_monthly[m_idx]
        s_rec = supplier_monthly[m_idx]
        tr_rec = trafo_monthly[m_idx]
        tx_rec = tax_monthly[m_idx]

        m_net = (
            d_rec.subtotal_dso_net +
            s_rec.subtotal_supplier_net +
            monthly_metering_fee +
            tr_rec.trafo_rental_fee +
            tx_rec.net_energy_tax
        )

        m_vat = m_net * vat_rate
        m_gross = m_net + m_vat
        eff_rate = (m_net / c_rec.total_kwh) if c_rec.total_kwh > 0 else 0.0

        consolidated_monthly.append(
            StatusQuoMonthlyResult(
                month_index=m_idx + 1,
                month_name=c_rec.month_name,
                consumption=c_rec,
                dso=d_rec,
                supplier=s_rec,
                metering_fee=round(monthly_metering_fee, 2),
                trafo=tr_rec,
                tax=tx_rec,
                total_net=round(m_net, 2),
                vat_amount=round(m_vat, 2),
                total_gross=round(m_gross, 2),
                effective_rate_net_kwh=round(eff_rate, 5)
            )
        )

    # 8. Annual aggregation across all 4 pillars
    total_dso_net = sum(r.dso.subtotal_dso_net for r in consolidated_monthly)
    total_supplier_net = sum(r.supplier.subtotal_supplier_net for r in consolidated_monthly)
    total_metering_net = monthly_metering_fee * 12.0
    total_trafo_net = sum(r.trafo.trafo_rental_fee for r in consolidated_monthly)
    total_taxes_net = sum(r.tax.net_energy_tax for r in consolidated_monthly)

    total_net_annual = (
        total_dso_net +
        total_supplier_net +
        total_metering_net +
        total_trafo_net +
        total_taxes_net
    )

    total_vat_annual = total_net_annual * vat_rate
    total_gross_annual = total_net_annual + total_vat_annual

    blended_net = (total_net_annual / total_consumption_kwh) if total_consumption_kwh > 0 else 0.0
    blended_gross = (total_gross_annual / total_consumption_kwh) if total_consumption_kwh > 0 else 0.0

    # 9. 15-Year Lifecycle TCO Trajectory
    r_wacc = float(config.discount_rate_pct) / 100.0
    g_esc = float(config.energy_escalation_pct) / 100.0
    horizon = int(config.evaluation_horizon_years)

    cashflows_net: List[float] = []
    discounted_cfs: List[float] = []
    npv_sum = 0.0

    for yr in range(1, horizon + 1):
        # Base annual spend escalates at rate g
        cf_nominal = total_net_annual * ((1.0 + g_esc) ** (yr - 1))
        # Discount factor at rate r
        discount_factor = 1.0 / ((1.0 + r_wacc) ** yr)
        pv = cf_nominal * discount_factor

        cashflows_net.append(round(cf_nominal, 2))
        discounted_cfs.append(round(pv, 2))
        npv_sum += pv

    return StatusQuoAnnualResult(
        config=config,
        total_consumption_kwh=round(total_consumption_kwh, 2),
        total_peak_tou_kwh=round(total_peak_tou_kwh, 2),
        total_offpeak_tou_kwh=round(total_offpeak_tou_kwh, 2),
        annual_peak_demand_kw=round(annual_peak_demand_kw, 2),
        monthly_records=consolidated_monthly,
        total_dso_net=round(total_dso_net, 2),
        total_supplier_net=round(total_supplier_net, 2),
        total_metering_net=round(total_metering_net, 2),
        total_trafo_net=round(total_trafo_net, 2),
        total_taxes_net=round(total_taxes_net, 2),
        total_status_quo_net=round(total_net_annual, 2),
        vat_rate_pct=config.levies.vat_rate_pct,
        total_vat_amount=round(total_vat_annual, 2),
        total_status_quo_gross=round(total_gross_annual, 2),
        blended_price_net_kwh=round(blended_net, 5),
        blended_price_gross_kwh=round(blended_gross, 5),
        tco_15_npv=round(npv_sum, 2),
        tco_yearly_cashflows_net=cashflows_net,
        tco_discounted_cashflows=discounted_cfs,
        has_capacity_breach=dso_summary.get("has_breaches", False),
        breached_months=dso_summary.get("breached_months", [])
    )


def convert_to_financial_cost_breakdown(
    result: StatusQuoAnnualResult,
    target_month: Optional[str] = None
) -> Any:
    """
    Adapter converting StatusQuoAnnualResult into a FinancialCostBreakdown dataclass.
    Enables instant reuse of project Plotly visualization figures without code changes.
    If target_month is provided (e.g. 'January'), yields a single-month breakdown.
    """
    is_filtered_month = (
        target_month is not None and
        target_month not in ("All Months", "All Months (Full Year Overview)", "All Months (Full Year 2025 Overview)")
    )

    if is_filtered_month and target_month:
        target_rec = next(
            (r for r in result.monthly_records if r.month_name.lower() in target_month.lower() or target_month.lower() in r.month_name.lower()),
            None
        )
        if target_rec is not None:
            r = target_rec
            gross = r.total_gross if r.total_gross > 0 else 1.0
            supp_base_mnd = round(float(result.config.supplier.base_fee_annual) / 12.0, 2)
            supp_energy_mnd = max(0.0, r.commercial.supplier_total_net - supp_base_mnd)
            base_fee_mnd = round(
                r.dso.fixed_connection_fee + r.dso.fixed_transport_fee +
                r.metering_net + r.trafo_net + supp_base_mnd, 2
            )

            line_items = [
                CostLineItem(
                    category="Energy (Active)",
                    description=f"Supplier Commodity ({r.month_name})",
                    basis_quantity=r.consumption.total_kwh,
                    unit="kWh",
                    unit_rate=round(supp_energy_mnd / r.consumption.total_kwh, 4) if r.consumption.total_kwh > 0 else 0.0,
                    cost_period=supp_energy_mnd,
                    cost_monthly=supp_energy_mnd,
                    share_pct=round((supp_energy_mnd / gross * 100.0), 1)
                ),
                CostLineItem(
                    category="Capacity (Contracted)",
                    description=f"DSO Contract Capacity GTV ({r.dso.billed_capacity_kw:.0f} kW)",
                    basis_quantity=r.dso.billed_capacity_kw,
                    unit="kW",
                    unit_rate=result.config.dso.rate_contracted_capacity,
                    cost_period=r.dso.contracted_capacity_fee,
                    cost_monthly=r.dso.contracted_capacity_fee,
                    share_pct=round((r.dso.contracted_capacity_fee / gross * 100.0), 1)
                ),
                CostLineItem(
                    category="Demand (Measured)",
                    description=f"DSO Monthly Peak ({r.dso.measured_peak_demand_kw:.1f} kW)",
                    basis_quantity=r.dso.measured_peak_demand_kw,
                    unit="kW",
                    unit_rate=result.config.dso.rate_peak_demand,
                    cost_period=r.dso.peak_demand_fee,
                    cost_monthly=r.dso.peak_demand_fee,
                    share_pct=round((r.dso.peak_demand_fee / gross * 100.0), 1)
                ),
                CostLineItem(
                    category="Base Fee",
                    description="Standing Network (PAV), Metering, Trafo & Supplier Fees",
                    basis_quantity=1.0,
                    unit="Month",
                    unit_rate=base_fee_mnd,
                    cost_period=base_fee_mnd,
                    cost_monthly=base_fee_mnd,
                    share_pct=round((base_fee_mnd / gross * 100.0), 1)
                ),
                CostLineItem(
                    category="Taxes & Levies",
                    description=f"Energiebelasting & VAT ({result.vat_rate_pct}%)",
                    basis_quantity=r.consumption.total_kwh,
                    unit="kWh",
                    unit_rate=round(r.taxes_net / r.consumption.total_kwh, 4) if r.consumption.total_kwh > 0 else 0.0,
                    cost_period=round(r.taxes_net + r.vat_amount, 2),
                    cost_monthly=round(r.taxes_net + r.vat_amount, 2),
                    share_pct=round(((r.taxes_net + r.vat_amount) / gross * 100.0), 1)
                ),
            ]
            if r.dso.volumetric_transport_fee > 0:
                line_items.append(
                    CostLineItem(
                        category="Network (Volume)",
                        description="DSO Volumetric kWh Transport Fee",
                        basis_quantity=r.consumption.total_kwh,
                        unit="kWh",
                        unit_rate=result.config.dso.rate_transport_peak_kwh,
                        cost_period=r.dso.volumetric_transport_fee,
                        cost_monthly=r.dso.volumetric_transport_fee,
                        share_pct=round((r.dso.volumetric_transport_fee / gross * 100.0), 1)
                    )
                )

            return FinancialCostBreakdown(
                currency="EUR",
                duration_days=float(r.consumption.days_count),
                total_consumption_kwh=r.consumption.total_kwh,
                peak_demand_kw=r.consumption.peak_demand_kw,
                contracted_capacity_kw=result.config.dso.contracted_capacity_kw,
                line_items=line_items,
                monthly_series=[],
                energy_cost_period=supp_energy_mnd,
                capacity_cost_period=r.dso.contracted_capacity_fee + r.dso.peak_demand_fee,
                network_cost_period=r.dso.volumetric_transport_fee,
                base_fee_period=base_fee_mnd,
                total_net_period=r.total_net,
                total_taxes_period=r.taxes_net + r.vat_amount,
                total_gross_period=r.total_gross,
                effective_kwh_price=r.effective_rate_net_kwh
            )

    # Full 12-month annual schedule
    monthly_series: List[MonthlyPaymentRecord] = []
    for r in result.monthly_records:
        supp_base_mnd = round(float(result.config.supplier.base_fee_annual) / 12.0, 2)
        supp_energy_mnd = max(0.0, r.commercial.supplier_total_net - supp_base_mnd)
        base_fee_mnd = round(
            r.dso.fixed_connection_fee + r.dso.fixed_transport_fee +
            r.metering_net + r.trafo_net + supp_base_mnd, 2
        )
        rec = MonthlyPaymentRecord(
            period_label=f"{r.month_name[:3]} 2025",
            days_count=r.consumption.days_count,
            energy_kwh=r.consumption.total_kwh,
            peak_demand_kw=r.consumption.peak_demand_kw,
            energy_cost_net=supp_energy_mnd,
            capacity_cost_net=r.dso.contracted_capacity_fee,
            penalty_cost_net=r.dso.peak_demand_fee,
            base_fee_net=base_fee_mnd,
            reactive_cost_net=r.dso.reactive_power_fee,
            total_net=r.total_net,
            taxes_and_levies=round(r.taxes_net + r.vat_amount, 2),
            total_gross=r.total_gross,
            effective_rate_kwh=r.total_gross / r.consumption.total_kwh if r.consumption.total_kwh > 0 else 0.0,
            network_cost_net=r.dso.volumetric_transport_fee
        )
        monthly_series.append(rec)

    annual_gross = result.total_status_quo_gross if result.total_status_quo_gross > 0 else 1.0
    supp_base_ann = float(result.config.supplier.base_fee_annual)
    supp_energy_ann = max(0.0, result.total_supplier_net - supp_base_ann)
    total_base_fees = round(
        (result.config.dso.fixed_connection_annual or 0.0) +
        (result.config.dso.fixed_transport_annual or 0.0) +
        result.total_metering_net +
        result.total_trafo_net +
        supp_base_ann, 2
    )

    line_items: List[CostLineItem] = [
        CostLineItem(
            category="Energy (Active)",
            description=f"Supplier Commodity ({result.config.supplier.supplier_name})",
            basis_quantity=result.total_consumption_kwh,
            unit="kWh",
            unit_rate=round(supp_energy_ann / result.total_consumption_kwh, 4) if result.total_consumption_kwh > 0 else 0.0,
            cost_period=supp_energy_ann,
            cost_monthly=round(supp_energy_ann / 12.0, 2),
            share_pct=round((supp_energy_ann / annual_gross * 100.0), 1)
        ),
        CostLineItem(
            category="Capacity (Contracted)",
            description=f"DSO Capacity & Peak ({result.config.dso.dso_name})",
            basis_quantity=result.config.dso.contracted_capacity_kw,
            unit="kW",
            unit_rate=result.config.dso.rate_contracted_capacity,
            cost_period=result.total_dso_net,
            cost_monthly=round(result.total_dso_net / 12.0, 2),
            share_pct=round((result.total_dso_net / annual_gross * 100.0), 1)
        ),
        CostLineItem(
            category="Base Fee",
            description="Standing DSO (PAV), Metering, Trafo & Retailer Fees",
            basis_quantity=12.0,
            unit="Month",
            unit_rate=round(total_base_fees / 12.0, 2),
            cost_period=total_base_fees,
            cost_monthly=round(total_base_fees / 12.0, 2),
            share_pct=round((total_base_fees / annual_gross * 100.0), 1)
        ),
        CostLineItem(
            category="Taxes & Levies",
            description=f"Energiebelasting & VAT ({result.vat_rate_pct}%)",
            basis_quantity=result.total_consumption_kwh,
            unit="kWh",
            unit_rate=round(result.total_taxes_net / result.total_consumption_kwh, 4) if result.total_consumption_kwh > 0 else 0.0,
            cost_period=round(result.total_taxes_net + result.total_vat_amount, 2),
            cost_monthly=round((result.total_taxes_net + result.total_vat_amount) / 12.0, 2),
            share_pct=round(((result.total_taxes_net + result.total_vat_amount) / annual_gross * 100.0), 1)
        )
    ]

    return FinancialCostBreakdown(
        currency="EUR",
        duration_days=365.0,
        total_consumption_kwh=result.total_consumption_kwh,
        peak_demand_kw=result.annual_peak_demand_kw,
        contracted_capacity_kw=result.config.dso.contracted_capacity_kw,
        line_items=line_items,
        monthly_series=monthly_series,
        energy_cost_period=supp_energy_ann,
        capacity_cost_period=result.total_dso_net,
        network_cost_period=0.0,
        base_fee_period=total_base_fees,
        total_net_period=result.total_status_quo_net,
        total_taxes_period=result.total_taxes_net + result.total_vat_amount,
        total_gross_period=result.total_status_quo_gross,
        effective_kwh_price=result.blended_price_net_kwh
    )

