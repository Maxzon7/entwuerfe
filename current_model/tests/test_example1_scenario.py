"""
========================================================================================
Unit Tests for End-to-End Demo Scenario "Example1" (tests/test_example1_scenario.py)
========================================================================================

Description:
------------
Comprehensive test suite validating the complete "Example1" European commercial benchmark
scenario spanning Tab 1 (Consumption), Tab 2 (Contract), Sub-Tab 3.1 (Solar PV Standalone),
and Sub-Tab 3.2 (Solar & Consumption Integration).
"""

import unittest
import datetime
import numpy as np
import pandas as pd
import streamlit as st

from current_model.core.demo_scenario import (
    get_example1_consumers,
    get_example1_contract,
    get_example1_solar_setup,
    load_example1_scenario,
    clear_demo_scenario,
    get_active_model_summary
)
from current_model.core.synthetic_engine import aggregate_synthetic_year, aggregate_synthetic_24h
from current_model.core.solar_engine import simulate_solar_pv_generation
from current_model.core.financial_engine import compute_financial_bill
from current_model.models.presets import PRESET_TEMPLATES
from current_model.models.contract import get_contract_presets


class TestExample1Scenario(unittest.TestCase):
    """Test suite validating the end-to-end Example1 scenario components and orchestration."""

    def setUp(self):
        # Clear Streamlit session state before each test
        clear_demo_scenario()

    def tearDown(self):
        clear_demo_scenario()

    def test_example1_consumers_and_annual_load(self):
        """Verify the 5 realistic commercial consumer assets and 365-day load simulation."""
        consumers = get_example1_consumers()
        self.assertEqual(len(consumers), 5, "Example 1 should have exactly 5 distinct consumer assets.")

        # Check total connected power
        total_connected_p = sum(c.power_kw for c in consumers)
        self.assertGreaterEqual(total_connected_p, 300.0)

        # Run 365-day annual simulation (35,040 steps @ 15-min)
        df_year, total_curve, metrics = aggregate_synthetic_year(consumers=consumers, year=2025)

        self.assertEqual(len(df_year), 35040, "365-day leap-free year must contain 35,040 15-minute intervals.")
        self.assertIn("Total_Demand_kW", df_year.columns)
        self.assertIn("timestamp", df_year.columns)

        peak_kw = float(df_year["Total_Demand_kW"].max())
        total_kwh = float(df_year["Total_Demand_kW"].sum() * 0.25)

        # Realistic checks for a commercial/industrial facility:
        # Peak should be ~380 - 410 kW (around 395 kW)
        self.assertGreater(peak_kw, 350.0, "Peak load should be > 350 kW to match 400 kW contracted capacity.")
        self.assertLess(peak_kw, 450.0, "Peak load should remain within reasonable limits of 400 kW.")

        # Annual energy should be ~1,000 - 1,300 MWh
        self.assertGreater(total_kwh, 900000.0, "Annual consumption should exceed 900 MWh.")
        self.assertLess(total_kwh, 1500000.0, "Annual consumption should remain under 1,500 MWh.")

    def test_example1_contract_and_tou_schedule(self):
        """Verify the commercial multi-tariff contract in EUR with capacity charge and 3 TOU windows."""
        contract = get_example1_contract()

        self.assertEqual(contract.currency, "EUR")
        self.assertEqual(contract.contracted_capacity_kw, 400.0)
        self.assertEqual(contract.monthly_capacity_tariff, 14.50)
        self.assertEqual(contract.demand_capacity_tariff, 2.50)
        self.assertTrue(contract.weekend_is_off_peak)

        # Test TOU rate lookups
        # Night / Valle: 0.1350 €/kWh
        r_night = contract.get_energy_rate(datetime.time(2, 0))
        self.assertAlmostEqual(r_night, 0.1350, places=4)

        # Day / Mid-Peak (Resto / Llano): 0.2150 €/kWh
        r_day = contract.get_energy_rate(datetime.time(12, 0))
        self.assertAlmostEqual(r_day, 0.2150, places=4)

        # Evening / High-Peak (Pico / Punta): 0.2950 €/kWh
        r_eve = contract.get_energy_rate(datetime.time(19, 0))
        self.assertAlmostEqual(r_eve, 0.2950, places=4)

        # Weekend off-peak lookup
        dt_sat = datetime.datetime(2025, 6, 14, 12, 0)  # Saturday noon
        self.assertAlmostEqual(contract.get_energy_rate(dt_sat), 0.1350, places=4)

        # Statutory taxes (VAT 19% and electricity tax)
        self.assertGreaterEqual(len(contract.taxes_and_fees), 2)
        tax_names = [t["name"] for t in contract.taxes_and_fees]
        self.assertTrue(any("VAT" in name or "Mehrwertsteuer" in name for name in tax_names))

    def test_example1_solar_setup_european_benchmark(self):
        """Verify the European solar installation in Seville, Spain with optimal South orientation and financials."""
        cfg, loc, fin = get_example1_solar_setup()

        # Seville, Spain location
        self.assertIn("Seville", loc.name)
        self.assertGreater(loc.latitude, 30.0, "Latitude should be in Southern Europe (> 30° N).")
        self.assertLess(loc.latitude, 45.0)

        # 696.6 kWp TOPCon
        self.assertEqual(cfg.module_count, 1548)
        self.assertEqual(cfg.module_power_wp, 450.0)
        self.assertEqual(cfg.dc_capacity_kwp, 696.6)
        self.assertEqual(cfg.inverter_capacity_kw, 590.0)

        # South orientation in Northern Hemisphere
        self.assertEqual(cfg.tilt_deg, 30.0)
        self.assertEqual(cfg.azimuth_deg, 180.0, "Azimuth in Europe / Northern Hemisphere must be 180° for South-facing.")

        # Financial parameters
        self.assertTrue(fin.is_enabled)
        self.assertEqual(fin.cost_modules_per_wp, 1.00)
        self.assertEqual(fin.cost_inverter_per_w, 0.07)
        self.assertEqual(fin.cost_substructure_per_wp, 0.15)
        self.assertEqual(fin.cost_installation_per_wp, 0.35)

    def test_one_click_load_and_clear_scenario(self):
        """Verify load_example1_scenario() populates all 4 tabs consistently and clear_demo_scenario() resets."""
        # 1. Initially unconfigured
        summary_before = get_active_model_summary()
        self.assertFalse(summary_before["is_example1"])

        # 2. Execute 1-click loading
        load_example1_scenario()

        # 3. Inspect global state
        self.assertTrue(st.session_state.get("example1_active"))
        self.assertEqual(st.session_state.get("tab1_active_source"), "synthetic")

        # Tab 1: active synthetic df
        df_load = st.session_state.get("active_synthetic_df")
        self.assertIsNotNone(df_load)
        self.assertEqual(len(df_load), 35040)

        # Tab 2: active contract
        contract = st.session_state.get("active_contract")
        self.assertIsNotNone(contract)
        self.assertEqual(contract.currency, "EUR")
        self.assertEqual(contract.contracted_capacity_kw, 400.0)

        # Tab 3.1: standalone solar simulation
        res_solar = st.session_state.get("app_tab3_sim_result")
        self.assertIsNotNone(res_solar)
        self.assertGreater(res_solar.kpis.annual_energy_mwh, 800.0)

        # Tab 3.2: coupled dispatch simulation
        res_coupled = st.session_state.get("app_tab3_int_sim_result")
        self.assertIsNotNone(res_coupled)

        # Check coupled dispatch metrics
        c_kpis = res_coupled.kpis
        self.assertGreater(c_kpis.self_consumption_rate_pct, 45.0, "Self-consumption rate should be substantial (~60%).")
        self.assertGreater(c_kpis.solar_fraction_autarky_pct, 45.0, "Solar fraction autarky should be substantial (~65%).")

        # Check peak demand shaving
        p_orig = float(res_coupled.df_timeseries["P_Load_kW"].max())
        p_res = float(res_coupled.df_timeseries["P_Residual_kW"].max())
        peak_shaved_annual = p_orig - p_res
        max_instantaneous_shaved = float((res_coupled.df_timeseries["P_Load_kW"] - res_coupled.df_timeseries["P_Residual_kW"]).max())

        self.assertGreaterEqual(peak_shaved_annual, 10.0, "Annual peak demand should be reduced by solar.")
        self.assertGreater(max_instantaneous_shaved, 200.0, "Midday solar should shave instantaneous load by > 200 kW.")

        # 4. Check summary inspector
        summary_active = get_active_model_summary()
        self.assertTrue(summary_active["is_example1"])
        self.assertTrue(summary_active["has_load"])
        self.assertTrue(summary_active["has_contract"])
        self.assertTrue(summary_active["has_solar"])
        self.assertTrue(summary_active["has_integration"])
        self.assertEqual(summary_active["contract_currency"], "EUR")

        # 5. Clear scenario
        clear_demo_scenario()
        summary_after = get_active_model_summary()
        self.assertFalse(summary_after["is_example1"])

    def test_presets_additive_registration(self):
        """Verify that Example 1 is registered in presets without removing any existing presets."""
        # Tab 1 Presets
        self.assertIn("Example 1: European Commercial Facility", PRESET_TEMPLATES)
        self.assertIn("Industry & Manufacturing", PRESET_TEMPLATES)
        self.assertIn("Commercial Office Building", PRESET_TEMPLATES)
        self.assertIn("Mobility & EV Hub", PRESET_TEMPLATES)

        # Tab 2 Presets
        presets = get_contract_presets()
        self.assertIn("Example 1: European Commercial Multi-Tariff (EUR)", presets)
        self.assertIn("Paula1 (Bodegas Salentein - EDEMSA T2 R MT)", presets)
        self.assertIn("Industrial Multi-Tariff (EUR)", presets)
        self.assertIn("Commercial Standard Fixed (EUR)", presets)
    def test_residual_grid_load_comparison_figure(self):
        """Verify create_residual_grid_load_comparison_figure renders correctly in all 3 modes."""
        from current_model.ui.tab_comparison.charts import create_residual_grid_load_comparison_figure
        
        sample_records = [
            {
                "id": "base",
                "name": "Status Quo (Base Scenario)",
                "total_load_mwh": 441.4,
                "monthly_load_mwh": [36.8] * 12,
                "monthly_residual_mwh": [36.8] * 12,
                "residual_grid_mwh": 441.4,
                "direct_consumption_mwh": 0.0,
                "autarky_pct": 0.0
            },
            {
                "id": "sub1",
                "name": "Option 1: Solar & Storage",
                "total_load_mwh": 441.4,
                "monthly_load_mwh": [36.8] * 12,
                "monthly_residual_mwh": [10.9] * 12,
                "residual_grid_mwh": 131.1,
                "direct_consumption_mwh": 310.3,
                "autarky_pct": 70.3
            }
        ]

        # Test 12-month trajectory curve mode (default)
        fig_curve = create_residual_grid_load_comparison_figure(sample_records, chart_mode="monthly_curve")
        self.assertIsNotNone(fig_curve)
        self.assertEqual(len(fig_curve.data), 2)
        self.assertEqual(fig_curve.data[0].name, "Facility Total Demand (Status Quo)")
        self.assertIn("Option 1: Solar & Storage", fig_curve.data[1].name)

        # Test monthly grouped mode
        fig_grouped = create_residual_grid_load_comparison_figure(sample_records, chart_mode="monthly_grouped")
        self.assertIsNotNone(fig_grouped)
        self.assertEqual(len(fig_grouped.data), 2)

        # Test annual totals mode
        fig_annual = create_residual_grid_load_comparison_figure(sample_records, chart_mode="annual_totals")
        self.assertIsNotNone(fig_annual)
        self.assertEqual(len(fig_annual.data), 1)

    def test_residual_grid_load_timeseries_figure(self):
        """Verify create_residual_grid_load_timeseries_figure renders high-resolution 15-minute dispatch."""
        from current_model.ui.tab_comparison.charts import create_residual_grid_load_timeseries_figure
        import pandas as pd
        import numpy as np

        dates = pd.date_range("2025-01-01 00:00", periods=96 * 7, freq="15min")
        df_load = pd.DataFrame({
            "timestamp": dates,
            "Total_Demand_kW": np.random.uniform(50, 150, len(dates))
        })
        sub_ts = [
            {
                "name": "Option 1: Solar",
                "color": "#38BDF8",
                "residual_series": df_load["Total_Demand_kW"] * 0.6
            }
        ]

        fig = create_residual_grid_load_timeseries_figure(
            df_load=df_load,
            sub_scenarios_timeseries=sub_ts,
            power_col="Total_Demand_kW",
            grid_limit_kw=120.0
        )
        self.assertIsNotNone(fig)
        self.assertEqual(len(fig.data), 2)
        self.assertEqual(fig.data[0].name, "Facility Total Demand (Status Quo)")
        self.assertIn("Option 1: Solar", fig.data[1].name)


    def test_build_scenario_evaluation_records_with_various_subscenarios(self):
        """Verify _build_scenario_evaluation_records handles subscenarios with and without solar without UnboundLocalError."""
        from current_model.ui.tab_comparison.view import _build_scenario_evaluation_records
        from current_model.models.scenario import ProjectContainer, BaseScenario, SubScenario
        from current_model.models.solar import SolarPVConfig
        from current_model.models.bess import BESSConfig

        proj = ProjectContainer(
            project_name="Mixed SubScenario Facility",
            base_scenario=BaseScenario(
                name="Base",
                baseline_annual_kwh=100000.0,
                baseline_annual_cost=30000.0
            ),
            sub_scenarios=[
                # SubScenario 1: Solar enabled
                SubScenario(
                    id="sub_solar",
                    name="Solar PV Branch",
                    include_solar=True,
                    solar_config=SolarPVConfig(module_count=200, module_power_wp=400.0)
                ),
                # SubScenario 2: BESS only (Solar disabled)
                SubScenario(
                    id="sub_bess_only",
                    name="Battery Only Branch",
                    include_solar=False,
                    include_bess=True,
                    bess_config=BESSConfig(capacity_kwh=100.0, max_discharge_power_kw=50.0)
                ),
                # SubScenario 3: Tariff switch only (Solar disabled, BESS disabled)
                SubScenario(
                    id="sub_tariff_only",
                    name="Tariff Only Branch",
                    include_solar=False,
                    include_bess=False,
                    use_custom_grid_tariff=True
                ),
                # SubScenario 4: Empty / default (Old legacy scenario upload)
                SubScenario(
                    id="sub_empty",
                    name="Empty Branch",
                    include_solar=False,
                    include_bess=False
                )
            ]
        )

        records = _build_scenario_evaluation_records(proj)
        self.assertEqual(len(records), 5)  # 1 base + 4 subscenarios
        for r in records:
            self.assertIn("monthly_load_mwh", r)
            self.assertIn("monthly_residual_mwh", r)
            self.assertEqual(len(r["monthly_load_mwh"]), 12)
            self.assertEqual(len(r["monthly_residual_mwh"]), 12)


if __name__ == "__main__":
    unittest.main()

