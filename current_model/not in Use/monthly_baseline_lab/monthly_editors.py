"""
========================================================================================
Monthly Baseline Table Editors (Table A: Consumption & Table B: Tariffs)
(current_model/ui_sandbox/monthly_editors.py)
========================================================================================

Description:
------------
Renders the interactive dual-matrix data editors for the 12-Month Baseline Lab:
1. Table A: 12-Month Ingestion Matrix (kWh per TOU window, P_contract, P_max)
   - Reset Consumption Data button.
2. Table B: 12-Month Contract & Tariff Matrix (Base fee, $/kW, $/kWh, Taxes %)
   - Reset Tariff Data button.
   - Copy Month 1 Rates to All 12 Months button.
========================================================================================
"""

from typing import List
import pandas as pd
import streamlit as st

# Safe imports
try:
    from current_model.ui_sandbox.monthly_baseline_lab.monthly_presets import TOUTierConfig, reload_preset_data
except ImportError:
    from monthly_presets import TOUTierConfig, reload_preset_data


def render_consumption_table_editor(
    key_prefix: str = "monthly_baseline",
    active_tiers: List[TOUTierConfig] = None,
    preset_name: str = "Standard Contract"
) -> pd.DataFrame:
    """
    Renders Section 3: Table A — 12-Month Consumption & Peak Demand Matrix.
    Returns:
        pd.DataFrame: Validated, user-edited consumption DataFrame.
    """
    if active_tiers is None:
        active_tiers = []

    state_cdf_key = f"{key_prefix}_consumption_df"

    col_hdr_a1, col_hdr_a2 = st.columns([3.5, 1.5])
    with col_hdr_a1:
        st.markdown("### :material/table_chart: 1. Consumption Matrix (12 Months)")
        st.caption("Enter monthly energy volumes (kWh) per TOU window, contracted capacity ($P_{contract}$), and measured monthly peak ($P_{max}$).")
    with col_hdr_a2:
        if st.button(
            ":material/restart_alt: Reset Consumption Data",
            key=f"{key_prefix}_btn_reset_consumption",
            use_container_width=True,
            help="Reset consumption volumes and peak demands to initial preset values"
        ):
            c_re, _, _, _, _, _ = reload_preset_data(preset_name)
            st.session_state[state_cdf_key] = c_re
            st.rerun()

    cdf_raw = st.session_state[state_cdf_key].copy()

    # Ensure all tier columns exist in consumption DataFrame
    for tier in active_tiers:
        col_id = f"kWh_{tier.id}"
        if col_id not in cdf_raw.columns:
            if tier.id == "peak" and "kWh_peak" in cdf_raw.columns:
                cdf_raw[col_id] = cdf_raw["kWh_peak"]
            elif tier.id == "offpeak" and "kWh_offpeak" in cdf_raw.columns:
                cdf_raw[col_id] = cdf_raw["kWh_offpeak"]
            else:
                cdf_raw[col_id] = 10000.0

    # Column configuration for Table A
    col_cfg_c = {
        "month_index": st.column_config.NumberColumn("Month #", disabled=True, width="small"),
        "Month": st.column_config.TextColumn("Month", disabled=True, width="medium"),
        "P_contract_kW": st.column_config.NumberColumn("P_contract (kW)", min_value=0.0, max_value=50000.0, step=1.0, format="%.0f kW"),
        "P_max_kW": st.column_config.NumberColumn("P_max (kW)", min_value=0.0, max_value=50000.0, step=1.0, format="%.0f kW"),
    }
    for tier in active_tiers:
        col_cfg_c[f"kWh_{tier.id}"] = st.column_config.NumberColumn(
            f"{tier.name} (kWh)",
            min_value=0.0,
            max_value=1e9,
            step=100.0,
            format="%.0f kWh"
        )

    edited_cdf = st.data_editor(
        cdf_raw,
        use_container_width=True,
        num_rows="fixed",
        key=f"{key_prefix}_consumption_editor",
        column_config=col_cfg_c,
        hide_index=True
    )
    st.session_state[state_cdf_key] = edited_cdf
    st.markdown("---")
    return edited_cdf


