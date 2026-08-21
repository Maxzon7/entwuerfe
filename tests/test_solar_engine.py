"""
========================================================================================
Unit Tests for Solar PV Simulation Engine (tests/test_solar_engine.py)
========================================================================================
"""

import unittest
import pandas as pd
import numpy as np

from current_model.models.solar import SolarLocation, SolarPVConfig, SolarSimulationResult
from current_model.core.solar_engine import (
    generate_synthetic_solar_weather,
    fetch_open_meteo_solar_data,
    simulate_solar_pv_generation
)


class TestSolarEngine(unittest.TestCase):
    """Test suite verifying the Solar PV physics calculations and data structures."""

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
            temp_coefficient_pct_c=-0.35,
            nmot_c=45.0,
            tilt_deg=30.0,
            azimuth_deg=0.0,
            inverter_capacity_kw=85.0,
            inverter_efficiency_pct=98.0,
            soiling_loss_pct=2.0,
            shading_loss_pct=1.5,
            dc_wiring_loss_pct=1.5
        )

    def test_synthetic_solar_weather_generation(self):
        """Verify clear-sky solar weather generates full 8,760 hourly steps with physical ranges."""
        df = generate_synthetic_solar_weather(
            latitude=self.location.latitude,
            longitude=self.location.longitude,
            tilt_deg=self.config.tilt_deg,
            azimuth_deg=self.config.azimuth_deg,
            year=2024
        )
        self.assertEqual(len(df), 8760)
        self.assertTrue("GHI_W_m2" in df.columns)
        self.assertTrue("POA_W_m2" in df.columns)
        self.assertTrue("Temp_Ambient_C" in df.columns)

        # Check physical non-negativity
        self.assertTrue((df["GHI_W_m2"] >= 0.0).all())
        self.assertTrue((df["POA_W_m2"] >= 0.0).all())
        # Max POA should be realistic peak sunlight (e.g. 700 - 1300 W/m2)
        self.assertTrue(700.0 <= df["POA_W_m2"].max() <= 1400.0)

    def test_solar_pv_simulation_physics(self):
        """Verify full physical simulation returns valid KPIs and clipped power."""
        result: SolarSimulationResult = simulate_solar_pv_generation(
            config=self.config,
            location=self.location
        )
        kpis = result.kpis
        df = result.df_timeseries

        # 1. AC power must never exceed inverter capacity
        self.assertTrue((df["P_AC_kW"] <= self.config.inverter_capacity_kw + 1e-3).all())

        # 2. Cell temperature must be higher than ambient during peak sunlight
        sunny_mask = df["POA_W_m2"] > 800.0
        if sunny_mask.any():
            self.assertTrue((df.loc[sunny_mask, "Temp_Cell_C"] > df.loc[sunny_mask, "Temp_Ambient_C"]).all())

        # 3. Specific yield in sunny Mendoza should be between 1,200 and 2,400 kWh/kWp
        self.assertTrue(1200.0 <= kpis.specific_yield_kwh_per_kwp <= 2400.0)

        # 4. Performance Ratio must be realistic (70% - 92%)
        self.assertTrue(70.0 <= kpis.performance_ratio_pct <= 92.0)

        # 5. Exactly 12 monthly yields
        self.assertEqual(len(result.monthly_yields), 12)
        for m in result.monthly_yields:
            self.assertTrue(m.energy_kwh >= 0.0)
            self.assertTrue(m.specific_yield_kwh_kwp >= 0.0)

        # 6. Loss breakdown must contain all expected stages
        self.assertTrue("Nominal Plane-of-Array Potential" in result.loss_breakdown)
        self.assertTrue("Net AC Energy Delivered" in result.loss_breakdown)


if __name__ == "__main__":
    unittest.main()
