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

# Optional and robust imports from main application and sandbox modules
try:
    from current_model.ui.common.styles import apply_custom_styles
    from current_model.ui_sandbox.Currentsituation_sandbox.app import render_current_situation_sandbox
    from current_model.ui_sandbox.status_quo_2025.status_quo_lab import render_status_quo_lab
    from current_model.ui_sandbox.monthly_baseline_lab.standalone_monthly_baseline_lab import render_monthly_baseline_lab
    from current_model.ui_sandbox.three_party_contract_lab.minimal_contract_system import render_minimal_contract_system
except ImportError:
    try:
        from ui.common.styles import apply_custom_styles
        from ui_sandbox.Currentsituation_sandbox.app import render_current_situation_sandbox
        from ui_sandbox.status_quo_2025.status_quo_lab import render_status_quo_lab
        from ui_sandbox.monthly_baseline_lab.standalone_monthly_baseline_lab import render_monthly_baseline_lab
        from ui_sandbox.three_party_contract_lab.minimal_contract_system import render_minimal_contract_system
    except ImportError:
        try:
            from Currentsituation_sandbox.app import render_current_situation_sandbox
            from status_quo_2025.status_quo_lab import render_status_quo_lab
            from monthly_baseline_lab.standalone_monthly_baseline_lab import render_monthly_baseline_lab
            from three_party_contract_lab.minimal_contract_system import render_minimal_contract_system
            apply_custom_styles = None
        except ImportError:
            try:
                from minimal_contract_system import render_minimal_contract_system
                from standalone_monthly_baseline_lab import render_monthly_baseline_lab
                from status_quo_2025.status_quo_lab import render_status_quo_lab
                from Currentsituation_sandbox.app import render_current_situation_sandbox
                apply_custom_styles = None
            except ImportError:
                render_minimal_contract_system = None
                render_monthly_baseline_lab = None
                render_status_quo_lab = None
                render_current_situation_sandbox = None
                apply_custom_styles = None


def main():
    st.set_page_config(
        page_title="UI Sandbox & Tariff Laboratory",
        page_icon=":material/science:",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    if apply_custom_styles:
        apply_custom_styles()

    # Laboratory Selector Header
    st.markdown("### :material/science: UI Sandbox & Tariff Laboratory Suite")
    st.caption("Isolated experimentation environment with zero production risk for `app.py`.")

    lab_mode = st.radio(
        "Select Laboratory Module:",
        options=[
            ":material/analytics: Current Situation (Status Quo) Lab (Tab 1 & 2 Main Replicas)",
            ":material/account_balance: Status Quo 2025 Lab (Unbundled 3-Party & 4-Point Audit)",
            ":material/calendar_month: Monthly Baseline & Tariff Lab (Pozo 600 & Enexis)",
            ":material/bolt: 15-Minute Load Profile & Supply Contract Lab"
        ],
        horizontal=True,
        key="sandbox_suite_mode_selector"
    )

    st.markdown("---")

    if "Current Situation" in lab_mode:
        if render_current_situation_sandbox:
            render_current_situation_sandbox(key_prefix="suite_currsit_lab")
        else:
            st.error("Could not load `render_current_situation_sandbox`. Check import paths.", icon=":material/error:")
    elif "Status Quo 2025" in lab_mode:
        if render_status_quo_lab:
            render_status_quo_lab(key_prefix="suite_sq2025_lab")
        else:
            st.error("Could not load `render_status_quo_lab`. Check import paths.", icon=":material/error:")
    elif "Monthly Baseline" in lab_mode:
        if render_monthly_baseline_lab:
            render_monthly_baseline_lab(key_prefix="suite_monthly_lab")
        else:
            st.error("Could not load `render_monthly_baseline_lab`. Check import paths.", icon=":material/error:")
    else:
        if render_minimal_contract_system:
            render_minimal_contract_system(key_prefix="suite_contract_app")
        else:
            st.error("Could not load `render_minimal_contract_system`. Check import paths.", icon=":material/error:")


if __name__ == "__main__":
    main()
