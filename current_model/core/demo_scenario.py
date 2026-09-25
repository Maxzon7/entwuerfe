"""
========================================================================================
Demo Scenario Engine: Example 1 (current_model/core/demo_scenario.py)
========================================================================================

Description:
------------
Provides the centralized "Example1" demonstration scenario factory and state orchestrator:
  - Tab 1 (Consumption): 365-Day European Commercial Facility (~1,120 MWh/a, 395 kW peak).
  - Tab 2 (Contract): Commercial Multi-Tariff Contract (EUR, 400 kW contracted capacity, 3 TOU tiers).
  - Tab 3.1 (Solar PV Standalone): 696.6 kWp TOPCon Array in Seville, Spain (1,548 panels à 450 Wp, 590 kW AC, 180° South).
  - Tab 3.2 (Solar & Consumption Integration): Coupled 15-minute electrical dispatch with autarky, self-consumption,
    peak shaving, and itemized financial invoice reduction.
"""

import datetime
from typing import List, Tuple, Dict, Any, Optional
import pandas as pd
import numpy as np
import streamlit as st

from current_model.models.load_component import SimpleConsumer, TimeWindow
from current_model.models.contract import Contract
from current_model.models.solar import (
    SolarLocation,
    SolarPVConfig,
    SolarSimulationResult,
    SolarFinancialConfig,
    SolarFinancialMetrics
)
from current_model.core.synthetic_engine import aggregate_synthetic_year, aggregate_synthetic_24h
from current_model.core.solar_engine import simulate_solar_pv_generation
from current_model.ui.common.session_utils import find_active_load_data_in_session, find_active_contract_in_session


def get_example1_consumers() -> List[SimpleConsumer]:
    """
    Returns 5 realistic bottom-up consumer assets representing a modern European commercial &
    agro-industrial facility (chillers, automated production lines, air compressors, office/HVAC, EV fleet).
    Schedules are optimized for typical industrial single-shift operations with daytime peak demand.
    """
    return [
        SimpleConsumer(
            name="1. Process Cooling & Refrigeration Chillers",
            power_kw=55.0,
            category="Cooling & Cold Storage",
            active_days=[0, 1, 2, 3, 4, 5, 6],
            seasonal_pattern="summer_heavy",
            time_windows=[
                # Continuous baseline cooling (24/7) with elevated midday process load (11:00 - 15:00)
                TimeWindow(
                    start_time=datetime.time(0, 0),
                    end_time=datetime.time(0, 0),
                    has_peak=True,
                    peak_power_kw=85.0,
                    peak_duration_min=240
                )
            ]
        ),
        SimpleConsumer(
            name="2. Automated Production & Packaging Line",
            power_kw=150.0,
            category="Production Machinery",
            active_days=[0, 1, 2, 3, 4],
            time_windows=[
                # Core production shift 07:30 - 16:00 with peak throughput 10:00 - 14:00
                TimeWindow(
                    start_time=datetime.time(7, 30),
                    end_time=datetime.time(16, 0),
                    has_peak=True,
                    peak_power_kw=190.0,
                    peak_duration_min=240
                )
            ]
        ),
        SimpleConsumer(
            name="3. Compressed Air & Vacuum Stations",
            power_kw=35.0,
            category="Pneumatics & Support",
            active_days=[0, 1, 2, 3, 4],
            time_windows=[
                TimeWindow(start_time=datetime.time(7, 0), end_time=datetime.time(16, 30))
            ]
        ),
        SimpleConsumer(
            name="4. Facility Lighting & Administrative HVAC",
            power_kw=20.0,
            category="Building & Infrastructure",
            active_days=[0, 1, 2, 3, 4, 5],
            time_windows=[
                TimeWindow(start_time=datetime.time(0, 0), end_time=datetime.time(0, 0), has_peak=False),
                TimeWindow(start_time=datetime.time(7, 0), end_time=datetime.time(17, 30), has_peak=False)
            ]
        ),
        SimpleConsumer(
            name="5. Logistics Fleet & Forklift EV Hub",
            power_kw=50.0,
            category="E-Mobility & Logistics",
            active_days=[0, 1, 2, 3, 4],
            time_windows=[
                # Midday smart solar charging window (10:30 - 14:30)
                TimeWindow(start_time=datetime.time(10, 30), end_time=datetime.time(14, 30))
            ]
        )
    ]


