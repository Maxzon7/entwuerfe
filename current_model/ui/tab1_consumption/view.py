"""
========================================================================================
Tab 1: Consumption Orchestrator (current_model/ui/tab1_consumption/view.py)
========================================================================================

Description:
------------
Main entry point for Tab 1 (Consumption), allowing the user to select between:
  1. ⚡ 24-Hour / 365-Day Synthetic Load Simulator
  2. 📁 CSV Real Meter Data Visualizer
Synchronizes the active data source selection with Tab 2 for financial assessment.
"""

import streamlit as st
from current_model.ui.tab1_consumption.synthetic.view import render_synthetic_simulator
from current_model.ui.tab1_consumption.csv_inspector.view import render_csv_inspector


def render_tab1_consumption(key_prefix: str = "tab1") -> None:
    """
    Renders Tab 1: Consumption Profile Modeling & Ingestion.
    """
    app_mode = st.radio(
        "Select Consumption Source:",
        options=[
            "⚡ Synthetic Load Simulator (24h / 365-Day)",
            "📁 CSV Real Meter Data Visualizer"
        ],
        horizontal=True,
        key=f"{key_prefix}_mode_radio"
    )
    st.divider()

    if "CSV" in app_mode:
        st.session_state["tab1_active_source"] = "csv"
        render_csv_inspector(key_prefix=f"{key_prefix}_csv")
    else:
        st.session_state["tab1_active_source"] = "synthetic"
        render_synthetic_simulator(key_prefix=f"{key_prefix}_synthetic")
