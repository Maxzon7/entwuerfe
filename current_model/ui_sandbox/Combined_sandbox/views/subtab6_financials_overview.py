"""
Subtab 6.2 (Hardware & Operating Costs), Subtab 6.3 (Executive 15-Year Overview & Charts),
and top-level `render_subtab6_financials` fragment orchestrator.
"""

import pandas as pd
import streamlit as st

from .state_and_helpers import (
    CombinedSystemConfig,
    CombinedFinancialConfig,
    SystemUtilizationDiagnostics,
    render_kpi_card,
    evaluate_combined_financials,
    compute_system_utilization_diagnostics,
    create_financial_cost_comparison_figure,
    create_financial_tco_trajectory_figure,
    create_financial_waterfall_bridge_figure,
    create_financial_monthly_cashflow_figure,
    create_solar_isolated_financial_figure,
    create_battery_isolated_financial_figure,
    create_generator_isolated_financial_figure,
    _activate_module_callback,
)
from .subtab5_mix_and_rules import render_supply_mix_and_utilization_overview
from .subtab6_financials_bill_and_hardware import (
    _render_master_cost_equation_bar,
    _render_sub_ledger_html,
    _render_subtab6_1_grid_tariffs,
)

@st.fragment
def _render_financial_chart_gallery_fragment(sim_res) -> None:
    """Isolates financial chart perspective switching inside a lightweight fragment."""
    with st.container(border=True):
        st.markdown("##### :material/analytics: Financial Charts")
        gallery_choice = st.radio(
            "Visualization Perspective",
            options=[
                "15-Year Cumulative TCO & Break-Even Trajectory",
                "Annual Cost Bridge (Waterfall)",
                "4-Pillar Annual Cost Comparison",
                "12-Month Seasonal Cashflow",
            ],
            index=0,
            horizontal=True,
            key="comb_fin_chart_gallery_sel",
            label_visibility="collapsed",
        )

        if gallery_choice == "15-Year Cumulative TCO & Break-Even Trajectory":
            fig_fin = create_financial_tco_trajectory_figure(sim_res)
        elif gallery_choice == "Annual Cost Bridge (Waterfall)":
            fig_fin = create_financial_waterfall_bridge_figure(sim_res)
        elif gallery_choice == "4-Pillar Annual Cost Comparison":
            fig_fin = create_financial_cost_comparison_figure(sim_res)
        else:
            fig_fin = create_financial_monthly_cashflow_figure(sim_res)

        st.plotly_chart(
            fig_fin,
            use_container_width=True,
            config={
                "scrollZoom": False,
                "displayModeBar": "hover",
                "responsive": True,
            },
            key=f"comb_fin_gallery_{gallery_choice.replace(' ', '_').replace('(', '').replace(')', '').replace('-', '_').lower()}",
        )


@st.fragment
def _render_cashflow_table_expander_fragment(sim_res) -> None:
    """Isolates the 15-year cashflow table behind a lazy expander + toggle to avoid unnecessary renders."""
    with st.expander(":material/table_chart: 15-Year Cashflow Table", expanded=False):
        show_cf_tbl = st.checkbox(
            "Show 15-Year Table",
            value=True,
            key="comb_fin_show_15y_ledger_chk",
        )
        if show_cf_tbl and sim_res.cashflow_15y_df is not None and not sim_res.cashflow_15y_df.empty:
            st.dataframe(
                sim_res.cashflow_15y_df,
                use_container_width=True,
                hide_index=True,
            )
