"""
========================================================================================
Dutch Grid Operator Tariff Generator (Enexis & Liander 2025)
(current_model/ui_sandbox/monthly_dso_generator.py)
========================================================================================

Description:
------------
Interactive configuration form for generating official Dutch 2025 network tariffs:
- Grid Operators: Enexis Netbeheer & Liander.
- Voltage Levels / Grid Tiers: LS, MS/LS, MS-D, MS, MS-T, HS/MS, TS, HS3, Reserve.
- Regulated Connection Capacity fees (from small commercial up to 10 MVA walk-in stations).
- Annual Fee Billing Schedule: Monthly accrual (1/12th) vs. Annual lump-sum in December (Month 12).
- Commodity supplier markup toggle (pure regulated grid charges vs. all-in electricity supply).
========================================================================================
"""

import streamlit as st

# Safe imports
try:
    from current_model.ui_sandbox.monthly_presets import (
        ENEXIS_2025_GRID_TIERS,
        ENEXIS_2025_CONNECTION_CAPACITIES,
        build_enexis_2025_tariff_dataframe,
        LIANDER_2025_GRID_TIERS,
        LIANDER_2025_CONNECTION_CAPACITIES,
        build_liander_2025_tariff_dataframe
    )
except ImportError:
    from monthly_presets import (
        ENEXIS_2025_GRID_TIERS,
        ENEXIS_2025_CONNECTION_CAPACITIES,
        build_enexis_2025_tariff_dataframe,
        LIANDER_2025_GRID_TIERS,
        LIANDER_2025_CONNECTION_CAPACITIES,
        build_liander_2025_tariff_dataframe
    )


