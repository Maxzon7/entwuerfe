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
    fetch_pvgis_tmy_data,
    load_solar_weather_data,
    compute_multi_year_risk_profile,
    simulate_solar_pv_generation,
    calculate_scenario_target_kwp,
    calculate_recommended_inverter_size,
    compute_multi_year_generation
)


class TestSolarEngine(unittest.TestCase):
    """Test suite verifying the Solar PV physics calculations, 15-min resolution, and data structures."""

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
            albedo=0.20,
            inverter_capacity_kw=85.0,
            inverter_efficiency_pct=98.0,
            soiling_loss_pct=2.0,
            shading_loss_pct=1.5,
            dc_wiring_loss_pct=1.5,
            degradation_pct_a=0.5,
            economic_lifetime_years=15
        )

    def test_synthetic_solar_weather_15min_resolution(self):
        """Verify clear-sky solar weather generates full 35,040 15-minute steps with physical ranges."""
        df = generate_synthetic_solar_weather(
            latitude=self.location.latitude,
            longitude=self.location.longitude,
            tilt_deg=self.config.tilt_deg,
            azimuth_deg=self.config.azimuth_deg,
            albedo=self.config.albedo,
            year=2025
        )
        self.assertEqual(len(df), 35040)
        self.assertTrue("GHI_W_m2" in df.columns)
        self.assertTrue("POA_W_m2" in df.columns)
        self.assertTrue("Temp_Ambient_C" in df.columns)

        # Check physical non-negativity
        self.assertTrue((df["GHI_W_m2"] >= 0.0).all())
        self.assertTrue((df["POA_W_m2"] >= 0.0).all())
        # Max POA should be realistic peak sunlight (e.g. 700 - 1350 W/m2)
        self.assertTrue(700.0 <= df["POA_W_m2"].max() <= 1350.0)

    def test_temperature_derating_physics(self):
        """Verify temperature derating strictly applies -0.25%/°C above 25°C and 0 loss at/below 25°C."""
        result: SolarSimulationResult = simulate_solar_pv_generation(
            config=self.config,
            location=self.location
        )
        df = result.df_timeseries

        # Points where cell temperature <= 25.0°C must have derate factor of 1.0 (no penalty)
        cool_mask = df["Temp_Cell_C"] <= 25.0
        if cool_mask.any():
            self.assertTrue(np.allclose(df.loc[cool_mask, "Thermal_Derate_Factor"], 1.0, atol=1e-3))

        # Points where cell temperature is 45.0°C (excess 20°C) must have derate factor: 1.0 - 20 * 0.0025 = 0.95
        hot_mask = np.isclose(df["Temp_Cell_C"], 45.0, atol=0.2)
        if hot_mask.any():
            self.assertTrue(np.allclose(df.loc[hot_mask, "Thermal_Derate_Factor"], 0.95, atol=0.01))

    def test_solar_pv_simulation_physics_and_clipping(self):
        """Verify full physical simulation returns valid KPIs and clipped power on 15-minute grid."""
        result: SolarSimulationResult = simulate_solar_pv_generation(
            config=self.config,
            location=self.location
        )
        kpis = result.kpis
        df = result.df_timeseries

        # 1. 35,040 steps
        self.assertEqual(len(df), 35040)

        # 2. AC power must never exceed inverter capacity
        self.assertTrue((df["P_AC_kW"] <= self.config.inverter_capacity_kw + 1e-3).all())

        # 3. Energy per step must equal P_AC * 0.25h
        self.assertTrue(np.allclose(df["E_AC_kWh"], df["P_AC_kW"] * 0.25, atol=1e-2))

        # 4. Cell temperature must be higher than ambient during peak sunlight
        sunny_mask = df["POA_W_m2"] > 800.0
        if sunny_mask.any():
            self.assertTrue((df.loc[sunny_mask, "Temp_Cell_C"] > df.loc[sunny_mask, "Temp_Ambient_C"]).all())

        # 5. Specific yield in sunny Mendoza should be in the realistic range (1,300 to 2,350 kWh/kWp)
        self.assertTrue(1300.0 <= kpis.specific_yield_kwh_per_kwp <= 2350.0)

        # 6. Performance Ratio must be realistic (72% - 90%)
        self.assertTrue(72.0 <= kpis.performance_ratio_pct <= 90.0)

        # 7. Exactly 12 monthly yields
        self.assertEqual(len(result.monthly_yields), 12)
        for m in result.monthly_yields:
            self.assertTrue(m.energy_kwh >= 0.0)
            self.assertTrue(m.specific_yield_kwh_kwp >= 0.0)

        # 8. Loss breakdown must contain all expected stages
        self.assertTrue("Nominal Plane-of-Array Potential" in result.loss_breakdown)
        self.assertTrue("Net AC Energy Delivered" in result.loss_breakdown)

    def test_auto_sizing_and_inverter_scaling(self):
        """Verify scenario auto-sizing target kWp and recommended inverter size calculations."""
        # 100,000 kWh annual consumption with 1650 kWh/kWp specific yield
        # 100% target: 100,000 / 1650 = 60.6 kWp
        kwp_100 = calculate_scenario_target_kwp(annual_load_kwh=100000.0, specific_yield_kwh_kwp=1650.0, scenario_pct=100.0)
        self.assertAlmostEqual(kwp_100, 60.6, delta=0.2)

        # 40% target: 40,000 / 1650 = 24.2 kWp
        kwp_40 = calculate_scenario_target_kwp(annual_load_kwh=100000.0, specific_yield_kwh_kwp=1650.0, scenario_pct=40.0)
        self.assertAlmostEqual(kwp_40, 24.2, delta=0.2)

        # Inverter size: 60.6 kWp / 1.175 = 51.6 kW
        inv_size = calculate_recommended_inverter_size(dc_kwp=kwp_100, dc_ac_ratio=1.175)
        self.assertAlmostEqual(inv_size, 51.6, delta=0.2)

    def test_multi_year_aging_degradation_15_years(self):
        """Verify 15-year lifetime degradation calculation with 2-stage degradation."""
        projections = compute_multi_year_generation(
            annual_kwh=100000.0,
            first_year_deg_pct=1.50,
            annual_deg_pct=0.40,
            lifetime_years=15
        )
        self.assertEqual(len(projections), 15)

        # Year 1: factor = 1 - 0.015 = 0.985, 98,500 kWh
        self.assertEqual(projections[0]["year"], 1)
        self.assertAlmostEqual(projections[0]["aging_factor"], 0.985, delta=1e-4)
        self.assertAlmostEqual(projections[0]["energy_kwh"], 98500.0, delta=1.0)

        # Year 2: factor = (1 - 0.015) * (1 - 0.004) = 0.985 * 0.996 = 0.98106
        self.assertEqual(projections[1]["year"], 2)
        self.assertAlmostEqual(projections[1]["aging_factor"], 0.98106, delta=1e-4)
        self.assertAlmostEqual(projections[1]["energy_kwh"], 98106.0, delta=2.0)

    def test_module_sizing_and_area_calculation(self):
        """Verify module count, wattage sizing, and physical area requirements."""
        # Test Case 1: 1,548 panels à 410 Wp -> 634.68 kWp
        cfg1 = SolarPVConfig(module_count=1548, module_power_wp=410.0)
        self.assertAlmostEqual(cfg1.dc_capacity_kwp, 634.68, delta=0.1)

        # Test Case 2: 80 panels, 1.2m x 0.7m, factor 1.8 -> exactly 121.0 m² (Matching Excel Bild 4)
        cfg2 = SolarPVConfig(
            module_count=80,
            module_length_m=1.20,
            module_width_m=0.70,
            area_factor=1.80
        )
        self.assertAlmostEqual(cfg2.gross_panel_area_m2, 67.20, delta=0.01)
        self.assertAlmostEqual(cfg2.required_area_m2, 121.0, delta=0.1)

    def test_multi_technology_comparison_matrix(self):
        """Verify comparative production matrix computes PERC vs TOPCon vs Backcontact yields."""
        result: SolarSimulationResult = simulate_solar_pv_generation(
            config=self.config,
            location=self.location
        )
        tech_items = result.technology_comparison
        self.assertEqual(len(tech_items), 3)

        perc = next(t for t in tech_items if t.tech_key == "PERC")
        topcon = next(t for t in tech_items if t.tech_key == "TOPCon")
        backcontact = next(t for t in tech_items if t.tech_key == "Backcontact")

        # PERC baseline gain must be 0%
        self.assertEqual(perc.gain_pct_vs_perc, 0.0)

        # TOPCon (450W, -0.29%/°C) must yield higher than PERC (410W, -0.35%/°C)
        self.assertGreater(topcon.year_1_kwh, perc.year_1_kwh)
        self.assertGreater(topcon.gain_pct_vs_perc, 8.0)

        # Backcontact (470W, -0.26%/°C) must yield higher than TOPCon
        self.assertGreater(backcontact.year_1_kwh, topcon.year_1_kwh)
        self.assertGreater(backcontact.gain_pct_vs_perc, topcon.gain_pct_vs_perc)

    def test_pvgis_tmy_weather_data_fetching_and_structure(self):
        """Verify TMY data returns a valid 35,040 15-minute grid with physical solar values."""
        df_tmy, label = fetch_pvgis_tmy_data(
            latitude=self.location.latitude,
            longitude=self.location.longitude,
            tilt_deg=self.config.tilt_deg,
            azimuth_deg=self.config.azimuth_deg,
            albedo=self.config.albedo
        )
        self.assertEqual(len(df_tmy), 35040)
        self.assertTrue("POA_W_m2" in df_tmy.columns)
        self.assertTrue("GHI_W_m2" in df_tmy.columns)
        self.assertTrue("Temp_Ambient_C" in df_tmy.columns)
        self.assertGreater(float(df_tmy["POA_W_m2"].max()), 500.0)
        self.assertGreater(float(df_tmy["POA_W_m2"].sum()), 0.0)

    def test_multi_year_risk_assessment(self):
        """Verify empirical P50 and P90 risk statistics are computed over multi-year span."""
        risk = compute_multi_year_risk_profile(
            config=self.config,
            location=self.location,
            start_year=2020,
            end_year=2024
        )
        self.assertTrue("p50_kwh" in risk)
        self.assertTrue("p90_kwh" in risk)
        self.assertTrue("p95_kwh" in risk)
        self.assertTrue("volatility_pct" in risk)
        self.assertGreater(risk["p50_kwh"], 0.0)
        self.assertGreater(risk["p90_kwh"], 0.0)
        self.assertLessEqual(risk["p90_kwh"], risk["p50_kwh"])
        self.assertLessEqual(risk["p95_kwh"], risk["p90_kwh"])
        self.assertGreater(risk["max_kwh"], risk["min_kwh"])

    def test_simulate_solar_pv_generation_with_multi_year_mode(self):
        """Verify simulate_solar_pv_generation populates multi-year risk metrics when requested."""
        cfg_multi = SolarPVConfig(
            module_count=600,
            module_power_wp=450.0,
            inverter_capacity_kw=230.0,
            weather_mode="multi_year",
            multi_year_start=2020,
            multi_year_end=2024
        )
        res = simulate_solar_pv_generation(config=cfg_multi, location=self.location)
        self.assertIsNotNone(res.kpis.p50_annual_kwh)
        self.assertIsNotNone(res.kpis.p90_annual_kwh)
        self.assertIsNotNone(res.multi_year_risk_summary)
        self.assertGreater(res.kpis.p50_annual_kwh, 0.0)


if __name__ == "__main__":
    unittest.main()



