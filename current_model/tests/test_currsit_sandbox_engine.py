"""
========================================================================================
Automated Verification Suite: Dutch Grootverbruik Sandbox Engine
tests/test_currsit_sandbox_engine.py
========================================================================================
Validates that the isolated sandbox engine reproduces the exact mathematical benchmarks
and regulatory mechanics of the authoritative Dutch commercial market reference:
  1. Benchmark Profile A: Commercial SME on Low Voltage (AC4b, 147 kW, 360 MWh) -> € 76,111.10 Net
  2. Benchmark Profile B: MV Industrial Facility (AC5a, 536 kW, 1.2 GWh) -> € 246,620.56 Net
  3. 12-Month Ratchet Exceedance Lock
  4. Tranche / Click Hybrid Hedge Mathematical Limits (100% vs 0%)
  5. Voltage Transition Advisory Tipping Point (AC4b vs AC5a)
========================================================================================
"""

import pytest
import numpy as np

from current_model.ui_sandbox.Currentsituation_sandbox.engine import (
    StatusQuoConfig2025,
    PricingMode,
    SupplierCategory,
    DSOTariff,
    SupplierTariff,
    TrafoRentalTariff,
    MeteringTariff,
    LevyConfig,
    TrancheBlock,
    synthesize_profile_a_360mwh,
    synthesize_profile_b_1200mwh,
    synthesize_benchmark_load_profile_2025,
    calculate_status_quo_master,
    compare_procurement_routes,
    evaluate_voltage_transition_advisor,
    get_dso_tariff_from_catalog,
    get_supplier_tariff_from_catalog,
    get_trafo_tariff_from_catalog,
    get_metering_tariff_from_catalog,
    get_default_levy_config,
)


def test_benchmark_profile_a_commercial_sme():
    """
    Validates Benchmark Profile A:
      - Low Voltage connection AC4b (Liander MS/LS DSO Trafo)
      - P_contract = 147 kW, P_peak = 140 kW, E_annual = 360,000 kWh (30,000 kWh/mo)
      - Supplier Fixed Rate = € 0.1100 / kWh, Base fee = € 30 / mo (€ 360 / yr)
      - Taxes = 2026 5-bracket schedule with Verblijfsfunctie rebate (€ 519.80 / yr)
      - Metering = LS Telemetry € 50 / mo (€ 600 / yr)
      - Trafo = € 0 / yr (DSO owned)
    Target Net Spend: € 76,111.10 / yr (tolerance ± € 1.00)
    """
    load_a = synthesize_profile_a_360mwh()
    assert abs(load_a.total_energy_kwh - 360000.0) < 1e-2
    assert abs(load_a.peak_demand_kw - 140.0) < 1e-2

    dso_a = get_dso_tariff_from_catalog(
        dso_company="Liander N.V.",
        tier_name="AC4b: MS/LS (Trafo DSO > 50 bis 147 kW)",
        contracted_capacity_kw=147.0
    )

    supplier_a = SupplierTariff(
        supplier_name="Custom Benchmark Supplier",
        supplier_category=SupplierCategory.MAJOR_UTILITY.value,
        pricing_mode=PricingMode.FIXED,
        tariff_product_name="Benchmark Fixed 0.110",
        base_fee_annual=360.00,
        fixed_rate_kwh=0.1100,
        is_dual_rate=False,
        supplier_margin_kwh=0.0,
        balancing_fee_kwh=0.0,
        green_certificate_surcharge_kwh=0.0
    )

    metering_a = MeteringTariff(
        meter_company_name="Standard Meetbedrijf",
        service_package_name="LS Telemetrie",
        annual_flat_fee=600.00,
        voltage_level="LS"
    )

    trafo_a = TrafoRentalTariff(
        provider_name="None / DSO Trafo",
        station_type="DSO MS/LS Trafo",
        is_rented=False,
        monthly_rental_fee=0.0
    )

    levies_a = get_default_levy_config(tax_year=2026, has_verblijfsfunctie=True)

    config_a = StatusQuoConfig2025(
        dso=dso_a,
        supplier=supplier_a,
        metering=metering_a,
        trafo=trafo_a,
        levies=levies_a
    )

    result_a = calculate_status_quo_master(load=load_a, config=config_a)

    # 1. DSO verification
    # PAV: 283.68, Vastrecht: 441.00, GTV: 6450.42, Peak: 5812.80, Transport: 7920.00 -> Sum = 20907.90
    assert abs(result_a.total_dso_net - 20907.90) < 0.50

    # 2. Supplier verification
    # Energy: 360000 * 0.110 = 39600.00 + Base 360.00 -> Sum = 39960.00
    assert abs(result_a.total_supplier_net - 39960.00) < 0.50

    # 3. Tax verification (2026)
    # Zone 1+2 (10k * 0.09161) = 916.10
    # Zone 3 (40k * 0.06671) = 2668.40
    # Zone 4 (310k * 0.03735) = 11578.50
    # Gross = 15163.00, Rebate = -519.80 -> Net Tax = 14643.20
    assert abs(result_a.total_taxes_net - 14643.20) < 0.50

    # 4. Metering & Trafo verification
    assert abs(result_a.total_metering_net - 600.00) < 1e-2
    assert abs(result_a.total_trafo_net - 0.0) < 1e-2

    # 5. Consolidated Total Net Spend
    # 20907.90 + 39960.00 + 14643.20 + 600.00 = 76111.10
    assert abs(result_a.total_status_quo_net - 76111.10) < 1.00

    # 6. BTW & Gross Total
    # BTW 21% = 15983.33, Gross = 92094.43
    assert abs(result_a.total_vat_amount - 15983.33) < 1.00
    assert abs(result_a.total_status_quo_gross - 92094.43) < 1.00
    assert abs(result_a.blended_price_net_kwh - 0.21142) < 1e-4


