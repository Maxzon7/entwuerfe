"""
========================================================================================
Unit Tests: 365-Day Annual Synthetic Simulation Engine (tests/test_annual_simulation.py)
========================================================================================
"""

import unittest
import datetime
import numpy as np
import pandas as pd

from current_model.models.load_component import SimpleConsumer, TimeWindow
from current_model.models.calendar_config import CalendarConfig
from current_model.core.synthetic_engine import aggregate_synthetic_year


class TestAnnualSimulationEngine(unittest.TestCase):
    """Tests the 365-day vectorized simulation, weekday scheduling, seasonality, and holidays."""

    def test_weekday_filtering(self):
        # Consumer only active Monday to Friday (0..4)
        c = SimpleConsumer(
            name="Weekday Machine",
            power_kw=10.0,
            active_days=[0, 1, 2, 3, 4],
            time_windows=[TimeWindow(datetime.time(8, 0), datetime.time(16, 0))]
        )

        df_year, total_curve, metrics = aggregate_synthetic_year([c], year=2025)

        self.assertEqual(len(total_curve), 35040)
        self.assertEqual(metrics["steps_count"], 35040)
        self.assertEqual(metrics["days_count"], 365)

        # 2025-01-01 was a Wednesday (active) -> at 10:00 (step 40) should be 10 kW
        self.assertEqual(total_curve[40], 10.0)

        # 2025-01-04 was a Saturday (inactive) -> day 3, all steps should be 0.0 kW
        sat_start = 3 * 96
        sat_end = 4 * 96
        self.assertTrue(np.all(total_curve[sat_start:sat_end] == 0.0))

    def test_system_wide_holiday_treatment_as_sunday(self):
        # Consumer active Mon-Fri only
        c = SimpleConsumer(
            name="Plant 1",
            power_kw=20.0,
            active_days=[0, 1, 2, 3, 4],
            time_windows=[TimeWindow(datetime.time(8, 0), datetime.time(16, 0))]
        )

        # Set 2025-01-01 (Wednesday) as a custom holiday
        df_year, total_curve, metrics = aggregate_synthetic_year(
            consumers=[c],
            year=2025,
            holidays=["2025-01-01"]
        )

        # 2025-01-01 is treated as Sunday -> consumer is inactive (0.0 kW)
        day1_steps = total_curve[:96]
        self.assertTrue(np.all(day1_steps == 0.0))

        # 2025-01-02 (Thursday) is not a holiday -> active (20.0 kW at 10:00)
        day2_10am = 96 + 40
        self.assertEqual(total_curve[day2_10am], 20.0)

    def test_seasonal_variation_profile(self):
        c_winter = SimpleConsumer(
            name="Heating System",
            power_kw=100.0,
            active_days=[0, 1, 2, 3, 4, 5, 6],
            seasonal_pattern="winter_heavy",
            time_windows=[TimeWindow(datetime.time(0, 0), datetime.time(0, 0))]
        )

        df_year, total_curve, metrics = aggregate_synthetic_year([c_winter], year=2025)

        # January factor is 1.25 -> 100 * 1.25 = 125 kW
        jan_sample = total_curve[10]
        self.assertEqual(jan_sample, 125.0)

        # July (starts on day 181 = 181 * 96) factor is 0.85 -> 100 * 0.85 = 85 kW
        jul_idx = 181 * 96 + 10
        self.assertEqual(total_curve[jul_idx], 85.0)

    def test_annual_metrics_calculation(self):
        c = SimpleConsumer(
            name="Constant Load",
            power_kw=10.0,
            active_days=[0, 1, 2, 3, 4, 5, 6],
            time_windows=[TimeWindow(datetime.time(0, 0), datetime.time(0, 0))]
        )
        df_year, total_curve, metrics = aggregate_synthetic_year([c], year=2025)

        # 10 kW * 8760 hours = 87,600 kWh = 87.6 MWh
        self.assertAlmostEqual(metrics["annual_energy_mwh"], 87.6, places=1)
        self.assertEqual(metrics["peak_demand_kw"], 10.0)
        self.assertAlmostEqual(metrics["full_load_hours"], 8760.0, places=0)


if __name__ == "__main__":
    unittest.main()
