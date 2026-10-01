"""
========================================================================================
Minimal Electricity Contract & Consumption System (ui_sandbox/minimal_contract_system.py)
========================================================================================

Description:
------------
Streamlined Sandbox environment with the exact layout of the main application,
using clear, simplified terminology (e.g. 'Fee per Reserved Power' instead of
'Contracted Capacity Tariff / Uso de Red', 'Reserved Power Limit' instead of
'Contracted Active Capacity / Potencia Contratada').
========================================================================================
"""

import io
import os
import sys
import re
import zipfile
from typing import Dict, Any, List, Optional, Tuple
import streamlit as st
import pandas as pd
import numpy as np

# Ensure project root and current_model are on sys.path
SANDBOX_DIR = os.path.dirname(os.path.abspath(__file__))
CURRENT_MODEL_DIR = os.path.abspath(os.path.join(SANDBOX_DIR, ".."))
WORKSPACE_ROOT = os.path.abspath(os.path.join(CURRENT_MODEL_DIR, ".."))

for path in [WORKSPACE_ROOT, CURRENT_MODEL_DIR]:
    if path not in sys.path:
        sys.path.insert(0, path)

from current_model.models.contract import Contract, get_contract_presets
from current_model.models.financial import FinancialCostBreakdown
from current_model.core.financial_engine import compute_financial_bill, _resolve_contract_for_month
from current_model.ui.common.styles import apply_custom_styles
from current_model.ui.common.cards import render_kpi_card
from current_model.ui.tab1_consumption.csv_inspector.view import render_csv_inspector
from current_model.ui.tab2_contract.charts import create_cost_donut_figure, create_monthly_payment_series_figure
from current_model.ui.tab2_contract.form import (
    _sanitize_rate_val,
    _sanitize_tax_val,
    _sanitize_filename,
    _parse_uploaded_contract_files,
    _sync_contract_to_state
)


