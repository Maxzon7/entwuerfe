"""
========================================================================================
Tab: DRACBV Generator Peaking Simulator (Beta) (ui/tab_dracbv_beta/view.py)
========================================================================================

Description:
------------
Standalone Beta module evaluating Generator Peaking & Peak Shaving:
  - Ingests active 15-minute facility load profile from Tab 1 and contract from Tab 2.
  - Simulates 15-minute generator dispatch to carry peaks exceeding the grid limit.
  - Computes fuel consumption, operating hours, and equipment OPEX / rental costs.
  - Renders 15-minute dispatch curve: Original Load + New Grid Load + Generator Output.
  - Generates Cumulative Payment Schedule (Kumulierte Zahlungsreihe) table and comparison chart.
"""

from typing import Optional, Dict, Any, List
import streamlit as st
import pandas as pd
import numpy as np

from current_model.models.generator import GeneratorConfig, GeneratorKPIs, get_generator_presets
from current_model.models.contract import Contract
from current_model.core.dracbv_engine import simulate_generator_peaking
from current_model.ui.common.session_utils import (
    find_active_load_data_in_session,
    find_active_contract_in_session,
    get_load_profile_summary
)
from current_model.ui.common.cards import render_kpi_card
from current_model.ui.tab_dracbv_beta.charts import (
    create_generator_dispatch_chart,
    create_cumulative_payment_chart
)


