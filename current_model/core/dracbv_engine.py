"""
========================================================================================
DRACBV Generator Peaking & Multi-Path Simulation Engine (current_model/core/dracbv_engine.py)
========================================================================================

Description:
------------
Core computational engine for Generator Peaking Simulation & Multi-Path Evaluation:
  - 15-minute interval-by-interval generator dispatch for peak shaving.
  - Calculation of fuel consumption, operating hours, and generator OPEX.
  - Month-by-month financial invoice evaluation via Contract billing engine.
  - Detailed Cumulative Payment Schedule (Kumulierte Zahlungsreihe) comparing
    Status Quo (Grid Only) vs. With Generator (Mitigated Grid + Genset OPEX/Rental).
"""

from typing import Dict, Any, List, Optional, Tuple, Union
import numpy as np
import pandas as pd

from current_model.models.dracbv import DRACBVConfig, DRACBVSolutionSummary
from current_model.models.generator import GeneratorConfig, GeneratorKPIs
from current_model.models.contract import Contract
from current_model.models.bess import BESSConfig
from current_model.core.bess_engine import analyze_grid_violations, simulate_bess_dispatch
from current_model.core.financial_engine import compute_financial_bill


def simulate_generator_peaking(
    df_load: pd.DataFrame,
    power_col: str,
    contract: Contract,
    gen_config: GeneratorConfig,
    step_hours: float = 0.25
) -> Dict[str, Any]:
    """
    Executes a high-precision 15-minute simulation evaluating generator peak shaving.
    
    Dispatch Logic:
      - Whenever P_Load(t) > trigger_kw:
          generator starts and produces min(excess_kw, rated_power_kw).
          If minimum loading ratio is configured, generator runs at least min_power_kw.
      - Residual Grid Draw: P_Grid_New(t) = max(0, P_Load(t) - P_Gen(t)).
      - Fuel consumed per interval calculated via linear fuel curve:
          Rate (L/h) = a * P_Gen + b * P_Rated
    """
    load_series = df_load[power_col].to_numpy(dtype=float)
    load_series = np.nan_to_num(load_series, nan=0.0)
    n_steps = len(load_series)

    duration_days = (n_steps * step_hours) / 24.0
    annual_factor = (365.0 / duration_days) if (0.1 < duration_days < 360.0) else 1.0

    trigger_kw = float(gen_config.peak_shaving_trigger_kw)
    if trigger_kw <= 0:
        trigger_kw = float(contract.contracted_capacity_kw)

    rated_kw = float(gen_config.rated_power_kw)
    min_power_kw = float(gen_config.min_power_kw)

    # 1. Dispatch Arrays
    gen_power = np.zeros(n_steps, dtype=float)
    new_grid_power = np.copy(load_series)
    fuel_liters_interval = np.zeros(n_steps, dtype=float)
    is_running = np.zeros(n_steps, dtype=bool)

    # 2. 15-minute interval loop
    for i in range(n_steps):
        p_act = load_series[i]
        if p_act > trigger_kw:
            excess = p_act - trigger_kw
            p_gen = min(excess, rated_kw)
            if p_gen > 0 and min_power_kw > 0:
                p_gen = max(p_gen, min_power_kw)
            
            gen_power[i] = p_gen
            new_grid_power[i] = max(0.0, p_act - p_gen)
            is_running[i] = True
            fuel_liters_interval[i] = gen_config.calc_fuel_consumption(p_gen, duration_hours=step_hours)
        else:
            gen_power[i] = 0.0
            new_grid_power[i] = p_act
            is_running[i] = False
            fuel_liters_interval[i] = 0.0

    # 3. Overall Operational Metrics
    total_run_intervals = int(np.sum(is_running))
    operating_hours = float(total_run_intervals * step_hours)
    total_fuel_liters = float(np.sum(fuel_liters_interval))
    total_generation_kwh = float(np.sum(gen_power) * step_hours)

    fuel_cost_total = total_fuel_liters * float(gen_config.fuel_price_per_unit)
    maint_cost_total = operating_hours * float(gen_config.maintenance_cost_per_op_hour)
    total_op_cost = fuel_cost_total + maint_cost_total

    orig_peak = float(np.max(load_series)) if n_steps > 0 else 0.0
    new_peak = float(np.max(new_grid_power)) if n_steps > 0 else 0.0
    peak_shaved_kw = max(0.0, orig_peak - new_peak)

    # 4. Construct Timeseries DataFrame for Charting
    if "timestamp" in df_load.columns:
        ts_series = pd.to_datetime(df_load["timestamp"])
    else:
        ts_series = pd.date_range("2026-01-01", periods=n_steps, freq=f"{int(step_hours * 60)}min")

    df_timeseries = pd.DataFrame({
        "timestamp": ts_series,
        "Original_Load_kW": np.round(load_series, 2),
        "New_Grid_Load_kW": np.round(new_grid_power, 2),
        "Generator_Power_kW": np.round(gen_power, 2),
        "Fuel_Liters": np.round(fuel_liters_interval, 3)
    })

    # 5. Month-by-Month Financial Evaluation (Zahlungsreihe)
    df_orig_input = pd.DataFrame({"P_kW": load_series, "timestamp": ts_series})
    df_new_input = pd.DataFrame({"P_kW": new_grid_power, "timestamp": ts_series})

    base_bill = compute_financial_bill(df_orig_input, contract, duration_days=duration_days, step_hours=step_hours)
    mitigated_bill = compute_financial_bill(df_new_input, contract, duration_days=duration_days, step_hours=step_hours)

    df_timeseries["month_period"] = ts_series.dt.to_period("M").astype(str)
    monthly_gen_stats = df_timeseries.groupby("month_period").agg(
        gen_hours=("Generator_Power_kW", lambda s: float((s > 0).sum() * step_hours)),
        fuel_liters=("Fuel_Liters", "sum"),
        gen_kwh=("Generator_Power_kW", lambda s: float(s.sum() * step_hours)),
        orig_peak=("Original_Load_kW", "max"),
        new_peak=("New_Grid_Load_kW", "max")
    ).reset_index()

    # Align with monthly billing records
    monthly_records = []
    cum_status_quo = 0.0
    cum_with_generator = 0.0
    cum_savings = 0.0

    num_months = max(1, len(base_bill.monthly_series))
    monthly_rental = float(gen_config.monthly_lease_fee)
    # If purchase mode, prorate capital cost across 12 months for first year
    amortized_monthly_capex = (float(gen_config.capital_cost) / 12.0) if monthly_rental <= 0 and gen_config.capital_cost > 0 else 0.0

    for idx, b_rec in enumerate(base_bill.monthly_series):
        label = b_rec.period_label
        base_gross = float(b_rec.total_gross)

        # Matching mitigated bill
        new_gross = float(mitigated_bill.monthly_series[idx].total_gross) if idx < len(mitigated_bill.monthly_series) else base_gross

        # Matching generator operational stats
        if idx < len(monthly_gen_stats):
            m_stats = monthly_gen_stats.iloc[idx]
            m_hours = float(m_stats["gen_hours"])
            m_fuel = float(m_stats["fuel_liters"])
            m_orig_pk = float(m_stats["orig_peak"])
            m_new_pk = float(m_stats["new_peak"])
        else:
            m_hours = operating_hours / num_months
            m_fuel = total_fuel_liters / num_months
            m_orig_pk = orig_peak
            m_new_pk = new_peak

        m_fuel_cost = m_fuel * float(gen_config.fuel_price_per_unit)
        m_maint_cost = m_hours * float(gen_config.maintenance_cost_per_op_hour)
        m_fixed_cost = monthly_rental if monthly_rental > 0 else amortized_monthly_capex
        m_gen_total = m_fuel_cost + m_maint_cost + m_fixed_cost

        m_total_with_gen = new_gross + m_gen_total
        m_savings = base_gross - m_total_with_gen

        cum_status_quo += base_gross
        cum_with_generator += m_total_with_gen
        cum_savings += m_savings

        monthly_records.append({
            "Month": label,
            "Baseline_Peak_kW": round(m_orig_pk, 1),
            "New_Grid_Peak_kW": round(m_new_pk, 1),
            "Peak_Shaved_kW": round(max(0.0, m_orig_pk - m_new_pk), 1),
            "Gen_Hours": round(m_hours, 1),
            "Fuel_Liters": round(m_fuel, 1),
            "Status_Quo_Bill": round(base_gross, 2),
            "New_Grid_Bill": round(new_gross, 2),
            "Generator_Cost": round(m_gen_total, 2),
            "Fuel_Cost": round(m_fuel_cost, 2),
            "Maintenance_Cost": round(m_maint_cost, 2),
            "Equipment_Fee": round(m_fixed_cost, 2),
            "Total_With_Generator": round(m_total_with_gen, 2),
            "Monthly_Savings": round(m_savings, 2),
            "Cum_Status_Quo": round(cum_status_quo, 2),
            "Cum_With_Generator": round(cum_with_generator, 2),
            "Cum_Savings": round(cum_savings, 2)
        })

    df_zahlungsreihe = pd.DataFrame(monthly_records)

    kpis = GeneratorKPIs(
        total_generation_kwh=round(total_generation_kwh, 1),
        total_fuel_units=round(total_fuel_liters, 1),
        operating_hours=round(operating_hours, 1),
        fuel_cost_total=round(fuel_cost_total, 2),
        om_cost_total=round(maint_cost_total, 2),
        total_operating_cost=round(total_op_cost, 2),
        levelized_cost_per_kwh=round((total_op_cost / total_generation_kwh), 3) if total_generation_kwh > 0 else 0.0
    )

    return {
        "kpis": kpis,
        "orig_peak_kw": orig_peak,
        "new_peak_kw": new_peak,
        "peak_shaved_kw": peak_shaved_kw,
        "trigger_kw": trigger_kw,
        "df_timeseries": df_timeseries,
        "df_dispatch": df_timeseries,
        "df_zahlungsreihe": df_zahlungsreihe,
        "annual_status_quo_bill": cum_status_quo * annual_factor,
        "annual_with_generator": cum_with_generator * annual_factor,
        "annual_net_savings": cum_savings * annual_factor,
        "base_diagnostics": analyze_grid_violations(load_series, trigger_kw, step_hours=step_hours),
        "new_diagnostics": analyze_grid_violations(new_grid_power, trigger_kw, step_hours=step_hours)
    }


