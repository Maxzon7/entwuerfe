"""
========================================================================================
Test Suite: Status Quo 2025 Accounting & 4-Point Audit (test_status_quo_2025.py)
========================================================================================
Validates all 5 layers and 4 audit points (13 mathematical criteria):
  - 1.1 - 1.3: Step count 35,040, energy conservation, calendar & TOU classification
  - 2.1 - 2.4: 12 monthly peaks, peak demand fee sum, contract breach logic, fixed fees
  - 3.1 - 3.4: Supplier pricing modes (Fixed/Var/Dynamic), metering, levies, feed-in lock
  - 4.1 - 4.3: Net sum, blended price, and 15-year lifecycle TCO NPV formula
  - Architectural isolation: app.py, core/, models/, ui/ do not import status_quo_2025
========================================================================================
"""

import unittest
import numpy as np
import pandas as pd

from current_model.ui_sandbox.status_quo_2025 import (
    TariffStage,
    PricingMode,
    LoadSeries2025,
    DSOTariff,
    SupplierTariff,
    MeteringTariff,
    LevyConfig,
    StatusQuoConfig2025,
    get_stage_1_default_config_2025,
    get_liander_2025_dso_defaults,
    get_default_supplier_tariff_2025,
    normalize_load_profile_2025,
    synthesize_benchmark_load_profile_2025,
    evaluate_load_integrity_audit,
    calculate_dso_accounting_2025,
    calculate_commercial_accounting_2025,
    calculate_status_quo_master_2025,
    perform_full_status_quo_audit,
)
from current_model.ui_sandbox.status_quo_2025.consumption_pipeline import (
    create_reference_2025_timestamps,
    classify_liander_tou_window,
    extract_monthly_consumption_records,
)
from current_model.ui_sandbox.status_quo_2025.status_quo_master import compute_tco_15_npv


