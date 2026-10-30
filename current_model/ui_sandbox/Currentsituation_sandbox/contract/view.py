"""
========================================================================================
Status Quo 2025 Contract & Billing Orchestrator (Currentsituation_sandbox/contract/view.py)
========================================================================================

Modular orchestrator view featuring:
  1. Reference Benchmark Quick-Loader & Market Structure Mode Control Bar
     - Presets:
       * Standard Enexis/Liander Commercial (250 kW)
       * Preset A: Rotterdam / Dutch WKO Site (Stedin Region – 110 kW Limit)
       * Preset B: EDEMSA Mendoza T2 RMT (Bodegas Salentein – 430 kW Limit)
     - Market Structure Modes:
       * Unbundled 4-Pillar Market (Netherlands / EU)
       * Integrated Single-Utility Bill (Argentina EDEMSA / Bundled DSO)
       * Custom Pillar Configuration
  2. Explicit Simulation Assumptions Register Banner
  3. Live "Master Bill Equation Bar" showing the additive 4-Pillar build-up at a glance:
     [1. Energy Supply: CURR X] + [2. Grid Network (DSO): CURR Y] + [3. Metering: CURR Z] +
     [4. Statutory Taxes: CURR W] = [Total Net: CURR N] (+ VAT) -> [TOTAL GROSS BILL: CURR G]
  4. Clean delegation to the 5 dedicated sub-tab modules (disabled pillars remain visible
     and are visually grayed out with [BYPASSED] tags):
     - tab_dso.render_dso_tab(...)
     - tab_supplier.render_supplier_tab(...)
     - tab_metering.render_metering_tab(...)
     - tab_overview.render_overview_tab(...)
     - tab_invoice_experimental.render_invoice_experimental_tab(...)
========================================================================================
"""

import os
from typing import Tuple, Any
import streamlit as st
import pandas as pd

try:
    from ui_sandbox.Currentsituation_sandbox.engine.config_and_models import (
        TariffStage,
        StatusQuoConfig2025,
        LoadSeries2025,
        StatusQuoAnnualResult,
    )
    from ui_sandbox.Currentsituation_sandbox.engine.consumption_pipeline import (
        normalize_load_profile_2025,
        synthesize_benchmark_load_profile_2025,
        synthesize_edemsa_salentein_load_profile_2025,
    )
    from ui_sandbox.Currentsituation_sandbox.engine.status_quo_master import (
        calculate_status_quo_master_2025,
    )
    from ui_sandbox.Currentsituation_sandbox.engine.tariff_defaults_2025 import (
        get_rotterdam_stedin_wko_config_2025,
        get_edemsa_salentein_config_2025,
    )
    from ui_sandbox.Currentsituation_sandbox.contract.assumptions_banner import (
        build_assumptions_register_dict,
        render_assumptions_banner,
    )
    from ui_sandbox.Currentsituation_sandbox.contract.tab_dso import render_dso_tab
    from ui_sandbox.Currentsituation_sandbox.contract.tab_supplier import render_supplier_tab
    from ui_sandbox.Currentsituation_sandbox.contract.tab_metering import render_metering_tab
    from ui_sandbox.Currentsituation_sandbox.contract.tab_overview import render_overview_tab
    from ui_sandbox.Currentsituation_sandbox.contract.tab_invoice_experimental import (
        render_invoice_experimental_tab,
    )
