"""
Subtab 6.1 (Electricity Bill & Grid Tariffs) view reusing Currentsituation_sandbox's
Unbundled 4-Pillar and Integrated Single-Utility (EDEMSA ARS) bill structure inside @st.fragment.
"""

import pandas as pd
import streamlit as st

from .state_and_helpers import (
    CombinedSystemConfig,
    CombinedFinancialConfig,
    evaluate_combined_financials,
    get_dso_preset_options,
    get_supplier_preset_options,
    get_metering_preset_options,
    apply_utility_tariff_presets,
    sync_financial_config_from_status_quo,
)
from .subtab6_isolated_pillars import (
    _curr_prefix,
    _fmt_curr,
    _render_sub_ledger_html,
    _render_monthly_grid_bill_progression_fragment,
    _render_isolated_pillar_deep_dive_fragment,
)

BILL_MODE_OPTIONS = [
    "Separate Suppliers (4-Part Bill — NL / EU)",
    "Single Utility Company (1 Combined Bill — Argentina EDEMSA)",
    "Custom Bill Parts",
]


def _bill_mode_label_for_cfg(cur_fin: CombinedFinancialConfig) -> str:
    mode = str(getattr(cur_fin, "market_mode", "unbundled_4_pillar")).lower()
    if "single" in mode:
        return BILL_MODE_OPTIONS[1]
    if "custom" in mode:
        return BILL_MODE_OPTIONS[2]
    return BILL_MODE_OPTIONS[0]


def _queue_fin_cfg_widget_sync(cur_fin: CombinedFinancialConfig) -> None:
    """Queues CombinedFinancialConfig values to be applied safely before 6.1 widgets render."""
    st.session_state["comb_pending_fin_widget_sync"] = {
        "comb_fin_bill_mode_sel": _bill_mode_label_for_cfg(cur_fin),
        "comb_fin_curr_sel": str(getattr(cur_fin, "currency_code", "EUR") or "EUR"),
        "comb_fin_en_p1_chk": bool(cur_fin.enable_pillar_1_supplier),
        "comb_fin_en_p2_chk": bool(cur_fin.enable_pillar_2_dso),
        "comb_fin_en_p3_chk": bool(cur_fin.enable_pillar_3_metering),
        "comb_fin_en_p4_chk": bool(cur_fin.enable_pillar_4_taxes),
        "comb_fin_supp_mode": (
            "Dual TOU Rate (Peak HT / Off-Peak NT)"
            if cur_fin.supplier_pricing_mode == "dual_tou"
            else "Single Flat Rate"
        ),
        "comb_fin_supp_kwh": float(cur_fin.supplier_energy_price_eur_kwh),
        "comb_fin_supp_ht": float(cur_fin.supplier_peak_ht_eur_kwh),
        "comb_fin_supp_nt": float(cur_fin.supplier_offpeak_nt_eur_kwh),
        "comb_fin_supp_gvo": float(cur_fin.supplier_gvo_surcharge_eur_kwh),
        "comb_fin_supp_fix": float(cur_fin.supplier_fixed_fee_eur_month),
        "comb_fin_dso_conn": float(cur_fin.dso_connection_fee_eur_month),
        "comb_fin_dso_fix": float(cur_fin.dso_fixed_fee_eur_month),
        "comb_fin_dso_cap": float(cur_fin.dso_capacity_fee_eur_kw_month),
        "comb_fin_dso_peak": float(cur_fin.dso_peak_demand_fee_eur_kw_month),
        "comb_fin_dso_vol": float(cur_fin.dso_transport_eur_kwh),
        "comb_fin_dso_3win_chk": bool(cur_fin.dso_enable_three_window_tou),
        "comb_fin_dso_pen": float(cur_fin.grid_overload_penalty_eur_kw),
        "comb_fin_dso_pen_chk": bool(cur_fin.dso_enable_excess_capacity_penalty),
        "comb_fin_dso_breach_adj": bool(cur_fin.dso_adjust_capacity_on_breach),
        "comb_fin_dso_pico_only": bool(cur_fin.dso_bill_peak_on_pico_only),
        "comb_fin_dso_reg_adj": float(cur_fin.dso_regulatory_adjustments_eur_month),
        "comb_fin_avoided_trafo": float(cur_fin.avoided_transformer_rent_eur_month),
        "comb_fin_meter_fix": float(cur_fin.metering_fixed_fee_eur_month),
        "comb_fin_tax_kwh": float(cur_fin.energy_tax_eur_kwh),
        "comb_fin_tax_pct": float(cur_fin.tax_surcharge_pct),
        "comb_fin_tax_credit": float(cur_fin.annual_tax_reduction_credit_eur),
        "comb_fin_vat_pct": float(cur_fin.vat_rate_pct),
        "comb_fin_vat_levies_chk": bool(cur_fin.vat_applies_to_levies),
        "comb_fin_dso_tou_v": int(st.session_state.get("comb_fin_dso_tou_v", 0)) + 1,
    }


def _apply_pending_fin_widget_sync() -> None:
    """Applies any pending Subtab 6.1 widget values prior to widget instantiation."""
    pending = st.session_state.pop("comb_pending_fin_widget_sync", None)
    if isinstance(pending, dict):
        for sk, sv in pending.items():
            st.session_state[sk] = sv


def _build_dso_tou_editor_df(cur_fin: CombinedFinancialConfig) -> pd.DataFrame:
    """Builds the 2-window (HT/NT) or 3-window (Pico/Valle/Resto) rate editor table."""
    r_pk = (
        float(cur_fin.dso_transport_peak_eur_kwh)
        if cur_fin.dso_transport_peak_eur_kwh is not None
        else float(cur_fin.dso_transport_eur_kwh)
    )
    r_off = (
        float(cur_fin.dso_transport_offpeak_eur_kwh)
        if cur_fin.dso_transport_offpeak_eur_kwh is not None
        else float(cur_fin.dso_transport_eur_kwh)
    )
    r_sh = (
        float(cur_fin.dso_transport_shoulder_eur_kwh)
        if float(cur_fin.dso_transport_shoulder_eur_kwh) > 0.0
        else float(cur_fin.dso_transport_eur_kwh)
    )
    if cur_fin.dso_enable_three_window_tou:
        return pd.DataFrame([
            {"Window": "Peak / Pico", "Rate": r_pk, "Hours": "18:00–23:00"},
            {"Window": "Off-Peak / Valle", "Rate": r_off, "Hours": "23:00–05:00"},
            {"Window": "Shoulder / Resto", "Rate": r_sh, "Hours": "05:00–18:00"},
        ])
    return pd.DataFrame([
        {"Window": "Peak Hours (HT)", "Rate": r_pk, "Hours": "07:00–23:00 (Mon–Fri)"},
        {"Window": "Off-Peak Hours (NT)", "Rate": r_off, "Hours": "23:00–07:00 & Weekends"},
    ])


