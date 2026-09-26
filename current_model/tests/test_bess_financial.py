"""
========================================================================================
Automated Unit Tests: BESS Financial Engine & Sub-Tab 4.2 (tests/test_bess_financial.py)
========================================================================================
"""

import sys
import os
import unittest
import numpy as np
import pandas as pd

# Ensure project and parent root in sys.path
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(TEST_DIR, ".."))
PARENT_ROOT = os.path.abspath(os.path.join(PROJECT_ROOT, ".."))
for p in [PROJECT_ROOT, PARENT_ROOT]:
    if p not in sys.path:
        sys.path.insert(0, p)

from current_model.models.bess import BESSConfig, BESSFinancialMetrics
from current_model.models.contract import Contract
from current_model.core.bess_engine import simulate_bess_dispatch
from current_model.core.bess_financial_engine import (
    compute_bess_capex_breakdown,
    compute_bess_financial_metrics,
    compute_bess_sensitivity_matrix
)
from current_model.ui.tab4_bess.financial_charts import (
    create_bess_cashflow_payback_figure,
    create_bess_annual_cost_comparison_figure,
    create_bess_cumulative_cost_trajectory_figure,
    create_bess_capex_donut_figure,
    create_bess_sensitivity_figure
)


class TestBESSFinancialEngine(unittest.TestCase):
    """Unit tests for BESS CAPEX, OPEX, billing savings, and 15-year lifecycle metrics."""

    def setUp(self):
        # 1-day synthetic profile with peaks
        n = 96
        base = np.full(n, 60.0)
        base[40:50] = 140.0
        base[70:80] = 160.0

        dates = pd.date_range("2026-06-01 00:00:00", periods=n, freq="15min")
        self.df_load = pd.DataFrame({"timestamp": dates, "P_Load_kW": base})

        self.bess_cfg = BESSConfig(
            capacity_kwh=200.0,
            max_charge_power_kw=100.0,
            max_discharge_power_kw=100.0,
            cost_per_kwh=350.0,
            fixed_installation_cost=5000.0,
            annual_om_pct=1.5,
            peak_shaving_threshold_kw=100.0
        )

        self.contract = Contract(
            name="Commercial Grid Tariff",
            currency="EUR",
            contracted_capacity_kw=100.0,
            monthly_capacity_tariff=14.0,
            peak_penalty_rate=25.0,
            default_energy_rate=0.20,
            base_monthly_fee=50.0
        )

        self.sim_res = simulate_bess_dispatch(
            bess_config=self.bess_cfg,
            load_df=self.df_load,
            grid_limit_kw=100.0
        )

    def test_bess_capex_breakdown(self):
        """Verify itemized CAPEX sums to total turn-key investment."""
        capex_dict = compute_bess_capex_breakdown(self.bess_cfg)
        # 200 kWh * 350 €/kWh + 5000 € = 75,000 €
        self.assertEqual(capex_dict["total_capex"], 75000.0)
        self.assertEqual(capex_dict["capex_per_kwh"], 375.0)
        self.assertGreater(capex_dict["capex_cells_modules"], 0.0)
        self.assertGreater(capex_dict["capex_inverter_pcs"], 0.0)

    def test_bess_financial_metrics(self):
        """Verify lifecycle financial metrics, payback, NPV, and cash flow schedule."""
        fin = compute_bess_financial_metrics(
            bess_config=self.bess_cfg,
            df_timeseries=self.sim_res.df_timeseries,
            contract=self.contract,
            grid_limit_kw=100.0,
            analysis_horizon_years=15,
            discount_rate_pct=5.0
        )

        self.assertTrue(fin.is_configured)
        self.assertEqual(fin.total_capex, 75000.0)
        self.assertEqual(len(fin.cash_flow_table), 15)
        self.assertEqual(len(fin.cumulative_cash_flow), 16)  # Year 0 to 15
        self.assertGreater(fin.annual_gross_savings, 0.0)
        self.assertGreater(fin.levelized_cost_of_storage_eur_kwh, 0.0)

        # Verify new detailed billing component breakdown
        self.assertGreater(fin.annual_status_quo_total_bill, 0.0)
        self.assertGreater(fin.annual_with_bess_total_bill, 0.0)
        self.assertGreater(fin.annual_penalty_savings, 0.0)
        self.assertGreater(fin.annual_fixed_om, 0.0)
        self.assertGreater(fin.annual_loss_kwh, 0.0)
        self.assertGreater(fin.annual_loss_cost, 0.0)
        self.assertAlmostEqual(fin.annual_opex_year1, fin.annual_fixed_om + fin.annual_loss_cost, places=2)

    def test_bess_sensitivity_matrix(self):
        """Verify sensitivity analysis over variations in CAPEX and Demand Tariffs."""
        matrix = compute_bess_sensitivity_matrix(
            bess_config=self.bess_cfg,
            df_timeseries=self.sim_res.df_timeseries,
            contract=self.contract,
            grid_limit_kw=100.0
        )
        self.assertEqual(len(matrix), 10)  # 5 variations x 2 parameters
        self.assertIn("parameter", matrix[0])
        self.assertIn("variation_pct", matrix[0])
        self.assertIn("payback_years", matrix[0])

    def test_financial_charts(self):
        """Verify Plotly figure constructors execute cleanly."""
        fin = compute_bess_financial_metrics(
            bess_config=self.bess_cfg,
            df_timeseries=self.sim_res.df_timeseries,
            contract=self.contract,
            grid_limit_kw=100.0
        )
        capex_dict = compute_bess_capex_breakdown(self.bess_cfg)
        sens_matrix = compute_bess_sensitivity_matrix(
            bess_config=self.bess_cfg,
            df_timeseries=self.sim_res.df_timeseries,
            contract=self.contract,
            grid_limit_kw=100.0
        )

        fig1 = create_bess_cashflow_payback_figure(fin, "EUR")
        self.assertIsNotNone(fig1)

        fig2 = create_bess_annual_cost_comparison_figure(fin, "EUR")
        self.assertIsNotNone(fig2)

        fig3 = create_bess_cumulative_cost_trajectory_figure(fin, "EUR")
        self.assertIsNotNone(fig3)

        fig4 = create_bess_capex_donut_figure(capex_dict, "EUR")
        self.assertIsNotNone(fig4)

        fig5 = create_bess_sensitivity_figure(sens_matrix)
        self.assertIsNotNone(fig5)

    def test_bess_in_scenario_comparison_records(self):
        """Verify Master Comparison evaluation dynamically processes standalone BESS scenarios."""
        from current_model.models.scenario import ProjectContainer, BaseScenario, SubScenario
        from current_model.ui.tab_comparison.view import _build_scenario_evaluation_records

        proj = ProjectContainer(
            project_name="Test Comparison Project",
            base_scenario=BaseScenario(
                name="Base",
                baseline_annual_kwh=1000000.0,
                baseline_peak_kw=200.0,
                baseline_annual_cost=200000.0,
                base_contract=self.contract
            )
        )
        sub_bess = SubScenario(
            name="BESS Peak Shaving Branch",
            include_solar=False,
            include_bess=True,
            bess_config=self.bess_cfg
        )
        proj.sub_scenarios.append(sub_bess)

        records = _build_scenario_evaluation_records(proj)
        self.assertEqual(len(records), 2)  # Base + BESS sub-scenario
        bess_rec = records[1]

        self.assertEqual(bess_rec["name"], "BESS Peak Shaving Branch")
        self.assertEqual(bess_rec["capex"], 75000.0)
        self.assertGreater(bess_rec["shaved_peak_kw"], 0.0)
        self.assertGreater(bess_rec["total_15y_tco"], 0.0)
        self.assertEqual(len(bess_rec["facility_cum_costs"]), 16)



if __name__ == "__main__":
    unittest.main()

