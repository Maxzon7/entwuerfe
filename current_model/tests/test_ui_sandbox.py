"""
========================================================================================
Unit Tests: UI Sandbox Isolation & Integrity (tests/test_ui_sandbox.py)
========================================================================================
Verifies that:
1. ui_sandbox/sandbox_app.py compiles and imports cleanly.
2. The main application (app.py, core, models, ui) never imports from ui_sandbox.
========================================================================================
"""

import unittest
import os
import sys
import glob
import ast

# Ensure project root is in sys.path
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)



class TestUISandboxIsolation(unittest.TestCase):
    """Ensures ui_sandbox exists, compiles cleanly, and remains strictly isolated from production code."""

    def setUp(self):
        this_dir = os.path.dirname(os.path.abspath(__file__))
        self.current_model_dir = os.path.abspath(os.path.join(this_dir, ".."))
        self.sandbox_dir = os.path.join(self.current_model_dir, "ui_sandbox")

    def test_sandbox_directory_and_entrypoint_exist(self):
        """Verifies sandbox directory and Currentsituation_sandbox entrypoint exist."""
        self.assertTrue(os.path.isdir(self.sandbox_dir), "ui_sandbox directory must exist")

        # Active Sandbox: Current Situation Sandbox
        currsit_dir = os.path.join(self.sandbox_dir, "Currentsituation_sandbox")
        self.assertTrue(os.path.isdir(currsit_dir), "ui_sandbox/Currentsituation_sandbox directory must exist")
        currsit_app = os.path.join(currsit_dir, "app.py")
        self.assertTrue(os.path.isfile(currsit_app), "ui_sandbox/Currentsituation_sandbox/app.py must exist")

        # Engine package inside Currentsituation_sandbox
        currsit_engine = os.path.join(currsit_dir, "engine")
        self.assertTrue(os.path.isdir(currsit_engine), "ui_sandbox/Currentsituation_sandbox/engine directory must exist")

        # Active Sandbox: BESS Sandbox
        bess_dir = os.path.join(self.sandbox_dir, "BESS_sandbox")
        self.assertTrue(os.path.isdir(bess_dir), "ui_sandbox/BESS_sandbox directory must exist")
        for expected_file in [
            "__init__.py", "app.py", "baseline_presets.py", "sandbox_bess_engine.py",
            "view_problem.py", "view_technical.py", "view_financial.py", "view_optimizer.py", "README.md"
        ]:
            f_path = os.path.join(bess_dir, expected_file)
            self.assertTrue(os.path.isfile(f_path), f"ui_sandbox/BESS_sandbox/{expected_file} must exist")

    def test_production_codebase_never_imports_ui_sandbox(self):
        """Strict architectural guard: Main app, core, models, and ui must NEVER import ui_sandbox."""
        prod_patterns = [
            os.path.join(self.current_model_dir, "*.py"),
            os.path.join(self.current_model_dir, "core", "**", "*.py"),
            os.path.join(self.current_model_dir, "models", "**", "*.py"),
            os.path.join(self.current_model_dir, "ui", "**", "*.py"),
        ]

        illegal_imports = []
        for pattern in prod_patterns:
            for py_file in glob.glob(pattern, recursive=True):
                if "ui_sandbox" in py_file or "__pycache__" in py_file:
                    continue
                try:
                    with open(py_file, "r", encoding="utf-8") as f:
                        tree = ast.parse(f.read(), filename=py_file)
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Import):
                            for alias in node.names:
                                if "ui_sandbox" in alias.name:
                                    illegal_imports.append((py_file, alias.name))
                        elif isinstance(node, ast.ImportFrom):
                            if node.module and "ui_sandbox" in node.module:
                                illegal_imports.append((py_file, node.module))
                except Exception as err:
                    self.fail(f"Could not parse {py_file}: {err}")

        self.assertEqual(
            len(illegal_imports), 0,
            f"Illegal imports from ui_sandbox detected in production code: {illegal_imports}"
        )

    def test_bess_sandbox_dual_sizing_and_dispatch(self):
        """Verifies BESS sandbox dual sizing, generator assist simulation, and economics."""
        from ui_sandbox.BESS_sandbox import (
            get_case1_liander_industrial_preset,
            compute_dual_bess_sizing,
            simulate_sandbox_bess_dispatch,
            evaluate_sandbox_bess_economics
        )

        preset = get_case1_liander_industrial_preset()
        self.assertIsNotNone(preset)
        self.assertGreater(preset.grid_limit_kw, 0.0)

        # 1. Dual Sizing
        dual_rec = compute_dual_bess_sizing(
            load_series=preset.load_df["Total_Demand_kW"],
            grid_limit_kw=preset.grid_limit_kw,
            target_percentile=90.0,
            round_trip_efficiency_pct=preset.bess_config.round_trip_efficiency_pct,
            soc_min_pct=preset.bess_config.soc_min_pct,
            soc_max_pct=preset.bess_config.soc_max_pct,
            unit_capacity_kwh=preset.bess_config.unit_capacity_kwh,
            step_hours=0.25
        )
        self.assertGreater(dual_rec.option_a_gross_kwh, 0.0)
        self.assertGreater(dual_rec.option_b_gross_kwh, 0.0)
        self.assertGreaterEqual(dual_rec.option_a_gross_kwh, dual_rec.option_b_gross_kwh)
        self.assertGreater(dual_rec.inverter_power_kw, 0.0)

        # 2. Dispatch with Option B (BESS + Generator)
        cfg_b = preset.bess_config
        cfg_b.capacity_kwh = dual_rec.option_b_gross_kwh
        cfg_b.unit_count = dual_rec.option_b_unit_count
        cfg_b.max_discharge_power_kw = dual_rec.inverter_power_kw
        cfg_b.max_charge_power_kw = dual_rec.inverter_power_kw

        sim_res = simulate_sandbox_bess_dispatch(
            bess_config=cfg_b,
            load_df=preset.load_df,
            grid_limit_kw=preset.grid_limit_kw,
            step_hours=0.25,
            power_col="Total_Demand_kW",
            enable_generator_assist=True,
            generator_rated_kw=dual_rec.required_generator_kw
        )
        self.assertIn("P_Generator_kW", sim_res.df_timeseries.columns)
        # Verify 100% feasibility under hybrid option
        res_overload = sim_res.diagnostics_after.get("overload_peak_kw", 0.0)
        self.assertLessEqual(res_overload, 0.05, "Hybrid BESS + Generator should eliminate all overloads")

        # 3. Financial evaluation with generator
        fin_res = evaluate_sandbox_bess_economics(
            bess_config=cfg_b,
            sim_result=sim_res,
            contract_baseline=preset.contract_baseline,
            contract_bess=preset.contract_bess,
            avoided_grid_upgrade_capex=preset.avoided_grid_upgrade_capex,
            avoided_monthly_transformer_rent=preset.avoided_monthly_transformer_rent,
            generator_capex=dual_rec.required_generator_kw * 120.0,
            generator_monthly_rent=0.0,
            diesel_price_per_liter=1.65,
            fuel_liters_per_kwh=0.28
        )
        self.assertIsNotNone(fin_res)
        self.assertGreater(fin_res.annual_gross_savings, 0.0)
        self.assertGreater(fin_res.annual_opex_year1, 0.0)

    def test_bess_sandbox_view_problem_diagnostics(self):
        """Verifies that view_problem imports engine cleanly and calculate_excel_bess_sizing_and_diagnostics runs."""
        from ui_sandbox.BESS_sandbox import view_problem, get_case1_liander_industrial_preset
        preset = get_case1_liander_industrial_preset()

        self.assertTrue(hasattr(view_problem, "engine"), "view_problem module must have engine imported")
        self.assertIsNotNone(view_problem.engine, "engine in view_problem must not be None")

        power_col = "Total_Demand_kW" if "Total_Demand_kW" in preset.load_df.columns else "P_Load_kW"
        excel_sizing = view_problem.engine.calculate_excel_bess_sizing_and_diagnostics(
            preset.load_df[power_col], preset.grid_limit_kw, step_hours=0.25
        )
        self.assertIsNotNone(excel_sizing)
        self.assertGreater(excel_sizing.worst_cluster_net_deficit_kwh, 0.0)

    def test_bess_sandbox_presets_and_quick_limit_callbacks(self):
        """Verifies presets have distinct grid limits and view_problem uses on_click callbacks for limits."""
        from ui_sandbox.BESS_sandbox import baseline_presets as presets
        import inspect
        from ui_sandbox.BESS_sandbox import view_problem

        case1 = presets.get_case1_liander_industrial_preset()
        case2 = presets.get_case2_enexis_commercial_preset()

        self.assertEqual(case1.grid_limit_kw, 147.0)
        self.assertEqual(case2.grid_limit_kw, 150.0)

        # Check that view_problem code uses on_click rather than setting session_state directly in if button
        src = inspect.getsource(view_problem.render_problem_baseline_tab)
        self.assertIn("on_click=_set_quick_grid_limit", src)
        self.assertNotIn("if q_cols[0].button", src)

    def test_bess_sandbox_exceedance_energy_summary(self):
        """Verifies calculation of total unmitigated exceedance kWh, peak excess kW, and count of overload hours."""
        from ui_sandbox.BESS_sandbox import (
            get_case1_liander_industrial_preset,
            compute_exceedance_energy_summary
        )
        preset = get_case1_liander_industrial_preset()
        power_col = "Total_Demand_kW" if "Total_Demand_kW" in preset.load_df.columns else "P_Load_kW"
        summary = compute_exceedance_energy_summary(
            preset.load_df[power_col],
            preset.grid_limit_kw,
            step_hours=0.25
        )
        self.assertGreater(summary["total_exceedance_kwh"], 0.0)
        self.assertGreater(summary["max_overload_kw"], 0.0)
        self.assertGreater(summary["overload_hours"], 0.0)
        self.assertGreater(summary["overload_intervals"], 0)
        # Peak excess + grid_limit should equal max demand
        max_demand = float(preset.load_df[power_col].max())
        self.assertAlmostEqual(summary["max_overload_kw"] + preset.grid_limit_kw, max_demand, places=2)

    def test_bess_sandbox_simultaneous_bottlenecks(self):
        """Verifies all 4 criteria are evaluated simultaneously without early if/elif exit."""
        from ui_sandbox.BESS_sandbox import (
            get_case1_liander_industrial_preset,
            evaluate_comprehensive_bottlenecks,
            calculate_excel_bess_sizing_and_diagnostics,
            simulate_sandbox_bess_dispatch
        )
        from models.bess import BESSConfig

        preset = get_case1_liander_industrial_preset()
        power_col = "Total_Demand_kW" if "Total_Demand_kW" in preset.load_df.columns else "P_Load_kW"

        excel_sizing = calculate_excel_bess_sizing_and_diagnostics(
            preset.load_df[power_col], preset.grid_limit_kw, step_hours=0.25
        )

        # Deliberately undersized test configuration to trigger multiple bottlenecks simultaneously
        undersized_cfg = BESSConfig(
            capacity_kwh=excel_sizing.min_required_gross_kwh * 0.3,
            max_discharge_power_kw=excel_sizing.min_required_discharge_kw * 0.5,
            max_charge_power_kw=excel_sizing.min_required_charge_kw * 0.5,
            round_trip_efficiency_pct=preset.bess_config.round_trip_efficiency_pct,
            soc_min_pct=preset.bess_config.soc_min_pct,
            soc_max_pct=preset.bess_config.soc_max_pct,
            initial_soc_pct=preset.bess_config.initial_soc_pct,
            unit_capacity_kwh=preset.bess_config.unit_capacity_kwh
        )


        sim_res = simulate_sandbox_bess_dispatch(
            bess_config=undersized_cfg,
            load_df=preset.load_df,
            grid_limit_kw=preset.grid_limit_kw,
            step_hours=0.25,
            power_col=power_col
        )

        audit = evaluate_comprehensive_bottlenecks(
            load_series=preset.load_df[power_col],
            grid_limit_kw=preset.grid_limit_kw,
            bess_config=undersized_cfg,
            step_hours=0.25,
            sim_result=sim_res
        )

        # Must evaluate all 4 checks, not exit on first failure
        self.assertEqual(len(audit.checks), 4)
        check_keys = [c.key for c in audit.checks]
        self.assertIn("discharge_power", check_keys)
        self.assertIn("storage_capacity", check_keys)
        self.assertIn("recharge_power", check_keys)
        self.assertIn("grid_headroom", check_keys)

        # Under 30% sizing, it must not be fully feasible
        self.assertFalse(audit.all_passed)
        self.assertGreater(audit.failed_count, 0)


    def test_bess_sandbox_pareto_curve(self):
        """Verifies Pareto tradeoff calculation returns valid curve points ending in 100% at reference sizing."""
        from ui_sandbox.BESS_sandbox import (
            get_case1_liander_industrial_preset,
            compute_pareto_coverage_curve
        )
        preset = get_case1_liander_industrial_preset()
        power_col = "Total_Demand_kW" if "Total_Demand_kW" in preset.load_df.columns else "P_Load_kW"

        pareto_res = compute_pareto_coverage_curve(
            load_series=preset.load_df[power_col],
            grid_limit_kw=preset.grid_limit_kw,
            round_trip_efficiency_pct=preset.bess_config.round_trip_efficiency_pct,
            soc_min_pct=preset.bess_config.soc_min_pct,
            soc_max_pct=preset.bess_config.soc_max_pct,
            step_hours=0.25
        )

        self.assertGreaterEqual(len(pareto_res.coverage_pct), 3)
        self.assertIn(100.0, pareto_res.coverage_pct)
        idx_100 = pareto_res.coverage_pct.index(100.0)
        self.assertAlmostEqual(pareto_res.residual_deficit_kwh[idx_100], 0.0, places=1)
        self.assertGreater(pareto_res.required_gross_kwh[idx_100], 0.0)

    def test_bess_sandbox_synced_charts(self):
        """Verifies Plotly 2-in-1 synced chart generation with shared x-axes and annotations."""
        from ui_sandbox.BESS_sandbox import (
            get_case1_liander_industrial_preset,
            simulate_sandbox_bess_dispatch,
            create_synced_dispatch_soc_figure,
            create_pareto_tradeoff_figure,
            compute_pareto_coverage_curve
        )
        preset = get_case1_liander_industrial_preset()
        power_col = "Total_Demand_kW" if "Total_Demand_kW" in preset.load_df.columns else "P_Load_kW"

        sim_res = simulate_sandbox_bess_dispatch(
            bess_config=preset.bess_config,
            load_df=preset.load_df,
            grid_limit_kw=preset.grid_limit_kw,
            step_hours=0.25,
            power_col=power_col
        )

        fig_synced = create_synced_dispatch_soc_figure(
            df=sim_res.df_timeseries,
            grid_limit_kw=preset.grid_limit_kw,
            soc_min_pct=preset.bess_config.soc_min_pct,
            soc_max_pct=preset.bess_config.soc_max_pct,
            capacity_kwh=preset.bess_config.capacity_kwh
        )
        self.assertIsNotNone(fig_synced)
        # Shared x-axes check: layout should contain xaxis or xaxis2
        self.assertTrue(hasattr(fig_synced.layout, "xaxis2") or hasattr(fig_synced.layout, "xaxis"))

        # Test Pareto chart
        pareto_res = compute_pareto_coverage_curve(
            load_series=preset.load_df[power_col],
            grid_limit_kw=preset.grid_limit_kw,
            round_trip_efficiency_pct=preset.bess_config.round_trip_efficiency_pct,
            soc_min_pct=preset.bess_config.soc_min_pct,
            soc_max_pct=preset.bess_config.soc_max_pct,
            step_hours=0.25
        )
        fig_pareto = create_pareto_tradeoff_figure(pareto_res)
        self.assertIsNotNone(fig_pareto)