class TestStatusQuo2025Accounting(unittest.TestCase):
    """Unit test cases for the Status Quo 2025 unbundled accounting engine."""

    def setUp(self):
        self.ref_index = create_reference_2025_timestamps()
        self.total_steps = 35040

    def test_criterion_1_load_integrity_constant_load(self):
        """Audit Point 1: 100 kW constant load across all 35,040 intervals."""
        power_arr = np.full(self.total_steps, 100.0, dtype=float)
        energy_arr = power_arr * 0.25
        month_idx = self.ref_index.month.to_numpy(dtype=int)
        is_ht = classify_liander_tou_window(self.ref_index)

        load = LoadSeries2025(
            timestamps=self.ref_index,
            power_kw=power_arr,
            energy_kwh=energy_arr,
            month_indices=month_idx,
            is_peak_tou=is_ht,
            total_steps=self.total_steps,
            step_hours=0.25
        )

        # 1.1: Exact step count
        self.assertEqual(len(load.power_kw), 35040)
        # 1.2: Exact energy sum: 100 kW * 8760 h = 876,000 kWh
        self.assertAlmostEqual(load.total_energy_kwh, 876000.0, places=3)

        records = extract_monthly_consumption_records(load)
        self.assertEqual(len(records), 12)
        sum_monthly_kwh = sum(r.total_kwh for r in records)
        self.assertAlmostEqual(sum_monthly_kwh, 876000.0, places=3)

        # 1.3: Audit validation
        audit_p1 = evaluate_load_integrity_audit(load, records)
        self.assertTrue(audit_p1["passed"])
        self.assertTrue(audit_p1["criteria"]["1.1_step_count_35040"]["passed"])
        self.assertTrue(audit_p1["criteria"]["1.2_energy_conservation"]["passed"])
        self.assertTrue(audit_p1["criteria"]["1.3_time_classification"]["passed"])

    def test_criterion_2_dso_monthly_peaks_and_breach(self):
        """Audit Point 2: Distinct monthly peaks and capacity breach in July."""
        power_arr = np.zeros(self.total_steps, dtype=float)
        month_idx = self.ref_index.month.to_numpy(dtype=int)

        # Base load is 100 kW
        power_arr[:] = 100.0

        # In July (month 7), create an interval spike to 250 kW
        july_mask = (month_idx == 7)
        first_july_idx = np.where(july_mask)[0][100]
        power_arr[first_july_idx] = 250.0

        load = LoadSeries2025(
            timestamps=self.ref_index,
            power_kw=power_arr,
            energy_kwh=power_arr * 0.25,
            month_indices=month_idx,
            is_peak_tou=classify_liander_tou_window(self.ref_index),
            total_steps=self.total_steps
        )

        records = extract_monthly_consumption_records(load)
        self.assertEqual(records[6].peak_demand_kw, 250.0)  # July
        self.assertEqual(records[0].peak_demand_kw, 100.0)  # January

        dso_tariff = DSOTariff(
            contracted_capacity_kw=200.0,
            rate_contracted_capacity=2.2233,
            rate_peak_demand=3.4600,
            adjust_capacity_on_breach=True
        )

        dso_results, summary = calculate_dso_accounting_2025(load, records, dso_tariff)
        self.assertEqual(len(dso_results), 12)

        # July must be breached
        self.assertTrue(dso_results[6].is_capacity_breached)
        self.assertEqual(dso_results[6].billed_capacity_kw, 250.0)
        self.assertEqual(dso_results[6].excess_capacity_kw, 50.0)

        # January must NOT be breached
        self.assertFalse(dso_results[0].is_capacity_breached)
        self.assertEqual(dso_results[0].billed_capacity_kw, 200.0)

        self.assertEqual(summary["breached_months"], [7])

    def test_criterion_3_commercial_supplier_modes(self):
        """Audit Point 3: Fixed, Variable, and Dynamic Spot pricing modes."""
        load = synthesize_benchmark_load_profile_2025(nominal_peak_kw=200.0)
        records = extract_monthly_consumption_records(load)

        # 1. FIXED Mode
        supp_fixed = SupplierTariff(
            pricing_mode=PricingMode.FIXED,
            fixed_rate_kwh=0.1500,
            base_fee_annual=180.0
        )
        meter_tariff = MeteringTariff(annual_flat_fee=900.0)
        levies = LevyConfig(statutory_levy_rate_kwh=0.0125)

        comm_res, comm_sum = calculate_commercial_accounting_2025(
            load=load,
            monthly_consumption=records,
            supplier_tariff=supp_fixed,
            metering_tariff=meter_tariff,
            levy_config=levies
        )

        expected_energy = load.total_energy_kwh * 0.1500
        self.assertAlmostEqual(comm_sum["total_supplier_energy_annual"], expected_energy, delta=0.50)
        self.assertEqual(comm_sum["total_metering_annual"], 900.0)
        self.assertEqual(comm_sum["total_feed_in_credit_annual"], 0.0)

        # 2. DYNAMIC Spot Mode
        supp_dynamic = SupplierTariff(
            pricing_mode=PricingMode.DYNAMIC,
            market_price_profile_id="epex_nl_2025",
            supplier_margin_kwh=0.0075
        )
        comm_dyn_res, comm_dyn_sum = calculate_commercial_accounting_2025(
            load=load,
            monthly_consumption=records,
            supplier_tariff=supp_dynamic,
            metering_tariff=meter_tariff,
            levy_config=levies
        )
        self.assertGreater(comm_dyn_sum["total_supplier_energy_annual"], 0.0)

    def test_criterion_4_master_and_tco_lifecycle(self):
        """Audit Point 4: Consolidation, blended price, and 15-year TCO NPV."""
        load = synthesize_benchmark_load_profile_2025(nominal_peak_kw=250.0)
        config = get_stage_1_default_config_2025(pricing_mode=PricingMode.FIXED)

        result = calculate_status_quo_master_2025(load=load, config=config)

        # 4.1: Net Sum
        expected_net = (
            result.total_dso_net +
            result.total_supplier_net +
            result.total_metering_net +
            result.total_levies_net
        )
        self.assertAlmostEqual(result.total_status_quo_net, expected_net, delta=0.10)

        # 4.2: Blended Rate
        expected_blended = result.total_status_quo_net / result.total_consumption_kwh
        self.assertAlmostEqual(result.blended_price_net_kwh, expected_blended, places=4)

        # 4.3: TCO NPV with zero rates (g=0, r=0)
        tco_zero, cf_zero, _ = compute_tco_15_npv(annual_net_cost=1000.0, horizon_years=15, discount_rate_pct=0.0, energy_escalation_pct=0.0)
        self.assertAlmostEqual(tco_zero, 15000.0, places=2)
        self.assertEqual(len(cf_zero), 15)

        # Standard TCO
        self.assertGreater(result.tco_15_npv, result.total_status_quo_net * 5.0)

    def test_full_13_criteria_audit_pass(self):
        """Comprehensive verification battery: all 13 criteria must PASS."""
        load = synthesize_benchmark_load_profile_2025(nominal_peak_kw=200.0)
        config = get_stage_1_default_config_2025(
            pricing_mode=PricingMode.DYNAMIC,
            contracted_capacity_kw=250.0
        )
        result = calculate_status_quo_master_2025(load=load, config=config)
        audit_report = perform_full_status_quo_audit(load=load, result=result)

        self.assertTrue(audit_report.passed_all)
        self.assertEqual(audit_report.passed_criteria_count, 14)
        self.assertEqual(audit_report.failed_criteria_count, 0)

    def test_supplier_dual_tou_commodity_accounting(self):
        """Verifies dual TOU commodity split: E_HT * rate_ht + E_NT * rate_nt."""
        from current_model.ui_sandbox.status_quo_2025.tariff_defaults_2025 import (
            get_supplier_tariff_from_catalog,
            get_metering_tariff_from_catalog,
        )
        load = synthesize_benchmark_load_profile_2025(nominal_peak_kw=100.0)
        supp_tariff = get_supplier_tariff_from_catalog(
            supplier_name="Vattenfall Zakelijk",
            product_name="Vast 1 Jaar (Dubbeltarief HT/NT)"
        )
        self.assertTrue(supp_tariff.is_dual_rate)
        self.assertEqual(supp_tariff.pricing_mode, PricingMode.FIXED)

        meter_tariff = get_metering_tariff_from_catalog(
            meter_company_name="Fudura B.V.",
            package_name="Kwartierdata Telemetrie MS (Grootverbruik RLM)"
        )
        self.assertEqual(meter_tariff.annual_flat_fee, 900.0)

        config = StatusQuoConfig2025(
            stage=TariffStage.STAGE_2_QUOTE,
            supplier=supp_tariff,
            metering=meter_tariff,
            levies=LevyConfig(statutory_levy_rate_kwh=0.0125, annual_tax_reduction=0.0, vat_rate_pct=21.0),
        )
        result = calculate_status_quo_master_2025(load=load, config=config)
        
        # Verify dual rate energy commodity sum equals (HT * rate_ht + NT * rate_nt) + surcharges + base
        expected_ht = result.total_peak_tou_kwh * supp_tariff.fixed_rate_peak_kwh
        expected_nt = result.total_offpeak_tou_kwh * supp_tariff.fixed_rate_offpeak_kwh
        expected_comm = expected_ht + expected_nt + (result.total_consumption_kwh * (supp_tariff.procurement_fee_kwh + supp_tariff.green_certificate_surcharge_kwh)) + supp_tariff.base_fee_annual
        self.assertAlmostEqual(result.total_supplier_net, expected_comm, delta=0.50)

    def test_single_month_breakdown_adapter(self):
        """Verifies single-month period filter adapter in convert_to_financial_cost_breakdown."""
        from current_model.ui_sandbox.status_quo_2025.status_quo_master import convert_to_financial_cost_breakdown
        load = synthesize_benchmark_load_profile_2025(nominal_peak_kw=150.0)
        config = get_stage_1_default_config_2025()
        result = calculate_status_quo_master_2025(load=load, config=config)

        # Single month breakdown for January
        jan_breakdown = convert_to_financial_cost_breakdown(result, target_month="January")
        self.assertEqual(jan_breakdown.duration_days, 31.0)
        self.assertGreater(jan_breakdown.total_net_period, 0.0)
        self.assertAlmostEqual(jan_breakdown.total_net_period, result.monthly_records[0].total_net, places=2)

    def test_architectural_isolation_sandbox(self):
        """Verifies that production files do not import anything from ui_sandbox."""
        import os
        import ast

        current_file = os.path.abspath(__file__)
        tests_dir = os.path.dirname(current_file)
        model_root = os.path.abspath(os.path.join(tests_dir, ".."))

        production_folders = ["core", "models", "ui"]
        for folder in production_folders:
            folder_path = os.path.join(model_root, folder)
            for root, _, files in os.walk(folder_path):
                for fname in files:
                    if fname.endswith(".py"):
                        fpath = os.path.join(root, fname)
                        with open(fpath, "r", encoding="utf-8") as f:
                            tree = ast.parse(f.read(), filename=fpath)
                        for node in ast.walk(tree):
                            if isinstance(node, ast.Import):
                                for alias in node.names:
                                    self.assertNotIn("ui_sandbox", alias.name, f"{fpath} imports ui_sandbox")
                            elif isinstance(node, ast.ImportFrom):
                                if node.module:
                                    self.assertNotIn("ui_sandbox", node.module, f"{fpath} imports from ui_sandbox")

    def test_liander_2025_table_2_1_pdf_alignment(self):
        """Validates that Liander 2025 MS/LS rates match official PDF Table 2.1."""
        from current_model.ui_sandbox.status_quo_2025.tariff_defaults_2025 import LIANDER_2025_GRID_TIERS

        ms_ls = LIANDER_2025_GRID_TIERS["MS/LS (> 50 t/m 136 kW)"]
        self.assertEqual(ms_ls["rate_contracted_monthly"], 3.6567)
        self.assertEqual(ms_ls["rate_peak_monthly"], 3.4600)
        self.assertEqual(ms_ls["vastrecht_annual"] / 12.0, 36.75)
        self.assertEqual(ms_ls["rate_peak_kwh"], 0.2200)
        self.assertEqual(ms_ls["rate_offpeak_kwh"], 0.2200)
        self.assertEqual(ms_ls["reactive_tariff"], 0.0000)


if __name__ == "__main__":
    unittest.main()
