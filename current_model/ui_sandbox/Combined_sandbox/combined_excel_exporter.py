"""
========================================================================================
Combined System Excel Verification Exporter (ui_sandbox/Combined_sandbox/combined_excel_exporter.py)
========================================================================================

Generates a complete 4-sheet Excel workbook (.xlsx via openpyxl) for mathematical
verification and auditing:
  - Sheet 1 (`Summary & KPIs`): Model parameters, interaction rules, technical & financial KPIs,
    Component Summary Table, and 4-Criterion BESS Bottleneck Table
  - Sheet 2 (`15-Min Dispatch`): All 35,040 15-minute intervals of the year
  - Sheet 3 (`Monthly Balance`): 12-month mirror of energy, peak demand, and generator metrics
  - Sheet 4 (`Cost & Tariffs`): Monthly & annual comparison of 4-Pillar tariffs, OPEX, savings,
    and 15-Year Lifecycle Cashflow Table
========================================================================================
"""

import io
from typing import List, Any
import numpy as np
import pandas as pd
import openpyxl

from .combined_sandbox_engine import (
    RULE1_OPTIONS,
    RULE2_OPTIONS,
    RULE3_OPTIONS,
    CombinedSimulationResult,
    CombinedFinancialConfig,
    evaluate_combined_financials,
)


def _append_df_to_ws(ws: Any, df: pd.DataFrame) -> None:
    """Appends a DataFrame header and rows into an openpyxl worksheet rapidly."""
    if df is None or df.empty:
        return
    ws.append(list(df.columns))
    for row in df.itertuples(index=False, name=None):
        ws.append(list(row))


