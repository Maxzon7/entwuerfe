"""
========================================================================================
Sub-Tab 1: Regulated Grid Operator (DSO) (contract/tab_dso.py)
========================================================================================

Description:
------------
Renders the dedicated Regulated Grid Operator (DSO) configuration and isolated analysis:
  1. DSO Company & Voltage Tier catalog selection (Enexis, Liander, Stedin 2025).
  2. Side-by-side st.form with technical inputs on the left and Direct Cost Impact preview on the right.
  3. Isolated Grid Operator Performance & Billing Analysis:
     - 4 executive KPI cards (Net Total, Capacity Fee, Peak Fee, Breach Status).
     - Interactive Monthly Peak Demand vs. Reserved Grid Capacity chart.
     - Itemized 12-Month DSO settlement statement table.
========================================================================================
"""

from typing import Tuple, Dict, Any, List
import streamlit as st
import pandas as pd

from current_model.ui.common.cards import render_kpi_card
from ui_sandbox.Currentsituation_sandbox.engine.config_and_models import (
    LoadSeries2025,
    DSOTariff,
    DSOMonthlyResult,
    MonthlyConsumptionRecord,
)
from ui_sandbox.Currentsituation_sandbox.engine.tariff_defaults_2025 import (
    DSO_CATALOGS_2025,
)
from ui_sandbox.Currentsituation_sandbox.engine.consumption_pipeline import (
    extract_monthly_consumption_records,
)
from ui_sandbox.Currentsituation_sandbox.engine.dso_accounting import (
    calculate_dso_accounting_2025,
)
import plotly.graph_objects as go

try:
    from ui_sandbox.Currentsituation_sandbox.contract.charts import (
        create_dso_monthly_peak_figure,
    )
except (ImportError, AttributeError):
    try:
        from .charts import create_dso_monthly_peak_figure
    except (ImportError, AttributeError):
        try:
            from contract.charts import create_dso_monthly_peak_figure
        except (ImportError, AttributeError):
            def create_dso_monthly_peak_figure(
                dso_monthly_results: List[Any],
                contracted_capacity_kw: float
            ) -> go.Figure:
                month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
                peaks = []
                colors = []
                custom_hover = []
                for idx, r in enumerate(dso_monthly_results):
                    p_val = getattr(r, "measured_peak_demand_kw", getattr(r, "peak_demand_kw", 0.0))
                    is_breach = getattr(r, "is_capacity_breached", p_val > (contracted_capacity_kw + 1e-4))
                    peaks.append(p_val)
                    m_name = month_names[idx] if idx < len(month_names) else f"M{idx+1}"
                    if is_breach:
                        colors.append("#EF4444")
                        excess = p_val - contracted_capacity_kw
                        custom_hover.append(f"{m_name}<br>Peak: {p_val:,.1f} kW<br>Status: Capacity Breach (+{excess:,.1f} kW)")
                    else:
                        colors.append("#38BDF8")
                        margin = contracted_capacity_kw - p_val
                        custom_hover.append(f"{m_name}<br>Peak: {p_val:,.1f} kW<br>Status: Within Limit (Headroom: {margin:,.1f} kW)")
                fig = go.Figure()
                fig.add_trace(go.Bar(x=month_names[:len(peaks)], y=peaks, name="Monthly Peak (kW)", marker_color=colors, hoverinfo="text", hovertext=custom_hover, opacity=0.9))
                fig.add_trace(go.Scatter(x=month_names[:len(peaks)], y=[contracted_capacity_kw] * len(peaks), mode="lines", name=f"Contracted Capacity ({contracted_capacity_kw:,.0f} kW)", line=dict(color="#F59E0B", width=2.5, dash="dash"), hoverinfo="skip"))
                fig.update_layout(template="plotly_dark", title=dict(text="<b>Monthly Peak Demand vs. Reserved Grid Capacity</b>", font=dict(size=14, color="#F8FAFC"), x=0.02, y=0.96), xaxis=dict(title="Billing Month", gridcolor="#1E293B"), yaxis=dict(title="Peak Power (kW)", gridcolor="#1E293B", zerolinecolor="#334155"), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5), margin=dict(l=40, r=30, t=55, b=40), plot_bgcolor="#0B0F19", paper_bgcolor="#0B0F19", height=320, hovermode="closest")
                return fig


