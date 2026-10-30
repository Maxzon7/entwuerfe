"""
========================================================================================
Sub-Tab 5: Classic Electricity Bill View (contract/tab_invoice_experimental.py)
========================================================================================

Description:
------------
Renders an authoritative, multi-section commercial electricity invoice layout strictly
adhering to the 4-Pillar glossary and zero-artificial-rounding reconciliation:
  1. Section 1: Control Bar (Billing Period Selector: Full Year 2025 vs. Single Month).
  2. Section 2: Invoice Cover Page (Letterhead, Plant/Customer Master Data, Physical
     Metrics, and Summary Block with Net Subtotal, VAT, and Total Gross Amount Due).
  3. Section 3: Itemized Invoice Positions (6-column structured ledger for Pillars 1-4:
     Energy Supply, Grid Network DSO, Metering & Telemetry, Statutory Taxes & Levies)
     mathematically reconciled to the cent without artificial rounding rows, followed by
     the Grand Total Reconciliation Table.
  4. Section 4: Graphical Invoice Attachment (Cost Donut, 12-Month Stacked Payment Schedule
     with active month highlight, and DSO Peak vs. Contracted Capacity audit chart).
  5. Section 5: Accounting Summary Matrix & Multi-Format Export Toolbar (CSV, JSON, and
     Multi-Period PDF Invoice Generator for Single Period, Custom Months, or Full 13-Page Book).
========================================================================================
"""

import io
import json
from typing import Dict, Any, List, Optional
import streamlit as st
import pandas as pd

try:
    from current_model.ui.common.cards import render_kpi_card
except ImportError:
    from ui.common.cards import render_kpi_card

try:
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
    from ui_sandbox.Currentsituation_sandbox.contract.invoice_pdf_exporter import (
        generate_multi_period_invoice_pdf,
    )
except ImportError:
    from current_model.ui_sandbox.Currentsituation_sandbox.engine.config_and_models import (
        LoadSeries2025,
        StatusQuoConfig2025,
        StatusQuoAnnualResult,
        PricingMode,
    )
    from current_model.ui_sandbox.Currentsituation_sandbox.engine.status_quo_master import (
        convert_to_financial_cost_breakdown,
    )
    from current_model.ui_sandbox.Currentsituation_sandbox.contract.charts import (
        create_cost_donut_figure,
        create_monthly_payment_series_figure,
        create_dso_monthly_peak_figure,
    )
    from current_model.ui_sandbox.Currentsituation_sandbox.contract.invoice_pdf_exporter import (
        generate_multi_period_invoice_pdf,
    )


