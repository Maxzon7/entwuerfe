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

    def test_generator_residual_backup_dispatch(self):
        import numpy as np
        import pandas as pd
        from current_model.core.dracbv_engine import simulate_generator_peaking
        from current_model.models.contract import Contract

        contract = Contract(contracted_capacity_kw=200.0)
        gen = GeneratorConfig(
            rated_power_kw=100.0,
            is_backup_mode=True,
            backup_coverage_pct=100.0,
            fuel_price_per_unit=1.50,
            maintenance_cost_per_op_hour=5.0
        )

        # Baseline load of 300 kW, but Solar PV direct already covered 150 kW -> Residual 150 kW
        n_steps = 96
        raw_load = np.full(n_steps, 300.0)
        residual_load = np.full(n_steps, 150.0)

        df_load = pd.DataFrame({"P_kW": raw_load})

        res = simulate_generator_peaking(
            df_load=df_load,
            power_col="P_kW",
            contract=contract,
            gen_config=gen,
            residual_series=residual_load
        )

        kpis = res["kpis"]
        # Generator rated at 100 kW covers 100 kW of the 150 kW residual load -> 50 kW final grid draw
        self.assertEqual(res["new_peak_kw"], 50.0)
        self.assertEqual(kpis.operating_hours, 24.0)
        self.assertEqual(kpis.total_generation_kwh, 100.0 * 24.0)
        self.assertGreater(kpis.total_fuel_units, 0.0)

    def test_subscenario_generator_initialization(self):
        from current_model.models.scenario import SubScenario
        sub = SubScenario(
            id="sub_gen_test",
            name="Generator Only",
            include_generator=True
        )
        self.assertIsNotNone(sub.generator_config)
        self.assertEqual(sub.generator_config.rated_power_kw, 100.0)
        self.assertIn("Genset", sub.technology_mix_label)

        sub_bk = SubScenario(
            id="sub_bk_test",
            name="Solar + Backup Gen",
            include_solar=True,
            include_generator=True
        )
        sub_bk.generator_config.is_backup_mode = True
        self.assertIn("Solar PV + Genset Backup", sub_bk.technology_mix_label)


if __name__ == "__main__":
    unittest.main()
