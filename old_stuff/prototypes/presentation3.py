# to run: python -m streamlit run presentation_2_2.py




"""


========================================================================================
DRACBV Energy Simulator - Advanced Load Profile & Simulation Engine (app.py)
========================================================================================

Description:
------------
This Streamlit application serves as an interactive energy load profile generator,
aggregator, and analysis dashboard. It allows electrical engineers, facility managers,
and energy consultants to:
  1. Choose from pre-configured industry presets (Manufacturing, Office, Mobility Hub, Custom).
  2. Dynamically add, modify, or remove modular electrical load components (machines, HVAC, EV chargers).
  3. Configure minute-precise operating windows, multi-shift schedules, and startup peak spikes.
  4. Aggregate loads with continuous standby/baseload consumption.
  5. Visualize 24-hour daily load curves (with weekday/weekend switching), 35,040-interval annual time series,
     and annual load duration curves.
  6. Compute key energy indicators (Peak Demand P_max, Total Consumption MWh/a, Average Power, Full Load Hours).
  7. Export high-resolution 15-minute simulation data to CSV format for battery sizing or grid studies.

Architecture & Execution Model:
-------------------------------
Streamlit operates on a reactive, top-to-bottom script rerun cycle whenever a user interacts
with any widget. To preserve dynamic state (such as added components, edited power ratings,
and loaded presets) across reruns, we utilize `st.session_state`.

Author: Antigravity AI & DRACBV Team
Year: 2026
"""

import datetime
from typing import Dict, List, Any, Optional
import io
import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

# --------------------------------------------------------------------------------------
# Internal Model Imports
# --------------------------------------------------------------------------------------
# LoadComponent: Represents an individual electrical machine or system with operating windows & peaks.
# TimeWindow: Defines a start/end time interval and optional inrush/peak power spike.
from models.load_component import LoadComponent, TimeWindow

# LoadAggregator: Combines multiple LoadComponents and a standby baseline into a unified 15-min profile.
from models.load_aggregator import LoadAggregator

# Presets: Predefined real-world energy load profiles (Industry, Commercial Office, Mobility Hub, Custom).
from models.presets import (
    PRESET_OPTIONS,
    get_preset_industry,
    get_preset_office,
    get_preset_mobility_hub,
    get_preset_custom,
)


