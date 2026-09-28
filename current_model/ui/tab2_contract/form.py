"""
========================================================================================
Contract Form (current_model/ui/tab2_contract/form.py)
========================================================================================

Description:
------------
Streamlit form for defining electricity supply contracts, capacity charges (contracted + measured),
reactive power rules, dynamic Time-of-Use (TOU) energy rates table, and custom taxes/fees.
Includes custom-named .drac file download (export), upload (import), and presets loader.
"""

import io
import os
import zipfile
from typing import Dict, Any, List, Optional, Tuple
import streamlit as st
import pandas as pd
import json
import re
from current_model.models.contract import Contract, get_contract_presets


def _sanitize_rate_val(val: Any, default: float = 0.20) -> float:
    """Sanitizes kWh rate inputs, converting comma strings and correcting unscaled 10,000x copy errors."""
    if val is None:
        return default
    if isinstance(val, str):
        val = val.replace(" ", "").replace(",", ".")
    try:
        f_val = float(val)
        # If rate was pasted without decimal point (e.g. 684335.0 instead of 68.4335)
        if f_val > 50000.0:
            f_val = f_val / 10000.0
        return round(f_val, 4)
    except Exception:
        return default


def _sanitize_tax_val(val: Any) -> float:
    """Sanitizes tax/fee values, supporting positive percentages, fixed monthly fees, and negative credit adjustments."""
    if val is None:
        return 0.0
    if isinstance(val, str):
        val = val.replace(" ", "").replace(",", ".")
    try:
        return float(val)
    except Exception:
        return 0.0


def _sanitize_filename(name: str, default: str = "contract.drac") -> str:
    """Ensures a clean filename ending with .drac."""
    name = (name or "").strip()
    if not name:
        return default
    # Replace invalid filename characters
    clean = re.sub(r'[\\/*?:"<>|]', "_", name)
    if not clean.lower().endswith(".drac"):
        clean += ".drac"
    return clean


def _parse_uploaded_contract_files(uploaded_files: List[Any]) -> Dict[str, Contract]:
    """Parses one or multiple .drac, .json, or .zip files containing electricity contracts."""
    parsed_contracts: Dict[str, Contract] = {}
    if not uploaded_files:
        return parsed_contracts

    for f in uploaded_files:
        fname = getattr(f, "name", "contract.drac")
        if fname.lower().endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(f.getvalue())) as z:
                    for member in z.namelist():
                        if member.lower().endswith((".drac", ".json")) and not member.startswith("__MACOSX"):
                            try:
                                content = z.read(member).decode("utf-8")
                                c = Contract.from_json(content)
                                base_member = os.path.basename(member)
                                label = f"{c.name} ({base_member})" if c.name else base_member
                                parsed_contracts[label] = c
                            except Exception:
                                continue
            except Exception:
                continue
        else:
            try:
                content = f.getvalue().decode("utf-8")
                c = Contract.from_json(content)
                label = f"{c.name} ({fname})" if c.name else fname
                parsed_contracts[label] = c
            except Exception:
                continue
    return parsed_contracts


def _sync_contract_to_state(contract: Contract, key_prefix: str) -> None:
    """Synchronizes a Contract object into Streamlit session state and data editors."""
    state_contract_key = f"{key_prefix}_contract_model"
    state_tou_key = f"{key_prefix}_tou_rates_df"
    state_taxes_key = f"{key_prefix}_taxes_df"
    active_lbl_key = f"{key_prefix}_active_contract_label"

    st.session_state[state_contract_key] = contract
    st.session_state[active_lbl_key] = contract.name
    st.session_state["active_contract"] = contract
    st.session_state[state_tou_key] = pd.DataFrame(contract.tou_rates) if contract.tou_rates else pd.DataFrame([
        {"name": "Standard Rate", "rate": contract.default_energy_rate, "start_time": "00:00", "end_time": "24:00"}
    ])
    st.session_state[state_taxes_key] = pd.DataFrame(contract.taxes_and_fees) if contract.taxes_and_fees else pd.DataFrame(columns=["name", "type", "value", "description"])

    # Clear data editor state keys so changes reflect immediately in UI
    for k in [f"{key_prefix}_tou_editor", f"{key_prefix}_taxes_editor"]:
        if k in st.session_state:
            del st.session_state[k]


