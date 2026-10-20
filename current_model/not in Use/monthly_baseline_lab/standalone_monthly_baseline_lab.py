# To run: python -m streamlit run current_model/ui_sandbox/standalone_monthly_baseline_lab.py

"""
========================================================================================
Standalone Monthly Baseline & Commercial Electricity Tariff Lab
(current_model/ui_sandbox/standalone_monthly_baseline_lab.py)
========================================================================================

Architecture & Isolation:
-------------------------
- Core Coordinator for the autarkic 12-Month Baseline & Commercial Tariff Lab.
- Modularized architecture strictly isolated inside ui_sandbox/ with zero production risk for app.py.
- Sub-components:
-     * monthly_presets: Standard preset catalogs and loader
-     * monthly_calc: Pure mathematical billing calculation engine & data models
-     * monthly_header_view: Standard presets toolbar, reload button, currency & FX converter
-     * monthly_editors: Dual interactive data editors (Table A Consumption, Table B Tariffs)
-     * monthly_charts: Plotly stacked cost composition & volume charts
-     * monthly_audit: Detailed step-by-step arithmetic and numerical audit panel
-     * monthly_financial_view: 4 Financial metric KPI cards & CSV/JSON export toolbar
-     * monthly_tou_manager: Optional dynamic Time-of-Use (TOU) window manager
-     * monthly_dso_generator: Optional Dutch Grid Operator (Enexis & Liander 2025) rate generator
========================================================================================
"""

import os
import sys
from typing import List, Tuple

import pandas as pd
import streamlit as st

# Ensure project root and current_model are on sys.path
SANDBOX_DIR = os.path.dirname(os.path.abspath(__file__))
CURRENT_MODEL_DIR = os.path.abspath(os.path.join(SANDBOX_DIR, ".."))
WORKSPACE_ROOT = os.path.abspath(os.path.join(CURRENT_MODEL_DIR, ".."))

for path in [WORKSPACE_ROOT, CURRENT_MODEL_DIR, SANDBOX_DIR]:
    if path not in sys.path:
        sys.path.insert(0, path)

try:
    from current_model.ui.common.styles import apply_custom_styles
except ImportError:
    apply_custom_styles = None

# Re-exports: Presets & Dutch DSO Catalogs
try:
    from current_model.ui_sandbox.monthly_baseline_lab.monthly_presets import (
        MONTHS_LIST,
        TOUTierConfig,
        ENEXIS_2025_GRID_TIERS,
        ENEXIS_2025_CONNECTION_CAPACITIES,
        build_enexis_2025_tariff_dataframe,
        LIANDER_2025_GRID_TIERS,
        LIANDER_2025_CONNECTION_CAPACITIES,
        build_liander_2025_tariff_dataframe,
        get_salentein_pozo600_preset,
        get_3tier_argentine_preset,
        get_netherlands_commercial_preset,
        reload_preset_data,
        get_preset_three_party_entities,
    )
except ImportError:
    from monthly_presets import (
        MONTHS_LIST,
        TOUTierConfig,
        ENEXIS_2025_GRID_TIERS,
        ENEXIS_2025_CONNECTION_CAPACITIES,
        build_enexis_2025_tariff_dataframe,
        LIANDER_2025_GRID_TIERS,
        LIANDER_2025_CONNECTION_CAPACITIES,
        build_liander_2025_tariff_dataframe,
        get_salentein_pozo600_preset,
        get_3tier_argentine_preset,
        get_netherlands_commercial_preset,
        reload_preset_data,
        get_preset_three_party_entities,
    )

# Re-exports: Calculation Engine
try:
    from current_model.ui_sandbox.monthly_baseline_lab.monthly_calc import (
        MonthlyBillingResult,
        AnnualBillingSummary,
        compute_monthly_billing,
        build_monthly_billing_statement_dataframe,
        build_baseline_export_payload,
    )
except ImportError:
    from monthly_calc import (
        MonthlyBillingResult,
        AnnualBillingSummary,
        compute_monthly_billing,
        build_monthly_billing_statement_dataframe,
        build_baseline_export_payload,
    )

# Visualizations & Sub-views
try:
    from current_model.ui_sandbox.monthly_baseline_lab.monthly_charts import (
        create_monthly_billing_breakdown_chart,
        create_monthly_energy_volume_chart,
    )
    from current_model.ui_sandbox.monthly_baseline_lab.monthly_audit import render_mathematical_audit_panel
    from current_model.ui_sandbox.monthly_baseline_lab.monthly_header_view import render_header_and_presets_toolbar
    from current_model.ui_sandbox.monthly_baseline_lab.monthly_tou_manager import render_tou_window_manager
    from current_model.ui_sandbox.monthly_baseline_lab.monthly_dso_generator import render_dso_tariff_generator
    from current_model.ui_sandbox.monthly_baseline_lab.monthly_editors import (
        render_consumption_table_editor,
        render_tariff_table_editor,
    )
    from current_model.ui_sandbox.monthly_baseline_lab.monthly_financial_view import (
        render_financial_kpi_cards,
        render_export_toolbar,
    )
