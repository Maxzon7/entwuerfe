"""
========================================================================================
Classic Invoice View (Experimental) - Sub-Tab 5 (contract/tab_invoice_experimental.py)
========================================================================================

Description:
------------
Renders an authentic, multi-section commercial utility invoice layout:
  1. Section 1: Control Bar (Billing period selector: Full Year 2025 vs. Single Month).
  2. Section 2: Invoice Cover Page (Letterhead, Plant/Customer Data, Technical Metrics,
     Summary Block with Net Subtotal, 21% VAT, and Total Gross Amount Due).
  3. Section 3: Itemized Invoice Positions (6-column structured ledger for Blocks A-D:
     Supplier, DSO, Metering, Statutory Taxes) mathematically reconciled to the cent.
  4. Section 4: Graphical Invoice Attachment (Cost Donut, 12-Month Stacked Cash Outflow
     with active month highlight, and DSO Peak vs. Capacity audit chart).
  5. Section 5: Accounting Summary Matrix & Multi-Format Export Toolbar.
========================================================================================
"""

import io
import json
from typing import Dict, Any, List, Optional
import streamlit as st
import pandas as pd

from current_model.ui.common.cards import render_kpi_card
from ui_sandbox.Currentsituation_sandbox.engine.config_and_models import (
    LoadSeries2025,
    StatusQuoConfig2025,
    StatusQuoAnnualResult,
    PricingMode,
)
from ui_sandbox.Currentsituation_sandbox.engine.status_quo_master import (
    convert_to_financial_cost_breakdown,
)
from ui_sandbox.Currentsituation_sandbox.contract.charts import (
    create_cost_donut_figure,
    create_monthly_payment_series_figure,
    create_dso_monthly_peak_figure,
)


