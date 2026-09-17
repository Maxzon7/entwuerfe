"""
========================================================================================
Unit Tests: Contract Presets Loading & Session State Synchronization
(tests/test_contract_presets_loading.py)
========================================================================================
"""

import unittest
import streamlit as st
import pandas as pd

from current_model.models.contract import Contract, get_contract_presets
from current_model.ui.tab2_contract.form import _sync_contract_to_state, render_contract_form


class TestContractPresetsLoading(unittest.TestCase):
    """Tests loading presets and state synchronization in Tab 2."""

    def setUp(self):
        # Reset streamlit session state
        st.session_state.clear()

    def test_presets_exist_and_are_valid(self):
        presets = get_contract_presets()
        self.assertGreater(len(presets), 0)
        for name, contract in presets.items():
            self.assertIsInstance(contract, Contract)
            self.assertTrue(bool(contract.name))
            self.assertGreater(contract.contracted_capacity_kw, 0)
            self.assertGreater(len(contract.tou_rates), 0)

    def test_sync_contract_to_state(self):
        presets = get_contract_presets()
        paula = presets["Paula1 (Bodegas Salentein - EDEMSA T2 R MT)"]
        key_prefix = "app_tab2"

        # Pre-populate session state with old editor state
        st.session_state[f"{key_prefix}_tou_editor"] = {"dummy": 1}
        st.session_state[f"{key_prefix}_taxes_editor"] = {"dummy": 2}

        _sync_contract_to_state(paula, key_prefix=key_prefix)

        # Check model and labels
        self.assertEqual(st.session_state[f"{key_prefix}_contract_model"], paula)
        self.assertEqual(st.session_state[f"{key_prefix}_active_contract_label"], "Paula1")
        self.assertEqual(st.session_state["active_contract"], paula)

        # Check dataframes
        tou_df = st.session_state[f"{key_prefix}_tou_rates_df"]
        self.assertIsInstance(tou_df, pd.DataFrame)
        self.assertEqual(len(tou_df), len(paula.tou_rates))

        taxes_df = st.session_state[f"{key_prefix}_taxes_df"]
        self.assertIsInstance(taxes_df, pd.DataFrame)
        self.assertEqual(len(taxes_df), len(paula.taxes_and_fees))

        # Check that editor keys were cleared
        self.assertNotIn(f"{key_prefix}_tou_editor", st.session_state)
        self.assertNotIn(f"{key_prefix}_taxes_editor", st.session_state)

    def test_switch_between_multiple_presets(self):
        presets = get_contract_presets()
        key_prefix = "app_tab2"

        p1 = presets["Paula1 (Bodegas Salentein - EDEMSA T2 R MT)"]
        p2 = presets["Industrial Multi-Tariff (EUR)"]

        # Apply P1
        _sync_contract_to_state(p1, key_prefix=key_prefix)
        self.assertEqual(st.session_state[f"{key_prefix}_contract_model"].currency, "ARS")
        self.assertEqual(st.session_state[f"{key_prefix}_active_contract_label"], "Paula1")

        # Apply P2
        _sync_contract_to_state(p2, key_prefix=key_prefix)
        self.assertEqual(st.session_state[f"{key_prefix}_contract_model"].currency, "EUR")
        self.assertEqual(st.session_state[f"{key_prefix}_active_contract_label"], "Industrial Multi-Tariff Contract")
        self.assertEqual(st.session_state[f"{key_prefix}_contract_model"].name, "Industrial Multi-Tariff Contract")


if __name__ == "__main__":
    unittest.main()
