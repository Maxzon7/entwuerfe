"""
========================================================================================
Scenario 3: Standalone Solar PV & Hockey-Stick Auto-Sizing Sandbox (ui_sandbox/Solar_sandbox/app.py)
========================================================================================

Standalone Execution:
    python -m streamlit run "ui_sandbox/Solar_sandbox/app.py"

4-Tab Architecture:
  - Tab 1: Facility Load & Solar Site Parameters (Climate/GPS preset, Tilt, Azimuth,
           Cell Technology PERC/TOPCon/Backcontact, Diurnal Load vs. Irradiance Preview)
  - Tab 2: Solar Sizing, Hockey-Stick Curve & Sub-Scenarios (Interactive Hockey-Stick
           Tradeoff Curve: Required PV kWp vs. Daylight Coverage % & SCR %, Auto-Sizing
           40%/60%/80%/100% buttons, Multi-Sizing Sub-Scenario Table, 15-Min Dispatch Chart)
  - Tab 3: 4-Pillar Contract Interaction & Bill Comparison (TOU Window kWh Savings in
           HT/Pico/Resto vs. NT/Valle, Monthly Peak Impact, Side-by-Side 4-Pillar Bill + PDF)
  - Tab 4: Solar CAPEX, Payback & 15Y TCO (Turnkey CAPEX, O&M, Feed-In Credit,
           15-Year Cashflow & TCO NPV, Standardized `ScenarioEvaluationOutput`)
========================================================================================
"""