def build_combined_verification_excel_bytes(
    sim_res: CombinedSimulationResult,
) -> bytes:
    """
    Constructs the 4-sheet `.xlsx` verification workbook in memory using openpyxl's
    fast streaming `write_only=True` mode and returns raw bytes.
    Respects Lazy Financials: only calls `evaluate_combined_financials` if
    `sim_res.system_config.enable_financials` is True.
    """
    cfg = sim_res.system_config
    if cfg.enable_financials and (sim_res.financial_kpis is None or sim_res.financial_config is None):
        evaluate_combined_financials(sim_res, CombinedFinancialConfig())

    rules = sim_res.rules_config
    deriv = sim_res.solar_derivation
    kpis = sim_res.kpis
    fin_kpis = sim_res.financial_kpis if cfg.enable_financials else None

    # 1. Sheet 1 DataFrames: Parameters, Rules, KPIs & Component Summary
    summary_rows: List[dict] = [
        {"Category": "Baseline (Current situation)", "Parameter / Metric": "Annual Consumption (kWh)", "Value": kpis.annual_consumption_kwh},
        {"Category": "Baseline (Current situation)", "Parameter / Metric": "Original Peak Demand (kW)", "Value": kpis.original_peak_kw},
        {"Category": "Baseline (Current situation)", "Parameter / Metric": "Average Load (kW)", "Value": kpis.average_load_kw},
        {"Category": "Baseline (Current situation)", "Parameter / Metric": "Baseline Overload Hours (hrs)", "Value": kpis.baseline_overload_hours},
        {"Category": "Baseline (Current situation)", "Parameter / Metric": "Baseline Overload Energy (kWh)", "Value": kpis.baseline_overload_kwh},
        {"Category": "Grid Input", "Parameter / Metric": "Contracted Grid Limit (kW)", "Value": cfg.grid_limit_kw},
        {"Category": "Solar Input", "Parameter / Metric": "Enable Solar", "Value": str(cfg.enable_solar)},
        {"Category": "Solar Input", "Parameter / Metric": "GPS Latitude / Longitude", "Value": f"{cfg.latitude:.4f}, {cfg.longitude:.4f}"},
        {"Category": "Solar Input", "Parameter / Metric": "Weather Data Source", "Value": deriv.data_source_label},
        {"Category": "Solar Input", "Parameter / Metric": "Specific Yield (kWh/kWp/year)", "Value": deriv.specific_yield_kwh_per_kwp},
        {"Category": "Solar Input", "Parameter / Metric": "Installed Solar Size (kWp)", "Value": deriv.installed_kwp},
        {"Category": "Solar Input", "Parameter / Metric": "Inverter AC Limit (kW) & Efficiency (%)", "Value": f"{deriv.inverter_ac_kw:.1f} kW @ {deriv.inverter_efficiency_pct:.1f}%"},
        {"Category": "Solar Input", "Parameter / Metric": "Panel Count & Wattage", "Value": f"{deriv.panel_count} panels @ {deriv.panel_wp:.0f} Wp"},
        {"Category": "Solar Input", "Parameter / Metric": "Derivation Formula", "Value": deriv.formula_text},
        {"Category": "Battery Input", "Parameter / Metric": "Enable Battery", "Value": str(cfg.enable_battery)},
        {"Category": "Battery Input", "Parameter / Metric": "Battery Capacity (kWh)", "Value": cfg.battery_capacity_kwh},
        {"Category": "Battery Input", "Parameter / Metric": "Battery Power (kW)", "Value": cfg.battery_power_kw},
        {"Category": "Battery Input", "Parameter / Metric": "SoC Window (%)", "Value": f"{cfg.min_soc_pct:.0f}% - {cfg.max_soc_pct:.0f}%"},
        {"Category": "Battery Input", "Parameter / Metric": "Round-Trip Efficiency (%)", "Value": cfg.round_trip_efficiency_pct},
        {"Category": "Generator Input", "Parameter / Metric": "Enable Generator", "Value": str(cfg.enable_generator)},
        {"Category": "Generator Input", "Parameter / Metric": "Generator Rated Power (kW)", "Value": cfg.generator_rated_kw},
        {"Category": "Generator Input", "Parameter / Metric": "Minimum Load (%)", "Value": cfg.generator_min_load_pct},
        {"Category": "Generator Input", "Parameter / Metric": "Fuel Type & Unit", "Value": f"{cfg.fuel_type} ({kpis.generator_fuel_unit})"},
        {"Category": "Generator Input", "Parameter / Metric": "Minimum Runtime (minutes)", "Value": cfg.gen_min_runtime_minutes},
        {"Category": "Operating Rules", "Parameter / Metric": "Rule 1 – Peak Shaving Priority", "Value": RULE1_OPTIONS.get(rules.rule1_peak_priority, rules.rule1_peak_priority)},
        {"Category": "Operating Rules", "Parameter / Metric": "Rule 2 – Normal Load Coverage", "Value": RULE2_OPTIONS.get(rules.rule2_battery_strategy, rules.rule2_battery_strategy)},
        {"Category": "Operating Rules", "Parameter / Metric": "Peak Reserve SoC (%)", "Value": rules.peak_reserve_soc_pct},
        {"Category": "Operating Rules", "Parameter / Metric": "Rule 3 – Battery Charging Sources", "Value": RULE3_OPTIONS.get(rules.rule3_charging_sources, rules.rule3_charging_sources)},
        {"Category": "Technical KPIs", "Parameter / Metric": "New Grid Peak (kW)", "Value": kpis.new_grid_peak_kw},
        {"Category": "Technical KPIs", "Parameter / Metric": "Grid Limit Met", "Value": str(kpis.grid_limit_met)},
        {"Category": "Technical KPIs", "Parameter / Metric": "Remaining Overload Hours (hrs)", "Value": kpis.remaining_overload_hours},
        {"Category": "Technical KPIs", "Parameter / Metric": "Remaining Overload Energy (kWh)", "Value": kpis.remaining_overload_kwh},
        {"Category": "Technical KPIs", "Parameter / Metric": "Supply Split – Grid (%)", "Value": kpis.grid_supply_share_pct},
        {"Category": "Technical KPIs", "Parameter / Metric": "Supply Split – Solar Direct + Battery (%)", "Value": kpis.solar_supply_share_pct},
        {"Category": "Technical KPIs", "Parameter / Metric": "Supply Split – Generator (%)", "Value": kpis.generator_supply_share_pct},
        {"Category": "Technical KPIs", "Parameter / Metric": "Generator Runtime (hrs/year)", "Value": kpis.generator_runtime_hours},
        {"Category": "Technical KPIs", "Parameter / Metric": "Generator Fuel Consumed", "Value": f"{kpis.generator_fuel_total:.1f} {kpis.generator_fuel_unit}"},
    ]

    if fin_kpis is not None:
        summary_rows.extend([
            {"Category": "Financial KPIs", "Parameter / Metric": "Total Investment / CAPEX (€)", "Value": fin_kpis.total_capex_eur},
            {"Category": "Financial KPIs", "Parameter / Metric": "Current situation Annual Bill (€/year)", "Value": fin_kpis.baseline_total_opex_eur},
            {"Category": "Financial KPIs", "Parameter / Metric": "Combined System Annual OPEX (€/year)", "Value": fin_kpis.total_annual_opex_eur},
            {"Category": "Financial KPIs", "Parameter / Metric": "Annual Savings vs. Current situation (€/year)", "Value": fin_kpis.annual_savings_eur},
            {"Category": "Financial KPIs", "Parameter / Metric": "Payback Period (Years)", "Value": fin_kpis.payback_years if fin_kpis.payback_years is not None else "N/A"},
            {"Category": "Financial KPIs", "Parameter / Metric": "15-Year NPV (€)", "Value": fin_kpis.npv_15y_eur},
        ])

    df_sheet1_meta = pd.DataFrame(summary_rows)

    # 2. Sheet 2 DataFrame: 35,040-Step 15-Min Dispatch
    n = len(sim_res.load_kw)
    df_sheet2_dispatch = pd.DataFrame({
        "Timestamp": sim_res.timestamps.strftime("%Y-%m-%d %H:%M"),
        "Consumption_kW": np.round(sim_res.load_kw, 2),
        "Grid_Limit_kW": np.full(n, round(cfg.grid_limit_kw, 2)),
        "Solar_Generation_kW": np.round(sim_res.solar_gen_kw, 2),
        "Solar_Direct_to_Load_kW": np.round(sim_res.solar_direct_kw, 2),
        "Solar_Surplus_kW": np.round(sim_res.solar_surplus_kw, 2),
        "Solar_Export_to_Grid_kW": np.round(sim_res.solar_export_kw, 2),
        "Battery_Charge_from_Solar_kW": np.round(sim_res.bess_charge_solar_kw, 2),
        "Battery_Charge_from_Grid_kW": np.round(sim_res.bess_charge_grid_kw, 2),
        "Battery_Charge_from_Generator_kW": np.round(sim_res.bess_charge_gen_kw, 2),
        "Battery_Discharge_to_Load_kW": np.round(sim_res.bess_discharge_kw, 2),
        "Battery_SoC_pct": np.round(sim_res.bess_soc_pct, 2),
        "Battery_Stored_Energy_kWh": np.round(sim_res.bess_energy_kwh, 2),
        "Generator_Output_kW": np.round(sim_res.gen_output_kw, 2),
        "Generator_to_Load_kW": np.round(sim_res.gen_to_load_kw, 2),
        "Generator_to_Battery_kW": np.round(sim_res.gen_to_bess_kw, 2),
        f"Generator_Fuel_{kpis.generator_fuel_unit}": np.round(sim_res.gen_fuel_step, 3),
        "Net_Grid_Import_kW": np.round(sim_res.grid_import_kw, 2),
        "Remaining_Overload_kW": np.round(sim_res.unmet_overload_kw, 2),
    })

    # 3. Write all 4 sheets into an in-memory openpyxl write_only workbook for maximum speed
    wb = openpyxl.Workbook(write_only=True)

    # Sheet 1: Summary & KPIs
    ws1 = wb.create_sheet(title="Summary & KPIs")
    _append_df_to_ws(ws1, df_sheet1_meta)
    ws1.append([])
    _append_df_to_ws(ws1, sim_res.summary_table_df)
    if not sim_res.bess_bottleneck_df.empty:
        ws1.append([])
        _append_df_to_ws(ws1, sim_res.bess_bottleneck_df)

    # Sheet 2: 15-Min Dispatch (35,040 rows)
    ws2 = wb.create_sheet(title="15-Min Dispatch")
    _append_df_to_ws(ws2, df_sheet2_dispatch)

    # Sheet 3: Monthly Balance
    ws3 = wb.create_sheet(title="Monthly Balance")
    _append_df_to_ws(ws3, sim_res.monthly_balance_df)

    # Sheet 4: Cost & Tariffs
    ws4 = wb.create_sheet(title="Cost & Tariffs")
    if cfg.enable_financials and fin_kpis is not None:
        _append_df_to_ws(ws4, sim_res.monthly_cost_df)
        if not sim_res.financial_table_df.empty:
            ws4.append([])
            _append_df_to_ws(ws4, sim_res.financial_table_df)
        if not sim_res.cashflow_15y_df.empty:
            ws4.append([])
            _append_df_to_ws(ws4, sim_res.cashflow_15y_df)
    else:
        _append_df_to_ws(ws4, pd.DataFrame([{"Status": "Financials disabled"}]))

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
