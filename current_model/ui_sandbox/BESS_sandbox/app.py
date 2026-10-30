# to run: python -m streamlit run "ui_sandbox/BESS_sandbox/app.py"

"""
========================================================================================
BESS Peak Shaving & 15-Year Life-Cycle TCO Sandbox App
ui_sandbox/BESS_sandbox/app.py
========================================================================================

Description:
------------
Streamlined BESS engineering and commercial decision platform:
  1. Tab 1: Current Situation & Load Ingestion
     - Unmitigated facility demand vs. contracted grid connection limit.
     - Overload diagnostics and single high-contrast exceedance preview chart.
  2. Tab 2: BESS Sizing & Excel Validation
     - Modular sizing form with automated gross nameplate recommendations.
     - 100% feasibility verdict, simultaneous bottleneck checklist, and synchronized Plotly subplot.
  3. Tab 3: Baseline vs. BESS Bill & Profile Comparison
     - Side-by-side comparison of grid demand profile (`P_Load_kW` vs `P_Grid_kW`), remaining peaks,
       battery SoC, and itemized 4-Pillar electricity bills (with PDF Report export).
  4. Tab 4: Financial Comparison & 15Y TCO
     - Avoided grid upgrade CAPEX & transformer rent vs. BESS turnkey investment.
========================================================================================
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
from ui_sandbox.BESS_sandbox.view_bill_comparison import (
    render_bill_and_profile_comparison_tab,
    build_4pillar_configs_for_preset,
)
from ui_sandbox.BESS_sandbox.view_financial import render_financial_viability_tab

try:
    from ui_sandbox.Currentsituation_sandbox.engine.consumption_pipeline import (
        normalize_load_profile_2025,
    )
    from ui_sandbox.Currentsituation_sandbox.contract.assumptions_banner import (
        build_assumptions_register_dict,
        render_assumptions_banner,
    )
except ImportError:
    from current_model.ui_sandbox.Currentsituation_sandbox.engine.consumption_pipeline import (
        normalize_load_profile_2025,
    )
    from current_model.ui_sandbox.Currentsituation_sandbox.contract.assumptions_banner import (
        build_assumptions_register_dict,
        render_assumptions_banner,
    )


def render_bess_sandbox(key_prefix: str = "bess_sb") -> None:
    """
    Renders the 4-tab BESS Peak Shaving, Bill Comparison & 15-Year TCO sandbox workbench.
    """
    st.markdown("## :material/battery_charging_full: BESS Peak Shaving, Bill Comparison & 15-Year TCO Sandbox")
    st.caption(
        "Isolated engineering and commercial laboratory to test battery peak shaving feasibility, "
        "gross modular sizing, side-by-side 4-Pillar electricity bill savings, and 15-year life-cycle economics."
    )

    # --- Top Control Bar: Active Preset & Load Profile Selection ---
    active_csv_df = st.session_state.get("active_csv_df")
    has_sandbox_csv = isinstance(active_csv_df, pd.DataFrame) and not active_csv_df.empty

    col_p1, col_p2, col_p3 = st.columns([3, 2, 1])

    with col_p1:
        preset_options = [
            "Case 3: Rotterdam / Paula Dutch Site (Stedin 28-Day WKO / 110 kW Limit)",
            "Case 4: EDEMSA Mendoza T2 RMT (Bodegas Salentein - 430 kW Limit)",
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
        if "Case 3" in selected_option or "Rotterdam" in selected_option:
            active_preset = presets.get_case3_paula_dutch_site_preset()
            st.info(
                f"**Benchmark Profile:** {active_preset.title}\n\n"
                f"Peak Demand: `131.4 kW` | Contracted Grid Limit: `{active_preset.grid_limit_kw:.0f} kW` | Overload: `+21.4 kW`",
                icon=":material/heat_pump:"
            )
        elif "Case 4" in selected_option or "EDEMSA" in selected_option:
            active_preset = presets.get_case4_edemsa_salentein_preset()
            st.info(
                f"**Benchmark Profile:** {active_preset.title}\n\n"
                f"Peak Demand: `691.0 kW` | Contracted Grid Limit: `{active_preset.grid_limit_kw:.0f} kW` | Exceso: `+261.0 kW`",
                icon=":material/wine_bar:"
            )
        elif "Case 1" in selected_option:
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
                cur_limit = float(st.session_state.get(f"{key_prefix}_grid_limit_kw", 150.0))
                active_preset = presets.build_custom_comparison_preset(custom_df, grid_limit_kw=cur_limit)
            else:
                st.info(
                    "**Custom Ingestion Mode:** Use Tab 1 below to upload and configure your 15-min CSV load profile.",
                    icon=":material/upload_file:"
                )
                active_preset = presets.get_case3_paula_dutch_site_preset()

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
            st.session_state.pop("active_csv_df", None)
            st.session_state.pop("active_csv_filename", None)
            st.rerun()

    assumptions_banner_container = st.container()
    st.markdown("---")

    # --- 4 Engineering, Bill Comparison & TCO Tabs ---
    tabs = st.tabs([
        ":material/warning: 1. Current Situation & Load Ingestion",
        ":material/battery_charging_full: 2. BESS Sizing & Excel Validation",
        ":material/compare_arrows: 3. Baseline vs. BESS Bill & Profile Comparison",
        ":material/account_balance: 4. Financial Comparison & 15Y TCO"
    ])

    with tabs[0]:
        active_limit_kw = render_problem_baseline_tab(active_preset)

    with tabs[1]:
        sim_result = render_technical_feasibility_tab(active_preset, grid_limit_kw=active_limit_kw)

    # Build Explicit Simulation Assumptions Register
    p_col = "Total_Demand_kW" if "Total_Demand_kW" in active_preset.load_df.columns else "P_Load_kW"
    load_norm_2025, _ = normalize_load_profile_2025(active_preset.load_df, power_col=p_col, time_col="timestamp")
    cfg_base, _ = build_4pillar_configs_for_preset(active_preset, active_limit_kw=active_limit_kw)
    assumptions_dict = build_assumptions_register_dict(
        load_series=load_norm_2025,
        config=cfg_base,
        source_filename=f"{active_preset.title} ({len(active_preset.load_df):,} steps)",
        bess_config=sim_result.config
    )

    with assumptions_banner_container:
        render_assumptions_banner(assumptions_dict=assumptions_dict, expanded=False)

    with tabs[2]:
        render_bill_and_profile_comparison_tab(
            preset=active_preset,
            sim_result=sim_result,
            assumptions_dict=assumptions_dict,
            key_prefix=f"{key_prefix}_comp"
        )

    with tabs[3]:
        render_financial_viability_tab(
            preset=active_preset,
            sim_result=sim_result
        )


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