def build_invoice_positions(
    result: StatusQuoAnnualResult,
    active_config: StatusQuoConfig2025,
    target_period: str
) -> Dict[str, Any]:
    """
    Derives mathematically reconciled, 6-column invoice line items for the selected period
    (Full Year 2025 or any of the 12 individual months).
    Guarantees cent-exact consistency with StatusQuoAnnualResult and StatusQuoMonthlyResult
    WITHOUT artificial rounding adjustment rows (Pos 1.9, 2.9, 4.9).
    Respects Market Role Toggles (enable_pillar_1_supplier..enable_pillar_4_taxes).
    """
    curr = getattr(active_config, "currency_code", "EUR")
    en_p1 = getattr(active_config, "enable_pillar_1_supplier", True)
    en_p2 = getattr(active_config, "enable_pillar_2_dso", True)
    en_p3 = getattr(active_config, "enable_pillar_3_metering", True)
    en_p4 = getattr(active_config, "enable_pillar_4_taxes", True)

    is_single_month = (target_period != "Annual Statement 2025 (Full Year)" and not target_period.startswith("Annual"))

    if is_single_month:
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
        kwh_sh = float(getattr(cons, "shoulder_tou_kwh", 0.0))
        p_max = cons.peak_demand_kw
        billed_peak_kw = float(getattr(dso_res, "billed_peak_demand_kw", 0.0)) or p_max

        target_supp_net = round(comm_res.supplier_energy_cost + comm_res.supplier_base_fee, 2) if en_p1 else 0.0
        target_dso_net = round(dso_res.subtotal_dso_net, 2) if en_p2 else 0.0
        target_meter_net = round(comm_res.metering_fee, 2) if en_p3 else 0.0
        target_levies_net = round(comm_res.statutory_levies, 2) if en_p4 else 0.0
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
        kwh_sh = sum(float(getattr(r.consumption, "shoulder_tou_kwh", 0.0)) for r in result.monthly_records)
        p_max = result.annual_peak_demand_kw
        billed_peak_kw = max(
            (float(getattr(r.dso, "billed_peak_demand_kw", 0.0)) or r.dso.measured_peak_demand_kw)
            for r in result.monthly_records
        ) if result.monthly_records else p_max

        target_supp_net = round(result.total_supplier_net, 2) if en_p1 else 0.0
        target_dso_net = round(result.total_dso_net, 2) if en_p2 else 0.0
        target_meter_net = round(result.total_metering_net, 2) if en_p3 else 0.0
        target_levies_net = round(result.total_levies_net, 2) if en_p4 else 0.0
        target_total_net = round(result.total_status_quo_net, 2)
        target_vat = round(result.total_vat_amount, 2)
        target_total_gross = round(result.total_status_quo_gross, 2)
        target_rate_net = result.blended_price_net_kwh

    contracted_kw = active_config.dso.contracted_capacity_kw
    is_breached = (p_max > contracted_kw)
    excess_kw = max(0.0, p_max - contracted_kw)
    is_3win = bool(getattr(active_config.dso, "enable_three_window_tou", False)) or (kwh_sh > 0.0)
    bill_pico_only = bool(getattr(active_config.dso, "bill_peak_demand_on_peak_tou_only", False))

    # ----------------------------------------------------------------------------------
    # Pillar 1 (Block A): Energy Supply (Retailer)
    # ----------------------------------------------------------------------------------
    block_a_positions: List[Dict[str, Any]] = []

    if en_p1:
        base_fee_net = round(
            comm_res.supplier_base_fee if is_single_month else sum(r.commercial.supplier_base_fee for r in result.monthly_records),
            2
        )
        block_a_positions.append({
            "pos": "1.1",
            "description": "Fixed Standing Fee (Retail Administration & Customer Service)",
            "quantity": float(months_count),
            "quantity_display": f"{months_count} mos" if not is_single_month else "1 mo",
            "unit": "months",
            "rate": active_config.supplier.base_fee_annual / 12.0,
            "amount_net": base_fee_net
        })

        surcharge_rate = active_config.supplier.procurement_fee_kwh + active_config.supplier.green_certificate_surcharge_kwh
        surcharges_net = round(kwh_total * surcharge_rate, 2)
        commodity_net = round(target_supp_net - base_fee_net - surcharges_net, 2)

        if active_config.supplier.is_dual_rate:
            ht_rate = active_config.supplier.fixed_rate_peak_kwh
            nt_rate = active_config.supplier.fixed_rate_offpeak_kwh
            ht_amount = round(kwh_ht * ht_rate, 2)
            nt_amount = round(commodity_net - ht_amount, 2)
            block_a_positions.append({
                "pos": "1.2",
                "description": "Active Energy Commodity — Peak Hours (HT)",
                "quantity": kwh_ht,
                "quantity_display": f"{kwh_ht:,.0f}",
                "unit": "kWh",
                "rate": ht_rate,
                "amount_net": ht_amount
            })
            block_a_positions.append({
                "pos": "1.3",
                "description": "Active Energy Commodity — Off-Peak Hours (NT)",
                "quantity": kwh_nt,
                "quantity_display": f"{kwh_nt:,.0f}",
                "unit": "kWh",
                "rate": nt_rate,
                "amount_net": nt_amount
            })
        elif active_config.supplier.pricing_mode == PricingMode.DYNAMIC:
            eff_spot_rate = commodity_net / max(1.0, kwh_total)
            block_a_positions.append({
                "pos": "1.2",
                "description": f"Day-Ahead EPEX Spot Wholesale Commodity + Retail Margin ({curr} {active_config.supplier.supplier_margin_kwh:.4f}/kWh)",
                "quantity": kwh_total,
                "quantity_display": f"{kwh_total:,.0f}",
                "unit": "kWh",
                "rate": eff_spot_rate,
                "amount_net": commodity_net
            })
        else:
            flat_rate = active_config.supplier.fixed_rate_kwh
            block_a_positions.append({
                "pos": "1.2",
                "description": "Active Energy Commodity — Fixed Single Flat Rate",
                "quantity": kwh_total,
                "quantity_display": f"{kwh_total:,.0f}",
                "unit": "kWh",
                "rate": flat_rate,
                "amount_net": commodity_net
            })

        if surcharge_rate > 0.0 or surcharges_net > 0.0:
            block_a_positions.append({
                "pos": "1.4",
                "description": "Procurement & Green Certificates (GvO)",
                "quantity": kwh_total,
                "quantity_display": f"{kwh_total:,.0f}",
                "unit": "kWh",
                "rate": surcharge_rate,
                "amount_net": surcharges_net
            })
    else:
        block_a_positions.append({
            "pos": "1.1",
            "description": "Energy Supply (Retailer) — Bypassed / Bundled into Single-Utility Grid Bill (Pillar 2)",
            "quantity": 0.0,
            "quantity_display": "Bypassed",
            "unit": "kWh",
            "rate": 0.0,
            "amount_net": 0.0
        })

    # ----------------------------------------------------------------------------------
    # Pillar 2 (Block B): Grid Network (DSO)
    # ----------------------------------------------------------------------------------
    block_b_positions: List[Dict[str, Any]] = []

    if en_p2:
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
            "description": f"Fixed Standing Fee — Grid Connection & Transport ({active_config.dso.dso_name})",
            "quantity": float(months_count),
            "quantity_display": f"{months_count} mos" if not is_single_month else "1 mo",
            "unit": "months",
            "rate": standing_dso_net / float(months_count),
            "amount_net": standing_dso_net
        })

        # Pos 2.2: Contracted Grid Capacity
        cap_fee_net = round(
            dso_res.contracted_capacity_fee if is_single_month else sum(r.dso.contracted_capacity_fee for r in result.monthly_records),
            2
        )
        if is_single_month:
            billed_kw_val = dso_res.billed_capacity_kw
            desc_cap = f"Contracted Grid Capacity ({active_config.dso.grid_tier})"
            if dso_res.is_capacity_breached and active_config.dso.adjust_capacity_on_breach:
                desc_cap += f" [Breach Adjusted to {billed_kw_val:.1f} kW]"
            cap_qty = billed_kw_val
            cap_qty_disp = f"{billed_kw_val:,.1f} kW"
            cap_unit = "kW/mo"
            cap_rate = active_config.dso.rate_contracted_capacity
        else:
            avg_billed_kw = sum(r.dso.billed_capacity_kw for r in result.monthly_records) / 12.0
            desc_cap = f"Contracted Grid Capacity ({active_config.dso.grid_tier})"
            if result.has_capacity_breach and active_config.dso.adjust_capacity_on_breach:
                desc_cap += f" [Breach-Adjusted Avg: {avg_billed_kw:.1f} kW]"
            cap_qty = avg_billed_kw
            cap_qty_disp = f"{avg_billed_kw:,.1f} kW (12 mos)"
            cap_unit = "kW/mo"
            cap_rate = active_config.dso.rate_contracted_capacity

        block_b_positions.append({
            "pos": "2.2",
            "description": desc_cap,
            "quantity": cap_qty,
            "quantity_display": cap_qty_disp,
            "unit": cap_unit,
            "rate": cap_rate,
            "amount_net": cap_fee_net
        })

        # Pos 2.3: Measured Monthly Peak Demand
        peak_fee_net = round(
            dso_res.peak_demand_fee if is_single_month else sum(r.dso.peak_demand_fee for r in result.monthly_records),
            2
        )
        if is_single_month:
            desc_peak = "Measured Monthly Peak Demand — Peak / Pico Hours (18:00–23:00)" if bill_pico_only else "Measured Monthly Peak Demand"
            peak_qty = billed_peak_kw
            peak_qty_disp = f"{billed_peak_kw:,.1f} kW"
            peak_unit = "kW/mo"
            peak_rate = active_config.dso.rate_peak_demand
        else:
            avg_monthly_peak_kw = sum(
                (float(getattr(r.dso, "billed_peak_demand_kw", 0.0)) or r.dso.measured_peak_demand_kw)
                for r in result.monthly_records
            ) / 12.0
            desc_peak = (
                f"Measured Monthly Peak Demand — Pico (Annual Max: {billed_peak_kw:,.1f} kW)"
                if bill_pico_only
                else f"Measured Monthly Peak Demand (Annual Max: {p_max:,.1f} kW)"
            )
            peak_qty = avg_monthly_peak_kw
            peak_qty_disp = f"Avg {avg_monthly_peak_kw:,.1f} kW (12 mos)"
            peak_unit = "kW/mo"
            peak_rate = active_config.dso.rate_peak_demand

        block_b_positions.append({
            "pos": "2.3",
            "description": desc_peak,
            "quantity": peak_qty,
            "quantity_display": peak_qty_disp,
            "unit": peak_unit,
            "rate": peak_rate,
            "amount_net": peak_fee_net
        })

        # Optional Pos 2.6: Explicit Excess Capacity Penalty (Exceso de Potencia)
        excess_pen_net = round(
            getattr(dso_res, "excess_penalty_fee", 0.0)
            if is_single_month
            else sum(getattr(r.dso, "excess_penalty_fee", 0.0) for r in result.monthly_records),
            2
        )

        # Optional Pos 2.7: Regulatory & Seasonal Pass-Through Adjustments
        reg_adj_net = round(
            getattr(dso_res, "regulatory_adjustments_fee", 0.0)
            if is_single_month
            else sum(getattr(r.dso, "regulatory_adjustments_fee", 0.0) for r in result.monthly_records),
            2
        )

        # Pos 2.4 / 2.5 (or 2.4a, 2.4b, 2.4c): Volumetric Network Transport / Active Energy
        vol_total_target = round(target_dso_net - standing_dso_net - cap_fee_net - peak_fee_net - excess_pen_net - reg_adj_net, 2)
        if is_3win:
            vol_peak_net = round(
                getattr(dso_res, "volumetric_peak_fee", round(kwh_ht * active_config.dso.rate_transport_peak_kwh, 2))
                if is_single_month
                else sum(getattr(r.dso, "volumetric_peak_fee", 0.0) for r in result.monthly_records),
                2
            )
            vol_offpeak_net = round(
                getattr(dso_res, "volumetric_offpeak_fee", round(kwh_nt * active_config.dso.rate_transport_offpeak_kwh, 2))
                if is_single_month
                else sum(getattr(r.dso, "volumetric_offpeak_fee", 0.0) for r in result.monthly_records),
                2
            )
            vol_shoulder_net = round(vol_total_target - vol_peak_net - vol_offpeak_net, 2)
            sh_rate = float(getattr(active_config.dso, "rate_transport_shoulder_kwh", 0.0)) or active_config.dso.rate_transport_peak_kwh
            block_b_positions.extend([
                {
                    "pos": "2.4a",
                    "description": "Active Energy — Peak / Pico (18:00–23:00)",
                    "quantity": kwh_ht,
                    "quantity_display": f"{kwh_ht:,.0f}",
                    "unit": "kWh",
                    "rate": active_config.dso.rate_transport_peak_kwh,
                    "amount_net": vol_peak_net,
                },
                {
                    "pos": "2.4b",
                    "description": "Active Energy — Off-Peak / Valle (23:00–05:00)",
                    "quantity": kwh_nt,
                    "quantity_display": f"{kwh_nt:,.0f}",
                    "unit": "kWh",
                    "rate": active_config.dso.rate_transport_offpeak_kwh,
                    "amount_net": vol_offpeak_net,
                },
                {
                    "pos": "2.4c",
                    "description": "Active Energy — Shoulder / Resto (05:00–18:00)",
                    "quantity": kwh_sh,
                    "quantity_display": f"{kwh_sh:,.0f}",
                    "unit": "kWh",
                    "rate": sh_rate,
                    "amount_net": vol_shoulder_net,
                },
            ])
        elif active_config.dso.rate_transport_peak_kwh > 0.0 or active_config.dso.rate_transport_offpeak_kwh > 0.0 or abs(vol_total_target) > 0.0:
            if active_config.dso.rate_transport_offpeak_kwh > 0.0:
                vol_peak_net = round(kwh_ht * active_config.dso.rate_transport_peak_kwh, 2)
                vol_offpeak_net = round(vol_total_target - vol_peak_net, 2)
                block_b_positions.append({
                    "pos": "2.4",
                    "description": "Volumetric Network Transport — Peak Hours (HT)",
                    "quantity": kwh_ht,
                    "quantity_display": f"{kwh_ht:,.0f}",
                    "unit": "kWh",
                    "rate": active_config.dso.rate_transport_peak_kwh,
                    "amount_net": vol_peak_net
                })
                block_b_positions.append({
                    "pos": "2.5",
                    "description": "Volumetric Network Transport — Off-Peak Hours (NT)",
                    "quantity": kwh_nt,
                    "quantity_display": f"{kwh_nt:,.0f}",
                    "unit": "kWh",
                    "rate": active_config.dso.rate_transport_offpeak_kwh,
                    "amount_net": vol_offpeak_net
                })
            else:
                block_b_positions.append({
                    "pos": "2.4",
                    "description": "Volumetric Network Transport — Peak Hours (HT)",
                    "quantity": kwh_ht,
                    "quantity_display": f"{kwh_ht:,.0f}",
                    "unit": "kWh",
                    "rate": active_config.dso.rate_transport_peak_kwh,
                    "amount_net": vol_total_target
                })
        elif abs(vol_total_target) > 0.0:
            block_b_positions[-1]["amount_net"] = round(block_b_positions[-1]["amount_net"] + vol_total_target, 2)

        if getattr(active_config.dso, "enable_excess_capacity_penalty", False) or excess_pen_net > 0.0:
            if is_single_month:
                ex_q = dso_res.excess_capacity_kw
                ex_disp = f"{ex_q:,.1f} kW"
            else:
                ex_q = sum(r.dso.excess_capacity_kw for r in result.monthly_records) / 12.0
                ex_disp = f"Avg {ex_q:,.1f} kW (12 mos)"
            block_b_positions.append({
                "pos": "2.6",
                "description": f"Excess Capacity Penalty (Exceso de Potencia > {contracted_kw:.0f} kW)",
                "quantity": ex_q,
                "quantity_display": ex_disp,
                "unit": "kW/mo",
                "rate": active_config.dso.peak_penalty_rate_kw,
                "amount_net": excess_pen_net
            })

        if abs(reg_adj_net) > 0.005:
            block_b_positions.append({
                "pos": "2.7",
                "description": "Regulatory & Seasonal Pass-Through Adjustments (GUDI / Seasonal Stabilization)",
                "quantity": float(months_count),
                "quantity_display": f"{months_count} mos" if not is_single_month else "1 mo",
                "unit": "months",
                "rate": round(reg_adj_net / float(months_count), 2),
                "amount_net": reg_adj_net,
            })
    else:
        block_b_positions.append({
            "pos": "2.1",
            "description": "Grid Network (DSO) — Bypassed under Custom Market Structure",
            "quantity": 0.0,
            "quantity_display": "Bypassed",
            "unit": "months",
            "rate": 0.0,
            "amount_net": 0.0
        })

    # ----------------------------------------------------------------------------------
    # Pillar 3 (Block C): Metering & Telemetry
    # ----------------------------------------------------------------------------------
    block_c_positions: List[Dict[str, Any]] = []
    if en_p3:
        block_c_positions.append({
            "pos": "3.1",
            "description": f"Fixed Standing Fee — Certified Metering & Telemetry ({active_config.metering.service_package_name} - {active_config.metering.meter_company_name})",
            "quantity": float(months_count),
            "quantity_display": f"{months_count} mos" if not is_single_month else "1 mo",
            "unit": "months",
            "rate": active_config.metering.annual_flat_fee / 12.0,
            "amount_net": target_meter_net
        })
    else:
        block_c_positions.append({
            "pos": "3.1",
            "description": "Certified Metering & Telemetry — Bypassed / Bundled into Single-Utility Grid Bill (Pillar 2)",
            "quantity": 0.0,
            "quantity_display": "Bypassed",
            "unit": "months",
            "rate": 0.0,
            "amount_net": 0.0
        })

    # ----------------------------------------------------------------------------------
    # Pillar 4 (Block D): Statutory Taxes & Levies
    # ----------------------------------------------------------------------------------
    block_d_positions: List[Dict[str, Any]] = []
    if en_p4:
        levy_rate = active_config.levies.statutory_levy_rate_kwh
        pct_levy_rate = float(getattr(active_config.levies, "percentage_levy_rate_pct", 0.0))
        electric_concepts_net = round(target_supp_net + target_dso_net + target_meter_net, 2)
        pct_levy_amount = round(electric_concepts_net * (pct_levy_rate / 100.0), 2) if pct_levy_rate > 0.0 else 0.0
        vol_levy_target = round(target_levies_net - pct_levy_amount, 2)
        gross_tax = round(kwh_total * levy_rate, 2)
        tax_credit = round(gross_tax - vol_levy_target, 2)

        if pct_levy_rate > 0.0 and levy_rate == 0.0:
            block_d_positions.append({
                "pos": "4.1",
                "description": f"Provincial & Municipal Percentage Levies ({pct_levy_rate:.4f}% of Electric Concepts)",
                "quantity": electric_concepts_net,
                "quantity_display": f"{curr} {electric_concepts_net:,.2f}",
                "unit": "%",
                "rate": pct_levy_rate,
                "amount_net": target_levies_net,
            })
        elif active_config.levies.annual_tax_reduction > 0.0 and tax_credit > 0.0:
            block_d_positions.append({
                "pos": "4.1",
                "description": "Statutory Energy Tax (Volumetric Levy)",
                "quantity": kwh_total,
                "quantity_display": f"{kwh_total:,.0f}",
                "unit": "kWh",
                "rate": levy_rate,
                "amount_net": gross_tax
            })
            block_d_positions.append({
                "pos": "4.2",
                "description": "Statutory Energy Tax Reduction Credit",
                "quantity": float(months_count),
                "quantity_display": f"{months_count} mos" if not is_single_month else "1 mo",
                "unit": "months",
                "rate": -round(tax_credit / float(months_count), 2),
                "amount_net": -tax_credit
            })
            if pct_levy_rate > 0.0:
                block_d_positions.append({
                    "pos": "4.3",
                    "description": f"Provincial & Municipal Percentage Levies ({pct_levy_rate:.4f}%)",
                    "quantity": electric_concepts_net,
                    "quantity_display": f"{curr} {electric_concepts_net:,.2f}",
                    "unit": "%",
                    "rate": pct_levy_rate,
                    "amount_net": pct_levy_amount,
                })
        else:
            block_d_positions.append({
                "pos": "4.1",
                "description": "Statutory Energy Tax (Volumetric Levy)",
                "quantity": kwh_total,
                "quantity_display": f"{kwh_total:,.0f}",
                "unit": "kWh",
                "rate": levy_rate,
                "amount_net": vol_levy_target
            })
            if pct_levy_rate > 0.0:
                block_d_positions.append({
                    "pos": "4.2",
                    "description": f"Provincial & Municipal Percentage Levies ({pct_levy_rate:.4f}%)",
                    "quantity": electric_concepts_net,
                    "quantity_display": f"{curr} {electric_concepts_net:,.2f}",
                    "unit": "%",
                    "rate": pct_levy_rate,
                    "amount_net": pct_levy_amount,
                })
    else:
        block_d_positions.append({
            "pos": "4.1",
            "description": "Statutory Energy Tax — Bypassed under Custom Market Structure",
            "quantity": 0.0,
            "quantity_display": "Bypassed",
            "unit": "kWh",
            "rate": 0.0,
            "amount_net": 0.0
        })

    # Ensure exact cent-level equality between sum of all 4 blocks and target_total_net
    sum_all_blocks = round(
        sum(p["amount_net"] for p in block_a_positions)
        + sum(p["amount_net"] for p in block_b_positions)
        + sum(p["amount_net"] for p in block_c_positions)
        + sum(p["amount_net"] for p in block_d_positions),
        2
    )
    residual_cent = round(target_total_net - sum_all_blocks, 2)
    if abs(residual_cent) > 0.0:
        if en_p1 and block_a_positions:
            for p in block_a_positions:
                if p["pos"] == "1.2":
                    p["amount_net"] = round(p["amount_net"] + residual_cent, 2)
                    break
        elif en_p2 and block_b_positions:
            block_b_positions[-1]["amount_net"] = round(block_b_positions[-1]["amount_net"] + residual_cent, 2)

    subtotal_a_val = round(sum(p["amount_net"] for p in block_a_positions), 2)
    subtotal_b_val = round(sum(p["amount_net"] for p in block_b_positions), 2)
    subtotal_c_val = round(sum(p["amount_net"] for p in block_c_positions), 2)
    subtotal_d_val = round(sum(p["amount_net"] for p in block_d_positions), 2)

    sh_pct = (kwh_sh / max(1.0, kwh_total)) * 100.0
    ht_pct_val = (kwh_ht / max(1.0, kwh_total)) * 100.0
    nt_pct_val = (kwh_nt / max(1.0, kwh_total)) * 100.0
    tou_split_summary = (
        f"Pico {ht_pct_val:.1f}% / Valle {nt_pct_val:.1f}% / Resto {sh_pct:.1f}%"
        if is_3win
        else f"HT {ht_pct_val:.1f}% / NT {nt_pct_val:.1f}%"
    )

    return {
        "period_label": period_label,
        "inv_number": inv_number,
        "period_days": period_days,
        "is_single_month": is_single_month,
        "month_index": month_idx,
        "currency_code": curr,
        # Physical
        "kwh_total": kwh_total,
        "kwh_ht": kwh_ht,
        "kwh_nt": kwh_nt,
        "kwh_sh": kwh_sh,
        "ht_pct": ht_pct_val,
        "nt_pct": nt_pct_val,
        "sh_pct": sh_pct,
        "tou_split_summary": tou_split_summary,
        "p_max": p_max,
        "billed_peak_kw": billed_peak_kw,
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
    subtotal_val: float,
    currency_code: str = "EUR",
    is_enabled: bool = True,
) -> str:
    """Renders a clean, high-contrast HTML ledger table without 4-space markdown code indentation."""
    rows_list: List[str] = []
    for idx, p in enumerate(positions):
        bg = "#1e293b" if idx % 2 == 0 else "#0f172a"
        unit_str = str(p["unit"])
        q_fmt = p.get("quantity_display")
        if not q_fmt:
            if unit_str in ("kW", "kW/mo"):
                q_fmt = f"{p['quantity']:,.1f}"
            elif unit_str == "kWh":
                q_fmt = f"{p['quantity']:,.0f}"
            else:
                q_fmt = f"{p['quantity']:.0f}"

        if unit_str in ("kWh", "kW", "kW/mo"):
            r_fmt = f"{currency_code} {p['rate']:.4f}"
        elif unit_str == "%":
            r_fmt = f"{p['rate']:.4f}%"
        else:
            r_fmt = f"{currency_code} {p['rate']:,.2f}"

        a_fmt = f"{currency_code} {p['amount_net']:,.2f}" if p["amount_net"] >= 0 else f"-{currency_code} {abs(p['amount_net']):,.2f}"
        color = "#f87171" if p["amount_net"] < 0 else "#e2e8f0"

        row_str = (
            f'<tr style="background-color: {bg}; border-bottom: 1px solid #334155;">'
            f'<td style="padding: 7px 10px; font-weight: 600; color: #94a3b8; font-size: 0.85rem;">{p["pos"]}</td>'
            f'<td style="padding: 7px 10px; color: #f1f5f9; font-size: 0.88rem;">{p["description"]}</td>'
            f'<td style="padding: 7px 10px; text-align: right; color: #cbd5e1; font-size: 0.88rem;">{q_fmt}</td>'
            f'<td style="padding: 7px 10px; text-align: center; color: #94a3b8; font-size: 0.82rem;">{unit_str}</td>'
            f'<td style="padding: 7px 10px; text-align: right; color: #cbd5e1; font-size: 0.88rem;">{r_fmt}</td>'
            f'<td style="padding: 7px 10px; text-align: right; font-weight: 600; color: {color}; font-size: 0.90rem;">{a_fmt}</td>'
            f'</tr>'
        )
        rows_list.append(row_str)

    rows_html = "\n".join(rows_list)
    sub_fmt = f"{currency_code} {subtotal_val:,.2f}"
    wrap_style = (
        "overflow-x: auto; margin-bottom: 16px; border-radius: 6px; border: 1px solid #334155;"
        if is_enabled
        else "overflow-x: auto; margin-bottom: 16px; border-radius: 6px; border: 1px dashed #475569; opacity: 0.45; filter: grayscale(100%);"
    )
    return (
        f'<div style="{wrap_style}">\n'
        f'<table style="width: 100%; border-collapse: collapse; font-family: -apple-system, BlinkMacSystemFont, sans-serif;">\n'
        f'<thead>\n'
        f'<tr style="background-color: #090d16; border-bottom: 2px solid #475569; color: #94a3b8; font-size: 0.80rem; text-transform: uppercase; letter-spacing: 0.05em;">'
        f'<th style="padding: 8px 10px; text-align: left; width: 6%;">Pos.</th>'
        f'<th style="padding: 8px 10px; text-align: left; width: 44%;">Description / Component</th>'
        f'<th style="padding: 8px 10px; text-align: right; width: 15%;">Quantity</th>'
        f'<th style="padding: 8px 10px; text-align: center; width: 9%;">Unit</th>'
        f'<th style="padding: 8px 10px; text-align: right; width: 13%;">Rate</th>'
        f'<th style="padding: 8px 10px; text-align: right; width: 13%;">Net Amount</th>'
        f'</tr>\n'
        f'</thead>\n'
        f'<tbody>\n'
        f'{rows_html}\n'
        f'<tr style="background-color: #0b1329; border-top: 2px solid #38bdf8; font-weight: 700;">'
        f'<td colspan="5" style="padding: 9px 10px; text-align: right; color: #38bdf8; font-size: 0.88rem; text-transform: uppercase;">{subtotal_title}:</td>'
        f'<td style="padding: 9px 10px; text-align: right; color: #38bdf8; font-size: 0.95rem;">{sub_fmt}</td>'
        f'</tr>\n'
        f'</tbody>\n'
        f'</table>\n'
        f'</div>'
    )


