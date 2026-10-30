"""
========================================================================================
Sub-Tab 1: Pillar 2 - Grid Network (DSO) (contract/tab_dso.py)
========================================================================================

Implements the standardized 3-Zone layout for Regulated Grid Operator (DSO) tariffs:
  - Zone A (Left Column, 58%): 1. Contract & Tariff Inputs
    Includes provider & voltage tier selectors, Fixed Connection Fee ({CURR}/month),
    Fixed Transport Fee ({CURR}/month), Contracted Grid Capacity (kW), Measured Monthly
    Peak Demand Rate ({CURR}/kW/month), Reactive Power settings, and Peak/Off-Peak (HT/NT)
    volumetric transport rates.
  - Zone B (Right Column, 42%): 2. Component Bill Calculation (How it Adds Up)
    Renders a standardized Electricity Bill Sub-Ledger showing:
    Line Item | Calculation (Quantity × Rate) | Monthly ({CURR}) | Annual ({CURR})
    concluding with = SUBTOTAL GRID NETWORK (NET).
  - Zone C (Bottom Full Width): 3. Monthly Breakdown & Visual Diagnostics
    Renders the interactive Peak vs. Contracted Capacity Plotly chart and 12-month DSO
    statement table inside an expander.
========================================================================================
"""

from typing import Dict, Any, List
import streamlit as st
import pandas as pd
import numpy as np

