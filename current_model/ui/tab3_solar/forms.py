"""
========================================================================================
Solar PV Location Picker & Specification Forms (current_model/ui/tab3_solar/forms.py)
========================================================================================

Description:
------------
Provides:
  - Global city/place search via Open-Meteo Geocoding API
  - Direct interactive map clicking to pin any point on earth
  - Quick site presets and manual latitude/longitude input
  - Comprehensive technical PV specification form (st.form)
"""

from typing import Tuple, Optional, Dict, Any, List
import streamlit as st
import folium
from streamlit_folium import st_folium

from current_model.models.solar import SolarLocation, SolarPVConfig
from current_model.core.solar_engine import search_locations_open_meteo

SITE_PRESETS = {
    "📍 Tunuyán / Mendoza, Argentina (Bodegas Salentein)": {
        "name": "Tunuyán, Mendoza (Bodegas Salentein)",
        "lat": -33.5133,
        "lon": -69.2561,
        "elevation": 1100.0,
        "tz": "America/Argentina/Mendoza"
    },
    "📍 Santiago de Chile": {
        "name": "Santiago de Chile",
        "lat": -33.4489,
        "lon": -70.6693,
        "elevation": 570.0,
        "tz": "America/Santiago"
    },
    "📍 Buenos Aires, Argentina": {
        "name": "Buenos Aires, Argentina",
        "lat": -34.6037,
        "lon": -58.3816,
        "elevation": 25.0,
        "tz": "America/Argentina/Buenos_Aires"
    },
    "📍 Madrid, Spain": {
        "name": "Madrid, Spain",
        "lat": 40.4168,
        "lon": -3.7038,
        "elevation": 667.0,
        "tz": "Europe/Madrid"
    },
    "📍 Berlin, Germany": {
        "name": "Berlin, Germany",
        "lat": 52.5200,
        "lon": 13.4050,
        "elevation": 34.0,
        "tz": "Europe/Berlin"
    }
}


