"""
========================================================================================
Sub-Tab 2: Pillar 1 - Energy Supply (Retailer) (contract/tab_supplier.py)
========================================================================================

Implements the standardized 3-Zone layout for Commercial Energy Supply (Retailer) tariffs:
  - Zone A (Left Column, 58%): 1. Contract & Tariff Inputs
    Includes retailer & pricing model selectors (Fixed Dual Rate HT/NT, Fixed Single Rate,
    Dynamic Day-Ahead EPEX Spot), Fixed Standing Fee ({CURR}/month), Procurement & Green
    Certificates (GvO) Surcharge ({CURR}/kWh), and Peak Hours (HT) / Off-Peak Hours (NT)
    or Spot Markup rates.
  - Zone B (Right Column, 42%): 2. Component Bill Calculation (How it Adds Up)
    Renders a standardized Electricity Bill Sub-Ledger showing:
    Line Item | Calculation (Quantity × Rate) | Monthly ({CURR}) | Annual ({CURR})
    concluding with = SUBTOTAL ENERGY SUPPLY (NET).
  - Zone C (Bottom Full Width): 3. Monthly Breakdown & Visual Diagnostics
    Renders the Supplier Benchmark Bar Chart, 24h Diurnal TOU Load Schedule or Spot
    Correlation Chart, and 12-Month Supplier Settlement Statement.
========================================================================================
"""

from typing import Dict, Any, List
import streamlit as st
import pandas as pd
import numpy as np

try:
    from ui_sandbox.Currentsituation_sandbox.engine.config_and_models import (
        SupplierTariff,
        PricingMode,
        LoadSeries2025,
        MeteringTariff,
        LevyConfig,
    )
    from ui_sandbox.Currentsituation_sandbox.engine.tariff_defaults_2025 import (
        SUPPLIER_CATALOG_2025,
    )
    from ui_sandbox.Currentsituation_sandbox.engine.consumption_pipeline import (
        extract_monthly_consumption_records,
    )
    from ui_sandbox.Currentsituation_sandbox.engine.commercial_accounting import (
        calculate_commercial_accounting_2025,
        align_spot_prices_amsterdam_2025,
    )
    from ui_sandbox.Currentsituation_sandbox.contract.charts import (
        create_supplier_benchmark_figure,
        create_dynamic_price_consumption_figure,
        create_tou_schedule_diurnal_figure,
    )
    from ui_sandbox.Currentsituation_sandbox.contract.tab_dso import _render_sub_ledger_html
except ImportError:
    from current_model.ui_sandbox.Currentsituation_sandbox.engine.config_and_models import (
        SupplierTariff,
        PricingMode,
        LoadSeries2025,
        MeteringTariff,
        LevyConfig,
    )
    from current_model.ui_sandbox.Currentsituation_sandbox.engine.tariff_defaults_2025 import (
        SUPPLIER_CATALOG_2025,
    )
    from current_model.ui_sandbox.Currentsituation_sandbox.engine.consumption_pipeline import (
        extract_monthly_consumption_records,
    )
    from current_model.ui_sandbox.Currentsituation_sandbox.engine.commercial_accounting import (
        calculate_commercial_accounting_2025,
        align_spot_prices_amsterdam_2025,
    )
    from current_model.ui_sandbox.Currentsituation_sandbox.contract.charts import (
        create_supplier_benchmark_figure,
        create_dynamic_price_consumption_figure,
        create_tou_schedule_diurnal_figure,
    )
    from current_model.ui_sandbox.Currentsituation_sandbox.contract.tab_dso import _render_sub_ledger_html