def build_invoice_positions(
    result: StatusQuoAnnualResult,
    active_config: StatusQuoConfig2025,
    target_period: str
) -> Dict[str, Any]:
    """
    Derives mathematically reconciled, 6-column invoice line items for the selected period
    (Full Year 2025 or any of the 12 individual months). Guarantees cent-exact consistency
    with StatusQuoAnnualResult and StatusQuoMonthlyResult.
    """
    is_single_month = (target_period != "Annual Statement 2025 (Full Year)" and not target_period.startswith("Annual"))

    if is_single_month:
        # Match by month name or index
        target_rec = next(
            (r for r in result.monthly_records if r.month_name in target_period or target_period.startswith(r.month_name)),
            result.monthly_records[0]
        )
        cons = target_rec.consumption
        dso_res = target_rec.dso
        comm_res = target_rec.commercial
        period_days = cons.days_count
        period_label = f"{target_rec.month_name} 2025"
        inv_number = f"INV-2025-{target_rec.month_index:02d}"
        months_count = 1
        month_idx = target_rec.month_index

        kwh_total = cons.total_kwh
        kwh_ht = cons.peak_tou_kwh
        kwh_nt = cons.offpeak_tou_kwh
        p_max = cons.peak_demand_kw

        target_supp_net = round(comm_res.supplier_energy_cost + comm_res.supplier_base_fee, 2)
        target_dso_net = round(dso_res.subtotal_dso_net, 2)
        target_meter_net = round(comm_res.metering_fee, 2)
        target_levies_net = round(comm_res.statutory_levies, 2)
        target_total_net = round(target_rec.total_net, 2)
        target_vat = round(target_rec.vat_amount, 2)
        target_total_gross = round(target_rec.total_gross, 2)
        target_rate_net = target_rec.effective_rate_net_kwh
    else:
        period_days = 365
        period_label = "Full Year 2025 (Jan 01 – Dec 31, 2025)"
        inv_number = "INV-2025-ANNUAL"
        months_count = 12
        month_idx = None

        kwh_total = result.total_consumption_kwh
        kwh_ht = result.total_peak_tou_kwh
        kwh_nt = result.total_offpeak_tou_kwh
        p_max = result.annual_peak_demand_kw

        target_supp_net = round(result.total_supplier_net, 2)
        target_dso_net = round(result.total_dso_net, 2)
        target_meter_net = round(result.total_metering_net, 2)
        target_levies_net = round(result.total_levies_net, 2)
        target_total_net = round(result.total_status_quo_net, 2)
        target_vat = round(result.total_vat_amount, 2)
        target_total_gross = round(result.total_status_quo_gross, 2)
        target_rate_net = result.blended_price_net_kwh

    contracted_kw = active_config.dso.contracted_capacity_kw
    is_breached = (p_max > contracted_kw)
    excess_kw = max(0.0, p_max - contracted_kw)

    # ----------------------------------------------------------------------------------
    # Block A: Energy Supply (Supplier / Commodity)
    # ----------------------------------------------------------------------------------
    block_a_positions: List[Dict[str, Any]] = []

    # Pos 1.1: Base Fee / Administration
    base_fee_net = round(
        comm_res.supplier_base_fee if is_single_month else sum(r.commercial.supplier_base_fee for r in result.monthly_records),
        2
    )
    block_a_positions.append({
        "pos": "1.1",
        "description": "Standing Base Fee & Customer Service Administration",
        "quantity": float(months_count),
        "unit": "month(s)",
        "rate": active_config.supplier.base_fee_annual / 12.0,
        "amount_net": base_fee_net
    })

    # Pos 1.4: Procurement & Green Certificates (GvO) Surcharges
    surcharge_rate = active_config.supplier.procurement_fee_kwh + active_config.supplier.green_certificate_surcharge_kwh
    surcharges_net = round(kwh_total * surcharge_rate, 2)
    if surcharge_rate > 0.0 or surcharges_net > 0.0:
        desc_surcharges = []
        if active_config.supplier.procurement_fee_kwh > 0.0:
            desc_surcharges.append(f"Procurement (€ {active_config.supplier.procurement_fee_kwh:.4f}/kWh)")
        if active_config.supplier.green_certificate_surcharge_kwh > 0.0:
            desc_surcharges.append(f"Green GvO (€ {active_config.supplier.green_certificate_surcharge_kwh:.4f}/kWh)")
        surcharge_desc = "Statutory Surcharges: " + " + ".join(desc_surcharges) if desc_surcharges else "Supplier Procurement Surcharges"

        block_a_positions.append({
            "pos": "1.4",
            "description": surcharge_desc,
            "quantity": kwh_total,
            "unit": "kWh",
            "rate": surcharge_rate,
            "amount_net": surcharges_net
        })

    # Pos 1.2 & 1.3: Commodity Active Energy
    tot_energy_stored = round(
        comm_res.supplier_energy_cost if is_single_month else sum(r.commercial.supplier_energy_cost for r in result.monthly_records),
        2
    )
    commodity_net = round(tot_energy_stored - surcharges_net, 2)

    if active_config.supplier.is_dual_rate:
        ht_rate = active_config.supplier.fixed_rate_peak_kwh
        nt_rate = active_config.supplier.fixed_rate_offpeak_kwh
        ht_amount = round(kwh_ht * ht_rate, 2)
        nt_amount = round(commodity_net - ht_amount, 2)
        block_a_positions.append({
            "pos": "1.2",
            "description": "Active Energy High Tariff (HT / Daytime Mo-Fr 07:00-23:00)",
            "quantity": kwh_ht,
            "unit": "kWh",
            "rate": ht_rate,
            "amount_net": ht_amount
        })
        block_a_positions.append({
            "pos": "1.3",
            "description": "Active Energy Low Tariff (NT / Night & Weekend)",
            "quantity": kwh_nt,
            "unit": "kWh",
            "rate": nt_rate,
            "amount_net": nt_amount
        })
    elif active_config.supplier.pricing_mode == PricingMode.DYNAMIC:
        eff_spot_rate = commodity_net / max(1.0, kwh_total)
        block_a_positions.append({
            "pos": "1.2",
            "description": f"Day-Ahead EPEX Spot Wholesale Commodity + Retail Margin (€ {active_config.supplier.supplier_margin_kwh:.4f}/kWh)",
            "quantity": kwh_total,
            "unit": "kWh",
            "rate": eff_spot_rate,
            "amount_net": commodity_net
        })
    else:
        flat_rate = active_config.supplier.fixed_rate_kwh
        block_a_positions.append({
            "pos": "1.2",
            "description": "Active Energy Commodity (Fixed Single Flat Rate)",
            "quantity": kwh_total,
            "unit": "kWh",
            "rate": flat_rate,
            "amount_net": commodity_net
        })

    # Cent reconciliation check for Block A
    sum_a = round(sum(p["amount_net"] for p in block_a_positions), 2)
    diff_a = round(target_supp_net - sum_a, 2)
    if abs(diff_a) > 0.0:
        block_a_positions.append({
            "pos": "1.9",
            "description": "Commercial Rounding Adjustment",
            "quantity": 1.0,
            "unit": "item",
            "rate": diff_a,
            "amount_net": diff_a
        })

    # ----------------------------------------------------------------------------------
    # Block B: Grid Operator & Capacity Fees (Regulated DSO)
    # ----------------------------------------------------------------------------------
    block_b_positions: List[Dict[str, Any]] = []

    # Pos 2.1: Standing Charge (Vastrecht & Connection)
    vastrecht_net = round(
        dso_res.fixed_transport_fee if is_single_month else sum(r.dso.fixed_transport_fee for r in result.monthly_records),
        2
    )
    conn_net = round(
        dso_res.fixed_connection_fee if is_single_month else sum(r.dso.fixed_connection_fee for r in result.monthly_records),
        2
    )
    standing_dso_net = round(vastrecht_net + conn_net, 2)
    block_b_positions.append({
        "pos": "2.1",
        "description": f"Fixed Grid Standing Charge & Connection Fee ({active_config.dso.dso_name})",
        "quantity": float(months_count),
        "unit": "month(s)",
        "rate": standing_dso_net / float(months_count),
        "amount_net": standing_dso_net
    })

    # Pos 2.2: Contracted Transmission Capacity
    cap_fee_net = round(
        dso_res.contracted_capacity_fee if is_single_month else sum(r.dso.contracted_capacity_fee for r in result.monthly_records),
        2
    )
    billed_kw_val = dso_res.billed_capacity_kw if is_single_month else contracted_kw
    desc_cap = f"Contracted Transmission Capacity (Capaciteitstarief @ {active_config.dso.grid_tier})"
    if is_single_month and dso_res.is_capacity_breached:
        desc_cap += f" [Breach Adjusted to {billed_kw_val:.1f} kW]"

    block_b_positions.append({
        "pos": "2.2",
        "description": desc_cap,
        "quantity": billed_kw_val if is_single_month else float(months_count),
        "unit": "kW" if is_single_month else "month(s)",
        "rate": active_config.dso.rate_contracted_capacity if is_single_month else cap_fee_net / float(months_count),
        "amount_net": cap_fee_net
    })

    # Pos 2.3: Measured Peak Demand Charge
    peak_fee_net = round(
        dso_res.peak_demand_fee if is_single_month else sum(r.dso.peak_demand_fee for r in result.monthly_records),
        2
    )
    block_b_positions.append({
        "pos": "2.3",
        "description": "Monthly Peak Demand Charge (Piekvermogenstarief for Measured Max kW)",
        "quantity": p_max if is_single_month else float(months_count),
        "unit": "kW" if is_single_month else "month(s)",
        "rate": active_config.dso.rate_peak_demand if is_single_month else peak_fee_net / float(months_count),
        "amount_net": peak_fee_net
    })

    # Pos 2.4: Volumetric Transport HT & NT
    vol_peak_net = round(
        getattr(dso_res, "volumetric_peak_fee", kwh_ht * active_config.dso.rate_transport_peak_kwh)
        if is_single_month else sum(getattr(r.dso, "volumetric_peak_fee", 0.0) for r in result.monthly_records),
        2
    )
    vol_offpeak_net = round(
        getattr(dso_res, "volumetric_offpeak_fee", kwh_nt * active_config.dso.rate_transport_offpeak_kwh)
        if is_single_month else sum(getattr(r.dso, "volumetric_offpeak_fee", 0.0) for r in result.monthly_records),
        2
    )
    if active_config.dso.rate_transport_peak_kwh > 0.0 or vol_peak_net > 0.0:
        block_b_positions.append({
            "pos": "2.4a",
            "description": "Volumetric Network Transport High Tariff (Normaaltarief HT)",
            "quantity": kwh_ht,
            "unit": "kWh",
            "rate": active_config.dso.rate_transport_peak_kwh,
            "amount_net": vol_peak_net
        })
    if active_config.dso.rate_transport_offpeak_kwh > 0.0 or vol_offpeak_net > 0.0:
        block_b_positions.append({
            "pos": "2.4b",
            "description": "Volumetric Network Transport Low Tariff (Daltarief NT)",
            "quantity": kwh_nt,
            "unit": "kWh",
            "rate": active_config.dso.rate_transport_offpeak_kwh,
            "amount_net": vol_offpeak_net
        })

    # Cent reconciliation check for Block B
    sum_b = round(sum(p["amount_net"] for p in block_b_positions), 2)
    diff_b = round(target_dso_net - sum_b, 2)
    if abs(diff_b) > 0.0:
        block_b_positions.append({
            "pos": "2.9",
            "description": "Grid Regulation Rounding Adjustment",
            "quantity": 1.0,
            "unit": "item",
            "rate": diff_b,
            "amount_net": diff_b
        })

    # ----------------------------------------------------------------------------------
    # Block C: Certified Metering & Telemetry (Meetbedrijf)
    # ----------------------------------------------------------------------------------
    block_c_positions: List[Dict[str, Any]] = []
    block_c_positions.append({
        "pos": "3.1",
        "description": f"Interval Telemetry & Meter Rental ({active_config.metering.service_package_name} - {active_config.metering.meter_company_name})",
        "quantity": float(months_count),
        "unit": "month(s)",
        "rate": active_config.metering.annual_flat_fee / 12.0,
        "amount_net": target_meter_net
    })

    # ----------------------------------------------------------------------------------
    # Block D: Statutory Energy Levies & Taxes (Belastingen)
    # ----------------------------------------------------------------------------------
    block_d_positions: List[Dict[str, Any]] = []
    levy_rate = active_config.levies.statutory_levy_rate_kwh
    gross_tax = round(kwh_total * levy_rate, 2)
    tax_credit = round(gross_tax - target_levies_net, 2)

    block_d_positions.append({
        "pos": "4.1",
        "description": "Statutory Energy Tax (Energiebelasting & Statutory Surcharges)",
        "quantity": kwh_total,
        "unit": "kWh",
        "rate": levy_rate,
        "amount_net": gross_tax
    })

    if tax_credit > 0.0:
        block_d_positions.append({
            "pos": "4.2",
            "description": "Statutory Energy Tax Reduction Credit (Vermindering Energiebelasting)",
            "quantity": float(months_count),
            "unit": "month(s)",
            "rate": -round(tax_credit / float(months_count), 2),
            "amount_net": -tax_credit
        })

    # Cent reconciliation check for Block D
    sum_d = round(sum(p["amount_net"] for p in block_d_positions), 2)
    diff_d = round(target_levies_net - sum_d, 2)
    if abs(diff_d) > 0.0:
        block_d_positions.append({
            "pos": "4.9",
            "description": "Statutory Tax Rounding Adjustment",
            "quantity": 1.0,
            "unit": "item",
            "rate": diff_d,
            "amount_net": diff_d
        })

    # Final invoice-wide cent reconciliation check against target_total_net
    all_blocks_sum = round(
        sum(p["amount_net"] for p in block_a_positions)
        + sum(p["amount_net"] for p in block_b_positions)
        + sum(p["amount_net"] for p in block_c_positions)
        + sum(p["amount_net"] for p in block_d_positions),
        2
    )
    final_diff = round(target_total_net - all_blocks_sum, 2)
    if abs(final_diff) > 0.0:
        if block_d_positions and block_d_positions[-1]["pos"].endswith(".9"):
            block_d_positions[-1]["amount_net"] = round(block_d_positions[-1]["amount_net"] + final_diff, 2)
            block_d_positions[-1]["rate"] = block_d_positions[-1]["amount_net"]
        else:
            block_d_positions.append({
                "pos": "4.9",
                "description": "Invoice Cent Balancing Adjustment",
                "quantity": 1.0,
                "unit": "item",
                "rate": final_diff,
                "amount_net": final_diff
            })

    subtotal_a_val = round(sum(p["amount_net"] for p in block_a_positions), 2)
    subtotal_b_val = round(sum(p["amount_net"] for p in block_b_positions), 2)
    subtotal_c_val = round(sum(p["amount_net"] for p in block_c_positions), 2)
    subtotal_d_val = round(sum(p["amount_net"] for p in block_d_positions), 2)

    return {
        "period_label": period_label,
        "inv_number": inv_number,
        "period_days": period_days,
        "is_single_month": is_single_month,
        "month_index": month_idx,
        # Physical
        "kwh_total": kwh_total,
        "kwh_ht": kwh_ht,
        "kwh_nt": kwh_nt,
        "ht_pct": (kwh_ht / max(1.0, kwh_total)) * 100.0,
        "nt_pct": (kwh_nt / max(1.0, kwh_total)) * 100.0,
        "p_max": p_max,
        "contracted_kw": contracted_kw,
        "is_breached": is_breached,
        "excess_kw": excess_kw,
        "utilization_hours": kwh_total / max(1.0, p_max),
        # Positions
        "block_a": block_a_positions,
        "block_b": block_b_positions,
        "block_c": block_c_positions,
        "block_d": block_d_positions,
        # Reconciled Totals
        "subtotal_a": subtotal_a_val,
        "subtotal_b": subtotal_b_val,
        "subtotal_c": subtotal_c_val,
        "subtotal_d": subtotal_d_val,
        "total_net": target_total_net,
        "vat_amount": target_vat,
        "total_gross": target_total_gross,
        "effective_rate_net": target_rate_net,
        "effective_rate_gross": target_total_gross / max(1.0, kwh_total),
    }


