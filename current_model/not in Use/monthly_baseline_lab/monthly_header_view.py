"""
========================================================================================
Monthly Baseline Header, Preset Selection & Currency Toolbar
(current_model/ui_sandbox/monthly_header_view.py)
========================================================================================

Description:
------------
Renders Section 1 of the Monthly Baseline & Commercial Tariff Lab:
- Main title header and description.
- 4 Standard Industry Presets (Salentein Pozo 600, Argentine 3-Tier, Enexis 2025, Liander 2025).
- Active preset badge and Reload Active Preset button.
- Currency selection (ARS, EUR, USD, GBP) and live FX conversion controls.
========================================================================================
"""

from typing import Tuple, List
import streamlit as st

# Safe imports
try:
    from current_model.ui_sandbox.monthly_baseline_lab.monthly_presets import (
        get_salentein_pozo600_preset,
        get_3tier_argentine_preset,
        get_netherlands_commercial_preset,
        reload_preset_data,
        get_preset_three_party_entities,
        TOUTierConfig
    )
except ImportError:
    from monthly_presets import (
        get_salentein_pozo600_preset,
        get_3tier_argentine_preset,
        get_netherlands_commercial_preset,
        reload_preset_data,
        get_preset_three_party_entities,
        TOUTierConfig
    )


