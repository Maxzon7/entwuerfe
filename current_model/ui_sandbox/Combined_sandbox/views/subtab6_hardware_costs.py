"""
Sub-Tab 6.2: Hardware & Running Costs (Technical Profiles, Unit Rates & >0 Lump-Sum Overrides,
Pure-Cost Sub-Ledgers with Implied Unit Benchmarks, BESS Repowering, and Isolated Asset Charts).
"""

import streamlit as st

from .state_and_helpers import (
    CombinedSystemConfig,
    CombinedFinancialConfig,
    render_kpi_card,
    determine_smart_modular_units,
    evaluate_combined_financials,
    scale_eur_hardware_defaults_to_currency,
    create_solar_isolated_financial_figure,
    create_battery_isolated_financial_figure,
    create_generator_isolated_financial_figure,
)
from .subtab6_isolated_pillars import (
    _get_curr_code,
    _curr_prefix,
    _fmt_curr,
    _render_sub_ledger_html,
    _rename_df_currency_cols,
)


def _render_subtab6_2_currency_guard(sim_res, cur_sys: CombinedSystemConfig, cur_fin: CombinedFinancialConfig, curr: str) -> None:
    """Warns if active contract currency is non-EUR while hardware defaults are still on EUR scale, with 1-click FX scaling."""
    if curr == "EUR":
        return

    looks_like_eur_defaults = (
        (cur_sys.enable_solar and cur_fin.solar_lump_sum_capex_eur == 0.0 and abs(cur_fin.solar_turnkey_eur_kwp - 850.0) < 1e-3)
        or (cur_sys.enable_battery and cur_fin.battery_lump_sum_capex_eur == 0.0 and abs(cur_fin.battery_capex_eur_kwh - 280.0) < 1e-3)
        or (cur_sys.enable_generator and cur_fin.generator_lump_sum_capex_eur == 0.0 and abs(cur_fin.generator_capex_eur - 22000.0) < 1e-3)
    )
    if not looks_like_eur_defaults:
        return

    default_fx = 1100.0 if curr == "ARS" else 1.08
    st.warning(
        f":material/currency_exchange: **Currency Check ({curr} Active):** Your electricity bill uses **{curr}**, "
        "while some hardware unit prices are still at default EUR numbers. Enter hardware quotes directly in "
        f"**{curr}** below, or scale the EUR defaults with an exchange rate first."
    )
    with st.form("comb_fin_hw_fx_scale_form"):
        fx_c1, fx_c2 = st.columns([2.2, 1.3])
        with fx_c1:
            fx_rate = st.number_input(
                f"Exchange Rate to Scale EUR Defaults (1 EUR = ? {curr})",
                min_value=0.01,
                max_value=100000.0,
                value=float(default_fx),
                step=10.0 if curr == "ARS" else 0.01,
                key="comb_fin_hw_fx_rate_num",
            )
        with fx_c2:
            st.write("")
            fx_apply = st.form_submit_button(
                f"Scale Defaults to {curr}",
                icon=":material/currency_exchange:",
                use_container_width=True,
            )

    if fx_apply:
        r = max(0.01, float(fx_rate))
        scale_eur_hardware_defaults_to_currency(cur_fin, fx_rate=r)
        for wk in (
            "comb_fin_sol_turnkey", "comb_fin_sol_mod", "comb_fin_sol_inv", "comb_fin_sol_mnt",
            "comb_fin_bat_rack", "comb_fin_bat_inv", "comb_fin_bat_bop",
            "comb_fin_gen_capex", "comb_fin_gen_rent", "comb_fin_gen_fuel", "comb_fin_gen_maint",
        ):
            st.session_state.pop(wk, None)
        evaluate_combined_financials(sim_res, cur_fin)
        st.session_state.pop("comb_cached_excel_bytes", None)
        st.rerun()