def test_benchmark_profile_b_mv_industrial():
    """
    Validates Benchmark Profile B:
      - Medium Voltage connection AC5a (Liander MS eigene Station)
      - P_contract = 536 kW, P_peak = 500 kW, E_annual = 1,200,000 kWh (100,000 kWh/mo)
      - Supplier Fixed Rate = € 0.1100 / kWh, Base fee = € 50 / mo (€ 600 / yr)
      - Taxes = 2026 5-bracket schedule with Verblijfsfunctie rebate (€ 519.80 / yr)
      - Metering = MS Telemetry € 70 / mo (€ 840 / yr)
      - Trafo = Rented 630 kVA Kompaktstation € 354 / mo (€ 4,248 / yr)
    Target Net Spend: € 246,620.56 / yr (tolerance ± € 1.00)
    """
    load_b = synthesize_profile_b_1200mwh()
    assert abs(load_b.total_energy_kwh - 1200000.0) < 1e-2
    assert abs(load_b.peak_demand_kw - 500.0) < 1e-2

    dso_b = get_dso_tariff_from_catalog(
        dso_company="Liander N.V.",
        tier_name="AC5a: MS eigene Station (> 136 bis 536 kW)",
        contracted_capacity_kw=536.0
    )

    supplier_b = SupplierTariff(
        supplier_name="Custom Industrial Supplier",
        supplier_category=SupplierCategory.B2B_PORTFOLIO.value,
        pricing_mode=PricingMode.FIXED,
        tariff_product_name="Industrial Fixed 0.110",
        base_fee_annual=600.00,
        fixed_rate_kwh=0.1100,
        is_dual_rate=False,
        supplier_margin_kwh=0.0,
        balancing_fee_kwh=0.0,
        green_certificate_surcharge_kwh=0.0
    )

    metering_b = MeteringTariff(
        meter_company_name="Fudura B.V.",
        service_package_name="MS <= 1 MW Telemetrie",
        annual_flat_fee=840.00,
        voltage_level="MS"
    )

    trafo_b = TrafoRentalTariff(
        provider_name="Fudura B.V.",
        station_type="Kompaktstation 400 bis 630 kVA",
        is_rented=True,
        monthly_rental_fee=354.00
    )

    levies_b = get_default_levy_config(tax_year=2026, has_verblijfsfunctie=True)

    config_b = StatusQuoConfig2025(
        dso=dso_b,
        supplier=supplier_b,
        metering=metering_b,
        trafo=trafo_b,
        levies=levies_b
    )

    result_b = calculate_status_quo_master(load=load_b, config=config_b)

    # 1. DSO verification
    # PAV: 1013.88, Vastrecht: 441.00, GTV: 14300.27 (or 14300.48), Peak: 20760.00, Transport: 26400.00
    # Sum = 62915.15 to 62915.36
    assert abs(result_b.total_dso_net - 62915.36) < 1.00

    # 2. Supplier verification
    # Energy: 1200000 * 0.110 = 132000.00 + Base 600.00 -> Sum = 132600.00
    assert abs(result_b.total_supplier_net - 132600.00) < 0.50

    # 3. Tax verification (2026)
    # First 50k: 3584.50
    # Zone 4 (1.15M * 0.03735): 42952.50
    # Gross = 46537.00, Rebate = -519.80 -> Net Tax = 46017.20
    assert abs(result_b.total_taxes_net - 46017.20) < 0.50

    # 4. Metering & Trafo verification
    # Metering: 840.00, Trafo: 12 * 354 = 4248.00 -> Sum = 5088.00
    assert abs(result_b.total_metering_net - 840.00) < 1e-2
    assert abs(result_b.total_trafo_net - 4248.00) < 1e-2

    # 5. Consolidated Total Net Spend
    # 62915.36 + 132600.00 + 46017.20 + 840.00 + 4248.00 = 246620.56
    assert abs(result_b.total_status_quo_net - 246620.56) < 1.00

    # 6. BTW & Gross Total
    # BTW 21% = 51790.32, Gross = 298410.88
    assert abs(result_b.total_vat_amount - 51790.32) < 1.00
    assert abs(result_b.total_status_quo_gross - 298410.88) < 1.00
    assert abs(result_b.blended_price_net_kwh - 0.20552) < 1e-4


