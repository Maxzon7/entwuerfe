# To Run: python -m streamlit run prototypes/presentation.py

"""
========================================================================================
PRESENTATION & MODULE TESTING PLAYGROUND (presentation.py)
========================================================================================
A lightweight playground allowing users to select between:
  1. ⚡ 24-Hour Synthetic Load Simulator (Bottom-up component modeling)
  2. 📁 CSV Real Meter Data Visualizer (Ingestion, column mapping, scaling & plots)
  3. 📄 Electricity Supply Contract & Tariff Configuration (Expandable)
========================================================================================
"""

import sys
import os
import datetime
import uuid
from typing import List, Dict, Optional, Tuple

# Ensure project root directory is at the front of sys.path to avoid name collision with prototypes/presentation2.py
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go

from presentation2 import render_csv_inspector
from templates.contract_form_template import render_contract_form


# --------------------------------------------------------------------------------------
# Page Setup
# --------------------------------------------------------------------------------------
st.set_page_config(
    page_title="Energy Simulator - Sandbox",
    page_icon="🧪",
    layout="wide"
)

# Dark theme card styling
st.markdown(
    """
    <style>
    .sandbox-card {
        background-color: #1a1f2c;
        border-radius: 10px;
        padding: 16px 20px;
        border-left: 5px solid #38bdf8;
        box-shadow: 0 4px 10px rgba(0,0,0,0.3);
        margin-bottom: 12px;
    }
    .sandbox-card-alert {
        background-color: #2b1319;
        border-radius: 10px;
        padding: 16px 20px;
        border-left: 5px solid #f43f5e;
        box-shadow: 0 4px 10px rgba(244,63,94,0.25);
        margin-bottom: 12px;
    }
    .sandbox-card-ok {
        background-color: #11261f;
        border-radius: 10px;
        padding: 16px 20px;
        border-left: 5px solid #10b981;
        box-shadow: 0 4px 10px rgba(16,185,129,0.25);
        margin-bottom: 12px;
    }
    .sandbox-title {
        font-size: 0.85rem;
        color: #94a3b8;
        text-transform: uppercase;
        font-weight: 600;
        letter-spacing: 0.5px;
    }
    .sandbox-value {
        font-size: 1.7rem;
        font-weight: 700;
        color: #f8fafc;
        margin-top: 4px;
    }
    .sandbox-sub {
        font-size: 0.75rem;
        color: #64748b;
        margin-top: 2px;
    }
    </style>
    """,
    unsafe_allow_html=True
)

st.title("Presentation & Testing Playground")
st.caption("A simplified sandbox for inspecting real CSV meter data or simulating synthetic load profiles.")

# Function Switcher
app_mode = st.radio(
    "Select Function:",
    options=[
        "⚡ 24-Hour Synthetic Load Simulator",
        "📁 CSV Real Meter Data Visualizer"
    ],
    horizontal=True
)

st.divider()


# ======================================================================================
# MODE A: Real CSV Meter Data Visualizer
# ======================================================================================
if app_mode == "📁 CSV Real Meter Data Visualizer":
    render_csv_inspector(key_prefix="presentation_csv")