def _render_subtab6_2_hardware_costs(sim_res, cur_sys: CombinedSystemConfig, cur_fin: CombinedFinancialConfig) -> None:
    """Sub-Tab 6.2: System Hardware & Operating Costs (Component CAPEX/OPEX Inputs + How It Adds Up Sub-Ledgers)."""
    fk = sim_res.financial_kpis
    kpis = sim_res.kpis
    deriv = sim_res.solar_derivation

    with st.form("comb_hardware_costs_form"):
        # --- 1. Solar PV System ---
        sol_badge = f"{deriv.installed_kwp:,.1f} kWp Active" if cur_sys.enable_solar else "INACTIVE — €0"
        with st.expander(f":material/solar_power: Solar Costs ({sol_badge})", expanded=cur_sys.enable_solar):
            s_in, s_led = st.columns([0.44, 0.56], gap="large")
            with s_in:
                sol_mod = st.number_input(
                    "Solar Modules (€/Wp)",
                    min_value=0.0, max_value=3.0, value=float(cur_fin.solar_modules_eur_wp), step=0.02, format="%.2f",
                    key="comb_fin_sol_mod", disabled=not cur_sys.enable_solar,
                )
                sol_inv = st.number_input(
                    "Solar Inverter (€/W)",
                    min_value=0.0, max_value=2.0, value=float(cur_fin.solar_inverter_eur_w), step=0.01, format="%.2f",
                    key="comb_fin_sol_inv", disabled=not cur_sys.enable_solar,
                )
                sol_mnt = st.number_input(
                    "Mounting & Installation (€/Wp)",
                    min_value=0.0, max_value=3.0, value=float(cur_fin.solar_mounting_eur_wp), step=0.02, format="%.2f",
                    key="comb_fin_sol_mnt", disabled=not cur_sys.enable_solar,
                )
                sol_om = st.number_input(
                    "Annual Maintenance (% of CAPEX/yr)",
                    min_value=0.0, max_value=15.0, value=float(cur_fin.solar_om_pct_of_capex), step=0.25,
                    key="comb_fin_sol_om", disabled=not cur_sys.enable_solar,
                )
            with s_led:
                sol_net_benefit = fk.solar_direct_value_y1_eur + fk.solar_export_revenue_eur - fk.solar_om_eur
                sol_rows = [
                    {"group": "Upfront Investment (CAPEX)"},
                    {"cells": ["1.1 Solar Modules", f"{deriv.installed_kwp:,.1f} kWp &times; 1,000 &times; &euro;{cur_fin.solar_modules_eur_wp:.2f}", "&mdash;", f"&euro;{fk.solar_modules_capex_eur:,.0f}"]},
                    {"cells": ["1.2 Solar Inverters", f"{deriv.installed_kwp:,.1f} kWp &times; 1,000 &times; &euro;{cur_fin.solar_inverter_eur_w:.2f}", "&mdash;", f"&euro;{fk.solar_inverter_capex_eur:,.0f}"]},
                    {"cells": ["1.3 Mounting &amp; Installation", f"{deriv.installed_kwp:,.1f} kWp &times; 1,000 &times; &euro;{cur_fin.solar_mounting_eur_wp:.2f}", "&mdash;", f"&euro;{fk.solar_mounting_capex_eur:,.0f}"]},
                    {"group": "Annual Operating Cost &amp; Value Generated"},
                    {"cells": ["Annual Maintenance (O&amp;M)", f"{cur_fin.solar_om_pct_of_capex:.2f}% &times; &euro;{fk.solar_capex_eur:,.0f}", f"-&euro;{fk.solar_om_eur / 12.0:,.0f}", f"-&euro;{fk.solar_om_eur:,.0f}"], "highlight": "#EF4444"},
                    {"cells": ["Direct Electricity Saved", f"{kpis.solar_direct_kwh:,.0f} kWh &times; &euro;{fk.variable_grid_rate_eur_kwh:.3f}", f"+&euro;{fk.solar_direct_value_y1_eur / 12.0:,.0f}", f"+&euro;{fk.solar_direct_value_y1_eur:,.0f}"], "highlight": "#22C55E"},
                    {"cells": ["Export Feed-in Revenue", f"{kpis.solar_export_kwh:,.0f} kWh &times; &euro;{cur_fin.solar_export_feed_in_eur_kwh:.3f}", f"+&euro;{fk.solar_export_revenue_eur / 12.0:,.0f}", f"+&euro;{fk.solar_export_revenue_eur:,.0f}"], "highlight": "#22C55E"},
                ]
                st.markdown(
                    _render_sub_ledger_html(
                        header_title=f"Solar PV Financial Breakdown (Total CAPEX: &euro;{fk.solar_capex_eur:,.0f})",
                        columns=["Line Item", "Calculation (Qty &times; Rate)", "Monthly", "One-Off / Annual"],
                        rows=sol_rows,
                        footer_cells=[
                            "= NET ANNUAL SOLAR VALUE (AFTER O&amp;M)",
                            f"&euro;{sol_net_benefit / 12.0:+,.0f}/mo",
                            f"&euro;{sol_net_benefit:+,.0f}/yr",
                        ],
                        accent_color="#FACC15",
                        is_enabled=cur_sys.enable_solar,
                    ),
                    unsafe_allow_html=True,
                )

        # --- 2. Battery Storage (BESS) ---
        bat_badge = f"{cur_sys.battery_capacity_kwh:,.0f} kWh / {cur_sys.battery_power_kw:,.0f} kW Active" if cur_sys.enable_battery else "INACTIVE — €0"
        with st.expander(f":material/battery_charging_full: Battery Costs ({bat_badge})", expanded=cur_sys.enable_battery):
            b_in, b_led = st.columns([0.44, 0.56], gap="large")
            with b_in:
                b1, b2 = st.columns(2)
                with b1:
                    bat_rack = st.number_input(
                        "Storage Racks (€/kWh)",
                        min_value=0.0, max_value=2000.0, value=float(cur_fin.battery_capex_eur_kwh), step=10.0,
                        key="comb_fin_bat_rack", disabled=not cur_sys.enable_battery,
                    )
                    bat_bop = st.number_input(
                        "Installation & Cabling (€)",
                        min_value=0.0, max_value=500000.0, value=float(cur_fin.battery_fixed_bop_eur), step=1000.0,
                        key="comb_fin_bat_bop", disabled=not cur_sys.enable_battery,
                    )
                with b2:
                    bat_inv = st.number_input(
                        "Power Inverter (€/kW)",
                        min_value=0.0, max_value=2000.0, value=float(cur_fin.battery_capex_eur_kw), step=10.0,
                        key="comb_fin_bat_inv", disabled=not cur_sys.enable_battery,
                    )
                    bat_om = st.number_input(
                        "Annual Maintenance (% of CAPEX/yr)",
                        min_value=0.0, max_value=15.0, value=float(cur_fin.battery_om_pct_of_capex), step=0.25,
                        key="comb_fin_bat_om", disabled=not cur_sys.enable_battery,
                    )
                a1, a2, a3 = st.columns([1.3, 0.85, 0.85])
                with a1:
                    en_aug = st.checkbox(
                        "Mid-Life Cell Replacement",
                        value=bool(cur_fin.enable_battery_augmentation),
                        key="comb_fin_bat_aug_chk", disabled=not cur_sys.enable_battery,
                    )
                with a2:
                    aug_yr = st.number_input(
                        "Year", min_value=5, max_value=14, value=int(cur_fin.battery_augmentation_year), step=1,
                        key="comb_fin_bat_aug_yr", disabled=not cur_sys.enable_battery,
                    )
                with a3:
                    aug_pct = st.number_input(
                        "Cost (% Racks)", min_value=10.0, max_value=100.0, value=float(cur_fin.battery_augmentation_pct_of_racks), step=5.0,
                        key="comb_fin_bat_aug_pct", disabled=not cur_sys.enable_battery,
                    )
            with b_led:
                bat_rows = [
                    {"group": "Upfront Investment (CAPEX)"},
                    {"cells": ["2.1 Storage Racks", f"{cur_sys.battery_capacity_kwh:,.0f} kWh &times; &euro;{cur_fin.battery_capex_eur_kwh:,.0f}/kWh", "&mdash;", f"&euro;{fk.battery_rack_capex_eur:,.0f}"]},
                    {"cells": ["2.2 Bidirectional Inverter", f"{cur_sys.battery_power_kw:,.0f} kW &times; &euro;{cur_fin.battery_capex_eur_kw:,.0f}/kW", "&mdash;", f"&euro;{fk.battery_inverter_capex_eur:,.0f}"]},
                    {"cells": ["2.3 Installation &amp; Cabling", "Fixed Balance of Plant", "&mdash;", f"&euro;{fk.battery_bop_capex_eur:,.0f}"]},
                    {"cells": [f"Planned Cell Replacement (Yr {int(cur_fin.battery_augmentation_year)})", f"{cur_fin.battery_augmentation_pct_of_racks:.0f}% of Racks (if enabled)", "&mdash;", f"&euro;{fk.battery_augmentation_eur:,.0f}"]},
                    {"group": "Annual Operating Cost &amp; Value Enabled"},
                    {"cells": ["Annual Battery Maintenance (O&amp;M)", f"{cur_fin.battery_om_pct_of_capex:.2f}% &times; &euro;{fk.battery_capex_eur:,.0f}", f"&euro;{fk.battery_om_eur / 12.0:,.0f}", f"&euro;{fk.battery_om_eur:,.0f}"], "highlight": "#EF4444"},
                    {"cells": ["Stored Solar Discharged", f"{kpis.solar_via_battery_kwh:,.0f} kWh &times; &euro;{fk.variable_grid_rate_eur_kwh:.3f}", f"+&euro;{fk.solar_stored_value_y1_eur / 12.0:,.0f}", f"+&euro;{fk.solar_stored_value_y1_eur:,.0f}"], "highlight": "#22C55E"},
                    {"cells": ["Peak Shaving &amp; Penalty Savings", f"Shared peak reduction ({kpis.peak_reduction_kw:,.1f} kW)", f"+&euro;{fk.grid_peak_and_penalty_savings_y1_eur / 12.0:,.0f}", f"+&euro;{fk.grid_peak_and_penalty_savings_y1_eur:,.0f}"], "highlight": "#22C55E"},
                ]
                st.markdown(
                    _render_sub_ledger_html(
                        header_title=f"Battery Storage (BESS) Financial Breakdown (Total CAPEX: &euro;{fk.battery_capex_eur:,.0f})",
                        columns=["Line Item", "Calculation (Qty &times; Rate)", "Monthly", "One-Off / Annual"],
                        rows=bat_rows,
                        footer_cells=[
                            "= ANNUAL BATTERY MAINTENANCE (O&amp;M)",
                            f"&euro;{fk.battery_om_eur / 12.0:,.0f}/mo",
                            f"&euro;{fk.battery_om_eur:,.0f}/yr",
                        ],
                        accent_color="#22C55E",
                        is_enabled=cur_sys.enable_battery,
                    ),
                    unsafe_allow_html=True,
                )

        # --- 3. Peaking Generator ---
        gen_badge = f"{cur_sys.generator_rated_kw:,.0f} kW {cur_sys.fuel_type} Active" if cur_sys.enable_generator else "INACTIVE — €0"
        with st.expander(f":material/power: Generator Costs ({gen_badge})", expanded=cur_sys.enable_generator):
            gn_in, gn_led = st.columns([0.44, 0.56], gap="large")
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
                        "Purchase Price (€)",
                        min_value=0.0, max_value=2000000.0, value=float(cur_fin.generator_capex_eur), step=1000.0,
                        key="comb_fin_gen_capex", disabled=not cur_sys.enable_generator,
                    )
                    fuel_pr = st.number_input(
                        f"Fuel Price (€/{kpis.generator_fuel_unit})",
                        min_value=0.0, max_value=10.0, value=float(cur_fin.fuel_price_eur_per_unit), step=0.05, format="%.2f",
                        key="comb_fin_gen_fuel", disabled=not cur_sys.enable_generator,
                    )
                with g_c2:
                    gen_rent = st.number_input(
                        "Monthly Rental (€/mo)",
                        min_value=0.0, max_value=100000.0, value=float(cur_fin.generator_rental_eur_month), step=100.0,
                        key="comb_fin_gen_rent", disabled=not cur_sys.enable_generator,
                    )
                    gen_maint = st.number_input(
                        "Maintenance (€/op hr)",
                        min_value=0.0, max_value=500.0, value=float(cur_fin.generator_maintenance_eur_per_hour), step=0.5,
                        key="comb_fin_gen_maint", disabled=not cur_sys.enable_generator,
                    )
            with gn_led:
                gen_rows = [
                    {"group": f"Acquisition ({cur_fin.generator_cost_model})"},
                    {"cells": ["3.1 Purchase Investment (CAPEX)", "One-off purchase (if selected)", "&mdash;", f"&euro;{fk.generator_capex_eur:,.0f}"]},
                    {"cells": ["3.2 Rental / Leasing Fee (OPEX)", f"12 mos &times; &euro;{cur_fin.generator_rental_eur_month:,.0f}/mo (if rental)", f"&euro;{fk.generator_rental_cost_eur / 12.0:,.0f}", f"&euro;{fk.generator_rental_cost_eur:,.0f}"]},
                    {"group": "Annual Fuel &amp; Operating Maintenance"},
                    {"cells": [f"3.3 Fuel Consumption ({cur_sys.fuel_type})", f"{kpis.generator_fuel_total:,.1f} {kpis.generator_fuel_unit} &times; &euro;{cur_fin.fuel_price_eur_per_unit:.2f}", f"&euro;{fk.generator_fuel_cost_eur / 12.0:,.0f}", f"&euro;{fk.generator_fuel_cost_eur:,.0f}"]},
                    {"cells": ["3.4 Running Hour Service", f"{kpis.generator_runtime_hours:,.1f} hrs &times; &euro;{cur_fin.generator_maintenance_eur_per_hour:.2f}/hr", f"&euro;{fk.generator_maintenance_cost_eur / 12.0:,.0f}", f"&euro;{fk.generator_maintenance_cost_eur:,.0f}"]},
                ]
                st.markdown(
                    _render_sub_ledger_html(
                        header_title=f"Generator Financial Breakdown (Generated to Load: {kpis.generator_to_load_kwh:,.0f} kWh/yr)",
                        columns=["Line Item", "Calculation (Qty &times; Rate)", "Monthly", "One-Off / Annual"],
                        rows=gen_rows,
                        footer_cells=[
                            "= TOTAL GENERATOR ANNUAL OPEX",
                            f"&euro;{fk.generator_total_opex_eur / 12.0:,.0f}/mo",
                            f"&euro;{fk.generator_total_opex_eur:,.0f}/yr",
                        ],
                        accent_color="#F97316",
                        is_enabled=cur_sys.enable_generator,
                    ),
                    unsafe_allow_html=True,
                )

        # --- 4. Avoided Grid Expansion Credits ---
        with st.expander(":material/savings: Saved Grid Upgrade Cost", expanded=bool(cur_fin.avoided_grid_upgrade_capex_eur > 0.0 or cur_fin.strict_grid_congestion_mode)):
            av_in, av_led = st.columns([0.44, 0.56], gap="large")
            with av_in:
                if cur_fin.strict_grid_congestion_mode:
                    st.session_state["comb_fin_avoided_upgrade"] = 0.0
                avoided_upgrade = st.number_input(
                    "One-Off Avoided Grid Upgrade Cost (€)",
                    min_value=0.0,
                    max_value=5000000.0,
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
                    f"Gross Hardware CAPEX (**€{fk.gross_capex_eur:,.0f}**) &minus; Avoided Grid Upgrade (**€{fk.avoided_grid_upgrade_capex_eur:,.0f}**) "
                    f"= **Net Turnkey Investment: €{fk.total_capex_eur:,.0f}**."
                )

        hw_submitted = st.form_submit_button(
            "Apply Hardware & Operating Costs",
            icon=":material/check_circle:",
            type="primary",
            use_container_width=True,
        )

    if hw_submitted:
        if cur_sys.enable_solar:
            cur_fin.solar_modules_eur_wp = float(sol_mod)
            cur_fin.solar_inverter_eur_w = float(sol_inv)
            cur_fin.solar_mounting_eur_wp = float(sol_mnt)
            cur_fin.solar_capex_eur_kwp = None
            cur_fin.solar_om_pct_of_capex = float(sol_om)

        if cur_sys.enable_battery:
            cur_fin.battery_capex_eur_kwh = float(bat_rack)
            cur_fin.battery_capex_eur_kw = float(bat_inv)
            cur_fin.battery_fixed_bop_eur = float(bat_bop)
            cur_fin.battery_om_pct_of_capex = float(bat_om)
            cur_fin.enable_battery_augmentation = bool(en_aug)
            cur_fin.battery_augmentation_year = int(aug_yr)
            cur_fin.battery_augmentation_pct_of_racks = float(aug_pct)

        if cur_sys.enable_generator:
            cur_fin.generator_cost_model = str(gen_model)
            cur_fin.generator_capex_eur = float(gen_capex)
            cur_fin.generator_rental_eur_month = float(gen_rent)
            cur_fin.fuel_price_eur_per_unit = float(fuel_pr)
            cur_fin.generator_maintenance_eur_per_hour = float(gen_maint)

        cur_fin.avoided_grid_upgrade_capex_eur = 0.0 if cur_fin.strict_grid_congestion_mode else float(avoided_upgrade)
        evaluate_combined_financials(sim_res, cur_fin)
        st.session_state.pop("comb_cached_excel_bytes", None)
        st.rerun(scope="fragment")

    _render_isolated_component_economics_fragment(sim_res, cur_sys)