# ======================================================================================
# PAGE CONFIGURATION & CUSTOM STYLING
# ======================================================================================
def configure_page() -> None:
    """
    Sets up the Streamlit page layout, browser tab title, favicon, and responsive design.
    Must be the first Streamlit command executed in the script.
    """
    st.set_page_config(
        page_title="DRACBV Energy Load Profile Simulator",
        page_icon="⚡",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    # Inject custom CSS for dark theme aesthetic, KPI card styling, and component containers
    st.markdown(
        """
        <style>
        /* Card container styling for KPI metrics in dark mode */
        .metric-card {
            background-color: #1a1f2c;
            border-radius: 10px;
            padding: 16px 20px;
            border-left: 5px solid #38bdf8;
            box-shadow: 0 4px 10px rgba(0,0,0,0.3);
            margin-bottom: 12px;
            border-top: 1px solid rgba(255,255,255,0.05);
            border-right: 1px solid rgba(255,255,255,0.05);
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }
        .metric-title {
            font-size: 0.85rem;
            color: #94a3b8;
            text-transform: uppercase;
            font-weight: 600;
            letter-spacing: 0.5px;
        }
        .metric-value {
            font-size: 1.7rem;
            font-weight: 700;
            color: #f8fafc;
            margin-top: 4px;
        }
        .metric-sub {
            font-size: 0.8rem;
            color: #64748b;
        }
        /* Component item container */
        .component-box {
            border: 1px solid #334155;
            border-radius: 8px;
            padding: 12px;
            margin-bottom: 12px;
            background-color: #1e293b;
        }
        </style>
        """,
        unsafe_allow_html=True
    )


# ======================================================================================
# SESSION STATE INITIALIZATION & MANAGEMENT
# ======================================================================================
def init_session_state() -> None:
    """
    Initializes required session state variables if they do not already exist.

    Why this is needed:
    -------------------
    Streamlit re-executes the entire script whenever a user clicks a button or moves a slider.
    Without `st.session_state`, modifying a component or switching presets would reset all
    user customizations back to initial defaults.

    Key state variables stored:
      - `aggregator`: The active LoadAggregator instance managing the load components.
      - `selected_preset_key`: The currently selected preset name from the dropdown.
      - `simulation_year`: The calendar year for 15-minute timestamp generation (e.g. 2026).
    """
    if "aggregator" not in st.session_state:
        # Default starting preset is the Industry / Manufacturing profile
        st.session_state.aggregator = get_preset_industry()
        st.session_state.selected_preset_key = list(PRESET_OPTIONS.keys())[0]

    if "simulation_year" not in st.session_state:
        st.session_state.simulation_year = 2026


def load_selected_preset(preset_key: str) -> None:
    """
    Instantiates a fresh LoadAggregator from the selected factory function and
    saves it into the session state.

    Args:
        preset_key: The dictionary key corresponding to one of the presets in `PRESET_OPTIONS`.
    """
    factory_fn = PRESET_OPTIONS.get(preset_key)
    if factory_fn:
        st.session_state.aggregator = factory_fn()
        st.session_state.selected_preset_key = preset_key
        st.toast(f"Loaded preset: {preset_key}", icon="✅")


# ======================================================================================
# PLOTLY VISUALIZATION HELPERS (DARK THEME OPTIMIZED)
# ======================================================================================
def create_daily_profile_figure(df_day: pd.DataFrame, day_name: str) -> go.Figure:
    """
    Builds an interactive Plotly Stacked Area & Total Line Chart for a 24-hour day
    with a dark background and high-contrast styling for maximum readability.

    How it works:
    -------------
    1. Extracts individual component columns (and optional Standby Baseload).
    2. Adds each active load as a stacked area trace (`stackgroup='one'`).
    3. Overlays the 'Total Grid Demand' line in bold pure white to stand out clearly.
    4. Annotates the peak load maximum P_max with a distinct callout badge.

    Args:
        df_day: 96-row DataFrame generated by `LoadAggregator.get_daily_dataframe()`.
        day_name: Human-readable name of the day (e.g. 'Workday (Monday - Friday)', 'Saturday').

    Returns:
        A styled `plotly.graph_objects.Figure` object with dark background.
    """
    fig = go.Figure()

    # Exclude non-component metadata columns
    exclude_cols = {"time", "Total_kW"}
    component_cols = [c for c in df_day.columns if c not in exclude_cols]

    # Predefined curated color palette for component area traces (vibrant dark-theme tones)
    color_palette = [
        "#3B82F6",  # Blue
        "#10B981",  # Emerald Green
        "#F59E0B",  # Amber
        "#EC4899",  # Pink
        "#8B5CF6",  # Purple
        "#14B8A6",  # Teal
        "#F97316",  # Orange
        "#06B6D4",  # Cyan
        "#84CC16",  # Lime
        "#E11D48"   # Rose
    ]

    # Add each component as a stacked area layer
    for idx, col in enumerate(component_cols):
        color = color_palette[idx % len(color_palette)]
        fig.add_trace(
            go.Scatter(
                x=df_day["time"],
                y=df_day[col],
                mode="lines",
                name=col,
                stackgroup="one",  # Enables stacking so component areas sum up visually
                line=dict(width=1.0, color=color),
                hovertemplate=f"<b>{col}</b>: %{{y:.1f}} kW<extra></extra>"
            )
        )

    # Overlay the Total Aggregated Load as a prominent bold white line
    fig.add_trace(
        go.Scatter(
            x=df_day["time"],
            y=df_day["Total_kW"],
            mode="lines",
            name="Total Grid Demand (kW)",
            line=dict(color="#FFFFFF", width=3.0),
            hovertemplate="<b>Total Demand</b>: %{y:.1f} kW at %{x}<extra></extra>"
        )
    )

    # Highlight Peak Maximum Point with a dark badge and red accent
    if not df_day["Total_kW"].empty:
        p_max = df_day["Total_kW"].max()
        max_idx = df_day["Total_kW"].idxmax()
        peak_time = df_day.loc[max_idx, "time"]

        fig.add_annotation(
            x=peak_time,
            y=p_max,
            text=f"Peak: {p_max:.1f} kW ({peak_time})",
            showarrow=True,
            arrowhead=2,
            arrowsize=1,
            arrowcolor="#EF4444",
            ax=0,
            ay=-42,
            font=dict(color="#F87171", size=12, family="Arial Black"),
            bgcolor="rgba(15, 23, 42, 0.95)",
            bordercolor="#EF4444",
            borderwidth=1.5,
            borderpad=5
        )

    # Layout configuration: sleek dark theme, high contrast gridlines and typography
    fig.update_layout(
        template="plotly_dark",
        title=dict(
            text=f"24-Hour Load Profile ({day_name}) - 15-Minute Resolution",
            font=dict(size=17, color="#F8FAFC")
        ),
        xaxis=dict(
            title=dict(text="Time of Day (HH:MM)", font=dict(color="#CBD5E1", size=13)),
            tickfont=dict(color="#94A3B8"),
            tickmode="linear",
            dtick=8,  # Show a tick every 2 hours (8 intervals of 15 min = 2 hours)
            gridcolor="#1E293B",
            showgrid=True,
            zerolinecolor="#334155"
        ),
        yaxis=dict(
            title=dict(text="Active Electrical Power (kW)", font=dict(color="#CBD5E1", size=13)),
            tickfont=dict(color="#94A3B8"),
            rangemode="tozero",
            gridcolor="#1E293B",
            showgrid=True,
            zerolinecolor="#334155"
        ),
        hovermode="x unified",  # Unified tooltip showing all components simultaneously at that timestamp
        hoverlabel=dict(
            bgcolor="#0F172A",
            font_size=12,
            font_family="sans-serif",
            font_color="#F8FAFC"
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.32,
            xanchor="center",
            x=0.5,
            font=dict(color="#CBD5E1", size=11),
            bgcolor="rgba(15, 23, 42, 0.6)"
        ),
        margin=dict(l=40, r=20, t=50, b=90),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        height=470
    )

    return fig


def create_load_duration_curve_figure(df_year: pd.DataFrame) -> go.Figure:
    """
    Computes and plots the Annual Load Duration Curve with dark theme styling.

    Args:
        df_year: Full year 35,040-row DataFrame with 'consumption_kw'.

    Returns:
        Plotly Figure showing the sorted power demand over 8,760 annual hours.
    """
    sorted_power = np.sort(df_year["consumption_kw"].values)[::-1]
    # 35,040 intervals represent 8,760 hours in a year (each interval is 0.25h)
    hours_axis = np.linspace(0, 8760, len(sorted_power))

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=hours_axis,
            y=sorted_power,
            mode="lines",
            name="Load Duration Curve (kW)",
            line=dict(color="#38BDF8", width=2.5),
            fill="tozeroy",
            fillcolor="rgba(56, 189, 248, 0.18)",
            hovertemplate="<b>Hours</b>: %{x:.0f} h<br><b>Power</b>: %{y:.1f} kW<extra></extra>"
        )
    )

    fig.update_layout(
        template="plotly_dark",
        title=dict(
            text="Annual Load Duration Curve (8,760 Hours)",
            font=dict(size=15, color="#F8FAFC")
        ),
        xaxis=dict(
            title=dict(text="Annual Operating Hours (h)", font=dict(color="#CBD5E1", size=12)),
            tickfont=dict(color="#94A3B8"),
            gridcolor="#1E293B",
            range=[0, 8760]
        ),
        yaxis=dict(
            title=dict(text="Electrical Power (kW)", font=dict(color="#CBD5E1", size=12)),
            tickfont=dict(color="#94A3B8"),
            rangemode="tozero",
            gridcolor="#1E293B"
        ),
        hoverlabel=dict(bgcolor="#0F172A", font_color="#F8FAFC"),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        margin=dict(l=40, r=20, t=50, b=40),
        height=340
    )
    return fig


