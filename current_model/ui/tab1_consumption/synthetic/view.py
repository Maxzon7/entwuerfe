"""
========================================================================================
Synthetic Load Simulator View (current_model/ui/tab1_consumption/synthetic/view.py)
========================================================================================

Description:
------------
Orchestrates the 24-hour synthetic bottom-up simulation interface:
  - Metric summary cards
  - Compact grid capacity limit setup
  - Plotly stacked profile visualization
  - Real-time overload limit calculations & alert cards
  - Consumer add/edit forms and preset loading
"""

import datetime
from typing import List
import streamlit as st
import numpy as np
import pandas as pd

from current_model.models.load_component import SimpleConsumer, TimeWindow
from current_model.models.grid_limit import OverloadAnalysisResult
from current_model.models.presets import PRESET_FACTORIES
from current_model.core.synthetic_engine import aggregate_synthetic_24h
from current_model.ui.common.cards import render_kpi_card
from current_model.ui.tab1_consumption.synthetic.charts import create_synthetic_profile_figure
from current_model.ui.tab1_consumption.synthetic.forms import render_add_consumer_form, render_consumer_editor


def render_synthetic_simulator(key_prefix: str = "synthetic") -> None:
    """
    Renders the complete 24-Hour Synthetic Load Simulator UI.
    """
    session_key = f"{key_prefix}_consumers"
    if session_key not in st.session_state:
        st.session_state[session_key] = []

    consumers: List[SimpleConsumer] = st.session_state[session_key]

    # Backward compatibility migration for older single-window objects
    for c in consumers:
        if not hasattr(c, "time_windows") or not c.time_windows:
            s_time = getattr(c, "start_time", datetime.time(8, 0))
            e_time = getattr(c, "end_time", datetime.time(16, 0))
            h_peak = getattr(c, "has_peak", False)
            p_power = getattr(c, "peak_power_kw", c.power_kw)
            p_dur = getattr(c, "peak_duration_min", 30)
            c.time_windows = [TimeWindow(s_time, e_time, h_peak, p_power, p_dur)]

    # Quick Preset Bar
    with st.expander("⚡ Load Pre-Configured Industry Presets", expanded=False):
        preset_cols = st.columns(len(PRESET_FACTORIES))
        for p_idx, (preset_name, factory_func) in enumerate(PRESET_FACTORIES.items()):
            with preset_cols[p_idx]:
                if st.button(f"Load {preset_name}", key=f"{key_prefix}_load_preset_{p_idx}", use_container_width=True):
                    st.session_state[session_key] = factory_func()
                    st.rerun()

    # 1. Aggregate Data for the 24-Hour Day (96 steps)
    df_day, total_curve, metrics = aggregate_synthetic_24h(consumers)

    # 2. Metric KPI Cards
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        render_kpi_card("⚡ Daily Peak Load (P_max)", f"{metrics['peak_demand_kw']:.1f} kW", "Maximum 15-min demand")
    with col2:
        render_kpi_card("🔋 Daily Energy Consumption", f"{metrics['daily_energy_kwh']:.1f} kWh", "Integrated 24h consumption")
    with col3:
        render_kpi_card("📊 Average Daily Power", f"{metrics['avg_power_kw']:.1f} kW", "Daily average baseline")
    with col4:
        render_kpi_card("🧩 Total Consumers", str(metrics['consumer_count']), "Active machine entities")

    # 3. Compact Grid Limit Option (No standalone subheader)
    g_col1, g_col2 = st.columns([1, 1])
    with g_col1:
        enable_grid_limit = st.toggle(
            "Enable Grid Capacity Limit",
            value=False,
            help="Define a maximum grid connection capacity limit and analyze overload violations.",
            key=f"{key_prefix}_enable_grid_limit"
        )
    with g_col2:
        if enable_grid_limit:
            grid_limit_kw = st.number_input(
                "Max Grid Capacity Limit (kW):",
                min_value=5.0,
                max_value=5000.0,
                value=100.0,
                step=5.0,
                key=f"{key_prefix}_grid_limit_kw"
            )
        else:
            grid_limit_kw = None

    # 4. Interactive Plotly Chart
    st.subheader("📈 24-Hour Simulated Load Profile (15-Minute Resolution)")
    fig = create_synthetic_profile_figure(
        df_day=df_day,
        consumers=consumers,
        grid_limit_kw=grid_limit_kw
    )
    st.plotly_chart(fig, use_container_width=True)

    # 5. Grid Limit Overload Analysis
    if enable_grid_limit and grid_limit_kw:
        analysis = OverloadAnalysisResult.from_curve(
            total_curve_kw=total_curve,
            grid_limit_kw=grid_limit_kw,
            step_hours=0.25
        )

        st.markdown("#### 🚨 Grid Capacity Overload Analysis")
        o_col1, o_col2, o_col3 = st.columns(3)

        with o_col1:
            status_style = "alert" if analysis.has_violation else "ok"
            status_title = "⚠️ Grid Overload Peak" if analysis.has_violation else "✅ Grid Status"
            val_str = f"+{analysis.overload_peak_kw:.1f} kW" if analysis.has_violation else "Within Limit"
            render_kpi_card(
                status_title,
                val_str,
                f"Max Limit: {grid_limit_kw:.1f} kW",
                status=status_style
            )

        with o_col2:
            render_kpi_card(
                "⏱️ Overload Duration",
                f"{analysis.overload_duration_hours:.2f} hrs",
                f"{analysis.overload_intervals_count} intervals (15-min)"
            )

        with o_col3:
            render_kpi_card(
                "⚡ Overload Energy",
                f"{analysis.overload_energy_kwh:.1f} kWh",
                "Excess Energy over Limit"
            )

    st.divider()

    # 6. Consumer Management & Add Form
    col_left, col_right = st.columns([1, 1])
    with col_left:
        render_add_consumer_form(consumers)
    with col_right:
        render_consumer_editor(consumers)
