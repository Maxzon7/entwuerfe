# To Run: python -m streamlit run current_model/app.py

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
from current_model.core.demo_scenario import (
    load_example1_scenario,
    clear_demo_scenario,
    get_active_model_summary
)

# 1. Page Configuration & Styling
st.set_page_config(
    page_title="Energy Simulator & Load Profiler",
    layout="wide"
)
apply_custom_styles()

# --------------------------------------------------------------------------
# 2. Sidebar: Scenario & Active Model Control
# --------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### Scenario & Model Control")
    st.caption("Toggle preconfigured end-to-end benchmark scenarios across all application tabs.")

    is_example1_active = bool(st.session_state.get("example1_active", False))

    # Toggle switch for Example 1
    toggle_val = st.toggle(
        "Activate **Example1** (European Benchmark)",
        value=is_example1_active,
        key="sidebar_example1_toggle",
        help="Loads the cohesive European commercial facility benchmark (Seville, Spain | EUR) across all tabs."
    )

    # Detect state change from toggle
    if toggle_val and not is_example1_active:
        load_example1_scenario()
        st.rerun()
    elif not toggle_val and is_example1_active:
        clear_demo_scenario()
        st.rerun()

    st.divider()

    # Active Model State Inspector
    st.markdown("#### Current Active Model")
    summary = get_active_model_summary()

    if summary["is_example1"]:
        st.success("**Example1: Active**\n\n*European Commercial Benchmark*")
        st.markdown(
            """
            * **Location:** Seville, Spain (EUR)
            * **Load (Tab 1):** 365-Day Commercial (~1,120 MWh/a, 395 kW peak)
            * **Contract (Tab 2):** 400 kW Multi-Tariff (3 TOU Tiers)
            * **Solar (Tab 3.1):** 696.6 kWp TOPCon (590 kW AC, 180° South)
            * **Integration (Tab 3.2):** ~62% Self-Consumption, ~65% Autarky
            """
        )
        if st.button("Reset All Tabs", key="sidebar_reset_btn", use_container_width=True):
            clear_demo_scenario()
            st.rerun()
    else:
        st.info("**Custom / User Defined**")
        c_label = f"{summary['contract_name']} ({summary['contract_currency']})" if summary['has_contract'] else "Unconfigured"
        s_label = f"{summary['solar_kwp']:.1f} kWp ({summary['solar_location']})" if summary['has_solar'] else "Unconfigured"
        st.markdown(
            f"""
            * **Tab 1 Load:** {summary['load_desc']}
            * **Tab 2 Contract:** {c_label}
            * **Tab 3 Solar:** {s_label}
            """
        )
        if st.button("Load Example1 Scenario", key="sidebar_quick_load_btn", use_container_width=True, type="primary"):
            load_example1_scenario()
            st.rerun()

# --------------------------------------------------------------------------
# 3. Main Header & Scenario Notification Banner
# --------------------------------------------------------------------------
st.title("Energy Simulator & Load Profile Analyzer")
st.caption("Modular platform for 24-Hour / 365-Day synthetic load modeling, real-world CSV meter analysis, electricity contract tariffs, and Solar PV generation.")

if is_example1_active:
    st.info(
        "💡 **Active Demo Scenario: Example 1 (European Commercial Benchmark - Seville, Spain | EUR)** — "
        "A cohesive profile is active across Tab 1 (Consumption), Tab 2 (Contract Data), and Tab 3 (Solar PV & Integration). "
        "You can toggle or inspect this scenario anytime in the sidebar."
    )

# --------------------------------------------------------------------------
# 4. Top-Level Tab Navigation
# --------------------------------------------------------------------------
tab_consumption, tab_contract, tab_solar = st.tabs([
    "1. Consumption",
    "2. Contract Data",
    "3. Solar PV Generation"
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
