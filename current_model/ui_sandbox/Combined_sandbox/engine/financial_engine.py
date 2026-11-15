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

def _calculate_irr(cashflows: List[float], max_iter: int = 200, tol: float = 1e-5) -> Optional[float]:
    """
    Computes the Internal Rate of Return (IRR in %) for an investment cashflow stream.
    cashflows[0] is initial negative investment (-CAPEX).
    Returns None if cashflows never break even or do not cross zero.
    """
    if len(cashflows) < 2 or cashflows[0] >= 0.0 or sum(cashflows[1:]) <= 0.0:
        return None

    def npv_at_r(r: float) -> float:
        val = 0.0
        for t, cf in enumerate(cashflows):
            val += cf / ((1.0 + r) ** t)
        return val

    # Test range -0.90 (-90%) to 5.0 (500%)
    low, high = -0.90, 5.0
    f_low, f_high = npv_at_r(low), npv_at_r(high)
    if f_low * f_high > 0:
        return None

    for _ in range(max_iter):
        mid = (low + high) / 2.0
        f_mid = npv_at_r(mid)
        if abs(f_mid) < tol or (high - low) / 2.0 < tol:
            return round(mid * 100.0, 1)
        if f_low * f_mid < 0:
            high = mid
            f_high = f_mid
        else:
            low = mid
            f_low = f_mid

    return round(((low + high) / 2.0) * 100.0, 1)

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

    # 1. Itemized Turnkey CAPEX
    solar_capex_kwp = fin_cfg.effective_solar_capex_eur_kwp
    solar_capex = (solar_deriv.installed_kwp * solar_capex_kwp) if cfg.enable_solar else 0.0
    if cfg.enable_solar:
        if fin_cfg.solar_capex_eur_kwp is not None:
            solar_modules_capex = solar_capex
            solar_inverter_capex = 0.0
            solar_mounting_capex = 0.0
        else:
            solar_modules_capex = solar_deriv.installed_kwp * 1000.0 * float(fin_cfg.solar_modules_eur_wp)
            solar_inverter_capex = solar_deriv.installed_kwp * 1000.0 * float(fin_cfg.solar_inverter_eur_w)
            solar_mounting_capex = solar_deriv.installed_kwp * 1000.0 * float(fin_cfg.solar_mounting_eur_wp)
    else:
        solar_modules_capex = 0.0
        solar_inverter_capex = 0.0
        solar_mounting_capex = 0.0

    battery_rack_capex = cfg.battery_capacity_kwh * fin_cfg.battery_capex_eur_kwh if cfg.enable_battery else 0.0
    battery_inv_capex = cfg.battery_power_kw * fin_cfg.battery_capex_eur_kw if cfg.enable_battery else 0.0
    battery_bop_capex = fin_cfg.battery_fixed_bop_eur if (cfg.enable_battery and cfg.battery_capacity_kwh > 0) else 0.0
    battery_capex = (battery_rack_capex + battery_inv_capex + battery_bop_capex) if cfg.enable_battery else 0.0

    battery_aug_eur = (
        battery_rack_capex * (fin_cfg.battery_augmentation_pct_of_racks / 100.0)
        if (cfg.enable_battery and fin_cfg.enable_battery_augmentation)
        else 0.0
    )

    gen_is_purchase = fin_cfg.generator_cost_model == "Purchase (CAPEX)"
    generator_capex = fin_cfg.generator_capex_eur if (cfg.enable_generator and gen_is_purchase) else 0.0
    gross_capex = solar_capex + battery_capex + generator_capex
    avoided_upgrade_capex = (
        0.0
        if fin_cfg.strict_grid_congestion_mode
        else max(0.0, float(fin_cfg.avoided_grid_upgrade_capex_eur))
    )
    net_total_capex = max(0.0, gross_capex - avoided_upgrade_capex)
    total_capex = net_total_capex

    # 2. Resolve 4-Pillar Rates
    is_legacy_energy = fin_cfg.grid_energy_price_eur_kwh is not None
    if is_legacy_energy:
        supp_kwh_rate = float(fin_cfg.grid_energy_price_eur_kwh)
        tax_kwh_rate = 0.0
        gvo_rate = 0.0
        is_dual_tou = False
    else:
        supp_kwh_rate = float(fin_cfg.supplier_energy_price_eur_kwh)
        tax_kwh_rate = float(fin_cfg.energy_tax_eur_kwh)
        gvo_rate = max(0.0, float(fin_cfg.supplier_gvo_surcharge_eur_kwh))
        is_dual_tou = str(fin_cfg.supplier_pricing_mode) == "dual_tou"

    supp_ht_rate = float(fin_cfg.supplier_peak_ht_eur_kwh)
    supp_nt_rate = float(fin_cfg.supplier_offpeak_nt_eur_kwh)

    if fin_cfg.grid_capacity_fee_eur_kw_month is not None:
        dso_cap_rate = float(fin_cfg.grid_capacity_fee_eur_kw_month)
        dso_peak_rate = 0.0
    else:
        dso_cap_rate = float(fin_cfg.dso_capacity_fee_eur_kw_month)
        dso_peak_rate = float(fin_cfg.dso_peak_demand_fee_eur_kw_month)

    if fin_cfg.grid_fixed_fee_eur_month is not None:
        supp_fixed_mo = 0.0
        dso_conn_mo = 0.0
        dso_trans_fix_mo = float(fin_cfg.grid_fixed_fee_eur_month)
        dso_fixed_mo = dso_trans_fix_mo
        meter_fixed_mo = 0.0
    else:
        supp_fixed_mo = float(fin_cfg.supplier_fixed_fee_eur_month)
        dso_conn_mo = max(0.0, float(fin_cfg.dso_connection_fee_eur_month))
        dso_trans_fix_mo = max(0.0, float(fin_cfg.dso_fixed_fee_eur_month))
        dso_fixed_mo = dso_conn_mo + dso_trans_fix_mo
        meter_fixed_mo = float(fin_cfg.metering_fixed_fee_eur_month)

    pen_rate_kw = float(fin_cfg.grid_overload_penalty_eur_kw)
    tax_pct = float(fin_cfg.tax_surcharge_pct) / 100.0
    dso_vol_rate = float(fin_cfg.dso_transport_eur_kwh)
    trafo_rent_mo = float(fin_cfg.avoided_transformer_rent_eur_month)
    vat_frac = max(0.0, float(fin_cfg.vat_rate_pct)) / 100.0
    annual_tax_credit = 0.0 if is_legacy_energy else max(0.0, float(fin_cfg.annual_tax_reduction_credit_eur))

    # 2b. Aggregate 15-Minute TOU Windows & Component Dispatches per Month
    n_steps = len(sim_res.load_kw)
    dt = 0.25
    cons_ht_m = np.zeros(12, dtype=float)
    cons_nt_m = np.zeros(12, dtype=float)
    imp_ht_m = np.zeros(12, dtype=float)
    imp_nt_m = np.zeros(12, dtype=float)
    pv_chg_bess_m = np.zeros(12, dtype=float)
    bess_chg_grid_m = np.zeros(12, dtype=float)
    bess_chg_gen_m = np.zeros(12, dtype=float)
    gen_to_load_m = np.zeros(12, dtype=float)
    bess_shave_kw_m = np.zeros(12, dtype=float)
    gen_shave_kw_m = np.zeros(12, dtype=float)

    ts = sim_res.timestamps
    if n_steps > 0 and isinstance(ts, pd.DatetimeIndex) and len(ts) == n_steps:
        m_arr = ts.month.to_numpy(dtype=np.intp) - 1
        is_peak_tou = (ts.dayofweek < 5) & (ts.hour >= 7) & (ts.hour < 23)
        p_load_arr = np.maximum(0.0, np.asarray(sim_res.load_kw, dtype=float))
        p_imp_arr = np.maximum(0.0, np.asarray(sim_res.grid_import_kw, dtype=float))
        p_bess_dis_arr = np.maximum(0.0, np.asarray(sim_res.bess_discharge_kw, dtype=float))
        p_bess_chg_sol_arr = np.maximum(0.0, np.asarray(sim_res.bess_charge_solar_kw, dtype=float))
        p_bess_chg_grd_arr = np.maximum(0.0, np.asarray(sim_res.bess_charge_grid_kw, dtype=float))
        p_bess_chg_gen_arr = np.maximum(0.0, np.asarray(sim_res.bess_charge_gen_kw, dtype=float))
        p_gen_load_arr = np.maximum(0.0, np.asarray(sim_res.gen_to_load_kw, dtype=float))

        cons_ht_m = np.bincount(m_arr, weights=p_load_arr * is_peak_tou, minlength=12) * dt
        cons_nt_m = np.bincount(m_arr, weights=p_load_arr * (~is_peak_tou), minlength=12) * dt
        imp_ht_m = np.bincount(m_arr, weights=p_imp_arr * is_peak_tou, minlength=12) * dt
        imp_nt_m = np.bincount(m_arr, weights=p_imp_arr * (~is_peak_tou), minlength=12) * dt
        pv_chg_bess_m = np.bincount(m_arr, weights=p_bess_chg_sol_arr, minlength=12) * dt
        bess_chg_grid_m = np.bincount(m_arr, weights=p_bess_chg_grd_arr, minlength=12) * dt
        bess_chg_gen_m = np.bincount(m_arr, weights=p_bess_chg_gen_arr, minlength=12) * dt
        gen_to_load_m = np.bincount(m_arr, weights=p_gen_load_arr, minlength=12) * dt

        over_mask = p_load_arr > cfg.grid_limit_kw
        for m_i in range(12):
            m_over = (m_arr == m_i) & over_mask
            if np.any(m_over):
                if cfg.enable_battery:
                    bess_shave_kw_m[m_i] = float(np.max(p_bess_dis_arr[m_over]))
                if cfg.enable_generator:
                    gen_shave_kw_m[m_i] = float(np.max(p_gen_load_arr[m_over]))

    if cfg.enable_solar and cfg.enable_battery and np.sum(pv_chg_bess_m) > 1e-6:
        sol_via_bess_m = pv_chg_bess_m * (float(getattr(kpis, "solar_via_battery_kwh", 0.0)) / float(np.sum(pv_chg_bess_m)))
    else:
        sol_via_bess_m = np.zeros(12, dtype=float)

    # 3. Monthly 4-Pillar Grid & Operational Costs (12 Months)
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
    base_tax_kwh_gross_sum = 0.0
    base_tax_credit_sum = 0.0
    base_tax_kwh_sum = 0.0
    base_tax_surcharge_sum = 0.0
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
    comb_tax_kwh_gross_sum = 0.0
    comb_tax_credit_sum = 0.0
    comb_tax_kwh_sum = 0.0
    comb_tax_surcharge_sum = 0.0
    comb_breach_months = 0

    gen_fuel_cost_sum = 0.0
    gen_maint_cost_sum = 0.0
    gen_rental_cost_sum = 0.0

    solar_om_annual = solar_capex * (fin_cfg.solar_om_pct_of_capex / 100.0)
    battery_om_annual = battery_capex * (fin_cfg.battery_om_pct_of_capex / 100.0)
    sol_om_monthly = solar_om_annual / 12.0
    bat_om_monthly = battery_om_annual / 12.0
    om_monthly = sol_om_monthly + bat_om_monthly
    feed_in_rate = max(0.0, float(fin_cfg.solar_export_feed_in_eur_kwh)) if cfg.enable_solar else 0.0

    # First estimate blended variable rate for monthly Solar & Battery value attribution
    eff_supp_rate_base = supp_kwh_rate
    if is_dual_tou:
        tot_ht_imp = float(np.sum(imp_ht_m))
        tot_nt_imp = float(np.sum(imp_nt_m))
        if tot_ht_imp + tot_nt_imp > 1.0:
            eff_supp_rate_base = (tot_ht_imp * supp_ht_rate + tot_nt_imp * supp_nt_rate) / (tot_ht_imp + tot_nt_imp)
    eff_tax_kwh_rate = tax_kwh_rate * (1.0 - comb_credit_ratio) if comb_gross_tax_tot > 1e-9 else tax_kwh_rate
    var_grid_rate = (eff_supp_rate_base + gvo_rate + dso_vol_rate) * (1.0 + tax_pct) + eff_tax_kwh_rate

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

        # Resolve monthly HT/NT kWh preserving exact monthly balance sums
        if is_dual_tou:
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
        else:
            b_ht_kwh, b_nt_kwh = cons_kwh, 0.0
            c_ht_kwh, c_nt_kwh = comb_imp_kwh, 0.0
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

        # Pillar 2: DSO (with optional breach capacity step-up)
        base_is_breach = bool(base_peak_kw > cfg.grid_limit_kw + 0.05)
        comb_is_breach = bool(comb_peak_kw > cfg.grid_limit_kw + 0.05)
        if base_is_breach:
            base_breach_months += 1
        if comb_is_breach:
            comb_breach_months += 1

        b_billed_cap_kw = max(cfg.grid_limit_kw, base_peak_kw) if fin_cfg.dso_adjust_capacity_on_breach else cfg.grid_limit_kw
        c_billed_cap_kw = max(cfg.grid_limit_kw, comb_peak_kw) if fin_cfg.dso_adjust_capacity_on_breach else cfg.grid_limit_kw

        b_pen = base_over_kw * pen_rate_kw
        b_cap = b_billed_cap_kw * dso_cap_rate
        b_pk = base_peak_kw * dso_peak_rate
        b_vol = cons_kwh * dso_vol_rate
        b_p2 = b_cap + b_pk + dso_fixed_mo + b_vol + trafo_rent_mo + b_pen

        c_pen = comb_over_kw * pen_rate_kw
        c_cap = c_billed_cap_kw * dso_cap_rate
        c_pk = comb_peak_kw * dso_peak_rate
        c_vol = comb_imp_kwh * dso_vol_rate
        c_p2 = c_cap + c_pk + dso_fixed_mo + c_vol + c_pen

        # Pillar 3: Metering
        b_p3 = meter_fixed_mo
        c_p3 = meter_fixed_mo

        # Pillar 4: Taxes & Tax Credit
        b_tax_kwh_gross = cons_kwh * tax_kwh_rate
        b_tax_credit = b_tax_kwh_gross * base_credit_ratio
        b_tax_kwh = b_tax_kwh_gross - b_tax_credit
        b_tax_sur = (b_p1 + b_p2 + b_p3) * tax_pct
        b_p4 = b_tax_kwh + b_tax_sur
        b_tot = b_p1 + b_p2 + b_p3 + b_p4

        c_tax_kwh_gross = comb_imp_kwh * tax_kwh_rate
        c_tax_credit = c_tax_kwh_gross * comb_credit_ratio
        c_tax_kwh = c_tax_kwh_gross - c_tax_credit
        c_tax_sur = (c_p1 + c_p2 + c_p3) * tax_pct
        c_p4 = c_tax_kwh + c_tax_sur

        c_fuel = (gen_fuel * fin_cfg.fuel_price_eur_per_unit) if cfg.enable_generator else 0.0
        c_maint = (gen_hrs * fin_cfg.generator_maintenance_eur_per_hour) if cfg.enable_generator else 0.0
        c_rent = fin_cfg.generator_rental_eur_month if (cfg.enable_generator and not gen_is_purchase) else 0.0
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
        base_tax_kwh_gross_sum += b_tax_kwh_gross
        base_tax_credit_sum += b_tax_credit
        base_tax_kwh_sum += b_tax_kwh
        base_tax_surcharge_sum += b_tax_sur

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
        comb_tax_kwh_gross_sum += c_tax_kwh_gross
        comb_tax_credit_sum += c_tax_credit
        comb_tax_kwh_sum += c_tax_kwh
        comb_tax_surcharge_sum += c_tax_sur

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

        # Isolated Monthly Solar Economics
        m_sol_dir_val = sol_dir_m_kwh * var_grid_rate
        m_sol_shift_val = sol_bat_m_kwh * var_grid_rate
        m_sol_exp_rev = sol_exp_m_kwh * feed_in_rate
        m_sol_om = sol_om_monthly if cfg.enable_solar else 0.0
        m_sol_net = m_sol_dir_val + m_sol_shift_val + m_sol_exp_rev - m_sol_om
        solar_fin_rows.append({
            "Month": m_name,
            "PV Total (kWh)": round(sol_gen_m_kwh, 0),
            "Direct Used (kWh)": round(sol_dir_m_kwh, 0),
            "Via Battery (kWh)": round(sol_bat_m_kwh, 0),
            "Exported (kWh)": round(sol_exp_m_kwh, 0),
            "Direct Savings (€)": round(m_sol_dir_val, 0),
            "Battery-Shift Value (€)": round(m_sol_shift_val, 0),
            "Export Revenue (€)": round(m_sol_exp_rev, 0),
            "Solar O&M (€)": round(m_sol_om, 0),
            "Net Solar Benefit (€)": round(m_sol_net, 0),
        })

        # Isolated Monthly Battery Economics
        m_bat_om = bat_om_monthly if cfg.enable_battery else 0.0
        m_bat_net = m_bat_peak_sav + m_sol_shift_val - m_bat_grid_chg_cost - m_bat_om
        battery_fin_rows.append({
            "Month": m_name,
            "Discharged (kWh)": round(b_dis_m_kwh, 0),
            "Solar Charged (kWh)": round(float(pv_chg_bess_m[m_idx_0]) if cfg.enable_battery else 0.0, 0),
            "Grid Charged (kWh)": round(float(bess_chg_grid_m[m_idx_0]) if cfg.enable_battery else 0.0, 0),
            "Peak Shaved (kW)": round(b_shv_kw, 1),
            "DSO Peak & Penalty Savings (€)": round(m_bat_peak_sav, 0),
            "Solar Shift Value (€)": round(m_sol_shift_val, 0),
            "Grid Charging Cost (€)": round(m_bat_grid_chg_cost, 0),
            "Battery O&M (€)": round(m_bat_om, 0),
            "Net Battery Benefit (€)": round(m_bat_net, 0),
        })

        # Isolated Monthly Generator Economics
        m_gen_opex = c_fuel + c_maint + c_rent
        m_gen_net = m_gen_peak_sav - m_gen_opex
        generator_fin_rows.append({
            "Month": m_name,
            "Runtime (hrs)": round(gen_hrs if cfg.enable_generator else 0.0, 1),
            "Generated (kWh)": round(g_out_m_kwh, 0),
            f"Fuel ({kpis.generator_fuel_unit})": round(gen_fuel if cfg.enable_generator else 0.0, 1),
            "Peak Shaved (kW)": round(g_shv_kw, 1),
            "Avoided DSO Value (€)": round(m_gen_peak_sav, 0),
            "Fuel & Service (€)": round(c_fuel + c_maint, 0),
            "Rental (€)": round(c_rent, 0),
            "Net Generator Impact (€)": round(m_gen_net, 0),
        })

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
            "VAT With System (€)": round((c_p1 + c_p2 + c_p3 + c_p4) * vat_frac, 0),
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

    baseline_vat_eur = baseline_total_opex * vat_frac
    baseline_total_gross_eur = baseline_total_opex + baseline_vat_eur
    combined_grid_vat_eur = combined_grid_total * vat_frac
    combined_grid_gross_eur = combined_grid_total + combined_grid_vat_eur

    solar_export_kwh = float(getattr(kpis, "solar_export_kwh", 0.0)) if cfg.enable_solar else 0.0
    solar_export_rev_y1 = (solar_export_kwh * max(0.0, float(fin_cfg.solar_export_feed_in_eur_kwh))) if cfg.enable_solar else 0.0

    system_om_and_fuel_y1 = solar_om_annual + battery_om_annual + gen_total_opex
    gross_bill_savings_y1 = (baseline_total_opex - combined_grid_total) + solar_export_rev_y1
    total_annual_opex = combined_grid_total + system_om_and_fuel_y1 - solar_export_rev_y1
    annual_savings = baseline_total_opex - total_annual_opex

    # 4. 15-Year Dynamic Lifecycle Cashflow, TCO & NPV Calculation
    r_disc = max(0.0, float(fin_cfg.discount_rate_pct)) / 100.0
    r_tariff = max(0.0, float(fin_cfg.tariff_escalation_pct_pa)) / 100.0
    r_om = max(0.0, float(fin_cfg.om_inflation_pct_pa)) / 100.0
    d_sys = max(0.0, float(fin_cfg.system_degradation_pct_pa)) / 100.0
    aug_yr = int(fin_cfg.battery_augmentation_year)

    bill_avoided_y1 = max(0.0, baseline_total_opex - combined_grid_total)

    cashflow_rows = []
    cum_cf = -total_capex
    cum_disc_cf = -total_capex
    npv_acc = -total_capex

    cashflow_rows.append({
        "Year": 0,
        "Tariff Escalation Factor": 1.0,
        "Investment & Augmentation (€)": round(-total_capex, 0),
        "Current situation Bill (€)": 0.0,
        "Combined Grid Bill (€)": 0.0,
        "System O&M & Fuel (€)": 0.0,
        "Export Revenue (€)": 0.0,
        "Combined System OPEX (€)": 0.0,
        "Annual Net Savings (€)": 0.0,
        "Net Cashflow (€)": round(-total_capex, 0),
        "Cumulative Cashflow (€)": round(cum_cf, 0),
        "Discounted Cashflow (€)": round(-total_capex, 0),
        "Cumulative TCO Current situation (€)": 0.0,
        "Cumulative TCO Combined system (€)": round(total_capex, 0),
    })

    tco_base_acc = 0.0
    tco_comb_acc = total_capex
    net_cfs_for_irr = [-total_capex]
    simple_payback_years: Optional[float] = None
    discounted_payback_years: Optional[float] = None

    disc_sys_energy_acc = 0.0
    disc_sys_cost_acc = total_capex

    sys_energy_y1 = float(getattr(kpis, "solar_total_supplied_kwh", 0.0)) + float(getattr(kpis, "battery_total_discharged_kwh", 0.0)) + float(getattr(kpis, "generator_to_load_kwh", 0.0))

    for yr in range(1, 16):
        esc_tariff = (1.0 + r_tariff) ** (yr - 1)
        esc_om = (1.0 + r_om) ** (yr - 1)
        deg_factor = max(0.0, (1.0 - d_sys) ** (yr - 1))

        b_bill_yr = baseline_total_opex * esc_tariff
        avoided_bill_yr = bill_avoided_y1 * deg_factor * esc_tariff
        c_grid_yr = max(0.0, b_bill_yr - avoided_bill_yr)

        om_sys_yr = system_om_and_fuel_y1 * esc_om
        exp_rev_yr = solar_export_rev_y1 * deg_factor * esc_tariff

        c_tot_yr = c_grid_yr + om_sys_yr - exp_rev_yr
        savings_yr = b_bill_yr - c_tot_yr

        yr_aug = -battery_aug_eur if (battery_aug_eur > 0.0 and yr == aug_yr) else 0.0
        net_cf = savings_yr + yr_aug
        net_cfs_for_irr.append(net_cf)

        prev_cf = cum_cf
        cum_cf += net_cf

        disc_cf = net_cf / ((1.0 + r_disc) ** yr)
        prev_disc_cf = cum_disc_cf
        cum_disc_cf += disc_cf
        npv_acc += disc_cf

        # Check payback crossings
        if total_capex > 0.0:
            if simple_payback_years is None and cum_cf >= 0.0:
                fraction = (-prev_cf) / max(1e-6, net_cf) if net_cf > 0 else 0.0
                simple_payback_years = round((yr - 1) + max(0.0, min(1.0, fraction)), 1)

            if discounted_payback_years is None and cum_disc_cf >= 0.0:
                fraction = (-prev_disc_cf) / max(1e-6, disc_cf) if disc_cf > 0 else 0.0
                discounted_payback_years = round((yr - 1) + max(0.0, min(1.0, fraction)), 1)

        tco_base_acc += b_bill_yr
        tco_comb_acc += (c_tot_yr + abs(yr_aug))

        disc_sys_energy_acc += (sys_energy_y1 * deg_factor) / ((1.0 + r_disc) ** yr)
        disc_sys_cost_acc += (om_sys_yr + abs(yr_aug)) / ((1.0 + r_disc) ** yr)

        cashflow_rows.append({
            "Year": yr,
            "Tariff Escalation Factor": round(esc_tariff, 3),
            "Investment & Augmentation (€)": round(yr_aug, 0),
            "Current situation Bill (€)": round(b_bill_yr, 0),
            "Combined Grid Bill (€)": round(c_grid_yr, 0),
            "System O&M & Fuel (€)": round(om_sys_yr, 0),
            "Export Revenue (€)": round(exp_rev_yr, 0),
            "Combined System OPEX (€)": round(c_tot_yr, 0),
            "Annual Net Savings (€)": round(savings_yr, 0),
            "Net Cashflow (€)": round(net_cf, 0),
            "Cumulative Cashflow (€)": round(cum_cf, 0),
            "Discounted Cashflow (€)": round(disc_cf, 0),
            "Cumulative TCO Current situation (€)": round(tco_base_acc, 0),
            "Cumulative TCO Combined system (€)": round(tco_comb_acc, 0),
        })

    if total_capex <= 0.0:
        simple_payback_years = 0.0 if annual_savings >= 0.0 else None
        discounted_payback_years = 0.0 if annual_savings >= 0.0 else None

    irr_val = _calculate_irr(net_cfs_for_irr)

    # Unit metrics & sub-ledger savings attribution
    ann_cons = max(1.0, float(kpis.annual_consumption_kwh))
    eff_grid_rate = baseline_total_opex / ann_cons
    sys_lcoe = (disc_sys_cost_acc / disc_sys_energy_acc) if disc_sys_energy_acc > 1.0 else 0.0

    base_vol_portion = (base_supp_energy_sum + base_dso_vol_sum) * (1.0 + tax_pct) + base_tax_kwh_sum
    comb_vol_portion = (comb_supp_energy_sum + comb_dso_vol_sum) * (1.0 + tax_pct) + comb_tax_kwh_sum
    grid_vol_savings = base_vol_portion - comb_vol_portion
    grid_peak_pen_savings = (baseline_total_opex - combined_grid_total) - grid_vol_savings

    solar_direct_val = float(getattr(kpis, "solar_direct_kwh", 0.0)) * var_grid_rate if cfg.enable_solar else 0.0
    solar_stored_val = float(getattr(kpis, "solar_via_battery_kwh", 0.0)) * var_grid_rate if (cfg.enable_solar and cfg.enable_battery) else 0.0

    # Isolated component metrics
    solar_gross_val_y1 = (solar_direct_val + solar_stored_val + solar_export_rev_y1) if cfg.enable_solar else 0.0
    solar_net_val_y1 = (solar_gross_val_y1 - solar_om_annual) if cfg.enable_solar else 0.0
    solar_iso_payback = round(solar_capex / solar_net_val_y1, 1) if (cfg.enable_solar and solar_capex > 0.0 and solar_net_val_y1 > 1.0) else (0.0 if (cfg.enable_solar and solar_capex <= 0.0 and solar_net_val_y1 >= 0.0) else None)
    if cfg.enable_solar and float(getattr(kpis, "solar_total_generation_kwh", 0.0)) > 1.0:
        disc_sol_cost = solar_capex
        disc_sol_gen = 0.0
        for yr in range(1, 16):
            disc_sol_cost += (solar_om_annual * ((1.0 + r_om) ** (yr - 1))) / ((1.0 + r_disc) ** yr)
            disc_sol_gen += (float(kpis.solar_total_generation_kwh) * max(0.0, (1.0 - d_sys) ** (yr - 1))) / ((1.0 + r_disc) ** yr)
        solar_iso_lcoe = disc_sol_cost / max(1.0, disc_sol_gen)
    else:
        solar_iso_lcoe = 0.0

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

    # Isolated Contract Actor Savings & 15Y Benefit-Cost Ratio
    dso_savings_eur = base_p2_sum - comb_p2_sum
    dso_savings_pct = (dso_savings_eur / base_p2_sum * 100.0) if base_p2_sum > 1e-6 else 0.0
    supplier_savings_eur = base_p1_sum - comb_p1_sum
    supplier_savings_pct = (supplier_savings_eur / base_p1_sum * 100.0) if base_p1_sum > 1e-6 else 0.0
    tax_metering_savings_eur = (base_p3_sum + base_p4_sum) - (comb_p3_sum + comb_p4_sum)
    disc_gross_benefits_15y = sum(
        ((bill_avoided_y1 + solar_export_rev_y1) * max(0.0, (1.0 - d_sys) ** (yr - 1)) * ((1.0 + r_tariff) ** (yr - 1))) / ((1.0 + r_disc) ** yr)
        for yr in range(1, 16)
    )
    bcr_15y = (disc_gross_benefits_15y / max(1.0, disc_sys_cost_acc)) if disc_sys_cost_acc > 1.0 else 0.0

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
    )

    denom = max(1.0, kpis.annual_consumption_kwh)
    payback_str = f"{simple_payback_years:.1f} yrs" if simple_payback_years is not None else "N/A"

    fin_rows = [
        {
            "Component": "Grid",
            "Installed Size": f"{kpis.grid_limit_kw:,.0f} kW limit",
            "Energy Supplied (kWh/year & %)": f"{kpis.grid_supplied_to_load_kwh:,.0f} kWh ({(kpis.grid_supplied_to_load_kwh / denom * 100.0):.1f}%)",
            "Investment (CAPEX)": "€0",
            "Annual Operating Cost (OPEX)": f"€{fin_kpis.combined_grid_total_eur:,.0f}",
            "Annual Savings vs. Current situation": f"€{(fin_kpis.baseline_total_opex_eur - fin_kpis.combined_grid_total_eur):,.0f}",
            "Payback (Years)": "—",
        },
        {
            "Component": "Solar",
            "Installed Size": f"{solar_deriv.installed_kwp:,.1f} kWp" if cfg.enable_solar else "0.0 kWp",
            "Energy Supplied (kWh/year & %)": f"{kpis.solar_direct_kwh:,.0f} kWh direct ({kpis.solar_supply_share_pct:.1f}% total)" if cfg.enable_solar else "0 kWh (0.0%)",
            "Investment (CAPEX)": f"€{fin_kpis.solar_capex_eur:,.0f}",
            "Annual Operating Cost (OPEX)": f"€{fin_kpis.solar_om_eur:,.0f}",
            "Annual Savings vs. Current situation": f"€{fin_kpis.solar_net_value_y1_eur:+,.0f}" if cfg.enable_solar else "—",
            "Payback (Years)": f"{solar_iso_payback:.1f} yrs" if solar_iso_payback is not None else "—",
        },
        {
            "Component": "Battery",
            "Installed Size": f"{cfg.battery_capacity_kwh:,.0f} kWh / {cfg.battery_power_kw:,.0f} kW" if cfg.enable_battery else "0 kWh / 0 kW",
            "Energy Supplied (kWh/year & %)": f"{kpis.battery_total_discharged_kwh:,.0f} kWh ({kpis.battery_discharge_share_pct:.1f}%)" if cfg.enable_battery else "0 kWh (0.0%)",
            "Investment (CAPEX)": f"€{fin_kpis.battery_capex_eur:,.0f}",
            "Annual Operating Cost (OPEX)": f"€{fin_kpis.battery_om_eur:,.0f}",
            "Annual Savings vs. Current situation": f"€{fin_kpis.battery_net_value_y1_eur:+,.0f}" if cfg.enable_battery else "—",
            "Payback (Years)": f"{bat_iso_payback:.1f} yrs" if bat_iso_payback is not None else "—",
        },
        {
            "Component": "Generator",
            "Installed Size": f"{cfg.generator_rated_kw:,.0f} kW ({cfg.fuel_type})" if cfg.enable_generator else "0 kW",
            "Energy Supplied (kWh/year & %)": f"{kpis.generator_to_load_kwh:,.0f} kWh ({kpis.generator_supply_share_pct:.1f}%)" if cfg.enable_generator else "0 kWh (0.0%)",
            "Investment (CAPEX)": f"€{fin_kpis.generator_capex_eur:,.0f}",
            "Annual Operating Cost (OPEX)": f"€{fin_kpis.generator_total_opex_eur:,.0f}",
            "Annual Savings vs. Current situation": f"€{fin_kpis.generator_net_value_y1_eur:+,.0f}" if cfg.enable_generator else "—",
            "Payback (Years)": f"{gen_iso_payback:.1f} yrs" if gen_iso_payback is not None else "—",
        },
        {
            "Component": "Combined system",
            "Installed Size": (
                f"Grid {kpis.grid_limit_kw:,.0f} kW + "
                f"Solar {solar_deriv.installed_kwp if cfg.enable_solar else 0.0:,.1f} kWp + "
                f"Battery {cfg.battery_capacity_kwh if cfg.enable_battery else 0.0:,.0f} kWh + "
                f"Generator {cfg.generator_rated_kw if cfg.enable_generator else 0.0:,.0f} kW"
            ),
            "Energy Supplied (kWh/year & %)": f"{kpis.annual_consumption_kwh:,.0f} kWh (100.0%)",
            "Investment (CAPEX)": f"€{fin_kpis.total_capex_eur:,.0f}",
            "Annual Operating Cost (OPEX)": f"€{fin_kpis.total_annual_opex_eur:,.0f}",
            "Annual Savings vs. Current situation": f"€{fin_kpis.annual_savings_eur:,.0f}",
            "Payback (Years)": payback_str,
        },
        {
            "Component": "Current situation",
            "Installed Size": f"Grid Limit {kpis.grid_limit_kw:,.0f} kW (Grid only)",
            "Energy Supplied (kWh/year & %)": f"{kpis.annual_consumption_kwh:,.0f} kWh (100.0%)",
            "Investment (CAPEX)": "€0",
            "Annual Operating Cost (OPEX)": f"€{fin_kpis.baseline_total_opex_eur:,.0f}",
            "Annual Savings vs. Current situation": "Baseline (€0)",
            "Payback (Years)": "—",
        },
    ]

    sim_res.financial_config = fin_cfg
    sim_res.financial_kpis = fin_kpis
    sim_res.financial_table_df = pd.DataFrame(fin_rows)
    sim_res.monthly_cost_df = pd.DataFrame(monthly_cost_rows)
    sim_res.cashflow_15y_df = pd.DataFrame(cashflow_rows)
    sim_res.dso_monthly_df = pd.DataFrame(dso_monthly_rows)
    sim_res.supplier_monthly_df = pd.DataFrame(supplier_monthly_rows)
    sim_res.tax_monthly_df = pd.DataFrame(tax_monthly_rows)
    sim_res.solar_fin_monthly_df = pd.DataFrame(solar_fin_rows)
    sim_res.battery_fin_monthly_df = pd.DataFrame(battery_fin_rows)
    sim_res.generator_fin_monthly_df = pd.DataFrame(generator_fin_rows)
    return sim_res
