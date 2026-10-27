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
        create_supplier_benchmark_figure,
        create_dynamic_price_consumption_figure,
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
            create_supplier_benchmark_figure,
            create_dynamic_price_consumption_figure,
        )
    except ImportError:
        from current_model.ui.common.styles import apply_custom_styles
        from current_model.ui.common.cards import render_kpi_card
        from contract.charts import (
            create_monthly_payment_series_figure,
            create_cost_donut_figure,
            create_tou_schedule_diurnal_figure,
            create_15_year_lifecycle_cost_figure,
            create_supplier_benchmark_figure,
            create_dynamic_price_consumption_figure,
        )

# 2025 5-Layer Accounting Modules & Official Catalogs
try:
    from ui_sandbox.Currentsituation_sandbox.engine.config_and_models import (
        TariffStage,
        PricingMode,
        DSOTariff,
        SupplierTariff,
        MeteringTariff,
        LevyConfig,
        StatusQuoConfig2025,
        LoadSeries2025,
    )
    from ui_sandbox.Currentsituation_sandbox.engine.tariff_defaults_2025 import (
        DSO_CATALOGS_2025,
        SUPPLIER_CATALOG_2025,
        METERING_CATALOG_2025,
        get_dso_tariff_from_catalog,
        get_stage_1_default_config_2025,
        get_default_supplier_tariff_2025,
        get_default_metering_tariff_2025,
        get_default_levy_config_2025,
    )
    from ui_sandbox.Currentsituation_sandbox.engine.consumption_pipeline import (
        normalize_load_profile_2025,
        synthesize_benchmark_load_profile_2025,
        extract_monthly_consumption_records,
    )
    from ui_sandbox.Currentsituation_sandbox.engine.status_quo_master import (
        calculate_status_quo_master_2025,
        convert_to_financial_cost_breakdown,
    )
    from ui_sandbox.Currentsituation_sandbox.engine.audit import perform_full_status_quo_audit
    from ui_sandbox.Currentsituation_sandbox.engine.commercial_accounting import align_spot_prices_amsterdam_2025
