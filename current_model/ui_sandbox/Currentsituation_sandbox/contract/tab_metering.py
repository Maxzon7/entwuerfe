"""
========================================================================================
Sub-Tab 3: Pillars 3 & 4 - Metering & Statutory Taxes (contract/tab_metering.py)
========================================================================================

Implements the standardized 3-Zone layout for Certified Metering & Statutory Taxes:
  - Zone A (Left Column, 58%): 1. Contract & Tariff Inputs
    Includes Metering Company & Service Package selectors, Fixed Standing Fee ({CURR}/month),
    Statutory Energy Tax Rate ({CURR}/kWh), Annual Tax Reduction Credit ({CURR}/year),
    Value Added Tax Rate (VAT %), and 15-Year TCO Discount & Escalation Rates.
  - Zone B (Right Column, 42%): 2. Component Bill Calculation (How it Adds Up)
    Renders a standardized Electricity Bill Sub-Ledger showing:
    Line Item | Calculation (Quantity × Rate) | Monthly ({CURR}) | Annual ({CURR})
    concluding with = SUBTOTAL METERING & TAXES (NET).
  - Zone C (Bottom Full Width): 3. Monthly Breakdown & Visual Diagnostics
    Renders the 12-Month Metering & Statutory Taxes Statement table inside an expander.
========================================================================================
"""

from typing import Tuple, List, Dict, Optional
import streamlit as st
import pandas as pd

try:
    from ui_sandbox.Currentsituation_sandbox.engine.config_and_models import (
        MeteringTariff,
        LevyConfig,
        LoadSeries2025,
    )
    from ui_sandbox.Currentsituation_sandbox.engine.tariff_defaults_2025 import (
        METERING_CATALOG_2025,
    )
    from ui_sandbox.Currentsituation_sandbox.engine.consumption_pipeline import (
        extract_monthly_consumption_records,
    )
    from ui_sandbox.Currentsituation_sandbox.contract.tab_dso import _render_sub_ledger_html
except ImportError:
    from current_model.ui_sandbox.Currentsituation_sandbox.engine.config_and_models import (
        MeteringTariff,
        LevyConfig,
        LoadSeries2025,
    )
    from current_model.ui_sandbox.Currentsituation_sandbox.engine.tariff_defaults_2025 import (
        METERING_CATALOG_2025,
    )
    from current_model.ui_sandbox.Currentsituation_sandbox.engine.consumption_pipeline import (
        extract_monthly_consumption_records,
    )
    from current_model.ui_sandbox.Currentsituation_sandbox.contract.tab_dso import _render_sub_ledger_html


