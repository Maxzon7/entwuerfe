"""
========================================================================================
Current Situation (Status Quo) Sandbox App
ui_sandbox/Currentsituation_sandbox/app.py
========================================================================================

Standalone Streamlit application encapsulating the Dutch Commercial Electricity
Grootverbruik workbench:
  1. Consumption Profile Modeling & 15-Minute Interval Ingestion (Interactive Plotly load curves,
     365-day baseline, monthly breakdown, overload analysis, and KPI cards).
  2. 4-Pillar Unbundled Contract Billing & Executive Strategy (Regulated DSO, Energy Retailer,
     Certified Metering EMV, Transformer Station Rental, and Degressive Energiebelasting).
"""

import os
import sys

# Ensure current_model and workspace roots are in sys.path
current_dir = os.path.abspath(os.path.dirname(__file__))
ui_sandbox_dir = os.path.abspath(os.path.join(current_dir, ".."))
current_model_dir = os.path.abspath(os.path.join(current_dir, "..", ".."))
workspace_dir = os.path.abspath(os.path.join(current_model_dir, ".."))
for p in [workspace_dir, current_model_dir, current_dir, ui_sandbox_dir]:
    if p not in sys.path:
        sys.path.insert(0, p)

import streamlit as st
import pandas as pd

import importlib

# ========================================================================================
# Developer Module Hot-Reloading:
# Can be triggered on-demand via the sidebar button or dev query parameter.
# Normal widget interactions run without reloading to preserve object class identity
# and eliminate redundant re-parsing of the 35,040 interval series.
# ========================================================================================

def reload_sandbox_modules() -> None:
    """Explicitly reloads all sandbox modules from disk when requested by developer."""
    for mod_name in list(sys.modules.keys()):
        if "Currentsituation_sandbox.engine" in mod_name:
            try:
                importlib.reload(sys.modules[mod_name])
            except Exception:
                pass
    try:
        import ui_sandbox.Currentsituation_sandbox.ui_theme as _ui_theme
        import ui_sandbox.Currentsituation_sandbox.contract.charts as _con_charts
        import ui_sandbox.Currentsituation_sandbox.contract.procurement_view as _strat_view
        import ui_sandbox.Currentsituation_sandbox.contract.view as _con_view
        import ui_sandbox.Currentsituation_sandbox.consumption.view as _c_view
        importlib.reload(_ui_theme)
        importlib.reload(_con_charts)
        importlib.reload(_strat_view)
        importlib.reload(_con_view)
        importlib.reload(_c_view)
    except Exception:
        try:
            import current_model.ui_sandbox.Currentsituation_sandbox.ui_theme as _ui_theme
            import current_model.ui_sandbox.Currentsituation_sandbox.contract.charts as _con_charts
            import current_model.ui_sandbox.Currentsituation_sandbox.contract.procurement_view as _strat_view
            import current_model.ui_sandbox.Currentsituation_sandbox.contract.view as _con_view
            import current_model.ui_sandbox.Currentsituation_sandbox.consumption.view as _c_view
            importlib.reload(_ui_theme)
            importlib.reload(_con_charts)
            importlib.reload(_strat_view)
            importlib.reload(_con_view)
            importlib.reload(_c_view)
        except Exception:
            pass


# Check if dev reload was requested via query param or session flag
_query_params = getattr(st, "query_params", {})
if _query_params.get("dev_reload") in ["1", "true", "True"] or st.session_state.get("_trigger_dev_reload", False):
    reload_sandbox_modules()
    st.session_state["_trigger_dev_reload"] = False

# Standard High-Performance Imports (Stable Class Identities)
try:
    from ui_sandbox.Currentsituation_sandbox.ui_theme import (
        apply_currsit_theme,
        configure_plotly_currsit_theme,
        render_hero_banner,
    )
    from ui_sandbox.Currentsituation_sandbox.consumption.view import render_tab1_consumption
    from ui_sandbox.Currentsituation_sandbox.contract.view import render_tab2_base_contract
