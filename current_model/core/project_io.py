"""
========================================================================================
Project & Scenario I/O and Persistence Engine (current_model/core/project_io.py)
========================================================================================

Description:
------------
Provides complete persistence, serialization, and deserialization routines for:
  - Full Project Snapshots (.dracproj / JSON): Entire workspace with Base Scenario,
    all 1-to-N Sub-Scenarios, component configurations, and cached dispatch results.
  - Modular Asset Files (.drac / JSON): Individual contracts or consumer load profiles.
  - File Validation: Inspects JSON schemas and returns rich validation metrics.
  - Session State Ingestion: Restores models and triggers cross-tab calculation pipelines.
"""

import json
import io
import datetime
from typing import Dict, Any, Tuple, Optional, List
import pandas as pd
import streamlit as st

from current_model.models.scenario import BaseScenario, SubScenario, ProjectContainer
from current_model.models.contract import Contract
from current_model.models.load_component import SimpleConsumer
from current_model.models.solar import SolarLocation, SolarPVConfig, SolarFinancialConfig, SolarSimulationResult
from current_model.models.bess import BESSConfig
from current_model.models.generator import GeneratorConfig
from current_model.core.synthetic_engine import aggregate_synthetic_year, aggregate_synthetic_24h
from current_model.core.solar_engine import simulate_solar_pv_generation
from current_model.core.solar_financial_engine import compute_solar_financial_metrics
from current_model.ui.common.session_utils import find_active_load_data_in_session, find_active_contract_in_session


def export_project_from_session(
    project_name: Optional[str] = None,
    description: Optional[str] = None,
    author: Optional[str] = None
) -> ProjectContainer:
    """
    Constructs a complete ProjectContainer snapshot from the active Streamlit session state.
    Captures Tab 1 load consumers/data, Tab 2 contracts, Tab 3 solar configs, and any configured sub-scenarios.
    """
    # 1. Inspect Base Scenario Load
    load_source_type = st.session_state.get("tab1_active_source", "synthetic")
    synthetic_horizon = st.session_state.get("app_tab1_synthetic_horizon", "Full Year (365 Days / 35,040 Steps)")
    load_profile_name = st.session_state.get("app_tab1_synthetic_profile_name_input", "Baseline Facility Load")
    
    consumers: List[SimpleConsumer] = []
    for k in ["app_tab1_synthetic_consumers", "synthetic_consumers"]:
        if k in st.session_state and isinstance(st.session_state[k], list):
            consumers = st.session_state[k]
            break

    # Holidays table
    holidays = []
    for k in ["app_tab1_synthetic_holidays_df", "synthetic_holidays_df"]:
        if k in st.session_state and isinstance(st.session_state[k], pd.DataFrame):
            df_h = st.session_state[k]
            if not df_h.empty:
                holidays = df_h.to_dict(orient="records")

    # CSV real meter records if active
    csv_filename = st.session_state.get("active_csv_filename")
    csv_power_col = None
    csv_records = None
    if "active_csv_df" in st.session_state and isinstance(st.session_state["active_csv_df"], pd.DataFrame):
        df_csv = st.session_state["active_csv_df"]
        if not df_csv.empty:
            # Sample or take key columns to keep file size reasonable
            cols_to_keep = [c for c in df_csv.columns if c in ["timestamp", "Total_Demand_kW", "Power_kW", "kW", "Active_Power_kW"]]
            if cols_to_keep:
                csv_power_col = cols_to_keep[-1]
                csv_records = df_csv[cols_to_keep].to_dict(orient="records")

    # 2. Inspect Base Contract
    contract = find_active_contract_in_session()
    currency = contract.currency if contract else "EUR"

    # 3. Inspect Location
    lat = st.session_state.get("app_tab3_loc_lat", -33.5133)
    lon = st.session_state.get("app_tab3_loc_lon", -69.2561)
    loc_name = st.session_state.get("app_tab3_loc_name", "Tunuyán, Mendoza")
    loc_elev = st.session_state.get("app_tab3_loc_elev", 1100.0)
    location = SolarLocation(name=loc_name, latitude=lat, longitude=lon, elevation_m=loc_elev)

    # 4. Build BaseScenario
    base_scenario = BaseScenario(
        name="Status Quo (Base Scenario)",
        description="Baseline facility demand and utility electricity contract without intervention.",
        load_source_type=load_source_type,
        load_profile_name=load_profile_name,
        synthetic_horizon=synthetic_horizon,
        consumers=consumers,
        holidays=holidays,
        csv_filename=csv_filename,
        csv_power_column=csv_power_col,
        csv_data_records=csv_records,
        base_contract=contract,
        location=location
    )

    # 5. Check if a ProjectContainer already exists in session_state, or initialize one
    project: Optional[ProjectContainer] = st.session_state.get("project_container")
    if project is None:
        project = ProjectContainer(
            project_name=project_name or "Energy Transition Project",
            description=description or "",
            author=author or "DRACBV Consultant",
            currency=currency,
            base_scenario=base_scenario
        )
    else:
        project.base_scenario = base_scenario
        if project_name:
            project.project_name = project_name
        if description:
            project.description = description
        if author:
            project.author = author
        project.currency = currency

    # 6. Ensure active Tab 3 Solar config is represented in at least one Sub-Scenario if active
    solar_cfg = st.session_state.get("app_tab3_config") or st.session_state.get("solar_config")
    solar_fin = st.session_state.get("app_tab3_fin_config") or st.session_state.get("solar_financial_config")

    if not project.sub_scenarios and solar_cfg is not None and getattr(solar_cfg, "module_count", 0) > 0:
        sub_default = SubScenario(
            id="sub_solar_pv",
            name="Sub-Scenario 1: Solar PV",
            color_code="#2563EB",
            include_solar=True,
            solar_config=solar_cfg,
            solar_financial=solar_fin
        )
        project.sub_scenarios.append(sub_default)

    st.session_state["project_container"] = project
    return project