except ImportError:
    from current_model.ui_sandbox.Currentsituation_sandbox.engine.config_and_models import (
        TariffStage,
        StatusQuoConfig2025,
        LoadSeries2025,
        StatusQuoAnnualResult,
    )
    from current_model.ui_sandbox.Currentsituation_sandbox.engine.consumption_pipeline import (
        normalize_load_profile_2025,
        synthesize_benchmark_load_profile_2025,
        synthesize_edemsa_salentein_load_profile_2025,
    )
    from current_model.ui_sandbox.Currentsituation_sandbox.engine.status_quo_master import (
        calculate_status_quo_master_2025,
    )
    from current_model.ui_sandbox.Currentsituation_sandbox.engine.tariff_defaults_2025 import (
        get_rotterdam_stedin_wko_config_2025,
        get_edemsa_salentein_config_2025,
    )
    from current_model.ui_sandbox.Currentsituation_sandbox.contract.assumptions_banner import (
        build_assumptions_register_dict,
        render_assumptions_banner,
    )
    from current_model.ui_sandbox.Currentsituation_sandbox.contract.tab_dso import render_dso_tab
    from current_model.ui_sandbox.Currentsituation_sandbox.contract.tab_supplier import render_supplier_tab
    from current_model.ui_sandbox.Currentsituation_sandbox.contract.tab_metering import render_metering_tab
    from current_model.ui_sandbox.Currentsituation_sandbox.contract.tab_overview import render_overview_tab
    from current_model.ui_sandbox.Currentsituation_sandbox.contract.tab_invoice_experimental import (
        render_invoice_experimental_tab,
    )


