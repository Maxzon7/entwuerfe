"""
========================================================================================
Consumer Management & Forms (current_model/ui/tab1_consumption/synthetic/forms.py)
========================================================================================

Description:
------------
Streamlit form components for:
  - Adding new electrical machines with operating windows and startup peaks.
  - Extended options for weekly schedule (Monday..Sunday) and seasonal profiles.
  - Editing and deleting existing consumer assets.
"""

import datetime
from typing import List, Dict
import streamlit as st
from current_model.models.load_component import SimpleConsumer, TimeWindow

WEEKDAY_LABELS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
WEEKDAY_TO_INT = {name: idx for idx, name in enumerate(WEEKDAY_LABELS)}
INT_TO_WEEKDAY = {idx: name for idx, name in enumerate(WEEKDAY_LABELS)}


def render_add_consumer_form(consumers: List[SimpleConsumer]) -> None:
    """Renders the form to add a new consumer with fast defaults and optional extended schedule options."""
    st.subheader("Add New Consumer")
    window_count = st.number_input(
        "Operating Windows count per day:",
        min_value=1,
        max_value=4,
        value=1,
        step=1,
        key="add_win_count"
    )

    with st.form("add_consumer_form"):
        col_n1, col_n2, col_n3 = st.columns([4, 3, 2])
        with col_n1:
            new_name = st.text_input("Consumer Name", value=f"Machine {len(consumers) + 1}")
        with col_n2:
            new_power = st.number_input("Nominal Power (kW)", min_value=0.1, value=20.0, step=1.0)
        with col_n3:
            new_count = st.number_input("Count / Units", min_value=1, value=1, step=1)

        new_windows = []
        for w_i in range(int(window_count)):
            st.markdown(f"**Operating Window {w_i + 1}:**")
            w_c1, w_c2 = st.columns(2)
            with w_c1:
                default_start = datetime.time(8, 0) if w_i == 0 else datetime.time(14, 0)
                w_start = st.time_input(f"Start Time (W{w_i+1})", value=default_start, step=900, key=f"add_start_{w_i}")
            with w_c2:
                default_end = datetime.time(16, 0) if w_i == 0 else datetime.time(18, 0)
                w_end = st.time_input(f"End Time (W{w_i+1})", value=default_end, step=900, key=f"add_end_{w_i}")

            w_has_peak = st.checkbox(f"Include Startup Peak? (W{w_i+1})", key=f"add_has_peak_{w_i}")
            p_col1, p_col2 = st.columns(2)
            with p_col1:
                w_peak_power = st.number_input(
                    f"Peak Power kW (W{w_i+1})",
                    min_value=0.0,
                    value=float(new_power * 1.5),
                    step=1.0,
                    key=f"add_peak_p_{w_i}"
                )
            with p_col2:
                w_peak_dur = st.selectbox(
                    f"Peak Duration min (W{w_i+1})",
                    options=[15, 30, 45, 60],
                    index=1,
                    key=f"add_peak_d_{w_i}"
                )

            new_windows.append(
                TimeWindow(
                    start_time=w_start,
                    end_time=w_end,
                    has_peak=w_has_peak,
                    peak_power_kw=w_peak_power if w_has_peak else new_power,
                    peak_duration_min=w_peak_dur
                )
            )

        # Extended Options inside Form
        with st.expander("Extended Options: Weekly Schedule & Seasonality", expanded=False):
            selected_days = st.multiselect(
                "Active Operating Days:",
                options=WEEKDAY_LABELS,
                default=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
                key="add_active_days"
            )

            season_options = [
                ("flat", "Flat (Constant 100% year-round)"),
                ("winter_heavy", "Winter-Heavy (+25% in Winter / Heating)"),
                ("summer_heavy", "Summer-Heavy (+30% in Summer / Cooling)")
            ]
            season_idx = st.selectbox(
                "Seasonal Load Profile:",
                options=[s[1] for s in season_options],
                index=0,
                key="add_season_pattern"
            )
            selected_pattern = [s[0] for s in season_options if s[1] == season_idx][0]

        submitted = st.form_submit_button("Add Consumer", type="primary", use_container_width=True)
        if submitted:
            active_day_ints = [WEEKDAY_TO_INT[d] for d in selected_days] if selected_days else [0, 1, 2, 3, 4]
            new_consumer = SimpleConsumer(
                name=new_name,
                power_kw=new_power,
                count=new_count,
                active_days=active_day_ints,
                seasonal_pattern=selected_pattern,
                time_windows=new_windows
            )
            consumers.append(new_consumer)
            st.rerun()


