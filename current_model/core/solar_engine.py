"""
========================================================================================
Solar PV Simulation & Radiation Engine (current_model/core/solar_engine.py)
========================================================================================

Description:
------------
Integrates Open-Meteo Solar API with a physical photovoltaic simulation model to compute:
  - Global Horizontal & Plane-of-Array (POA) solar irradiance
  - Dynamic cell temperature modeling based on ambient temperature and NMOT
  - Temperature derating & Balance of System (BOS) system losses
  - Inverter AC conversion efficiency and power clipping
  - Key Performance Indicators (Specific Yield kWh/kWp, PR %, Capacity Factor, Monthly Yields)
  - Offline fallback clear-sky radiation generator for offline/resilient execution
"""

from typing import Optional, Dict, List, Tuple, Any
import datetime
import math
import numpy as np
import pandas as pd
import requests

from current_model.models.solar import (
    SolarLocation,
    SolarPVConfig,
    SolarMonthlyYield,
    SolarKPIs,
    SolarSimulationResult
)

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
]
DAYS_IN_MONTHS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def search_locations_open_meteo(query: str, count: int = 5, timeout_sec: int = 4) -> List[Dict[str, Any]]:
    """
    Searches for cities/places worldwide using the free Open-Meteo Geocoding API.
    Returns a list of matching locations with name, country, admin province, lat, lon, and elevation.
    """
    if not query or len(query.strip()) < 2:
        return []

    url = f"https://geocoding-api.open-meteo.com/v1/search?name={requests.utils.quote(query.strip())}&count={count}&language=en&format=json"
    try:
        resp = requests.get(url, timeout=timeout_sec)
        if resp.status_code == 200:
            results = resp.json().get("results", [])
            output = []
            for item in results:
                admin = item.get("admin1", "")
                country = item.get("country", "")
                name = item.get("name", "")
                disp_parts = [name]
                if admin and admin != name:
                    disp_parts.append(admin)
                if country:
                    disp_parts.append(country)
                output.append({
                    "name": name,
                    "display_name": ", ".join(disp_parts),
                    "lat": round(float(item.get("latitude", 0.0)), 4),
                    "lon": round(float(item.get("longitude", 0.0)), 4),
                    "elevation": float(item.get("elevation", 0.0)),
                    "timezone": item.get("timezone", "auto"),
                    "country_code": item.get("country_code", "")
                })
            return output
    except Exception:
        pass
    return []



def generate_synthetic_solar_weather(
    latitude: float,
    longitude: float,
    tilt_deg: float = 30.0,
    azimuth_deg: float = 0.0,
    year: int = 2024
) -> pd.DataFrame:
    """
    Robust analytical clear-sky solar radiation and ambient temperature model (8,760 hourly intervals).
    Used as an offline fallback or baseline when external API is unreachable.
    """
    start_dt = pd.Timestamp(f"{year}-01-01 00:00:00")
    timestamps = pd.date_range(start=start_dt, periods=8760, freq="1h")

    lat_rad = math.radians(latitude)
    tilt_rad = math.radians(tilt_deg)
    # Southern hemisphere summer is in Jan/Dec, winter in Jun/Jul
    is_south = (latitude < 0)

    ghi_arr = np.zeros(8760, dtype=float)
    dni_arr = np.zeros(8760, dtype=float)
    dhi_arr = np.zeros(8760, dtype=float)
    poa_arr = np.zeros(8760, dtype=float)
    temp_arr = np.zeros(8760, dtype=float)

    base_temp = 16.0 - abs(latitude) * 0.2

    for i, ts in enumerate(timestamps):
        day_of_year = ts.dayofyear
        hour = ts.hour + ts.minute / 60.0

        # Solar declination angle
        declination = 23.45 * math.sin(math.radians(360.0 / 365.0 * (284 + day_of_year)))
        dec_rad = math.radians(declination)

        # Solar hour angle (12:00 = 0°)
        hour_angle = 15.0 * (hour - 12.0)
        ha_rad = math.radians(hour_angle)

        # Solar zenith angle / elevation
        sin_elev = math.sin(lat_rad) * math.sin(dec_rad) + math.cos(lat_rad) * math.cos(dec_rad) * math.cos(ha_rad)
        solar_elevation_deg = math.degrees(math.asin(max(-1.0, min(1.0, sin_elev))))

        if solar_elevation_deg > 0.0:
            zenith_rad = math.radians(90.0 - solar_elevation_deg)
            # Extraterrestrial irradiance with eccentricity
            e_0 = 1367.0 * (1.0 + 0.033 * math.cos(math.radians(360.0 * day_of_year / 365.0)))

            # Air Mass
            air_mass = 1.0 / (math.cos(zenith_rad) + 0.50572 * max(0.01, (96.07995 - (90.0 - solar_elevation_deg))) ** -1.6364)
            air_mass = min(30.0, max(1.0, air_mass))

            # Clear sky GHI (Haurwitz model approximation)
            ghi = max(0.0, 1098.0 * math.cos(zenith_rad) * math.exp(-0.057 / max(0.05, math.cos(zenith_rad))))
            ghi = min(ghi, e_0 * math.cos(zenith_rad))

            dhi = ghi * (0.15 + 0.10 * (1.0 - math.cos(zenith_rad)))
            dni = (ghi - dhi) / max(0.05, math.cos(zenith_rad))

            # Approximate Plane of Array (POA) irradiance with tilt factor
            # Optimal angle boost:
            cos_inc = math.cos(zenith_rad) * math.cos(tilt_rad) + math.sin(zenith_rad) * math.sin(tilt_rad)
            poa = max(0.0, dni * max(0.0, cos_inc) + dhi * (1.0 + math.cos(tilt_rad)) / 2.0 + ghi * 0.20 * (1.0 - math.cos(tilt_rad)) / 2.0)

            ghi_arr[i] = round(ghi, 2)
            dni_arr[i] = round(dni, 2)
            dhi_arr[i] = round(dhi, 2)
            poa_arr[i] = round(poa, 2)

        # Ambient temperature model (seasonal + daily sine wave)
        seasonal_phase = (day_of_year - 20) / 365.0 * 2.0 * math.pi
        seasonal_temp = -10.0 * math.cos(seasonal_phase) if is_south else 10.0 * math.cos(seasonal_phase - math.pi)
        daily_temp = 5.5 * math.sin(math.radians((hour - 9.0) / 24.0 * 360.0))
        temp_arr[i] = round(base_temp + seasonal_temp + daily_temp, 1)

    df_weather = pd.DataFrame({
        "timestamp": timestamps,
        "GHI_W_m2": ghi_arr,
        "DNI_W_m2": dni_arr,
        "DHI_W_m2": dhi_arr,
        "POA_W_m2": poa_arr,
        "Temp_Ambient_C": temp_arr
    })
    return df_weather