def render_metering_tab(
    load_series: LoadSeries2025,
    key_prefix: str = "currsit_contract",
    enable_p3_metering: bool = True,
    enable_p4_taxes: bool = True,
    currency_code: str = "EUR",
    dso_monthly_net: Optional[List[float]] = None,
    supplier_monthly_net: Optional[List[float]] = None,
) -> Tuple[MeteringTariff, LevyConfig, float, float]:
    """
    Renders Sub-Tab 3: Pillars 3 & 4 - Metering & Statutory Taxes using the standardized
    3-Zone layout and returns (MeteringTariff, LevyConfig, discount_rate_pct, escalation_rate_pct).
    Supports independent gray-out of Pillar 3 (Metering) and Pillar 4 (Statutory Taxes),
    and computes Provincial / Municipal Percentage Levies live against Pillars 1 & 2 net concepts.
    """
    both_disabled = (not enable_p3_metering and not enable_p4_taxes)
    status_tag = ""
    if both_disabled:
        status_tag = " `[BYPASSED / GRAYED OUT]`"
    elif not enable_p3_metering:
        status_tag = " `[P3 METERING BYPASSED]`"
    elif not enable_p4_taxes:
        status_tag = " `[P4 TAXES BYPASSED]`"

    st.markdown(f"#### :material/speed: Pillars 3 & 4: Metering & Telemetry + Statutory Taxes & Levies{status_tag}")

    if not enable_p3_metering and enable_p4_taxes:
        st.info(
            ":material/visibility_off: **Pillar 3 (Certified Metering) is Bypassed / Grayed Out** under the active Market Structure Mode "
            "(metering is bundled into the Single-Utility Grid Bill). Pillar 3 inputs are disabled and evaluate to **0.00**, "
            "while **Pillar 4 (Statutory Taxes & VAT)** remains active.",
            icon=":material/info:"
        )
    elif both_disabled:
        st.info(
            ":material/visibility_off: **Both Pillar 3 (Metering) and Pillar 4 (Statutory Taxes) are Bypassed / Grayed Out.** "
            "All inputs remain visible in read-only state and evaluate to **0.00**.",
            icon=":material/info:"
        )

    col_zone_a, col_zone_b = st.columns([0.58, 0.42], gap="large")

    # ----------------------------------------------------------------------------------
    # Zone A (Left Column, 58%): 1. Contract & Tariff Inputs
    # ----------------------------------------------------------------------------------
    with col_zone_a:
        st.markdown("##### :material/tune: 1. Contract & Tariff Inputs")

        col_m_co, col_m_pkg = st.columns([1.4, 2.2])
        with col_m_co:
            meter_options = list(METERING_CATALOG_2025.keys()) + ["Custom Metering Provider"]
            selected_meter_name = st.selectbox(
                "Certified Metering Provider:",
                options=meter_options,
                index=0,
                key=f"{key_prefix}_meter_name_select",
                disabled=not enable_p3_metering,
            )

        with col_m_pkg:
            if selected_meter_name in METERING_CATALOG_2025:
                pkg_dict = METERING_CATALOG_2025[selected_meter_name]
                pkg_options = list(pkg_dict.keys())
                selected_pkg = st.selectbox(
                    "Service Package & Telemetry Tier:",
                    options=pkg_options,
                    index=0,
                    key=f"{key_prefix}_meter_pkg_{selected_meter_name}",
                    disabled=not enable_p3_metering,
                )
                pkg_data = pkg_dict[selected_pkg]
                if enable_p3_metering:
                    st.caption(f":material/info: *{pkg_data.get('description', '')}*")
                else:
                    st.caption(":material/layers_clear: *Bundled in Utility (Single-Utility Mode — Pillar 3 bypassed at 0.00).*")
            else:
                selected_pkg = "Custom Telemetry Package"
                pkg_data = {"annual_flat_fee": 900.00, "description": "Custom interval metering & telemetry"}
                st.caption(":material/tune: *Custom interval metering and transformer rental schedule.*")

        with st.form(key=f"{key_prefix}_metering_taxes_form"):
            p3_badge = "" if enable_p3_metering else " [BYPASSED]"
            st.markdown(f"###### A. Pillar 3: Metering & Telemetry Fees{p3_badge}")
            default_meter_monthly = round(float(pkg_data.get("annual_flat_fee", 900.00)) / 12.0, 2)
            meter_monthly = st.number_input(
                f"Fixed Standing Fee — Metering & Telemetry ({currency_code}/month):",
                min_value=0.0,
                value=default_meter_monthly,
                step=5.0,
                format="%.2f",
                key=f"{key_prefix}_meter_monthly_{selected_meter_name}_{selected_pkg}",
                help=f"Monthly flat fee for certified 15-minute RLM interval telemetry and meter rental ({currency_code}/month)",
                disabled=not enable_p3_metering,
            )

            p4_badge = "" if enable_p4_taxes else " [BYPASSED]"
            st.markdown(f"###### B. Pillar 4: Statutory Taxes & Levies{p4_badge}")
            default_levy_rate = float(st.session_state.get(f"{key_prefix}_preset_levy_rate", 0.0125))
            default_pct_levy = float(st.session_state.get(f"{key_prefix}_preset_pct_levy_rate", 0.0))
            default_vat_rate = float(st.session_state.get(f"{key_prefix}_preset_vat_rate", 21.0))
            default_vat_on_levies = bool(st.session_state.get(f"{key_prefix}_preset_vat_on_levies", True))

            col_tax1, col_tax2 = st.columns(2)
            with col_tax1:
                levy_rate = st.number_input(
                    f"Volumetric Energy Tax ({currency_code}/kWh):",
                    min_value=0.0,
                    value=default_levy_rate,
                    format="%.4f",
                    step=0.0005,
                    key=f"{key_prefix}_levy_rate",
                    help=f"Volumetric statutory energy tax rate per kWh ({currency_code}/kWh)",
                    disabled=not enable_p4_taxes,
                )
                pct_levy_rate = st.number_input(
                    "Provincial / Municipal Percentage Levies (% of Net Electric Bill):",
                    min_value=0.0,
                    max_value=100.0,
                    value=default_pct_levy,
                    format="%.6f",
                    step=0.1,
                    key=f"{key_prefix}_pct_levy_rate",
                    help="Percentage statutory levies applied to net electric concepts (e.g., 12.516026% for EDEMSA Municipal, Sellos, CAP & IIBB taxes)",
                    disabled=not enable_p4_taxes,
                )
            with col_tax2:
                tax_reduction = st.number_input(
                    f"Tax Reduction Credit ({currency_code}/year):",
                    min_value=0.0,
                    value=0.0,
                    step=50.0,
                    format="%.2f",
                    key=f"{key_prefix}_tax_reduction",
                    help=f"Annual statutory energy tax reduction credit ({currency_code}/year)",
                    disabled=not enable_p4_taxes,
                )
                vat_rate = st.number_input(
                    "Value Added Tax (VAT %):",
                    min_value=0.0,
                    max_value=100.0,
                    value=default_vat_rate,
                    step=1.0,
                    format="%.1f",
                    key=f"{key_prefix}_vat_rate",
                    help="Statutory Value Added Tax percentage (21.0% in NL, 27.0% in AR)"
                )

            vat_on_levies = st.checkbox(
                "Apply VAT on top of Pillar 4 Statutory Levies (True for NL 21% BTW; False for Argentina 27% IVA on Electric Concepts only)",
                value=default_vat_on_levies,
                key=f"{key_prefix}_vat_on_levies",
                disabled=not enable_p4_taxes,
            )

            st.markdown("###### C. 15-Year Lifecycle TCO Parameters")
            col_tco1, col_tco2 = st.columns(2)
            with col_tco1:
                discount_rate = st.number_input(
                    "WACC / Discount Rate r (%):",
                    min_value=0.0,
                    max_value=25.0,
                    value=5.0,
                    step=0.5,
                    format="%.1f",
                    key=f"{key_prefix}_tco_r"
                )
            with col_tco2:
                escalation_rate = st.number_input(
                    "Annual Cost Escalation Rate g (%):",
                    min_value=0.0,
                    max_value=25.0,
                    value=3.0,
                    step=0.5,
                    format="%.1f",
                    key=f"{key_prefix}_tco_g"
                )

            submitted_meter = st.form_submit_button(
                "Apply Metering & Tax Settings",
                icon=":material/save:",
                type="primary",
                use_container_width=True
            )

        if submitted_meter:
            st.success("Metering & Statutory Tax configuration updated.", icon=":material/check_circle:")

    meter_annual = round(meter_monthly * 12.0, 2)
    eff_meter_company = selected_meter_name if enable_p3_metering else "Bundled in Utility"
    eff_meter_pkg = selected_pkg if enable_p3_metering else "Single-Utility Mode (Bundled)"
    eff_meter_desc = pkg_data.get("description", "") if enable_p3_metering else "Metering bundled into Single-Utility Grid Bill (Pillar 2)"

    metering_tariff = MeteringTariff(
        meter_company_name=eff_meter_company,
        service_package_name=eff_meter_pkg,
        annual_flat_fee=meter_annual,
        description=eff_meter_desc,
    )
    levy_config = LevyConfig(
        statutory_levy_rate_kwh=levy_rate,
        annual_tax_reduction=tax_reduction,
        vat_rate_pct=vat_rate,
        percentage_levy_rate_pct=pct_levy_rate,
        vat_applies_to_levies=vat_on_levies,
    )

    # ----------------------------------------------------------------------------------
    # Zone B (Right Column, 42%): 2. Component Bill Calculation (How it Adds Up)
    # ----------------------------------------------------------------------------------
    monthly_cons = extract_monthly_consumption_records(load_series)
    total_kwh = float(load_series.total_energy_kwh)

    eff_meter_mo = meter_monthly if enable_p3_metering else 0.0
    eff_meter_ann = meter_annual if enable_p3_metering else 0.0

    monthly_credit = tax_reduction / 12.0
    gross_tax_ann = round(total_kwh * levy_rate, 2) if enable_p4_taxes else 0.0
    vol_levies_monthly = [
        max(0.0, round((c.total_kwh * levy_rate) - monthly_credit, 2)) if enable_p4_taxes else 0.0
        for c in monthly_cons
    ]
    vol_levies_ann = round(sum(vol_levies_monthly), 2)
    effective_credit_ann = round(gross_tax_ann - vol_levies_ann, 2) if enable_p4_taxes else 0.0

    # Live calculation of Provincial / Municipal Percentage Levies against Net Electric Concepts
    pct_levies_monthly: List[float] = []
    electric_concepts_monthly: List[float] = []
    for idx in range(len(monthly_cons)):
        dso_m = float(dso_monthly_net[idx]) if (dso_monthly_net and idx < len(dso_monthly_net)) else 0.0
        supp_m = float(supplier_monthly_net[idx]) if (supplier_monthly_net and idx < len(supplier_monthly_net)) else 0.0
        elec_base_m = round(dso_m + supp_m + eff_meter_mo, 2)
        electric_concepts_monthly.append(elec_base_m)
        if enable_p4_taxes and pct_levy_rate > 0.0:
            pct_levies_monthly.append(round(elec_base_m * (pct_levy_rate / 100.0), 2))
        else:
            pct_levies_monthly.append(0.0)

    electric_concepts_ann = round(sum(electric_concepts_monthly), 2)
    pct_levies_ann = round(sum(pct_levies_monthly), 2)
    pct_levies_mo = round(pct_levies_ann / 12.0, 2)

    net_levies_monthly = [
        round(v_m + p_m, 2) for v_m, p_m in zip(vol_levies_monthly, pct_levies_monthly)
    ]
    net_levies_ann = round(sum(net_levies_monthly), 2)

    subtotal_mt_ann = round(eff_meter_ann + net_levies_ann, 2)
    subtotal_mt_mo = round(subtotal_mt_ann / 12.0, 2)

    with col_zone_b:
        st.markdown("##### :material/receipt_long: 2. Component Bill Calculation (How it Adds Up)")

        p3_calc_tag = "" if enable_p3_metering else " [BYPASSED]"
        p4_calc_tag = "" if enable_p4_taxes else " [BYPASSED]"
        meter_item_label = (
            f"3.1 Fixed Standing Fee — Metering ({selected_meter_name})"
            if enable_p3_metering
            else "3.1 Fixed Standing Fee — Metering (Bundled in Utility)"
        )
        meter_calc_str = (
            f"12 mos × {currency_code} {meter_monthly:,.2f}/mo"
            if enable_p3_metering
            else f"Bundled in Single-Utility Bill ({currency_code} 0.00/mo){p3_calc_tag}"
        )

        ledger_rows: List[Dict[str, str]] = [
            {
                "item": meter_item_label,
                "calc": meter_calc_str,
                "monthly": f"{eff_meter_mo:,.2f}",
                "annual": f"{eff_meter_ann:,.2f}",
            },
            {
                "item": "4.1 Statutory Energy Tax (Volumetric)",
                "calc": f"{total_kwh:,.0f} kWh × {currency_code} {levy_rate:.4f}/kWh{p4_calc_tag}",
                "monthly": f"{gross_tax_ann / 12.0:,.2f}",
                "annual": f"{gross_tax_ann:,.2f}",
            },
        ]

        if pct_levy_rate > 0.0:
            ledger_rows.append({
                "item": "4.1b Provincial / Municipal Percentage Levies",
                "calc": f"{pct_levy_rate:.6f}% × {currency_code} {electric_concepts_ann:,.2f}{p4_calc_tag}",
                "monthly": f"{pct_levies_mo:,.2f}",
                "annual": f"{pct_levies_ann:,.2f}",
            })

        if effective_credit_ann > 0.0:
            ledger_rows.append({
                "item": "4.2 Statutory Tax Reduction Credit",
                "calc": f"12 mos × -{currency_code} {effective_credit_ann / 12.0:,.2f}/mo",
                "monthly": f"-{effective_credit_ann / 12.0:,.2f}",
                "annual": f"-{effective_credit_ann:,.2f}",
            })

        st.markdown(
            _render_sub_ledger_html(
                header_title="Pillars 3 & 4 Sub-Ledger — Metering & Statutory Levies",
                rows=ledger_rows,
                subtotal_label="= SUBTOTAL METERING & TAXES (NET)",
                subtotal_monthly_eur=subtotal_mt_mo,
                subtotal_annual_eur=subtotal_mt_ann,
                accent_color="#10b981",
                currency_code=currency_code,
                is_enabled=not both_disabled,
            ),
            unsafe_allow_html=True
        )

        st.info(
            f":material/account_balance: **Pillar 3 (Metering Net):** {currency_code} {eff_meter_ann:,.2f}/yr ({currency_code} {eff_meter_mo:,.2f}/mo) | "
            f"**Pillar 4 (Statutory Taxes Net):** {currency_code} {net_levies_ann:,.2f}/yr ({currency_code} {net_levies_ann / 12.0:,.2f}/mo) | "
            f"**Applicable VAT:** {vat_rate:.1f}%.",
            icon=":material/info:"
        )

    # ----------------------------------------------------------------------------------
    # Zone C (Bottom Full Width): 3. Monthly Breakdown & Visual Diagnostics
    # ----------------------------------------------------------------------------------
    st.markdown("---")
    with st.expander(":material/table_view: 3. Monthly Breakdown & Schedule (Metering & Statutory Taxes)", expanded=False):
        month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        mt_rows = []
        for c_rec, l_net in zip(monthly_cons, net_levies_monthly):
            mt_rows.append({
                "Month": month_names[c_rec.month_index - 1],
                "Consumption (kWh)": f"{c_rec.total_kwh:,.0f}",
                f"Pillar 3: Metering Net ({currency_code})": f"{eff_meter_mo:,.2f}",
                f"Pillar 4: Statutory Taxes Net ({currency_code})": f"{l_net:,.2f}",
                f"Combined Net ({currency_code})": f"{eff_meter_mo + l_net:,.2f}",
            })
        st.dataframe(pd.DataFrame(mt_rows), use_container_width=True, hide_index=True)

    return metering_tariff, levy_config, discount_rate, escalation_rate
