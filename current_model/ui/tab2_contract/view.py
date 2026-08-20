"""
========================================================================================
Tab 2: Contract Data Orchestrator (current_model/ui/tab2_contract/view.py)
========================================================================================

Description:
------------
Main entry point for Tab 2 (Contract Data) rendering:
  - Caution / Guidance warning
  - Electricity supply contract & dynamic tariff configuration form
"""

import streamlit as st
from current_model.models.contract import Contract
from current_model.ui.tab2_contract.form import render_contract_form


def render_tab2_contract(key_prefix: str = "tab2") -> Contract:
    """
    Renders Tab 2: Electricity Supply Contract & Tariff Configuration.
    """
    st.warning("⚠️ Should you wish to not use a contract, leave the fields empty.")
    return render_contract_form(as_expander=False, key_prefix=key_prefix)
