"""
========================================================================================
Combined System Sandbox Application (ui_sandbox/Combined_sandbox/app.py)
========================================================================================

Standalone Execution:
    python -m streamlit run "ui_sandbox/Combined_sandbox/app.py"

3-Level Modular Architecture ("Clean Screen Policy"):
  - Level 1 (Top — System Overview Bar): `views/level1_overview_bar.py`
  - Level 2 (Middle — 6 Modular Sub-Tabs): `views/subtab1_consumption.py` through
    `views/subtab6_financials_overview.py`
  - Level 3 (Bottom — Permanent Master Output): `views/level3_master_output.py`
========================================================================================
"""

import os
import sys
import streamlit as st

_CURRENT_DIR = os.path.abspath(os.path.dirname(__file__))
_UI_SANDBOX_DIR = os.path.abspath(os.path.join(_CURRENT_DIR, ".."))
_PROJECT_ROOT = os.path.abspath(os.path.join(_UI_SANDBOX_DIR, ".."))
_WORKSPACE_DIR = os.path.abspath(os.path.join(_PROJECT_ROOT, ".."))
for _p in (_WORKSPACE_DIR, _PROJECT_ROOT, _UI_SANDBOX_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from ui_sandbox.Combined_sandbox.views import (
        apply_custom_styles,
        CombinedSystemConfig,
        InteractionRulesConfig,
        simulate_combined_system_dispatch,
        _init_session_defaults,
        _get_active_load_series,
        _load_fingerprint,
        _physical_sys_tuple,
        _rules_tuple,
        render_level1_overview_bar,
        render_subtab1_consumption,
        render_subtab2_solar,
        render_subtab3_battery,
        render_subtab4_generator,
        render_subtab5_interaction_rules,
        render_subtab6_financials,
        render_level3_permanent_master_output,
    )
except ImportError:
    from current_model.ui_sandbox.Combined_sandbox.views import (
        apply_custom_styles,
        CombinedSystemConfig,
        InteractionRulesConfig,
        simulate_combined_system_dispatch,
        _init_session_defaults,
        _get_active_load_series,
        _load_fingerprint,
        _physical_sys_tuple,
        _rules_tuple,
        render_level1_overview_bar,
        render_subtab1_consumption,
        render_subtab2_solar,
        render_subtab3_battery,
        render_subtab4_generator,
        render_subtab5_interaction_rules,
        render_subtab6_financials,
        render_level3_permanent_master_output,
    )


def main() -> None:
    st.set_page_config(
        page_title="Combined System",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    apply_custom_styles()
    _init_session_defaults()

    st.markdown("### :material/hub: Combined System")
    st.caption("Grid + Solar + Battery + Generator")

    load_series, load_label = _get_active_load_series()

    # LEVEL 1: System Overview Bar (Top)
    render_level1_overview_bar(load_series, load_label)

    # LEVEL 2: 6 Modular Sub-Tabs (Middle)
    subtabs = st.tabs(
        [
            ":material/analytics: 1. Consumption",
            ":material/solar_power: 2. Solar",
            ":material/battery_charging_full: 3. Battery",
            ":material/power: 4. Generator",
            ":material/tune: 5. System Mix & Rules",
            ":material/payments: 6. Financials",
        ]
    )

    with subtabs[0]:
        render_subtab1_consumption(load_series)

    # Refresh load_series if changed inside Subtab 1
    load_series, load_label = _get_active_load_series()

    with subtabs[1]:
        render_subtab2_solar(load_series)

    with subtabs[2]:
        render_subtab3_battery(load_series)

    with subtabs[3]:
        render_subtab4_generator(load_series)

    with subtabs[4]:
        render_subtab5_interaction_rules(load_series)

    # Run fast physical 15-minute simulation only when physical fingerprint changes
    cur_sys: CombinedSystemConfig = st.session_state["comb_system_cfg"]
    cur_rules: InteractionRulesConfig = st.session_state["comb_rules_cfg"]
    dispatch_fp = (
        _load_fingerprint(load_series),
        _physical_sys_tuple(cur_sys),
        _rules_tuple(cur_rules),
    )
    if (
        st.session_state.get("comb_dispatch_fp") != dispatch_fp
        or "comb_sandbox_result" not in st.session_state
    ):
        sim_res = simulate_combined_system_dispatch(
            load_kw=load_series.power_kw,
            timestamps=load_series.timestamps,
            system_cfg=cur_sys,
            rules_cfg=cur_rules,
            is_gap=getattr(load_series, "is_gap", None),
        )
        if "comb_latest_bottleneck_df" in st.session_state:
            sim_res.bess_bottleneck_df = st.session_state["comb_latest_bottleneck_df"]
        st.session_state["comb_sandbox_result"] = sim_res
        st.session_state["comb_dispatch_fp"] = dispatch_fp
        st.session_state.pop("comb_cached_excel_bytes", None)
    else:
        sim_res = st.session_state["comb_sandbox_result"]
        sim_res.system_config.enable_financials = bool(cur_sys.enable_financials)
        if "comb_latest_bottleneck_df" in st.session_state:
            sim_res.bess_bottleneck_df = st.session_state["comb_latest_bottleneck_df"]

    with subtabs[5]:
        render_subtab6_financials(sim_res)

    # LEVEL 3: Permanent Master Output (Bottom — outside subtabs so always visible)
    render_level3_permanent_master_output(sim_res)


if __name__ == "__main__":
    main()
