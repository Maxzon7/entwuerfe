"""
========================================================================================
Explicit Simulation Assumptions Banner (contract/assumptions_banner.py)
========================================================================================

Renders a structured, collapsible "Active Tariff, Grid & BESS Assumptions" Register
directly below the top control bar in both Currentsituation_sandbox and BESS_sandbox.
Also provides structured assumption dictionaries for inclusion on exported PDF reports.
========================================================================================
"""

from typing import Dict, Any, Optional, List
import numpy as np
import streamlit as st


def build_assumptions_register_dict(
    dataset_label: str = "Active Facility Profile",
    total_steps: int = 35040,
    measured_days: float = 365.0,
    total_energy_kwh: float = 0.0,
    peak_demand_kw: float = 0.0,
    currency_code: str = "EUR",
    market_mode_label: str = "Unbundled 4-Pillar Market (Netherlands / EU)",
    dso_name: str = "Enexis Netbeheer B.V.",
    grid_tier: str = "MS-D (125 t/m 1.500 kW)",
    contracted_capacity_kw: float = 250.0,
    rate_contracted_capacity: float = 2.4400,
    rate_peak_demand: float = 3.7100,
    peak_penalty_rate_kw: float = 0.2500,
    supplier_name: str = "Vattenfall Zakelijk",
    commodity_summary: str = "HT (07:00-23:00 Mo-Fr): 0.1340 / NT: 0.1180",
    vat_rate_pct: float = 21.0,
    enable_p1: bool = True,
    enable_p2: bool = True,
    enable_p3: bool = True,
    enable_p4: bool = True,
    bess_assumptions: Optional[Dict[str, Any]] = None,
    # Object-based convenience arguments (used by view.py and BESS_sandbox/app.py)
    load_series: Optional[Any] = None,
    config: Optional[Any] = None,
    source_filename: Optional[str] = None,
    bess_config: Optional[Any] = None,
) -> Dict[str, List[Dict[str, str]]]:
    """
    Constructs a structured dictionary of active assumptions across 3 categories:
      1. Load & Period Assumptions
      2. Grid & Tariff Assumptions
      3. Battery Physics Assumptions (optional, when BESS is active)
    Accepts either explicit scalar parameters or domain objects (`load_series`, `config`,
    `source_filename`, `bess_config`).
    """
    if source_filename is not None:
        dataset_label = str(source_filename)

    if load_series is not None:
        if hasattr(load_series, "power_kw"):
            total_steps = len(load_series.power_kw)
        total_energy_kwh = float(getattr(load_series, "total_energy_kwh", total_energy_kwh))
        peak_demand_kw = float(getattr(load_series, "peak_demand_kw", peak_demand_kw))
        measured_days = float(getattr(load_series, "measured_days", total_steps * 0.25 / 24.0))

    if config is not None:
        currency_code = str(getattr(config, "currency_code", currency_code) or "EUR")
        enable_p1 = bool(getattr(config, "enable_pillar_1_supplier", enable_p1))
        enable_p2 = bool(getattr(config, "enable_pillar_2_dso", enable_p2))
        enable_p3 = bool(getattr(config, "enable_pillar_3_metering", enable_p3))
        enable_p4 = bool(getattr(config, "enable_pillar_4_taxes", enable_p4))

        mode_raw = str(getattr(config, "market_mode", "unbundled_4_pillar"))
        if mode_raw == "single_utility":
            market_mode_label = "Integrated Single-Utility Bill (Bundled DSO)"
        elif mode_raw == "custom":
            market_mode_label = "Custom Pillar Configuration"
        else:
            market_mode_label = "Unbundled 4-Pillar Market (Netherlands / EU)"

        dso_obj = getattr(config, "dso", None)
        if dso_obj is not None:
            dso_name = str(getattr(dso_obj, "dso_name", dso_name))
            grid_tier = str(getattr(dso_obj, "grid_tier", grid_tier))
            contracted_capacity_kw = float(getattr(dso_obj, "contracted_capacity_kw", contracted_capacity_kw))
            rate_contracted_capacity = float(getattr(dso_obj, "rate_contracted_capacity", rate_contracted_capacity))
            rate_peak_demand = float(getattr(dso_obj, "rate_peak_demand", rate_peak_demand))
            peak_penalty_rate_kw = float(getattr(dso_obj, "peak_penalty_rate_kw", peak_penalty_rate_kw))

        supp_obj = getattr(config, "supplier", None)
        if supp_obj is not None:
            supplier_name = str(getattr(supp_obj, "supplier_name", supplier_name))
            p_mode = getattr(supp_obj, "pricing_mode", None)
            p_mode_val = p_mode.value if hasattr(p_mode, "value") else str(p_mode)
            if p_mode_val == "dynamic":
                margin = float(getattr(supp_obj, "supplier_margin_kwh", 0.0))
                commodity_summary = f"EPEX Day-Ahead Spot + {currency_code} {margin:.4f}/kWh"
            elif getattr(supp_obj, "is_dual_rate", False):
                ht = float(getattr(supp_obj, "fixed_rate_peak_kwh", 0.0))
                nt = float(getattr(supp_obj, "fixed_rate_offpeak_kwh", 0.0))
                commodity_summary = f"Dual TOU (HT: {currency_code} {ht:.4f} / NT: {currency_code} {nt:.4f}/kWh)"
            else:
                flat = float(getattr(supp_obj, "fixed_rate_kwh", 0.0))
                commodity_summary = f"Fixed Flat Rate ({currency_code} {flat:.4f}/kWh)"

        lev_obj = getattr(config, "levies", None)
        if lev_obj is not None:
            vat_rate_pct = float(getattr(lev_obj, "vat_rate_pct", vat_rate_pct))

    if bess_config is not None and bess_assumptions is None:
        bess_assumptions = {
            "capacity_kwh": float(getattr(bess_config, "capacity_kwh", 100.0)),
            "soc_min_pct": float(getattr(bess_config, "soc_min_pct", 10.0)),
            "soc_max_pct": float(getattr(bess_config, "soc_max_pct", 95.0)),
            "max_discharge_kw": float(getattr(bess_config, "max_discharge_power_kw", 50.0)),
            "max_charge_kw": float(getattr(bess_config, "max_charge_power_kw", 50.0)),
            "rte_pct": float(getattr(bess_config, "round_trip_efficiency_pct", 90.0)),
            "target_grid_limit_kw": float(getattr(bess_config, "peak_shaving_threshold_kw", contracted_capacity_kw)),
        }
    is_projected = (measured_days < 350.0 and total_steps == 35040)
    proj_note = (
        f"Normalized to 365 days (35,040 steps @ 15-min) from {measured_days:.0f}-day recording"
        if is_projected
        else f"{measured_days:.0f} days ({total_steps:,} intervals @ 15-min, dt = 0.25 h)"
    )

    active_pillars_list = []
    if enable_p1:
        active_pillars_list.append("P1: Supply")
    else:
        active_pillars_list.append("P1: Bypassed")
    if enable_p2:
        active_pillars_list.append("P2: Grid/Utility")
    else:
        active_pillars_list.append("P2: Bypassed")
    if enable_p3:
        active_pillars_list.append("P3: Metering")
    else:
        active_pillars_list.append("P3: Bypassed")
    if enable_p4:
        active_pillars_list.append("P4: Taxes")
    else:
        active_pillars_list.append("P4: Bypassed")

    overload_kw = max(0.0, peak_demand_kw - contracted_capacity_kw)
    overload_str = f"+{overload_kw:,.1f} kW Exceedance" if overload_kw > 0.05 else "0.0 kW (Within Limit)"

    reg: Dict[str, List[Dict[str, str]]] = {
        "load_and_period": [
            {"parameter": "Source Load Dataset", "value": str(dataset_label)},
            {"parameter": "Time Resolution & Horizon", "value": proj_note},
            {"parameter": "Total Active Energy", "value": f"{total_energy_kwh:,.0f} kWh"},
            {"parameter": "Measured Peak Demand", "value": f"{peak_demand_kw:,.1f} kW ({overload_str})"},
        ],
        "grid_and_tariff": [
            {"parameter": "Market Structure Mode", "value": f"{market_mode_label} ({', '.join(active_pillars_list)})"},
            {"parameter": "Grid / Utility & Tier", "value": f"{dso_name} — {grid_tier}"},
            {"parameter": "Contracted Grid Capacity", "value": f"{contracted_capacity_kw:,.1f} kW @ {currency_code} {rate_contracted_capacity:,.4f}/kW/mo"},
            {"parameter": "Peak Demand & Breach Rate", "value": f"Peak: {currency_code} {rate_peak_demand:,.4f}/kW/mo | Penalty: {currency_code} {peak_penalty_rate_kw:,.2f}/kW"},
            {"parameter": "Energy Supply & VAT", "value": f"{supplier_name if enable_p1 else 'Bundled in Utility (P2)'} | {commodity_summary} | VAT: {vat_rate_pct:.1f}%"},
        ],
    }

    if bess_assumptions:
        cap_kwh = float(bess_assumptions.get("capacity_kwh", 100.0))
        soc_min = float(bess_assumptions.get("soc_min_pct", 10.0))
        soc_max = float(bess_assumptions.get("soc_max_pct", 95.0))
        dod_pct = max(10.0, soc_max - soc_min)
        usable_kwh = cap_kwh * (dod_pct / 100.0)
        dis_kw = float(bess_assumptions.get("max_discharge_kw", 50.0))
        chg_kw = float(bess_assumptions.get("max_charge_kw", 50.0))
        c_rate = dis_kw / max(1.0, cap_kwh)
        rte_pct = float(bess_assumptions.get("rte_pct", 90.0))
        eta_one_way = float(np.sqrt(max(0.5, rte_pct / 100.0)) * 100.0)
        target_kw = float(bess_assumptions.get("target_grid_limit_kw", contracted_capacity_kw))

        reg["battery_physics"] = [
            {"parameter": "Gross Nameplate & Usable DoD", "value": f"{cap_kwh:,.1f} kWh Gross | {usable_kwh:,.1f} kWh Usable ({soc_min:.0f}%–{soc_max:.0f}% SoC, {dod_pct:.0f}% DoD)"},
            {"parameter": "Inverter Power Rating (C-Rate)", "value": f"Discharge: {dis_kw:,.1f} kW / Charge: {chg_kw:,.1f} kW ({c_rate:.2f} C)"},
            {"parameter": "Round-Trip Efficiency (RTE)", "value": f"{rte_pct:.1f}% Total (One-Way Charge/Discharge: {eta_one_way:.2f}%)"},
            {"parameter": "Dispatch Strategy", "value": f"Greedy Peak Shaving at {target_kw:,.1f} kW Grid Limit (Opportunistic Headroom Recharge)"},
        ]

    return reg


