"""
========================================================================================
Unit Tests: Data Models (tests/test_models.py)
========================================================================================
"""

import unittest
import datetime
import numpy as np

from current_model.models.load_component import (
    TimeWindow,
    SimpleConsumer,
    LoadComponent,
    consumers_to_drac,
    consumers_from_drac
)
from current_model.models.contract import Contract, get_contract_presets
from current_model.models.grid_limit import GridLimitConfig, OverloadAnalysisResult
from current_model.models.presets import get_industry_preset_consumers, get_office_preset_consumers, get_ev_hub_preset_consumers


class TestLoadComponentModels(unittest.TestCase):
    """Tests for TimeWindow and SimpleConsumer / LoadComponent."""

    def test_timewindow_serialization(self):
        tw = TimeWindow(datetime.time(8, 30), datetime.time(17, 0), True, 45.0, 30)
        data = tw.to_dict()
        self.assertEqual(data["start_time"], "08:30")
        self.assertEqual(data["end_time"], "17:00")
        self.assertTrue(data["has_peak"])
        self.assertEqual(data["peak_power_kw"], 45.0)

        restored = TimeWindow.from_dict(data)
        self.assertEqual(restored.start_time, datetime.time(8, 30))
        self.assertEqual(restored.end_time, datetime.time(17, 0))
        self.assertTrue(restored.has_peak)

    def test_consumer_standard_operation(self):
        # 10 kW machine running 08:00 to 12:00
        consumer = SimpleConsumer(
            name="Machine Test",
            power_kw=10.0,
            time_windows=[TimeWindow(datetime.time(8, 0), datetime.time(12, 0))]
        )
        curve = consumer.get_24h_array()
        self.assertEqual(len(curve), 96)
        # 07:45 (step 31) -> 0 kW
        self.assertEqual(curve[31], 0.0)
        # 08:00 (step 32) -> 10 kW
        self.assertEqual(curve[32], 10.0)
        # 11:45 (step 47) -> 10 kW
        self.assertEqual(curve[47], 10.0)
        # 12:00 (step 48) -> 0 kW
        self.assertEqual(curve[48], 0.0)

    def test_consumer_inrush_peak_spike(self):
        # 20 kW machine, 05:00-14:00 with 30 kW inrush for 30 minutes
        consumer = SimpleConsumer(
            name="Peak Machine",
            power_kw=20.0,
            time_windows=[
                TimeWindow(
                    start_time=datetime.time(5, 0),
                    end_time=datetime.time(14, 0),
                    has_peak=True,
                    peak_power_kw=30.0,
                    peak_duration_min=30
                )
            ]
        )
        curve = consumer.get_24h_array()
        # 05:00 (step 20) -> 30 kW
        self.assertEqual(curve[20], 30.0)
        # 05:15 (step 21) -> 30 kW
        self.assertEqual(curve[21], 30.0)
        # 05:30 (step 22) -> 20 kW (nominal)
        self.assertEqual(curve[22], 20.0)

    def test_consumer_overnight_shift(self):
        # Overnight shift: 22:00 to 06:00
        consumer = SimpleConsumer(
            name="Night Shift Machine",
            power_kw=15.0,
            time_windows=[TimeWindow(datetime.time(22, 0), datetime.time(6, 0))]
        )
        curve = consumer.get_24h_array()
        # 02:00 (step 8) -> 15 kW
        self.assertEqual(curve[8], 15.0)
        # 12:00 (step 48) -> 0 kW
        self.assertEqual(curve[48], 0.0)
        # 23:00 (step 92) -> 15 kW
        self.assertEqual(curve[92], 15.0)

    def test_consumer_multiplier_count(self):
        consumer = SimpleConsumer(
            name="Charging Array",
            power_kw=11.0,
            count=4,
            time_windows=[TimeWindow(datetime.time(8, 0), datetime.time(16, 0))]
        )
        curve = consumer.get_24h_array()
        # 10:00 (step 40) -> 44 kW (11 kW * 4)
        self.assertEqual(curve[40], 44.0)

    def test_consumer_drac_export_import_roundtrip(self):
        original_consumers = get_industry_preset_consumers()
        drac_json_str = consumers_to_drac(original_consumers, profile_name="Industry Test")
        self.assertIn("drac_load_profile", drac_json_str)
        self.assertIn("Industry Test", drac_json_str)

        imported_consumers = consumers_from_drac(drac_json_str)
        self.assertEqual(len(imported_consumers), len(original_consumers))
        self.assertEqual(imported_consumers[0].name, original_consumers[0].name)
        self.assertEqual(imported_consumers[0].power_kw, original_consumers[0].power_kw)