def _render_subtab6_2_hardware_costs(sim_res, cur_sys: CombinedSystemConfig, cur_fin: CombinedFinancialConfig) -> None:
    """Sub-Tab 6.2: Technical Profiles, Unit Rates vs. >0 Lump-Sum Overrides & Pure-Cost Sub-Ledgers."""
    fk = sim_res.financial_kpis
    kpis = sim_res.kpis
    deriv = sim_res.solar_derivation
    curr = _get_curr_code(sim_res)
    c_html = _curr_prefix(curr, html=True)

    _render_subtab6_2_currency_guard(sim_res, cur_sys, cur_fin, curr)

    with st.form("comb_hardware_costs_form"):
        # ------------------------------------------------------------------------------
        # 1. SOLAR PV SYSTEM
        # ------------------------------------------------------------------------------
        sol_badge = f"{deriv.installed_kwp:,.1f} kWp Active" if cur_sys.enable_solar else f"INACTIVE — {_fmt_curr(0, curr)}"
        with st.expander(f":material/solar_power: Solar Costs ({sol_badge})", expanded=cur_sys.enable_solar):
            st.info(
                f":material/info: **Technical Profile:** Installed DC: **{deriv.installed_kwp:,.1f} kWp** "
                f"| Panels: **{deriv.panel_count:,} x {deriv.panel_wp:.0f} Wp** "
                f"| AC Inverter Limit: **{deriv.inverter_ac_kw:,.1f} kW**",
            )
            s_in, s_led = st.columns([0.46, 0.54], gap="large")
            with s_in:
                sol_turnkey = st.number_input(
                    f"Turnkey Solar Price ({curr}/kWp)",
                    min_value=0.0,
                    max_value=1e10,
                    value=float(cur_fin.solar_turnkey_eur_kwp),
                    step=25.0,
                    key="comb_fin_sol_turnkey",
                    disabled=not cur_sys.enable_solar,
                    help="Standard all-in price per kWp installed. Ignored if Detailed Breakdown or Lump-Sum CAPEX Override (> 0) is active.",
                )
                sol_om = st.number_input(
                    "Annual Maintenance (% of CAPEX/yr)",
                    min_value=0.0,
                    max_value=25.0,
                    value=float(cur_fin.solar_om_pct_of_capex),
                    step=0.25,
                    key="comb_fin_sol_om",
                    disabled=not cur_sys.enable_solar,
                )
                with st.container(border=True):
                    sol_use_detail = st.checkbox(
                        "Use Detailed Breakdown instead of Turnkey /kWp",
                        value=bool(cur_fin.solar_use_detailed_breakdown),
                        key="comb_fin_sol_use_detail",
                        disabled=not cur_sys.enable_solar,
                    )
                    sd1, sd2, sd3 = st.columns(3)
                    with sd1:
                        sol_mod = st.number_input(
                            f"Modules ({curr}/Wp)",
                            min_value=0.0, max_value=1e8, value=float(cur_fin.solar_modules_eur_wp), step=0.02, format="%.2f",
                            key="comb_fin_sol_mod", disabled=not cur_sys.enable_solar,
                        )
                    with sd2:
                        sol_inv = st.number_input(
                            f"Inverter ({curr}/W)",
                            min_value=0.0, max_value=1e8, value=float(cur_fin.solar_inverter_eur_w), step=0.01, format="%.2f",
                            key="comb_fin_sol_inv", disabled=not cur_sys.enable_solar,
                        )
                    with sd3:
                        sol_mnt = st.number_input(
                            f"Mounting ({curr}/Wp)",
                            min_value=0.0, max_value=1e8, value=float(cur_fin.solar_mounting_eur_wp), step=0.02, format="%.2f",
                            key="comb_fin_sol_mnt", disabled=not cur_sys.enable_solar,
                        )

                st.markdown("---")
                st.caption("**Quote Override (Enter > 0 to use exact quote without overwriting unit rates above):**")
                so_1, so_2 = st.columns(2)
                with so_1:
                    sol_lump_capex = st.number_input(
                        f"Lump-Sum CAPEX Override ({curr}, 0 = use unit rate)",
                        min_value=0.0, max_value=1e12, value=float(cur_fin.solar_lump_sum_capex_eur), step=1000.0,
                        key="comb_fin_sol_lump_capex", disabled=not cur_sys.enable_solar,
                    )
                with so_2:
                    sol_lump_om = st.number_input(
                        f"Lump-Sum Annual O&M Override ({curr}/yr, 0 = use %)",
                        min_value=0.0, max_value=1e12, value=float(cur_fin.solar_lump_sum_om_eur_year), step=250.0,
                        key="comb_fin_sol_lump_om", disabled=not cur_sys.enable_solar,
                    )

            with s_led:
                sol_rows = [{"group": f"Upfront Investment (CAPEX — {fk.solar_pricing_mode})"}]
                if cur_fin.solar_lump_sum_capex_eur > 0.0:
                    sol_rows.append({
                        "cells": [
                            "1.1 Lump-Sum Turnkey Quote (Override)",
                            f"Exact quote for {deriv.installed_kwp:,.1f} kWp",
                            "&mdash;",
                            _fmt_curr(fk.solar_capex_eur, curr, html=True),
                        ]
                    })
                elif cur_fin.solar_use_detailed_breakdown:
                    sol_rows.extend([
                        {"cells": ["1.1 Solar Modules", f"{deriv.installed_kwp:,.1f} kWp &times; 1,000 &times; {c_html}{cur_fin.solar_modules_eur_wp:,.2f}", "&mdash;", _fmt_curr(fk.solar_modules_capex_eur, curr, html=True)]},
                        {"cells": ["1.2 Solar Inverters", f"{deriv.installed_kwp:,.1f} kWp &times; 1,000 &times; {c_html}{cur_fin.solar_inverter_eur_w:,.2f}", "&mdash;", _fmt_curr(fk.solar_inverter_capex_eur, curr, html=True)]},
                        {"cells": ["1.3 Mounting &amp; Installation", f"{deriv.installed_kwp:,.1f} kWp &times; 1,000 &times; {c_html}{cur_fin.solar_mounting_eur_wp:,.2f}", "&mdash;", _fmt_curr(fk.solar_mounting_capex_eur, curr, html=True)]},
                    ])
                else:
                    sol_rows.append({
                        "cells": [
                            "1.1 Turnkey Solar PV System",
                            f"{deriv.installed_kwp:,.1f} kWp &times; {c_html}{cur_fin.solar_turnkey_eur_kwp:,.0f}/kWp",
                            "&mdash;",
                            _fmt_curr(fk.solar_capex_eur, curr, html=True),
                        ]
                    })

                om_calc_txt = (
                    "Lump-Sum O&amp;M Override"
                    if cur_fin.solar_lump_sum_om_eur_year > 0.0
                    else f"{cur_fin.solar_om_pct_of_capex:.2f}% &times; {_fmt_curr(fk.solar_capex_eur, curr, html=True)}"
                )
                sol_rows.extend([
                    {"group": f"Recurring Operating Cost (OPEX — {fk.solar_opex_pricing_mode})"},
                    {"cells": ["2.1 Annual Maintenance (O&amp;M)", om_calc_txt, _fmt_curr(fk.solar_om_eur / 12.0, curr, html=True), _fmt_curr(fk.solar_om_eur, curr, html=True)]},
                ])
                st.markdown(
                    _render_sub_ledger_html(
                        header_title=f"Solar PV Cost Summary (Total CAPEX: {_fmt_curr(fk.solar_capex_eur, curr, html=True)})",
                        columns=["Cost Line Item", "Calculation Basis", "Monthly", "One-Off / Annual"],
                        rows=sol_rows,
                        footer_cells=[
                            "= TOTAL ANNUAL SOLAR O&amp;M (OPEX)",
                            f"{_fmt_curr(fk.solar_om_eur / 12.0, curr, html=True)}/mo",
                            f"{_fmt_curr(fk.solar_om_eur, curr, html=True)}/yr",
                        ],
                        accent_color="#FACC15",
                        is_enabled=cur_sys.enable_solar,
                        currency_code=curr,
                    ),
                    unsafe_allow_html=True,
                )
                if cur_sys.enable_solar and deriv.installed_kwp > 0.0:
                    ov_tag = " (Lump-Sum Override Active)" if cur_fin.solar_lump_sum_capex_eur > 0.0 else ""
                    st.caption(
                        f":material/fact_check: **Market Check{ov_tag}:** Implied Solar CAPEX = **{_fmt_curr(fk.solar_implied_eur_kwp, curr)} / kWp**"
                    )

        # ------------------------------------------------------------------------------
        # 2. BATTERY STORAGE (BESS)
        # ------------------------------------------------------------------------------
        bat_badge = (
            f"{cur_sys.battery_capacity_kwh:,.0f} kWh / {cur_sys.battery_power_kw:,.0f} kW Active"
            if cur_sys.enable_battery
            else f"INACTIVE — {_fmt_curr(0, curr)}"
        )
        with st.expander(f":material/battery_charging_full: Battery Costs ({bat_badge})", expanded=cur_sys.enable_battery):
            b_units = int(st.session_state.get("comb_bess_unit_count", 0) or 0)
            b_ukwh = float(st.session_state.get("comb_bess_unit_kwh", 0.0) or 0.0)
            if (b_units <= 0 or b_ukwh <= 0.0) and cur_sys.battery_capacity_kwh > 0.0:
                b_units, b_ukwh = determine_smart_modular_units(cur_sys.battery_capacity_kwh)
            c_rate = (cur_sys.battery_power_kw / cur_sys.battery_capacity_kwh) if cur_sys.battery_capacity_kwh > 0.0 else 0.0
            dur_h = (cur_sys.battery_capacity_kwh / cur_sys.battery_power_kw) if cur_sys.battery_power_kw > 0.0 else 0.0
            st.info(
                f":material/info: **Technical Profile:** Gross Capacity: **{cur_sys.battery_capacity_kwh:,.0f} kWh** "
                f"(**{b_units} x {b_ukwh:,.0f} kWh**) "
                f"| Inverter Power: **{cur_sys.battery_power_kw:,.1f} kW** "
                f"| C-Rate: **{c_rate:.2f} C ({dur_h:.1f}h storage)**",
            )
            b_in, b_led = st.columns([0.46, 0.54], gap="large")
            with b_in:
                b1, b2 = st.columns(2)
                with b1:
                    bat_rack = st.number_input(
                        f"Storage Racks ({curr}/kWh)",
                        min_value=0.0, max_value=1e10, value=float(cur_fin.battery_capex_eur_kwh), step=10.0,
                        key="comb_fin_bat_rack", disabled=not cur_sys.enable_battery,
                    )
                    bat_bop = st.number_input(
                        f"Installation & BoP ({curr})",
                        min_value=0.0, max_value=1e12, value=float(cur_fin.battery_fixed_bop_eur), step=1000.0,
                        key="comb_fin_bat_bop", disabled=not cur_sys.enable_battery,
                    )
                with b2:
                    bat_inv = st.number_input(
                        f"Power Inverter / PCS ({curr}/kW)",
                        min_value=0.0, max_value=1e10, value=float(cur_fin.battery_capex_eur_kw), step=10.0,
                        key="comb_fin_bat_inv", disabled=not cur_sys.enable_battery,
                    )
                    bat_om = st.number_input(
                        "Annual Maintenance (% of CAPEX/yr)",
                        min_value=0.0, max_value=25.0, value=float(cur_fin.battery_om_pct_of_capex), step=0.25,
                        key="comb_fin_bat_om", disabled=not cur_sys.enable_battery,
                    )

                st.caption("**Planned Cell Replacement (Repowering):**")
                a1, a2, a3 = st.columns([1.25, 0.85, 0.90])
                with a1:
                    en_aug = st.checkbox(
                        "Plan Cell Repowering",
                        value=bool(cur_fin.enable_battery_augmentation),
                        key="comb_fin_bat_aug_chk", disabled=not cur_sys.enable_battery,
                    )
                with a2:
                    aug_yr = st.number_input(
                        "Year", min_value=5, max_value=14, value=int(cur_fin.battery_augmentation_year), step=1,
                        key="comb_fin_bat_aug_yr", disabled=not (cur_sys.enable_battery and en_aug),
                    )
                with a3:
                    aug_pct = st.number_input(
                        "Cost (% Base)", min_value=10.0, max_value=100.0, value=float(cur_fin.battery_augmentation_pct_of_racks), step=5.0,
                        key="comb_fin_bat_aug_pct", disabled=not (cur_sys.enable_battery and en_aug),
                        help="Applied to Storage Racks under unit pricing, or to total BESS lump sum if CAPEX override is active.",
                    )
                aug_lump = st.number_input(
                    f"Repowering Lump-Sum Override ({curr}, 0 = use % above)",
                    min_value=0.0, max_value=1e12, value=float(cur_fin.battery_augmentation_lump_sum_eur), step=1000.0,
                    key="comb_fin_bat_aug_lump", disabled=not (cur_sys.enable_battery and en_aug),
                )

                st.markdown("---")
                st.caption("**Quote Override (Enter > 0 to use exact quote without overwriting unit rates above):**")
                bo_1, bo_2 = st.columns(2)
                with bo_1:
                    bat_lump_capex = st.number_input(
                        f"Lump-Sum CAPEX Override ({curr}, 0 = use unit rates)",
                        min_value=0.0, max_value=1e12, value=float(cur_fin.battery_lump_sum_capex_eur), step=1000.0,
                        key="comb_fin_bat_lump_capex", disabled=not cur_sys.enable_battery,
                    )
                with bo_2:
                    bat_lump_om = st.number_input(
                        f"Lump-Sum Annual O&M Override ({curr}/yr, 0 = use %)",
                        min_value=0.0, max_value=1e12, value=float(cur_fin.battery_lump_sum_om_eur_year), step=250.0,
                        key="comb_fin_bat_lump_om", disabled=not cur_sys.enable_battery,
                    )

            with b_led:
                bat_rows = [{"group": f"Upfront Investment (CAPEX — {fk.battery_pricing_mode})"}]
                if cur_fin.battery_lump_sum_capex_eur > 0.0:
                    bat_rows.append({
                        "cells": [
                            "2.1 Lump-Sum Turnkey Quote (Override)",
                            f"Exact quote for {cur_sys.battery_capacity_kwh:,.0f} kWh / {cur_sys.battery_power_kw:,.0f} kW",
                            "&mdash;",
                            _fmt_curr(fk.battery_capex_eur, curr, html=True),
                        ]
                    })
                else:
                    bat_rows.extend([
                        {"cells": ["2.1 Storage Racks", f"{cur_sys.battery_capacity_kwh:,.0f} kWh &times; {c_html}{cur_fin.battery_capex_eur_kwh:,.0f}/kWh", "&mdash;", _fmt_curr(fk.battery_rack_capex_eur, curr, html=True)]},
                        {"cells": ["2.2 Bidirectional Inverter (PCS)", f"{cur_sys.battery_power_kw:,.0f} kW &times; {c_html}{cur_fin.battery_capex_eur_kw:,.0f}/kW", "&mdash;", _fmt_curr(fk.battery_inverter_capex_eur, curr, html=True)]},
                        {"cells": ["2.3 Installation &amp; BoP", "Fixed Balance of Plant", "&mdash;", _fmt_curr(fk.battery_bop_capex_eur, curr, html=True)]},
                    ])
                bat_rows.append({
                    "cells": [
                        "<b>= Total Battery CAPEX</b>",
                        "Upfront Turnkey Investment",
                        "&mdash;",
                        f"<b>{_fmt_curr(fk.battery_capex_eur, curr, html=True)}</b>",
                    ]
                })

                rep_desc = (
                    f"Year {int(cur_fin.battery_augmentation_year)} ({fk.battery_repowering_mode})"
                    if cur_fin.enable_battery_augmentation
                    else "Not planned"
                )
                bat_om_desc = (
                    "Lump-Sum O&amp;M Override"
                    if cur_fin.battery_lump_sum_om_eur_year > 0.0
                    else f"{cur_fin.battery_om_pct_of_capex:.2f}% &times; {_fmt_curr(fk.battery_capex_eur, curr, html=True)}"
                )
                bat_rows.extend([
                    {"group": "Mid-Life Repowering &amp; Recurring OPEX"},
                    {"cells": [f"Planned Cell Repowering (Yr {int(cur_fin.battery_augmentation_year)})", rep_desc, "&mdash;", _fmt_curr(fk.battery_augmentation_eur, curr, html=True)]},
                    {"cells": [f"Annual Battery Maintenance ({fk.battery_opex_pricing_mode})", bat_om_desc, _fmt_curr(fk.battery_om_eur / 12.0, curr, html=True), _fmt_curr(fk.battery_om_eur, curr, html=True)]},
                ])
                st.markdown(
                    _render_sub_ledger_html(
                        header_title=f"Battery Storage Cost Summary (Total CAPEX: {_fmt_curr(fk.battery_capex_eur, curr, html=True)})",
                        columns=["Cost Line Item", "Calculation Basis", "Monthly", "One-Off / Annual"],
                        rows=bat_rows,
                        footer_cells=[
                            "= TOTAL ANNUAL BATTERY O&amp;M (OPEX)",
                            f"{_fmt_curr(fk.battery_om_eur / 12.0, curr, html=True)}/mo",
                            f"{_fmt_curr(fk.battery_om_eur, curr, html=True)}/yr",
                        ],
                        accent_color="#22C55E",
                        is_enabled=cur_sys.enable_battery,
                        currency_code=curr,
                    ),
                    unsafe_allow_html=True,
                )
                if cur_sys.enable_battery and cur_sys.battery_capacity_kwh > 0.0:
                    ov_tag = " (Lump-Sum Override Active)" if cur_fin.battery_lump_sum_capex_eur > 0.0 else ""
                    st.caption(
                        f":material/fact_check: **Market Check{ov_tag}:** Implied BESS CAPEX = "
                        f"**{_fmt_curr(fk.battery_implied_eur_kwh, curr)} / kWh** | "
                        f"**{_fmt_curr(fk.battery_implied_eur_kw, curr)} / kW**"
                    )

        # ------------------------------------------------------------------------------
        # 3. PEAKING GENERATOR
        # ------------------------------------------------------------------------------
        gen_badge = f"{cur_sys.generator_rated_kw:,.0f} kW {cur_sys.fuel_type} Active" if cur_sys.enable_generator else f"INACTIVE — {_fmt_curr(0, curr)}"
        with st.expander(f":material/power: Generator Costs ({gen_badge})", expanded=cur_sys.enable_generator):
            st.info(
                f":material/info: **Technical Profile:** Rated Power: **{cur_sys.generator_rated_kw:,.0f} kW** "
                f"| Fuel: **{cur_sys.fuel_type}** "
                f"| Simulated Runtime: **{kpis.generator_runtime_hours:,.1f} hrs/yr** ({kpis.generator_starts_count} starts/yr)",
            )
            gn_in, gn_led = st.columns([0.46, 0.54], gap="large")
            with gn_in:
                gen_model = st.selectbox(
                    "Acquisition Mode",
                    options=["Purchase (CAPEX)", "Monthly Rental (OPEX)"],
                    index=0 if cur_fin.generator_cost_model == "Purchase (CAPEX)" else 1,
                    key="comb_fin_gen_model", disabled=not cur_sys.enable_generator,
                )
                g_c1, g_c2 = st.columns(2)
                with g_c1:
                    gen_capex = st.number_input(
                        f"Purchase Price ({curr})",
                        min_value=0.0, max_value=1e12, value=float(cur_fin.generator_capex_eur), step=1000.0,
                        key="comb_fin_gen_capex", disabled=not cur_sys.enable_generator,
                    )
                    fuel_pr = st.number_input(
                        f"Fuel Price ({curr}/{kpis.generator_fuel_unit})",
                        min_value=0.0, max_value=1e8, value=float(cur_fin.fuel_price_eur_per_unit), step=0.05, format="%.2f",
                        key="comb_fin_gen_fuel", disabled=not cur_sys.enable_generator,
                    )
                with g_c2:
                    gen_rent = st.number_input(
                        f"Monthly Rental ({curr}/mo)",
                        min_value=0.0, max_value=1e11, value=float(cur_fin.generator_rental_eur_month), step=100.0,
                        key="comb_fin_gen_rent", disabled=not cur_sys.enable_generator,
                    )
                    gen_maint = st.number_input(
                        f"Maintenance ({curr}/op hr)",
                        min_value=0.0, max_value=1e9, value=float(cur_fin.generator_maintenance_eur_per_hour), step=0.5,
                        key="comb_fin_gen_maint", disabled=not cur_sys.enable_generator,
                    )
                gen_rent_active_only = st.checkbox(
                    "Charge Rental Only in Active Months (Runtime > 0)",
                    value=bool(getattr(cur_fin, "generator_rental_active_months_only", False)),
                    key="comb_fin_gen_rent_active_only",
                    disabled=not cur_sys.enable_generator,
                    help="Applies in Monthly Rental (OPEX) mode: monthly rental is only charged in months where the generator actually runs (runtime > 0 hrs). Default off = all 12 months.",
                )

                st.markdown("---")
                st.caption("**Quote Override (Enter > 0 to replace Purchase CAPEX or Service/Rental OPEX):**")
                go_1, go_2 = st.columns(2)
                with go_1:
                    gen_lump_capex = st.number_input(
                        f"Lump-Sum CAPEX Override ({curr}, 0 = use purchase price)",
                        min_value=0.0, max_value=1e12, value=float(cur_fin.generator_lump_sum_capex_eur), step=1000.0,
                        key="comb_fin_gen_lump_capex", disabled=not cur_sys.enable_generator,
                    )
                with go_2:
                    gen_lump_svc = st.number_input(
                        f"Lump-Sum Service/Fixed OPEX Override ({curr}/yr, 0 = use rate)",
                        min_value=0.0, max_value=1e12, value=float(cur_fin.generator_lump_sum_service_opex_eur_year), step=500.0,
                        key="comb_fin_gen_lump_svc", disabled=not cur_sys.enable_generator,
                        help="Replaces hourly service & rental fees with an annual lump sum while keeping simulated fuel cost dynamic.",
                    )

            with gn_led:
                capex_desc = (
                    "Lump-Sum CAPEX Override"
                    if cur_fin.generator_lump_sum_capex_eur > 0.0 and cur_fin.generator_cost_model == "Purchase (CAPEX)"
                    else ("One-off purchase" if cur_fin.generator_cost_model == "Purchase (CAPEX)" else "Rental mode (CAPEX = 0)")
                )
                svc_desc = (
                    "Lump-Sum Annual Service Override"
                    if cur_fin.generator_lump_sum_service_opex_eur_year > 0.0
                    else f"{kpis.generator_runtime_hours:,.1f} hrs &times; {c_html}{cur_fin.generator_maintenance_eur_per_hour:,.2f}/hr"
                )
                rent_months_label = (
                    f"{int(round(fk.generator_rental_cost_eur / cur_fin.generator_rental_eur_month))} active mos"
                    if (cur_fin.generator_rental_active_months_only and cur_fin.generator_rental_eur_month > 0.0 and cur_fin.generator_cost_model == "Monthly Rental (OPEX)")
                    else "12 mos"
                )
                gen_rows = [
                    {"group": f"Acquisition ({fk.generator_pricing_mode})"},
                    {"cells": ["3.1 Purchase Investment (CAPEX)", capex_desc, "&mdash;", _fmt_curr(fk.generator_capex_eur, curr, html=True)]},
                    {"cells": ["3.2 Rental / Leasing Fee (OPEX)", f"{rent_months_label} &times; {c_html}{cur_fin.generator_rental_eur_month:,.0f}/mo (if rental &amp; no override)", _fmt_curr(fk.generator_rental_cost_eur / 12.0, curr, html=True), _fmt_curr(fk.generator_rental_cost_eur, curr, html=True)]},
                    {"group": f"Annual Fuel &amp; Operating Service ({fk.generator_opex_pricing_mode})"},
                    {"cells": [f"3.3 Fuel Consumption ({cur_sys.fuel_type})", f"{kpis.generator_fuel_total:,.1f} {kpis.generator_fuel_unit} &times; {c_html}{cur_fin.fuel_price_eur_per_unit:,.2f}", _fmt_curr(fk.generator_fuel_cost_eur / 12.0, curr, html=True), _fmt_curr(fk.generator_fuel_cost_eur, curr, html=True)]},
                    {"cells": ["3.4 Service &amp; Maintenance", svc_desc, _fmt_curr(fk.generator_maintenance_cost_eur / 12.0, curr, html=True), _fmt_curr(fk.generator_maintenance_cost_eur, curr, html=True)]},
                ]
                st.markdown(
                    _render_sub_ledger_html(
                        header_title=f"Generator Cost Summary (Generated: {kpis.generator_to_load_kwh:,.0f} kWh/yr)",
                        columns=["Cost Line Item", "Calculation Basis", "Monthly", "One-Off / Annual"],
                        rows=gen_rows,
                        footer_cells=[
                            "= TOTAL GENERATOR ANNUAL OPEX",
                            f"{_fmt_curr(fk.generator_total_opex_eur / 12.0, curr, html=True)}/mo",
                            f"{_fmt_curr(fk.generator_total_opex_eur, curr, html=True)}/yr",
                        ],
                        accent_color="#F97316",
                        is_enabled=cur_sys.enable_generator,
                        currency_code=curr,
                    ),
                    unsafe_allow_html=True,
                )
                if cur_sys.enable_generator and cur_fin.generator_cost_model == "Purchase (CAPEX)" and cur_sys.generator_rated_kw > 0.0:
                    ov_tag = " (Lump-Sum Override Active)" if cur_fin.generator_lump_sum_capex_eur > 0.0 else ""
                    st.caption(
                        f":material/fact_check: **Market Check{ov_tag}:** Implied Generator CAPEX = **{_fmt_curr(fk.generator_implied_eur_kw, curr)} / kW**"
                    )

        # ------------------------------------------------------------------------------
        # 4. SAVED GRID UPGRADE CREDIT
        # ------------------------------------------------------------------------------
        with st.expander(":material/savings: Saved Grid Upgrade Cost", expanded=bool(cur_fin.avoided_grid_upgrade_capex_eur > 0.0 or cur_fin.strict_grid_congestion_mode)):
            av_in, av_led = st.columns([0.46, 0.54], gap="large")
            with av_in:
                if cur_fin.strict_grid_congestion_mode:
                    st.session_state["comb_fin_avoided_upgrade"] = 0.0
                avoided_upgrade = st.number_input(
                    f"One-Off Avoided Grid Upgrade Cost ({curr})",
                    min_value=0.0,
                    max_value=1e12,
                    value=0.0 if cur_fin.strict_grid_congestion_mode else float(cur_fin.avoided_grid_upgrade_capex_eur),
                    step=5000.0,
                    key="comb_fin_avoided_upgrade",
                    disabled=bool(cur_fin.strict_grid_congestion_mode),
                    help="Capital expenditure avoided by peak shaving instead of paying the DSO for a grid expansion.",
                )
                if cur_fin.strict_grid_congestion_mode:
                    st.caption(
                        ":material/lock: Disabled while **Strict Grid Congestion Lock** is active — "
                        "buying a grid upgrade is not allowed under congestion constraints."
                    )
            with av_led:
                st.info(
                    f":material/info: **Net Project Investment Summary:**  \n"
                    f"Gross Hardware CAPEX (**{_fmt_curr(fk.gross_capex_eur, curr)}**) &minus; Avoided Grid Upgrade (**{_fmt_curr(fk.avoided_grid_upgrade_capex_eur, curr)}**) "
                    f"= **Net Turnkey Investment: {_fmt_curr(fk.total_capex_eur, curr)}**."
                )

        hw_submitted = st.form_submit_button(
            "Apply Hardware & Operating Costs",
            icon=":material/check_circle:",
            type="primary",
            use_container_width=True,
        )

    if hw_submitted:
        if cur_sys.enable_solar:
            cur_fin.solar_turnkey_eur_kwp = float(sol_turnkey)
            cur_fin.solar_use_detailed_breakdown = bool(sol_use_detail)
            cur_fin.solar_modules_eur_wp = float(sol_mod)
            cur_fin.solar_inverter_eur_w = float(sol_inv)
            cur_fin.solar_mounting_eur_wp = float(sol_mnt)
            cur_fin.solar_capex_eur_kwp = None
            cur_fin.solar_lump_sum_capex_eur = float(sol_lump_capex)
            cur_fin.solar_om_pct_of_capex = float(sol_om)
            cur_fin.solar_lump_sum_om_eur_year = float(sol_lump_om)

        if cur_sys.enable_battery:
            cur_fin.battery_capex_eur_kwh = float(bat_rack)
            cur_fin.battery_capex_eur_kw = float(bat_inv)
            cur_fin.battery_fixed_bop_eur = float(bat_bop)
            cur_fin.battery_lump_sum_capex_eur = float(bat_lump_capex)
            cur_fin.battery_om_pct_of_capex = float(bat_om)
            cur_fin.battery_lump_sum_om_eur_year = float(bat_lump_om)
            cur_fin.enable_battery_augmentation = bool(en_aug)
            cur_fin.battery_augmentation_year = int(aug_yr)
            cur_fin.battery_augmentation_pct_of_racks = float(aug_pct)
            cur_fin.battery_augmentation_lump_sum_eur = float(aug_lump)

        if cur_sys.enable_generator:
            cur_fin.generator_cost_model = str(gen_model)
            cur_fin.generator_capex_eur = float(gen_capex)
            cur_fin.generator_lump_sum_capex_eur = float(gen_lump_capex)
            cur_fin.generator_rental_eur_month = float(gen_rent)
            cur_fin.generator_rental_active_months_only = bool(gen_rent_active_only)
            cur_fin.fuel_price_eur_per_unit = float(fuel_pr)
            cur_fin.generator_maintenance_eur_per_hour = float(gen_maint)
            cur_fin.generator_lump_sum_service_opex_eur_year = float(gen_lump_svc)

        cur_fin.avoided_grid_upgrade_capex_eur = 0.0 if cur_fin.strict_grid_congestion_mode else float(avoided_upgrade)
        evaluate_combined_financials(sim_res, cur_fin)
        st.session_state.pop("comb_cached_excel_bytes", None)
        st.rerun()

    _render_isolated_component_economics_fragment(sim_res, cur_sys)


