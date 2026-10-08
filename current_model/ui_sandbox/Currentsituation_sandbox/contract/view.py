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
    )
except ImportError:
    try:
        from ui.common.styles import apply_custom_styles
        from ui.common.cards import render_kpi_card
        from ui_sandbox.Currentsituation_sandbox.contract.charts import (
            create_monthly_payment_series_figure,
            create_cost_donut_figure,
            create_tou_schedule_diurnal_figure,
        )
    except ImportError:
        from current_model.ui.common.styles import apply_custom_styles
        from current_model.ui.common.cards import render_kpi_card
        from contract.charts import (
            create_monthly_payment_series_figure,
            create_cost_donut_figure,
            create_tou_schedule_diurnal_figure,
        )

# 2025 5-Layer Accounting Modules & Official Catalogs
try:
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
    )
    from ui_sandbox.status_quo_2025.status_quo_master import (
        calculate_status_quo_master_2025,
        convert_to_financial_cost_breakdown,
    )
    from ui_sandbox.status_quo_2025.audit import perform_full_status_quo_audit
except ImportError:
    from current_model.ui_sandbox.status_quo_2025.config_and_models import (
        TariffStage,
        PricingMode,
        DSOTariff,
        SupplierTariff,
        MeteringTariff,
        LevyConfig,
        StatusQuoConfig2025,
        LoadSeries2025,
    )
    from current_model.ui_sandbox.status_quo_2025.tariff_defaults_2025 import (
        DSO_CATALOGS_2025,
        SUPPLIER_CATALOG_2025,
        METERING_CATALOG_2025,
        get_dso_tariff_from_catalog,
        get_stage_1_default_config_2025,
        get_default_supplier_tariff_2025,
        get_default_metering_tariff_2025,
        get_default_levy_config_2025,
    )
    from current_model.ui_sandbox.status_quo_2025.consumption_pipeline import (
        normalize_load_profile_2025,
        synthesize_benchmark_load_profile_2025,
    )
    from current_model.ui_sandbox.status_quo_2025.status_quo_master import (
        calculate_status_quo_master_2025,
        convert_to_financial_cost_breakdown,
    )
    from current_model.ui_sandbox.status_quo_2025.audit import perform_full_status_quo_audit


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

        st.markdown("---")

        # ==============================================================================
        # 1. General & Active Capacity Parameters
        # ==============================================================================
        st.subheader("1. General & Active Capacity Parameters")

        dso_contract_name_default = f"{selected_dso_company} - {selected_tier} (2025)"
        contract_name_val = st.text_input(
            "Contract Name / Identifier:",
            value=dso_contract_name_default,
            key=f"{key_prefix}_dso_name_val_{selected_dso_company}_{selected_tier}",
            help="Custom name or tariff identifier for the regulated grid operator contract."
        )

        c1, c2 = st.columns(2)
        with c1:
            curr_options = ["EUR", "USD", "GBP", "CHF", "ARS"]
            currency = st.selectbox(
                "Currency:",
                options=curr_options,
                index=0,
                key=f"{key_prefix}_dso_currency"
            )
            # Default monthly standing charges = (aansluitdienst + vastrecht) / 12
            ann_standing_default = float(preset_data.get("aansluitdienst_annual", 1653.0) + preset_data.get("vastrecht_annual", 441.0))
            monthly_standing_default = round(ann_standing_default / 12.0, 2)
            base_fee = st.number_input(
                "Base Monthly Fee (Cargo Comercialización):",
                min_value=0.0,
                value=monthly_standing_default,
                step=5.0,
                format="%.2f",
                key=f"{key_prefix}_dso_base_fee_{selected_dso_company}_{selected_tier}",
                help="Fixed monthly standing charges (Vastrecht + Aansluitdienst maandbedrag)"
            )
            contracted_kw = st.number_input(
                "Contracted Active Capacity (kW - Potencia Contratada):",
                min_value=10.0,
                max_value=20000.0,
                value=float(max(50.0, round(load_series.peak_demand_kw * 1.05, 0))),
                step=10.0,
                format="%.1f",
                key=f"{key_prefix}_dso_p_contract",
                help="Gecontracteerd transportvermogen in kW"
            )

        with c2:
            capacity_tariff = st.number_input(
                "Contracted Capacity Tariff (/kW/month - Uso de Red):",
                min_value=0.0,
                value=float(preset_data.get("rate_contracted_monthly", 2.4400)),
                step=0.01,
                format="%.4f",
                key=f"{key_prefix}_dso_rate_cap_{selected_dso_company}_{selected_tier}",
                help="Capaciteitstarief per kW gecontracteerd vermogen per maand"
            )
            demand_tariff = st.number_input(
                "Measured Demand Tariff (/kW/month - Consumo de Potencia):",
                min_value=0.0,
                value=float(preset_data.get("rate_peak_monthly", 3.7100)),
                step=0.01,
                format="%.4f",
                key=f"{key_prefix}_dso_rate_peak_{selected_dso_company}_{selected_tier}",
                help="Piekvermogenstarief per kW maandelijks gemeten maximum vermogen"
            )
            max_physical_kw = st.number_input(
                "Max Physical Limit (kW):",
                min_value=10.0,
                value=float(preset_data.get("max_physical_limit_kw", 1000.0)),
                step=50.0,
                format="%.1f",
                key=f"{key_prefix}_dso_max_phys_{selected_dso_company}_{selected_tier}",
                help="Fysieke aansluitcapaciteit van de transformator (kVA / kW limit)"
            )
            penalty_rate = st.number_input(
                "Peak Penalty Rate (/kW - Exceso de Potencia):",
                min_value=0.0,
                value=float(preset_data.get("peak_penalty_rate_kw", 0.2500)),
                step=0.05,
                format="%.4f",
                key=f"{key_prefix}_dso_penalty_{selected_dso_company}_{selected_tier}",
                help="Tarief bij contractoverschrijding per kW boven gecontracteerd vermogen"
            )

        # ==============================================================================
        # 2. Reactive Power Parameters
        # ==============================================================================
        st.subheader("2. Reactive Power Parameters")
        q1, q2, q3 = st.columns(3)
        with q1:
            reactive_tariff = st.number_input(
                "Reactive Energy Tariff (/kVARh):",
                min_value=0.0,
                value=float(preset_data.get("reactive_tariff", 0.0188)),
                step=0.005,
                format="%.4f",
                key=f"{key_prefix}_dso_reactive_{selected_dso_company}_{selected_tier}",
                help="Blindvermogenstarief per kVARh buiten toegestane arbeidsfactor"
            )
        with q2:
            min_cos_phi = st.number_input(
                "Min Power Factor (cos phi):",
                min_value=0.50,
                max_value=1.00,
                value=float(preset_data.get("min_power_factor", 0.90)),
                step=0.02,
                format="%.2f",
                key=f"{key_prefix}_dso_cosphi_{selected_dso_company}_{selected_tier}",
                help="Minimale arbeidsfactor cos phi zonder blindvermogenstoeslag"
            )
        with q3:
            reactive_allowance = st.number_input(
                "Reactive Allowance (% of kWh):",
                min_value=0.0,
                max_value=100.0,
                value=float(preset_data.get("reactive_allowance_pct", 33.0)),
                step=1.0,
                format="%.1f",
                key=f"{key_prefix}_dso_q_allow_{selected_dso_company}_{selected_tier}",
                help="Toegestane vrije hoeveelheid reactieve energie als percentage van werkelijk verbruik"
            )

        # ==============================================================================
        # 3. Time-of-Use (TOU) Energy Rates
        # ==============================================================================
        st.subheader("3. Time-of-Use (TOU) Energy Rates")
        st.caption("Define Time-of-Use rate windows for network transport services:")

        t1, t2 = st.columns(2)
        with t1:
            trans_norm_kwh = st.number_input(
                "High Tariff Rate HT / Normaal (€/kWh):",
                min_value=0.0,
                value=float(preset_data.get("rate_peak_kwh", 0.0250)),
                step=0.001,
                format="%.4f",
                key=f"{key_prefix}_dso_trans_ht_{selected_dso_company}_{selected_tier}",
                help="Transporttarief normaalvenster (werkdagen 07:00 - 23:00)"
            )
        with t2:
            trans_off_kwh = st.number_input(
                "Off-Peak Rate NT / Dal (€/kWh):",
                min_value=0.0,
                value=float(preset_data.get("rate_offpeak_kwh", 0.0250)),
                step=0.001,
                format="%.4f",
                key=f"{key_prefix}_dso_trans_nt_{selected_dso_company}_{selected_tier}",
                help="Transporttarief dalvenster (nachten en weekenden)"
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

        st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
        if st.button("Save Contract Configuration", icon=":material/save:", type="primary", use_container_width=True, key=f"{key_prefix}_save_dso_btn"):
            st.success(f"Grid Operator configuration saved: **{contract_name_val}**")

    # ----------------------------------------------------------------------------------
    # Sub-Tab 2: Energy Retailer (Supplier)
    # ----------------------------------------------------------------------------------
    with actor_tabs[1]:
        st.markdown("##### Commercial Energy Supply Contract (Commodity Rates & Retail Pricing)")

        col_supp_co, col_supp_prod = st.columns([1.5, 2.5])
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

        col_smode, col_sbase = st.columns([2.5, 1.5])
        with col_smode:
            default_mode = prod_data.get("pricing_mode", PricingMode.FIXED)
            mode_idx = 0 if default_mode == PricingMode.DYNAMIC else (1 if default_mode == PricingMode.FIXED else 2)
            selected_pricing_mode_str = st.radio(
                "Supplier Pricing Mechanism:",
                options=[
                    ":material/show_chart: Dynamic Spot (EPEX Spot NL 2025)",
                    ":material/lock: Fixed All-In Rate",
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
            else:
                active_pricing_mode = PricingMode.VARIABLE

        with col_sbase:
            supp_base = st.number_input(
                "Retailer Standing Fee (€/year):",
                min_value=0.0,
                value=float(prod_data.get("base_fee_annual", 180.00)),
                step=15.0,
                key=f"{key_prefix}_supp_base_{selected_supplier_name}_{selected_product}",
                help="Vastrecht levering per jaar excl. btw"
            )

        st.markdown("---")

        col_s1, col_s2, col_s3 = st.columns(3)
        with col_s1:
            green_surcharge = st.number_input(
                "Green Power Surcharge GvO (€/kWh):",
                min_value=0.0,
                value=float(prod_data.get("green_surcharge_kwh", 0.0)),
                format="%.4f",
                key=f"{key_prefix}_supp_green_{selected_supplier_name}_{selected_product}",
                help="Garantie van Oorsprong (GvO) opslag voor 100% Nederlandse groene stroom"
            )

        with col_s2:
            if active_pricing_mode == PricingMode.DYNAMIC:
                supp_margin = st.number_input(
                    "Supplier Retail Markup / Opslag (€/kWh):",
                    min_value=0.0,
                    value=float(prod_data.get("supplier_margin_kwh", 0.0075)),
                    format="%.4f",
                    key=f"{key_prefix}_supp_margin_{selected_supplier_name}_{selected_product}",
                    help="Leveranciersopslag bovenop de EPEX Spot Day-Ahead uur-/kwartierprijs"
                )
                procure_fee = st.number_input(
                    "Procurement Fee (€/kWh):",
                    min_value=0.0,
                    value=float(prod_data.get("procurement_fee_kwh", 0.0015)),
                    format="%.4f",
                    key=f"{key_prefix}_supp_procure_{selected_supplier_name}_{selected_product}",
                    help="Vaste inkoopvergoeding per kWh"
                )
                is_dual_rate = False
                fixed_rate_val = 0.1250
                fixed_rate_ht = 0.1340
                fixed_rate_nt = 0.1180
            elif active_pricing_mode == PricingMode.FIXED:
                is_dual_rate = st.checkbox(
                    ":material/contrast: Dual Rate (Dubbeltarief: HT / NT)",
                    value=bool(prod_data.get("is_dual_rate", False)),
                    key=f"{key_prefix}_supp_is_dual_{selected_supplier_name}_{selected_product}",
                    help="Vink aan voor afzonderlijke tarieven voor piekuren (normaaltarief) en daluren (daltarief)."
                )
                if is_dual_rate:
                    fixed_rate_ht = st.number_input(
                        "High Tariff Rate HT / Normaal (€/kWh):",
                        min_value=0.0,
                        value=float(prod_data.get("rate_peak_kwh", 0.1340)),
                        format="%.4f",
                        key=f"{key_prefix}_supp_ht_{selected_supplier_name}_{selected_product}",
                        help="Tarief actieve energie tijdens werkdagen 07:00 - 23:00"
                    )
                    fixed_rate_val = fixed_rate_ht
                else:
                    fixed_rate_val = st.number_input(
                        "Fixed Active Energy Rate (€/kWh):",
                        min_value=0.0,
                        value=float(prod_data.get("fixed_rate_kwh", 0.1250)),
                        format="%.4f",
                        key=f"{key_prefix}_supp_fixed_rate_{selected_supplier_name}_{selected_product}",
                        help="Uniforme vaste leveringsprijs per actief kilowattuur"
                    )
                    fixed_rate_ht = fixed_rate_val
                supp_margin = 0.0
                procure_fee = 0.0
            else:
                st.caption(":material/calendar_month: *Using 12-month variable rate schedule.*")
                is_dual_rate = False
                fixed_rate_val = 0.1250
                fixed_rate_ht = 0.1340
                fixed_rate_nt = 0.1180
                supp_margin = 0.0
                procure_fee = 0.0

        with col_s3:
            if active_pricing_mode == PricingMode.FIXED and is_dual_rate:
                fixed_rate_nt = st.number_input(
                    "Off-Peak Rate NT / Dal (€/kWh):",
                    min_value=0.0,
                    value=float(prod_data.get("rate_offpeak_kwh", 0.1180)),
                    format="%.4f",
                    key=f"{key_prefix}_supp_nt_{selected_supplier_name}_{selected_product}",
                    help="Tarief actieve energie tijdens nachten (23:00 - 07:00) en weekenden (24h)"
                )
            elif active_pricing_mode == PricingMode.DYNAMIC:
                st.caption(":material/hub: *EPEX Spot wholesale series linked to Europe/Amsterdam timezone.*")

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
    # 2. Prominent Time-of-Use (TOU) Segment Visualizer & Inspection
    # ----------------------------------------------------------------------------------
    st.markdown("### :material/schedule: Time-of-Use (TOU) Segments & Diurnal Energy Split")

    # Compute exact TOU consumption volumes
    ht_mask = load_series.is_peak_tou
    nt_mask = ~ht_mask
    ht_kwh = float(np.sum(load_series.energy_kwh[ht_mask]))
    nt_kwh = float(np.sum(load_series.energy_kwh[nt_mask]))
    tot_kwh = ht_kwh + nt_kwh
    ht_pct = (ht_kwh / tot_kwh * 100.0) if tot_kwh > 0 else 0.0
    nt_pct = (nt_kwh / tot_kwh * 100.0) if tot_kwh > 0 else 0.0
    ht_peak = float(np.max(load_series.power_kw[ht_mask])) if np.any(ht_mask) else 0.0
    nt_peak = float(np.max(load_series.power_kw[nt_mask])) if np.any(nt_mask) else 0.0

    col_tou1, col_tou2, col_tou3 = st.columns(3)
    with col_tou1:
        render_kpi_card(
            title=":material/light_mode: High Tariff (HT / Normaal)",
            value=f"{ht_kwh:,.1f} kWh",
            subtext=f"Share: {ht_pct:.1f}% | Peak: {ht_peak:.1f} kW",
            status="default"
        )
    with col_tou2:
        render_kpi_card(
            title=":material/dark_mode: Off-Peak (NT / Dal / Laag)",
            value=f"{nt_kwh:,.1f} kWh",
            subtext=f"Share: {nt_pct:.1f}% | Peak: {nt_peak:.1f} kW",
            status="default"
        )
    with col_tou3:
        render_kpi_card(
            title=":material/event: Active TOU Window Schedule",
            value="Mo-Fr 07:00 - 23:00",
            subtext="Off-Peak: Nights (23:00-07:00) & Weekends (24h)",
            status="ok"
        )

    # Interactive 24-hour diurnal profile chart with shaded TOU bands
    tou_fig = create_tou_schedule_diurnal_figure(load_series, ht_start_hour=7, ht_end_hour=23)
    st.plotly_chart(tou_fig, use_container_width=True)

    st.markdown("---")

    # ----------------------------------------------------------------------------------
    # 3. Assemble Configuration & Execute 5-Layer 2025 Accounting
    # ----------------------------------------------------------------------------------
    # Decompose monthly base fee into fixed connection and transport
    preset_conn_ann = float(preset_data.get("aansluitdienst_annual", 0.0))
    preset_vast_ann = float(preset_data.get("vastrecht_annual", 0.0))
    tot_preset_ann = preset_conn_ann + preset_vast_ann
    ratio_conn = (preset_conn_ann / tot_preset_ann) if tot_preset_ann > 0 else 0.79
    total_base_ann = base_fee * 12.0
    fixed_conn = total_base_ann * ratio_conn
    fixed_trans = total_base_ann * (1.0 - ratio_conn)

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
    # 5. 14-Criteria / 4-Point Audit Expander
    # ----------------------------------------------------------------------------------
    audit_icon = ":material/verified:" if audit_report.passed_all else ":material/error:"
    audit_title = f"{audit_icon} Verification Protocol: {audit_report.passed_criteria_count}/{audit_report.total_criteria_count} Checks Passed"
    with st.expander(audit_title, expanded=not audit_report.passed_all):
        st.markdown(audit_report.to_markdown(), unsafe_allow_html=True)
        if result.has_capacity_breach:
            st.warning(
                f":material/warning: Capacity Breach Detected: Recorded maximum peak in month(s) "
                f"{result.breach_months} exceeded contracted capacity limit ({contracted_kw:.1f} kW). "
                f"Capacity fee was billed on actual measured peak for these months under Dutch tariff rules.",
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
    # 8. Export Toolbar (CSV & JSON)
    # ----------------------------------------------------------------------------------
    col_exp1, col_exp2, col_exp3 = st.columns(3)
    with col_exp1:
        csv_buf = io.StringIO()
        df_table.to_csv(csv_buf, index=False, sep=";")
        st.download_button(
            label=":material/download: Export 12-Month Statement (CSV)",
            data=csv_buf.getvalue(),
            file_name="status_quo_2025_statement.csv",
            mime="text/csv",
            key=f"{key_prefix}_export_csv"
        )
    with col_exp2:
        export_payload = {
            "evaluation_year": 2025,
            "total_consumption_kwh": result.total_consumption_kwh,
            "total_status_quo_net": result.total_status_quo_net,
            "total_status_quo_gross": result.total_status_quo_gross,
            "blended_price_net_kwh": result.blended_price_net_kwh,
            "tco_15_npv": result.tco_15_npv,
            "audit_passed_all": audit_report.passed_all,
            "monthly_records": table_data
        }
        json_str = json.dumps(export_payload, indent=2)
        st.download_button(
            label=":material/download: Export Accounting Audit (JSON)",
            data=json_str,
            file_name="status_quo_2025_audit.json",
            mime="application/json",
            key=f"{key_prefix}_export_json"
        )
    with col_exp3:
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
            label=":material/save: Export Contract Terms (JSON)",
            data=json.dumps(contract_payload, indent=2),
            file_name="unbundled_contract_2025.json",
            mime="application/json",
            key=f"{key_prefix}_export_contract"
        )

    return result


def render_tab2_contract(key_prefix: str = "currsit_contract") -> Any:
    """Alias for render_tab2_base_contract."""
    return render_tab2_base_contract(key_prefix=key_prefix)


def render_tab2_contract_switch(key_prefix: str = "currsit_contract") -> Any:
    """Compatibility switch alias rendering the base contract."""
    return render_tab2_base_contract(key_prefix=key_prefix)