try:
    from ui_sandbox.Currentsituation_sandbox.engine.config_and_models import (
        DSOTariff,
        LoadSeries2025,
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
    from ui_sandbox.Currentsituation_sandbox.contract.charts import (
        create_dso_monthly_peak_figure,
    )
except ImportError:
    from current_model.ui_sandbox.Currentsituation_sandbox.engine.config_and_models import (
        DSOTariff,
        LoadSeries2025,
    )
    from current_model.ui_sandbox.Currentsituation_sandbox.engine.tariff_defaults_2025 import (
        DSO_CATALOGS_2025,
    )
    from current_model.ui_sandbox.Currentsituation_sandbox.engine.consumption_pipeline import (
        extract_monthly_consumption_records,
    )
    from current_model.ui_sandbox.Currentsituation_sandbox.engine.dso_accounting import (
        calculate_dso_accounting_2025,
    )
    from current_model.ui_sandbox.Currentsituation_sandbox.contract.charts import (
        create_dso_monthly_peak_figure,
    )


def _render_sub_ledger_html(
    header_title: str,
    rows: List[Dict[str, str]],
    subtotal_label: str,
    subtotal_monthly_eur: float,
    subtotal_annual_eur: float,
    accent_color: str = "#f59e0b",
    currency_code: str = "EUR",
    is_enabled: bool = True,
) -> str:
    """Renders a clean, zero-indentation HTML sub-ledger table for Zone B with optional gray-out."""
    rows_html_list: List[str] = []
    for idx, r in enumerate(rows):
        bg = "#1e293b" if idx % 2 == 0 else "#0f172a"
        mo_val = "0.00" if not is_enabled else r["monthly"]
        ann_val = "0.00" if not is_enabled else r["annual"]
        calc_str = f"{r['calc']} [BYPASSED]" if not is_enabled else r["calc"]
        rows_html_list.append(
            f'<tr style="background-color: {bg}; border-bottom: 1px solid #334155;">'
            f'<td style="padding: 8px 10px; color: #f1f5f9; font-size: 0.85rem; font-weight: 500;">{r["item"]}</td>'
            f'<td style="padding: 8px 10px; color: #cbd5e1; font-size: 0.82rem; font-family: monospace;">{calc_str}</td>'
            f'<td style="padding: 8px 10px; text-align: right; color: #e2e8f0; font-size: 0.85rem;">{currency_code} {mo_val}</td>'
            f'<td style="padding: 8px 10px; text-align: right; color: #f8fafc; font-weight: 600; font-size: 0.86rem;">{currency_code} {ann_val}</td>'
            f'</tr>'
        )
    body_rows = "\n".join(rows_html_list)
    sub_mo = 0.0 if not is_enabled else subtotal_monthly_eur
    sub_ann = 0.0 if not is_enabled else subtotal_annual_eur
    wrapper_style = (
        "border-radius: 8px; border: 1px solid #334155; overflow: hidden; margin-bottom: 12px;"
        if is_enabled
        else "border-radius: 8px; border: 1px dashed #475569; overflow: hidden; margin-bottom: 12px; opacity: 0.45; filter: grayscale(100%);"
    )
    status_badge = "" if is_enabled else " — [BYPASSED / GRAYED OUT: 0.00]"

    return (
        f'<div style="{wrapper_style}">\n'
        f'<div style="background-color: #0f172a; padding: 10px 14px; border-bottom: 2px solid {accent_color}; font-weight: 700; color: #f8fafc; font-size: 0.92rem;">'
        f'{header_title}{status_badge}'
        f'</div>\n'
        f'<table style="width: 100%; border-collapse: collapse; font-family: -apple-system, BlinkMacSystemFont, sans-serif;">\n'
        f'<thead>\n'
        f'<tr style="background-color: #090d16; border-bottom: 1px solid #475569; color: #94a3b8; font-size: 0.76rem; text-transform: uppercase; letter-spacing: 0.04em;">'
        f'<th style="padding: 8px 10px; text-align: left; width: 34%;">Line Item</th>'
        f'<th style="padding: 8px 10px; text-align: left; width: 34%;">Calculation (Quantity &times; Rate)</th>'
        f'<th style="padding: 8px 10px; text-align: right; width: 16%;">Monthly ({currency_code})</th>'
        f'<th style="padding: 8px 10px; text-align: right; width: 16%;">Annual ({currency_code})</th>'
        f'</tr>\n'
        f'</thead>\n'
        f'<tbody>\n'
        f'{body_rows}\n'
        f'<tr style="background-color: #0b1329; border-top: 2px solid {accent_color}; font-weight: 700;">'
        f'<td colspan="2" style="padding: 10px 10px; text-align: right; color: {accent_color}; font-size: 0.86rem; text-transform: uppercase;">{subtotal_label}</td>'
        f'<td style="padding: 10px 10px; text-align: right; color: {accent_color}; font-size: 0.90rem;">{currency_code} {sub_mo:,.2f}</td>'
        f'<td style="padding: 10px 10px; text-align: right; color: #ffffff; font-size: 0.96rem;">{currency_code} {sub_ann:,.2f}</td>'
        f'</tr>\n'
        f'</tbody>\n'
        f'</table>\n'
        f'</div>'
    )


def render_dso_tab(
    load_series: LoadSeries2025,
    key_prefix: str = "currsit_contract",
    is_enabled: bool = True,
    currency_code: str = "EUR",
) -> DSOTariff:
    """
    Renders Sub-Tab 1: Pillar 2 - Grid Network (DSO) using the standardized 3-Zone layout
    and returns the configured DSOTariff model.
    """
    status_tag = "" if is_enabled else " `[BYPASSED / GRAYED OUT]`"
    st.markdown(f"#### :material/grid_view: Pillar 2: Grid Network (DSO) — Regulated Connection, Capacity & Transport{status_tag}")

    if not is_enabled:
        st.info(
            ":material/visibility_off: **Pillar 2 (Grid Network DSO) is currently Bypassed / Grayed Out** under the active Custom Market Structure. "
            "All inputs below are shown in read-only grayed-out state so the tab structure remains visible, and Pillar 2 evaluates to **0.00** in the master bill.",
            icon=":material/info:"
        )

    col_zone_a, col_zone_b = st.columns([0.58, 0.42], gap="large")

    with col_zone_a:
        st.markdown("##### :material/tune: 1. Contract & Tariff Inputs")

        col_dso_co, col_dso_tier = st.columns([1.4, 2.2])
        with col_dso_co:
            dso_company_options = list(DSO_CATALOGS_2025.keys()) + ["Custom Grid Operator"]
            default_co_idx = 0
            preset_co = st.session_state.get(f"{key_prefix}_dso_company")
            if preset_co in dso_company_options:
                default_co_idx = dso_company_options.index(preset_co)
            selected_dso_company = st.selectbox(
                "Regulated Grid Operator / Utility (DSO):",
                options=dso_company_options,
                index=default_co_idx,
                key=f"{key_prefix}_dso_company",
                disabled=not is_enabled,
            )

        with col_dso_tier:
            if selected_dso_company in DSO_CATALOGS_2025:
                tier_dict = DSO_CATALOGS_2025[selected_dso_company]
                tier_options = list(tier_dict.keys())
                default_tier_idx = 0
                for idx, t_name in enumerate(tier_options):
                    if "MS-D" in t_name or ("MS" in t_name and "LS" not in t_name) or "T2 RMT" in t_name:
                        default_tier_idx = idx
                        break
                selected_tier = st.selectbox(
                    "Voltage Tier & Connection Category:",
                    options=tier_options,
                    index=default_tier_idx,
                    key=f"{key_prefix}_dso_tier",
                    disabled=not is_enabled,
                )
                preset_data = tier_dict[selected_tier]
                st.caption(f":material/info: *{preset_data.get('description', '')}*")
            else:
                selected_tier = "Custom Tier"
                preset_data = {
                    "aansluitdienst_annual": 1013.88,
                    "vastrecht_annual": 441.00,
                    "rate_contracted_monthly": 2.4400,
                    "rate_peak_monthly": 3.7100,
                    "rate_peak_kwh": 0.0250,
                    "rate_offpeak_kwh": 0.0250,
                    "reactive_tariff": 0.0188,
                }
                st.caption(":material/tune: *Custom manual grid operator tariff schedule.*")

        state_always_reload_key = f"{key_prefix}_dso_always_reload_{selected_dso_company}_{selected_tier}"
        always_reload = st.session_state.get(state_always_reload_key, False)

        reload_version_key = f"{key_prefix}_dso_version_{selected_dso_company}_{selected_tier}"
        form_version = st.session_state.get(reload_version_key, 0)

        r_col1, r_col2 = st.columns([1.8, 2.2])
        with r_col1:
            if st.button(
                ":material/restart_alt: Reload Catalog Defaults",
                key=f"{key_prefix}_btn_reload_preset_{selected_dso_company}_{selected_tier}",
                use_container_width=True,
                disabled=not is_enabled,
                help="Reset all input rates and TOU windows for this voltage tier back to official catalog defaults."
            ):
                st.session_state[reload_version_key] = form_version + 1
                for k in list(st.session_state.keys()):
                    if f"{selected_dso_company}_{selected_tier}" in k or "dso_base_fee" in k or "dso_conn_fee" in k or "dso_p_contract" in k or "dso_rate_" in k:
                        del st.session_state[k]
                st.rerun()

        with r_col2:
            always_reload = st.checkbox(
                "Always reload catalog defaults on tier switch",
                value=always_reload,
                key=state_always_reload_key,
                disabled=not is_enabled,
            )

        state_dso_tou_key = f"{key_prefix}_dso_tou_df_{selected_dso_company}_{selected_tier}_v{form_version}"
        is_preset_3win = bool(preset_data.get("enable_three_window_tou", False))
        if state_dso_tou_key not in st.session_state or always_reload:
            default_peak = float(preset_data.get("rate_peak_kwh", 0.0250))
            default_offpeak = float(preset_data.get("rate_offpeak_kwh", 0.0250))
            if is_preset_3win:
                default_shoulder = float(preset_data.get("rate_shoulder_kwh", default_peak))
                st.session_state[state_dso_tou_key] = pd.DataFrame([
                    {"name": "Peak / Pico (18:00–23:00)", "rate": default_peak, "start_time": "18:00", "end_time": "23:00"},
                    {"name": "Off-Peak / Valle (23:00–05:00)", "rate": default_offpeak, "start_time": "23:00", "end_time": "05:00"},
                    {"name": "Shoulder / Resto (05:00–18:00)", "rate": default_shoulder, "start_time": "05:00", "end_time": "18:00"},
                ])
            else:
                st.session_state[state_dso_tou_key] = pd.DataFrame([
                    {"name": "Peak Hours (HT)", "rate": default_peak, "start_time": "07:00", "end_time": "23:00"},
                    {"name": "Off-Peak Hours (NT)", "rate": default_offpeak, "start_time": "23:00", "end_time": "07:00"},
                ])

        with st.form(key=f"{key_prefix}_dso_contract_form_{selected_dso_company}_{selected_tier}_v{form_version}"):
            st.markdown("###### A. Fixed Standing Charges & Capacity Rates")

            conn_annual_default = float(preset_data.get("aansluitdienst_annual", 1013.88))
            conn_monthly_default = round(conn_annual_default / 12.0, 2)
            trans_annual_default = float(preset_data.get("vastrecht_annual", 441.00))
            trans_monthly_default = round(trans_annual_default / 12.0, 2)
            default_contract_kw = float(preset_data.get("typical_contracted_kw", max(50.0, round(load_series.peak_demand_kw * 1.05, 0))))
            if "preset_contracted_kw" in st.session_state:
                default_contract_kw = float(st.session_state["preset_contracted_kw"])

            c1, c2 = st.columns(2)
            with c1:
                conn_monthly_fee = st.number_input(
                    f"Fixed Connection Fee ({currency_code}/month):",
                    min_value=0.0,
                    value=conn_monthly_default,
                    step=5.0,
                    format="%.2f",
                    key=f"{key_prefix}_dso_conn_fee_{selected_dso_company}_{selected_tier}_v{form_version}",
                    help=f"Monthly periodic connection maintenance fee ({currency_code}/month)",
                    disabled=not is_enabled,
                )
                trans_monthly_fee = st.number_input(
                    f"Fixed Transport / Standing Fee ({currency_code}/month):",
                    min_value=0.0,
                    value=trans_monthly_default,
                    step=5.0,
                    format="%.2f",
                    key=f"{key_prefix}_dso_base_fee_{selected_dso_company}_{selected_tier}_v{form_version}",
                    help=f"Monthly fixed transport or commercialization standing charge ({currency_code}/month)",
                    disabled=not is_enabled,
                )
                contracted_kw = st.number_input(
                    "Contracted Grid Capacity (kW):",
                    min_value=10.0,
                    max_value=20000.0,
                    value=default_contract_kw,
                    step=10.0,
                    format="%.1f",
                    key=f"{key_prefix}_dso_p_contract_{selected_dso_company}_{selected_tier}_v{form_version}",
                    help="Reserved active power capacity contracted with the grid operator (kW)",
                    disabled=not is_enabled,
                )

            with c2:
                capacity_tariff = st.number_input(
                    f"Contracted Capacity Rate ({currency_code}/kW/month):",
                    min_value=0.0,
                    value=float(preset_data.get("rate_contracted_monthly", 2.4400)),
                    step=0.01,
                    format="%.4f",
                    key=f"{key_prefix}_dso_rate_cap_{selected_dso_company}_{selected_tier}_v{form_version}",
                    help=f"Monthly fee per kW of contracted grid capacity ({currency_code}/kW/month)",
                    disabled=not is_enabled,
                )
                demand_tariff = st.number_input(
                    f"Measured Monthly Peak Rate ({currency_code}/kW/month):",
                    min_value=0.0,
                    value=float(preset_data.get("rate_peak_monthly", 3.7100)),
                    step=0.01,
                    format="%.4f",
                    key=f"{key_prefix}_dso_rate_peak_{selected_dso_company}_{selected_tier}_v{form_version}",
                    help=f"Monthly fee billed per highest 15-minute peak demand recorded in that month ({currency_code}/kW/month)",
                    disabled=not is_enabled,
                )
                max_physical_kw = st.number_input(
                    "Physical Transformer Limit (kW):",
                    min_value=10.0,
                    value=float(preset_data.get("max_physical_limit_kw", 1000.0)),
                    step=50.0,
                    format="%.1f",
                    key=f"{key_prefix}_dso_max_phys_{selected_dso_company}_{selected_tier}_v{form_version}",
                    disabled=not is_enabled,
                )

            st.markdown(f"###### B. Volumetric Network Transport / Bundled Energy Rates ({currency_code}/kWh)")
            edited_dso_tou = st.data_editor(
                st.session_state[state_dso_tou_key],
                num_rows="dynamic",
                use_container_width=True,
                disabled=not is_enabled,
                column_config={
                    "name": st.column_config.TextColumn("Tariff Window", required=True),
                    "rate": st.column_config.NumberColumn(
                        f"Transport / Utility Rate ({currency_code}/kWh)",
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

            default_enable_excess = bool(preset_data.get("enable_excess_capacity_penalty", False))
            default_pico_only = bool(preset_data.get("bill_peak_demand_on_peak_tou_only", False))
            default_reg_adj = float(preset_data.get("regulatory_adjustments_monthly", 0.0))
            with st.expander(":material/settings: Reactive Power, Pass-Through Adjustments & Capacity Breach Rules", expanded=default_enable_excess):
                q1, q2, q3 = st.columns(3)
                with q1:
                    reactive_tariff = st.number_input(
                        f"Reactive Power Rate ({currency_code}/kVARh):",
                        min_value=0.0,
                        value=float(preset_data.get("reactive_tariff", 0.0188)),
                        step=0.005,
                        format="%.4f",
                        key=f"{key_prefix}_dso_reactive_{selected_dso_company}_{selected_tier}_v{form_version}",
                        disabled=not is_enabled,
                    )
                with q2:
                    min_cos_phi = st.number_input(
                        "Target Power Factor (cos phi):",
                        min_value=0.50,
                        max_value=1.00,
                        value=float(preset_data.get("min_power_factor", 0.90)),
                        step=0.02,
                        format="%.2f",
                        key=f"{key_prefix}_dso_cosphi_{selected_dso_company}_{selected_tier}_v{form_version}",
                        disabled=not is_enabled,
                    )
                with q3:
                    penalty_rate = st.number_input(
                        f"Exceedance Penalty ({currency_code}/kW/mo):",
                        min_value=0.0,
                        value=float(preset_data.get("peak_penalty_rate_kw", 0.2500)),
                        step=0.05,
                        format="%.4f",
                        key=f"{key_prefix}_dso_penalty_{selected_dso_company}_{selected_tier}_v{form_version}",
                        disabled=not is_enabled,
                    )

                reg_adj_monthly = st.number_input(
                    f"Regulatory & Seasonal Pass-Through Adjustments ({currency_code}/month):",
                    value=default_reg_adj,
                    step=100.0,
                    format="%.2f",
                    key=f"{key_prefix}_dso_reg_adj_{selected_dso_company}_{selected_tier}_v{form_version}",
                    help=f"Monthly statutory pass-through adjustments (e.g., EDEMSA GUDI / seasonal stabilization net pass-through in {currency_code}/month)",
                    disabled=not is_enabled,
                )

                adjust_breach = st.checkbox(
                    "Adjust contracted capacity billing to measured peak during breach months (NL Rule)",
                    value=not default_enable_excess,
                    key=f"{key_prefix}_dso_adjust_breach_{selected_dso_company}_{selected_tier}",
                    disabled=not is_enabled,
                )
                enable_excess_penalty = st.checkbox(
                    "Bill explicit Excess Capacity Penalty (Exceso de Potencia = Excess kW × Penalty Rate)",
                    value=default_enable_excess,
                    key=f"{key_prefix}_dso_excess_pen_{selected_dso_company}_{selected_tier}",
                    disabled=not is_enabled,
                )
                bill_pico_only = st.checkbox(
                    "Bill Peak Demand Fee (Pos 2.3) strictly on Peak/Pico TOU window demand (EDEMSA T2 Rule)",
                    value=default_pico_only,
                    key=f"{key_prefix}_dso_pico_only_{selected_dso_company}_{selected_tier}",
                    disabled=not is_enabled,
                )

            submitted_dso = st.form_submit_button(
                "Apply Grid Network Tariff",
                icon=":material/save:",
                type="primary",
                use_container_width=True,
                disabled=not is_enabled,
            )

        if submitted_dso and is_enabled:
            if edited_dso_tou is not None and not edited_dso_tou.empty:
                st.session_state[state_dso_tou_key] = edited_dso_tou
            st.success(f"Grid Network tariff updated ({selected_dso_company} - {selected_tier})", icon=":material/check_circle:")

    # Extract active peak, offpeak, and optional shoulder transport rates
    active_tou_df = st.session_state[state_dso_tou_key]
    trans_norm_kwh = float(preset_data.get("rate_peak_kwh", 0.0250))
    trans_off_kwh = float(preset_data.get("rate_offpeak_kwh", 0.0250))
    trans_sh_kwh = float(preset_data.get("rate_shoulder_kwh", 0.0000))
    enable_3win = is_preset_3win
    if active_tou_df is not None and not active_tou_df.empty:
        rows_tou = active_tou_df.to_dict(orient="records")
        if len(rows_tou) >= 3:
            enable_3win = True
        for r in rows_tou:
            r_name = str(r.get("name", "")).lower()
            r_rate = float(r.get("rate", trans_norm_kwh))
            if any(k in r_name for k in ["shoulder", "resto", "mid"]):
                trans_sh_kwh = r_rate
                enable_3win = True
            elif any(k in r_name for k in ["off", "nt", "low", "night", "weekend", "valle"]):
                trans_off_kwh = r_rate
            elif any(k in r_name for k in ["peak", "ht", "high", "day", "work", "pico"]):
                trans_norm_kwh = r_rate

    dso_tariff = DSOTariff(
        dso_name=selected_dso_company,
        grid_tier=selected_tier,
        connection_category="standard",
        fixed_connection_annual=round(conn_monthly_fee * 12.0, 2),
        fixed_transport_annual=round(trans_monthly_fee * 12.0, 2),
        cable_surcharge_annual=0.0,
        contracted_capacity_kw=contracted_kw,
        rate_contracted_capacity=capacity_tariff,
        rate_peak_demand=demand_tariff,
        rate_transport_peak_kwh=trans_norm_kwh,
        rate_transport_offpeak_kwh=trans_off_kwh,
        rate_transport_shoulder_kwh=trans_sh_kwh,
        enable_three_window_tou=enable_3win,
        adjust_capacity_on_breach=adjust_breach,
        max_physical_limit_kw=max_physical_kw,
        peak_penalty_rate_kw=penalty_rate,
        reactive_power_tariff=reactive_tariff,
        min_power_factor=min_cos_phi,
        reactive_allowance_pct=33.0,
        enable_excess_capacity_penalty=enable_excess_penalty,
        bill_peak_demand_on_peak_tou_only=bill_pico_only,
        regulatory_adjustments_monthly=reg_adj_monthly,
    )

    # Compute DSO accounting for Zone B and Zone C
    monthly_cons = extract_monthly_consumption_records(load_series)
    dso_monthly_results, dso_summary = calculate_dso_accounting_2025(
        load=load_series,
        monthly_consumption=monthly_cons,
        dso_tariff=dso_tariff
    )

    # ----------------------------------------------------------------------------------
    # Zone B (Right Column, 42%): 2. Component Bill Calculation (How it Adds Up)
    # ----------------------------------------------------------------------------------
    with col_zone_b:
        st.markdown("##### :material/receipt_long: 2. Component Bill Calculation (How it Adds Up)")

        conn_ann = dso_summary["total_fixed_connection_annual"]
        trans_ann = dso_summary["total_fixed_transport_annual"]
        standing_ann = round(conn_ann + trans_ann, 2)
        standing_mo = round(standing_ann / 12.0, 2)

        cap_ann = dso_summary["total_capacity_fee_annual"]
        cap_mo = round(cap_ann / 12.0, 2)
        avg_billed_kw = sum(r.billed_capacity_kw for r in dso_monthly_results) / 12.0

        peak_ann = dso_summary["total_peak_demand_fee_annual"]
        peak_mo = round(peak_ann / 12.0, 2)
        avg_peak_kw = sum(getattr(r, "billed_peak_demand_kw", r.measured_peak_demand_kw) for r in dso_monthly_results) / 12.0

        excess_pen_ann = dso_summary.get("total_excess_penalty_annual", 0.0)
        excess_pen_mo = round(excess_pen_ann / 12.0, 2)
        avg_excess_kw = sum(r.excess_capacity_kw for r in dso_monthly_results) / 12.0

        reg_adj_ann = dso_summary.get("total_regulatory_adjustments_annual", 0.0)
        reg_adj_mo = round(reg_adj_ann / 12.0, 2)

        tot_ht_kwh = sum(c.peak_tou_kwh for c in monthly_cons)
        tot_nt_kwh = sum(c.offpeak_tou_kwh for c in monthly_cons)
        tot_sh_kwh = sum(getattr(c, "shoulder_tou_kwh", 0.0) for c in monthly_cons)
        vol_ht_ann = dso_summary.get("total_volumetric_peak_annual", round(tot_ht_kwh * trans_norm_kwh, 2))
        vol_nt_ann = dso_summary.get("total_volumetric_offpeak_annual", round(tot_nt_kwh * trans_off_kwh, 2))
        vol_sh_ann = dso_summary.get("total_volumetric_shoulder_annual", round(tot_sh_kwh * trans_sh_kwh, 2))

        subtotal_dso_ann = dso_summary["total_dso_net_annual"]
        subtotal_dso_mo = round(subtotal_dso_ann / 12.0, 2)

        peak_desc_lbl = "2.3 Measured Monthly Peak Demand (Pico)" if bill_pico_only else "2.3 Measured Monthly Peak Demand"
        ledger_rows = [
            {
                "item": "2.1 Fixed Standing Fee (Connection + Transport)",
                "calc": f"12 mos × {currency_code} {standing_mo:,.2f}/mo",
                "monthly": f"{standing_mo:,.2f}",
                "annual": f"{standing_ann:,.2f}",
            },
            {
                "item": "2.2 Contracted Grid Capacity",
                "calc": f"{avg_billed_kw:,.1f} kW × 12 mos × {currency_code} {capacity_tariff:.4f}/kW/mo",
                "monthly": f"{cap_mo:,.2f}",
                "annual": f"{cap_ann:,.2f}",
            },
            {
                "item": peak_desc_lbl,
                "calc": f"Avg {avg_peak_kw:,.1f} kW/mo × 12 mos × {currency_code} {demand_tariff:.4f}/kW/mo",
                "monthly": f"{peak_mo:,.2f}",
                "annual": f"{peak_ann:,.2f}",
            },
        ]

        if enable_3win or tot_sh_kwh > 0.0:
            ledger_rows.extend([
                {
                    "item": "2.4a Active Energy — Peak / Pico (18:00–23:00)",
                    "calc": f"{tot_ht_kwh:,.0f} kWh × {currency_code} {trans_norm_kwh:.6f}/kWh",
                    "monthly": f"{vol_ht_ann / 12.0:,.2f}",
                    "annual": f"{vol_ht_ann:,.2f}",
                },
                {
                    "item": "2.4b Active Energy — Off-Peak / Valle (23:00–05:00)",
                    "calc": f"{tot_nt_kwh:,.0f} kWh × {currency_code} {trans_off_kwh:.6f}/kWh",
                    "monthly": f"{vol_nt_ann / 12.0:,.2f}",
                    "annual": f"{vol_nt_ann:,.2f}",
                },
                {
                    "item": "2.4c Active Energy — Shoulder / Resto (05:00–18:00)",
                    "calc": f"{tot_sh_kwh:,.0f} kWh × {currency_code} {trans_sh_kwh:.6f}/kWh",
                    "monthly": f"{vol_sh_ann / 12.0:,.2f}",
                    "annual": f"{vol_sh_ann:,.2f}",
                },
            ])
        else:
            ledger_rows.extend([
                {
                    "item": "2.4 Volumetric Transport — Peak Hours (HT)",
                    "calc": f"{tot_ht_kwh:,.0f} kWh × {currency_code} {trans_norm_kwh:.4f}/kWh",
                    "monthly": f"{vol_ht_ann / 12.0:,.2f}",
                    "annual": f"{vol_ht_ann:,.2f}",
                },
                {
                    "item": "2.5 Volumetric Transport — Off-Peak Hours (NT)",
                    "calc": f"{tot_nt_kwh:,.0f} kWh × {currency_code} {trans_off_kwh:.4f}/kWh",
                    "monthly": f"{vol_nt_ann / 12.0:,.2f}",
                    "annual": f"{vol_nt_ann:,.2f}",
                },
            ])

        if enable_excess_penalty or excess_pen_ann > 0.0:
            ledger_rows.append({
                "item": "2.6 Excess Capacity Penalty (Exceso de Potencia)",
                "calc": f"Avg {avg_excess_kw:,.1f} kW × 12 mos × {currency_code} {penalty_rate:.4f}/kW/mo",
                "monthly": f"{excess_pen_mo:,.2f}",
                "annual": f"{excess_pen_ann:,.2f}",
            })

        if abs(reg_adj_ann) > 0.005:
            ledger_rows.append({
                "item": "2.7 Regulatory & Seasonal Pass-Through Adjustments",
                "calc": f"12 mos × {currency_code} {reg_adj_mo:,.2f}/mo",
                "monthly": f"{reg_adj_mo:,.2f}",
                "annual": f"{reg_adj_ann:,.2f}",
            })

        st.markdown(
            _render_sub_ledger_html(
                header_title=f"Pillar 2 Sub-Ledger — {selected_dso_company} ({selected_tier})",
                rows=ledger_rows,
                subtotal_label="= SUBTOTAL GRID NETWORK (NET)",
                subtotal_monthly_eur=subtotal_dso_mo,
                subtotal_annual_eur=subtotal_dso_ann,
                accent_color="#f59e0b",
                currency_code=currency_code,
                is_enabled=is_enabled,
            ),
            unsafe_allow_html=True
        )

        eff_dso_kwh = (0.0 if not is_enabled else subtotal_dso_ann) / max(1.0, load_series.total_energy_kwh)
        if dso_summary["has_breaches"]:
            st.warning(
                f":material/warning: **Capacity Breach Detected:** Measured peak exceeded contracted capacity "
                f"({contracted_kw:,.1f} kW) in {dso_summary['breached_months_count']} month(s): {dso_summary['breached_months']}.",
                icon=":material/warning:"
            )
        else:
            st.success(
                f":material/verified: **Capacity Compliance:** All 12 monthly peaks within {contracted_kw:,.1f} kW limit "
                f"(Max recorded: {load_series.peak_demand_kw:,.1f} kW | Effective Grid Rate: {currency_code} {eff_dso_kwh:.4f}/kWh).",
                icon=":material/check_circle:"
            )

    # ----------------------------------------------------------------------------------
    # Zone C (Bottom Full Width): 3. Monthly Breakdown & Visual Diagnostics
    # ----------------------------------------------------------------------------------
    st.markdown("---")
    with st.expander(":material/analytics: 3. Monthly Breakdown & Visual Diagnostics (Grid Network DSO)", expanded=is_enabled):
        col_c_chart, col_c_table = st.columns([1.1, 1.2], gap="large")
        with col_c_chart:
            fig_peak = create_dso_monthly_peak_figure(
                dso_monthly_results=dso_monthly_results,
                contracted_capacity_kw=contracted_kw
            )
            st.plotly_chart(fig_peak, use_container_width=True, key=f"{key_prefix}_dso_zone_c_peak_chart")

        with col_c_table:
            st.markdown("###### 12-Month Grid Network (DSO) Statement")
            month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
            dso_rows = []
            for r in dso_monthly_results:
                m_label = month_names[r.month_index - 1]
                mult = 1.0 if is_enabled else 0.0
                row_dict: Dict[str, Any] = {
                    "Month": m_label,
                    "Measured Peak (kW)": f"{r.measured_peak_demand_kw:,.1f}",
                    "Billed Cap (kW)": f"{r.billed_capacity_kw:,.1f}",
                    f"Standing ({currency_code})": f"{(r.fixed_connection_fee + r.fixed_transport_fee) * mult:,.2f}",
                    f"Capacity ({currency_code})": f"{r.contracted_capacity_fee * mult:,.2f}",
                    f"Peak Fee ({currency_code})": f"{r.peak_demand_fee * mult:,.2f}",
                    f"Transport ({currency_code})": f"{r.volumetric_transport_fee * mult:,.2f}",
                }
                if enable_excess_penalty or excess_pen_ann > 0.0:
                    row_dict[f"Excess Penalty ({currency_code})"] = f"{r.excess_capacity_kw * penalty_rate * mult:,.2f}"
                row_dict[f"Subtotal Net ({currency_code})"] = f"{r.subtotal_dso_net * mult:,.2f}"
                dso_rows.append(row_dict)
            st.dataframe(pd.DataFrame(dso_rows), use_container_width=True, hide_index=True)

    return dso_tariff