def create_component_pie_chart(component_shares: Dict[str, Any]) -> go.Figure:
    """
    Creates an interactive Donut Chart illustrating the percentage share
    of total annual energy consumption (MWh/a) per machine or subsystem in dark mode.

    Args:
        component_shares: Dictionary produced by `LoadAggregator.calculate_kpis()`.

    Returns:
        Plotly Figure donut chart.
    """
    labels = list(component_shares.keys())
    values = [info["mwh"] for info in component_shares.values()]

    # High-contrast donut colors
    pie_colors = [
        "#3B82F6", "#10B981", "#F59E0B", "#EC4899",
        "#8B5CF6", "#14B8A6", "#F97316", "#06B6D4", "#84CC16"
    ]

    fig = go.Figure(
        data=[
            go.Pie(
                labels=labels,
                values=values,
                hole=0.45,  # Donut hole for modern visual aesthetic
                marker=dict(colors=pie_colors[:len(labels)], line=dict(color="#0B0F19", width=2)),
                textinfo="label+percent",
                textfont=dict(color="#F8FAFC"),
                hovertemplate="<b>%{label}</b><br>Consumption: %{value:.2f} MWh/a (%{percent})<extra></extra>"
            )
        ]
    )

    fig.update_layout(
        template="plotly_dark",
        title=dict(text="Energy Share per Consumer (MWh/a)", font=dict(size=15, color="#F8FAFC")),
        margin=dict(l=20, r=20, t=40, b=20),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.25,
            xanchor="center",
            x=0.5,
            font=dict(color="#CBD5E1", size=11)
        ),
        plot_bgcolor="#0B0F19",
        paper_bgcolor="#0B0F19",
        height=340
    )
    return fig


