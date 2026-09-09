"""
========================================================================================
Unit Tests: Generator Data Models (tests/test_generator_model.py)
========================================================================================
"""

import unittest
from current_model.models.generator import GeneratorConfig, GeneratorKPIs, get_generator_presets


class TestGeneratorModels(unittest.TestCase):
    """Tests for GeneratorConfig dataclass, calculations, and presets."""

    def test_generator_fuel_consumption(self):
        gen = GeneratorConfig(
            rated_power_kw=100.0,
            fuel_curve_slope_l_per_kwh=0.24,
            fuel_curve_intercept_l_per_kw_rated=0.04
        )
        # Power = 0 kW -> 0 L/h
        self.assertEqual(gen.calc_fuel_rate_per_hour(0.0), 0.0)
        self.assertEqual(gen.calc_fuel_consumption(0.0, 0.25), 0.0)

        # Power = 50 kW (50% load) -> Rate = (0.24 * 50) + (0.04 * 100) = 12.0 + 4.0 = 16.0 L/h
        rate_50 = gen.calc_fuel_rate_per_hour(50.0)
        self.assertEqual(rate_50, 16.0)
        # 15-minute consumption (0.25 hours) = 16.0 * 0.25 = 4.0 Liters
        self.assertEqual(gen.calc_fuel_consumption(50.0, 0.25), 4.0)

        # Power = 100 kW (100% load) -> Rate = (0.24 * 100) + 4.0 = 28.0 L/h
        rate_100 = gen.calc_fuel_rate_per_hour(100.0)
        self.assertEqual(rate_100, 28.0)

    def test_generator_serialization_roundtrip(self):
        gen = GeneratorConfig(
            rated_power_kw=250.0,
            fuel_type="Diesel",
            dispatch_mode="peak_shaving_assist",
            peak_shaving_trigger_kw=280.0,
            fuel_price_per_unit=1.55,
            maintenance_cost_per_op_hour=7.50
        )
        data = gen.to_dict()
        self.assertEqual(data["rated_power_kw"], 250.0)
        self.assertEqual(data["fuel_type"], "Diesel")
        self.assertEqual(data["peak_shaving_trigger_kw"], 280.0)
        self.assertEqual(data["fuel_price_per_unit"], 1.55)

        restored = GeneratorConfig.from_dict(data)
        self.assertEqual(restored.rated_power_kw, 250.0)
        self.assertEqual(restored.fuel_type, "Diesel")
        self.assertEqual(restored.peak_shaving_trigger_kw, 280.0)
        self.assertEqual(restored.fuel_price_per_unit, 1.55)

    def test_generator_presets(self):
        presets = get_generator_presets()
        self.assertIn("100 kW Diesel Peaker", presets)
        self.assertIn("150 kW Natural Gas Baseload/Island", presets)
        
        gas_gen = presets["150 kW Natural Gas Baseload/Island"]
        self.assertEqual(gas_gen.fuel_type, "Natural Gas")
        self.assertEqual(gas_gen.dispatch_mode, "islanding_grid_congestion")


if __name__ == "__main__":
    unittest.main()