def _render_grand_total_reconciliation_html(
    inv_data: Dict[str, Any],
    vat_pct: float = 21.0,
    currency_code: str = "EUR",
) -> str:
    """Renders the Grand Total Reconciliation Table at the bottom of Section 3."""
    kwh = max(1.0, inv_data["kwh_total"])
    sub_a = inv_data["subtotal_a"]
    sub_b = inv_data["subtotal_b"]
    sub_c = inv_data["subtotal_c"]
    sub_d = inv_data["subtotal_d"]
    tot_net = inv_data["total_net"]
    vat_val = inv_data["vat_amount"]
    tot_gross = inv_data["total_gross"]

    return (
        f'<div style="border-radius: 8px; border: 2px solid #38bdf8; overflow: hidden; margin-top: 12px; margin-bottom: 16px;">\n'
        f'<div style="background-color: #0b1329; padding: 10px 14px; border-bottom: 1px solid #334155; font-weight: 700; color: #38bdf8; font-size: 0.92rem; text-transform: uppercase;">'
        f'Grand Total Invoice Reconciliation (4 Pillars &rarr; Net &rarr; Gross)'
        f'</div>\n'
        f'<table style="width: 100%; border-collapse: collapse; font-family: -apple-system, BlinkMacSystemFont, sans-serif;">\n'
        f'<tbody>\n'
        f'<tr style="background-color: #1e293b; border-bottom: 1px solid #334155;">'
        f'<td style="padding: 8px 14px; color: #f1f5f9; font-size: 0.88rem;">Subtotal 1: Pillar 1 — Energy Supply (Retailer) (Net)</td>'
        f'<td style="padding: 8px 14px; text-align: right; color: #cbd5e1; font-size: 0.86rem; font-family: monospace;">{currency_code} {sub_a / kwh:.4f}/kWh</td>'
        f'<td style="padding: 8px 14px; text-align: right; font-weight: 600; color: #38bdf8; font-size: 0.90rem;">{currency_code} {sub_a:,.2f}</td>'
        f'</tr>\n'
        f'<tr style="background-color: #0f172a; border-bottom: 1px solid #334155;">'
        f'<td style="padding: 8px 14px; color: #f1f5f9; font-size: 0.88rem;">+ Subtotal 2: Pillar 2 — Grid Network (DSO) (Net)</td>'
        f'<td style="padding: 8px 14px; text-align: right; color: #cbd5e1; font-size: 0.86rem; font-family: monospace;">{currency_code} {sub_b / kwh:.4f}/kWh</td>'
        f'<td style="padding: 8px 14px; text-align: right; font-weight: 600; color: #f59e0b; font-size: 0.90rem;">{currency_code} {sub_b:,.2f}</td>'
        f'</tr>\n'
        f'<tr style="background-color: #1e293b; border-bottom: 1px solid #334155;">'
        f'<td style="padding: 8px 14px; color: #f1f5f9; font-size: 0.88rem;">+ Subtotal 3: Pillar 3 — Metering & Telemetry (Net)</td>'
        f'<td style="padding: 8px 14px; text-align: right; color: #cbd5e1; font-size: 0.86rem; font-family: monospace;">{currency_code} {sub_c / kwh:.4f}/kWh</td>'
        f'<td style="padding: 8px 14px; text-align: right; font-weight: 600; color: #8b5cf6; font-size: 0.90rem;">{currency_code} {sub_c:,.2f}</td>'
        f'</tr>\n'
        f'<tr style="background-color: #0f172a; border-bottom: 1px solid #334155;">'
        f'<td style="padding: 8px 14px; color: #f1f5f9; font-size: 0.88rem;">+ Subtotal 4: Pillar 4 — Statutory Taxes & Levies (Net)</td>'
        f'<td style="padding: 8px 14px; text-align: right; color: #cbd5e1; font-size: 0.86rem; font-family: monospace;">{currency_code} {sub_d / kwh:.4f}/kWh</td>'
        f'<td style="padding: 8px 14px; text-align: right; font-weight: 600; color: #10b981; font-size: 0.90rem;">{currency_code} {sub_d:,.2f}</td>'
        f'</tr>\n'
        f'<tr style="background-color: #0b1329; border-top: 2px solid #38bdf8; font-weight: 700;">'
        f'<td style="padding: 10px 14px; color: #38bdf8; font-size: 0.92rem;">= TOTAL NET INVOICE AMOUNT (EXCL. VAT)</td>'
        f'<td style="padding: 10px 14px; text-align: right; color: #38bdf8; font-size: 0.88rem; font-family: monospace;">Blended Rate (Net): {currency_code} {inv_data["effective_rate_net"]:.4f}/kWh</td>'
        f'<td style="padding: 10px 14px; text-align: right; color: #ffffff; font-size: 1.00rem;">{currency_code} {tot_net:,.2f}</td>'
        f'</tr>\n'
        f'<tr style="background-color: #0f172a; border-top: 1px solid #334155;">'
        f'<td style="padding: 8px 14px; color: #94a3b8; font-size: 0.88rem;">+ Value Added Tax ({vat_pct:.0f}% VAT)</td>'
        f'<td style="padding: 8px 14px; text-align: right; color: #94a3b8; font-size: 0.85rem; font-family: monospace;">{currency_code} {vat_val / kwh:.4f}/kWh</td>'
        f'<td style="padding: 8px 14px; text-align: right; color: #cbd5e1; font-size: 0.90rem;">{currency_code} {vat_val:,.2f}</td>'
        f'</tr>\n'
        f'<tr style="background-color: #111827; border-top: 2px solid #10b981; font-weight: 800;">'
        f'<td style="padding: 12px 14px; color: #ffffff; font-size: 0.96rem;">= TOTAL GROSS AMOUNT DUE (INCL. VAT)</td>'
        f'<td style="padding: 12px 14px; text-align: right; color: #10b981; font-size: 0.90rem; font-family: monospace;">Blended Rate (Gross): {currency_code} {inv_data["effective_rate_gross"]:.4f}/kWh</td>'
        f'<td style="padding: 12px 14px; text-align: right; color: #10b981; font-size: 1.15rem;">{currency_code} {tot_gross:,.2f}</td>'
        f'</tr>\n'
        f'</tbody>\n'
        f'</table>\n'
        f'</div>'
    )