# ======================================================================================
# SIDEBAR CONTROLS & PRESET SELECTOR
# ======================================================================================
def render_sidebar(aggregator: LoadAggregator) -> None:
    """
    Renders the sidebar navigation, preset selection dropdown, global baseload controls,
    and simulation year configuration.

    Args:
        aggregator: Active LoadAggregator instance from session state.
    """
    st.sidebar.image(
        "https://raw.githubusercontent.com/feathericons/feather/master/icons/zap.svg",
        width=48
    )
    st.sidebar.title("Load Profile Simulator")
    st.sidebar.markdown("**DRACBV Energy Modeling Engine**")
    st.sidebar.divider()

    # ----------------------------------------------------------------------------------
    # 1. Preset Profile Selection
    # ----------------------------------------------------------------------------------
    st.sidebar.subheader("1. Profile Presets")
    preset_names = list(PRESET_OPTIONS.keys())

    # Locate current index for the selectbox
    current_index = 0
    if st.session_state.selected_preset_key in preset_names:
        current_index = preset_names.index(st.session_state.selected_preset_key)

    chosen_preset = st.sidebar.selectbox(
        "Select Profile Preset:",
        options=preset_names,
        index=current_index,
        help="Choose an industry-tailored preset with preconfigured machines, time windows, and startup peaks."
    )

    # Button to explicitly reload / reset the selected preset
    if st.sidebar.button("🔄 Load / Reset Selected Preset", use_container_width=True):
        load_selected_preset(chosen_preset)
        st.rerun()

    st.sidebar.divider()

    # ----------------------------------------------------------------------------------
    # 2. Standby / Baseload Configuration
    # ----------------------------------------------------------------------------------
    st.sidebar.subheader("2. Continuous Standby Baseload")
    aggregator.baseline_enabled = st.sidebar.toggle(
        "Enable Baseload",
        value=aggregator.baseline_enabled,
        help="Enables a continuous 24/7 baseload (e.g., standby power, IT servers, emergency lighting)."
    )

    if aggregator.baseline_enabled:
        aggregator.baseline_power_kw = st.sidebar.number_input(
            "Baseload Power (kW):",
            min_value=0.0,
            max_value=500.0,
            value=float(aggregator.baseline_power_kw),
            step=0.5,
            help="Continuous electrical active power in kW operating 24 hours a day, 365 days a year."
        )

    st.sidebar.divider()

    # ----------------------------------------------------------------------------------
    # 3. Simulation Parameters
    # ----------------------------------------------------------------------------------
    st.sidebar.subheader("3. Simulation Parameters")
    sim_year = st.sidebar.number_input(
        "Simulation Year:",
        min_value=2020,
        max_value=2050,
        value=int(aggregator.year),
        step=1
    )
    aggregator.year = sim_year
    st.session_state.simulation_year = sim_year

    st.sidebar.info(
        "💡 **Note**: All modifications to machines, time windows, or baseload are recalculated "
        "live across all charts and KPI metrics."
    )


