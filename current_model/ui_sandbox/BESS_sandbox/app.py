# to run: python -m streamlit run "ui_sandbox/BESS_sandbox/app.py"

"""
========================================================================================
BESS Peak Shaving & 15-Year Life-Cycle TCO Sandbox App
ui_sandbox/BESS_sandbox/app.py
========================================================================================

Description:
------------
Standalone, high-precision Battery Energy Storage System (BESS) optimization laboratory:
  1. Technical Peak Shaving Feasibility & Interval Dispatch
     - 15-minute dispatch simulation, safe SoC envelopes, C-rate adherence,
       gross nameplate sizing recommendations, and 100% overload elimination verification.
  2. Financial Viability & 15-Year Life-Cycle TCO
     - Avoided grid upgrade CAPEX & transformer rental vs. BESS turnkey investment,
       unbundled bill reductions (kW-max demand + GTV capacity tariffs), dynamic degradation,
       OPEX, conversion loss costs, NPV, IRR, and payback.
  3. Sizing Optimizer & Multi-Parameter Sensitivity
     - Parametric capacity sweep across strategic size multiples, minimum feasible
       vs. maximum economic NPV sizing, and sensitivity tornado charts.
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
from ui_sandbox.BESS_sandbox import sandbox_bess_engine as engine
from ui_sandbox.BESS_sandbox.view_technical import render_technical_feasibility_tab
from ui_sandbox.BESS_sandbox.view_financial import render_financial_viability_tab
from ui_sandbox.BESS_sandbox.view_optimizer import render_optimizer_tab


def render_bess_sandbox(key_prefix: str = "bess_sb") -> None:
    """
    Renders the complete BESS Peak Shaving & 15-Year TCO sandbox workbench.
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
                f"**Scenario:** {active_preset.title}\n\n"
                f"Grid Cap: `{active_preset.grid_limit_kw:.0f} kW` | Avoided Upgrade: `€{active_preset.avoided_grid_upgrade_capex:,.0f}`",
                icon=":material/factory:"
            )
        elif "Case 2" in selected_option:
            active_preset = presets.get_case2_enexis_commercial_preset()
            st.info(
                f"**Scenario:** {active_preset.title}\n\n"
                f"Grid Cap: `{active_preset.grid_limit_kw:.0f} kW` | Avoided Upgrade: `€{active_preset.avoided_grid_upgrade_capex:,.0f}`",
                icon=":material/business:"
            )
        else:
            # Custom Profile
            if has_sandbox_csv:
                st.success(
                    f"**Connected to Current Situation Sandbox:** Using `{len(active_csv_df):,}` 15-minute load rows.",
                    icon=":material/link:"
                )
                custom_df = active_csv_df
            else:
                st.warning("No CSV detected in Current Situation Sandbox. Upload a 15-min CSV below.", icon=":material/upload_file:")
                uploaded = st.file_uploader("Upload 15-Min Load CSV", type=["csv"], key=f"{key_prefix}_csv_up")
                if uploaded is not None:
                    try:
                        custom_df = pd.read_csv(uploaded)
                        st.session_state["active_csv_df"] = custom_df
                        st.session_state["active_csv_filename"] = uploaded.name
                        st.rerun()
                    except Exception as ex:
                        st.error(f"Error parsing uploaded CSV: {ex}")
                        custom_df = None
                else:
                    custom_df = None

            if custom_df is not None:
                active_preset = presets.build_custom_comparison_preset(custom_df, grid_limit_kw=150.0)
            else:
                # Fallback to Case 1
                active_preset = presets.get_case1_liander_industrial_preset()

    with col_p3:
        st.markdown("**Session Actions:**")
        if st.button(":material/restart_alt: Reset Form", use_container_width=True, key=f"{key_prefix}_reset"):
            for k in list(st.session_state.keys()):
                if k.startswith("bess_sb"):
                    st.session_state.pop(k, None)
            st.rerun()

    st.markdown("---")

    # --- 3 Navigation Tabs ---
    tabs = st.tabs([
        ":material/speed: 1. Peak Shaving & Dispatch (Technical)",
        ":material/account_balance: 2. Financial Viability & 15Y TCO (Economics)",
        ":material/precision_manufacturing: 3. Sizing Optimizer & Sensitivity (Parametric)"
    ])

    with tabs[0]:
        sim_result = render_technical_feasibility_tab(active_preset)

    with tabs[1]:
        # Use active sim_result from Tab 1 or fallback
        cur_sim = st.session_state.get("bess_sb_sim_result", sim_result)
        fin_metrics = render_financial_viability_tab(active_preset, cur_sim)

    with tabs[2]:
        cur_cfg = st.session_state.get("bess_sb_active_config", active_preset.bess_config)
        cur_sim = st.session_state.get("bess_sb_sim_result", sim_result)
        render_optimizer_tab(active_preset, cur_cfg, cur_sim)


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
