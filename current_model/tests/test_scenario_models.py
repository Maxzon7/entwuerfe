"""
========================================================================================
Unit Tests: Scenario & Project Domain Models (tests/test_scenario_models.py)
========================================================================================
"""

import unittest
import json
import datetime
from current_model.models.load_component import SimpleConsumer, TimeWindow
from current_model.models.contract import Contract
from current_model.models.solar import SolarLocation, SolarPVConfig, SolarFinancialConfig
from current_model.models.bess import BESSConfig
from current_model.models.generator import GeneratorConfig
from current_model.models.scenario import BaseScenario, SubScenario, ProjectContainer


class TestScenarioDomainModels(unittest.TestCase):
    """Tests for BaseScenario, SubScenario, and ProjectContainer."""

    def setUp(self):
        self.location = SolarLocation(name="Seville", latitude=37.38, longitude=-5.98)
        self.contract = Contract(name="Base Contract", contracted_capacity_kw=300.0, default_energy_rate=0.20)
        self.consumer = SimpleConsumer(
            name="Test Chiller",
            power_kw=50.0,
            time_windows=[TimeWindow(datetime.time(8, 0), datetime.time(18, 0))]
        )

    def test_base_scenario_serialization(self):
        base = BaseScenario(
            name="Status Quo Facility",
            description="Baseline testing scenario",
            load_source_type="synthetic",
            consumers=[self.consumer],
            base_contract=self.contract,
            location=self.location,
            baseline_annual_kwh=150000.0,
            baseline_peak_kw=50.0,
            baseline_annual_cost=35000.0
        )
        data = base.to_dict()
        self.assertEqual(data["name"], "Status Quo Facility")
        self.assertEqual(len(data["consumers"]), 1)
        self.assertEqual(data["base_contract"]["contracted_capacity_kw"], 300.0)
        self.assertEqual(data["location"]["latitude"], 37.38)

        restored = BaseScenario.from_dict(data)
        self.assertEqual(restored.name, "Status Quo Facility")
        self.assertEqual(len(restored.consumers), 1)
        self.assertEqual(restored.consumers[0].name, "Test Chiller")
        self.assertEqual(restored.base_contract.contracted_capacity_kw, 300.0)
        self.assertEqual(restored.location.name, "Seville")

    def test_sub_scenario_opt_in_and_cloning(self):
        solar_cfg = SolarPVConfig(module_count=500, module_power_wp=450.0)
        bess_cfg = BESSConfig(capacity_kwh=200.0, max_discharge_power_kw=100.0)
        gen_cfg = GeneratorConfig(rated_power_kw=75.0)

        sub = SubScenario(
            id="sub_test_1",
            name="Option A: Solar + Storage",
            include_solar=True,
            include_bess=True,
            include_generator=False,
            solar_config=solar_cfg,
            bess_config=bess_cfg,
            generator_config=gen_cfg
        )
        self.assertEqual(sub.technology_mix_label, "Solar PV + BESS")

        # Test Cloning
        cloned = sub.clone(new_id="sub_clone_1", new_name="Option A Clone")
        self.assertEqual(cloned.id, "sub_clone_1")
        self.assertEqual(cloned.name, "Option A Clone")
        self.assertTrue(cloned.include_solar)
        self.assertTrue(cloned.include_bess)
        self.assertFalse(cloned.include_generator)
        self.assertEqual(cloned.solar_config.module_count, 500)
        self.assertEqual(cloned.bess_config.capacity_kwh, 200.0)

    def test_project_container_management(self):
        project = ProjectContainer(
            project_name="Commercial Solar & BESS Assessment",
            currency="EUR",
            author="Max Mustermann"
        )
        self.assertEqual(len(project.sub_scenarios), 0)

        sub1 = SubScenario(id="s1", name="Scenario 1: Solar Only", include_solar=True)
        sub2 = SubScenario(id="s2", name="Scenario 2: Solar + BESS", include_solar=True, include_bess=True)

        project.add_sub_scenario(sub1)
        project.add_sub_scenario(sub2)

        self.assertEqual(len(project.sub_scenarios), 2)
        self.assertEqual(project.active_sub_scenario_id, "s2")
        self.assertEqual(project.get_active_scenario().name, "Scenario 2: Solar + BESS")

        # Test duplication
        duplicated = project.duplicate_sub_scenario("s1", new_name="Scenario 1 Sensitivity")
        self.assertIsNotNone(duplicated)
        self.assertEqual(len(project.sub_scenarios), 3)
        self.assertEqual(duplicated.name, "Scenario 1 Sensitivity")

        # Test deletion
        deleted = project.delete_sub_scenario("s2")
        self.assertTrue(deleted)
        self.assertEqual(len(project.sub_scenarios), 2)

    def test_full_project_json_roundtrip(self):
        project = ProjectContainer(
            project_name="Full Roundtrip Test",
            currency="USD",
            base_scenario=BaseScenario(
                name="Baseline Facility",
                location=self.location,
                base_contract=self.contract,
                consumers=[self.consumer]
            )
        )
        sub = SubScenario(
            id="sub_roundtrip",
            name="Hybrid Microgrid",
            include_solar=True,
            include_bess=True,
            include_generator=True,
            solar_config=SolarPVConfig(module_count=1000),
            bess_config=BESSConfig(capacity_kwh=500.0),
            generator_config=GeneratorConfig(rated_power_kw=200.0)
        )
        project.add_sub_scenario(sub)

        json_str = project.to_json()
        self.assertIn("drac_simulation_project", json_str)
        self.assertIn("Hybrid Microgrid", json_str)

        restored_proj = ProjectContainer.from_json(json_str)
        self.assertEqual(restored_proj.project_name, "Full Roundtrip Test")
        self.assertEqual(restored_proj.currency, "USD")
        self.assertEqual(restored_proj.base_scenario.name, "Baseline Facility")
        self.assertEqual(len(restored_proj.sub_scenarios), 1)
        
        restored_sub = restored_proj.sub_scenarios[0]
        self.assertEqual(restored_sub.name, "Hybrid Microgrid")
        self.assertTrue(restored_sub.include_solar)
        self.assertTrue(restored_sub.include_bess)
        self.assertTrue(restored_sub.include_generator)
        self.assertEqual(restored_sub.solar_config.module_count, 1000)
        self.assertEqual(restored_sub.bess_config.capacity_kwh, 500.0)
        self.assertEqual(restored_sub.generator_config.rated_power_kw, 200.0)


if __name__ == "__main__":
    unittest.main()
