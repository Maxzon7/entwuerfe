"""
========================================================================================
Status Quo 2025 Contract & Billing View (Currentsituation_sandbox/contract/view.py)
========================================================================================

Extended 3-Party unbundled electricity contract assessment view:
  1. Three dedicated actor sub-tabs:
     - Regulated Grid Operator (DSO: Enexis, Liander, Stedin official 2025 catalogs)
     - Energy Retailer (Supplier: Vattenfall, Eneco, Essent, Dynamic Spot / Fixed / Variable)
     - Certified Metering & Taxes (Meetbedrijf: Fudura, Joulz, Kenter + Levies & VAT)
  2. Time-of-Use (TOU) Segment Visualizer (HT vs NT breakdown & 24h diurnal schedule).
  3. Executive presentation layout (KPI cards, Cost Donut, 12-Month Payment Series,
     itemized statement table, export toolbar).
  4. 5-Layer 2025 Unbundled Accounting Engine with 14-criteria audit verification.
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
    Renders the Status Quo 2025 Electricity Contract Configuration & Accounting view.
    Includes 3 dedicated actor sub-tabs, TOU segment inspection, KPI cards, and audit battery.
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
    # 1. Three Dedicated Actor Sub-Tabs (DSO, Supplier, Metering & Taxes)
    # ----------------------------------------------------------------------------------
    st.markdown("### :material/account_tree: 4-Pillar Unbundled Market Actors & Sourcing Strategy")

    actor_tabs = st.tabs([
        ":material/grid_view: 1. Regulated Grid (DSO)",
        ":material/bolt: 2. Commercial Supplier",
        ":material/speed: 3. Metering & Trafo Rental",
        ":material/account_balance: 4. Statutory Taxes & Lifecycle",
        ":material/insights: 5. Procurement Strategy & Advisory"
    ])

    # ----------------------------------------------------------------------------------
    # Sub-Tab 1: Regulated Grid Operator (DSO)
    # ----------------------------------------------------------------------------------
    with actor_tabs[0]:
        st.markdown("##### Regulated Grid Connection & Transport Tariffs (Enexis / Liander / Stedin 2025)")

        col_dso_co, col_dso_tier = st.columns([1.5, 2.5])
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
                # Default selection heuristic: match facility peak power
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
                st.caption(":material/tune: *Fully customizable manual grid operator tariffs.*")

        # Reload / Always Reload options for default preset rates
        state_always_reload_key = f"{key_prefix}_dso_always_reload_{selected_dso_company}_{selected_tier}"
        always_reload = st.session_state.get(state_always_reload_key, False)

        reload_version_key = f"{key_prefix}_dso_version_{selected_dso_company}_{selected_tier}"
        form_version = st.session_state.get(reload_version_key, 0)

        r_col1, r_col2 = st.columns([2.5, 2.5])
        with r_col1:
            if st.button(
                ":material/restart_alt: Reload Preset Defaults",
                key=f"{key_prefix}_btn_reload_preset_{selected_dso_company}_{selected_tier}",
                use_container_width=True,
                help="Reset all values and TOU tables for this grid tier back to the original catalog defaults."
            ):
                st.session_state[reload_version_key] = form_version + 1
                # Clear stored widget states and data editor for this tier
                for k in list(st.session_state.keys()):
                    if f"{selected_dso_company}_{selected_tier}" in k or "dso_base_fee" in k or "dso_p_contract" in k or "dso_rate_" in k:
                        del st.session_state[k]
                st.rerun()

        with r_col2:
            always_reload = st.checkbox(
                ":material/sync: Always reload catalog defaults on tier switch",
                value=always_reload,
                key=state_always_reload_key,
                help="When enabled, switching tiers or companies automatically discards custom edits and reloads original catalog defaults."
            )

        # Dynamic session state key for DSO TOU rates matrix
        state_dso_tou_key = f"{key_prefix}_dso_tou_df_{selected_dso_company}_{selected_tier}_v{form_version}"
        if state_dso_tou_key not in st.session_state or always_reload:
            default_peak = float(preset_data.get("rate_peak_kwh", 0.0250))
            default_offpeak = float(preset_data.get("rate_offpeak_kwh", 0.0250))
            st.session_state[state_dso_tou_key] = pd.DataFrame([
                {"name": "Daytime / Working Hours (kWh hoch)", "rate": default_peak, "start_time": "07:00", "end_time": "23:00"},
                {"name": "Night & Weekend / Off-Peak (kWh niedrig)", "rate": default_offpeak, "start_time": "23:00", "end_time": "07:00"}
            ])

        # Pre-initialize penalty_rate to ensure availability across all execution paths
        penalty_rate = float(preset_data.get("peak_penalty_rate_kw", 0.0))

        with st.form(key=f"{key_prefix}_dso_contract_form_{selected_dso_company}_{selected_tier}_v{form_version}"):
            # ==============================================================================
            # 1. Grid Capacity & Fixed Fees
            # ==============================================================================
            st.subheader("1. Grid Capacity & Fixed Fees")

            dso_contract_name_default = f"{selected_dso_company} - {selected_tier} (2025)"
            contract_name_val = st.text_input(
                "Contract Name / Identifier:",
                value=dso_contract_name_default,
                key=f"{key_prefix}_dso_name_val_{selected_dso_company}_{selected_tier}_v{form_version}",
                help="Custom name or tariff identifier for the regulated grid operator contract."
            )

            c1, c2 = st.columns(2)
            with c1:
                curr_options = ["EUR", "USD", "GBP", "CHF", "ARS"]
                currency = st.selectbox(
                    "Currency:",
                    options=curr_options,
                    index=0,
                    key=f"{key_prefix}_dso_currency_v{form_version}"
                )
                # Connection Fee PAV (Periodieke aansluitvergoeding)
                pav_monthly_default = float(preset_data.get("fixed_connection_monthly", 57.73))
                fixed_conn_mnd = st.number_input(
                    "Connection Fee PAV (€/month):",
                    min_value=0.0,
                    value=pav_monthly_default,
                    step=5.0,
                    format="%.2f",
                    key=f"{key_prefix}_dso_pav_{selected_dso_company}_{selected_tier}_v{form_version}",
                    help="Periodieke aansluitvergoeding (PAV) per maand based on connection capacity (e.g. AC4b = €57.73/mo, AC5a = €160.57/mo)"
                )
                # Fixed Monthly Transport Admin Fee (Vastrecht transport)
                ann_standing_default = float(preset_data.get("vastrecht_annual", 52.54))
                monthly_standing_default = round(ann_standing_default / 12.0, 2)
                base_fee = st.number_input(
                    "Fixed Transport Admin Fee Vastrecht (€/month):",
                    min_value=0.0,
                    value=monthly_standing_default,
                    step=1.0,
                    format="%.2f",
                    key=f"{key_prefix}_dso_base_fee_{selected_dso_company}_{selected_tier}_v{form_version}",
                    help="Fixed standing charge for grid administration (Vastrecht transport €/month, official Liander €4.38/mo)"
                )
                contracted_kw = st.number_input(
                    "Contracted Grid Capacity GTV (kW):",
                    min_value=10.0,
                    max_value=20000.0,
                    value=float(max(50.0, round(load_series.peak_demand_kw * 1.05, 0))),
                    step=10.0,
                    format="%.1f",
                    key=f"{key_prefix}_dso_p_contract_{selected_dso_company}_{selected_tier}_v{form_version}",
                    help="Gecontracteerd Transportvermogen (GTV) reserved on the grid for your facility"
                )

            with c2:
                capacity_tariff = st.number_input(
                    "Contracted Capacity Rate GTV (€/kW/month):",
                    min_value=0.0,
                    value=float(preset_data.get("rate_contracted_monthly", 3.6567)),
                    step=0.01,
                    format="%.4f",
                    key=f"{key_prefix}_dso_rate_cap_{selected_dso_company}_{selected_tier}_v{form_version}",
                    help="Monthly fee billed per reserved kW (Capaciteitstarief GTV in €/kW/mo)"
                )
                demand_tariff = st.number_input(
                    "Monthly Peak Demand Rate (€/kW/month):",
                    min_value=0.0,
                    value=float(preset_data.get("rate_peak_monthly", 3.4600)),
                    step=0.01,
                    format="%.4f",
                    key=f"{key_prefix}_dso_rate_peak_{selected_dso_company}_{selected_tier}_v{form_version}",
                    help="Monthly fee billed per measured 15-minute maximum peak (Maandpiek in €/kW/mo)"
                )
                cable_surcharge = st.number_input(
                    "Cable Surcharge Meerlengte (€/year):",
                    min_value=0.0,
                    value=float(preset_data.get("cable_surcharge_annual", 0.0)),
                    step=50.0,
                    format="%.2f",
                    key=f"{key_prefix}_dso_cable_{selected_dso_company}_{selected_tier}_v{form_version}",
                    help="Meerlengte connection cable surcharge if connection cable > 25 meters"
                )
                max_physical_kw = st.number_input(
                    "Physical Connection / Trafo Limit (kW):",
                    min_value=10.0,
                    value=float(preset_data.get("max_physical_limit_kw", 1000.0)),
                    step=50.0,
                    format="%.1f",
                    key=f"{key_prefix}_dso_max_phys_{selected_dso_company}_{selected_tier}_v{form_version}",
                    help="Maximum physical electrical capacity limit of your transformer or main connection"
                )
                penalty_rate = st.number_input(
                    "Peak Overload Penalty Rate (€/kW):",
                    min_value=0.0,
                    value=float(preset_data.get("peak_penalty_rate_kw", 0.0)),
                    step=0.05,
                    format="%.4f",
                    key=f"{key_prefix}_dso_penalty_rate_{selected_dso_company}_{selected_tier}_v{form_version}",
                    help="Penalty fee per kW for exceeding contracted capacity (standard in international tariffs, €0.00 for Dutch standard ratchet)."
                )

            # ==============================================================================
            # 2. Reactive Power & Power Factor (Blindenergie)
            # ==============================================================================
            st.subheader("2. Reactive Power & Power Factor (Blindenergie)")
            q1, q2, q3 = st.columns(3)
            with q1:
                reactive_tariff = st.number_input(
                    "Reactive Power Rate (€/kVARh):",
                    min_value=0.0,
                    value=float(preset_data.get("reactive_tariff", 0.0188)),
                    step=0.005,
                    format="%.4f",
                    key=f"{key_prefix}_dso_reactive_{selected_dso_company}_{selected_tier}_v{form_version}",
                    help="Tariff for consumed reactive energy (Blindenergie €/kVARh)"
                )
            with q2:
                min_cos_phi = st.number_input(
                    "Target Power Factor (cos φ):",
                    min_value=0.50,
                    max_value=1.00,
                    value=float(preset_data.get("min_power_factor", 0.90)),
                    step=0.02,
                    format="%.2f",
                    key=f"{key_prefix}_dso_cosphi_{selected_dso_company}_{selected_tier}_v{form_version}",
                    help="Minimum required power factor (cos φ = 0.90) to avoid reactive charges"
                )
            with q3:
                reactive_allowance = st.number_input(
                    "Free Reactive Energy Allowance (% of kWh):",
                    min_value=0.0,
                    max_value=100.0,
                    value=float(preset_data.get("reactive_allowance_pct", 33.0)),
                    step=1.0,
                    format="%.1f",
                    key=f"{key_prefix}_dso_q_allow_{selected_dso_company}_{selected_tier}_v{form_version}",
                    help="Permitted free reactive energy as a percentage of active consumption (33%)"
                )

            # ==============================================================================
            # 3. Time-of-Use Electricity Rates (Working Hours vs. Off-Peak)
            # ==============================================================================
            st.subheader("3. Time-of-Use Electricity Rates (Working Hours vs. Off-Peak)")
            st.caption("Define Time-of-Use rate windows. The table supports adding and deleting rows:")

            edited_dso_tou = st.data_editor(
                st.session_state[state_dso_tou_key],
                num_rows="dynamic",
                use_container_width=True,
                column_config={
                    "name": st.column_config.TextColumn("Tariff Name", required=True),
                    "rate": st.column_config.NumberColumn(
                        f"Rate ({currency}/kWh)",
                        format="%.4f",
                        min_value=0.0,
                        step=0.0001,
                        required=True
                    ),
                    "start_time": st.column_config.TextColumn("Start Time (HH:MM)", required=True),
                    "end_time": st.column_config.TextColumn("End Time (HH:MM)", required=True)
                },
                key=f"{key_prefix}_dso_tou_editor_{selected_dso_company}_{selected_tier}_v{form_version}"
            )

            weekend_off_peak = st.checkbox(
                "Treat Weekends as Off-Peak (Apply Lowest Tariff)",
                value=True,
                key=f"{key_prefix}_dso_weekend_offpeak",
                help="Pas gedurende het gehele weekend het daltarief toe"
            )

            adjust_breach = st.checkbox(
                ":material/lock_clock: 12-Month Ratchet Clause: Peak exceedances lock contracted capacity for remaining 12 months (Dutch ACM rules)",
                value=True,
                key=f"{key_prefix}_dso_adjust_breach",
                help="Bij overschrijding van het gecontracteerde vermogen (GTV) wordt de contractcapaciteit voor de resterende 12 maanden vergrendeld op het nieuwe piekniveau."
            )

            submitted_dso = st.form_submit_button(
                "Save Grid Operator Tariff",
                icon=":material/save:",
                type="primary",
                use_container_width=True
            )

        if submitted_dso:
            if edited_dso_tou is not None and not edited_dso_tou.empty:
                st.session_state[state_dso_tou_key] = edited_dso_tou
            st.success(f"Grid Operator configuration saved: **{contract_name_val}**", icon=":material/check_circle:")

        # Extract active peak & offpeak rates from the TOU matrix for calculation pipeline
        active_tou_df = st.session_state[state_dso_tou_key]
        trans_norm_kwh = float(preset_data.get("rate_peak_kwh", 0.0250))
        trans_off_kwh = float(preset_data.get("rate_offpeak_kwh", 0.0250))
        if active_tou_df is not None and not active_tou_df.empty:
            rows = active_tou_df.to_dict(orient="records")
            for r in rows:
                r_name = str(r.get("name", "")).lower()
                r_rate = float(r.get("rate", trans_norm_kwh))
                if any(k in r_name for k in ["high", "normaal", "peak", "ht", "hoch", "daytime", "working"]):
                    trans_norm_kwh = r_rate
                elif any(k in r_name for k in ["off", "dal", "laag", "nt", "niedrig", "night", "weekend"]):
                    trans_off_kwh = r_rate

    # ----------------------------------------------------------------------------------
    # Sub-Tab 2: Energy Retailer (Supplier)
    # ----------------------------------------------------------------------------------
    with actor_tabs[1]:
        st.markdown("##### Commercial Energy Supply Contract (Commodity Rates & Retail Pricing)")

        # Row 1: Provider & Product Selector (Symmetrical 50% / 50%)
        col_supp_co, col_supp_prod = st.columns(2)
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
                    "Contract Product & Pricing Tier:",
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
                    "procurement_fee_kwh": 0.0,
                    "green_surcharge_kwh": 0.0,
                }
                st.caption(":material/tune: *Custom energy retailer contract parameters.*")

        st.markdown("---")

        # Row 2: Pricing Mechanism Selection
        default_mode = prod_data.get("pricing_mode", PricingMode.FIXED)
        mode_idx = 0 if default_mode == PricingMode.DYNAMIC else (
            1 if default_mode == PricingMode.FIXED else (
                2 if default_mode in (PricingMode.TRANCHE, getattr(PricingMode, "TRANCHE_CLICK", PricingMode.TRANCHE)) else 3
            )
        )
        selected_pricing_mode_str = st.radio(
            "Supplier Pricing Mechanism:",
            options=[
                ":material/show_chart: Dynamic Spot (EPEX Spot NL 2025)",
                ":material/lock: Fixed All-In Rate",
                ":material/view_timeline: Tranche / Click (Block Hedging + Spot)",
                ":material/calendar_month: Variable Monthly Rates"
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

        with st.form(key=f"{key_prefix}_supplier_form_{selected_supplier_name}_{selected_product}"):
            col_s_fee, col_s_option = st.columns(2)
            with col_s_fee:
                supp_base = st.number_input(
                    "Retailer Standing Fee Vastrecht levering (€/year):",
                    min_value=0.0,
                    value=float(prod_data.get("base_fee_annual", 180.00)),
                    step=15.0,
                    key=f"{key_prefix}_supp_base_{selected_supplier_name}_{selected_product}",
                    help="Fixed annual supplier administrative fee (Vastrecht levering per jaar excl. btw)."
                )

            with col_s_option:
                if active_pricing_mode == PricingMode.FIXED:
                    is_dual_rate = st.checkbox(
                        ":material/contrast: Dual Rate (Dubbeltarief: HT / NT)",
                        value=bool(prod_data.get("is_dual_rate", False)),
                        key=f"{key_prefix}_supp_is_dual_{selected_supplier_name}_{selected_product}",
                        help="Enable separate rates for daytime / working hours (HT) and night / weekends (NT)."
                    )
                elif active_pricing_mode in (PricingMode.TRANCHE, getattr(PricingMode, "TRANCHE_CLICK", PricingMode.TRANCHE)):
                    is_dual_rate = False
                    st.info(
                        ":material/view_timeline: **Tranche / Click Hedging:** Forward blocks locked "
                        "per quarter; remaining consumption settles against hourly EPEX Spot prices."
                    )
                elif active_pricing_mode == PricingMode.DYNAMIC:
                    is_dual_rate = False
                    st.info(
                        ":material/show_chart: **Dynamic Spot Mode:** Hourly & 15-minute settlement "
                        "against EPEX Spot Day-Ahead wholesale market prices."
                    )
                else:
                    is_dual_rate = False
                    st.info(
                        ":material/calendar_month: **Variable Mode:** 12 monthly rates applied "
                        "chronologically across the billing cycle."
                    )

            # 5-Component Rate Parameters Grid
            st.markdown("###### 5-Component Wholesale & Retail Supplier Rates")
            col_s1, col_s2, col_s3, col_s4 = st.columns(4)
            with col_s2:
                supp_margin = st.number_input(
                    "Retail Markup / Opslag (€/kWh):",
                    min_value=0.0,
                    value=float(prod_data.get("supplier_margin_kwh", 0.0075)),
                    format="%.4f",
                    key=f"{key_prefix}_supp_margin_{selected_supplier_name}_{selected_product}",
                    help="Leveranciersopslag per kWh (Dutch utility margin)."
                )
            with col_s3:
                procure_fee = st.number_input(
                    "Imbalance Fee Onbalanskosten (€/kWh):",
                    min_value=0.0,
                    value=float(prod_data.get("balancing_fee_kwh", 0.0035)),
                    format="%.4f",
                    key=f"{key_prefix}_supp_procure_{selected_supplier_name}_{selected_product}",
                    help="Onbalanskosten passed through to customer (typically €0.003 to €0.008/kWh)."
                )
            with col_s4:
                green_surcharge = st.number_input(
                    "Green Power Surcharge GvO (€/kWh):",
                    min_value=0.0,
                    value=float(prod_data.get("green_certificate_surcharge_kwh", 0.0025)),
                    format="%.4f",
                    key=f"{key_prefix}_supp_green_{selected_supplier_name}_{selected_product}",
                    help="Garanties van Oorsprong (GvO) for 100% Dutch green energy."
                )

            # Mode-specific Commodity Rate
            tranche_blocks_configured = []
            if active_pricing_mode in (PricingMode.TRANCHE, getattr(PricingMode, "TRANCHE_CLICK", PricingMode.TRANCHE)):
                with col_s1:
                    tranche_base_price = st.number_input(
                        "Weighted Hedged Price (€/MWh):",
                        min_value=0.0,
                        value=95.0,
                        step=2.5,
                        format="%.2f",
                        key=f"{key_prefix}_tranche_p_mwh",
                        help="Volume-weighted hedge price across locked forward blocks."
                    )
                st.markdown("###### Tranche / Click Block Hedge Configuration")
                t_cols = st.columns(4)
                hedge_shares = [0.40, 0.40, 0.35, 0.45]
                for q_idx in range(4):
                    with t_cols[q_idx]:
                        q_share = st.slider(
                            f"Q{q_idx + 1} Hedge (%):",
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
                avg_hedge_pct = sum((b.hedged_capacity_mw or 0.0) for b in tranche_blocks_configured) * 1000.0 / max(1.0, load_series.peak_demand_kw) * 100.0
                st.caption(f":material/check_circle: *Overall Forward Hedge: ~{avg_hedge_pct:.0f}% locked; remaining ~{100 - avg_hedge_pct:.0f}% exposed to EPEX Spot.*")
                fixed_rate_val = tranche_base_price / 1000.0
                fixed_rate_ht = fixed_rate_val
                fixed_rate_nt = fixed_rate_val

            elif active_pricing_mode == PricingMode.DYNAMIC:
                with col_s1:
                    st.info(":material/show_chart: Wholesale: EPEX Spot 15-min index")
                fixed_rate_val = 0.0950
                fixed_rate_ht = 0.1050
                fixed_rate_nt = 0.0850

            elif active_pricing_mode == PricingMode.FIXED:
                if is_dual_rate:
                    with col_s1:
                        fixed_rate_ht = st.number_input(
                            "High Tariff HT / Normaal (€/kWh):",
                            min_value=0.0,
                            value=float(prod_data.get("rate_peak_kwh", 0.1180)),
                            format="%.4f",
                            key=f"{key_prefix}_supp_ht_{selected_supplier_name}_{selected_product}",
                            help="Normaaltarief during working weekdays (07:00 – 23:00)."
                        )
                        fixed_rate_nt = st.number_input(
                            "Off-Peak NT / Dal (€/kWh):",
                            min_value=0.0,
                            value=float(prod_data.get("rate_offpeak_kwh", 0.0980)),
                            format="%.4f",
                            key=f"{key_prefix}_supp_nt_{selected_supplier_name}_{selected_product}",
                            help="Daltarief during nights (23:00 – 07:00) and weekends (24h)."
                        )
                    fixed_rate_val = fixed_rate_ht
                else:
                    with col_s1:
                        fixed_rate_val = st.number_input(
                            "Uniform Energy Rate (€/kWh):",
                            min_value=0.0,
                            value=float(prod_data.get("fixed_rate_kwh", 0.1100)),
                            format="%.4f",
                            key=f"{key_prefix}_supp_fixed_rate_{selected_supplier_name}_{selected_product}",
                            help="Enkeltarief applied 24/7 across all active kilowatt-hours."
                        )
                    fixed_rate_ht = fixed_rate_val
                    fixed_rate_nt = fixed_rate_val
            else:
                with col_s1:
                    fixed_rate_val = st.number_input(
                        "Base Index Energy Rate (€/kWh):",
                        min_value=0.0,
                        value=float(prod_data.get("fixed_rate_kwh", 0.1150)),
                        format="%.4f",
                        key=f"{key_prefix}_supp_var_rate_{selected_supplier_name}_{selected_product}",
                        help="Baseline monthly forward energy rate."
                    )
                fixed_rate_ht = fixed_rate_val
                fixed_rate_nt = fixed_rate_val

            submitted_supp = st.form_submit_button(
                "Save Supplier Tariff",
                icon=":material/save:",
                type="primary",
                use_container_width=True
            )
            if submitted_supp:
                st.success(f"Supplier configuration saved: **{selected_supplier_name}** ({active_pricing_mode.value.upper()})", icon=":material/check_circle:")

    # ----------------------------------------------------------------------------------
    # Sub-Tab 3: Metering Company & Transformer Station Rental
    # ----------------------------------------------------------------------------------
    with actor_tabs[2]:
        st.markdown("##### Pillar 3 & 4: Certified Metering (EMV) & Transformer Station Rental")

        with st.form(key=f"{key_prefix}_meter_trafo_form"):
            st.subheader("1. Certified Metering Company (Erkend Meetverantwoordelijke - EMV)")
            col_m_co, col_m_pkg = st.columns([1.5, 2.5])
            with col_m_co:
                meter_options = list(METERING_CATALOG_2025.keys()) + ["Custom Meetbedrijf"]
                selected_meter_name = st.selectbox(
                    "Metering Company (Meetbedrijf):",
                    options=meter_options,
                    index=0,
                    key=f"{key_prefix}_meter_name_select"
                )

            with col_m_pkg:
                if selected_meter_name in METERING_CATALOG_2025:
                    pkg_dict = METERING_CATALOG_2025[selected_meter_name]
                    pkg_options = list(pkg_dict.keys())
                    selected_pkg = st.selectbox(
                        "Service Package & Voltage Tier:",
                        options=pkg_options,
                        index=0,
                        key=f"{key_prefix}_meter_pkg_{selected_meter_name}"
                    )
                    pkg_data = pkg_dict[selected_pkg]
                    st.caption(f":material/info: *{pkg_data.get('description', '')}*")
                else:
                    selected_pkg = "Custom Metering Package"
                    pkg_data = {"annual_flat_fee": 840.00, "voltage_level": "MS", "description": "Custom telemetry contract"}
                    st.caption(":material/tune: *Custom telemetry and meter service contract.*")

            col_m1, col_m2 = st.columns(2)
            with col_m1:
                meter_annual = st.number_input(
                    "Annual Telemetry & Meter Fee (€/year):",
                    min_value=0.0,
                    value=float(pkg_data.get("annual_flat_fee", 840.00)),
                    step=50.0,
                    key=f"{key_prefix}_meter_annual",
                    help="15-minuten intervaltelemetrie en NEDU data clearing per jaar excl. btw"
                )
            with col_m2:
                st.info(
                    f":material/speed: **Monthly Metering Equivalent:** € {meter_annual / 12.0:,.2f} / month | "
                    f"**Voltage Tier:** {pkg_data.get('voltage_level', 'MS')}",
                    icon=":material/speed:"
                )

            st.markdown("---")
            st.subheader("2. Dedicated Transformer Substation Rental (Trafo-Station)")
            st.caption("For Medium Voltage connections (AC5a, AC5b, AC5, AC6), taking delivery at 10 kV / 20 kV requires a dedicated transformer station.")

            col_t_co, col_t_type = st.columns(2)
            with col_t_co:
                trafo_provider = st.selectbox(
                    "Transformer Provider (Materiaalleverancier):",
                    options=["Fudura B.V.", "Kenter B.V.", "Joulz Energy Solutions", "Alfen B.V.", "None / DSO Owned Trafo"],
                    index=0,
                    key=f"{key_prefix}_trafo_provider"
                )

            is_trafo_rented = (trafo_provider != "None / DSO Owned Trafo")
            default_trafo_fee = 4248.0 if is_trafo_rented else 0.0

            with col_t_type:
                trafo_capacity = st.selectbox(
                    "Transformer Station Capacity:",
                    options=[
                        "400 - 630 kVA Compactstation (€ 4,248 / yr = € 354 / mo)",
                        "1,000 kVA Substation (€ 6,200 / yr)",
                        "1,600 - 2,000 kVA Industrial (€ 9,200 / yr)",
                        "5,000 kVA (5 MVA) High Capacity (€ 18,500 / yr)",
                        "No Rental (Low Voltage AC4b or Customer Owned)"
                    ],
                    index=0 if is_trafo_rented else 4,
                    key=f"{key_prefix}_trafo_cap_select"
                )

            if "630" in trafo_capacity:
                default_trafo_fee = 4248.0
            elif "1,000" in trafo_capacity:
                default_trafo_fee = 6200.0
            elif "2,000" in trafo_capacity:
                default_trafo_fee = 9200.0
            elif "5,000" in trafo_capacity:
                default_trafo_fee = 18500.0
            elif "No Rental" in trafo_capacity:
                default_trafo_fee = 0.0
                is_trafo_rented = False

            col_tf1, col_tf2 = st.columns(2)
            with col_tf1:
                trafo_annual_fee = st.number_input(
                    "Annual Transformer Rental & Maintenance (€/year):",
                    min_value=0.0,
                    value=float(default_trafo_fee),
                    step=100.0,
                    key=f"{key_prefix}_trafo_annual_fee",
                    help="Jaarlijkse huur- en onderhoudskosten voor transformatorstation excl. btw"
                )
            with col_tf2:
                nen_3840_included = st.checkbox(
                    ":material/verified_user: Statutory NEN 3840 & IV-er Responsibility Included",
                    value=True,
                    key=f"{key_prefix}_trafo_nen3840",
                    help="Inclusief wettelijk verplichte Installatieverantwoordelijke (IV-er) en 24/7 storingsdienst."
                )

            submitted_m_t = st.form_submit_button(
                "Save Metering & Transformer Configuration",
                icon=":material/save:",
                type="primary",
                use_container_width=True
            )
            if submitted_m_t:
                st.success("Metering and Transformer Substation parameters saved.", icon=":material/check_circle:")

    # ----------------------------------------------------------------------------------
    # Sub-Tab 4: Statutory Taxes & Lifecycle Economics
    # ----------------------------------------------------------------------------------
    with actor_tabs[3]:
        st.markdown("##### Statutory Energy Taxes (Energiebelasting) & 15-Year TCO Economics")

        with st.form(key=f"{key_prefix}_tax_tco_form"):
            st.subheader("1. Degressive Dutch Energiebelasting (5 Brackets)")

            col_tx_yr, col_tx_verb = st.columns(2)
            with col_tx_yr:
                selected_tax_year = st.radio(
                    "Statutory Tax Schedule:",
                    options=[2025, 2026],
                    index=0,
                    horizontal=True,
                    key=f"{key_prefix}_tax_year_radio"
                )
            with col_tx_verb:
                has_verblijfsfunctie = st.checkbox(
                    ":material/home_work: Connection has Residential/Work Function (Verblijfsfunctie)",
                    value=True,
                    key=f"{key_prefix}_tax_verblijfsfunctie",
                    help="Entitles the connection to the statutory Vermindering Energiebelasting rebate (€524.95 in 2025, €519.80 in 2026)."
                )

            # Display Degressive Bracket Rates
            credit_val = 524.95 if selected_tax_year == 2025 else 519.80
            st.markdown(f"**Tax Year {selected_tax_year} Official Rates:**")
            st.markdown(
                f"- **Bracket 1 & 2 (0 – 10,000 kWh):** €{'0.1088' if selected_tax_year == 2025 else '0.1060'} / kWh\n"
                f"- **Bracket 3 (10,000 – 50,000 kWh):** €{'0.0674' if selected_tax_year == 2025 else '0.0656'} / kWh\n"
                f"- **Bracket 4 (50,000 – 10,000,000 kWh):** €{'0.0390' if selected_tax_year == 2025 else '0.0380'} / kWh\n"
                f"- **Bracket 5 (> 10,000,000 kWh):** €0.0005 / kWh\n"
                f"- **Vermindering Rebate:** €{credit_val:.2f} / year ({'Active' if has_verblijfsfunctie else 'Deactivated'}) | **VAT:** 21.0%"
            )

            st.markdown("---")
            st.subheader("2. 15-Year Lifecycle TCO Economics (Wirtschaftlichkeit)")
            col_tco1, col_tco2 = st.columns(2)
            with col_tco1:
                discount_rate = st.number_input(
                    "WACC / Discount Rate r (%):",
                    min_value=0.0,
                    max_value=25.0,
                    value=5.0,
                    step=0.5,
                    key=f"{key_prefix}_tco_r",
                    help="Discontovoet voor 15-jarige Total Cost of Ownership (NPV)"
                )
            with col_tco2:
                escalation_rate = st.number_input(
                    "Annual Electricity Price Escalation g (%):",
                    min_value=0.0,
                    max_value=25.0,
                    value=3.0,
                    step=0.5,
                    key=f"{key_prefix}_tco_g",
                    help="Jaarlijkse indexatie / stijging van de elektriciteitsprijs"
                )

            submitted_tax_tco = st.form_submit_button(
                "Save Tax & Lifecycle Parameters",
                icon=":material/save:",
                type="primary",
                use_container_width=True
            )
            if submitted_tax_tco:
                st.success("Tax schedule and 15-year lifecycle parameters saved.", icon=":material/check_circle:")

    st.markdown("---")



    # ----------------------------------------------------------------------------------
    # 3. Assemble Configuration & Execute 5-Layer 2025 Accounting
    # ----------------------------------------------------------------------------------
    # Connection Fee PAV (annual) and Fixed Transport Admin Fee Vastrecht (annual)
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
    # Sub-Tab 5: Executive Advisory & Strategy (Rendered inside the tab bar)
    # ----------------------------------------------------------------------------------
    with actor_tabs[4]:
        render_procurement_strategy_view(
            load=load_series,
            active_config=active_config,
            load_series=load_series,
            active_result=result,
            key_prefix=f"{key_prefix}_strategy"
        )

    # ----------------------------------------------------------------------------------
    # 4. Period Filter Inspector & Executive Financial KPI Cards
    # ----------------------------------------------------------------------------------
    st.markdown("### :material/dashboard: Key Financial & Operational Metrics")

    # Period Filter Selector
    month_options = ["All Months (Full Year 2025 Overview)"] + [r.month_name for r in result.monthly_records]
    col_p_sel, col_p_info = st.columns([2, 3])
    with col_p_sel:
        selected_period = st.selectbox(
            "Billing Period / Month to Inspect:",
            options=month_options,
            index=0,
            key=f"{key_prefix}_period_inspector"
        )
    is_single_month = (selected_period != "All Months (Full Year 2025 Overview)")

    with col_p_info:
        if is_single_month:
            st.info(f":material/filter_alt: Inspecting single-month accounting statement for **{selected_period}**", icon=":material/filter_alt:")
        else:
            st.caption(":material/calendar_month: *Consolidated 12-month annual accounting overview (reference year 2025).*")

    col_kpi1, col_kpi2, col_kpi3, col_kpi4 = st.columns(4)
    if is_single_month:
        target_rec = next((r for r in result.monthly_records if r.month_name == selected_period), result.monthly_records[0])
        excess_p = max(0.0, target_rec.consumption.peak_demand_kw - contracted_kw)
        with col_kpi1:
            render_kpi_card(
                title=f":material/receipt_long: {selected_period} Net Total",
                value=f"€ {target_rec.total_net:,.2f}",
                subtext=f"Gross (+21% VAT): € {target_rec.total_gross:,.2f} | VAT: € {target_rec.vat_amount:,.2f}",
                status="default"
            )
        with col_kpi2:
            render_kpi_card(
                title=f":material/price_change: {selected_period} Net Rate",
                value=f"€ {target_rec.effective_rate_net_kwh:.4f} / kWh",
                subtext=f"Energy: {target_rec.consumption.total_kwh:,.0f} kWh ({target_rec.consumption.days_count} days)",
                status="default"
            )
        with col_kpi3:
            breach_status = "alert" if excess_p > 0 else "ok"
            breach_sub = f"Overload: +{excess_p:.1f} kW (Limit: {contracted_kw:.0f} kW)" if excess_p > 0 else f"Peak within limit ({contracted_kw:.0f} kW)"
            render_kpi_card(
                title=f":material/speed: {selected_period} Peak Demand",
                value=f"{target_rec.consumption.peak_demand_kw:,.1f} kW",
                subtext=breach_sub,
                status=breach_status
            )
        with col_kpi4:
            supp_cost = target_rec.commercial.supplier_total_net
            meter_trafo_cost = target_rec.metering_net + target_rec.trafo_net
            render_kpi_card(
                title=f":material/account_tree: {selected_period} Actor Split",
                value=f"DSO: € {target_rec.dso.subtotal_dso_net:,.0f}",
                subtext=f"Supp: € {supp_cost:,.0f} | Met/Trafo: € {meter_trafo_cost:,.0f}",
                status="default"
            )
    else:
        with col_kpi1:
            render_kpi_card(
                title=":material/receipt_long: Annual Net Invoice",
                value=f"€ {result.total_status_quo_net:,.2f}",
                subtext=f"Gross (+21% VAT): € {result.total_status_quo_gross:,.2f}",
                status="default"
            )
        with col_kpi2:
            render_kpi_card(
                title=":material/price_change: Blended Net Rate",
                value=f"€ {result.blended_price_net_kwh:.4f} / kWh",
                subtext=f"Gross: € {result.blended_price_gross_kwh:.4f} / kWh",
                status="default"
            )
        with col_kpi3:
            breach_status = "alert" if result.has_capacity_breach else "ok"
            breach_sub = (
                f"Breach in {len(result.breach_months)} month(s): {result.breach_months}"
                if result.has_capacity_breach
                else f"Max peak {result.annual_peak_demand_kw:.1f} kW ≤ {contracted_kw:.1f} kW"
            )
            render_kpi_card(
                title=":material/speed: Annual Peak Demand",
                value=f"{result.annual_peak_demand_kw:,.1f} kW",
                subtext=breach_sub,
                status=breach_status
            )
        with col_kpi4:
            render_kpi_card(
                title=":material/savings: 15-Year TCO (NPV)",
                value=f"€ {result.tco_15_npv:,.2f}",
                subtext=f"WACC: {active_config.discount_rate_pct:.1f}% | Escalation: {active_config.energy_escalation_pct:.1f}%",
                status="default"
            )

    # ----------------------------------------------------------------------------------
    # 5. Operational Alerts & Breach Status
    # ----------------------------------------------------------------------------------
    if result.has_capacity_breach:
        max_excess = max(0.0, result.annual_peak_demand_kw - contracted_kw)
        excess_pct = (max_excess / max(1.0, contracted_kw)) * 100.0
        breach_list_str = ", ".join(str(m) for m in result.breach_months)
        st.markdown(
            f"""
            <div style="background: rgba(239, 68, 68, 0.08); border: 1px solid #EF4444; border-radius: 10px; padding: 18px 20px; margin-bottom: 20px; box-shadow: 0 4px 16px rgba(0,0,0,0.3);">
                <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
                    <span style="font-size: 1.05rem; font-weight: 700; color: #F87171;">
                        :material/warning: Contracted Grid Capacity Exceeded (GTV Overload Alert)
                    </span>
                    <span class="badge badge-rose" style="font-size: 0.8rem; font-weight: 600;">
                        +{max_excess:.1f} kW (+{excess_pct:.1f}%)
                    </span>
                </div>
                <div style="font-size: 0.88rem; color: #CBD5E1; line-height: 1.5; margin-bottom: 12px;">
                    <strong>Peak Measurement:</strong> The facility recorded a peak of 
                    <strong style="color: #F87171;">{result.annual_peak_demand_kw:,.1f} kW</strong>, exceeding the reserved GTV limit of 
                    <strong>{contracted_kw:,.1f} kW</strong> in <strong>{len(result.breach_months)} month(s)</strong> (Month {breach_list_str}).
                </div>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-top: 10px;">
                    <div style="background: rgba(15, 23, 42, 0.6); border: 1px solid #334155; border-radius: 8px; padding: 12px 14px;">
                        <div style="font-size: 0.85rem; font-weight: 600; color: #F59E0B; margin-bottom: 4px;">
                            :material/lock_clock: Case 1: Standard Grid (12-Month Ratchet Trap)
                        </div>
                        <div style="font-size: 0.8rem; color: #94A3B8; line-height: 1.4;">
                            Under Dutch ACM regulatory rules, regional DSOs (Liander, Enexis, Stedin) treat single peak exceedances as a tacit capacity upgrade. 
                            The monthly capacity fee is locked at this new peak level for <strong>at least 12 consecutive months</strong>, locking in substantial standing OPEX increases.
                        </div>
                    </div>
                    <div style="background: rgba(15, 23, 42, 0.6); border: 1px solid #334155; border-radius: 8px; padding: 12px 14px;">
                        <div style="font-size: 0.85rem; font-weight: 600; color: #EF4444; margin-bottom: 4px;">
                            :material/gavel: Case 2: Congested Grid Zone (Netcongestie Risk)
                        </div>
                        <div style="font-size: 0.8rem; color: #94A3B8; line-height: 1.4;">
                            In designated Dutch grid congestion areas (North Brabant, Gelderland, Utrecht, etc.), capacity increases are legally and physically blocked. 
                            Exceeding GTV is classified as a <strong>contract breach</strong>, carrying regulatory fines and the immediate threat of <strong>forced curtailment or complete grid disconnection</strong>.
                        </div>
                    </div>
                </div>
                <div style="margin-top: 12px; padding-top: 10px; border-top: 1px solid rgba(239, 68, 68, 0.2); font-size: 0.82rem; color: #00D2B4;">
                    :material/bolt: <strong>Strategic BESS Advisory:</strong> Implementing Battery Energy Storage (BESS) Peak Shaving buffers these 15-minute spikes, guarantees stay below GTV, protects against 12-month ratchet penalties, and circumvents congestion disputes.
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
    else:
        st.success(
            f":material/check_circle: **Contracted Capacity Compliant**: Maximum measured annual peak of "
            f"**{result.annual_peak_demand_kw:,.1f} kW** is within reserved GTV limit of **{contracted_kw:.1f} kW**.",
            icon=":material/check_circle:"
        )

    st.markdown("---")

    # ----------------------------------------------------------------------------------
    # 6. Unbundled Charts: Donut & 12-Month Payment Series (Zahlungsreihe)
    # ----------------------------------------------------------------------------------
    st.markdown("### :material/bar_chart: Cost Distribution & 12-Month Payment Schedule")

    breakdown_adapter = convert_to_financial_cost_breakdown(result, target_month=selected_period)

    col_chart1, col_chart2 = st.columns([1.2, 1.8])
    with col_chart1:
        chart_title = f"Cost Share by Component ({selected_period})" if is_single_month else "Cost Share by Component (Annualized)"
        st.markdown(f"##### {chart_title}")
        donut_fig = create_cost_donut_figure(breakdown_adapter)
        st.plotly_chart(donut_fig, use_container_width=True)

    with col_chart2:
        st.markdown("##### 12-Month Stacked Payment Series (Zahlungsreihe)")
        annual_adapter = convert_to_financial_cost_breakdown(result)
        series_fig = create_monthly_payment_series_figure(annual_adapter)
        st.plotly_chart(series_fig, use_container_width=True)

    # ----------------------------------------------------------------------------------
    # 7. 12-Month Itemized Statement Table
    # ----------------------------------------------------------------------------------
    # Live 4-Pillar Unbundled Invoice Card
    render_live_invoice_card(
        result=result,
        period_title="Annual Consolidated Grootverbruik Statement" if not is_single_month else f"Monthly Invoice Statement: {selected_period}"
    )

    st.markdown("### :material/table_view: 12-Month Accounting Statement Table")

    table_data = []
    for r in result.monthly_records:
        table_data.append({
            "Month": r.month_name,
            "Consumption (kWh)": round(r.consumption.total_kwh, 1),
            "Peak kW (P_max)": round(r.consumption.peak_demand_kw, 1),
            "DSO Net (€)": round(r.dso.subtotal_dso_net, 2),
            "Supplier Net (€)": round(r.commercial.supplier_total_net, 2),
            "Metering Net (€)": round(r.metering_net, 2),
            "Trafo Net (€)": round(r.trafo_net, 2),
            "Taxes Net (€)": round(r.taxes_net, 2),
            "Total Net (€)": round(r.total_net, 2),
            "VAT 21% (€)": round(r.vat_amount, 2),
            "Total Gross (€)": round(r.total_gross, 2),
            "Net Rate (€/kWh)": round(r.effective_rate_net_kwh, 4),
            "Breach": "YES" if r.dso.is_capacity_breached else "NO"
        })

    df_table = pd.DataFrame(table_data)
    st.dataframe(df_table, use_container_width=True, hide_index=True)

    # ----------------------------------------------------------------------------------
    # 8. 15-Year Long-Term Cost Structure & Lifecycle Forecast
    # ----------------------------------------------------------------------------------
    st.markdown("---")
    st.markdown("### :material/trending_up: 15-Year Long-Term Cost Structure & Lifecycle Projection (2025 – 2039)")
    st.caption(
        "Comprehensive 15-year lifecycle forecast consolidating **all 4 cost pillars** (Regulated DSO Grid, "
        "Energy Supplier Commodity, Certified Metering, and Statutory Taxes) assuming "
        f"{active_config.energy_escalation_pct:.1f}% annual inflation and discounted at "
        f"{active_config.discount_rate_pct:.1f}% WACC."
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

    col_tco_kpi1, col_tco_kpi2, col_tco_kpi3, col_tco_kpi4 = st.columns(4)
    with col_tco_kpi1:
        render_kpi_card(
            title=":material/payments: 15-Year Spend (Nominal)",
            value=f"€ {total_15y_nominal:,.2f}",
            subtext=f"Total cash outlay across {horizon_years} years (+{active_config.energy_escalation_pct:.1f}%/yr)",
            status="default"
        )
    with col_tco_kpi2:
        render_kpi_card(
            title=":material/savings: 15-Year TCO (NPV)",
            value=f"€ {result.tco_15_npv:,.2f}",
            subtext=f"Discounted present value today @ {active_config.discount_rate_pct:.1f}% WACC",
            status="default"
        )
    with col_tco_kpi3:
        render_kpi_card(
            title=":material/analytics: Average Annual Spend",
            value=f"€ {avg_annual_spend:,.2f}",
            subtext="Mean annual consolidated electricity budget",
            status="default"
        )
    with col_tco_kpi4:
        render_kpi_card(
            title=":material/event: Projected Year 15 Cost",
            value=f"€ {yr15_spend:,.2f}",
            subtext=f"Compounded budget in {start_calendar_year + horizon_years - 1}",
            status="default"
        )

    # Render interactive 15-Year Stacked Figure
    fig_15y = create_15_year_lifecycle_cost_figure(result, start_year=start_calendar_year)
    st.plotly_chart(fig_15y, use_container_width=True)

    # Itemized 15-Year Cashflow Table
    st.markdown("##### :material/table_rows: 15-Year Annual Financial Schedule")
    st.dataframe(df_tco_15, use_container_width=True, hide_index=True)

    # ----------------------------------------------------------------------------------
    # 9. Export Toolbar (CSV & JSON)
    # ----------------------------------------------------------------------------------
    col_exp1, col_exp2, col_exp3, col_exp4 = st.columns(4)
    with col_exp1:
        csv_buf = io.StringIO()
        df_table.to_csv(csv_buf, index=False, sep=";")
        st.download_button(
            label=":material/download: 12-Month CSV",
            data=csv_buf.getvalue(),
            file_name="status_quo_2025_statement.csv",
            mime="text/csv",
            key=f"{key_prefix}_export_csv",
            use_container_width=True
        )
    with col_exp2:
        csv_15y_buf = io.StringIO()
        df_tco_15.to_csv(csv_15y_buf, index=False, sep=";")
        st.download_button(
            label=":material/download: 15-Year TCO CSV",
            data=csv_15y_buf.getvalue(),
            file_name="status_quo_15_year_lifecycle_projection.csv",
            mime="text/csv",
            key=f"{key_prefix}_export_15y_csv",
            use_container_width=True
        )
    with col_exp3:
        export_payload = {
            "evaluation_year": 2025,
            "total_consumption_kwh": result.total_consumption_kwh,
            "total_status_quo_net": result.total_status_quo_net,
            "total_status_quo_gross": result.total_status_quo_gross,
            "blended_price_net_kwh": result.blended_price_net_kwh,
            "tco_15_npv": result.tco_15_npv,
            "total_15_year_nominal_spend": total_15y_nominal,
            "monthly_records": table_data,
            "lifecycle_15_year_schedule": tco_15_rows
        }
        json_str = json.dumps(export_payload, indent=2)
        st.download_button(
            label=":material/download: Audit JSON",
            data=json_str,
            file_name="status_quo_2025_audit.json",
            mime="application/json",
            key=f"{key_prefix}_export_json",
            use_container_width=True
        )
    with col_exp4:
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
            label=":material/save: Contract JSON",
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
