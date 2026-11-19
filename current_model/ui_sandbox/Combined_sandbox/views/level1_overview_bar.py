"""
Level 1 Top System Overview Bar view (Contracted Grid Limit + Global Module Switches).
"""

import streamlit as st

from .state_and_helpers import (
    fmt_num,
    LoadSeries2025,
    CombinedSystemConfig,
)

# ======================================================================================
# LEVEL 1: System Overview Bar (Top)
# ======================================================================================

def render_level1_overview_bar(load_series: LoadSeries2025, load_label: str) -> None:
    """
    Renders the top System Overview Bar:
      - Contracted Grid Limit (kW) input right next to measured Peak Demand (kW)
      - Global activation toggles for Solar, Battery, Generator, and Financials
    """
    cur_sys: CombinedSystemConfig = st.session_state["comb_system_cfg"]
    orig_peak_kw = float(load_series.peak_demand_kw)

    with st.container(border=True):
        c_grid, c_peak, c_sol, c_bat, c_gen, c_fin = st.columns([1.4, 1.2, 0.85, 0.85, 0.85, 0.85])

        with c_grid:
            with st.form("comb_grid_limit_form"):
                raw_grid_limit = float(cur_sys.grid_limit_kw)
                max_grid_limit = max(100000.0, raw_grid_limit * 2, orig_peak_kw * 2)
                safe_grid_limit = min(max_grid_limit, max(10.0, raw_grid_limit))
                grid_limit_val = st.number_input(
                    "Grid Limit (kW)",
                    min_value=10.0,
                    max_value=max_grid_limit,
                    value=safe_grid_limit,
                    step=10.0,
                    key="comb_grid_limit_input",
                )
                gl_submitted = st.form_submit_button(
                    "Apply Limit",
                    use_container_width=True,
                )
            if gl_submitted:
                cur_sys.grid_limit_kw = float(grid_limit_val)
                st.session_state.pop("comb_cached_excel_bytes", None)

        overload_kw = max(0.0, orig_peak_kw - float(cur_sys.grid_limit_kw))
        with c_peak:
            st.metric(
                label="Peak Demand",
                value=f"{fmt_num(orig_peak_kw, 1)} kW",
                delta=(
                    f"+{fmt_num(overload_kw, 1)} kW above Grid Limit"
                    if overload_kw > 0.05
                    else "Within Grid Limit"
                ),
                delta_color="inverse" if overload_kw > 0.05 else "normal",
            )

        with c_sol:
            st.write("")
            en_sol = st.toggle(
                ":material/solar_power: Solar",
                key="comb_enable_solar_toggle",
            )
            cur_sys.enable_solar = bool(en_sol)

        with c_bat:
            st.write("")
            en_bat = st.toggle(
                ":material/battery_charging_full: Battery",
                key="comb_enable_battery_toggle",
            )
            cur_sys.enable_battery = bool(en_bat)

        with c_gen:
            st.write("")
            en_gen = st.toggle(
                ":material/power: Generator",
                key="comb_enable_generator_toggle",
            )
            cur_sys.enable_generator = bool(en_gen)

        with c_fin:
            st.write("")
            en_fin = st.toggle(
                ":material/payments: Financials",
                key="comb_enable_financials_toggle",
            )
            cur_sys.enable_financials = bool(en_fin)
