"""
========================================================================================
Unit Tests: Multi-Contract Comparison Engine (tests/test_contract_comparison.py)
========================================================================================
"""

import unittest
import numpy as np
import pandas as pd
import plotly.graph_objects as go

from current_model.models.contract import Contract
from current_model.models.financial import FinancialCostBreakdown
from current_model.core.financial_engine import compute_financial_bill
from current_model.ui.tab2_contract.comparison_charts import (
    create_comparison_stacked_bar_figure,
    create_monthly_comparison_series_figure,
    create_effective_rate_bar_figure
)


class TestContractComparison(unittest.TestCase):
    """Tests the multi-contract calculation, ranking, savings delta, and chart generators."""

    def setUp(self):
        # 96 steps constant 100 kW load curve
        self.load_curve = np.full(96, 100.0)

        self.c_ref = Contract(
            name="Reference Standard",
            currency="EUR",
            base_monthly_fee=50.0,
            contracted_capacity_kw=120.0,
            monthly_capacity_tariff=10.0,
            default_energy_rate=0.25,
            tou_rates=[{"name": "Standard", "rate": 0.25, "start_time": "00:00", "end_time": "24:00"}]
        )

        self.c_cheap = Contract(
            name="Cheap Dynamic Tariff",
            currency="EUR",
            base_monthly_fee=40.0,
            contracted_capacity_kw=120.0,
            monthly_capacity_tariff=8.0,
            default_energy_rate=0.18,
            tou_rates=[{"name": "Flat Cheap", "rate": 0.18, "start_time": "00:00", "end_time": "24:00"}]
        )

        self.c_expensive = Contract(
            name="High Peak Penalty Tariff",
            currency="EUR",
            base_monthly_fee=100.0,
            contracted_capacity_kw=80.0,  # Below 100 kW -> incurs peak penalty
            monthly_capacity_tariff=15.0,
            peak_penalty_rate=30.0,
            default_energy_rate=0.30,
            tou_rates=[{"name": "High Peak", "rate": 0.30, "start_time": "00:00", "end_time": "24:00"}]
        )

    def test_multi_contract_financial_computation_and_ranking(self):
        b_ref = compute_financial_bill(self.load_curve, self.c_ref)
        b_cheap = compute_financial_bill(self.load_curve, self.c_cheap)
        b_expensive = compute_financial_bill(self.load_curve, self.c_expensive)

        # Cheap contract should have lower gross cost than reference
        self.assertLess(b_cheap.total_gross_period, b_ref.total_gross_period)
        # Expensive contract should have higher gross cost than reference
        self.assertGreater(b_expensive.total_gross_period, b_ref.total_gross_period)

        # Verify savings
        savings_eur = b_ref.total_gross_period - b_cheap.total_gross_period
        self.assertGreater(savings_eur, 0.0)

    def test_comparison_chart_generation(self):
        results = [
            {
                "key": "ref",
                "display_name": "Reference Standard",
                "contract": self.c_ref,
                "currency": "EUR",
                "total_gross": 1000.0,
                "total_net": 1000.0,
                "energy_cost": 600.0,
                "capacity_cost": 300.0,
                "demand_cost": 0.0,
                "base_fee": 50.0,
                "penalty_cost": 0.0,
                "reactive_cost": 0.0,
                "taxes_cost": 50.0,
                "effective_rate_kwh": 0.25,
                "diff_gross": 0.0,
                "diff_pct": 0.0,
                "is_reference": True,
                "is_winner": False,
                "monthly_series": []
            },
            {
                "key": "cheap",
                "display_name": "Cheap Dynamic Tariff",
                "contract": self.c_cheap,
                "currency": "EUR",
                "total_gross": 800.0,
                "total_net": 800.0,
                "energy_cost": 450.0,
                "capacity_cost": 250.0,
                "demand_cost": 0.0,
                "base_fee": 40.0,
                "penalty_cost": 0.0,
                "reactive_cost": 0.0,
                "taxes_cost": 60.0,
                "effective_rate_kwh": 0.19,
                "diff_gross": -200.0,
                "diff_pct": -20.0,
                "is_reference": False,
                "is_winner": True,
                "monthly_series": []
            }
        ]

        fig1 = create_comparison_stacked_bar_figure(results, currency="EUR")
        self.assertIsInstance(fig1, go.Figure)

        fig2 = create_monthly_comparison_series_figure(results, currency="EUR")
        self.assertIsInstance(fig2, go.Figure)

        fig3 = create_effective_rate_bar_figure(results, currency="EUR")
        self.assertIsInstance(fig3, go.Figure)


if __name__ == "__main__":
    unittest.main()