class TestContractModel(unittest.TestCase):
    """Tests for the Contract model, dynamic TOU rates, and .drac serialization."""

    def test_default_contract_creation(self):
        ct = Contract()
        self.assertEqual(ct.name, "Electricity Contract")
        self.assertEqual(ct.currency, "EUR")
        self.assertEqual(ct.base_monthly_fee, 50.0)
        self.assertTrue(len(ct.tou_rates) >= 1)
        self.assertEqual(ct.get_energy_rate(12), 0.20)

    def test_dynamic_tou_rate_matching(self):
        ct = Contract(
            tou_rates=[
                {"name": "Standard Day", "rate": 0.22, "start_time": "06:00", "end_time": "18:00"},
                {"name": "Peak Evening", "rate": 0.35, "start_time": "18:00", "end_time": "22:00"},
                {"name": "Night Tariff", "rate": 0.12, "start_time": "22:00", "end_time": "06:00"}
            ]
        )
        self.assertAlmostEqual(ct.get_energy_rate(10), 0.22)
        self.assertAlmostEqual(ct.get_energy_rate(19), 0.35)
        self.assertAlmostEqual(ct.get_energy_rate(23), 0.12)
        self.assertAlmostEqual(ct.get_energy_rate(2), 0.12)

    def test_datetime_and_weekend_rate(self):
        ct = Contract(
            tou_rates=[
                {"name": "Weekday Peak", "rate": 0.30, "start_time": "08:00", "end_time": "20:00"},
                {"name": "Weekday OffPeak", "rate": 0.15, "start_time": "20:00", "end_time": "08:00"}
            ],
            weekend_is_off_peak=True
        )
        # Saturday: 2026-08-22
        dt_saturday = datetime.datetime(2026, 8, 22, 14, 0)
        self.assertAlmostEqual(ct.get_energy_rate(dt_saturday), 0.15)

    def test_contract_drac_serialization_and_deserialization(self):
        original = Contract(
            name="Green Energy Pro 2026",
            currency="USD",
            base_monthly_fee=75.50,
            contracted_capacity_kw=350.0,
            monthly_capacity_tariff=0.25,
            demand_capacity_tariff=1.80,
            max_physical_limit_kw=700.0,
            peak_penalty_rate=0.50,
            reactive_power_tariff=0.04,
            min_power_factor=0.92,
            reactive_power_allowance_pct=30.0,
            tou_rates=[
                {"name": "Day Peak", "rate": 0.28, "start_time": "08:00", "end_time": "20:00"},
                {"name": "Night Off-Peak", "rate": 0.14, "start_time": "20:00", "end_time": "08:00"}
            ],
            default_energy_rate=0.28,
            weekend_is_off_peak=True,
            taxes_and_fees=[
                {"name": "City Utility Tax", "type": "percentage", "value": 4.5, "description": "Municipal Tax"},
                {"name": "Grid Surcharge", "type": "fixed_monthly", "value": 25.0, "description": "Flat Monthly"}
            ]
        )

        drac_json_str = original.to_json(indent=2)
        self.assertIn("drac_contract", drac_json_str)
        self.assertIn("Green Energy Pro 2026", drac_json_str)
        self.assertIn("USD", drac_json_str)

        restored = Contract.from_json(drac_json_str)
        self.assertEqual(restored.name, "Green Energy Pro 2026")
        self.assertEqual(restored.currency, "USD")
        self.assertAlmostEqual(restored.base_monthly_fee, 75.50)
        self.assertAlmostEqual(restored.contracted_capacity_kw, 350.0)
        self.assertAlmostEqual(restored.monthly_capacity_tariff, 0.25)
        self.assertAlmostEqual(restored.demand_capacity_tariff, 1.80)
        self.assertEqual(len(restored.tou_rates), 2)
        self.assertEqual(len(restored.taxes_and_fees), 2)
        self.assertTrue(restored.weekend_is_off_peak)

    def test_contract_presets(self):
        presets = get_contract_presets()
        self.assertGreaterEqual(len(presets), 3)
        for name, preset_contract in presets.items():
            self.assertIsInstance(preset_contract, Contract)
            self.assertTrue(preset_contract.contracted_capacity_kw > 0)
            self.assertTrue(len(preset_contract.tou_rates) >= 1)

    def test_contract_resilience_to_malformed_data(self):
        # Empty dict should fallback safely to valid defaults
        empty_contract = Contract.from_dict({})
        self.assertEqual(empty_contract.currency, "EUR")
        self.assertTrue(len(empty_contract.tou_rates) >= 1)

        # None/Invalid input
        invalid_contract = Contract.from_dict(None)  # type: ignore
        self.assertEqual(invalid_contract.currency, "EUR")


class TestGridLimitModels(unittest.TestCase):
    """Tests for GridLimitConfig and OverloadAnalysisResult."""

    def test_overload_calculation_with_violation(self):
        # 4 steps: 50, 120, 150, 80 kW with limit of 100 kW
        curve = np.array([50.0, 120.0, 150.0, 80.0])
        result = OverloadAnalysisResult.from_curve(curve, grid_limit_kw=100.0, step_hours=0.25)
        self.assertTrue(result.has_violation)
        self.assertEqual(result.overload_peak_kw, 50.0)      # max(150 - 100) = 50
        self.assertEqual(result.overload_intervals_count, 2) # steps 1 and 2
        self.assertEqual(result.overload_duration_hours, 0.5) # 2 * 0.25h = 0.5h
        # excess: (20 + 50) * 0.25 = 70 * 0.25 = 17.5 kWh
        self.assertEqual(result.overload_energy_kwh, 17.5)

    def test_overload_calculation_without_violation(self):
        curve = np.array([50.0, 70.0, 80.0, 60.0])
        result = OverloadAnalysisResult.from_curve(curve, grid_limit_kw=100.0)
        self.assertFalse(result.has_violation)
        self.assertEqual(result.overload_peak_kw, 0.0)
        self.assertEqual(result.overload_duration_hours, 0.0)


if __name__ == "__main__":
    unittest.main()