def get_example1_contract() -> Contract:
    """
    Returns an electricity supply contract in EUR representing a commercial medium-voltage supply contract:
    - Contracted Capacity: 400 kW (matched to ~395 kW facility peak)
    - 3 Dynamic Time-of-Use rate tiers (Off-Peak / Mid-Peak / High-Peak)
    - Capacity and demand charges, power factor threshold, statutory VAT and electricity tax.
    """
    return Contract(
        name="Example 1 - European Commercial Multi-Tariff",
        currency="EUR",
        base_monthly_fee=95.00,
        contracted_capacity_kw=400.0,
        monthly_capacity_tariff=14.50,         # €/kW/month contracted capacity charge
        demand_capacity_tariff=2.50,           # €/kW/month measured peak demand charge
        max_physical_limit_kw=750.0,
        peak_penalty_rate=28.00,               # €/kW penalty for exceeding 400 kW contracted
        reactive_power_tariff=0.032,
        min_power_factor=0.92,
        reactive_power_allowance_pct=33.0,
        tou_rates=[
            {"name": "Off-Peak (Valle / Night)", "rate": 0.1350, "start_time": "00:00", "end_time": "06:00"},
            {"name": "Mid-Peak (Llano / Daytime)", "rate": 0.2150, "start_time": "06:00", "end_time": "17:00"},
            {"name": "High-Peak (Punta / Evening)", "rate": 0.2950, "start_time": "17:00", "end_time": "22:00"},
            {"name": "Off-Peak (Valle / Night)", "rate": 0.1350, "start_time": "22:00", "end_time": "24:00"}
        ],
        default_energy_rate=0.2150,
        weekend_is_off_peak=True,
        taxes_and_fees=[
            {"name": "Electricity Tax (Stromsteuer)", "type": "per_kwh", "value": 0.0205, "description": "Statutory excise duty"},
            {"name": "VAT / Mehrwertsteuer", "type": "percentage", "value": 19.00, "description": "Value added tax"}
        ]
    )


def get_example1_solar_setup() -> Tuple[SolarPVConfig, SolarLocation, SolarFinancialConfig]:
    """
    Returns the European PV configuration, location, and turn-key investment financials for Example 1:
    - Location: Seville Commercial Park, Spain (37.3891° N, -5.9845° W, elevation 18m)
    - System: 1,548 TOPCon modules à 450 Wp = 696.6 kWp DC
    - Inverter: 590 kW AC (optimal DC/AC oversizing ratio 1.18)
    - Orientation: 30° tilt, 180° azimuth (optimally South-facing in Northern hemisphere)
    - Financials (DRACBV Kosten-/Berechnungs-Dashboard):
        * Modules: 1.00 €/Wp
        * Inverter: 0.07 €/W AC
        * Substructure / Maschinenbau: 0.15 €/Wp
        * Electrical Installation & Commissioning: 0.35 €/Wp
        * Zählerschrank: 2,500 € | Anfahrt: 1,000 €
        * OPEX: 1.0 %/a | Inflation: 3.0 % | Discount rate: 5.0 % | Feed-in: 0.06 €/kWh
    """
    location = SolarLocation(
        name="Seville Commercial Park, Spain",
        latitude=37.3891,
        longitude=-5.9845,
        elevation_m=18.0
    )
    config = SolarPVConfig(
        module_count=1548,
        module_power_wp=450.0,
        dc_capacity_kwp=696.6,
        technology_preset="TOPCon",
        module_technology="TOPCon (450 Wp - N-Type Modern Standard)",
        inverter_capacity_kw=590.0,
        tilt_deg=30.0,
        azimuth_deg=180.0,   # 180° = South in Northern Hemisphere
        temp_coefficient_pct_c=-0.30,
        nmot_c=42.0,
        inverter_efficiency_pct=98.5,
        soiling_loss_pct=2.0,
        shading_loss_pct=1.5,
        dc_wiring_loss_pct=1.5,
        weather_mode="TMY"
    )
    fin_config = SolarFinancialConfig(
        is_enabled=True,
        currency="EUR",
        cost_modules_per_wp=1.00,
        cost_inverter_per_w=0.07,
        cost_substructure_per_wp=0.15,
        cost_installation_per_wp=0.35,
        fixed_switchgear_cost=2500.0,
        fixed_travel_fee=1000.0,
        annual_opex_pct=1.0,
        discount_rate_pct=5.0,
        electricity_price_inflation_pct=3.0,
        feed_in_tariff_per_kwh=0.06,
        analysis_horizon_years=15
    )
    return config, location, fin_config


