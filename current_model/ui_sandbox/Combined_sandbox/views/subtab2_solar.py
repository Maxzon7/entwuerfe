"""
Subtab 2: Solar PV view (GPS search, interactive Folium map fragment, dual quick-sizing & explainer).
"""

from typing import Optional
import streamlit as st

from .state_and_helpers import (
    _HAS_FOLIUM,
    folium,
    st_folium,
    search_locations_open_meteo,
    LoadSeries2025,
    SOLAR_SITE_PRESETS,
    CombinedSystemConfig,
    get_unit_solar_generation_profile,
    derive_solar_sizing_and_formula,
    compute_standalone_solar_production_summary,
    compute_synced_solar_pair,
    render_kpi_card,
    create_solar_production_figure,
    _activate_module_callback,
    _apply_solar_quick_share,
)

# ======================================================================================
# LEVEL 2 — SUBTAB 2: Solar (Grayed Out Until Activated)
# ======================================================================================

@st.fragment
def _render_solar_map_fragment(eff_lat: float, eff_lon: float, site_disp: str, is_active: bool) -> None:
    """Renders an interactive Folium map fragment so panning/zooming never reloads the app."""
    if not _HAS_FOLIUM:
        st.info(
            f"Map preview unavailable (`folium` / `streamlit-folium` not installed). "
            f"Active Pin: **{site_disp}** ({eff_lat:.4f}°N, {eff_lon:.4f}°E).",
            icon=":material/map:",
        )
        return

    st.caption("Click anywhere on the map to move the Solar location pin and recalculate PVGIS irradiance.")
    m = folium.Map(
        location=[eff_lat, eff_lon],
        zoom_start=8,
        tiles="OpenStreetMap",
        control_scale=True,
    )
    folium.Marker(
        [eff_lat, eff_lon],
        tooltip=f"{site_disp} ({eff_lat:.4f}°, {eff_lon:.4f}°)",
        popup=site_disp,
        icon=folium.Icon(color="orange", icon="sun", prefix="fa"),
    ).add_to(m)

    map_out = st_folium(
        m,
        width="100%",
        height=300,
        returned_objects=["last_clicked"],
        key="comb_solar_interactive_map",
    )
    if is_active and map_out and map_out.get("last_clicked"):
        c_lat = float(map_out["last_clicked"]["lat"])
        c_lon = float(map_out["last_clicked"]["lng"])
        click_sig = (round(c_lat, 5), round(c_lon, 5))
        prev_sig = st.session_state.get("comb_solar_last_map_click")
        if click_sig != prev_sig and (abs(c_lat - eff_lat) > 1e-4 or abs(c_lon - eff_lon) > 1e-4):
            st.session_state["comb_solar_last_map_click"] = click_sig
            st.session_state["comb_solar_lat"] = c_lat
            st.session_state["comb_solar_lon"] = c_lon
            st.session_state["comb_solar_site_name"] = f"Map Pin ({c_lat:.4f}°, {c_lon:.4f}°)"
            st.session_state["comb_solar_preset_choice"] = "Custom GPS Coordinates"
            st.session_state["comb_pending_solar_loc_sync"] = {
                "comb_solar_preset_select": "Custom GPS Coordinates",
                "comb_solar_search_input": "",
            }
            cur_sys_ref: Optional[CombinedSystemConfig] = st.session_state.get("comb_system_cfg")
            if cur_sys_ref is not None:
                cur_sys_ref.latitude = c_lat
                cur_sys_ref.longitude = c_lon
            st.session_state.pop("comb_cached_excel_bytes", None)
            st.rerun()


