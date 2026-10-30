"""
========================================================================================
BESS Sandbox - Tab 3: Baseline vs. BESS Bill & Profile Comparison
(ui_sandbox/BESS_sandbox/view_bill_comparison.py)
========================================================================================

Description:
------------
End-to-End Baseline (Without Battery) vs. Peak-Shaving Scenario (With Battery) comparison:
  1. Section 1: Effect on Grid Demand Profile & Remaining Peaks
     - Before vs. After Peak-Shaving KPI Comparison Strip:
       * Facility Peak Demand (Before BESS) -> Grid Import Peak (With BESS)
       * Overload Hours & Remaining Peak Deficit (kW / kWh)
       * Grid Energy Import (kWh) + BESS Discharged Throughput (kWh) + RTE Conversion Loss (kWh)
     - Interactive Synchronized 2-in-1 Plotly Dispatch & SoC Chart
  2. Section 2: Effect on Resulting Electricity Costs (Side-by-Side 4-Pillar Electricity Bill)
     - Evaluates the 4-Pillar Electricity Bill Engine (`calculate_status_quo_master_2025` &
       `build_invoice_positions`) on `P_Load_kW` (Baseline) vs. `P_Grid_kW` (With BESS).
     - Supports Peak Billing Month (Single Month Invoice View) vs. Full Year 2025 (12-Month Aggregation).
     - High-contrast Side-by-Side Itemized Electricity Bill Comparison Table (`Pos. & Cost Component |
       Baseline Bill (Without BESS) | Peak-Shaving Bill (With BESS) | Cost Delta / Savings (CURR & %)`).
     - PDF Export Button ("Download Baseline vs. BESS Comparison Report (PDF)") + CSV Export.
========================================================================================
"""

import os
import sys
from typing import Dict, Any, List, Tuple, Optional
import numpy as np
import pandas as pd
import streamlit as st