def render_solar_location_section(key_prefix: str = "solar_loc") -> SolarLocation:
    """
    Renders the location section featuring:
      1. City / Address search input
      2. Quick preset selector
      3. Interactive Folium map with click-to-pin coordinate detection
      4. Manual coordinate inputs
    """
    st.subheader("1. Geographic Location & Solar Radiation Site")
    st.caption("Enter a city/address, choose a preset, click on the map, or type exact GPS coordinates:")

    state_lat_key = f"{key_prefix}_lat"
    state_lon_key = f"{key_prefix}_lon"
    state_name_key = f"{key_prefix}_name"
    state_elev_key = f"{key_prefix}_elev"
    state_prev_click_key = f"{key_prefix}_prev_click"

    # Default initial location: Tunuyán, Mendoza
    if state_lat_key not in st.session_state:
        st.session_state[state_lat_key] = -33.5133
        st.session_state[state_lon_key] = -69.2561
        st.session_state[state_name_key] = "Tunuyán, Mendoza (Bodegas Salentein)"
        st.session_state[state_elev_key] = 1100.0

    # Top search and preset controls
    col_search, col_preset = st.columns([5, 5])

    with col_search:
        search_query = st.text_input(
            "🔍 Search City or Address (Worldwide):",
            placeholder="e.g. Mendoza, Berlin, Madrid, Santiago, Miami...",
            key=f"{key_prefix}_search_input"
        )
        if search_query and len(search_query.strip()) >= 2:
            search_results = search_locations_open_meteo(search_query.strip(), count=5)
            if search_results:
                options_dict = {f"📍 {r['display_name']} ({r['lat']}°, {r['lon']}°)": r for r in search_results}
                selected_match_label = st.selectbox(
                    "Matching Locations (Select to apply):",
                    options=list(options_dict.keys()),
                    key=f"{key_prefix}_search_results"
                )
                if selected_match_label in options_dict:
                    chosen = options_dict[selected_match_label]
                    if abs(st.session_state[state_lat_key] - chosen["lat"]) > 0.001 or abs(st.session_state[state_lon_key] - chosen["lon"]) > 0.001:
                        st.session_state[state_lat_key] = chosen["lat"]
                        st.session_state[state_lon_key] = chosen["lon"]
                        st.session_state[state_name_key] = chosen["display_name"]
                        st.session_state[state_elev_key] = chosen.get("elevation", 500.0)
                        st.rerun()
            else:
                st.caption("No matching cities found. Try another spelling.")

    with col_preset:
        preset_choice = st.selectbox(
            "📍 Quick Site Presets:",
            options=["-- Select a Preset Location --"] + list(SITE_PRESETS.keys()),
            index=0,
            key=f"{key_prefix}_preset_select"
        )
        if preset_choice in SITE_PRESETS:
            p_data = SITE_PRESETS[preset_choice]
            if abs(st.session_state[state_lat_key] - p_data["lat"]) > 0.001 or abs(st.session_state[state_lon_key] - p_data["lon"]) > 0.001:
                st.session_state[state_lat_key] = p_data["lat"]
                st.session_state[state_lon_key] = p_data["lon"]
                st.session_state[state_name_key] = p_data["name"]
                st.session_state[state_elev_key] = p_data.get("elevation", 500.0)
                st.rerun()

    cur_lat = float(st.session_state[state_lat_key])
    cur_lon = float(st.session_state[state_lon_key])
    cur_name = st.session_state.get(state_name_key, f"Site ({cur_lat:.3f}, {cur_lon:.3f})")

    # Interactive Folium Map
    m = folium.Map(
        location=[cur_lat, cur_lon],
        zoom_start=9 if abs(cur_lat) > 0 else 3,
        tiles="OpenStreetMap",
        control_scale=True
    )

    folium.Marker(
        location=[cur_lat, cur_lon],
        popup=f"Selected Solar Site: {cur_name} ({cur_lat:.4f}, {cur_lon:.4f})",
        tooltip=f"Pinned: {cur_name}",
        icon=folium.Icon(color="orange", icon="sun", prefix="fa")
    ).add_to(m)

    # st_folium with returned_objects=["last_clicked"] to only capture click events without continuous reruns
    map_out = st_folium(
        m,
        width="100%",
        height=320,
        returned_objects=["last_clicked"],
        key=f"{key_prefix}_interactive_map"
    )

    # Check for user click on map
    if map_out and map_out.get("last_clicked"):
        clicked = map_out["last_clicked"]
        click_lat = round(float(clicked["lat"]), 4)
        click_lon = round(float(clicked["lng"]), 4)
        prev_click = st.session_state.get(state_prev_click_key)

        # Only update if new distinct click
        if prev_click != (click_lat, click_lon) and (abs(click_lat - cur_lat) > 0.001 or abs(click_lon - cur_lon) > 0.001):
            st.session_state[state_prev_click_key] = (click_lat, click_lon)
            st.session_state[state_lat_key] = click_lat
            st.session_state[state_lon_key] = click_lon
            st.session_state[state_name_key] = f"Pinned Map Site ({click_lat:.3f}°, {click_lon:.3f}°)"
            st.rerun()

    # Manual Coordinate Fields (Optional Overrides)
    with st.expander("🛠️ Manual Coordinates & GPS Fine-Tuning", expanded=False):
        c_lat, c_lon = st.columns(2)
        with c_lat:
            man_lat = st.number_input(
                "Latitude (°N / °S):",
                min_value=-90.0,
                max_value=90.0,
                value=float(st.session_state[state_lat_key]),
                step=0.01,
                format="%.4f",
                key=f"{key_prefix}_man_lat"
            )
            if man_lat != st.session_state[state_lat_key]:
                st.session_state[state_lat_key] = man_lat
                st.session_state[state_name_key] = f"Coordinates ({man_lat:.3f}°, {cur_lon:.3f}°)"
                st.rerun()

        with c_lon:
            man_lon = st.number_input(
                "Longitude (°E / °W):",
                min_value=-180.0,
                max_value=180.0,
                value=float(st.session_state[state_lon_key]),
                step=0.01,
                format="%.4f",
                key=f"{key_prefix}_man_lon"
            )
            if man_lon != st.session_state[state_lon_key]:
                st.session_state[state_lon_key] = man_lon
                st.session_state[state_name_key] = f"Coordinates ({cur_lat:.3f}°, {man_lon:.3f}°)"
                st.rerun()

    # Information badge
    is_south = cur_lat < 0
    hemi_desc = "Southern Hemisphere (Recommended Panel Orientation: North 0°, Tilt: ~29°)" if is_south else "Northern Hemisphere (Recommended Panel Orientation: South 180°, Tilt: ~35°)"
    st.info(
        f"📍 **Active Site:** {cur_name} | **GPS:** `{cur_lat:.4f}°`, `{cur_lon:.4f}°` | *{hemi_desc}*"
    )

    return SolarLocation(
        name=cur_name,
        latitude=cur_lat,
        longitude=cur_lon,
        elevation_m=float(st.session_state.get(state_elev_key, 1000.0))
    )