# ======================================================================================
# KPI METRICS DASHBOARD
# ======================================================================================
def render_kpi_dashboard(kpis: Dict[str, Any]) -> None:
    """
    Renders top-level Key Performance Indicator (KPI) cards in a 4-column responsive grid.

    Calculated Metrics:
      - Peak Demand P_max (kW): Highest instantaneous power drawn from the grid.
      - Annual Energy (MWh/a): Total electricity consumed across all 8,760 hours.
      - Workday Consumption (kWh/d): Daily energy requirement on typical production days.
      - Full Load Hours (h/a): Utilization indicator (Annual kWh / P_max).

    Args:
        kpis: Dictionary returned by `LoadAggregator.calculate_kpis()`.
    """
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-title">⚡ Peak Demand (P_max)</div>
                <div class="metric-value">{kpis['p_max_kw']:.1f} kW</div>
                <div class="metric-sub">Peak at {kpis['peak_time_workday']} on workdays</div>
            </div>
            """,
            unsafe_allow_html=True
        )

    with col2:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-title">🔋 Annual Consumption</div>
                <div class="metric-value">{kpis['annual_mwh']:.2f} MWh</div>
                <div class="metric-sub">{kpis['annual_kwh']:,.0f} kWh / year</div>
            </div>
            """,
            unsafe_allow_html=True
        )

    with col3:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-title">📅 Workday Demand (Mon-Fri)</div>
                <div class="metric-value">{kpis['workday_kwh']:.1f} kWh</div>
                <div class="metric-sub">Sat: {kpis['saturday_kwh']:.0f} kWh | Sun: {kpis['sunday_kwh']:.0f} kWh</div>
            </div>
            """,
            unsafe_allow_html=True
        )

    with col4:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-title">⏱️ Full Load Hours</div>
                <div class="metric-value">{kpis['full_load_hours']:.0f} h/a</div>
                <div class="metric-sub">Average Power: {kpis['p_avg_kw']:.1f} kW</div>
            </div>
            """,
            unsafe_allow_html=True
        )