def fetch_open_meteo_solar_data(
    latitude: float,
    longitude: float,
    tilt_deg: float = 30.0,
    azimuth_deg: float = 0.0,
    year: int = 2024,
    timeout_sec: int = 8
) -> Tuple[pd.DataFrame, str]:
    """
    Fetches real solar irradiance and temperature data from Open-Meteo API.
    Falls back gracefully to synthetic solar clear-sky engine if network is unavailable.
    Returns (weather_dataframe, data_source_label).
    """
    # 1. Try Historical Archive API for a full 1-year historical dataset
    archive_url = (
        f"https://archive-api.open-meteo.com/v1/archive"
        f"?latitude={latitude:.4f}&longitude={longitude:.4f}"
        f"&start_date={year}-01-01&end_date={year}-12-31"
        f"&hourly=shortwave_radiation,direct_normal_irradiance,diffuse_radiation,direct_radiation,temperature_2m"
        f"&timezone=auto"
    )

    try:
        resp = requests.get(archive_url, timeout=timeout_sec)
        if resp.status_code == 200:
            data = resp.json()
            hourly = data.get("hourly", {})
            times = pd.to_datetime(hourly.get("time", []))
            ghi = np.array(hourly.get("shortwave_radiation", []), dtype=float)
            dni = np.array(hourly.get("direct_normal_irradiance", []), dtype=float)
            dhi = np.array(hourly.get("diffuse_radiation", []), dtype=float)
            temp_amb = np.array(hourly.get("temperature_2m", []), dtype=float)

            if len(times) >= 8700:
                # Transpose GHI/DNI to Plane of Array (POA) using Hay-Davies isotropic transposition
                tilt_rad = math.radians(tilt_deg)
                lat_rad = math.radians(latitude)
                poa_list = []

                for i, ts in enumerate(times):
                    g = max(0.0, ghi[i]) if i < len(ghi) else 0.0
                    d = max(0.0, dhi[i]) if i < len(dhi) else 0.0
                    dn = max(0.0, dni[i]) if i < len(dni) else 0.0

                    if g <= 0.0:
                        poa_list.append(0.0)
                        continue

                    day_of_year = ts.dayofyear
                    hour = ts.hour + ts.minute / 60.0
                    declination = 23.45 * math.sin(math.radians(360.0 / 365.0 * (284 + day_of_year)))
                    dec_rad = math.radians(declination)
                    ha_rad = math.radians(15.0 * (hour - 12.0))

                    sin_elev = math.sin(lat_rad) * math.sin(dec_rad) + math.cos(lat_rad) * math.cos(dec_rad) * math.cos(ha_rad)
                    if sin_elev > 0.05:
                        zenith_rad = math.asin(min(1.0, sin_elev))
                        cos_inc = math.sin(zenith_rad) * math.cos(tilt_rad) + math.cos(zenith_rad) * math.sin(tilt_rad)
                        poa_val = dn * max(0.0, cos_inc) + d * (1.0 + math.cos(tilt_rad)) / 2.0 + g * 0.20 * (1.0 - math.cos(tilt_rad)) / 2.0
                        poa_list.append(max(0.0, float(poa_val)))
                    else:
                        poa_list.append(0.0)

                df = pd.DataFrame({
                    "timestamp": times,
                    "GHI_W_m2": ghi,
                    "DNI_W_m2": dni,
                    "DHI_W_m2": dhi,
                    "POA_W_m2": np.array(poa_list),
                    "Temp_Ambient_C": temp_amb
                })
                return df, f"Open-Meteo Historical Archive ({year})"

    except Exception:
        pass

    # 2. Fallback to High-Accuracy Clear-Sky Physical Engine
    df_synthetic = generate_synthetic_solar_weather(
        latitude=latitude,
        longitude=longitude,
        tilt_deg=tilt_deg,
        azimuth_deg=azimuth_deg,
        year=year
    )
    return df_synthetic, "Analytical Solar Radiation Engine (Clear-Sky Model)"


