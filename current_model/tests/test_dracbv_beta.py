"""
========================================================================================
Unit Tests for DRACBV Multi-Path Simulator Beta (tests/test_dracbv_beta.py)
========================================================================================

Description:
------------
Verifies:
  - DRACBVConfig dataclass serialization and round-trip fidelity.
  - Lifecycle discounted cash flow calculations (TCO, NPV, Payback).
  - Parallel simulation execution of all solution paths against a synthetic load profile.
  - Dispatch timeseries column integrity and leaderboard structure.
"""

import unittest
import numpy as np
import pandas as pd

from current_model.models.dracbv import DRACBVConfig, DRACBVSolutionSummary
from current_model.models.contract import Contract
from current_model.models.generator import GeneratorConfig
from current_model.core.dracbv_engine import (
    compute_lifecycle_financials,
    compute_npv_and_payback,
    simulate_dracbv_multi_path,
    simulate_generator_peaking
)


class TestDRACBVMultiPathSimulator(unittest.TestCase):
    """Test suite for DRACBV simulation models and computational engine."""

    def setUp(self):
        # Create standard test contract
        self.contract = Contract(
            name="Test AC4 Contract",
            currency="EUR",
            contracted_capacity_kw=400.0,
            base_monthly_fee=100.0,
            monthly_capacity_tariff=0.15,
            default_energy_rate=0.20
        )

        # Create 1-week test load profile (672 steps) with peaks up to 550 kW (> 400 kW limit)
        np.random.seed(42)
        base_curve = 250.0 + 100.0 * np.sin(np.linspace(0, 7 * 2 * np.pi, 672))
        # Add peak bursts exceeding 400 kW (4 intervals = 1 hour each)
        base_curve[100:104] += 100.0 # Peak ~450 kW for 1 hour
        base_curve[300:304] += 100.0 # Peak ~450 kW for 1 hour
        self.df_load = pd.DataFrame({
            "timestamp": pd.date_range("2026-01-01", periods=672, freq="15min"),
            "Total_Demand_kW": np.maximum(20.0, base_curve)
        })

    def test_dracbv_config_serialization(self):
        """Verifies DRACBVConfig to_dict and from_dict round-trip."""
        cfg = DRACBVConfig(
            problem_type="grid_congestion",
            project_duration_years=15,
            upgrade_target_capacity_kw=650.0,
            bess_capacity_kwh=300.0
        )
        d = cfg.to_dict()
        cfg_restored = DRACBVConfig.from_dict(d)
        self.assertEqual(cfg_restored.problem_type, "grid_congestion")
        self.assertEqual(cfg_restored.project_duration_years, 15)
        self.assertEqual(cfg_restored.upgrade_target_capacity_kw, 650.0)
        self.assertEqual(cfg_restored.bess_capacity_kwh, 300.0)

    def test_lifecycle_financials_discounting(self):
        """Verifies TCO and discounted cash flows over time."""
        capex = 50000.0
        annual_opex = 2000.0
        annual_bill = 80000.0
        duration = 10
        wacc = 6.0
        infl = 2.5
        escl = 3.0

        tco, yearly, cum = compute_lifecycle_financials(
            initial_capex=capex,
            annual_opex_base=annual_opex,
            annual_grid_bill_base=annual_bill,
            duration_years=duration,
            discount_rate_pct=wacc,
            inflation_rate_pct=infl,
            energy_escalation_pct=escl
        )

        self.assertGreater(tco, capex)
        self.assertEqual(len(yearly), duration + 1)
        self.assertEqual(len(cum), duration + 1)
        self.assertEqual(cum[0], capex)
        self.assertGreater(cum[-1], cum[0])

    def test_npv_and_payback_calculation(self):
        """Verifies NPV positive return and payback calculation."""
        base_cum = [0.0, 100000.0, 200000.0, 300000.0, 400000.0, 500000.0]
        base_yr = [0.0, 100000.0, 100000.0, 100000.0, 100000.0, 100000.0]

        # Alternative has 50,000 capex, but 70,000 annual bill (saves 30,000/year)
        alt_cum = [50000.0, 120000.0, 190000.0, 260000.0, 330000.0, 400000.0]
        alt_yr = [50000.0, 70000.0, 70000.0, 70000.0, 70000.0, 70000.0]

        npv, payback = compute_npv_and_payback(base_cum, alt_cum, base_yr, alt_yr, discount_rate_pct=5.0)
        self.assertGreater(npv, 0.0)
        self.assertIsNotNone(payback)
        # Payback should occur around year 2
        self.assertTrue(1.0 <= payback <= 3.0)

    def test_multi_path_simulation_execution(self):
        """Verifies full multi-path parallel simulation against load profile."""
        config = DRACBVConfig(
            project_duration_years=10,
            upgrade_target_capacity_kw=600.0,
            upgrade_capex=40000.0,
            bess_capacity_kwh=250.0,
            bess_power_kw=120.0,
            bess_target_cap_kw=400.0,
            generator_enabled=True,
            solar_enabled=True,
            solar_target_coverage_pct=40.0
        )

        res = simulate_dracbv_multi_path(
            df_load=self.df_load,
            power_col="Total_Demand_kW",
            contract=self.contract,
            config=config,
            step_hours=0.25
        )

        self.assertIn("solutions", res)
        self.assertIn("df_dispatch", res)
        self.assertIn("leaderboard", res)

        solutions = res["solutions"]
        # Expected paths: Baseline, Grid Upgrade, AC4+BESS, Generator Bridging, Solar+BESS
        self.assertGreaterEqual(len(solutions), 4)

        path_ids = [s.path_id for s in solutions]
        self.assertIn("baseline_status_quo", path_ids)
        self.assertIn("path_grid_upgrade", path_ids)
        self.assertIn("path_ac4_bess", path_ids)
        self.assertIn("path_generator_bridging", path_ids)
        self.assertIn("path_pv_bess_hybrid", path_ids)

        # Baseline should detect violations
        base_sol = next(s for s in solutions if s.path_id == "baseline_status_quo")
        self.assertGreater(base_sol.violations_count, 0)
        self.assertFalse(base_sol.is_technically_feasible)

        # Upgrade path should have zero violations
        upg_sol = next(s for s in solutions if s.path_id == "path_grid_upgrade")
        self.assertEqual(upg_sol.violations_count, 0)
        self.assertTrue(upg_sol.is_technically_feasible)
        self.assertEqual(upg_sol.initial_capex, 40000.0)

        # BESS path should shave peaks
        bess_sol = next(s for s in solutions if s.path_id == "path_ac4_bess")
        self.assertGreater(bess_sol.peak_reduction_kw, 0.0)
        self.assertGreater(bess_sol.initial_capex, 0.0)

        # Dispatch dataframe checks
        df_disp = res["df_dispatch"]
        self.assertIn("Original_Load_kW", df_disp.columns)
        self.assertIn("New_Grid_Load_kW", df_disp.columns)
        self.assertIn("Generator_Power_kW", df_disp.columns)

    def test_generator_peaking_simulation_and_zahlungsreihe(self):
        """Verifies 15-minute generator peaking simulation, dispatch columns, and Zahlungsreihe."""
        gen_cfg = GeneratorConfig(
            rated_power_kw=100.0,
            peak_shaving_trigger_kw=400.0,
            fuel_price_per_unit=1.50,
            maintenance_cost_per_op_hour=4.00,
            monthly_lease_fee=1000.0
        )
        res = simulate_generator_peaking(
            df_load=self.df_load,
            power_col="Total_Demand_kW",
            contract=self.contract,
            gen_config=gen_cfg,
            step_hours=0.25
        )
        self.assertIn("df_timeseries", res)
        self.assertIn("df_zahlungsreihe", res)
        self.assertIn("kpis", res)

        # Check dispatch dataframe
        df_ts = res["df_timeseries"]
        self.assertIn("Original_Load_kW", df_ts.columns)
        self.assertIn("New_Grid_Load_kW", df_ts.columns)
        self.assertIn("Generator_Power_kW", df_ts.columns)
        self.assertIn("Fuel_Liters", df_ts.columns)

        # Verify generator ran during peak intervals
        self.assertGreater(res["kpis"].operating_hours, 0.0)
        self.assertGreater(res["kpis"].total_fuel_units, 0.0)
        self.assertGreater(res["peak_shaved_kw"], 0.0)
        self.assertLessEqual(res["new_peak_kw"], 400.0 + 1.0)

        # Check Zahlungsreihe dataframe
        df_z = res["df_zahlungsreihe"]
        self.assertIn("Month", df_z.columns)
        self.assertIn("Status_Quo_Bill", df_z.columns)
        self.assertIn("New_Grid_Bill", df_z.columns)
        self.assertIn("Generator_Cost", df_z.columns)
        self.assertIn("Total_With_Generator", df_z.columns)
        self.assertIn("Cum_Status_Quo", df_z.columns)
        self.assertIn("Cum_With_Generator", df_z.columns)
        self.assertIn("Cum_Savings", df_z.columns)


if __name__ == "__main__":
    unittest.main()