# ======================================================================================
# COMPONENT BUILDER & DYNAMIC EDITOR
# ======================================================================================
def render_component_editor(aggregator: LoadAggregator) -> None:
    """
    Renders an interactive editor that allows the user to inspect, modify, add, or delete
    individual electrical load components and their operating time windows.

    Dynamic Capabilities:
      - Modify component name, category, nominal power (kW), count multiplier.
      - Add multiple time windows per machine (e.g. 2-shift operations).
      - Configure startup peak power (inrush kW) with specific duration (minutes).
      - Toggle active operating days of the week (Monday through Sunday).
      - Activate / Deactivate individual components without deleting them.
      - Remove or add new components dynamically.

    Args:
        aggregator: Active LoadAggregator instance from session state.
    """
    st.subheader("🧩 Configure Consumers & Machines")
    st.markdown(
        "Manage individual machines, systems, or partial loads, adjust power ratings, "
        "and configure operating schedules and inrush peak spikes."
    )

    day_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    category_options = ["Production", "HVAC", "IT & Office", "Lighting", "Mobility", "Other"]

    # Iterate over all components in the aggregator
    for idx, comp in enumerate(aggregator.components):
        # Use an expander for each component to keep the UI clean
        status_icon = "🟢" if comp.is_active else "⚪"
        expander_title = f"{status_icon} {comp.name} ({comp.nominal_power_kw} kW × {comp.count})"

        with st.expander(expander_title, expanded=False):
            st.markdown(f"**Component ID:** `{comp.id}`")

            col_a, col_b, col_c, col_d = st.columns([3, 2, 2, 1])

            with col_a:
                comp.name = st.text_input(
                    "Name / Label",
                    value=comp.name,
                    key=f"name_{comp.id}"
                )
            with col_b:
                cat_idx = category_options.index(comp.category) if comp.category in category_options else category_options.index("Other")
                comp.category = st.selectbox(
                    "Category",
                    options=category_options,
                    index=cat_idx,
                    key=f"cat_{comp.id}"
                )
            with col_c:
                comp.nominal_power_kw = st.number_input(
                    "Nominal Power (kW)",
                    min_value=0.0,
                    value=float(comp.nominal_power_kw),
                    step=1.0,
                    key=f"nom_{comp.id}"
                )
            with col_d:
                comp.count = st.number_input(
                    "Units (Count)",
                    min_value=1,
                    max_value=100,
                    value=int(comp.count),
                    step=1,
                    key=f"cnt_{comp.id}"
                )

            # Active Days Multi-checkbox selection
            st.markdown("**Active Days of Week:**")
            day_cols = st.columns(7)
            new_active_days = []
            for day_idx in range(7):
                with day_cols[day_idx]:
                    is_day_active = st.checkbox(
                        day_labels[day_idx],
                        value=(day_idx in comp.active_days),
                        key=f"day_{comp.id}_{day_idx}"
                    )
                    if is_day_active:
                        new_active_days.append(day_idx)
            comp.active_days = new_active_days

            # Time Windows Management
            st.markdown("---")
            st.markdown("**🕒 Operating Time Windows & Inrush Peaks:**")

            windows_to_remove = []
            for w_idx, win in enumerate(comp.time_windows):
                w_col1, w_col2, w_col3, w_col4, w_col5 = st.columns([2, 2, 2, 2, 1])

                with w_col1:
                    win.start_time = st.time_input(
                        f"Start #{w_idx+1}",
                        value=win.start_time,
                        step=900,  # 15-minute steps
                        key=f"start_{comp.id}_{w_idx}"
                    )
                with w_col2:
                    win.end_time = st.time_input(
                        f"End #{w_idx+1}",
                        value=win.end_time,
                        step=900,
                        key=f"end_{comp.id}_{w_idx}"
                    )
                with w_col3:
                    win.has_peak = st.checkbox(
                        "Inrush Peak?",
                        value=win.has_peak,
                        key=f"haspeak_{comp.id}_{w_idx}"
                    )
                with w_col4:
                    if win.has_peak:
                        win.peak_power_kw = st.number_input(
                            f"Peak Power (kW)",
                            min_value=float(comp.nominal_power_kw),
                            value=float(win.peak_power_kw if win.peak_power_kw is not None else comp.nominal_power_kw * 1.3),
                            step=1.0,
                            key=f"peakval_{comp.id}_{w_idx}"
                        )
                        win.peak_duration_min = st.selectbox(
                            "Duration",
                            options=[15, 30, 45, 60],
                            index=[15, 30, 45, 60].index(win.peak_duration_min) if win.peak_duration_min in [15, 30, 45, 60] else 1,
                            key=f"dur_{comp.id}_{w_idx}"
                        )
                    else:
                        st.caption("No startup peak")

                with w_col5:
                    if len(comp.time_windows) > 1:
                        if st.button("🗑️", key=f"delwin_{comp.id}_{w_idx}", help="Delete time window"):
                            windows_to_remove.append(w_idx)

            # Apply window removals
            for w_idx in sorted(windows_to_remove, reverse=True):
                comp.remove_time_window(w_idx)
                st.rerun()

            # Add Time Window button
            if st.button(f"➕ Add Time Window ({comp.name})", key=f"addwin_{comp.id}"):
                comp.add_time_window(
                    start_time=datetime.time(8, 0),
                    end_time=datetime.time(16, 0)
                )
                st.rerun()

            # Component Actions (Toggle active status / Delete component)
            st.markdown("---")
            action_col1, action_col2 = st.columns([3, 1])
            with action_col1:
                comp.is_active = st.toggle(
                    "Component Active (Include in simulation)",
                    value=comp.is_active,
                    key=f"active_{comp.id}"
                )
            with action_col2:
                if st.button("❌ Delete Component", key=f"delcomp_{comp.id}", type="secondary"):
                    aggregator.remove_component(comp.id)
                    st.rerun()

    # ----------------------------------------------------------------------------------
    # Add New Component Form
    # ----------------------------------------------------------------------------------
    st.markdown("---")
    st.markdown("### ➕ Add New Consumer / Component")
    with st.form(key="add_new_component_form"):
        f_col1, f_col2, f_col3, f_col4 = st.columns(4)
        with f_col1:
            new_name = st.text_input("Component Name", value="New Machine")
        with f_col2:
            new_cat = st.selectbox(
                "Category",
                options=category_options
            )
        with f_col3:
            new_power = st.number_input("Nominal Power (kW)", min_value=0.1, value=25.0, step=1.0)
        with f_col4:
            new_count = st.number_input("Number of Units", min_value=1, value=1, step=1)

        t_col1, t_col2 = st.columns(2)
        with t_col1:
            new_start = st.time_input("Start Time", value=datetime.time(7, 0), step=900)
        with t_col2:
            new_end = st.time_input("End Time", value=datetime.time(16, 0), step=900)

        submitted = st.form_submit_button("✅ Add Component to Simulation", use_container_width=True)

        if submitted:
            new_comp = LoadComponent(
                name=new_name,
                category=new_cat,
                nominal_power_kw=new_power,
                count=new_count,
                time_windows=[TimeWindow(start_time=new_start, end_time=new_end)],
                active_days=[0, 1, 2, 3, 4],  # Mon-Fri by default
                is_active=True
            )
            aggregator.add_component(new_comp)
            st.success(f"Component '{new_name}' ({new_power} kW) successfully added!")
            st.rerun()