# Path bootstrapping
CURRENT_DIR = os.path.abspath(os.path.dirname(__file__))
UI_SANDBOX_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
CURRENT_MODEL_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
WORKSPACE_DIR = os.path.abspath(os.path.join(CURRENT_MODEL_DIR, ".."))
for p in [CURRENT_DIR, UI_SANDBOX_DIR, CURRENT_MODEL_DIR, WORKSPACE_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from current_model.core.bess_engine import BESSSimulationResult
except ImportError:
    from core.bess_engine import BESSSimulationResult

from ui_sandbox.BESS_sandbox import baseline_presets as presets
from ui_sandbox.BESS_sandbox.sandbox_charts import (
    create_synced_dispatch_soc_figure,
    compute_focus_range,
)

try:
    from ui_sandbox.Currentsituation_sandbox.engine.config_and_models import (
        StatusQuoConfig2025,
        LoadSeries2025,
        StatusQuoAnnualResult,
    )
    from ui_sandbox.Currentsituation_sandbox.engine.consumption_pipeline import (
        normalize_load_profile_2025,
        classify_edemsa_tou_windows,
    )
    from ui_sandbox.Currentsituation_sandbox.engine.status_quo_master import (
        calculate_status_quo_master_2025,
    )
    from ui_sandbox.Currentsituation_sandbox.engine.tariff_defaults_2025 import (
        get_default_status_quo_config_2025,
        get_rotterdam_stedin_wko_config_2025,
        get_edemsa_salentein_config_2025,
        get_dso_tariff_from_catalog_2025,
    )
    from ui_sandbox.Currentsituation_sandbox.contract.tab_invoice_experimental import (
        build_invoice_positions,
    )
    from ui_sandbox.Currentsituation_sandbox.contract.invoice_pdf_exporter import (
        generate_bess_comparison_report_pdf,
    )
except ImportError:
    from current_model.ui_sandbox.Currentsituation_sandbox.engine.config_and_models import (
        StatusQuoConfig2025,
        LoadSeries2025,
        StatusQuoAnnualResult,
    )
    from current_model.ui_sandbox.Currentsituation_sandbox.engine.consumption_pipeline import (
        normalize_load_profile_2025,
        classify_edemsa_tou_windows,
    )
    from current_model.ui_sandbox.Currentsituation_sandbox.engine.status_quo_master import (
        calculate_status_quo_master_2025,
    )
    from current_model.ui_sandbox.Currentsituation_sandbox.engine.tariff_defaults_2025 import (
        get_default_status_quo_config_2025,
        get_rotterdam_stedin_wko_config_2025,
        get_edemsa_salentein_config_2025,
        get_dso_tariff_from_catalog_2025,
    )
    from current_model.ui_sandbox.Currentsituation_sandbox.contract.tab_invoice_experimental import (
        build_invoice_positions,
    )
    from current_model.ui_sandbox.Currentsituation_sandbox.contract.invoice_pdf_exporter import (
        generate_bess_comparison_report_pdf,
    )


def build_4pillar_configs_for_preset(
    preset: presets.BaselinePreset,
    active_limit_kw: float
) -> Tuple[StatusQuoConfig2025, StatusQuoConfig2025]:
    """
    Constructs the Baseline and With-BESS 4-Pillar `StatusQuoConfig2025` objects
    matching the active BESS preset (`Rotterdam Stedin`, `EDEMSA T2 RMT`, `Liander`, `Enexis`, or Custom).
    """
    key_low = preset.key.lower()
    if "edemsa" in key_low or "salentein" in key_low:
        cfg_base = get_edemsa_salentein_config_2025(contracted_capacity_kw=active_limit_kw)
        cfg_bess = get_edemsa_salentein_config_2025(contracted_capacity_kw=active_limit_kw)
        return cfg_base, cfg_bess

    if "paula" in key_low or "rotterdam" in key_low or "wko" in key_low:
        cfg_base = get_rotterdam_stedin_wko_config_2025(contracted_capacity_kw=active_limit_kw)
        cfg_bess = get_rotterdam_stedin_wko_config_2025(contracted_capacity_kw=active_limit_kw)
        cfg_base.dso.enable_excess_capacity_penalty = True
        cfg_bess.dso.enable_excess_capacity_penalty = True
        return cfg_base, cfg_bess

    if "liander" in key_low:
        # Case 1: Baseline AC5a (350 kW) vs With-BESS AC4b (active_limit_kw = 147 kW)
        cfg_base = get_default_status_quo_config_2025(contracted_capacity_kw=350.0)
        cfg_base.dso = get_dso_tariff_from_catalog_2025(
            "Liander Netbeheer",
            "AC5a MS-Trafo (160 t/m 1,000 kW)",
            contracted_capacity_kw=350.0
        )
        cfg_bess = get_default_status_quo_config_2025(contracted_capacity_kw=active_limit_kw)
        cfg_bess.dso = get_dso_tariff_from_catalog_2025(
            "Liander Netbeheer",
            "AC4b LS-Trafo (80 t/m 160 kW)",
            contracted_capacity_kw=active_limit_kw
        )
        return cfg_base, cfg_bess

    # Default / Case 2 Enexis MS-D or Custom
    base_gtv = max(active_limit_kw, float(preset.contract_baseline.contracted_capacity_kw))
    cfg_base = get_default_status_quo_config_2025(contracted_capacity_kw=base_gtv)
    cfg_base.dso.enable_excess_capacity_penalty = True
    cfg_bess = get_default_status_quo_config_2025(contracted_capacity_kw=active_limit_kw)
    cfg_bess.dso.enable_excess_capacity_penalty = True
    return cfg_base, cfg_bess


def evaluate_baseline_vs_bess_4pillar_bills(
    sim_result: BESSSimulationResult,
    preset: presets.BaselinePreset,
    active_limit_kw: float,
    period_choice: str = "Peak Billing Month (Single Month Invoice View)"
) -> Dict[str, Any]:
    """
    Evaluates the 4-Pillar Electricity Bill Engine on both `P_Load_kW` (Baseline)
    and `P_Grid_kW` (With BESS) and builds side-by-side comparison line items.
    """
    df_ts = sim_result.df_timeseries.copy()
    p_load = df_ts["P_Load_kW"].to_numpy(dtype=float)
    p_grid = df_ts["P_Grid_kW"].to_numpy(dtype=float)
    p_dis = df_ts["P_BESS_Discharge_kW"].to_numpy(dtype=float) if "P_BESS_Discharge_kW" in df_ts.columns else np.zeros_like(p_load)
    p_chg = df_ts["P_BESS_Charge_kW"].to_numpy(dtype=float) if "P_BESS_Charge_kW" in df_ts.columns else np.zeros_like(p_load)
    p_unmet = df_ts["P_Overload_Unmet_kW"].to_numpy(dtype=float) if "P_Overload_Unmet_kW" in df_ts.columns else np.maximum(0.0, p_grid - active_limit_kw)
    soc_pct = df_ts["SoC_pct"].to_numpy(dtype=float) if "SoC_pct" in df_ts.columns else np.zeros_like(p_load)

    n_steps = len(df_ts)
    dt_h = 0.25

    # Physical metrics over the measured simulation dataset
    peak_before_kw = float(np.max(p_load)) if n_steps > 0 else 0.0
    peak_after_kw = float(np.max(p_grid)) if n_steps > 0 else 0.0
    peak_shaved_kw = max(0.0, peak_before_kw - peak_after_kw)
    peak_shaved_pct = (peak_shaved_kw / peak_before_kw * 100.0) if peak_before_kw > 0 else 0.0

    overload_before_kw = max(0.0, peak_before_kw - active_limit_kw)
    overload_after_kw = max(0.0, peak_after_kw - active_limit_kw)
    overload_hours_before = float(np.sum(p_load > active_limit_kw) * dt_h)
    overload_hours_after = float(np.sum(p_grid > active_limit_kw + 1e-4) * dt_h)
    overload_energy_before_kwh = float(np.sum(np.maximum(0.0, p_load - active_limit_kw)) * dt_h)
    overload_energy_after_kwh = float(np.sum(p_unmet) * dt_h)

    energy_before_kwh = float(np.sum(p_load) * dt_h)
    energy_after_kwh = float(np.sum(p_grid) * dt_h)
    bess_discharged_kwh = float(np.sum(p_dis) * dt_h)
    bess_charged_kwh = float(np.sum(p_chg) * dt_h)
    rte_loss_kwh = max(0.0, energy_after_kwh - energy_before_kwh)

    # Normalize both series to 2025 for the 4-Pillar Master Engine
    df_base_raw = pd.DataFrame({
        "timestamp": df_ts["timestamp"] if "timestamp" in df_ts.columns else pd.date_range("2025-01-01", periods=n_steps, freq="15min"),
        "Total_Demand_kW": p_load
    })
    df_bess_raw = pd.DataFrame({
        "timestamp": df_ts["timestamp"] if "timestamp" in df_ts.columns else pd.date_range("2025-01-01", periods=n_steps, freq="15min"),
        "Total_Demand_kW": p_grid
    })

    load_base_2025, _ = normalize_load_profile_2025(df_base_raw, power_col="Total_Demand_kW", time_col="timestamp")
    load_bess_2025, _ = normalize_load_profile_2025(df_bess_raw, power_col="Total_Demand_kW", time_col="timestamp")

    cfg_base, cfg_bess = build_4pillar_configs_for_preset(preset, active_limit_kw=active_limit_kw)
    if getattr(cfg_base.dso, "enable_three_window_tou", False):
        tou_codes_base = classify_edemsa_tou_windows(load_base_2025.timestamps)
        load_base_2025.tou_window_codes = tou_codes_base
        load_base_2025.is_peak_tou = (tou_codes_base == 1)
        tou_codes_bess = classify_edemsa_tou_windows(load_bess_2025.timestamps)
        load_bess_2025.tou_window_codes = tou_codes_bess
        load_bess_2025.is_peak_tou = (tou_codes_bess == 1)

    res_base = calculate_status_quo_master_2025(load=load_base_2025, config=cfg_base)
    res_bess = calculate_status_quo_master_2025(load=load_bess_2025, config=cfg_bess)

    # Determine target_period for build_invoice_positions
    if "Full Year" in period_choice or "Annual" in period_choice:
        target_period_arg = "Annual Statement 2025 (Full Year)"
    else:
        # Select the month with the highest peak demand so peak-shaving impact is faithfully represented
        peak_m_idx = max(range(len(res_base.monthly_records)), key=lambda i: res_base.monthly_records[i].consumption.peak_demand_kw)
        m_rec = res_base.monthly_records[peak_m_idx]
        target_period_arg = f"{m_rec.month_name} 2025"

    inv_base = build_invoice_positions(
        result=res_base,
        active_config=cfg_base,
        target_period=target_period_arg
    )
    inv_bess = build_invoice_positions(
        result=res_bess,
        active_config=cfg_bess,
        target_period=target_period_arg
    )

    curr = cfg_base.currency_code
    en_p1 = getattr(cfg_base, "enable_pillar_1_supplier", True)
    en_p2 = getattr(cfg_base, "enable_pillar_2_dso", True)
    en_p3 = getattr(cfg_base, "enable_pillar_3_metering", True)
    en_p4 = getattr(cfg_base, "enable_pillar_4_taxes", True)

    block_defs = [
        ("A. Energy Supply (Retailer)", "block_a", "subtotal_a", en_p1),
        ("B. Grid Network (DSO)", "block_b", "subtotal_b", en_p2),
        ("C. Metering & Telemetry", "block_c", "subtotal_c", en_p3),
        ("D. Statutory Taxes & Levies", "block_d", "subtotal_d", en_p4),
    ]

    comparison_rows: List[Dict[str, Any]] = []
    pdf_comparison_rows: List[Dict[str, Any]] = []

    for blk_label, blk_key, sub_key, is_en in block_defs:
        pos_b_list = inv_base[blk_key]
        pos_w_list = inv_bess[blk_key]
        b_by_code = {p["pos"]: p for p in pos_b_list}
        w_by_code = {p["pos"]: p for p in pos_w_list}
        codes = list(dict.fromkeys([p["pos"] for p in pos_b_list] + [p["pos"] for p in pos_w_list]))

        byp_tag = "" if is_en else " [BYPASSED]"
        pdf_comparison_rows.append({
            "component": f"Pillar {blk_label}{byp_tag}",
            "baseline_str": "",
            "bess_str": "",
            "delta_str": "",
            "is_header": True,
            "is_summary": False,
        })

        for code in codes:
            rb = b_by_code.get(code)
            rw = w_by_code.get(code)
            ref = rb or rw
            val_b = float(rb["amount_net"]) if rb else 0.0
            val_w = float(rw["amount_net"]) if rw else 0.0
            delta = val_w - val_b
            pct = (delta / val_b * 100.0) if abs(val_b) > 1e-6 else 0.0
            row_dict = {
                "pos": code,
                "block": blk_label,
                "description": ref["description"],
                "qty_base": float(rb["quantity"]) if rb else 0.0,
                "qty_bess": float(rw["quantity"]) if rw else 0.0,
                "unit": ref["unit"],
                "rate": float(ref["rate"]),
                "base_amount": round(val_b, 2),
                "bess_amount": round(val_w, 2),
                "delta_amount": round(delta, 2),
                "delta_pct": round(pct, 1),
                "is_enabled": is_en,
            }
            comparison_rows.append(row_dict)
            pdf_comparison_rows.append({
                "component": f"{code} {ref['description']}",
                "baseline_str": f"{curr} {val_b:,.2f}",
                "bess_str": f"{curr} {val_w:,.2f}",
                "delta_str": f"{delta:+,.2f} ({pct:+.1f}%)" if abs(delta) > 0.005 else "0.00",
                "is_header": False,
                "is_summary": False,
            })

        sub_b = float(inv_base[sub_key])
        sub_w = float(inv_bess[sub_key])
        sub_d = sub_w - sub_b
        sub_pct = (sub_d / sub_b * 100.0) if abs(sub_b) > 1e-6 else 0.0
        pdf_comparison_rows.append({
            "component": f"= Subtotal {blk_label}",
            "baseline_str": f"{curr} {sub_b:,.2f}",
            "bess_str": f"{curr} {sub_w:,.2f}",
            "delta_str": f"{sub_d:+,.2f} ({sub_pct:+.1f}%)" if abs(sub_d) > 0.005 else "0.00",
            "is_header": False,
            "is_summary": True,
        })

    # Grand total rows for PDF
    net_b, net_w = float(inv_base["total_net"]), float(inv_bess["total_net"])
    net_d = net_w - net_b
    net_pct = (net_d / net_b * 100.0) if abs(net_b) > 1e-6 else 0.0

    vat_b, vat_w = float(inv_base["vat_amount"]), float(inv_bess["vat_amount"])
    vat_d = vat_w - vat_b
    vat_pct_rate = cfg_base.levies.vat_rate_pct

    grs_b, grs_w = float(inv_base["total_gross"]), float(inv_bess["total_gross"])
    grs_d = grs_w - grs_b
    grs_pct = (grs_d / grs_b * 100.0) if abs(grs_b) > 1e-6 else 0.0

    bl_b, bl_w = float(inv_base["effective_rate_net"]), float(inv_bess["effective_rate_net"])
    bl_d = bl_w - bl_b

    pdf_comparison_rows.extend([
        {
            "component": "= TOTAL NET ELECTRICITY BILL (1 + 2 + 3 + 4)",
            "baseline_str": f"{curr} {net_b:,.2f}",
            "bess_str": f"{curr} {net_w:,.2f}",
            "delta_str": f"{net_d:+,.2f} ({net_pct:+.1f}%)",
            "is_header": False,
            "is_summary": True,
        },
        {
            "component": f"+ Value Added Tax ({vat_pct_rate:.1f}% VAT)",
            "baseline_str": f"{curr} {vat_b:,.2f}",
            "bess_str": f"{curr} {vat_w:,.2f}",
            "delta_str": f"{vat_d:+,.2f}",
            "is_header": False,
            "is_summary": False,
        },
        {
            "component": "= TOTAL GROSS ELECTRICITY BILL (INCL. VAT)",
            "baseline_str": f"{curr} {grs_b:,.2f}",
            "bess_str": f"{curr} {grs_w:,.2f}",
            "delta_str": f"{grs_d:+,.2f} ({grs_pct:+.1f}%)",
            "is_header": False,
            "is_summary": True,
        },
        {
            "component": f"Effective Blended Rate (Net {curr}/kWh)",
            "baseline_str": f"{curr} {bl_b:.4f}/kWh",
            "bess_str": f"{curr} {bl_w:.4f}/kWh",
            "delta_str": f"{bl_d:+.4f}/kWh",
            "is_header": False,
            "is_summary": False,
        },
    ])

    return {
        "currency": curr,
        "period_label": inv_base["period_label"],
        "cfg_base": cfg_base,
        "cfg_bess": cfg_bess,
        "res_base": res_base,
        "res_bess": res_bess,
        "inv_base": inv_base,
        "inv_bess": inv_bess,
        "comparison_rows": comparison_rows,
        "pdf_comparison_rows": pdf_comparison_rows,
        "physical": {
            "n_steps": n_steps,
            "days": n_steps * dt_h / 24.0,
            "grid_limit_kw": active_limit_kw,
            "active_limit_kw": active_limit_kw,
            "peak_before_kw": peak_before_kw,
            "peak_after_kw": peak_after_kw,
            "peak_shaved_kw": peak_shaved_kw,
            "peak_shaved_pct": peak_shaved_pct,
            "overload_before_kw": overload_before_kw,
            "overload_after_kw": overload_after_kw,
            "overload_hrs_before": overload_hours_before,
            "overload_hrs_after": overload_hours_after,
            "overload_hours_before": overload_hours_before,
            "overload_hours_after": overload_hours_after,
            "overload_energy_before_kwh": overload_energy_before_kwh,
            "overload_energy_after_kwh": overload_energy_after_kwh,
            "remaining_deficit_kwh": overload_energy_after_kwh,
            "load_kwh": energy_before_kwh,
            "grid_import_kwh": energy_after_kwh,
            "energy_before_kwh": energy_before_kwh,
            "energy_after_kwh": energy_after_kwh,
            "discharge_kwh": bess_discharged_kwh,
            "bess_discharged_kwh": bess_discharged_kwh,
            "bess_charged_kwh": bess_charged_kwh,
            "rte_loss_kwh": rte_loss_kwh,
            "soc_min_obs_pct": float(np.min(soc_pct)) if len(soc_pct) > 0 else 0.0,
            "soc_max_obs_pct": float(np.max(soc_pct)) if len(soc_pct) > 0 else 0.0,
        },
    }


def _render_side_by_side_bill_html(comp_data: Dict[str, Any]) -> str:
    """Renders the high-contrast HTML Side-by-Side 4-Pillar Electricity Bill Comparison Table."""
    curr = comp_data["currency"]
    rows = comp_data["comparison_rows"]
    ib = comp_data["inv_base"]
    iw = comp_data["inv_bess"]
    vat_pct_rate = comp_data["cfg_base"].levies.vat_rate_pct

    blocks = [
        ("A. Energy Supply (Retailer)", "#38bdf8", "1. Energy Supply (Retailer)", ib["subtotal_a"], iw["subtotal_a"]),
        ("B. Grid Network (DSO)", "#f59e0b", "2. Grid Network (DSO)", ib["subtotal_b"], iw["subtotal_b"]),
        ("C. Metering & Telemetry", "#8b5cf6", "3. Metering & Telemetry", ib["subtotal_c"], iw["subtotal_c"]),
        ("D. Statutory Taxes & Levies", "#10b981", "4. Statutory Taxes & Levies", ib["subtotal_d"], iw["subtotal_d"]),
    ]

    html_parts: List[str] = [
        '<div style="background-color: #0b1329; border: 1.5px solid #334155; border-radius: 10px; padding: 16px; margin-bottom: 16px;">',
        f'<div style="font-size: 0.80rem; font-weight: 700; color: #38bdf8; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 10px;">'
        f'Side-by-Side 4-Pillar Electricity Bill Comparison ({comp_data["period_label"]} | Currency: {curr})'
        f'</div>',
        '<table style="width: 100%; border-collapse: collapse; font-family: sans-serif; color: #f8fafc;">',
        '<thead>',
        '<tr style="background-color: #1e293b; border-bottom: 2px solid #475569; text-align: left;">',
        '<th style="padding: 9px 10px; font-size: 0.76rem; color: #cbd5e1; width: 7%;">Pos.</th>',
        '<th style="padding: 9px 10px; font-size: 0.76rem; color: #cbd5e1; width: 39%;">Cost Component & Tariff Line Item</th>',
        f'<th style="padding: 9px 10px; font-size: 0.76rem; color: #cbd5e1; text-align: right; width: 18%;">Baseline Bill ({curr})<br><span style="font-size:0.68rem; color:#94a3b8;">Without BESS</span></th>',
        f'<th style="padding: 9px 10px; font-size: 0.76rem; color: #cbd5e1; text-align: right; width: 18%;">Peak-Shaving Bill ({curr})<br><span style="font-size:0.68rem; color:#38bdf8;">With BESS</span></th>',
        f'<th style="padding: 9px 10px; font-size: 0.76rem; color: #cbd5e1; text-align: right; width: 18%;">Cost Delta / Savings<br><span style="font-size:0.68rem; color:#34d399;">({curr} &amp; %)</span></th>',
        '</tr>',
        '</thead>',
        '<tbody>',
    ]

    for blk_key, accent_hex, blk_title, sub_b, sub_w in blocks:
        blk_rows = [r for r in rows if r["block"] == blk_key]
        is_en = blk_rows[0]["is_enabled"] if blk_rows else True
        dim_style = "" if is_en else "opacity: 0.42; filter: grayscale(100%);"
        byp_tag = "" if is_en else " [BYPASSED / BUNDLED]"

        html_parts.append(
            f'<tr style="background-color: #0f172a; border-top: 2px solid #334155; {dim_style}">'
            f'<td colspan="5" style="padding: 8px 10px; font-size: 0.82rem; font-weight: 700; color: {accent_hex}; border-left: 4px solid {accent_hex};">'
            f'Pillar {blk_title}{byp_tag}'
            f'</td></tr>'
        )

        for idx, r in enumerate(blk_rows):
            bg = "#1e293b" if idx % 2 == 0 else "#0f172a"
            vb = r["base_amount"]
            vw = r["bess_amount"]
            dlt = r["delta_amount"]
            pct = r["delta_pct"]
            if dlt < -0.005:
                d_col = "#34d399"
                d_str = f"{dlt:,.2f} ({pct:+.1f}%)"
            elif dlt > 0.005:
                d_col = "#fbbf24"
                d_str = f"+{dlt:,.2f} ({pct:+.1f}%)"
            else:
                d_col = "#94a3b8"
                d_str = "0.00 (0.0%)"

            qty_info = f"<span style='color:#94a3b8; font-size:0.75rem;'>({r['qty_base']:,.1f} &rarr; {r['qty_bess']:,.1f} {r['unit']})</span>"
            html_parts.append(
                f'<tr style="background-color: {bg}; border-bottom: 1px solid #334155; {dim_style}">'
                f'<td style="padding: 7px 10px; font-weight: 600; color: #94a3b8; font-size: 0.82rem;">{r["pos"]}</td>'
                f'<td style="padding: 7px 10px; color: #f1f5f9; font-size: 0.84rem;">{r["description"]} {qty_info}</td>'
                f'<td style="padding: 7px 10px; text-align: right; color: #cbd5e1; font-size: 0.84rem;">{curr} {vb:,.2f}</td>'
                f'<td style="padding: 7px 10px; text-align: right; color: #f8fafc; font-weight: 600; font-size: 0.84rem;">{curr} {vw:,.2f}</td>'
                f'<td style="padding: 7px 10px; text-align: right; color: {d_col}; font-weight: 700; font-size: 0.84rem;">{d_str}</td>'
                f'</tr>'
            )

        sub_d = sub_w - sub_b
        sub_pct = (sub_d / sub_b * 100.0) if abs(sub_b) > 1e-6 else 0.0
        sub_col = "#34d399" if sub_d < -0.005 else ("#fbbf24" if sub_d > 0.005 else "#94a3b8")
        sub_str = f"{sub_d:+,.2f} ({sub_pct:+.1f}%)" if abs(sub_d) > 0.005 else "0.00 (0.0%)"

        html_parts.append(
            f'<tr style="background-color: #172554; border-bottom: 2px solid #334155; {dim_style}">'
            f'<td colspan="2" style="padding: 7px 10px; text-align: right; font-weight: 700; color: #cbd5e1; font-size: 0.83rem;">'
            f'= Subtotal {blk_title}:</td>'
            f'<td style="padding: 7px 10px; text-align: right; font-weight: 700; color: #e2e8f0; font-size: 0.85rem;">{curr} {sub_b:,.2f}</td>'
            f'<td style="padding: 7px 10px; text-align: right; font-weight: 700; color: #ffffff; font-size: 0.85rem;">{curr} {sub_w:,.2f}</td>'
            f'<td style="padding: 7px 10px; text-align: right; font-weight: 700; color: {sub_col}; font-size: 0.85rem;">{sub_str}</td>'
            f'</tr>'
        )

    # Grand Totals: Net, VAT, Gross, Blended Rate
    net_b, net_w = float(ib["total_net"]), float(iw["total_net"])
    net_d = net_w - net_b
    net_pct = (net_d / net_b * 100.0) if abs(net_b) > 1e-6 else 0.0

    vat_b, vat_w = float(ib["vat_amount"]), float(iw["vat_amount"])
    vat_d = vat_w - vat_b

    grs_b, grs_w = float(ib["total_gross"]), float(iw["total_gross"])
    grs_d = grs_w - grs_b
    grs_pct = (grs_d / grs_b * 100.0) if abs(grs_b) > 1e-6 else 0.0

    bl_b, bl_w = float(ib["effective_rate_net"]), float(iw["effective_rate_net"])
    bl_d = bl_w - bl_b

    html_parts.extend([
        f'<tr style="background-color: #0f172a; border-top: 2px solid #38bdf8;">'
        f'<td colspan="2" style="padding: 9px 10px; text-align: right; font-weight: 800; color: #38bdf8; font-size: 0.90rem;">= TOTAL NET ELECTRICITY BILL (1 + 2 + 3 + 4):</td>'
        f'<td style="padding: 9px 10px; text-align: right; font-weight: 800; color: #f8fafc; font-size: 0.92rem;">{curr} {net_b:,.2f}</td>'
        f'<td style="padding: 9px 10px; text-align: right; font-weight: 800; color: #ffffff; font-size: 0.92rem;">{curr} {net_w:,.2f}</td>'
        f'<td style="padding: 9px 10px; text-align: right; font-weight: 800; color: #34d399; font-size: 0.92rem;">{net_d:+,.2f} ({net_pct:+.1f}%)</td>'
        f'</tr>',
        f'<tr style="background-color: #1e293b; border-bottom: 1px solid #334155;">'
        f'<td colspan="2" style="padding: 7px 10px; text-align: right; font-weight: 600; color: #94a3b8; font-size: 0.84rem;">+ Value Added Tax (VAT @ {vat_pct_rate:.1f}%):</td>'
        f'<td style="padding: 7px 10px; text-align: right; color: #cbd5e1; font-size: 0.84rem;">{curr} {vat_b:,.2f}</td>'
        f'<td style="padding: 7px 10px; text-align: right; color: #cbd5e1; font-size: 0.84rem;">{curr} {vat_w:,.2f}</td>'
        f'<td style="padding: 7px 10px; text-align: right; color: #34d399; font-size: 0.84rem;">{vat_d:+,.2f}</td>'
        f'</tr>',
        f'<tr style="background-color: #06281e; border-top: 2px solid #10b981;">'
        f'<td colspan="2" style="padding: 10px 10px; text-align: right; font-weight: 800; color: #34d399; font-size: 0.96rem;">= TOTAL GROSS ELECTRICITY BILL (INCL. VAT):</td>'
        f'<td style="padding: 10px 10px; text-align: right; font-weight: 800; color: #ffffff; font-size: 0.98rem;">{curr} {grs_b:,.2f}</td>'
        f'<td style="padding: 10px 10px; text-align: right; font-weight: 800; color: #ffffff; font-size: 0.98rem;">{curr} {grs_w:,.2f}</td>'
        f'<td style="padding: 10px 10px; text-align: right; font-weight: 800; color: #34d399; font-size: 0.98rem;">{grs_d:+,.2f} ({grs_pct:+.1f}%)</td>'
        f'</tr>',
        f'<tr style="background-color: #0f172a;">'
        f'<td colspan="2" style="padding: 7px 10px; text-align: right; font-weight: 600; color: #94a3b8; font-size: 0.82rem;">Effective Blended Rate (Net {curr}/kWh):</td>'
        f'<td style="padding: 7px 10px; text-align: right; color: #cbd5e1; font-size: 0.82rem;">{curr} {bl_b:.4f}/kWh</td>'
        f'<td style="padding: 7px 10px; text-align: right; color: #38bdf8; font-weight: 700; font-size: 0.82rem;">{curr} {bl_w:.4f}/kWh</td>'
        f'<td style="padding: 7px 10px; text-align: right; color: #34d399; font-weight: 600; font-size: 0.82rem;">{bl_d:+.4f}/kWh</td>'
        f'</tr>',
        '</tbody></table></div>',
    ])

    return "\n".join(html_parts)


def render_bill_and_profile_comparison_tab(
    preset: presets.BaselinePreset,
    sim_result: BESSSimulationResult,
    assumptions_dict: Optional[Dict[str, Any]] = None,
    key_prefix: str = "bess_sb_comp"
) -> Dict[str, Any]:
    """
    Renders Tab 3: "3. Baseline vs. BESS Bill & Profile Comparison":
      - Section 1: Effect on Grid Demand Profile & Remaining Peaks (KPI Strip + Synced 2-in-1 Dispatch & SoC Chart)
      - Section 2: Effect on Resulting Electricity Costs (Side-by-Side 4-Pillar Electricity Bill Comparison + PDF Export)
    """
    st.subheader(":material/compare_arrows: Baseline (Without BESS) vs. Peak-Shaving Scenario (With BESS)")
    st.caption(
        "Direct side-by-side verification of how battery peak shaving alters the physical grid import profile (`P_Load_kW` vs. `P_Grid_kW`), "
        "eliminates capacity exceedances, and reduces the itemized 4-Pillar electricity bill."
    )

    active_limit_kw = float(st.session_state.get("bess_sb_active_limit_kw", preset.grid_limit_kw))

    # Billing period selector for Section 2
    ctrl_col1, ctrl_col2 = st.columns([2.2, 1.8])
    with ctrl_col1:
        period_options = [
            "Peak Billing Month (Single Month Invoice View)",
            "Full Year 2025 (12-Month Annualized Aggregation)"
        ]
        selected_period = st.selectbox(
            "Electricity Bill Evaluation Horizon",
            options=period_options,
            index=0,
            key=f"{key_prefix}_period_select",
            help="Compare either a single peak monthly utility invoice or the full 12-month annualized electricity bill."
        )

    comp_data = evaluate_baseline_vs_bess_4pillar_bills(
        sim_result=sim_result,
        preset=preset,
        active_limit_kw=active_limit_kw,
        period_choice=selected_period
    )
    phys = comp_data["physical"]
    curr = comp_data["currency"]

    with ctrl_col2:
        net_sav = float(comp_data["inv_base"]["total_net"]) - float(comp_data["inv_bess"]["total_net"])
        grs_sav = float(comp_data["inv_base"]["total_gross"]) - float(comp_data["inv_bess"]["total_gross"])
        st.success(
            f"**Net Bill Savings ({comp_data['period_label']}):** `{curr} {net_sav:,.2f}`\n\n"
            f"**Gross Bill Savings (incl. VAT):** `{curr} {grs_sav:,.2f}`",
            icon=":material/savings:"
        )

    # =========================================================================
    # SECTION 1: Effect on Grid Demand Profile & Remaining Peaks
    # =========================================================================
    st.markdown("---")
    st.markdown("### :material/monitoring: 1. Effect on Grid Demand Profile, Remaining Peaks & Battery SoC")

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    with kpi1:
        peak_delta = phys["peak_after_kw"] - phys["peak_before_kw"]
        st.metric(
            label="Grid Peak Demand (Before -> With BESS)",
            value=f"{phys['peak_before_kw']:,.1f} -> {phys['peak_after_kw']:,.1f} kW",
            delta=f"{peak_delta:,.1f} kW shaved (Limit: {active_limit_kw:,.1f} kW)",
            delta_color="normal"
        )
    with kpi2:
        st.metric(
            label="Remaining Peak Deficit (Above Limit)",
            value=f"{phys['overload_after_kw']:,.1f} kW",
            delta=f"Before BESS: +{phys['overload_before_kw']:,.1f} kW ({phys['overload_hours_before']:,.1f} hrs)",
            delta_color="normal" if phys["overload_after_kw"] <= 0.05 else "inverse"
        )
    with kpi3:
        st.metric(
            label="Uncovered Overload Energy",
            value=f"{phys['overload_energy_after_kwh']:,.1f} kWh",
            delta=f"Shaved: {phys['overload_energy_before_kwh'] - phys['overload_energy_after_kwh']:,.1f} kWh",
            delta_color="normal" if phys["overload_energy_after_kwh"] <= 0.05 else "inverse"
        )
    with kpi4:
        st.metric(
            label="Grid Import Energy & RTE Loss",
            value=f"{phys['energy_after_kwh']:,.0f} kWh",
            delta=f"BESS Discharged: {phys['bess_discharged_kwh']:,.0f} kWh | RTE Loss: +{phys['rte_loss_kwh']:,.1f} kWh",
            delta_color="off"
        )

    with st.expander(":material/show_chart: Interactive Synchronized Grid Demand (`P_Load_kW` vs `P_Grid_kW`) & Battery SoC Chart", expanded=True):
        init_focus = compute_focus_range(sim_result.df_timeseries, days=7.0)
        bess_cfg = sim_result.config
        fig_comp = create_synced_dispatch_soc_figure(
            df=sim_result.df_timeseries,
            grid_limit_kw=active_limit_kw,
            soc_min_pct=bess_cfg.soc_min_pct,
            soc_max_pct=bess_cfg.soc_max_pct,
            capacity_kwh=bess_cfg.capacity_kwh,
            initial_range=init_focus
        )
        st.plotly_chart(fig_comp, use_container_width=True, key=f"{key_prefix}_synced_plotly")

    # =========================================================================
    # SECTION 2: Effect on Resulting Electricity Costs (Side-by-Side Bill)
    # =========================================================================
    st.markdown("---")
    st.markdown("### :material/receipt_long: 2. Effect on Resulting Electricity Bill (Baseline vs. With-BESS Line-by-Line)")
    st.caption(
        "Itemized 4-Pillar electricity invoice comparison showing exact cost changes across "
        "Pillar 1 (Commodity & RTE conversion loss), Pillar 2 (Contracted Capacity, Monthly Peak Demand & Eliminated Penalties), "
        "Pillar 3 (Metering), and Pillar 4 (Statutory Taxes & VAT)."
    )

    st.markdown(_render_side_by_side_bill_html(comp_data), unsafe_allow_html=True)

    # --- PDF & CSV Export Bar ---
    exp_col1, exp_col2 = st.columns(2)
    with exp_col1:
        pdf_bytes = generate_bess_comparison_report_pdf(
            site_name=f"{preset.title} ({comp_data['period_label']})",
            currency_code=curr,
            assumptions_dict=assumptions_dict or {},
            physical_kpis=phys,
            comparison_rows=comp_data["pdf_comparison_rows"]
        )
        safe_preset = preset.key.replace(" ", "_")
        st.download_button(
            label=f":material/picture_as_pdf: Download Baseline vs. BESS Comparison Report (PDF - {curr})",
            data=pdf_bytes,
            file_name=f"BESS_Bill_Comparison_{safe_preset}.pdf",
            mime="application/pdf",
            use_container_width=True,
            key=f"{key_prefix}_dl_pdf_btn"
        )

    with exp_col2:
        df_csv_export = pd.DataFrame(comp_data["comparison_rows"])
        csv_bytes = df_csv_export.to_csv(index=False).encode("utf-8")
        st.download_button(
            label=":material/download: Export Side-by-Side Bill Comparison (CSV)",
            data=csv_bytes,
            file_name=f"BESS_Bill_Comparison_{safe_preset}.csv",
            mime="text/csv",
            use_container_width=True,
            key=f"{key_prefix}_dl_csv_btn"
        )

    return comp_data