@st.fragment
def _render_solar_production_fragment(
    timestamps,
    cur_sys: CombinedSystemConfig,
    solar_deriv,
    is_active: bool,
) -> None:
    """Renders standalone, consumption-independent Solar Production KPIs and comparison chart."""
    if not is_active:
        st.info(
            "Activate Solar above to inspect standalone **Solar Production** and inverter clipping metrics.",
            icon=":material/info:",
        )
        return

    prod_summary = compute_standalone_solar_production_summary(
        system_cfg=cur_sys,
        solar_derivation=solar_deriv,
        n_steps=len(timestamps) if timestamps is not None and len(timestamps) > 0 else 35040,
    )
    inv_kw = float(prod_summary["inverter_ac_kw"])
    prod_kwh = float(prod_summary["production_kwh"])
    pot_kwh = float(prod_summary["potential_kwh"])
    clip_kwh = float(prod_summary["clipping_loss_kwh"])
    clip_pct = float(prod_summary["clipping_loss_pct"])
    clip_hrs = float(prod_summary["clipped_hours"])
    peak_prod = float(prod_summary["peak_production_kw"])
    peak_pot = float(prod_summary["peak_potential_kw"])
    flh = float(prod_summary["full_load_hours"])
    active_hrs = float(prod_summary["active_hours"])
    cap_pct = float(prod_summary["captured_pct"])

    st.caption(
        "Shows usable AC solar generation independent of facility consumption or load meter gaps, "
        "comparing inverter-clipped **Solar Production (kW)** against unclipped **Solar Total Potential (kW)**."
    )

    sp1, sp2, sp3, sp4 = st.columns(4)
    with sp1:
        render_kpi_card(
            title="Solar Production",
            value=f"{prod_kwh:,.0f} kWh/yr",
            subtext=f"{cap_pct:.1f}% of {pot_kwh:,.0f} kWh unclipped potential",
            status="ok",
        )
    with sp2:
        render_kpi_card(
            title="Peak Solar Production",
            value=f"{peak_prod:,.1f} kW AC",
            subtext=f"Inverter Limit: {inv_kw:,.1f} kW | Potential Peak: {peak_pot:,.1f} kW" if inv_kw > 0.0 else f"Inverter Limit: Disabled (Unclipped) | Potential Peak: {peak_pot:,.1f} kW",
            status="default",
        )
    with sp3:
        render_kpi_card(
            title="Inverter Clipping Loss",
            value=f"{clip_kwh:,.0f} kWh/yr",
            subtext=f"{clip_pct:.1f}% of potential across {clip_hrs:,.1f} hrs/yr at limit",
            status="alert" if clip_pct >= 5.0 else "default",
        )
    with sp4:
        render_kpi_card(
            title="Full-Load / Sun Hours",
            value=f"{flh:,.0f} hrs/yr",
            subtext=f"{prod_summary['specific_yield_after_inv_kwh_kwp']:,.0f} kWh/kWp | Active: {active_hrs:,.0f} hrs/yr",
            status="default",
        )

    fig_prod = create_solar_production_figure(
        timestamps=timestamps,
        solar_production_kw=prod_summary["solar_production_kw"],
        solar_potential_kw=prod_summary["solar_potential_kw"],
        inverter_ac_kw=inv_kw,
        color_overrides=st.session_state.get("comb_powerflow_colors"),
    )
    st.plotly_chart(
        fig_prod,
        use_container_width=True,
        config={"scrollZoom": False, "displayModeBar": "hover", "responsive": True},
        key="comb_solar_production_chart",
    )