def render_invoice_experimental_tab(
    result: StatusQuoAnnualResult,
    active_config: StatusQuoConfig2025,
    load_series: LoadSeries2025,
    key_prefix: str = "currsit_contract",
    assumptions_dict: Optional[Dict[str, List[Dict[str, str]]]] = None,
) -> None:
    """
    Renders Sub-Tab 5: Classic Commercial Utility Invoice with Multi-Period PDF Export Center.
    """
    curr = getattr(active_config, "currency_code", "EUR")
    en_p1 = getattr(active_config, "enable_pillar_1_supplier", True)
    en_p2 = getattr(active_config, "enable_pillar_2_dso", True)
    en_p3 = getattr(active_config, "enable_pillar_3_metering", True)
    en_p4 = getattr(active_config, "enable_pillar_4_taxes", True)

    # ----------------------------------------------------------------------------------
    # Section 1: Control Bar (Billing Period Inspector)
    # ----------------------------------------------------------------------------------
    st.markdown("#### :material/receipt: Classic Commercial Electricity Bill (4-Pillar Itemized Ledger)")
    st.caption("Authoritative commercial utility invoice with cent-exact mathematical reconciliation across all 4 cost pillars.")

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
                f":material/calendar_today: **Monthly Utility Bill Statement:** {inv_data['period_label']} "
                f"({inv_data['period_days']} calendar days, {inv_data['period_days'] * 96:,} interval steps @ 15 min).",
                icon=":material/info:"
            )
        else:
            st.success(
                ":material/verified: **Consolidated Annual Electricity Bill 2025:** Full reference year "
                "(365 days, 35,040 steps @ 15 min, 100% cent-exact reconciliation).",
                icon=":material/check_circle:"
            )

    st.markdown("---")

    # ----------------------------------------------------------------------------------
    # Section 2: Invoice Cover Page
    # ----------------------------------------------------------------------------------
    site_name = st.session_state.get("active_csv_filename", "Industrial Peak Facility (Benchmark)")

    with st.container(border=True):
        col_hdr_left, col_hdr_right = st.columns(2)
        with col_hdr_left:
            st.markdown("##### :material/factory: Facility & Customer Master Data")
            st.markdown(
                f"**Facility / Site:** `{site_name}`<br>"
                f"**Grid Metering Code (EAN):** `871685900012345678`<br>"
                f"**Voltage Tier:** `{active_config.dso.grid_tier}`<br>"
                f"**Grid Network Operator (DSO):** `{active_config.dso.dso_name}`",
                unsafe_allow_html=True
            )
        with col_hdr_right:
            st.markdown("##### :material/receipt_long: Invoice & Contract Metadata")
            supp_disp = active_config.supplier.supplier_name if en_p1 else "Bundled in Utility [BYPASSED]"
            st.markdown(
                f"**Document Number:** `{inv_data['inv_number']}`<br>"
                f"**Accounting Period:** `{inv_data['period_label']}` ({inv_data['period_days']} days)<br>"
                f"**Energy Retailer:** `{supp_disp}`<br>"
                f"**Currency & Pricing Mode:** `{curr}` — `{active_config.supplier.pricing_mode.value.upper()}`",
                unsafe_allow_html=True
            )

        st.markdown("<hr style='margin: 12px 0; border-color: #334155;'>", unsafe_allow_html=True)

        st.markdown("###### :material/electric_bolt: Physical Billing Foundations & Load Factor")
        kpi_t1, kpi_t2, kpi_t3, kpi_t4 = st.columns(4)
        with kpi_t1:
            render_kpi_card(
                title=":material/bolt: Active Energy",
                value=f"{inv_data['kwh_total']:,.0f} kWh",
                subtext=inv_data.get("tou_split_summary", f"Peak (HT): {inv_data['ht_pct']:.1f}% | Off-Peak (NT): {inv_data['nt_pct']:.1f}%"),
                status="default"
            )
        with kpi_t2:
            bp_kw = float(inv_data.get("billed_peak_kw", inv_data["p_max"]))
            peak_sub = (
                f"Billed Pico Peak: {bp_kw:,.1f} kW"
                if abs(bp_kw - inv_data["p_max"]) > 0.05
                else "Highest 15-min interval demand"
            )
            render_kpi_card(
                title=":material/speed: Measured Monthly Peak Demand",
                value=f"{inv_data['p_max']:,.1f} kW",
                subtext=peak_sub,
                status="default"
            )
        with kpi_t3:
            breach_status = "alert" if inv_data["is_breached"] else "ok"
            breach_desc = f"+{inv_data['excess_kw']:.1f} kW Breach" if inv_data["is_breached"] else "100% Within Contract Limit"
            render_kpi_card(
                title=":material/verified_user: Contracted Grid Capacity",
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

        col_sum_left, col_sum_right = st.columns([1.2, 1.0])
        with col_sum_left:
            st.markdown("###### :material/pie_chart: 4-Pillar Net Cost Summary")
            share_supp = (inv_data["subtotal_a"] / max(1.0, inv_data["total_net"])) * 100.0
            share_dso = (inv_data["subtotal_b"] / max(1.0, inv_data["total_net"])) * 100.0
            share_meter = (inv_data["subtotal_c"] / max(1.0, inv_data["total_net"])) * 100.0
            share_levies = (inv_data["subtotal_d"] / max(1.0, inv_data["total_net"])) * 100.0

            p1_tag = "" if en_p1 else " [BYPASSED]"
            p2_tag = "" if en_p2 else " [BYPASSED]"
            p3_tag = "" if en_p3 else " [BYPASSED]"
            p4_tag = "" if en_p4 else " [BYPASSED]"

            st.markdown(
                f'<div style="font-size: 0.90rem; line-height: 1.8; color: #cbd5e1;">'
                f'• <b>Pillar 1: Energy Supply (Retailer){p1_tag}:</b> {curr} {inv_data["subtotal_a"]:,.2f} <span style="color: #38bdf8;">({share_supp:.1f}%)</span><br>'
                f'• <b>Pillar 2: Grid Network (DSO){p2_tag}:</b> {curr} {inv_data["subtotal_b"]:,.2f} <span style="color: #f59e0b;">({share_dso:.1f}%)</span><br>'
                f'• <b>Pillar 3: Metering & Telemetry{p3_tag}:</b> {curr} {inv_data["subtotal_c"]:,.2f} <span style="color: #8b5cf6;">({share_meter:.1f}%)</span><br>'
                f'• <b>Pillar 4: Statutory Taxes & Levies{p4_tag}:</b> {curr} {inv_data["subtotal_d"]:,.2f} <span style="color: #10b981;">({share_levies:.1f}%)</span>'
                f'</div>',
                unsafe_allow_html=True
            )

        with col_sum_right:
            vat_pct = active_config.levies.vat_rate_pct
            st.markdown(
                f'<div style="background-color: #0b1329; border: 2px solid #38bdf8; border-radius: 8px; padding: 14px 18px; text-align: right;">'
                f'<div style="color: #94a3b8; font-size: 0.82rem; text-transform: uppercase;">Total Net Invoice Amount (Excl. VAT)</div>'
                f'<div style="color: #e2e8f0; font-size: 1.15rem; font-weight: 600; margin-bottom: 4px;">{curr} {inv_data["total_net"]:,.2f}</div>'
                f'<div style="color: #94a3b8; font-size: 0.82rem; text-transform: uppercase;">+ Value Added Tax ({vat_pct:.0f}% VAT)</div>'
                f'<div style="color: #cbd5e1; font-size: 1.00rem; font-weight: 500; margin-bottom: 8px;">{curr} {inv_data["vat_amount"]:,.2f}</div>'
                f'<hr style="border-color: #334155; margin: 8px 0;">'
                f'<div style="color: #38bdf8; font-size: 0.85rem; font-weight: 700; text-transform: uppercase;">Total Gross Amount Due</div>'
                f'<div style="color: #ffffff; font-size: 1.65rem; font-weight: 800; letter-spacing: -0.02em;">{curr} {inv_data["total_gross"]:,.2f}</div>'
                f'<div style="color: #94a3b8; font-size: 0.80rem; margin-top: 6px;">'
                f'Blended Rate (Net): <b>{curr} {inv_data["effective_rate_net"]:.4f}/kWh</b> | Blended Rate (Gross): <b>{curr} {inv_data["effective_rate_gross"]:.4f}/kWh</b>'
                f'</div>'
                f'</div>',
                unsafe_allow_html=True
            )

    # ----------------------------------------------------------------------------------
    # Section 3: Itemized Invoice Positions (Pillars 1-4 + Grand Total Reconciliation)
    # ----------------------------------------------------------------------------------
    st.markdown("### :material/format_list_numbered: Itemized Electricity Bill Schedule")
    st.caption("Standard 6-column commercial invoice format: Pos. | Description | Quantity | Unit | Rate | Net Amount.")

    # Pillar 1
    p1_hdr = "##### :material/storefront: Pillar 1: Energy Supply (Retailer)" + ("" if en_p1 else " `[BYPASSED / GRAYED OUT]`")
    st.markdown(p1_hdr)
    st.markdown(
        _render_positions_table_html(
            inv_data["block_a"],
            "Subtotal 1: Energy Supply (Net)",
            inv_data["subtotal_a"],
            currency_code=curr,
            is_enabled=en_p1,
        ),
        unsafe_allow_html=True
    )

    # Pillar 2
    p2_hdr = "##### :material/grid_view: Pillar 2: Grid Network (DSO)" + ("" if en_p2 else " `[BYPASSED / GRAYED OUT]`")
    st.markdown(p2_hdr)
    st.markdown(
        _render_positions_table_html(
            inv_data["block_b"],
            "Subtotal 2: Grid Network DSO (Net)",
            inv_data["subtotal_b"],
            currency_code=curr,
            is_enabled=en_p2,
        ),
        unsafe_allow_html=True
    )

    # Pillar 3
    p3_hdr = "##### :material/speed: Pillar 3: Metering & Telemetry" + ("" if en_p3 else " `[BYPASSED / GRAYED OUT]`")
    st.markdown(p3_hdr)
    st.markdown(
        _render_positions_table_html(
            inv_data["block_c"],
            "Subtotal 3: Metering & Telemetry (Net)",
            inv_data["subtotal_c"],
            currency_code=curr,
            is_enabled=en_p3,
        ),
        unsafe_allow_html=True
    )

    # Pillar 4
    p4_hdr = "##### :material/account_balance: Pillar 4: Statutory Taxes & Levies" + ("" if en_p4 else " `[BYPASSED / GRAYED OUT]`")
    st.markdown(p4_hdr)
    st.markdown(
        _render_positions_table_html(
            inv_data["block_d"],
            "Subtotal 4: Statutory Energy Taxes (Net)",
            inv_data["subtotal_d"],
            currency_code=curr,
            is_enabled=en_p4,
        ),
        unsafe_allow_html=True
    )

    # Grand Total Reconciliation Table
    st.markdown(
        _render_grand_total_reconciliation_html(
            inv_data=inv_data,
            vat_pct=active_config.levies.vat_rate_pct,
            currency_code=curr,
        ),
        unsafe_allow_html=True
    )

    # ----------------------------------------------------------------------------------
    # Section 4: Graphical Invoice Attachment (Visual Enclosure)
    # ----------------------------------------------------------------------------------
    st.markdown("---")
    st.markdown("### :material/analytics: Graphical Billing Audit & Verification Enclosure")
    st.caption("Visual audit enclosure verifying cost distribution and 12-month payment schedule.")

    month_name_target = selected_period.split()[0] if inv_data["is_single_month"] else None

    col_chart_left, col_chart_right = st.columns([1.2, 1.8])
    with col_chart_left:
        st.markdown(f"##### Cost Share ({inv_data['period_label']})")
        adapter_donut = convert_to_financial_cost_breakdown(
            result,
            target_month=month_name_target
        )
        donut_fig = create_cost_donut_figure(adapter_donut)
        st.plotly_chart(donut_fig, use_container_width=True, key=f"{key_prefix}_inv_donut_chart")

    with col_chart_right:
        st.markdown("##### 12-Month Payment Schedule")
        adapter_annual = convert_to_financial_cost_breakdown(result)
        series_fig = create_monthly_payment_series_figure(
            adapter_annual,
            highlight_month=month_name_target
        )
        st.plotly_chart(series_fig, use_container_width=True, key=f"{key_prefix}_inv_series_chart")

    with st.expander(":material/insights: Grid Network (DSO) Monthly Peak vs. Contracted Capacity Audit", expanded=False):
        fig_peak = create_dso_monthly_peak_figure(
            [r.dso for r in result.monthly_records],
            active_config.dso.contracted_capacity_kw
        )
        st.plotly_chart(fig_peak, use_container_width=True, key=f"{key_prefix}_inv_peak_chart")

    # ----------------------------------------------------------------------------------
    # Section 5: Accounting Matrix, Component Schedules & Multi-Period PDF Export Center
    # ----------------------------------------------------------------------------------
    st.markdown("---")
    st.markdown("### :material/table_view: Accounting Summary Matrix & Detailed Component Schedules")

    with st.expander(":material/table_rows: Consolidated 12-Month Cross-Comparison Accounting Matrix", expanded=False):
        matrix_rows = []
        for r in result.monthly_records:
            matrix_rows.append({
                "Month": r.month_name,
                "Energy (kWh)": f"{r.consumption.total_kwh:,.0f}",
                "Peak (kW)": f"{r.consumption.peak_demand_kw:,.1f}",
                f"1. Energy Supply ({curr})": f"{curr} {r.commercial.supplier_energy_cost + r.commercial.supplier_base_fee:,.2f}",
                f"2. Grid Network DSO ({curr})": f"{curr} {r.dso.subtotal_dso_net:,.2f}",
                f"3. Metering ({curr})": f"{curr} {r.commercial.metering_fee:,.2f}",
                f"4. Statutory Taxes ({curr})": f"{curr} {r.commercial.statutory_levies:,.2f}",
                f"Total Net ({curr})": f"{curr} {r.total_net:,.2f}",
                f"VAT ({curr})": f"{curr} {r.vat_amount:,.2f}",
                f"Total Gross ({curr})": f"{curr} {r.total_gross:,.2f}",
                f"Blended Rate Net ({curr}/kWh)": f"{curr} {r.effective_rate_net_kwh:.4f}",
                "Capacity Breach": f"+{r.dso.excess_capacity_kw:.1f} kW" if r.dso.is_capacity_breached else "OK"
            })
        st.dataframe(pd.DataFrame(matrix_rows), use_container_width=True, hide_index=True)

    with st.expander(":material/account_tree: Itemized 12-Month Schedules by Cost Pillar (DSO, Supplier, Metering, Taxes)", expanded=False):
        tab_p1, tab_p2, tab_p3, tab_p4 = st.tabs([
            ":material/storefront: Pillar 1: Energy Supply",
            ":material/grid_view: Pillar 2: Grid Network (DSO)",
            ":material/speed: Pillar 3: Metering & Telemetry",
            ":material/account_balance: Pillar 4: Statutory Taxes"
        ])

        with tab_p1:
            st.markdown("###### 12-Month Energy Supply (Retailer) Payment Schedule")
            p1_schedule = []
            for r in result.monthly_records:
                c = r.consumption
                m_comm = r.commercial
                e_tot = m_comm.supplier_energy_cost
                base = m_comm.supplier_base_fee
                p1_tot = round(e_tot + base, 2)
                p1_schedule.append({
                    "Month": r.month_name,
                    "Total Consumption (kWh)": f"{c.total_kwh:,.0f}",
                    "Peak HT (kWh)": f"{c.peak_tou_kwh:,.0f}",
                    "Off-Peak NT (kWh)": f"{c.offpeak_tou_kwh:,.0f}",
                    f"Fixed Standing Fee ({curr})": f"{curr} {base:,.2f}",
                    f"Commodity & Surcharges ({curr})": f"{curr} {e_tot:,.2f}",
                    f"Subtotal Supply Net ({curr})": f"{curr} {p1_tot:,.2f}",
                    f"Effective Rate ({curr}/kWh)": f"{curr} {p1_tot / max(1.0, c.total_kwh):.4f}"
                })
            tot_p1_kwh = result.total_consumption_kwh
            tot_p1_base = sum(r.commercial.supplier_base_fee for r in result.monthly_records)
            tot_p1_energy = sum(r.commercial.supplier_energy_cost for r in result.monthly_records)
            tot_p1_net = result.total_supplier_net
            p1_schedule.append({
                "Month": "FULL YEAR 2025",
                "Total Consumption (kWh)": f"{tot_p1_kwh:,.0f}",
                "Peak HT (kWh)": f"{result.total_peak_tou_kwh:,.0f}",
                "Off-Peak NT (kWh)": f"{result.total_offpeak_tou_kwh:,.0f}",
                f"Fixed Standing Fee ({curr})": f"{curr} {tot_p1_base:,.2f}",
                f"Commodity & Surcharges ({curr})": f"{curr} {tot_p1_energy:,.2f}",
                f"Subtotal Supply Net ({curr})": f"{curr} {tot_p1_net:,.2f}",
                f"Effective Rate ({curr}/kWh)": f"{curr} {tot_p1_net / max(1.0, tot_p1_kwh):.4f}"
            })
            st.dataframe(pd.DataFrame(p1_schedule), use_container_width=True, hide_index=True)

        with tab_p2:
            st.markdown("###### 12-Month Regulated Grid Operator (DSO) Payment Schedule")
            p2_schedule = []
            for r in result.monthly_records:
                d = r.dso
                stand = round(d.fixed_connection_fee + d.fixed_transport_fee + d.cable_surcharge, 2)
                p2_schedule.append({
                    "Month": r.month_name,
                    "Measured Peak (kW)": f"{d.measured_peak_demand_kw:,.1f}",
                    "Billed Capacity (kW)": f"{d.billed_capacity_kw:,.1f}",
                    f"Fixed Standing Fee ({curr})": f"{curr} {stand:,.2f}",
                    f"Contracted Capacity Fee ({curr})": f"{curr} {d.contracted_capacity_fee:,.2f}",
                    f"Peak Demand Fee ({curr})": f"{curr} {d.peak_demand_fee:,.2f}",
                    f"Volumetric Transport ({curr})": f"{curr} {d.volumetric_transport_fee:,.2f}",
                    f"Subtotal DSO Net ({curr})": f"{curr} {d.subtotal_dso_net:,.2f}",
                    "Breach": "YES" if d.is_capacity_breached else "NO"
                })
            tot_p2_stand = sum(r.dso.fixed_connection_fee + r.dso.fixed_transport_fee + r.dso.cable_surcharge for r in result.monthly_records)
            tot_p2_cap = sum(r.dso.contracted_capacity_fee for r in result.monthly_records)
            tot_p2_peak = sum(r.dso.peak_demand_fee for r in result.monthly_records)
            tot_p2_vol = sum(r.dso.volumetric_transport_fee for r in result.monthly_records)
            tot_p2_net = result.total_dso_net
            p2_schedule.append({
                "Month": "FULL YEAR 2025",
                "Measured Peak (kW)": f"Max {result.annual_peak_demand_kw:,.1f}",
                "Billed Capacity (kW)": f"Cap {active_config.dso.contracted_capacity_kw:,.0f}",
                f"Fixed Standing Fee ({curr})": f"{curr} {tot_p2_stand:,.2f}",
                f"Contracted Capacity Fee ({curr})": f"{curr} {tot_p2_cap:,.2f}",
                f"Peak Demand Fee ({curr})": f"{curr} {tot_p2_peak:,.2f}",
                f"Volumetric Transport ({curr})": f"{curr} {tot_p2_vol:,.2f}",
                f"Subtotal DSO Net ({curr})": f"{curr} {tot_p2_net:,.2f}",
                "Breach": f"{len(result.breach_months)} mos" if result.has_capacity_breach else "NO"
            })
            st.dataframe(pd.DataFrame(p2_schedule), use_container_width=True, hide_index=True)

        with tab_p3:
            st.markdown("###### 12-Month Certified Metering & Telemetry Payment Schedule")
            p3_schedule = []
            for r in result.monthly_records:
                p3_schedule.append({
                    "Month": r.month_name,
                    "Provider & Package": f"{active_config.metering.meter_company_name} - {active_config.metering.service_package_name}",
                    "Telemetry Interval": "15-min RLM",
                    f"Monthly Metering Fee ({curr})": f"{curr} {r.commercial.metering_fee:,.2f}",
                    f"Subtotal Metering Net ({curr})": f"{curr} {r.commercial.metering_fee:,.2f}"
                })
            p3_schedule.append({
                "Month": "FULL YEAR 2025",
                "Provider & Package": f"{active_config.metering.meter_company_name}",
                "Telemetry Interval": "12 Billing Months",
                f"Monthly Metering Fee ({curr})": f"{curr} {result.total_metering_net / 12.0:,.2f} / mo",
                f"Subtotal Metering Net ({curr})": f"{curr} {result.total_metering_net:,.2f}"
            })
            st.dataframe(pd.DataFrame(p3_schedule), use_container_width=True, hide_index=True)

        with tab_p4:
            st.markdown("###### 12-Month Statutory Energy Taxes & Levies Schedule")
            p4_schedule = []
            levy_r = active_config.levies.statutory_levy_rate_kwh if en_p4 else 0.0
            for r in result.monthly_records:
                k_m = r.consumption.total_kwh
                gross_tax_m = round(k_m * levy_r, 2)
                net_levy_m = r.commercial.statutory_levies
                eff_cred_m = round(gross_tax_m - net_levy_m, 2)
                p4_schedule.append({
                    "Month": r.month_name,
                    "Consumption (kWh)": f"{k_m:,.0f}",
                    f"Tax Rate ({curr}/kWh)": f"{curr} {levy_r:.4f}",
                    f"Gross Energy Tax ({curr})": f"{curr} {gross_tax_m:,.2f}",
                    f"Tax Reduction Credit ({curr})": f"-{curr} {eff_cred_m:,.2f}" if eff_cred_m > 0 else f"{curr} 0.00",
                    f"Net Statutory Taxes ({curr})": f"{curr} {net_levy_m:,.2f}"
                })
            tot_p4_kwh = result.total_consumption_kwh
            tot_p4_gross = round(tot_p4_kwh * levy_r, 2)
            tot_p4_net = result.total_levies_net
            tot_p4_credit = round(tot_p4_gross - tot_p4_net, 2)
            p4_schedule.append({
                "Month": "FULL YEAR 2025",
                "Consumption (kWh)": f"{tot_p4_kwh:,.0f}",
                f"Tax Rate ({curr}/kWh)": f"{curr} {levy_r:.4f}",
                f"Gross Energy Tax ({curr})": f"{curr} {tot_p4_gross:,.2f}",
                f"Tax Reduction Credit ({curr})": f"-{curr} {tot_p4_credit:,.2f}" if tot_p4_credit > 0 else f"{curr} 0.00",
                f"Net Statutory Taxes ({curr})": f"{curr} {tot_p4_net:,.2f}"
            })
            st.dataframe(pd.DataFrame(p4_schedule), use_container_width=True, hide_index=True)

    # ----------------------------------------------------------------------------------
    # Section 6: Multi-Period PDF Invoice & Document Export Center
    # ----------------------------------------------------------------------------------
    st.markdown("---")
    with st.container(border=True):
        st.markdown("#### :material/picture_as_pdf: PDF Invoice & Multi-Month Document Export Center")
        st.caption(
            "Export formatted A4 PDF utility invoices for the active period, a custom selection of months (e.g., Q1 or Jan–Dec), "
            "or a complete 13-page Annual + 12-Month Invoice Book."
        )

        pdf_mode_options = [
            f"Single Active Period ({selected_period})",
            "Custom Multi-Month Selection (1 Page per Month)",
            "Full 13-Page Annual + 12-Month Invoice Book (2025)"
        ]
        col_pdf_m, col_pdf_sel = st.columns([1.6, 2.4])
        with col_pdf_m:
            selected_pdf_mode = st.selectbox(
                "PDF Export Scope:",
                options=pdf_mode_options,
                index=0,
                key=f"{key_prefix}_pdf_scope_mode"
            )

        all_12_month_labels = [f"{r.month_name} 2025" for r in result.monthly_records]
        with col_pdf_sel:
            if "Custom Multi-Month" in selected_pdf_mode:
                selected_custom_months = st.multiselect(
                    "Select Billing Months to Include in PDF:",
                    options=all_12_month_labels,
                    default=all_12_month_labels[:3],
                    key=f"{key_prefix}_pdf_custom_months"
                )
                target_pdf_periods = selected_custom_months if selected_custom_months else [selected_period]
            elif "Full 13-Page" in selected_pdf_mode:
                target_pdf_periods = ["Annual Statement 2025 (Full Year)"] + all_12_month_labels
                st.info(":material/menu_book: **13-Page Invoice Book Ready:** Page 1 = Consolidated Annual Statement, Pages 2–13 = Jan–Dec Monthly Bills.", icon=":material/info:")
            else:
                target_pdf_periods = [selected_period]
                st.info(f":material/description: **Single-Page Invoice Ready:** Exporting `{inv_data['inv_number']}` ({inv_data['period_label']}).", icon=":material/check_circle:")

        pdf_bytes = generate_multi_period_invoice_pdf(
            result=result,
            active_config=active_config,
            periods=target_pdf_periods,
            build_positions_fn=build_invoice_positions,
            site_name=site_name,
            assumptions_dict=assumptions_dict,
        )

        all_positions = []
        for block_name, pos_list in [
            ("Pillar 1 - Energy Supply (Retailer)", inv_data["block_a"]),
            ("Pillar 2 - Grid Network (DSO)", inv_data["block_b"]),
            ("Pillar 3 - Metering & Telemetry", inv_data["block_c"]),
            ("Pillar 4 - Statutory Taxes & Levies", inv_data["block_d"]),
        ]:
            for p in pos_list:
                all_positions.append({
                    "Pillar": block_name,
                    "Position": p["pos"],
                    "Description": p["description"],
                    "Quantity": p["quantity"],
                    "Unit": p["unit"],
                    f"Rate_{curr}": round(p["rate"], 4),
                    f"Amount_Net_{curr}": round(p["amount_net"], 2),
                })

        col_exp_pdf, col_exp1, col_exp2 = st.columns([1.4, 1.1, 1.1])
        with col_exp_pdf:
            pdf_fname = (
                "invoice_book_2025_13pages.pdf"
                if len(target_pdf_periods) == 13
                else (
                    f"invoices_multi_{len(target_pdf_periods)}mos_2025.pdf"
                    if len(target_pdf_periods) > 1
                    else f"invoice_{inv_data['inv_number']}.pdf"
                )
            )
            st.download_button(
                label=f":material/picture_as_pdf: Download PDF Invoice ({len(target_pdf_periods)} Page{'s' if len(target_pdf_periods) > 1 else ''})",
                data=pdf_bytes,
                file_name=pdf_fname,
                mime="application/pdf",
                type="primary",
                key=f"{key_prefix}_export_inv_pdf",
                use_container_width=True
            )

        with col_exp1:
            df_csv = pd.DataFrame(all_positions)
            csv_buf = io.StringIO()
            df_csv.to_csv(csv_buf, index=False, sep=";")
            st.download_button(
                label=f":material/download: Export Itemized CSV ({inv_data['inv_number']})",
                data=csv_buf.getvalue(),
                file_name=f"invoice_{inv_data['inv_number']}.csv",
                mime="text/csv",
                key=f"{key_prefix}_export_inv_csv",
                use_container_width=True
            )

        with col_exp2:
            export_payload = {
                "invoice_number": inv_data["inv_number"],
                "currency": curr,
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
                "vat_amount": inv_data["vat_amount"],
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
