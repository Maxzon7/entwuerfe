"""
========================================================================================
Status Quo 2025 Interactive Laboratory (status_quo_lab.py)
========================================================================================
Interactive Streamlit laboratory providing end-to-end testing, audit verification,
and unbundled commercial billing visualization for the reference year 2025.
Follows strict project UI standards:
  - English UI text
  - Native Streamlit Material Symbols (:material/<icon_name>:)
  - Two-stage switch: Stage 1 (Default Benchmark) vs Stage 2 (Custom Quote)
  - Full automated audit protocol (Audit Points 1 to 4)
  - Stacked monthly billing charts and itemized table exports
========================================================================================
"""

import os
import sys
import io
import json
from typing import Optional, Dict, Any

import streamlit as st
import pandas as pd
import numpy as np

# Ensure project root, current_model, and sandbox directories are on sys.path for direct execution
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
SANDBOX_DIR = os.path.abspath(os.path.join(THIS_DIR, ".."))
CURRENT_MODEL_DIR = os.path.abspath(os.path.join(SANDBOX_DIR, ".."))
WORKSPACE_ROOT = os.path.abspath(os.path.join(CURRENT_MODEL_DIR, ".."))

for path in [WORKSPACE_ROOT, CURRENT_MODEL_DIR, SANDBOX_DIR, THIS_DIR]:
    if path not in sys.path:
        sys.path.insert(0, path)

try:
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
        get_stage_1_default_config_2025,
        get_liander_2025_dso_defaults,
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
except ImportError:
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
            get_stage_1_default_config_2025,
            get_liander_2025_dso_defaults,
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
        from config_and_models import (
            TariffStage,
            PricingMode,
            DSOTariff,
            SupplierTariff,
            MeteringTariff,
            LevyConfig,
            StatusQuoConfig2025,
            LoadSeries2025,
        )
        from tariff_defaults_2025 import (
            get_stage_1_default_config_2025,
            get_liander_2025_dso_defaults,
            get_default_supplier_tariff_2025,
            get_default_metering_tariff_2025,
            get_default_levy_config_2025,
        )
        from consumption_pipeline import (
            normalize_load_profile_2025,
            synthesize_benchmark_load_profile_2025,
        )
        from status_quo_master import (
            calculate_status_quo_master_2025,
            convert_to_financial_cost_breakdown,
        )
        from audit import perform_full_status_quo_audit

# Project UI components
try:
    from current_model.ui.common.styles import apply_custom_styles
    from current_model.ui.common.cards import render_kpi_card
    from current_model.ui.tab2_contract.charts import (
        create_monthly_payment_series_figure,
        create_cost_donut_figure,
    )
    from current_model.core.csv_parser import parse_csv_content, detect_suggested_columns
except ImportError:
    from ui.common.styles import apply_custom_styles
    from ui.common.cards import render_kpi_card
    from ui.tab2_contract.charts import (
        create_monthly_payment_series_figure,
        create_cost_donut_figure,
    )
    from core.csv_parser import parse_csv_content, detect_suggested_columns