def _render_positions_table_html(
    positions: List[Dict[str, Any]],
    subtotal_title: str,
    subtotal_val: float
) -> str:
    """Renders a clean, high-contrast HTML ledger table styled for dark/light themes."""
    rows_html = ""
    for idx, p in enumerate(positions):
        bg = "#1e293b" if idx % 2 == 0 else "#0f172a"
        q_fmt = f"{p['quantity']:,.1f}" if p['unit'] == "kW" else (f"{p['quantity']:,.0f}" if p['unit'] == "kWh" else f"{p['quantity']:.0f}")
        r_fmt = f"€ {p['rate']:.4f}" if p['unit'] == "kWh" else f"€ {p['rate']:,.2f}"
        a_fmt = f"€ {p['amount_net']:,.2f}" if p['amount_net'] >= 0 else f"-€ {abs(p['amount_net']):,.2f}"
        color = "#f87171" if p['amount_net'] < 0 else "#e2e8f0"

        rows_html += f"""
        <tr style="background-color: {bg}; border-bottom: 1px solid #334155;">
            <td style="padding: 7px 10px; font-weight: 600; color: #94a3b8; font-size: 0.85rem;">{p['pos']}</td>
            <td style="padding: 7px 10px; color: #f1f5f9; font-size: 0.88rem;">{p['description']}</td>
            <td style="padding: 7px 10px; text-align: right; color: #cbd5e1; font-size: 0.88rem;">{q_fmt}</td>
            <td style="padding: 7px 10px; text-align: center; color: #94a3b8; font-size: 0.82rem;">{p['unit']}</td>
            <td style="padding: 7px 10px; text-align: right; color: #cbd5e1; font-size: 0.88rem;">{r_fmt}</td>
            <td style="padding: 7px 10px; text-align: right; font-weight: 600; color: {color}; font-size: 0.90rem;">{a_fmt}</td>
        </tr>
        """

    sub_fmt = f"€ {subtotal_val:,.2f}"
    return f"""
    <div style="overflow-x: auto; margin-bottom: 16px; border-radius: 6px; border: 1px solid #334155;">
        <table style="width: 100%; border-collapse: collapse; font-family: -apple-system, BlinkMacSystemFont, sans-serif;">
            <thead>
                <tr style="background-color: #090d16; border-bottom: 2px solid #475569; color: #94a3b8; font-size: 0.80rem; text-transform: uppercase; letter-spacing: 0.05em;">
                    <th style="padding: 8px 10px; text-align: left; width: 6%;">Pos.</th>
                    <th style="padding: 8px 10px; text-align: left; width: 44%;">Description / Component</th>
                    <th style="padding: 8px 10px; text-align: right; width: 14%;">Quantity</th>
                    <th style="padding: 8px 10px; text-align: center; width: 10%;">Unit</th>
                    <th style="padding: 8px 10px; text-align: right; width: 13%;">Rate</th>
                    <th style="padding: 8px 10px; text-align: right; width: 13%;">Net Amount</th>
                </tr>
            </thead>
            <tbody>
                {rows_html}
                <tr style="background-color: #0b1329; border-top: 2px solid #38bdf8; font-weight: 700;">
                    <td colspan="5" style="padding: 9px 10px; text-align: right; color: #38bdf8; font-size: 0.88rem; text-transform: uppercase;">{subtotal_title}:</td>
                    <td style="padding: 9px 10px; text-align: right; color: #38bdf8; font-size: 0.95rem;">{sub_fmt}</td>
                </tr>
            </tbody>
        </table>
    </div>
    """