def _load_paula_rotterdam_28d_series() -> Tuple[LoadSeries2025, str]:
    """Loads Paula3_totaal_clean.csv (Rotterdam / Dutch WKO 131.4 kW peak dataset) normalized to 2025."""
    current_dir = os.path.abspath(os.path.dirname(__file__))
    candidates = [
        os.path.abspath(os.path.join(current_dir, "..", "..", "BESS_sandbox", "data", "Paula3_totaal_clean.csv")),
        os.path.abspath(os.path.join(current_dir, "..", "data", "Paula3_totaal_clean.csv")),
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                raw_df = pd.read_csv(p)
                if "Date" in raw_df.columns and "Time" in raw_df.columns:
                    ts = pd.to_datetime(raw_df["Date"] + " " + raw_df["Time"], format="%d.%m.%Y %H:%M", errors="coerce")
                    raw_df["timestamp"] = ts
                p_col = "Total_Demand_kW" if "Total_Demand_kW" in raw_df.columns else raw_df.columns[-1]
                load_norm, _ = normalize_load_profile_2025(raw_df=raw_df, power_col=p_col, time_col="timestamp")
                return load_norm, "Paula3_totaal_clean.csv (Rotterdam / Dutch WKO Site - 131.4 kW Peak)"
            except Exception:
                pass
    load_bench = synthesize_benchmark_load_profile_2025(nominal_peak_kw=131.4)
    return load_bench, "Rotterdam / Dutch WKO Benchmark (131.4 kW Peak)"


def _find_or_create_load_series_2025() -> Tuple[LoadSeries2025, str]:
    """Retrieves or normalizes the active load profile for reference year 2025."""
    if "active_load_series_2025" in st.session_state and isinstance(st.session_state["active_load_series_2025"], LoadSeries2025):
        fname = st.session_state.get("active_csv_filename", "Active Profile")
        return st.session_state["active_load_series_2025"], f"Normalized 2025 Meter Data ({fname})"

    if "active_csv_df" in st.session_state and isinstance(st.session_state["active_csv_df"], pd.DataFrame):
        df_csv = st.session_state["active_csv_df"]
        if not df_csv.empty:
            fname = st.session_state.get("active_csv_filename", "Uploaded Meter File")
            p_col = "Total_Demand_kW" if "Total_Demand_kW" in df_csv.columns else df_csv.columns[1]
            t_col = "timestamp" if "timestamp" in df_csv.columns else None
            try:
                load_norm, _ = normalize_load_profile_2025(raw_df=df_csv, power_col=p_col, time_col=t_col)
                st.session_state["active_load_series_2025"] = load_norm
                return load_norm, f"CSV Real Meter Data ({fname})"
            except Exception:
                pass

    load_bench = synthesize_benchmark_load_profile_2025(nominal_peak_kw=250.0)
    st.session_state["active_load_series_2025"] = load_bench
    return load_bench, "Commercial Benchmark Simulation (250 kW peak)"


def _clear_dso_and_metering_widget_cache(key_prefix: str) -> None:
    """Clears cached form widget keys in st.session_state so newly loaded presets apply immediately."""
    substrings_to_clear = (
        f"{key_prefix}_dso_conn_fee_",
        f"{key_prefix}_dso_base_fee_",
        f"{key_prefix}_dso_p_contract_",
        f"{key_prefix}_dso_rate_cap_",
        f"{key_prefix}_dso_rate_peak_",
        f"{key_prefix}_dso_max_phys_",
        f"{key_prefix}_dso_tou_df_",
        f"{key_prefix}_dso_tou_editor_",
        f"{key_prefix}_dso_reactive_",
        f"{key_prefix}_dso_cosphi_",
        f"{key_prefix}_dso_penalty_",
        f"{key_prefix}_dso_reg_adj_",
        f"{key_prefix}_dso_adjust_breach_",
        f"{key_prefix}_dso_excess_pen_",
        f"{key_prefix}_dso_pico_only_",
    )
    for k in list(st.session_state.keys()):
        if any(sub in k for sub in substrings_to_clear):
            del st.session_state[k]


def _apply_reference_preset(preset_choice: str, key_prefix: str) -> None:
    """Applies a flagship reference preset into session state widget keys."""
    _clear_dso_and_metering_widget_cache(key_prefix)
    if "Rotterdam" in preset_choice or "Preset A" in preset_choice:
        cfg = get_rotterdam_stedin_wko_config_2025(contracted_capacity_kw=110.0)
        load_norm, fname = _load_paula_rotterdam_28d_series()
        st.session_state["active_load_series_2025"] = load_norm
        st.session_state["active_csv_filename"] = fname
        st.session_state["preset_contracted_kw"] = 110.0
        st.session_state[f"{key_prefix}_market_mode"] = "Unbundled 4-Pillar Market (Netherlands / EU)"
        st.session_state[f"{key_prefix}_currency_code"] = "EUR"
        st.session_state[f"{key_prefix}_dso_company"] = "Stedin Netbeheer B.V."
        st.session_state[f"{key_prefix}_dso_tier"] = "Trafo MS/LS (51 t/m 150 kW)"
        st.session_state[f"{key_prefix}_dso_gtv_kw"] = 110.0
        st.session_state[f"{key_prefix}_dso_enable_penalty"] = False
        st.session_state[f"{key_prefix}_vat_pct"] = 21.0
        st.session_state[f"{key_prefix}_vat_rate"] = 21.0
        st.session_state[f"{key_prefix}_preset_vat_rate"] = 21.0
        st.session_state[f"{key_prefix}_levy_rate"] = 0.0125
        st.session_state[f"{key_prefix}_preset_levy_rate"] = 0.0125
        st.session_state[f"{key_prefix}_pct_levy_rate"] = 0.0
        st.session_state[f"{key_prefix}_preset_pct_levy_rate"] = 0.0
        st.session_state[f"{key_prefix}_vat_on_levies"] = True
        st.session_state[f"{key_prefix}_preset_vat_on_levies"] = True
    elif "EDEMSA" in preset_choice or "Preset B" in preset_choice:
        cfg = get_edemsa_salentein_config_2025(contracted_capacity_kw=430.0)
        load_sal = synthesize_edemsa_salentein_load_profile_2025()
        st.session_state["active_load_series_2025"] = load_sal
        st.session_state["active_csv_filename"] = "EDEMSA Bodegas Salentein T2 RMT (02/2026 Calibrated — 691.0 kW Max / 649.0 kW Pico vs. 430.0 kW Limit)"
        st.session_state["preset_contracted_kw"] = 430.0
        st.session_state[f"{key_prefix}_market_mode"] = "Integrated Single-Utility Bill (Argentina EDEMSA / Bundled DSO)"
        st.session_state[f"{key_prefix}_currency_code"] = "ARS"
        st.session_state[f"{key_prefix}_dso_company"] = "EDEMSA Mendoza (Single-Utility)"
        st.session_state[f"{key_prefix}_dso_tier"] = "T2 RMT (Bodegas Salentein 430 kW)"
        st.session_state[f"{key_prefix}_dso_gtv_kw"] = 430.0
        st.session_state[f"{key_prefix}_dso_enable_penalty"] = True
        st.session_state[f"{key_prefix}_dso_penalty_rate"] = 40607.0460
        st.session_state[f"{key_prefix}_vat_pct"] = 27.0
        st.session_state[f"{key_prefix}_vat_rate"] = 27.0
        st.session_state[f"{key_prefix}_preset_vat_rate"] = 27.0
        st.session_state[f"{key_prefix}_levy_rate"] = 0.0
        st.session_state[f"{key_prefix}_preset_levy_rate"] = 0.0
        st.session_state[f"{key_prefix}_pct_levy_rate"] = 12.516026
        st.session_state[f"{key_prefix}_preset_pct_levy_rate"] = 12.516026
        st.session_state[f"{key_prefix}_vat_on_levies"] = False
        st.session_state[f"{key_prefix}_preset_vat_on_levies"] = False
    else:
        load_bench = synthesize_benchmark_load_profile_2025(nominal_peak_kw=250.0)
        st.session_state["active_load_series_2025"] = load_bench
        st.session_state["active_csv_filename"] = "Commercial Benchmark Simulation (250 kW peak)"
        st.session_state["preset_contracted_kw"] = 250.0
        st.session_state[f"{key_prefix}_market_mode"] = "Unbundled 4-Pillar Market (Netherlands / EU)"
        st.session_state[f"{key_prefix}_currency_code"] = "EUR"
        st.session_state[f"{key_prefix}_dso_company"] = "Enexis Netbeheer B.V."
        st.session_state[f"{key_prefix}_dso_tier"] = "MS-D (125 t/m 1.500 kW)"
        st.session_state[f"{key_prefix}_dso_gtv_kw"] = 250.0
        st.session_state[f"{key_prefix}_dso_enable_penalty"] = False
        st.session_state[f"{key_prefix}_vat_pct"] = 21.0
        st.session_state[f"{key_prefix}_vat_rate"] = 21.0
        st.session_state[f"{key_prefix}_preset_vat_rate"] = 21.0
        st.session_state[f"{key_prefix}_levy_rate"] = 0.0125
        st.session_state[f"{key_prefix}_preset_levy_rate"] = 0.0125
        st.session_state[f"{key_prefix}_pct_levy_rate"] = 0.0
        st.session_state[f"{key_prefix}_preset_pct_levy_rate"] = 0.0
        st.session_state[f"{key_prefix}_vat_on_levies"] = True
        st.session_state[f"{key_prefix}_preset_vat_on_levies"] = True


def _render_master_bill_equation_bar_html(result: StatusQuoAnnualResult) -> str:
    """
    Renders the Master Bill Equation Bar directly above the 5 tabs:
    [1. Energy Supply: CURR X] + [2. Grid Network (DSO): CURR Y] + [3. Metering: CURR Z] +
    [4. Statutory Taxes: CURR W] = [Total Net: CURR N] (+ VAT) -> [TOTAL GROSS BILL: CURR G | Blended Rate: CURR R/kWh]
    Bypassed pillars are visually grayed out (opacity: 0.45) with a [BYPASSED] badge.
    """
    curr = getattr(result.config, "currency_code", "EUR") or "EUR"
    en_p1 = getattr(result.config, "enable_pillar_1_supplier", True)
    en_p2 = getattr(result.config, "enable_pillar_2_dso", True)
    en_p3 = getattr(result.config, "enable_pillar_3_metering", True)
    en_p4 = getattr(result.config, "enable_pillar_4_taxes", True)

    p1 = result.total_supplier_net
    p2 = result.total_dso_net
    p3 = result.total_metering_net
    p4 = result.total_levies_net
    net = result.total_status_quo_net
    vat = result.total_vat_amount
    gross = result.total_status_quo_gross
    vat_pct = result.config.levies.vat_rate_pct
    r_net = result.blended_price_net_kwh
    r_gross = result.blended_price_gross_kwh

    p1_style = "" if en_p1 else "opacity: 0.42; filter: grayscale(100%);"
    p2_style = "" if en_p2 else "opacity: 0.42; filter: grayscale(100%);"
    p3_style = "" if en_p3 else "opacity: 0.42; filter: grayscale(100%);"
    p4_style = "" if en_p4 else "opacity: 0.42; filter: grayscale(100%);"

    p1_tag = "" if en_p1 else " <span style='font-size:0.65rem; color:#f59e0b;'>[BYPASSED]</span>"
    p2_tag = "" if en_p2 else " <span style='font-size:0.65rem; color:#f59e0b;'>[BYPASSED]</span>"
    p3_tag = "" if en_p3 else " <span style='font-size:0.65rem; color:#f59e0b;'>[BYPASSED]</span>"
    p4_tag = "" if en_p4 else " <span style='font-size:0.65rem; color:#f59e0b;'>[BYPASSED]</span>"

    return (
        f'<div style="background-color: #0b1329; border: 2px solid #334155; border-radius: 10px; padding: 14px 18px; margin-bottom: 14px;">\n'
        f'<div style="font-size: 0.76rem; font-weight: 700; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 10px;">'
        f'Master Annual Electricity Bill Equation (4 Cost Pillars &rarr; Total Net &rarr; Total Gross | Currency: {curr})'
        f'</div>\n'
        f'<div style="display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px;">\n'
        f'<div style="background-color: #1e293b; border-left: 4px solid #38bdf8; border-radius: 6px; padding: 8px 12px; flex: 1; min-width: 145px; {p1_style}">'
        f'<div style="font-size: 0.74rem; color: #94a3b8; font-weight: 600;">1. Energy Supply{p1_tag}</div>'
        f'<div style="font-size: 1.02rem; color: #f8fafc; font-weight: 700;">{curr} {p1:,.2f}</div>'
        f'</div>\n'
        f'<div style="color: #64748b; font-weight: 800; font-size: 1.15rem;">+</div>\n'
        f'<div style="background-color: #1e293b; border-left: 4px solid #f59e0b; border-radius: 6px; padding: 8px 12px; flex: 1; min-width: 145px; {p2_style}">'
        f'<div style="font-size: 0.74rem; color: #94a3b8; font-weight: 600;">2. Grid Network (DSO){p2_tag}</div>'
        f'<div style="font-size: 1.02rem; color: #f8fafc; font-weight: 700;">{curr} {p2:,.2f}</div>'
        f'</div>\n'
        f'<div style="color: #64748b; font-weight: 800; font-size: 1.15rem;">+</div>\n'
        f'<div style="background-color: #1e293b; border-left: 4px solid #8b5cf6; border-radius: 6px; padding: 8px 12px; flex: 1; min-width: 130px; {p3_style}">'
        f'<div style="font-size: 0.74rem; color: #94a3b8; font-weight: 600;">3. Metering{p3_tag}</div>'
        f'<div style="font-size: 1.02rem; color: #f8fafc; font-weight: 700;">{curr} {p3:,.2f}</div>'
        f'</div>\n'
        f'<div style="color: #64748b; font-weight: 800; font-size: 1.15rem;">+</div>\n'
        f'<div style="background-color: #1e293b; border-left: 4px solid #10b981; border-radius: 6px; padding: 8px 12px; flex: 1; min-width: 140px; {p4_style}">'
        f'<div style="font-size: 0.74rem; color: #94a3b8; font-weight: 600;">4. Statutory Taxes{p4_tag}</div>'
        f'<div style="font-size: 1.02rem; color: #f8fafc; font-weight: 700;">{curr} {p4:,.2f}</div>'
        f'</div>\n'
        f'<div style="color: #38bdf8; font-weight: 800; font-size: 1.20rem;">=</div>\n'
        f'<div style="background-color: #0f172a; border: 1.5px solid #38bdf8; border-radius: 6px; padding: 8px 14px; flex: 1.15; min-width: 165px;">'
        f'<div style="font-size: 0.74rem; color: #38bdf8; font-weight: 700; text-transform: uppercase;">Total Net Bill</div>'
        f'<div style="font-size: 1.08rem; color: #ffffff; font-weight: 800;">{curr} {net:,.2f}</div>'
        f'<div style="font-size: 0.72rem; color: #94a3b8;">+ {vat_pct:.0f}% VAT: {curr} {vat:,.2f}</div>'
        f'</div>\n'
        f'<div style="color: #10b981; font-weight: 800; font-size: 1.20rem;">&rarr;</div>\n'
        f'<div style="background-color: #06281e; border: 2px solid #10b981; border-radius: 6px; padding: 8px 14px; flex: 1.35; min-width: 210px;">'
        f'<div style="font-size: 0.75rem; color: #34d399; font-weight: 800; text-transform: uppercase;">TOTAL GROSS BILL</div>'
        f'<div style="font-size: 1.18rem; color: #ffffff; font-weight: 800;">{curr} {gross:,.2f}</div>'
        f'<div style="font-size: 0.73rem; color: #a7f3d0;">Blended Rate: <b>{curr} {r_net:.4f}</b> net / <b>{curr} {r_gross:.4f}</b> gross/kWh</div>'
        f'</div>\n'
        f'</div>\n'
        f'</div>'
    )


def render_tab2_base_contract(key_prefix: str = "currsit_contract") -> Any:
    """
    Renders the modular Status Quo 2025 Electricity Contract Configuration & Billing view:
    - Reference Benchmark & Market Structure Mode Control Bar
    - Master Bill Equation Bar above the tabs
    - Explicit Simulation Assumptions Register Banner
    - 5 dedicated sub-tabs delegated to modular files (disabled pillars are visually grayed out)
    """
    # --- Top Control Bar: Reference Presets & Market Structure Mode ---
    with st.container(border=True):
        st.markdown("##### :material/tune: Market Structure Mode & Reference Benchmark Quick-Loader")
        ctrl_c1, ctrl_c2, ctrl_c3, ctrl_c4 = st.columns([2.4, 1.0, 2.2, 0.9])

        with ctrl_c1:
            preset_options = [
                "Standard Enexis/Liander Commercial (250 kW Peak / 250 kW Limit)",
                "Preset A: Rotterdam / Dutch WKO Site (Stedin Region - 110 kW Limit)",
                "Preset B: EDEMSA Mendoza T2 RMT (Bodegas Salentein - 430 kW Limit)"
            ]
            selected_preset = st.selectbox(
                "Reference Benchmark Preset",
                options=preset_options,
                index=0,
                key=f"{key_prefix}_ref_preset_sel",
                help="Select a verified utility benchmark (auto-applies on change, or click 'Load Preset' to reset all fields)."
            )
            last_applied_key = f"{key_prefix}_last_applied_ref_preset"
            if last_applied_key not in st.session_state:
                st.session_state[last_applied_key] = selected_preset
            elif st.session_state[last_applied_key] != selected_preset:
                st.session_state[last_applied_key] = selected_preset
                _apply_reference_preset(selected_preset, key_prefix=key_prefix)
                st.rerun()

        with ctrl_c2:
            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            if st.button(":material/download_done: Load Preset", use_container_width=True, key=f"{key_prefix}_btn_load_preset"):
                st.session_state[f"{key_prefix}_last_applied_ref_preset"] = selected_preset
                _apply_reference_preset(selected_preset, key_prefix=key_prefix)
                st.rerun()

        with ctrl_c3:
            market_mode_options = [
                "Unbundled 4-Pillar Market (Netherlands / EU)",
                "Integrated Single-Utility Bill (Argentina EDEMSA / Bundled DSO)",
                "Custom Pillar Configuration"
            ]
            current_mode = st.session_state.get(f"{key_prefix}_market_mode", market_mode_options[0])
            mode_idx = market_mode_options.index(current_mode) if current_mode in market_mode_options else 0
            market_mode_label = st.selectbox(
                "Market Structure Mode (Tab Gray-Out Control)",
                options=market_mode_options,
                index=mode_idx,
                key=f"{key_prefix}_market_mode",
                help=(
                    "Unbundled 4-Pillar: Separate Retailer, DSO, Metering, and Tax pillars. "
                    "Integrated Single-Utility: Grays out Retailer & Metering tabs (set to 0.00) while keeping them visible."
                )
            )

        with ctrl_c4:
            curr_options = ["EUR", "ARS", "USD"]
            cur_curr = st.session_state.get(f"{key_prefix}_currency_code", "EUR")
            curr_idx = curr_options.index(cur_curr) if cur_curr in curr_options else 0
            currency_code = st.selectbox(
                "Currency",
                options=curr_options,
                index=curr_idx,
                key=f"{key_prefix}_currency_code"
            )

        # Resolve pillar enablement flags
        if "Integrated Single-Utility" in market_mode_label:
            market_mode_code = "single_utility"
            en_p2_dso = True
            en_p1_supplier = False
            en_p3_metering = False
            en_p4_taxes = True
            st.caption(
                ":material/layers_clear: **Integrated Single-Utility Mode Active:** "
                "Tab 2 (*Energy Supply Retailer*) and Pillar 3 (*Metering*) remain visible in the tab bar below "
                "but are **grayed out (`[BYPASSED]`)** and evaluate to `0.00` so all bundled charges are billed via the Utility/DSO."
            )
        elif "Custom" in market_mode_label:
            market_mode_code = "custom"
            chk1, chk2, chk3, chk4 = st.columns(4)
            with chk1:
                en_p2_dso = st.checkbox(
                    "Enable Pillar 2: Grid Network (DSO)",
                    value=bool(st.session_state.get(f"{key_prefix}_en_p2", True)),
                    key=f"{key_prefix}_en_p2"
                )
            with chk2:
                en_p1_supplier = st.checkbox(
                    "Enable Pillar 1: Energy Supply (Retailer)",
                    value=bool(st.session_state.get(f"{key_prefix}_en_p1", True)),
                    key=f"{key_prefix}_en_p1"
                )
            with chk3:
                en_p3_metering = st.checkbox(
                    "Enable Pillar 3: Metering & Telemetry",
                    value=bool(st.session_state.get(f"{key_prefix}_en_p3", True)),
                    key=f"{key_prefix}_en_p3"
                )
            with chk4:
                en_p4_taxes = st.checkbox(
                    "Enable Pillar 4: Statutory Taxes",
                    value=bool(st.session_state.get(f"{key_prefix}_en_p4", True)),
                    key=f"{key_prefix}_en_p4"
                )
        else:
            market_mode_code = "unbundled_4_pillar"
            en_p2_dso = True
            en_p1_supplier = True
            en_p3_metering = True
            en_p4_taxes = True

    load_series, source_label = _find_or_create_load_series_2025()

    st.info(
        f":material/bolt: **Active Consumption Baseline:** {source_label} | "
        f"**Annual Consumption:** {load_series.total_energy_kwh:,.0f} kWh | "
        f"**Measured Annual Peak:** {load_series.peak_demand_kw:,.1f} kW",
        icon=":material/info:"
    )

    equation_bar_container = st.container()
    assumptions_banner_container = st.container()

    # Keep all 5 tabs visible at all times; append [BYPASSED] to grayed-out pillars
    tab1_title = ":material/grid_view: 1. Grid Network (DSO)" + ("" if en_p2_dso else " [BYPASSED]")
    tab2_title = ":material/storefront: 2. Energy Supply (Retailer)" + ("" if en_p1_supplier else " [BYPASSED]")
    if en_p3_metering and en_p4_taxes:
        tab3_suffix = ""
    elif not en_p3_metering and not en_p4_taxes:
        tab3_suffix = " [BYPASSED]"
    elif not en_p3_metering:
        tab3_suffix = " [Metering BYPASSED]"
    else:
        tab3_suffix = " [Taxes BYPASSED]"
    tab3_title = f":material/speed: 3. Metering & Statutory Taxes{tab3_suffix}"

    actor_tabs = st.tabs([
        tab1_title,
        tab2_title,
        tab3_title,
        ":material/analytics: 4. Executive Overview & 15Y TCO",
        ":material/receipt: 5. Classic Electricity Bill"
    ])

    with actor_tabs[0]:
        dso_tariff = render_dso_tab(
            load_series=load_series,
            key_prefix=key_prefix,
            is_enabled=en_p2_dso,
            currency_code=currency_code
        )

    with actor_tabs[1]:
        supplier_tariff = render_supplier_tab(
            load_series=load_series,
            key_prefix=key_prefix,
            is_enabled=en_p1_supplier,
            currency_code=currency_code
        )

    with actor_tabs[2]:
        metering_tariff, levy_config, discount_rate, escalation_rate = render_metering_tab(
            load_series=load_series,
            key_prefix=key_prefix,
            enable_p3_metering=en_p3_metering,
            enable_p4_taxes=en_p4_taxes,
            currency_code=currency_code
        )

    active_config = StatusQuoConfig2025(
        stage=TariffStage.STAGE_1_DEFAULT,
        dso=dso_tariff,
        supplier=supplier_tariff,
        metering=metering_tariff,
        levies=levy_config,
        discount_rate_pct=discount_rate,
        energy_escalation_pct=escalation_rate,
        evaluation_horizon_years=15,
        currency_code=currency_code,
        market_mode=market_mode_code,
        enable_pillar_1_supplier=en_p1_supplier,
        enable_pillar_2_dso=en_p2_dso,
        enable_pillar_3_metering=en_p3_metering,
        enable_pillar_4_taxes=en_p4_taxes,
    )

    result = calculate_status_quo_master_2025(load=load_series, config=active_config)

    assumptions_dict = build_assumptions_register_dict(
        load_series=load_series,
        config=active_config,
        source_filename=source_label,
        bess_config=None
    )

    with equation_bar_container:
        st.markdown(_render_master_bill_equation_bar_html(result), unsafe_allow_html=True)

    with assumptions_banner_container:
        render_assumptions_banner(assumptions_dict=assumptions_dict, expanded=False)

    with actor_tabs[3]:
        render_overview_tab(
            result=result,
            active_config=active_config,
            key_prefix=key_prefix
        )

    with actor_tabs[4]:
        render_invoice_experimental_tab(
            result=result,
            active_config=active_config,
            load_series=load_series,
            key_prefix=key_prefix,
            assumptions_dict=assumptions_dict
        )

    return result


def render_tab2_contract(key_prefix: str = "currsit_contract") -> Any:
    """Alias for render_tab2_base_contract."""
    return render_tab2_base_contract(key_prefix=key_prefix)


def render_tab2_contract_switch(key_prefix: str = "currsit_contract") -> Any:
    """Compatibility switch alias rendering the base contract."""
    return render_tab2_base_contract(key_prefix=key_prefix)
