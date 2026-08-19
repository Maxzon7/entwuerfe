# To Run python -m streamlit run presentation.py

"""
========================================================================================
PRESENTATION & MODULE TESTING PLAYGROUND (presentation.py)
========================================================================================

Purpose & Scope:
----------------
This standalone file is designed for testing, demonstrating, and presenting individual
modules and algorithms independently from the main `app.py` application.

Key Notes:
----------
- You are encouraged to FREELY OVERWRITE, edit, experiment with, or adapt this file.
- It acts as a lightweight sandbox / playground.
- To run this file independently: `python -m streamlit run presentation.py`

Initial Minimal Version:
------------------------
- Focuses strictly on a SINGLE 24-HOUR DAY (96 fifteen-minute intervals).
- No complex presets or full-year calendar scheduling.
- Dynamic interface to add and manage electrical consumers (loads).
- Live 24-hour interactive load curve visualization (Plotly dark theme).
- Instant calculation of key daily energy indicators (Peak Load kW, Total Energy kWh, Average Power kW).
========================================================================================
"""

import datetime
import uuid
import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go

# --------------------------------------------------------------------------------------
# Page Setup
# --------------------------------------------------------------------------------------
st.set_page_config(
    page_title="Energy Simulator - Sandbox",
    page_icon="🧪",
    layout="wide"
)

