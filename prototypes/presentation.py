# To Run: python -m streamlit run prototypes/presentation.py

"""
========================================================================================
PRESENTATION & TESTING PLAYGROUND (prototypes/presentation.py)
========================================================================================
A lightweight sandbox orchestrator delegating directly to current_model tabs:
  - Tab 1: ⚡ Consumption
  - Tab 2: 📄 Contract Data
========================================================================================
"""

import os
import sys
import streamlit as st

# Ensure project root directory is at the front of sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from current_model.ui.common.styles import apply_custom_styles
from current_model.ui.tab1_consumption.view import render_tab1_consumption
from current_model.ui.tab2_contract.view import render_tab2_contract

# 1. Page Configuration & Styling
st.set_page_config(
    page_title="Energy Simulator - Sandbox",
    page_icon="🧪",
    layout="wide"
)
apply_custom_styles()

st.title("Presentation & Testing Playground")
st.caption("Standalone sandbox for inspecting real CSV meter data, simulating synthetic loads, and contract tariff modeling.")

# 2. Top-Level Tab Navigation
tab_consumption, tab_contract = st.tabs(["⚡ 1. Consumption", "📄 2. Contract Data"])

# TAB 1: Consumption
with tab_consumption:
    render_tab1_consumption(key_prefix="presentation_tab1")

# TAB 2: Contract Data
with tab_contract:
    render_tab2_contract(key_prefix="presentation_tab2")
