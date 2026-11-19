"""
15-Year lifecycle cashflow schedule, IRR/NPV/TCO, payback crossings, LCOE, and Benefit-Cost Ratio.
"""

from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd


def extract_tou_and_dispatch_monthly_arrays(sim_res: Any, cfg: Any, kpis: Any) -> Dict[str, np.ndarray]:
    """Aggregates 15-minute 2-window (HT/NT), 3-window (Pico/Valle/Resto), and component dispatch arrays per month."""
    n_steps = len(sim_res.load_kw)
    dt = 0.25
    out: Dict[str, np.ndarray] = {
        k: np.zeros(12, dtype=float)
        for k in (
            "cons_ht_m", "cons_nt_m", "imp_ht_m", "imp_nt_m",
            "cons_pico_m", "cons_valle_m", "cons_resto_m",
            "imp_pico_m", "imp_valle_m", "imp_resto_m",
            "base_pico_pk_m", "comb_pico_pk_m",
            "pv_chg_bess_m", "bess_chg_grid_m", "bess_chg_gen_m", "gen_to_load_m",
            "bess_shave_kw_m", "gen_shave_kw_m",
        )
    }
    ts = sim_res.timestamps
    if n_steps > 0 and isinstance(ts, pd.DatetimeIndex) and len(ts) == n_steps:
        m_arr = ts.month.to_numpy(dtype=np.intp) - 1
        hr_arr = ts.hour.to_numpy(dtype=np.intp)
        is_peak_tou = (ts.dayofweek < 5) & (ts.hour >= 7) & (ts.hour < 23)
        is_pico_tou = (hr_arr >= 18) & (hr_arr < 23)
        is_valle_tou = (hr_arr >= 23) | (hr_arr < 5)
        is_resto_tou = (hr_arr >= 5) & (hr_arr < 18)

        p_load = np.maximum(0.0, np.asarray(sim_res.load_kw, dtype=float))
        p_imp = np.maximum(0.0, np.asarray(sim_res.grid_import_kw, dtype=float))
        p_dis = np.maximum(0.0, np.asarray(sim_res.bess_discharge_kw, dtype=float))
        p_csol = np.maximum(0.0, np.asarray(sim_res.bess_charge_solar_kw, dtype=float))
        p_cgrd = np.maximum(0.0, np.asarray(sim_res.bess_charge_grid_kw, dtype=float))
        p_cgen = np.maximum(0.0, np.asarray(sim_res.bess_charge_gen_kw, dtype=float))
        p_gen = np.maximum(0.0, np.asarray(sim_res.gen_to_load_kw, dtype=float))

        out["cons_ht_m"] = np.bincount(m_arr, weights=p_load * is_peak_tou, minlength=12) * dt
        out["cons_nt_m"] = np.bincount(m_arr, weights=p_load * (~is_peak_tou), minlength=12) * dt
        out["imp_ht_m"] = np.bincount(m_arr, weights=p_imp * is_peak_tou, minlength=12) * dt
        out["imp_nt_m"] = np.bincount(m_arr, weights=p_imp * (~is_peak_tou), minlength=12) * dt
        out["cons_pico_m"] = np.bincount(m_arr, weights=p_load * is_pico_tou, minlength=12) * dt
        out["cons_valle_m"] = np.bincount(m_arr, weights=p_load * is_valle_tou, minlength=12) * dt
        out["cons_resto_m"] = np.bincount(m_arr, weights=p_load * is_resto_tou, minlength=12) * dt
        out["imp_pico_m"] = np.bincount(m_arr, weights=p_imp * is_pico_tou, minlength=12) * dt
        out["imp_valle_m"] = np.bincount(m_arr, weights=p_imp * is_valle_tou, minlength=12) * dt
        out["imp_resto_m"] = np.bincount(m_arr, weights=p_imp * is_resto_tou, minlength=12) * dt
        out["pv_chg_bess_m"] = np.bincount(m_arr, weights=p_csol, minlength=12) * dt
        out["bess_chg_grid_m"] = np.bincount(m_arr, weights=p_cgrd, minlength=12) * dt
        out["bess_chg_gen_m"] = np.bincount(m_arr, weights=p_cgen, minlength=12) * dt
        out["gen_to_load_m"] = np.bincount(m_arr, weights=p_gen, minlength=12) * dt

        over_mask = p_load > cfg.grid_limit_kw
        for m_i in range(12):
            m_pico = (m_arr == m_i) & is_pico_tou
            if np.any(m_pico):
                out["base_pico_pk_m"][m_i] = float(np.max(p_load[m_pico]))
                out["comb_pico_pk_m"][m_i] = float(np.max(p_imp[m_pico]))
            m_over = (m_arr == m_i) & over_mask
            if np.any(m_over):
                if cfg.enable_battery:
                    out["bess_shave_kw_m"][m_i] = float(np.max(p_dis[m_over]))
                if cfg.enable_generator:
                    out["gen_shave_kw_m"][m_i] = float(np.max(p_gen[m_over]))

    if cfg.enable_solar and cfg.enable_battery and np.sum(out["pv_chg_bess_m"]) > 1e-6:
        out["sol_via_bess_m"] = out["pv_chg_bess_m"] * (
            float(getattr(kpis, "solar_via_battery_kwh", 0.0)) / float(np.sum(out["pv_chg_bess_m"]))
        )
    else:
        out["sol_via_bess_m"] = np.zeros(12, dtype=float)
    return out


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


