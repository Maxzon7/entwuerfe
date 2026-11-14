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
        self.assertEqual(len(fig_tco.data), 3)

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

    def test_all_subtab_forms_encapsulated(self):
        """Verifies that all heavy input sections are encapsulated in st.form or st.fragment to eliminate intermediate reruns."""
        app_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "ui_sandbox", "Combined_sandbox", "app.py")
        )
        with open(app_path, "r", encoding="utf-8") as f:
            code = f.read()

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

        # 6. Verify that hardcoded max_value=200 is gone from Combined_sandbox/app.py
        app_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "ui_sandbox", "Combined_sandbox", "app.py")
        )
        with open(app_path, "r", encoding="utf-8") as f:
            app_code = f.read()

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
        app_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "ui_sandbox",
            "Combined_sandbox",
            "app.py",
        )
        with open(app_path, "r", encoding="utf-8") as f:
            app_src = f.read()

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

        app_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "ui_sandbox",
            "Combined_sandbox",
            "app.py",
        )
        with open(app_path, "r", encoding="utf-8") as f:
            app_src = f.read()

        self.assertIn("def render_supply_mix_and_utilization_overview(", app_src)
        self.assertIn("create_supply_mix_pie_figure", app_src)
        self.assertIn("create_component_utilization_bars_figure", app_src)
        self.assertIn("Trim Unused Battery Capacity", app_src)
        self.assertIn('st.form("comb_system_mix_form")', app_src)
        self.assertIn('st.form("comb_rules_form")', app_src)


if __name__ == "__main__":
    unittest.main()
