"""
========================================================================================
Tab 1: Consumption Orchestrator (current_model/ui/tab1_consumption/view.py)
========================================================================================

Description:
------------
Main entry point for Tab 1 (Consumption), allowing the user to select between:
  1. Synthetic Load Simulator (24h / 365-Day)
  2. CSV Real Meter Data Visualizer
Synchronizes the active data source selection with Tab 2 for financial assessment.
"""

import streamlit as st
import pandas as pd
try:
    from ui_sandbox.Currentsituation_sandbox.consumption.synthetic.view import render_synthetic_simulator
    from ui_sandbox.Currentsituation_sandbox.consumption.csv_inspector.view import render_csv_inspector
except ImportError:
    try:
        from current_model.ui_sandbox.Currentsituation_sandbox.consumption.synthetic.view import render_synthetic_simulator
        from current_model.ui_sandbox.Currentsituation_sandbox.consumption.csv_inspector.view import render_csv_inspector
    except ImportError:
        try:
            from consumption.synthetic.view import render_synthetic_simulator
            from consumption.csv_inspector.view import render_csv_inspector
        except ImportError:
            from current_model.ui.tab1_consumption.synthetic.view import render_synthetic_simulator
            from current_model.ui.tab1_consumption.csv_inspector.view import render_csv_inspector


def render_tab1_consumption(key_prefix: str = "tab1") -> None:
    """
    Renders Tab 1: Consumption Profile Modeling & Ingestion.
    Keeps the active load source strictly synchronized across all scenarios and sessions.
    """
    active_source = st.session_state.get("tab1_active_source")
    if not active_source:
        if "active_csv_df" in st.session_state and isinstance(st.session_state["active_csv_df"], pd.DataFrame) and not st.session_state["active_csv_df"].empty:
            active_source = "csv"
        else:
            active_source = "synthetic"
        st.session_state["tab1_active_source"] = active_source

    options = [
        ":material/bolt: Synthetic Load Simulator (24h / 365-Day)",
        ":material/upload_file: CSV Real Meter Data Visualizer"
    ]
    default_idx = 1 if active_source == "csv" else 0

    radio_key = f"{key_prefix}_mode_radio"
    expected_choice = options[default_idx]
    # Ensure current radio widget key in session state matches canonical active_source
    if radio_key not in st.session_state or st.session_state[radio_key] not in options:
        st.session_state[radio_key] = expected_choice
    elif ("CSV" in str(st.session_state[radio_key])) != (active_source == "csv"):
        st.session_state[radio_key] = expected_choice

    def _on_mode_change() -> None:
        chosen = st.session_state.get(radio_key, "")
        st.session_state["tab1_active_source"] = "csv" if "CSV" in chosen else "synthetic"

    app_mode = st.radio(
        "Select Consumption Source:",
        options=options,
        index=default_idx,
        horizontal=True,
        key=radio_key,
        on_change=_on_mode_change
    )
    st.divider()

    if "CSV" in app_mode:
        st.session_state["tab1_active_source"] = "csv"
        render_csv_inspector(key_prefix=f"{key_prefix}_csv")
    else:
        st.session_state["tab1_active_source"] = "synthetic"
        render_synthetic_simulator(key_prefix=f"{key_prefix}_synthetic")
        # Ensure 2025 synthetic series is registered for Tab 2
        try:
            try:
                from ui_sandbox.status_quo_2025.consumption_pipeline import synthesize_benchmark_load_profile_2025
            except ImportError:
                from current_model.ui_sandbox.status_quo_2025.consumption_pipeline import synthesize_benchmark_load_profile_2025
            if "active_load_series_2025" not in st.session_state or st.session_state.get("last_synced_source") != "synthetic":
                st.session_state["active_load_series_2025"] = synthesize_benchmark_load_profile_2025(nominal_peak_kw=250.0)
                st.session_state["last_synced_source"] = "synthetic"
        except Exception:
            pass