def load_example1_scenario() -> None:
    """
    One-click loader: Sets up all session state variables across all 4 application components:
      1. Tab 1: 365-day annual synthetic load simulation.
      2. Tab 2: Commercial multi-tariff contract with TOU table and taxes.
      3. Sub-Tab 3.1: 696.6 kWp TOPCon solar simulation in Seville, Spain with turn-key CAPEX breakdown.
      4. Sub-Tab 3.2: Coupled 15-minute electrical load dispatch & avoided invoice savings with 15-year ROI.
    """
    # --------------------------------------------------------------------------
    # 1. TAB 1: Consumption Profile Modeling
    # --------------------------------------------------------------------------
    st.session_state["tab1_active_source"] = "synthetic"
    st.session_state["app_tab1_mode_radio"] = ":material/bolt: Synthetic Load Simulator (24h / 365-Day)"
    st.session_state["app_tab1_synthetic_horizon"] = "Full Year (365 Days / 35,040 Steps)"

    consumers = get_example1_consumers()
    st.session_state["app_tab1_synthetic_consumers"] = consumers
    st.session_state["app_tab1_synthetic_profile_name_input"] = "Example 1 - Commercial Facility"

    # Pre-simulate 365-day annual series (35,040 intervals at 15-min)
    df_year, _, _ = aggregate_synthetic_year(consumers=consumers, year=2025, holidays=[])
    st.session_state["app_tab1_synthetic_active_df"] = df_year
    st.session_state["active_synthetic_df"] = df_year

    # --------------------------------------------------------------------------
    # 2. TAB 2: Electricity Supply Contract & Billing
    # --------------------------------------------------------------------------
    contract = get_example1_contract()
    st.session_state["app_tab2_contract_model"] = contract
    st.session_state["app_tab2_contract"] = contract
    st.session_state["active_contract"] = contract
    st.session_state["app_tab2_tou_rates_df"] = pd.DataFrame(contract.tou_rates)
    st.session_state["app_tab2_taxes_df"] = pd.DataFrame(contract.taxes_and_fees)

    # Clear stale editor widget keys
    for k in ["app_tab2_tou_editor", "app_tab2_taxes_editor", "app_tab2_contract_form"]:
        if k in st.session_state:
            del st.session_state[k]

    # --------------------------------------------------------------------------
    # 3. TAB 3.1: Standalone Solar PV Generation (Seville, Spain)
    # --------------------------------------------------------------------------
    from current_model.core.solar_financial_engine import compute_solar_financial_metrics

    solar_cfg, solar_loc, solar_fin = get_example1_solar_setup()

    st.session_state["app_tab3_loc_lat"] = solar_loc.latitude
    st.session_state["app_tab3_loc_lon"] = solar_loc.longitude
    st.session_state["app_tab3_loc_name"] = solar_loc.name
    st.session_state["app_tab3_loc_elev"] = solar_loc.elevation_m
    st.session_state["app_tab3_config"] = solar_cfg
    st.session_state["app_tab3_fin_config"] = solar_fin
    st.session_state["solar_financial_config"] = solar_fin

    # Pre-simulate Tab 3.1 standalone generation
    sim_res_standalone: SolarSimulationResult = simulate_solar_pv_generation(
        config=solar_cfg,
        location=solar_loc
    )
    # Pre-calculate pure solar financial metrics
    fin_metrics_standalone = compute_solar_financial_metrics(
        config=solar_cfg,
        fin_config=solar_fin,
        annual_generation_kwh=sim_res_standalone.kpis.annual_energy_kwh,
        multi_year_yields=sim_res_standalone.multi_year_yields
    )
    sim_res_standalone.financial_config = solar_fin
    sim_res_standalone.financial_metrics = fin_metrics_standalone

    st.session_state["app_tab3_sim_result"] = sim_res_standalone
    st.session_state["solar_kw_15min"] = sim_res_standalone.df_timeseries["P_AC_kW"]
    st.session_state["solar_kpis"] = sim_res_standalone.kpis
    st.session_state["solar_config"] = solar_cfg
    st.session_state["solar_financial_metrics"] = fin_metrics_standalone

    # Clear stale Tab 3.1 input & location widget keys
    for k in [
        "app_tab3_form_mod_count",
        "app_tab3_form_tech_choice",
        "app_tab3_form_inv_kw",
        "app_tab3_form_tilt",
        "app_tab3_form_azimuth",
        "app_tab3_form_weather_mode_select",
        "app_tab3_form_hist_year_select",
        "app_tab3_form_enable_financials",
        "app_tab3_form_fin_mod_wp",
        "app_tab3_form_fin_inv_w",
        "app_tab3_form_fin_sub_wp",
        "app_tab3_form_fin_inst_wp",
        "app_tab3_form_fin_switch",
        "app_tab3_form_fin_travel",
        "app_tab3_loc_man_lat",
        "app_tab3_loc_man_lon",
        "app_tab3_loc_search_input",
        "app_tab3_loc_preset_select"
    ]:
        if k in st.session_state:
            del st.session_state[k]

    # --------------------------------------------------------------------------
    # 4. TAB 3.2: Solar & Consumption Integration (Coupled Dispatch)
    # --------------------------------------------------------------------------
    st.session_state["app_tab3_int_config"] = solar_cfg

    # Run coupled dispatch against the 365-day annual load profile
    sim_res_coupled: SolarSimulationResult = simulate_solar_pv_generation(
        config=solar_cfg,
        location=solar_loc,
        load_df=df_year
    )
    st.session_state["app_tab3_int_sim_result"] = sim_res_coupled
    st.session_state["solar_dispatch_result"] = sim_res_coupled

    # Clear stale Tab 3.2 input widget keys
    for k in [
        "app_tab3_int_mod_count_inp",
        "app_tab3_int_mod_wp_inp",
        "app_tab3_int_inv_kw_inp"
    ]:
        if k in st.session_state:
            del st.session_state[k]

    # --------------------------------------------------------------------------
    # 5. Global Scenario Flag
    # --------------------------------------------------------------------------
    st.session_state["example1_active"] = True