def render_status_quo_lab(key_prefix: str = "sq2025") -> None:
    """Renders the complete 2025 Status Quo Accounting & Audit Laboratory."""
    st.markdown("## :material/account_balance: Status Quo 2025 Laboratory")
    st.caption(
        "Unbundled European commercial electricity accounting & 15-year lifecycle TCO verification "
        "for the reference year 2025 (35,040 intervals @ 15 min)."
    )

    # ----------------------------------------------------------------------------------
    # 1. Stage Selector (Stage 1 Benchmark Defaults vs Stage 2 Custom Quote)
    # ----------------------------------------------------------------------------------
    col_stage, col_mode = st.columns([1.5, 1.5])
    with col_stage:
        selected_stage = st.radio(
            "Tariff Sourcing Level:",
            options=[
                ":material/verified: Stage 1: Default Benchmark (Liander 2025)",
                ":material/request_quote: Stage 2: Custom Quote / Contract Overrides"
            ],
            index=0,
            key=f"{key_prefix}_stage_selector",
            horizontal=True
        )
        is_stage_2 = "Stage 2" in selected_stage
        active_stage = TariffStage.STAGE_2_QUOTE if is_stage_2 else TariffStage.STAGE_1_DEFAULT

    with col_mode:
        selected_pricing_mode_str = st.selectbox(
            "Supplier Pricing Mechanism:",
            options=["Dynamic Spot (EPEX NL 2025)", "Fixed All-In Rate", "Variable Monthly Rates"],
            index=0,
            key=f"{key_prefix}_pricing_mode_select"
        )
        if "Dynamic" in selected_pricing_mode_str:
            active_pricing_mode = PricingMode.DYNAMIC
        elif "Fixed" in selected_pricing_mode_str:
            active_pricing_mode = PricingMode.FIXED
        else:
            active_pricing_mode = PricingMode.VARIABLE

    st.markdown("---")

    # ----------------------------------------------------------------------------------
    # 2. Consumption Ingestion & Profile Management
    # ----------------------------------------------------------------------------------
    st.markdown("### :material/upload_file: 1. Consumption Profile Ingestion (Year 2025)")

    load_source = st.radio(
        "Load Profile Source:",
        options=[
            ":material/science: Commercial Benchmark Simulation (35,040 intervals)",
            ":material/file_upload: Upload 15-Minute CSV Meter File"
        ],
        horizontal=True,
        key=f"{key_prefix}_load_source_radio"
    )

    load_series: Optional[LoadSeries2025] = None
    diagnostics: Dict[str, Any] = {}

    if "Benchmark Simulation" in load_source:
        col_bench_kw, col_bench_info = st.columns([1, 2])
        with col_bench_kw:
            bench_peak_kw = st.number_input(
                "Facility Nominal Peak Power (kW):",
                min_value=10.0,
                max_value=5000.0,
                value=250.0,
                step=25.0,
                key=f"{key_prefix}_bench_peak_kw"
            )
        with col_bench_info:
            st.info(
                f"Generating a calibrated 35,040-interval annual commercial profile (Mo-Fr operations, "
                f"24/7 cold storage baseload, summer-heavy cooling) scaled to {bench_peak_kw:.1f} kW peak.",
                icon=":material/info:"
            )

        load_series = synthesize_benchmark_load_profile_2025(
            profile_type="commercial_hvac",
            nominal_peak_kw=float(bench_peak_kw)
        )

    else:
        uploaded_file = st.file_uploader(
            "Upload 15-minute interval CSV file:",
            type=["csv", "txt"],
            key=f"{key_prefix}_csv_uploader"
        )
        if uploaded_file is not None:
            try:
                raw_bytes = uploaded_file.read()
                raw_text = raw_bytes.decode("utf-8-sig", errors="replace")
                parsed_df = parse_csv_content(raw_text)
                
                time_sug, power_sug, unit_sug = detect_suggested_columns(parsed_df)
                
                col_c1, col_c2 = st.columns(2)
                with col_c1:
                    sel_p_col = st.selectbox(
                        "Select Power / Demand Column:",
                        options=parsed_df.columns.tolist(),
                        index=parsed_df.columns.get_loc(power_sug[0]) if power_sug and power_sug[0] in parsed_df.columns else 0,
                        key=f"{key_prefix}_sel_p_col"
                    )
                with col_c2:
                    sel_t_col = st.selectbox(
                        "Select Date/Time Column:",
                        options=["Auto-Detect"] + parsed_df.columns.tolist(),
                        index=0,
                        key=f"{key_prefix}_sel_t_col"
                    )

                time_col_arg = None if sel_t_col == "Auto-Detect" else sel_t_col
                load_series, diagnostics = normalize_load_profile_2025(
                    raw_df=parsed_df,
                    power_col=sel_p_col,
                    time_col=time_col_arg
                )
                st.success(
                    f"Successfully normalized meter file to 35,040 intervals for 2025. "
                    f"Total Consumption: {load_series.total_energy_kwh:,.1f} kWh | Peak: {load_series.peak_demand_kw:,.1f} kW",
                    icon=":material/check_circle:"
                )

            except Exception as e:
                st.error(f"Error reading CSV file: {e}", icon=":material/error:")
                st.warning("Falling back to synthetic benchmark profile.", icon=":material/warning:")
                load_series = synthesize_benchmark_load_profile_2025(nominal_peak_kw=250.0)
        else:
            st.info("No file uploaded yet. Using default benchmark profile (250 kW peak).", icon=":material/info:")
            load_series = synthesize_benchmark_load_profile_2025(nominal_peak_kw=250.0)

    st.markdown("---")

    # ----------------------------------------------------------------------------------
    # 3. Tariff Parameters (Defaults or Stage 2 Custom Overrides)
    # ----------------------------------------------------------------------------------
    st.markdown("### :material/tune: 2. Unbundled Tariff Parameters & Contract Terms")

    # Initialize configuration
    default_cfg = get_stage_1_default_config_2025(
        pricing_mode=active_pricing_mode,
        contracted_capacity_kw=max(50.0, round(load_series.peak_demand_kw * 1.05, 0))
    )

    with st.expander(":material/settings: Inspect & Adjust Tariff Parameters", expanded=is_stage_2):
        tab_dso, tab_supp, tab_meter, tab_tco = st.tabs([
            ":material/grid_view: Regulated DSO (Liander)",
            ":material/bolt: Energy Retailer",
            ":material/speed: Metering & Taxes",
            ":material/analytics: 15-Year TCO Economics"
        ])

        with tab_dso:
            col_d1, col_d2, col_d3 = st.columns(3)
            with col_d1:
                contracted_kw = st.number_input(
                    "Contracted Capacity (kW - P_contract):",
                    min_value=10.0,
                    value=float(default_cfg.dso.contracted_capacity_kw),
                    step=10.0,
                    key=f"{key_prefix}_dso_p_contract"
                )
                rate_cap = st.number_input(
                    "Reserved Capacity Rate (€/kW/mo):",
                    min_value=0.0,
                    value=float(default_cfg.dso.rate_contracted_capacity),
                    format="%.4f",
                    key=f"{key_prefix}_dso_rate_cap"
                )
            with col_d2:
                rate_peak = st.number_input(
                    "Measured Peak Demand Rate (€/kW/mo):",
                    min_value=0.0,
                    value=float(default_cfg.dso.rate_peak_demand),
                    format="%.4f",
                    key=f"{key_prefix}_dso_rate_peak"
                )
                fixed_conn = st.number_input(
                    "Fixed Connection Fee (€/year):",
                    min_value=0.0,
                    value=float(default_cfg.dso.fixed_connection_annual),
                    step=50.0,
                    key=f"{key_prefix}_dso_fixed_conn"
                )
            with col_d3:
                fixed_trans = st.number_input(
                    "Fixed Transport Fee Vastrecht (€/year):",
                    min_value=0.0,
                    value=float(default_cfg.dso.fixed_transport_annual),
                    step=25.0,
                    key=f"{key_prefix}_dso_fixed_trans"
                )
                cable_surcharge = st.number_input(
                    "Cable Length Surcharge (€/year):",
                    min_value=0.0,
                    value=float(default_cfg.dso.cable_surcharge_annual),
                    step=50.0,
                    key=f"{key_prefix}_dso_cable_surcharge"
                )

            adjust_breach = st.checkbox(
                "Adjust capacity billing to actual peak during breach months (Dutch standard)",
                value=True,
                key=f"{key_prefix}_dso_adjust_breach"
            )

        with tab_supp:
            col_s1, col_s2 = st.columns(2)
            with col_s1:
                supp_name = st.text_input(
                    "Energy Retailer Name:",
                    value=default_cfg.supplier.supplier_name,
                    key=f"{key_prefix}_supp_name"
                )
                supp_base = st.number_input(
                    "Retailer Annual Standing Fee (€/year):",
                    min_value=0.0,
                    value=float(default_cfg.supplier.base_fee_annual),
                    step=15.0,
                    key=f"{key_prefix}_supp_base"
                )
            with col_s2:
                if active_pricing_mode == PricingMode.DYNAMIC:
                    supp_margin = st.number_input(
                        "Supplier Retail Markup / Opslag (€/kWh):",
                        min_value=0.0,
                        value=float(default_cfg.supplier.supplier_margin_kwh),
                        format="%.4f",
                        key=f"{key_prefix}_supp_margin"
                    )
                    fixed_rate_val = 0.1250
                elif active_pricing_mode == PricingMode.FIXED:
                    fixed_rate_val = st.number_input(
                        "Fixed Active Energy Rate (€/kWh):",
                        min_value=0.0,
                        value=float(default_cfg.supplier.fixed_rate_kwh),
                        format="%.4f",
                        key=f"{key_prefix}_supp_fixed_rate"
                    )
                    supp_margin = 0.0
                else:
                    st.caption("Using 12-month variable rate schedule.")
                    fixed_rate_val = 0.1250
                    supp_margin = 0.0

        with tab_meter:
            col_m1, col_m2 = st.columns(2)
            with col_m1:
                meter_name = st.text_input(
                    "Metering Company (Meetbedrijf):",
                    value=default_cfg.metering.meter_company_name,
                    key=f"{key_prefix}_meter_name"
                )
                meter_annual = st.number_input(
                    "Annual Metering & Telemetry Flat Fee (€/year):",
                    min_value=0.0,
                    value=float(default_cfg.metering.annual_flat_fee),
                    step=50.0,
                    key=f"{key_prefix}_meter_annual"
                )
            with col_m2:
                levy_rate = st.number_input(
                    "Statutory Energy Levies (€/kWh):",
                    min_value=0.0,
                    value=float(default_cfg.levies.statutory_levy_rate_kwh),
                    format="%.4f",
                    key=f"{key_prefix}_levy_rate"
                )
                vat_rate = st.number_input(
                    "Value Added Tax (VAT %):",
                    min_value=0.0,
                    max_value=100.0,
                    value=float(default_cfg.levies.vat_rate_pct),
                    step=1.0,
                    key=f"{key_prefix}_vat_rate"
                )

        with tab_tco:
            col_t1, col_t2 = st.columns(2)
            with col_t1:
                discount_rate = st.number_input(
                    "WACC / Discount Rate r (%):",
                    min_value=0.0,
                    max_value=25.0,
                    value=float(default_cfg.discount_rate_pct),
                    step=0.5,
                    key=f"{key_prefix}_tco_r"
                )
            with col_t2:
                escalation_rate = st.number_input(
                    "Annual Electricity Price Escalation g (%):",
                    min_value=0.0,
                    max_value=25.0,
                    value=float(default_cfg.energy_escalation_pct),
                    step=0.5,
                    key=f"{key_prefix}_tco_g"
                )

    # Assemble active configuration
    dso_tariff = DSOTariff(
        dso_name=default_cfg.dso.dso_name,
        grid_tier=default_cfg.dso.grid_tier,
        connection_category=default_cfg.dso.connection_category,
        fixed_connection_annual=fixed_conn,
        fixed_transport_annual=fixed_trans,
        cable_surcharge_annual=cable_surcharge,
        contracted_capacity_kw=contracted_kw,
        rate_contracted_capacity=rate_cap,
        rate_peak_demand=rate_peak,
        rate_transport_peak_kwh=default_cfg.dso.rate_transport_peak_kwh,
        rate_transport_offpeak_kwh=default_cfg.dso.rate_transport_offpeak_kwh,
        adjust_capacity_on_breach=adjust_breach,
    )
    supplier_tariff = SupplierTariff(
        supplier_name=supp_name,
        pricing_mode=active_pricing_mode,
        base_fee_annual=supp_base,
        fixed_rate_kwh=fixed_rate_val,
        monthly_variable_rates=default_cfg.supplier.monthly_variable_rates,
        market_price_profile_id="epex_nl_2025",
        supplier_margin_kwh=supp_margin,
    )
    metering_tariff = MeteringTariff(
        meter_company_name=meter_name,
        annual_flat_fee=meter_annual,
    )
    levy_config = LevyConfig(
        statutory_levy_rate_kwh=levy_rate,
        vat_rate_pct=vat_rate,
    )
    active_config = StatusQuoConfig2025(
        stage=active_stage,
        dso=dso_tariff,
        supplier=supplier_tariff,
        metering=metering_tariff,
        levies=levy_config,
        discount_rate_pct=discount_rate,
        energy_escalation_pct=escalation_rate,
        evaluation_horizon_years=15,
    )

    # ----------------------------------------------------------------------------------
    # 4. Calculation Execution
    # ----------------------------------------------------------------------------------
    result = calculate_status_quo_master_2025(load=load_series, config=active_config)
    audit_report = perform_full_status_quo_audit(load=load_series, result=result)

    # ----------------------------------------------------------------------------------
    # 5. Executive Financial KPI Cards
    # ----------------------------------------------------------------------------------
    st.markdown("### :material/dashboard: 3. Key Financial & Operational Metrics")

    col_kpi1, col_kpi2, col_kpi3, col_kpi4 = st.columns(4)
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
            else "Peak demand within contracted capacity"
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
    # 6. Audit & Verification Panel
    # ----------------------------------------------------------------------------------
    audit_icon = ":material/verified:" if audit_report.passed_all else ":material/error:"
    audit_status_title = (
        f"{audit_icon} Audit Protocol: {audit_report.passed_criteria_count}/{audit_report.total_criteria_count} Checks Passed"
    )

    with st.expander(audit_status_title, expanded=not audit_report.passed_all):
        st.markdown(audit_report.to_markdown(), unsafe_allow_html=True)
        if result.has_capacity_breach:
            st.warning(
                f":material/warning: Contract Capacity Exceeded: Recorded maximum peak in months "
                f"{result.breach_months} exceeded contracted transformer limit ({active_config.dso.contracted_capacity_kw:.1f} kW). "
                f"Under standard Liander terms, capacity fee was calculated on actual peak for these months.",
                icon=":material/warning:"
            )

    st.markdown("---")

    # ----------------------------------------------------------------------------------
    # 7. Unbundled Charts & Payment Series
    # ----------------------------------------------------------------------------------
    st.markdown("### :material/bar_chart: 4. Unbundled Cost Distribution & 12-Month Schedule")

    breakdown_adapter = convert_to_financial_cost_breakdown(result)

    col_chart1, col_chart2 = st.columns([1.2, 1.8])
    with col_chart1:
        st.markdown("##### Cost Share by Component")
        donut_fig = create_cost_donut_figure(breakdown_adapter)
        st.plotly_chart(donut_fig, use_container_width=True)

    with col_chart2:
        st.markdown("##### 12-Month Stacked Payment Series (Zahlungsreihe)")
        series_fig = create_monthly_payment_series_figure(breakdown_adapter)
        st.plotly_chart(series_fig, use_container_width=True)

    # ----------------------------------------------------------------------------------
    # 8. Monthly Statement Table & Export
    # ----------------------------------------------------------------------------------
    st.markdown("### :material/table_view: 5. 12-Month Accounting Statement Table")

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

    # Export Toolbar
    col_exp1, col_exp2 = st.columns(2)
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


if __name__ == "__main__":
    st.set_page_config(
        page_title="Status Quo 2025 Laboratory",
        page_icon=":material/account_balance:",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    if apply_custom_styles:
        apply_custom_styles()
    render_status_quo_lab()
