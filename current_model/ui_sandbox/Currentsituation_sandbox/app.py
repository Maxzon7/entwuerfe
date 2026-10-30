# to run: python -m streamlit run "ui_sandbox/Currentsituation_sandbox/app.py"
"""
========================================================================================
Current Situation (Status Quo) Sandbox App
ui_sandbox/Currentsituation_sandbox/app.py
========================================================================================

Standalone Streamlit application encapsulating the baseline Status Quo workflow:
  1. Consumption Profile Modeling & Real CSV Ingestion (with full interactive Plotly load curves,
     365-day baseline, monthly breakdown, overload analysis, and KPI cards).
  2. Electricity Contract & Status Quo Billing Assessment (with Master Bill Equation Bar and
     5 modular sub-tabs: Grid Network DSO, Energy Supply Retailer, Metering & Statutory Taxes,
     Executive Overview & 15Y TCO, and Classic Electricity Bill).
"""

import os
import sys

# Ensure current_model and workspace roots are in sys.path
current_dir = os.path.abspath(os.path.dirname(__file__))
ui_sandbox_dir = os.path.abspath(os.path.join(current_dir, ".."))
current_model_dir = os.path.abspath(os.path.join(current_dir, "..", ".."))
workspace_dir = os.path.abspath(os.path.join(current_model_dir, ".."))
for p in [current_dir, ui_sandbox_dir, current_model_dir, workspace_dir]:
    if p not in sys.path:
        sys.path.insert(0, p)

import streamlit as st
import pandas as pd

# Styling & Common Components
try:
    from current_model.ui.common.styles import apply_custom_styles
    from current_model.ui.common.cards import render_kpi_card
except ImportError:
    from ui.common.styles import apply_custom_styles
    from ui.common.cards import render_kpi_card

import importlib

# Reload all modular contract submodules + charts + assumptions + pdf exporter + view
try:
    import ui_sandbox.Currentsituation_sandbox.contract.charts as _con_charts
    import ui_sandbox.Currentsituation_sandbox.contract.assumptions_banner as _assump_ban
    import ui_sandbox.Currentsituation_sandbox.contract.invoice_pdf_exporter as _pdf_exp
    import ui_sandbox.Currentsituation_sandbox.contract.tab_dso as _tab_dso
    import ui_sandbox.Currentsituation_sandbox.contract.tab_supplier as _tab_supp
    import ui_sandbox.Currentsituation_sandbox.contract.tab_metering as _tab_meter
    import ui_sandbox.Currentsituation_sandbox.contract.tab_overview as _tab_ov
    import ui_sandbox.Currentsituation_sandbox.contract.tab_invoice_experimental as _tab_inv
    import ui_sandbox.Currentsituation_sandbox.consumption.view as _c_view
    import ui_sandbox.Currentsituation_sandbox.contract.view as _con_view
    for _mod in (_con_charts, _assump_ban, _pdf_exp, _tab_dso, _tab_supp, _tab_meter, _tab_ov, _tab_inv, _con_view, _c_view):
        importlib.reload(_mod)
    render_tab1_consumption = _c_view.render_tab1_consumption
    render_tab2_base_contract = _con_view.render_tab2_base_contract
except Exception:
    try:
        import current_model.ui_sandbox.Currentsituation_sandbox.contract.charts as _con_charts
        import current_model.ui_sandbox.Currentsituation_sandbox.contract.assumptions_banner as _assump_ban
        import current_model.ui_sandbox.Currentsituation_sandbox.contract.invoice_pdf_exporter as _pdf_exp
        import current_model.ui_sandbox.Currentsituation_sandbox.contract.tab_dso as _tab_dso
        import current_model.ui_sandbox.Currentsituation_sandbox.contract.tab_supplier as _tab_supp
        import current_model.ui_sandbox.Currentsituation_sandbox.contract.tab_metering as _tab_meter
        import current_model.ui_sandbox.Currentsituation_sandbox.contract.tab_overview as _tab_ov
        import current_model.ui_sandbox.Currentsituation_sandbox.contract.tab_invoice_experimental as _tab_inv
        import current_model.ui_sandbox.Currentsituation_sandbox.consumption.view as _c_view
        import current_model.ui_sandbox.Currentsituation_sandbox.contract.view as _con_view
        for _mod in (_con_charts, _assump_ban, _pdf_exp, _tab_dso, _tab_supp, _tab_meter, _tab_ov, _tab_inv, _con_view, _c_view):
            importlib.reload(_mod)
        render_tab1_consumption = _c_view.render_tab1_consumption
        render_tab2_base_contract = _con_view.render_tab2_base_contract
    except Exception:
        try:
            import contract.charts as _con_charts
            import contract.assumptions_banner as _assump_ban
            import contract.invoice_pdf_exporter as _pdf_exp
            import contract.tab_dso as _tab_dso
            import contract.tab_supplier as _tab_supp
            import contract.tab_metering as _tab_meter
            import contract.tab_overview as _tab_ov
            import contract.tab_invoice_experimental as _tab_inv
            for _mod in (_con_charts, _assump_ban, _pdf_exp, _tab_dso, _tab_supp, _tab_meter, _tab_ov, _tab_inv):
                importlib.reload(_mod)
        except Exception:
            pass
        from consumption.view import render_tab1_consumption
        from contract.view import render_tab2_base_contract


def render_current_situation_sandbox(key_prefix: str = "currsit") -> None:
    """Renders the complete Current Situation (Status Quo) workbench."""
    st.markdown("## :material/analytics: Current Situation (Status Quo) Sandbox")
    st.caption(
        "Self-contained baseline laboratory replicating the main application's consumption inspector, "
        "full 15-minute interactive load visualizer, and commercial electricity contract billing engine."
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
        page_title="Current Situation Sandbox | Energy Simulator",
        page_icon=":material/analytics:",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    if apply_custom_styles:
        apply_custom_styles()
    render_current_situation_sandbox()


if __name__ == "__main__":
    main()