except ImportError:
    from monthly_charts import (
        create_monthly_billing_breakdown_chart,
        create_monthly_energy_volume_chart,
    )
    from monthly_audit import render_mathematical_audit_panel
    from monthly_header_view import render_header_and_presets_toolbar
    from monthly_tou_manager import render_tou_window_manager
    from monthly_dso_generator import render_dso_tariff_generator
    from monthly_editors import (
        render_consumption_table_editor,
        render_tariff_table_editor,
    )
    from monthly_financial_view import (
        render_financial_kpi_cards,
        render_export_toolbar,
    )


def render_monthly_baseline_lab(key_prefix: str = "monthly_baseline"):
    """Core orchestrator for the standalone monthly baseline and commercial tariff laboratory."""

    # 1. State Initialization
    state_cdf_key = f"{key_prefix}_consumption_df"
    state_tdf_key = f"{key_prefix}_tariff_df"
    state_tiers_key = f"{key_prefix}_tou_tiers"
    state_currency_key = f"{key_prefix}_currency"
    state_fx_key = f"{key_prefix}_fx_rate"
    state_preset_name_key = f"{key_prefix}_preset_name"
    state_dso_key = f"{key_prefix}_dso_name"
    state_supplier_key = f"{key_prefix}_supplier_name"
    state_meter_co_key = f"{key_prefix}_meter_company_name"
    state_meter_fee_key = f"{key_prefix}_meter_fee"

    if (state_cdf_key not in st.session_state or state_tdf_key not in st.session_state or state_tiers_key not in st.session_state):
        c_init, t_init, tiers_init, cur_init, fx_init, name_init = get_salentein_pozo600_preset()
        dso_init, supp_init, meter_init, fee_init = get_preset_three_party_entities(name_init)
        st.session_state[state_cdf_key] = c_init
        st.session_state[state_tdf_key] = t_init
        st.session_state[state_tiers_key] = tiers_init
        st.session_state[state_currency_key] = cur_init
        st.session_state[state_fx_key] = fx_init
        st.session_state[state_preset_name_key] = name_init
        st.session_state[state_dso_key] = dso_init
        st.session_state[state_supplier_key] = supp_init
        st.session_state[state_meter_co_key] = meter_init
        st.session_state[state_meter_fee_key] = fee_init

    # 2. Section 1: Header, Standard Presets & Currency Controls & 3-Party Entities
    currency, fx_rate, preset_name, dso_name, supplier_name, meter_company_name = render_header_and_presets_toolbar(key_prefix=key_prefix)

    # Active TOU Tiers directly from session state (Core Competence)
    active_tiers: List[TOUTierConfig] = st.session_state.get(state_tiers_key, [])
    if not active_tiers:
        _, _, active_tiers, _, _, _ = get_salentein_pozo600_preset()
        st.session_state[state_tiers_key] = active_tiers

    # 3. Section 1: Table A — 12-Month Consumption Matrix
    edited_cdf = render_consumption_table_editor(key_prefix=key_prefix, active_tiers=active_tiers, preset_name=preset_name)

    # 4. Section 2: Table B — 12-Month Tariff Matrix
    edited_tdf = render_tariff_table_editor(key_prefix=key_prefix, active_tiers=active_tiers, selected_cur=currency, preset_name=preset_name)

    # 5. Section 3: Financial Assessment & Core Calculation Engine
    st.markdown("### :material/analytics: 3. Financial Assessment & Full-Year Statement")
    summary = compute_monthly_billing(
        consumption_df=edited_cdf,
        tariff_df=edited_tdf,
        tou_tiers=active_tiers,
        currency=currency,
        fx_rate=fx_rate,
        dso_name=dso_name,
        supplier_name=supplier_name,
        meter_company_name=meter_company_name
    )

    # 7. Financial Dashboard: KPIs, Stacked Chart, Statement Table & Mathematical Audit
    render_financial_kpi_cards(summary=summary, selected_cur=currency)

    st.markdown("#### :material/bar_chart: Monthly Cost Composition Breakdown (Stacked)")
    fig = create_monthly_billing_breakdown_chart(summary=summary, active_tiers=active_tiers)
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### :material/format_list_bulleted: Comprehensive Full-Year Billing Statement")
    statement_df = build_monthly_billing_statement_dataframe(summary=summary, active_tiers=active_tiers)
    st.dataframe(statement_df, use_container_width=True, hide_index=True)

    render_mathematical_audit_panel(
        summary=summary,
        active_tiers=active_tiers,
        tariff_df=edited_tdf,
        selected_cur=currency,
        key_prefix=key_prefix
    )

    # 8. Baseline Export (CSV & JSON)
    render_export_toolbar(
        summary=summary,
        active_tiers=active_tiers,
        consumption_df=edited_cdf,
        tariff_df=edited_tdf,
        preset_name=preset_name,
        selected_cur=currency,
        fx_rate=fx_rate
    )


def main():
    st.set_page_config(
        page_title="Monthly Baseline & Commercial Tariff Lab",
        page_icon=":material/calendar_month:",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    if apply_custom_styles:
        apply_custom_styles()

    render_monthly_baseline_lab(key_prefix="standalone_lab")


if __name__ == "__main__":
    main()
