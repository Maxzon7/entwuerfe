"""
========================================================================================
Contract Form (current_model/ui/tab2_contract/form.py)
========================================================================================

Description:
------------
Streamlit form for defining electricity supply contracts, capacity charges (contracted + measured),
reactive power rules, dynamic Time-of-Use (TOU) energy rates table, and custom taxes/fees.
Includes intelligent input sanitization for European/Argentine comma decimals and auto-scaling.
"""

from typing import Dict, Any, List
import streamlit as st
import pandas as pd
from current_model.models.contract import Contract


def _sanitize_rate_val(val: Any, default: float = 0.20) -> float:
    """Sanitizes kWh rate inputs, converting comma strings and correcting unscaled 10,000x copy errors."""
    if val is None:
        return default
    if isinstance(val, str):
        val = val.replace(" ", "").replace(",", ".")
    try:
        f_val = float(val)
        # If rate was pasted without decimal point (e.g. 684335.0 instead of 68.4335)
        if f_val > 1000.0:
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


def render_contract_form(
    current_contract: Contract = None,
    as_expander: bool = False,
    key_prefix: str = "contract"
) -> Contract:
    """
    Renders the contract parameter configuration form.
    Stores and retrieves the contract model directly from `st.session_state`.
    """
    state_contract_key = f"{key_prefix}_contract_model"
    state_tou_key = f"{key_prefix}_tou_rates_df"
    state_taxes_key = f"{key_prefix}_taxes_df"

    if state_contract_key not in st.session_state:
        st.session_state[state_contract_key] = current_contract or Contract()

    current: Contract = st.session_state[state_contract_key]

    # Backward compatibility migration for session state objects
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
        st.caption("Configure contracted capacity, measured demand charges, reactive power rules, dynamic Time-of-Use (TOU) tariffs, and custom taxes/fees.")

        with st.form(key=f"{key_prefix}_contract_form"):
            st.subheader("1. Active Capacity & Base Fees")
            c1, c2 = st.columns(2)
            with c1:
                curr_options = ["ARS", "EUR", "USD", "GBP", "CHF"]
                current_curr = getattr(current, "currency", "ARS")
                curr_idx = curr_options.index(current_curr) if current_curr in curr_options else 0
                currency = st.selectbox("Currency:", options=curr_options, index=curr_idx, key=f"{key_prefix}_curr")
                base_fee = st.number_input("Base Monthly Fee (Cargo Comercialización):", min_value=0.0, value=float(current.base_monthly_fee), step=5.0, format="%.2f", key=f"{key_prefix}_base_fee")
                contracted_kw = st.number_input("Contracted Active Capacity (kW - Potencia Contratada):", min_value=0.0, value=float(current.contracted_capacity_kw), step=10.0, format="%.1f", key=f"{key_prefix}_kw")

            with c2:
                capacity_tariff = st.number_input("Contracted Capacity Tariff (/kW/month - Uso de Red):", min_value=0.0, value=float(current.monthly_capacity_tariff), step=1.0, format="%.4f", key=f"{key_prefix}_cap_t")
                demand_tariff = st.number_input("Measured Demand Tariff (/kW/month - Consumo de Potencia):", min_value=0.0, value=float(getattr(current, "demand_capacity_tariff", 0.0)), step=1.0, format="%.4f", key=f"{key_prefix}_dem_t")
                max_physical_kw = st.number_input("Max Physical Limit (kW):", min_value=0.0, value=float(current.max_physical_limit_kw), step=50.0, format="%.1f", key=f"{key_prefix}_max_kw")
                penalty_rate = st.number_input("Peak Penalty Rate (/kW - Exceso de Potencia):", min_value=0.0, value=float(current.peak_penalty_rate), step=1.0, format="%.4f", key=f"{key_prefix}_pen")

            st.subheader("2. Reactive Power Parameters")
            q1, q2, q3 = st.columns(3)
            with q1:
                reactive_tariff = st.number_input("Reactive Energy Tariff (/kVARh):", min_value=0.0, value=float(current.reactive_power_tariff), step=0.005, format="%.4f", key=f"{key_prefix}_react_t")
            with q2:
                min_cos_phi = st.number_input("Min Power Factor (cos phi):", min_value=0.50, max_value=1.00, value=float(current.min_power_factor), step=0.02, format="%.2f", key=f"{key_prefix}_cos_phi")
            with q3:
                reactive_allowance = st.number_input("Reactive Allowance (% of kWh):", min_value=0.0, max_value=100.0, value=float(current.reactive_power_allowance_pct), step=1.0, format="%.1f", key=f"{key_prefix}_react_allow")

            # 3. Dynamic Time-of-Use (TOU) Energy Rates
            st.subheader("3. Time-of-Use (TOU) Energy Rates")
            st.caption("Standard: Default 24h rate. You can add multiple Time-of-Use tariff windows or delete rows:")

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
                value=bool(current.weekend_is_off_peak),
                key=f"{key_prefix}_wknd"
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

            submitted = st.form_submit_button("💾 Save Contract Configuration", type="primary", use_container_width=True)

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

            st.session_state[state_contract_key] = Contract(
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
            st.success("Contract configuration successfully saved.")
            st.rerun()

    return st.session_state[state_contract_key]