def render_contract_form(
    current_contract: Contract = None,
    as_expander: bool = False,
    key_prefix: str = "contract"
) -> Contract:
    """
    Renders the contract parameter configuration form with custom-named .drac export/import and presets.
    Stores and retrieves the contract model directly from `st.session_state`.
    """
    state_contract_key = f"{key_prefix}_contract_model"
    state_tou_key = f"{key_prefix}_tou_rates_df"
    state_taxes_key = f"{key_prefix}_taxes_df"
    loaded_contracts_dict_key = f"{key_prefix}_loaded_contracts_dict"
    uploader_sig_key = f"{key_prefix}_last_files_sig"

    if state_contract_key not in st.session_state:
        st.session_state[state_contract_key] = current_contract or Contract()

    raw_current = st.session_state[state_contract_key]

    # Robust migration: ensure instance is of latest Contract class with to_json/from_json
    if not hasattr(raw_current, "to_json"):
        current = Contract(
            name=str(getattr(raw_current, "name", "Electricity Contract")),
            currency=str(getattr(raw_current, "currency", "EUR")),
            base_monthly_fee=float(getattr(raw_current, "base_monthly_fee", 50.0)),
            contracted_capacity_kw=float(getattr(raw_current, "contracted_capacity_kw", 400.0)),
            monthly_capacity_tariff=float(getattr(raw_current, "monthly_capacity_tariff", 0.15)),
            demand_capacity_tariff=float(getattr(raw_current, "demand_capacity_tariff", 0.0)),
            max_physical_limit_kw=float(getattr(raw_current, "max_physical_limit_kw", 1000.0)),
            peak_penalty_rate=float(getattr(raw_current, "peak_penalty_rate", 0.25)),
            reactive_power_tariff=float(getattr(raw_current, "reactive_power_tariff", 0.03)),
            min_power_factor=float(getattr(raw_current, "min_power_factor", 0.90)),
            reactive_power_allowance_pct=float(getattr(raw_current, "reactive_power_allowance_pct", 33.0)),
            tou_rates=getattr(raw_current, "tou_rates", [{"name": "Standard Rate", "rate": 0.20, "start_time": "00:00", "end_time": "24:00"}]),
            default_energy_rate=float(getattr(raw_current, "default_energy_rate", 0.20)),
            weekend_is_off_peak=bool(getattr(raw_current, "weekend_is_off_peak", False)),
            taxes_and_fees=getattr(raw_current, "taxes_and_fees", [])
        )
        st.session_state[state_contract_key] = current
    else:
        current = raw_current

    # Backward compatibility migration for session state objects
    if not hasattr(current, "name") or not current.name:
        current.name = "Electricity Contract"

    if not hasattr(current, "tou_rates") or current.tou_rates is None:
        default_r = getattr(current, "default_energy_rate", 0.20)
        current.tou_rates = [{"name": "Standard Rate", "rate": default_r, "start_time": "00:00", "end_time": "24:00"}]

    if not hasattr(current, "taxes_and_fees") or current.taxes_and_fees is None:
        current.taxes_and_fees = []

    if state_tou_key not in st.session_state:
        st.session_state[state_tou_key] = pd.DataFrame(current.tou_rates)

    if state_taxes_key not in st.session_state:
        st.session_state[state_taxes_key] = pd.DataFrame(current.taxes_and_fees) if current.taxes_and_fees else pd.DataFrame(columns=["name", "type", "value", "description"])

    container = st.expander("Electricity Supply Contract & Tariff Configuration", expanded=False) if as_expander else st.container()

    with container:
        # ==============================================================================
        # Contract File Management & Presets Toolbar (Download / Upload as .drac)
        # ==============================================================================
        st.markdown("### Contract File Transfer & Presets (.drac)")
        st.caption("Download your configured contract as a reusable `.drac` file or upload multiple saved contract files / ZIP archives.")

        col_up, col_down = st.columns([1, 1])

        # --- LEFT: Upload / Import / Presets ---
        with col_up:
            st.markdown("##### Import Contract(s)")
            uploaded_files = st.file_uploader(
                "Select `.drac`, `.json` or `.zip` contract file(s):",
                type=["drac", "json", "zip"],
                accept_multiple_files=True,
                key=f"{key_prefix}_file_uploader",
                help="Upload one or multiple .drac/.json contract files (or a .zip folder) to inspect and switch between them."
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
                    else:
                        st.error("No valid contract files (.drac or .json) could be parsed from upload.")

            # Dynamic Contract Switcher if multiple contracts are loaded or created
            loaded_dict = st.session_state.get(loaded_contracts_dict_key, {})
            # Ensure current active contract is in dictionary
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
                index=sel_idx
            )
            if selected_label != current_sel and selected_label in loaded_dict:
                _sync_contract_to_state(loaded_dict[selected_label], key_prefix=key_prefix)
                st.rerun()

            # Contract Actions: Create New, Duplicate, or Delete
            btn_act1, btn_act2, btn_act3 = st.columns(3)
            with btn_act1:
                if st.button("Create New Contract", icon=":material/add_circle:", key=f"{key_prefix}_new_contract_btn", use_container_width=True):
                    new_c_name = f"Contract #{len(loaded_dict) + 1}"
                    new_contract = Contract(
                        name=new_c_name,
                        currency=current.currency,
                        base_monthly_fee=50.0,
                        contracted_capacity_kw=current.contracted_capacity_kw,
                        monthly_capacity_tariff=0.15,
                        tou_rates=[{"name": "Standard Rate", "rate": 0.20, "start_time": "00:00", "end_time": "24:00"}]
                    )
                    loaded_dict[new_c_name] = new_contract
                    st.session_state[loaded_contracts_dict_key] = loaded_dict
                    _sync_contract_to_state(new_contract, key_prefix=key_prefix)
                    st.success(f"Created new contract: {new_c_name}")
                    st.rerun()

            with btn_act2:
                if st.button("Duplicate Current", icon=":material/content_copy:", key=f"{key_prefix}_dup_contract_btn", use_container_width=True):
                    dup_name = f"{current.name} (Copy)"
                    dup_contract = Contract.from_dict(current.to_dict()) if hasattr(current, "to_dict") else Contract.from_json(current.to_json())
                    dup_contract.name = dup_name
                    loaded_dict[dup_name] = dup_contract
                    st.session_state[loaded_contracts_dict_key] = loaded_dict
                    _sync_contract_to_state(dup_contract, key_prefix=key_prefix)
                    st.success(f"Duplicated to: {dup_name}")
                    st.rerun()

            with btn_act3:
                can_delete = len(loaded_dict) > 1
                if st.button("Delete Contract", icon=":material/delete:", key=f"{key_prefix}_del_contract_btn", use_container_width=True, disabled=not can_delete):
                    if current_sel in loaded_dict and len(loaded_dict) > 1:
                        del loaded_dict[current_sel]
                        st.session_state[loaded_contracts_dict_key] = loaded_dict
                        new_first = list(loaded_dict.keys())[0]
                        _sync_contract_to_state(loaded_dict[new_first], key_prefix=key_prefix)
                        st.warning(f"Deleted contract: {current_sel}")
                        st.rerun()

            # Preset selector
            presets = get_contract_presets()
            selected_preset_name = st.selectbox(
                "Or load an industry contract preset:",
                options=["-- Select a Template --"] + list(presets.keys()),
                index=0,
                key=f"{key_prefix}_preset_select"
            )
            p_col1, p_col2 = st.columns(2)
            with p_col1:
                if selected_preset_name in presets:
                    if st.button("Apply Preset", icon=":material/playlist_add_check:", key=f"{key_prefix}_apply_preset_btn", use_container_width=True):
                        preset_c = presets[selected_preset_name]
                        preset_copy = Contract.from_dict(preset_c.to_dict()) if hasattr(preset_c, "to_dict") else Contract.from_json(preset_c.to_json())
                        loaded_dict[preset_copy.name] = preset_copy
                        st.session_state[loaded_contracts_dict_key] = loaded_dict
                        _sync_contract_to_state(preset_copy, key_prefix=key_prefix)
                        st.success(f"Loaded preset: {selected_preset_name}")
                        st.rerun()
            with p_col2:
                if st.button("Reset to Basic Contract", icon=":material/restart_alt:", key=f"{key_prefix}_reset_basic_c_btn", use_container_width=True, help="Restores the standard baseline utility tariff contract."):
                    default_c = Contract(name="Standard Utility Contract (Baseline)")
                    loaded_dict[default_c.name] = default_c
                    st.session_state[loaded_contracts_dict_key] = loaded_dict
                    _sync_contract_to_state(default_c, key_prefix=key_prefix)
                    st.rerun()

        # --- RIGHT: Download / Export as .drac ---
        with col_down:
            st.markdown("##### Export Contract")
            default_file_base = re.sub(r'[^a-zA-Z0-9_-]', '_', current.name.lower().strip()) or "electricity_contract"
            custom_download_filename = st.text_input(
                "Individual Download Filename (.drac):",
                value=f"{default_file_base}.drac",
                key=f"{key_prefix}_custom_filename_input",
                help="Specify your custom filename. The .drac extension will automatically be ensured."
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
            st.caption(f"Ready for export: **{current.name}** ({current.currency}, {current.contracted_capacity_kw:.0f} kW, {len(current.tou_rates)} TOU windows)")

        st.divider()

        # ==============================================================================
        # Contract Parameter Configuration Form
        # ==============================================================================
        with st.form(key=f"{key_prefix}_contract_form"):
            st.subheader("1. General & Active Capacity Parameters")

            # Contract Name
            contract_name_val = st.text_input(
                "Contract Name / Identifier:",
                value=str(current.name),
                help="Custom name or tariff identifier for this contract."
            )

            c1, c2 = st.columns(2)
            with c1:
                curr_options = ["ARS", "EUR", "USD", "GBP", "CHF"]
                current_curr = getattr(current, "currency", "EUR")
                curr_idx = curr_options.index(current_curr) if current_curr in curr_options else 1
                currency = st.selectbox("Currency:", options=curr_options, index=curr_idx)
                base_fee = st.number_input("Base Monthly Fee (Cargo Comercialización):", min_value=0.0, value=float(current.base_monthly_fee), step=5.0, format="%.2f")
                contracted_kw = st.number_input("Contracted Active Capacity (kW - Potencia Contratada):", min_value=0.0, value=float(current.contracted_capacity_kw), step=10.0, format="%.1f")

            with c2:
                capacity_tariff = st.number_input("Contracted Capacity Tariff (/kW/month - Uso de Red):", min_value=0.0, value=float(current.monthly_capacity_tariff), step=1.0, format="%.4f")
                demand_tariff = st.number_input("Measured Demand Tariff (/kW/month - Consumo de Potencia):", min_value=0.0, value=float(getattr(current, "demand_capacity_tariff", 0.0)), step=1.0, format="%.4f")
                max_physical_kw = st.number_input("Max Physical Limit (kW):", min_value=0.0, value=float(current.max_physical_limit_kw), step=50.0, format="%.1f")
                penalty_rate = st.number_input("Peak Penalty Rate (/kW - Exceso de Potencia):", min_value=0.0, value=float(current.peak_penalty_rate), step=1.0, format="%.4f")

            st.subheader("2. Reactive Power Parameters")
            q1, q2, q3 = st.columns(3)
            with q1:
                reactive_tariff = st.number_input("Reactive Energy Tariff (/kVARh):", min_value=0.0, value=float(current.reactive_power_tariff), step=0.005, format="%.4f")
            with q2:
                min_cos_phi = st.number_input("Min Power Factor (cos phi):", min_value=0.50, max_value=1.00, value=float(current.min_power_factor), step=0.02, format="%.2f")
            with q3:
                reactive_allowance = st.number_input("Reactive Allowance (% of kWh):", min_value=0.0, max_value=100.0, value=float(current.reactive_power_allowance_pct), step=1.0, format="%.1f")

            # 3. Dynamic Time-of-Use (TOU) Energy Rates
            st.subheader("3. Time-of-Use (TOU) Energy Rates")
            st.caption("Define Time-of-Use rate windows. The table supports adding and deleting rows:")

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

            weekend_off_peak = st.checkbox(
                "Treat Weekends as Off-Peak (Apply Lowest Tariff)",
                value=bool(current.weekend_is_off_peak)
            )

            # 4. Dynamic Taxes & Additional Fees Table
            st.subheader("4. Taxes & Additional Fees")
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
            # Clean, sanitize, and validate TOU rates table
            cleaned_tou = edited_tou.dropna(subset=["name", "rate"]).to_dict(orient="records") if edited_tou is not None and not edited_tou.empty else []
            for r in cleaned_tou:
                r["rate"] = _sanitize_rate_val(r.get("rate", 0.20))
                # Fix common typo where 05:00 to 23:00 was entered for Resto instead of 05:00 to 18:00
                if r.get("name") == "Resto" and r.get("end_time") == "23:00":
                    r["end_time"] = "18:00"

            if not cleaned_tou:
                cleaned_tou = [{"name": "Standard Rate", "rate": 0.20, "start_time": "00:00", "end_time": "24:00"}]
            st.session_state[state_tou_key] = pd.DataFrame(cleaned_tou)

            # Clean and validate Taxes table
            cleaned_taxes = []
            if edited_taxes is not None and not edited_taxes.empty:
                # Drop invalid rows where name or value is null or empty
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

            default_rate = float(cleaned_tou[0].get("rate", 0.20))

            updated_contract = Contract(
                name=contract_name_val.strip() if contract_name_val else "Electricity Contract",
                currency=currency,
                base_monthly_fee=base_fee,
                contracted_capacity_kw=contracted_kw,
                monthly_capacity_tariff=capacity_tariff,
                demand_capacity_tariff=demand_tariff,
                max_physical_limit_kw=max_physical_kw,
                peak_penalty_rate=penalty_rate,
                reactive_power_tariff=reactive_tariff,
                min_power_factor=min_cos_phi,
                reactive_power_allowance_pct=reactive_allowance,
                tou_rates=cleaned_tou,
                default_energy_rate=default_rate,
                weekend_is_off_peak=weekend_off_peak,
                taxes_and_fees=cleaned_taxes
            )
            if loaded_contracts_dict_key in st.session_state and st.session_state[loaded_contracts_dict_key]:
                old_active_lbl = st.session_state.get(f"{key_prefix}_active_contract_label")
                new_lbl = updated_contract.name
                if old_active_lbl and old_active_lbl != new_lbl and old_active_lbl in st.session_state[loaded_contracts_dict_key]:
                    del st.session_state[loaded_contracts_dict_key][old_active_lbl]
                st.session_state[loaded_contracts_dict_key][new_lbl] = updated_contract

            _sync_contract_to_state(updated_contract, key_prefix=key_prefix)
            st.success("Contract configuration successfully saved.")
            st.rerun()
    return st.session_state[state_contract_key]
