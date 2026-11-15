"""
Subtab 1: Facility Consumption Profile view (1-Click Reference Presets, CSV & Synthetic Ingestion).
"""

import numpy as np
import streamlit as st

from .state_and_helpers import (
    LoadSeries2025,
    CombinedSystemConfig,
    render_kpi_card,
    synthesize_benchmark_load_profile_2025,
    synthesize_edemsa_salentein_load_profile_2025,
    render_tab1_consumption,
    _sync_shared_load_series,
)

# ======================================================================================
# LEVEL 2 — SUBTAB 1: Consumption (Always Active)
# ======================================================================================

REFERENCE_SCENARIOS: dict = {
    "Commercial Bakery / Office (250 kW Peak / Enexis Netbeheer)": {
        "type": "commercial_hvac",
        "peak_kw": 250.0,
        "grid_limit_kw": 180.0,
    },
    "Rotterdam WKO Heat Pump (110 kW Peak / Stedin Netbeheer)": {
        "type": "commercial_hvac",
        "peak_kw": 110.0,
        "grid_limit_kw": 75.0,
    },
    "Heavy Industrial Logistics (550 kW Peak / Liander Netbeheer)": {
        "type": "commercial_hvac",
        "peak_kw": 550.0,
        "grid_limit_kw": 380.0,
    },
    "Bodegas Salentein Mendoza (430 kW Peak / EDEMSA)": {
        "type": "edemsa_salentein",
        "peak_kw": 691.0,
        "grid_limit_kw": 430.0,
    },
}


def render_subtab1_consumption(load_series: LoadSeries2025) -> None:
    """
    Renders Subtab 1: Consumption (1-Click Reference Scenarios, CSV upload, and 4 Base KPIs).
    """
    cur_sys: CombinedSystemConfig = st.session_state["comb_system_cfg"]
    load_kw = load_series.power_kw
    ann_kwh = float(load_series.total_energy_kwh)
    peak_kw = float(load_series.peak_demand_kw)
    avg_kw = float(np.mean(load_kw)) if len(load_kw) > 0 else 0.0
    over_arr = np.maximum(0.0, load_kw - float(cur_sys.grid_limit_kw))
    over_kw = float(np.max(over_arr)) if len(over_arr) > 0 else 0.0
    over_hrs = float(np.sum(over_arr > 0.05) * 0.25)
    over_kwh = float(np.sum(over_arr) * 0.25)

    # 4 Base KPIs
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        render_kpi_card(
            title="Annual Consumption",
            value=f"{ann_kwh:,.0f} kWh",
            subtext="Total annual electricity demand",
            status="default",
        )
    with k2:
        render_kpi_card(
            title="Peak Demand",
            value=f"{peak_kw:,.1f} kW",
            subtext="Highest 15-minute load spike",
            status="default",
        )
    with k3:
        render_kpi_card(
            title="Average Load",
            value=f"{avg_kw:,.1f} kW",
            subtext=f"Load factor: {(avg_kw / max(1.0, peak_kw) * 100.0):.1f}%",
            status="default",
        )
    with k4:
        render_kpi_card(
            title="Overload above Grid Limit",
            value=f"{over_kw:,.1f} kW ({over_hrs:,.1f} hrs)",
            subtext=f"{over_kwh:,.0f} kWh above {cur_sys.grid_limit_kw:,.0f} kW limit",
            status="ok" if over_kw <= 0.05 else "alert",
        )

    # Reference Profiles
    with st.container(border=True):
        st.markdown("##### :material/dataset: Example Profiles")
        with st.form("comb_ref_scenario_form"):
            sc1, sc_btn = st.columns([2.5, 1.2])
            with sc1:
                ref_names = list(REFERENCE_SCENARIOS.keys())
                sel_sc = st.selectbox(
                    "Select Profile",
                    options=ref_names,
                    index=0,
                    key="comb_ref_scenario_select",
                    help="Loads a ready-made consumption profile and grid limit.",
                )
            with sc_btn:
                st.write("")
                apply_sc = st.form_submit_button(
                    "Load Profile",
                    icon=":material/download:",
                    use_container_width=True,
                )

        if apply_sc and sel_sc in REFERENCE_SCENARIOS:
            sc_info = REFERENCE_SCENARIOS[sel_sc]
            cur_sys.grid_limit_kw = float(sc_info["grid_limit_kw"])
            st.session_state["comb_grid_limit_num"] = cur_sys.grid_limit_kw
            if sc_info["type"] == "edemsa_salentein":
                bench_profile = synthesize_edemsa_salentein_load_profile_2025()
            else:
                bench_profile = synthesize_benchmark_load_profile_2025(
                    profile_type=sc_info["type"],
                    nominal_peak_kw=float(sc_info["peak_kw"]),
                )
            st.session_state["active_load_series_2025"] = bench_profile
            st.session_state["comb_active_load_series"] = bench_profile
            st.session_state["active_csv_filename"] = sel_sc
            st.session_state["comb_active_load_label"] = f"Reference: {sel_sc}"
            st.session_state["tab1_active_source"] = "benchmark"
            _sync_shared_load_series()
            st.rerun()

    st.write("")
    render_tab1_consumption(key_prefix="comb_tab1_cons")
    _sync_shared_load_series()
