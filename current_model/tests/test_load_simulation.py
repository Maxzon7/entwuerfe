"""
========================================================================================
Unit Tests for Load Simulation & Aggregator Engine (tests/test_load_simulation.py)
========================================================================================

Description:
------------
Comprehensive test suite verifying:
  1. Single and dual operating time windows.
  2. Startup peak power spikes and durations.
  3. Continuous 24/7 operations and overnight shifts across midnight.
  4. Full aggregator synthesis and KPI calculations.
"""

import datetime
import numpy as np
import pandas as pd

from current_model.models.load_component import LoadComponent, TimeWindow, SimpleConsumer
from current_model.models.presets import get_industry_preset_consumers
from current_model.core.synthetic_engine import aggregate_synthetic_24h, aggregate_synthetic_year


def test_time_window_single_and_dual():
    """Tests a machine with two distinct operational shifts on weekdays."""
    # Machine 2: 20 kW, 02:00 to 13:00 AND 14:00 to 17:00
    comp = LoadComponent(
        name="Machine 2",
        power_kw=20.0,
        time_windows=[
            TimeWindow(start_time=datetime.time(2, 0), end_time=datetime.time(13, 0)),
            TimeWindow(start_time=datetime.time(14, 0), end_time=datetime.time(17, 0))
        ],
        active_days=[0, 1, 2, 3, 4],
        is_active=True
    )

    curve = comp.get_daily_array_15min(day_of_week=0)  # Monday
    assert len(curve) == 96

    # 01:00 is step 4 -> should be 0 kW
    assert curve[4] == 0.0

    # 02:00 is step 8 -> should be 20 kW
    assert curve[8] == 20.0
    # 12:45 is step 51 -> should be 20 kW
    assert curve[51] == 20.0

    # 13:15 is step 53 (between 13:00 and 14:00) -> should be 0 kW
    assert curve[53] == 0.0

    # 14:00 is step 56 -> should be 20 kW
    assert curve[56] == 20.0
    # 16:45 is step 67 -> should be 20 kW
    assert curve[67] == 20.0

    # 17:15 is step 69 -> should be 0 kW
    assert curve[69] == 0.0

    # On Sunday (day_of_week=6), curve should be all 0 kW
    sunday_curve = comp.get_daily_array_15min(day_of_week=6)
    assert np.all(sunday_curve == 0.0)


def test_peak_load_spike():
    """Tests startup inrush peak spike calculation."""
    # Machine 1: 100 kW, 05:00-14:00 with 130 kW peak for 30 minutes
    comp = LoadComponent(
        name="Machine 1",
        power_kw=100.0,
        time_windows=[
            TimeWindow(
                start_time=datetime.time(5, 0),
                end_time=datetime.time(14, 0),
                has_peak=True,
                peak_power_kw=130.0,
                peak_duration_min=30
            )
        ],
        active_days=[0],
        is_active=True
    )

    curve = comp.get_daily_array_15min(day_of_week=0)

    # 05:00 is step 20 -> 130 kW
    assert curve[20] == 130.0
    # 05:15 is step 21 -> 130 kW
    assert curve[21] == 130.0
    # 05:30 is step 22 -> 100 kW
    assert curve[22] == 100.0
    # 13:45 is step 55 -> 100 kW
    assert curve[55] == 100.0
    # 14:00 is step 56 -> 0 kW
    assert curve[56] == 0.0


def test_24h_continuous_and_overnight():
    """Tests continuous 24/7 loads and overnight shifts wrapping around midnight."""
    # Server: 24h
    comp_24h = LoadComponent(
        name="Server",
        power_kw=10.0,
        time_windows=[
            TimeWindow(start_time=datetime.time(0, 0), end_time=datetime.time(0, 0))
        ],
        active_days=[0, 1, 2, 3, 4, 5, 6],
        is_active=True
    )
    curve_24h = comp_24h.get_daily_array_15min(day_of_week=0)
    assert np.all(curve_24h == 10.0)

    # Overnight Shift: 22:00 to 06:00
    comp_night = LoadComponent(
        name="Night Shift",
        power_kw=50.0,
        time_windows=[
            TimeWindow(start_time=datetime.time(22, 0), end_time=datetime.time(6, 0))
        ],
        active_days=[0],
        is_active=True
    )
    curve_night = comp_night.get_daily_array_15min(day_of_week=0)
    # 02:00 is step 8 -> active
    assert curve_night[8] == 50.0
    # 12:00 is step 48 -> inactive
    assert curve_night[48] == 0.0
    # 23:00 is step 92 -> active
    assert curve_night[92] == 50.0


def test_aggregator_and_kpis():
    """Tests aggregator DataFrame synthesis, baseload addition, and KPI metrics."""
    consumers = get_industry_preset_consumers()
    df_day, total_day, metrics_day = aggregate_synthetic_24h(consumers=consumers)
    assert len(df_day) == 96
    assert "Total_kW" in df_day.columns
    assert metrics_day["peak_demand_kw"] > 0
    assert metrics_day["daily_energy_kwh"] > 0

    df_year, total_year, metrics_year = aggregate_synthetic_year(consumers=consumers, year=2025)
    assert len(df_year) == 35040
    assert "Total_Demand_kW" in df_year.columns
    assert metrics_year["annual_energy_mwh"] > 0
    assert metrics_year["peak_demand_kw"] > 0


if __name__ == "__main__":
    test_time_window_single_and_dual()
    test_peak_load_spike()
    test_24h_continuous_and_overnight()
    test_aggregator_and_kpis()
    print("All load simulation tests passed successfully!")
