"""
========================================================================================
DRACBV Energy Simulator - Tab 1: Single Load Profile Generator (tab1_baseline.py)
========================================================================================

Description:
------------
This module provides a streamlined single-component Load Profile Generator.
It allows users to quickly define a single machine's power rating, active operating days,
and operational time window, generating a full 1-year 15-minute time series.

Module Design:
--------------
- Encapsulated inside `render_tab()` to allow modular inclusion in multi-tab Streamlit apps.
- Uses `st.form` to batch user inputs and prevent unnecessary reruns until submission.
"""

import datetime
import streamlit as st
import pandas as pd
from models.Load_profile import LoadProfile


def render_tab() -> None:
    """
    Renders the simple single-component load profile generator tab.

    Execution Flow:
    ---------------
    1. Collects basic machine parameters: Name, Power Rating (kW), Days per week.
    2. Collects operating time window (Start Time and End Time in 15-minute increments).
    3. On form submission, instantiates `LoadProfile`, computes the 1-year time series,
       and renders an interactive line chart and summary statistics.
    """
    with st.form(key="Loadprofile_form"):
        st.title("Single Load Profile Generator")
        st.caption("Generate a 15-minute resolution annual load curve for an individual machine or system.")

        st.header("1. Basic Parameters")
        name = st.text_input("Component Name", value="Machine 1", help="Descriptive identifier for this machine.")
        power = st.number_input(
            "Nominal Power (kW)",
            min_value=0.0,
            value=10.0,
            step=0.5,
            help="Electrical active power consumption during operation in kilowatts."
        )
        days_per_week = st.slider(
            "Operating Days per Week",
            min_value=1,
            max_value=7,
            value=5,
            step=1,
            help="5 = Monday to Friday (standard work week), 7 = continuous weekly operation."
        )

        st.header("2. Operating Time Window")
        col1, col2 = st.columns(2)
        with col1:
            start_time = st.time_input("Start Time", value=datetime.time(8, 0), step=900)
        with col2:
            end_time = st.time_input("End Time", value=datetime.time(16, 0), step=900)

        # The submit button triggers the computation within this form
        submitted = st.form_submit_button("⚡ Generate Load Profile", use_container_width=True)

    # Output section displayed after form submission
    if submitted:
        # Step 1: Instantiate the LoadProfile model
        profile = LoadProfile(name=name, power=power, days_per_week=days_per_week)
        profile.add_time_window(start_time, end_time)

        # Step 2: Generate the 1-year 15-minute time series DataFrame
        df: pd.DataFrame = profile.generate()

        # Step 3: Compute basic energy indicators
        total_energy_kwh = float(df["consumption_kw"].sum() * 0.25)
        total_energy_mwh = total_energy_kwh / 1000.0
        peak_demand_kw = float(df["consumption_kw"].max())

        st.success(f"Load profile for '{name}' successfully generated!")

        # Step 4: Display summary KPI metrics
        metric_col1, metric_col2, metric_col3 = st.columns(3)
        with metric_col1:
            st.metric("Peak Demand", f"{peak_demand_kw:.1f} kW")
        with metric_col2:
            st.metric("Annual Energy", f"{total_energy_mwh:.2f} MWh/a", f"{total_energy_kwh:,.0f} kWh")
        with metric_col3:
            st.metric("Total Intervals", f"{len(df):,} (15-min)")

        # Step 5: Render the time-series chart
        st.subheader("Load Profile Preview (First 7 Days)")
        # Preview first 7 days (7 * 96 = 672 intervals)
        preview_df = df.iloc[:672]
        st.line_chart(preview_df.set_index("timestamp")["consumption_kw"])