# ======================================================================================
# MODE B: 24-Hour Synthetic Load Simulator
# ======================================================================================
else:
    class TimeWindow:
        """Represents a single daily operating window with optional startup peak."""
        def __init__(
            self,
            start_time: datetime.time = datetime.time(8, 0),
            end_time: datetime.time = datetime.time(16, 0),
            has_peak: bool = False,
            peak_power_kw: float = 0.0,
            peak_duration_min: int = 30
        ):
            self.start_time = start_time
            self.end_time = end_time
            self.has_peak = has_peak
            self.peak_power_kw = float(peak_power_kw)
            self.peak_duration_min = int(peak_duration_min)


    class SimpleConsumer:
        """Represents an electrical consumer load supporting multiple 24-hour time windows."""
        def __init__(
            self,
            name: str,
            power_kw: float,
            time_windows: List[TimeWindow] = None
        ):
            self.id = str(uuid.uuid4())[:8]
            self.name = name
            self.power_kw = max(0.0, float(power_kw))
            self.time_windows = time_windows if time_windows is not None else []

        def get_24h_array(self) -> np.ndarray:
            """Computes a 96-element array of power (kW) for 15-minute intervals across all windows."""
            curve = np.zeros(96, dtype=float)
            for window in self.time_windows:
                start_m = window.start_time.hour * 60 + window.start_time.minute
                end_m = window.end_time.hour * 60 + window.end_time.minute
                is_24h = (start_m == 0 and end_m == 0 and window.start_time == window.end_time)

                for step in range(96):
                    slot_start = step * 15
                    active = False

                    if is_24h:
                        active = True
                    elif start_m < end_m:
                        if slot_start >= start_m and slot_start < end_m:
                            active = True
                    elif start_m > end_m:
                        if slot_start >= start_m or slot_start < end_m:
                            active = True

                    if active:
                        val = self.power_kw
                        if window.has_peak and window.peak_power_kw > self.power_kw:
                            peak_dur = window.peak_duration_min
                            if start_m < end_m:
                                if slot_start < (start_m + peak_dur):
                                    val = window.peak_power_kw
                            else:
                                if slot_start >= start_m and slot_start < (start_m + peak_dur):
                                    val = window.peak_power_kw
                                elif slot_start < end_m and (slot_start + 1440) < (start_m + peak_dur):
                                    val = window.peak_power_kw
                        curve[step] = max(curve[step], val)

            return curve


    # Session State: Consumer List
    if "presentation_consumers" not in st.session_state:
        st.session_state.presentation_consumers = []

    consumers: List[SimpleConsumer] = st.session_state.presentation_consumers

    # Backward compatibility migration for older single-window objects
    for c in consumers:
        if not hasattr(c, "time_windows") or not c.time_windows:
            s_time = getattr(c, "start_time", datetime.time(8, 0))
            e_time = getattr(c, "end_time", datetime.time(16, 0))
            h_peak = getattr(c, "has_peak", False)
            p_power = getattr(c, "peak_power_kw", c.power_kw)
            p_dur = getattr(c, "peak_duration_min", 30)
            c.time_windows = [TimeWindow(s_time, e_time, h_peak, p_power, p_dur)]

    # Aggregate Data for the 24-Hour Day (96 steps)
    time_labels = [f"{h:02d}:{m:02d}" for h in range(24) for m in (0, 15, 30, 45)]
    df_day = pd.DataFrame({"time": time_labels})
    total_curve = np.zeros(96, dtype=float)

    for c in consumers:
        c_curve = c.get_24h_array()
        df_day[c.name] = c_curve
        total_curve += c_curve

    df_day["Total_kW"] = total_curve

    # Metrics
    peak_demand_kw = float(total_curve.max()) if len(total_curve) > 0 else 0.0
    daily_energy_kwh = float(total_curve.sum() * 0.25)
    avg_power_kw = daily_energy_kwh / 24.0

    # KPI Cards
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(
            f"""<div class="sandbox-card">
                <div class="sandbox-title">⚡ Daily Peak Load (P_max)</div>
                <div class="sandbox-value">{peak_demand_kw:.1f} kW</div>
            </div>""",
            unsafe_allow_html=True
        )
    with col2:
        st.markdown(
            f"""<div class="sandbox-card">
                <div class="sandbox-title">🔋 Daily Energy Consumption</div>
                <div class="sandbox-value">{daily_energy_kwh:.1f} kWh</div>
            </div>""",
            unsafe_allow_html=True
        )
    with col3:
        st.markdown(
            f"""<div class="sandbox-card">
                <div class="sandbox-title">📊 Average Daily Power</div>
                <div class="sandbox-value">{avg_power_kw:.1f} kW</div>
            </div>""",
            unsafe_allow_html=True
        )
    with col4:
        st.markdown(
            f"""<div class="sandbox-card">
                <div class="sandbox-title">🧩 Total Consumers</div>
                <div class="sandbox-value">{len(consumers)}</div>
            </div>""",
            unsafe_allow_html=True
        )

    # Grid Limit Settings
    st.subheader("⚡ Grid Capacity Limit & Peak Shaving Setup")
    g_col1, g_col2, g_col3 = st.columns([4, 4, 4])
    with g_col1:
        enable_grid_limit = st.toggle("Enable Grid Capacity Limit Monitoring", value=False, help="Toggle on to define maximum grid connection limits and analyze overload violations.")
    with g_col2:
        if enable_grid_limit:
            grid_limit_kw = st.number_input("Max Grid Capacity Limit (kW):", min_value=5.0, max_value=5000.0, value=100.0, step=5.0)
        else:
            grid_limit_kw = None
    with g_col3:
        if enable_grid_limit:
            target_cap_kw = st.number_input("Target Peak-Shaving Cap (kW):", min_value=1.0, max_value=float(grid_limit_kw), value=min(80.0, float(grid_limit_kw)), step=5.0)
        else:
            target_cap_kw = None

    # Interactive Plotly Chart
    st.subheader("📈 24-Hour Simulated Load Profile (15-Minute Resolution)")
    fig = go.Figure()
    color_palette = ["#3B82F6", "#10B981", "#F59E0B", "#EC4899", "#8B5CF6", "#14B8A6", "#F97316"]

    for idx, c in enumerate(consumers):
        color = color_palette[idx % len(color_palette)]
        fig.add_trace(
            go.Scatter(
                x=df_day["time"],
                y=df_day[c.name],
                mode="lines",
                name=c.name,
                stackgroup="one",
                line=dict(width=1.0, color=color),
                hovertemplate=f"<b>{c.name}</b>: %{{y:.1f}} kW<extra></extra>"
            )
        )

    fig.add_trace(
        go.Scatter(
            x=df_day["time"],
            y=df_day["Total_kW"],
            mode="lines",
            name="Total Grid Demand",
            line=dict(color="#FFFFFF", width=3.0),
            hovertemplate="<b>Total Demand</b>: %{y:.1f} kW at %{x}<extra></extra>"
        )
    )

    # Grid Limit & Shaving Target Lines on Chart
    if enable_grid_limit and grid_limit_kw:
        fig.add_hline(
            y=grid_limit_kw,
            line_dash="dash",
            line_color="#f43f5e",
            line_width=2,
            annotation_text=f"Max Grid Limit ({grid_limit_kw:.1f} kW)",
            annotation_position="top right"
        )
        if target_cap_kw and target_cap_kw < grid_limit_kw:
            fig.add_hline(
                y=target_cap_kw,
                line_dash="dot",
                line_color="#38bdf8",
                line_width=1.5,
                annotation_text=f"Target Shaving Cap ({target_cap_kw:.1f} kW)",
                annotation_position="bottom right"
            )

    fig.update_layout(
        template="plotly_dark",
        xaxis=dict(title="Time of Day (HH:MM)", tickmode="linear", dtick=8, gridcolor="#1E293B"),
        yaxis=dict(title="Active Electrical Power (kW)", rangemode="tozero", gridcolor="#1E293B"),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=-0.28, xanchor="center", x=0.5),
        margin=dict(l=40, r=20, t=30, b=80),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        height=420
    )
    st.plotly_chart(fig, use_container_width=True)

    # ----------------------------------------------------------------------------------
    # Grid Limit Overload Analysis & Violation Key Data (Rendered Directly Below Chart)
    # ----------------------------------------------------------------------------------
    if enable_grid_limit and grid_limit_kw:
        overload_diff = (total_curve - grid_limit_kw).clip(min=0.0)
        overload_peak_kw = float(overload_diff.max())
        overload_hours = float((total_curve > grid_limit_kw).sum() * 0.25)
        overload_kwh = float(overload_diff.sum() * 0.25)
        has_violation = overload_peak_kw > 0.0

        if target_cap_kw:
            shave_diff = (total_curve - target_cap_kw).clip(min=0.0)
            shave_peak_kw = float(shave_diff.max())
            shave_kwh = float(shave_diff.sum() * 0.25)

        st.markdown("#### 🚨 Grid Capacity Limit & Overload Analysis")
        o_col1, o_col2, o_col3, o_col4 = st.columns(4)

        with o_col1:
            card_style = "sandbox-card-alert" if has_violation else "sandbox-card-ok"
            status_title = "⚠️ Grid Overload Peak" if has_violation else "✅ Grid Status"
            val_str = f"+{overload_peak_kw:.1f} kW" if has_violation else "Within Limit"
            st.markdown(
                f"""<div class="{card_style}">
                    <div class="sandbox-title">{status_title}</div>
                    <div class="sandbox-value">{val_str}</div>
                    <div class="sandbox-sub">Max Limit: {grid_limit_kw:.1f} kW</div>
                </div>""",
                unsafe_allow_html=True
            )

        with o_col2:
            st.markdown(
                f"""<div class="sandbox-card">
                    <div class="sandbox-title">⏱️ Overload Duration</div>
                    <div class="sandbox-value">{overload_hours:.2f} hrs</div>
                    <div class="sandbox-sub">{int(overload_hours * 4)} 15-min intervals</div>
                </div>""",
                unsafe_allow_html=True
            )

        with o_col3:
            st.markdown(
                f"""<div class="sandbox-card">
                    <div class="sandbox-title">⚡ Overload Energy</div>
                    <div class="sandbox-value">{overload_kwh:.1f} kWh</div>
                    <div class="sandbox-sub">Excess Energy over Limit</div>
                </div>""",
                unsafe_allow_html=True
            )

        with o_col4:
            if target_cap_kw:
                st.markdown(
                    f"""<div class="sandbox-card">
                        <div class="sandbox-title">🔋 Target Shaving Energy</div>
                        <div class="sandbox-value">{shave_kwh:.1f} kWh</div>
                        <div class="sandbox-sub">Peak Shaving Target: {target_cap_kw:.1f} kW</div>
                    </div>""",
                    unsafe_allow_html=True
                )
            else:
                st.markdown(
                    f"""<div class="sandbox-card">
                        <div class="sandbox-title">🛡️ Status</div>
                        <div class="sandbox-value">{"LIMIT EXCEEDED" if has_violation else "OK"}</div>
                        <div class="sandbox-sub">Target Shaving Cap disabled</div>
                    </div>""",
                    unsafe_allow_html=True
                )

    st.divider()

    # Consumer Management & Add Form
    col_left, col_right = st.columns([1, 1])

    with col_left:
        st.subheader("➕ Add New Consumer")
        window_count = st.number_input("Operating Windows count per day:", min_value=1, max_value=4, value=1, step=1, key="add_win_count")

        with st.form("add_consumer_form"):
            new_name = st.text_input("Consumer Name", value=f"Machine {len(consumers) + 1}")
            new_power = st.number_input("Nominal Power (kW)", min_value=0.1, value=20.0, step=1.0)

            new_windows = []
            for w_i in range(int(window_count)):
                st.markdown(f"**Operating Window {w_i + 1}:**")
                w_c1, w_c2 = st.columns(2)
                with w_c1:
                    default_start = datetime.time(8, 0) if w_i == 0 else datetime.time(14, 0)
                    w_start = st.time_input(f"Start Time (W{w_i+1})", value=default_start, step=900, key=f"add_start_{w_i}")
                with w_c2:
                    default_end = datetime.time(12, 0) if w_i == 0 else datetime.time(18, 0)
                    w_end = st.time_input(f"End Time (W{w_i+1})", value=default_end, step=900, key=f"add_end_{w_i}")

                w_has_peak = st.checkbox(f"Include Startup Peak? (W{w_i+1})", key=f"add_has_peak_{w_i}")
                p_col1, p_col2 = st.columns(2)
                with p_col1:
                    w_peak_power = st.number_input(f"Peak Power kW (W{w_i+1})", min_value=0.0, value=float(new_power * 1.5), step=1.0, key=f"add_peak_p_{w_i}")
                with p_col2:
                    w_peak_dur = st.selectbox(f"Peak Duration min (W{w_i+1})", options=[15, 30, 45, 60], index=1, key=f"add_peak_d_{w_i}")

                new_windows.append(TimeWindow(
                    start_time=w_start,
                    end_time=w_end,
                    has_peak=w_has_peak,
                    peak_power_kw=w_peak_power if w_has_peak else new_power,
                    peak_duration_min=w_peak_dur
                ))

            submitted = st.form_submit_button("✅ Add Consumer to Day", use_container_width=True)
            if submitted:
                new_consumer = SimpleConsumer(
                    name=new_name,
                    power_kw=new_power,
                    time_windows=new_windows
                )
                st.session_state.presentation_consumers.append(new_consumer)
                st.rerun()

    with col_right:
        st.subheader("📋 Current Consumers & Editor")
        if not consumers:
            st.info("No consumers defined. Add a consumer on the left.")
        else:
            for idx, c in enumerate(consumers):
                with st.expander(f"✏️ {c.name} ({c.power_kw:.1f} kW) — {len(c.time_windows)} Window(s)", expanded=False):
                    with st.form(key=f"edit_consumer_form_{c.id}"):
                        edit_name = st.text_input("Name:", value=c.name, key=f"edit_name_{c.id}")
                        edit_power = st.number_input("Nominal Power (kW):", min_value=0.1, value=float(c.power_kw), step=1.0, key=f"edit_power_{c.id}")

                        updated_windows = []
                        for w_idx, w in enumerate(c.time_windows):
                            st.markdown(f"**Time Window {w_idx + 1}:**")
                            ew_c1, ew_c2 = st.columns(2)
                            with ew_c1:
                                e_start = st.time_input("Start Time:", value=w.start_time, step=900, key=f"e_start_{c.id}_{w_idx}")
                            with ew_c2:
                                e_end = st.time_input("End Time:", value=w.end_time, step=900, key=f"e_end_{c.id}_{w_idx}")

                            e_has_peak = st.checkbox("Include Startup Peak?", value=w.has_peak, key=f"e_has_peak_{c.id}_{w_idx}")
                            ep_c1, ep_c2 = st.columns(2)
                            with ep_c1:
                                e_peak_p = st.number_input("Peak Power (kW):", min_value=0.0, value=float(w.peak_power_kw if w.has_peak else edit_power * 1.5), step=1.0, key=f"e_peak_p_{c.id}_{w_idx}")
                            with ep_c2:
                                default_dur_idx = [15, 30, 45, 60].index(w.peak_duration_min) if w.peak_duration_min in [15, 30, 45, 60] else 1
                                e_peak_d = st.selectbox("Peak Duration (min):", options=[15, 30, 45, 60], index=default_dur_idx, key=f"e_peak_d_{c.id}_{w_idx}")

                            updated_windows.append(TimeWindow(
                                start_time=e_start,
                                end_time=e_end,
                                has_peak=e_has_peak,
                                peak_power_kw=e_peak_p if e_has_peak else edit_power,
                                peak_duration_min=e_peak_d
                            ))

                        btn_c1, btn_c2 = st.columns([3, 1])
                        with btn_c1:
                            save_submitted = st.form_submit_button("💾 Save Changes", type="primary", use_container_width=True)
                        with btn_c2:
                            delete_submitted = st.form_submit_button("🗑️ Delete", use_container_width=True)

                        if save_submitted:
                            c.name = edit_name
                            c.power_kw = float(edit_power)
                            c.time_windows = updated_windows
                            st.success(f"Saved {c.name}")
                            st.rerun()

                        if delete_submitted:
                            st.session_state.presentation_consumers.pop(idx)
                            st.rerun()


# ======================================================================================
# Bottom Component: Electricity Contract & Tariff Configuration (Expandable)
# ======================================================================================
st.divider()
render_contract_form(as_expander=True, key_prefix="presentation")
