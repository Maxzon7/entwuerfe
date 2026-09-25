"""
========================================================================================
Unit Tests: Project I/O and Persistence Engine (tests/test_project_io.py)
========================================================================================
"""

import unittest
import json
from current_model.models.scenario import BaseScenario, SubScenario, ProjectContainer
from current_model.models.contract import Contract
from current_model.models.solar import SolarLocation, SolarPVConfig
from current_model.models.load_component import SimpleConsumer
from current_model.core.project_io import (
    validate_project_file,
    export_project_json
)


class TestProjectIO(unittest.TestCase):
    """Tests for project serialization, validation, and deserialization routines."""

    def setUp(self):
        self.project = ProjectContainer(
            project_name="Test Persisted Facility",
            currency="EUR",
            base_scenario=BaseScenario(
                name="Status Quo",
                location=SolarLocation(name="Madrid", latitude=40.41, longitude=-3.70),
                base_contract=Contract(name="Madrid MV Tariff", contracted_capacity_kw=400.0)
            ),
            sub_scenarios=[
                SubScenario(
                    id="sub_test_pv",
                    name="Solar PV 500 kWp",
                    include_solar=True,
                    solar_config=SolarPVConfig(module_count=1111, module_power_wp=450.0)
                )
            ]
        )

    def test_project_json_export_and_validation(self):
        json_str = export_project_json(self.project)
        self.assertIsInstance(json_str, str)
        self.assertIn("drac_simulation_project", json_str)
        self.assertIn("Test Persisted Facility", json_str)

        # Validate with validator
        is_valid, msg, meta = validate_project_file(json_str)
        self.assertTrue(is_valid)
        self.assertEqual(meta["format"], "drac_simulation_project")
        self.assertEqual(meta["project_name"], "Test Persisted Facility")
        self.assertEqual(meta["sub_scenario_count"], 1)
        self.assertEqual(meta["currency"], "EUR")

    def test_modular_asset_validation(self):
        # Contract asset
        contract_data = {
            "format": "drac_contract",
            "name": "Industrial 500kW",
            "currency": "USD",
            "contracted_capacity_kw": 500.0
        }
        is_valid, msg, meta = validate_project_file(contract_data)
        self.assertTrue(is_valid)
        self.assertEqual(meta["format"], "drac_contract")
        self.assertEqual(meta["contract_name"], "Industrial 500kW")

        # Consumer profile asset
        load_data = {
            "format": "drac_load_profile",
            "profile_name": "Bakery Load Profile",
            "consumers": [{"name": "Oven 1"}, {"name": "Mixer"}]
        }
        is_valid, msg, meta = validate_project_file(load_data)
        self.assertTrue(is_valid)
        self.assertEqual(meta["format"], "drac_load_profile")
        self.assertEqual(meta["consumer_count"], 2)

    def test_sync_active_scenario_into_session_defer_simulation(self):
        import streamlit as st
        from current_model.core.project_io import sync_active_scenario_into_session

        # Select sub_test_pv
        self.project.active_sub_scenario_id = "sub_test_pv"
        sync_active_scenario_into_session(self.project, auto_execute=False)

        # Config must be populated in session state
        self.assertIn("app_tab3_config", st.session_state)
        self.assertEqual(st.session_state["app_tab3_config"].module_count, 1111)

        # Simulation result must NOT be calculated automatically
        self.assertNotIn("app_tab3_sim_result", st.session_state)
        self.assertNotIn("solar_kw_15min", st.session_state)

        # Widget selection keys must be properly synchronized
        self.assertEqual(st.session_state.get("sidebar_target_scenario_select"), "sub_test_pv")
        self.assertEqual(st.session_state.get("app_scenarios_target_scenario_select"), "sub_test_pv")

        # When switched to base (Status Quo), widget keys must synchronize to base
        self.project.active_sub_scenario_id = None
        sync_active_scenario_into_session(self.project, auto_execute=False)
        self.assertEqual(st.session_state.get("sidebar_target_scenario_select"), "base")
        self.assertEqual(st.session_state.get("app_scenarios_target_scenario_select"), "base")

    def test_load_project_with_string_timestamps_and_compute_bill(self):
        import streamlit as st
        import pandas as pd
        from current_model.core.project_io import load_project_into_session
        from current_model.core.financial_engine import compute_financial_bill

        # Simulate restored project with string timestamps in csv_data_records
        records = [
            {"timestamp": "2025-01-01 00:00:00", "Total_Demand_kW": 100.0},
            {"timestamp": "2025-01-01 00:15:00", "Total_Demand_kW": 120.0},
            {"timestamp": "2025-01-01 00:30:00", "Total_Demand_kW": 110.0},
            {"timestamp": "2025-01-01 00:45:00", "Total_Demand_kW": 90.0},
        ]
        self.project.base_scenario.csv_data_records = records
        self.project.base_scenario.load_source_type = "csv"

        load_project_into_session(self.project, auto_execute=False)

        # active_csv_df must have been parsed to datetime
        self.assertIn("active_csv_df", st.session_state)
        df_csv = st.session_state["active_csv_df"]
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(df_csv["timestamp"]))

        # Financial bill computation should not raise TypeError
        bill = compute_financial_bill(load_data=df_csv, contract=self.project.base_scenario.base_contract)
        self.assertIsNotNone(bill)
        self.assertGreater(bill.total_gross_period, 0.0)


if __name__ == "__main__":
    unittest.main()

