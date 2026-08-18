"""
========================================================================================
Load Profile Presets & Factory Configuration (models/presets.py)
========================================================================================

Description:
------------
This module provides ready-to-use, realistic preset profiles representing common
industrial, commercial, and mobility electrification load profiles.
Each preset configures a `LoadAggregator` with specific `LoadComponent` entities,
operational time windows, startup inrush spikes, multi-shift patterns, and standby baselines.

Available Presets:
------------------
1. 🏭 Industry & Manufacturing:
   - Machine 1 (Main Production): 100 kW with 130 kW inrush peak (05:00 - 14:00, Mon-Fri).
   - Machine 2 (CNC Machining): 20 kW with dual shifts (02:00 - 13:00 and 14:00 - 17:00, Mon-Fri).
   - Air Compressor: 30 kW continuous production support (06:00 - 18:00, Mon-Sat).
   - Facility Lighting & Ventilation: 8 kW extended shift (05:00 - 22:00, Mon-Fri).
   - Standby Baseline: 12 kW continuous 24/7.

2. 🏢 Commercial Office Building:
   - IT Infrastructure & Data Center: 15 kW (24/7 continuous operation).
   - Workstations & Lighting: 45 kW (07:30 - 17:30, Mon-Fri).
   - HVAC & Building Ventilation: 25 kW with morning startup peak 35 kW (08:00 - 18:00, Mon-Fri).
   - Standby Baseline: 5 kW continuous 24/7.

3. ⚡ Mobility Hub & Charging Park:
   - 1x DC High-Power Fast Charger: 150 kW peak demand (Morning 07:00-09:30 & Evening 16:30-19:30, 7 days/week).
   - 6x AC Wallboxes: 11 kW each = 66 kW aggregated (Workday commuting 08:00 - 17:00, Mon-Fri).
   - Standby Baseline: 0 kW.

4. ✏️ Custom Profile (User-Defined):
   - A single customizable default machine (50 kW, 08:00 - 16:00, Mon-Fri) ready for full user customization.
"""

import datetime
from typing import Dict, List, Any, Callable
from models.load_component import LoadComponent, TimeWindow
from models.load_aggregator import LoadAggregator


def get_preset_industry() -> LoadAggregator:
    """
    Factory function for the Manufacturing & Heavy Industry preset.

    Characteristics:
      - High morning startup inrush peaks.
      - Dual-shift operations on CNC machines.
      - Saturday compressor operation for maintenance/secondary shifts.
      - Continuous 12 kW standby baseline.
    """
    # Component 1: Heavy Industrial Machine with 30-minute startup peak
    comp1 = LoadComponent(
        name="Machine 1 (Main Production)",
        category="Production",
        nominal_power_kw=100.0,
        peak_power_kw=130.0,
        count=1,
        time_windows=[
            TimeWindow(
                start_time=datetime.time(5, 0),
                end_time=datetime.time(14, 0),
                has_peak=True,
                peak_power_kw=130.0,
                peak_duration_min=30
            )
        ],
        active_days=[0, 1, 2, 3, 4],  # Monday to Friday
        is_active=True
    )

    # Component 2: CNC Machining center operating two distinct daily shifts
    comp2 = LoadComponent(
        name="Machine 2 (CNC Machining)",
        category="Production",
        nominal_power_kw=20.0,
        peak_power_kw=25.0,
        count=1,
        time_windows=[
            TimeWindow(start_time=datetime.time(2, 0), end_time=datetime.time(13, 0)),
            TimeWindow(start_time=datetime.time(14, 0), end_time=datetime.time(17, 0))
        ],
        active_days=[0, 1, 2, 3, 4],  # Monday to Friday
        is_active=True
    )

    # Component 3: Air Compressor operating 6 days a week (Mon-Sat)
    comp3 = LoadComponent(
        name="Air Compressor",
        category="Production",
        nominal_power_kw=30.0,
        peak_power_kw=30.0,
        count=1,
        time_windows=[
            TimeWindow(start_time=datetime.time(6, 0), end_time=datetime.time(18, 0))
        ],
        active_days=[0, 1, 2, 3, 4, 5],  # Monday to Saturday
        is_active=True
    )

    # Component 4: Lighting & Extraction Ventilation
    comp4 = LoadComponent(
        name="Facility Lighting & Ventilation",
        category="Lighting",
        nominal_power_kw=8.0,
        peak_power_kw=8.0,
        count=1,
        time_windows=[
            TimeWindow(start_time=datetime.time(5, 0), end_time=datetime.time(22, 0))
        ],
        active_days=[0, 1, 2, 3, 4],  # Monday to Friday
        is_active=True
    )

    return LoadAggregator(
        components=[comp1, comp2, comp3, comp4],
        baseline_enabled=True,
        baseline_power_kw=12.0,
        year=2026
    )