# ======================================================================================
# DATA EXPORT FACILITY
# ======================================================================================
def render_export_section(aggregator: LoadAggregator) -> None:
    """
    Generates downloadable CSV datasets for both the 24-hour daily curve and the
    complete 35,040-interval annual time series.

    Why high-resolution CSV export is important:
    --------------------------------------------
    Battery storage sizing algorithms, PV self-consumption calculators, and power flow
    simulations require minute-level or 15-minute standard time series. Providing standard
    CSV exports allows seamless integration with tools like PV*SOL, HOMER, or internal solvers.

    Args:
        aggregator: Active LoadAggregator instance.
    """
    st.subheader("💾 Data Export (CSV / Time Series)")
    st.markdown(
        "Export the computed load profiles as standardized 15-minute time series "
        "for battery storage sizing, PV self-consumption analysis, or grid compatibility simulations."
    )

    exp_col1, exp_col2 = st.columns(2)

    with exp_col1:
        st.markdown("**1. Full Annual Load Profile (35,040 Data Points)**")
        df_year = aggregator.get_yearly_dataframe()
        csv_year = df_year.to_csv(index=False, sep=";").encode("utf-8")

        st.download_button(
            label="📥 Download Annual Profile (CSV)",
            data=csv_year,
            file_name=f"load_profile_annual_{aggregator.year}.csv",
            mime="text/csv",
            use_container_width=True
        )

    with exp_col2:
        st.markdown("**2. 24-Hour Daily Profile (96 Data Points)**")
        df_day = aggregator.get_daily_dataframe(day_of_week=0)
        csv_day = df_day.to_csv(index=False, sep=";").encode("utf-8")

        st.download_button(
            label="📥 Download 24h Workday Profile (CSV)",
            data=csv_day,
            file_name="load_profile_24h_workday.csv",
            mime="text/csv",
            use_container_width=True
        )


# ======================================================================================
# METHODOLOGY & TECHNICAL DOCUMENTATION
# ======================================================================================
def render_technical_documentation() -> None:
    """
    Renders an in-app technical documentation guide explaining the underlying mathematical
    models, time-window discretization, inrush peaks, overnight shifts, and KPI definitions.
    """
    with st.expander("📖 Mathematical Methodology & Simulator Architecture (Documentation)", expanded=False):
        st.markdown(
            """
            ### 1. 15-Minute Time Discretization
            European power grids and modern digital energy meters operate on the standard
            **15-minute (quarter-hour) resolution**.
            - A single 24-hour day consists of $24 \\text{ hours} \\times 4 = 96 \\text{ intervals}$.
            - A standard non-leap year consists of $365 \\times 96 = 35,040 \\text{ data points}$.
            - Energy integration per interval:
              $$E_{\\text{interval}} \\text{ [kWh]} = P \\text{ [kW]} \\times \\Delta t \\text{ [h]} = P \\times 0.25$$

            ---

            ### 2. Multi-Shift Operations & Overnight Schedules (Midnight Wrap-Around)
            - Standard same-day time window: $T_{\\text{start}} < T_{\\text{end}}$ (e.g., 08:00 to 16:00).
            - **Overnight shift**: $T_{\\text{start}} > T_{\\text{end}}$ (e.g., 22:00 to 06:00).
              The simulation activates the component if current slot $t \\ge T_{\\text{start}}$ **OR** $t < T_{\\text{end}}$.

            ---

            ### 3. Startup Inrush Peaks (Load Spikes)
            Many heavy industrial loads (induction furnaces, compressors, heat pumps) draw higher
            electrical power during the initial startup or heating phase:
            $$P(t) = \\begin{cases}
            P_{\\text{peak}}, & \\text{if } T_{\\text{start}} \\le t < T_{\\text{start}} + \\Delta t_{\\text{peak}} \\\\
            P_{\\text{nominal}}, & \\text{otherwise during operational window}
            \\end{cases}$$

            ---

            ### 4. Aggregation Logic & Key Performance Indicators (KPIs)
            - **Total Grid Load at any timestamp:**
              $$P_{\\text{total}}(t) = P_{\\text{baseload}} + \\sum_{i=1}^{N} \\left( P_i(t) \\times \\text{Count}_i \\right)$$
            - **Annual Electricity Consumption:**
              $$E_{\\text{annual}} \\text{ [kWh]} = \\sum_{k=1}^{35,040} P_{\\text{total}}(t_k) \\times 0.25$$
            - **Full Load Hours ($T_{\\text{full}}$ / Vollbenutzungsstunden):**
              $$T_{\\text{full}} \\text{ [h/a]} = \\frac{E_{\\text{annual}} \\text{ [kWh]}}{P_{\\max} \\text{ [kW]}}$$
            """
        )


