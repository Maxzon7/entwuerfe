import datetime
import streamlit as st
from models.Load_profile import LoadProfile


def render_tab():
    with st.form(key="Loadprofile_form"):
        st.title("Loadprofile")
        
        st.header("Basic Parameters")
        name = st.text_input("Name", value="Machine 1")
        power = st.number_input("Power (kW)", min_value=0.0, value=10.0, step=0.1)
        days_per_week = st.slider("Days per week", 1, 7, 5, 1)

        st.header("Time Windows")
        col1, col2 = st.columns(2)
        with col1:
            start_time = st.time_input("Start Time", value=datetime.time(8, 0), step=900)
        with col2:
            end_time = st.time_input("End Time", value=datetime.time(16, 0), step=900)

        # Submit button MUST be inside the with st.form block!
        submitted = st.form_submit_button("Generate Load Profile")

    # This runs when the user clicks the button
    if submitted:
        # Create an instance of LoadProfile
        profile = LoadProfile(name=name, power=power, days_per_week=days_per_week)
        profile.add_time_window(start_time, end_time)

        # Generate data
        df = profile.generate()

        st.success("Load Profile successfully generated!")
        st.header("Load Profile")
        st.line_chart(df.set_index('timestamp')['consumption_kw'])