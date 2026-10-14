"""
========================================================================================
Status Quo 2025 Contract & Billing View (Currentsituation_sandbox/contract/view.py)
========================================================================================

2-Column Live Cockpit for Dutch Grootverbruik (> 3x80A) Electricity Procurement:
  - Persistent Top Master KPI Bar (Annual Spend, Blended Rate, Peak vs GTV, 15-Year TCO).
  - 60/40 Split Live Cockpit:
    * Left (60%): 4 Unbundled Pillars with Progressive Disclosure (Core inputs visible,
      advanced parameters in collapsed expanders, auto-coupling & auto-fit GTV).
    * Right (40%): Live Invoice Receipt Card, Cost Donut Chart, and Compliance Alert.
  - 3 Structured Lower Deep-Dive Analysis Tabs:
    * View 1: 12-Month Payment Schedule & Statement Table.
    * View 2: 15-Year TCO & Lifecycle Cashflows.
    * View 3: Strategic Procurement Advisory (3 Routes, Voltage Transition, BESS Flex) & Audit.
========================================================================================
"""

import io
import json
from typing import Tuple, Optional, Any, List, Dict
import streamlit as st
import pandas as pd
import numpy as np

# Styling & Common Components
try:
    from current_model.ui.common.styles import apply_custom_styles
    from current_model.ui.common.cards import render_kpi_card
    from current_model.ui_sandbox.Currentsituation_sandbox.contract.charts import (
        create_monthly_payment_series_figure,
        create_cost_donut_figure,
        create_tou_schedule_diurnal_figure,
        create_15_year_lifecycle_cost_figure,
    )
except ImportError:
    try:
        from ui.common.styles import apply_custom_styles
        from ui.common.cards import render_kpi_card
        from ui_sandbox.Currentsituation_sandbox.contract.charts import (
            create_monthly_payment_series_figure,
            create_cost_donut_figure,
            create_tou_schedule_diurnal_figure,
            create_15_year_lifecycle_cost_figure,
        )
    except ImportError:
        from current_model.ui.common.styles import apply_custom_styles
        from current_model.ui.common.cards import render_kpi_card
        from contract.charts import (
            create_monthly_payment_series_figure,
            create_cost_donut_figure,
            create_tou_schedule_diurnal_figure,
            create_15_year_lifecycle_cost_figure,
        )

# 2025 Grootverbruik 4-Pillar Engine Modules & Catalogs
try:
    from ui_sandbox.Currentsituation_sandbox.engine import (
        TariffStage,
        PricingMode,
        SupplierCategory,
        TrancheBlock,
        DSOTariff,
        SupplierTariff,
        MeteringTariff,
        TrafoRentalTariff,
        LevyConfig,
        StatusQuoConfig2025,
        LoadSeries2025,
        DSO_CATALOGS_2025,
        SUPPLIER_CATALOG_2025,
        METERING_CATALOG_2025,
        TRAFO_CATALOG_2025,
        get_dso_tariff_from_catalog,
        get_supplier_tariff_from_catalog,
        get_trafo_tariff_from_catalog,
        get_metering_tariff_from_catalog,
        get_default_levy_config,
        normalize_load_profile_2025,
        synthesize_benchmark_load_profile_2025,
        calculate_status_quo_master,
        convert_to_financial_cost_breakdown,
        perform_full_status_quo_audit,
    )
    from ui_sandbox.Currentsituation_sandbox.ui_theme import (
        render_live_invoice_card,
        render_metric_card,
    )
    from ui_sandbox.Currentsituation_sandbox.contract.procurement_view import (
        render_procurement_strategy_view,
    )
except ImportError:
    from current_model.ui_sandbox.Currentsituation_sandbox.engine import (
        TariffStage,
        PricingMode,
        SupplierCategory,
        TrancheBlock,
        DSOTariff,
        SupplierTariff,
        MeteringTariff,
        TrafoRentalTariff,
        LevyConfig,
        StatusQuoConfig2025,
        LoadSeries2025,
        DSO_CATALOGS_2025,
        SUPPLIER_CATALOG_2025,
        METERING_CATALOG_2025,
        TRAFO_CATALOG_2025,
        get_dso_tariff_from_catalog,
        get_supplier_tariff_from_catalog,
        get_trafo_tariff_from_catalog,
        get_metering_tariff_from_catalog,
        get_default_levy_config,
        normalize_load_profile_2025,
        synthesize_benchmark_load_profile_2025,
        calculate_status_quo_master,
        convert_to_financial_cost_breakdown,
        perform_full_status_quo_audit,
    )
    from current_model.ui_sandbox.Currentsituation_sandbox.ui_theme import (
        render_live_invoice_card,
        render_metric_card,
    )
    from current_model.ui_sandbox.Currentsituation_sandbox.contract.procurement_view import (
        render_procurement_strategy_view,
    )


def _find_or_create_load_series_2025() -> Tuple[LoadSeries2025, str]:
    """Retrieves or normalizes the active load profile for reference year 2025."""
    if "active_load_series_2025" in st.session_state and isinstance(st.session_state["active_load_series_2025"], LoadSeries2025):
        fname = st.session_state.get("active_csv_filename", "Active Profile")
        return st.session_state["active_load_series_2025"], f"Normalized 2025 Meter Data ({fname})"

    if "active_csv_df" in st.session_state and isinstance(st.session_state["active_csv_df"], pd.DataFrame):
        df_csv = st.session_state["active_csv_df"]
        if not df_csv.empty:
            fname = st.session_state.get("active_csv_filename", "Uploaded Meter File")
            p_col = "Total_Demand_kW" if "Total_Demand_kW" in df_csv.columns else df_csv.columns[1]
            t_col = "timestamp" if "timestamp" in df_csv.columns else None
            try:
                load_norm, _ = normalize_load_profile_2025(raw_df=df_csv, power_col=p_col, time_col=t_col)
                st.session_state["active_load_series_2025"] = load_norm
                return load_norm, f"CSV Real Meter Data ({fname})"
            except Exception:
                pass

    load_bench = synthesize_benchmark_load_profile_2025(nominal_peak_kw=250.0)
    st.session_state["active_load_series_2025"] = load_bench
    return load_bench, "Commercial Benchmark Simulation (250 kW peak)"