# ======================================================================================
# MAIN APPLICATION CONTROLLER
# ======================================================================================
def main() -> None:
    """
    Main application orchestration function.
    Coordinates session state, sidebar controls, KPI dashboard, interactive charts,
    component management, data exports, and documentation.
    """
    # 1. Initialize page layout and theme
    configure_page()

    # 2. Setup or retrieve session state
    init_session_state()
    aggregator: LoadAggregator = st.session_state.aggregator

    # 3. Render sidebar controls (Preset selection, Baseload power, Simulation year)
    render_sidebar(aggregator)

    # 4. App Header
    st.title("⚡ DRACBV Energy & Load Profile Simulator")
    st.markdown(
        "Modular electrical load profile synthesis for industry, commercial buildings, HVAC, and EV mobility. "
        "Synthesize realistic 15-minute load curves featuring inrush peak spikes, multi-shift operations, and standby baseloads."
    )

    # Display active preset badge
    st.caption(f"Active Profile: **{st.session_state.selected_preset_key}** | Simulation Year: **{aggregator.year}**")

    # 5. Calculate Energy KPIs
    kpis = aggregator.calculate_kpis()

    # 6. Render top KPI cards
    render_kpi_dashboard(kpis)

    st.markdown("---")

    # 7. Tab-based Layout for Visualizations, Component Editor, and Exports
    tab_charts, tab_editor, tab_export, tab_info = st.tabs([
        "📊 Load Profiles & Charts",
        "⚙️ Manage Components & Machines",
        "💾 Data Export (CSV)",
        "ℹ️ Methodology & Documentation"
    ])

    # ----------------------------------------------------------------------------------
    # TAB 1: Visualizations & Charts
    # ----------------------------------------------------------------------------------
    with tab_charts:
        st.subheader("📈 24-Hour Load Profile")

        # Day selection filter (Workday vs Saturday vs Sunday)
        day_options = {
            "Workday (Monday - Friday)": 0,
            "Saturday": 5,
            "Sunday": 6
        }
        chosen_day_label = st.radio(
            "Select Day Type:",
            options=list(day_options.keys()),
            horizontal=True
        )
        selected_dow = day_options[chosen_day_label]

        # Generate 96-step daily dataframe and display stacked Plotly chart
        df_day = aggregator.get_daily_dataframe(day_of_week=selected_dow)
        fig_daily = create_daily_profile_figure(df_day, chosen_day_label)
        st.plotly_chart(fig_daily, use_container_width=True)

        st.markdown("---")

        # Annual Duration Curve & Component Energy Breakdown
        col_chart_left, col_chart_right = st.columns([1, 1])

        with col_chart_left:
            df_year = aggregator.get_yearly_dataframe()
            fig_duration = create_load_duration_curve_figure(df_year)
            st.plotly_chart(fig_duration, use_container_width=True)

        with col_chart_right:
            if kpis["component_shares"]:
                fig_pie = create_component_pie_chart(kpis["component_shares"])
                st.plotly_chart(fig_pie, use_container_width=True)
            else:
                st.info("No active components available to calculate energy breakdown.")

    # ----------------------------------------------------------------------------------
    # TAB 2: Dynamic Component Builder & Manager
    # ----------------------------------------------------------------------------------
    with tab_editor:
        render_component_editor(aggregator)

    # ----------------------------------------------------------------------------------
    # TAB 3: CSV Export
    # ----------------------------------------------------------------------------------
    with tab_export:
        render_export_section(aggregator)

    # ----------------------------------------------------------------------------------
    # TAB 4: Technical Methodology & Equations
    # ----------------------------------------------------------------------------------
    with tab_info:
        render_technical_documentation()


if __name__ == "__main__":
    main()