# ========================================================================================
# Legacy Multi-Path Helpers (Retained for Backwards Compatibility & Testing)
# ========================================================================================
def compute_lifecycle_financials(
    initial_capex: float,
    annual_opex_base: float,
    annual_grid_bill_base: float,
    duration_years: int,
    discount_rate_pct: float,
    inflation_rate_pct: float,
    energy_escalation_pct: float,
    repower_year: Optional[int] = None,
    repower_cost: float = 0.0
) -> Tuple[float, List[float], List[float]]:
    wacc = discount_rate_pct / 100.0
    infl = inflation_rate_pct / 100.0
    escl = energy_escalation_pct / 100.0

    yearly_cashflows: List[float] = [float(initial_capex)]
    cumulative_cashflows: List[float] = [float(initial_capex)]
    running_cum = float(initial_capex)
    total_discounted_tco = float(initial_capex)

    for y in range(1, duration_years + 1):
        opex_y = annual_opex_base * ((1.0 + infl) ** (y - 1))
        grid_y = annual_grid_bill_base * ((1.0 + escl) ** (y - 1))
        extra_capex = repower_cost * ((1.0 + infl) ** (y - 1)) if (repower_year and y == repower_year) else 0.0

        cash_y = opex_y + grid_y + extra_capex
        yearly_cashflows.append(round(cash_y, 2))
        running_cum += cash_y
        cumulative_cashflows.append(round(running_cum, 2))

        discount_factor = (1.0 + wacc) ** y
        total_discounted_tco += (cash_y / discount_factor)

    return round(total_discounted_tco, 2), yearly_cashflows, cumulative_cashflows


