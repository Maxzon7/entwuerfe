# To Run standalone: python -m streamlit run templates/contract_form_template.py

"""
Contract Form Template & Component
==================================
Reusable Streamlit form for configuring and saving an electricity supply
contract with Active & Reactive power, Time-of-Use (TOU) rates, and Taxes/Fees.
"""

import streamlit as st
import pandas as pd
from models.contract import Contract


def render_contract_form(as_expander: bool = True, key_prefix: str = "main") -> Contract:
    """
    Renders an electricity supply contract configuration form.
    Can be embedded directly or wrapped inside an st.expander.
    """
    # Initialize contract in session state
    state_contract_key = f"{key_prefix}_contract"
    state_taxes_key = f"{key_prefix}_contract_taxes_df"

    if state_contract_key not in st.session_state:
        st.session_state[state_contract_key] = Contract()

    current: Contract = st.session_state[state_contract_key]

    if state_taxes_key not in st.session_state or st.session_state[state_taxes_key].empty:
        st.session_state[state_taxes_key] = pd.DataFrame(current.taxes_and_fees)

    # Container definition (expander or direct container)
    container = st.expander("Electricity Supply Contract & Tariff Configuration", expanded=False) if as_expander else st.container()

    with container:
        st.caption("Configure contracted capacity, reactive power parameters, Time-of-Use (TOU) tariffs, and custom taxes/fees.")

        with st.form(key=f"{key_prefix}_contract_form"):
            st.subheader("1. Active Capacity & Base Fees")
            c1, c2 = st.columns(2)
            with c1:
                currency = st.selectbox("Currency:", options=["EUR", "USD", "ARS", "GBP", "CHF"], index=0, key=f"{key_prefix}_curr")
                base_fee = st.number_input("Base Monthly Fee:", min_value=0.0, value=float(current.base_monthly_fee), step=5.0, key=f"{key_prefix}_base_fee")
                contracted_kw = st.number_input("Contracted Capacity (kW):", min_value=0.0, value=float(current.contracted_capacity_kw), step=10.0, key=f"{key_prefix}_kw")

            with c2:
                capacity_tariff = st.number_input("Monthly Capacity Tariff (/kW/month):", min_value=0.0, value=float(current.monthly_capacity_tariff), step=0.05, format="%.3f", key=f"{key_prefix}_cap_t")
                max_physical_kw = st.number_input("Max Physical Limit (kW):", min_value=0.0, value=float(current.max_physical_limit_kw), step=50.0, key=f"{key_prefix}_max_kw")
                penalty_rate = st.number_input("Peak Penalty Rate (/kW):", min_value=0.0, value=float(current.peak_penalty_rate), step=0.05, format="%.3f", key=f"{key_prefix}_pen")

            st.subheader("2. Reactive Power Parameters")
            q1, q2, q3 = st.columns(3)
            with q1:
                reactive_tariff = st.number_input("Reactive Energy Tariff (/kVARh):", min_value=0.0, value=float(current.reactive_power_tariff), step=0.005, format="%.3f", key=f"{key_prefix}_react_t")
            with q2:
                min_cos_phi = st.number_input("Min Power Factor (cos phi):", min_value=0.50, max_value=1.00, value=float(current.min_power_factor), step=0.02, format="%.2f", key=f"{key_prefix}_cos_phi")
            with q3:
                reactive_allowance = st.number_input("Reactive Allowance (% of kWh):", min_value=0.0, max_value=100.0, value=float(current.reactive_power_allowance_pct), step=1.0, key=f"{key_prefix}_react_allow")

            st.subheader("3. Time-of-Use (TOU) Energy Rates")
            r1, r2 = st.columns(2)
            with r1:
                peak_rate = st.number_input("Peak Energy Rate (/kWh):", min_value=0.0, value=float(current.peak_energy_rate), step=0.01, format="%.3f", key=f"{key_prefix}_peak_r")
                peak_start = st.number_input("Peak Window Start Hour (0-23):", min_value=0, max_value=23, value=int(current.peak_hours[0]), step=1, key=f"{key_prefix}_peak_s")
                weekend_off_peak = st.checkbox("Treat Weekends as Off-Peak", value=bool(current.weekend_is_off_peak), key=f"{key_prefix}_wknd")

            with r2:
                off_peak_rate = st.number_input("Off-Peak Energy Rate (/kWh):", min_value=0.0, value=float(current.off_peak_energy_rate), step=0.01, format="%.3f", key=f"{key_prefix}_offpeak_r")
                peak_end = st.number_input("Peak Window End Hour (0-23):", min_value=0, max_value=23, value=int(current.peak_hours[1]), step=1, key=f"{key_prefix}_peak_e")

            st.subheader("4. Taxes & Additional Fees")
            st.caption("Standard: 20% VAT. You can add custom fees or delete rows:")

            edited_taxes = st.data_editor(
                st.session_state[state_taxes_key],
                num_rows="dynamic",
                use_container_width=True,
                column_config={
                    "name": st.column_config.TextColumn("Fee/Tax Name", required=True),
                    "type": st.column_config.SelectboxColumn(
                        "Type",
                        options=["percentage", "per_kwh", "fixed_monthly"],
                        required=True
                    ),
                    "value": st.column_config.NumberColumn("Rate / Value", format="%.3f", required=True),
                    "description": st.column_config.TextColumn("Notes / Description")
                },
                key=f"{key_prefix}_taxes_editor"
            )

            submitted = st.form_submit_button("Save Contract Configuration", type="primary", use_container_width=True)

        if submitted:
            cleaned_taxes = edited_taxes.dropna(subset=["name", "value"]).to_dict(orient="records")
            st.session_state[state_taxes_key] = pd.DataFrame(cleaned_taxes) if cleaned_taxes else pd.DataFrame(columns=["name", "type", "value", "description"])

            st.session_state[state_contract_key] = Contract(
                currency=currency,
                base_monthly_fee=base_fee,
                contracted_capacity_kw=contracted_kw,
                monthly_capacity_tariff=capacity_tariff,
                max_physical_limit_kw=max_physical_kw,
                peak_penalty_rate=penalty_rate,
                reactive_power_tariff=reactive_tariff,
                min_power_factor=min_cos_phi,
                reactive_power_allowance_pct=reactive_allowance,
                peak_energy_rate=peak_rate,
                off_peak_energy_rate=off_peak_rate,
                peak_hours=(int(peak_start), int(peak_end)),
                weekend_is_off_peak=weekend_off_peak,
                taxes_and_fees=cleaned_taxes
            )
            st.success("Contract configuration successfully saved.")

    return st.session_state[state_contract_key]


if __name__ == "__main__":
    st.set_page_config(page_title="Contract Form Template", layout="centered")
    st.title("Electricity Contract Configuration")
    render_contract_form(as_expander=False)
