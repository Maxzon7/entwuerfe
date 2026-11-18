"""
========================================================================================
Unit Tests for Combined System Sandbox (tests/test_combined_sandbox.py)
========================================================================================

Verifies:
  1. Default Amsterdam GPS (52.3676, 4.9041), transparent Solar kWp derivation formula,
     Inverter AC Limit & Efficiency (98%), and EU PVGIS label.
  2. All 8 enable/disable combinations of Solar, Battery, and Generator over 35,040 steps.
  3. Operating Rules 1, 2, and 3 (including Rule 3 Option D "all_sources").
  4. Dual-Sizing for Battery (Standalone vs. Coupled + 4-Criterion Bottleneck Table)
     and Dual-Sizing for Generator (Standalone vs. Coupled).
  5. Lazy-Loaded Financial Evaluation Engine (`evaluate_combined_financials`) with 4-Pillar
     Tariff, 15-Year Cashflow Table, 15Y NPV, Cost Comparison Chart & 4-sheet Excel export.
  6. Interactive Plotly figures & Clean Screen Policy terminology compliance.
========================================================================================
"""

import io
import os
import zipfile
import unittest
import numpy as np
import pandas as pd
import openpyxl

from current_model.core.csv_parser import read_raw_content, parse_csv_content
from current_model.core.load_processor import process_load_profile_data
from current_model.ui_sandbox.Currentsituation_sandbox.engine.consumption_pipeline import (
    synthesize_benchmark_load_profile_2025,
    normalize_load_profile_2025,
)
from current_model.ui_sandbox.Currentsituation_sandbox.engine.config_and_models import LoadSeries2025
from current_model.ui_sandbox.Combined_sandbox.combined_sandbox_engine import (
    ENGINE_VERSION,
    MIX_STRATEGY_OPTIONS,
    CombinedSystemConfig,
    InteractionRulesConfig,
    CombinedFinancialConfig,
    SystemUtilizationDiagnostics,
    derive_solar_sizing_and_formula,
    compute_dual_battery_sizing,
    refresh_bottleneck_table_configured_status,
    compute_dual_generator_sizing,
    compute_coordinated_mix_sizing,
    simulate_combined_system_dispatch,
    compute_system_utilization_diagnostics,
    evaluate_combined_financials,
)
from current_model.ui_sandbox.Combined_sandbox.combined_charts import (
    _mask_gap_for_webgl_fill,
    create_consumption_baseline_figure,
    create_combined_dispatch_soc_figure,
    create_financial_cost_comparison_figure,
    create_financial_tco_trajectory_figure,
    create_financial_waterfall_bridge_figure,
    create_financial_monthly_cashflow_figure,
    create_monthly_grid_bill_progression_figure,
    create_dso_isolated_breakdown_figure,
    create_supplier_isolated_breakdown_figure,
    create_tax_isolated_breakdown_figure,
    create_solar_isolated_financial_figure,
    create_battery_isolated_financial_figure,
    create_generator_isolated_financial_figure,
    create_supply_mix_pie_figure,
    create_component_utilization_bars_figure,
)
from current_model.ui_sandbox.Combined_sandbox.combined_excel_exporter import (
    build_combined_verification_excel_bytes,
)


