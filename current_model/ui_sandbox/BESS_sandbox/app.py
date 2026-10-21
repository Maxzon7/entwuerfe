# to run: python -m streamlit run "ui_sandbox/BESS_sandbox/app.py"

"""
========================================================================================
BESS Peak Shaving & 15-Year Life-Cycle TCO Sandbox App
ui_sandbox/BESS_sandbox/app.py
========================================================================================

Description:
------------
Streamlined 3-tab BESS engineering and commercial decision platform:
  1. Tab 1: Current Situation (The Problem)
     - Unmitigated facility demand vs. contracted grid connection limit.
     - Overload diagnostics and single high-contrast exceedance preview chart.
  2. Tab 2: BESS Peak Shaving (The Solution)
     - Modular sizing form with automated gross nameplate recommendations.
     - 100% feasibility verdict and strictly 2 operational charts (15-min timeseries + SoC).
  3. Tab 3: Financial Comparison & 15Y TCO (The Economics)
     - Avoided grid upgrade CAPEX & transformer rent vs. BESS turnkey investment.
     - 6 executive KPI cards, itemized Year-1 table, and 2 life-cycle trajectory curves.
"""

import os
import sys
from typing import Optional

# Path bootstrapping
CURRENT_DIR = os.path.abspath(os.path.dirname(__file__))
UI_SANDBOX_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
CURRENT_MODEL_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
WORKSPACE_DIR = os.path.abspath(os.path.join(CURRENT_MODEL_DIR, ".."))
for p in [CURRENT_DIR, UI_SANDBOX_DIR, CURRENT_MODEL_DIR, WORKSPACE_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

import streamlit as st
import pandas as pd

# Styling & Common Components
try:
    from current_model.ui.common.styles import apply_custom_styles
except ImportError:
    try:
        from ui.common.styles import apply_custom_styles
    except ImportError:
        apply_custom_styles = None

from ui_sandbox.BESS_sandbox import baseline_presets as presets
from ui_sandbox.BESS_sandbox.view_problem import render_problem_baseline_tab
from ui_sandbox.BESS_sandbox.view_technical import render_technical_feasibility_tab
from ui_sandbox.BESS_sandbox.view_financial import render_financial_viability_tab


def render_bess_sandbox(key_prefix: str = "bess_sb") -> None:
    """
    Renders the streamlined 3-tab BESS Peak Shaving & 15-Year TCO sandbox workbench.
    """
    st.markdown("## :material/battery_charging_full: BESS Peak Shaving & 15-Year TCO Sandbox")
    st.caption(
        "Isolated engineering and financial laboratory to test battery peak shaving feasibility, "
        "gross modular sizing, and life-cycle economics against avoided utility grid upgrade costs."
    )

    # --- Top Control Bar: Active Preset & Load Profile Selection ---
    active_csv_df = st.session_state.get("active_csv_df")
    has_sandbox_csv = isinstance(active_csv_df, pd.DataFrame) and not active_csv_df.empty

    col_p1, col_p2, col_p3 = st.columns([3, 2, 1])

    with col_p1:
        preset_options = [
            "Case 1: Liander AC4b vs. AC5a Upgrade (Industrial 350 kW)",
            "Case 2: Enexis MS-D Commercial (250 kW Peak vs. 150 kW Cap)",
            "Custom Profile (Upload CSV or Current Situation Sandbox)"
        ]
        selected_option = st.selectbox(
            "Benchmark Comparison Scenario / Preset",
            options=preset_options,
            index=st.session_state.get(f"{key_prefix}_preset_idx", 0),
            key=f"{key_prefix}_preset_select"
        )

    with col_p2:
        if "Case 1" in selected_option:
            active_preset = presets.get_case1_liander_industrial_preset()
            st.info(
                f"**Benchmark Profile:** {active_preset.title}\n\n"
                f"Peak Demand: `350 kW` | Contracted Grid Limit: `{active_preset.grid_limit_kw:.0f} kW`",
                icon=":material/factory:"
            )
        elif "Case 2" in selected_option:
            active_preset = presets.get_case2_enexis_commercial_preset()
            st.info(
                f"**Benchmark Profile:** {active_preset.title}\n\n"
                f"Peak Demand: `250 kW` | Contracted Grid Limit: `{active_preset.grid_limit_kw:.0f} kW`",
                icon=":material/business:"
            )
        else:
            # Custom Profile
            custom_df = st.session_state.get("bess_sb_custom_df")
            if custom_df is None and has_sandbox_csv:
                custom_df = active_csv_df

            if custom_df is not None:
                st.success(
                    f"**Active Custom Load Profile:** `{len(custom_df):,}` 15-minute intervals loaded.",
                    icon=":material/data_object:"
                )
                active_preset = presets.build_custom_comparison_preset(custom_df, grid_limit_kw=150.0)
            else:
                st.info(
                    "**Custom Ingestion Mode:** Use Tab 1 below to upload and configure your 15-min CSV load profile.",
                    icon=":material/upload_file:"
                )
                active_preset = presets.get_case1_liander_industrial_preset()

        # Auto-synchronize grid limit and reset hardware overrides if preset changes
        prev_preset_key = f"{key_prefix}_prev_selected_option"
        if st.session_state.get(prev_preset_key) != selected_option:
            st.session_state[prev_preset_key] = selected_option
            st.session_state[f"{key_prefix}_grid_limit_kw"] = float(active_preset.grid_limit_kw)
            for tech_key in ["unit_count", "unit_kwh", "discharge_kw", "charge_kw"]:
                st.session_state.pop(f"{key_prefix}_{tech_key}", None)

    with col_p3:
        st.markdown("**Session Actions:**")
        if st.button(":material/restart_alt: Reset Form", use_container_width=True, key=f"{key_prefix}_reset"):
            for k in list(st.session_state.keys()):
                if k.startswith("bess_sb"):
                    st.session_state.pop(k, None)
            st.rerun()

    st.markdown("---")

    # --- 2 Physics & Feasibility Tabs ---
    tabs = st.tabs([
        ":material/warning: 1. Current Situation & Load Ingestion (The Problem)",
        ":material/battery_charging_full: 2. BESS Sizing & Excel Validation (The Solution)"
    ])

    with tabs[0]:
        active_limit_kw = render_problem_baseline_tab(active_preset)

    with tabs[1]:
        sim_result = render_technical_feasibility_tab(active_preset, grid_limit_kw=active_limit_kw)


def main() -> None:
    """Standalone page entrypoint."""
    st.set_page_config(
        page_title="BESS Peak Shaving & 15-Year TCO Sandbox",
        page_icon=":material/battery_charging_full:",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    if apply_custom_styles:
        apply_custom_styles()
    render_bess_sandbox()


if __name__ == "__main__":
    main()