def render_solar_config_form(
    location: SolarLocation,
    current_config: Optional[SolarPVConfig] = None,
    key_prefix: str = "solar_cfg"
) -> Tuple[SolarPVConfig, bool]:
    """
    Renders the technical PV configuration inside an st.form container.
    """
    cfg = current_config or SolarPVConfig()

    is_south = location.latitude < 0
    default_azimuth = 0.0 if is_south else 180.0
    default_tilt = float(round(max(10.0, min(60.0, abs(location.latitude) * 0.85)), 0))

    with st.form(key=f"{key_prefix}_spec_form"):
        st.subheader("2. Solar PV System Specifications & Technical Sizing")

        # 1. DC Array Sizing
        st.markdown("##### ⚡ DC Generator & Module Technology")
        c1, c2, c3 = st.columns(3)
        with c1:
            dc_kwp = st.number_input(
                "Installed DC Capacity (kWp):",
                min_value=1.0,
                max_value=50000.0,
                value=float(cfg.dc_capacity_kwp),
                step=10.0,
                format="%.1f",
                key=f"{key_prefix}_dc_kwp"
            )
        with c2:
            tech_options = [
                "Mono-Si PERC/TOPCon (γ = -0.35%/°C)",
                "Poly-Si Standard (γ = -0.40%/°C)",
                "Thin-Film CdTe (γ = -0.28%/°C)",
                "Custom Parameters"
            ]
            selected_tech = st.selectbox(
                "Module Technology:",
                options=tech_options,
                index=0,
                key=f"{key_prefix}_tech"
            )
        with c3:
            if "Mono" in selected_tech:
                def_gamma = -0.35
            elif "Poly" in selected_tech:
                def_gamma = -0.40
            elif "Thin" in selected_tech:
                def_gamma = -0.28
            else:
                def_gamma = cfg.temp_coefficient_pct_c

            temp_coeff = st.number_input(
                "Temperature Coeff. γ (%/°C):",
                min_value=-1.0,
                max_value=0.0,
                value=float(def_gamma),
                step=0.01,
                format="%.2f",
                key=f"{key_prefix}_gamma"
            )

        # 2. Mounting & Orientation
        st.markdown("##### 📐 Mounting Geometry & Orientation")
        g1, g2, g3 = st.columns(3)
        with g1:
            tilt_deg = st.number_input(
                "Tilt Angle β (°):",
                min_value=0.0,
                max_value=90.0,
                value=float(default_tilt),
                step=1.0,
                format="%.1f",
                help="0° = Horizontal, 90° = Vertical facade. Recommended: ~|Latitude| * 0.85",
                key=f"{key_prefix}_tilt"
            )
        with g2:
            azimuth_deg = st.number_input(
                "Azimuth Orientation α (°):",
                min_value=-180.0,
                max_value=360.0,
                value=float(default_azimuth),
                step=5.0,
                format="%.1f",
                help="South Hemisphere: 0° = North. North Hemisphere: 180° = South. East = 90°, West = 270° / -90°",
                key=f"{key_prefix}_azimuth"
            )
        with g3:
            mounting_options = [
                "Open-Rack (Ground / Carport - High Ventilation)",
                "Roof-Mounted (Flush with air gap)",
                "Roof-Integrated (No rear ventilation)",
                "1-Axis Tracker (Horizontal East-West)"
            ]
            mounting_type = st.selectbox(
                "Mounting Structure:",
                options=mounting_options,
                index=0,
                key=f"{key_prefix}_mounting"
            )

        # 3. Inverter & System Losses
        st.markdown("##### 🔄 Inverter & Balance of System (BOS) Losses")
        i1, i2, i3 = st.columns(3)
        with i1:
            def_inv_kw = round(dc_kwp / 1.15, 1)
            inverter_kw = st.number_input(
                "Inverter AC Capacity Limit (kW):",
                min_value=1.0,
                max_value=50000.0,
                value=float(def_inv_kw),
                step=10.0,
                format="%.1f",
                help="Maximum AC export limit. Power above this threshold is clipped.",
                key=f"{key_prefix}_inv_kw"
            )
        with i2:
            inverter_eff = st.number_input(
                "Inverter Efficiency (%):",
                min_value=80.0,
                max_value=100.0,
                value=98.0,
                step=0.1,
                format="%.1f",
                key=f"{key_prefix}_inv_eff"
            )
        with i3:
            soiling_loss = st.number_input(
                "Soiling & Dust Loss (%):",
                min_value=0.0,
                max_value=30.0,
                value=2.0,
                step=0.5,
                format="%.1f",
                key=f"{key_prefix}_soil_loss"
            )

        l1, l2 = st.columns(2)
        with l1:
            shading_loss = st.number_input(
                "Near Shading Loss (%):",
                min_value=0.0,
                max_value=30.0,
                value=1.5,
                step=0.5,
                format="%.1f",
                key=f"{key_prefix}_shade_loss"
            )
        with l2:
            dc_wiring_loss = st.number_input(
                "DC Ohmic & Mismatch Loss (%):",
                min_value=0.0,
                max_value=20.0,
                value=1.5,
                step=0.5,
                format="%.1f",
                key=f"{key_prefix}_dc_loss"
            )

        submitted = st.form_submit_button(
            "☀️ Run Solar PV Simulation (Fetch Open-Meteo & Compute)",
            type="primary",
            use_container_width=True
        )

    updated_config = SolarPVConfig(
        dc_capacity_kwp=dc_kwp,
        module_technology=selected_tech,
        temp_coefficient_pct_c=temp_coeff,
        nmot_c=45.0 if "Open-Rack" in mounting_type else (50.0 if "Flush" in mounting_type else 55.0),
        tilt_deg=tilt_deg,
        azimuth_deg=azimuth_deg,
        mounting_type=mounting_type,
        inverter_capacity_kw=inverter_kw,
        inverter_efficiency_pct=inverter_eff,
        soiling_loss_pct=soiling_loss,
        shading_loss_pct=shading_loss,
        dc_wiring_loss_pct=dc_wiring_loss
    )

    return updated_config, submitted