def test_12_month_ratchet_lock():
    """
    Verifies that an exceedance in an early month permanently locks contracted
    capacity for the remainder of the 12-month period.
    """
    load_bench = synthesize_benchmark_load_profile_2025(nominal_peak_kw=250.0)

    # Set contracted capacity below peak (e.g. 200 kW)
    dso_tariff = get_dso_tariff_from_catalog(contracted_capacity_kw=200.0, ratchet_12_months=True)
    supplier_tariff = get_supplier_tariff_from_catalog()
    metering_tariff = get_metering_tariff_from_catalog()
    trafo_tariff = get_trafo_tariff_from_catalog()
    levies = get_default_levy_config()

    config = StatusQuoConfig2025(
        dso=dso_tariff,
        supplier=supplier_tariff,
        metering=metering_tariff,
        trafo=trafo_tariff,
        levies=levies
    )

    result = calculate_status_quo_master(load=load_bench, config=config)

    # Breach should be recorded
    assert result.has_capacity_breach is True
    # Final billed capacity should match or exceed nominal peak (250 kW)
    assert result.monthly_records[-1].dso.billed_capacity_kw >= 249.0


def test_tranche_hedge_limits():
    """
    Verifies the mathematical boundary limits of the Tranche contract engine:
      - 100% hedge in all quarters must equal a fixed price contract at click rate.
    """
    load_bench = synthesize_benchmark_load_profile_2025(nominal_peak_kw=200.0)

    # 1. 100% hedged tranche contract at 0.1100 €/kWh
    tranche_blocks_100 = [
        TrancheBlock(label="All Year", months=list(range(1, 13)), hedged_share_pct=100.0, click_price_kwh=0.1100)
    ]
    supp_tranche = SupplierTariff(
        supplier_name="Test Supplier",
        pricing_mode=PricingMode.TRANCHE,
        tranche_blocks=tranche_blocks_100,
        supplier_margin_kwh=0.0075,
        balancing_fee_kwh=0.0015,
        base_fee_annual=360.0
    )

    # 2. Fixed contract at 0.1100 €/kWh
    supp_fixed = SupplierTariff(
        supplier_name="Test Supplier",
        pricing_mode=PricingMode.FIXED,
        fixed_rate_kwh=0.1100,
        supplier_margin_kwh=0.0075,
        balancing_fee_kwh=0.0015,
        base_fee_annual=360.0
    )

    cfg_tranche = StatusQuoConfig2025(supplier=supp_tranche)
    cfg_fixed = StatusQuoConfig2025(supplier=supp_fixed)

    res_tranche = calculate_status_quo_master(load_bench, cfg_tranche)
    res_fixed = calculate_status_quo_master(load_bench, cfg_fixed)

    # 100% hedge must match fixed commodity cost exactly
    assert abs(res_tranche.total_supplier_net - res_fixed.total_supplier_net) < 1e-2