def compute_hardware_capex_and_opex(cfg: Any, solar_deriv: Any, fin_cfg: Any) -> Dict[str, Any]:
    """
    Computes Solar, Battery (incl. Repowering), and Generator CAPEX, annual fixed/O&M baselines,
    pricing mode flags (Unit Rates vs. >0 Lump-Sum Override), and implied unit benchmarks.
    """
    # Solar CAPEX & O&M
    sol_lump_cap = max(0.0, float(getattr(fin_cfg, "solar_lump_sum_capex_eur", 0.0) or 0.0))
    sol_lump_om = max(0.0, float(getattr(fin_cfg, "solar_lump_sum_om_eur_year", 0.0) or 0.0))
    if not cfg.enable_solar:
        solar_capex = solar_modules_capex = solar_inverter_capex = solar_mounting_capex = 0.0
        solar_pricing_mode = "Inactive"
        solar_implied_kwp = 0.0
        solar_om_annual = 0.0
        solar_opex_mode = "Inactive"
    else:
        kwp = float(solar_deriv.installed_kwp)
        if sol_lump_cap > 0.0:
            solar_capex = sol_lump_cap
            solar_modules_capex = solar_capex
            solar_inverter_capex = 0.0
            solar_mounting_capex = 0.0
            solar_pricing_mode = "Lump-Sum Override"
        elif fin_cfg.solar_capex_eur_kwp is not None:
            solar_capex = kwp * float(fin_cfg.solar_capex_eur_kwp)
            solar_modules_capex = solar_capex
            solar_inverter_capex = 0.0
            solar_mounting_capex = 0.0
            solar_pricing_mode = "Lump-Sum Override"
        elif bool(getattr(fin_cfg, "solar_use_detailed_breakdown", False)):
            solar_modules_capex = kwp * 1000.0 * float(fin_cfg.solar_modules_eur_wp)
            solar_inverter_capex = kwp * 1000.0 * float(fin_cfg.solar_inverter_eur_w)
            solar_mounting_capex = kwp * 1000.0 * float(fin_cfg.solar_mounting_eur_wp)
            solar_capex = solar_modules_capex + solar_inverter_capex + solar_mounting_capex
            solar_pricing_mode = "Detailed Breakdown"
        else:
            turnkey_rate = float(getattr(fin_cfg, "solar_turnkey_eur_kwp", 850.0))
            solar_capex = kwp * turnkey_rate
            w_mod = max(0.0, float(fin_cfg.solar_modules_eur_wp))
            w_inv = max(0.0, float(fin_cfg.solar_inverter_eur_w))
            w_mnt = max(0.0, float(fin_cfg.solar_mounting_eur_wp))
            w_sum = w_mod + w_inv + w_mnt
            if w_sum > 1e-6:
                solar_modules_capex = solar_capex * (w_mod / w_sum)
                solar_inverter_capex = solar_capex * (w_inv / w_sum)
                solar_mounting_capex = solar_capex - solar_modules_capex - solar_inverter_capex
            else:
                solar_modules_capex = solar_capex
                solar_inverter_capex = 0.0
                solar_mounting_capex = 0.0
            solar_pricing_mode = "Turnkey Unit Rate"

        solar_implied_kwp = (solar_capex / kwp) if kwp > 0.01 else 0.0
        if sol_lump_om > 0.0:
            solar_om_annual = sol_lump_om
            solar_opex_mode = "Lump-Sum Override"
        else:
            solar_om_annual = solar_capex * (fin_cfg.solar_om_pct_of_capex / 100.0)
            solar_opex_mode = "% of CAPEX"

    # Battery CAPEX, Repowering & O&M
    bat_lump_cap = max(0.0, float(getattr(fin_cfg, "battery_lump_sum_capex_eur", 0.0) or 0.0))
    bat_lump_om = max(0.0, float(getattr(fin_cfg, "battery_lump_sum_om_eur_year", 0.0) or 0.0))
    bat_lump_aug = max(0.0, float(getattr(fin_cfg, "battery_augmentation_lump_sum_eur", 0.0) or 0.0))
    if not cfg.enable_battery:
        battery_rack_capex = battery_inv_capex = battery_bop_capex = battery_capex = 0.0
        battery_pricing_mode = "Inactive"
        battery_implied_kwh = battery_implied_kw = 0.0
        battery_aug_eur = 0.0
        battery_repowering_mode = "Inactive"
        battery_om_annual = 0.0
        battery_opex_mode = "Inactive"
    else:
        if bat_lump_cap > 0.0:
            battery_capex = bat_lump_cap
            battery_rack_capex = battery_capex
            battery_inv_capex = 0.0
            battery_bop_capex = 0.0
            battery_pricing_mode = "Lump-Sum Override"
        else:
            battery_rack_capex = cfg.battery_capacity_kwh * fin_cfg.battery_capex_eur_kwh
            battery_inv_capex = cfg.battery_power_kw * fin_cfg.battery_capex_eur_kw
            battery_bop_capex = fin_cfg.battery_fixed_bop_eur if cfg.battery_capacity_kwh > 0 else 0.0
            battery_capex = battery_rack_capex + battery_inv_capex + battery_bop_capex
            battery_pricing_mode = "Unit Rates"

        battery_implied_kwh = (battery_capex / cfg.battery_capacity_kwh) if cfg.battery_capacity_kwh > 0.0 else 0.0
        battery_implied_kw = (battery_capex / cfg.battery_power_kw) if cfg.battery_power_kw > 0.0 else 0.0

        if fin_cfg.enable_battery_augmentation:
            if bat_lump_aug > 0.0:
                battery_aug_eur = bat_lump_aug
                battery_repowering_mode = "Lump-Sum Override"
            elif bat_lump_cap > 0.0:
                battery_aug_eur = battery_capex * (fin_cfg.battery_augmentation_pct_of_racks / 100.0)
                battery_repowering_mode = "% of Lump-Sum CAPEX"
            else:
                battery_aug_eur = battery_rack_capex * (fin_cfg.battery_augmentation_pct_of_racks / 100.0)
                battery_repowering_mode = "% of Racks"
        else:
            battery_aug_eur = 0.0
            battery_repowering_mode = "Disabled"

        if bat_lump_om > 0.0:
            battery_om_annual = bat_lump_om
            battery_opex_mode = "Lump-Sum Override"
        else:
            battery_om_annual = battery_capex * (fin_cfg.battery_om_pct_of_capex / 100.0)
            battery_opex_mode = "% of CAPEX"

    # Generator CAPEX & Service Override
    gen_is_purchase = fin_cfg.generator_cost_model == "Purchase (CAPEX)"
    gen_lump_cap = max(0.0, float(getattr(fin_cfg, "generator_lump_sum_capex_eur", 0.0) or 0.0))
    gen_lump_svc = max(0.0, float(getattr(fin_cfg, "generator_lump_sum_service_opex_eur_year", 0.0) or 0.0))
    if not cfg.enable_generator:
        generator_capex = 0.0
        generator_pricing_mode = "Inactive"
        generator_opex_mode = "Inactive"
        generator_implied_kw = 0.0
    else:
        if gen_is_purchase:
            if gen_lump_cap > 0.0:
                generator_capex = gen_lump_cap
                generator_pricing_mode = "Lump-Sum Override"
            else:
                generator_capex = float(fin_cfg.generator_capex_eur)
                generator_pricing_mode = "Purchase (CAPEX)"
        else:
            generator_capex = 0.0
            generator_pricing_mode = "Monthly Rental (OPEX)"
        generator_implied_kw = (generator_capex / cfg.generator_rated_kw) if (generator_capex > 0.0 and cfg.generator_rated_kw > 0.0) else 0.0
        generator_opex_mode = "Lump-Sum Service Override + Fuel" if gen_lump_svc > 0.0 else "Runtime & Fuel"

    return {
        "solar_capex": solar_capex,
        "solar_modules_capex": solar_modules_capex,
        "solar_inverter_capex": solar_inverter_capex,
        "solar_mounting_capex": solar_mounting_capex,
        "solar_om_annual": solar_om_annual,
        "solar_pricing_mode": solar_pricing_mode,
        "solar_opex_mode": solar_opex_mode,
        "solar_implied_kwp": solar_implied_kwp,
        "battery_capex": battery_capex,
        "battery_rack_capex": battery_rack_capex,
        "battery_inv_capex": battery_inv_capex,
        "battery_bop_capex": battery_bop_capex,
        "battery_aug_eur": battery_aug_eur,
        "battery_om_annual": battery_om_annual,
        "battery_pricing_mode": battery_pricing_mode,
        "battery_opex_mode": battery_opex_mode,
        "battery_repowering_mode": battery_repowering_mode,
        "battery_implied_kwh": battery_implied_kwh,
        "battery_implied_kw": battery_implied_kw,
        "gen_is_purchase": gen_is_purchase,
        "generator_capex": generator_capex,
        "generator_pricing_mode": generator_pricing_mode,
        "generator_opex_mode": generator_opex_mode,
        "generator_implied_kw": generator_implied_kw,
        "gen_lump_svc_annual": gen_lump_svc,
    }


