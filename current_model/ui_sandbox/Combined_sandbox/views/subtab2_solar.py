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
            cur_sys_ref: Optional[CombinedSystemConfig] = st.session_state.get("comb_system_cfg")
            if cur_sys_ref is not None:
                cur_sys_ref.latitude = c_lat
                cur_sys_ref.longitude = c_lon
            st.session_state.pop("comb_cached_excel_bytes", None)
            st.rerun()


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

            gps_c1, gps_c2, loc_btn = st.columns([1.2, 1.2, 1.0])
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
            elif search_changed:
                search_results = search_locations_open_meteo(clean_q, count=1)
                if search_results:
                    chosen = search_results[0]
                    st.session_state["comb_solar_lat"] = float(chosen["lat"])
                    st.session_state["comb_solar_lon"] = float(chosen["lon"])
                    st.session_state["comb_solar_site_name"] = chosen["display_name"]
                    st.session_state["comb_solar_preset_choice"] = "Custom GPS Coordinates"
                st.session_state["comb_solar_last_search"] = clean_q
            elif manual_changed:
                st.session_state["comb_solar_lat"] = float(lat_input)
                st.session_state["comb_solar_lon"] = float(lon_input)
                st.session_state["comb_solar_site_name"] = (
                    f"Custom ({float(lat_input):.4f}°N, {float(lon_input):.4f}°E)"
                )
                st.session_state["comb_solar_preset_choice"] = "Custom GPS Coordinates"
            elif preset_choice in SOLAR_SITE_PRESETS:
                p_data = SOLAR_SITE_PRESETS[preset_choice]
                st.session_state["comb_solar_lat"] = float(p_data["latitude"])
                st.session_state["comb_solar_lon"] = float(p_data["longitude"])
                st.session_state["comb_solar_site_name"] = p_data["name"]
                st.session_state["comb_solar_preset_choice"] = preset_choice

            st.session_state.pop("comb_cached_excel_bytes", None)
            st.rerun()

        eff_lat = float(st.session_state.get("comb_solar_lat", 52.3676))
        eff_lon = float(st.session_state.get("comb_solar_lon", 4.9041))
        _, spec_yield, _ = get_unit_solar_generation_profile(
            latitude=eff_lat,
            longitude=eff_lon,
            tilt_deg=30.0,
            azimuth_deg=180.0 if eff_lat >= 0.0 else 0.0,
            dc_ac_ratio=cur_sys.dc_ac_ratio,
        )
        site_disp = st.session_state.get("comb_solar_site_name", "Amsterdam, Netherlands")
        st.caption(
            f"Data source: **EU PVGIS (ERA5 15-min TMY)** | Location: **{site_disp}** "
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

        # 2. Dual Quick-Sizing & Manual Input (st.form encapsulated)
        st.caption("Quick Sizing Presets (% of Annual Consumption):")
        qb1, qb2, qb3, qb4 = st.columns(4)
        qb1.button(
            "20%", use_container_width=True, disabled=not is_active,
            key="comb_sol_q20", on_click=_apply_solar_quick_share, args=(20.0,),
        )
        qb2.button(
            "40%", use_container_width=True, disabled=not is_active,
            key="comb_sol_q40", on_click=_apply_solar_quick_share, args=(40.0,),
        )
        qb3.button(
            "60%", use_container_width=True, disabled=not is_active,
            key="comb_sol_q60", on_click=_apply_solar_quick_share, args=(60.0,),
        )
        qb4.button(
            "100%", use_container_width=True, disabled=not is_active,
            key="comb_sol_q100", on_click=_apply_solar_quick_share, args=(100.0,),
        )

        preview_kwp = (
            round((ann_kwh * (float(cur_sys.target_consumption_share_pct) / 100.0)) / max(100.0, spec_yield), 1)
            if cur_sys.solar_sizing_method == "target_share_pct"
            else round(float(cur_sys.solar_kwp), 1)
        )
        default_inv_kw = (
            float(cur_sys.inverter_ac_limit_kw)
            if cur_sys.inverter_ac_limit_kw > 0.0
            else round(preview_kwp / max(1.0, cur_sys.dc_ac_ratio), 1)
        )

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
                target_share_val = st.number_input(
                    "Share of Consumption (%)",
                    min_value=5.0,
                    max_value=250.0,
                    value=float(cur_sys.target_consumption_share_pct),
                    step=5.0,
                    disabled=not is_active,
                    key="comb_solar_target_share_num",
                    help="Percentage of total annual electricity demand to be supplied by solar.",
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
                    help="Direct nameplate DC capacity in kWp.",
                )
                raw_inv_ac = max(0.0, float(default_inv_kw))
                max_inv_ac = max(100000.0, raw_inv_ac * 2)
                safe_inv_ac = min(max_inv_ac, max(0.0, raw_inv_ac))
                inv_ac_limit_val = st.number_input(
                    "Inverter AC Limit (kW)",
                    min_value=0.0,
                    max_value=max_inv_ac,
                    value=safe_inv_ac,
                    step=10.0,
                    disabled=not is_active,
                    key="comb_solar_inv_ac_limit_num",
                    help="Maximum continuous AC feed-in power to the site/grid.",
                )
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
            cur_sys.solar_sizing_method = sizing_method_key
            cur_sys.target_consumption_share_pct = float(target_share_val)
            cur_sys.solar_kwp = float(direct_kwp_val)
            cur_sys.inverter_ac_limit_kw = float(inv_ac_limit_val)
            cur_sys.inverter_efficiency_pct = float(inv_eff_val)
            st.session_state.pop("comb_cached_excel_bytes", None)

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
        )
        st.info(solar_deriv.formula_text, icon=":material/calculate:")

        with st.expander("How Solar Sizing & Weather Data Work", expanded=False, icon=":material/help_outline:"):
            st.markdown(
                f"""
**1. Quick Sizing Presets (`20% / 40% / 60% / 100%`)**  
Each percentage scales the PV array so its expected **annual electricity generation** equals that share of your annual facility consumption (`{ann_kwh:,.0f} kWh/yr`):
- `Target Solar Generation (kWh/yr) = Annual Consumption (kWh/yr) × Target Share (%)`
- `Required PV Size (kWp) = Target Solar Generation / Specific Yield ({spec_yield:,.0f} kWh/kWp/yr)`

**2. Why 100% Annual Solar Does Not Mean 100% Direct Self-Consumption**  
Solar irradiance peaks around midday and during summer months, whereas electricity demand also occurs at night, early mornings, and overcast winter weeks. Without a battery or generator, daytime surpluses above your live load are exported while evening/winter peaks still require Grid, Battery, or Generator power.  
*Tip:* In the bottom **Power Flow & Battery Level** chart, click **Solar Total Potential (kW)** in the legend to compare maximum possible PV output against **Solar Direct (kW)** actually absorbed on-site.

**3. Weather Data Basis (Typical Meteorological Year — TMY)**  
Solar generation is simulated from **EU PVGIS (ERA5) 15-minute TMY** profiles for your active GPS pin (`{eff_lat:.4f}°N, {eff_lon:.4f}°E`). A TMY dataset combines statistically typical months from multi-year satellite/reanalysis weather records to represent normal seasonal sunlight and temperature rather than a single outlier weather year.
                """.strip()
            )
