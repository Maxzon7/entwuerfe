"""
========================================================================================
Synthetic Load Simulator View (current_model/ui/tab1_consumption/synthetic/view.py)
========================================================================================

Description:
------------
Main orchestrator for the Synthetic 24-Hour & 365-Day Annual Load Simulator:
  - Presets loader (Industry, Office, EV Hub) and custom consumer forms.
  - Horizon selector: 24-Hour Typical Day vs. Full Year (365 Days / 35,040 steps).
  - System-wide custom public holiday calendar editor (treated as Sundays).
  - Annual and daily KPI metric cards.
  - Interactive 24h stacked profile, 365-day timeseries with rangeslider, and 2D load heatmap.
  - Real-time grid capacity overload violation analysis.
"""

import io
import os
import zipfile
from typing import List, Dict, Any, Optional
import streamlit as st
import numpy as np
import pandas as pd

from current_model.models.load_component import (
    SimpleConsumer,
    consumers_to_drac,
    consumers_from_drac
)
from current_model.models.presets import (
    PRESET_FACTORIES,
    PRESET_TEMPLATES,
    get_preset_factory,
    get_industry_preset_consumers
)
from current_model.core.synthetic_engine import aggregate_synthetic_24h, aggregate_synthetic_year
from current_model.ui.common.cards import render_kpi_card
from current_model.ui.tab1_consumption.synthetic.charts import (
    create_synthetic_profile_figure,
    create_annual_synthetic_figure,
    create_annual_heatmap_figure
)
from current_model.ui.tab1_consumption.synthetic.forms import render_add_consumer_form, render_consumer_editor


def _parse_uploaded_profile_files(uploaded_files: List[Any]) -> Dict[str, List[SimpleConsumer]]:
    """Parses one or multiple .drac, .json, or .zip files containing consumer profiles."""
    parsed: Dict[str, List[SimpleConsumer]] = {}
    if not uploaded_files:
        return parsed

    for f in uploaded_files:
        fname = getattr(f, "name", "profile.drac")
        if fname.lower().endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(f.getvalue())) as z:
                    for member in z.namelist():
                        if member.lower().endswith((".drac", ".json")) and not member.startswith("__MACOSX"):
                            try:
                                raw_data = z.read(member).decode("utf-8")
                                loaded = consumers_from_drac(raw_data)
                                if loaded:
                                    base_member = os.path.basename(member)
                                    parsed[base_member or member] = loaded
                            except Exception:
                                continue
            except Exception:
                continue
        else:
            try:
                raw_data = f.getvalue().decode("utf-8")
                loaded = consumers_from_drac(raw_data)
                if loaded:
                    parsed[fname] = loaded
            except Exception:
                continue
    return parsed
import re


