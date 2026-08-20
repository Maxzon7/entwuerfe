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
from current_model.models.financial import FinancialCostBreakdown, MonthlyPaymentRecord
from current_model.core.financial_engine import compute_financial_bill


class TestFinancialEngine(unittest.TestCase):
    """Tests the financial billing engine calculations, TOU splitting, monthly payment series, and taxes."""

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

    def test_synthetic_24h_financial_bill_and_series(self):
        # 96 steps: 50 kW constant 24/7
        curve_96 = np.full(96, 50.0)
        breakdown = compute_financial_bill(load_data=curve_96, contract=self.contract, duration_days=1.0)

        self.assertEqual(breakdown.total_consumption_kwh, 1200.0)
        self.assertEqual(breakdown.peak_demand_kw, 50.0)
        self.assertAlmostEqual(breakdown.energy_cost_period, 180.00, places=2)

        # Monthly payment series should have 12 calendar months
        self.assertEqual(len(breakdown.monthly_series), 12)
        self.assertEqual(breakdown.monthly_series[0].period_label, "January")
        self.assertEqual(breakdown.monthly_series[0].days_count, 31)

        # January: 31 days * 1200 kWh/day = 37,200 kWh
        self.assertEqual(breakdown.monthly_series[0].energy_kwh, 37200.0)

        # January Energy Cost: 31 * 180.00 = 5580.00 €
        self.assertEqual(breakdown.monthly_series[0].energy_cost_net, 5580.00)
        self.assertEqual(breakdown.monthly_series[0].capacity_cost_net, 150.00)
        self.assertEqual(breakdown.monthly_series[0].base_fee_net, 50.00)

        # Net = 5580 + 150 + 50 = 5780.00 €
        self.assertEqual(breakdown.monthly_series[0].total_net, 5780.00)
        # Taxes = 20% of 5780 = 1156.00 €
        self.assertEqual(breakdown.monthly_series[0].taxes_and_levies, 1156.00)
        # Gross = 6936.00 €
        self.assertEqual(breakdown.monthly_series[0].total_gross, 6936.00)

    def test_peak_penalty_calculation(self):
        curve_96 = np.full(96, 50.0)
        curve_96[40] = 120.0  # Peak spike exceeding 100 kW by 20 kW

        breakdown = compute_financial_bill(load_data=curve_96, contract=self.contract, duration_days=1.0)
        self.assertEqual(breakdown.peak_demand_kw, 120.0)
        self.assertEqual(breakdown.penalty_cost_monthly, 100.00)
        self.assertEqual(breakdown.monthly_series[0].penalty_cost_net, 100.00)

    def test_csv_dataframe_multi_month_series(self):
        # Generate 60 days (spanning 2 calendar months)
        dates = pd.date_range("2025-01-01 00:00", periods=96 * 60, freq="15min")
        df_csv = pd.DataFrame({
            "timestamp": dates,
            "Total_Demand_kW": [40.0] * (96 * 60)
        })

        breakdown = compute_financial_bill(load_data=df_csv, contract=self.contract)
        self.assertAlmostEqual(breakdown.duration_days, 60.0, places=0)
        self.assertTrue(len(breakdown.monthly_series) >= 2)
        self.assertEqual(breakdown.monthly_series[0].period_label, "Jan 2025")
        self.assertEqual(breakdown.monthly_series[1].period_label, "Feb 2025")


if __name__ == "__main__":
    unittest.main()
