"""
========================================================================================
Automated Unit Tests: BESS Engine & Tab 4 Simulation (tests/test_bess_simulation.py)
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

from current_model.models.bess import BESSConfig, BESSKPIs, get_bess_presets
from current_model.core.bess_engine import (
    analyze_grid_violations,
    simulate_bess_dispatch,
    compute_average_week_dispatch,
    BESSSimulationResult
)
from current_model.ui.tab4_bess.charts import (
    create_grid_violation_preview_figure,
    create_average_week_dispatch_figure,
    create_bess_soc_analysis_figure,
    create_bess_soc_heatmap_figure,
    create_bess_dispatch_timeseries_figure,
    create_load_duration_peak_shaving_figure,
    create_seasonal_bess_diurnal_figure,
    create_monthly_bess_throughput_figure
)


class TestBESSSimulation(unittest.TestCase):
    """Unit test suite for physical BESS dispatch and grid overload diagnostics."""

    def setUp(self):
        # Create a synthetic 1-day (96 15-min intervals) load profile with two prominent peaks
        # Peak 1: 140 kW at noon (intervals 44-52)
        # Peak 2: 160 kW in evening (intervals 72-80)
        # Baseline: 60 kW
        self.dt_hours = 0.25
        self.n_intervals = 96
        base_curve = np.full(self.n_intervals, 60.0)
        base_curve[44:52] = 140.0  # 2 hours peak
        base_curve[72:80] = 160.0  # 2 hours peak

        dates = pd.date_range("2026-06-01 00:00:00", periods=self.n_intervals, freq="15min")
        self.test_df = pd.DataFrame({
            "timestamp": dates,
            "P_Load_kW": base_curve
        })
        self.grid_limit_kw = 100.0

    def test_grid_violation_diagnostics(self):
        """Verify calculation of overload peak, longest violation run, and exceedance energy."""
        diag = analyze_grid_violations(
            self.test_df["P_Load_kW"],
            grid_limit_kw=self.grid_limit_kw,
            step_hours=self.dt_hours
        )

        self.assertEqual(diag["peak_load_kw"], 160.0)
        self.assertEqual(diag["overload_peak_kw"], 60.0)  # 160 - 100
        self.assertEqual(diag["total_violation_intervals"], 16)  # 8 + 8 intervals
        self.assertEqual(diag["total_violation_hours"], 4.0)    # 16 * 0.25h
        self.assertEqual(diag["longest_violation_run_intervals"], 8)
        self.assertEqual(diag["longest_violation_run_hours"], 2.0)

        # Exceedance energy:
        # Peak 1: (140 - 100) * 8 * 0.25 = 40 * 2 = 80 kWh
        # Peak 2: (160 - 100) * 8 * 0.25 = 60 * 2 = 120 kWh
        # Total: 200 kWh
        self.assertAlmostEqual(diag["total_exceedance_energy_kwh"], 200.0, places=1)
        self.assertAlmostEqual(diag["worst_event_energy_kwh"], 120.0, places=1)
        self.assertAlmostEqual(diag["min_bess_capacity_kwh"], 120.0, places=1)
        self.assertAlmostEqual(diag["worst_event_duration_hours"], 2.0, places=1)
        self.assertTrue(diag["has_violations"])

    def test_min_bess_capacity_asymmetric_peaks(self):
        """
        Verify that minimum BESS capacity correctly integrates discrete energy
        even when one peak is long & low and another is short & sharp.
        """
        # 100 kW grid limit
        # Event 1: Long & low: 24 intervals (6 hours) at 115 kW -> 15 kW over * 6h = 90 kWh
        # Event 2: Short & sharp: 4 intervals (1 hour) at 170 kW -> 70 kW over * 1h = 70 kWh
        load = np.full(100, 50.0)
        load[10:34] = 115.0  # 6 hours, 15 kW exceedance = 90 kWh
        load[50:54] = 170.0  # 1 hour, 70 kW exceedance = 70 kWh

        diag = analyze_grid_violations(load, grid_limit_kw=100.0, step_hours=0.25)
        self.assertEqual(diag["overload_peak_kw"], 70.0)
        self.assertEqual(diag["longest_violation_run_hours"], 6.0)
        # Event 1 has greater energy (90 kWh > 70 kWh) despite lower peak
        self.assertAlmostEqual(diag["worst_event_energy_kwh"], 90.0, places=1)
        self.assertAlmostEqual(diag["min_bess_capacity_kwh"], 90.0, places=1)
        self.assertAlmostEqual(diag["worst_event_duration_hours"], 6.0, places=1)

        # Now test case where short & sharp has more energy:
        # Event 3: 8 intervals (2 hours) at 180 kW -> 80 kW over * 2h = 160 kWh
        load[70:78] = 180.0
        diag2 = analyze_grid_violations(load, grid_limit_kw=100.0, step_hours=0.25)
        self.assertEqual(diag2["overload_peak_kw"], 80.0)
        self.assertEqual(diag2["longest_violation_run_hours"], 6.0)  # Still event 1 has longest duration
        self.assertAlmostEqual(diag2["worst_event_energy_kwh"], 160.0, places=1)  # Event 3 has highest energy
        self.assertAlmostEqual(diag2["min_bess_capacity_kwh"], 160.0, places=1)
        self.assertAlmostEqual(diag2["worst_event_duration_hours"], 2.0, places=1)

    def test_bess_peak_shaving_dispatch(self):
        """Verify interval-by-interval battery peak shaving dispatch and SoC tracking."""
        bess_cfg = BESSConfig(
            capacity_kwh=300.0,
            max_charge_power_kw=100.0,
            max_discharge_power_kw=100.0,
            round_trip_efficiency_pct=90.0,
            soc_min_pct=10.0,
            soc_max_pct=95.0,
            initial_soc_pct=95.0,  # fully charged to start
            peak_shaving_threshold_kw=100.0
        )

        sim_res = simulate_bess_dispatch(
            bess_config=bess_cfg,
            load_df=self.test_df,
            grid_limit_kw=100.0,
            step_hours=self.dt_hours
        )

        self.assertIsInstance(sim_res, BESSSimulationResult)
        df_out = sim_res.df_timeseries

        # Residual peak on grid should be shaved down to 100 kW
        max_grid_pk = df_out["P_Grid_kW"].max()
        self.assertLessEqual(max_grid_pk, 100.01)

        # Discharge should occur during the peak hours
        self.assertGreater(sim_res.kpis.total_discharged_kwh, 0.0)
        self.assertGreater(sim_res.kpis.peak_shaved_kw, 59.0)  # Shaved ~60 kW

        # SoC must never drop below SoC_min (10% = 30 kWh)
        min_soc_reached = df_out["SoC_kWh"].min()
        self.assertGreaterEqual(min_soc_reached, 300.0 * 0.10 - 1e-3)

        # SoC must never exceed SoC_max (95% = 285 kWh)
        max_soc_reached = df_out["SoC_kWh"].max()
        self.assertLessEqual(max_soc_reached, 300.0 * 0.95 + 1e-3)

    def test_average_week_aggregation(self):
        """Verify representative 7-day (168-hour) week aggregation."""
        # 1 full year dataset (35,040 intervals)
        n_year = 35040
        dates_year = pd.date_range("2026-01-01 00:00:00", periods=n_year, freq="15min")
        df_year = pd.DataFrame({
            "timestamp": dates_year,
            "P_Load_kW": np.random.uniform(50.0, 150.0, n_year),
            "P_Grid_kW": np.random.uniform(50.0, 100.0, n_year),
            "P_BESS_Discharge_kW": np.random.uniform(0.0, 50.0, n_year),
            "P_BESS_Charge_kW": np.random.uniform(0.0, 30.0, n_year),
            "SoC_pct": np.random.uniform(10.0, 95.0, n_year),
            "SoC_kWh": np.random.uniform(20.0, 190.0, n_year)
        })

        df_avg_week = compute_average_week_dispatch(df_year, step_hours=0.25)
        # Should have exactly 7 days * 24 hours * 4 intervals/hour = 672 intervals
        self.assertEqual(len(df_avg_week), 672)
        self.assertIn("week_hour", df_avg_week.columns)
        self.assertIn("time_label", df_avg_week.columns)
        self.assertIn("day_name", df_avg_week.columns)
        self.assertAlmostEqual(df_avg_week["week_hour"].iloc[0], 0.0)
        self.assertAlmostEqual(df_avg_week["week_hour"].iloc[-1], 167.75)

    def test_bess_chart_constructors(self):
        """Verify Plotly figure constructors execute without exceptions."""
        bess_cfg = BESSConfig(capacity_kwh=200.0, max_charge_power_kw=100.0, max_discharge_power_kw=100.0)
        sim_res = simulate_bess_dispatch(bess_cfg, self.test_df, grid_limit_kw=100.0)

        fig1 = create_grid_violation_preview_figure(self.test_df, grid_limit_kw=100.0)
        self.assertIsNotNone(fig1)

        fig2 = create_bess_dispatch_timeseries_figure(sim_res.df_timeseries, 100.0, 100.0, 200.0)
        self.assertIsNotNone(fig2)

        df_avg_week = compute_average_week_dispatch(sim_res.df_timeseries, 0.25)
        fig_avg = create_average_week_dispatch_figure(df_avg_week, 100.0, 200.0)
        self.assertIsNotNone(fig_avg)

        fig_soc_dyn = create_bess_soc_analysis_figure(sim_res.df_timeseries, bess_cfg)
        self.assertIsNotNone(fig_soc_dyn)

        fig_soc_heat = create_bess_soc_heatmap_figure(sim_res.df_timeseries)
        self.assertIsNotNone(fig_soc_heat)

        fig3 = create_load_duration_peak_shaving_figure(sim_res.df_timeseries, 100.0)
        self.assertIsNotNone(fig3)

        fig4 = create_seasonal_bess_diurnal_figure(sim_res.df_timeseries)
        self.assertIsNotNone(fig4)

        fig5 = create_monthly_bess_throughput_figure(sim_res.monthly_metrics)
        self.assertIsNotNone(fig5)


if __name__ == "__main__":
    unittest.main()

