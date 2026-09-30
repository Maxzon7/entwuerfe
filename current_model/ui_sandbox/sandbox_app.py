"""
========================================================================================
UI Sandbox & Simple Electricity Contract Lab (ui_sandbox/sandbox_app.py)
========================================================================================
Minimal, straightforward sandbox for evaluating electricity contracts against consumption CSV data.
Uses crystal-clear, plain English terms (e.g. 'Fee per reserved kW', 'Reserved grid power limit').
========================================================================================
"""

import os
import sys
import streamlit as st

# Ensure project root and current_model are on sys.path
SANDBOX_DIR = os.path.dirname(os.path.abspath(__file__))
CURRENT_MODEL_DIR = os.path.abspath(os.path.join(SANDBOX_DIR, ".."))
WORKSPACE_ROOT = os.path.abspath(os.path.join(CURRENT_MODEL_DIR, ".."))

for path in [WORKSPACE_ROOT, CURRENT_MODEL_DIR]:
    if path not in sys.path:
        sys.path.insert(0, path)

# Optional and robust imports from main application and sandbox module
try:
    from current_model.ui.common.styles import apply_custom_styles
    from current_model.ui_sandbox.minimal_contract_system import render_minimal_contract_system
except ImportError:
    try:
        from ui.common.styles import apply_custom_styles
        from ui_sandbox.minimal_contract_system import render_minimal_contract_system
    except ImportError:
        try:
            from minimal_contract_system import render_minimal_contract_system
            apply_custom_styles = None
        except ImportError:
            render_minimal_contract_system = None
            apply_custom_styles = None


def main():
    st.set_page_config(
        page_title="Simple Electricity Contract Lab",
        page_icon=":material/electric_meter:",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    if apply_custom_styles:
        apply_custom_styles()

    if render_minimal_contract_system:
        render_minimal_contract_system(key_prefix="sandbox_app")
    else:
        st.error("Could not load `minimal_contract_system`. Check import paths.", icon=":material/error:")


if __name__ == "__main__":
    main()
