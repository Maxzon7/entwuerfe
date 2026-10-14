"""
========================================================================================
Procurement Strategy & Executive Advisory View (procurement_view.py)
Current Situation (Status Quo) Sandbox
========================================================================================
Provides executive decision support for Dutch Grootverbruik electricity procurement:
  1. 3-Route Sourcing Comparator (Fixed vs. Tranche vs. Dynamic Spot)
  2. Voltage Level Transition Advisor (AC4b vs. AC5a with rented transformer station)
  3. BESS & Congestion Flexibility Advisor (Peak shaving, GTV downsizing, CBC fees)
  4. Supplier Market Landscape Directory (4 supplier segments & contract models)
========================================================================================
"""

from typing import Dict, Any, Optional
import streamlit as st
import plotly.graph_objects as go

from ui_sandbox.Currentsituation_sandbox.engine import (
    LoadSeries2025,
    StatusQuoConfig2025,
    compare_procurement_routes,
    evaluate_voltage_transition_advisor,
    evaluate_bess_flexibility_upside,
    SUPPLIER_CATALOG_2025,
    SupplierCategory,
)


def render_procurement_strategy_view(
    load: Optional[LoadSeries2025] = None,
    active_config: Optional[StatusQuoConfig2025] = None,
    key_prefix: str = "currsit_strat",
    *args: Any,
    load_series: Optional[LoadSeries2025] = None,
    active_result: Any = None,
    **kwargs: Any
) -> None:
    """Renders the executive procurement strategy and asset planning suite."""
    if load is None:
        load = load_series or kwargs.get("load") or kwargs.get("load_series")
    if active_config is None:
        active_config = (
            active_result.config
            if active_result and hasattr(active_result, "config")
            else None
        ) or kwargs.get("active_config")

    if load is None or active_config is None:
        st.warning("Procurement Strategy Advisory requires an active load profile and contract configuration.")
        return
    st.markdown("#### :material/strategy: Commercial Procurement Strategy & Asset Advisory")
    st.caption(
        "Executive decision guidance for Dutch commercial power procurement (Grootverbruik), "
        "asset planning (Solar PV & BESS), and grid voltage level optimization."
    )

    strat_tabs = st.tabs([
        ":material/compare_arrows: 1. 3-Route Sourcing Comparator",
        ":material/electric_meter: 2. Voltage Level Transition Advisor (AC4b vs. AC5a)",
        ":material/battery_charging_full: 3. BESS & Congestion Flex Advisor",
        ":material/storefront: 4. Supplier Landscape Directory",
    ])

    # ----------------------------------------------------------------------------------
    # Sub-Tab 1: 3-Route Sourcing Comparator
    # ----------------------------------------------------------------------------------
    with strat_tabs[0]:
        st.markdown("##### 1. Three Sourcing Routes: Side-by-Side Assessment")
        st.caption(
            "Compares wholesale procurement costs across Fixed, Tranche, and Dynamic Spot "
            "for the facility's active 15-minute load profile."
        )

        routes = compare_procurement_routes(load=load, base_config=active_config)

        c1, c2, c3 = st.columns(3)
        with c1:
            rf = routes["fixed"]
            st.markdown(
                f"""
                <div class="metric-box">
                    <div class="metric-label">:material/lock: Fixed-Price (Vaste Prijs)</div>
                    <div class="metric-number">€ {rf['annual_supplier_net']:,.2f}</div>
                    <div class="metric-sub">Blended: € {rf['blended_net_rate']:.4f}/kWh | Risk Premium: +€ {rf['risk_premium_eur']:,.2f}</div>
                </div>
                """,
                unsafe_allow_html=True
            )
            st.caption(":material/shield: 100% budget certainty; zero wholesale exposure; highest risk premium embedded.")

        with c2:
            rt = routes["tranche"]
            st.markdown(
                f"""
                <div class="metric-box">
                    <div class="metric-label">:material/stacked_line_chart: Tranche / Click (Klik)</div>
                    <div class="metric-number">€ {rt['annual_supplier_net']:,.2f}</div>
                    <div class="metric-sub">Blended: € {rt['blended_net_rate']:.4f}/kWh | Spread vs Spot: +€ {rt['risk_premium_eur']:,.2f}</div>
                </div>
                """,
                unsafe_allow_html=True
            )
            st.caption(":material/timeline: Phased hedging on ICE Endex futures; captures market dips; residual volume on spot.")

        with c3:
            rd = routes["dynamic"]
            st.markdown(
                f"""
                <div class="metric-box">
                    <div class="metric-label">:material/show_chart: Dynamic Spot (EPEX Spot)</div>
                    <div class="metric-number">€ {rd['annual_supplier_net']:,.2f}</div>
                    <div class="metric-sub">Blended: € {rd['blended_net_rate']:.4f}/kWh | Zero hedging markup</div>
                </div>
                """,
                unsafe_allow_html=True
            )
            st.caption(":material/bolt: Pure wholesale pass-through + fixed handling margin; mandatory for BESS arbitrage.")

        # Comparison Bar Chart
        route_names = ["Fixed Price", "Tranche / Click", "Dynamic Spot"]
        annual_costs = [rf["annual_supplier_net"], rt["annual_supplier_net"], rd["annual_supplier_net"]]
        colors = ["#38BDF8", "#8B5CF6", "#00D2B4"]

        fig_comp = go.Figure(data=[
            go.Bar(
                x=route_names,
                y=annual_costs,
                marker_color=colors,
                text=[f"€ {v:,.0f}" for v in annual_costs],
                textposition="auto",
                hovertemplate="<b>%{x}</b><br>Annual Supplier Net: € %{y:,.2f}<extra></extra>"
            )
        ])
        fig_comp.update_layout(
            title="Annual Commodity Spend Comparison (Netto)",
            yaxis_title="Supplier Net Spend (€/year)",
            height=340,
            margin=dict(l=40, r=40, t=50, b=40),
        )
        st.plotly_chart(fig_comp, use_container_width=True)

    # ----------------------------------------------------------------------------------
    # Sub-Tab 2: Voltage Level Transition Advisor
    # ----------------------------------------------------------------------------------
    with strat_tabs[1]:
        st.markdown("##### 2. Voltage Level Optimization: Low Voltage (AC4b) vs. Medium Voltage (AC5a)")
        st.caption(
            "Analyzes whether transitioning from Low Voltage (DSO transformator) to Medium Voltage "
            "with a rented transformer station (€ 354/month) is financially beneficial."
        )

        col_t1, col_t2 = st.columns([1.5, 2.5])
        with col_t1:
            eval_trans = evaluate_voltage_transition_advisor(load=load)
            st.metric("Facility Peak Demand", f"{eval_trans['peak_demand_kw']:.1f} kW")
            st.metric("Reserved Capacity (GTV)", f"{eval_trans['contracted_kw']:.1f} kW")
            st.metric("Break-Even Peak Threshold", f"{eval_trans['break_even_kw']:.1f} kW")

        with col_t2:
            st.markdown(
                f"""
                <div class="invoice-card">
                    <div class="invoice-header">:material/balance: Economic Transition Balance</div>
                    <div class="invoice-row">
                        <span>GTV Tariff Savings (AC4b €43.88 vs. AC5a €26.68/kW/yr)</span>
                        <span class="mono-val" style="color:#00D2B4;">+ € {eval_trans['annual_gtv_savings']:,.2f} / yr</span>
                    </div>
                    <div class="invoice-row">
                        <span>PAV Connection Surcharge Delta (AC5a vs. AC4b)</span>
                        <span class="mono-val" style="color:#EF4444;">- € {eval_trans['pav_delta']:,.2f} / yr</span>
                    </div>
                    <div class="invoice-row">
                        <span>Transformer Station Rental (630 kVA Kompaktstation)</span>
                        <span class="mono-val" style="color:#F59E0B;">- € {eval_trans['annual_trafo_rent']:,.2f} / yr</span>
                    </div>
                    <div class="invoice-row total">
                        <span>Net Annual Economic Advantage</span>
                        <span class="mono-val" style="color:{'#00D2B4' if eval_trans['is_beneficial'] else '#EF4444'};">
                            € {eval_trans['net_annual_benefit']:,.2f} / yr
                        </span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )
            if eval_trans["is_beneficial"]:
                st.success(f":material/check_circle: {eval_trans['recommendation']}")
            else:
                st.info(f":material/info: {eval_trans['recommendation']}")

    # ----------------------------------------------------------------------------------
    # Sub-Tab 3: BESS & Congestion Flex Advisor
    # ----------------------------------------------------------------------------------
    with strat_tabs[2]:
        st.markdown("##### 3. Battery Energy Storage System (BESS) & Congestion Flexibility")
        st.caption(
            "Monetizing on-site battery storage via Peak Shaving (Maandpiek & GTV) and "
            "Capacity Limitation Contracts (Capaciteitsbeperkingscontracten - CBC)."
        )

        col_b1, col_b2 = st.columns([1.5, 2.5])
        with col_b1:
            shave_input = st.number_input(
                "Simulated Peak Shaving Power (kW):",
                min_value=10.0,
                max_value=2000.0,
                value=float(min(100.0, round(load.peak_demand_kw * 0.3, 0))),
                step=10.0,
                key=f"{key_prefix}_bess_shave_kw"
            )

        with col_b2:
            bess_eval = evaluate_bess_flexibility_upside(
                load=load,
                active_config=active_config,
                shave_kw=shave_input
            )

            st.markdown(
                f"""
                <div class="invoice-card">
                    <div class="invoice-header">:material/battery_saver: BESS Financial Value Levers</div>
                    <div class="invoice-row">
                        <span>1. Maandpiek Demand Fee Shaving (€ 3.46/kW/mo &times; 12)</span>
                        <span class="mono-val" style="color:#00D2B4;">+ € {bess_eval['annual_peak_fee_savings']:,.2f} / yr</span>
                    </div>
                    <div class="invoice-row">
                        <span>2. Permanent GTV Reserved Capacity Downsizing</span>
                        <span class="mono-val" style="color:#00D2B4;">+ € {bess_eval['annual_gtv_savings']:,.2f} / yr</span>
                    </div>
                    <div class="invoice-row">
                        <span>3. CBC Congestion Availability Remuneration</span>
                        <span class="mono-val" style="color:#8B5CF6;">+ € {bess_eval['annual_cbc_income']:,.2f} / yr</span>
                    </div>
                    <div class="invoice-row total">
                        <span>Total Annual Flexibility Value Potential</span>
                        <span class="mono-val" style="color:#00D2B4;">+ € {bess_eval['total_flex_value']:,.2f} / yr</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )
            st.info(f":material/lightbulb: **Contract Requirement:** {bess_eval['bess_contract_requirement']}")

    # ----------------------------------------------------------------------------------
    # Sub-Tab 4: Supplier Landscape Directory
    # ----------------------------------------------------------------------------------
    with strat_tabs[3]:
        st.markdown("##### 4. Dutch Commercial Electricity Supplier Directory")
        st.caption(
            "Overview of the four distinct supplier categories in the Dutch Grootverbruik market."
        )

        cat_cols = st.columns(4)
        categories_meta = [
            ("Major Integrated Utilities", ":material/domain:", "High balance-sheet security, own generation fleet (wind/gas/solar). Large corporates and multisite chains.", "Essent, Vattenfall, Eneco, PZEM"),
            ("B2B Portfolio Specialists", ":material/show_chart:", "Corporate-only suppliers. Pioneers in structured hedging, multi-tranche clicks, and load management.", "Scholt Energy, ENGIE, SEFE Energy"),
            ("Pure Dynamic & Spot Providers", ":material/bolt:", "Digital-first pass-through of raw EPEX Spot wholesale prices with fixed handling margin. Zero risk premiums.", "NieuweStroom, Energyhouse, Tibber Zakelijk"),
            ("Green Sourcing Specialists", ":material/eco:", "100% verified Dutch Guarantees of Origin (GvO) from local wind and solar assets. Strict ESG mandates.", "Greenchoice, Audax Renewables, Clean/Pure"),
        ]

        for idx, (c_name, c_icon, c_desc, c_players) in enumerate(categories_meta):
            with cat_cols[idx]:
                st.markdown(
                    f"""
                    <div class="metric-box" style="min-height: 220px;">
                        <div class="metric-label">{c_icon} {c_name}</div>
                        <p style="font-size:0.8rem; color:#CBD5E1; margin:8px 0;">{c_desc}</p>
                        <div style="font-size:0.75rem; color:#00D2B4; font-weight:600; border-top:1px solid #23304A; padding-top:6px;">
                            Key Players:<br><span style="color:#F1F5F9;">{c_players}</span>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