def compute_npv_and_payback(
    baseline_cum_cashflows: List[float],
    alt_cum_cashflows: List[float],
    baseline_yearly: List[float],
    alt_yearly: List[float],
    discount_rate_pct: float
) -> Tuple[float, Optional[float]]:
    wacc = discount_rate_pct / 100.0
    npv = 0.0
    duration = min(len(baseline_yearly), len(alt_yearly))
    capex_diff = alt_yearly[0] - baseline_yearly[0]
    npv -= capex_diff

    for y in range(1, duration):
        annual_saving = baseline_yearly[y] - alt_yearly[y]
        discount_factor = (1.0 + wacc) ** y
        npv += (annual_saving / discount_factor)

    payback_years: Optional[float] = None
    if capex_diff > 0:
        for y in range(1, duration):
            if alt_cum_cashflows[y] <= baseline_cum_cashflows[y]:
                prev_diff = alt_cum_cashflows[y - 1] - baseline_cum_cashflows[y - 1]
                curr_diff = alt_cum_cashflows[y] - baseline_cum_cashflows[y]
                if (prev_diff - curr_diff) > 0:
                    fraction = prev_diff / (prev_diff - curr_diff)
                    payback_years = round((y - 1) + max(0.0, min(1.0, fraction)), 1)
                else:
                    payback_years = float(y)
                break

    return round(npv, 2), payback_years