@st.fragment
def _render_isolated_component_economics_fragment(sim_res, cur_sys: CombinedSystemConfig) -> None:
    """Isolated Solar, Battery, and Generator economics with KPIs, Plotly charts, and 12-month verification tables."""
    fk = sim_res.financial_kpis
    kpis = sim_res.kpis
    if fk is None:
        return

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
                    value=f"€{fk.solar_capex_eur:,.0f}",
                    subtext=f"{sim_res.solar_derivation.installed_kwp:,.1f} kWp installed",
                    status="default",
                )
            with sc2:
                render_kpi_card(
                    title="Gross Annual Solar Value",
                    value=f"€{fk.solar_gross_value_y1_eur:,.0f} / yr",
                    subtext=f"Direct + Battery-shifted + €{fk.solar_export_revenue_eur:,.0f} export",
                    status="ok",
                )
            with sc3:
                render_kpi_card(
                    title="Net Annual Solar Value (after O&M)",
                    value=f"€{fk.solar_net_value_y1_eur:+,.0f} / yr",
                    subtext=f"Annual O&M: €{fk.solar_om_eur:,.0f}/yr",
                    status="ok" if fk.solar_net_value_y1_eur > 0 else "alert",
                )
            with sc4:
                render_kpi_card(
                    title="Isolated Payback & LCOE",
                    value=f"{sol_pb} | €{fk.solar_isolated_lcoe_eur_kwh:.3f}/kWh",
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
                st.dataframe(sim_res.solar_fin_monthly_df, use_container_width=True, hide_index=True)

    with st.expander(":material/battery_charging_full: Isolated Battery Economics (Chart & 12-Month Table)", expanded=False):
        if not cur_sys.enable_battery:
            st.info(":material/info: Enable **Battery Storage** in Tab 3 or Tab 5 to view isolated battery economics.")
        else:
            bat_pb = f"{fk.battery_isolated_payback_years:.1f} yrs" if fk.battery_isolated_payback_years is not None else "N/A"
            bc1, bc2, bc3, bc4 = st.columns(4)
            with bc1:
                render_kpi_card(
                    title="Battery Investment (CAPEX)",
                    value=f"€{fk.battery_capex_eur:,.0f}",
                    subtext=f"{cur_sys.battery_capacity_kwh:,.0f} kWh / {cur_sys.battery_power_kw:,.0f} kW",
                    status="default",
                )
            with bc2:
                render_kpi_card(
                    title="Attributed Peak & Shift Value",
                    value=f"€{fk.battery_gross_value_y1_eur:,.0f} / yr",
                    subtext=f"Peak savings: €{fk.battery_peak_savings_y1_eur:,.0f} | Solar shift: €{fk.solar_stored_value_y1_eur:,.0f}",
                    status="ok" if fk.battery_gross_value_y1_eur > 0 else "default",
                )
            with bc3:
                render_kpi_card(
                    title="Net Annual Battery Value",
                    value=f"€{fk.battery_net_value_y1_eur:+,.0f} / yr",
                    subtext=f"O&M: €{fk.battery_om_eur:,.0f} | Grid charge: €{fk.battery_grid_charge_cost_y1_eur:,.0f}",
                    status="ok" if fk.battery_net_value_y1_eur > 0 else "alert",
                )
            with bc4:
                render_kpi_card(
                    title="Isolated Payback & Cost/kWh",
                    value=f"{bat_pb} | €{fk.battery_cost_per_discharged_kwh:.3f}/kWh",
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
                st.dataframe(sim_res.battery_fin_monthly_df, use_container_width=True, hide_index=True)

    with st.expander(":material/settings_input_component: Isolated Generator Economics (Chart & 12-Month Table)", expanded=False):
        if not cur_sys.enable_generator:
            st.info(":material/info: Enable **Generator** in Tab 4 or Tab 5 to view isolated generator economics.")
        else:
            gen_pb = f"{fk.generator_isolated_payback_years:.1f} yrs" if fk.generator_isolated_payback_years is not None else "N/A"
            gc1, gc2, gc3, gc4 = st.columns(4)
            with gc1:
                render_kpi_card(
                    title="Generator CAPEX & Model",
                    value=f"€{fk.generator_capex_eur:,.0f}",
                    subtext=f"{cur_sys.generator_rated_kw:,.0f} kW ({sim_res.financial_config.generator_cost_model if sim_res.financial_config else 'Purchase'})",
                    status="default",
                )
            with gc2:
                render_kpi_card(
                    title="Attributed Peak & Penalty Savings",
                    value=f"€{fk.generator_peak_savings_y1_eur:,.0f} / yr",
                    subtext=f"{kpis.generator_total_generation_kwh:,.0f} kWh generated in {kpis.generator_runtime_hours:,.1f} hrs",
                    status="ok" if fk.generator_peak_savings_y1_eur > 0 else "default",
                )
            with gc3:
                render_kpi_card(
                    title="Annual Fuel, Service & Rental",
                    value=f"€{fk.generator_total_opex_eur:,.0f} / yr",
                    subtext=f"Fuel: €{fk.generator_fuel_cost_eur:,.0f} | O&M: €{fk.generator_maintenance_cost_eur:,.0f} | Rent: €{fk.generator_rental_cost_eur:,.0f}",
                    status="default",
                )
            with gc4:
                render_kpi_card(
                    title="Net Impact & Cost/kWh",
                    value=f"€{fk.generator_net_value_y1_eur:+,.0f} | €{fk.generator_cost_per_kwh:.3f}/kWh",
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
                st.dataframe(sim_res.generator_fin_monthly_df, use_container_width=True, hide_index=True)


def _render_subtab6_3_executive_overview(sim_res, cur_sys: CombinedSystemConfig, cur_fin: CombinedFinancialConfig) -> None:
    """Sub-Tab 6.3: Executive Summary, 15-Year Dynamics, Component Cost Matrix & Financial Charts."""
    # Long-Term Escalation, Degradation & Discount Rate Form
    with st.form("comb_fin_longterm_form"):
        st.markdown("##### :material/trending_up: Price Increases & Lifespan")
        lt1, lt2, lt3, lt4, lt_btn = st.columns([1.0, 1.0, 1.0, 1.0, 1.1])
        with lt1:
            tariff_esc = st.number_input(
                "Tariff Escalation (% p.a.)",
                min_value=0.0, max_value=15.0, value=float(cur_fin.tariff_escalation_pct_pa), step=0.5,
                key="comb_fin_tariff_esc",
                help="Annual electricity & grid tariff inflation.",
            )
        with lt2:
            om_inf = st.number_input(
                "O&M Inflation (% p.a.)",
                min_value=0.0, max_value=15.0, value=float(cur_fin.om_inflation_pct_pa), step=0.5,
                key="comb_fin_om_inf",
                help="Annual inflation for hardware maintenance and fuel.",
            )
        with lt3:
            sys_deg = st.number_input(
                "System Degradation (% p.a.)",
                min_value=0.0, max_value=5.0, value=float(cur_fin.system_degradation_pct_pa), step=0.1, format="%.2f",
                key="comb_fin_sys_deg",
                help="Annual yield/capacity degradation of solar & battery.",
            )
        with lt4:
            disc_rate = st.number_input(
                "Discount Rate for NPV (%)",
                min_value=0.0, max_value=20.0, value=float(cur_fin.discount_rate_pct), step=0.5,
                key="comb_fin_disc_rate",
            )
        with lt_btn:
            st.write("")
            st.write("")
            lt_submitted = st.form_submit_button(
                "Update Projection",
                icon=":material/refresh:",
                type="primary",
                use_container_width=True,
            )

    if lt_submitted:
        cur_fin.tariff_escalation_pct_pa = float(tariff_esc)
        cur_fin.om_inflation_pct_pa = float(om_inf)
        cur_fin.system_degradation_pct_pa = float(sys_deg)
        cur_fin.discount_rate_pct = float(disc_rate)
        evaluate_combined_financials(sim_res, cur_fin)
        st.session_state.pop("comb_cached_excel_bytes", None)
        st.rerun(scope="fragment")

    fin_kpis = sim_res.financial_kpis

    # Economic Bottleneck Alert (Automatic Diagnostic)
    if cur_sys.enable_battery and fin_kpis.battery_om_eur > 0:
        bat_om = fin_kpis.battery_om_eur
        gross_sav = fin_kpis.gross_bill_savings_y1_eur
        bat_capex = fin_kpis.battery_capex_eur
        if bat_om > 0.5 * max(1.0, gross_sav) or (gross_sav > 0 and fin_kpis.annual_savings_eur <= 0):
            st.warning(
                f"**:material/lightbulb: Economic Bottleneck Alert:** Annual battery maintenance (€{bat_om:,.0f}/yr from €{bat_capex:,.0f} CAPEX) "
                f"consumes {(bat_om / max(1.0, gross_sav) * 100.0):.1f}% of the gross electricity bill savings (€{gross_sav:,.0f}/yr). "
                f"Tip: Selecting an 80% battery capacity target or pairing a smaller battery with a peaking generator "
                f"substantially reduces CAPEX and O&M costs."
            )

    st.markdown("##### :material/account_balance: Financial Summary")

    # Single Clear 4-Card Headline Overview
    fk1, fk2, fk3, fk4 = st.columns(4)
    pb_str = f"{fin_kpis.payback_years:.1f} yrs" if fin_kpis.payback_years is not None else "N/A"
    disc_pb_str = f"{fin_kpis.discounted_payback_years:.1f} yrs" if fin_kpis.discounted_payback_years is not None else "N/A"
    irr_str = f"{fin_kpis.irr_15y_pct:.1f}%" if fin_kpis.irr_15y_pct is not None else "N/A"
    with fk1:
        capex_subtext = (
            f"Gross: €{fin_kpis.gross_capex_eur:,.0f} | Avoided: -€{fin_kpis.avoided_grid_upgrade_capex_eur:,.0f}"
            if fin_kpis.avoided_grid_upgrade_capex_eur > 0
            else f"Solar: €{fin_kpis.solar_capex_eur:,.0f} | Battery: €{fin_kpis.battery_capex_eur:,.0f} | Gen: €{fin_kpis.generator_capex_eur:,.0f}"
        )
        render_kpi_card(
            title="Total Investment",
            value=f"€{fin_kpis.total_capex_eur:,.0f}",
            subtext=capex_subtext,
            status="default",
        )
    with fk2:
        render_kpi_card(
            title="Annual Savings (Year 1)",
            value=f"€{fin_kpis.annual_savings_eur:+,.0f} / yr",
            subtext=f"New annual cost: €{fin_kpis.total_annual_opex_eur:,.0f} vs. €{fin_kpis.baseline_total_opex_eur:,.0f} current",
            status="ok" if fin_kpis.annual_savings_eur > 0 else "alert",
        )
    with fk3:
        render_kpi_card(
            title="Payback Period",
            value=pb_str,
            subtext="Years until investment is paid back",
            status="ok" if fin_kpis.payback_years is not None else "alert",
        )
    with fk4:
        render_kpi_card(
            title="15-Year Net Profit",
            value=f"€{fin_kpis.tco_15y_savings_eur:+,.0f}",
            subtext=f"15Y total cost: €{fin_kpis.tco_15y_combined_eur:,.0f} vs. €{fin_kpis.tco_15y_baseline_eur:,.0f} current",
            status="ok" if fin_kpis.tco_15y_savings_eur > 0 else "alert",
        )

    if cur_fin.strict_grid_congestion_mode:
        if fin_kpis.grid_congestion_compliant:
            st.success(
                f":material/verified: **Strict Grid Congestion Lock Active — Compliant:** "
                f"System stays within the {cur_sys.grid_limit_kw:,.0f} kW contracted limit all year without grid upgrades."
            )
        else:
            st.error(
                f":material/gpp_bad: **Strict Grid Congestion Lock Active — Violation:** "
                f"Grid peak reaches {sim_res.kpis.new_grid_peak_kw:,.1f} kW (+{fin_kpis.grid_congestion_breach_kw:,.1f} kW over limit). "
                f"Avoided grid upgrade CAPEX is locked at €0; adjust Battery, Generator, or Load Mix in Tab 5."
            )

    # Complete Component & Cost Summary Matrix
    with st.container(border=True):
        st.markdown("##### :material/summarize: System Cost Summary")
        comp_rows = [
            {"cells": ["1. Electricity Supply (Retailer)", "&euro;0", f"&euro;{fin_kpis.baseline_pillar1_supply_eur:,.0f}", f"&euro;{fin_kpis.combined_pillar1_supply_eur:,.0f}", f"&euro;{fin_kpis.baseline_pillar1_supply_eur - fin_kpis.combined_pillar1_supply_eur:+,.0f}"], "highlight": "#22C55E" if fin_kpis.baseline_pillar1_supply_eur > fin_kpis.combined_pillar1_supply_eur else None},
            {"cells": ["2. Grid Network (DSO &amp; Peaks)", f"-&euro;{fin_kpis.avoided_grid_upgrade_capex_eur:,.0f}" if fin_kpis.avoided_grid_upgrade_capex_eur > 0 else "&euro;0", f"&euro;{fin_kpis.baseline_pillar2_dso_eur:,.0f}", f"&euro;{fin_kpis.combined_pillar2_dso_eur:,.0f}", f"&euro;{fin_kpis.baseline_pillar2_dso_eur - fin_kpis.combined_pillar2_dso_eur:+,.0f}"], "highlight": "#22C55E" if fin_kpis.baseline_pillar2_dso_eur > fin_kpis.combined_pillar2_dso_eur else None},
            {"cells": ["3. Metering &amp; Statutory Taxes", "&euro;0", f"&euro;{fin_kpis.baseline_pillar3_metering_eur + fin_kpis.baseline_pillar4_taxes_eur:,.0f}", f"&euro;{fin_kpis.combined_pillar3_metering_eur + fin_kpis.combined_pillar4_taxes_eur:,.0f}", f"&euro;{(fin_kpis.baseline_pillar3_metering_eur + fin_kpis.baseline_pillar4_taxes_eur) - (fin_kpis.combined_pillar3_metering_eur + fin_kpis.combined_pillar4_taxes_eur):+,.0f}"], "highlight": "#22C55E" if fin_kpis.baseline_pillar4_taxes_eur > fin_kpis.combined_pillar4_taxes_eur else None},
            {"cells": ["4. Solar PV System (O&amp;M)", f"&euro;{fin_kpis.solar_capex_eur:,.0f}", "&euro;0", f"&euro;{fin_kpis.solar_om_eur:,.0f}", f"-&euro;{fin_kpis.solar_om_eur:,.0f}" if fin_kpis.solar_om_eur > 0 else "&euro;0"], "highlight": "#EF4444" if fin_kpis.solar_om_eur > 0 else None},
            {"cells": ["5. Battery Storage BESS (O&amp;M)", f"&euro;{fin_kpis.battery_capex_eur:,.0f}", "&euro;0", f"&euro;{fin_kpis.battery_om_eur:,.0f}", f"-&euro;{fin_kpis.battery_om_eur:,.0f}" if fin_kpis.battery_om_eur > 0 else "&euro;0"], "highlight": "#EF4444" if fin_kpis.battery_om_eur > 0 else None},
            {"cells": ["6. Peaking Generator (Fuel &amp; Service)", f"&euro;{fin_kpis.generator_capex_eur:,.0f}", "&euro;0", f"&euro;{fin_kpis.generator_total_opex_eur:,.0f}", f"-&euro;{fin_kpis.generator_total_opex_eur:,.0f}" if fin_kpis.generator_total_opex_eur > 0 else "&euro;0"], "highlight": "#EF4444" if fin_kpis.generator_total_opex_eur > 0 else None},
            {"cells": ["7. Solar Export Feed-in Revenue", "&euro;0", "&euro;0", f"-&euro;{fin_kpis.solar_export_revenue_eur:,.0f}" if fin_kpis.solar_export_revenue_eur > 0 else "&euro;0", f"+&euro;{fin_kpis.solar_export_revenue_eur:,.0f}" if fin_kpis.solar_export_revenue_eur > 0 else "&euro;0"], "highlight": "#22C55E" if fin_kpis.solar_export_revenue_eur > 0 else None},
        ]
        st.markdown(
            _render_sub_ledger_html(
                header_title="Costs &amp; Savings by Component",
                columns=["Cost Component", "One-Off CAPEX", "Current (/yr)", "With System (/yr)", "Annual Impact (/yr)"],
                rows=comp_rows,
                footer_cells=[
                    "= TOTAL COMBINED SYSTEM (NET)",
                    f"&euro;{fin_kpis.total_capex_eur:,.0f}",
                    f"&euro;{fin_kpis.baseline_total_opex_eur:,.0f}/yr",
                    f"&euro;{fin_kpis.total_annual_opex_eur:,.0f}/yr",
                    f"&euro;{fin_kpis.annual_savings_eur:+,.0f}/yr",
                ],
                accent_color="#10B981",
                is_enabled=True,
            ),
            unsafe_allow_html=True,
        )

    # Secondary Technical & Contract Indicators (collapsed by default for clean screen clarity)
    with st.expander(":material/analytics: Additional Financial & Contract Indicators (NPV, IRR, LCOE & Contract Split)", expanded=False):
        cong_val = (
            f"Compliant (0 breach mos, Peak {sim_res.kpis.new_grid_peak_kw:,.1f} <= {cur_sys.grid_limit_kw:,.0f} kW)"
            if fin_kpis.grid_congestion_compliant
            else f"Breach (+{fin_kpis.grid_congestion_breach_kw:,.1f} kW across {fin_kpis.grid_congestion_breach_months} mos)"
        )
        ind_df = pd.DataFrame([
            {"Indicator": "Discounted Payback", "Value": disc_pb_str, "Notes": f"Break-even discounted at {cur_fin.discount_rate_pct:.1f}% p.a."},
            {"Indicator": "15-Year NPV & IRR", "Value": f"€{fin_kpis.npv_15y_eur:+,.0f} | IRR: {irr_str}", "Notes": f"Discounted net present value at {cur_fin.discount_rate_pct:.1f}%"},
            {"Indicator": "15-Year Benefit-Cost Ratio (BCR)", "Value": f"{fin_kpis.benefit_cost_ratio_15y:.2f}x", "Notes": "Discounted 15-year savings divided by Net CAPEX"},
            {"Indicator": "On-Site Energy Cost vs. Grid", "Value": f"€{fin_kpis.system_lcoe_eur_kwh:.3f} / kWh", "Notes": f"Effective grid rate: €{fin_kpis.effective_blended_grid_rate_eur_kwh:.3f} / kWh"},
            {"Indicator": "Peak Shaving Cost Efficiency", "Value": f"€{fin_kpis.annualized_cost_per_shaved_kw_eur:,.0f} / kW/yr", "Notes": f"Peak demand reduced by {sim_res.kpis.peak_reduction_kw:,.1f} kW"},
            {"Indicator": "DSO Contract Savings (Isolated)", "Value": f"€{fin_kpis.dso_savings_eur:+,.0f} / yr ({fin_kpis.dso_savings_pct:+.1f}%)", "Notes": f"New DSO grid bill: €{fin_kpis.combined_pillar2_dso_eur:,.0f}/yr"},
            {"Indicator": "Supplier Commodity Savings (Isolated)", "Value": f"€{fin_kpis.supplier_savings_eur:+,.0f} / yr ({fin_kpis.supplier_savings_pct:+.1f}%)", "Notes": f"New energy bill: €{fin_kpis.combined_pillar1_supply_eur:,.0f}/yr"},
            {"Indicator": "Grid Congestion Compliance", "Value": cong_val, "Notes": "Checks whether all 12 monthly peaks stay within contracted grid limit"},
        ])
        st.dataframe(ind_df, use_container_width=True, hide_index=True)

    # Supply Mix, Asset Utilization & Financial Cost Share Bridge (collapsible fragment)
    _render_subtab6_supply_mix_bridge_fragment(sim_res)

    # Interactive Financial Chart Gallery (isolated fragment)
    _render_financial_chart_gallery_fragment(sim_res)

    # Expandable 15-Year Cashflow Table (isolated fragment)
    _render_cashflow_table_expander_fragment(sim_res)


@st.fragment
def _render_subtab6_supply_mix_bridge_fragment(sim_res) -> None:
    """Collapsible Supply Mix, Asset Utilization & Physical vs. Financial Cost Share comparison table."""
    fk = sim_res.financial_kpis
    if fk is None:
        return

    with st.expander(":material/donut_large: Supply Mix, Asset Utilization & Financial Cost Share", expanded=False):
        render_supply_mix_and_utilization_overview(sim_res, key_prefix="subtab6")

        diag: SystemUtilizationDiagnostics = compute_system_utilization_diagnostics(sim_res)
        grid_opex = max(0.0, float(fk.combined_grid_total_eur))
        solar_opex = max(0.0, float(fk.solar_om_eur))
        bat_opex = max(0.0, float(fk.battery_om_eur))
        gen_opex = max(0.0, float(fk.generator_total_opex_eur))
        gross_opex_sum = max(1.0, grid_opex + solar_opex + bat_opex + gen_opex)

        bridge_df = pd.DataFrame([
            {
                "Source": "Grid Import",
                "Physical Energy (MWh/yr)": round(diag.grid_direct_kwh / 1000.0, 1),
                "Physical Share (%)": round(diag.grid_direct_pct, 1),
                "Annual Operating Cost (€/yr)": round(grid_opex, 0),
                "Annual Cost Share (%)": round((grid_opex / gross_opex_sum) * 100.0, 1),
                "CAPEX (€)": round(0.0, 0),
            },
            {
                "Source": "Solar Direct",
                "Physical Energy (MWh/yr)": round(diag.solar_direct_kwh / 1000.0, 1),
                "Physical Share (%)": round(diag.solar_direct_pct, 1),
                "Annual Operating Cost (€/yr)": round(solar_opex - float(fk.solar_export_revenue_eur), 0),
                "Annual Cost Share (%)": round((solar_opex / gross_opex_sum) * 100.0, 1),
                "CAPEX (€)": round(float(fk.solar_capex_eur), 0),
            },
            {
                "Source": "Battery Storage",
                "Physical Energy (MWh/yr)": round(diag.battery_discharge_kwh / 1000.0, 1),
                "Physical Share (%)": round(diag.battery_discharge_pct, 1),
                "Annual Operating Cost (€/yr)": round(bat_opex, 0),
                "Annual Cost Share (%)": round((bat_opex / gross_opex_sum) * 100.0, 1),
                "CAPEX (€)": round(float(fk.battery_capex_eur), 0),
            },
            {
                "Source": "Generator Backup",
                "Physical Energy (MWh/yr)": round(diag.generator_direct_kwh / 1000.0, 1),
                "Physical Share (%)": round(diag.generator_direct_pct, 1),
                "Annual Operating Cost (€/yr)": round(gen_opex, 0),
                "Annual Cost Share (%)": round((gen_opex / gross_opex_sum) * 100.0, 1),
                "CAPEX (€)": round(float(fk.generator_capex_eur), 0),
            },
        ])
        st.markdown("**Physical Energy Share (%) vs. Annual Operating Cost Share (%)**")
        st.caption(
            "Solar operating cost shows Solar O&M minus Export Feed-in Revenue; "
            "Cost Share (%) reflects each source's share of gross annual operating outflows."
        )
        st.dataframe(bridge_df, use_container_width=True, hide_index=True)


@st.fragment
def render_subtab6_financials(sim_res) -> None:
    """
    Renders Subtab 6: Financials (Lazy-loaded, @st.fragment isolated):
      - Live Master Cost & Savings Equation Bar
      - 3 Structured Inner Sub-Tabs modeled after Currentsituation_sandbox:
          * 6.1: Electricity Bill & Grid Tariffs (3-Zone: Inputs | Bill Sub-Ledger | Monthly Progression)
          * 6.2: System Hardware & Operating Costs (Solar, Battery, Generator & Avoided Grid Credit)
          * 6.3: Executive Summary & 15-Year Projection (8 KPIs, Component Matrix, Charts, 15Y Ledger)
    """
    cur_sys: CombinedSystemConfig = st.session_state["comb_system_cfg"]
    cur_fin: CombinedFinancialConfig = st.session_state["comb_fin_cfg"]
    # Upgrade in-memory CombinedFinancialConfig after hot reloads so new fields exist cleanly.
    for _k, _v in CombinedFinancialConfig().__dict__.items():
        if not hasattr(cur_fin, _k):
            setattr(cur_fin, _k, _v)
    is_fin_active = bool(cur_sys.enable_financials)

    if not is_fin_active:
        with st.container(border=True):
            f_col1, f_col2 = st.columns([2.5, 1.2])
            with f_col1:
                st.markdown(
                    "**Financials is currently paused for maximum simulation speed.** "
                    "Click **Activate Financials** to run the 4-Pillar Tariff billing, component investment breakdown, "
                    "monthly progression charts, and 15-year cashflow analysis."
                )
            with f_col2:
                st.button(
                    "Activate Financials",
                    icon=":material/power_settings_new:",
                    type="primary",
                    use_container_width=True,
                    key="comb_btn_activate_financials",
                    on_click=_activate_module_callback,
                    args=("comb_enable_financials_toggle",),
                )
        return

    _needs_fin_eval = (
        sim_res.financial_kpis is None
        or not hasattr(sim_res.financial_kpis, "dso_savings_eur")
        or getattr(sim_res, "dso_monthly_df", None) is None
        or sim_res.dso_monthly_df.empty
    )
    if _needs_fin_eval:
        evaluate_combined_financials(sim_res, cur_fin)

    # Top: Live Master Cost & Savings Equation Bar
    st.markdown(_render_master_cost_equation_bar(sim_res), unsafe_allow_html=True)

    # 3 Structured Financial Inner Sub-Tabs
    fin_tabs = st.tabs([
        ":material/receipt_long: 1. Electricity Bill",
        ":material/precision_manufacturing: 2. Hardware & Running Costs",
        ":material/analytics: 3. 15-Year Overview",
    ])

    with fin_tabs[0]:
        _render_subtab6_1_grid_tariffs(sim_res, cur_sys, cur_fin)

    with fin_tabs[1]:
        _render_subtab6_2_hardware_costs(sim_res, cur_sys, cur_fin)

    with fin_tabs[2]:
        _render_subtab6_3_executive_overview(sim_res, cur_sys, cur_fin)
