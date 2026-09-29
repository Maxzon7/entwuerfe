"""
========================================================================================
Unit Tests: Solar PV + BESS Hybrid Engine (current_model/tests/test_solar_bess_engine.py)
========================================================================================
"""

import unittest
import numpy as np
import pandas as pd

from current_model.models.solar import SolarPVConfig, SolarLocation
from current_model.models.bess import BESSConfig
from current_model.core.solar_bess_engine import (
    simulate_solar_bess_dispatch,
    SolarBESSSimulationResult,
    SolarBESSKPIs
)


class TestSolarBESSEngine(unittest.TestCase):
    """Test suite for Solar PV + BESS hybrid dispatch engine."""

    def setUp(self):
        # 96 steps (1 day at 15-min intervals)
        self.n_steps = 96
        self.ts = pd.date_range("2026-06-01 00:00:00", periods=self.n_steps, freq="15min")
        
        # Base constant load of 100 kW
        self.load_df = pd.DataFrame({
            "timestamp": self.ts,
            "Total_Demand_kW": np.full(self.n_steps, 100.0)
        })

        self.solar_cfg = SolarPVConfig(
            module_count=600,
            module_power_wp=450.0,
            inverter_capacity_kw=230.0
        )
        self.location = SolarLocation(name="Mendoza Test Site", latitude=-33.5, longitude=-69.2)

        self.bess_cfg = BESSConfig(
            capacity_kwh=200.0,
            max_charge_power_kw=50.0,
            max_discharge_power_kw=50.0,
            round_trip_efficiency_pct=90.0,
            soc_min_pct=10.0,
            soc_max_pct=90.0,
            initial_soc_pct=50.0,
            dispatch_strategy="self_consumption"
        )

    def test_solar_surplus_charges_bess_first(self):
        """Verify that when Solar > Load, surplus charges BESS before exporting to grid."""
        # Custom solar profile: 200 kW during middle of day, 0 at night
        p_solar = np.zeros(self.n_steps)
        p_solar[40:60] = 200.0  # 200 kW solar vs 100 kW load -> 100 kW surplus

        precomputed_solar = pd.DataFrame({"P_AC_kW": p_solar})

        res = simulate_solar_bess_dispatch(
            load_df=self.load_df,
            solar_config=self.solar_cfg,
            bess_config=self.bess_cfg,
            grid_limit_kw=200.0,
            precomputed_solar_df=precomputed_solar
        )

        df = res.df_dispatch
        # In interval 40, Load = 100, Solar = 200 -> Direct = 100, Surplus = 100
        step_40 = df.iloc[40]
        self.assertEqual(step_40["P_Direct_kW"], 100.0)
        self.assertEqual(step_40["P_Surplus_kW"], 100.0)
        # BESS max charge power is 50 kW -> BESS charges at 50 kW
        self.assertEqual(step_40["P_BESS_Charge_PV_kW"], 50.0)
        # Remaining 50 kW is exported to grid
        self.assertEqual(step_40["P_Grid_Export_kW"], 50.0)
        # Zero grid import
        self.assertEqual(step_40["P_Grid_Import_kW"], 0.0)

    def test_bess_discharges_on_solar_deficit(self):
        """Verify that when Solar < Load, BESS discharges to cover residual load."""
        # Solar = 40 kW vs Load = 100 kW -> Deficit / Residual = 60 kW
        p_solar = np.full(self.n_steps, 40.0)
        precomputed_solar = pd.DataFrame({"P_AC_kW": p_solar})

        res = simulate_solar_bess_dispatch(
            load_df=self.load_df,
            solar_config=self.solar_cfg,
            bess_config=self.bess_cfg,
            grid_limit_kw=200.0,
            precomputed_solar_df=precomputed_solar
        )

        df = res.df_dispatch
        step_0 = df.iloc[0]
        self.assertEqual(step_0["P_Direct_kW"], 40.0)
        self.assertEqual(step_0["P_Residual_kW"], 60.0)
        # BESS max discharge power is 50 kW -> BESS discharges at 50 kW
        self.assertEqual(step_0["P_BESS_Discharge_kW"], 50.0)
        # Remaining 10 kW is imported from grid
        self.assertEqual(step_0["P_Grid_Import_kW"], 10.0)

    def test_peak_shaving_strategy(self):
        """Verify that in peak_shaving mode, BESS only discharges when residual load > target_cap."""
        cfg_ps = BESSConfig(
            capacity_kwh=200.0,
            max_charge_power_kw=50.0,
            max_discharge_power_kw=50.0,
            soc_min_pct=10.0,
            soc_max_pct=90.0,
            initial_soc_pct=50.0,
            dispatch_strategy="peak_shaving",
            peak_shaving_threshold_kw=80.0
        )

        # Load = 100 kW, Solar = 40 kW -> Residual = 60 kW.
        # Since Residual (60 kW) < Threshold (80 kW), BESS should NOT discharge in peak_shaving mode
        p_solar = np.full(self.n_steps, 40.0)
        precomputed_solar = pd.DataFrame({"P_AC_kW": p_solar})

        res = simulate_solar_bess_dispatch(
            load_df=self.load_df,
            solar_config=self.solar_cfg,
            bess_config=cfg_ps,
            grid_limit_kw=80.0,
            precomputed_solar_df=precomputed_solar
        )

        df = res.df_dispatch
        step_0 = df.iloc[0]
        self.assertEqual(step_0["P_BESS_Discharge_kW"], 0.0)
        self.assertEqual(step_0["P_Grid_Import_kW"], 60.0)

    def test_soc_envelope_boundaries(self):
        """Verify SoC stays strictly within [soc_min_pct, soc_max_pct]."""
        p_solar = np.zeros(self.n_steps)
        p_solar[20:80] = 500.0  # Massive solar surplus

        precomputed_solar = pd.DataFrame({"P_AC_kW": p_solar})

        res = simulate_solar_bess_dispatch(
            load_df=self.load_df,
            solar_config=self.solar_cfg,
            bess_config=self.bess_cfg,
            grid_limit_kw=200.0,
            precomputed_solar_df=precomputed_solar
        )

        df = res.df_dispatch
        self.assertTrue((df["SoC_pct"] <= self.bess_cfg.soc_max_pct + 1e-4).all())
        self.assertTrue((df["SoC_pct"] >= self.bess_cfg.soc_min_pct - 1e-4).all())

    def test_kpis_and_monthly_metrics(self):
        """Verify KPI calculations and monthly metrics structure."""
        res = simulate_solar_bess_dispatch(
            load_df=self.load_df,
            solar_config=self.solar_cfg,
            bess_config=self.bess_cfg,
            grid_limit_kw=200.0,
            location=self.location
        )

        kpis = res.kpis
        self.assertIsInstance(kpis, SolarBESSKPIs)
        self.assertGreater(kpis.annual_load_kwh, 0.0)
        self.assertGreater(kpis.annual_solar_kwh, 0.0)
        self.assertGreaterEqual(kpis.autarky_rate_pct, 0.0)
        self.assertLessEqual(kpis.autarky_rate_pct, 100.0)
        self.assertEqual(len(res.monthly_metrics), 12)


if __name__ == "__main__":
    unittest.main()