def render_assumptions_banner(
    assumptions_dict: Dict[str, List[Dict[str, str]]],
    expanded: bool = False,
    title: str = ":material/fact_check: Active Tariff, Grid & BESS Simulation Assumptions Register",
) -> None:
    """
    Renders the Explicit Simulation Assumptions Banner in a clean collapsible card.
    Never uses 4+ leading spaces in HTML strings to prevent Markdown code-block escaping.
    """
    has_bess = "battery_physics" in assumptions_dict and bool(assumptions_dict["battery_physics"])

    with st.expander(title, expanded=expanded):
        if has_bess:
            c1, c2, c3 = st.columns(3, gap="medium")
        else:
            c1, c2 = st.columns(2, gap="large")
            c3 = None

        def _render_category_card(col_obj: Any, header: str, accent: str, items: List[Dict[str, str]]) -> None:
            rows_html = []
            for item in items:
                rows_html.append(
                    f'<div style="display:flex; justify-content:space-between; border-bottom:1px solid #1e293b; padding:5px 0; font-size:0.82rem;">'
                    f'<span style="color:#94a3b8; font-weight:500; padding-right:8px;">{item["parameter"]}:</span>'
                    f'<span style="color:#f1f5f9; font-weight:600; text-align:right;">{item["value"]}</span>'
                    f'</div>'
                )
            body = "\n".join(rows_html)
            html_box = (
                f'<div style="background-color:#0f172a; border:1px solid #334155; border-top:3px solid {accent}; border-radius:6px; padding:10px 14px; height:100%;">\n'
                f'<div style="font-size:0.80rem; font-weight:700; color:{accent}; text-transform:uppercase; letter-spacing:0.04em; margin-bottom:8px;">{header}</div>\n'
                f'{body}\n'
                f'</div>'
            )
            with col_obj:
                st.markdown(html_box, unsafe_allow_html=True)

        _render_category_card(
            c1,
            "1. Load & Period Assumptions",
            "#38bdf8",
            assumptions_dict.get("load_and_period", [])
        )
        _render_category_card(
            c2,
            "2. Grid & Tariff Assumptions",
            "#f59e0b",
            assumptions_dict.get("grid_and_tariff", [])
        )
        if has_bess and c3 is not None:
            _render_category_card(
                c3,
                "3. Battery Physics Assumptions",
                "#10b981",
                assumptions_dict.get("battery_physics", [])
            )