def render_tariff_table_editor(
    key_prefix: str = "monthly_baseline",
    active_tiers: List[TOUTierConfig] = None,
    selected_cur: str = "EUR",
    preset_name: str = "Standard Contract"
) -> pd.DataFrame:
    """
    Renders Section 4: Table B — 12-Month Contract & Tariff Matrix.
    Returns:
        pd.DataFrame: Validated, user-edited tariff DataFrame.
    """
    if active_tiers is None:
        active_tiers = []

    state_tdf_key = f"{key_prefix}_tariff_df"

    st.markdown(f"### :material/request_quote: 2. Contract & Tariff Matrix (12 Months) — Currency: `{selected_cur}`")
    st.caption(
        "Enter monthly standing fees, capacity rates, limit violation penalties, peak demand charges, "
        "energy unit rates per TOU window, and statutory tax rates."
    )

    tdf_raw = st.session_state[state_tdf_key].copy()

    # Ensure all rate columns exist in tariff DataFrame
    for tier in active_tiers:
        col_id = f"rate_{tier.id}"
        if col_id not in tdf_raw.columns:
            if tier.id == "peak" and "rate_peak" in tdf_raw.columns:
                tdf_raw[col_id] = tdf_raw["rate_peak"]
            elif tier.id == "offpeak" and "rate_offpeak" in tdf_raw.columns:
                tdf_raw[col_id] = tdf_raw["rate_offpeak"]
            else:
                tdf_raw[col_id] = 100.0 if selected_cur == "ARS" else 0.1500

    # Ensure default numeric columns exist
    default_cols = {
        "base_fee": 28929.64 if selected_cur == "ARS" else 174.50,
        "metering_fee": 0.0 if selected_cur == "ARS" else 75.00,
        "rate_contracted_kw": 3589.886 if selected_cur == "ARS" else 2.440,
        "rate_excess_kw": 3589.886 if selected_cur == "ARS" else 0.0,
        "rate_peak_demand_kw": 0.0 if selected_cur == "ARS" else 3.71,
        "tax_rate_pct": 37.59 if selected_cur == "ARS" else 21.0,
        "exempt_surcharge": 16688.00 if selected_cur == "ARS" else 0.0
    }
    for col_name, def_val in default_cols.items():
        if col_name not in tdf_raw.columns:
            tdf_raw[col_name] = def_val

    # Table B helper buttons
    col_t_space, col_t_reset, col_t_btn = st.columns([2.0, 1.5, 1.5])
    with col_t_reset:
        if st.button(
            ":material/restart_alt: Reset Tariff Data",
            key=f"{key_prefix}_btn_reset_tariffs",
            use_container_width=True,
            help="Reset tariff rates to initial preset values"
        ):
            _, t_re, _, _, _, _ = reload_preset_data(preset_name)
            st.session_state[state_tdf_key] = t_re
            st.rerun()
    with col_t_btn:
        if st.button(":material/content_copy: Copy Month 1 Rates to All", key=f"{key_prefix}_copy_m1", use_container_width=True, help="Replicate Month 1 tariff rates across all 12 calendar months"):
            m1_row = tdf_raw.iloc[0]
            for col in tdf_raw.columns:
                if col not in ["month_index", "Month"]:
                    tdf_raw[col] = m1_row[col]
            st.session_state[state_tdf_key] = tdf_raw
            st.rerun()

    # Column configuration for Table B with 3-Party Market Attribution
    col_cfg_t = {
        "month_index": st.column_config.NumberColumn("Month #", disabled=True, width="small"),
        "Month": st.column_config.TextColumn("Month", disabled=True, width="medium"),
        "base_fee": st.column_config.NumberColumn(
            f"DSO Base Fee ({selected_cur})",
            min_value=0.0,
            max_value=1e9,
            step=100.0 if selected_cur == "ARS" else 5.0,
            format="%.2f",
            help="Regulated standing charge from the Distribution Network Operator (DSO)"
        ),
        "metering_fee": st.column_config.NumberColumn(
            f"Meetbedrijf Meter Fee ({selected_cur})",
            min_value=0.0,
            max_value=1e9,
            step=10.0 if selected_cur == "ARS" else 5.0,
            format="%.2f",
            help="Monthly telemetry and certified meter rental fee from the Meetbedrijf"
        ),
        "rate_contracted_kw": st.column_config.NumberColumn(
            f"DSO Capacity ({selected_cur}/kW)",
            min_value=0.0,
            max_value=1e8,
            step=10.0 if selected_cur == "ARS" else 0.10,
            format="%.3f",
            help="Regulated contracted grid transport capacity rate from DSO"
        ),
        "rate_excess_kw": st.column_config.NumberColumn(
            f"DSO Over Limit ({selected_cur}/kW)",
            min_value=0.0,
            max_value=1e8,
            step=10.0 if selected_cur == "ARS" else 0.50,
            format="%.3f",
            help="Penalty charge for exceeding contracted capacity limit"
        ),
        "rate_peak_demand_kw": st.column_config.NumberColumn(
            f"DSO Peak Demand ({selected_cur}/kW)",
            min_value=0.0,
            max_value=1e8,
            step=10.0 if selected_cur == "ARS" else 0.10,
            format="%.3f",
            help="Measured peak demand charge (kW-max) from DSO"
        ),
    }
    for tier in active_tiers:
        col_cfg_t[f"rate_{tier.id}"] = st.column_config.NumberColumn(
            f"Supplier {tier.name} ({selected_cur}/kWh)",
            min_value=0.0,
            max_value=1e6,
            step=1.0 if selected_cur == "ARS" else 0.005,
            format="%.4f",
            help="Commodity energy unit rate billed by the Energy Supplier"
        )
    col_cfg_t["tax_rate_pct"] = st.column_config.NumberColumn("Statutory Taxes (%)", min_value=0.0, max_value=200.0, step=0.01, format="%.2f%%")
    col_cfg_t["exempt_surcharge"] = st.column_config.NumberColumn(f"Exempt Surcharge ({selected_cur})", min_value=0.0, max_value=1e9, step=100.0 if selected_cur == "ARS" else 5.0, format="%.2f")

    edited_tdf = st.data_editor(
        tdf_raw,
        use_container_width=True,
        num_rows="fixed",
        key=f"{key_prefix}_tariff_editor",
        column_config=col_cfg_t,
        hide_index=True
    )
    st.session_state[state_tdf_key] = edited_tdf
    st.markdown("---")
    return edited_tdf