except ImportError:
    try:
        from current_model.ui_sandbox.Currentsituation_sandbox.ui_theme import (
            apply_currsit_theme,
            configure_plotly_currsit_theme,
            render_hero_banner,
        )
        from current_model.ui_sandbox.Currentsituation_sandbox.consumption.view import render_tab1_consumption
        from current_model.ui_sandbox.Currentsituation_sandbox.contract.view import render_tab2_base_contract
    except ImportError:
        from ui_theme import (
            apply_currsit_theme,
            configure_plotly_currsit_theme,
            render_hero_banner,
        )
        from consumption.view import render_tab1_consumption
        from contract.view import render_tab2_base_contract


def render_current_situation_sandbox(key_prefix: str = "currsit") -> None:
    """Renders the complete Current Situation (Status Quo) workbench."""
    render_hero_banner(
        title="Commercial Electricity Procurement & Status Quo Sandbox",
        subtitle=(
            "Dutch Grootverbruik (> 3x80A) regulatory baseline: 4-pillar unbundled market structure "
            "(Regulated DSO, Energy Retailer, Certified EMV Metering, Transformer Substation Rental), "
            "degressive Energiebelasting, and executive sourcing advisory."
        ),
        badge_text="DUTCH GROOTVERBRUIK > 3x80A",
        icon=":material/analytics:"
    )

    # Status Overview Banner
    active_source = st.session_state.get("tab1_active_source", "csv")
    csv_df = st.session_state.get("active_csv_df")
    csv_name = st.session_state.get("active_csv_filename", "Uploaded File")
    has_csv = isinstance(csv_df, pd.DataFrame) and not csv_df.empty

    col_stat1, col_stat2, col_stat3 = st.columns(3)
    with col_stat1:
        source_label = "CSV Real Meter Data" if active_source == "csv" else "Synthetic Simulator"
        st.info(f"**Active Load Source:** {source_label}", icon=":material/power:")
    with col_stat2:
        if has_csv and active_source == "csv":
            st.success(f"**Active CSV:** `{csv_name}` ({len(csv_df):,} intervals)", icon=":material/check_circle:")
        else:
            st.info("**Profile Status:** Ready for ingestion / simulation", icon=":material/info:")
    with col_stat3:
        if st.button(":material/restart_alt: Reset Sandbox Session", use_container_width=True, key=f"{key_prefix}_reset_btn"):
            for k in list(st.session_state.keys()):
                if k.startswith(key_prefix) or "active_csv" in k or "calc_data" in k:
                    st.session_state.pop(k, None)
            st.rerun()

    # Developer Sidebar Trigger
    with st.sidebar:
        st.markdown("### :material/developer_mode: Sandbox Controls")
        if st.button(":material/refresh: Reload Modules from Disk", use_container_width=True, key=f"{key_prefix}_reload_btn", help="Force reloads all sandbox code from disk"):
            reload_sandbox_modules()
            st.success("Sandbox modules reloaded from disk!")
            st.rerun()

    st.markdown("---")

    # Dual Navigation Tabs
    tab_titles = [
        ":material/monitoring: 1. Consumption Profile (Visualizer & Inspector)",
        ":material/receipt_long: 2. Current Contract & Status Quo Billing"
    ]
    tabs = st.tabs(tab_titles)

    with tabs[0]:
        st.markdown("### :material/insights: Facility Consumption Profile & Interval Data")
        render_tab1_consumption(key_prefix=f"{key_prefix}_tab1")

    with tabs[1]:
        st.markdown("### :material/description: Electricity Supply Contract & Cost Assessment")
        render_tab2_base_contract(key_prefix=f"{key_prefix}_tab2")


def main() -> None:
    """Standalone page entrypoint."""
    st.set_page_config(
        page_title="Dutch Commercial Electricity Sandbox | Status Quo",
        page_icon=":material/analytics:",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    apply_currsit_theme()
    configure_plotly_currsit_theme()
    render_current_situation_sandbox()


if __name__ == "__main__":
    main()