def clear_demo_scenario() -> None:
    """
    Clears the active demo scenario and resets session state back to clean default.
    """
    keys_to_clear = [
        "example1_active",
        "app_tab1_synthetic_consumers",
        "app_tab1_synthetic_active_df",
        "active_synthetic_df",
        "active_csv_df",
        "active_csv_filename",
        "app_tab2_contract_model",
        "app_tab2_contract",
        "active_contract",
        "app_tab2_tou_rates_df",
        "app_tab2_taxes_df",
        "app_tab3_config",
        "app_tab3_sim_result",
        "solar_kw_15min",
        "solar_kpis",
        "solar_config",
        "app_tab3_fin_config",
        "solar_financial_config",
        "solar_financial_metrics",
        "app_tab3_int_config",
        "app_tab3_int_sim_result",
        "solar_dispatch_result"
    ]
    for k in keys_to_clear:
        if k in st.session_state:
            del st.session_state[k]

    st.session_state["example1_active"] = False


def get_active_model_summary() -> Dict[str, Any]:
    """
    Inspects current session state and returns a summary dict of active configurations
    for display in the sidebar model inspector.
    """
    is_example1 = bool(st.session_state.get("example1_active", False))

    # Tab 1: Load data
    df_load, load_desc, p_col = find_active_load_data_in_session()
    has_load = df_load is not None and not df_load.empty

    # Tab 2: Contract
    contract = find_active_contract_in_session()
    has_contract = contract is not None

    # Tab 3: Solar PV
    pv_res = st.session_state.get("app_tab3_sim_result")
    pv_cfg = st.session_state.get("app_tab3_config")
    has_solar = pv_cfg is not None and getattr(pv_cfg, "module_count", 0) > 0
    fin_m = getattr(pv_res, "financial_metrics", None) or st.session_state.get("solar_financial_metrics")
    has_fin = fin_m is not None and getattr(fin_m, "is_configured", False) and getattr(fin_m, "total_capex", 0) > 0

    return {
        "is_example1": is_example1,
        "has_load": has_load,
        "load_desc": load_desc if has_load else "None (Unconfigured)",
        "has_contract": has_contract,
        "contract_name": getattr(contract, "name", "None") if has_contract else "None (Unconfigured)",
        "contract_currency": getattr(contract, "currency", "EUR") if has_contract else "",
        "contract_kw": getattr(contract, "contracted_capacity_kw", 0.0) if has_contract else 0.0,
        "has_solar": has_solar,
        "solar_kwp": getattr(pv_cfg, "dc_capacity_kwp", 0.0) if has_solar else 0.0,
        "solar_location": st.session_state.get("app_tab3_loc_name", "Seville, Spain") if has_solar else "None",
        "has_financials": has_fin,
        "solar_capex": getattr(fin_m, "total_capex", 0.0) if has_fin else 0.0,
        "has_integration": "app_tab3_int_sim_result" in st.session_state
    }