except ImportError:
    try:
        from engine.config_and_models import (
            TariffStage,
            PricingMode,
            DSOTariff,
            SupplierTariff,
            MeteringTariff,
            LevyConfig,
            StatusQuoConfig2025,
            LoadSeries2025,
        )
        from engine.tariff_defaults_2025 import (
            DSO_CATALOGS_2025,
            SUPPLIER_CATALOG_2025,
            METERING_CATALOG_2025,
            get_dso_tariff_from_catalog,
            get_stage_1_default_config_2025,
            get_default_supplier_tariff_2025,
            get_default_metering_tariff_2025,
            get_default_levy_config_2025,
        )
        from engine.consumption_pipeline import (
            normalize_load_profile_2025,
            synthesize_benchmark_load_profile_2025,
            extract_monthly_consumption_records,
        )
        from engine.status_quo_master import (
            calculate_status_quo_master_2025,
            convert_to_financial_cost_breakdown,
        )
        from engine.audit import perform_full_status_quo_audit
        from engine.commercial_accounting import align_spot_prices_amsterdam_2025
    except ImportError:
        try:
            from current_model.ui_sandbox.Currentsituation_sandbox.engine.config_and_models import (
                TariffStage,
                PricingMode,
                DSOTariff,
                SupplierTariff,
                MeteringTariff,
                LevyConfig,
                StatusQuoConfig2025,
                LoadSeries2025,
            )
            from current_model.ui_sandbox.Currentsituation_sandbox.engine.tariff_defaults_2025 import (
                DSO_CATALOGS_2025,
                SUPPLIER_CATALOG_2025,
                METERING_CATALOG_2025,
                get_dso_tariff_from_catalog,
                get_stage_1_default_config_2025,
                get_default_supplier_tariff_2025,
                get_default_metering_tariff_2025,
                get_default_levy_config_2025,
            )
            from current_model.ui_sandbox.Currentsituation_sandbox.engine.consumption_pipeline import (
                normalize_load_profile_2025,
                synthesize_benchmark_load_profile_2025,
                extract_monthly_consumption_records,
            )
            from current_model.ui_sandbox.Currentsituation_sandbox.engine.status_quo_master import (
                calculate_status_quo_master_2025,
                convert_to_financial_cost_breakdown,
            )
            from current_model.ui_sandbox.Currentsituation_sandbox.engine.audit import perform_full_status_quo_audit
            from current_model.ui_sandbox.Currentsituation_sandbox.engine.commercial_accounting import align_spot_prices_amsterdam_2025
        except ImportError:
            from ui_sandbox.status_quo_2025.config_and_models import (
                TariffStage,
                PricingMode,
                DSOTariff,
                SupplierTariff,
                MeteringTariff,
                LevyConfig,
                StatusQuoConfig2025,
                LoadSeries2025,
            )
            from ui_sandbox.status_quo_2025.tariff_defaults_2025 import (
                DSO_CATALOGS_2025,
                SUPPLIER_CATALOG_2025,
                METERING_CATALOG_2025,
                get_dso_tariff_from_catalog,
                get_stage_1_default_config_2025,
                get_default_supplier_tariff_2025,
                get_default_metering_tariff_2025,
                get_default_levy_config_2025,
            )
            from ui_sandbox.status_quo_2025.consumption_pipeline import (
                normalize_load_profile_2025,
                synthesize_benchmark_load_profile_2025,
                extract_monthly_consumption_records,
            )
            from ui_sandbox.status_quo_2025.status_quo_master import (
                calculate_status_quo_master_2025,
                convert_to_financial_cost_breakdown,
            )
            from ui_sandbox.status_quo_2025.audit import perform_full_status_quo_audit
            from ui_sandbox.status_quo_2025.commercial_accounting import align_spot_prices_amsterdam_2025


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
    st.markdown("### :material/account_tree: 3-Party Unbundled Market Actors & Tariffs")

    actor_tabs = st.tabs([
        ":material/grid_view: 1. Regulated Grid Operator (Netzbetreiber / DSO)",
        ":material/bolt: 2. Energy Retailer (Energielieferant / Supplier)",
        ":material/speed: 3. Metering & Taxes (Meetbedrijf & Belastingen)"
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

        # Pre-compute current/saved DSO cost components for live preview card
        saved_dso_kw_val = float(st.session_state.get(f"{key_prefix}_dso_p_contract_{selected_dso_company}_{selected_tier}_v{form_version}", max(50.0, round(load_series.peak_demand_kw * 1.05, 0))))
        saved_dso_base_val = float(st.session_state.get(f"{key_prefix}_dso_base_fee_{selected_dso_company}_{selected_tier}_v{form_version}", round(float(preset_data.get("vastrecht_annual", 441.0)) / 12.0, 2)))
        saved_dso_cap_rate = float(st.session_state.get(f"{key_prefix}_dso_rate_cap_{selected_dso_company}_{selected_tier}_v{form_version}", float(preset_data.get("rate_contracted_monthly", 2.4400))))
        saved_dso_peak_rate = float(st.session_state.get(f"{key_prefix}_dso_rate_peak_{selected_dso_company}_{selected_tier}_v{form_version}", float(preset_data.get("rate_peak_monthly", 3.7100))))

        # Monthly records from load series
        _records_preview = extract_monthly_consumption_records(load_series)
        _prev_peak_demand_annual = sum(r.peak_demand_kw * saved_dso_peak_rate for r in _records_preview)
        _prev_fixed_annual = saved_dso_base_val * 12.0
        _prev_cap_annual = saved_dso_kw_val * saved_dso_cap_rate * 12.0
        _active_tou_df_prev = st.session_state.get(state_dso_tou_key)
        _prev_trans_ht = float(preset_data.get("rate_peak_kwh", 0.0250))
        _prev_trans_nt = float(preset_data.get("rate_offpeak_kwh", 0.0250))
        if _active_tou_df_prev is not None and not _active_tou_df_prev.empty:
            for _r in _active_tou_df_prev.to_dict(orient="records"):
                _rn = str(_r.get("name", "")).lower()
                _rr = float(_r.get("rate", _prev_trans_ht))
                if any(_k in _rn for _k in ["high", "normaal", "peak", "ht", "hoch", "daytime", "working"]):
                    _prev_trans_ht = _rr
                elif any(_k in _rn for _k in ["off", "dal", "laag", "nt", "niedrig", "night", "weekend"]):
                    _prev_trans_nt = _rr
        # Calculate HT and NT volume sums and sub-costs
        _total_ht_kwh = sum(r.peak_tou_kwh for r in _records_preview)
        _total_nt_kwh = sum(r.offpeak_tou_kwh for r in _records_preview)
        _prev_vol_ht_annual = _total_ht_kwh * _prev_trans_ht
        _prev_vol_nt_annual = _total_nt_kwh * _prev_trans_nt
        _prev_vol_annual = _prev_vol_ht_annual + _prev_vol_nt_annual
        _prev_breach_months = [r.month_name for r in _records_preview if r.peak_demand_kw > (saved_dso_kw_val + 1e-4)]
        _prev_dso_net_annual = _prev_fixed_annual + _prev_cap_annual + _prev_peak_demand_annual + _prev_vol_annual

        with st.form(key=f"{key_prefix}_dso_contract_form_{selected_dso_company}_{selected_tier}_v{form_version}"):
            col_form_inputs, col_form_preview = st.columns([1.65, 1.0], gap="large")

            with col_form_inputs:
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
                    ann_standing_default = float(preset_data.get("vastrecht_annual", 441.0))
                    monthly_standing_default = round(ann_standing_default / 12.0, 2)
                    base_fee = st.number_input(
                        "Fixed Monthly Grid Fee (€/month):",
                        min_value=0.0,
                        value=monthly_standing_default,
                        step=5.0,
                        format="%.2f",
                        key=f"{key_prefix}_dso_base_fee_{selected_dso_company}_{selected_tier}_v{form_version}",
                        help="Fixed standing charge for grid access (Festgebühr Transport / Vastrecht €/month)"
                    )
                    contracted_kw = st.number_input(
                        "Reserved Grid Capacity (kW):",
                        min_value=10.0,
                        max_value=20000.0,
                        value=float(max(50.0, round(load_series.peak_demand_kw * 1.05, 0))),
                        step=10.0,
                        format="%.1f",
                        key=f"{key_prefix}_dso_p_contract_{selected_dso_company}_{selected_tier}_v{form_version}",
                        help="Power reserved on the grid for your facility (kW-Vertrag / Gecontracteerd vermogen in kW)"
                    )

                with c2:
                    capacity_tariff = st.number_input(
                        "Reserved Capacity Rate (€/kW/month):",
                        min_value=0.0,
                        value=float(preset_data.get("rate_contracted_monthly", 2.4400)),
                        step=0.01,
                        format="%.4f",
                        key=f"{key_prefix}_dso_rate_cap_{selected_dso_company}_{selected_tier}_v{form_version}",
                        help="Monthly fee billed per reserved kW (kW-Vertrag Tarif / Capaciteitstarief)"
                    )
                    demand_tariff = st.number_input(
                        "Monthly Peak Demand Rate (€/kW/month):",
                        min_value=0.0,
                        value=float(preset_data.get("rate_peak_monthly", 3.7100)),
                        step=0.01,
                        format="%.4f",
                        key=f"{key_prefix}_dso_rate_peak_{selected_dso_company}_{selected_tier}_v{form_version}",
                        help="Monthly fee billed per measured 15-minute maximum peak (kW max. pro Monat / Piekvermogen)"
                    )
                    max_physical_kw = st.number_input(
                        "Physical Transformer Limit (kW):",
                        min_value=10.0,
                        value=float(preset_data.get("max_physical_limit_kw", 1000.0)),
                        step=50.0,
                        format="%.1f",
                        key=f"{key_prefix}_dso_max_phys_{selected_dso_company}_{selected_tier}_v{form_version}",
                        help="Maximum physical electrical limit of your transformer or main connection"
                    )
                    penalty_rate = st.number_input(
                        "Capacity Exceedance Penalty (€/kW):",
                        min_value=0.0,
                        value=float(preset_data.get("peak_penalty_rate_kw", 0.2500)),
                        step=0.05,
                        format="%.4f",
                        key=f"{key_prefix}_dso_penalty_{selected_dso_company}_{selected_tier}_v{form_version}",
                        help="Penalty fee charged when monthly peak demand exceeds reserved grid capacity"
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
                    ":material/shield: Adjust capacity billing to actual peak during breach months (Dutch standard rule)",
                    value=True,
                    key=f"{key_prefix}_dso_adjust_breach",
                    help="Bij overschrijding van het gecontracteerde vermogen wordt de capaciteitsvergoeding in de desbetreffende maand berekend op basis van de werkelijke piek."
                )

            with col_form_preview:
                # ==============================================================================
                # DIRECT COST IMPACT & ITEMIZATION PREVIEW (SIDE-BY-SIDE INSIDE FORM)
                # ==============================================================================
                st.markdown("#### :material/receipt_long: Direct Cost Impact")
                st.caption("Calculated based on active load baseline & current tariff rates:")

                with st.container(border=True):
                    st.metric(
                        label="DSO Net Annual Cost",
                        value=f"€ {_prev_dso_net_annual:,.2f}",
                        delta=f"€ {_prev_dso_net_annual / 12.0:,.2f} / month (avg)",
                        delta_color="off"
                    )

                    st.divider()

                    st.markdown("**Itemized Cost Breakdown (Year & Month):**")
                    cost_table_html = f"""
                    <div style="width: 100%; overflow-x: auto;">
                    <table style="width: 100%; border-collapse: collapse; font-size: 0.86rem;">
                        <thead>
                            <tr style="border-bottom: 1px solid rgba(128, 128, 128, 0.3); color: #888888; font-size: 0.78rem;">
                                <th style="text-align: left; padding: 4px 6px;">Component</th>
                                <th style="text-align: right; padding: 4px 6px;">Per Year</th>
                                <th style="text-align: right; padding: 4px 6px;">Per Month</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr style="border-bottom: 1px solid rgba(128, 128, 128, 0.15);">
                                <td style="padding: 6px 6px;">Fixed Standing Fee:</td>
                                <td style="text-align: right; padding: 6px 6px; font-weight: bold;">€ {_prev_fixed_annual:,.2f}</td>
                                <td style="text-align: right; padding: 6px 6px; color: #a0aec0;">€ {_prev_fixed_annual / 12.0:,.2f}</td>
                            </tr>
                            <tr style="border-bottom: 1px solid rgba(128, 128, 128, 0.15);">
                                <td style="padding: 6px 6px;">Reserved Capacity:</td>
                                <td style="text-align: right; padding: 6px 6px; font-weight: bold;">€ {_prev_cap_annual:,.2f}</td>
                                <td style="text-align: right; padding: 6px 6px; color: #a0aec0;">€ {_prev_cap_annual / 12.0:,.2f}</td>
                            </tr>
                            <tr style="border-bottom: 1px solid rgba(128, 128, 128, 0.15);">
                                <td style="padding: 6px 6px;">Peak Demand:</td>
                                <td style="text-align: right; padding: 6px 6px; font-weight: bold;">€ {_prev_peak_demand_annual:,.2f}</td>
                                <td style="text-align: right; padding: 6px 6px; color: #a0aec0;">€ {_prev_peak_demand_annual / 12.0:,.2f}</td>
                            </tr>
                            <tr style="border-bottom: 1px solid rgba(128, 128, 128, 0.15);">
                                <td style="padding: 6px 6px; font-weight: 600;">Volumetric Transport:</td>
                                <td style="text-align: right; padding: 6px 6px; font-weight: bold;">€ {_prev_vol_annual:,.2f}</td>
                                <td style="text-align: right; padding: 6px 6px; font-weight: bold; color: #a0aec0;">€ {_prev_vol_annual / 12.0:,.2f}</td>
                            </tr>
                            <tr style="border-bottom: 1px solid rgba(128, 128, 128, 0.1); font-size: 0.80rem; color: #a0aec0;">
                                <td style="padding: 3px 6px 3px 18px;">↳ Daytime / HT ({_total_ht_kwh:,.0f} kWh)</td>
                                <td style="text-align: right; padding: 3px 6px;">€ {_prev_vol_ht_annual:,.2f}</td>
                                <td style="text-align: right; padding: 3px 6px;">€ {_prev_vol_ht_annual / 12.0:,.2f}</td>
                            </tr>
                            <tr style="border-bottom: 1px solid rgba(128, 128, 128, 0.1); font-size: 0.80rem; color: #a0aec0;">
                                <td style="padding: 3px 6px 3px 18px;">↳ Off-Peak / NT ({_total_nt_kwh:,.0f} kWh)</td>
                                <td style="text-align: right; padding: 3px 6px;">€ {_prev_vol_nt_annual:,.2f}</td>
                                <td style="text-align: right; padding: 3px 6px;">€ {_prev_vol_nt_annual / 12.0:,.2f}</td>
                            </tr>
                        </tbody>
                    </table>
                    </div>
                    """
                    st.markdown(cost_table_html, unsafe_allow_html=True)

                    st.divider()

                    st.markdown("**Capacity & Grid Diagnostics:**")
                    st.write(f"• Facility Peak: **{load_series.peak_demand_kw:,.1f} kW**")
                    st.write(f"• Reserved Capacity: **{saved_dso_kw_val:,.1f} kW**")

                    if len(_prev_breach_months) > 0:
                        st.warning(
                            f":material/warning: **Capacity Overload:** Exceeded in **{len(_prev_breach_months)} month(s)**: "
                            f"{', '.join(_prev_breach_months[:3])}{'...' if len(_prev_breach_months) > 3 else ''}."
                        )
                    else:
                        st.success(":material/check_circle: **Safe Capacity:** Peak within reserved limit across all 12 months.")

            st.markdown("---")
            submitted_dso = st.form_submit_button(
                "Save Contract Configuration & Recalculate",
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

        # Determine Profile Duration in Actual Days
        actual_profile_days = 365.0
        if "active_csv_df" in st.session_state and isinstance(st.session_state["active_csv_df"], pd.DataFrame):
            df_active = st.session_state["active_csv_df"]
            t_col_cand = "timestamp" if "timestamp" in df_active.columns else (df_active.columns[0] if "time" in str(df_active.columns[0]).lower() else None)
            if t_col_cand and t_col_cand in df_active.columns:
                try:
                    ts_parsed = pd.to_datetime(df_active[t_col_cand], errors="coerce").dropna()
                    if len(ts_parsed) > 1:
                        dur_d = (ts_parsed.max() - ts_parsed.min()).total_seconds() / 86400.0
                        if dur_d > 0.5:
                            actual_profile_days = float(dur_d)
                except Exception:
                    pass
        elif getattr(load_series, "duration_days", None):
            actual_profile_days = float(load_series.duration_days)

        # ------------------------------------------------------------------------------
        # A. Pre-Selection Toolbar (Outside the Form)
        # ------------------------------------------------------------------------------
        col_tb_supp, col_tb_mode = st.columns([1.5, 2.5])
        with col_tb_supp:
            supplier_options = list(SUPPLIER_CATALOG_2025.keys()) + ["Custom Energy Retailer"]
            selected_supplier_name = st.selectbox(
                "Energy Retailer (Leverancier):",
                options=supplier_options,
                index=0,
                key=f"{key_prefix}_supp_name_select"
            )

        # 3 Core Pricing Models (covering >90% of Dutch commercial market)
        MODEL_DUAL = "Fixed Dual Rate (Dubbeltarief HT/NT)"
        MODEL_SINGLE = "Fixed Single Rate (Enkeltarief)"
        MODEL_DYNAMIC = "Dynamic Day-Ahead (EPEX Spot NL + Opslag)"
        model_options = [MODEL_DUAL, MODEL_SINGLE, MODEL_DYNAMIC]

        # Determine best default model from catalog if present
        def_model_idx = 0
        if selected_supplier_name in SUPPLIER_CATALOG_2025:
            supp_prods = SUPPLIER_CATALOG_2025[selected_supplier_name]
            first_prod = list(supp_prods.values())[0]
            if first_prod.get("pricing_mode") == PricingMode.DYNAMIC:
                def_model_idx = 2
            elif first_prod.get("is_dual_rate", False):
                def_model_idx = 0
            else:
                def_model_idx = 1
        elif "tibber" in selected_supplier_name.lower():
            def_model_idx = 2

        with col_tb_mode:
            selected_model_type = st.radio(
                "Contract Pricing Model:",
                options=model_options,
                index=def_model_idx,
                horizontal=True,
                key=f"{key_prefix}_supp_model_radio_{selected_supplier_name}"
            )

        # Derive initial defaults matching the selected supplier & model
        found_prod_key = None
        found_prod_data: Dict[str, Any] = {}
        if selected_supplier_name in SUPPLIER_CATALOG_2025:
            prods = SUPPLIER_CATALOG_2025[selected_supplier_name]
            # Match product with chosen model
            for p_k, p_v in prods.items():
                if selected_model_type == MODEL_DYNAMIC and p_v.get("pricing_mode") == PricingMode.DYNAMIC:
                    found_prod_key, found_prod_data = p_k, p_v
                    break
                elif selected_model_type == MODEL_DUAL and p_v.get("pricing_mode") == PricingMode.FIXED and p_v.get("is_dual_rate", False):
                    found_prod_key, found_prod_data = p_k, p_v
                    break
                elif selected_model_type == MODEL_SINGLE and p_v.get("pricing_mode") == PricingMode.FIXED and not p_v.get("is_dual_rate", False):
                    found_prod_key, found_prod_data = p_k, p_v
                    break
            # Fallback to first product if no exact match found
            if not found_prod_data and prods:
                found_prod_key = list(prods.keys())[0]
                found_prod_data = prods[found_prod_key]

        selected_product = found_prod_key or f"{selected_supplier_name} {selected_model_type}"
        prod_data = found_prod_data

        if prod_data.get("description"):
            st.caption(f":material/info: *{prod_data['description']}*")

        # Session state buffering for form values
        supp_state_key = f"{key_prefix}_supp_form_vals"
        if supp_state_key not in st.session_state:
            st.session_state[supp_state_key] = {}

        # Reset defaults if supplier or model changed
        preset_hash = f"{selected_supplier_name}_{selected_model_type}"
        last_preset = st.session_state[supp_state_key].get("_preset_hash")
        if last_preset != preset_hash:
            st.session_state[supp_state_key] = {
                "_preset_hash": preset_hash,
                "base_fee": float(prod_data.get("base_fee_annual", 180.00)),
                "green_surcharge": float(prod_data.get("green_surcharge_kwh", 0.0030)),
                "ht_rate": float(prod_data.get("rate_peak_kwh", 0.1340)),
                "nt_rate": float(prod_data.get("rate_offpeak_kwh", 0.1180)),
                "single_rate": float(prod_data.get("fixed_rate_kwh", 0.1250)),
                "supplier_margin": float(prod_data.get("supplier_margin_kwh", 0.0075)),
                "procure_fee": float(prod_data.get("procurement_fee_kwh", 0.0015)),
                "weekend_offpeak": True,
            }

        curr_vals = st.session_state[supp_state_key]

        # Dynamic session state key for Supplier TOU rates matrix
        state_supp_tou_key = f"{key_prefix}_supp_tou_df_{selected_supplier_name}_{selected_model_type}"
        if state_supp_tou_key not in st.session_state or last_preset != preset_hash:
            default_supp_ht = float(curr_vals.get("ht_rate", 0.1340))
            default_supp_nt = float(curr_vals.get("nt_rate", 0.1180))
            st.session_state[state_supp_tou_key] = pd.DataFrame([
                {"name": "High Tariff HT (Normaaltarief)", "rate": default_supp_ht, "start_time": "07:00", "end_time": "23:00"},
                {"name": "Off-Peak NT (Daltarief)", "rate": default_supp_nt, "start_time": "23:00", "end_time": "07:00"}
            ])

        # ------------------------------------------------------------------------------
        # B. Encapsulated Form (st.form) for Numerical Parameters
        # ------------------------------------------------------------------------------
        with st.form(key=f"{key_prefix}_retailer_form"):
            col_f_base, col_f_green = st.columns(2)
            with col_f_base:
                supp_base = st.number_input(
                    "Retailer Standing Fee (€/year):",
                    min_value=0.0,
                    value=float(curr_vals["base_fee"]),
                    step=15.0,
                    help="Vastrecht levering per jaar excl. btw"
                )
            with col_f_green:
                green_surcharge = st.number_input(
                    "Green Power Surcharge GvO (€/kWh):",
                    min_value=0.0,
                    value=float(curr_vals["green_surcharge"]),
                    format="%.4f",
                    step=0.0005,
                    help="Garantie van Oorsprong (GvO) opslag voor 100% Nederlandse groene stroom"
                )

            # Contextual Fields by Selected Model
            edited_supp_tou = None
            supp_weekend_offpeak = True
            ht_start_hour_supp = 7
            ht_end_hour_supp = 23

            if selected_model_type == MODEL_DUAL:
                active_pricing_mode = PricingMode.FIXED
                is_dual_rate = True
                supp_margin = 0.0
                procure_fee = 0.0

                st.markdown("###### :material/schedule: Time-of-Use Electricity Rates (Working Hours vs. Off-Peak)")
                st.caption("Define commodity rate windows. The table supports direct editing of rates and hours:")

                edited_supp_tou = st.data_editor(
                    st.session_state[state_supp_tou_key],
                    num_rows="dynamic",
                    use_container_width=True,
                    column_config={
                        "name": st.column_config.TextColumn("Tariff Name", required=True),
                        "rate": st.column_config.NumberColumn(
                            "Rate (€/kWh)",
                            format="%.4f",
                            min_value=0.0,
                            step=0.0001,
                            required=True
                        ),
                        "start_time": st.column_config.TextColumn("Start Time (HH:MM)", required=True),
                        "end_time": st.column_config.TextColumn("End Time (HH:MM)", required=True)
                    },
                    key=f"{key_prefix}_supp_tou_editor_{selected_supplier_name}_{selected_model_type}"
                )

                supp_weekend_offpeak = st.checkbox(
                    "Treat Weekends as Off-Peak (Apply Lowest Tariff)",
                    value=bool(curr_vals.get("weekend_offpeak", True)),
                    key=f"{key_prefix}_supp_weekend_offpeak",
                    help="Pas gedurende het gehele weekend het daltarief (NT) toe"
                )

                # Extract rates and hours from matrix
                current_matrix = edited_supp_tou if (edited_supp_tou is not None and not edited_supp_tou.empty) else st.session_state[state_supp_tou_key]
                fixed_rate_ht = float(curr_vals["ht_rate"])
                fixed_rate_nt = float(curr_vals["nt_rate"])

                if current_matrix is not None and not current_matrix.empty:
                    rows = current_matrix.to_dict(orient="records")
                    for r in rows:
                        r_name = str(r.get("name", "")).lower()
                        r_rate = float(r.get("rate", fixed_rate_ht))
                        if any(k in r_name for k in ["high", "normaal", "peak", "ht", "hoch", "daytime", "working"]):
                            fixed_rate_ht = r_rate
                            try:
                                s_str = str(r.get("start_time", "07:00")).split(":")[0]
                                e_str = str(r.get("end_time", "23:00")).split(":")[0]
                                ht_start_hour_supp = int(s_str)
                                ht_end_hour_supp = int(e_str)
                            except Exception:
                                pass
                        elif any(k in r_name for k in ["off", "dal", "laag", "nt", "niedrig", "night", "weekend"]):
                            fixed_rate_nt = r_rate

                fixed_rate_val = fixed_rate_ht

            elif selected_model_type == MODEL_SINGLE:
                active_pricing_mode = PricingMode.FIXED
                is_dual_rate = False
                supp_margin = 0.0
                procure_fee = 0.0

                fixed_rate_val = st.number_input(
                    "Uniform Fixed Rate (€/kWh) – 24/7 Flat Rate:",
                    min_value=0.0,
                    value=float(curr_vals["single_rate"]),
                    format="%.4f",
                    step=0.0020,
                    help="Uniforme vaste leveringsprijs per actief kilowattuur over alle uren"
                )
                fixed_rate_ht = fixed_rate_val
                fixed_rate_nt = fixed_rate_val

            else:  # MODEL_DYNAMIC
                active_pricing_mode = PricingMode.DYNAMIC
                is_dual_rate = False
                fixed_rate_val = 0.1250
                fixed_rate_ht = 0.1340
                fixed_rate_nt = 0.1180

                col_dyn1, col_dyn2 = st.columns(2)
                with col_dyn1:
                    supp_margin = st.number_input(
                        "Supplier Retail Markup / Opslag (€/kWh):",
                        min_value=0.0,
                        value=float(curr_vals["supplier_margin"]),
                        format="%.4f",
                        step=0.0005,
                        help="Leveranciersopslag bovenop de EPEX Spot Day-Ahead uur-/kwartierprijs"
                    )
                with col_dyn2:
                    procure_fee = st.number_input(
                        "Procurement / Imbalance Fee (€/kWh):",
                        min_value=0.0,
                        value=float(curr_vals["procure_fee"]),
                        format="%.4f",
                        step=0.0005,
                        help="Vaste inkoopvergoeding en onbalansbijdrage per kWh"
                    )

            form_submitted = st.form_submit_button(
                "Apply Provider Tariff & Calculate",
                type="primary",
                icon=":material/calculate:"
            )

        # Update session buffer on submission
        if form_submitted:
            st.session_state[supp_state_key]["base_fee"] = supp_base
            st.session_state[supp_state_key]["green_surcharge"] = green_surcharge
            if selected_model_type == MODEL_DUAL:
                if edited_supp_tou is not None and not edited_supp_tou.empty:
                    st.session_state[state_supp_tou_key] = edited_supp_tou
                st.session_state[supp_state_key]["ht_rate"] = fixed_rate_ht
                st.session_state[supp_state_key]["nt_rate"] = fixed_rate_nt
                st.session_state[supp_state_key]["weekend_offpeak"] = supp_weekend_offpeak
            elif selected_model_type == MODEL_SINGLE:
                st.session_state[supp_state_key]["single_rate"] = fixed_rate_val
            else:
                st.session_state[supp_state_key]["supplier_margin"] = supp_margin
                st.session_state[supp_state_key]["procure_fee"] = procure_fee

        st.markdown("---")

        # ------------------------------------------------------------------------------
        # C. Isolated Supplier Accounting & 2-Way Evaluation Mode
        # ------------------------------------------------------------------------------
        st.markdown("##### :material/payments: Isolated Supplier Performance & Cost Analysis")

        # 2-Way Evaluation Mode: Default is Modus A (Actual Measured Period)
        col_eval_mode, col_eval_badge = st.columns([2.5, 1.5])
        with col_eval_mode:
            eval_mode = st.radio(
                "Evaluation Horizon:",
                options=[
                    f"Actual Measured Period ({actual_profile_days:.0f} Days)",
                    "Annualized Projection (365 Days)"
                ],
                index=0,  # MODUS A IS DEFAULT
                horizontal=True,
                key=f"{key_prefix}_supplier_eval_horizon_radio"
            )

        is_actual_horizon = "Actual Measured" in eval_mode

        with col_eval_badge:
            if is_actual_horizon:
                day_scale = actual_profile_days / 365.0
                st.caption(
                    f":material/event_available: Pro-rata standing fee: "
                    f"€ {supp_base * day_scale:,.2f} ({actual_profile_days:.0f}/365 days)"
                )
            else:
                day_scale = 1.0
                annual_scaling_factor = 365.0 / max(1.0, actual_profile_days)
                if actual_profile_days < 360:
                    st.info(
                        f":material/info: Scaled by {annual_scaling_factor:.2f}x to represent 365 days.",
                        icon=":material/info:"
                    )

        # ------------------------------------------------------------------------------
        # D. Mathematics: Pure Supplier Costs & Benchmark Shadow Calculation
        # ------------------------------------------------------------------------------
        total_kwh = float(load_series.total_energy_kwh)

        # Dynamic HT/NT mask: adapts to user-defined start/end hours and weekend toggle
        ts = load_series.timestamps
        if selected_model_type == MODEL_DUAL:
            if supp_weekend_offpeak:
                day_filter = (ts.dayofweek < 5)
            else:
                day_filter = np.ones(len(ts), dtype=bool)

            if ht_start_hour_supp <= ht_end_hour_supp:
                hour_filter = (ts.hour >= ht_start_hour_supp) & (ts.hour < ht_end_hour_supp)
            else:
                hour_filter = (ts.hour >= ht_start_hour_supp) | (ts.hour < ht_end_hour_supp)

            ht_mask = np.asarray(day_filter & hour_filter, dtype=bool)
        else:
            ht_mask = load_series.is_peak_tou

        ht_kwh = float(np.sum(load_series.energy_kwh[ht_mask]))
        nt_kwh = float(np.sum(load_series.energy_kwh[~ht_mask]))

        # Helper temporary tariff for spot alignment
        temp_spot_tariff = SupplierTariff(
            supplier_name=selected_supplier_name,
            pricing_mode=PricingMode.DYNAMIC,
            tariff_product_name="Spot Temp",
            base_fee_annual=supp_base,
            supplier_margin_kwh=supp_margin if selected_model_type == MODEL_DYNAMIC else 0.0070,
            procurement_fee_kwh=procure_fee if selected_model_type == MODEL_DYNAMIC else 0.0015,
            green_certificate_surcharge_kwh=green_surcharge,
            spot_default_fallback_rate=0.1200
        )
        spot_prices = align_spot_prices_amsterdam_2025(load_series, temp_spot_tariff)

        # Pure commodity cost functions
        surcharge_kwh = procure_fee + green_surcharge
        if selected_model_type == MODEL_DUAL:
            active_energy_cost = (ht_kwh * fixed_rate_ht) + (nt_kwh * fixed_rate_nt) + (total_kwh * surcharge_kwh)
        elif selected_model_type == MODEL_SINGLE:
            active_energy_cost = (total_kwh * fixed_rate_val) + (total_kwh * surcharge_kwh)
        else:
            all_in_spot = spot_prices + supp_margin + surcharge_kwh
            active_energy_cost = float(np.sum(load_series.energy_kwh * all_in_spot))

        # Benchmark Shadow Costs for all 3 models
        # 1. Dual Benchmark:
        bench_ht = fixed_rate_ht if selected_model_type == MODEL_DUAL else float(curr_vals.get("ht_rate", 0.1340))
        bench_nt = fixed_rate_nt if selected_model_type == MODEL_DUAL else float(curr_vals.get("nt_rate", 0.1180))
        cost_dual_energy = (ht_kwh * bench_ht) + (nt_kwh * bench_nt) + (total_kwh * surcharge_kwh)

        # 2. Single Benchmark:
        bench_single = fixed_rate_val if selected_model_type == MODEL_SINGLE else float(curr_vals.get("single_rate", 0.1250))
        cost_single_energy = (total_kwh * bench_single) + (total_kwh * surcharge_kwh)

        # 3. Dynamic Benchmark:
        bench_dyn_margin = supp_margin if selected_model_type == MODEL_DYNAMIC else 0.0070
        bench_dyn_procure = procure_fee if selected_model_type == MODEL_DYNAMIC else 0.0015
        dyn_all_in = spot_prices + bench_dyn_margin + bench_dyn_procure + green_surcharge
        cost_dynamic_energy = float(np.sum(load_series.energy_kwh * dyn_all_in))

        # Apply Horizon Scaling
        if is_actual_horizon:
            horizon_kwh = total_kwh
            horizon_ht_kwh = ht_kwh
            horizon_nt_kwh = nt_kwh
            base_fee_evaluated = supp_base * (actual_profile_days / 365.0)
            evaluated_energy_cost = active_energy_cost
            bench_total_dual = cost_dual_energy + base_fee_evaluated
            bench_total_single = cost_single_energy + base_fee_evaluated
            bench_total_dynamic = cost_dynamic_energy + base_fee_evaluated
        else:
            scale_fac = 365.0 / max(1.0, actual_profile_days)
            horizon_kwh = total_kwh * scale_fac
            horizon_ht_kwh = ht_kwh * scale_fac
            horizon_nt_kwh = nt_kwh * scale_fac
            base_fee_evaluated = supp_base
            evaluated_energy_cost = active_energy_cost * scale_fac
            bench_total_dual = (cost_dual_energy * scale_fac) + base_fee_evaluated
            bench_total_single = (cost_single_energy * scale_fac) + base_fee_evaluated
            bench_total_dynamic = (cost_dynamic_energy * scale_fac) + base_fee_evaluated

        supplier_net_total = evaluated_energy_cost + base_fee_evaluated
        effective_commodity_rate = supplier_net_total / max(1.0, horizon_kwh)

        # Benchmark comparison against the main alternative model
        if selected_model_type == MODEL_DYNAMIC:
            alt_model_name = "Fixed Dual Rate"
            alt_cost = bench_total_dual
        else:
            alt_model_name = "Dynamic Day-Ahead"
            alt_cost = bench_total_dynamic

        delta_eur = supplier_net_total - alt_cost
        delta_pct = (delta_eur / max(1.0, alt_cost)) * 100.0

        # ------------------------------------------------------------------------------
        # E. 4 Executive KPI Cards
        # ------------------------------------------------------------------------------
        col_kpi_s1, col_kpi_s2, col_kpi_s3, col_kpi_s4 = st.columns(4)
        with col_kpi_s1:
            render_kpi_card(
                title=":material/receipt_long: Pure Supplier Total",
                value=f"€ {supplier_net_total:,.2f}",
                subtext=f"Energy: € {evaluated_energy_cost:,.2f} | Base: € {base_fee_evaluated:,.2f}",
                status="default"
            )
        with col_kpi_s2:
            render_kpi_card(
                title=":material/price_change: Effective Commodity Rate",
                value=f"€ {effective_commodity_rate:.4f} / kWh",
                subtext=f"Commodity only ({effective_commodity_rate * 100.0:.2f} ct/kWh)",
                status="default"
            )
        with col_kpi_s3:
            ht_share = (horizon_ht_kwh / max(1.0, horizon_kwh)) * 100.0
            nt_share = (horizon_nt_kwh / max(1.0, horizon_kwh)) * 100.0
            render_kpi_card(
                title=":material/contrast: HT / NT Volume Split",
                value=f"HT: {ht_share:.1f}% | NT: {nt_share:.1f}%",
                subtext=f"HT: {horizon_ht_kwh:,.0f} kWh | NT: {horizon_nt_kwh:,.0f} kWh",
                status="default"
            )
        with col_kpi_s4:
            if abs(delta_eur) < 1.0:
                delta_str = "Parity (±0 €)"
                d_status = "ok"
            elif delta_eur < 0:
                delta_str = f"-€ {abs(delta_eur):,.0f} ({delta_pct:.1f}%)"
                d_status = "ok"
            else:
                delta_str = f"+€ {delta_eur:,.0f} (+{delta_pct:.1f}%)"
                d_status = "alert"

            render_kpi_card(
                title=f":material/compare_arrows: vs. {alt_model_name}",
                value=delta_str,
                subtext=f"Alt Cost: € {alt_cost:,.0f} net",
                status=d_status
            )

        # ------------------------------------------------------------------------------
        # F. Compact Visualizations & Itemized Settlement Table (2 Columns)
        # ------------------------------------------------------------------------------
        col_vis_left, col_vis_right = st.columns([1.1, 1.0])

        with col_vis_left:
            st.markdown("###### :material/insights: Visual Tariff Benchmark & Load Schedule")

            # 1. Horizontal Benchmark Bar Chart
            bench_dict = {
                "Fixed Dual Rate (HT/NT)": bench_total_dual,
                "Fixed Single Rate": bench_total_single,
                "Dynamic Day-Ahead": bench_total_dynamic,
            }
            fig_bench = create_supplier_benchmark_figure(bench_dict)
            st.plotly_chart(fig_bench, use_container_width=True)

            # 2. Model-specific detail curve
            if selected_model_type == MODEL_DYNAMIC:
                # Dual-axis chart: Load demand (kW) vs. synchronous EPEX Spot Price (€/MWh)
                spot_eur_mwh = spot_prices * 1000.0
                fig_dyn = create_dynamic_price_consumption_figure(
                    timestamps=load_series.timestamps,
                    power_kw=load_series.power_kw,
                    spot_prices_eur_mwh=spot_eur_mwh,
                    title_suffix=f"({actual_profile_days:.0f} Days)"
                )
                st.plotly_chart(fig_dyn, use_container_width=True)
            else:
                # 24h Diurnal load schedule with HT/NT window adapting to configured hours
                fig_diurnal = create_tou_schedule_diurnal_figure(
                    load=load_series,
                    ht_start_hour=ht_start_hour_supp,
                    ht_end_hour=ht_end_hour_supp,
                    ht_rate_label=f"High Tariff HT ({fixed_rate_ht:.4f} €/kWh)",
                    nt_rate_label=f"Off-Peak NT ({fixed_rate_nt:.4f} €/kWh)"
                )
                st.plotly_chart(fig_diurnal, use_container_width=True)

        with col_vis_right:
            st.markdown("###### :material/table_chart: Pure Supplier Settlement Statement")

            # Construct itemized monthly settlement rows
            billing_rows = []
            month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
            for m in range(1, 13):
                m_mask = (load_series.month_indices == m)
                m_kwh = float(np.sum(load_series.energy_kwh[m_mask]))
                if m_kwh <= 0.0:
                    continue

                m_ht_kwh = float(np.sum(load_series.energy_kwh[m_mask & ht_mask]))
                m_nt_kwh = float(np.sum(load_series.energy_kwh[m_mask & ~ht_mask]))

                if selected_model_type == MODEL_DUAL:
                    m_ecost = (m_ht_kwh * fixed_rate_ht) + (m_nt_kwh * fixed_rate_nt) + (m_kwh * surcharge_kwh)
                elif selected_model_type == MODEL_SINGLE:
                    m_ecost = (m_kwh * fixed_rate_val) + (m_kwh * surcharge_kwh)
                else:
                    m_all_in = spot_prices[m_mask] + supp_margin + surcharge_kwh
                    m_ecost = float(np.sum(load_series.energy_kwh[m_mask] * m_all_in))

                # Monthly standing fee allocation
                if is_actual_horizon:
                    # Days in this month contained in profile
                    m_days = len(np.unique(load_series.timestamps[m_mask].date))
                    m_base = supp_base * (m_days / 365.0)
                else:
                    m_base = supp_base / 12.0
                    m_kwh = m_kwh * scale_fac
                    m_ht_kwh = m_ht_kwh * scale_fac
                    m_nt_kwh = m_nt_kwh * scale_fac
                    m_ecost = m_ecost * scale_fac

                m_total = m_ecost + m_base
                m_eff_rate = m_total / max(1.0, m_kwh)

                billing_rows.append({
                    "Period": month_names[m - 1],
                    "Total (kWh)": f"{m_kwh:,.0f}",
                    "HT (kWh)": f"{m_ht_kwh:,.0f}",
                    "NT (kWh)": f"{m_nt_kwh:,.0f}",
                    "Energy (€)": f"€ {m_ecost:,.2f}",
                    "Base (€)": f"€ {m_base:,.2f}",
                    "Supplier Total (€)": f"€ {m_total:,.2f}",
                    "Rate (€/kWh)": f"€ {m_eff_rate:.4f}"
                })

            # Append Consolidated Summary Row
            billing_rows.append({
                "Period": "TOTAL",
                "Total (kWh)": f"{horizon_kwh:,.0f}",
                "HT (kWh)": f"{horizon_ht_kwh:,.0f}",
                "NT (kWh)": f"{horizon_nt_kwh:,.0f}",
                "Energy (€)": f"€ {evaluated_energy_cost:,.2f}",
                "Base (€)": f"€ {base_fee_evaluated:,.2f}",
                "Supplier Total (€)": f"€ {supplier_net_total:,.2f}",
                "Rate (€/kWh)": f"€ {effective_commodity_rate:.4f}"
            })

            df_billing = pd.DataFrame(billing_rows)
            st.dataframe(df_billing, use_container_width=True, hide_index=True)

            st.caption(
                ":material/security: Pure supplier view strictly excludes DSO network tariffs, "
                "metering telemetry services, energy taxes (EB) and statutory VAT."
            )

    # ----------------------------------------------------------------------------------
    # Sub-Tab 3: Metering Company & Taxes
    # ----------------------------------------------------------------------------------
    with actor_tabs[2]:
        st.markdown("##### Certified Metering, Statutory Energy Levies & Lifecycle Economics")

        col_m_co, col_m_pkg = st.columns([1.5, 2.5])
        with col_m_co:
            meter_options = list(METERING_CATALOG_2025.keys()) + ["Custom Meetbedrijf"]
            selected_meter_name = st.selectbox(
                "Metering Company (Erkend Meetbedrijf):",
                options=meter_options,
                index=0,
                key=f"{key_prefix}_meter_name_select"
            )

        with col_m_pkg:
            if selected_meter_name in METERING_CATALOG_2025:
                pkg_dict = METERING_CATALOG_2025[selected_meter_name]
                pkg_options = list(pkg_dict.keys())
                selected_pkg = st.selectbox(
                    "Service Package & Meter Type:",
                    options=pkg_options,
                    index=0,
                    key=f"{key_prefix}_meter_pkg_{selected_meter_name}"
                )
                pkg_data = pkg_dict[selected_pkg]
                st.caption(f":material/info: *{pkg_data.get('description', '')}*")
            else:
                selected_pkg = "Custom Metering Package"
                pkg_data = {"annual_flat_fee": 900.00, "description": "Custom metering contract"}
                st.caption(":material/tune: *Custom metering and telemetry fees.*")

        st.markdown("---")

        col_m1, col_m2 = st.columns(2)
        with col_m1:
            meter_annual = st.number_input(
                "Annual Telemetry & Meter Flat Fee (€/year):",
                min_value=0.0,
                value=float(pkg_data.get("annual_flat_fee", 900.00)),
                step=50.0,
                key=f"{key_prefix}_meter_annual_{selected_meter_name}_{selected_pkg}",
                help="Kwartierdata telemetrie en meterhuur per jaar excl. btw"
            )
        with col_m2:
            st.info(
                f":material/speed: **Monthly Metering Equivalent:** € {meter_annual / 12.0:,.2f} / month | "
                f"**Service:** {selected_pkg}",
                icon=":material/speed:"
            )

        st.markdown("##### Statutory Energy Levies & VAT (Belastingen)")
        col_tax1, col_tax2, col_tax3 = st.columns(3)
        with col_tax1:
            levy_rate = st.number_input(
                "Statutory Energy Levies (€/kWh):",
                min_value=0.0,
                value=0.0125,
                format="%.4f",
                key=f"{key_prefix}_levy_rate",
                help="Energiebelasting en wettelijke heffingen (indicatieve basisschijf)"
            )
        with col_tax2:
            tax_reduction = st.number_input(
                "Tax Reduction Credit Vermindering (€/year):",
                min_value=0.0,
                value=0.0,
                step=50.0,
                key=f"{key_prefix}_tax_reduction",
                help="Vermindering energiebelasting (Heffingskorting € 631,39 voor aansluitingen met verblijfsfunctie, € 0 voor zuiver zakelijk)"
            )
        with col_tax3:
            vat_rate = st.number_input(
                "Value Added Tax (VAT %):",
                min_value=0.0,
                max_value=100.0,
                value=21.0,
                step=1.0,
                key=f"{key_prefix}_vat_rate",
                help="Btw-tarief (21% in Nederland)"
            )

        st.markdown("##### 15-Year Lifecycle TCO Economics (Wirtschaftlichkeit)")
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

    st.markdown("---")



    # ----------------------------------------------------------------------------------
    # 3. Assemble Configuration & Execute 5-Layer 2025 Accounting
    # ----------------------------------------------------------------------------------
    # Connection fee is omitted for now (set to € 0.00); entire monthly fee represents fixed transport standing charge (Vastrecht)
    fixed_conn = 0.0
    fixed_trans = base_fee * 12.0

    dso_tariff = DSOTariff(
        dso_name=selected_dso_company,
        grid_tier=selected_tier,
        connection_category="standard",
        fixed_connection_annual=fixed_conn,
        fixed_transport_annual=fixed_trans,
        cable_surcharge_annual=0.0,
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
        pricing_mode=active_pricing_mode,
        tariff_product_name=selected_product,
        base_fee_annual=supp_base,
        fixed_rate_kwh=fixed_rate_val,
        is_dual_rate=is_dual_rate,
        fixed_rate_peak_kwh=fixed_rate_ht,
        fixed_rate_offpeak_kwh=fixed_rate_nt,
        procurement_fee_kwh=procure_fee,
        green_certificate_surcharge_kwh=green_surcharge,
        monthly_variable_rates=prod_data.get("monthly_variable_rates", [0.125] * 12),
        market_price_profile_id="epex_nl_2025",
        supplier_margin_kwh=supp_margin,
        spot_default_fallback_rate=0.1200,
    )
    metering_tariff = MeteringTariff(
        meter_company_name=selected_meter_name,
        service_package_name=selected_pkg,
        annual_flat_fee=meter_annual,
        description=pkg_data.get("description", ""),
    )
    levy_config = LevyConfig(
        statutory_levy_rate_kwh=levy_rate,
        annual_tax_reduction=tax_reduction,
        vat_rate_pct=vat_rate,
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
    )

    result = calculate_status_quo_master_2025(load=load_series, config=active_config)
    audit_report = perform_full_status_quo_audit(load=load_series, result=result)

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
            supp_cost = target_rec.commercial.supplier_energy_cost + target_rec.commercial.supplier_base_fee
            render_kpi_card(
                title=f":material/account_tree: {selected_period} Actor Split",
                value=f"DSO: € {target_rec.dso.subtotal_dso_net:,.0f}",
                subtext=f"Supp: € {supp_cost:,.0f} | Meter: € {target_rec.commercial.metering_fee:,.0f}",
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
        st.warning(
            f":material/warning: **Capacity Breach Detected**: Recorded peak in month(s) "
            f"{result.breach_months} exceeded reserved grid capacity ({contracted_kw:.1f} kW). "
            f"Under Dutch grid regulation, capacity fee was adjusted to the actual measured peak for those months.",
            icon=":material/warning:"
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
    st.markdown("### :material/table_view: 12-Month Accounting Statement Table")

    table_data = []
    for r in result.monthly_records:
        table_data.append({
            "Month": r.month_name,
            "Consumption (kWh)": round(r.consumption.total_kwh, 1),
            "Peak kW (P_max)": round(r.consumption.peak_demand_kw, 1),
            "DSO Net (€)": round(r.dso.subtotal_dso_net, 2),
            "Supplier Net (€)": round(r.commercial.supplier_energy_cost + r.commercial.supplier_base_fee, 2),
            "Metering Net (€)": round(r.commercial.metering_fee, 2),
            "Levies Net (€)": round(r.commercial.statutory_levies, 2),
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
    base_meter_taxes = float(result.total_metering_net) + float(result.total_levies_net)
    base_kwh = float(result.total_consumption_kwh)

    tco_15_rows = []
    cum_nominal_spend = 0.0
    for i in range(horizon_years):
        esc_factor = (1.0 + g_rate) ** i
        disc_factor = 1.0 / ((1.0 + r_rate) ** (i + 1))

        dso_y = round(base_dso * esc_factor, 2)
        supp_y = round(base_supp * esc_factor, 2)
        met_y = round(base_meter_taxes * esc_factor, 2)
        tot_y = round(dso_y + supp_y + met_y, 2)
        cum_nominal_spend += tot_y
        pv_y = round(tot_y * disc_factor, 2)
        blended_y = round((tot_y / base_kwh), 4) if base_kwh > 0 else 0.0

        tco_15_rows.append({
            "Period": f"Year {i + 1}",
            "Calendar Year": start_calendar_year + i,
            "DSO Grid (€)": dso_y,
            "Supplier (€)": supp_y,
            "Metering & Taxes (€)": met_y,
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