import os
import sys
from typing import Dict, List, Any
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# Ensure root and parent directories are on sys.path for standalone execution
_CURRENT_DIR = os.path.abspath(os.path.dirname(__file__))
_UI_SANDBOX_DIR = os.path.abspath(os.path.join(_CURRENT_DIR, ".."))
_PROJECT_ROOT = os.path.abspath(os.path.join(_UI_SANDBOX_DIR, ".."))
for _p in (_PROJECT_ROOT, _UI_SANDBOX_DIR, _CURRENT_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from models.solar import TECHNOLOGY_SPECS
from ui_sandbox.common import (
    ScenarioEvaluationOutput,
    build_residual_load_series_2025,
    evaluate_scenario_4pillar_bill_comparison,
    render_shared_4pillar_bill_comparison_ui,
    render_scenario_evaluation_output_card,
    compute_15y_tco_npv,
    render_standalone_baseline_control_bar,
)
from ui_sandbox.Currentsituation_sandbox.engine.consumption_pipeline import MONTH_NAMES
from ui_sandbox.Currentsituation_sandbox.engine.status_quo_master import calculate_status_quo_master_2025
from ui_sandbox.Currentsituation_sandbox.contract.assumptions_banner import build_assumptions_register_dict
from ui_sandbox.Solar_sandbox.solar_sandbox_engine import (
    SOLAR_CLIMATE_PRESETS,
    generate_normalized_solar_unit_profile_2025,
    simulate_standalone_solar_dispatch,
    compute_solar_hockey_stick_curve,
    create_solar_hockey_stick_figure,
)


def render_solar_sandbox(key_prefix: str = "solar_sb") -> ScenarioEvaluationOutput:
    """Main orchestrator for Scenario 3: Standalone Solar PV & Hockey-Stick Auto-Sizing Sandbox."""
    st.markdown(
        """
        <div style="background: linear-gradient(90deg, #0f172a 0%, #1e293b 100%);
                    border-left: 5px solid #f59e0b; padding: 14px 20px; border-radius: 8px; margin-bottom: 12px;">
            <h3 style="margin:0; color:#f8fafc; font-size:1.25rem;">
                Scenario 3: Standalone Solar PV & Hockey-Stick Auto-Sizing Sandbox
            </h3>
            <p style="margin:4px 0 0 0; color:#94a3b8; font-size:0.86rem;">
                Couples 15-minute Solar PV generation with the 4-Pillar Electricity Bill Engine.
                Features the interactive <b>Solar Sizing Hockey-Stick Curve</b> (Required kWp vs. Daylight Load Coverage % & Self-Consumption Rate %)
                and transparent TOU window bill savings analysis.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    base_load, base_config, site_label = render_standalone_baseline_control_bar(
        key_prefix=key_prefix,
        default_preset_idx=0,
    )
    curr = base_config.currency_code

    # Default climate selection matched to currency/preset
    default_clim_idx = 1 if curr == "ARS" else 0
    climate_keys = list(SOLAR_CLIMATE_PRESETS.keys())

    tabs = st.tabs(
        [
            ":material/wb_sunny: 1. Facility Load & Solar Site Parameters",
            ":material/ssid_chart: 2. Solar Sizing, Hockey-Stick Curve & Sub-Scenarios",
            ":material/receipt_long: 3. 4-Pillar Contract Interaction & Bill Comparison",
            ":material/account_balance: 4. Solar CAPEX, Payback & 15Y TCO",
        ]
    )

    # ----------------------------------------------------------------------------------
    # TAB 1: Facility Load & Solar Site Parameters
    # ----------------------------------------------------------------------------------
    with tabs[0]:
        st.markdown("#### :material/wb_sunny: Solar Location, Array Geometry & Module Technology")
        c_loc, c_geo, c_tech = st.columns(3)

        with c_loc:
            with st.container(border=True):
                st.markdown("##### :material/location_on: 1. Solar Climate & GPS")
                clim_choice = st.selectbox(
                    "Regional Solar Irradiance Benchmark",
                    options=climate_keys,
                    index=default_clim_idx,
                    key=f"{key_prefix}_clim_sel",
                )
                clim_meta = SOLAR_CLIMATE_PRESETS[clim_choice]
                lat_val = st.number_input(
                    "Latitude (deg)",
                    min_value=-65.0,
                    max_value=65.0,
                    value=float(clim_meta["latitude"]),
                    step=0.1,
                    key=f"{key_prefix}_lat_{clim_choice[:8]}",
                )
                lon_val = st.number_input(
                    "Longitude (deg)",
                    min_value=-180.0,
                    max_value=180.0,
                    value=float(clim_meta["longitude"]),
                    step=0.1,
                    key=f"{key_prefix}_lon_{clim_choice[:8]}",
                )

        with c_geo:
            with st.container(border=True):
                st.markdown("##### :material/explore: 2. Roof / Array Geometry")
                tilt_deg = st.slider(
                    "Module Tilt Angle (deg)",
                    min_value=0.0,
                    max_value=60.0,
                    value=float(clim_meta["default_tilt_deg"]),
                    step=1.0,
                    key=f"{key_prefix}_tilt_{clim_choice[:8]}",
                )
                azimuth_deg = st.slider(
                    "Azimuth Angle (0°=North, 90°=East, 180°=South, 270°=West)",
                    min_value=0.0,
                    max_value=360.0,
                    value=float(clim_meta["default_azimuth_deg"]),
                    step=5.0,
                    key=f"{key_prefix}_az_{clim_choice[:8]}",
                )
                dc_ac_ratio = st.slider(
                    "Inverter DC/AC Sizing Ratio",
                    min_value=1.00,
                    max_value=1.40,
                    value=1.15,
                    step=0.05,
                    key=f"{key_prefix}_dcac",
                )

        with c_tech:
            with st.container(border=True):
                st.markdown("##### :material/memory: 3. Cell Technology & Losses")
                tech_choice = st.selectbox(
                    "Solar Cell Technology",
                    options=list(TECHNOLOGY_SPECS.keys()),
                    index=1,  # TOPCon default
                    key=f"{key_prefix}_tech",
                )
                tech_info = TECHNOLOGY_SPECS[tech_choice]
                sys_losses_pct = st.slider(
                    "Total System & Wiring Losses (%)",
                    min_value=5.0,
                    max_value=25.0,
                    value=14.0,
                    step=0.5,
                    key=f"{key_prefix}_losses",
                )
                st.caption(
                    f"**{tech_info['name']}** — {tech_info['power_wp']:.0f} Wp/module | "
                    f"Temp. Coeff: {tech_info['temp_coeff_pct_c']:.2f}%/°C | "
                    f"Annual Deg: {tech_info['annual_deg_pct']:.2f}%/yr"
                )

        # Generate normalized unit PV profile (35,040 steps)
        unit_pv_kw, spec_yield_kwh_kwp = generate_normalized_solar_unit_profile_2025(
            timestamps=base_load.timestamps,
            latitude=lat_val,
            tilt_deg=tilt_deg,
            azimuth_deg=azimuth_deg,
            technology=tech_choice,
            dc_ac_ratio=dc_ac_ratio,
            system_losses_pct=sys_losses_pct,
        )

        # Diurnal Average Load vs. Unit Solar Irradiance Shape
        hours_of_day = base_load.timestamps.hour + base_load.timestamps.minute / 60.0
        df_diurnal = pd.DataFrame(
            {"hour": hours_of_day, "load_kw": base_load.power_kw, "unit_pv": unit_pv_kw * 100.0}
        ).groupby("hour", as_index=False).mean()

        fig_diurnal = go.Figure()
        fig_diurnal.add_trace(
            go.Scatter(
                x=df_diurnal["hour"],
                y=df_diurnal["load_kw"],
                mode="lines",
                name="Mean Facility Load (kW)",
                line=dict(color="#38bdf8", width=3),
            )
        )
        fig_diurnal.add_trace(
            go.Scatter(
                x=df_diurnal["hour"],
                y=df_diurnal["unit_pv"],
                mode="lines",
                fill="tozeroy",
                name="Solar Output per 100 kWp (kW AC)",
                line=dict(color="#f59e0b", width=2.5),
                fillcolor="rgba(245, 158, 11, 0.22)",
            )
        )
        fig_diurnal.update_layout(
            title=dict(
                text=f"<b>Diurnal Coincidence Check: Mean Facility Load vs. Solar Generation Curve ({spec_yield_kwh_kwp:,.0f} kWh/kWp/yr)</b>",
                x=0.01,
                y=0.98,
                xanchor="left",
            ),
            template="plotly_dark",
            paper_bgcolor="rgba(15, 23, 42, 0.0)",
            plot_bgcolor="rgba(15, 23, 42, 0.55)",
            height=340,
            margin=dict(l=50, r=30, t=85, b=40),
            xaxis=dict(title="Hour of Day (00:00 - 24:00)", gridcolor="#1e293b"),
            yaxis=dict(title="Active Power (kW)", gridcolor="#1e293b"),
        )
        st.plotly_chart(fig_diurnal, use_container_width=True, key=f"{key_prefix}_diurnal_chart")

    # ----------------------------------------------------------------------------------
    # TAB 2: Solar Sizing, Hockey-Stick Curve & Sub-Scenarios
    # ----------------------------------------------------------------------------------
    df_hockey, presets_kwp = compute_solar_hockey_stick_curve(
        load=base_load,
        unit_pv_kw=unit_pv_kw,
        specific_yield_kwh_per_kwp=spec_yield_kwh_kwp,
    )

    with tabs[1]:
        st.markdown("#### :material/ssid_chart: Interactive Solar Auto-Sizing Hockey-Stick Curve & Sub-Scenarios")
        st.caption(
            "Just like the BESS Pareto curve, sizing standalone Solar PV exhibits a **Hockey-Stick Inflection Point**: "
            "up to ~50–60% of annual demand, almost all generated solar energy is consumed directly on-site (high SCR %). "
            "Beyond that inflection point, midday demand is already saturated and required kWp shoots up exponentially for every extra percent of direct load coverage."
        )

        # Quick Auto-Sizing Preset Buttons
        st.markdown("##### :material/auto_awesome: Quick Auto-Sizing Targets (Click to Apply)")
        b1, b2, b3, b4, b5 = st.columns(5)
        state_kwp_key = f"{key_prefix}_active_pv_kwp"
        if state_kwp_key not in st.session_state:
            st.session_state[state_kwp_key] = float(presets_kwp["60_pct"])

        if b1.button(f"40% Demand ({presets_kwp['40_pct']:,.0f} kWp)", use_container_width=True, key=f"{key_prefix}_btn_40"):
            st.session_state[state_kwp_key] = float(presets_kwp["40_pct"])
        if b2.button(f"Sweet-Spot 55% ({presets_kwp['sweet_spot']:,.0f} kWp)", use_container_width=True, key=f"{key_prefix}_btn_sweet", type="primary"):
            st.session_state[state_kwp_key] = float(presets_kwp["sweet_spot"])
        if b3.button(f"60% Demand ({presets_kwp['60_pct']:,.0f} kWp)", use_container_width=True, key=f"{key_prefix}_btn_60"):
            st.session_state[state_kwp_key] = float(presets_kwp["60_pct"])
        if b4.button(f"80% Demand ({presets_kwp['80_pct']:,.0f} kWp)", use_container_width=True, key=f"{key_prefix}_btn_80"):
            st.session_state[state_kwp_key] = float(presets_kwp["80_pct"])
        if b5.button(f"100% Net-Zero ({presets_kwp['100_pct']:,.0f} kWp)", use_container_width=True, key=f"{key_prefix}_btn_100"):
            st.session_state[state_kwp_key] = float(presets_kwp["100_pct"])

        col_chart, col_cfg = st.columns([1.45, 1.0])
        with col_cfg:
            with st.container(border=True):
                st.markdown("##### :material/tune: Active Solar PV Sizing Configuration")
                active_pv_kwp = st.number_input(
                    "Installed Solar PV Nameplate Capacity (kWp DC)",
                    min_value=5.0,
                    max_value=25000.0,
                    value=float(st.session_state[state_kwp_key]),
                    step=10.0,
                    key=f"{key_prefix}_num_kwp",
                )
                st.session_state[state_kwp_key] = float(active_pv_kwp)

                limit_export = st.checkbox(
                    "Enforce Grid Export Limit at Connection Capacity (P_contract)",
                    value=False,
                    key=f"{key_prefix}_lim_exp",
                )
                max_exp_kw = base_config.dso.contracted_capacity_kw if limit_export else None

                sim_active = simulate_standalone_solar_dispatch(
                    load=base_load,
                    unit_pv_kw=unit_pv_kw,
                    pv_capacity_kwp=active_pv_kwp,
                    max_grid_export_kw=max_exp_kw,
                )

                mod_wp = TECHNOLOGY_SPECS[tech_choice]["power_wp"]
                n_modules = int(np.ceil(active_pv_kwp * 1000.0 / mod_wp))
                roof_area_m2 = n_modules * 2.15

                st.metric("Annual Solar Generation", f"{sim_active['pv_kwh']:,.0f} kWh/yr", f"Specific Yield: {spec_yield_kwh_kwp:,.0f} kWh/kWp")
                st.metric(
                    "Direct On-Site Self-Consumption",
                    f"{sim_active['direct_kwh']:,.0f} kWh/yr",
                    f"SCR: {sim_active['self_consumption_pct']:.1f}% | Autarky: {sim_active['autarky_pct']:.1f}%",
                )
                st.metric(
                    "Surplus Grid Export",
                    f"{sim_active['export_kwh']:,.0f} kWh/yr",
                    f"Panels: {n_modules:,}x ({roof_area_m2:,.0f} m² roof)",
                    delta_color="off",
                )

        with col_chart:
            fig_hockey = create_solar_hockey_stick_figure(
                df_curve=df_hockey,
                selected_kwp=active_pv_kwp,
                selected_daylight_cov_pct=sim_active["daylight_coverage_pct"],
                selected_scr_pct=sim_active["self_consumption_pct"],
            )
            st.plotly_chart(fig_hockey, use_container_width=True, key=f"{key_prefix}_hockey_chart")

        # Multi-Sizing Sub-Scenario Comparison Table
        st.markdown("##### :material/table_chart: Multi-Sizing Sub-Scenario Comparison Table")
        sub_variants = [
            ("Sub-Scenario A: 40% Demand (High Self-Consumption)", presets_kwp["40_pct"]),
            ("Sub-Scenario B: 60% Demand (Balanced Commercial)", presets_kwp["60_pct"]),
            ("Sub-Scenario C: 80% Demand (High Daylight Coverage)", presets_kwp["80_pct"]),
            ("Sub-Scenario D: 100% Annual Net-Zero Volume", presets_kwp["100_pct"]),
            ("Sub-Scenario E: Active Selected Configuration", active_pv_kwp),
        ]
        sub_rows = []
        for lbl, kwp_v in sub_variants:
            s_v = simulate_standalone_solar_dispatch(load=base_load, unit_pv_kw=unit_pv_kw, pv_capacity_kwp=kwp_v, max_grid_export_kw=max_exp_kw)
            sub_rows.append(
                {
                    "Solar Sizing Sub-Scenario": lbl,
                    "PV Capacity (kWp)": f"{kwp_v:,.1f}",
                    "Annual PV Yield (kWh)": f"{s_v['pv_kwh']:,.0f}",
                    "Direct Self-Cons. (kWh)": f"{s_v['direct_kwh']:,.0f}",
                    "Grid Export (kWh)": f"{s_v['export_kwh']:,.0f}",
                    "Self-Consumption Rate (SCR %)": f"{s_v['self_consumption_pct']:.1f}%",
                    "Daylight Coverage (%)": f"{s_v['daylight_coverage_pct']:.1f}%",
                    "Total Autarky (%)": f"{s_v['autarky_pct']:.1f}%",
                    "Residual Max Peak (kW)": f"{s_v['peak_after_kw']:,.1f}",
                }
            )
        st.dataframe(pd.DataFrame(sub_rows), use_container_width=True, hide_index=True)

        # 15-Minute Dispatch Preview (7-Day Peak Summer Window)
        st.markdown("##### :material/timeline: 15-Minute Power Flow Dispatch (Representative 7-Day Window)")
        start_step = 96 * 160  # Mid-June
        end_step = start_step + 96 * 7
        ts_win = base_load.timestamps[start_step:end_step]

        fig_disp = go.Figure()
        fig_disp.add_trace(
            go.Scatter(x=ts_win, y=sim_active["p_load_kw"][start_step:end_step], name="Facility Load P_Load (kW)", line=dict(color="#94a3b8", width=1.8))
        )
        fig_disp.add_trace(
            go.Scatter(x=ts_win, y=sim_active["p_pv_kw"][start_step:end_step], name="Solar PV Output P_Solar (kW)", line=dict(color="#f59e0b", width=2.2))
        )
        fig_disp.add_trace(
            go.Scatter(
                x=ts_win,
                y=sim_active["p_grid_kw"][start_step:end_step],
                name="Residual Grid Import P_Grid (kW)",
                line=dict(color="#38bdf8", width=2.2),
            )
        )
        fig_disp.update_layout(
            title=dict(text="<b>15-Minute Facility Load, Solar Generation & Residual Grid Import</b>", x=0.01, y=0.98, xanchor="left"),
            template="plotly_dark",
            paper_bgcolor="rgba(15, 23, 42, 0.0)",
            plot_bgcolor="rgba(15, 23, 42, 0.55)",
            height=350,
            margin=dict(l=50, r=30, t=85, b=40),
            legend=dict(orientation="h", yanchor="bottom", y=1.08, xanchor="left", x=0.01),
            yaxis=dict(title="Active Power (kW)", gridcolor="#1e293b"),
        )
        st.plotly_chart(fig_disp, use_container_width=True, key=f"{key_prefix}_disp_chart")

    # Build standardized Residual LoadSeries2025 for 4-Pillar Billing Engine
    residual_load = build_residual_load_series_2025(
        base_load=base_load,
        residual_power_kw=sim_active["p_grid_kw"],
    )

    # ----------------------------------------------------------------------------------
    # TAB 3: 4-Pillar Contract Interaction & Bill Comparison
    # ----------------------------------------------------------------------------------
    with tabs[2]:
        st.markdown("#### :material/bolt: Solar TOU Window Coincidence & Peak Demand Impact")
        t1, t2, t3, t4 = st.columns(4)
        if base_load.tou_window_codes is not None:
            t1.metric("Saved in Resto (05:00-18:00)", f"{sim_active['resto_saved_kwh']:,.0f} kWh", "Daytime Solar Window")
            t2.metric("Saved in Pico (18:00-23:00)", f"{sim_active['pico_or_ht_saved_kwh']:,.0f} kWh", "Evening Peak Window")
            t3.metric("Saved in Valle (23:00-05:00)", f"{sim_active['valle_or_nt_saved_kwh']:,.0f} kWh", "Night Off-Peak Window")
        else:
            t1.metric("Saved in High-Tariff (HT 07-23h)", f"{sim_active['pico_or_ht_saved_kwh']:,.0f} kWh", "Weekday Daytime HT")
            t2.metric("Saved in Low-Tariff (NT Weekend/Night)", f"{sim_active['valle_or_nt_saved_kwh']:,.0f} kWh", "Weekend Daytime NT")
            t3.metric("Residual Grid Import", f"{sim_active['grid_import_kwh']:,.0f} kWh", f"-{sim_active['autarky_pct']:.1f}% Grid kWh")
        t4.metric(
            "Annual Max Peak Impact",
            f"{sim_active['peak_after_kw']:,.1f} kW",
            f"-{sim_active['peak_shaved_kw']:,.1f} kW vs. {sim_active['peak_before_kw']:,.1f} kW",
            delta_color="normal",
        )

        period_options = ["Annual Statement 2025 (Full Year)"] + [
            f"2025-{m:02d} ({MONTH_NAMES[m - 1]})" for m in range(1, 13)
        ]
        sel_period = st.selectbox(
            ":material/calendar_month: Select Billing Statement Period for 4-Pillar Comparison",
            options=period_options,
            index=0,
            key=f"{key_prefix}_period_sel",
        )

        comp_data = evaluate_scenario_4pillar_bill_comparison(
            base_load=base_load,
            residual_load=residual_load,
            base_config=base_config,
            alt_config=base_config,
            period_choice=sel_period,
        )

        assumptions_dict = build_assumptions_register_dict(
            load_series=base_load,
            config=base_config,
            source_filename=site_label,
            bess_config=None,
        )
        physical_kpis = {
            "peak_before_kw": sim_active["peak_before_kw"],
            "peak_after_kw": sim_active["peak_after_kw"],
            "peak_shaved_kw": sim_active["peak_shaved_kw"],
            "peak_shaved_pct": (sim_active["peak_shaved_kw"] / max(1.0, sim_active["peak_before_kw"]) * 100.0),
            "grid_limit_kw": base_config.dso.contracted_capacity_kw,
            "overload_hrs_before": float(np.sum(base_load.power_kw > base_config.dso.contracted_capacity_kw) * 0.25),
            "overload_hrs_after": float(np.sum(residual_load.power_kw > base_config.dso.contracted_capacity_kw) * 0.25),
            "remaining_deficit_kwh": 0.0,
            "load_kwh": sim_active["load_kwh"],
            "grid_import_kwh": sim_active["grid_import_kwh"],
            "discharge_kwh": sim_active["direct_kwh"],
            "rte_loss_kwh": sim_active["export_kwh"],
        }

        render_shared_4pillar_bill_comparison_ui(
            comp_data=comp_data,
            baseline_col_title="Baseline (No Solar)",
            scenario_col_title=f"With Solar ({active_pv_kwp:,.0f} kWp)",
            site_name=site_label,
            assumptions_dict=assumptions_dict,
            physical_kpis=physical_kpis,
            key_prefix=key_prefix,
        )

    # ----------------------------------------------------------------------------------
    # TAB 4: Solar CAPEX, Payback & 15Y TCO
    # ----------------------------------------------------------------------------------
    with tabs[3]:
        st.markdown("#### :material/account_balance: Solar PV Turnkey CAPEX, O&M & 15-Year TCO Evaluation")
        f1, f2, f3 = st.columns(3)
        default_capex_per_kwp = 850000.0 if curr == "ARS" else 880.0
        default_om_per_kwp = 12000.0 if curr == "ARS" else 14.0
        default_fit_rate = 35.0 if curr == "ARS" else 0.045

        with f1:
            capex_per_kwp = st.number_input(
                f"Turnkey Solar PV CAPEX ({curr}/kWp)",
                min_value=0.0,
                value=float(default_capex_per_kwp),
                step=25.0 if curr != "ARS" else 25000.0,
                key=f"{key_prefix}_capex_kwp_{curr}",
            )
        with f2:
            om_per_kwp_yr = st.number_input(
                f"Annual Solar O&M Cost ({curr}/kWp/yr)",
                min_value=0.0,
                value=float(default_om_per_kwp),
                step=1.0 if curr != "ARS" else 1000.0,
                key=f"{key_prefix}_om_kwp_{curr}",
            )
        with f3:
            feed_in_rate_kwh = st.number_input(
                f"Grid Export Feed-In Remuneration ({curr}/kWh)",
                min_value=0.0,
                value=float(default_fit_rate),
                step=0.005 if curr != "ARS" else 5.0,
                format="%.4f",
                key=f"{key_prefix}_fit_{curr}",
            )

        res_base_full = calculate_status_quo_master_2025(load=base_load, config=base_config)
        res_after_full = calculate_status_quo_master_2025(load=residual_load, config=base_config)

        total_capex = active_pv_kwp * capex_per_kwp
        annual_om = active_pv_kwp * om_per_kwp_yr
        annual_fit_credit = sim_active["export_kwh"] * feed_in_rate_kwh
        bill_savings_net = res_base_full.total_annual_net - res_after_full.total_annual_net
        annual_net_savings = bill_savings_net + annual_fit_credit - annual_om
        payback_yrs = (total_capex / annual_net_savings) if annual_net_savings > 0 else 99.9

        npv_before, sched_before = compute_15y_tco_npv(
            capex=0.0,
            annual_grid_bill_year1=res_base_full.total_annual_net,
            discount_rate_pct=base_config.discount_rate_pct,
            escalation_rate_pct=base_config.energy_escalation_pct,
        )
        npv_after, sched_after = compute_15y_tco_npv(
            capex=total_capex,
            annual_grid_bill_year1=res_after_full.total_annual_net,
            annual_tech_opex_year1=annual_om,
            annual_feed_in_credit_year1=annual_fit_credit,
            discount_rate_pct=base_config.discount_rate_pct,
            escalation_rate_pct=base_config.energy_escalation_pct,
        )

        fig_tco = go.Figure()
        fig_tco.add_trace(
            go.Scatter(
                x=[r["year"] for r in sched_before],
                y=[r["cumulative_discounted"] for r in sched_before],
                mode="lines+markers",
                name="Status Quo (No Solar)",
                line=dict(color="#ef4444", width=3, dash="dash"),
            )
        )
        fig_tco.add_trace(
            go.Scatter(
                x=[r["year"] for r in sched_after],
                y=[r["cumulative_discounted"] for r in sched_after],
                mode="lines+markers",
                name=f"With Solar PV ({active_pv_kwp:,.0f} kWp)",
                line=dict(color="#f59e0b", width=3),
            )
        )
        fig_tco.update_layout(
            title=dict(text="<b>15-Year Cumulative Discounted TCO: Status Quo vs. Standalone Solar PV</b>", x=0.01, y=0.98, xanchor="left"),
            template="plotly_dark",
            paper_bgcolor="rgba(15, 23, 42, 0.0)",
            plot_bgcolor="rgba(15, 23, 42, 0.55)",
            height=370,
            margin=dict(l=50, r=30, t=85, b=40),
            xaxis=dict(title="Project Year", gridcolor="#1e293b"),
            yaxis=dict(title=f"Cumulative Discounted Cost ({curr})", gridcolor="#1e293b"),
        )
        st.plotly_chart(fig_tco, use_container_width=True, key=f"{key_prefix}_tco_chart")

        scen_output = ScenarioEvaluationOutput(
            scenario_id="solar_only",
            scenario_name="Scenario 3: Standalone Solar PV",
            sub_scenario_label=f"{active_pv_kwp:,.1f} kWp {tech_choice} ({sim_active['self_consumption_pct']:.1f}% SCR)",
            currency_code=curr,
            peak_before_kw=sim_active["peak_before_kw"],
            peak_after_kw=sim_active["peak_after_kw"],
            peak_shaved_kw=sim_active["peak_shaved_kw"],
            peak_shaved_pct=(sim_active["peak_shaved_kw"] / max(1.0, sim_active["peak_before_kw"]) * 100.0),
            grid_limit_kw=base_config.dso.contracted_capacity_kw,
            overload_hours_before=float(np.sum(base_load.power_kw > base_config.dso.contracted_capacity_kw) * 0.25),
            overload_hours_after=float(np.sum(residual_load.power_kw > base_config.dso.contracted_capacity_kw) * 0.25),
            annual_load_kwh=sim_active["load_kwh"],
            annual_grid_import_before_kwh=sim_active["load_kwh"],
            annual_grid_import_after_kwh=sim_active["grid_import_kwh"],
            self_consumption_pct=sim_active["self_consumption_pct"],
            autarky_pct=sim_active["autarky_pct"],
            capex_total=float(total_capex),
            annual_tech_opex=float(annual_om),
            annual_grid_bill_net_before=float(res_base_full.total_annual_net),
            annual_grid_bill_net_after=float(res_after_full.total_annual_net),
            annual_grid_bill_gross_before=float(res_base_full.total_annual_gross),
            annual_grid_bill_gross_after=float(res_after_full.total_annual_gross),
            annual_net_savings=float(annual_net_savings),
            simple_payback_years=float(payback_yrs),
            npv_15y_tco_before=float(npv_before),
            npv_15y_tco_after=float(npv_after),
            npv_15y_net_benefit=float(npv_before - npv_after),
        )
        render_scenario_evaluation_output_card(output=scen_output, key_prefix=key_prefix)

    return scen_output


def main() -> None:
    st.set_page_config(
        page_title="Standalone Solar PV Sandbox (Scenario 3)",
        page_icon=":material/wb_sunny:",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    render_solar_sandbox(key_prefix="solar_sb")


if __name__ == "__main__":
    main()

