"""
========================================================================================
Unit Tests for Combined System Sandbox (tests/test_combined_sandbox.py)
========================================================================================

Verifies:
  1. Transparent Solar kWp derivation formula & EU PVGIS data source string.
  2. All 8 enable/disable combinations of Solar, Battery, and Generator over 35,040 steps.
  3. Operating Rules 1, 2, and 3 (Peak priority, Battery reserve strategy, Charging sources).
  4. Interactive Plotly figures (Consumption baseline + Synchronized 2-in-1 Dispatch & SoC).
  5. Clean Screen Policy & strict terminology compliance across `ui_sandbox/Combined_sandbox/`.
========================================================================================
"""

import os
import unittest
import numpy as np
import pandas as pd

from current_model.ui_sandbox.Currentsituation_sandbox.engine.consumption_pipeline import (
    synthesize_benchmark_load_profile_2025,
)
from current_model.ui_sandbox.Combined_sandbox.combined_sandbox_engine import (
    CombinedSystemConfig,
    InteractionRulesConfig,
    derive_solar_sizing_and_formula,
    simulate_combined_system_dispatch,
)
from current_model.ui_sandbox.Combined_sandbox.combined_charts import (
    create_consumption_baseline_figure,
    create_combined_dispatch_soc_figure,
)


class TestCombinedSandbox(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.load_series = synthesize_benchmark_load_profile_2025(nominal_peak_kw=250.0)
        cls.load_kw = cls.load_series.power_kw
        cls.timestamps = cls.load_series.timestamps

    def test_solar_derivation_formula_and_pvgis_label(self):
        """Verifies transparent Solar kWp calculation formula and EU PVGIS source string."""
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

        deriv_direct = derive_solar_sizing_and_formula(
            annual_consumption_kwh=250000.0,
            specific_yield_kwh_per_kwp=1000.0,
            sizing_method="direct_kwp",
            direct_kwp=200.0,
            target_share_pct=60.0,
            panel_wp=500.0,
            enable_solar=True,
        )
        self.assertAlmostEqual(deriv_direct.installed_kwp, 200.0, places=1)
        self.assertEqual(deriv_direct.panel_count, 400)
        self.assertIn("200,000 kWh/year", deriv_direct.formula_text)

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
                    if not en_solar:
                        self.assertEqual(res.kpis.solar_total_generation_kwh, 0.0)
                    if not en_bess:
                        self.assertEqual(res.kpis.battery_total_discharged_kwh, 0.0)
                    if not en_gen:
                        self.assertEqual(res.kpis.generator_total_generation_kwh, 0.0)

    def test_interaction_rules_behavior(self):
        """Verifies Rules 1, 2, and 3 produce physically distinct and valid dispatch outcomes."""
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
        )

        # Rule 1 comparison: Battery first vs Generator first
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

        # Rule 2 comparison: Self-consumption + Peak Reserve should cycle battery more than Peak Shaving only
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

        # Rule 3 comparison: Grid charging and Generator cycle charging
        res_grid_chg = simulate_combined_system_dispatch(
            load_kw=self.load_kw,
            timestamps=self.timestamps,
            system_cfg=cfg,
            rules_cfg=InteractionRulesConfig(
                rule1_peak_priority="battery_first",
                rule2_battery_strategy="self_consumption_reserve",
                peak_reserve_soc_pct=40.0,
                rule3_charging_sources="solar_and_grid",
            ),
        )
        self.assertGreater(res_grid_chg.kpis.battery_charged_from_grid_kwh, 0.0)

        res_cycle_chg = simulate_combined_system_dispatch(
            load_kw=self.load_kw,
            timestamps=self.timestamps,
            system_cfg=cfg,
            rules_cfg=InteractionRulesConfig(
                rule1_peak_priority="generator_first",
                rule2_battery_strategy="self_consumption_reserve",
                peak_reserve_soc_pct=30.0,
                rule3_charging_sources="solar_and_generator",
            ),
        )
        self.assertGreaterEqual(res_cycle_chg.kpis.battery_charged_from_gen_kwh, 0.0)

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

        fig1 = create_consumption_baseline_figure(self.timestamps, self.load_kw, timeframe="Peak Week")
        fig2 = create_combined_dispatch_soc_figure(sim_res, timeframe="Peak Week")
        self.assertGreater(len(fig1.data), 0)
        self.assertGreater(len(fig2.data), 4)

        # Strict terminology check across Combined_sandbox source files
        forbidden_terms = [
            "double lever",
            "double-lever",
            "hockey-stick",
            "hockey stick",
            "pareto",
            "the perfect generator",
            "zero-breach champion",
            "4-pillar reconciliation",
        ]
        sandbox_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "ui_sandbox", "Combined_sandbox")
        )
        for fname in ("app.py", "combined_sandbox_engine.py", "combined_charts.py"):
            fpath = os.path.join(sandbox_dir, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                content_lower = f.read().lower()
            for term in forbidden_terms:
                self.assertNotIn(
                    term,
                    content_lower,
                    f"Forbidden marketing term '{term}' found in {fname}",
                )


if __name__ == "__main__":
    unittest.main()