def get_preset_office() -> LoadAggregator:
    """
    Factory function for the Commercial Office Building preset.

    Characteristics:
      - 24/7 IT Data Center load.
      - Daytime office occupancy profile (07:30 - 17:30).
      - HVAC ventilation with morning thermal conditioning inrush.
      - Continuous 5 kW standby baseline.
    """
    # Component 1: 24/7 Continuous Server & Network Infrastructure
    comp_it = LoadComponent(
        name="IT Infrastructure / Data Center",
        category="IT & Office",
        nominal_power_kw=15.0,
        peak_power_kw=15.0,
        count=1,
        time_windows=[
            TimeWindow(start_time=datetime.time(0, 0), end_time=datetime.time(0, 0))  # 24h
        ],
        active_days=[0, 1, 2, 3, 4, 5, 6],  # 7 days / week
        is_active=True
    )

    # Component 2: Workstation PCs, Monitors, Lighting & Kitchen
    comp_work = LoadComponent(
        name="Workstations & Lighting",
        category="IT & Office",
        nominal_power_kw=45.0,
        peak_power_kw=50.0,
        count=1,
        time_windows=[
            TimeWindow(start_time=datetime.time(7, 30), end_time=datetime.time(17, 30))
        ],
        active_days=[0, 1, 2, 3, 4],  # Monday to Friday
        is_active=True
    )

    # Component 3: HVAC System with 45-minute morning pre-conditioning peak
    comp_hvac = LoadComponent(
        name="HVAC & Ventilation",
        category="HVAC",
        nominal_power_kw=25.0,
        peak_power_kw=35.0,
        count=1,
        time_windows=[
            TimeWindow(
                start_time=datetime.time(8, 0),
                end_time=datetime.time(18, 0),
                has_peak=True,
                peak_power_kw=35.0,
                peak_duration_min=45
            )
        ],
        active_days=[0, 1, 2, 3, 4],  # Monday to Friday
        is_active=True
    )

    return LoadAggregator(
        components=[comp_it, comp_work, comp_hvac],
        baseline_enabled=True,
        baseline_power_kw=5.0,
        year=2026
    )


def get_preset_mobility_hub() -> LoadAggregator:
    """
    Factory function for the EV Charging & Mobility Hub preset.

    Characteristics:
      - 1x 150 kW DC Fast Charger with commuter peaks in morning and late afternoon.
      - 6x 11 kW AC Wallboxes utilized during normal working hours (total 66 kW).
      - No standby baseline.
    """
    # 150 kW DC High Power Charger (Morning & Evening commuting spikes)
    comp_dc = LoadComponent(
        name="DC High-Power Fast Charger (150 kW)",
        category="Mobility",
        nominal_power_kw=150.0,
        peak_power_kw=150.0,
        count=1,
        time_windows=[
            TimeWindow(start_time=datetime.time(7, 0), end_time=datetime.time(9, 30)),
            TimeWindow(start_time=datetime.time(16, 30), end_time=datetime.time(19, 30))
        ],
        active_days=[0, 1, 2, 3, 4, 5, 6],  # Available all week
        is_active=True
    )

    # 6x 11 kW AC Employee & Fleet Charging Points
    comp_ac = LoadComponent(
        name="AC Charging Stations (6x 11 kW)",
        category="Mobility",
        nominal_power_kw=11.0,
        peak_power_kw=11.0,
        count=6,
        time_windows=[
            TimeWindow(start_time=datetime.time(8, 0), end_time=datetime.time(17, 0))
        ],
        active_days=[0, 1, 2, 3, 4],  # Workdays
        is_active=True
    )

    return LoadAggregator(
        components=[comp_dc, comp_ac],
        baseline_enabled=False,
        baseline_power_kw=0.0,
        year=2026
    )


def get_preset_custom() -> LoadAggregator:
    """
    Factory function providing a minimal custom baseline to start modeling from scratch.
    """
    comp1 = LoadComponent(
        name="Machine 1",
        category="Production",
        nominal_power_kw=50.0,
        peak_power_kw=60.0,
        count=1,
        time_windows=[
            TimeWindow(start_time=datetime.time(8, 0), end_time=datetime.time(16, 0))
        ],
        active_days=[0, 1, 2, 3, 4],
        is_active=True
    )
    return LoadAggregator(
        components=[comp1],
        baseline_enabled=False,
        baseline_power_kw=0.0,
        year=2026
    )


# --------------------------------------------------------------------------------------
# Public Preset Options Registry
# --------------------------------------------------------------------------------------
# Maps human-readable UI names and icons to their corresponding generator factory functions.
PRESET_OPTIONS: Dict[str, Callable[[], LoadAggregator]] = {
    "🏭 Industry & Manufacturing (Machines, Shifts & Peaks)": get_preset_industry,
    "🏢 Commercial Office Building (IT, HVAC & Workstations)": get_preset_office,
    "⚡ Mobility Hub & Charging Park (DC/AC EV Infrastructure)": get_preset_mobility_hub,
    "✏️ Custom Profile (Build Your Own)": get_preset_custom
}
