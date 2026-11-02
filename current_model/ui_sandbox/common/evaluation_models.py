"""
========================================================================================
Shared Foundation: Scenario Evaluation Models & 4-Pillar Bill Comparison (ui_sandbox/common/evaluation_models.py)
========================================================================================

Implements the 3 core architectural building blocks shared by all 6 standalone scenario sandboxes:
  - Building Block 1: `build_residual_load_series_2025` (transforms any post-mitigation 35,040-step
    grid import array P_Grid(t) into a validated LoadSeries2025 object).
  - Building Block 2: `evaluate_scenario_4pillar_bill_comparison` & `render_shared_4pillar_bill_comparison_ui`
    (passes both Baseline and Residual/Alternative scenarios through `calculate_status_quo_master_2025`
    and `build_invoice_positions` to produce reconciled side-by-side 4-Pillar statements + PDF export).
  - Building Block 3: `ScenarioEvaluationOutput` & `render_scenario_evaluation_output_card`
    (standardized technical & financial output container for future multi-scenario aggregation).
========================================================================================
"""

from dataclasses import dataclass, asdict
from typing import Dict, List, Any, Optional, Tuple
import json
import datetime
import numpy as np
import pandas as pd
import streamlit as st

try:
    from ui_sandbox.Currentsituation_sandbox.engine.config_and_models import (
        LoadSeries2025,
        StatusQuoConfig2025,
        StatusQuoAnnualResult,
    )
    from ui_sandbox.Currentsituation_sandbox.engine.consumption_pipeline import (
        create_reference_2025_timestamps,
        classify_liander_tou_window,
        classify_edemsa_tou_windows,
        MONTH_NAMES,
    )
    from ui_sandbox.Currentsituation_sandbox.engine.status_quo_master import (
        calculate_status_quo_master_2025,
    )
    from ui_sandbox.Currentsituation_sandbox.contract.tab_invoice_experimental import (
        build_invoice_positions,
    )
    from ui_sandbox.Currentsituation_sandbox.contract.invoice_pdf_exporter import (
        generate_bess_comparison_report_pdf,
    )
except ImportError:
    from current_model.ui_sandbox.Currentsituation_sandbox.engine.config_and_models import (
        LoadSeries2025,
        StatusQuoConfig2025,
        StatusQuoAnnualResult,
    )
    from current_model.ui_sandbox.Currentsituation_sandbox.engine.consumption_pipeline import (
        create_reference_2025_timestamps,
        classify_liander_tou_window,
        classify_edemsa_tou_windows,
        MONTH_NAMES,
    )
    from current_model.ui_sandbox.Currentsituation_sandbox.engine.status_quo_master import (
        calculate_status_quo_master_2025,
    )
    from current_model.ui_sandbox.Currentsituation_sandbox.contract.tab_invoice_experimental import (
        build_invoice_positions,
    )
    from current_model.ui_sandbox.Currentsituation_sandbox.contract.invoice_pdf_exporter import (
        generate_bess_comparison_report_pdf,
    )


@dataclass
class ScenarioEvaluationOutput:
    """
    Standardized Evaluation Output Container (Building Block 3).
    Every standalone scenario sandbox produces this exact structure so all 6 scenarios
    can later be aggregated and compared side-by-side in a unified master program.
    """
    scenario_id: str                        # "status_quo", "new_contract", "solar_only", "bess_only", "solar_bess", "generator"
    scenario_name: str                      # Human-readable scenario name
    sub_scenario_label: str                 # e.g. "Pareto Sweet-Spot (85% Coverage)" or "Solar 60% Demand"
    currency_code: str                      # "EUR", "ARS", "USD"

    # Technical KPIs
    peak_before_kw: float
    peak_after_kw: float
    peak_shaved_kw: float
    peak_shaved_pct: float
    grid_limit_kw: float
    overload_hours_before: float
    overload_hours_after: float
    annual_load_kwh: float
    annual_grid_import_before_kwh: float
    annual_grid_import_after_kwh: float
    self_consumption_pct: float
    autarky_pct: float

    # Financial KPIs (Coupled with 4-Pillar Billing Engine)
    capex_total: float
    annual_tech_opex: float                 # O&M, leasing, or generator fuel cost
    annual_grid_bill_net_before: float
    annual_grid_bill_net_after: float
    annual_grid_bill_gross_before: float
    annual_grid_bill_gross_after: float
    annual_net_savings: float               # (Grid Bill Before - Grid Bill After) - Tech OPEX + Feed-In Credit
    simple_payback_years: float
    npv_15y_tco_before: float
    npv_15y_tco_after: float
    npv_15y_net_benefit: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScenarioEvaluationOutput":
        return cls(**data)