def simulate_dracbv_multi_path(
    df_load: pd.DataFrame,
    power_col: str,
    contract: Contract,
    config: DRACBVConfig,
    step_hours: float = 0.25
) -> Dict[str, Any]:
    # Call simulate_generator_peaking internally and build multi-path records
    gen_cfg = GeneratorConfig(
        rated_power_kw=config.generator_power_kw,
        peak_shaving_trigger_kw=config.bess_target_cap_kw,
        fuel_price_per_unit=config.generator_fuel_price_per_unit,
        maintenance_cost_per_op_hour=config.generator_maintenance_per_op_hour,
        monthly_lease_fee=config.generator_monthly_rental if config.generator_mode == "rental" else 0.0,
        capital_cost=config.generator_purchase_capex if config.generator_mode == "purchase" else 0.0,
        fuel_type=config.generator_fuel_type
    )
    gen_result = simulate_generator_peaking(df_load, power_col, contract, gen_cfg, step_hours=step_hours)

    load_series = df_load[power_col].to_numpy(dtype=float)
    total_steps = len(load_series)
    duration_days = (total_steps * step_hours) / 24.0
    annual_factor = (365.0 / duration_days) if (0.1 < duration_days < 360.0) else 1.0

    base_diag = gen_result["base_diagnostics"]
    base_tco = gen_result["annual_status_quo_bill"] * config.project_duration_years

    solutions = [
        DRACBVSolutionSummary(
            path_id="baseline_status_quo",
            name="Status Quo (Grid Only)",
            technology_label=f"Grid ({contract.contracted_capacity_kw:.0f} kW)",
            description="Baseline facility draw without peak shaving.",
            color_code="#94A3B8",
            is_technically_feasible=(base_diag["total_violation_intervals"] == 0),
            peak_grid_draw_kw=gen_result["orig_peak_kw"],
            violations_count=base_diag["total_violation_intervals"],
            annual_grid_bill_year1=gen_result["annual_status_quo_bill"],
            lifetime_tco=base_tco,
            cashflows=[0.0] + [gen_result["annual_status_quo_bill"]] * config.project_duration_years,
            cumulative_cashflows=[0.0] + [gen_result["annual_status_quo_bill"] * y for y in range(1, config.project_duration_years + 1)]
        ),
        DRACBVSolutionSummary(
            path_id="path_generator_bridging",
            name=f"Generator Peaking ({gen_cfg.rated_power_kw:.0f} kW)",
            technology_label="Generator Peaker",
            description=f"Runs generator to carry peaks above {gen_result['trigger_kw']:.0f} kW.",
            color_code="#F59E0B",
            is_technically_feasible=(gen_result["new_diagnostics"]["total_violation_intervals"] == 0),
            peak_grid_draw_kw=gen_result["new_peak_kw"],
            peak_reduction_kw=gen_result["peak_shaved_kw"],
            generator_runtime_hours=gen_result["kpis"].operating_hours,
            generator_fuel_liters=gen_result["kpis"].total_fuel_units,
            annual_opex_year1=gen_result["kpis"].total_operating_cost,
            annual_grid_bill_year1=gen_result["annual_with_generator"],
            lifetime_tco=gen_result["annual_with_generator"] * config.project_duration_years,
            npv_vs_baseline=gen_result["annual_net_savings"] * config.project_duration_years,
            cashflows=[0.0] + [gen_result["annual_with_generator"]] * config.project_duration_years,
            cumulative_cashflows=[0.0] + [gen_result["annual_with_generator"] * y for y in range(1, config.project_duration_years + 1)]
        )
    ]

    # Additional standard upgrade and BESS paths for backwards compatibility
    if config.upgrade_enabled:
        target_cap = config.upgrade_target_capacity_kw
        upg_diag = analyze_grid_violations(load_series, target_cap, step_hours)
        solutions.append(DRACBVSolutionSummary(
            path_id="path_grid_upgrade",
            name=f"Grid Upgrade ({target_cap:.0f} kW)",
            technology_label="Traditional Network Upgrade",
            description="Traditional network reinforcement.",
            color_code="#2563EB",
            is_technically_feasible=(upg_diag["total_violation_intervals"] == 0),
            peak_grid_draw_kw=gen_result["orig_peak_kw"],
            initial_capex=config.upgrade_capex,
            annual_grid_bill_year1=gen_result["annual_status_quo_bill"],
            lifetime_tco=config.upgrade_capex + gen_result["annual_status_quo_bill"] * config.project_duration_years
        ))

    if config.bess_enabled:
        df_load_for_bess = pd.DataFrame({"P_Load_kW": load_series})
        if "timestamp" in df_load.columns:
            df_load_for_bess["timestamp"] = df_load["timestamp"].values
        bess_cfg = BESSConfig(
            capacity_kwh=config.bess_capacity_kwh,
            max_charge_power_kw=config.bess_power_kw,
            max_discharge_power_kw=config.bess_power_kw,
            peak_shaving_threshold_kw=config.bess_target_cap_kw
        )
        bess_res = simulate_bess_dispatch(bess_cfg, df_load_for_bess, config.bess_target_cap_kw, step_hours=step_hours, power_col="P_Load_kW")
        bess_tco = (config.bess_capacity_kwh * config.bess_capex_per_kwh) + gen_result["annual_status_quo_bill"] * config.project_duration_years
        solutions.append(DRACBVSolutionSummary(
            path_id="path_ac4_bess",
            name="BESS Peak Shaving",
            technology_label="Battery Storage",
            description="BESS peak shaving.",
            color_code="#10B981",
            is_technically_feasible=(bess_res.diagnostics_after["total_violation_intervals"] == 0),
            peak_grid_draw_kw=float(bess_res.diagnostics_after["peak_load_kw"]),
            peak_reduction_kw=float(bess_res.kpis.peak_shaved_kw),
            initial_capex=(config.bess_capacity_kwh * config.bess_capex_per_kwh),
            lifetime_tco=bess_tco
        ))

    if config.solar_enabled:
        solutions.append(DRACBVSolutionSummary(
            path_id="path_pv_bess_hybrid",
            name="Solar + BESS Hybrid",
            technology_label="Solar PV + BESS",
            description="Solar PV coupled with battery storage.",
            color_code="#8B5CF6",
            is_technically_feasible=True,
            initial_capex=50000.0,
            annual_grid_bill_year1=gen_result["annual_status_quo_bill"] * 0.6,
            lifetime_tco=50000.0 + gen_result["annual_status_quo_bill"] * 0.6 * config.project_duration_years
        ))

    leaderboard_data = [{
        "Path": s.name,
        "Technology": s.technology_label,
        "Feasible": "Yes" if s.is_technically_feasible else "No",
        "Initial CAPEX": s.initial_capex,
        "Annual Cost": s.annual_grid_bill_year1,
        "Lifetime TCO": s.lifetime_tco
    } for s in solutions]

    return {
        "solutions": solutions,
        "df_dispatch": gen_result["df_timeseries"],
        "df_zahlungsreihe": gen_result["df_zahlungsreihe"],
        "leaderboard": pd.DataFrame(leaderboard_data),
        "baseline_diagnostics": base_diag,
        "generator_result": gen_result
    }
