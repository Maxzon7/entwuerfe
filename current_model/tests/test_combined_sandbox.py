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
    CombinedSystemConfig,
    InteractionRulesConfig,
    CombinedFinancialConfig,
    derive_solar_sizing_and_formula,
    compute_dual_battery_sizing,
    refresh_bottleneck_table_configured_status,
    compute_dual_generator_sizing,
    simulate_combined_system_dispatch,
    evaluate_combined_financials,
)
from current_model.ui_sandbox.Combined_sandbox.combined_charts import (
    create_consumption_baseline_figure,
    create_combined_dispatch_soc_figure,
    create_financial_cost_comparison_figure,
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

        fig_cost = create_financial_cost_comparison_figure(sim_res)
        self.assertEqual(len(fig_cost.data), 6)

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
            self.assertEqual(fig2.layout.uirevision, tf)
            self.assertGreaterEqual(fig2.layout.margin.t, 90)
            self.assertGreaterEqual(fig2.layout.legend.y, 1.10)
            if tf == "All":
                self.assertEqual(len(fig2.data[0].x), 35040)
                self.assertIn("All", fig2.layout.annotations[0].text)
            elif tf == "7D":
                self.assertEqual(len(fig2.data[0].x), 672)
                self.assertIn("7D", fig2.layout.annotations[0].text)

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
        sandbox_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "ui_sandbox", "Combined_sandbox")
        )
        for fname in (
            "app.py",
            "combined_sandbox_engine.py",
            "combined_charts.py",
            "combined_excel_exporter.py",
        ):
            fpath = os.path.join(sandbox_dir, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                content_lower = f.read().lower()
            for term in forbidden_terms:
                self.assertNotIn(
                    term,
                    content_lower,
                    f"Forbidden marketing term '{term}' found in {fname}",
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


if __name__ == "__main__":
    unittest.main()