def compute_15y_tco_npv(
    capex: float,
    annual_grid_bill_year1: float,
    annual_tech_opex_year1: float = 0.0,
    annual_feed_in_credit_year1: float = 0.0,
    discount_rate_pct: float = 5.0,
    escalation_rate_pct: float = 3.0,
    horizon_years: int = 15,
    replacement_year: int = 0,
    replacement_cost: float = 0.0,
) -> Tuple[float, List[Dict[str, float]]]:
    """
    Computes the 15-Year Total Cost of Ownership (TCO) Net Present Value (NPV)
    and annual cashflow schedule for any scenario.
    Returns (npv_tco_total, yearly_schedule_list).
    """
    r = discount_rate_pct / 100.0
    g = escalation_rate_pct / 100.0
    npv_total = float(capex)
    cum_nominal = float(capex)
    cum_discounted = float(capex)
    schedule: List[Dict[str, float]] = [
        {
            "year": 0,
            "capex_and_rep": float(capex),
            "grid_bill": 0.0,
            "tech_opex": 0.0,
            "feed_in_credit": 0.0,
            "net_annual_cost": float(capex),
            "discounted_cost": float(capex),
            "cumulative_nominal": cum_nominal,
            "cumulative_discounted": cum_discounted,
        }
    ]

    for y in range(1, horizon_years + 1):
        esc_factor = (1.0 + g) ** (y - 1)
        disc_factor = (1.0 + r) ** y
        grid_y = float(annual_grid_bill_year1) * esc_factor
        opex_y = float(annual_tech_opex_year1) * esc_factor
        credit_y = float(annual_feed_in_credit_year1) * esc_factor
        rep_y = float(replacement_cost) if (replacement_year > 0 and y == replacement_year) else 0.0

        net_cost_y = grid_y + opex_y - credit_y + rep_y
        disc_cost_y = net_cost_y / disc_factor
        npv_total += disc_cost_y
        cum_nominal += net_cost_y
        cum_discounted += disc_cost_y

        schedule.append(
            {
                "year": y,
                "capex_and_rep": rep_y,
                "grid_bill": grid_y,
                "tech_opex": opex_y,
                "feed_in_credit": credit_y,
                "net_annual_cost": net_cost_y,
                "discounted_cost": disc_cost_y,
                "cumulative_nominal": cum_nominal,
                "cumulative_discounted": cum_discounted,
            }
        )

    return float(npv_total), schedule


def build_residual_load_series_2025(
    base_load: LoadSeries2025,
    residual_power_kw: np.ndarray,
    force_edemsa_3win: Optional[bool] = None,
) -> LoadSeries2025:
    """
    Building Block 1: Converts any 35,040-step (or shorter) post-mitigation grid import power array
    P_Grid(t) into a standardized, validated `LoadSeries2025` object.
    """
    ref_index = base_load.timestamps if len(base_load.timestamps) == 35040 else create_reference_2025_timestamps()
    total_steps = 35040

    p_arr = np.asarray(residual_power_kw, dtype=float).flatten()
    p_arr = np.clip(np.nan_to_num(p_arr, nan=0.0), 0.0, None)

    if len(p_arr) != total_steps:
        if len(p_arr) == 0:
            p_arr = np.zeros(total_steps, dtype=float)
        else:
            reps = int(np.ceil(total_steps / len(p_arr)))
            p_arr = np.tile(p_arr, reps)[:total_steps]

    energy_kwh = p_arr * 0.25
    month_indices = base_load.month_indices if len(base_load.month_indices) == total_steps else ref_index.month.to_numpy(dtype=int)

    use_3win = force_edemsa_3win if force_edemsa_3win is not None else (base_load.tou_window_codes is not None)
    if use_3win:
        tou_codes = base_load.tou_window_codes if (base_load.tou_window_codes is not None and len(base_load.tou_window_codes) == total_steps) else classify_edemsa_tou_windows(ref_index)
        is_peak_tou = (tou_codes == 1)
    else:
        tou_codes = None
        is_peak_tou = base_load.is_peak_tou if len(base_load.is_peak_tou) == total_steps else classify_liander_tou_window(ref_index)

    return LoadSeries2025(
        timestamps=ref_index,
        power_kw=p_arr,
        energy_kwh=energy_kwh,
        month_indices=month_indices,
        is_peak_tou=is_peak_tou,
        total_steps=total_steps,
        step_hours=0.25,
        tou_window_codes=tou_codes,
    )