def render_synthetic_simulator(key_prefix: str = "synthetic") -> None:
    """
    Renders the bottom-up synthetic load simulator supporting 24h daily and 365d annual horizons.
    """
    state_consumers_key = f"{key_prefix}_consumers"
    state_holidays_key = f"{key_prefix}_holidays_df"

    # Initialize default industry consumers if not yet set
    if state_consumers_key not in st.session_state:
        st.session_state[state_consumers_key] = get_industry_preset_consumers()

    consumers: List[SimpleConsumer] = st.session_state[state_consumers_key]

    # Initialize system-wide holidays table (default: empty list as requested)
    if state_holidays_key not in st.session_state:
        st.session_state[state_holidays_key] = pd.DataFrame(columns=["date", "holiday_name"])

    # 1. Preset & File Transfer Toolbar (.drac / Templates)
    with st.expander("Profile Presets & File Transfer (.drac)", expanded=True):
        f_col1, f_col2 = st.columns([1, 1])

        # LEFT: Upload & Predefined Templates
        with f_col1:
            st.markdown("##### Import Profile(s) / Templates")
            uploaded_profiles = st.file_uploader(
                "Upload `.drac`, `.json` or `.zip` load profile(s):",
                type=["drac", "json", "zip"],
                accept_multiple_files=True,
                key=f"{key_prefix}_profile_uploader",
                help="Upload one or multiple .drac profile files (or a .zip folder) to restore consumer assets and schedules."
            )
            loaded_profiles_dict_key = f"{key_prefix}_loaded_profiles_dict"
            prof_uploader_sig_key = f"{key_prefix}_last_profiles_sig"

            if loaded_profiles_dict_key not in st.session_state:
                st.session_state[loaded_profiles_dict_key] = {}

            if uploaded_profiles:
                current_sig = "|".join(sorted([f"{f.name}_{f.size}" for f in uploaded_profiles]))
                if st.session_state.get(prof_uploader_sig_key) != current_sig:
                    new_profiles = _parse_uploaded_profile_files(uploaded_profiles)
                    if new_profiles:
                        st.session_state[loaded_profiles_dict_key] = new_profiles
                        st.session_state[prof_uploader_sig_key] = current_sig
                        first_label = list(new_profiles.keys())[0]
                        st.session_state[state_consumers_key] = new_profiles[first_label]
                        st.session_state[f"{key_prefix}_active_profile_label"] = first_label
                        st.success(f"Successfully imported **{len(new_profiles)}** profile(s)!")
                        st.rerun()
                    else:
                        st.error("No valid load profiles (.drac or .json) found in uploaded file(s).")

            # Dynamic Switcher if multiple profiles are loaded
            loaded_prof_dict = st.session_state.get(loaded_profiles_dict_key, {})
            if loaded_prof_dict:
                prof_labels = list(loaded_prof_dict.keys())
                curr_prof_sel = st.session_state.get(f"{key_prefix}_active_profile_label", prof_labels[0])
                p_sel_idx = prof_labels.index(curr_prof_sel) if curr_prof_sel in prof_labels else 0

                selected_prof_label = st.selectbox(
                    "📑 Switch Active Profile:",
                    options=prof_labels,
                    index=p_sel_idx,
                    key=f"{key_prefix}_switch_profile_select"
                )
                if selected_prof_label != st.session_state.get(f"{key_prefix}_active_profile_label"):
                    st.session_state[f"{key_prefix}_active_profile_label"] = selected_prof_label
                    st.session_state[state_consumers_key] = loaded_prof_dict[selected_prof_label]
                    st.rerun()

            preset_names = list(PRESET_TEMPLATES.keys())
            selected_preset = st.selectbox(
                "Or load an industry preset:",
                options=["-- Select a Template --"] + preset_names,
                index=0,
                key=f"{key_prefix}_preset_select"
            )
            p_btn1, p_btn2 = st.columns(2)
            with p_btn1:
                if selected_preset in PRESET_TEMPLATES:
                    if st.button("Apply Template", key=f"{key_prefix}_apply_preset", use_container_width=True):
                        st.session_state[state_consumers_key] = PRESET_TEMPLATES[selected_preset]()
                        st.rerun()
            with p_btn2:
                if st.button("Clear All Assets", key=f"{key_prefix}_clear_btn", use_container_width=True):
                    st.session_state[state_consumers_key] = []
                    st.rerun()

        # RIGHT: Download / Export as .drac
        with f_col2:
            st.markdown("##### Export Profile")
            profile_name_input = st.text_input(
                "Profile Name:",
                value="Synthetic Load Profile",
                key=f"{key_prefix}_profile_name_input"
            )
            default_drac_base = re.sub(r'[^a-zA-Z0-9_-]', '_', profile_name_input.lower().strip()) or "load_profile"
            custom_prof_filename = st.text_input(
                "Custom Download Filename (.drac):",
                value=f"{default_drac_base}.drac",
                key=f"{key_prefix}_prof_filename_input"
            )
            if not custom_prof_filename.strip().lower().endswith(".drac"):
                custom_prof_filename = custom_prof_filename.strip() + ".drac"

            drac_profile_content = consumers_to_drac(consumers, profile_name=profile_name_input)
            st.download_button(
                label=f"Download Profile as `{custom_prof_filename}`",
                data=drac_profile_content,
                file_name=custom_prof_filename,
                mime="application/json",
                key=f"{key_prefix}_prof_download_btn",
                use_container_width=True,
                type="secondary",
                disabled=len(consumers) == 0
            )
            st.caption(f"Active profile has **{len(consumers)}** consumer assets.")


    # 2. System-wide Holiday Calendar Expander (Treated as Sundays)
    with st.expander("System-wide Holiday Calendar (Treated as Sundays)", expanded=False):
        st.caption("Add specific holiday dates (YYYY-MM-DD) which will automatically be simulated using the Sunday schedule.")
        edited_holidays = st.data_editor(
            st.session_state[state_holidays_key],
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "date": st.column_config.TextColumn("Date (YYYY-MM-DD or DD.MM.YYYY)", required=True),
                "holiday_name": st.column_config.TextColumn("Holiday / Shutdown Name")
            },
            key=f"{key_prefix}_holiday_editor"
        )
        st.session_state[state_holidays_key] = edited_holidays

    holiday_list = []
    if not edited_holidays.empty and "date" in edited_holidays.columns:
        holiday_list = edited_holidays["date"].dropna().astype(str).tolist()

    # 3. Horizon Selector: 24h vs. 365 Days
    h_col1, h_col2 = st.columns([4, 6])
    with h_col1:
        horizon_mode = st.radio(
            "Simulation Horizon:",
            options=["24-Hour Typical Day", "Full Year (365 Days / 35,040 Steps)"],
            horizontal=True,
            key=f"{key_prefix}_horizon"
        )

    # 4. Simulation Calculations
    if not consumers:
        st.info("No active consumers in profile. Add machines below or load a template above.")
        c_col1, c_col2 = st.columns([1, 1])
        with c_col1:
            render_add_consumer_form(consumers)
        with c_col2:
            render_consumer_editor(consumers)
        return

    # Calculate 24h baseline
    df_day, total_curve_24h, metrics_24h = aggregate_synthetic_24h(consumers)

    # Calculate 365-day annual timeseries on-demand only when Full Year is active
    is_full_year = horizon_mode.startswith("Full Year")
    if is_full_year:
        df_year, total_curve_year, metrics_year = aggregate_synthetic_year(
            consumers=consumers,
            year=2025,
            holidays=holiday_list
        )
        active_synthetic_dataset = df_year
    else:
        df_year, total_curve_year, metrics_year = None, None, None
        active_synthetic_dataset = df_day

    # Store active dataset in session state so Tab 2 can automatically read it
    st.session_state[f"{key_prefix}_active_df"] = active_synthetic_dataset
    st.session_state["active_synthetic_df"] = active_synthetic_dataset


    # 5. KPI Cards
    if horizon_mode.startswith("24-Hour"):
        k1, k2, k3, k4 = st.columns(4)
        with k1:
            render_kpi_card("Peak Demand", f"{metrics_24h['peak_demand_kw']:.1f} kW", "Max instantaneous power")
        with k2:
            render_kpi_card("Daily Energy", f"{metrics_24h['daily_energy_kwh']:,.1f} kWh", "Sum across 24h cycle")
        with k3:
            render_kpi_card("Average Power", f"{metrics_24h['avg_power_kw']:.1f} kW", "Average continuous load")
        with k4:
            render_kpi_card("Active Assets", f"{metrics_24h['consumer_count']}", "Total machines in profile")
    else:
        k1, k2, k3, k4 = st.columns(4)
        with k1:
            render_kpi_card("Annual Energy", f"{metrics_year['annual_energy_mwh']:,.2f} MWh", f"{metrics_year['annual_energy_kwh']:,.0f} kWh")
        with k2:
            render_kpi_card("Annual Peak Demand", f"{metrics_year['peak_demand_kw']:.1f} kW", "Max measured power")
        with k3:
            render_kpi_card("Full Load Hours", f"{metrics_year['full_load_hours']:,.0f} h/a", f"Load Factor: {metrics_year['load_factor_pct']:.1f}%")
        with k4:
            render_kpi_card("Average Power", f"{metrics_year['avg_demand_kw']:.1f} kW", f"Across {metrics_year['days_count']} days")

    # 6. Compact Grid Limit Option
    g_col1, g_col2 = st.columns([1, 1])
    with g_col1:
        enable_grid_limit = st.toggle(
            "Enable Grid Capacity Limit",
            value=False,
            help="Define a maximum grid connection capacity limit and analyze overload violations.",
            key=f"{key_prefix}_grid_limit_toggle"
        )
    with g_col2:
        if enable_grid_limit:
            ref_peak = metrics_year['peak_demand_kw'] if horizon_mode.startswith("Full Year") else metrics_24h['peak_demand_kw']
            grid_limit_kw = st.number_input(
                "Max Grid Capacity Limit (kW):",
                min_value=5.0,
                max_value=5000.0,
                value=float(np.round(ref_peak * 0.8, 0)) if ref_peak > 0 else 100.0,
                step=5.0,
                key=f"{key_prefix}_grid_limit_val"
            )
        else:
            grid_limit_kw = None

    # 7. Visualizations
    if horizon_mode.startswith("24-Hour"):
        fig_24h = create_synthetic_profile_figure(
            df_day=df_day,
            consumers=consumers,
            grid_limit_kw=grid_limit_kw
        )
        st.plotly_chart(fig_24h, use_container_width=True)

        if enable_grid_limit and grid_limit_kw:
            overload_diff = (total_curve_24h - grid_limit_kw).clip(min=0.0)
            overload_peak = float(overload_diff.max())
            overload_hours = float((total_curve_24h > grid_limit_kw).sum() * 0.25)
            overload_kwh = float(overload_diff.sum() * 0.25)
            has_violation = overload_peak > 0.0

            st.markdown("#### Grid Capacity Overload Analysis")
            o1, o2, o3 = st.columns(3)
            with o1:
                render_kpi_card(
                    "Overload Peak" if has_violation else "Grid Status",
                    f"+{overload_peak:.1f} kW" if has_violation else "Within Limit",
                    f"Max Limit: {grid_limit_kw:.1f} kW",
                    status="alert" if has_violation else "ok"
                )
            with o2:
                render_kpi_card("Overload Duration", f"{overload_hours:.2f} hrs", "Violation duration")
            with o3:
                render_kpi_card("Overload Energy", f"{overload_kwh:.1f} kWh", "Excess energy over limit")

    else:
        # Annual Time Series and 2D Heatmap
        fig_annual = create_annual_synthetic_figure(
            df_year=df_year,
            grid_limit_kw=grid_limit_kw
        )
        st.plotly_chart(fig_annual, use_container_width=True)

        fig_heat = create_annual_heatmap_figure(df_year=df_year)
        st.plotly_chart(fig_heat, use_container_width=True)

        if enable_grid_limit and grid_limit_kw:
            overload_diff = (total_curve_year - grid_limit_kw).clip(min=0.0)
            overload_peak = float(overload_diff.max())
            overload_hours = float((total_curve_year > grid_limit_kw).sum() * 0.25)
            overload_kwh = float(overload_diff.sum() * 0.25)
            has_violation = overload_peak > 0.0

            st.markdown("#### Annual Grid Capacity Overload Analysis")
            o1, o2, o3 = st.columns(3)
            with o1:
                render_kpi_card(
                    "Annual Overload Peak" if has_violation else "Grid Status",
                    f"+{overload_peak:.1f} kW" if has_violation else "Within Limit",
                    f"Max Limit: {grid_limit_kw:.1f} kW",
                    status="alert" if has_violation else "ok"
                )
            with o2:
                render_kpi_card("Annual Overload Duration", f"{overload_hours:,.1f} hrs", f"{(overload_hours / 8760.0 * 100.0):.1f}% of year")
            with o3:
                render_kpi_card("Annual Overload Energy", f"{overload_kwh:,.0f} kWh", f"{(overload_kwh / 1000.0):.2f} MWh excess")

    # 8. Consumer Management Forms (Left: Add, Right: Edit/Delete)
    st.divider()
    col_f1, col_f2 = st.columns([1, 1])
    with col_f1:
        render_add_consumer_form(consumers)
    with col_f2:
        render_consumer_editor(consumers)
