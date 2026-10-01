"""
========================================================================================
Unit Tests: Dynamic Day-Ahead Electricity Contracts & Market Price Integration
(current_model/tests/test_dynamic_contract.py)
========================================================================================
Verifies:
1. Contract data model pricing_model, supplier_margin, network_volume_tariff, and serialization.
2. Market price engine loading, caching, 15-min resampling, and temporal alignment.
3. Financial billing engine calculations with dynamic Day-Ahead tariffs and Enexis MS-D rules.
4. Mathematical plausibility of fixed fees, network charges, and effective unit rates.
========================================================================================
"""

import unittest
import numpy as np
import pandas as pd
import datetime

from current_model.models.contract import Contract, get_contract_presets
from current_model.models.financial import FinancialCostBreakdown, MonthlyPaymentRecord
from current_model.core.market_price_engine import (
    list_available_market_profiles,
    load_market_price_series,
    get_aligned_market_prices,
    get_market_price_kpis
)
from current_model.core.financial_engine import compute_financial_bill


class TestDynamicContractSystem(unittest.TestCase):
    """Tests for dynamic Day-Ahead wholesale contracts and market price series."""

    def test_contract_dynamic_fields_default_and_custom(self):
        c_default = Contract()
        self.assertEqual(c_default.pricing_model, "time_of_use")
        self.assertEqual(c_default.network_volume_tariff, 0.0)
        self.assertEqual(c_default.supplier_margin, 0.0)
        self.assertEqual(c_default.market_price_profile_id, "epex_nl_2025")

        c_custom = Contract(
            name="Custom Dutch Dynamic",
            pricing_model="day_ahead_dynamic",
            network_volume_tariff=0.0250,
            supplier_margin=0.0075,
            market_price_profile_id="epex_nl_2025"
        )
        self.assertEqual(c_custom.pricing_model, "day_ahead_dynamic")
        self.assertEqual(c_custom.network_volume_tariff, 0.0250)
        self.assertEqual(c_custom.supplier_margin, 0.0075)

    def test_contract_serialization_preserves_dynamic_fields(self):
        c = Contract(
            name="Serialized Dynamic Contract",
            pricing_model="day_ahead_dynamic",
            network_volume_tariff=0.0250,
            supplier_margin=0.0080,
            market_price_profile_id="epex_nl_2025"
        )
        d = c.to_dict()
        self.assertEqual(d["pricing_model"], "day_ahead_dynamic")
        self.assertEqual(d["network_volume_tariff"], 0.0250)
        self.assertEqual(d["supplier_margin"], 0.0080)
        self.assertEqual(d["market_price_profile_id"], "epex_nl_2025")

        c2 = Contract.from_dict(d)
        self.assertEqual(c2.pricing_model, "day_ahead_dynamic")
        self.assertEqual(c2.network_volume_tariff, 0.0250)
        self.assertEqual(c2.supplier_margin, 0.0080)
        self.assertEqual(c2.market_price_profile_id, "epex_nl_2025")

    def test_enexis_dynamic_preset_exists(self):
        presets = get_contract_presets()
        self.assertIn("Netherlands Dynamic Day-Ahead (Enexis MS-D 2025)", presets)
        enexis = presets["Netherlands Dynamic Day-Ahead (Enexis MS-D 2025)"]
        self.assertEqual(enexis.pricing_model, "day_ahead_dynamic")
        self.assertEqual(enexis.contracted_capacity_kw, 500.0)
        self.assertEqual(enexis.network_volume_tariff, 0.0250)
        self.assertEqual(enexis.supplier_margin, 0.0075)
        self.assertEqual(enexis.currency, "EUR")

    def test_market_price_engine_load_and_resample(self):
        profiles = list_available_market_profiles()
        self.assertIn("epex_nl_2025", profiles)
        self.assertTrue(profiles["epex_nl_2025"]["is_available"])

        df_prices = load_market_price_series("epex_nl_2025")
        # 365 days * 96 slots = 35040 intervals
        self.assertEqual(len(df_prices), 35040)
        self.assertFalse(df_prices["price_eur_kwh"].isna().any())
        self.assertFalse(df_prices["price_eur_mwh"].isna().any())

        # Average price in Netherlands 2025 is between 0.07 and 0.10 EUR/kWh
        mean_p = df_prices["price_eur_kwh"].mean()
        self.assertTrue(0.07 <= mean_p <= 0.10, f"Unexpected mean spot price: {mean_p}")

    def test_market_price_engine_kpis(self):
        kpis = get_market_price_kpis("epex_nl_2025")
        self.assertEqual(kpis["profile_id"], "epex_nl_2025")
        self.assertEqual(kpis["total_hours"], 8760.0)
        self.assertTrue(kpis["negative_price_hours"] > 0)
        self.assertTrue(kpis["mean_eur_kwh"] > 0.05)

    def test_market_price_alignment_years(self):
        # 1. 2025 timestamps
        dates_2025 = pd.date_range("2025-05-01 00:00", periods=96, freq="15min")
        prices_2025 = get_aligned_market_prices(dates_2025, profile_id="epex_nl_2025")
        self.assertEqual(len(prices_2025), 96)
        self.assertFalse(np.isnan(prices_2025).any())

        # 2. 2026 timestamps (should map to same May 1st profile)
        dates_2026 = pd.date_range("2026-05-01 00:00", periods=96, freq="15min")
        prices_2026 = get_aligned_market_prices(dates_2026, profile_id="epex_nl_2025")
        self.assertEqual(len(prices_2026), 96)
        np.testing.assert_allclose(prices_2025, prices_2026, rtol=1e-5)

        # 3. Synthetic without timestamps
        synth_prices = get_aligned_market_prices(timestamps=None, profile_id="epex_nl_2025", n_steps=96)
        self.assertEqual(len(synth_prices), 96)
        self.assertFalse(np.isnan(synth_prices).any())

    def test_enexis_financial_calculation_full_year(self):
        presets = get_contract_presets()
        contract = presets["Netherlands Dynamic Day-Ahead (Enexis MS-D 2025)"]

        # 1 full year 15-minute load data (flat 100 kW = 876,000 kWh)
        dates = pd.date_range("2025-01-01 00:00", "2025-12-31 23:45", freq="15min")
        df_load = pd.DataFrame({
            "timestamp": dates,
            "Total_Demand_kW": [100.0] * len(dates)
        })

        breakdown = compute_financial_bill(load_data=df_load, contract=contract)

        self.assertEqual(breakdown.currency, "EUR")
        self.assertAlmostEqual(breakdown.total_consumption_kwh, 876000.0, places=0)
        self.assertAlmostEqual(breakdown.peak_demand_kw, 100.0, places=1)
        self.assertEqual(len(breakdown.monthly_series), 12)

        # Fixed capacity charge verification:
        # Contracted capacity is 500 kW at 3.85 EUR/kW/month = 1,925 EUR/month = 23,100 EUR/year
        cap_items = [it for it in breakdown.line_items if it.category == "Capacity (Contracted)"]
        self.assertTrue(len(cap_items) > 0)
        self.assertAlmostEqual(cap_items[0].cost_period, 23100.0, places=0)
        self.assertAlmostEqual(cap_items[0].cost_monthly, 1925.0, places=0)

        # Base fee verification: 125 EUR/month * 12 = 1,500 EUR/year
        base_items = [it for it in breakdown.line_items if it.category == "Base Fee"]
        self.assertTrue(len(base_items) > 0)
        self.assertAlmostEqual(base_items[0].cost_period, 1500.0, places=0)
        self.assertAlmostEqual(base_items[0].cost_monthly, 125.0, places=0)

        # Network transport volume charge: 876,000 kWh * 0.0250 = 21,900 EUR/year
        net_items = [it for it in breakdown.line_items if it.category == "Network (Volume)"]
        self.assertTrue(len(net_items) > 0)
        self.assertAlmostEqual(net_items[0].cost_period, 21900.0, places=0)

        # Supplier opslag: 876,000 kWh * 0.0075 = 6,570 EUR/year
        margin_items = [it for it in breakdown.line_items if "Supplier" in it.description or "Opslag" in it.description]
        self.assertTrue(len(margin_items) > 0)
        self.assertAlmostEqual(margin_items[0].cost_period, 6570.0, places=0)

        # Total line items should equal total gross period within rounding
        line_item_sum = sum(it.cost_period for it in breakdown.line_items)
        self.assertAlmostEqual(line_item_sum, breakdown.total_gross_period, places=0)

        # Effective unit rate plausibility:
        # Net unit rate (without VAT) is roughly: Spot (~0.087) + Opslag (0.0075) + Net (0.0250) + Fixed/kWh (~0.028) + EB (0.0131) ~ 0.16 EUR/kWh
        # With 21% VAT: around 0.18 - 0.20 EUR/kWh.
        self.assertTrue(0.12 <= breakdown.effective_kwh_price <= 0.22,
                        f"Effective rate out of plausible range: {breakdown.effective_kwh_price}")


if __name__ == "__main__":
    unittest.main()