@st.fragment
def _render_isolated_component_economics_fragment(sim_res, cur_sys: CombinedSystemConfig) -> None:
    """Isolated Solar, Battery, and Generator economics with KPIs, Plotly charts, and 12-month tables."""
    fk = sim_res.financial_kpis
    kpis = sim_res.kpis
    if fk is None:
        return
    curr = _get_curr_code(sim_res)

    st.markdown("##### :material/analytics: Isolated Hardware Economics (Charts & 12-Month Tables)")
    st.caption(
        "Inspect standalone economics for Solar, Battery, and Generator individually. Each expander shows "
        "asset-level CAPEX, value created, OPEX, and monthly numbers for exact verification."
    )

    with st.expander(":material/wb_sunny: Isolated Solar Economics (Chart & 12-Month Table)", expanded=False):
        if not cur_sys.enable_solar:
            st.info(":material/info: Enable **Solar PV** in Tab 2 or Tab 5 to view isolated solar economics.")
        else:
            sol_pb = f"{fk.solar_isolated_payback_years:.1f} yrs" if fk.solar_isolated_payback_years is not None else "N/A"
            sc1, sc2, sc3, sc4 = st.columns(4)
            with sc1:
                render_kpi_card(
                    title="Solar Investment (CAPEX)",
                    value=_fmt_curr(fk.solar_capex_eur, curr),
                    subtext=f"{sim_res.solar_derivation.installed_kwp:,.1f} kWp installed",
                    status="default",
                )
            with sc2:
                render_kpi_card(
                    title="Gross Annual Solar Value",
                    value=f"{_fmt_curr(fk.solar_gross_value_y1_eur, curr)} / yr",
                    subtext=f"Direct + Battery-shifted + {_fmt_curr(fk.solar_export_revenue_eur, curr)} export",
                    status="ok",
                )
            with sc3:
                render_kpi_card(
                    title="Net Annual Solar Value (after O&M)",
                    value=f"{_fmt_curr(fk.solar_net_value_y1_eur, curr, signed=True)} / yr",
                    subtext=f"Annual O&M: {_fmt_curr(fk.solar_om_eur, curr)}/yr",
                    status="ok" if fk.solar_net_value_y1_eur > 0 else "alert",
                )
            with sc4:
                render_kpi_card(
                    title="Isolated Payback & LCOE",
                    value=f"{sol_pb} | {_curr_prefix(curr)}{fk.solar_isolated_lcoe_eur_kwh:,.3f}/kWh",
                    subtext=f"15Y annualized cost across {kpis.solar_total_generation_kwh / 1000.0:,.1f} MWh/yr",
                    status="ok" if fk.solar_isolated_payback_years is not None else "default",
                )
            st.plotly_chart(
                create_solar_isolated_financial_figure(sim_res),
                use_container_width=True,
                config={"scrollZoom": False, "displayModeBar": "hover", "responsive": True},
                key="comb_iso_solar_chart",
            )
            if sim_res.solar_fin_monthly_df is not None and not sim_res.solar_fin_monthly_df.empty:
                st.dataframe(_rename_df_currency_cols(sim_res.solar_fin_monthly_df, curr), use_container_width=True, hide_index=True)

    with st.expander(":material/battery_charging_full: Isolated Battery Economics (Chart & 12-Month Table)", expanded=False):
        if not cur_sys.enable_battery:
            st.info(":material/info: Enable **Battery Storage** in Tab 3 or Tab 5 to view isolated battery economics.")
        else:
            bat_pb = f"{fk.battery_isolated_payback_years:.1f} yrs" if fk.battery_isolated_payback_years is not None else "N/A"
            bc1, bc2, bc3, bc4 = st.columns(4)
            with bc1:
                render_kpi_card(
                    title="Battery Investment (CAPEX)",
                    value=_fmt_curr(fk.battery_capex_eur, curr),
                    subtext=f"{cur_sys.battery_capacity_kwh:,.0f} kWh / {cur_sys.battery_power_kw:,.0f} kW",
                    status="default",
                )
            with bc2:
                render_kpi_card(
                    title="Attributed Peak & Shift Value",
                    value=f"{_fmt_curr(fk.battery_gross_value_y1_eur, curr)} / yr",
                    subtext=f"Peak savings: {_fmt_curr(fk.battery_peak_savings_y1_eur, curr)} | Solar shift: {_fmt_curr(fk.solar_stored_value_y1_eur, curr)}",
                    status="ok" if fk.battery_gross_value_y1_eur > 0 else "default",
                )
            with bc3:
                render_kpi_card(
                    title="Net Annual Battery Value",
                    value=f"{_fmt_curr(fk.battery_net_value_y1_eur, curr, signed=True)} / yr",
                    subtext=f"O&M: {_fmt_curr(fk.battery_om_eur, curr)} | Grid charge: {_fmt_curr(fk.battery_grid_charge_cost_y1_eur, curr)}",
                    status="ok" if fk.battery_net_value_y1_eur > 0 else "alert",
                )
            with bc4:
                render_kpi_card(
                    title="Isolated Payback & Cost/kWh",
                    value=f"{bat_pb} | {_curr_prefix(curr)}{fk.battery_cost_per_discharged_kwh:,.3f}/kWh",
                    subtext=f"{kpis.battery_total_discharged_kwh:,.0f} kWh discharged ({kpis.battery_equivalent_cycles:.1f} cyc/yr)",
                    status="ok" if fk.battery_isolated_payback_years is not None else "default",
                )
            st.plotly_chart(
                create_battery_isolated_financial_figure(sim_res),
                use_container_width=True,
                config={"scrollZoom": False, "displayModeBar": "hover", "responsive": True},
                key="comb_iso_battery_chart",
            )
            if sim_res.battery_fin_monthly_df is not None and not sim_res.battery_fin_monthly_df.empty:
                st.dataframe(_rename_df_currency_cols(sim_res.battery_fin_monthly_df, curr), use_container_width=True, hide_index=True)

    with st.expander(":material/settings_input_component: Isolated Generator Economics (Chart & 12-Month Table)", expanded=False):
        if not cur_sys.enable_generator:
            st.info(":material/info: Enable **Generator** in Tab 4 or Tab 5 to view isolated generator economics.")
        else:
            gen_pb = f"{fk.generator_isolated_payback_years:.1f} yrs" if fk.generator_isolated_payback_years is not None else "N/A"
            gc1, gc2, gc3, gc4 = st.columns(4)
            with gc1:
                render_kpi_card(
                    title="Generator CAPEX & Model",
                    value=_fmt_curr(fk.generator_capex_eur, curr),
                    subtext=f"{cur_sys.generator_rated_kw:,.0f} kW ({sim_res.financial_config.generator_cost_model if sim_res.financial_config else 'Purchase'})",
                    status="default",
                )
            with gc2:
                render_kpi_card(
                    title="Attributed Peak & Penalty Savings",
                    value=f"{_fmt_curr(fk.generator_peak_savings_y1_eur, curr)} / yr",
                    subtext=f"{kpis.generator_total_generation_kwh:,.0f} kWh generated in {kpis.generator_runtime_hours:,.1f} hrs",
                    status="ok" if fk.generator_peak_savings_y1_eur > 0 else "default",
                )
            with gc3:
                render_kpi_card(
                    title="Annual Fuel, Service & Rental",
                    value=f"{_fmt_curr(fk.generator_total_opex_eur, curr)} / yr",
                    subtext=f"Fuel: {_fmt_curr(fk.generator_fuel_cost_eur, curr)} | O&M: {_fmt_curr(fk.generator_maintenance_cost_eur, curr)} | Rent: {_fmt_curr(fk.generator_rental_cost_eur, curr)}",
                    status="default",
                )
            with gc4:
                render_kpi_card(
                    title="Net Impact & Cost/kWh",
                    value=f"{_fmt_curr(fk.generator_net_value_y1_eur, curr, signed=True)} | {_curr_prefix(curr)}{fk.generator_cost_per_kwh:,.3f}/kWh",
                    subtext=f"Isolated payback: {gen_pb}",
                    status="ok" if fk.generator_net_value_y1_eur >= 0 else "alert",
                )
            st.plotly_chart(
                create_generator_isolated_financial_figure(sim_res),
                use_container_width=True,
                config={"scrollZoom": False, "displayModeBar": "hover", "responsive": True},
                key="comb_iso_generator_chart",
            )
            if sim_res.generator_fin_monthly_df is not None and not sim_res.generator_fin_monthly_df.empty:
                st.dataframe(_rename_df_currency_cols(sim_res.generator_fin_monthly_df, curr), use_container_width=True, hide_index=True)

