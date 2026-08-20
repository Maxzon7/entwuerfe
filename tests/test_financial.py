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
            currency="ARS",
            base_monthly_fee=500.0,
            contracted_capacity_kw=100.0,
            monthly_capacity_tariff=150.0,
            peak_penalty_rate=200.0,
            tou_rates=[
                {"name": "Standard Day", "rate": 60.0, "start_time": "08:00", "end_time": "20:00"},
                {"name": "Off-Peak Night", "rate": 30.0, "start_time": "20:00", "end_time": "08:00"}
            ],
            taxes_and_fees=[
                {"name": "VAT", "type": "percentage", "value": 20.0, "description": "20% VAT"}
            ]
        )

    def test_synthetic_24h_financial_bill_and_series(self):
        # 96 steps: 50 kW constant 24/7
        curve_96 = np.full(96, 50.0)
        breakdown = compute_financial_bill(load_data=curve_96, contract=self.contract, duration_days=1.0)

        self.assertEqual(breakdown.currency, "ARS")
        self.assertEqual(breakdown.total_consumption_kwh, 1200.0)
        self.assertEqual(breakdown.peak_demand_kw, 50.0)

        # Monthly payment series should have 12 calendar months
        self.assertEqual(len(breakdown.monthly_series), 12)
        self.assertEqual(breakdown.monthly_series[0].period_label, "January")
        self.assertEqual(breakdown.monthly_series[0].days_count, 31)

    def test_peak_penalty_calculation(self):
        curve_96 = np.full(96, 50.0)
        curve_96[40] = 120.0  # Peak spike exceeding 100 kW by 20 kW

        breakdown = compute_financial_bill(load_data=curve_96, contract=self.contract, duration_days=1.0)
        self.assertEqual(breakdown.peak_demand_kw, 120.0)
        self.assertEqual(breakdown.penalty_cost_monthly, 4000.00)

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

    def test_single_month_inspection_target_month(self):
        dates = pd.date_range("2025-01-01 00:00", periods=96 * 60, freq="15min")
        df_csv = pd.DataFrame({
            "timestamp": dates,
            "Total_Demand_kW": [40.0] * (96 * 60)
        })

        feb_breakdown = compute_financial_bill(load_data=df_csv, contract=self.contract, target_month="Feb 2025")
        self.assertEqual(feb_breakdown.currency, "ARS")
        # February 2025 has 28 days = 28 * 96 = 2688 steps = 28 * 40 * 24 = 26,880 kWh
        self.assertEqual(feb_breakdown.total_consumption_kwh, 26880.0)
        self.assertEqual(feb_breakdown.duration_days, 28.0)


if __name__ == "__main__":
    unittest.main()
