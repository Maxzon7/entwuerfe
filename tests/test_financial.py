"""
========================================================================================
Unit Tests: Financial & Cost Breakdown Engine (tests/test_financial.py)
========================================================================================
"""

import unittest
import numpy as np
import pandas as pd
import datetime

from current_model.models.contract import Contract
from current_model.models.financial import FinancialCostBreakdown
from current_model.core.financial_engine import compute_financial_bill


class TestFinancialEngine(unittest.TestCase):
    """Tests the financial billing engine calculations, TOU splitting, capacity charges, and taxes."""

    def setUp(self):
        self.contract = Contract(
            currency="EUR",
            base_monthly_fee=50.0,
            contracted_capacity_kw=100.0,
            monthly_capacity_tariff=1.50,    # 100 kW * 1.50 = 150.00 €/month
            peak_penalty_rate=5.00,
            tou_rates=[
                {"name": "Standard Day", "rate": 0.20, "start_time": "08:00", "end_time": "20:00"},
                {"name": "Off-Peak Night", "rate": 0.10, "start_time": "20:00", "end_time": "08:00"}
            ],
            taxes_and_fees=[
                {"name": "VAT", "type": "percentage", "value": 20.0, "description": "20% VAT"}
            ]
        )

    def test_synthetic_24h_financial_bill(self):
        # 96 steps: 50 kW constant 24/7
        curve_96 = np.full(96, 50.0)
        # Total energy = 50 kW * 24h = 1200 kWh/day
        # Day (08:00 to 20:00 = 12h = 48 steps): 50 kW * 12h = 600 kWh @ 0.20 = 120.00 €
        # Night (20:00 to 08:00 = 12h = 48 steps): 50 kW * 12h = 600 kWh @ 0.10 = 60.00 €
        # Total energy period = 180.00 €/day
        breakdown = compute_financial_bill(load_data=curve_96, contract=self.contract, duration_days=1.0)

        self.assertEqual(breakdown.total_consumption_kwh, 1200.0)
        self.assertEqual(breakdown.peak_demand_kw, 50.0)
        self.assertAlmostEqual(breakdown.energy_cost_period, 180.00, places=2)

        # Monthly energy projection: 180 €/day * 30.4167 days = 5475.00 €/month
        self.assertAlmostEqual(breakdown.energy_cost_monthly, 180.00 * 30.4167, places=1)

        # Monthly capacity: 100 kW * 1.50 €/kW = 150.00 €
        self.assertEqual(breakdown.capacity_cost_monthly, 150.00)

        # Monthly base fee: 50.00 €
        self.assertEqual(breakdown.base_fee_monthly, 50.00)

        # Penalty: P_max (50 kW) <= contracted (100 kW) -> 0.00 €
        self.assertEqual(breakdown.penalty_cost_monthly, 0.0)

        # Net monthly: 5475.00 + 150.00 + 50.00 = 5675.00 €
        expected_net_m = (180.00 * 30.4167) + 150.00 + 50.00
        self.assertAlmostEqual(breakdown.total_net_monthly, expected_net_m, places=1)

        # Taxes: 20% of net
        expected_tax_m = expected_net_m * 0.20
        self.assertAlmostEqual(breakdown.total_taxes_monthly, expected_tax_m, places=1)

        # Gross: net + tax
        self.assertAlmostEqual(breakdown.total_gross_monthly, expected_net_m + expected_tax_m, places=1)

    def test_peak_penalty_calculation(self):
        # 96 steps with peak demand of 120 kW (exceeding 100 kW contracted by 20 kW)
        curve_96 = np.full(96, 50.0)
        curve_96[40] = 120.0  # Peak spike

        breakdown = compute_financial_bill(load_data=curve_96, contract=self.contract, duration_days=1.0)
        self.assertEqual(breakdown.peak_demand_kw, 120.0)

        # Excess: 20 kW * 5.00 €/kW = 100.00 € penalty per month
        self.assertEqual(breakdown.penalty_cost_monthly, 100.00)

    def test_csv_dataframe_financial_bill(self):
        dates = pd.date_range("2025-01-01 00:00", periods=96 * 7, freq="15min")
        df_csv = pd.DataFrame({
            "timestamp": dates,
            "Total_Demand_kW": [40.0] * (96 * 7)
        })

        breakdown = compute_financial_bill(load_data=df_csv, contract=self.contract)
        self.assertEqual(breakdown.duration_days, 7.0)
        self.assertTrue(len(breakdown.line_items) >= 4)
        self.assertTrue(breakdown.effective_kwh_price > 0.0)


if __name__ == "__main__":
    unittest.main()
