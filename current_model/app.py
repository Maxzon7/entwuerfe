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
from current_model.ui.tab1_consumption.view import render_tab1_consumption
from current_model.ui.tab2_contract.view import render_tab2_contract
from current_model.ui.tab3_solar.view import render_tab3_solar

# 1. Page Configuration & Styling
st.set_page_config(
    page_title="Energy Simulator & Load Profiler",
    page_icon="⚡",
    layout="wide"
)
apply_custom_styles()

st.title("Energy Simulator & Load Profile Analyzer")
st.caption("Modular platform for 24-Hour synthetic bottom-up load modeling, real-world CSV meter analysis, electricity contract tariffs, and Solar PV generation.")

# 2. Top-Level Tab Navigation (1:1 mapped to ui/tab1_..., ui/tab2_..., ui/tab3_...)
tab_consumption, tab_contract, tab_solar = st.tabs([
    "⚡ 1. Consumption",
    "📄 2. Contract Data",
    "☀️ 3. Solar PV Generation"
])

# TAB 1: Consumption
with tab_consumption:
    render_tab1_consumption(key_prefix="app_tab1")

# TAB 2: Contract Data
with tab_contract:
    render_tab2_contract(key_prefix="app_tab2")

# TAB 3: Solar PV Generation (Standalone Isolated Simulation)
with tab_solar:
    render_tab3_solar(key_prefix="app_tab3")

