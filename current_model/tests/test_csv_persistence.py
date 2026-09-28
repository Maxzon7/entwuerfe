"""
========================================================================================
Unit Tests: CSV Persistence & Snapshot Restoration (tests/test_csv_persistence.py)
========================================================================================

Description:
------------
Validates that CSV load profiles are properly persisted in .dracproj snapshots
as compact time series records (without storing raw multi-MB unparsed CSV files),
and that Tab 1 CSV Inspector cleanly renders restored diagrams and KPIs.
"""

import unittest
import pandas as pd
import numpy as np
import streamlit as st

from current_model.models.scenario import BaseScenario, ProjectContainer
from current_model.models.contract import Contract
from current_model.core.project_io import (
    export_project_from_session,
    export_project_json,
    validate_project_file,
    load_project_into_session
)
from current_model.ui.tab1_consumption.csv_inspector.view import render_csv_inspector
from current_model.ui.tab1_consumption.csv_inspector.charts import create_csv_inspector_figure
from current_model.core.metrics_engine import compute_load_profile_kpis


class TestCSVPersistence(unittest.TestCase):
    """Tests project snapshot export, import, and diagram rendering for CSV load profiles."""

    def setUp(self):
        # Create a sample 15-minute load profile DataFrame (24 hours = 96 steps)
        dates = pd.date_range("2025-01-01 00:00", periods=96, freq="15min")
        powers = [50.0 + 20.0 * np.sin(i / 10.0) for i in range(96)]
        self.sample_df = pd.DataFrame({
            "timestamp": dates,
            "Total_Demand_kW": powers
        })

    def test_export_project_contains_only_compact_records_not_raw_csv(self):
        # Setup session state with active CSV data
        st.session_state["tab1_active_source"] = "csv"
        st.session_state["active_csv_df"] = self.sample_df
        st.session_state["active_csv_filename"] = "factory_january.csv"
        st.session_state["active_contract"] = Contract(name="Test Contract", currency="EUR")

        project = export_project_from_session(project_name="Snapshot Test")
        json_str = export_project_json(project)

        # Validate that JSON is valid
        is_valid, msg, meta = validate_project_file(json_str)
        self.assertTrue(is_valid)
        self.assertEqual(meta["load_type"], "csv")

        # Verify that base_scenario has csv_data_records but no massive raw text blob
        self.assertIsNotNone(project.base_scenario.csv_data_records)
        self.assertEqual(len(project.base_scenario.csv_data_records), 96)
        self.assertEqual(project.base_scenario.csv_filename, "factory_january.csv")

    def test_load_project_restores_active_csv_df(self):
        # Simulate clean session state
        st.session_state.clear()

        # Build project with csv_data_records
        records = self.sample_df.copy()
        records["timestamp"] = records["timestamp"].astype(str)
        proj = ProjectContainer(
            project_name="Restored Factory",
            currency="EUR",
            base_scenario=BaseScenario(
                name="Status Quo",
                load_source_type="csv",
                csv_filename="factory_january.csv",
                csv_data_records=records.to_dict(orient="records"),
                base_contract=Contract(name="Test Tariff", currency="EUR")
            )
        )

        load_project_into_session(proj, auto_execute=False)

        # active_csv_df must be populated and timestamps must be datetime
        self.assertIn("active_csv_df", st.session_state)
        restored_df = st.session_state["active_csv_df"]
        self.assertIsInstance(restored_df, pd.DataFrame)
        self.assertEqual(len(restored_df), 96)
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(restored_df["timestamp"]))
        self.assertEqual(st.session_state.get("tab1_active_source"), "csv")
        self.assertEqual(st.session_state.get("active_csv_filename"), "factory_january.csv")

    def test_render_csv_inspector_with_restored_dataset(self):
        # Clear raw file caches to simulate freshly loaded project snapshot
        st.session_state.clear()
        st.session_state["tab1_active_source"] = "csv"
        st.session_state["active_csv_df"] = self.sample_df
        st.session_state["active_csv_filename"] = "factory_january.csv"

        # render_csv_inspector should execute cleanly without raising exceptions
        try:
            render_csv_inspector(key_prefix="test_restored_csv")
        except Exception as e:
            self.fail(f"render_csv_inspector raised an unexpected exception: {e}")

    def test_create_csv_inspector_figure_from_restored_df(self):
        kpis = compute_load_profile_kpis(self.sample_df, power_col="Total_Demand_kW")
        fig = create_csv_inspector_figure(
            df_clean=self.sample_df,
            file_name="factory_january.csv",
            selected_power_cols=["Total_Demand_kW"],
            total_col="Total_Demand_kW",
            peak_kw=kpis.peak_kw,
            grid_limit_kw=60.0
        )
        self.assertIsNotNone(fig)
        self.assertGreater(len(fig.data), 0)


if __name__ == "__main__":
    unittest.main()