def simulate_solar_pv_generation(
    config: SolarPVConfig,
    location: SolarLocation,
    weather_df: Optional[pd.DataFrame] = None
) -> SolarSimulationResult:
    """
    Executes physical Solar PV generation simulation across all hourly intervals:
      1. Irradiance on plane of array (POA)
      2. Dynamic cell temperature modeling: T_cell = T_amb + POA * (NMOT - 20) / 800
      3. Temperature derating: f_temp = 1 + gamma * (T_cell - 25)
      4. System DC losses: soiling, shading, DC wiring
      5. Inverter AC conversion & clipping: P_ac = min(P_dc * eta_inv, P_ac_max)
      6. Monthly yields, annual energy, specific yield (kWh/kWp), PR (%), Capacity Factor
    """
    if weather_df is None or weather_df.empty:
        weather_df, _ = fetch_open_meteo_solar_data(
            latitude=location.latitude,
            longitude=location.longitude,
            tilt_deg=config.tilt_deg,
            azimuth_deg=config.azimuth_deg
        )

    df = weather_df.copy()
    timestamps = pd.to_datetime(df["timestamp"])
    df["timestamp"] = timestamps

    poa = df["POA_W_m2"].to_numpy(dtype=float)
    t_amb = df["Temp_Ambient_C"].to_numpy(dtype=float)

    # 1. Cell Temperature
    # T_cell = T_amb + POA * (NMOT - 20) / 800
    nmot = float(config.nmot_c)
    t_cell = t_amb + poa * ((nmot - 20.0) / 800.0)
    df["Temp_Cell_C"] = np.round(t_cell, 1)

    # 2. Temperature Derate Factor
    gamma = float(config.temp_coefficient_pct_c) / 100.0
    f_temp = 1.0 + gamma * (t_cell - 25.0)
    # Physical clamp: f_temp > 0.4
    f_temp = np.clip(f_temp, 0.40, 1.20)
    df["Thermal_Derate_Factor"] = np.round(f_temp, 4)

    # 3. DC Power Generation (kW)
    # P_dc_ideal = P_dc_nom * (POA / 1000 W/m2)
    p_nom = float(config.dc_capacity_kwp)
    p_dc_ideal = p_nom * (poa / 1000.0)
    dc_loss_factor = (1.0 - config.total_dc_loss_pct / 100.0)
    p_dc = np.maximum(0.0, p_dc_ideal * f_temp * dc_loss_factor)
    df["P_DC_kW"] = np.round(p_dc, 2)

    # 4. Inverter AC Conversion & Inverter Clipping
    eta_inv = float(config.inverter_efficiency_pct) / 100.0
    p_ac_max = float(config.inverter_capacity_kw)
    p_ac_uncapped = p_dc * eta_inv
    p_ac = np.minimum(p_ac_uncapped, p_ac_max)
    clipping_loss = np.maximum(0.0, p_ac_uncapped - p_ac_max)

    df["P_AC_kW"] = np.round(p_ac, 2)
    df["Clipping_Loss_kW"] = np.round(clipping_loss, 2)

    # 5. Monthly Aggregations
    df["month"] = timestamps.dt.month
    monthly_yields: List[SolarMonthlyYield] = []

    for m_idx in range(1, 13):
        m_mask = (df["month"] == m_idx)
        m_df = df.loc[m_mask]
        m_name = MONTH_NAMES[m_idx - 1]
        m_days = DAYS_IN_MONTHS[m_idx - 1]

        if not m_df.empty:
            m_kwh = float(m_df["P_AC_kW"].sum())
            m_mwh = m_kwh / 1000.0
            m_avg_daily = m_kwh / max(1, m_days)
            m_peak = float(m_df["P_AC_kW"].max())
            m_spec_yield = m_kwh / max(0.1, p_nom)
            m_cf = (m_kwh / (p_nom * m_days * 24.0)) * 100.0 if p_nom > 0 else 0.0
        else:
            m_kwh, m_mwh, m_avg_daily, m_peak, m_spec_yield, m_cf = 0.0, 0.0, 0.0, 0.0, 0.0, 0.0

        monthly_yields.append(
            SolarMonthlyYield(
                month_name=m_name,
                month_idx=m_idx,
                days_count=m_days,
                energy_kwh=round(m_kwh, 1),
                energy_mwh=round(m_mwh, 3),
                avg_daily_kwh=round(m_avg_daily, 1),
                peak_power_kw=round(m_peak, 1),
                capacity_factor_pct=round(m_cf, 1),
                specific_yield_kwh_kwp=round(m_spec_yield, 1)
            )
        )

    # 6. Comprehensive KPIs
    annual_energy_kwh = float(df["P_AC_kW"].sum())
    annual_energy_mwh = annual_energy_kwh / 1000.0
    specific_yield = annual_energy_kwh / max(0.1, p_nom)
    full_load_hours = annual_energy_kwh / max(0.1, p_nom)
    capacity_factor = (annual_energy_kwh / (p_nom * 8760.0) * 100.0) if p_nom > 0 else 0.0

    # Total Solar Irradiance Energy on POA (kWh/m2)
    poa_energy_kwh_m2 = float(poa.sum() / 1000.0)
    ghi_energy_kwh_m2 = float(df["GHI_W_m2"].sum() / 1000.0) if "GHI_W_m2" in df.columns else poa_energy_kwh_m2

    # Performance Ratio (PR) = Actual AC Energy / (Nominal DC Capacity * POA Irradiance / 1000)
    ideal_poa_energy_kwh = p_nom * poa_energy_kwh_m2
    performance_ratio = (annual_energy_kwh / ideal_poa_energy_kwh * 100.0) if ideal_poa_energy_kwh > 0 else 0.0

    total_clipping_loss_kwh = float(df["Clipping_Loss_kW"].sum())
    # Thermal losses (relative to STC 25°C)
    stc_dc_energy_kwh = float((p_nom * (poa / 1000.0) * dc_loss_factor).sum())
    actual_dc_energy_kwh = float(df["P_DC_kW"].sum())
    thermal_loss_kwh = max(0.0, stc_dc_energy_kwh - actual_dc_energy_kwh)

    kpis = SolarKPIs(
        annual_energy_mwh=round(annual_energy_mwh, 2),
        annual_energy_kwh=round(annual_energy_kwh, 0),
        specific_yield_kwh_per_kwp=round(specific_yield, 1),
        performance_ratio_pct=round(performance_ratio, 1),
        capacity_factor_pct=round(capacity_factor, 1),
        full_load_hours=round(full_load_hours, 0),
        max_ac_power_kw=round(float(df["P_AC_kW"].max()), 1),
        max_dc_power_kw=round(float(df["P_DC_kW"].max()), 1),
        clipping_loss_kwh=round(total_clipping_loss_kwh, 1),
        thermal_loss_kwh=round(thermal_loss_kwh, 1),
        location_name=location.name,
        global_horizontal_irradiance_mwh_m2=round(ghi_energy_kwh_m2 / 1000.0, 2)
    )

    # 7. Loss Waterfall Breakdown (%)
    loss_breakdown = {
        "Nominal Plane-of-Array Potential": round(ideal_poa_energy_kwh, 1),
        "Thermal Losses (Temperature Derate)": round(thermal_loss_kwh, 1),
        "BOS & System Losses (Soiling, DC Wiring)": round(stc_dc_energy_kwh * (config.total_dc_loss_pct / 100.0), 1),
        "Inverter Conversion Loss": round(actual_dc_energy_kwh * (1.0 - eta_inv), 1),
        "Inverter Clipping Loss": round(total_clipping_loss_kwh, 1),
        "Net AC Energy Delivered": round(annual_energy_kwh, 1)
    }

    return SolarSimulationResult(
        config=config,
        location=location,
        df_timeseries=df,
        monthly_yields=monthly_yields,
        kpis=kpis,
        loss_breakdown=loss_breakdown
    )