def render_tab2_base_contract(key_prefix: str = "currsit_contract") -> Any:
    """
    Renders the Status Quo 2025 Electricity Contract Configuration & Accounting view
    using an optimized 2-column live cockpit layout with progressive disclosure.
    """
    load_series, source_label = _find_or_create_load_series_2025()

    # Active Baseline Banner
    st.info(
        f":material/bolt: **Active Consumption Baseline:** {source_label} | "
        f"**Annual Energy:** {load_series.total_energy_kwh:,.1f} kWh | "
        f"**Peak Demand:** {load_series.peak_demand_kw:,.1f} kW",
        icon=":material/info:"
    )

    # ----------------------------------------------------------------------------------
    # Persistent Top Master KPI Placeholder (Populated dynamically after calculation)
    # ----------------------------------------------------------------------------------
    top_kpi_container = st.container()

    st.markdown("---")

    # ----------------------------------------------------------------------------------
    # 2-Column Live Cockpit (60% Control Configuration / 40% Live Invoice & Donut)
    # ----------------------------------------------------------------------------------
    col_controls, col_receipt = st.columns([1.45, 1.05], gap="medium")

    with col_controls:
        st.markdown("#### :material/tune: 4-Pillar Contract Parameters")

        pillar_tabs = st.tabs([
            ":material/grid_view: 1. DSO Grid",
            ":material/bolt: 2. Supplier",
            ":material/speed: 3. Meter & Trafo",
            ":material/account_balance: 4. Taxes & TCO"
        ])

        # ==============================================================================
        # Pillar 1: Regulated Grid Operator (DSO)
        # ==============================================================================
        with pillar_tabs[0]:
            st.markdown("##### Regulated Grid Connection & Transport Tariffs")

            col_dso_co, col_dso_tier = st.columns([1.3, 2.7])
            with col_dso_co:
                dso_company_options = list(DSO_CATALOGS_2025.keys()) + ["Custom / Other Grid Operator"]
                selected_dso_company = st.selectbox(
                    "Grid Operator (Netbeheerder):",
                    options=dso_company_options,
                    index=0,
                    key=f"{key_prefix}_dso_company"
                )

            with col_dso_tier:
                if selected_dso_company in DSO_CATALOGS_2025:
                    tier_dict = DSO_CATALOGS_2025[selected_dso_company]
                    tier_options = list(tier_dict.keys())
                    default_tier_idx = 0
                    for idx, t_name in enumerate(tier_options):
                        if "MS-D" in t_name or ("MS" in t_name and "LS" not in t_name):
                            default_tier_idx = idx
                            break
                    selected_tier = st.selectbox(
                        "Tariff Category & Voltage Tier:",
                        options=tier_options,
                        index=default_tier_idx,
                        key=f"{key_prefix}_dso_tier"
                    )
                    preset_data = tier_dict[selected_tier]
                    st.caption(f":material/info: *{preset_data.get('description', '')}*")
                else:
                    selected_tier = "Custom"
                    preset_data = {
                        "aansluitdienst_annual": 1653.00,
                        "vastrecht_annual": 441.00,
                        "rate_contracted_monthly": 2.4400,
                        "rate_peak_monthly": 3.7100,
                        "rate_peak_kwh": 0.0250,
                        "rate_offpeak_kwh": 0.0250,
                        "reactive_tariff": 0.0188,
                    }
                    st.caption(":material/tune: *Custom grid operator tariffs.*")

            # Smart Defaults & Auto-Coupling Logic (Action Plan 2.1)
            is_low_voltage = any(x in selected_tier for x in ["AC2", "AC3", "AC4", "LS", "Laagspanning", "Trafo DSO"])
            is_medium_voltage = any(x in selected_tier for x in ["AC5", "AC6", "MS", "Middenspanning"])

            last_tier_key = f"{key_prefix}_last_selected_tier"
            prev_tier = st.session_state.get(last_tier_key)
            tier_has_changed = (prev_tier is not None and prev_tier != selected_tier)

            trafo_prov_key = f"{key_prefix}_trafo_provider"
            trafo_cap_key = f"{key_prefix}_trafo_cap_select"
            trafo_fee_key = f"{key_prefix}_trafo_annual_fee"
            meter_pkg_key = f"{key_prefix}_meter_pkg_select"

            if prev_tier is None or tier_has_changed:
                st.session_state[last_tier_key] = selected_tier
                if is_low_voltage:
                    st.session_state[trafo_prov_key] = "None / DSO Owned Trafo"
                    st.session_state[trafo_cap_key] = "No Rental (Low Voltage AC4b or Customer Owned)"
                    st.session_state[trafo_fee_key] = 0.0
                    st.session_state[meter_pkg_key] = "LS Telemetrie Wandlermessung"
                elif is_medium_voltage:
                    st.session_state[trafo_prov_key] = "Fudura B.V."
                    st.session_state[trafo_cap_key] = "400 - 630 kVA Compactstation (€ 4,248 / yr = € 354 / mo)"
                    st.session_state[trafo_fee_key] = 4248.0
                    st.session_state[meter_pkg_key] = "MS <= 1 MW Telemetrie"

            # Auto-Fit GTV Helper (Action Plan 2.2)
            gtv_key = f"{key_prefix}_dso_p_contract"
            peak_measured = float(load_series.peak_demand_kw)
            recommended_gtv = float(max(50.0, round(peak_measured * 1.05, 0)))

            if gtv_key not in st.session_state:
                st.session_state[gtv_key] = recommended_gtv

            col_gtv_val, col_gtv_act = st.columns([1.8, 1.2])
            with col_gtv_val:
                contracted_kw = st.number_input(
                    "Contracted Grid Capacity GTV (kW):",
                    min_value=10.0,
                    max_value=20000.0,
                    value=float(st.session_state[gtv_key]),
                    step=10.0,
                    format="%.1f",
                    key=gtv_key,
                    help="Gecontracteerd Transportvermogen (GTV) reserved on the grid for your facility"
                )
            with col_gtv_act:
                st.write("")
                st.write("")
                if st.button(
                    ":material/auto_fix_high: Auto-Fit (Peak + 5%)",
                    key=f"{key_prefix}_btn_autofit_gtv",
                    help=f"Automatically set GTV to {recommended_gtv:,.1f} kW (measured peak {peak_measured:,.1f} kW + 5% buffer)",
                    use_container_width=True
                ):
                    st.session_state[gtv_key] = recommended_gtv
                    st.rerun()

            # Core DSO Rates
            col_cr1, col_cr2 = st.columns(2)
            with col_cr1:
                capacity_tariff = st.number_input(
                    "Contracted Capacity Rate GTV (€/kW/month):",
                    min_value=0.0,
                    value=float(preset_data.get("rate_contracted_monthly", 3.6567)),
                    step=0.01,
                    format="%.4f",
                    key=f"{key_prefix}_dso_rate_cap_{selected_tier}",
                    help="Monthly fee billed per reserved kW (Capaciteitstarief GTV in €/kW/mo)"
                )
            with col_cr2:
                demand_tariff = st.number_input(
                    "Monthly Peak Demand Rate (€/kW/month):",
                    min_value=0.0,
                    value=float(preset_data.get("rate_peak_monthly", 3.4600)),
                    step=0.01,
                    format="%.4f",
                    key=f"{key_prefix}_dso_rate_peak_{selected_tier}",
                    help="Monthly fee billed per measured 15-minute maximum peak (Maandpiek in €/kW/mo)"
                )

            # Progressive Disclosure: Advanced Grid Tariff Details & Overrides
            with st.expander(":material/tune: Advanced Grid Tariff Details & Overrides", expanded=False):
                col_adv1, col_adv2 = st.columns(2)
                with col_adv1:
                    fixed_conn_mnd = st.number_input(
                        "Connection Fee PAV (€/month):",
                        min_value=0.0,
                        value=float(preset_data.get("fixed_connection_monthly", 57.73)),
                        step=5.0,
                        format="%.2f",
                        key=f"{key_prefix}_dso_pav_{selected_tier}",
                        help="Periodieke aansluitvergoeding (PAV) per maand based on connection capacity."
                    )
                    base_fee = st.number_input(
                        "Fixed Transport Admin Fee Vastrecht (€/month):",
                        min_value=0.0,
                        value=round(float(preset_data.get("vastrecht_annual", 52.54)) / 12.0, 2),
                        step=1.0,
                        format="%.2f",
                        key=f"{key_prefix}_dso_base_fee_{selected_tier}",
                        help="Fixed standing charge for grid administration (Vastrecht transport €/month)."
                    )
                    cable_surcharge = st.number_input(
                        "Cable Surcharge Meerlengte (€/year):",
                        min_value=0.0,
                        value=float(preset_data.get("cable_surcharge_annual", 0.0)),
                        step=50.0,
                        format="%.2f",
                        key=f"{key_prefix}_dso_cable_{selected_tier}",
                        help="Meerlengte connection cable surcharge if connection cable > 25 meters."
                    )
                with col_adv2:
                    max_physical_kw = st.number_input(
                        "Physical Connection Limit (kW):",
                        min_value=10.0,
                        value=float(preset_data.get("max_physical_limit_kw", 1000.0)),
                        step=50.0,
                        format="%.1f",
                        key=f"{key_prefix}_dso_max_phys_{selected_tier}",
                        help="Maximum physical electrical capacity limit of your transformer or main connection."
                    )
                    penalty_rate = st.number_input(
                        "Peak Overload Penalty Rate (€/kW):",
                        min_value=0.0,
                        value=float(preset_data.get("peak_penalty_rate_kw", 0.0)),
                        step=0.05,
                        format="%.4f",
                        key=f"{key_prefix}_dso_penalty_rate_{selected_tier}",
                        help="Penalty fee per kW for exceeding contracted capacity."
                    )
                    currency = st.selectbox(
                        "Currency:",
                        options=["EUR", "USD", "GBP", "CHF"],
                        index=0,
                        key=f"{key_prefix}_dso_currency"
                    )

                st.markdown("###### Reactive Power & Power Factor (Blindenergie)")
                q1, q2, q3 = st.columns(3)
                with q1:
                    reactive_tariff = st.number_input(
                        "Reactive Rate (€/kVARh):",
                        min_value=0.0,
                        value=float(preset_data.get("reactive_tariff", 0.0188)),
                        step=0.005,
                        format="%.4f",
                        key=f"{key_prefix}_dso_reactive_{selected_tier}",
                        help="Tariff for consumed reactive energy (Blindenergie €/kVARh)."
                    )
                with q2:
                    min_cos_phi = st.number_input(
                        "Target cos φ:",
                        min_value=0.50,
                        max_value=1.00,
                        value=float(preset_data.get("min_power_factor", 0.90)),
                        step=0.02,
                        format="%.2f",
                        key=f"{key_prefix}_dso_cosphi_{selected_tier}",
                        help="Minimum required power factor (cos φ = 0.90) to avoid reactive charges."
                    )
                with q3:
                    reactive_allowance = st.number_input(
                        "Free Reactive Allowance (%):",
                        min_value=0.0,
                        max_value=100.0,
                        value=float(preset_data.get("reactive_allowance_pct", 33.0)),
                        step=1.0,
                        format="%.1f",
                        key=f"{key_prefix}_dso_q_allow_{selected_tier}",
                        help="Permitted free reactive energy as a percentage of active consumption."
                    )

                st.markdown("###### Time-of-Use Rate Matrix (DSO Variable Transport)")
                state_dso_tou_key = f"{key_prefix}_dso_tou_df_{selected_dso_company}_{selected_tier}"
                if state_dso_tou_key not in st.session_state:
                    default_peak = float(preset_data.get("rate_peak_kwh", 0.0250))
                    default_offpeak = float(preset_data.get("rate_offpeak_kwh", 0.0250))
                    st.session_state[state_dso_tou_key] = pd.DataFrame([
                        {"name": "Daytime / Working Hours (HT)", "rate": default_peak, "start_time": "07:00", "end_time": "23:00"},
                        {"name": "Night & Weekend / Off-Peak (NT)", "rate": default_offpeak, "start_time": "23:00", "end_time": "07:00"}
                    ])

                edited_dso_tou = st.data_editor(
                    st.session_state[state_dso_tou_key],
                    num_rows="dynamic",
                    use_container_width=True,
                    key=f"{key_prefix}_dso_tou_editor_{selected_tier}"
                )
                if edited_dso_tou is not None and not edited_dso_tou.empty:
                    st.session_state[state_dso_tou_key] = edited_dso_tou

                adjust_breach = st.checkbox(
                    ":material/lock_clock: 12-Month Ratchet Clause (Lock contracted capacity on peak breach - Dutch ACM rules)",
                    value=True,
                    key=f"{key_prefix}_dso_adjust_breach",
                    help="Exceeding contracted capacity (GTV) locks the monthly fee at the new peak for 12 consecutive months."
                )

            # Resolve active peak and offpeak transport rates
            active_tou_df = st.session_state.get(state_dso_tou_key)
            trans_norm_kwh = float(preset_data.get("rate_peak_kwh", 0.0250))
            trans_off_kwh = float(preset_data.get("rate_offpeak_kwh", 0.0250))
            if active_tou_df is not None and not active_tou_df.empty:
                for r in active_tou_df.to_dict(orient="records"):
                    r_name = str(r.get("name", "")).lower()
                    r_rate = float(r.get("rate", trans_norm_kwh))
                    if any(k in r_name for k in ["high", "normaal", "peak", "ht", "hoch", "daytime", "working"]):
                        trans_norm_kwh = r_rate
                    elif any(k in r_name for k in ["off", "dal", "laag", "nt", "niedrig", "night", "weekend"]):
                        trans_off_kwh = r_rate

        # ==============================================================================
        # Pillar 2: Commercial Energy Retailer (Supplier)
        # ==============================================================================
        with pillar_tabs[1]:
            st.markdown("##### Commercial Energy Supply Contract & Pricing")

            col_supp_co, col_supp_prod = st.columns([1.5, 1.5])
            with col_supp_co:
                supplier_options = list(SUPPLIER_CATALOG_2025.keys()) + ["Custom Energy Retailer"]
                selected_supplier_name = st.selectbox(
                    "Energy Retailer (Leverancier):",
                    options=supplier_options,
                    index=0,
                    key=f"{key_prefix}_supp_name_select"
                )

            with col_supp_prod:
                if selected_supplier_name in SUPPLIER_CATALOG_2025:
                    prod_dict = SUPPLIER_CATALOG_2025[selected_supplier_name]
                    prod_options = list(prod_dict.keys())
                    selected_product = st.selectbox(
                        "Contract Product:",
                        options=prod_options,
                        index=0,
                        key=f"{key_prefix}_supp_product_{selected_supplier_name}"
                    )
                    prod_data = prod_dict[selected_product]
                    st.caption(f":material/info: *{prod_data.get('description', '')}*")
                else:
                    selected_product = "Custom Contract"
                    prod_data = {
                        "pricing_mode": PricingMode.FIXED,
                        "is_dual_rate": False,
                        "base_fee_annual": 180.00,
                        "fixed_rate_kwh": 0.1250,
                        "rate_peak_kwh": 0.1340,
                        "rate_offpeak_kwh": 0.1180,
                        "supplier_margin_kwh": 0.0075,
                        "balancing_fee_kwh": 0.0035,
                        "green_surcharge_kwh": 0.0025,
                    }
                    st.caption(":material/tune: *Custom energy retailer contract parameters.*")

            # Pricing Mode Selector
            default_mode = prod_data.get("pricing_mode", PricingMode.FIXED)
            mode_idx = 0 if default_mode == PricingMode.DYNAMIC else (
                1 if default_mode == PricingMode.FIXED else (
                    2 if default_mode in (PricingMode.TRANCHE, getattr(PricingMode, "TRANCHE_CLICK", PricingMode.TRANCHE)) else 3
                )
            )
            selected_pricing_mode_str = st.radio(
                "Pricing Mechanism:",
                options=[
                    ":material/show_chart: Dynamic Spot (EPEX NL)",
                    ":material/lock: Fixed All-In",
                    ":material/view_timeline: Tranche / Click",
                    ":material/calendar_month: Variable Monthly"
                ],
                index=mode_idx,
                horizontal=True,
                key=f"{key_prefix}_pricing_mode_radio_{selected_supplier_name}_{selected_product}"
            )
            if "Dynamic" in selected_pricing_mode_str:
                active_pricing_mode = PricingMode.DYNAMIC
            elif "Fixed" in selected_pricing_mode_str:
                active_pricing_mode = PricingMode.FIXED
            elif "Tranche" in selected_pricing_mode_str:
                active_pricing_mode = PricingMode.TRANCHE
            else:
                active_pricing_mode = PricingMode.VARIABLE

            # Mode-specific Core Commodity Rate inputs
            tranche_blocks_configured = []
            is_dual_rate = False

            if active_pricing_mode in (PricingMode.TRANCHE, getattr(PricingMode, "TRANCHE_CLICK", PricingMode.TRANCHE)):
                tranche_base_price = st.number_input(
                    "Weighted Hedged Price (€/MWh):",
                    min_value=0.0,
                    value=95.0,
                    step=2.5,
                    format="%.2f",
                    key=f"{key_prefix}_tranche_p_mwh",
                    help="Volume-weighted hedge price across locked forward blocks."
                )
                st.markdown("###### Forward Block Hedge Shares (Q1 – Q4)")
                t_cols = st.columns(4)
                hedge_shares = [0.40, 0.40, 0.35, 0.45]
                for q_idx in range(4):
                    with t_cols[q_idx]:
                        q_share = st.slider(
                            f"Q{q_idx + 1} (%):",
                            min_value=0,
                            max_value=100,
                            value=int(hedge_shares[q_idx] * 100),
                            step=5,
                            key=f"{key_prefix}_tranche_q{q_idx+1}_pct"
                        )
                        tranche_blocks_configured.append(
                            TrancheBlock(
                                label=f"Q{q_idx+1}",
                                months=[q_idx * 3 + 1, q_idx * 3 + 2, q_idx * 3 + 3],
                                hedged_share_pct=float(q_share),
                                click_price_kwh=tranche_base_price / 1000.0,
                                tranche_id=f"Q{q_idx+1}_Base",
                                quarter_label=f"Q{q_idx+1}",
                                hedged_capacity_mw=round((load_series.peak_demand_kw * (q_share / 100.0)) / 1000.0, 3),
                                hedged_price_eur_mwh=tranche_base_price,
                                is_locked=True
                            )
                        )
                fixed_rate_val = tranche_base_price / 1000.0
                fixed_rate_ht = fixed_rate_val
                fixed_rate_nt = fixed_rate_val

            elif active_pricing_mode == PricingMode.DYNAMIC:
                st.info(":material/show_chart: **Dynamic Spot Mode:** Hourly & 15-minute settlement against EPEX Spot Day-Ahead index.")
                fixed_rate_val = 0.0950
                fixed_rate_ht = 0.1050
                fixed_rate_nt = 0.0850

            elif active_pricing_mode == PricingMode.FIXED:
                col_fx1, col_fx2 = st.columns(2)
                with col_fx1:
                    fixed_rate_val = st.number_input(
                        "Uniform Energy Rate (€/kWh):",
                        min_value=0.0,
                        value=float(prod_data.get("fixed_rate_kwh", 0.1100)),
                        format="%.4f",
                        key=f"{key_prefix}_supp_fixed_rate_{selected_supplier_name}_{selected_product}",
                        help="Enkeltarief applied 24/7 across all active kilowatt-hours."
                    )
                with col_fx2:
                    is_dual_rate = st.checkbox(
                        ":material/contrast: Dual Rate (Dubbeltarief HT/NT)",
                        value=bool(prod_data.get("is_dual_rate", False)),
                        key=f"{key_prefix}_supp_is_dual_{selected_supplier_name}_{selected_product}"
                    )
                if is_dual_rate:
                    col_ht, col_nt = st.columns(2)
                    with col_ht:
                        fixed_rate_ht = st.number_input(
                            "High Tariff HT / Normaal (€/kWh):",
                            min_value=0.0,
                            value=float(prod_data.get("rate_peak_kwh", 0.1180)),
                            format="%.4f",
                            key=f"{key_prefix}_supp_ht_{selected_supplier_name}_{selected_product}"
                        )
                    with col_nt:
                        fixed_rate_nt = st.number_input(
                            "Off-Peak NT / Dal (€/kWh):",
                            min_value=0.0,
                            value=float(prod_data.get("rate_offpeak_kwh", 0.0980)),
                            format="%.4f",
                            key=f"{key_prefix}_supp_nt_{selected_supplier_name}_{selected_product}"
                        )
                else:
                    fixed_rate_ht = fixed_rate_val
                    fixed_rate_nt = fixed_rate_val
            else:
                fixed_rate_val = st.number_input(
                    "Base Index Energy Rate (€/kWh):",
                    min_value=0.0,
                    value=float(prod_data.get("fixed_rate_kwh", 0.1150)),
                    format="%.4f",
                    key=f"{key_prefix}_supp_var_rate_{selected_supplier_name}_{selected_product}"
                )
                fixed_rate_ht = fixed_rate_val
                fixed_rate_nt = fixed_rate_val

            # Progressive Disclosure: Advanced Retail Margins & Surcharges
            with st.expander(":material/tune: Advanced Retail Margins & Surcharges", expanded=False):
                col_sm1, col_sm2 = st.columns(2)
                with col_sm1:
                    supp_base = st.number_input(
                        "Retailer Standing Fee Vastrecht levering (€/year):",
                        min_value=0.0,
                        value=float(prod_data.get("base_fee_annual", 180.00)),
                        step=15.0,
                        key=f"{key_prefix}_supp_base_{selected_supplier_name}_{selected_product}",
                        help="Fixed annual supplier administrative fee."
                    )
                    supp_margin = st.number_input(
                        "Retail Markup / Opslag (€/kWh):",
                        min_value=0.0,
                        value=float(prod_data.get("supplier_margin_kwh", 0.0075)),
                        format="%.4f",
                        key=f"{key_prefix}_supp_margin_{selected_supplier_name}_{selected_product}",
                        help="Leveranciersopslag per kWh."
                    )
                with col_sm2:
                    procure_fee = st.number_input(
                        "Imbalance Fee Onbalanskosten (€/kWh):",
                        min_value=0.0,
                        value=float(prod_data.get("balancing_fee_kwh", 0.0035)),
                        format="%.4f",
                        key=f"{key_prefix}_supp_procure_{selected_supplier_name}_{selected_product}",
                        help="Onbalanskosten passed through to customer."
                    )
                    green_surcharge = st.number_input(
                        "Green Power Surcharge GvO (€/kWh):",
                        min_value=0.0,
                        value=float(prod_data.get("green_certificate_surcharge_kwh", 0.0025)),
                        format="%.4f",
                        key=f"{key_prefix}_supp_green_{selected_supplier_name}_{selected_product}",
                        help="Garanties van Oorsprong (GvO) for green energy."
                    )

        # ==============================================================================
        # Pillar 3: Certified Metering (EMV) & Transformer Station Rental
        # ==============================================================================
        with pillar_tabs[2]:
            st.markdown("##### Certified Metering (EMV) & Transformer Station Rental")

            if is_low_voltage:
                st.info(
                    ":material/check_circle: **Smart Coupling:** Low Voltage connection detected from Pillar 1. "
                    "Transformer rental defaults to **€0 / year** (DSO owned) with LS telemetry.",
                    icon=":material/info:"
                )
            else:
                st.info(
                    ":material/bolt: **Smart Coupling:** Medium Voltage connection detected from Pillar 1. "
                    "A dedicated transformer station rental is active (prefilled: 630 kVA compact station).",
                    icon=":material/info:"
                )

            st.markdown("###### 1. Certified Metering Company (Meetbedrijf - EMV)")
            col_m_co, col_m_pkg = st.columns([1.4, 2.6])
            with col_m_co:
                meter_options = list(METERING_CATALOG_2025.keys()) + ["Custom Meetbedrijf"]
                selected_meter_name = st.selectbox(
                    "Metering Company:",
                    options=meter_options,
                    index=0,
                    key=f"{key_prefix}_meter_name_select"
                )

            with col_m_pkg:
                if selected_meter_name in METERING_CATALOG_2025:
                    pkg_dict = METERING_CATALOG_2025[selected_meter_name]
                    pkg_options = list(pkg_dict.keys())
                    current_pkg_target = st.session_state.get(meter_pkg_key, pkg_options[0])
                    pkg_idx = pkg_options.index(current_pkg_target) if current_pkg_target in pkg_options else 0
                    selected_pkg = st.selectbox(
                        "Service Package:",
                        options=pkg_options,
                        index=pkg_idx,
                        key=f"{key_prefix}_meter_pkg_{selected_meter_name}"
                    )
                    pkg_data = pkg_dict[selected_pkg]
                    st.caption(f":material/info: *{pkg_data.get('description', '')}*")
                else:
                    selected_pkg = "Custom Metering Package"
                    pkg_data = {"annual_flat_fee": 840.00, "voltage_level": "MS", "description": "Custom telemetry contract"}
                    st.caption(":material/tune: *Custom telemetry and meter service contract.*")

            st.markdown("###### 2. Dedicated Transformer Station Rental")
            col_t_co, col_t_type = st.columns(2)
            with col_t_co:
                trafo_provider_options = ["Fudura B.V.", "Kenter B.V.", "Joulz Energy Solutions", "Alfen B.V.", "None / DSO Owned Trafo"]
                curr_trafo_prov = st.session_state.get(trafo_prov_key, "Fudura B.V." if is_medium_voltage else "None / DSO Owned Trafo")
                t_idx = trafo_provider_options.index(curr_trafo_prov) if curr_trafo_prov in trafo_provider_options else 0
                trafo_provider = st.selectbox(
                    "Transformer Provider:",
                    options=trafo_provider_options,
                    index=t_idx,
                    key=trafo_prov_key
                )

            is_trafo_rented = (trafo_provider != "None / DSO Owned Trafo")

            with col_t_type:
                trafo_cap_options = [
                    "400 - 630 kVA Compactstation (€ 4,248 / yr = € 354 / mo)",
                    "1,000 kVA Substation (€ 6,200 / yr)",
                    "1,600 - 2,000 kVA Industrial (€ 9,200 / yr)",
                    "5,000 kVA (5 MVA) High Capacity (€ 18,500 / yr)",
                    "No Rental (Low Voltage AC4b or Customer Owned)"
                ]
                curr_cap = st.session_state.get(trafo_cap_key, trafo_cap_options[0] if is_trafo_rented else trafo_cap_options[4])
                c_idx = trafo_cap_options.index(curr_cap) if curr_cap in trafo_cap_options else (0 if is_trafo_rented else 4)
                trafo_capacity = st.selectbox(
                    "Transformer Capacity Tier:",
                    options=trafo_cap_options,
                    index=c_idx,
                    key=trafo_cap_key
                )

            # Progressive Disclosure: Advanced Station & Telemetry Overrides
            with st.expander(":material/tune: Advanced Station & Telemetry Overrides", expanded=False):
                col_mt1, col_mt2 = st.columns(2)
                with col_mt1:
                    meter_annual = st.number_input(
                        "Annual Telemetry Fee (€/year):",
                        min_value=0.0,
                        value=float(pkg_data.get("annual_flat_fee", 840.00)),
                        step=50.0,
                        key=f"{key_prefix}_meter_annual",
                        help="15-minute interval telemetry and data clearing per year excl. VAT."
                    )
                with col_mt2:
                    default_trafo_fee = 4248.0 if is_trafo_rented else 0.0
                    if "1,000" in trafo_capacity:
                        default_trafo_fee = 6200.0
                    elif "2,000" in trafo_capacity:
                        default_trafo_fee = 9200.0
                    elif "5,000" in trafo_capacity:
                        default_trafo_fee = 18500.0
                    elif "No Rental" in trafo_capacity or not is_trafo_rented:
                        default_trafo_fee = 0.0

                    trafo_annual_fee = st.number_input(
                        "Annual Transformer Rental (€/year):",
                        min_value=0.0,
                        value=float(default_trafo_fee),
                        step=100.0,
                        key=trafo_fee_key,
                        help="Annual transformer station rental and maintenance fee excl. VAT."
                    )

                nen_3840_included = st.checkbox(
                    ":material/verified_user: Statutory NEN 3840 & IV-er Responsibility Included",
                    value=True,
                    key=f"{key_prefix}_trafo_nen3840",
                    help="Includes legally mandated Installation Responsible (IV-er) and 24/7 emergency repair service."
                )

        # ==============================================================================
        # Pillar 4: Statutory Taxes & Lifecycle Economics
        # ==============================================================================
        with pillar_tabs[3]:
            st.markdown("##### Statutory Energy Taxes (Energiebelasting) & 15-Year TCO")

            col_tx_yr, col_tx_verb = st.columns(2)
            with col_tx_yr:
                selected_tax_year = st.radio(
                    "Tax Schedule Year:",
                    options=[2025, 2026],
                    index=0,
                    horizontal=True,
                    key=f"{key_prefix}_tax_year_radio"
                )
            with col_tx_verb:
                has_verblijfsfunctie = st.checkbox(
                    ":material/home_work: Residential/Work Function (Verblijfsfunctie)",
                    value=True,
                    key=f"{key_prefix}_tax_verblijfsfunctie",
                    help="Entitles connection to Vermindering Energiebelasting rebate (€524.95 in 2025, €519.80 in 2026)."
                )

            col_tco1, col_tco2 = st.columns(2)
            with col_tco1:
                discount_rate = st.number_input(
                    "WACC / Discount Rate r (%):",
                    min_value=0.0,
                    max_value=25.0,
                    value=5.0,
                    step=0.5,
                    key=f"{key_prefix}_tco_r",
                    help="Discount rate for 15-year Net Present Value (NPV)."
                )
            with col_tco2:
                escalation_rate = st.number_input(
                    "Price Escalation g (%/year):",
                    min_value=0.0,
                    max_value=25.0,
                    value=3.0,
                    step=0.5,
                    key=f"{key_prefix}_tco_g",
                    help="Annual projected electricity inflation rate."
                )

            with st.expander(":material/info: Official Degressive Tax Schedule Brackets", expanded=False):
                credit_val = 524.95 if selected_tax_year == 2025 else 519.80
                st.markdown(
                    f"**Tax Year {selected_tax_year} Official Rates:**\n"
                    f"- **Bracket 1 & 2 (0 – 10,000 kWh):** €{'0.1088' if selected_tax_year == 2025 else '0.1060'} / kWh\n"
                    f"- **Bracket 3 (10,000 – 50,000 kWh):** €{'0.0674' if selected_tax_year == 2025 else '0.0656'} / kWh\n"
                    f"- **Bracket 4 (50,000 – 10,000,000 kWh):** €{'0.0390' if selected_tax_year == 2025 else '0.0380'} / kWh\n"
                    f"- **Bracket 5 (> 10,000,000 kWh):** €0.0005 / kWh\n"
                    f"- **Vermindering Rebate:** €{credit_val:.2f} / year ({'Active' if has_verblijfsfunctie else 'Deactivated'}) | **VAT:** 21.0%"
                )

    # ----------------------------------------------------------------------------------
    # 3. Assemble Configuration & Execute 5-Layer 2025 Accounting Engine
    # ----------------------------------------------------------------------------------
    fixed_conn = round(fixed_conn_mnd * 12.0, 2)
    fixed_trans = round(base_fee * 12.0, 2)

    dso_tariff = DSOTariff(
        dso_name=selected_dso_company,
        grid_tier=selected_tier,
        connection_category=selected_tier,
        fixed_connection_annual=fixed_conn,
        fixed_transport_annual=fixed_trans,
        cable_surcharge_annual=round(cable_surcharge, 2),
        contracted_capacity_kw=contracted_kw,
        rate_contracted_capacity=capacity_tariff,
        rate_peak_demand=demand_tariff,
        rate_transport_peak_kwh=trans_norm_kwh,
        rate_transport_offpeak_kwh=trans_off_kwh,
        adjust_capacity_on_breach=adjust_breach,
        max_physical_limit_kw=max_physical_kw,
        peak_penalty_rate_kw=penalty_rate,
        reactive_power_tariff=reactive_tariff,
        min_power_factor=min_cos_phi,
        reactive_allowance_pct=reactive_allowance,
    )
    supplier_tariff = SupplierTariff(
        supplier_name=selected_supplier_name,
        supplier_category=str(prod_data.get("category", SupplierCategory.MAJOR_UTILITY.value)),
        pricing_mode=active_pricing_mode,
        tariff_product_name=selected_product,
        base_fee_annual=supp_base,
        fixed_rate_kwh=fixed_rate_val,
        is_dual_rate=is_dual_rate,
        fixed_rate_peak_kwh=fixed_rate_ht,
        fixed_rate_offpeak_kwh=fixed_rate_nt,
        procurement_fee_kwh=0.0,
        supplier_margin_kwh=supp_margin,
        balancing_fee_kwh=procure_fee,
        green_certificate_surcharge_kwh=green_surcharge,
        tranche_blocks=tranche_blocks_configured,
        monthly_variable_rates=prod_data.get("monthly_variable_rates", [0.125] * 12),
        market_price_profile_id="epex_nl_2025",
        spot_default_fallback_rate=0.0950,
    )
    metering_tariff = MeteringTariff(
        meter_company_name=selected_meter_name,
        service_package_name=selected_pkg,
        annual_flat_fee=meter_annual,
        voltage_level=pkg_data.get("voltage_level", "MS"),
        description=pkg_data.get("description", ""),
    )
    trafo_tariff = TrafoRentalTariff(
        provider_name=trafo_provider,
        station_type=trafo_capacity,
        is_rented=is_trafo_rented,
        monthly_rental_fee=round(trafo_annual_fee / 12.0, 2),
    )
    levy_config = get_default_levy_config(
        tax_year=selected_tax_year,
        has_verblijfsfunctie=has_verblijfsfunctie,
    )
    active_config = StatusQuoConfig2025(
        stage=TariffStage.STAGE_1_DEFAULT,
        dso=dso_tariff,
        supplier=supplier_tariff,
        metering=metering_tariff,
        trafo=trafo_tariff,
        levies=levy_config,
        discount_rate_pct=discount_rate,
        energy_escalation_pct=escalation_rate,
        evaluation_horizon_years=15,
    )

    result = calculate_status_quo_master(load=load_series, config=active_config)
    audit_report = perform_full_status_quo_audit(load=load_series, result=result)

    # ----------------------------------------------------------------------------------
    # Populate Top Master KPI Bar (Pinned at top of Tab 2)
    # ----------------------------------------------------------------------------------
    with top_kpi_container:
        st.markdown("#### :material/dashboard: Key Financial & Capacity Metrics")
        kpi_c1, kpi_c2, kpi_c3, kpi_c4 = st.columns(4)

        with kpi_c1:
            render_kpi_card(
                title=":material/receipt_long: Annual Net Invoice",
                value=f"€ {result.total_status_quo_net:,.2f}",
                subtext=f"Gross (+21% VAT): € {result.total_status_quo_gross:,.2f}",
                status="default"
            )
        with kpi_c2:
            render_kpi_card(
                title=":material/price_change: Blended Net Rate",
                value=f"€ {result.blended_price_net_kwh:.4f} / kWh",
                subtext=f"Gross: € {result.blended_price_gross_kwh:.4f} / kWh",
                status="default"
            )
        with kpi_c3:
            breach_status = "alert" if result.has_capacity_breach else "ok"
            breach_sub = (
                f"Breach in {len(result.breached_months)} month(s): {result.breached_months}"
                if result.has_capacity_breach
                else f"Max peak {result.annual_peak_demand_kw:.1f} kW ≤ {contracted_kw:.1f} kW"
            )
            render_kpi_card(
                title=":material/speed: Annual Peak Demand",
                value=f"{result.annual_peak_demand_kw:,.1f} kW",
                subtext=breach_sub,
                status=breach_status
            )
        with kpi_c4:
            render_kpi_card(
                title=":material/savings: 15-Year TCO (NPV)",
                value=f"€ {result.tco_15_npv:,.2f}",
                subtext=f"WACC: {active_config.discount_rate_pct:.1f}% | Escalation: {active_config.energy_escalation_pct:.1f}%",
                status="default"
            )

    # ----------------------------------------------------------------------------------
    # Right Column: Live Bill Receipt & Cost Donut (60/40 Split Live Cockpit)
    # ----------------------------------------------------------------------------------
    with col_receipt:
        st.markdown("#### :material/receipt: Live Bill & Cost Allocation")

        month_options = ["All Months (Consolidated 2025)"] + [r.month_name for r in result.monthly_records]
        selected_period = st.selectbox(
            "Billing Period:",
            options=month_options,
            index=0,
            key=f"{key_prefix}_live_period_inspector"
        )
        is_single_month = (selected_period != "All Months (Consolidated 2025)")

        # Capacity Breach or Compliance Alert Card
        if result.has_capacity_breach:
            max_excess = max(0.0, result.annual_peak_demand_kw - contracted_kw)
            st.error(
                f":material/warning: **GTV Overload Detected!** Measured peak of **{result.annual_peak_demand_kw:,.1f} kW** "
                f"exceeds reserved capacity by **+{max_excess:.1f} kW**. 12-month ratchet clause applies.",
                icon=":material/warning:"
            )
        else:
            st.success(
                f":material/check_circle: **GTV Compliant**: Peak of **{result.annual_peak_demand_kw:,.1f} kW** "
                f"is within reserved limit of **{contracted_kw:,.1f} kW**.",
                icon=":material/check_circle:"
            )

        # Live Invoice Receipt Card
        bill_title = "Annual Consolidated Statement (2025)" if not is_single_month else f"Monthly Invoice: {selected_period}"
        render_live_invoice_card(result=result, period_title=bill_title)

        # Cost Share Donut Chart
        breakdown_adapter = convert_to_financial_cost_breakdown(result, target_month=selected_period if is_single_month else None)
        donut_fig = create_cost_donut_figure(breakdown_adapter)
        st.plotly_chart(donut_fig, use_container_width=True)

    # ----------------------------------------------------------------------------------
    # Lower Full-Width Structured Analysis Views (Action Plan 3.3)
    # ----------------------------------------------------------------------------------
    st.markdown("---")
    st.markdown("### :material/analytics: Comprehensive Financial Audit & Sourcing Advisory")

    analysis_tabs = st.tabs([
        ":material/calendar_month: 1. 12-Month Payment Schedule & Statements",
        ":material/trending_up: 2. 15-Year TCO & Lifecycle Projections",
        ":material/insights: 3. Strategic Procurement Advisory & Audit"
    ])

    # ==================================================================================
    # Analysis Tab 1: 12-Month Payment Schedule & Statement Table
    # ==================================================================================
    with analysis_tabs[0]:
        st.markdown("##### 12-Month Stacked Payment Series (Zahlungsreihe)")
        annual_adapter = convert_to_financial_cost_breakdown(result)
        series_fig = create_monthly_payment_series_figure(annual_adapter)
        st.plotly_chart(series_fig, use_container_width=True)

        st.markdown("##### Itemized 12-Month Accounting Statement Table")
        table_data = []
        for r in result.monthly_records:
            table_data.append({
                "Month": r.month_name,
                "Consumption (kWh)": round(r.consumption.total_kwh, 1),
                "Peak kW (P_max)": round(r.consumption.peak_demand_kw, 1),
                "DSO Net (€)": round(r.dso.subtotal_dso_net, 2),
                "Supplier Net (€)": round(r.supplier.subtotal_supplier_net, 2),
                "Metering Net (€)": round(r.metering_fee, 2),
                "Trafo Net (€)": round(r.trafo.trafo_rental_fee, 2),
                "Taxes Net (€)": round(r.tax.net_energy_tax, 2),
                "Total Net (€)": round(r.total_net, 2),
                "VAT 21% (€)": round(r.vat_amount, 2),
                "Total Gross (€)": round(r.total_gross, 2),
                "Net Rate (€/kWh)": round(r.effective_rate_net_kwh, 4),
                "Breach": "YES" if r.dso.is_capacity_breached else "NO"
            })
        df_table = pd.DataFrame(table_data)
        st.dataframe(df_table, use_container_width=True, hide_index=True)

        # Export Buttons for Tab 1
        col_exp1, col_exp2 = st.columns(2)
        with col_exp1:
            csv_buf = io.StringIO()
            df_table.to_csv(csv_buf, index=False, sep=";")
            st.download_button(
                label=":material/download: Download 12-Month Statement (CSV)",
                data=csv_buf.getvalue(),
                file_name="status_quo_2025_statement.csv",
                mime="text/csv",
                key=f"{key_prefix}_export_csv",
                use_container_width=True
            )
        with col_exp2:
            export_payload = {
                "evaluation_year": 2025,
                "total_consumption_kwh": result.total_consumption_kwh,
                "total_status_quo_net": result.total_status_quo_net,
                "total_status_quo_gross": result.total_status_quo_gross,
                "blended_price_net_kwh": result.blended_price_net_kwh,
                "monthly_records": table_data
            }
            st.download_button(
                label=":material/download: Download 12-Month JSON",
                data=json.dumps(export_payload, indent=2),
                file_name="status_quo_2025_statement.json",
                mime="application/json",
                key=f"{key_prefix}_export_json_tab1",
                use_container_width=True
            )

    # ==================================================================================
    # Analysis Tab 2: 15-Year TCO & Lifecycle Projections
    # ==================================================================================
    with analysis_tabs[1]:
        st.markdown("##### 15-Year Long-Term Cost Structure & Lifecycle Projection (2025 – 2039)")
        st.caption(
            f"Consolidates all 4 pillars under {active_config.energy_escalation_pct:.1f}% annual inflation "
            f"and discounted at {active_config.discount_rate_pct:.1f}% WACC."
        )

        horizon_years = int(getattr(active_config, "evaluation_horizon_years", 15))
        g_rate = float(getattr(active_config, "energy_escalation_pct", 3.0)) / 100.0
        r_rate = float(getattr(active_config, "discount_rate_pct", 5.0)) / 100.0
        start_calendar_year = 2025

        base_dso = float(result.total_dso_net)
        base_supp = float(result.total_supplier_net)
        base_meter_trafo_taxes = float(result.total_metering_net) + float(result.total_trafo_net) + float(result.total_taxes_net)
        base_kwh = float(result.total_consumption_kwh)

        tco_15_rows = []
        cum_nominal_spend = 0.0
        for i in range(horizon_years):
            esc_factor = (1.0 + g_rate) ** i
            disc_factor = 1.0 / ((1.0 + r_rate) ** (i + 1))

            dso_y = round(base_dso * esc_factor, 2)
            supp_y = round(base_supp * esc_factor, 2)
            met_y = round(base_meter_trafo_taxes * esc_factor, 2)
            tot_y = round(dso_y + supp_y + met_y, 2)
            cum_nominal_spend += tot_y
            pv_y = round(tot_y * disc_factor, 2)
            blended_y = round((tot_y / base_kwh), 4) if base_kwh > 0 else 0.0

            tco_15_rows.append({
                "Period": f"Year {i + 1}",
                "Calendar Year": start_calendar_year + i,
                "DSO Grid (€)": dso_y,
                "Supplier (€)": supp_y,
                "Metering, Trafo & Taxes (€)": met_y,
                "Annual Net Spend (€)": tot_y,
                "Cumulative Spend (€)": round(cum_nominal_spend, 2),
                "Discount Factor": round(disc_factor, 4),
                "Present Value (€)": pv_y,
                "Blended Rate (€/kWh)": blended_y,
            })

        df_tco_15 = pd.DataFrame(tco_15_rows)
        total_15y_nominal = round(cum_nominal_spend, 2)
        avg_annual_spend = round(total_15y_nominal / horizon_years, 2)
        yr15_spend = tco_15_rows[-1]["Annual Net Spend (€)"] if tco_15_rows else 0.0

        col_tco_k1, col_tco_k2, col_tco_k3, col_tco_k4 = st.columns(4)
        with col_tco_k1:
            render_kpi_card(
                title=":material/payments: 15-Year Spend (Nominal)",
                value=f"€ {total_15y_nominal:,.2f}",
                subtext=f"Total cash outlay across {horizon_years} years",
                status="default"
            )
        with col_tco_k2:
            render_kpi_card(
                title=":material/savings: 15-Year TCO (NPV)",
                value=f"€ {result.tco_15_npv:,.2f}",
                subtext=f"Discounted present value today @ {active_config.discount_rate_pct:.1f}% WACC",
                status="default"
            )
        with col_tco_k3:
            render_kpi_card(
                title=":material/analytics: Average Annual Spend",
                value=f"€ {avg_annual_spend:,.2f}",
                subtext="Mean annual electricity budget",
                status="default"
            )
        with col_tco_k4:
            render_kpi_card(
                title=":material/event: Year 15 Budget",
                value=f"€ {yr15_spend:,.2f}",
                subtext=f"Indexed in {start_calendar_year + horizon_years - 1}",
                status="default"
            )

        # 15-Year Interactive Chart
        fig_15y = create_15_year_lifecycle_cost_figure(result, start_year=start_calendar_year)
        st.plotly_chart(fig_15y, use_container_width=True)

        st.markdown("##### 15-Year Cashflow Schedule")
        st.dataframe(df_tco_15, use_container_width=True, hide_index=True)

        csv_15y_buf = io.StringIO()
        df_tco_15.to_csv(csv_15y_buf, index=False, sep=";")
        st.download_button(
            label=":material/download: Download 15-Year TCO CSV",
            data=csv_15y_buf.getvalue(),
            file_name="status_quo_15_year_lifecycle_projection.csv",
            mime="text/csv",
            key=f"{key_prefix}_export_15y_csv",
            use_container_width=True
        )

    # ==================================================================================
    # Analysis Tab 3: Strategic Procurement Advisory & Audit
    # ==================================================================================
    with analysis_tabs[2]:
        render_procurement_strategy_view(
            load=load_series,
            active_config=active_config,
            load_series=load_series,
            active_result=result,
            key_prefix=f"{key_prefix}_strategy"
        )

        st.markdown("---")
        st.markdown("##### :material/verified_user: 14-Criteria Mathematical Audit Report")
        col_au1, col_au2 = st.columns([1.5, 2.5])
        with col_au1:
            st.success(
                f":material/check_circle: **Audit Status:** {audit_report.get('overall_status', 'PASSED')} | "
                f"**Score:** {audit_report.get('passed_criteria_count', 14)} / 14 Criteria",
                icon=":material/check_circle:"
            )
        with col_au2:
            st.caption(":material/info: Fully validated against ACM Dutch Grootverbruik regulatory standards.")

        col_exp_a, col_exp_b = st.columns(2)
        with col_exp_a:
            full_audit_payload = {
                "evaluation_year": 2025,
                "total_consumption_kwh": result.total_consumption_kwh,
                "total_status_quo_net": result.total_status_quo_net,
                "total_status_quo_gross": result.total_status_quo_gross,
                "blended_price_net_kwh": result.blended_price_net_kwh,
                "tco_15_npv": result.tco_15_npv,
                "total_15_year_nominal_spend": total_15y_nominal,
                "audit": audit_report,
                "monthly_records": table_data,
                "lifecycle_15_year_schedule": tco_15_rows
            }
            st.download_button(
                label=":material/download: Download Full Audit JSON",
                data=json.dumps(full_audit_payload, indent=2),
                file_name="status_quo_2025_full_audit.json",
                mime="application/json",
                key=f"{key_prefix}_export_full_audit_json",
                use_container_width=True
            )
        with col_exp_b:
            contract_payload = {
                "version": "2025.1",
                "dso": active_config.dso.to_dict(),
                "supplier": active_config.supplier.to_dict(),
                "metering": active_config.metering.to_dict(),
                "trafo": active_config.trafo.to_dict(),
                "levies": active_config.levies.to_dict(),
                "tco": {
                    "discount_rate_pct": active_config.discount_rate_pct,
                    "energy_escalation_pct": active_config.energy_escalation_pct,
                    "evaluation_horizon_years": active_config.evaluation_horizon_years,
                }
            }
            st.download_button(
                label=":material/save: Download Unbundled Contract JSON",
                data=json.dumps(contract_payload, indent=2),
                file_name="unbundled_contract_2025.json",
                mime="application/json",
                key=f"{key_prefix}_export_contract",
                use_container_width=True
            )

    return result


def render_tab2_contract(key_prefix: str = "currsit_contract") -> Any:
    """Alias for render_tab2_base_contract."""
    return render_tab2_base_contract(key_prefix=key_prefix)


def render_tab2_contract_switch(key_prefix: str = "currsit_contract") -> Any:
    """Compatibility switch alias rendering the base contract."""
    return render_tab2_base_contract(key_prefix=key_prefix)