def render_tab_dracbv_beta(key_prefix: str = "app_dracbv_beta") -> None:
    """
    Main entry point for the Generator Peaking Simulator (Beta).
    """
    # --------------------------------------------------------------------------
    # 0. Prominent Experimental Beta Warning Banner
    # --------------------------------------------------------------------------
    st.warning(
        ":material/science: **DRACBV Generator Peaking Simulator (Experimental Beta)**  \n"
        "This experimental module evaluates whether running an on-site generator to carry facility load peaks "
        "is more economical than traditional grid draw with peak capacity fees and overload penalties. "
        "It executes an interval-by-interval 15-minute dispatch and computes the complete cumulative payment schedule (Zahlungsreihe).  \n"
        "*Note: Results in this tab are calculated independently and are not yet linked to the global Scenario Management leaderboard.*"
    )

    # --------------------------------------------------------------------------
    # 1. Discover Active Load & Contract in Workspace
    # --------------------------------------------------------------------------
    df_load, load_desc, power_col = find_active_load_data_in_session(prefer_annual=True)
    active_contract = find_active_contract_in_session()

    # Fallback to default contract if none found
    if active_contract is None:
        active_contract = Contract(
            name="Standard Industrial Contract (400 kW Limit)",
            contracted_capacity_kw=400.0,
            monthly_capacity_tariff=0.15,
            default_energy_rate=0.20,
            currency="EUR"
        )

    # Handle missing consumption data
    if df_load is None or df_load.empty or not power_col:
        st.info(
            "### :material/info: No Active Load Profile Found\n\n"
            "Please configure or generate a consumption profile in **Tab 2: Consumption (Baseline)** "
            "(via CSV real meter upload or the 365-day synthetic simulator) to run the Generator Peaking simulation."
        )
        return

    # Summarize active load
    load_summary = get_load_profile_summary(df_load, power_col)
    peak_kw = float(load_summary.get("peak_kw", 0.0))
    total_kwh = float(load_summary.get("total_kwh", 0.0))
    contract_cap_kw = float(active_contract.contracted_capacity_kw)
    total_intervals = len(df_load)
    total_days = max(1, int(np.ceil(total_intervals * 0.25 / 24.0)))

    # Allow custom currency symbol override (e.g. switch between ARS and EUR)
    contract_currency_default = getattr(active_contract, "currency", "EUR")
    col_hdr_left, col_hdr_right = st.columns([3, 1])
    with col_hdr_left:
        st.markdown(f"**Facility Profile:** `{load_desc}` | **Horizon:** `{total_days} Days ({total_intervals:,} intervals)`")
    with col_hdr_right:
        currency = st.text_input(
            ":material/currency_exchange: Display & Billing Currency",
            value=st.session_state.get(f"{key_prefix}_currency_override", contract_currency_default),
            help="Specify currency symbol for all inputs, outputs, charts, and payment series (e.g. EUR, USD, ARS, €)."
        ).strip()
        if not currency:
            currency = contract_currency_default
        st.session_state[f"{key_prefix}_currency_override"] = currency

    is_overloaded = (peak_kw > contract_cap_kw)
    overload_kw = max(0.0, peak_kw - contract_cap_kw)

    # Clone contract and apply selected currency
    sim_contract = Contract.from_dict(active_contract.to_dict())
    sim_contract.currency = currency

    # --------------------------------------------------------------------------
    # 2. Status Diagnostic Cards
    # --------------------------------------------------------------------------
    col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4)
    with col_stat1:
        render_kpi_card(
            title=":material/analytics: Facility Peak Demand",
            value=f"{peak_kw:.1f} kW",
            subtext=f"Total: {total_kwh:,.0f} kWh/a",
            status="default"
        )
    with col_stat2:
        render_kpi_card(
            title=":material/speed: Contracted Grid Limit",
            value=f"{contract_cap_kw:.0f} kW",
            subtext=f"Contract: {sim_contract.name[:22]}",
            status="default"
        )
    with col_stat3:
        status_theme = "alert" if is_overloaded else "ok"
        status_val = f"+{overload_kw:.1f} kW Overload" if is_overloaded else "Within Limit"
        status_sub = "Grid Capacity Exceeded!" if is_overloaded else "No Overload Violations"
        render_kpi_card(
            title=":material/warning: Overload Status",
            value=status_val,
            subtext=status_sub,
            status=status_theme
        )
    with col_stat4:
        render_kpi_card(
            title=":material/payments: Capacity Tariff Rate",
            value=f"{sim_contract.monthly_capacity_tariff:,.2f} {currency}/kW/mo",
            subtext=f"Penalty Rate: {sim_contract.peak_penalty_rate:,.2f} {currency}/kW",
            status="default"
        )

    st.markdown("---")

    # --------------------------------------------------------------------------
    # 3. Generator Configuration Panel
    # --------------------------------------------------------------------------
    st.subheader(":material/settings: Generator Peaking Configuration")

    # Adapt realistic currency fuel pricing defaults
    is_ars = (currency.upper() == "ARS")
    default_fuel_price = 1200.0 if is_ars else 1.45
    default_maint_cost = 4500.0 if is_ars else 4.50
    default_lease_fee = 1500000.0 if is_ars else 1200.0
    default_purchase_capex = 25000000.0 if is_ars else 20000.0

    # Auto-size suggested generator power
    suggested_gen_kw = max(50.0, round((overload_kw * 1.25) / 25.0) * 25.0) if is_overloaded else 100.0

    presets = get_generator_presets()
    preset_names = ["Custom"] + list(presets.keys())

    selected_preset = st.selectbox(
        "Load Pre-Configured Generator Model",
        options=preset_names,
        index=0,
        key=f"{key_prefix}_preset_select"
    )

    if selected_preset != "Custom" and selected_preset in presets:
        base_cfg = presets[selected_preset]
        init_power_kw = float(base_cfg.rated_power_kw)
        init_fuel_type = base_cfg.fuel_type
        init_fuel_price = float(base_cfg.fuel_price_per_unit) if not is_ars else default_fuel_price
        init_maint_cost = float(base_cfg.maintenance_cost_per_op_hour) if not is_ars else default_maint_cost
        init_capex = float(base_cfg.capital_cost) if not is_ars else default_purchase_capex
    else:
        init_power_kw = float(suggested_gen_kw)
        init_fuel_type = "Diesel"
        init_fuel_price = default_fuel_price
        init_maint_cost = default_maint_cost
        init_capex = default_purchase_capex

    with st.form(key=f"{key_prefix}_generator_form"):
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            gen_power_kw = st.number_input(
                "Generator Rated Power (kW)",
                min_value=10.0,
                max_value=3000.0,
                value=float(init_power_kw),
                step=25.0,
                help="Maximum continuous electrical output capacity of the generator."
            )
            trigger_kw = st.number_input(
                "Dispatch Trigger / Grid Cap (kW)",
                min_value=10.0,
                max_value=5000.0,
                value=float(contract_cap_kw),
                step=25.0,
                help="When facility demand exceeds this threshold, the generator starts automatically to carry the peak."
            )

        with col_f2:
            fuel_type = st.selectbox("Fuel Type", options=["Diesel", "Natural Gas", "HVO/Biofuel"], index=0)
            fuel_price = st.number_input(
                f"Fuel Price ({currency}/Liter or m³)",
                min_value=0.01,
                max_value=50000.0,
                value=float(init_fuel_price),
                step=0.05 if not is_ars else 50.0
            )
            maint_per_hour = st.number_input(
                f"Maintenance Cost ({currency}/operating hour)",
                min_value=0.0,
                max_value=50000.0,
                value=float(init_maint_cost),
                step=0.5 if not is_ars else 200.0,
                help="Servicing, engine oil, lubrication, and overhaul costs per operating hour."
            )

        with col_f3:
            acq_mode = st.radio("Acquisition Model", options=["Rental / Monthly Lease", "Capital Purchase (CAPEX)"], index=0)
            if acq_mode == "Rental / Monthly Lease":
                monthly_lease = st.number_input(
                    f"Monthly Lease Fee ({currency}/month)",
                    min_value=0.0,
                    max_value=100000000.0,
                    value=float(default_lease_fee),
                    step=100.0 if not is_ars else 50000.0
                )
                capital_cost = 0.0
            else:
                capital_cost = st.number_input(
                    f"Purchase CAPEX ({currency})",
                    min_value=0.0,
                    max_value=500000000.0,
                    value=float(init_capex),
                    step=1000.0 if not is_ars else 500000.0
                )
                monthly_lease = 0.0

            min_load_pct = st.slider("Minimum Loading Ratio (%)", min_value=0.0, max_value=50.0, value=25.0, step=5.0, help="Prevents engine wet-stacking when operating.")

        submitted = st.form_submit_button(":material/play_arrow: Run 15-Minute Generator Peaking Simulation", type="primary")

    # Assemble Generator Config
    gen_config = GeneratorConfig(
        rated_power_kw=float(gen_power_kw),
        fuel_type=str(fuel_type),
        min_load_ratio_pct=float(min_load_pct),
        peak_shaving_trigger_kw=float(trigger_kw),
        monthly_lease_fee=float(monthly_lease),
        capital_cost=float(capital_cost),
        fuel_price_per_unit=float(fuel_price),
        maintenance_cost_per_op_hour=float(maint_per_hour),
        currency=currency
    )

    # --------------------------------------------------------------------------
    # 4. Execute 15-Minute Simulation
    # --------------------------------------------------------------------------
    sim_result = simulate_generator_peaking(
        df_load=df_load,
        power_col=power_col,
        contract=sim_contract,
        gen_config=gen_config,
        step_hours=0.25
    )

    kpis: GeneratorKPIs = sim_result["kpis"]
    df_dispatch = sim_result["df_dispatch"]
    df_zahlungsreihe = sim_result["df_zahlungsreihe"]
    shaved_peak = sim_result["peak_shaved_kw"]
    new_peak = sim_result["new_peak_kw"]
    annual_savings = sim_result["annual_net_savings"]

    st.markdown("---")

    # --------------------------------------------------------------------------
    # 5. Executive Results & Key Performance Indicators
    # --------------------------------------------------------------------------
    st.subheader(":material/speed: Simulation Results & Peaking Impact")

    col_r1, col_r2, col_r3, col_r4 = st.columns(4)
    with col_r1:
        render_kpi_card(
            title=":material/compress: Shaved Peak Demand",
            value=f"{shaved_peak:.1f} kW",
            subtext=f"New Grid Peak: {new_peak:.1f} kW",
            status="ok" if shaved_peak > 0 else "default"
        )
    with col_r2:
        render_kpi_card(
            title=":material/timer: Generator Runtime",
            value=f"{kpis.operating_hours:.1f} hrs",
            subtext=f"Total Generated: {kpis.total_generation_kwh:,.0f} kWh",
            status="default"
        )
    with col_r3:
        render_kpi_card(
            title=":material/local_gas_station: Fuel Consumption",
            value=f"{kpis.total_fuel_units:,.1f} Liters",
            subtext=f"Fuel Cost: {kpis.fuel_cost_total:,.0f} {currency}",
            status="default"
        )
    with col_r4:
        is_pos = (annual_savings > 0)
        render_kpi_card(
            title=":material/savings: Net Financial Savings",
            value=f"{annual_savings:,.0f} {currency}/a",
            subtext="Generates Net Savings!" if is_pos else "Generator More Expensive",
            status="ok" if is_pos else "alert"
        )

    # --------------------------------------------------------------------------
    # 6. Diagram 1: 15-Minute Load & Generation Timeseries
    # --------------------------------------------------------------------------
    st.markdown("#### :material/show_chart: 15-Minute Power Dispatch Curve")

    fig_dispatch = create_generator_dispatch_chart(df_dispatch, trigger_kw=trigger_kw, days_to_show=None)
    st.plotly_chart(fig_dispatch, use_container_width=True)

    # --------------------------------------------------------------------------
    # 7. Diagram 2: Cumulative Payment Series (Kumulierte Zahlungsreihe)
    # --------------------------------------------------------------------------
    st.markdown("#### :material/stacked_line_chart: Cumulative Payment Trajectory (Kumulierte Zahlungsreihe)")
    fig_payment = create_cumulative_payment_chart(df_zahlungsreihe, currency=currency)
    st.plotly_chart(fig_payment, use_container_width=True)

    # --------------------------------------------------------------------------
    # 8. Data Table: Detailed Monthly Payment Schedule (Zahlungsreihe)
    # --------------------------------------------------------------------------
    st.markdown("#### :material/table_chart: Month-by-Month Cost Comparison (Zahlungsreihe)")
    
    # Format table for display
    display_df = df_zahlungsreihe.copy()
    display_df = display_df.rename(columns={
        "Month": "Billing Month",
        "Baseline_Peak_kW": "Baseline Peak (kW)",
        "New_Grid_Peak_kW": "New Peak (kW)",
        "Peak_Shaved_kW": "Peak Shaved (kW)",
        "Gen_Hours": "Genset Hours (h)",
        "Fuel_Liters": "Fuel (L)",
        "Status_Quo_Bill": f"Status Quo Bill ({currency})",
        "New_Grid_Bill": f"New Grid Bill ({currency})",
        "Generator_Cost": f"Genset Expenses ({currency})",
        "Total_With_Generator": f"Total with Genset ({currency})",
        "Monthly_Savings": f"Net Monthly Savings ({currency})",
        "Cum_Status_Quo": f"Cum. Status Quo ({currency})",
        "Cum_With_Generator": f"Cum. with Genset ({currency})",
        "Cum_Savings": f"Cum. Savings ({currency})"
    })

    # Drop minor columns for clean executive presentation
    cols_to_show = [
        "Billing Month", "Baseline Peak (kW)", "New Peak (kW)", "Genset Hours (h)", "Fuel (L)",
        f"Status Quo Bill ({currency})", f"New Grid Bill ({currency})", f"Genset Expenses ({currency})",
        f"Total with Genset ({currency})", f"Net Monthly Savings ({currency})",
        f"Cum. Status Quo ({currency})", f"Cum. with Genset ({currency})", f"Cum. Savings ({currency})"
    ]
    st.dataframe(display_df[cols_to_show], use_container_width=True)