def render_header_and_presets_toolbar(key_prefix: str = "monthly_baseline") -> Tuple[str, float, str, str, str, str]:
    """
    Renders the top preset buttons, active preset badge, reload button, currency controls,
    and the 3-Party Market Entities (DSO, Supplier, Meetbedrijf) attribution card.
    Returns:
        (currency: str, fx_rate: float, preset_name: str, dso_name: str, supplier_name: str, meter_company_name: str)
    """
    state_cdf_key = f"{key_prefix}_consumption_df"
    state_tdf_key = f"{key_prefix}_tariff_df"
    state_tiers_key = f"{key_prefix}_tou_tiers"
    state_currency_key = f"{key_prefix}_currency"
    state_fx_key = f"{key_prefix}_fx_rate"
    state_preset_name_key = f"{key_prefix}_preset_name"
    state_dso_key = f"{key_prefix}_dso_name"
    state_supplier_key = f"{key_prefix}_supplier_name"
    state_meter_co_key = f"{key_prefix}_meter_company_name"
    state_meter_fee_key = f"{key_prefix}_meter_fee"

    currency: str = st.session_state.get(state_currency_key, "EUR")
    fx_rate: float = float(st.session_state.get(state_fx_key, 1.0))
    preset_name: str = st.session_state.get(state_preset_name_key, "Standard Contract")

    # Initialize 3-Party Entities if not present
    if state_dso_key not in st.session_state:
        dso_def, supp_def, meter_def, fee_def = get_preset_three_party_entities(preset_name)
        st.session_state[state_dso_key] = dso_def
        st.session_state[state_supplier_key] = supp_def
        st.session_state[state_meter_co_key] = meter_def
        st.session_state[state_meter_fee_key] = fee_def

    # Header Title
    st.markdown("## :material/science: Monthly Baseline & Commercial Tariff Laboratory")

    # 4 Standard Presets Toolbar
    pcol1, pcol2, pcol3, pcol4 = st.columns(4)

    with pcol1:
        if st.button(":material/download: Salentein Pozo 600", key=f"{key_prefix}_btn_salentein", use_container_width=True):
            c_s, t_s, tiers_s, cur_s, fx_s, name_s = get_salentein_pozo600_preset()
            dso_s, supp_s, meter_s, fee_s = get_preset_three_party_entities(name_s)
            st.session_state[state_cdf_key] = c_s
            st.session_state[state_tdf_key] = t_s
            st.session_state[state_tiers_key] = tiers_s
            st.session_state[state_currency_key] = cur_s
            st.session_state[state_fx_key] = fx_s
            st.session_state[state_preset_name_key] = name_s
            st.session_state[state_dso_key] = dso_s
            st.session_state[state_supplier_key] = supp_s
            st.session_state[state_meter_co_key] = meter_s
            st.session_state[state_meter_fee_key] = fee_s
            st.rerun()

    with pcol2:
        if st.button(":material/factory: Argentine 3-Tier", key=f"{key_prefix}_btn_3tier", use_container_width=True):
            c_3, t_3, tiers_3, cur_3, fx_3, name_3 = get_3tier_argentine_preset()
            dso_3, supp_3, meter_3, fee_3 = get_preset_three_party_entities(name_3)
            st.session_state[state_cdf_key] = c_3
            st.session_state[state_tdf_key] = t_3
            st.session_state[state_tiers_key] = tiers_3
            st.session_state[state_currency_key] = cur_3
            st.session_state[state_fx_key] = fx_3
            st.session_state[state_preset_name_key] = name_3
            st.session_state[state_dso_key] = dso_3
            st.session_state[state_supplier_key] = supp_3
            st.session_state[state_meter_co_key] = meter_3
            st.session_state[state_meter_fee_key] = fee_3
            st.rerun()

    with pcol3:
        if st.button(":material/bolt: Enexis 2025 (MS-D)", key=f"{key_prefix}_btn_nl", use_container_width=True):
            c_n, t_n, tiers_n, cur_n, fx_n, name_n = get_netherlands_commercial_preset(provider="enexis")
            dso_n, supp_n, meter_n, fee_n = get_preset_three_party_entities(name_n)
            st.session_state[state_cdf_key] = c_n
            st.session_state[state_tdf_key] = t_n
            st.session_state[state_tiers_key] = tiers_n
            st.session_state[state_currency_key] = cur_n
            st.session_state[state_fx_key] = fx_n
            st.session_state[state_preset_name_key] = name_n
            st.session_state[state_dso_key] = dso_n
            st.session_state[state_supplier_key] = supp_n
            st.session_state[state_meter_co_key] = meter_n
            st.session_state[state_meter_fee_key] = fee_n
            st.rerun()

    with pcol4:
        if st.button(":material/electric_bolt: Liander 2025 (MS)", key=f"{key_prefix}_btn_liander", use_container_width=True):
            c_l, t_l, tiers_l, cur_l, fx_l, name_l = get_netherlands_commercial_preset(provider="liander")
            dso_l, supp_l, meter_l, fee_l = get_preset_three_party_entities(name_l)
            st.session_state[state_cdf_key] = c_l
            st.session_state[state_tdf_key] = t_l
            st.session_state[state_tiers_key] = tiers_l
            st.session_state[state_currency_key] = cur_l
            st.session_state[state_fx_key] = fx_l
            st.session_state[state_preset_name_key] = name_l
            st.session_state[state_dso_key] = dso_l
            st.session_state[state_supplier_key] = supp_l
            st.session_state[state_meter_co_key] = meter_l
            st.session_state[state_meter_fee_key] = fee_l
            st.rerun()

    # Active preset status and reload button
    bar_info, bar_reload = st.columns([3.2, 1.8])
    with bar_info:
        st.info(f":material/bookmark: Active Preset: **{preset_name}**", icon=":material/tune:")
    with bar_reload:
        if st.button(
            ":material/restart_alt: Reload Active Preset",
            key=f"{key_prefix}_btn_reload_active",
            use_container_width=True,
            help="Reset consumption volumes, tariff rates, and TOU tiers back to the clean initial preset"
        ):
            c_re, t_re, tiers_re, cur_re, fx_re, name_re = reload_preset_data(preset_name)
            dso_re, supp_re, meter_re, fee_re = get_preset_three_party_entities(name_re)
            st.session_state[state_cdf_key] = c_re
            st.session_state[state_tdf_key] = t_re
            st.session_state[state_tiers_key] = tiers_re
            st.session_state[state_currency_key] = cur_re
            st.session_state[state_fx_key] = fx_re
            st.session_state[state_preset_name_key] = name_re
            st.session_state[state_dso_key] = dso_re
            st.session_state[state_supplier_key] = supp_re
            st.session_state[state_meter_co_key] = meter_re
            st.session_state[state_meter_fee_key] = fee_re
            st.rerun()

    # Currency & FX Conversion Controls
    with st.container(border=True):
        cur_col1, cur_col2, cur_col3 = st.columns([1.5, 1.5, 3.0])
        with cur_col1:
            prev_cur = st.session_state.get(state_currency_key, currency)
            selected_cur = st.selectbox(
                "Contract Currency",
                options=["ARS", "EUR", "USD", "GBP"],
                index=0 if currency == "ARS" else (1 if currency == "EUR" else (2 if currency == "USD" else 3)),
                key=f"{key_prefix}_select_currency"
            )
            # If currency was changed, update sensible default FX rate
            if selected_cur != prev_cur:
                st.session_state[state_currency_key] = selected_cur
                if selected_cur == "EUR":
                    st.session_state[state_fx_key] = 1.0
                elif selected_cur == "ARS":
                    st.session_state[state_fx_key] = 1300.0
                elif selected_cur == "USD":
                    st.session_state[state_fx_key] = 1.08
                elif selected_cur == "GBP":
                    st.session_state[state_fx_key] = 0.86
                st.rerun()

        with cur_col2:
            is_eur = (selected_cur == "EUR")
            if is_eur:
                st.session_state[state_fx_key] = 1.0
                input_fx = 1.0
                st.text_input(
                    f"Exchange Rate ({selected_cur} / EUR)",
                    value="1.0000 (Direct €)",
                    disabled=True,
                    help="1 EUR = 1 EUR. Contract rates in Table B are directly evaluated in Euro without currency conversion."
                )
            else:
                curr_fx_val = float(st.session_state.get(state_fx_key, fx_rate))
                input_fx = st.number_input(
                    f"Exchange Rate ({selected_cur} / EUR)",
                    min_value=0.0001,
                    max_value=100000.0,
                    value=curr_fx_val,
                    step=10.0 if selected_cur == "ARS" else 0.05,
                    format="%.4f",
                    help=f"Rates in {selected_cur} are divided by this exchange rate to calculate Euro (€) totals.",
                    key=f"{key_prefix}_num_fx"
                )
                st.session_state[state_fx_key] = input_fx
        with cur_col3:
            if is_eur:
                st.caption("Reporting Currency: **EUR (€)**  \nExchange rate is locked at `1.0000` (1 EUR = 1 EUR). Contract rates in Table B are directly evaluated in Euro without foreign currency division.")
            else:
                st.caption(f"Reporting Currency: **EUR (€)**  \nContract rates in `{selected_cur}` are converted to Euro (€) using: `Cost_EUR = Cost_{selected_cur} / {input_fx:.2f}`.")

    # 3-Party Market Entities & Contract Attribution Card
    with st.container(border=True):
        st.markdown("#### :material/account_balance: Market Entities & Contract Attribution (Unbundled 3-Party Model)")
        st.caption(
            "Under liberalized commercial energy market structures, electricity supply is legally unbundled across 3 distinct entities: "
            "the regulated **Distribution Network Operator (DSO)**, the **Energy Commodity Supplier**, and the **Certified Meter Company (Meetbedrijf)**."
        )
        col_m1, col_m2, col_m3 = st.columns(3)
        with col_m1:
            st.markdown("**:material/account_tree: 1. Regulated Grid Operator (DSO)**")
            dso_val = st.text_input(
                "Grid Operator / Netbeheerder",
                value=st.session_state.get(state_dso_key, "Liander Netbeheer B.V."),
                key=f"{key_prefix}_input_dso_name",
                help="Regulated monopoly operator for grid transport capacity, peak demand, and physical connection."
            )
            st.session_state[state_dso_key] = dso_val
            st.caption("Charges: Base Standing Fee, Contracted kW Capacity, Peak Demand kW, Limit Overload Penalties.")

        with col_m2:
            st.markdown("**:material/storefront: 2. Energy Commodity Supplier**")
            supp_val = st.text_input(
                "Energy Supplier / Leverancier",
                value=st.session_state.get(state_supplier_key, "Eneco Zakelijk"),
                key=f"{key_prefix}_input_supplier_name",
                help="Commercial supplier delivering physical electricity and billing Time-of-Use active energy consumption."
            )
            st.session_state[state_supplier_key] = supp_val
            st.caption("Charges: Time-of-Use active energy commodity rates (Pico/Resto/Valle or Piek/Dal) per kWh.")

        with col_m3:
            st.markdown("**:material/speed: 3. Certified Meter Company (Meetbedrijf)**")
            meter_co_val = st.text_input(
                "Meter Company / Meetbedrijf",
                value=st.session_state.get(state_meter_co_key, "Fudura B.V."),
                key=f"{key_prefix}_input_meter_co_name",
                help="Independent accredited meter company providing telemetry, interval data logging, and physical meters."
            )
            st.session_state[state_meter_co_key] = meter_co_val

            curr_fee_val = float(st.session_state.get(state_meter_fee_key, 75.0 if currency == "EUR" else 0.0))
            meter_fee_val = st.number_input(
                f"Monthly Telemetry & Meter Fee ({currency}/month)",
                min_value=0.0,
                max_value=100000.0,
                value=curr_fee_val,
                step=5.0 if currency == "EUR" else 100.0,
                format="%.2f",
                key=f"{key_prefix}_input_meter_fee",
                help="Fixed monthly metering operator fee for certified telemetry, interval data logging, and meter rental."
            )
            if abs(meter_fee_val - curr_fee_val) > 1e-4:
                st.session_state[state_meter_fee_key] = meter_fee_val
                if state_tdf_key in st.session_state:
                    tdf = st.session_state[state_tdf_key].copy()
                    tdf["metering_fee"] = meter_fee_val
                    st.session_state[state_tdf_key] = tdf
                    st.rerun()
            st.caption("Charges: Dedicated calibrated telemetry, interval data collection, and physical meter equipment.")

    st.markdown("---")
    return selected_cur, input_fx, preset_name, dso_val, supp_val, meter_co_val