def render_dso_tab(
    load_series: LoadSeries2025,
    key_prefix: str = "currsit_contract"
) -> Tuple[DSOTariff, List[DSOMonthlyResult], Dict[str, Any]]:
    """
    Renders the complete Regulated Grid Operator (DSO) tab including parameters form,
    instant cost preview, and isolated 12-month billing performance metrics.
    """
    st.markdown("##### Regulated Grid Connection & Transport Tariffs (Enexis / Liander / Stedin 2025)")

    # 1. Company and Voltage Tier Selection Toolbar
    col_dso_co, col_dso_tier = st.columns([1.5, 2.5])
    with col_dso_co:
        dso_company_options = list(DSO_CATALOGS_2025.keys()) + ["Custom / Other Grid Operator"]
        selected_dso_company = st.selectbox(
            "Grid Operator (DSO):",
            options=dso_company_options,
            index=0,
            key=f"{key_prefix}_dso_company"
        )

    with col_dso_tier:
        if selected_dso_company in DSO_CATALOGS_2025:
            tier_dict = DSO_CATALOGS_2025[selected_dso_company]
            tier_options = list(tier_dict.keys())
            default_tier_idx = 0
            for idx, t_name in enumerate(tier_options):
                if "MS-D" in t_name or ("MS" in t_name and "LS" not in t_name):
                    default_tier_idx = idx
                    break
            selected_tier = st.selectbox(
                "Tariff Category & Voltage Tier:",
                options=tier_options,
                index=default_tier_idx,
                key=f"{key_prefix}_dso_tier"
            )
            preset_data = tier_dict[selected_tier]
            st.caption(f":material/info: *{preset_data.get('description', '')}*")
        else:
            selected_tier = "Custom"
            preset_data = {
                "aansluitdienst_annual": 1653.00,
                "vastrecht_annual": 441.00,
                "rate_contracted_monthly": 2.4400,
                "rate_peak_monthly": 3.7100,
                "rate_peak_kwh": 0.0250,
                "rate_offpeak_kwh": 0.0250,
                "reactive_tariff": 0.0188,
            }
            st.caption(":material/tune: *Fully customizable manual grid operator tariffs.*")

    # Reload / Always Reload options for default preset rates
    state_always_reload_key = f"{key_prefix}_dso_always_reload_{selected_dso_company}_{selected_tier}"
    always_reload = st.session_state.get(state_always_reload_key, False)

    reload_version_key = f"{key_prefix}_dso_version_{selected_dso_company}_{selected_tier}"
    form_version = st.session_state.get(reload_version_key, 0)

    r_col1, r_col2 = st.columns([2.5, 2.5])
    with r_col1:
        if st.button(
            ":material/restart_alt: Reload Preset Defaults",
            key=f"{key_prefix}_btn_reload_preset_{selected_dso_company}_{selected_tier}",
            use_container_width=True,
            help="Reset all values and TOU tables for this grid tier back to the original catalog defaults."
        ):
            st.session_state[reload_version_key] = form_version + 1
            for k in list(st.session_state.keys()):
                if f"{selected_dso_company}_{selected_tier}" in k or "dso_base_fee" in k or "dso_p_contract" in k or "dso_rate_" in k:
                    del st.session_state[k]
            st.rerun()

    with r_col2:
        always_reload = st.checkbox(
            ":material/sync: Always reload catalog defaults on tier switch",
            value=always_reload,
            key=state_always_reload_key,
            help="When enabled, switching tiers or companies automatically discards custom edits and reloads original catalog defaults."
        )

    # Dynamic session state key for DSO TOU rates matrix
    state_dso_tou_key = f"{key_prefix}_dso_tou_df_{selected_dso_company}_{selected_tier}_v{form_version}"
    if state_dso_tou_key not in st.session_state or always_reload:
        default_peak = float(preset_data.get("rate_peak_kwh", 0.0250))
        default_offpeak = float(preset_data.get("rate_offpeak_kwh", 0.0250))
        st.session_state[state_dso_tou_key] = pd.DataFrame([
            {"name": "Daytime / Working Hours (kWh high)", "rate": default_peak, "start_time": "07:00", "end_time": "23:00"},
            {"name": "Night & Weekend / Off-Peak (kWh low)", "rate": default_offpeak, "start_time": "23:00", "end_time": "07:00"}
        ])

    # Pre-compute current/saved DSO cost components for live preview card using engine
    saved_dso_kw_val = float(st.session_state.get(f"{key_prefix}_dso_p_contract_{selected_dso_company}_{selected_tier}_v{form_version}", max(50.0, round(load_series.peak_demand_kw * 1.05, 0))))
    saved_dso_base_val = float(st.session_state.get(f"{key_prefix}_dso_base_fee_{selected_dso_company}_{selected_tier}_v{form_version}", round(float(preset_data.get("vastrecht_annual", 441.0)) / 12.0, 2)))
    saved_dso_cap_rate = float(st.session_state.get(f"{key_prefix}_dso_rate_cap_{selected_dso_company}_{selected_tier}_v{form_version}", float(preset_data.get("rate_contracted_monthly", 2.4400))))
    saved_dso_peak_rate = float(st.session_state.get(f"{key_prefix}_dso_rate_peak_{selected_dso_company}_{selected_tier}_v{form_version}", float(preset_data.get("rate_peak_monthly", 3.7100))))
    saved_adjust_breach = bool(st.session_state.get(f"{key_prefix}_dso_adjust_breach", True))

    _records_preview: List[MonthlyConsumptionRecord] = extract_monthly_consumption_records(load_series)
    _active_tou_df_prev = st.session_state.get(state_dso_tou_key)
    _prev_trans_ht = float(preset_data.get("rate_peak_kwh", 0.0250))
    _prev_trans_nt = float(preset_data.get("rate_offpeak_kwh", 0.0250))
    if _active_tou_df_prev is not None and not _active_tou_df_prev.empty:
        for _r in _active_tou_df_prev.to_dict(orient="records"):
            _rn = str(_r.get("name", "")).lower()
            _rr = float(_r.get("rate", _prev_trans_ht))
            if any(_k in _rn for _k in ["high", "normaal", "peak", "ht", "hoch", "daytime", "working"]):
                _prev_trans_ht = _rr
            elif any(_k in _rn for _k in ["off", "dal", "laag", "nt", "niedrig", "night", "weekend"]):
                _prev_trans_nt = _rr

    # Build preview tariff and execute exact DSO accounting engine
    _preview_tariff = DSOTariff(
        dso_name=selected_dso_company,
        grid_tier=selected_tier,
        connection_category="standard",
        fixed_connection_annual=0.0,
        fixed_transport_annual=saved_dso_base_val * 12.0,
        cable_surcharge_annual=0.0,
        contracted_capacity_kw=saved_dso_kw_val,
        rate_contracted_capacity=saved_dso_cap_rate,
        rate_peak_demand=saved_dso_peak_rate,
        rate_transport_peak_kwh=_prev_trans_ht,
        rate_transport_offpeak_kwh=_prev_trans_nt,
        adjust_capacity_on_breach=saved_adjust_breach,
    )
    _dso_results_preview, _dso_summary_preview = calculate_dso_accounting_2025(
        load=load_series,
        monthly_consumption=_records_preview,
        dso_tariff=_preview_tariff
    )

    _total_ht_kwh = sum(r.peak_tou_kwh for r in _records_preview)
    _total_nt_kwh = sum(r.offpeak_tou_kwh for r in _records_preview)
    _prev_vol_ht_annual = _total_ht_kwh * _prev_trans_ht
    _prev_vol_nt_annual = _total_nt_kwh * _prev_trans_nt
    _prev_vol_annual = _dso_summary_preview["total_volumetric_transport_annual"]
    _prev_fixed_annual = _dso_summary_preview["total_fixed_transport_annual"]
    _prev_cap_annual = _dso_summary_preview["total_capacity_fee_annual"]
    _prev_peak_demand_annual = _dso_summary_preview["total_peak_demand_fee_annual"]
    _prev_dso_net_annual = _dso_summary_preview["total_dso_net_annual"]
    _prev_breach_months = [r.month_name for r in _records_preview if r.peak_demand_kw > (saved_dso_kw_val + 1e-4)]

    # 2. Main Form (Side-by-Side: Inputs on Left, Direct Cost Impact on Right)
    with st.form(key=f"{key_prefix}_dso_contract_form_{selected_dso_company}_{selected_tier}_v{form_version}"):
        col_form_inputs, col_form_preview = st.columns([1.65, 1.0], gap="large")

        with col_form_inputs:
            st.subheader("1. Grid Capacity & Fixed Fees")

            dso_contract_name_default = f"{selected_dso_company} - {selected_tier} (2025)"
            contract_name_val = st.text_input(
                "Contract Name / Identifier:",
                value=dso_contract_name_default,
                key=f"{key_prefix}_dso_name_val_{selected_dso_company}_{selected_tier}_v{form_version}",
                help="Custom name or tariff identifier for the regulated grid operator contract."
            )

            c1, c2 = st.columns(2)
            with c1:
                curr_options = ["EUR", "USD", "GBP", "CHF"]
                currency = st.selectbox(
                    "Currency:",
                    options=curr_options,
                    index=0,
                    key=f"{key_prefix}_dso_currency_v{form_version}"
                )
                ann_standing_default = float(preset_data.get("vastrecht_annual", 441.0))
                monthly_standing_default = round(ann_standing_default / 12.0, 2)
                base_fee = st.number_input(
                    "Fixed Monthly Grid Fee (€/month):",
                    min_value=0.0,
                    value=monthly_standing_default,
                    step=5.0,
                    format="%.2f",
                    key=f"{key_prefix}_dso_base_fee_{selected_dso_company}_{selected_tier}_v{form_version}",
                    help="Fixed standing charge for grid access (Fixed Transport Standing Charge €/month)"
                )
                contracted_kw = st.number_input(
                    "Reserved Grid Capacity (kW):",
                    min_value=10.0,
                    max_value=20000.0,
                    value=float(max(50.0, round(load_series.peak_demand_kw * 1.05, 0))),
                    step=10.0,
                    format="%.1f",
                    key=f"{key_prefix}_dso_p_contract_{selected_dso_company}_{selected_tier}_v{form_version}",
                    help="Power reserved on the grid for your facility (Contracted Capacity in kW)"
                )

            with c2:
                capacity_tariff = st.number_input(
                    "Reserved Capacity Rate (€/kW/month):",
                    min_value=0.0,
                    value=float(preset_data.get("rate_contracted_monthly", 2.4400)),
                    step=0.01,
                    format="%.4f",
                    key=f"{key_prefix}_dso_rate_cap_{selected_dso_company}_{selected_tier}_v{form_version}",
                    help="Monthly fee billed per reserved kW (Contracted Capacity Tariff)"
                )
                demand_tariff = st.number_input(
                    "Monthly Peak Demand Rate (€/kW/month):",
                    min_value=0.0,
                    value=float(preset_data.get("rate_peak_monthly", 3.7100)),
                    step=0.01,
                    format="%.4f",
                    key=f"{key_prefix}_dso_rate_peak_{selected_dso_company}_{selected_tier}_v{form_version}",
                    help="Monthly fee billed per measured 15-minute maximum peak (Peak Demand Charge)"
                )
                max_physical_kw = st.number_input(
                    "Physical Transformer Limit (kW):",
                    min_value=10.0,
                    value=float(preset_data.get("max_physical_limit_kw", 1000.0)),
                    step=50.0,
                    format="%.1f",
                    key=f"{key_prefix}_dso_max_phys_{selected_dso_company}_{selected_tier}_v{form_version}",
                    help="Maximum physical electrical limit of your transformer or main connection"
                )
                penalty_rate = st.number_input(
                    "Capacity Exceedance Penalty (€/kW):",
                    min_value=0.0,
                    value=float(preset_data.get("peak_penalty_rate_kw", 0.2500)),
                    step=0.05,
                    format="%.4f",
                    key=f"{key_prefix}_dso_penalty_{selected_dso_company}_{selected_tier}_v{form_version}",
                    help="Penalty fee charged when monthly peak demand exceeds reserved grid capacity"
                )

            st.subheader("2. Reactive Power & Power Factor")
            q1, q2, q3 = st.columns(3)
            with q1:
                reactive_tariff = st.number_input(
                    "Reactive Power Rate (€/kVARh):",
                    min_value=0.0,
                    value=float(preset_data.get("reactive_tariff", 0.0188)),
                    step=0.005,
                    format="%.4f",
                    key=f"{key_prefix}_dso_reactive_{selected_dso_company}_{selected_tier}_v{form_version}",
                    help="Tariff for consumed reactive energy (€/kVARh)"
                )
            with q2:
                min_cos_phi = st.number_input(
                    "Target Power Factor (cos φ):",
                    min_value=0.50,
                    max_value=1.00,
                    value=float(preset_data.get("min_power_factor", 0.90)),
                    step=0.02,
                    format="%.2f",
                    key=f"{key_prefix}_dso_cosphi_{selected_dso_company}_{selected_tier}_v{form_version}",
                    help="Minimum required power factor (cos φ = 0.90) to avoid reactive charges"
                )
            with q3:
                reactive_allowance = st.number_input(
                    "Free Reactive Allowance (% of kWh):",
                    min_value=0.0,
                    max_value=100.0,
                    value=float(preset_data.get("reactive_allowance_pct", 33.0)),
                    step=1.0,
                    format="%.1f",
                    key=f"{key_prefix}_dso_q_allow_{selected_dso_company}_{selected_tier}_v{form_version}",
                    help="Permitted free reactive energy as a percentage of active consumption (33%)"
                )

            st.subheader("3. Time-of-Use Electricity Rates (Working Hours vs. Off-Peak)")
            st.caption("Define Time-of-Use rate windows. The table supports adding and deleting rows:")

            edited_dso_tou = st.data_editor(
                st.session_state[state_dso_tou_key],
                num_rows="dynamic",
                use_container_width=True,
                column_config={
                    "name": st.column_config.TextColumn("Tariff Name", required=True),
                    "rate": st.column_config.NumberColumn(
                        f"Rate ({currency}/kWh)",
                        format="%.4f",
                        min_value=0.0,
                        step=0.0001,
                        required=True
                    ),
                    "start_time": st.column_config.TextColumn("Start Time (HH:MM)", required=True),
                    "end_time": st.column_config.TextColumn("End Time (HH:MM)", required=True)
                },
                key=f"{key_prefix}_dso_tou_editor_{selected_dso_company}_{selected_tier}_v{form_version}"
            )

            weekend_off_peak = st.checkbox(
                "Treat Weekends as Off-Peak (Apply Lowest Tariff)",
                value=True,
                key=f"{key_prefix}_dso_weekend_offpeak",
                help="Apply the off-peak tariff throughout the entire weekend."
            )

            adjust_breach = st.checkbox(
                ":material/shield: Adjust capacity billing to actual peak during breach months (Standard rule)",
                value=True,
                key=f"{key_prefix}_dso_adjust_breach",
                help="When monthly peak demand exceeds reserved grid capacity, capacity fee is billed on actual measured peak."
            )

        with col_form_preview:
            st.markdown("#### :material/receipt_long: Direct Cost Impact")
            st.caption("Calculated based on active load baseline & current tariff rates:")

            with st.container(border=True):
                st.metric(
                    label="DSO Net Annual Cost",
                    value=f"€ {_prev_dso_net_annual:,.2f}",
                    delta=f"€ {_prev_dso_net_annual / 12.0:,.2f} / month (avg)",
                    delta_color="off"
                )

                st.divider()

                st.markdown("**Itemized Cost Breakdown (Year & Month):**")
                cost_table_html = f"""
                <div style="width: 100%; overflow-x: auto;">
                <table style="width: 100%; border-collapse: collapse; font-size: 0.86rem;">
                    <thead>
                        <tr style="border-bottom: 1px solid rgba(128, 128, 128, 0.3); color: #888888; font-size: 0.78rem;">
                            <th style="text-align: left; padding: 4px 6px;">Component</th>
                            <th style="text-align: right; padding: 4px 6px;">Per Year</th>
                            <th style="text-align: right; padding: 4px 6px;">Per Month</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr style="border-bottom: 1px solid rgba(128, 128, 128, 0.15);">
                            <td style="padding: 6px 6px;">Fixed Standing Fee:</td>
                            <td style="text-align: right; padding: 6px 6px; font-weight: bold;">€ {_prev_fixed_annual:,.2f}</td>
                            <td style="text-align: right; padding: 6px 6px; color: #a0aec0;">€ {_prev_fixed_annual / 12.0:,.2f}</td>
                        </tr>
                        <tr style="border-bottom: 1px solid rgba(128, 128, 128, 0.15);">
                            <td style="padding: 6px 6px;">Reserved Capacity:</td>
                            <td style="text-align: right; padding: 6px 6px; font-weight: bold;">€ {_prev_cap_annual:,.2f}</td>
                            <td style="text-align: right; padding: 6px 6px; color: #a0aec0;">€ {_prev_cap_annual / 12.0:,.2f}</td>
                        </tr>
                        <tr style="border-bottom: 1px solid rgba(128, 128, 128, 0.15);">
                            <td style="padding: 6px 6px;">Peak Demand:</td>
                            <td style="text-align: right; padding: 6px 6px; font-weight: bold;">€ {_prev_peak_demand_annual:,.2f}</td>
                            <td style="text-align: right; padding: 6px 6px; color: #a0aec0;">€ {_prev_peak_demand_annual / 12.0:,.2f}</td>
                        </tr>
                        <tr style="border-bottom: 1px solid rgba(128, 128, 128, 0.15);">
                            <td style="padding: 6px 6px; font-weight: 600;">Volumetric Transport:</td>
                            <td style="text-align: right; padding: 6px 6px; font-weight: bold;">€ {_prev_vol_annual:,.2f}</td>
                            <td style="text-align: right; padding: 6px 6px; font-weight: bold; color: #a0aec0;">€ {_prev_vol_annual / 12.0:,.2f}</td>
                        </tr>
                        <tr style="border-bottom: 1px solid rgba(128, 128, 128, 0.1); font-size: 0.80rem; color: #a0aec0;">
                            <td style="padding: 3px 6px 3px 18px;">↳ Daytime / HT ({_total_ht_kwh:,.0f} kWh)</td>
                            <td style="text-align: right; padding: 3px 6px;">€ {_prev_vol_ht_annual:,.2f}</td>
                            <td style="text-align: right; padding: 3px 6px;">€ {_prev_vol_ht_annual / 12.0:,.2f}</td>
                        </tr>
                        <tr style="border-bottom: 1px solid rgba(128, 128, 128, 0.1); font-size: 0.80rem; color: #a0aec0;">
                            <td style="padding: 3px 6px 3px 18px;">↳ Off-Peak / NT ({_total_nt_kwh:,.0f} kWh)</td>
                            <td style="text-align: right; padding: 3px 6px;">€ {_prev_vol_nt_annual:,.2f}</td>
                            <td style="text-align: right; padding: 3px 6px;">€ {_prev_vol_nt_annual / 12.0:,.2f}</td>
                        </tr>
                    </tbody>
                </table>
                </div>
                """
                st.markdown(cost_table_html, unsafe_allow_html=True)

                st.divider()

                st.markdown("**Capacity & Grid Diagnostics:**")
                st.write(f"• Facility Peak: **{load_series.peak_demand_kw:,.1f} kW**")
                st.write(f"• Reserved Capacity: **{saved_dso_kw_val:,.1f} kW**")

                if len(_prev_breach_months) > 0:
                    st.warning(
                        f":material/warning: **Capacity Overload:** Exceeded in **{len(_prev_breach_months)} month(s)**: "
                        f"{', '.join(_prev_breach_months[:3])}{'...' if len(_prev_breach_months) > 3 else ''}."
                    )
                else:
                    st.success(":material/check_circle: **Safe Capacity:** Peak within reserved limit across all 12 months.")

        st.markdown("---")
        submitted_dso = st.form_submit_button(
            "Save Contract Configuration & Recalculate",
            icon=":material/save:",
            type="primary",
            use_container_width=True
        )

    if submitted_dso:
        if edited_dso_tou is not None and not edited_dso_tou.empty:
            st.session_state[state_dso_tou_key] = edited_dso_tou
        st.success(f"Grid Operator configuration saved: **{contract_name_val}**", icon=":material/check_circle:")

    # Extract active peak & offpeak rates from the TOU matrix for calculation pipeline
    active_tou_df = st.session_state[state_dso_tou_key]
    trans_norm_kwh = float(preset_data.get("rate_peak_kwh", 0.0250))
    trans_off_kwh = float(preset_data.get("rate_offpeak_kwh", 0.0250))
    if active_tou_df is not None and not active_tou_df.empty:
        rows = active_tou_df.to_dict(orient="records")
        for r in rows:
            r_name = str(r.get("name", "")).lower()
            r_rate = float(r.get("rate", trans_norm_kwh))
            if any(k in r_name for k in ["high", "normaal", "peak", "ht", "hoch", "daytime", "working"]):
                trans_norm_kwh = r_rate
            elif any(k in r_name for k in ["off", "dal", "laag", "nt", "niedrig", "night", "weekend"]):
                trans_off_kwh = r_rate

    # Construct authoritative DSOTariff model
    dso_tariff = DSOTariff(
        dso_name=selected_dso_company,
        grid_tier=selected_tier,
        connection_category="standard",
        fixed_connection_annual=0.0,
        fixed_transport_annual=base_fee * 12.0,
        cable_surcharge_annual=0.0,
        contracted_capacity_kw=contracted_kw,
        rate_contracted_capacity=capacity_tariff,
        rate_peak_demand=demand_tariff,
        rate_transport_peak_kwh=trans_norm_kwh,
        rate_transport_offpeak_kwh=trans_off_kwh,
        adjust_capacity_on_breach=adjust_breach,
        max_physical_limit_kw=max_physical_kw,
        peak_penalty_rate_kw=penalty_rate,
        reactive_power_tariff=reactive_tariff,
        min_power_factor=min_cos_phi,
        reactive_allowance_pct=reactive_allowance,
    )

    # Execute authoritative DSO accounting
    monthly_consumption = extract_monthly_consumption_records(load_series)
    dso_results, dso_summary = calculate_dso_accounting_2025(
        load=load_series,
        monthly_consumption=monthly_consumption,
        dso_tariff=dso_tariff
    )

    # 3. Dedicated Isolated DSO Performance & Cost Analysis (Matching Supplier Tab Pattern!)
    st.markdown("---")
    st.markdown("##### :material/payments: Isolated Grid Operator Performance & Cost Analysis")

    kpi_c1, kpi_c2, kpi_c3, kpi_c4 = st.columns(4)
    with kpi_c1:
        render_kpi_card(
            title=":material/receipt_long: DSO Net Annual Cost",
            value=f"€ {dso_summary['total_dso_net_annual']:,.2f}",
            subtext=f"Monthly Average: € {dso_summary['total_dso_net_annual'] / 12.0:,.2f} / month",
            status="default"
        )
    with kpi_c2:
        render_kpi_card(
            title=":material/speed: Reserved Capacity Spend",
            value=f"€ {dso_summary['total_capacity_fee_annual']:,.2f}",
            subtext=f"Rate: € {dso_tariff.rate_contracted_capacity:.4f} / kW / month",
            status="default"
        )
    with kpi_c3:
        render_kpi_card(
            title=":material/trending_up: Peak Demand Charges",
            value=f"€ {dso_summary['total_peak_demand_fee_annual']:,.2f}",
            subtext=f"Rate: € {dso_tariff.rate_peak_demand:.4f} / kW / month",
            status="default"
        )
    with kpi_c4:
        breach_count = dso_summary.get("breached_months_count", 0)
        breach_status = "alert" if breach_count > 0 else "ok"
        breach_text = f"Breach in {breach_count} month(s)" if breach_count > 0 else f"Peak ≤ {contracted_kw:.0f} kW limit"
        render_kpi_card(
            title=":material/warning: Capacity Breach Status",
            value="Overload Detected" if breach_count > 0 else "100% Compliant",
            subtext=breach_text,
            status=breach_status
        )

    # Isolated Visual Chart & 12-Month DSO Settlement Table
    dso_ch_col1, dso_ch_col2 = st.columns([1.2, 1.8])
    with dso_ch_col1:
        st.markdown("###### :material/insights: Monthly Peak Demand vs. Reserved Capacity")
        fig_dso_peaks = create_dso_monthly_peak_figure(dso_results, contracted_kw)
        st.plotly_chart(fig_dso_peaks, use_container_width=True)

    with dso_ch_col2:
        st.markdown("###### :material/table_chart: Pure DSO Settlement Statement")
        dso_table_rows = []
        month_names = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
        for res in dso_results:
            m_idx = res.month_index - 1
            m_lbl = month_names[m_idx] if 0 <= m_idx < len(month_names) else f"Month {res.month_index}"
            dso_table_rows.append({
                "Month": m_lbl,
                "Peak (kW)": f"{res.measured_peak_demand_kw:,.1f}",
                "Billed (kW)": f"{res.billed_capacity_kw:,.1f}",
                "Capacity (€)": f"€ {res.contracted_capacity_fee:,.2f}",
                "Peak Fee (€)": f"€ {res.peak_demand_fee:,.2f}",
                "Volumetric (€)": f"€ {res.volumetric_transport_fee:,.2f}",
                "DSO Total (€)": f"€ {res.subtotal_dso_net:,.2f}",
                "Breach": "YES" if res.is_capacity_breached else "NO"
            })
        
        # Add summary row
        dso_table_rows.append({
            "Month": "TOTAL",
            "Peak (kW)": f"{load_series.peak_demand_kw:,.1f}",
            "Billed (kW)": "-",
            "Capacity (€)": f"€ {dso_summary['total_capacity_fee_annual']:,.2f}",
            "Peak Fee (€)": f"€ {dso_summary['total_peak_demand_fee_annual']:,.2f}",
            "Volumetric (€)": f"€ {dso_summary['total_volumetric_transport_annual']:,.2f}",
            "DSO Total (€)": f"€ {dso_summary['total_dso_net_annual']:,.2f}",
            "Breach": f"{breach_count} Month(s)" if breach_count > 0 else "NO"
        })
        df_dso_statement = pd.DataFrame(dso_table_rows)
        st.dataframe(df_dso_statement, use_container_width=True, hide_index=True)

    return dso_tariff, dso_results, dso_summary
