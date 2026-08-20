"""
========================================================================================
Tab 1: Consumption Orchestrator (current_model/ui/tab1_consumption/view.py)
========================================================================================

Description:
------------
Main entry point for Tab 1 (Consumption), allowing the user to select between:
  1. ⚡ 24-Hour Synthetic Load Simulator
  2. 📁 CSV Real Meter Data Visualizer
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
            "⚡ 24-Hour Synthetic Load Simulator",
            "📁 CSV Real Meter Data Visualizer"
        ],
        horizontal=True,
        key=f"{key_prefix}_mode_radio"
    )
    st.divider()

    if app_mode == "⚡ 24-Hour Synthetic Load Simulator":
        render_synthetic_simulator(key_prefix=f"{key_prefix}_synthetic")
    else:
        render_csv_inspector(key_prefix=f"{key_prefix}_csv")
