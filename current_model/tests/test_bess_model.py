"""
========================================================================================
Unit Tests: BESS Data Models (tests/test_bess_model.py)
========================================================================================
"""

import unittest
from current_model.models.bess import BESSConfig, BESSKPIs, get_bess_presets


class TestBESSModels(unittest.TestCase):
    """Tests for BESSConfig dataclass, calculations, and presets."""

    def test_bess_defaults_and_properties(self):
        bess = BESSConfig(
            capacity_kwh=200.0,
            max_charge_power_kw=100.0,
            max_discharge_power_kw=100.0,
            soc_min_pct=10.0,
            soc_max_pct=90.0,
            cost_per_kwh=350.0,
            fixed_installation_cost=5000.0
        )
        # Usable capacity: 200 * (90 - 10)% = 160 kWh
        self.assertEqual(bess.effective_usable_kwh, 160.0)
        # C-rate: 100 kW / 200 kWh = 0.5 C
        self.assertEqual(bess.c_rate_discharge, 0.5)
        # Total CAPEX: (200 * 350) + 5000 = 75,000 €
        self.assertEqual(bess.total_capex, 75000.0)

    def test_bess_serialization_roundtrip(self):
        bess = BESSConfig(
            capacity_kwh=300.0,
            dispatch_strategy="peak_shaving",
            peak_shaving_threshold_kw=180.0,
            round_trip_efficiency_pct=92.5
        )
        data = bess.to_dict()
        self.assertEqual(data["capacity_kwh"], 300.0)
        self.assertEqual(data["dispatch_strategy"], "peak_shaving")
        self.assertEqual(data["peak_shaving_threshold_kw"], 180.0)
        self.assertEqual(data["round_trip_efficiency_pct"], 92.5)

        restored = BESSConfig.from_dict(data)
        self.assertEqual(restored.capacity_kwh, 300.0)
        self.assertEqual(restored.dispatch_strategy, "peak_shaving")
        self.assertEqual(restored.peak_shaving_threshold_kw, 180.0)
        self.assertEqual(restored.round_trip_efficiency_pct, 92.5)

    def test_bess_presets(self):
        presets = get_bess_presets()
        self.assertIn("Small C&I Storage (100 kWh / 50 kW)", presets)
        self.assertIn("Industrial Peak Shaver (200 kWh / 200 kW - 1C)", presets)
        
        peak_shaver = presets["Industrial Peak Shaver (200 kWh / 200 kW - 1C)"]
        self.assertEqual(peak_shaver.c_rate_discharge, 1.0)
        self.assertEqual(peak_shaver.dispatch_strategy, "peak_shaving")


if __name__ == "__main__":
    unittest.main()
