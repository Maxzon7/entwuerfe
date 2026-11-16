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
