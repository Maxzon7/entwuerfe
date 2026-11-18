"""
Pure Python (zero Streamlit) Scenario Comparison helpers (`1..N` architecture ready):
  - Plain-language upgrade cost vs. yearly savings evaluation
  - Unused battery value, unit-rate savings & 15-year cost split indicators
  - Segmented 5-domain comparison tables
  - Zero-simulation `snapshot_to_sim_view` adapter for reusing single-scenario charts

Re-exported via `engine/__init__.py` and `combined_sandbox_engine.py`.
"""

from typing import Any, Dict, List, Optional, Sequence
import numpy as np
import pandas as pd

from .models_and_presets import (
    CombinedScenarioSnapshot,
    CombinedSimulationResult,
)
from .scenario_comparison_engine import (
    normalize_scenario_list,
    format_currency_value,
    build_ab_comparison_matrix_df,
)


def _curr_prefix(currency_code: str = "EUR") -> str:
    """Returns compact currency prefix (`€`, `$`, or `<ISO> `)."""
    return "€" if currency_code == "EUR" else ("$" if currency_code == "USD" else f"{currency_code} ")


def compute_snapshot_bwl_extensions(snap: CombinedScenarioSnapshot) -> Dict[str, Any]:
    """
    Computes BWL investment efficiency & dead-capital indicators for a single
    `CombinedScenarioSnapshot`:
      - `idle_bess_kwh` & `idle_bess_capex_eur`: unused usable battery reserve valued at implied EUR/kWh
      - `lcoe_spread_eur_kwh`: Blended Grid Rate minus On-Site System LCOE (+ = cheaper than grid)
      - `capital_productivity_per_1k`: Year-1 Net Savings generated per 1,000 invested Net CAPEX
      - `fixed_capex_share_15y_pct` / `variable_opex_share_15y_pct`: 15Y inflation-shield vs. tariff-exposed split
    """
    u = snap.utilization_diagnostics
    fk = snap.financial_kpis
    fin_cfg = snap.financial_config
    has_fin = bool(getattr(snap.system_config, "enable_financials", False) and fk is not None)

    idle_bess_kwh = float(u.bess_unused_usable_kwh) if snap.system_config.enable_battery else 0.0
    implied_bess_unit = float(getattr(fin_cfg, "battery_capex_eur_kwh", 0.0) or 0.0)
    if fk is not None and float(getattr(fk, "battery_implied_eur_kwh", 0.0) or 0.0) > 0.0:
        implied_bess_unit = float(fk.battery_implied_eur_kwh)
    idle_bess_capex_eur = (idle_bess_kwh * implied_bess_unit) if (has_fin and snap.system_config.enable_battery) else 0.0

    if not has_fin or fk is None:
        return {
            "has_financials": False,
            "idle_bess_kwh": idle_bess_kwh,
            "implied_bess_eur_kwh": implied_bess_unit,
            "idle_bess_capex_eur": 0.0,
            "lcoe_spread_eur_kwh": 0.0,
            "capital_productivity_per_1k": 0.0,
            "fixed_capex_share_15y_pct": 0.0,
            "variable_opex_share_15y_pct": 100.0,
        }

    net_capex = float(fk.total_capex_eur)
    rep_capex = float(fk.battery_augmentation_eur) if snap.system_config.enable_battery else 0.0
    tco_15y = float(fk.tco_15y_combined_eur)

    lcoe_spread = float(fk.effective_blended_grid_rate_eur_kwh) - float(fk.system_lcoe_eur_kwh)
    cap_prod = (float(fk.annual_savings_eur) / net_capex * 1000.0) if net_capex > 0.0 else 0.0
    fixed_share = min(100.0, max(0.0, ((net_capex + rep_capex) / max(1.0, tco_15y)) * 100.0)) if tco_15y > 0.0 else 0.0

    return {
        "has_financials": True,
        "idle_bess_kwh": idle_bess_kwh,
        "implied_bess_eur_kwh": implied_bess_unit,
        "idle_bess_capex_eur": idle_bess_capex_eur,
        "lcoe_spread_eur_kwh": lcoe_spread,
        "capital_productivity_per_1k": cap_prod,
        "fixed_capex_share_15y_pct": fixed_share,
        "variable_opex_share_15y_pct": max(0.0, 100.0 - fixed_share),
    }


