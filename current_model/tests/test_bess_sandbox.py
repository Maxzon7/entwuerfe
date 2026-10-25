"""
========================================================================================
Unit Tests: BESS Sandbox Engineering & Excel Sizing Verification (tests/test_bess_sandbox.py)
========================================================================================
Verifies:
1. Pure physical exceedance energy conservation.
2. 100% Zero-Deficit sizing equivalence (0.0 kWh remaining deficit).
3. Simultaneous 4-criterion bottleneck audit without early if/elif exit.
4. Pareto sizing frontier monotonicity across coverage percentiles.
5. Paula3 Dutch Site preset accuracy (131.4 kW peak vs. 110.0 kW limit = +21.4 kW overload).
6. "No-Date Fallback" anchor mapping time-only sequences to continuous 2026-01-01 DatetimeIndex.
========================================================================================
"""

import unittest
import os
import sys
import numpy as np
import pandas as pd

# Path bootstrapping
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
WORKSPACE_DIR = os.path.abspath(os.path.join(PROJECT_ROOT, ".."))
for p in [WORKSPACE_DIR, PROJECT_ROOT]:
    if p not in sys.path:
        sys.path.insert(0, p)

from models.bess import BESSConfig
from core.load_processor import process_load_profile_data
from ui_sandbox.BESS_sandbox import (
    get_case1_liander_industrial_preset,
    get_case2_enexis_commercial_preset,
    get_case3_paula_dutch_site_preset,
    calculate_excel_bess_sizing_and_diagnostics,
    evaluate_comprehensive_bottlenecks,
    simulate_sandbox_bess_dispatch,
    compute_pareto_coverage_curve,
    compute_exceedance_energy_summary
)