def evaluate_scenario_4pillar_bill_comparison(
    base_load: LoadSeries2025,
    residual_load: LoadSeries2025,
    base_config: StatusQuoConfig2025,
    alt_config: Optional[StatusQuoConfig2025] = None,
    period_choice: str = "Annual Statement 2025 (Full Year)",
) -> Dict[str, Any]:
    """
    Building Block 2: Evaluates both the Baseline (Status Quo) and the Mitigated/Alternative
    scenario through `calculate_status_quo_master_2025` and `build_invoice_positions`,
    returning line-by-line comparison structures and full-year financial totals.
    """
    cfg_after = alt_config if alt_config is not None else base_config

    res_base = calculate_status_quo_master_2025(load=base_load, config=base_config)
    res_after = calculate_status_quo_master_2025(load=residual_load, config=cfg_after)

    inv_base = build_invoice_positions(res_base, base_config, period_choice)
    inv_after = build_invoice_positions(res_after, cfg_after, period_choice)

    return {
        "res_base": res_base,
        "res_after": res_after,
        "inv_base": inv_base,
        "inv_after": inv_after,
        "base_config": base_config,
        "alt_config": cfg_after,
        "period_choice": period_choice,
    }


def render_shared_4pillar_bill_comparison_ui(
    comp_data: Dict[str, Any],
    baseline_col_title: str,
    scenario_col_title: str,
    site_name: str,
    assumptions_dict: Dict[str, List[Dict[str, str]]],
    physical_kpis: Dict[str, Any],
    key_prefix: str,
) -> None:
    """
    Renders the authoritative side-by-side 4-Pillar Electricity Bill Comparison Table,
    Grand Total Invoice Reconciliation, and PDF/CSV Export controls.
    """
    inv_base = comp_data["inv_base"]
    inv_after = comp_data["inv_after"]
    cfg_base: StatusQuoConfig2025 = comp_data["base_config"]
    cfg_after: StatusQuoConfig2025 = comp_data["alt_config"]
    curr = getattr(cfg_base, "currency_code", "EUR")
    vat_pct = cfg_base.levies.vat_rate_pct

    en_p1 = getattr(cfg_base, "enable_pillar_1_supplier", True) or getattr(cfg_after, "enable_pillar_1_supplier", True)
    en_p2 = getattr(cfg_base, "enable_pillar_2_dso", True) or getattr(cfg_after, "enable_pillar_2_dso", True)
    en_p3 = getattr(cfg_base, "enable_pillar_3_metering", True) or getattr(cfg_after, "enable_pillar_3_metering", True)
    en_p4 = getattr(cfg_base, "enable_pillar_4_taxes", True) or getattr(cfg_after, "enable_pillar_4_taxes", True)

    net_savings = inv_base["total_net"] - inv_after["total_net"]
    gross_savings = inv_base["total_gross"] - inv_after["total_gross"]
    savings_pct = (net_savings / inv_base["total_net"] * 100.0) if inv_base["total_net"] > 0 else 0.0

    # Top Executive Bill Delta KPI Strip
    k1, k2, k3, k4 = st.columns(4)
    k1.metric(
        f"Baseline Bill (Net)",
        f"{curr} {inv_base['total_net']:,.2f}",
        f"Gross: {curr} {inv_base['total_gross']:,.2f}",
        delta_color="off",
    )
    k2.metric(
        f"{scenario_col_title} Bill (Net)",
        f"{curr} {inv_after['total_net']:,.2f}",
        f"Gross: {curr} {inv_after['total_gross']:,.2f}",
        delta_color="off",
    )
    k3.metric(
        "Net Electricity Bill Savings",
        f"{curr} {net_savings:,.2f}",
        f"-{savings_pct:.1f}% Cost Reduction" if net_savings >= 0 else f"+{abs(savings_pct):.1f}% Cost Increase",
        delta_color="normal" if net_savings >= 0 else "inverse",
    )
    k4.metric(
        "Gross Bill Savings (Incl. VAT)",
        f"{curr} {gross_savings:,.2f}",
        f"Billed Peak: {inv_base.get('billed_peak_kw', inv_base['p_max']):,.1f} -> {inv_after.get('billed_peak_kw', inv_after['p_max']):,.1f} kW",
        delta_color="normal" if gross_savings >= 0 else "inverse",
    )

    st.markdown(f"#### :material/compare_arrows: Side-by-Side 4-Pillar Invoice Statement ({comp_data['period_choice']})")

    blocks_meta = [
        ("Pillar 1: Energy Supply (Retailer)", "block_a", "subtotal_a", en_p1, "#38bdf8"),
        ("Pillar 2: Grid Network (DSO / Utility)", "block_b", "subtotal_b", en_p2, "#fbbf24"),
        ("Pillar 3: Metering & Telemetry (Meetbedrijf)", "block_c", "subtotal_c", en_p3, "#a855f7"),
        ("Pillar 4: Statutory Taxes & Levies", "block_d", "subtotal_d", en_p4, "#f87171"),
    ]

    pdf_comparison_rows: List[Dict[str, Any]] = []
    html_rows = ""

    for b_title, b_key, sub_key, is_en, b_color in blocks_meta:
        tag_html = "" if is_en else " <span style='color:#fbbf24;font-size:0.75rem;'>[BYPASSED IN SINGLE-UTILITY MODE]</span>"
        html_rows += (
            f"<tr style='background:#1e293b; border-top:2px solid {b_color};'>"
            f"<td colspan='6' style='padding:8px 10px; color:#f8fafc; font-weight:700; font-size:0.84rem;'>{b_title}{tag_html}</td>"
            f"</tr>"
        )
        pdf_comparison_rows.append(
            {"component": b_title, "baseline_str": "", "bess_str": "", "delta_str": "", "is_header": True}
        )

        pos_base_list = inv_base[b_key]
        pos_after_list = inv_after[b_key]
        max_len = max(len(pos_base_list), len(pos_after_list))

        for i in range(max_len):
            pb = pos_base_list[i] if i < len(pos_base_list) else pos_after_list[i]
            pa = pos_after_list[i] if i < len(pos_after_list) else pos_base_list[i]

            amt_b = 0.0 if not is_en else float(pb["amount_net"])
            amt_a = 0.0 if not is_en else float(pa["amount_net"])
            delta_v = amt_a - amt_b

            qb_disp = pb.get("quantity_display", f"{pb['quantity']:,.1f}")
            qa_disp = pa.get("quantity_display", f"{pa['quantity']:,.1f}")
            unit_s = pb["unit"]

            if delta_v < -0.01:
                d_color = "#4ade80"
                d_str = f"-{curr} {abs(delta_v):,.2f}"
            elif delta_v > 0.01:
                d_color = "#f87171"
                d_str = f"+{curr} {delta_v:,.2f}"
            else:
                d_color = "#94a3b8"
                d_str = f"{curr} 0.00"

            row_op = "1.0" if is_en else "0.45"
            html_rows += (
                f"<tr style='border-bottom:1px solid #1e293b; opacity:{row_op}; font-size:0.80rem;'>"
                f"<td style='padding:6px 8px; color:#94a3b8; font-weight:600; white-space:nowrap;'>{pb['pos']}</td>"
                f"<td style='padding:6px 8px; color:#e2e8f0;'>{pb['description']}</td>"
                f"<td style='padding:6px 8px; text-align:right; color:#cbd5e1; font-family:monospace; white-space:nowrap;'>{qb_disp} -> {qa_disp} {unit_s}</td>"
                f"<td style='padding:6px 8px; text-align:right; color:#f8fafc; font-family:monospace; white-space:nowrap;'>{curr} {amt_b:,.2f}</td>"
                f"<td style='padding:6px 8px; text-align:right; color:#f8fafc; font-family:monospace; white-space:nowrap;'>{curr} {amt_a:,.2f}</td>"
                f"<td style='padding:6px 8px; text-align:right; color:{d_color}; font-weight:700; font-family:monospace; white-space:nowrap;'>{d_str}</td>"
                f"</tr>"
            )
            pdf_comparison_rows.append(
                {
                    "component": f"{pb['pos']} {pb['description']}",
                    "baseline_str": f"{curr} {amt_b:,.2f}",
                    "bess_str": f"{curr} {amt_a:,.2f}",
                    "delta_str": d_str,
                    "is_summary": False,
                }
            )

        sub_b = 0.0 if not is_en else float(inv_base[sub_key])
        sub_a = 0.0 if not is_en else float(inv_after[sub_key])
        sub_d = sub_a - sub_b
        sd_str = f"-{curr} {abs(sub_d):,.2f}" if sub_d < -0.01 else (f"+{curr} {sub_d:,.2f}" if sub_d > 0.01 else f"{curr} 0.00")
        sd_col = "#4ade80" if sub_d < -0.01 else ("#f87171" if sub_d > 0.01 else "#cbd5e1")

        html_rows += (
            f"<tr style='background:#0f172a; border-bottom:2px solid #334155; font-weight:700; font-size:0.82rem;'>"
            f"<td colspan='3' style='padding:7px 10px; text-align:right; color:#cbd5e1;'>Subtotal ({b_title}):</td>"
            f"<td style='padding:7px 8px; text-align:right; color:#f8fafc; font-family:monospace; white-space:nowrap;'>{curr} {sub_b:,.2f}</td>"
            f"<td style='padding:7px 8px; text-align:right; color:#f8fafc; font-family:monospace; white-space:nowrap;'>{curr} {sub_a:,.2f}</td>"
            f"<td style='padding:7px 8px; text-align:right; color:{sd_col}; font-family:monospace; white-space:nowrap;'>{sd_str}</td>"
            f"</tr>"
        )
        pdf_comparison_rows.append(
            {
                "component": f"Subtotal ({b_title})",
                "baseline_str": f"{curr} {sub_b:,.2f}",
                "bess_str": f"{curr} {sub_a:,.2f}",
                "delta_str": sd_str,
                "is_summary": True,
            }
        )

    # Grand totals
    tot_net_b = float(inv_base["total_net"])
    tot_net_a = float(inv_after["total_net"])
    tot_net_d = tot_net_a - tot_net_b

    vat_b = float(inv_base["vat_amount"])
    vat_a = float(inv_after["vat_amount"])
    vat_d = vat_a - vat_b

    gr_b = float(inv_base["total_gross"])
    gr_a = float(inv_after["total_gross"])
    gr_d = gr_a - gr_b

    for lbl, vb, va, vd, is_gr in [
        ("TOTAL NET INVOICE AMOUNT (EXCL. VAT)", tot_net_b, tot_net_a, tot_net_d, False),
        (f"Value Added Tax ({vat_pct:.1f}% VAT)", vat_b, vat_a, vat_d, False),
        ("TOTAL GROSS AMOUNT DUE (INCL. VAT)", gr_b, gr_a, gr_d, True),
    ]:
        d_s = f"-{curr} {abs(vd):,.2f}" if vd < -0.01 else (f"+{curr} {vd:,.2f}" if vd > 0.01 else f"{curr} 0.00")
        d_c = "#4ade80" if vd < -0.01 else ("#f87171" if vd > 0.01 else "#f8fafc")
        bg_c = "rgba(16, 185, 129, 0.16)" if is_gr else "rgba(56, 189, 248, 0.12)"
        html_rows += (
            f"<tr style='background:{bg_c}; border-top:1px solid #475569; font-weight:800; font-size:0.86rem;'>"
            f"<td colspan='3' style='padding:9px 10px; color:#f8fafc;'>{lbl}</td>"
            f"<td style='padding:9px 8px; text-align:right; color:#f8fafc; font-family:monospace; white-space:nowrap;'>{curr} {vb:,.2f}</td>"
            f"<td style='padding:9px 8px; text-align:right; color:#f8fafc; font-family:monospace; white-space:nowrap;'>{curr} {va:,.2f}</td>"
            f"<td style='padding:9px 8px; text-align:right; color:{d_c}; font-family:monospace; white-space:nowrap;'>{d_s}</td>"
            f"</tr>"
        )
        pdf_comparison_rows.append(
            {
                "component": lbl,
                "baseline_str": f"{curr} {vb:,.2f}",
                "bess_str": f"{curr} {va:,.2f}",
                "delta_str": d_s,
                "is_summary": True,
            }
        )

    comp_table_html = (
        "<div style='background:#0f172a; border:1px solid #334155; border-radius:8px; overflow-x:auto; margin-bottom:14px;'>"
        "<table style='width:100%; border-collapse:collapse; font-family:sans-serif;'>"
        "<thead><tr style='background:#020617; color:#94a3b8; border-bottom:2px solid #334155; font-size:0.78rem;'>"
        "<th style='padding:8px; text-align:left;'>Pos.</th>"
        "<th style='padding:8px; text-align:left;'>Tariff Component</th>"
        f"<th style='padding:8px; text-align:right;'>Billing Quantity ({baseline_col_title} -> {scenario_col_title})</th>"
        f"<th style='padding:8px; text-align:right;'>{baseline_col_title} ({curr})</th>"
        f"<th style='padding:8px; text-align:right;'>{scenario_col_title} ({curr})</th>"
        "<th style='padding:8px; text-align:right;'>Net Delta / Savings</th>"
        "</tr></thead>"
        f"<tbody>{html_rows}</tbody></table></div>"
    )
    st.markdown(comp_table_html, unsafe_allow_html=True)

    # Export Controls (PDF & CSV)
    exp_c1, exp_c2 = st.columns(2)
    with exp_c1:
        pdf_bytes = generate_bess_comparison_report_pdf(
            site_name=site_name,
            currency_code=curr,
            assumptions_dict=assumptions_dict,
            physical_kpis=physical_kpis,
            comparison_rows=pdf_comparison_rows,
        )
        st.download_button(
            label=":material/picture_as_pdf: Download Side-by-Side 4-Pillar Comparison Report (.pdf)",
            data=pdf_bytes,
            file_name=f"4pillar_comparison_{key_prefix}_{comp_data['period_choice'][:7].replace(' ', '_')}.pdf",
            mime="application/pdf",
            key=f"{key_prefix}_dl_comp_pdf",
            use_container_width=True,
            type="primary",
        )
    with exp_c2:
        df_export = pd.DataFrame(pdf_comparison_rows)
        st.download_button(
            label=":material/download: Export Itemized Comparison Table (.csv)",
            data=df_export.to_csv(index=False).encode("utf-8"),
            file_name=f"4pillar_comparison_{key_prefix}.csv",
            mime="text/csv",
            key=f"{key_prefix}_dl_comp_csv",
            use_container_width=True,
        )


