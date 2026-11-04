"""
========================================================================================
Scenario 2: Standalone Contract Switch & Twin-Contract Benchmark Sandbox
ui_sandbox/NewContract_sandbox/app.py
========================================================================================

Standalone Execution:
    python -m streamlit run "ui_sandbox/NewContract_sandbox/app.py"

3-Tab Twin-Contract Architecture:
  - Top Header Banner: Active Consumption Baseline (Source, 35,040 steps, Annual kWh, Peak kW) + Preset Quick-Loader
  - Tab 1: Contract 1 — Current Situation (Baseline Contract with all 5 sub-tabs)
  - Tab 2: Contract 2 — Alternative Contract (Contract Switch Setup, auto-cloned from Contract 1 with all 5 sub-tabs)
  - Tab 3: Cost Comparison & Delta Analytics (Side-by-side 4-pillar breakdown, delta cards, monthly & 15Y charts, audit table)
========================================================================================
"""

import os
import sys
import copy
from typing import Dict, List, Any, Tuple, Optional
import numpy as np
import pandas as pd
import streamlit as st

# Ensure root and parent directories are on sys.path for standalone execution
_CURRENT_DIR = os.path.abspath(os.path.dirname(__file__))
_UI_SANDBOX_DIR = os.path.abspath(os.path.join(_CURRENT_DIR, ".."))
_PROJECT_ROOT = os.path.abspath(os.path.join(_UI_SANDBOX_DIR, ".."))
_WORKSPACE_DIR = os.path.abspath(os.path.join(_PROJECT_ROOT, ".."))
for _p in (_WORKSPACE_DIR, _PROJECT_ROOT, _UI_SANDBOX_DIR, _CURRENT_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from ui_sandbox.common import (
        ScenarioEvaluationOutput,
        render_standalone_baseline_control_bar,
        compute_15y_tco_npv,
        render_scenario_evaluation_output_card,
    )
    from ui_sandbox.Currentsituation_sandbox.engine.config_and_models import (
        LoadSeries2025,
        StatusQuoConfig2025,
        StatusQuoAnnualResult,
        TariffStage,
        MeteringTariff,
        LevyConfig,
    )
    from ui_sandbox.Currentsituation_sandbox.engine.consumption_pipeline import (
        extract_monthly_consumption_records,
    )
    from ui_sandbox.Currentsituation_sandbox.engine.dso_accounting import (
        calculate_dso_accounting_2025,
    )
    from ui_sandbox.Currentsituation_sandbox.engine.commercial_accounting import (
        calculate_commercial_accounting_2025,
    )
    from ui_sandbox.Currentsituation_sandbox.engine.status_quo_master import (
        calculate_status_quo_master_2025,
    )
    from ui_sandbox.Currentsituation_sandbox.contract.assumptions_banner import (
        build_assumptions_register_dict,
        render_assumptions_banner,
    )
    from ui_sandbox.Currentsituation_sandbox.contract.tab_dso import render_dso_tab
    from ui_sandbox.Currentsituation_sandbox.contract.tab_supplier import render_supplier_tab
    from ui_sandbox.Currentsituation_sandbox.contract.tab_metering import render_metering_tab
    from ui_sandbox.Currentsituation_sandbox.contract.tab_overview import render_overview_tab
    from ui_sandbox.Currentsituation_sandbox.contract.tab_invoice_experimental import (
        render_invoice_experimental_tab,
    )
    from ui_sandbox.Currentsituation_sandbox.contract.view import (
        _render_master_bill_equation_bar_html,
        _apply_reference_preset,
    )
    from ui_sandbox.NewContract_sandbox.contract_comparison_engine import (
        compute_contract_switch_kpis,
        create_4pillar_side_by_side_figure,
        create_12month_monthly_bill_comparison_figure,
        create_15year_tco_comparison_figure,
        build_4pillar_comparison_table,
    )
    from ui.common.cards import render_kpi_card
    from ui.common.styles import apply_custom_styles
except ImportError:
    from current_model.ui_sandbox.common import (
        ScenarioEvaluationOutput,
        render_standalone_baseline_control_bar,
        compute_15y_tco_npv,
        render_scenario_evaluation_output_card,
    )
    from current_model.ui_sandbox.Currentsituation_sandbox.engine.config_and_models import (
        LoadSeries2025,
        StatusQuoConfig2025,
        StatusQuoAnnualResult,
        TariffStage,
        MeteringTariff,
        LevyConfig,
    )
    from current_model.ui_sandbox.Currentsituation_sandbox.engine.consumption_pipeline import (
        extract_monthly_consumption_records,
    )
    from current_model.ui_sandbox.Currentsituation_sandbox.engine.dso_accounting import (
        calculate_dso_accounting_2025,
    )
    from current_model.ui_sandbox.Currentsituation_sandbox.engine.commercial_accounting import (
        calculate_commercial_accounting_2025,
    )
    from current_model.ui_sandbox.Currentsituation_sandbox.engine.status_quo_master import (
        calculate_status_quo_master_2025,
    )
    from current_model.ui_sandbox.Currentsituation_sandbox.contract.assumptions_banner import (
        build_assumptions_register_dict,
        render_assumptions_banner,
    )
    from current_model.ui_sandbox.Currentsituation_sandbox.contract.tab_dso import render_dso_tab
    from current_model.ui_sandbox.Currentsituation_sandbox.contract.tab_supplier import render_supplier_tab
    from current_model.ui_sandbox.Currentsituation_sandbox.contract.tab_metering import render_metering_tab
    from current_model.ui_sandbox.Currentsituation_sandbox.contract.tab_overview import render_overview_tab
    from current_model.ui_sandbox.Currentsituation_sandbox.contract.tab_invoice_experimental import (
        render_invoice_experimental_tab,
    )
    from current_model.ui_sandbox.Currentsituation_sandbox.contract.view import (
        _render_master_bill_equation_bar_html,
        _apply_reference_preset,
    )
    from current_model.ui_sandbox.NewContract_sandbox.contract_comparison_engine import (
        compute_contract_switch_kpis,
        create_4pillar_side_by_side_figure,
        create_12month_monthly_bill_comparison_figure,
        create_15year_tco_comparison_figure,
        build_4pillar_comparison_table,
    )
    from current_model.ui.common.cards import render_kpi_card
    from current_model.ui.common.styles import apply_custom_styles


def sync_contract_state(from_prefix: str = "con1", to_prefix: str = "con2") -> None:
    """
    Clones all session state parameters from from_prefix into to_prefix.
    Ensures that Contract 2 is 100% identical to Contract 1 until explicitly modified.
    Strictly skips ephemeral button/download widgets and st.data_editor state dictionaries
    to comply with Streamlit's widget policy (avoiding StreamlitValueAssignmentNotAllowedError).
    """
    source_tag = f"{from_prefix}_"
    target_tag = f"{to_prefix}_"
    prefix_len = len(source_tag)

    skip_keywords = (
        "btn",
        "button",
        "download",
        "dl_",
        "upload",
        "submit",
        "editor",
        "data_editor",
        "tou_editor",
        "_form",
    )

    # Clean existing target keys to avoid stale overrides
    for k in list(st.session_state.keys()):
        if k.startswith(target_tag):
            del st.session_state[k]

    # Deep-copy source parameters, strictly filtering out buttons and action widgets
    for k, v in list(st.session_state.items()):
        if k.startswith(source_tag):
            suffix = k[prefix_len:]
            if any(kw in suffix.lower() for kw in skip_keywords):
                continue
            target_key = f"{target_tag}{suffix}"
            try:
                st.session_state[target_key] = copy.deepcopy(v)
            except Exception:
                st.session_state[target_key] = v


def render_contract_workbench_instance(
    load_series: LoadSeries2025,
    key_prefix: str,
    contract_label: str,
) -> Tuple[StatusQuoConfig2025, StatusQuoAnnualResult]:
    """
    Renders an isolated 5-subtab electricity contract configuration & billing workbench instance:
      1. General Market Structure & Currency Settings
      2. Reference Benchmark Quick-Loader (Demo Presets: Enexis, Rotterdam Stedin, EDEMSA Mendoza)
      3. Master Bill Equation Bar
      4. Explicit Simulation Assumptions Register Banner
      5. 5 Modular Actor Sub-Tabs:
         - Sub-Tab 1: Grid Network (DSO)
         - Sub-Tab 2: Energy Supply (Retailer)
         - Sub-Tab 3: Metering & Statutory Taxes
         - Sub-Tab 4: Executive Overview & 15Y TCO
         - Sub-Tab 5: Classic Electricity Bill
    """
    # --- Top Control Bar: Separation Between Market Structure & Demo Presets ---
    col_top_market, col_top_preset = st.columns([1.35, 1.0], gap="medium")

    with col_top_market:
        with st.container(border=True):
            st.markdown(f"##### :material/tune: Market Structure & Currency ({contract_label})")
            ctrl_m1, ctrl_m2 = st.columns([2.6, 1.0])
            with ctrl_m1:
                market_mode_options = [
                    "Unbundled 4-Pillar Market (Netherlands / EU)",
                    "Integrated Single-Utility Bill (Argentina EDEMSA / Bundled DSO)",
                    "Custom Pillar Configuration",
                ]
                current_mode = st.session_state.get(f"{key_prefix}_market_mode", market_mode_options[0])
                mode_idx = market_mode_options.index(current_mode) if current_mode in market_mode_options else 0
                market_mode_label = st.selectbox(
                    "Market Structure Mode",
                    options=market_mode_options,
                    index=mode_idx,
                    key=f"{key_prefix}_market_mode",
                    help="Unbundled: Separate Retailer, DSO, Metering, Taxes. Single-Utility: Grays out Retailer & Metering.",
                )

            with ctrl_m2:
                curr_options = ["EUR", "ARS", "USD"]
                cur_curr = st.session_state.get(f"{key_prefix}_currency_code", "EUR")
                curr_idx = curr_options.index(cur_curr) if cur_curr in curr_options else 0
                currency_code = st.selectbox(
                    "Currency",
                    options=curr_options,
                    index=curr_idx,
                    key=f"{key_prefix}_currency_code",
                )

            # Resolve pillar enablement flags
            if "Integrated Single-Utility" in market_mode_label:
                market_mode_code = "single_utility"
                en_p2_dso = True
                en_p1_supplier = False
                en_p3_metering = False
                en_p4_taxes = True
                st.caption(
                    ":material/layers_clear: **Integrated Single-Utility Active:** "
                    "Retailer & Metering pillars evaluate to `0.00` and are grayed out (`[BYPASSED]`)."
                )
            elif "Custom" in market_mode_label:
                market_mode_code = "custom"
                chk1, chk2, chk3, chk4 = st.columns(4)
                with chk1:
                    en_p2_dso = st.checkbox(
                        "Pillar 2: DSO",
                        value=bool(st.session_state.get(f"{key_prefix}_en_p2", True)),
                        key=f"{key_prefix}_en_p2",
                    )
                with chk2:
                    en_p1_supplier = st.checkbox(
                        "Pillar 1: Supply",
                        value=bool(st.session_state.get(f"{key_prefix}_en_p1", True)),
                        key=f"{key_prefix}_en_p1",
                    )
                with chk3:
                    en_p3_metering = st.checkbox(
                        "Pillar 3: Metering",
                        value=bool(st.session_state.get(f"{key_prefix}_en_p3", True)),
                        key=f"{key_prefix}_en_p3",
                    )
                with chk4:
                    en_p4_taxes = st.checkbox(
                        "Pillar 4: Taxes",
                        value=bool(st.session_state.get(f"{key_prefix}_en_p4", True)),
                        key=f"{key_prefix}_en_p4",
                    )
            else:
                market_mode_code = "unbundled_4_pillar"
                en_p2_dso = True
                en_p1_supplier = True
                en_p3_metering = True
                en_p4_taxes = True
                st.caption(
                    ":material/check_circle: **Unbundled 4-Pillar Active:** "
                    "All 4 pillars (Retailer, DSO, Metering, and Taxes) are fully active."
                )

    with col_top_preset:
        with st.container(border=True):
            st.markdown(f"##### :material/science: Presets Quick-Loader ({contract_label})")
            ctrl_p1, ctrl_p2 = st.columns([2.2, 1.0])
            with ctrl_p1:
                preset_options = [
                    "Standard Enexis/Liander Commercial (250 kW Peak / 250 kW Limit)",
                    "Preset A: Rotterdam / Dutch WKO Site (Stedin Region - 110 kW Limit)",
                    "Preset B: EDEMSA Mendoza T2 RMT (Bodegas Salentein - 430 kW Limit)",
                ]
                selected_preset = st.selectbox(
                    "Benchmark Tariff Preset",
                    options=preset_options,
                    index=0,
                    key=f"{key_prefix}_ref_preset_sel",
                    help="Auto-applies calibrated utility tariffs, taxes, and contract structures.",
                )
                last_applied_key = f"{key_prefix}_last_applied_ref_preset"
                if last_applied_key not in st.session_state:
                    st.session_state[last_applied_key] = selected_preset
                elif st.session_state[last_applied_key] != selected_preset:
                    st.session_state[last_applied_key] = selected_preset
                    _apply_reference_preset(selected_preset, key_prefix=key_prefix)
                    st.rerun()

            with ctrl_p2:
                st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                btn_load_key = f"{key_prefix}_btn_load_preset"
                if btn_load_key in st.session_state:
                    del st.session_state[btn_load_key]
                if st.button(
                    ":material/download_done: Load",
                    use_container_width=True,
                    key=btn_load_key,
                    help="Applies this preset to this contract setup.",
                ):
                    st.session_state[f"{key_prefix}_last_applied_ref_preset"] = selected_preset
                    _apply_reference_preset(selected_preset, key_prefix=key_prefix)
                    st.rerun()

    equation_bar_container = st.container()
    assumptions_banner_container = st.container()

    # 5 Actor Sub-Tabs (append [BYPASSED] to grayed-out pillars)
    tab1_title = ":material/grid_view: 1. Grid Network (DSO)" + ("" if en_p2_dso else " [BYPASSED]")
    tab2_title = ":material/storefront: 2. Energy Supply (Retailer)" + ("" if en_p1_supplier else " [BYPASSED]")
    if en_p3_metering and en_p4_taxes:
        tab3_suffix = ""
    elif not en_p3_metering and not en_p4_taxes:
        tab3_suffix = " [BYPASSED]"
    elif not en_p3_metering:
        tab3_suffix = " [Metering BYPASSED]"
    else:
        tab3_suffix = " [Taxes BYPASSED]"
    tab3_title = f":material/speed: 3. Metering & Statutory Taxes{tab3_suffix}"

    actor_tabs = st.tabs([
        tab1_title,
        tab2_title,
        tab3_title,
        ":material/analytics: 4. Executive Overview & 15Y TCO",
        ":material/receipt: 5. Classic Electricity Bill",
    ])

    with actor_tabs[0]:
        dso_tariff = render_dso_tab(
            load_series=load_series,
            key_prefix=key_prefix,
            is_enabled=en_p2_dso,
            currency_code=currency_code,
        )

    with actor_tabs[1]:
        supplier_tariff = render_supplier_tab(
            load_series=load_series,
            key_prefix=key_prefix,
            is_enabled=en_p1_supplier,
            currency_code=currency_code,
        )

    # Pre-compute monthly net arrays for Pillar 2 (DSO) and Pillar 1 (Supplier) so Tab 3 computes percentage levies live
    monthly_cons_pre = extract_monthly_consumption_records(load_series)
    if en_p2_dso:
        dso_res_pre, _ = calculate_dso_accounting_2025(
            load=load_series,
            monthly_consumption=monthly_cons_pre,
            dso_tariff=dso_tariff,
        )
        dso_monthly_net_pre = [round(r.subtotal_dso_net, 2) for r in dso_res_pre]
    else:
        dso_monthly_net_pre = [0.0] * len(monthly_cons_pre)

    if en_p1_supplier:
        comm_res_pre, _ = calculate_commercial_accounting_2025(
            load=load_series,
            monthly_consumption=monthly_cons_pre,
            supplier_tariff=supplier_tariff,
            metering_tariff=MeteringTariff(annual_flat_fee=0.0),
            levy_config=LevyConfig(statutory_levy_rate_kwh=0.0, annual_tax_reduction=0.0),
        )
        supplier_monthly_net_pre = [round(r.supplier_base_fee + r.supplier_energy_cost, 2) for r in comm_res_pre]
    else:
        supplier_monthly_net_pre = [0.0] * len(monthly_cons_pre)

    with actor_tabs[2]:
        metering_tariff, levy_config, discount_rate, escalation_rate = render_metering_tab(
            load_series=load_series,
            key_prefix=key_prefix,
            enable_p3_metering=en_p3_metering,
            enable_p4_taxes=en_p4_taxes,
            currency_code=currency_code,
            dso_monthly_net=dso_monthly_net_pre,
            supplier_monthly_net=supplier_monthly_net_pre,
        )

    active_config = StatusQuoConfig2025(
        stage=TariffStage.STAGE_1_DEFAULT,
        dso=dso_tariff,
        supplier=supplier_tariff,
        metering=metering_tariff,
        levies=levy_config,
        discount_rate_pct=discount_rate,
        energy_escalation_pct=escalation_rate,
        evaluation_horizon_years=15,
        currency_code=currency_code,
        market_mode=market_mode_code,
        enable_pillar_1_supplier=en_p1_supplier,
        enable_pillar_2_dso=en_p2_dso,
        enable_pillar_3_metering=en_p3_metering,
        enable_pillar_4_taxes=en_p4_taxes,
    )

    result = calculate_status_quo_master_2025(load=load_series, config=active_config)

    assumptions_dict = build_assumptions_register_dict(
        load_series=load_series,
        config=active_config,
        source_filename=contract_label,
        bess_config=None,
    )

    with equation_bar_container:
        st.markdown(_render_master_bill_equation_bar_html(result), unsafe_allow_html=True)

    with assumptions_banner_container:
        render_assumptions_banner(assumptions_dict=assumptions_dict, expanded=False)

    with actor_tabs[3]:
        render_overview_tab(
            result=result,
            active_config=active_config,
            key_prefix=key_prefix,
        )

    with actor_tabs[4]:
        render_invoice_experimental_tab(
            result=result,
            active_config=active_config,
            load_series=load_series,
            key_prefix=key_prefix,
            assumptions_dict=assumptions_dict,
        )

    return active_config, result


def render_new_contract_sandbox(key_prefix: str = "newcon_sb") -> ScenarioEvaluationOutput:
    """
    Main orchestrator for Scenario 2: Standalone Contract Switch & Twin-Contract Benchmark Sandbox.
    """
    # Top Header Banner
    st.markdown(
        """
        <div style="background: linear-gradient(90deg, #0f172a 0%, #1e293b 100%);
                    border-left: 5px solid #38bdf8; padding: 14px 20px; border-radius: 8px; margin-bottom: 12px;">
            <h3 style="margin:0; color:#f8fafc; font-size:1.25rem;">
                Scenario 2: Standalone Contract Switch & Twin-Contract Benchmark Sandbox
            </h3>
            <p style="margin:4px 0 0 0; color:#94a3b8; font-size:0.86rem;">
                Benchmark your Status Quo electricity contract against an alternative supply contract or right-sized
                grid capacity without investing in hardware. Contract 2 is cloned identically from Contract 1 by default,
                allowing you to switch only the energy retailer or adjust contracted capacity in seconds.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Top standalone baseline selector (Default: Preset A Rotterdam WKO or user choice)
    base_load, base_config, site_label = render_standalone_baseline_control_bar(
        key_prefix=key_prefix,
        default_preset_idx=0,
    )

    # 3-Tab Main Architecture
    main_tabs = st.tabs([
        ":material/description: 1. Contract 1 (Status Quo Baseline)",
        ":material/tune: 2. Contract 2 (Alternative / Switch Setup)",
        ":material/compare_arrows: 3. Cost Comparison & Delta Analytics",
    ])

    # ----------------------------------------------------------------------------------
    # TAB 1: Contract 1 — Current Situation (Baseline Contract)
    # ----------------------------------------------------------------------------------
    with main_tabs[0]:
        st.markdown("#### :material/description: Contract 1 Setup (Status Quo Baseline)")
        st.caption(
            "Configure your active baseline electricity contract across the 5 standard sub-tabs. "
            "Contract 2 automatically clones these values as its starting point."
        )
        cfg1, res1 = render_contract_workbench_instance(
            load_series=base_load,
            key_prefix="con1",
            contract_label="Contract 1 (Baseline)",
        )

    # Automatic first-time synchronization: Clone Contract 1 into Contract 2
    if not st.session_state.get("con2_initialized", False):
        sync_contract_state("con1", "con2")
        st.session_state["con2_initialized"] = True

    # ----------------------------------------------------------------------------------
    # TAB 2: Contract 2 — Alternative Contract (Switch Setup)
    # ----------------------------------------------------------------------------------
    with main_tabs[1]:
        with st.container(border=True):
            col_bar_info, col_bar_action = st.columns([3.6, 1.4])
            with col_bar_info:
                st.markdown(
                    "**:material/tune: Contract 2 Setup (Alternative Contract / Switch Setup)**<br>"
                    "<span style='color:#94a3b8; font-size:0.84rem;'>"
                    "Contract 2 is initialized from Contract 1. Modify only the fields you want to test "
                    "(e.g. switch the Energy Retailer in Sub-tab 2 from Fixed to EPEX Spot or right-size Contracted Capacity in Sub-tab 1). "
                    "All other parameters remain synchronized."
                    "</span>",
                    unsafe_allow_html=True,
                )
            with col_bar_action:
                st.markdown("<div style='height: 4px;'></div>", unsafe_allow_html=True)
                if st.button(
                    ":material/content_copy: Reset / Sync from Contract 1",
                    key="btn_con2_sync_from_con1",
                    use_container_width=True,
                    help="Overwrites all Contract 2 fields with the exact values currently configured in Contract 1.",
                ):
                    sync_contract_state("con1", "con2")
                    st.toast("Contract 2 successfully synced from Contract 1!", icon=":material/check_circle:")
                    st.rerun()

        cfg2, res2 = render_contract_workbench_instance(
            load_series=base_load,
            key_prefix="con2",
            contract_label="Contract 2 (Alternative Switch)",
        )

    # ----------------------------------------------------------------------------------
    # TAB 3: Cost Comparison & Delta Analytics (Contract 1 vs. Contract 2)
    # ----------------------------------------------------------------------------------
    with main_tabs[2]:
        kpis = compute_contract_switch_kpis(res1, res2)
        curr = kpis["currency_code"]

        # Executive Delta Header & Status Badge
        delta_net = kpis["delta_net"]
        pct_net = kpis["pct_net"]

        if delta_net > 50.0:
            st.markdown(
                f"""
                <div style="background-color: #06281e; border: 2px solid #10b981; border-radius: 8px; padding: 12px 18px; margin-bottom: 14px;">
                    <strong style="color:#34d399; font-size:1.05rem;">
                        :material/trending_down: Cost Savings Achieved: -{curr} {delta_net:,.2f} / year (-{pct_net:.1f}%)
                    </strong>
                    <div style="color:#a7f3d0; font-size:0.86rem; margin-top:2px;">
                        Contract 2 successfully reduces your annual net electricity invoice from <b>{curr} {kpis['net1']:,.2f}</b> down to <b>{curr} {kpis['net2']:,.2f}</b>.
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        elif delta_net < -50.0:
            st.markdown(
                f"""
                <div style="background-color: #2b1113; border: 2px solid #ef4444; border-radius: 8px; padding: 12px 18px; margin-bottom: 14px;">
                    <strong style="color:#f87171; font-size:1.05rem;">
                        :material/trending_up: Cost Increase / Surcharge: +{curr} {abs(delta_net):,.2f} / year (+{abs(pct_net):.1f}%)
                    </strong>
                    <div style="color:#fca5a5; font-size:0.86rem; margin-top:2px;">
                        Contract 2 increases annual net electricity expenses from <b>{curr} {kpis['net1']:,.2f}</b> to <b>{curr} {kpis['net2']:,.2f}</b>.
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"""
                <div style="background-color: #0f172a; border: 1.5px solid #64748b; border-radius: 8px; padding: 12px 18px; margin-bottom: 14px;">
                    <strong style="color:#f8fafc; font-size:1.02rem;">
                        :material/check_circle: Parity / Identical Costs: Both Contracts Produce the Same Net Bill
                    </strong>
                    <div style="color:#94a3b8; font-size:0.85rem; margin-top:2px;">
                        Contract 1 and Contract 2 evaluate to virtually identical annual costs (Net Delta: <b>{curr} {delta_net:,.2f}</b>).
                        Modify parameters in Tab 2 to benchmark a contract switch.
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # 5 Executive Delta KPI Metric Cards
        sk1, sk2, sk3, sk4, sk5 = st.columns(5)
        with sk1:
            render_kpi_card(
                "Annual Net Bill Delta",
                f"{'+' if delta_net >= 0 else '-'}{curr} {abs(delta_net):,.2f}",
                f"{'+' if delta_net >= 0 else ''}{pct_net:.1f}% vs. Baseline",
                status="ok" if delta_net >= 0 else "warning",
            )
        with sk2:
            render_kpi_card(
                "Annual Gross Delta (incl. VAT)",
                f"{'+' if kpis['delta_gross'] >= 0 else '-'}{curr} {abs(kpis['delta_gross']):,.2f}",
                f"Gross: {curr} {kpis['gross1']:,.0f} -> {curr} {kpis['gross2']:,.0f}",
                status="ok" if kpis["delta_gross"] >= 0 else "warning",
            )
        with sk3:
            render_kpi_card(
                "Pillar 1: Energy Supply Delta",
                f"{'+' if kpis['delta_p1'] >= 0 else '-'}{curr} {abs(kpis['delta_p1']):,.2f}",
                f"Base: {curr} {kpis['p1_1']:,.0f} | Switch: {curr} {kpis['p1_2']:,.0f}",
            )
        with sk4:
            render_kpi_card(
                "Pillar 2: Grid Operator Delta",
                f"{'+' if kpis['delta_p2'] >= 0 else '-'}{curr} {abs(kpis['delta_p2']):,.2f}",
                f"Base: {curr} {kpis['p2_1']:,.0f} | Switch: {curr} {kpis['p2_2']:,.0f}",
            )
        with sk5:
            render_kpi_card(
                "Blended Rate Delta",
                f"{'+' if kpis['delta_rate'] >= 0 else '-'}{curr} {abs(kpis['delta_rate']):.4f}/kWh",
                f"{curr} {kpis['rate1']:.4f} -> {curr} {kpis['rate2']:.4f}/kWh",
                status="ok" if kpis["delta_rate"] >= 0 else "warning",
            )

        st.write("")

        # Visual Analytics Suite
        c_fig_left, c_fig_right = st.columns(2)
        with c_fig_left:
            st.plotly_chart(
                create_4pillar_side_by_side_figure(res1, res2),
                use_container_width=True,
            )
        with c_fig_right:
            st.plotly_chart(
                create_12month_monthly_bill_comparison_figure(res1, res2),
                use_container_width=True,
            )

        st.plotly_chart(
            create_15year_tco_comparison_figure(res1, res2),
            use_container_width=True,
        )

        st.divider()

        # Detailed 4-Pillar Comparative Audit Table
        st.subheader("4-Pillar Detailed Line-by-Line Comparative Audit")
        st.caption(
            "Complete comparison of all 4 pillars, sub-ledgers, standing fees, capacity charges, and invoice positions."
        )
        df_comp_table = build_4pillar_comparison_table(res1, res2)
        st.dataframe(df_comp_table, use_container_width=True, hide_index=True)

        st.divider()

        # Grid Capacity & Breach Diagnostics
        st.subheader("Grid Capacity & Breach Penalty Diagnostics")
        st.caption(
            "Evaluates whether right-sizing contracted capacity (P_contract) eliminates excess breach penalties or creates capacity fee savings."
        )
        diag1, diag2, diag3, diag4 = st.columns(4)
        with diag1:
            render_kpi_card(
                "Contracted Capacity (P_contract)",
                f"{kpis['cap2']:,.1f} kW",
                f"Baseline: {kpis['cap1']:,.1f} kW (Δ {kpis['delta_cap']:+,.1f} kW)",
            )
        with diag2:
            render_kpi_card(
                "Measured Peak Demand",
                f"{base_load.peak_demand_kw:,.1f} kW",
                f"Headroom / Overload: {kpis['cap2'] - base_load.peak_demand_kw:+,.1f} kW",
                status="ok" if kpis["cap2"] >= base_load.peak_demand_kw else "warning",
            )
        with diag3:
            render_kpi_card(
                "Capacity Breach Months",
                f"{kpis['breach2']} Months",
                f"Baseline: {kpis['breach1']} Months (Δ {kpis['breach2'] - kpis['breach1']:+d})",
                status="warning" if kpis["breach2"] > 0 else "ok",
            )
        with diag4:
            render_kpi_card(
                "Excess Capacity Penalty",
                f"{curr} {kpis['pen2']:,.2f}",
                f"Baseline: {curr} {kpis['pen1']:,.2f} (Savings: {curr} {kpis['delta_pen']:+,.2f})",
                status="ok" if kpis["pen2"] < 0.01 else "warning",
            )

        st.divider()

        # Export & Master Integration Section
        st.subheader("Report Export & Master Multi-Scenario Integration")
        exp_col1, exp_col2 = st.columns(2)

        with exp_col1:
            csv_data = df_comp_table.to_csv(index=False).encode("utf-8")
            st.download_button(
                label=":material/download: Export 4-Pillar Comparison Table (.csv)",
                data=csv_data,
                file_name=f"contract_switch_comparison_{curr}.csv",
                mime="text/csv",
                use_container_width=True,
                key=f"{key_prefix}_dl_comp_csv",
            )

        with exp_col2:
            output_obj = ScenarioEvaluationOutput(
                scenario_id="scenario_2_contract_switch",
                scenario_name="Scenario 2: Contract & Capacity Optimization",
                sub_scenario_label="Alternative Contract Benchmarking",
                currency_code=curr,
                peak_before_kw=float(base_load.peak_demand_kw),
                peak_after_kw=float(base_load.peak_demand_kw),
                peak_shaved_kw=0.0,
                peak_shaved_pct=0.0,
                grid_limit_kw=float(cfg2.dso.contracted_capacity_kw),
                overload_hours_before=float(kpis["breach1"]),
                overload_hours_after=float(kpis["breach2"]),
                annual_load_kwh=float(base_load.total_energy_kwh),
                annual_grid_import_before_kwh=float(base_load.total_energy_kwh),
                annual_grid_import_after_kwh=float(base_load.total_energy_kwh),
                self_consumption_pct=0.0,
                autarky_pct=0.0,
                capex_total=0.0,
                annual_tech_opex=0.0,
                annual_grid_bill_net_before=float(kpis["net1"]),
                annual_grid_bill_net_after=float(kpis["net2"]),
                annual_grid_bill_gross_before=float(kpis["gross1"]),
                annual_grid_bill_gross_after=float(kpis["gross2"]),
                annual_net_savings=float(delta_net),
                simple_payback_years=0.0,
                npv_15y_tco_before=float(kpis["tco1"]),
                npv_15y_tco_after=float(kpis["tco2"]),
                npv_15y_net_benefit=float(kpis["delta_tco"]),
            )
            st.session_state["scenario_2_contract_switch_output"] = output_obj

            out_json = output_obj.to_json()
            st.download_button(
                label=":material/share: Export Standardized Scenario Evaluation (.json)",
                data=out_json.encode("utf-8"),
                file_name=f"scenario_2_contract_switch_evaluation_{curr}.json",
                mime="application/json",
                use_container_width=True,
                key=f"{key_prefix}_dl_output_json",
            )

        render_scenario_evaluation_output_card(output=output_obj, key_prefix=f"{key_prefix}_eval_card")

    return output_obj


def main() -> None:
    st.set_page_config(
        page_title="Scenario 2: Contract Switch Sandbox",
        page_icon=":material/tune:",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    apply_custom_styles()
    render_new_contract_sandbox(key_prefix="newcon_sb")


if __name__ == "__main__":
    main()
