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
  - Clean and simple technical PV specification form (DC kWp, tilt, azimuth, inverter, losses)
"""

from typing import Tuple, Optional, Dict, Any, List
import streamlit as st
import folium
from streamlit_folium import st_folium

from current_model.models.solar import SolarLocation, SolarPVConfig, SolarFinancialConfig
from current_model.core.solar_engine import search_locations_open_meteo

SITE_PRESETS = {
    "Tunuyán / Mendoza, Argentina (Bodegas Salentein)": {
        "name": "Tunuyán, Mendoza (Bodegas Salentein)",
        "lat": -33.5133,
        "lon": -69.2561,
        "elevation": 1100.0,
        "tz": "America/Argentina/Mendoza"
    },
    "Santiago de Chile": {
        "name": "Santiago de Chile",
        "lat": -33.4489,
        "lon": -70.6693,
        "elevation": 570.0,
        "tz": "America/Santiago"
    },
    "Buenos Aires, Argentina": {
        "name": "Buenos Aires, Argentina",
        "lat": -34.6037,
        "lon": -58.3816,
        "elevation": 25.0,
        "tz": "America/Argentina/Buenos_Aires"
    },
    "Madrid, Spain": {
        "name": "Madrid, Spain",
        "lat": 40.4168,
        "lon": -3.7038,
        "elevation": 667.0,
        "tz": "Europe/Madrid"
    },
    "Berlin, Germany": {
        "name": "Berlin, Germany",
        "lat": 52.5200,
        "lon": 13.4050,
        "elevation": 34.0,
        "tz": "Europe/Berlin"
    }
}


def _apply_location_update(lat: float, lon: float, name: str, elevation: float, key_prefix: str) -> None:
    st.session_state[f"{key_prefix}_lat"] = lat
    st.session_state[f"{key_prefix}_lon"] = lon
    st.session_state[f"{key_prefix}_name"] = name
    st.session_state[f"{key_prefix}_elev"] = elevation

    # Determine hemisphere-optimal azimuth (180° South for North Hemisphere, 0° North for South Hemisphere) and tilt
    is_south = (lat < 0)
    opt_azimuth = 0.0 if is_south else 180.0
    opt_tilt = float(round(max(10.0, min(60.0, abs(lat) * 0.85)), 0))

    # Purge widget state keys so input fields refresh with optimal values
    for k in [
        "app_tab3_form_tilt", "app_tab3_form_azimuth",
        "tab3_solar_form_tilt", "tab3_solar_form_azimuth",
        "solar_cfg_form_tilt", "solar_cfg_form_azimuth"
    ]:
        if k in st.session_state:
            del st.session_state[k]

    # Invalidate cached simulation results from the previous location so stale charts are cleared
    for k in [
        "app_tab3_sim_result", "tab3_solar_sim_result", "solar_kw_15min", "solar_kpis", "solar_financial_metrics"
    ]:
        if k in st.session_state:
            del st.session_state[k]

    # Auto-trigger calculation with the new location radiation dataset
    st.session_state["app_tab3_trigger_calc"] = True
    st.session_state["tab3_solar_trigger_calc"] = True


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

    col_search, col_preset = st.columns([5, 5])

    with col_search:
        search_query = st.text_input(
            "Search City or Address (Worldwide):",
            placeholder="e.g. Mendoza, Berlin, Madrid, Santiago, Miami...",
            key=f"{key_prefix}_search_input"
        )
        if search_query and len(search_query.strip()) >= 2:
            search_results = search_locations_open_meteo(search_query.strip(), count=5)
            if search_results:
                options_dict = {f"{r['display_name']} ({r['lat']}°, {r['lon']}°)": r for r in search_results}
                selected_match_label = st.selectbox(
                    "Matching Locations (Select to apply):",
                    options=list(options_dict.keys()),
                    key=f"{key_prefix}_search_results"
                )
                if selected_match_label in options_dict:
                    chosen = options_dict[selected_match_label]
                    if abs(st.session_state[state_lat_key] - chosen["lat"]) > 0.001 or abs(st.session_state[state_lon_key] - chosen["lon"]) > 0.001:
                        _apply_location_update(
                            lat=chosen["lat"],
                            lon=chosen["lon"],
                            name=chosen["display_name"],
                            elevation=chosen.get("elevation", 500.0),
                            key_prefix=key_prefix
                        )
                        st.rerun()
            else:
                st.caption("No matching cities found. Try another spelling.")

    with col_preset:
        preset_choice = st.selectbox(
            "Quick Site Presets:",
            options=["-- Select a Preset Location --"] + list(SITE_PRESETS.keys()),
            index=0,
            key=f"{key_prefix}_preset_select"
        )
        if preset_choice in SITE_PRESETS:
            p_data = SITE_PRESETS[preset_choice]
            if abs(st.session_state[state_lat_key] - p_data["lat"]) > 0.001 or abs(st.session_state[state_lon_key] - p_data["lon"]) > 0.001:
                _apply_location_update(
                    lat=p_data["lat"],
                    lon=p_data["lon"],
                    name=p_data["name"],
                    elevation=p_data.get("elevation", 500.0),
                    key_prefix=key_prefix
                )
                st.rerun()

    cur_lat = float(st.session_state[state_lat_key])
    cur_lon = float(st.session_state[state_lon_key])
    cur_name = st.session_state.get(state_name_key, f"Site ({cur_lat:.3f}, {cur_lon:.3f})")

    # Interactive Folium Map (Loaded on-demand inside expander to eliminate lag)
    with st.expander("Interactive Site Map & Pin Location", icon=":material/map:", expanded=False):
        st.caption("Click anywhere on the map to pin exact site GPS coordinates:")
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

        map_out = st_folium(
            m,
            width="100%",
            height=300,
            returned_objects=["last_clicked"],
            key=f"{key_prefix}_interactive_map"
        )

        if map_out and map_out.get("last_clicked"):
            clicked = map_out["last_clicked"]
            click_lat = round(float(clicked["lat"]), 4)
            click_lon = round(float(clicked["lng"]), 4)
            prev_click = st.session_state.get(state_prev_click_key)

            if prev_click != (click_lat, click_lon) and (abs(click_lat - cur_lat) > 0.001 or abs(click_lon - cur_lon) > 0.001):
                st.session_state[state_prev_click_key] = (click_lat, click_lon)
                _apply_location_update(
                    lat=click_lat,
                    lon=click_lon,
                    name=f"Pinned Map Site ({click_lat:.3f}°, {click_lon:.3f}°)",
                    elevation=500.0,
                    key_prefix=key_prefix
                )
                st.rerun()

    # Manual Coordinate Fields
    with st.expander("Manual Coordinates & GPS Fine-Tuning", expanded=False):
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
                _apply_location_update(
                    lat=man_lat,
                    lon=cur_lon,
                    name=f"Coordinates ({man_lat:.3f}°, {cur_lon:.3f}°)",
                    elevation=float(st.session_state.get(state_elev_key, 500.0)),
                    key_prefix=key_prefix
                )
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
                _apply_location_update(
                    lat=cur_lat,
                    lon=man_lon,
                    name=f"Coordinates ({cur_lat:.3f}°, {man_lon:.3f}°)",
                    elevation=float(st.session_state.get(state_elev_key, 500.0)),
                    key_prefix=key_prefix
                )
                st.rerun()

    is_south = cur_lat < 0
    hemi_desc = "Southern Hemisphere (Optimal Orientation: North 0°, Tilt: ~29°)" if is_south else "Northern Hemisphere (Optimal Orientation: South 180°, Tilt: ~35°)"
    st.info(f"Active Site: **{cur_name}** | GPS: `{cur_lat:.4f}°`, `{cur_lon:.4f}°` | *{hemi_desc}*")

    return SolarLocation(
        name=cur_name,
        latitude=cur_lat,
        longitude=cur_lon,
        elevation_m=float(st.session_state.get(state_elev_key, 1000.0))
    )


def render_solar_config_form(
    location: SolarLocation,
    current_config: Optional[SolarPVConfig] = None,
    current_fin_config: Optional[SolarFinancialConfig] = None,
    key_prefix: str = "solar_cfg"
) -> Tuple[SolarPVConfig, SolarFinancialConfig, bool]:
    """
    Renders the Excel-aligned technical PV specification form (Input Panel & Year Sheet)
    with live reactive updating for module count, wattage, area requirements, and inverter rating.
    """
    from current_model.models.solar import TECHNOLOGY_SPECS

    # Defensive fallback for legacy objects in existing session states
    if current_config is not None:
        if not hasattr(current_config, "technology_preset") or not hasattr(current_config, "module_count"):
            cfg = SolarPVConfig(
                dc_capacity_kwp=getattr(current_config, "dc_capacity_kwp", 696.6),
                tilt_deg=getattr(current_config, "tilt_deg", 30.0),
                azimuth_deg=getattr(current_config, "azimuth_deg", 0.0),
                inverter_capacity_kw=getattr(current_config, "inverter_capacity_kw", 590.0),
                inverter_efficiency_pct=getattr(current_config, "inverter_efficiency_pct", 98.0)
            )
        else:
            cfg = current_config
    else:
        cfg = SolarPVConfig(module_count=600, module_power_wp=450.0, inverter_capacity_kw=230.0)

    is_south = location.latitude < 0
    default_azimuth = 0.0 if is_south else 180.0
    default_tilt = float(round(max(10.0, min(60.0, abs(location.latitude) * 0.85)), 0))

    st.subheader("2. Solar PV Technical Specifications & Generator Sizing")
    st.caption("Configure solar module quantities, rated wattage, cell technology, mounting area, and inverter limits:")

    # Compact Educational Guide on Cell Technologies
    with st.expander("Technology Guide: What are PERC, TOPCon, and Backcontact?", expanded=False):
        st.markdown(
            """
            | Technology | Std. Power | Temp. Coeff. γ | Degradation (Y1 / Annual) | Core Characteristics |
            | :--- | :---: | :---: | :---: | :--- |
            | **PERC** | 410 Wp | -0.35 %/°C | 2.0 % / 0.55 %/a | Cost-effective P-Type industrial standard. Higher initial LID degradation. |
            | **TOPCon** | 450 Wp | -0.29 %/°C | 1.5 % / 0.40 %/a | Modern N-Type benchmark: +9.8 % power density, superior low-light yield. |
            | **Backcontact** | 470 Wp | -0.26 %/°C | 1.0 % / 0.35 %/a | Premium IBC tier: Zero front busbar shading, lowest thermal losses. |
            """
        )

    # Compact Educational Guide on Weather Data Foundations
    with st.expander("Educational Guide: How Solar Weather Data and Multi-Year Modeling Work", expanded=False):
        st.markdown(
            """
            * **Typical Meteorological Year (TMY / ISO 15927-4):** Normalized 1-year climatological dataset combining 12 representative historical months from 10–20 years. Preserves true cloud dynamics and diurnal swings without single-year weather anomalies. International bankability standard (PVGIS/NREL).
            * **Specific Historical Calendar Year:** Exact hourly measurements from a single calendar year (e.g. 2024). Best for reconciling simulations against actual utility billing invoices.
            * **Multi-Year P50 / P90 Risk Analysis (2015–2024):** Empirical 10-year simulation:
              - **P50 (Median Expected Yield):** 50% probability of exceedance; baseline for ROI and payback models.
              - **P90 (Debt-Sizing Limit):** Conservative threshold reached in 90% of years; required by commercial lenders.
              - **Volatility Bandwidth:** Inter-annual yield spread between best and worst historical years.
            """
        )

    # Technical Specifications Form (Buffered in st.form to eliminate UI lag & reruns on input)
    with st.form(key=f"{key_prefix}_specs_form", clear_on_submit=False):
        # 1. Weather Data Foundation & Multi-Year Evaluation
        st.markdown("##### 1. Weather Data Foundation & Multi-Year Evaluation")
        weather_mode_options = [
            "Typical Meteorological Year (TMY - 10-to-20 Year Climatological Baseline) [Default]",
            "Specific Historical Calendar Year (e.g. 2024, 2023, 2022, 2021, 2020)",
            "Multi-Year Range & P50 / P90 Risk Analysis (2015-2024)"
        ]

        current_w_mode = getattr(cfg, "weather_mode", "TMY")
        w_idx = 0
        if current_w_mode == "single_year":
            w_idx = 1
        elif current_w_mode == "multi_year":
            w_idx = 2

        w_col1, w_col2 = st.columns([7, 5])
        with w_col1:
            chosen_w_label = st.selectbox(
                "Select Weather Data Mode:",
                options=weather_mode_options,
                index=w_idx,
                help="Choose between long-term climatological TMY, specific historical calendar years, or 10-year P50/P90 risk simulation.",
                key=f"{key_prefix}_weather_mode_select"
            )

        selected_mode = "TMY"
        selected_year = getattr(cfg, "selected_weather_year", 2024)
        if "Specific Historical" in chosen_w_label:
            selected_mode = "single_year"
            with w_col2:
                selected_year = st.selectbox(
                    "Historical Calendar Year:",
                    options=[2024, 2023, 2022, 2021, 2020],
                    index=0,
                    key=f"{key_prefix}_hist_year_select"
                )
        elif "Multi-Year Range" in chosen_w_label:
            selected_mode = "multi_year"
            with w_col2:
                st.caption("10-Year Historical Evaluation Horizon: **2015 - 2024** (Computes P50 expected yield, P90 debt sizing, and volatility range)")

        # 2. Module Quantities & Cell Technology (Input Panel)
        st.markdown("##### 2. Module Quantity & Cell Technology (Input Panel)")
        c1, c2, c3 = st.columns([4, 4, 4])

        with c1:
            tech_options = [
                "TOPCon (450 Wp - N-Type Modern Standard)",
                "PERC (410 Wp - P-Type Standard)",
                "Backcontact / IBC (470 Wp - Premium)",
                "Custom Parameters"
            ]
            current_tech_idx = 0
            preset_name = getattr(cfg, "technology_preset", "TOPCon")
            if preset_name == "PERC":
                current_tech_idx = 1
            elif preset_name == "Backcontact":
                current_tech_idx = 2
            elif preset_name == "Custom":
                current_tech_idx = 3

            selected_tech = st.selectbox(
                "Cell Technology Preset:",
                options=tech_options,
                index=current_tech_idx,
                key=f"{key_prefix}_tech_choice"
            )

        # Technology Parameter Presets
        if "TOPCon" in selected_tech:
            preset_key = "TOPCon"
            def_wp = 450.0
            def_gamma = -0.29
            def_d1 = 1.50
            def_d2 = 0.40
        elif "PERC" in selected_tech:
            preset_key = "PERC"
            def_wp = 410.0
            def_gamma = -0.35
            def_d1 = 2.00
            def_d2 = 0.55
        elif "Backcontact" in selected_tech:
            preset_key = "Backcontact"
            def_wp = 470.0
            def_gamma = -0.26
            def_d1 = 1.00
            def_d2 = 0.35
        else:
            preset_key = "Custom"
            def_wp = getattr(cfg, "module_power_wp", 450.0)
            def_gamma = getattr(cfg, "temp_coefficient_pct_c", -0.29)
            def_d1 = getattr(cfg, "first_year_degradation_pct", 1.50)
            def_d2 = getattr(cfg, "annual_degradation_pct", 0.40)

        with c2:
            default_mod_count = int(st.session_state.get(f"{key_prefix}_mod_count", getattr(cfg, "module_count", 600) or 600))
            mod_count = st.number_input(
                "Amount of Modules (Units):",
                min_value=0,
                max_value=200000,
                value=default_mod_count,
                step=10,
                help="Total number of physical PV panels (e.g. 600, 1548).",
                key=f"{key_prefix}_mod_count"
            )

        with c3:
            mod_wp = st.number_input(
                "Module Rated Power (Wp / Unit):",
                min_value=50.0,
                max_value=1000.0,
                value=float(def_wp),
                step=5.0,
                format="%.1f",
                help="Rated STC peak power per module in Watts-peak (Wp).",
                key=f"{key_prefix}_mod_wp"
            )

        # Dynamic Calculated DC Capacity Info Banner
        calc_dc_kwp = round((mod_count * mod_wp) / 1000.0, 2)
        if calc_dc_kwp > 0:
            st.info(f"**Installed DC Generator Capacity:** `{calc_dc_kwp:,.2f} kWp` ({mod_count:,} Modules × {mod_wp:.0f} Wp)")
        else:
            st.info("**Installed DC Generator Capacity:** `0.00 kWp` *(Tip: Enter your module count and click 'Calculate Solar PV Generation' at the bottom of this form to apply)*")

        # 3. Physical Dimensions & Area Requirements (Year Sheet)
        st.markdown("##### 3. Physical Dimensions & Required Area (Year Sheet)")
        a1, a2, a3 = st.columns(3)
        with a1:
            mod_len = st.number_input(
                "Module Length (m):",
                min_value=0.5,
                max_value=3.0,
                value=float(getattr(cfg, "module_length_m", 1.76)),
                step=0.05,
                format="%.2f",
                help="Physical length of panel (standard: 1.76m or 1.2m).",
                key=f"{key_prefix}_mod_len"
            )
        with a2:
            mod_wid = st.number_input(
                "Module Width (m):",
                min_value=0.3,
                max_value=2.0,
                value=float(getattr(cfg, "module_width_m", 1.13)),
                step=0.05,
                format="%.2f",
                help="Physical width of panel (standard: 1.13m or 0.7m).",
                key=f"{key_prefix}_mod_wid"
            )
        with a3:
            area_factor = st.number_input(
                "Area Spacing Factor (Row Pitch):",
                min_value=1.0,
                max_value=3.0,
                value=float(getattr(cfg, "area_factor", 1.40)),
                step=0.1,
                format="%.2f",
                help="1.0 = flush coplanar roof, 1.4 - 1.8 = ground mount / tilted rows with shadow clearance.",
                key=f"{key_prefix}_area_fact"
            )

        gross_panel_area = mod_count * mod_len * mod_wid
        req_total_area = gross_panel_area * area_factor
        st.caption(f"**Net Active Panel Area:** `{gross_panel_area:,.1f} m²` | **Total Required Installation Area:** `{req_total_area:,.1f} m²` (Pitch Factor: {area_factor:.2f})")

        # 4. Temperature Physics & 2-Stage Degradation
        st.markdown("##### 4. Temperature Physics & 2-Stage Degradation")
        d1_col, d2_col, d3_col = st.columns(3)
        with d1_col:
            temp_coeff = st.number_input(
                "Temperature Coeff. γ (%/°C above 25°C):",
                min_value=-1.0,
                max_value=0.0,
                value=float(def_gamma),
                step=0.01,
                format="%.2f",
                help="Derate coefficient per °C above 25°C cell temp. Standard: -0.25%/°C to -0.29%/°C.",
                key=f"{key_prefix}_temp_coeff"
            )
        with d2_col:
            first_yr_deg = st.number_input(
                "Year 1 Degradation (%):",
                min_value=0.0,
                max_value=10.0,
                value=float(def_d1),
                step=0.1,
                format="%.2f",
                help="Initial light-induced degradation (LID) in year 1.",
                key=f"{key_prefix}_deg_y1"
            )
        with d3_col:
            annual_deg = st.number_input(
                "Annual Degradation (%/year, Y2+):",
                min_value=0.0,
                max_value=5.0,
                value=float(def_d2),
                step=0.05,
                format="%.2f",
                help="Linear degradation per year for years 2 through 15.",
                key=f"{key_prefix}_deg_annual"
            )

        # 5. Mounting Orientation & Inverter Limits
        st.markdown("##### 5. Mounting Orientation & Inverter Limits")
        g1, g2, g3, g4 = st.columns(4)
        with g1:
            tilt_deg = st.number_input(
                "Tilt Angle β (°):",
                min_value=0.0,
                max_value=90.0,
                value=float(default_tilt),
                step=1.0,
                format="%.1f",
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
                help="0° = North (Optimal for South Hemisphere like Mendoza), 180° = South.",
                key=f"{key_prefix}_azimuth"
            )
        with g3:
            # Dynamically auto-scale recommended inverter size if not manually customized
            rec_inv_kw = float(round(calc_dc_kwp / 1.175, 1)) if calc_dc_kwp > 0 else 380.0
            init_inv_kw = float(getattr(cfg, "inverter_capacity_kw", 0.0) or 0.0)
            if init_inv_kw <= 0.0 and rec_inv_kw > 0.0:
                init_inv_kw = rec_inv_kw
            inverter_kw = st.number_input(
                "Inverter AC Limit (kW):",
                min_value=0.0,
                max_value=50000.0,
                value=float(init_inv_kw),
                step=10.0,
                format="%.1f",
                help="Maximum AC inverter power (DC/AC ~ 1.175). Power exceeding this rating is clipped.",
                key=f"{key_prefix}_inv_kw"
            )
        with g4:
            inverter_eff = st.number_input(
                "Inverter Efficiency (%):",
                min_value=80.0,
                max_value=100.0,
                value=98.0,
                step=0.1,
                format="%.1f",
                key=f"{key_prefix}_inv_eff"
            )

        # 6. Solar Financial & Investment Parameters (DRACBV Kosten-/Berechnungs-Dashboard)
        st.markdown("##### 6. Solar Financial & Turn-Key Investment Costs (Optional)")
        st.caption("Enter investment costs to calculate CAPEX breakdown, LCOE (€/kWh), and 15-year life-cycle ROI. *Leave empty/unchecked if you wish to run technical generation only.*")

        existing_fin = (
            current_fin_config or 
            st.session_state.get(f"{key_prefix}_fin_config") or 
            st.session_state.get("solar_financial_config") or 
            st.session_state.get("app_tab3_fin_config") or 
            SolarFinancialConfig(is_enabled=True)
        )
        is_fin_active = st.checkbox(
            "Enable Solar Financial Assessment & Turn-Key CAPEX Calculation",
            value=getattr(existing_fin, "is_enabled", True),
            key=f"{key_prefix}_enable_financials",
            help="When checked, computes itemized CAPEX (modules, inverters, substructure, installation), LCOE, and cash-flow timeline."
        )

        fin_curr = getattr(existing_fin, "currency", "EUR")
        fin_mod_wp = getattr(existing_fin, "cost_modules_per_wp", None)
        fin_inv_w = getattr(existing_fin, "cost_inverter_per_w", None)
        fin_sub_wp = getattr(existing_fin, "cost_substructure_per_wp", None)
        fin_inst_wp = getattr(existing_fin, "cost_installation_per_wp", None)
        fin_switch = getattr(existing_fin, "fixed_switchgear_cost", 0.0)
        fin_travel = getattr(existing_fin, "fixed_travel_fee", 0.0)
        fin_opex = getattr(existing_fin, "annual_opex_pct", 1.0)
        fin_infl = getattr(existing_fin, "electricity_price_inflation_pct", 3.0)
        fin_disc = getattr(existing_fin, "discount_rate_pct", 5.0)
        fin_feed = getattr(existing_fin, "feed_in_tariff_per_kwh", 0.06)

        fc1, fc2, fc3 = st.columns(3)
        with fc1:
            inp_curr = st.text_input("Currency Code / Symbol:", value=fin_curr, key=f"{key_prefix}_fin_curr")
            inp_mod_wp = st.number_input(
                f"Solar Modules ({inp_curr}/Wp):",
                min_value=0.0,
                max_value=10.0,
                value=float(fin_mod_wp if fin_mod_wp is not None else 1.00),
                step=0.05,
                format="%.2f",
                help="Turn-key cost per Watt-peak for modules (e.g. 1.00 €/Wp).",
                key=f"{key_prefix}_fin_mod_wp"
            )
            inp_switch = st.number_input(
                f"Switchgear Cabinet ({inp_curr}):",
                min_value=0.0,
                value=float(fin_switch),
                step=250.0,
                help="Fixed meter and switchgear cabinet fee (e.g. 2,500 €).",
                key=f"{key_prefix}_fin_switch"
            )

        with fc2:
            inp_inv_w = st.number_input(
                f"Inverter AC Power ({inp_curr}/W AC):",
                min_value=0.0,
                max_value=2.0,
                value=float(fin_inv_w if fin_inv_w is not None else 0.07),
                step=0.01,
                format="%.2f",
                help="Cost per Watt AC for inverters (e.g. 0.07 €/W = 70 €/kW).",
                key=f"{key_prefix}_fin_inv_w"
            )
            inp_sub_wp = st.number_input(
                f"Substructure / Racking ({inp_curr}/Wp):",
                min_value=0.0,
                max_value=5.0,
                value=float(fin_sub_wp if fin_sub_wp is not None else 0.15),
                step=0.01,
                format="%.2f",
                help="Mounting racks, substructure & trackers (e.g. 0.15 €/Wp).",
                key=f"{key_prefix}_fin_sub_wp"
            )
            inp_travel = st.number_input(
                f"Mobilization Fee ({inp_curr}):",
                min_value=0.0,
                value=float(fin_travel),
                step=100.0,
                help="Fixed site mobilization & travel charge (e.g. 1,000 €).",
                key=f"{key_prefix}_fin_travel"
            )

        with fc3:
            inp_inst_wp = st.number_input(
                f"Installation & AC Connect ({inp_curr}/Wp):",
                min_value=0.0,
                max_value=5.0,
                value=float(fin_inst_wp if fin_inst_wp is not None else 0.35),
                step=0.01,
                format="%.2f",
                help="Electrical wiring, assembly and certification (e.g. 0.35 €/Wp).",
                key=f"{key_prefix}_fin_inst_wp"
            )
            inp_opex = st.number_input(
                "Annual O&M & Insurance (% of CAPEX/a):",
                min_value=0.0,
                max_value=10.0,
                value=float(fin_opex),
                step=0.1,
                format="%.1f",
                help="Annual operational expenditure and maintenance reserve.",
                key=f"{key_prefix}_fin_opex"
            )
            inp_disc = st.number_input(
                "Discount Rate / Kalkulationszins (%):",
                min_value=0.0,
                max_value=20.0,
                value=float(fin_disc),
                step=0.5,
                format="%.1f",
                help="Capital interest rate used for NPV and LCOE discounting.",
                key=f"{key_prefix}_fin_disc"
            )

        submitted = st.form_submit_button(
            "Calculate Solar PV Generation & Multi-Technology Comparison",
            icon=":material/calculate:",
            type="primary",
            use_container_width=True
        )

    if submitted and mod_count <= 0:
        st.error("Sizing Required: Please enter a module count greater than 0 before calculating, or click 'Load Example Case' above.", icon=":material/warning:")

    calc_dc = round((mod_count * mod_wp) / 1000.0, 2)
    final_inv_kw = float(inverter_kw)
    if final_inv_kw <= 0.0 and calc_dc > 0:
        final_inv_kw = float(round(calc_dc / 1.175, 1))

    updated_config = SolarPVConfig(
        module_count=int(mod_count),
        module_power_wp=float(mod_wp),
        technology_preset=preset_key,
        module_technology=selected_tech,
        temp_coefficient_pct_c=float(temp_coeff),
        first_year_degradation_pct=float(first_yr_deg),
        annual_degradation_pct=float(annual_deg),
        degradation_pct_a=float(annual_deg),
        module_length_m=float(mod_len),
        module_width_m=float(mod_wid),
        area_factor=float(area_factor),
        tilt_deg=float(tilt_deg),
        azimuth_deg=float(azimuth_deg),
        albedo=0.20,
        inverter_capacity_kw=float(final_inv_kw),
        inverter_efficiency_pct=float(inverter_eff),
        soiling_loss_pct=2.0,
        shading_loss_pct=1.5,
        dc_wiring_loss_pct=1.5,
        economic_lifetime_years=15,
        weather_mode=selected_mode,
        selected_weather_year=int(selected_year)
    )

    fin_config = SolarFinancialConfig(
        is_enabled=bool(is_fin_active),
        currency=str(inp_curr or "EUR").strip(),
        cost_modules_per_wp=float(inp_mod_wp),
        cost_inverter_per_w=float(inp_inv_w),
        cost_substructure_per_wp=float(inp_sub_wp),
        cost_installation_per_wp=float(inp_inst_wp),
        fixed_switchgear_cost=float(inp_switch),
        fixed_travel_fee=float(inp_travel),
        annual_opex_pct=float(inp_opex),
        discount_rate_pct=float(inp_disc),
        electricity_price_inflation_pct=float(fin_infl),
        feed_in_tariff_per_kwh=float(fin_feed),
        analysis_horizon_years=15
    )

    return updated_config, fin_config, submitted