def render_consumer_editor(consumers: List[SimpleConsumer]) -> None:
    """Renders expanders allowing editing and deleting existing consumers."""
    st.subheader("Current Consumers & Editor")
    if not consumers:
        st.info("No consumers defined. Add a consumer on the left.")
        return

    for idx, c in enumerate(consumers):
        # Format active days string
        c_days_str = "Mo-Fr" if getattr(c, "active_days", [0, 1, 2, 3, 4]) == [0, 1, 2, 3, 4] else f"{len(getattr(c, 'active_days', []))} Days"
        c_count_str = f" x{c.count}" if getattr(c, "count", 1) > 1 else ""

        with st.expander(f"{c.name} ({c.power_kw:.1f} kW{c_count_str}) — {len(c.time_windows)} Window(s) | {c_days_str}", expanded=False):
            with st.form(key=f"edit_consumer_form_{c.id}"):
                col_e1, col_e2, col_e3 = st.columns([4, 3, 2])
                with col_e1:
                    edit_name = st.text_input("Name:", value=c.name, key=f"edit_name_{c.id}")
                with col_e2:
                    edit_power = st.number_input(
                        "Nominal Power (kW):",
                        min_value=0.1,
                        value=float(c.power_kw),
                        step=1.0,
                        key=f"edit_power_{c.id}"
                    )
                with col_e3:
                    edit_count = st.number_input(
                        "Count:",
                        min_value=1,
                        value=int(getattr(c, "count", 1)),
                        step=1,
                        key=f"edit_count_{c.id}"
                    )

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
                        e_peak_p = st.number_input(
                            "Peak Power (kW):",
                            min_value=0.0,
                            value=float(w.peak_power_kw if w.has_peak else edit_power * 1.5),
                            step=1.0,
                            key=f"e_peak_p_{c.id}_{w_idx}"
                        )
                    with ep_c2:
                        default_dur_idx = [15, 30, 45, 60].index(w.peak_duration_min) if w.peak_duration_min in [15, 30, 45, 60] else 1
                        e_peak_d = st.selectbox(
                            "Peak Duration (min):",
                            options=[15, 30, 45, 60],
                            index=default_dur_idx,
                            key=f"e_peak_d_{c.id}_{w_idx}"
                        )

                    updated_windows.append(
                        TimeWindow(
                            start_time=e_start,
                            end_time=e_end,
                            has_peak=e_has_peak,
                            peak_power_kw=e_peak_p if e_has_peak else edit_power,
                            peak_duration_min=e_peak_d
                        )
                    )

                with st.expander("Schedule & Seasonality", expanded=False):
                    current_days = [INT_TO_WEEKDAY[d] for d in getattr(c, "active_days", [0, 1, 2, 3, 4]) if d in INT_TO_WEEKDAY]
                    edit_days = st.multiselect(
                        "Active Operating Days:",
                        options=WEEKDAY_LABELS,
                        default=current_days,
                        key=f"edit_days_{c.id}"
                    )
                    pattern_keys = ["flat", "winter_heavy", "summer_heavy"]
                    curr_pat = getattr(c, "seasonal_pattern", "flat")
                    pat_idx = pattern_keys.index(curr_pat) if curr_pat in pattern_keys else 0
                    edit_pattern = st.selectbox(
                        "Seasonal Profile:",
                        options=["Flat (Constant 100%)", "Winter-Heavy (+25% in Winter)", "Summer-Heavy (+30% in Summer)"],
                        index=pat_idx,
                        key=f"edit_pattern_{c.id}"
                    )
                    pattern_map = {
                        "Flat (Constant 100%)": "flat",
                        "Winter-Heavy (+25% in Winter)": "winter_heavy",
                        "Summer-Heavy (+30% in Summer)": "summer_heavy"
                    }

                btn_c1, btn_c2 = st.columns([3, 1])
                with btn_c1:
                    save_submitted = st.form_submit_button("Save Changes", type="primary", use_container_width=True)
                with btn_c2:
                    delete_submitted = st.form_submit_button("Delete", use_container_width=True)

                if save_submitted:
                    c.name = edit_name
                    c.power_kw = float(edit_power)
                    c.nominal_power_kw = c.power_kw
                    c.count = int(edit_count)
                    c.active_days = [WEEKDAY_TO_INT[d] for d in edit_days] if edit_days else [0, 1, 2, 3, 4]
                    c.seasonal_pattern = pattern_map.get(edit_pattern, "flat")
                    c.time_windows = updated_windows
                    st.success(f"Saved {c.name}")
                    st.rerun()

                if delete_submitted:
                    consumers.pop(idx)
                    st.rerun()