def render_supplier_tab(
    load_series: LoadSeries2025,
    key_prefix: str = "currsit_contract",
    is_enabled: bool = True,
    currency_code: str = "EUR",
) -> SupplierTariff:
    """
    Renders Sub-Tab 2: Pillar 1 - Energy Supply (Retailer) using the standardized 3-Zone layout
    and returns the configured SupplierTariff model.
    When is_enabled=False (e.g., Integrated Single-Utility Mode), the tab remains visible and
    accessible, with an informational banner, disabled form inputs, and a grayed-out Zone B sub-ledger.
    """
    status_tag = "" if is_enabled else " `[BYPASSED / GRAYED OUT]`"
    st.markdown(f"#### :material/storefront: Pillar 1: Energy Supply (Retailer) — Commodity Electricity & Surcharges{status_tag}")

    if not is_enabled:
        st.info(
            ":material/visibility_off: **Market Role Bypassed (Integrated Single-Utility Bill):** "
            "Separate Energy Supply (Retailer) is bypassed under the active Market Structure Mode. "
            "All commodity energy charges are bundled directly inside **Pillar 2: Grid Network / Utility (DSO)**. "
            "The form controls and sub-ledger below remain visible in grayed-out state and evaluate to **0.00**.",
            icon=":material/info:"
        )

    MODEL_DUAL = "Fixed Dual Rate (Peak HT / Off-Peak NT)"
    MODEL_SINGLE = "Fixed Single Rate (24/7 Flat)"
    MODEL_DYNAMIC = "Dynamic Day-Ahead (EPEX Spot + Margin)"
    model_options = [MODEL_DUAL, MODEL_SINGLE, MODEL_DYNAMIC]

    col_zone_a, col_zone_b = st.columns([0.58, 0.42], gap="large")

    # ----------------------------------------------------------------------------------
    # Zone A (Left Column, 58%): 1. Contract & Tariff Inputs
    # ----------------------------------------------------------------------------------
    with col_zone_a:
        st.markdown("##### :material/tune: 1. Contract & Tariff Inputs")

        col_tb_supp, col_tb_mode = st.columns([1.4, 2.2])
        with col_tb_supp:
            supplier_options = list(SUPPLIER_CATALOG_2025.keys()) + ["Custom Energy Retailer"]
            selected_supplier_name = st.selectbox(
                "Energy Retailer:",
                options=supplier_options,
                index=0,
                key=f"{key_prefix}_supp_name_select",
                disabled=not is_enabled,
            )

        def_model_idx = 0
        if selected_supplier_name in SUPPLIER_CATALOG_2025:
            supp_prods = SUPPLIER_CATALOG_2025[selected_supplier_name]
            first_prod = list(supp_prods.values())[0]
            if first_prod.get("pricing_mode") == PricingMode.DYNAMIC:
                def_model_idx = 2
            elif first_prod.get("is_dual_rate", False):
                def_model_idx = 0
            else:
                def_model_idx = 1
        elif "tibber" in selected_supplier_name.lower():
            def_model_idx = 2

        with col_tb_mode:
            selected_model_type = st.selectbox(
                "Commodity Pricing Model:",
                options=model_options,
                index=def_model_idx,
                key=f"{key_prefix}_supp_model_select_{selected_supplier_name}",
                disabled=not is_enabled,
            )

        found_prod_key = None
        found_prod_data: Dict[str, Any] = {}
        if selected_supplier_name in SUPPLIER_CATALOG_2025:
            prods = SUPPLIER_CATALOG_2025[selected_supplier_name]
            for p_k, p_v in prods.items():
                if selected_model_type == MODEL_DYNAMIC and p_v.get("pricing_mode") == PricingMode.DYNAMIC:
                    found_prod_key, found_prod_data = p_k, p_v
                    break
                elif selected_model_type == MODEL_DUAL and p_v.get("pricing_mode") == PricingMode.FIXED and p_v.get("is_dual_rate", False):
                    found_prod_key, found_prod_data = p_k, p_v
                    break
                elif selected_model_type == MODEL_SINGLE and p_v.get("pricing_mode") == PricingMode.FIXED and not p_v.get("is_dual_rate", False):
                    found_prod_key, found_prod_data = p_k, p_v
                    break
            if not found_prod_data and prods:
                found_prod_key = list(prods.keys())[0]
                found_prod_data = prods[found_prod_key]

        selected_product = found_prod_key or f"{selected_supplier_name} {selected_model_type}"
        prod_data = found_prod_data

        if prod_data.get("description"):
            st.caption(f":material/info: *{prod_data['description']}*")

        supp_state_key = f"{key_prefix}_supp_form_vals"
        if supp_state_key not in st.session_state:
            st.session_state[supp_state_key] = {}

        preset_hash = f"{selected_supplier_name}_{selected_model_type}"
        last_preset = st.session_state[supp_state_key].get("_preset_hash")
        if last_preset != preset_hash:
            st.session_state[supp_state_key] = {
                "_preset_hash": preset_hash,
                "base_fee_monthly": round(float(prod_data.get("base_fee_annual", 180.00)) / 12.0, 2),
                "green_surcharge": float(prod_data.get("green_surcharge_kwh", 0.0030)),
                "ht_rate": float(prod_data.get("rate_peak_kwh", 0.1340)),
                "nt_rate": float(prod_data.get("rate_offpeak_kwh", 0.1180)),
                "single_rate": float(prod_data.get("fixed_rate_kwh", 0.1250)),
                "supplier_margin": float(prod_data.get("supplier_margin_kwh", 0.0075)),
                "procure_fee": float(prod_data.get("procurement_fee_kwh", 0.0015)),
                "weekend_offpeak": True,
            }

        curr_vals = st.session_state[supp_state_key]

        state_supp_tou_key = f"{key_prefix}_supp_tou_df_{selected_supplier_name}_{selected_model_type}"
        if state_supp_tou_key not in st.session_state or last_preset != preset_hash:
            default_supp_ht = float(curr_vals.get("ht_rate", 0.1340))
            default_supp_nt = float(curr_vals.get("nt_rate", 0.1180))
            st.session_state[state_supp_tou_key] = pd.DataFrame([
                {"name": "Peak Hours (HT)", "rate": default_supp_ht, "start_time": "07:00", "end_time": "23:00"},
                {"name": "Off-Peak Hours (NT)", "rate": default_supp_nt, "start_time": "23:00", "end_time": "07:00"}
            ])

        with st.form(key=f"{key_prefix}_retailer_form"):
            st.markdown("###### A. Standing Fee & Certificate Surcharges")
            col_f_base, col_f_green = st.columns(2)
            with col_f_base:
                supp_base_monthly = st.number_input(
                    f"Fixed Standing Fee ({currency_code}/month):",
                    min_value=0.0,
                    value=float(curr_vals.get("base_fee_monthly", 15.00)),
                    step=2.50,
                    format="%.2f",
                    help=f"Monthly retailer administration and standing fee ({currency_code}/month)",
                    disabled=not is_enabled,
                )
            with col_f_green:
                green_surcharge = st.number_input(
                    f"Green Certificates (GvO) Surcharge ({currency_code}/kWh):",
                    min_value=0.0,
                    value=float(curr_vals["green_surcharge"]),
                    format="%.4f",
                    step=0.0005,
                    help=f"Guarantee of Origin (GvO) renewable electricity surcharge per kWh ({currency_code}/kWh)",
                    disabled=not is_enabled,
                )

            edited_supp_tou = None
            supp_weekend_offpeak = True
            ht_start_hour_supp = 7
            ht_end_hour_supp = 23

            st.markdown(f"###### B. Active Energy Commodity Rates ({currency_code}/kWh)")
            if selected_model_type == MODEL_DUAL:
                active_pricing_mode = PricingMode.FIXED
                is_dual_rate = True
                supp_margin = 0.0
                procure_fee = 0.0

                edited_supp_tou = st.data_editor(
                    st.session_state[state_supp_tou_key],
                    num_rows="dynamic",
                    use_container_width=True,
                    disabled=not is_enabled,
                    column_config={
                        "name": st.column_config.TextColumn("Tariff Window", required=True),
                        "rate": st.column_config.NumberColumn(
                            f"Commodity Rate ({currency_code}/kWh)",
                            format="%.4f",
                            min_value=0.0,
                            step=0.0001,
                            required=True
                        ),
                        "start_time": st.column_config.TextColumn("Start Time (HH:MM)", required=True),
                        "end_time": st.column_config.TextColumn("End Time (HH:MM)", required=True)
                    },
                    key=f"{key_prefix}_supp_tou_editor_{selected_supplier_name}_{selected_model_type}"
                )

                supp_weekend_offpeak = st.checkbox(
                    "Treat Weekends as Off-Peak Hours (NT)",
                    value=bool(curr_vals.get("weekend_offpeak", True)),
                    key=f"{key_prefix}_supp_weekend_offpeak",
                    disabled=not is_enabled,
                )

                current_matrix = edited_supp_tou if (edited_supp_tou is not None and not edited_supp_tou.empty) else st.session_state[state_supp_tou_key]
                fixed_rate_ht = float(curr_vals["ht_rate"])
                fixed_rate_nt = float(curr_vals["nt_rate"])

                if current_matrix is not None and not current_matrix.empty:
                    for r in current_matrix.to_dict(orient="records"):
                        r_name = str(r.get("name", "")).lower()
                        r_rate = float(r.get("rate", fixed_rate_ht))
                        if any(k in r_name for k in ["peak", "ht", "high", "day", "work"]) and "off" not in r_name:
                            fixed_rate_ht = r_rate
                            try:
                                ht_start_hour_supp = int(str(r.get("start_time", "07:00")).split(":")[0])
                                ht_end_hour_supp = int(str(r.get("end_time", "23:00")).split(":")[0])
                            except Exception:
                                pass
                        elif any(k in r_name for k in ["off", "nt", "low", "night", "weekend"]):
                            fixed_rate_nt = r_rate

                fixed_rate_val = fixed_rate_ht

            elif selected_model_type == MODEL_SINGLE:
                active_pricing_mode = PricingMode.FIXED
                is_dual_rate = False
                supp_margin = 0.0
                procure_fee = 0.0

                fixed_rate_val = st.number_input(
                    f"Fixed Single Commodity Rate ({currency_code}/kWh):",
                    min_value=0.0,
                    value=float(curr_vals["single_rate"]),
                    format="%.4f",
                    step=0.0020,
                    disabled=not is_enabled,
                )
                fixed_rate_ht = fixed_rate_val
                fixed_rate_nt = fixed_rate_val

            else:
                active_pricing_mode = PricingMode.DYNAMIC
                is_dual_rate = False
                fixed_rate_val = 0.1250
                fixed_rate_ht = 0.1340
                fixed_rate_nt = 0.1180

                col_dyn1, col_dyn2 = st.columns(2)
                with col_dyn1:
                    supp_margin = st.number_input(
                        f"Retail Margin / Markup ({currency_code}/kWh):",
                        min_value=0.0,
                        value=float(curr_vals["supplier_margin"]),
                        format="%.4f",
                        step=0.0005,
                        help=f"Retailer margin added to hourly EPEX Spot Day-Ahead price ({currency_code}/kWh)",
                        disabled=not is_enabled,
                    )
                with col_dyn2:
                    procure_fee = st.number_input(
                        f"Procurement & Imbalance Fee ({currency_code}/kWh):",
                        min_value=0.0,
                        value=float(curr_vals["procure_fee"]),
                        format="%.4f",
                        step=0.0005,
                        help=f"Balancing and market access procurement fee per kWh ({currency_code}/kWh)",
                        disabled=not is_enabled,
                    )

            form_submitted = st.form_submit_button(
                "Apply Energy Supply Tariff",
                type="primary",
                icon=":material/calculate:",
                use_container_width=True,
                disabled=not is_enabled,
            )

        supp_base_annual = round(supp_base_monthly * 12.0, 2)

        if form_submitted and is_enabled:
            st.session_state[supp_state_key]["base_fee_monthly"] = supp_base_monthly
            st.session_state[supp_state_key]["green_surcharge"] = green_surcharge
            if selected_model_type == MODEL_DUAL:
                if edited_supp_tou is not None and not edited_supp_tou.empty:
                    st.session_state[state_supp_tou_key] = edited_supp_tou
                st.session_state[supp_state_key]["ht_rate"] = fixed_rate_ht
                st.session_state[supp_state_key]["nt_rate"] = fixed_rate_nt
                st.session_state[supp_state_key]["weekend_offpeak"] = supp_weekend_offpeak
            elif selected_model_type == MODEL_SINGLE:
                st.session_state[supp_state_key]["single_rate"] = fixed_rate_val
            else:
                st.session_state[supp_state_key]["supplier_margin"] = supp_margin
                st.session_state[supp_state_key]["procure_fee"] = procure_fee
            st.success(f"Energy Supply tariff updated ({selected_supplier_name})", icon=":material/check_circle:")

    supplier_tariff = SupplierTariff(
        supplier_name=selected_supplier_name,
        pricing_mode=active_pricing_mode,
        tariff_product_name=selected_product,
        base_fee_annual=supp_base_annual,
        fixed_rate_kwh=fixed_rate_val,
        is_dual_rate=is_dual_rate,
        fixed_rate_peak_kwh=fixed_rate_ht,
        fixed_rate_offpeak_kwh=fixed_rate_nt,
        procurement_fee_kwh=procure_fee,
        green_certificate_surcharge_kwh=green_surcharge,
        monthly_variable_rates=prod_data.get("monthly_variable_rates", [0.125] * 12),
        market_price_profile_id="epex_nl_2025",
        supplier_margin_kwh=supp_margin,
        spot_default_fallback_rate=0.1200,
    )

    # Execute engine calculation for Supplier
    monthly_cons = extract_monthly_consumption_records(load_series)
    comm_monthly, comm_summary = calculate_commercial_accounting_2025(
        load=load_series,
        monthly_consumption=monthly_cons,
        supplier_tariff=supplier_tariff,
        metering_tariff=MeteringTariff(annual_flat_fee=0.0),
        levy_config=LevyConfig(statutory_levy_rate_kwh=0.0, annual_tax_reduction=0.0)
    )

    total_kwh = float(load_series.total_energy_kwh)
    ht_kwh = sum(c.peak_tou_kwh for c in monthly_cons)
    nt_kwh = sum(c.offpeak_tou_kwh for c in monthly_cons)

    base_ann = comm_summary["total_supplier_base_annual"]
    base_mo = round(base_ann / 12.0, 2)
    tot_energy_ann = comm_summary["total_supplier_energy_annual"]

    surcharge_rate = procure_fee + green_surcharge
    surcharge_ann = round(total_kwh * surcharge_rate, 2)
    commodity_only_ann = round(tot_energy_ann - surcharge_ann, 2)

    # ----------------------------------------------------------------------------------
    # Zone B (Right Column, 42%): 2. Component Bill Calculation (How it Adds Up)
    # ----------------------------------------------------------------------------------
    with col_zone_b:
        st.markdown("##### :material/receipt_long: 2. Component Bill Calculation (How it Adds Up)")

        ledger_rows: List[Dict[str, str]] = [
            {
                "item": "1.1 Fixed Standing Fee",
                "calc": f"12 mos × {currency_code} {base_mo:,.2f}/mo",
                "monthly": f"{base_mo:,.2f}",
                "annual": f"{base_ann:,.2f}",
            }
        ]

        if is_dual_rate:
            ht_ann = round(ht_kwh * fixed_rate_ht, 2)
            nt_ann = round(commodity_only_ann - ht_ann, 2)
            ledger_rows.append({
                "item": "1.2 Active Energy — Peak Hours (HT)",
                "calc": f"{ht_kwh:,.0f} kWh × {currency_code} {fixed_rate_ht:.4f}/kWh",
                "monthly": f"{ht_ann / 12.0:,.2f}",
                "annual": f"{ht_ann:,.2f}",
            })
            ledger_rows.append({
                "item": "1.3 Active Energy — Off-Peak Hours (NT)",
                "calc": f"{nt_kwh:,.0f} kWh × {currency_code} {fixed_rate_nt:.4f}/kWh",
                "monthly": f"{nt_ann / 12.0:,.2f}",
                "annual": f"{nt_ann:,.2f}",
            })
        elif active_pricing_mode == PricingMode.DYNAMIC:
            eff_spot_rate = commodity_only_ann / max(1.0, total_kwh)
            ledger_rows.append({
                "item": "1.2 Day-Ahead Spot Commodity + Margin",
                "calc": f"{total_kwh:,.0f} kWh × {currency_code} {eff_spot_rate:.4f}/kWh",
                "monthly": f"{commodity_only_ann / 12.0:,.2f}",
                "annual": f"{commodity_only_ann:,.2f}",
            })
        else:
            ledger_rows.append({
                "item": "1.2 Active Energy — Single Flat Rate",
                "calc": f"{total_kwh:,.0f} kWh × {currency_code} {fixed_rate_val:.4f}/kWh",
                "monthly": f"{commodity_only_ann / 12.0:,.2f}",
                "annual": f"{commodity_only_ann:,.2f}",
            })

        ledger_rows.append({
            "item": "1.4 Procurement & Green Certificates (GvO)",
            "calc": f"{total_kwh:,.0f} kWh × {currency_code} {surcharge_rate:.4f}/kWh",
            "monthly": f"{surcharge_ann / 12.0:,.2f}",
            "annual": f"{surcharge_ann:,.2f}",
        })

        subtotal_supp_ann = round(base_ann + tot_energy_ann, 2)
        subtotal_supp_mo = round(subtotal_supp_ann / 12.0, 2)

        st.markdown(
            _render_sub_ledger_html(
                header_title=f"Pillar 1 Sub-Ledger — {selected_supplier_name}",
                rows=ledger_rows,
                subtotal_label="= SUBTOTAL ENERGY SUPPLY (NET)",
                subtotal_monthly_eur=subtotal_supp_mo,
                subtotal_annual_eur=subtotal_supp_ann,
                accent_color="#38bdf8",
                currency_code=currency_code,
                is_enabled=is_enabled,
            ),
            unsafe_allow_html=True
        )

        eff_supp_rate = (0.0 if not is_enabled else subtotal_supp_ann) / max(1.0, total_kwh)
        ht_share = (ht_kwh / max(1.0, total_kwh)) * 100.0
        nt_share = (nt_kwh / max(1.0, total_kwh)) * 100.0
        st.info(
            f":material/price_change: **Effective Supply Rate:** {currency_code} {eff_supp_rate:.4f}/kWh | "
            f"**Volume Split:** Peak Hours (HT) {ht_share:.1f}% ({ht_kwh:,.0f} kWh) / "
            f"Off-Peak Hours (NT) {nt_share:.1f}% ({nt_kwh:,.0f} kWh).",
            icon=":material/info:"
        )

    # ----------------------------------------------------------------------------------
    # Zone C (Bottom Full Width): 3. Monthly Breakdown & Visual Diagnostics
    # ----------------------------------------------------------------------------------
    st.markdown("---")
    with st.expander(":material/analytics: 3. Monthly Breakdown & Visual Diagnostics (Energy Supply)", expanded=is_enabled):
        spot_prices = align_spot_prices_amsterdam_2025(load_series, supplier_tariff)
        bench_ht = fixed_rate_ht if selected_model_type == MODEL_DUAL else float(curr_vals.get("ht_rate", 0.1340))
        bench_nt = fixed_rate_nt if selected_model_type == MODEL_DUAL else float(curr_vals.get("nt_rate", 0.1180))
        bench_dual = round((ht_kwh * bench_ht) + (nt_kwh * bench_nt) + surcharge_ann + base_ann, 2)

        bench_single_r = fixed_rate_val if selected_model_type == MODEL_SINGLE else float(curr_vals.get("single_rate", 0.1250))
        bench_single = round((total_kwh * bench_single_r) + surcharge_ann + base_ann, 2)

        bench_dyn_m = supp_margin if selected_model_type == MODEL_DYNAMIC else 0.0075
        bench_dyn_p = procure_fee if selected_model_type == MODEL_DYNAMIC else 0.0015
        dyn_all_in = spot_prices + bench_dyn_m + bench_dyn_p + green_surcharge
        bench_dynamic = round(float(np.sum(load_series.energy_kwh * dyn_all_in)) + base_ann, 2)

        col_vis_left, col_vis_right = st.columns([1.1, 1.1], gap="large")
        with col_vis_left:
            bench_dict = {
                "Fixed Dual Rate (HT/NT)": bench_dual if is_enabled else 0.0,
                "Fixed Single Rate": bench_single if is_enabled else 0.0,
                "Dynamic Day-Ahead": bench_dynamic if is_enabled else 0.0,
            }
            fig_bench = create_supplier_benchmark_figure(bench_dict, currency=currency_code)
            st.plotly_chart(fig_bench, use_container_width=True, key=f"{key_prefix}_supp_bench_chart")

            if selected_model_type == MODEL_DYNAMIC:
                spot_eur_mwh = spot_prices * 1000.0
                fig_dyn = create_dynamic_price_consumption_figure(
                    timestamps=load_series.timestamps,
                    power_kw=load_series.power_kw,
                    spot_prices_eur_mwh=spot_eur_mwh,
                    title_suffix="(365 Days)",
                    currency=currency_code
                )
                st.plotly_chart(fig_dyn, use_container_width=True, key=f"{key_prefix}_supp_dyn_chart")
            else:
                fig_diurnal = create_tou_schedule_diurnal_figure(
                    load=load_series,
                    ht_start_hour=ht_start_hour_supp,
                    ht_end_hour=ht_end_hour_supp,
                    ht_rate_label=f"Peak Hours HT ({currency_code} {fixed_rate_ht:.4f}/kWh)",
                    nt_rate_label=f"Off-Peak Hours NT ({currency_code} {fixed_rate_nt:.4f}/kWh)"
                )
                st.plotly_chart(fig_diurnal, use_container_width=True, key=f"{key_prefix}_supp_diurnal_chart")

        with col_vis_right:
            st.markdown("###### 12-Month Energy Supply Settlement Statement")
            month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
            billing_rows = []
            mult = 1.0 if is_enabled else 0.0
            for c_rec, m_res in zip(monthly_cons, comm_monthly):
                m_tot = round((m_res.supplier_energy_cost + m_res.supplier_base_fee) * mult, 2)
                m_rate = m_tot / max(1.0, c_rec.total_kwh)
                billing_rows.append({
                    "Month": month_names[c_rec.month_index - 1],
                    "Total (kWh)": f"{c_rec.total_kwh:,.0f}",
                    "Peak HT (kWh)": f"{c_rec.peak_tou_kwh:,.0f}",
                    "Off-Peak NT (kWh)": f"{c_rec.offpeak_tou_kwh:,.0f}",
                    f"Standing ({currency_code})": f"{m_res.supplier_base_fee * mult:,.2f}",
                    f"Energy & GvO ({currency_code})": f"{m_res.supplier_energy_cost * mult:,.2f}",
                    f"Subtotal Net ({currency_code})": f"{m_tot:,.2f}",
                    f"Rate ({currency_code}/kWh)": f"{m_rate:.4f}"
                })
            st.dataframe(pd.DataFrame(billing_rows), use_container_width=True, hide_index=True)

    return supplier_tariff
