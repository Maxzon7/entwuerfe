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
from current_model.ui.tab_comparison.view import render_scenario_management
from current_model.ui.tab1_consumption.view import render_tab1_consumption
from current_model.ui.tab2_contract.view import render_tab2_base_contract, render_tab2_contract_switch
from current_model.ui.tab3_solar.view import render_tab3_solar
from current_model.ui.tab4_bess.view import render_tab4_bess
from current_model.ui.tab_generator.view import render_tab_generator
from current_model.ui.tab_dracbv_beta.view import render_tab_dracbv_beta
from current_model.ui.tab_hybrid_beta.view import render_tab_solar_bess_beta
from current_model.ui.common.sidebar_scenario_view import render_sidebar_scenario_controller
from current_model.core.project_io import export_project_from_session

from current_model.ui.common.cards import render_active_scenario_banner

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

hdr_col1, hdr_col2 = st.columns([8.5, 1.5])
with hdr_col1:
    st.title(":material/bolt: Energy Simulator & Multi-Scenario Decision Platform")
    st.caption(f":material/folder_open: **Active Workspace Project:** {active_project_name} | Parametric 15-minute dispatch, electricity contract tariffs, and solar & storage investment assessment.")
with hdr_col2:
    st.markdown("<div style='height: 18px;'></div>", unsafe_allow_html=True)
    if st.button(":material/refresh: Reload App", use_container_width=True, help="Force a complete reload of the application and recalculations."):
        st.rerun()

# Active Scenario Banner Indicator
render_active_scenario_banner()

# --------------------------------------------------------------------------
# 4. Top-Level Tab Navigation (Dynamic Scenario-Centric Architecture)
# --------------------------------------------------------------------------
project = export_project_from_session()
active_sub = project.get_active_scenario()

# 4.1 Assemble Base Navigation Tabs
nav_tabs = [
    (":material/dashboard: 1. Scenario Management", lambda: render_scenario_management(key_prefix="app_scenarios")),
    (":material/analytics: 2. Consumption (Baseline)", lambda: render_tab1_consumption(key_prefix="app_tab1")),
    (":material/description: 3. Current Contract (Status Quo)", lambda: render_tab2_base_contract(key_prefix="app_tab2")),
    (":material/science: 4. DRACBV Simulator (Beta)", lambda: render_tab_dracbv_beta(key_prefix="app_dracbv_beta")),
    (":material/science: 5. Solar + BESS (Beta)", lambda: render_tab_solar_bess_beta(key_prefix="app_solar_bess_beta"))
]

# 4.2 Append Dynamic Solution Module Tabs Strictly Based on Active Sub-Scenario Configuration
if active_sub is not None:
    if active_sub.include_solar:
        nav_tabs.append((":material/solar_power: Solar PV Generation", lambda: render_tab3_solar(key_prefix="app_tab3")))
    if active_sub.include_bess:
        nav_tabs.append((":material/battery_charging_full: Battery Storage (BESS)", lambda: render_tab4_bess(key_prefix="app_tab4_bess")))
    if active_sub.include_generator:
        nav_tabs.append((":material/local_gas_station: Generator / Genset", lambda: render_tab_generator(key_prefix="app_tab_generator")))
    if active_sub.use_custom_grid_tariff:
        nav_tabs.append((":material/swap_horiz: Tariff Switch / Alternative Contract", lambda: render_tab2_contract_switch(key_prefix="app_contract_switch")))

# 4.3 Render Tabs Dynamically
tab_titles = [title for title, _ in nav_tabs]
rendered_tabs = st.tabs(tab_titles)

for tab_element, (_, render_fn) in zip(rendered_tabs, nav_tabs):
    with tab_element:
        render_fn()