def render_simplified_contract_form(key_prefix: str = "sandbox_contract") -> Contract:
    """
    Renders the Electricity Supply Contract form with the exact layout of the main app,
    using clean and simplified terminology.
    """
    state_contract_key = f"{key_prefix}_contract_model"
    state_tou_key = f"{key_prefix}_tou_rates_df"
    state_taxes_key = f"{key_prefix}_taxes_df"
    loaded_contracts_dict_key = f"{key_prefix}_loaded_contracts_dict"
    uploader_sig_key = f"{key_prefix}_last_files_sig"

    if state_contract_key not in st.session_state:
        st.session_state[state_contract_key] = Contract()

    current: Contract = st.session_state[state_contract_key]

    if not hasattr(current, "name") or not current.name:
        current.name = "Electricity Contract"
    if not hasattr(current, "tou_rates") or current.tou_rates is None:
        current.tou_rates = [{"name": "Standard Rate", "rate": float(getattr(current, "default_energy_rate", 0.20)), "start_time": "00:00", "end_time": "24:00"}]
    if not hasattr(current, "taxes_and_fees") or current.taxes_and_fees is None:
        current.taxes_and_fees = []

    if state_tou_key not in st.session_state:
        st.session_state[state_tou_key] = pd.DataFrame(current.tou_rates)

    if state_taxes_key not in st.session_state:
        st.session_state[state_taxes_key] = pd.DataFrame(current.taxes_and_fees) if current.taxes_and_fees else pd.DataFrame(columns=["name", "type", "value", "description"])

    with st.container():
        # ==============================================================================
        # Toolbar: Import & Export Contracts / Presets
        # ==============================================================================
        st.markdown("### Contract File Transfer & Presets (.drac)")
        st.caption("Download your configured contract as a reusable `.drac` file or upload saved contract files.")

        col_up, col_down = st.columns([1, 1])

        # --- LEFT: Upload / Import / Presets ---
        with col_up:
            st.markdown("##### Import Contract(s)")
            uploaded_files = st.file_uploader(
                "Select `.drac`, `.json` or `.zip` contract file(s):",
                type=["drac", "json", "zip"],
                accept_multiple_files=True,
                key=f"{key_prefix}_file_uploader"
            )

            if loaded_contracts_dict_key not in st.session_state:
                st.session_state[loaded_contracts_dict_key] = {}

            if uploaded_files:
                current_sig = "|".join(sorted([f"{f.name}_{f.size}" for f in uploaded_files]))
                if st.session_state.get(uploader_sig_key) != current_sig:
                    new_contracts = _parse_uploaded_contract_files(uploaded_files)
                    if new_contracts:
                        st.session_state[loaded_contracts_dict_key] = new_contracts
                        st.session_state[uploader_sig_key] = current_sig
                        first_label = list(new_contracts.keys())[0]
                        _sync_contract_to_state(new_contracts[first_label], key_prefix=key_prefix)
                        st.success(f"Successfully loaded **{len(new_contracts)}** contract(s)!")
                        st.rerun()

            loaded_dict = st.session_state.get(loaded_contracts_dict_key, {})
            if current.name not in loaded_dict:
                loaded_dict[current.name] = current
                st.session_state[loaded_contracts_dict_key] = loaded_dict

            labels = list(loaded_dict.keys())
            current_sel = st.session_state.get(f"{key_prefix}_active_contract_label", labels[0])
            if current_sel not in labels:
                current_sel = labels[0]
                st.session_state[f"{key_prefix}_active_contract_label"] = current_sel
            sel_idx = labels.index(current_sel)

            selected_label = st.selectbox(
                "Active Contract Selection:",
                options=labels,
                index=sel_idx,
                key=f"{key_prefix}_sel_box"
            )
            if selected_label != current_sel and selected_label in loaded_dict:
                _sync_contract_to_state(loaded_dict[selected_label], key_prefix=key_prefix)
                st.rerun()

            col_dup, col_del = st.columns([1, 1])
            with col_dup:
                if st.button("Duplicate for Months", icon=":material/content_copy:", key=f"{key_prefix}_dup_btn", use_container_width=True):
                    clone_num = len(loaded_dict) + 1
                    clone_name = f"{current.name} (Variant {clone_num})"
                    cloned_c = Contract.from_dict(current.to_dict()) if hasattr(current, "to_dict") else Contract.from_json(current.to_json())
                    cloned_c.name = clone_name
                    loaded_dict[clone_name] = cloned_c
                    st.session_state[loaded_contracts_dict_key] = loaded_dict
                    _sync_contract_to_state(cloned_c, key_prefix=key_prefix)
                    st.success(f"Duplicated contract as '{clone_name}'. You can now customize rates and select applicable months.")
                    st.rerun()

            with col_del:
                if len(loaded_dict) > 1:
                    if st.button("Delete Contract", icon=":material/delete:", key=f"{key_prefix}_del_btn", use_container_width=True):
                        if current.name in loaded_dict:
                            del loaded_dict[current.name]
                            st.session_state[loaded_contracts_dict_key] = loaded_dict
                            remaining_first = list(loaded_dict.values())[0]
                            _sync_contract_to_state(remaining_first, key_prefix=key_prefix)
                            st.warning(f"Deleted contract '{current.name}'.")
                            st.rerun()

            presets = get_contract_presets()
            selected_preset_name = st.selectbox(
                "Or load an industry contract preset:",
                options=["-- Select a Template --"] + list(presets.keys()),
                index=0,
                key=f"{key_prefix}_preset_select"
            )
            if selected_preset_name in presets:
                if st.button("Apply Preset", icon=":material/playlist_add_check:", key=f"{key_prefix}_apply_preset_btn", use_container_width=True):
                    preset_c = presets[selected_preset_name]
                    preset_copy = Contract.from_dict(preset_c.to_dict()) if hasattr(preset_c, "to_dict") else Contract.from_json(preset_c.to_json())
                    loaded_dict[preset_copy.name] = preset_copy
                    st.session_state[loaded_contracts_dict_key] = loaded_dict
                    _sync_contract_to_state(preset_copy, key_prefix=key_prefix)
                    st.success(f"Loaded preset: {selected_preset_name}")
                    st.rerun()

        # --- RIGHT: Download / Export as .drac ---
        with col_down:
            st.markdown("##### Export Contract")
            default_file_base = re.sub(r'[^a-zA-Z0-9_-]', '_', current.name.lower().strip()) or "electricity_contract"
            custom_download_filename = st.text_input(
                "Individual Download Filename (.drac):",
                value=f"{default_file_base}.drac",
                key=f"{key_prefix}_custom_filename_input"
            )
            final_filename = _sanitize_filename(custom_download_filename, default=f"{default_file_base}.drac")

            contract_json_data = current.to_json(indent=2) if hasattr(current, "to_json") else Contract.from_dict(getattr(current, "__dict__", {})).to_json(indent=2)
            st.download_button(
                label=f"Download Contract as `{final_filename}`",
                data=contract_json_data,
                file_name=final_filename,
                mime="application/json",
                icon=":material/download:",
                key=f"{key_prefix}_download_btn",
                type="secondary",
                use_container_width=True
            )
            st.caption(f"Ready for export: **{current.name}** ({current.currency}, {current.contracted_capacity_kw:.0f} kW)")

        st.divider()

        # ==============================================================================
        # 12-Month Contract Coverage Matrix
        # ==============================================================================
        st.markdown("##### :material/calendar_month: 12-Month Contract Assignment Overview")
        st.caption("Visual matrix showing which contract governs each calendar month. Highlighted cards indicate months assigned to the currently edited contract.")
        month_abbr_list = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        mat_cols = st.columns(12)
        for m_idx, abbr in enumerate(month_abbr_list, start=1):
            assigned_c = _resolve_contract_for_month(list(loaded_dict.values()), m_idx, default_contract=current)
            is_active_for_curr = (assigned_c.name == current.name)
            with mat_cols[m_idx - 1]:
                st.markdown(
                    f"""
                    <div style="
                        border: 1px solid {'#3b82f6' if is_active_for_curr else '#374151'};
                        border-radius: 6px;
                        padding: 6px 2px;
                        text-align: center;
                        background-color: {'rgba(59, 130, 246, 0.20)' if is_active_for_curr else 'rgba(31, 41, 55, 0.45)'};
                        margin-bottom: 6px;
                    ">
                        <div style="font-weight: 700; font-size: 0.8rem; color: {'#93c5fd' if is_active_for_curr else '#e5e7eb'};">{abbr}</div>
                        <div style="color: {'#bfdbfe' if is_active_for_curr else '#9ca3af'}; font-size: 0.68rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="{assigned_c.name}">
                            {assigned_c.name[:10]}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

        st.divider()

        # ==============================================================================
        # Contract Parameter Configuration Form (Exact layout with simplified terms)
        # ==============================================================================
        with st.form(key=f"{key_prefix}_contract_form"):
            st.subheader("1. General & Active Capacity Parameters")

            contract_name_val = st.text_input(
                "Contract Name / Identifier:",
                value=str(current.name),
                help="Custom name or identifier for this contract."
            )

            c1, c2 = st.columns(2)
            with c1:
                curr_options = ["EUR", "USD", "ARS", "GBP", "CHF"]
                current_curr = getattr(current, "currency", "EUR")
                curr_idx = curr_options.index(current_curr) if current_curr in curr_options else 0
                currency = st.selectbox("Currency:", options=curr_options, index=curr_idx)
                base_fee = st.number_input("Base Monthly Fee (/month):", min_value=0.0, value=float(current.base_monthly_fee), step=5.0, format="%.2f", help="Fixed standing fee paid every month.")
                contracted_kw = st.number_input("Reserved Power Limit (kW):", min_value=0.0, value=float(current.contracted_capacity_kw), step=10.0, format="%.1f", help="Contracted grid capacity limit.")

            with c2:
                capacity_tariff = st.number_input("Fee per Reserved Power (/kW/month):", min_value=0.0, value=float(current.monthly_capacity_tariff), step=0.1, format="%.4f", help="Monthly fee charged per reserved kW.")
                demand_tariff = st.number_input("Fee for Highest Measured Peak (/kW/month):", min_value=0.0, value=float(getattr(current, "demand_capacity_tariff", 0.0)), step=0.1, format="%.4f", help="Monthly charge billed per highest measured peak kW.")
                max_physical_kw = st.number_input("Max Physical Limit (kW):", min_value=0.0, value=float(current.max_physical_limit_kw), step=50.0, format="%.1f", help="Physical transformer / fuse limit.")
                penalty_rate = st.number_input("Penalty Rate for Exceeding Limit (/kW):", min_value=0.0, value=float(current.peak_penalty_rate), step=1.0, format="%.4f", help="Penalty fee billed for kW exceeding the reserved power limit.")

            # 2. Applicable Validity Months
            st.subheader("2. Applicable Validity Months (Gültigkeitsmonate)")
            st.caption("Select the months where this contract configuration applies. By default, it applies to all 12 months:")

            all_month_abbrs = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
            curr_app_months = getattr(current, "applicable_months", list(range(1, 13))) or list(range(1, 13))
            curr_selected_abbrs = [all_month_abbrs[m - 1] for m in curr_app_months if 1 <= m <= 12]

            selected_months = st.multiselect(
                "Select Months Governed by this Contract:",
                options=all_month_abbrs,
                default=curr_selected_abbrs,
                help="By default, all months are selected. Uncheck months to restrict this contract to specific seasons or months.",
                key=f"{key_prefix}_months_multiselect"
            )
            parsed_app_months = [all_month_abbrs.index(m) + 1 for m in selected_months if m in all_month_abbrs]
            if not parsed_app_months:
                parsed_app_months = list(range(1, 13))

            st.subheader("3. Reactive Power Parameters")
            q1, q2, q3 = st.columns(3)
            with q1:
                reactive_tariff = st.number_input("Reactive Energy Fee (/kVARh):", min_value=0.0, value=float(current.reactive_power_tariff), step=0.005, format="%.4f")
            with q2:
                min_cos_phi = st.number_input("Min Power Factor (cos phi):", min_value=0.50, max_value=1.00, value=float(current.min_power_factor), step=0.02, format="%.2f")
            with q3:
                reactive_allowance = st.number_input("Free Reactive Allowance (% of kWh):", min_value=0.0, max_value=100.0, value=float(current.reactive_power_allowance_pct), step=1.0, format="%.1f")

            # 4. Electricity Energy Supply Pricing (Fixed TOU vs Dynamic Spot Market)
            st.subheader("4. Energy Supply Pricing Model")
            st.caption("Choose whether energy is billed via fixed Time-of-Use hourly windows or dynamically linked to wholesale Day-Ahead spot market prices:")

            pricing_options = [
                "Fixed Time-of-Use Tariffs",
                "Dynamic Spot Market (Day-Ahead NL 2025)"
            ]
            current_pricing_model = getattr(current, "pricing_model", "time_of_use")
            default_pricing_idx = 1 if current_pricing_model == "day_ahead_dynamic" else 0

            selected_pricing_mode = st.radio(
                "Supply Pricing Mode:",
                options=pricing_options,
                index=default_pricing_idx,
                horizontal=True,
                help="Select between fixed Time-of-Use rate windows or dynamic spot market wholesale hourly auction prices.",
                key=f"{key_prefix}_pricing_mode_radio"
            )
            is_dynamic_selected = (selected_pricing_mode == "Dynamic Spot Market (Day-Ahead NL 2025)")

            if is_dynamic_selected:
                st.markdown("##### :material/trending_up: Day-Ahead Spot Market Settings")
                dyn_c1, dyn_c2 = st.columns(2)
                with dyn_c1:
                    supplier_margin_val = st.number_input(
                        f"Supplier Margin / Opslag ({currency}/kWh):",
                        min_value=0.0,
                        value=float(getattr(current, "supplier_margin", 0.0075)),
                        step=0.0010,
                        format="%.4f",
                        help="Fixed supplier service fee added on top of the wholesale spot price (e.g. 0.0075 EUR/kWh)."
                    )
                    network_volume_tariff_val = st.number_input(
                        f"Grid Transport Volume Fee ({currency}/kWh):",
                        min_value=0.0,
                        value=float(getattr(current, "network_volume_tariff", 0.0250)),
                        step=0.0025,
                        format="%.4f",
                        help="Regulated grid operator transport fee charged per delivered kWh (e.g. Enexis MS-D: 0.0250 EUR/kWh)."
                    )
                with dyn_c2:
                    market_profile_val = st.selectbox(
                        "Wholesale Market Price Dataset:",
                        options=["epex_nl_2025"],
                        format_func=lambda x: "Netherlands Day-Ahead (EPEX Spot NL 2025)",
                        index=0,
                        help="Wholesale auction dataset used to price every interval."
                    )
                    default_rate_val = st.number_input(
                        f"Fallback Energy Rate ({currency}/kWh):",
                        min_value=0.0,
                        value=float(getattr(current, "default_energy_rate", 0.0900)),
                        step=0.0050,
                        format="%.4f",
                        help="Safety backup rate applied if a price timestamp is missing."
                    )

                try:
                    from current_model.core.market_price_engine import get_market_price_kpis
                    kpi_meta = get_market_price_kpis("epex_nl_2025")
                    st.info(
                        f":material/info: **Linked Wholesale Dataset:** EPEX Spot Netherlands 2025 | "
                        f"**Annual Mean Price:** {kpi_meta['mean_eur_kwh']:.4f} {currency}/kWh ({kpi_meta['mean_eur_mwh']:.2f} {currency}/MWh) | "
                        f"**Negative Price Hours:** {kpi_meta['negative_price_hours']:.0f} h | "
                        f"**Coverage:** {kpi_meta['total_hours']:.0f} hours (100% complete)"
                    )
                except Exception:
                    pass

                edited_tou = None
                weekend_off_peak = False
            else:
                edited_tou = st.data_editor(
                    st.session_state[state_tou_key],
                    num_rows="dynamic",
                    use_container_width=True,
                    column_config={
                        "name": st.column_config.TextColumn("Tariff Name", required=True),
                        "rate": st.column_config.NumberColumn(f"Rate ({currency}/kWh)", format="%.4f", min_value=0.0, step=0.0001, required=True),
                        "start_time": st.column_config.TextColumn("Start Time (HH:MM)", required=True),
                        "end_time": st.column_config.TextColumn("End Time (HH:MM)", required=True)
                    },
                    key=f"{key_prefix}_tou_editor"
                )

                col_w, col_net = st.columns(2)
                with col_w:
                    weekend_off_peak = st.checkbox(
                        "Treat Weekends as Off-Peak (Apply Lowest Tariff)",
                        value=bool(current.weekend_is_off_peak)
                    )
                with col_net:
                    network_volume_tariff_val = st.number_input(
                        f"Grid Transport Volume Fee ({currency}/kWh):",
                        min_value=0.0,
                        value=float(getattr(current, "network_volume_tariff", 0.0)),
                        step=0.0025,
                        format="%.4f",
                        help="Optional grid operator volume transport charge per delivered kWh (0 if already bundled)."
                    )
                supplier_margin_val = 0.0
                market_profile_val = getattr(current, "market_price_profile_id", "epex_nl_2025") or "epex_nl_2025"
                default_rate_val = float(getattr(current, "default_energy_rate", 0.20))

            # 5. Dynamic Taxes & Additional Fees Table
            st.subheader("5. Taxes & Additional Fees")
            st.caption("Add custom percentage or fixed fees, or clear table to disable taxes:")

            edited_taxes = st.data_editor(
                st.session_state[state_taxes_key],
                num_rows="dynamic",
                use_container_width=True,
                column_config={
                    "name": st.column_config.TextColumn("Fee/Tax Name"),
                    "type": st.column_config.SelectboxColumn(
                        "Type",
                        options=["percentage", "per_kwh", "fixed_monthly"],
                        default="percentage"
                    ),
                    "value": st.column_config.NumberColumn("Rate / Value", format="%.4f"),
                    "description": st.column_config.TextColumn("Notes / Description")
                },
                key=f"{key_prefix}_taxes_editor"
            )

            submitted = st.form_submit_button("Save Contract Configuration", icon=":material/save:", type="primary", use_container_width=True)

        if submitted:
            pricing_model_val = "day_ahead_dynamic" if is_dynamic_selected else "time_of_use"

            if is_dynamic_selected:
                cleaned_tou = [{"name": "Day-Ahead Dynamic Spot", "rate": default_rate_val, "start_time": "00:00", "end_time": "24:00"}]
                default_energy_rate = default_rate_val
            else:
                cleaned_tou = edited_tou.dropna(subset=["name", "rate"]).to_dict(orient="records") if edited_tou is not None and not edited_tou.empty else []
                for r in cleaned_tou:
                    r["rate"] = _sanitize_rate_val(r.get("rate", 0.20))
                    if r.get("name") == "Resto" and r.get("end_time") == "23:00":
                        r["end_time"] = "18:00"

                if not cleaned_tou:
                    cleaned_tou = [{"name": "Standard Rate", "rate": 0.20, "start_time": "00:00", "end_time": "24:00"}]
                default_energy_rate = float(cleaned_tou[0].get("rate", 0.20)) if cleaned_tou else 0.20

            st.session_state[state_tou_key] = pd.DataFrame(cleaned_tou)

            cleaned_taxes = []
            if edited_taxes is not None and not edited_taxes.empty:
                valid_tax_df = edited_taxes.dropna(subset=["name", "value"]).copy()
                mask = ~valid_tax_df["name"].astype(str).str.strip().str.lower().isin(["", "none", "nan"])
                valid_tax_df = valid_tax_df.loc[mask]
                raw_tax_records = valid_tax_df.to_dict(orient="records")
                for t in raw_tax_records:
                    t_name = str(t.get("name", "")).strip()
                    t_val = _sanitize_tax_val(t.get("value", 0.0))
                    if t_name and abs(t_val) > 1e-6:
                        cleaned_taxes.append({
                            "name": t_name,
                            "type": str(t.get("type", "percentage")).strip(),
                            "value": t_val,
                            "description": str(t.get("description", "")).strip() if pd.notnull(t.get("description")) else ""
                        })

            st.session_state[state_taxes_key] = pd.DataFrame(cleaned_taxes) if cleaned_taxes else pd.DataFrame(columns=["name", "type", "value", "description"])

            updated_contract = Contract(
                name=contract_name_val,
                currency=currency,
                base_monthly_fee=base_fee,
                contracted_capacity_kw=contracted_kw,
                monthly_capacity_tariff=capacity_tariff,
                demand_capacity_tariff=demand_tariff,
                max_physical_limit_kw=max_physical_kw,
                peak_penalty_rate=penalty_rate,
                network_volume_tariff=network_volume_tariff_val,
                pricing_model=pricing_model_val,
                supplier_margin=supplier_margin_val,
                market_price_profile_id=market_profile_val,
                reactive_power_tariff=reactive_tariff,
                min_power_factor=min_cos_phi,
                reactive_power_allowance_pct=reactive_allowance,
                tou_rates=cleaned_tou,
                default_energy_rate=default_energy_rate,
                weekend_is_off_peak=weekend_off_peak,
                applicable_months=parsed_app_months,
                taxes_and_fees=cleaned_taxes
            )

            # If contract was renamed, remove old name key from dictionary
            if current.name in loaded_dict and current.name != updated_contract.name:
                del loaded_dict[current.name]

            st.session_state[state_contract_key] = updated_contract
            loaded_dict[updated_contract.name] = updated_contract
            st.session_state[loaded_contracts_dict_key] = loaded_dict
            st.session_state[f"{key_prefix}_active_contract_label"] = updated_contract.name
            st.toast(f"Saved '{updated_contract.name}' ({len(parsed_app_months)} months assigned)!", icon=":material/check_circle:")
            st.rerun()

    return st.session_state[state_contract_key]


def render_minimal_contract_system(key_prefix: str = "sandbox_min") -> None:
    """
    Renders the minimal single-page flow:
      1. Consumption (CSV Load Profile Ingestion)
      2. Electricity Contract & Billing Assessment (Exact main app layout with simple terms)
    """
    st.title(":material/electric_meter: Simple Electricity Contract & Load Assessment Lab")
    st.caption("Upload your electricity consumption file (CSV) and configure the contract details.")

    # 1. Consumption Section
    st.header(":material/upload_file: 1. Consumption (CSV Load Profile)")
    render_csv_inspector(key_prefix=f"{key_prefix}_csv")

    st.markdown("---")

    # Find active load dataframe
    active_load_df = st.session_state.get("active_csv_df")
    if active_load_df is None or not isinstance(active_load_df, pd.DataFrame) or active_load_df.empty:
        for k in reversed(list(st.session_state.keys())):
            if "calc_data" in k and isinstance(st.session_state[k], dict) and "df_clean" in st.session_state[k]:
                df_c = st.session_state[k]["df_clean"]
                if isinstance(df_c, pd.DataFrame) and not df_c.empty:
                    active_load_df = df_c
                    break

    # 2. Electricity Contract Section
    st.header(":material/description: 2. Electricity Contract & Financial Assessment")
    contract = render_simplified_contract_form(key_prefix=f"{key_prefix}_contract")
    st.session_state["active_contract"] = contract

    st.divider()

    # 3. Monthly Cost & Financial Assessment Section
    st.subheader("Monthly Cost & Financial Assessment")

    if active_load_df is None or active_load_df.empty:
        st.info("Upload a CSV file in section 1 above to view the automated monthly financial assessment.", icon=":material/info:")
        return

    # Collect all loaded contracts to form portfolio for monthly dispatch
    loaded_dict = st.session_state.get(f"{key_prefix}_contract_loaded_contracts_dict", {})
    contracts_portfolio = list(loaded_dict.values()) if loaded_dict else [contract]
    if contract not in contracts_portfolio:
        contracts_portfolio.append(contract)

    # Calculate live bill breakdown across portfolio of monthly contracts
    full_breakdown: FinancialCostBreakdown = compute_financial_bill(load_data=active_load_df, contract=contracts_portfolio)
    curr = getattr(contract, "currency", "EUR")

    # Period filter selector
    is_synthetic_annual = (len(full_breakdown.monthly_series) == 12 and full_breakdown.duration_days <= 1.5)
    overview_label = "All Months (Full Year Overview)" if is_synthetic_annual else "All Months (Full Duration Overview)"
    month_options = [overview_label]
    if full_breakdown.monthly_series:
        month_options += [m.period_label for m in full_breakdown.monthly_series]

    col_sel1, col_sel2 = st.columns([5, 3])
    with col_sel1:
        selected_period = st.selectbox(
            "Select Billing Period / Month to Inspect:",
            options=month_options,
            index=0,
            key=f"{key_prefix}_period_select"
        )
    with col_sel2:
        st.write("")
        st.write("")
        is_single_month = (selected_period != overview_label)
        if is_single_month:
            active_month_c = _resolve_contract_for_month(contracts_portfolio, selected_period, default_contract=contract)
            pricing_type_str = "Dynamic Day-Ahead Spot" if getattr(active_month_c, "pricing_model", "time_of_use") == "day_ahead_dynamic" else "Fixed / TOU"
            st.info(
                f":material/contract: Active Contract for **{selected_period}**: **{active_month_c.name}** "
                f"({pricing_type_str} | {active_month_c.contracted_capacity_kw:.0f} kW, {active_month_c.monthly_capacity_tariff:.4f} {active_month_c.currency}/kW/mo)"
            )
        else:
            distinct_names = list(dict.fromkeys(c.name for c in contracts_portfolio))
            if len(distinct_names) > 1:
                st.info(f":material/account_tree: Multi-Contract portfolio active (**{len(distinct_names)}** contract configurations across 12 months).")

    if is_single_month:
        breakdown = compute_financial_bill(load_data=active_load_df, contract=contracts_portfolio, target_month=selected_period)
    else:
        breakdown = full_breakdown

    # Financial KPI Cards
    kpi_col1, kpi_col2, kpi_col3, kpi_col4 = st.columns(4)
    if is_single_month:
        excess_p = max(0.0, breakdown.peak_demand_kw - breakdown.contracted_capacity_kw)
        with kpi_col1:
            render_kpi_card(
                title=f"{selected_period} Gross Total",
                value=f"{breakdown.total_gross_period:,.2f} {curr}",
                subtext=f"Net: {breakdown.total_net_period:,.2f} | Taxes: {breakdown.total_taxes_period:,.2f}"
            )
        with kpi_col2:
            render_kpi_card(
                title=f"{selected_period} Peak Demand",
                value=f"{breakdown.peak_demand_kw:,.1f} kW",
                subtext=f"Overload: +{excess_p:,.1f} kW (Limit: {breakdown.contracted_capacity_kw:.0f} kW)",
                status="alert" if excess_p > 0 else "ok"
            )
        with kpi_col3:
            render_kpi_card(
                title=f"{selected_period} Energy",
                value=f"{breakdown.total_consumption_kwh:,.0f} kWh",
                subtext=f"Duration: {breakdown.duration_days:.0f} days"
            )
        with kpi_col4:
            render_kpi_card(
                title="Effective Unit Rate",
                value=f"{breakdown.effective_kwh_price:.4f} {curr}/kWh",
                subtext="All-inclusive unit cost"
            )
    else:
        if breakdown.monthly_series:
            sched_gross = sum(m.total_gross for m in breakdown.monthly_series)
            sched_net = sum(m.total_net for m in breakdown.monthly_series)
            sched_taxes = sum(m.taxes_and_levies for m in breakdown.monthly_series)
            sched_kwh = sum(m.energy_kwh for m in breakdown.monthly_series)
            n_months = len(breakdown.monthly_series)
            avg_monthly_gross = sched_gross / max(1, n_months)
            effective_price = (sched_gross / sched_kwh) if sched_kwh > 0 else breakdown.effective_kwh_price
        else:
            sched_gross = breakdown.total_gross_period
            sched_net = breakdown.total_net_period
            sched_taxes = breakdown.total_taxes_period
            avg_monthly_gross = breakdown.total_gross_monthly
            effective_price = breakdown.effective_kwh_price

        with kpi_col1:
            render_kpi_card(
                title="Total Gross Electricity Cost",
                value=f"{sched_gross:,.2f} {curr}",
                subtext=f"Net: {sched_net:,.2f} | Taxes: {sched_taxes:,.2f}"
            )
        with kpi_col2:
            render_kpi_card(
                title="Monthly Average Invoice",
                value=f"{avg_monthly_gross:,.2f} {curr}",
                subtext=f"12-month payment share",
                status="info"
            )
        with kpi_col3:
            render_kpi_card(
                title="Total Energy Consumed",
                value=f"{breakdown.total_consumption_kwh:,.0f} kWh",
                subtext=f"Peak Demand: {breakdown.peak_demand_kw:,.1f} kW"
            )
        with kpi_col4:
            render_kpi_card(
                title="Effective Unit Rate",
                value=f"{effective_price:.4f} {curr}/kWh",
                subtext="Total cost ÷ total kWh",
                status="success"
            )

    # Cost Breakdown Donut & Monthly Payment Schedule Series
    col_chart1, col_chart2 = st.columns([1, 1])
    with col_chart1:
        st.subheader("Cost Structure Distribution")
        fig_donut = create_cost_donut_figure(breakdown=breakdown)
        st.plotly_chart(fig_donut, use_container_width=True)

    with col_chart2:
        st.subheader("Payment Schedule Series (Zahlungsreihe)")
        fig_series = create_monthly_payment_series_figure(breakdown=full_breakdown)
        st.plotly_chart(fig_series, use_container_width=True)

    # Itemized Cost Table
    st.subheader("Itemized Billing Line Items")
    if breakdown.line_items:
        t_rows = []
        for it in breakdown.line_items:
            t_rows.append({
                "Category": it.category,
                "Description": it.description,
                "Basis": f"{it.basis_quantity:,.2f} {it.unit}",
                "Unit Rate": f"{it.unit_rate:.4f} {curr}",
                "Period Total": f"{it.cost_period:,.2f} {curr}",
                "Monthly Total": f"{it.cost_monthly:,.2f} {curr}",
                "Share": f"{it.share_pct:.1f} %"
            })
        st.dataframe(pd.DataFrame(t_rows), use_container_width=True, hide_index=True)


if __name__ == "__main__":
    st.set_page_config(
        page_title="Simple Electricity Contract Lab",
        page_icon=":material/electric_meter:",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    apply_custom_styles()
    render_minimal_contract_system()
