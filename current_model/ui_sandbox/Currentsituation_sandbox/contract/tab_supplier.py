"""
========================================================================================
Sub-Tab 2: Energy Retailer (Supplier) (contract/tab_supplier.py)
========================================================================================

Description:
------------
Renders the dedicated Commercial Energy Supply Contract view:
  1. Retailer selection & 3-way commercial pricing model toolbar:
     - Fixed Dual Rate (HT/NT)
     - Fixed Single Rate (24/7 Flat Rate)
     - Dynamic Day-Ahead (EPEX Spot NL + Markup)
  2. Encapsulated form (st.form) for numerical rate parameters.
  3. Isolated Supplier Performance & Cost Analysis:
     - 4 executive KPI cards (Pure Supplier Total, Effective Rate, Volume Split, Model Delta).
     - Visual Tariff Benchmark (bar chart) & Diurnal / Dynamic correlation figure.
     - Pure Supplier 12-Month Settlement Statement table.
========================================================================================
"""

from typing import Tuple, Dict, Any, List
import streamlit as st
import numpy as np
import pandas as pd

from current_model.ui.common.cards import render_kpi_card
from ui_sandbox.Currentsituation_sandbox.engine.config_and_models import (
    LoadSeries2025,
    SupplierTariff,
    PricingMode,
)
from ui_sandbox.Currentsituation_sandbox.engine.tariff_defaults_2025 import (
    SUPPLIER_CATALOG_2025,
)
from ui_sandbox.Currentsituation_sandbox.engine.commercial_accounting import (
    align_spot_prices_amsterdam_2025,
)
try:
    from ui_sandbox.Currentsituation_sandbox.contract.charts import (
        create_supplier_benchmark_figure,
        create_dynamic_price_consumption_figure,
        create_tou_schedule_diurnal_figure,
    )
except (ImportError, AttributeError):
    try:
        from .charts import (
            create_supplier_benchmark_figure,
            create_dynamic_price_consumption_figure,
            create_tou_schedule_diurnal_figure,
        )
    except (ImportError, AttributeError):
        from contract.charts import (
            create_supplier_benchmark_figure,
            create_dynamic_price_consumption_figure,
            create_tou_schedule_diurnal_figure,
        )