# Dark theme card styling1
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
    </style>
    """,
    unsafe_allow_html=True
)

st.title("Presentation & Testing Playground")
st.caption("A simplified, standalone sandbox for testing modular load profiles on a single 24-hour day.")


# --------------------------------------------------------------------------------------
# Minimal Single-Day Simulation Logic
# --------------------------------------------------------------------------------------
class SimpleConsumer:
    """Represents a simplified electrical load for a 24-hour period."""
    def __init__(
        self,
        name: str,
        power_kw: float,
        start_time: datetime.time,
        end_time: datetime.time,
        has_peak: bool = False,
        peak_power_kw: float = 0.0,
        peak_duration_min: int = 30
    ):
        self.id = str(uuid.uuid4())
        self.name = name
        self.power_kw = max(0.0, float(power_kw))
        self.start_time = start_time
        self.end_time = end_time
        self.has_peak = has_peak
        self.peak_power_kw = max(self.power_kw, float(peak_power_kw)) if has_peak else self.power_kw
        self.peak_duration_min = peak_duration_min

    def get_24h_array(self) -> np.ndarray:
        """Computes a 96-element array of power (kW) for 15-minute intervals."""
        curve = np.zeros(96, dtype=float)
        start_m = self.start_time.hour * 60 + self.start_time.minute
        end_m = self.end_time.hour * 60 + self.end_time.minute
        is_24h = (start_m == 0 and end_m == 0)

        for step in range(96):
            slot_start = step * 15
            slot_end = slot_start + 15
            active = False

            if is_24h:
                active = True
            elif start_m < end_m:
                # Normal window (e.g. 08:00 to 16:00)
                if slot_start >= start_m and slot_end <= end_m:
                    active = True
                elif slot_start < end_m and slot_end > start_m:
                    active = True
            elif start_m > end_m:
                # Overnight window (e.g. 22:00 to 06:00)
                if slot_start >= start_m or slot_end <= end_m:
                    active = True
                elif slot_start < end_m or slot_end > start_m:
                    active = True

            if active:
                val = self.power_kw
                if self.has_peak:
                    if start_m < end_m:
                        if slot_start < start_m + self.peak_duration_min:
                            val = self.peak_power_kw
                    else:
                        if slot_start >= start_m and slot_start < (start_m + self.peak_duration_min):
                            val = self.peak_power_kw
                curve[step] = val

        return curve


# --------------------------------------------------------------------------------------
# Session State: Consumer List (Starts completely empty, no presets)
# --------------------------------------------------------------------------------------
if "presentation_consumers" not in st.session_state:
    st.session_state.presentation_consumers = []

consumers: list[SimpleConsumer] = st.session_state.presentation_consumers

# --------------------------------------------------------------------------------------
# Aggregate Data for the 24-Hour Day (96 steps)
# --------------------------------------------------------------------------------------
time_labels = [f"{h:02d}:{m:02d}" for h in range(24) for m in (0, 15, 30, 45)]
df_day = pd.DataFrame({"time": time_labels})
total_curve = np.zeros(96, dtype=float)

for c in consumers:
    c_curve = c.get_24h_array()
    df_day[c.name] = c_curve
    total_curve += c_curve

df_day["Total_kW"] = total_curve

# Calculate Core Metrics
peak_demand_kw = float(total_curve.max()) if len(total_curve) > 0 else 0.0
# Daily energy in kWh: sum of kW * 0.25h (15-min intervals)
daily_energy_kwh = float(total_curve.sum() * 0.25)
avg_power_kw = daily_energy_kwh / 24.0


# --------------------------------------------------------------------------------------
# KPI Cards
# --------------------------------------------------------------------------------------
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown(
        f"""
        <div class="sandbox-card">
            <div class="sandbox-title">⚡ Daily Peak Load (P_max)</div>
            <div class="sandbox-value">{peak_demand_kw:.1f} kW</div>
        </div>
        """,
        unsafe_allow_html=True
    )

with col2:
    st.markdown(
        f"""
        <div class="sandbox-card">
            <div class="sandbox-title">🔋 Daily Energy Consumption</div>
            <div class="sandbox-value">{daily_energy_kwh:.1f} kWh</div>
        </div>
        """,
        unsafe_allow_html=True
    )

with col3:
    st.markdown(
        f"""
        <div class="sandbox-card">
            <div class="sandbox-title">📊 Average Daily Power</div>
            <div class="sandbox-value">{avg_power_kw:.1f} kW</div>
        </div>
        """,
        unsafe_allow_html=True
    )

with col4:
    st.markdown(
        f"""
        <div class="sandbox-card">
            <div class="sandbox-title">🧩 Total Consumers</div>
            <div class="sandbox-value">{len(consumers)}</div>
        </div>
        """,
        unsafe_allow_html=True
    )


# --------------------------------------------------------------------------------------
# Interactive 24h Plotly Chart (Dark Theme)
# --------------------------------------------------------------------------------------
st.subheader("📈 24-Hour Simulated Load Profile (15-Minute Resolution)")

fig = go.Figure()
color_palette = ["#3B82F6", "#10B981", "#F59E0B", "#EC4899", "#8B5CF6", "#14B8A6", "#F97316"]

# Add stacked area traces for each consumer
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

# Overlay Total Demand Line
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

fig.update_layout(
    template="plotly_dark",
    xaxis=dict(
        title="Time of Day (HH:MM)",
        tickmode="linear",
        dtick=8,
        gridcolor="#1E293B"
    ),
    yaxis=dict(
        title="Active Electrical Power (kW)",
        rangemode="tozero",
        gridcolor="#1E293B"
    ),
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=-0.28, xanchor="center", x=0.5),
    margin=dict(l=40, r=20, t=30, b=80),
    plot_bgcolor="#0B0F19",
    paper_bgcolor="#0B0F19",
    height=420
)

st.plotly_chart(fig, use_container_width=True)

st.divider()


# --------------------------------------------------------------------------------------
# Consumer Management & Add Form
# --------------------------------------------------------------------------------------
col_left, col_right = st.columns([1, 1])

with col_left:
    st.subheader("➕ Add New Consumer")
    with st.form("add_consumer_form"):
        new_name = st.text_input("Consumer Name", value=f"Machine {len(consumers) + 1}")
        new_power = st.number_input("Nominal Power (kW)", min_value=0.1, value=20.0, step=1.0)
        
        c_time1, c_time2 = st.columns(2)
        with c_time1:
            new_start = st.time_input("Start Time", value=datetime.time(8, 0), step=900)
        with c_time2:
            new_end = st.time_input("End Time", value=datetime.time(16, 0), step=900)

        new_has_peak = st.checkbox("Include Startup Inrush Peak?")
        new_peak_power = 0.0
        new_peak_dur = 30
        if new_has_peak:
            p_col1, p_col2 = st.columns(2)
            with p_col1:
                new_peak_power = st.number_input("Peak Power (kW)", min_value=float(new_power), value=float(new_power * 1.3), step=1.0)
            with p_col2:
                new_peak_dur = st.selectbox("Peak Duration (min)", options=[15, 30, 45, 60], index=1)

        submitted = st.form_submit_button("✅ Add Consumer to Day", use_container_width=True)
        if submitted:
            new_consumer = SimpleConsumer(
                name=new_name,
                power_kw=new_power,
                start_time=new_start,
                end_time=new_end,
                has_peak=new_has_peak,
                peak_power_kw=new_peak_power,
                peak_duration_min=new_peak_dur
            )
            st.session_state.presentation_consumers.append(new_consumer)
            st.rerun()

with col_right:
    st.subheader("📋 Current Consumers")
    if not consumers:
        st.info("No consumers defined. Add a consumer on the left.")
    else:
        for idx, c in enumerate(consumers):
            with st.container():
                c_col1, c_col2 = st.columns([3, 1])
                with c_col1:
                    peak_str = f" (Peak: {c.peak_power_kw} kW for {c.peak_duration_min} min)" if c.has_peak else ""
                    st.markdown(
                        f"**{idx + 1}. {c.name}**  \n"
                        f"⚡ `{c.power_kw} kW` | 🕒 `{c.start_time.strftime('%H:%M')} – {c.end_time.strftime('%H:%M')}`{peak_str}"
                    )
                with c_col2:
                    if st.button("🗑️ Delete", key=f"del_{c.id}"):
                        st.session_state.presentation_consumers.pop(idx)
                        st.rerun()
                st.markdown("---")
