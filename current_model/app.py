# To Run: python -m streamlit run current_model/app.py
# Updated: 2026-09-07 17:36 - Solar PV Sizing & Reactive Form Synchronization

"""
========================================================================================
Energy Simulator & Load Profile Analyzer (current_model/app.py)
========================================================================================

Main application entry point structured in three top-level tabs:
  - Tab 1: Consumption (Synthetic 24h / 365d simulation & CSV real meter visualizer)
  - Tab 2: Contract Data (Electricity supply contract & tariff configuration)
  - Tab 3: Solar PV Generation (Standalone PV simulation & Load Integration)
========================================================================================
"""

import sys
import os

# Ensure both current_model and parent directory are in sys.path
current_dir = os.path.abspath(os.path.dirname(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, ".."))
for p in [current_dir, parent_dir]:
    if p not in sys.path:
        sys.path.insert(0, p)

import streamlit as st
from current_model.ui.common.styles import apply_custom_styles
from current_model.ui.tab1_consumption.view import render_tab1_consumption
from current_model.ui.tab2_contract.view import render_tab2_contract
from current_model.ui.tab3_solar.view import render_tab3_solar
from current_model.ui.tab_comparison.view import render_master_comparison_dashboard
from current_model.ui.common.sidebar_scenario_view import render_sidebar_scenario_controller

# 1. Page Configuration & Styling
st.set_page_config(
    page_title="Energy Simulator & Load Profiler (DRACBV)",
    layout="wide"
)
apply_custom_styles()

# --------------------------------------------------------------------------
# 2. Sidebar: Multi-Scenario & Persistence Controller
# --------------------------------------------------------------------------
with st.sidebar:
    render_sidebar_scenario_controller()

# --------------------------------------------------------------------------
# 3. Main Header & Active Project Indicator
# --------------------------------------------------------------------------
active_project_name = st.session_state.get("active_project_name", "Energy Transition & Optimization Project")
st.title(":material/bolt: Energy Simulator & Multi-Scenario Decision Platform")
st.caption(f":material/folder_open: **Active Workspace Project:** {active_project_name} | Parametric 15-minute dispatch, electricity contract tariffs, and solar & storage investment assessment.")

# --------------------------------------------------------------------------
# 4. Top-Level Tab Navigation
# --------------------------------------------------------------------------
tab_consumption, tab_contract, tab_solar, tab_comparison = st.tabs([
    ":material/analytics: 1. Consumption",
    ":material/description: 2. Contract Data",
    ":material/solar_power: 3. Solar PV Generation",
    ":material/leaderboard: 4. Master Scenario Comparison & Ranking"
])

# TAB 1: Consumption
with tab_consumption:
    render_tab1_consumption(key_prefix="app_tab1")

# TAB 2: Contract Data
with tab_contract:
    render_tab2_contract(key_prefix="app_tab2")

# TAB 3: Solar PV Generation
with tab_solar:
    render_tab3_solar(key_prefix="app_tab3")

# TAB 4: Master Scenario Comparison & Decision Dashboard
with tab_comparison:
    render_master_comparison_dashboard(key_prefix="app_tab4")
