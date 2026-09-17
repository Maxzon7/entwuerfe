"""
========================================================================================
Automated Unit Tests: Scenario Component Deletion & State Sync (tests/test_scenario_component_deletion.py)
========================================================================================
"""

import sys
import os
import unittest
import streamlit as st

# Ensure project root in sys.path
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(TEST_DIR, ".."))
PARENT_ROOT = os.path.abspath(os.path.join(PROJECT_ROOT, ".."))
for p in [PROJECT_ROOT, PARENT_ROOT]:
    if p not in sys.path:
        sys.path.insert(0, p)

from current_model.models.scenario import BaseScenario, SubScenario, ProjectContainer
from current_model.models.solar import SolarPVConfig, SolarFinancialConfig
from current_model.models.bess import BESSConfig
from current_model.models.generator import GeneratorConfig
from current_model.core.project_io import sync_active_scenario_into_session


class TestScenarioComponentDeletion(unittest.TestCase):
    """Tests granular component deletion, state isolation, and reset functionality."""

    def setUp(self):
        self.project = ProjectContainer(project_name="Test Project")

        # Scenario 1: Solar + BESS
        self.sub1 = SubScenario(
            id="sub_1",
            name="Sub 1: Solar + Storage",
            include_solar=True,
            solar_config=SolarPVConfig(module_count=500, module_power_wp=450.0),
            solar_financial=SolarFinancialConfig(is_enabled=True),
            include_bess=True,
            bess_config=BESSConfig(capacity_kwh=200.0, max_discharge_power_kw=100.0),
            include_generator=True,
            generator_config=GeneratorConfig(rated_power_kw=50.0)
        )

        # Scenario 2: Solar only
        self.sub2 = SubScenario(
            id="sub_2",
            name="Sub 2: Pure Solar",
            include_solar=True,
            solar_config=SolarPVConfig(module_count=1000, module_power_wp=450.0),
            include_bess=False,
            bess_config=None
        )

        self.project.add_sub_scenario(self.sub1)
        self.project.add_sub_scenario(self.sub2)

    def test_remove_component_solar(self):
        """Test removing solar component from SubScenario."""
        self.assertTrue(self.sub1.include_solar)
        self.assertIsNotNone(self.sub1.solar_config)

        self.sub1.remove_component("solar")
        self.assertFalse(self.sub1.include_solar)
        self.assertIsNone(self.sub1.solar_config)
        self.assertIsNone(self.sub1.solar_financial)

        # BESS and Generator should remain intact
        self.assertTrue(self.sub1.include_bess)
        self.assertIsNotNone(self.sub1.bess_config)
        self.assertTrue(self.sub1.include_generator)

    def test_remove_component_bess(self):
        """Test removing BESS component from SubScenario."""
        self.assertTrue(self.sub1.include_bess)
        self.assertIsNotNone(self.sub1.bess_config)

        self.sub1.remove_component("bess")
        self.assertFalse(self.sub1.include_bess)
        self.assertIsNone(self.sub1.bess_config)

        # Solar should remain intact
        self.assertTrue(self.sub1.include_solar)

    def test_remove_component_all(self):
        """Test resetting all components from SubScenario."""
        self.sub1.remove_component("all")
        self.assertFalse(self.sub1.include_solar)
        self.assertIsNone(self.sub1.solar_config)
        self.assertFalse(self.sub1.include_bess)
        self.assertIsNone(self.sub1.bess_config)
        self.assertFalse(self.sub1.include_generator)
        self.assertIsNone(self.sub1.generator_config)
        self.assertEqual(self.sub1.technology_mix_label, "Grid Only (No Active Modules)")

    def test_project_container_remove_and_reset(self):
        """Test ProjectContainer delegation methods."""
        res = self.project.remove_sub_scenario_component("sub_1", "generator")
        self.assertTrue(res)
        self.assertFalse(self.sub1.include_generator)

        res_reset = self.project.reset_sub_scenario("sub_1")
        self.assertTrue(res_reset)
        self.assertFalse(self.sub1.include_solar)
        self.assertFalse(self.sub1.include_bess)

    def test_sync_preserves_and_restores_state_across_scenarios(self):
        """Test that switching between scenarios restores saved data and does not overwrite."""
        # Switch to sub 1
        self.project.active_sub_scenario_id = "sub_1"
        sync_active_scenario_into_session(self.project, auto_execute=False)

        self.assertIn("app_tab3_config", st.session_state)
        self.assertEqual(st.session_state["app_tab3_config"].module_count, 500)
        self.assertIn("app_tab4_bess_config", st.session_state)
        self.assertEqual(st.session_state["app_tab4_bess_config"].capacity_kwh, 200.0)

        # Switch to sub 2 (Solar only, no BESS)
        self.project.active_sub_scenario_id = "sub_2"
        sync_active_scenario_into_session(self.project, auto_execute=False)

        self.assertIn("app_tab3_config", st.session_state)
        self.assertEqual(st.session_state["app_tab3_config"].module_count, 1000)
        # BESS should be cleanly purged
        self.assertNotIn("app_tab4_bess_config", st.session_state)

        # Switch back to sub 1 -> Old input data must be restored intact!
        self.project.active_sub_scenario_id = "sub_1"
        sync_active_scenario_into_session(self.project, auto_execute=False)

        self.assertIn("app_tab3_config", st.session_state)
        self.assertEqual(st.session_state["app_tab3_config"].module_count, 500)
        self.assertIn("app_tab4_bess_config", st.session_state)
        self.assertEqual(st.session_state["app_tab4_bess_config"].capacity_kwh, 200.0)

    def test_new_scenario_starts_clean(self):
        """Test that creating a new blank sub-scenario starts clean."""
        new_sub = SubScenario(id="sub_new", name="New Empty Branch", include_solar=False, include_bess=False)
        self.project.add_sub_scenario(new_sub)
        self.project.active_sub_scenario_id = "sub_new"
        sync_active_scenario_into_session(self.project, auto_execute=False)

        # Both Solar and BESS must be unpopulated
        self.assertNotIn("app_tab3_config", st.session_state)
        self.assertNotIn("app_tab4_bess_config", st.session_state)
        self.assertNotIn("app_tab3_sim_result", st.session_state)
        self.assertNotIn("app_tab4_bess_sim_result", st.session_state)


if __name__ == "__main__":
    unittest.main()