def compute_15y_lifecycle_projection(
    total_capex: float,
    battery_aug_eur: float,
    aug_yr: int,
    baseline_total_opex: float,
    combined_grid_total: float,
    system_om_and_fuel_y1: float,
    solar_export_rev_y1: float,
    annual_savings: float,
    sys_energy_y1: float,
    solar_capex: float,
    solar_om_annual: float,
    solar_total_generation_kwh: float,
    enable_solar: bool,
    discount_rate_pct: float,
    tariff_escalation_pct_pa: float,
    om_inflation_pct_pa: float,
    system_degradation_pct_pa: float,
    bill_volume_avoided_y1: Optional[float] = None,
    bill_peak_avoided_y1: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Evaluates the 15-year escalated/degraded cashflow schedule, cumulative TCO curves,
    simple & discounted payback periods, IRR, NPV, system LCOE, solar LCOE, and BCR.
    """
    r_disc = max(0.0, float(discount_rate_pct)) / 100.0
    r_tariff = max(0.0, float(tariff_escalation_pct_pa)) / 100.0
    r_om = max(0.0, float(om_inflation_pct_pa)) / 100.0
    d_sys = max(0.0, float(system_degradation_pct_pa)) / 100.0

    bill_avoided_y1 = max(0.0, baseline_total_opex - combined_grid_total)
    cashflow_rows: List[dict] = []
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

    use_split_deg = (
        bill_volume_avoided_y1 is not None
        and bill_peak_avoided_y1 is not None
        and bill_avoided_y1 > 0.0
    )
    vol_sav_y1 = float(bill_volume_avoided_y1) if use_split_deg else bill_avoided_y1
    pk_sav_y1 = float(bill_peak_avoided_y1) if use_split_deg else 0.0

    for yr in range(1, 16):
        esc_tariff = (1.0 + r_tariff) ** (yr - 1)
        esc_om = (1.0 + r_om) ** (yr - 1)
        deg_factor = max(0.0, (1.0 - d_sys) ** (yr - 1))

        b_bill_yr = baseline_total_opex * esc_tariff
        if use_split_deg:
            # Volumetric PV & shifted-energy savings degrade with system_degradation_pct_pa;
            # Peak-shaving & penalty savings remain stable as capacity keeps peaks below limit.
            avoided_bill_yr = max(0.0, (vol_sav_y1 * deg_factor + pk_sav_y1) * esc_tariff)
        else:
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
    sys_lcoe = (disc_sys_cost_acc / disc_sys_energy_acc) if disc_sys_energy_acc > 1.0 else 0.0

    if enable_solar and solar_total_generation_kwh > 1.0:
        disc_sol_cost = solar_capex
        disc_sol_gen = 0.0
        for yr in range(1, 16):
            disc_sol_cost += (solar_om_annual * ((1.0 + r_om) ** (yr - 1))) / ((1.0 + r_disc) ** yr)
            disc_sol_gen += (solar_total_generation_kwh * max(0.0, (1.0 - d_sys) ** (yr - 1))) / ((1.0 + r_disc) ** yr)
        solar_iso_lcoe = disc_sol_cost / max(1.0, disc_sol_gen)
    else:
        solar_iso_lcoe = 0.0

    if use_split_deg:
        disc_gross_benefits_15y = sum(
            (max(0.0, (vol_sav_y1 + solar_export_rev_y1) * max(0.0, (1.0 - d_sys) ** (yr - 1)) + pk_sav_y1) * ((1.0 + r_tariff) ** (yr - 1))) / ((1.0 + r_disc) ** yr)
            for yr in range(1, 16)
        )
    else:
        disc_gross_benefits_15y = sum(
            ((bill_avoided_y1 + solar_export_rev_y1) * max(0.0, (1.0 - d_sys) ** (yr - 1)) * ((1.0 + r_tariff) ** (yr - 1))) / ((1.0 + r_disc) ** yr)
            for yr in range(1, 16)
        )
    bcr_15y = (disc_gross_benefits_15y / max(1.0, disc_sys_cost_acc)) if disc_sys_cost_acc > 1.0 else 0.0

    return {
        "cashflow_rows": cashflow_rows,
        "simple_payback_years": simple_payback_years,
        "discounted_payback_years": discounted_payback_years,
        "npv_acc": npv_acc,
        "irr_val": irr_val,
        "tco_base_acc": tco_base_acc,
        "tco_comb_acc": tco_comb_acc,
        "sys_lcoe": sys_lcoe,
        "solar_iso_lcoe": solar_iso_lcoe,
        "bcr_15y": bcr_15y,
    }


def append_isolated_hardware_monthly_rows(
    m_name: str,
    cfg: Any,
    kpis: Any,
    var_grid_rate: float,
    feed_in_rate: float,
    sol_om_monthly: float,
    bat_om_monthly: float,
    sol_gen_m_kwh: float,
    sol_dir_m_kwh: float,
    sol_bat_m_kwh: float,
    sol_exp_m_kwh: float,
    b_dis_m_kwh: float,
    pv_chg_b_kwh: float,
    grd_chg_b_kwh: float,
    b_shv_kw: float,
    m_bat_peak_sav: float,
    m_bat_grid_chg_cost: float,
    gen_hrs: float,
    g_out_m_kwh: float,
    gen_fuel: float,
    g_shv_kw: float,
    m_gen_peak_sav: float,
    c_fuel: float,
    c_maint: float,
    c_rent: float,
    solar_fin_rows: List[dict],
    battery_fin_rows: List[dict],
    generator_fin_rows: List[dict],
) -> None:
    """Appends one month's isolated Solar, Battery, and Generator financial rows for chart/table verification."""
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

    m_bat_om = bat_om_monthly if cfg.enable_battery else 0.0
    m_bat_net = m_bat_peak_sav + m_sol_shift_val - m_bat_grid_chg_cost - m_bat_om
    battery_fin_rows.append({
        "Month": m_name,
        "Discharged (kWh)": round(b_dis_m_kwh, 0),
        "Solar Charged (kWh)": round(pv_chg_b_kwh if cfg.enable_battery else 0.0, 0),
        "Grid Charged (kWh)": round(grd_chg_b_kwh if cfg.enable_battery else 0.0, 0),
        "Peak Shaved (kW)": round(b_shv_kw, 1),
        "DSO Peak & Penalty Savings (€)": round(m_bat_peak_sav, 0),
        "Solar Shift Value (€)": round(m_sol_shift_val, 0),
        "Grid Charging Cost (€)": round(m_bat_grid_chg_cost, 0),
        "Battery O&M (€)": round(m_bat_om, 0),
        "Net Battery Benefit (€)": round(m_bat_net, 0),
    })

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