def _render_subtab6_1_bill_setup_controls(
    sim_res,
    cur_sys: CombinedSystemConfig,
    cur_fin: CombinedFinancialConfig,
) -> None:
    """Renders Grid Congestion Lock, Currentsituation Sync, Bill Structure selector & Utility Presets."""
    fk_live = sim_res.financial_kpis
    curr = str(getattr(cur_fin, "currency_code", "EUR") or "EUR")

    # 1. Grid Congestion Lock & Optional Sync from Current Situation Sandbox
    with st.container(border=True):
        cg1, cg2 = st.columns([0.55, 0.45])
        with cg1:
            strict_cong = st.toggle(
                "Strict Grid Congestion Lock: No Grid Upgrade or Contract Breach Allowed",
                value=bool(cur_fin.strict_grid_congestion_mode),
                key="comb_strict_congestion_toggle",
                help=(
                    "Enable when the local grid is congested and exceeding contracted capacity or "
                    "buying a grid upgrade is impossible. Sets avoided grid upgrade credits to 0."
                ),
            )
            if bool(strict_cong) != bool(cur_fin.strict_grid_congestion_mode):
                cur_fin.strict_grid_congestion_mode = bool(strict_cong)
                if cur_fin.strict_grid_congestion_mode:
                    cur_fin.avoided_grid_upgrade_capex_eur = 0.0
                    st.session_state["comb_fin_avoided_upgrade"] = 0.0
                evaluate_combined_financials(sim_res, cur_fin)
                st.session_state.pop("comb_cached_excel_bytes", None)
                st.rerun(scope="fragment")
        with cg2:
            if cur_fin.strict_grid_congestion_mode:
                if fk_live is not None and fk_live.grid_congestion_compliant:
                    st.success(
                        f":material/verified: **COMPLIANT:** Peak stays within the {cur_sys.grid_limit_kw:,.0f} kW limit all year."
                    )
                else:
                    br_kw = fk_live.grid_congestion_breach_kw if fk_live is not None else 0.0
                    br_mo = fk_live.grid_congestion_breach_months if fk_live is not None else 0
                    st.error(
                        f":material/gpp_bad: **VIOLATION:** Peak exceeds limit by **+{br_kw:,.1f} kW** "
                        f"in **{br_mo} month(s)**. Increase Battery or Generator support."
                    )
            else:
                st.caption(
                    ":material/info: Grid Congestion Lock is off. Turn it on if exceeding your grid limit is prohibited."
                )

        snap = st.session_state.get("shared_baseline_snapshot")
        if isinstance(snap, dict) and snap.get("config") is not None:
            sc_l, sc_btn = st.columns([0.68, 0.32])
            with sc_l:
                st.caption(
                    f":material/link: Found saved contract in **Current Situation Sandbox** "
                    f"(`{snap.get('site_label', 'Active Contract')}`)."
                )
            with sc_btn:
                if st.button(
                    "Sync Contract from Current Situation",
                    icon=":material/sync:",
                    use_container_width=True,
                    key="comb_btn_sync_currsit_contract",
                ):
                    sync_financial_config_from_status_quo(snap["config"], cur_fin)
                    _queue_fin_cfg_widget_sync(cur_fin)
                    evaluate_combined_financials(sim_res, cur_fin)
                    st.session_state.pop("comb_cached_excel_bytes", None)
                    st.rerun(scope="fragment")

    # 2. Bill Structure & Currency Bar (Separate 4-Part vs Single Utility Argentina vs Custom)
    with st.container(border=True):
        bm_c1, bm_c2 = st.columns([0.72, 0.28])
        cur_mode_lbl = _bill_mode_label_for_cfg(cur_fin)
        if st.session_state.get("comb_fin_bill_mode_sel") not in BILL_MODE_OPTIONS:
            st.session_state["comb_fin_bill_mode_sel"] = cur_mode_lbl
        with bm_c1:
            sel_bill_mode = st.selectbox(
                "Bill Structure (Who is on your electricity bill?)",
                options=BILL_MODE_OPTIONS,
                index=BILL_MODE_OPTIONS.index(st.session_state["comb_fin_bill_mode_sel"]),
                key="comb_fin_bill_mode_sel",
                help=(
                    "Separate Suppliers: Standard 4-part NL/EU bill (Supplier + Grid + Metering + Taxes). "
                    "Single Utility Company: Skips separate Supplier & Metering (e.g. Argentina EDEMSA)."
                ),
            )
        curr_opts = ["EUR", "ARS", "USD"]
        if st.session_state.get("comb_fin_curr_sel") not in curr_opts:
            st.session_state["comb_fin_curr_sel"] = curr if curr in curr_opts else "EUR"
        with bm_c2:
            sel_curr = st.selectbox(
                "Currency",
                options=curr_opts,
                index=curr_opts.index(st.session_state["comb_fin_curr_sel"]),
                key="comb_fin_curr_sel",
            )

        changed_mode = False
        if sel_curr != cur_fin.currency_code:
            cur_fin.currency_code = sel_curr
            changed_mode = True

        target_mode_code = (
            "single_utility"
            if sel_bill_mode.startswith("Single")
            else ("custom" if sel_bill_mode.startswith("Custom") else "unbundled_4_pillar")
        )
        if target_mode_code != cur_fin.market_mode:
            cur_fin.market_mode = target_mode_code
            if target_mode_code == "single_utility":
                cur_fin.enable_pillar_1_supplier = False
                cur_fin.enable_pillar_2_dso = True
                cur_fin.enable_pillar_3_metering = False
                cur_fin.enable_pillar_4_taxes = True
            elif target_mode_code == "unbundled_4_pillar":
                cur_fin.enable_pillar_1_supplier = True
                cur_fin.enable_pillar_2_dso = True
                cur_fin.enable_pillar_3_metering = True
                cur_fin.enable_pillar_4_taxes = True
            changed_mode = True

        if target_mode_code == "single_utility":
            st.caption(
                ":material/layers_clear: **Single Utility Bill Active:** Separate **Energy Supplier** and **Metering** "
                "charges are bypassed (`0.00`) because electricity supply & grid delivery are combined under Section A."
            )
        elif target_mode_code == "custom":
            ck1, ck2, ck3, ck4 = st.columns(4)
            with ck1:
                c_p2 = st.checkbox("Include Grid / Utility", value=bool(cur_fin.enable_pillar_2_dso), key="comb_fin_en_p2_chk")
            with ck2:
                c_p1 = st.checkbox("Include Energy Supplier", value=bool(cur_fin.enable_pillar_1_supplier), key="comb_fin_en_p1_chk")
            with ck3:
                c_p3 = st.checkbox("Include Metering", value=bool(cur_fin.enable_pillar_3_metering), key="comb_fin_en_p3_chk")
            with ck4:
                c_p4 = st.checkbox("Include Taxes & VAT", value=bool(cur_fin.enable_pillar_4_taxes), key="comb_fin_en_p4_chk")
            if (c_p1, c_p2, c_p3, c_p4) != (
                bool(cur_fin.enable_pillar_1_supplier),
                bool(cur_fin.enable_pillar_2_dso),
                bool(cur_fin.enable_pillar_3_metering),
                bool(cur_fin.enable_pillar_4_taxes),
            ):
                cur_fin.enable_pillar_1_supplier = bool(c_p1)
                cur_fin.enable_pillar_2_dso = bool(c_p2)
                cur_fin.enable_pillar_3_metering = bool(c_p3)
                cur_fin.enable_pillar_4_taxes = bool(c_p4)
                changed_mode = True

        if changed_mode:
            _queue_fin_cfg_widget_sync(cur_fin)
            evaluate_combined_financials(sim_res, cur_fin)
            st.session_state.pop("comb_cached_excel_bytes", None)
            st.rerun(scope="fragment")

    # 3. Utility Presets Expander
    with st.expander(":material/account_balance: Utility Presets", expanded=False):
        with st.form("comb_utility_preset_form"):
            dso_opts = get_dso_preset_options()
            supp_opts = get_supplier_preset_options()
            meter_opts = get_metering_preset_options()

            dso_list = list(dso_opts.keys())
            supp_list = list(supp_opts.keys())
            meter_list = list(meter_opts.keys())
            for _sk, _opts in [
                ("comb_preset_dso_sel", dso_list),
                ("comb_preset_supp_sel", supp_list),
                ("comb_preset_meter_sel", meter_list),
            ]:
                if _sk in st.session_state and st.session_state[_sk] not in _opts:
                    st.session_state.pop(_sk, None)

            en_p1 = bool(cur_fin.enable_pillar_1_supplier)
            en_p3 = bool(cur_fin.enable_pillar_3_metering)

            u_c1, u_c2, u_c3, u_btn = st.columns([1.3, 1.3, 1.3, 1.1])
            with u_c1:
                sel_dso = st.selectbox("Grid Operator (DSO)", options=dso_list, index=0, key="comb_preset_dso_sel")
                tier_list = dso_opts.get(sel_dso, ["MV-D (125 to 1,500 kW)"])
                if st.session_state.get("comb_preset_tier_sel") not in tier_list:
                    st.session_state.pop("comb_preset_tier_sel", None)
                sel_tier = st.selectbox("Voltage & Capacity Tier", options=tier_list, index=0, key="comb_preset_tier_sel")
            with u_c2:
                sel_supp = st.selectbox(
                    "Energy Supplier",
                    options=supp_list,
                    index=0,
                    key="comb_preset_supp_sel",
                    disabled=not en_p1,
                )
                plan_list = supp_opts.get(sel_supp, ["Fixed 1-Year (Dual TOU HT/NT)"])
                if st.session_state.get("comb_preset_plan_sel") not in plan_list:
                    st.session_state.pop("comb_preset_plan_sel", None)
                sel_plan = st.selectbox(
                    "Contract Tariff Plan",
                    options=plan_list,
                    index=0,
                    key="comb_preset_plan_sel",
                    disabled=not en_p1,
                )
                if not en_p1:
                    st.caption(":material/layers_clear: *Bypassed in Single Utility mode*")
            with u_c3:
                sel_meter = st.selectbox(
                    "Metering Company",
                    options=meter_list,
                    index=0,
                    key="comb_preset_meter_sel",
                    disabled=not en_p3,
                )
                m_plan_list = meter_opts.get(sel_meter, ["15-Min Interval Telemetry MV (Large Consumer)"])
                if st.session_state.get("comb_preset_mplan_sel") not in m_plan_list:
                    st.session_state.pop("comb_preset_mplan_sel", None)
                sel_m_plan = st.selectbox(
                    "Metering Package",
                    options=m_plan_list,
                    index=0,
                    key="comb_preset_mplan_sel",
                    disabled=not en_p3,
                )
                if not en_p3:
                    st.caption(":material/layers_clear: *Included in Single Utility bill*")
            with u_btn:
                st.write("")
                st.write("")
                apply_tariffs = st.form_submit_button(
                    "Load Selected Utility Tariffs",
                    icon=":material/download:",
                    type="primary",
                    use_container_width=True,
                )

        if apply_tariffs:
            apply_utility_tariff_presets(
                dso_choice=sel_dso,
                tier_choice=sel_tier,
                supp_choice=sel_supp,
                supp_plan=sel_plan,
                meter_choice=sel_meter,
                meter_tier=sel_m_plan,
                fin_cfg=cur_fin,
            )
            _queue_fin_cfg_widget_sync(cur_fin)
            evaluate_combined_financials(sim_res, cur_fin)
            st.session_state.pop("comb_cached_excel_bytes", None)
            st.rerun(scope="fragment")


