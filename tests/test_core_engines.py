"""
========================================================================================
Unit Tests: Core Calculation & Processing Engines (tests/test_core_engines.py)
========================================================================================
"""

import unittest
import pandas as pd
import numpy as np

from current_model.core.csv_parser import (
    generate_sample_demo_csv,
    parse_csv_content,
    detect_suggested_columns
)
from current_model.core.load_processor import process_load_profile_data
from current_model.core.metrics_engine import compute_load_profile_kpis
from current_model.core.synthetic_engine import aggregate_synthetic_24h
from current_model.models.load_component import SimpleConsumer, TimeWindow
import datetime


class TestCoreEngines(unittest.TestCase):
    """Tests core computational, parser, and normalization functions."""

    def test_csv_parser_and_demo_generation(self):
        filename, csv_text = generate_sample_demo_csv(days=3)
        self.assertTrue(filename.endswith(".csv"))
        self.assertTrue(len(csv_text) > 100)

        df_raw = parse_csv_content(csv_text)
        self.assertEqual(len(df_raw), 96 * 3)

        time_cols, power_cols, unit = detect_suggested_columns(df_raw)
        self.assertTrue(len(time_cols) >= 1)
        self.assertTrue(len(power_cols) >= 2)

    def test_load_processor_with_units(self):
        # Create a sample DataFrame
        df_sample = pd.DataFrame({
            "Date": ["01.01.2025", "01.01.2025", "01.01.2025", "01.01.2025"],
            "Time": ["00:00", "00:15", "00:30", "00:45"],
            "Meter1": [10.0, 20.0, 30.0, 40.0],
            "Meter2": [5.0, 5.0, 10.0, 10.0]
        })

        # Test direct kW
        df_clean = process_load_profile_data(
            df_raw=df_sample,
            selected_time_cols=["Date", "Time"],
            selected_power_cols=["Meter1", "Meter2"],
            selected_unit="kW (Active Power - Direct)",
            dayfirst=True
        )
        self.assertIn("Total_Demand_kW", df_clean.columns)
        self.assertEqual(df_clean["Total_Demand_kW"].iloc[0], 15.0)
        self.assertEqual(df_clean["Total_Demand_kW"].iloc[3], 50.0)

        # Test 15-min kWh conversion (* 4.0)
        df_clean_kwh = process_load_profile_data(
            df_raw=df_sample,
            selected_time_cols=["Date", "Time"],
            selected_power_cols=["Meter1"],
            selected_unit="kWh (15-min interval) → kW",
            dayfirst=True
        )
        # 10.0 kWh in 15min = 40.0 kW
        self.assertEqual(df_clean_kwh["Meter1"].iloc[0], 40.0)

    def test_metrics_engine_kpis(self):
        dates = pd.date_range("2025-01-01 00:00", periods=96, freq="15min")
        df_clean = pd.DataFrame({
            "timestamp": dates,
            "Total_Demand_kW": [20.0] * 96
        })
        kpis = compute_load_profile_kpis(df_clean)
        self.assertEqual(kpis.peak_kw, 20.0)
        self.assertEqual(kpis.min_kw, 20.0)
        self.assertEqual(kpis.avg_kw, 20.0)
        # 20 kW * 24 hours = 480 kWh = 0.48 MWh
        self.assertAlmostEqual(kpis.total_kwh, 480.0, places=1)
        self.assertAlmostEqual(kpis.total_mwh, 0.48, places=2)

    def test_synthetic_engine_aggregation(self):
        c1 = SimpleConsumer("Machine 1", 30.0, [TimeWindow(datetime.time(8, 0), datetime.time(12, 0))])
        c2 = SimpleConsumer("Machine 2", 20.0, [TimeWindow(datetime.time(10, 0), datetime.time(16, 0))])

        df_day, total_curve, metrics = aggregate_synthetic_24h([c1, c2])
        self.assertEqual(len(df_day), 96)
        self.assertEqual(len(total_curve), 96)

        # At 11:00 (step 44), both are active -> 30 + 20 = 50 kW
        self.assertEqual(total_curve[44], 50.0)
        self.assertEqual(metrics["peak_demand_kw"], 50.0)
        self.assertEqual(metrics["consumer_count"], 2)


if __name__ == "__main__":
    unittest.main()
