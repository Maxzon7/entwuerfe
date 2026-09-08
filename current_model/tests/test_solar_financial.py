"""
========================================================================================
Solar Financial Engine Unit & Integration Tests (current_model/tests/test_solar_financial.py)
========================================================================================
"""

import pytest
from current_model.models.solar import (
    SolarPVConfig,
    SolarLocation,
    SolarFinancialConfig,
    SolarFinancialMetrics
)
from current_model.core.solar_financial_engine import (
    compute_solar_capex,
    compute_solar_financial_metrics
)
from current_model.core.demo_scenario import (
    get_example1_solar_setup,
    load_example1_scenario,
    get_active_model_summary
)


def test_solar_capex_computation():
    """Tests turn-key CAPEX calculation matching the DRACBV Kosten-/Berechnungs-Dashboard."""
    # Test with standard DRACBV screenshot values:
    # 267.5 kWp DC (267,500 Wp), 196 kW AC Inverter (196,040 W)
    config = SolarPVConfig(
        module_count=461,
        module_power_wp=580.0,
        dc_capacity_kwp=267.38,
        inverter_capacity_kw=196.04
    )
    fin_cfg = SolarFinancialConfig(
        is_enabled=True,
        currency="EUR",
        cost_modules_per_wp=1.00,
        cost_inverter_per_w=0.07,
        cost_substructure_per_wp=0.15,
        cost_installation_per_wp=0.35,
        fixed_switchgear_cost=2500.0,
        fixed_travel_fee=1000.0
    )

    capex = compute_solar_capex(config, fin_cfg)
    assert capex["total_capex"] > 0
    assert capex["capex_modules"] > 0
    assert capex["capex_inverter"] > 0
    assert capex["capex_substructure"] > 0
    assert capex["capex_installation"] > 0
    assert capex["capex_fixed_fees"] == 3500.0
    assert capex["capex_per_kwp"] > 1000.0


def test_disabled_financials_returns_empty():
    """Tests that leaving financial parameters disabled returns unconfigured metrics without error."""
    config = SolarPVConfig(module_count=600, module_power_wp=450.0)
    fin_cfg = SolarFinancialConfig(is_enabled=False)

    capex = compute_solar_capex(config, fin_cfg)
    assert capex["total_capex"] == 0.0

    metrics = compute_solar_financial_metrics(
        config=config,
        fin_config=fin_cfg,
        annual_generation_kwh=450000.0
    )
    assert not metrics.is_configured
    assert metrics.total_capex == 0.0


def test_15_year_lifecycle_and_lcoe():
    """Tests 15-year cash-flow, LCOE, NPV, and payback calculation."""
    config = SolarPVConfig(
        module_count=1548,
        module_power_wp=450.0,
        dc_capacity_kwp=696.6,
        inverter_capacity_kw=590.0
    )
    fin_cfg = SolarFinancialConfig(
        is_enabled=True,
        currency="EUR",
        cost_modules_per_wp=1.00,
        cost_inverter_per_w=0.07,
        cost_substructure_per_wp=0.15,
        cost_installation_per_wp=0.35,
        annual_opex_pct=1.0,
        discount_rate_pct=5.0,
        electricity_price_inflation_pct=3.0,
        feed_in_tariff_per_kwh=0.06,
        analysis_horizon_years=15
    )

    annual_gen = 1150000.0  # 1.15 GWh/a
    metrics = compute_solar_financial_metrics(
        config=config,
        fin_config=fin_cfg,
        annual_generation_kwh=annual_gen,
        annual_avoided_cost=165000.0,
        annual_export_revenue=15000.0
    )

    assert metrics.is_configured
    assert metrics.total_capex > 1000000.0  # ~1.13M €
    assert len(metrics.cash_flow_table) == 15
    assert 0.02 < metrics.lcoe_per_kwh < 0.15
    assert metrics.payback_period_years is not None
    assert 4.0 < metrics.payback_period_years < 12.0
    assert metrics.npv > 0.0


def test_example1_has_solar_financials():
    """Verifies that Example 1 benchmark has preconfigured solar financials."""
    config, location, fin_config = get_example1_solar_setup()
    assert fin_config.is_enabled
    assert fin_config.cost_modules_per_wp == 1.00
    assert fin_config.cost_inverter_per_w == 0.07
    assert fin_config.cost_substructure_per_wp == 0.15
    assert fin_config.cost_installation_per_wp == 0.35


def test_instant_financial_recalculation_without_resimulation():
    """Verifies that changing unit costs updates CAPEX and LCOE immediately using existing generation."""
    config = SolarPVConfig(module_count=1000, module_power_wp=450.0)
    fin_cfg1 = SolarFinancialConfig(is_enabled=True, cost_modules_per_wp=0.80)
    metrics1 = compute_solar_financial_metrics(config, fin_cfg1, annual_generation_kwh=650000.0)

    fin_cfg2 = SolarFinancialConfig(is_enabled=True, cost_modules_per_wp=1.20)
    metrics2 = compute_solar_financial_metrics(config, fin_cfg2, annual_generation_kwh=650000.0)

    assert metrics2.capex_modules > metrics1.capex_modules
    assert metrics2.total_capex > metrics1.total_capex
    assert metrics2.lcoe_per_kwh > metrics1.lcoe_per_kwh


def test_gather_available_contracts_uses_clean_emoji_keys():
    """Verifies that _gather_available_contracts uses clean unicode emoji keys without raw :material/ codes."""
    from current_model.models.contract import Contract
    from current_model.ui.tab2_contract.comparison_view import _gather_available_contracts

    ref_c = Contract(name="Test Reference Contract")
    contracts = _gather_available_contracts(ref_c, key_prefix="test")

    for key in contracts.keys():
        assert not key.startswith(":material/"), f"Key {key} contains unparsed material icon shortcode"
        assert key.startswith("📌") or key.startswith("📄") or key.startswith("⚙️")

