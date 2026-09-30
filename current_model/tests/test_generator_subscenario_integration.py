"""
========================================================================================
Integration Tests: Generator Sub-Scenario & Multi-Asset Dispatch
(tests/test_generator_subscenario_integration.py)
========================================================================================
"""

import unittest
import numpy as np
import pandas as pd

from current_model.models.scenario import ProjectContainer, BaseScenario, SubScenario
from current_model.models.generator import GeneratorConfig
from current_model.models.solar import SolarPVConfig, SolarLocation
from current_model.models.bess import BESSConfig
from current_model.models.contract import Contract
from current_model.core.dracbv_engine import simulate_hybrid_scenario_dispatch
from current_model.ui.tab_comparison.view import _build_scenario_evaluation_records


class TestGeneratorSubScenarioIntegration(unittest.TestCase):
    """Verifies complete end-to-end integration of Generator within Sub-Scenarios."""

    def setUp(self):
        # 7-day test load profile (672 steps of 15 min) with 500 kW peaks
        np.random.seed(42)
        n_steps = 672
        timestamps = pd.date_range("2026-01-01", periods=n_steps, freq="15min")
        base_curve = 200.0 + 100.0 * np.sin(np.linspace(0, 7 * 2 * np.pi, n_steps))
        # Add peak overload exceeding 350 kW
        base_curve[100:108] += 200.0  # 450-500 kW peak

        self.df_load = pd.DataFrame({
            "timestamp": timestamps,
            "Total_Demand_kW": base_curve
        })

        self.contract = Contract(
            name="Industrial Supply Contract",
            contracted_capacity_kw=350.0,
            monthly_capacity_tariff=0.15,
            default_energy_rate=0.20,
            currency="EUR"
        )

        self.location = SolarLocation(name="Test Site", latitude=48.1351, longitude=11.5820)

    def test_standalone_generator_subscenario(self):
        """Tests Sub-Scenario with Generator only (peaking above 350 kW)."""
        sub = SubScenario(
            id="sub_gen_peaker",
            name="Genset Peaker",
            include_generator=True,
            generator_config=GeneratorConfig(
                rated_power_kw=150.0,
                dispatch_mode="peak_shaving_assist",
                peak_shaving_trigger_kw=350.0,
                capital_cost=25000.0,
                fuel_price_per_unit=1.50,
                maintenance_cost_per_op_hour=5.0
            )
        )

        res = simulate_hybrid_scenario_dispatch(
            sub_scenario=sub,
            df_load=self.df_load,
            power_col="Total_Demand_kW",
            contract=self.contract,
            location=self.location
        )

        self.assertIsNotNone(res["gen_result"])
        kpis = res["gen_result"]["kpis"]
        self.assertGreater(kpis.total_generation_kwh, 0.0)
        self.assertGreater(kpis.operating_hours, 0.0)
        # Verify peak was shaved down to at most ~350 kW
        self.assertLessEqual(res["gen_result"]["new_peak_kw"], 355.0)

    def test_hybrid_solar_bess_generator_backup(self):
        """Tests Sub-Scenario combining Solar PV + BESS + Generator Backup."""
        sub = SubScenario(
            id="sub_tri_hybrid",
            name="Tri-Hybrid",
            include_solar=True,
            solar_config=SolarPVConfig(module_count=400, module_power_wp=450.0),
            include_bess=True,
            bess_config=BESSConfig(capacity_kwh=100.0, max_discharge_power_kw=50.0),
            include_generator=True,
            generator_config=GeneratorConfig(
                rated_power_kw=100.0,
                is_backup_mode=True,
                backup_coverage_pct=100.0
            )
        )

        res = simulate_hybrid_scenario_dispatch(
            sub_scenario=sub,
            df_load=self.df_load,
            power_col="Total_Demand_kW",
            contract=self.contract,
            location=self.location
        )

        # Check all three technologies produced/dispatched
        self.assertGreater(np.sum(res["p_solar"]), 0.0)
        self.assertGreater(np.sum(res["p_solar_direct"]), 0.0)
        self.assertIsNotNone(res["gen_result"])
        self.assertGreater(res["gen_result"]["kpis"].total_generation_kwh, 0.0)

    def test_scenario_comparison_leaderboard_with_generator(self):
        """Tests that _build_scenario_evaluation_records correctly computes TCO and generation for generator sub-scenarios."""
        base = BaseScenario(base_contract=self.contract, location=self.location)
        project = ProjectContainer(project_name="Test Project", base_scenario=base)

        sub_gen = SubScenario(
            id="sub_gen_only",
            name="Generator Solution",
            include_generator=True,
            generator_config=GeneratorConfig(
                rated_power_kw=100.0,
                capital_cost=20000.0,
                fuel_price_per_unit=1.50
            )
        )
        project.sub_scenarios.append(sub_gen)

        records = _build_scenario_evaluation_records(project)
        self.assertEqual(len(records), 2)  # Base + Sub

        sub_rec = next(r for r in records if r["id"] == "sub_gen_only")
        self.assertGreater(sub_rec["capex"], 0.0)
        self.assertGreater(sub_rec["total_15y_tco"], 0.0)
        self.assertIn("Genset", sub_rec["tech_mix"])


if __name__ == "__main__":
    unittest.main()
