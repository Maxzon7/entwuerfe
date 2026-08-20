# To Run: python -m streamlit run current_model/app.py

"""
========================================================================================
Energy Simulator & Load Profile Analyzer (current_model/app.py)
========================================================================================

Main application entry point structured in two top-level tabs:
  - Tab 1: ⚡ Consumption (Synthetic 24h simulation & CSV real meter visualizer)
  - Tab 2: 📄 Contract Data (Electricity supply contract & tariff configuration)
========================================================================================
"""

import sys
import os

# Ensure project root is in sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import streamlit as st
from current_model.ui.common.styles import apply_custom_styles
from current_model.ui.synthetic.view import render_synthetic_simulator
from current_model.ui.csv_inspector.view import render_csv_inspector
from current_model.ui.contract.form import render_contract_view

# 1. Page Configuration & Styling
st.set_page_config(
    page_title="Energy Simulator & Load Profiler",
    page_icon="⚡",
    layout="wide"
)
apply_custom_styles()

st.title("Energy Simulator & Load Profile Analyzer")
st.caption("Modular platform for 24-Hour synthetic bottom-up load modeling, real-world CSV meter analysis, and contract modeling.")

# 2. Top-Level Tab Navigation
tab_consumption, tab_contract = st.tabs(["⚡ Consumption", "📄 Contract Data"])

# ======================================================================================
# TAB 1: Consumption (Synthetic 24h Simulation vs CSV Real Meter Data)
# ======================================================================================
with tab_consumption:
    app_mode = st.radio(
        "Select Consumption Source:",
        options=[
            "⚡ 24-Hour Synthetic Load Simulator",
            "📁 CSV Real Meter Data Visualizer"
        ],
        horizontal=True
    )
    st.divider()

    if app_mode == "⚡ 24-Hour Synthetic Load Simulator":
        render_synthetic_simulator(key_prefix="app_synthetic")
    else:
        render_csv_inspector(key_prefix="app_csv")

# ======================================================================================
# TAB 2: Contract Data (Electricity Supply Contract & Tariffs)
# ======================================================================================
with tab_contract:
    render_contract_view(key_prefix="app_contract")