def render_scenario_evaluation_output_card(
    output: ScenarioEvaluationOutput,
    key_prefix: str,
) -> None:
    """
    Renders Building Block 3: Standardized Scenario Evaluation Output summary card
    and `.json` export button so the scenario can be saved or combined into a master dashboard.
    """
    curr = output.currency_code
    st.markdown("---")
    st.markdown(
        f"#### :material/inventory: Standardized Scenario Output Container (`ScenarioEvaluationOutput` — `{output.scenario_id}`)"
    )
    st.caption(
        "This standardized data contract is shared across all 6 scenario sandboxes so every scenario can be tested "
        "independently today and seamlessly combined into a unified multi-scenario comparison later."
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "Grid Peak (Before -> After)",
        f"{output.peak_after_kw:,.1f} kW",
        f"-{output.peak_shaved_kw:,.1f} kW (-{output.peak_shaved_pct:.1f}%)",
        delta_color="normal" if output.peak_shaved_kw >= 0 else "inverse",
    )
    c2.metric(
        "Turnkey CAPEX & Annual Tech OPEX",
        f"{curr} {output.capex_total:,.0f}",
        f"Tech OPEX: {curr} {output.annual_tech_opex:,.0f}/yr",
        delta_color="off",
    )
    c3.metric(
        "Annual Net Savings (vs. Status Quo)",
        f"{curr} {output.annual_net_savings:,.0f}/yr",
        f"Payback: {output.simple_payback_years:.1f} yrs" if output.simple_payback_years < 99.0 else "Payback: N/A",
        delta_color="normal" if output.annual_net_savings >= 0 else "inverse",
    )
    c4.metric(
        "15-Year Net NPV Benefit",
        f"{curr} {output.npv_15y_net_benefit:,.0f}",
        f"15Y TCO: {curr} {output.npv_15y_tco_after:,.0f}",
        delta_color="normal" if output.npv_15y_net_benefit >= 0 else "inverse",
    )

    # Also store in session_state registry for cross-sandbox inspection if run in same session
    if "sandbox_scenario_outputs" not in st.session_state:
        st.session_state["sandbox_scenario_outputs"] = {}
    st.session_state["sandbox_scenario_outputs"][output.scenario_id] = output.to_dict()

    with st.expander(":material/code: Inspect Standardized `ScenarioEvaluationOutput` JSON & Export", expanded=False):
        json_str = output.to_json(indent=2)
        st.download_button(
            label=f":material/download: Export Standardized Scenario Result ({output.scenario_id}.json)",
            data=json_str.encode("utf-8"),
            file_name=f"scenario_output_{output.scenario_id}.json",
            mime="application/json",
            key=f"{key_prefix}_dl_scen_json",
            use_container_width=True,
        )
        st.code(json_str, language="json")