class TestClassicInvoiceReconciliation(unittest.TestCase):
    """Verifies that tab_invoice_experimental derives positions matching master results to the cent."""

    def test_annual_and_monthly_cent_reconciliation(self):
        from ui_sandbox.Currentsituation_sandbox.engine.consumption_pipeline import (
            synthesize_benchmark_load_profile_2025
        )
        from ui_sandbox.Currentsituation_sandbox.engine.tariff_defaults_2025 import (
            get_stage_1_default_config_2025
        )
        from ui_sandbox.Currentsituation_sandbox.engine.config_and_models import PricingMode
        from ui_sandbox.Currentsituation_sandbox.engine.status_quo_master import (
            calculate_status_quo_master_2025
        )
        from ui_sandbox.Currentsituation_sandbox.contract.tab_invoice_experimental import (
            build_invoice_positions
        )

        load = synthesize_benchmark_load_profile_2025(nominal_peak_kw=250.0)

        for mode in [PricingMode.FIXED, PricingMode.DYNAMIC]:
            config = get_stage_1_default_config_2025(pricing_mode=mode, contracted_capacity_kw=250.0)
            if mode == PricingMode.FIXED:
                config.supplier.is_dual_rate = True
            result = calculate_status_quo_master_2025(load=load, config=config)

            # 1. Test Annual Statement
            inv_ann = build_invoice_positions(result, config, "Annual Statement 2025 (Full Year)")
            self.assertAlmostEqual(inv_ann["subtotal_a"], result.total_supplier_net, places=2)
            self.assertAlmostEqual(inv_ann["subtotal_b"], result.total_dso_net, places=2)
            self.assertAlmostEqual(inv_ann["subtotal_c"], result.total_metering_net, places=2)
            self.assertAlmostEqual(inv_ann["subtotal_d"], result.total_levies_net, places=2)
            self.assertAlmostEqual(inv_ann["total_net"], result.total_status_quo_net, places=2)
            self.assertAlmostEqual(inv_ann["total_gross"], result.total_status_quo_gross, places=2)

            sum_lines = (
                sum(p["amount_net"] for p in inv_ann["block_a"])
                + sum(p["amount_net"] for p in inv_ann["block_b"])
                + sum(p["amount_net"] for p in inv_ann["block_c"])
                + sum(p["amount_net"] for p in inv_ann["block_d"])
            )
            self.assertAlmostEqual(sum_lines, result.total_status_quo_net, places=2)

            # 2. Test All 12 Individual Months
            for r in result.monthly_records:
                inv_m = build_invoice_positions(result, config, f"{r.month_name} 2025")
                self.assertAlmostEqual(inv_m["total_net"], r.total_net, places=2)
                self.assertAlmostEqual(inv_m["total_gross"], r.total_gross, places=2)
                sum_m_lines = (
                    sum(p["amount_net"] for p in inv_m["block_a"])
                    + sum(p["amount_net"] for p in inv_m["block_b"])
                    + sum(p["amount_net"] for p in inv_m["block_c"])
                    + sum(p["amount_net"] for p in inv_m["block_d"])
                )
                self.assertAlmostEqual(sum_m_lines, r.total_net, places=2)


if __name__ == "__main__":
    unittest.main()



