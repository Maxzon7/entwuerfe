"""
========================================================================================
Unit Tests for Sub-Tab 3.2 Solar & Consumption Integration (tests/test_solar_integration_tab.py)
========================================================================================
"""

import unittest
import numpy as np
import pandas as pd
import streamlit as st

from current_model.models.solar import SolarLocation, SolarPVConfig, SolarSimulationResult, SolarKPIs
from current_model.core.solar_engine import (
    simulate_solar_pv_generation,
    compute_solar_load_dispatch,
    calculate_scenario_target_kwp,
    calculate_recommended_inverter_size
)
from current_model.ui.common.session_utils import (
    find_active_load_data_in_session,
    find_active_contract_in_session,
    get_load_profile_summary
)
from current_model.ui.tab3_solar.integration_charts import (
    create_solar_load_dispatch_figure,
    create_monthly_energy_balance_figure,
    create_seasonal_dispatch_daily_figure,
    create_energy_flow_sankey_figure
)


class TestSolarIntegrationTab(unittest.TestCase):
    """Test suite validating Sub-Tab 3.2 functionality, dispatch physics, and visual components."""

    def setUp(self):
        self.location = SolarLocation(
            name="Mendoza Benchmark",
            latitude=-32.8908,
            longitude=-68.8272,
            elevation_m=746.0
        )
        self.config = SolarPVConfig(
            module_count=500,
            module_power_wp=450.0,
            technology_preset="TOPCon",
            inverter_capacity_kw=190.0,
            tilt_deg=28.0,
            azimuth_deg=0.0
        )

    def test_session_utils_load_summary(self):
        """Verify load profile summary metrics extraction."""
        n_steps = 96  # 24 hours @ 15-min
        p_vals = np.array([50.0] * n_steps)
        df_dummy = pd.DataFrame({
            "timestamp": pd.date_range("2025-01-01 00:00:00", periods=n_steps, freq="15min"),
            "Total_Demand_kW": p_vals
        })

        summary = get_load_profile_summary(df_dummy, power_col="Total_Demand_kW")
        # 50 kW continuous for 24h = 1200 kWh
        self.assertAlmostEqual(summary["total_kwh"], 1200.0, places=1)
        self.assertAlmostEqual(summary["total_mwh"], 1.2, places=2)
        self.assertEqual(summary["peak_kw"], 50.0)
        self.assertEqual(summary["data_points"], 96)
        self.assertAlmostEqual(summary["duration_days"], 1.0, places=1)

    def test_target_coverage_auto_sizing(self):
        """Verify 40%, 60%, 80%, and 100% net coverage calculation logic."""
        annual_kwh = 1_000_000.0  # 1 GWh / year
        spec_yield = 1600.0       # 1,600 kWh/kWp

        kwp_40 = calculate_scenario_target_kwp(annual_kwh, spec_yield, 40.0)
        kwp_60 = calculate_scenario_target_kwp(annual_kwh, spec_yield, 60.0)
        kwp_80 = calculate_scenario_target_kwp(annual_kwh, spec_yield, 80.0)
        kwp_100 = calculate_scenario_target_kwp(annual_kwh, spec_yield, 100.0)

        # 1M * 0.40 / 1600 = 250 kWp
        self.assertAlmostEqual(kwp_40, 250.0, places=1)
        # 1M * 0.60 / 1600 = 375 kWp
        self.assertAlmostEqual(kwp_60, 375.0, places=1)
        # 1M * 0.80 / 1600 = 500 kWp
        self.assertAlmostEqual(kwp_80, 500.0, places=1)
        # 1M * 1.00 / 1600 = 625 kWp
        self.assertAlmostEqual(kwp_100, 625.0, places=1)

        # Inverter sizing recommendation
        inv_size = calculate_recommended_inverter_size(kwp_100, dc_ac_ratio=1.175)
        self.assertAlmostEqual(inv_size, round(625.0 / 1.175, 1), places=1)

    def test_coupled_dispatch_conservation(self):
        """Verify interval-by-interval dispatch physics and energy balance conservation."""
        time_idx = pd.date_range("2025-01-01 00:00:00", periods=96, freq="15min")
        # Load: 100 kW day, 40 kW night
        hours = time_idx.hour + time_idx.minute / 60.0
        load_kw = np.where((hours >= 8) & (hours <= 18), 100.0, 40.0)
        df_load = pd.DataFrame({"timestamp": time_idx, "Total_Demand_kW": load_kw})

        sim_res = simulate_solar_pv_generation(
            config=self.config,
            location=self.location,
            load_df=df_load
        )

        df = sim_res.df_timeseries
        kpis = sim_res.kpis

        # 1. Conservation: Direct + Residual == Facility Load
        self.assertTrue(np.allclose(df["P_Direct_kW"] + df["P_Residual_kW"], df["P_Load_kW"], atol=1e-2))

        # 2. Conservation: Direct + Surplus == Solar AC Output
        self.assertTrue(np.allclose(df["P_Direct_kW"] + df["P_Surplus_kW"], df["P_AC_kW"], atol=1e-2))

        # 3. Direct <= min(Load, Solar)
        self.assertTrue(np.all(df["P_Direct_kW"] <= np.minimum(df["P_Load_kW"], df["P_AC_kW"]) + 1e-3))

        # 4. KPI boundaries
        self.assertTrue(0.0 <= kpis.self_consumption_rate_pct <= 100.0)
        self.assertTrue(0.0 <= kpis.solar_fraction_autarky_pct <= 100.0)

    def test_integration_chart_generators(self):
        """Verify Plotly figure constructors execute cleanly and return valid figures."""
        time_idx = pd.date_range("2025-01-01 00:00:00", periods=96, freq="15min")
        df_dummy = pd.DataFrame({
            "timestamp": time_idx,
            "P_Load_kW": [50.0] * 96,
            "P_AC_kW": [40.0] * 96,
            "P_Direct_kW": [40.0] * 96,
            "P_Surplus_kW": [0.0] * 96,
            "P_Residual_kW": [10.0] * 96
        })

        # Chart 1: Dispatch Timeseries
        fig_ts = create_solar_load_dispatch_figure(df_dummy, dc_capacity_kwp=225.0, inverter_capacity_kw=190.0)
        self.assertIsNotNone(fig_ts)
        self.assertTrue(len(fig_ts.data) >= 3)

        # Chart 2: Monthly Energy Balance
        fig_monthly = create_monthly_energy_balance_figure(df_dummy)
        self.assertIsNotNone(fig_monthly)
        self.assertTrue(len(fig_monthly.data) >= 2)

        # Chart 3: Seasonal Diurnal Profiles
        fig_seasonal = create_seasonal_dispatch_daily_figure(df_dummy)
        self.assertIsNotNone(fig_seasonal)

        # Chart 4: Sankey Diagram
        dummy_kpis = SolarKPIs(
            annual_energy_kwh=100_000.0,
            total_load_kwh=120_000.0,
            direct_consumption_kwh=80_000.0,
            surplus_generation_kwh=20_000.0,
            residual_load_kwh=40_000.0
        )
        fig_sankey = create_energy_flow_sankey_figure(dummy_kpis)
        self.assertIsNotNone(fig_sankey)

    def test_couple_solar_simulation_with_load_fast(self):
        """Verify that couple_solar_simulation_with_load accurately and rapidly couples solar output."""
        from current_model.core.solar_engine import couple_solar_simulation_with_load

        # 1. Run physical simulation standalone (without load)
        standalone_res = simulate_solar_pv_generation(
            config=self.config,
            location=self.location
        )
        self.assertIn("P_AC_kW", standalone_res.df_timeseries.columns)

        # 2. Fast couple with facility load
        time_idx = pd.date_range("2025-01-01 00:00:00", periods=len(standalone_res.df_timeseries), freq="15min")
        hours = time_idx.hour + time_idx.minute / 60.0
        load_kw = np.where((hours >= 8) & (hours <= 18), 120.0, 30.0)
        df_load = pd.DataFrame({"timestamp": time_idx, "Total_Demand_kW": load_kw})

        coupled_res = couple_solar_simulation_with_load(standalone_res, df_load)

        df = coupled_res.df_timeseries
        kpis = coupled_res.kpis

        # Verify coupled columns
        for col in ["P_Load_kW", "P_Direct_kW", "P_Surplus_kW", "P_Residual_kW"]:
            self.assertIn(col, df.columns)

        # Verify physics conservation
        self.assertTrue(np.allclose(df["P_Direct_kW"] + df["P_Residual_kW"], df["P_Load_kW"], atol=1e-2))
        self.assertTrue(np.allclose(df["P_Direct_kW"] + df["P_Surplus_kW"], df["P_AC_kW"], atol=1e-2))
        self.assertTrue(np.all(df["P_Direct_kW"] <= np.minimum(df["P_Load_kW"], df["P_AC_kW"]) + 1e-3))

        # Verify KPIs are populated
        self.assertGreater(kpis.direct_consumption_kwh, 0.0)
        self.assertGreater(kpis.total_load_kwh, 0.0)
        self.assertGreaterEqual(kpis.self_consumption_rate_pct, 0.0)
        self.assertLessEqual(kpis.self_consumption_rate_pct, 100.0)
        self.assertGreaterEqual(kpis.solar_fraction_autarky_pct, 0.0)
        self.assertLessEqual(kpis.solar_fraction_autarky_pct, 100.0)

    def test_find_active_contract_in_session_scenarios(self):
        """Verify robust contract resolution across project container, sub-scenarios, and session keys."""
        from current_model.models.contract import Contract
        from current_model.models.scenario import ProjectContainer, BaseScenario, SubScenario

        # Clear session keys
        for k in list(st.session_state.keys()):
            del st.session_state[k]

        test_contract = Contract(name="Primary Contract", contracted_capacity_kw=250.0)

        # 1. Direct session key
        st.session_state["active_contract"] = test_contract
        resolved = find_active_contract_in_session()
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.contracted_capacity_kw, 250.0)

        # 2. Project container base scenario
        del st.session_state["active_contract"]
        base = BaseScenario(name="Base", base_contract=test_contract)
        proj = ProjectContainer(project_name="Test Proj", base_scenario=base)
        st.session_state["project_container"] = proj

        resolved = find_active_contract_in_session()
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.contracted_capacity_kw, 250.0)

        # 3. Sub-scenario custom tariff override
        sub_custom = Contract(name="Special Custom Tariff", contracted_capacity_kw=500.0)
        sub = SubScenario(
            id="sub_custom",
            name="Option with Custom Grid Tariff",
            use_custom_grid_tariff=True,
            custom_contract=sub_custom
        )
        proj.sub_scenarios.append(sub)
        proj.active_sub_scenario_id = "sub_custom"

        resolved = find_active_contract_in_session()
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.contracted_capacity_kw, 500.0)
        self.assertEqual(resolved.name, "Special Custom Tariff")

    def test_load_profile_gap_alignment_bypass(self):
        """Verify that couple_solar_simulation_with_load correctly handles load profile gaps in bypass mode without phase shifts."""
        from current_model.core.solar_engine import couple_solar_simulation_with_load

        # Standalone solar simulation
        standalone_res = simulate_solar_pv_generation(
            config=self.config,
            location=self.location
        )

        # Create multi-day load dataframe with an explicit 10-day gap:
        # Part 1: Jan 1 to Jan 15 (14 days)
        # GAP: Jan 15 00:00 to Jan 25 00:00 (10 days missing)
        # Part 2: Jan 25 to Feb 28
        idx_p1 = pd.date_range("2025-01-01 00:00:00", "2025-01-14 23:45:00", freq="15min")
        idx_p2 = pd.date_range("2025-01-25 00:00:00", "2025-02-28 23:45:00", freq="15min")
        combined_idx = idx_p1.union(idx_p2)

        hours = combined_idx.hour + combined_idx.minute / 60.0
        load_kw = np.where((hours >= 11) & (hours <= 13), 150.0, 30.0)
        df_load = pd.DataFrame({"timestamp": combined_idx, "Total_Demand_kW": load_kw})

        coupled_res = couple_solar_simulation_with_load(standalone_res, df_load, gap_handling="bypass")
        df = coupled_res.df_timeseries
        kpis = coupled_res.kpis

        # 1. Gaps are detected in KPIs
        self.assertTrue(kpis.has_load_gaps)
        self.assertGreaterEqual(kpis.gap_count, 1)
        self.assertGreater(kpis.total_gap_days, 9.0)
        self.assertLess(kpis.data_coverage_pct, 100.0)
        self.assertIsNotNone(kpis.annualized_load_kwh)

        # 2. Check gap period: Jan 18 12:00 (inside gap)
        mask_gap_noon = df["timestamp"] == pd.Timestamp("2025-01-18 12:00:00")
        row_gap = df.loc[mask_gap_noon].iloc[0]
        self.assertTrue(np.isnan(row_gap["P_Load_kW"]))
        self.assertTrue(np.isnan(row_gap["P_Direct_kW"]))
        self.assertGreater(row_gap["P_Surplus_kW"], 0.0)

        # 3. Check post-gap alignment: Jan 26 12:00 (noon after gap)
        # Solar noon and load noon MUST align with NO phase shift!
        mask_post_noon = df["timestamp"] == pd.Timestamp("2025-01-26 12:00:00")
        row_post = df.loc[mask_post_noon].iloc[0]
        self.assertFalse(np.isnan(row_post["P_Load_kW"]))
        self.assertAlmostEqual(row_post["P_Load_kW"], 150.0, delta=1.0)
        self.assertGreater(row_post["P_Direct_kW"], 0.0)

    def test_load_profile_gap_alignment_impute(self):
        """Verify that couple_solar_simulation_with_load fills gaps with typical profiles in impute mode."""
        from current_model.core.solar_engine import couple_solar_simulation_with_load

        standalone_res = simulate_solar_pv_generation(
            config=self.config,
            location=self.location
        )

        idx_p1 = pd.date_range("2025-01-01 00:00:00", "2025-01-14 23:45:00", freq="15min")
        idx_p2 = pd.date_range("2025-01-25 00:00:00", "2025-02-28 23:45:00", freq="15min")
        combined_idx = idx_p1.union(idx_p2)
        hours = combined_idx.hour + combined_idx.minute / 60.0
        load_kw = np.where((hours >= 11) & (hours <= 13), 150.0, 30.0)
        df_load = pd.DataFrame({"timestamp": combined_idx, "Total_Demand_kW": load_kw})

        coupled_res = couple_solar_simulation_with_load(standalone_res, df_load, gap_handling="impute")
        df = coupled_res.df_timeseries
        kpis = coupled_res.kpis

        self.assertEqual(kpis.gap_handling_mode, "impute")
        # In impute mode, there are no NaNs in P_Load_kW
        self.assertFalse(df["P_Load_kW"].isna().any())
        self.assertFalse(df["P_Direct_kW"].isna().any())

        # Jan 18 12:00 was imputed with typical noon load
        mask_gap_noon = df["timestamp"] == pd.Timestamp("2025-01-18 12:00:00")
        row_gap = df.loc[mask_gap_noon].iloc[0]
        self.assertGreater(row_gap["P_Load_kW"], 0.0)
        self.assertGreater(row_gap["P_Direct_kW"], 0.0)


if __name__ == "__main__":
    unittest.main()