def render_invoice_experimental_tab(
    result: StatusQuoAnnualResult,
    active_config: StatusQuoConfig2025,
    load_series: LoadSeries2025,
    key_prefix: str = "currsit_contract"
) -> None:
    """
    Renders Sub-Tab 5: Classic Commercial Utility Invoice (Experimental).
    """
    # ----------------------------------------------------------------------------------
    # Section 1: Control Bar (Billing Period Inspector)
    # ----------------------------------------------------------------------------------
    st.markdown("### :material/receipt: Classic Utility Invoice View (Experimental)")
    st.caption("Replicates an authoritative, multi-page commercial utility bill mathematically reconciled to the cent.")

    period_options = ["Annual Statement 2025 (Full Year)"] + [f"{r.month_name} 2025" for r in result.monthly_records]
    col_ctrl_left, col_ctrl_right = st.columns([2, 3])
    with col_ctrl_left:
        selected_period = st.selectbox(
            "Billing Period to Audit:",
            options=period_options,
            index=0,
            key=f"{key_prefix}_inv_period_sel"
        )

    inv_data = build_invoice_positions(result, active_config, selected_period)

    with col_ctrl_right:
        if inv_data["is_single_month"]:
            st.info(
                f":material/calendar_today: Simulating **Monthly Utility Settlement**: {inv_data['period_label']} "
                f"({inv_data['period_days']} calendar days, {inv_data['period_days'] * 96:,} interval steps @ 15 min).",
                icon=":material/info:"
            )
        else:
            st.success(
                ":material/verified: Simulating **Consolidated Annual Settlement 2025**: Full reference year "
                "(365 days, 35,040 steps @ 15 min, 100% reconciled).",
                icon=":material/check_circle:"
            )

    st.markdown("---")

    # ----------------------------------------------------------------------------------
    # Section 2: Invoice Cover Page (Container with Paper Optic)
    # ----------------------------------------------------------------------------------
    site_name = st.session_state.get("active_csv_filename", "Industrial Peak Facility (Benchmark)")

    with st.container(border=True):
        # Line 2.1: Briefkopf & Master Metadata
        col_hdr_left, col_hdr_right = st.columns(2)
        with col_hdr_left:
            st.markdown("##### :material/factory: Facility & Customer Master Data")
            st.markdown(
                f"**Facility / Site:** `{site_name}`<br>"
                f"**Grid Metering Code (EAN):** `871685900012345678` *(Sample EAN - Placeholder)*<br>"
                f"**Voltage Tier:** `{active_config.dso.grid_tier}`<br>"
                f"**Grid Operator Area:** `{active_config.dso.dso_name}`",
                unsafe_allow_html=True
            )
        with col_hdr_right:
            st.markdown("##### :material/receipt_long: Invoice & Contract Metadata")
            st.markdown(
                f"**Document Number:** `{inv_data['inv_number']}`<br>"
                f"**Accounting Period:** `{inv_data['period_label']}` ({inv_data['period_days']} days)<br>"
                f"**Energy Supplier:** `{active_config.supplier.supplier_name}`<br>"
                f"**Pricing Contract:** `{active_config.supplier.pricing_mode.value}` ({active_config.supplier.tariff_product_name})",
                unsafe_allow_html=True
            )

        st.markdown("<hr style='margin: 12px 0; border-color: #334155;'>", unsafe_allow_html=True)

        # Line 2.2: Technical Consumption & Demand Proof (4 metrics)
        st.markdown("###### :material/electric_bolt: Physical Billing Foundations & Load Factor")
        kpi_t1, kpi_t2, kpi_t3, kpi_t4 = st.columns(4)
        with kpi_t1:
            render_kpi_card(
                title=":material/bolt: Active Energy",
                value=f"{inv_data['kwh_total']:,.0f} kWh",
                subtext=f"HT: {inv_data['ht_pct']:.1f}% | NT: {inv_data['nt_pct']:.1f}%",
                status="default"
            )
        with kpi_t2:
            render_kpi_card(
                title=":material/speed: Measured Peak (P_max)",
                value=f"{inv_data['p_max']:,.1f} kW",
                subtext="Highest 15-min demand",
                status="default"
            )
        with kpi_t3:
            breach_status = "alert" if inv_data["is_breached"] else "ok"
            breach_desc = f"+{inv_data['excess_kw']:.1f} kW Overload" if inv_data["is_breached"] else "100% Within Limit"
            render_kpi_card(
                title=":material/verified_user: Contract Capacity",
                value=f"{inv_data['contracted_kw']:,.0f} kW",
                subtext=breach_desc,
                status=breach_status
            )
        with kpi_t4:
            render_kpi_card(
                title=":material/timelapse: Utilization Hours",
                value=f"{inv_data['utilization_hours']:,.0f} h",
                subtext=f"Load factor: {(inv_data['utilization_hours'] / (inv_data['period_days'] * 24)) * 100:.1f}%",
                status="default"
            )

        st.markdown("<hr style='margin: 12px 0; border-color: #334155;'>", unsafe_allow_html=True)

        # Line 2.3: Commercial Summary & Reconciled Total Box
        col_sum_left, col_sum_right = st.columns([1.2, 1.0])
        with col_sum_left:
            st.markdown("###### :material/pie_chart: Cost Pillar Breakdown (Net Amounts)")
            share_supp = (inv_data["subtotal_a"] / max(1.0, inv_data["total_net"])) * 100.0
            share_dso = (inv_data["subtotal_b"] / max(1.0, inv_data["total_net"])) * 100.0
            share_meter = (inv_data["subtotal_c"] / max(1.0, inv_data["total_net"])) * 100.0
            share_levies = (inv_data["subtotal_d"] / max(1.0, inv_data["total_net"])) * 100.0

            st.markdown(
                f"""
                <div style="font-size: 0.90rem; line-height: 1.8; color: #cbd5e1;">
                    • <b>1. Energy Commodity (Retailer):</b> € {inv_data['subtotal_a']:,.2f} <span style="color: #38bdf8;">({share_supp:.1f}%)</span><br>
                    • <b>2. Network Transmission (DSO):</b> € {inv_data['subtotal_b']:,.2f} <span style="color: #f59e0b;">({share_dso:.1f}%)</span><br>
                    • <b>3. Certified Metering (Meetbedrijf):</b> € {inv_data['subtotal_c']:,.2f} <span style="color: #8b5cf6;">({share_meter:.1f}%)</span><br>
                    • <b>4. Statutory Energy Taxes (Belastingen):</b> € {inv_data['subtotal_d']:,.2f} <span style="color: #10b981;">({share_levies:.1f}%)</span>
                </div>
                """,
                unsafe_allow_html=True
            )

        with col_sum_right:
            st.markdown(
                f"""
                <div style="background-color: #0b1329; border: 2px solid #38bdf8; border-radius: 8px; padding: 14px 18px; text-align: right;">
                    <div style="color: #94a3b8; font-size: 0.82rem; text-transform: uppercase;">Net Subtotal (Excl. VAT)</div>
                    <div style="color: #e2e8f0; font-size: 1.15rem; font-weight: 600; margin-bottom: 4px;">€ {inv_data['total_net']:,.2f}</div>
                    <div style="color: #94a3b8; font-size: 0.82rem; text-transform: uppercase;">+ Value Added Tax (21% BTW)</div>
                    <div style="color: #cbd5e1; font-size: 1.00rem; font-weight: 500; margin-bottom: 8px;">€ {inv_data['vat_amount']:,.2f}</div>
                    <hr style="border-color: #334155; margin: 8px 0;">
                    <div style="color: #38bdf8; font-size: 0.85rem; font-weight: 700; text-transform: uppercase;">Total Invoice Amount Due (Gross)</div>
                    <div style="color: #ffffff; font-size: 1.65rem; font-weight: 800; letter-spacing: -0.02em;">€ {inv_data['total_gross']:,.2f}</div>
                    <div style="color: #94a3b8; font-size: 0.80rem; margin-top: 6px;">
                        Blended Rate: <b>€ {inv_data['effective_rate_net']:.4f}</b> net / <b>€ {inv_data['effective_rate_gross']:.4f}</b> gross per kWh
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )

    # ----------------------------------------------------------------------------------
    # Section 3: Itemized Invoice Positions (Ledger Tables for Blocks A-D)
    # ----------------------------------------------------------------------------------
    st.markdown("### :material/format_list_numbered: Itemized Accounting Schedule")
    st.caption("Standard 6-column invoice format: Pos. | Description | Quantity | Unit | Rate | Net Amount.")

    # Block A
    st.markdown("##### :material/storefront: Block A: Energy Retailer Supply (Commodity)")
    st.markdown(
        _render_positions_table_html(
            inv_data["block_a"],
            "Subtotal Energy Supply (Net)",
            inv_data["subtotal_a"]
        ),
        unsafe_allow_html=True
    )

    # Block B
    st.markdown("##### :material/grid_view: Block B: Regulated Grid Operator (DSO Transmission & Capacity)")
    st.markdown(
        _render_positions_table_html(
            inv_data["block_b"],
            "Subtotal Grid Transmission & Capacity (Net)",
            inv_data["subtotal_b"]
        ),
        unsafe_allow_html=True
    )

    # Block C
    st.markdown("##### :material/speed: Block C: Certified Metering Services (Meetbedrijf Telemetry)")
    st.markdown(
        _render_positions_table_html(
            inv_data["block_c"],
            "Subtotal Metering Services (Net)",
            inv_data["subtotal_c"]
        ),
        unsafe_allow_html=True
    )

    # Block D
    st.markdown("##### :material/account_balance: Block D: Statutory Energy Levies & VAT (Belastingen)")
    st.markdown(
        _render_positions_table_html(
            inv_data["block_d"],
            "Subtotal Statutory Levies & Taxes (Net)",
            inv_data["subtotal_d"]
        ),
        unsafe_allow_html=True
    )

    # ----------------------------------------------------------------------------------
    # Section 4: Graphical Invoice Attachment (Visual Enclosure)
    # ----------------------------------------------------------------------------------
    st.markdown("---")
    st.markdown("### :material/analytics: Graphical Billing Audit & Verification Enclosure")
    st.caption("Visual audit enclosure verifying cost distribution and 12-month payment trajectory.")

    # Target month for charts
    month_name_target = target_period.split()[0] if inv_data["is_single_month"] else None

    col_chart_left, col_chart_right = st.columns([1.2, 1.8])
    with col_chart_left:
        st.markdown(f"##### Cost Share ({inv_data['period_label']})")
        adapter_donut = convert_to_financial_cost_breakdown(
            result,
            target_month=month_name_target
        )
        donut_fig = create_cost_donut_figure(adapter_donut)
        st.plotly_chart(donut_fig, use_container_width=True)

    with col_chart_right:
        st.markdown("##### 12-Month Payment Schedule (Cash Outflow)")
        adapter_annual = convert_to_financial_cost_breakdown(result)
        series_fig = create_monthly_payment_series_figure(
            adapter_annual,
            highlight_month=month_name_target
        )
        st.plotly_chart(series_fig, use_container_width=True)

    with st.expander(":material/insights: Grid Operator Monthly Peak vs. Reserved Capacity Audit", expanded=False):
        fig_peak = create_dso_monthly_peak_figure(
            [r.dso for r in result.monthly_records],
            active_config.dso.contracted_capacity_kw
        )
        st.plotly_chart(fig_peak, use_container_width=True)

    # ----------------------------------------------------------------------------------
    # Section 5: Accounting Matrix & Multi-Format Export Toolbar
    # ----------------------------------------------------------------------------------
    st.markdown("---")
    st.markdown("### :material/table_view: Accounting Summary Matrix & Document Export")

    with st.expander(":material/table_rows: 12-Month Cross-Comparison Accounting Matrix", expanded=False):
        matrix_rows = []
        for r in result.monthly_records:
            matrix_rows.append({
                "Month": r.month_name,
                "Energy (kWh)": f"{r.consumption.total_kwh:,.0f}",
                "Peak (kW)": f"{r.consumption.peak_demand_kw:,.1f}",
                "Supplier (€)": f"€ {r.commercial.supplier_energy_cost + r.commercial.supplier_base_fee:,.2f}",
                "DSO (€)": f"€ {r.dso.subtotal_dso_net:,.2f}",
                "Metering (€)": f"€ {r.commercial.metering_fee:,.2f}",
                "Taxes (€)": f"€ {r.commercial.statutory_levies:,.2f}",
                "Total Net (€)": f"€ {r.total_net:,.2f}",
                "VAT (€)": f"€ {r.vat_amount:,.2f}",
                "Total Gross (€)": f"€ {r.total_gross:,.2f}",
                "Rate (€/kWh)": f"€ {r.effective_rate_net_kwh:.4f}",
                "Breach": f"+{r.dso.excess_capacity_kw:.1f} kW" if r.dso.is_capacity_breached else "OK"
            })
        st.dataframe(pd.DataFrame(matrix_rows), use_container_width=True, hide_index=True)

    # Flatten all positions for CSV export
    all_positions = []
    for block_name, pos_list in [
        ("Block A - Energy Supply", inv_data["block_a"]),
        ("Block B - Grid Operator", inv_data["block_b"]),
        ("Block C - Metering", inv_data["block_c"]),
        ("Block D - Taxes & Levies", inv_data["block_d"]),
    ]:
        for p in pos_list:
            all_positions.append({
                "Block": block_name,
                "Position": p["pos"],
                "Description": p["description"],
                "Quantity": p["quantity"],
                "Unit": p["unit"],
                "Rate_EUR": round(p["rate"], 4),
                "Amount_Net_EUR": round(p["amount_net"], 2),
            })

    col_exp1, col_exp2 = st.columns(2)
    with col_exp1:
        df_csv = pd.DataFrame(all_positions)
        csv_buf = io.StringIO()
        df_csv.to_csv(csv_buf, index=False, sep=";")
        st.download_button(
            label=f":material/download: Export Itemized Invoice CSV ({inv_data['inv_number']})",
            data=csv_buf.getvalue(),
            file_name=f"invoice_{inv_data['inv_number']}.csv",
            mime="text/csv",
            key=f"{key_prefix}_export_inv_csv",
            use_container_width=True
        )

    with col_exp2:
        export_payload = {
            "invoice_number": inv_data["inv_number"],
            "period": inv_data["period_label"],
            "days_count": inv_data["period_days"],
            "facility": site_name,
            "consumption_kwh": inv_data["kwh_total"],
            "peak_demand_kw": inv_data["p_max"],
            "contracted_capacity_kw": inv_data["contracted_kw"],
            "capacity_breach": inv_data["is_breached"],
            "subtotal_supplier_net": inv_data["subtotal_a"],
            "subtotal_dso_net": inv_data["subtotal_b"],
            "subtotal_metering_net": inv_data["subtotal_c"],
            "subtotal_taxes_net": inv_data["subtotal_d"],
            "total_net": inv_data["total_net"],
            "vat_21_pct": inv_data["vat_amount"],
            "total_gross": inv_data["total_gross"],
            "blended_price_net_kwh": inv_data["effective_rate_net"],
            "positions": all_positions
        }
        st.download_button(
            label=f":material/save: Export Invoice JSON ({inv_data['inv_number']})",
            data=json.dumps(export_payload, indent=2),
            file_name=f"invoice_{inv_data['inv_number']}.json",
            mime="application/json",
            key=f"{key_prefix}_export_inv_json",
            use_container_width=True
        )