def _render_subtab6_1_grid_tariffs(
    sim_res,
    cur_sys: CombinedSystemConfig,
    cur_fin: CombinedFinancialConfig,
) -> None:
    """Sub-Tab 6.1: Electricity Bill & Grid Tariffs (Utility Presets, Zone A Tariff Inputs & Zone B Bill Summary)."""
    _apply_pending_fin_widget_sync()
    _render_subtab6_1_bill_setup_controls(sim_res, cur_sys, cur_fin)

    curr = str(getattr(cur_fin, "currency_code", "EUR") or "EUR")
    c_lbl = "€" if curr == "EUR" else curr
    en_p1 = bool(cur_fin.enable_pillar_1_supplier)
    en_p2 = bool(cur_fin.enable_pillar_2_dso)
    en_p3 = bool(cur_fin.enable_pillar_3_metering)
    en_p4 = bool(cur_fin.enable_pillar_4_taxes)
    is_single_util = (not en_p1 and not en_p3)

    col_za, col_zb = st.columns([0.48, 0.52], gap="large")

    with col_za:
        st.markdown("##### :material/tune: 1. Tariff Rates")
        tou_v = int(st.session_state.get("comb_fin_dso_tou_v", 0))
        dso_tou_seed_df = _build_dso_tou_editor_df(cur_fin)

        with st.form("comb_tariff_inputs_form"):
            sec_a_title = (
                ":material/cable: A. Utility & Grid Contract (Single Bill)"
                if is_single_util
                else ":material/cable: A. Grid Operator Contract (DSO)"
            )
            with st.expander(sec_a_title, expanded=True):
                g1, g2 = st.columns(2)
                with g1:
                    dso_conn = st.number_input(
                        f"Fixed Connection Fee ({c_lbl}/month)",
                        min_value=0.0, max_value=10000000.0, value=float(cur_fin.dso_connection_fee_eur_month), step=10.0,
                        key="comb_fin_dso_conn", disabled=not en_p2,
                        help="Fixed monthly grid connection service fee.",
                    )
                    dso_fix = st.number_input(
                        f"Fixed Transport / Standing Fee ({c_lbl}/month)",
                        min_value=0.0, max_value=50000000.0, value=float(cur_fin.dso_fixed_fee_eur_month), step=10.0,
                        key="comb_fin_dso_fix", disabled=not en_p2,
                    )
                    dso_cap = st.number_input(
                        f"Booked Grid Capacity ({c_lbl}/kW/mo)",
                        min_value=0.0, max_value=1000000.0, value=float(cur_fin.dso_capacity_fee_eur_kw_month), step=0.25, format="%.4f",
                        key="comb_fin_dso_cap", disabled=not en_p2,
                        help="Charged monthly per kW of contracted Grid Limit.",
                    )
                with g2:
                    dso_peak = st.number_input(
                        f"Monthly Peak Demand ({c_lbl}/kW/mo)",
                        min_value=0.0, max_value=1000000.0, value=float(cur_fin.dso_peak_demand_fee_eur_kw_month), step=0.25, format="%.4f",
                        key="comb_fin_dso_peak", disabled=not en_p2,
                        help="Charged monthly on highest 15-min peak demand (or evening peak window if selected below).",
                    )
                    dso_pen = st.number_input(
                        f"Overload Penalty ({c_lbl}/kW above limit)",
                        min_value=0.0, max_value=1000000.0, value=float(cur_fin.grid_overload_penalty_eur_kw), step=1.0, format="%.2f",
                        key="comb_fin_dso_pen", disabled=not en_p2,
                    )
                    avoided_trafo = st.number_input(
                        f"Avoided Transformer Rental ({c_lbl}/mo)",
                        min_value=0.0, max_value=50000000.0, value=float(cur_fin.avoided_transformer_rent_eur_month), step=50.0,
                        key="comb_fin_avoided_trafo", disabled=not en_p2,
                        help="Monthly transformer rent saved when staying within contracted capacity.",
                    )

                st.markdown(f"**Energy Delivery / Transport Rates ({c_lbl}/kWh)**")
                dso_3win_chk = st.checkbox(
                    "Use 3 Time Windows (Evening Peak / Night / Daytime — e.g. EDEMSA)",
                    value=bool(cur_fin.dso_enable_three_window_tou),
                    key="comb_fin_dso_3win_chk",
                    disabled=not en_p2,
                )
                edited_dso_tou = st.data_editor(
                    dso_tou_seed_df,
                    use_container_width=True,
                    hide_index=True,
                    disabled=not en_p2,
                    column_config={
                        "Window": st.column_config.TextColumn("Time Window", disabled=True),
                        "Rate": st.column_config.NumberColumn(
                            f"Rate ({c_lbl}/kWh)", min_value=0.0, max_value=10000.0, step=0.001, format="%.6f", required=True
                        ),
                        "Hours": st.column_config.TextColumn("Hours", disabled=True),
                    },
                    key=f"comb_fin_dso_tou_editor_v{tou_v}",
                )

                r_adj1, r_adj2 = st.columns(2)
                with r_adj1:
                    dso_reg_adj = st.number_input(
                        f"Monthly Utility Adjustments ({c_lbl}/month)",
                        min_value=-100000000.0, max_value=100000000.0, value=float(cur_fin.dso_regulatory_adjustments_eur_month), step=100.0, format="%.2f",
                        key="comb_fin_dso_reg_adj", disabled=not en_p2,
                        help="Monthly utility pass-through charges or seasonal adjustments (e.g. EDEMSA monthly adjustments).",
                    )
                with r_adj2:
                    dso_pen_chk = st.checkbox(
                        "Charge Overload Penalty Above Limit",
                        value=bool(cur_fin.dso_enable_excess_capacity_penalty),
                        key="comb_fin_dso_pen_chk", disabled=not en_p2,
                    )
                    dso_breach_adj = st.checkbox(
                        "Step Up Booked Capacity in Breach Months",
                        value=bool(cur_fin.dso_adjust_capacity_on_breach),
                        key="comb_fin_dso_breach_adj", disabled=not en_p2,
                        help="When enabled, any monthly peak above contracted capacity steps up billed capacity for that month.",
                    )
                    dso_pico_only = st.checkbox(
                        "Bill Peak Demand Only in Evening Peak Window (EDEMSA T2 Rule)",
                        value=bool(cur_fin.dso_bill_peak_on_pico_only),
                        key="comb_fin_dso_pico_only", disabled=not en_p2,
                    )

            b_title = (
                ":material/bolt: B. Energy Supplier [Bypassed — In Section A] & Solar Export"
                if not en_p1
                else ":material/bolt: B. Energy Supplier & Solar Export"
            )
            with st.expander(b_title, expanded=en_p1):
                if not en_p1:
                    st.info(
                        ":material/visibility_off: **Included in Utility Bill (Section A):** Separate energy supplier charges "
                        "evaluate to **0.00** because energy supply is already included in the Single Utility contract above."
                    )
                _mode_options = ["Single Flat Rate", "Dual TOU Rate (Peak HT / Off-Peak NT)"]
                if st.session_state.get("comb_fin_supp_mode") not in _mode_options:
                    st.session_state["comb_fin_supp_mode"] = (
                        "Dual TOU Rate (Peak HT / Off-Peak NT)"
                        if cur_fin.supplier_pricing_mode == "dual_tou"
                        else "Single Flat Rate"
                    )
                supp_mode = st.radio(
                    "Supplier Pricing Structure",
                    options=_mode_options,
                    horizontal=True,
                    key="comb_fin_supp_mode",
                    disabled=not en_p1,
                    help="Dual TOU bills Mon-Fri 07:00-23:00 at Peak HT Rate and nights/weekends at Off-Peak NT Rate.",
                )
                s1, s2, s3 = st.columns(3)
                with s1:
                    supp_kwh = st.number_input(
                        f"Single Rate ({c_lbl}/kWh)",
                        min_value=0.0, max_value=10000.0, value=float(cur_fin.supplier_energy_price_eur_kwh), step=0.01, format="%.3f",
                        key="comb_fin_supp_kwh", disabled=not en_p1,
                    )
                    supp_ht = st.number_input(
                        f"Peak HT Rate ({c_lbl}/kWh)",
                        min_value=0.0, max_value=10000.0, value=float(cur_fin.supplier_peak_ht_eur_kwh), step=0.01, format="%.3f",
                        key="comb_fin_supp_ht", disabled=not en_p1,
                    )
                with s2:
                    supp_nt = st.number_input(
                        f"Off-Peak NT Rate ({c_lbl}/kWh)",
                        min_value=0.0, max_value=10000.0, value=float(cur_fin.supplier_offpeak_nt_eur_kwh), step=0.01, format="%.3f",
                        key="comb_fin_supp_nt", disabled=not en_p1,
                    )
                    supp_gvo = st.number_input(
                        f"Green Cert. Surcharge ({c_lbl}/kWh)",
                        min_value=0.0, max_value=100.0, value=float(cur_fin.supplier_gvo_surcharge_eur_kwh), step=0.001, format="%.4f",
                        key="comb_fin_supp_gvo", disabled=not en_p1,
                    )
                with s3:
                    supp_fix = st.number_input(
                        f"Supplier Base Fee ({c_lbl}/mo)",
                        min_value=0.0, max_value=500000.0, value=float(cur_fin.supplier_fixed_fee_eur_month), step=10.0,
                        key="comb_fin_supp_fix", disabled=not en_p1,
                    )
                    solar_fi = st.number_input(
                        f"Solar Feed-in ({c_lbl}/kWh)",
                        min_value=0.0, max_value=10000.0, value=float(cur_fin.solar_export_feed_in_eur_kwh), step=0.01, format="%.3f",
                        key="comb_fin_solar_fi",
                        help="Revenue received per kWh of solar surplus exported to the grid.",
                    )

            with st.expander(":material/receipt: C. Metering, Taxes & VAT", expanded=not en_p1):
                if not en_p3:
                    st.caption(":material/layers_clear: *Metering is included in Section A (0.00).*")
                m1, m2 = st.columns(2)
                with m1:
                    meter_fix = st.number_input(
                        f"Metering Fee ({c_lbl}/mo)",
                        min_value=0.0, max_value=500000.0, value=float(cur_fin.metering_fixed_fee_eur_month), step=5.0,
                        key="comb_fin_meter_fix", disabled=not en_p3,
                    )
                    tax_kwh = st.number_input(
                        f"Energy Tax ({c_lbl}/kWh)",
                        min_value=0.0, max_value=10000.0, value=float(cur_fin.energy_tax_eur_kwh), step=0.005, format="%.4f",
                        key="comb_fin_tax_kwh", disabled=not en_p4,
                    )
                    tax_credit = st.number_input(
                        f"Annual Tax Credit ({c_lbl}/yr)",
                        min_value=0.0, max_value=10000000.0, value=float(cur_fin.annual_tax_reduction_credit_eur), step=50.0,
                        key="comb_fin_tax_credit", disabled=not en_p4,
                        help="Fixed statutory annual energy tax rebate deducted from Energy Tax.",
                    )
                with m2:
                    tax_pct = st.number_input(
                        "Extra / Municipal Tax Levies (%)",
                        min_value=0.0, max_value=100.0, value=float(cur_fin.tax_surcharge_pct), step=0.5, format="%.4f",
                        key="comb_fin_tax_pct", disabled=not en_p4,
                    )
                    vat_pct = st.number_input(
                        "VAT Rate (%)",
                        min_value=0.0, max_value=50.0, value=float(cur_fin.vat_rate_pct), step=1.0, format="%.1f",
                        key="comb_fin_vat_pct",
                    )
                    vat_on_levies = st.checkbox(
                        "Apply VAT on top of taxes & levies (Off for Argentina 27% IVA)",
                        value=bool(cur_fin.vat_applies_to_levies),
                        key="comb_fin_vat_levies_chk",
                        disabled=not en_p4,
                    )

            tariffs_submitted = st.form_submit_button(
                "Apply Grid & Electricity Tariffs",
                icon=":material/check_circle:",
                type="primary",
                use_container_width=True,
            )

        if tariffs_submitted:
            cur_fin.dso_connection_fee_eur_month = float(dso_conn)
            cur_fin.dso_fixed_fee_eur_month = float(dso_fix)
            cur_fin.dso_capacity_fee_eur_kw_month = float(dso_cap)
            cur_fin.dso_peak_demand_fee_eur_kw_month = float(dso_peak)
            cur_fin.dso_enable_three_window_tou = bool(dso_3win_chk)
            if edited_dso_tou is not None and not edited_dso_tou.empty:
                for row_t in edited_dso_tou.to_dict(orient="records"):
                    w_name = str(row_t.get("Window", "")).lower()
                    w_rate = float(row_t.get("Rate", 0.0))
                    if "shoulder" in w_name or "resto" in w_name:
                        cur_fin.dso_transport_shoulder_eur_kwh = w_rate
                    elif "off" in w_name or "valle" in w_name or "nt" in w_name:
                        cur_fin.dso_transport_offpeak_eur_kwh = w_rate
                    else:
                        cur_fin.dso_transport_peak_eur_kwh = w_rate
                cur_fin.dso_transport_eur_kwh = float(
                    cur_fin.dso_transport_shoulder_eur_kwh
                    if (dso_3win_chk and cur_fin.dso_transport_shoulder_eur_kwh > 0.0)
                    else (cur_fin.dso_transport_peak_eur_kwh or cur_fin.dso_transport_eur_kwh)
                )
            cur_fin.dso_regulatory_adjustments_eur_month = float(dso_reg_adj)
            cur_fin.grid_overload_penalty_eur_kw = float(dso_pen)
            cur_fin.dso_enable_excess_capacity_penalty = bool(dso_pen_chk)
            cur_fin.avoided_transformer_rent_eur_month = float(avoided_trafo)
            cur_fin.dso_adjust_capacity_on_breach = bool(dso_breach_adj)
            cur_fin.dso_bill_peak_on_pico_only = bool(dso_pico_only)

            cur_fin.supplier_pricing_mode = "dual_tou" if str(supp_mode).startswith("Dual") else "single"
            cur_fin.supplier_energy_price_eur_kwh = float(supp_kwh)
            cur_fin.supplier_peak_ht_eur_kwh = float(supp_ht)
            cur_fin.supplier_offpeak_nt_eur_kwh = float(supp_nt)
            cur_fin.supplier_gvo_surcharge_eur_kwh = float(supp_gvo)
            cur_fin.supplier_fixed_fee_eur_month = float(supp_fix)
            cur_fin.solar_export_feed_in_eur_kwh = float(solar_fi)

            cur_fin.metering_fixed_fee_eur_month = float(meter_fix)
            cur_fin.energy_tax_eur_kwh = float(tax_kwh)
            cur_fin.annual_tax_reduction_credit_eur = float(tax_credit)
            cur_fin.tax_surcharge_pct = float(tax_pct)
            cur_fin.vat_rate_pct = float(vat_pct)
            cur_fin.vat_applies_to_levies = bool(vat_on_levies)

            evaluate_combined_financials(sim_res, cur_fin)
            st.session_state["comb_fin_dso_tou_v"] = tou_v + 1
            st.session_state.pop("comb_cached_excel_bytes", None)
            st.rerun(scope="fragment")

    with col_zb:
        st.markdown("##### :material/receipt_long: 2. Annual Bill Summary")
        fk = sim_res.financial_kpis
        kpis = sim_res.kpis
        m_df = sim_res.monthly_cost_df
        c_pref = _curr_prefix(curr, html=True)

        base_kwh = float(kpis.annual_consumption_kwh)
        comb_kwh = float(kpis.grid_import_total_kwh)
        avg_base_pk = float(m_df["Current situation Peak (kW)"].mean()) if (not m_df.empty and "Current situation Peak (kW)" in m_df.columns) else float(kpis.original_peak_kw)
        avg_comb_pk = float(m_df["Combined Grid Peak (kW)"].mean()) if (not m_df.empty and "Combined Grid Peak (kW)" in m_df.columns) else float(kpis.new_grid_peak_kw)

        def _row_bill(item: str, calc: str, b_val: float, c_val: float, bypassed: bool = False) -> dict:
            sav = b_val - c_val
            hl = "#22C55E" if sav > 0.5 else ("#EF4444" if sav < -0.5 else None)
            return {
                "cells": [
                    item,
                    calc,
                    _fmt_curr(b_val, curr, html=True),
                    _fmt_curr(c_val, curr, html=True),
                    _fmt_curr(sav, curr, signed=True, html=True),
                ],
                "highlight": hl,
                "bypassed": bypassed,
            }

        bill_rows = []
        if en_p1:
            bill_rows.append({"group": "1. Electricity Supply (Retailer)"})
            if cur_fin.supplier_pricing_mode == "dual_tou":
                bill_rows.extend([
                    _row_bill("1.1a Peak HT Commodity (Mon-Fri 07-23)", f"{c_pref}{cur_fin.supplier_peak_ht_eur_kwh:.3f}/kWh", fk.baseline_supply_peak_ht_eur, fk.combined_supply_peak_ht_eur),
                    _row_bill("1.1b Off-Peak NT Commodity", f"{c_pref}{cur_fin.supplier_offpeak_nt_eur_kwh:.3f}/kWh", fk.baseline_supply_offpeak_nt_eur, fk.combined_supply_offpeak_nt_eur),
                ])
            else:
                bill_rows.append(
                    _row_bill("1.1 Purchased Energy (Single Rate)", f"{comb_kwh:,.0f} vs {base_kwh:,.0f} kWh &times; {c_pref}{cur_fin.supplier_energy_price_eur_kwh:.3f}", fk.baseline_supply_energy_eur, fk.combined_supply_energy_eur)
                )
            if cur_fin.supplier_gvo_surcharge_eur_kwh > 0.0:
                bill_rows.append(
                    _row_bill("1.2 Green Cert. & Surcharge", f"{comb_kwh:,.0f} kWh &times; {c_pref}{cur_fin.supplier_gvo_surcharge_eur_kwh:.4f}/kWh", fk.baseline_supply_gvo_eur, fk.combined_supply_gvo_eur)
                )
            bill_rows.append(
                _row_bill("1.3 Supplier Base Fee", f"12 mos &times; {c_pref}{cur_fin.supplier_fixed_fee_eur_month:.2f}/mo", fk.baseline_supply_fixed_eur, fk.combined_supply_fixed_eur)
            )
        else:
            bill_rows.append({"group": "1. Electricity Supply (Retailer) [BYPASSED — Bundled in Section 2]", "bypassed": True})
            bill_rows.append(
                _row_bill("1.1 Separate Energy Supplier", "Included in Single Utility Contract", 0.0, 0.0, bypassed=True)
            )

        p2_hdr = "2. Utility & Grid Network (Single Bill)" if is_single_util else "2. Grid Network (DSO)"
        if en_p2:
            bill_rows.append({"group": p2_hdr})
            if cur_fin.dso_connection_fee_eur_month > 0.0:
                bill_rows.extend([
                    _row_bill("2.1a Fixed Connection Fee", f"12 mos &times; {c_pref}{cur_fin.dso_connection_fee_eur_month:,.2f}/mo", fk.baseline_dso_connection_eur, fk.combined_dso_connection_eur),
                    _row_bill("2.1b Fixed Transport / Standing Fee", f"12 mos &times; {c_pref}{cur_fin.dso_fixed_fee_eur_month:,.2f}/mo", fk.baseline_dso_transport_fixed_eur, fk.combined_dso_transport_fixed_eur),
                ])
            else:
                bill_rows.append(
                    _row_bill("2.1 Fixed Standing Fee", f"12 mos &times; {c_pref}{cur_fin.dso_fixed_fee_eur_month:,.2f}/mo", fk.baseline_dso_fixed_eur, fk.combined_dso_fixed_eur)
                )
            breach_note = (
                f" [Breach-Adjusted: {fk.combined_dso_breach_months} mos]"
                if (cur_fin.dso_adjust_capacity_on_breach and (fk.combined_dso_breach_months > 0 or fk.baseline_dso_breach_months > 0))
                else ""
            )
            pk_disp_c = fk.combined_dso_billed_peak_avg_kw if fk.combined_dso_billed_peak_avg_kw > 0 else avg_comb_pk
            pk_disp_b = fk.baseline_dso_billed_peak_avg_kw if fk.baseline_dso_billed_peak_avg_kw > 0 else avg_base_pk
            pk_lbl = "2.3 Peak Demand Fee (Evening Window)" if cur_fin.dso_bill_peak_on_pico_only else "2.3 Monthly Peak Demand"
            bill_rows.extend([
                _row_bill("2.2 Booked Grid Capacity", f"{cur_sys.grid_limit_kw:,.0f} kW &times; 12 &times; {c_pref}{cur_fin.dso_capacity_fee_eur_kw_month:,.2f}{breach_note}", fk.baseline_dso_capacity_eur, fk.combined_dso_capacity_eur),
                _row_bill(pk_lbl, f"Avg {pk_disp_c:.0f} vs {pk_disp_b:.0f} kW &times; 12 &times; {c_pref}{cur_fin.dso_peak_demand_fee_eur_kw_month:,.2f}", fk.baseline_dso_peak_eur, fk.combined_dso_peak_eur),
            ])
            if cur_fin.dso_enable_three_window_tou:
                r_pk = float(cur_fin.dso_transport_peak_eur_kwh or cur_fin.dso_transport_eur_kwh)
                r_off = float(cur_fin.dso_transport_offpeak_eur_kwh or cur_fin.dso_transport_eur_kwh)
                r_sh = float(cur_fin.dso_transport_shoulder_eur_kwh or cur_fin.dso_transport_eur_kwh)
                bill_rows.extend([
                    _row_bill("2.4a Active Energy — Peak / Pico (18–23h)", f"{fk.combined_dso_peak_tou_kwh:,.0f} kWh &times; {c_pref}{r_pk:.4f}", fk.baseline_dso_vol_peak_eur, fk.combined_dso_vol_peak_eur),
                    _row_bill("2.4b Active Energy — Off-Peak / Valle (23–05h)", f"{fk.combined_dso_offpeak_tou_kwh:,.0f} kWh &times; {c_pref}{r_off:.4f}", fk.baseline_dso_vol_offpeak_eur, fk.combined_dso_vol_offpeak_eur),
                    _row_bill("2.4c Active Energy — Shoulder / Resto (05–18h)", f"{fk.combined_dso_shoulder_tou_kwh:,.0f} kWh &times; {c_pref}{r_sh:.4f}", fk.baseline_dso_vol_shoulder_eur, fk.combined_dso_vol_shoulder_eur),
                ])
            else:
                bill_rows.append(
                    _row_bill("2.4 Grid Transport Volume", f"{comb_kwh:,.0f} kWh &times; {c_pref}{cur_fin.dso_transport_eur_kwh:.3f}/kWh", fk.baseline_dso_transport_eur, fk.combined_dso_transport_eur)
                )
            if cur_fin.dso_enable_excess_capacity_penalty or fk.baseline_penalty_cost_eur > 0.5 or fk.combined_grid_penalty_cost_eur > 0.5:
                bill_rows.append(
                    _row_bill("2.5 Overload Penalties", f"Peak &gt; {cur_sys.grid_limit_kw:,.0f} kW &times; {c_pref}{cur_fin.grid_overload_penalty_eur_kw:,.2f}/kW", fk.baseline_penalty_cost_eur, fk.combined_grid_penalty_cost_eur)
                )
            if abs(cur_fin.dso_regulatory_adjustments_eur_month) > 0.01:
                bill_rows.append(
                    _row_bill("2.6 Monthly Utility Adjustments", f"12 mos &times; {c_pref}{cur_fin.dso_regulatory_adjustments_eur_month:,.0f}/mo", fk.baseline_dso_regulatory_adj_eur, fk.combined_dso_regulatory_adj_eur)
                )
            if cur_fin.avoided_transformer_rent_eur_month > 0.0:
                bill_rows.append(
                    _row_bill("2.7 Avoided Transformer Rent", f"12 mos &times; {c_pref}{cur_fin.avoided_transformer_rent_eur_month:,.0f}/mo", fk.baseline_dso_transformer_rent_eur, fk.combined_dso_transformer_rent_eur)
                )
        else:
            bill_rows.append({"group": "2. Grid Network (DSO) [BYPASSED]", "bypassed": True})

        bill_rows.append({"group": "3. Metering & Statutory Taxes"})
        if en_p3:
            bill_rows.append(
                _row_bill("3.1 Metering Service", f"12 mos &times; {c_pref}{cur_fin.metering_fixed_fee_eur_month:.2f}/mo", fk.baseline_pillar3_metering_eur, fk.combined_pillar3_metering_eur)
            )
        else:
            bill_rows.append(
                _row_bill("3.1 Metering [Bypassed — In Section 2]", "Included in Single Utility Contract", 0.0, 0.0, bypassed=True)
            )
        if en_p4:
            if cur_fin.energy_tax_eur_kwh > 0.0 or fk.baseline_energy_tax_gross_eur > 0.5:
                bill_rows.append(
                    _row_bill("3.2 Energy Tax (Gross)", f"{comb_kwh:,.0f} kWh &times; {c_pref}{cur_fin.energy_tax_eur_kwh:.4f}/kWh", fk.baseline_energy_tax_gross_eur, fk.combined_energy_tax_gross_eur)
                )
            if cur_fin.annual_tax_reduction_credit_eur > 0.0 or fk.baseline_tax_credit_eur > 0.5:
                bill_rows.append(
                    _row_bill("3.3 Annual Tax Credit", f"Fixed rebate {_fmt_curr(cur_fin.annual_tax_reduction_credit_eur, curr, html=True)}/yr", -fk.baseline_tax_credit_eur, -fk.combined_tax_credit_eur)
                )
            if cur_fin.tax_surcharge_pct > 0.0:
                bill_rows.append(
                    _row_bill("3.4 Municipal & Extra Tax Levies", f"{cur_fin.tax_surcharge_pct:.4f}% on electric net", fk.baseline_tax_surcharge_eur, fk.combined_tax_surcharge_eur)
                )
        else:
            bill_rows.append(_row_bill("3.2 Statutory Taxes [Bypassed]", "Disabled in Custom Bill Parts", 0.0, 0.0, bypassed=True))

        if cur_sys.enable_solar and fk.solar_export_revenue_eur > 0.0:
            bill_rows.append({"group": "4. Solar Export Credit"})
            bill_rows.append({
                "cells": [
                    "4.1 Grid Feed-in Revenue",
                    f"{kpis.solar_export_kwh:,.0f} kWh &times; {c_pref}{cur_fin.solar_export_feed_in_eur_kwh:.3f}",
                    _fmt_curr(0.0, curr, html=True),
                    f"-{_fmt_curr(fk.solar_export_revenue_eur, curr, html=True)}",
                    _fmt_curr(fk.solar_export_revenue_eur, curr, signed=True, html=True),
                ],
                "highlight": "#22C55E",
            })

        comb_bill_net_of_export = fk.combined_grid_total_eur - fk.solar_export_revenue_eur
        bill_savings_total = fk.baseline_total_opex_eur - comb_bill_net_of_export
        sub_html = _render_sub_ledger_html(
            header_title=f"Annual Electricity Bill Breakdown ({curr}, Net Excl. VAT)",
            columns=["Bill Line Item", "Calculation (Qty &times; Rate)", "Current (/yr)", "With System (/yr)", "Savings (/yr)"],
            rows=bill_rows,
            footer_cells=[
                "= TOTAL ANNUAL UTILITY BILL (NET OF EXPORT)",
                _fmt_curr(fk.baseline_total_opex_eur, curr, html=True),
                _fmt_curr(comb_bill_net_of_export, curr, html=True),
                _fmt_curr(bill_savings_total, curr, signed=True, html=True),
            ],
            accent_color="#38BDF8",
            is_enabled=True,
            currency_code=curr,
        )
        st.markdown(sub_html, unsafe_allow_html=True)
        if cur_fin.vat_rate_pct > 0.0:
            vat_note = "on electric parts only" if not cur_fin.vat_applies_to_levies else "on total net bill"
            st.caption(
                f":material/receipt: **Gross Bill Incl. {cur_fin.vat_rate_pct:.1f}% VAT ({vat_note}):** "
                f"Current **{_fmt_curr(fk.baseline_total_gross_eur, curr)}/yr** (VAT {_fmt_curr(fk.baseline_vat_eur, curr)}) -> "
                f"With System **{_fmt_curr(fk.combined_grid_gross_eur, curr)}/yr** (VAT {_fmt_curr(fk.combined_grid_vat_eur, curr)})."
            )

        if kpis.grid_limit_met:
            st.success(
                f":material/check_circle: **Grid Compliance & Bill Impact:** Peak reduced from **{kpis.original_peak_kw:,.1f} kW** to **{kpis.new_grid_peak_kw:,.1f} kW** "
                f"(within {cur_sys.grid_limit_kw:,.0f} kW limit).  \n"
                f"**Where Grid Savings Come From:** **{_fmt_curr(fk.grid_volume_savings_y1_eur, curr)}/yr** from reduced energy imports + "
                f"**{_fmt_curr(fk.grid_peak_and_penalty_savings_y1_eur, curr)}/yr** from peak shaving & avoided penalties"
                + (f" + **{_fmt_curr(fk.solar_export_revenue_eur, curr)}/yr** solar export income." if fk.solar_export_revenue_eur > 0 else ".")
            )
        else:
            st.warning(
                f":material/warning: **Remaining Overload Warning:** Peak reduced from **{kpis.original_peak_kw:,.1f} kW** to **{kpis.new_grid_peak_kw:,.1f} kW** "
                f"(**+{kpis.remaining_overload_kw:,.1f} kW** above {cur_sys.grid_limit_kw:,.0f} kW limit).  \n"
                f"**Where Grid Savings Come From:** **{_fmt_curr(fk.grid_volume_savings_y1_eur, curr)}/yr** from reduced energy imports + "
                f"**{_fmt_curr(fk.grid_peak_and_penalty_savings_y1_eur, curr)}/yr** from peak & penalty reductions."
            )

    _render_monthly_grid_bill_progression_fragment(sim_res)
    _render_isolated_pillar_deep_dive_fragment(sim_res)