def compute_incremental_bwl_evaluation(
    snap_a: Optional[CombinedScenarioSnapshot] = None,
    snap_b: Optional[CombinedScenarioSnapshot] = None,
    scenarios: Optional[Sequence[CombinedScenarioSnapshot]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Evaluates the BWL Incremental Investment Decision (`Differenzinvestitionsrechnung`)
    comparing the lower-CAPEX baseline candidate against the higher-CAPEX upgrade candidate.
    Returns `None` if fewer than 2 same-currency financial snapshots are available.
    """
    items = normalize_scenario_list(snap_a, snap_b, scenarios=scenarios)
    fin_snaps = [
        s for s in items
        if getattr(s.system_config, "enable_financials", False) and s.financial_kpis is not None
    ]
    if len(fin_snaps) < 2:
        return None

    currencies = {str(s.financial_config.currency_code or "EUR") for s in fin_snaps}
    if len(currencies) != 1:
        return None
    curr = next(iter(currencies))

    low_cap_snap = min(fin_snaps, key=lambda s: float(s.financial_kpis.total_capex_eur))
    remaining = [s for s in fin_snaps if s is not low_cap_snap]
    high_cap_snap = max(remaining, key=lambda s: float(s.financial_kpis.total_capex_eur))

    low_fk = low_cap_snap.financial_kpis
    high_fk = high_cap_snap.financial_kpis
    delta_capex = float(high_fk.total_capex_eur) - float(low_fk.total_capex_eur)
    delta_opex_savings = float(low_fk.total_annual_opex_eur) - float(high_fk.total_annual_opex_eur)
    delta_tco_savings = float(low_fk.tco_15y_combined_eur) - float(high_fk.tco_15y_combined_eur)
    delta_npv = float(high_fk.npv_15y_eur) - float(low_fk.npv_15y_eur)

    if delta_capex > 0.5 and delta_opex_savings > 1.0:
        inc_payback: Optional[float] = delta_capex / delta_opex_savings
    elif delta_capex <= 0.5 and delta_opex_savings > 0.0:
        inc_payback = 0.0
    else:
        inc_payback = None

    accretive = bool(delta_tco_savings > 0.0)
    never_pays_back = bool(delta_capex > 0.5 and delta_opex_savings <= 1.0)
    winner_name = high_cap_snap.name if accretive else low_cap_snap.name

    if delta_capex > 0.5 and delta_opex_savings <= 0.0:
        verdict_title = f"{low_cap_snap.name} wins on both upfront cost and yearly savings"
        verdict_text = (
            f"Both options are profitable on their own, but in a direct comparison {low_cap_snap.name} "
            f"costs {format_currency_value(delta_capex, curr)} less upfront AND saves "
            f"{format_currency_value(abs(delta_opex_savings), curr)}/yr more than {high_cap_snap.name} "
            f"— finishing {format_currency_value(abs(delta_tco_savings), curr)} ahead over 15 years."
        )
    elif accretive and inc_payback is not None and inc_payback <= 15.0:
        verdict_title = f"{high_cap_snap.name} pays back its extra upfront cost in {inc_payback:.1f} years"
        verdict_text = (
            f"Spending an extra {format_currency_value(delta_capex, curr)} upfront for {high_cap_snap.name} "
            f"instead of {low_cap_snap.name} lowers yearly running costs by "
            f"{format_currency_value(delta_opex_savings, curr)}/yr, "
            f"delivering {format_currency_value(delta_tco_savings, curr, signed=True)} higher net profit over 15 years."
        )
    elif delta_capex <= 0.5 and delta_tco_savings > 0.0:
        verdict_title = f"{high_cap_snap.name} wins on both upfront cost and 15-year profit"
        verdict_text = (
            f"{high_cap_snap.name} saves an extra {format_currency_value(delta_tco_savings, curr)} over 15 years "
            f"without costing more upfront."
        )
    else:
        verdict_title = f"{low_cap_snap.name} is the better deal over 15 years"
        pb_txt = f"{inc_payback:.1f} years" if inc_payback is not None else "more than 15 years"
        verdict_text = (
            f"The extra {format_currency_value(delta_capex, curr)} upfront cost for {high_cap_snap.name} "
            f"only saves {format_currency_value(delta_opex_savings, curr)}/yr more than {low_cap_snap.name} "
            f"(payback on extra cost: {pb_txt}), leaving {low_cap_snap.name} ahead by "
            f"{format_currency_value(abs(delta_tco_savings), curr)} over 15 years."
        )

    return {
        "currency_code": curr,
        "low_cap_name": low_cap_snap.name,
        "high_cap_name": high_cap_snap.name,
        "winner_name": winner_name,
        "never_pays_back": never_pays_back,
        "low_capex_eur": float(low_fk.total_capex_eur),
        "high_capex_eur": float(high_fk.total_capex_eur),
        "delta_capex_eur": delta_capex,
        "low_opex_y1_eur": float(low_fk.total_annual_opex_eur),
        "high_opex_y1_eur": float(high_fk.total_annual_opex_eur),
        "delta_annual_opex_savings_eur": delta_opex_savings,
        "incremental_payback_years": inc_payback,
        "delta_tco_15y_savings_eur": delta_tco_savings,
        "delta_npv_15y_eur": delta_npv,
        "is_upgrade_value_accretive": accretive,
        "verdict_title": verdict_title,
        "verdict_text": verdict_text,
    }


def _short_hw_signature(snap: Optional[CombinedScenarioSnapshot]) -> str:
    """Compact system hardware signature for domain table footers."""
    if snap is None:
        return "—"
    c = snap.system_config
    parts: List[str] = []
    if c.enable_solar:
        parts.append(f"PV {snap.solar_derivation.installed_kwp:,.0f}kWp")
    if c.enable_battery:
        parts.append(f"BESS {c.battery_capacity_kwh:,.0f}kWh")
    if c.enable_generator:
        parts.append(f"Gen {c.generator_rated_kw:,.0f}kW")
    return " + ".join(parts) if parts else "Grid Only"


def build_segmented_comparison_tables(
    snap_a: Optional[CombinedScenarioSnapshot] = None,
    snap_b: Optional[CombinedScenarioSnapshot] = None,
    scenarios: Optional[Sequence[CombinedScenarioSnapshot]] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    Builds 5 focused domain comparison tables (`3` technical + `2` BWL/financial when Financials is active)
    reusing `build_ab_comparison_matrix_df` and adding BWL dead-capital, LCOE spread, capital productivity,
    and 15Y fixed-vs-variable risk rows.
    """
    if scenarios is not None and snap_a is None and snap_b is None:
        clean_list = [s for s in scenarios if s is not None]
        snap_a = clean_list[0] if len(clean_list) >= 1 else None
        snap_b = clean_list[1] if len(clean_list) >= 2 else None

    df_full = build_ab_comparison_matrix_df(snap_a, snap_b)
    if df_full.empty:
        return {}

    ref = snap_a if snap_a is not None else snap_b
    assert ref is not None
    cols = list(df_full.columns)
    row_by_metric = {str(r["Metric / KPI"]): dict(r) for r in df_full.to_dict(orient="records")}

    ext_a = compute_snapshot_bwl_extensions(snap_a) if snap_a is not None else None
    ext_b = compute_snapshot_bwl_extensions(snap_b) if snap_b is not None else None
    has_fin_a = bool(ext_a and ext_a["has_financials"])
    has_fin_b = bool(ext_b and ext_b["has_financials"])
    any_fin = has_fin_a or has_fin_b
    same_curr = bool(
        snap_a is not None
        and snap_b is not None
        and snap_a.financial_config.currency_code == snap_b.financial_config.currency_code
    )
    curr_a = str(snap_a.financial_config.currency_code or "EUR") if snap_a else "EUR"
    curr_b = str(snap_b.financial_config.currency_code or "EUR") if snap_b else "EUR"
    ref_curr = curr_a if has_fin_a else curr_b

    def _subset_df(metrics_order: List[str], extra_rows: Optional[List[Dict[str, str]]] = None) -> pd.DataFrame:
        selected = [row_by_metric[m] for m in metrics_order if m in row_by_metric]
        if extra_rows:
            selected.extend(extra_rows)
        return pd.DataFrame(selected, columns=cols)

    def _info_row(metric: str, cur_s: str, a_s: str, b_s: str, d_s: str) -> Dict[str, str]:
        return {
            "Category": "Value & Efficiency",
            "Metric / KPI": metric,
            "Current Situation": cur_s,
            "Scenario A": a_s,
            "Scenario B": b_s,
            "Delta (B vs. A)": d_s,
        }

    # 1. Hardware Sizing & Operating Rules
    sizing_df = _subset_df([
        "Scenario Name",
        "Contracted Grid Limit (kW)",
        "Solar PV Size",
        "Battery Storage (kWh / kW)",
        "Peaking Generator (kW & Fuel)",
        "Operating Rules (R1 / R2 / R3)",
    ])

    # 2. Grid Compliance, Peak Shaving & Energy Balance
    grid_df = _subset_df([
        "Peak Grid Demand (kW)",
        "Peak Demand Shaved (kW)",
        "Remaining Overload (hrs/yr)",
        "Remaining Overload Energy (kWh/yr)",
        "Overload Eliminated (%)",
        "On-Site Autarky Share (%)",
        "Annual Residual Grid Import (MWh/yr)",
        "Supply Share: Grid (%)",
        "Supply Share: Solar Direct (%)",
        "Supply Share: Battery Discharge (%)",
        "Supply Share: Generator (%)",
    ])

    # 3. Asset Utilization & Oversizing Diagnostics (Dead-Capital Check)
    idle_extra: List[Dict[str, str]] = []
    if any_fin:
        idle_a = (
            format_currency_value(ext_a["idle_bess_capex_eur"], curr_a) if has_fin_a else "Financials Off"
        ) if snap_a else "—"
        idle_b = (
            format_currency_value(ext_b["idle_bess_capex_eur"], curr_b) if has_fin_b else "Financials Off"
        ) if snap_b else "—"
        idle_d = (
            format_currency_value(ext_b["idle_bess_capex_eur"] - ext_a["idle_bess_capex_eur"], ref_curr, signed=True)
            if (has_fin_a and has_fin_b and same_curr)
            else "—"
        )
        idle_extra.append(_info_row("Unused Battery Value", format_currency_value(0.0, ref_curr), idle_a, idle_b, idle_d))

    util_df = _subset_df(
        [
            "Solar Generation / Used On-Site",
            "Solar Exported Surplus (MWh/yr)",
            "Battery Cycles / Capacity Used",
            "Battery Min SoC / Unused Reserve",
        ],
        extra_rows=idle_extra,
    )
    if "Generator Runtime & Fuel" in row_by_metric:
        util_df = pd.concat([util_df, pd.DataFrame([row_by_metric["Generator Runtime & Fuel"]], columns=cols)], ignore_index=True)

    def _compliance_badge(snap: Optional[CombinedScenarioSnapshot]) -> str:
        if snap is None:
            return "—"
        hrs = float(snap.kpis.remaining_overload_hours)
        return "COMPLIANT (0.0 hrs)" if hrs <= 0.05 else f"BREACH ({hrs:,.1f} hrs)"

    def _unused_footer(snap: Optional[CombinedScenarioSnapshot], ext: Optional[Dict[str, Any]], curr_c: str) -> str:
        if snap is None or ext is None:
            return "—"
        if not snap.system_config.enable_battery:
            return "No BESS"
        if ext["has_financials"]:
            return f"{ext['idle_bess_kwh']:,.0f} kWh ({format_currency_value(ext['idle_bess_capex_eur'], curr_c)})"
        return f"{ext['idle_bess_kwh']:,.0f} kWh unused"

    delta_peak_str = row_by_metric.get("Peak Grid Demand (kW)", {}).get("Delta (B vs. A)", "—")
    delta_idle_str = idle_extra[0]["Delta (B vs. A)"] if idle_extra else row_by_metric.get("Battery Min SoC / Unused Reserve", {}).get("Delta (B vs. A)", "—")

    tables: Dict[str, Dict[str, Any]] = {
        "sizing_rules": {
            "title": ":material/tune: 1. System Size & Operating Rules",
            "header_title": "1. System Size &amp; Operating Rules",
            "accent_color": "#38BDF8",
            "df": sizing_df,
            "footer_cells": [
                "System Summary",
                "Grid Only",
                _short_hw_signature(snap_a),
                _short_hw_signature(snap_b),
                f"{snap_b.system_config.grid_limit_kw - snap_a.system_config.grid_limit_kw:+.0f} kW Limit" if (snap_a and snap_b) else "—",
            ],
        },
        "grid_balance": {
            "title": ":material/bolt: 2. Grid Limit & Electricity Supply",
            "header_title": "2. Grid Limit &amp; Electricity Supply",
            "accent_color": "#10B981",
            "df": grid_df,
            "footer_cells": [
                "Grid Limit Status",
                f"Overload ({ref.kpis.baseline_overload_hours:,.1f} hrs)",
                _compliance_badge(snap_a),
                _compliance_badge(snap_b),
                f"Peak {delta_peak_str}" if delta_peak_str != "—" else "—",
            ],
        },
        "utilization_dead_cap": {
            "title": ":material/speed: 3. System Usage & Unused Capacity",
            "header_title": "3. System Usage &amp; Unused Capacity",
            "accent_color": "#F59E0B",
            "df": util_df,
            "footer_cells": [
                "Unused Battery / Idle Value",
                "N/A",
                _unused_footer(snap_a, ext_a, curr_a),
                _unused_footer(snap_b, ext_b, curr_b),
                delta_idle_str,
            ],
        },
    }

    if not any_fin:
        return tables

    # 4. Upfront Cost & Yearly Electricity Bill
    pnl_df = _subset_df([
        "Gross Hardware CAPEX",
        "Avoided Grid Upgrade Credit",
        "Net Upfront CAPEX",
        "Year-1 Pillar 1: Energy Supply",
        "Year-1 Pillar 2: DSO Network (excl. Penalties)",
        "Year-1 Pillar 2: Overload Penalties",
        "Year-1 Pillar 3 & 4: Metering & Taxes",
        "Year-1 Total Grid Bill (4-Pillar)",
        "Year-1 Hardware O&M & Generator OPEX",
        "Year-1 Solar Export Revenue",
        "Year-1 Net Operating Cost (Total OPEX)",
        "Year-1 Net Annual Savings (vs. Current)",
    ])
    fin_ref = snap_a if has_fin_a else snap_b
    assert fin_ref is not None
    opex_a_str = format_currency_value(snap_a.financial_kpis.total_annual_opex_eur, curr_a) if has_fin_a else ("Financials Off" if snap_a else "—")
    opex_b_str = format_currency_value(snap_b.financial_kpis.total_annual_opex_eur, curr_b) if has_fin_b else ("Financials Off" if snap_b else "—")
    sav_delta_str = row_by_metric.get("Year-1 Net Annual Savings (vs. Current)", {}).get("Delta (B vs. A)", "—")

    tables["capex_y1_pnl"] = {
        "title": f":material/receipt_long: 4. Upfront Cost & Yearly Electricity Bill ({ref_curr})",
        "header_title": f"4. Upfront Cost &amp; Yearly Electricity Bill ({ref_curr})",
        "accent_color": "#6366F1",
        "df": pnl_df,
        "footer_cells": [
            "Yearly Running Cost (Net)",
            format_currency_value(fin_ref.financial_kpis.baseline_total_opex_eur, ref_curr),
            opex_a_str,
            opex_b_str,
            f"Y1 Savings {sav_delta_str}" if sav_delta_str != "—" else "—",
        ],
    }

    # 5. 15-Year Costs, Payback & Profit
    def _fmt_spread(snap: Optional[CombinedScenarioSnapshot], ext: Optional[Dict[str, Any]], curr_c: str) -> str:
        if snap is None:
            return "—"
        if not ext or not ext["has_financials"]:
            return "Financials Off"
        return f"{_curr_prefix(curr_c)}{ext['lcoe_spread_eur_kwh']:+.3f}/kWh"

    def _fmt_prod(snap: Optional[CombinedScenarioSnapshot], ext: Optional[Dict[str, Any]], curr_c: str) -> str:
        if snap is None:
            return "—"
        if not ext or not ext["has_financials"]:
            return "Financials Off"
        return f"{format_currency_value(ext['capital_productivity_per_1k'], curr_c)} / 1k"

    def _fmt_risk(snap: Optional[CombinedScenarioSnapshot], ext: Optional[Dict[str, Any]]) -> str:
        if snap is None:
            return "—"
        if not ext or not ext["has_financials"]:
            return "Financials Off"
        return f"{ext['fixed_capex_share_15y_pct']:.0f}% Upfront / {ext['variable_opex_share_15y_pct']:.0f}% Running"

    bwl_extra_rows = [
        _info_row(
            "Savings per kWh vs. Grid",
            "0.000/kWh",
            _fmt_spread(snap_a, ext_a, curr_a),
            _fmt_spread(snap_b, ext_b, curr_b),
            f"{(ext_b['lcoe_spread_eur_kwh'] - ext_a['lcoe_spread_eur_kwh']):+.3f}/kWh" if (has_fin_a and has_fin_b and same_curr) else "—",
        ),
        _info_row(
            "Yearly Savings per 1,000 Invested",
            "—",
            _fmt_prod(snap_a, ext_a, curr_a),
            _fmt_prod(snap_b, ext_b, curr_b),
            format_currency_value(ext_b["capital_productivity_per_1k"] - ext_a["capital_productivity_per_1k"], ref_curr, signed=True)
            if (has_fin_a and has_fin_b and same_curr)
            else "—",
        ),
        _info_row(
            "15-Year Cost Split (Upfront vs. Running)",
            "0% Upfront / 100% Running",
            _fmt_risk(snap_a, ext_a),
            _fmt_risk(snap_b, ext_b),
            f"{ext_b['fixed_capex_share_15y_pct'] - ext_a['fixed_capex_share_15y_pct']:+.0f} pp Upfront"
            if (has_fin_a and has_fin_b)
            else "—",
        ),
    ]

    bwl_df = _subset_df(
        [
            "Simple Payback Period",
            "Discounted Payback Period",
            "15-Year Cumulative TCO",
            "15-Year TCO Net Savings (vs. Current)",
            "15-Year Net Present Value (NPV)",
            "15-Year Internal Rate of Return (IRR)",
            "15-Year Benefit-Cost Ratio (BCR)",
            "On-Site System LCOE (per kWh)",
        ],
        extra_rows=bwl_extra_rows,
    )
    if "Annualized Cost per Shaved Peak kW" in row_by_metric:
        bwl_df = pd.concat([bwl_df, pd.DataFrame([row_by_metric["Annualized Cost per Shaved Peak kW"]], columns=cols)], ignore_index=True)

    tco_a_str = format_currency_value(snap_a.financial_kpis.tco_15y_combined_eur, curr_a) if has_fin_a else ("Financials Off" if snap_a else "—")
    tco_b_str = format_currency_value(snap_b.financial_kpis.tco_15y_combined_eur, curr_b) if has_fin_b else ("Financials Off" if snap_b else "—")
    tco_d_str = row_by_metric.get("15-Year Cumulative TCO", {}).get("Delta (B vs. A)", "—")

    tables["bwl_15y_metrics"] = {
        "title": f":material/monitoring: 5. 15-Year Costs, Payback & Profit ({ref_curr})",
        "header_title": f"5. 15-Year Costs, Payback &amp; Profit ({ref_curr})",
        "accent_color": "#A855F7",
        "df": bwl_df,
        "footer_cells": [
            "15-Year Total Cost",
            format_currency_value(fin_ref.financial_kpis.tco_15y_baseline_eur, ref_curr),
            tco_a_str,
            tco_b_str,
            tco_d_str,
        ],
    }
    return tables


def snapshot_to_sim_view(
    snap: CombinedScenarioSnapshot,
    load_series: Optional[Any] = None,
) -> CombinedSimulationResult:
    """
    Reconstructs a lightweight `CombinedSimulationResult` view in O(1) directly from
    a stored `CombinedScenarioSnapshot` and active `load_series`, allowing all single-scenario
    charts (Supply Mix, Utilization, 15Y Cashflow, Waterfall, Power Flow) to render with zero dispatch re-run.
    """
    grid_imp = (
        np.asarray(snap.grid_import_kw_f32, dtype=np.float32)
        if getattr(snap, "grid_import_kw_f32", None) is not None and len(snap.grid_import_kw_f32) > 0
        else np.zeros(35040, dtype=np.float32)
    )
    n = len(grid_imp)
    d = getattr(snap, "dispatch_f32_dict", None) or {}

    def _vec(arr: Optional[np.ndarray], fallback_val: float = 0.0) -> np.ndarray:
        if arr is not None and len(arr) == n:
            return np.asarray(arr, dtype=np.float32)
        return np.full(n, fallback_val, dtype=np.float32)

    raw_load = getattr(load_series, "power_kw", None)
    load_arr = _vec(raw_load) if raw_load is not None else grid_imp.copy()

    raw_ts = getattr(load_series, "timestamps", None)
    if raw_ts is not None and len(raw_ts) == n:
        ts_idx = raw_ts
    else:
        ts_idx = pd.date_range("2025-01-01 00:00:00", periods=n, freq="15min")

    raw_gap = getattr(load_series, "is_gap", None)
    is_gap_arr = np.asarray(raw_gap, dtype=bool) if (raw_gap is not None and len(raw_gap) == n) else np.zeros(n, dtype=bool)

    soc_arr = _vec(getattr(snap, "bess_soc_pct_f32", None))
    unmet_arr = _vec(getattr(snap, "unmet_overload_kw_f32", None))
    sol_gen = _vec(d.get("solar_gen_kw"))
    sol_dir = _vec(d.get("solar_direct_kw"))
    sol_pot = np.asarray(d["solar_potential_kw"], dtype=np.float32) if ("solar_potential_kw" in d and len(d["solar_potential_kw"]) == n) else sol_gen
    bess_dis = _vec(d.get("bess_discharge_kw"))
    bess_chg = _vec(d.get("bess_charge_total_kw"))
    gen_out = _vec(d.get("gen_output_kw"))
    zeros = np.zeros(n, dtype=np.float32)

    cap_kwh = float(getattr(snap.system_config, "battery_capacity_kwh", 0.0) or 0.0)
    bess_kwh = (soc_arr / np.float32(100.0)) * np.float32(cap_kwh)

    return CombinedSimulationResult(
        system_config=snap.system_config,
        rules_config=snap.rules_config,
        solar_derivation=snap.solar_derivation,
        kpis=snap.kpis,
        timestamps=ts_idx,
        load_kw=load_arr,
        solar_gen_kw=sol_gen,
        solar_direct_kw=sol_dir,
        solar_surplus_kw=np.maximum(np.float32(0.0), sol_gen - sol_dir),
        solar_export_kw=zeros,
        bess_charge_solar_kw=bess_chg,
        bess_charge_grid_kw=zeros,
        bess_charge_gen_kw=zeros,
        bess_discharge_kw=bess_dis,
        bess_soc_pct=soc_arr,
        bess_energy_kwh=bess_kwh,
        gen_output_kw=gen_out,
        gen_to_load_kw=gen_out,
        gen_to_bess_kw=zeros,
        gen_fuel_step=zeros,
        gen_running_mask=(gen_out > 0.05),
        grid_import_kw=grid_imp,
        unmet_overload_kw=unmet_arr,
        is_gap=is_gap_arr,
        solar_potential_kw=sol_pot,
        monthly_balance_df=snap.monthly_balance_df,
        financial_config=snap.financial_config,
        financial_kpis=snap.financial_kpis,
        monthly_cost_df=snap.monthly_cost_df,
        cashflow_15y_df=snap.cashflow_15y_df,
    )