def render_supplier_tab(
    load_series: LoadSeries2025,
    key_prefix: str = "currsit_contract"
) -> Tuple[SupplierTariff, float, List[Dict[str, Any]]]:
    """
    Renders the complete Energy Retailer (Supplier) tab with toolbar, form parameters,
    isolated KPI cards, benchmark charts, and 12-month settlement table.
    """
    st.markdown("##### Commercial Energy Supply Contract (Commodity Rates & Retail Pricing)")

    # Determine Profile Duration in Actual Days
    actual_profile_days = 365.0
    if "active_csv_df" in st.session_state and isinstance(st.session_state["active_csv_df"], pd.DataFrame):
        df_active = st.session_state["active_csv_df"]
        t_col_cand = "timestamp" if "timestamp" in df_active.columns else (df_active.columns[0] if "time" in str(df_active.columns[0]).lower() else None)
        if t_col_cand and t_col_cand in df_active.columns:
            try:
                ts_parsed = pd.to_datetime(df_active[t_col_cand], errors="coerce").dropna()
                if len(ts_parsed) > 1:
                    dur_d = (ts_parsed.max() - ts_parsed.min()).total_seconds() / 86400.0
                    if dur_d > 0.5:
                        actual_profile_days = float(dur_d)
            except Exception:
                pass
    elif getattr(load_series, "duration_days", None):
        actual_profile_days = float(load_series.duration_days)

    # 1. Pre-Selection Toolbar (Outside the Form)
    col_tb_supp, col_tb_mode = st.columns([1.5, 2.5])
    with col_tb_supp:
        supplier_options = list(SUPPLIER_CATALOG_2025.keys()) + ["Custom Energy Retailer"]
        selected_supplier_name = st.selectbox(
            "Energy Retailer (Supplier):",
            options=supplier_options,
            index=0,
            key=f"{key_prefix}_supp_name_select"
        )

    MODEL_DUAL = "Fixed Dual Rate (HT/NT)"
    MODEL_SINGLE = "Fixed Single Rate (24/7 Flat Rate)"
    MODEL_DYNAMIC = "Dynamic Day-Ahead (EPEX Spot NL + Markup)"
    model_options = [MODEL_DUAL, MODEL_SINGLE, MODEL_DYNAMIC]

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
        selected_model_type = st.radio(
            "Contract Pricing Model:",
            options=model_options,
            index=def_model_idx,
            horizontal=True,
            key=f"{key_prefix}_supp_model_radio_{selected_supplier_name}"
        )

    # Derive initial defaults matching the selected supplier & model
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

    # Session state buffering for form values
    supp_state_key = f"{key_prefix}_supp_form_vals"
    if supp_state_key not in st.session_state:
        st.session_state[supp_state_key] = {}

    preset_hash = f"{selected_supplier_name}_{selected_model_type}"
    last_preset = st.session_state[supp_state_key].get("_preset_hash")
    if last_preset != preset_hash:
        st.session_state[supp_state_key] = {
            "_preset_hash": preset_hash,
            "base_fee": float(prod_data.get("base_fee_annual", 180.00)),
            "green_surcharge": float(prod_data.get("green_surcharge_kwh", 0.0030)),
            "ht_rate": float(prod_data.get("rate_peak_kwh", 0.1340)),
            "nt_rate": float(prod_data.get("rate_offpeak_kwh", 0.1180)),
            "single_rate": float(prod_data.get("fixed_rate_kwh", 0.1250)),
            "supplier_margin": float(prod_data.get("supplier_margin_kwh", 0.0075)),
            "procure_fee": float(prod_data.get("procurement_fee_kwh", 0.0015)),
            "weekend_offpeak": True,
        }

    curr_vals = st.session_state[supp_state_key]

    # Dynamic session state key for Supplier TOU rates matrix
    state_supp_tou_key = f"{key_prefix}_supp_tou_df_{selected_supplier_name}_{selected_model_type}"
    if state_supp_tou_key not in st.session_state or last_preset != preset_hash:
        default_supp_ht = float(curr_vals.get("ht_rate", 0.1340))
        default_supp_nt = float(curr_vals.get("nt_rate", 0.1180))
        st.session_state[state_supp_tou_key] = pd.DataFrame([
            {"name": "High Tariff HT (Daytime)", "rate": default_supp_ht, "start_time": "07:00", "end_time": "23:00"},
            {"name": "Off-Peak NT (Night & Weekend)", "rate": default_supp_nt, "start_time": "23:00", "end_time": "07:00"}
        ])

    # 2. Form for Numerical Parameters
    with st.form(key=f"{key_prefix}_retailer_form"):
        col_f_base, col_f_green = st.columns(2)
        with col_f_base:
            supp_base = st.number_input(
                "Retailer Standing Fee (€/year):",
                min_value=0.0,
                value=float(curr_vals["base_fee"]),
                step=15.0,
                help="Standing administrative supply fee per year excluding VAT"
            )
        with col_f_green:
            green_surcharge = st.number_input(
                "Green Power Surcharge (€/kWh):",
                min_value=0.0,
                value=float(curr_vals["green_surcharge"]),
                format="%.4f",
                step=0.0005,
                help="Guarantee of Origin surcharge for renewable electricity"
            )

        # Contextual Fields by Selected Model
        edited_supp_tou = None
        supp_weekend_offpeak = True
        ht_start_hour_supp = 7
        ht_end_hour_supp = 23

        if selected_model_type == MODEL_DUAL:
            active_pricing_mode = PricingMode.FIXED
            is_dual_rate = True
            supp_margin = 0.0
            procure_fee = 0.0

            st.markdown("###### :material/schedule: Time-of-Use Electricity Rates (Working Hours vs. Off-Peak)")
            st.caption("Define commodity rate windows. The table supports direct editing of rates and hours:")

            edited_supp_tou = st.data_editor(
                st.session_state[state_supp_tou_key],
                num_rows="dynamic",
                use_container_width=True,
                column_config={
                    "name": st.column_config.TextColumn("Tariff Name", required=True),
                    "rate": st.column_config.NumberColumn(
                        "Rate (€/kWh)",
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
                "Treat Weekends as Off-Peak (Apply Lowest Tariff)",
                value=bool(curr_vals.get("weekend_offpeak", True)),
                key=f"{key_prefix}_supp_weekend_offpeak",
                help="Apply the off-peak tariff (NT) throughout the weekend."
            )

            current_matrix = edited_supp_tou if (edited_supp_tou is not None and not edited_supp_tou.empty) else st.session_state[state_supp_tou_key]
            fixed_rate_ht = float(curr_vals["ht_rate"])
            fixed_rate_nt = float(curr_vals["nt_rate"])

            if current_matrix is not None and not current_matrix.empty:
                rows = current_matrix.to_dict(orient="records")
                for r in rows:
                    r_name = str(r.get("name", "")).lower()
                    r_rate = float(r.get("rate", fixed_rate_ht))
                    if any(k in r_name for k in ["high", "normaal", "peak", "ht", "hoch", "daytime", "working"]):
                        fixed_rate_ht = r_rate
                        try:
                            s_str = str(r.get("start_time", "07:00")).split(":")[0]
                            e_str = str(r.get("end_time", "23:00")).split(":")[0]
                            ht_start_hour_supp = int(s_str)
                            ht_end_hour_supp = int(e_str)
                        except Exception:
                            pass
                    elif any(k in r_name for k in ["off", "dal", "laag", "nt", "niedrig", "night", "weekend"]):
                        fixed_rate_nt = r_rate

            fixed_rate_val = fixed_rate_ht

        elif selected_model_type == MODEL_SINGLE:
            active_pricing_mode = PricingMode.FIXED
            is_dual_rate = False
            supp_margin = 0.0
            procure_fee = 0.0

            fixed_rate_val = st.number_input(
                "Uniform Fixed Rate (€/kWh) – 24/7 Flat Rate:",
                min_value=0.0,
                value=float(curr_vals["single_rate"]),
                format="%.4f",
                step=0.0020,
                help="Uniform fixed electricity supply rate per active kWh across all hours"
            )
            fixed_rate_ht = fixed_rate_val
            fixed_rate_nt = fixed_rate_val

        else:  # MODEL_DYNAMIC
            active_pricing_mode = PricingMode.DYNAMIC
            is_dual_rate = False
            fixed_rate_val = 0.1250
            fixed_rate_ht = 0.1340
            fixed_rate_nt = 0.1180

            col_dyn1, col_dyn2 = st.columns(2)
            with col_dyn1:
                supp_margin = st.number_input(
                    "Supplier Retail Markup (€/kWh):",
                    min_value=0.0,
                    value=float(curr_vals["supplier_margin"]),
                    format="%.4f",
                    step=0.0005,
                    help="Retail markup on top of EPEX Spot Day-Ahead wholesale price"
                )
            with col_dyn2:
                procure_fee = st.number_input(
                    "Procurement / Imbalance Fee (€/kWh):",
                    min_value=0.0,
                    value=float(curr_vals["procure_fee"]),
                    format="%.4f",
                    step=0.0005,
                    help="Procurement and grid balancing fee per kWh"
                )

        form_submitted = st.form_submit_button(
            "Apply Provider Tariff & Calculate",
            type="primary",
            icon=":material/calculate:"
        )

    if form_submitted:
        st.session_state[supp_state_key]["base_fee"] = supp_base
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

    st.markdown("---")

    # 3. Isolated Supplier Accounting & 2-Way Evaluation Mode
    st.markdown("##### :material/payments: Isolated Supplier Performance & Cost Analysis")

    col_eval_mode, col_eval_badge = st.columns([2.5, 1.5])
    with col_eval_mode:
        eval_mode = st.radio(
            "Evaluation Horizon:",
            options=[
                f"Actual Measured Period ({actual_profile_days:.0f} Days)",
                "Annualized Projection (365 Days)"
            ],
            index=0,
            horizontal=True,
            key=f"{key_prefix}_supplier_eval_horizon_radio"
        )

    is_actual_horizon = "Actual Measured" in eval_mode

    with col_eval_badge:
        if is_actual_horizon:
            day_scale = actual_profile_days / 365.0
            st.caption(
                f":material/event_available: Pro-rata standing fee: "
                f"€ {supp_base * day_scale:,.2f} ({actual_profile_days:.0f}/365 days)"
            )
        else:
            day_scale = 1.0
            annual_scaling_factor = 365.0 / max(1.0, actual_profile_days)
            if actual_profile_days < 360:
                st.info(
                    f":material/info: Scaled by {annual_scaling_factor:.2f}x to represent 365 days.",
                    icon=":material/info:"
                )

    total_kwh = float(load_series.total_energy_kwh)

    ts = load_series.timestamps
    if selected_model_type == MODEL_DUAL:
        if supp_weekend_offpeak:
            day_filter = (ts.dayofweek < 5)
        else:
            day_filter = np.ones(len(ts), dtype=bool)

        if ht_start_hour_supp <= ht_end_hour_supp:
            hour_filter = (ts.hour >= ht_start_hour_supp) & (ts.hour < ht_end_hour_supp)
        else:
            hour_filter = (ts.hour >= ht_start_hour_supp) | (ts.hour < ht_end_hour_supp)

        ht_mask = np.asarray(day_filter & hour_filter, dtype=bool)
    else:
        ht_mask = load_series.is_peak_tou

    ht_kwh = float(np.sum(load_series.energy_kwh[ht_mask]))
    nt_kwh = float(np.sum(load_series.energy_kwh[~ht_mask]))

    temp_spot_tariff = SupplierTariff(
        supplier_name=selected_supplier_name,
        pricing_mode=PricingMode.DYNAMIC,
        tariff_product_name="Spot Temp",
        base_fee_annual=supp_base,
        supplier_margin_kwh=supp_margin if selected_model_type == MODEL_DYNAMIC else 0.0070,
        procurement_fee_kwh=procure_fee if selected_model_type == MODEL_DYNAMIC else 0.0015,
        green_certificate_surcharge_kwh=green_surcharge,
        spot_default_fallback_rate=0.1200
    )
    spot_prices = align_spot_prices_amsterdam_2025(load_series, temp_spot_tariff)

    surcharge_kwh = procure_fee + green_surcharge
    if selected_model_type == MODEL_DUAL:
        active_energy_cost = (ht_kwh * fixed_rate_ht) + (nt_kwh * fixed_rate_nt) + (total_kwh * surcharge_kwh)
    elif selected_model_type == MODEL_SINGLE:
        active_energy_cost = (total_kwh * fixed_rate_val) + (total_kwh * surcharge_kwh)
    else:
        all_in_spot = spot_prices + supp_margin + surcharge_kwh
        active_energy_cost = float(np.sum(load_series.energy_kwh * all_in_spot))

    bench_ht = fixed_rate_ht if selected_model_type == MODEL_DUAL else float(curr_vals.get("ht_rate", 0.1340))
    bench_nt = fixed_rate_nt if selected_model_type == MODEL_DUAL else float(curr_vals.get("nt_rate", 0.1180))
    cost_dual_energy = (ht_kwh * bench_ht) + (nt_kwh * bench_nt) + (total_kwh * surcharge_kwh)

    bench_single = fixed_rate_val if selected_model_type == MODEL_SINGLE else float(curr_vals.get("single_rate", 0.1250))
    cost_single_energy = (total_kwh * bench_single) + (total_kwh * surcharge_kwh)

    bench_dyn_margin = supp_margin if selected_model_type == MODEL_DYNAMIC else 0.0070
    bench_dyn_procure = procure_fee if selected_model_type == MODEL_DYNAMIC else 0.0015
    dyn_all_in = spot_prices + bench_dyn_margin + bench_dyn_procure + green_surcharge
    cost_dynamic_energy = float(np.sum(load_series.energy_kwh * dyn_all_in))

    if is_actual_horizon:
        horizon_kwh = total_kwh
        horizon_ht_kwh = ht_kwh
        horizon_nt_kwh = nt_kwh
        base_fee_evaluated = supp_base * (actual_profile_days / 365.0)
        evaluated_energy_cost = active_energy_cost
        bench_total_dual = cost_dual_energy + base_fee_evaluated
        bench_total_single = cost_single_energy + base_fee_evaluated
        bench_total_dynamic = cost_dynamic_energy + base_fee_evaluated
    else:
        scale_fac = 365.0 / max(1.0, actual_profile_days)
        horizon_kwh = total_kwh * scale_fac
        horizon_ht_kwh = ht_kwh * scale_fac
        horizon_nt_kwh = nt_kwh * scale_fac
        base_fee_evaluated = supp_base
        evaluated_energy_cost = active_energy_cost * scale_fac
        bench_total_dual = (cost_dual_energy * scale_fac) + base_fee_evaluated
        bench_total_single = (cost_single_energy * scale_fac) + base_fee_evaluated
        bench_total_dynamic = (cost_dynamic_energy * scale_fac) + base_fee_evaluated

    supplier_net_total = evaluated_energy_cost + base_fee_evaluated
    effective_commodity_rate = supplier_net_total / max(1.0, horizon_kwh)

    if selected_model_type == MODEL_DYNAMIC:
        alt_model_name = "Fixed Dual Rate"
        alt_cost = bench_total_dual
    else:
        alt_model_name = "Dynamic Day-Ahead"
        alt_cost = bench_total_dynamic

    delta_eur = supplier_net_total - alt_cost
    delta_pct = (delta_eur / max(1.0, alt_cost)) * 100.0

    # 4 Executive KPI Cards
    col_kpi_s1, col_kpi_s2, col_kpi_s3, col_kpi_s4 = st.columns(4)
    with col_kpi_s1:
        render_kpi_card(
            title=":material/receipt_long: Pure Supplier Total",
            value=f"€ {supplier_net_total:,.2f}",
            subtext=f"Energy: € {evaluated_energy_cost:,.2f} | Base: € {base_fee_evaluated:,.2f}",
            status="default"
        )
    with col_kpi_s2:
        render_kpi_card(
            title=":material/price_change: Effective Commodity Rate",
            value=f"€ {effective_commodity_rate:.4f} / kWh",
            subtext=f"Commodity only ({effective_commodity_rate * 100.0:.2f} ct/kWh)",
            status="default"
        )
    with col_kpi_s3:
        ht_share = (horizon_ht_kwh / max(1.0, horizon_kwh)) * 100.0
        nt_share = (horizon_nt_kwh / max(1.0, horizon_kwh)) * 100.0
        render_kpi_card(
            title=":material/contrast: HT / NT Volume Split",
            value=f"HT: {ht_share:.1f}% | NT: {nt_share:.1f}%",
            subtext=f"HT: {horizon_ht_kwh:,.0f} kWh | NT: {horizon_nt_kwh:,.0f} kWh",
            status="default"
        )
    with col_kpi_s4:
        if abs(delta_eur) < 1.0:
            delta_str = "Parity (±0 €)"
            d_status = "ok"
        elif delta_eur < 0:
            delta_str = f"-€ {abs(delta_eur):,.0f} ({delta_pct:.1f}%)"
            d_status = "ok"
        else:
            delta_str = f"+€ {delta_eur:,.0f} (+{delta_pct:.1f}%)"
            d_status = "alert"

        render_kpi_card(
            title=f":material/compare_arrows: vs. {alt_model_name}",
            value=delta_str,
            subtext=f"Alt Cost: € {alt_cost:,.0f} net",
            status=d_status
        )

    # 4. Compact Visualizations & Itemized Settlement Table (2 Columns)
    col_vis_left, col_vis_right = st.columns([1.1, 1.0])

    with col_vis_left:
        st.markdown("###### :material/insights: Visual Tariff Benchmark & Load Schedule")

        bench_dict = {
            "Fixed Dual Rate (HT/NT)": bench_total_dual,
            "Fixed Single Rate": bench_total_single,
            "Dynamic Day-Ahead": bench_total_dynamic,
        }
        fig_bench = create_supplier_benchmark_figure(bench_dict)
        st.plotly_chart(fig_bench, use_container_width=True)

        if selected_model_type == MODEL_DYNAMIC:
            spot_eur_mwh = spot_prices * 1000.0
            fig_dyn = create_dynamic_price_consumption_figure(
                timestamps=load_series.timestamps,
                power_kw=load_series.power_kw,
                spot_prices_eur_mwh=spot_eur_mwh,
                title_suffix=f"({actual_profile_days:.0f} Days)"
            )
            st.plotly_chart(fig_dyn, use_container_width=True)
        else:
            fig_diurnal = create_tou_schedule_diurnal_figure(
                load=load_series,
                ht_start_hour=ht_start_hour_supp,
                ht_end_hour=ht_end_hour_supp,
                ht_rate_label=f"High Tariff HT ({fixed_rate_ht:.4f} €/kWh)",
                nt_rate_label=f"Off-Peak NT ({fixed_rate_nt:.4f} €/kWh)"
            )
            st.plotly_chart(fig_diurnal, use_container_width=True)

    with col_vis_right:
        st.markdown("###### :material/table_chart: Pure Supplier Settlement Statement")

        billing_rows = []
        month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        for m in range(1, 13):
            m_mask = (load_series.month_indices == m)
            m_kwh = float(np.sum(load_series.energy_kwh[m_mask]))
            if m_kwh <= 0.0:
                continue

            m_ht_kwh = float(np.sum(load_series.energy_kwh[m_mask & ht_mask]))
            m_nt_kwh = float(np.sum(load_series.energy_kwh[m_mask & ~ht_mask]))

            if selected_model_type == MODEL_DUAL:
                m_ecost = (m_ht_kwh * fixed_rate_ht) + (m_nt_kwh * fixed_rate_nt) + (m_kwh * surcharge_kwh)
            elif selected_model_type == MODEL_SINGLE:
                m_ecost = (m_kwh * fixed_rate_val) + (m_kwh * surcharge_kwh)
            else:
                m_all_in = spot_prices[m_mask] + supp_margin + surcharge_kwh
                m_ecost = float(np.sum(load_series.energy_kwh[m_mask] * m_all_in))

            if is_actual_horizon:
                m_days = len(np.unique(load_series.timestamps[m_mask].date))
                m_base = supp_base * (m_days / 365.0)
            else:
                m_base = supp_base / 12.0
                m_kwh = m_kwh * scale_fac
                m_ht_kwh = m_ht_kwh * scale_fac
                m_nt_kwh = m_nt_kwh * scale_fac
                m_ecost = m_ecost * scale_fac

            m_total = m_ecost + m_base
            m_eff_rate = m_total / max(1.0, m_kwh)

            billing_rows.append({
                "Period": month_names[m - 1],
                "Total (kWh)": f"{m_kwh:,.0f}",
                "HT (kWh)": f"{m_ht_kwh:,.0f}",
                "NT (kWh)": f"{m_nt_kwh:,.0f}",
                "Energy (€)": f"€ {m_ecost:,.2f}",
                "Base (€)": f"€ {m_base:,.2f}",
                "Supplier Total (€)": f"€ {m_total:,.2f}",
                "Rate (€/kWh)": f"€ {m_eff_rate:.4f}"
            })

        billing_rows.append({
            "Period": "TOTAL",
            "Total (kWh)": f"{horizon_kwh:,.0f}",
            "HT (kWh)": f"{horizon_ht_kwh:,.0f}",
            "NT (kWh)": f"{horizon_nt_kwh:,.0f}",
            "Energy (€)": f"€ {evaluated_energy_cost:,.2f}",
            "Base (€)": f"€ {base_fee_evaluated:,.2f}",
            "Supplier Total (€)": f"€ {supplier_net_total:,.2f}",
            "Rate (€/kWh)": f"€ {effective_commodity_rate:.4f}"
        })

        df_billing = pd.DataFrame(billing_rows)
        st.dataframe(df_billing, use_container_width=True, hide_index=True)

        st.caption(
            ":material/security: Pure supplier view strictly excludes DSO network tariffs, "
            "metering telemetry services, energy taxes and statutory VAT."
        )

    # Build authoritative SupplierTariff model
    supplier_tariff = SupplierTariff(
        supplier_name=selected_supplier_name,
        pricing_mode=active_pricing_mode,
        tariff_product_name=selected_product,
        base_fee_annual=supp_base,
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

    return supplier_tariff, supplier_net_total, billing_rows
