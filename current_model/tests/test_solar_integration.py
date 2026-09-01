"""
========================================================================================
Unit Tests for Solar PV System Integration & Load Dispatch (tests/test_solar_integration.py)
========================================================================================
"""

import unittest
import numpy as np
import pandas as pd

from current_model.models.solar import SolarLocation, SolarPVConfig, SolarSimulationResult
from current_model.core.solar_engine import (
    simulate_solar_pv_generation,
    compute_solar_load_dispatch,
    calculate_scenario_target_kwp,
    calculate_recommended_inverter_size
)


class TestSolarIntegration(unittest.TestCase):
    """Test suite verifying the electrical load coupling, conservation of energy, and dispatch metrics."""

    def setUp(self):
        self.location = SolarLocation(
            name="Mendoza Test Site",
            latitude=-33.5133,
            longitude=-69.2561,
            elevation_m=1100.0
        )
        self.config = SolarPVConfig(
            dc_capacity_kwp=100.0,
            module_technology="Mono-Si PERC/TOPCon",
            temp_coefficient_pct_c=-0.25,
            nmot_c=45.0,
            tilt_deg=30.0,
            azimuth_deg=0.0,
            inverter_capacity_kw=85.0,
            inverter_efficiency_pct=98.0,
            economic_lifetime_years=15
        )

    def test_electrical_conservation_of_energy(self):
        """
        Verify strict interval-by-interval conservation of energy:
          1. P_direct(t) + P_residual(t) == P_load(t)
          2. P_direct(t) + P_surplus(t) == P_solar(t)
          3. 0 <= P_direct(t) <= min(P_load(t), P_solar(t))
        """
        # Create representative synthetic 35,040 load profile (e.g. oscillating 20kW to 120kW)
        n_steps = 35040
        time_idx = pd.date_range(start="2025-01-01 00:00:00", periods=n_steps, freq="15min")
        hours = (time_idx.hour + time_idx.minute / 60.0).to_numpy()
        base_load = 30.0 + 40.0 * np.clip(np.sin(np.pi * (hours - 6.0) / 12.0), 0.0, None)
        df_load = pd.DataFrame({"timestamp": time_idx, "Total_Demand_kW": base_load})

        sim_res: SolarSimulationResult = simulate_solar_pv_generation(
            config=self.config,
            location=self.location,
            load_df=df_load
        )
        df = sim_res.df_timeseries
        kpis = sim_res.kpis

        # 1. Load split conservation: Direct + Residual == Total Demand
        self.assertTrue(np.allclose(df["P_Direct_kW"] + df["P_Residual_kW"], df["P_Load_kW"], atol=1e-2))

        # 2. Solar split conservation: Direct + Surplus == Solar AC Output
        self.assertTrue(np.allclose(df["P_Direct_kW"] + df["P_Surplus_kW"], df["P_AC_kW"], atol=1e-2))

        # 3. Direct consumption bounds
        min_load_solar = np.minimum(df["P_Load_kW"], df["P_AC_kW"])
        self.assertTrue(np.allclose(df["P_Direct_kW"], min_load_solar, atol=1e-2))

        # 4. Energy totals check (kWh)
        self.assertGreater(kpis.total_load_kwh, 0.0)
        self.assertGreater(kpis.direct_consumption_kwh, 0.0)
        self.assertGreater(kpis.surplus_generation_kwh, 0.0)
        self.assertGreater(kpis.residual_load_kwh, 0.0)

        # 5. Rates must be in [0%, 100%]
        self.assertTrue(0.0 <= kpis.self_consumption_rate_pct <= 100.0)
        self.assertTrue(0.0 <= kpis.solar_fraction_autarky_pct <= 100.0)

    def test_direct_dispatch_function_pure(self):
        """Verify pure numpy dispatch calculation logic on isolated test vectors."""
        p_solar = np.array([0.0, 10.0, 50.0, 80.0, 100.0, 0.0])
        p_load = np.array([20.0, 30.0, 50.0, 40.0, 20.0, 15.0])

        res = compute_solar_load_dispatch(p_solar, p_load, hours_per_step=0.25)

        # Direct: min(solar, load)
        np.testing.assert_array_almost_equal(res["p_direct_kw"], np.array([0.0, 10.0, 50.0, 40.0, 20.0, 0.0]))

        # Surplus: max(0, solar - load)
        np.testing.assert_array_almost_equal(res["p_surplus_kw"], np.array([0.0, 0.0, 0.0, 40.0, 80.0, 0.0]))

        # Residual: max(0, load - solar)
        np.testing.assert_array_almost_equal(res["p_residual_kw"], np.array([20.0, 20.0, 0.0, 0.0, 0.0, 15.0]))

        # Energy sums:
        # direct_kwh = sum([0, 10, 50, 40, 20, 0]) * 0.25 = 120 * 0.25 = 30.0
        self.assertAlmostEqual(res["direct_kwh"], 30.0)
        # surplus_kwh = sum([0, 0, 0, 40, 80, 0]) * 0.25 = 120 * 0.25 = 30.0
        self.assertAlmostEqual(res["surplus_kwh"], 30.0)
        # residual_kwh = sum([20, 20, 0, 0, 0, 15]) * 0.25 = 55 * 0.25 = 13.75 -> 13.8
        self.assertAlmostEqual(res["residual_kwh"], 13.8, delta=0.1)

        # total_solar = 240 * 0.25 = 60.0 kWh -> SCR = 30 / 60 = 50.0%
        self.assertAlmostEqual(res["self_consumption_rate_pct"], 50.0)


if __name__ == "__main__":
    unittest.main()
