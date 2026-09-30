"""
========================================================================================
Sidebar Project & Scenario Controller (current_model/ui/common/sidebar_scenario_view.py)
========================================================================================

Description:
------------
Provides the centralized Sidebar Control Panel:
  - Sub-Scenario Manager: Switch between Status Quo and 1-to-N branchable Sub-Scenarios,
    create new sub-scenarios, clone for sensitivity tests, and delete obsolete instances.
  - Project Persistence Bar: Export/download complete `.dracproj` project snapshots,
    upload & validate existing project files with summary preview, and 1-click benchmark loaders.
  - Active Model & Technology Inspector using Streamlit Material symbols.
"""

import streamlit as st
import datetime
import re
from typing import Dict, Any, Optional, List

from current_model.models.scenario import BaseScenario, SubScenario, ProjectContainer
from current_model.core.project_io import (
    export_project_from_session,
    export_project_json,
    validate_project_file,
    load_project_into_session
)
from current_model.core.demo_scenario import (
    load_example1_scenario,
    clear_demo_scenario,
    get_active_model_summary
)


def render_sidebar_scenario_controller() -> None:
    """
    Renders the unified multi-scenario controller and project persistence manager in the sidebar.
    """
    st.markdown("### :material/tune: Project & Scenario Control")
    st.caption("Manage multi-scenario energy transitions, switch solution paths, and persist project snapshots.")

    # 1. Initialize or Retrieve Project Container
    project: ProjectContainer = export_project_from_session()

    # --------------------------------------------------------------------------
    # 2. Sub-Scenario Switcher & Selector
    # --------------------------------------------------------------------------
    st.markdown("#### :material/alt_route: Active Scenario Branch")
    
    scenario_ids = ["base"] + [s.id for s in project.sub_scenarios]
    scenario_label_map = {"base": "Status Quo (Base Benchmark)"}
    for s in project.sub_scenarios:
        scenario_label_map[s.id] = f"{s.name} ({s.technology_mix_label})"

    # Determine current index based on stable scenario IDs
    current_active_id = project.active_sub_scenario_id if (project.active_sub_scenario_id and project.active_sub_scenario_id in scenario_ids) else "base"
    try:
        current_idx = scenario_ids.index(current_active_id)
    except ValueError:
        current_idx = 0

    sb_key = "sidebar_target_scenario_select"
    # Ensure selectbox key in session state is strictly synchronized with active scenario id
    if sb_key not in st.session_state or st.session_state[sb_key] not in scenario_ids or st.session_state[sb_key] != current_active_id:
        st.session_state[sb_key] = current_active_id

    def _on_sidebar_scenario_change() -> None:
        new_target = st.session_state.get(sb_key)
        proj = export_project_from_session()
        proj.active_sub_scenario_id = None if new_target == "base" else new_target
        st.session_state["project_container"] = proj
        st.session_state["app_scenarios_target_scenario_select"] = new_target or "base"
        from current_model.core.project_io import sync_active_scenario_into_session
        sync_active_scenario_into_session(proj, auto_execute=False)

    st.selectbox(
        "Active Simulation Target:",
        options=scenario_ids,
        format_func=lambda s_id: scenario_label_map.get(s_id, s_id),
        key=sb_key,
        on_change=_on_sidebar_scenario_change,
        help="Select which scenario branch to inspect, configure, or optimize in the workspace tabs."
    )

    # --------------------------------------------------------------------------
    # 3. Scenario Management Actions (New, Duplicate, Delete)
    # --------------------------------------------------------------------------
    btn_col1, btn_col2 = st.columns(2)
    with btn_col1:
        with st.popover("New Branch", icon=":material/add:", use_container_width=True):
            st.markdown("##### :material/add_circle: Create Sub-Scenario")
            new_name = st.text_input(
                "Sub-Scenario Name:",
                value=f"Option {len(project.sub_scenarios) + 1}: Solar & Storage",
                key="sidebar_new_scen_name"
            )
            color_choice = st.selectbox(
                "Chart Color:",
                options=["#2563EB (Blue)", "#059669 (Green)", "#D97706 (Amber)", "#DC2626 (Red)", "#7C3AED (Purple)", "#0891B2 (Cyan)"],
                index=len(project.sub_scenarios) % 6,
                key="sidebar_new_scen_color"
            )
            clean_color = color_choice.split(" ")[0]

            st.markdown("**Select Modules to Include:**")
            s_sol = st.checkbox(":material/solar_power: Solar PV Generation", value=True, key="sidebar_new_sol")
            s_bess = st.checkbox(":material/battery_charging_full: Battery Storage (BESS)", value=False, key="sidebar_new_bess")
            s_gen = st.checkbox(":material/local_gas_station: Peaking / Backup Generator (Genset)", value=False, key="sidebar_new_gen")
            s_tar = st.checkbox(":material/swap_horiz: Tariff Switch / Alternative Contract", value=False, key="sidebar_new_tar")

            if st.button("Instantiate Branch", icon=":material/check:", type="primary", use_container_width=True):
                new_sub = SubScenario(
                    name=new_name.strip() or f"Sub-Scenario {len(project.sub_scenarios) + 1}",
                    color_code=clean_color,
                    include_solar=s_sol,
                    include_bess=s_bess,
                    include_generator=s_gen,
                    use_custom_grid_tariff=s_tar
                )
                project.add_sub_scenario(new_sub)
                project.active_sub_scenario_id = new_sub.id
                st.session_state["project_container"] = project
                from current_model.core.project_io import sync_active_scenario_into_session
                sync_active_scenario_into_session(project, auto_execute=False)
                st.rerun()

    with btn_col2:
        if project.active_sub_scenario_id and project.active_sub_scenario_id != "base":
            with st.popover("Branch Actions", icon=":material/more_vert:", use_container_width=True):
                active_sub = project.get_sub_scenario(project.active_sub_scenario_id)
                if active_sub:
                    st.caption(f"Managing: **{active_sub.name}**")
                    if st.button("Duplicate Branch", icon=":material/content_copy:", use_container_width=True):
                        cloned = project.duplicate_sub_scenario(active_sub.id, f"{active_sub.name} (Clone)")
                        project.active_sub_scenario_id = cloned.id
                        st.session_state["project_container"] = project
                        from current_model.core.project_io import sync_active_scenario_into_session
                        sync_active_scenario_into_session(project, auto_execute=False)
                        st.rerun()
                    if st.button("Delete Branch", icon=":material/delete:", type="secondary", use_container_width=True):
                        project.delete_sub_scenario(active_sub.id)
                        project.active_sub_scenario_id = project.sub_scenarios[0].id if project.sub_scenarios else None
                        st.session_state["project_container"] = project
                        from current_model.core.project_io import sync_active_scenario_into_session
                        sync_active_scenario_into_session(project, auto_execute=False)
                        st.rerun()
        else:
            st.button("Base Anchor", icon=":material/lock:", disabled=True, use_container_width=True, help="Status Quo is the immutable anchor.")

    st.divider()

    # --------------------------------------------------------------------------
    # 4. Project Persistence Bar (.dracproj Save & Load)
    # --------------------------------------------------------------------------
    st.markdown("#### :material/save: Project Persistence & Transfer")

    with st.expander("Save & Export Project (.dracproj)", icon=":material/download:", expanded=False):
        proj_name_input = st.text_input(
            "Project Title:",
            value=project.project_name,
            key="sidebar_export_proj_name"
        )
        if proj_name_input != project.project_name:
            project.project_name = proj_name_input
            st.session_state["project_container"] = project

        proj_json_str = export_project_json(project)
        safe_fname = re.sub(r'[\\/*?:"<>| ]', "_", project.project_name).strip() or "DRACBV_Project"
        if not safe_fname.lower().endswith(".dracproj"):
            safe_fname += ".dracproj"

        st.download_button(
            label="Download Complete Project (.dracproj)",
            data=proj_json_str,
            file_name=safe_fname,
            mime="application/json",
            icon=":material/download:",
            use_container_width=True,
            type="primary",
            help="Exports all Base Scenario data, load profiles, contracts, and all Sub-Scenarios into a unified JSON bundle."
        )

    with st.expander("Load Project or Asset (.dracproj / .drac)", icon=":material/upload_file:", expanded=False):
        uploaded_file = st.file_uploader(
            "Upload Simulation Project (.dracproj, .json, .drac):",
            type=["dracproj", "json", "drac"],
            key="sidebar_proj_uploader"
        )
        if uploaded_file is not None:
            raw_bytes = uploaded_file.getvalue()
            is_valid, msg, meta = validate_project_file(raw_bytes)

            if is_valid:
                st.success(f":material/check_circle: {msg}")
                if meta.get("format") == "drac_simulation_project":
                    st.markdown(
                        f"""
                        * **Project:** {meta.get('project_name')}
                        * **Sub-Scenarios:** {meta.get('sub_scenario_count')} branches
                        * **Site:** {meta.get('location_name')}
                        * **Contract:** {meta.get('contract_name')} ({meta.get('currency')})
                        """
                    )
                    if st.button("Apply Project & Restore Workspace", icon=":material/refresh:", type="primary", use_container_width=True, key="sidebar_apply_proj_btn"):
                        import json
                        loaded_container = ProjectContainer.from_json(raw_bytes.decode("utf-8"))
                        load_project_into_session(loaded_container, auto_execute=True)
                        st.rerun()
                elif meta.get("format") == "drac_contract":
                    st.info(f"Contract Asset Detected: **{meta.get('contract_name')}** ({meta.get('contracted_capacity_kw')} kW)")
                    if st.button("Import as Base Contract", icon=":material/description:", use_container_width=True, key="sidebar_import_c_btn"):
                        from current_model.models.contract import Contract
                        c_loaded = Contract.from_json(raw_bytes.decode("utf-8"))
                        st.session_state["app_tab2_contract"] = c_loaded
                        st.session_state["active_contract"] = c_loaded
                        st.rerun()
                elif meta.get("format") == "drac_load_profile":
                    st.info(f"Load Profile Asset Detected: **{meta.get('profile_name')}** ({meta.get('consumer_count')} consumers)")
                    if st.button("Import as Base Load Profile", icon=":material/analytics:", use_container_width=True, key="sidebar_import_l_btn"):
                        from current_model.models.load_component import consumers_from_drac
                        c_list = consumers_from_drac(raw_bytes.decode("utf-8"))
                        st.session_state["app_tab1_synthetic_consumers"] = c_list
                        st.rerun()
            else:
                st.error(f":material/error: {msg}")

    st.divider()

    # --------------------------------------------------------------------------
    # 5. Benchmark Scenarios & Quick Reset / Reload
    # --------------------------------------------------------------------------
    st.markdown("#### :material/science: Benchmark Templates & Quick Actions")
    col_bench1, col_bench2, col_bench3 = st.columns(3)
    with col_bench1:
        if st.button("Example 1", icon=":material/rocket_launch:", use_container_width=True, help="Loads European Commercial Benchmark (Seville, Spain - EUR)."):
            load_example1_scenario()
            st.rerun()
    with col_bench2:
        if st.button("Reload", icon=":material/refresh:", use_container_width=True, help="Reloads and reruns the entire application workspace."):
            st.rerun()
    with col_bench3:
        if st.button("Reset All", icon=":material/restart_alt:", use_container_width=True, help="Clears session state and resets to clean default."):
            clear_demo_scenario()
            if "project_container" in st.session_state:
                del st.session_state["project_container"]
            st.rerun()

    st.divider()

    # --------------------------------------------------------------------------
    # 6. Current Model Summary
    # --------------------------------------------------------------------------
    st.markdown("#### :material/info: Model Summary")
    summary = get_active_model_summary()
    c_label = f"{summary['contract_name']} ({summary['contract_currency']})" if summary['has_contract'] else "Unconfigured"
    s_label = f"{summary['solar_kwp']:.1f} kWp ({summary['solar_location']})" if summary['has_solar'] else "Unconfigured"

    st.markdown(
        f"""
        * :material/analytics: **Load:** {summary['load_desc']}
        * :material/description: **Contract:** {c_label}
        * :material/solar_power: **Solar PV:** {s_label}
        * :material/alt_route: **Branches:** {len(project.sub_scenarios)} Sub-Scenarios
        """
    )