def render_subtab2_solar(load_series: LoadSeries2025) -> None:
    """
    Renders Subtab 2: Solar
      - 1-Click Activate button if inactive
      - Location (City search, Presets, Manual GPS & Interactive Map) + EU PVGIS source line
      - Dual Quick-Sizing (% of Annual Consumption: 20/40/60/100% vs. Direct Size kWp)
      - Blue live formula box + Plain-language Solar & Weather Explanation Expander
      - Inverter AC Limit (kW) & Inverter Efficiency (%) (Default: 98%)
    """
    cur_sys: CombinedSystemConfig = st.session_state["comb_system_cfg"]
    is_active = bool(cur_sys.enable_solar)
    ann_kwh = float(load_series.total_energy_kwh)

    if not is_active:
        with st.container(border=True):
            b_col1, b_col2 = st.columns([2.5, 1.2])
            with b_col1:
                st.markdown(
                    "**Solar is currently inactive.** Click **Activate Solar** to include solar generation in your system."
                )
            with b_col2:
                st.button(
                    "Activate Solar",
                    icon=":material/power_settings_new:",
                    type="primary",
                    use_container_width=True,
                    key="comb_btn_activate_solar",
                    on_click=_activate_module_callback,
                    args=("comb_enable_solar_toggle",),
                )

    with st.container(border=True):
        st.markdown("##### :material/solar_power: Solar Settings")

        pending_loc_sync = st.session_state.pop("comb_pending_solar_loc_sync", None)
        if isinstance(pending_loc_sync, dict):
            for sk, sv in pending_loc_sync.items():
                st.session_state[sk] = sv

        curr_lat = float(st.session_state.get("comb_solar_lat", 52.3676))
        curr_lon = float(st.session_state.get("comb_solar_lon", 4.9041))

        # 1. Location: City Search, Presets & Manual GPS Coordinates (Default: Amsterdam)
        with st.form("comb_solar_location_form"):
            loc_c1, loc_c2 = st.columns(2)
            with loc_c1:
                search_query = st.text_input(
                    "City Search",
                    value=st.session_state.get("comb_solar_search_input", ""),
                    placeholder="Type city (e.g. Amsterdam, Berlin, Madrid)...",
                    disabled=not is_active,
                    key="comb_solar_search_input",
                )
            with loc_c2:
                preset_options = list(SOLAR_SITE_PRESETS.keys()) + ["Custom GPS Coordinates"]
                curr_preset = st.session_state.get("comb_solar_preset_choice", "Amsterdam (Default GPS)")
                preset_idx = preset_options.index(curr_preset) if curr_preset in preset_options else 0
                preset_choice = st.selectbox(
                    "Location Presets (Default: Amsterdam)",
                    options=preset_options,
                    index=preset_idx,
                    disabled=not is_active,
                    key="comb_solar_preset_select",
                )

            gps_c1, gps_c2, ws_c1, ws_c2, loc_btn = st.columns([1.0, 1.0, 1.5, 0.75, 0.95])
            with gps_c1:
                lat_input = st.number_input(
                    "Latitude (°N)",
                    min_value=-90.0,
                    max_value=90.0,
                    value=curr_lat,
                    step=0.01,
                    format="%.4f",
                    disabled=not is_active,
                )
            with gps_c2:
                lon_input = st.number_input(
                    "Longitude (°E)",
                    min_value=-180.0,
                    max_value=180.0,
                    value=curr_lon,
                    step=0.01,
                    format="%.4f",
                    disabled=not is_active,
                )
            with ws_c1:
                ws_opts = ["Specific Year (Solar Data)", "Typical Year (PVGIS TMY)"]
                cur_w_mode = str(getattr(cur_sys, "solar_weather_mode", "single_year") or "single_year")
                ws_idx = 0 if cur_w_mode == "single_year" else 1
                weather_src_choice = st.selectbox(
                    "Weather Data Source",
                    options=ws_opts,
                    index=ws_idx,
                    disabled=not is_active,
                    key="comb_solar_weather_mode_sel",
                    help="Specific Year uses actual historical weather for the selected year (good for checking against real meter data). TMY uses a multi-year typical average.",
                )
            with ws_c2:
                yr_opts = [2025, 2024, 2023, 2022, 2021, 2020]
                cur_w_yr = int(getattr(cur_sys, "solar_weather_year", 2025) or 2025)
                yr_idx = yr_opts.index(cur_w_yr) if cur_w_yr in yr_opts else 0
                weather_year_choice = st.selectbox(
                    "Year",
                    options=yr_opts,
                    index=yr_idx,
                    disabled=not is_active,
                    key="comb_solar_weather_year_sel",
                    help="Calendar year used when Specific Year (Solar Data) is active.",
                )
            with loc_btn:
                st.write("")
                loc_submitted = st.form_submit_button(
                    "Apply Location",
                    use_container_width=True,
                    disabled=not is_active,
                )

        if loc_submitted:
            clean_q = (search_query or "").strip()
            manual_changed = (
                abs(float(lat_input) - curr_lat) > 1e-5
                or abs(float(lon_input) - curr_lon) > 1e-5
            )
            preset_changed = (
                preset_choice in SOLAR_SITE_PRESETS
                and preset_choice != st.session_state.get("comb_solar_preset_choice")
            )
            search_changed = (
                len(clean_q) >= 2
                and clean_q != st.session_state.get("comb_solar_last_search", "")
            )

            if preset_changed:
                p_data = SOLAR_SITE_PRESETS[preset_choice]
                st.session_state["comb_solar_lat"] = float(p_data["latitude"])
                st.session_state["comb_solar_lon"] = float(p_data["longitude"])
                st.session_state["comb_solar_site_name"] = p_data["name"]
                st.session_state["comb_solar_preset_choice"] = preset_choice
                st.session_state["comb_pending_solar_loc_sync"] = {"comb_solar_search_input": ""}
                st.session_state.pop("comb_solar_search_matches", None)
                st.session_state.pop("comb_solar_last_search", None)
            elif search_changed:
                search_results = search_locations_open_meteo(clean_q, count=8)
                st.session_state["comb_solar_search_matches"] = list(search_results or [])
                if search_results:
                    chosen = search_results[0]
                    st.session_state["comb_solar_lat"] = float(chosen["lat"])
                    st.session_state["comb_solar_lon"] = float(chosen["lon"])
                    st.session_state["comb_solar_site_name"] = chosen["display_name"]
                    st.session_state["comb_solar_preset_choice"] = "Custom GPS Coordinates"
                    st.session_state["comb_pending_solar_loc_sync"] = {
                        "comb_solar_preset_select": "Custom GPS Coordinates",
                    }
                st.session_state["comb_solar_last_search"] = clean_q
            elif manual_changed:
                st.session_state["comb_solar_lat"] = float(lat_input)
                st.session_state["comb_solar_lon"] = float(lon_input)
                st.session_state["comb_solar_site_name"] = (
                    f"Custom ({float(lat_input):.4f}°N, {float(lon_input):.4f}°E)"
                )
                st.session_state["comb_solar_preset_choice"] = "Custom GPS Coordinates"
                st.session_state["comb_pending_solar_loc_sync"] = {
                    "comb_solar_preset_select": "Custom GPS Coordinates",
                    "comb_solar_search_input": "",
                }
                st.session_state.pop("comb_solar_search_matches", None)
                st.session_state.pop("comb_solar_last_search", None)
            elif preset_choice in SOLAR_SITE_PRESETS:
                p_data = SOLAR_SITE_PRESETS[preset_choice]
                st.session_state["comb_solar_lat"] = float(p_data["latitude"])
                st.session_state["comb_solar_lon"] = float(p_data["longitude"])
                st.session_state["comb_solar_site_name"] = p_data["name"]
                st.session_state["comb_solar_preset_choice"] = preset_choice
                st.session_state["comb_pending_solar_loc_sync"] = {"comb_solar_search_input": ""}
                st.session_state.pop("comb_solar_search_matches", None)
                st.session_state.pop("comb_solar_last_search", None)

            cur_sys.solar_weather_mode = (
                "single_year" if weather_src_choice.startswith("Specific") else "TMY"
            )
            cur_sys.solar_weather_year = int(weather_year_choice)

            new_lat = float(st.session_state.get("comb_solar_lat", cur_sys.latitude))
            new_lon = float(st.session_state.get("comb_solar_lon", cur_sys.longitude))
            _, new_spec_y, _ = get_unit_solar_generation_profile(
                latitude=new_lat,
                longitude=new_lon,
                tilt_deg=float(cur_sys.tilt_deg),
                azimuth_deg=180.0 if new_lat >= 0.0 else 0.0,
                dc_ac_ratio=float(cur_sys.dc_ac_ratio),
                weather_mode=cur_sys.solar_weather_mode,
                selected_year=cur_sys.solar_weather_year,
            )
            s_kwp, s_share = compute_synced_solar_pair(
                sizing_method=cur_sys.solar_sizing_method,
                direct_kwp=float(cur_sys.solar_kwp),
                target_share_pct=float(cur_sys.target_consumption_share_pct),
                annual_consumption_kwh=ann_kwh,
                specific_yield_kwh_per_kwp=new_spec_y,
                inverter_efficiency_pct=float(cur_sys.inverter_efficiency_pct),
            )
            cur_sys.solar_kwp = float(s_kwp)
            cur_sys.target_consumption_share_pct = float(s_share)
            st.session_state["comb_pending_solar_widget_sync"] = {
                "comb_solar_target_share_num": float(s_share),
                "comb_solar_direct_kwp_num": float(s_kwp),
            }
            st.session_state.pop("comb_cached_excel_bytes", None)
            st.rerun()

        eff_lat = float(st.session_state.get("comb_solar_lat", 52.3676))
        eff_lon = float(st.session_state.get("comb_solar_lon", 4.9041))
        eff_w_mode = str(getattr(cur_sys, "solar_weather_mode", "single_year") or "single_year")
        eff_w_year = int(getattr(cur_sys, "solar_weather_year", 2025) or 2025)

        search_matches = st.session_state.get("comb_solar_search_matches", [])
        if is_active and isinstance(search_matches, list) and len(search_matches) > 1:
            match_labels = [
                f"{m.get('display_name', m.get('name', 'Place'))} ({float(m['lat']):.4f}°, {float(m['lon']):.4f}°)"
                for m in search_matches
            ]
            cur_match_idx = 0
            for idx_m, m_item in enumerate(search_matches):
                if (
                    abs(float(m_item["lat"]) - eff_lat) < 1e-4
                    and abs(float(m_item["lon"]) - eff_lon) < 1e-4
                ):
                    cur_match_idx = idx_m
                    break
            m_c1, m_c2 = st.columns([3.0, 1.0])
            with m_c1:
                picked_label = st.selectbox(
                    "Multiple matching places found — select the right one:",
                    options=match_labels,
                    index=cur_match_idx,
                    key="comb_solar_match_pick_sel",
                )
            with m_c2:
                st.write("")
                if st.button("Use Selected Location", use_container_width=True, key="comb_solar_match_apply_btn"):
                    picked_idx = match_labels.index(picked_label)
                    chosen_m = search_matches[picked_idx]
                    st.session_state["comb_solar_lat"] = float(chosen_m["lat"])
                    st.session_state["comb_solar_lon"] = float(chosen_m["lon"])
                    st.session_state["comb_solar_site_name"] = chosen_m["display_name"]
                    st.session_state["comb_solar_preset_choice"] = "Custom GPS Coordinates"
                    st.session_state["comb_pending_solar_loc_sync"] = {
                        "comb_solar_preset_select": "Custom GPS Coordinates",
                    }
                    _, m_spec_y, _ = get_unit_solar_generation_profile(
                        latitude=float(chosen_m["lat"]),
                        longitude=float(chosen_m["lon"]),
                        tilt_deg=float(cur_sys.tilt_deg),
                        azimuth_deg=180.0 if float(chosen_m["lat"]) >= 0.0 else 0.0,
                        dc_ac_ratio=float(cur_sys.dc_ac_ratio),
                        weather_mode=eff_w_mode,
                        selected_year=eff_w_year,
                    )
                    m_kwp, m_share = compute_synced_solar_pair(
                        sizing_method=cur_sys.solar_sizing_method,
                        direct_kwp=float(cur_sys.solar_kwp),
                        target_share_pct=float(cur_sys.target_consumption_share_pct),
                        annual_consumption_kwh=ann_kwh,
                        specific_yield_kwh_per_kwp=m_spec_y,
                        inverter_efficiency_pct=float(cur_sys.inverter_efficiency_pct),
                    )
                    cur_sys.solar_kwp = float(m_kwp)
                    cur_sys.target_consumption_share_pct = float(m_share)
                    st.session_state["comb_pending_solar_widget_sync"] = {
                        "comb_solar_target_share_num": float(m_share),
                        "comb_solar_direct_kwp_num": float(m_kwp),
                    }
                    st.session_state.pop("comb_cached_excel_bytes", None)
                    st.rerun()
        _, spec_yield, solar_src_label = get_unit_solar_generation_profile(
            latitude=eff_lat,
            longitude=eff_lon,
            tilt_deg=float(cur_sys.tilt_deg),
            azimuth_deg=180.0 if eff_lat >= 0.0 else 0.0,
            dc_ac_ratio=cur_sys.dc_ac_ratio,
            weather_mode=eff_w_mode,
            selected_year=eff_w_year,
        )
        site_disp = st.session_state.get("comb_solar_site_name", "Amsterdam, Netherlands")
        st.caption(
            f"Data source: **{solar_src_label}** | Location: **{site_disp}** "
            f"(`{eff_lat:.4f}°N, {eff_lon:.4f}°E`) | Specific Yield: **{spec_yield:,.0f} kWh/kWp/year**"
        )

        with st.expander("Location Map & Pin Selection", expanded=False, icon=":material/map:"):
            _render_solar_map_fragment(
                eff_lat=eff_lat,
                eff_lon=eff_lon,
                site_disp=site_disp,
                is_active=is_active,
            )

        st.markdown("---")

        # 2. Dual Sizing & Manual Input (st.form encapsulated)
        preview_kwp = (
            round((ann_kwh * (float(cur_sys.target_consumption_share_pct) / 100.0)) / max(100.0, spec_yield), 1)
            if cur_sys.solar_sizing_method == "target_share_pct"
            else round(float(cur_sys.solar_kwp), 1)
        )
        auto_inv_kw = round(preview_kwp / max(1.0, cur_sys.dc_ac_ratio), 1)

        pending_sol_sync = st.session_state.pop("comb_pending_solar_widget_sync", None)
        if isinstance(pending_sol_sync, dict):
            for sk, sv in pending_sol_sync.items():
                st.session_state[sk] = sv

        with st.form("comb_solar_form"):
            sz_c1, sz_c2, sz_c3 = st.columns(3)
            with sz_c1:
                st.markdown("**Sizing Mode & Energy Share:**")
                sizing_mode_label = st.radio(
                    "Sizing Mode",
                    options=["% of Annual Consumption", "Direct Size (kWp)"],
                    index=0 if cur_sys.solar_sizing_method == "target_share_pct" else 1,
                    horizontal=True,
                    disabled=not is_active,
                    key="comb_solar_sizing_radio",
                )
                raw_share = float(cur_sys.target_consumption_share_pct)
                safe_share = min(1000.0, max(0.1, raw_share))
                target_share_val = st.number_input(
                    "Share of Consumption (%)",
                    min_value=0.1,
                    max_value=1000.0,
                    value=safe_share,
                    step=5.0,
                    disabled=not is_active,
                    key="comb_solar_target_share_num",
                    help="Target yearly solar production as a % of your total electricity use. Automatically updates when you apply Direct Size (kWp).",
                )
            with sz_c2:
                st.markdown("**Size & Inverter Limit:**")
                raw_solar_kwp = float(cur_sys.solar_kwp)
                max_solar_kwp = max(100000.0, raw_solar_kwp * 2)
                safe_solar_kwp = min(max_solar_kwp, max(1.0, raw_solar_kwp))
                direct_kwp_val = st.number_input(
                    "Direct Size (kWp)",
                    min_value=1.0,
                    max_value=max_solar_kwp,
                    value=safe_solar_kwp,
                    step=10.0,
                    disabled=not is_active,
                    key="comb_solar_direct_kwp_num",
                    help="Installed solar panel capacity in kWp. Automatically updates when you apply % of Annual Consumption.",
                )
                disable_inv_val = st.checkbox(
                    "Disable Inverter AC Limit (100% Unclipped Output)",
                    value=bool(getattr(cur_sys, "disable_solar_inverter_limit", False)),
                    disabled=not is_active,
                    key="comb_solar_disable_inv_limit_chk",
                    help="When enabled, no AC ceiling is applied so 100% of solar potential is usable without clipping.",
                )
                raw_inv_ac = max(0.0, float(cur_sys.inverter_ac_limit_kw))
                max_inv_ac = max(100000.0, raw_inv_ac * 2, auto_inv_kw * 2)
                safe_inv_ac = min(max_inv_ac, max(0.0, raw_inv_ac))
                inv_ac_limit_val = st.number_input(
                    "Inverter AC Limit (kW, 0 = Auto)",
                    min_value=0.0,
                    max_value=max_inv_ac,
                    value=safe_inv_ac,
                    step=10.0,
                    disabled=(not is_active) or disable_inv_val,
                    key="comb_solar_inv_ac_limit_num",
                    help="Maximum power the inverter can feed into your site (0 = auto-sized).",
                )
                if not disable_inv_val and raw_inv_ac <= 0.0:
                    st.caption(f"Auto-sized when 0: **{auto_inv_kw:,.1f} kW AC** (DC/AC {cur_sys.dc_ac_ratio:.2f})")
            with sz_c3:
                st.markdown("**Efficiency & Apply:**")
                inv_eff_val = st.slider(
                    "Inverter Efficiency (%)",
                    min_value=85,
                    max_value=100,
                    value=int(round(cur_sys.inverter_efficiency_pct)),
                    step=1,
                    disabled=not is_active,
                    key="comb_solar_inv_eff_num",
                )
                st.write("")
                sol_submitted = st.form_submit_button(
                    "Update Solar Settings & Run Simulation",
                    icon=":material/refresh:",
                    type="primary",
                    use_container_width=True,
                    disabled=not is_active,
                )

        if sol_submitted:
            sizing_method_key = "target_share_pct" if sizing_mode_label == "% of Annual Consumption" else "direct_kwp"
            synced_kwp, synced_share = compute_synced_solar_pair(
                sizing_method=sizing_method_key,
                direct_kwp=float(direct_kwp_val),
                target_share_pct=float(target_share_val),
                annual_consumption_kwh=ann_kwh,
                specific_yield_kwh_per_kwp=spec_yield,
                inverter_efficiency_pct=float(inv_eff_val),
            )
            cur_sys.solar_sizing_method = sizing_method_key
            cur_sys.solar_kwp = float(synced_kwp)
            cur_sys.target_consumption_share_pct = float(synced_share)
            cur_sys.disable_solar_inverter_limit = bool(disable_inv_val)
            cur_sys.inverter_ac_limit_kw = float(inv_ac_limit_val)
            cur_sys.inverter_efficiency_pct = float(inv_eff_val)
            st.session_state["comb_pending_solar_widget_sync"] = {
                "comb_solar_target_share_num": float(synced_share),
                "comb_solar_direct_kwp_num": float(synced_kwp),
            }
            st.session_state.pop("comb_cached_excel_bytes", None)
            st.rerun()

        cur_sys.latitude = eff_lat
        cur_sys.longitude = eff_lon

        solar_deriv = derive_solar_sizing_and_formula(
            annual_consumption_kwh=ann_kwh,
            specific_yield_kwh_per_kwp=spec_yield,
            sizing_method=cur_sys.solar_sizing_method,
            direct_kwp=float(cur_sys.solar_kwp),
            target_share_pct=float(cur_sys.target_consumption_share_pct),
            panel_wp=cur_sys.panel_wp,
            dc_ac_ratio=cur_sys.dc_ac_ratio,
            enable_solar=True,
            inverter_ac_limit_kw=float(cur_sys.inverter_ac_limit_kw),
            inverter_efficiency_pct=float(cur_sys.inverter_efficiency_pct),
            data_source_label=solar_src_label,
            disable_inverter_limit=bool(getattr(cur_sys, "disable_solar_inverter_limit", False)),
        )

        with st.expander("Your Solar System at a Glance", expanded=True, icon=":material/calculate:"):
            dc_ac_actual = (
                (solar_deriv.installed_kwp / solar_deriv.inverter_ac_kw)
                if solar_deriv.inverter_ac_kw > 0.0
                else float(cur_sys.dc_ac_ratio)
            )
            w_mode_short = (
                f"Solar Data {eff_w_year}"
                if eff_w_mode == "single_year"
                else "PVGIS TMY (Multi-Year Typical)"
            )
            summary_rows_html = "".join(
                f'<tr style="border-bottom:1px solid #1e293b;">'
                f'<td style="padding:8px 12px; color:#cbd5e1; font-weight:600;">{item}</td>'
                f'<td style="padding:8px 12px; color:#f8fafc; font-weight:700; text-align:right;">{val}</td>'
                f'<td style="padding:8px 12px; color:#94a3b8; font-size:0.86rem;">{note}</td>'
                f'</tr>'
                for item, val, note in [
                    (
                        "Weather Data Source",
                        w_mode_short,
                        solar_src_label,
                    ),
                    (
                        "System Size",
                        f"{solar_deriv.installed_kwp:,.1f} kWp",
                        f"{solar_deriv.panel_count:,} panels ({solar_deriv.panel_wp:,.0f} Wp each)",
                    ),
                    (
                        "Sun at Your Location",
                        f"{solar_deriv.specific_yield_kwh_per_kwp:,.0f} kWh / kWp / yr",
                        f"Expected yearly output per installed kWp in {site_disp}",
                    ),
                    (
                        "Expected Yearly Production",
                        f"{solar_deriv.expected_annual_yield_kwh:,.0f} kWh / yr",
                        f"{solar_deriv.installed_kwp:,.1f} kWp &times; {solar_deriv.specific_yield_kwh_per_kwp:,.0f} kWh/kWp (at {solar_deriv.inverter_efficiency_pct:.0f}% inverter efficiency)",
                    ),
                    (
                        "Covers of Your Consumption",
                        f"{solar_deriv.effective_share_pct:,.1f}%",
                        (
                            f"Compared against your {ann_kwh:,.0f} kWh/yr total electricity use"
                            if ann_kwh > 0.0
                            else "Upload or select a consumption profile to compare against annual demand"
                        ),
                    ),
                    (
                        "Inverter Size",
                        (
                            f"{solar_deriv.inverter_ac_kw:,.1f} kW AC"
                            if solar_deriv.inverter_ac_kw > 0.0
                            else "No AC Limit (Unclipped)"
                        ),
                        (
                            f"DC/AC ratio {dc_ac_actual:.2f} &middot; {solar_deriv.inverter_efficiency_pct:.0f}% efficiency"
                            if solar_deriv.inverter_ac_kw > 0.0
                            else f"100% of solar potential usable (AC clipping disabled) &middot; {solar_deriv.inverter_efficiency_pct:.0f}% efficiency"
                        ),
                    ),
                ]
            )
            table_html = (
                '<div style="border-radius:8px; border:1px solid #334155; overflow:hidden; margin-bottom:10px;">'
                '<table style="width:100%; border-collapse:collapse; font-family:-apple-system, BlinkMacSystemFont, sans-serif;">'
                '<thead><tr style="background-color:#090d16; border-bottom:1px solid #475569; color:#94a3b8; font-size:0.72rem; text-transform:uppercase; letter-spacing:0.04em;">'
                '<th style="padding:8px 12px; text-align:left;">Setting / Result</th>'
                '<th style="padding:8px 12px; text-align:right;">Value</th>'
                '<th style="padding:8px 12px; text-align:left;">What This Means</th>'
                '</tr></thead>'
                f'<tbody style="background-color:#0f172a;">{summary_rows_html}</tbody>'
                '</table>'
                '</div>'
            )
            st.markdown(table_html, unsafe_allow_html=True)

            flow_html = (
                '<div style="background-color:#0b1329; border:1px solid #334155; border-radius:8px; padding:10px 14px; margin-bottom:8px; '
                'display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:8px;">'
                f'<div style="background-color:#1e293b; border-left:3px solid #FACC15; border-radius:6px; padding:6px 10px; flex:1; min-width:130px;">'
                f'<div style="font-size:0.70rem; color:#94a3b8;">System Size</div>'
                f'<div style="font-size:0.95rem; color:#f8fafc; font-weight:700;">{solar_deriv.installed_kwp:,.1f} kWp</div></div>'
                '<div style="color:#64748b; font-weight:800;">&times;</div>'
                f'<div style="background-color:#1e293b; border-left:3px solid #38BDF8; border-radius:6px; padding:6px 10px; flex:1; min-width:150px;">'
                f'<div style="font-size:0.70rem; color:#94a3b8;">Sun at Location</div>'
                f'<div style="font-size:0.95rem; color:#f8fafc; font-weight:700;">{solar_deriv.specific_yield_kwh_per_kwp:,.0f} kWh/kWp/yr</div></div>'
                '<div style="color:#64748b; font-weight:800;">=</div>'
                f'<div style="background-color:#1e293b; border-left:3px solid #22C55E; border-radius:6px; padding:6px 10px; flex:1; min-width:150px;">'
                f'<div style="font-size:0.70rem; color:#94a3b8;">Yearly Production</div>'
                f'<div style="font-size:0.95rem; color:#f8fafc; font-weight:700;">{solar_deriv.expected_annual_yield_kwh:,.0f} kWh/yr</div></div>'
                '<div style="color:#38BDF8; font-weight:800;">&rarr;</div>'
                f'<div style="background-color:#06281e; border:1.5px solid #22C55E; border-radius:6px; padding:6px 10px; flex:1; min-width:140px;">'
                f'<div style="font-size:0.70rem; color:#86EFAC; font-weight:700;">Covers of Demand</div>'
                f'<div style="font-size:0.95rem; color:#ffffff; font-weight:800;">{solar_deriv.effective_share_pct:,.1f}%</div></div>'
                '</div>'
            )
            st.markdown(flow_html, unsafe_allow_html=True)

            st.caption(
                "Yearly production is not the same as power used directly on site — sunny midday surplus is fed into the grid "
                "unless a battery stores it. Inspect pure PV output in **Solar Production** below or compare against load in the **Power Flow** chart."
            )

            if ann_kwh > 0.0 and solar_deriv.effective_share_pct > 100.0:
                st.warning(
                    "This system produces more energy over the year than your site consumes. "
                    "Extra midday energy will mostly be fed into the grid unless stored.",
                    icon=":material/info:",
                )
            if solar_deriv.installed_kwp > 0.0 and solar_deriv.inverter_ac_kw < solar_deriv.installed_kwp * 0.5:
                st.warning(
                    "The inverter limit is less than half of the panel size, so sunny midday peaks will be cut back.",
                    icon=":material/warning:",
                )

        with st.expander("Solar Production", expanded=False, icon=":material/solar_power:"):
            _render_solar_production_fragment(
                timestamps=load_series.timestamps,
                cur_sys=cur_sys,
                solar_deriv=solar_deriv,
                is_active=is_active,
            )

        with st.expander("How Solar Sizing & Weather Data Work", expanded=False, icon=":material/help_outline:"):
            st.markdown(
                f"""
**1. Sizing Modes (`% of Annual Consumption` vs. `Direct Size (kWp)`)**  
In **% of Annual Consumption** mode, the array is scaled so its expected yearly production matches that share of your annual electricity use (`{ann_kwh:,.0f} kWh/yr`):
- `Target Solar Generation (kWh/yr) = Annual Consumption (kWh/yr) × Target Share (%)`
- `Required PV Size (kWp) = Target Solar Generation / Specific Yield ({spec_yield:,.0f} kWh/kWp/yr)`
In **Direct Size (kWp)** mode, you set the panel capacity directly and the matching consumption share is calculated automatically after applying.

**2. Why 100% Annual Solar Does Not Mean 100% Direct Self-Consumption**  
Solar irradiance peaks around midday and during summer months, whereas electricity demand also occurs at night, early mornings, and overcast winter weeks. Without a battery or generator, daytime surpluses above your live load are exported while evening/winter peaks still require Grid, Battery, or Generator power.  
*Tip:* Open the **Solar Production** expander above (or toggle **Solar Production (kW)** / **Solar Total Potential (kW)** in the bottom **Power Flow & Battery Level** chart) to compare usable inverter-clipped PV generation against unclipped maximum potential and on-site **Solar Direct (kW)**.

**3. Weather Data Basis (Specific Year vs. Typical Meteorological Year — TMY)**  
You can switch between two solar weather datasets for your active GPS pin (`{eff_lat:.4f}°N, {eff_lon:.4f}°E`):
- **Specific Year (Default: `2025`):** Uses historical hourly irradiance & temperature records from **Open-Meteo** for that exact calendar year (`{eff_w_year}`), interpolated to 15 minutes — ideal for checking the program directly against real meter data from that year.
- **Typical Meteorological Year (`TMY`):** Uses **EU PVGIS (ERA5)** statistically typical months across multiple years to represent long-term average seasonal sunlight rather than one individual weather year.
                """.strip()
            )