class TestCombinedSandbox(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.load_series = synthesize_benchmark_load_profile_2025(nominal_peak_kw=250.0)
        cls.load_kw = cls.load_series.power_kw
        cls.timestamps = cls.load_series.timestamps

    def test_amsterdam_default_gps_and_solar_derivation(self):
        """Verifies default GPS is Amsterdam (52.3676, 4.9041) and transparent Solar formula."""
        default_cfg = CombinedSystemConfig()
        self.assertAlmostEqual(default_cfg.latitude, 52.3676, places=4)
        self.assertAlmostEqual(default_cfg.longitude, 4.9041, places=4)
        self.assertAlmostEqual(default_cfg.inverter_efficiency_pct, 98.0, places=1)
        self.assertIn("Amsterdam", default_cfg.site_preset)

        deriv_share = derive_solar_sizing_and_formula(
            annual_consumption_kwh=250000.0,
            specific_yield_kwh_per_kwp=1000.0,
            sizing_method="target_share_pct",
            direct_kwp=100.0,
            target_share_pct=60.0,
            panel_wp=450.0,
            enable_solar=True,
        )
        self.assertAlmostEqual(deriv_share.installed_kwp, 150.0, places=1)
        self.assertEqual(deriv_share.panel_count, 333)
        self.assertIn("EU PVGIS (ERA5 TMY, 15-min resolution)", deriv_share.source_info_text)
        self.assertIn("150.0 kWp (333 panels @ 450 Wp)", deriv_share.formula_text)

    def test_all_enable_disable_combinations(self):
        """Tests all 8 on/off combinations of Solar, Battery, and Generator."""
        rules = InteractionRulesConfig()
        for en_solar in (False, True):
            for en_bess in (False, True):
                for en_gen in (False, True):
                    cfg = CombinedSystemConfig(
                        grid_limit_kw=180.0,
                        enable_solar=en_solar,
                        enable_battery=en_bess,
                        enable_generator=en_gen,
                    )
                    res = simulate_combined_system_dispatch(
                        load_kw=self.load_kw,
                        timestamps=self.timestamps,
                        system_cfg=cfg,
                        rules_cfg=rules,
                    )
                    self.assertEqual(len(res.grid_import_kw), 35040)
                    self.assertEqual(len(res.summary_table_df), 6)
                    self.assertEqual(len(res.monthly_balance_df), 12)
                    # Pure dispatch simulation does not run sizing pre-calculations internally
                    self.assertTrue(res.bess_bottleneck_df.empty)
                    # Lazy financials: financial_kpis is None until evaluate_combined_financials is called
                    self.assertIsNone(res.financial_kpis)
                    if not en_solar:
                        self.assertEqual(res.kpis.solar_total_generation_kwh, 0.0)
                    if not en_bess:
                        self.assertEqual(res.kpis.battery_total_discharged_kwh, 0.0)
                    if not en_gen:
                        self.assertEqual(res.kpis.generator_total_generation_kwh, 0.0)

    def test_interaction_rules_behavior_including_option_d(self):
        """Verifies Rules 1, 2, and 3 (including Option D 'all_sources') produce valid outcomes."""
        cfg = CombinedSystemConfig(
            grid_limit_kw=150.0,
            enable_solar=True,
            solar_sizing_method="direct_kwp",
            solar_kwp=250.0,
            enable_battery=True,
            battery_capacity_kwh=400.0,
            battery_power_kw=150.0,
            enable_generator=True,
            generator_rated_kw=80.0,
            generator_min_load_pct=25.0,
            gen_min_runtime_minutes=15,
        )

        res_bess_first = simulate_combined_system_dispatch(
            load_kw=self.load_kw,
            timestamps=self.timestamps,
            system_cfg=cfg,
            rules_cfg=InteractionRulesConfig(
                rule1_peak_priority="battery_first",
                rule2_battery_strategy="peak_shaving_only",
                rule3_charging_sources="solar_only",
            ),
        )
        res_gen_first = simulate_combined_system_dispatch(
            load_kw=self.load_kw,
            timestamps=self.timestamps,
            system_cfg=cfg,
            rules_cfg=InteractionRulesConfig(
                rule1_peak_priority="generator_first",
                rule2_battery_strategy="peak_shaving_only",
                rule3_charging_sources="solar_only",
            ),
        )
        self.assertGreater(
            res_gen_first.kpis.generator_total_generation_kwh,
            res_bess_first.kpis.generator_total_generation_kwh,
        )
        self.assertGreater(
            res_bess_first.kpis.battery_total_discharged_kwh,
            res_gen_first.kpis.battery_total_discharged_kwh,
        )

        res_sc_reserve = simulate_combined_system_dispatch(
            load_kw=self.load_kw,
            timestamps=self.timestamps,
            system_cfg=cfg,
            rules_cfg=InteractionRulesConfig(
                rule1_peak_priority="battery_first",
                rule2_battery_strategy="self_consumption_reserve",
                peak_reserve_soc_pct=30.0,
                rule3_charging_sources="solar_only",
            ),
        )
        self.assertGreater(
            res_sc_reserve.kpis.battery_total_discharged_kwh,
            res_bess_first.kpis.battery_total_discharged_kwh,
        )

        res_all_sources = simulate_combined_system_dispatch(
            load_kw=self.load_kw,
            timestamps=self.timestamps,
            system_cfg=cfg,
            rules_cfg=InteractionRulesConfig(
                rule1_peak_priority="battery_first",
                rule2_battery_strategy="self_consumption_reserve",
                peak_reserve_soc_pct=40.0,
                rule3_charging_sources="all_sources",
            ),
        )
        self.assertGreater(res_all_sources.kpis.battery_charged_from_grid_kwh, 0.0)

    def test_standalone_battery_peak_shaving_and_grid_recharge(self):
        """Verifies that standalone BESS (enable_solar=False) operates strictly as peak_shaving_only,
        recharges from grid headroom, and does not drain to 30% reserve into normal load."""
        from current_model.ui_sandbox.Combined_sandbox.combined_sandbox_engine import ENGINE_VERSION
        self.assertEqual(ENGINE_VERSION, "13.7")

        cfg = CombinedSystemConfig(
            grid_limit_kw=180.0,
            enable_solar=False,
            enable_battery=True,
            battery_capacity_kwh=500.0,
            battery_power_kw=100.0,
            min_soc_pct=10.0,
            max_soc_pct=90.0,
        )
        # Default rules have rule2="self_consumption_reserve" and rule3="solar_only"
        default_rules = InteractionRulesConfig()
        res = simulate_combined_system_dispatch(
            load_kw=self.load_kw,
            timestamps=self.timestamps,
            system_cfg=cfg,
            rules_cfg=default_rules,
        )

        # 1. Battery starts fully charged at max_soc_pct (90%)
        self.assertAlmostEqual(res.bess_soc_pct[0], 90.0, places=1)

        # 2. Battery never discharges into normal load below grid limit
        normal_load_mask = self.load_kw <= 180.0
        self.assertTrue(np.all(res.bess_discharge_kw[normal_load_mask] == 0.0))

        # 3. Battery recharges from grid headroom whenever below max_soc_pct
        self.assertGreater(res.kpis.battery_charged_from_grid_kwh, 1000.0)
        self.assertGreater(res.kpis.battery_equivalent_cycles, 10.0)

        # 4. Standalone sizing allows grid recharge
        dual_bess = compute_dual_battery_sizing(self.load_kw, cfg, default_rules)
        self.assertLess(dual_bess.coupled_100_kwh, 20000.0)

    def test_dual_sizing_and_4_bottleneck_table(self):
        """Verifies Dual-Sizing (Standalone vs. Coupled) for Battery and Generator + 4-Bottleneck Table."""
        cfg = CombinedSystemConfig(
            grid_limit_kw=180.0,
            enable_solar=True,
            solar_sizing_method="target_share_pct",
            target_consumption_share_pct=60.0,
            enable_battery=True,
            battery_capacity_kwh=300.0,
            battery_power_kw=100.0,
            enable_generator=True,
            generator_rated_kw=40.0,
        )
        rules = InteractionRulesConfig(
            rule1_peak_priority="generator_first",
            rule2_battery_strategy="peak_shaving_only",
            rule3_charging_sources="solar_and_grid",
        )

        bess_dual = compute_dual_battery_sizing(self.load_kw, cfg, rules)
        self.assertGreater(bess_dual.standalone_100_kwh, 0.0)
        self.assertGreater(bess_dual.standalone_100_kw, 0.0)
        # Coupled required power is smaller than Standalone when Generator is active
        self.assertLessEqual(bess_dual.coupled_100_kw, bess_dual.standalone_100_kw)
        self.assertEqual(len(bess_dual.bottleneck_table_df), 4)
        self.assertIn("1. Peak Discharge Power (kW)", bess_dual.bottleneck_table_df["Criterion"].values)
        self.assertIn("2. Single Peak Event Energy (kWh)", bess_dual.bottleneck_table_df["Criterion"].values)
        self.assertIn("3. Multi-Day Cluster Energy (kWh)", bess_dual.bottleneck_table_df["Criterion"].values)
        self.assertIn("4. Available Recharge Headroom", bess_dual.bottleneck_table_df["Criterion"].values)

        # Verify O(1) bottleneck status column refresh without re-running 35,040-step loops
        refreshed_df = refresh_bottleneck_table_configured_status(
            bess_dual,
            configured_kwh=5000.0,
            configured_kw=500.0,
            enable_battery=True,
        )
        self.assertEqual(len(refreshed_df), 4)
        self.assertEqual(refreshed_df.iloc[0]["Configured Battery"], "500.0 kW")
        self.assertEqual(refreshed_df.iloc[0]["Status"], "Pass")
        self.assertEqual(refreshed_df.iloc[1]["Configured Battery"], "5,000.0 kWh")

        gen_dual = compute_dual_generator_sizing(self.load_kw, self.timestamps, cfg, rules)
        self.assertGreater(gen_dual.standalone_100_kw, 0.0)
        self.assertLessEqual(gen_dual.coupled_100_kw, gen_dual.standalone_100_kw)

    def test_financials_4pillar_15y_cashflow_and_4sheet_excel_export(self):
        """Verifies Lazy-Financials protection in Excel export, 4-Pillar Financials, 15Y Cashflow/NPV, and 4-sheet Excel export."""
        cfg = CombinedSystemConfig(grid_limit_kw=180.0, enable_financials=False)
        rules = InteractionRulesConfig()
        sim_res = simulate_combined_system_dispatch(
            load_kw=self.load_kw,
            timestamps=self.timestamps,
            system_cfg=cfg,
            rules_cfg=rules,
        )

        # 1. When Financials is disabled, Excel export must NOT secretly trigger evaluate_combined_financials
        excel_bytes_no_fin = build_combined_verification_excel_bytes(sim_res)
        self.assertIsNone(sim_res.financial_kpis)
        self.assertGreater(len(excel_bytes_no_fin), 50000)

        # 2. When Financials is enabled, evaluate_combined_financials populates all 4-Pillar & 15Y cashflow tables
        sim_res.system_config.enable_financials = True
        fin_cfg = CombinedFinancialConfig()
        evaluate_combined_financials(sim_res, fin_cfg)

        self.assertIsNotNone(sim_res.financial_kpis)
        self.assertGreater(sim_res.financial_kpis.total_capex_eur, 0.0)
        self.assertGreater(sim_res.financial_kpis.baseline_pillar1_supply_eur, 0.0)
        self.assertGreater(sim_res.financial_kpis.baseline_pillar2_dso_eur, 0.0)
        self.assertEqual(len(sim_res.financial_table_df), 6)
        self.assertEqual(len(sim_res.monthly_cost_df), 12)
        self.assertEqual(len(sim_res.cashflow_15y_df), 16)  # Years 0..15

        # Verify dynamic 15-year lifecycle metrics
        self.assertGreater(sim_res.financial_kpis.tco_15y_baseline_eur, 0.0)
        self.assertGreater(sim_res.financial_kpis.tco_15y_combined_eur, 0.0)
        self.assertGreater(sim_res.financial_kpis.gross_bill_savings_y1_eur, 0.0)
        self.assertIn("Cumulative TCO Current situation (€)", sim_res.cashflow_15y_df.columns)
        self.assertIn("Tariff Escalation Factor", sim_res.cashflow_15y_df.columns)
        self.assertIn("System O&M & Fuel (€)", sim_res.cashflow_15y_df.columns)

        # Verify all 4 financial decision charts build cleanly
        fig_cost = create_financial_cost_comparison_figure(sim_res)
        self.assertEqual(len(fig_cost.data), 6)

        fig_tco = create_financial_tco_trajectory_figure(sim_res)
        self.assertEqual(len(fig_tco.data), 4)
        tco_trace_names = [t.name for t in fig_tco.data]
        self.assertIn("Cumulative Net Cashflow (EUR)", tco_trace_names)
        self.assertIn("Annual Net Cashflow (EUR/yr)", tco_trace_names)
        self.assertIn("Current System Annual Bill (EUR/yr)", tco_trace_names)
        self.assertIn("Combined System Annual Cost (EUR/yr)", tco_trace_names)

        # Also test No-Break-Even annotation branch (payback_years=None)
        old_pb = sim_res.financial_kpis.payback_years
        sim_res.financial_kpis.payback_years = None
        fig_tco_nopb = create_financial_tco_trajectory_figure(sim_res)
        self.assertEqual(len(fig_tco_nopb.data), 4)
        self.assertTrue(any("No Break-Even" in str(a.text) for a in fig_tco_nopb.layout.annotations))
        sim_res.financial_kpis.payback_years = old_pb

        fig_bridge = create_financial_waterfall_bridge_figure(sim_res)
        self.assertGreater(len(fig_bridge.data), 0)

        fig_monthly = create_financial_monthly_cashflow_figure(sim_res)
        self.assertEqual(len(fig_monthly.data), 3)

        excel_bytes = build_combined_verification_excel_bytes(sim_res)
        self.assertGreater(len(excel_bytes), 50000)

        wb = openpyxl.load_workbook(io.BytesIO(excel_bytes), read_only=True)
        self.assertEqual(
            wb.sheetnames,
            ["Summary & KPIs", "15-Min Dispatch", "Monthly Balance", "Cost & Tariffs"],
        )
        wb.close()

    def test_charts_and_clean_screen_terminology_guard(self):
        """Verifies Plotly figures build cleanly and prohibited marketing terms are absent."""
        cfg = CombinedSystemConfig(grid_limit_kw=180.0)
        rules = InteractionRulesConfig()
        sim_res = simulate_combined_system_dispatch(
            load_kw=self.load_kw,
            timestamps=self.timestamps,
            system_cfg=cfg,
            rules_cfg=rules,
        )

        for tf in ("7D", "1M", "3M", "All"):
            fig1 = create_consumption_baseline_figure(self.timestamps, self.load_kw, timeframe=tf)
            fig2 = create_combined_dispatch_soc_figure(sim_res, timeframe=tf)
            self.assertGreater(len(fig1.data), 0)
            self.assertGreater(len(fig2.data), 4)
            self.assertEqual(fig2.data[0].type, "scattergl")
            self.assertEqual(len(fig2.data[0].x), 35040)
            self.assertGreaterEqual(fig2.layout.margin.t, 90)
            self.assertGreaterEqual(fig2.layout.legend.y, 1.10)
            self.assertEqual(fig2.layout.annotations[0].text, "15-Minute Power Dispatch (kW)")
            self.assertEqual(fig2.layout.annotations[1].text, "Battery State of Charge (% and stored kWh)")
            self.assertTrue(fig2.layout.xaxis2.rangeslider.visible)

        forbidden_terms = [
            "double lever",
            "double-lever",
            "hockey-stick",
            "hockey stick",
            "pareto",
            "the perfect generator",
            "zero-breach champion",
            "4-pillar reconciliation",
            "4-pillar equation bar",
        ]
        import ast

        sandbox_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "ui_sandbox", "Combined_sandbox")
        )
        py_files = []
        for dirpath, _, filenames in os.walk(sandbox_dir):
            if "__pycache__" in dirpath:
                continue
            for fn in sorted(filenames):
                if fn.endswith(".py"):
                    py_files.append(os.path.join(dirpath, fn))
        self.assertGreaterEqual(len(py_files), 20)
        for fpath in sorted(py_files):
            rel_name = os.path.relpath(fpath, sandbox_dir)
            with open(fpath, "r", encoding="utf-8") as f:
                src = f.read()
            ast.parse(src, filename=rel_name)
            self.assertLessEqual(
                len(src.splitlines()),
                960,
                f"Module {rel_name} exceeds 960 lines",
            )
            content_lower = src.lower()
            for term in forbidden_terms:
                self.assertNotIn(
                    term,
                    content_lower,
                    f"Forbidden marketing term '{term}' found in {rel_name}",
                )

    def test_csv_upload_parsing(self):
        """Verifies CSV parsing function signatures work without TypeError."""
        from current_model.core.csv_parser import parse_csv_content, detect_suggested_columns

        sample_csv = "timestamp;Total_Demand_kW\n2025-01-01 00:00:00;120,5\n2025-01-01 00:15:00;135,0"
        df = parse_csv_content(sample_csv)
        self.assertEqual(len(df), 2)
        time_cols, power_cols, _ = detect_suggested_columns(df)
        self.assertIn("timestamp", time_cols)
        self.assertIn("Total_Demand_kW", power_cols)

    def test_gps_location_and_symmetrical_architecture(self):
        """Verifies Solar module-style GPS presets and 4-source configuration."""
        from current_model.ui_sandbox.Combined_sandbox.combined_sandbox_engine import (
            SOLAR_SITE_PRESETS,
        )
        from current_model.core.solar_engine import search_locations_open_meteo

        self.assertIn("Amsterdam (Default GPS)", SOLAR_SITE_PRESETS)
        self.assertIn("Germany / Berlin", SOLAR_SITE_PRESETS)
        amsterdam_info = SOLAR_SITE_PRESETS["Amsterdam (Default GPS)"]
        self.assertAlmostEqual(amsterdam_info["latitude"], 52.3676, places=4)
        self.assertAlmostEqual(amsterdam_info["longitude"], 4.9041, places=4)

        cfg = CombinedSystemConfig()
        self.assertTrue(hasattr(cfg, "enable_grid"))
        self.assertTrue(hasattr(cfg, "enable_financials"))
        self.assertFalse(cfg.enable_financials)
        self.assertEqual(cfg.site_preset, "Amsterdam (Default GPS)")
        self.assertAlmostEqual(cfg.latitude, 52.3676, places=4)
        self.assertAlmostEqual(cfg.longitude, 4.9041, places=4)

        self.assertTrue(callable(search_locations_open_meteo))

    def test_quick_sizing_and_share_split(self):
        """Verifies 20/40/60/100% presets and the Battery/Generator split of the overload."""
        from current_model.ui_sandbox.Combined_sandbox.combined_sandbox_engine import (
            derive_quick_sizing,
            compute_overload_reference,
        )

        grid_limit = 180.0
        max_kw, event_kwh = compute_overload_reference(self.load_kw, grid_limit)
        self.assertGreater(max_kw, 0.0)
        self.assertGreater(event_kwh, 0.0)

        for bat in (0.0, 20.0, 40.0, 60.0, 100.0):
            res = derive_quick_sizing(self.load_kw, grid_limit, 40.0, bat, 1000.0)
            self.assertAlmostEqual(res.battery_share_pct + res.generator_share_pct, 100.0)
            self.assertAlmostEqual(
                res.battery_power_kw + res.generator_rated_kw, res.max_overload_kw, delta=0.2
            )

        # 100% Generator removes the overload completely (0.0 hrs remaining)
        res_gen = derive_quick_sizing(self.load_kw, grid_limit, 0.0, 0.0, 1000.0)
        cfg_gen = CombinedSystemConfig(
            grid_limit_kw=grid_limit,
            enable_solar=False,
            enable_battery=False,
            enable_generator=True,
            generator_rated_kw=res_gen.generator_rated_kw,
            generator_min_load_pct=0.0,
        )
        sim_gen = simulate_combined_system_dispatch(
            load_kw=self.load_kw, timestamps=self.timestamps,
            system_cfg=cfg_gen, rules_cfg=InteractionRulesConfig(),
        )
        self.assertAlmostEqual(sim_gen.kpis.remaining_overload_hours, 0.0, places=1)
        self.assertLess(sim_gen.kpis.remaining_overload_kwh, 1.0)

        # 100% Battery removes the overload completely (0.0 hrs remaining)
        res_bat = derive_quick_sizing(self.load_kw, grid_limit, 0.0, 100.0, 1000.0)
        self.assertGreater(res_bat.battery_capacity_kwh, 0.0)
        cfg_bat = CombinedSystemConfig(
            grid_limit_kw=grid_limit,
            enable_solar=False,
            enable_battery=True,
            battery_power_kw=res_bat.battery_power_kw,
            battery_capacity_kwh=res_bat.battery_capacity_kwh,
            enable_generator=False,
        )
        sim_bat = simulate_combined_system_dispatch(
            load_kw=self.load_kw, timestamps=self.timestamps,
            system_cfg=cfg_bat,
            rules_cfg=InteractionRulesConfig(
                rule1_peak_priority="battery_first",
                rule2_battery_strategy="peak_shaving_only",
                rule3_charging_sources="solar_and_grid",
            ),
        )
        self.assertAlmostEqual(sim_bat.kpis.remaining_overload_hours, 0.0, places=1)
        self.assertLess(sim_bat.kpis.remaining_overload_kwh, 1.0)

    def test_universal_csv_and_zip_ingestion(self):
        """Verifies universal CSV / ZIP ingestion pipeline."""
        csv_raw_text = (
            "Utility Report: Station 404\n"
            "Interval: 15-Minute\n"
            "Date;Time;Power_Phase1_kWh;Power_Phase2_kWh\n"
            "01.01.2025;00:15;25,5;15,5\n"
            "01.01.2025;00:30;20,0;10,0\n"
            "01.01.2025;00:45;30,0;15,0\n"
            "01.01.2025;01:00;40,0;20,0\n"
        )

        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("subfolder/meter_export_2025.csv", csv_raw_text.encode("latin1"))
        zip_buf.seek(0)

        extracted_files = []
        with zipfile.ZipFile(zip_buf, "r") as z:
            for member in z.namelist():
                if member.endswith(".csv"):
                    raw_b = z.read(member)
                    for enc in ["utf-8-sig", "utf-8", "latin1", "cp1252"]:
                        try:
                            dec = raw_b.decode(enc)
                            extracted_files.append((member, dec))
                            break
                        except Exception:
                            continue

        self.assertEqual(len(extracted_files), 1)
        _, decoded_content = extracted_files[0]

        df_raw = parse_csv_content(decoded_content, skiprows=2)
        df_proc = process_load_profile_data(
            df_raw=df_raw,
            selected_time_cols=["Date", "Time"],
            selected_power_cols=["Power_Phase1_kWh", "Power_Phase2_kWh"],
            selected_unit="kWh (15-min interval) → kW",
            dayfirst=True,
        )
        self.assertAlmostEqual(df_proc["Total_Demand_kW"].iloc[0], 164.0, places=2)

        norm_series, _ = normalize_load_profile_2025(
            raw_df=df_proc,
            power_col="Total_Demand_kW",
            time_col="timestamp",
        )
        self.assertIsInstance(norm_series, LoadSeries2025)
        self.assertEqual(len(norm_series.power_kw), 35040)

    @staticmethod
    def _read_combined_ui_source() -> str:
        """Returns concatenated source of app.py and all views/*.py modules for UI contract tests."""
        sandbox_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "ui_sandbox", "Combined_sandbox")
        )
        parts = []
        app_path = os.path.join(sandbox_dir, "app.py")
        with open(app_path, "r", encoding="utf-8") as f:
            parts.append(f.read())
        views_dir = os.path.join(sandbox_dir, "views")
        if os.path.isdir(views_dir):
            for fn in sorted(os.listdir(views_dir)):
                if fn.endswith(".py"):
                    with open(os.path.join(views_dir, fn), "r", encoding="utf-8") as f:
                        parts.append(f.read())
        return "\n".join(parts)

    def test_all_subtab_forms_encapsulated(self):
        """Verifies that all heavy input sections are encapsulated in st.form or st.fragment to eliminate intermediate reruns."""
        code = self._read_combined_ui_source()

        required_forms = [
            'st.form("comb_grid_limit_form")',
            'st.form("comb_ref_scenario_form")',
            'st.form("comb_solar_location_form")',
            'st.form("comb_solar_form")',
            'st.form("comb_battery_form")',
            'st.form("comb_gen_preset_form")',
            'st.form("comb_generator_form")',
            'st.form("comb_rules_form")',
            'st.form("comb_utility_preset_form")',
            'st.form("comb_tariff_inputs_form")',
            'st.form("comb_hardware_costs_form")',
            'st.form("comb_fin_longterm_form")',
        ]
        for form_str in required_forms:
            self.assertIn(
                form_str,
                code,
                f"Required form '{form_str}' missing from Combined_sandbox/app.py",
            )

        # Check fragment wrappers
        self.assertIn("@st.fragment\ndef _render_battery_reference_fragment", code)
        self.assertIn("@st.fragment\ndef _render_generator_reference_fragment", code)
        self.assertIn("@st.fragment\ndef _render_master_dispatch_chart_fragment", code)
        self.assertIn("@st.fragment\ndef _render_monthly_grid_bill_progression_fragment", code)
        self.assertIn("@st.fragment\ndef _render_financial_chart_gallery_fragment", code)
        self.assertIn("@st.fragment\ndef _render_cashflow_table_expander_fragment", code)

    def test_battery_exact_cluster_and_usable_kwh(self):
        """Verifies exact 100% Zero-Overload battery sizing with usable chemical energy and cluster duration."""
        cfg = CombinedSystemConfig(grid_limit_kw=140.0, enable_solar=True, solar_kwp=50.0)
        rules = InteractionRulesConfig()
        dual_bess = compute_dual_battery_sizing(
            load_kw=self.load_kw,
            system_cfg=cfg,
            rules_cfg=rules,
        )
        self.assertGreater(dual_bess.standalone_100_kwh, 0.0)
        self.assertGreater(dual_bess.standalone_usable_kwh, 0.0)
        self.assertGreater(dual_bess.standalone_cluster_duration_hrs, 0.0)
        self.assertGreater(dual_bess.coupled_100_kwh, 0.0)
        self.assertGreater(dual_bess.coupled_usable_kwh, 0.0)
        self.assertGreater(dual_bess.coupled_cluster_duration_hrs, 0.0)
        # Usable energy must be less than or equal to gross capacity
        self.assertLessEqual(dual_bess.standalone_usable_kwh, dual_bess.standalone_100_kwh)
        self.assertLessEqual(dual_bess.coupled_usable_kwh, dual_bess.coupled_100_kwh)
        # 100% capacity should be ceil-rounded
        self.assertEqual(dual_bess.standalone_100_kwh, float(np.ceil(dual_bess.standalone_100_kwh)))
        self.assertEqual(dual_bess.coupled_100_kwh, float(np.ceil(dual_bess.coupled_100_kwh)))

    def test_generator_diagnostic_metrics(self):
        """Verifies generator dual sizing returns energy, runtime, longest continuous run, and recommended fuel tank."""
        cfg = CombinedSystemConfig(grid_limit_kw=180.0, enable_solar=True, solar_kwp=150.0, enable_battery=True)
        rules = InteractionRulesConfig()
        dual_gen = compute_dual_generator_sizing(
            load_kw=self.load_kw,
            timestamps=self.timestamps,
            system_cfg=cfg,
            rules_cfg=rules,
        )
        self.assertGreater(dual_gen.standalone_100_kw, 0.0)
        self.assertGreater(dual_gen.standalone_energy_mwh, 0.0)
        self.assertGreater(dual_gen.standalone_runtime_hours, 0.0)
        self.assertGreater(dual_gen.standalone_longest_run_hours, 0.0)
        self.assertGreater(dual_gen.standalone_fuel_tank_liters, 0.0)
        # Longest run cannot exceed total runtime
        self.assertLessEqual(dual_gen.standalone_longest_run_hours, dual_gen.standalone_runtime_hours)

    def test_utility_tariff_presets_and_avoided_capex(self):
        """Verifies 1-click utility presets and avoided grid upgrade CAPEX offsetting gross CAPEX."""
        from current_model.ui_sandbox.Combined_sandbox.combined_sandbox_engine import (
            apply_utility_tariff_presets,
            get_dso_preset_options,
            get_supplier_preset_options,
            get_metering_preset_options,
        )
        dso_opts = get_dso_preset_options()
        self.assertIn("Enexis Netbeheer B.V.", dso_opts)
        self.assertIn("Liander Netbeheer B.V.", dso_opts)

        fin_cfg = CombinedFinancialConfig()
        apply_utility_tariff_presets(
            dso_choice="Enexis Netbeheer B.V.",
            tier_choice="MS-D (125 t/m 1.500 kW)",
            supp_choice="Vattenfall Zakelijk",
            supp_plan="Vast 1 Jaar (Dubbeltarief HT/NT)",
            meter_choice="Fudura B.V.",
            meter_tier="Kwartierdata Telemetrie MS (Grootverbruik RLM)",
            fin_cfg=fin_cfg,
        )
        self.assertAlmostEqual(fin_cfg.dso_capacity_fee_eur_kw_month, 2.44, places=2)
        self.assertAlmostEqual(fin_cfg.supplier_energy_price_eur_kwh, 0.125, places=3)
        self.assertAlmostEqual(fin_cfg.metering_fixed_fee_eur_month, 75.0, places=1)

        # Test Avoided Grid Upgrade CAPEX offset
        fin_cfg.avoided_grid_upgrade_capex_eur = 50000.0
        fin_cfg.avoided_transformer_rent_eur_month = 500.0
        sys_cfg = CombinedSystemConfig(
            grid_limit_kw=180.0,
            enable_solar=True,
            solar_kwp=100.0,
            enable_battery=True,
            battery_capacity_kwh=200.0,
            battery_power_kw=100.0,
        )
        rules = InteractionRulesConfig()
        sim_res = simulate_combined_system_dispatch(
            load_kw=self.load_kw,
            timestamps=self.timestamps,
            system_cfg=sys_cfg,
            rules_cfg=rules,
        )
        res_fin = evaluate_combined_financials(sim_res, fin_cfg)
        fin_kpis = res_fin.financial_kpis
        self.assertGreater(fin_kpis.gross_capex_eur, 0.0)
        self.assertEqual(fin_kpis.avoided_grid_upgrade_capex_eur, 50000.0)
        self.assertAlmostEqual(
            fin_kpis.total_capex_eur,
            max(0.0, fin_kpis.gross_capex_eur - 50000.0),
            places=1,
        )


    def test_csv_submeter_selection_and_rangeslider_performance(self):
        """Verifies sub-meter aggregation for Total Demand and that range sliders are disabled for 60 FPS scrolling."""
        # 1. Test multi-meter selective aggregation
        df_raw = pd.DataFrame({
            "timestamp": pd.date_range("2025-01-01 00:00", periods=96, freq="15min"),
            "Meter_HVAC_kW": np.full(96, 20.0),
            "Meter_Production_kW": np.full(96, 50.0),
            "Meter_EV_Chargers_kW": np.full(96, 30.0),
            "Meter_Lighting_kW": np.full(96, 10.0),
        })
        # Full selection: 20 + 50 + 30 + 10 = 110 kW
        all_meters = ["Meter_HVAC_kW", "Meter_Production_kW", "Meter_EV_Chargers_kW", "Meter_Lighting_kW"]
        df_raw["Total_Demand_kW"] = df_raw[all_meters].sum(axis=1)
        self.assertAlmostEqual(df_raw["Total_Demand_kW"].iloc[0], 110.0, places=2)

        # Exclude EV chargers: 20 + 50 + 10 = 80 kW
        selected_subset = ["Meter_HVAC_kW", "Meter_Production_kW", "Meter_Lighting_kW"]
        df_raw["Total_Demand_kW"] = df_raw[selected_subset].sum(axis=1)
        self.assertAlmostEqual(df_raw["Total_Demand_kW"].iloc[0], 80.0, places=2)

        # Normalize for 2025 pipeline
        norm_series, _ = normalize_load_profile_2025(raw_df=df_raw, power_col="Total_Demand_kW", time_col="timestamp")
        self.assertAlmostEqual(norm_series.peak_demand_kw, 80.0, places=1)

        # 2. Test Range-Slider configuration matching BESS Sandbox standard (visible on row 2)
        fig_cons = create_consumption_baseline_figure(self.timestamps, self.load_kw)
        self.assertFalse(fig_cons.layout.xaxis.rangeslider.visible)

        sys_cfg = CombinedSystemConfig(enable_battery=True, battery_capacity_kwh=100.0, battery_power_kw=50.0)
        rules = InteractionRulesConfig()
        sim_res = simulate_combined_system_dispatch(
            load_kw=self.load_kw,
            timestamps=self.timestamps,
            system_cfg=sys_cfg,
            rules_cfg=rules,
        )
        fig_master = create_combined_dispatch_soc_figure(sim_res=sim_res, timeframe="7D")
        self.assertTrue(fig_master.layout.xaxis2.rangeslider.visible)

    def test_extreme_scale_bess_unit_sizing_and_no_max_error(self):
        """Verifies scale-aware modular battery sizing and dynamic bounds prevent StreamlitValueAboveMaxError."""
        from current_model.ui_sandbox.Combined_sandbox.combined_sandbox_engine import (
            determine_smart_modular_units,
        )

        # 1. Small C&I tier (<= 500 kWh) -> 50 kWh rack modules
        units_small, kwh_small = determine_smart_modular_units(100.0)
        self.assertEqual(units_small, 2)
        self.assertEqual(kwh_small, 50.0)

        # 2. Medium C&I tier (500 - 2,500 kWh) -> 100 / 250 kWh cabinets
        units_med, kwh_med = determine_smart_modular_units(1000.0)
        self.assertEqual(units_med, 4)
        self.assertEqual(kwh_med, 250.0)

        # 3. Large C&I tier (2,500 - 10,000 kWh) -> 500 kWh blocks
        units_lg, kwh_lg = determine_smart_modular_units(5000.0)
        self.assertEqual(units_lg, 10)
        self.assertEqual(kwh_lg, 500.0)

        # 4. Utility scale (10,000 - 50,000 kWh) -> 1,000 kWh container blocks
        units_util, kwh_util = determine_smart_modular_units(20000.0)
        self.assertEqual(units_util, 20)
        self.assertEqual(kwh_util, 1000.0)

        # 5. Mega scale (> 50,000 kWh) -> 2,500 kWh container units (e.g. 1,265,500 kWh)
        units_mega, kwh_mega = determine_smart_modular_units(1265500.0)
        self.assertEqual(units_mega, 506)
        self.assertAlmostEqual(units_mega * kwh_mega, 1265500.0, delta=1000.0)

        # 6. Verify that hardcoded max_value=200 is gone from Combined_sandbox views/app
        app_code = self._read_combined_ui_source()

        self.assertNotIn(
            'max_value=200,',
            app_code,
            "Hardcoded max_value=200 must be replaced by dynamic max_units",
        )
        self.assertIn("max_units = max(100000, raw_units * 2)", app_code)

        # 7. Verify that hardcoded max_value=100 is gone from BESS_sandbox/view_technical.py
        bess_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "ui_sandbox", "BESS_sandbox", "view_technical.py")
        )
        with open(bess_path, "r", encoding="utf-8") as f:
            bess_code = f.read()

        self.assertNotIn(
            'max_value=100,',
            bess_code,
            "Hardcoded max_value=100 must be replaced by dynamic max_sb_units",
        )
        self.assertIn("max_sb_units = max(100000, init_unit_count * 2)", bess_code)

    def test_standalone_battery_recharge_and_bess_standard_charts(self):
        """Verifies that standalone BESS recharges from grid headroom and chart aligns with BESS sandbox standard."""
        # 1. Standalone Battery (Solar disabled, Generator disabled)
        cfg = CombinedSystemConfig(
            grid_limit_kw=180.0,
            enable_solar=False,
            enable_battery=True,
            battery_capacity_kwh=300.0,
            battery_power_kw=100.0,
            enable_generator=False,
        )
        rules = InteractionRulesConfig(rule3_charging_sources="solar_only")  # Even if default solar_only
        sim_res = simulate_combined_system_dispatch(
            load_kw=self.load_kw,
            timestamps=self.timestamps,
            system_cfg=cfg,
            rules_cfg=rules,
        )

        # Standalone battery MUST recharge from grid headroom
        total_chg_grid_kwh = float(np.sum(sim_res.bess_charge_grid_kw) * 0.25)
        total_dis_kwh = float(np.sum(sim_res.bess_discharge_kw) * 0.25)
        self.assertGreater(total_chg_grid_kwh, 0.0, "Standalone battery must recharge from grid headroom")
        self.assertGreater(total_dis_kwh, 0.0, "Standalone battery must actively discharge for peak shaving")
        self.assertGreater(float(np.max(sim_res.bess_soc_pct)), 80.0, "Battery must reach recharge state")

        # 2. Master Dispatch Figure structure (BESS Sandbox 2-in-1 standard)
        fig = create_combined_dispatch_soc_figure(sim_res=sim_res, timeframe="7D")
        trace_names = [t.name for t in fig.data]

        self.assertIn("Facility Load (kW)", trace_names)
        self.assertIn("Grid Import (kW)", trace_names)
        self.assertIn("BESS Discharge (kW)", trace_names)
        self.assertIn("BESS Charge (kW, shown negative)", trace_names)
        self.assertIn("SoC (%)", trace_names)
        self.assertIn("Stored Energy (kWh)", trace_names)
        if float(np.max(sim_res.unmet_overload_kw)) > 0.05:
            self.assertIn("Grid Excess (kW)", trace_names)
            self.assertNotIn("Remaining Deficit (kW)", trace_names)

        # Verify dual Y-axes on lower subplot
        self.assertIsNotNone(fig.layout.yaxis2)
        self.assertEqual(fig.layout.yaxis2.title.text, "SoC (%)")
        self.assertIsNotNone(fig.layout.yaxis3)
        self.assertEqual(fig.layout.yaxis3.title.text, "Stored (kWh)")

        # Verify ENGINE_VERSION is 13.7 and WebGL trace Y-arrays use float32
        self.assertEqual(ENGINE_VERSION, "13.7")
        for trace in fig.data:
            if hasattr(trace, "y") and isinstance(trace.y, np.ndarray):
                self.assertEqual(trace.y.dtype, np.float32)

    def test_data_gap_normalization_and_preservation(self):
        """Verifies that measurement interruptions (> 1 hour) are flagged in is_gap and not linearly interpolated."""
        # Create 15-min intervals with a 20-day gap: Jan 1 to Feb 5, then Feb 26 to Dec 31
        part1 = pd.date_range("2025-01-01 00:00:00", "2025-02-05 23:45:00", freq="15min")
        part2 = pd.date_range("2025-02-26 00:00:00", "2025-12-31 23:45:00", freq="15min")
        full_ts = part1.append(part2)
        power_vals = np.full(len(full_ts), 200.0, dtype=float)

        raw_df = pd.DataFrame({"timestamp": full_ts, "Total_Demand_kW": power_vals})
        norm_series, diag = normalize_load_profile_2025(raw_df=raw_df, power_col="Total_Demand_kW", time_col="timestamp")

        self.assertIsInstance(norm_series, LoadSeries2025)
        self.assertEqual(len(norm_series.power_kw), 35040)
        self.assertIsNotNone(norm_series.is_gap)
        self.assertTrue(np.any(norm_series.is_gap))

        # Check that gap intervals between Feb 6 and Feb 25 are flagged and zeroed
        gap_mask = (norm_series.timestamps > pd.Timestamp("2025-02-05 23:45:00")) & (norm_series.timestamps < pd.Timestamp("2025-02-26 00:00:00"))
        self.assertTrue(np.all(norm_series.is_gap[gap_mask]))
        self.assertTrue(np.all(norm_series.power_kw[gap_mask] == 0.0))

        # Expected energy should equal measured energy without phantom addition
        expected_kwh = float(len(full_ts) * 200.0 * 0.25)
        self.assertAlmostEqual(norm_series.total_energy_kwh, expected_kwh, delta=50.0)
        self.assertGreater(diag["gap_intervals_count"], 0)

    def test_simulation_dispatch_with_data_gap(self):
        """Verifies that dispatch engine freezes battery SoC across gaps and produces 0 false overload."""
        part1 = pd.date_range("2025-01-01 00:00:00", "2025-02-05 23:45:00", freq="15min")
        part2 = pd.date_range("2025-02-26 00:00:00", "2025-12-31 23:45:00", freq="15min")
        full_ts = part1.append(part2)
        power_vals = np.full(len(full_ts), 250.0, dtype=float)

        raw_df = pd.DataFrame({"timestamp": full_ts, "Total_Demand_kW": power_vals})
        norm_series, _ = normalize_load_profile_2025(raw_df=raw_df, power_col="Total_Demand_kW", time_col="timestamp")

        cfg = CombinedSystemConfig(
            grid_limit_kw=150.0,
            enable_solar=False,
            enable_battery=True,
            battery_capacity_kwh=300.0,
            battery_power_kw=150.0,
            enable_generator=False,
        )
        rules = InteractionRulesConfig(rule2_battery_strategy="peak_shaving_only")

        sim_res = simulate_combined_system_dispatch(
            load_kw=norm_series.power_kw,
            timestamps=norm_series.timestamps,
            system_cfg=cfg,
            rules_cfg=rules,
            is_gap=norm_series.is_gap,
        )

        gap_mask = norm_series.is_gap
        # During gap intervals: BESS discharge must be 0, grid import must be 0, unmet overload must be 0
        self.assertTrue(np.all(sim_res.bess_discharge_kw[gap_mask] == 0.0))
        self.assertTrue(np.all(sim_res.grid_import_kw[gap_mask] == 0.0))
        self.assertTrue(np.all(sim_res.unmet_overload_kw[gap_mask] == 0.0))

        # Battery SoC must be frozen during gap (all gap intervals equal the same energy)
        gap_soc = sim_res.bess_energy_kwh[gap_mask]
        self.assertAlmostEqual(float(np.min(gap_soc)), float(np.max(gap_soc)), delta=1e-3)

        # Plotly chart must have NaNs in traces across gap intervals
        fig = create_combined_dispatch_soc_figure(sim_res=sim_res, timeframe="Full Year")
        for trace in fig.data:
            if hasattr(trace, "y") and isinstance(trace.y, np.ndarray) and len(trace.y) == 35040:
                self.assertTrue(np.any(np.isnan(trace.y)), f"Trace '{trace.name}' should have NaNs during gaps")

    def test_financial_subledger_itemization_and_monthly_progression(self):
        """Verify itemized 4-Pillar bill sub-ledger, hardware breakdown, savings split, and 12-month progression chart."""
        cfg = CombinedSystemConfig(
            enable_solar=True,
            solar_sizing_method="direct_kwp",
            solar_kwp=200.0,
            enable_battery=True,
            battery_capacity_kwh=200.0,
            battery_power_kw=100.0,
            enable_generator=True,
            generator_rated_kw=100.0,
            grid_limit_kw=180.0,
        )
        sim_res = simulate_combined_system_dispatch(
            self.load_kw, self.timestamps, cfg, InteractionRulesConfig()
        )
        fin_cfg = CombinedFinancialConfig()
        evaluate_combined_financials(sim_res, fin_cfg)

        kpi = sim_res.financial_kpis
        self.assertIsNotNone(kpi)

        # 1. Itemized Pillar 1..4 bill sums reconcile with totals
        base_sum = (
            kpi.baseline_supply_energy_eur
            + kpi.baseline_supply_fixed_eur
            + kpi.baseline_dso_fixed_eur
            + kpi.baseline_dso_capacity_eur
            + kpi.baseline_dso_peak_eur
            + kpi.baseline_dso_transport_eur
            + kpi.baseline_dso_transformer_rent_eur
            + kpi.baseline_penalty_cost_eur
            + kpi.baseline_pillar3_metering_eur
            + kpi.baseline_energy_tax_eur
            + kpi.baseline_tax_surcharge_eur
        )
        comb_sum = (
            kpi.combined_supply_energy_eur
            + kpi.combined_supply_fixed_eur
            + kpi.combined_dso_fixed_eur
            + kpi.combined_dso_capacity_eur
            + kpi.combined_dso_peak_eur
            + kpi.combined_dso_transport_eur
            + kpi.combined_dso_transformer_rent_eur
            + kpi.combined_grid_penalty_cost_eur
            + kpi.combined_pillar3_metering_eur
            + kpi.combined_energy_tax_eur
            + kpi.combined_tax_surcharge_eur
        )
        self.assertAlmostEqual(base_sum, kpi.baseline_total_opex_eur, delta=1.0)
        self.assertAlmostEqual(comb_sum, kpi.combined_grid_total_eur, delta=1.0)

        # 2. Hardware CAPEX line items sum to total solar / battery CAPEX
        self.assertAlmostEqual(
            kpi.solar_modules_capex_eur + kpi.solar_inverter_capex_eur + kpi.solar_mounting_capex_eur,
            kpi.solar_capex_eur,
            delta=1.0,
        )
        self.assertAlmostEqual(
            kpi.battery_rack_capex_eur + kpi.battery_inverter_capex_eur + kpi.battery_bop_capex_eur,
            kpi.battery_capex_eur,
            delta=1.0,
        )

        # 3. Year-1 bill savings split reconciles with gross bill reduction
        expected_bill_savings = kpi.baseline_total_opex_eur - kpi.combined_grid_total_eur
        self.assertAlmostEqual(
            kpi.grid_volume_savings_y1_eur + kpi.grid_peak_and_penalty_savings_y1_eur,
            expected_bill_savings,
            delta=1.0,
        )
        self.assertGreater(kpi.variable_grid_rate_eur_kwh, 0.0)
        self.assertGreaterEqual(kpi.solar_direct_value_y1_eur, 0.0)
        self.assertGreaterEqual(kpi.solar_stored_value_y1_eur, 0.0)

        # 4. Monthly progression columns and chart modes
        df_m = sim_res.monthly_cost_df
        expected_cols = [
            "Current situation Peak (kW)",
            "Combined Grid Peak (kW)",
            "Combined Grid Import (kWh)",
            "Combined Standing & Metering (€)",
            "Combined Booked Capacity (€)",
            "Combined Peak Demand Fee (€)",
            "Combined DSO Transport (€)",
            "Combined DSO Total (€)",
            "Current situation DSO Total (€)",
            "Combined Supply & Tax (€)",
            "Current situation Supply & Tax (€)",
        ]
        for col in expected_cols:
            self.assertIn(col, df_m.columns, f"Missing monthly column '{col}'")
        self.assertEqual(len(df_m), 12)

        for mode in ["Combined System Bill", "Current Situation Bill", "Monthly Bill Comparison"]:
            fig_m = create_monthly_grid_bill_progression_figure(sim_res, view_mode=mode)
            self.assertGreaterEqual(len(fig_m.data), 2)

    def test_battery_quick_size_preserves_power_and_coupled_calibration(self):
        rules_default = InteractionRulesConfig()
        self.assertEqual(rules_default.rule3_charging_sources, "solar_and_grid")

        cfg = CombinedSystemConfig(
            enable_grid=True,
            grid_limit_kw=180.0,
            enable_solar=True,
            solar_sizing_method="target_share_pct",
            target_consumption_share_pct=60.0,
            enable_battery=True,
            enable_generator=False,
        )
        dual = compute_dual_battery_sizing(self.load_kw, cfg, rules_default)
        self.assertGreater(dual.standalone_100_kw, 0.0)
        self.assertEqual(dual.standalone_80_kw, dual.standalone_100_kw)
        self.assertEqual(dual.standalone_50_kw, dual.standalone_100_kw)
        self.assertEqual(dual.coupled_80_kw, dual.coupled_100_kw)
        self.assertEqual(dual.coupled_50_kw, dual.coupled_100_kw)
        self.assertLess(dual.standalone_80_kwh, dual.standalone_100_kwh)

        cfg.battery_power_kw = dual.coupled_100_kw
        cfg.battery_capacity_kwh = dual.coupled_100_kwh
        sim_zero = simulate_combined_system_dispatch(
            self.load_kw, self.timestamps, cfg, rules_default
        )
        self.assertTrue(sim_zero.kpis.grid_limit_met)
        self.assertAlmostEqual(sim_zero.kpis.remaining_overload_kwh, 0.0, places=1)

    def test_coordinated_mix_sizing_hybrid_and_strategies(self):
        cfg = CombinedSystemConfig(
            enable_grid=True,
            grid_limit_kw=180.0,
            enable_solar=True,
            target_consumption_share_pct=60.0,
        )
        rules = InteractionRulesConfig()

        pure_bess = compute_coordinated_mix_sizing(
            load_kw=self.load_kw,
            system_cfg=cfg,
            rules_cfg=rules,
            strategy_key="pure_battery_100",
            target_grid_limit_kw=180.0,
            solar_share_pct=60.0,
        )
        hybrid_2h = compute_coordinated_mix_sizing(
            load_kw=self.load_kw,
            system_cfg=cfg,
            rules_cfg=rules,
            strategy_key="hybrid_2h",
            target_grid_limit_kw=180.0,
            solar_share_pct=60.0,
            bess_duration_hours=2.0,
            gen_cover_remaining_peaks=True,
        )
        pure_gen = compute_coordinated_mix_sizing(
            load_kw=self.load_kw,
            system_cfg=cfg,
            rules_cfg=rules,
            strategy_key="pure_generator_100",
            target_grid_limit_kw=180.0,
            solar_share_pct=60.0,
        )

        self.assertTrue(pure_bess.battery_enabled)
        self.assertFalse(pure_bess.generator_enabled)
        self.assertLessEqual(pure_bess.est_unmet_overload_hrs, 0.1)

        self.assertTrue(hybrid_2h.battery_enabled)
        self.assertLessEqual(hybrid_2h.est_unmet_overload_hrs, 0.1)
        self.assertLessEqual(hybrid_2h.battery_capacity_kwh, pure_bess.battery_capacity_kwh)

        self.assertFalse(pure_gen.battery_enabled)
        self.assertTrue(pure_gen.generator_enabled)
        self.assertLessEqual(pure_gen.est_unmet_overload_hrs, 0.1)
        self.assertIn("hybrid_2h", MIX_STRATEGY_OPTIONS)

    def test_solar_potential_trace_and_webgl_gap_masking(self):
        arr = np.array([10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0], dtype=float)
        gap_b = np.array([False, True, True, True, True, True, False, False], dtype=bool)
        masked = _mask_gap_for_webgl_fill(arr, gap_b)
        self.assertEqual(float(masked[0]), 10.0)
        self.assertEqual(float(masked[1]), 0.0)
        self.assertTrue(np.all(np.isnan(masked[2:5])))
        self.assertEqual(float(masked[5]), 0.0)
        self.assertEqual(float(masked[6]), 70.0)

        cfg = CombinedSystemConfig(enable_grid=True, grid_limit_kw=180.0, enable_solar=True)
        sim_res = simulate_combined_system_dispatch(
            self.load_kw, self.timestamps, cfg, InteractionRulesConfig()
        )
        fig = create_combined_dispatch_soc_figure(sim_res)
        trace_by_name = {t.name: t for t in fig.data}
        self.assertIn("Solar Total Potential (kW)", trace_by_name)
        self.assertEqual(trace_by_name["Solar Total Potential (kW)"].visible, "legendonly")

    def test_solar_explanation_and_system_mix_form_present(self):
        app_src = self._read_combined_ui_source()

        self.assertIn('st.form("comb_system_mix_form")', app_src)
        self.assertIn('st.form("comb_rules_form")', app_src)
        self.assertIn("How Solar Sizing & Weather Data Work", app_src)
        self.assertIn("Location Map & Pin Selection", app_src)
        self.assertIn("Latitude (°N)", app_src)
        self.assertIn("Longitude (°E)", app_src)
        self.assertIn("5. System Mix & Rules", app_src)

    def test_supply_mix_utilization_diagnostics_and_charts(self):
        cfg = CombinedSystemConfig(
            enable_grid=True,
            grid_limit_kw=180.0,
            enable_solar=True,
            solar_sizing_method="target_share_pct",
            target_consumption_share_pct=60.0,
            enable_battery=True,
            battery_capacity_kwh=5000.0,
            battery_power_kw=300.0,
            enable_generator=True,
            generator_rated_kw=200.0,
        )
        rules = InteractionRulesConfig()
        sim_res = simulate_combined_system_dispatch(
            self.load_kw, self.timestamps, cfg, rules
        )
        diag = compute_system_utilization_diagnostics(sim_res)
        self.assertIsInstance(diag, SystemUtilizationDiagnostics)

        share_sum = (
            diag.grid_direct_pct
            + diag.solar_direct_pct
            + diag.battery_discharge_pct
            + diag.generator_direct_pct
        )
        self.assertAlmostEqual(share_sum, 100.0, delta=0.5)
        self.assertAlmostEqual(
            diag.bess_max_depth_used_kwh + diag.bess_unused_usable_kwh,
            diag.bess_usable_window_kwh,
            delta=0.2,
        )
        self.assertGreaterEqual(diag.bess_capacity_utilization_pct, 0.0)
        self.assertLessEqual(diag.bess_capacity_utilization_pct, 100.0)
        self.assertGreater(diag.bess_right_sized_kwh, 0.0)
        self.assertLessEqual(diag.bess_right_sized_kwh, diag.bess_installed_kwh)
        self.assertLess(diag.bess_right_sized_kwh, diag.bess_installed_kwh)

        fig_pie = create_supply_mix_pie_figure(diag)
        self.assertGreaterEqual(len(fig_pie.data), 1)
        fig_bars = create_component_utilization_bars_figure(diag)
        self.assertEqual(len(fig_bars.data), 2)
        bar_labels = list(fig_bars.data[0].y)
        self.assertIn("Battery Capacity (kWh)", bar_labels)
        self.assertNotIn("Battery Power (kW)", bar_labels)

        app_src = self._read_combined_ui_source()

        self.assertIn("def render_supply_mix_and_utilization_overview(", app_src)
        self.assertIn("create_supply_mix_pie_figure", app_src)
        self.assertIn("create_component_utilization_bars_figure", app_src)
        self.assertIn("Trim Unused Battery Capacity", app_src)
        self.assertIn('st.form("comb_system_mix_form")', app_src)
        self.assertIn('st.form("comb_rules_form")', app_src)

    def test_classic_4pillar_bill_congestion_and_isolated_deep_dives(self):
        """Verifies TOU HT/NT, DSO connection split & breach step-up, tax credit, VAT, congestion lock, and isolated charts."""
        sys_cfg = CombinedSystemConfig(
            grid_limit_kw=160.0,
            enable_solar=True,
            solar_sizing_method="direct_kwp",
            solar_kwp=200.0,
            enable_battery=True,
            battery_capacity_kwh=250.0,
            battery_power_kw=100.0,
            enable_generator=True,
            generator_rated_kw=100.0,
            enable_financials=True,
        )
        rules_cfg = InteractionRulesConfig()
        res = simulate_combined_system_dispatch(
            self.load_kw, self.timestamps, sys_cfg, rules_cfg
        )

        fin_tou = CombinedFinancialConfig(
            supplier_pricing_mode="dual_tou",
            supplier_peak_ht_eur_kwh=0.16,
            supplier_offpeak_nt_eur_kwh=0.10,
            supplier_gvo_surcharge_eur_kwh=0.005,
            dso_connection_fee_eur_month=120.0,
            dso_fixed_fee_eur_month=90.0,
            dso_adjust_capacity_on_breach=True,
            annual_tax_reduction_credit_eur=600.0,
            vat_rate_pct=21.0,
            avoided_grid_upgrade_capex_eur=50000.0,
            strict_grid_congestion_mode=False,
        )
        evaluate_combined_financials(res, fin_tou)
        fk = res.financial_kpis
        self.assertIsNotNone(fk)
        self.assertGreater(fk.baseline_supply_peak_ht_eur, 0.0)
        self.assertGreater(fk.baseline_supply_offpeak_nt_eur, 0.0)
        self.assertGreater(fk.combined_supply_gvo_eur, 0.0)
        self.assertAlmostEqual(fk.baseline_dso_connection_eur, 1440.0, places=2)
        self.assertAlmostEqual(fk.baseline_dso_transport_fixed_eur, 1080.0, places=2)
        self.assertGreater(fk.baseline_dso_breach_months, 0)
        self.assertAlmostEqual(fk.baseline_tax_credit_eur, 600.0, places=2)
        self.assertLess(res.tax_monthly_df["Tax Credit (-€)"].sum(), 0.0)
        self.assertGreater(fk.baseline_total_gross_eur, fk.baseline_total_opex_eur)
        self.assertEqual(fk.avoided_grid_upgrade_capex_eur, 50000.0)
        self.assertGreater(fk.dso_savings_eur, 0.0)

        for df_attr in (
            "dso_monthly_df",
            "supplier_monthly_df",
            "tax_monthly_df",
            "solar_fin_monthly_df",
            "battery_fin_monthly_df",
            "generator_fin_monthly_df",
        ):
            df_iso = getattr(res, df_attr)
            self.assertEqual(len(df_iso), 12, f"Expected 12 rows in {df_attr}")

        for fig_builder in (
            create_dso_isolated_breakdown_figure,
            create_supplier_isolated_breakdown_figure,
            create_tax_isolated_breakdown_figure,
            create_solar_isolated_financial_figure,
            create_battery_isolated_financial_figure,
            create_generator_isolated_financial_figure,
        ):
            fig = fig_builder(res)
            self.assertGreaterEqual(len(fig.data), 2)

        # Strict Grid Congestion Lock zeroes avoided upgrade credit
        fin_strict = CombinedFinancialConfig(
            strict_grid_congestion_mode=True,
            avoided_grid_upgrade_capex_eur=50000.0,
        )
        evaluate_combined_financials(res, fin_strict)
        self.assertEqual(res.financial_kpis.avoided_grid_upgrade_capex_eur, 0.0)

        # Verify compliant vs non-compliant congestion states
        breach_cfg = CombinedSystemConfig(
            grid_limit_kw=120.0,
            battery_power_kw=30.0,
            generator_rated_kw=20.0,
            enable_financials=True,
        )
        res_breach = simulate_combined_system_dispatch(self.load_kw, self.timestamps, breach_cfg, rules_cfg)
        evaluate_combined_financials(res_breach, fin_strict)
        self.assertFalse(res_breach.financial_kpis.grid_congestion_compliant)
        self.assertGreater(res_breach.financial_kpis.grid_congestion_breach_kw, 0.0)

        ok_cfg = CombinedSystemConfig(grid_limit_kw=300.0, enable_financials=True)
        res_ok = simulate_combined_system_dispatch(self.load_kw, self.timestamps, ok_cfg, rules_cfg)
        evaluate_combined_financials(res_ok, fin_strict)
        self.assertTrue(res_ok.financial_kpis.grid_congestion_compliant)
        self.assertEqual(res_ok.financial_kpis.grid_congestion_breach_kw, 0.0)

        app_src = self._read_combined_ui_source()
        for expected in (
            "def _render_isolated_pillar_deep_dive_fragment(",
            "def _render_isolated_component_economics_fragment(",
            "def _render_subtab6_supply_mix_bridge_fragment(",
            "Strict Grid Congestion Lock: No Grid Upgrade or Contract Breach Allowed",
            "Grid Operator Contract Only (DSO)",
            "Dual TOU Rate (Peak HT / Off-Peak NT)",
            "Annual Tax Credit",
        ):
            self.assertIn(expected, app_src)
        for dutch_term in (
            "Aansluitdienst",
            "Vastrecht",
            "Heffingskorting",
            "Vermindering",
            "Dubbeltarief",
            "Grootverbruik",
            "Garantie van Oorsprong",
        ):
            self.assertNotIn(dutch_term, app_src)

        self.assertNotIn("generator_maint_cost_eur", app_src)
        self.assertIn("fk.generator_maintenance_cost_eur", app_src)

        import re
        from current_model.ui_sandbox.Combined_sandbox.combined_sandbox_engine import CombinedFinancialKPIs

        valid_fk_fields = set(CombinedFinancialKPIs().__dict__.keys())
        referenced_fk_fields = set(re.findall(r"\b(?:fk|fin_kpis)\.([a-zA-Z_][a-zA-Z0-9_]*)", app_src))
        self.assertTrue(len(referenced_fk_fields) > 0)
        missing_fk_fields = sorted(referenced_fk_fields - valid_fk_fields)
        self.assertEqual(missing_fk_fields, [], f"Unknown CombinedFinancialKPIs fields referenced in app.py: {missing_fk_fields}")

    def test_edemsa_single_utility_ars_and_currsit_reconciliation(self):
        """Verifies EDEMSA Single-Utility ARS bypass of Energy Supplier/Metering and 1:1 Currentsituation reconciliation."""
        from current_model.ui_sandbox.Combined_sandbox.combined_sandbox_engine import (
            apply_utility_tariff_presets,
            sync_financial_config_from_status_quo,
        )
        from current_model.ui_sandbox.Currentsituation_sandbox.engine.consumption_pipeline import (
            synthesize_edemsa_salentein_load_profile_2025,
        )
        from current_model.ui_sandbox.Currentsituation_sandbox.engine.tariff_defaults_2025 import (
            get_edemsa_salentein_config_2025,
        )
        from current_model.ui_sandbox.Currentsituation_sandbox.engine.status_quo_master import (
            calculate_status_quo_master_2025,
        )

        load_sal = synthesize_edemsa_salentein_load_profile_2025()
        sys_cfg = CombinedSystemConfig(
            grid_limit_kw=430.0,
            enable_solar=False,
            enable_battery=False,
            enable_generator=False,
            enable_financials=True,
        )
        sim_res = simulate_combined_system_dispatch(
            load_kw=load_sal.power_kw,
            timestamps=load_sal.timestamps,
            system_cfg=sys_cfg,
            rules_cfg=InteractionRulesConfig(),
        )

        fin_edemsa = CombinedFinancialConfig()
        apply_utility_tariff_presets(
            dso_choice="EDEMSA Mendoza (Single-Utility)",
            tier_choice="T2 RMT (Bodegas Salentein 430 kW)",
            supp_choice="Vattenfall Business",
            supp_plan="Fixed 1-Year (Dual TOU HT/NT)",
            meter_choice="Fudura B.V.",
            meter_tier="15-Min Interval Telemetry MV (Large Consumer)",
            fin_cfg=fin_edemsa,
        )
        self.assertEqual(fin_edemsa.currency_code, "ARS")
        self.assertEqual(fin_edemsa.market_mode, "single_utility")
        self.assertFalse(fin_edemsa.enable_pillar_1_supplier)
        self.assertTrue(fin_edemsa.enable_pillar_2_dso)
        self.assertFalse(fin_edemsa.enable_pillar_3_metering)
        self.assertTrue(fin_edemsa.enable_pillar_4_taxes)
        self.assertTrue(fin_edemsa.dso_enable_three_window_tou)
        self.assertTrue(fin_edemsa.dso_bill_peak_on_pico_only)
        self.assertFalse(fin_edemsa.vat_applies_to_levies)

        evaluate_combined_financials(sim_res, fin_edemsa)
        fk = sim_res.financial_kpis
        self.assertEqual(fk.baseline_pillar1_supply_eur, 0.0)
        self.assertEqual(fk.combined_pillar1_supply_eur, 0.0)
        self.assertEqual(fk.baseline_pillar3_metering_eur, 0.0)
        self.assertGreater(fk.baseline_dso_vol_peak_eur, 0.0)
        self.assertGreater(fk.baseline_dso_vol_offpeak_eur, 0.0)
        self.assertGreater(fk.baseline_dso_vol_shoulder_eur, 0.0)
        self.assertAlmostEqual(fk.baseline_dso_regulatory_adj_eur, 12.0 * 7848661.60, delta=10.0)

        sq_cfg = get_edemsa_salentein_config_2025(contracted_capacity_kw=430.0)
        sq_res = calculate_status_quo_master_2025(load=load_sal, config=sq_cfg)
        self.assertAlmostEqual(fk.baseline_pillar2_dso_eur, sq_res.total_dso_net, delta=50.0)
        self.assertAlmostEqual(fk.baseline_pillar4_taxes_eur, sq_res.total_levies_net, delta=50.0)
        self.assertAlmostEqual(fk.baseline_total_opex_eur, sq_res.total_status_quo_net, delta=50.0)
        self.assertAlmostEqual(fk.baseline_vat_eur, sq_res.total_vat_amount, delta=50.0)
        self.assertAlmostEqual(fk.baseline_total_gross_eur, sq_res.total_status_quo_gross, delta=50.0)

        from current_model.ui_sandbox.Combined_sandbox.combined_charts import create_dso_isolated_breakdown_figure
        fig_dso = create_dso_isolated_breakdown_figure(sim_res)
        dso_stack_traces = [t for t in fig_dso.data if getattr(t, "offsetgroup", None) == "dso_annual_stack"]
        self.assertIn("Regulatory Adjustments", [t.name for t in dso_stack_traces])
        self.assertAlmostEqual(sum(float(t.y[0]) for t in dso_stack_traces), fk.baseline_pillar2_dso_eur, delta=1.0)
        self.assertAlmostEqual(sum(float(t.y[1]) for t in dso_stack_traces), fk.combined_pillar2_dso_eur, delta=1.0)

        # Also test direct StatusQuoConfig2025 -> CombinedFinancialConfig sync helper
        fin_synced = sync_financial_config_from_status_quo(sq_cfg, CombinedFinancialConfig())
        evaluate_combined_financials(sim_res, fin_synced)
        self.assertEqual(sim_res.financial_kpis.baseline_pillar1_supply_eur, 0.0)
        self.assertAlmostEqual(sim_res.financial_kpis.baseline_total_gross_eur, sq_res.total_status_quo_gross, delta=50.0)

        ui_src = self._read_combined_ui_source()
        self.assertIn("Sync Contract from Current Situation", ui_src)
        self.assertIn("Single Utility Company (1 Combined Bill", ui_src)

    def test_bess_generator_switch_and_handoff_zero_overload(self):
        """Verifies Without-Generator default for BESS dual-sizing, With-Generator switch, and clean Battery->Generator handoff."""
        cfg = CombinedSystemConfig(
            enable_grid=True,
            grid_limit_kw=140.0,
            enable_solar=True,
            solar_sizing_method="target_share_pct",
            target_consumption_share_pct=60.0,
            enable_battery=True,
            battery_capacity_kwh=80.0,
            battery_power_kw=150.0,
            enable_generator=True,
            generator_rated_kw=250.0,
        )
        rules = InteractionRulesConfig(
            rule1_peak_priority="battery_first",
            rule2_battery_strategy="peak_shaving_only",
            rule3_charging_sources="solar_and_grid",
        )

        # 1. Default (include_generator_in_coupled=False): Battery sizing ignores Generator
        dual_no_gen = compute_dual_battery_sizing(self.load_kw, cfg, rules)
        self.assertGreater(dual_no_gen.coupled_100_kw, 0.0)
        self.assertGreater(dual_no_gen.coupled_100_kwh, 0.0)

        # 2. Switch ON (include_generator_in_coupled=True): 250 kW Generator absorbs overload
        dual_with_gen = compute_dual_battery_sizing(
            self.load_kw, cfg, rules, include_generator_in_coupled=True
        )
        self.assertEqual(dual_with_gen.coupled_100_kw, 0.0)
        self.assertEqual(dual_with_gen.coupled_100_kwh, 0.0)

        # 3. Partial Battery + Backup Generator handoff leaves exact 0.0 hrs remaining overload
        sim_res = simulate_combined_system_dispatch(self.load_kw, self.timestamps, cfg, rules)
        self.assertTrue(sim_res.kpis.grid_limit_met)
        self.assertEqual(sim_res.kpis.remaining_overload_hours, 0.0)
        self.assertEqual(sim_res.kpis.remaining_overload_kwh, 0.0)
        self.assertGreater(sim_res.kpis.generator_runtime_hours, 0.0)

        # 4. UI switch controls present in Sub-Tab 3
        ui_src = self._read_combined_ui_source()
        self.assertIn("Without Generator (Default)", ui_src)
        self.assertIn("With Generator Backup", ui_src)
        self.assertIn("Include Generator Backup in Limit Check", ui_src)

    def test_hardware_lump_sum_overrides_repowering_split_degradation_and_excel(self):
        """Verifies >0 lump-sum CAPEX/OPEX overrides, repowering override, split degradation, and Excel transparency."""
        cfg = CombinedSystemConfig(
            enable_grid=True,
            grid_limit_kw=160.0,
            enable_solar=True,
            solar_sizing_method="direct_kwp",
            solar_kwp=200.0,
            enable_battery=True,
            battery_capacity_kwh=400.0,
            battery_power_kw=100.0,
            enable_generator=True,
            generator_rated_kw=100.0,
            enable_financials=True,
        )
        rules = InteractionRulesConfig()
        sim_res = simulate_combined_system_dispatch(self.load_kw, self.timestamps, cfg, rules)

        # 1. Lump-sum overrides (>0) replace unit rates without losing underlying unit rate fields
        fin_ov = CombinedFinancialConfig(
            currency_code="USD",
            solar_turnkey_eur_kwp=900.0,
            solar_lump_sum_capex_eur=150000.0,
            solar_lump_sum_om_eur_year=2100.0,
            battery_capex_eur_kwh=280.0,
            battery_lump_sum_capex_eur=120000.0,
            battery_lump_sum_om_eur_year=1800.0,
            enable_battery_augmentation=True,
            battery_augmentation_year=10,
            battery_augmentation_pct_of_racks=50.0,
            generator_lump_sum_capex_eur=35000.0,
            generator_lump_sum_service_opex_eur_year=1200.0,
        )
        evaluate_combined_financials(sim_res, fin_ov)
        fk = sim_res.financial_kpis
        self.assertEqual(fk.solar_capex_eur, 150000.0)
        self.assertEqual(fk.solar_om_eur, 2100.0)
        self.assertEqual(fk.solar_pricing_mode, "Lump-Sum Override")
        self.assertAlmostEqual(fk.solar_implied_eur_kwp, 750.0, delta=5.0)
        self.assertEqual(fk.battery_capex_eur, 120000.0)
        self.assertEqual(fk.battery_om_eur, 1800.0)
        self.assertEqual(fk.battery_pricing_mode, "Lump-Sum Override")
        self.assertAlmostEqual(fk.battery_implied_eur_kwh, 300.0, places=1)
        self.assertAlmostEqual(fk.battery_implied_eur_kw, 1200.0, places=1)
        # Repowering scales on lump-sum BESS (50% of 120,000 = 60,000) and hits Year 10 cashflow
        self.assertEqual(fk.battery_repowering_mode, "% of Lump-Sum CAPEX")
        self.assertAlmostEqual(fk.battery_augmentation_eur, 60000.0, places=1)
        cf10 = sim_res.cashflow_15y_df.loc[sim_res.cashflow_15y_df["Year"] == 10, "Investment & Augmentation (€)"].iloc[0]
        self.assertAlmostEqual(float(cf10), -60000.0, places=1)
        self.assertEqual(fk.generator_capex_eur, 35000.0)
        self.assertAlmostEqual(fk.generator_implied_eur_kw, 350.0, places=1)
        self.assertAlmostEqual(fk.generator_maintenance_cost_eur, 1200.0, places=1)

        # Reset overrides to 0 -> reverts cleanly to preserved unit rates & explicit repowering override works
        fin_ov.solar_lump_sum_capex_eur = 0.0
        fin_ov.battery_lump_sum_capex_eur = 0.0
        fin_ov.battery_augmentation_lump_sum_eur = 45000.0
        evaluate_combined_financials(sim_res, fin_ov)
        self.assertAlmostEqual(sim_res.financial_kpis.solar_capex_eur, 200.0 * 900.0, delta=5000.0)
        self.assertEqual(sim_res.financial_kpis.solar_pricing_mode, "Turnkey Unit Rate")
        self.assertEqual(sim_res.financial_kpis.battery_repowering_mode, "Lump-Sum Override")
        self.assertEqual(sim_res.financial_kpis.battery_augmentation_eur, 45000.0)

        # 2. Split 15-Year Degradation: pure Peak-Shaving scenario (no Solar) degrades far less than full tariff
        cfg_bess_only = CombinedSystemConfig(
            enable_grid=True, grid_limit_kw=160.0, enable_solar=False,
            enable_battery=True, battery_capacity_kwh=500.0, battery_power_kw=150.0,
            enable_financials=True,
        )
        sim_bess = simulate_combined_system_dispatch(self.load_kw, self.timestamps, cfg_bess_only, rules)
        fin_deg = CombinedFinancialConfig(tariff_escalation_pct_pa=0.0, om_inflation_pct_pa=0.0, system_degradation_pct_pa=2.0)
        evaluate_combined_financials(sim_bess, fin_deg)
        yr1_bill = float(sim_bess.cashflow_15y_df.loc[sim_bess.cashflow_15y_df["Year"] == 1, "Combined Grid Bill (€)"].iloc[0])
        yr15_bill = float(sim_bess.cashflow_15y_df.loc[sim_bess.cashflow_15y_df["Year"] == 15, "Combined Grid Bill (€)"].iloc[0])
        # With 0% escalation and stable peak shaving, Combined Grid Bill stays almost unchanged across 15 yrs
        self.assertAlmostEqual(yr15_bill, yr1_bill, delta=max(500.0, yr1_bill * 0.02))

        # 3. Excel Sheet 1 includes Hardware Cost Basis & Implied Unit Benchmarks
        excel_bytes = build_combined_verification_excel_bytes(sim_res)
        wb = openpyxl.load_workbook(io.BytesIO(excel_bytes), read_only=True)
        ws1_rows = list(wb["Summary & KPIs"].iter_rows(values_only=True))
        wb.close()
        ws1_text = "\n".join(str(c) for row in ws1_rows for c in row if c is not None)
        self.assertIn("Hardware Cost Basis", ws1_text)
        self.assertIn("Solar Implied Unit Cost", ws1_text)
        self.assertIn("Battery Repowering Basis", ws1_text)

        # 4. UI Sub-Tab 6.2 structural contracts & dynamic currency (zero hardcoded EUR in Sub-Tab 6.2)
        hw_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "ui_sandbox", "Combined_sandbox", "views", "subtab6_hardware_costs.py")
        )
        with open(hw_path, "r", encoding="utf-8") as f:
            hw_src = f.read()
        self.assertIn("Technical Profile:", hw_src)
        self.assertIn("Lump-Sum CAPEX Override", hw_src)
        self.assertIn("Plan Cell Repowering", hw_src)
        self.assertNotIn("€", hw_src)
        self.assertNotIn("Direct Electricity Saved", hw_src)
        self.assertNotIn("Peak Shaving &amp; Penalty Savings", hw_src)

    def test_zero_start_baseline_example_expander_and_no_radio_warning(self):
        """Verifies zero-load 35,040-step simulation, collapsed Example Profiles (index=None), and clean radio widget."""
        from current_model.ui_sandbox.Combined_sandbox.views.state_and_helpers import _create_empty_load_series_2025

        empty_ls = _create_empty_load_series_2025()
        self.assertEqual(len(empty_ls.power_kw), 35040)
        self.assertEqual(empty_ls.total_energy_kwh, 0.0)
        self.assertEqual(empty_ls.peak_demand_kw, 0.0)

        cfg = CombinedSystemConfig(enable_grid=True, grid_limit_kw=180.0, enable_financials=True)
        sim_zero = simulate_combined_system_dispatch(
            load_kw=empty_ls.power_kw,
            timestamps=empty_ls.timestamps,
            system_cfg=cfg,
            rules_cfg=InteractionRulesConfig(),
        )
        self.assertEqual(sim_zero.kpis.annual_consumption_kwh, 0.0)
        self.assertTrue(sim_zero.kpis.grid_limit_met)
        evaluate_combined_financials(sim_zero, CombinedFinancialConfig())
        self.assertIsNotNone(sim_zero.financial_kpis)

        sub1_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "ui_sandbox", "Combined_sandbox", "views", "subtab1_consumption.py")
        )
        with open(sub1_path, "r", encoding="utf-8") as f:
            sub1_src = f.read()
        self.assertIn('st.expander(":material/dataset: Example Profiles", expanded=False)', sub1_src)
        self.assertIn("index=None,", sub1_src)

        cons_view_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "ui_sandbox", "Currentsituation_sandbox", "consumption", "view.py")
        )
        with open(cons_view_path, "r", encoding="utf-8") as f:
            cons_src = f.read()
        self.assertNotIn("index=default_idx", cons_src)

    def test_generator_rental_active_months_only_option(self):
        """Verifies generator_rental_active_months_only defaults to False (12 mos) and bills only active months when True."""
        cfg = CombinedSystemConfig(
            enable_grid=True,
            grid_limit_kw=220.0,
            enable_solar=False,
            enable_battery=False,
            enable_generator=True,
            generator_rated_kw=100.0,
            enable_financials=True,
        )
        sim_res = simulate_combined_system_dispatch(self.load_kw, self.timestamps, cfg, InteractionRulesConfig())

        # Default: False -> all 12 months charged
        fin_all = CombinedFinancialConfig(
            generator_cost_model="Monthly Rental (OPEX)",
            generator_rental_eur_month=1200.0,
        )
        self.assertFalse(fin_all.generator_rental_active_months_only)
        evaluate_combined_financials(sim_res, fin_all)
        self.assertEqual(sim_res.financial_kpis.generator_capex_eur, 0.0)
        self.assertEqual(sim_res.financial_kpis.generator_pricing_mode, "Monthly Rental (OPEX)")
        self.assertAlmostEqual(sim_res.financial_kpis.generator_rental_cost_eur, 12.0 * 1200.0, places=2)

        # Active months only: True -> only months with runtime > 0 charged
        fin_active = CombinedFinancialConfig(
            generator_cost_model="Monthly Rental (OPEX)",
            generator_rental_eur_month=1200.0,
            generator_rental_active_months_only=True,
        )
        evaluate_combined_financials(sim_res, fin_active)
        gen_df = sim_res.generator_fin_monthly_df
        active_months = int((gen_df["Runtime (hrs)"] > 0.0).sum())
        self.assertGreater(active_months, 0)
        self.assertLess(active_months, 12)
        self.assertAlmostEqual(sim_res.financial_kpis.generator_rental_cost_eur, active_months * 1200.0, places=2)
        self.assertTrue(all(gen_df.loc[gen_df["Runtime (hrs)"] == 0.0, "Rental (€)"] == 0.0))
        self.assertTrue(all(gen_df.loc[gen_df["Runtime (hrs)"] > 0.0, "Rental (€)"] == 1200.0))

    def test_component_wise_ars_scaling_and_dynamic_chart_currency_labels(self):
        """Verifies component-wise EUR->ARS default scaling without double-scaling and ARS labels across all charts."""
        from current_model.ui_sandbox.Combined_sandbox.combined_sandbox_engine import (
            scale_eur_hardware_defaults_to_currency,
        )
        from current_model.ui_sandbox.Combined_sandbox.combined_charts import (
            create_dso_isolated_breakdown_figure,
            create_supplier_isolated_breakdown_figure,
            create_solar_isolated_financial_figure,
            create_battery_isolated_financial_figure,
            create_generator_isolated_financial_figure,
            create_tax_isolated_breakdown_figure,
        )

        # Simulate Battery already customized in ARS while Solar is still at EUR default (850.0)
        fin = CombinedFinancialConfig(
            currency_code="ARS",
            battery_capex_eur_kwh=300000.0,
            battery_capex_eur_kw=150000.0,
            battery_fixed_bop_eur=10000000.0,
        )
        changed = scale_eur_hardware_defaults_to_currency(fin, fx_rate=1100.0)
        self.assertTrue(changed)
        # Solar & Generator scaled once; Battery NOT double-scaled
        self.assertAlmostEqual(fin.solar_turnkey_eur_kwp, 850.0 * 1100.0, places=2)
        self.assertAlmostEqual(fin.solar_modules_eur_wp, 0.45 * 1100.0, places=2)
        self.assertAlmostEqual(fin.battery_capex_eur_kwh, 300000.0, places=2)
        self.assertAlmostEqual(fin.generator_capex_eur, 22000.0 * 1100.0, places=2)
        # Second call is a no-op
        self.assertFalse(scale_eur_hardware_defaults_to_currency(fin, fx_rate=1100.0))

        # All charts use ARS instead of € / EUR
        cfg = CombinedSystemConfig(
            enable_grid=True,
            grid_limit_kw=180.0,
            enable_solar=True,
            solar_sizing_method="direct_kwp",
            solar_kwp=150.0,
            enable_battery=True,
            battery_capacity_kwh=200.0,
            battery_power_kw=100.0,
            enable_generator=True,
            generator_rated_kw=100.0,
            enable_financials=True,
        )
        sim_res = simulate_combined_system_dispatch(self.load_kw, self.timestamps, cfg, InteractionRulesConfig())
        evaluate_combined_financials(sim_res, fin)

        for fig_fn in (
            create_financial_cost_comparison_figure,
            create_financial_tco_trajectory_figure,
            create_financial_waterfall_bridge_figure,
            create_financial_monthly_cashflow_figure,
            create_monthly_grid_bill_progression_figure,
            create_dso_isolated_breakdown_figure,
            create_supplier_isolated_breakdown_figure,
            create_solar_isolated_financial_figure,
            create_battery_isolated_financial_figure,
            create_generator_isolated_financial_figure,
            create_tax_isolated_breakdown_figure,
        ):
            fig = fig_fn(sim_res)
            title_txt = str(fig.layout.title.text or "")
            if title_txt:
                self.assertIn("ARS", title_txt)
                self.assertNotIn("EUR", title_txt)
                self.assertNotIn("€", title_txt)

    def test_solar_bidirectional_sizing_sync_and_summary_expander(self):
        """Verifies two-way sync between Direct Size (kWp) and Share of Consumption (%) and summary table expander."""
        from current_model.ui_sandbox.Combined_sandbox.views.state_and_helpers import (
            compute_synced_solar_pair,
        )

        # Direct kWp -> Share (%)
        kwp1, share1 = compute_synced_solar_pair(
            sizing_method="direct_kwp",
            direct_kwp=300.0,
            target_share_pct=150.0,
            annual_consumption_kwh=2150000.0,
            specific_yield_kwh_per_kwp=2186.0,
            inverter_efficiency_pct=98.0,
        )
        self.assertAlmostEqual(kwp1, 300.0, places=1)
        self.assertAlmostEqual(share1, 30.5, places=1)

        # Share (%) -> Direct kWp
        kwp2, share2 = compute_synced_solar_pair(
            sizing_method="target_share_pct",
            direct_kwp=300.0,
            target_share_pct=50.0,
            annual_consumption_kwh=2000000.0,
            specific_yield_kwh_per_kwp=1000.0,
            inverter_efficiency_pct=98.0,
        )
        self.assertAlmostEqual(kwp2, 1000.0, places=1)
        self.assertAlmostEqual(share2, 50.0, places=1)

        sub2_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "ui_sandbox", "Combined_sandbox", "views", "subtab2_solar.py")
        )
        with open(sub2_path, "r", encoding="utf-8") as f:
            sub2_src = f.read()
        self.assertIn("Your Solar System at a Glance", sub2_src)
        self.assertNotIn("st.info(solar_deriv.formula_text", sub2_src)
        self.assertIn("compute_synced_solar_pair", sub2_src)

        cfg_sol = CombinedSystemConfig(
            grid_limit_kw=180.0,
            enable_solar=True,
            solar_sizing_method="direct_kwp",
            solar_kwp=300.0,
        )
        sim_sol = simulate_combined_system_dispatch(self.load_kw, self.timestamps, cfg_sol, InteractionRulesConfig())
        fig_sol = create_combined_dispatch_soc_figure(sim_sol, timeframe="7D")
        sol_traces = [t for t in fig_sol.data if str(getattr(t, "name", "")).startswith("Inverter Limit (")]
        self.assertEqual(len(sol_traces), 1)
        self.assertEqual(sol_traces[0].y.dtype, np.float32)

        # Unclipped solar potential exceeds the inverter AC limit while actual solar_gen_kw stays capped
        self.assertIsNotNone(sim_sol.solar_potential_kw)
        inv_kw = float(sim_sol.solar_derivation.inverter_ac_kw)
        self.assertGreater(float(np.max(sim_sol.solar_potential_kw)), inv_kw)
        self.assertLessEqual(float(np.max(sim_sol.solar_gen_kw)), inv_kw + 1e-6)
        pot_traces = [t for t in fig_sol.data if getattr(t, "name", "") == "Solar Total Potential (kW)"]
        self.assertEqual(len(pot_traces), 1)
        self.assertGreater(float(np.nanmax(pot_traces[0].y)), inv_kw)

    def test_solar_weather_data_source_specific_year_and_tmy(self):
        """Verifies default solar_weather_mode='single_year' (2025), switching to 'TMY', and fingerprint invalidation."""
        from current_model.ui_sandbox.Combined_sandbox.combined_sandbox_engine import (
            get_unit_solar_generation_profile,
        )
        from current_model.ui_sandbox.Combined_sandbox.views.state_and_helpers import _physical_sys_tuple

        default_cfg = CombinedSystemConfig()
        self.assertEqual(default_cfg.solar_weather_mode, "single_year")
        self.assertEqual(default_cfg.solar_weather_year, 2025)

        tmy_cfg = CombinedSystemConfig(solar_weather_mode="TMY", solar_weather_year=2025)
        self.assertNotEqual(_physical_sys_tuple(default_cfg), _physical_sys_tuple(tmy_cfg))

        _, sy_2025, lbl_2025 = get_unit_solar_generation_profile(
            latitude=52.3676,
            longitude=4.9041,
            weather_mode="single_year",
            selected_year=2025,
        )
        _, sy_tmy, lbl_tmy = get_unit_solar_generation_profile(
            latitude=52.3676,
            longitude=4.9041,
            weather_mode="TMY",
            selected_year=2025,
        )
        self.assertGreater(sy_2025, 500.0)
        self.assertGreater(sy_tmy, 500.0)
        self.assertNotIn("TMY", lbl_2025)
        self.assertIn("TMY", lbl_tmy)

        sub2_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "ui_sandbox", "Combined_sandbox", "views", "subtab2_solar.py")
        )
        with open(sub2_path, "r", encoding="utf-8") as f:
            sub2_src = f.read()
        self.assertIn("Weather Data Source", sub2_src)
        self.assertIn("Specific Year (Solar Data)", sub2_src)
        self.assertIn("Typical Year (PVGIS TMY)", sub2_src)
        self.assertIn("search_locations_open_meteo(clean_q, count=8)", sub2_src)
        self.assertIn("Multiple matching places found", sub2_src)
        self.assertIn("Use Selected Location", sub2_src)
        self.assertNotIn("Quick Sizing Presets (% of Annual Consumption):", sub2_src)

    def test_battery_quick_size_clears_05c_lock_and_clear_table(self):
        """Verifies _apply_bess_quick_size clears 0.5 C lock, Block 1 summary table renders, and Rule 2 banner skips Reserve % for peak_shaving_only."""
        sub3_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "ui_sandbox", "Combined_sandbox", "views", "subtab3_battery.py")
        )
        helpers_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "ui_sandbox", "Combined_sandbox", "views", "state_and_helpers.py")
        )
        with open(sub3_path, "r", encoding="utf-8") as f:
            sub3_src = f.read()
        with open(helpers_path, "r", encoding="utf-8") as f:
            helpers_src = f.read()

        self.assertIn('st.session_state["comb_bess_lock_05c"] = False', helpers_src)
        self.assertIn('st.session_state["comb_bess_lock_05c_box"] = False', helpers_src)
        self.assertIn("comb_pending_bess_widget_sync", sub3_src)
        self.assertIn("Total Battery Size Needed", sub3_src)
        self.assertIn("Longest Peak Period", sub3_src)
        self.assertIn('if cur_rules_ref.rule2_battery_strategy == "self_consumption_reserve"', sub3_src)

    def test_standalone_solar_production_view_and_inverter_clipping(self):
        """Verifies standalone Solar Production KPIs/chart are load-independent, respect explicit Inverter AC Limit symmetrically, and keep distinct colors/lines."""
        from current_model.ui_sandbox.Combined_sandbox.combined_sandbox_engine import (
            derive_solar_sizing_and_formula,
            compute_standalone_solar_production_summary,
        )
        from current_model.ui_sandbox.Combined_sandbox.combined_charts import (
            create_solar_production_figure,
        )

        # Tighten inverter AC limit vs loosen inverter AC limit above 1.18 ratio on 300 kWp
        cfg_tight = CombinedSystemConfig(
            enable_solar=True,
            solar_sizing_method="direct_kwp",
            solar_kwp=300.0,
            inverter_ac_limit_kw=180.0,
        )
        cfg_wide = CombinedSystemConfig(
            enable_solar=True,
            solar_sizing_method="direct_kwp",
            solar_kwp=300.0,
            inverter_ac_limit_kw=280.0,
        )

        deriv_tight_zero_load = derive_solar_sizing_and_formula(
            annual_consumption_kwh=0.0,
            specific_yield_kwh_per_kwp=1000.0,
            sizing_method="direct_kwp",
            direct_kwp=300.0,
            target_share_pct=60.0,
            enable_solar=True,
            inverter_ac_limit_kw=180.0,
        )
        deriv_tight_high_load = derive_solar_sizing_and_formula(
            annual_consumption_kwh=5_000_000.0,
            specific_yield_kwh_per_kwp=1000.0,
            sizing_method="direct_kwp",
            direct_kwp=300.0,
            target_share_pct=60.0,
            enable_solar=True,
            inverter_ac_limit_kw=180.0,
        )

        sum_zero = compute_standalone_solar_production_summary(cfg_tight, deriv_tight_zero_load, n_steps=len(self.timestamps))
        sum_high = compute_standalone_solar_production_summary(cfg_tight, deriv_tight_high_load, n_steps=len(self.timestamps))
        self.assertEqual(sum_zero["production_kwh"], sum_high["production_kwh"])
        self.assertEqual(sum_zero["clipping_loss_kwh"], sum_high["clipping_loss_kwh"])
        self.assertLessEqual(sum_zero["peak_production_kw"], 180.05)
        self.assertGreater(sum_zero["peak_potential_kw"], 180.0)
        self.assertGreater(sum_zero["clipping_loss_kwh"], 0.0)
        self.assertGreater(sum_zero["clipped_hours"], 0.0)

        # Wider explicit inverter limit (280 kW > 300/1.18 = 254.2 kW) raises AC peak above 254.2 kW
        sim_wide = simulate_combined_system_dispatch(self.load_kw, self.timestamps, cfg_wide, InteractionRulesConfig())
        if float(np.max(sim_wide.solar_potential_kw)) > 255.0:
            self.assertGreater(float(np.max(sim_wide.solar_gen_kw)), 255.0)
        self.assertLessEqual(float(np.max(sim_wide.solar_gen_kw)), 280.05)

        # Independent lines & distinct colors in standalone Solar Production chart and Master Dispatch chart
        fig_prod = create_solar_production_figure(
            timestamps=self.timestamps,
            solar_production_kw=sum_zero["solar_production_kw"],
            solar_potential_kw=sum_zero["solar_potential_kw"],
            inverter_ac_kw=sum_zero["inverter_ac_kw"],
        )
        prod_traces = {t.name: t for t in fig_prod.data}
        self.assertIn("Solar Production (kW)", prod_traces)
        self.assertIn("Solar Total Potential (kW)", prod_traces)
        self.assertIn("Inverter Limit (180 kW)", prod_traces)
        self.assertNotEqual(prod_traces["Solar Production (kW)"].line.color, prod_traces["Solar Total Potential (kW)"].line.color)
        self.assertEqual(prod_traces["Solar Total Potential (kW)"].line.dash, "dash")

        sim_tight = simulate_combined_system_dispatch(self.load_kw, self.timestamps, cfg_tight, InteractionRulesConfig())
        fig_master = create_combined_dispatch_soc_figure(sim_tight, timeframe="7D")
        master_traces = {t.name: t for t in fig_master.data}
        self.assertIn("Solar Production (kW)", master_traces)
        self.assertIn("Solar Total Potential (kW)", master_traces)
        self.assertNotEqual(master_traces["Solar Production (kW)"].line.color, master_traces["Solar Total Potential (kW)"].line.color)

        sub2_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "ui_sandbox", "Combined_sandbox", "views", "subtab2_solar.py")
        )
        with open(sub2_path, "r", encoding="utf-8") as f:
            sub2_src = f.read()
        self.assertIn('st.expander("Solar Production"', sub2_src)
        self.assertIn("_render_solar_production_fragment", sub2_src)

    def test_disable_solar_inverter_limit_and_powerflow_color_overrides(self):
        """Verifies disable_solar_inverter_limit makes 100% of solar potential usable and color_overrides updates trace colors."""
        from current_model.ui_sandbox.Combined_sandbox.combined_sandbox_engine import (
            compute_standalone_solar_production_summary,
        )
        from current_model.ui_sandbox.Combined_sandbox.combined_charts import (
            create_solar_production_figure,
        )

        cfg_no_inv = CombinedSystemConfig(
            enable_solar=True,
            solar_sizing_method="direct_kwp",
            solar_kwp=300.0,
            inverter_ac_limit_kw=180.0,
            disable_solar_inverter_limit=True,
        )
        sim_no_inv = simulate_combined_system_dispatch(self.load_kw, self.timestamps, cfg_no_inv, InteractionRulesConfig())
        self.assertEqual(sim_no_inv.solar_derivation.inverter_ac_kw, 0.0)
        np.testing.assert_allclose(sim_no_inv.solar_gen_kw, sim_no_inv.solar_potential_kw, rtol=1e-6, atol=1e-6)

        summary_no_inv = compute_standalone_solar_production_summary(
            cfg_no_inv, sim_no_inv.solar_derivation, n_steps=len(self.timestamps)
        )
        self.assertEqual(summary_no_inv["clipping_loss_kwh"], 0.0)
        self.assertEqual(summary_no_inv["captured_pct"], 100.0)

        custom_colors = {
            "facility_load": "#112233",
            "grid_import": "#223344",
            "solar_direct": "#334455",
            "solar_production": "#445566",
            "solar_potential": "#556677",
        }
        fig_m = create_combined_dispatch_soc_figure(sim_no_inv, timeframe="7D", color_overrides=custom_colors)
        m_traces = {t.name: t for t in fig_m.data}
        self.assertEqual(m_traces["Facility Load (kW)"].line.color, "#112233")
        self.assertEqual(m_traces["Grid Import (kW)"].line.color, "#223344")
        self.assertEqual(m_traces["Solar Direct (kW)"].line.color, "#334455")
        self.assertEqual(m_traces["Solar Production (kW)"].line.color, "#445566")
        self.assertEqual(m_traces["Solar Total Potential (kW)"].line.color, "#556677")
        self.assertFalse(any(str(t.name).startswith("Inverter Limit (") for t in fig_m.data))

        fig_p = create_solar_production_figure(
            timestamps=self.timestamps,
            solar_production_kw=summary_no_inv["solar_production_kw"],
            solar_potential_kw=summary_no_inv["solar_potential_kw"],
            inverter_ac_kw=summary_no_inv["inverter_ac_kw"],
            color_overrides=custom_colors,
        )
        p_traces = {t.name: t for t in fig_p.data}
        self.assertEqual(p_traces["Solar Production (kW)"].line.color, "#445566")
        self.assertEqual(p_traces["Solar Total Potential (kW)"].line.color, "#556677")
        self.assertFalse(any(str(t.name).startswith("Inverter Limit (") for t in fig_p.data))

    def test_lazy_financials_snapshot_capture(self):
        """Verifies capture_scenario_snapshot populates full financials and utilization without mutating live sim_res or storing 35,040-step arrays."""
        from current_model.ui_sandbox.Combined_sandbox.combined_sandbox_engine import (
            CombinedScenarioSnapshot,
            build_load_fingerprint_from_series,
            capture_scenario_snapshot,
        )

        cfg = CombinedSystemConfig(
            grid_limit_kw=180.0,
            enable_solar=True,
            solar_kwp=120.0,
            enable_battery=True,
            battery_capacity_kwh=200.0,
            battery_power_kw=100.0,
            enable_generator=False,
            enable_financials=False,
        )
        rules = InteractionRulesConfig()
        sim_res = simulate_combined_system_dispatch(self.load_kw, self.timestamps, cfg, rules)
        self.assertIsNone(sim_res.financial_kpis)

        fin_cfg = CombinedFinancialConfig(currency_code="EUR", solar_turnkey_eur_kwp=900.0)
        load_fp = build_load_fingerprint_from_series(self.load_series)
        snap = capture_scenario_snapshot(
            sim_res=sim_res,
            fin_cfg=fin_cfg,
            slot_id="A",
            custom_name="Lazy Financials Check",
            load_fp=load_fp,
        )

        self.assertIsInstance(snap, CombinedScenarioSnapshot)
        # Live sim_res must remain untouched (Lazy Financials preserved)
        self.assertIsNone(sim_res.financial_kpis)
        self.assertTrue(sim_res.cashflow_15y_df.empty)
        # Snapshot must have complete 4-Pillar, 15-Year TCO, and Utilization metrics
        self.assertIsNotNone(snap.financial_kpis)
        self.assertGreater(snap.financial_kpis.total_capex_eur, 0.0)
        self.assertGreater(snap.financial_kpis.tco_15y_baseline_eur, 0.0)
        self.assertEqual(len(snap.cashflow_15y_df), 16)
        self.assertEqual(len(snap.monthly_cost_df), 12)
        self.assertEqual(len(snap.monthly_balance_df), 12)
        self.assertIsInstance(snap.utilization_diagnostics, SystemUtilizationDiagnostics)
        # Lightweight check: snapshot only stores compact np.float32 vectors (zero float64 dispatch arrays)
        allowed_f32_arrays = {"grid_import_kw_f32", "bess_soc_pct_f32", "unmet_overload_kw_f32"}
        total_array_bytes = 0
        for attr_name, attr_val in snap.__dict__.items():
            if isinstance(attr_val, np.ndarray):
                self.assertIn(attr_name, allowed_f32_arrays)
                self.assertEqual(attr_val.dtype, np.float32)
                total_array_bytes += int(attr_val.nbytes)
        if snap.dispatch_f32_dict is not None:
            for d_arr in snap.dispatch_f32_dict.values():
                self.assertEqual(d_arr.dtype, np.float32)
                total_array_bytes += int(d_arr.nbytes)
        self.assertLessEqual(total_array_bytes, 1_500_000)

    def test_zero_simulation_overhead_comparison(self):
        """Verifies Quick-Generate A/B pair, 5 segmented tables, snapshot_to_sim_view, sync_side_by_side_yaxis, and all comparison/single-scenario charts run with zero dispatch calls."""
        import copy
        import time
        import unittest.mock as mock
        from current_model.ui_sandbox.Combined_sandbox.combined_sandbox_engine import (
            generate_quick_ab_preset_snapshots,
            build_ab_comparison_matrix_df,
            build_multi_scenario_leaderboard_df,
            normalize_scenario_list,
            SCENARIO_COMPARISON_PALETTE,
            compute_snapshot_bwl_extensions,
            compute_incremental_bwl_evaluation,
            build_segmented_comparison_tables,
            snapshot_to_sim_view,
        )
        from current_model.ui_sandbox.Combined_sandbox.combined_charts import (
            create_supply_mix_pie_figure,
            create_component_utilization_bars_figure,
            create_combined_dispatch_soc_figure,
            create_financial_tco_trajectory_figure,
            create_financial_waterfall_bridge_figure,
            create_financial_monthly_cashflow_figure,
            create_ab_15y_tco_comparison_figure,
            create_ab_annual_cost_stack_figure,
            create_ab_supply_and_utilization_figure,
            create_ab_monthly_peak_and_grid_import_figure,
            create_ab_energy_flow_balance_figure,
            create_ab_capex_vs_opex_shift_figure,
            create_ab_load_profile_overlay_figure,
            sync_side_by_side_yaxis,
        )

        base_cfg = CombinedSystemConfig(
            grid_limit_kw=180.0,
            enable_solar=True,
            solar_sizing_method="target_share_pct",
            target_consumption_share_pct=60.0,
            enable_battery=False,
            enable_generator=False,
            enable_financials=True,
        )
        base_rules = InteractionRulesConfig()
        fin_cfg = CombinedFinancialConfig()

        snap_a, snap_b = generate_quick_ab_preset_snapshots(
            load_series=self.load_series,
            base_sys_cfg=base_cfg,
            base_rules_cfg=base_rules,
            fin_cfg=fin_cfg,
        )
        self.assertEqual(snap_a.slot_id, "A")
        self.assertEqual(snap_b.slot_id, "B")
        self.assertFalse(snap_a.system_config.enable_generator)
        self.assertTrue(snap_a.system_config.enable_battery)
        self.assertLessEqual(snap_a.kpis.remaining_overload_hours, 0.05)
        self.assertTrue(snap_b.system_config.enable_battery)
        self.assertLessEqual(snap_b.kpis.remaining_overload_hours, 0.05)
        self.assertIsNotNone(snap_a.grid_import_kw_f32)
        self.assertEqual(snap_a.grid_import_kw_f32.dtype, np.float32)
        self.assertEqual(len(snap_a.grid_import_kw_f32), 35040)
        self.assertIsNotNone(snap_a.bess_soc_pct_f32)
        self.assertIsNotNone(snap_a.unmet_overload_kw_f32)

        # Build a lightweight 3rd snapshot to test native 1..N readiness across engine & charts
        snap_c = copy.deepcopy(snap_b)
        snap_c.slot_id = "C"
        snap_c.name = "Scenario C: Tight Hybrid Reserve"
        self.assertGreaterEqual(len(SCENARIO_COMPARISON_PALETTE), 4)
        self.assertEqual(len(normalize_scenario_list(snap_a, snap_b, scenarios=[snap_a, snap_b, snap_c])), 3)

        with mock.patch(
            "current_model.ui_sandbox.Combined_sandbox.engine.dispatch_simulation.simulate_combined_system_dispatch",
            side_effect=AssertionError("Dispatch simulation must not be called during comparison rendering!"),
        ):
            t0 = time.perf_counter()
            df_comp = build_ab_comparison_matrix_df(snap_a, snap_b)
            df_multi = build_ab_comparison_matrix_df(scenarios=[snap_a, snap_b, snap_c])
            lb_fin = build_multi_scenario_leaderboard_df([snap_a, snap_b, snap_c])
            seg_fin = build_segmented_comparison_tables(snap_a, snap_b)
            bwl_inc = compute_incremental_bwl_evaluation(snap_a, snap_b)
            bwl_ext_a = compute_snapshot_bwl_extensions(snap_a)

            fig_tco = create_ab_15y_tco_comparison_figure(snap_a, snap_b)
            fig_stack = create_ab_annual_cost_stack_figure(snap_a, snap_b)
            fig_util = create_ab_supply_and_utilization_figure(snap_a, snap_b)
            fig_monthly = create_ab_monthly_peak_and_grid_import_figure(snap_a, snap_b)
            fig_flow = create_ab_energy_flow_balance_figure(snap_a, snap_b)
            fig_shift = create_ab_capex_vs_opex_shift_figure(snap_a, snap_b)

            fig_prof_all = create_ab_load_profile_overlay_figure(
                snap_a, snap_b, baseline_load_kw=self.load_kw, timestamps=self.timestamps, timeframe="Full Year"
            )

            # 1..N multi-scenario execution on all 7 charts + single-scenario diagram adapter & Y-axis sync
            seg_multi = build_segmented_comparison_tables(scenarios=[snap_a, snap_b, snap_c])
            bwl_inc_multi = compute_incremental_bwl_evaluation(scenarios=[snap_a, snap_b, snap_c])
            sim_view_a = snapshot_to_sim_view(snap_a, self.load_series)
            sim_view_b = snapshot_to_sim_view(snap_b, self.load_series)
            fig_pie_a = create_supply_mix_pie_figure(snap_a.utilization_diagnostics)
            fig_util_a = create_component_utilization_bars_figure(snap_a.utilization_diagnostics)
            fig_disp_a = create_combined_dispatch_soc_figure(sim_view_a)
            fig_disp_b = create_combined_dispatch_soc_figure(sim_view_b)
            sync_side_by_side_yaxis(fig_disp_a, fig_disp_b, axes=("yaxis",))
            fig_wf_a = create_financial_waterfall_bridge_figure(sim_view_a)
            fig_wf_b = create_financial_waterfall_bridge_figure(sim_view_b)
            sync_side_by_side_yaxis(fig_wf_a, fig_wf_b, axes=("yaxis",))
            fig_amort_a = create_financial_tco_trajectory_figure(sim_view_a)
            fig_amort_b = create_financial_tco_trajectory_figure(sim_view_b)
            sync_side_by_side_yaxis(fig_amort_a, fig_amort_b, axes=("yaxis", "yaxis2"))
            fig_mcf_a = create_financial_monthly_cashflow_figure(sim_view_a)
            fig_mcf_b = create_financial_monthly_cashflow_figure(sim_view_b)
            sync_side_by_side_yaxis(fig_mcf_a, fig_mcf_b, axes=("yaxis", "yaxis2"))

            multi_figs = [
                create_ab_15y_tco_comparison_figure(scenarios=[snap_a, snap_b, snap_c]),
                create_ab_annual_cost_stack_figure(scenarios=[snap_a, snap_b, snap_c]),
                create_ab_supply_and_utilization_figure(scenarios=[snap_a, snap_b, snap_c]),
                create_ab_monthly_peak_and_grid_import_figure(scenarios=[snap_a, snap_b, snap_c]),
                create_ab_energy_flow_balance_figure(scenarios=[snap_a, snap_b, snap_c]),
                create_ab_capex_vs_opex_shift_figure(scenarios=[snap_a, snap_b, snap_c]),
                create_ab_load_profile_overlay_figure(
                    scenarios=[snap_a, snap_b, snap_c], baseline_load_kw=self.load_kw, timestamps=self.timestamps, timeframe="Full Year"
                ),
            ]
            elapsed_ms = (time.perf_counter() - t0) * 1000.0

        self.assertFalse(df_comp.empty)
        self.assertFalse(df_multi.empty)
        self.assertEqual(list(df_comp.columns), ["Category", "Metric / KPI", "Current Situation", "Scenario A", "Scenario B", "Delta (B vs. A)"])
        self.assertEqual(set(seg_fin.keys()), {"sizing_rules", "grid_balance", "utilization_dead_cap", "capex_y1_pnl", "bwl_15y_metrics"})
        self.assertEqual(set(seg_multi.keys()), {"sizing_rules", "grid_balance", "utilization_dead_cap", "capex_y1_pnl", "bwl_15y_metrics"})
        self.assertIn("Unused Battery Value", set(seg_fin["utilization_dead_cap"]["df"]["Metric / KPI"]))
        self.assertIn("Savings per kWh vs. Grid", set(seg_fin["bwl_15y_metrics"]["df"]["Metric / KPI"]))
        self.assertIn("Yearly Savings per 1,000 Invested", set(seg_fin["bwl_15y_metrics"]["df"]["Metric / KPI"]))
        self.assertIn("15-Year Cost Split (Upfront vs. Running)", set(seg_fin["bwl_15y_metrics"]["df"]["Metric / KPI"]))
        self.assertIsNotNone(bwl_inc)
        self.assertIsNotNone(bwl_inc_multi)
        self.assertGreaterEqual(bwl_inc["delta_capex_eur"], 0.0)
        self.assertTrue(bwl_ext_a["has_financials"])
        self.assertEqual(fig_wf_a.layout.yaxis.range, fig_wf_b.layout.yaxis.range)
        self.assertEqual(fig_disp_a.layout.yaxis.range, fig_disp_b.layout.yaxis.range)
        self.assertEqual(fig_amort_a.layout.yaxis.range, fig_amort_b.layout.yaxis.range)
        self.assertEqual(fig_mcf_a.layout.yaxis2.range, fig_mcf_b.layout.yaxis2.range)
        self.assertGreater(len(fig_pie_a.data), 0)
        self.assertGreater(len(fig_util_a.data), 0)
        metrics_set = set(df_comp["Metric / KPI"])
        for expected_metric in (
            "Peak Demand Shaved (kW)",
            "Overload Eliminated (%)",
            "On-Site Autarky Share (%)",
            "Annual Residual Grid Import (MWh/yr)",
            "Solar Exported Surplus (MWh/yr)",
            "Battery Min SoC / Unused Reserve",
            "On-Site System LCOE (per kWh)",
            "Annualized Cost per Shaved Peak kW",
        ):
            self.assertIn(expected_metric, metrics_set)

        self.assertEqual(len(lb_fin), 3)
        self.assertEqual(list(lb_fin["Rank"]), [1, 2, 3])
        self.assertIn("15-Year TCO", lb_fin.columns)

        self.assertGreaterEqual(len(fig_tco.data), 3)
        self.assertGreaterEqual(len(fig_stack.data), 7)
        self.assertGreaterEqual(len(fig_util.data), 7)
        self.assertGreaterEqual(len(fig_monthly.data), 6)
        self.assertGreaterEqual(len(fig_flow.data), 7)
        self.assertGreaterEqual(len(fig_shift.data), 6)
        self.assertGreaterEqual(len(fig_prof_all.data), 5)
        for m_fig in multi_figs:
            self.assertGreater(len(m_fig.data), 0)
        self.assertLess(elapsed_ms, 8000.0)

        # When Financials is disabled on all snapshots, comparison matrix omits Economics rows & financial charts stay disabled
        snap_a.system_config.enable_financials = False
        snap_b.system_config.enable_financials = False
        snap_c.system_config.enable_financials = False
        df_tech = build_ab_comparison_matrix_df(snap_a, snap_b)
        lb_tech = build_multi_scenario_leaderboard_df([snap_a, snap_b, snap_c])
        seg_tech = build_segmented_comparison_tables(snap_a, snap_b)
        self.assertEqual(set(seg_tech.keys()), {"sizing_rules", "grid_balance", "utilization_dead_cap"})
        self.assertIsNone(compute_incremental_bwl_evaluation(snap_a, snap_b))
        self.assertNotIn("Economics & 15-Year Financials", set(df_tech["Category"]))
        self.assertIn("Technical Performance", set(df_tech["Category"]))
        self.assertNotIn("15-Year TCO", lb_tech.columns)
        self.assertIn("On-Site Autarky (%)", lb_tech.columns)
        self.assertEqual(len(create_ab_15y_tco_comparison_figure(snap_a, snap_b).data), 0)
        self.assertEqual(len(create_ab_annual_cost_stack_figure(snap_a, snap_b).data), 0)
        self.assertEqual(len(create_ab_capex_vs_opex_shift_figure(snap_a, snap_b).data), 0)
        self.assertGreaterEqual(len(create_ab_supply_and_utilization_figure(snap_a, snap_b).data), 7)
        self.assertGreaterEqual(len(create_ab_monthly_peak_and_grid_import_figure(snap_a, snap_b).data), 6)
        self.assertGreaterEqual(len(create_ab_energy_flow_balance_figure(snap_a, snap_b).data), 7)
        self.assertGreaterEqual(len(create_ab_load_profile_overlay_figure(snap_a, snap_b, baseline_load_kw=self.load_kw).data), 5)

    def test_round_trip_restore_widget_sync_and_baseline_recalc(self):
        """Verifies full snapshot restore payload (Level 1 + Sub-Tabs 2-6) and baseline tariff recalculation."""
        from current_model.ui_sandbox.Combined_sandbox.combined_sandbox_engine import (
            build_load_fingerprint_from_series,
            capture_scenario_snapshot,
            build_restore_widget_sync_payload,
            recalculate_snapshot_on_active_load,
        )

        custom_cfg = CombinedSystemConfig(
            grid_limit_kw=160.0,
            enable_financials=True,
            enable_solar=True,
            site_preset="Spain / Madrid",
            latitude=40.4168,
            longitude=-3.7038,
            solar_sizing_method="direct_kwp",
            solar_kwp=210.0,
            inverter_ac_limit_kw=175.0,
            disable_solar_inverter_limit=False,
            inverter_efficiency_pct=97.0,
            solar_weather_mode="TMY",
            solar_weather_year=2024,
            enable_battery=True,
            battery_capacity_kwh=250.0,
            battery_power_kw=110.0,
            min_soc_pct=15.0,
            max_soc_pct=85.0,
            round_trip_efficiency_pct=90.0,
            enable_generator=True,
            generator_rated_kw=95.0,
            generator_min_load_pct=30.0,
            fuel_type="HVO",
        )
        custom_rules = InteractionRulesConfig(
            rule1_peak_priority="generator_first",
            rule2_battery_strategy="self_consumption_reserve",
            peak_reserve_soc_pct=45.0,
            rule3_charging_sources="all_sources",
        )
        custom_fin = CombinedFinancialConfig(
            currency_code="USD",
            market_mode="custom",
            enable_pillar_1_supplier=True,
            enable_pillar_2_dso=True,
            enable_pillar_3_metering=False,
            enable_pillar_4_taxes=True,
            supplier_pricing_mode="dual_tou",
            supplier_peak_ht_eur_kwh=0.19,
            supplier_offpeak_nt_eur_kwh=0.11,
            solar_lump_sum_capex_eur=145000.0,
            battery_lump_sum_capex_eur=82000.0,
            generator_cost_model="Monthly Rental (OPEX)",
            generator_rental_eur_month=950.0,
            generator_rental_active_months_only=True,
            strict_grid_congestion_mode=True,
            discount_rate_pct=7.5,
        )

        sim_res = simulate_combined_system_dispatch(self.load_kw, self.timestamps, custom_cfg, custom_rules)
        load_fp = build_load_fingerprint_from_series(self.load_series)
        snap = capture_scenario_snapshot(sim_res, custom_fin, "A", "Custom Madrid Hybrid", load_fp)

        payload = build_restore_widget_sync_payload(snap, current_dso_tou_v=4)
        self.assertEqual(payload["system_config"].grid_limit_kw, 160.0)
        self.assertEqual(payload["system_config"].fuel_type, "HVO")
        self.assertEqual(payload["rules_config"].rule1_peak_priority, "generator_first")
        self.assertEqual(payload["rules_config"].rule3_charging_sources, "all_sources")
        self.assertEqual(payload["financial_config"].solar_lump_sum_capex_eur, 145000.0)

        mix_sync = payload["comb_pending_mix_widget_sync"]
        sol_sync = payload["comb_pending_solar_widget_sync"]
        fin_sync = payload["comb_pending_fin_widget_sync"]

        self.assertTrue(mix_sync["comb_enable_solar_toggle"])
        self.assertTrue(mix_sync["comb_enable_battery_toggle"])
        self.assertTrue(mix_sync["comb_enable_generator_toggle"])
        self.assertTrue(mix_sync["comb_enable_financials_toggle"])
        self.assertEqual(mix_sync["comb_grid_limit_input"], 160.0)
        self.assertEqual(mix_sync["comb_rule1_select"], "generator_first")
        self.assertEqual(mix_sync["comb_rule2_reserve_slider"], 45)
        self.assertEqual(mix_sync["comb_generator_fuel_type_select"], "HVO")

        self.assertEqual(sol_sync["comb_solar_preset_choice"], "Spain / Madrid")
        self.assertEqual(sol_sync["comb_solar_sizing_radio"], "Direct Size (kWp)")
        self.assertEqual(sol_sync["comb_solar_direct_kwp_num"], 210.0)
        self.assertEqual(sol_sync["comb_solar_weather_mode_sel"], "Typical Year (PVGIS TMY)")

        self.assertEqual(fin_sync["comb_fin_curr_sel"], "USD")
        self.assertEqual(fin_sync["comb_fin_bill_mode_sel"], "Custom Bill Parts")
        self.assertEqual(fin_sync["comb_fin_sol_lump_capex"], 145000.0)
        self.assertEqual(fin_sync["comb_fin_bat_lump_capex"], 82000.0)
        self.assertEqual(fin_sync["comb_fin_gen_model"], "Monthly Rental (OPEX)")
        self.assertTrue(fin_sync["comb_fin_gen_rent_active_only"])
        self.assertTrue(fin_sync["comb_strict_congestion_toggle"])
        self.assertEqual(fin_sync["comb_fin_dso_tou_v"], 5)

        # Recalculating on new load + tariff must update baseline tariff fingerprint while keeping custom hardware quotes
        new_load = synthesize_benchmark_load_profile_2025(nominal_peak_kw=310.0)
        new_tariff = CombinedFinancialConfig(currency_code="EUR", supplier_energy_price_eur_kwh=0.22)
        recalc_snap = recalculate_snapshot_on_active_load(snap, new_load, active_fin_cfg=new_tariff)
        self.assertEqual(recalc_snap.load_fingerprint, build_load_fingerprint_from_series(new_load))
        self.assertEqual(recalc_snap.financial_config.currency_code, "EUR")
        self.assertEqual(recalc_snap.financial_config.supplier_energy_price_eur_kwh, 0.22)
        self.assertEqual(recalc_snap.financial_config.solar_lump_sum_capex_eur, 145000.0)

    def test_excel_exporter_5th_sheet_and_subtab7_fragment_contract(self):
        """Verifies 4-sheet vs 5-sheet Excel export, Sub-Tab 7 fragment/form contract, and zero Streamlit imports in scenario engine."""
        import ast
        from current_model.ui_sandbox.Combined_sandbox.combined_sandbox_engine import (
            generate_quick_ab_preset_snapshots,
        )

        cfg = CombinedSystemConfig(grid_limit_kw=180.0, enable_solar=True, solar_kwp=120.0, enable_battery=True, enable_financials=True)
        sim_res = simulate_combined_system_dispatch(self.load_kw, self.timestamps, cfg, InteractionRulesConfig())
        evaluate_combined_financials(sim_res, CombinedFinancialConfig())

        # Without saved scenarios -> 4 sheets
        xlsx_4 = build_combined_verification_excel_bytes(sim_res)
        wb_4 = openpyxl.load_workbook(io.BytesIO(xlsx_4), read_only=True)
        self.assertEqual(wb_4.sheetnames, ["Summary & KPIs", "15-Min Dispatch", "Monthly Balance", "Cost & Tariffs"])
        wb_4.close()

        # With saved scenarios -> 5 sheets including Scenario Comparison
        snap_a, snap_b = generate_quick_ab_preset_snapshots(
            load_series=self.load_series,
            base_sys_cfg=cfg,
            base_rules_cfg=InteractionRulesConfig(),
            fin_cfg=CombinedFinancialConfig(),
        )
        xlsx_5 = build_combined_verification_excel_bytes(sim_res, saved_scenarios={"A": snap_a, "B": snap_b})
        wb_5 = openpyxl.load_workbook(io.BytesIO(xlsx_5), read_only=True)
        self.assertEqual(
            wb_5.sheetnames,
            ["Summary & KPIs", "15-Min Dispatch", "Monthly Balance", "Cost & Tariffs", "Scenario Comparison"],
        )
        ws_comp = wb_5["Scenario Comparison"]
        comp_rows = list(ws_comp.iter_rows(values_only=True))
        self.assertEqual(
            list(comp_rows[0]),
            ["Category", "Metric / KPI", "Current Situation", "Scenario A", "Scenario B", "Delta (B vs. A)"],
        )
        self.assertGreater(len(comp_rows), 20)
        wb_5.close()

        # Verify pure Python comparison engines have zero Streamlit imports
        for eng_fname in ("scenario_comparison_engine.py", "scenario_tables_and_profiles.py"):
            engine_path = os.path.abspath(
                os.path.join(
                    os.path.dirname(__file__),
                    "..",
                    "ui_sandbox",
                    "Combined_sandbox",
                    "engine",
                    eng_fname,
                )
            )
            with open(engine_path, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=engine_path)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertNotIn("streamlit", alias.name)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    self.assertNotIn("streamlit", node.module)

        # Verify Sub-Tab 7 fragment & form isolation contract
        code = self._read_combined_ui_source()
        self.assertNotIn("load_series.annual_consumption_kwh", code)
        self.assertIn("@st.fragment\ndef render_subtab7_scenario_comparison", code)
        self.assertIn("@st.fragment\ndef _render_ab_chart_gallery_fragment", code)
        self.assertIn("@st.fragment\ndef _render_power_flow_lazy_fragment", code)
        self.assertIn("@st.fragment\ndef _render_comparison_ledger", code)
        self.assertIn("comb_ab_show_overlay_pf", code)
        self.assertIn("comb_ab_show_side_by_side_pf", code)
        self.assertIn("comb_ab_table_section_sel_fin", code)
        self.assertIn("snapshot_to_sim_view", code)
        self.assertIn("sync_side_by_side_yaxis", code)
        self.assertIn("create_supply_mix_pie_figure", code)
        self.assertIn("create_component_utilization_bars_figure", code)
        self.assertIn("create_combined_dispatch_soc_figure", code)
        self.assertIn("create_financial_tco_trajectory_figure", code)
        self.assertIn("create_financial_waterfall_bridge_figure", code)
        self.assertIn("create_financial_monthly_cashflow_figure", code)
        self.assertIn("create_ab_load_profile_overlay_figure", code)
        self.assertIn('st.form(f"comb_save_slot_{slot_id}_form")', code)
        self.assertIn('st.rerun(scope="app")', code)


if __name__ == "__main__":
    unittest.main()
