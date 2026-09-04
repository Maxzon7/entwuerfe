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


if __name__ == "__main__":
    unittest.main()