def export_project_json(project: Optional[ProjectContainer] = None, indent: int = 2) -> str:
    """Serializes the project to formatted JSON string."""
    if project is None:
        project = export_project_from_session()
    return project.to_json(indent=indent)


def validate_project_file(raw_content: Any) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Validates a loaded file (JSON string or dict) and returns:
      (is_valid: bool, status_message: str, summary_metadata: Dict[str, Any])
    """
    try:
        if isinstance(raw_content, bytes):
            raw_content = raw_content.decode("utf-8")
        if isinstance(raw_content, str):
            data = json.loads(raw_content)
        elif isinstance(raw_content, dict):
            data = raw_content
        else:
            return False, "Invalid data type. Expected JSON string or dictionary.", {}

        fmt = data.get("format", "")
        if fmt == "drac_simulation_project":
            proj_name = data.get("project_name", "Unnamed Project")
            base_data = data.get("base_scenario", {})
            subs_data = data.get("sub_scenarios", [])
            currency = data.get("currency", "EUR")

            summary = {
                "format": "drac_simulation_project",
                "project_name": proj_name,
                "currency": currency,
                "author": data.get("author", "DRACBV"),
                "created_at": data.get("created_at", ""),
                "sub_scenario_count": len(subs_data),
                "load_type": base_data.get("load_source_type", "synthetic"),
                "consumer_count": len(base_data.get("consumers", [])),
                "has_contract": base_data.get("base_contract") is not None,
                "contract_name": (base_data.get("base_contract") or {}).get("name", "None"),
                "location_name": (base_data.get("location") or {}).get("name", "Custom Location")
            }
            return True, f"Valid DRACBV Project Snapshot: '{proj_name}' ({len(subs_data)} Sub-Scenarios)", summary

        elif fmt == "drac_contract":
            summary = {
                "format": "drac_contract",
                "contract_name": data.get("name", "Unnamed Contract"),
                "currency": data.get("currency", "EUR"),
                "contracted_capacity_kw": data.get("contracted_capacity_kw", 0.0)
            }
            return True, f"Valid Contract Asset: '{data.get('name', 'Contract')}'", summary

        elif fmt == "drac_load_profile":
            summary = {
                "format": "drac_load_profile",
                "profile_name": data.get("profile_name", "Load Profile"),
                "consumer_count": len(data.get("consumers", []))
            }
            return True, f"Valid Load Profile Asset: '{data.get('profile_name', 'Profile')}'", summary

        else:
            return False, f"Unrecognized JSON format schema: '{fmt}'.", {}

    except Exception as e:
        return False, f"JSON parsing error: {str(e)}", {}


def load_project_into_session(project: ProjectContainer, auto_execute: bool = True) -> None:
    """
    Restores the complete project state into Streamlit session state and
    automatically recalculates simulation pipelines so all tabs are 100% active.
    """
    st.session_state["project_container"] = project
    st.session_state["active_project_name"] = project.project_name

    base = project.base_scenario

    # 1. Restore Tab 1: Load Profile & Consumers
    st.session_state["tab1_active_source"] = base.load_source_type
    st.session_state["app_tab1_synthetic_horizon"] = base.synthetic_horizon
    st.session_state["app_tab1_synthetic_profile_name_input"] = base.load_profile_name

    if base.consumers:
        st.session_state["app_tab1_synthetic_consumers"] = base.consumers
        st.session_state["synthetic_consumers"] = base.consumers

        # Run annual synthetic simulation to populate 35,040 steps dataframe
        if "365" in base.synthetic_horizon or "Year" in base.synthetic_horizon:
            df_year, _, _ = aggregate_synthetic_year(consumers=base.consumers, year=2025)
            st.session_state["app_tab1_synthetic_active_df"] = df_year
            st.session_state["active_synthetic_df"] = df_year
        else:
            df_day, _, _ = aggregate_synthetic_24h(base.consumers)
            st.session_state["app_tab1_synthetic_active_df"] = df_day
            st.session_state["active_synthetic_df"] = df_day

    if base.holidays:
        st.session_state["app_tab1_synthetic_holidays_df"] = pd.DataFrame(base.holidays)

    if base.csv_data_records:
        df_csv = pd.DataFrame(base.csv_data_records)
        st.session_state["active_csv_df"] = df_csv
        st.session_state["active_csv_filename"] = base.csv_filename or "Restored_Meter_Data.csv"

    # 2. Restore Tab 2: Base Contract
    if base.base_contract:
        st.session_state["app_tab2_contract"] = base.base_contract
        st.session_state["app_tab2_contract_model"] = base.base_contract
        st.session_state["active_contract"] = base.base_contract
        st.session_state["app_tab2_tou_rates_df"] = pd.DataFrame(base.base_contract.tou_rates)
        st.session_state["app_tab2_taxes_df"] = pd.DataFrame(base.base_contract.taxes_and_fees)

        for k in ["app_tab2_tou_editor", "app_tab2_taxes_editor", "app_tab2_contract_form"]:
            if k in st.session_state:
                del st.session_state[k]

    # 3. Restore Location
    if base.location:
        st.session_state["app_tab3_loc_lat"] = base.location.latitude
        st.session_state["app_tab3_loc_lon"] = base.location.longitude
        st.session_state["app_tab3_loc_name"] = base.location.name
        st.session_state["app_tab3_loc_elev"] = base.location.elevation_m

    # 4. Restore Active Sub-Scenario Configurations in Tabs
    sync_active_scenario_into_session(project, auto_execute=auto_execute)

    st.session_state["example1_active"] = False


def sync_active_scenario_into_session(project: ProjectContainer, auto_execute: bool = True) -> None:
    """
    Synchronizes the active scenario (Status Quo vs SubScenario) into Streamlit session state.
    Clears input widget caches so form values strictly reflect the active scenario branch.
    """
    st.session_state["project_container"] = project
    active_sub = project.get_active_scenario()
    base = project.base_scenario

    # Comprehensive list of Tab 3 form widget keys to purge on scenario switch
    form_keys_to_clear = [
        "app_tab3_form_mod_count",
        "app_tab3_form_mod_wp",
        "app_tab3_form_tech_choice",
        "app_tab3_form_inv_kw",
        "app_tab3_form_inv_eff",
        "app_tab3_form_tilt",
        "app_tab3_form_azimuth",
        "app_tab3_form_weather_mode_select",
        "app_tab3_form_hist_year_select",
        "app_tab3_form_enable_financials",
        "app_tab3_form_fin_curr",
        "app_tab3_form_fin_mod_wp",
        "app_tab3_form_fin_inv_w",
        "app_tab3_form_fin_sub_wp",
        "app_tab3_form_fin_inst_wp",
        "app_tab3_form_fin_switch",
        "app_tab3_form_fin_travel",
        "app_tab3_form_fin_opex",
        "app_tab3_form_fin_disc",
        "app_tab3_form_fin_infl",
        "app_tab3_form_fin_feed",
        "tab3_form_mod_count",
        "tab3_form_tech_choice",
        "tab3_form_inv_kw",
        "tab3_form_tilt",
        "tab3_form_azimuth",
        "solar_cfg_mod_count",
        "solar_cfg_mod_wp",
        "solar_cfg_tech_choice"
    ]
    for k in form_keys_to_clear:
        if k in st.session_state:
            del st.session_state[k]

    if active_sub is None:
        # Status Quo is active: Pure baseline without solar PV simulation state
        for k in [
            "app_tab3_sim_result",
            "app_tab3_int_sim_result",
            "solar_kw_15min",
            "solar_kpis",
            "solar_dispatch_result",
            "solar_financial_metrics",
            "app_tab3_config",
            "solar_config",
            "app_tab3_fin_config",
            "solar_financial_config"
        ]:
            if k in st.session_state:
                del st.session_state[k]
    else:
        # SubScenario is active: Populate specific solar and financial configs
        if active_sub.solar_config:
            st.session_state["app_tab3_config"] = active_sub.solar_config
            st.session_state["solar_config"] = active_sub.solar_config
        else:
            if "app_tab3_config" in st.session_state:
                del st.session_state["app_tab3_config"]
            if "solar_config" in st.session_state:
                del st.session_state["solar_config"]

        if active_sub.solar_financial:
            st.session_state["app_tab3_fin_config"] = active_sub.solar_financial
            st.session_state["solar_financial_config"] = active_sub.solar_financial
        else:
            if "app_tab3_fin_config" in st.session_state:
                del st.session_state["app_tab3_fin_config"]
            if "solar_financial_config" in st.session_state:
                del st.session_state["solar_financial_config"]

        # Run automated physical and financial simulation for active sub-scenario
        if auto_execute and active_sub.include_solar and active_sub.solar_config and base.location:
            sim_res: SolarSimulationResult = simulate_solar_pv_generation(
                config=active_sub.solar_config,
                location=base.location
            )
            if active_sub.solar_financial and active_sub.solar_financial.is_enabled:
                fin_m = compute_solar_financial_metrics(
                    config=active_sub.solar_config,
                    fin_config=active_sub.solar_financial,
                    annual_generation_kwh=sim_res.kpis.annual_energy_kwh,
                    multi_year_yields=sim_res.multi_year_yields
                )
                sim_res.financial_metrics = fin_m
                sim_res.financial_config = active_sub.solar_financial
                st.session_state["solar_financial_metrics"] = fin_m

            st.session_state["app_tab3_sim_result"] = sim_res
            st.session_state["solar_kw_15min"] = sim_res.df_timeseries["P_AC_kW"]
            st.session_state["solar_kpis"] = sim_res.kpis

            # Coupled dispatch with baseline load
            df_load_active = st.session_state.get("app_tab1_synthetic_active_df")
            if df_load_active is None or not isinstance(df_load_active, pd.DataFrame):
                df_load_active = st.session_state.get("active_csv_df")

            if df_load_active is not None and isinstance(df_load_active, pd.DataFrame) and not df_load_active.empty:
                sim_res_coupled = simulate_solar_pv_generation(
                    config=active_sub.solar_config,
                    location=base.location,
                    load_df=df_load_active
                )
                st.session_state["app_tab3_int_sim_result"] = sim_res_coupled
                st.session_state["solar_dispatch_result"] = sim_res_coupled