def render_dso_tariff_generator(
    key_prefix: str = "monthly_baseline",
    selected_cur: str = "EUR"
):
    """
    Renders the Dutch Grid Operator Tariff Generator expander and rate application button.
    Populates Table B with official Enexis Netbeheer or Liander 2025 network rates.
    """
    state_tdf_key = f"{key_prefix}_tariff_df"
    state_currency_key = f"{key_prefix}_currency"
    state_fx_key = f"{key_prefix}_fx_rate"
    state_preset_name_key = f"{key_prefix}_preset_name"

    with st.expander(":material/tune: Dutch Grid Operator Tariff Generator (Enexis & Liander 2025)", expanded=(selected_cur == "EUR")):
        st.caption(
            "Select your grid operator, voltage level, and connection capacity. "
            "Choose between monthly accrual or annual year-end settlement in December."
        )
        op_col1, op_col2, op_col3 = st.columns([1.5, 2.0, 2.0])

        with op_col1:
            sel_provider = st.selectbox(
                "Grid Operator",
                options=["enexis", "liander"],
                format_func=lambda x: "Enexis Netbeheer (2025)" if x == "enexis" else "Liander (2025)",
                key=f"{key_prefix}_dso_provider_select"
            )

        with op_col2:
            if sel_provider == "enexis":
                e_tier_keys = list(ENEXIS_2025_GRID_TIERS.keys())
                sel_tier_key = st.selectbox(
                    "Voltage Level / Grid Tier",
                    options=e_tier_keys,
                    format_func=lambda k: ENEXIS_2025_GRID_TIERS[k]["label"],
                    index=e_tier_keys.index("MS_D") if "MS_D" in e_tier_keys else 0,
                    key=f"{key_prefix}_enex_tier_select"
                )
            else:
                l_tier_keys = list(LIANDER_2025_GRID_TIERS.keys())
                sel_tier_key = st.selectbox(
                    "Voltage Level / Grid Tier",
                    options=l_tier_keys,
                    format_func=lambda k: LIANDER_2025_GRID_TIERS[k]["label"],
                    index=l_tier_keys.index("MS") if "MS" in l_tier_keys else 0,
                    key=f"{key_prefix}_liander_tier_select"
                )

        with op_col3:
            if sel_provider == "enexis":
                e_cap_keys = list(ENEXIS_2025_CONNECTION_CAPACITIES.keys())
                def_cap = ENEXIS_2025_GRID_TIERS[sel_tier_key].get("default_capacity_key", "cap_1750")
                sel_cap_key = st.selectbox(
                    "Connection Capacity",
                    options=e_cap_keys,
                    format_func=lambda k: ENEXIS_2025_CONNECTION_CAPACITIES[k]["label"],
                    index=e_cap_keys.index(def_cap) if def_cap in e_cap_keys else 0,
                    key=f"{key_prefix}_enex_cap_select"
                )
            else:
                l_cap_keys = list(LIANDER_2025_CONNECTION_CAPACITIES.keys())
                def_cap = LIANDER_2025_GRID_TIERS[sel_tier_key].get("default_capacity_key", "cap_630")
                sel_cap_key = st.selectbox(
                    "Connection Capacity",
                    options=l_cap_keys,
                    format_func=lambda k: LIANDER_2025_CONNECTION_CAPACITIES[k]["label"],
                    index=l_cap_keys.index(def_cap) if def_cap in l_cap_keys else 0,
                    key=f"{key_prefix}_liander_cap_select"
                )

        sched_col1, sched_col2 = st.columns(2)
        with sched_col1:
            sel_schedule = st.radio(
                "Annual Fee Billing Schedule",
                options=["monthly", "annual_settlement"],
                format_func=lambda x: "Monthly Accrual (1/12 per month)" if x == "monthly" else "Annual Settlement (Lump-Sum in Dec / Month 12)",
                horizontal=True,
                key=f"{key_prefix}_dso_schedule_radio"
            )
        with sched_col2:
            supply_mode = st.radio(
                "Energy Price Scope",
                options=["pure_grid", "with_supply"],
                format_func=lambda x: "Pure Grid Charges (0.00 €/kWh supply)" if x == "pure_grid" else "Add Supplier Energy Markup (Commodity)",
                horizontal=True,
                key=f"{key_prefix}_dso_supply_mode"
            )

        sup_p = 0.0
        sup_op = 0.0
        if supply_mode == "with_supply":
            s_c1, s_c2 = st.columns(2)
            with s_c1:
                sup_p = st.number_input("Peak Supply Markup (€/kWh)", min_value=0.0, max_value=2.0, value=0.1200, step=0.005, format="%.4f", key=f"{key_prefix}_sup_p")
            with s_c2:
                sup_op = st.number_input("Off-Peak Supply Markup (€/kWh)", min_value=0.0, max_value=2.0, value=0.0800, step=0.005, format="%.4f", key=f"{key_prefix}_sup_op")

        btn_apply_dso, _ = st.columns([2.5, 2.5])
        with btn_apply_dso:
            provider_title = "Enexis Netbeheer" if sel_provider == "enexis" else "Liander"
            if st.button(f":material/sync: Apply {provider_title} 2025 Contract to Table B", key=f"{key_prefix}_btn_apply_dso", use_container_width=True):
                if sel_provider == "enexis":
                    new_t_df = build_enexis_2025_tariff_dataframe(
                        grid_tier_key=sel_tier_key,
                        capacity_key=sel_cap_key,
                        billing_schedule=sel_schedule,
                        supply_markup_peak=sup_p,
                        supply_markup_offpeak=sup_op,
                        tax_rate_pct=21.0
                    )
                    tier_info = ENEXIS_2025_GRID_TIERS.get(sel_tier_key, {})
                    label_text = tier_info.get("voltage_level", sel_tier_key)
                else:
                    new_t_df = build_liander_2025_tariff_dataframe(
                        grid_tier_key=sel_tier_key,
                        capacity_key=sel_cap_key,
                        billing_schedule=sel_schedule,
                        supply_markup_peak=sup_p,
                        supply_markup_offpeak=sup_op,
                        tax_rate_pct=21.0
                    )
                    tier_info = LIANDER_2025_GRID_TIERS.get(sel_tier_key, {})
                    label_text = tier_info.get("voltage_level", sel_tier_key)

                st.session_state[state_tdf_key] = new_t_df
                st.session_state[state_currency_key] = "EUR"
                st.session_state[state_fx_key] = 1.0
                st.session_state[state_preset_name_key] = f"Netherlands {provider_title} 2025 ({label_text})"
                st.rerun()
