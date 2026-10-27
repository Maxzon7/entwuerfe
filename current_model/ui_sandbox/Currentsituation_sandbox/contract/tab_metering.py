"""
========================================================================================
Sub-Tab 3: Metering & Taxes (contract/tab_metering.py)
========================================================================================

Description:
------------
Renders the dedicated Certified Metering and Statutory Energy Levies view:
  1. Metering Company selection (Fudura, Joulz, Kenter, Custom) and service packages.
  2. Encapsulated form (st.form) for metering fees, statutory energy levies, tax credits, and VAT.
  3. Isolated Metering & Tax Performance & Cost Analysis:
     - 4 executive KPI cards (Metering Annual, Statutory Levies, Tax Reduction, Net Subtotal).
     - Itemized annual vs. monthly tax and telemetry statement table.
========================================================================================
"""

from typing import Tuple, Dict, Any, List
import streamlit as st
import pandas as pd

from current_model.ui.common.cards import render_kpi_card
from ui_sandbox.Currentsituation_sandbox.engine.config_and_models import (
    LoadSeries2025,
    MeteringTariff,
    LevyConfig,
)
from ui_sandbox.Currentsituation_sandbox.engine.tariff_defaults_2025 import (
    METERING_CATALOG_2025,
)


def render_metering_tab(
    load_series: LoadSeries2025,
    key_prefix: str = "currsit_contract"
) -> Tuple[MeteringTariff, LevyConfig, float, float]:
    """
    Renders the complete Certified Metering and Statutory Taxes tab with
    form configuration, isolated KPI cards, and annual vs. monthly breakdown.
    """
    st.markdown("##### Certified Metering & Statutory Energy Taxes")

    # 1. Metering Provider and Package Toolbar
    col_m_co, col_m_pkg = st.columns([1.5, 2.5])
    with col_m_co:
        meter_options = list(METERING_CATALOG_2025.keys()) + ["Custom Metering Provider"]
        selected_meter_name = st.selectbox(
            "Metering Provider:",
            options=meter_options,
            index=0,
            key=f"{key_prefix}_meter_name_select"
        )

    with col_m_pkg:
        if selected_meter_name in METERING_CATALOG_2025:
            pkg_dict = METERING_CATALOG_2025[selected_meter_name]
            pkg_options = list(pkg_dict.keys())
            selected_pkg = st.selectbox(
                "Service Package & Meter Tier:",
                options=pkg_options,
                index=0,
                key=f"{key_prefix}_meter_pkg_{selected_meter_name}"
            )
            pkg_data = pkg_dict[selected_pkg]
            st.caption(f":material/info: *{pkg_data.get('description', '')}*")
        else:
            selected_pkg = "Custom Metering Package"
            pkg_data = {"annual_flat_fee": 900.00, "description": "Custom metering and interval telemetry contract"}
            st.caption(":material/tune: *Custom metering and telemetry fees.*")

    # 2. Form for Numerical Parameters
    with st.form(key=f"{key_prefix}_metering_tax_form"):
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            meter_annual = st.number_input(
                "Annual Telemetry & Meter Flat Fee (€/year):",
                min_value=0.0,
                value=float(pkg_data.get("annual_flat_fee", 900.00)),
                step=50.0,
                key=f"{key_prefix}_meter_annual_{selected_meter_name}_{selected_pkg}",
                help="15-minute interval telemetry reading and certified meter rental per year excluding VAT"
            )
        with col_m2:
            st.info(
                f":material/speed: **Monthly Metering Equivalent:** € {meter_annual / 12.0:,.2f} / month | "
                f"**Package:** {selected_pkg}",
                icon=":material/speed:"
            )

        st.markdown("##### Statutory Energy Levies & VAT")
        col_tax1, col_tax2, col_tax3 = st.columns(3)
        with col_tax1:
            levy_rate = st.number_input(
                "Statutory Energy Levies (€/kWh):",
                min_value=0.0,
                value=0.0125,
                format="%.4f",
                key=f"{key_prefix}_levy_rate",
                help="Statutory energy taxes and levies per active kWh"
            )
        with col_tax2:
            tax_reduction = st.number_input(
                "Tax Reduction Credit (€/year):",
                min_value=0.0,
                value=0.0,
                step=50.0,
                key=f"{key_prefix}_tax_reduction",
                help="Statutory tax reduction credit per connection"
            )
        with col_tax3:
            vat_rate = st.number_input(
                "Value Added Tax (VAT %):",
                min_value=0.0,
                max_value=100.0,
                value=21.0,
                step=1.0,
                key=f"{key_prefix}_vat_rate",
                help="Statutory Value Added Tax percentage"
            )

        submitted_metering = st.form_submit_button(
            "Save Metering & Tax Configuration",
            icon=":material/save:",
            type="primary",
            use_container_width=True
        )

    if submitted_metering:
        st.success("Metering and tax configuration saved successfully.", icon=":material/check_circle:")

    # 3. Mathematics & Isolated Analysis
    total_kwh = float(load_series.total_energy_kwh)
    annual_levies_gross = total_kwh * levy_rate
    annual_levies_net = max(0.0, annual_levies_gross - tax_reduction)
    combined_net = meter_annual + annual_levies_net
    vat_amount = combined_net * (vat_rate / 100.0)
    combined_gross = combined_net + vat_amount

    st.markdown("---")
    st.markdown("##### :material/payments: Isolated Metering & Tax Performance Analysis")

    kpi_m1, kpi_m2, kpi_m3, kpi_m4 = st.columns(4)
    with kpi_m1:
        render_kpi_card(
            title=":material/speed: Annual Metering Fee",
            value=f"€ {meter_annual:,.2f}",
            subtext=f"Monthly: € {meter_annual / 12.0:,.2f} / month",
            status="default"
        )
    with kpi_m2:
        render_kpi_card(
            title=":material/receipt: Statutory Energy Levies",
            value=f"€ {annual_levies_gross:,.2f}",
            subtext=f"Rate: € {levy_rate:.4f} / kWh ({total_kwh:,.0f} kWh)",
            status="default"
        )
    with kpi_m3:
        render_kpi_card(
            title=":material/redeem: Tax Reduction Credit",
            value=f"-€ {tax_reduction:,.2f}",
            subtext="Annual statutory credit" if tax_reduction > 0 else "No commercial credit applied",
            status="default" if tax_reduction > 0 else "info"
        )
    with kpi_m4:
        render_kpi_card(
            title=":material/payments: Metering & Tax Net Total",
            value=f"€ {combined_net:,.2f}",
            subtext=f"Gross (+{vat_rate:.0f}% VAT): € {combined_gross:,.2f}",
            status="default"
        )

    # Itemized Breakdown Table
    st.markdown("###### :material/table_chart: Itemized Metering & Tax Cost Schedule")
    meter_tax_rows = [
        {
            "Cost Component": f"Certified Metering ({selected_pkg})",
            "Basis": "Annual Fixed Flat Fee",
            "Per Year (€)": f"€ {meter_annual:,.2f}",
            "Per Month (€)": f"€ {meter_annual / 12.0:,.2f}"
        },
        {
            "Cost Component": "Statutory Energy Levies",
            "Basis": f"{total_kwh:,.0f} kWh @ € {levy_rate:.4f}/kWh",
            "Per Year (€)": f"€ {annual_levies_gross:,.2f}",
            "Per Month (€)": f"€ {annual_levies_gross / 12.0:,.2f}"
        },
        {
            "Cost Component": "Statutory Tax Reduction Credit",
            "Basis": "Annual Connection Allowance",
            "Per Year (€)": f"-€ {tax_reduction:,.2f}",
            "Per Month (€)": f"-€ {tax_reduction / 12.0:,.2f}"
        },
        {
            "Cost Component": "SUBTOTAL (Net)",
            "Basis": "Metering + Levies - Credit",
            "Per Year (€)": f"€ {combined_net:,.2f}",
            "Per Month (€)": f"€ {combined_net / 12.0:,.2f}"
        },
        {
            "Cost Component": f"Value Added Tax ({vat_rate:.0f}% VAT)",
            "Basis": f"{vat_rate:.0f}% on Net Subtotal",
            "Per Year (€)": f"€ {vat_amount:,.2f}",
            "Per Month (€)": f"€ {vat_amount / 12.0:,.2f}"
        },
        {
            "Cost Component": "TOTAL (Gross)",
            "Basis": "Net Subtotal + VAT",
            "Per Year (€)": f"€ {combined_gross:,.2f}",
            "Per Month (€)": f"€ {combined_gross / 12.0:,.2f}"
        }
    ]
    st.dataframe(pd.DataFrame(meter_tax_rows), use_container_width=True, hide_index=True)

    # Models
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

    return metering_tariff, levy_config, meter_annual, annual_levies_net
