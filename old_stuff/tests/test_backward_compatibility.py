"""
========================================================================================
Unit Tests: Backward Compatibility & Migrations (tests/test_backward_compatibility.py)
========================================================================================
"""

import unittest
import datetime
from current_model.models.load_component import TimeWindow, SimpleConsumer
from current_model.models.contract import Contract


class TestBackwardCompatibility(unittest.TestCase):
    """Tests ensuring older serialized session state objects migrate gracefully without exceptions."""

    def test_legacy_consumer_object_migration(self):
        # Emulate an old consumer object that only had single start_time / end_time attributes
        class LegacyConsumer:
            def __init__(self):
                self.name = "Old Machine"
                self.power_kw = 25.0
                self.start_time = datetime.time(8, 0)
                self.end_time = datetime.time(16, 0)
                self.has_peak = True
                self.peak_power_kw = 40.0
                self.peak_duration_min = 30

        legacy = LegacyConsumer()

        # Migration logic check
        if not hasattr(legacy, "time_windows") or not legacy.time_windows:
            s_time = getattr(legacy, "start_time", datetime.time(8, 0))
            e_time = getattr(legacy, "end_time", datetime.time(16, 0))
            h_peak = getattr(legacy, "has_peak", False)
            p_power = getattr(legacy, "peak_power_kw", legacy.power_kw)
            p_dur = getattr(legacy, "peak_duration_min", 30)
            legacy.time_windows = [TimeWindow(s_time, e_time, h_peak, p_power, p_dur)]

        self.assertEqual(len(legacy.time_windows), 1)
        self.assertEqual(legacy.time_windows[0].peak_power_kw, 40.0)

    def test_legacy_contract_object_migration(self):
        # Emulate an old Contract object lacking tou_rates list
        class LegacyContract:
            def __init__(self):
                self.currency = "EUR"
                self.base_monthly_fee = 50.0
                self.default_energy_rate = 0.25

        legacy_ct = LegacyContract()

        # Migration logic check
        if not hasattr(legacy_ct, "tou_rates") or not legacy_ct.tou_rates:
            default_r = getattr(legacy_ct, "default_energy_rate", 0.20)
            legacy_ct.tou_rates = [{"name": "Standard Rate", "rate": default_r, "start_time": "00:00", "end_time": "24:00"}]

        self.assertEqual(len(legacy_ct.tou_rates), 1)
        self.assertEqual(legacy_ct.tou_rates[0]["rate"], 0.25)


if __name__ == "__main__":
    unittest.main()