def test_voltage_transition_advisor_threshold():
    """
    Verifies that the Voltage Transition Advisor identifies the tipping point:
      - Above ~200 kW, transition to AC5a (with trafo rent) is beneficial.
      - At 100 kW, remaining on AC4b is recommended.
    """
    load_large = synthesize_benchmark_load_profile_2025(nominal_peak_kw=500.0)
    eval_large = evaluate_voltage_transition_advisor(load_large, contracted_kw=500.0)
    assert eval_large["is_beneficial"] is True
    assert eval_large["net_annual_benefit"] > 0.0

    load_small = synthesize_benchmark_load_profile_2025(nominal_peak_kw=100.0)
    eval_small = evaluate_voltage_transition_advisor(load_small, contracted_kw=100.0)
    assert eval_small["is_beneficial"] is False
    assert eval_small["net_annual_benefit"] < 0.0


def test_convert_to_financial_cost_breakdown_and_property_aliases():
    """
    Verifies that convert_to_financial_cost_breakdown works for both annual and single-month modes,
    and that all backward-compatible property accessors (commercial, metering_net, trafo_net, taxes_net,
    supplier_total_net, breach_months) function without AttributeError.
    """
    from current_model.ui_sandbox.Currentsituation_sandbox.engine import (
        convert_to_financial_cost_breakdown,
    )

    load = synthesize_profile_a_360mwh()
    config = StatusQuoConfig2025()
    result = calculate_status_quo_master(load=load, config=config)

    # 1. Full-Year Breakdown
    annual_breakdown = convert_to_financial_cost_breakdown(result, target_month=None)
    assert annual_breakdown is not None
    assert annual_breakdown.duration_days == 365.0
    assert len(annual_breakdown.monthly_series) == 12
    assert annual_breakdown.total_net_period > 0.0

    # 2. Single-Month Filtered Breakdown (e.g., January)
    jan_breakdown = convert_to_financial_cost_breakdown(result, target_month="January")
    assert jan_breakdown is not None
    assert jan_breakdown.duration_days == 31.0
    assert jan_breakdown.total_net_period > 0.0

    # 3. Test backward-compatible property accessors on StatusQuoMonthlyResult
    first_month = result.monthly_records[0]
    assert first_month.commercial is first_month.supplier
    assert first_month.metering_net == first_month.metering_fee
    assert first_month.trafo_net == first_month.trafo.trafo_rental_fee
    assert first_month.taxes_net == first_month.tax.net_energy_tax
    assert first_month.commercial.supplier_total_net == first_month.supplier.subtotal_supplier_net

    # 4. Test breach_months property on StatusQuoAnnualResult
    assert result.breach_months == result.breached_months