class TestBESSSandboxPhysics(unittest.TestCase):
    """Test suite asserting mathematical equivalence and robustness of BESS Sandbox physics."""

    def test_exceedance_energy_conservation(self):
        """Verifies that integral exceedance energy strictly matches discrete 15-minute interval sums."""
        preset = get_case1_liander_industrial_preset()
        load_series = preset.load_df["Total_Demand_kW"].to_numpy(dtype=float)
        grid_limit = preset.grid_limit_kw

        summary = compute_exceedance_energy_summary(load_series, grid_limit, step_hours=0.25)
        raw_overload = np.maximum(0.0, load_series - grid_limit)
        expected_kwh = float(np.sum(raw_overload) * 0.25)

        self.assertAlmostEqual(summary["total_exceedance_kwh"], expected_kwh, places=2)
        self.assertAlmostEqual(summary["max_overload_kw"], float(np.max(raw_overload)), places=2)
        self.assertGreater(summary["total_exceedance_kwh"], 0.0)

    def test_infinite_ghost_battery_zero_deficit(self):
        """Confirms that applying recommended 100% sizing yields strictly 0.0 kWh remaining deficit."""
        preset = get_case1_liander_industrial_preset()
        power_col = "Total_Demand_kW"

        excel_sizing = calculate_excel_bess_sizing_and_diagnostics(
            preset.load_df[power_col], preset.grid_limit_kw, step_hours=0.25
        )

        # Sizing recommended for 100% zero deficit
        zero_deficit_cfg = BESSConfig(
            capacity_kwh=excel_sizing.min_required_gross_kwh,
            max_discharge_power_kw=excel_sizing.min_required_discharge_kw,
            max_charge_power_kw=excel_sizing.min_required_charge_kw,
            round_trip_efficiency_pct=preset.bess_config.round_trip_efficiency_pct,
            soc_min_pct=preset.bess_config.soc_min_pct,
            soc_max_pct=preset.bess_config.soc_max_pct,
            initial_soc_pct=preset.bess_config.soc_max_pct,
            unit_capacity_kwh=excel_sizing.recommended_unit_kwh,
            unit_count=excel_sizing.recommended_units
        )

        sim_res = simulate_sandbox_bess_dispatch(
            bess_config=zero_deficit_cfg,
            load_df=preset.load_df,
            grid_limit_kw=preset.grid_limit_kw,
            step_hours=0.25,
            power_col=power_col
        )

        unmet_kwh = float(sim_res.df_timeseries["P_Overload_Unmet_kW"].sum() * 0.25)
        unmet_peak_kw = float(sim_res.df_timeseries["P_Overload_Unmet_kW"].max())

        self.assertAlmostEqual(unmet_kwh, 0.0, delta=0.5, msg="Remaining deficit must be ~0.0 kWh under 100% sizing")
        self.assertAlmostEqual(unmet_peak_kw, 0.0, delta=0.5, msg="Peak deficit must be ~0.0 kW under 100% sizing")

    def test_simultaneous_bottlenecks(self):
        """Verifies that all 4 criteria are evaluated simultaneously without early if/elif short-circuiting."""
        preset = get_case1_liander_industrial_preset()
        power_col = "Total_Demand_kW"

        excel_sizing = calculate_excel_bess_sizing_and_diagnostics(
            preset.load_df[power_col], preset.grid_limit_kw, step_hours=0.25
        )

        # Deliberately undersize both power and capacity
        undersized_cfg = BESSConfig(
            capacity_kwh=excel_sizing.min_required_gross_kwh * 0.3,
            max_discharge_power_kw=excel_sizing.min_required_discharge_kw * 0.5,
            max_charge_power_kw=excel_sizing.min_required_charge_kw * 0.5,
            round_trip_efficiency_pct=preset.bess_config.round_trip_efficiency_pct,
            soc_min_pct=preset.bess_config.soc_min_pct,
            soc_max_pct=preset.bess_config.soc_max_pct,
            initial_soc_pct=preset.bess_config.soc_max_pct,
            unit_capacity_kwh=preset.bess_config.unit_capacity_kwh
        )

        sim_res = simulate_sandbox_bess_dispatch(
            bess_config=undersized_cfg,
            load_df=preset.load_df,
            grid_limit_kw=preset.grid_limit_kw,
            step_hours=0.25,
            power_col=power_col
        )

        audit = evaluate_comprehensive_bottlenecks(
            load_series=preset.load_df[power_col],
            grid_limit_kw=preset.grid_limit_kw,
            bess_config=undersized_cfg,
            step_hours=0.25,
            sim_result=sim_res
        )

        self.assertEqual(len(audit.checks), 4, "Must return exactly 4 checks")
        self.assertFalse(audit.all_passed, "Audit must not pass when undersized")
        self.assertGreater(audit.failed_count, 1, "Multiple simultaneous failures must be flagged")

        keys = [c.key for c in audit.checks]
        self.assertIn("discharge_power", keys)
        self.assertIn("storage_capacity", keys)
        self.assertIn("recharge_power", keys)
        self.assertIn("grid_headroom", keys)

    def test_pareto_monotonicity(self):
        """Asserts that required battery capacity and power increase monotonically with target coverage."""
        preset = get_case1_liander_industrial_preset()
        power_col = "Total_Demand_kW"

        pareto_res = compute_pareto_coverage_curve(
            load_series=preset.load_df[power_col],
            grid_limit_kw=preset.grid_limit_kw,
            round_trip_efficiency_pct=preset.bess_config.round_trip_efficiency_pct,
            soc_min_pct=preset.bess_config.soc_min_pct,
            soc_max_pct=preset.bess_config.soc_max_pct,
            step_hours=0.25
        )

        self.assertGreaterEqual(len(pareto_res.coverage_pct), 5)
        # Verify monotonicity of capacity: higher coverage requires >= gross kWh
        kwh_values = pareto_res.required_gross_kwh
        for i in range(len(kwh_values) - 1):
            self.assertLessEqual(
                kwh_values[i],
                kwh_values[i + 1] + 1.0,  # small numerical tolerance
                f"Pareto curve must be non-decreasing at step {i}"
            )

        # Residual deficit must decrease monotonically towards 0
        deficits = pareto_res.residual_deficit_kwh
        for i in range(len(deficits) - 1):
            self.assertGreaterEqual(
                deficits[i] + 0.1,
                deficits[i + 1],
                f"Residual deficit must be non-increasing at step {i}"
            )

    def test_paula3_preset_diagnostics(self):
        """Verifies Paula3 Dutch Site preset has peak demand 131.4 kW and unserved overload +21.4 kW."""
        preset = get_case3_paula_dutch_site_preset()
        self.assertEqual(preset.grid_limit_kw, 110.0)
        self.assertIn("Paula", preset.title)

        load_series = preset.load_df["Total_Demand_kW"].to_numpy(dtype=float)
        peak_demand = float(np.max(load_series))
        self.assertAlmostEqual(peak_demand, 131.4, places=1, msg="Paula3 peak must be 131.4 kW")

        summary = compute_exceedance_energy_summary(load_series, preset.grid_limit_kw, step_hours=0.25)
        self.assertAlmostEqual(summary["max_overload_kw"], 21.4, places=1, msg="Overload peak must be +21.4 kW")
        self.assertGreater(summary["total_exceedance_kwh"], 0.0)

    def test_no_date_fallback_anchor(self):
        """Verifies that time-only sequences (00:00..23:45) are cleanly anchored to 2026-01-01 00:00:00."""
        # Create a raw table with time-only strings across 3 days (288 intervals)
        times = []
        for d in range(3):
            for h in range(24):
                for m in [0, 15, 30, 45]:
                    times.append(f"{h:02d}:{m:02d}")

        raw_df = pd.DataFrame({
            "Time": times,
            "Power_kW": [50.0 + (i % 20) for i in range(len(times))]
        })

        processed = process_load_profile_data(
            df_raw=raw_df,
            selected_time_cols=["Time"],
            selected_power_cols=["Power_kW"],
            selected_unit="kW (Active Power - Direct)",
            dayfirst=True
        )

        self.assertEqual(len(processed), len(times))
        self.assertIn("timestamp", processed.columns)
        # Must span across 3 distinct calendar days starting on 2026-01-01
        self.assertEqual(processed["timestamp"].min(), pd.Timestamp("2026-01-01 00:00:00"))
        self.assertEqual(processed["timestamp"].dt.date.nunique(), 3, "Must not collapse into a single day")


if __name__ == "__main__":
    unittest.main()
