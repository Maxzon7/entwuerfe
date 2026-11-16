"""
Lazy-loaded 4-pillar commercial electricity tariff evaluator, isolated component economics,
and 15-year cashflow / NPV / IRR engine.
"""

from typing import List, Optional
import numpy as np
import pandas as pd

from .models_and_presets import (
    MONTH_NAMES_SHORT,
    CombinedFinancialConfig,
    CombinedFinancialKPIs,
    CombinedSimulationResult,
)
from .tariff_presets import build_financial_summary_table_df
from .cashflow_lifecycle import (
    _calculate_irr,
    append_isolated_hardware_monthly_rows,
    compute_hardware_capex_and_opex,
    compute_15y_lifecycle_projection,
    extract_tou_and_dispatch_monthly_arrays,
)

def evaluate_combined_financials(
    sim_res: CombinedSimulationResult,
    fin_cfg: CombinedFinancialConfig,
) -> CombinedSimulationResult:
    """
    Evaluates the 4-Pillar Tariff costs (Supplier, DSO, Metering, Taxes), itemized component
    CAPEX & OPEX, Annual Net Savings vs. Current situation, Simple Payback, 15-Year NPV, and
    the 15-Year Cashflow Table.
    """
    cfg = sim_res.system_config
    kpis = sim_res.kpis
    solar_deriv = sim_res.solar_derivation

    # 1. Hardware CAPEX, Repowering & OPEX Overrides (Unit Rates vs. >0 Lump-Sum Overrides)
    hw_res = compute_hardware_capex_and_opex(cfg=cfg, solar_deriv=solar_deriv, fin_cfg=fin_cfg)
    solar_capex = hw_res["solar_capex"]
    solar_modules_capex = hw_res["solar_modules_capex"]
    solar_inverter_capex = hw_res["solar_inverter_capex"]
    solar_mounting_capex = hw_res["solar_mounting_capex"]
    battery_rack_capex = hw_res["battery_rack_capex"]
    battery_inv_capex = hw_res["battery_inv_capex"]
    battery_bop_capex = hw_res["battery_bop_capex"]
    battery_capex = hw_res["battery_capex"]
    battery_aug_eur = hw_res["battery_aug_eur"]
    gen_is_purchase = hw_res["gen_is_purchase"]
    generator_capex = hw_res["generator_capex"]
    gross_capex = solar_capex + battery_capex + generator_capex
    avoided_upgrade_capex = (
        0.0
        if fin_cfg.strict_grid_congestion_mode
        else max(0.0, float(fin_cfg.avoided_grid_upgrade_capex_eur))
    )
    net_total_capex = max(0.0, gross_capex - avoided_upgrade_capex)
    total_capex = net_total_capex

    # 2. Resolve 4-Pillar & Single-Utility Market Structure Rates
    is_legacy_energy = fin_cfg.grid_energy_price_eur_kwh is not None
    en_p1 = True if is_legacy_energy else bool(fin_cfg.enable_pillar_1_supplier)
    en_p2 = True if fin_cfg.grid_capacity_fee_eur_kw_month is not None else bool(fin_cfg.enable_pillar_2_dso)
    en_p3 = True if fin_cfg.grid_fixed_fee_eur_month is not None else bool(fin_cfg.enable_pillar_3_metering)
    en_p4 = False if is_legacy_energy else bool(fin_cfg.enable_pillar_4_taxes)

    if is_legacy_energy:
        supp_kwh_rate = float(fin_cfg.grid_energy_price_eur_kwh)
        tax_kwh_rate = 0.0
        gvo_rate = 0.0
        is_dual_tou = False
    else:
        supp_kwh_rate = float(fin_cfg.supplier_energy_price_eur_kwh) if en_p1 else 0.0
        tax_kwh_rate = float(fin_cfg.energy_tax_eur_kwh) if en_p4 else 0.0
        gvo_rate = max(0.0, float(fin_cfg.supplier_gvo_surcharge_eur_kwh)) if en_p1 else 0.0
        is_dual_tou = bool(en_p1 and str(fin_cfg.supplier_pricing_mode) == "dual_tou")

    supp_ht_rate = float(fin_cfg.supplier_peak_ht_eur_kwh) if en_p1 else 0.0
    supp_nt_rate = float(fin_cfg.supplier_offpeak_nt_eur_kwh) if en_p1 else 0.0

    if fin_cfg.grid_capacity_fee_eur_kw_month is not None:
        dso_cap_rate = float(fin_cfg.grid_capacity_fee_eur_kw_month)
        dso_peak_rate = 0.0
    else:
        dso_cap_rate = float(fin_cfg.dso_capacity_fee_eur_kw_month) if en_p2 else 0.0
        dso_peak_rate = float(fin_cfg.dso_peak_demand_fee_eur_kw_month) if en_p2 else 0.0

    if fin_cfg.grid_fixed_fee_eur_month is not None:
        supp_fixed_mo = 0.0
        dso_conn_mo = 0.0
        dso_trans_fix_mo = float(fin_cfg.grid_fixed_fee_eur_month) if en_p2 else 0.0
        dso_fixed_mo = dso_trans_fix_mo
        meter_fixed_mo = 0.0
    else:
        supp_fixed_mo = float(fin_cfg.supplier_fixed_fee_eur_month) if en_p1 else 0.0
        dso_conn_mo = max(0.0, float(fin_cfg.dso_connection_fee_eur_month)) if en_p2 else 0.0
        dso_trans_fix_mo = max(0.0, float(fin_cfg.dso_fixed_fee_eur_month)) if en_p2 else 0.0
        dso_fixed_mo = dso_conn_mo + dso_trans_fix_mo
        meter_fixed_mo = float(fin_cfg.metering_fixed_fee_eur_month) if en_p3 else 0.0

    en_excess_pen = bool(fin_cfg.dso_enable_excess_capacity_penalty) and en_p2
    pen_rate_kw = float(fin_cfg.grid_overload_penalty_eur_kw) if en_excess_pen else 0.0
    tax_pct = (float(fin_cfg.tax_surcharge_pct) / 100.0) if en_p4 else 0.0
    dso_vol_rate = float(fin_cfg.dso_transport_eur_kwh) if en_p2 else 0.0
    dso_3win_tou = bool(fin_cfg.dso_enable_three_window_tou) and en_p2
    dso_pk_vol_rate = (
        float(fin_cfg.dso_transport_peak_eur_kwh)
        if fin_cfg.dso_transport_peak_eur_kwh is not None
        else dso_vol_rate
    ) if en_p2 else 0.0
    dso_off_vol_rate = (
        float(fin_cfg.dso_transport_offpeak_eur_kwh)
        if fin_cfg.dso_transport_offpeak_eur_kwh is not None
        else dso_vol_rate
    ) if en_p2 else 0.0
    dso_sh_vol_rate = (
        float(fin_cfg.dso_transport_shoulder_eur_kwh)
        if fin_cfg.dso_transport_shoulder_eur_kwh > 0.0
        else dso_vol_rate
    ) if en_p2 else 0.0
    dso_pico_peak_only = bool(fin_cfg.dso_bill_peak_on_pico_only) and en_p2
    dso_reg_adj_mo = float(fin_cfg.dso_regulatory_adjustments_eur_month) if en_p2 else 0.0
    trafo_rent_mo = float(fin_cfg.avoided_transformer_rent_eur_month) if en_p2 else 0.0
    vat_frac = max(0.0, float(fin_cfg.vat_rate_pct)) / 100.0
    vat_on_levies = bool(fin_cfg.vat_applies_to_levies)
    annual_tax_credit = 0.0 if (is_legacy_energy or not en_p4) else max(0.0, float(fin_cfg.annual_tax_reduction_credit_eur))

    # 2b. Aggregate 15-Minute TOU Windows (2-Window HT/NT + 3-Window Pico/Valle/Resto) & Component Dispatches
    _arrs = extract_tou_and_dispatch_monthly_arrays(sim_res, cfg, kpis)
    cons_ht_m = _arrs["cons_ht_m"]
    cons_nt_m = _arrs["cons_nt_m"]
    imp_ht_m = _arrs["imp_ht_m"]
    imp_nt_m = _arrs["imp_nt_m"]
    cons_pico_m = _arrs["cons_pico_m"]
    cons_valle_m = _arrs["cons_valle_m"]
    cons_resto_m = _arrs["cons_resto_m"]
    imp_pico_m = _arrs["imp_pico_m"]
    imp_valle_m = _arrs["imp_valle_m"]
    imp_resto_m = _arrs["imp_resto_m"]
    base_pico_pk_m = _arrs["base_pico_pk_m"]
    comb_pico_pk_m = _arrs["comb_pico_pk_m"]
    pv_chg_bess_m = _arrs["pv_chg_bess_m"]
    bess_chg_grid_m = _arrs["bess_chg_grid_m"]
    bess_shave_kw_m = _arrs["bess_shave_kw_m"]
    gen_shave_kw_m = _arrs["gen_shave_kw_m"]
    sol_via_bess_m = _arrs["sol_via_bess_m"]

    # 3. Monthly 4-Pillar / Single-Utility Grid & Operational Costs (12 Months)
    mb_df = sim_res.monthly_balance_df
    monthly_cost_rows = []
    dso_monthly_rows = []
    supplier_monthly_rows = []
    tax_monthly_rows = []
    solar_fin_rows = []
    battery_fin_rows = []
    generator_fin_rows = []

    total_cons_kwh_mb = float(mb_df["Consumption (kWh)"].sum()) if not mb_df.empty else 0.0
    total_imp_kwh_mb = float(mb_df["Combined Grid Import (kWh)"].sum()) if not mb_df.empty else 0.0
    base_gross_tax_tot = total_cons_kwh_mb * tax_kwh_rate
    comb_gross_tax_tot = total_imp_kwh_mb * tax_kwh_rate
    base_credit_ratio = min(1.0, annual_tax_credit / base_gross_tax_tot) if base_gross_tax_tot > 1e-9 else 0.0
    comb_credit_ratio = min(1.0, annual_tax_credit / comb_gross_tax_tot) if comb_gross_tax_tot > 1e-9 else 0.0

    base_p1_sum = 0.0
    base_p2_sum = 0.0
    base_p3_sum = 0.0
    base_p4_sum = 0.0
    base_pen_sum = 0.0
    base_supp_energy_sum = 0.0
    base_supp_ht_sum = 0.0
    base_supp_nt_sum = 0.0
    base_supp_gvo_sum = 0.0
    base_dso_cap_sum = 0.0
    base_dso_peak_sum = 0.0
    base_dso_vol_sum = 0.0
    base_dso_vol_pk_sum = 0.0
    base_dso_vol_off_sum = 0.0
    base_dso_vol_sh_sum = 0.0
    base_dso_pk_kwh_sum = 0.0
    base_dso_off_kwh_sum = 0.0
    base_dso_sh_kwh_sum = 0.0
    base_dso_reg_sum = 0.0
    base_dso_billed_pk_sum = 0.0
    base_dso_billed_cap_sum = 0.0
    base_tax_kwh_gross_sum = 0.0
    base_tax_credit_sum = 0.0
    base_tax_kwh_sum = 0.0
    base_tax_surcharge_sum = 0.0
    base_vat_sum = 0.0
    base_breach_months = 0

    comb_p1_sum = 0.0
    comb_p2_sum = 0.0
    comb_p3_sum = 0.0
    comb_p4_sum = 0.0
    comb_pen_sum = 0.0
    comb_supp_energy_sum = 0.0
    comb_supp_ht_sum = 0.0
    comb_supp_nt_sum = 0.0
    comb_supp_gvo_sum = 0.0
    comb_dso_cap_sum = 0.0
    comb_dso_peak_sum = 0.0
    comb_dso_vol_sum = 0.0
    comb_dso_vol_pk_sum = 0.0
    comb_dso_vol_off_sum = 0.0
    comb_dso_vol_sh_sum = 0.0
    comb_dso_pk_kwh_sum = 0.0
    comb_dso_off_kwh_sum = 0.0
    comb_dso_sh_kwh_sum = 0.0
    comb_dso_reg_sum = 0.0
    comb_dso_billed_pk_sum = 0.0
    comb_dso_billed_cap_sum = 0.0
    comb_tax_kwh_gross_sum = 0.0
    comb_tax_credit_sum = 0.0
    comb_tax_kwh_sum = 0.0
    comb_tax_surcharge_sum = 0.0
    comb_vat_sum = 0.0
    comb_breach_months = 0

    gen_fuel_cost_sum = 0.0
    gen_maint_cost_sum = 0.0
    gen_rental_cost_sum = 0.0

    solar_om_annual = hw_res["solar_om_annual"]
    battery_om_annual = hw_res["battery_om_annual"]
    gen_lump_svc_monthly = hw_res["gen_lump_svc_annual"] / 12.0
    sol_om_monthly = solar_om_annual / 12.0
    bat_om_monthly = battery_om_annual / 12.0
    om_monthly = sol_om_monthly + bat_om_monthly
    feed_in_rate = max(0.0, float(fin_cfg.solar_export_feed_in_eur_kwh)) if cfg.enable_solar else 0.0

    # First estimate blended variable rate for monthly Solar & Battery value attribution
    eff_supp_rate_base = supp_kwh_rate if en_p1 else 0.0
    if en_p1 and is_dual_tou:
        tot_ht_imp = float(np.sum(imp_ht_m))
        tot_nt_imp = float(np.sum(imp_nt_m))
        if tot_ht_imp + tot_nt_imp > 1.0:
            eff_supp_rate_base = (tot_ht_imp * supp_ht_rate + tot_nt_imp * supp_nt_rate) / (tot_ht_imp + tot_nt_imp)
    if dso_3win_tou:
        tot_3w = float(np.sum(imp_pico_m) + np.sum(imp_valle_m) + np.sum(imp_resto_m))
        if tot_3w > 1.0:
            eff_dso_vol_rate = (
                float(np.sum(imp_pico_m)) * dso_pk_vol_rate
                + float(np.sum(imp_valle_m)) * dso_off_vol_rate
                + float(np.sum(imp_resto_m)) * dso_sh_vol_rate
            ) / tot_3w
        else:
            eff_dso_vol_rate = dso_sh_vol_rate
    else:
        eff_dso_vol_rate = dso_vol_rate
    eff_tax_kwh_rate = tax_kwh_rate * (1.0 - comb_credit_ratio) if comb_gross_tax_tot > 1e-9 else tax_kwh_rate
    var_grid_rate = (eff_supp_rate_base + gvo_rate + eff_dso_vol_rate) * (1.0 + tax_pct) + eff_tax_kwh_rate

    bat_peak_sav_sum = 0.0
    bat_grid_chg_cost_sum = 0.0
    gen_peak_sav_sum = 0.0

    for row_idx, row in mb_df.iterrows():
        m_name = str(row["Month"])
        m_idx_0 = MONTH_NAMES_SHORT.index(m_name) if m_name in MONTH_NAMES_SHORT else min(11, int(row_idx))
        cons_kwh = float(row["Consumption (kWh)"])
        base_peak_kw = float(row["Current situation Peak (kW)"])
        base_over_kw = float(row["Current situation Overload (kW)"])

        comb_imp_kwh = float(row["Combined Grid Import (kWh)"])
        comb_peak_kw = float(row["Combined Grid Peak (kW)"])
        comb_over_kw = float(row["Remaining Overload (kW)"])
        sol_gen_m_kwh = float(row.get("Solar Generation (kWh)", 0.0)) if cfg.enable_solar else 0.0
        sol_dir_m_kwh = float(row.get("Solar Direct (kWh)", 0.0)) if cfg.enable_solar else 0.0
        sol_exp_m_kwh = float(row.get("Solar Export (kWh)", 0.0)) if cfg.enable_solar else 0.0
        sol_bat_m_kwh = float(sol_via_bess_m[m_idx_0]) if (cfg.enable_solar and cfg.enable_battery) else 0.0
        b_dis_m_kwh = float(row.get("Battery Discharge (kWh)", 0.0)) if cfg.enable_battery else 0.0
        g_out_m_kwh = float(row.get("Generator Output (kWh)", 0.0)) if cfg.enable_generator else 0.0
        gen_hrs = float(row["Generator Runtime (hrs)"])
        gen_fuel = float(row["Generator Fuel"])

        # Pillar 1: Energy Supply (Retailer)
        if not en_p1:
            b_supp_ht = b_supp_nt = b_supp_gvo = b_supp_en = b_p1 = 0.0
            c_supp_ht = c_supp_nt = c_supp_gvo = c_supp_en = c_p1 = 0.0
        elif is_dual_tou:
            raw_b_tot = float(cons_ht_m[m_idx_0] + cons_nt_m[m_idx_0])
            if raw_b_tot > 1e-6:
                b_ht_kwh = cons_kwh * (float(cons_ht_m[m_idx_0]) / raw_b_tot)
                b_nt_kwh = max(0.0, cons_kwh - b_ht_kwh)
            else:
                b_ht_kwh, b_nt_kwh = cons_kwh * 0.55, cons_kwh * 0.45

            raw_c_tot = float(imp_ht_m[m_idx_0] + imp_nt_m[m_idx_0])
            if raw_c_tot > 1e-6:
                c_ht_kwh = comb_imp_kwh * (float(imp_ht_m[m_idx_0]) / raw_c_tot)
                c_nt_kwh = max(0.0, comb_imp_kwh - c_ht_kwh)
            else:
                c_ht_kwh, c_nt_kwh = comb_imp_kwh * 0.55, comb_imp_kwh * 0.45

            b_supp_ht = b_ht_kwh * supp_ht_rate
            b_supp_nt = b_nt_kwh * supp_nt_rate
            c_supp_ht = c_ht_kwh * supp_ht_rate
            c_supp_nt = c_nt_kwh * supp_nt_rate
            b_supp_gvo = cons_kwh * gvo_rate
            b_supp_en = b_supp_ht + b_supp_nt + b_supp_gvo
            b_p1 = b_supp_en + supp_fixed_mo
            c_supp_gvo = comb_imp_kwh * gvo_rate
            c_supp_en = c_supp_ht + c_supp_nt + c_supp_gvo
            c_p1 = c_supp_en + supp_fixed_mo
        else:
            b_supp_ht = cons_kwh * supp_kwh_rate
            b_supp_nt = 0.0
            c_supp_ht = comb_imp_kwh * supp_kwh_rate
            c_supp_nt = 0.0
            b_supp_gvo = cons_kwh * gvo_rate
            b_supp_en = b_supp_ht + b_supp_nt + b_supp_gvo
            b_p1 = b_supp_en + supp_fixed_mo
            c_supp_gvo = comb_imp_kwh * gvo_rate
            c_supp_en = c_supp_ht + c_supp_nt + c_supp_gvo
            c_p1 = c_supp_en + supp_fixed_mo

        # Pillar 2: Grid Network (DSO / Single-Utility)
        base_is_breach = bool(base_peak_kw > cfg.grid_limit_kw + 0.05)
        comb_is_breach = bool(comb_peak_kw > cfg.grid_limit_kw + 0.05)
        if base_is_breach:
            base_breach_months += 1
        if comb_is_breach:
            comb_breach_months += 1

        if en_p2:
            b_billed_cap_kw = max(cfg.grid_limit_kw, base_peak_kw) if fin_cfg.dso_adjust_capacity_on_breach else cfg.grid_limit_kw
            c_billed_cap_kw = max(cfg.grid_limit_kw, comb_peak_kw) if fin_cfg.dso_adjust_capacity_on_breach else cfg.grid_limit_kw
            b_billed_pk_kw = float(base_pico_pk_m[m_idx_0]) if (dso_pico_peak_only and base_pico_pk_m[m_idx_0] > 0.0) else base_peak_kw
            c_billed_pk_kw = float(comb_pico_pk_m[m_idx_0]) if (dso_pico_peak_only and comb_pico_pk_m[m_idx_0] > 0.0) else comb_peak_kw

            if dso_3win_tou:
                b_3w_tot = float(cons_pico_m[m_idx_0] + cons_valle_m[m_idx_0] + cons_resto_m[m_idx_0])
                b_scale = (cons_kwh / b_3w_tot) if b_3w_tot > 1e-6 else 0.0
                b_pk_kwh = float(cons_pico_m[m_idx_0]) * b_scale if b_3w_tot > 1e-6 else cons_kwh * 0.21
                b_off_kwh = float(cons_valle_m[m_idx_0]) * b_scale if b_3w_tot > 1e-6 else cons_kwh * 0.21
                b_sh_kwh = max(0.0, cons_kwh - b_pk_kwh - b_off_kwh)

                c_3w_tot = float(imp_pico_m[m_idx_0] + imp_valle_m[m_idx_0] + imp_resto_m[m_idx_0])
                c_scale = (comb_imp_kwh / c_3w_tot) if c_3w_tot > 1e-6 else 0.0
                c_pk_kwh = float(imp_pico_m[m_idx_0]) * c_scale if c_3w_tot > 1e-6 else comb_imp_kwh * 0.21
                c_off_kwh = float(imp_valle_m[m_idx_0]) * c_scale if c_3w_tot > 1e-6 else comb_imp_kwh * 0.21
                c_sh_kwh = max(0.0, comb_imp_kwh - c_pk_kwh - c_off_kwh)

                b_vol_pk = b_pk_kwh * dso_pk_vol_rate
                b_vol_off = b_off_kwh * dso_off_vol_rate
                b_vol_sh = b_sh_kwh * dso_sh_vol_rate
                c_vol_pk = c_pk_kwh * dso_pk_vol_rate
                c_vol_off = c_off_kwh * dso_off_vol_rate
                c_vol_sh = c_sh_kwh * dso_sh_vol_rate
            else:
                raw_b2_tot = float(cons_ht_m[m_idx_0] + cons_nt_m[m_idx_0])
                b_pk_kwh = cons_kwh * (float(cons_ht_m[m_idx_0]) / raw_b2_tot) if raw_b2_tot > 1e-6 else cons_kwh * 0.55
                b_off_kwh = max(0.0, cons_kwh - b_pk_kwh)
                b_sh_kwh = 0.0

                raw_c2_tot = float(imp_ht_m[m_idx_0] + imp_nt_m[m_idx_0])
                c_pk_kwh = comb_imp_kwh * (float(imp_ht_m[m_idx_0]) / raw_c2_tot) if raw_c2_tot > 1e-6 else comb_imp_kwh * 0.55
                c_off_kwh = max(0.0, comb_imp_kwh - c_pk_kwh)
                c_sh_kwh = 0.0

                b_vol_pk = b_pk_kwh * dso_pk_vol_rate
                b_vol_off = b_off_kwh * dso_off_vol_rate
                b_vol_sh = 0.0
                c_vol_pk = c_pk_kwh * dso_pk_vol_rate
                c_vol_off = c_off_kwh * dso_off_vol_rate
                c_vol_sh = 0.0

            b_pen = base_over_kw * pen_rate_kw
            b_cap = b_billed_cap_kw * dso_cap_rate
            b_pk = b_billed_pk_kw * dso_peak_rate
            b_vol = b_vol_pk + b_vol_off + b_vol_sh
            b_p2 = b_cap + b_pk + dso_fixed_mo + b_vol + trafo_rent_mo + b_pen + dso_reg_adj_mo

            c_pen = comb_over_kw * pen_rate_kw
            c_cap = c_billed_cap_kw * dso_cap_rate
            c_pk = c_billed_pk_kw * dso_peak_rate
            c_vol = c_vol_pk + c_vol_off + c_vol_sh
            c_p2 = c_cap + c_pk + dso_fixed_mo + c_vol + c_pen + dso_reg_adj_mo
        else:
            b_billed_cap_kw = c_billed_cap_kw = 0.0
            b_billed_pk_kw = c_billed_pk_kw = 0.0
            b_pk_kwh = b_off_kwh = b_sh_kwh = c_pk_kwh = c_off_kwh = c_sh_kwh = 0.0
            b_vol_pk = b_vol_off = b_vol_sh = c_vol_pk = c_vol_off = c_vol_sh = 0.0
            b_pen = b_cap = b_pk = b_vol = b_p2 = 0.0
            c_pen = c_cap = c_pk = c_vol = c_p2 = 0.0

        # Pillar 3: Metering
        b_p3 = meter_fixed_mo if en_p3 else 0.0
        c_p3 = meter_fixed_mo if en_p3 else 0.0

        # Pillar 4: Taxes, Levies & VAT
        b_electric_net = b_p1 + b_p2 + b_p3
        c_electric_net = c_p1 + c_p2 + c_p3
        if en_p4:
            b_tax_kwh_gross = cons_kwh * tax_kwh_rate
            b_tax_credit = b_tax_kwh_gross * base_credit_ratio
            b_tax_kwh = b_tax_kwh_gross - b_tax_credit
            b_tax_sur = b_electric_net * tax_pct
            b_p4 = b_tax_kwh + b_tax_sur

            c_tax_kwh_gross = comb_imp_kwh * tax_kwh_rate
            c_tax_credit = c_tax_kwh_gross * comb_credit_ratio
            c_tax_kwh = c_tax_kwh_gross - c_tax_credit
            c_tax_sur = c_electric_net * tax_pct
            c_p4 = c_tax_kwh + c_tax_sur
        else:
            b_tax_kwh_gross = b_tax_credit = b_tax_kwh = b_tax_sur = b_p4 = 0.0
            c_tax_kwh_gross = c_tax_credit = c_tax_kwh = c_tax_sur = c_p4 = 0.0

        b_tot = b_electric_net + b_p4
        b_vat_m = ((b_tot) if vat_on_levies else b_electric_net) * vat_frac
        c_vat_m = ((c_electric_net + c_p4) if vat_on_levies else c_electric_net) * vat_frac

        c_fuel = (gen_fuel * fin_cfg.fuel_price_eur_per_unit) if cfg.enable_generator else 0.0
        if cfg.enable_generator:
            if gen_lump_svc_monthly > 0.0:
                c_maint = gen_lump_svc_monthly
                c_rent = 0.0
            else:
                c_maint = gen_hrs * fin_cfg.generator_maintenance_eur_per_hour
                c_rent = fin_cfg.generator_rental_eur_month if not gen_is_purchase else 0.0
        else:
            c_maint = 0.0
            c_rent = 0.0
        c_tot = c_p1 + c_p2 + c_p3 + c_p4 + c_fuel + c_maint + c_rent + om_monthly

        base_p1_sum += b_p1
        base_p2_sum += b_p2
        base_p3_sum += b_p3
        base_p4_sum += b_p4
        base_pen_sum += b_pen
        base_supp_energy_sum += b_supp_en
        base_supp_ht_sum += b_supp_ht
        base_supp_nt_sum += b_supp_nt
        base_supp_gvo_sum += b_supp_gvo
        base_dso_cap_sum += b_cap
        base_dso_peak_sum += b_pk
        base_dso_vol_sum += b_vol
        base_dso_vol_pk_sum += b_vol_pk
        base_dso_vol_off_sum += b_vol_off
        base_dso_vol_sh_sum += b_vol_sh
        base_dso_pk_kwh_sum += b_pk_kwh
        base_dso_off_kwh_sum += b_off_kwh
        base_dso_sh_kwh_sum += b_sh_kwh
        base_dso_reg_sum += dso_reg_adj_mo
        base_dso_billed_pk_sum += b_billed_pk_kw
        base_dso_billed_cap_sum += b_billed_cap_kw
        base_tax_kwh_gross_sum += b_tax_kwh_gross
        base_tax_credit_sum += b_tax_credit
        base_tax_kwh_sum += b_tax_kwh
        base_tax_surcharge_sum += b_tax_sur
        base_vat_sum += b_vat_m

        comb_p1_sum += c_p1
        comb_p2_sum += c_p2
        comb_p3_sum += c_p3
        comb_p4_sum += c_p4
        comb_pen_sum += c_pen
        comb_supp_energy_sum += c_supp_en
        comb_supp_ht_sum += c_supp_ht
        comb_supp_nt_sum += c_supp_nt
        comb_supp_gvo_sum += c_supp_gvo
        comb_dso_cap_sum += c_cap
        comb_dso_peak_sum += c_pk
        comb_dso_vol_sum += c_vol
        comb_dso_vol_pk_sum += c_vol_pk
        comb_dso_vol_off_sum += c_vol_off
        comb_dso_vol_sh_sum += c_vol_sh
        comb_dso_pk_kwh_sum += c_pk_kwh
        comb_dso_off_kwh_sum += c_off_kwh
        comb_dso_sh_kwh_sum += c_sh_kwh
        comb_dso_reg_sum += dso_reg_adj_mo
        comb_dso_billed_pk_sum += c_billed_pk_kw
        comb_dso_billed_cap_sum += c_billed_cap_kw
        comb_tax_kwh_gross_sum += c_tax_kwh_gross
        comb_tax_credit_sum += c_tax_credit
        comb_tax_kwh_sum += c_tax_kwh
        comb_tax_surcharge_sum += c_tax_sur
        comb_vat_sum += c_vat_m

        gen_fuel_cost_sum += c_fuel
        gen_maint_cost_sum += c_maint
        gen_rental_cost_sum += c_rent

        # Isolated Peak-Shaving Attribution (no double counting between Battery & Generator)
        m_dso_peak_pen_sav = max(0.0, (b_cap - c_cap) + (b_pk - c_pk) + (b_pen - c_pen) + trafo_rent_mo)
        b_shv_kw = float(bess_shave_kw_m[m_idx_0]) if cfg.enable_battery else 0.0
        g_shv_kw = float(gen_shave_kw_m[m_idx_0]) if cfg.enable_generator else 0.0
        if b_shv_kw > 0.0 and g_shv_kw > 0.0:
            w_bess = b_shv_kw / (b_shv_kw + g_shv_kw)
            w_gen = 1.0 - w_bess
        elif b_shv_kw > 0.0:
            w_bess, w_gen = 1.0, 0.0
        elif g_shv_kw > 0.0:
            w_bess, w_gen = 0.0, 1.0
        elif cfg.enable_battery and b_dis_m_kwh > 0.0:
            w_bess, w_gen = 1.0, 0.0
        elif cfg.enable_generator and g_out_m_kwh > 0.0:
            w_bess, w_gen = 0.0, 1.0
        else:
            w_bess, w_gen = 0.0, 0.0

        m_bat_peak_sav = m_dso_peak_pen_sav * w_bess
        m_gen_peak_sav = m_dso_peak_pen_sav * w_gen
        bat_peak_sav_sum += m_bat_peak_sav
        gen_peak_sav_sum += m_gen_peak_sav

        m_bat_grid_chg_cost = float(bess_chg_grid_m[m_idx_0]) * var_grid_rate if cfg.enable_battery else 0.0
        bat_grid_chg_cost_sum += m_bat_grid_chg_cost

        append_isolated_hardware_monthly_rows(
            m_name=m_name, cfg=cfg, kpis=kpis, var_grid_rate=var_grid_rate, feed_in_rate=feed_in_rate,
            sol_om_monthly=sol_om_monthly, bat_om_monthly=bat_om_monthly,
            sol_gen_m_kwh=sol_gen_m_kwh, sol_dir_m_kwh=sol_dir_m_kwh, sol_bat_m_kwh=sol_bat_m_kwh,
            sol_exp_m_kwh=sol_exp_m_kwh, b_dis_m_kwh=b_dis_m_kwh,
            pv_chg_b_kwh=float(pv_chg_bess_m[m_idx_0]), grd_chg_b_kwh=float(bess_chg_grid_m[m_idx_0]),
            b_shv_kw=b_shv_kw, m_bat_peak_sav=m_bat_peak_sav, m_bat_grid_chg_cost=m_bat_grid_chg_cost,
            gen_hrs=gen_hrs, g_out_m_kwh=g_out_m_kwh, gen_fuel=gen_fuel,
            g_shv_kw=g_shv_kw, m_gen_peak_sav=m_gen_peak_sav,
            c_fuel=c_fuel, c_maint=c_maint, c_rent=c_rent,
            solar_fin_rows=solar_fin_rows, battery_fin_rows=battery_fin_rows, generator_fin_rows=generator_fin_rows,
        )

        # Isolated Monthly Contract Pillar Statements (DSO / Supplier / Taxes & Metering)
        dso_monthly_rows.append({
            "Month": m_name,
            "Current Peak (kW)": round(base_peak_kw, 1),
            "With System Peak (kW)": round(comb_peak_kw, 1),
            "Billed Capacity (kW)": round(c_billed_cap_kw, 1),
            "Fixed Fees (€)": round(dso_fixed_mo, 0),
            "Booked Capacity (€)": round(c_cap, 0),
            "Peak Demand Fee (€)": round(c_pk, 0),
            "kWh Transport (€)": round(c_vol, 0),
            "Overload Penalty (€)": round(c_pen, 0),
            "DSO Current (€)": round(b_p2, 0),
            "DSO With System (€)": round(c_p2, 0),
            "DSO Savings (€)": round(b_p2 - c_p2, 0),
        })
        supplier_monthly_rows.append({
            "Month": m_name,
            "Current Load (kWh)": round(cons_kwh, 0),
            "Grid Import (kWh)": round(comb_imp_kwh, 0),
            "Import Peak HT (€)": round(c_supp_ht, 0),
            "Import Off-Peak NT (€)": round(c_supp_nt, 0),
            "Surcharge & Base (€)": round(c_supp_gvo + supp_fixed_mo, 0),
            "Supplier Current (€)": round(b_p1, 0),
            "Supplier With System (€)": round(c_p1, 0),
            "Supplier Savings (€)": round(b_p1 - c_p1, 0),
        })
        tax_monthly_rows.append({
            "Month": m_name,
            "Metering (€)": round(c_p3, 0),
            "Energy Tax Gross (€)": round(c_tax_kwh_gross, 0),
            "Tax Credit (-€)": round(-c_tax_credit, 0),
            "Tax Surcharge (€)": round(c_tax_sur, 0),
            "VAT With System (€)": round(c_vat_m, 0),
            "Tax & Metering Current (€)": round(b_p3 + b_p4, 0),
            "Tax & Metering System (€)": round(c_p3 + c_p4, 0),
            "Savings (€)": round((b_p3 + b_p4) - (c_p3 + c_p4), 0),
        })

        monthly_cost_rows.append({
            "Month": m_name,
            "Current situation Peak (kW)": round(base_peak_kw, 1),
            "Combined Grid Peak (kW)": round(comb_peak_kw, 1),
            "Combined Grid Import (kWh)": round(comb_imp_kwh, 0),
            "Combined Standing & Metering (€)": round(supp_fixed_mo + dso_fixed_mo + meter_fixed_mo, 2),
            "Combined Booked Capacity (€)": round(c_cap, 2),
            "Combined Peak Demand Fee (€)": round(c_pk, 2),
            "Combined DSO Transport (€)": round(c_vol, 2),
            "Combined DSO Total (€)": round(c_p2, 2),
            "Current situation DSO Total (€)": round(b_p2, 2),
            "Combined Supply & Tax (€)": round(c_supp_en + c_p4, 2),
            "Current situation Supply & Tax (€)": round(b_supp_en + b_p4, 2),
            "Current situation Energy & Taxes (€)": round(b_p1 - supp_fixed_mo + b_p4, 2),
            "Current situation Network & Standing (€)": round(b_p2 - b_pen + supp_fixed_mo + b_p3, 2),
            "Current situation Overload Penalty (€)": round(b_pen, 2),
            "Current situation Total (€)": round(b_tot, 2),
            "Combined Grid Energy & Taxes (€)": round(c_p1 - supp_fixed_mo + c_p4, 2),
            "Combined Network & Standing (€)": round(c_p2 - c_pen + supp_fixed_mo + c_p3, 2),
            "Combined Overload Penalty (€)": round(c_pen, 2),
            "Generator Fuel & Maint & Rental (€)": round(c_fuel + c_maint + c_rent, 2),
            "Solar & Battery O&M (€)": round(om_monthly, 2),
            "Combined System Total OPEX (€)": round(c_tot, 2),
            "Monthly Savings (€)": round(b_tot - c_tot, 2),
        })

    baseline_total_opex = base_p1_sum + base_p2_sum + base_p3_sum + base_p4_sum
    combined_grid_total = comb_p1_sum + comb_p2_sum + comb_p3_sum + comb_p4_sum
    gen_total_opex = gen_fuel_cost_sum + gen_maint_cost_sum + gen_rental_cost_sum

    baseline_vat_eur = base_vat_sum
    baseline_total_gross_eur = baseline_total_opex + baseline_vat_eur
    combined_grid_vat_eur = comb_vat_sum
    combined_grid_gross_eur = combined_grid_total + combined_grid_vat_eur

    solar_export_kwh = float(getattr(kpis, "solar_export_kwh", 0.0)) if cfg.enable_solar else 0.0
    solar_export_rev_y1 = (solar_export_kwh * max(0.0, float(fin_cfg.solar_export_feed_in_eur_kwh))) if cfg.enable_solar else 0.0

    system_om_and_fuel_y1 = solar_om_annual + battery_om_annual + gen_total_opex
    gross_bill_savings_y1 = (baseline_total_opex - combined_grid_total) + solar_export_rev_y1
    total_annual_opex = combined_grid_total + system_om_and_fuel_y1 - solar_export_rev_y1
    annual_savings = baseline_total_opex - total_annual_opex

    # Split Year-1 grid savings into volumetric energy/tax savings (degrades) vs. peak/penalty savings (stable)
    base_vol_portion = (base_supp_energy_sum + base_dso_vol_sum) * (1.0 + tax_pct) + base_tax_kwh_sum
    comb_vol_portion = (comb_supp_energy_sum + comb_dso_vol_sum) * (1.0 + tax_pct) + comb_tax_kwh_sum
    grid_vol_savings = base_vol_portion - comb_vol_portion
    grid_peak_pen_savings = (baseline_total_opex - combined_grid_total) - grid_vol_savings

    # 4. 15-Year Dynamic Lifecycle Cashflow, TCO & NPV Calculation
    r_disc = max(0.0, float(fin_cfg.discount_rate_pct)) / 100.0
    sys_energy_y1 = (
        float(getattr(kpis, "solar_total_supplied_kwh", 0.0))
        + float(getattr(kpis, "battery_total_discharged_kwh", 0.0))
        + float(getattr(kpis, "generator_to_load_kwh", 0.0))
    )
    proj = compute_15y_lifecycle_projection(
        total_capex=total_capex,
        battery_aug_eur=battery_aug_eur,
        aug_yr=int(fin_cfg.battery_augmentation_year),
        baseline_total_opex=baseline_total_opex,
        combined_grid_total=combined_grid_total,
        system_om_and_fuel_y1=system_om_and_fuel_y1,
        solar_export_rev_y1=solar_export_rev_y1,
        annual_savings=annual_savings,
        sys_energy_y1=sys_energy_y1,
        solar_capex=solar_capex,
        solar_om_annual=solar_om_annual,
        solar_total_generation_kwh=float(getattr(kpis, "solar_total_generation_kwh", 0.0)),
        enable_solar=bool(cfg.enable_solar),
        discount_rate_pct=float(fin_cfg.discount_rate_pct),
        tariff_escalation_pct_pa=float(fin_cfg.tariff_escalation_pct_pa),
        om_inflation_pct_pa=float(fin_cfg.om_inflation_pct_pa),
        system_degradation_pct_pa=float(fin_cfg.system_degradation_pct_pa),
        bill_volume_avoided_y1=grid_vol_savings,
        bill_peak_avoided_y1=grid_peak_pen_savings,
    )
    cashflow_rows = proj["cashflow_rows"]
    simple_payback_years = proj["simple_payback_years"]
    discounted_payback_years = proj["discounted_payback_years"]
    npv_acc = proj["npv_acc"]
    irr_val = proj["irr_val"]
    tco_base_acc = proj["tco_base_acc"]
    tco_comb_acc = proj["tco_comb_acc"]
    sys_lcoe = proj["sys_lcoe"]
    solar_iso_lcoe = proj["solar_iso_lcoe"]
    bcr_15y = proj["bcr_15y"]

    # Unit metrics & sub-ledger savings attribution
    ann_cons = max(1.0, float(kpis.annual_consumption_kwh))
    eff_grid_rate = baseline_total_opex / ann_cons

    solar_direct_val = float(getattr(kpis, "solar_direct_kwh", 0.0)) * var_grid_rate if cfg.enable_solar else 0.0
    solar_stored_val = float(getattr(kpis, "solar_via_battery_kwh", 0.0)) * var_grid_rate if (cfg.enable_solar and cfg.enable_battery) else 0.0

    # Isolated component metrics
    solar_gross_val_y1 = (solar_direct_val + solar_stored_val + solar_export_rev_y1) if cfg.enable_solar else 0.0
    solar_net_val_y1 = (solar_gross_val_y1 - solar_om_annual) if cfg.enable_solar else 0.0
    solar_iso_payback = round(solar_capex / solar_net_val_y1, 1) if (cfg.enable_solar and solar_capex > 0.0 and solar_net_val_y1 > 1.0) else (0.0 if (cfg.enable_solar and solar_capex <= 0.0 and solar_net_val_y1 >= 0.0) else None)

    bat_gross_val_y1 = (bat_peak_sav_sum + solar_stored_val - bat_grid_chg_cost_sum) if cfg.enable_battery else 0.0
    bat_net_val_y1 = (bat_gross_val_y1 - battery_om_annual) if cfg.enable_battery else 0.0
    bat_iso_payback = round(battery_capex / bat_net_val_y1, 1) if (cfg.enable_battery and battery_capex > 0.0 and bat_net_val_y1 > 1.0) else (0.0 if (cfg.enable_battery and battery_capex <= 0.0 and bat_net_val_y1 >= 0.0) else None)
    bat_dis_kwh_yr = float(getattr(kpis, "battery_total_discharged_kwh", 0.0))
    bat_annuity = (battery_capex * ((r_disc * ((1.0 + r_disc) ** 15)) / (((1.0 + r_disc) ** 15) - 1.0))) if (r_disc > 0 and battery_capex > 0) else (battery_capex / 15.0)
    bat_cost_per_kwh = ((bat_annuity + battery_om_annual + bat_grid_chg_cost_sum) / bat_dis_kwh_yr) if (cfg.enable_battery and bat_dis_kwh_yr > 1.0) else 0.0

    gen_net_val_y1 = (gen_peak_sav_sum - gen_total_opex) if cfg.enable_generator else 0.0
    gen_iso_payback = round(generator_capex / gen_net_val_y1, 1) if (cfg.enable_generator and generator_capex > 0.0 and gen_net_val_y1 > 1.0) else (0.0 if (cfg.enable_generator and generator_capex <= 0.0 and gen_net_val_y1 >= 0.0) else None)
    gen_kwh_yr = float(getattr(kpis, "generator_to_load_kwh", 0.0))
    gen_annuity = (generator_capex * ((r_disc * ((1.0 + r_disc) ** 15)) / (((1.0 + r_disc) ** 15) - 1.0))) if (r_disc > 0 and generator_capex > 0) else (generator_capex / 15.0)
    gen_cost_per_kwh = ((gen_annuity + gen_total_opex) / gen_kwh_yr) if (cfg.enable_generator and gen_kwh_yr > 1.0) else 0.0

    # Isolated Contract Actor Savings
    dso_savings_eur = base_p2_sum - comb_p2_sum
    dso_savings_pct = (dso_savings_eur / base_p2_sum * 100.0) if base_p2_sum > 1e-6 else 0.0
    supplier_savings_eur = base_p1_sum - comb_p1_sum
    supplier_savings_pct = (supplier_savings_eur / base_p1_sum * 100.0) if base_p1_sum > 1e-6 else 0.0
    tax_metering_savings_eur = (base_p3_sum + base_p4_sum) - (comb_p3_sum + comb_p4_sum)

    congestion_breach_kw = float(getattr(kpis, "remaining_overload_kw", 0.0))
    congestion_compliant = bool(congestion_breach_kw <= 0.05)

    peak_red = float(getattr(kpis, "peak_reduction_kw", 0.0))
    if peak_red > 0.1:
        if r_disc > 0:
            annuity_factor = (r_disc * ((1.0 + r_disc) ** 15)) / (((1.0 + r_disc) ** 15) - 1.0)
            ann_capex = total_capex * annuity_factor
        else:
            ann_capex = total_capex / 15.0
        ann_cost_shaved_kw = (ann_capex + system_om_and_fuel_y1) / peak_red
    else:
        ann_cost_shaved_kw = 0.0

    fin_kpis = CombinedFinancialKPIs(
        solar_capex_eur=round(solar_capex, 0),
        battery_capex_eur=round(battery_capex, 0),
        battery_augmentation_eur=round(battery_aug_eur, 0),
        generator_capex_eur=round(generator_capex, 0),
        gross_capex_eur=round(gross_capex, 0),
        avoided_grid_upgrade_capex_eur=round(avoided_upgrade_capex, 0),
        total_capex_eur=round(total_capex, 0),
        baseline_pillar1_supply_eur=round(base_p1_sum, 0),
        baseline_pillar2_dso_eur=round(base_p2_sum, 0),
        baseline_pillar3_metering_eur=round(base_p3_sum, 0),
        baseline_pillar4_taxes_eur=round(base_p4_sum, 0),
        baseline_energy_cost_eur=round(base_p1_sum + base_p4_sum - 12.0 * supp_fixed_mo, 0),
        baseline_capacity_cost_eur=round(base_p2_sum - base_pen_sum - 12.0 * dso_fixed_mo, 0),
        baseline_fixed_cost_eur=round(12.0 * (supp_fixed_mo + dso_fixed_mo + meter_fixed_mo), 0),
        baseline_penalty_cost_eur=round(base_pen_sum, 0),
        baseline_total_opex_eur=round(baseline_total_opex, 0),
        combined_pillar1_supply_eur=round(comb_p1_sum, 0),
        combined_pillar2_dso_eur=round(comb_p2_sum, 0),
        combined_pillar3_metering_eur=round(comb_p3_sum, 0),
        combined_pillar4_taxes_eur=round(comb_p4_sum, 0),
        combined_grid_energy_cost_eur=round(comb_p1_sum + comb_p4_sum - 12.0 * supp_fixed_mo, 0),
        combined_grid_capacity_cost_eur=round(comb_p2_sum - comb_pen_sum - 12.0 * dso_fixed_mo, 0),
        combined_grid_fixed_cost_eur=round(12.0 * (supp_fixed_mo + dso_fixed_mo + meter_fixed_mo), 0),
        combined_grid_penalty_cost_eur=round(comb_pen_sum, 0),
        combined_grid_total_eur=round(combined_grid_total, 0),
        solar_om_eur=round(solar_om_annual, 0),
        battery_om_eur=round(battery_om_annual, 0),
        generator_fuel_cost_eur=round(gen_fuel_cost_sum, 0),
        generator_maintenance_cost_eur=round(gen_maint_cost_sum, 0),
        generator_rental_cost_eur=round(gen_rental_cost_sum, 0),
        generator_total_opex_eur=round(gen_total_opex, 0),
        total_annual_opex_eur=round(total_annual_opex, 0),
        annual_savings_eur=round(annual_savings, 0),
        payback_years=simple_payback_years,
        npv_15y_eur=round(npv_acc, 0),
        solar_export_revenue_eur=round(solar_export_rev_y1, 0),
        gross_bill_savings_y1_eur=round(gross_bill_savings_y1, 0),
        system_om_and_fuel_y1_eur=round(system_om_and_fuel_y1, 0),
        discounted_payback_years=discounted_payback_years,
        irr_15y_pct=irr_val,
        tco_15y_baseline_eur=round(tco_base_acc, 0),
        tco_15y_combined_eur=round(tco_comb_acc, 0),
        tco_15y_savings_eur=round(tco_base_acc - tco_comb_acc, 0),
        effective_blended_grid_rate_eur_kwh=round(eff_grid_rate, 4),
        system_lcoe_eur_kwh=round(sys_lcoe, 4),
        annualized_cost_per_shaved_kw_eur=round(ann_cost_shaved_kw, 1),
        baseline_supply_energy_eur=round(base_supp_energy_sum, 2),
        combined_supply_energy_eur=round(comb_supp_energy_sum, 2),
        baseline_supply_fixed_eur=round(12.0 * supp_fixed_mo, 2),
        combined_supply_fixed_eur=round(12.0 * supp_fixed_mo, 2),
        baseline_dso_fixed_eur=round(12.0 * dso_fixed_mo, 2),
        combined_dso_fixed_eur=round(12.0 * dso_fixed_mo, 2),
        baseline_dso_capacity_eur=round(base_dso_cap_sum, 2),
        combined_dso_capacity_eur=round(comb_dso_cap_sum, 2),
        baseline_dso_peak_eur=round(base_dso_peak_sum, 2),
        combined_dso_peak_eur=round(comb_dso_peak_sum, 2),
        baseline_dso_transport_eur=round(base_dso_vol_sum, 2),
        combined_dso_transport_eur=round(comb_dso_vol_sum, 2),
        baseline_dso_transformer_rent_eur=round(12.0 * trafo_rent_mo, 2),
        combined_dso_transformer_rent_eur=0.0,
        baseline_energy_tax_eur=round(base_tax_kwh_sum, 2),
        combined_energy_tax_eur=round(comb_tax_kwh_sum, 2),
        baseline_tax_surcharge_eur=round(base_tax_surcharge_sum, 2),
        combined_tax_surcharge_eur=round(comb_tax_surcharge_sum, 2),
        solar_modules_capex_eur=round(solar_modules_capex, 0),
        solar_inverter_capex_eur=round(solar_inverter_capex, 0),
        solar_mounting_capex_eur=round(solar_mounting_capex, 0),
        battery_rack_capex_eur=round(battery_rack_capex, 0),
        battery_inverter_capex_eur=round(battery_inv_capex, 0),
        battery_bop_capex_eur=round(battery_bop_capex, 0),
        variable_grid_rate_eur_kwh=round(var_grid_rate, 4),
        grid_volume_savings_y1_eur=round(grid_vol_savings, 0),
        grid_peak_and_penalty_savings_y1_eur=round(grid_peak_pen_savings, 0),
        solar_direct_value_y1_eur=round(solar_direct_val, 0),
        solar_stored_value_y1_eur=round(solar_stored_val, 0),
        baseline_supply_peak_ht_eur=round(base_supp_ht_sum, 2),
        combined_supply_peak_ht_eur=round(comb_supp_ht_sum, 2),
        baseline_supply_offpeak_nt_eur=round(base_supp_nt_sum, 2),
        combined_supply_offpeak_nt_eur=round(comb_supp_nt_sum, 2),
        baseline_supply_gvo_eur=round(base_supp_gvo_sum, 2),
        combined_supply_gvo_eur=round(comb_supp_gvo_sum, 2),
        baseline_dso_connection_eur=round(12.0 * dso_conn_mo, 2),
        combined_dso_connection_eur=round(12.0 * dso_conn_mo, 2),
        baseline_dso_transport_fixed_eur=round(12.0 * dso_trans_fix_mo, 2),
        combined_dso_transport_fixed_eur=round(12.0 * dso_trans_fix_mo, 2),
        baseline_dso_breach_months=int(base_breach_months),
        combined_dso_breach_months=int(comb_breach_months),
        baseline_energy_tax_gross_eur=round(base_tax_kwh_gross_sum, 2),
        combined_energy_tax_gross_eur=round(comb_tax_kwh_gross_sum, 2),
        baseline_tax_credit_eur=round(base_tax_credit_sum, 2),
        combined_tax_credit_eur=round(comb_tax_credit_sum, 2),
        baseline_vat_eur=round(baseline_vat_eur, 0),
        combined_grid_vat_eur=round(combined_grid_vat_eur, 0),
        baseline_total_gross_eur=round(baseline_total_gross_eur, 0),
        combined_grid_gross_eur=round(combined_grid_gross_eur, 0),
        grid_congestion_compliant=congestion_compliant,
        grid_congestion_breach_kw=round(congestion_breach_kw, 1),
        grid_congestion_breach_months=int(comb_breach_months),
        dso_savings_eur=round(dso_savings_eur, 0),
        dso_savings_pct=round(dso_savings_pct, 1),
        supplier_savings_eur=round(supplier_savings_eur, 0),
        supplier_savings_pct=round(supplier_savings_pct, 1),
        tax_and_metering_savings_eur=round(tax_metering_savings_eur, 0),
        benefit_cost_ratio_15y=round(bcr_15y, 2),
        solar_gross_value_y1_eur=round(solar_gross_val_y1, 0),
        solar_net_value_y1_eur=round(solar_net_val_y1, 0),
        solar_isolated_payback_years=solar_iso_payback,
        solar_isolated_lcoe_eur_kwh=round(solar_iso_lcoe, 4),
        battery_peak_savings_y1_eur=round(bat_peak_sav_sum, 0),
        battery_grid_charge_cost_y1_eur=round(bat_grid_chg_cost_sum, 0),
        battery_gross_value_y1_eur=round(bat_gross_val_y1, 0),
        battery_net_value_y1_eur=round(bat_net_val_y1, 0),
        battery_isolated_payback_years=bat_iso_payback,
        battery_cost_per_discharged_kwh=round(bat_cost_per_kwh, 4),
        generator_peak_savings_y1_eur=round(gen_peak_sav_sum, 0),
        generator_net_value_y1_eur=round(gen_net_val_y1, 0),
        generator_isolated_payback_years=gen_iso_payback,
        generator_cost_per_kwh=round(gen_cost_per_kwh, 4),
        currency_code=str(getattr(fin_cfg, "currency_code", "EUR") or "EUR"),
        baseline_dso_vol_peak_eur=round(base_dso_vol_pk_sum, 2),
        combined_dso_vol_peak_eur=round(comb_dso_vol_pk_sum, 2),
        baseline_dso_vol_offpeak_eur=round(base_dso_vol_off_sum, 2),
        combined_dso_vol_offpeak_eur=round(comb_dso_vol_off_sum, 2),
        baseline_dso_vol_shoulder_eur=round(base_dso_vol_sh_sum, 2),
        combined_dso_vol_shoulder_eur=round(comb_dso_vol_sh_sum, 2),
        baseline_dso_peak_tou_kwh=round(base_dso_pk_kwh_sum, 1),
        combined_dso_peak_tou_kwh=round(comb_dso_pk_kwh_sum, 1),
        baseline_dso_offpeak_tou_kwh=round(base_dso_off_kwh_sum, 1),
        combined_dso_offpeak_tou_kwh=round(comb_dso_off_kwh_sum, 1),
        baseline_dso_shoulder_tou_kwh=round(base_dso_sh_kwh_sum, 1),
        combined_dso_shoulder_tou_kwh=round(comb_dso_sh_kwh_sum, 1),
        baseline_dso_regulatory_adj_eur=round(base_dso_reg_sum, 2),
        combined_dso_regulatory_adj_eur=round(comb_dso_reg_sum, 2),
        baseline_dso_billed_peak_avg_kw=round(base_dso_billed_pk_sum / 12.0, 1),
        combined_dso_billed_peak_avg_kw=round(comb_dso_billed_pk_sum / 12.0, 1),
        baseline_dso_billed_cap_avg_kw=round(base_dso_billed_cap_sum / 12.0, 1),
        combined_dso_billed_cap_avg_kw=round(comb_dso_billed_cap_sum / 12.0, 1),
        solar_pricing_mode=hw_res["solar_pricing_mode"],
        solar_opex_pricing_mode=hw_res["solar_opex_mode"],
        solar_implied_eur_kwp=round(hw_res["solar_implied_kwp"], 2),
        battery_pricing_mode=hw_res["battery_pricing_mode"],
        battery_opex_pricing_mode=hw_res["battery_opex_mode"],
        battery_repowering_mode=hw_res["battery_repowering_mode"],
        battery_implied_eur_kwh=round(hw_res["battery_implied_kwh"], 2),
        battery_implied_eur_kw=round(hw_res["battery_implied_kw"], 2),
        generator_pricing_mode=hw_res["generator_pricing_mode"],
        generator_opex_pricing_mode=hw_res["generator_opex_mode"],
        generator_implied_eur_kw=round(hw_res["generator_implied_kw"], 2),
    )

    sim_res.financial_config = fin_cfg
    sim_res.financial_kpis = fin_kpis
    sim_res.financial_table_df = build_financial_summary_table_df(
        cfg=cfg,
        solar_deriv=solar_deriv,
        kpis=kpis,
        fin_kpis=fin_kpis,
        simple_payback_years=simple_payback_years,
        solar_iso_payback=solar_iso_payback,
        bat_iso_payback=bat_iso_payback,
        gen_iso_payback=gen_iso_payback,
    )
    sim_res.monthly_cost_df = pd.DataFrame(monthly_cost_rows)
    sim_res.cashflow_15y_df = pd.DataFrame(cashflow_rows)
    sim_res.dso_monthly_df = pd.DataFrame(dso_monthly_rows)
    sim_res.supplier_monthly_df = pd.DataFrame(supplier_monthly_rows)
    sim_res.tax_monthly_df = pd.DataFrame(tax_monthly_rows)
    sim_res.solar_fin_monthly_df = pd.DataFrame(solar_fin_rows)
    sim_res.battery_fin_monthly_df = pd.DataFrame(battery_fin_rows)
    sim_res.generator_fin_monthly_df = pd.DataFrame(generator_fin_rows)
    return sim_res
